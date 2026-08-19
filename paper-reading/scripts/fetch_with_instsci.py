#!/usr/bin/env python3
"""Run InstSci safely and verify that requested publisher PDFs were captured.

The wrapper keeps different publishers out of the same InstSci invocation,
uses one browser profile per publisher, records detached job IDs, and treats
the generated manifest—not generic terminal text—as the success criterion.

Examples:
  python fetch_with_instsci.py --file dois.txt --output downloads/instsci
  python fetch_with_instsci.py 10.1016/j.inffus.2025.103599 \
      --output downloads/instsci --network direct
  python fetch_with_instsci.py --check downloads/instsci/run-20260818-170000-12345
"""

import argparse
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse


DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
JOB_RE = re.compile(r"Job submitted:\s*([A-Za-z0-9-]+)")
PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def emit(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def normalize_doi(value):
    value = unquote(str(value).strip())
    value = re.sub(r"^doi:\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.IGNORECASE)
    value = value.rstrip(".,;)").strip()
    if not DOI_RE.match(value):
        raise ValueError(f"invalid DOI: {value}")
    return value.lower()


def collect_dois(values, files):
    raw = list(values or [])
    for filename in files or []:
        path = Path(filename).expanduser()
        if not path.is_file():
            raise ValueError(f"DOI file not found: {path}")
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                raw.append(line)
    if not raw:
        raise ValueError("provide at least one DOI or --file")
    seen = set()
    normalized = []
    for value in raw:
        doi = normalize_doi(value)
        if doi not in seen:
            seen.add(doi)
            normalized.append(doi)
    return normalized


def publisher_key(value):
    return re.sub(r"[^a-z0-9_-]+", "-", str(value).strip().lower()).strip("-")


def resolve_instsci(executable):
    candidate = Path(executable).expanduser()
    if not candidate.is_absolute():
        located = shutil.which(str(candidate))
        if not located:
            raise RuntimeError("instsci executable not found on PATH")
        candidate = Path(located)
    if not candidate.exists():
        raise RuntimeError(f"instsci executable not found: {candidate}")
    return candidate.resolve()


def instsci_python(executable):
    """Return the isolated Python used by the uv/pipx InstSci entrypoint."""
    try:
        first_line = Path(executable).read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return None
    if not first_line.startswith("#!"):
        return None
    try:
        command = shlex.split(first_line[2:].strip())
    except ValueError:
        return None
    if not command:
        return None
    python = Path(command[0])
    return python if python.exists() else None


def infer_publisher(executable, doi, runner=subprocess.run):
    """Ask the installed InstSci version to infer its own publisher profile."""
    python = instsci_python(executable)
    if python is None:
        return None
    code = (
        "import re,sys\n"
        "from instsci.publisher_profiles import infer_publisher_profile\n"
        "profile=infer_publisher_profile(sys.argv[1])\n"
        "print(re.sub(r'[^a-z0-9_-]+','-',profile.name.lower()).strip('-') if profile else '')\n"
    )
    try:
        result = runner(
            [str(python), "-c", code, doi],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = publisher_key(result.stdout.strip())
    return value or None


def group_dois(dois, executable, explicit_publisher="auto"):
    explicit = publisher_key(explicit_publisher)
    if explicit and explicit != "auto":
        inferred = {infer_publisher(executable, doi) for doi in dois}
        known = {item for item in inferred if item}
        if known and known != {explicit}:
            raise ValueError(
                f"--publisher {explicit} conflicts with inferred publishers: "
                + ", ".join(sorted(known))
            )
        return OrderedDict([(explicit, list(dois))])

    groups = OrderedDict()
    unknown_index = 0
    for doi in dois:
        key = infer_publisher(executable, doi)
        if not key:
            unknown_index += 1
            key = f"auto-{unknown_index:03d}"
        groups.setdefault(key, []).append(doi)
    return groups


def proxy_reachable(proxy_url, timeout=0.25):
    parsed = urlparse(proxy_url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port
    if port is None:
        port = 1080 if parsed.scheme.startswith("socks") else 8080
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def prepare_child_env(mode="auto", environ=None):
    env = dict(os.environ if environ is None else environ)
    if mode == "inherit":
        return env, "inherited"
    if mode == "direct":
        for key in PROXY_ENV_VARS:
            env.pop(key, None)
        env["INSTSCI_BROWSER_PROXY_MODE"] = "direct"
        return env, "proxy_variables_removed"
    if mode != "auto":
        raise ValueError(f"unknown network mode: {mode}")

    urls = [env[key] for key in PROXY_ENV_VARS if env.get(key)]
    parsed = [urlparse(url) for url in urls]
    loopback_only = bool(parsed) and all(
        item.hostname in {"127.0.0.1", "localhost", "::1"} for item in parsed
    )
    if loopback_only and not any(proxy_reachable(url) for url in urls):
        for key in PROXY_ENV_VARS:
            env.pop(key, None)
        env["INSTSCI_BROWSER_PROXY_MODE"] = "direct"
        return env, "stale_loopback_proxy_removed"
    return env, "inherited"


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "item"


def classify_failure(text):
    text = (text or "").lower()
    categories = (
        ("tls_certificate", ("err_cert", "certificate_verify_failed", "certificate subject", "hostname mismatch", "证书")),
        ("navigation_timeout", ("page.goto: timeout", "navigation timeout", "timeout 60000ms exceeded")),
        ("broker_stopped", ("targetclosederror", "broker for ", "broker stopped", "write epipe", "browser has been closed")),
        ("entitlement_missing", ("entitlement", "subscription access", "purchase pdf", "access denied")),
        ("api_forbidden", ("403 forbidden", "invalid api key", "authentication_error")),
        ("sso_required", ("sso_required", "captcha", "sign in via", "manual login", "login attention")),
        ("pdf_not_captured", ("pdf_not_captured", "viewer_timeout", "pdf response", "0 verified")),
    )
    for category, markers in categories:
        if any(marker in text for marker in markers):
            return category
    return "unknown"


def diagnostic_text(output_dir, stdout="", stderr=""):
    chunks = [stdout or "", stderr or ""]
    output_dir = Path(output_dir)
    for relative in (
        "summary.json",
        "primary/summary.json",
        "primary/summary_partial.json",
        "retry/summary.json",
    ):
        path = output_dir / relative
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    return "\n".join(chunks)


def is_pdf(path):
    try:
        with Path(path).open("rb") as handle:
            return handle.read(5) == b"%PDF-"
    except OSError:
        return False


def validate_output(output_dir, expected_dois):
    output_dir = Path(output_dir)
    summary_path = output_dir / "summary.json"
    manifest_path = output_dir / "complete" / "manifest.json"
    if not summary_path.is_file() or not manifest_path.is_file():
        return {
            "ok": False,
            "complete": False,
            "category": "result_not_ready",
            "summary": str(summary_path),
            "manifest": str(manifest_path),
        }
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "complete": True, "category": "invalid_result_json", "error": str(exc)}
    if not isinstance(manifest, list):
        return {"ok": False, "complete": True, "category": "invalid_manifest"}

    records = {}
    for item in manifest:
        if not isinstance(item, dict) or not item.get("doi"):
            continue
        try:
            records[normalize_doi(item["doi"])] = item
        except ValueError:
            continue

    diagnostic_reasons = {}
    for relative in ("primary/summary.json", "retry/summary.json"):
        path = output_dir / relative
        try:
            phase = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in phase.get("results", []) if isinstance(phase, dict) else []:
            if not isinstance(item, dict) or not item.get("doi"):
                continue
            try:
                diagnostic_reasons[normalize_doi(item["doi"])] = str(item.get("reason") or "")
            except ValueError:
                continue

    failures = []
    verified = []
    for doi in expected_dois:
        record = records.get(normalize_doi(doi))
        if not record:
            failures.append({"doi": doi, "category": "identity_mismatch", "reason": "DOI absent from manifest"})
            continue
        reason = str(record.get("reason") or diagnostic_reasons.get(normalize_doi(doi)) or "")
        pdf_path = str(record.get("pdf_path") or "")
        good = (
            record.get("status") == "success"
            and record.get("verified_match") is True
            and pdf_path
            and is_pdf(pdf_path)
        )
        if good:
            verified.append({"doi": doi, "pdf_path": pdf_path, "size_bytes": record.get("size_bytes", 0)})
        else:
            failures.append(
                {
                    "doi": doi,
                    "category": classify_failure(reason) if reason else "unverified_result",
                    "reason": reason or "manifest entry is not a verified PDF",
                }
            )

    ok = not failures and len(verified) == len(expected_dois)
    return {
        "ok": ok,
        "complete": True,
        "category": "verified" if ok else classify_failure(diagnostic_text(output_dir)),
        "summary": summary,
        "verified": verified,
        "failures": failures,
        "manifest": str(manifest_path),
    }


def parse_job_id(text):
    match = JOB_RE.search(text or "")
    return match.group(1) if match else None


def make_run_root(base):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    root = Path(base).expanduser() / f"run-{stamp}-{os.getpid()}"
    root.mkdir(parents=True, exist_ok=False)
    return root.resolve()


def run_new(args):
    executable = resolve_instsci(args.instsci)
    dois = collect_dois(args.dois, args.files)
    groups = group_dois(dois, executable, args.publisher)
    child_env, network_action = prepare_child_env(args.network)
    root = make_run_root(args.output)
    profile_root = Path(args.browser_profile_root).expanduser()
    state = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(root),
        "instsci": str(executable),
        "network": args.network,
        "network_action": network_action,
        "detach": args.detach,
        "requested_dois": dois,
        "groups": [],
    }

    for key, group_doi_values in groups.items():
        group_dir = root / "groups" / safe_name(key)
        output_dir = group_dir / "output"
        input_path = group_dir / "dois.txt"
        group_dir.mkdir(parents=True, exist_ok=True)
        input_path.write_text("".join(f"{doi}\n" for doi in group_doi_values), encoding="utf-8")
        profile_dir = profile_root / safe_name(key)
        publisher_arg = args.publisher if publisher_key(args.publisher) != "auto" else "auto"
        command = [
            str(executable),
            "papers",
            str(input_path),
            "--publisher",
            publisher_arg,
            "--output",
            str(output_dir),
            "--browser-profile",
            str(profile_dir),
            "--login-timeout",
            str(args.login_timeout),
            "--pdf-timeout",
            str(args.pdf_timeout),
        ]
        if args.institution:
            command.extend(["--institution", args.institution])
        if args.detach:
            command.append("--detach")

        result = subprocess.run(command, check=False, capture_output=True, text=True, env=child_env)
        (group_dir / "command.stdout.log").write_text(result.stdout or "", encoding="utf-8")
        (group_dir / "command.stderr.log").write_text(result.stderr or "", encoding="utf-8")
        combined = "\n".join((result.stdout or "", result.stderr or ""))
        group_state = {
            "publisher": key,
            "dois": group_doi_values,
            "input": str(input_path),
            "output": str(output_dir),
            "browser_profile": str(profile_dir),
            "returncode": result.returncode,
        }
        if args.detach:
            job_id = parse_job_id(combined)
            group_state.update(
                {
                    "job_id": job_id,
                    "status": "submitted" if result.returncode == 0 and job_id else "submission_failed",
                    "category": "submitted" if job_id else classify_failure(combined),
                }
            )
        else:
            verification = validate_output(output_dir, group_doi_values)
            group_state.update(
                {
                    "status": "completed" if verification.get("ok") else "failed",
                    "category": verification.get("category") or classify_failure(combined),
                    "verification": verification,
                }
            )
        state["groups"].append(group_state)
        (root / "instsci-run.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    if args.detach:
        state["complete"] = False
        state["ok"] = all(item.get("status") == "submitted" for item in state["groups"])
    else:
        state["complete"] = True
        state["ok"] = all(item.get("verification", {}).get("ok") for item in state["groups"])
    (root / "instsci-run.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    emit(state)
    return 0 if state["ok"] else 2


def check_existing(args):
    state_path = Path(args.check).expanduser()
    if state_path.is_dir():
        state_path = state_path / "instsci-run.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        emit({"ok": False, "error": f"cannot read wrapper state: {exc}"})
        return 1

    executable = resolve_instsci(state.get("instsci") or args.instsci)
    child_env, network_action = prepare_child_env(state.get("network", args.network))
    pending = False
    for group in state.get("groups", []):
        job_id = group.get("job_id")
        if job_id:
            result = subprocess.run(
                [str(executable), "jobs", "status", job_id, "--json"],
                check=False,
                capture_output=True,
                text=True,
                env=child_env,
            )
            try:
                job = json.loads(result.stdout) if result.returncode == 0 else None
            except json.JSONDecodeError:
                job = None
            group["job"] = job
            job_status = job.get("status") if isinstance(job, dict) else "status_unavailable"
            group["status"] = job_status
            if job_status in {"queued", "running"}:
                pending = True
        verification = validate_output(group["output"], group["dois"])
        group["verification"] = verification
        if verification.get("complete"):
            group["status"] = "completed" if verification.get("ok") else "failed"
            group["category"] = verification.get("category")

    state["checked_at"] = datetime.now().isoformat(timespec="seconds")
    state["network_action"] = network_action
    state["complete"] = not pending and all(
        item.get("verification", {}).get("complete") for item in state.get("groups", [])
    )
    state["ok"] = state["complete"] and all(
        item.get("verification", {}).get("ok") for item in state.get("groups", [])
    )
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit(state)
    if state["ok"]:
        return 0
    return 3 if pending else 2


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dois", nargs="*", help="DOI values; different publishers are separated automatically")
    parser.add_argument("--file", dest="files", action="append", default=[], help="DOI file, one value per line")
    parser.add_argument("--check", help="recheck a detached wrapper run directory or instsci-run.json")
    parser.add_argument("--output", default="downloads/instsci", help="base directory for a timestamped wrapper run")
    parser.add_argument("--publisher", default="auto", help="explicit publisher only when every DOI belongs to it")
    parser.add_argument("--instsci", default="instsci", help="InstSci executable")
    parser.add_argument("--browser-profile-root", default="~/.instsci/profiles", help="one persistent profile is created per publisher")
    parser.add_argument("--institution", default="", help="optional institution override")
    parser.add_argument("--login-timeout", type=int, default=900)
    parser.add_argument("--pdf-timeout", type=int, default=90)
    parser.add_argument("--detach", action="store_true", help="submit jobs and return; use --check later")
    parser.add_argument(
        "--network",
        choices=("auto", "inherit", "direct"),
        default="auto",
        help="auto removes an unreachable loopback proxy; direct removes proxy variables for InstSci only",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return check_existing(args) if args.check else run_new(args)
    except (ValueError, RuntimeError, OSError) as exc:
        emit({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

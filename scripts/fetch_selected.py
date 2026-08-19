#!/usr/bin/env python3
"""Fetch the 60-paper corpus with the project's paper-reading resolver."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELECTION = ROOT / "searches/2026-08-18-human-ai-interaction-2025-2026/selected-papers.tsv"
DEFAULT_OUT = ROOT / "papers/human-ai-interaction-2025-2026"
DEFAULT_STATUS = ROOT / "searches/2026-08-18-human-ai-interaction-2025-2026/fetch-status.json"
FETCHER = ROOT / "paper-reading/scripts/fetch_paper.py"
PYTHON = ROOT / "paper-reading/.venv/bin/python"


def read_selection(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def clean_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    ):
        env.pop(key, None)
    return env


def parse_json_output(stdout: str) -> dict:
    text = stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.rfind("\n{")
        if start >= 0:
            try:
                return json.loads(text[start + 1 :])
            except json.JSONDecodeError:
                pass
    return {"ok": False, "error": "unparseable fetcher output", "stdout_tail": text[-1200:]}


def verify_pdf(result: dict) -> tuple[bool, str | None]:
    value = result.get("pdf_path")
    if not value:
        return False, "fetcher returned no pdf_path"
    path = Path(value)
    if not path.is_file():
        return False, f"missing PDF: {path}"
    with path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            return False, f"invalid PDF header: {path}"
    return True, None


def fetch_one(row: dict[str, str], outdir: Path) -> dict:
    command = [str(PYTHON if PYTHON.exists() else "python3"), str(FETCHER), row["doi"], str(outdir)]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=clean_env(),
            text=True,
            capture_output=True,
            timeout=300,
        )
        result = parse_json_output(completed.stdout)
        result.update({
            "id": row["id"],
            "requested_doi": row["doi"],
            "requested_title": row["title"],
            "returncode": completed.returncode,
            "stderr_tail": completed.stderr[-2000:],
        })
        valid, error = verify_pdf(result)
        result["verified_pdf"] = valid
        if error:
            result["verification_error"] = error
        result["ok"] = bool(result.get("ok") and completed.returncode == 0 and valid)
        return result
    except subprocess.TimeoutExpired as exc:
        return {
            "id": row["id"],
            "requested_doi": row["doi"],
            "requested_title": row["title"],
            "ok": False,
            "error": "fetch timeout after 300 seconds",
            "stdout_tail": (exc.stdout or "")[-1000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-1000:] if isinstance(exc.stderr, str) else "",
        }
    except Exception as exc:
        return {
            "id": row["id"],
            "requested_doi": row["doi"],
            "requested_title": row["title"],
            "ok": False,
            "error": repr(exc),
        }


def write_status(path: Path, results: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "total": len(results),
        "ok": sum(bool(item.get("ok")) for item in results),
        "failed": sum(not item.get("ok") for item in results),
        "results": sorted(results, key=lambda item: item.get("id", "")),
    }
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--ids", nargs="*", help="optional Pxx subset")
    args = parser.parse_args()

    rows = read_selection(args.selection)
    if args.ids:
        wanted = set(args.ids)
        rows = [row for row in rows if row["id"] in wanted]
    args.out.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch_one, row, args.out): row for row in rows}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            write_status(args.status, results)
            print(f"{result['id']}\t{'ok' if result.get('ok') else 'failed'}\t{result.get('requested_doi')}", flush=True)

    write_status(args.status, results)
    return 0 if all(item.get("ok") for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Acquire legal open versions from every OpenAlex location and arXiv title search."""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "searches/2026-08-18-human-ai-interaction-2025-2026/selected-papers.tsv"
OUTDIR = ROOT / "papers/human-ai-interaction-2025-2026"
STATUS = ROOT / "searches/2026-08-18-human-ai-interaction-2025-2026/open-version-status.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
ATOM = {"a": "http://www.w3.org/2005/Atom"}

KNOWN_OPEN_URLS: dict[str, list[tuple[str, str]]] = {
    "P03": [("https://www.research.ed.ac.uk/files/494727834/chi25b-sub3698-cam-i16.pdf", "edinburgh-repository")],
    "P11": [("https://curis.ku.dk/ws/files/449130913/Artificial_Intimacy.pdf", "copenhagen-repository")],
    "P22": [("https://arxiv.org/pdf/2603.07459", "arxiv:2603.07459")],
    "P24": [("https://arxiv.org/pdf/2502.01564", "arxiv:2502.01564")],
    "P28": [("https://pure.uva.nl/ws/files/270380462/3711014.pdf", "uva-repository")],
    "P29": [("https://arxiv.org/pdf/2401.14362", "arxiv:2401.14362")],
    "P43": [("https://arxiv.org/pdf/2502.01448", "arxiv:2502.01448")],
    "P45": [("https://arxiv.org/pdf/2503.15500", "arxiv:2503.15500")],
    "P46": [("https://arxiv.org/pdf/2503.11177", "arxiv:2503.11177")],
    "P50": [("https://arxiv.org/pdf/2501.17299", "arxiv:2501.17299")],
    "P52": [("https://arxiv.org/pdf/2308.07164", "arxiv:2308.07164")],
    "P53": [("https://researchprofiles.ku.dk/files/451949031/Towards_Clinically_Useful_AI.pdf", "copenhagen-repository")],
    "P55": [("https://hal.science/hal-05374294v1/file/main.pdf", "hal:hal-05374294v1")],
    "P58": [("https://scholars.cityu.edu.hk/files/293385767/288540800.pdf", "cityu-repository")],
}


def opener() -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx)
    )


HTTP = opener()


def get(url: str, accept: str = "application/json,*/*", timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    last: Exception | None = None
    for attempt in range(3):
        try:
            with HTTP.open(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            last = exc
            if attempt < 2:
                time.sleep(1 + attempt)
    raise RuntimeError(f"GET failed: {url}: {last}")


def get_json(url: str) -> dict:
    return json.loads(get(url).decode("utf-8", "replace"))


def normalize(text: str) -> str:
    text = text.lower().replace("–", "-").replace("—", "-")
    return " ".join(re.findall(r"[a-z0-9]+", text))


def slug(text: str, length: int = 62) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value[:length].rstrip("-") or "paper"


def arxiv_search(title: str) -> list[dict[str, str]]:
    query = urllib.parse.quote(f'ti:"{title}"')
    url = f"https://export.arxiv.org/api/query?search_query={query}&start=0&max_results=5"
    try:
        root = ET.fromstring(get(url, "application/atom+xml,*/*", timeout=90))
    except Exception:
        return []
    wanted = normalize(title)
    matches: list[dict[str, str]] = []
    for entry in root.findall("a:entry", ATOM):
        found = " ".join((entry.findtext("a:title", default="", namespaces=ATOM)).split())
        ratio = difflib.SequenceMatcher(None, wanted, normalize(found)).ratio()
        if ratio < 0.86:
            continue
        ident = entry.findtext("a:id", default="", namespaces=ATOM).rsplit("/", 1)[-1]
        if ident:
            matches.append({
                "url": f"https://arxiv.org/pdf/{ident}",
                "kind": "arxiv-title-match",
                "arxiv_id": ident,
                "title_ratio": f"{ratio:.3f}",
            })
    return matches


def openalex_record(doi: str) -> dict:
    encoded = urllib.parse.quote(doi.lower(), safe="")
    return get_json(f"https://api.openalex.org/works/doi:{encoded}")


def reconstruct_abstract(inverted: dict | None) -> str | None:
    if not inverted:
        return None
    pairs = [(position, word) for word, positions in inverted.items() for position in positions]
    return " ".join(word for _, word in sorted(pairs))


def candidates_from_openalex(work: dict) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for location in work.get("locations") or []:
        pdf = location.get("pdf_url")
        landing = location.get("landing_page_url") or ""
        source = (location.get("source") or {}).get("display_name") or ""
        if not pdf and "arxiv.org/abs/" in landing:
            pdf = landing.replace("http://", "https://").replace("/abs/", "/pdf/")
        if not pdf or pdf in seen:
            continue
        seen.add(pdf)
        host = urllib.parse.urlparse(pdf).netloc.lower()
        if host == "dl.acm.org":
            priority = 50
        elif "arxiv.org" in host:
            priority = 0
        elif location.get("version") == "acceptedVersion":
            priority = 5
        elif (location.get("source") or {}).get("type") == "repository":
            priority = 10
        else:
            priority = 20
        candidates.append({
            "url": pdf,
            "kind": f"openalex:{source or host}",
            "priority": str(priority),
            "version": location.get("version") or "unknown",
        })
    return sorted(candidates, key=lambda item: int(item["priority"]))


def curl_download(url: str, destination: Path) -> tuple[bool, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".download-", suffix=".pdf", dir=destination.parent, delete=False) as handle:
        temp_path = Path(handle.name)
    env = dict(os.environ)
    for key in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    ):
        env.pop(key, None)
    command = [
        "curl", "--noproxy", "*", "-L", "--fail", "--retry", "2",
        "--retry-delay", "1", "--max-time", "120", "-A", UA,
        url, "-o", str(temp_path),
    ]
    completed = subprocess.run(command, env=env, text=True, capture_output=True, timeout=150)
    if completed.returncode == 0 and temp_path.exists():
        with temp_path.open("rb") as handle:
            valid = handle.read(5) == b"%PDF-"
        if valid:
            temp_path.replace(destination)
            return True, completed.stderr[-600:]
    temp_path.unlink(missing_ok=True)
    return False, completed.stderr[-1000:]


def existing_pdf_for_doi(doi: str) -> tuple[Path, dict] | None:
    for meta_path in OUTDIR.glob("*/meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(meta.get("doi", "")).lower() != doi.lower():
            continue
        for pdf in meta_path.parent.glob("*.pdf"):
            try:
                with pdf.open("rb") as handle:
                    if handle.read(5) == b"%PDF-":
                        return pdf, meta
            except OSError:
                pass
    return None


def acquire(row: dict[str, str], allow_arxiv_search: bool = True) -> dict:
    paper_dir = OUTDIR / f"{row['id'].lower()}-{slug(row['title'])}"
    pdf_path = paper_dir / f"{paper_dir.name}.pdf"
    meta_path = paper_dir / "meta.json"
    result: dict = {"id": row["id"], "doi": row["doi"], "title": row["title"], "paper_dir": str(paper_dir)}

    existing = existing_pdf_for_doi(row["doi"])
    if existing:
        old_pdf, old_meta = existing
        paper_dir.mkdir(parents=True, exist_ok=True)
        if old_pdf.resolve() != pdf_path.resolve():
            shutil.move(str(old_pdf), str(pdf_path))
        result.update({"ok": True, "source": old_meta.get("source", "existing"), "pdf_path": str(pdf_path)})
        work = None
        try:
            work = openalex_record(row["doi"])
        except Exception:
            pass
    else:
        work = openalex_record(row["doi"])

    if work is None:
        try:
            work = openalex_record(row["doi"])
        except Exception as exc:
            work = {}
            result["openalex_error"] = str(exc)

    candidates = [
        {"url": url, "kind": kind, "priority": "-10", "version": "openVersion"}
        for url, kind in KNOWN_OPEN_URLS.get(row["id"], [])
    ]
    candidates.extend(candidates_from_openalex(work))
    if allow_arxiv_search and not any("arxiv" in item["kind"] for item in candidates):
        candidates.extend(arxiv_search(row["title"]))

    if not result.get("ok"):
        attempts = []
        for candidate in candidates:
            ok, detail = curl_download(candidate["url"], pdf_path)
            attempts.append({**candidate, "ok": ok, "detail_tail": detail})
            if ok:
                result.update({"ok": True, "source": candidate["kind"], "pdf_path": str(pdf_path)})
                if candidate.get("arxiv_id"):
                    result["arxiv_id"] = candidate["arxiv_id"]
                break
        result["attempts"] = attempts

    authors = [
        (authorship.get("author") or {}).get("display_name")
        for authorship in (work.get("authorships") or [])
        if (authorship.get("author") or {}).get("display_name")
    ]
    source = ((work.get("primary_location") or {}).get("source") or {}).get("display_name")
    ids = work.get("ids") or {}
    meta = {
        "ok": bool(result.get("ok")),
        "pdf_path": str(pdf_path) if result.get("ok") else None,
        "paper_dir": str(paper_dir),
        "source": result.get("source"),
        "title": work.get("title") or row["title"],
        "authors": authors,
        "year": work.get("publication_year") or int(row["year"]),
        "venue": source or row["venue"],
        "doi": row["doi"],
        "arxiv_id": result.get("arxiv_id") or ids.get("arxiv"),
        "openalex_id": work.get("id") or ids.get("openalex"),
        "preferred_version": row["doi"],
        "analyzed_version": result.get("arxiv_id") or result.get("source") or row["doi"],
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "selection_id": row["id"],
        "theme": row["theme"],
        "requested_venue": row["venue"],
        "publication_date": work.get("publication_date"),
        "evidence_level": "full text" if result.get("ok") else "abstract/metadata only",
    }
    paper_dir.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps({key: value for key, value in meta.items() if value is not None}, ensure_ascii=False, indent=2), encoding="utf-8")
    result["candidate_count"] = len(candidates)
    return result


def write_status(results: list[dict]) -> None:
    payload = {
        "total": len(results),
        "ok": sum(bool(item.get("ok")) for item in results),
        "failed": sum(not item.get("ok") for item in results),
        "results": sorted(results, key=lambda item: item["id"]),
    }
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--no-arxiv-search", action="store_true")
    args = parser.parse_args()
    with SELECTION.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if args.ids:
        wanted = set(args.ids)
        rows = [row for row in rows if row["id"] in wanted]

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as pool:
        futures = {
            pool.submit(acquire, row, not args.no_arxiv_search): row for row in rows
        }
        for future in as_completed(futures):
            row = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"id": row["id"], "doi": row["doi"], "title": row["title"], "ok": False, "error": repr(exc)}
            results.append(result)
            write_status(results)
            print(f"{result['id']}\t{'ok' if result.get('ok') else 'failed'}\t{result.get('source', '')}", flush=True)
    write_status(results)
    return 0 if all(item.get("ok") for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())

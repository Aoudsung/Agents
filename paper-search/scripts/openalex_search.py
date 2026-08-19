#!/usr/bin/env python3
"""Fetch normalized OpenAlex search records with cursor continuation.

The output intentionally keeps public paper identifiers and the next cursor,
instead of saving raw API responses. A Retriever can inspect the new evidence
and decide whether another page or a revised query is more useful.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request


API_URL = "https://api.openalex.org/works"
USER_AGENT = "paper-search-skill/1.0"


def normalize_doi(value):
    if not value:
        return None
    value = urllib.parse.unquote(str(value)).strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    return value or None


def extract_arxiv_id(ids):
    value = (ids or {}).get("arxiv") or (ids or {}).get("ArXiv")
    if not value:
        return None
    value = str(value).strip()
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^/?#\s]+)", value, re.I)
    if match:
        value = match.group(1)
    else:
        value = re.sub(r"^arxiv:\s*", "", value, flags=re.I)
    value = re.sub(r"\.pdf$", "", value, flags=re.I)
    return value if re.match(r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", value) else None


def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return None
    positioned = []
    for word, positions in inverted_index.items():
        for position in positions:
            positioned.append((position, word))
    positioned.sort()
    return " ".join(word for _, word in positioned) or None


def normalize_work(work):
    ids = work.get("ids") or {}
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    authors = []
    for authorship in work.get("authorships") or []:
        name = (authorship.get("author") or {}).get("display_name")
        if name:
            authors.append(name)
    openalex_id = work.get("id") or ids.get("openalex")
    return {
        "openalex_id": openalex_id,
        "doi": normalize_doi(work.get("doi") or ids.get("doi")),
        "arxiv_id": extract_arxiv_id(ids),
        "title": work.get("title"),
        "authors": authors,
        "year": work.get("publication_year"),
        "venue": source.get("display_name"),
        "venue_type": source.get("type"),
        "work_type": work.get("type"),
        "cited_by_count": work.get("cited_by_count"),
        "landing_page": location.get("landing_page_url"),
        "pdf_url": location.get("pdf_url"),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
    }


def record_key(record):
    return record.get("openalex_id") or record.get("doi") or record.get("arxiv_id")


def build_url(query, from_year, cursor, per_page):
    params = {
        "search": query,
        "cursor": cursor,
        "per-page": per_page,
        "select": (
            "id,title,publication_year,doi,ids,authorships,primary_location,"
            "cited_by_count,type,abstract_inverted_index"
        ),
    }
    if from_year:
        params["filter"] = f"from_publication_date:{from_year}-01-01"
    email = os.environ.get("UNPAYWALL_EMAIL")
    if email:
        params["mailto"] = email
    return API_URL + "?" + urllib.parse.urlencode(params)


def fetch_page(query, from_year=None, cursor="*", per_page=50):
    request = urllib.request.Request(
        build_url(query, from_year, cursor, per_page),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload


def search(query, from_year=None, cursor="*", pages=2, per_page=50, pause=1.0):
    records = []
    seen = set()
    next_cursor = cursor
    pages_fetched = 0
    for page_index in range(pages):
        payload = fetch_page(query, from_year, next_cursor, per_page)
        pages_fetched += 1
        for work in payload.get("results") or []:
            record = normalize_work(work)
            key = record_key(record)
            if key and key not in seen:
                seen.add(key)
                records.append(record)
        next_cursor = (payload.get("meta") or {}).get("next_cursor")
        if not next_cursor or not payload.get("results"):
            break
        if pause and page_index + 1 < pages:
            time.sleep(pause)
    return {
        "query": query,
        "from_year": from_year,
        "pages_fetched": pages_fetched,
        "next_cursor": next_cursor,
        "records": records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="search OpenAlex and emit normalized records")
    parser.add_argument("query")
    parser.add_argument("--from-year", type=int)
    parser.add_argument("--cursor", default="*")
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--per-page", type=int, default=50)
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--output", help="write JSON to this path instead of stdout")
    args = parser.parse_args(argv)
    if args.pages < 1:
        parser.error("--pages must be at least 1")
    result = search(
        args.query,
        from_year=args.from_year,
        cursor=args.cursor,
        pages=args.pages,
        per_page=args.per_page,
        pause=args.pause,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)

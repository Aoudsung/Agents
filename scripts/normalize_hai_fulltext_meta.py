#!/usr/bin/env python3
"""Normalize full-text acquisition metadata for the 60-paper HAI corpus."""

from __future__ import annotations

import json
from pathlib import Path


WORKSPACE = Path("/Users/aoudsung/Documents/AcdamicAgents")
PAPER_ROOT = WORKSPACE / "papers" / "human-ai-interaction-2025-2026"

INSTSCI_IDS = {
    "P03", "P08", "P10", "P11", "P13", "P16", "P18", "P20", "P21",
    "P23", "P25", "P26", "P27", "P32", "P34", "P35", "P38", "P39",
    "P48", "P53", "P54", "P55", "P56", "P60",
}
BROWSER_IDS = {"P42", "P57", "P58", "P59"}

# Version IDs verified from the first-page headers of the analyzed local PDFs.
ARXIV_IDS = {
    "P02": "2502.17348v1",
    "P04": "2409.11672v3",
    "P06": "2503.01631v1",
    "P07": "2501.10553v1",
    "P09": "2503.18419v1",
    "P14": "2601.17962v2",
    "P15": "2603.16918v1",
    "P17": "2602.08636v1",
    "P19": "2602.11567v1",
    "P22": "2603.07459v1",
    "P24": "2502.01564v1",
    "P29": "2401.14362v3",
    "P30": "2504.04299v2",
    "P31": "2503.09436v2",
    "P33": "2602.01481v1",
    "P36": "2602.07283v1",
    "P37": "2507.18802v1",
    "P40": "2507.14527v1",
    "P41": "2507.20655v2",
    "P43": "2502.01448v1",
    "P45": "2503.15500v1",
    "P46": "2503.11177v1",
    "P49": "2505.05660v3",
    "P50": "2501.17299v1",
    "P51": "2506.09873v1",
    "P52": "2308.07164v2",
}

# P55/P56 appeared online in 2025 but belong to TOCHI 33(1), February 2026.
FORMAL_PUBLICATION_OVERRIDES = {
    "P55": {"year": 2026, "publication_date": "2026-02-01"},
    "P56": {"year": 2026, "publication_date": "2026-02-01"},
}


def main() -> None:
    changed = 0
    checked = 0
    for meta_path in sorted(PAPER_ROOT.glob("p??-*/meta.json")):
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        selection_id = data.get("selection_id")
        if not selection_id:
            continue
        checked += 1
        paper_dir = meta_path.parent
        slug = paper_dir.name
        pdf_path = paper_dir / f"{slug}.pdf"
        text_path = paper_dir / f"{slug}.txt"
        if not pdf_path.is_file() or not text_path.is_file():
            raise SystemExit(f"missing full text for {selection_id}: {paper_dir}")

        before = json.dumps(data, ensure_ascii=False, sort_keys=True)
        data["ok"] = True
        data["pdf_path"] = str(pdf_path)
        data["text_path"] = str(text_path)
        data["evidence_level"] = "full text"
        if selection_id in ARXIV_IDS:
            data["arxiv_id"] = ARXIV_IDS[selection_id]
            data["analyzed_version"] = ARXIV_IDS[selection_id]
        if selection_id in FORMAL_PUBLICATION_OVERRIDES:
            override = FORMAL_PUBLICATION_OVERRIDES[selection_id]
            old_date = data.get("publication_date")
            if old_date and old_date != override["publication_date"]:
                data["online_publication_date"] = old_date
            data.update(override)
        if selection_id in INSTSCI_IDS:
            data["source"] = "instsci-verified-publisher-pdf"
        elif selection_id in BROWSER_IDS:
            data["source"] = "authenticated-institution-browser-pdf"

        after = json.dumps(data, ensure_ascii=False, sort_keys=True)
        if after != before:
            meta_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            changed += 1

    if checked != 60:
        raise SystemExit(f"expected 60 selected papers, found {checked}")
    print(json.dumps({"checked": checked, "changed": changed}, ensure_ascii=False))


if __name__ == "__main__":
    main()

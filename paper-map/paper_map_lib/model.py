from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

RELATION_TYPES = {
    "supports", "extends", "conditions", "challenges",
    "conflicts", "measurement", "incomparable",
}
RELATION_STATUSES = {"proposed", "accepted", "rejected", "stale"}
ALIGNMENT = {"same", "partial", "different", "unknown"}
EVIDENCE_ALIGNMENT = {"same", "complementary", "different", "unknown"}
COMPARABILITY = {"comparable", "partially-comparable", "incomparable"}
CONCLUSION_STATUS = {"established", "conditional", "contested", "insufficient"}
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}")


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def endpoint_ref(endpoint: Any) -> str:
    if not isinstance(endpoint, dict):
        return ""
    paper_id, unit_id = endpoint.get("paper_id"), endpoint.get("unit_id")
    return f"{paper_id}:{unit_id}" if nonempty(paper_id) and nonempty(unit_id) else ""


def tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text or "")}


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "-", value.strip())
    return value.strip("-") or "item"


def yaml_list(values: Iterable[str]) -> str:
    rows = [str(value).replace('"', "'") for value in values if nonempty(value)]
    return "[]" if not rows else "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in rows) + "]"


def default_map() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "map_id": "paper-map",
        "revision": 1,
        "title": "Paper Map",
        "scope": {"included": [], "excluded": []},
        "knowledge_questions": [],
        "research_routes": [],
        "conclusions": [],
        "controversies": [],
        "reading_path": [],
        "coverage": {"included_papers": [], "known_gaps": []},
    }


def relative_path(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path

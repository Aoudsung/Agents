from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import default_map


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: expected an object")
        rows.append(row)
    return rows


def init_workspace(root: Path) -> None:
    for relative in (
        "knowledge/cards",
        "knowledge-vault/00-Overview",
        "knowledge-vault/10-Papers",
        "knowledge-vault/20-Questions",
        "knowledge-vault/30-Routes",
        "knowledge-vault/40-Controversies",
        "knowledge-vault/90-Human-Notes",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    map_path = root / "knowledge/map.json"
    relations_path = root / "knowledge/relations.jsonl"
    if not map_path.exists():
        write_json(map_path, default_map())
    if not relations_path.exists():
        relations_path.write_text("", encoding="utf-8")


def card_paths(root: Path) -> list[Path]:
    paths = set(root.glob("papers/**/paper-card.json"))
    paths.update(root.glob("knowledge/cards/*.json"))
    return sorted(paths)


def load_cards(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Path], list[str]]:
    cards: dict[str, dict[str, Any]] = {}
    origins: dict[str, Path] = {}
    errors: list[str] = []
    for path in card_paths(root):
        try:
            card = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
            continue
        paper_id = str(card.get("paper_id", "")).strip()
        if not paper_id:
            errors.append(f"{path}: missing paper_id")
        elif paper_id in cards:
            errors.append(f"duplicate paper_id {paper_id}: {origins[paper_id]} and {path}")
        else:
            cards[paper_id], origins[paper_id] = card, path
    return cards, origins, errors

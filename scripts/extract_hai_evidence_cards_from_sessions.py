#!/usr/bin/env python3
"""Recover validated HAI evidence cards from one-shot subagent session logs.

The exploration agents are intentionally read-only.  Their final answers contain a
single JSON evidence card in a fenced block; this utility performs the mechanical
handoff into files that the main agent can validate and render.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


# Accept a numbered regeneration pass as well as the original one-shot agent
# names.  A later pass is used when an earlier agent returned only a summary,
# and the timestamp tie-break below already selects the newest valid card.
AGENT_RE = re.compile(r"^/root/regen(?:\d+)?_p(?P<number>\d{2})$")
FENCED_JSON_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass(frozen=True)
class SessionCard:
    paper_id: str
    session_path: Path
    session_timestamp: str
    card: dict[str, Any]


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL: {exc}") from exc
            if isinstance(value, dict):
                yield value


def session_metadata(records: list[dict[str, Any]]) -> tuple[str | None, str | None, str]:
    for record in records:
        if record.get("type") != "session_meta":
            continue
        payload = record.get("payload", {})
        source = payload.get("source")
        agent_path = None
        if isinstance(source, dict):
            subagent = source.get("subagent")
            if isinstance(subagent, dict):
                spawn = subagent.get("thread_spawn")
                if isinstance(spawn, dict):
                    agent_path = spawn.get("agent_path")
        return payload.get("parent_thread_id"), agent_path, str(payload.get("timestamp", ""))
    return None, None, ""


def assistant_texts(records: list[dict[str, Any]]) -> Iterable[str]:
    for record in records:
        if record.get("type") != "response_item":
            continue
        payload = record.get("payload", {})
        if payload.get("type") != "message" or payload.get("role") != "assistant":
            continue
        for item in payload.get("content", []):
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                yield item["text"]


def extract_card(text: str, expected_id: str) -> dict[str, Any] | None:
    candidates = [match.group(1) for match in FENCED_JSON_RE.finditer(text)]
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append(json.dumps(value, ensure_ascii=False))
    for candidate in reversed(candidates):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(value, dict)
            and value.get("schema_version") == 2
            and value.get("id") == expected_id
        ):
            return value
    return None


def collect_cards(session_root: Path, parent_thread_id: str) -> dict[str, SessionCard]:
    cards: dict[str, SessionCard] = {}
    for path in sorted(session_root.rglob("*.jsonl")):
        records = list(iter_jsonl(path))
        parent_id, agent_path, timestamp = session_metadata(records)
        if parent_id != parent_thread_id or not isinstance(agent_path, str):
            continue
        match = AGENT_RE.fullmatch(agent_path)
        if not match:
            continue
        paper_id = f"P{match.group('number')}"
        card = None
        for text in assistant_texts(records):
            candidate = extract_card(text, paper_id)
            if candidate is not None:
                card = candidate
        if card is None:
            continue
        recovered = SessionCard(paper_id, path, timestamp, card)
        previous = cards.get(paper_id)
        if previous is None or (recovered.session_timestamp, str(path)) > (
            previous.session_timestamp,
            str(previous.session_path),
        ):
            cards[paper_id] = recovered
    return cards


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--parent-thread-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requested = {value.upper() for value in args.only}
    cards = collect_cards(args.sessions, args.parent_thread_id)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    skipped: list[str] = []
    for paper_id, recovered in sorted(cards.items()):
        if requested and paper_id not in requested:
            continue
        destination = args.output_dir / f"{paper_id}.json"
        if destination.exists() and not args.overwrite:
            skipped.append(paper_id)
            continue
        destination.write_text(
            json.dumps(recovered.card, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(paper_id)

    missing = sorted(requested - set(cards)) if requested else []
    print(json.dumps({"written": written, "skipped": skipped, "missing": missing}))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())

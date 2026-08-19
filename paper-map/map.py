#!/usr/bin/env python3
"""Lightweight validator, candidate retriever, and renderer for paper-map."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from paper_map_lib import candidate_neighbors, init_workspace, load_cards, render_workspace, validate_workspace


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("init", "validate", "render"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, default=Path.cwd())
    candidates = commands.add_parser("candidates")
    candidates.add_argument("--root", type=Path, default=Path.cwd())
    candidates.add_argument("--paper", required=True)
    candidates.add_argument("--limit", type=int, default=8)
    return root


def main() -> int:
    args = parser().parse_args()
    root = args.root.resolve()
    if args.command == "init":
        init_workspace(root)
        print(f"initialized {root}")
        return 0
    if args.command == "validate":
        init_workspace(root)
        errors, warnings, stats = validate_workspace(root)
        print(
            f"cards={stats['cards']} knowledge_units={stats['knowledge_units']} "
            f"relations={stats['relations']} errors={len(errors)} warnings={len(warnings)}"
        )
        for warning in warnings:
            print(f"WARNING: {warning}")
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1 if errors else 0
    if args.command == "candidates":
        cards, _, errors = load_cards(root)
        if errors:
            raise ValueError("\n".join(errors))
        if args.paper not in cards:
            raise ValueError(f"unknown paper_id: {args.paper}")
        print(json.dumps(candidate_neighbors(cards, args.paper, max(1, args.limit)), ensure_ascii=False, indent=2))
        return 0
    errors, _, _ = validate_workspace(root)
    if errors:
        raise ValueError("workspace validation failed:\n" + "\n".join(errors))
    render_workspace(root)
    print(f"rendered {root / 'knowledge/MAP.md'} and {root / 'knowledge-vault'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

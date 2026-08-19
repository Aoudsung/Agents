from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import (
    ALIGNMENT, COMPARABILITY, CONCLUSION_STATUS, EVIDENCE_ALIGNMENT,
    RELATION_STATUSES, RELATION_TYPES, default_map, endpoint_ref, nonempty,
)
from .storage import load_cards, read_json, read_jsonl


def validate_card(card: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    if not nonempty(card.get("paper_id")):
        errors.append(f"{label}: paper_id is required")
    if not isinstance(card.get("revision"), int) or card["revision"] < 1:
        errors.append(f"{label}: revision must be a positive integer")
    identity = card.get("identity")
    if not isinstance(identity, dict) or not nonempty(identity.get("title")):
        errors.append(f"{label}: identity.title is required")
    classification = card.get("classification")
    if not isinstance(classification, dict):
        errors.append(f"{label}: classification is required")
    else:
        for field in ("paper_type", "evidence_mode"):
            if not isinstance(classification.get(field), list) or not classification[field]:
                errors.append(f"{label}: classification.{field} must be a non-empty list")
        for field in ("analysis_unit", "inference_scope"):
            if not nonempty(classification.get(field)):
                errors.append(f"{label}: classification.{field} is required")

    units = card.get("knowledge_units", [])
    if not isinstance(units, list):
        errors.append(f"{label}: knowledge_units must be a list")
        units = []
    seen: set[str] = set()
    for index, unit in enumerate(units):
        where = f"{label}: knowledge_units[{index}]"
        if not isinstance(unit, dict):
            errors.append(f"{where} must be an object")
            continue
        unit_id = unit.get("id")
        if not nonempty(unit_id):
            errors.append(f"{where}.id is required")
        elif unit_id in seen:
            errors.append(f"{label}: duplicate knowledge unit id {unit_id}")
        else:
            seen.add(unit_id)
        for field in ("kind", "text", "scope", "statement_source", "support_status"):
            if not nonempty(unit.get(field)):
                errors.append(f"{where}.{field} is required")
        locations = unit.get("evidence_locations")
        if not isinstance(locations, list) or not locations or any(not nonempty(v) for v in locations):
            errors.append(f"{where}.evidence_locations must be a non-empty list")

    reading = card.get("reading")
    if not isinstance(reading, dict):
        errors.append(f"{label}: reading is required")
    else:
        if not nonempty(reading.get("why_read")):
            errors.append(f"{label}: reading.why_read is required")
        for field in ("use_for", "do_not_use_for"):
            if not isinstance(reading.get(field), list):
                errors.append(f"{label}: reading.{field} must be a list")
    provenance = card.get("provenance")
    if not isinstance(provenance, dict) or not nonempty(provenance.get("content_hash")):
        errors.append(f"{label}: provenance.content_hash is required")
    return errors


def unit_index(cards: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for paper_id, card in cards.items():
        for unit in card.get("knowledge_units", []):
            if isinstance(unit, dict) and nonempty(unit.get("id")):
                result[f"{paper_id}:{unit['id']}"] = unit
    return result


def validate_relation(
    relation: dict[str, Any], cards: dict[str, dict[str, Any]],
    units: dict[str, dict[str, Any]], label: str,
) -> list[str]:
    errors: list[str] = []
    if not nonempty(relation.get("relation_id")):
        errors.append(f"{label}: relation_id is required")
    relation_type, status = relation.get("relation_type"), relation.get("status")
    if relation_type not in RELATION_TYPES:
        errors.append(f"{label}: invalid relation_type {relation_type!r}")
    if status not in RELATION_STATUSES:
        errors.append(f"{label}: invalid status {status!r}")

    for side in ("source", "target"):
        endpoint = relation.get(side)
        ref = endpoint_ref(endpoint)
        if not ref:
            errors.append(f"{label}: {side} endpoint is incomplete")
            continue
        if ref not in units:
            errors.append(f"{label}: unknown {side} endpoint {ref}")
            continue
        card = cards[endpoint["paper_id"]]
        if endpoint.get("revision") != card.get("revision"):
            errors.append(f"{label}: {side} revision does not match {endpoint['paper_id']}")
        expected_hash = card.get("provenance", {}).get("content_hash")
        if endpoint.get("content_hash") != expected_hash:
            errors.append(f"{label}: {side} content_hash does not match {endpoint['paper_id']}")

    comp = relation.get("comparability")
    if not isinstance(comp, dict):
        errors.append(f"{label}: comparability is required")
    else:
        for field in ("knowledge_question", "construct", "analysis_unit", "context"):
            if comp.get(field) not in ALIGNMENT:
                errors.append(f"{label}: invalid comparability.{field}")
        if comp.get("evidence_mode") not in EVIDENCE_ALIGNMENT:
            errors.append(f"{label}: invalid comparability.evidence_mode")
        decision = comp.get("decision")
        if decision not in COMPARABILITY:
            errors.append(f"{label}: invalid comparability.decision")
        if relation_type == "conflicts" and decision != "comparable":
            errors.append(f"{label}: conflicts requires comparable endpoints")
        if relation_type == "incomparable" and decision != "incomparable":
            errors.append(f"{label}: incomparable relation requires incomparable decision")
    if not nonempty(relation.get("rationale")):
        errors.append(f"{label}: rationale is required")
    evidence = relation.get("evidence_refs")
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{label}: evidence_refs must be a non-empty list")
    elif any(ref not in units for ref in evidence):
        errors.append(f"{label}: evidence_refs contains an unknown knowledge unit")
    return errors


def validate_map(data: dict[str, Any], relations: list[dict[str, Any]], label: str) -> list[str]:
    errors: list[str] = []
    for field in ("knowledge_questions", "research_routes", "conclusions", "controversies", "reading_path"):
        if not isinstance(data.get(field), list):
            errors.append(f"{label}: {field} must be a list")
    accepted = {
        row.get("relation_id") for row in relations
        if row.get("status") == "accepted" and nonempty(row.get("relation_id"))
    }
    for index, conclusion in enumerate(data.get("conclusions", [])):
        where = f"{label}: conclusions[{index}]"
        if not isinstance(conclusion, dict):
            errors.append(f"{where} must be an object")
            continue
        if conclusion.get("status") not in CONCLUSION_STATUS:
            errors.append(f"{where}: invalid status")
        relation_ids = conclusion.get("supporting_relations", [])
        if conclusion.get("status") != "insufficient":
            if not isinstance(relation_ids, list) or not relation_ids:
                errors.append(f"{where}: non-insufficient conclusion needs supporting_relations")
            elif any(relation_id not in accepted for relation_id in relation_ids):
                errors.append(f"{where}: conclusion references a non-accepted relation")
    return errors


def validate_workspace(root: Path) -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []
    cards, origins, load_errors = load_cards(root)
    errors.extend(load_errors)
    for paper_id, card in cards.items():
        errors.extend(validate_card(card, str(origins[paper_id])))
    units = unit_index(cards)
    relation_path = root / "knowledge/relations.jsonl"
    try:
        relations = read_jsonl(relation_path)
    except ValueError as exc:
        errors.append(str(exc)); relations = []
    seen: set[str] = set()
    for index, relation in enumerate(relations, 1):
        relation_id = relation.get("relation_id")
        if nonempty(relation_id) and relation_id in seen:
            errors.append(f"{relation_path}:{index}: duplicate relation_id {relation_id}")
        elif nonempty(relation_id):
            seen.add(relation_id)
        errors.extend(validate_relation(relation, cards, units, f"{relation_path}:{index}"))
    map_path = root / "knowledge/map.json"
    try:
        map_data = read_json(map_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc)); map_data = default_map()
    errors.extend(validate_map(map_data, relations, str(map_path)))
    if not cards:
        warnings.append("no paper-card.json files found; structure is valid but the map is empty")
    return errors, warnings, {"cards": len(cards), "knowledge_units": len(units), "relations": len(relations)}

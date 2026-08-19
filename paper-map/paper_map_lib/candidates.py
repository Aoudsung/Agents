from __future__ import annotations

from typing import Any

from .model import nonempty, tokens


def question_text(card: dict[str, Any]) -> str:
    values: list[str] = []
    for item in card.get("research_questions", []):
        if isinstance(item, dict) and nonempty(item.get("text")):
            values.append(item["text"])
        elif nonempty(item):
            values.append(item)
    return " ".join(values)


def candidate_neighbors(cards: dict[str, dict[str, Any]], paper_id: str, limit: int) -> list[dict[str, Any]]:
    source = cards[paper_id]
    source_concepts = {str(v).strip().lower() for v in source.get("concepts", []) if nonempty(v)}
    source_question = tokens(question_text(source))
    hinted = {
        hint.get("target_paper") for hint in source.get("relation_hints", [])
        if isinstance(hint, dict) and nonempty(hint.get("target_paper"))
    }
    result: list[dict[str, Any]] = []
    for other_id, other in cards.items():
        if other_id == paper_id:
            continue
        other_concepts = {str(v).strip().lower() for v in other.get("concepts", []) if nonempty(v)}
        shared_concepts = sorted(source_concepts & other_concepts)
        shared_question = sorted(source_question & tokens(question_text(other)))
        reverse_hint = any(
            isinstance(hint, dict) and hint.get("target_paper") == paper_id
            for hint in other.get("relation_hints", [])
        )
        has_hint = other_id in hinted or reverse_hint
        score = len(shared_concepts) * 4 + min(len(shared_question), 6) + (6 if has_hint else 0)
        if score <= 0:
            continue
        reasons: list[str] = []
        if shared_concepts:
            reasons.append("shared concepts: " + ", ".join(shared_concepts[:5]))
        if shared_question:
            reasons.append("question token overlap: " + ", ".join(shared_question[:5]))
        if has_hint:
            reasons.append("relation hint")
        result.append({"paper_id": other_id, "score": score, "reasons": reasons})
    return sorted(result, key=lambda row: (-row["score"], row["paper_id"]))[:limit]

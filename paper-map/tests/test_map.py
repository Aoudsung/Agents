from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))
import paper_map_lib as paper_map


def card(paper_id: str, concept: str, question: str, revision: int = 1) -> dict:
    return {
        "schema_version": 1,
        "paper_id": paper_id,
        "revision": revision,
        "identity": {"title": f"Paper {paper_id}", "year": 2026, "work_id": f"W-{paper_id}", "analyzed_version": "v1"},
        "classification": {
            "paper_type": ["controlled-experiment"],
            "evidence_mode": ["quantitative"],
            "analysis_unit": "participant decision",
            "inference_scope": "the evaluated task and sample",
        },
        "research_questions": [{"id": "RQ1", "text": question}],
        "knowledge_units": [
            {
                "id": "K1",
                "kind": "finding",
                "text": f"Specific result from {paper_id}",
                "scope": "evaluated task",
                "statement_source": "author_result",
                "evidence_locations": ["TXT:10-20"],
                "support_status": "direct",
            }
        ],
        "contribution": {"text": f"Contribution {paper_id}", "reading_role": "representative"},
        "reading": {"why_read": f"Why read {paper_id}", "use_for": ["supported claim"], "do_not_use_for": ["unmeasured outcome"]},
        "concepts": [concept],
        "relation_hints": [],
        "provenance": {"source_record": f"papers/{paper_id}/research-record.md", "content_hash": "sha256:" + (paper_id.lower().replace("p", "a") * 32)[:64]},
    }


def relation(source: dict, target: dict, decision: str = "comparable", relation_type: str = "supports") -> dict:
    return {
        "schema_version": 1,
        "relation_id": "REL-1",
        "source": {"paper_id": source["paper_id"], "unit_id": "K1", "revision": source["revision"], "content_hash": source["provenance"]["content_hash"]},
        "target": {"paper_id": target["paper_id"], "unit_id": "K1", "revision": target["revision"], "content_hash": target["provenance"]["content_hash"]},
        "relation_type": relation_type,
        "comparability": {
            "knowledge_question": "same",
            "construct": "same",
            "analysis_unit": "same",
            "context": "partial",
            "evidence_mode": "same",
            "decision": decision,
        },
        "rationale": "The two findings address the same question under sufficiently aligned designs.",
        "evidence_refs": [f"{source['paper_id']}:K1", f"{target['paper_id']}:K1"],
        "status": "accepted",
        "confidence": "medium",
    }


class PaperMapTests(unittest.TestCase):
    def create_workspace(self, root: Path) -> tuple[dict, dict]:
        paper_map.init_workspace(root)
        first = card("P01", "reliance calibration", "When is reliance calibrated?")
        second = card("P02", "reliance calibration", "When is reliance calibrated?")
        for item in (first, second):
            path = root / "knowledge/cards" / f"{item['paper_id']}.json"
            paper_map.write_json(path, item)
        return first, second

    def test_valid_pipeline_and_render(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = self.create_workspace(root)
            rel = relation(first, second)
            (root / "knowledge/relations.jsonl").write_text(json.dumps(rel) + "\n", encoding="utf-8")
            state = paper_map.default_map()
            state["conclusions"] = [
                {
                    "id": "C1",
                    "status": "established",
                    "text": "Aligned evidence supports the scoped conclusion.",
                    "supporting_relations": ["REL-1"],
                    "scope": "evaluated tasks",
                    "residual_uncertainty": "external validity",
                }
            ]
            paper_map.write_json(root / "knowledge/map.json", state)

            errors, warnings, stats = paper_map.validate_workspace(root)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])
            self.assertEqual(stats["cards"], 2)
            candidates = paper_map.candidate_neighbors({"P01": first, "P02": second}, "P01", 8)
            self.assertEqual(candidates[0]["paper_id"], "P02")

            human_note = root / "knowledge-vault/90-Human-Notes/note.md"
            human_note.write_text("keep", encoding="utf-8")
            paper_map.render_workspace(root)
            self.assertTrue((root / "knowledge/MAP.md").exists())
            self.assertTrue((root / "knowledge-vault/10-Papers/P01.md").exists())
            self.assertEqual(human_note.read_text(encoding="utf-8"), "keep")

    def test_conflict_requires_full_comparability(self) -> None:
        first = card("P01", "trust", "Does trust change?")
        second = card("P02", "trust", "Does trust change?")
        rel = relation(first, second, decision="partially-comparable", relation_type="conflicts")
        cards = {"P01": first, "P02": second}
        errors = paper_map.validate_relation(rel, cards, paper_map.unit_index(cards), "REL-1")
        self.assertTrue(any("conflicts requires comparable" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

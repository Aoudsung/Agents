#!/usr/bin/env python3
"""Regression tests for the semantic artifact gate."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.qa_hai_artifacts_v2 import (
    BANNED_PHRASES,
    QAResult,
    repeated_substantive_sentences,
    validate_question_contract,
    validate_record,
    validate_report,
    validate_synthesis,
)


def question_return(status: str = "answered", question: str = "论文建立了什么？") -> str:
    return f"""# 精读返回

### Q1｜{question}

- status：{status}
- conclusion：结论
- evidence_location：TXT:12
"""


def valid_record(paper_type: str, claim_id: str) -> str:
    return f"""# 全文证据账本

- paper_type：{paper_type}
- study_design：类型适配设计
- evidence_mode：全文证据
- analysis_unit：论文实际分析单位
- classification_evidence：TXT:12
- reading_role：路线代表
- why_read：提供该类型独有证据
- best_sections：方法与结果
- use_for：理解具体论证
- do_not_use_for：跨情境因果外推

### {claim_id}｜论文特异主张

- evidence_location：TXT:12
"""


class QuestionContractTests(unittest.TestCase):
    def test_exact_q_alignment(self) -> None:
        brief = "# 交接单\n\n### Q1｜论文建立了什么？\n"
        result = QAResult()
        validate_question_contract("P01", brief, question_return(), result)
        self.assertEqual([], result.failures)

        changed = QAResult()
        validate_question_contract(
            "P01",
            brief,
            question_return(question="论文的机制是什么？"),
            changed,
        )
        self.assertTrue(
            any("changed question text" in failure for failure in changed.failures)
        )

    def test_not_applicable_is_valid(self) -> None:
        brief = "# 交接单\n\n### Q1｜是否存在训练链？\n"
        result = QAResult()
        validate_question_contract(
            "P02",
            brief,
            question_return(
                status="not-applicable",
                question="是否存在训练链？",
            ),
            result,
        )
        self.assertEqual([], result.failures)


class SemanticGateTests(unittest.TestCase):
    def test_universal_execution_chain_is_rejected(self) -> None:
        phrase = next(
            item for item in BANNED_PHRASES if item.startswith("执行链可重建为")
        )
        report = f"""# 报告

## 为什么值得读
- reading_role：代表作
## 作者在回答什么
## 论文怎样回答
{phrase}
## 核心发现
- 原文位置：TXT:12
## 论文贡献
## 证据有多强
## 如何阅读、引用与避免误用
- best_sections：结果
- use_for：理解论文
- do_not_use_for：过度外推
## 对精读交接问题的回答
"""
        result = QAResult()
        validate_report("P03", report, result)
        self.assertTrue(
            any("universal-analysis prose" in failure for failure in result.failures)
        )

    def test_repeated_substantive_sentence_is_detected(self) -> None:
        sentence = (
            "这段文字声称所有论文都共享同一种机制、同一种证据关系和同一种"
            "研究机会，因此能够未经修改地复制到彼此完全不同的研究设计中。"
        )
        reports = {
            "P01": f"# 一\n\n{sentence}",
            "P02": f"# 二\n\n{sentence}",
            "P03": f"# 三\n\n{sentence}",
        }
        repeated = repeated_substantive_sentences(reports)
        self.assertEqual(1, len(repeated))
        self.assertEqual(["P01", "P02", "P03"], repeated[0][1])

    def test_heterogeneous_types_do_not_require_fixed_claim_gap_or_opportunity(self) -> None:
        for paper_type, claim_id in (
            ("综述/分类", "C7"),
            ("测量/心理测量", "C12"),
            ("政策/治理", "C2"),
        ):
            with self.subTest(paper_type=paper_type):
                result = QAResult()
                validate_record("PX", valid_record(paper_type, claim_id), result)
                self.assertEqual([], result.failures)

    def test_synthesis_requires_knowledge_first_structure(self) -> None:
        synthesis = """# 领域知识合成

## 领域边界与核心问题树
## 研究传统与路线
## 跨论文证据关系矩阵
## 已相对建立的认识
## 有条件成立或仍有争议的认识
## 暂不可比较的方向
## 分层阅读路径
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "SYNTHESIS.md"
            path.write_text(synthesis, encoding="utf-8")
            result = QAResult()
            validate_synthesis(path, result)
            self.assertEqual([], result.failures)

            path.write_text(
                synthesis + "\n## 可组合的研究程序\n",
                encoding="utf-8",
            )
            legacy = QAResult()
            validate_synthesis(path, legacy)
            self.assertTrue(
                any("agenda-first legacy" in failure for failure in legacy.failures)
            )


if __name__ == "__main__":
    unittest.main()

# 精读返回：<论文标题>

> 论文记录：research-record.md | paper card：paper-card.json | 来源交接单：<path 或 无> | brief_id：<ID> | source_record_revision：<revision>

## 1. 身份与类型纠正

- paper_key：
- work_id：
- version_id：
- DOI：
- arXiv（保留版本）：
- OpenAlex ID：
- 首选引用版本：
- 实际分析版本：
- identity_change：
- paper_type_hypothesis → confirmed：
- study_design_hypothesis → confirmed：
- evidence_mode_hypothesis → confirmed：
- analysis_unit_hypothesis → confirmed：
- classification_evidence：

## 2. 对交接问题的逐项回答

### Q1｜<问题原文>

- status：answered / partial / undetermined / not-applicable
- conclusion：
- evidence_location：
- evidence_type：
- remaining_uncertainty：
- judgment_change：
- reading_value_change：
- relation_hint_change：
- next_search_action：

## 3. 检索判断变更

| 判断 | 精读前 | 全文结果 | 状态：确认/纠正/保留不确定/不适用 | 依据 |
|---|---|---|---|---|

## 4. 阅读价值变更

- reading_value_before：
- reading_value_after：
- reading_role：
- why_read：
- best_sections：
- use_for：
- do_not_use_for：
- priority_change：

## 5. Relation hint 变更

- relation_hint_before：
- relation_hint_after：
- proposed_relation_type：
- related_papers_or_units：
- relation_basis：
- comparability_risks：
- relation_status：proposed

> 本节不构成 canonical relation。Map Agent 读取 paper-card 后执行可比性门和最终裁定。

## 6. 可回用于检索的新信息

- 更准确的术语：
- 关键前驱、后续、竞争工作或反证：<附 DOI/arXiv/OpenAlex>
- 值得扩展的引用关系：
- 建议新增或改写的查询：
- 需要 Search 定向核查的 Claim、relation hint 或研究机会：
- invalidated_routes_or_tasks：

## 7. 论文真正建立了什么

- 具体贡献：
- 最强证据：
- 最重要的零结果、反例或边界：
- 未建立的内容：
- paper-card knowledge units：

## 8. 建议 Search 更新

<明确指出 Search research-record 中要修改的身份、类型、阅读作用、relation hint、证据层级、未决问题或查询；没有变化时说明原因。>

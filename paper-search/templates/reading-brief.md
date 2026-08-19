# 精读交接单：<论文标题>

> 来源检索：<search-dir>/research-record.md | brief_id：<稳定 ID> | source_record_revision：<修订号> | 建立时间：<日期>

## 1. 论文身份

- paper_key：
- work_id：
- version_id：
- DOI：
- arXiv（保留版本）：
- OpenAlex ID：
- 首选版本及理由：
- 论文输入：
- 当前身份或版本疑点：

## 2. 检索级类型假设

- paper_type_hypothesis：<可多标签>
- study_design_hypothesis：
- evidence_mode_hypothesis：
- analysis_unit_hypothesis：
- classification_basis：<metadata / abstract / full-text 线索及位置>
- 允许 Analysis 纠正：是

## 3. 为什么现在读

- reading_role：
- reading_value_hypothesis：
- priority_reason：
- best_alternative_and_why_insufficient：

## 4. Provisional relation hint

- source_or_target_papers：
- source_or_target_units：<若未知写 unknown>
- proposed_relation_type：supports / extends / conditions / challenges / conflicts / measurement / incomparable
- claimed_relation：
- comparability_risks：
- evidence_level：metadata / abstract / full text
- relation_status：provisional

> Analysis 只核查当前论文能够支持的部分，并输出 proposed hint。最终关系由 Map Agent 裁定。

## 5. 需要精读核实的问题

### Q1｜<问题原文>

- target_judgment：
- current_search_judgment：
- why_it_matters：
- expected_evidence：<章节/表/图/统计/质性材料/理论步骤/版本信息>
- priority：high / medium / low
- allowed_status：answered / partial / undetermined / not-applicable

## 6. 相关工作与竞争解释

<只列会改变 Q#、阅读价值或 relation hint 的论文，写清身份与证据层级。>

## 7. 当前证据边界

- 仅有 metadata/abstract 的判断：
- 尚未确认的身份、版本、方法、结果或引用：
- 可能的类型误判：
- 本轮不要求 Analysis 回答的内容：

## 8. 返回合同

Analysis 必须逐字保留每个 Q# 与题目，并逐项返回 status、conclusion、evidence location/type、remaining uncertainty、judgment change、reading value change、relation hint change 和 next search action；同时生成符合 Schema 的 `paper-card.json`。

# 全文证据账本：<论文标题>

> revision：<修订号> | 建立时间：<日期> | 最近更新：<日期>

## 1. 论文身份与来源

- paper_key：
- work_id：
- version_id：
- DOI：
- arXiv（保留版本）：
- OpenAlex ID：
- 标题、作者、年份、venue：
- 首选引用版本：
- 实际分析版本：
- PDF/TXT 与提取方式：
- reading-brief：
- 来源检索记录：
- 身份或版本纠正：

## 2. 证据类型路由

- paper_type：<可多标签>
- study_design：
- evidence_mode：
- analysis_unit：
- data_or_materials：
- inference_scope：
- selected_reading_route：
- classification_evidence：<原文方法/问题位置>
- unresolved_classification：
- 不适用模块：<例如训练链/交互执行链/因果审计，说明原因>

## 3. 本次问题合同

复制每个 Q#，题目必须与 reading-brief 完全一致。

### Q1｜<问题原文>

- target_judgment：
- expected_evidence：
- status：answered / partial / undetermined / not-applicable
- current_answer：
- evidence_location：
- remaining_uncertainty：

## 4. 作者的问题与论证结构

### 4.1 作者认为出了什么问题

### 4.2 研究问题、命题或设计目标

### 4.3 论证地图

| 步骤/研究/章节 | 回答的问题 | 材料或方法 | 直接产出 | 与下一步的关系 |
|---|---|---|---|---|

### 4.4 作者声称的贡献

- 概念贡献：
- 方法或设计贡献：
- 实证或理论贡献：
- 测量、制度或实践贡献：
- 作者没有声称的内容：

## 5. 研究设计与证据

按 paper_type 只保留适用项。

### 方法或模型

- 数据、表示、目标函数：
- 训练路径：
- 推理路径：
- 基线、消融和评估：

### 交互系统或设计

- 设计问题与 rationale：
- 系统实际提供的能力：
- 用户实际如何使用：
- 被同时改变的组件：
- 可用性、过程和实际效用证据：

### 受控实验

- 操纵和条件：
- 样本、分配和统计单位：
- 估计量、主要终点和多重比较：
- 零结果、方向冲突和敏感性：

### 质性、调查、民族志或现场研究

- 情境、参与者和招募：
- 材料或数据来源：
- 分析和编码过程：
- 主题证据、反例和参与者引文：
- 代表性、反身性和转移边界：

### 综述、分类或指南分析

- 检索或语料范围：
- 纳入排除：
- 编码框架与可靠性：
- 描述性模式：
- 描述到解释的推断：

### 测量或量表验证

- 构念与题项来源：
- 样本与划分：
- 信度、结构效度、标准或行为关联：
- 不变性、方法效应和替代模型：

### 理论、概念、政策、治理或审计

- 定义、命题或规范对象：
- 语料、案例或推导步骤：
- 权力、责任和实施条件：
- 经验主张与规范主张的边界：

### 混合方法整合

| 组成方法 | 单独回答什么 | 证据 | 如何与其他方法整合 | 冲突或未闭合之处 |
|---|---|---|---|---|

## 6. 核心 Finding、零结果和例外

| Finding ID | 具体发现 | 证据类型 | 样本/设置/分析单位 | 原文位置 | 作者解释 | 边界或反例 |
|---|---|---|---|---|---|---|

关键数字记录标签、分母、比较组、方向、显著性或不确定性。质性发现记录材料范围和反例；理论发现记录假设与推导。

## 7. 论文特异的 Claim-Evidence Cards

### <C#>｜<具体主张>

- claim_text：
- statement_source：author statement / author interpretation / analyst inference
- claim_kind：descriptive / associational / causal / mechanism / design / measurement / theoretical / normative / extrapolative
- analysis_unit：
- evidence_type：
- evidence_location：
- observed_result：
- inference_rule：
- required_assumptions：
- support_status：direct / conditional / indirect / undetermined / contradicted
- boundary_conditions：
- related_question：Q#
- unresolved_part：

> 通用 Claim 不是合格 Claim。证据位置存在不等于语义支持。

## 8. 贡献与阅读价值

- 本文独有的知识增量：
- reading_role：
- why_read：
- audience：
- reading_priority 与理由：
- best_sections：
- use_for：
- do_not_use_for：
- 可跳过的部分及条件：

## 9. Proposed relation hints

| 当前 unit | 目标论文/unit | proposed type | 为什么值得比较 | 可比性风险 | 当前证据层级 | status |
|---|---|---|---|---|---|---|

proposed type：supports / extends / conditions / challenges / conflicts / measurement / incomparable。status 固定为 proposed；最终裁定由 Map Agent 完成。

## 10. 证据审计

| Claim | 证据实际观察什么 | 语义是否匹配 | 关键假设 | 合理替代解释 | 当前结论 |
|---|---|---|---|---|---|

- 关键数字复核：
- 统计或测量警报：
- 质性材料覆盖与反例：
- 图表、公式、附录或工件核查：
- 无法确认的内容：

## 11. 可选：科学 Gap

没有符合条件的 Gap 时写“未生成：当前最需要的是理解、测量或外部核查，而非构造研究缺口”。

### <G#>｜<标题>

- affected_claim：
- observed：
- required_relation：
- missing_variable_or_intervention：
- why_it_changes_the_conclusion：
- discriminating_observation：
- different_predictions：
- scope_and_locus：

## 12. 可选：候选研究程序

候选进入研究决策前必须完成 Search 最近工作核查；不得写入 paper-card 的 contribution 或 knowledge units。

### <O#>｜<标题>

- source_gap：
- research_question：
- evidence_basis：
- hypothesis_and_alternatives：
- discriminating_study：
- design_requirements：
- informative_outcomes：
- closest_work_and_difference：
- novelty_check：
- feasibility_boundary：

## 13. 对 reading-brief 的逐项回答

### Q1｜<问题原文>

- status：
- conclusion：
- evidence_location：
- evidence_type：
- remaining_uncertainty：
- judgment_change：
- reading_value_change：
- relation_hint_change：
- next_search_action：

## 14. paper-card 导出清单

- card path：paper-card.json
- schema version：1
- card revision：
- content hash：
- 导出的 research questions：
- 导出的 knowledge units：
- 导出的 contribution：
- 导出的 relation hints：
- 未导出内容及原因：<例如 Reader 后续研究建议>
- 与本账本一致性检查：pass / fail

## 15. 返回 Search 的变更集

- identity_change：
- type_change：
- judgment_change：
- reading_value_before：
- reading_value_after：
- reading_role：
- relation_hint_before：
- relation_hint_after：
- proposed_relation_type：
- new_terms：
- citations_to_expand：
- invalidated_routes_or_tasks：
- Search research-record 应修改什么：

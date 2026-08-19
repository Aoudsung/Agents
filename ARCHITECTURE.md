# 三 Agent 架构与知识产品契约

## 1. 设计原则

Agent 边界按证据边界划分，而不是按连续推理步骤拆分：

- Searcher 面对外部论文空间；
- Reader 面对单篇全文；
- Mapper 面对多篇已经验证的 paper cards。

这避免 Searcher、Reader 和 Mapper 分别生成一套相互竞争的文献地图。

## 2. 所有权矩阵

| 对象 | Searcher | Reader | Mapper |
|---|---|---|---|
| 候选论文与版本 | authoritative | verify analyzed version | consume |
| 引用谱系 | authoritative | return corrections | consume |
| 单篇论证与 Finding/Claim | no | authoritative | consume |
| 阅读价值 | hypothesis | authoritative | organize path |
| relation hint | propose | propose | adjudicate |
| canonical relation | no | no | authoritative |
| 领域问题树与路线 | candidate frontier | no | authoritative |
| 领域结论、争议、阅读路径 | no | no | authoritative |
| Obsidian 投影 | no | no | authoritative renderer |

## 3. 三类知识产品

### 3.1 检索前沿

`searches/**/research-record.md` 保存候选路线、论文身份、证据层级、精读优先级和 provisional relation hints。它回答“可能有什么”和“下一步读什么”，不回答“领域最终建立了什么”。

### 3.2 单篇知识

`papers/**/research-record.md` 是全文证据账本；`report.md` 是面向研究者的阅读报告；`paper-card.json` 是 Mapper 的结构化输入。Reader 不维护跨论文 synthesis。

### 3.3 跨论文知识

`knowledge/relations.jsonl` 保存 canonical relations；`knowledge/map.json` 保存问题、路线、结论、争议和阅读路径；`MAP.md` 和 Obsidian Vault 是确定性投影。

## 4. 数据流

```text
Search relation hint
      ↓
reading-brief Q#
      ↓
Reader full-text verification
      ↓
paper-card.json
      ↓
Mapper candidate neighborhood
      ↓
comparability gate
      ↓
accepted / rejected / incomparable / stale relation
      ↓
map.json conclusions and reading path
```

`report.md` 可用于人工理解，但不能替代 paper card。Reader 的研究建议不得进入论文贡献或 knowledge unit。

## 5. Paper Card 合同

Card 必须包含：

- 稳定 paper ID、work/version identity 和 revision；
- paper type、evidence mode、analysis unit、inference scope；
- research questions；
- knowledge units 及原文位置与 scope；
- contribution 与 reading role；
- why_read、use_for、do_not_use_for；
- concepts；
- proposed relation hints；
- provenance content hash。

Card 可以没有 knowledge unit 或 relation hint；不得为满足 Schema 制造通用 Claim。

## 6. Canonical Relation 合同

每条 relation 连接两个明确 knowledge units，并记录：

- relation type；
- 五维可比性；
- rationale；
- evidence refs；
- source/target card revision 与 hash；
- accepted / rejected / proposed / stale 状态；
- confidence。

`conflicts` 仅允许在 comparability decision 为 `comparable` 时成立。`incomparable` 必须说明不兼容维度。

## 7. Map Conclusion 合同

每项领域结论必须：

- 自包含；
- 标记 established / conditional / contested / insufficient；
- 引用 accepted relation IDs；
- 写明 scope；
- 写明反例或剩余不确定性。

Mapper 先形成领域认识，再按用户需要提出研究议程。

## 8. 增量与失效

Card revision 或 hash 变化时，仅检查引用该 card/unit 的 relations。端点文本、scope、证据位置、support status 或分析版本发生变化时，将 relation 标记 stale。stale relation 不得继续支撑领域结论。

## 9. Obsidian

Obsidian 是本地浏览层，不是 canonical store。Mapper 生成平面 YAML、普通 Markdown links 和多个局部视图，不生成一张不可读的全局 hairball。渲染不得覆盖 `knowledge-vault/90-Human-Notes/`。

## 10. 轻量实现

首版只使用：

```text
JSON paper cards
JSONL relations
JSON map state
Markdown / Obsidian
Python 3 standard library
Git
```

不依赖 Neo4j、向量数据库、工作流引擎或社区插件。候选召回和关系裁定分离：脚本召回候选，Map Agent 完成语义判断。

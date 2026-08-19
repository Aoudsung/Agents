# paper-search — Search Agent

Search Agent 维护外部检索前沿：问题形式化、A/B/C/D 按需检索、候选召回、引用谱系、版本身份、类型假设、阅读价值、精读优先级和 provisional relation hints。

它不维护 canonical paper-map。所有跨论文关系在 Search 阶段均为候选，必须由 Reader 的全文 `paper-card.json` 和 Map Agent 的可比性判断后才能接受。

## 使用

```text
检索 大语言模型多智能体通信中的信息瓶颈问题
调研 offline preference learning 的可辨识性，重点找反证
以 10.1145/... 为种子扩展谱系和竞争路线
吸收 papers/.../reading-return.md，更新检索前沿
执行 Mapper 请求的复现、负结果或测量工具定向核查
```

产物：

```text
searches/<date>-<topic>/
├── research-record.md
├── search-evidence.md
├── reading-briefs/<paper-key>/reading-brief.md
└── report.md
```

`report.md` 说明覆盖范围、候选路线、代表候选、阅读队列和证据边界，不冒充最终领域合成。`reading-brief.md` 使用稳定 Q#，并将领域关系明确标记为 `provisional relation hint`。

## 与 Reader、Mapper 的衔接

Reader 消费 reading brief，返回 Q# 状态、全文证据、阅读价值变化和 relation hint 变化，并生成 `paper-card.json`。Mapper 读取 cards，裁定 canonical relation。

Search 可以读取 Mapper 已接受的 relation ID 作为后续检索事实，但不得另建一份权威关系状态，也不得直接写入 `knowledge/relations.jsonl` 或 `knowledge/map.json`。

## OpenAlex

```bash
python3 scripts/openalex_search.py "<query>" --from-year 2023 --pages 2
```

是否继续翻页由新增研究问题、谱系角色、反证和未决问题决定，不固定只看第一页。摘要只形成待核假设，不替代全文评价。

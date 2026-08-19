# paper-search — Search Agent

围绕研究问题建立可持续更新的文献地图和阅读导航。单一 Search Agent 统一完成问题形式化、A/B/C/D 按需检索、候选召回、引用谱系、版本身份、研究类型假设、证据关系、阅读价值判断、定向外部核查和精读选择。

A/B/C/D 是四种检索意图，不是四个 Agent：

- A：直接相关；
- B：科学邻域；
- C：跨领域同构机制；
- D：缺口、负结果与反向证据。

只有某类结果可能改变当前判断时才启用。核心状态是 `research-record.md`；实际查询、候选和引用证据放在 `search-evidence.md`。新证据可以修订旧查询、版本关系、论文阅读作用或路线判断。

## 使用

```text
检索 大语言模型多智能体通信中的信息瓶颈问题
调研 offline preference learning 的可辨识性，重点找反证
以 10.1145/... 为种子扩展它的谱系和竞争路线
吸收 papers/.../reading-return.md，更新上次检索
核查某个候选研究程序是否已有最近工作
```

产物位于工作区根的 `searches/`：

```text
searches/<date>-<topic>/
├── research-record.md
├── search-evidence.md
├── reading-briefs/<paper-key>/reading-brief.md
└── report.md
```

每篇候选保留文件系统安全的 `paper_key`，并分别保存规范 DOI、带版本 arXiv ID、OpenAlex ID、首选版本和证据层级。候选还要记录 `paper_type / study_design / evidence_mode / analysis_unit` 假设、`reading role / why read` 与领域关系。摘要只用于形成待核假设，不替代全文评价。

## Search 与 Analysis

Search 为优先论文生成 `reading-brief.md`，说明为什么现在读、类型与领域关系假设，以及哪些问题会改变当前判断。问题使用稳定 Q#，措辞保持中性，不预设论文包含交互链、训练链、Gap 或组件实验。

`paper-reading` 的 Analysis Agent 消费交接单并生成 `reading-return.md`。返回必须逐字保留 Q#，显式给出 `answered / partial / undetermined / not-applicable`，并记录阅读价值和领域关系的前后变化。Search 将全文纠正写回当前记录，只更新受影响的查询、谱系、阅读路径或路线。

Search 的 `report.md` 是知识优先的文献地图：先写领域边界、问题树、研究传统、证据关系、相对建立的认识、争议与不可比较项，再给出分层阅读路径。P 编号只用于定位，不能替代论文标题、独有贡献和为什么读。

## OpenAlex

```bash
python3 scripts/openalex_search.py "<query>" --from-year 2023 --pages 2
```

输出包含规范化公开标识和 `next_cursor`。是否继续翻页由新增机制族、谱系角色、反证和未决问题决定，不固定只看第一页。

## 依赖

- Python 3 标准库，用于 OpenAlex 结构化检索助手；
- OpenAlex、arXiv、Crossref、OpenCitations 和网页搜索；
- 可选 `ELSEVIER_API_KEY`、`S2_API_KEY`、`UNPAYWALL_EMAIL`。

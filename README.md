# AcademicAgents — 三 Agent 论文知识工作流

本项目将论文研究流程拆成三个证据边界清晰的 Agent：

- **Search Agent**：维护外部检索前沿，负责候选召回、身份版本、引用谱系、阅读优先级和 provisional relation hints；
- **Analysis Agent**：负责单篇全文、作者论证、Finding/Claim-Evidence、阅读价值，以及结构化 `paper-card.json`；
- **Map Agent**：负责多篇论文之间的可比性、canonical relations、领域问题树、研究路线、争议和阅读路径。

成功标准不是文件齐全或图中边很多，而是：

1. 单篇报告能说明论文做了什么、发现了什么、为什么值得读；
2. 每条跨论文关系都连接明确知识单元，并说明可比性和适用条件；
3. `knowledge/MAP.md` 能形成自包含、可追溯的领域认识。

## 权威状态

```text
Search  → searches/**/research-record.md     # 检索前沿与候选假设
Reader  → papers/**/research-record.md       # 单篇全文证据账本
Reader  → papers/**/paper-card.json          # Mapper 的单篇机器合同
Mapper  → knowledge/relations.jsonl          # canonical relation state
Mapper  → knowledge/map.json                 # 问题、路线、结论与阅读路径
Mapper  → knowledge/MAP.md                    # 面向研究者的领域地图
Mapper  → knowledge-vault/                    # Obsidian 投影
```

`report.md` 面向人类阅读，不是 Mapper 的主要机器输入。Searcher 和 Reader 可以提出关系候选，但只有 Mapper 能写入 accepted relation。

## 最小闭环

```text
用户问题
  ↓
Search 建立检索前沿并选择值得精读的论文
  ↓
Reader 恢复单篇论证，生成 report.md + paper-card.json
  ↓
Mapper 对齐知识问题和具体 knowledge units
  ↓
可比性判断 → 关系裁定 → map.json
  ↓
MAP.md / INDEX.md / Obsidian Vault
  ↓
缺少外部或全文证据时，向 Searcher/Reader 发最小请求
```

## 目录

```text
Agents/
├── Search-Agent.md
├── Analysis-Agent.md
├── Map-Agent.md
├── ARCHITECTURE.md
├── paper-search/
├── paper-reading/
├── paper-map/
│   ├── SKILL.md
│   ├── schemas/
│   ├── templates/
│   ├── tests/
│   └── map.py
├── knowledge/
│   ├── cards/
│   ├── relations.jsonl
│   └── map.json
└── knowledge-vault/
```

根目录 Agent 定义与对应 Skill 文件保持一致：

```text
Search-Agent.md   == paper-search/SKILL.md
Analysis-Agent.md == paper-reading/SKILL.md
Map-Agent.md      == paper-map/SKILL.md
```

## Paper Map 命令

不需要图数据库、向量数据库或 Obsidian 插件：

```bash
python3 paper-map/map.py init --root .
python3 paper-map/map.py validate --root .
python3 paper-map/map.py candidates --root . --paper P51 --limit 8
python3 paper-map/map.py render --root .
python3 -m unittest discover -s paper-map/tests -v
```

`candidates` 只生成局部候选邻域；它不会自动接受关系。`render` 从 canonical JSON/JSONL 确定性生成 Markdown 与 Obsidian 视图，并保留 `knowledge-vault/90-Human-Notes/`。

## 自动化边界

脚本可以处理路径、结构、revision、候选召回和渲染；不能仅凭摘要、共同关键词、引用边或 embedding 自动生成科学关系。任何 `conflicts` 关系都必须通过可比性门；任何领域结论都必须引用 accepted relation IDs。

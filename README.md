# AcademicAgents — 双 Agent 论文知识工作流

本项目只保留两个顶层 Agent，但不再把“填满同一套分析字段”当成完成：

- Search Agent 负责外部文献空间、论文身份、研究路线、证据关系、阅读优先级和定向核查；
- Analysis Agent 负责单篇全文、论文自己的论证结构、主张—证据关系、阅读价值，以及证据可比时的跨论文知识合成。

成功标准是读者能够回答三组问题：一篇论文为什么值得读、能够怎样引用；它与相邻论文究竟支持、扩展、条件化、挑战还是不可比较；多篇论文共同建立了什么、哪些认识仍有争议。

## 三种产品

三种产品面向不同读者，不能互相替代：

1. research-record.md 是可追溯的证据账本，保存类型路由、分析单位、原文位置、具体 Claim 和未决问题；
2. report.md 是面向研究者的阅读报告，按论文自身的问题与论证组织；
3. papers/SYNTHESIS.md 是领域知识合成，组织问题树、研究传统、证据关系、稳定认识、争议、不可比较项和阅读路径。

Gap、研究机会和独立批评都是按需产物。论文没有交互系统、训练过程或因果识别时，不得为了模板完整而制造对应执行链；not-applicable 是合法结论。

## Agent 闭环

Search 先提出论文类型、阅读价值和领域关系假设，并在 reading-brief.md 中用稳定 Q# 写明需要全文核实的问题。Analysis 先做类型路由，再维护证据账本、生成阅读报告，并在 reading-return.md 中逐字保留 Q#，返回 answered、partial、undetermined 或 not-applicable，以及阅读价值和领域关系的具体变化。Search 只更新被新证据改变的部分。

完整契约见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 目录

```text
AcademicAgents/
├── Search-Agent.md
├── Analysis-Agent.md
├── ARCHITECTURE.md
├── paper-search/
│   ├── SKILL.md
│   ├── README.md
│   ├── scripts/openalex_search.py
│   └── templates/
│       ├── research-record.md
│       ├── search-evidence.md
│       ├── reading-brief.md
│       └── report.md
├── paper-reading/
│   ├── SKILL.md
│   ├── README.md
│   ├── scripts/
│   └── templates/
│       ├── research-record.md
│       ├── critical-review.md
│       ├── reading-return.md
│       ├── report.md
│       └── synthesis.md
└── scripts/
    ├── qa_hai_artifacts.py
    ├── qa_hai_artifacts_v2.py
    └── build_hai_analysis_artifacts.py
```

Search-Agent.md 与 paper-search/SKILL.md、Analysis-Agent.md 与 paper-reading/SKILL.md 分别保持完全一致，便于单文件审阅和实际技能加载。

## 自动化边界

脚本可以校验身份、文件、Q# 对齐、原文位置、索引字段、重复句和合成结构；不能从摘要卡批量发明全文解读、固定 C1–C3、G1/O1 或领域结论。

旧的 build_hai_analysis_artifacts.py 仅保留为问题溯源，入口已经失败关闭。它生成的旧 01–04 文件属于迁移输入，不是现行必需产物。运行以下只读门禁检查当前产物：

```bash
python3 scripts/qa_hai_artifacts.py
```

门禁失败意味着产物尚未满足新的阅读与合成标准，不能用“文件齐全”覆盖失败。

# paper-reading — Analysis Agent

Analysis Agent 深度阅读单篇科研论文。它先识别论文类型、研究设计、证据模式和分析单位，再按论文自身论证组织 Finding、Claim-Evidence、阅读报告和 `paper-card.json`。

机制链、Gap、研究程序和独立批评仅在论文与任务确实需要时启用；外部召回统一交给 `paper-search`；canonical 跨论文关系和领域合成统一交给 `paper-map`。

## 使用

```text
精读 https://arxiv.org/abs/1706.03762v5
分析 10.1038/... 的论证、证据边界和阅读价值
读取 searches/.../reading-brief.md 中指定的论文并返回检索反馈
补读 Mapper 指定的 definition、Claim 或 evidence location
```

产物：

```text
papers/<topic-or-inbox>/<slug>/
├── <slug>.pdf / <slug>.txt / meta.json
├── reading-brief.md
├── research-record.md
├── critical-review.md       # 可选
├── reading-return.md
├── paper-card.json
└── report.md
```

- `research-record.md`：全文证据账本；
- `report.md`：面向研究者的阅读报告；
- `reading-return.md`：返回 Searcher 的证据变化；
- `paper-card.json`：返回 Mapper 的结构化知识索引。

`paper-card.json` 不得包含 Reader 自行提出的后续实验作为论文贡献。关系只能以 `status: proposed` 进入 `relation_hints`；Reader 不写 canonical `relations.jsonl`。

## 脚本

```bash
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
$PY scripts/fetch_paper.py "<paper>" papers/<topic-or-inbox>
$PY scripts/pdf_to_text.py <paper.pdf> -o <paper.txt>
$PY scripts/fetch_with_instsci.py --file /tmp/dois.txt --output downloads/instsci
```

付费全文只通过合法机构授权获取。SSO、2FA、CAPTCHA 由用户本人完成；不索取密码，不绕过付费墙或 TLS。

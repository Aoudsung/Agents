# paper-reading — Analysis Agent

单一 Analysis Agent 深度阅读一篇科研论文。它先识别论文类型、研究设计、证据模式和分析单位，再按论文自己的论证组织 Claim-Evidence 与阅读报告。机制链、Gap、研究程序和独立批评仅在论文与任务确实需要时启用；外部文献召回统一交给 `paper-search`。

## 使用

```text
精读 https://arxiv.org/abs/1706.03762v5
分析 10.1038/... 的论证、证据边界和阅读价值
读取 searches/.../reading-brief.md 中指定的论文并返回检索反馈
综合 papers/ 下已经读过的论文
独立批评某个准备进入研究计划的候选机会
```

支持本地 PDF、arXiv ID/URL、直链 PDF、DOI 和出版社页面。产物结构：

```text
papers/<topic-or-inbox>/<slug>/
├── <slug>.pdf / <slug>.txt / meta.json
├── reading-brief.md
├── research-record.md
├── critical-review.md       # 可选
├── reading-return.md
└── report.md
```

`research-record.md` 是 Agent 与审计使用的证据账本；`report.md` 是面向研究者的阅读报告，两者不得互相复制。前者保存类型路由、原文位置和具体 Claim，后者优先回答为什么读、作者怎样论证、如何引用和不能怎样引用。`critical-review.md` 只在高影响结论、强新颖性主张、用户要求或研究决策需要时生成。

## 与 paper-search 的双向衔接

paper-search 生成 `reading-brief.md`，交付论文身份、类型假设、阅读价值、领域关系和带稳定 Q# 的待核问题。Analysis Agent 逐字保留 Q#，逐项回答并生成 `reading-return.md`，返回：

- DOI、带版本 arXiv ID、OpenAlex ID、首选引用版本和实际分析版本纠正；
- 被全文确认、推翻或仍不能确认的检索判断；
- `answered / partial / undetermined / not-applicable` 状态和原文位置；
- 阅读价值、领域关系及其成立条件的前后变化；
- 更准确的术语、相邻工作和反证线索；
- 值得继续扩展的引用、最近工作和查询；
- 全文证据实际改变了什么。

Search 随后只更新受影响部分，不从头重跑。

跨论文 `SYNTHESIS.md` 不是研究机会清单。它先组织领域边界、问题树、研究传统、证据关系、已建立认识、争议、不可比较项和分层阅读路径；只有前述知识模型成立后，才可选地提出研究议程。

## 脚本

```bash
PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
$PY scripts/fetch_paper.py "<paper>" papers/<topic-or-inbox>
$PY scripts/pdf_to_text.py <paper.pdf> -o <paper.txt>
$PY scripts/fetch_with_instsci.py --file /tmp/dois.txt --output downloads/instsci
```

`fetch_paper.py` 保留公开身份并避免不同直链使用同一个泛化目录；arXiv 有正式 DOI 时优先尝试公开正式版本。`pdf_to_text.py` 只在自动结果明显较差时切换引擎，并报告实际尝试。

付费墙论文首选 [instsci](https://github.com/Rimagination/instsci) 机构浏览器工作流。包装器按出版商拆分 DOI、隔离 profile，并以 manifest 中原 DOI 的 `verified_match=true` 和真实 PDF 为成功条件。Codex 工具执行使用同步模式；`--detach` 只用于普通交互终端，之后用 `--check <run-dir>` 查询。可见浏览器中的学校 SSO/2FA/CAPTCHA 只由用户本人完成，任何情况下都不索要账号密码。

不要混合 publisher、手动复用 broker profile、根据通用登录提示猜测失败原因，或把 `pkill`/删除 Singleton 锁作为首选恢复。先查看 diagnostics，并使用 `session-broker-status`、`session-doctor`、`publisher-doctor` 和 `jobs status/tail/resume`。TLS 错误必须修复代理、DNS 或 CA；不关闭证书验证。不可达 loopback 代理在 `--network auto` 下只对子进程移除；明确直连时使用 `--network direct`。

核心脚本使用 Python 3 标准库。推荐 Poppler `pdftotext`；也支持 PyMuPDF、pdfplumber、pypdf 和显式 `pymupdf4llm`。可选 `UNPAYWALL_EMAIL`、`S2_API_KEY`、`ELSEVIER_API_KEY`。

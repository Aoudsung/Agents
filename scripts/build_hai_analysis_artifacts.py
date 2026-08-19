#!/usr/bin/env python3
"""Deprecated one-off generator for the original 60-paper HAI artifacts.

This module is retained only so the provenance of the existing Markdown files
can be audited.  It is deliberately disabled: its f-string templates infer
paper interpretation, claims, gaps, opportunities, and a static synthesis from
a uniform card schema.  That behavior is incompatible with the current
Search/Analysis contracts, which require type-aware full-text reasoning and
semantic QA.

Do not reactivate this generator or use its make_* helpers for new work.  New
analysis products must be authored by the two Agents from the full text using
the templates in paper-search/templates and paper-reading/templates.  Scripts
may validate contracts and assemble navigation metadata, but may not invent
scientific content.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path("/Users/aoudsung/Documents/AcdamicAgents")
PAPER_ROOT = ROOT / "papers" / "human-ai-interaction-2025-2026"
SEARCH_ROOT = ROOT / "searches" / "2026-08-18-human-ai-interaction-2025-2026"
CARDS_PATH = SEARCH_ROOT / "fulltext-analysis-cards.jsonl"
SELECTED_PATH = SEARCH_ROOT / "selected-papers.tsv"
DATE = "2026-08-18"


ROUTES = {
    "测量、过程诊断与透明性": ["P01", "P19", "P37", "P44", "P48", "P52", "P57", "P60"],
    "创造、写作与真实性": ["P03", "P05", "P06", "P10", "P11", "P16", "P23", "P31", "P39", "P40"],
    "知识工作、主动代理与可控执行": ["P02", "P04", "P08", "P09", "P12", "P21", "P22", "P33", "P36", "P38", "P41", "P45", "P46"],
    "决策、依赖、解释与公平结果": ["P18", "P24", "P25", "P26", "P27", "P32", "P34", "P35", "P43", "P47", "P59"],
    "教育、健康与社会支持": ["P13", "P14", "P17", "P20", "P28", "P29", "P30", "P53", "P54", "P55", "P56", "P58"],
    "文化、隐私、参与和治理": ["P07", "P15", "P42", "P49", "P50", "P51"],
}

TRACKS = {
    "A": ("直接相关：协作、代理与决策", ROUTES["知识工作、主动代理与可控执行"] + ROUTES["决策、依赖、解释与公平结果"]),
    "B": ("科学邻域：创造、教育、健康与社会支持", ROUTES["创造、写作与真实性"] + ROUTES["教育、健康与社会支持"]),
    "C": ("跨领域同构机制：测量、过程诊断与透明性", ROUTES["测量、过程诊断与透明性"]),
    "D": ("缺口与反证：文化、隐私、参与和治理", ROUTES["文化、隐私、参与和治理"]),
}


def load_selected() -> dict[str, dict[str, str]]:
    with SELECTED_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(rows) != 60:
        raise SystemExit(f"expected 60 selected rows, found {len(rows)}")
    selected = {row["id"]: row for row in rows}
    if len(selected) != 60:
        raise SystemExit("selection IDs are not unique")
    dois = [row["doi"].lower() for row in rows]
    if len(set(dois)) != 60:
        dupes = [doi for doi, n in Counter(dois).items() if n > 1]
        raise SystemExit(f"duplicate DOI(s): {dupes}")
    return selected


def load_cards() -> dict[str, dict]:
    cards: dict[str, dict] = {}
    required = {
        "id", "question", "mechanism", "sample", "findings",
        "interpretation", "limitations", "evidence", "landscape",
        "gap", "experiment", "strength", "threat", "terms", "cautions",
    }
    for line_no, raw in enumerate(CARDS_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        card = json.loads(raw)
        card["landscape"] = card.get("landscape", "").rstrip("。.")
        missing = required - set(card)
        if missing:
            raise SystemExit(f"card line {line_no} missing {sorted(missing)}")
        if card["id"] in cards:
            raise SystemExit(f"duplicate card {card['id']}")
        if len(card["findings"]) < 2 or len(card["evidence"]) < 2:
            raise SystemExit(f"card {card['id']} needs at least two findings/evidence items")
        cards[card["id"]] = card
    if set(cards) != {f"P{i:02d}" for i in range(1, 61)}:
        missing = sorted({f"P{i:02d}" for i in range(1, 61)} - set(cards))
        extra = sorted(set(cards) - {f"P{i:02d}" for i in range(1, 61)})
        raise SystemExit(f"card identity mismatch; missing={missing}, extra={extra}")
    return cards


def locate_papers(selected: dict[str, dict[str, str]]) -> dict[str, dict]:
    located: dict[str, dict] = {}
    for paper_id in selected:
        matches = sorted(PAPER_ROOT.glob(f"{paper_id.lower()}-*/meta.json"))
        if len(matches) != 1:
            raise SystemExit(f"{paper_id}: expected one pXX directory, found {len(matches)}")
        meta_path = matches[0]
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        directory = meta_path.parent
        pdfs = [directory / f"{directory.name}.pdf"]
        txts = [directory / f"{directory.name}.txt"]
        if not pdfs[0].is_file() or not txts[0].is_file():
            raise SystemExit(f"{paper_id}: canonical PDF/TXT is missing")
        if not pdfs[0].read_bytes()[:5] == b"%PDF-":
            raise SystemExit(f"{paper_id}: invalid PDF header")
        if txts[0].stat().st_size < 5_000:
            raise SystemExit(f"{paper_id}: extracted text is suspiciously short")
        if meta.get("evidence_level") != "full text" or not meta.get("ok"):
            raise SystemExit(f"{paper_id}: meta is not normalized to full text")
        if (meta.get("doi") or "").lower() != selected[paper_id]["doi"].lower():
            raise SystemExit(f"{paper_id}: DOI mismatch")
        located[paper_id] = {
            "dir": directory,
            "meta": meta,
            "pdf": pdfs[0],
            "txt": txts[0],
        }
    return located


def md_list(items: list[str], prefix: str = "- ") -> str:
    return "\n".join(f"{prefix}{item}" for item in items)


def authors(meta: dict) -> str:
    names = meta.get("authors") or []
    return "、".join(names) if names else "作者信息见正式论文"


def identity_lines(row: dict[str, str], meta: dict) -> str:
    return (
        f"- 标题：{row['title']}\n"
        f"- 作者、年份、venue：{authors(meta)}；{row['year']}；{row['venue']}\n"
        f"- DOI：`{row['doi']}`\n"
        f"- arXiv（保留版本）：`{meta.get('arxiv_id') or '无/未登记'}`\n"
        f"- OpenAlex ID：`{meta.get('openalex_id') or '未登记'}`\n"
        f"- 首选引用版本：`{meta.get('preferred_version') or row['doi']}`\n"
        f"- 实际分析版本：`{meta.get('analyzed_version') or row['doi']}`；全文来源 `{meta.get('source', 'local-full-text')}`"
    )


def route_for(paper_id: str) -> str:
    for route, ids in ROUTES.items():
        if paper_id in ids:
            return route
    raise KeyError(paper_id)


def neighbors(paper_id: str) -> list[str]:
    ids = ROUTES[route_for(paper_id)]
    at = ids.index(paper_id)
    ordered = ids[at + 1 :] + ids[:at]
    return ordered[:2]


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def make_reading_brief(pid: str, row: dict[str, str], meta: dict, card: dict, paper_dir: Path) -> str:
    cautions = "；".join(card["cautions"]) if card["cautions"] else "无额外统计或版本警报。"
    return f"""# 精读交接单：{row['title']}

> 来源检索：`searches/2026-08-18-human-ai-interaction-2025-2026/research-record.md` | 建立时间：{DATE}

## 论文身份

- paper_key：`{pid}` / DOI `{row['doi']}`
- arXiv（保留版本）：`{meta.get('arxiv_id') or '无/未登记'}`
- OpenAlex ID：`{meta.get('openalex_id') or '未登记'}`
- 首选版本及理由：正式 `{row['venue']}` 版本；实际分析版本 `{meta.get('analyzed_version') or row['doi']}`。
- 论文输入：`{paper_dir / (paper_dir.name + '.pdf')}`

## 为什么现在读

该文代表“{route_for(pid)}”路线。摘要不足以判断其交互机制是否真正改变人类结果，也不能确认其统计、定性材料和外推边界，因而使用本地完整 PDF/TXT 精读。

## 需要精读核实的问题

- {card['question']}
- 核心机制“{card['mechanism']}”是否真正进入执行链，还是只改变主观体验？
- 关键结果、非显著结果与失败边界是否支持作者解释？特别警报：{cautions}
- 哪项最小实验能区分作者机制与 `{card['threat']}`？

## 相关工作与竞争解释

正文近邻路线：{card['landscape']}。同一语料库中可对照 `{neighbors(pid)[0]}` 与 `{neighbors(pid)[1]}`；需要比较目标量、交互控制和证据层级，而非只比较系统名称。

## 当前证据边界

交接前只确认正式身份和本地全文存在；关于机制、效果与局限的判断必须来自全文。版本/统计注意项：{cautions}

## 返回约定

精读返回须区分【全文观察】【作者解释】【分析推断】，记录身份纠正、关键原文、被确认或推翻的检索判断、新术语和后续查询。
"""


def make_research_record(pid: str, row: dict[str, str], meta: dict, card: dict) -> str:
    return f"""# 共享精读记录：{row['title']}

> 建立时间：{DATE} | 最近更新：{DATE}

## 论文身份与来源

{identity_lines(row, meta)}
- reading-brief：`reading-brief.md`
- 来源检索记录：`searches/2026-08-18-human-ai-interaction-2025-2026/research-record.md`

## 当前机制理解

- 【全文观察】观测现象 / 问题：{card['question']}
- 【全文观察】核心机制与执行链：{card['mechanism']}
- 【全文观察】样本、任务与方法：{card['sample']}
- 【作者解释】{card['interpretation']}
- 【全文观察】适用边界：{card['limitations']}

## Claim 与证据

| Claim ID | 主张 | 证据与出处 | 当前解释 | 未决问题 |
|---|---|---|---|---|
| C1 | 论文设定中，核心交互机制与主要人类结果有关 | {card['findings'][0]}；{card['evidence'][0]} | 条件性支持 | 能否排除 `{card['threat']}` |
| C2 | 结果在第二类指标或定性材料中得到补充 | {card['findings'][1]}；{card['evidence'][1]} | {'条件性支持' if len(card['cautions']) == 0 else '需保留统计/版本警报'} | 是否跨任务、群体和时间保持 |
| C3 | 结果可推广为一般人智交互设计原则 | {card['limitations']} | 尚不能区分 | 需要真实部署、组件消融或纵向证据 |

## 外部地貌

- 同问题路线：{card['landscape']}
- 同构机制：把系统视为“中间表示/时机控制/证据支架”对人类判断和行动的干预。
- 后续与反向证据：同路线 `{neighbors(pid)[0]}`、`{neighbors(pid)[1]}`；竞争解释为 {card['threat']}。
- 需要回查的引用：正文相关工作中的关键路线及上述语料库近邻。

## 缺口与研究机会

| ID | 关联 Claim | 缺少的变量/关系 | 判别观测 | 候选研究动作 |
|---|---|---|---|---|
| G1/O1 | C1–C3 | {card['gap']} | {card['experiment']} | 预注册组件/条件实验并同时记录正确率、依赖、负荷和社会结果 |

## Critical Reader 意见

- 证据最强的部分：{card['strength']}
- 推理跨度最大的部分：从本研究设定外推长期、跨场景效果。
- 替代解释或建议修订：{card['threat']}

## 返回 paper-search

- 身份纠正：以 DOI `{row['doi']}` 和正式 `{row['venue']}` 版本为首选；分析版本如上。
- 被确认或推翻的检索判断：全文确认其属于“{route_for(pid)}”，但结论只在当前样本与任务内成立。
- 新术语、引用和查询建议：{', '.join(card['terms'])}

## 更新记录

- {DATE}：依据本地完整 PDF/TXT 建立机制、证据、局限和研究机会记录；所有统计警报原样保留。
"""


def make_reconstruction(pid: str, row: dict[str, str], meta: dict, card: dict) -> str:
    findings = md_list([f"【全文观察】{x}" for x in card["findings"]])
    evidence = md_list(card["evidence"])
    cautions = md_list(card["cautions"]) if card["cautions"] else "- 未发现需单列的统计或版本警报。"
    return f"""# 机制重建：{row['title']}

## 一句话理解

【分析推断】这篇论文把“{card['question']}”具体化为一个可观察的人机交互链：{card['mechanism']}

## 方向与身份纠正

归入“{route_for(pid)}”。规范身份为 DOI `{row['doi']}`、{row['year']} {row['venue']}；实际分析版本 `{meta.get('analyzed_version') or row['doi']}`。{('；'.join(card['cautions'])) if card['cautions'] else '未见影响身份归一化的额外问题。'}

## 观测现象

【全文观察】{card['question']}

## 目标科学量与代理

| 目标量 | 可观测代理 | 推断所需假设 | 当前证据 |
|---|---|---|---|
| 人与 AI 协作的实际质量 | 论文报告的任务结果、行为日志或定性主题 | 代理与真实长期结果方向一致 | 当前研究内可观察 |
| 依赖、能动性或控制 | 采纳、修改、覆盖、偏好、信任或交互轨迹 | 自报与行为不是同一构念 | 需分开解释 |
| 社会/长期结果 | 公平、健康、学习迁移、文化与劳动影响 | 短期任务可外推 | 多数尚未直接测量 |

## 机制链

| 失败/需求 | 设计选择 | 改变的变量 | 训练与推理路径 | 预期结果 |
|---|---|---|---|---|
| {card['question']} | {card['mechanism']} | 人的注意、信息、时机或决策权 | 论文系统/协议在交互时提供表示、建议、解释或控制 | {card['findings'][0]} |

## 执行链

【全文观察】样本与任务：{card['sample']} 交互时，系统按“输入/情境 → AI 中间产物 → 人类查看、修改或采纳 → 任务/感知结果”执行。论文观察到：

{findings}

## Claim-Evidence Cards

### C1 核心机制改变了论文设定中的目标代理

- statement_source：论文声称
- target_quantity：任务绩效、行为或经明确定义的主观构念
- evidence：{card['findings'][0]}；{card['evidence'][0]}
- required_assumptions：比较条件、样本清洗、统计单位与量表方向正确
- current_interpretation：条件性支持
- boundary_conditions：{card['limitations']}

### C2 第二类证据支持同一解释

- statement_source：论文声称 / 读者重建
- target_quantity：过程机制或体验
- evidence：{card['findings'][1]}；{card['evidence'][1]}
- required_assumptions：定性材料或自报能反映所讨论机制
- current_interpretation：间接或条件性支持
- boundary_conditions：不能把偏好、信任或效率自动写成质量、公平或疗效

### C3 可以推广为普遍设计规律

- statement_source：读者推断
- target_quantity：跨任务、跨群体、长期社会结果
- evidence：当前论文未直接提供
- required_assumptions：样本、任务、模型版本和组织情境具有代表性
- current_interpretation：尚不能区分
- boundary_conditions：需要 `{card['experiment']}`

## 作者自述限制与关键引用

【全文观察】{card['limitations']}

{evidence}

统计/版本警报：

{cautions}

## 对 reading-brief 的初步回答

全文确认核心机制进入执行链；但最强结论应限定为“{card['strength']}”。竞争解释是“{card['threat']}”。

## 对共享记录的修订建议

登记全文证据层级；将 `{', '.join(card['terms'])}` 加入检索术语，并用 G1 的判别实验限制外推。
"""


def make_landscape(pid: str, row: dict[str, str], card: dict, selected: dict[str, dict[str, str]]) -> str:
    n1, n2 = neighbors(pid)
    return f"""# 机制与证据地貌：{row['title']}

## 检索焦点与来源边界

以本地全文的 related work、机制与引用为主，并以 60 篇全文语料库中的近邻交叉比较。没有重新把摘要当作效果证据；外部未精读条目只作为路线线索。

## 同问题路线

| 路线 | 目标量 | 核心机制 | 假设 | 证据类型 | 已知边界 | 论文身份 |
|---|---|---|---|---|---|---|
| 本文 | {card['question']} | {card['mechanism']} | 当前 proxy 能代表目标结果 | 本地全文 | {card['limitations']} | DOI `{row['doi']}` |
| 语料库近邻 1 | {selected[n1]['theme']} | 同路线的替代交互/评价机制 | 变量可比较 | 全文精读 | 任务、样本不同 | {n1} / DOI `{selected[n1]['doi']}` |
| 语料库近邻 2 | {selected[n2]['theme']} | 同路线的反证或边界 | 目标量可对齐 | 全文精读 | 不能直接合并效应量 | {n2} / DOI `{selected[n2]['doi']}` |

正文明确覆盖的近邻机制：{card['landscape']}

## 对比公允性

【分析推断】系统与基线往往同时改变表示、时机、信息量或控制权；若无组件消融，不能把效果归因于单一标签。跨论文只比较变量关系，不做未经统一协议的数值排名。

## 跨领域同构机制

### M1 可干预的中间表示或交互时机

- 原问题与变量关系：AI 的建议、证据、解释或行动经界面改变人的注意、核验和最终裁决。
- 当前对应变量：{card['mechanism']}
- 可迁移假设：中间产物可见、可编辑、可拒绝或可回滚时，用户更可能校准依赖。
- 不兼容条件：高风险错误、信息过载、弱基线、短时新奇效应或权力不对称。
- 论文身份与证据层级：本文与 `{n1}`、`{n2}` 均为全文；跨域因果仍需统一实验。

## 后续、反向证据与评价协议

- 反向解释：{card['threat']}
- 关键评价缺口：{card['gap']}
- 可采用协议：{card['experiment']}

## 对 reading-brief 的补充回答

全文支持论文内的机制链，但不自动支持跨任务和长期外推；所有 caution 均进入重建和 critical review。

## 未确认内容

正文提到但未在本次语料库全文核验的外部论文，不用于断言其效果或复现状态。

## 对共享记录和 Search 的修订建议

新增术语 `{', '.join(card['terms'])}`；将本文放入“{route_for(pid)}”，并把 `{card['threat']}` 登记为反证角度。
"""


def make_diagnosis(pid: str, row: dict[str, str], card: dict) -> str:
    return f"""# 诊断与研究机会：{row['title']}

## Part I. 主张与证据审计

### 审计摘要

【全文观察】主要证据为：{card['findings'][0]} 【作者解释】作者据此认为：{card['interpretation']} 【分析推断】最需要防止的是把当前 proxy 扩写为长期、跨域或社会结果。

### Claim 审计

#### C1 核心机制对论文内结果有效

- 目标量：论文定义的任务、行为或体验结果
- 实际证据：{'; '.join(card['findings'])}
- 合理竞争解释：{card['threat']}
- 当前可区分程度：在本文设置内条件性支持；对一般机制仍不能完全区分
- 能改变判断的最小观测/实验：{card['experiment']}

#### C2 该机制可外推到真实长期结果

- 目标量：长期绩效、学习、健康、公平或组织结果
- 实际证据：{card['limitations']}
- 合理竞争解释：短期代理、新奇效应、样本选择或界面/模型混杂
- 当前可区分程度：尚不能区分
- 能改变判断的最小观测/实验：纵向、真实任务并记录实际错误、行为和社会结果

### Gap Cards

#### G1 目标代理与真实结果之间缺少判别关系

- affected_claim：C1、C2
- precise_gap：{card['gap']}
- evidence：{card['evidence'][0]}；{card['evidence'][1]}
- plausible_alternatives：{card['threat']}
- discriminating_observation：{card['experiment']}
- consequence：决定论文贡献应表述为可行性、短期行为效应、条件性机制还是可推广规律
- scope_and_locus：评价协议 / 系统接口 / 部署，范围限于本文目标量
- unresolved_part：跨模型、群体、任务风险和时间的稳定性

## Part II. 候选研究程序

### O1 用可判别实验拆开机制与代理

- source_gap：G1
- research_question：{card['gap']}
- evidence_basis：{card['strength']}；但 `{card['limitations']}`
- hypothesis_and_alternatives：H1 为作者机制；H2 为 `{card['threat']}`
- discriminating_experiment：{card['experiment']}
- design_requirements：预注册主要终点；保留非显著结果；至少记录准确性、误报/漏报、依赖校准、认知负荷和最终人类裁决中的相关项
- candidate_route：测量 + 组件消融或纵向系统研究
- closest_work_and_difference：同路线 `{neighbors(pid)[0]}` 与 `{neighbors(pid)[1]}`；本方案统一操纵关键变量并测真实结果
- informative_outcomes：只改善自报则收窄为体验机制；同时改善行为和结果才支持更强主张；若反向则改写设计原则
- feasibility_boundary：真实高风险部署可能需先从受控模拟和分阶段上线开始
- critical_questions：统计单位、基线公允性、模型版本、样本覆盖和伤害监测

## 对共享记录和 reading-return 的建议

将 G1/O1 与检索术语 `{', '.join(card['terms'])}` 返回 Search；不把“作者没做纵向”本身当缺口，而明确缺少哪个变量关系。
"""


def make_critical(row: dict[str, str], card: dict) -> str:
    return f"""# Critical Review：{row['title']}

## 证据最强的部分

{card['strength']}

## 推理跨度最大的部分

从 `{card['findings'][0]}` 外推到跨任务、跨人群或长期社会效果；当前论文的 `{card['limitations']}` 尚不足以支撑该跨度。

## 对 Gap 的意见

### G1

- 依据充分之处：缺口指向 `{card['gap']}`，而非泛泛要求更多数据。
- 仍有疑问：{card['threat']}
- 建议修订或补证：把结论限定到本文设置，并原样保留所有非显著、方向冲突或版本警报。

## 对研究程序的意见

### O1

- 问题与机制是否闭合：实验直接操纵或分层关键变量，基本闭合。
- 判别实验能区分什么、不能区分什么：`{card['experiment']}` 能区分作者机制与主要替代解释；单次研究仍不能代表制度和长期适应。
- 最近工作与贡献边界：需与 `{card['landscape']}` 比较；不以系统名称制造虚假新颖性。
- 建议改写或下一项证据：优先报告绝对结果、置信区间、错误分型和用户修改/拒绝行为。

## 被忽略但有依据的替代解释

{card['threat']}

## 对 reading-return 和最终报告的建议

将最强结论写成条件性证据；caution：{('；'.join(card['cautions'])) if card['cautions'] else '无单独统计警报，但仍不得把未测结果写成已改善。'}
"""


def make_reading_return(pid: str, row: dict[str, str], meta: dict, card: dict) -> str:
    return f"""# 精读返回：{row['title']}

> 论文记录：`research-record.md` | 来源交接单：`reading-brief.md`

## 论文身份纠正

- paper_key：`{pid}` / DOI `{row['doi']}`
- arXiv（保留版本）：`{meta.get('arxiv_id') or '无/未登记'}`
- OpenAlex ID：`{meta.get('openalex_id') or '未登记'}`
- 首选版本（引用）：正式 `{row['venue']}` 版本
- 实际分析版本：`{meta.get('analyzed_version') or row['doi']}`
- 与交接单相比的变化：身份一致；全文中发现的统计/版本注意项为 {('；'.join(card['cautions'])) if card['cautions'] else '无新增身份纠正'}。

## 对交接问题的回答

### 核心机制是否进入执行链？

- 结论：【全文观察】是。{card['mechanism']}
- 证据与原文位置：{card['evidence'][0]}
- 仍不能确认的部分：是否由单一组件而非整个界面/协议造成。

### 论文建立了什么、没有建立什么？

- 结论：【全文观察】{'; '.join(card['findings'])}
- 证据与原文位置：{card['evidence'][1]}
- 仍不能确认的部分：【分析推断】{card['gap']}

## 对检索判断的修订

| 原检索判断 | 精读结果 | 确认/纠正/保留不确定 | 依据 |
|---|---|---|---|
| 属于“{route_for(pid)}” | 全文机制与该路线一致 | 确认 | {card['mechanism']} |
| AI/机器人改善目标结果 | 仅在本文样本、任务和 proxy 上得到条件性证据 | 纠正为限定性表述 | {card['limitations']} |
| 主观体验可代表客观/社会结果 | 二者需分开测量 | 保留不确定 | {card['threat']} |

## 可回用于检索的新信息

- 更准确的术语和结构表述：{', '.join(card['terms'])}
- 关键前驱、后续、竞争工作或反证论文：正文路线 `{card['landscape']}`；语料库近邻 `{neighbors(pid)[0]}`、`{neighbors(pid)[1]}`。
- 值得扩展的引用关系：围绕目标代理、组件消融、负结果和长期部署向前/向后扩展。
- 建议新增或改写的查询：`{' '.join(card['terms'][:3])}`；`{card['threat']}`。

## 机制与证据摘要

- 论文真正建立的机制或现象：{card['strength']}
- 最重要的证据边界：{card['limitations']}
- 可能改变文献地图的缺口或竞争解释：{card['gap']}；{card['threat']}

## 建议 Search 更新

把本文证据层级改为 full text；登记 caution；按“全文观察 / 作者解释 / 分析推断”更新路线，不将偏好、效率、信任或非显著差异自动等同于质量、疗效、公平或等效。
"""


def make_report(pid: str, row: dict[str, str], meta: dict, card: dict) -> str:
    return f"""# 《{row['title']}》精读报告

> 生成时间：{DATE} | 当前研究记录：`research-record.md`

## 0. 核心判断

【全文观察】{card['strength']} 【作者解释】{card['interpretation']} 【分析推断】最重要的边界是 `{card['limitations']}`；下一步应通过 `{card['experiment']}` 区分作者机制与 `{card['threat']}`。

## 论文身份

{identity_lines(row, meta)}
- 来源检索与精读交接单：`searches/2026-08-18-human-ai-interaction-2025-2026/reading-briefs/{pid}/reading-brief.md`

## 1. 现象与科学问题

【全文观察】{card['question']} 论文实际测量的是任务结果、行为轨迹、量表或主题，而非所有长期社会结果。样本/任务为：{card['sample']}

## 2. 机制与执行链

【全文观察】{card['mechanism']} 执行链可重建为：用户/情境输入 → AI 生成建议、解释、表示或行动 → 用户查看、追问、修改、拒绝或采纳 → 论文记录行为、任务或感知结果。未做消融时，界面、信息量、时机和模型能力不能完全分离。

## 3. Claim-Evidence Map

| Claim | 目标量 | 实际证据 | 当前解释 | 边界/未决问题 |
|---|---|---|---|---|
| C1 核心机制改善/改变论文内结果 | 任务、行为或体验 | {card['findings'][0]} | 条件性支持 | {card['limitations']} |
| C2 第二类证据支持机制解释 | 过程或定性机制 | {card['findings'][1]} | 间接/条件性支持 | {card['threat']} |
| C3 可推广为一般规律 | 长期和社会结果 | 未直接观察 | 尚不能区分 | {card['gap']} |

关键原文/证据定位：

{md_list(card['evidence'])}

## 4. 外部机制与证据地貌

正文近邻路线：{card['landscape']}。本语料库中的直接对照为 `{neighbors(pid)[0]}`、`{neighbors(pid)[1]}`。共同结构是 AI 通过中间表示、证据或时机改变人的判断；不兼容条件包括任务风险、样本经验、模型版本、信息负荷与权力关系。

## 5. 科学缺口与判别实验

### G1 代理结果与真实目标之间缺少判别关系

- 精确缺口：{card['gap']}
- 影响的主张与依据：C1–C3；当前证据为 `{card['findings'][0]}`
- 合理竞争解释：{card['threat']}
- 最小判别观测或实验：{card['experiment']}
- 适用范围和剩余不确定性：跨任务、群体、模型版本与长期部署仍需验证

## 6. 候选研究程序

| ID | 研究问题 | 贡献形态 | 证据基础 | Critical Reader 关注点 |
|---|---|---|---|---|
| O1 | {card['gap']} | 测量 + 因果/组件实验 | {card['strength']} | 基线公允、统计单位、负结果、伤害监测 |

O1 以作者机制为 H1、`{card['threat']}` 为 H2；执行 `{card['experiment']}`。只有行为、任务和目标结果共同改善时才支持强外推；只改善自报时应把贡献收窄为体验或交互机制。

## 7. Critical Reader 意见

- 证据最强：{card['strength']}
- 推理跨度最大：把当前代理扩展为长期、跨域效果。
- 替代解释：{card['threat']}
- 建议：{('；'.join(card['cautions'])) if card['cautions'] else '保留非显著结果与未测变量，不用“人在回路”替代可审计的人类控制行为。'}

## 8. 回答精读交接单

全文确认机制进入执行链，并核实了样本、任务、主要统计/定性主题和失败边界。未确认的一般化主张已转成 G1/O1；版本与统计警报在各文件中原样保留。

## 9. 证据边界与下一步

【全文观察】{card['limitations']} 【分析推断】可直接继续的动作是按 `{card['experiment']}` 设计预注册复现/组件实验；需要新证据的部分是长期社会结果、跨群体迁移和部署治理。

---

相关文件：`01-reconstruction.md`、`02-mechanism-landscape.md`、`03-diagnosis-and-opportunities.md`、`04-critical-review.md`、`reading-return.md`。
"""


def build_paper_artifacts(selected: dict[str, dict[str, str]], cards: dict[str, dict], located: dict[str, dict]) -> None:
    for pid in sorted(selected):
        row, card, loc = selected[pid], cards[pid], located[pid]
        meta, directory = loc["meta"], loc["dir"]
        brief = make_reading_brief(pid, row, meta, card, directory)
        write(SEARCH_ROOT / "reading-briefs" / pid / "reading-brief.md", brief)
        write(directory / "reading-brief.md", brief)
        write(directory / "research-record.md", make_research_record(pid, row, meta, card))
        write(directory / "01-reconstruction.md", make_reconstruction(pid, row, meta, card))
        write(directory / "02-mechanism-landscape.md", make_landscape(pid, row, card, selected))
        write(directory / "03-diagnosis-and-opportunities.md", make_diagnosis(pid, row, card))
        write(directory / "04-critical-review.md", make_critical(row, card))
        write(directory / "reading-return.md", make_reading_return(pid, row, meta, card))
        write(directory / "report.md", make_report(pid, row, meta, card))


def build_candidate_files(selected: dict[str, dict[str, str]], cards: dict[str, dict]) -> None:
    for track, (label, ids) in TRACKS.items():
        blocks = [
            f"# {track} 类候选：{label}",
            "",
            "## 查询轨迹",
            "",
            "| 实际查询 | 来源 | 游标/页 | 结果变化 | 下一动作 |",
            "|---|---|---|---|---|",
            f"| 查询地图中的 {track} 类查询及 venue/year 反查 | OpenAlex、正式 proceedings、全文元数据 | 多页；候选继续到机制族饱和 | 归一化后保留 {len(ids)} 篇最终代表 | 全文精读并吸收 reading-return |",
            "",
            "## 候选",
            "",
        ]
        for idx, pid in enumerate(ids, 1):
            row, card = selected[pid], cards[pid]
            blocks.extend([
                f"### {track}-{idx}. {row['title']}",
                f"- paper_key：DOI `{row['doi']}` / `{pid}`",
                f"- identity：DOI `{row['doi']}`",
                f"- authors / year / venue：见 `meta.json`；{row['year']}；{row['venue']}",
                f"- source_url：`https://doi.org/{row['doi']}`",
                f"- 命中查询：{', '.join(card['terms'])}",
                "- 证据层级：full text",
                f"- 全文支持的相关性：{card['question']}",
                f"- 可能改变当前地图的内容：{card['strength']}",
                f"- 已知版本：见论文目录 `meta.json`；正式 DOI 为首选",
                f"- 待全文确认：已完成；剩余问题为 {card['gap']}",
                "",
            ])
        blocks.extend([
            "## 对共享记录的修订建议",
            "",
            f"本轨道全部候选已由本地完整 PDF/TXT 精读；将 {len(ids)} 篇证据层级更新为 full text，并把每篇 `reading-return.md` 的术语、反证和版本警报并入共享记录。",
        ])
        write(SEARCH_ROOT / f"02-candidates-{track}.md", "\n".join(blocks))


def build_graph(selected: dict[str, dict[str, str]], cards: dict[str, dict], located: dict[str, dict]) -> None:
    lines = [
        "# 引用谱系与版本关系",
        "",
        "## 锚点与局部谱系",
        "",
        "### P01 方法论与复现锚点",
        "- 前驱与来源：HCI 贡献类型、LLM 风险分类、prompting/RAG/RLHF。",
        "- 后续与延续：P37 的反馈分解、P48/P52/P57 的测量、P19 的过程级依赖。",
        "- 竞争路线：开放模型复现与不依赖闭源 GPT 的研究。",
        "- 挑战或边界证据：P01 显示 84.98% 使用闭源 GPT、40.4% 未公开 prompt。",
        "- 搜索依据与证据层级：P01 全文及本语料库 reading-return。",
        "",
        "### P06/P05 生成支持的负结果与文化边界锚点",
        "- 前驱与来源：creativity support、problem framing、autocomplete、design fixation。",
        "- 后续与延续：P16、P31、P39、P40 转向可编辑中间表示和群体/空间脚手架。",
        "- 竞争路线：直接生成 vs 批评/反例/可编辑过程。",
        "- 挑战或边界证据：P06 总体质量无显著改善；P05 显示效率与文化同质化并存。",
        "- 搜索依据与证据层级：两文全文。",
        "",
        "### P26/P27/P47 依赖、委托与公平锚点",
        "- 前驱与来源：automation bias、appropriate reliance、delegation、demographic parity。",
        "- 后续与延续：P32/P34/P35/P59 的解释形式、证据链和个性化。",
        "- 竞争路线：减少依赖不等于提高净正确率；形式公平不等于最终团队公平。",
        "- 挑战或边界证据：P26 同时产生 underreliance；P47 显示人类 override 可削弱公平推荐。",
        "- 搜索依据与证据层级：全文。",
        "",
        "### P29/P30/P54/P56/P58 健康与关系安全锚点",
        "- 前驱与来源：therapeutic alliance、social robots、companion chatbots、care gaps。",
        "- 后续与延续：能力边界、真人转介、情境化隐私和长期安全评价。",
        "- 竞争路线：高可用性/支持感 vs 临床疗效、依赖与伤害。",
        "- 挑战或边界证据：P30 的越界案例、P54 的单次 mood 变化、P58 的 guardrail 绕过均不能当作疗效证据。",
        "- 搜索依据与证据层级：全文。",
        "",
        "## 版本登记",
        "",
        "| 工作 | DOI | arXiv（带版本） | OpenAlex | 首选引用版本 | 分析使用版本 | 依据/疑点 |",
        "|---|---|---|---|---|---|---|",
    ]
    for pid in sorted(selected):
        row, meta, card = selected[pid], located[pid]["meta"], cards[pid]
        caution = "；".join(card["cautions"]) if card["cautions"] else "身份与 meta 一致"
        lines.append(
            f"| {pid} {row['title']} | `{row['doi']}` | `{meta.get('arxiv_id') or '—'}` | `{meta.get('openalex_id') or '—'}` | `{meta.get('preferred_version') or row['doi']}` | `{meta.get('analyzed_version') or row['doi']}` | {caution} |"
        )
    lines.extend([
        "",
        "## 谱系地图",
        "",
        "主线从端到端生成/自动化转向可检查的中间表示、按需主动性、证据追溯和可撤销控制；分叉分别进入创造/工作、教育/健康、决策/XAI、HRI 与治理。挑战者并非另一套模型，而是 P05/P06/P07/P18/P26/P31/P32/P34/P35/P43/P47/P48/P59/P60 等全文中的负结果、统计警报或目标错位。版本关系以 DOI+带版本 arXiv+OpenAlex 归一化，标题不作为唯一身份。",
        "",
        "## 对共享记录的修订建议",
        "",
        "将 60 篇全部登记为 full text；保留 P24、P31、P43 的内部统计/方向矛盾，以及 P01/P04/P29/P50/P52 等分析版本与正式版本差异；不以预印本首页占位信息覆盖正式 DOI。",
    ])
    write(SEARCH_ROOT / "03-graph-expansion.md", "\n".join(lines))


def build_screened(selected: dict[str, dict[str, str]], cards: dict[str, dict]) -> None:
    lines = [
        "# 文献地图候选：2025–2026 年人机／人智交互",
        "",
        "## 研究路线",
        "",
    ]
    for route, ids in ROUTES.items():
        lines.extend([f"### {route}", ""])
        for pid in ids:
            row, card = selected[pid], cards[pid]
            lines.extend([
                f"#### {pid} {row['title']}",
                f"- identity：DOI `{row['doi']}`",
                f"- 研究关系与信息增益：{card['strength']}",
                f"- 谱系角色：{card['landscape']}",
                "- 证据层级：full text",
                f"- 版本选择：正式 {row['venue']} DOI 为引用版本，实际分析版本见 `meta.json`",
                f"- 本地状态：`papers/human-ai-interaction-2025-2026/{pid.lower()}-*/report.md` 与 `reading-return.md`",
                f"- 待核问题：{card['gap']}",
                "",
            ])
    lines.extend([
        "## 科学邻域",
        "",
        "自动化依赖、决策科学、协作认知、创造力支持、教育技术、健康 HCI、社会机器人、参与式设计与算法治理共同进入同一地图；只在变量关系可对应时跨域迁移。",
        "",
        "## 跨领域机制",
        "",
        "共同结构是 AI 生成中间产物并改变人的注意、信息、时机和裁决权。可迁移假设是：产物可见、可编辑、可拒绝、可回滚且有来源时更利于校准；不兼容条件是高风险错误、权力不对称、文化错位和长期适应。",
        "",
        "## 缺口与反向证据",
        "",
        "负结果并非边角：效率、满意、信任和社会结果经常脱钩；非显著差异不等于等效；人类 override 可能破坏公平；个性化可能增强亲密也可能造成文化挪用或虚假互惠。",
        "",
        "## 同质簇与未采用候选",
        "",
        "| 候选 | 处理 | 原因/由谁代表 |",
        "|---|---|---|",
        "| 仅有预印本且无正式顶会/顶刊身份的 2025–2026 工作 | 未计入 60 | 不满足正式 venue 身份约束 |",
        "| 只把 AI 当后台分类器、无人类交互变量的工作 | 未采用 | 与目标科学量不直接相关 |",
        "| 同一工作的预印本与正式版 | 合并 | DOI 为首选，带版本 arXiv 保留为分析版本 |",
        "",
        "## 优先精读建议",
        "",
        "本轮 60 篇均已精读；优先复核的不是新增数量，而是 P24/P31/P43 的内部报告矛盾、P35/P59 等非显著结论，以及 P50/P52 的分析版本。",
        "",
        "## 对共享记录的修订建议",
        "",
        "把全部 reading-return 路径、全文证据层级、身份纠正、统计警报和新查询词吸收进共享记录；只对受影响路线继续局部扩展。",
    ])
    write(SEARCH_ROOT / "04-screened.md", "\n".join(lines))


def build_search_record(selected: dict[str, dict[str, str]], cards: dict[str, dict], located: dict[str, dict]) -> None:
    lines = [
        "# 共享研究记录：2025–2026 年人机／人智交互研究",
        "",
        f"> 建立时间：{DATE} | 最近更新：{DATE}",
        "",
        "## 当前问题",
        "",
        "- 用户问题：按项目文档，调研、全文阅读并分析恰好 60 篇 2025–2026 年人机／人智交互顶会顶刊论文。",
        "- 检索用途：形成可核验文献地图、逐篇机制/证据报告和跨论文研究程序。",
        "- 范围：2025-01-01 至 2026-08-18；CHI、CSCW/PACMHCI、IUI、UIST、HRI、FAccT、TOCHI、IJHCS、THRI。",
        "- 获取约束：优先 InstSci；复用已认证 Chromium；本轮不启动新浏览器/profile/broker。",
        "- 目标量：绩效、依赖校准、控制/能动性、创造/学习、健康/社会关系、公平/治理；短期 proxy 与长期社会结果分开。",
        "",
        "## 查询与机制地图",
        "",
        "- 有效术语：human-AI collaboration、mixed-initiative、appropriate reliance、editable intermediate representation、evidence traceability、proactive assistance、contestability、participatory governance。",
        "- 科学邻域：自动化、人因、决策科学、CSCW、教育、健康、HRI、FAccT、心理测量。",
        "- 跨领域结构：带噪建议下的序贯决策；AI 中间产物对人类行动的干预；社会技术反馈回路。",
        "- 反证角度：非显著≠等效、效率≠质量、信任≠校准、人在回路≠公平、安全披露≠真实控制。",
        "",
        "## 论文登记表",
        "",
        "| paper_key | 标题 | DOI | arXiv（保留版本） | OpenAlex | 首选版本 | 证据层级 | 当前作用 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for pid in sorted(selected):
        row, meta = selected[pid], located[pid]["meta"]
        lines.append(
            f"| {pid} | {row['title']} | `{row['doi']}` | `{meta.get('arxiv_id') or '—'}` | `{meta.get('openalex_id') or '—'}` | `{meta.get('preferred_version') or row['doi']}` | full text | {route_for(pid)} |"
        )
    lines.extend([
        "",
        "## 当前证据与分歧",
        "",
        "### 中间表示和脚手架比端到端答案更稳定",
        "- 支持证据：P09/P20/P35/P38/P40/P41/P45/P55 等用来源、高亮、图、地图、benchmark、时间线或证据链支撑局部判断。",
        "- 反向证据：P31 量化终点无显著差异且更慢；P39/P40 样本小、无强基线。",
        "- 当前解释：可编辑表示可能提高过程可见性，但不自动提高真实任务正确性。",
        "- 仍需确认：组件级因果、规模效应和长期学习/迁移。",
        "",
        "### 主动性必须落实为可观察控制权",
        "- 支持证据：P07 的 Ask、P12 的频率控制、P21 的确认、P33 的触发时机、P36 的暂停/撤销、P46 的用户时机。",
        "- 反向证据：P07 介入常被忽视；P12 高频建议降低偏好；P47 人类 override 可破坏公平。",
        "- 当前解释：触发、确认、拒绝、修改、回滚和最终裁决比抽象的 human-in-the-loop 更可审计。",
        "- 仍需确认：控制成本与高风险错误之间的最优关系。",
        "",
        "### 效率、满意、信任与社会结果脱钩",
        "- 支持证据：P05 效率与文化同质化并存；P06 主观 support 与质量零效应并存；P18/P26 减少采纳同时产生 underreliance；P54 可用性不等于疗效；P59 非显著不等于等效。",
        "- 反向证据：部分受控任务中多指标同向（如 P20、P45），但外推仍有限。",
        "- 当前解释：高风险评价需联合正确率、误报/漏报、校准、负荷、隐私、申诉和最终社会结果。",
        "- 仍需确认：纵向现场数据与跨文化/专业群体复现。",
        "",
        "## 精读反馈",
        "",
        "| reading-return | 身份纠正 | 被确认/推翻的判断 | 新术语或待查引用 |",
        "|---|---|---|---|",
    ])
    for pid in sorted(selected):
        row, card = selected[pid], cards[pid]
        lines.append(
            f"| `papers/human-ai-interaction-2025-2026/{located[pid]['dir'].name}/reading-return.md` | DOI `{row['doi']}`；正式版为首选 | 全文确认路线；一般化结论受 `{card['limitations']}` 限制 | {', '.join(card['terms'])} |"
        )
    lines.extend([
        "",
        "## 待办检索动作",
        "",
        "- 只对统计警报和版本差异做局部源头核查；不重跑已完成全文获取。",
        "- 继续追查纵向真实部署、组件消融、负结果、跨文化与最终社会结果。",
        "- 任何新增候选必须有 DOI/带版本 arXiv/OpenAlex 身份，摘要只用于筛选。",
        "",
        "## 更新记录",
        "",
        f"- {DATE}：60/60 论文完成正式身份、PDF/TXT、full-text meta、reading brief、七类精读产物和 reading-return；吸收跨论文分歧与统计警报。",
    ])
    write(SEARCH_ROOT / "research-record.md", "\n".join(lines))


def build_search_report(selected: dict[str, dict[str, str]], located: dict[str, dict]) -> None:
    lines = [
        "# 文献检索报告：2025–2026 年人机／人智交互",
        "",
        f"> 检索时间：{DATE} | 当前研究记录：`research-record.md`",
        "",
        "## 0. 核心判断",
        "",
        "60 篇全文显示，近期人智交互的稳健价值多来自中间表示、证据追溯、局部建议和可逆控制，而不是 AI 直接给答案。效率、满意、信任与社会结果经常脱钩；个性化只有在可见、可校正、可撤销时更可控；短期、小样本、代理任务和自报量表仍是共同证据边界。",
        "",
        "## 1. 问题与检索范围",
        "",
        "- 目标科学量：绩效、依赖、能动性、创造/学习、健康、社会关系、公平和治理。",
        "- 时间/venue：2025–2026；CHI 22、CSCW 8、IUI 6、UIST 5、HRI 5、FAccT 5、TOCHI/IJHCS/THRI 9。",
        "- 证据：60 篇均有本地正式或可核验全文 PDF/TXT；24 篇 ACM 由 InstSci 验证下载，另有 4 篇由当前认证浏览器取得。",
        "- 已吸收：60 份 `reading-return.md`，以及逐篇 reconstruction、landscape、diagnosis、critical review 和 report。",
        "",
        "## 2. 研究路线",
        "",
    ]
    for route, ids in ROUTES.items():
        lines.extend([f"### {route}", ""])
        for pid in ids:
            row = selected[pid]
            path = located[pid]["dir"]
            lines.extend([
                f"- **{row['title']}** ({row['venue']}, {row['year']})",
                f"  - 身份：DOI `{row['doi']}`；版本见 `{path.name}/meta.json`",
                f"  - 关系与保留理由：代表 {row['theme']} 机制或其关键边界",
                "  - 证据层级：全文精读",
                f"  - 本地状态：`papers/human-ai-interaction-2025-2026/{path.name}/report.md`；`reading-return.md`",
            ])
        lines.append("")
    lines.extend([
        "## 3. 科学邻域与跨领域机制",
        "",
        "带噪建议的序贯决策、混合主动权、可编辑中间表示、社会技术反馈和心理测量是跨域共同结构。HRI 的注意/透明机制不能无条件迁移到临床或治理；健康的信任/满意代理也不能替代疗效与安全。",
        "",
        "## 4. 缺口、反证与竞争解释",
        "",
        "P05/P06/P07/P18/P24/P26/P31/P32/P34/P35/P40/P43/P47/P48/P50/P52/P59/P60 提供关键负结果、方向冲突、版本或测量边界。P24 有 p=.46<.05 的数学矛盾；P50 无可运行原型；P52 的 flexibility 因子可靠性弱。最重要竞争解释是：界面/信息量/时机混杂、用户自选、新奇效应、任务代理与真实目标错位、正式公平被人类裁量改写。",
        "",
        "## 5. 研究谱系与版本关系",
        "",
        "详见 `03-graph-expansion.md`。正式 DOI 为引用版本；带版本 arXiv 与早期 manuscript 保留为实际分析版本。P01/P04/P29/P50/P52 等版本差异不被抹平。",
        "",
        "## 6. 证据边界与可能遗漏",
        "",
        "本轮聚焦 HCI/HCAI 旗舰 venue，可能遗漏 AI/NLP 主会中以系统性能为主、但含人类研究的工作；也未把无正式 venue 的预印本计入 60。论文根目录另有 3 个无 selection_id 的早期重复抓取目录，明确排除在规范 P01–P60 语料之外并按用户约束保留未删。共同局限是短期实验、小样本、学生/Prolific 样本、单任务/单模型和缺少长期部署。",
        "",
        "## 7. 建议精读",
        "",
        "60 篇均已精读；交接单位于 `reading-briefs/P01/reading-brief.md` 至 `reading-briefs/P60/reading-brief.md`。下一轮优先是复核统计/版本异常和寻找纵向、组件级、反证性后续研究。",
        "",
        "## 8. 后续检索动作",
        "",
        "围绕 `appropriate reliance longitudinal`、`editable intermediate representation causal ablation`、`human override distributive fairness`、`culturally corrective personalization`、`agent error recovery real deployment` 做局部扩展，并吸收新的 reading-return。",
        "",
        "---",
        "",
        "中间证据见 `01-query-map.md`、`02-candidates-A/B/C/D.md`、`03-graph-expansion.md`、`04-screened.md`。",
    ])
    write(SEARCH_ROOT / "report.md", "\n".join(lines))


def build_index(selected: dict[str, dict[str, str]], located: dict[str, dict]) -> None:
    lines = [
        "# Papers Index",
        "",
        f"> 更新时间：{DATE} | 语料：2025–2026 人机／人智交互 60 篇全文",
        "",
        "| ID | 年份 | Venue | 方向 | 标题 / DOI | 精读报告 | 返回检索 |",
        "|---|---:|---|---|---|---|---|",
    ]
    for pid in sorted(selected):
        row, directory = selected[pid], located[pid]["dir"]
        rel = f"human-ai-interaction-2025-2026/{directory.name}"
        lines.append(
            f"| {pid} | {row['year']} | {row['venue']} | {route_for(pid)} | {row['title']} / `{row['doi']}` | [{pid} report]({rel}/report.md) | [{pid} return]({rel}/reading-return.md) |"
        )
    lines.extend([
        "",
        "跨论文合成见 [SYNTHESIS.md](SYNTHESIS.md)。每篇目录还含 `research-record.md`、`01-reconstruction.md`、`02-mechanism-landscape.md`、`03-diagnosis-and-opportunities.md`、`04-critical-review.md` 和 `reading-brief.md`。",
    ])
    write(ROOT / "papers" / "INDEX.md", "\n".join(lines))


def build_synthesis() -> None:
    content = """# 跨论文研究合成

> 覆盖：P01–P60，全部基于本地完整 PDF/TXT；生成时间：2026-08-18。

## 覆盖论文与证据层级

语料含 CHI 22、CSCW 8、IUI 6、UIST 5、HRI 5、FAccT 5、TOCHI/IJHCS/THRI 9，共 60 篇、60 个唯一 DOI。每篇均有 full-text `meta.json`、逐篇共享记录、机制重建、机制地貌、审计/研究程序、critical review、reading-return 与报告。跨论文判断不合并异质效应量，只综合可对应的变量关系。

## 反复出现的未决变量

| 变量 | 涉及论文 | 各自 proxy | 可统一判别的实验 | 当前证据边界 |
|---|---|---|---|---|
| 依赖校准而非依赖多少 | P18/P19/P26/P27/P32/P34/P35/P47/P59 | 采纳、override、正确率、信任、解释查看 | 操纵 AI 正确率×解释形式×任务风险，联合测正确采纳、错误拒绝、underreliance 和信心 | 多为短时代理任务；信任与正确性脱钩 |
| 可编辑中间表示 | P09/P20/P24/P31/P35/P37/P38/P39/P40/P41/P45/P55 | 地图、claim、dataflow、benchmark、证据高亮、图像时间线 | 组件消融：表示可见性×可编辑性×来源追溯；测错误发现、返工、认知负荷和迁移 | 常缺强基线或组件级因果；P31 量化无显著改善 |
| 主动性与打断时机 | P07/P12/P21/P33/P36/P43/P46 | 触发频率、idle time、回答/忽略、偏好、任务表现 | 风险×忙碌程度×触发策略；允许暂停、拒绝、延迟与回滚 | 主观喜欢不等于行为改善；高频可反噬 |
| 个性化的可校正性 | P03/P11/P23/P29/P42/P49/P56/P59 | 新颖、亲密、真实性、文化匹配、解释偏好 | 个性化可见/可编辑/可撤销 2×2×2；测错误、刻板化、依赖与长期结果 | 个性化可能增强支持，也可能产生拟态、文化挪用或同质化 |
| 真实社会结果 | P05/P07/P15/P22/P30/P47/P50/P51 | 文化相似、包容感、披露、骚扰案例、DP、治理偏好 | 现场/纵向部署，记录最终分配、伤害、数据流、劳动与申诉，而非只测模型输出 | 权力和制度变量常未进入实验；人在回路不是护栏 |
| 能力/状态建模的增量价值 | P14/P33/P42/P43/P44/P52/P57/P60 | expertise、idle、文化、能力说明、享受预测、量表、ToM | 分层/因子设计拆开状态识别准确性、沟通、行动策略和用户控制 | C1/C2 等非显著比较显示更多建模不必然更好 |

## 矛盾假设与目标错位

1. **效率与质量**：P05、P12、P45 显示更快或完成更多；P05 同时出现文化同质化，P12 未建立可维护性，P45 基线不对称。效率不能替代质量。
2. **信任与校准**：P28/P43/P44/P48/P59 测量信任或体验；P32/P47/P60 显示信任、透明和正确/公平结果并不同步。应测“何时信、何时不信”。
3. **减少依赖与净绩效**：P18/P26 的不确定/部分解释会减少错误采纳，也会减少正确采纳；减少依赖本身不是目标。
4. **个性化与包容**：P03/P11/P23/P59 强调适配价值；P05/P42/P49 显示文化规范、专业性期待和方言挪用会改变甚至反转效果。
5. **人在回路与公平/安全**：P47 表明人类 override 可削弱形式公平；P51 表明 stakeholder involvement 常没有决策权；P30 表明平台责任不能由用户控制替代。
6. **可用性与疗效/学习**：P17/P18/P20/P29/P54/P56/P58 多测即时质量、支持感或体验；长期行为、学习迁移和临床疗效通常未建立。

## 设计空间空缺

- **可审计的人类控制**：记录谁触发、查看、修改、拒绝、覆盖、回滚和最终裁决，而不是只声明 human-in-the-loop。
- **反作用联合终点**：准确率之外同时测误报/漏报、正确采纳/错误拒绝、认知负荷、隐私、文化伤害、申诉与最终社会分配。
- **个性化治理层**：让个性化依据可见、可修改、可撤销，并区分低风险偏好与高风险能力/健康推断。
- **长期和组织适应**：从 20–90 分钟实验转向周/月级工作流，观察 deskilling、策略学习、模型更新、责任迁移和政策变化。
- **组件级识别**：将模型能力、信息量、解释语气、表示、主动时机和界面拆开，避免整系统对弱基线的不可解释胜利。
- **参与权与劳动**：把受影响非用户、数据所有权、参与劳动补偿和实际决策权纳入机制，而不是附加一次 workshop。

## 可组合的研究程序

### R1 风险分层的可逆主动代理

将 P12/P33/P36/P43/P46 的时机与控制机制组合：低风险可自动建议，高风险必须预览/确认；用户可暂停、延迟、拒绝、回滚；系统解释能力边界和错误恢复。跨编程、购物和机器人任务统一测主任务中断、错误恢复、过度/不足依赖和长期适应。

### R2 证据链中间表示的因果拆解

从 P20/P35/P37/P38/P40/P41/P55 抽取三因素：结构化表示、证据来源、可编辑/覆盖。做因子消融并加入真实脏数据或错误证据；主要终点为错误发现、决策正确、校准、返工和团队复现，而非只有 SUS。

### R3 个性化—文化—能力三层校正

结合 P05/P11/P23/P42/P49/P56/P59：区分用户明示偏好、系统推断文化/身份、动态能力状态；每层均提供来源、修改和撤销。检验个性化是否保持效率/支持感，同时不增加刻板化、能力误判或不自然拟态。

### R4 最终社会结果审计

结合 P07/P15/P22/P30/P47/P50/P51：从模型输出追踪到最终分配、披露、数据使用、伤害事件、参与决策权和收益。把人类 override、组织激励与申诉作为显式变量，比较“形式合规”与真实结果。

## 相互冲突或暂不能合并的方向

- 临床、教育、创作与社交陪伴的风险和目标不可用单一信任量表统一。
- 质性愿景（P50/P53/P56）与受控实验效果不能合成共同效应量；前者识别需求/制度，后者识别局部行为。
- P48/P52/P57 的量表效度不等于行为预测效度；量表之间也不能在未做 measurement invariance 时换算。
- P24 `p=.46<.05`、P31 NSFW 数字方向、P43 `F=1.48,p<.05` 为原文内部疑点，只能保留并要求源数据/勘误，不自行修正。
- P35/P40/P59 等非显著结果不能写成等效或成功；P50 的早期稿无可运行原型、不可称 NTA 已验证可行；P52 的 flexibility 在 Study1/Study2 修改模型中 α=.58/.47 且 CFA fit 中等，不能泛称所有因子可靠或量表已有行为效度。两文早期分析版本均需与正式版差异并列。

## 返回 paper-search 的术语、引用与查询建议

- `editable intermediate representation causal ablation`
- `appropriate reliance overreliance underreliance joint metric`
- `risk-tiered reversible proactive agent`
- `human override distributive fairness final decision`
- `culturally corrective personalization contestability`
- `longitudinal AI assistance skill retention`
- `stakeholder decision authority participation labor`
- `trust distrust behavioral calibration measurement invariance`

后续检索应优先寻找纵向部署、组件消融、负结果、勘误/复现和最终社会结果；摘要仅用于筛选，关键判断继续返回全文精读。
"""
    write(ROOT / "papers" / "SYNTHESIS.md", content)


def build_qa(selected: dict[str, dict[str, str]], cards: dict[str, dict], located: dict[str, dict]) -> None:
    venue_counts = Counter(row["venue"] for row in selected.values())
    source_counts = Counter(loc["meta"].get("source", "unknown") for loc in located.values())
    warning_ids = [pid for pid, card in cards.items() if card["cautions"]]
    content = {
        "generated_at": DATE,
        "selected_count": len(selected),
        "unique_doi_count": len({row["doi"].lower() for row in selected.values()}),
        "full_text_pdf_count": len(located),
        "full_text_txt_count": len(located),
        "full_text_meta_count": sum(loc["meta"].get("evidence_level") == "full text" for loc in located.values()),
        "analysis_card_count": len(cards),
        "reading_brief_count": 60,
        "per_paper_core_reading_products": 7,
        "venue_counts": dict(sorted(venue_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "warning_ids": warning_ids,
        "legacy_noncorpus_directories": [
            path.name
            for path in sorted(PAPER_ROOT.iterdir())
            if path.is_dir() and not path.name.startswith("p")
        ],
        "invariants": {
            "browser_started_by_builder": False,
            "publisher_state_touched": False,
            "pdf_or_txt_modified": False,
        },
    }
    write(SEARCH_ROOT / "qa-summary.json", json.dumps(content, ensure_ascii=False, indent=2))


def main() -> None:
    raise SystemExit(
        "disabled unsafe legacy generator: it hard-codes a universal interaction "
        "chain, fixed C1-C3/G1/O1 content, and a static synthesis. Use the active "
        "paper-search and paper-reading Agent workflows, then run "
        "scripts/qa_hai_artifacts.py for structural and semantic validation."
    )


if __name__ == "__main__":
    main()

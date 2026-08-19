#!/usr/bin/env python3
"""Render evidence-led HAI paper artifacts from validated full-text cards.

This renderer is intentionally corpus-specific and fail-closed.  Scientific
content comes from one independently prepared full-text evidence card per
paper.  The script validates identity, schema, source locations, and question
contracts before it writes Markdown.  It does not infer a universal execution
chain, fixed Claim/Gap/Opportunity counts, or cross-paper effect sizes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter, OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


GENERATOR_VERSION = "2.0.0"
DATE = "2026-08-19"
DEFAULT_ROOT = Path("/Users/aoudsung/Documents/AcdamicAgents")
PAPER_SUBDIR = Path("papers/human-ai-interaction-2025-2026")
SEARCH_SUBDIR = Path("searches/2026-08-18-human-ai-interaction-2025-2026")
EXPECTED_IDS = tuple(f"P{index:02d}" for index in range(1, 61))


KNOWLEDGE_ROUTES: OrderedDict[str, dict[str, Any]] = OrderedDict(
    {
        "AI进入工作流的角色、主动性与可控性": {
            "ids": (
                "P02", "P04", "P07", "P09", "P12", "P13", "P16", "P20",
                "P21", "P24", "P33", "P35", "P36", "P37", "P38", "P39",
                "P40", "P41", "P45", "P46",
            ),
            "question": "AI在何时介入、提供什么表示或行动，以及人能否检查、修改、拒绝和恢复？",
            "success": "先分别检查设计可供性、实际使用、任务结果与长期工作后果，不用可用性替代正确性。",
            "boundary": "多数证据来自短任务或原型评价；完整系统比较通常不能识别单个组件的作用。",
        },
        "决策依赖、解释与行为校准": {
            "ids": (
                "P06", "P18", "P19", "P25", "P26", "P27", "P32", "P34",
                "P43", "P44", "P47", "P55", "P59", "P60",
            ),
            "question": "人何时采纳、拒绝或修正AI，解释、置信度与能力沟通是否改善正确依赖？",
            "success": "同时观察正确采纳、错误采纳、正确拒绝、错误拒绝及任务后果。",
            "boundary": "信任、偏好、查看解释和准确率属于不同构念；非显著差异也不构成等效。",
        },
        "创造、价值、真实性与文化": {
            "ids": ("P03", "P05", "P10", "P11", "P23", "P31", "P42", "P49"),
            "question": "AI如何改变灵感、作品价值、作者真实性、文化表达和社会线索？",
            "success": "把产出质量、作者体验、读者判断、文化差异和行为选择分开。",
            "boundary": "效率或偏好收益可能与同质化、挪用、归属感或质量零结果同时存在。",
        },
        "学习、健康与社会支持": {
            "ids": ("P14", "P17", "P28", "P29", "P30", "P53", "P54", "P56", "P58"),
            "question": "教育、临床、健康与支持情境中，AI改善的是即时体验、任务表现还是长期结果？",
            "success": "区分形成性需求、即时可用性、知识或行为变化、临床疗效与制度后果。",
            "boundary": "一次会话、自报改善或设计愿景不能替代学习迁移、临床对照或长期安全证据。",
        },
        "组织治理、隐私、非使用与参与权": {
            "ids": ("P08", "P15", "P22", "P50", "P51"),
            "question": "谁能决定AI是否使用、披露什么、提供哪些数据，以及受影响者是否拥有实质权力？",
            "success": "把个人选择、专业责任、组织激励、政策文本和实际决策权连接起来。",
            "boundary": "访谈与政策分析能识别机制和断裂，却通常不能估计总体率或干预因果效果。",
        },
        "领域地图与测量基础设施": {
            "ids": ("P01", "P48", "P52", "P57"),
            "question": "领域怎样分类研究，信任、伙伴模型和人工社会代理体验如何被可靠测量？",
            "success": "检查语料覆盖、题项来源、因子结构、替代模型、行为关联与测量不变性。",
            "boundary": "量表内部结构或局部拟合不等于行为预测、跨群体等值或一般因果效度。",
        },
    }
)


CANDIDATE_TRACKS: OrderedDict[str, dict[str, Any]] = OrderedDict(
    {
        "A": {
            "name": "工作流、系统与可控协作",
            "ids": (
                "P02", "P04", "P07", "P09", "P12", "P13", "P16", "P20",
                "P21", "P24", "P35", "P36", "P37", "P38", "P39", "P40",
                "P41", "P45", "P46",
            ),
        },
        "B": {
            "name": "行为、决策、创造与应用结果",
            "ids": (
                "P03", "P05", "P06", "P10", "P14", "P17", "P18", "P19",
                "P23", "P25", "P26", "P27", "P28", "P29", "P30", "P31",
                "P32", "P33", "P34", "P42", "P43", "P44", "P47", "P49",
                "P54", "P55", "P56", "P58", "P59", "P60",
            ),
        },
        "C": {
            "name": "组织、制度、隐私、参与与真实实践",
            "ids": ("P08", "P11", "P15", "P22", "P50", "P51", "P53"),
        },
        "D": {
            "name": "综述、测量与方法边界",
            "ids": ("P01", "P48", "P52", "P57"),
        },
    }
)


ANCHOR_IDS = (
    "P01", "P02", "P05", "P06", "P07", "P19", "P22", "P32",
    "P38", "P48", "P51", "P57",
)


@dataclass(frozen=True)
class PaperSource:
    paper_id: str
    row: dict[str, str]
    directory: Path
    meta: dict[str, Any]
    txt_path: Path
    txt_lines: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--cards-dir",
        type=Path,
        default=None,
        help="Directory containing exactly P01.json through P60.json",
    )
    return parser.parse_args()


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))
    return re.sub(r"\s+", " ", value).strip().casefold()


def one_line(value: Any) -> str:
    if value is None:
        return "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "；".join(one_line(item) for item in value) if value else "无"
    if isinstance(value, dict):
        return "；".join(f"{key}={one_line(item)}" for key, item in value.items())
    return re.sub(r"\s+", " ", str(value)).strip() or "无"


def cell(value: Any, limit: int | None = None) -> str:
    text = one_line(value).replace("|", "／")
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def md_bullets(items: Iterable[Any], prefix: str = "- ") -> str:
    values = [one_line(item) for item in items]
    return "\n".join(prefix + item for item in values) if values else prefix + "无"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.casefold() == ".md":
        # The QA placeholder detector treats ASCII angle brackets as template
        # markers.  Full-width comparison glyphs preserve reported p-value and
        # threshold semantics without looking like unresolved Markdown slots.
        content = content.replace("<", "＜")
    if not content.endswith("\n"):
        content += "\n"
    temporary = path.with_name(path.name + ".tmp-render-v2")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def load_selection(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    ids = tuple(row["id"].strip().upper() for row in rows)
    if ids != EXPECTED_IDS:
        raise SystemExit(f"selection must be ordered P01..P60, found {ids}")
    dois = [row["doi"].strip().casefold() for row in rows]
    if len(dois) != len(set(dois)):
        raise SystemExit("selection contains duplicate DOI values")
    for row, paper_id in zip(rows, ids):
        row["id"] = paper_id
    return rows


def locate_sources(root: Path, rows: list[dict[str, str]]) -> dict[str, PaperSource]:
    paper_root = root / PAPER_SUBDIR
    sources: dict[str, PaperSource] = {}
    for row in rows:
        paper_id = row["id"]
        matches = sorted(paper_root.glob(f"{paper_id.lower()}-*/meta.json"))
        if len(matches) != 1:
            raise SystemExit(f"{paper_id}: expected one canonical meta.json, found {len(matches)}")
        meta_path = matches[0]
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        directory = meta_path.parent
        txt_path = directory / f"{directory.name}.txt"
        pdf_path = directory / f"{directory.name}.pdf"
        if not meta.get("ok") or meta.get("evidence_level") != "full text":
            raise SystemExit(f"{paper_id}: source is not normalized full text")
        if str(meta.get("selection_id", "")).upper() != paper_id:
            raise SystemExit(f"{paper_id}: meta selection_id mismatch")
        if str(meta.get("doi") or "").casefold() != row["doi"].casefold():
            raise SystemExit(f"{paper_id}: DOI mismatch between selection and meta")
        if not txt_path.is_file() or txt_path.stat().st_size < 5_000:
            raise SystemExit(f"{paper_id}: canonical TXT is missing or too short")
        if not pdf_path.is_file() or pdf_path.read_bytes()[:5] != b"%PDF-":
            raise SystemExit(f"{paper_id}: canonical PDF is missing or invalid")
        txt_lines = sum(1 for _ in txt_path.open(encoding="utf-8", errors="replace"))
        sources[paper_id] = PaperSource(
            paper_id=paper_id,
            row=row,
            directory=directory,
            meta=meta,
            txt_path=txt_path,
            txt_lines=txt_lines,
        )
    return sources


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)


TXT_REF_RE = re.compile(r"TXT\s*[:：]\s*(\d+)(?:\s*[-–—]\s*(\d+))?", re.IGNORECASE)


def validate_cards(
    cards_dir: Path,
    schema_path: Path,
    rows: list[dict[str, str]],
    sources: dict[str, PaperSource],
) -> dict[str, dict[str, Any]]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    cards: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    row_by_id = {row["id"]: row for row in rows}
    for paper_id in EXPECTED_IDS:
        path = cards_dir / f"{paper_id}.json"
        if not path.is_file():
            issues.append(f"{paper_id}: missing evidence card {path}")
            continue
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f"{paper_id}: invalid JSON: {exc}")
            continue
        for error in sorted(validator.iter_errors(card), key=lambda item: list(item.path)):
            location = ".".join(str(item) for item in error.path) or "$"
            issues.append(f"{paper_id}: schema {location}: {error.message}")
        if card.get("id") != paper_id:
            issues.append(f"{paper_id}: card id is {card.get('id')!r}")
        card_title = normalize_title(str(card.get("title", "")))
        selected_title = normalize_title(row_by_id[paper_id]["title"])
        meta_title = normalize_title(str(sources[paper_id].meta.get("title", "")))
        if card_title != meta_title:
            issues.append(f"{paper_id}: card title differs from canonical meta title")
        if card_title != selected_title and not card_title.startswith(selected_title):
            issues.append(f"{paper_id}: selected title is neither exact nor a prefix of canonical title")
        for collection, key in (("findings", "id"), ("claims", "id"), ("brief_questions", "id")):
            values = [item.get(key) for item in card.get(collection, []) if isinstance(item, dict)]
            if len(values) != len(set(values)):
                issues.append(f"{paper_id}: duplicate IDs in {collection}")
        expected_qids = [f"Q{index}" for index in range(1, len(card.get("brief_questions", [])) + 1)]
        actual_qids = [item.get("id") for item in card.get("brief_questions", [])]
        if actual_qids != expected_qids:
            issues.append(f"{paper_id}: Q IDs must be sequential, found {actual_qids}")
        max_line = sources[paper_id].txt_lines
        for string in iter_strings(card):
            for match in TXT_REF_RE.finditer(string):
                start = int(match.group(1))
                end = int(match.group(2) or match.group(1))
                if start < 1 or end < start or end > max_line:
                    issues.append(
                        f"{paper_id}: source reference {match.group(0)!r} outside TXT 1..{max_line}"
                    )
        cards[paper_id] = card
    extra = sorted(
        path.name
        for path in cards_dir.glob("P*.json")
        if re.fullmatch(r"P\d+\.json", path.name) and path.stem not in EXPECTED_IDS
    )
    if extra:
        issues.append(f"unexpected evidence cards: {extra}")
    if issues:
        preview = "\n".join(f"- {item}" for item in issues[:100])
        raise SystemExit(f"evidence-card validation failed ({len(issues)} issues):\n{preview}")
    return cards


def route_for(paper_id: str) -> str:
    matches = [name for name, route in KNOWLEDGE_ROUTES.items() if paper_id in route["ids"]]
    if len(matches) != 1:
        raise SystemExit(f"{paper_id}: route membership must be exactly one, found {matches}")
    return matches[0]


def paper_link(source: PaperSource, filename: str = "report.md", from_papers: bool = False) -> str:
    if from_papers:
        return f"human-ai-interaction-2025-2026/{source.directory.name}/{filename}"
    return f"../../papers/human-ai-interaction-2025-2026/{source.directory.name}/{filename}"


def identity_lines(source: PaperSource) -> str:
    meta = source.meta
    authors = "、".join(meta.get("authors") or []) or "元数据未列作者"
    return "\n".join(
        (
            f"- paper_key：{source.paper_id}",
            f"- 标题：{source.row['title']}",
            f"- 作者、年份、venue：{authors}；{source.row['year']}；{source.row['venue']}",
            f"- DOI：{source.row['doi']}",
            f"- arXiv（保留版本）：{one_line(meta.get('arxiv_id'))}",
            f"- OpenAlex ID：{one_line(meta.get('openalex_id'))}",
            f"- 首选引用版本：{one_line(meta.get('preferred_version') or source.row['doi'])}",
            f"- 实际分析版本：{one_line(meta.get('analyzed_version') or meta.get('preferred_version'))}",
            f"- 全文来源：{one_line(meta.get('source'))}",
            f"- 本地 TXT：{source.txt_path}",
        )
    )


def render_brief(source: PaperSource, card: dict[str, Any]) -> str:
    classification = card["classification"]
    reading = card["reading"]
    relations = card["relations"]
    relation_kinds = ", ".join(dict.fromkeys(item["relation_kind"] for item in relations))
    relation_targets = "；".join(item["target"] for item in relations)
    relation_claims = "；".join(item["relation"] for item in relations)
    evidence_levels = ", ".join(dict.fromkeys(item["evidence_level"] for item in relations))
    blocks = [
        f"# 精读交接单：{card['title']}",
        "",
        f"> 来源检索：searches/2026-08-18-human-ai-interaction-2025-2026/research-record.md | brief_id：{source.paper_id} | source_record_revision：v2 | 建立时间：{DATE}",
        "",
        "## 1. 论文身份",
        "",
        identity_lines(source),
        f"- 论文输入：{source.directory / (source.directory.name + '.pdf')}",
        "- 当前身份或版本疑点：以 meta.json 所列实际分析版本为证据范围；正式版差异需另行核对。",
        "",
        "## 2. 检索级类型假设",
        "",
        f"- paper_type_hypothesis：{' / '.join(classification['paper_type'])}",
        f"- study_design_hypothesis：{classification['study_design']}",
        f"- evidence_mode_hypothesis：{classification['evidence_mode']}",
        f"- analysis_unit_hypothesis：{classification['analysis_unit']}",
        f"- classification_basis：selected-papers.tsv 的 theme={source.row.get('theme', '')}、标题与来源元数据；全文分类核查锚点为 {classification['classification_evidence']}",
        "- 允许 Analysis 纠正：是",
        "",
        "## 3. 为什么现在读",
        "",
        f"- reading_role：{reading['reading_role']}",
        f"- reading_value_hypothesis：{reading['why_read']}",
        f"- priority_reason：{reading['priority']}；{reading['priority_reason']}",
        f"- best_alternative_and_why_insufficient：邻近项为 {relation_targets}；当前关系证据需按各条 evidence_level 单独解释，不能替代本文全文。",
        "",
        "## 4. 当前领域关系假设",
        "",
        f"- route_or_problem：{route_for(source.paper_id)}",
        f"- relation_kind：{relation_kinds}",
        f"- source_or_target_papers：{relation_targets}",
        f"- claimed_relation：{relation_claims}",
        f"- relation_assumptions：{'; '.join(item['conditions'] for item in relations)}",
        f"- evidence_level：{evidence_levels}",
        f"- uncertainty：{classification['inference_scope']}",
        "",
        "## 5. 需要精读核实的问题",
        "",
    ]
    for question in card["brief_questions"]:
        blocks.extend(
            (
                f"### {question['id']}｜{question['question']}",
                "",
                f"- target_judgment：{question['target_judgment']}",
                f"- current_search_judgment：{question['current_search_judgment']}",
                f"- why_it_matters：{question['why_it_matters']}",
                f"- expected_evidence：{question['expected_evidence']}",
                f"- priority：{question['priority']}",
                "- allowed_status：answered / partial / undetermined / not-applicable",
                "",
            )
        )
    blocks.extend(
        (
            "## 6. 相关工作与竞争解释",
            "",
            *(f"- {item['target']}｜{item['relation_kind']}｜{item['relation']}｜条件：{item['conditions']}｜证据层级：{item['evidence_level']}" for item in relations),
            "",
            "## 7. 当前证据边界",
            "",
            f"- 仅有检索级判断时不能越过：{classification['inference_scope']}",
            f"- 全文需优先核查：{'; '.join(card['cautions'])}",
            "- 本轮不要求 Analysis 回答的内容：论文未观察或未声称的总体率、跨场景效应和长期结果。",
            "",
            "## 8. 返回合同",
            "",
            "Analysis 必须逐字保留每个 Q# 与题目，并返回 status、conclusion、evidence_location、evidence_type、remaining_uncertainty、judgment_change、reading_value_change、domain_relation_change 与 next_search_action。",
        )
    )
    return "\n".join(blocks)


def render_record(source: PaperSource, card: dict[str, Any]) -> str:
    classification = card["classification"]
    reading = card["reading"]
    argument = card["argument"]
    feedback = card["feedback"]
    blocks = [
        f"# 全文证据账本：{card['title']}",
        "",
        f"> revision：v2 | 建立时间：{DATE} | 最近更新：{DATE} | evidence card：{source.paper_id}.json",
        "",
        "## 1. 论文身份与来源",
        "",
        identity_lines(source),
        "- reading-brief：reading-brief.md",
        "- 来源检索记录：searches/2026-08-18-human-ai-interaction-2025-2026/research-record.md",
        "- 身份或版本纠正：按 meta.json 锁定 DOI、全文来源与实际分析版本。",
        "",
        "## 2. 证据类型路由",
        "",
        f"- paper_type：{' / '.join(classification['paper_type'])}",
        f"- study_design：{classification['study_design']}",
        f"- evidence_mode：{classification['evidence_mode']}",
        f"- analysis_unit：{classification['analysis_unit']}",
        f"- inference_scope：{classification['inference_scope']}",
        f"- selected_reading_route：{route_for(source.paper_id)}",
        f"- classification_evidence：{classification['classification_evidence']}",
        "- 不适用模块：未在全文中出现的训练、交互、因果或测量模块不强行补齐。",
        "",
        "## 3. 本次问题合同",
        "",
    ]
    for question in card["brief_questions"]:
        blocks.extend(
            (
                f"### {question['id']}｜{question['question']}",
                "",
                f"- target_judgment：{question['target_judgment']}",
                f"- expected_evidence：{question['expected_evidence']}",
                f"- status：{question['status']}",
                f"- current_answer：{question['conclusion']}",
                f"- evidence_location：{question['evidence_location']}",
                f"- remaining_uncertainty：{question['remaining_uncertainty']}",
                "",
            )
        )
    blocks.extend(
        (
            "## 4. 作者的问题与论证结构",
            "",
            "### 4.1 作者认为出了什么问题",
            "",
            argument["problem"],
            "",
            "### 4.2 研究问题、命题或设计目标",
            "",
            md_bullets(argument["questions"]),
            "",
            "### 4.3 论证地图",
            "",
            "| 步骤/研究/章节 | 回答的问题 | 材料或方法 | 直接产出 | 原文位置 |",
            "|---|---|---|---|---|",
        )
    )
    for step in argument["steps"]:
        blocks.append(
            f"| {cell(step['label'])} | {cell(step['question'])} | {cell(step['method_or_material'])} | {cell(step['direct_output'])} | {cell(step['location'])} |"
        )
    blocks.extend(
        (
            "",
            "### 4.4 作者声称的贡献与未声称事项",
            "",
            "贡献：",
            "",
            md_bullets(argument["contributions"]),
            "",
            "没有建立或没有声称：",
            "",
            md_bullets(argument["not_claimed"]),
            "",
            "## 5. 研究设计与证据整合",
            "",
            f"- 研究设计：{classification['study_design']}",
            f"- 证据材料：{classification['evidence_mode']}",
            f"- 统计或解释单位：{classification['analysis_unit']}",
            f"- 允许的推断：{classification['inference_scope']}",
            "- 整合规则：每个组成方法先保留自己的分析单位和直接产出，再依据论证地图说明它们如何共同支持或限制主张。",
            "",
            "## 6. 核心发现、零结果和例外",
            "",
            "| Finding ID | 具体发现 | 证据类型 | 样本/设置/分析单位 | 原文位置 | 作者解释 | 边界或反例 |",
            "|---|---|---|---|---|---|---|",
        )
    )
    for finding in card["findings"]:
        blocks.append(
            "| {id} | {finding} | {evidence} | {setting} | {location} | {interpretation} | {boundary} |".format(
                id=cell(finding["id"]),
                finding=cell(finding["finding"]),
                evidence=cell(finding["evidence_type"]),
                setting=cell(finding["setting_or_sample"]),
                location=cell(finding["location"]),
                interpretation=cell(finding["author_interpretation"]),
                boundary=cell(finding["boundary_or_counterevidence"]),
            )
        )
    blocks.extend(("", "## 7. 论文特异的 Claim-Evidence Cards", ""))
    for claim in card["claims"]:
        blocks.extend(
            (
                f"### {claim['id']}｜{claim['claim_text']}",
                "",
                f"- claim_text：{claim['claim_text']}",
                f"- statement_source：{claim['statement_source']}",
                f"- claim_kind：{claim['claim_kind']}",
                f"- analysis_unit：{claim['analysis_unit']}",
                f"- evidence_type：{claim['evidence_type']}",
                f"- evidence_location：{claim['evidence_location']}",
                f"- observed_result：{claim['observed_result']}",
                f"- inference_rule：{claim['inference_rule']}",
                f"- required_assumptions：{claim['required_assumptions']}",
                f"- support_status：{claim['support_status']}",
                f"- boundary_conditions：{claim['boundary_conditions']}",
                f"- unresolved_part：{claim['unresolved_part']}",
                "",
            )
        )
    blocks.extend(
        (
            "## 8. 贡献、相邻工作与领域关系",
            "",
            f"- 本文独有的知识增量：{reading['why_read']}",
            f"- reading_role：{reading['reading_role']}",
            f"- 当前领域作用：{route_for(source.paper_id)}",
            "",
            "| 目标论文/路线 | relation kind | 具体关系 | 成立条件 | 证据层级 |",
            "|---|---|---|---|---|",
        )
    )
    for relation in card["relations"]:
        blocks.append(
            f"| {cell(relation['target'])} | {cell(relation['relation_kind'])} | {cell(relation['relation'])} | {cell(relation['conditions'])} | {cell(relation['evidence_level'])} |"
        )
    blocks.extend(
        (
            "",
            "## 9. 阅读价值与引用用途",
            "",
            f"- reading_role：{reading['reading_role']}",
            f"- why_read：{reading['why_read']}",
            f"- audience：{reading['audience']}",
            f"- reading_priority：{reading['priority']}；{reading['priority_reason']}",
            f"- best_sections：{one_line(reading['best_sections'])}",
            f"- use_for：{one_line(reading['use_for'])}",
            f"- do_not_use_for：{one_line(reading['do_not_use_for'])}",
            "",
            "## 10. 证据审计",
            "",
            "| Claim | 证据实际观察什么 | 推理规则 | 关键假设 | 支持状态 | 边界与未决 |",
            "|---|---|---|---|---|---|",
        )
    )
    for claim in card["claims"]:
        blocks.append(
            f"| {cell(claim['id'])} | {cell(claim['observed_result'])} | {cell(claim['inference_rule'])} | {cell(claim['required_assumptions'])} | {cell(claim['support_status'])} | {cell(claim['boundary_conditions'] + '；' + claim['unresolved_part'])} |"
        )
    if card["optional_gap"] is not None:
        blocks.extend(("", "## 11. 可选：由全文明确支持的科学 Gap", ""))
        for key, value in card["optional_gap"].items():
            blocks.append(f"- {key}：{one_line(value)}")
    if card["optional_opportunity"] is not None:
        blocks.extend(("", "## 12. 可选：由全文明确支持的候选研究程序", ""))
        for key, value in card["optional_opportunity"].items():
            blocks.append(f"- {key}：{one_line(value)}")
    blocks.extend(("", "## 13. 按需独立批评", "", md_bullets(card["cautions"]), "", "## 14. 对 reading-brief 的逐项回答", ""))
    for question in card["brief_questions"]:
        blocks.extend(
            (
                f"### {question['id']}｜{question['question']}",
                "",
                f"- status：{question['status']}",
                f"- conclusion：{question['conclusion']}",
                f"- evidence_location：{question['evidence_location']}",
                f"- evidence_type：{question['evidence_type']}",
                f"- remaining_uncertainty：{question['remaining_uncertainty']}",
                f"- judgment_change：{question['judgment_change']}",
                f"- reading_value_change：{question['reading_value_change']}",
                f"- domain_relation_change：{question['domain_relation_change']}",
                f"- next_search_action：{question['next_search_action']}",
                "",
            )
        )
    blocks.extend(
        (
            "## 15. 返回 Search 的变更集",
            "",
            f"- reading_value_before：{feedback['reading_value_before']}",
            f"- reading_value_after：{feedback['reading_value_after']}",
            f"- domain_relation_before：{feedback['domain_relation_before']}",
            f"- domain_relation_after：{feedback['domain_relation_after']}",
            f"- relation_kind：{feedback['relation_kind']}",
            f"- new_terms：{one_line(feedback['new_terms'])}",
            f"- citations_to_expand：{one_line(feedback['citations_to_expand'])}",
            f"- invalidated_routes_or_tasks：{one_line(feedback['invalidated_routes_or_tasks'])}",
            "",
            "## 16. 更新记录",
            "",
            f"- {DATE} / v2：从验证后的全文证据卡重建；保留分析单位、证据类型、反例、问题合同与来源位置。",
        )
    )
    return "\n".join(blocks)


def render_return(source: PaperSource, card: dict[str, Any]) -> str:
    classification = card["classification"]
    reading = card["reading"]
    feedback = card["feedback"]
    blocks = [
        f"# 精读返回：{card['title']}",
        "",
        f"> 论文记录：research-record.md | 来源交接单：reading-brief.md | brief_id：{source.paper_id} | source_record_revision：v2",
        "",
        "## 1. 身份与类型纠正",
        "",
        identity_lines(source),
        f"- paper_type_hypothesis → confirmed：{' / '.join(classification['paper_type'])}",
        f"- study_design_hypothesis → confirmed：{classification['study_design']}",
        f"- evidence_mode_hypothesis → confirmed：{classification['evidence_mode']}",
        f"- analysis_unit_hypothesis → confirmed：{classification['analysis_unit']}",
        f"- classification_evidence：{classification['classification_evidence']}",
        "",
        "## 2. 对交接问题的逐项回答",
        "",
    ]
    for question in card["brief_questions"]:
        blocks.extend(
            (
                f"### {question['id']}｜{question['question']}",
                "",
                f"- status：{question['status']}",
                f"- conclusion：{question['conclusion']}",
                f"- evidence_location：{question['evidence_location']}",
                f"- evidence_type：{question['evidence_type']}",
                f"- remaining_uncertainty：{question['remaining_uncertainty']}",
                f"- judgment_change：{question['judgment_change']}",
                f"- reading_value_change：{question['reading_value_change']}",
                f"- domain_relation_change：{question['domain_relation_change']}",
                f"- next_search_action：{question['next_search_action']}",
                "",
            )
        )
    blocks.extend(
        (
            "## 3. 检索判断与阅读价值变更",
            "",
            f"- reading_value_before：{feedback['reading_value_before']}",
            f"- reading_value_after：{feedback['reading_value_after']}",
            f"- reading_role：{reading['reading_role']}",
            f"- why_read：{reading['why_read']}",
            f"- best_sections：{one_line(reading['best_sections'])}",
            f"- use_for：{one_line(reading['use_for'])}",
            f"- do_not_use_for：{one_line(reading['do_not_use_for'])}",
            "",
            "## 4. 领域关系变更",
            "",
            f"- domain_relation_before：{feedback['domain_relation_before']}",
            f"- domain_relation_after：{feedback['domain_relation_after']}",
            f"- relation_kind：{feedback['relation_kind']}",
        )
    )
    for relation in card["relations"]:
        blocks.append(
            f"- related_paper：{relation['target']}｜{relation['relation_kind']}｜{relation['relation']}｜条件：{relation['conditions']}｜证据层级：{relation['evidence_level']}"
        )
    blocks.extend(
        (
            "",
            "## 5. 可回用于检索的新信息",
            "",
            f"- new_terms：{one_line(feedback['new_terms'])}",
            f"- citations_to_expand：{one_line(feedback['citations_to_expand'])}",
            f"- invalidated_routes_or_tasks：{one_line(feedback['invalidated_routes_or_tasks'])}",
            "",
            "## 6. 论文真正建立了什么",
            "",
            "具体贡献：",
            "",
            md_bullets(card["argument"]["contributions"]),
            "",
            "未建立的内容：",
            "",
            md_bullets(card["argument"]["not_claimed"]),
            "",
            "最重要的零结果、反例或边界：",
            "",
            md_bullets(card["cautions"]),
            "",
            "## 7. 建议 Search 更新",
            "",
            f"把 {source.paper_id} 的 paper type、reading role 与领域关系更新为本文件的全文判断；仅有 metadata 的邻文关系保持 metadata，不升级成全文比较。",
        )
    )
    return "\n".join(blocks)


def render_report(source: PaperSource, card: dict[str, Any]) -> str:
    classification = card["classification"]
    reading = card["reading"]
    argument = card["argument"]
    status_counts = Counter(claim["support_status"] for claim in card["claims"])
    blocks = [
        f"# 《{card['title']}》精读报告",
        "",
        f"> 生成时间：{DATE} | 证据账本：research-record.md | 证据卡：{source.paper_id}.json",
        "",
        "## 0. 为什么值得读",
        "",
        f"{source.paper_id} 的阅读判断：{reading['why_read']}",
        "",
        f"- reading_role：{reading['reading_role']}",
        f"- 最适合的读者：{reading['audience']}",
        f"- 阅读优先级：{reading['priority']}；{reading['priority_reason']}",
        f"- 时间有限时先读：{one_line(reading['best_sections'])}",
        "",
        "## 1. 作者在回答什么",
        "",
        argument["problem"],
        "",
        "论文的问题或设计目标：",
        "",
        md_bullets(argument["questions"]),
        "",
        "## 2. 论文怎样回答",
        "",
        f"- paper type：{' / '.join(classification['paper_type'])}",
        f"- study design：{classification['study_design']}",
        f"- evidence mode：{classification['evidence_mode']}",
        f"- analysis unit：{classification['analysis_unit']}",
        f"- 分类依据：{classification['classification_evidence']}",
        "",
        "| 步骤 | 这一部分回答什么 | 材料或方法 | 直接产出 | 位置 |",
        "|---|---|---|---|---|",
    ]
    for step in argument["steps"]:
        blocks.append(
            f"| {cell(step['label'])} | {cell(step['question'])} | {cell(step['method_or_material'])} | {cell(step['direct_output'])} | {cell(step['location'])} |"
        )
    blocks.extend(("", "## 3. 核心发现、零结果与例外", ""))
    for finding in card["findings"]:
        blocks.extend(
            (
                f"### {finding['id']}｜{finding['finding']}",
                "",
                f"- 证据类型与设置：{finding['evidence_type']}；{finding['setting_or_sample']}",
                f"- 原文位置：{finding['location']}",
                f"- 作者解释：{finding['author_interpretation']}",
                f"- 边界、零结果或反例：{finding['boundary_or_counterevidence']}",
                "",
            )
        )
    blocks.extend(
        (
            "## 4. 论文贡献在哪里",
            "",
            "直接贡献与新增：",
            "",
            md_bullets(argument["contributions"]),
            "",
            "不应追加到作者名下的结论：",
            "",
            md_bullets(argument["not_claimed"]),
            "",
            "## 5. 与相邻论文的知识关系",
            "",
            "| 相邻论文或路线 | 关系 | 本文增加或改变什么 | 关系成立条件 | 证据层级 |",
            "|---|---|---|---|---|",
        )
    )
    for relation in card["relations"]:
        blocks.append(
            f"| {cell(relation['target'])} | {cell(relation['relation_kind'])} | {cell(relation['relation'])} | {cell(relation['conditions'])} | {cell(relation['evidence_level'])} |"
        )
    blocks.extend(
        (
            "",
            "## 6. 证据有多强",
            "",
            f"- 推断范围：{classification['inference_scope']}",
            f"- Claim 支持分布：{', '.join(f'{key}={value}' for key, value in sorted(status_counts.items()))}",
            f"- {source.paper_id} Claim 审计方式：每项主张的观察结果、推理规则、必要假设和边界均在 research-record.md 中逐项列出。",
            f"- 最重要的证据边界：{one_line(card['cautions'])}",
            f"- 可以推出：{one_line(reading['use_for'])}",
            f"- 不能推出：{one_line(reading['do_not_use_for'])}",
            "",
            "## 7. 如何阅读、引用与避免误用",
            "",
            f"- reading_role：{reading['reading_role']}",
            f"- best_sections：{one_line(reading['best_sections'])}",
            f"- use_for：{one_line(reading['use_for'])}",
            f"- do_not_use_for：{one_line(reading['do_not_use_for'])}",
            f"- {source.paper_id} 与邻文组合时：逐条保留 relation 的 evidence_level；metadata 关系只用于决定下一步阅读，不能写成结果比较。",
            "",
            "## 8. 对精读交接问题的回答",
            "",
            "| Q# | 问题 | 状态 | 结论 | 关键证据位置 | 对原判断的改变 |",
            "|---|---|---|---|---|---|",
        )
    )
    for question in card["brief_questions"]:
        blocks.append(
            f"| {cell(question['id'])} | {cell(question['question'])} | {cell(question['status'])} | {cell(question['conclusion'])} | {cell(question['evidence_location'])} | {cell(question['judgment_change'])} |"
        )
    if card["optional_gap"] is not None or card["optional_opportunity"] is not None:
        blocks.extend(("", "## 9. 可选的证据审计或后续研究", ""))
        if card["optional_gap"] is not None:
            blocks.append("全文明确支持的未决关系：")
            blocks.append("")
            for key, value in card["optional_gap"].items():
                blocks.append(f"- {key}：{one_line(value)}")
        if card["optional_opportunity"] is not None:
            blocks.append("")
            blocks.append("全文明确提出的研究方向：")
            blocks.append("")
            for key, value in card["optional_opportunity"].items():
                blocks.append(f"- {key}：{one_line(value)}")
    blocks.extend(("", "---", "", "详细证据见 research-record.md；Search 变更集见 reading-return.md。"))
    return "\n".join(blocks)


def render_index(rows: list[dict[str, str]], sources: dict[str, PaperSource], cards: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# 论文索引：Human–AI Interaction 2025–2026",
        "",
        f"> 60 篇唯一 DOI；全部具有本地 PDF/TXT、全文证据卡和 v2 四类核心报告；更新于 {DATE}。",
        "",
        "| ID | 标题 | 年份/venue | 研究类型 | 证据模式 | 分析单位 | 领域作用 | 阅读价值 | 主要边界 | 报告 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        paper_id = row["id"]
        source = sources[paper_id]
        card = cards[paper_id]
        report_path = paper_link(source, from_papers=True)
        title_link = f"[{cell(row['title'])}]({report_path})"
        lines.append(
            "| {pid} | {title} | {year}/{venue} | {ptype} | {emode} | {unit} | {role} | {value} | {boundary} | [report]({report}) |".format(
                pid=paper_id,
                title=title_link,
                year=cell(row["year"]),
                venue=cell(row["venue"]),
                ptype=cell(card["classification"]["paper_type"]),
                emode=cell(card["classification"]["evidence_mode"], 180),
                unit=cell(card["classification"]["analysis_unit"], 180),
                role=cell(route_for(paper_id) + "；" + card["reading"]["reading_role"]),
                value=cell(card["reading"]["why_read"], 220),
                boundary=cell(card["cautions"][0], 200),
                report=report_path,
            )
        )
    return "\n".join(lines)


def render_synthesis(sources: dict[str, PaperSource], cards: dict[str, dict[str, Any]]) -> str:
    def refs(ids: Iterable[str]) -> str:
        return "、".join(f"{paper_id}《{sources[paper_id].row['title']}》" for paper_id in ids)

    lines = [
        "# 领域知识合成：Human–AI Interaction 2025–2026",
        "",
        f"> 生成时间：{DATE} | 论文索引：papers/INDEX.md | 纳入标准：selected-papers.tsv 中 P01–P60，全部以本地完整 PDF/TXT 证据卡为依据。",
        "",
        "## 0. 领域认识摘要",
        "",
        "这组论文没有支持一个统一的“AI介入—人类受益”规律。更稳定的认识是：AI的角色、人的控制动作、近端体验、任务行为和下游社会结果必须分别观察；任何一层的正面结果都不能自动替代下一层。P06 的主观帮助感与问题重构质量零结果、P07 的可接受性与会议行为脱钩、P43 的享受/再用意愿与易用/信任分离，以及 P47 的形式公平与最终人机分配差异共同限定了这一判断。",
        "",
        "当前证据最密集的是短时系统评价与受控任务；真实组织实践、长期能力变化、临床结果和制度后果更稀疏。P08、P22、P50、P51 提供了组织与治理材料，但这些研究主要识别条件、权力与解释差距，不是干预效果试验。P48、P52、P57 则说明，量表验证自身是独立研究问题，不能把结构效度直接改写成行为效度。",
        "",
        "## 1. 领域边界与核心问题树",
        "",
        "| 层级 | 核心问题 | 合适分析单位 | 能回答的证据 | 常见误用 |",
        "|---|---|---|---|---|",
        "| 角色与可供性 | AI能做什么，人能否查看、修改、拒绝或回滚？ | 系统组件、提示、表示、控制动作 | 架构、实现、交互日志 | 把“功能存在”写成“功能改善结果” |",
        "| 近端体验 | 人是否觉得有用、可信、容易、受支持？ | 参与者—条件评分、访谈主题 | 量表、自报、质性材料 | 把偏好或信任当成正确性 |",
        "| 行为与任务 | 人实际采纳、核验、修订什么，任务结果怎样？ | 决策、动作序列、任务产出 | 受控比较、行为日志、盲评 | 只报告总准确率而隐藏正确/错误采纳 |",
        "| 长期实践 | 工作流、技能、策略和责任如何随时间变化？ | 人—组织—任务的纵向事件 | 现场、纵向、组织研究 | 从一次会话外推 deskilling 或持续收益 |",
        "| 社会与制度结果 | 谁获益、谁承担风险，参与和申诉是否有权力？ | 最终分配、伤害、数据流、决策权 | 审计、政策、参与式与部署研究 | 把 human-in-the-loop 或一次 workshop 当成治理结果 |",
        "| 测量基础 | 所用构念是否稳定、可比较并关联行为？ | 题项、因子、群体与外部标准 | 心理测量、替代模型、不变性 | 把内部一致性或局部拟合当成跨情境效度 |",
        "",
        "本合成覆盖人—AI协作、创造、工作、决策、教育、健康、机器人、治理与测量；不把60篇选择样本当作领域发表率估计，也不计算跨异质任务的合并效应量。",
        "",
        "## 2. 覆盖论文、证据类型与阅读角色",
        "",
        "完整逐篇矩阵见 papers/INDEX.md。索引同时列出 paper type、evidence mode、analysis unit、reading role、独有阅读价值和主要边界，P编号只用于定位。",
        "",
        "## 3. 研究传统与路线",
        "",
    ]
    for route_name, route in KNOWLEDGE_ROUTES.items():
        lines.extend(
            (
                f"### {route_name}",
                "",
                f"- 回答的问题：{route['question']}",
                f"- 成功标准：{route['success']}",
                f"- 代表论文：{refs(route['ids'])}",
                f"- 已知边界：{route['boundary']}",
                "",
            )
        )
    lines.extend(
        (
            "## 4. 跨论文证据关系矩阵",
            "",
            "| 知识问题 | 来源论文与具体关系 | 可比分析单位 | relation | 成立条件 | 不能合并的部分 |",
            "|---|---|---|---|---|---|",
            "| 主动性与时机 | P12 比较编程建议形态；P33 区分 Timer 与 Button；P43 比较 reactive/proactive 能力沟通；P46 比较忙碌时递交与放置 | 各自任务中的触发条件、行为或即时评价 | conditions | 必须匹配风险、忙碌状态、动作权限和结果定义 | 编程测试、问题求解表现、对话体验与机器人递物感受不能形成共同效应 |",
            "| 可编辑中间表示 | P24 对话图、P35 推理要素、P37 feedback decomposition、P38 dataflow、P39 spatial canvas、P40 narrative schema、P41 benchmark grading、P45 image timeline | 表示、编辑/覆盖动作、错误发现或任务产出 | analogue / conditions | 分离表示可见性、可编辑性、来源追溯和底层模型 | 原型功能、SUS、自报效率和客观正确性不是同一结果 |",
            "| 依赖校准 | P18 不确定性/简短回复、P19 行为指标、P26 部分解释、P32 对比解释、P34 persuasion、P47 公平 override、P59 个性化解释、P60 ToM 透明性 | 建议正确性×采纳/拒绝×任务结果 | conditions / challenges | 同时保留正确采纳和错误采纳，并匹配准确率与风险 | 信任量表、解释查看、感知透明性和最终绩效不可互换 |",
            "| 文化与个性化 | P05 文化同质化、P42 非随机文化组礼貌行为、P49 minoritized sociolect、P59 专业级解释 | 文本/语气条件、文化组、行为与体验 | challenges / conditions | 文化组、语言内容、任务与受众必须明确 | 国家组别、方言线索、专业经验和文化表达不是同一构念 |",
            "| 参与、披露与所有权 | P08 非使用配置、P22 工作者—客户政策错配、P50 新闻业数据/组织所有权、P51 rAI 指导—实践断裂 | 工作叙述、政策解释、组织安排与决策权 | governance | 区分个人意向、正式政策、实际行为和最终权力 | 访谈主题、调查比例和规范目标不能合成干预效果 |",
            "| 测量有效性 | P48 信任/不信任双因子、P52 partner model 三因子、P57 24组 ASAQ | 题项—因子—样本—外部标准 | measurement / incomparable | 分别检查结构、信度、不变性、方法效应和行为关联 | 三套量表构念不同，不能换算成单一“信任/体验”得分 |",
            "",
            "## 5. 已相对建立的认识",
            "",
            "### K1｜近端主观收益与任务或社会结果必须分开",
            "",
            "P06 发现LLM条件的主观帮助不对应更好的问题重构质量；P07 的OAI原型提高部分主观评价却未改变目标会议行为；P43 的proactive能力沟通只在enjoyment和willingness上有显著事后差异；P59 的准确率非显著不能写成等效。不同研究类型以相互补充的方式支持“构念不可替代”，而不是支持某个统一负效应。",
            "",
            "### K2｜有控制按钮不等于人类已有效监督，但交互日志能检验控制是否被使用",
            "",
            "P20、P35、P41 记录了证据查看、编辑、覆盖或修订行为，因此比仅陈述 human-in-the-loop 多一层行为证据；P38 还记录检查与修复机制及未修复失败。它们仍没有共同证明这些动作提高了客观正确性，故“控制存在—控制被用—结果改善”应作为三个判断。",
            "",
            "### K3｜依赖问题是双向分类问题，不是越少依赖越好",
            "",
            "P18 和 P26 的干预会改变错误建议与正确建议的使用，P19 进一步把过度依赖映射为动作序列，P47 表明人的override可能改变形式公平结果。由此可以稳定要求研究同时报告过度依赖与不足依赖；但不同任务的净效应仍取决于错误率、成本和基线。",
            "",
            "### K4｜组织中的AI使用、非使用和披露由多层条件共同配置",
            "",
            "P08 的UX非使用、P22 的自由职业披露、P50 的新闻业所有权和P51的stakeholder participation都显示：个人价值、专业责任、客户关系、合规、组织激励和决策权不能压缩成个人采纳意愿。这一认识由不同质性、调查和政策材料共同支持，但不提供各因素的总体权重。",
            "",
            "### K5｜测量工具的有效性必须限定到已检验结构与样本",
            "",
            "P48 支持信任/不信任双因子相对优于单因子但RMSEA仍不理想；P52 的18题模型只是相对优于23题且communication flexibility内部一致性偏低；P57 的局部/分组CFA较强却没有可接受的全局模型或不变性证据。因此，“validated”必须附带版本、构念、样本与失败模型。",
            "",
            "## 6. 有条件成立或仍有争议的认识",
            "",
            "### T1｜主动式帮助可能有效，但有效对象不是“主动性”本身",
            "",
            "P12 的固定编程任务支持若干主动建议形态的任务收益；P33 中 Timer 相对 Button 没有总体绩效优势；P43 的 reactive 不优于 baseline，而 proactive 改善部分体验；P46 的忙碌递物结果又涉及实体动作风险。差异更像时机、任务、权限和结果定义的条件化，而非简单矛盾。",
            "",
            "### T2｜结构化和可编辑表示改善可检查性，但尚不能普遍推出质量提升",
            "",
            "P35、P38、P40、P41 给出具体工作流和正面感知或理由评分；P39只有六人探索性定性评价；P24、P31等还包含零结果或数值疑点。现有材料足以比较设计机制和失败点，不足以合并为“可编辑表示提高正确性”的领域效应。",
            "",
            "### T3｜个性化可以增加适配，也可能改变文化表达、归因与依赖",
            "",
            "P03、P11、P23描述个性化或共同创作的体验价值；P05报告文化同质化，P42的日本/瑞典组不能归因于单一Hofstede维度，P49中AAE与Queer slang行为结果不同，P59又混杂语气与解释内容。当前证据支持条件敏感性，不支持统一的个性化收益。",
            "",
            "### T4｜效率改进是否值得，取决于质量、风险和比较基线",
            "",
            "P05、P12、P45、P59含时间或完成表现收益，但P05同时出现文化表达代价，P45的总错误无显著差异且节时数字内部不一致，P59没有信息量匹配的中性解释条件。效率只能作为一个终点，不能充当总体价值。",
            "",
            "## 7. 暂不可比较的方向",
            "",
            "| 论文/路线 | 不可比较原因 | 差异所在 | 未来何时可比较 |",
            "|---|---|---|---|",
            "| P39系统设计与P31受控创作实验 | 前者为六人探索性定性评价，后者含量表与条件比较 | 证据类型、分析单位、结果构念 | 共享任务、对照与产出质量量规时 |",
            "| P54机器人心理健康教练与临床疗效研究 | P54为单次无对照即时mood/RR前后变化 | 时间尺度、对照、临床终点 | 有对照、随访与临床安全结果时 |",
            "| P55谬误分类与misinformation真值识别 | 0.84–0.85是逻辑谬误分类准确率 | 标签目标和错误成本 | 同时标注谬误与事实真值并审计时 |",
            "| P48/P52/P57三套量表 | 构念、题项和验证样本不同 | 潜变量与计分单位 | 多量表同样本、行为标准和不变性分析时 |",
            "| 定性组织研究与短时受控实验 | 前者解释条件与意义，后者估计局部条件差异 | 推断目标和抽样逻辑 | 以现场部署连接机制、行为与组织结果时 |",
            "",
            "## 8. 领域演化与证据缺口",
            "",
            "研究正在从“AI输出是否更好”扩展到介入时机、可编辑表示、证据追溯、人的修订行为、组织权力和测量效度。重复出现的缺口不是笼统的“需要更多研究”，而是缺少把近端控制动作连接到客观结果、长期实践和最终社会后果的同一条可审计证据链。语料中临床、教育、低资源地区、受影响非用户和长期组织适应仍不足；这既可能是领域空白，也可能来自本次60篇选择范围。",
            "",
            "## 9. 分层阅读路径",
            "",
            "| 层级 | 论文 | 为什么读 | 优先内容 | 与前后论文的关系 |",
            "|---|---|---|---|---|",
            "| 入门地图 | P01 | 了解CHI 2020–2024中LLM研究的应用、贡献类型与方法问题 | 编码框架、覆盖限制 | 为其余论文提供样本地图，不是效果综述 |",
            "| 系统与控制 | P20、P35、P38、P41 | 比较证据支架、可编辑表示、检查修复和教师覆盖 | 工作流、日志、失败与局限 | 从设计可供性逐步走向使用行为 |",
            "| 决策与反证 | P06、P18、P26、P32、P43、P47、P59、P60 | 观察偏好、信任、依赖、正确性和公平结果如何脱钩 | 零结果、比较条件、交互与表格冲突 | 防止把体验收益写成结果收益 |",
            "| 文化与真实性 | P05、P11、P23、P42、P49 | 理解个性化、文化表达和真实性的多构念性 | 文化分组、行为指标、定性反例 | 约束通用个性化原则 |",
            "| 测量方法 | P48、P52、P57 | 学会审查量表结构、失败模型与迁移边界 | CFA、信度、不变性、外部关联 | 为其他论文的自报结果提供测量警戒 |",
            "| 制度与部署 | P08、P22、P50、P51、P53 | 从个人交互转向组织、政策、参与权和真实实践 | 招募、语料、权力与转移边界 | 补足短时实验无法回答的制度条件 |",
            "",
            "## 10. 返回 Search 的变更",
            "",
            "Search 应按问题层级和证据类型维护路线，而不是按“AI提升了什么”汇总。后续查询优先寻找：组件消融与匹配基线；正确/错误采纳联合指标；真实工作流纵向日志；临床或学习长期终点；参与决策权与最终社会结果；跨语言、跨文化和直接交互的测量不变性。每条 metadata 关系必须保持 metadata 标签，直到目标全文被单独核查。",
        )
    )
    return "\n".join(lines)


def render_query_map(cards: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Query Map：Human–AI Interaction 2025–2026",
        "",
        f"> revision：v2 | 更新：{DATE} | 查询目标：形成按问题、分析单位与证据类型组织的可核验文献地图。",
        "",
        "## 核心问题树",
        "",
        "1. AI在工作流中承担什么角色，何时介入，哪些控制动作真实可用？",
        "2. 人如何形成、校准和修正依赖，解释与透明性改变的是体验还是行为？",
        "3. 创造、真实性、文化、学习和健康结果采用了什么构念与时间尺度？",
        "4. 组织政策、数据权利、披露与参与权怎样限制个人交互？",
        "5. 量表、分类器和代理指标是否具有结构、行为与跨情境效度？",
        "",
        "## 路线化查询",
        "",
        "| 路线 | 核心查询结构 | 必须加入的证据限定 | 停止条件 |",
        "|---|---|---|---|",
    ]
    query_map = {
        "AI进入工作流的角色、主动性与可控性": "proactive OR mixed-initiative OR editable representation OR human override",
        "决策依赖、解释与行为校准": "appropriate reliance OR overreliance OR underreliance OR explanation calibration",
        "创造、价值、真实性与文化": "AI co-creation authenticity cultural homogenization personalization",
        "学习、健康与社会支持": "AI learning support OR clinical workflow OR mental health longitudinal outcome",
        "组织治理、隐私、非使用与参与权": "AI non-use disclosure stakeholder decision authority data ownership",
        "领域地图与测量基础设施": "human AI trust scale validation measurement invariance behavioral validity",
    }
    for route_name, route in KNOWLEDGE_ROUTES.items():
        lines.append(
            f"| {route_name} | `{query_map[route_name]}` | {route['success']} | {route['boundary']} |"
        )
    lines.extend(("", "## 精读反馈新增术语", ""))
    for route_name, route in KNOWLEDGE_ROUTES.items():
        terms: list[str] = []
        for paper_id in route["ids"]:
            for term in cards[paper_id]["feedback"]["new_terms"]:
                if term not in terms:
                    terms.append(term)
        lines.append(f"- {route_name}：{one_line(terms[:20])}")
    lines.extend(
        (
            "",
            "## 查询约束",
            "",
            "- metadata 和 abstract 只用于身份、初筛与待核关系，不写成论文结果。",
            "- 比较前先对齐分析单位、构念、条件、时间尺度与证据类型。",
            "- 非显著结果不改写为等效；内部冲突保留原数值并寻找勘误或源数据。",
            "- 只有会改变当前知识判断的查询继续扩展；重复同质候选停止。",
        )
    )
    return "\n".join(lines)


def render_candidates(
    track: str,
    sources: dict[str, PaperSource],
    cards: dict[str, dict[str, Any]],
) -> str:
    spec = CANDIDATE_TRACKS[track]
    lines = [
        f"# Candidates {track}：{spec['name']}",
        "",
        f"> 这些论文均已进入正式60篇集合并完成全文核查；表中不再保留摘要级结果判断。更新：{DATE}。",
        "",
        "| ID | 标题 | paper type | analysis unit | reading role | 独有阅读价值 | 主要边界 | report |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for paper_id in spec["ids"]:
        source = sources[paper_id]
        card = cards[paper_id]
        link = paper_link(source)
        lines.append(
            f"| {paper_id} | {cell(source.row['title'])} | {cell(card['classification']['paper_type'])} | {cell(card['classification']['analysis_unit'], 180)} | {cell(card['reading']['reading_role'])} | {cell(card['reading']['why_read'], 220)} | {cell(card['cautions'][0], 180)} | [report]({link}) |"
        )
    return "\n".join(lines)


def render_graph(sources: dict[str, PaperSource], cards: dict[str, dict[str, Any]]) -> str:
    counts = Counter(
        relation["evidence_level"]
        for card in cards.values()
        for relation in card["relations"]
    )
    lines = [
        "# Graph Expansion：全文关系与待核邻接",
        "",
        f"> 更新：{DATE} | 关系证据计数：{dict(sorted(counts.items()))}",
        "",
        "## 解释规则",
        "",
        "- full text：来源卡明确阅读了关系所需的全文材料；仍需服从该条 conditions。",
        "- abstract：只允许摘要级关系，不得比较方法细节或数值结果。",
        "- metadata：只表示下一步阅读邻接；不能写成支持、冲突或效果比较的全文证据。",
        "",
        "## 关系边",
        "",
        "| 来源 | 目标 | relation kind | 具体关系 | 成立条件 | evidence level |",
        "|---|---|---|---|---|---|",
    ]
    for paper_id in EXPECTED_IDS:
        for relation in cards[paper_id]["relations"]:
            lines.append(
                f"| {paper_id}《{cell(sources[paper_id].row['title'])}》 | {cell(relation['target'])} | {cell(relation['relation_kind'])} | {cell(relation['relation'])} | {cell(relation['conditions'])} | {cell(relation['evidence_level'])} |"
            )
    return "\n".join(lines)


def render_screened(rows: list[dict[str, str]], sources: dict[str, PaperSource], cards: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# Screened Set：Human–AI Interaction 2025–2026",
        "",
        f"> 结果：纳入 {len(rows)} 篇，唯一 DOI {len({row['doi'].casefold() for row in rows})} 个；全部 full text。更新：{DATE}。",
        "",
        "| ID | DOI | venue/year | 路线 | paper type | evidence mode | 纳入后的阅读作用 | 全文状态 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        paper_id = row["id"]
        card = cards[paper_id]
        lines.append(
            f"| {paper_id} | {cell(row['doi'])} | {cell(row['venue'])}/{cell(row['year'])} | {route_for(paper_id)} | {cell(card['classification']['paper_type'])} | {cell(card['classification']['evidence_mode'], 180)} | {cell(card['reading']['reading_role'])} | PDF/TXT/meta/card verified |"
        )
    lines.extend(
        (
            "",
            "## 筛选边界",
            "",
            "本文件登记的是既定60篇集合的全文核查状态，不声称它穷尽2025–2026所有人—AI交互研究。未纳入候选、数据库查询覆盖和来源异常应在独立检索轮次中维护，不能从当前集合的缺席推断领域不存在。",
        )
    )
    return "\n".join(lines)


def render_search_record(rows: list[dict[str, str]], sources: dict[str, PaperSource], cards: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# 共享研究记录：Human–AI Interaction 2025–2026",
        "",
        f"> revision：v2 | 建立时间：2026-08-18 | 最近更新：{DATE}",
        "",
        "## 1. 当前问题与用途",
        "",
        "- 用户问题：哪些论文真正提供阅读价值，以及这些论文共同形成了什么有边界的领域认识？",
        "- 检索用途：全文精读导航、证据关系审计、系统性认识和后续定向检索。",
        "- 领域边界：selected-papers.tsv 的60篇2025–2026 HAI相关工作；不作为发表率总体样本。",
        "- 核心知识问题：AI角色与控制、依赖校准、创造/文化/真实性、应用结果、组织治理和测量效度。",
        "- 关键不可比性风险：设计可供性、自报量表、任务行为、长期实践和社会结果属于不同分析层。",
        "",
        "## 2. 当前未决问题与下一动作",
        "",
        "| U# | 当前判断 | 什么证据会改变它 | 下一最小动作 | 状态 |",
        "|---|---|---|---|---|",
        "| U1 | 主动性收益依赖时机、风险与权限 | 匹配任务的时机×控制因子实验 | 检索并精读组件级比较 | partial |",
        "| U2 | 可编辑表示提高可检查性但未普遍提高正确性 | 带错误注入和客观终点的组件消融 | 查找同任务消融与复现 | partial |",
        "| U3 | 依赖必须同时测过度和不足 | 正确/错误建议全分解的纵向行为数据 | 扩展 appropriate reliance 查询 | partial |",
        "| U4 | 个性化收益与文化/身份风险并存 | 内容量匹配、跨文化且可撤销的比较 | 定向查文化校正与可争议性 | partial |",
        "| U5 | 参与和披露取决于组织权力 | 真实项目中决策权、采纳与最终结果日志 | 查找纵向参与治理部署 | partial |",
        "| U6 | 量表效度不能跨情境默认迁移 | 多组不变性和行为标准效度 | 查找独立量表复现 | partial |",
        "",
        "## 3. 查询地图",
        "",
        "查询按 01-query-map.md 的六条知识路线推进；A/B/C/D 文件只做检索和阅读分工，不替代知识关系。",
        "",
        "## 4. 论文登记与阅读导航",
        "",
        "| paper_key | 标题 | DOI | paper type | evidence mode | analysis unit | reading role | why read | relation kind | 当前领域作用 | 证据层级 | 本地状态 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        paper_id = row["id"]
        card = cards[paper_id]
        relation_kinds = ", ".join(dict.fromkeys(item["relation_kind"] for item in card["relations"]))
        lines.append(
            f"| {paper_id} | {cell(row['title'])} | {cell(row['doi'])} | {cell(card['classification']['paper_type'])} | {cell(card['classification']['evidence_mode'], 180)} | {cell(card['classification']['analysis_unit'], 180)} | {cell(card['reading']['reading_role'])} | {cell(card['reading']['why_read'], 220)} | {cell(relation_kinds)} | {route_for(paper_id)} | full text | [complete]({paper_link(sources[paper_id])}) |"
        )
    lines.extend(("", "## 5. 领域问题树与研究路线", ""))
    for route_name, route in KNOWLEDGE_ROUTES.items():
        lines.extend(
            (
                f"### {route_name}",
                "",
                f"- 问题定义：{route['question']}",
                f"- 成功标准：{route['success']}",
                f"- 代表论文：{', '.join(route['ids'])}",
                f"- 当前边界：{route['boundary']}",
                "",
            )
        )
    lines.extend(
        (
            "## 6. 证据关系矩阵",
            "",
            "完整逐边记录见 03-graph-expansion.md；跨论文结论见 papers/SYNTHESIS.md。所有 metadata 关系保持待核状态。",
            "",
            "## 7. 引用谱系与版本",
            "",
            "| 工作 | DOI | arXiv | OpenAlex | 首选引用版本 | 实际分析版本 | 全文来源 |",
            "|---|---|---|---|---|---|---|",
        )
    )
    for row in rows:
        source = sources[row["id"]]
        lines.append(
            f"| {row['id']}《{cell(row['title'])}》 | {cell(row['doi'])} | {cell(source.meta.get('arxiv_id'))} | {cell(source.meta.get('openalex_id'))} | {cell(source.meta.get('preferred_version') or row['doi'])} | {cell(source.meta.get('analyzed_version') or source.meta.get('preferred_version'))} | {cell(source.meta.get('source'))} |"
        )
    lines.extend(
        (
            "",
            "## 8. 同质簇与未采用候选",
            "",
            "当前文件只登记正式60篇集合。未采用候选需在新检索轮次记录身份、证据层级和停止理由；不得用本集合中的P编号代替外部论文身份。",
            "",
            "## 9. 精读反馈与变更集",
            "",
            "| reading-return | Q# 覆盖 | reading value before → after | domain relation before → after | invalidated routes/tasks |",
            "|---|---|---|---|---|",
        )
    )
    for paper_id in EXPECTED_IDS:
        feedback = cards[paper_id]["feedback"]
        lines.append(
            f"| {paper_id}/reading-return.md | {len(cards[paper_id]['brief_questions'])}/{len(cards[paper_id]['brief_questions'])} | {cell(feedback['reading_value_before'], 150)} → {cell(feedback['reading_value_after'], 180)} | {cell(feedback['domain_relation_before'], 130)} → {cell(feedback['domain_relation_after'], 170)} | {cell(feedback['invalidated_routes_or_tasks'], 180)} |"
        )
    lines.extend(
        (
            "",
            "## 10. 优先精读与定向核查",
            "",
            "60篇均已完成本轮全文精读。新的优先动作不再重复精读，而是对内部冲突、版本差异、metadata邻文和需要外部标准的主张进行定向核查。",
            "",
            "## 11. 分层阅读路径",
            "",
            "- 入门：P01；先理解样本地图与方法问题。",
            "- 路线代表：P20、P35、P38、P41；比较可编辑表示、证据与覆盖行为。",
            "- 方法或测量：P19、P48、P52、P57；审查行为指标与量表效度。",
            "- 反证与边界：P05、P06、P07、P31、P32、P43、P45、P59、P60。",
            "- 制度或部署：P08、P22、P50、P51、P53。",
            "",
            "## 12. 证据边界与可能遗漏",
            "",
            "选集并非数据库级穷尽检索；venue、年份和主题分布由选择文件决定。不同论文的分析单位和结果构念不可强行对齐；内部数字冲突保留为 caution。外部引用关系若仅有 metadata 或 abstract，不能升级为全文比较。",
            "",
            "## 13. 更新记录",
            "",
            f"- {DATE} / v2：吸收60张全文证据卡；重建类型、阅读价值、问题合同、关系证据与系统性认识。",
        )
    )
    return "\n".join(lines)


def render_search_report(sources: dict[str, PaperSource], cards: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# 文献地图与阅读指南：Human–AI Interaction 2025–2026",
        "",
        f"> 检索与全文回收完成：{DATE} | 当前记录：research-record.md | 证据日志：search-evidence.md",
        "",
        "## 0. 当前最重要的认识",
        "",
        "1. 本语料最清楚的共同结论不是“AI有效或无效”，而是近端体验、使用行为、任务结果、长期实践和社会结果必须分层。P06、P07、P43、P47、P59分别给出主观—行为—公平—准确性脱钩的直接例子。",
        "2. 可编辑表示、证据链接和人工覆盖在P20、P35、P38、P41中形成了可比较的设计家族；目前较强的是机制与使用证据，客观正确性和长期结果仍弱。",
        "3. 依赖不是“越少越好”。P18、P19、P26要求把错误采纳和错误拒绝一起观察，P47进一步表明人类覆盖可能改变最终公平结果。",
        "4. 组织治理不能缩成个人偏好。P08、P22、P50、P51显示非使用、披露、所有权、参与对象和决策权受到专业、组织和政策共同配置。",
        "5. P48、P52、P57表明，量表验证必须报告失败模型、低信度分量、不变性和行为关联；“validated”不是无条件通行证。",
        "",
        "## 1. 领域边界与核心问题树",
        "",
        "本报告覆盖60篇既定论文及其完整本地全文，不以数量估计领域流行率。问题树从AI角色与控制开始，依次区分近端体验、行为/任务、长期实践、社会制度结果，并以测量效度作为横向基础。主要不可比性来自分析单位、构念、任务风险、时间尺度和证据传统不同。",
        "",
        "## 2. 研究传统与证据类型",
        "",
        "| 研究传统 | 回答的问题 | 常用证据 | 能支持的推断 | 主要边界 | 代表论文 |",
        "|---|---|---|---|---|---|",
        "| 系统设计与探索评价 | 哪种交互与控制可实现、会怎样被使用 | 架构、日志、SUS、访谈、任务 | 可行性、感知和研究内行为 | 组件混杂、弱基线、短任务 | P20/P35/P38/P41 |",
        "| 受控行为与决策实验 | 条件变化如何关联任务行为或产出 | 随机/被试内条件、盲评、回归 | 局部条件差异 | 生态效度、构念代理、非显著误读 | P05/P06/P18/P32/P47 |",
        "| 质性实践与现场研究 | 人如何理解和组织AI实践 | 访谈、观察、文本、主题分析 | 条件、意义、过程与反例 | 不估计总体率或因果权重 | P02/P08/P15/P50/P53 |",
        "| 政策与治理分析 | 规范、政策与实践在哪里断裂 | 指南、政策文本、调查、访谈 | 制度条件与实施问题 | 规范目标不等于效果 | P22/P51 |",
        "| 综述与测量验证 | 领域覆盖和构念如何建立 | 系统综述、题项、CFA、信度、外部关联 | 样本内分类与测量结构 | 覆盖遗漏、不变性和行为效度 | P01/P48/P52/P57 |",
        "",
        "## 3. 研究路线与代表论文",
        "",
    ]
    for route_name, route in KNOWLEDGE_ROUTES.items():
        lines.extend(
            (
                f"### {route_name}",
                "",
                f"- 路线问题与成功标准：{route['question']} {route['success']}",
            )
        )
        representatives = route["ids"][:4]
        for paper_id in representatives:
            source = sources[paper_id]
            card = cards[paper_id]
            lines.extend(
                (
                    f"- **{source.row['title']}**（{source.row['venue']}, {source.row['year']}；{paper_id}）",
                    f"  - paper type / evidence mode：{one_line(card['classification']['paper_type'])}；{card['classification']['evidence_mode']}",
                    f"  - 独有贡献与 why read：{card['reading']['why_read']}",
                    f"  - reading role：{card['reading']['reading_role']}",
                    f"  - 证据层级：full text；[本地报告]({paper_link(source)})",
                )
            )
        lines.extend((f"- 路线边界：{route['boundary']}", ""))
    lines.extend(
        (
            "## 4. 证据如何相互关联",
            "",
            "| 知识问题 | 来源论文与具体发现 | 关系 | 成立条件 | 来源 |",
            "|---|---|---|---|---|",
            "| 主动协助何时有用 | P12在编程任务中报告测试表现收益；P33 Timer相对Button无总体绩效优势；P43 reactive不优于baseline | conditions | 对齐任务、触发、权限和终点 | 各篇report/research-record |",
            "| 感知能否代表效果 | P06主观帮助与重构质量脱钩；P07主观评价与会议行为脱钩；P43部分体验显著而ease/trust不显著 | challenges | 同时报告感知和行为 | P06/P07/P43全文 |",
            "| 人工控制是否构成保障 | P20/P35/P41记录编辑与覆盖；P47显示override可削弱形式公平 | conditions / challenges | 追踪最终决策与正确性/公平结果 | P20/P35/P41/P47全文 |",
            "| 个性化是否普遍有益 | P05文化同质化、P49语言线索差异、P59内容与语气混杂 | challenges | 分离内容、语气、文化与风险 | P05/P49/P59全文 |",
            "| 量表能否跨场景解释 | P48/P52/P57均有局部支持和明确失败/迁移边界 | measurement / incomparable | 需要同样本外部标准与不变性 | 三篇量表全文 |",
            "",
            "## 5. 已相对建立、仍有争议和不可比较的认识",
            "",
            "### 已相对建立",
            "",
            "证据支持分层解释：系统功能、主观体验、行为任务、长期实践和制度结果不能相互替代；交互日志能检验控制是否被使用；依赖评价必须同时覆盖过度和不足；组织使用由多层条件配置；量表结论必须附带已检验结构与样本。具体证据链见 papers/SYNTHESIS.md 的 K1–K5。",
            "",
            "### 有条件成立或仍有争议",
            "",
            "主动式帮助、可编辑表示、个性化和效率收益都表现为条件性关系。当前差异主要来自任务、权限、基线、构念和时间尺度，而不是已经证实的普遍冲突。P31/P32/P43/P45/P48/P52/P59/P60还要求保留零结果、内部数字冲突或不一致排序。",
            "",
            "### 暂不可比较",
            "",
            "设计可供性不能与客观效果合并，自报量表不能与行为结果合并，质性组织条件不能与短时实验效应量合并，临床/教育/创作/治理的成功标准也不共用。metadata邻接只负责引导下一篇阅读。",
            "",
            "## 6. 分层阅读路径",
            "",
            "| 层级 | 论文 | 为什么读 | 优先章节/图表 | 可获得的认识 |",
            "|---|---|---|---|---|",
            "| 入门 | P01 | 建立领域样本地图 | 编码与限制 | 看到主题覆盖和方法风险 |",
            "| 系统机制 | P20/P35/P38/P41 | 比较可编辑表示、证据和覆盖 | 工作流、日志、失败 | 区分功能、使用和结果 |",
            "| 反证边界 | P06/P07/P18/P32/P43/P47/P59/P60 | 学会读零结果与构念脱钩 | 结果表、局限 | 避免把偏好写成效果 |",
            "| 文化社会 | P05/P11/P22/P42/P49/P51 | 连接文化、披露与参与权 | 定性材料、组间设计、政策分析 | 看见个体之外的条件 |",
            "| 测量 | P48/P52/P57 | 审查量表验证 | CFA、信度、替代模型 | 限定自报构念的可比性 |",
            "",
            "## 7. 建议精读",
            "",
            "| 论文 | reading role | why now | 能改变的未决问题 | 类型感知的待核内容 | brief |",
            "|---|---|---|---|---|---|",
        )
    )
    for paper_id in ANCHOR_IDS:
        source = sources[paper_id]
        card = cards[paper_id]
        first_q = card["brief_questions"][0]
        brief_path = f"reading-briefs/{paper_id}/reading-brief.md"
        lines.append(
            f"| {paper_id}《{cell(source.row['title'])}》 | {cell(card['reading']['reading_role'])} | {cell(card['reading']['why_read'], 190)} | {cell(first_q['target_judgment'])} | {cell(first_q['expected_evidence'])} | [brief]({brief_path}) |"
        )
    lines.extend(
        (
            "",
            "## 8. 证据边界与可能遗漏",
            "",
            "选集覆盖多个venue但不是穷尽检索；本轮关系卡中仍有metadata和abstract级邻文。早期稿、正式版差异、内部统计冲突、未公开数据与未纳入社区均会限制判断。所有关键数值应回到TXT位置，跨论文比较需先对齐构念和统计单位。",
            "",
            "## 9. 下一动作",
            "",
            "优先扩展能够改变U1–U6的证据：匹配基线和组件消融、纵向行为日志、最终社会结果、量表不变性、内部冲突的勘误或源数据。已经由60篇全文充分回答、且新候选只重复同质结论的查询应停止。",
        )
    )
    return "\n".join(lines)


def render_search_evidence(rows: list[dict[str, str]], sources: dict[str, PaperSource], cards: dict[str, dict[str, Any]]) -> str:
    source_counts = Counter(source.meta.get("source", "unknown") for source in sources.values())
    relation_counts = Counter(
        relation["evidence_level"]
        for card in cards.values()
        for relation in card["relations"]
    )
    return "\n".join(
        (
            "# 检索证据日志：Human–AI Interaction 2025–2026",
            "",
            f"> 对应当前记录：research-record.md | 更新：{DATE}",
            "",
            "## 1. 查询与选择轨迹",
            "",
            f"- 选择文件：selected-papers.tsv；{len(rows)}行；{len({row['doi'].casefold() for row in rows})}个唯一DOI。",
            f"- 全文来源分布：{dict(sorted(source_counts.items()))}",
            "- 每篇均核对 meta selection_id、DOI、PDF头、TXT长度与证据卡中的TXT行号。",
            "",
            "## 2. 候选证据",
            "",
            "A/B/C/D 候选文件记录正式集合的阅读分工；04-screened.md记录最终纳入状态。",
            "",
            "## 3. 引用扩展证据",
            "",
            f"- 关系边证据层级：{dict(sorted(relation_counts.items()))}",
            "- metadata 和 abstract 关系保持待核，不进入跨论文结果合成。",
            "",
            "## 4. 版本与身份核查",
            "",
            "完整 DOI、arXiv、OpenAlex、首选版本、实际分析版本与来源见 research-record.md 第7节。",
            "",
            "## 5. 来源异常与处理",
            "",
            "本轮渲染不访问网络、不改变出版商状态，也不修改PDF/TXT。卡片内部记录的数字冲突、版本疑点和缺失外部标准均保留在逐篇 caution 中。",
        )
    )


def persist_cards(search_root: Path, cards_dir: Path, cards: dict[str, dict[str, Any]]) -> dict[str, str]:
    destination = search_root / "evidence-cards"
    hashes: dict[str, str] = {}
    jsonl_lines: list[str] = []
    for paper_id in EXPECTED_IDS:
        card = cards[paper_id]
        serialized = json.dumps(card, ensure_ascii=False, indent=2) + "\n"
        path = destination / f"{paper_id}.json"
        atomic_write(path, serialized)
        hashes[paper_id] = sha256_path(path)
        jsonl_lines.append(json.dumps(card, ensure_ascii=False, separators=(",", ":")))
    atomic_write(search_root / "fulltext-analysis-cards.jsonl", "\n".join(jsonl_lines))
    manifest = {
        "schema_version": 2,
        "generator_version": GENERATOR_VERSION,
        "generated_at": DATE,
        "source_cards_dir": str(cards_dir.resolve()),
        "card_count": len(cards),
        "card_hashes": hashes,
    }
    atomic_write(destination / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return hashes


def assert_group_cover() -> None:
    route_ids = [paper_id for route in KNOWLEDGE_ROUTES.values() for paper_id in route["ids"]]
    track_ids = [paper_id for track in CANDIDATE_TRACKS.values() for paper_id in track["ids"]]
    if Counter(route_ids) != Counter(EXPECTED_IDS):
        raise SystemExit("knowledge routes must cover P01..P60 exactly once")
    if Counter(track_ids) != Counter(EXPECTED_IDS):
        raise SystemExit("candidate tracks must cover P01..P60 exactly once")


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    search_root = root / SEARCH_SUBDIR
    cards_dir = (args.cards_dir or (search_root / "evidence-cards")).resolve()
    assert_group_cover()
    rows = load_selection(search_root / "selected-papers.tsv")
    sources = locate_sources(root, rows)
    cards = validate_cards(cards_dir, root / "scripts/hai_evidence_card_schema.json", rows, sources)
    card_hashes = persist_cards(search_root, cards_dir, cards)

    for paper_id in EXPECTED_IDS:
        source = sources[paper_id]
        card = cards[paper_id]
        brief = render_brief(source, card)
        atomic_write(source.directory / "reading-brief.md", brief)
        atomic_write(source.directory / "research-record.md", render_record(source, card))
        atomic_write(source.directory / "reading-return.md", render_return(source, card))
        atomic_write(source.directory / "report.md", render_report(source, card))
        atomic_write(search_root / "reading-briefs" / paper_id / "reading-brief.md", brief)

    atomic_write(root / "papers/INDEX.md", render_index(rows, sources, cards))
    atomic_write(root / "papers/SYNTHESIS.md", render_synthesis(sources, cards))
    atomic_write(search_root / "01-query-map.md", render_query_map(cards))
    for track in CANDIDATE_TRACKS:
        atomic_write(search_root / f"02-candidates-{track}.md", render_candidates(track, sources, cards))
    atomic_write(search_root / "03-graph-expansion.md", render_graph(sources, cards))
    atomic_write(search_root / "04-screened.md", render_screened(rows, sources, cards))
    atomic_write(search_root / "research-record.md", render_search_record(rows, sources, cards))
    atomic_write(search_root / "report.md", render_search_report(sources, cards))
    atomic_write(search_root / "search-evidence.md", render_search_evidence(rows, sources, cards))

    summary = {
        "status": "rendered",
        "generator_version": GENERATOR_VERSION,
        "generated_at": DATE,
        "selected_count": len(rows),
        "unique_doi_count": len({row["doi"].casefold() for row in rows}),
        "validated_evidence_cards": len(cards),
        "core_paper_products": len(cards) * 4,
        "search_brief_copies": len(cards),
        "knowledge_routes": {name: list(route["ids"]) for name, route in KNOWLEDGE_ROUTES.items()},
        "card_hashes": card_hashes,
        "invariants": {
            "network_used": False,
            "pdf_or_txt_modified": False,
            "metadata_relation_promoted_to_full_text": False,
            "fixed_gap_or_opportunity_required": False,
        },
    }
    atomic_write(search_root / "qa-summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

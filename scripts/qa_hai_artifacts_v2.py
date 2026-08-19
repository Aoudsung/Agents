#!/usr/bin/env python3
"""Structural and semantic QA for Search/Analysis paper artifacts.

The validator is read-only. It derives corpus size from the selection file,
treats old 01-04 files as legacy inputs, checks the brief/return contract,
rejects universal-analysis phrases, and detects repeated substantive sentences.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


CORE_PAPER_FILES = {
    "reading-brief.md",
    "research-record.md",
    "reading-return.md",
    "report.md",
}
VALID_STATUSES = {
    "answered",
    "partial",
    "undetermined",
    "not-applicable",
}
BRIEF_FIELDS = {
    "paper_type_hypothesis",
    "study_design_hypothesis",
    "evidence_mode_hypothesis",
    "analysis_unit_hypothesis",
    "classification_basis",
    "reading_role",
    "reading_value_hypothesis",
    "relation_kind",
}
BANNED_PHRASES = {
    "执行链可重建为：用户/情境输入 → AI 生成建议、解释、表示或行动",
    "全文确认机制进入执行链",
    "论文实际测量的是任务结果、行为轨迹、量表或主题",
    "核心机制改善/改变论文内结果",
    "第二类证据支持机制解释",
    "可推广为一般规律",
    "测量 + 因果/组件实验",
    "只有行为、任务和目标结果共同改善时才支持强外推",
    "推理跨度最大：把当前代理扩展为长期、跨域效果",
}
REPORT_VALUE_FIELDS = {
    "reading_role",
    "best_sections",
    "use_for",
    "do_not_use_for",
}
RETURN_VALUE_FIELDS = {
    "classification_evidence",
    "reading_role",
    "why_read",
    "best_sections",
    "use_for",
    "do_not_use_for",
}
REPORT_HEADINGS = {
    "为什么值得读",
    "作者在回答什么",
    "论文怎样回答",
    "核心发现",
    "论文贡献",
    "证据有多强",
    "如何阅读、引用与避免误用",
    "对精读交接问题的回答",
}
RECORD_FIELDS = {
    "paper_type",
    "study_design",
    "evidence_mode",
    "analysis_unit",
    "classification_evidence",
}
RETURN_MARKERS = {
    "reading_value_before",
    "reading_value_after",
    "domain_relation_before",
    "domain_relation_after",
}
SYNTHESIS_HEADINGS = {
    "领域边界与核心问题树",
    "研究传统与路线",
    "跨论文证据关系矩阵",
    "已相对建立的认识",
    "有条件成立或仍有争议的认识",
    "暂不可比较的方向",
    "分层阅读路径",
}
LEGACY_SYNTHESIS_HEADINGS = {
    "反复出现的未决变量",
    "设计空间空缺",
    "可组合的研究程序",
}
Q_HEADING_RE = re.compile(
    r"^###\s+(Q\d+)\s*(?:[｜|:：]\s*|\s+)(.+?)\s*$",
    re.MULTILINE,
)
UNRESOLVED_RE = re.compile(r"<[^>\n]{2,100}>|\bTODO\b|待补")
SOURCE_LOCATION_RE = re.compile(
    r"TXT\s*[:：]\s*\d+|第\s*\d+\s*页|§\s*\d+|"
    r"Table\s*\d+|Fig(?:ure)?\s*\d+|表\s*\d+|图\s*\d+|附录\s*[A-Z\d]",
    re.IGNORECASE,
)
Q_STATUS_RE = re.compile(
    r"^\s*-\s*status\s*[：:]\s*([a-z-]+)",
    re.MULTILINE | re.IGNORECASE,
)
PLACEHOLDER_ONLY_RE = re.compile(
    r"^(?:[-—–]|n/?a|none|unknown|待定|待补|未填写|<[^>]+>)$",
    re.IGNORECASE,
)
INDEX_COLUMN_ALIASES = {
    "research_type": {"研究类型", "论文类型", "paper type", "paper_type"},
    "reading_value": {"阅读价值", "why read", "why_read"},
    "field_role": {"领域作用", "领域角色", "field role", "reading role"},
}
REPEAT_EXEMPT_SNIPPETS = {
    "详细证据见 research-record.md",
    "Search 变更集见 reading-return.md",
    "状态使用 answered / partial / undetermined / not-applicable",
    "相关文件：01-reconstruction.md",
}
MIN_ARTIFACT_BYTES = 300
MIN_TEXT_BYTES = 5_000
MAX_REPORTED_REPEATS = 20


@dataclass
class QAResult:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, object] = field(default_factory=dict)

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/Users/aoudsung/Documents/AcdamicAgents"),
    )
    parser.add_argument(
        "--paper-subdir",
        default="papers/human-ai-interaction-2025-2026",
    )
    parser.add_argument(
        "--search-subdir",
        default="searches/2026-08-18-human-ai-interaction-2025-2026",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def field_value(text: str, field: str) -> str | None:
    pattern = re.compile(
        rf"^\s*-\s*{re.escape(field)}\s*[：:]\s*(.+?)\s*$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def normalize_inline(value: str) -> str:
    value = re.sub(r"[*_]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_questions(
    text: str,
    require_status: bool = False,
) -> dict[str, dict[str, str | None]]:
    matches = list(Q_HEADING_RE.finditer(text))
    result: dict[str, dict[str, str | None]] = {}
    for index, match in enumerate(matches):
        qid, question = match.group(1), normalize_inline(match.group(2))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end]
        status_match = Q_STATUS_RE.search(block)
        status = status_match.group(1).lower() if status_match else None
        if require_status and status not in VALID_STATUSES:
            status = None
        result[qid] = {"question": question, "status": status}
    return result


def question_entries(text: str) -> list[tuple[str, str, str | None]]:
    """Return Q# entries in source order without hiding duplicate IDs."""
    matches = list(Q_HEADING_RE.finditer(text))
    entries: list[tuple[str, str, str | None]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        status_match = Q_STATUS_RE.search(text[start:end])
        status = status_match.group(1).lower() if status_match else None
        entries.append(
            (
                match.group(1),
                normalize_inline(match.group(2)),
                status,
            )
        )
    return entries


def resolved_field(text: str, name: str) -> bool:
    value = field_value(text, name)
    if value is None:
        return False
    normalized = normalize_inline(value).strip(chr(96))
    return bool(normalized) and PLACEHOLDER_ONLY_RE.fullmatch(normalized) is None


def markdown_headings(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            heading = re.sub(r"^\d+(?:\.\d+)*[.、]?\s*", "", match.group(1))
            headings.append(normalize_inline(heading))
    return headings


def unresolved_markers(text: str) -> list[str]:
    return sorted(set(match.group(0) for match in UNRESOLVED_RE.finditer(text)))


def banned_phrases(text: str) -> list[str]:
    return sorted(phrase for phrase in BANNED_PHRASES if phrase in text)


def source_locations(text: str) -> list[str]:
    return [match.group(0) for match in SOURCE_LOCATION_RE.finditer(text)]


def validate_question_contract(
    paper_id: str,
    brief_text: str,
    return_text: str,
    result: QAResult,
) -> None:
    brief = question_entries(brief_text)
    returned = question_entries(return_text)

    if not brief:
        result.fail(f"{paper_id}: reading brief has no structured Q# questions")
        return
    brief_ids = [item[0] for item in brief]
    return_ids = [item[0] for item in returned]
    if len(set(brief_ids)) != len(brief_ids):
        result.fail(f"{paper_id}: reading brief contains duplicate Q# IDs")
    if len(set(return_ids)) != len(return_ids):
        result.fail(f"{paper_id}: reading return contains duplicate Q# IDs")
    if brief_ids != return_ids:
        result.fail(
            f"{paper_id}: brief/return Q# sequence mismatch "
            f"(brief={brief_ids}, return={return_ids})"
        )
        return

    changed = [
        qid
        for (qid, question, _), (_, returned_question, _) in zip(brief, returned)
        if question != returned_question
    ]
    if changed:
        result.fail(
            f"{paper_id}: reading return changed question text for "
            f"{', '.join(changed)}"
        )

    invalid_statuses = [
        f"{qid}={status or 'missing'}"
        for qid, _, status in returned
        if status not in VALID_STATUSES
    ]
    if invalid_statuses:
        result.fail(
            f"{paper_id}: invalid/missing return status: "
            f"{', '.join(invalid_statuses)}"
        )


def validate_brief(paper_id: str, text: str, result: QAResult) -> None:
    missing = sorted(name for name in BRIEF_FIELDS if not resolved_field(text, name))
    if missing:
        result.fail(
            f"{paper_id}: reading brief missing/unresolved fields: "
            f"{', '.join(missing)}"
        )
    markers = unresolved_markers(text)
    if markers:
        result.fail(
            f"{paper_id}: unresolved markers in reading brief: "
            f"{', '.join(markers[:5])}"
        )
    phrases = banned_phrases(text)
    if phrases:
        result.fail(
            f"{paper_id}: universal-analysis assumptions in reading brief: "
            f"{'; '.join(phrases)}"
        )


def validate_record(paper_id: str, text: str, result: QAResult) -> None:
    required = RECORD_FIELDS | {
        "reading_role",
        "why_read",
        "best_sections",
        "use_for",
        "do_not_use_for",
    }
    missing = sorted(name for name in required if not resolved_field(text, name))
    if missing:
        result.fail(
            f"{paper_id}: evidence ledger missing/unresolved fields: "
            f"{', '.join(missing)}"
        )
    markers = unresolved_markers(text)
    if markers:
        result.fail(
            f"{paper_id}: unresolved markers in evidence ledger: "
            f"{', '.join(markers[:5])}"
        )
    phrases = banned_phrases(text)
    if phrases:
        result.fail(
            f"{paper_id}: universal-analysis claims in evidence ledger: "
            f"{'; '.join(phrases)}"
        )
    if not re.search(r"^###\s+C\d+\s*[｜|:：]", text, re.MULTILINE):
        result.fail(f"{paper_id}: evidence ledger has no paper-specific Claim card")
    if not source_locations(text):
        result.fail(f"{paper_id}: evidence ledger has no source location")


def validate_report(paper_id: str, text: str, result: QAResult) -> None:
    headings = markdown_headings(text)
    missing_headings = sorted(
        expected
        for expected in REPORT_HEADINGS
        if not any(expected in actual for actual in headings)
    )
    if missing_headings:
        result.fail(
            f"{paper_id}: reader report missing headings: "
            f"{', '.join(missing_headings)}"
        )
    missing_fields = sorted(
        name for name in REPORT_VALUE_FIELDS if not resolved_field(text, name)
    )
    if missing_fields:
        result.fail(
            f"{paper_id}: reader report missing reading-value fields: "
            f"{', '.join(missing_fields)}"
        )
    markers = unresolved_markers(text)
    if markers:
        result.fail(
            f"{paper_id}: unresolved markers in reader report: "
            f"{', '.join(markers[:5])}"
        )
    phrases = banned_phrases(text)
    if phrases:
        result.fail(
            f"{paper_id}: universal-analysis prose in reader report: "
            f"{'; '.join(phrases)}"
        )
    if not source_locations(text):
        result.fail(f"{paper_id}: reader report has no source location")


def validate_return(paper_id: str, text: str, result: QAResult) -> None:
    required = RETURN_MARKERS | RETURN_VALUE_FIELDS
    missing = sorted(name for name in required if not resolved_field(text, name))
    if missing:
        result.fail(
            f"{paper_id}: reading return missing/unresolved fields: "
            f"{', '.join(missing)}"
        )
    markers = unresolved_markers(text)
    if markers:
        result.fail(
            f"{paper_id}: unresolved markers in reading return: "
            f"{', '.join(markers[:5])}"
        )
    phrases = banned_phrases(text)
    if phrases:
        result.fail(
            f"{paper_id}: universal-analysis prose in reading return: "
            f"{'; '.join(phrases)}"
        )
    if not source_locations(text):
        result.fail(f"{paper_id}: reading return has no source location")


def _is_substantive(sentence: str) -> bool:
    if any(snippet in sentence for snippet in REPEAT_EXEMPT_SNIPPETS):
        return False
    compact = re.sub(r"\s+", "", sentence)
    han_count = len(re.findall(r"[\u3400-\u9fff]", sentence))
    word_count = len(re.findall(r"[A-Za-z][A-Za-z0-9'-]*", sentence))
    return len(compact) >= 45 and (han_count >= 24 or word_count >= 10)


def substantive_sentences(text: str) -> set[str]:
    """Extract long prose sentences while excluding document scaffolding."""
    sentences: set[str] = set()
    in_fence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith(chr(96) * 3):
            in_fence = not in_fence
            continue
        if (
            in_fence
            or not line
            or line.startswith("#")
            or line.startswith("|")
            or line.startswith(">")
            or line == "---"
        ):
            continue
        line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)
        line = re.sub(r"!\[[^\]]*]\([^)]*\)", "", line)
        line = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", line)
        line = re.sub(r"[*_~]", "", line)
        line = line.replace(chr(96), "")
        for part in re.split(r"(?<=[。！？!?])\s*|(?<=[.])\s+(?=[A-Z])", line):
            normalized = re.sub(r"\s+", " ", part).strip(" -—–;；")
            if _is_substantive(normalized):
                sentences.add(normalized)
    return sentences


def repeated_substantive_sentences(
    reports: dict[str, str],
    minimum_reports: int = 3,
) -> list[tuple[str, list[str]]]:
    occurrences: dict[str, list[str]] = {}
    for paper_id, text in reports.items():
        for sentence in substantive_sentences(text):
            occurrences.setdefault(sentence, []).append(paper_id)
    repeated = [
        (sentence, sorted(paper_ids))
        for sentence, paper_ids in occurrences.items()
        if len(set(paper_ids)) >= minimum_reports
    ]
    repeated.sort(key=lambda item: (-len(item[1]), item[0]))
    return repeated


def validate_index(
    path: Path,
    selected_ids: list[str],
    result: QAResult,
) -> None:
    if not path.is_file():
        result.fail("papers/INDEX.md is missing")
        return
    text = read_text(path)
    table_lines = [line.strip() for line in text.splitlines() if line.lstrip().startswith("|")]
    if not table_lines:
        result.fail("papers/INDEX.md has no Markdown table")
        return
    header = [normalize_inline(cell).casefold() for cell in table_lines[0].strip("|").split("|")]
    for semantic_name, aliases in INDEX_COLUMN_ALIASES.items():
        folded_aliases = {alias.casefold() for alias in aliases}
        if not any(cell in folded_aliases for cell in header):
            result.fail(
                f"papers/INDEX.md missing {semantic_name} column "
                f"(accepted: {', '.join(sorted(aliases))})"
            )
    row_ids = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and re.fullmatch(r"P\d+", cells[0], re.IGNORECASE):
            row_ids.append(cells[0].upper())
    expected = Counter(item.upper() for item in selected_ids)
    actual = Counter(row_ids)
    if expected != actual:
        missing = sorted((expected - actual).elements())
        extra = sorted((actual - expected).elements())
        result.fail(
            "papers/INDEX.md selection mismatch "
            f"(missing={missing}, extra={extra})"
        )
    markers = unresolved_markers(text)
    if markers:
        result.fail(
            "papers/INDEX.md contains unresolved markers: "
            f"{', '.join(markers[:5])}"
        )


def validate_synthesis(path: Path, result: QAResult) -> None:
    if not path.is_file():
        result.fail("papers/SYNTHESIS.md is missing")
        return
    text = read_text(path)
    headings = markdown_headings(text)
    missing = sorted(
        expected
        for expected in SYNTHESIS_HEADINGS
        if not any(expected in actual for actual in headings)
    )
    if missing:
        result.fail(
            "papers/SYNTHESIS.md missing knowledge-first headings: "
            f"{', '.join(missing)}"
        )
    legacy = sorted(
        expected
        for expected in LEGACY_SYNTHESIS_HEADINGS
        if any(expected in actual for actual in headings)
    )
    if legacy:
        result.fail(
            "papers/SYNTHESIS.md retains agenda-first legacy headings: "
            f"{', '.join(legacy)}"
        )
    markers = unresolved_markers(text)
    if markers:
        result.fail(
            "papers/SYNTHESIS.md contains unresolved markers: "
            f"{', '.join(markers[:5])}"
        )
    phrases = banned_phrases(text)
    if phrases:
        result.fail(
            "papers/SYNTHESIS.md repeats universal-analysis claims: "
            f"{'; '.join(phrases)}"
        )


def validate_legacy_builder(path: Path, result: QAResult) -> None:
    if not path.is_file():
        result.fail("legacy builder is missing; provenance/fail-closed status cannot be checked")
        return
    try:
        module = ast.parse(read_text(path), filename=str(path))
    except SyntaxError as exc:
        result.fail(f"legacy builder cannot be parsed: {exc}")
        return
    main_functions = [
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "main"
    ]
    if len(main_functions) != 1:
        result.fail("legacy builder must expose exactly one fail-closed main()")
        return
    body = main_functions[0].body
    if len(body) != 1 or not isinstance(body[0], ast.Raise):
        result.fail("legacy builder main() is not fail-closed")
        return
    source = ast.get_source_segment(read_text(path), body[0]) or ""
    required = (
        "disabled unsafe legacy generator",
        "universal interaction",
        "fixed C1-C3/G1/O1",
        "static synthesis",
    )
    if any(marker not in source for marker in required):
        result.fail("legacy builder fail-closed reason is incomplete")


def load_selection(path: Path, result: QAResult) -> list[dict[str, str]]:
    if not path.is_file():
        result.fail(f"selection file is missing: {path}")
        return []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            rows = list(reader)
            columns = set(reader.fieldnames or [])
    except (OSError, csv.Error) as exc:
        result.fail(f"cannot read selection file: {exc}")
        return []
    required_columns = {"id", "title", "doi", "year", "venue"}
    missing_columns = sorted(required_columns - columns)
    if missing_columns:
        result.fail(
            "selection file missing columns: "
            f"{', '.join(missing_columns)}"
        )
        return []
    if not rows:
        result.fail("selection file contains no papers")
        return []

    ids = [row["id"].strip().upper() for row in rows]
    invalid_ids = sorted(item for item in ids if not re.fullmatch(r"P\d+", item))
    if invalid_ids:
        result.fail(f"selection contains invalid IDs: {invalid_ids}")
    duplicate_ids = sorted(item for item, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        result.fail(f"selection contains duplicate IDs: {duplicate_ids}")
    dois = [row["doi"].strip().casefold() for row in rows if row["doi"].strip()]
    duplicate_dois = sorted(item for item, count in Counter(dois).items() if count > 1)
    if duplicate_dois:
        result.fail(f"selection contains duplicate DOIs: {duplicate_dois}")
    for row, paper_id in zip(rows, ids):
        row["id"] = paper_id
        if not row["title"].strip():
            result.fail(f"{paper_id}: selection title is empty")
    return rows


def validate_paper_source(
    row: dict[str, str],
    paper_root: Path,
    result: QAResult,
) -> tuple[Path | None, dict[str, object] | None]:
    paper_id = row["id"]
    matches = list(paper_root.glob(f"{paper_id.lower()}-*/meta.json"))
    if len(matches) != 1:
        result.fail(f"{paper_id}: expected one paper directory/meta.json, found {len(matches)}")
        return None, None
    meta_path = matches[0]
    directory = meta_path.parent
    try:
        meta = json.loads(read_text(meta_path))
    except (OSError, json.JSONDecodeError) as exc:
        result.fail(f"{paper_id}: invalid meta.json: {exc}")
        return directory, None
    if not isinstance(meta, dict):
        result.fail(f"{paper_id}: meta.json is not an object")
        return directory, None

    if str(meta.get("selection_id", "")).upper() != paper_id:
        result.fail(f"{paper_id}: meta selection_id mismatch")
    selected_doi = row["doi"].strip().casefold()
    meta_doi = str(meta.get("doi") or "").strip().casefold()
    if selected_doi and selected_doi != meta_doi:
        result.fail(f"{paper_id}: meta DOI mismatch")
    if not meta.get("ok") or meta.get("evidence_level") != "full text":
        result.fail(f"{paper_id}: source is not verified full text")
    if normalize_inline(str(meta.get("title") or "")).casefold() != normalize_inline(
        row["title"]
    ).casefold():
        result.warn(
            f"{paper_id}: meta title differs from selection title; DOI remains authoritative"
        )

    pdf_path = directory / f"{directory.name}.pdf"
    txt_path = directory / f"{directory.name}.txt"
    try:
        if not pdf_path.is_file() or pdf_path.read_bytes()[:5] != b"%PDF-":
            result.fail(f"{paper_id}: canonical PDF missing or invalid")
    except OSError as exc:
        result.fail(f"{paper_id}: cannot inspect canonical PDF: {exc}")
    try:
        if not txt_path.is_file() or txt_path.stat().st_size < MIN_TEXT_BYTES:
            result.fail(f"{paper_id}: canonical TXT missing or shorter than {MIN_TEXT_BYTES} bytes")
    except OSError as exc:
        result.fail(f"{paper_id}: cannot inspect canonical TXT: {exc}")
    return directory, meta


def validate_search_report(path: Path, result: QAResult) -> None:
    if not path.is_file():
        result.fail("search report.md is missing")
        return
    text = read_text(path)
    expected = {
        "当前最重要的认识",
        "领域边界与核心问题树",
        "研究传统与证据类型",
        "研究路线与代表论文",
        "证据如何相互关联",
        "已相对建立、仍有争议和不可比较的认识",
        "分层阅读路径",
        "建议精读",
    }
    headings = markdown_headings(text)
    missing = sorted(
        item for item in expected if not any(item in heading for heading in headings)
    )
    if missing:
        result.fail(
            "search report.md missing knowledge-first headings: "
            f"{', '.join(missing)}"
        )
    markers = unresolved_markers(text)
    if markers:
        result.fail(
            "search report.md contains unresolved markers: "
            f"{', '.join(markers[:5])}"
        )


def run_qa(root: Path, paper_subdir: str, search_subdir: str) -> QAResult:
    result = QAResult()
    paper_root = root / paper_subdir
    search_root = root / search_subdir
    rows = load_selection(search_root / "selected-papers.tsv", result)
    result.stats["selected_papers"] = len(rows)
    if not rows:
        validate_legacy_builder(root / "scripts/build_hai_analysis_artifacts.py", result)
        return result

    reports: dict[str, str] = {}
    sources: Counter[str] = Counter()
    years: Counter[str] = Counter()
    venues: Counter[str] = Counter()
    valid_core_files = 0
    for row in rows:
        paper_id = row["id"]
        years[row["year"]] += 1
        venues[row["venue"]] += 1
        directory, meta = validate_paper_source(row, paper_root, result)
        if meta is not None:
            sources[str(meta.get("source") or "unknown")] += 1
        if directory is None:
            continue

        texts: dict[str, str] = {}
        for filename in sorted(CORE_PAPER_FILES):
            path = directory / filename
            try:
                if not path.is_file() or path.stat().st_size < MIN_ARTIFACT_BYTES:
                    result.fail(
                        f"{paper_id}: missing/short core product {filename}"
                    )
                    continue
                texts[filename] = read_text(path)
                valid_core_files += 1
            except OSError as exc:
                result.fail(f"{paper_id}: cannot read {filename}: {exc}")

        brief_text = texts.get("reading-brief.md")
        record_text = texts.get("research-record.md")
        return_text = texts.get("reading-return.md")
        report_text = texts.get("report.md")
        if brief_text is not None:
            validate_brief(paper_id, brief_text, result)
        if record_text is not None:
            validate_record(paper_id, record_text, result)
        if return_text is not None:
            validate_return(paper_id, return_text, result)
        if brief_text is not None and return_text is not None:
            validate_question_contract(paper_id, brief_text, return_text, result)
        if report_text is not None:
            validate_report(paper_id, report_text, result)
            reports[paper_id] = report_text

        search_brief_path = search_root / "reading-briefs" / paper_id / "reading-brief.md"
        if not search_brief_path.is_file():
            result.fail(f"{paper_id}: Search reading brief is missing")
        else:
            search_brief = read_text(search_brief_path)
            validate_brief(f"{paper_id} Search copy", search_brief, result)
            if brief_text is not None:
                local_contract = [
                    (qid, question) for qid, question, _ in question_entries(brief_text)
                ]
                search_contract = [
                    (qid, question) for qid, question, _ in question_entries(search_brief)
                ]
                if local_contract != search_contract:
                    result.fail(
                        f"{paper_id}: local and Search reading-brief Q# contracts differ"
                    )

    repeated = repeated_substantive_sentences(reports)
    for sentence, paper_ids in repeated[:MAX_REPORTED_REPEATS]:
        preview = sentence if len(sentence) <= 140 else sentence[:137] + "..."
        result.fail(
            f"repeated substantive report sentence in {len(paper_ids)} papers "
            f"({', '.join(paper_ids[:8])}): {preview}"
        )
    if len(repeated) > MAX_REPORTED_REPEATS:
        result.fail(
            f"{len(repeated) - MAX_REPORTED_REPEATS} additional repeated "
            "substantive report sentences omitted"
        )

    validate_index(root / "papers/INDEX.md", [row["id"] for row in rows], result)
    validate_synthesis(root / "papers/SYNTHESIS.md", result)
    validate_search_report(search_root / "report.md", result)
    validate_legacy_builder(root / "scripts/build_hai_analysis_artifacts.py", result)

    result.stats.update(
        {
            "valid_core_products": valid_core_files,
            "expected_core_products": len(rows) * len(CORE_PAPER_FILES),
            "reports_checked_for_repetition": len(reports),
            "repeated_substantive_sentences": len(repeated),
            "unique_dois": len(
                {
                    row["doi"].strip().casefold()
                    for row in rows
                    if row["doi"].strip()
                }
            ),
            "years": dict(sorted(years.items())),
            "venues": dict(sorted(venues.items())),
            "sources": dict(sorted(sources.items())),
        }
    )
    return result


def main() -> None:
    args = parse_args()
    result = run_qa(args.root.resolve(), args.paper_subdir, args.search_subdir)
    payload = {
        "status": "failed" if result.failures else "ok",
        **result.stats,
        "failure_count": len(result.failures),
        "warning_count": len(result.warnings),
        "failures": result.failures,
        "warnings": result.warnings,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result.failures else 0)


if __name__ == "__main__":
    main()

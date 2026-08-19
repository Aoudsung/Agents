from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from .model import endpoint_ref, nonempty, relative_path, safe_name, yaml_list
from .storage import load_cards, read_json, read_jsonl


def accepted_relations(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in relations if row.get("status") == "accepted"]


def render_map_markdown(data: dict[str, Any], cards: dict[str, dict[str, Any]], relations: list[dict[str, Any]]) -> str:
    lines = [f"# {data.get('title') or 'Paper Map'}", ""]
    scope = data.get("scope", {})
    if isinstance(scope, dict) and (scope.get("included") or scope.get("excluded")):
        lines += [
            "覆盖：" + (", ".join(scope.get("included", [])) or "未声明"),
            "排除：" + (", ".join(scope.get("excluded", [])) or "未声明"), "",
        ]
    lines += ["## 1. 核心知识问题", ""]
    questions = data.get("knowledge_questions", [])
    lines += [f"- **{q.get('id', '?')}** {q.get('text', '')}" for q in questions] or ["尚未建立知识问题。"]

    lines += ["", "## 2. 研究路线", ""]
    routes = data.get("research_routes", [])
    if routes:
        for route in routes:
            papers = ", ".join(route.get("representative_papers", [])) or "尚无代表论文"
            lines += [f"### {route.get('name') or route.get('id', 'Route')}", "", route.get("description", ""), "", f"代表论文：{papers}", ""]
    else:
        lines.append("尚未建立研究路线。")

    lines += ["", "## 3. 已建立、条件成立与争议认识", ""]
    conclusions = data.get("conclusions", [])
    if conclusions:
        for item in conclusions:
            relations_text = ", ".join(item.get("supporting_relations", [])) or "无"
            lines += [
                f"### {item.get('id', '?')}｜{item.get('status', 'unknown')}", "",
                item.get("text", ""), "",
                f"- 适用范围：{item.get('scope', '')}",
                f"- 关系依据：{relations_text}",
                f"- 剩余不确定性：{item.get('residual_uncertainty', '')}", "",
            ]
    else:
        lines.append("当前没有由 accepted relations 支撑的领域结论。")

    lines += ["", "## 4. Canonical relations", ""]
    rows = accepted_relations(relations)
    if rows:
        lines += ["| ID | 来源 | 关系 | 目标 | 可比性 | 理由 |", "|---|---|---|---|---|---|"]
        for row in rows:
            reason = str(row.get("rationale", "")).replace("|", "\\|")
            lines.append(
                f"| {row.get('relation_id', '')} | {endpoint_ref(row.get('source'))} | "
                f"{row.get('relation_type', '')} | {endpoint_ref(row.get('target'))} | "
                f"{row.get('comparability', {}).get('decision', '')} | {reason} |"
            )
    else:
        lines.append("尚无 accepted relations。")

    lines += ["", "## 5. 分层阅读路径", ""]
    path = data.get("reading_path", [])
    if path:
        lines += ["| 层级 | 论文 | 为什么读 |", "|---|---|---|"]
        for item in path:
            reason = str(item.get("reason", "")).replace("|", "\\|")
            lines.append(f"| {item.get('level', '')} | {', '.join(item.get('papers', []))} | {reason} |")
    else:
        lines.append("尚未建立阅读路径。")
    lines += ["", "## 6. 语料覆盖", "", f"当前 paper cards：{len(cards)}；accepted relations：{len(rows)}。", ""]
    return "\n".join(lines)


def render_index(cards: dict[str, dict[str, Any]], origins: dict[str, Path], root: Path) -> str:
    lines = ["# Papers Knowledge Index", "", "| ID | 标题 | 研究类型 | reading role | why read | card |", "|---|---|---|---|---|---|"]
    for paper_id, card in sorted(cards.items()):
        identity, classification = card.get("identity", {}), card.get("classification", {})
        contribution, reading = card.get("contribution", {}), card.get("reading", {})
        lines.append(
            "| {pid} | {title} | {types} | {role} | {why} | `{path}` |".format(
                pid=paper_id,
                title=str(identity.get("title", "")).replace("|", "\\|"),
                types=", ".join(classification.get("paper_type", [])),
                role=str(contribution.get("reading_role", "")).replace("|", "\\|"),
                why=str(reading.get("why_read", "")).replace("|", "\\|"),
                path=relative_path(origins[paper_id], root),
            )
        )
    if not cards:
        lines.append("| — | 尚无 paper cards | — | — | — | — |")
    return "\n".join(lines) + "\n"


def reset_generated_vault(vault: Path) -> None:
    for name in ("00-Overview", "10-Papers", "20-Questions", "30-Routes", "40-Controversies"):
        path = vault / name
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
    (vault / "90-Human-Notes").mkdir(parents=True, exist_ok=True)


def render_vault(root: Path, data: dict[str, Any], cards: dict[str, dict[str, Any]], relations: list[dict[str, Any]], map_md: str) -> None:
    vault = root / "knowledge-vault"
    reset_generated_vault(vault)
    (vault / "00-Overview/Field Map.md").write_text(map_md, encoding="utf-8")
    by_paper: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in accepted_relations(relations):
        for side in ("source", "target"):
            paper_id = relation.get(side, {}).get("paper_id")
            if nonempty(paper_id):
                by_paper[paper_id].append(relation)

    for paper_id, card in sorted(cards.items()):
        identity, classification = card.get("identity", {}), card.get("classification", {})
        contribution, reading = card.get("contribution", {}), card.get("reading", {})
        lines = [
            "---", "type: paper", f"paper_id: {paper_id}", f"year: {identity.get('year', '')}",
            f"paper_type: {yaml_list(classification.get('paper_type', []))}",
            f"concepts: {yaml_list(card.get('concepts', []))}",
            f"reading_role: {contribution.get('reading_role', '')}", "---", "",
            f"# {identity.get('title', paper_id)}", "", "## 为什么读", "", reading.get("why_read", ""), "",
            "## 论文建立了什么", "",
        ]
        units = card.get("knowledge_units", [])
        lines += [f"- **{paper_id}:{u.get('id')}** [{u.get('kind')}] {u.get('text')}" for u in units] or ["尚无可供跨论文比较的知识单元。"]
        lines += ["", "## Canonical relations", ""]
        lines += [
            f"- **{r.get('relation_id')}** `{r.get('relation_type')}` {endpoint_ref(r.get('source'))} → {endpoint_ref(r.get('target'))}"
            for r in by_paper.get(paper_id, [])
        ] or ["尚无 accepted relations。"]
        (vault / "10-Papers" / f"{safe_name(paper_id)}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    for q in data.get("knowledge_questions", []):
        qid = q.get("id", "Q")
        text = f"---\ntype: knowledge-question\nquestion_id: {qid}\n---\n\n# {q.get('text', qid)}\n\n{q.get('description', '')}\n"
        (vault / "20-Questions" / f"{safe_name(qid)}.md").write_text(text, encoding="utf-8")
    for route in data.get("research_routes", []):
        rid = route.get("id", "ROUTE")
        papers = "\n".join(f"- [[{safe_name(pid)}]]" for pid in route.get("representative_papers", [])) or "- 尚无代表论文"
        text = f"---\ntype: research-route\nroute_id: {rid}\n---\n\n# {route.get('name', rid)}\n\n{route.get('description', '')}\n\n## 代表论文\n\n{papers}\n"
        (vault / "30-Routes" / f"{safe_name(rid)}.md").write_text(text, encoding="utf-8")
    for item in data.get("controversies", []):
        cid = item.get("id", "T")
        text = f"---\ntype: controversy\ncontroversy_id: {cid}\n---\n\n# {item.get('question', cid)}\n\n{item.get('current_interpretation', '')}\n\n关系：{', '.join(item.get('relation_ids', []))}\n"
        (vault / "40-Controversies" / f"{safe_name(cid)}.md").write_text(text, encoding="utf-8")


def render_workspace(root: Path) -> None:
    cards, origins, errors = load_cards(root)
    if errors:
        raise ValueError("\n".join(errors))
    data = read_json(root / "knowledge/map.json")
    relations = read_jsonl(root / "knowledge/relations.jsonl")
    map_md = render_map_markdown(data, cards, relations)
    (root / "knowledge/MAP.md").write_text(map_md, encoding="utf-8")
    (root / "knowledge/INDEX.md").write_text(render_index(cards, origins, root), encoding="utf-8")
    render_vault(root, data, cards, relations, map_md)

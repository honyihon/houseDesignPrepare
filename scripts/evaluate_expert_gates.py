#!/usr/bin/env python3
"""Evaluate multi-expert gates and generate human/machine readable reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

REPORT_DIR = ROOT / "structured" / "expert_review"
RULE_DIR = ROOT / "scripts" / "rules"
PROGRAM_FILE = ROOT / "structured" / "room_program.json"
CANDIDATE_FILE = ROOT / "structured" / "candidates" / "layout_candidates.json"
ARCHITECT_METRICS_FILE = ROOT / "structured" / "architect_metrics" / "metrics.json"
NORMALIZED_REQUEST_FILE = REPORT_DIR / "request_normalized.json"
DEFAULT_REPORT_JSON = REPORT_DIR / "report.json"
DEFAULT_REPORT_MD = REPORT_DIR / "report.md"
DEFAULT_TASK_BOARD = ROOT / "task-board.md"
DEFAULT_SIGNOFF_FILE = REPORT_DIR / "signoff.yaml"
SCHEMA_VERSION = "expert-review-v1"
TASK_BOARD_MARKER_START = "<!-- AUTO:LAST_RUN_START -->"
TASK_BOARD_MARKER_END = "<!-- AUTO:LAST_RUN_END -->"

HTML_FILE_MAP: dict[str, str] = {
    "A": "AbuildingView.html",
    "B": "BbuildingView.html",
    "C": "CbuildingView.html",
    "STORAGE": "storage.html",
}

SEVERITY_ORDER = {"critical": 3, "warning": 2, "info": 1}
PUBLIC_ROOM_KEYWORDS = ["客廳", "玄關", "餐廳", "神明廳"]
PRIVATE_ROOM_KEYWORDS = ["主臥", "臥", "客房", "孝親"]
WET_ROOM_KEYWORDS = ["衛", "浴", "廁", "廚", "洗"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_match_text(value: str) -> str:
    value = normalize_whitespace(value).lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value)
    return value


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def truthy_attr(value: str | None) -> bool:
    if value is None:
        return False
    text = normalize_whitespace(value).lower()
    if text in {"", "1", "true", "yes", "y", "on"}:
        return True
    return text not in {"0", "false", "no", "n", "off"}


def text_of(node: Tag | None) -> str:
    if node is None:
        return ""
    return normalize_whitespace(node.get_text(" ", strip=True))


def parse_highlight_room(onclick: str) -> str:
    raw = onclick or ""
    match = re.search(r"highlightRoom\(\s*'([^']+)'", raw)
    if match:
        return match.group(1)
    match = re.search(r'highlightRoom\(\s*"([^"]+)"', raw)
    return match.group(1) if match else ""


def parse_buildings(value: str) -> list[str]:
    items: list[str] = []
    for raw in value.split(","):
        token = normalize_whitespace(raw).upper()
        if token and token in HTML_FILE_MAP and token not in items:
            items.append(token)
    if not items:
        return ["A", "B", "C"]
    return items


def parse_markdown_sections(content: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "General"
    sections[current] = []
    for line in content.splitlines():
        heading_match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading_match:
            current = normalize_whitespace(heading_match.group(1))
            if current not in sections:
                sections[current] = []
            continue
        sections[current].append(line.rstrip())
    return {k: normalize_whitespace("\n".join(v)) for k, v in sections.items()}


def parse_signoff_yaml(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = normalize_whitespace(key)
        value = normalize_whitespace(value)
        if key:
            result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def load_rule_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore

            payload = yaml.safe_load(text)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    raise ValueError(f"Unsupported rule format: {path}")


def load_rule_packs(rule_dir: Path) -> list[dict[str, Any]]:
    expected = [
        "tw_building_regulations.yaml",
        "tw_accessibility.yaml",
        "fengshui.yaml",
        "interior_design.yaml",
    ]
    packs: list[dict[str, Any]] = []
    for name in expected:
        path = rule_dir / name
        if not path.exists():
            continue
        payload = load_rule_file(path)
        payload["_file"] = path.name
        packs.append(payload)
    return packs


def has_required_citation(rule: dict[str, Any]) -> bool:
    return bool(
        normalize_whitespace(str(rule.get("source_doc", "")))
        and normalize_whitespace(str(rule.get("source_article", "")))
        and normalize_whitespace(str(rule.get("source_url", "")))
    )


@dataclass
class RuleEvalContext:
    request_text: str
    request_sections: dict[str, str]
    selected_buildings: list[str]
    soups: dict[str, BeautifulSoup]
    program: dict[str, Any]
    candidates: dict[str, Any]
    architect_metrics: dict[str, Any]


def build_context(
    request_text: str,
    request_sections: dict[str, str],
    selected_buildings: list[str],
) -> RuleEvalContext:
    soups: dict[str, BeautifulSoup] = {}
    for building in selected_buildings:
        html_name = HTML_FILE_MAP[building]
        html_path = ROOT / html_name
        if not html_path.exists():
            continue
        soups[building] = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    program = load_json(PROGRAM_FILE) if PROGRAM_FILE.exists() else {}
    candidates = load_json(CANDIDATE_FILE) if CANDIDATE_FILE.exists() else {}
    architect_metrics = load_json(ARCHITECT_METRICS_FILE) if ARCHITECT_METRICS_FILE.exists() else {}
    return RuleEvalContext(
        request_text=request_text,
        request_sections=request_sections,
        selected_buildings=selected_buildings,
        soups=soups,
        program=program,
        candidates=candidates,
        architect_metrics=architect_metrics,
    )


def floor_nodes_with_cells(soup: BeautifulSoup) -> list[Tag]:
    nodes: list[Tag] = []
    for floor in soup.select(".floor-plan"):
        if floor.select(".plan-cell"):
            nodes.append(floor)
    return nodes


def floor_level_label(floor: Tag) -> str:
    icon = text_of(floor.select_one(".floor-title-icon"))
    if icon:
        return icon.upper()
    floor_id = normalize_whitespace(str(floor.get("id", ""))).upper()
    if floor_id in {"FLOOR-1", "FLOOR_1"}:
        return "1F"
    return (text_of(floor.select_one(".floor-title")) or floor_id).upper()


def evaluate_floor_attr_required(rule: dict[str, Any], ctx: RuleEvalContext) -> tuple[bool, list[str]]:
    attrs = [str(v) for v in rule.get("attrs", [])]
    missing: list[str] = []
    for building in ctx.selected_buildings:
        soup = ctx.soups.get(building)
        if not soup:
            missing.append(f"{building}: html missing")
            continue
        for floor in floor_nodes_with_cells(soup):
            floor_id = floor.get("id", "<no-id>")
            for attr in attrs:
                if not normalize_whitespace(floor.get(attr, "")):
                    missing.append(f"{building}:{floor_id} missing {attr}")
    return (len(missing) == 0, missing)


def evaluate_entry_per_floor(rule: dict[str, Any], ctx: RuleEvalContext) -> tuple[bool, list[str]]:
    problems: list[str] = []
    for building in ctx.selected_buildings:
        soup = ctx.soups.get(building)
        if not soup:
            problems.append(f"{building}: html missing")
            continue
        for floor in floor_nodes_with_cells(soup):
            floor_id = floor.get("id", "<no-id>")
            count = 0
            for cell in floor.select(".plan-cell"):
                if truthy_attr(cell.get("data-entry")):
                    count += 1
            if count != 1:
                problems.append(f"{building}:{floor_id} entry_count={count}")
    return (len(problems) == 0, problems)


def evaluate_entry_ground_floor(rule: dict[str, Any], ctx: RuleEvalContext) -> tuple[bool, list[str]]:
    problems: list[str] = []
    ground_labels = {"1F", "GF", "G/F", "GROUND FLOOR"}
    for building in ctx.selected_buildings:
        soup = ctx.soups.get(building)
        if not soup:
            problems.append(f"{building}: html missing")
            continue
        for floor in floor_nodes_with_cells(soup):
            floor_id = floor.get("id", "<no-id>")
            if floor_level_label(floor) not in ground_labels:
                continue
            count = sum(
                1
                for cell in floor.select(".plan-cell")
                if truthy_attr(cell.get("data-entry"))
            )
            if count != 1:
                problems.append(f"{building}:{floor_id} entry_count={count}")
    return (len(problems) == 0, problems)


def evaluate_door_width_min(rule: dict[str, Any], ctx: RuleEvalContext) -> tuple[bool, list[str]]:
    minimum = to_int(rule.get("min_mm"), 800)
    problems: list[str] = []
    for building in ctx.selected_buildings:
        soup = ctx.soups.get(building)
        if not soup:
            continue
        for idx, cell in enumerate(soup.select(".plan-cell"), start=1):
            raw = normalize_whitespace(cell.get("data-door-mm", ""))
            if not raw:
                continue
            value = to_int(raw, -1)
            if value >= 0 and value < minimum:
                room_name = text_of(cell.select_one(".cell-name")) or f"cell-{idx}"
                problems.append(f"{building}:{room_name} door_mm={value}<{minimum}")
    return (len(problems) == 0, problems)


def evaluate_building_keyword_required(rule: dict[str, Any], ctx: RuleEvalContext) -> tuple[bool, list[str]]:
    keyword = normalize_whitespace(str(rule.get("keyword", "")))
    missing: list[str] = []
    if not keyword:
        return (True, [])
    for building in ctx.selected_buildings:
        soup = ctx.soups.get(building)
        if not soup:
            missing.append(f"{building}: html missing")
            continue
        if keyword not in soup.get_text(" ", strip=True):
            missing.append(f"{building}: keyword '{keyword}' not found")
    return (len(missing) == 0, missing)


def evaluate_accessible_door_min(rule: dict[str, Any], ctx: RuleEvalContext) -> tuple[bool, list[str]]:
    raw_keywords = rule.get("keywords")
    if not isinstance(raw_keywords, list):
        raw_keywords = [rule.get("keyword", "無障礙")]
    keywords = [
        normalize_whitespace(str(keyword))
        for keyword in raw_keywords
        if normalize_whitespace(str(keyword))
    ]
    minimum = to_int(rule.get("min_mm"), 800)
    accessible_roles = {"elder", "accessible-bath"}
    problems: list[str] = []
    for building in ctx.selected_buildings:
        soup = ctx.soups.get(building)
        if not soup:
            continue
        matched = False
        for idx, cell in enumerate(soup.select(".plan-cell"), start=1):
            cell_name = text_of(cell.select_one(".cell-name"))
            raw_text = " ".join(
                [
                    text_of(cell),
                    normalize_whitespace(cell.get("onclick", "")),
                    normalize_whitespace(" ".join(cell.get("class", []))),
                ]
            )
            is_accessible = truthy_attr(cell.get("data-accessible"))
            room_role = normalize_whitespace(cell.get("data-room-role", "")).lower()
            has_accessible_role = room_role in accessible_roles
            if not is_accessible and not has_accessible_role and not any(keyword in raw_text for keyword in keywords):
                continue
            matched = True
            door_mm = to_int(cell.get("data-door-mm"), -1)
            if door_mm < minimum:
                label = cell_name or f"cell-{idx}"
                problems.append(f"{building}:{label} accessible_door_mm={door_mm}<{minimum}")
        if not matched:
            problems.append(
                f"{building}: no cell matched accessible keywords {keywords}"
            )
    return (len(problems) == 0, problems)


def evaluate_request_section_required(rule: dict[str, Any], ctx: RuleEvalContext) -> tuple[bool, list[str]]:
    section = normalize_whitespace(str(rule.get("section", "")))
    if not section:
        return (True, [])
    for key in ctx.request_sections:
        if section.lower() in key.lower():
            return (True, [])
    return (False, [f"request missing section like '{section}'"])


def evaluate_request_regex(rule: dict[str, Any], ctx: RuleEvalContext) -> tuple[bool, list[str]]:
    pattern = str(rule.get("pattern", ""))
    if not pattern:
        return (True, [])
    if re.search(pattern, ctx.request_text, flags=re.IGNORECASE | re.MULTILINE):
        return (True, [])
    return (False, [f"request regex not matched: {pattern}"])


def evaluate_candidate_metric_min(rule: dict[str, Any], ctx: RuleEvalContext) -> tuple[bool, list[str]]:
    metric = normalize_whitespace(str(rule.get("metric", "circulation")))
    minimum = to_float(rule.get("min"), 50.0)
    floors = ctx.candidates.get("floors", [])
    if not floors:
        return (False, [f"candidate data missing for metric '{metric}'"])
    failed: list[str] = []
    for floor in floors:
        candidates = floor.get("candidates", [])
        if not candidates:
            continue
        best = candidates[0]
        value = to_float(best.get("scores", {}).get(metric), 0.0)
        if value < minimum:
            failed.append(
                f"{floor.get('building_id')}:{floor.get('floor_id')} {metric}={value}<{minimum}"
            )
    return (len(failed) == 0, failed)


def evaluate_rule(rule: dict[str, Any], ctx: RuleEvalContext) -> tuple[bool, list[str]]:
    check_type = normalize_whitespace(str(rule.get("check_type", "")))
    if check_type == "floor_attr_required":
        return evaluate_floor_attr_required(rule, ctx)
    if check_type == "entry_per_floor":
        return evaluate_entry_per_floor(rule, ctx)
    if check_type == "entry_ground_floor":
        return evaluate_entry_ground_floor(rule, ctx)
    if check_type == "door_width_min":
        return evaluate_door_width_min(rule, ctx)
    if check_type == "building_keyword_required":
        return evaluate_building_keyword_required(rule, ctx)
    if check_type == "accessible_door_min":
        return evaluate_accessible_door_min(rule, ctx)
    if check_type == "request_section_required":
        return evaluate_request_section_required(rule, ctx)
    if check_type == "request_regex":
        return evaluate_request_regex(rule, ctx)
    if check_type == "candidate_metric_min":
        return evaluate_candidate_metric_min(rule, ctx)
    return (True, [f"unsupported check_type={check_type} (treated as pass)"])


def contains_any_keyword(value: str, keywords: list[str]) -> bool:
    return any(k in value for k in keywords)


def fengshui_candidate_score(floor: dict[str, Any], candidate: dict[str, Any]) -> float:
    pair_details = candidate.get("pair_details", [])
    slot_count = max(1, to_int(floor.get("slot_count"), len(pair_details)))
    if not pair_details:
        return 50.0

    points = 0.0
    max_points = 0.0
    for pair in pair_details:
        room_text = normalize_match_text(str(pair.get("room_name", "")))
        slot_order = to_int(pair.get("slot_order"), 1)
        entrance_proximity = 1.0 if slot_count <= 1 else 1.0 - ((slot_order - 1) / (slot_count - 1))
        depth_ratio = 1.0 - entrance_proximity

        if contains_any_keyword(room_text, [normalize_match_text(v) for v in PUBLIC_ROOM_KEYWORDS]):
            points += entrance_proximity * 100.0
            max_points += 100.0
        if contains_any_keyword(room_text, [normalize_match_text(v) for v in PRIVATE_ROOM_KEYWORDS]):
            points += depth_ratio * 100.0
            max_points += 100.0
        if contains_any_keyword(room_text, [normalize_match_text(v) for v in WET_ROOM_KEYWORDS]):
            points += max(0.0, 1.0 - abs(entrance_proximity - 0.5) * 2.0) * 80.0
            max_points += 80.0

    if max_points <= 0.0:
        return 50.0
    return round(max(0.0, min(100.0, (points / max_points) * 100.0)), 2)


def parse_weights(raw: str) -> dict[str, float]:
    chunks = [normalize_whitespace(v) for v in raw.split(",")]
    chunks = [v for v in chunks if v]
    defaults = [0.35, 0.25, 0.20, 0.20]
    if len(chunks) != 4:
        values = defaults
    else:
        values = [to_float(v, defaults[idx]) for idx, v in enumerate(chunks)]
    total = sum(values) or 1.0
    normalized = [max(0.0, v) / total for v in values]
    return {
        "circulation": round(normalized[0], 4),
        "daylight": round(normalized[1], 4),
        "mep": round(normalized[2], 4),
        "fengshui": round(normalized[3], 4),
    }


def evaluate_expert_scoring(
    candidates_payload: dict[str, Any],
    weights: dict[str, float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    floors = candidates_payload.get("floors", [])
    recommendations: list[dict[str, Any]] = []

    totals = {
        "circulation": 0.0,
        "daylight": 0.0,
        "mep": 0.0,
        "fengshui": 0.0,
        "composite": 0.0,
    }
    strategy_count: dict[str, int] = {}

    for floor in floors:
        scored_candidates: list[dict[str, Any]] = []
        for candidate in floor.get("candidates", []):
            raw_scores = candidate.get("scores", {})
            circulation = to_float(raw_scores.get("circulation"), 0.0)
            daylight = to_float(raw_scores.get("daylight"), 0.0)
            mep = to_float(raw_scores.get("mep"), 0.0)
            fengshui = fengshui_candidate_score(floor, candidate)
            composite = (
                circulation * weights["circulation"]
                + daylight * weights["daylight"]
                + mep * weights["mep"]
                + fengshui * weights["fengshui"]
            )
            scored_candidates.append(
                {
                    "id": candidate.get("id", ""),
                    "strategy": candidate.get("strategy", ""),
                    "scores": {
                        "circulation": round(circulation, 2),
                        "daylight": round(daylight, 2),
                        "mep": round(mep, 2),
                        "fengshui": round(fengshui, 2),
                        "composite": round(composite, 2),
                    },
                }
            )

        scored_candidates.sort(key=lambda x: x["scores"]["composite"], reverse=True)
        if not scored_candidates:
            continue

        best = scored_candidates[0]
        pipeline_best = ""
        if floor.get("candidates"):
            pipeline_best = str(floor["candidates"][0].get("id", ""))

        recommendation = {
            "building_id": floor.get("building_id", ""),
            "floor_id": floor.get("floor_id", ""),
            "pipeline_best": pipeline_best,
            "expert_best": best["id"],
            "changed_from_pipeline": bool(pipeline_best and best["id"] != pipeline_best),
            "top_scores": best["scores"],
            "ranked": scored_candidates,
        }
        recommendations.append(recommendation)

        totals["circulation"] += best["scores"]["circulation"]
        totals["daylight"] += best["scores"]["daylight"]
        totals["mep"] += best["scores"]["mep"]
        totals["fengshui"] += best["scores"]["fengshui"]
        totals["composite"] += best["scores"]["composite"]

        strategy = normalize_whitespace(best.get("strategy", ""))
        strategy_count[strategy] = strategy_count.get(strategy, 0) + 1

    count = max(1, len(recommendations))
    breakdown = {
        "weights": weights,
        "evaluated_floor_count": len(recommendations),
        "averages": {
            "circulation": round(totals["circulation"] / count, 2),
            "daylight": round(totals["daylight"] / count, 2),
            "mep": round(totals["mep"] / count, 2),
            "fengshui": round(totals["fengshui"] / count, 2),
            "composite": round(totals["composite"] / count, 2),
        },
        "recommended_strategy_distribution": strategy_count,
        "pipeline_changed_floor_count": sum(1 for r in recommendations if r["changed_from_pipeline"]),
    }
    return recommendations, breakdown


def generate_report_md(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Expert Review Report")
    lines.append("")
    lines.append(f"- Generated: `{report.get('generated_at', '')}`")
    lines.append(f"- Mode: `{report.get('input', {}).get('mode', '')}`")
    lines.append(f"- Buildings: `{','.join(report.get('input', {}).get('buildings', []))}`")
    lines.append(f"- Hard Gate: **{report.get('hard_gate', 'unknown').upper()}**")
    lines.append("")

    lines.append("## Critical Failures")
    lines.append("")
    critical_failures = report.get("critical_failures", [])
    if not critical_failures:
        lines.append("- None")
    else:
        for item in critical_failures:
            lines.append(format_review_item(item))
    lines.append("")

    append_review_section(lines, "Warnings", report.get("warnings", []))
    append_review_section(lines, "Info Items", report.get("infos", []))

    lines.append("## Score Breakdown")
    lines.append("")
    score = report.get("score_breakdown", {})
    weights = score.get("weights", {})
    averages = score.get("averages", {})
    lines.append(
        f"- Weights: circulation={weights.get('circulation', 0)}, "
        f"daylight={weights.get('daylight', 0)}, mep={weights.get('mep', 0)}, "
        f"fengshui={weights.get('fengshui', 0)}"
    )
    lines.append(
        f"- Averages: circulation={averages.get('circulation', 0)}, "
        f"daylight={averages.get('daylight', 0)}, mep={averages.get('mep', 0)}, "
        f"fengshui={averages.get('fengshui', 0)}, composite={averages.get('composite', 0)}"
    )
    lines.append(
        f"- Floors changed by expert weighting: {score.get('pipeline_changed_floor_count', 0)}"
    )
    lines.append("")

    lines.append("## Architect Metrics")
    lines.append("")
    architect_summary = report.get("architect_metrics_summary", {})
    if not architect_summary:
        lines.append("- Not generated")
    else:
        status_counts = architect_summary.get("status_counts", {})
        lines.append(f"- Evaluated floors: {architect_summary.get('evaluated_floor_count', 0)}")
        lines.append(
            f"- Status: ok={status_counts.get('ok', 0)}, "
            f"advisory={status_counts.get('advisory', 0)}, "
            f"missing_data={status_counts.get('missing_data', 0)}, "
            f"professional_required={status_counts.get('professional_required', 0)}"
        )
        lines.append(
            f"- Daylight avg: {architect_summary.get('daylight_factor_avg_pct', 0)}%; "
            f"below target rooms: {architect_summary.get('daylight_rooms_below_target', 0)}"
        )
        top_issues = architect_summary.get("top_issues", [])
        if top_issues:
            lines.append(f"- First issue: {top_issues[0]}")
        action_groups = architect_summary.get("action_groups", {})
        if action_groups:
            lines.append("- Action groups:")
            for group, items in action_groups.items():
                lines.append(f"  - {group}: {len(items)} item(s)")
    lines.append("")

    lines.append("## Review Artifacts")
    lines.append("")
    artifacts = report.get("artifacts", {})
    artifact_items = [(key, value) for key, value in artifacts.items() if value]
    if not artifact_items:
        lines.append("- None")
    else:
        for key, value in artifact_items:
            lines.append(f"- `{key}`: `{value}`")
    lines.append("")

    lines.append("## Citations")
    lines.append("")
    citations = report.get("citations", [])
    if not citations:
        lines.append("- None")
    else:
        for c in citations:
            lines.append(
                f"- `{c.get('rule_id')}` {c.get('source_doc')} {c.get('source_article')} ({c.get('source_url')})"
            )
    lines.append("")
    return "\n".join(lines)


def format_review_item(item: dict[str, Any]) -> str:
    parts = [f"- `{item.get('rule_id', '')}` {item.get('message', '')}"]
    evidence = item.get("evidence", [])
    if evidence:
        parts.append(f"evidence: {'; '.join(str(v) for v in evidence[:3])}")
    fix_hint = normalize_whitespace(str(item.get("fix_hint", "")))
    if fix_hint:
        parts.append(f"fix: {fix_hint}")
    return " | ".join(parts)


def append_review_section(lines: list[str], title: str, items: list[dict[str, Any]]) -> None:
    lines.append(f"## {title}")
    lines.append("")
    if not items:
        lines.append("- None")
    else:
        for item in items:
            lines.append(format_review_item(item))
    lines.append("")


def ensure_task_board(path: Path) -> None:
    if path.exists():
        return
    template = """# House Design Task Board

## Rollout Plan

- Pilot: A Building
- Expansion: B, C Buildings

## Validation Points

- R0 Requirement confirmed
- R1 Geometry specification
- R2 HTML consistency
- R3 Expert gates
- R4 IFC + signoff

<!-- AUTO:LAST_RUN_START -->
Last run not recorded yet.
<!-- AUTO:LAST_RUN_END -->
"""
    path.write_text(template, encoding="utf-8")


def update_task_board(path: Path, report: dict[str, Any]) -> None:
    ensure_task_board(path)
    content = path.read_text(encoding="utf-8")
    block = "\n".join(
        [
            TASK_BOARD_MARKER_START,
            f"- Last Run: {report.get('generated_at', '')}",
            f"- Mode: {report.get('input', {}).get('mode', '')}",
            f"- Buildings: {','.join(report.get('input', {}).get('buildings', []))}",
            f"- Hard Gate: {report.get('hard_gate', '').upper()}",
            f"- Critical Failures: {len(report.get('critical_failures', []))}",
            f"- Warning Count: {len(report.get('warnings', []))}",
            f"- Expert Composite Avg: {report.get('score_breakdown', {}).get('averages', {}).get('composite', 0)}",
            f"- Architect Metrics Advisory: {report.get('architect_metrics_summary', {}).get('status_counts', {}).get('advisory', 0)}",
            TASK_BOARD_MARKER_END,
        ]
    )
    pattern = re.compile(
        re.escape(TASK_BOARD_MARKER_START) + r".*?" + re.escape(TASK_BOARD_MARKER_END),
        flags=re.DOTALL,
    )
    if pattern.search(content):
        content = pattern.sub(block, content)
    else:
        content = content.rstrip() + "\n\n" + block + "\n"
    path.write_text(content, encoding="utf-8")


def build_normalized_request(request_path: Path) -> dict[str, Any]:
    request_text = request_path.read_text(encoding="utf-8")
    sections = parse_markdown_sections(request_text)
    normalized = {
        "schema_version": "design-request-normalized-v1",
        "generated_at": now_iso(),
        "source_file": str(request_path.name),
        "word_count": len(re.findall(r"\S+", request_text)),
        "sections": sections,
        "top_level_headings": [k for k in sections.keys() if k != "General"],
    }
    NORMALIZED_REQUEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    NORMALIZED_REQUEST_FILE.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def rule_result_item(
    rule: dict[str, Any],
    passed: bool,
    evidence: list[str],
    hard_gate_eligible: bool,
) -> dict[str, Any]:
    return {
        "rule_id": normalize_whitespace(str(rule.get("rule_id", ""))),
        "domain": normalize_whitespace(str(rule.get("domain", ""))),
        "severity": normalize_whitespace(str(rule.get("severity", "warning")).lower()),
        "passed": passed,
        "message": normalize_whitespace(str(rule.get("message", ""))),
        "fail_message": normalize_whitespace(str(rule.get("fail_message", ""))),
        "fix_hint": normalize_whitespace(str(rule.get("fix_hint", ""))),
        "evidence": evidence[:10],
        "source_doc": normalize_whitespace(str(rule.get("source_doc", ""))),
        "source_article": normalize_whitespace(str(rule.get("source_article", ""))),
        "source_url": normalize_whitespace(str(rule.get("source_url", ""))),
        "hard_gate_eligible": hard_gate_eligible,
    }


def architect_metric_rule_results(metrics_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not metrics_payload:
        return [
            {
                "rule_id": "ARCH-MET-000",
                "domain": "architect_metrics",
                "severity": "info",
                "passed": False,
                "message": "Architect metrics report not found.",
                "fail_message": "Run scripts/evaluate_architect_metrics.py after room_program is generated.",
                "fix_hint": "Use the full pipeline or run the architect metrics step manually.",
                "evidence": ["structured/architect_metrics/metrics.json missing"],
                "source_doc": "Skills-Architects calculator adaptation",
                "source_article": "Concept advisory metrics",
                "source_url": "https://github.com/Amanbh997/Skills-Architects",
                "hard_gate_eligible": False,
            }
        ]

    summary = metrics_payload.get("summary", {})
    status_counts = summary.get("status_counts", {})
    generated_at = normalize_whitespace(str(metrics_payload.get("generated_at", "")))
    results: list[dict[str, Any]] = []

    advisory_count = to_int(status_counts.get("advisory"), 0)
    missing_count = to_int(status_counts.get("missing_data"), 0)
    if advisory_count or missing_count:
        results.append(
            {
                "rule_id": "ARCH-MET-001",
                "domain": "architect_metrics",
                "severity": "warning",
                "passed": False,
                "message": "Concept architect metrics found advisory or missing-data items.",
                "fail_message": "Some rooms need better daylight, door, geometry, or metadata before design review.",
                "fix_hint": "Review structured/architect_metrics/report.md and update HTML geometry/openings or request professional calculation.",
                "evidence": [
                    f"generated_at={generated_at}",
                    f"advisory={advisory_count}",
                    f"missing_data={missing_count}",
                    *[str(v) for v in summary.get("top_issues", [])[:8]],
                ],
                "source_doc": "Skills-Architects calculator adaptation",
                "source_article": "Daylight/door/geometry advisory screening",
                "source_url": "https://github.com/Amanbh997/Skills-Architects",
                "hard_gate_eligible": False,
            }
        )

    professional_count = to_int(status_counts.get("professional_required"), 0)
    if professional_count:
        results.append(
            {
                "rule_id": "ARCH-MET-002",
                "domain": "architect_metrics",
                "severity": "info",
                "passed": False,
                "message": "Architect metrics identified items requiring professional review.",
                "fail_message": "Formal daylight, ventilation, egress, or structural review is still required.",
                "fix_hint": "Keep these items as architect/engineer confirmation tasks; do not treat concept metrics as signoff.",
                "evidence": [
                    f"generated_at={generated_at}",
                    f"professional_required={professional_count}",
                ],
                "source_doc": "Skills-Architects calculator adaptation",
                "source_article": "Professional review advisory screening",
                "source_url": "https://github.com/Amanbh997/Skills-Architects",
                "hard_gate_eligible": False,
            }
        )

    return results


VOLATILE_REPORT_HASH_KEYS = {"generated_at", "report_hash", "signoff"}
VALID_SIGNOFF_DECISIONS = {"approved", "pass", "approved_with_conditions"}
VALID_REVIEWER_KINDS = {"human", "professional"}


def clean_yaml_scalar(value: Any) -> str:
    text = normalize_whitespace(str(value or ""))
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def valid_reviewer_field(value: str) -> bool:
    normalized = normalize_match_text(value)
    return bool(value) and not (value.startswith("<") and value.endswith(">")) and normalized not in {
        "claudecode",
        "codex",
        "ai",
        "assistant",
    }


def stable_report_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: stable_report_value(item)
            for key, item in value.items()
            if key not in VOLATILE_REPORT_HASH_KEYS
        }
    if isinstance(value, list):
        return [stable_report_value(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"generated_at=[^,\];\s]+", "generated_at=<volatile>", value)
    return value


def report_hash_payload(report: dict[str, Any]) -> dict[str, Any]:
    return stable_report_value(report)


def report_content_hash(report: dict[str, Any]) -> str:
    payload = json.dumps(
        report_hash_payload(report),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def stable_report_hash(report: dict[str, Any]) -> str:
    return report_content_hash(report)


def validate_signoff_for_report(
    signoff_data: dict[str, str],
    report: dict[str, Any],
    allow_stale: bool = False,
) -> dict[str, Any]:
    decision = clean_yaml_scalar(signoff_data.get("decision", "")).lower()
    reviewer_kind = clean_yaml_scalar(signoff_data.get("reviewer_kind", "")).lower()
    reviewer_role = clean_yaml_scalar(signoff_data.get("reviewer_role", ""))
    reviewer_name = clean_yaml_scalar(signoff_data.get("reviewer_name", ""))
    reviewer_date = clean_yaml_scalar(signoff_data.get("reviewer_date", signoff_data.get("date", "")))
    expected_hash = normalize_whitespace(str(report.get("report_hash") or report_content_hash(report)))
    related_hash = clean_yaml_scalar(signoff_data.get("related_report_hash", ""))
    hash_match = bool(related_hash) and related_hash == expected_hash
    decision_valid = decision in VALID_SIGNOFF_DECISIONS
    reviewer_valid = (
        reviewer_kind in VALID_REVIEWER_KINDS
        and valid_reviewer_field(reviewer_role)
        and valid_reviewer_field(reviewer_name)
        and valid_reviewer_field(reviewer_date)
    )
    valid = decision_valid and reviewer_valid and (hash_match or allow_stale)
    if valid:
        reason = "ok" if hash_match else "stale_allowed"
    elif not decision_valid:
        reason = "decision_missing_or_invalid"
    elif not reviewer_valid:
        reason = "reviewer_kind_or_identity_missing_or_invalid"
    elif not related_hash:
        reason = "related_report_hash_missing"
    else:
        reason = "related_report_hash_mismatch"

    return {
        "exists": bool(signoff_data),
        "decision": decision,
        "decision_valid": decision_valid,
        "reviewer_kind": reviewer_kind,
        "reviewer_valid": reviewer_valid,
        "reviewer_role": reviewer_role,
        "reviewer_name": reviewer_name,
        "reviewer_date": reviewer_date,
        "related_report_hash": related_hash,
        "related_report_generated_at": clean_yaml_scalar(signoff_data.get("related_report_generated_at", "")),
        "expected_report_hash": expected_hash,
        "hash_match": hash_match,
        "stale_allowed": allow_stale,
        "valid": valid,
        "reason": reason,
    }


def build_report(
    request_path: Path,
    selected_buildings: list[str],
    mode: str,
    selection: str,
    weights: dict[str, float],
    rule_dir: Path,
    signoff_file: Path,
    allow_stale_signoff: bool = False,
) -> dict[str, Any]:
    normalized_request = build_normalized_request(request_path)
    request_text = request_path.read_text(encoding="utf-8")
    ctx = build_context(
        request_text=request_text,
        request_sections=normalized_request.get("sections", {}),
        selected_buildings=selected_buildings,
    )

    packs = load_rule_packs(rule_dir)
    rule_results: list[dict[str, Any]] = []
    citation_issues: list[str] = []
    citations: list[dict[str, str]] = []

    for pack in packs:
        pack_domain = normalize_whitespace(str(pack.get("domain", "")))
        for raw_rule in pack.get("rules", []):
            rule = dict(raw_rule)
            rule.setdefault("domain", pack_domain)
            severity = normalize_whitespace(str(rule.get("severity", "warning")).lower())
            passed, evidence = evaluate_rule(rule, ctx)
            hard_gate_eligible = severity == "critical" and has_required_citation(rule)
            if severity == "critical" and not has_required_citation(rule):
                citation_issues.append(
                    f"{rule.get('rule_id', '<no-id>')} missing source_doc/source_article/source_url"
                )
            rule_item = rule_result_item(rule, passed, evidence, hard_gate_eligible)
            rule_results.append(rule_item)
            if not passed and has_required_citation(rule):
                citations.append(
                    {
                        "rule_id": rule_item["rule_id"],
                        "source_doc": rule_item["source_doc"],
                        "source_article": rule_item["source_article"],
                        "source_url": rule_item["source_url"],
                    }
                )

    rule_results.extend(architect_metric_rule_results(ctx.architect_metrics))

    critical_failures = [
        r
        for r in rule_results
        if (not r["passed"]) and r["severity"] == "critical" and r["hard_gate_eligible"]
    ]
    warnings = [r for r in rule_results if (not r["passed"]) and r["severity"] == "warning"]
    infos = [r for r in rule_results if (not r["passed"]) and r["severity"] == "info"]
    hard_gate = "fail" if critical_failures else "pass"

    recommendations, score_breakdown = evaluate_expert_scoring(ctx.candidates, weights)

    signoff_data = parse_signoff_yaml(signoff_file)
    signoff_status = {
        "exists": signoff_file.exists(),
        "decision": clean_yaml_scalar(signoff_data.get("decision", "")).lower(),
        "reviewer_kind": clean_yaml_scalar(signoff_data.get("reviewer_kind", "")).lower(),
        "reviewer_role": clean_yaml_scalar(signoff_data.get("reviewer_role", "")),
        "reviewer_name": clean_yaml_scalar(signoff_data.get("reviewer_name", "")),
        "reviewer_date": clean_yaml_scalar(signoff_data.get("reviewer_date", signoff_data.get("date", ""))),
        "related_report_hash": clean_yaml_scalar(signoff_data.get("related_report_hash", "")),
        "related_report_generated_at": clean_yaml_scalar(signoff_data.get("related_report_generated_at", "")),
    }

    artifacts = {
        "normalized_request": artifact_path(NORMALIZED_REQUEST_FILE) if NORMALIZED_REQUEST_FILE.exists() else "",
        "room_program": artifact_path(PROGRAM_FILE) if PROGRAM_FILE.exists() else "",
        "candidates": artifact_path(CANDIDATE_FILE) if CANDIDATE_FILE.exists() else "",
        "architect_metrics": artifact_path(ARCHITECT_METRICS_FILE) if ARCHITECT_METRICS_FILE.exists() else "",
        "architect_metrics_report": artifact_path(ROOT / "structured/architect_metrics/report.md")
        if (ROOT / "structured/architect_metrics/report.md").exists()
        else "",
        "html_consistency": artifact_path(ROOT / "structured/expert_review/html_consistency.json")
        if (ROOT / "structured/expert_review/html_consistency.json").exists()
        else "",
        "domain_checklist": artifact_path(ROOT / "structured/expert_review/domain_checklist.md"),
        "viewer": artifact_path(ROOT / "structured/candidates/viewer.html")
        if (ROOT / "structured/candidates/viewer.html").exists()
        else "",
        "pdf": artifact_path(ROOT / "structured/candidates/print_bundle.pdf")
        if (ROOT / "structured/candidates/print_bundle.pdf").exists()
        else "",
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "input": {
            "request_file": str(request_path.name),
            "mode": mode,
            "selection": selection,
            "buildings": selected_buildings,
            "rule_dir": str(rule_dir.relative_to(ROOT)) if rule_dir.exists() else str(rule_dir),
        },
        "hard_gate": hard_gate,
        "critical_failures": critical_failures,
        "warnings": warnings,
        "infos": infos,
        "citation_issues": citation_issues,
        "citations": citations,
        "score_breakdown": score_breakdown,
        "architect_metrics_summary": ctx.architect_metrics.get("summary", {}),
        "expert_recommendations": recommendations,
        "signoff": signoff_status,
        "artifacts": artifacts,
        "rule_results": sorted(
            rule_results,
            key=lambda x: (
                -SEVERITY_ORDER.get(x.get("severity", "info"), 0),
                x.get("rule_id", ""),
            ),
        ),
    }
    report["report_hash"] = report_content_hash(report)
    report["signoff"] = validate_signoff_for_report(
        signoff_data,
        report,
        allow_stale=allow_stale_signoff,
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate expert gates and produce reports.")
    parser.add_argument("--request", type=Path, required=True, help="Input requirement markdown file")
    parser.add_argument("--buildings", type=str, default="A,B,C", help="Comma separated building IDs")
    parser.add_argument("--mode", type=str, default="draft", choices=["concept", "draft", "ifc"])
    parser.add_argument("--selection", type=str, default="auto", choices=["auto", "baseline", "best"])
    parser.add_argument("--stage", type=str, default="full", choices=["normalize", "gate", "report", "full"])
    parser.add_argument("--weights", type=str, default="0.35,0.25,0.20,0.20")
    parser.add_argument("--rule-dir", type=Path, default=RULE_DIR)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_REPORT_MD)
    parser.add_argument("--task-board", type=Path, default=DEFAULT_TASK_BOARD)
    parser.add_argument("--signoff", type=Path, default=DEFAULT_SIGNOFF_FILE)
    parser.add_argument(
        "--enforce-signoff-hash",
        action="store_true",
        help="Return exit code 2 unless signoff related_report_hash matches this report.",
    )
    parser.add_argument(
        "--allow-stale-signoff",
        action="store_true",
        help="Record stale signoff as allowed instead of failing hash enforcement.",
    )
    parser.add_argument(
        "--allow-hard-gate-failure",
        action="store_true",
        help="Always return 0 even when hard gate fails.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    request_path = args.request.resolve()
    if not request_path.exists():
        raise SystemExit(f"request file not found: {request_path}")

    selected_buildings = parse_buildings(args.buildings)
    weights = parse_weights(args.weights)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if args.stage == "normalize":
        normalized = build_normalized_request(request_path)
        print(f"Normalized request: {NORMALIZED_REQUEST_FILE}")
        print(f"Sections: {list(normalized.get('sections', {}).keys())}")
        return

    report = build_report(
        request_path=request_path,
        selected_buildings=selected_buildings,
        mode=args.mode,
        selection=args.selection,
        weights=weights,
        rule_dir=args.rule_dir.resolve(),
        signoff_file=args.signoff.resolve(),
        allow_stale_signoff=args.allow_stale_signoff,
    )
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(generate_report_md(report), encoding="utf-8")
    if args.stage in {"report", "full"}:
        update_task_board(args.task_board.resolve(), report)
        task_board_status = str(args.task_board.resolve())
    else:
        task_board_status = "skipped for stage gate"

    print(f"Report JSON: {args.output_json.resolve()}")
    print(f"Report MD:   {args.output_md.resolve()}")
    print(f"Task board:  {task_board_status}")
    print(f"Hard gate:   {report['hard_gate']}")
    print(f"Critical:    {len(report['critical_failures'])}")
    print(f"Warnings:    {len(report['warnings'])}")
    print(f"Info:        {len(report['infos'])}")

    if args.enforce_signoff_hash and not report.get("signoff", {}).get("valid"):
        signoff = report.get("signoff", {})
        print(f"IFC signoff: {signoff.get('reason', 'invalid')}")
        print(f"Expected related_report_hash: {signoff.get('expected_report_hash', '')}")
        print(f"Actual related_report_hash:   {signoff.get('related_report_hash', '')}")
        raise SystemExit(2)

    if report["hard_gate"] == "fail" and not args.allow_hard_gate_failure:
        raise SystemExit(10)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Export canonical-first discussion HTML copies with candidate metadata."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag


ROOT = Path(__file__).resolve().parents[1]
PROGRAM_FILE = ROOT / "structured" / "room_program.json"
CANDIDATES_FILE = ROOT / "structured" / "candidates" / "layout_candidates.json"
REPORT_FILE = ROOT / "structured" / "expert_review" / "report.json"
SVG_MANIFEST_FILE = ROOT / "structured" / "candidates" / "svg" / "manifest.json"
OUTPUT_DIR = ROOT / "structured" / "final_design_html"
SCHEMA_VERSION = "final-html-sync-v2"
SYNC_MODE = "canonical_snapshot"

HTML_FILE_MAP: dict[str, str] = {
    "A": "AbuildingView.html",
    "B": "BbuildingView.html",
    "C": "CbuildingView.html",
}

STYLE_BLOCK = """
.final-sync-summary,
.final-floor-note {
    border: 1px solid rgba(96, 165, 250, .45);
    background: rgba(15, 23, 42, .78);
    color: #e5eefc;
    border-radius: 12px;
    padding: 14px 16px;
    margin: 14px 0;
    box-shadow: 0 10px 30px rgba(2, 6, 23, .18);
}
.final-sync-summary h2 {
    margin: 0 0 8px;
    color: #93c5fd;
    font-size: 1.05rem;
}
.final-sync-summary p,
.final-floor-note p {
    margin: 5px 0;
    color: #cbd5e1;
    line-height: 1.45;
}
.final-sync-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 8px;
    margin-top: 10px;
}
.final-sync-kpi {
    border: 1px solid rgba(148, 163, 184, .25);
    border-radius: 8px;
    padding: 8px 10px;
    background: rgba(30, 41, 59, .58);
}
.final-sync-kpi b {
    display: block;
    color: #f8fafc;
    font-size: .92rem;
}
.final-sync-kpi span {
    color: #94a3b8;
    font-size: .76rem;
}
.final-floor-note {
    border-color: rgba(45, 212, 191, .36);
    background: rgba(8, 47, 73, .48);
}
.final-floor-note strong {
    color: #5eead4;
}
.final-floor-note ul {
    margin: 6px 0 0 18px;
    padding: 0;
    color: #cbd5e1;
    font-size: .84rem;
}
.final-candidate-mismatch {
    color: #fde68a;
}
.badge.final-sync,
.final-sync-chip {
    border-color: rgba(45, 212, 191, .55) !important;
    color: #99f6e4 !important;
    background: rgba(20, 184, 166, .14) !important;
}
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_buildings(raw: str) -> list[str]:
    buildings: list[str] = []
    for token in raw.split(","):
        key = normalize(token).upper()
        if key in HTML_FILE_MAP and key not in buildings:
            buildings.append(key)
    return buildings or ["A", "B", "C"]


def resolve_selection(mode: str, selection: str) -> str:
    if selection != "auto":
        return selection
    return "best" if mode == "concept" else "baseline"


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing {label}: {path}. Run /workflow-house-all-in-one first.")
    return json.loads(path.read_text(encoding="utf-8"))


def parse_highlight_room(onclick: str) -> str:
    raw = onclick or ""
    match = re.search(r"highlightRoom\(\s*'([^']+)'", raw)
    if match:
        return match.group(1)
    match = re.search(r'highlightRoom\(\s*"([^"]+)"', raw)
    return match.group(1) if match else ""


def room_local_id(room_uid: str) -> str:
    return room_uid.rsplit(":", 1)[-1] if ":" in room_uid else room_uid


def split_icon_name(value: str) -> tuple[str, str]:
    text = normalize(value)
    if not text:
        return "", ""
    first = text[0]
    if first.isalnum() or "\u4e00" <= first <= "\u9fff":
        return "", text
    match = re.match(r"^([^\w\u4e00-\u9fff\s]+)\s*(.+)$", text, flags=re.UNICODE)
    if match:
        return match.group(1), normalize(match.group(2))
    return "", text


def text_of(node: Tag | None) -> str:
    if node is None:
        return ""
    return normalize(node.get_text(" ", strip=True))


def append_fragment(parent: Tag, fragment_html: str, position: int | None = None) -> None:
    fragment = BeautifulSoup(fragment_html, "html.parser")
    nodes = [node for node in fragment.contents if normalize(str(node))]
    if position is None:
        for node in nodes:
            parent.append(node)
    else:
        for offset, node in enumerate(nodes):
            parent.insert(position + offset, node)


def insert_after(target: Tag, fragment_html: str) -> None:
    fragment = BeautifulSoup(fragment_html, "html.parser")
    last: Tag | None = target
    for node in [node for node in fragment.contents if normalize(str(node))]:
        last.insert_after(node)
        if isinstance(node, Tag):
            last = node


def build_program_index(program: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for building in program.get("buildings", []):
        building_id = normalize(building.get("id", "")).upper()
        for floor in building.get("floors", []):
            floor_id = normalize(floor.get("id", ""))
            rooms_by_uid = {}
            rooms_by_local = {}
            for room in floor.get("rooms", []):
                uid = normalize(room.get("uid", ""))
                local_id = normalize(room.get("local_id", ""))
                if uid:
                    rooms_by_uid[uid] = room
                if local_id:
                    rooms_by_local[local_id] = room
            index[(building_id, floor_id)] = {
                "building": building,
                "floor": floor,
                "rooms_by_uid": rooms_by_uid,
                "rooms_by_local": rooms_by_local,
            }
    return index


def build_candidate_index(candidates: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for floor in candidates.get("floors", []):
        building_id = normalize(floor.get("building_id", "")).upper()
        floor_id = normalize(floor.get("floor_id", ""))
        index[(building_id, floor_id)] = floor
    return index


def select_candidate(floor_result: dict[str, Any], selection: str) -> dict[str, Any] | None:
    candidates = floor_result.get("candidates", [])
    if not candidates:
        return None
    by_id = {normalize(c.get("id", "")): c for c in candidates}
    if selection == "baseline":
        return by_id.get("baseline") or by_id.get(normalize(floor_result.get("best_candidate_id", ""))) or candidates[0]
    best_id = normalize(floor_result.get("best_candidate_id", ""))
    return by_id.get(best_id) or candidates[0]


def build_report_indexes(report: dict[str, Any], buildings: list[str]) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], list[str]]]:
    expert_map: dict[tuple[str, str], dict[str, Any]] = {}
    for rec in report.get("expert_recommendations", []):
        building_id = normalize(rec.get("building_id", "")).upper()
        floor_id = normalize(rec.get("floor_id", ""))
        if building_id and floor_id:
            expert_map[(building_id, floor_id)] = rec

    issue_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    issue_items = []
    issue_items.extend(report.get("critical_failures", []))
    issue_items.extend(report.get("warnings", []))
    issue_items.extend(report.get("infos", []))
    for item in issue_items:
        rule_id = normalize(item.get("rule_id", ""))
        message = normalize(item.get("message", "") or item.get("fail_message", ""))
        for evidence in item.get("evidence", []):
            ev = normalize(evidence)
            for building_id in buildings:
                match = re.search(rf"\b{re.escape(building_id)}:(floor-[A-Za-z0-9_-]+)", ev)
                if not match:
                    continue
                floor_id = match.group(1)
                text = f"{rule_id}: {message} ({ev})"
                if text not in issue_map[(building_id, floor_id)]:
                    issue_map[(building_id, floor_id)].append(text)

    for issue in report.get("architect_metrics_summary", {}).get("top_issues", []):
        ev = normalize(issue)
        for building_id in buildings:
            match = re.search(rf"\b{re.escape(building_id)}:(floor-[A-Za-z0-9_-]+)", ev)
            if match:
                floor_id = match.group(1)
                text = f"ARCH: {ev}"
                if text not in issue_map[(building_id, floor_id)]:
                    issue_map[(building_id, floor_id)].append(text)
    return expert_map, issue_map


def score_line(scores: dict[str, Any]) -> str:
    if not scores:
        return "score unavailable"
    parts = []
    for key in ["total", "circulation", "daylight", "mep", "utilization"]:
        if key in scores:
            try:
                parts.append(f"{key}={float(scores[key]):.1f}")
            except (TypeError, ValueError):
                parts.append(f"{key}={scores[key]}")
    return " | ".join(parts)


def floor_note_html(
    building_id: str,
    floor_id: str,
    selected: dict[str, Any],
    expert_rec: dict[str, Any] | None,
    issues: list[str],
    candidate_summary: dict[str, Any],
) -> str:
    selected_id = normalize(selected.get("id", ""))
    scores = selected.get("scores", {})
    expert_best = normalize((expert_rec or {}).get("expert_best", ""))
    expert_text = ""
    if expert_best:
        if expert_best == selected_id:
            expert_text = f"Expert weighting agrees with selected `{selected_id}`."
        else:
            expert_text = f"Expert weighting prefers `{expert_best}`; this copy follows export selection `{selected_id}`."
    issue_items = "".join(f"<li>{html.escape(item)}</li>" for item in issues[:3])
    if not issue_items:
        issue_items = "<li>No floor-specific warning was found in the latest report.</li>"
    mismatches = candidate_summary.get("rejected_assignments", [])
    mismatch_items = "".join(
        "<li>"
        f"{html.escape(item.get('slot_id', ''))}: "
        f"canonical {html.escape(item.get('canonical_room_target', '') or item.get('canonical_slot_name', ''))} "
        f"kept; candidate suggested {html.escape(item.get('candidate_room_local_id', '') or item.get('candidate_room_name', ''))}"
        "</li>"
        for item in mismatches[:3]
    )
    if not mismatch_items:
        mismatch_items = "<li>No candidate/canonical room-slot mismatch was found for this floor.</li>"
    return f"""
<div class="final-floor-note" data-final-building-id="{html.escape(building_id)}" data-final-floor-id="{html.escape(floor_id)}">
  <p><strong>Candidate selection:</strong> {html.escape(selected_id)} | {html.escape(score_line(scores))}</p>
  <p><strong>Canonical snapshot:</strong> visual room names, onclick targets, geometry, doors and windows are kept from the source HTML.</p>
  <p><strong>Candidate analysis:</strong> {candidate_summary.get("matched_assignment_count", 0)} matched / {candidate_summary.get("rejected_assignment_count", 0)} rejected / 0 applied to visible cells.</p>
  <p>{html.escape(expert_text or "No expert recommendation was recorded for this floor.")}</p>
  <ul class="final-candidate-mismatch">{mismatch_items}</ul>
  <ul>{issue_items}</ul>
</div>
"""


def summary_html(
    building_id: str,
    mode: str,
    selection: str,
    report: dict[str, Any],
    floor_count: int,
    candidate_assignment_count: int,
    rejected_assignment_count: int,
    applied_assignment_count: int,
    warnings: list[str],
) -> str:
    generated = normalize(report.get("generated_at", ""))
    hard_gate = normalize(report.get("hard_gate", "unknown")).upper()
    report_hash = normalize(report.get("report_hash", ""))[:12]
    warning_count = len(report.get("warnings", []))
    info_count = len(report.get("infos", []))
    warning_items = "".join(f"<li>{html.escape(item)}</li>" for item in warnings[:5])
    if not warning_items:
        warning_items = "<li>No building-specific warning was found in the latest report.</li>"
    return f"""
<section class="final-sync-summary" id="final-design-notes">
  <h2>Final Design Notes - Building {html.escape(building_id)}</h2>
  <p>This is a generated discussion copy. It keeps the canonical source layout and stores candidate analysis as metadata only.</p>
  <div class="final-sync-grid">
    <div class="final-sync-kpi"><b>{html.escape(mode)}</b><span>Mode</span></div>
    <div class="final-sync-kpi"><b>{html.escape(selection)}</b><span>Export selection</span></div>
    <div class="final-sync-kpi"><b>{html.escape(hard_gate)}</b><span>Hard gate</span></div>
    <div class="final-sync-kpi"><b>{floor_count}</b><span>Analyzed floors</span></div>
    <div class="final-sync-kpi"><b>{candidate_assignment_count}</b><span>Candidate assignments</span></div>
    <div class="final-sync-kpi"><b>{rejected_assignment_count}</b><span>Rejected visual moves</span></div>
    <div class="final-sync-kpi"><b>{applied_assignment_count}</b><span>Applied visual moves</span></div>
    <div class="final-sync-kpi"><b>{warning_count}/{info_count}</b><span>Warnings / Info</span></div>
  </div>
  <p>Report generated: {html.escape(generated)} | hash: {html.escape(report_hash)}</p>
  <ul>{warning_items}</ul>
</section>
"""


def add_style_block(soup: BeautifulSoup) -> None:
    if soup.find(id="final-design-sync-style"):
        return
    style = soup.new_tag("style", id="final-design-sync-style")
    style.string = STYLE_BLOCK
    if soup.head:
        soup.head.append(style)
    else:
        soup.insert(0, style)


def add_json_payload(soup: BeautifulSoup, payload: dict[str, Any]) -> None:
    old = soup.find(id="house-design-final-sync")
    if old:
        old.decompose()
    script = soup.new_tag("script", id="house-design-final-sync", type="application/json")
    script.string = json.dumps(payload, ensure_ascii=False, indent=2)
    if soup.body:
        soup.body.append(script)
    else:
        soup.append(script)


def analyze_cell_assignment(
    cell: Tag,
    slot_id: str,
    pair: dict[str, Any],
    room: dict[str, Any] | None,
) -> dict[str, Any]:
    room_uid = normalize(pair.get("room_uid", ""))
    candidate_local_id = room_local_id(room_uid)
    raw_room_name = normalize(pair.get("room_name", "")) or normalize((room or {}).get("name", ""))
    _, display_name = split_icon_name(raw_room_name)
    display_name = display_name or raw_room_name or room_uid
    canonical_target = parse_highlight_room(normalize(cell.get("onclick", "")))
    canonical_name = text_of(cell.select_one(".cell-name"))
    canonical_size = text_of(cell.select_one(".cell-size"))
    fit = pair.get("dimension_fit", {}) if isinstance(pair.get("dimension_fit", {}), dict) else {}
    matched = bool(canonical_target and candidate_local_id and canonical_target == candidate_local_id)
    reason = "same_room_target" if matched else "candidate_would_move_room_from_canonical_cell"
    if not canonical_target:
        reason = "missing_canonical_onclick_target"

    return {
        "slot_id": slot_id,
        "status": "matched" if matched else "rejected",
        "reason": reason,
        "canonical_room_target": canonical_target,
        "canonical_slot_name": canonical_name,
        "canonical_cell_size": canonical_size,
        "candidate_room_uid": room_uid,
        "candidate_room_local_id": candidate_local_id,
        "candidate_room_name": display_name,
        "dimension_fit": fit,
    }


def candidate_summary_for_floor(assignments: list[dict[str, Any]]) -> dict[str, Any]:
    matched = [item for item in assignments if item.get("status") == "matched"]
    rejected = [item for item in assignments if item.get("status") != "matched"]
    return {
        "candidate_assignment_count": len(assignments),
        "matched_assignment_count": len(matched),
        "rejected_assignment_count": len(rejected),
        "applied_assignment_count": 0,
        "matched_assignments": matched,
        "rejected_assignments": rejected,
    }


def building_warnings(report: dict[str, Any], building_id: str) -> list[str]:
    results: list[str] = []
    for item in [*report.get("critical_failures", []), *report.get("warnings", []), *report.get("infos", [])]:
        rule_id = normalize(item.get("rule_id", ""))
        message = normalize(item.get("message", "") or item.get("fail_message", ""))
        for evidence in item.get("evidence", []):
            ev = normalize(evidence)
            if ev.startswith(f"{building_id}:") or f" {building_id}:" in ev:
                text = f"{rule_id}: {message} ({ev})"
                if text not in results:
                    results.append(text)
    return results


def export_building_html(
    building_id: str,
    mode: str,
    selection: str,
    program_index: dict[tuple[str, str], dict[str, Any]],
    candidate_index: dict[tuple[str, str], dict[str, Any]],
    report: dict[str, Any],
    expert_map: dict[tuple[str, str], dict[str, Any]],
    issue_map: dict[tuple[str, str], list[str]],
    output_dir: Path,
) -> dict[str, Any]:
    source_name = HTML_FILE_MAP[building_id]
    source_path = ROOT / source_name
    if not source_path.exists():
        raise SystemExit(f"Missing canonical HTML file: {source_path}")

    soup = BeautifulSoup(source_path.read_text(encoding="utf-8"), "html.parser")
    add_style_block(soup)

    updated_floors: list[dict[str, Any]] = []
    candidate_assignment_total = 0
    matched_assignment_total = 0
    rejected_assignment_total = 0
    applied_assignment_total = 0

    for floor_node in soup.select(".floor-plan"):
        floor_id = normalize(floor_node.get("id", ""))
        if not floor_id:
            continue
        floor_result = candidate_index.get((building_id, floor_id))
        program_floor = program_index.get((building_id, floor_id), {})
        if not floor_result or not program_floor:
            continue

        selected = select_candidate(floor_result, selection)
        if not selected:
            continue

        candidate_id = normalize(selected.get("id", ""))
        floor_program = program_floor.get("floor", program_floor)
        pair_by_slot = {normalize(pair.get("slot_id", "")): pair for pair in selected.get("pair_details", [])}
        rooms_by_uid = program_floor.get("rooms_by_uid", {})
        cells = floor_node.select(".plan-grid-visual .plan-cell")

        assignments: list[dict[str, Any]] = []
        for idx, cell in enumerate(cells, start=1):
            slot_id = f"slot-{idx}"
            pair = pair_by_slot.get(slot_id)
            if not pair:
                continue
            room_uid = normalize(pair.get("room_uid", ""))
            room = rooms_by_uid.get(room_uid)
            assignments.append(analyze_cell_assignment(cell, slot_id, pair, room))

        if assignments:
            candidate_summary = candidate_summary_for_floor(assignments)
            candidate_assignment_total += candidate_summary["candidate_assignment_count"]
            matched_assignment_total += candidate_summary["matched_assignment_count"]
            rejected_assignment_total += candidate_summary["rejected_assignment_count"]
            expert_rec = expert_map.get((building_id, floor_id))
            issues = issue_map.get((building_id, floor_id), [])
            header = floor_node.select_one(".floor-header")
            note_html = floor_note_html(building_id, floor_id, selected, expert_rec, issues, candidate_summary)
            if header:
                insert_after(header, note_html)
            else:
                append_fragment(floor_node, note_html, position=0)
            spatial_summary = {
                "orientation": floor_program.get("orientation", {}),
                "cell_spatial": [
                    {
                        "order": cell.get("order"),
                        "name": normalize(cell.get("name", "")),
                        "target_room_uid": normalize(cell.get("target_room_uid", "")),
                        "spatial": cell.get("spatial", {}),
                    }
                    for cell in floor_program.get("plan_cells", [])
                ],
            }
            updated_floors.append(
                {
                    "building_id": building_id,
                    "floor_id": floor_id,
                    "selected_candidate_id": candidate_id,
                    "scores": selected.get("scores", {}),
                    "candidate_assignment_count": candidate_summary["candidate_assignment_count"],
                    "matched_assignment_count": candidate_summary["matched_assignment_count"],
                    "rejected_assignment_count": candidate_summary["rejected_assignment_count"],
                    "applied_assignment_count": candidate_summary["applied_assignment_count"],
                    "assignments": assignments,
                    "rejected_assignments": candidate_summary["rejected_assignments"],
                    "expert_best": normalize((expert_rec or {}).get("expert_best", "")),
                    "pipeline_best": normalize((expert_rec or {}).get("pipeline_best", "")),
                    "orientation": spatial_summary["orientation"],
                    "spatial_summary": spatial_summary,
                    "floor_issues": issues[:10],
                }
            )

    append_summary_to_container(
        soup=soup,
        building_id=building_id,
        mode=mode,
        selection=selection,
        report=report,
        floor_count=len(updated_floors),
        candidate_assignment_count=candidate_assignment_total,
        rejected_assignment_count=rejected_assignment_total,
        applied_assignment_count=applied_assignment_total,
    )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "sync_mode": SYNC_MODE,
        "generated_at": now_iso(),
        "building_id": building_id,
        "mode": mode,
        "selection": selection,
        "source_file": source_name,
        "report_hash": normalize(report.get("report_hash", "")),
        "report_generated_at": normalize(report.get("generated_at", "")),
        "updated_floor_count": len(updated_floors),
        "analyzed_floor_count": len(updated_floors),
        "candidate_assignment_count": candidate_assignment_total,
        "matched_assignment_count": matched_assignment_total,
        "rejected_assignment_count": rejected_assignment_total,
        "applied_assignment_count": applied_assignment_total,
        "floors": updated_floors,
    }
    add_json_payload(soup, payload)

    output_path = output_dir / f"{Path(source_name).stem}.final.html"
    output_path.write_text(str(soup), encoding="utf-8")
    return {
        "building_id": building_id,
        "source_file": source_name,
        "output_file": output_path.name,
        "output_path": str(output_path.relative_to(ROOT)),
        "updated_floor_count": len(updated_floors),
        "analyzed_floor_count": len(updated_floors),
        "candidate_assignment_count": candidate_assignment_total,
        "matched_assignment_count": matched_assignment_total,
        "rejected_assignment_count": rejected_assignment_total,
        "applied_assignment_count": applied_assignment_total,
        "floors": [
            {
                "floor_id": floor["floor_id"],
                "selected_candidate_id": floor["selected_candidate_id"],
                "candidate_assignment_count": floor["candidate_assignment_count"],
                "matched_assignment_count": floor["matched_assignment_count"],
                "rejected_assignment_count": floor["rejected_assignment_count"],
                "applied_assignment_count": floor["applied_assignment_count"],
                "expert_best": floor["expert_best"],
            }
            for floor in updated_floors
        ],
    }


def append_summary_to_container(
    soup: BeautifulSoup,
    building_id: str,
    mode: str,
    selection: str,
    report: dict[str, Any],
    floor_count: int,
    candidate_assignment_count: int,
    rejected_assignment_count: int,
    applied_assignment_count: int,
) -> None:
    warnings = building_warnings(report, building_id)
    fragment = summary_html(
        building_id=building_id,
        mode=mode,
        selection=selection,
        report=report,
        floor_count=floor_count,
        candidate_assignment_count=candidate_assignment_count,
        rejected_assignment_count=rejected_assignment_count,
        applied_assignment_count=applied_assignment_count,
        warnings=warnings,
    )
    container = soup.select_one(".container")
    if container:
        append_fragment(container, fragment, position=0)
    elif soup.body:
        append_fragment(soup.body, fragment, position=0)
    else:
        append_fragment(soup, fragment, position=0)


def render_index(records: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    cards = []
    for rec in records:
        floors = ", ".join(
            f"{floor['floor_id']}:{floor['selected_candidate_id']}" for floor in rec.get("floors", [])
        )
        cards.append(
            f"""
      <article class="card">
        <h2>Building {html.escape(rec['building_id'])}</h2>
        <p>{rec['analyzed_floor_count']} floors | {rec['candidate_assignment_count']} candidate assignments | {rec['rejected_assignment_count']} rejected visual moves</p>
        <p class="muted">{html.escape(floors)}</p>
        <a href="{html.escape(rec['output_file'])}">{html.escape(rec['output_file'])}</a>
      </article>
"""
        )
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Final Design HTML Index</title>
  <style>
    body {{ margin: 0; padding: 24px; font-family: "Segoe UI", "Microsoft JhengHei", sans-serif; background: #0f172a; color: #e2e8f0; }}
    h1 {{ margin: 0 0 8px; color: #93c5fd; }}
    .meta {{ color: #94a3b8; margin-bottom: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }}
    .card {{ border: 1px solid #334155; border-radius: 10px; padding: 14px; background: #111c31; }}
    .card h2 {{ margin: 0 0 8px; font-size: 1rem; }}
    .card a {{ color: #5eead4; }}
    .muted {{ color: #94a3b8; font-size: .85rem; }}
  </style>
</head>
<body>
  <h1>Final Design HTML Index</h1>
  <div class="meta">Generated: {html.escape(manifest.get("generated_at", ""))} | mode={html.escape(manifest.get("mode", ""))} | selection={html.escape(manifest.get("selection", ""))} | sync={html.escape(manifest.get("sync_mode", ""))}</div>
  <section class="grid">
    {''.join(cards)}
  </section>
</body>
</html>
"""


def svg_manifest_selection() -> str:
    if not SVG_MANIFEST_FILE.exists():
        return ""
    try:
        payload = json.loads(SVG_MANIFEST_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return normalize(payload.get("candidate_selection", ""))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export final-design discussion HTML copies.")
    parser.add_argument("--mode", choices=["concept", "draft", "ifc"], default="draft")
    parser.add_argument("--selection", choices=["auto", "baseline", "best"], default="auto")
    parser.add_argument("--buildings", default="A,B,C")
    parser.add_argument("--program", type=Path, default=PROGRAM_FILE)
    parser.add_argument("--candidates", type=Path, default=CANDIDATES_FILE)
    parser.add_argument("--report", type=Path, default=REPORT_FILE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected_buildings = parse_buildings(args.buildings)
    resolved_selection = resolve_selection(args.mode, args.selection)

    program = load_json(args.program.resolve(), "room program")
    candidates = load_json(args.candidates.resolve(), "layout candidates")
    report = load_json(args.report.resolve(), "expert report")

    program_index = build_program_index(program)
    candidate_index = build_candidate_index(candidates)
    expert_map, issue_map = build_report_indexes(report, selected_buildings)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for building_id in selected_buildings:
        records.append(
            export_building_html(
                building_id=building_id,
                mode=args.mode,
                selection=resolved_selection,
                program_index=program_index,
                candidate_index=candidate_index,
                report=report,
                expert_map=expert_map,
                issue_map=issue_map,
                output_dir=output_dir,
            )
        )

    svg_selection = svg_manifest_selection()
    warnings = []
    if svg_selection and svg_selection != resolved_selection:
        warnings.append(
            f"SVG manifest selection is '{svg_selection}', but final HTML selection is '{resolved_selection}'. Rerun the workflow or SVG export with the same selection if needed."
        )

    candidate_assignment_count = sum(int(rec.get("candidate_assignment_count", 0) or 0) for rec in records)
    matched_assignment_count = sum(int(rec.get("matched_assignment_count", 0) or 0) for rec in records)
    rejected_assignment_count = sum(int(rec.get("rejected_assignment_count", 0) or 0) for rec in records)
    applied_assignment_count = sum(int(rec.get("applied_assignment_count", 0) or 0) for rec in records)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "sync_mode": SYNC_MODE,
        "generated_at": now_iso(),
        "mode": args.mode,
        "selection": resolved_selection,
        "requested_selection": args.selection,
        "buildings": selected_buildings,
        "candidate_assignment_count": candidate_assignment_count,
        "matched_assignment_count": matched_assignment_count,
        "rejected_assignment_count": rejected_assignment_count,
        "applied_assignment_count": applied_assignment_count,
        "source_files": {
            "program": str(args.program.resolve().relative_to(ROOT)),
            "candidates": str(args.candidates.resolve().relative_to(ROOT)),
            "report": str(args.report.resolve().relative_to(ROOT)),
            "svg_manifest": str(SVG_MANIFEST_FILE.relative_to(ROOT)) if SVG_MANIFEST_FILE.exists() else "",
        },
        "report_hash": normalize(report.get("report_hash", "")),
        "svg_manifest_selection": svg_selection,
        "warnings": warnings,
        "exports": records,
    }
    manifest_path = output_dir / "manifest.json"
    index_path = output_dir / "index.html"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    index_path.write_text(render_index(records, manifest), encoding="utf-8")

    print(f"Final design HTML output: {output_dir}")
    print(f"Selection: {resolved_selection}")
    print(f"Sync mode: {SYNC_MODE}")
    print(f"Exported buildings: {len(records)}")
    print(f"Candidate assignments: {candidate_assignment_count}")
    print(f"Rejected visual moves: {rejected_assignment_count}")
    print(f"Applied visual moves: {applied_assignment_count}")
    print(f"Manifest: {manifest_path}")
    print(f"Index: {index_path}")
    for warning in warnings:
        print(f"[WARN] {warning}", file=sys.stderr)


if __name__ == "__main__":
    main()

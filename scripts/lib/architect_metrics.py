#!/usr/bin/env python3
"""Concept-level architectural metrics derived from room_program.json.

These helpers adapt calculator-style methods from Skills-Architects for early
design screening. They are advisory only; formal Taiwan code, daylight,
egress, ventilation, and structural signoff remains professional work.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "architect-metrics-v1"
STATUS_OK = "ok"
STATUS_ADVISORY = "advisory"
STATUS_MISSING = "missing_data"
STATUS_PROFESSIONAL = "professional_required"
ALLOWED_STATUSES = {STATUS_OK, STATUS_ADVISORY, STATUS_MISSING, STATUS_PROFESSIONAL}
AUTO_GEOMETRY_SOURCES = {"auto-grid-v1", "heuristic", "estimated"}

PUBLIC_ROOM_KEYWORDS = ["客廳", "玄關", "餐廳", "神明廳", "娛樂", "書房", "茶水"]
PRIVATE_ROOM_KEYWORDS = ["主臥", "臥", "客房", "孝親", "房"]
WET_ROOM_KEYWORDS = ["衛", "浴", "廁", "廚", "洗", "陽台"]
SERVICE_ROOM_KEYWORDS = [
    "mdf", "idf", "機櫃", "設備", "機房", "儲藏", "配電", "弱電",
    "水塔", "泵", "熱泵", "vf800", "太陽能",
]
STRUCTURE_REVIEW_KEYWORDS = [
    "水塔",
    "熱泵",
    "vf800",
    "太陽能",
    "儲能",
    "棚架",
    "跑步機",
    "運動",
]
STRUCTURE_EVIDENCE_KEYWORDS = ["結構", "技師", "載重", "承載", "錨定", "基座", "防水", "維修"]
STRUCTURE_REVIEW_MARKERS = {"1", "true", "yes", "required", "professional_required"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_match_text(value: str) -> str:
    value = normalize_whitespace(value).lower()
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value)


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def mm_to_m(value: Any) -> float:
    return to_float(value, 0.0) / 1000.0


def geometry_provenance(floor: dict[str, Any]) -> tuple[str, str]:
    source = str(floor.get("geometry_source", "") or "").strip().lower()
    if source in AUTO_GEOMETRY_SOURCES or source.startswith("auto-"):
        return source or "auto-derived", "auto-derived"
    if not source:
        return "unknown", "unknown"
    return source, "declared"


def provenance_confidence(floor: dict[str, Any], default: str) -> tuple[str, str]:
    source, provenance = geometry_provenance(floor)
    return ("low" if provenance == "auto-derived" else default), source


def has_any_keyword(text: str, keywords: list[str]) -> bool:
    return any(normalize_match_text(keyword) in text for keyword in keywords)


def safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def metric_item(
    building_id: str,
    floor_id: str,
    room_uid: str,
    metric_type: str,
    inputs: dict[str, Any],
    result: dict[str, Any],
    status: str,
    confidence: str,
    issues: list[str] | None = None,
) -> dict[str, Any]:
    if status not in ALLOWED_STATUSES:
        status = STATUS_ADVISORY
    return {
        "building_id": building_id,
        "floor_id": floor_id,
        "room_uid": room_uid,
        "metric_type": metric_type,
        "inputs": inputs,
        "result": result,
        "status": status,
        "confidence": confidence,
        "issues": issues or [],
    }


def metric_issue_label(metric: dict[str, Any]) -> str:
    metric_type = normalize_whitespace(str(metric.get("metric_type", "")))
    room_uid = normalize_whitespace(str(metric.get("room_uid", "")))
    if room_uid:
        label = f"{room_uid}:{metric_type}"
    else:
        label = ":".join(
            value
            for value in (
                normalize_whitespace(str(metric.get("building_id", ""))),
                normalize_whitespace(str(metric.get("floor_id", ""))),
                metric_type,
            )
            if value
        )
    issues = metric.get("issues", [])
    first_issue = normalize_whitespace(str(issues[0])) if issues else normalize_whitespace(str(metric.get("status", "")))
    return f"{label} - {first_issue}" if first_issue else label


def action_group_for_metric(metric: dict[str, Any]) -> str:
    metric_type = normalize_whitespace(str(metric.get("metric_type", "")))
    room_uid = normalize_whitespace(str(metric.get("room_uid", "")))
    text = " ".join(str(issue) for issue in metric.get("issues", []))
    combined = normalize_match_text(f"{room_uid} {text}")
    if metric_type == "daylight_factor":
        return "architect_daylight_ventilation"
    if metric_type == "door_width":
        return "accessibility_door_width"
    if metric_type == "structure_load_review":
        return "structural_rf_equipment"
    if any(token in combined for token in ["heatpump", "pump", "vf800", "熱泵", "加壓"]):
        return "mep_rf_equipment"
    return "owner_design_decision"


def build_action_groups(metrics: list[dict[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for metric in metrics:
        if metric.get("status") == STATUS_OK:
            continue
        group = action_group_for_metric(metric)
        groups.setdefault(group, []).append(metric_issue_label(metric))
    return {key: values[:20] for key, values in groups.items() if values}


def architect_metric_defaults(defaults: dict[str, Any]) -> dict[str, Any]:
    raw = defaults.get("architect_metrics", {})
    return {
        "room_height_mm": int(to_float(raw.get("room_height_mm"), 3000)),
        "window_sill_height_mm": int(to_float(raw.get("window_sill_height_mm"), 900)),
        "window_height_mm": int(to_float(raw.get("window_height_mm"), 1200)),
        "glazing_transmittance": to_float(raw.get("glazing_transmittance"), 0.65),
        "average_reflectance": to_float(raw.get("average_reflectance"), 0.5),
        "daylight_target_pct": to_float(raw.get("daylight_target_pct"), 2.0),
        "egress_proxy_warning_m": to_float(raw.get("egress_proxy_warning_m"), 30.0),
    }


def geometry_dimensions_m(item: dict[str, Any]) -> tuple[float, float]:
    geometry = item.get("geometry_mm") or {}
    width_m = mm_to_m(geometry.get("w_mm"))
    depth_m = mm_to_m(geometry.get("h_mm"))
    if width_m > 0 and depth_m > 0:
        return width_m, depth_m

    area_metrics = item.get("area_metrics") or item.get("size_metrics") or {}
    dim = area_metrics.get("dimension_m") or {}
    width_m = to_float(dim.get("width_m"), 0.0)
    depth_m = to_float(dim.get("depth_m"), 0.0)
    return width_m, depth_m


def geometry_area_sqm(item: dict[str, Any]) -> float:
    width_m, depth_m = geometry_dimensions_m(item)
    if width_m > 0 and depth_m > 0:
        return width_m * depth_m
    area_metrics = item.get("area_metrics") or item.get("size_metrics") or {}
    return to_float(area_metrics.get("dimension_sqm"), 0.0)


def floor_area_sqm(floor: dict[str, Any]) -> float:
    geometry = floor.get("geometry_mm") or {}
    width_m = mm_to_m(geometry.get("width_mm"))
    depth_m = mm_to_m(geometry.get("depth_mm"))
    if width_m > 0 and depth_m > 0:
        return width_m * depth_m
    return 0.0


def cell_center_m(cell: dict[str, Any]) -> tuple[float, float] | None:
    geometry = cell.get("geometry_mm") or {}
    x = mm_to_m(geometry.get("x_mm"))
    y = mm_to_m(geometry.get("y_mm"))
    w = mm_to_m(geometry.get("w_mm"))
    h = mm_to_m(geometry.get("h_mm"))
    if w <= 0 or h <= 0:
        return None
    return (x + (w / 2.0), y + (h / 2.0))


def cell_maps(floor: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_slot: dict[str, dict[str, Any]] = {}
    by_uid: dict[str, dict[str, Any]] = {}
    for cell in floor.get("plan_cells", []):
        slot_id = f"slot-{cell.get('order', '')}"
        by_slot[slot_id] = cell
        uid = normalize_whitespace(str(cell.get("target_room_uid", "")))
        if uid:
            by_uid[uid] = cell
    return by_slot, by_uid


def matched_cell(room: dict[str, Any], slot_by_id: dict[str, dict[str, Any]], slot_by_uid: dict[str, dict[str, Any]]) -> dict[str, Any]:
    uid = normalize_whitespace(str(room.get("uid", "")))
    if uid in slot_by_uid:
        return slot_by_uid[uid]
    slot_id = normalize_whitespace(str(room.get("target_cell_id", "")))
    if slot_id in slot_by_id:
        return slot_by_id[slot_id]
    return {}


def room_text(room: dict[str, Any], cell: dict[str, Any] | None = None) -> str:
    parts: list[str] = [str(room.get("name", ""))]
    parts.extend(str(v) for v in room.get("notes_normalized", []))
    parts.extend(str(v) for v in room.get("notes_rendered", []))
    if cell:
        parts.append(str(cell.get("name", "")))
        parts.extend(str(v) for v in cell.get("badges", []))
        parts.extend(str(v) for v in cell.get("classes", []))
    return " ".join(parts)


def structure_trigger_text(
    room: dict[str, Any],
    cell: dict[str, Any] | None = None,
) -> str:
    parts = [str(room.get("name", ""))]
    if cell:
        parts.append(str(cell.get("name", "")))
    return " ".join(parts)


def has_structure_review_marker(
    room: dict[str, Any],
    cell: dict[str, Any] | None = None,
) -> bool:
    values = [room.get("structural_review")]
    if cell:
        values.append(cell.get("structural_review"))
    return any(
        normalize_whitespace(str(value)).lower() in STRUCTURE_REVIEW_MARKERS
        for value in values
        if value is not None
    )


def needs_daylight(room: dict[str, Any]) -> bool:
    declared = (room.get("semantics") or {}).get("daylight_required")
    if declared is not None:
        return bool(declared)
    text = normalize_match_text(str(room.get("name", "")))
    return has_any_keyword(text, PUBLIC_ROOM_KEYWORDS) or has_any_keyword(text, PRIVATE_ROOM_KEYWORDS)


def is_service_room(room: dict[str, Any]) -> bool:
    role = str((room.get("semantics") or {}).get("room_role", ""))
    if role in {"equipment", "mechanical", "service"}:
        return True
    text = normalize_match_text(str(room.get("name", "")))
    return has_any_keyword(text, SERVICE_ROOM_KEYWORDS)


def is_bath_or_wet_room(room: dict[str, Any]) -> bool:
    text = normalize_match_text(str(room.get("name", "")))
    return has_any_keyword(text, WET_ROOM_KEYWORDS)


def daylight_factor(
    room_width_m: float,
    room_depth_m: float,
    room_height_m: float,
    window_width_m: float,
    window_height_m: float,
    window_sill_height_m: float,
    glazing_transmittance: float,
    average_reflectance: float,
) -> dict[str, float]:
    window_area = window_width_m * window_height_m
    floor_area = room_width_m * room_depth_m
    ceiling_area = floor_area
    wall_long = 2 * (room_depth_m * room_height_m)
    wall_short = 2 * (room_width_m * room_height_m)
    total_surface_area = floor_area + ceiling_area + wall_long + wall_short
    window_head_m = window_sill_height_m + window_height_m
    theta_rad = math.atan2(window_head_m, max(room_depth_m, 0.001))
    theta_deg = math.degrees(theta_rad)
    theta_factor = theta_deg / 90.0
    denominator = total_surface_area * (1 - average_reflectance * average_reflectance)
    factor_pct = 0.0
    if denominator > 0:
        factor_pct = (window_area * glazing_transmittance * theta_factor) / denominator * 100.0
    return {
        "window_area_m2": round(window_area, 3),
        "floor_area_m2": round(floor_area, 3),
        "total_surface_area_m2": round(total_surface_area, 3),
        "window_to_floor_ratio_pct": round((window_area / floor_area) * 100.0, 2) if floor_area > 0 else 0.0,
        "visible_sky_angle_deg": round(theta_deg, 1),
        "sky_angle_factor": round(theta_factor, 4),
        "daylight_factor_pct": round(factor_pct, 2),
    }


def build_floor_area_metric(building_id: str, floor: dict[str, Any]) -> dict[str, Any]:
    area = floor_area_sqm(floor)
    geometry = floor.get("geometry_mm") or {}
    confidence, geometry_source = provenance_confidence(floor, "high")
    if area <= 0:
        return metric_item(
            building_id,
            str(floor.get("id", "")),
            "",
            "floor_area",
            {"geometry_mm": geometry, "geometry_source": geometry_source},
            {"floor_area_sqm": 0.0},
            STATUS_MISSING,
            "low",
            ["missing floor width/depth geometry"],
        )
    return metric_item(
        building_id,
        str(floor.get("id", "")),
        "",
        "floor_area",
        {"geometry_mm": geometry, "geometry_source": geometry_source},
        {"floor_area_sqm": round(area, 2)},
        STATUS_ADVISORY if confidence == "low" else STATUS_OK,
        confidence,
        ["floor dimensions are auto-derived; replace with surveyed/CAD geometry"]
        if confidence == "low"
        else [],
    )


def build_daylight_metric(
    building_id: str,
    floor: dict[str, Any],
    room: dict[str, Any],
    cell: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    floor_id = str(floor.get("id", ""))
    uid = str(room.get("uid", ""))
    room_width_m, room_depth_m = geometry_dimensions_m(room)
    if room_width_m <= 0 or room_depth_m <= 0:
        room_width_m, room_depth_m = geometry_dimensions_m(cell)

    metric_defaults = architect_metric_defaults(defaults)
    confidence, geometry_source = provenance_confidence(floor, "medium")
    room_height_m = mm_to_m(metric_defaults["room_height_mm"])
    window_height_m = mm_to_m(metric_defaults["window_height_mm"])
    window_sill_m = mm_to_m(metric_defaults["window_sill_height_mm"])
    openings = cell.get("openings_mm") or {}
    raw_window_width_m = mm_to_m(openings.get("window_mm"))
    target = metric_defaults["daylight_target_pct"]
    issues: list[str] = []

    if room_width_m <= 0 or room_depth_m <= 0:
        return metric_item(
            building_id,
            floor_id,
            uid,
            "daylight_factor",
            {"method": "BRE simplified daylight factor adapted from Skills-Architects"},
            {"daylight_factor_pct": 0.0, "target_daylight_factor_pct": target},
            STATUS_MISSING,
            "low",
            ["missing room/cell geometry for daylight estimate"],
        )

    if raw_window_width_m <= 0:
        return metric_item(
            building_id,
            floor_id,
            uid,
            "daylight_factor",
            {
                "room_width_m": round(room_width_m, 2),
                "room_depth_m": round(room_depth_m, 2),
                "window_width_m": 0.0,
                "geometry_source": geometry_source,
                "method": "BRE simplified daylight factor adapted from Skills-Architects",
            },
            {"daylight_factor_pct": 0.0, "target_daylight_factor_pct": target},
            STATUS_MISSING,
            confidence,
            ["missing window width for daylight-sensitive room"],
        )

    window_width_m = raw_window_width_m
    if window_width_m > room_width_m:
        issues.append("window width exceeds room width; clamped for advisory estimate")
        window_width_m = room_width_m

    result = daylight_factor(
        room_width_m=room_width_m,
        room_depth_m=room_depth_m,
        room_height_m=room_height_m,
        window_width_m=window_width_m,
        window_height_m=window_height_m,
        window_sill_height_m=window_sill_m,
        glazing_transmittance=metric_defaults["glazing_transmittance"],
        average_reflectance=metric_defaults["average_reflectance"],
    )
    result["target_daylight_factor_pct"] = target
    status = STATUS_OK if result["daylight_factor_pct"] >= target else STATUS_ADVISORY
    if status == STATUS_ADVISORY:
        issues.append("concept daylight factor is below target; formal daylight/ventilation calculation still required")
    if confidence == "low":
        status = STATUS_ADVISORY
        issues.append("daylight estimate uses auto-derived geometry/openings")

    return metric_item(
        building_id,
        floor_id,
        uid,
        "daylight_factor",
        {
            "room_width_m": round(room_width_m, 2),
            "room_depth_m": round(room_depth_m, 2),
            "room_height_m": round(room_height_m, 2),
            "window_width_m": round(window_width_m, 2),
            "raw_window_width_m": round(raw_window_width_m, 2),
            "geometry_source": geometry_source,
            "window_height_m": round(window_height_m, 2),
            "window_sill_height_m": round(window_sill_m, 2),
            "glazing_transmittance": metric_defaults["glazing_transmittance"],
            "average_reflectance": metric_defaults["average_reflectance"],
            "method": "BRE simplified daylight factor adapted from Skills-Architects; advisory only",
        },
        result,
        status,
        confidence,
        issues,
    )


def build_door_width_metric(
    building_id: str,
    floor: dict[str, Any],
    room: dict[str, Any],
    cell: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    floor_id = str(floor.get("id", ""))
    uid = str(room.get("uid", ""))
    openings = cell.get("openings_mm") or {}
    door_mm = to_float(openings.get("door_mm"), 0.0)
    confidence, geometry_source = provenance_confidence(floor, "high")
    door_defaults = (defaults.get("geometry") or {}).get("door_width_mm") or {}
    semantics = room.get("semantics") or {}
    if bool(cell.get("is_entry")):
        category = "entry"
    elif bool(semantics.get("is_accessible")):
        category = "accessible"
    elif is_bath_or_wet_room(room):
        category = "bathroom"
    elif is_service_room(room):
        category = "service"
    else:
        category = "interior"
    minimum = int(to_float(door_defaults.get(category), 900 if category == "accessible" else 800))

    if door_mm <= 0:
        return metric_item(
            building_id,
            floor_id,
            uid,
            "door_width",
            {"category": category, "minimum_mm": minimum, "geometry_source": geometry_source},
            {"door_width_mm": 0},
            STATUS_MISSING,
            confidence,
            ["missing door width metadata"],
        )

    status = STATUS_OK if door_mm >= minimum else STATUS_ADVISORY
    issues = [] if status == STATUS_OK else [f"door width {door_mm:g}mm is below advisory minimum {minimum}mm"]
    return metric_item(
        building_id,
        floor_id,
        uid,
        "door_width",
        {"category": category, "minimum_mm": minimum, "geometry_source": geometry_source},
        {"door_width_mm": round(door_mm, 1)},
        status,
        confidence,
        issues,
    )


def build_egress_proxy_metric(building_id: str, floor: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    floor_id = str(floor.get("id", ""))
    cells = [cell for cell in floor.get("plan_cells", []) if cell_center_m(cell)]
    entry_cells = [cell for cell in cells if bool(cell.get("is_entry"))]
    stair_cells = [
        cell
        for cell in cells
        if has_any_keyword(
            normalize_match_text(
                " ".join(
                    [
                        str(cell.get("name", "")),
                        " ".join(str(v) for v in cell.get("badges", [])),
                        " ".join(str(v) for v in cell.get("classes", [])),
                    ]
                )
            ),
            ["樓梯", "梯廳", "梯間", "走廊", "玄關", "stair", "corridor"],
        )
    ]
    warning_m = architect_metric_defaults(defaults)["egress_proxy_warning_m"]
    if not cells:
        return metric_item(
            building_id,
            floor_id,
            "",
            "egress_distance_proxy",
            {"method": "cell-center direct distance proxy"},
            {"max_proxy_direct_distance_m": 0.0},
            STATUS_MISSING,
            "low",
            ["missing cell geometry for egress proxy"],
        )

    anchor_cells = entry_cells if len(entry_cells) == 1 else stair_cells[:1]
    if not anchor_cells:
        floor_label = normalize_match_text(
            " ".join(str(floor.get(key, "")) for key in ("id", "title", "tab_label"))
        )
        is_roof = "rf" in floor_label or "屋頂" in floor_label
        return metric_item(
            building_id,
            floor_id,
            "",
            "egress_distance_proxy",
            {"method": "cell-center direct distance proxy", "entry_count": len(entry_cells)},
            {"max_proxy_direct_distance_m": 0.0},
            STATUS_PROFESSIONAL if is_roof else STATUS_MISSING,
            "low" if is_roof else "medium",
            [
                "roof access route is not modeled; confirm stair/hatch and maintenance egress professionally"
                if is_roof
                else "egress proxy requires one entry marker or stair/landing cell"
            ],
        )

    anchor = anchor_cells[0]
    anchor_center = cell_center_m(anchor)
    anchor_type = "entry" if anchor in entry_cells else "stair"
    assert anchor_center is not None
    distances: list[float] = []
    farthest_cell = ""
    for cell in cells:
        center = cell_center_m(cell)
        if center is None:
            continue
        distance = math.dist(anchor_center, center)
        distances.append(distance)
        if distance == max(distances):
            farthest_cell = str(cell.get("name", ""))

    max_distance = max(distances) if distances else 0.0
    issues = ["formal egress route and travel distance calculation remains professional work"]
    if max_distance > warning_m:
        issues.append(f"proxy distance {max_distance:.1f}m exceeds advisory watch threshold {warning_m:.1f}m")

    return metric_item(
        building_id,
        floor_id,
        "",
        "egress_distance_proxy",
        {
            "method": "cell-center direct distance proxy; not code travel path",
            "anchor_cell": anchor.get("name", ""),
            "anchor_type": anchor_type,
            "warning_threshold_m": warning_m,
        },
        {
            "max_proxy_direct_distance_m": round(max_distance, 2),
            "avg_proxy_direct_distance_m": round(sum(distances) / len(distances), 2) if distances else 0.0,
            "farthest_cell": farthest_cell,
        },
        STATUS_PROFESSIONAL,
        "medium",
        issues,
    )


def build_structure_review_metric(
    building_id: str,
    floor: dict[str, Any],
    room: dict[str, Any],
    cell: dict[str, Any],
) -> dict[str, Any] | None:
    trigger_text = normalize_match_text(structure_trigger_text(room, cell))
    explicit_marker = has_structure_review_marker(room, cell)
    matched_keywords = [
        keyword
        for keyword in STRUCTURE_REVIEW_KEYWORDS
        if normalize_match_text(keyword) in trigger_text
    ]
    if not matched_keywords and not explicit_marker:
        return None

    text = room_text(room, cell)
    normalized = normalize_match_text(text)
    matched_evidence = [keyword for keyword in STRUCTURE_EVIDENCE_KEYWORDS if normalize_match_text(keyword) in normalized]
    essential = {"結構", "技師", "載重", "承載"}
    has_essential = explicit_marker or bool(set(matched_evidence) & essential)
    status = STATUS_PROFESSIONAL if has_essential else STATUS_MISSING
    issues = ["formal structural review/signoff is required for load, anchoring, waterproofing, and maintenance path"]
    if not has_essential:
        issues.append("missing explicit structural/load review wording in room notes")

    return metric_item(
        building_id,
        str(floor.get("id", "")),
        str(room.get("uid", "")),
        "structure_load_review",
        {
            "matched_keywords": matched_keywords,
            "explicit_marker": explicit_marker,
            "review_terms_found": matched_evidence,
        },
        {
            "requires_professional_review": True,
            "has_load_or_structural_note": has_essential,
        },
        status,
        "medium",
        issues,
    )


def evaluate_program(
    program: dict[str, Any],
    defaults: dict[str, Any],
    selected_buildings: list[str] | None = None,
) -> dict[str, Any]:
    selected = {value.upper() for value in (selected_buildings or ["A", "B", "C", "STORAGE"])}
    metrics: list[dict[str, Any]] = []
    skipped_floors: list[dict[str, str]] = []
    non_floor_sections: list[dict[str, str]] = []
    evaluated_floor_count = 0

    for building in program.get("buildings", []):
        building_id = str(building.get("id", "")).upper()
        if building_id not in selected:
            continue
        for floor in building.get("floors", []):
            floor_id = str(floor.get("id", ""))
            cells = floor.get("plan_cells", [])
            if not cells:
                non_floor_sections.append(
                    {
                        "building_id": building_id,
                        "floor_id": floor_id,
                        "record_type": str(floor.get("record_type", "section")),
                    }
                )
                continue

            evaluated_floor_count += 1
            metrics.append(build_floor_area_metric(building_id, floor))
            metrics.append(build_egress_proxy_metric(building_id, floor, defaults))
            slot_by_id, slot_by_uid = cell_maps(floor)

            for room in floor.get("rooms", []):
                cell = matched_cell(room, slot_by_id, slot_by_uid)
                if needs_daylight(room):
                    metrics.append(build_daylight_metric(building_id, floor, room, cell, defaults))
                metrics.append(build_door_width_metric(building_id, floor, room, cell, defaults))
                structure_metric = build_structure_review_metric(building_id, floor, room, cell)
                if structure_metric:
                    metrics.append(structure_metric)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "source_program_schema": program.get("schema_version", ""),
        "selected_buildings": sorted(selected),
        "evaluated_floor_count": evaluated_floor_count,
        "skipped_floor_count": len(skipped_floors),
        "non_floor_section_count": len(non_floor_sections),
        "metrics_count": len(metrics),
        "metrics": metrics,
        "skipped_floors": skipped_floors,
        "non_floor_sections": non_floor_sections,
        "method_notes": [
            "Metrics are concept-level advisory screening only.",
            "Taiwan code, daylight, ventilation, egress, and structural compliance require professional calculation.",
            "Daylight factor adapts the Skills-Architects simplified daylight calculator method.",
        ],
    }
    payload["summary"] = summarize_metrics_payload(payload)
    return payload


def summarize_metrics_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics", [])
    status_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    building_counts: dict[str, int] = {}
    issue_evidence_by_building: dict[str, list[str]] = {}
    daylight_values: list[float] = []
    daylight_below_target = 0
    door_below_min = 0

    for metric in metrics:
        status = str(metric.get("status", ""))
        metric_type = str(metric.get("metric_type", ""))
        building_id = str(metric.get("building_id", ""))
        status_counts[status] = status_counts.get(status, 0) + 1
        type_counts[metric_type] = type_counts.get(metric_type, 0) + 1
        building_counts[building_id] = building_counts.get(building_id, 0) + 1

        result = metric.get("result", {})
        if metric_type == "daylight_factor":
            value = to_float(result.get("daylight_factor_pct"), -1.0)
            target = to_float(result.get("target_daylight_factor_pct"), 2.0)
            if value >= 0:
                daylight_values.append(value)
                if value < target:
                    daylight_below_target += 1
        if metric_type == "door_width" and metric.get("status") == STATUS_ADVISORY:
            door_below_min += 1

        if metric.get("issues") and metric.get("status") != STATUS_OK:
            room_uid = normalize_whitespace(str(metric.get("room_uid", "")))
            if room_uid:
                label = f"{room_uid}:{metric_type}"
            else:
                floor_id = normalize_whitespace(str(metric.get("floor_id", "")))
                label = ":".join(
                    value for value in (building_id, floor_id, metric_type) if value
                )
            issue_evidence_by_building.setdefault(building_id, []).append(
                f"{label} - {metric['issues'][0]}"
            )

    issue_evidence: list[str] = []
    building_queues = {
        building_id: list(items)
        for building_id, items in sorted(issue_evidence_by_building.items())
    }
    while len(issue_evidence) < 20 and any(building_queues.values()):
        for building_id in building_queues:
            if building_queues[building_id] and len(issue_evidence) < 20:
                issue_evidence.append(building_queues[building_id].pop(0))

    daylight_avg = round(sum(daylight_values) / len(daylight_values), 2) if daylight_values else 0.0
    return {
        "status_counts": status_counts,
        "metric_type_counts": type_counts,
        "building_counts": building_counts,
        "evaluated_floor_count": payload.get("evaluated_floor_count", 0),
        "skipped_floor_count": payload.get("skipped_floor_count", 0),
        "non_floor_section_count": payload.get("non_floor_section_count", 0),
        "daylight_factor_avg_pct": daylight_avg,
        "daylight_rooms_below_target": daylight_below_target,
        "door_width_advisory_count": door_below_min,
        "top_issues": issue_evidence[:20],
        "action_groups": build_action_groups(metrics),
    }


def daylight_fit_from_ratio(ratio: float) -> float:
    return round(max(-0.8, min(1.0, (ratio * 1.45) - 0.8)), 4)


def build_daylight_score_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for metric in payload.get("metrics", []):
        if metric.get("metric_type") != "daylight_factor":
            continue
        if metric.get("status") == STATUS_MISSING:
            continue
        uid = normalize_whitespace(str(metric.get("room_uid", "")))
        result = metric.get("result", {})
        value = to_float(result.get("daylight_factor_pct"), -1.0)
        target = to_float(result.get("target_daylight_factor_pct"), 2.0)
        if not uid or value < 0 or target <= 0:
            continue
        ratio = value / target
        index[uid] = {
            "fit_score": daylight_fit_from_ratio(ratio),
            "confidence": metric.get("confidence", "low"),
            "daylight_factor_pct": round(value, 2),
            "target_daylight_factor_pct": round(target, 2),
            "status": metric.get("status", ""),
            "source": "architect_metrics:daylight_factor",
        }
    return index


def generate_metrics_report_md(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    status_counts = summary.get("status_counts", {})
    type_counts = summary.get("metric_type_counts", {})
    lines: list[str] = []
    lines.append("# Architect Metrics Report")
    lines.append("")
    lines.append(f"- Generated: `{payload.get('generated_at', '')}`")
    lines.append(f"- Schema: `{payload.get('schema_version', '')}`")
    lines.append(f"- Buildings: `{','.join(payload.get('selected_buildings', []))}`")
    lines.append(f"- Evaluated floors: **{payload.get('evaluated_floor_count', 0)}**")
    lines.append(f"- Skipped floors: **{payload.get('skipped_floor_count', 0)}**")
    lines.append(f"- Non-floor sections: **{payload.get('non_floor_section_count', 0)}**")
    lines.append("")
    lines.append("## Status Summary")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|---|---:|")
    for key in [STATUS_OK, STATUS_ADVISORY, STATUS_MISSING, STATUS_PROFESSIONAL]:
        lines.append(f"| `{key}` | {status_counts.get(key, 0)} |")
    lines.append("")
    lines.append("## Metric Types")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|---|---:|")
    for key in sorted(type_counts):
        lines.append(f"| `{key}` | {type_counts[key]} |")
    lines.append("")
    lines.append("## Key Advisory Results")
    lines.append("")
    lines.append(f"- Average concept daylight factor: `{summary.get('daylight_factor_avg_pct', 0)}%`")
    lines.append(f"- Daylight-sensitive rooms below target: `{summary.get('daylight_rooms_below_target', 0)}`")
    lines.append(f"- Door width advisory count: `{summary.get('door_width_advisory_count', 0)}`")
    lines.append("")
    lines.append("## Top Issues")
    lines.append("")
    top_issues = summary.get("top_issues", [])
    if not top_issues:
        lines.append("- None")
    else:
        for issue in top_issues:
            lines.append(f"- {issue}")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    for note in payload.get("method_notes", []):
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)

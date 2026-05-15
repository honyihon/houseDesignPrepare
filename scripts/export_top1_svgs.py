#!/usr/bin/env python3
"""Export top-1 layout candidates as standalone SVG files."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.standards import (  # noqa: E402
    defaults_summary_line,
    door_width_mm,
    drawing_font_family,
    load_residential_defaults,
    px_per_mm,
    wall_thickness_mm,
    window_width_mm,
)

PROGRAM_FILE = ROOT / "structured" / "room_program.json"
CANDIDATES_FILE = ROOT / "structured" / "candidates" / "layout_candidates.json"
OUT_DIR = ROOT / "structured" / "candidates" / "svg"
MANIFEST_FILE = OUT_DIR / "manifest.json"
INDEX_FILE = OUT_DIR / "index.html"
SCHEMA_VERSION = "layout-top1-svg-v2"
PRESENTATION_VERSION = 2

# Common residential defaults (April 2026 baseline):
# - Door minima from IRC R311.2 (egress clear width >= 32 in / 813 mm).
# - Market-standard slabs commonly listed as 24/28/30/32/36 x 80 in.
# - Typical 2x4 partition wall (with drywall) around 4.5 in (~114 mm).
# These are used only when source drawing data does not provide dimensions.
RESIDENTIAL_DEFAULTS = load_residential_defaults()
DOOR_WIDTH_MM = door_width_mm(RESIDENTIAL_DEFAULTS)
WALL_MM = wall_thickness_mm(RESIDENTIAL_DEFAULTS)
FURNITURE_MM = RESIDENTIAL_DEFAULTS.get("furniture_mm", {})
DRAWING_DEFAULTS = RESIDENTIAL_DEFAULTS.get("drawing", {})
SVG_FONT_FAMILY = drawing_font_family(RESIDENTIAL_DEFAULTS)
DEFAULTS_HEADER_LINE = defaults_summary_line(RESIDENTIAL_DEFAULTS)
WINDOW_WIDTH_MM = window_width_mm(RESIDENTIAL_DEFAULTS)

# Rendering conversion for unknown real scale (heuristic placeholder).
PX_PER_MM = px_per_mm(RESIDENTIAL_DEFAULTS)
INTERIOR_WALL_FACTOR = float(DRAWING_DEFAULTS.get("interior_wall_factor", 0.32) or 0.32)
EXTERIOR_WALL_EXTRA_PX = float(DRAWING_DEFAULTS.get("exterior_wall_extra_px", 1.2) or 1.2)
WINDOW_LINE_WIDTH_PX = float(DRAWING_DEFAULTS.get("window_line_width_px", 2.2) or 2.2)
DIMENSION_LINE_COLOR = str(DRAWING_DEFAULTS.get("dimension_line_color", "#777"))
VALID_DRAWING_STYLES = ("presentation", "technical", "debug")
VALIDATION_MARKERS = ["ENT", "DW:", "WIN:", "DIM:", "LEGEND:", "ELEV:"]

BASE_STYLE_PROFILE: dict[str, Any] = {
    "show_debug_header": False,
    "show_room_notes": False,
    "show_opening_labels": False,
    "show_dimensions": True,
    "show_dimension_subchains": False,
    "show_right_legend": False,
    "show_bottom_legend": True,
    "show_elevation_indices": False,
    "show_furniture": True,
    "show_score_line": False,
    "presentation_version": PRESENTATION_VERSION,
    "plan_left_px": 58,
    "plan_top_px": 90,
    "plan_width_px": 1040,
    "right_panel_width_px": 64,
    "bottom_padding_px": 136,
    "furniture_opacity": 0.42,
    "colors": {
        "paper": "#f3f4f6",
        "plan_background": "#ffffff",
        "frame": "#d1d5db",
        "text": "#111827",
        "muted": "#64748b",
        "wall_outer": "#111827",
        "wall_inner": "#374151",
        "dimension": "#9ca3af",
        "door": "#475569",
        "window": "#2563eb",
        "furniture_fill": "#ffffff",
        "furniture_stroke": "#64748b",
        "label_halo": "#ffffff",
        "hatch": "#94a3b8",
    },
    "room_fills": {
        "entry": "#fffaf3",
        "living": "#fffaf3",
        "dining": "#fffbeb",
        "bedroom": "#f7f8ff",
        "bath": "#f3fdff",
        "kitchen": "#f5fff8",
        "service": "#f7f9fc",
        "stair": "#f8fafc",
        "outdoor": "#f2fbf5",
        "other": "#ffffff",
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export SVG floor plans from candidate results.")
    parser.add_argument(
        "--selection",
        choices=("baseline", "best"),
        default="baseline",
        help="Candidate selection strategy (default: baseline).",
    )
    parser.add_argument(
        "--style",
        choices=VALID_DRAWING_STYLES,
        default=default_drawing_style(),
        help="Drawing style profile (default: configured default, usually presentation).",
    )
    return parser.parse_args()


def default_drawing_style() -> str:
    value = str(DRAWING_DEFAULTS.get("default_style", "presentation") or "presentation")
    return value if value in VALID_DRAWING_STYLES else "presentation"


def drawing_profile(style: str) -> dict[str, Any]:
    profile = dict(BASE_STYLE_PROFILE)
    profile["colors"] = dict(BASE_STYLE_PROFILE["colors"])
    profile["room_fills"] = dict(BASE_STYLE_PROFILE["room_fills"])

    configured_profiles = DRAWING_DEFAULTS.get("style_profiles", {})
    raw_profile = configured_profiles.get(style, {}) if isinstance(configured_profiles, dict) else {}
    if isinstance(raw_profile, dict):
        for key, value in raw_profile.items():
            if key in {"colors", "room_fills"} and isinstance(value, dict):
                merged = dict(profile.get(key, {}))
                merged.update({str(k): str(v) for k, v in value.items()})
                profile[key] = merged
            else:
                profile[key] = value

    profile["name"] = style
    return profile


def presentation_version(profile: dict[str, Any], style: str) -> int:
    if style != "presentation":
        return 0
    try:
        return int(profile.get("presentation_version", PRESENTATION_VERSION) or PRESENTATION_VERSION)
    except (TypeError, ValueError):
        return PRESENTATION_VERSION


def is_presentation_v2(profile: dict[str, Any], style: str) -> bool:
    return presentation_version(profile, style) >= 2


def style_bool(profile: dict[str, Any], key: str, default: bool = False) -> bool:
    value = profile.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def style_float(profile: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(profile.get(key, default))
    except (TypeError, ValueError):
        return default


def style_color(profile: dict[str, Any], key: str, default: str) -> str:
    colors = profile.get("colors", {})
    if isinstance(colors, dict):
        value = colors.get(key)
        if value:
            return str(value)
    return default


def room_fill_color(profile: dict[str, Any], kind: str, drawing_style: str = "") -> str:
    if is_presentation_v2(profile, drawing_style) and kind in {"bath", "service", "outdoor"}:
        return f"url(#p2-{kind}-hatch)"
    fills = profile.get("room_fills", {})
    if isinstance(fills, dict):
        return str(fills.get(kind) or fills.get("other") or "#ffffff")
    return "#ffffff"


def room_area_text(slot: dict[str, Any], pair_map: dict[str, dict[str, Any]], room_index: dict[str, dict[str, Any]]) -> str:
    pair = pair_map.get(slot["slot_id"])
    if pair:
        room_uid = str(pair.get("room_uid", ""))
        indexed = room_index.get(room_uid, {})
        area_text = normalize(str(indexed.get("area_text", "")))
        if area_text:
            return area_text
    return normalize(slot.get("size_text", ""))


def compact_room_label(room_name: str, slot: dict[str, Any], width: float, height: float) -> str:
    if width < 78 or height < 58:
        return f"R{slot.get('order', '')}".strip()
    limit = text_limit_from_width(width, 4, 24 if width < 145 else 34)
    return truncate_text(room_name, limit)


def display_room_name(value: str) -> str:
    text = normalize(value)
    match = re.match(r"^([^\w\u4e00-\u9fff\s]+)\s*(.+)$", text, flags=re.UNICODE)
    return normalize(match.group(2)) if match else text


def room_label_info(
    room_name: str,
    slot: dict[str, Any],
    width: float,
    height: float,
    profile: dict[str, Any],
    drawing_style: str,
) -> dict[str, Any]:
    display_name = display_room_name(room_name) or "未指派"
    if not is_presentation_v2(profile, drawing_style):
        label = compact_room_label(display_name, slot, width, height)
        return {"label": label, "full_label": display_name, "compact": label.startswith("R")}

    code = f"R{slot.get('order', '')}".strip()
    usable_w = max(0.0, width - 30.0)
    approx_text_w = len(display_name) * 7.2
    compact = width < 124 or height < 78 or approx_text_w > usable_w or len(display_name) > 22
    if compact:
        return {"label": code, "full_label": display_name, "compact": True}
    limit = text_limit_from_width(width, 6, 30)
    return {"label": truncate_text(display_name, limit), "full_label": display_name, "compact": False}


def normalize(value: str) -> str:
    return " ".join((value or "").split())


def safe_slug(value: str) -> str:
    value = normalize(value).lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "unknown"


def truncate_text(value: str, limit: int) -> str:
    text = normalize(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def build_slot_index(program: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for building in program.get("buildings", []):
        b_id = building.get("id", "")
        for floor in building.get("floors", []):
            f_id = floor.get("id", "")
            cells = []
            for cell in floor.get("plan_cells", []):
                order = int(cell.get("order", 0))
                layout = cell.get("layout", {})
                if not isinstance(layout, dict):
                    layout = {}
                cells.append(
                    {
                        "slot_id": f"slot-{order}",
                        "order": order,
                        "name": normalize(cell.get("name", "")),
                        "icon": normalize(cell.get("icon", "")),
                        "size_text": normalize(cell.get("size_text", "")),
                        "badges": cell.get("badges", []),
                        "classes": cell.get("classes", []),
                        "row_order": int(layout.get("row_order", 0) or 0),
                        "col_order": int(layout.get("col_order", 0) or 0),
                        "col_weight": float(layout.get("col_weight", 1.0) or 1.0),
                        "geometry_mm": cell.get("geometry_mm", {}) if isinstance(cell.get("geometry_mm", {}), dict) else {},
                        "openings_mm": cell.get("openings_mm", {}) if isinstance(cell.get("openings_mm", {}), dict) else {},
                        "is_entry": bool(cell.get("is_entry", False)),
                        "material": normalize(str(cell.get("material", ""))),
                    }
                )
            cells.sort(key=lambda x: x["order"])
            index[(b_id, f_id)] = cells
    return index


def build_room_index(program: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for building in program.get("buildings", []):
        for floor in building.get("floors", []):
            for room in floor.get("rooms", []):
                uid = str(room.get("uid", ""))
                if not uid:
                    continue
                details = [normalize(v) for v in room.get("details", []) if normalize(v)]
                tags = []
                for tag in room.get("tags", []):
                    title = normalize(str(tag.get("title", "")))
                    content = normalize(str(tag.get("content", "")))
                    if title and content:
                        tags.append(f"{title}: {content}")
                    elif content:
                        tags.append(content)
                rendered_notes = [normalize(v) for v in room.get("notes_rendered", []) if normalize(v)]
                index[uid] = {
                    "name": normalize(str(room.get("name", ""))),
                    "area_text": normalize(str(room.get("area_text", ""))),
                    "details": details,
                    "tags": tags,
                    "notes_rendered": rendered_notes,
                }
    return index


def fit_to_color(avg_fit: float | None) -> str:
    if avg_fit is None:
        return "#5b6d8d"
    if avg_fit >= 0.35:
        return "#30c694"
    if avg_fit >= 0.05:
        return "#f0b355"
    return "#ef7474"


def choose_columns(slot_count: int) -> int:
    if slot_count <= 6:
        return 3
    if slot_count <= 10:
        return 4
    if slot_count <= 14:
        return 5
    return 6


def score_avg(dimension_fit: dict[str, Any]) -> float:
    c = float(dimension_fit.get("circulation", 0))
    d = float(dimension_fit.get("daylight", 0))
    m = float(dimension_fit.get("mep", 0))
    return (c + d + m) / 3.0


def has_source_row_layout(slots: list[dict[str, Any]]) -> bool:
    return bool(slots) and all(int(s.get("row_order", 0) or 0) > 0 for s in slots)


def has_precise_slot_geometry(slots: list[dict[str, Any]]) -> bool:
    if not slots:
        return False
    for slot in slots:
        geom = slot.get("geometry_mm", {})
        if not isinstance(geom, dict):
            return False
        if any(geom.get(key) is None for key in ("x_mm", "y_mm", "w_mm", "h_mm")):
            return False
    return True


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def precise_bounds_mm(slots: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")
    for slot in slots:
        geom = slot.get("geometry_mm", {})
        x = _f(geom.get("x_mm", 0.0))
        y = _f(geom.get("y_mm", 0.0))
        w = max(1.0, _f(geom.get("w_mm", 1.0)))
        h = max(1.0, _f(geom.get("h_mm", 1.0)))
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x + w)
        max_y = max(max_y, y + h)
    if min_x == float("inf") or min_y == float("inf"):
        return 0.0, 0.0, 1.0, 1.0
    return min_x, min_y, max_x, max_y


def group_slots_by_source_rows(slots: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    row_map: dict[int, list[dict[str, Any]]] = {}
    for slot in slots:
        row_order = int(slot.get("row_order", 0) or 0)
        if row_order <= 0:
            return []
        row_map.setdefault(row_order, []).append(slot)

    grouped: list[list[dict[str, Any]]] = []
    for row_order in sorted(row_map.keys()):
        row_slots = sorted(
            row_map[row_order],
            key=lambda item: (
                int(item.get("col_order", 0) or 9999),
                int(item.get("order", 0)),
            ),
        )
        grouped.append(row_slots)
    return grouped


def text_limit_from_width(width: float, min_chars: int, max_chars: int) -> int:
    approx = int(max(0.0, width - 28.0) / 7.4)
    return max(min_chars, min(max_chars, approx))


def svg_text(x: float, y: float, text: str, size: int = 13, weight: int = 400, color: str = "#e8edf7") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}" font-size="{size}" '
        f'font-family="{html.escape(SVG_FONT_FAMILY)}" font-weight="{weight}">{html.escape(text)}</text>'
    )


def svg_text_centered(
    x: float,
    y: float,
    text: str,
    size: int = 13,
    weight: int = 400,
    color: str = "#111827",
    halo: str = "#ffffff",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}" font-size="{size}" '
        f'font-family="{html.escape(SVG_FONT_FAMILY)}" font-weight="{weight}" text-anchor="middle" '
        f'dominant-baseline="middle" paint-order="stroke" stroke="{halo}" stroke-width="2.4" '
        f'stroke-linejoin="round">{html.escape(text)}</text>'
    )


def presentation_defs(profile: dict[str, Any], drawing_style: str) -> str:
    if not is_presentation_v2(profile, drawing_style):
        return ""
    fills = profile.get("room_fills", {}) if isinstance(profile.get("room_fills"), dict) else {}
    hatch = style_color(profile, "hatch", "#94a3b8")
    wet_fill = str(fills.get("bath", "#ecfeff"))
    service_fill = str(fills.get("service", "#f1f5f9"))
    outdoor_fill = str(fills.get("outdoor", "#ecfdf5"))
    return f"""
<defs>
  <pattern id="p2-bath-hatch" patternUnits="userSpaceOnUse" width="9" height="9" patternTransform="rotate(45)">
    <rect width="9" height="9" fill="{wet_fill}"/>
    <line x1="0" y1="0" x2="0" y2="9" stroke="{hatch}" stroke-width="0.55" opacity="0.28"/>
  </pattern>
  <pattern id="p2-service-hatch" patternUnits="userSpaceOnUse" width="10" height="10">
    <rect width="10" height="10" fill="{service_fill}"/>
    <path d="M 0 10 L 10 0" stroke="{hatch}" stroke-width="0.5" opacity="0.20"/>
  </pattern>
  <pattern id="p2-outdoor-hatch" patternUnits="userSpaceOnUse" width="12" height="12">
    <rect width="12" height="12" fill="{outdoor_fill}"/>
    <path d="M 0 6 H 12 M 6 0 V 12" stroke="{hatch}" stroke-width="0.45" opacity="0.18"/>
  </pattern>
</defs>
"""


def render_slot_card(
    parts: list[str],
    x: float,
    y: float,
    cell_w: float,
    cell_h: float,
    slot: dict[str, Any],
    fallback_order: int,
    pair_map: dict[str, dict[str, Any]],
) -> None:
    slot_id = slot["slot_id"]
    pair = pair_map.get(slot_id)

    room_name = "— 未指派 —"
    fit_color = "#5b6d8d"
    fit_text = "unassigned"
    if pair:
        room_name = normalize(pair.get("room_name", ""))
        avg_fit = score_avg(pair.get("dimension_fit", {}))
        fit_color = fit_to_color(avg_fit)
        fit_text = f"fit {avg_fit * 100:.0f}%"

    parts.append(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" '
        f'rx="13" fill="#14233d" stroke="#3b557e" stroke-width="1.1"/>'
    )
    parts.append(svg_text(x + 12, y + 22, f'{slot_id}  #{slot.get("order", fallback_order)}', size=12, weight=700, color="#9fbbde"))

    slot_name_limit = text_limit_from_width(cell_w, 10, 36)
    room_name_limit = text_limit_from_width(cell_w, 12, 40)
    misc_limit = text_limit_from_width(cell_w, 14, 48)

    slot_name = truncate_text(f'{slot.get("icon", "")} {slot.get("name", "")}'.strip(), slot_name_limit)
    parts.append(svg_text(x + 12, y + 45, slot_name, size=15, weight=800, color="#edf4ff"))

    room_name = truncate_text(room_name, room_name_limit)
    parts.append(svg_text(x + 12, y + 72, room_name, size=14, weight=700, color="#ffffff"))

    size_text = truncate_text(slot.get("size_text", ""), misc_limit)
    if size_text:
        parts.append(svg_text(x + 12, y + 95, size_text, size=11, weight=500, color="#a5b8d7"))

    badges = slot.get("badges", [])[:3]
    if badges:
        badge_text = truncate_text(" | ".join(badges), misc_limit)
        parts.append(svg_text(x + 12, y + 116, badge_text, size=10, weight=500, color="#94c7e7"))

    fit_w = 80 if cell_w >= 190 else 64
    fit_x = x + cell_w - fit_w - 10
    parts.append(
        f'<rect x="{fit_x:.1f}" y="{y + cell_h - 30:.1f}" width="{fit_w:.1f}" height="20" '
        f'rx="10" fill="#122035" stroke="{fit_color}" stroke-width="1.2"/>'
    )
    parts.append(svg_text(fit_x + 10, y + cell_h - 16, fit_text, size=10, weight=700, color=fit_color))


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", normalize(value).lower())


def room_kind(name: str) -> str:
    key = normalize_key(name)
    if any(k in key for k in ["玄關", "入口", "大門", "entry", "foyer"]):
        return "entry"
    if any(k in key for k in ["客廳", "起居", "living", "lounge"]):
        return "living"
    if any(k in key for k in ["餐廳", "dining"]):
        return "dining"
    if any(k in key for k in ["主臥", "臥", "客房", "bedroom", "master", "sleep"]):
        return "bedroom"
    if any(k in key for k in ["衛", "浴", "廁", "bath", "toilet", "wc"]):
        return "bath"
    if any(k in key for k in ["廚", "kitchen"]):
        return "kitchen"
    if any(k in key for k in ["陽台", "露台", "側院", "車庫", "balcony", "terrace", "garage", "outdoor"]):
        return "outdoor"
    if any(k in key for k in ["樓梯", "梯間", "stair"]):
        return "stair"
    if any(k in key for k in ["機櫃", "機房", "配電", "儲藏", "設備", "mdf", "idf", "service", "storage"]):
        return "service"
    return "other"


def pick_room_name(slot: dict[str, Any], pair_map: dict[str, dict[str, Any]]) -> str:
    pair = pair_map.get(slot["slot_id"])
    if pair:
        room_name = normalize(pair.get("room_name", ""))
        if room_name:
            return room_name
    return normalize(slot.get("name", "")) or "未指派"


def pick_room_notes(
    slot: dict[str, Any],
    pair_map: dict[str, dict[str, Any]],
    room_index: dict[str, dict[str, Any]],
) -> list[str]:
    notes: list[str] = []

    badges = [normalize(v) for v in slot.get("badges", []) if normalize(v)]
    if badges:
        notes.append(" | ".join(badges[:3]))

    pair = pair_map.get(slot["slot_id"])
    if pair:
        room_uid = str(pair.get("room_uid", ""))
        info = room_index.get(room_uid, {})
        rendered_notes = [normalize(v) for v in info.get("notes_rendered", []) if normalize(v)]
        for v in rendered_notes[:2]:
            if v and v not in notes:
                notes.append(v)
        for v in info.get("details", [])[:1]:
            if v and v not in notes:
                notes.append(v)
        for v in info.get("tags", [])[:1]:
            if v and v not in notes:
                notes.append(v)

    return notes[:2]


def door_type_for_pair(kind_a: str, kind_b: str) -> str:
    pair = {kind_a, kind_b}
    if "entry" in pair:
        return "entry"
    if "bath" in pair:
        return "bathroom"
    if "service" in pair:
        return "service"
    return "interior"


def door_width_mm_for_pair(kind_a: str, kind_b: str) -> int:
    door_type = door_type_for_pair(kind_a, kind_b)
    return int(DOOR_WIDTH_MM.get(door_type, DOOR_WIDTH_MM["interior"]))


def door_span_px(default_mm: int, edge_length: float) -> float:
    target = float(default_mm) * PX_PER_MM
    return max(24.0, min(target, edge_length * 0.82))


def build_adjacency_edges(rects: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ids = list(rects.keys())
    eps = 1e-3
    edges: list[dict[str, Any]] = []
    for i in range(len(ids)):
        a_id = ids[i]
        a = rects[a_id]
        ax1 = float(a["x"])
        ay1 = float(a["y"])
        ax2 = ax1 + float(a["w"])
        ay2 = ay1 + float(a["h"])
        for j in range(i + 1, len(ids)):
            b_id = ids[j]
            b = rects[b_id]
            bx1 = float(b["x"])
            by1 = float(b["y"])
            bx2 = bx1 + float(b["w"])
            by2 = by1 + float(b["h"])

            if abs(ax2 - bx1) <= eps or abs(bx2 - ax1) <= eps:
                y1 = max(ay1, by1)
                y2 = min(ay2, by2)
                overlap = y2 - y1
                if overlap > 24:
                    edges.append(
                        {
                            "a": a_id,
                            "b": b_id,
                            "orientation": "v",
                            "x": bx1 if abs(ax2 - bx1) <= eps else ax1,
                            "y1": y1,
                            "y2": y2,
                            "length": overlap,
                        }
                    )

            if abs(ay2 - by1) <= eps or abs(by2 - ay1) <= eps:
                x1 = max(ax1, bx1)
                x2 = min(ax2, bx2)
                overlap = x2 - x1
                if overlap > 24:
                    edges.append(
                        {
                            "a": a_id,
                            "b": b_id,
                            "orientation": "h",
                            "y": by1 if abs(ay2 - by1) <= eps else ay1,
                            "x1": x1,
                            "x2": x2,
                            "length": overlap,
                        }
                    )
    return edges


def edge_score(edge: dict[str, Any], kind_map: dict[str, str]) -> float:
    a = kind_map.get(edge["a"], "other")
    b = kind_map.get(edge["b"], "other")
    pair = {a, b}
    score = 1.0
    if "entry" in pair:
        score += 3.5
    if "living" in pair:
        score += 2.8
    if "dining" in pair:
        score += 1.8
    if "stair" in pair:
        score += 1.5
    if pair == {"bedroom", "bath"}:
        score += 2.0
    if "kitchen" in pair and ("dining" in pair or "living" in pair):
        score += 1.8
    if "outdoor" in pair and "living" in pair:
        score += 1.4
    if "service" in pair and "bedroom" in pair:
        score -= 0.4
    return score + min(0.9, edge.get("length", 0) / 220.0)


def pick_root_slot(slots: list[dict[str, Any]], pair_map: dict[str, dict[str, Any]]) -> str:
    for slot in slots:
        if bool(slot.get("is_entry", False)):
            return slot["slot_id"]
    for slot in slots:
        name = pick_room_name(slot, pair_map)
        if room_kind(name) == "entry":
            return slot["slot_id"]
    for slot in slots:
        name = pick_room_name(slot, pair_map)
        if room_kind(name) in {"living", "dining"}:
            return slot["slot_id"]
    return slots[0]["slot_id"] if slots else ""


def choose_door_edges(
    slot_ids: list[str],
    adjacency_edges: list[dict[str, Any]],
    root_slot: str,
    kind_map: dict[str, str],
) -> list[dict[str, Any]]:
    if not slot_ids or not adjacency_edges:
        return []

    connected: set[str] = {root_slot or slot_ids[0]}
    chosen: list[dict[str, Any]] = []

    while len(connected) < len(slot_ids):
        best_edge = None
        best_score = float("-inf")
        for edge in adjacency_edges:
            a = edge["a"]
            b = edge["b"]
            a_in = a in connected
            b_in = b in connected
            if a_in == b_in:
                continue
            score = edge_score(edge, kind_map)
            if score > best_score:
                best_score = score
                best_edge = edge

        if best_edge is None:
            for slot_id in slot_ids:
                if slot_id not in connected:
                    connected.add(slot_id)
                    break
            continue

        chosen.append(best_edge)
        connected.add(best_edge["a"])
        connected.add(best_edge["b"])

    return chosen


def draw_furniture(parts: list[str], rect: dict[str, Any], kind: str, profile: dict[str, Any]) -> None:
    x = float(rect["x"])
    y = float(rect["y"])
    w = float(rect["w"])
    h = float(rect["h"])
    if min(w, h) < 92:
        return

    stroke = style_color(profile, "furniture_stroke", "#555")
    fill = style_color(profile, "furniture_fill", "#f6f6f6")
    opacity = max(0.1, min(1.0, style_float(profile, "furniture_opacity", 1.0)))
    if opacity < 1.0:
        parts.append(f'<g opacity="{opacity:.2f}">')

    if kind == "bedroom":
        bed_cfg = FURNITURE_MM.get("bed_double", {"width": 1500, "depth": 1900})
        bw = min(w * 0.78, max(90.0, bed_cfg["width"] * PX_PER_MM))
        bh = min(h * 0.64, max(74.0, bed_cfg["depth"] * PX_PER_MM))
        bx = x + (w - bw) / 2
        by = y + (h - bh) / 2 + 8
        parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="1.1"/>')
        pillow_w = bw * 0.22
        pillow_h = bh * 0.20
        parts.append(
            f'<rect x="{bx + bw * 0.08:.1f}" y="{by + 5:.1f}" width="{pillow_w:.1f}" height="{pillow_h:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="0.9"/>'
        )
        parts.append(
            f'<rect x="{bx + bw * 0.70:.1f}" y="{by + 5:.1f}" width="{pillow_w:.1f}" height="{pillow_h:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="0.9"/>'
        )
    elif kind == "living":
        sofa_cfg = FURNITURE_MM.get("sofa_3", {"width": 2100, "depth": 900})
        sw = min(w * 0.76, max(100.0, sofa_cfg["width"] * PX_PER_MM))
        sh = min(h * 0.35, max(26.0, sofa_cfg["depth"] * PX_PER_MM))
        sx = x + (w - sw) / 2
        sy = y + h * 0.55
        parts.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{sw:.1f}" height="{sh:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="1.1"/>')
        cw = w * 0.18
        ch = h * 0.12
        cx = x + (w - cw) / 2
        cy = sy - h * 0.18
        parts.append(f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{cw:.1f}" height="{ch:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="1.0"/>')
    elif kind == "dining":
        table_cfg = FURNITURE_MM.get("dining_table_6", {"width": 1600, "depth": 800})
        tw = min(w * 0.60, max(76.0, table_cfg["width"] * PX_PER_MM))
        th = min(h * 0.34, max(30.0, table_cfg["depth"] * PX_PER_MM))
        tx = x + (w - tw) / 2
        ty = y + h * 0.50
        parts.append(f'<rect x="{tx:.1f}" y="{ty:.1f}" width="{tw:.1f}" height="{th:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="1.0"/>')
        r = min(8.0, min(w, h) * 0.06)
        chair_points = [
            (tx - r * 1.8, ty + th * 0.25),
            (tx - r * 1.8, ty + th * 0.75),
            (tx + tw + r * 1.8, ty + th * 0.25),
            (tx + tw + r * 1.8, ty + th * 0.75),
        ]
        for cx, cy in chair_points:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="0.9"/>')
    elif kind == "kitchen":
        kitchen_depth_mm = float(FURNITURE_MM.get("kitchen_counter_depth", 650))
        counter_depth_px = max(14.0, kitchen_depth_mm * PX_PER_MM * 0.35)
        parts.append(
            f'<rect x="{x + 10:.1f}" y="{y + h - (counter_depth_px + 10):.1f}" width="{w - 20:.1f}" '
            f'height="{counter_depth_px:.1f}" fill="#f6f6f6" stroke="{stroke}" stroke-width="1.0"/>'
        )
        burner_y = y + h - (counter_depth_px / 2 + 10)
        parts.append(f'<circle cx="{x + 24:.1f}" cy="{burner_y:.1f}" r="4" fill="none" stroke="{stroke}" stroke-width="0.9"/>')
        parts.append(f'<circle cx="{x + 34:.1f}" cy="{burner_y:.1f}" r="4" fill="none" stroke="{stroke}" stroke-width="0.9"/>')
    elif kind == "bath":
        wc_w = min(34.0, w * 0.26)
        wc_h = min(24.0, h * 0.20)
        bx = x + w * 0.56
        by = y + h * 0.55
        parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{wc_w:.1f}" height="{wc_h:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="1.0"/>')
        parts.append(f'<ellipse cx="{bx + wc_w / 2:.1f}" cy="{by - 8:.1f}" rx="{wc_w / 2:.1f}" ry="7" fill="{fill}" stroke="{stroke}" stroke-width="0.9"/>')
    elif kind == "stair":
        steps = 7
        for i in range(steps):
            yy = y + 16 + i * ((h - 32) / steps)
            parts.append(f'<line x1="{x + 10:.1f}" y1="{yy:.1f}" x2="{x + w - 10:.1f}" y2="{yy:.1f}" stroke="{stroke}" stroke-width="0.9"/>')
    elif kind == "outdoor":
        parts.append(
            f'<rect x="{x + 7:.1f}" y="{y + 7:.1f}" width="{w - 14:.1f}" height="{h - 14:.1f}" fill="none" stroke="#8a8a8a" stroke-dasharray="5 4" stroke-width="0.9"/>'
        )
    if opacity < 1.0:
        parts.append("</g>")


def draw_internal_door(
    parts: list[str],
    edge: dict[str, Any],
    rects: dict[str, dict[str, Any]],
    kind_map: dict[str, str],
    profile: dict[str, Any],
) -> None:
    kind_a = kind_map.get(edge["a"], "other")
    kind_b = kind_map.get(edge["b"], "other")
    door_hint_a = opening_hint_mm(rects[edge["a"]]["slot"], "door_mm")
    door_hint_b = opening_hint_mm(rects[edge["b"]]["slot"], "door_mm")
    door_mm = door_hint_a or door_hint_b or door_width_mm_for_pair(kind_a, kind_b)
    span = door_span_px(door_mm, float(edge.get("length", 0)))
    if span < 24:
        return

    a = rects[edge["a"]]
    b = rects[edge["b"]]
    area_a = float(a["w"]) * float(a["h"])
    area_b = float(b["w"]) * float(b["h"])
    swing_room = a if area_a <= area_b else b

    door_color = style_color(profile, "door", "#666")
    wall_cut_color = style_color(profile, "plan_background", "#ffffff")
    show_labels = style_bool(profile, "show_opening_labels", True)

    if edge["orientation"] == "v":
        x = float(edge["x"])
        mid = (float(edge["y1"]) + float(edge["y2"])) / 2
        y0 = mid - span / 2
        parts.append(f'<line x1="{x:.1f}" y1="{y0:.1f}" x2="{x:.1f}" y2="{y0 + span:.1f}" stroke="{wall_cut_color}" stroke-width="4.8"/>')
        sign = -1 if float(swing_room["x"]) + float(swing_room["w"]) / 2 < x else 1
        r = span
        hx = x
        hy = y0
        ex = x + sign * r
        ey = hy
        sweep = 1 if sign > 0 else 0
        parts.append(f'<line x1="{hx:.1f}" y1="{hy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{door_color}" stroke-width="1.2"/>')
        parts.append(
            f'<path d="M {x:.1f} {hy + r:.1f} A {r:.1f} {r:.1f} 0 0 {sweep} {ex:.1f} {ey:.1f}" '
            f'fill="none" stroke="{door_color}" stroke-width="0.9"/>'
        )
        if show_labels:
            parts.append(svg_text(x + 4, y0 + span + 9, f"DW:{int(round(door_mm / 10.0))}", size=8, weight=500, color=door_color))
    else:
        y = float(edge["y"])
        mid = (float(edge["x1"]) + float(edge["x2"])) / 2
        x0 = mid - span / 2
        parts.append(f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x0 + span:.1f}" y2="{y:.1f}" stroke="{wall_cut_color}" stroke-width="4.8"/>')
        sign = -1 if float(swing_room["y"]) + float(swing_room["h"]) / 2 < y else 1
        r = span
        hx = x0
        hy = y
        ex = hx
        ey = y + sign * r
        sweep = 0 if sign > 0 else 1
        parts.append(f'<line x1="{hx:.1f}" y1="{hy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{door_color}" stroke-width="1.2"/>')
        parts.append(
            f'<path d="M {hx + r:.1f} {y:.1f} A {r:.1f} {r:.1f} 0 0 {sweep} {ex:.1f} {ey:.1f}" '
            f'fill="none" stroke="{door_color}" stroke-width="0.9"/>'
        )
        if show_labels:
            parts.append(svg_text(x0 + span + 4, y + 10, f"DW:{int(round(door_mm / 10.0))}", size=8, weight=500, color=door_color))


def draw_entrance_marker(parts: list[str], rect: dict[str, Any], side: str, profile: dict[str, Any]) -> None:
    x = float(rect["x"])
    y = float(rect["y"])
    w = float(rect["w"])
    h = float(rect["h"])
    entry_mm = int(DOOR_WIDTH_MM["entry"])
    span = min(max(38.0, entry_mm * PX_PER_MM), max(38.0, min(w, h) * 0.62))
    door_color = style_color(profile, "door", "#666")
    wall_cut_color = style_color(profile, "plan_background", "#ffffff")
    show_labels = style_bool(profile, "show_opening_labels", True)

    if side in {"left", "right"}:
        wall_x = x if side == "left" else x + w
        center_y = y + h * 0.66
        y0 = center_y - span / 2
        parts.append(f'<line x1="{wall_x:.1f}" y1="{y0:.1f}" x2="{wall_x:.1f}" y2="{y0 + span:.1f}" stroke="{wall_cut_color}" stroke-width="5.4"/>')
        sign = -1 if side == "left" else 1
        tri_x = wall_x + sign * 34
        tri_y = center_y + 34
        points = f"{tri_x - 10:.1f},{tri_y + 6:.1f} {tri_x + 10:.1f},{tri_y + 6:.1f} {tri_x:.1f},{tri_y - 12:.1f}"
        parts.append(f'<polygon points="{points}" fill="{door_color}"/>')
        if show_labels:
            parts.append(svg_text(tri_x - 10, tri_y + 22, "ENT", size=10, weight=700, color=style_color(profile, "text", "#333")))
            parts.append(svg_text(tri_x - 12, tri_y + 34, f"DW:{int(round(entry_mm / 10.0))}", size=8, weight=500, color=door_color))
    else:
        wall_y = y if side == "top" else y + h
        center_x = x + w * 0.50
        x0 = center_x - span / 2
        parts.append(f'<line x1="{x0:.1f}" y1="{wall_y:.1f}" x2="{x0 + span:.1f}" y2="{wall_y:.1f}" stroke="{wall_cut_color}" stroke-width="5.4"/>')
        sign = -1 if side == "top" else 1
        tri_x = center_x
        tri_y = wall_y + sign * 34
        if sign > 0:
            points = f"{tri_x - 10:.1f},{tri_y - 6:.1f} {tri_x + 10:.1f},{tri_y - 6:.1f} {tri_x:.1f},{tri_y + 12:.1f}"
            text_y = tri_y + 26
        else:
            points = f"{tri_x - 10:.1f},{tri_y + 6:.1f} {tri_x + 10:.1f},{tri_y + 6:.1f} {tri_x:.1f},{tri_y - 12:.1f}"
            text_y = tri_y - 14
        parts.append(f'<polygon points="{points}" fill="{door_color}"/>')
        if show_labels:
            parts.append(svg_text(tri_x - 10, text_y, "ENT", size=10, weight=700, color=style_color(profile, "text", "#333")))
            parts.append(svg_text(tri_x - 12, text_y + 12, f"DW:{int(round(entry_mm / 10.0))}", size=8, weight=500, color=door_color))


def pick_entrance_side(
    rect: dict[str, Any],
    room_by_slot: dict[str, dict[str, Any]],
    slot_id: str,
    plan_left: float,
    plan_top: float,
    plan_right: float,
    plan_bottom: float,
) -> str:
    slot_center_x = float(rect["x"]) + float(rect["w"]) / 2
    slot_center_y = float(rect["y"]) + float(rect["h"]) / 2
    edge_flags = room_by_slot.get(slot_id, {}).get("outer_sides", {"left": True, "right": True, "top": True, "bottom": True})

    candidates = []
    if edge_flags.get("bottom", False):
        candidates.append(("bottom", abs(plan_bottom - (float(rect["y"]) + float(rect["h"])))))
    if edge_flags.get("right", False):
        candidates.append(("right", abs(plan_right - (float(rect["x"]) + float(rect["w"])))))
    if edge_flags.get("left", False):
        candidates.append(("left", abs(float(rect["x"]) - plan_left)))
    if edge_flags.get("top", False):
        candidates.append(("top", abs(float(rect["y"]) - plan_top)))

    if candidates:
        candidates.sort(key=lambda item: item[1])
        return candidates[0][0]

    if slot_center_y >= (plan_top + plan_bottom) / 2:
        return "bottom"
    if slot_center_x >= (plan_left + plan_right) / 2:
        return "right"
    return "left"


def mm_from_px(px: float) -> int:
    if PX_PER_MM <= 0:
        return int(round(px))
    return int(round(px / PX_PER_MM))


def window_width_mm_for_kind(kind: str) -> int:
    if kind in WINDOW_WIDTH_MM:
        return int(WINDOW_WIDTH_MM[kind])
    return int(WINDOW_WIDTH_MM.get("other", 1000))


def opening_hint_mm(slot: dict[str, Any], key: str) -> int | None:
    openings = slot.get("openings_mm", {})
    if not isinstance(openings, dict):
        return None
    value = openings.get(key)
    try:
        if value is None:
            return None
        ivalue = int(round(float(value)))
        return ivalue if ivalue > 0 else None
    except (TypeError, ValueError):
        return None


def window_span_px(window_mm: int, edge_length: float) -> float:
    target = float(window_mm) * PX_PER_MM
    return max(26.0, min(target, edge_length * 0.72))


def preferred_window_sides(kind: str) -> list[str]:
    if kind in {"living", "dining"}:
        return ["bottom", "right", "left", "top"]
    if kind == "bedroom":
        return ["right", "bottom", "top", "left"]
    if kind == "kitchen":
        return ["top", "right", "left", "bottom"]
    if kind == "bath":
        return ["top", "right", "left", "bottom"]
    if kind in {"service", "stair"}:
        return ["top", "right", "left", "bottom"]
    return ["right", "bottom", "top", "left"]


def choose_window_specs(
    slot_ids: list[str],
    rects: dict[str, dict[str, Any]],
    room_by_slot: dict[str, dict[str, Any]],
    kind_map: dict[str, str],
    root_slot: str,
    root_entry_side: str,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []

    for slot_id in slot_ids:
        rect = rects.get(slot_id)
        if not rect:
            continue

        kind = kind_map.get(slot_id, "other")
        if kind == "outdoor":
            continue

        outer = room_by_slot.get(slot_id, {}).get("outer_sides", {})
        side_order = preferred_window_sides(kind)
        if slot_id == root_slot and root_entry_side and root_entry_side in side_order and len(side_order) > 1:
            side_order = [s for s in side_order if s != root_entry_side]

        selected_side = ""
        for side in side_order:
            if not outer.get(side, False):
                continue
            edge_len = float(rect["h"]) if side in {"left", "right"} else float(rect["w"])
            if edge_len >= 60.0:
                selected_side = side
                break

        if not selected_side:
            continue

        width_mm = opening_hint_mm(rect["slot"], "window_mm") or window_width_mm_for_kind(kind)
        specs.append(
            {
                "slot_id": slot_id,
                "side": selected_side,
                "kind": kind,
                "width_mm": width_mm,
            }
        )

    # Guarantee at least one window marker for machine validation and drawing readability.
    if specs:
        return specs

    for slot_id in slot_ids:
        rect = rects.get(slot_id)
        if not rect:
            continue
        outer = room_by_slot.get(slot_id, {}).get("outer_sides", {})
        for side in ["right", "bottom", "left", "top"]:
            if outer.get(side, False):
                kind = kind_map.get(slot_id, "other")
                specs.append(
                    {
                        "slot_id": slot_id,
                        "side": side,
                        "kind": kind,
                        "width_mm": opening_hint_mm(rect["slot"], "window_mm") or window_width_mm_for_kind(kind),
                    }
                )
                return specs
    return specs


def draw_window_symbol(
    parts: list[str],
    rect: dict[str, Any],
    side: str,
    width_mm: int,
    exterior_wall_px: float,
    profile: dict[str, Any],
) -> None:
    x = float(rect["x"])
    y = float(rect["y"])
    w = float(rect["w"])
    h = float(rect["h"])
    span = window_span_px(width_mm, h if side in {"left", "right"} else w)
    opening_stroke = max(4.8, exterior_wall_px + 2.4)
    window_color = style_color(profile, "window", "#2d6ea3")
    wall_cut_color = style_color(profile, "plan_background", "#ffffff")
    window_line_width = style_float(profile, "window_line_width_px", WINDOW_LINE_WIDTH_PX)
    show_labels = style_bool(profile, "show_opening_labels", True)

    if side in {"left", "right"}:
        wall_x = x if side == "left" else x + w
        center_y = y + h * 0.5
        y0 = center_y - span / 2
        parts.append(f'<line x1="{wall_x:.1f}" y1="{y0:.1f}" x2="{wall_x:.1f}" y2="{y0 + span:.1f}" stroke="{wall_cut_color}" stroke-width="{opening_stroke:.1f}"/>')
        in_sign = 1 if side == "left" else -1
        pane_x = wall_x + in_sign * 2.8
        parts.append(f'<line x1="{pane_x:.1f}" y1="{y0 + 1.2:.1f}" x2="{pane_x:.1f}" y2="{y0 + span - 1.2:.1f}" stroke="{window_color}" stroke-width="{window_line_width:.1f}"/>')
        label_x = wall_x + 8 if side == "left" else wall_x - 62
        if show_labels:
            parts.append(svg_text(label_x, y0 - 4, f"WIN:{width_mm}", size=8, weight=500, color=window_color))
    else:
        wall_y = y if side == "top" else y + h
        center_x = x + w * 0.5
        x0 = center_x - span / 2
        parts.append(f'<line x1="{x0:.1f}" y1="{wall_y:.1f}" x2="{x0 + span:.1f}" y2="{wall_y:.1f}" stroke="{wall_cut_color}" stroke-width="{opening_stroke:.1f}"/>')
        in_sign = 1 if side == "top" else -1
        pane_y = wall_y + in_sign * 2.8
        parts.append(f'<line x1="{x0 + 1.2:.1f}" y1="{pane_y:.1f}" x2="{x0 + span - 1.2:.1f}" y2="{pane_y:.1f}" stroke="{window_color}" stroke-width="{window_line_width:.1f}"/>')
        label_y = wall_y - 6 if side == "top" else wall_y + 14
        if show_labels:
            parts.append(svg_text(x0, label_y, f"WIN:{width_mm}", size=8, weight=500, color=window_color))


def draw_dimension_horizontal(parts: list[str], x1: float, x2: float, y: float, label: str, color: str = DIMENSION_LINE_COLOR) -> None:
    if x2 <= x1:
        return
    parts.append(f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(f'<line x1="{x1:.1f}" y1="{y - 4:.1f}" x2="{x1:.1f}" y2="{y + 4:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(f'<line x1="{x2:.1f}" y1="{y - 4:.1f}" x2="{x2:.1f}" y2="{y + 4:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(f'<line x1="{x1 + 3:.1f}" y1="{y - 3:.1f}" x2="{x1:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(f'<line x1="{x1 + 3:.1f}" y1="{y + 3:.1f}" x2="{x1:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(f'<line x1="{x2 - 3:.1f}" y1="{y - 3:.1f}" x2="{x2:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(f'<line x1="{x2 - 3:.1f}" y1="{y + 3:.1f}" x2="{x2:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(svg_text((x1 + x2) / 2 - 34, y - 6, label, size=8, weight=500, color=color))


def draw_dimension_vertical(parts: list[str], x: float, y1: float, y2: float, label: str, color: str = DIMENSION_LINE_COLOR) -> None:
    if y2 <= y1:
        return
    parts.append(f'<line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(f'<line x1="{x - 4:.1f}" y1="{y1:.1f}" x2="{x + 4:.1f}" y2="{y1:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(f'<line x1="{x - 4:.1f}" y1="{y2:.1f}" x2="{x + 4:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(f'<line x1="{x - 3:.1f}" y1="{y1 + 3:.1f}" x2="{x:.1f}" y2="{y1:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(f'<line x1="{x + 3:.1f}" y1="{y1 + 3:.1f}" x2="{x:.1f}" y2="{y1:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(f'<line x1="{x - 3:.1f}" y1="{y2 - 3:.1f}" x2="{x:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(f'<line x1="{x + 3:.1f}" y1="{y2 - 3:.1f}" x2="{x:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="0.9"/>')
    parts.append(svg_text(x + 7, (y1 + y2) / 2, label, size=8, weight=500, color=color))


def draw_dimension_chains(
    parts: list[str],
    plan_left: float,
    plan_top: float,
    plan_right: float,
    plan_bottom: float,
    grouped_rows: list[list[dict[str, Any]]],
    rects: dict[str, dict[str, Any]],
    source_bounds_mm: dict[str, float] | None = None,
    profile: dict[str, Any] | None = None,
) -> None:
    if profile is None:
        profile = {}
    dim_color = style_color(profile, "dimension", DIMENSION_LINE_COLOR)
    show_subchains = style_bool(profile, "show_dimension_subchains", True)
    if source_bounds_mm:
        total_w_mm = int(round(source_bounds_mm.get("width_mm", 0.0)))
        total_d_mm = int(round(source_bounds_mm.get("depth_mm", 0.0)))
    else:
        total_w_mm = mm_from_px(plan_right - plan_left)
        total_d_mm = mm_from_px(plan_bottom - plan_top)

    draw_dimension_horizontal(parts, plan_left, plan_right, plan_bottom + 22, f"DIM:W {total_w_mm}mm", color=dim_color)
    draw_dimension_vertical(parts, plan_left - 28, plan_top, plan_bottom, f"DIM:D {total_d_mm}mm", color=dim_color)

    if not show_subchains:
        return

    if grouped_rows:
        row0 = grouped_rows[0]
        for idx, slot in enumerate(row0):
            rect = rects.get(slot["slot_id"])
            if not rect:
                continue
            x1 = float(rect["x"])
            x2 = x1 + float(rect["w"])
            width_mm = int(round(float(rect.get("w_mm", mm_from_px(x2 - x1)))))
            draw_dimension_horizontal(parts, x1, x2, plan_bottom + 40, f"DIM:C{idx + 1} {width_mm}", color=dim_color)

    for row_idx, row_slots in enumerate(grouped_rows):
        if not row_slots:
            continue
        first_rect = rects.get(row_slots[0]["slot_id"])
        if not first_rect:
            continue
        y1 = float(first_rect["y"])
        y2 = y1 + float(first_rect["h"])
        height_mm = int(round(float(first_rect.get("h_mm", mm_from_px(y2 - y1)))))
        draw_dimension_vertical(parts, plan_right + 20, y1, y2, f"DIM:R{row_idx + 1} {height_mm}", color=dim_color)


def draw_north_arrow(parts: list[str], center_x: float, center_y: float, profile: dict[str, Any]) -> None:
    r = 14.0
    text_color = style_color(profile, "text", "#222")
    parts.append(f'<circle cx="{center_x:.1f}" cy="{center_y:.1f}" r="{r:.1f}" fill="#ffffff" stroke="{text_color}" stroke-width="1.1"/>')
    points = f"{center_x:.1f},{center_y - 10:.1f} {center_x - 5:.1f},{center_y + 3:.1f} {center_x + 5:.1f},{center_y + 3:.1f}"
    parts.append(f'<polygon points="{points}" fill="{text_color}"/>')
    parts.append(svg_text(center_x - 10, center_y + 24, "N↑", size=10, weight=700, color=text_color))


def draw_material_legend(
    parts: list[str],
    x: float,
    y: float,
    width: float,
    height: float,
    interior_wall_px: float,
    exterior_wall_px: float,
    profile: dict[str, Any],
) -> None:
    text_color = style_color(profile, "text", "#222")
    muted_color = style_color(profile, "muted", "#333")
    outer_color = style_color(profile, "wall_outer", "#111")
    inner_color = style_color(profile, "wall_inner", "#1d1d1d")
    door_color = style_color(profile, "door", "#666")
    window_color = style_color(profile, "window", "#2d6ea3")
    furniture_fill = style_color(profile, "furniture_fill", "#f6f6f6")
    furniture_stroke = style_color(profile, "furniture_stroke", "#666")
    window_line_width = style_float(profile, "window_line_width_px", WINDOW_LINE_WIDTH_PX)

    parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" fill="#ffffff" stroke="{style_color(profile, "frame", "#b5b5b5")}" stroke-width="1.0"/>')
    parts.append(svg_text(x + 10, y + 18, "LEGEND:", size=11, weight=700, color=text_color))

    cy = y + 34
    parts.append(f'<line x1="{x + 10:.1f}" y1="{cy:.1f}" x2="{x + 48:.1f}" y2="{cy:.1f}" stroke="{outer_color}" stroke-width="{exterior_wall_px:.1f}"/>')
    parts.append(svg_text(x + 56, cy + 4, "Exterior wall", size=9, weight=500, color=muted_color))

    cy += 18
    parts.append(f'<line x1="{x + 10:.1f}" y1="{cy:.1f}" x2="{x + 48:.1f}" y2="{cy:.1f}" stroke="{inner_color}" stroke-width="{interior_wall_px:.1f}"/>')
    parts.append(svg_text(x + 56, cy + 4, "Interior wall", size=9, weight=500, color=muted_color))

    cy += 18
    parts.append(f'<line x1="{x + 10:.1f}" y1="{cy:.1f}" x2="{x + 38:.1f}" y2="{cy:.1f}" stroke="#ffffff" stroke-width="4.8"/>')
    parts.append(f'<line x1="{x + 24:.1f}" y1="{cy:.1f}" x2="{x + 40:.1f}" y2="{cy - 12:.1f}" stroke="{door_color}" stroke-width="1.1"/>')
    parts.append(svg_text(x + 56, cy + 4, "Door swing (DW)", size=9, weight=500, color=muted_color))

    cy += 18
    parts.append(f'<line x1="{x + 10:.1f}" y1="{cy:.1f}" x2="{x + 44:.1f}" y2="{cy:.1f}" stroke="#ffffff" stroke-width="4.8"/>')
    parts.append(f'<line x1="{x + 11:.1f}" y1="{cy:.1f}" x2="{x + 43:.1f}" y2="{cy:.1f}" stroke="{window_color}" stroke-width="{window_line_width:.1f}"/>')
    parts.append(svg_text(x + 56, cy + 4, "Window opening (WIN)", size=9, weight=500, color=muted_color))

    cy += 18
    parts.append(f'<polygon points="{x + 16:.1f},{cy - 6:.1f} {x + 26:.1f},{cy - 6:.1f} {x + 21:.1f},{cy + 3:.1f}" fill="{door_color}"/>')
    parts.append(svg_text(x + 56, cy + 4, "Entrance marker (ENT)", size=9, weight=500, color=muted_color))

    cy += 18
    parts.append(f'<rect x="{x + 10:.1f}" y="{cy - 7:.1f}" width="26" height="12" fill="{furniture_fill}" stroke="{furniture_stroke}" stroke-width="0.9"/>')
    parts.append(svg_text(x + 56, cy + 3, "Furniture block", size=9, weight=500, color=muted_color))


def draw_bottom_legend(
    parts: list[str],
    x: float,
    y: float,
    width: float,
    interior_wall_px: float,
    exterior_wall_px: float,
    profile: dict[str, Any],
    drawing_style: str,
    compact_entries: list[dict[str, str]] | None = None,
) -> None:
    text_color = style_color(profile, "text", "#111")
    muted_color = style_color(profile, "muted", "#64748b")
    outer_color = style_color(profile, "wall_outer", "#111")
    inner_color = style_color(profile, "wall_inner", "#334155")
    door_color = style_color(profile, "door", "#475569")
    window_color = style_color(profile, "window", "#2563eb")
    fills = profile.get("room_fills", {}) if isinstance(profile.get("room_fills"), dict) else {}

    parts.append(svg_text(x, y, "LEGEND:", size=9, weight=700, color=text_color))
    cursor = x + 58
    samples = [
        ("公共", fills.get("living", "#fff7ed")),
        ("臥室", fills.get("bedroom", "#eef2ff")),
        ("濕區", "url(#p2-bath-hatch)" if is_presentation_v2(profile, drawing_style) else fills.get("bath", "#ecfeff")),
        ("設備", "url(#p2-service-hatch)" if is_presentation_v2(profile, drawing_style) else fills.get("service", "#f1f5f9")),
        ("戶外", "url(#p2-outdoor-hatch)" if is_presentation_v2(profile, drawing_style) else fills.get("outdoor", "#ecfdf5")),
    ]
    for label, fill in samples:
        parts.append(f'<rect x="{cursor:.1f}" y="{y - 10:.1f}" width="18" height="10" fill="{fill}" stroke="#cbd5e1" stroke-width="0.8"/>')
        parts.append(svg_text(cursor + 23, y, label, size=9, weight=500, color=muted_color))
        cursor += 62

    line_x = min(x + width - 292, cursor + 8)
    parts.append(f'<line x1="{line_x:.1f}" y1="{y - 5:.1f}" x2="{line_x + 28:.1f}" y2="{y - 5:.1f}" stroke="{outer_color}" stroke-width="{exterior_wall_px:.1f}"/>')
    parts.append(svg_text(line_x + 36, y, "外牆", size=9, weight=500, color=muted_color))
    parts.append(f'<line x1="{line_x + 74:.1f}" y1="{y - 5:.1f}" x2="{line_x + 102:.1f}" y2="{y - 5:.1f}" stroke="{inner_color}" stroke-width="{interior_wall_px:.1f}"/>')
    parts.append(svg_text(line_x + 110, y, "內牆", size=9, weight=500, color=muted_color))
    parts.append(f'<line x1="{line_x + 148:.1f}" y1="{y - 5:.1f}" x2="{line_x + 174:.1f}" y2="{y - 5:.1f}" stroke="{window_color}" stroke-width="2.0"/>')
    parts.append(svg_text(line_x + 182, y, "窗", size=9, weight=500, color=muted_color))
    parts.append(f'<line x1="{line_x + 212:.1f}" y1="{y - 5:.1f}" x2="{line_x + 238:.1f}" y2="{y - 5:.1f}" stroke="{door_color}" stroke-width="1.2"/>')
    parts.append(svg_text(line_x + 246, y, "門", size=9, weight=500, color=muted_color))

    compact_entries = compact_entries or []
    if compact_entries:
        items = [f"{item['code']}={item['room_name']}" for item in compact_entries[:8]]
        suffix = " ..." if len(compact_entries) > 8 else ""
        parts.append(svg_text(x, y + 18, "短碼: " + " / ".join(items) + suffix, size=8, weight=500, color=muted_color))


def draw_elevation_indices(
    parts: list[str],
    plan_left: float,
    plan_top: float,
    plan_right: float,
    plan_bottom: float,
) -> None:
    mid_x = (plan_left + plan_right) / 2
    mid_y = (plan_top + plan_bottom) / 2

    parts.append(
        f'<line x1="{plan_left:.1f}" y1="{mid_y:.1f}" x2="{plan_right:.1f}" y2="{mid_y:.1f}" '
        'stroke="#888" stroke-width="0.9" stroke-dasharray="6 4"/>'
    )
    parts.append(f'<circle cx="{plan_left - 10:.1f}" cy="{mid_y:.1f}" r="8" fill="#fff" stroke="#666" stroke-width="1.0"/>')
    parts.append(f'<circle cx="{plan_right + 10:.1f}" cy="{mid_y:.1f}" r="8" fill="#fff" stroke="#666" stroke-width="1.0"/>')
    parts.append(svg_text(plan_left - 14, mid_y + 4, "A", size=9, weight=700, color="#333"))
    parts.append(svg_text(plan_right + 6, mid_y + 4, "A", size=9, weight=700, color="#333"))
    parts.append(svg_text(plan_right + 22, mid_y - 4, "ELEV:A-A", size=8, weight=600, color="#666"))

    parts.append(
        f'<line x1="{mid_x:.1f}" y1="{plan_top:.1f}" x2="{mid_x:.1f}" y2="{plan_bottom:.1f}" '
        'stroke="#888" stroke-width="0.9" stroke-dasharray="6 4"/>'
    )
    parts.append(f'<circle cx="{mid_x:.1f}" cy="{plan_top - 10:.1f}" r="8" fill="#fff" stroke="#666" stroke-width="1.0"/>')
    parts.append(f'<circle cx="{mid_x:.1f}" cy="{plan_bottom + 10:.1f}" r="8" fill="#fff" stroke="#666" stroke-width="1.0"/>')
    parts.append(svg_text(mid_x - 4, plan_top - 6, "B", size=9, weight=700, color="#333"))
    parts.append(svg_text(mid_x - 4, plan_bottom + 14, "B", size=9, weight=700, color="#333"))
    parts.append(svg_text(mid_x + 14, plan_top - 14, "ELEV:B-B", size=8, weight=600, color="#666"))


def render_floor_svg(
    floor: dict[str, Any],
    slots: list[dict[str, Any]],
    best_candidate: dict[str, Any],
    room_index: dict[str, dict[str, Any]],
    out_path: Path,
    drawing_style: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    slot_count = max(1, len(slots))
    use_source_rows = has_source_row_layout(slots)
    grouped_rows = group_slots_by_source_rows(slots) if use_source_rows else []
    if not grouped_rows:
        cols = choose_columns(slot_count)
        grouped_rows = [slots[i : i + cols] for i in range(0, len(slots), cols)] or [slots]
    use_precise_geometry = has_precise_slot_geometry(slots)

    row_count = len(grouped_rows)
    row_h = 148.0
    row_gap = 0.0
    col_gap = 0.0
    plan_left = style_float(profile, "plan_left_px", 58.0)
    plan_top = style_float(profile, "plan_top_px", 90.0)
    plan_w = style_float(profile, "plan_width_px", 1040.0)
    source_bounds_mm: dict[str, float] | None = None
    precise_scale = 1.0
    precise_min_x = 0.0
    precise_min_y = 0.0
    if use_precise_geometry:
        min_x_mm, min_y_mm, max_x_mm, max_y_mm = precise_bounds_mm(slots)
        source_w_mm = max(1.0, max_x_mm - min_x_mm)
        source_h_mm = max(1.0, max_y_mm - min_y_mm)
        precise_scale = plan_w / source_w_mm
        precise_min_x = min_x_mm
        precise_min_y = min_y_mm
        plan_h = max(320.0, source_h_mm * precise_scale)
        source_bounds_mm = {"width_mm": source_w_mm, "depth_mm": source_h_mm}
    else:
        plan_h = row_count * row_h + max(0, row_count - 1) * row_gap
    right_panel_w = style_float(profile, "right_panel_width_px", 36.0)
    bottom_padding = style_float(profile, "bottom_padding_px", 118.0)
    if style_bool(profile, "show_right_legend", False):
        right_panel_w = max(236.0, right_panel_w)
    width = int(plan_left + plan_w + right_panel_w)
    height = int(plan_top + plan_h + bottom_padding)
    plan_right = plan_left + plan_w
    plan_bottom = plan_top + plan_h

    pair_map = {p.get("slot_id", ""): p for p in best_candidate.get("pair_details", [])}
    scores = best_candidate.get("scores", {})
    strategy = best_candidate.get("id", "")
    interior_wall_px = max(1.8, WALL_MM["interior"] * PX_PER_MM * INTERIOR_WALL_FACTOR)
    exterior_wall_px = max(interior_wall_px + EXTERIOR_WALL_EXTRA_PX, WALL_MM["exterior"] * PX_PER_MM * INTERIOR_WALL_FACTOR)
    if is_presentation_v2(profile, drawing_style):
        interior_wall_px = max(2.2, interior_wall_px)
        exterior_wall_px = max(interior_wall_px + 2.0, exterior_wall_px)
    paper_color = style_color(profile, "paper", "#f6f6f6")
    plan_background = style_color(profile, "plan_background", "#ffffff")
    frame_color = style_color(profile, "frame", "#b5b5b5")
    text_color = style_color(profile, "text", "#111")
    muted_color = style_color(profile, "muted", "#555")
    wall_outer_color = style_color(profile, "wall_outer", "#111")
    wall_inner_color = style_color(profile, "wall_inner", "#1d1d1d")

    rects: dict[str, dict[str, Any]] = {}
    if use_precise_geometry:
        for slot in slots:
            slot_id = slot["slot_id"]
            geom = slot.get("geometry_mm", {})
            gx = _f(geom.get("x_mm"), 0.0)
            gy = _f(geom.get("y_mm"), 0.0)
            gw = max(1.0, _f(geom.get("w_mm"), 1.0))
            gh = max(1.0, _f(geom.get("h_mm"), 1.0))

            x = plan_left + (gx - precise_min_x) * precise_scale
            y = plan_top + (gy - precise_min_y) * precise_scale
            cell_w = max(36.0, gw * precise_scale)
            cell_h = max(36.0, gh * precise_scale)

            row_hint = int(slot.get("row_order", 0) or 0)
            col_hint = int(slot.get("col_order", 0) or 0)
            rects[slot_id] = {
                "slot": slot,
                "x": x,
                "y": y,
                "w": cell_w,
                "h": cell_h,
                "w_mm": gw,
                "h_mm": gh,
                "row_idx": row_hint if row_hint > 0 else 0,
                "col_idx": col_hint if col_hint > 0 else int(slot.get("order", 0) or 0),
                "sort_y": y,
                "sort_x": x,
            }
    else:
        for row_idx, row_slots in enumerate(grouped_rows):
            if not row_slots:
                continue
            y = plan_top + row_idx * (row_h + row_gap)
            weights = [max(0.1, float(slot.get("col_weight", 1.0) or 1.0)) for slot in row_slots]
            total_weight = sum(weights) or float(len(row_slots))
            available_w = plan_w - max(0, len(row_slots) - 1) * col_gap
            x = plan_left
            for col_idx, slot in enumerate(row_slots):
                if col_idx == len(row_slots) - 1:
                    cell_w = plan_left + plan_w - x
                else:
                    cell_w = available_w * (weights[col_idx] / total_weight)
                rects[slot["slot_id"]] = {
                    "slot": slot,
                    "x": x,
                    "y": y,
                    "w": max(64.0, cell_w),
                    "h": row_h,
                    "row_idx": row_idx,
                    "col_idx": col_idx,
                    "sort_y": y,
                    "sort_x": x,
                }
                x += cell_w + col_gap

    adjacency_edges = build_adjacency_edges(rects)
    slot_ids = [slot["slot_id"] for slot in slots if slot["slot_id"] in rects]
    root_slot = pick_root_slot(slots, pair_map)

    room_name_map: dict[str, str] = {}
    kind_map: dict[str, str] = {}
    for slot in slots:
        slot_id = slot["slot_id"]
        if slot_id not in rects:
            continue
        room_name = pick_room_name(slot, pair_map)
        room_name_map[slot_id] = room_name
        kind_map[slot_id] = room_kind(room_name)

    door_edges = choose_door_edges(slot_ids, adjacency_edges, root_slot, kind_map)

    room_by_slot: dict[str, dict[str, Any]] = {slot_id: {"outer_sides": {"left": True, "right": True, "top": True, "bottom": True}} for slot_id in slot_ids}
    for edge in adjacency_edges:
        a = edge["a"]
        b = edge["b"]
        if edge["orientation"] == "v":
            ax = float(rects[a]["x"]) + float(rects[a]["w"]) / 2
            bx = float(rects[b]["x"]) + float(rects[b]["w"]) / 2
            if ax < bx:
                room_by_slot[a]["outer_sides"]["right"] = False
                room_by_slot[b]["outer_sides"]["left"] = False
            else:
                room_by_slot[a]["outer_sides"]["left"] = False
                room_by_slot[b]["outer_sides"]["right"] = False
        else:
            ay = float(rects[a]["y"]) + float(rects[a]["h"]) / 2
            by = float(rects[b]["y"]) + float(rects[b]["h"]) / 2
            if ay < by:
                room_by_slot[a]["outer_sides"]["bottom"] = False
                room_by_slot[b]["outer_sides"]["top"] = False
            else:
                room_by_slot[a]["outer_sides"]["top"] = False
                room_by_slot[b]["outer_sides"]["bottom"] = False

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(floor["building_id"])} {html.escape(floor["floor_id"])}">'
    )
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "drawing_style": drawing_style,
        "presentation_version": presentation_version(profile, drawing_style),
        "building_id": floor.get("building_id", ""),
        "floor_id": floor.get("floor_id", ""),
        "candidate_id": best_candidate.get("id", ""),
        "validation_markers": VALIDATION_MARKERS,
    }
    parts.append(f"<metadata>{html.escape(json.dumps(metadata, ensure_ascii=False))}</metadata>")
    defs = presentation_defs(profile, drawing_style)
    if defs:
        parts.append(defs)
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="{paper_color}"/>')
    if is_presentation_v2(profile, drawing_style):
        parts.append(f'<rect x="{plan_left - 18:.1f}" y="{plan_top - 28:.1f}" width="{plan_w + 36:.1f}" height="{plan_h + 74:.1f}" fill="{plan_background}" stroke="{frame_color}" stroke-width="1.1"/>')
        parts.append(f'<rect x="{plan_left - 8:.1f}" y="{plan_top - 18:.1f}" width="{plan_w + 16:.1f}" height="{plan_h + 22:.1f}" fill="none" stroke="#e2e8f0" stroke-width="0.8"/>')
    else:
        parts.append(f'<rect x="{plan_left - 12:.1f}" y="{plan_top - 22:.1f}" width="{plan_w + 24:.1f}" height="{plan_h + 34:.1f}" fill="{plan_background}" stroke="{frame_color}" stroke-width="1.2"/>')

    title = f'[{floor["building_id"]}] {floor["floor_id"]} {normalize(floor.get("floor_title", ""))}'.strip()
    subtitle = normalize(floor.get("tab_label", "")) or "Floor Plan"
    parts.append(svg_text(plan_left, 32, title, size=19, weight=700, color=text_color))
    parts.append(svg_text(plan_left, 55, subtitle, size=12, weight=500, color=muted_color))
    if is_presentation_v2(profile, drawing_style):
        block_x = max(plan_left + 360, plan_right - 274)
        block_y = 18.0
        block_w = min(274.0, plan_right - block_x)
        parts.append(f'<rect x="{block_x:.1f}" y="{block_y:.1f}" width="{block_w:.1f}" height="48" fill="#ffffff" stroke="{frame_color}" stroke-width="0.8"/>')
        parts.append(svg_text(block_x + 10, block_y + 17, "住宅平面討論圖", size=10, weight=700, color=text_color))
        parts.append(svg_text(block_x + 10, block_y + 33, f"Selection: {strategy} | {drawing_style} v{presentation_version(profile, drawing_style)}", size=8, weight=500, color=muted_color))
        parts.append(svg_text(block_x + block_w - 84, block_y + 33, "Scale: diagram", size=8, weight=500, color=muted_color))
    if style_bool(profile, "show_debug_header", False) or style_bool(profile, "show_score_line", False):
        parts.append(
            svg_text(
                plan_left,
                76,
                f'Strategy: {strategy} | Total {scores.get("total", 0):.2f} | C {scores.get("circulation", 0):.1f} D {scores.get("daylight", 0):.1f} M {scores.get("mep", 0):.1f}',
                size=10,
                weight=500,
                color=muted_color,
            )
        )
    if style_bool(profile, "show_debug_header", False):
        parts.append(
            svg_text(
                plan_left,
                94,
                DEFAULTS_HEADER_LINE,
                size=9,
                weight=400,
                color=muted_color,
            )
        )
        parts.append(
            svg_text(
                plan_left,
                110,
                "Layout source: precise-mm geometry" if use_precise_geometry else "Layout source: heuristic row/column",
                size=9,
                weight=500,
                color=muted_color,
            )
        )

    ordered_slots = sorted(
        slot_ids,
        key=lambda sid: (
            float(rects[sid].get("sort_y", rects[sid]["y"])),
            float(rects[sid].get("sort_x", rects[sid]["x"])),
            int(rects[sid].get("row_idx", 0)),
            int(rects[sid].get("col_idx", 0)),
        ),
    )
    compact_label_entries: list[dict[str, str]] = []
    for slot_id in ordered_slots:
        rect = rects[slot_id]
        slot = rect["slot"]
        x = float(rect["x"])
        y = float(rect["y"])
        w = float(rect["w"])
        h = float(rect["h"])

        kind = kind_map.get(slot_id, "other")
        fill = room_fill_color(profile, kind, drawing_style)
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{wall_inner_color}" stroke-width="{interior_wall_px:.1f}"/>')

        if style_bool(profile, "show_furniture", True) and is_presentation_v2(profile, drawing_style):
            draw_furniture(parts, rect, kind, profile)

        room_name = room_name_map.get(slot_id, "未指派")
        label_info = room_label_info(room_name, slot, w, h, profile, drawing_style)
        label = str(label_info["label"])
        if label_info.get("compact"):
            compact_label_entries.append({"code": label, "room_name": str(label_info["full_label"]), "slot_id": slot_id})

        size_text = truncate_text(room_area_text(slot, pair_map, room_index), text_limit_from_width(w, 7, 32))
        if is_presentation_v2(profile, drawing_style):
            center_x = x + w / 2
            center_y = y + h / 2
            halo = style_color(profile, "label_halo", "#ffffff")
            parts.append(svg_text_centered(center_x, center_y - (7 if size_text and not label_info.get("compact") else 0), label, size=12, weight=700, color=text_color, halo=halo))
            if size_text and not label_info.get("compact") and h >= 70 and w >= 112:
                parts.append(svg_text_centered(center_x, center_y + 11, size_text, size=8, weight=500, color=muted_color, halo=halo))
        else:
            parts.append(svg_text(x + 8, y + 20, label, size=12, weight=700, color=text_color))
            if size_text and h >= 70 and w >= 95:
                parts.append(svg_text(x + 8, y + 38, size_text, size=9, weight=400, color=muted_color))

        if style_bool(profile, "show_room_notes", False):
            notes = pick_room_notes(slot, pair_map, room_index)
            for idx, note in enumerate(notes):
                note_line = truncate_text(note, text_limit_from_width(w, 10, 64))
                note_y = y + h - 8 - (len(notes) - idx - 1) * 11
                parts.append(svg_text(x + 8, note_y, note_line, size=8, weight=400, color=muted_color))

        if style_bool(profile, "show_furniture", True) and not is_presentation_v2(profile, drawing_style):
            draw_furniture(parts, rect, kind, profile)

    for slot_id in ordered_slots:
        rect = rects[slot_id]
        x = float(rect["x"])
        y = float(rect["y"])
        w = float(rect["w"])
        h = float(rect["h"])
        outer = room_by_slot.get(slot_id, {}).get("outer_sides", {})
        if outer.get("top"):
            parts.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x + w:.1f}" y2="{y:.1f}" stroke="{wall_outer_color}" stroke-width="{exterior_wall_px:.1f}"/>')
        if outer.get("right"):
            parts.append(f'<line x1="{x + w:.1f}" y1="{y:.1f}" x2="{x + w:.1f}" y2="{y + h:.1f}" stroke="{wall_outer_color}" stroke-width="{exterior_wall_px:.1f}"/>')
        if outer.get("bottom"):
            parts.append(f'<line x1="{x:.1f}" y1="{y + h:.1f}" x2="{x + w:.1f}" y2="{y + h:.1f}" stroke="{wall_outer_color}" stroke-width="{exterior_wall_px:.1f}"/>')
        if outer.get("left"):
            parts.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{y + h:.1f}" stroke="{wall_outer_color}" stroke-width="{exterior_wall_px:.1f}"/>')

    root_entry_side = ""
    if root_slot and root_slot in rects:
        root_entry_side = pick_entrance_side(
            rects[root_slot],
            room_by_slot,
            root_slot,
            plan_left,
            plan_top,
            plan_right,
            plan_bottom,
        )

    window_specs = choose_window_specs(slot_ids, rects, room_by_slot, kind_map, root_slot, root_entry_side)
    for win in window_specs:
        slot_id = win["slot_id"]
        rect = rects.get(slot_id)
        if not rect:
            continue
        draw_window_symbol(parts, rect, str(win["side"]), int(win["width_mm"]), exterior_wall_px, profile)

    for edge in door_edges:
        draw_internal_door(parts, edge, rects, kind_map, profile)

    if root_slot and root_slot in rects and root_entry_side:
        draw_entrance_marker(parts, rects[root_slot], root_entry_side, profile)

    if style_bool(profile, "show_elevation_indices", True):
        draw_elevation_indices(parts, plan_left, plan_top, plan_right, plan_bottom)
    if style_bool(profile, "show_dimensions", True):
        draw_dimension_chains(parts, plan_left, plan_top, plan_right, plan_bottom, grouped_rows, rects, source_bounds_mm=source_bounds_mm, profile=profile)
    draw_north_arrow(parts, plan_right + 24, 40, profile)
    if style_bool(profile, "show_right_legend", False):
        draw_material_legend(parts, plan_right + 18, 82, right_panel_w - 28, 148, interior_wall_px, exterior_wall_px, profile)
    if style_bool(profile, "show_bottom_legend", False):
        draw_bottom_legend(parts, plan_left, plan_bottom + 58, plan_w, interior_wall_px, exterior_wall_px, profile, drawing_style, compact_label_entries)

    parts.append(svg_text(plan_left, height - 12, f"Generated: {now_iso()} | {SCHEMA_VERSION} | style={drawing_style}", size=9, weight=400, color=muted_color))
    parts.append("</svg>")

    out_path.write_text("\n".join(parts), encoding="utf-8")
    return {
        "file": out_path.name,
        "path": str(out_path),
        "width": width,
        "height": height,
        "drawing_style": drawing_style,
        "slot_count": len(slots),
        "strategy": strategy,
        "score_total": scores.get("total", 0),
        "layout_mode": "blueprint-precise-mm" if use_precise_geometry else ("blueprint-source-row" if use_source_rows else "blueprint-grid"),
        "precise_geometry": use_precise_geometry,
        "window_count": len(window_specs),
        "has_dimensions": style_bool(profile, "show_dimensions", True),
        "has_legend": style_bool(profile, "show_right_legend", False) or style_bool(profile, "show_bottom_legend", False),
        "has_elevation_index": style_bool(profile, "show_elevation_indices", True),
        "presentation_version": presentation_version(profile, drawing_style),
        "compact_label_count": len(compact_label_entries),
        "compact_labels": compact_label_entries,
    }


def render_index_html(records: list[dict[str, Any]], drawing_style: str) -> str:
    cards = []
    for rec in records:
        cards.append(
            f"""
      <article class="card">
        <h3>{html.escape(rec['title'])}</h3>
        <p class="meta">Style: <b>{html.escape(drawing_style)}</b> · Strategy: <b>{html.escape(rec['strategy'])}</b> · Total: <b>{rec['score_total']:.2f}</b> · Slots: {rec['slot_count']} · Compact labels: {rec.get('compact_label_count', 0)}</p>
        <a class="link" href="{html.escape(rec['file'])}" target="_blank">{html.escape(rec['file'])}</a>
        <img src="{html.escape(rec['file'])}" alt="{html.escape(rec['title'])}" loading="lazy"/>
      </article>
"""
        )

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Top1 SVG Index</title>
  <style>
    body {{
      margin: 0; padding: 18px;
      font-family: "{html.escape(SVG_FONT_FAMILY)}";
      background: linear-gradient(150deg,#0b1020,#18243a);
      color: #e6eefb;
    }}
    h1 {{ margin: 0 0 8px; color: #f0b52b; }}
    .sub {{ color: #9fb4d2; margin-bottom: 16px; font-size: .9rem; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
      gap: 14px;
    }}
    .card {{
      border: 1px solid #324c72; border-radius: 12px;
      background: rgba(12,22,38,.72);
      padding: 12px;
    }}
    .card h3 {{ margin: 0 0 6px; font-size: 1rem; }}
    .meta {{ margin: 0 0 10px; color: #b4c6de; font-size: .82rem; }}
    .link {{ color: #7de0d7; font-size: .8rem; text-decoration: none; }}
    .link:hover {{ text-decoration: underline; }}
    img {{
      margin-top: 10px;
      width: 100%;
      border: 1px solid #405c88;
      border-radius: 10px;
      background: #111b2d;
    }}
  </style>
</head>
<body>
  <h1>Top1 SVG Export Index</h1>
  <div class="sub">Generated: {html.escape(now_iso())} · Drawing style: {html.escape(drawing_style)} · Total: {len(records)} floors</div>
  <section class="grid">
    {''.join(cards)}
  </section>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    profile = drawing_profile(args.style)
    if not PROGRAM_FILE.exists():
        raise SystemExit(f"Missing {PROGRAM_FILE}. Run build_room_program.py first.")
    if not CANDIDATES_FILE.exists():
        raise SystemExit(f"Missing {CANDIDATES_FILE}. Run generate_layout_candidates.py first.")

    program = json.loads(PROGRAM_FILE.read_text(encoding="utf-8"))
    candidates = json.loads(CANDIDATES_FILE.read_text(encoding="utf-8"))
    slot_index = build_slot_index(program)
    room_index = build_room_index(program)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old_svg in OUT_DIR.glob("*.svg"):
        old_svg.unlink()

    records = []
    skipped = []
    for floor in candidates.get("floors", []):
        b_id = floor.get("building_id", "")
        f_id = floor.get("floor_id", "")
        best_id = floor.get("best_candidate_id", "")
        cand_map = {c.get("id", ""): c for c in floor.get("candidates", [])}
        selected = None
        if args.selection == "baseline":
            selected = cand_map.get("baseline")
        if not selected:
            selected = cand_map.get(best_id) or (floor.get("candidates") or [None])[0]
        if not selected:
            skipped.append({"building_id": b_id, "floor_id": f_id, "reason": "no candidates"})
            continue

        slots = slot_index.get((b_id, f_id), [])
        if not slots:
            skipped.append({"building_id": b_id, "floor_id": f_id, "reason": "no slots"})
            continue

        slug = f"{safe_slug(b_id)}_{safe_slug(f_id)}_{safe_slug(selected.get('id', args.selection))}"
        out_file = OUT_DIR / f"{slug}.svg"
        rendered = render_floor_svg(floor, slots, selected, room_index, out_file, args.style, profile)
        record = {
            "building_id": b_id,
            "floor_id": f_id,
            "title": f"[{b_id}] {f_id} {normalize(floor.get('floor_title', ''))}".strip(),
            "strategy": rendered["strategy"],
            "score_total": rendered["score_total"],
            "slot_count": rendered["slot_count"],
            "drawing_style": args.style,
            "presentation_version": rendered.get("presentation_version", 0),
            "compact_label_count": rendered.get("compact_label_count", 0),
            "file": out_file.name,
            "path": str(out_file),
            "svg": rendered,
        }
        records.append(record)

    records.sort(key=lambda r: (r["building_id"], r["floor_id"]))
    compact_label_count = sum(int(r.get("compact_label_count", 0) or 0) for r in records)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "source_files": {"program": PROGRAM_FILE.name, "candidates": CANDIDATES_FILE.name},
        "defaults_profile": {
            "schema_version": RESIDENTIAL_DEFAULTS.get("schema_version", ""),
            "profile": RESIDENTIAL_DEFAULTS.get("profile", ""),
            "config_path": RESIDENTIAL_DEFAULTS.get("_meta", {}).get("config_path", ""),
            "config_loaded": RESIDENTIAL_DEFAULTS.get("_meta", {}).get("config_loaded", False),
        },
        "candidate_selection": args.selection,
        "drawing_style": args.style,
        "presentation_version": presentation_version(profile, args.style),
        "compact_label_count": compact_label_count,
        "exported_count": len(records),
        "skipped_count": len(skipped),
        "exports": records,
        "skipped": skipped,
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    INDEX_FILE.write_text(render_index_html(records, args.style), encoding="utf-8")

    print(f"Exported SVG count: {len(records)}")
    print(f"Skipped floors:      {len(skipped)}")
    print(f"Selection mode:      {args.selection}")
    print(f"Drawing style:       {args.style}")
    print(f"Manifest: {MANIFEST_FILE}")
    print(f"Index:    {INDEX_FILE}")


if __name__ == "__main__":
    main()

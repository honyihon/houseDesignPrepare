#!/usr/bin/env python3
"""Run static consistency checks against canonical (non _tmp) building HTML files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.spatial_metadata import (  # noqa: E402
    is_daylight_exempt,
    nearest_declared_side,
    parse_cell_spatial,
    parse_floor_orientation,
    window_issue_level,
)
from lib.dimension_overrides import (  # noqa: E402
    PING_TO_SQM,
    load_overrides,
)
from lib.standards import load_residential_defaults  # noqa: E402

OUTPUT_PATH = ROOT / "structured" / "expert_review" / "html_consistency.json"

# A floor whose cells leave this much of the envelope unaccounted for is either
# missing a cell or has the wrong outer dimensions.  Both matter: floor_area,
# daylight factor and the egress proxy are all computed off this envelope.
COVERAGE_VOID_MIN_SQM = 2.0
COVERAGE_VOID_MIN_RATIO = 0.05

# Ratio of (area written in the HTML) to (area implied by the mm geometry).
# Outside this band the two disagree by more than rounding or wall thickness
# can explain, so one of them is wrong.
AREA_MATCH_MIN_RATIO = 0.80
AREA_MATCH_MAX_RATIO = 1.25

# Floors of the same building should sit on the same footprint.  Roof levels are
# legitimately smaller, so they are excluded.
FOOTPRINT_TOLERANCE_MM = 100.0
HTML_FILE_MAP: dict[str, str] = {
    "A": "AbuildingView.html",
    "B": "BbuildingView.html",
    "C": "CbuildingView.html",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def text_of(node: Tag | None) -> str:
    if node is None:
        return ""
    return normalize_whitespace(node.get_text(" ", strip=True))


def parse_highlight_room(onclick: str) -> str:
    raw = onclick or ""
    m = re.search(r"highlightRoom\(\s*'([^']+)'", raw)
    if m:
        return m.group(1)
    m = re.search(r'highlightRoom\(\s*"([^"]+)"', raw)
    return m.group(1) if m else ""


def to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def truthy_attr(value: str | None) -> bool:
    if value is None:
        return False
    token = normalize_whitespace(value).lower()
    if token in {"", "1", "true", "yes", "on", "y"}:
        return True
    return token not in {"0", "false", "no", "off", "n"}


def parse_buildings(raw: str) -> list[str]:
    values: list[str] = []
    for token in raw.split(","):
        key = normalize_whitespace(token).upper()
        if key in HTML_FILE_MAP and key not in values:
            values.append(key)
    return values or ["A", "B", "C"]


def normalized_promotion_categories(spatial_config: dict[str, Any]) -> dict[str, set[str]]:
    raw = spatial_config.get("ifc_promotion", {})
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, set[str]] = {}
    for key, values in raw.items():
        if isinstance(values, list):
            normalized[str(key).strip().lower()] = {
                normalize_whitespace(value).lower() for value in values if normalize_whitespace(str(value))
            }
    return normalized


def promoted_level(mode: str, promotions: dict[str, set[str]], category: str, default: str = "warning") -> str:
    if mode == "ifc" and category in promotions.get(category, set()):
        return "critical"
    return default


def floor_label(floor: Tag, floor_id: str) -> str:
    icon = text_of(floor.select_one(".floor-title-icon"))
    if icon:
        return icon.upper()
    floor_token = normalize_whitespace(floor_id).upper()
    if floor_token in {"FLOOR-1", "FLOOR_1"}:
        return "1F"
    title = text_of(floor.select_one(".floor-title")) or floor_id
    return title.upper()


def is_ground_floor_label(label: str) -> bool:
    return label in {"1F", "GF", "G/F", "GROUND FLOOR"}


def is_roof_label(label: str) -> bool:
    """Roof levels legitimately sit on a smaller footprint than the floors below."""

    token = normalize_whitespace(label).upper()
    return token in {"RF", "R/F", "ROOF", "屋頂", "頂樓"} or token.startswith("RF")


def overlap(
    a: dict[str, float],
    b: dict[str, float],
    tolerance_mm: float = 1.0,
) -> bool:
    ax1, ay1 = a["x_mm"], a["y_mm"]
    ax2, ay2 = ax1 + a["w_mm"], ay1 + a["h_mm"]
    bx1, by1 = b["x_mm"], b["y_mm"]
    bx2, by2 = bx1 + b["w_mm"], by1 + b["h_mm"]
    overlap_w = min(ax2, bx2) - max(ax1, bx1)
    overlap_h = min(ay2, by2) - max(ay1, by1)
    return overlap_w > tolerance_mm and overlap_h > tolerance_mm


def issue(
    issues: list[dict[str, Any]],
    level: str,
    building_id: str,
    file_name: str,
    floor_id: str,
    code: str,
    message: str,
    evidence: str = "",
    fix_hint: str = "",
) -> None:
    issues.append(
        {
            "level": level,
            "building_id": building_id,
            "file": file_name,
            "floor_id": floor_id,
            "code": code,
            "message": message,
            "evidence": evidence,
            "fix_hint": fix_hint,
        }
    )


def declared_area_sqm(cell: Tag) -> tuple[float | None, str]:
    """Area written on the cell in the HTML, in m², plus the text it came from.

    Recognises both forms used in these pages: ``約 8 坪`` and ``約 5.5m × 6.0m``.
    """

    raw = text_of(cell.select_one(".cell-size"))
    if not raw:
        return None, ""

    dim = re.search(r"(\d+(?:\.\d+)?)\s*m\s*[x×]\s*(\d+(?:\.\d+)?)\s*m", raw, re.IGNORECASE)
    if dim:
        return float(dim.group(1)) * float(dim.group(2)), raw

    ping = re.search(r"(\d+(?:\.\d+)?)\s*坪", raw)
    if ping:
        return float(ping.group(1)) * PING_TO_SQM, raw

    return None, raw


def covered_area_sqmm(cells: list[dict[str, Any]]) -> float:
    """Union area of the cell rectangles, in mm².

    Sweeps the distinct x edges so overlapping cells are not counted twice —
    summing w*h would hide a void behind an overlap of the same size.
    """

    if not cells:
        return 0.0
    xs = sorted({c["x_mm"] for c in cells} | {c["x_mm"] + c["w_mm"] for c in cells})
    total = 0.0
    for left, right in zip(xs, xs[1:]):
        strip_w = right - left
        if strip_w <= 0:
            continue
        spans = sorted(
            (c["y_mm"], c["y_mm"] + c["h_mm"])
            for c in cells
            if c["x_mm"] < right and c["x_mm"] + c["w_mm"] > left
        )
        merged_h = 0.0
        cur_lo = cur_hi = None
        for lo, hi in spans:
            if cur_hi is None or lo > cur_hi:
                if cur_hi is not None:
                    merged_h += cur_hi - cur_lo
                cur_lo, cur_hi = lo, hi
            else:
                cur_hi = max(cur_hi, hi)
        if cur_hi is not None:
            merged_h += cur_hi - cur_lo
        total += strip_w * merged_h
    return total


def check_building_footprint(
    building_id: str,
    file_name: str,
    envelopes: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    """Floors of one building should stack on a consistent footprint.

    Differing width/depth per floor means the envelope numbers are placeholders,
    not a real building: everything derived from floor area inherits the error.
    Roof levels are excluded because a smaller roof deck is legitimate.
    """

    candidates = [e for e in envelopes if not is_roof_label(e["floor_name"])]
    if len(candidates) < 2:
        return

    widths = [e["width_mm"] for e in candidates]
    depths = [e["depth_mm"] for e in candidates]
    width_spread = max(widths) - min(widths)
    depth_spread = max(depths) - min(depths)
    if width_spread <= FOOTPRINT_TOLERANCE_MM and depth_spread <= FOOTPRINT_TOLERANCE_MM:
        return

    detail = "; ".join(
        f"{e['floor_id']}={e['width_mm']:.0f}x{e['depth_mm']:.0f}mm" for e in candidates
    )
    issue(
        issues,
        "warning",
        building_id,
        file_name,
        "<building>",
        "FOOTPRINT_INCONSISTENT",
        (
            f"Floor envelopes differ across {len(candidates)} floors "
            f"(width spread {width_spread:.0f}mm, depth spread {depth_spread:.0f}mm)"
        ),
        evidence=detail,
        fix_hint=(
            "同一棟各層應共用同一外框。實測後在 inputs/dimensions.json 逐層填入 "
            "width_mm / depth_mm。"
        ),
    )


def check_floor_geometry(
    building_id: str,
    file_name: str,
    floor: Tag,
    issues: list[dict[str, Any]],
    door_min_mm: int,
    door_max_mm: int,
    window_min_mm: int,
    window_max_mm: int,
    mode: str = "draft",
    spatial_config: dict[str, Any] | None = None,
    overrides: Any = None,
) -> dict[str, Any] | None:
    """Check one floor.  Returns its envelope for the building-level footprint check."""

    floor_id = normalize_whitespace(floor.get("id", "")) or "<no-id>"
    floor_w = to_float(floor.get("data-floor-width-mm"))
    floor_d = to_float(floor.get("data-floor-depth-mm"))
    spatial_config = spatial_config or {}
    promotions = normalized_promotion_categories(spatial_config)
    overlap_tolerance_mm = to_float(spatial_config.get("geometry_overlap_tolerance_mm"))
    if overlap_tolerance_mm is None or overlap_tolerance_mm < 0:
        overlap_tolerance_mm = 1.0
    orientation = parse_floor_orientation(floor.attrs)
    direction_config = spatial_config.get("direction", {})
    floor_name = floor_label(floor, floor_id)
    is_ground_floor = is_ground_floor_label(floor_name)
    if (
        orientation["front_side"] != "unknown"
        and orientation["rear_side"] != "unknown"
        and orientation["front_side"] == orientation["rear_side"]
    ):
        issue(
            issues,
            "warning",
            building_id,
            file_name,
            floor_id,
        "ORIENTATION_CONFLICT",
        "data-front-side and data-rear-side must not be the same",
        evidence=f"front={orientation['front_side']}; rear={orientation['rear_side']}",
        fix_hint="調整 data-front-side / data-rear-side，使前後方向可區分。",
    )
    if orientation["front_side"] == "unknown" or orientation["rear_side"] == "unknown":
        issue(
            issues,
            "info",
            building_id,
            file_name,
            floor_id,
            "ORIENTATION_UNRESOLVED",
            "Floor front/rear orientation metadata is not fully confirmed",
            evidence=f"front={orientation['front_side']}; rear={orientation['rear_side']}",
            fix_hint="若方位已確認，補 data-front-side 與 data-rear-side；未確認則保留 unknown。",
        )

    rooms = {
        normalize_whitespace((room.get("id", "") or "").replace("room-", "", 1))
        for room in floor.select(".room")
    }
    rooms.discard("")

    geometry_cells: list[dict[str, Any]] = []
    unresolved_targets: list[str] = []
    referenced_rooms: set[str] = set()
    entry_count = 0

    for idx, cell in enumerate(floor.select(".plan-cell"), start=1):
        x = to_float(cell.get("data-x-mm"))
        y = to_float(cell.get("data-y-mm"))
        w = to_float(cell.get("data-w-mm"))
        h = to_float(cell.get("data-h-mm"))
        label = text_of(cell.select_one(".cell-name")) or f"cell-{idx}"
        classes = [str(cls) for cls in (cell.get("class") or []) if str(cls) != "plan-cell"]
        spatial = parse_cell_spatial(cell.attrs, classes)
        # Same key the override file uses: the highlightRoom target, else the
        # cell order.  Mirrors lib.dimension_overrides.cell_key, which reads the
        # room program's target_room_local_id — that field is exactly this
        # onclick argument, so the two agree.
        override_key = parse_highlight_room(normalize_whitespace(cell.get("onclick", ""))) or f"cell-{idx}"

        if None in {x, y, w, h}:
            issue(
                issues,
                "critical",
                building_id,
                file_name,
                floor_id,
                "MISSING_CELL_GEOMETRY",
                f"{label} missing one of data-x-mm/y-mm/w-mm/h-mm",
                evidence=f"cell-{idx}",
                fix_hint="補齊 plan-cell 的 x/y/w/h mm 幾何欄位。",
            )
        else:
            geometry_valid = x >= 0 and y >= 0 and w > 0 and h > 0
            if not geometry_valid:
                issue(
                    issues,
                    "critical",
                    building_id,
                    file_name,
                    floor_id,
                    "INVALID_CELL_GEOMETRY",
                    f"{label} has invalid geometry x={x}, y={y}, w={w}, h={h}",
                    evidence=f"cell-{idx}",
                    fix_hint="修正為非負座標且寬高大於 0。",
                )
            else:
                geometry_cells.append(
                    {
                        "idx": idx,
                        "label": label,
                        "override_key": override_key,
                        "x_mm": float(x),
                        "y_mm": float(y),
                        "w_mm": float(w),
                        "h_mm": float(h),
                    }
                )
                if spatial.get("facing") in {"front", "rear"}:
                    nearest = nearest_declared_side(
                        floor_w,
                        floor_d,
                        {"x_mm": float(x), "y_mm": float(y), "w_mm": float(w), "h_mm": float(h)},
                        orientation["front_side"],
                        orientation["rear_side"],
                        float(direction_config.get("ambiguous_center_tolerance_ratio", 0.10)),
                        float(direction_config.get("span_ambiguity_ratio", 0.70)),
                    )
                    if not nearest.get("ambiguous") and nearest.get("nearest_role") != spatial.get("facing"):
                        level = "warning" if mode == "ifc" else "info"
                        issue(
                            issues,
                            level,
                            building_id,
                            file_name,
                            floor_id,
                            "FACING_GEOMETRY_MISMATCH",
                            f"{label} data-facing={spatial.get('facing')} but geometry is nearest {nearest.get('nearest_role')}",
                            evidence=f"cell-{idx}; nearest_side={nearest.get('nearest_side')}",
                            fix_hint="確認 data-facing 是否表示開口方向，或調整 floor front/rear side metadata。",
                        )
                stated_sqm, stated_text = declared_area_sqm(cell)
                if stated_sqm and stated_sqm > 0:
                    geometry_sqm = (w * h) / 1_000_000.0
                    ratio = geometry_sqm / stated_sqm if stated_sqm else 0.0
                    if not (AREA_MATCH_MIN_RATIO <= ratio <= AREA_MATCH_MAX_RATIO):
                        issue(
                            issues,
                            "warning",
                            building_id,
                            file_name,
                            floor_id,
                            "AREA_TEXT_MISMATCH",
                            f"{label} states {stated_sqm:.1f} m² but its geometry is {geometry_sqm:.1f} m²",
                            evidence=(
                                f"cell-{idx}: text={stated_text!r}; "
                                f"{w:.0f}x{h:.0f}mm; ratio={ratio:.2f}"
                            ),
                            fix_hint=(
                                "文字標示與 mm 幾何其中之一有誤。實測後填入 inputs/dimensions.json "
                                "並將 _provenance 設為 measured。"
                            ),
                        )

                if floor_w is not None and floor_d is not None:
                    if x + w > floor_w or y + h > floor_d:
                        issue(
                            issues,
                            "warning",
                            building_id,
                            file_name,
                            floor_id,
                            "CELL_OUT_OF_BOUND",
                            f"{label} exceeds floor envelope",
                            evidence=f"cell-{idx}: x+w={x+w}, y+h={y+h}, floor={floor_w}x{floor_d}",
                            fix_hint="調整 cell 幾何或樓層外框尺寸。",
                        )

        door_mm = to_int(cell.get("data-door-mm"))
        raw_window_mm = cell.get("data-window-mm")
        window_mm = to_int(raw_window_mm)
        has_window_attr = cell.has_attr("data-window-mm")
        is_window_outside_range = window_mm is None or not (window_min_mm <= window_mm <= window_max_mm)
        if door_mm is not None and not (door_min_mm <= door_mm <= door_max_mm):
            issue(
                issues,
                "warning",
                building_id,
                file_name,
                floor_id,
                "DOOR_RANGE",
                f"{label} data-door-mm={door_mm} out of range [{door_min_mm}, {door_max_mm}]",
                evidence=f"cell-{idx}",
                fix_hint="依常見住宅尺度調整門寬。",
            )
        if has_window_attr and is_daylight_exempt(spatial) and is_window_outside_range:
            issue(
                issues,
                "info",
                building_id,
                file_name,
                floor_id,
                "DAYLIGHT_EXEMPTION",
                f"{label} is explicitly marked as not daylight-required",
                evidence=f"cell-{idx}; data-window-mm={raw_window_mm}",
                fix_hint="確認此空間仍有符合設計需求的通風、空調與消防排煙策略。",
            )
        elif has_window_attr and window_mm is None:
            issue(
                issues,
                "warning",
                building_id,
                file_name,
                floor_id,
                "WINDOW_INVALID",
                f"{label} data-window-mm={raw_window_mm!r} is not a valid mm value",
                evidence=f"cell-{idx}",
                fix_hint="提供可解析為數值的 data-window-mm。",
            )
        else:
            window_level = window_issue_level(
                spatial,
                classes,
                has_window_attr,
                window_mm,
                window_min_mm,
                window_max_mm,
                spatial_config.get("opening_required_roles", []),
            )
            if window_level == "warning" and has_window_attr:
                issue(
                    issues,
                    "warning",
                    building_id,
                    file_name,
                    floor_id,
                    "WINDOW_RANGE",
                    f"{label} data-window-mm={window_mm} out of range [{window_min_mm}, {window_max_mm}]",
                    evidence=f"cell-{idx}",
                    fix_hint="依採光與法規調整窗寬，戶外空間請標 data-outdoor-role。",
                )
            elif window_level == "warning":
                issue(
                    issues,
                    "warning",
                    building_id,
                    file_name,
                    floor_id,
                    "WINDOW_MISSING",
                    f"{label} missing data-window-mm for an indoor-like cell",
                    evidence=f"cell-{idx}",
                    fix_hint="室內格位補上 data-window-mm；戶外空間請標 data-outdoor-role。",
                )
            elif window_level == "info":
                issue(
                    issues,
                    "info",
                    building_id,
                    file_name,
                    floor_id,
                    "WINDOW_MISSING_OPTIONAL",
                    f"{label} missing optional data-window-mm for role {spatial.get('outdoor_role')}",
                    evidence=f"cell-{idx}",
                    fix_hint="若此戶外角色需要開口資料，補上 data-window-mm。",
                )

        if truthy_attr(cell.get("data-entry")):
            entry_count += 1

        target = parse_highlight_room(normalize_whitespace(cell.get("onclick", "")))
        if target:
            if target not in rooms:
                unresolved_targets.append(f"{label}->{target}")
            else:
                referenced_rooms.add(target)

    for i in range(len(geometry_cells)):
        for j in range(i + 1, len(geometry_cells)):
            if overlap(
                geometry_cells[i],
                geometry_cells[j],
                tolerance_mm=overlap_tolerance_mm,
            ):
                issue(
                    issues,
                    promoted_level(mode, promotions, "cell_overlap"),
                    building_id,
                    file_name,
                    floor_id,
                    "CELL_OVERLAP",
                    f"{geometry_cells[i]['label']} overlaps {geometry_cells[j]['label']}",
                    evidence=f"cell-{geometry_cells[i]['idx']} vs cell-{geometry_cells[j]['idx']}",
                    fix_hint="調整 x/y/w/h 避免重疊。",
                )

    if geometry_cells and floor_w and floor_d:
        envelope_sqm = (floor_w * floor_d) / 1_000_000.0
        void_sqm = envelope_sqm - covered_area_sqmm(geometry_cells) / 1_000_000.0
        void_ratio = void_sqm / envelope_sqm if envelope_sqm else 0.0
        if void_sqm > COVERAGE_VOID_MIN_SQM and void_ratio > COVERAGE_VOID_MIN_RATIO:
            issue(
                issues,
                "warning",
                building_id,
                file_name,
                floor_id,
                "FLOOR_COVERAGE_VOID",
                f"{void_sqm:.1f} m² of the floor envelope is not covered by any cell",
                evidence=(
                    f"envelope={envelope_sqm:.1f} m² ({floor_w:.0f}x{floor_d:.0f}mm); "
                    f"void={void_ratio * 100:.0f}%"
                ),
                fix_hint="補上缺少的 plan-cell，或修正樓層外框 data-floor-width-mm / data-floor-depth-mm。",
            )

    if overrides is not None and geometry_cells:
        auto_cells = [
            c
            for c in geometry_cells
            if not overrides.cell(building_id, floor_id, c["override_key"])
        ]
        if auto_cells:
            issue(
                issues,
                "info",
                building_id,
                file_name,
                floor_id,
                "GEOMETRY_PROVENANCE_AUTO",
                f"{len(auto_cells)}/{len(geometry_cells)} cells still use auto-derived (guessed) geometry",
                evidence="; ".join(c["label"] for c in auto_cells[:6])
                + ("; …" if len(auto_cells) > 6 else ""),
                fix_hint="見 structured/dimension_todo.md；實測後填入 inputs/dimensions.json。",
            )

    if entry_count != 1:
        if is_ground_floor:
            issue(
                issues,
                "warning",
                building_id,
                file_name,
                floor_id,
                "ENTRY_COUNT",
                f"Expected exactly 1 main entry cell on {floor_name}, got {entry_count}",
                evidence=f"entry_count={entry_count}",
                fix_hint="首層應保留一個主要出入口 data-entry=\"true\"。",
            )
        else:
            issue(
                issues,
                "info",
                building_id,
                file_name,
                floor_id,
                "ENTRY_COUNT_UPPER_FLOOR",
                f"Expected exactly 1 stair or landing entry cell on {floor_name}, got {entry_count}",
                evidence=f"entry_count={entry_count}",
                fix_hint="上層若有樓梯或平台銜接格位，標示單一 data-entry=\"true\"。",
            )

    if unresolved_targets:
        issue(
            issues,
            promoted_level(mode, promotions, "room_target_mismatch"),
            building_id,
            file_name,
            floor_id,
            "ROOM_TARGET_MISMATCH",
            "highlightRoom target is missing in room id list",
            evidence="; ".join(unresolved_targets[:5]),
            fix_hint="同步修正 highlightRoom('id') 與 room-id 對應。",
        )

    unreferenced = sorted([rid for rid in rooms if rid not in referenced_rooms])
    if unreferenced:
        issue(
            issues,
            "info",
            building_id,
            file_name,
            floor_id,
            "UNREFERENCED_ROOM",
            f"{len(unreferenced)} room(s) are not referenced by any plan-cell",
            evidence=", ".join(unreferenced[:8]),
            fix_hint="確認是否為純描述房間，或補齊對應格位。",
        )

    if floor_w and floor_d:
        return {
            "floor_id": floor_id,
            "floor_name": floor_name,
            "width_mm": float(floor_w),
            "depth_mm": float(floor_d),
        }
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check static consistency for building HTML.")
    parser.add_argument("--buildings", type=str, default="A,B,C")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--door-min-mm", type=int, default=700)
    parser.add_argument("--door-max-mm", type=int, default=1400)
    parser.add_argument("--window-min-mm", type=int, default=300)
    parser.add_argument("--window-max-mm", type=int, default=3600)
    parser.add_argument("--mode", type=str, default="draft", choices=["concept", "draft", "ifc"])
    parser.add_argument("--allow-critical", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected = parse_buildings(args.buildings)
    defaults = load_residential_defaults()
    spatial_config = defaults.get("spatial_metadata", {})
    overrides = load_overrides()
    issues: list[dict[str, Any]] = []
    scanned_files: list[str] = []
    floor_count = 0
    cell_count = 0

    for building_id in selected:
        file_name = HTML_FILE_MAP[building_id]
        path = ROOT / file_name
        if not path.exists():
            issue(
                issues,
                "critical",
                building_id,
                file_name,
                "<global>",
                "MISSING_HTML",
                f"Missing canonical HTML file: {file_name}",
                fix_hint="確認檔案存在且名稱正確。",
            )
            continue
        scanned_files.append(file_name)
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        envelopes: list[dict[str, Any]] = []
        for floor in soup.select(".floor-plan"):
            if not floor.select(".plan-cell"):
                continue
            floor_count += 1
            cell_count += len(floor.select(".plan-cell"))
            envelope = check_floor_geometry(
                building_id=building_id,
                file_name=file_name,
                floor=floor,
                issues=issues,
                door_min_mm=args.door_min_mm,
                door_max_mm=args.door_max_mm,
                window_min_mm=args.window_min_mm,
                window_max_mm=args.window_max_mm,
                mode=args.mode,
                spatial_config=spatial_config,
                overrides=overrides,
            )
            if envelope:
                envelopes.append(envelope)
        check_building_footprint(building_id, file_name, envelopes, issues)

    summary = {
        "critical": sum(1 for i in issues if i["level"] == "critical"),
        "warning": sum(1 for i in issues if i["level"] == "warning"),
        "info": sum(1 for i in issues if i["level"] == "info"),
        "scanned_file_count": len(scanned_files),
        "floor_count": floor_count,
        "cell_count": cell_count,
    }
    output = {
        "schema_version": "html-consistency-v1",
        "generated_at": now_iso(),
        "selected_buildings": selected,
        "scanned_files": scanned_files,
        "summary": summary,
        "issues": issues,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"HTML consistency report: {args.output.resolve()}")
    print(f"Critical: {summary['critical']} | Warning: {summary['warning']} | Info: {summary['info']}")

    if summary["critical"] > 0 and not args.allow_critical:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

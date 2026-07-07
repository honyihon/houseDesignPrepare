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
    nearest_declared_side,
    parse_cell_spatial,
    parse_floor_orientation,
    window_issue_level,
)
from lib.standards import load_residential_defaults  # noqa: E402

OUTPUT_PATH = ROOT / "structured" / "expert_review" / "html_consistency.json"
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


def overlap(a: dict[str, float], b: dict[str, float]) -> bool:
    ax1, ay1 = a["x_mm"], a["y_mm"]
    ax2, ay2 = ax1 + a["w_mm"], ay1 + a["h_mm"]
    bx1, by1 = b["x_mm"], b["y_mm"]
    bx2, by2 = bx1 + b["w_mm"], by1 + b["h_mm"]
    return (ax1 < bx2) and (ax2 > bx1) and (ay1 < by2) and (ay2 > by1)


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
) -> None:
    floor_id = normalize_whitespace(floor.get("id", "")) or "<no-id>"
    floor_w = to_float(floor.get("data-floor-width-mm"))
    floor_d = to_float(floor.get("data-floor-depth-mm"))
    spatial_config = spatial_config or {}
    orientation = parse_floor_orientation(floor.attrs)
    direction_config = spatial_config.get("direction", {})
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
            if x < 0 or y < 0 or w <= 0 or h <= 0:
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
            geometry_cells.append(
                {
                    "idx": idx,
                    "label": label,
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
        window_mm = to_int(cell.get("data-window-mm"))
        has_window_attr = cell.has_attr("data-window-mm")
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
            if overlap(geometry_cells[i], geometry_cells[j]):
                issue(
                    issues,
                    "warning",
                    building_id,
                    file_name,
                    floor_id,
                    "CELL_OVERLAP",
                    f"{geometry_cells[i]['label']} overlaps {geometry_cells[j]['label']}",
                    evidence=f"cell-{geometry_cells[i]['idx']} vs cell-{geometry_cells[j]['idx']}",
                    fix_hint="調整 x/y/w/h 避免重疊。",
                )

    if entry_count != 1:
        issue(
            issues,
            "warning",
            building_id,
            file_name,
            floor_id,
            "ENTRY_COUNT",
            f"Expected exactly 1 main entry cell, got {entry_count}",
            evidence=f"entry_count={entry_count}",
            fix_hint="每層僅保留一個 data-entry=\"true\"。",
        )

    if unresolved_targets:
        issue(
            issues,
            "warning",
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
        for floor in soup.select(".floor-plan"):
            if not floor.select(".plan-cell"):
                continue
            floor_count += 1
            cell_count += len(floor.select(".plan-cell"))
            check_floor_geometry(
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
            )

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

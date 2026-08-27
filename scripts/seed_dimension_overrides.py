#!/usr/bin/env python3
"""Seed inputs/dimensions.json from the size text already present in the HTML.

The HTML labels a handful of cells with a real size ("約 5.5m × 6.0m") or an
area in ping ("約 8 坪").  Those are the only non-guessed numbers in the whole
data set, so this script promotes them into the override file and produces
``structured/dimension_todo.md`` listing every cell that still has nothing but
an auto-grid guess behind it.

Usage:
    python scripts/seed_dimension_overrides.py --dry-run
    python scripts/seed_dimension_overrides.py            # creates the file
    python scripts/seed_dimension_overrides.py --force    # refresh, keeping measured entries
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.dimension_overrides import (  # noqa: E402
    DEFAULT_OVERRIDE_PATH,
    PING_TO_SQM,
    PROVENANCE_DECLARED,
    PROVENANCE_MEASURED,
    SCHEMA_VERSION,
    auto_geometry,
    cell_key,
    iter_floor_records,
    load_overrides,
)
from lib.standards import load_residential_defaults  # noqa: E402

PROGRAM_PATH = ROOT / "structured" / "room_program.json"
TODO_PATH = ROOT / "structured" / "dimension_todo.md"

# Rounding slack when testing a derived cell against its floor envelope.
TOLERANCE_MM = 1.0

# No site survey exists anywhere in the repo.  A row of buildings 12 m apart is
# a placeholder so the 3D model has something to draw; it is labelled "assumed"
# so the viewer can say so out loud.
DEFAULT_SITE = {
    "_provenance": "assumed",
    "_note": (
        "無實測基地配置。以下為暫定值：三棟一列。站在前院面對房子時，"
        "右→左為 A、B、C（x 越大越靠右）。量測後請改 _provenance 為 measured。"
    ),
    "C": {"x_mm": 0, "y_mm": 0, "rotation_deg": 0},
    "B": {"x_mm": 12000, "y_mm": 0, "rotation_deg": 0},
    "A": {"x_mm": 24000, "y_mm": 0, "rotation_deg": 0},
}


def derive_from_size_text(
    cell: dict[str, Any], floor_geo: dict[str, Any]
) -> tuple[dict[str, float], str] | tuple[None, str] | None:
    """Turn a cell's declared size text into w/h in mm, if it declares anything.

    Returns ``(dims, note)`` when a usable size was derived, ``(None, reason)``
    when the cell declares a size that cannot be reconciled with where it is
    drawn, and ``None`` when it declares nothing at all.
    """

    metrics = cell.get("size_metrics") or {}
    # Read the pre-override snapshot, never the live geometry: on a rebuild the
    # live values are this script's own previous output, and seeding from those
    # compounds the error a little more on every run.
    geo = auto_geometry(cell)
    auto_w = float(geo.get("w_mm") or 0)
    auto_x = float(geo.get("x_mm") or 0)
    auto_y = float(geo.get("y_mm") or 0)
    floor_w = float(floor_geo.get("width_mm") or 0)
    floor_d = float(floor_geo.get("depth_mm") or 0)

    dimension = metrics.get("dimension_m")
    if isinstance(dimension, dict) and dimension.get("width_m") and dimension.get("depth_m"):
        w_mm = round(float(dimension["width_m"]) * 1000, 1)
        h_mm = round(float(dimension["depth_m"]) * 1000, 1)
        note = f"declared {dimension['width_m']}m × {dimension['depth_m']}m"
        if floor_w and auto_x + w_mm > floor_w + TOLERANCE_MM:
            return None, f"{note} 超出樓層寬 {floor_w:.0f}mm（x={auto_x:.0f}）"
        if floor_d and auto_y + h_mm > floor_d + TOLERANCE_MM:
            return None, f"{note} 超出樓層深 {floor_d:.0f}mm（y={auto_y:.0f}）"
        return {"w_mm": w_mm, "h_mm": h_mm}, note

    ping_values = metrics.get("ping_values") or []
    if ping_values and auto_w > 0:
        target_sqm = float(ping_values[0]) * PING_TO_SQM
        # Keep the auto width and solve for depth.  Width comes from the CSS
        # grid-template-columns split, so it is at least proportional to what
        # was drawn and stays inside the floor.  Depth is the axis the
        # heuristic invents outright (a constant 1100/1300/1700 mm lookup), so
        # that is the one worth replacing.  Scaling both axes instead would
        # keep the bogus 8:1 aspect ratio and push cells outside the building.
        h_mm = round(target_sqm * 1_000_000 / auto_w, 1)
        note = (
            f"declared {ping_values[0]} 坪 = {target_sqm:.1f} m²; "
            f"width kept from grid ({auto_w:.0f}mm), depth solved"
        )
        if floor_d and auto_y + h_mm > floor_d + TOLERANCE_MM:
            # The declared area does not fit in the space the cell occupies.
            # Manufacturing a value that pokes out of the building would be a
            # worse guess than the one already there, so hand it to the
            # surveyor instead.
            return None, (
                f"declared {ping_values[0]} 坪 需深 {h_mm:.0f}mm，"
                f"但樓層深僅 {floor_d:.0f}mm（y={auto_y:.0f}）— 標示面積與繪製位置衝突"
            )
        return {"w_mm": round(auto_w, 1), "h_mm": h_mm}, note

    return None


def build(program: dict[str, Any], existing) -> tuple[dict[str, Any], list[dict[str, Any]], int, int]:
    defaults = load_residential_defaults()
    storey = float(defaults.get("architect_metrics", {}).get("room_height_mm", 3000))

    buildings: dict[str, Any] = {}
    todo: list[dict[str, Any]] = []
    seeded = 0
    conflicts = 0

    for building, floor in iter_floor_records(program):
        bid = building.get("id", "")
        fid = floor.get("id", "")
        fgeo = auto_geometry(floor)

        prior_floor = existing.floor(bid, fid)
        floor_node: dict[str, Any] = {
            "width_mm": prior_floor.get("width_mm", fgeo.get("width_mm")),
            "depth_mm": prior_floor.get("depth_mm", fgeo.get("depth_mm")),
            "north_deg": prior_floor.get("north_deg", fgeo.get("north_deg", 0)),
            "storey_height_mm": prior_floor.get("storey_height_mm", storey),
            "_provenance": prior_floor.get("_provenance", "auto"),
            "_title": floor.get("title", ""),
            "cells": {},
        }

        for cell in floor.get("plan_cells", []):
            key = cell_key(cell)
            prior = existing.cell(bid, fid, key)
            if prior.get("_provenance") == PROVENANCE_MEASURED:
                # Never clobber a real measurement.
                floor_node["cells"][key] = prior
                seeded += 1
                continue

            derived = derive_from_size_text(cell, fgeo)
            geo = auto_geometry(cell)
            if derived is None or derived[0] is None:
                reason = derived[1] if derived else ""
                if reason:
                    conflicts += 1
                todo.append(
                    {
                        "building": bid,
                        "floor": fid,
                        "floor_title": floor.get("title", ""),
                        "key": key,
                        "name": cell.get("name", ""),
                        "auto_w_mm": geo.get("w_mm"),
                        "auto_h_mm": geo.get("h_mm"),
                        "role": (cell.get("spatial") or {}).get("room_role", ""),
                        "conflict": reason,
                    }
                )
                continue

            dims, note = derived
            floor_node["cells"][key] = {
                "x_mm": geo.get("x_mm", 0),
                "y_mm": geo.get("y_mm", 0),
                **dims,
                "_provenance": PROVENANCE_DECLARED,
                "_name": cell.get("name", ""),
                "_note": note,
            }
            seeded += 1

        buildings.setdefault(bid, {"floors": {}})["floors"][fid] = floor_node


    site = existing.site() or DEFAULT_SITE
    doc = {
        "schema": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "_readme": (
            "尺寸覆寫檔。pipeline 讀這裡的值優先於 HTML 的 auto-grid 推導值。"
            "量到真實尺寸後填入 w_mm/h_mm（必要時連 x_mm/y_mm），並把該格的 "
            "_provenance 改成 \"measured\"；標成 measured 的項目不會被本腳本覆蓋。"
        ),
        "default_storey_height_mm": storey,
        "site": site,
        "buildings": buildings,
    }
    return doc, todo, seeded, conflicts


def write_todo(todo: list[dict[str, Any]], seeded: int, total: int, conflicts: int) -> None:
    lines = [
        "# 待補實測尺寸清單",
        "",
        f"- Generated: `{datetime.now(timezone.utc).isoformat()}`",
        f"- 已有尺寸依據: **{seeded}** / {total} 格",
        f"- 仍為 auto-grid 推導（純猜測）: **{len(todo)}** 格",
        f"- 其中「標示面積與繪製位置衝突」: **{conflicts}** 格（下方標 ⚠️）",
        "",
        "> auto 欄位是 `scripts/annotate_html_geometry.py` 由 CSS class 推出的猜測值",
        "> （列深度查表 1100/1200/1300/1700mm、樓層寬固定 11000mm），不是實測值。",
        "> 量到真值後填入 `inputs/dimensions.json` 並把 `_provenance` 改成 `measured`。",
        "",
    ]
    if conflicts:
        lines += [
            "⚠️ 標記的格子在 HTML 上已寫有坪數或尺寸，但那個面積放不進它被畫到的位置。",
            "這代表**文字標示與平面配置其中一個是錯的**，不能靠推算解決，請優先實測這幾格。",
            "",
        ]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in todo:
        grouped.setdefault(f"{item['building']} / {item['floor']} {item['floor_title']}", []).append(item)

    for header, items in grouped.items():
        lines.append(f"## {header}")
        lines.append("")
        lines.append("| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |")
        lines.append("|---|---|---:|---:|---|---|---|---|")
        for item in items:
            conflict = item.get("conflict") or ""
            mark = f"⚠️ {conflict}" if conflict else ""
            lines.append(
                f"| `{item['key']}` | {item['name']} | {item['auto_w_mm']} | {item['auto_h_mm']} "
                f"| {item['role']} |  |  | {mark} |"
            )
        lines.append("")

    TODO_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    parser.add_argument("--force", action="store_true", help="rewrite an existing override file")
    parser.add_argument("--output", type=Path, default=DEFAULT_OVERRIDE_PATH)
    args = parser.parse_args()

    if not PROGRAM_PATH.exists():
        raise SystemExit(f"Missing {PROGRAM_PATH}. Run scripts/build_room_program.py first.")
    program = json.loads(PROGRAM_PATH.read_text(encoding="utf-8"))

    existing = load_overrides(args.output)
    doc, todo, seeded, conflicts = build(program, existing)
    total = seeded + len(todo)

    print(f"Cells with a declared size: {seeded}")
    print(f"Cells still auto-derived:   {len(todo)}  ({round(100.0 * len(todo) / total, 1) if total else 0}%)")
    if conflicts:
        print(f"  of which declared-vs-drawn conflicts needing a tape measure: {conflicts}")

    if args.dry_run:
        print("(--dry-run: nothing written)")
        return 0

    if args.output.exists() and not args.force:
        print(f"{args.output} already exists; pass --force to rewrite (measured entries are preserved).")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {args.output}")

    write_todo(todo, seeded, total, conflicts)
    print(f"Wrote {TODO_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

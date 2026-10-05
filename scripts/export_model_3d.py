#!/usr/bin/env python3
"""Export a single-file, offline 3D massing viewer for the A/B/C compound.

Reads ``structured/room_program.json`` (already carrying the dimension-override
layer from ``scripts/lib/dimension_overrides.py``) and writes
``structured/candidates/model3d.html`` — one self-contained file that opens by
double-clicking, with no web server and no network.

Read-only massing, not a modelling tool
---------------------------------------
Every box in the output is derived from ``plan_cells[].geometry_mm``. Nothing
here can be edited and saved back; ``structured/room_program.json`` stays the
single source of truth. See ``Docs/superpowers/plans/`` for how this sits
against the "no BIM/CAD/3D stack" non-goal.

Honesty is the point
--------------------
About four fifths of the geometry is still auto-derived from CSS classes rather
than measured (see ``scripts/annotate_html_geometry.py`` for how those numbers
are manufactured). The viewer therefore ships a provenance colour mode that
renders measured / declared / auto volumes differently, so the amount of
guesswork is visible at a glance instead of hidden behind a confident-looking
render.

Why three.js is inlined
-----------------------
``assets/vendor/three/three.min.js`` is a UMD classic script, embedded directly
into a ``<script>`` block. Chrome blocks ES-module scripts over ``file://`` as
cross-origin, which would leave the viewer blank for exactly the audience it is
for. See ``assets/vendor/three/VERSION.txt``.
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from export_top1_svgs import (  # noqa: E402
    default_drawing_style,
    drawing_profile,
    normalize,
    room_kind,
)
from lib.dimension_overrides import (  # noqa: E402
    PING_TO_SQM,
    PROVENANCE_AUTO,
    PROVENANCE_LEVELS,
    load_overrides,
    summarize_provenance,
)
from lib.furniture_layout import attach_furniture_layout  # noqa: E402
from lib.html_parametric_compare import (  # noqa: E402
    build_compare,
    find_cell_overlaps,
    format_compare_panel,
)
from lib.standards import load_residential_defaults, repo_relative  # noqa: E402

from house_design.physical_items import PHYSICAL_ITEMS_PATH  # noqa: E402
from house_design.rendering import encode_html_json  # noqa: E402

PROGRAM_FILE = ROOT / "structured" / "room_program.json"
PLAN_FILE = ROOT / "structured" / "parametric" / "plan.json"
THREE_FILE = ROOT / "assets" / "vendor" / "three" / "three.min.js"
THREE_VERSION_FILE = ROOT / "assets" / "vendor" / "three" / "VERSION.txt"
OUTPUT_HTML = ROOT / "structured" / "candidates" / "model3d.html"
FURNITURE_FILE = ROOT / "inputs" / "furniture-layout.json"
PHYSICAL_ITEMS_FILE = PHYSICAL_ITEMS_PATH

SCHEMA_VERSION = "house-model3d-v1"

# Outdoor cells (garage, balcony, terrace) get a slab rather than a volume:
# drawing them full storey height would wall off the very spaces that read as
# open in the plan.
OUTDOOR_SLAB_MM = 200.0

# Fallbacks only — the real values come from residential_defaults_tw.json.
FALLBACK_STOREY_MM = 3000.0
FALLBACK_DOOR_HEIGHT_MM = 2100.0
FALLBACK_WINDOW_SILL_MM = 900.0
FALLBACK_WINDOW_HEIGHT_MM = 1200.0

# Plan-space y grows downward on screen. With north_deg == 0 that maps to
# "up on the plan is north", i.e. north is -Z in the scene.
FRONT_SIDE_TO_FACE = {
    "top": "north",
    "bottom": "south",
    "left": "west",
    "right": "east",
}

KIND_LABELS = {
    "entry": "玄關",
    "living": "客廳",
    "dining": "餐廳",
    "bedroom": "臥室",
    "bath": "衛浴",
    "kitchen": "廚房",
    "service": "設備/儲藏",
    "stair": "樓梯",
    "outdoor": "戶外",
    "other": "其他",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _box_mm(geo: dict[str, Any]) -> dict[str, float]:
    return {k: round(as_float(geo.get(k)), 1) for k in ("x_mm", "y_mm", "w_mm", "h_mm")}


def _is_roof_floor(floor_id: str, label: str) -> bool:
    token = f"{floor_id} {label}".upper()
    return "FLOOR-4" in token or "FLOOR-RF" in token or "RF" in token or "屋頂" in label


def declared_area_sqm(cell: dict[str, Any]) -> float | None:
    """Area as written on the HTML label, in m², if it states one."""

    metrics = cell.get("size_metrics") or {}
    dimension_sqm = metrics.get("dimension_sqm")
    if isinstance(dimension_sqm, (int, float)) and dimension_sqm > 0:
        return round(float(dimension_sqm), 2)
    for value in metrics.get("sqm_from_ping_values") or []:
        if isinstance(value, (int, float)) and value > 0:
            return round(float(value), 2)
    return None


def opening_face(cell: dict[str, Any], front_side: str) -> tuple[str, str]:
    """Which wall the door/window patch goes on, and how sure we are.

    ``spatial.facing`` is the right answer but is currently ``unknown`` for
    every cell — the HTML records no opening orientation at all. Falling back to
    the floor's front side keeps the patches consistent instead of arbitrary,
    and the returned source string lets the viewer label them as inferred.
    """

    facing = str((cell.get("spatial") or {}).get("facing", "") or "").lower()
    if facing in {"north", "south", "east", "west"}:
        return facing, "cell"
    face = FRONT_SIDE_TO_FACE.get(front_side)
    if face:
        return face, "floor-front"
    return "south", "assumed"


def build_cell(
    building_id: str,
    floor_id: str,
    cell: dict[str, Any],
    fills: dict[str, str],
    front_side: str,
) -> dict[str, Any]:
    geo = cell.get("geometry_mm") or {}
    auto = cell.get("geometry_auto_mm") or {}
    spatial = cell.get("spatial") or {}
    openings = cell.get("openings_mm") or {}

    name = normalize(cell.get("name", "")) or "未命名"
    kind = room_kind(name)
    declared = _box_mm(geo)
    auto_box = _box_mm(auto)
    if auto_box["w_mm"] <= 0 and auto_box["h_mm"] <= 0:
        auto_box = dict(declared)
    w_mm = declared["w_mm"]
    h_mm = declared["h_mm"]
    area_sqm = round(w_mm * h_mm / 1_000_000.0, 2)
    key = str(cell.get("override_key") or f"cell-{cell.get('order', 0)}")
    face, face_source = opening_face(cell, front_side)

    return {
        "id": f"{building_id}:{floor_id}:{key}",
        "key": key,
        "order": int(as_float(cell.get("order"), 0)),
        "name": name,
        "icon": normalize(cell.get("icon", "")),
        "kind": kind,
        "color": fills.get(kind) or fills.get("other") or "#ffffff",
        "size_text": normalize(cell.get("size_text", "")),
        "x_mm": declared["x_mm"],
        "y_mm": declared["y_mm"],
        "w_mm": round(w_mm, 1),
        "h_mm": round(h_mm, 1),
        "declared_mm": declared,
        "auto_mm": auto_box,
        "provenance": str(cell.get("geometry_provenance") or PROVENANCE_AUTO),
        "is_outdoor": bool(spatial.get("is_outdoor_like")),
        "is_entry": bool(cell.get("is_entry")),
        "room_role": str(spatial.get("room_role") or "unknown"),
        "zone": str(spatial.get("zone") or "unknown"),
        "facing": str(spatial.get("facing") or "unknown"),
        "area_sqm": area_sqm,
        "area_ping": round(area_sqm / PING_TO_SQM, 2) if area_sqm else 0.0,
        "declared_sqm": declared_area_sqm(cell),
        "door_mm": round(as_float(openings.get("door_mm")), 1),
        "window_mm": round(as_float(openings.get("window_mm")), 1),
        "opening_face": face,
        "opening_face_source": face_source,
        "badges": [normalize(v) for v in cell.get("badges", []) if normalize(v)][:4],
        "room_uid": str(cell.get("target_room_uid") or ""),
    }


def build_buildings(
    program: dict[str, Any],
    overrides: Any,
    fills: dict[str, str],
    default_storey_mm: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    buildings: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    overlaps_auto: list[dict[str, Any]] = []
    overlaps_declared: list[dict[str, Any]] = []

    for building in program.get("buildings", []):
        building_id = str(building.get("id", ""))
        floors_out: list[dict[str, Any]] = []
        base_mm = 0.0

        # Only record_type == "floor" carries geometry; the overview / checklist
        # tabs are parsed as "section" records and have no plan cells.
        floor_records = [f for f in building.get("floors", []) if f.get("record_type") == "floor"]
        for index, floor in enumerate(floor_records):
            floor_id = str(floor.get("id", ""))
            geo = floor.get("geometry_mm") or {}
            auto_geo = floor.get("geometry_auto_mm") or geo
            height_mm = as_float(floor.get("storey_height_mm"), default_storey_mm) or default_storey_mm
            front_side = str((floor.get("orientation") or {}).get("front_side", "") or "unknown")
            raw_label = normalize(floor.get("tab_label", "")) or normalize(floor.get("title", "")) or floor_id
            is_roof = _is_roof_floor(floor_id, raw_label)
            label = raw_label
            if is_roof and "RF" not in raw_label.upper() and "屋頂" not in raw_label:
                label = f"{raw_label}（屋頂／RF，非 4F）"
            cells = [
                build_cell(building_id, floor_id, cell, fills, front_side)
                for cell in floor.get("plan_cells", [])
            ]
            overlaps_auto.extend(find_cell_overlaps(cells, "auto_mm", building_id, floor_id))
            overlaps_declared.extend(find_cell_overlaps(cells, "declared_mm", building_id, floor_id))
            floors_out.append(
                {
                    "id": floor_id,
                    "index": index,
                    "label": label,
                    "title": normalize(floor.get("title", "")),
                    "is_roof": is_roof,
                    "base_mm": round(base_mm, 1),
                    "height_mm": round(height_mm, 1),
                    "width_mm": round(as_float(geo.get("width_mm")), 1),
                    "depth_mm": round(as_float(geo.get("depth_mm")), 1),
                    "auto_width_mm": round(as_float(auto_geo.get("width_mm"), as_float(geo.get("width_mm"))), 1),
                    "auto_depth_mm": round(as_float(auto_geo.get("depth_mm"), as_float(geo.get("depth_mm"))), 1),
                    "north_deg": round(as_float(geo.get("north_deg")), 1),
                    "front_side": front_side,
                    "provenance": str(floor.get("geometry_provenance") or PROVENANCE_AUTO),
                    "cells": cells,
                }
            )
            base_mm += height_mm

        if not floors_out:
            skipped.append(
                {
                    "building": building_id,
                    "source_file": str(building.get("source_file", "")),
                    "reason": "沒有任何 plan-cell 幾何，無法建立量體",
                }
            )
            continue

        placement = overrides.site_placement(building_id)
        buildings.append(
            {
                "id": building_id,
                "title": normalize(building.get("document_title", "")),
                "source_file": str(building.get("source_file", "")),
                "placement": {
                    "x_mm": as_float(placement.get("x_mm")),
                    "y_mm": as_float(placement.get("y_mm")),
                    "rotation_deg": as_float(placement.get("rotation_deg")),
                    "declared": bool(placement),
                },
                "floors": floors_out,
            }
        )

    return buildings, skipped, overlaps_auto, overlaps_declared


def build_payload(
    program: dict[str, Any],
    overrides: Any,
    style: str,
    plan: dict[str, Any] | None = None,
    furniture_path: Path = FURNITURE_FILE,
    physical_items_path: Path = PHYSICAL_ITEMS_FILE,
) -> dict[str, Any]:
    defaults = load_residential_defaults()
    metrics = defaults.get("architect_metrics", {}) if isinstance(defaults.get("architect_metrics"), dict) else {}
    geometry = defaults.get("geometry", {}) if isinstance(defaults.get("geometry"), dict) else {}
    profile = drawing_profile(style)
    drawing = defaults.get("drawing", {}) if isinstance(defaults.get("drawing"), dict) else {}
    # Start from the SVG room fills so the room-kind keys stay in lockstep with
    # the drawings, then let the screen palette win: the print pastels are all
    # within a few percent of white and shade to identical grey on a 3D volume.
    fills = {str(k): str(v) for k, v in (profile.get("room_fills") or {}).items()}
    screen = drawing.get("model3d_room_colors")
    if isinstance(screen, dict):
        fills.update({str(k): str(v) for k, v in screen.items() if not str(k).startswith("_")})

    default_storey_mm = as_float(metrics.get("room_height_mm"), FALLBACK_STOREY_MM) or FALLBACK_STOREY_MM
    buildings, skipped, overlaps_auto, overlaps_declared = build_buildings(
        program, overrides, fills, default_storey_mm
    )

    site = overrides.site()
    provenance = summarize_provenance(program)
    cells_summary = provenance.get("cells", {}) if isinstance(provenance.get("cells"), dict) else {}
    compare = build_compare(program, plan)
    furniture = attach_furniture_layout(buildings, furniture_path, physical_items_path)

    return {
        "schema": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "source": {
            "program": repo_relative(PROGRAM_FILE),
            "overrides": repo_relative(overrides.path),
            "overrides_loaded": bool(overrides.loaded),
            "three": repo_relative(THREE_FILE),
            "drawing_style": style,
            "furniture": repo_relative(furniture_path),
            "physical_items": repo_relative(physical_items_path),
        },
        "standards": {
            "storey_height_mm": default_storey_mm,
            "outdoor_slab_mm": OUTDOOR_SLAB_MM,
            "door_height_mm": as_float(geometry.get("door_height_mm"), FALLBACK_DOOR_HEIGHT_MM),
            "window_sill_height_mm": as_float(metrics.get("window_sill_height_mm"), FALLBACK_WINDOW_SILL_MM),
            "window_height_mm": as_float(metrics.get("window_height_mm"), FALLBACK_WINDOW_HEIGHT_MM),
        },
        "site": {
            "provenance": str(site.get("_provenance") or "assumed"),
            "note": normalize(str(site.get("_note") or "")),
        },
        "provenance": {
            "cells": {level: int(cells_summary.get(level, 0)) for level in PROVENANCE_LEVELS},
            "total": int(cells_summary.get("total", 0)),
            "auto_pct": float(cells_summary.get("auto_pct", 0.0)),
        },
        "palette": fills,
        "kind_labels": KIND_LABELS,
        "buildings": buildings,
        "skipped": skipped,
        "overlaps": {"auto": overlaps_auto, "declared": overlaps_declared},
        "compare": compare,
        "furniture": furniture,
        "geom_source_default": "auto",
    }


def three_source() -> tuple[str, dict[str, Any]]:
    if not THREE_FILE.exists():
        raise SystemExit(
            f"three.js not vendored: {repo_relative(THREE_FILE)} is missing.\n"
            "See assets/vendor/three/VERSION.txt for the exact build to fetch."
        )
    source = THREE_FILE.read_text(encoding="utf-8")
    # Inlining is only safe while the bundle contains no closing script tag.
    # A future three.js upgrade that breaks this should fail loudly here rather
    # than silently produce a truncated viewer.
    if "</script" in source.lower():
        raise SystemExit(
            f"{repo_relative(THREE_FILE)} contains a closing script tag and cannot be inlined verbatim."
        )
    return source, {"file": repo_relative(THREE_FILE), "bytes": len(source.encode("utf-8"))}


# The template is a plain string with placeholders rather than an f-string: the
# JavaScript below is mostly braces, and doubling every one of them to survive
# f-string interpolation is a reliable way to introduce a typo nobody can see.
TEMPLATE_FILE = SCRIPT_DIR / "templates/model3d.html"
HTML_TEMPLATE = TEMPLATE_FILE.read_text(encoding="utf-8")


def render_html(payload: dict[str, Any], three_js: str) -> str:
    compare_html = format_compare_panel(payload.get("compare") or {})
    return (
        HTML_TEMPLATE.replace("__THREE_JS__", three_js)
        .replace("__MODEL_DATA__", encode_html_json(payload))
        .replace("__COMPARE_HTML__", compare_html)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", type=Path, default=PROGRAM_FILE)
    parser.add_argument("--plan", type=Path, default=PLAN_FILE)
    parser.add_argument("--output", type=Path, default=OUTPUT_HTML)
    parser.add_argument("--style", type=str, default="", help="drawing style whose room_fills the 3D reuses")
    parser.add_argument(
        "--furniture",
        type=Path,
        default=FURNITURE_FILE,
        help="editable furniture/equipment draft mapped to HTML room ids",
    )
    parser.add_argument(
        "--physical-items",
        type=Path,
        default=PHYSICAL_ITEMS_FILE,
        help="owner physical-item register supplying shared measured or planning dimensions",
    )
    args = parser.parse_args()

    if not args.program.exists():
        raise SystemExit(f"Missing room program: {args.program}. Run scripts/build_room_program.py first.")

    program = json.loads(args.program.read_text(encoding="utf-8"))
    plan = None
    if args.plan.exists():
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    overrides = load_overrides()
    style = args.style or default_drawing_style()
    payload = build_payload(program, overrides, style, plan, args.furniture, args.physical_items)
    three_js, three_meta = three_source()
    payload["source"]["three_bytes"] = three_meta["bytes"]
    if plan:
        payload["source"]["plan"] = repo_relative(args.plan)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_html(payload, three_js), encoding="utf-8")

    cells = payload["provenance"]["cells"]
    floor_count = sum(len(b["floors"]) for b in payload["buildings"])
    print(f"3D massing viewer: {args.output}")
    print(f"  buildings={len(payload['buildings'])} floors={floor_count} cells={payload['provenance']['total']}")
    print(
        "  geometry provenance: "
        f"measured={cells['measured']} declared={cells['declared']} auto={cells['auto']} "
        f"({payload['provenance']['auto_pct']}% still auto-derived guesses)"
    )
    if payload["site"]["provenance"] != "measured":
        print("  site placement is assumed, not surveyed — banner shown in the viewer")
    n_overlap = len(payload.get("overlaps", {}).get("declared") or [])
    print(f"  declared-geometry overlaps: {n_overlap}")
    furniture = payload.get("furniture") or {}
    if furniture.get("available"):
        print(f"  furniture draft: {furniture['items']} items in {furniture['rooms']} HTML rooms")
    else:
        print("  furniture draft: unavailable")
    if payload.get("compare", {}).get("available"):
        print(f"  parametric compare: {payload['compare']['variant']['label']}")
    for item in payload["skipped"]:
        print(f"  skipped {item['building']}: {item['reason']}")


if __name__ == "__main__":
    main()

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
from house_design.rendering import encode_html_json  # noqa: E402
from lib.dimension_overrides import (  # noqa: E402
    PING_TO_SQM,
    PROVENANCE_AUTO,
    PROVENANCE_LEVELS,
    load_overrides,
    summarize_provenance,
)
from lib.standards import load_residential_defaults, repo_relative  # noqa: E402

PROGRAM_FILE = ROOT / "structured" / "room_program.json"
THREE_FILE = ROOT / "assets" / "vendor" / "three" / "three.min.js"
THREE_VERSION_FILE = ROOT / "assets" / "vendor" / "three" / "VERSION.txt"
OUTPUT_HTML = ROOT / "structured" / "candidates" / "model3d.html"

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
    w_mm = as_float(geo.get("w_mm"))
    h_mm = as_float(geo.get("h_mm"))
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
        "x_mm": round(as_float(geo.get("x_mm")), 1),
        "y_mm": round(as_float(geo.get("y_mm")), 1),
        "w_mm": round(w_mm, 1),
        "h_mm": round(h_mm, 1),
        "auto_mm": {k: round(as_float(auto.get(k)), 1) for k in ("x_mm", "y_mm", "w_mm", "h_mm")},
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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    buildings: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

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
            height_mm = as_float(floor.get("storey_height_mm"), default_storey_mm) or default_storey_mm
            front_side = str((floor.get("orientation") or {}).get("front_side", "") or "unknown")
            cells = [
                build_cell(building_id, floor_id, cell, fills, front_side)
                for cell in floor.get("plan_cells", [])
            ]
            floors_out.append(
                {
                    "id": floor_id,
                    "index": index,
                    "label": normalize(floor.get("tab_label", "")) or normalize(floor.get("title", "")) or floor_id,
                    "title": normalize(floor.get("title", "")),
                    "base_mm": round(base_mm, 1),
                    "height_mm": round(height_mm, 1),
                    "width_mm": round(as_float(geo.get("width_mm")), 1),
                    "depth_mm": round(as_float(geo.get("depth_mm")), 1),
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

    return buildings, skipped


def build_payload(program: dict[str, Any], overrides: Any, style: str) -> dict[str, Any]:
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
    buildings, skipped = build_buildings(program, overrides, fills, default_storey_mm)

    site = overrides.site()
    provenance = summarize_provenance(program)
    cells_summary = provenance.get("cells", {}) if isinstance(provenance.get("cells"), dict) else {}

    return {
        "schema": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "source": {
            "program": repo_relative(PROGRAM_FILE),
            "overrides": repo_relative(overrides.path),
            "overrides_loaded": bool(overrides.loaded),
            "three": repo_relative(THREE_FILE),
            "drawing_style": style,
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
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>三棟量體 3D 檢視器</title>
<style>
  :root {
    --bg0: #0b1020; --bg1: #101c2f; --card: #131f36; --line: #2a3b5a;
    --text: #e8edf7; --muted: #9fb0cd; --accent: #19c3c5; --warn: #f8b84e;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0; color: var(--text); overflow: hidden;
    font-family: "Segoe UI", "Microsoft JhengHei", sans-serif;
    background: linear-gradient(145deg, var(--bg0), var(--bg1));
  }
  #app { display: grid; grid-template-columns: 330px minmax(0, 1fr); height: 100vh; }
  #panel { overflow-y: auto; padding: 16px; border-right: 1px solid var(--line); background: rgba(9, 14, 26, 0.72); }
  #panel h1 { font-size: 18px; margin: 0 0 2px; }
  #panel h2 { font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin: 18px 0 8px; }
  .sub { margin: 0; font-size: 12px; color: var(--muted); }
  .banner { margin-top: 12px; padding: 9px 11px; border-radius: 8px; font-size: 12px; line-height: 1.55; }
  .banner.warn { background: rgba(248, 184, 78, .12); border: 1px solid rgba(248, 184, 78, .42); color: #ffdda1; }
  .seg { display: flex; gap: 6px; }
  .seg button {
    flex: 1; padding: 7px 6px; font-size: 12px; cursor: pointer; color: var(--muted);
    background: var(--card); border: 1px solid var(--line); border-radius: 7px;
    font-family: inherit;
  }
  .seg button.on { color: #08131f; background: var(--accent); border-color: var(--accent); font-weight: 700; }
  .seg button:focus-visible, #panel input:focus-visible, .grp-toggle:focus-visible {
    outline: 3px solid var(--accent); outline-offset: 2px;
  }
  #legend { display: flex; flex-wrap: wrap; gap: 5px 10px; margin-top: 10px; font-size: 11px; color: var(--muted); }
  #legend span { display: inline-flex; align-items: center; gap: 5px; }
  #legend i { width: 11px; height: 11px; border-radius: 3px; border: 1px solid rgba(255,255,255,.28); }
  .grp { margin-bottom: 10px; }
  .grp-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 4px; }
  .grp-head strong { font-size: 13px; }
  .grp-toggle {
    font-size: 11px; padding: 2px 8px; cursor: pointer; color: var(--muted);
    background: transparent; border: 1px solid var(--line); border-radius: 999px; font-family: inherit;
  }
  label.row { display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 3px 0; cursor: pointer; }
  label.row .tag { margin-left: auto; font-size: 10px; color: var(--muted); }
  input[type="range"] { width: 100%; }
  .hint { font-size: 11px; color: var(--muted); margin: 4px 0 10px; }
  #info { font-size: 12px; line-height: 1.65; }
  #info .k { color: var(--muted); }
  #info .name { font-size: 15px; font-weight: 700; display: block; margin-bottom: 6px; }
  #info dl { display: grid; grid-template-columns: auto 1fr; gap: 3px 10px; margin: 0; }
  #info dt { color: var(--muted); }
  #info dd { margin: 0; }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
  .pill.measured { background: #16a34a; color: #04140a; }
  .pill.declared { background: #f59e0b; color: #23150b; }
  .pill.auto { background: #64748b; color: #0b1020; }
  .muted { color: var(--muted); }
  #stage { position: relative; }
  canvas { display: block; width: 100%; height: 100%; touch-action: none; cursor: grab; }
  canvas:active { cursor: grabbing; }
  #hud {
    position: absolute; left: 14px; top: 12px; font-size: 11px; color: var(--muted);
    background: rgba(9, 14, 26, .68); border: 1px solid var(--line); border-radius: 8px;
    padding: 7px 11px; line-height: 1.7; pointer-events: none;
  }
  #compass {
    position: absolute; right: 16px; top: 14px; width: 54px; height: 54px; border-radius: 50%;
    border: 1px solid var(--line); background: rgba(9, 14, 26, .68); color: var(--muted);
    display: grid; place-items: center; font-size: 11px; text-align: center; line-height: 1.25;
  }
  #compass b { color: var(--text); font-size: 13px; }
  @media (max-width: 860px) {
    #app { grid-template-columns: 1fr; grid-template-rows: minmax(0, 44vh) minmax(0, 1fr); }
    #panel { border-right: 0; border-bottom: 1px solid var(--line); }
  }
</style>
</head>
<body>
<div id="app">
  <aside id="panel">
    <h1>三棟量體 3D 檢視器</h1>
    <p class="sub" id="subtitle"></p>
    <div class="banner warn" id="honesty"></div>

    <h2>顯示模式</h2>
    <div class="seg" role="group" aria-label="顯示模式">
      <button type="button" data-mode="kind" class="on">用途配色</button>
      <button type="button" data-mode="provenance">尺寸來源</button>
    </div>
    <div id="legend"></div>

    <h2>樓層</h2>
    <div id="floors"></div>

    <h2>剖切與圖層</h2>
    <input type="range" id="cut" min="0" max="1000" value="1000" aria-label="剖切高度" />
    <div class="hint" id="cut-label"></div>
    <label class="row"><input type="checkbox" id="openings" /> 顯示門窗示意</label>
    <label class="row"><input type="checkbox" id="grid" checked /> 顯示基地格線</label>
    <button type="button" class="grp-toggle" id="reset-view" style="margin-top:10px">重設視角</button>

    <h2>選取</h2>
    <div id="info" class="muted">點選任一量體查看資訊。</div>
  </aside>
  <main id="stage">
    <canvas id="canvas"></canvas>
    <div id="hud">拖曳旋轉 · 滾輪縮放 · 右鍵/Shift 拖曳平移 · 點選看資訊</div>
    <div id="compass"><span><b>N</b><br />方位為推定</span></div>
  </main>
</div>

<script>__THREE_JS__</script>
<script>
(function () {
  "use strict";
  var DATA = __MODEL_DATA__;
  var MM = 0.001;

  var PROV_STYLE = {
    measured: { color: 0x16a34a, opacity: 1.00, edge: 0x22c55e },
    declared: { color: 0xf59e0b, opacity: 0.48, edge: 0xfbbf24 },
    auto:     { color: 0x64748b, opacity: 0.07, edge: 0x8fa3bf }
  };
  var PROV_LABEL = { measured: "實測", declared: "標示推算", auto: "CSS 推導（猜測）" };

  // ---------- scene ----------
  var canvas = document.getElementById("canvas");
  var stage = document.getElementById("stage");
  var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.localClippingEnabled = true;
  renderer.setClearColor(0x0b1020, 1);

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(45, 1, 0.1, 2000);

  scene.add(new THREE.HemisphereLight(0xdce8ff, 0x1b2438, 1.05));
  var sun = new THREE.DirectionalLight(0xffffff, 0.85);
  sun.position.set(28, 46, 20);
  scene.add(sun);
  var fill = new THREE.DirectionalLight(0xbcd4ff, 0.35);
  fill.position.set(-30, 18, -24);
  scene.add(fill);

  var grid = new THREE.GridHelper(80, 40, 0x33507a, 0x1d2c46);
  grid.position.y = -0.01;
  scene.add(grid);

  var clipPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 1e6);

  var boxGeom = new THREE.BoxGeometry(1, 1, 1);
  var edgeGeom = new THREE.EdgesGeometry(boxGeom);
  var planeGeom = new THREE.PlaneGeometry(1, 1);

  var materials = {};
  function solidMaterial(hex, opacity) {
    var key = "s" + hex + "_" + opacity;
    if (!materials[key]) {
      materials[key] = new THREE.MeshLambertMaterial({
        color: hex,
        transparent: opacity < 1,
        opacity: opacity,
        depthWrite: opacity > 0.6,
        side: THREE.DoubleSide,
        clippingPlanes: [clipPlane]
      });
    }
    return materials[key];
  }
  function lineMaterial(hex, opacity) {
    var key = "l" + hex + "_" + opacity;
    if (!materials[key]) {
      materials[key] = new THREE.LineBasicMaterial({
        color: hex,
        transparent: true,
        opacity: opacity,
        clippingPlanes: [clipPlane]
      });
    }
    return materials[key];
  }

  // ---------- build ----------
  var root = new THREE.Group();
  scene.add(root);

  var floorGroups = [];   // one per building x floor, for the toggles
  var pickables = [];     // meshes the raycaster may hit
  // Opening patches stay parented to their building group so they inherit its
  // placement transform; the toggle flips visibility over this flat list
  // instead, since re-parenting them into one group would drop that transform.
  var openingMeshes = [];
  var bounds = new THREE.Box3();

  DATA.buildings.forEach(function (building) {
    var bGroup = new THREE.Group();
    var place = building.placement || {};
    bGroup.position.set((place.x_mm || 0) * MM, 0, (place.y_mm || 0) * MM);
    bGroup.rotation.y = -(place.rotation_deg || 0) * Math.PI / 180;
    root.add(bGroup);

    building.floors.forEach(function (floor) {
      var fGroup = new THREE.Group();
      bGroup.add(fGroup);
      floorGroups.push({ building: building, floor: floor, group: fGroup });

      floor.cells.forEach(function (cell) {
        var w = cell.w_mm * MM;
        var d = cell.h_mm * MM;
        if (w <= 0 || d <= 0) { return; }
        var h = (cell.is_outdoor ? DATA.standards.outdoor_slab_mm : floor.height_mm) * MM;
        var cx = (cell.x_mm * MM) + w / 2;
        var cz = (cell.y_mm * MM) + d / 2;
        var cy = (floor.base_mm * MM) + h / 2;

        var mesh = new THREE.Mesh(boxGeom, solidMaterial(0xffffff, 1));
        mesh.scale.set(w, h, d);
        mesh.position.set(cx, cy, cz);
        mesh.userData = { cell: cell, floor: floor, building: building };
        fGroup.add(mesh);
        pickables.push(mesh);

        var edges = new THREE.LineSegments(edgeGeom, lineMaterial(0xffffff, 1));
        edges.scale.copy(mesh.scale);
        edges.position.copy(mesh.position);
        fGroup.add(edges);
        mesh.userData.edges = edges;

        addOpenings(cell, floor, bGroup, w, d, cx, cz);
      });
    });
  });

  function addOpenings(cell, floor, bGroup, w, d, cx, cz) {
    var base = floor.base_mm * MM;
    var specs = [];
    if (cell.door_mm > 0) {
      specs.push({
        width: cell.door_mm * MM,
        height: DATA.standards.door_height_mm * MM,
        sill: 0,
        color: 0x475569
      });
    }
    if (cell.window_mm > 0) {
      specs.push({
        width: cell.window_mm * MM,
        height: DATA.standards.window_height_mm * MM,
        sill: DATA.standards.window_sill_height_mm * MM,
        color: 0x2563eb
      });
    }
    specs.forEach(function (spec, i) {
      var patch = new THREE.Mesh(planeGeom, solidMaterial(spec.color, 0.92));
      patch.scale.set(Math.min(spec.width, w * 0.9), spec.height, 1);
      var offset = (i === 0 ? -1 : 1) * Math.min(spec.width, w * 0.9) * 0.55;
      var eps = 0.02;
      // Nudge the patch just outside the wall plane so it does not z-fight.
      if (cell.opening_face === "north") {
        patch.position.set(cx + offset, base + spec.sill + spec.height / 2, cz - d / 2 - eps);
        patch.rotation.y = Math.PI;
      } else if (cell.opening_face === "south") {
        patch.position.set(cx + offset, base + spec.sill + spec.height / 2, cz + d / 2 + eps);
      } else if (cell.opening_face === "west") {
        patch.position.set(cx - w / 2 - eps, base + spec.sill + spec.height / 2, cz + offset);
        patch.rotation.y = -Math.PI / 2;
      } else {
        patch.position.set(cx + w / 2 + eps, base + spec.sill + spec.height / 2, cz + offset);
        patch.rotation.y = Math.PI / 2;
      }
      patch.visible = false;
      bGroup.add(patch);
      openingMeshes.push(patch);
    });
  }

  // Centre the compound on the origin so orbiting feels natural.
  bounds.setFromObject(root);
  var centre = bounds.getCenter(new THREE.Vector3());
  var size = bounds.getSize(new THREE.Vector3());
  root.position.x -= centre.x;
  root.position.z -= centre.z;
  bounds.setFromObject(root);

  // ---------- colour modes ----------
  var mode = "kind";
  function applyMode() {
    pickables.forEach(function (mesh) {
      var cell = mesh.userData.cell;
      if (mode === "provenance") {
        var style = PROV_STYLE[cell.provenance] || PROV_STYLE.auto;
        mesh.material = solidMaterial(style.color, style.opacity);
        mesh.userData.edges.material = lineMaterial(style.edge, cell.provenance === "auto" ? 0.85 : 0.5);
      } else {
        var hex = parseInt(String(cell.color).replace("#", ""), 16);
        mesh.material = solidMaterial(isNaN(hex) ? 0xffffff : hex, cell.is_outdoor ? 0.95 : 0.86);
        mesh.userData.edges.material = lineMaterial(0x22324d, 0.7);
      }
    });
    renderLegend();
  }

  function renderLegend() {
    var el = document.getElementById("legend");
    var html = "";
    if (mode === "provenance") {
      ["measured", "declared", "auto"].forEach(function (level) {
        var n = DATA.provenance.cells[level] || 0;
        html += '<span><i style="background:#' + PROV_STYLE[level].color.toString(16).padStart(6, "0") +
                '"></i>' + PROV_LABEL[level] + " " + n + " 格</span>";
      });
    } else {
      var seen = {};
      pickables.forEach(function (m) { seen[m.userData.cell.kind] = m.userData.cell.color; });
      Object.keys(seen).sort().forEach(function (kind) {
        html += '<span><i style="background:' + seen[kind] + '"></i>' +
                escapeHtml(DATA.kind_labels[kind] || kind) + "</span>";
      });
    }
    el.innerHTML = html;
  }

  // ---------- selection ----------
  var selection = new THREE.LineSegments(
    edgeGeom,
    new THREE.LineBasicMaterial({ color: 0xf2b705, depthTest: false, transparent: true, opacity: 0.95 })
  );
  selection.visible = false;
  selection.renderOrder = 999;
  scene.add(selection);

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function showInfo(mesh) {
    var info = document.getElementById("info");
    if (!mesh) {
      selection.visible = false;
      info.className = "muted";
      info.textContent = "點選任一量體查看資訊。";
      return;
    }
    var cell = mesh.userData.cell;
    var floor = mesh.userData.floor;
    var building = mesh.userData.building;

    selection.visible = true;
    selection.scale.copy(mesh.scale).multiplyScalar(1.005);
    mesh.getWorldPosition(selection.position);

    var rows = "";
    function row(k, v) { rows += "<dt>" + escapeHtml(k) + "</dt><dd>" + v + "</dd>"; }
    row("位置", escapeHtml(building.id + " 棟 · " + floor.label));
    row("幾何面積", escapeHtml(cell.area_sqm.toFixed(2) + " m² / " + cell.area_ping.toFixed(2) + " 坪"));
    row("量體尺寸", escapeHtml(Math.round(cell.w_mm) + " × " + Math.round(cell.h_mm) + " × " + Math.round(cell.is_outdoor ? DATA.standards.outdoor_slab_mm : floor.height_mm) + " mm"));
    row("尺寸來源", '<span class="pill ' + escapeHtml(cell.provenance) + '">' + escapeHtml(PROV_LABEL[cell.provenance] || cell.provenance) + "</span>");
    if (cell.size_text) { row("圖面標示", escapeHtml(cell.size_text)); }
    if (cell.declared_sqm) {
      var ratio = cell.area_sqm > 0 ? (cell.declared_sqm / cell.area_sqm) : 0;
      var warn = (ratio < 0.8 || ratio > 1.25) ? ' <span class="k">⚠ 與幾何差 ' + ratio.toFixed(2) + " 倍</span>" : "";
      row("標示面積", escapeHtml(cell.declared_sqm.toFixed(1) + " m²") + warn);
    }
    if (cell.provenance === "auto") {
      row("CSS 推導值", escapeHtml(Math.round(cell.auto_mm.w_mm) + " × " + Math.round(cell.auto_mm.h_mm) + " mm"));
    }
    if (cell.room_role && cell.room_role !== "unknown") { row("角色", escapeHtml(cell.room_role)); }
    if (cell.is_entry) { row("主要出入口", "是"); }
    if (cell.badges.length) { row("標註", escapeHtml(cell.badges.join(" · "))); }

    info.className = "";
    info.innerHTML = '<span class="name">' + escapeHtml((cell.icon ? cell.icon + " " : "") + cell.name) +
                     "</span><dl>" + rows + "</dl>";
  }

  // ---------- controls (hand-rolled: OrbitControls ships ESM only, which
  // Chrome blocks over file://) ----------
  var target = new THREE.Vector3(0, size.y * 0.35, 0);
  var spherical = { radius: Math.max(size.x, size.z, 20) * 1.35, theta: Math.PI * 0.28, phi: Math.PI * 0.34 };
  var HOME = { target: target.clone(), radius: spherical.radius, theta: spherical.theta, phi: spherical.phi };

  function updateCamera() {
    spherical.phi = Math.max(0.06, Math.min(Math.PI / 2 - 0.02, spherical.phi));
    spherical.radius = Math.max(3, Math.min(400, spherical.radius));
    camera.position.set(
      target.x + spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta),
      target.y + spherical.radius * Math.cos(spherical.phi),
      target.z + spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta)
    );
    camera.lookAt(target);
    // Panning reads the camera's own basis vectors, so keep the matrix current
    // rather than trailing the render loop by a frame.
    camera.updateMatrixWorld();
  }

  var pointers = {};
  var dragMode = null;
  var last = { x: 0, y: 0 };
  var travelled = 0;
  var pinchDistance = 0;

  canvas.addEventListener("contextmenu", function (e) { e.preventDefault(); });

  canvas.addEventListener("pointerdown", function (e) {
    canvas.setPointerCapture(e.pointerId);
    pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
    var count = Object.keys(pointers).length;
    if (count === 1) {
      dragMode = (e.button === 0 && !e.shiftKey) ? "rotate" : "pan";
      last.x = e.clientX; last.y = e.clientY;
      travelled = 0;
    } else if (count === 2) {
      dragMode = "pinch";
      pinchDistance = pointerSpread();
    }
  });

  function pointerSpread() {
    var ids = Object.keys(pointers);
    if (ids.length < 2) { return 0; }
    var a = pointers[ids[0]], b = pointers[ids[1]];
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  canvas.addEventListener("pointermove", function (e) {
    if (!pointers[e.pointerId]) { return; }
    var dx = e.clientX - last.x;
    var dy = e.clientY - last.y;
    pointers[e.pointerId] = { x: e.clientX, y: e.clientY };

    if (dragMode === "pinch") {
      var spread = pointerSpread();
      if (pinchDistance > 0 && spread > 0) {
        spherical.radius *= pinchDistance / spread;
        pinchDistance = spread;
        updateCamera();
      }
      return;
    }

    travelled += Math.abs(dx) + Math.abs(dy);
    last.x = e.clientX; last.y = e.clientY;

    if (dragMode === "rotate") {
      spherical.theta -= dx * 0.005;
      spherical.phi -= dy * 0.005;
    } else if (dragMode === "pan") {
      var scale = spherical.radius * 0.0018;
      var right = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0);
      var up = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 1);
      target.addScaledVector(right, -dx * scale);
      target.addScaledVector(up, dy * scale);
    }
    updateCamera();
  });

  function endPointer(e) {
    delete pointers[e.pointerId];
    if (Object.keys(pointers).length === 0) {
      if (dragMode === "rotate" && travelled < 6) { pick(e); }
      dragMode = null;
    } else {
      dragMode = null;
    }
  }
  canvas.addEventListener("pointerup", endPointer);
  canvas.addEventListener("pointercancel", endPointer);

  canvas.addEventListener("wheel", function (e) {
    e.preventDefault();
    spherical.radius *= (e.deltaY > 0 ? 1.1 : 0.9);
    updateCamera();
  }, { passive: false });

  var raycaster = new THREE.Raycaster();
  function pick(e) {
    var rect = canvas.getBoundingClientRect();
    var ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1
    );
    raycaster.setFromCamera(ndc, camera);
    var visible = pickables.filter(function (m) {
      return m.parent && m.parent.visible && m.position.y - m.scale.y / 2 <= clipPlane.constant;
    });
    var hits = raycaster.intersectObjects(visible, false);
    showInfo(hits.length ? hits[0].object : null);
  }

  // ---------- panel ----------
  document.getElementById("subtitle").textContent =
    DATA.buildings.length + " 棟 · " +
    DATA.buildings.reduce(function (n, b) { return n + b.floors.length; }, 0) + " 層 · " +
    DATA.provenance.total + " 個量體";

  var honesty = document.getElementById("honesty");
  var lines = [];
  lines.push("⚠️ <strong>" + DATA.provenance.total + " 格中 " + DATA.provenance.cells.auto +
             " 格（" + DATA.provenance.auto_pct + "%）的尺寸是由 CSS class 推導的猜測值，非實測。</strong>" +
             "切到「尺寸來源」模式即可看出哪些量體不可信；待實測清單見 structured/dimension_todo.md。");
  if (DATA.site.provenance !== "measured") {
    lines.push("三棟的相對位置為<strong>假設值</strong>" + (DATA.site.note ? "：" + DATA.site.note : "。"));
  }
  if (DATA.skipped.length) {
    lines.push(DATA.skipped.map(function (s) { return s.building + "：" + s.reason; }).join("；") + "。");
  }
  honesty.innerHTML = lines.join("<br />");

  var floorsEl = document.getElementById("floors");
  var byBuilding = {};
  floorGroups.forEach(function (entry) {
    (byBuilding[entry.building.id] = byBuilding[entry.building.id] || []).push(entry);
  });
  Object.keys(byBuilding).forEach(function (bid) {
    var wrap = document.createElement("div");
    wrap.className = "grp";
    var head = document.createElement("div");
    head.className = "grp-head";
    head.innerHTML = "<strong>" + escapeHtml(bid) + " 棟</strong>";
    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "grp-toggle";
    toggle.textContent = "全部切換";
    head.appendChild(toggle);
    wrap.appendChild(head);

    var boxes = [];
    byBuilding[bid].forEach(function (entry) {
      var label = document.createElement("label");
      label.className = "row";
      var box = document.createElement("input");
      box.type = "checkbox";
      box.checked = true;
      box.addEventListener("change", function () {
        entry.group.visible = box.checked;
        if (!box.checked) { showInfo(null); }
      });
      boxes.push(box);
      label.appendChild(box);
      label.appendChild(document.createTextNode(" " + entry.floor.label));
      var tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = entry.floor.cells.length + " 格";
      label.appendChild(tag);
      wrap.appendChild(label);
    });

    toggle.addEventListener("click", function () {
      var next = !boxes.every(function (b) { return b.checked; });
      boxes.forEach(function (b) {
        b.checked = next;
        b.dispatchEvent(new Event("change"));
      });
    });
    floorsEl.appendChild(wrap);
  });

  var topMm = 0;
  DATA.buildings.forEach(function (b) {
    b.floors.forEach(function (f) { topMm = Math.max(topMm, f.base_mm + f.height_mm); });
  });
  var cut = document.getElementById("cut");
  var cutLabel = document.getElementById("cut-label");
  function applyCut() {
    var ratio = Number(cut.value) / Number(cut.max);
    clipPlane.constant = (topMm * MM) * ratio + 0.001;
    cutLabel.textContent = ratio >= 1
      ? "未剖切（完整高度 " + Math.round(topMm) + " mm）"
      : "剖至 " + Math.round(topMm * ratio) + " mm（約 " + (topMm * ratio / 1000).toFixed(2) + " m）";
  }
  cut.addEventListener("input", applyCut);

  document.getElementById("openings").addEventListener("change", function (e) {
    openingMeshes.forEach(function (m) { m.visible = e.target.checked; });
  });
  document.getElementById("grid").addEventListener("change", function (e) {
    grid.visible = e.target.checked;
  });
  document.getElementById("reset-view").addEventListener("click", function () {
    target.copy(HOME.target);
    spherical.radius = HOME.radius;
    spherical.theta = HOME.theta;
    spherical.phi = HOME.phi;
    updateCamera();
  });

  Array.prototype.forEach.call(document.querySelectorAll(".seg button"), function (button) {
    button.addEventListener("click", function () {
      Array.prototype.forEach.call(document.querySelectorAll(".seg button"), function (b) {
        b.classList.toggle("on", b === button);
      });
      mode = button.getAttribute("data-mode");
      applyMode();
    });
  });

  // ---------- run ----------
  function resize() {
    var w = stage.clientWidth || 1;
    var h = stage.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize);

  applyMode();
  applyCut();
  resize();
  updateCamera();

  (function loop() {
    requestAnimationFrame(loop);
    renderer.render(scene, camera);
  })();
})();
</script>
</body>
</html>
"""


def render_html(payload: dict[str, Any], three_js: str) -> str:
    return HTML_TEMPLATE.replace("__THREE_JS__", three_js).replace(
        "__MODEL_DATA__", encode_html_json(payload)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", type=Path, default=PROGRAM_FILE)
    parser.add_argument("--output", type=Path, default=OUTPUT_HTML)
    parser.add_argument("--style", type=str, default="", help="drawing style whose room_fills the 3D reuses")
    args = parser.parse_args()

    if not args.program.exists():
        raise SystemExit(f"Missing room program: {args.program}. Run scripts/build_room_program.py first.")

    program = json.loads(args.program.read_text(encoding="utf-8"))
    overrides = load_overrides()
    style = args.style or default_drawing_style()
    payload = build_payload(program, overrides, style)
    three_js, three_meta = three_source()
    payload["source"]["three_bytes"] = three_meta["bytes"]

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
    for item in payload["skipped"]:
        print(f"  skipped {item['building']}: {item['reason']}")


if __name__ == "__main__":
    main()

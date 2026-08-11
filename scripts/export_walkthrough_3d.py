#!/usr/bin/env python3
"""Export the walk-in 3D viewer for the parametric plans.

Reads ``structured/parametric/plan.json`` and writes a single self-contained
``structured/parametric/walkthrough.html`` that opens by double-clicking — no
web server, no network, no build step.

What this is for
----------------
The architect has not drawn anything yet and the site dimensions are not fixed.
This viewer exists so the family and the architect can *stand inside* each
candidate before any of that is decided: walk in the front door, down the
corridor, into the 孝親房, and find out whether a wheelchair can turn around.
That question is not answerable from a table of areas, which is why the effort
goes here rather than into more numbers.

Walls with real holes, without CSG
----------------------------------
``plan_geometry`` records each opening as a ``(t0, t1, z0, z1)`` interval on the
wall it pierces. Rather than subtract geometry, each wall is emitted as a run of
boxes: solid spans between openings, plus the piece under a window sill and the
piece over a door lintel. Boolean geometry in the browser would be slower, more
fragile, and would look exactly the same.

Collision uses the same box list, so a hole you can see through is a hole you
can walk through. There is no separate navmesh that can disagree with the walls.

Honesty
-------
Every dimension here is derived from a stated *area requirement*, not from a
survey or an architect's drawing. The banner in the viewer says so. What is real
is the arithmetic: 32 坪 with a garage inside it does not fit the 1F brief for
A 棟 or C 棟 at any frontage, and walking through the squeezed result is the
most direct way to feel why.
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
for _p in (str(SCRIPT_DIR), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from house_design.rendering import encode_html_json  # noqa: E402
from lib import viewer_shell  # noqa: E402
from lib.standards import load_residential_defaults, repo_relative  # noqa: E402

PLAN_FILE = ROOT / "structured" / "parametric" / "plan.json"
OUTPUT_HTML = ROOT / "structured" / "parametric" / "walkthrough.html"

SCHEMA_VERSION = "house-walkthrough-v1"

# Saturated versions of the SVG room fills in export_top1_svgs.py. The paper
# palette there is nearly white by design; reused verbatim on a dark 3D ground
# every room would read as the same grey slab.
KIND_COLORS = {
    "entry": 0xF2C879,
    "living": 0xE8A15C,
    "dining": 0xE4C24A,
    "bedroom": 0x7C93E8,
    "bath": 0x4FC3D9,
    "kitchen": 0x5FBF8B,
    "service": 0x8899B4,
    "stair": 0xB0BCCF,
    "outdoor": 0x63A96A,
    "other": 0x9AA7BD,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_payload(plan: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    geometry = defaults.get("geometry", {})
    site = plan.get("site", {})
    return {
        "schema": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "source": {
            "plan": repo_relative(PLAN_FILE),
            "plan_schema": plan.get("schema"),
            "plan_generated_at": plan.get("generated_at"),
        },
        "site": site,
        "row": plan.get("row", {}),
        "standards": {
            "door_height_mm": int(geometry.get("door_height_mm", 2100)),
            "storey_height_mm": int(site.get("storey_height_mm", 3000)),
            "parapet_height_mm": int(site.get("parapet_height_mm", 1100)),
            "wheelchair_turn_mm": int(
                site.get("corridor", {}).get("wheelchair_turn_mm", 1500)
            ),
        },
        "kind_colors": KIND_COLORS,
        "variants": plan.get("variants", []),
        "findings": plan.get("findings", []),
        "provenance": plan.get("provenance", {}),
    }


# The template is a plain string with placeholders rather than an f-string: the
# JavaScript below is mostly braces, and doubling every one of them to survive
# f-string interpolation is a reliable way to introduce a typo nobody can see.
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>參數化平面 · 走入式 3D</title>
<style>
__BASE_CSS__
  .val { margin-left: auto; font-variant-numeric: tabular-nums; color: var(--text); }
  .slider-head { display: flex; align-items: center; font-size: 12px; margin-bottom: 2px; }
  .slider-head b { font-weight: 600; }
  #rules { font-size: 11.5px; line-height: 1.5; }
  #rules .f {
    display: block; width: 100%; text-align: left; margin-bottom: 4px; padding: 6px 8px;
    border-radius: 6px; border: 1px solid var(--line); background: var(--card);
    color: var(--text); cursor: pointer; font-family: inherit; font-size: 11.5px;
  }
  #rules .f:hover { border-color: var(--accent); }
  #rules .f .code { font-weight: 700; font-size: 10px; letter-spacing: .04em; }
  #rules .f.error .code { color: var(--bad); }
  #rules .f.warning .code { color: var(--warn); }
  #rules .f.note .code { color: var(--muted); }
  #rules .f .where { color: var(--muted); }
  #info dl { display: grid; grid-template-columns: auto 1fr; gap: 3px 10px; margin: 0; font-size: 12px; }
  #info dt { color: var(--muted); }
  #info dd { margin: 0; }
  #info .name { font-size: 15px; font-weight: 700; display: block; margin-bottom: 6px; }
  .flag { display: inline-block; padding: 1px 7px; border-radius: 999px; font-size: 10px;
          font-weight: 700; background: rgba(242,99,126,.18); color: #ffb3c3; margin-right: 4px; }
  #crosshair {
    position: absolute; left: 50%; top: 50%; width: 14px; height: 14px; margin: -7px 0 0 -7px;
    pointer-events: none; display: none;
  }
  #crosshair::before, #crosshair::after {
    content: ""; position: absolute; background: rgba(255,255,255,.75);
  }
  #crosshair::before { left: 6px; top: 0; width: 2px; height: 14px; }
  #crosshair::after { top: 6px; left: 0; height: 2px; width: 14px; }
  #stage.walking canvas { cursor: none; }
  #stage.walking #crosshair { display: block; }
  #turnbadge {
    position: absolute; right: 16px; top: 14px; font-size: 12px; padding: 7px 12px;
    border-radius: 8px; border: 1px solid var(--line); background: rgba(9,14,26,.75);
    color: var(--muted); display: none; line-height: 1.5;
  }
  #stage.wheels #turnbadge { display: block; }
  #turnbadge.bad { border-color: var(--bad); color: #ffb3c3; }
  #turnbadge.ok { border-color: var(--ok); color: #a7f0d4; }
</style>
</head>
<body>
<div id="app">
  <aside id="panel">
    <h1>走入式 3D · 設計前期</h1>
    <p class="sub" id="subtitle"></p>
    <div class="banner warn">
      這不是建築師的圖。所有尺寸都是<b>從面積需求反推</b>的，用來感受空間大小與動線，
      不能拿去申請建照。地的長寬尚未決定，棟距與三棟位置都是假設。
    </div>

    <h2>檢視模式</h2>
    <div class="seg" role="group" aria-label="檢視模式">
      <button type="button" data-view="orbit" class="on">環繞</button>
      <button type="button" data-view="walk">走入</button>
    </div>
    <div class="hint" id="view-hint"></div>

    <h2>參數</h2>
    <div class="slider-head"><b>開間</b><span class="val" id="v-frontage"></span></div>
    <input type="range" id="frontage" min="0" max="4" step="1" value="0" aria-label="開間" />
    <div class="hint" id="h-frontage"></div>

    <div class="slider-head"><b>車位</b><span class="val" id="v-bays"></span></div>
    <input type="range" id="bays" min="0" max="1" step="1" value="0" aria-label="車位數" />
    <div class="hint">車庫在建築體內，計入 32 坪建築面積。</div>

    <div class="slider-head"><b>棟距</b><span class="val" id="v-gap"></span></div>
    <input type="range" id="gap" min="3000" max="12000" step="500" value="6000" aria-label="棟距" />
    <div class="hint">棟距只影響三棟的相對位置，不改變任何平面幾何。</div>

    <h2>樓層</h2>
    <div class="seg" id="floors" role="group" aria-label="樓層"></div>
    <label class="row" style="margin-top:8px">
      <input type="checkbox" id="allfloors" /> 環繞模式顯示全部樓層
    </label>
    <label class="row">
      <input type="checkbox" id="wheels" /> 輪椅模式（迴轉圈 <span id="turnmm"></span> mm）
    </label>
    <div class="hint" id="h-wheels"></div>

    <h2>規則檢查<span class="val" id="rule-count"></span></h2>
    <div id="rules"></div>

    <h2>選取</h2>
    <div id="info" class="muted">環繞模式點選房間看資訊。</div>
  </aside>
  <main id="stage">
    <canvas id="canvas"></canvas>
    <div id="hud"></div>
    <div id="crosshair"></div>
    <div id="turnbadge"></div>
  </main>
</div>

<script>__THREE_JS__</script>
<script>
(function () {
  "use strict";
  var DATA = __MODEL_DATA__;
  var MM = 0.001;

  // Coordinate convention
  // ---------------------
  // Plan space: x runs right across the facade, y runs from the front facade
  // toward the rear. World space is Y-up, so:
  //     worldX = planX,  worldY = height,  worldZ = -planY
  // The negation is what puts the front yard at positive Z. A camera there
  // looking toward -Z has its screen-right along +X, so the building with the
  // largest planX appears on the right — which is how 「右 A、中 B、左 C」
  // ends up true rather than mirrored.
  function wz(planY) { return -planY * MM; }

  var STOREY = DATA.standards.storey_height_mm;
  var TURN = DATA.standards.wheelchair_turn_mm;
  var PARAPET = DATA.standards.parapet_height_mm;

  var EYE_WALK = 1600, EYE_CHAIR = 1200;
  var RAD_WALK = 250, RAD_CHAIR = 375;   // body radius, mm
  var SPEED = 2.6;                        // m/s

  // ---------- scene ----------
  var canvas = document.getElementById("canvas");
  var stage = document.getElementById("stage");
  var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x0b1020, 1);

  var scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0b1020, 40, 150);
  var camera = new THREE.PerspectiveCamera(60, 1, 0.05, 500);

  scene.add(new THREE.HemisphereLight(0xdce8ff, 0x1b2438, 1.15));
  var sun = new THREE.DirectionalLight(0xffffff, 0.75);
  sun.position.set(24, 40, 26);
  scene.add(sun);
  var fillLight = new THREE.DirectionalLight(0xbcd4ff, 0.30);
  fillLight.position.set(-26, 16, -20);
  scene.add(fillLight);

  var ground = new THREE.Mesh(
    new THREE.PlaneGeometry(400, 400),
    new THREE.MeshLambertMaterial({ color: 0x15203a })
  );
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.02;
  scene.add(ground);
  var grid = new THREE.GridHelper(200, 100, 0x33507a, 0x1d2c46);
  scene.add(grid);

  var boxGeom = new THREE.BoxGeometry(1, 1, 1);
  var planeGeom = new THREE.PlaneGeometry(1, 1);
  var edgeGeom = new THREE.EdgesGeometry(boxGeom);

  var matCache = {};
  function mat(hex, opacity, lit) {
    var key = hex + "_" + opacity + "_" + (lit ? 1 : 0);
    if (!matCache[key]) {
      var Ctor = lit ? THREE.MeshLambertMaterial : THREE.MeshBasicMaterial;
      matCache[key] = new Ctor({
        color: hex, transparent: opacity < 1, opacity: opacity,
        side: THREE.DoubleSide, depthWrite: opacity > 0.65
      });
    }
    return matCache[key];
  }
  var wallMat = new THREE.MeshLambertMaterial({ color: 0xd8dfec, side: THREE.DoubleSide });
  var extMat = new THREE.MeshLambertMaterial({ color: 0xaab6c9, side: THREE.DoubleSide });
  var glassMat = new THREE.MeshLambertMaterial({
    color: 0x8fd4ff, transparent: true, opacity: 0.22, side: THREE.DoubleSide, depthWrite: false
  });
  var edgeMat = new THREE.LineBasicMaterial({ color: 0x2a3b5a, transparent: true, opacity: 0.5 });

  // ---------- state ----------
  // `garage` is an object, so dedupe on its bay count — comparing the objects
  // themselves gives one "option" per variant and silently breaks both sliders.
  var frontages = [], bayOptions = [];
  DATA.variants.forEach(function (v) {
    if (frontages.indexOf(v.frontage_mm) < 0) { frontages.push(v.frontage_mm); }
    if (bayOptions.indexOf(v.garage.bays) < 0) { bayOptions.push(v.garage.bays); }
  });
  frontages.sort(function (a, b) { return a - b; });
  bayOptions.sort(function (a, b) { return a - b; });

  var state = {
    fIndex: 0, bIndex: 0, gap: DATA.row.gap_mm || 6000,
    floor: "floor-1", allFloors: false, wheels: false, walking: false
  };

  var root = new THREE.Group();
  scene.add(root);
  var buildingGroups = [];   // { id, group, originX_mm }
  var floorGroups = [];      // { buildingId, floorId, group }
  var pickables = [];
  var ceilings = [];
  var blockers = [];         // { x0,z0,x1,z1 } world metres, current floor only
  var highlight = null;

  function currentVariant() {
    var f = frontages[state.fIndex], g = bayOptions[state.bIndex];
    for (var i = 0; i < DATA.variants.length; i++) {
      if (DATA.variants[i].frontage_mm === f && DATA.variants[i].garage.bays === g) {
        return DATA.variants[i];
      }
    }
    return DATA.variants[0];
  }

  // ---------- wall splitting ----------
  // A wall is a run of boxes rather than one box with a hole: solid spans
  // between openings, the piece under a window sill, the piece over a lintel.
  // Returned pieces are in plan mm; `blocks` marks the ones a body runs into.
  function wallPieces(wall, height) {
    var box = wall.box;                       // [x0, y0, x1, y1]
    var vertical = wall.orientation === "v";  // runs along plan y
    var t0 = vertical ? box[1] : box[0];
    var t1 = vertical ? box[3] : box[2];
    var ops = (wall.openings || []).filter(function (o) {
      return Math.min(t1, o.t1) > Math.max(t0, o.t0);
    });
    var pieces = [];

    function solid(a, b, z0, z1) {
      if (b - a < 1 || z1 - z0 < 1) { return; }
      pieces.push({
        a: a, b: b, z0: z0, z1: z1,
        // Anything whose underside sits at knee level or below stops a body.
        // A lintel at 2100 does not, which is exactly why a door is walkable
        // and a window is not.
        blocks: z0 < 900
      });
    }

    // Sweep the wall's own length rather than walking the openings in order.
    // Openings can overlap — the entry window lands on top of the front door on
    // several variants — and a sequential walk re-inserts that window's sill
    // straight across the doorway, quietly bricking up the front door.
    var cuts = [t0, t1];
    ops.forEach(function (o) {
      cuts.push(Math.max(t0, o.t0));
      cuts.push(Math.min(t1, o.t1));
    });
    cuts.sort(function (a, b) { return a - b; });

    for (var i = 0; i < cuts.length - 1; i++) {
      var a = cuts[i], b = cuts[i + 1];
      if (b - a < 1) { continue; }
      var midT = (a + b) / 2;
      // Union of every opening covering this strip, as a list of z intervals.
      var holes = [];
      ops.forEach(function (o) {
        if (o.t0 <= midT && midT <= o.t1) {
          holes.push([Math.max(0, o.z0), Math.min(height, o.z1)]);
        }
      });
      holes.sort(function (x, y) { return x[0] - y[0]; });
      var z = 0;
      holes.forEach(function (h) {
        if (h[1] <= z) { return; }          // wholly swallowed by an earlier hole
        solid(a, b, z, Math.min(h[0], height));
        z = Math.max(z, h[1]);
      });
      solid(a, b, z, height);
    }
    return pieces;
  }

  function addWall(group, wall, baseMm, height, collect) {
    var box = wall.box;
    var vertical = wall.orientation === "v";
    var thick = vertical ? (box[2] - box[0]) : (box[3] - box[1]);
    var fixed = vertical ? (box[0] + box[2]) / 2 : (box[1] + box[3]) / 2;
    var material = wall.kind === "exterior" ? extMat : wallMat;

    wallPieces(wall, height).forEach(function (p) {
      var len = p.b - p.a, h = p.z1 - p.z0;
      var mid = (p.a + p.b) / 2;
      var m = new THREE.Mesh(boxGeom, material);
      if (vertical) {
        m.scale.set(thick * MM, h * MM, len * MM);
        m.position.set(fixed * MM, (baseMm + p.z0 + h / 2) * MM, wz(mid));
      } else {
        m.scale.set(len * MM, h * MM, thick * MM);
        m.position.set(mid * MM, (baseMm + p.z0 + h / 2) * MM, wz(fixed));
      }
      group.add(m);
      if (collect && p.blocks) {
        var hw = (vertical ? thick : len) * MM / 2;
        var hd = (vertical ? len : thick) * MM / 2;
        collect.push({
          x0: m.position.x - hw, x1: m.position.x + hw,
          z0: m.position.z - hd, z1: m.position.z + hd
        });
      }
    });
  }

  function addGlass(group, win, baseMm) {
    var vertical = win.orientation === "v";
    var w = win.width_mm * MM, h = win.height_mm * MM;
    var m = new THREE.Mesh(planeGeom, glassMat);
    m.scale.set(w, h, 1);
    var y = (baseMm + win.sill_mm + win.height_mm / 2) * MM;
    if (vertical) {
      m.rotation.y = Math.PI / 2;
      m.position.set(win.line * MM, y, wz(win.center));
    } else {
      m.position.set(win.center * MM, y, wz(win.line));
    }
    group.add(m);
  }

  // ---------- build ----------
  function clearGroup(g) {
    while (g.children.length) {
      var c = g.children.pop();
      if (c.geometry && c.geometry !== boxGeom && c.geometry !== planeGeom &&
          c.geometry !== edgeGeom) { c.geometry.dispose(); }
    }
  }

  function rebuild() {
    clearGroup(root);
    buildingGroups = []; floorGroups = []; pickables = []; ceilings = []; highlight = null;

    var variant = currentVariant();
    // Plan x increases to the right on the plan, and DATA.row lists the order
    // in that same direction, so laying the buildings out along +X in list
    // order needs no reversal anywhere.
    var order = DATA.row.order_left_to_right || ["C", "B", "A"];
    var cursor = 0;
    order.forEach(function (bid) {
      var b = variant.buildings[bid];
      if (!b) { return; }
      var g = new THREE.Group();
      g.position.x = cursor * MM;
      root.add(g);
      buildingGroups.push({ id: bid, group: g, width_mm: b.frontage_mm });
      cursor += b.frontage_mm + state.gap;

      b.floors.forEach(function (floor) {
        var fg = new THREE.Group();
        g.add(fg);
        floorGroups.push({ buildingId: bid, floorId: floor.floor_id, group: fg, floor: floor, building: b });
        buildFloor(fg, floor, b, bid);
      });

      var label = labelSprite(bid + " 棟");
      label.position.set(b.frontage_mm * MM / 2, 3 * STOREY * MM + 1.6, wz(b.depth_mm / 2));
      g.add(label);
    });
    // Re-centre so the row straddles the origin: the default camera sits on the
    // Z axis and should look at the middle building, not past the end of the row.
    var span = cursor - state.gap;
    root.position.x = -span * MM / 2;
    applyVisibility();
    refreshRules();
    return variant;
  }

  function buildFloor(fg, floor, building, bid) {
    var idx = ["floor-1", "floor-2", "floor-3"].indexOf(floor.floor_id);
    var isRoof = floor.floor_id === "floor-rf";
    var base = (isRoof ? 3 : idx) * STOREY;
    var height = isRoof ? PARAPET : STOREY;

    // Slab, so a walker has something under their feet and the plan reads from above.
    var net = floor.net_rect;
    var slab = new THREE.Mesh(boxGeom, mat(0x1b2740, 1, true));
    slab.scale.set((net[2] - net[0]) * MM, 0.12, (net[3] - net[1]) * MM);
    slab.position.set(
      (net[0] + net[2]) / 2 * MM, (base - 60) * MM, wz((net[1] + net[3]) / 2)
    );
    fg.add(slab);

    // Room floor patches: colour is what makes a space legible from inside.
    floor.cells.forEach(function (cell) {
      var r = cell.clear_rect || cell.rect;
      var w = (r[2] - r[0]) * MM, d = (r[3] - r[1]) * MM;
      if (w <= 0 || d <= 0) { return; }
      var color = DATA.kind_colors[cell.kind] || DATA.kind_colors.other;
      // Unprogrammed slack reads as a hole in the palette on purpose: it is
      // floor area the brief never asked for, and it should look unfinished
      // rather than blend in as one more room.
      var alpha = 0.85;
      if (cell.role === "flex") { color = 0xC94F7C; alpha = 0.38; }
      var patch = new THREE.Mesh(planeGeom, mat(color, alpha, false));
      patch.rotation.x = -Math.PI / 2;
      patch.scale.set(w, d, 1);
      patch.position.set((r[0] + r[2]) / 2 * MM, (base + 6) * MM, wz((r[1] + r[3]) / 2));
      patch.userData = { cell: cell, floor: floor, building: building, bid: bid };
      fg.add(patch);
      pickables.push(patch);

      var edge = new THREE.LineSegments(
        new THREE.EdgesGeometry(new THREE.PlaneGeometry(w, d)), edgeMat
      );
      edge.rotation.x = -Math.PI / 2;
      edge.position.copy(patch.position);
      fg.add(edge);
    });

    (floor.walls || []).forEach(function (wall) {
      addWall(fg, wall, base, height, null);
    });
    (floor.windows || []).forEach(function (win) { addGlass(fg, win, base); });

    // A ceiling, for walk mode only. Without one the sky pours in and a corridor
    // reads as a canyon rather than a corridor — which defeats the whole point
    // of walking through it. Orbit mode needs the rooms open from above.
    if (!isRoof) {
      // Unlit: every light in the scene is above the slab, so a Lambert ceiling
      // is lit only on the side nobody can see and reads as solid black.
      var ceil = new THREE.Mesh(planeGeom, mat(0x30405e, 1, false));
      ceil.rotation.x = Math.PI / 2;
      ceil.scale.set((net[2] - net[0]) * MM, (net[3] - net[1]) * MM, 1);
      ceil.position.set(
        (net[0] + net[2]) / 2 * MM, (base + STOREY - 10) * MM, wz((net[1] + net[3]) / 2)
      );
      ceil.userData.ceiling = true;
      fg.add(ceil);
      ceilings.push(ceil);
    }
  }

  // Floating labels, because the whole point of the default front-yard camera is
  // that the user can confirm 右 A／中 B／左 C without taking my word for the
  // coordinate algebra.
  function labelSprite(text) {
    var c = document.createElement("canvas");
    c.width = 256; c.height = 128;
    var g = c.getContext("2d");
    g.fillStyle = "rgba(11,16,32,.82)";
    g.strokeStyle = "#19c3c5"; g.lineWidth = 6;
    g.beginPath(); g.roundRect(6, 22, 244, 84, 16); g.fill(); g.stroke();
    g.fillStyle = "#e8edf7";
    g.font = "bold 58px 'Microsoft JhengHei', sans-serif";
    g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(text, 128, 64);
    var tex = new THREE.CanvasTexture(c);
    var sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false }));
    sp.scale.set(3.2, 1.6, 1);
    return sp;
  }

  // ---------- visibility & collision ----------
  function applyVisibility() {
    floorGroups.forEach(function (fg) {
      fg.group.visible = (state.allFloors && !state.walking) || fg.floorId === state.floor;
    });
    ceilings.forEach(function (c) { c.visible = state.walking; });
    rebuildBlockers();
  }

  // Collision is derived from the very boxes that were drawn, so a gap you can
  // see through is a gap you can walk through. Rebuilt on any change that moves
  // a wall, because a stale blocker list is an invisible wall.
  function rebuildBlockers() {
    blockers = [];
    var variant = currentVariant();
    buildingGroups.forEach(function (bg) {
      var b = variant.buildings[bg.id];
      if (!b) { return; }
      b.floors.forEach(function (floor) {
        if (floor.floor_id !== state.floor) { return; }
        var isRoof = floor.floor_id === "floor-rf";
        var height = isRoof ? PARAPET : STOREY;
        var local = [];
        (floor.walls || []).forEach(function (wall) {
          var tmp = new THREE.Group();
          addWall(tmp, wall, 0, height, local);
        });
        local.forEach(function (r) {
          blockers.push({
            x0: r.x0 + bg.group.position.x + root.position.x,
            x1: r.x1 + bg.group.position.x + root.position.x,
            z0: r.z0, z1: r.z1
          });
        });
      });
    });
  }

  function resolve(px, pz, radius) {
    for (var pass = 0; pass < 3; pass++) {
      var moved = false;
      for (var i = 0; i < blockers.length; i++) {
        var b = blockers[i];
        var cx = Math.max(b.x0, Math.min(px, b.x1));
        var cz = Math.max(b.z0, Math.min(pz, b.z1));
        var dx = px - cx, dz = pz - cz;
        var d2 = dx * dx + dz * dz;
        if (d2 >= radius * radius) { continue; }
        var d = Math.sqrt(d2);
        if (d > 1e-6) {
          px = cx + dx / d * radius; pz = cz + dz / d * radius;
        } else {
          // Dead centre inside the box: push out along the shallowest face.
          var l = px - b.x0, r = b.x1 - px, u = pz - b.z0, dn = b.z1 - pz;
          var m = Math.min(l, r, u, dn);
          if (m === l) { px = b.x0 - radius; }
          else if (m === r) { px = b.x1 + radius; }
          else if (m === u) { pz = b.z0 - radius; }
          else { pz = b.z1 + radius; }
        }
        moved = true;
      }
      if (!moved) { break; }
    }
    return [px, pz];
  }

  function clearanceAt(px, pz) {
    var best = Infinity;
    for (var i = 0; i < blockers.length; i++) {
      var b = blockers[i];
      var cx = Math.max(b.x0, Math.min(px, b.x1));
      var cz = Math.max(b.z0, Math.min(pz, b.z1));
      best = Math.min(best, Math.hypot(px - cx, pz - cz));
    }
    return best;
  }

  // ---------- camera: orbit + first person ----------
  var onOrbitPick = null;  // assigned below; ORBIT_JS calls it by name
__ORBIT_JS__

  var walker = { x: 0, z: 0, yaw: Math.PI, pitch: 0 };
  var keys = {};
  window.addEventListener("keydown", function (e) {
    keys[e.code] = true;
    if (state.walking && ["KeyW", "KeyA", "KeyS", "KeyD", "Space"].indexOf(e.code) >= 0) {
      e.preventDefault();
    }
    if (e.code === "Escape" && state.walking) { setView("orbit"); }
  });
  window.addEventListener("keyup", function (e) { keys[e.code] = false; });

  canvas.addEventListener("click", function () {
    if (state.walking && document.pointerLockElement !== canvas) {
      lockPointer();
    }
  });

  // Pointer lock is the good experience, but some file:// and embedded contexts
  // refuse it. Dragging to look is the fallback, so walking never becomes
  // impossible — only slightly clumsier.
  var dragLook = false;
  function lockPointer() {
    try {
      var r = canvas.requestPointerLock();
      if (r && typeof r.catch === "function") { r.catch(function () {}); }
    } catch (err) { /* fall through to drag-look */ }
  }
  function look(dx, dy) {
    walker.yaw -= dx * 0.0022;
    walker.pitch = Math.max(-1.4, Math.min(1.4, walker.pitch - dy * 0.0022));
  }
  document.addEventListener("mousemove", function (e) {
    if (!state.walking) { return; }
    if (document.pointerLockElement === canvas) { look(e.movementX, e.movementY); }
    else if (dragLook) { look(e.movementX || 0, e.movementY || 0); }
  });
  canvas.addEventListener("pointerdown", function () {
    if (state.walking && document.pointerLockElement !== canvas) { dragLook = true; }
  });
  window.addEventListener("pointerup", function () { dragLook = false; });
  document.addEventListener("pointerlockerror", function () {
    el.viewHint.textContent = "這個環境不允許鎖定滑鼠，改用按住左鍵拖曳轉向。";
  });

  function spawnInFrontYard() {
    // Line the walker up with the middle building's front door, three metres
    // out. Standing at the centre of the facade instead would mean the first
    // press of W walks into a wall, which teaches the user nothing.
    var variant = currentVariant();
    var mid = buildingGroups[Math.floor(buildingGroups.length / 2)];
    if (!mid) { return; }
    var b = variant.buildings[mid.id];
    var ground = b.floors[0];
    var offset = b.frontage_mm / 2;
    (ground.doors || []).forEach(function (d) {
      if (d.role === "main_entrance") { offset = d.center; }
    });
    walker.x = root.position.x + mid.group.position.x + offset * MM;
    walker.z = 3.0;
    walker.yaw = 0;  // faces -Z, i.e. straight at the facades
    walker.pitch = 0;
    // On an upper floor there is no front yard to stand in; start by the stair.
    if (state.floor !== "floor-1") {
      var fl = null;
      b.floors.forEach(function (f) { if (f.floor_id === state.floor) { fl = f; } });
      if (fl) {
        fl.cells.forEach(function (c) {
          if (c.role !== "corridor") { return; }
          var r = c.clear_rect;
          walker.x = root.position.x + mid.group.position.x + (r[0] + r[2]) / 2 * MM;
          walker.z = wz((r[1] + r[3]) / 2);
        });
      }
    }
  }

  function updateWalker(dt) {
    var fwd = 0, side = 0;
    if (keys.KeyW || keys.ArrowUp) { fwd += 1; }
    if (keys.KeyS || keys.ArrowDown) { fwd -= 1; }
    if (keys.KeyD || keys.ArrowRight) { side += 1; }
    if (keys.KeyA || keys.ArrowLeft) { side -= 1; }
    var boost = keys.ShiftLeft || keys.ShiftRight ? 2.2 : 1;

    if (fwd || side) {
      var len = Math.hypot(fwd, side);
      var s = Math.sin(walker.yaw), c = Math.cos(walker.yaw);
      // A three.js camera looks down its local -Z, so yaw 0 faces -Z world and
      // the look direction is (-sin, -cos) — not (sin, cos). Getting this
      // backwards makes W walk out of the scene while facing the wrong way.
      var vx = (-s * fwd + c * side) / len;
      var vz = (-c * fwd - s * side) / len;
      var step = SPEED * boost * dt;
      var radius = (state.wheels ? RAD_CHAIR : RAD_WALK) * MM;
      var got = resolve(walker.x + vx * step, walker.z + vz * step, radius);
      walker.x = got[0]; walker.z = got[1];
    }

    var eye = (state.wheels ? EYE_CHAIR : EYE_WALK) * MM;
    var base = floorBaseMm() * MM;
    camera.position.set(walker.x, base + eye, walker.z);
    camera.rotation.set(0, 0, 0);
    camera.rotateY(walker.yaw);
    camera.rotateX(walker.pitch);
    camera.updateMatrixWorld();

    updateTurnCircle();
  }

  function floorBaseMm() {
    var idx = ["floor-1", "floor-2", "floor-3"].indexOf(state.floor);
    return (idx < 0 ? 3 : idx) * STOREY;
  }

  // ---------- wheelchair turning circle ----------
  var turnRing = new THREE.Mesh(
    new THREE.RingGeometry(0.5, 0.5, 64),
    new THREE.MeshBasicMaterial({ color: 0x35d39a, side: THREE.DoubleSide,
                                  transparent: true, opacity: 0.85 })
  );
  turnRing.rotation.x = -Math.PI / 2;
  turnRing.visible = false;
  scene.add(turnRing);

  function setRingRadius(r) {
    turnRing.geometry.dispose();
    turnRing.geometry = new THREE.RingGeometry(r * 0.94, r, 64);
  }
  setRingRadius(TURN * MM / 2);

  var badge = document.getElementById("turnbadge");
  function updateTurnCircle() {
    if (!state.wheels || !state.walking) { turnRing.visible = false; return; }
    var need = TURN * MM / 2;
    var got = clearanceAt(walker.x, walker.z);
    var fits = got >= need;
    turnRing.visible = true;
    turnRing.position.set(walker.x, floorBaseMm() * MM + 0.02, walker.z);
    turnRing.material.color.setHex(fits ? 0x35d39a : 0xf2637e);
    badge.className = fits ? "ok" : "bad";
    // Stated as a radius on both sides of the comparison: half of the 1500 mm
    // turning circle is the distance to the nearest wall that has to be free.
    badge.innerHTML = (fits ? "迴轉圈 " + TURN + " mm 放得下" : "迴轉圈 " + TURN + " mm 放不下") +
      "<br><span class=\\"muted\\">身邊淨空 " + Math.round(got * 1000) +
      " mm　／　需要 " + Math.round(need * 1000) + " mm（半徑）</span>";
  }

  // ---------- picking ----------
  var raycaster = new THREE.Raycaster();
  onOrbitPick = function (e) {
    var rect = canvas.getBoundingClientRect();
    var ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1
    );
    raycaster.setFromCamera(ndc, camera);
    var visible = pickables.filter(function (m) { return m.parent && m.parent.visible; });
    var hits = raycaster.intersectObjects(visible, false);
    if (hits.length) { showCell(hits[0].object); }
  };

  var infoEl = document.getElementById("info");
  function showCell(mesh) {
    if (highlight) { highlight.material = highlight.userData.baseMat; }
    var u = mesh.userData;
    var c = u.cell;
    mesh.userData.baseMat = mesh.userData.baseMat || mesh.material;
    highlight = mesh;
    mesh.material = mat(0x19c3c5, 0.92, false);

    var r = c.clear_rect || c.rect;
    var w = r[2] - r[0], d = r[3] - r[1];
    var flags = (c.flags || []).map(function (f) {
      return '<span class="flag">' + f + "</span>";
    }).join("");
    infoEl.className = "";
    infoEl.innerHTML =
      '<span class="name">' + c.name + "</span>" +
      "<dl>" +
      "<dt>棟／層</dt><dd>" + u.bid + " 棟 " + u.floor.label + "</dd>" +
      "<dt>淨尺寸</dt><dd>" + w + " × " + d + " mm</dd>" +
      "<dt>面積</dt><dd>" + c.area_sqm + " m²（" + c.area_ping + " 坪）</dd>" +
      (c.target_sqm ? "<dt>需求</dt><dd>" + c.target_sqm + " m²</dd>" : "") +
      "<dt>採光</dt><dd>" + (c.exterior_sides.length ? c.exterior_sides.length + " 面外牆" : "無外牆") + "</dd>" +
      "</dl>" +
      (flags ? "<div style='margin-top:8px'>" + flags + "</div>" : "") +
      (c.note ? "<p class='hint' style='margin-top:8px'>" + c.note + "</p>" : "");
  }

  // ---------- panel ----------
  var el = {
    frontage: document.getElementById("frontage"),
    bays: document.getElementById("bays"),
    gap: document.getElementById("gap"),
    vFrontage: document.getElementById("v-frontage"),
    vBays: document.getElementById("v-bays"),
    vGap: document.getElementById("v-gap"),
    hFrontage: document.getElementById("h-frontage"),
    floors: document.getElementById("floors"),
    allFloors: document.getElementById("allfloors"),
    wheels: document.getElementById("wheels"),
    rules: document.getElementById("rules"),
    ruleCount: document.getElementById("rule-count"),
    hud: document.getElementById("hud"),
    viewHint: document.getElementById("view-hint"),
    subtitle: document.getElementById("subtitle")
  };

  el.frontage.max = String(frontages.length - 1);
  el.bays.max = String(bayOptions.length - 1);
  el.gap.min = String(DATA.row.gap_min_mm || 3000);
  el.gap.max = String(DATA.row.gap_max_mm || 12000);
  el.gap.value = String(state.gap);
  document.getElementById("turnmm").textContent = TURN;
  document.getElementById("h-wheels").textContent =
    "眼高 " + EYE_CHAIR + " mm、車身半徑 " + RAD_CHAIR +
    " mm。走入模式下地上會畫出迴轉圈，放不下就變紅。";

  ["floor-1", "floor-2", "floor-3", "floor-rf"].forEach(function (fid, i) {
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = ["1F", "2F", "3F", "RF"][i];
    b.dataset.floor = fid;
    if (fid === state.floor) { b.className = "on"; }
    b.addEventListener("click", function () {
      state.floor = fid;
      Array.prototype.forEach.call(el.floors.children, function (x) {
        x.className = x.dataset.floor === fid ? "on" : "";
      });
      applyVisibility();
      if (state.walking) { spawnInFrontYard(); }
      syncLabels();
    });
    el.floors.appendChild(b);
  });

  function syncLabels() {
    var v = currentVariant();
    el.vFrontage.textContent = (v.frontage_mm / 1000).toFixed(1) + " m";
    el.vBays.textContent = v.garage.label;
    el.vGap.textContent = (state.gap / 1000).toFixed(1) + " m";
    el.hFrontage.textContent =
      "進深 " + (v.depth_mm / 1000).toFixed(1) + " m（面積鎖死在 " +
      v.footprint_ping.toFixed(2) + " 坪，開間變寬進深就變淺）";
    el.subtitle.textContent =
      v.frontage_mm / 1000 + " × " + (v.depth_mm / 1000).toFixed(1) + " m　·　" +
      v.garage.label + "　·　右 A／中 B／左 C";
    el.hud.innerHTML = state.walking
      ? "W A S D 走動 · 滑鼠轉向 · Shift 加速 · Esc 離開走入模式"
      : "拖曳旋轉 · 滾輪縮放 · 右鍵／Shift 拖曳平移 · 點選房間看資訊";
    el.viewHint.textContent = state.walking
      ? "點畫面鎖定滑鼠後才能轉向。走入模式只顯示目前樓層。"
      : "環繞看整體；要感受空間大小請切到走入。";
  }

  el.frontage.addEventListener("input", function () {
    state.fIndex = parseInt(this.value, 10);
    rebuild(); syncLabels(); if (state.walking) { spawnInFrontYard(); }
  });
  el.bays.addEventListener("input", function () {
    state.bIndex = parseInt(this.value, 10);
    rebuild(); syncLabels(); if (state.walking) { spawnInFrontYard(); }
  });
  el.gap.addEventListener("input", function () {
    // Gap only moves buildings, so shift the groups instead of rebuilding.
    state.gap = parseInt(this.value, 10);
    var cursor = 0;
    buildingGroups.forEach(function (bg) {
      bg.group.position.x = cursor * MM;
      cursor += bg.width_mm + state.gap;
    });
    root.position.x = -(cursor - state.gap) * MM / 2;
    rebuildBlockers();
    syncLabels();
  });
  el.allFloors.addEventListener("change", function () {
    state.allFloors = this.checked; applyVisibility();
  });
  el.wheels.addEventListener("change", function () {
    state.wheels = this.checked;
    stage.classList.toggle("wheels", state.wheels);
    // The chair is wider than the walker, so a spot that was legal a moment ago
    // may now be inside a wall. Push out immediately instead of on next input.
    if (state.walking) {
      var got = resolve(walker.x, walker.z, (state.wheels ? RAD_CHAIR : RAD_WALK) * MM);
      walker.x = got[0]; walker.z = got[1];
    }
  });

  Array.prototype.forEach.call(document.querySelectorAll("[data-view]"), function (b) {
    b.addEventListener("click", function () { setView(b.dataset.view); });
  });

  function setView(view) {
    state.walking = view === "walk";
    Array.prototype.forEach.call(document.querySelectorAll("[data-view]"), function (x) {
      x.className = x.dataset.view === view ? "on" : "";
    });
    stage.classList.toggle("walking", state.walking);
    orbit.setEnabled(!state.walking);
    if (state.walking) {
      camera.fov = 72;
      spawnInFrontYard();
      applyVisibility();
      lockPointer();
    } else {
      camera.fov = 60;
      if (document.pointerLockElement === canvas) { document.exitPointerLock(); }
      applyVisibility();
      homeCamera();
    }
    camera.updateProjectionMatrix();
    syncLabels();
  }

  function homeCamera() {
    var variant = currentVariant();
    var span = 0;
    buildingGroups.forEach(function (bg) { span += bg.width_mm + state.gap; });
    span = Math.max(span - state.gap, 12000) * MM;
    var t = new THREE.Vector3(0, 4, -variant.depth_mm * MM / 2);
    // theta = 0 puts the camera on +Z looking toward -Z: standing in the front
    // yard, which is the one viewpoint where 右 A／中 B／左 C is checkable.
    orbit.setHome(t, span * 1.15, 0, Math.PI * 0.40);
  }

  // ---------- rules ----------
  function refreshRules() {
    var v = currentVariant();
    var list = DATA.findings.filter(function (f) { return f.variant === v.id; });
    el.ruleCount.textContent = list.length + " 項";
    if (!list.length) {
      el.rules.innerHTML = "<p class='hint'>這個變體沒有觸發任何規則。</p>";
      return;
    }
    var rank = { error: 0, warning: 1, note: 2 };
    list = list.slice().sort(function (a, b) {
      return (rank[a.severity] - rank[b.severity]) || a.building.localeCompare(b.building);
    });
    el.rules.innerHTML = "";
    list.forEach(function (f) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "f " + f.severity;
      b.innerHTML = '<span class="code">' + f.code + "</span> " +
                    '<span class="where">' + f.building + " 棟 " + f.floor + "</span><br>" +
                    f.message;
      b.addEventListener("click", function () { focusFinding(f); });
      el.rules.appendChild(b);
    });
  }

  function focusFinding(f) {
    if (f.floor_id && f.floor_id !== state.floor) {
      var btn = el.floors.querySelector('[data-floor="' + f.floor_id + '"]');
      if (btn) { btn.click(); }
    }
    var refs = f.refs || [];
    for (var i = 0; i < pickables.length; i++) {
      var u = pickables[i].userData;
      if (u.bid === f.building && u.floor.floor_id === f.floor_id &&
          (refs.indexOf(u.cell.id) >= 0 || (!refs.length && u.cell.role === "corridor"))) {
        showCell(pickables[i]);
        if (!state.walking) {
          pickables[i].getWorldPosition(orbit.target);
          orbit.update();
        }
        return;
      }
    }
  }

  // Everything above lives in a closure, which is right for a page that shares
  // the global scope with an inlined library — but it also means an automated
  // browser check has nothing to assert against. This is that seam, and the
  // only reason it exists.
  window.__walkDebug = function () {
    return {
      variant: currentVariant().id,
      state: { floor: state.floor, walking: state.walking, wheels: state.wheels, gap: state.gap },
      walker: { x: +walker.x.toFixed(3), z: +walker.z.toFixed(3), yaw: +walker.yaw.toFixed(3) },
      camera: [+camera.position.x.toFixed(2), +camera.position.y.toFixed(2), +camera.position.z.toFixed(2)],
      blockers: blockers.length,
      clearance_mm: Math.round(clearanceAt(walker.x, walker.z) * 1000),
      // Screen-space x of each building, so 右 A／中 B／左 C is checkable by a
      // machine instead of by trusting my coordinate algebra.
      onScreen: buildingGroups.map(function (bg) {
        var v = new THREE.Vector3(bg.width_mm * MM / 2, 1.5, -1);
        bg.group.localToWorld(v);
        v.project(camera);
        return { id: bg.id, ndcX: +v.x.toFixed(3) };
      })
    };
  };

  // ---------- run ----------
__LOOP_JS__

  rebuild();
  syncLabels();
  homeCamera();
  startLoop(function (dt) {
    if (state.walking) { updateWalker(dt); }
  });
})();
</script>
</body>
</html>
"""


def render_html(payload: dict[str, Any], three_js: str) -> str:
    return (
        HTML_TEMPLATE
        .replace("__BASE_CSS__", viewer_shell.BASE_CSS)
        .replace("__ORBIT_JS__", viewer_shell.ORBIT_JS)
        .replace("__LOOP_JS__", viewer_shell.LOOP_JS)
        .replace("__THREE_JS__", three_js)
        .replace("__MODEL_DATA__", encode_html_json(payload))
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export the walk-in 3D viewer.")
    ap.add_argument("--plan", type=Path, default=PLAN_FILE)
    ap.add_argument("--output", type=Path, default=OUTPUT_HTML)
    args = ap.parse_args(argv)

    if not args.plan.exists():
        raise SystemExit(
            f"Missing {repo_relative(args.plan)}. "
            "Run scripts/generate_parametric_plan.py first."
        )

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    defaults = load_residential_defaults()
    payload = build_payload(plan, defaults)
    three_js, three_meta = three_source_checked()
    html = render_html(payload, three_js)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")

    floors = sum(len(b["floors"]) for v in payload["variants"] for b in v["buildings"].values())
    walls = sum(len(f.get("walls", []))
                for v in payload["variants"] for b in v["buildings"].values()
                for f in b["floors"])
    print(f"走入式 3D：{repo_relative(args.output)}")
    print(f"  變體 {len(payload['variants'])}　樓層 {floors}　牆段 {walls}　"
          f"規則 {len(payload['findings'])} 項")
    print(f"  {three_meta.get('version') or 'three.js'}"
          f"（{three_meta['bytes'] // 1024} KB 內嵌）"
          f"　輸出 {args.output.stat().st_size // 1024} KB")
    return 0


def three_source_checked() -> tuple[str, dict[str, Any]]:
    return viewer_shell.three_source()


if __name__ == "__main__":
    raise SystemExit(main())

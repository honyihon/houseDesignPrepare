#!/usr/bin/env python3
"""Shared pieces for the single-file, offline three.js viewers.

``export_model_3d.py`` proved this arrangement works when the page is opened by
double-clicking a ``file://`` path: three.js r160 UMD inlined into a plain
``<script>`` block, a hand-rolled orbit controller, and no fetch of any kind.
``export_walkthrough_3d.py`` needs the same foundation, so the parts that are
genuinely identical live here rather than being copied and left to drift.

What is *not* here is the scene construction. The massing viewer draws one box
per room; the walkthrough viewer draws walls with holes in them. Those have
nothing in common beyond the camera, and pretending otherwise would produce a
helper with a flag for every difference.

``export_model_3d.py`` is deliberately left alone: it is verified and shipped.
Merging it onto this shell is a separate, later change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
THREE_FILE = ROOT / "assets" / "vendor" / "three" / "three.min.js"
VERSION_FILE = ROOT / "assets" / "vendor" / "three" / "VERSION.txt"


def three_source() -> tuple[str, dict[str, Any]]:
    """Return the vendored three.js text, ready to drop inside a script tag."""
    if not THREE_FILE.exists():
        raise SystemExit(
            f"three.js not vendored: {THREE_FILE} is missing.\n"
            "See assets/vendor/three/VERSION.txt for the exact build to fetch."
        )
    source = THREE_FILE.read_text(encoding="utf-8")
    # Inlining is only safe while the bundle contains no closing script tag. A
    # future upgrade that breaks this should fail loudly rather than silently
    # produce a viewer truncated halfway through the library.
    if "</script" in source.lower():
        raise SystemExit(
            f"{THREE_FILE} contains a closing script tag and cannot be inlined verbatim."
        )
    version = ""
    if VERSION_FILE.exists():
        version = VERSION_FILE.read_text(encoding="utf-8").strip().splitlines()[0]
    return source, {"bytes": len(source.encode("utf-8")), "version": version}


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

# Dark palette shared with model3d.html so the two viewers read as one tool.
BASE_CSS = """
  :root {
    --bg0: #0b1020; --bg1: #101c2f; --card: #131f36; --line: #2a3b5a;
    --text: #e8edf7; --muted: #9fb0cd; --accent: #19c3c5;
    --warn: #f8b84e; --bad: #f2637e; --ok: #35d39a;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0; color: var(--text); overflow: hidden;
    font-family: "Segoe UI", "Microsoft JhengHei", sans-serif;
    background: linear-gradient(145deg, var(--bg0), var(--bg1));
  }
  #app { display: grid; grid-template-columns: 340px minmax(0, 1fr); height: 100vh; }
  #panel {
    overflow-y: auto; padding: 16px; border-right: 1px solid var(--line);
    background: rgba(9, 14, 26, 0.72);
  }
  #panel h1 { font-size: 18px; margin: 0 0 2px; }
  #panel h2 {
    font-size: 12px; letter-spacing: .08em; text-transform: uppercase;
    color: var(--muted); margin: 18px 0 8px;
  }
  .sub { margin: 0; font-size: 12px; color: var(--muted); }
  .banner { margin-top: 12px; padding: 9px 11px; border-radius: 8px; font-size: 12px; line-height: 1.55; }
  .banner.warn { background: rgba(248, 184, 78, .12); border: 1px solid rgba(248, 184, 78, .42); color: #ffdda1; }
  /* Which branch this viewer belongs to: ok = the predesign baseline, note =
     the archived HTML sketches. Both viewers look equally finished, so the
     status has to be on the page rather than only in CLAUDE.md. */
  .banner.ok { background: rgba(88, 214, 165, .12); border: 1px solid rgba(88, 214, 165, .42); color: #a7f0d4; }
  .banner.note { background: rgba(150, 160, 180, .12); border: 1px solid rgba(150, 160, 180, .40); color: #ccd4e2; }
  .seg { display: flex; gap: 6px; }
  .seg button {
    flex: 1; padding: 7px 6px; font-size: 12px; cursor: pointer; color: var(--muted);
    background: var(--card); border: 1px solid var(--line); border-radius: 7px;
    font-family: inherit;
  }
  .seg button.on { color: #08131f; background: var(--accent); border-color: var(--accent); font-weight: 700; }
  .seg button:focus-visible, #panel input:focus-visible, button:focus-visible {
    outline: 3px solid var(--accent); outline-offset: 2px;
  }
  label.row { display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 3px 0; cursor: pointer; }
  label.row .tag { margin-left: auto; font-size: 10px; color: var(--muted); }
  input[type="range"] { width: 100%; }
  .hint { font-size: 11px; color: var(--muted); margin: 4px 0 10px; line-height: 1.5; }
  .muted { color: var(--muted); }
  #stage { position: relative; }
  canvas { display: block; width: 100%; height: 100%; touch-action: none; cursor: grab; }
  canvas:active { cursor: grabbing; }
  #hud {
    position: absolute; left: 14px; top: 12px; font-size: 11px; color: var(--muted);
    background: rgba(9, 14, 26, .68); border: 1px solid var(--line); border-radius: 8px;
    padding: 7px 11px; line-height: 1.7; pointer-events: none; max-width: 46ch;
  }
  @media (max-width: 860px) {
    #app { grid-template-columns: 1fr; grid-template-rows: minmax(0, 44vh) minmax(0, 1fr); }
    #panel { border-right: 0; border-bottom: 1px solid var(--line); }
  }
"""


# ---------------------------------------------------------------------------
# JS: orbit controller
# ---------------------------------------------------------------------------

# Hand-rolled rather than OrbitControls: the examples/ addons only ship as ES
# modules, which Chrome refuses to load cross-origin over file://.
#
# Expects `canvas`, `camera`, `THREE` in scope, and a global `onOrbitPick(event)`
# for click-to-select. Exposes `orbit` with target/spherical/update/home.
ORBIT_JS = """
  var orbit = (function () {
    var target = new THREE.Vector3(0, 0, 0);
    var sph = { radius: 30, theta: Math.PI * 0.28, phi: Math.PI * 0.34 };
    var home = { target: target.clone(), radius: 30, theta: sph.theta, phi: sph.phi };
    var enabled = true;

    function update() {
      sph.phi = Math.max(0.06, Math.min(Math.PI - 0.06, sph.phi));
      sph.radius = Math.max(1.5, Math.min(400, sph.radius));
      camera.position.set(
        target.x + sph.radius * Math.sin(sph.phi) * Math.sin(sph.theta),
        target.y + sph.radius * Math.cos(sph.phi),
        target.z + sph.radius * Math.sin(sph.phi) * Math.cos(sph.theta)
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
    var pinch = 0;

    function spread() {
      var ids = Object.keys(pointers);
      if (ids.length < 2) { return 0; }
      var a = pointers[ids[0]], b = pointers[ids[1]];
      return Math.hypot(a.x - b.x, a.y - b.y);
    }

    canvas.addEventListener("contextmenu", function (e) { e.preventDefault(); });

    canvas.addEventListener("pointerdown", function (e) {
      if (!enabled) { return; }
      canvas.setPointerCapture(e.pointerId);
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      var n = Object.keys(pointers).length;
      if (n === 1) {
        dragMode = (e.button === 0 && !e.shiftKey) ? "rotate" : "pan";
        last.x = e.clientX; last.y = e.clientY; travelled = 0;
      } else if (n === 2) {
        dragMode = "pinch"; pinch = spread();
      }
    });

    canvas.addEventListener("pointermove", function (e) {
      if (!enabled || !pointers[e.pointerId]) { return; }
      var dx = e.clientX - last.x, dy = e.clientY - last.y;
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };

      if (dragMode === "pinch") {
        var s = spread();
        if (pinch > 0 && s > 0) { sph.radius *= pinch / s; pinch = s; update(); }
        return;
      }
      travelled += Math.abs(dx) + Math.abs(dy);
      last.x = e.clientX; last.y = e.clientY;

      if (dragMode === "rotate") {
        sph.theta -= dx * 0.005;
        sph.phi -= dy * 0.005;
      } else if (dragMode === "pan") {
        var scale = sph.radius * 0.0018;
        var right = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0);
        var up = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 1);
        target.addScaledVector(right, -dx * scale);
        target.addScaledVector(up, dy * scale);
      }
      update();
    });

    function end(e) {
      delete pointers[e.pointerId];
      if (Object.keys(pointers).length === 0) {
        if (enabled && dragMode === "rotate" && travelled < 6 &&
            typeof onOrbitPick === "function") { onOrbitPick(e); }
      }
      dragMode = null;
    }
    canvas.addEventListener("pointerup", end);
    canvas.addEventListener("pointercancel", end);

    canvas.addEventListener("wheel", function (e) {
      if (!enabled) { return; }
      e.preventDefault();
      sph.radius *= (e.deltaY > 0 ? 1.1 : 0.9);
      update();
    }, { passive: false });

    return {
      target: target, sph: sph, update: update,
      setEnabled: function (v) { enabled = !!v; pointers = {}; dragMode = null; },
      setHome: function (t, r, th, ph) {
        home = { target: t.clone(), radius: r, theta: th, phi: ph };
        this.goHome();
      },
      goHome: function () {
        target.copy(home.target);
        sph.radius = home.radius; sph.theta = home.theta; sph.phi = home.phi;
        update();
      }
    };
  })();
"""


# Expects `stage`, `renderer`, `camera`, `scene`; call `startLoop(beforeRender)`.
LOOP_JS = """
  function resize() {
    var w = stage.clientWidth || 1, h = stage.clientHeight || 1;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize);

  function startLoop(beforeRender) {
    var prev = performance.now();
    resize();
    (function loop(now) {
      requestAnimationFrame(loop);
      var dt = Math.min(((now || prev) - prev) / 1000, 0.1);
      prev = now || prev;
      if (beforeRender) { beforeRender(dt); }
      renderer.render(scene, camera);
    })(prev);
  }
"""

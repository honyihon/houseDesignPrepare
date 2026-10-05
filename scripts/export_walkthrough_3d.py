#!/usr/bin/env python3
"""Export the walk-in 3D viewer for the legacy parametric scenario.

Reads ``structured/parametric/plan.json`` and writes a single self-contained
``structured/parametric/walkthrough.html`` that opens by double-clicking — no
web server, no network, no build step.

What this is for
----------------
This viewer preserves an earlier thought experiment so the family and architect
can discuss how the old room brief behaved when every storey was assumed to be
32 ping. The confirmed 32 ping is now parcel area, so this is regression and
archive evidence, not a proposed or buildable design.

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
Every dimension here is derived from an old *area assumption*, not from a survey
or an architect's drawing. The banner in the viewer says so. The model may still
help explain why the former brief became squeezed, but it cannot establish what
fits on any of the three parcels.
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

from lib import viewer_shell  # noqa: E402
from lib.html_parametric_compare import build_compare, build_compare_variants  # noqa: E402
from lib.standards import load_residential_defaults, repo_relative  # noqa: E402

from house_design.rendering import encode_html_json  # noqa: E402

PLAN_FILE = ROOT / "structured" / "parametric" / "plan.json"
PROGRAM_FILE = ROOT / "structured" / "room_program.json"
OUTPUT_HTML = ROOT / "structured" / "parametric" / "walkthrough.html"

SCHEMA_VERSION = "house-walkthrough-v2"

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


def build_payload(
    plan: dict[str, Any],
    defaults: dict[str, Any],
    program: dict[str, Any] | None = None,
) -> dict[str, Any]:
    geometry = defaults.get("geometry", {})
    site = plan.get("site", {})
    if program is None:
        compare = {
            "schema": "house-html-parametric-compare-v2",
            "available": False,
            "variant": None,
            "ghost": None,
            "buildings": [],
            "summary": {},
            "note": "缺少 room_program.json；3D 可檢視，但原 HTML 對照不可用。",
        }
        compare_variants: dict[str, dict[str, Any]] = {}
    else:
        compare = build_compare(program, plan)
        compare_variants = build_compare_variants(program, plan)
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
        "compare": compare,
        "compare_variants": compare_variants,
    }


# The template is a plain string with placeholders rather than an f-string: the
# JavaScript below is mostly braces, and doubling every one of them to survive
# f-string interpolation is a reliable way to introduce a typo nobody can see.
TEMPLATE_FILE = SCRIPT_DIR / "templates/walkthrough.html"
HTML_TEMPLATE = TEMPLATE_FILE.read_text(encoding="utf-8")


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
    ap.add_argument("--program", type=Path, default=PROGRAM_FILE)
    ap.add_argument("--output", type=Path, default=OUTPUT_HTML)
    args = ap.parse_args(argv)

    if not args.plan.exists():
        raise SystemExit(
            f"Missing {repo_relative(args.plan)}. "
            "Run scripts/generate_parametric_plan.py first."
        )

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if plan.get("schema") != "house-parametric-plan-v1":
        raise SystemExit(f"Unsupported parametric plan schema: {plan.get('schema')!r}")
    if not isinstance(plan.get("variants"), list) or not plan["variants"]:
        raise SystemExit("Parametric plan has no variants; refusing to emit an empty viewer.")
    program = None
    if args.program.exists():
        program = json.loads(args.program.read_text(encoding="utf-8"))
    defaults = load_residential_defaults()
    payload = build_payload(plan, defaults, program)
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

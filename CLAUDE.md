# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Residential building design preparation toolchain for a three-building compound (A, B, C buildings + storage) in Taiwan. Converts interactive HTML floor-plan pages into structured JSON, then runs a Python pipeline that generates scored layout candidates, SVG floor-plan drawings, and print-ready PDF bundles. Domain language is Traditional Chinese (zh-TW); dimensions in mm and "ping" (tsubo) area units.

## Which data is authoritative

The current confirmed condition is **three adjacent, separately reviewed
parcels in Kaohsiung, each approximately 32 ping of land**. Thirty-two ping is
parcel area, not a permitted floor footprint.

Authority is split by data type:

| Data | Current authority |
|---|---|
| Parcel facts and unknown legal inputs | `inputs/project.json` |
| Owner decisions and unconfirmed ideas | `inputs/requirements.json` |
| Architect drawing versions and normalized evidence | `inputs/revisions/<revision>/` |
| Current findings and offline dashboard | `structured/reviews/<revision>/` |

`inputs/site.json` + `inputs/brief/{A,B,C}.json` → `structured/parametric/`
is now a **legacy parametric scenario**. It treats 32 ping as each storey's
building area, so it remains useful only for historical discussion and
regression tests. It must never be called the current baseline, a buildable
envelope, or a regulatory result.

The numbered HTML pipeline below is also historical. Its 82% auto-derived
geometry is useful as an archive and parser regression sample, not drawing
evidence.

The HTML branch is kept for three reasons, all of them real: it is the **archive
of the original sketches** (where the room list came from), it carries the
**traceability** from `inputs/design_request.md` prose to named rooms, and it is
the **regression sample** that keeps the older pipeline honest. It is not a
design input any more. Its own "canonical" rule (below) still holds *within that
branch* — `XbuildingView.html` remains the source of truth for the HTML branch's
own outputs — it just no longer means "source of truth for the project".

Practical consequence: do not port dimensions from either historical branch
into the current project model. New facts go to `inputs/project.json`; owner
decisions go to the requirement register; real geometry arrives through an
immutable PDF + IFC/DXF revision.

## Architecture & Data Flow (HTML historical branch)

```
HTML source files (AbuildingView.html, BbuildingView.html, CbuildingView.html, storage.html)
  │
  ├─ [Step 0] annotate_html_geometry.py (optional pre-processing, adds data-* attrs to HTML)
  │
  ├─ [Step 1] extract_layout_data.py → structured/*.structured.json
  │
  ├─ [Step 2] build_room_program.py → structured/room_program.json (unified building/floor/room schema)
  │
  ├─ [Step 3] generate_layout_candidates.py → structured/candidates/layout_candidates.json + summary.md
  │
  ├─ [Step 4] render_candidate_viewer.py → structured/candidates/viewer.html
  │
  ├─ [Step 5] export_model_3d.py → structured/candidates/model3d.html (offline 3D massing viewer)
  │
  ├─ [Step 6] export_top1_svgs.py → structured/candidates/svg/*.svg + manifest.json + index.html
  │
  └─ [Step 7] export_print_bundle_pdf.py → structured/candidates/print_bundle.pdf
```

`inputs/dimensions.json` (schema `house-dimensions-override-v1`) feeds Step 2 and
overrides the auto-derived grid geometry. Every cell carries a
`geometry_provenance` of `measured` | `declared` | `auto`; most are still `auto`,
i.e. guessed from CSS classes. See "Geometry provenance" below.

**Storeys.** Each building is **3 habitable storeys plus RF**. RF is a roof — a
parapet with the stair penthouse, water tank, heat pump and solar — not a fourth
floor. `floor-4` does not exist; the ids are `floor-1|floor-2|floor-3|floor-rf`
in the parametric branch, and the HTML branch's fourth SVG (`*_floor-4.svg`) is
the roof level under an older name.

**Row order.** Standing in the front yard facing the buildings, right → left is
**A, B, C**. In every viewer, world X = plan x and larger x is to the right, so
`site` placement in `inputs/dimensions.json` puts C at x=0 and A at the largest
x. Both 3D viewers depend on this; do not "tidy" it back to alphabetical.

### Parametric branch — legacy 32-ping-footprint scenario

This branch answers the historical question "what fits if every storey itself
is 32 ping?" It does not answer what fits on a 32-ping parcel after coverage,
setbacks and legal open space. Its outputs must retain a legacy warning.

```
inputs/site.json          massing parameters (frontage variants, garage bays, row order, gap)
inputs/brief/{A,B,C}.json per-room area brief (target/min area, band, light, access, notes)
  │
  ├─ generate_parametric_plan.py → structured/parametric/plan.json    (walls, doors, windows, stairs)
  │      via lib/plan_geometry.py    → structured/parametric/capacity.md (capacity ledger + rule findings)
  │      and  lib/plan_rules.py
  │
  └─ export_walkthrough_3d.py   → structured/parametric/walkthrough.html (single-file offline, walk-in)
```

Depth is derived, never entered: `depth = 32坪 × 3.305785 × 1e6 / frontage_mm`,
so floor area is pinned at 32 坪 and the frontage slider trades width for depth.
Ten variants (5 frontages × 2 garage sizes) are pre-baked into `plan.json`; the
building-gap slider is applied live in the viewer because it only moves the three
buildings relative to each other.

The generator **produces a plan even when the brief does not fit** — over-capacity
floors are compressed and flagged rather than aborting the run. Seeing 玄關 squeezed
to 1.8 m² is the point; a clean failure would hide it.

**The garage is the one exception to "compress quietly".** The car parks inside the
building, so the garage has a hard minimum derived from the `vehicle` block in
`residential_defaults_tw.json` (one SUV plus a wall-mounted EV charger): clear
**3000 × 6100 mm** for one bay, **5250 × 6100** for two. `garage_min_bay_mm()` in
`lib/plan_geometry.py` is the single source of that number — both the generator and
the rule checker call it. A garage that comes out smaller is clamped to the space
that exists and flagged `GARAGE_TOO_SHALLOW` / `GARAGE_TOO_NARROW` on the skeleton
and `GARAGE_NOT_PARKABLE` (error) / `GARAGE_FEWER_BAYS` (warning) in the findings.
The generator does **not** rotate the garage 90° to fit a shallow footprint: the
three houses sit in a row with their only street frontage at the front, so a
side-facing garage door would open onto the 6 m gap with no driveway behind it.
Consequence, as of 2026-08-10: an indoor SUV garage only works at **6 m and 7 m
frontage (all three) and 8 m (A and C)**; two indoor bays fit at no frontage.

## Running the Pipeline

**Dependencies:** `beautifulsoup4`, `reportlab`, `svglib`

```bash
python -m pip install --user beautifulsoup4 reportlab svglib
```

**Individual steps:**
```bash
python scripts/extract_layout_data.py
python scripts/build_room_program.py
python scripts/generate_layout_candidates.py
python scripts/render_candidate_viewer.py
python scripts/export_model_3d.py
python scripts/export_top1_svgs.py --selection baseline|best
python scripts/export_print_bundle_pdf.py --paper a3|a4 --output structured/candidates/print_bundle.pdf
python scripts/validate_layout_bundle.py  # standalone validation gate
python scripts/check_html_consistency.py --mode concept|draft|ifc  # geometry/HTML findings
python scripts/seed_dimension_overrides.py --dry-run  # what can be back-filled vs measured
python scripts/generate_parametric_plan.py   # parametric branch: plan.json + capacity.md
python scripts/export_walkthrough_3d.py      # parametric branch: walk-in 3D
```

**One-click (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1
# Options: -Mode concept|draft|ifc  -Paper a3|a4  -Selection auto|baseline|best
```

**Current review CLI:**
```bash
python -m house_design intake validate
python -m house_design drawings import --revision R001 --label "初步設計" --pdf drawings.pdf --ifc model.ifc
python -m house_design review run --revision R001 --previous R000
```

The historical rendering pipeline remains available with `pipeline`. Its final
validation mode is named `release`; `ifc` is a deprecated compatibility alias
and does not mean the pipeline reads IFC:

```bash
python -m house_design pipeline --mode release --force
```

This entrypoint uses `.house-design-cache.json` to skip steps whose commands,
inputs, and expected outputs are unchanged.

- **concept**: fast, skips PDF, auto-selects the source-preserving `baseline` candidate
- **draft**: default, baseline selection, generates PDF
- **release**: full historical export + validation gate; still not professional approval

## Critical Conventions

- **Two-file pattern** (HTML branch): Each building has canonical HTML (`XbuildingView.html`) and a `_tmp` working copy. The HTML pipeline reads only canonical (non-`_tmp`) files, and within that historical branch the canonical file is its own source of truth. Never modify `*_tmp` files.
- **Millimeter geometry**: The `data-*-mm` attributes on `.plan-cell` and `.floor-plan` carry the geometry the pipeline reads, but most of them were *generated* by `annotate_html_geometry.py` from CSS classes, not measured. Real numbers belong in `inputs/dimensions.json`, which wins over the HTML. `blueprint-precise-mm` is only claimed when no cell is left at `auto`; otherwise the mode is `mixed-provenance`.
- **DOM skeleton must be preserved**: `.floor-plan > .plan-grid-visual > .plan-row > .plan-cell` structure is parsed by BeautifulSoup. Do not restructure this hierarchy.
- **Room-cell binding**: `onclick="highlightRoom('xxx', this)"` must correspond to `id="room-xxx"`. Keep these in sync.
- **Main entrance**: Only one `.plan-cell` per floor should have `data-entry="true"`.
- **After editing HTML**: Always run the historical pipeline (at minimum `-Mode concept`) to verify changes. Its release gate does not update or approve the current parcel/drawing review.

## Geometry provenance

Every cell and floor carries `geometry_provenance`:

| Value | Meaning |
|-------|---------|
| `measured` | Someone put a tape measure on it and recorded the number in `inputs/dimensions.json`. |
| `declared` | Back-filled from the `.cell-size` text in the HTML (a stated ping figure or W×H), so it reflects intent but not survey. |
| `auto` | Derived by `annotate_html_geometry.py` from CSS classes — a heuristic guess. |

As of 2026-08-06: 0 measured, 15 declared, 69 auto (82.1% guessed). Floor areas,
daylight factors, egress proxies, and every candidate score inherit that
uncertainty, so treat absolute numbers as indicative until the count moves.

`structured/dimension_todo.md` lists what still needs measuring, grouped by
building and floor. `structured/candidates/model3d.html` shows the same thing
spatially: its "尺寸來源" mode draws `auto` cells as wireframe.

Three-building site placement (`site` in `inputs/dimensions.json`) is entirely
assumed — a 12 m east-west row. Nothing in the source data records it.

## Key Files

| File | Purpose |
|------|---------|
| `scripts/config/residential_defaults_tw.json` | Centralized Taiwan residential defaults (wall thickness, door/window widths, furniture dims, `vehicle` = SUV + EV-charger clearances the garage minimum is derived from) |
| `scripts/lib/standards.py` | Typed access to the defaults config |
| `inputs/dimensions.json` | Measured/declared geometry overrides; wins over the HTML `data-*-mm` values |
| `scripts/lib/dimension_overrides.py` | Loads the overrides and stamps `geometry_provenance` onto the room program |
| `scripts/seed_dimension_overrides.py` | Back-fills overrides from `.cell-size` text; writes `structured/dimension_todo.md` |
| `scripts/export_model_3d.py` | Builds the offline 3D massing viewer (`structured/candidates/model3d.html`) |
| `assets/vendor/three/` | Vendored three.js r160 UMD build; must stay UMD so `file://` double-click works |
| `scripts/lib/viewer_shell.py` | Shared CSS / orbit controller / render loop for the offline three.js viewers |
| `inputs/site.json` | Parametric massing parameters (schema `house-site-massing-v1`) |
| `inputs/brief/{A,B,C}.json` | Per-room area brief (schema `house-area-brief-v1`); hand-written from `inputs/design_request.md` |
| `scripts/lib/plan_geometry.py` | Derives walls/doors/windows/stairs from the brief (fixed core + corridor spine + guillotine split) |
| `scripts/lib/plan_rules.py` | Circulation-graph rule checks (wheelchair turn, door clear width, 穿堂煞, 武轎 path …) |
| `scripts/generate_parametric_plan.py` | Bakes the 10 variants into `structured/parametric/plan.json` + `capacity.md` |
| `scripts/export_walkthrough_3d.py` | Builds the walk-in 3D viewer (`structured/parametric/walkthrough.html`) |
| `scripts/WEB_TO_PLAN_PROMPTS.zh-TW.md` | Prompt templates for HTML→plan conversion workflow |
| `scripts/run_full_pipeline.ps1` | Pipeline orchestrator (concept/draft/ifc modes) |
| `.mcp.json` | Project-level MCP servers (playwright + brave-search) for web lookup tasks |
| `網路架構.txt` | Network architecture doc (standalone, not processed by pipeline) |

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Residential building design preparation toolchain for a three-building compound (A, B, C buildings + storage) in Taiwan. Converts interactive HTML floor-plan pages into structured JSON, then runs a Python pipeline that generates scored layout candidates, SVG floor-plan drawings, and print-ready PDF bundles. Domain language is Traditional Chinese (zh-TW); dimensions in mm and "ping" (tsubo) area units.

## Architecture & Data Flow

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
  ├─ [Step 5] export_top1_svgs.py → structured/candidates/svg/*.svg + manifest.json + index.html
  │
  └─ [Step 6] export_print_bundle_pdf.py → structured/candidates/print_bundle.pdf
```

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
python scripts/export_top1_svgs.py --selection baseline|best
python scripts/export_print_bundle_pdf.py --paper a3|a4 --output structured/candidates/print_bundle.pdf
python scripts/validate_layout_bundle.py  # standalone validation gate
```

**One-click (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1
# Options: -Mode concept|draft|ifc  -Paper a3|a4  -Selection auto|baseline|best
```

**Incremental package CLI:**
```bash
python -m house_design pipeline --mode concept
python -m house_design pipeline --mode draft --from-step candidates --to-step svg
python -m house_design pipeline --mode ifc --force
```

This entrypoint uses `.house-design-cache.json` to skip steps whose commands,
inputs, and expected outputs are unchanged.

- **concept**: fast, skips PDF, auto-selects the source-preserving `baseline` candidate
- **draft**: default, baseline selection, generates PDF
- **ifc**: full export + validation gate

## Critical Conventions

- **Two-file pattern**: Each building has canonical HTML (`XbuildingView.html`) and a `_tmp` working copy. Pipeline reads only canonical (non-`_tmp`) files. Never modify `*_tmp` files.
- **Millimeter geometry**: All `data-*-mm` attributes on `.plan-cell` and `.floor-plan` elements are the source of truth. When all cells provide x/y/w/h in mm, the pipeline enters `blueprint-precise-mm` mode; otherwise it falls back to estimation.
- **DOM skeleton must be preserved**: `.floor-plan > .plan-grid-visual > .plan-row > .plan-cell` structure is parsed by BeautifulSoup. Do not restructure this hierarchy.
- **Room-cell binding**: `onclick="highlightRoom('xxx', this)"` must correspond to `id="room-xxx"`. Keep these in sync.
- **Main entrance**: Only one `.plan-cell` per floor should have `data-entry="true"`.
- **After editing HTML**: Always run the pipeline (at minimum `-Mode concept`) to verify changes. For release, run `-Mode ifc`.

## Key Files

| File | Purpose |
|------|---------|
| `scripts/config/residential_defaults_tw.json` | Centralized Taiwan residential defaults (wall thickness, door/window widths, furniture dims) |
| `scripts/lib/standards.py` | Typed access to the defaults config |
| `scripts/WEB_TO_PLAN_PROMPTS.zh-TW.md` | Prompt templates for HTML→plan conversion workflow |
| `scripts/run_full_pipeline.ps1` | Pipeline orchestrator (concept/draft/ifc modes) |
| `.mcp.json` | Project-level MCP servers (playwright + brave-search) for web lookup tasks |
| `網路架構.txt` | Network architecture doc (standalone, not processed by pipeline) |

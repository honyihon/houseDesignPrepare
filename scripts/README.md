# Layout Data Extraction

## Purpose

Convert the static building HTML pages into structured JSON files for downstream automation
(layout scoring, auto-plan generation, prompt input, etc.).

## Input Files

- `AbuildingView.html`
- `BbuildingView.html`
- `CbuildingView.html`
- `storage.html`

## Output Directory

- `structured/`
  - `AbuildingView.structured.json`
  - `BbuildingView.structured.json`
  - `CbuildingView.structured.json`
  - `storage.structured.json`
  - `index.json`

## Run

```bash
python scripts/extract_layout_data.py
python scripts/build_room_program.py
python scripts/generate_layout_candidates.py
python scripts/render_candidate_viewer.py
python scripts/export_top1_svgs.py
python scripts/export_print_bundle_pdf.py
```

## One-Click Run (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1
```

Common options:

```powershell
# Export A4 bundle
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Paper a4 -Output structured/candidates/print_bundle_a4.pdf

# Fast concept iteration (no PDF, auto selection=best)
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Mode concept

# Draft bundle (default mode, auto selection=baseline)
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Mode draft

# IFC-like gate (full export + validation)
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Mode ifc

# Force specific candidate selection
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Selection best

# Use a specific Python executable
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -PythonExe py
```

## One-Click Expert Workflow (A/B/C + 5 Experts)

This is the all-in-one entrypoint for:
- requirement normalization
- expert hard gates (regulation/accessibility)
- HTML consistency checks
- pipeline export
- validation
- report + task-board update

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
  -Selection auto
```

Interface:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request <path/to/request.md> `
  -Mode <concept|draft|ifc> `
  -Buildings <A,B,C> `
  -Selection <auto|baseline|best> `
  -Paper <a3|a4> `
  -Output <output/pdf/path> `
  -PythonExe <python>
```

Key outputs:
- `structured/expert_review/report.json`
- `structured/expert_review/report.md`
- `structured/expert_review/request_normalized.json`
- `structured/expert_review/html_consistency.json`
- `task-board.md`

## Dependency

```bash
python -m pip install --user beautifulsoup4
python -m pip install --user reportlab svglib
```

## Output for Step 2

After running `build_room_program.py`, you'll get:

- `structured/room_program.json`

This file unifies all buildings into one normalized schema:
- building/floor hierarchy
- room list with area parsing (`坪`, `m × m`)
- plan-cell mapping to rooms
- tables/checklists/section bullets converted into constraints

## Output for Step 3

After running `generate_layout_candidates.py`, you'll get:

- `structured/candidates/layout_candidates.json`
- `structured/candidates/summary.md`

Each evaluated floor includes:
- `baseline`, `circulation`, `daylight`, `mep` candidates
- per-candidate scores (`circulation`, `daylight`, `mep`, `utilization`, `total`)
- room-slot assignment details and unplaced/unassigned lists

## Output for Step 4

After running `render_candidate_viewer.py`, you'll get:

- `structured/candidates/viewer.html`

This page provides:
- floor selection
- candidate switching (ranked list)
- slot-to-room visual mapping
- score bars and rationale / unplaced room summaries

## Output for Step 5

After running `export_top1_svgs.py`, you'll get:

- `structured/candidates/svg/*.svg` (one Top1 SVG per evaluated floor)
- `structured/candidates/svg/manifest.json`
- `structured/candidates/svg/index.html`

This is suitable for sharing with designers/contractors as static deliverables.
Round-2 annotations are included by default:
- window symbols (`WIN:`)
- dimension chains (`DIM:`)
- material legend (`LEGEND:`)
- elevation index (`ELEV:A-A`, `ELEV:B-B`)
- north arrow (`N↑`)

Default export mode uses `baseline` candidate mapping (closer to original floor plan intent).
To export heuristic best-score mapping instead:

```bash
python scripts/export_top1_svgs.py --selection best
```

## Output for Step 6

After running `export_print_bundle_pdf.py`, you'll get:

- `structured/candidates/print_bundle.pdf`

By default, this PDF is exported in A3 landscape and includes:
- cover page
- table of contents
- one floor layout per page (from `structured/candidates/svg/manifest.json`)

Optional arguments:
- `--paper a4` to output A4 landscape
- `--output <path>` to change destination file
- `--manifest <path>` to use a different SVG manifest

## Quality Gate

You can run validation manually:

```bash
python scripts/validate_layout_bundle.py
```

Checks include:
- `room_program.json` metadata / notes coverage
- exported SVG file existence
- required drawing markers (`ENT`, `DW:`, `WIN:`, `DIM:`, `LEGEND:`, `ELEV:`)

## Shared Defaults Config

Default assumptions are centralized in:

- `scripts/config/residential_defaults_tw.json`

This file drives:
- wall / door / furniture defaults
- px-per-mm conversion
- drawing validation markers

## Improve Precision from Source HTML

You can make final SVG/PDF much closer to real drawings by adding geometry attributes in original HTML.

Supported attributes:
- floor: `.floor-plan`
  - `data-floor-width-mm`, `data-floor-depth-mm`, `data-north-deg`, `data-geometry-source`
- plan cell: `.plan-cell`
  - `data-x-mm`, `data-y-mm`, `data-w-mm`, `data-h-mm`
  - `data-door-mm`, `data-window-mm`
  - `data-entry="true"` for main entrance
  - `data-material` (optional material hint)
- room: `.room`
  - `data-x-mm`, `data-y-mm`, `data-w-mm`, `data-h-mm`
  - `data-target-cell="slot-<n>"` (optional binding hint)

Example:

```html
<div class="floor-plan" id="floor-1" data-floor-width-mm="11000" data-floor-depth-mm="7800" data-north-deg="0">
  <div class="plan-cell" data-x-mm="3600" data-y-mm="1200" data-w-mm="7400" data-h-mm="1300"
       data-door-mm="900" data-window-mm="1800">...</div>
</div>
```

When all cells on a floor provide `x/y/w/h` (mm), export enters `blueprint-precise-mm` mode.

## Prompt Templates

For daily HTML-design revisions that must convert to realistic plan drawings, use:

- `scripts/WEB_TO_PLAN_PROMPTS.zh-TW.md`
- `scripts/WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md`

This pack includes:
- single master prompt for end-to-end execution
- fixed failure response format
- fallback prompt when slash command is unavailable

## Troubleshooting

### 1) Rule citation issue (`citation_issues`)

Symptom:
- `report.json` shows `citation_issues`

Meaning:
- A `critical` rule is missing one or more of:
  - `source_doc`
  - `source_article`
  - `source_url`

Fix:
- Update the rule file under `scripts/rules/*.yaml`.
- Without full citations, that critical rule cannot become a hard gate.

### 2) IFC signoff missing

Symptom:
- `run_full_expert_workflow.ps1 -Mode ifc` fails before/after pipeline

Fix:
- Create `structured/expert_review/signoff.yaml` from `structured/expert_review/signoff.template.yaml`
- Set:
  - `decision: approved`
  - reviewer metadata and `related_report_hash`

### 3) HTML mapping mismatch (`highlightRoom` / `room-id`)

Symptom:
- `html_consistency.json` contains `ROOM_TARGET_MISMATCH`

Fix:
- Ensure each `onclick="highlightRoom('xxx', this)"` matches `id="room-xxx"`.
- Keep DOM skeleton unchanged:
  - `.floor-plan > .plan-grid-visual > .plan-row > .plan-cell`

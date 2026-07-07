# House Design Workflow Optimization Design

## Context

This repository is a Taiwan residential design preparation toolchain for three self-build houses: A, B, and C. The current production input is the canonical HTML set:

- `AbuildingView.html`
- `BbuildingView.html`
- `CbuildingView.html`
- `storage.html`

The current pipeline is already useful and should be preserved. It converts HTML floor-plan pages into structured JSON, builds a room program, runs advisory architect metrics, generates layout candidates, exports SVG/PDF bundles, and produces canonical-first final discussion HTML.

The recommended improvement scope is limited to workflow reliability and data quality. It does not change the actual house layout decisions, room placement, or visual design content unless a later task explicitly addresses those files.

## Problem Summary

The current flow passes the latest hard gate, but it still has quality and maintainability risks:

- `evaluate_expert_gates.py` treats `gate`, `report`, and `full` nearly the same after `normalize`, so preflight gate and final reporting are not clearly separated.
- IFC mode can run `validate_layout_bundle.py` twice: once inside `run_full_pipeline.ps1`, then again in `run_full_expert_workflow.ps1`.
- The latest `html_consistency.json` has 33 warnings, including `WINDOW_RANGE`, `ENTRY_COUNT`, `CELL_OVERLAP`, and `ROOM_TARGET_MISMATCH`.
- Some warnings are noisy for legitimate outdoor spaces, such as balconies or terraces with `data-window-mm="0"`.
- Directional semantics are under-specified. For example, A building 2F `高雄厝陽台` has geometry and `outdoor` class, but no explicit field saying whether it is front, rear, side, planting, or service balcony.
- Claude Code settings and MCP config are broad or unpinned, which weakens repeatability.
- Python dependency and test setup are not explicit.

## Goals

1. Make Claude Code workflow execution predictable and easier to audit.
2. Separate preflight gate behavior from final report behavior.
3. Reduce false-positive warnings without hiding real design issues.
4. Add structured direction and outdoor-space metadata so front/rear/side balcony questions can be answered from data rather than inferred from labels.
5. Add a small test/verification foundation for the pipeline scripts.
6. Keep existing successful outputs and slash commands compatible.

## Non-Goals

- Do not redesign A/B/C house layouts.
- Do not automatically move rooms between cells.
- Do not replace the current HTML-first workflow.
- Do not introduce a full BIM, CAD, or 3D modeling stack.
- Do not refactor the large SVG renderer unless required by the focused changes.

## Recommended Approach

Implement the work in two phases.

### Phase A: Workflow Stabilization

Tighten the command and script layer without changing design semantics.

Key changes:

- Make `evaluate_expert_gates.py --stage gate` perform preflight-only behavior:
  - write report JSON/MD as today for auditability,
  - do not update `task-board.md`,
  - return exit code `10` on hard gate failure,
  - print concise gate summary.
- Keep `--stage report` as the final reporting stage:
  - write report JSON/MD,
  - update `task-board.md`,
  - include artifacts from the completed pipeline.
- Keep `--stage full` as a convenience path for direct manual execution.
- Avoid duplicate validation in IFC mode by making the outer expert workflow skip the second validation when the inner pipeline already ran it, or by passing a flag that makes validation ownership explicit.
- Add dependency metadata:
  - `requirements.txt` for runtime dependencies.
  - optional `requirements-dev.txt` for test dependencies.
- Update `.gitignore` for Python cache, local env files, and generated cache noise.
- Keep already tracked structured deliverables untouched unless a later cleanup task explicitly changes version-control policy.

### Phase B: Data Quality and Directional Schema

Add explicit metadata to canonical HTML and propagate it through extraction and reports.

Supported new attributes:

- On `.floor-plan`:
  - `data-front-side="top|right|bottom|left"`
  - `data-rear-side="top|right|bottom|left"`
  - `data-site-orientation-note="..."` for human-readable context.
- On `.plan-cell`:
  - `data-zone="front|rear|side|core|service|roof|unknown"`
  - `data-outdoor-role="balcony|kaohsiung-house-balcony|terrace|side-yard|garage|service-yard|roof-platform|planting|utility|none"`
  - `data-facing="front|rear|left|right|side|roof|internal|unknown"`

Propagation:

- `extract_layout_data.py` reads the new attributes into structured floor and cell records.
- `build_room_program.py` carries them into `room_program.json`.
- `check_html_consistency.py` uses them to classify warnings.
- `export_final_design_html.py` includes them in metadata payloads.
- SVG/PDF output can remain visually unchanged in the first implementation, but the manifest should preserve the metadata when practical.

Warning policy updates:

- `WINDOW_RANGE` should not warn for outdoor spaces whose role does not require a window, such as balconies, side yards, garages, roof platforms, terraces, and service yards.
- `ENTRY_COUNT` should distinguish ground-floor main entries from upper-floor stair/landing entries. Missing upper-floor `data-entry` should be warning or info depending on the floor role, not a generic warning with the same wording as 1F.
- `CELL_OVERLAP` should remain warning in concept/draft, but IFC mode should be able to treat selected overlap categories as critical.
- `ROOM_TARGET_MISMATCH` should remain a warning in concept/draft and should be promoted for IFC if it affects exported canonical discussion HTML.

## A Building 2F Directional Handling

The current A building 2F floor has:

- floor geometry: `width_mm=11000`, `depth_mm=5200`, `north_deg=0`
- `高雄厝陽台`: `x=5500`, `y=3500`, `w=5500`, `h=1700`
- approximate area: `9.35 m2`
- approximate floor envelope area: `57.2 m2`
- approximate share: `16.3%`

Because the HTML currently says `⬆️ 前：採光面` and the balcony is located at the lower/right portion of the visual grid, the system can only infer its front/rear relationship. The optimization should make this explicit by adding metadata such as:

```html
data-zone="rear"
data-facing="rear"
data-outdoor-role="kaohsiung-house-balcony"
```

The exact values should be confirmed against the intended site orientation before editing the canonical HTML. The pipeline should support the metadata first, then the A/B/C HTML can be annotated in a later focused pass.

## Architecture

The existing pipeline stays intact:

```text
canonical HTML
  -> extract_layout_data.py
  -> build_room_program.py
  -> evaluate_architect_metrics.py
  -> generate_layout_candidates.py
  -> render_candidate_viewer.py
  -> export_top1_svgs.py
  -> export_print_bundle_pdf.py
  -> validate_layout_bundle.py
  -> evaluate_expert_gates.py --stage report
  -> export_final_design_html.py
```

The improvement adds a small shared metadata contract:

```text
HTML data-* attributes
  -> structured/*.structured.json
  -> structured/room_program.json
  -> consistency/report/final-html metadata
```

The main script contracts remain CLI-first and PowerShell-compatible.

## Files Expected To Change

Phase A:

- `.gitignore`
- `requirements.txt`
- `requirements-dev.txt`
- `scripts/evaluate_expert_gates.py`
- `scripts/run_full_expert_workflow.ps1`
- `scripts/run_full_pipeline.ps1`
- `Docs/claude-code-usage.md`
- `scripts/README.md`

Phase B:

- `scripts/extract_layout_data.py`
- `scripts/build_room_program.py`
- `scripts/check_html_consistency.py`
- `scripts/export_final_design_html.py`
- `scripts/config/residential_defaults_tw.json`
- focused test files under `tests/`

Optional later annotation pass:

- `AbuildingView.html`
- `BbuildingView.html`
- `CbuildingView.html`

## Testing Strategy

Add focused tests before changing behavior:

- Unit tests for parsing new floor/cell metadata from minimal HTML snippets.
- Unit tests for carrying metadata through `build_room_program.py`.
- Consistency tests proving outdoor balconies with `data-window-mm="0"` do not produce false `WINDOW_RANGE` warnings.
- Consistency tests proving real indoor rooms with invalid window dimensions still warn.
- Gate-stage tests proving `--stage gate` does not update `task-board.md`.
- Workflow smoke check:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode concept `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

For final verification after implementation, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode ifc `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

## Risks

- Tightening gate semantics may change `task-board.md` update timing. This is intended, but it must be documented.
- Reducing noisy warnings must not suppress real indoor-room issues.
- Directional metadata can be wrong if site orientation is assumed instead of confirmed. The pipeline should support metadata before applying it broadly.
- Existing generated artifacts are tracked in git. Implementation should avoid unnecessary churn in `structured/` unless the task explicitly regenerates outputs.

## Acceptance Criteria

- Existing slash commands remain documented and usable.
- `--stage gate` and `--stage report` have distinct behavior.
- IFC validation is not redundantly run by default.
- New directional/outdoor metadata is parsed and preserved through structured outputs.
- Balcony/terrace/service-yard `data-window-mm="0"` no longer causes irrelevant window warnings.
- Indoor invalid window data still reports warnings.
- A concept-mode full expert workflow completes successfully.
- The design does not change room placements or canonical visible layout.

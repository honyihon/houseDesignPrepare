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
- Exit-code semantics are implicit. `10` is already used for hard-gate failure, but the contract is not documented across Python, PowerShell, and slash-command usage.
- Generated `structured/` artifacts are tracked in git, so any metadata schema change must explicitly decide whether regenerated outputs are part of the same change.

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
- Avoid duplicate validation with an explicit validation ownership flag. Do not infer whether validation ran from filesystem timestamps or existing artifacts.
- Add dependency metadata:
  - `requirements.txt` for runtime dependencies.
  - `requirements-dev.txt` for test dependencies.
- Update `.gitignore` for Python cache, local env files, and generated cache noise.
- Pin project MCP server package versions instead of using `@latest`, unless the implementation plan records a reason to keep a moving target.
- Narrow `.claude/settings.local.json` permissions to the documented commands needed by this workflow.
- Keep already tracked structured deliverables untouched unless a later cleanup task explicitly changes version-control policy.

### Process Contracts

#### Exit Codes

All scripts and wrappers that participate in the workflow must preserve these exit-code meanings:

| Exit code | Meaning | Producer | Wrapper behavior |
|---:|---|---|---|
| `0` | Successful completion | Python scripts, PowerShell scripts | Continue to next step |
| `1` | Unexpected runtime error or uncaught exception | Python / PowerShell runtime | Stop workflow and report failed stage |
| `2` | Validation, consistency, or argument-level failure that is not a hard gate | `check_html_consistency.py`, `validate_layout_bundle.py`, argparse-style failures | Stop workflow and report failed stage |
| `10` | Expert hard gate failed with eligible critical failure | `evaluate_expert_gates.py`, `run_full_expert_workflow.ps1` | Stop workflow, preserve report files, print retry guidance |

`run_full_expert_workflow.ps1` must not convert exit code `10` into a generic exception. It should surface it as an expected hard-gate stop so Claude Code and manual PowerShell users see the same meaning.

`check_html_consistency.py` must keep the current threshold semantics unless the implementation plan explicitly changes them:

- `critical > 0` returns exit code `2`.
- `warning > 0` with `critical = 0` returns exit code `0`.
- `info > 0` with `critical = 0` returns exit code `0`.

This keeps concept/draft workflows usable while still allowing warning counts to be reported and reduced over time.

#### Validation Ownership

Use an explicit validation ownership contract:

- `run_full_pipeline.ps1` receives `-ValidationOwner inner|outer|none`.
- Default for direct pipeline execution: `inner`.
- Default when called from `run_full_expert_workflow.ps1`: `outer`.
- `run_full_expert_workflow.ps1` must pass `-ValidationOwner outer` explicitly when invoking `run_full_pipeline.ps1`; the inner script must not infer ownership from its caller.
- `inner`: the pipeline runs `validate_layout_bundle.py` when `Mode=ifc`.
- `outer`: the pipeline does not run validation; the expert workflow runs validation exactly once after the pipeline.
- `none`: validation is skipped only for targeted developer/debug commands, not for documented release workflows.

Failure propagation:

- If the owner runs validation and it exits non-zero, the owner exits non-zero immediately.
- The non-owner must not re-run validation as a fallback because that can hide ownership bugs and duplicate report noise.

#### Task Board Compatibility

Changing `--stage gate` so it no longer updates `task-board.md` intentionally changes the stage contract. The implementation plan must check for current consumers before changing behavior:

- repository scripts,
- docs and slash-command prompts,
- any local dashboard or manual workflow described in `Docs/` or `task-board.md`.

If no consumer depends on gate-time task-board updates, document the new contract in `Docs/claude-code-usage.md` and `scripts/README.md`.

### Phase B: Data Quality and Directional Schema

Add explicit metadata to canonical HTML and propagate it through extraction and reports.

Coordinate-system contract:

- `top|right|bottom|left` always means the HTML visual grid coordinate system.
- `x_mm` increases left to right in the visual grid.
- `y_mm` increases top to bottom in the visual grid.
- `data-front-side` and `data-rear-side` are visual-grid sides, not geographic directions.
- `data-north-deg` remains the geographic orientation input.
- Geographic conversion is computed by the pipeline from visual-grid side plus `north_deg`; humans should not encode the same relationship twice in free text.
- `data-site-orientation-note` is explanatory text only and must not be used as the source of truth for validation.
- Side detection for consistency checks uses the visual-grid geometry. For a cell, compute the centroid `(x_mm + w_mm / 2, y_mm + h_mm / 2)` and compare distance to the declared front/rear side. If the nearest-side difference is less than 10% of the relevant floor dimension, or if the cell spans more than 70% of that dimension, the cell is considered ambiguous and no direction-conflict warning is emitted.

Supported new attributes:

- On `.floor-plan`:
  - `data-front-side="top|right|bottom|left"`
  - `data-rear-side="top|right|bottom|left"`
  - `data-site-orientation-note="..."` for human-readable context.
- On `.plan-cell`:
  - `data-zone="front|rear|side|core|service|roof|unknown"`
  - `data-outdoor-role="balcony|kaohsiung-house-balcony|terrace|side-yard|garage|service-yard|roof-platform|planting|utility|none"`
  - `data-facing="front|rear|left|right|side|roof|internal|unknown"`

Schema meaning:

- `data-zone` describes where the cell sits in the plan.
- `data-facing` describes the primary opening, view, or exposure direction.
- `data-outdoor-role` describes whether the cell is outdoor-like and what kind of outdoor space it is.
- `data-zone` and `data-facing` may differ. Example: a cell can be in the `core` zone but face `front` through an opening.
- `data-outdoor-role="none"` means the cell is treated as indoor for window validation unless another explicit class or rule says otherwise.
- Prefer `left` or `right` over `side` when the side can be determined from the visual-grid coordinate system. Use `side` only when the design intentionally says "side-facing" but the left/right side is unknown, not relevant, or not yet confirmed.
- `data-zone="side"` has the same convention: use it only when a cell is side-zone but left/right attribution is not yet known or not worth modeling.

Propagation:

- `extract_layout_data.py` reads the new attributes into structured floor and cell records.
- `build_room_program.py` carries them into `room_program.json`.
- `check_html_consistency.py` uses them to classify warnings.
- `export_final_design_html.py` includes them in metadata payloads.
- SVG/PDF output can remain visually unchanged in the first implementation, but the manifest should preserve the metadata when practical.

Warning policy updates:

- `WINDOW_RANGE` should be based on indoor/outdoor classification, not an ever-growing blacklist of outdoor role names.
- `ENTRY_COUNT` should distinguish ground-floor main entries from upper-floor stair/landing entries. Missing upper-floor `data-entry` should be warning or info depending on the floor role, not a generic warning with the same wording as 1F.
- `CELL_OVERLAP` should remain warning in concept/draft, but IFC mode should be able to treat selected overlap categories as critical.
- `ROOM_TARGET_MISMATCH` should remain a warning in concept/draft and should be promoted for IFC if it affects exported canonical discussion HTML.

The role-to-opening and severity policy should live in `scripts/config/residential_defaults_tw.json`, not as hard-coded scattered lists. At minimum, the config should define:

- outdoor-like roles for window validation,
- roles that normally require openings,
- IFC promotion categories for overlap and room-target issues.

Window warning matrix:

| Space classification | `data-window-mm` state | Expected result |
|---|---|---|
| Outdoor-like: `data-outdoor-role != "none"` or explicit outdoor class | `0` | No warning |
| Outdoor-like: `data-outdoor-role != "none"` or explicit outdoor class | Missing | No warning; optional info only if the role normally needs an opening |
| Indoor: `data-outdoor-role="none"` or no outdoor signal | Valid value inside configured range | No warning |
| Indoor: `data-outdoor-role="none"` or no outdoor signal | `0` or out of range | Warning |
| Indoor: `data-outdoor-role="none"` or no outdoor signal | Missing | Warning for possible missing metadata |

Directional consistency checks:

- If `data-front-side` and `data-rear-side` are equal, report warning.
- If a cell has `data-facing="front"` but its geometry is closest to the declared rear side, report info in concept/draft and warning in IFC.
- If a cell has `data-facing="rear"` but its geometry is closest to the declared front side, report info in concept/draft and warning in IFC.
- If `data-zone` and `data-facing` differ, do not warn by default. Only warn when the geometry contradicts both values or when the pair is explicitly impossible under configured rules.
- If `data-site-orientation-note` contradicts structured attributes, structured attributes win and the note receives an info-level consistency issue.

IFC promotion policy:

- Promotion from warning to critical must be deterministic and category-based.
- The default promotion set must be empty or limited to categories verified to produce zero critical issues on the current checked-in A/B/C baseline, unless the same implementation also fixes the affected source data.
- Before enabling a promotion category, run the consistency check against A/B/C and record the resulting critical count in the implementation summary.
- IFC smoke success remains `summary.critical=0`; do not redefine success as "current known critical baseline" inside this workflow optimization.
- Example promotion categories may include geometry overlaps between two indoor rooms and room-target mismatches that affect exported canonical discussion HTML. Outdoor overlap or decorative/service annotation overlap should stay warning or info unless configured otherwise.

Structured output regeneration policy:

- The schema changes are backward compatible. Missing directional/outdoor metadata must default to `unknown` or `none` without breaking existing artifacts.
- When extraction starts emitting the new metadata fields, bump the structured extraction schema from `house-design-structured-v2` to `house-design-structured-v3` and update downstream `source_schema_version` handling. Downstream scripts must read both v2 and v3 during migration.
- Phase B implementation should not regenerate all tracked `structured/` artifacts in the same commit as parser/checker changes.
- After parser/checker behavior is reviewed, run a separate regeneration commit if the team wants checked-in outputs to include the new metadata.
- The regeneration commit must include a short summary of expected churn: files changed, warning-count change, and whether SVG/PDF visual output changed.

Storage scope:

- `storage.html` remains a canonical extraction input.
- Because current `storage.html` produces `storage_zones` and no `plan_cells`, Phase B directional cell metadata does not apply to it by default.
- If storage later gains a plan-cell layout, it should use the same metadata contract.
- Storage-zone metadata can be added later as a separate, narrower enhancement; do not block Phase B on storage-zone direction modeling.

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
  -> export_print_bundle_pdf.py       [draft/ifc only]
  -> validate_layout_bundle.py        [owner-controlled; required for ifc]
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
- `.mcp.json`
- `.claude/settings.local.json`
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
- `storage.html` only if it later gets plan-cell layout metadata or a separate storage-zone metadata contract

## Testing Strategy

Add focused tests before changing behavior:

- Unit tests for parsing new floor/cell metadata from minimal HTML snippets.
- Unit tests for carrying metadata through `build_room_program.py`.
- Consistency tests proving outdoor balconies with `data-window-mm="0"` do not produce false `WINDOW_RANGE` warnings.
- Consistency tests proving outdoor spaces with missing `data-window-mm` do not warn unless configured for that role.
- Consistency tests proving real indoor rooms with invalid window dimensions still warn.
- Consistency tests proving real indoor rooms with missing `data-window-mm` warn.
- Consistency tests for `data-front-side`, `data-rear-side`, `data-zone`, and `data-facing` contradictions.
- Gate-stage tests proving `--stage gate` does not update `task-board.md`.
- Exit-code tests or smoke checks proving hard-gate failure preserves exit code `10` through PowerShell.
- Validation ownership tests proving IFC mode runs `validate_layout_bundle.py` exactly once in the documented workflow.
- Validation ownership tests proving `-ValidationOwner none` skips validation only when explicitly requested.
- Negative validation ownership tests proving the non-owner does not rerun validation after an owner failure.
- Consistency exit-code tests proving warning-only reports exit `0` and critical reports exit `2`.
- Workflow smoke check:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode concept `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

Concept-mode smoke success means:

- command exits `0`,
- `structured/expert_review/report.json` exists,
- `structured/expert_review/report.md` exists,
- `structured/candidates/viewer.html` exists,
- `structured/final_design_html/index.html` exists,
- no PDF is required because concept mode skips PDF export.

For final verification after implementation, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode ifc `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

IFC smoke success means:

- command exits `0`,
- `structured/expert_review/report.json` has `hard_gate="pass"`,
- `structured/expert_review/html_consistency.json` has `summary.critical=0`,
- `structured/candidates/svg/manifest.json` exists,
- `structured/candidates/print_bundle.pdf` exists,
- `structured/final_design_html/index.html` exists.

## Risks

- Tightening gate semantics may change `task-board.md` update timing. This is intended, but it must be documented.
- Reducing noisy warnings must not suppress real indoor-room issues.
- Directional metadata can be wrong if site orientation is assumed instead of confirmed. The pipeline should support metadata before applying it broadly.
- Existing generated artifacts are tracked in git. Implementation should avoid unnecessary churn in `structured/` unless the task explicitly regenerates outputs.
- Pinning MCP packages improves repeatability but may require periodic manual updates.
- Narrowing Claude Code permissions can break undocumented local commands. Keep the documented workflow commands allowed and mention removed broad permissions in the implementation summary.

## Acceptance Criteria

- Existing slash commands remain documented and usable.
- `--stage gate` and `--stage report` have distinct behavior.
- Exit codes are documented and preserved through Python and PowerShell wrappers.
- IFC validation ownership is explicit and the documented workflow runs validation exactly once.
- New directional/outdoor metadata is parsed and preserved through structured outputs.
- Outdoor-like `data-window-mm="0"` no longer causes irrelevant window warnings.
- Indoor invalid or missing window data still reports warnings.
- Coordinate-system semantics for visual grid, front/rear side, and `north_deg` are documented.
- The implementation either avoids `structured/` regeneration or uses a separate regeneration commit with expected-churn summary.
- A concept-mode full expert workflow meets the smoke success criteria.
- The design does not change room placements or canonical visible layout.

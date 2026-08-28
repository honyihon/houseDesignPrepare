# House Design Data Governance Design

> **歷史規格（2026-08-27 已被新版圖面檢核架構取代）。** 本文的 Current Baseline 只代表 2026-07-10 當時的 HTML pipeline 狀態；現行資料權威請見 `CLAUDE.md`、`inputs/project.json` 與 `structured/reviews/`。

## Goal

把目前已能通過 `concept`、`draft`、`ifc` 的三棟住宅設計 workflow，往下一層資料治理收斂：補齊 canonical HTML 與 structured outputs 之間的房間對應、方向語意、長輩/無障礙標記、signoff 可追溯性，以及出圖產物版本控管。

這一輪目標不是重畫 A/B/C 棟格局，而是讓既有格局能被流程更可靠地讀懂、檢查、追蹤與交付。

## Current Baseline

2026-07-10 盤點結果：

- `python -m pytest tests -q`: 52 passed.
- `python scripts/validate_layout_bundle.py`: 0 errors / 0 warnings.
- `run_full_expert_workflow.ps1 -Mode concept`: exit 0，約 14 秒。
- `run_full_expert_workflow.ps1 -Mode draft`: exit 0，約 33 秒，PDF 12 pages / failures 0。
- `run_full_expert_workflow.ps1 -Mode ifc`: exit 0，約 33 秒，hard gate pass。
- `structured/expert_review/html_consistency.json`: critical 0 / warning 3 / info 9。
- `structured/expert_review/report.json`: hard_gate pass，warnings 3，citation_issues 0。
- `structured/architect_metrics/metrics.json`: ok 81 / advisory 27 / missing_data 8 / professional_required 17。

Remaining HTML consistency warnings:

- A `floor-3`: `WINDOW_RANGE`，`娛樂室/家庭劇院 data-window-mm=0`。
- C `floor-1`: `ROOM_TARGET_MISMATCH`，`garage/entrance/living/dining/kitchen` 沒有對應 detail room。
- C `floor-4`: `ROOM_TARGET_MISMATCH`，`stair-rf/riser-rf/platform/laundry-rf` 沒有對應 detail room。

Important observed data gaps:

- A/B/C floor orientation currently extracts as `front_side=unknown` and `rear_side=unknown`.
- A/B/C cells mostly lack explicit `data-zone`, `data-facing`, and `data-outdoor-role`.
- A 2F `高雄厝陽台` is geometrically bottom-right in the HTML visual grid: `x=5500`, `y=3500`, `w=5500`, `h=1700`, area `9.35m2`, about `16.3%` of the 2F envelope. Current workflow cannot determine whether it is front/rear without explicit metadata.
- A building still fails the accessibility advisory matcher because no A-cell matches `無障礙` or `孝親`.
- Running `draft` / `ifc` can create large tracked-output churn in `structured/candidates/svg/` when selection changes from strategy-named SVG files to `baseline` SVG files.
- Existing `structured/expert_review/signoff.yaml` can allow IFC mode to pass even if it was written for an older report summary.

## Scope

### 1. C Building Room Detail Completion

Add missing detail room blocks for C building cells that currently have `highlightRoom(...)` targets but no matching `id="room-..."` detail block:

- C 1F:
  - `garage`
  - `entrance`
  - `living`
  - `dining`
  - `kitchen`
  - `service` if the visual cell remains `後工作陽台` with `onclick="highlightRoom('service', this)"`.
- C RF:
  - `stair-rf`
  - `riser-rf`
  - `platform`
  - `laundry-rf`

Each new room block must include:

- `id="room-<target>"`
- `data-target-cell="slot-N"` matching the current visual cell order.
- `data-x-mm`, `data-y-mm`, `data-w-mm`, `data-h-mm` matching the current cell geometry.
- A short detail list describing the design intent already implied by the visual cell.

This is a data-completeness pass only. It must not move cells, resize cells, or change visible room placement.

### 2. Direction and Outdoor Metadata Annotation

Add explicit coordinate metadata to canonical A/B/C floor plans and selected cells.

Floor-level metadata:

- `data-front-side="top|right|bottom|left"`
- `data-rear-side="top|right|bottom|left"`
- `data-site-orientation-note="..."` for human-readable context.

Cell-level metadata:

- `data-zone="front|rear|left|right|side|core|service|roof|unknown"`
- `data-facing="front|rear|left|right|side|roof|internal|unknown"`
- `data-outdoor-role="balcony|kaohsiung-house-balcony|terrace|side-yard|garage|service-yard|roof-platform|laundry-yard|equipment-yard|none"`
- Optional `data-room-role` for semantic roles such as `elder`, `accessible-bath`, `shrine`, `equipment`, `mechanical`, `service`, `circulation`.
- Optional `data-accessible="true"` for rooms or cells intentionally designed for wheelchair/elder use.

Coordinate contract:

- `top/right/bottom/left` always means the HTML visual grid, not geographic north.
- `data-north-deg` remains geographic orientation.
- `data-site-orientation-note` is explanatory text only; structured attributes are the source of truth.
- If direction is not confirmed by the owner or architect, keep it `unknown` and emit a review item instead of guessing.

Initial priority annotations:

- A 2F `高雄厝陽台`: mark outdoor role and direction after confirming whether the bottom-right visual zone is intended as front or rear.
- A 1F `多功能房/客房`: if it is intended to become elder room, annotate `data-room-role="elder"` and accessibility intent.
- A 1F `1F 公用衛浴`: if it is intended as elder/accessible bath, annotate `data-room-role="accessible-bath"` and `data-accessible="true"`.
- C 1F `孝親房` and `孝親衛浴`: annotate elder/accessibility roles explicitly.
- C side yard, balconies, RF platform, RF laundry: annotate outdoor role.
- B 1F shrine and worship-related support spaces: annotate `data-room-role="shrine"` or service roles where useful for future checks.

### 3. Consistency and Metrics Policy Updates

Update validation behavior so the new metadata has practical value.

HTML consistency:

- `ROOM_TARGET_MISMATCH` remains warning in concept/draft and should be clean for the canonical A/B/C baseline after C detail completion.
- `WINDOW_RANGE` should distinguish:
  - indoor room with `data-window-mm=0`: warning.
  - deliberately dark room such as home theater with `data-room-role="theater"` or `data-daylight-required="false"`: no generic window warning; emit an info-level confirmation item instead.
  - outdoor-like cells with `data-outdoor-role != "none"`: no window warning for `0` or missing window metadata.
- Direction checks should report unresolved `front_side/rear_side` as info, and contradictions as warning.

Expert gate:

- A building accessibility warning should be resolved by explicit A 1F elder/accessibility annotations, not by adding broad fuzzy keywords.
- Keep advisory metrics non-hard-gate unless a future implementation explicitly promotes a category.

Architect Metrics:

- Convert the top advisory output into a clearer action list grouped by professional owner:
  - architect/daylight-ventilation,
  - accessibility/door-width,
  - structural/RF equipment and exercise vibration,
  - MEP/RF equipment, drainage, water pressure, heat pump,
  - owner decision/open design preference.
- Missing-data metrics should point to exact missing metadata fields when possible.

### 4. IFC Signoff Traceability

`structured/expert_review/signoff.yaml` must not be a reusable evergreen pass.

Add or require:

- `related_report_hash`
- `related_report_generated_at`
- `reviewer_role`
- `reviewer_name`
- `reviewer_date`
- `decision`

IFC mode should:

- read the latest report hash generated before final signoff validation,
- fail with exit code `2` if `related_report_hash` is missing or does not match the current report,
- allow `approved`, `pass`, or `approved_with_conditions` only when the hash matches,
- keep report files for audit even on signoff mismatch.

The expected release flow is two-pass when the report content changes:

1. Run IFC workflow to regenerate the latest report and report hash.
2. If signoff is missing or stale, the workflow exits `2` after preserving the report.
3. Reviewer updates `structured/expert_review/signoff.yaml` with the latest hash and decision.
4. Re-run IFC workflow; it passes only if the regenerated report hash still matches the signoff.

Developer/debug escape hatch:

- A direct script flag may allow `--allow-stale-signoff` only for local investigation.
- `/workflow-house-all-in-one` and documented release commands must not use that escape hatch.

### 5. Structured Output and SVG Churn Control

Current tracked outputs are useful as samples, but daily smoke runs should not create confusing file deletes and untracked replacement SVGs.

Recommended behavior:

- `export_top1_svgs.py` should either clean obsolete SVG files for the selected export set before writing, or write selection-specific outputs under stable subdirectories such as:
  - `structured/candidates/svg/baseline/`
  - `structured/candidates/svg/best/`
  - `structured/candidates/svg/debug/`
- `manifest.json` must record:
  - requested selection,
  - resolved selection,
  - drawing style,
  - output directory,
  - exported filenames.
- `validate_layout_bundle.py` should validate against the manifest, not against leftover SVG files.
- Regenerated `structured/` artifacts should be committed only in an intentional regeneration commit with a summary of expected churn.

### 6. Domain Review Checklist Export

Create a machine-readable review checklist from the current advisory reports and user priorities.

The checklist should include:

- A 2F Kaohsiung-house / `高雄厝` balcony direction confirmation.
- A whole-house low-cost cooling / air distribution research item.
- A RF typhoon protection item for solar shade canopy and rain exposure.
- A elder/accessibility 150cm turning-circle confirmation item for A/C 1F elder-use rooms and bathrooms.
- B shrine wall, beam, 2F wet-area overlay, exhaust, make-up air, and fire-material confirmation items.
- C side-yard clear width, 2F laundry waterproofing, 3F exercise vibration, and RF equipment anchoring items.

Output target:

- `structured/expert_review/domain_checklist.json`
- `structured/expert_review/domain_checklist.md`

These are owner/architect discussion artifacts. They must not claim legal, structural, daylight, ventilation, fire, or accessibility compliance.

## Non-Goals

- Do not redesign or relocate A/B/C rooms.
- Do not change the visible canonical layout except adding missing detail blocks and data attributes.
- Do not introduce BIM, CAD, 3D, HVAC simulation, or solar structural calculation tools.
- Do not turn advisory metrics into legal or professional compliance statements.
- Do not remove tracked `structured/` outputs as part of this change.
- Do not update external regulation interpretations without a separate source-verification pass.

## Proposed Architecture

Existing pipeline remains intact:

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

This change adds a data-governance layer:

```text
canonical HTML data-* annotations
  -> structured metadata
  -> consistency checks
  -> architect metrics action grouping
  -> expert report
  -> domain checklist
  -> final design HTML metadata
```

The canonical HTML remains the source of truth. `structured/` is regenerated output.

## Files Expected To Change

Canonical data annotations:

- `AbuildingView.html`
- `BbuildingView.html`
- `CbuildingView.html`

Script behavior:

- `scripts/extract_layout_data.py`
- `scripts/build_room_program.py`
- `scripts/check_html_consistency.py`
- `scripts/evaluate_architect_metrics.py`
- `scripts/evaluate_expert_gates.py`
- `scripts/export_top1_svgs.py`
- `scripts/export_print_bundle_pdf.py`
- `scripts/validate_layout_bundle.py`
- `scripts/export_final_design_html.py`
- `scripts/config/residential_defaults_tw.json`

Docs and tests:

- `Docs/claude-code-usage.md`
- `scripts/README.md`
- focused tests under `tests/`

Generated outputs, only in a separate regeneration commit if approved:

- `structured/*.json`
- `structured/expert_review/*`
- `structured/architect_metrics/*`
- `structured/candidates/*`
- `structured/final_design_html/*`

## Testing Strategy

Add tests before implementation changes.

Required focused tests:

- C 1F and RF no longer produce `ROOM_TARGET_MISMATCH`.
- Missing room detail blocks still produce `ROOM_TARGET_MISMATCH` on synthetic fixtures.
- A home-theater cell with `data-daylight-required="false"` does not produce generic `WINDOW_RANGE` warning.
- Indoor cell with `data-window-mm="0"` and no exemption still produces `WINDOW_RANGE`.
- Outdoor-like cell with `data-outdoor-role != "none"` and `data-window-mm="0"` does not warn.
- Extractor carries floor orientation and cell spatial metadata into structured JSON.
- `build_room_program.py` preserves room/cell semantic roles.
- Accessibility matcher recognizes explicit `data-accessible="true"` and `data-room-role="elder"` for A 1F.
- IFC signoff fails when `related_report_hash` is missing or stale.
- IFC signoff passes when the hash matches the latest report.
- SVG export does not leave obsolete selected-strategy files as untracked or deleted churn.
- `validate_layout_bundle.py` validates only manifest-listed SVG files.
- Domain checklist generation emits the required A/B/C review items without compliance claims.

Smoke tests:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode concept `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

IFC smoke requires a fresh signoff hash generated from the current report:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode ifc `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

## Risks

- Direction metadata can be wrong if filled by inference. The implementation must leave unknown values where the owner or architect has not confirmed direction.
- C detail completion can accidentally duplicate or contradict existing notes. Keep new blocks short and tied to existing visual-cell intent.
- Signoff hash enforcement changes current IFC convenience behavior. This is intended, but docs must show the new workflow clearly.
- SVG churn control touches tracked generated artifacts. Implementation commits must avoid mixing source changes with regeneration churn.
- A theater daylight exemption can hide a real ventilation issue if named too broadly. The exemption should be explicit with `data-daylight-required="false"`, not inferred from label alone.
- Domain checklist may grow noisy if every advisory is exported. The first version should focus on current high-value owner/architect questions.

## Acceptance Criteria

- Full tests pass.
- Concept and draft expert workflows exit 0.
- IFC workflow requires a matching fresh signoff hash.
- HTML consistency has `critical=0`.
- C 1F and C RF `ROOM_TARGET_MISMATCH` warnings are gone.
- A 3F theater window warning is either resolved with real window metadata or replaced by explicit daylight-exemption info.
- A accessibility warning is resolved through explicit elder/accessibility metadata, not broader fuzzy matching.
- A/B/C floor orientation metadata is present where confirmed; unconfirmed direction stays `unknown` with an info-level review item.
- A 2F Kaohsiung-house / `高雄厝` balcony report states its area, share, visual-grid location, and whether front/rear is confirmed or unresolved.
- Draft PDF generation still reports zero failures.
- Running the workflow does not leave unexpected deleted SVGs or untracked selected-strategy SVGs.
- `structured/expert_review/domain_checklist.md` gives owner/architect discussion items for A cooling/RF, B shrine/fire/smoke, and C elder/laundry/exercise/RF checks.
- The final implementation summary explicitly says which `structured/` artifacts were regenerated, or that regeneration was intentionally skipped.

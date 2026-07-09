# House Workflow Quality Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove known workflow false positives and preserve reliable, traceable PDF and expert-report output.

**Architecture:** Keep changes inside the existing consistency checker, rule engine, SVG exporter, PDF adapter, and metrics helper. Each behavior is introduced with a focused regression test before the minimum production change.

**Tech Stack:** Python 3.14, pytest 8, BeautifulSoup, ReportLab, svglib, PowerShell.

## Global Constraints

- Canonical A/B/C HTML geometry and room placement must not be redesigned.
- Do not add a PDF rendering dependency.
- Architect Metrics remain advisory and must not claim regulatory compliance.
- Keep generated `structured/` changes out of source-code commits.

---

### Task 1: Geometry tolerance and entry policy

**Files:**
- Modify: `scripts/check_html_consistency.py`
- Modify: `scripts/config/residential_defaults_tw.json`
- Modify: `scripts/evaluate_expert_gates.py`
- Modify: `scripts/rules/tw_building_regulations.yaml`
- Modify: `scripts/rules/tw_accessibility.yaml`
- Test: `tests/test_html_consistency_metadata.py`
- Create: `tests/test_expert_rule_policies.py`

**Interfaces:**
- `overlap(a, b, tolerance_mm=1.0) -> bool`
- `evaluate_entry_ground_floor(rule, ctx) -> tuple[bool, list[str]]`
- `evaluate_accessible_door_min(rule, ctx)` accepts `keywords` and legacy `keyword`

- [ ] **Step 1: Write failing overlap tests**

Add tests proving a 1 mm edge overlap returns no `CELL_OVERLAP`, while a 2 mm overlap still returns a warning.

- [ ] **Step 2: Run overlap tests and verify RED**

Run: `python -m pytest tests/test_html_consistency_metadata.py -q`

Expected: the 1 mm case fails because the current checker reports every positive overlap.

- [ ] **Step 3: Implement configurable overlap tolerance**

Add `geometry_overlap_tolerance_mm: 1.0` under `spatial_metadata`, pass it through `check_floor_geometry`, and require both overlap dimensions to exceed it.

- [ ] **Step 4: Run overlap tests and verify GREEN**

Run: `python -m pytest tests/test_html_consistency_metadata.py -q`

Expected: all tests pass.

- [ ] **Step 5: Write failing expert-rule policy tests**

Use small BeautifulSoup fixtures to prove:

```python
assert evaluate_entry_ground_floor(rule, ctx_with_missing_1f)[0] is False
assert evaluate_entry_ground_floor(rule, ctx_with_missing_2f)[0] is True
assert evaluate_accessible_door_min(
    {"keywords": ["無障礙", "孝親"], "min_mm": 800},
    ctx_with_named_elder_bath,
)[0] is True
```

- [ ] **Step 6: Run policy tests and verify RED**

Run: `python -m pytest tests/test_expert_rule_policies.py -q`

Expected: import or assertion failures because the ground-floor evaluator and keyword-array behavior do not exist.

- [ ] **Step 7: Implement entry and accessibility policy**

Add `entry_ground_floor` dispatch, restrict it with the existing ground-floor label helper, support `keywords`, full cell text, and `data-accessible`, then update the two YAML rules.

- [ ] **Step 8: Run policy and full tests**

Run: `python -m pytest tests/test_expert_rule_policies.py tests/test_html_consistency_metadata.py -q`

Expected: all tests pass.

- [ ] **Step 9: Commit**

```powershell
git add scripts/check_html_consistency.py scripts/config/residential_defaults_tw.json scripts/evaluate_expert_gates.py scripts/rules/tw_building_regulations.yaml scripts/rules/tw_accessibility.yaml tests/test_html_consistency_metadata.py tests/test_expert_rule_policies.py
git commit -m "fix: align geometry and entry policies"
```

### Task 2: PDF-compatible presentation hatches

**Files:**
- Modify: `scripts/export_top1_svgs.py`
- Modify: `scripts/export_print_bundle_pdf.py`
- Create: `tests/test_pdf_hatch_compatibility.py`

**Interfaces:**
- `room_fill_color(...)` returns a concrete color.
- `room_hatch_paths(x, y, width, height, kind, profile, drawing_style) -> str`
- `load_svg_drawing(path, font)` receives SVG without pattern URL fills.

- [ ] **Step 1: Write failing SVG compatibility test**

Generate hatch markup and assert presentation output contains `data-hatch-kind="bath"` but no `url(#p2-`.

- [ ] **Step 2: Run SVG test and verify RED**

Run: `python -m pytest tests/test_pdf_hatch_compatibility.py -q`

Expected: failure because presentation fills currently use pattern URLs.

- [ ] **Step 3: Implement explicit hatch paths**

Return configured solid room fills, generate bounded diagonal paths for bath/service and cross paths for outdoor, and append them immediately after each room rectangle.

- [ ] **Step 4: Run SVG test and verify GREEN**

Run: `python -m pytest tests/test_pdf_hatch_compatibility.py -q`

Expected: SVG compatibility test passes.

- [ ] **Step 5: Add PDF adapter regression test**

Create a temporary SVG containing generated bath hatch output, call `load_svg_drawing`, capture stderr, and assert `Can't handle color` is absent.

- [ ] **Step 6: Run PDF test and verify GREEN**

Run: `python -m pytest tests/test_pdf_hatch_compatibility.py -q`

Expected: all tests pass without stderr warnings.

- [ ] **Step 7: Commit**

```powershell
git add scripts/export_top1_svgs.py scripts/export_print_bundle_pdf.py tests/test_pdf_hatch_compatibility.py
git commit -m "fix: render presentation hatches in PDF"
```

### Task 3: Architect Metrics signal quality

**Files:**
- Modify: `scripts/lib/architect_metrics.py`
- Create: `tests/test_architect_metrics_quality.py`

**Interfaces:**
- `structure_trigger_text(room, cell) -> str`
- `build_structure_review_metric(...)` uses identity for triggering and notes for evidence.
- `summarize_metrics_payload(payload)` returns balanced, non-duplicated `top_issues`.

- [ ] **Step 1: Write failing trigger tests**

Prove a stair room whose notes mention RF returns no structure metric, while a room named `熱泵熱水器` returns one.

- [ ] **Step 2: Run trigger tests and verify RED**

Run: `python -m pytest tests/test_architect_metrics_quality.py -q`

Expected: note-only RF currently creates a metric.

- [ ] **Step 3: Implement identity-based triggering**

Remove generic `rf` and `設備` triggers, inspect room/cell names and optional `structural_review`, and continue using full notes only for review evidence.

- [ ] **Step 4: Run trigger tests and verify GREEN**

Run: `python -m pytest tests/test_architect_metrics_quality.py -q`

Expected: trigger tests pass.

- [ ] **Step 5: Write failing summary tests**

Create A/B/C metric fixtures and assert labels contain each UID once and the first summary window includes all represented buildings.

- [ ] **Step 6: Run summary tests and verify RED**

Run: `python -m pytest tests/test_architect_metrics_quality.py -q`

Expected: duplicated UID label and A-first bias fail assertions.

- [ ] **Step 7: Implement balanced summary**

Use `room_uid` directly, group issue strings by building, then round-robin sorted building queues up to 20 items.

- [ ] **Step 8: Run metrics and full tests**

Run: `python -m pytest tests/test_architect_metrics_quality.py -q`

Expected: all tests pass.

- [ ] **Step 9: Commit**

```powershell
git add scripts/lib/architect_metrics.py tests/test_architect_metrics_quality.py
git commit -m "fix: reduce architect metrics noise"
```

### Task 4: Traceable rule references and workflow verification

**Files:**
- Modify: `scripts/rules/interior_design.yaml`
- Modify: `scripts/rules/fengshui.yaml`
- Modify: `scripts/rules/tw_accessibility.yaml`
- Modify: `Docs/claude-code-usage.md`
- Create: `tests/test_rule_citations.py`

**Interfaces:**
- Rule packs contain no `example.com`.
- Accessibility rules use the official NLMA regulation page.

- [ ] **Step 1: Write failing citation test**

Load all rule packs and assert every `source_url` is non-placeholder and accessibility URLs use `https://www.nlma.gov.tw/`.

- [ ] **Step 2: Run citation test and verify RED**

Run: `python -m pytest tests/test_rule_citations.py -q`

Expected: placeholder URLs fail.

- [ ] **Step 3: Replace references and document policy**

Point accessibility rules to the official regulation page and project heuristics to the repository design checklist. Document that heuristic citations are project governance references, not legal authority.

- [ ] **Step 4: Run citation and full tests**

Run: `python -m pytest tests -q`

Expected: all tests pass.

- [ ] **Step 5: Run workflow smoke checks**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 -Request inputs/design_request.md -Mode concept -Buildings A,B,C -Selection auto -DrawingStyle presentation
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 -Request inputs/design_request.md -Mode draft -Buildings A,B,C -Selection auto -DrawingStyle presentation
python scripts/validate_layout_bundle.py
```

Expected:

- concept and draft exit 0;
- HTML consistency has no 1 mm overlap warning;
- expert report has no upper-floor entry warning;
- PDF stderr has no unsupported hatch-color warning;
- bundle validation has 0 errors and 0 warnings.

- [ ] **Step 6: Restore generated artifacts and commit source/docs only**

```powershell
git restore -- structured task-board.md
git add scripts/rules Docs/claude-code-usage.md tests/test_rule_citations.py Docs/superpowers
git commit -m "docs: make workflow rule references traceable"
```

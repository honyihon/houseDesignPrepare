# House Design Workflow Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the house design workflow contracts and add directional/outdoor metadata support without changing visible A/B/C house layouts.

**Architecture:** Add one shared metadata helper under `scripts/lib/` and let extraction, room-program normalization, consistency checks, and final HTML metadata consume it. Keep the existing HTML-first pipeline and PowerShell entrypoints, but make gate/report semantics, validation ownership, exit codes, and smoke criteria explicit.

**Tech Stack:** Python 3.12-compatible scripts, BeautifulSoup 4.14.3, ReportLab 4.4.10, svglib 1.6.0, pytest 8.x for tests, PowerShell orchestration, Claude Code project config, npm MCP packages pinned to `@playwright/mcp@0.0.77` and `@modelcontextprotocol/server-brave-search@0.6.2`.

## Global Constraints

- Do not redesign A/B/C house layouts.
- Do not automatically move rooms between cells.
- Do not replace the current HTML-first workflow.
- Do not introduce a full BIM, CAD, or 3D modeling stack.
- Do not refactor the large SVG renderer unless required by the focused changes.
- `top|right|bottom|left` always means the HTML visual grid coordinate system.
- `x_mm` increases left to right in the visual grid.
- `y_mm` increases top to bottom in the visual grid.
- `data-front-side` and `data-rear-side` are visual-grid sides, not geographic directions.
- `data-north-deg` remains the geographic orientation input.
- `data-site-orientation-note` is explanatory text only and must not be used as the source of truth for validation.
- `check_html_consistency.py`: `critical > 0` exits `2`; warning-only and info-only reports exit `0`.
- Expert hard-gate failures preserve exit code `10`.
- The documented expert workflow runs `validate_layout_bundle.py` exactly once.
- Do not stage generated `structured/` artifact churn in code-change commits. Use the final artifact regeneration task for generated outputs.

### Amendment 2026-08-06 — read-only massing viewer

`scripts/export_model_3d.py` produces `structured/candidates/model3d.html`, a
three.js massing viewer. This does **not** relax the "no BIM, CAD, or 3D modeling
stack" constraint above:

- It is read-only. Geometry is derived from `structured/room_program.json`, which
  remains the single source of truth; the viewer has no authoring, editing, or
  export-back path, and nothing downstream consumes it.
- It draws extruded plan cells, not building elements. There is no IFC entity
  model, no parametric objects, no boolean openings — door/window positions are
  painted as face patches for orientation only.
- three.js is vendored as a static asset under `assets/vendor/three/` and inlined
  into a single offline HTML file. No build step, no runtime dependency, no
  toolchain enters the pipeline.

Its purpose is spatial comprehension and, equally, provenance disclosure: the
"尺寸來源" mode renders auto-derived cells as wireframe so the ~82% of geometry
that is still a CSS-class guess is visible at a glance.

---

## File Structure

- Create `scripts/lib/spatial_metadata.py`: shared parsing, normalization, indoor/outdoor classification, window validation, nearest-side, and direction-conflict helpers.
- Create `tests/conftest.py`: test import path setup for root-level scripts and `scripts/lib`.
- Create `tests/test_spatial_metadata.py`: unit tests for the shared helper.
- Create `tests/test_extract_and_room_program_metadata.py`: tests for metadata propagation from HTML extraction to room program.
- Create `tests/test_html_consistency_metadata.py`: tests for window, direction, and exit-threshold behavior.
- Create `tests/test_workflow_contracts.py`: tests for stage behavior and generated command text where feasible.
- Modify `scripts/extract_layout_data.py`: bump structured schema to `house-design-structured-v3`; parse floor `orientation` and cell `spatial`.
- Modify `scripts/build_room_program.py`: accept v2/v3 structured input and preserve `orientation` and `spatial`.
- Modify `scripts/check_html_consistency.py`: use shared metadata helper, defaults config, mode-aware checks, and warning-only exit behavior.
- Modify `scripts/export_final_design_html.py`: include floor/cell metadata summaries in final HTML JSON payloads.
- Modify `scripts/config/residential_defaults_tw.json`: add `spatial_metadata` config.
- Modify `scripts/evaluate_expert_gates.py`: make `gate` and `report` task-board behavior distinct.
- Modify `scripts/run_full_pipeline.ps1`: add `-ValidationOwner inner|outer|none`.
- Modify `scripts/run_full_expert_workflow.ps1`: pass `-ValidationOwner outer`, preserve hard-gate exit `10`, and run validation once.
- Modify `.mcp.json`: pin MCP package versions.
- Modify `.claude/settings.local.json`: narrow permissions to documented workflow commands.
- Modify `.gitignore`: ignore Python cache, pytest cache, and local env files.
- Create `requirements.txt` and `requirements-dev.txt`.
- Modify `Docs/claude-code-usage.md` and `scripts/README.md`: document new contracts and commands.

---

### Task 1: Shared Spatial Metadata Helper

**Files:**
- Create: `scripts/lib/spatial_metadata.py`
- Create: `tests/conftest.py`
- Create: `tests/test_spatial_metadata.py`
- Create: `requirements-dev.txt`

**Interfaces:**
- Produces: `parse_floor_orientation(attrs: Mapping[str, Any]) -> dict[str, str]`
- Produces: `parse_cell_spatial(attrs: Mapping[str, Any], classes: Iterable[str]) -> dict[str, Any]`
- Produces: `is_outdoor_like(spatial: Mapping[str, Any], classes: Iterable[str]) -> bool`
- Produces: `window_issue_level(spatial: Mapping[str, Any], classes: Iterable[str], has_window_attr: bool, window_mm: int | None, min_mm: int, max_mm: int, opening_required_roles: Iterable[str] = ()) -> str`
- Produces: `nearest_declared_side(floor_width_mm: float | None, floor_depth_mm: float | None, rect: Mapping[str, float], front_side: str, rear_side: str, tolerance_ratio: float = 0.10, span_ratio: float = 0.70) -> dict[str, Any]`
- Consumes: no project-specific generated artifacts.

- [ ] **Step 1: Add dev dependency file**

Create `requirements-dev.txt` with:

```text
pytest>=8.0,<9.0
```

- [ ] **Step 2: Add pytest import setup**

Create `tests/conftest.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

for path in (ROOT, SCRIPTS):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)
```

- [ ] **Step 3: Write failing helper tests**

Create `tests/test_spatial_metadata.py`:

```python
from __future__ import annotations

from lib.spatial_metadata import (
    is_outdoor_like,
    nearest_declared_side,
    parse_cell_spatial,
    parse_floor_orientation,
    window_issue_level,
)


def test_parse_floor_orientation_normalizes_known_sides() -> None:
    orientation = parse_floor_orientation(
        {
            "data-front-side": "Top",
            "data-rear-side": "bottom",
            "data-site-orientation-note": " front faces road ",
        }
    )

    assert orientation == {
        "front_side": "top",
        "rear_side": "bottom",
        "site_orientation_note": "front faces road",
    }


def test_parse_floor_orientation_defaults_unknown_sides() -> None:
    orientation = parse_floor_orientation({"data-front-side": "street"})

    assert orientation["front_side"] == "unknown"
    assert orientation["rear_side"] == "unknown"
    assert orientation["site_orientation_note"] == ""


def test_parse_cell_spatial_prefers_explicit_values_and_outdoor_role() -> None:
    spatial = parse_cell_spatial(
        {
            "data-zone": "rear",
            "data-facing": "Side",
            "data-outdoor-role": "kaohsiung-house-balcony",
        },
        classes=["plan-cell", "outdoor"],
    )

    assert spatial == {
        "zone": "rear",
        "facing": "side",
        "outdoor_role": "kaohsiung-house-balcony",
        "is_outdoor_like": True,
    }


def test_outdoor_window_zero_is_not_a_warning() -> None:
    spatial = parse_cell_spatial({"data-outdoor-role": "balcony"}, classes=[])

    assert window_issue_level(spatial, [], True, 0, 300, 3600) == ""


def test_indoor_window_zero_is_warning() -> None:
    spatial = parse_cell_spatial({"data-outdoor-role": "none"}, classes=[])

    assert window_issue_level(spatial, [], True, 0, 300, 3600) == "warning"


def test_indoor_missing_window_is_warning() -> None:
    spatial = parse_cell_spatial({"data-zone": "core"}, classes=[])

    assert window_issue_level(spatial, [], False, None, 300, 3600) == "warning"


def test_outdoor_missing_window_is_not_a_warning() -> None:
    spatial = parse_cell_spatial({"data-outdoor-role": "terrace"}, classes=[])

    assert window_issue_level(spatial, [], False, None, 300, 3600) == ""


def test_nearest_declared_side_detects_front_and_rear() -> None:
    front = nearest_declared_side(
        11000,
        5200,
        {"x_mm": 1000, "y_mm": 200, "w_mm": 1000, "h_mm": 800},
        "top",
        "bottom",
    )
    rear = nearest_declared_side(
        11000,
        5200,
        {"x_mm": 7000, "y_mm": 4200, "w_mm": 1000, "h_mm": 800},
        "top",
        "bottom",
    )

    assert front["nearest_role"] == "front"
    assert front["ambiguous"] is False
    assert rear["nearest_role"] == "rear"
    assert rear["ambiguous"] is False


def test_nearest_declared_side_marks_large_spanning_cells_ambiguous() -> None:
    result = nearest_declared_side(
        11000,
        5200,
        {"x_mm": 0, "y_mm": 1000, "w_mm": 11000, "h_mm": 3600},
        "top",
        "bottom",
    )

    assert result["nearest_role"] == "unknown"
    assert result["ambiguous"] is True
```

- [ ] **Step 4: Run tests to verify they fail**

Run:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_spatial_metadata.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'lib.spatial_metadata'`.

- [ ] **Step 5: Implement shared helper**

Create `scripts/lib/spatial_metadata.py`:

```python
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

FLOOR_SIDES = {"top", "right", "bottom", "left"}
CELL_ZONES = {"front", "rear", "side", "core", "service", "roof", "unknown"}
CELL_FACING = {"front", "rear", "left", "right", "side", "roof", "internal", "unknown"}
OUTDOOR_ROLES = {
    "balcony",
    "kaohsiung-house-balcony",
    "terrace",
    "side-yard",
    "garage",
    "service-yard",
    "roof-platform",
    "planting",
    "utility",
}
OUTDOOR_CLASSES = {"outdoor", "garage", "terrace", "balcony", "side-yard"}


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_token(value: Any, allowed: set[str], default: str = "unknown") -> str:
    token = normalize_text(value).lower()
    return token if token in allowed else default


def parse_floor_orientation(attrs: Mapping[str, Any]) -> dict[str, str]:
    return {
        "front_side": normalize_token(attrs.get("data-front-side"), FLOOR_SIDES),
        "rear_side": normalize_token(attrs.get("data-rear-side"), FLOOR_SIDES),
        "site_orientation_note": normalize_text(attrs.get("data-site-orientation-note")),
    }


def parse_cell_spatial(attrs: Mapping[str, Any], classes: Iterable[str]) -> dict[str, Any]:
    outdoor_role = normalize_token(attrs.get("data-outdoor-role"), OUTDOOR_ROLES | {"none"}, "none")
    spatial = {
        "zone": normalize_token(attrs.get("data-zone"), CELL_ZONES),
        "facing": normalize_token(attrs.get("data-facing"), CELL_FACING),
        "outdoor_role": outdoor_role,
    }
    spatial["is_outdoor_like"] = is_outdoor_like(spatial, classes)
    return spatial


def is_outdoor_like(spatial: Mapping[str, Any], classes: Iterable[str]) -> bool:
    role = normalize_text(spatial.get("outdoor_role")).lower()
    if role and role != "none":
        return True
    class_set = {normalize_text(cls).lower() for cls in classes}
    return bool(class_set & OUTDOOR_CLASSES)


def window_issue_level(
    spatial: Mapping[str, Any],
    classes: Iterable[str],
    has_window_attr: bool,
    window_mm: int | None,
    min_mm: int,
    max_mm: int,
    opening_required_roles: Iterable[str] = (),
) -> str:
    role = normalize_text(spatial.get("outdoor_role")).lower()
    required_roles = {normalize_text(item).lower() for item in opening_required_roles}
    if is_outdoor_like(spatial, classes):
        if not has_window_attr and role in required_roles:
            return "info"
        return ""
    if not has_window_attr:
        return "warning"
    if window_mm is None:
        return "warning"
    if min_mm <= window_mm <= max_mm:
        return ""
    return "warning"


def _distance_to_side(
    floor_width_mm: float,
    floor_depth_mm: float,
    center_x: float,
    center_y: float,
    side: str,
) -> float:
    if side == "top":
        return center_y
    if side == "bottom":
        return floor_depth_mm - center_y
    if side == "left":
        return center_x
    if side == "right":
        return floor_width_mm - center_x
    return float("inf")


def _span_for_side(rect: Mapping[str, float], side: str) -> float:
    if side in {"top", "bottom"}:
        return float(rect.get("h_mm", 0))
    if side in {"left", "right"}:
        return float(rect.get("w_mm", 0))
    return 0.0


def nearest_declared_side(
    floor_width_mm: float | None,
    floor_depth_mm: float | None,
    rect: Mapping[str, float],
    front_side: str,
    rear_side: str,
    tolerance_ratio: float = 0.10,
    span_ratio: float = 0.70,
) -> dict[str, Any]:
    if not floor_width_mm or not floor_depth_mm:
        return {"nearest_role": "unknown", "nearest_side": "unknown", "ambiguous": True}
    if front_side not in FLOOR_SIDES or rear_side not in FLOOR_SIDES or front_side == rear_side:
        return {"nearest_role": "unknown", "nearest_side": "unknown", "ambiguous": True}

    x = float(rect.get("x_mm", 0))
    y = float(rect.get("y_mm", 0))
    w = float(rect.get("w_mm", 0))
    h = float(rect.get("h_mm", 0))
    center_x = x + w / 2
    center_y = y + h / 2

    front_distance = _distance_to_side(floor_width_mm, floor_depth_mm, center_x, center_y, front_side)
    rear_distance = _distance_to_side(floor_width_mm, floor_depth_mm, center_x, center_y, rear_side)
    relevant_dimension = floor_depth_mm if front_side in {"top", "bottom"} else floor_width_mm
    span = max(_span_for_side(rect, front_side), _span_for_side(rect, rear_side))

    if abs(front_distance - rear_distance) < relevant_dimension * tolerance_ratio:
        return {"nearest_role": "unknown", "nearest_side": "unknown", "ambiguous": True}
    if span > relevant_dimension * span_ratio:
        return {"nearest_role": "unknown", "nearest_side": "unknown", "ambiguous": True}

    if front_distance < rear_distance:
        return {"nearest_role": "front", "nearest_side": front_side, "ambiguous": False}
    return {"nearest_role": "rear", "nearest_side": rear_side, "ambiguous": False}
```

- [ ] **Step 6: Run helper tests**

Run:

```powershell
python -m pytest tests/test_spatial_metadata.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add requirements-dev.txt tests/conftest.py tests/test_spatial_metadata.py scripts/lib/spatial_metadata.py
git commit -m "test: add spatial metadata helper"
```

---

### Task 2: Extract And Preserve Spatial Metadata

**Files:**
- Modify: `scripts/extract_layout_data.py:23`
- Modify: `scripts/extract_layout_data.py:180-221`
- Modify: `scripts/extract_layout_data.py:424-451`
- Modify: `scripts/build_room_program.py:23`
- Modify: `scripts/build_room_program.py:197-367`
- Create: `tests/test_extract_and_room_program_metadata.py`

**Interfaces:**
- Consumes: Task 1 `parse_floor_orientation`, `parse_cell_spatial`.
- Produces: structured extraction schema `house-design-structured-v3`.
- Produces: floor field `orientation: {"front_side": str, "rear_side": str, "site_orientation_note": str}`.
- Produces: cell field `spatial: {"zone": str, "facing": str, "outdoor_role": str, "is_outdoor_like": bool}`.
- Produces: room-program field `source_schema_version` accepting v2 and v3.

- [ ] **Step 1: Write failing propagation tests**

Create `tests/test_extract_and_room_program_metadata.py`:

```python
from __future__ import annotations

from bs4 import BeautifulSoup

from build_room_program import transform_floor
from extract_layout_data import SCHEMA_VERSION, extract_floor


def test_extract_floor_emits_v3_orientation_and_cell_spatial() -> None:
    html = """
    <div class="floor-plan" id="floor-2" data-floor-width-mm="11000" data-floor-depth-mm="5200"
         data-north-deg="0" data-front-side="top" data-rear-side="bottom"
         data-site-orientation-note="front faces road">
      <div class="floor-title"><div>2F</div></div>
      <div class="plan-grid-visual">
        <div class="plan-row" data-row-h-mm="1700" style="grid-template-columns:1fr;">
          <div class="plan-cell outdoor" data-x-mm="5500" data-y-mm="3500" data-w-mm="5500" data-h-mm="1700"
               data-window-mm="0" data-zone="rear" data-facing="rear"
               data-outdoor-role="kaohsiung-house-balcony" onclick="highlightRoom('balcony2', this)">
            <span class="cell-name">高雄厝陽台</span>
          </div>
        </div>
      </div>
      <div class="room" id="room-balcony2"></div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    floor = extract_floor(soup.select_one(".floor-plan"), 1)

    assert SCHEMA_VERSION == "house-design-structured-v3"
    assert floor["orientation"] == {
        "front_side": "top",
        "rear_side": "bottom",
        "site_orientation_note": "front faces road",
    }
    assert floor["plan_cells"][0]["spatial"] == {
        "zone": "rear",
        "facing": "rear",
        "outdoor_role": "kaohsiung-house-balcony",
        "is_outdoor_like": True,
    }


def test_build_room_program_preserves_orientation_and_cell_spatial() -> None:
    floor = {
        "id": "floor-2",
        "order": 1,
        "title": "2F",
        "subtitle": "",
        "direction_badges": [],
        "orientation": {"front_side": "top", "rear_side": "bottom", "site_orientation_note": "front faces road"},
        "geometry_mm": {"width_mm": 11000, "depth_mm": 5200, "north_deg": 0},
        "geometry_source": "test",
        "rooms": [{"order": 1, "id": "balcony2", "name": "高雄厝陽台", "area": "", "details": [], "tags": []}],
        "plan_cells": [
            {
                "order": 1,
                "target_room_id": "balcony2",
                "name": "高雄厝陽台",
                "icon": "",
                "size": "",
                "badges": [],
                "classes": ["outdoor"],
                "row_order": 1,
                "col_order": 1,
                "col_weight": 1,
                "row_template_columns": [1],
                "geometry_mm": {"x_mm": 5500, "y_mm": 3500, "w_mm": 5500, "h_mm": 1700},
                "openings_mm": {"window_mm": 0},
                "is_entry": False,
                "material": "concrete+drain",
                "spatial": {
                    "zone": "rear",
                    "facing": "rear",
                    "outdoor_role": "kaohsiung-house-balcony",
                    "is_outdoor_like": True,
                },
            }
        ],
        "plan_rows": [],
        "tables": [],
        "checklists": [],
        "section_blocks": [],
    }

    program_floor = transform_floor("A", floor, [])

    assert program_floor["orientation"]["front_side"] == "top"
    assert program_floor["plan_cells"][0]["spatial"]["outdoor_role"] == "kaohsiung-house-balcony"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_extract_and_room_program_metadata.py -v
```

Expected: FAIL because `SCHEMA_VERSION` is still `house-design-structured-v2` and `orientation` / `spatial` are missing.

- [ ] **Step 3: Implement extraction changes**

Modify `scripts/extract_layout_data.py`:

```python
import sys
```

Add after `OUTPUT_DIR = ROOT / "structured"`:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
```

Add import after the sys path block:

```python
from lib.spatial_metadata import parse_cell_spatial, parse_floor_orientation  # noqa: E402
```

Change:

```python
SCHEMA_VERSION = "house-design-structured-v2"
```

to:

```python
SCHEMA_VERSION = "house-design-structured-v3"
```

In `extract_plan_cell`, add this field to the returned dict:

```python
"spatial": parse_cell_spatial(cell.attrs, classes_of(cell, remove={"plan-cell"})),
```

In `extract_floor`, add this field to the returned dict:

```python
"orientation": parse_floor_orientation(scope.attrs),
```

- [ ] **Step 4: Implement room-program propagation**

Modify `scripts/build_room_program.py`.

Change:

```python
        "source_schema_version": "house-design-structured-v2",
```

to:

```python
        "source_schema_version": "house-design-structured-v3",
        "compatible_source_schema_versions": ["house-design-structured-v2", "house-design-structured-v3"],
```

In `transform_floor`, before the return dict, add:

```python
    orientation = floor.get("orientation", {})
    if not isinstance(orientation, dict):
        orientation = {}
    normalized_orientation = {
        "front_side": normalize_whitespace(str(orientation.get("front_side", "unknown") or "unknown")),
        "rear_side": normalize_whitespace(str(orientation.get("rear_side", "unknown") or "unknown")),
        "site_orientation_note": normalize_whitespace(str(orientation.get("site_orientation_note", ""))),
    }
```

Add this field to each normalized cell:

```python
                "spatial": cell.get(
                    "spatial",
                    {"zone": "unknown", "facing": "unknown", "outdoor_role": "none", "is_outdoor_like": "outdoor" in cell.get("classes", [])},
                ),
```

Add this field to the returned floor dict:

```python
        "orientation": normalized_orientation,
```

- [ ] **Step 5: Run propagation tests**

Run:

```powershell
python -m pytest tests/test_extract_and_room_program_metadata.py -v
```

Expected: PASS.

- [ ] **Step 6: Run helper regression tests**

Run:

```powershell
python -m pytest tests/test_spatial_metadata.py tests/test_extract_and_room_program_metadata.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add tests/test_extract_and_room_program_metadata.py scripts/extract_layout_data.py scripts/build_room_program.py
git commit -m "feat: preserve spatial metadata in room program"
```

---

### Task 3: Metadata-Aware HTML Consistency Checks

**Files:**
- Modify: `scripts/config/residential_defaults_tw.json`
- Modify: `scripts/check_html_consistency.py:1-367`
- Create: `tests/test_html_consistency_metadata.py`

**Interfaces:**
- Consumes: Task 1 `parse_cell_spatial`, `parse_floor_orientation`, `nearest_declared_side`, `window_issue_level`.
- Produces: `check_floor_geometry(..., mode: str = "draft", spatial_config: dict[str, Any] | None = None) -> None`.
- Produces: CLI arg `--mode concept|draft|ifc`.
- Preserves: warning-only consistency reports exit `0`; critical reports exit `2`.

- [ ] **Step 1: Write failing consistency tests**

Create `tests/test_html_consistency_metadata.py`:

```python
from __future__ import annotations

from bs4 import BeautifulSoup

from check_html_consistency import check_floor_geometry


def _floor(html: str):
    return BeautifulSoup(html, "html.parser").select_one(".floor-plan")


def _run(html: str, mode: str = "draft") -> list[dict]:
    issues: list[dict] = []
    check_floor_geometry(
        building_id="A",
        file_name="AbuildingView.html",
        floor=_floor(html),
        issues=issues,
        door_min_mm=700,
        door_max_mm=1400,
        window_min_mm=300,
        window_max_mm=3600,
        mode=mode,
        spatial_config={
            "opening_required_roles": [],
            "ifc_promotion": {"cell_overlap": [], "room_target_mismatch": []},
            "direction": {"ambiguous_center_tolerance_ratio": 0.10, "span_ambiguity_ratio": 0.70},
        },
    )
    return issues


def test_outdoor_window_zero_does_not_warn() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000">
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell outdoor" data-x-mm="0" data-y-mm="0" data-w-mm="500" data-h-mm="500"
             data-window-mm="0" data-outdoor-role="balcony"><span class="cell-name">陽台</span></div>
      </div></div>
    </div>
    """

    issues = _run(html)

    assert [i for i in issues if i["code"] == "WINDOW_RANGE"] == []


def test_indoor_window_zero_warns() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000">
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="500" data-h-mm="500"
             data-window-mm="0" data-outdoor-role="none"><span class="cell-name">臥室</span></div>
      </div></div>
    </div>
    """

    issues = _run(html)

    assert any(i["code"] == "WINDOW_RANGE" and i["level"] == "warning" for i in issues)


def test_indoor_missing_window_warns() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000">
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="500" data-h-mm="500"
             data-outdoor-role="none"><span class="cell-name">臥室</span></div>
      </div></div>
    </div>
    """

    issues = _run(html)

    assert any(i["code"] == "WINDOW_MISSING" and i["level"] == "warning" for i in issues)


def test_same_front_and_rear_side_warns() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000"
         data-front-side="top" data-rear-side="top">
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="500" data-h-mm="500"
             data-window-mm="800"><span class="cell-name">客廳</span></div>
      </div></div>
    </div>
    """

    issues = _run(html)

    assert any(i["code"] == "ORIENTATION_CONFLICT" for i in issues)


def test_rear_facing_cell_near_front_reports_info_in_draft() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000"
         data-front-side="top" data-rear-side="bottom">
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="100" data-y-mm="0" data-w-mm="200" data-h-mm="200"
             data-window-mm="800" data-facing="rear"><span class="cell-name">陽台</span></div>
      </div></div>
    </div>
    """

    issues = _run(html, mode="draft")

    assert any(i["code"] == "FACING_GEOMETRY_MISMATCH" and i["level"] == "info" for i in issues)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_html_consistency_metadata.py -v
```

Expected: FAIL because `check_floor_geometry` does not accept `mode` and does not use spatial metadata.

- [ ] **Step 3: Add defaults config**

Modify `scripts/config/residential_defaults_tw.json` by adding this top-level object before `validation`:

```json
  "spatial_metadata": {
    "opening_required_roles": [],
    "ifc_promotion": {
      "cell_overlap": [],
      "room_target_mismatch": []
    },
    "direction": {
      "ambiguous_center_tolerance_ratio": 0.1,
      "span_ambiguity_ratio": 0.7
    }
  },
```

- [ ] **Step 4: Implement consistency checker imports and args**

Modify `scripts/check_html_consistency.py`:

```python
import sys
```

Add after `ROOT = Path(__file__).resolve().parents[1]`:

```python
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
```

Add imports:

```python
from lib.spatial_metadata import (  # noqa: E402
    nearest_declared_side,
    parse_cell_spatial,
    parse_floor_orientation,
    window_issue_level,
)
from lib.standards import load_residential_defaults  # noqa: E402
```

Add parser arg:

```python
    parser.add_argument("--mode", type=str, default="draft", choices=["concept", "draft", "ifc"])
```

- [ ] **Step 5: Implement metadata-aware checks**

Change `check_floor_geometry` signature to:

```python
def check_floor_geometry(
    building_id: str,
    file_name: str,
    floor: Tag,
    issues: list[dict[str, Any]],
    door_min_mm: int,
    door_max_mm: int,
    window_min_mm: int,
    window_max_mm: int,
    mode: str = "draft",
    spatial_config: dict[str, Any] | None = None,
) -> None:
```

At the top of `check_floor_geometry`, add:

```python
    spatial_config = spatial_config or {}
    orientation = parse_floor_orientation(floor.attrs)
    direction_config = spatial_config.get("direction", {})
    if (
        orientation["front_side"] != "unknown"
        and orientation["rear_side"] != "unknown"
        and orientation["front_side"] == orientation["rear_side"]
    ):
        issue(
            issues,
            "warning",
            building_id,
            file_name,
            floor_id,
            "ORIENTATION_CONFLICT",
            "data-front-side and data-rear-side must not be the same",
            evidence=f"front={orientation['front_side']}; rear={orientation['rear_side']}",
            fix_hint="調整 data-front-side / data-rear-side，使前後方向可區分。",
        )
```

In the cell loop, after `label = ...`, add:

```python
        classes = [str(cls) for cls in (cell.get("class") or []) if str(cls) != "plan-cell"]
        spatial = parse_cell_spatial(cell.attrs, classes)
```

Replace the current window check with:

```python
        has_window_attr = cell.has_attr("data-window-mm")
        window_level = window_issue_level(
            spatial,
            classes,
            has_window_attr,
            window_mm,
            window_min_mm,
            window_max_mm,
            spatial_config.get("opening_required_roles", []),
        )
        if window_level == "warning" and has_window_attr:
            issue(
                issues,
                "warning",
                building_id,
                file_name,
                floor_id,
                "WINDOW_RANGE",
                f"{label} data-window-mm={window_mm} out of range [{window_min_mm}, {window_max_mm}]",
                evidence=f"cell-{idx}",
                fix_hint="依採光與法規調整窗寬，戶外空間請標 data-outdoor-role。",
            )
        elif window_level == "warning":
            issue(
                issues,
                "warning",
                building_id,
                file_name,
                floor_id,
                "WINDOW_MISSING",
                f"{label} missing data-window-mm for an indoor-like cell",
                evidence=f"cell-{idx}",
                fix_hint="室內格位補上 data-window-mm；戶外空間請標 data-outdoor-role。",
            )
        elif window_level == "info":
            issue(
                issues,
                "info",
                building_id,
                file_name,
                floor_id,
                "WINDOW_MISSING_OPTIONAL",
                f"{label} missing optional data-window-mm for role {spatial.get('outdoor_role')}",
                evidence=f"cell-{idx}",
                fix_hint="若此戶外角色需要開口資料，補上 data-window-mm。",
            )
```

After geometry cell append, add:

```python
                if spatial.get("facing") in {"front", "rear"}:
                    nearest = nearest_declared_side(
                        floor_w,
                        floor_d,
                        {"x_mm": float(x), "y_mm": float(y), "w_mm": float(w), "h_mm": float(h)},
                        orientation["front_side"],
                        orientation["rear_side"],
                        float(direction_config.get("ambiguous_center_tolerance_ratio", 0.10)),
                        float(direction_config.get("span_ambiguity_ratio", 0.70)),
                    )
                    if not nearest.get("ambiguous") and nearest.get("nearest_role") != spatial.get("facing"):
                        level = "warning" if mode == "ifc" else "info"
                        issue(
                            issues,
                            level,
                            building_id,
                            file_name,
                            floor_id,
                            "FACING_GEOMETRY_MISMATCH",
                            f"{label} data-facing={spatial.get('facing')} but geometry is nearest {nearest.get('nearest_role')}",
                            evidence=f"cell-{idx}; nearest_side={nearest.get('nearest_side')}",
                            fix_hint="確認 data-facing 是否表示開口方向，或調整 floor front/rear side metadata。",
                        )
```

In `main`, load defaults:

```python
    defaults = load_residential_defaults()
    spatial_config = defaults.get("spatial_metadata", {})
```

Pass mode/config into `check_floor_geometry`:

```python
                mode=args.mode,
                spatial_config=spatial_config,
```

- [ ] **Step 6: Run consistency tests**

Run:

```powershell
python -m pytest tests/test_html_consistency_metadata.py -v
```

Expected: PASS.

- [ ] **Step 7: Run direct consistency check**

Run:

```powershell
python scripts/check_html_consistency.py --buildings A,B,C --mode concept
```

Expected: exit `0`; output says `Critical: 0`; warning count may change from the previous baseline because outdoor window warnings are reduced and missing indoor window metadata may be reported.

- [ ] **Step 8: Commit**

Run:

```powershell
git add tests/test_html_consistency_metadata.py scripts/check_html_consistency.py scripts/config/residential_defaults_tw.json
git commit -m "feat: classify spatial consistency warnings"
```

---

### Task 4: Workflow Stage And Validation Ownership Contracts

**Files:**
- Modify: `scripts/evaluate_expert_gates.py:916-956`
- Modify: `scripts/run_full_pipeline.ps1:1-88`
- Modify: `scripts/run_full_expert_workflow.ps1:1-165`
- Create: `tests/test_workflow_contracts.py`

**Interfaces:**
- Produces: `evaluate_expert_gates.py --stage gate` writes report but does not update task board.
- Produces: `run_full_pipeline.ps1 -ValidationOwner inner|outer|none`.
- Produces: `run_full_expert_workflow.ps1` passes `-ValidationOwner outer`.
- Preserves: hard-gate failures exit `10`.

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_workflow_contracts.py`:

```python
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_run_full_pipeline_defines_validation_owner() -> None:
    script = (ROOT / "scripts" / "run_full_pipeline.ps1").read_text(encoding="utf-8")

    assert '[ValidateSet("inner", "outer", "none")]' in script
    assert '[string]$ValidationOwner = "inner"' in script
    assert '$ValidationOwner -eq "inner"' in script


def test_expert_workflow_passes_outer_validation_owner() -> None:
    script = (ROOT / "scripts" / "run_full_expert_workflow.ps1").read_text(encoding="utf-8")

    assert "-ValidationOwner outer" in script


def test_expert_gate_stage_does_not_update_task_board() -> None:
    script = (ROOT / "scripts" / "evaluate_expert_gates.py").read_text(encoding="utf-8")

    assert 'if args.stage in {"report", "full"}:' in script
    assert 'task_board_status = "skipped for stage gate"' in script
    assert 'print(f"Task board:  {task_board_status}")' in script


def test_expert_workflow_allows_gate_exit_10_before_explicit_exit() -> None:
    script = (ROOT / "scripts" / "run_full_expert_workflow.ps1").read_text(encoding="utf-8")

    assert 'AllowedExitCodes @(0, 10)' in script
    assert "exit 10" in script
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_workflow_contracts.py -v
```

Expected: FAIL because workflow contract strings are not present yet.

- [ ] **Step 3: Update expert gate stage behavior**

Modify `scripts/evaluate_expert_gates.py`.

Replace:

```python
    update_task_board(args.task_board.resolve(), report)
```

with:

```python
    if args.stage in {"report", "full"}:
        update_task_board(args.task_board.resolve(), report)
        task_board_status = str(args.task_board.resolve())
    else:
        task_board_status = "skipped for stage gate"
```

Replace:

```python
    print(f"Task board:  {args.task_board.resolve()}")
```

with:

```python
    print(f"Task board:  {task_board_status}")
```

- [ ] **Step 4: Update pipeline validation ownership**

Modify `scripts/run_full_pipeline.ps1`.

Add param:

```powershell
    [ValidateSet("inner", "outer", "none")]
    [string]$ValidationOwner = "inner",
```

Update status line:

```powershell
Write-Host ("Running mode: {0} | selection: {1} | drawing style: {2} | validation owner: {3}" -f $Mode, $resolvedSelection, $DrawingStyle, $ValidationOwner) -ForegroundColor DarkCyan
```

Replace:

```powershell
if ($Mode -eq "ifc") {
    Invoke-Step -Name "Step IFC gate validate_layout_bundle" -Arguments @("scripts/validate_layout_bundle.py")
}
```

with:

```powershell
if ($Mode -eq "ifc" -and $ValidationOwner -eq "inner") {
    Invoke-Step -Name "Step IFC gate validate_layout_bundle" -Arguments @("scripts/validate_layout_bundle.py")
}
elseif ($Mode -eq "ifc" -and $ValidationOwner -eq "outer") {
    Write-Host "`nMode ifc: validation owned by outer workflow." -ForegroundColor Yellow
}
elseif ($Mode -eq "ifc" -and $ValidationOwner -eq "none") {
    Write-Host "`nMode ifc: validation skipped by explicit request." -ForegroundColor Yellow
}
```

- [ ] **Step 5: Update expert workflow hard-gate and ownership behavior**

Modify `scripts/run_full_expert_workflow.ps1`.

For Step 2 gate, change call to:

```powershell
$gateExit = Invoke-PythonStep -Name "Step 2/7 expert rules preflight gate" -Arguments @(
    "scripts/evaluate_expert_gates.py",
    "--stage", "gate",
    "--request", $resolvedRequestPath,
    "--buildings", $buildingsArg,
    "--mode", $Mode,
    "--selection", $resolvedSelection
) -AllowedExitCodes @(0, 10)
```

Add immediately after:

```powershell
if ($gateExit -eq 10) {
    Write-Host "`nHard gate failed. Please resolve critical issues and rerun." -ForegroundColor Red
    exit 10
}
```

Add to the `run_full_pipeline.ps1` call:

```powershell
    -ValidationOwner outer `
```

For Step 6 report, change call to:

```powershell
$reportExit = Invoke-PythonStep -Name "Step 6/7 summarize expert report" -Arguments @(
    "scripts/evaluate_expert_gates.py",
    "--stage", "report",
    "--request", $resolvedRequestPath,
    "--buildings", $buildingsArg,
    "--mode", $Mode,
    "--selection", $resolvedSelection,
    "--signoff", $Signoff
) -AllowedExitCodes @(0, 10)
```

Add immediately after:

```powershell
if ($reportExit -eq 10) {
    Write-Host "`nHard gate failed in final report. Check structured/expert_review/report.md." -ForegroundColor Red
    exit 10
}
```

- [ ] **Step 6: Run contract tests**

Run:

```powershell
python -m pytest tests/test_workflow_contracts.py -v
```

Expected: PASS.

- [ ] **Step 7: Run PowerShell syntax smoke checks**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "$null = [scriptblock]::Create((Get-Content -Raw scripts/run_full_pipeline.ps1)); 'pipeline syntax ok'"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$null = [scriptblock]::Create((Get-Content -Raw scripts/run_full_expert_workflow.ps1)); 'expert workflow syntax ok'"
```

Expected:

```text
pipeline syntax ok
expert workflow syntax ok
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add tests/test_workflow_contracts.py scripts/evaluate_expert_gates.py scripts/run_full_pipeline.ps1 scripts/run_full_expert_workflow.ps1
git commit -m "feat: enforce workflow execution contracts"
```

---

### Task 5: Final HTML Metadata And Project Config

**Files:**
- Modify: `scripts/export_final_design_html.py:445-558`
- Modify: `.mcp.json`
- Modify: `.claude/settings.local.json`
- Modify: `.gitignore`
- Create: `requirements.txt`

**Interfaces:**
- Consumes: room program floor `orientation` and plan cell `spatial`.
- Produces: final HTML payload floor fields `orientation` and `spatial_summary`.
- Produces: `.mcp.json` pinned packages.
- Produces: narrowed Claude Code permissions matching documented commands.

- [ ] **Step 1: Add runtime dependency file**

Create `requirements.txt`:

```text
beautifulsoup4==4.14.3
reportlab==4.4.10
svglib==1.6.0
```

- [ ] **Step 2: Update `.gitignore`**

Replace `.gitignore` content with:

```text
*.bak
__pycache__/
*.py[cod]
.pytest_cache/
.env
.env.*
!.env.mcp.example
```

- [ ] **Step 3: Pin MCP versions**

Modify `.mcp.json` package args:

```json
"@playwright/mcp@0.0.77"
```

and:

```json
"@modelcontextprotocol/server-brave-search@0.6.2"
```

- [ ] **Step 4: Narrow Claude Code local settings**

Modify `.claude/settings.local.json` allow list to include the documented workflow commands and direct Python steps:

```json
{
  "permissions": {
    "allow": [
      "Bash(powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 *)",
      "Bash(powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 *)",
      "Bash(python scripts/extract_layout_data.py)",
      "Bash(python scripts/build_room_program.py)",
      "Bash(python scripts/evaluate_architect_metrics.py)",
      "Bash(python scripts/generate_layout_candidates.py)",
      "Bash(python scripts/render_candidate_viewer.py)",
      "Bash(python scripts/export_top1_svgs.py *)",
      "Bash(python scripts/export_print_bundle_pdf.py *)",
      "Bash(python scripts/validate_layout_bundle.py)",
      "Bash(python scripts/check_html_consistency.py *)",
      "Bash(python scripts/evaluate_expert_gates.py *)",
      "Bash(python scripts/export_final_design_html.py *)",
      "Bash(python -m pytest *)",
      "Bash(npm view @playwright/mcp version)",
      "Bash(npm view @modelcontextprotocol/server-brave-search version)"
    ]
  },
  "enabledMcpjsonServers": [
    "playwright",
    "brave-search"
  ]
}
```

- [ ] **Step 5: Add final HTML metadata**

Modify `scripts/export_final_design_html.py`. In `export_building_html`, before `updated_floors.append(...)`, add:

```python
            spatial_summary = {
                "orientation": program_floor.get("orientation", {}),
                "cell_spatial": [
                    {
                        "order": cell.get("order"),
                        "name": normalize(cell.get("name", "")),
                        "target_room_uid": normalize(cell.get("target_room_uid", "")),
                        "spatial": cell.get("spatial", {}),
                    }
                    for cell in program_floor.get("plan_cells", [])
                ],
            }
```

Add to the `updated_floors.append` dict:

```python
                    "orientation": spatial_summary["orientation"],
                    "spatial_summary": spatial_summary,
```

- [ ] **Step 6: Verify config JSON**

Run:

```powershell
python -m json.tool .mcp.json > $null
python -m json.tool .claude/settings.local.json > $null
```

Expected: both commands exit `0`.

- [ ] **Step 7: Run relevant tests**

Run:

```powershell
python -m pytest tests/test_spatial_metadata.py tests/test_extract_and_room_program_metadata.py tests/test_html_consistency_metadata.py tests/test_workflow_contracts.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```powershell
git add requirements.txt .gitignore .mcp.json .claude/settings.local.json scripts/export_final_design_html.py
git commit -m "chore: pin workflow config and export metadata"
```

---

### Task 6: Documentation Updates

**Files:**
- Modify: `Docs/claude-code-usage.md`
- Modify: `scripts/README.md`

**Interfaces:**
- Consumes: Tasks 1-5 behavior.
- Produces: updated user-facing workflow docs covering exit codes, validation ownership, metadata schema, and warning policy.

- [ ] **Step 1: Update Claude Code usage doc**

In `Docs/claude-code-usage.md`, add a section after the one-click workflow explanation:

```markdown
## Workflow Contracts

Exit codes:

| Exit code | Meaning |
|---:|---|
| `0` | Step completed successfully |
| `1` | Unexpected runtime error |
| `2` | Validation, consistency, or argument-level failure that is not an expert hard gate |
| `10` | Expert hard gate failed with eligible critical failure |

Validation ownership:

- Direct `scripts/run_full_pipeline.ps1` execution defaults to `-ValidationOwner inner`.
- `/workflow-house-all-in-one` passes `-ValidationOwner outer` and runs `validate_layout_bundle.py` exactly once after the pipeline.
- `-ValidationOwner none` is for targeted developer/debug commands only.

HTML consistency:

- Critical issues stop the workflow with exit code `2`.
- Warning-only and info-only reports exit `0`, but warning counts remain visible in `structured/expert_review/html_consistency.json`.
- Outdoor-like cells with `data-outdoor-role` do not require `data-window-mm` unless configured as opening-required roles.
```

- [ ] **Step 2: Update script README**

In `scripts/README.md`, add a section after `Quality Gate`:

```markdown
## Spatial Metadata Contract

Directional metadata is optional and backward-compatible:

- `.floor-plan`: `data-front-side`, `data-rear-side`, `data-site-orientation-note`
- `.plan-cell`: `data-zone`, `data-facing`, `data-outdoor-role`

`top/right/bottom/left` refer to the HTML visual grid, not geographic north. `data-north-deg` remains the geographic orientation input.

Extraction emits `house-design-structured-v3` when spatial metadata support is active. Downstream scripts accept both `house-design-structured-v2` and `house-design-structured-v3` during migration.
```

- [ ] **Step 3: Run markdown grep check**

Run:

```powershell
rg -n "Workflow Contracts|ValidationOwner|Spatial Metadata Contract|house-design-structured-v3" Docs/claude-code-usage.md scripts/README.md
```

Expected: matching lines are printed from both docs.

- [ ] **Step 4: Commit**

Run:

```powershell
git add Docs/claude-code-usage.md scripts/README.md
git commit -m "docs: document workflow execution contracts"
```

---

### Task 7: Verification And Artifact Regeneration

**Files:**
- May modify generated outputs under `structured/`
- May modify `task-board.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: concept smoke evidence.
- Produces: optional separate artifact regeneration commit if generated outputs change.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
python -m pytest tests -v
```

Expected: PASS.

- [ ] **Step 2: Run concept expert workflow smoke**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode concept `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

Expected:

```text
Expert workflow completed successfully.
```

Also verify:

```powershell
Test-Path structured/expert_review/report.json
Test-Path structured/expert_review/report.md
Test-Path structured/candidates/viewer.html
Test-Path structured/final_design_html/index.html
```

Expected: all four commands print `True`.

- [ ] **Step 3: Check generated artifact churn**

Run:

```powershell
git status --short
git diff --name-only -- structured task-board.md
```

Expected: generated files may be listed because extraction now emits `house-design-structured-v3` metadata and workflow reports include fresh timestamps.

- [ ] **Step 4: Commit code changes if any remain uncommitted outside generated outputs**

Run:

```powershell
git status --short
```

Expected before continuing: no unstaged or staged code/doc/config files outside `structured/` and `task-board.md`.

- [ ] **Step 5: Create separate artifact regeneration commit when generated files changed**

If `git diff --name-only -- structured task-board.md` prints files, run:

```powershell
git add structured task-board.md
git commit -m "chore: regenerate house design artifacts"
```

Expected: generated artifact changes are isolated from code changes.

- [ ] **Step 6: Final status**

Run:

```powershell
git status --short --branch
git log --oneline -n 8
```

Expected: working tree clean; latest commits include the task commits and optional artifact regeneration commit.

---

## Plan Self-Review

Spec coverage:

- Exit-code contract: Task 4 and Task 7.
- Validation ownership: Task 4 and Task 7.
- Directional/outdoor metadata parsing and propagation: Task 1 and Task 2.
- Warning matrix and consistency exit behavior: Task 3.
- `storage.html` handling: Task 2 preserves existing storage behavior; no plan-cell metadata is required for storage.
- Config and dependency stabilization: Task 5.
- Documentation: Task 6.
- Smoke verification and generated artifact policy: Task 7.

Type consistency:

- `orientation` is always `dict[str, str]` with `front_side`, `rear_side`, and `site_orientation_note`.
- `spatial` is always a dict with `zone`, `facing`, `outdoor_role`, and `is_outdoor_like`.
- `ValidationOwner` values are exactly `inner`, `outer`, and `none`.
- Structured extraction schema is exactly `house-design-structured-v3`.

No generated outputs are staged in code-change tasks. Generated artifacts are isolated in Task 7.

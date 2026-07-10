# House Design Data Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the A/B/C house workflow preserve room-detail completeness, direction/outdoor/accessibility semantics, IFC signoff traceability, stable SVG outputs, and owner/architect review checklists without redesigning the visible layouts.

**Architecture:** Keep canonical HTML as the source of truth and extend the existing HTML -> structured JSON -> room program -> metrics -> candidates -> SVG/PDF -> expert report pipeline. Add small metadata fields and focused validation rules to existing helpers rather than introducing a new data model. Generated `structured/` artifacts are regenerated only after source behavior and tests are complete.

**Tech Stack:** Python 3, BeautifulSoup, PowerShell workflow wrappers, ReportLab/svglib PDF pipeline, pytest.

## Global Constraints

- Do not redesign or relocate A/B/C rooms.
- Do not change the visible canonical layout except adding missing detail blocks and data attributes.
- Do not introduce BIM, CAD, 3D, HVAC simulation, or solar structural calculation tools.
- Do not turn advisory metrics into legal or professional compliance statements.
- Do not remove tracked `structured/` outputs as part of source-code commits.
- Do not update external regulation interpretations without a separate source-verification pass.
- `top/right/bottom/left` always means the HTML visual grid, not geographic north.
- `data-north-deg` remains geographic orientation.
- If direction is not confirmed by the owner or architect, keep it `unknown` and emit a review item instead of guessing.
- C detail completion must not move cells, resize cells, or change visible room placement.
- IFC workflow requires a matching fresh signoff hash.

---

## File Structure

- `scripts/lib/spatial_metadata.py`: parsing and normalization of floor/cell semantic metadata.
- `scripts/extract_layout_data.py`: extracts new data attributes from canonical HTML into `*.structured.json`.
- `scripts/build_room_program.py`: preserves semantic metadata in `room_program.json`.
- `scripts/check_html_consistency.py`: reports room binding, window/daylight exemption, and orientation issues.
- `scripts/evaluate_expert_gates.py`: accessibility matching, report hash generation, and signoff hash enforcement.
- `scripts/lib/architect_metrics.py`: advisory action grouping and clearer missing-data ownership.
- `scripts/generate_domain_checklist.py`: new owner/architect discussion checklist generator.
- `scripts/export_top1_svgs.py`: stable SVG filenames and manifest metadata.
- `scripts/validate_layout_bundle.py`: validates manifest-listed SVGs only.
- `scripts/run_full_expert_workflow.ps1`: calls checklist generation and enforces IFC signoff through report stage.
- `AbuildingView.html`, `BbuildingView.html`, `CbuildingView.html`: canonical data annotations and missing C detail blocks.
- `Docs/claude-code-usage.md`, `scripts/README.md`, prompt docs: updated workflow and signoff instructions.
- `tests/`: focused tests added beside existing coverage.

## Task 1: Semantic Metadata Parsing And Preservation

**Files:**
- Modify: `scripts/lib/spatial_metadata.py`
- Modify: `scripts/extract_layout_data.py`
- Modify: `scripts/build_room_program.py`
- Test: `tests/test_spatial_metadata.py`
- Test: `tests/test_extract_and_room_program_metadata.py`

**Interfaces:**
- Consumes: HTML attributes `data-zone`, `data-facing`, `data-outdoor-role`, `data-room-role`, `data-accessible`, `data-daylight-required`.
- Produces: `parse_cell_spatial(attrs, classes) -> dict[str, Any]` with keys `zone`, `facing`, `outdoor_role`, `is_outdoor_like`, `room_role`, `is_accessible`, `daylight_required`.
- Produces: room records with `semantics` from `extract_layout_data.extract_rooms()` and `build_room_program.transform_floor()`.

- [ ] **Step 1: Add failing spatial metadata tests**

Add to `tests/test_spatial_metadata.py`:

```python
def test_parse_cell_spatial_preserves_semantic_roles() -> None:
    spatial = parse_cell_spatial(
        {
            "data-zone": "rear",
            "data-facing": "internal",
            "data-outdoor-role": "laundry-yard",
            "data-room-role": "accessible-bath",
            "data-accessible": "true",
            "data-daylight-required": "false",
        },
        ["outdoor"],
    )

    assert spatial == {
        "zone": "rear",
        "facing": "internal",
        "outdoor_role": "laundry-yard",
        "is_outdoor_like": True,
        "room_role": "accessible-bath",
        "is_accessible": True,
        "daylight_required": False,
    }


def test_parse_cell_spatial_defaults_semantics() -> None:
    spatial = parse_cell_spatial({}, [])

    assert spatial["room_role"] == "unknown"
    assert spatial["is_accessible"] is False
    assert spatial["daylight_required"] is None
```

Add to `tests/test_extract_and_room_program_metadata.py`:

```python
def test_room_semantics_are_extracted_and_preserved() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000">
      <div class="floor-title"><div>1F</div></div>
      <div class="plan-grid-visual">
        <div class="plan-row">
          <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="500" data-h-mm="500"
               data-window-mm="800" data-room-role="elder" data-accessible="true"
               onclick="highlightRoom('elder', this)">
            <span class="cell-name">孝親房</span>
          </div>
        </div>
      </div>
      <div class="room" id="room-elder" data-target-cell="slot-1"
           data-room-role="elder" data-accessible="true">
        <div class="room-name">孝親房</div>
        <div class="room-details"><li>輪椅友善</li></div>
      </div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    floor = extract_floor(soup.select_one(".floor-plan"), 1)
    program_floor = transform_floor("C", floor, [])

    assert floor["plan_cells"][0]["spatial"]["room_role"] == "elder"
    assert floor["rooms"][0]["semantics"]["room_role"] == "elder"
    assert program_floor["plan_cells"][0]["spatial"]["is_accessible"] is True
    assert program_floor["rooms"][0]["semantics"]["is_accessible"] is True
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_spatial_metadata.py tests/test_extract_and_room_program_metadata.py -q
```

Expected: fails because `laundry-yard`, `equipment-yard`, `data-room-role`, `data-accessible`, room `semantics`, and `daylight_required` are not yet preserved.

- [ ] **Step 3: Extend `spatial_metadata.py`**

Modify `scripts/lib/spatial_metadata.py`:

```python
CELL_ZONES = {"front", "rear", "left", "right", "side", "core", "service", "roof", "unknown"}
OUTDOOR_ROLES = {
    "balcony",
    "kaohsiung-house-balcony",
    "terrace",
    "side-yard",
    "garage",
    "service-yard",
    "roof-platform",
    "laundry-yard",
    "equipment-yard",
    "planting",
    "utility",
}
ROOM_ROLES = {
    "elder",
    "accessible-bath",
    "shrine",
    "equipment",
    "mechanical",
    "service",
    "circulation",
    "theater",
    "unknown",
}


def truthy_attr(value: Any) -> bool:
    token = normalize_text(value).lower()
    if token in {"", "1", "true", "yes", "y", "on"}:
        return True
    return token not in {"0", "false", "no", "n", "off"}


def optional_bool_attr(value: Any) -> bool | None:
    token = normalize_text(value).lower()
    if not token:
        return None
    if token in {"1", "true", "yes", "y", "on"}:
        return True
    if token in {"0", "false", "no", "n", "off"}:
        return False
    return None


def parse_semantics(attrs: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "room_role": normalize_token(attrs.get("data-room-role"), ROOM_ROLES),
        "is_accessible": truthy_attr(attrs.get("data-accessible")) if "data-accessible" in attrs else False,
        "daylight_required": optional_bool_attr(attrs.get("data-daylight-required")),
    }
```

Then merge `parse_semantics(attrs)` into `parse_cell_spatial()`.

- [ ] **Step 4: Extract and preserve room semantics**

Modify `scripts/extract_layout_data.py`:

```python
from lib.spatial_metadata import parse_cell_spatial, parse_floor_orientation, parse_semantics  # noqa: E402
```

Inside `extract_rooms()`, include:

```python
"semantics": parse_semantics(room.attrs),
```

Modify `scripts/build_room_program.py` room normalization to include:

```python
"semantics": room.get(
    "semantics",
    {"room_role": "unknown", "is_accessible": False, "daylight_required": None},
),
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests/test_spatial_metadata.py tests/test_extract_and_room_program_metadata.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add scripts/lib/spatial_metadata.py scripts/extract_layout_data.py scripts/build_room_program.py tests/test_spatial_metadata.py tests/test_extract_and_room_program_metadata.py
git commit -m "feat: preserve house semantic metadata"
```

## Task 2: HTML Consistency Policy For Daylight And Orientation

**Files:**
- Modify: `scripts/check_html_consistency.py`
- Modify: `scripts/lib/spatial_metadata.py`
- Test: `tests/test_html_consistency_metadata.py`

**Interfaces:**
- Consumes: `spatial["daylight_required"]` and `spatial["room_role"]`.
- Produces: `DAYLIGHT_EXEMPTION` info issue when an indoor theater-like room explicitly opts out of daylight requirement.
- Produces: `ORIENTATION_UNRESOLVED` info issue when a floor has plan cells and unknown front/rear metadata.

- [ ] **Step 1: Add failing consistency tests**

Add to `tests/test_html_consistency_metadata.py`:

```python
def test_explicit_daylight_exemption_replaces_window_range_warning() -> None:
    html = """
    <div class="floor-plan" id="floor-3" data-floor-width-mm="11000" data-floor-depth-mm="5200">
      <div class="floor-title"><div>3F</div></div>
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="11000" data-h-mm="1100"
             data-window-mm="0" data-room-role="theater" data-daylight-required="false">
          <span class="cell-name">娛樂室/家庭劇院</span>
        </div>
      </div></div>
    </div>
    """

    issues = _run(html)

    assert not any(i["code"] == "WINDOW_RANGE" for i in issues)
    assert any(i["code"] == "DAYLIGHT_EXEMPTION" and i["level"] == "info" for i in issues)


def test_floor_unknown_orientation_reports_info() -> None:
    html = """
    <div class="floor-plan" id="floor-2" data-floor-width-mm="11000" data-floor-depth-mm="5200">
      <div class="floor-title"><div>2F</div></div>
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell outdoor" data-x-mm="5500" data-y-mm="3500" data-w-mm="5500" data-h-mm="1700"
             data-window-mm="0" data-outdoor-role="kaohsiung-house-balcony">
          <span class="cell-name">高雄厝陽台</span>
        </div>
      </div></div>
    </div>
    """

    issues = _run(html)

    assert any(i["code"] == "ORIENTATION_UNRESOLVED" and i["level"] == "info" for i in issues)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_html_consistency_metadata.py::test_explicit_daylight_exemption_replaces_window_range_warning tests/test_html_consistency_metadata.py::test_floor_unknown_orientation_reports_info -q
```

Expected: fails because the new issue codes are not emitted.

- [ ] **Step 3: Add daylight exemption helper**

Add to `scripts/lib/spatial_metadata.py`:

```python
def is_daylight_exempt(spatial: Mapping[str, Any]) -> bool:
    if spatial.get("daylight_required") is False:
        return True
    return normalize_text(spatial.get("room_role")).lower() == "theater"
```

- [ ] **Step 4: Update `check_html_consistency.py`**

Import:

```python
from lib.spatial_metadata import (
    is_daylight_exempt,
    nearest_declared_side,
    parse_cell_spatial,
    parse_floor_orientation,
    window_issue_level,
)
```

After `orientation = parse_floor_orientation(floor.attrs)`, add:

```python
if orientation["front_side"] == "unknown" or orientation["rear_side"] == "unknown":
    issue(
        issues,
        "info",
        building_id,
        file_name,
        floor_id,
        "ORIENTATION_UNRESOLVED",
        "Floor front/rear orientation metadata is not fully confirmed",
        evidence=f"front={orientation['front_side']}; rear={orientation['rear_side']}",
        fix_hint="若方位已確認，補 data-front-side 與 data-rear-side；未確認則保留 unknown。",
    )
```

Before emitting `WINDOW_RANGE`, add the explicit exemption branch:

```python
if has_window_attr and is_daylight_exempt(spatial) and (window_mm is None or not (window_min_mm <= window_mm <= window_max_mm)):
    issue(
        issues,
        "info",
        building_id,
        file_name,
        floor_id,
        "DAYLIGHT_EXEMPTION",
        f"{label} is explicitly marked as not daylight-required",
        evidence=f"cell-{idx}; data-window-mm={window_mm}",
        fix_hint="確認此空間仍有符合設計需求的通風、空調與消防排煙策略。",
    )
    window_level = ""
else:
    window_level = window_issue_level(...)
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests/test_html_consistency_metadata.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add scripts/lib/spatial_metadata.py scripts/check_html_consistency.py tests/test_html_consistency_metadata.py
git commit -m "feat: refine daylight and orientation consistency"
```

## Task 3: Canonical HTML Data Completion

**Files:**
- Modify: `AbuildingView.html`
- Modify: `BbuildingView.html`
- Modify: `CbuildingView.html`
- Test: `tests/test_house_canonical_data_governance.py`

**Interfaces:**
- Consumes: canonical HTML DOM skeleton `.floor-plan > .plan-grid-visual > .plan-row > .plan-cell`.
- Produces: no `ROOM_TARGET_MISMATCH` warnings for C 1F/RF.
- Produces: A 2F `高雄厝陽台` with `data-outdoor-role="kaohsiung-house-balcony"`.
- Produces: A and C elder/accessibility cells with explicit semantic metadata.

- [ ] **Step 1: Add failing canonical data tests**

Create `tests/test_house_canonical_data_governance.py`:

```python
from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from check_html_consistency import check_floor_geometry


ROOT = Path(__file__).resolve().parents[1]


def _issues_for(building_id: str, file_name: str, floor_id: str) -> list[dict]:
    soup = BeautifulSoup((ROOT / file_name).read_text(encoding="utf-8"), "html.parser")
    floor = soup.select_one(f".floor-plan#{floor_id}")
    issues: list[dict] = []
    check_floor_geometry(
        building_id=building_id,
        file_name=file_name,
        floor=floor,
        issues=issues,
        door_min_mm=700,
        door_max_mm=1400,
        window_min_mm=300,
        window_max_mm=3600,
        mode="draft",
        spatial_config={
            "opening_required_roles": [],
            "geometry_overlap_tolerance_mm": 1.0,
            "ifc_promotion": {"cell_overlap": [], "room_target_mismatch": []},
            "direction": {"ambiguous_center_tolerance_ratio": 0.10, "span_ambiguity_ratio": 0.70},
        },
    )
    return issues


def test_c_1f_and_rf_room_targets_are_complete() -> None:
    c_1f = _issues_for("C", "CbuildingView.html", "floor-1")
    c_rf = _issues_for("C", "CbuildingView.html", "floor-4")

    assert not any(i["code"] == "ROOM_TARGET_MISMATCH" for i in c_1f)
    assert not any(i["code"] == "ROOM_TARGET_MISMATCH" for i in c_rf)


def test_a_2f_kaohsiung_balcony_has_outdoor_metadata() -> None:
    soup = BeautifulSoup((ROOT / "AbuildingView.html").read_text(encoding="utf-8"), "html.parser")
    cell = soup.select_one("#floor-2 .plan-cell[onclick*=\"balcony2\"]")

    assert cell["data-outdoor-role"] == "kaohsiung-house-balcony"
    assert cell["data-zone"] == "unknown"
    assert cell["data-facing"] == "unknown"


def test_a_1f_and_c_1f_accessible_roles_are_explicit() -> None:
    a = BeautifulSoup((ROOT / "AbuildingView.html").read_text(encoding="utf-8"), "html.parser")
    c = BeautifulSoup((ROOT / "CbuildingView.html").read_text(encoding="utf-8"), "html.parser")

    assert a.select_one("#floor-1 .plan-cell[data-room-role='elder'][data-accessible='true']")
    assert a.select_one("#floor-1 .plan-cell[data-room-role='accessible-bath'][data-accessible='true']")
    assert c.select_one("#floor-1 .plan-cell[data-room-role='elder'][data-accessible='true']")
    assert c.select_one("#floor-1 .plan-cell[data-room-role='accessible-bath'][data-accessible='true']")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_house_canonical_data_governance.py -q
```

Expected: fails because C detail blocks and semantic attributes are not complete.

- [ ] **Step 3: Add A building metadata**

Modify these exact cells:

- `AbuildingView.html` A 1F `onclick="highlightRoom('flex1', this)"`:

```html
data-room-role="elder" data-accessible="true"
```

- `AbuildingView.html` A 1F `onclick="highlightRoom('bath1', this)"`:

```html
data-room-role="accessible-bath" data-accessible="true"
```

- `AbuildingView.html` A 2F `onclick="highlightRoom('balcony2', this)"`:

```html
data-zone="unknown" data-facing="unknown" data-outdoor-role="kaohsiung-house-balcony"
```

- `AbuildingView.html` A 3F `onclick="highlightRoom('entertainment', this)"`:

```html
data-room-role="theater" data-daylight-required="false"
```

Also add the same `data-room-role` and `data-accessible` / `data-daylight-required` attributes to matching detail `.room` blocks where present.

- [ ] **Step 4: Add C building detail blocks and metadata**

In `CbuildingView.html`, add missing detail blocks inside the same `.details-panel` as the existing C 1F rooms. Use current cell geometry:

```html
<div class="room special-outdoor" data-h-mm="1200" data-target-cell="slot-1" data-w-mm="11000" data-x-mm="0" data-y-mm="0" id="room-garage">
  <div class="room-head"><div class="room-name"><div class="room-name-icon">🚗</div> 前院車庫</div><div class="room-area">約 2 車位 + 機車</div></div>
  <div class="room-details">
    <li><strong>用途：</strong>車輛停放、EV 充電與颱風軌道預留。</li>
    <li><strong>施工重點：</strong>排水、防滑與車庫到玄關高低差需確認。</li>
  </div>
</div>
<div class="room" data-h-mm="1700" data-target-cell="slot-2" data-w-mm="2750" data-x-mm="0" data-y-mm="1200" id="room-entrance">
  <div class="room-head"><div class="room-name"><div class="room-name-icon">🚪</div> 玄關</div></div>
  <div class="room-details">
    <li><strong>無障礙：</strong>車庫進門至客廳、孝親房與衛浴需維持連續平整動線。</li>
    <li><strong>收納：</strong>鞋櫃不可壓縮輪椅迴轉與轉向空間。</li>
  </div>
</div>
<div class="room" data-h-mm="1700" data-target-cell="slot-3" data-w-mm="5500" data-x-mm="2750" data-y-mm="1200" id="room-living">
  <div class="room-head"><div class="room-name"><div class="room-name-icon">🛋️</div> 客廳</div><div class="room-area">約 8 坪</div></div>
  <div class="room-details">
    <li><strong>定位：</strong>1F 家庭公共空間，需保留輪椅通行寬度。</li>
    <li><strong>設備：</strong>TV、AP、弱電點位依現有圖面預留。</li>
  </div>
</div>
<div class="room" data-h-mm="1100" data-target-cell="slot-5" data-w-mm="3771" data-x-mm="0" data-y-mm="2900" id="room-dining">
  <div class="room-head"><div class="room-name"><div class="room-name-icon">🍽️</div> 餐廳</div></div>
  <div class="room-details">
    <li><strong>定位：</strong>連接客廳與廚房的日常用餐區。</li>
    <li><strong>動線：</strong>餐桌配置需避免卡住玄關到孝親房的輪椅路徑。</li>
  </div>
</div>
<div class="room" data-h-mm="1100" data-target-cell="slot-6" data-w-mm="4086" data-x-mm="3771" data-y-mm="2900" id="room-kitchen">
  <div class="room-head"><div class="room-name"><div class="room-name-icon">🍳</div> 廚房</div></div>
  <div class="room-details">
    <li><strong>機電：</strong>冷熱水與專用迴路依現有圖面預留。</li>
    <li><strong>家務：</strong>應確認與後工作陽台的清潔、排水、垃圾動線。</li>
  </div>
</div>
<div class="room special-outdoor" data-h-mm="1700" data-target-cell="slot-11" data-w-mm="5500" data-x-mm="5500" data-y-mm="5300" id="room-service">
  <div class="room-head"><div class="room-name"><div class="room-name-icon">🧺</div> 後工作陽台</div></div>
  <div class="room-details">
    <li><strong>用途：</strong>清潔、設備維修與排水相關工作區。</li>
    <li><strong>施工重點：</strong>地坪排水、防滑與室內交界防水需確認。</li>
  </div>
</div>
```

In C RF details panel, add:

```html
<div class="room" data-h-mm="1300" data-target-cell="slot-1" data-w-mm="5500" data-x-mm="0" data-y-mm="0" id="room-stair-rf">
  <div class="room-head"><div class="room-name"><div class="room-name-icon">🪜</div> 樓梯出口（⬇️3F）</div><div class="room-area">防水人孔蓋</div></div>
  <div class="room-details"><li><strong>防水：</strong>人孔蓋、門檻與收邊需避免颱風雨倒灌。</li></div>
</div>
<div class="room" data-h-mm="1300" data-target-cell="slot-2" data-w-mm="5500" data-x-mm="5500" data-y-mm="0" id="room-riser-rf">
  <div class="room-head"><div class="room-name"><div class="room-name-icon">🔌</div> 弱電預留人孔</div><div class="room-area">可掀式防水蓋</div></div>
  <div class="room-details"><li><strong>弱電：</strong>出口需做 drip loop、防水蓋與維修照明。</li></div>
</div>
<div class="room special-outdoor" data-h-mm="1700" data-target-cell="slot-6" data-w-mm="6600" data-x-mm="0" data-y-mm="2400" id="room-platform">
  <div class="room-head"><div class="room-name"><div class="room-name-icon">🏗️</div> 活動平台 / 曬衣棚架</div><div class="room-area">預留未來擴充</div></div>
  <div class="room-details"><li><strong>防颱：</strong>棚架、太陽能遮光構件與錨定需由結構/機電確認。</li></div>
</div>
<div class="room special-outdoor" data-h-mm="1700" data-target-cell="slot-7" data-w-mm="4400" data-x-mm="6600" data-y-mm="2400" id="room-laundry-rf">
  <div class="room-head"><div class="room-name"><div class="room-name-icon">👕</div> 曬衣區</div></div>
  <div class="room-details"><li><strong>使用限制：</strong>RF 可作備用曬衣，不作長輩日常主要家務動線。</li></div>
</div>
```

Annotate C 1F / RF cells:

```html
data-outdoor-role="garage"
data-room-role="elder" data-accessible="true"
data-room-role="accessible-bath" data-accessible="true"
data-outdoor-role="side-yard"
data-outdoor-role="service-yard"
data-outdoor-role="roof-platform"
data-outdoor-role="laundry-yard"
```

Annotate B 1F shrine cell/detail:

```html
data-room-role="shrine"
```

- [ ] **Step 5: Run focused tests and consistency check**

Run:

```powershell
python -m pytest tests/test_house_canonical_data_governance.py -q
python scripts/check_html_consistency.py --buildings A,B,C --mode draft
```

Expected: focused tests pass; consistency report has `critical=0`; `ROOM_TARGET_MISMATCH` for C 1F/RF is gone.

- [ ] **Step 6: Commit**

```powershell
git add AbuildingView.html BbuildingView.html CbuildingView.html tests/test_house_canonical_data_governance.py
git commit -m "fix: complete canonical house metadata"
```

## Task 4: Accessibility Matching And IFC Signoff Hash

**Files:**
- Modify: `scripts/evaluate_expert_gates.py`
- Modify: `scripts/run_full_expert_workflow.ps1`
- Modify: `structured/expert_review/signoff.template.yaml`
- Test: `tests/test_expert_rule_policies.py`
- Test: `tests/test_workflow_contracts.py`
- Test: `tests/test_ifc_signoff_hash.py`

**Interfaces:**
- Produces: `report_content_hash(report) -> str` excluding volatile `generated_at`, `report_hash`, and `signoff`.
- Produces: `validate_signoff_for_report(signoff_data, report, allow_stale=False) -> tuple[bool, list[str]]`.
- Consumes: `--enforce-signoff-hash` on `evaluate_expert_gates.py --stage report`.
- Consumes: `--allow-stale-signoff` only for direct developer/debug command.

- [ ] **Step 1: Add failing expert/signoff tests**

Append to `tests/test_expert_rule_policies.py`:

```python
def test_accessible_door_policy_supports_room_role_elder() -> None:
    ctx = _context(
        """
        <div class="floor-plan" id="floor-1">
          <div class="plan-cell" data-door-mm="900" data-room-role="elder">
            <span class="cell-name">多功能房</span>
          </div>
        </div>
        """
    )

    passed, evidence = gates.evaluate_accessible_door_min(
        {"keywords": ["無障礙", "孝親"], "min_mm": 800},
        ctx,
    )

    assert passed is True
    assert evidence == []
```

Create `tests/test_ifc_signoff_hash.py`:

```python
from __future__ import annotations

import evaluate_expert_gates as gates


def _report() -> dict:
    return {
        "schema_version": "expert-review-v1",
        "generated_at": "2026-07-10T00:00:00+00:00",
        "hard_gate": "pass",
        "critical_failures": [],
        "warnings": [],
        "infos": [],
        "signoff": {"decision": "approved"},
    }


def test_report_content_hash_ignores_generated_at_and_signoff() -> None:
    first = _report()
    second = _report()
    second["generated_at"] = "2026-07-10T01:00:00+00:00"
    second["signoff"] = {"decision": "approved", "reviewer_name": "Owner"}

    assert gates.report_content_hash(first) == gates.report_content_hash(second)


def test_signoff_requires_matching_hash() -> None:
    report = _report()
    report_hash = gates.report_content_hash(report)

    ok, issues = gates.validate_signoff_for_report(
        {
            "decision": "approved",
            "related_report_hash": report_hash,
            "reviewer_role": "owner",
            "reviewer_name": "Owner",
            "reviewer_date": "2026-07-10",
        },
        report,
    )

    assert ok is True
    assert issues == []


def test_signoff_rejects_stale_hash() -> None:
    ok, issues = gates.validate_signoff_for_report(
        {
            "decision": "approved",
            "related_report_hash": "stale",
            "reviewer_role": "owner",
            "reviewer_name": "Owner",
            "reviewer_date": "2026-07-10",
        },
        _report(),
    )

    assert ok is False
    assert any("related_report_hash" in issue for issue in issues)
```

Append to `tests/test_workflow_contracts.py`:

```python
def test_expert_workflow_enforces_ifc_signoff_hash_in_report_stage() -> None:
    script = (ROOT / "scripts" / "run_full_expert_workflow.ps1").read_text(encoding="utf-8")

    assert "--enforce-signoff-hash" in script
    assert "Assert-IfCSignoff" not in script
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_expert_rule_policies.py tests/test_ifc_signoff_hash.py tests/test_workflow_contracts.py -q
```

Expected: fails because hash helpers, room-role matching, and workflow flag are not present.

- [ ] **Step 3: Update accessibility matcher**

In `evaluate_accessible_door_min()`, include role/accessibility checks:

```python
room_role = normalize_match_text(cell.get("data-room-role", ""))
is_accessible = truthy_attr(cell.get("data-accessible"))
role_match = room_role in {"elder", "accessiblebath"}
if not is_accessible and not role_match and not any(keyword in raw_text for keyword in keywords):
    continue
```

- [ ] **Step 4: Add stable report hash and signoff validation**

In `scripts/evaluate_expert_gates.py`, add:

```python
def report_hash_payload(report: dict[str, Any]) -> dict[str, Any]:
    excluded = {"generated_at", "report_hash", "signoff"}
    return {key: value for key, value in report.items() if key not in excluded}


def report_content_hash(report: dict[str, Any]) -> str:
    payload = json.dumps(report_hash_payload(report), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_signoff_for_report(
    signoff_data: dict[str, str],
    report: dict[str, Any],
    allow_stale: bool = False,
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    decision = normalize_whitespace(signoff_data.get("decision", "")).lower()
    if decision not in {"approved", "pass", "approved_with_conditions"}:
        issues.append("decision must be approved, pass, or approved_with_conditions")
    for key in ["reviewer_role", "reviewer_name", "reviewer_date"]:
        if not normalize_whitespace(signoff_data.get(key, "")):
            issues.append(f"{key} is required")
    expected_hash = report_content_hash(report)
    actual_hash = normalize_whitespace(signoff_data.get("related_report_hash", ""))
    if actual_hash != expected_hash and not allow_stale:
        issues.append(f"related_report_hash mismatch: expected {expected_hash}, got {actual_hash or '<missing>'}")
    return len(issues) == 0, issues
```

Use `report["report_hash"] = report_content_hash(report)`.

- [ ] **Step 5: Enforce signoff in report stage**

Add argparse flags:

```python
parser.add_argument("--enforce-signoff-hash", action="store_true")
parser.add_argument("--allow-stale-signoff", action="store_true")
```

After writing report JSON/MD, add:

```python
if args.enforce_signoff_hash:
    signoff_data = parse_signoff_yaml(args.signoff.resolve())
    ok, signoff_issues = validate_signoff_for_report(
        signoff_data,
        report,
        allow_stale=args.allow_stale_signoff,
    )
    if not ok:
        print("IFC signoff mismatch:")
        for item in signoff_issues:
            print(f"- {item}")
        raise SystemExit(2)
```

Remove PowerShell early `Assert-IfCSignoff` call and pass `--enforce-signoff-hash` to Step 6 only when `$Mode -eq "ifc"`.

- [ ] **Step 6: Update signoff template**

Modify `structured/expert_review/signoff.template.yaml`:

```yaml
decision: approved
reviewer_role: owner
reviewer_name: ""
reviewer_date: "2026-07-10"
related_report_hash: ""
related_report_generated_at: ""
notes: |
  Review the latest structured/expert_review/report.md before copying its report_hash here.
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
python -m pytest tests/test_expert_rule_policies.py tests/test_ifc_signoff_hash.py tests/test_workflow_contracts.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```powershell
git add scripts/evaluate_expert_gates.py scripts/run_full_expert_workflow.ps1 structured/expert_review/signoff.template.yaml tests/test_expert_rule_policies.py tests/test_ifc_signoff_hash.py tests/test_workflow_contracts.py
git commit -m "feat: enforce traceable IFC signoff"
```

## Task 5: Architect Metrics Action Groups

**Files:**
- Modify: `scripts/lib/architect_metrics.py`
- Modify: `scripts/evaluate_expert_gates.py`
- Test: `tests/test_architect_metrics_quality.py`

**Interfaces:**
- Produces: `summary["action_groups"]` mapping owner group names to issue strings.
- Group names: `architect_daylight_ventilation`, `accessibility_door_width`, `structural_rf_equipment`, `mep_rf_equipment`, `owner_design_decision`.

- [ ] **Step 1: Add failing action-group test**

Append to `tests/test_architect_metrics_quality.py`:

```python
def test_summary_groups_actions_by_professional_owner() -> None:
    payload = {
        "metrics": [
            {
                "building_id": "A",
                "floor_id": "floor-1",
                "room_uid": "A:floor-1:living",
                "metric_type": "daylight_factor",
                "status": "advisory",
                "issues": ["concept daylight factor is below target"],
            },
            {
                "building_id": "C",
                "floor_id": "floor-4",
                "room_uid": "C:floor-4:heatpump",
                "metric_type": "structure_load_review",
                "status": STATUS_MISSING,
                "issues": ["formal structural review/signoff is required"],
            },
        ],
        "evaluated_floor_count": 2,
        "skipped_floor_count": 0,
    }

    summary = summarize_metrics_payload(payload)

    assert "architect_daylight_ventilation" in summary["action_groups"]
    assert "structural_rf_equipment" in summary["action_groups"]
    assert summary["action_groups"]["architect_daylight_ventilation"][0].startswith("A:floor-1:living")
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests/test_architect_metrics_quality.py::test_summary_groups_actions_by_professional_owner -q
```

Expected: fails because `action_groups` is missing.

- [ ] **Step 3: Implement grouping helper**

Add to `scripts/lib/architect_metrics.py`:

```python
def action_group_for_metric(metric: dict[str, Any]) -> str:
    metric_type = str(metric.get("metric_type", ""))
    room_uid = str(metric.get("room_uid", ""))
    text = " ".join(str(issue) for issue in metric.get("issues", []))
    if metric_type == "daylight_factor":
        return "architect_daylight_ventilation"
    if metric_type == "door_width":
        return "accessibility_door_width"
    if metric_type == "structure_load_review":
        return "structural_rf_equipment"
    if any(token in room_uid + text for token in ["heatpump", "pump", "VF800", "熱泵", "加壓"]):
        return "mep_rf_equipment"
    return "owner_design_decision"


def build_action_groups(metrics: list[dict[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for metric in metrics:
        if metric.get("status") == STATUS_OK:
            continue
        group = action_group_for_metric(metric)
        label = metric_issue_label(metric)
        groups.setdefault(group, []).append(label)
    return {key: values[:20] for key, values in groups.items() if values}
```

Inside `summarize_metrics_payload()`, add:

```python
summary["action_groups"] = build_action_groups(metrics)
```

- [ ] **Step 4: Include action groups in report markdown**

In `evaluate_expert_gates.generate_report_md()`, under `## Architect Metrics`, add:

```python
action_groups = architect_summary.get("action_groups", {})
if action_groups:
    lines.append("- Action groups:")
    for group, items in action_groups.items():
        lines.append(f"  - {group}: {len(items)} item(s)")
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests/test_architect_metrics_quality.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add scripts/lib/architect_metrics.py scripts/evaluate_expert_gates.py tests/test_architect_metrics_quality.py
git commit -m "feat: group architect metric actions"
```

## Task 6: Domain Review Checklist Generation

**Files:**
- Create: `scripts/generate_domain_checklist.py`
- Modify: `scripts/run_full_expert_workflow.ps1`
- Test: `tests/test_domain_checklist.py`
- Modify docs later in Task 8.

**Interfaces:**
- Produces: `build_domain_checklist(report, html_consistency, room_program, metrics) -> dict[str, Any]`.
- Writes: `structured/expert_review/domain_checklist.json`.
- Writes: `structured/expert_review/domain_checklist.md`.

- [ ] **Step 1: Add failing checklist tests**

Create `tests/test_domain_checklist.py`:

```python
from __future__ import annotations

from scripts.generate_domain_checklist import build_domain_checklist, render_domain_checklist_md


def test_domain_checklist_contains_current_owner_architect_questions() -> None:
    checklist = build_domain_checklist(
        report={"report_hash": "abc123"},
        html_consistency={"issues": []},
        room_program={"buildings": []},
        metrics={"summary": {"action_groups": {}}},
    )
    text = "\n".join(item["title"] for item in checklist["items"])

    assert "A 2F 高雄厝陽台方向確認" in text
    assert "A 棟低成本冷氣擴散策略" in text
    assert "B 棟神明廳上下疊圖與排煙防火" in text
    assert "C 棟側院、洗衣、運動與 RF 設備確認" in text


def test_domain_checklist_markdown_has_no_compliance_claim() -> None:
    checklist = build_domain_checklist(
        report={"report_hash": "abc123"},
        html_consistency={"issues": []},
        room_program={"buildings": []},
        metrics={"summary": {"action_groups": {}}},
    )
    md = render_domain_checklist_md(checklist)

    assert "不作為法規、結構、消防、採光、通風或無障礙合規證明" in md
    assert "已通過法規" not in md
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_domain_checklist.py -q
```

Expected: fails because the script does not exist.

- [ ] **Step 3: Create checklist script**

Create `scripts/generate_domain_checklist.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "structured" / "expert_review" / "report.json"
HTML_CONSISTENCY_JSON = ROOT / "structured" / "expert_review" / "html_consistency.json"
ROOM_PROGRAM_JSON = ROOT / "structured" / "room_program.json"
METRICS_JSON = ROOT / "structured" / "architect_metrics" / "metrics.json"
OUTPUT_JSON = ROOT / "structured" / "expert_review" / "domain_checklist.json"
OUTPUT_MD = ROOT / "structured" / "expert_review" / "domain_checklist.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def item(category: str, title: str, owner: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "category": category,
        "title": title,
        "owner": owner,
        "status": "open",
        "evidence": evidence,
        "claim_limit": "discussion_only_not_compliance",
    }


def build_domain_checklist(
    report: dict[str, Any],
    html_consistency: dict[str, Any],
    room_program: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "domain-checklist-v1",
        "generated_at": now_iso(),
        "report_hash": str(report.get("report_hash", "")),
        "items": [
            item("A", "A 2F 高雄厝陽台方向確認", "owner_architect", ["area=9.35m2", "share=16.3%", "visual_grid=bottom-right"]),
            item("A", "A 棟低成本冷氣擴散策略", "architect_mep", ["research low-cost whole-house air distribution before equipment purchase"]),
            item("A", "A RF 太陽能遮光棚架與颱風雨防護", "structural_mep", ["solar shade canopy", "rain exposure", "anchoring"]),
            item("A/C", "A/C 1F 長輩房與衛浴 150cm 迴轉圈", "architect_accessibility", ["elder room", "accessible bath", "furniture placed before confirmation"]),
            item("B", "B 棟神明廳上下疊圖與排煙防火", "architect_mep_fire", ["shrine wall", "beam overlay", "2F wet area", "exhaust", "make-up air", "fire material"]),
            item("C", "C 棟側院、洗衣、運動與 RF 設備確認", "architect_structural_mep", ["side-yard clear width", "2F laundry waterproofing", "3F exercise vibration", "RF anchoring"]),
        ],
        "source_counts": {
            "html_consistency_issues": len(html_consistency.get("issues", [])),
            "architect_action_groups": len(metrics.get("summary", {}).get("action_groups", {})),
        },
    }


def render_domain_checklist_md(checklist: dict[str, Any]) -> str:
    lines = [
        "# Domain Review Checklist",
        "",
        "本清單供屋主、建築師、結構技師與機電討論，不作為法規、結構、消防、採光、通風或無障礙合規證明。",
        "",
        f"- Report hash: `{checklist.get('report_hash', '')}`",
        "",
    ]
    for entry in checklist.get("items", []):
        evidence = "; ".join(entry.get("evidence", []))
        lines.append(f"- [{entry.get('status')}] **{entry.get('title')}** ({entry.get('owner')}) - {evidence}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate owner/architect domain review checklist.")
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=OUTPUT_MD)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    checklist = build_domain_checklist(
        report=load_json(REPORT_JSON),
        html_consistency=load_json(HTML_CONSISTENCY_JSON),
        room_program=load_json(ROOM_PROGRAM_JSON),
        metrics=load_json(METRICS_JSON),
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(checklist, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(render_domain_checklist_md(checklist), encoding="utf-8")
    print(f"Domain checklist JSON: {args.output_json}")
    print(f"Domain checklist MD:   {args.output_md}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add workflow step**

In `scripts/run_full_expert_workflow.ps1`, after report generation and before final HTML export, add a Python step:

```powershell
Invoke-PythonStep -Name "Step 7/8 generate domain checklist" -Arguments @(
    "scripts/generate_domain_checklist.py"
)
```

Rename final HTML step to `Step 8/8 export final design HTML`, and update earlier labels from `Step N/7` to `Step N/8`.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests/test_domain_checklist.py tests/test_workflow_contracts.py -q
```

Expected: tests pass. If workflow-contract tests assert exact `Step 3/7` text, update them to accept `Step 3/8`.

- [ ] **Step 6: Commit**

```powershell
git add scripts/generate_domain_checklist.py scripts/run_full_expert_workflow.ps1 tests/test_domain_checklist.py tests/test_workflow_contracts.py
git commit -m "feat: generate domain review checklist"
```

## Task 7: Stable SVG Export And Manifest Validation

**Files:**
- Modify: `scripts/export_top1_svgs.py`
- Modify: `scripts/validate_layout_bundle.py`
- Modify: `scripts/export_print_bundle_pdf.py`
- Modify: `scripts/export_final_design_html.py`
- Test: `tests/test_pdf_hatch_compatibility.py`
- Test: `tests/test_svg_manifest_stability.py`

**Interfaces:**
- Produces stable SVG filenames: `<building>_<floor>.svg`.
- Manifest keeps selected candidate in fields `requested_selection`, `resolved_selection`, `selected_candidate_id`, `selected_strategy`.
- Validation reads only `manifest["exports"][*]["file"]`.

- [ ] **Step 1: Add failing manifest stability test**

Create `tests/test_svg_manifest_stability.py`:

```python
from __future__ import annotations

from export_top1_svgs import stable_svg_filename


def test_stable_svg_filename_ignores_candidate_strategy() -> None:
    assert stable_svg_filename("A", "floor-1") == "a_floor-1.svg"
    assert stable_svg_filename("B", "floor-4") == "b_floor-4.svg"
```

Append to `tests/test_pdf_hatch_compatibility.py`:

```python
def test_manifest_records_selection_fields_without_strategy_filename() -> None:
    name = svg_export.stable_svg_filename("A", "floor-1")

    assert name == "a_floor-1.svg"
    assert "_baseline" not in name
    assert "_mep" not in name
    assert "_circulation" not in name
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_svg_manifest_stability.py tests/test_pdf_hatch_compatibility.py -q
```

Expected: fails because `stable_svg_filename` is missing.

- [ ] **Step 3: Implement stable filenames and cleanup**

In `scripts/export_top1_svgs.py`, add:

```python
def stable_svg_filename(building_id: str, floor_id: str) -> str:
    return f"{safe_slug(building_id)}_{safe_slug(floor_id)}.svg"
```

Replace:

```python
slug = f"{safe_slug(b_id)}_{safe_slug(f_id)}_{safe_slug(selected.get('id', args.selection))}"
out_file = OUT_DIR / f"{slug}.svg"
```

with:

```python
out_file = OUT_DIR / stable_svg_filename(b_id, f_id)
```

Keep the existing `for old_svg in OUT_DIR.glob("*.svg"): old_svg.unlink()` cleanup so stale strategy-named files are removed during the intentional regeneration commit.

Add manifest fields:

```python
"requested_selection": args.selection,
"resolved_selection": args.selection,
```

In each export record add:

```python
"selected_candidate_id": selected.get("id", ""),
"selected_strategy": selected.get("strategy", ""),
```

- [ ] **Step 4: Keep consumers manifest-based**

Confirm `scripts/validate_layout_bundle.py`, `scripts/export_print_bundle_pdf.py`, and `scripts/export_final_design_html.py` continue resolving `rec["file"]` relative to manifest directory. If any consumer scans `*.svg`, replace the scan with manifest reads.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests/test_svg_manifest_stability.py tests/test_pdf_hatch_compatibility.py -q
```

Expected: tests pass.

- [ ] **Step 6: Commit source changes**

```powershell
git add scripts/export_top1_svgs.py scripts/validate_layout_bundle.py scripts/export_print_bundle_pdf.py scripts/export_final_design_html.py tests/test_svg_manifest_stability.py tests/test_pdf_hatch_compatibility.py
git commit -m "fix: stabilize SVG export filenames"
```

## Task 8: Workflow Documentation And Prompt Updates

**Files:**
- Modify: `Docs/claude-code-usage.md`
- Modify: `scripts/README.md`
- Modify: `scripts/WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md`
- Modify: `scripts/WEB_TO_PLAN_PROMPTS.zh-TW.md`
- Test: `tests/test_workflow_contracts.py`

**Interfaces:**
- Documents two-pass IFC signoff hash flow.
- Documents domain checklist outputs.
- Documents stable SVG filename behavior and manifest fields.

- [ ] **Step 1: Add failing docs contract tests**

Append to `tests/test_workflow_contracts.py`:

```python
def test_docs_describe_signoff_hash_and_domain_checklist() -> None:
    usage = (ROOT / "Docs" / "claude-code-usage.md").read_text(encoding="utf-8")
    readme = (ROOT / "scripts" / "README.md").read_text(encoding="utf-8")

    assert "related_report_hash" in usage
    assert "domain_checklist.md" in usage
    assert "related_report_hash" in readme
    assert "domain_checklist.md" in readme


def test_prompts_do_not_describe_decision_only_ifc_signoff() -> None:
    all_in_one = (ROOT / "scripts" / "WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md").read_text(encoding="utf-8")
    web_to_plan = (ROOT / "scripts" / "WEB_TO_PLAN_PROMPTS.zh-TW.md").read_text(encoding="utf-8")

    assert "related_report_hash" in all_in_one
    assert "related_report_hash" in web_to_plan
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest tests/test_workflow_contracts.py -q
```

Expected: fails until docs mention the new contract.

- [ ] **Step 3: Update docs**

In `Docs/claude-code-usage.md` and `scripts/README.md`, add:

```markdown
### IFC signoff hash

`ifc` 模式不再只看 `decision: approved`。流程會產生最新 `structured/expert_review/report.json` 與 `report_hash`，`structured/expert_review/signoff.yaml` 必須填入相同的 `related_report_hash` 才能通過。

建議流程：

1. 先跑一次 `-Mode ifc` 產生最新 report。
2. 若 signoff missing/stale，流程會以 exit code `2` 停止並保留 report。
3. Reviewer 檢查 `report.md` 後，把 `report_hash` 填入 `signoff.yaml` 的 `related_report_hash`。
4. 重跑 `-Mode ifc`。
```

Add output docs:

```markdown
- `structured/expert_review/domain_checklist.json`
- `structured/expert_review/domain_checklist.md`
```

Update prompt docs so IFC says `decision + related_report_hash` instead of decision-only.

- [ ] **Step 4: Run docs tests**

Run:

```powershell
python -m pytest tests/test_workflow_contracts.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add Docs/claude-code-usage.md scripts/README.md scripts/WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md scripts/WEB_TO_PLAN_PROMPTS.zh-TW.md tests/test_workflow_contracts.py
git commit -m "docs: document data governance workflow"
```

## Task 9: Full Verification And Intentional Regeneration

**Files:**
- Regenerate: `structured/*.json`
- Regenerate: `structured/expert_review/*`
- Regenerate: `structured/architect_metrics/*`
- Regenerate: `structured/candidates/*`
- Regenerate: `structured/final_design_html/*`

**Interfaces:**
- Produces checked-in artifacts matching the new stable SVG names and metadata.
- Leaves the worktree clean after the final commit.

- [ ] **Step 1: Run full tests before regeneration**

Run:

```powershell
python -m pytest tests -q
python -m compileall -q scripts tests
python -m pip check
```

Expected:

```text
52+ passed
No broken requirements found.
```

- [ ] **Step 2: Run concept and draft smoke**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode concept `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

Expected:

- exit code `0`
- `structured/expert_review/html_consistency.json` has `critical=0`
- C `ROOM_TARGET_MISMATCH` warnings are gone
- draft PDF writes 12 floor pages with failures `0`
- `structured/expert_review/domain_checklist.md` exists

- [ ] **Step 3: Generate fresh IFC signoff hash**

Run IFC once:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode ifc `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

Expected: exit code `2` if current `signoff.yaml` is missing or stale; report files remain written.

Read the hash:

```powershell
$report = Get-Content -Raw structured\expert_review\report.json | ConvertFrom-Json
$report.report_hash
```

Update `structured/expert_review/signoff.yaml`:

```yaml
decision: approved
reviewer_role: owner
reviewer_name: I29786
reviewer_date: "2026-07-10"
related_report_hash: "<copy report.report_hash>"
related_report_generated_at: "<copy report.generated_at>"
notes: |
  IFC smoke signoff for regenerated house design data-governance artifacts.
```

- [ ] **Step 4: Run IFC smoke again**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode ifc `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

Expected:

- exit code `0`
- hard gate pass
- signoff hash matches latest report
- bundle validation errors `0`
- PDF failures `0`

- [ ] **Step 5: Inspect generated churn**

Run:

```powershell
git status --short
git diff --stat
python scripts/validate_layout_bundle.py
```

Expected:

- changed files are generated artifacts plus `signoff.yaml`
- no untracked `structured/candidates/svg/*_baseline.svg`, `*_mep.svg`, `*_circulation.svg`, or `*_daylight.svg`
- validation errors `0`, warnings `0`

- [ ] **Step 6: Commit regeneration separately**

```powershell
git add structured
git commit -m "chore: regenerate house data governance artifacts"
```

- [ ] **Step 7: Final verification**

Run:

```powershell
python -m pytest tests -q
python scripts/validate_layout_bundle.py
git diff --check
git status --short --branch
```

Expected:

- all tests pass
- validation errors `0`, warnings `0`
- `git diff --check` exits `0`
- branch is ahead of `origin/main` with no dirty files

## Self-Review Checklist

- Spec coverage: Tasks 1-3 cover semantic metadata, C detail completion, A theater daylight policy, and A/C accessibility metadata. Task 4 covers IFC signoff traceability. Task 5 covers Architect Metrics action groups. Task 6 covers domain checklist. Task 7 covers SVG churn. Task 8 covers docs and prompts. Task 9 covers regenerated artifacts and smoke verification.
- Placeholder scan: This plan contains concrete file paths, function names, commands, expected outcomes, and code snippets for every behavior change.
- Type consistency: New functions are `parse_semantics`, `is_daylight_exempt`, `report_content_hash`, `validate_signoff_for_report`, `build_action_groups`, `build_domain_checklist`, `render_domain_checklist_md`, and `stable_svg_filename`; all later tasks refer to these exact names.


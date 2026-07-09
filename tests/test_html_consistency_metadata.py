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
            "geometry_overlap_tolerance_mm": 1.0,
            "ifc_promotion": {"cell_overlap": [], "room_target_mismatch": []},
            "direction": {
                "ambiguous_center_tolerance_ratio": 0.10,
                "span_ambiguity_ratio": 0.70,
            },
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


def test_invalid_window_value_emits_dedicated_issue() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000">
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="500" data-h-mm="500"
             data-window-mm="abc"><span class="cell-name">臥室</span></div>
      </div></div>
    </div>
    """

    issues = _run(html)

    assert any(i["code"] == "WINDOW_INVALID" and i["level"] == "warning" for i in issues)
    assert not any(
        i["code"] == "WINDOW_RANGE" and "None" in i["message"]
        for i in issues
    )


def test_invalid_geometry_does_not_emit_facing_mismatch() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000"
         data-front-side="top" data-rear-side="bottom">
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="-10" data-y-mm="0" data-w-mm="200" data-h-mm="200"
             data-window-mm="800" data-facing="rear"><span class="cell-name">陽台</span></div>
      </div></div>
    </div>
    """

    issues = _run(html)

    assert any(i["code"] == "INVALID_CELL_GEOMETRY" for i in issues)
    assert not any(i["code"] == "FACING_GEOMETRY_MISMATCH" for i in issues)


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


def test_cell_overlap_stays_warning_without_ifc_promotion() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000">
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="600" data-h-mm="600"
             data-window-mm="800"><span class="cell-name">客廳</span></div>
        <div class="plan-cell" data-x-mm="500" data-y-mm="0" data-w-mm="400" data-h-mm="400"
             data-window-mm="800"><span class="cell-name">餐廳</span></div>
      </div></div>
    </div>
    """

    issues = _run(html, mode="ifc")

    assert any(i["code"] == "CELL_OVERLAP" and i["level"] == "warning" for i in issues)


def test_one_mm_rounding_overlap_is_ignored() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="11000" data-floor-depth-mm="1100">
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="3667" data-y-mm="0" data-w-mm="3667" data-h-mm="1100"
             data-window-mm="800"><span class="cell-name">設備 A</span></div>
        <div class="plan-cell" data-x-mm="7333" data-y-mm="0" data-w-mm="3667" data-h-mm="1100"
             data-window-mm="800"><span class="cell-name">設備 B</span></div>
      </div></div>
    </div>
    """

    issues = _run(html)

    assert not any(i["code"] == "CELL_OVERLAP" for i in issues)


def test_overlap_above_tolerance_is_reported() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="11000" data-floor-depth-mm="1100">
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="3667" data-y-mm="0" data-w-mm="3668" data-h-mm="1100"
             data-window-mm="800"><span class="cell-name">設備 A</span></div>
        <div class="plan-cell" data-x-mm="7333" data-y-mm="0" data-w-mm="3667" data-h-mm="1100"
             data-window-mm="800"><span class="cell-name">設備 B</span></div>
      </div></div>
    </div>
    """

    issues = _run(html)

    assert any(i["code"] == "CELL_OVERLAP" for i in issues)


def test_cell_overlap_promotes_to_critical_in_ifc_when_configured() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000">
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="600" data-h-mm="600"
             data-window-mm="800"><span class="cell-name">客廳</span></div>
        <div class="plan-cell" data-x-mm="500" data-y-mm="0" data-w-mm="400" data-h-mm="400"
             data-window-mm="800"><span class="cell-name">餐廳</span></div>
      </div></div>
    </div>
    """

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
        mode="ifc",
        spatial_config={
            "opening_required_roles": [],
            "ifc_promotion": {"cell_overlap": ["cell_overlap"], "room_target_mismatch": []},
            "direction": {
                "ambiguous_center_tolerance_ratio": 0.10,
                "span_ambiguity_ratio": 0.70,
            },
        },
    )

    assert any(i["code"] == "CELL_OVERLAP" and i["level"] == "critical" for i in issues)


def test_room_target_mismatch_stays_warning_without_ifc_promotion() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000">
      <div class="room" id="room-living"></div>
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="500" data-h-mm="500"
             data-window-mm="800" onclick="highlightRoom('missing', this)">
          <span class="cell-name">客廳</span>
        </div>
      </div></div>
    </div>
    """

    issues = _run(html, mode="ifc")

    assert any(i["code"] == "ROOM_TARGET_MISMATCH" and i["level"] == "warning" for i in issues)


def test_room_target_mismatch_promotes_to_critical_in_ifc_when_configured() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000">
      <div class="room" id="room-living"></div>
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="500" data-h-mm="500"
             data-window-mm="800" onclick="highlightRoom('missing', this)">
          <span class="cell-name">客廳</span>
        </div>
      </div></div>
    </div>
    """

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
        mode="ifc",
        spatial_config={
            "opening_required_roles": [],
            "ifc_promotion": {"cell_overlap": [], "room_target_mismatch": ["room_target_mismatch"]},
            "direction": {
                "ambiguous_center_tolerance_ratio": 0.10,
                "span_ambiguity_ratio": 0.70,
            },
        },
    )

    assert any(i["code"] == "ROOM_TARGET_MISMATCH" and i["level"] == "critical" for i in issues)


def test_ground_floor_entry_count_uses_main_entry_wording() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000">
      <div class="floor-title"><div>1F</div></div>
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="500" data-h-mm="500"
             data-window-mm="800"><span class="cell-name">客廳</span></div>
      </div></div>
    </div>
    """

    issues = _run(html)
    entry_issue = next(i for i in issues if i["code"] == "ENTRY_COUNT")

    assert entry_issue["level"] == "warning"
    assert "main entry" in entry_issue["message"]


def test_upper_floor_entry_count_uses_stair_or_landing_wording() -> None:
    html = """
    <div class="floor-plan" id="floor-2" data-floor-width-mm="1000" data-floor-depth-mm="1000">
      <div class="floor-title"><div>2F</div></div>
      <div class="plan-grid-visual"><div class="plan-row">
        <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="500" data-h-mm="500"
             data-window-mm="800"><span class="cell-name">起居室</span></div>
      </div></div>
    </div>
    """

    issues = _run(html)
    entry_issue = next(i for i in issues if i["code"] in {"ENTRY_COUNT_UPPER_FLOOR", "ENTRY_COUNT"})

    assert entry_issue["message"] != "Expected exactly 1 main entry cell, got 0"
    assert "main entry" not in entry_issue["message"]
    assert "stair" in entry_issue["message"] or "landing" in entry_issue["message"]

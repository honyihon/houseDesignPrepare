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

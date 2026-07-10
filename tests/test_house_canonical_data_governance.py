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

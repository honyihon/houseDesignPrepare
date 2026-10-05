from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
BUILDING_FILES = {
    "A": "AbuildingView.html",
    "B": "BbuildingView.html",
    "C": "CbuildingView.html",
}


def test_canonical_html_pages_load_the_shared_3d_bridge() -> None:
    for building_id, filename in BUILDING_FILES.items():
        soup = BeautifulSoup((ROOT / filename).read_text(encoding="utf-8"), "html.parser")

        assert soup.body["data-building-id"] == building_id
        assert soup.body["data-design-status"] == "historical-html-sketch"
        assert soup.select_one('link[href="assets/html_design_bridge.css"]') is not None
        assert soup.select_one('script[src="assets/html_design_bridge.js"]') is not None


def test_every_html_plan_cell_still_binds_to_a_room_and_known_orientation() -> None:
    bound_cells = 0
    for filename in BUILDING_FILES.values():
        soup = BeautifulSoup((ROOT / filename).read_text(encoding="utf-8"), "html.parser")
        for floor in soup.select('.floor-plan[data-front-side="top"][data-rear-side="bottom"]'):
            for cell in floor.select(".plan-cell[onclick]"):
                match = re.search(r"highlightRoom\(\s*['\"]([^'\"]+)", cell.get("onclick", ""))
                assert match is not None
                assert soup.select_one(f"#room-{match.group(1)}") is not None
                bound_cells += 1

    assert bound_cells == 92


def test_bridge_declares_the_room_deep_link_and_anchor_restore_contract() -> None:
    source = (ROOT / "assets" / "html_design_bridge.js").read_text(encoding="utf-8")

    assert 'params.set("building", buildingId)' in source
    assert 'params.set("floor", floorId)' in source
    assert 'params.set("room", buildingId + ":" + floorId + ":" + roomId)' in source
    assert 'params.set("view", "plan")' in source
    assert "match(/^#room-(.+)$/)" in source


def test_c_elder_bath_does_not_assume_inward_opening() -> None:
    soup = BeautifulSoup((ROOT / "CbuildingView.html").read_text(encoding="utf-8"), "html.parser")
    text = soup.select_one("#room-elder-bath").get_text(" ", strip=True)
    assert "不預設向內開" in text
    assert "外部緊急解鎖" in text
    assert "建議向內開或拉門" not in text


def test_static_review_does_not_hide_area_or_version_differences() -> None:
    from house_design.owner_consistency import build_consistency_review

    report = build_consistency_review()
    findings = report["findings"]
    assert any(f["title"] == "HTML 靜態查核 · AREA_TEXT_MISMATCH" for f in findings)
    assert any(f["title"] == "A 棟客餐廳提案與原 HTML 版本不同" for f in findings)
    assert all(
        f["status"] == "insufficient"
        for f in findings
        if f["title"] in {"HTML 靜態查核 · FOOTPRINT_INCONSISTENT", "HTML 靜態查核 · FLOOR_COVERAGE_VOID"}
    )

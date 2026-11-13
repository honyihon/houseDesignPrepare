"""Generated-data regressions only: no browser, WebGL or scene runtime."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import export_c_integrated_options as export
import pytest
from historical_support import assert_historical_sources
from lib.model3d_placement import overlaps

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def study():
    return json.loads((ROOT / "structured/candidates/c-integrated-options/layout.js").read_text().split(" = ", 1)[1].rstrip(";\n"))


@pytest.fixture(scope="module")
def models():
    source = (ROOT / "structured/candidates/c-integrated-options-3d.html").read_text()
    return json.loads(re.search(r"^\s*var DATA = (.+);\s*$", source, re.M).group(1))["bc_options"]


def test_sources_main_b32_requirements_archives_current_and_not_adopted(study):
    assert study["active_design"] == "baseline" and study["status"] == export.STATUS
    assert set(study["professional_status"].values()) == {"unknown"}
    assert all(d["status"] == "pending" for d in study["owner_decisions"])
    assert_historical_sources("c-integrated-options", study)
    for rel, sha in study["protected_main_hashes"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == sha, rel
    assert any(rel.startswith("inputs/revisions/R000/") for rel in study["protected_main_hashes"])
    assert [o["id"] for o in study["options"]] == [f"c-integrated-{h}" for h in (3000, 3600, 4000)]
    assert study["default_option"] == "c-integrated-3600"


def test_all_twelve_floors_html_svg_3d_exact_parity_and_full_coverage(study, models):
    totals = [0, 0, 0]
    for o in study["options"]:
        m = next(m["model"] for m in models["options"] if m["id"] == o["id"])
        assert [b["id"] for b in m["buildings"]] == ["C"]
        stairs = []
        base = 0
        for n, f in enumerate(o["plans"]["floors"]):
            totals[0] += 1
            totals[1] += len(f["rooms"])
            assert [f["width_mm"], f["depth_mm"]] == [6000, 17630]
            assert f["base_mm"] == base
            base += f["height_mm"]
            assert sum(r["geometry"]["w_mm"]*r["geometry"]["h_mm"] for r in f["rooms"]) == 6000*17630
            cells = {c["id"]: c for c in m["buildings"][0]["floors"][n]["cells"] if c.get("tour_active")}
            tree = ET.parse(ROOT / "structured/candidates/c-integrated-options" / f["plan_file"])
            assert tree.getroot().get("data-study-status") == export.STATUS
            for index, r in enumerate(f["rooms"]):
                assert not any(overlaps(export.shared.box(r["geometry"]), export.shared.box(s["geometry"])) for s in f["rooms"][index+1:])
                assert r["geometry"] == cells[r["id"]]["tour_mm"]
                assert r["features"] == cells[r["id"]]["tour_features"]
                if r["kind"] == "stair":
                    stairs.append(r["features"]["stair_footprint_mm"])
                    assert r["features"]["stair_geometry"]["fits_reserved_box"]
                for i in r["furniture"]:
                    totals[2] += 1
                    assert i["placement"] == cells[r["id"]]["furniture_placements"]["tour_mm"][i["id"]]
                    p = tree.find('.//*[@data-furniture-id="'+i["id"]+'"]')
                    assert p is not None and float(p.get("data-width-mm")) == i["width_mm"]
                if r["features"]["window_review"]["renderable"]:
                    group = tree.find('.//*[@data-room-id="'+r["id"]+'"]')
                    assert group.findall('.//*[@stroke="#3b7894"]')
            if n == 2:
                assert len(tree.findall('.//*[@data-exercise-allowance]')) == 3
        assert all(s == stairs[0] for s in stairs)
    assert totals == [12, 117, 141]


@pytest.mark.parametrize("index,living,master", [(0, 21.4096, 20.6736), (1, 18.256, 20.6736), (2, 16.6792, 19.0968)])
def test_original_area_targets_and_wall_sensitivity_not_silently_lowered(study, index, living, master):
    p = study["options"][index]["review"]["program"]
    rows = {r["id"]: r for r in p["upper_area_checks"]}
    assert rows["C.floor-2.living2"]["discussion_inset_sqm"] == living
    assert rows["C.floor-3.master_c"]["discussion_inset_sqm"] == master
    guest = rows["C.floor-2.guest2"]
    assert [r["area_sqm"] for r in guest["inset_sensitivity"]] == [9.3456, 9.1, 8.9179]
    assert guest["target_sqm"] == 12 and guest["minimum_sqm"] == 9 and guest["target_state"] == "below-target"
    assert rows["C.floor-2.living2"]["target_sqm"] == 22
    assert rows["C.floor-3.master_c"]["target_sqm"] == 20
    assert all(r["finished_and_legal_area"] is None for r in rows.values())
    assert "owner-decision-pending" in p["guest_location_deviation"]


def test_integrated_visitor_window_bed_projection_and_real_furniture(study):
    for o in study["options"]:
        p = o["review"]["program"]
        assert p["visitor_route"] == ["dining", "entrance", "public-bath"] and not p["wet_rooms_over_bed"]
        rooms = {r["id"]: r for f in o["plans"]["floors"] for r in f["rooms"]}
        assert rooms["C:floor-1:elder"]["features"]["window_mm"] == 2300
        assert rooms["C:floor-1:public-bath"]["features"]["window_review"]["renderable"]
        guest = rooms["C:floor-2:guestroom2f"]
        assert guest["features"]["window_face"] == "front" and guest["features"]["window_review"]["renderable"]
        assert {i["catalog_id"]: (i["width_mm"], i["depth_mm"]) for i in guest["furniture"]} == {
            "single-bed": (1050, 1880), "desk-140": (1400, 700), "wardrobe-180": (1800, 600)}
        kitchen = rooms["C:floor-2:kitchen2f"]
        assert {i["catalog_id"]: (i["width_mm"], i["depth_mm"], i["front_clearance_mm"]) for i in kitchen["furniture"]} == {
            "counter-240": (2400, 650, 900), "fridge-75": (750, 700, 600)}
        screen = o["review"]["coordinate_screen"]
        assert screen["fixed_body_failures"] == screen["pending_solver_items"] == screen["operation_limits"] == []
        assert not any(r["issue"] == "operation-vs-body" for r in screen["operation_sharing"])


@pytest.mark.parametrize("defect", ["zone-blocked", "zone-over-guest", "guest-window"])
def test_real_geometry_changes_are_rejected_not_just_matching_metadata(models, defect):
    b = copy.deepcopy(models["options"][0]["model"]["buildings"][0])
    cells = {c["key"]: c for c in b["floors"][2]["cells"] if c.get("tour_active")}
    zone = cells["fitness3f"]["tour_features"]["exercise_review"]["zones"][0]
    if defect == "zone-blocked":
        zone["aabb"] = dict(cells["fitness3f"]["furniture_placements"]["tour_mm"]["C:floor-3:fitness3f:furniture:yoga-mat"]["aabb"])
    elif defect == "zone-over-guest":
        zone["aabb"].update(minY=5000, maxY=6000)
    else:
        guest = next(c for c in b["floors"][1]["cells"] if c["key"] == "guestroom2f")
        guest["tour_features"]["window_review"]["renderable"] = False
    with pytest.raises(ValueError, match="Integrated C"):
        export.integrated_screen(b)

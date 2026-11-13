"""Small snapshot/geometry regressions; no scene, browser or parent rebuild."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import export_kaohsiung_options as export
import pytest

from house_design.b32_rear_right import body
from house_design.contracts import ContractError, sha256_file
from house_design.kaohsiung_options import review

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def studies():
    cfg = json.loads((ROOT/export.SOURCE).read_text())
    parent, history = export.frozen_base(cfg)
    return export.build_study(), cfg, parent, history


def option(data, oid):
    return next(o for o in data["options"] if o["id"] == oid)


def balcony(state, bid):
    return next(r for f in state["plans"]["floors"] if f["id"] == "floor-2"
        for r in f["rooms"] if r["key"] == ("balcony2f" if bid == "C" else "balcony2"))


def test_explicit_independent_scope_and_exact_historical_inputs(studies):
    study, _, _, history = studies
    assert len(study["options"]) == 5 and sum(len(o["states"]) for o in study["options"]) == 9
    assert study["adopted"] is False and study["rendered_qa"] == "not-run"
    assert not study["original_requirements_changed"] and not study["full_scene_or_parent_regeneration"]
    assert len(history) == 2
    for entry in history:
        assert sha256_file(ROOT/entry["historical_reference"]) == entry["frozen_sha256"]
        assert entry["current_sha256"] != entry["frozen_sha256"]
    assert set(study["professional_status"].values()) == {"unknown"}


def test_unexplained_parent_source_change_fails_before_new_plan(monkeypatch):
    cfg = json.loads((ROOT/export.SOURCE).read_text())
    real = export.sha256_file
    monkeypatch.setattr(export, "sha256_file", lambda p: "0"*64 if Path(p).as_posix().endswith("inputs/requirements.json") else real(p))
    with pytest.raises(ContractError, match="Unexplained frozen source change"):
        export.frozen_base(cfg)


def test_historical_reference_cannot_be_replaced_by_a_current_source_digest(monkeypatch):
    cfg = json.loads((ROOT/export.SOURCE).read_text())
    real = export.sha256_file
    monkeypatch.setattr(export, "sha256_file", lambda p: "0"*64 if str(p).endswith("20261027-before-model3d_review.py.txt") else real(p))
    with pytest.raises(ContractError, match="Historical opening-source bytes"):
        export.frozen_base(cfg)


@pytest.mark.parametrize("oid,area,green,woody", [
    ("a-rear-study", 8, 2.85, 3), ("b-rear-split", 9.12, 3.24, 4),
    ("b-front-split", 9.12, 3.24, 4), ("c-split", 9, 3.393, 4),
])
def test_garden_never_double_counts_equipment_operation_or_green(studies, oid, area, green, woody):
    study, _, _, _ = studies
    for state in option(study, oid)["states"]:
        result = state["review"]
        assert result["garden_nominal_sqm"] == area and result["proposed_soil_sqm"] == green
        assert result["proposed_green_ratio"] >= 1/3 and result["woody_count"] == woody
        assert not result["body_conflicts"] and not result["operation_conflicts"]
        assert not result["local_700mm_rectangle_route"]["coordinate_failures"]
        assert all(not r["coordinate_failures"] for r in result["service_local_700mm_routes"].values())
        assert result["lawful_area_roof_cover_cantilever_soil_depth"] == "unknown"


def test_b_both_entry_versions_and_all_three_first_floor_use_states_unchanged(studies):
    study, _, parent, _ = studies
    for oid, oldid in (("b-rear-split", "b-rear-refined"), ("b-front-split", "b-front-refined")):
        current, original = option(study, oid), option(parent, oldid)
        assert [s["id"] for s in current["states"]] == ["daily", "ritual", "carry"]
        for now, old in zip(current["states"], original["states"], strict=True):
            assert now["plans"]["floors"][0]["rooms"] == old["plans"]["floors"][0]["rooms"]
            assert balcony(now, "B")["features"]["hvac_units"] == balcony(old, "B")["features"]["hvac_units"]
    assert option(study, "b-rear-split")["states"][0]["plans"]["floors"][0]["rooms"] != option(study, "b-front-split")["states"][0]["plans"]["floors"][0]["rooms"]


def test_c_retains_original_entrance_one_washer_and_full_rack(studies):
    study, _, parent, _ = studies
    state = option(study, "c-split")["states"][0]
    room = balcony(state, "C")
    original = balcony(option(parent, "c-care-refined")["states"][0], "C")
    assert room["features"]["doors"] == original["features"]["doors"]
    assert len(state["review"]["service_local_700mm_routes"]) == 3
    rack = next(i for i in room["furniture"] if i["shape"] == "clothes-rack")
    assert rack["width_mm"] == 2400 and rack["depth_mm"] == 600 and rack["front_clearance_mm"] == 900
    assert body(rack) == [115, 1385, 600, 2400]
    assert sum(i["catalog_id"] == "washer" for f in state["plans"]["floors"] for r in f["rooms"] for i in r["furniture"]) == 1
    assert all(f["height_mm"] == old["height_mm"] and f["base_mm"] == old["base_mm"]
        for f, old in zip(state["plans"]["floors"], option(parent, "c-care-refined")["states"][0]["plans"]["floors"], strict=True))


def test_c_relocated_hvac_keeps_pair_and_every_route_copy_consistent(studies):
    study, _, _, _ = studies
    model = option(study, "c-split")["states"][0]["model"]
    units = [u for f in model["buildings"][0]["floors"] for c in f["cells"]
        if c.get("tour_active") for u in c["tour_features"].get("hvac_units", [])]
    for uid, x in (("C-AC01", 5470), ("C-AC03", 3300), ("C-AC07", 4300)):
        pair = [u for u in units if u["id"] == uid]
        assert len(pair) == 2 and {u["type"] for u in pair} == {"indoor", "outdoor"}
        assert pair[0]["route"] == pair[1]["route"] and pair[0]["route"]["compliance"] == "unknown"
        route = pair[0]["route"]
        assert all(p[0] == x for p in route["polyline_mm"][2:])
        assert route["estimated_routed_length_mm"] == sum(sum(abs(a-b) for a, b in zip(p, q, strict=True))
            for p, q in zip(route["polyline_mm"], route["polyline_mm"][1:], strict=False))+route["bend_service_allowance_mm"]


@pytest.mark.parametrize("mutation", ["garden-in-equipment", "reduced-soil", "shrink-rack", "door", "window", "height"])
def test_no_false_positive_after_geometry_or_product_tampering(studies, mutation):
    study, cfg, parent, _ = studies
    current = copy.deepcopy(option(study, "c-split")["states"][0]["plans"])
    base = option(parent, "c-care-refined")["states"][0]["plans"]
    state = {"plans": current}
    room = balcony(state, "C")
    if mutation == "garden-in-equipment":
        room["features"]["kaohsiung_zones"]["garden_mm"][0] = 0
        room["features"]["kaohsiung_zones"]["soil_rects_mm"] = [[115, 1765, 3770, 900]]
        room["features"]["kaohsiung_zones"]["woody_points_mm"] = [[590, 2215], [1530, 2215], [2470, 2215], [3410, 2215]]
    elif mutation == "reduced-soil":
        room["features"]["kaohsiung_zones"]["soil_rects_mm"][0][3] = 200
    elif mutation == "shrink-rack":
        next(i for i in room["furniture"] if i["shape"] == "clothes-rack")["width_mm"] = 1200
    elif mutation == "door":
        room["features"]["doors"][0]["width_mm"] = 500
    elif mutation == "window":
        current["floors"][0]["rooms"][0]["features"]["window_face"] = "rear"
    else:
        current["floors"][0]["height_mm"] = 4000
    with pytest.raises(ContractError):
        review(current, base, cfg["c"], "C")


def test_front_A_and_taller_C_are_costs_only_not_fake_geometry(studies):
    study, _, _, _ = studies
    a = study["cost_studies"]["a_front_uniform_depth_2200"]
    assert a["nominal_master_remaining_sqm"] == 15.48 and a["remaining_room_depth_mm"] == 2580
    c = study["cost_studies"]["c_arcade_height_stair"]
    assert c["proposed_required_run_and_landings_mm"] == 11*270+1000+1000
    assert c["additional_box_depth_needed_mm"] == 4970-4840 == 130
    assert c["proposed_riser_mm"]*24 == 4000
    assert c["keep_22_risers_at_4000mm"]["riser_mm"]*22 == 4000
    assert c["keep_22_risers_at_4000mm"]["nominal_box_spare_mm"] == 140


def test_html_and_svg_carry_same_zone_data_and_3d_adapter(studies):
    study, _, _, _ = studies
    viewer = export.render_viewer(study)
    parsed = json.loads(re.search(r"^\s*var DATA = (.+);\s*$", viewer, re.M)[1])["kaohsiung_options"]
    assert len(parsed["options"]) == 5 and "khBuildZones(mesh,group,base,features);" in viewer
    assert 'kaohsiung:khEvidence()' in viewer and 'dataset.studyKind="kaohsiung-options"' in viewer
    assert study["display_revision"] == parsed["display_revision"] == 2
    assert viewer.count('if(mesh){khAppendEquipmentReadout(list,mesh.userData.cell,featuresOf(mesh.userData.cell));}') == 1
    assert 'dataset.khDisplayRevision="2"' in viewer
    assert '"current-design-basis.html#"' not in viewer
    for o in study["options"]:
        for s in o["states"]:
            floor = s["plans"]["floors"][1]
            svg = export.svg_plan(o, s, floor)
            zone = balcony(s, o["building"])["features"].get("kaohsiung_zones")
            actual = svg.findall('.//*[@data-kh-zone]')
            assert len(actual) == (1+len(zone["soil_rects_mm"]) if zone else 0)
    source = export.render_index(study)
    assert source.count('id="kh-adoption-warning"') == 1
    assert source.index('id="kh-adoption-warning"') < source.index("<details")

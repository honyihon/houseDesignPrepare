"""Focused geometry, quotation and source-boundary checks for the five studies."""
import csv
import io
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from house_design.abc_next_improvements import CONFIG, OUT, build, inside, overlap
from house_design.contracts import ContractError, sha256_file
from scripts.export_abc_next_improvements import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_reject_changed_parent_before_reading_controls(tmp_path):
    (tmp_path/"inputs").mkdir()
    cfg = json.loads((ROOT/CONFIG).read_text())
    cfg["source_report"] = "source.json"
    (tmp_path/CONFIG).write_text(json.dumps(cfg))
    (tmp_path/"source.json").write_text("{}")
    with pytest.raises(ContractError, match="source changed"):
        build(tmp_path)


def test_original_and_rendered_controls_remain_immutable(report):
    controls = json.loads((ROOT/"inputs/abc-next-protected-controls.json").read_text())
    assert report["previous_rendered_sources_unchanged"] == 141
    assert report["protected_control_count"] == len(controls["hashes"]) == 149
    for path, expected in controls["hashes"].items():
        assert sha256_file(ROOT/path) == expected, path
    assert report["adopted"] is False
    assert report["professional_approval"] == "unknown"
    assert report["rendered_qa"] == "not-run-static-comparisons"
    assert "house_design/c_coordination.py" in report["source_hashes"]
    assert "house_design/contracts.py" in report["source_hashes"]


def test_a_control_edges_do_not_fit_blind_1200(report):
    a = report["a_care"]
    assert a["control_shared_bath_wall_mm"] == 1048
    assert a["control_shared_elder_wall_mm"] == 1120
    assert a["small"]["body_approach_hits"] == []
    row = next(r for r in a["clear_sensitivity"] if r["aperture_mm"] == 1050 and r["deduction_mm"] == 230)
    assert row["clear_mm"] == 820 and row["margin_to_900_mm"] == -80


def test_a_wider_conserves_area_and_full_furniture(report):
    a, w = report["a_care"], report["a_care"]["wider"]
    old = a["control_bath_rect_mm"]
    assert w["bath_rect_mm"] == [3800, 8952, 2200, 3108]
    assert w["area_transferred_to_dry_sqm"] == pytest.approx(.87024)
    assert w["bath_area_sqm"]+w["area_transferred_to_dry_sqm"] == pytest.approx(old[2]*old[3]/1e6)
    assert w["all_sizes_preserved"] is True
    assert w["elder_fixture_rects_mm"]["bed"][2:] == [1520, 1880]
    assert w["elder_fixture_rects_mm"]["wardrobe"][2:] == [600, 1200]
    assert w["bed_upper_wet_projection"] == []


def test_a_wider_door_shared_edges_and_park_do_not_hit_nominal_route(report):
    w = report["a_care"]["wider"]
    assert w["hall_rect_mm"][0]+w["hall_rect_mm"][2] == 3800
    assert w["elder_opening_x_mm"][0] >= 2400
    assert w["elder_opening_x_mm"][1] <= 3800
    assert w["route_body_hits"] == []
    assert w["elder_1200_route_side_gaps_mm"] == [20, 20]
    assert w["net_clearance_status"] == "unknown"
    for sw in w["elder_route_sweeps_mm"]:
        assert inside(sw, report["a_care"]["control_elder_rect_mm"])


def test_a_turn_and_fixtures_stay_within_explicit_wall_sensitivity(report):
    w = report["a_care"]["wider"]
    assert w["bath_inset_contains_bodies"] is True
    assert w["bath_turn_body_hits"] == []
    assert w["bath_fixture_body_hits"] == []
    assert inside(w["bath_turn_rect_mm"], w["bath_illustrative_inset_rect_mm"])
    assert w["bath_turn_min_fixture_gap_mm"] == 20


def test_b_distinguishes_backing_projection_from_altar(report):
    for o in report["b_coordination"]["options"]:
        assert o["wet_area_over_backing_by_floor_sqm"] == {"floor-2": 2.912, "floor-3": 1.376}
        assert all(w["over_altar_body_sqm"] == 0 for w in o["wet_projections"])
        assert any(p["item"].endswith(":toilet") for p in o["fixture_projections"])
        assert o["street_axis_x_mm"] == o["altar_axis_x_mm"] == 3400
        assert "另重排" in o["religious_decision"]


def test_b_retains_two_independent_layouts_and_all_three_states(report):
    options = report["b_coordination"]["options"]
    assert [o["id"] for o in options] == ["b-rear-split", "b-front-split"]
    for o in options:
        assert set(o["state_preserved"]) == {"daily", "ritual", "carry"}
        assert o["continuous_1500_carried_route"] == "unknown"
        assert o["stack_hole_size_mm"] is None
    assert options[0]["state_preserved"]["carry"]["plans_hash"] != options[1]["state_preserved"]["carry"]["plans_hash"]


def test_b_shaft_budget_does_not_claim_structural_or_route_approval(report):
    for o in report["b_coordination"]["options"]:
        rear = o["id"] == "b-rear-split"
        assert o["shaft_rect_mm"] == ([5600, 13480, 250, 250] if rear else [3510, 13480, 250, 250])
        assert o["bath_approach_remaining_nominal_width_mm"] == (1280 if rear else 1250)
        assert o["shaft_body_hits"] == o["shaft_operation_hits"] == []
        assert o["drain_terminal_mm"] is o["waterproofing_test_report"] is None
        if not rear:
            assert not overlap(o["shaft_rect_mm"], [3850, 13085, 900, 1130])


def test_c_same_guestroom_two_units_are_compared_without_deletion(report):
    h = report["c_hvac"]
    assert h["nominal_area_sqm"] == pytest.approx(10.36)
    assert [u["id"] for u in h["units"]] == ["C-AC04", "C-AC07"]
    assert h["pipe_length_difference_mm"] == 4100
    assert h["load_sensitivity"][-1]["kw"] == pytest.approx(2.4864)
    assert h["actual_load_kw"] is None
    assert h["selected_models"] == []
    assert h["options"][0]["retained_alternative"] == ["C-AC07"]


def test_c_landscape_alternatives_preserve_landscape_and_count_pipe_cost(report):
    g = report["c_landscape"]
    assert g["garden_sqm"] == 9
    assert g["soil_sqm"] == pytest.approx(3.393)
    assert g["woody_count"] == 4
    assert all(len(v["trees_mm"]) == 4 for v in g["variants"])
    control, trees, bypass = g["variants"]
    assert control["minimum_plan_distance_mm"] == 20
    assert trees["minimum_plan_distance_mm"] == 480
    assert bypass["minimum_plan_distance_mm"] == 840
    assert bypass["extra_length_mm"] == 5400
    assert bypass["estimated_pipe_length_mm"] == 20895 > 20000
    assert bypass["canopy_sensitivity"][-1]["margin_with_pipe_and_buffer_mm"] == 65
    assert bypass["trees_mm"] == control["trees_mm"]
    for point in bypass["polyline_mm"]:
        if point[1] <= 3900:
            assert point[2] in {6350, 4500}


def test_left_bypass_avoids_ac03_indoor_body_without_calling_connection_collision(report):
    bypass = report["c_landscape"]["variants"][-1]
    assert [4450, 3600, 6350] in bypass["polyline_mm"]
    assert all(hit["own_connection"] for hit in bypass["body_hits"])
    assert {r["id"] for r in report["c_landscape"]["other_front_routes"]} == {"C-AC03", "C-AC07"}


def test_toilet_fit_uses_707_total_projection_and_305_unknown_as_built(report):
    rows = report["products"]["fit_rows"]
    for r in (row for row in rows if row["product"] == "WC-T"):
        assert max(r["candidate_rect_mm"][2:]) == 707
        assert not inside(r["candidate_rect_mm"], r["representative_rect_mm"])
        assert r["candidate_rough_in_mm"] == 305 and r["rough_in_as_built_mm"] is None
        assert r["adopted"] is False
    assert any(r["status"] == "exceeds-representative-body" for r in rows)


def test_no_small_cabinet_silently_replaces_b_master_storage(report):
    rows = [r for r in report["products"]["fit_rows"] if r["room"] == "B:floor-2:master-bath2" and r["product"].startswith("BS-")]
    assert len(rows) == 4  # Two mutually exclusive B options, two basin candidates each.
    assert {r["status"] for r in rows} == {"storage-capacity-not-equivalent"}
    assert all(r["mounting_and_care_approval"] == "unknown" for r in rows)


def test_hvac_extra_height_and_incomplete_manual_not_papered_over(report):
    rows = report["products"]["hvac_rows"]
    assert len(rows) == 22*4  # A7 + B-rear4 + B-front4 + C7, never an order quantity.
    assert all(r["indoor_body_margins_whd_mm"][1] == -15 for r in rows)
    assert all(r["current_install_manual"] is None and r["service_area_and_actual_load_kw"] is None for r in rows)


def test_quote_response_fields_remain_blank_and_alternatives_separate(report):
    products = report["products"]
    assert products["counts_by_option"]["a-rear-study"]["bathrooms"] == 3
    assert products["counts_by_option"]["c-split"]["bathrooms"] == 4
    assert [p["historical_full_material_twd"] for p in products["packages"]] == [26360, 27060, 36490]
    for row in products["quote_rows"]:
        assert row["net_installed_twd"] is row["formal_quote_reference"] is row["model_returned"] is None
    assert sum(q["kind"] == "complete-door-set" for q in products["quote_rows"]) == len(products["door_rows"])
    assert all(q["quantity"] == 1 for q in products["quote_rows"])
    assert products["care_responses_changed"] is False
    assert products["formal_quote_status"] == "not-received"


def test_artifacts_are_small_accessible_source_bound_and_current(report):
    files = render(report)
    assert len(files) == 15
    for name, value in files.items():
        assert (ROOT/OUT/name).read_bytes() == value.encode(), name
        if name.endswith(".svg"):
            el = ET.fromstring(value)
            assert float(el.attrib["width"])*float(el.attrib["height"]) <= 1_600_000
            assert el.find("{http://www.w3.org/2000/svg}title") is not None
            assert report["source_layout_report_sha256"] in value
    quotes = list(csv.DictReader(io.StringIO(files["quote-schedule.csv"].lstrip("\ufeff"))))
    assert quotes and all(q["含工淨價"] == q["正式報價單號"] == "" for q in quotes)
    assert 'lang="zh-Hant"' in files["index.html"]
    assert "未採用的深化比較" in files["index.html"]
    assert files["A01-care-doors.svg"].count('data-element-kind="candidate-window"') == 3
    assert 'data-element-kind="candidate-window"' in files["C01-guest-hvac.svg"]
    assert files["C02-landscape-pipes.svg"].count('data-element-kind="outdoor-unit-footprint"') == 9
    assert overlap([0, 0, 10, 10], [10, 0, 5, 5]) == 0

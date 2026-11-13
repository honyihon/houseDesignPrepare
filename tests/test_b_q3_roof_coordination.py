"""Same-revision Q3/RF geometry contracts; no runtime or professional approval."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from house_design.b_q3_roof_coordination import CONFIG, OUT, build
from house_design.b_upper_replan import rect
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_q3_roof_coordination import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_frozen_parents_and_original_controls_are_not_rewritten_or_adopted(report):
    before = {n: (ROOT/n).read_bytes() for n in report["config"]["pinned_sources"]}
    assert report["report_hash"] == build(ROOT)["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in before}
    assert report["protected_controls_unchanged"] == 149 and not report["adopted"]
    assert not report["primary_abc_or_3d_changed"] and not report["all_original_requirements_met"]
    assert report["rendered_qa"] == "not-run" and report["professional_approval"] == "unknown"
    assert report["actual_site_or_product_data_received"] == 0
    assert not report["original_Q3_non_RF_geometry_changed"] and not report["first_floor_or_two_ground_entry_variants_changed"]


def test_new_arrival_is_the_exact_Q3_full_platform_condition(report):
    q3 = json.loads((ROOT/report["config"]["q3_report"]).read_text())
    assert report["q3_primary_hash"] == stable_hash(q3["primary"])
    assert report["floor_requirements"]["landing_mm"] == q3["upper_stairs"]["primary"]["floor_landing_mm"] == [80, 4770, 2200, 1000]
    assert report["Q3_KTV_area_reference_sqm"] == 20.1889 and report["RF_arrival_shift_from_original_mm"] == 800
    assert report["floor_requirements"]["vestibule_mm"] == [115, 4015, 2170, 755]
    assert report["new_floor_slab_and_door_thresholds_required"]
    assert report["floor_requirements"]["roof_floor_full_width_and_same_level_required_not_verified"]
    assert not report["floor_requirements"]["entire_stair_headroom_slab_support_or_penthouse_legality_approved"]


def test_rf_side_aperture_stays_original_and_does_not_use_third_floor_side_door(report):
    assert report["config"]["roof_enclosure_mm"] == [0, 3900, 2400, 5200]
    assert report["floor_requirements"]["enclosure_nominal_sqm"] == 12.48
    assert report["floor_requirements"]["original_RF_side_door_center_y_mm"] == pytest.approx(4400)
    assert not report["old_RF_enclosure_or_side_aperture_moved"] and not report["floor_requirements"]["side_door_moved"]
    for o in report["options"]:
        assert o["side_door"]["a"] == [2400, 3900] and o["side_door"]["b"] == [2400, 4900]
        assert o["front_door"] == {"a": [1150, 3900], "b": [2280, 3900], "hinge": "left", "opens": "inside"}


def test_floor_does_not_cap_q3_treads_or_invent_a_solid_stair_room(report):
    f = report["floor_requirements"]
    assert f["stairwell_keep_open_mm"] == [80, 5770, 2200, 3260]
    assert len(f["Q3_incoming_treads"]) == len(f["rejected_full_enclosure_cap_tread_ids"]) == 16
    assert not f["covered_Q3_tread_ids"]
    indoor = rect(f["landing_mm"]).union(rect(f["vestibule_mm"]))
    assert all(indoor.intersection(rect(s["rect_mm"])).area == 0 for s in f["Q3_incoming_treads"])
    assert indoor.intersection(rect(f["stairwell_keep_open_mm"])).area == 0
    assert not report["new_solid_slab_over_incoming_stairwell_allowed"]


def test_equipment_and_furniture_are_copied_exactly_not_shrunk_to_fit(report):
    daily = json.loads((ROOT/report["config"]["daily_report"]).read_text())
    roof = json.loads((ROOT/daily["config"]["parent_report"]).read_text())
    for o in report["options"]:
        d = next(d for d in daily["options"] if d["id"] == o["old_daily_option_id"])
        r = next(r for r in roof["options"] if r["id"] == o["equipment_option_id"])
        assert o["equipment_reference_hash"] == stable_hash(r) and o["daily_reference_hash"] == stable_hash(d)
        assert o["equipment_reservations"] == r["reservations"] and o["furniture"] == d["furniture"]
        assert not o["all_actual_devices_piping_or_products_approved"]


def test_each_option_has_recomputed_daily_and_necessary_inspection_routes(report):
    for o in report["options"]:
        assert len(o["routes"]) == 9
        assert sum(r["use"] == "daily" for r in o["routes"]) == 3
        assert sum(r["use"] == "necessary-inspection" for r in o["routes"]) == 6
        assert all(r["inside_explicit_same_revision_surface"] and not r["fixed_body_hits"] and not r["void_or_guard_hit"] for r in o["routes"])
        assert all(r["over_protected_sqm"] == 0 for r in o["routes"] if r["use"] == "daily")
        assert any(r["over_protected_sqm"] > 0 for r in o["routes"] if r["use"] == "necessary-inspection")
        assert all(r["actual_human_transport_or_religious_approval"] == "unknown" for r in o["routes"])
        assert o["new_inspection_results_recomputed_not_inherited"]


def test_front_heat_pump_inspection_avoids_old_042sqm_rack_collision(report):
    front, rear = report["options"]
    assert front["prior_heat_pump_route_over_drying_rack_sqm"] == .42
    assert front["front_heat_pump_inspection_rerouted_around_drying_rack"]
    route = next(r for r in front["routes"] if r["id"] == "inspect-heat-pump-boundary")
    assert route["door"] == "front" and not route["fixed_body_hits"] and route["over_protected_sqm"] == 0
    assert rear["prior_heat_pump_route_over_drying_rack_sqm"] == 0
    assert not rear["front_heat_pump_inspection_rerouted_around_drying_rack"]
    assert next(r for r in rear["routes"] if r["id"] == "inspect-heat-pump-boundary")["door"] == "side"


def test_independent_nine_door_states_do_not_pass_half_or_closed(report):
    assert sum(len(o["door_states"]) for o in report["options"]) == 18
    for o in report["options"]:
        assert len({(s["front"], s["side"]) for s in o["door_states"]}) == 9
        assert not o["sampled_swing_body_hits"]
        for state in o["door_states"]:
            assert not state["fixed_body_hits"] and not state["leaf_pair_hit"]
            for route in o["routes"]:
                expected = [route["door"]] if route["door"] and state[route["door"]] != "open" else []
                assert state["route_blockers"][route["id"]] == expected


def test_900_daily_route_is_conditional_and_not_applied_to_770_side_aperture(report):
    assert report["front_door_nominal_mm"] == 1130 and report["front_door_clear_budget_mm"] == 900
    assert report["side_door_nominal_mm"] == 1000 and report["side_door_clear_budget_mm"] == 770
    for o in report["options"]:
        assert {r["width_mm"] for r in o["arrival_width_cases"]} == {700, 800, 900}
        assert all(r["inside_required_full_platform_and_vestibule"] and not r["body_hits"] and not r["fully_open_front_door_hit"] and r["over_protected_sqm"] == 0 for r in o["arrival_width_cases"])
        assert all(r["product_or_care_approval"] == "unknown" for r in o["arrival_width_cases"])
        assert all(r["width_mm"] == 700 for r in o["routes"] if r["use"] == "necessary-inspection")


def test_original_roof_goal_sharing_and_other_design_deficits_are_not_hidden(report):
    assert report["parent_daily_capacity"]["RF_deck_original_target_sqm"] == 24
    assert report["parent_daily_capacity"]["front_before_equipment_with_edge_budget_sqm"] == 21.83945
    assert not report["RF_indoor_vestibule_added_to_outdoor_goal"] and not report["all_actual_devices_and_piping_fitted"]
    assert report["options"][0]["arrival_shares_folding_operation"]
    assert not report["options"][1]["arrival_shares_folding_operation"]
    assert all(not o["RF24_goal_met_or_reduced"] for o in report["options"])
    assert "P3" in report["config"]["limits"][-2] and "150mm" in report["config"]["limits"][-2]


@pytest.mark.parametrize("defect", ["cap-stair", "move-side", "daily-protected", "restore-colliding-route", "change-pins"])
def test_known_regressions_stop_same_revision_export(monkeypatch, defect):
    import house_design.b_q3_roof_coordination as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    if defect == "cap-stair":
        cfg["vestibule_floor_mm"] = [115, 4015, 2170, 5015]
    elif defect == "move-side":
        cfg["side_door"]["a"][1] += 800
        cfg["side_door"]["b"][1] += 800
    elif defect == "daily-protected":
        cfg["daily_arrival_route_mm"] = [[1780, 5270], [2850, 4400], [3150, 2500]]
    elif defect == "restore-colliding-route":
        cfg["front_heat_pump_inspection_mm"] = [[1780, 5270], [1780, 4400], [2850, 4400], [5350, 4400], [5350, 2500], [1715, 2500], [1715, 1715]]
    else:
        cfg["pinned_sources"][cfg["q3_report"]] = "0"*64
    monkeypatch.setattr(module, "read_json", lambda p: cfg if p == ROOT/CONFIG else read(p))
    with pytest.raises(ContractError):
        build(ROOT)


def test_static_output_source_seals_links_bounds_and_blank_replies(report):
    files = render(report)
    assert len(files) == 10 and sum(n.endswith(".svg") for n in files) == 3
    assert all((ROOT/OUT/n).read_bytes() == value.encode() for n, value in files.items())
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in report["source_hashes"].items())
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n, h in manifest["artifacts"].items())
    for name, value in files.items():
        if name.endswith(".svg"):
            svg = ET.fromstring(value)
            assert int(svg.attrib["width"])*int(svg.attrib["height"]) <= 1_680_000
            assert all(0 <= float(t.attrib["y"]) < 1200 for t in svg.iter() if t.tag.endswith("text"))
    assert all((ROOT/OUT/ref).is_file() for ref in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]))
    assert "未採用" in files["index.html"] and "900／770" in files["index.html"] and "2200×3260" in files["index.html"]
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"])

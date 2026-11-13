"""Bounded laundry geometry and source tests; no browser, scene or appliance selection."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from house_design.abc_ground_laundry import CONFIG, OUT, build, screen_plan, validate_config
from house_design.contracts import ContractError, stable_hash
from scripts.export_abc_ground_laundry import render

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text())


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_latest_owner_direction_is_distinct_from_original_models_or_purchases(report):
    assert report["shared_active_group_direction"] == 1
    assert report["owner_direction"]["confirmed"]["A_upper_floor_washer_space_required"]
    assert report["formal_requirement_statuses"] == {"candidate": 66}
    assert report["formal_register_statuses"] == {"unknown": 105}
    assert report["protected_controls_unchanged"] == 149
    for key in ["adopted", "host_building_adopted", "original_ABC_or_3d_changed", "accepted_storage_viewers_changed", "A_upper_active_machine_count_decided"]:
        assert report[key] is False
    assert report["professional_approval"] == "unknown" and report["rendered_qa"] == "not-run"
    assert report["actual_conditions_received"] == 0 and all(v is None for v in report["actual_conditions"].values())


def test_compact_layout_retains_kitchen_but_discloses_lowered_drying_and_sequential_operation(report):
    compact = report["A1_options"][0]
    screen = compact["screen"]
    assert compact["kitchen_loss_nominal_sqm"] == 0 and not compact["source_filter_moved"]
    assert screen["nominal_region_sqm"] == 10.8
    assert screen["local_route_inside_finished"] and not screen["local_route_fixed_hits"]
    assert screen["turn_lowered_body_hits"] == ["lowered-drying-envelope"]
    assert screen["turn_if_drying_fully_stowed_body_hits"] == []
    assert not screen["stowed_drying_headroom_and_product_verified"]
    assert screen["operation_shared"] == [{"a": "washer-loading", "b": "dryer-loading", "overlap_sqm": .253}]
    assert screen["operation_door_approach_shared"]
    assert screen["existing_fixed_outside_finished"]  # Inherited 80mm reservations do not silently pass 115mm finish.


def test_deeper_alternative_reports_exact_kitchen_loss_without_taking_bedroom_or_arcade(report):
    deeper = report["A1_options"][1]
    assert deeper["screen"]["turn_inside_finished"] and deeper["screen"]["turn_lowered_body_hits"] == []
    assert deeper["kitchen_area"]["before_nominal_sqm"] == 9.048
    assert deeper["kitchen_area"]["after_nominal_sqm"] == 6.816
    assert deeper["kitchen_area"]["loss_nominal_sqm"] == 2.232
    assert deeper["kitchen_area"]["original_fixture_bodies_inside_nominal"]
    assert not deeper["kitchen_area"]["finished_kitchen_and_door_sweeps_verified"]
    moved = next(i for i in deeper["bodies"] if i["id"] == "moved-water-filter")
    assert moved["rect_mm"][2:] == [900, 650] and deeper["source_filter_moved"]
    assert deeper["region_rects_mm"][-1] == [0, 14900, 2400, 930]


def test_machine_bays_remain_clear_of_listed_fixed_bodies_and_operations(report):
    for plan in [*report["A1_options"], report["A2_reservation"]]:
        result = plan["screen"]
        for key in ["body_pair_hits", "new_body_fixed_hits", "operation_fixed_hits", "operation_other_body_hits",
                "new_body_outside_finished", "operation_outside_finished"]:
            assert result[key] == []
        assert not result["whole_route_or_care_approved"] and not result["product_door_sweeps_verified"]


def test_doors_and_shared_edge_cannot_be_hidden_by_a_large_local_turn_square(report):
    assert all(d["nominal_mm"] == 900 and d["assumed_clear_mm"] == 670 and d["shortfall_mm"] == 230 for d in report["doors"])
    assert all(d["actual_clear_mm"] is None and not d["verified"] for d in report["doors"])
    entry = report["A1_entry_constraint"]
    assert entry["A1_public_hall_to_kitchen_nominal_shared_edge_mm"] == 1040
    assert entry["required_nominal_for_900_clear_if_frame230_mm"] == 1130
    assert entry["widening_requires_adjacent_replanning"]
    assert not entry["MDF_alcove_released"] and not entry["bedroom_pass_through_proposed"]
    assert not report["cross_building_route"]["approved"] and report["cross_building_route"]["site_order"] is None


def test_A_upper_reservation_and_C_dormant_space_do_not_add_or_remove_source_machines(report):
    upper = report["A2_reservation"]
    assert upper["floor"] == "floor-2" and upper["room"] == "balcony2"
    assert upper["bodies"][0]["rect_mm"] == [3450, 15945, 850, 750]
    assert upper["screen"]["operation_door_approach_shared"]
    dormant = report["C2_space_retained"]
    assert dormant["source_item"] == "C:floor-2:balcony2f:furniture:washer"
    assert dormant["rect_mm"][2:] == [650, 650]
    assert dormant["new_direction_use"] == "temporarily-inactive-reserve-space"
    assert not dormant["removed_from_original"] and not dormant["source_model_changed"]
    assert len(report["B_source_states_retained"]) == 6
    assert {s["option"] for s in report["B_source_states_retained"]} == {"b-rear-split", "b-front-split"}


@pytest.mark.parametrize("defect", ["adopt", "groups", "C2", "A-upper", "B-fallback", "filled-actual"])
def test_owner_intent_and_unfilled_actual_conditions_cannot_be_relaxed(defect):
    cfg = read(CONFIG)
    owner = read(cfg["owner_reference"])
    if defect == "adopt":
        cfg["adopted"] = True
    elif defect == "groups":
        owner["confirmed"]["shared_group_at_ground_floor"] = 3
    elif defect == "C2":
        owner["confirmed"]["C_floor2_initial_washer_use"] = "removed"
    elif defect == "A-upper":
        owner["confirmed"]["A_upper_floor_washer_space_required"] = False
    elif defect == "B-fallback":
        cfg["source_options"]["B"].pop()
    else:
        cfg["open_actual_conditions"]["common_route_length_mm"] = 0
    with pytest.raises(ContractError):
        validate_config(cfg, owner)


@pytest.mark.parametrize("defect", ["HVAC-body", "outside", "operation", "route"])
def test_bad_local_positions_and_paths_are_rejected(report, defect):
    plan = copy.deepcopy(report["A1_options"][0])
    if defect == "HVAC-body":
        plan["bodies"][0]["rect_mm"][:2] = [4500, 16000]
    elif defect == "outside":
        plan["bodies"][0]["rect_mm"][0] = 5800
    elif defect == "operation":
        plan["operations"][0]["rect_mm"][:2] = plan["bodies"][1]["rect_mm"][:2]
    else:
        plan["route_points_mm"] = [[4000, 16000], [4900, 17000]]
    with pytest.raises(ContractError, match="Laundry local geometry conflict"):
        screen_plan(plan, plan["fixed"], 115, 900)


def test_frozen_inputs_and_accepted_zips_stay_unchanged_on_build(report):
    before = {name: (ROOT/name).read_bytes() for name in report["source_hashes"]}
    assert build(ROOT)["report_hash"] == report["report_hash"]
    assert before == {name: (ROOT/name).read_bytes() for name in before}
    for name, checksum in report["source_hashes"].items():
        assert hashlib.sha256(before[name]).hexdigest() == checksum
    assert stable_hash({k: v for k, v in report.items() if k != "report_hash"}) == report["report_hash"]


def test_outputs_are_bounded_vectors_with_visible_names_and_matching_manifest(report):
    files = render(report)
    assert len(files) == 9 and all((ROOT/OUT/n).read_bytes() == text.encode() for n, text in files.items())
    for name in ["A1-compact.svg", "A1-deeper.svg", "A2-reserve.svg"]:
        svg = ET.fromstring(files[name])
        assert svg.attrib["viewBox"] == "0 0 1400 1200"
        assert svg.attrib["width"] == "1400" and svg.attrib["height"] == "1200"
        assert "洗衣備位" in files[name] and "未採用" in files[name]
        assert not any(e.tag.rsplit("}", 1)[-1] in {"image", "script", "foreignObject"} for e in svg.iter())
    assert "兩個A一樓900名義門" in files["A1-compact.svg"]
    assert "2.232" in files["A1-deeper.svg"]
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == checksum for n, checksum in manifest["artifacts"].items())

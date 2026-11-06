"""Bounded stair/landing regression evidence, never a full scene or legal test."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import export_c_stair_landing as export
import pytest

from house_design.c_balcony_coordination import _area, _overlap
from house_design.c_stair_landing import CONFIG, build, detail, flight_surfaces, headroom_proxy
from house_design.contracts import ContractError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def source():
    cfg = json.loads((ROOT/CONFIG).read_text())
    parent = json.loads((ROOT/cfg["base_report"]).read_text())
    option = next(o for o in parent["options"] if o["id"] == "c-split")
    return cfg, option["states"][0]["plans"]


def test_shared_apron_keeps_1000_landing_and_records_reallocated_front_budget(source):
    cfg, plans = source
    original = copy.deepcopy(plans)
    r = detail(plans, cfg)
    assert plans == original
    assert r["core_rect_mm"] == [2400, 8960, 3600, 4840]
    assert r["shared_level_apron_mm"] == [3720, 8760, 2200, 1000]
    assert r["shared_front_strip_mm"] == [3720, 8760, 2200, 200]
    assert r["first_stair"]["riser_mm"] == pytest.approx(4000/24)
    assert r["first_stair"]["first_step_start_y_mm"] == 9760
    assert r["first_stair"]["middle_start_y_mm"] == 12730
    assert r["first_stair"]["whole_core_extension_mm"] == 0
    assert r["first_stair"]["original_front_70mm_reallocated_to_shared_level_floor"] == 70
    assert r["first_stair"]["rear_70mm_nominal_budget_retained"] == 70
    assert len([s for s in r["surfaces"] if s["storey"] == "floor-1" and s["kind"] == "tread"]) == 22


def test_shared_floor_is_reported_and_never_sold_as_new_area(source):
    cfg, plans = source
    r = detail(plans, cfg)
    assert all(a["union_shared_sqm"] == pytest.approx(.44) for a in r["shared_floor_areas"])
    first = {a["room"]: a["shared_sqm"] for a in r["shared_floor_areas"][0]["affected"]}
    assert first == {"C:floor-1:living-hall": pytest.approx(.056), "C:floor-1:living-right": pytest.approx(.384)}
    assert not r["landing_furniture_and_operation_conflicts"]
    assert r["source_furniture_count"] == 49
    assert r["third_floor_front_hall_mm"] == [2400, 7600, 3600, 1360]
    assert r["floor_bases_mm"] == {"floor-1": 0, "floor-2": 4000, "floor-3": 7000, "floor-4": 10000}
    for s in r["surfaces"]:
        if s["kind"] == "tread":
            assert _area(_overlap(s["rect_mm"], r["left_public_corridor_nominal_mm"])) == 0


def test_second_floor_platform_must_not_cap_last_incoming_tread(source):
    cfg, plans = source
    r = detail(plans, cfg)
    assert r["second_floor_floor_level_platform_removed_mm"] == [4720, 9760, 1200, 270]
    assert r["removed_platform_sqm"] == pytest.approx(.324)
    assert r["naive_full_width_platform_gap_over_last_incoming_tread_mm"] == pytest.approx(50/3)
    assert not r["headroom_proxy"]["below_target"]
    assert r["headroom_proxy"]["minimum_sampled_gap_mm"] == pytest.approx(2850)
    assert r["headroom_proxy"]["samples_without_modelled_overhead"] > 0
    old_platform = {"id": "unsafe-old-full-platform", "rect_mm": [3720, 9030, 2200, 1000],
        "top_z_mm": 4000, "kind": "departure", "storey": "floor-2"}
    bad = headroom_proxy([*r["surfaces"], old_platform], 150, 2000)
    assert any(s["walking_surface"] == "floor-1:return-23" for s in bad["below_target"])


def test_shared_apron_conflicting_with_furniture_is_rejected(source):
    cfg, plans = source
    changed = copy.deepcopy(plans)
    room = next(r for r in changed["floors"][1]["rooms"] if r["key"] == "living2f")
    room["furniture"][0]["placement"]["aabb"] = {"minX": 4900, "maxX": 5900, "minY": 8700, "maxY": 8900}
    with pytest.raises(ContractError, match="Shared landing clashes"):
        detail(changed, cfg)


def test_opening_widths_and_new_conditions_are_explicit(source):
    cfg, plans = source
    r = detail(plans, cfg)
    assert [o["opening_width_mm"] for o in r["opening_proposals"]] == [3020, 2200]
    for opening in r["opening_proposals"]:
        assert sum(b-a for a, b in (n["x_range_mm"] for n in opening["neighbors"])) == opening["opening_width_mm"]
    assert r["legal_fire_separation_opening_structure_and_actual_headroom"] == "unknown"
    assert r["complete_scheme_adopted"] is False
    assert r["comparison_250mm_tread"] == "retained-in-c-balcony-coordination-not-used-here"
    assert "redesign-door" in r["if_independent_fire_or_privacy_door_required"]


def test_inconsistent_tread_run_or_wrong_study_direction_fails(source):
    cfg, plans = source
    with pytest.raises(ContractError, match="Flight run and landings"):
        flight_surfaces("floor-1", 0, 4000, [3720, 9030, 2200, 4700], 24, 270, 1000, 1000, 1000)
    changed = copy.deepcopy(cfg)
    changed["first_stair"]["tread_mm"] = 250
    with pytest.raises(ContractError, match="approved study direction"):
        detail(plans, changed)


def test_source_hash_change_cannot_be_relabelled_as_same_detail(monkeypatch):
    import house_design.c_stair_landing as stairs

    real = stairs.sha256_file
    monkeypatch.setattr(stairs, "sha256_file", lambda p: "0"*64 if p.name == "requirements.json" else real(p))
    with pytest.raises(ContractError, match="Frozen C dependency changed"):
        build(ROOT)


def test_artifacts_are_fresh_bounded_and_describe_scope():
    outputs = export.artifacts(ROOT)
    assert len(outputs) == 5
    for name, content in outputs.items():
        assert (ROOT/name).read_text() == content
        if not name.endswith(".svg"):
            continue
        root = ET.fromstring(content)
        assert int(root.get("width"))*int(root.get("height")) <= 1600000
        assert root.get("aria-labelledby") == "title desc"
    plan = "".join(ET.fromstring(outputs[export.OUT+"/plans-1f-2f.svg"]).itertext())
    assert "完整1000mm" in plan and "200mm" in plan and "3020" in plan
    section = ET.fromstring(outputs[export.OUT+"/return-flight-section.svg"])
    assert "離散踏面中心試算不等於實際淨高" in section.find("{http://www.w3.org/2000/svg}desc").text
    privacy = ET.fromstring(outputs[export.OUT+"/partition-options.svg"])
    privacy_text = "".join(privacy.itertext())
    assert "前置可關門" in privacy.find("{http://www.w3.org/2000/svg}title").text
    assert "屋主已接受" in privacy_text and "等待屋主分隔偏好" not in privacy_text
    door_fit = ET.fromstring(outputs[export.OUT+"/door-fit-and-side-door.svg"])
    assert "900" in "".join(door_fit.itertext())


def test_forward_doors_keep_approaches_and_record_public_space_cost(source):
    cfg, plans = source
    r = detail(plans, cfg)
    comparison = r["front_partition_comparison"]
    assert comparison["owner_preference"] == "forward-closing-door"
    assert comparison["owner_confirmation"]["quote"] == "前置可關門版 可以接受"
    doors = next(o for o in comparison["options"] if o["id"] == "forward-closing-door")
    assert doors["selected"] is True
    assert next(o for o in comparison["options"] if o["id"] == "shared-open")["selected"] is False
    assert r["complete_scheme_adopted"] is False and r["professional_approval"] == "unknown"
    for door in doors["floor_details"]:
        assert not door["furniture_body_and_operation_conflicts"]
        assert door["existing_public_floor_used_sqm"] == pytest.approx(1.476)
        assert door["additional_public_floor_in_pocket_sqm"] == pytest.approx(1.036)
        assert door["actual_door_clear_width_mm"] is None
        assert door["wall_to_shared_apron_gap_mm"] == 160
        assert door["inner_wall_face_to_first_riser_mm"] == 1160
        assert door["inner_leaf_face_to_first_riser_mm"] == 1060
        assert door["leaf_to_shared_apron_gap_mm"] == 60
        assert door["closed_leaf_rect_mm"][1::2] == door["parking_rect_mm"][1::2]
        assert door["approach_rectangles_mm"]["outside"][2:] == [1400, 900]
        for wall in [*door["wall_budgets_mm"], door["parking_rect_mm"]]:
            assert not _area(_overlap(wall, r["shared_level_apron_mm"]))
        assert not any(_area(_overlap(door["parking_rect_mm"], rect))
            for rect in door["approach_rectangles_mm"].values())


@pytest.mark.parametrize("index,opening,parking", [
    (0, [2800, 4000], [4000, 5200]),
    (1, [3600, 4800], [4800, 6000]),
])
def test_rejected_gate_positions_cannot_hide_sofa_or_operation_conflicts(source, index, opening, parking):
    cfg, plans = source
    wrong = copy.deepcopy(cfg)
    floor = wrong["front_partition_comparison"]["floors"][index]
    floor.update(opening_x_mm=opening, sliding_parking_x_mm=parking)
    with pytest.raises(ContractError, match="overlaps furniture"):
        detail(plans, wrong)


def test_open_door_sightlines_and_side_bypass_still_limit_privacy_and_sound_claims(source):
    cfg, plans = source
    comparison = detail(plans, cfg)["front_partition_comparison"]
    sight = comparison["sightline_proxy_first_floor"]
    assert sight["all_open_rays_blocked"] is False
    assert sum(r["passes_open_aperture_in_plan"] for r in sight["rays"]) == 2
    assert all(r["closed_opaque_panel_intercepts_at_plane"] for r in sight["rays"])
    assert comparison["second_floor_bypass"]["closing_front_door_does_not_close_side_door"] is True
    assert comparison["sound_reduction_rating_dB"] is None
    assert comparison["regulatory_fire_and_stair_compartment"].startswith("unknown")


def test_clear_width_sensitivity_never_turns_nominal_opening_into_completed_width(source):
    cfg, plans = source
    study = detail(plans, cfg)["door_fit_review"]
    for floor in study["floor_details"]:
        assert floor["actual_completed_clear_width_mm"] is None
        assert floor["clear_width_target_mm"] == 900
        cases = {c["total_frame_stop_overlap_mm"]: c for c in floor["clear_width_cases"]}
        assert cases[300]["calculated_clear_width_mm"] == 900
        assert cases[350]["margin_to_900mm_mm"] == -50
    assert study["side_door"]["source_nominal_width_mm"] == 900
    assert study["side_door"]["source_900mm_has_no_extra_frame_budget_for_900mm_goal"] is True
    assert study["side_door"]["actual_completed_clear_width_mm"] is None


def test_deeper_track_cannot_be_fixed_by_moving_gate_into_tv_operation(source):
    cfg, plans = source
    study = detail(plans, cfg)["door_fit_review"]
    second = next(f for f in study["floor_details"] if f["floor"] == "floor-2")
    cases = {c["assumed_track_leaf_depth_mm"]: c for c in second["track_and_leaf_depth_cases"]}
    assert cases[100]["margin_to_apron_at_current_line_mm"] == 60
    assert cases[180]["forward_shift_to_keep_original_60mm_budget_mm"] == 80
    assert cases[180]["extra_public_floor_if_shifted_sqm"] == pytest.approx(.288)
    assert cases[180]["shifted_outside_approach_mm"][1] == 7520
    assert not cases[180]["shifted_outside_approach_conflicts"]
    assert {c["item"] for c in cases[220]["shifted_outside_approach_conflicts"]} == {"C:floor-2:living2f:furniture:tv"}
    assert all(c["shift_is_only_sensitivity_not_selected_new_door_line"] for c in cases.values())


def test_larger_door_leaf_has_different_parking_limits_on_each_floor(source):
    cfg, plans = source
    study = detail(plans, cfg)["door_fit_review"]
    first = next(f for f in study["floor_details"] if f["floor"] == "floor-1")
    second = next(f for f in study["floor_details"] if f["floor"] == "floor-2")
    assert first["leaf_parking_available_before_corner_budget_mm"] == 1800
    assert second["leaf_parking_available_before_corner_budget_mm"] == 1500
    assert next(c for c in second["leaf_width_cases"] if c["assumed_leaf_width_mm"] == 1600)["parking_margin_mm"] == -100
    assert study["selected_product"] is None


def test_front_door_selection_does_not_remove_the_existing_second_floor_side_route(source):
    cfg, plans = source
    study = detail(plans, cfg)["door_fit_review"]
    states = {(s["front_door_open"], s["side_door_open"]): s for s in study["two_door_states"]}
    assert len(states[(True, True)]["specified_unobstructed_doorway_paths"]) == 2
    assert states[(False, True)]["specified_unobstructed_doorway_paths"] == [
        ["living2f", "living-nook", "day-reserve", "stair2f"]]
    assert not states[(False, False)]["specified_unobstructed_doorway_paths"]
    assert study["both_closed_does_not_prove_airtight_or_soundproof"] is True
    assert all("not-an-egress" in s["people_can_open_closed_doors_and_air_leakage"] for s in states.values())

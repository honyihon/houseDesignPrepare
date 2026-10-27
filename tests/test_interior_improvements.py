"""Small data/serialization checks. Never build a scene, run WebGL or a browser."""
from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import export_interior_improvements as export
import pytest

from house_design.b32_daily_use import review_daily_use, subtract_rect
from house_design.b32_service_detail import _circle_hits, _inside
from house_design.b32_services import _covered, _hits
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash


@pytest.fixture(scope="module")
def study():
    return export.build_study()


def option(study, oid):
    return next(o for o in study["options"] if o["id"] == oid)


def rooms(o, index):
    return {r["key"]: r for r in o["plans"]["floors"][index]["rooms"]}


def test_ten_independent_complete_options_and_original_unknowns(study):
    assert study["status"] == "comparison-only-not-adopted" and study["rendered_qa"] == "not-run"
    assert [o["id"] for o in study["options"]] == ["b-rear-service", "b-front-service", "c-care-laundry", "a-upper-wet-core", "b-rear-right-access", "b-front-right-access", "b-rear-window", "b-front-window", "b-rear-dry-service", "b-front-dry-service"]
    assert set(study["professional_status"].values()) == {"unknown"}
    assert study["revision"] == 7 and study["default_option"] == "b-rear-dry-service"
    assert Counter(d["status"] for d in study["owner_decisions"]) == {"pending": 4, "confirmed-preference": 3}
    assert {d["id"]: d["choice"] for d in study["owner_decisions"] if d["status"] == "confirmed-preference"} == export.CONFIRMED_CHOICES
    for o in study["options"]:
        assert [b["id"] for b in o["model"]["buildings"]] == [o["building"]]
        assert o["model"]["bc_option"]["geometry_review"] == o["review"]
        assert o["review"]["professional_approval"] == "unknown" and o["review"]["rendered_qa"] == "not-run"
        assert len(o["plans"]["floors"]) == 4
        for f in o["plans"]["floors"]:
            assert [f["width_mm"], f["depth_mm"]] == [6000, 17630]
            for i, r in enumerate(f["rooms"]):
                a = [r["geometry"][k] for k in export.KEYS]
                assert _covered(a, [[0, 0, 6000, 17630]])
                assert not any(_hits(a, [other["geometry"][k] for k in export.KEYS]) for other in f["rooms"][i+1:])


def test_no_main_scene_or_furniture_solver_is_called(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("The resource-heavy model/packing workflow must not run")
    monkeypatch.setattr(export.viewer, "build_payload", forbidden)
    monkeypatch.setattr(export.viewer, "attach_placements", forbidden)
    assert len(export.build_study()["options"]) == 10


def test_b_altar_axis_backing_frontage_stairs_and_original_goals_remain(study):
    for oid in ("b-rear-service", "b-front-service"):
        o = option(study, oid)
        first = rooms(o, 0)
        assert first["altar-backing"]["geometry"] == dict(zip(export.KEYS, [2500, 11370, 1820, 1600], strict=True))
        altar = next(i for i in first["shrine"]["furniture"] if i["catalog_id"] == "altar-table")
        assert altar["placement"]["aabb"] == export._bounds([2500, 10690, 1800, 600])
        gate = next(d for d in first["shrine-front"]["features"]["doors"] if d["neighbor"] is None)
        assert gate["width_mm"] == 1800
        assert 2400+3600*gate["ratio"] == pytest.approx(3400)
        assert first["garage"]["outdoor"] and not first["garage"]["furniture"]
        storage = next(r for r in o["review"]["area_rows"] if r["zone"] == "storage")
        assert storage["original_target_sqm"] == 10.5
        assert storage["sensitivity"][0]["area_sqm"] == 9.6404
        assert storage["functional_acceptance"] == "unknown"


def test_b_pocket_door_is_paired_left_access_not_old_right_route(study):
    for oid in ("b-rear-service", "b-front-service"):
        o = option(study, oid)
        first = rooms(o, 0)
        door = next(d for d in first["bath1"]["features"]["doors"] if d["neighbor"] == first["housework-passage"]["id"])
        assert door["face"] == "left" and door["width_mm"] == 1130 and door["operation"] == "sliding"
        assert not any(d["neighbor"] == first["corridor1"]["id"] for k in ("bath1", "bath-extension") for d in first[k]["features"]["doors"])
        assert any(d["neighbor"] == first["bath1"]["id"] for d in first["housework-passage"]["features"]["doors"])
        assert all("entry_access_review" not in r["features"] for r in first.values())
        rows = o["review"]["bath_route_sensitivity"]
        assert [r["pocket_wall_budget_meets_proposal"] for r in rows] == [False, False, True]
        assert [r["passage_width_mm"] for r in rows] == [980, 940, 910]
        assert [r["door_clear_assumption_mm"] for r in rows] == [970, 930, 900]
        assert rows[-1]["extra_over_900mm_body"] == 10
        assert all(r["bath_entry_route"]["coordinate_failures"] == [] for r in rows)
        assert any(z["kind"] == "care-turn" for z in first["bath-extension"]["features"]["reserved_mm"])


def test_b_same_room_seams_cannot_leave_false_walls_or_borrow_rear_door(study):
    rear, front = [option(study, oid) for oid in ("b-rear-service", "b-front-service")]
    for o in (rear, front):
        first = rooms(o, 0)
        for key, other, width in (("bath1", "bath-shoulder", 230), ("storage", "storage-shoulder", 340)):
            assert any(c["neighbor"] == first[other]["id"] and c["width_mm"] == width for c in first[key]["features"]["open_connections"])
        assert o["review"]["carry_body_115mm"]["coordinate_failures"] == []
        assert o["review"]["front_gate_clear_115mm"] == 1430
        assert o["review"]["whole_assembled_carry"].startswith("unknown")
    assert any(d["face"] == "rear" and d["neighbor"] is None for d in rooms(rear, 0)["storage"]["features"]["doors"])
    assert not any(d["face"] == "rear" and d["neighbor"] is None for d in rooms(front, 0)["storage"]["features"]["doors"])
    assert rear["review"]["carry_body_115mm"]["points_mm"][0][1] > 16000
    assert front["review"]["carry_body_115mm"]["points_mm"][0][1] < 5000


@pytest.mark.parametrize("mode", ["rear", "front"])
def test_b_right_door_and_left_dry_entrance_are_paired_without_a_door_through_altar_back(mode, study):
    o = option(study, "b-"+mode+"-right-access")
    first = rooms(o, 0)
    assert not {"bath1", "bath-shoulder"}.intersection(first)
    assert first["dry-access"]["geometry"] == dict(zip(export.KEYS, [1140, 11370, 1360, 1600], strict=True))
    assert first["bath-extension"]["geometry"] == dict(zip(export.KEYS, [1140, 12970, 3180, 1960], strict=True))
    for key, other, face, cy, width in (("bath-extension", "corridor1", "right", 13650, 1130), ("altar-backing", "dry-access", "left", 12170, 1060)):
        door = next(d for d in first[key]["features"]["doors"] if d["neighbor"] == first[other]["id"])
        paired = next(d for d in first[other]["features"]["doors"] if d["neighbor"] == first[key]["id"])
        assert door["face"] == face and door["width_mm"] == paired["width_mm"] == width
        assert first[key]["geometry"]["y_mm"]+door["ratio"]*first[key]["geometry"]["h_mm"] == cy
    assert not any(d["face"] in {"front", "right"} for d in first["altar-backing"]["features"]["doors"])
    assert o["review"]["paired_bath_door_coordinate_review"]
    assert not any("pocket_door_review" in r["features"] for r in first.values())


@pytest.mark.parametrize("mode", ["rear", "front"])
def test_b_right_study_preserves_storage_laundry_altar_stair_and_upper_floors(mode, study):
    o, control = option(study, "b-"+mode+"-right-access"), option(study, "b-"+mode+"-service")
    now, prior = rooms(o, 0), rooms(control, 0)
    for key in ("garage", "shrine-front", "shrine", "stair1", "storage", "storage-front", "storage-shoulder", "work-reserve"):
        assert now[key] == prior[key]
    assert now["housework-passage"]["geometry"] == prior["housework-passage"]["geometry"]
    assert now["housework-passage"]["furniture"] == prior["housework-passage"]["furniture"]
    assert not now["housework-passage"]["features"]["doors"]
    assert any(d["neighbor"] == now["dry-access"]["id"] for d in now["housework-passage"]["features"]["open_connections"])
    assert now["altar-backing"]["geometry"] == prior["altar-backing"]["geometry"]
    for before, after in zip(control["plans"]["floors"][1:], o["plans"]["floors"][1:], strict=True):
        assert {k: v for k, v in before.items() if k != "plan_file"} == {k: v for k, v in after.items() if k != "plan_file"}
        assert after["plan_file"] == o["id"]+"_"+after["id"]+".svg"
    for zone in ("storage", "laundry"):
        assert next(r for r in o["review"]["area_rows"] if r["zone"] == zone) == next(r for r in control["review"]["area_rows"] if r["zone"] == zone)
    assert not o["review"]["carry_body_115mm"]["coordinate_failures"]
    assert o["review"]["carry_entry_mode"] == mode
    assert any(d["face"] == "rear" and d["neighbor"] is None for d in now["storage"]["features"]["doors"]) == (mode == "rear")
    first_y = o["review"]["carry_body_115mm"]["points_mm"][0][1]
    assert first_y > 16000 if mode == "rear" else first_y < 5000


def test_b_right_tradeoff_is_recomputed_not_old_l_bath_area_or_target_reduction(study):
    o = option(study, "b-rear-right-access")
    area = next(r for r in o["review"]["area_rows"] if r["zone"] == "bathroom")
    assert [r["area_sqm"] for r in area["sensitivity"]] == [5.436, 5.2448, 5.1035]
    assert area["original_minimum_sqm"] == 4.5 and area["original_target_sqm"] == 7
    assert area["functional_acceptance"] == "unknown" and area["below_target_at_80mm"]
    assert [r["loss_sqm"] for r in o["review"]["bath_area_lost_from_left_control_sqm"]] == [1.92, 1.856, 1.808]
    assert o["review"]["bath_window"].startswith("none-mechanical-exhaust")
    assert o["review"]["care_and_rescue"].startswith("unknown")
    assert all(d["status"] == "pending" for d in o["model"]["bc_option"]["owner_decisions"])


def test_b_right_door_budgets_improve_approach_without_erasing_900_door_or_1500_carry_shortfall(study):
    o = option(study, "b-rear-right-access")
    rows = o["review"]["bath_route_sensitivity"]
    assert [r["passage_width_mm"] for r in rows] == [1425, 1385, 1355]
    assert [r["door_clear_assumption_mm"] for r in rows] == [970, 930, 900]
    assert [r["dry_door_clear_assumption_mm"] for r in rows] == [900, 860, 830]
    assert rows[-1]["extra_over_900mm_body"] == 455
    assert rows[-1]["left_control_passage_width_mm"] == 910
    assert o["review"]["front_gate_clear_115mm"] == 1430
    assert o["review"]["front_continuous_1500mm_shortfall_mm"] == 145
    for r in rows:
        for key in ("bath_entry_route", "basin_approach_route", "toilet_side_route", "dry_cabinet_700mm_body_route"):
            assert not r[key]["coordinate_failures"]
        assert not r["turn_circle_coordinate_failures"] and not r["fixture_body_coordinate_failures"]
        assert not r["dry_door_swing_coordinate_failures"]
    assert o["review"]["dry_cabinet_route_scope"].startswith("700mm-discussion-body-not-wheelchair")


def test_b_right_full_size_cabinet_and_door_parking_are_not_a_wall_pocket(study):
    first = rooms(option(study, "b-rear-right-access"), 0)
    cabinet = first["altar-backing"]["furniture"][0]
    assert [cabinet[k] for k in ("width_mm", "depth_mm", "height_mm")] == [1200, 450, 2100]
    assert cabinet["placement"]["aabb"] == export._bounds([3755, 11485, 450, 1200])
    assert cabinet["placement"]["rotation_deg"] == 90
    reserves = first["bath-extension"]["features"]["reserved_mm"]
    parked = next(z for z in reserves if z["kind"] == "b-right-slider-park")
    assert parked["aabb"] == export._bounds([4435, 11855, 95, 1230])
    assert parked["status"] == "assumed-budget-not-product"
    assert not _hits([4435, 11855, 95, 1230], [4320, 14330, 1680, 600])


def test_b_right_shared_shower_floor_is_explicit_not_permission_to_ignore_fixed_body_collisions(study):
    o = option(study, "b-rear-right-access")
    first = rooms(o, 0)
    shower = next(i for i in first["bath-extension"]["furniture"] if i["shape"] == "shower")
    assert shower["step_free"] and shower["placement"]["rotation_deg"] == 270
    assert not o["review"]["operation_vs_fixed_body"]
    assert len(o["review"]["operation_vs_shared_wet_floor"]) == 1
    assert o["review"]["shared_wet_floor_and_slip_control"] == "sequential-only-not-approved"
    model = copy.deepcopy(o["model"])
    bath = export._rooms(model["buildings"][0]["floors"][0])["bath-extension"]
    next(i for i in bath["furniture"] if i["shape"] == "shower")["step_free"] = False
    screen = export._screen(model, [80, 100, 115], model["buildings"][0])
    assert any(i["hits"].endswith(":shower") for i in screen["operation_vs_fixed_body"])
    assert not screen["operation_vs_shared_wet_floor"]


def test_b_larger_real_door_projection_must_flag_carry_body_not_reuse_95mm_fit(study):
    o = option(study, "b-front-right-access")
    cfg = read_json(ROOT / export.SOURCE)
    cfg["b_right_access"]["surface_slide_projection_mm"] = 300
    review = export._b_right_review(o["model"], cfg, o["review"])
    assert review["carry_body_115mm"]["coordinate_failures"]
    assert review["front_continuous_1500mm_shortfall_mm"] == 350
    cfg["b_right_access"]["dry_door_leaf_thickness_budget_mm"] = 100
    review = export._b_right_review(o["model"], cfg, o["review"])
    assert review["bath_route_sensitivity"][-1]["dry_door_swing_coordinate_failures"]


def test_b_right_cannot_evaluate_room_union_if_actual_door_is_moved(study):
    o = option(study, "b-rear-right-access")
    model = copy.deepcopy(o["model"])
    bath = export._rooms(model["buildings"][0]["floors"][0])["bath-extension"]
    bath["tour_features"]["doors"][0]["ratio"] += .1
    with pytest.raises(ContractError, match="actual paired openings"):
        export._b_right_review(model, read_json(ROOT / export.SOURCE), o["review"])


def test_b_public_bath_path_avoids_ritual_reserves_instead_of_assuming_they_are_empty(study):
    o = option(study, "b-rear-right-access")
    first = rooms(o, 0)
    reserves = [z["aabb"] for r in first.values() for z in r["features"]["fixed_reserved_mm"] if z["kind"] == "ritual-approach"]
    for row in o["review"]["bath_route_sensitivity"]:
        assert row["bath_entry_route"]["points_mm"][1][1] == 5000
        for sweep in row["bath_entry_route"]["sweeps_mm"]:
            assert all(not _hits(sweep, [a["minX"], a["minY"], a["maxX"]-a["minX"], a["maxY"]-a["minY"]]) for a in reserves)


def test_b_carry_uses_actual_gate_width_not_just_union_of_adjacent_rectangles(study):
    o = option(study, "b-front-right-access")
    model = copy.deepcopy(o["model"])
    first = export._rooms(model["buildings"][0]["floors"][0])
    for a, b in (("corridor1", "storage-front"), ("storage-front", "corridor1")):
        next(d for d in first[a]["tour_features"]["doors"] if d["neighbor"] == first[b]["id"])["width_mm"] = 1400
    review = export._b_right_review(model, read_json(ROOT / export.SOURCE), o["review"])
    assert review["front_gate_clear_115mm"] == 1170
    assert "actual-storage-gate:narrower-than-body" in review["carry_body_115mm"]["coordinate_failures"]
    assert o["review"]["original_carry_target_mm"] == 1500
    requirements = read_json(ROOT / "inputs/requirements.json")["requirements"]
    req = next(r for r in requirements if r["id"] == "B.floor-1.palanquin")
    assert req["constraints"]["door_clear_mm"] == o["review"]["original_carry_target_mm"]


@pytest.mark.parametrize("mode", ["rear", "front"])
def test_b_window_preserves_frame_altar_stair_and_upper_floors_not_the_oversized_draft(mode, study):
    o, control = option(study, "b-"+mode+"-window"), option(study, "b-"+mode+"-service")
    now, old = rooms(o, 0), rooms(control, 0)
    assert now["rear-bath"]["geometry"] == dict(zip(export.KEYS, [0, 14500, 2700, 3130], strict=True))
    assert now["laundry-base"]["geometry"] == dict(zip(export.KEYS, [1360, 12970, 2960, 1530], strict=True))
    for key in ("garage", "stair1", "shrine-front"):
        assert now[key] == old[key]
    assert now["shrine"]["geometry"] == old["shrine"]["geometry"]
    assert now["shrine"]["furniture"] == old["shrine"]["furniture"]
    assert now["altar-backing"]["geometry"] == old["altar-backing"]["geometry"]
    assert all(d["face"] == "right" for d in now["altar-backing"]["features"]["doors"])
    assert not now["altar-backing"]["features"]["window_review"]["renderable"]
    for before, after in zip(control["plans"]["floors"][1:], o["plans"]["floors"][1:], strict=True):
        assert {k: v for k, v in before.items() if k != "plan_file"} == {k: v for k, v in after.items() if k != "plan_file"}
    assert o["review"]["old_six_comparisons_retained"]
    assert all(d["status"] == "pending" for d in o["model"]["bc_option"]["owner_decisions"])


def test_b_window_has_a_real_revalidated_rear_opening_not_a_laundry_or_side_window(study):
    first = rooms(option(study, "b-rear-window"), 0)
    bath = first["rear-bath"]
    f = bath["features"]
    assert f["window_review"]["renderable"] and not f["window_review"]["issues"]
    assert f["window_review"]["professional_acceptance"] == "unknown"
    assert f["window_face"] == "rear"
    assert [f[k] for k in ("window_mm", "window_sill_mm", "window_height_mm")] == [900, 1500, 600]
    assert f["window_ratio"]*bath["geometry"]["w_mm"] == 1950
    assert all(not first[k]["features"]["window_review"]["renderable"] for k in ("laundry-front", "laundry-base"))
    assert option(study, "b-rear-window")["review"]["laundry_exterior_window"].startswith("none-after-relocation")


@pytest.mark.parametrize("mode", ["rear", "front"])
def test_b_window_fixtures_are_wall_backed_and_dry_circle_transfer_do_not_borrow_shower(mode, study):
    o = option(study, "b-"+mode+"-window")
    first = rooms(o, 0)
    bath = first["rear-bath"]
    products = {i["id"].rsplit(":", 1)[-1]: i for i in bath["furniture"]}
    toilet = products["toilet"]["placement"]
    assert toilet["rotation_deg"] == 90 and toilet["wall_anchor"] == "right"
    assert toilet["aabb"] == export._bounds([1885, 14825, 700, 450])
    assert products["shower"]["placement"]["aabb"] == export._bounds([115, 16315, 1200, 1200])
    assert products["basin"]["placement"]["aabb"] == export._bounds([1535, 17065, 600, 450])
    settings = read_json(ROOT / export.SOURCE)["b_rear_window"]
    for item in products.values():
        b = item["placement"]["aabb"]
        assert not _circle_hits(settings["turn_circle_mm"], [b["minX"], b["minY"], b["maxX"]-b["minX"], b["maxY"]-b["minY"]])
    assert not o["review"]["operation_vs_fixed_body"]
    assert not o["review"]["operation_vs_shared_wet_floor"]
    assert o["review"]["dry_turn_and_transfer_do_not_borrow_shower"]
    assert not any(i["room"] in {"B:floor-1:"+k for k in settings["zones_mm"]} for i in o["review"]["furniture_body_sensitivity"])
    for row in o["review"]["bath_route_sensitivity"]:
        for key in ("bath_entry_route", "local_bath_open_route", "basin_approach_route", "toilet_side_route", "shower_approach_route", "dry_cabinet_700mm_body_route"):
            assert not row[key]["coordinate_failures"]
        assert not row["turn_circle_coordinate_failures"] and not row["bath_operation_coordinate_failures"]
        assert not row["laundry_operation_coordinate_failures"] and not row["dry_door_swing_coordinate_failures"]
        assert row["closed_door_route"]["coordinate_failures"]
        assert row["arrival_during_ritual"]["coordinate_failures"]  # Do not erase ceremonial occupancy to claim simultaneous passage.


def test_b_window_areas_meet_discussion_targets_without_counting_public_lane_or_balcony_approval(study):
    o = option(study, "b-rear-window")
    rows = {r["zone"]: r for r in o["review"]["area_rows"]}
    for key, values, target in (("bathroom", [7.5438, 7.325, 7.163], 7), ("storage", [11.6514, 11.3474, 11.1215], 10.5), ("laundry", [5.404, 5.1748, 5.005], 5)):
        assert [r["area_sqm"] for r in rows[key]["sensitivity"]] == values
        assert rows[key]["original_target_sqm"] == target
        assert not rows[key]["below_target_at_80mm"] and not rows[key]["below_minimum_insets_mm"]
        assert rows[key]["functional_acceptance"] == "unknown"
    assert not o["review"]["laundry_public_route_counted_as_area"]
    assert o["review"]["independent_outdoor_work_balcony"].startswith("unmet")
    first = rooms(o, 0)
    assert not first["laundry-front"]["outdoor"] and not first["laundry-base"]["outdoor"]
    cfg = read_json(ROOT / export.SOURCE)
    # 5.005m² is only a discussion budget: slightly thicker finishes lose it.
    laundry = [{"geometry": first[k]["geometry"]} for k in ("laundry-front", "laundry-base")]
    assert export.discussion_area(laundry, 116) < 5
    assert not o["review"]["laundry_operation_bands_overlap"]
    assert not _hits(cfg["b_rear_window"]["laundry_operations_mm"]["washer-front"], cfg["b_rear_window"]["laundry_operations_mm"]["sink-front"])
    for rect in cfg["b_rear_window"]["laundry_operations_mm"].values():
        assert _inside(rect, [[r["geometry"][k] for k in export.KEYS] for r in (first["laundry-front"], first["laundry-base"])], 115)
        assert not _hits(rect, [first["dry-route"]["geometry"][k] for k in export.KEYS])


def test_b_window_keeps_tight_door_budgets_conditional_arrival_and_separate_rear_front_paths(study):
    rear, front = [option(study, "b-"+m+"-window") for m in ("rear", "front")]
    for o in (rear, front):
        rows = o["review"]["bath_route_sensitivity"]
        assert [r["passage_width_mm"] for r in rows] == [1200, 1160, 1130]
        assert [r["door_clear_assumption_mm"] for r in rows] == [970, 930, 900]
        assert [r["local_open_route_leaf_gap_mm"] for r in rows] == [400, 380, 365]
        assert rows[-1]["door_envelopes_mm"]["park"] == [1245, 14615, 1230, 95]
        assert o["review"]["arrival_ritual_conflict"].startswith("must-time-separate-pending-family")
        assert not o["review"]["carry_body_115mm"]["coordinate_failures"]
        assert o["review"]["original_carry_target_mm"] == 1500
        assert o["review"]["front_gate_clear_115mm"] == 1430
        assert o["review"]["front_continuous_1500mm_shortfall_mm"] == 70
        assert o["review"]["care_and_rescue"].startswith("unknown")
    assert rear["review"]["carry_entry_mode"] == "rear" and rear["review"]["carry_entry_gate_clear_115mm"] == 1730
    assert front["review"]["carry_entry_mode"] == "front" and front["review"]["carry_entry_gate_clear_115mm"] == 1570
    for o in (rear, front):
        assert any(d["neighbor"] is None and d["face"] == "rear" for d in rooms(o, 0)["storage"]["features"]["doors"]) == (o is rear)


def test_b_window_more_demanding_hardware_and_narrower_actual_gate_cannot_reuse_fit(study):
    o = option(study, "b-front-window")
    cfg = read_json(ROOT / export.SOURCE)
    cfg["b_rear_window"]["surface_slide_projection_mm"] = 500
    review = export._b_window_review(o["model"], cfg, o["review"])
    assert review["bath_route_sensitivity"][-1]["local_bath_open_route"]["coordinate_failures"]
    assert review["bath_route_sensitivity"][-1]["local_open_route_leaf_gap_mm"] == -40
    cfg = read_json(ROOT / export.SOURCE)
    cfg["b_rear_window"]["dry_door_leaf_thickness_budget_mm"] = 100
    assert export._b_window_review(o["model"], cfg, o["review"])["bath_route_sensitivity"][-1]["dry_door_swing_coordinate_failures"]
    model = copy.deepcopy(o["model"])
    first = export._rooms(model["buildings"][0]["floors"][0])
    for a, b in (("corridor1", "storage-front"), ("storage-front", "corridor1")):
        next(d for d in first[a]["tour_features"]["doors"] if d["neighbor"] == first[b]["id"])["width_mm"] = 1400
    review = export._b_window_review(model, read_json(ROOT / export.SOURCE), o["review"])
    assert review["front_gate_clear_115mm"] == 1170
    assert "actual-storage-gate:narrower-than-body" in review["carry_body_115mm"]["coordinate_failures"]
    first["rear-bath"]["tour_features"]["doors"][0]["ratio"] += .1
    with pytest.raises(ContractError, match="actual paired openings"):
        export._b_window_review(model, read_json(ROOT / export.SOURCE), o["review"])


@pytest.mark.parametrize("width", [2700, 4000])
def test_b_window_invalid_rear_window_must_be_rejected_by_shared_opening_screen(width):
    cfg = read_json(ROOT / export.SOURCE)
    cfg["b_rear_window"]["rear_window"]["width_mm"] = width
    source = export._select(export.read_model(ROOT / "structured/candidates/b32-entry-options-3d.html"), "b32-rear", "B")
    with pytest.raises(ContractError, match="geometric opening screen"):
        export.b_window_proposal(copy.deepcopy(source), cfg, ROOT)


def test_c_keeps_public_wc_window_private_bed_and_only_original_second_floor_washer(study):
    o = option(study, "c-care-laundry")
    first = rooms(o, 0)
    assert first["public-bath"]["features"]["window_review"]["renderable"]
    assert first["public-bath"]["features"]["window_face"] == "front"
    assert first["elder"]["features"]["window_mm"] == 2300
    assert o["review"]["second_floor_washer_retained"]
    assert o["review"]["independent_work_balcony_requirement"] == "unmet-unchanged"
    washers = [i for f in o["plans"]["floors"] for r in f["rooms"] for i in r["furniture"] if i["catalog_id"] == "washer"]
    assert len(washers) == 1
    assert all([i["width_mm"], i["depth_mm"], i["height_mm"]] == [650, 650, 1000] for i in washers)
    assert not any(i["catalog_id"] == "washer" for r in first.values() for i in r["furniture"])
    source = export._select(export.read_model(ROOT / "structured/candidates/c-integrated-options-3d.html"), "c-integrated-3600", "C")
    original = next((c, i) for c in source["buildings"][0]["floors"][1]["cells"] for i in c["furniture"] if i["catalog_id"] == "washer")
    assert washers[0]["placement"] == original[0]["furniture_placements"]["tour_mm"][original[1]["id"]]
    assert o["review"]["washer_count"] == 1 and o["review"]["washer_floor"] == "floor-2"
    assert o["review"]["new_first_floor_washer"].startswith("withdrawn")
    assert o["review"]["operation_vs_fixed_body"] == []
    assert all(r["kitchen_entry_route"]["coordinate_failures"] == [] for r in o["review"]["kitchen_route_sensitivity"])
    assert [r["prior_opposed_layout_shortfall_mm"] for r in o["review"]["kitchen_route_sensitivity"]] == [0, 0, 30]
    assert not any(i["room"] == "C:floor-1:kitchen" for i in o["review"]["furniture_body_sensitivity"])
    assert not any(i["inset_mm"] is None for i in o["review"]["furniture_body_sensitivity"])
    assert not any(i["room"] == "C:floor-1:living" for i in o["review"]["furniture_body_sensitivity"])


def test_c_longitudinal_fridge_preserves_products_operation_bands_and_assumed_finish_space(study):
    o = option(study, "c-care-laundry")
    kitchen = rooms(o, 0)["kitchen"]
    counter, fridge = (next(i for i in kitchen["furniture"] if i["catalog_id"] == k) for k in ("counter-240-60", "fridge-75"))
    assert [counter[k] for k in ("width_mm", "depth_mm", "height_mm")] == [2400, 600, 900]
    assert [fridge[k] for k in ("width_mm", "depth_mm", "height_mm")] == [750, 700, 1800]
    assert fridge["placement"]["rotation_deg"] == 180 and fridge["placement"]["wall_anchor"] == "front"
    assert fridge["placement"]["aabb"] == export._bounds([1435, 8795, 750, 700])
    rows = o["review"]["kitchen_route_sensitivity"]
    assert [r["counter_working_width_at_fixed_products_mm"] for r in rows] == [1605, 1585, 1570]
    assert all(r["counter_operation_depth_mm"] == 900 and r["fridge_operation_depth_mm"] == 600 for r in rows)
    assert all(not r["operation_failures"] and not r["fixed_body_failures"] and r["paired_door_coordinate_review"] for r in rows)
    assert all(not r["fridge_body_replacement_route"]["coordinate_failures"] for r in rows)
    assert all(r["counter_fridge_longitudinal_gap_mm"] == 50 and r["fridge_clearance_discussion_assumptions_met"] for r in rows)
    assert rows[-1]["fridge_back_space_after_inset_mm"] == rows[-1]["fridge_side_space_after_inset_mm"] == 100
    assert o["review"]["kitchen_product_manual_approval"].startswith("unknown")
    assert o["review"]["door_sweep_drawers_pocket_extraction_and_exhaust"].startswith("unknown")


def test_c_kitchen_borrows_public_area_without_changing_stair_elder_baths_or_upper_floors(study):
    o = option(study, "c-care-laundry")
    source = export._select(export.read_model(ROOT / "structured/candidates/c-integrated-options-3d.html"), "c-integrated-3600", "C")
    before, after = source["buildings"][0], o["model"]["buildings"][0]
    for index, (prior, now) in enumerate(zip(before["floors"], after["floors"], strict=True)):
        left, right = export._rooms(prior), export._rooms(now)
        assert set(left) == set(right)
        for key, c in left.items():
            if index or key not in {"kitchen", "living"}:
                assert c["tour_mm"] == right[key]["tour_mm"]
                assert c["furniture_placements"] == right[key]["furniture_placements"]
            if c["kind"] == "stair":
                assert c["tour_features"]["stair_geometry"] == right[key]["tour_features"]["stair_geometry"]
                assert c["tour_features"]["stair_footprint_mm"] == right[key]["tour_features"]["stair_footprint_mm"]
            assert Counter(i["catalog_id"] for i in c["furniture"]) == Counter(i["catalog_id"] for i in right[key]["furniture"])
    trade = o["review"]["public_area_tradeoff"]
    assert trade["front_partition_shift_mm"] == 450 and trade["nominal_public_loss_sqm"] == 1.08
    assert trade["public_includes_foyer"] and not trade["pure_living_or_legal_area_claimed"]
    assert trade["nominal_public_before_sqm"] == 26.928 and trade["nominal_public_now_sqm"] == 25.848
    assert trade["nominal_living_dining_without_foyer_before_sqm"] == 23.328
    assert trade["nominal_living_dining_without_foyer_now_sqm"] == 22.248
    assert trade["status"] == "owner-confirmed-for-integration-professional-unknown"
    decision = next(d for d in study["owner_decisions"] if d["id"] == "c-kitchen")
    assert decision["status"] == "confirmed-preference"
    assert not decision["accepted_scope"]["whole_c_layout_adopted"]
    assert decision["accepted_scope"]["professional_approval"] == "unknown"
    assert next(d for d in study["owner_decisions"] if d["id"] == "c-base")["status"] == "pending"


def test_c_reintroducing_opposed_fridge_flags_actual_operation_collision_at_115(study):
    o = option(study, "c-care-laundry")
    model = copy.deepcopy(o["model"])
    kitchen = export._rooms(model["buildings"][0]["floors"][0])["kitchen"]
    products = {i["catalog_id"]: i for i in kitchen["furniture"]}
    export._empty(kitchen)
    export._place(kitchen, products["counter-240-60"], [115, 9365, 600, 2400], 270, "left")
    export._place(kitchen, products["fridge-75"], [1585, 11135, 700, 750], 90, "right")
    review = export._functional_review(model, "C", read_json(ROOT / export.SOURCE), o["review"], ROOT)
    row = review["kitchen_route_sensitivity"][-1]
    assert row["counter_working_width_at_fixed_products_mm"] == 870
    assert not row["fixed_body_failures"]  # A body-only check would falsely pass this layout.
    assert "counter:hits-fridge" in row["operation_failures"]
    assert not row["fridge_clearance_discussion_assumptions_met"]


def test_c_more_demanding_product_vent_space_cannot_reuse_discussion_fit(study):
    o = option(study, "c-care-laundry")
    cfg = read_json(ROOT / export.SOURCE)
    cfg["c"]["fridge_clearance_assumptions_mm"]["back"] = 150
    rows = export._functional_review(o["model"], "C", cfg, o["review"], ROOT)["kitchen_route_sensitivity"]
    assert not any(r["fridge_clearance_discussion_assumptions_met"] for r in rows)


def test_freestanding_seating_keeps_original_600mm_operation_and_coffee_table_clears_chair(study):
    living = rooms(option(study, "c-care-laundry"), 0)["living"]
    items = {i["id"].rsplit(":", 1)[-1]: i for i in living["furniture"]}
    sofa, chair, table = (items[k] for k in ("sofa", "reading-chair", "coffee-table"))
    assert sofa["front_clearance_mm"] == chair["front_clearance_mm"] == 600
    assert sofa["placement"]["operation_mm"] == export._bounds([1215, 6610, 600, 1800])
    assert chair["placement"]["operation_mm"] == export._bounds([115, 6180, 900, 600])
    assert table["placement"]["rotation_deg"] == 0
    assert table["placement"]["aabb"] == export._bounds([115, 7770, 1100, 600])
    chair_box = chair["placement"]["aabb"]
    assert table["placement"]["aabb"]["minY"]-chair_box["maxY"] == 140
    for oid in ("b-rear-service", "b-front-service"):
        benches = [i for i in rooms(option(study, oid), 0)["shrine"]["furniture"] if i["catalog_id"] == "movable-bench"]
        assert len(benches) == 2 and all(i["placement"]["operation_mm"] is None for i in benches)  # Parked, not usable seats.


def test_c_open_public_furniture_bodies_and_operations_do_not_hit_across_data_room_seams(study):
    def xy(a):
        return [a["minX"], a["minY"], a["maxX"]-a["minX"], a["maxY"]-a["minY"]]
    first = rooms(option(study, "c-care-laundry"), 0)
    public = [i for r in first.values() if r["features"]["space_group"] == "prep-C-open-public" for i in r["furniture"]]
    for item in public:
        p = item["placement"]
        for other in public:
            if item is other:
                continue
            op = other["placement"]
            box, other_box = p["aabb"], op["aabb"]
            if min(p["mount_height_mm"]+item["height_mm"], op["mount_height_mm"]+other["height_mm"]) > max(p["mount_height_mm"], op["mount_height_mm"]):
                assert not _hits(xy(box), xy(other_box)), (item["id"], other["id"])
            if p["operation_mm"]:
                assert not _hits(xy(p["operation_mm"]), xy(other_box)), (item["id"], other["id"])


def test_translating_coffee_table_into_reading_chair_is_rejected_not_rendered_as_pass(monkeypatch):
    original = export.read_json
    def read(path):
        data = original(path)
        if path.name == "interior-improvements.json":
            table = next(p for p in data["c"]["living_products"] if p["local"] == "coffee-table")
            table.update(rect_mm=[380, 7280, 600, 1100], rotation_deg=270)
            # A synthetic owner acceptance must not bypass the collision screen.
            decision = next(d for d in data["owner_decisions"] if d["id"] == "c-kitchen")
            decision["accepted_scope"]["layout_sha256"] = stable_hash({k: data["c"][k] for k in export.C_LAYOUT_KEYS})
        return data
    monkeypatch.setattr(export, "read_json", read)
    with pytest.raises(ContractError, match="fixed-body or retained seating-operation"):
        export.build_study()


def test_a_reverts_windowless_relocation_and_keeps_original_rear_window_without_full_stack_claim(study):
    o = option(study, "a-upper-wet-core")
    third = rooms(o, 2)
    assert third["bath3"]["features"]["window_review"]["renderable"]
    assert third["bath3"]["features"]["window_face"] == "rear"
    assert [third["bath3"]["features"][k] for k in ("window_mm", "window_sill_mm", "window_height_mm")] == [600, 2100, 500]
    assert third["bath3"]["features"]["window_review"]["professional_acceptance"] == "unknown"
    assert o["review"]["bath_window"].startswith("original-rear")
    assert o["review"]["windowless_relocation"].startswith("withdrawn")
    assert not o["review"]["wet_area_over_study_removed"]
    assert o["review"]["bath_3f_rect_mm"] == [0, 13400, 2360, 2230]
    assert o["review"]["bath_2f_rect_mm"] == [2160, 5880, 2400, 2100]
    assert not o["review"]["corridor_reduction_claimed"]
    assert o["review"]["original_master_ensuite"] == "unaccommodated-unchanged"
    rows = {r["requirement_id"]: r for r in o["review"]["area_rows"]}
    assert rows["A.floor-3.bath3"]["original_target_sqm"] == 4.5
    assert rows["A.floor-3.bath3"]["sensitivity"][0]["area_sqm"] == 4.554
    assert rows["A.floor-3.bath3"]["sensitivity"][-1]["area_sqm"] == 4.26
    assert rows["A.floor-3.multi"]["original_target_sqm"] == 10
    assert rows["A.floor-3.multi"]["sensitivity"][0]["area_sqm"] == 8.9088
    assert o["review"]["inherited_unallocated_zones"][0]["area_sqm"] == .096


def test_a_does_not_discard_furniture_or_alter_other_floors_stairs(study):
    original = export.read_model(ROOT / "structured/candidates/model3d.html")
    prior = next(b for b in original["buildings"] if b["id"] == "A")
    after = option(study, "a-upper-wet-core")["model"]["buildings"][0]
    for before, now in zip(prior["floors"], after["floors"], strict=True):
        left, right = export._rooms(before), export._rooms(now)
        assert Counter(i["catalog_id"] for c in left.values() for i in c["furniture"]) == Counter(i["catalog_id"] for c in right.values() for i in c["furniture"])
        assert {k: c["tour_mm"] for k, c in left.items()} == {k: c["tour_mm"] for k, c in right.items()}
        assert {k: c["furniture_placements"] for k, c in left.items()} == {k: c["furniture_placements"] for k, c in right.items()}
        for key, c in left.items():
            if c["kind"] == "stair":
                assert c["tour_features"]["stair_geometry"] == right[key]["tour_features"]["stair_geometry"]
                assert c["tour_features"]["stair_footprint_mm"] == right[key]["tour_features"]["stair_footprint_mm"]


def test_every_item_is_unscaled_and_recomputed_hvac_has_no_old_pass(study):
    catalog = read_json(ROOT / "inputs/furniture-layout.json")["catalog"]
    for o in study["options"]:
        for f in o["plans"]["floors"]:
            for r in f["rooms"]:
                for i in r["furniture"]:
                    if i["catalog_id"] in catalog and "width_mm" in catalog[i["catalog_id"]]:
                        assert [i[k] for k in ("width_mm", "depth_mm", "height_mm")] == [catalog[i["catalog_id"]][k] for k in ("width_mm", "depth_mm", "height_mm")]
                    p = i["placement"]
                    dims = [i["width_mm"], i["depth_mm"]]
                    if p["rotation_deg"] % 180:
                        dims.reverse()
                    assert [p["aabb"]["maxX"]-p["aabb"]["minX"], p["aabb"]["maxY"]-p["aabb"]["minY"]] == pytest.approx(dims, abs=1e-6)
        assert o["model"]["layout_review"]["checks"] == []
        assert o["model"]["facade"]["buildings"] == []
        assert all(r["compliance"] == "unknown" and r["model"] is None for r in o["model"]["layout_review"]["hvac_routes"])
        assert not any(i["inset_mm"] == 80 for i in o["review"]["furniture_body_sensitivity"])


def test_moved_product_cannot_be_shrunk_to_force_fit(study):
    c = copy.deepcopy(option(study, "c-care-laundry")["model"]["buildings"][0]["floors"][0])
    kitchen = export._rooms(c)["kitchen"]
    item = kitchen["furniture"][0]
    with pytest.raises(ContractError, match="scale"):
        export._place(kitchen, item, [80, 9365, 500, 2400], 270, "left")


def test_base_option_order_cannot_swap_rear_and_front(study, monkeypatch):
    original = export.read_model
    def read(path):
        data = original(path)
        if path.name == "b32-entry-options-3d.html":
            data["bc_options"]["options"].reverse()
        return data
    monkeypatch.setattr(export, "read_model", read)
    result = export.build_study()
    assert option(result, "b-rear-service")["review"]["carry_entry_mode"] == "rear"
    assert option(result, "b-front-service")["review"]["carry_entry_mode"] == "front"


def test_ambiguous_or_wrong_building_source_is_rejected():
    with pytest.raises(ContractError):
        export._select({"bc_options": {"options": [{"id": "b32-rear", "building": "C"}]}}, "b32-rear", "B")


@pytest.mark.parametrize("change", ["second-washer", "move-washer", "windowless", "stack-priority", "unapproved-b", "missing-owner-source", "duplicate-decision"])
def test_owner_preferences_cannot_turn_into_other_choices_or_unapproved_adoption(change):
    cfg = read_json(ROOT / export.SOURCE)
    if change == "second-washer":
        cfg["c"]["washer_count"] = 2
    elif change == "move-washer":
        cfg["c"]["washer_floor"] = "floor-1"
    elif change == "windowless":
        cfg["a"]["bath_strategy"] = "move-bath-to-middle"
    elif change == "stack-priority":
        cfg["a"]["wet_stack_priority"] = "exact-stacking-before-window"
    elif change == "unapproved-b":
        cfg["owner_decisions"][0]["status"] = "confirmed-preference"
    elif change == "missing-owner-source":
        next(d for d in cfg["owner_decisions"] if d["id"] == "c-washer").pop("source")
    else:
        cfg["owner_decisions"][0] = cfg["owner_decisions"][-1]
    with pytest.raises(ContractError, match="owner preferences"):
        export._validate_owner_choices(cfg)


@pytest.mark.parametrize("change", ["layout-drift", "area-drift", "whole-layout", "professional-pass", "missing-basis", "missing-source"])
def test_c_kitchen_confirmation_cannot_expand_scope_or_follow_a_changed_layout(change):
    cfg = read_json(ROOT / export.SOURCE)
    decision = next(d for d in cfg["owner_decisions"] if d["id"] == "c-kitchen")
    scope = decision["accepted_scope"]
    if change == "layout-drift":
        cfg["c"]["products"][0]["rect_mm"][0] += 1
    elif change == "area-drift":
        scope["nominal_public_loss_sqm"] = 2.0
    elif change == "whole-layout":
        scope["whole_c_layout_adopted"] = True
    elif change == "professional-pass":
        scope["professional_approval"] = "passed"
    elif change == "missing-basis":
        scope.pop("basis_report_hash")
    else:
        decision.pop("source")
    with pytest.raises(ContractError, match="scope changed|owner preferences"):
        export._validate_owner_choices(cfg)


def test_c_cannot_silently_reintroduce_first_floor_washer():
    cfg = read_json(ROOT / export.SOURCE)["c"]
    cfg["products"].append({"local": "care-washer", "catalog": "washer"})
    with pytest.raises(ContractError, match="reintroduce"):
        export.c_proposal(export._select(export.read_model(ROOT / "structured/candidates/c-integrated-options-3d.html"), cfg["base_option"], "C"), cfg)


def test_a_cannot_claim_retained_window_without_renderable_source_window():
    model = export.read_model(ROOT / "structured/candidates/model3d.html")
    building = next(b for b in model["buildings"] if b["id"] == "A")
    export._rooms(building["floors"][2])["bath3"]["tour_features"]["window_review"]["renderable"] = False
    with pytest.raises(ContractError, match="original rear bathroom"):
        export.a_proposal(model, read_json(ROOT / export.SOURCE)["a"])


@pytest.mark.parametrize("value", ["file:///etc/passwd", "../model.html", "/tmp/model.html", "inputs/private/model.html"])
def test_sources_never_escape_public_project(value, monkeypatch):
    original = export.read_json
    def read(path):
        data = original(path)
        if path.name == "interior-improvements.json":
            data["sources"]["abc"] = value
        return data
    monkeypatch.setattr(export, "read_json", read)
    with pytest.raises(ContractError):
        export.build_study()


def test_parser_only_decodes_one_json_assignment_never_javascript(tmp_path):
    path = tmp_path / "malicious.html"
    path.write_text('  var DATA = (()=>{throw Error("must never run")})();')
    with pytest.raises(ValueError):
        export.read_model(path)
    path.write_text('  var DATA = {};\n  var DATA = {};')
    with pytest.raises(ContractError):
        export.read_model(path)


def test_serialization_and_all_forty_plan_views_share_exact_model_data(study, tmp_path):
    protected = [ROOT / p for p in study["source_hashes"]]
    before = {p: sha256_file(p) for p in protected}
    files = export.write_study(study, tmp_path)
    manifest = read_json(Path(files["report"]))
    data = export.read_model(Path(files["viewer"]))
    viewer_text = Path(files["viewer"]).read_text()
    assert viewer_text.count("envelope.userData.interiorDoorEnvelope=zone.kind;") == 1
    assert "拉門關閉範圍（不可通行）" in viewer_text and export.DOOR_ENVELOPES in study["source_hashes"]
    assert len(list((tmp_path / export.OUT).glob("*.svg"))) == 40
    for o in manifest["options"]:
        embedded = next(d["model"] for d in data["bc_options"]["options"] if d["id"] == o["id"])
        assert export.plan_data(embedded)["buildings"][0]["floors"][0]["rooms"] == o["plans"]["floors"][0]["rooms"]
        for f in o["plans"]["floors"]:
            p = tmp_path / export.OUT / f["plan_file"]
            tree = ET.parse(p).getroot()
            assert tree.get("data-improvement-option") == o["id"]
            assert int(tree.get("width"))*int(tree.get("height")) < 1_300_000
            if o["id"].endswith("-window") and f["id"] == "floor-1":
                bath_group = tree.find('.//*[@data-room-id="B:floor-1:rear-bath"]')
                assert bath_group is not None
                windows = [line for line in bath_group.findall("{http://www.w3.org/2000/svg}line") if line.get("stroke") == "#3b7894"]
                assert len(windows) == 1
                assert [float(windows[0].get(k)) for k in ("x1", "x2", "y1", "y2")] == [1500, 2400, 17630, 17630]
                assert bath_group.find('.//*[@data-reserved="b-window-toilet-side-transfer"]') is not None
            for room in f["rooms"]:
                cell = next(c for mf in embedded["buildings"][0]["floors"] for c in mf["cells"] if c["id"] == room["id"])
                assert room["geometry"] == cell["tour_mm"] and room["features"] == cell["tour_features"]
                for i in room["furniture"]:
                    assert i["placement"] == cell["furniture_placements"]["tour_mm"][i["id"]]
                    assert tree.find('.//*[@data-furniture-id="'+i["id"]+'"]') is not None
    assert before == {p: sha256_file(p) for p in protected}
    index = Path(files["index"]).read_text()
    assert 'data-plan-viewer' in index and 'assets/plan_viewer.js' in index
    assert '未採用' in index and '原ABC主案' in index
    assert index.count('data-decision-status="confirmed-preference"') == 3
    assert index.count('data-decision-status="pending"') == 4
    assert "1.08m²" in index and 'data-decision="c-kitchen"' in index
    assert 'data-decision="c-kitchen" data-decision-status="confirmed-preference"' in index
    assert "取捨待決" not in index and "45cm待決" not in index
    assert "一樓洗衣備選" not in index and "三樓衛浴／休憩移位比較" not in index
    assert 'data-study-kind", "interior-improvements"' in Path(files["viewer"]).read_text()


@pytest.mark.parametrize("mode", ["rear", "front"])
def test_daily_adds_only_two_tentative_items_no_room_door_or_upper_floor_moves(mode, study):
    now, control = option(study, "b-"+mode+"-dry-service"), option(study, "b-"+mode+"-window")
    assert now["review"]["original_eight_comparisons_retained"]
    for n, (before, after) in enumerate(zip(control["plans"]["floors"], now["plans"]["floors"], strict=True)):
        old, new = {r["id"]: r for r in before["rooms"]}, {r["id"]: r for r in after["rooms"]}
        assert old.keys() == new.keys()
        for key, r in old.items():
            s = new[key]
            assert r["geometry"] == s["geometry"]
            for feature in ("doors", "open_connections", "window_mm", "window_face", "window_review", "stair_geometry"):
                assert r["features"].get(feature) == s["features"].get(feature)
            assert all(i in s["furniture"] for i in r["furniture"])
            if n or r["key"] != "laundry-base":
                assert r == s
        assert sum(len(r["furniture"]) for r in after["rooms"]) - sum(len(r["furniture"]) for r in before["rooms"]) == (2 if n == 0 else 0)
    assert now["review"]["area_rows"] == control["review"]["area_rows"]
    assert now["review"]["carry_entry_mode"] == mode
    assert now["review"]["carry_body_115mm"] == control["review"]["carry_body_115mm"]
    assert now["review"]["front_continuous_1500mm_shortfall_mm"] == 70
    assert now["review"]["independent_outdoor_work_balcony"].startswith("unmet")


@pytest.mark.parametrize("mode", ["rear", "front"])
def test_daily_keeps_original_equipment_operations_and_small_rack_is_not_scaled_catalog(mode, study):
    o = option(study, "b-"+mode+"-dry-service")
    daily = o["review"]["daily_use_review"]
    first = rooms(o, 0)
    rack = next(i for i in first["laundry-base"]["furniture"] if i["shape"] == "clothes-rack")
    dehum = next(i for i in first["laundry-base"]["furniture"] if i["catalog_id"] == "dehumidifier")
    assert rack["catalog_id"] == "generic-indoor-drying-envelope-1200"
    assert [rack[k] for k in ("width_mm", "depth_mm", "height_mm")] == [1200, 600, 1600]
    assert read_json(ROOT / "inputs/furniture-layout.json")["catalog"]["clothes-rack"]["width_mm"] == 2400
    assert rack["placement"]["aabb"] == export._bounds([3005, 13785, 1200, 600])
    assert rack["placement"]["operation_mm"] == export._bounds([3005, 13085, 1200, 700])
    assert dehum["placement"]["aabb"] == export._bounds([2500, 13985, 350, 300])
    assert not rack.get("physical_item_label") and not dehum.get("physical_item_label")
    assert rack["physical_item_id"] is dehum["physical_item_id"] is None
    assert daily["equipment"]["rack_count"] == 1
    assert daily["equipment"]["laundry_machines"] == [{"id": "B:floor-1:laundry-front:furniture:washer", "floor": "floor-1", "catalog": "washer"}]
    assert daily["equipment"]["dehumidifier_service_mm"] == [2400, 13885, 550, 500]
    assert not o["review"]["operation_vs_fixed_body"]
    for row in daily["sensitivity"]:
        assert not row["equipment_and_operation_failures"]
        assert not row["local_loading_700mm_body_route"]["coordinate_failures"]
        assert row["local_loading_700mm_body_route"]["body_mm"] == [700, 700]
    assert daily["local_scope"].startswith("700mm-loading-body-not-public")
    assert all(v.startswith("unknown") for v in daily["mechanical_requirements"].values())
    assert daily["original_work_balcony"].startswith("unmet")


def test_daily_does_not_call_ritual_seated_mode_pass_or_count_cross_corridor_as_laundry(study):
    daily = option(study, "b-rear-dry-service")["review"]["daily_use_review"]
    for row in daily["sensitivity"]:
        assert any("ritual-approach" in s for s in row["ceremony_bath_access_failures"])
        assert any("bench-" in s for s in row["ceremony_bath_access_failures"])
        assert row["ceremony_bath_access_status"].startswith("blocked-do-not-treat-pause-or-upstairs")
    cut = daily["cross_corridor"]
    assert cut["nominal_area_taken_sqm"] == 3.3448
    assert [r["area_sqm"] for r in cut["remaining_laundry_area_sensitivity"]] == [2.0832, 1.868, 1.7108]
    assert cut["original_minimum_sqm"] == 4 and cut["original_target_sqm"] == 5
    assert cut["position"].startswith("reject-this-local-cut")
    assert cut["new_doors_hardware_and_complete_route"].startswith("not-designed")
    next_step = daily["next_recommendation"]
    assert next_step["status"] == "owner-direction-required-not-drawn-or-adopted"
    assert next_step["simple_swap_front_carry_status"].startswith("not-accommodated")
    assert next_step["left_front_lane_clear_115mm_if_only_rooms_swapped"] == 1130
    assert next_step["unassembled_body_width_mm"] == 1200
    assert next_step["rear_access_rights"] == "unknown-no-rear-alley-assumed"


@pytest.mark.parametrize("cut", [[20, 20, 60, 60], [0, 0, 100, 100], [200, 200, 10, 10], [-10, 40, 200, 20]])
def test_cross_corridor_subtraction_has_exact_disjoint_area(cut):
    rect = [0, 0, 100, 100]
    remaining = subtract_rect(rect, cut)
    x0, y0, x1, y1 = max(0, cut[0]), max(0, cut[1]), min(100, cut[0]+cut[2]), min(100, cut[1]+cut[3])
    overlap = max(0, x1-x0)*max(0, y1-y0)
    assert sum(r[2]*r[3] for r in remaining) == 10000-overlap
    for n, r in enumerate(remaining):
        assert _covered(r, [rect]) and not _hits(r, cut)
        assert all(not _hits(r, other) for other in remaining[n+1:])


def test_daily_dehumidifier_in_original_sink_operation_is_not_allowed(monkeypatch):
    original = export.read_json
    def read(path):
        cfg = original(path)
        if path.name == "interior-improvements.json":
            cfg["b_daily_use"]["dehumidifier"]["rect_mm"] = [1800, 13300, 350, 300]
        return cfg
    monkeypatch.setattr(export, "read_json", read)
    with pytest.raises(ContractError, match="retained-operation or local-access conflict"):
        export.build_study()


def test_daily_moisture_and_working_band_claims_cannot_be_marked_approved(study):
    o = option(study, "b-rear-dry-service")
    cfg = read_json(ROOT / export.SOURCE)["b_daily_use"]
    prior = o["review"]
    seated = read_json(ROOT / "inputs/b32-service-detail.json")["shrine"]["ritual_seated_benches"]
    cfg["mechanical_requirements"]["dehumidification_capacity_heat_noise_and_controls"] = "approved"
    with pytest.raises(ContractError, match="ventilation or drying approval"):
        review_daily_use(o["plans"], cfg, prior, [80, 100, 115], seated)
    cfg = read_json(ROOT / export.SOURCE)["b_daily_use"]
    cfg["drying_rack"]["front_operation_rect_mm"][3] = 600
    with pytest.raises(ContractError, match="full 1200x700"):
        review_daily_use(o["plans"], cfg, prior, [80, 100, 115], seated)


def test_daily_sources_and_envelopes_are_serialized_to_svg(study, tmp_path):
    assert "house_design/b32_daily_use.py" in study["source_hashes"]
    export.write_study(study, tmp_path)
    svg = ET.parse(tmp_path / export.OUT / "b-rear-dry-service_floor-1.svg").getroot()
    assert svg.find('.//*[@data-furniture-id="B:floor-1:laundry-base:furniture:small-drying-rack"]') is not None
    assert svg.find('.//*[@data-furniture-id="B:floor-1:laundry-base:furniture:dehumidifier"]') is not None
    assert svg.find('.//*[@data-reserved="b-daily-drying-loading"]') is not None
    assert svg.find('.//*[@data-reserved="b-daily-dehumidifier-service"]') is not None


def test_source_and_report_hash_are_current_and_repeatable(study):
    assert all(sha256_file(ROOT / p) == v for p, v in study["source_hashes"].items())
    assert study["generator_sha256"] == sha256_file(Path(export.__file__))
    assert stable_hash({k: v for k, v in study.items() if k not in {"generated_at", "report_hash"}}) == study["report_hash"]
    assert export.build_study()["report_hash"] == study["report_hash"]

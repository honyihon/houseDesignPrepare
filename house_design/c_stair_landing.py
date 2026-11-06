"""Explicit shared floor landings; no whole-core expansion or scene build."""
from __future__ import annotations

import copy
import math

from house_design.c_balcony_coordination import _area, _box, _overlap, _path, _rect, _union_area
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.frozen_kaohsiung import MANIFEST, historical_artifact

CONFIG = "inputs/c-stair-shared-landing.json"
SCHEMA = "house-c-stair-shared-landing-v1"


def _surface(identifier, rect, z, kind, storey):
    return {"id": identifier, "rect_mm": rect, "top_z_mm": z, "kind": kind, "storey": storey}


def flight_surfaces(fid, base, height, footprint, risers, tread, width, departure, middle):
    x, y, w, depth = footprint
    n = risers//2
    run = (n-1)*tread
    if risers % 2 or not math.isclose(departure+run+middle, depth):
        raise ContractError("Flight run and landings must match the original bounded depth")
    start = y+departure
    result = [_surface(fid+":middle", [x, start+run, w, middle], base+height/2, "middle", fid)]
    for k in range(n-1):
        result.append(_surface(fid+":up-"+str(k+1), [x, start+k*tread, width, tread],
            base+(k+1)*height/risers, "tread", fid))
        result.append(_surface(fid+":return-"+str(n+k+1), [x+w-width, start+run-(k+1)*tread, width, tread],
            base+height/2+(k+1)*height/risers, "tread", fid))
    return result


def _centre(rect):
    return [rect[0]+rect[2]/2, rect[1]+rect[3]/2]


def _covers(rect, point):
    return rect[0] < point[0] < rect[0]+rect[2] and rect[1] < point[1] < rect[1]+rect[3]


def headroom_proxy(surfaces, structure, target):
    samples = []
    for lower in surfaces:
        if lower["kind"] != "tread":
            continue
        point = _centre(lower["rect_mm"])
        overhead = [s for s in surfaces if s["storey"] != lower["storey"]
            and s["top_z_mm"] > lower["top_z_mm"] and _covers(s["rect_mm"], point)]
        nearest = min(overhead, key=lambda s: s["top_z_mm"], default=None)
        gap = None if nearest is None else nearest["top_z_mm"]-structure-lower["top_z_mm"]
        samples.append({"walking_surface": lower["id"], "point_mm": [*point, lower["top_z_mm"]],
            "overhead_surface": None if nearest is None else nearest["id"], "proxy_gap_mm": gap})
    known = [s["proxy_gap_mm"] for s in samples if s["proxy_gap_mm"] is not None]
    return {"coordination_target_mm": target, "illustrative_structure_depth_mm": structure,
        "sample_count": len(samples), "samples_without_modelled_overhead": sum(s["proxy_gap_mm"] is None for s in samples),
        "minimum_sampled_gap_mm": min(known, default=None),
        "below_target": [s for s in samples if s["proxy_gap_mm"] is not None and s["proxy_gap_mm"] < target],
        "samples": samples, "actual_waist_slab_beams_handrails_and_clearance_approval": "unknown"}


def partition_comparison(plans, cfg, apron):
    """A forward door comparison; no airtight, acoustic or fire approval."""
    spec = cfg["front_partition_comparison"]
    plane, thickness = spec["plane_y_mm"], spec["partition_thickness_budget_mm"]
    approach, side = spec["approach_depth_proxy_mm"], spec["approach_side_budget_mm"]
    if (spec["status"] != "owner-selected-development-pending-professional-review"
            or spec.get("selected_option") != "forward-closing-door"
            or spec.get("owner_confirmation", {}).get("quote") != "前置可關門版 可以接受"
            or not spec.get("owner_confirmation", {}).get("scope") or plane != 8550 or thickness != 100
            or spec["nominal_opening_mm"] != 1200 or approach != 900 or side != 100):
        raise ContractError("Preserve owner-selected partition direction without extending approval scope")
    walls = [[2400, plane-thickness/2, 3600, thickness],
        [2400-thickness/2, plane+thickness/2, thickness, 8960-plane-thickness/2]]
    result = []
    for gate in spec["floors"]:
        floor = next(f for f in plans["floors"] if f["id"] == gate["floor"])
        x0, x1 = gate["opening_x_mm"]
        p0, p1 = gate["sliding_parking_x_mm"]
        if x1-x0 != 1200 or p1-p0 != 1200 or p0 != x1 or x0 < 2400 or p1 > 6000:
            raise ContractError("Door opening and side parking must remain explicit 1200mm budgets")
        approaches = {
            "outside": [x0-side, plane-thickness/2-approach, x1-x0+2*side, approach],
            "inside": [x0-side, plane+thickness*1.5, x1-x0+2*side, approach],
        }
        parking = [p0, plane+thickness/2, p1-p0, thickness]
        closed_leaf = [x0, parking[1], x1-x0, parking[3]]
        solids = [{"id": "partition-"+str(n), "rect_mm": w} for n, w in enumerate(walls)]
        solids += [{"id": "sliding-parking", "rect_mm": parking}]
        checks = solids+[{"id": "approach-"+k, "rect_mm": v} for k, v in approaches.items()]
        conflicts = []
        for room in floor["rooms"]:
            for item in room["furniture"]:
                for kind, box in (("body", item["placement"]["aabb"]), ("operation", item["placement"].get("operation_mm"))):
                    if not box:
                        continue
                    for candidate in checks:
                        if _area(_overlap(candidate["rect_mm"], _box(box))) > 0:
                            conflicts.append({"item": item["id"], "kind": kind, "candidate": candidate["id"]})
        if conflicts or any(_area(_overlap(w, apron)) > 0 for w in walls+[parking]):
            raise ContractError("Forward partition/door budget overlaps furniture or required shared platform: "+str(conflicts))
        if any(_area(_overlap(parking, r)) > 0 for r in approaches.values()):
            raise ContractError("Open sliding leaf must not enter the approach budget")
        pocket = [2400, plane, 3600, 8960-plane]
        affected = [{"room": room["id"], "overlap_sqm": _area(_overlap(pocket, _rect(room["geometry"]))) }
            for room in floor["rooms"] if _area(_overlap(pocket, _rect(room["geometry"]))) > 0]
        if not math.isclose(sum(a["overlap_sqm"] for a in affected), _area(pocket)):
            raise ContractError("Front vestibule proxy must be fully accounted in existing public floor")
        door_to_step = apron[1]+apron[3]-(plane+thickness/2)
        result.append({**copy.deepcopy(gate), "plane_y_mm": plane, "wall_budgets_mm": walls,
            "parking_rect_mm": parking, "closed_leaf_rect_mm": closed_leaf,
            "approach_rectangles_mm": approaches,
            "opening_width_nominal_mm": x1-x0, "actual_door_clear_width_mm": None,
            "vestibule_proxy_mm": pocket, "existing_public_floor_used_sqm": _area(pocket),
            "includes_earlier_shared_apron_sqm": .44,
            "additional_public_floor_in_pocket_sqm": _area(pocket)-.44,
            "affected_existing_rooms": affected, "inner_wall_face_to_first_riser_mm": door_to_step,
            "wall_to_shared_apron_gap_mm": apron[1]-(plane+thickness/2),
            "inner_leaf_face_to_first_riser_mm": apron[1]+apron[3]-parking[1]-parking[3],
            "leaf_to_shared_apron_gap_mm": apron[1]-parking[1]-parking[3],
            "furniture_body_and_operation_conflicts": conflicts,
            "actual_seals_leaf_hardware_slab_connection_and_rescue": "unknown"})
    if {r["floor"] for r in result} != {"floor-1", "floor-2"} or len(result) != 2:
        raise ContractError("Keep both first and second floor independent partition checks")
    first = next(r for r in result if r["floor"] == "floor-1")
    sight = []
    target = [4220, 9895]
    for x in (3000, 3400, 3800):
        start = [x, 3900]
        t = (plane-start[1])/(target[1]-start[1])
        at = start[0]+t*(target[0]-start[0])
        sight.append({"from_mm": start, "to_mm": target, "at_partition_x_mm": at,
            "passes_open_aperture_in_plan": first["opening_x_mm"][0] < at < first["opening_x_mm"][1],
            "closed_opaque_panel_intercepts_at_plane": 2400 < at < 6000})
    return {"status": spec["status"], "owner_preference": spec["selected_option"],
        "owner_confirmation": copy.deepcopy(spec["owner_confirmation"]),
        "selection_scope": "partition-direction-only-not-product-full-scheme-or-professional-approval",
        "options": [{"id": "shared-open", "selected": False, "new_partition": False,
            "public_floor_used_in_additional_pocket_sqm": 0, "acoustic_and_air_zone_isolation": "not-provided-by-open-apron"},
            {"id": "forward-closing-door", "selected": True, "new_partition": True,
                "floor_details": result, "acoustic_and_air_zone_isolation": "unknown-side-openings-and-actual-seals-needed"}],
        "sightline_proxy_first_floor": {"rays": sight,
            "all_open_rays_blocked": not any(s["passes_open_aperture_in_plan"] for s in sight),
            "scope": "three-plane-rays-to-one-first-flight-point-not-eye-height-all-angles-or-fengshui-approval"},
        "second_floor_bypass": {"path": ["living-nook", "day-reserve", "stair2f"],
            "source_side_door_width_mm": 900, "source_side_door_operation": "unconfirmed",
            "closing_front_door_does_not_close_side_door": True},
        "sliding_panel_and_fixed_panel_material": "opaque-or-privacy-study-no-selected-product",
        "regulatory_fire_and_stair_compartment": "unknown-no-professional-fire-approval",
        "sound_reduction_rating_dB": None, "open_door_fengshui_and_privacy_approval": "unknown"}


def door_fit_review(plans, cfg, partition):
    """Product-independent fit bounds and two-door connectivity, not air flow."""
    spec = cfg["door_fit_review"]
    if spec["clear_width_target_mm"] != 900:
        raise ContractError("Do not reduce the existing completed-clear-width target")
    values = [*spec["total_frame_stop_and_overlap_sensitivity_mm"],
        *spec["track_and_leaf_depth_sensitivity_mm"], *spec["leaf_width_sensitivity_mm"],
        spec["parking_corner_budget_mm"]]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values):
        raise ContractError("Door sensitivities must be finite positive values")
    gates = next(o for o in partition["options"] if o["selected"])["floor_details"]
    result = []
    for gate in gates:
        floor = next(f for f in plans["floors"] if f["id"] == gate["floor"])
        available = 6000-gate["parking_rect_mm"][0]-spec["parking_corner_budget_mm"]
        depths = []
        for depth in spec["track_and_leaf_depth_sensitivity_mm"]:
            forward = max(0, depth-gate["parking_rect_mm"][3])
            moved = copy.deepcopy(gate["approach_rectangles_mm"]["outside"])
            moved[1] -= forward
            conflicts = []
            for room in floor["rooms"]:
                for item in room["furniture"]:
                    for kind, box in (("body", item["placement"]["aabb"]), ("operation", item["placement"].get("operation_mm"))):
                        if box and _area(_overlap(moved, _box(box))) > 0:
                            conflicts.append({"item": item["id"], "kind": kind})
            depths.append({"assumed_track_leaf_depth_mm": depth,
                "margin_to_apron_at_current_line_mm": 160-depth,
                "forward_shift_to_keep_original_60mm_budget_mm": forward,
                "extra_public_floor_if_shifted_sqm": 3600*forward/1e6,
                "shifted_outside_approach_mm": moved,
                "shifted_outside_approach_conflicts": conflicts,
                "shift_is_only_sensitivity_not_selected_new_door_line": True})
        result.append({"floor": gate["floor"], "clear_width_target_mm": spec["clear_width_target_mm"],
            "nominal_opening_mm": gate["opening_width_nominal_mm"], "selected_product": None,
            "actual_completed_clear_width_mm": None,
            "clear_width_cases": [{"total_frame_stop_overlap_mm": amount,
                "calculated_clear_width_mm": gate["opening_width_nominal_mm"]-amount,
                "margin_to_900mm_mm": gate["opening_width_nominal_mm"]-amount-900}
                for amount in spec["total_frame_stop_and_overlap_sensitivity_mm"]],
            "leaf_parking_available_before_corner_budget_mm": available,
            "leaf_width_cases": [{"assumed_leaf_width_mm": width, "parking_margin_mm": available-width}
                for width in spec["leaf_width_sensitivity_mm"]],
            "track_and_leaf_depth_cases": depths,
            "mechanical_stops_handles_clear_opening_and_maintenance": "unknown"})
    second = next(f for f in plans["floors"] if f["id"] == "floor-2")
    rooms = {r["key"]: r for r in second["rooms"]}
    side_door = next(d for d in rooms["stair2f"]["features"]["doors"]
        if d["neighbor"] == rooms["day-reserve"]["id"])
    for a, b in (("living2f", "living-nook"), ("living-nook", "day-reserve")):
        if not any(c["neighbor"] == rooms[b]["id"] for c in rooms[a]["features"]["open_connections"]):
            raise ContractError("Second-floor side-bypass source connections changed")
    states = []
    for front_open, side_open in ((True, True), (True, False), (False, True), (False, False)):
        routes = []
        if front_open:
            routes.append(["living2f", "stair2f"])
        if side_open:
            routes.append(["living2f", "living-nook", "day-reserve", "stair2f"])
        states.append({"front_door_open": front_open, "side_door_open": side_open,
            "specified_unobstructed_doorway_paths": routes,
            "people_can_open_closed_doors_and_air_leakage": "not-modelled-not-an-egress-or-airflow-graph"})
    return {"scope": "door-fit-sensitivities-and-specified-two-door-state-paths",
        "floor_details": result, "selected_product": None,
        "side_door": {"room_pair": [rooms["day-reserve"]["id"], rooms["stair2f"]["id"]],
            "face": side_door["face"], "ratio": side_door["ratio"], "source_nominal_width_mm": side_door["width_mm"],
            "source_operation": side_door["operation"], "clear_width_target_mm": 900,
            "actual_completed_clear_width_mm": None,
            "source_900mm_has_no_extra_frame_budget_for_900mm_goal": side_door["width_mm"] == 900,
            "action": "include-existing-side-door-in-same-fit-and-seal-review-widening-if-needed-is-not-yet-designed"},
        "two_door_states": states, "regulatory_fire_acoustic_rescue_and_products": "unknown",
        "both_closed_does_not_prove_airtight_or_soundproof": True}


def detail(plans, cfg):
    original = copy.deepcopy(plans)
    floors = {f["id"]: f for f in plans["floors"]}
    stair_rooms = {fid: next(r for r in floor["rooms"] if r["features"].get("stairs"))
        for fid, floor in floors.items()}
    core = _rect(stair_rooms["floor-1"]["geometry"])
    spec = cfg["first_stair"]
    for value in (cfg["headroom_proxy"]["illustrative_structure_depth_mm"], cfg["headroom_proxy"]["coordination_target_mm"]):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ContractError("Headroom proxy needs finite positive assumptions")
    footprint = spec["footprint_mm"]
    if (cfg.get("first_storey_mm") != 4000 or spec.get("risers") != 24 or spec.get("tread_mm") != 270
            or spec.get("flight_width_mm") != 1000 or spec.get("landing_depth_mm") != 1000
            or spec.get("departure_offset_mm") != 730 or spec.get("middle_landing_mm") != 1000
            or footprint != _rect(stair_rooms["floor-1"]["features"]["stair_footprint_mm"])):
        raise ContractError("Preserve the approved study direction and original flight box")
    step_start = footprint[1]+spec["departure_offset_mm"]
    apron = [footprint[0], step_start-spec["landing_depth_mm"], footprint[2], spec["landing_depth_mm"]]
    shared_depth = core[1]-apron[1]
    shared_strip = [apron[0], apron[1], apron[2], shared_depth]
    if shared_depth != 200:
        raise ContractError("Expected a 200mm shared floor-level apron, not a hidden core extension")
    shift = cfg["first_storey_mm"]-floors["floor-1"]["height_mm"]
    bases = {fid: f["base_mm"]+(shift if fid != "floor-1" else 0) for fid, f in floors.items()}
    surfaces = flight_surfaces("floor-1", bases["floor-1"], cfg["first_storey_mm"], footprint,
        spec["risers"], spec["tread_mm"], spec["flight_width_mm"], spec["departure_offset_mm"], spec["middle_landing_mm"])
    surfaces += [_surface("floor-1:shared-departure", apron, bases["floor-1"], "shared-landing", "floor-1"),
        _surface("floor-2:shared-arrival", apron, bases["floor-2"], "shared-landing", "floor-2")]
    for fid in ("floor-2", "floor-3"):
        room = stair_rooms[fid]
        old = room["features"]["stair_geometry"]
        fp = _rect(room["features"]["stair_footprint_mm"])
        surfaces += flight_surfaces(fid, bases[fid], floors[fid]["height_mm"], fp,
            old["risers"], old["tread_mm"], old["flight_width_mm"], old["departure_offset_mm"], old["middle_landing_mm"])
        lower_width = old["flight_width_mm"] if fid == "floor-2" else fp[2]
        surfaces.append(_surface(fid+":departure", [fp[0], fp[1], lower_width, old["landing_mm"]], bases[fid], "departure", fid))
    roof_fp = _rect(stair_rooms["floor-4"]["features"]["stair_footprint_mm"])
    surfaces.append(_surface("floor-4:arrival", [roof_fp[0], roof_fp[1], roof_fp[2], 1000], bases["floor-4"], "roof-arrival", "floor-4"))
    old_top = stair_rooms["floor-2"]["features"]["stair_geometry"]
    old_top_fp = _rect(stair_rooms["floor-2"]["features"]["stair_footprint_mm"])
    removed = [footprint[0]+spec["flight_width_mm"], step_start,
        footprint[2]-spec["flight_width_mm"], old_top_fp[1]+old_top["landing_mm"]-step_start]
    incoming_last = next(s for s in surfaces if s["id"] == "floor-1:return-23")
    naive_gap = bases["floor-2"]-cfg["headroom_proxy"]["illustrative_structure_depth_mm"]-incoming_last["top_z_mm"]
    shared_areas, landing_body_conflicts = [], []
    for fid in ("floor-1", "floor-2"):
        affected = []
        for room in floors[fid]["rooms"]:
            overlap = _overlap(shared_strip, _rect(room["geometry"]))
            if _area(overlap) <= 0:
                continue
            affected.append({"room": room["id"], "shared_rect_mm": overlap, "shared_sqm": _area(overlap)})
            for item in room["furniture"]:
                for kind, box in (("body", item["placement"]["aabb"]), ("operation", item["placement"].get("operation_mm"))):
                    if box and _area(_overlap(shared_strip, _box(box))) > 0:
                        landing_body_conflicts.append({"floor": fid, "item": item["id"], "kind": kind})
        shared_areas.append({"floor": fid, "affected": affected, "union_shared_sqm": _union_area([a["shared_rect_mm"] for a in affected])})
    proxy = headroom_proxy(surfaces, cfg["headroom_proxy"]["illustrative_structure_depth_mm"], cfg["headroom_proxy"]["coordination_target_mm"])
    if landing_body_conflicts or proxy["below_target"]:
        raise ContractError("Shared landing clashes with furniture or listed stair surfaces")
    corridor = [2400, 8960, 1200, 4840]
    upper_hall = next(r for r in floors["floor-3"]["rooms"] if r["key"] == "front-hall")
    protected = [r for f in plans["floors"] for r in f["rooms"]
        if r["key"] in ("elder", "elder-bath", "front-hall")]
    if plans != original:
        raise ContractError("Detail must not mutate frozen rooms, furniture or openings")
    partition = partition_comparison(plans, cfg, apron)
    return {"schema": SCHEMA, "revision": 3, "status": cfg["status"],
        "owner_authorized_detail_direction": "4000mm-24-risers-270mm-treads",
        "complete_scheme_adopted": False, "professional_approval": "unknown",
        "source_option": "c-split", "source_state": "daily", "source_plans_mutated": False,
        "core_rect_mm": core, "flight_footprint_mm": footprint,
        "first_stair": {**copy.deepcopy(spec), "riser_mm": cfg["first_storey_mm"]/spec["risers"],
            "treads_per_flight": 11, "run_mm": 2970, "first_step_start_y_mm": step_start,
            "middle_start_y_mm": step_start+2970, "whole_core_extension_mm": 0,
            "original_front_70mm_reallocated_to_shared_level_floor": 70,
            "rear_70mm_nominal_budget_retained": 70,
            "departure_offset_is_not_full_landing_depth": True},
        "floor_bases_mm": bases,
        "shared_level_apron_mm": apron, "shared_front_strip_mm": shared_strip,
        "shared_floor_areas": shared_areas,
        "source_furniture_count": sum(len(r["furniture"]) for f in plans["floors"] for r in f["rooms"]),
        "source_room_and_furniture_hash": stable_hash(plans["floors"]),
        "protected_rooms": [{"id": r["id"], "geometry": r["geometry"], "furniture_sha256": stable_hash(r["furniture"])} for r in protected],
        "third_floor_front_hall_mm": _rect(upper_hall["geometry"]),
        "left_public_corridor_nominal_mm": corridor,
        "corridor_to_flight_horizontal_budget_mm": footprint[0]-corridor[0]-corridor[2],
        "nominal_corridor_is_not_finished_clear_width": True,
        "opening_proposals": [
            {"floor": "floor-1", "y_mm": core[1], "x_range_mm": [2900, 5920],
                "opening_width_mm": 3020, "operation": "shared-unobstructed-opening-leaf-pending",
                "replaces_front_door_width_mm": 1000,
                "neighbors": [{"room": "C:floor-1:living-hall", "x_range_mm": [2900, 4000]},
                    {"room": "C:floor-1:living-right", "x_range_mm": [4000, 5920]}]},
            {"floor": "floor-2", "y_mm": core[1], "x_range_mm": [3720, 5920],
                "opening_width_mm": 2200, "operation": "shared-unobstructed-opening-leaf-pending",
                "replaces_front_door_width_mm": 900,
                "neighbors": [{"room": "C:floor-2:living2f", "x_range_mm": [3720, 5920]}]},
        ],
        "upper_floor_18_riser_and_RF_arrival_locations": "retained-relative-positions-bases-shifted-only",
        "second_floor_floor_level_platform_removed_mm": removed,
        "removed_platform_sqm": _area(removed),
        "naive_full_width_platform_gap_over_last_incoming_tread_mm": naive_gap,
        "surfaces": surfaces, "headroom_proxy": proxy,
        "landing_furniture_and_operation_conflicts": landing_body_conflicts,
        "legal_fire_separation_opening_structure_and_actual_headroom": "unknown",
        "open_stair_acoustics_privacy_and_fengshui_acceptance": "open-baseline-not-selected-no-fengshui-approval",
        "if_independent_fire_or_privacy_door_required": "forward-privacy-layout-selected-redesign-door-and-platform-if-rated-system-requires-not-in-730mm-offset",
        "balcony_soil_section_and_AC01_riser": "remain-unresolved-in-separate-coordination-study",
        "comparison_250mm_tread": "retained-in-c-balcony-coordination-not-used-here",
        "front_partition_comparison": partition,
        "door_fit_review": door_fit_review(plans, cfg, partition)}


def build(root):
    cfg = read_json(root/CONFIG)
    if (cfg.get("schema") != SCHEMA or cfg.get("status") != "bounded-detail-pending-architect-review"
            or cfg.get("option") != "c-split" or cfg.get("state") != "daily"
            or cfg.get("professional_approval") != "unknown"):
        raise ContractError("Preserve bounded stair detail and unknown approval")
    path = _path(root, cfg["base_report"])
    if sha256_file(path) != cfg["base_report_sha256"]:
        raise ContractError("Frozen C basis changed")
    report = read_json(path)
    for group in (report["source_hashes"], report["artifact_hashes"]):
        for name, digest in group.items():
            if sha256_file(_path(root, name)) != digest:
                if name not in report["artifact_hashes"] or sha256_file(historical_artifact(root, name, digest)) != digest:
                    raise ContractError("Frozen C dependency changed: "+name)
    option = next(o for o in report["options"] if o["id"] == cfg["option"])
    state = next(s for s in option["states"] if s["id"] == cfg["state"])
    result = detail(state["plans"], cfg)
    sources = [CONFIG, cfg["base_report"], "house_design/c_stair_landing.py",
        "house_design/c_balcony_coordination.py", "house_design/contracts.py", "scripts/export_c_stair_landing.py",
        "house_design/frozen_kaohsiung.py", MANIFEST]
    result["source_hashes"] = {name: sha256_file(root/name) for name in sources}
    result["parent_source_and_artifact_counts"] = [len(report["source_hashes"]), len(report["artifact_hashes"])]
    return result

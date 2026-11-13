"""Coordinate frozen Q3 arrival with roof doors, daily use and inspection paths."""
from __future__ import annotations

import copy
from itertools import product
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

from house_design.b_ktv_stair_options import incoming_steps, side_leaf
from house_design.b_upper_replan import bridge, door, finish, hit, rect, ring, sweep
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-q3-roof-coordination.json"
OUT = "structured/coordination/b-q3-roof-coordination-v1"
STATES = {"open": 90, "half": 45, "closed": 0}


def required_floor(cfg, q3, daily):
    landing = q3["upper_stairs"]["primary"]["floor_landing_mm"]
    vestibule = cfg["vestibule_floor_mm"]
    source = daily["stair_source_room"]
    side = cfg["side_door"]
    original_side = source["features"]["doors"][0]
    original_side_center = source["rect_mm"][1]+source["rect_mm"][3]*original_side["ratio"]
    if (cfg["roof_enclosure_mm"] != source["rect_mm"] or side["a"][0] != 2400 or side["b"][0] != 2400
            or side.get("hinge") != "rear" or side.get("opens") != "right"
            or abs((side["a"][1]+side["b"][1])/2-original_side_center) > .01 or side["b"][1]-side["a"][1] != original_side["width_mm"]):
        raise ContractError("Preserve the original RF enclosure and nominal side aperture")
    if landing != [80, 4770, 2200, 1000] or vestibule != [115, 4015, 2170, 755]:
        raise ContractError("RF arrival no longer matches the explicit Q3 full-platform/vestibule condition")
    threshold = [2280, side["a"][1]+cfg["frame_each_side_mm"], 235, side["b"][1]-side["a"][1]-2*cfg["frame_each_side_mm"]]
    front = daily["nominal_front_door"]
    indoor = unary_union([rect(landing), rect(vestibule), bridge(front, cfg["frame_each_side_mm"]), rect(threshold)])
    well = [80, landing[1]+landing[3], 2200, q3["upper_stairs"]["primary"]["new_rear_end_mm"]-landing[1]-landing[3]]
    incoming = copy.deepcopy(q3["original_stairs_by_floor"]["floor-3"])
    incoming["footprint"] = copy.deepcopy(q3["upper_stairs"]["primary"]["footprint"])
    incoming["geometry"]["middle_landing_mm"] = q3["upper_stairs"]["primary"]["middle_landing_mm"]
    steps = incoming_steps(incoming)
    covered = [s["id"] for s in steps if hit(indoor, rect(s["rect_mm"]))]
    full_cap = rect(cfg["roof_enclosure_mm"])
    rejected = [s["id"] for s in steps if hit(full_cap, rect(s["rect_mm"]))]
    if covered or hit(indoor, rect(well)):
        raise ContractError("RF proposed floor caps a Q3 incoming tread or the retained stairwell")
    return {"landing_mm": landing, "vestibule_mm": vestibule, "side_threshold_mm": threshold,
        "front_threshold_polygon_mm": ring(bridge(front, cfg["frame_each_side_mm"])), "stairwell_keep_open_mm": well,
        "covered_Q3_tread_ids": covered, "rejected_full_enclosure_cap_tread_ids": rejected,
        "Q3_incoming_treads": steps, "enclosure_nominal_sqm": rect(cfg["roof_enclosure_mm"]).area/1e6,
        "roof_floor_full_width_and_same_level_required_not_verified": True,
        "entire_stair_headroom_slab_support_or_penthouse_legality_approved": False,
        "original_RF_side_door_center_y_mm": round(original_side_center, 3), "side_door_moved": False,
        "new_RF_stair_geometry_or_building_data_received": 0}, indoor


def make_option(cfg, q3, daily, roof, old_daily, indoor):
    r1 = roof["R1_reference"]
    guarded_opening = unary_union([rect(r1["rf_opening_mm"])]+[Polygon(p) for p in r1["rf_guard_polygons_mm"]])
    frame = finish(rect([0, 0, *cfg["frame_mm"]]), cfg["edge_budget_mm"])
    # The RF front wall occupies the rear edge of the front deck except at its explicit door threshold.
    front_wall = rect([0, 3900-cfg["edge_budget_mm"], 2400, cfg["edge_budget_mm"]])
    outdoor = frame.difference(unary_union([rect(cfg["roof_enclosure_mm"]), guarded_opening, front_wall]))
    surface = unary_union([outdoor, indoor])
    protected = unary_union([Polygon(p) for p in q3["protected_polygons_mm"]])
    equipment = next(o for o in roof["options"] if o["id"] == old_daily["equipment_option_id"])
    furniture, reservations = old_daily["furniture"], equipment["reservations"]
    fixed = [{"id": i["id"], "shape": rect(i.get("body_mm", i["rect_mm"]))} for i in reservations]+[{"id": i["id"], "shape": rect(i["rect_mm"])} for i in furniture]
    old_spec = next(o for o in daily["config"]["options"] if o["id"] == old_daily["id"])
    specs = [
        {"id": "daily-arrival", "points_mm": cfg["daily_arrival_route_mm"], "width_mm": cfg["ordinary_route_width_mm"], "door": "front", "use": "daily"},
        {"id": "rack-operation", "points_mm": daily["config"]["rack_route_mm"], "width_mm": 700, "door": None, "use": "daily"},
        {"id": "table-operation", "points_mm": old_spec["table_route_mm"], "width_mm": 700, "door": None, "use": "daily"}]
    for old in equipment["inspection_routes"]:
        if old["points_mm"][0] != [2850, 4400]:
            raise ContractError("RF old inspection start no longer matches the retained side door")
        front_heat_pump = old["id"] == "heat-pump-boundary" and next(i for i in reservations if i["id"] == "heat-pump")["rect_mm"][1] < 3900
        specs.append({"id": "inspect-"+old["id"],
            "points_mm": cfg["front_heat_pump_inspection_mm"] if front_heat_pump else cfg["inspection_prefix_mm"]+old["points_mm"],
            "width_mm": 700, "door": "front" if front_heat_pump else "side", "use": "necessary-inspection"})
    routes = []
    for spec in specs:
        shape = sweep(spec["points_mm"], spec["width_mm"])
        over = shape.intersection(protected).area/1e6
        routes.append({**spec, "inside_explicit_same_revision_surface": surface.buffer(.01).covers(shape),
            "fixed_body_hits": [i["id"] for i in fixed if hit(shape, i["shape"])],
            "void_or_guard_hit": hit(shape, guarded_opening), "over_protected_sqm": round(over, 6),
            "protection_scope": "no-daily-entry-into-protection" if spec["use"] == "daily" else "existing-necessary-inspection-premise-not-expanded",
            "shared_operation_ids": [i["id"] for i in furniture if hit(shape, rect(i["operation_mm"]))],
            "actual_human_transport_or_religious_approval": "unknown"})
    states = []
    front_door = daily["nominal_front_door"]
    for front, side in product(STATES, repeat=2):
        leaves = {"front": door(front_door, STATES[front]), "side": side_leaf(cfg["side_door"], STATES[side])}
        states.append({"front": front, "side": side,
            "fixed_body_hits": [{"door": key, "body": i["id"]} for key, leaf in leaves.items() for i in fixed if hit(leaf, i["shape"])],
            "leaf_pair_hit": hit(leaves["front"], leaves["side"]),
            "route_blockers": {r["id"]: [key for key, leaf in leaves.items() if hit(leaf, sweep(r["points_mm"], r["width_mm"]))] for r in routes}})
    sweep_hits = [{"door": key, "angle_deg": angle, "body": i["id"]}
        for key, function, spec in [("front", door, front_door), ("side", side_leaf, cfg["side_door"])]
        for angle in range(0, 91, 15) for i in fixed if hit(function(spec, angle), i["shape"])]
    if sweep_hits or any(not r["inside_explicit_same_revision_surface"] or r["fixed_body_hits"] or r["void_or_guard_hit"]
            or (r["use"] == "daily" and r["over_protected_sqm"]) for r in routes):
        raise ContractError("Q3 RF floor/route conflict: "+str({"id": old_daily["id"], "sweep_hits": sweep_hits, "routes": routes}))
    for state in states:
        if state["fixed_body_hits"] or state["leaf_pair_hit"] or any(state["route_blockers"][r["id"]] != ([r["door"]] if r["door"] and state[r["door"]] != "open" else []) for r in routes):
            raise ContractError("Q3 RF independent door conflict: "+str(state))
    widths = []
    for width in cfg["arrival_width_cases_mm"]:
        shape = sweep(cfg["daily_arrival_route_mm"], width)
        widths.append({"width_mm": width, "inside_required_full_platform_and_vestibule": surface.buffer(.01).covers(shape),
            "body_hits": [i["id"] for i in fixed if hit(shape, i["shape"])], "fully_open_front_door_hit": hit(shape, door(front_door, 90)),
            "over_protected_sqm": round(shape.intersection(protected).area/1e6, 6), "product_or_care_approval": "unknown"})
    if any(not w["inside_required_full_platform_and_vestibule"] or w["body_hits"] or w["fully_open_front_door_hit"] or w["over_protected_sqm"] for w in widths):
        raise ContractError("Q3 RF declared arrival width cannot fit its explicit floor condition")
    return {"id": "Q3-"+old_daily["id"], "title": "Q3 RF｜"+old_daily["title"], "old_daily_option_id": old_daily["id"],
        "equipment_option_id": equipment["id"], "equipment_reference_hash": stable_hash(equipment), "daily_reference_hash": stable_hash(old_daily),
        "equipment_reservations": copy.deepcopy(reservations), "furniture": copy.deepcopy(furniture),
        "front_door": copy.deepcopy(front_door), "side_door": copy.deepcopy(cfg["side_door"]),
        "routes": routes, "door_states": states, "sampled_swing_body_hits": sweep_hits, "arrival_width_cases": widths,
        "front_open_outline_before_daily_furniture_sqm": old_daily["front_open_outline_before_daily_furniture_sqm"],
        "front_open_outline_after_daily_furniture_sqm": old_daily["front_open_outline_after_daily_furniture_sqm"],
        "arrival_shares_folding_operation": "folding-table" in routes[0]["shared_operation_ids"],
        "front_heat_pump_inspection_rerouted_around_drying_rack": any(r["id"] == "inspect-heat-pump-boundary" and r["door"] == "front" for r in routes),
        "prior_heat_pump_route_over_drying_rack_sqm": round(sweep(next(r["points_mm"] for r in equipment["inspection_routes"] if r["id"] == "heat-pump-boundary"), 700)
            .intersection(rect(next(i["rect_mm"] for i in furniture if i["id"] == "drying-rack"))).area/1e6, 6),
        "full_enclosure_floor_cap_allowed": False, "new_inspection_results_recomputed_not_inherited": True,
        "RF24_goal_met_or_reduced": False, "adopted": False, "all_actual_devices_piping_or_products_approved": False}


def build(root):
    root, cache = Path(root), {}
    cfg = read_json(root/CONFIG)
    if (cfg.get("schema") != "house-b-q3-roof-coordination-v1" or cfg.get("adopted") is not False or cfg["frame_mm"] != [6000, 17630]
            or cfg["edge_budget_mm"] != 115 or cfg["frame_each_side_mm"] != 115 or cfg["ordinary_route_width_mm"] != 700
            or cfg["arrival_width_cases_mm"] != [700, 800, 900]
            or cfg["daily_arrival_route_mm"][0] != [1780, 5270] or cfg["inspection_prefix_mm"][0] != [1780, 5270]):
        raise ContractError("Keep independent Q3 RF planning frame and explicit budgets")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen Q3 RF parent changed: "+name)
    q3, daily = [read_json(root/cfg[k]) for k in ["q3_report", "daily_report"]]
    for parent in [q3, daily]:
        for name, expected in parent["source_hashes"].items():
            if digest(root, name, cache) != expected:
                raise ContractError("Q3 RF parent source drift: "+name)
    controls = read_json(root/cfg["protected_controls"])["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    roof = read_json(root/daily["config"]["parent_report"])
    if q3["RF_arrival_platform_shift_mm"] != 800 or q3["primary"]["KTV_area_after_wrap_and_cabinet_sqm"] != 20.1889:
        raise ContractError("Q3 RF does not attach to the frozen800mm/20.1889sqm variant")
    floor, indoor = required_floor(cfg, q3, daily)
    options = [make_option(cfg, q3, daily, roof, option, indoor) for option in daily["options"]]
    report = {"schema": "house-b-q3-roof-coordination-report-v1", "date": cfg["date"], "config": cfg,
        "q3_report_hash": q3["report_hash"], "daily_report_hash": daily["report_hash"], "q3_primary_hash": stable_hash(q3["primary"]),
        "floor_requirements": floor, "options": options, "protected_polygons_mm": q3["protected_polygons_mm"],
        "R1_reference": roof["R1_reference"], "Q3_KTV_area_reference_sqm": q3["primary"]["KTV_area_after_wrap_and_cabinet_sqm"],
        "front_door_nominal_mm": 1130, "front_door_clear_budget_mm": 900,
        "side_door_nominal_mm": 1000, "side_door_clear_budget_mm": 770,
        "RF_arrival_shift_from_original_mm": 800, "old_RF_enclosure_or_side_aperture_moved": False,
        "new_floor_slab_and_door_thresholds_required": True, "new_solid_slab_over_incoming_stairwell_allowed": False,
        "parent_daily_capacity": copy.deepcopy(daily["capacity"]), "RF_indoor_vestibule_added_to_outdoor_goal": False,
        "original_Q3_non_RF_geometry_changed": False, "first_floor_or_two_ground_entry_variants_changed": False,
        "all_actual_devices_and_piping_fitted": False, "protected_controls_unchanged": len(controls),
        "actual_site_or_product_data_received": 0, "primary_abc_or_3d_changed": False, "adopted": False,
        "all_original_requirements_met": False, "rendered_qa": "not-run", "professional_approval": "unknown",
        "conclusion": "Q3可用明確新到達平台與前室接回原RF前門／側門，側門不必僅因改梯後移；S1／S2設備與D1／D2桌架原位保留，日常及巡檢門態全部重算。完整樓板／平台仍是結構條件，後梯井保留，900試線不等於成品或照護核可，RF24㎡及其他工程缺口仍保留。"}
    names = [CONFIG, *cfg["pinned_sources"], *q3["source_hashes"], *daily["source_hashes"], cfg["protected_controls"],
        "house_design/b_q3_roof_coordination.py", "scripts/export_b_q3_roof_coordination.py", "Docs/b-q3-roof-coordination-v1.md"]
    report["source_hashes"] = {name: digest(root, name, cache) for name in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

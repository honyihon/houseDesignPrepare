"""Fixed-roof daily use, component capacity and conditional arrival geometry."""
from __future__ import annotations

import copy
from itertools import combinations
from pathlib import Path

from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from house_design.b_upper_replan import bridge, door, finish, hit, rect, sweep
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-roof-daily-use.json"
OUT = "structured/coordination/b-roof-daily-use-v1"


def components(shape):
    return list(shape.geoms) if shape.geom_type == "MultiPolygon" else [shape]


def make_option(cfg, spec, parent, platform, landing, full_landing, protected):
    equipment = next(o for o in parent["options"] if o["id"] == spec["parent_option"])
    items = copy.deepcopy(spec["furniture"])
    reservations = equipment["reservations"]
    fixed = [{"id": i["id"], "shape": rect(i.get("body_mm", i["rect_mm"]))} for i in reservations]+[
        {"id": i["id"], "shape": rect(i["rect_mm"])} for i in items]
    bodies = [{"a": a["id"], "b": b["id"]} for a, b in combinations(fixed, 2) if hit(a["shape"], b["shape"])]
    outside = [{"id": i["id"], "part": part} for i in items for part in ["rect_mm", "operation_mm"] if not platform.buffer(.01).covers(rect(i[part]))]
    equipment_hits = [{"id": i["id"], "part": part, "equipment": e["id"]} for i in items for part in ["rect_mm", "operation_mm"] for e in reservations if hit(rect(i[part]), rect(e["rect_mm"]))]
    other_bodies = [{"operation": a["id"], "body": b["id"]} for pair in combinations(items, 2) for a, b in [pair, pair[::-1]] if hit(rect(a["operation_mm"]), rect(b["rect_mm"]))]
    front_door = cfg["proposed_front_door"]
    floor = unary_union([platform, landing, bridge(front_door, cfg["door_width_frame_budget_each_mm"])])
    full_floor = unary_union([platform, full_landing, bridge(front_door, cfg["door_width_frame_budget_each_mm"])])
    specs = [{"id": "arrival-to-front", "points_mm": cfg["arrival_route_mm"], "expected_door": "front"},
        {"id": "rack-operation", "points_mm": cfg["rack_route_mm"], "expected_door": None},
        {"id": "table-operation", "points_mm": spec["table_route_mm"], "expected_door": None}]
    routes = []
    for r in specs:
        shape = sweep(r["points_mm"], cfg["ordinary_route_width_mm"])
        routes.append({**r, "width_mm": cfg["ordinary_route_width_mm"], "inside_conditional_floor": floor.buffer(.01).covers(shape),
            "fixed_body_hits": [i["id"] for i in fixed if hit(shape, i["shape"])],
            "over_protected_sqm": round(shape.intersection(protected).area/1e6, 6),
            "shared_operation_ids": [i["id"] for i in items if hit(shape, rect(i["operation_mm"]))],
            "person_motion_or_actual_clearance_approval": "unknown"})
    door_states = []
    for state, angle in cfg["door_states_deg"].items():
        leaf = door(front_door, angle)
        door_states.append({"state": state, "angle_deg": angle,
            "fixed_body_hits": [i["id"] for i in fixed if hit(leaf, i["shape"])],
            "route_blockers": {r["id"]: hit(leaf, sweep(r["points_mm"], r["width_mm"])) for r in routes},
            "leaf_polygon_mm": [list(p) for p in leaf.exterior.coords]})
    sweep_hits = [{"angle_deg": angle, "body": i["id"]} for angle in range(0, 91, 15) for i in fixed if hit(door(front_door, angle), i["shape"])]
    if (bodies or outside or equipment_hits or other_bodies or sweep_hits or any(not r["inside_conditional_floor"] or r["fixed_body_hits"] or r["over_protected_sqm"] for r in routes)
            or any(s["fixed_body_hits"] or any(s["route_blockers"][r["id"]] != (r["expected_door"] is not None and s["state"] != "open") for r in routes) for s in door_states)):
        raise ContractError("Daily roof geometry defect: "+str({"option": spec["id"], "bodies": bodies, "outside": outside, "equipment": equipment_hits, "operations": other_bodies,
            "door_sweep": sweep_hits, "routes": routes, "door_states": door_states}))
    widths = []
    for width in cfg["arrival_width_cases_mm"]:
        shape = sweep(cfg["arrival_route_mm"], width)
        widths.append({"width_mm": width, "inside_conditional_floor": floor.buffer(.01).covers(shape),
            "inside_if_source_full_width_landing_confirmed": full_floor.buffer(.01).covers(shape),
            "outside_conditional_floor_sqm": round(shape.difference(floor).area/1e6, 6),
            "fully_open_door_hit": hit(shape, door(front_door, 90)),
            "fixed_body_hits": [i["id"] for i in fixed if hit(shape, i["shape"])], "actual_clearance_or_care_approval": "unknown"})
    operation_shares = [{"operation": a["id"], "other_operation": b["id"], "sqm": round(rect(a["operation_mm"]).intersection(rect(b["operation_mm"])).area/1e6, 6)}
        for a, b in combinations(items, 2) if hit(rect(a["operation_mm"]), rect(b["operation_mm"]))]
    return {"id": spec["id"], "title": spec["title"], "equipment_option_id": equipment["id"], "equipment_reference_hash": stable_hash(equipment),
        "furniture": items, "equipment_reservations": reservations, "routes": routes, "door_states": door_states,
        "arrival_width_cases": widths, "furniture_body_or_operation_defects": [], "sampled_door_sweep_hits": sweep_hits,
        "shared_operation_pairs": operation_shares, "arrival_route_shares_folding_operation": "folding-table" in routes[0]["shared_operation_ids"],
        "simultaneous_two_person_work_and_escape_verified": False,
        "front_open_outline_before_daily_furniture_sqm": equipment["front_open_outline_including_shared_walkways_sqm"],
        "front_open_outline_after_daily_furniture_sqm": round(equipment["front_open_outline_including_shared_walkways_sqm"]-sum(rect(i["rect_mm"]).area/1e6 for i in items), 6),
        "area_scope": "paper-outline-including-circulation-not-complete-effective-or-legally-approved-area",
        "original_RF_deck_goal_sqm": 24, "original_RF_deck_goal_met": False, "goal_reduced_or_owner_adopted": False,
        "old_right_hinged_door_full_open_blocks_arrival_route": hit(door(parent["config"]["proposed_RF_front_door"], 90), sweep(cfg["arrival_route_mm"], cfg["ordinary_route_width_mm"])),
        "wet_laundry_appliance_or_new_drain_added": False, "outdoor_furniture_products_selected": False,
        "upstream_stairs_products_structure_weather_or_religion_approved": False, "adopted": False}


def build(root):
    root, cache = Path(root), {}
    cfg = read_json(root/CONFIG)
    if (cfg.get("schema") != "house-b-roof-daily-use-v1" or cfg.get("adopted") is not False or cfg["frame_mm"] != [6000, 17630]
            or cfg["ordinary_route_width_mm"] != 700 or cfg["edge_budget_mm"] != 115 or cfg["door_width_frame_budget_each_mm"] != 115
            or cfg["door_states_deg"] != {"open": 90, "half": 45, "closed": 0}):
        raise ContractError("Preserve independent daily-use study and explicit budgets")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen daily-use source changed: "+name)
    parent = read_json(root/cfg["parent_report"])
    for name, expected in parent["source_hashes"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("Daily-use parent source drift: "+name)
    controls = read_json(root/cfg["protected_controls"])["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    ground = read_json(root/cfg["ground_report"])
    rf = ground["stack_and_entry"]["options"][0]["roof_reference"]
    stair = next(r for r in rf["rooms"] if r["features"].get("stairs"))
    footprint, stairs = stair["features"]["stair_footprint_mm"], stair["features"]["stair_geometry"]
    if stairs["connects_to_next_storey"] is not False or footprint["y_mm"] != 3970 or stairs["departure_offset_mm"] != stairs["landing_mm"]:
        raise ContractError("Arrival geometry no longer matches the frozen RF/last right flight")
    landing_mm = [footprint["x_mm"]+footprint["w_mm"]-stairs["flight_width_mm"], footprint["y_mm"], stairs["flight_width_mm"], stairs["landing_mm"]]
    landing = rect(landing_mm)
    platform = finish(rect([0, 0, 6000, 3900]), cfg["edge_budget_mm"])
    frame = finish(rect([0, 0, *cfg["frame_mm"]]), cfg["edge_budget_mm"])
    protected = unary_union([Polygon(p) for p in parent["protected_polygons_mm"]])
    r1 = parent["R1_reference"]
    blocked = unary_union([protected, rect(stair["rect_mm"]), rect(r1["rf_opening_mm"])]+[Polygon(p) for p in r1["rf_guard_polygons_mm"]])
    open_parts = components(frame.difference(blocked))
    front = next(p for p in open_parts if p.covers(Point(1715, 2500)))
    rear = next(p for p in open_parts if p.covers(Point(3000, 15000)))
    if front.equals(rear) or front.area >= 24e6:
        raise ContractError("Daily roof components or fixed-front capacity no longer match the analysis")
    if {s["parent_option"] for s in cfg["options"]} != {o["id"] for o in parent["options"]} or len(cfg["options"]) != 2:
        raise ContractError("Preserve both independent S1/S2 alternatives")
    size_sets = [{i["id"]: sorted(i["rect_mm"][2:]) for i in o["furniture"]} for o in cfg["options"]]
    if size_sets[0] != size_sets[1] or size_sets[0] != {"drying-rack": [600, 1800], "folding-table": [450, 1200]}:
        raise ContractError("Use equal explicit representative furniture in both alternatives")
    connection = cfg["proposed_front_door"]
    if connection != {**parent["config"]["proposed_RF_front_door"], "hinge": "left"}:
        raise ContractError("Only change RF front door handing; preserve its nominal opening and source control")
    full_landing_mm = [footprint["x_mm"], footprint["y_mm"], footprint["w_mm"], stairs["landing_mm"]]
    options = [make_option(cfg, spec, parent, platform, landing, rect(full_landing_mm), protected) for spec in cfg["options"]]
    center = (connection["a"][0]+connection["b"][0])/2
    report = {"schema": "house-b-roof-daily-use-report-v1", "date": cfg["date"], "config": cfg,
        "parent_report_hash": parent["report_hash"], "parent_equipment_options_hash": stable_hash(parent["options"]),
        "options": options, "stair_source_room": stair, "arrival_platform_mm": landing_mm,
        "original_full_RF_arrival_slab_mm": full_landing_mm,
        "source_full_width_landing_structurally_usable_verified": False,
        "front_connection_strip_mm": [landing_mm[0], 3900, landing_mm[2], footprint["y_mm"]-3900],
        "nominal_front_door": connection, "door_nominal_width_mm": connection["b"][0]-connection["a"][0],
        "old_right_hinge_door_control": parent["config"]["proposed_RF_front_door"],
        "door_clear_budget_after_two_frames_mm": connection["b"][0]-connection["a"][0]-2*cfg["door_width_frame_budget_each_mm"],
        "arrival_platform_vs_door_center_offset_mm": landing.centroid.x-center,
        "900_route_left_of_conservative_platform_mm": landing_mm[0]-(center-450),
        "actual_3F_to_RF_stair_flights_levels_or_door_threshold_verified": False,
        "RF_existing_roof_hash": stable_hash(rf), "R1_opening_mm": r1["rf_opening_mm"], "protected_polygons_mm": parent["protected_polygons_mm"],
        "capacity": {"scope": "fixed-frame-stair-and-protection-topology-only-not-global-impossibility",
            "front_nominal_gross_sqm": 23.4, "front_before_equipment_with_edge_budget_sqm": round(front.area/1e6, 6),
            "front_short_of24_before_equipment_sqm": round(24-front.area/1e6, 6), "disconnected_component_count": len(open_parts),
            "rear_unconnected_area_before_equipment_sqm": round(rear.area/1e6, 6),
            "components_mm": [{"outer": [list(q) for q in p.exterior.coords], "holes": [[list(q) for q in h.coords] for h in p.interiors]} for p in open_parts],
            "front_and_rear_daily_areas_added_together": False, "ordinary_route_through_protection_authorized": False,
            "RF_deck_original_target_sqm": 24, "RF_deck_original_min_sqm": 10,
            "min10_is_owner_accepted_target": False, "removing_equipment_or_changing_only_front_door_can_solve24": False},
        "decision_paths": cfg["decision_paths"], "original_RF_requirements": parent["original_RF_requirements"],
        "protected_controls_unchanged": len(controls), "actual_site_or_product_data_received": 0,
        "primary_abc_or_3d_changed": False, "adopted": False, "all_original_requirements_met": False,
        "rendered_qa": "not-run", "professional_approval": "unknown",
        "conclusion": "固定前帶無法靠移機／改門湊24㎡。D1先保較寬鬆設備但折衣與通道分時；D2日常操作較順但後設備緊迫。兩案補入同尺寸桌架及RF前門三態，700／800試線可在條件地面通，900仍有到達平台偏移缺口。先保完整比較，24㎡及家規不改，待實際資料再取捨。"}
    names = [CONFIG, *cfg["pinned_sources"], *parent["source_hashes"], cfg["ground_report"], cfg["protected_controls"],
        "house_design/b_roof_daily_use.py", "scripts/export_b_roof_daily_use.py", "Docs/b-roof-daily-use-v1.md"]
    report["source_hashes"] = {n: digest(root, n, cache) for n in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

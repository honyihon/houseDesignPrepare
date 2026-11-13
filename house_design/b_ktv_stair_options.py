"""Independent L-shaped B3 entertainment/stair tradeoff with bounded local checks."""
from __future__ import annotations

import copy
import math
from itertools import product
from pathlib import Path

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from house_design.b_upper_replan import analyze_floor, bridge, finish, hit, rect, ring, room, sweep
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-ktv-stair-options.json"
OUT = "structured/coordination/b-ktv-stair-options-v1"
STATES = {"open": 90, "half": 45, "closed": 0}


def front_leaf(spec, angle):
    # The inherited helper assumes every front opening has y <= 3900; this one moves to y=4700.
    hinge, end = (spec["b"], spec["a"]) if spec["hinge"] == "right" else (spec["a"], spec["b"])
    vx = end[0]-hinge[0]
    r = math.radians(angle if spec["hinge"] == "right" else -angle)
    return LineString([hinge, [hinge[0]+vx*math.cos(r), hinge[1]+vx*math.sin(r)]]).buffer(47.5, cap_style=2)


def side_leaf(spec, angle):
    hinge, end = spec["b"], spec["a"]
    length = hinge[1]-end[1]
    r = math.radians(angle)
    return LineString([hinge, [hinge[0]+length*math.sin(r), hinge[1]-length*math.cos(r)]]).buffer(47.5, cap_style=2)


def stair_case(source, extension):
    original, g = source["footprint"], source["geometry"]
    middle = g["middle_landing_mm"]-extension
    proposed = {**original, "y_mm": original["y_mm"]+extension, "h_mm": original["h_mm"]-extension}
    landing = [proposed["x_mm"], proposed["y_mm"], proposed["w_mm"], g["landing_mm"]]
    return {"extension_mm": extension, "middle_landing_mm": middle, "footprint": proposed,
        "original_rear_end_mm": original["y_mm"]+original["h_mm"], "new_rear_end_mm": proposed["y_mm"]+proposed["h_mm"],
        "run_mm": g["run_mm"], "riser_count": g["risers"], "riser_mm": source["height_mm"]/g["risers"],
        "flight_width_mm": g["flight_width_mm"], "tread_mm": g["tread_mm"],
        "floor_landing_mm": landing, "geometry_depth_sum_mm": g["departure_offset_mm"]+g["run_mm"]+middle,
        "all_dimensions_are_source_assumptions_not_site_verification": True}


def capacity_cases(cfg, parent, source):
    front = rect(parent["config"]["front_room_mm"])
    shaft = rect(parent["front_2F_pipe_shaft_retained_mm"])
    wrap = shaft.buffer(cfg["shaft_extra_wrap_each_mm"], join_style=2)
    rows = []
    for extension in cfg["extension_depth_cases_mm"]:
        outline = unary_union([front, rect([0, 3900, cfg["front_left_extension_width_mm"], extension])]) if extension else front
        stair = stair_case(source, extension)
        for extra in cfg["extra_acoustic_cases_mm"]:
            usable = finish(outline, cfg["base_inset_mm"]+extra).difference(wrap)
            for service in cfg["extra_floor_service_cases_sqm"]:
                value = usable.area/1e6-service
                rows.append({"extension_mm": extension, "extra_acoustic_each_face_mm": extra, "extra_floor_service_sqm": service,
                    "shaft_wrap_each_mm": cfg["shaft_extra_wrap_each_mm"], "remaining_sqm": round(value, 6),
                    "goal20_met_in_area_model": value >= 20-1e-9, "middle_landing_mm": stair["middle_landing_mm"],
                    "middle_landing_meets_model_budget": stair["middle_landing_mm"] >= cfg["minimum_model_middle_landing_mm"],
                    "acoustic_performance_or_legal_approval": "unknown"})
    return rows


def incoming_steps(source):
    g, fp = source["geometry"], source["footprint"]
    count = g["risers"]//2
    start = fp["y_mm"]+g["departure_offset_mm"]
    tread, rise = g["run_mm"]/(count-1), source["height_mm"]/g["risers"]
    result = []
    for step in range(count-1):
        result.append({"id": "left-"+str(step+1), "rect_mm": [fp["x_mm"], start+step*tread, g["flight_width_mm"], tread],
            "top_z_mm": source["base_mm"]+(step+1)*rise})
        result.append({"id": "right-"+str(step+1), "rect_mm": [fp["x_mm"]+fp["w_mm"]-g["flight_width_mm"], start+g["run_mm"]-(step+1)*tread, g["flight_width_mm"], tread],
            "top_z_mm": source["base_mm"]+source["height_mm"]/2+(step+1)*rise})
    return result


def arrival_screen(cfg, stairs, incoming):
    old = stairs["original_upper_source"]["footprint"]
    old_pad = [old["x_mm"], old["y_mm"], old["w_mm"], stairs["original_upper_source"]["geometry"]["landing_mm"]]
    proposed_pad = stairs["primary"]["floor_landing_mm"]
    left_pad = [proposed_pad[0], proposed_pad[1], stairs["primary"]["flight_width_mm"], proposed_pad[3]]
    safe = unary_union([rect(old_pad), rect(left_pad)])
    slab_under = incoming["base_mm"]+incoming["height_mm"]-cfg["assumed_slab_thickness_for_local_screen_mm"]
    steps = incoming_steps(incoming)
    right_treads = [s for s in steps if s["id"].startswith("right")]
    naive_hits = [{"step": s["id"], "clearance_under_assumed_slab_mm": round(slab_under-s["top_z_mm"], 3)} for s in right_treads if hit(rect(proposed_pad), rect(s["rect_mm"]))]
    safe_hits = [s["id"] for s in right_treads if hit(safe, rect(s["rect_mm"]))]
    local = [{"step": s["id"], "clearance_under_assumed_slab_mm": round(slab_under-s["top_z_mm"], 3)} for s in steps if hit(safe, rect(s["rect_mm"]))]
    route = sweep(cfg["second_floor_transfer_route_mm"], 900)
    if safe_hits or not safe.buffer(.01).covers(route):
        raise ContractError("New 2F platform caps the old incoming flight or disconnects the listed transfer")
    return {"old_floor2_landing_mm": old_pad, "new_floor2_left_connection_mm": left_pad,
        "floor2_landing_polygon_mm": ring(safe), "naive_full_width_new_platform_over_incoming_right_steps": naive_hits,
        "actual_candidate_over_incoming_right_steps": safe_hits,
        "local_previous_left_tread_clearances_with200mm_assumption": local,
        "only_local_minimum_clearance_under_assumed_slab_mm": min((r["clearance_under_assumed_slab_mm"] for r in local), default=None),
        "second_floor_transfer_route_mm": cfg["second_floor_transfer_route_mm"], "transfer_width_mm": 900,
        "inside_explicit_L_landing_model": True,
        "full_headroom_structural_or_egress_approval": False,
        "first_floor_stair_changed": False}


def primary_geometry(cfg, parent, upper, stairs):
    extension = cfg["primary_extension_depth_mm"]
    outline = unary_union([rect(parent["config"]["front_room_mm"]), rect([0, 3900, cfg["front_left_extension_width_mm"], extension])])
    cabinet = {"id": "service-cabinet", "label": "600×900機櫃預留／非選機", "rect_mm": cfg["cabinet_rect_mm"], "operation_mm": cfg["cabinet_operation_mm"]}
    rooms = copy.deepcopy(parent["front_option"]["rooms"])
    for index, r in enumerate(rooms):
        if r["id"] == "front-entertainment":
            rooms[index] = room(r["id"], "Q3 L形前側娛樂／階梯代價比較", outline, [*cfg["front_furniture"], cabinet],
                r["shafts_mm"], [cfg["front_door"]], r["windows_mm"], "high-activity")
        elif r["id"] == "stair":
            rooms[index] = room(r["id"], "3F縮短上層折返平台的樓梯候選", rect([0, 3900+extension, 2400, 5200-extension]))
    protected = unary_union([Polygon(p) for p in upper["protected_polygons_mm"]])
    storage = rect(upper["palanquin_rect_mm"])
    analysis_rooms = copy.deepcopy(rooms)
    next(r for r in analysis_rooms if r["id"] == "front-entertainment")["doors"] = []
    floor = analyze_floor(analysis_rooms, upper["config"], protected, storage, {}, "floor-3", [])
    floor["rooms"] = rooms
    floor["front_and_new_side_door_motion_checked_by_explicit_geometry"] = True
    inset = cfg["base_inset_mm"]+cfg["primary_extra_acoustic_mm"]
    shaft = rect(parent["front_2F_pipe_shaft_retained_mm"])
    inner = finish(outline, inset).difference(shaft.buffer(cfg["shaft_extra_wrap_each_mm"], join_style=2))
    items = [*cfg["front_furniture"], cabinet]
    invalid = [{"id": i["id"], "part": p} for i in items for p in ["rect_mm", "operation_mm"] if i.get(p) and not inner.buffer(.01).covers(rect(i[p]))]
    landing = rect(stairs["primary"]["floor_landing_mm"])
    side_bridge = rect([landing.bounds[2], cfg["side_door"]["a"][1]+cfg["base_inset_mm"],
        cfg["side_door"]["b"][0]+cfg["base_inset_mm"]-landing.bounds[2],
        cfg["side_door"]["b"][1]-cfg["side_door"]["a"][1]-2*cfg["base_inset_mm"]])
    quiet = finish(Polygon(next(r["polygon_mm"] for r in rooms if r["id"] == "quiet-living")), cfg["base_inset_mm"])
    floor_surface = unary_union([inner, landing, bridge(cfg["front_door"], inset), side_bridge, quiet])
    specs = [{"id": "KTV-seat-operation", "points_mm": cfg["front_route_mm"], "width_mm": 700, "door": "front"},
        {"id": "quiet-from-landing", "points_mm": cfg["side_route_mm"], "width_mm": 700, "door": "side"},
        {"id": "KTV-arrival900", "points_mm": cfg["arrival_900_route_mm"], "width_mm": 900, "door": "front"}]
    all_items = [{**i, "room": r["id"]} for r in rooms for i in r["items"]]
    routes = []
    for r in specs:
        shape = sweep(r["points_mm"], r["width_mm"])
        routes.append({**r, "inside_explicit_surface": floor_surface.buffer(.01).covers(shape),
            "body_hits": [i["room"]+":"+i["id"] for i in all_items if hit(shape, rect(i["rect_mm"]))],
            "shaft_or_wrap_hit": hit(shape, shaft.buffer(cfg["shaft_extra_wrap_each_mm"], join_style=2)),
            "shared_operations": [i["room"]+":"+i["id"] for i in all_items if i.get("operation_mm") and hit(shape, rect(i["operation_mm"]))],
            "actual_person_or_product_clearance": "unknown"})
    states = []
    for front, side in product(STATES, repeat=2):
        shapes = {"front": front_leaf(cfg["front_door"], STATES[front]), "side": side_leaf(cfg["side_door"], STATES[side])}
        states.append({"front": front, "side": side,
            "body_hits": [{"door": name, "body": i["room"]+":"+i["id"]} for name, leaf in shapes.items() for i in all_items if hit(leaf, rect(i["rect_mm"]))],
            "door_pair_hit": hit(shapes["front"], shapes["side"]),
            "route_blockers": {r["id"]: [name for name, leaf in shapes.items() if hit(leaf, sweep(r["points_mm"], r["width_mm"]))] for r in specs}})
    sweep_hits = [{"door": name, "angle_deg": angle, "body": i["room"]+":"+i["id"]}
        for name, function, spec in [("front", front_leaf, cfg["front_door"]), ("side", side_leaf, cfg["side_door"])]
        for angle in range(0, 91, 15) for i in all_items if hit(function(spec, angle), rect(i["rect_mm"]))]
    bad_keys = ["body_hits", "operation_body_hits", "not_inside_115", "shaft_body_hits", "shaft_operation_hits", "fully_open_door_body_hits", "sampled_swing_body_hits"]
    if (invalid or sweep_hits or any(floor["fixtures"][k] for k in bad_keys) or floor["partition"]["overlaps"] or floor["partition"]["unallocated_sqm"] or floor["partition"]["outside_frame_sqm"]
            or any(p["prohibited_overlap"] for p in floor["religious_projection"])
            or any(not r["inside_explicit_surface"] or r["body_hits"] or r["shaft_or_wrap_hit"] for r in routes)):
        raise ContractError("Q3 room/route conflict: "+str({"invalid": invalid, "fixtures": floor["fixtures"], "routes": routes}))
    for s in states:
        if s["body_hits"] or s["door_pair_hit"] or any(s["route_blockers"][r["id"]] != ([r["door"]] if s[r["door"]] != "open" else []) for r in specs):
            raise ContractError("Q3 independent door-state defect: "+str(s))
    area = inner.difference(rect(cfg["cabinet_rect_mm"])).area/1e6
    return {"rooms": rooms, "floor_analysis": floor, "KTV_inner_polygon_mm": ring(inner),
        "KTV_area_after_wrap_and_cabinet_sqm": round(area, 6), "KTV_area_before_cabinet_after_wrap_sqm": round(inner.area/1e6, 6),
        "KTV_nominal_outline_sqm": round(outline.area/1e6, 6), "front_nominal_add_over_Q2_sqm": round(outline.area/1e6-23.4, 6),
        "additional_whole_floor_enclosed_volume_over_Q2_sqm": 0,
        "inset_each_face_mm": inset, "shaft_extra_wrap_each_mm": cfg["shaft_extra_wrap_each_mm"],
        "routes": routes, "door_states": states, "sampled_front_and_side_swing_body_hits": sweep_hits,
        "side_threshold_candidate_polygon_mm": ring(side_bridge),
        "front_nominal_aperture_mm": cfg["front_door"]["b"][0]-cfg["front_door"]["a"][0],
        "front_clear_budget_mm": cfg["front_door"]["b"][0]-cfg["front_door"]["a"][0]-2*inset,
        "acoustic_dB_or_full_airlock_and_silencer_approved": False}


def build(root):
    root, cache = Path(root), {}
    cfg = read_json(root/CONFIG)
    if (cfg.get("schema") != "house-b-ktv-stair-options-v1" or cfg.get("adopted") is not False or cfg["frame_mm"] != [6000, 17630]
            or cfg["base_inset_mm"] != 115 or cfg["primary_extra_acoustic_mm"] != 100 or cfg["primary_extension_depth_mm"] != 800
            or cfg["minimum_model_middle_landing_mm"] != 1000 or cfg["shaft_extra_wrap_each_mm"] != 50):
        raise ContractError("Keep independent Q3 frame and explicit primary budgets")
    for n, h in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, n)) != h:
            raise ContractError("Frozen Q3 source changed: "+n)
    parent = read_json(root/cfg["parent_report"])
    for n, h in parent["source_hashes"].items():
        if digest(root, n, cache) != h:
            raise ContractError("Q3 parent source drift: "+n)
    controls = read_json(root/cfg["protected_controls"])["hashes"]
    for n, h in controls.items():
        if digest(root, n, cache) != h:
            raise ContractError("Protected original changed: "+n)
    snapshot = read_json(root/cfg["stair_snapshot"])
    original_floors = next(o for o in snapshot["options"] if o["id"] == "b-rear-split")["states"][0]["plans"]["floors"]
    sources = {}
    for floor in original_floors:
        r = next(r for r in floor["rooms"] if r["features"].get("stairs"))
        sources[floor["id"]] = {"base_mm": floor["base_mm"], "height_mm": floor["height_mm"], "footprint": r["features"]["stair_footprint_mm"], "geometry": r["features"]["stair_geometry"]}
    upper = read_json(root/parent["config"]["upper_report"])
    source = sources["floor-2"]
    if (sources["floor-1"]["geometry"]["risers"] != 24 or sources["floor-1"]["height_mm"] != 4000
            or source["geometry"]["risers"] != 18 or source["height_mm"] != 3000 or source["geometry"]["middle_landing_mm"] != 1900
            or sources["floor-3"]["geometry"] != source["geometry"]):
        raise ContractError("Q3 upper flights no longer match the frozen 18-riser source")
    stairs = {"original_upper_source": source, "primary": stair_case(source, cfg["primary_extension_depth_mm"])}
    if stairs["primary"]["middle_landing_mm"] < cfg["minimum_model_middle_landing_mm"]:
        raise ContractError("Q3 shortens the return platform below its stated comparison budget")
    def fixture_sizes(items):
        return {i["id"]: sorted(i["rect_mm"][2:]) for i in items}
    if fixture_sizes(cfg["front_furniture"]) != fixture_sizes(parent["config"]["front_furniture"]):
        raise ContractError("Do not shrink or delete retained KTV furniture")
    arrival = arrival_screen(cfg, stairs, sources["floor-1"])
    primary = primary_geometry(cfg, parent, upper, stairs)
    if primary["KTV_area_after_wrap_and_cabinet_sqm"] < 20:
        raise ContractError("Q3 primary budget no longer supports its stated20sqm area comparison")
    cases = capacity_cases(cfg, parent, source)
    original_five = copy.deepcopy(parent["original_3f_requirement_ledger"])
    for row in original_five:
        if row["id"].endswith(".ktv"):
            row["modeled_value_sqm"] = primary["KTV_area_after_wrap_and_cabinet_sqm"]
            row["target_met_in_area_model_only"] = row["modeled_value_sqm"] >= row["target_sqm"]
        row["functional_or_legal_requirement_verified"] = False
    report = {"schema": "house-b-ktv-stair-options-report-v1", "date": cfg["date"], "config": cfg,
        "parent_report_hash": parent["report_hash"], "primary": primary, "capacity_cases": cases,
        "upper_stairs": stairs, "original_stairs_by_floor": sources, "floor2_arrival_screen": arrival,
        "protected_polygons_mm": upper["protected_polygons_mm"], "palanquin_rect_mm": upper["palanquin_rect_mm"],
        "original_3F_requirement_ledger": original_five, "original_frozen_ground_and_roof_controls": parent["ground_and_roof_controls"],
        "retained_guest_bath_sliders": copy.deepcopy(parent["config"]["sliders"]),
        "retained_quiet_rear_opening": copy.deepcopy(parent["front_option"]["quiet_to_rear_connection"]),
        "floor1_stair_and_owner_functions_changed": False, "second_floor_room_boundaries_and_wet_areas_changed": False,
        "second_and_third_outgoing_stair_geometry_changes_required": True,
        "RF_arrival_platform_shift_mm": cfg["primary_extension_depth_mm"], "RF_R_S_D_routes_inherited_as_verified": False,
        "upstream_P3_front_drainage_resolved": False, "RF24_goal_or_C_care_or_A_space_changed": False,
        "protected_controls_unchanged": len(controls), "adopted": False, "primary_abc_or_3d_changed": False,
        "actual_site_or_product_data_received": 0, "all_original_requirements_met": False,
        "rendered_qa": "not-run", "professional_approval": "unknown",
        "conclusion": "Q3釋出上層折返平台前段，L形KTV在115＋100mm／面、原井外包50mm及0.54㎡機櫃後，面積算術可過20；代價是2F／3F樓梯與RF到達必須重設，二樓須保L形接段避免蓋住舊下樓梯。這是有條件的整層比較，不是隔音、梯段或全案已核。Q2原梯與所有需求保留。"}
    names = [CONFIG, *cfg["pinned_sources"], *parent["source_hashes"], cfg["protected_controls"],
        "house_design/b_ktv_stair_options.py", "scripts/export_b_ktv_stair_options.py", "Docs/b-ktv-stair-options-v1.md"]
    report["source_hashes"] = {n: digest(root, n, cache) for n in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

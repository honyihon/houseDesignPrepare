"""Independent B3 entertainment placement and acoustic-space tradeoffs; no scenes."""
from __future__ import annotations

import copy
from itertools import combinations, product
from pathlib import Path

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from house_design.b_front_service_detail import leaves, panel_travel
from house_design.b_upper_replan import analyze_floor, bridge, door, finish, hit, rect, room, sweep
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-third-entertainment.json"
OUT = "structured/coordination/b-third-entertainment-v1"
STATES = {"open": 90, "half": 45, "closed": 0}


def area_after(shape, inset, shafts):
    return finish(shape, inset).difference(unary_union([rect(s) for s in shafts])).area/1e6


def acoustic_cases(rooms, cfg):
    data = []
    for label, room_data in rooms.items():
        shape = Polygon(room_data["polygon_mm"])
        for extra in cfg["additional_acoustic_insets_mm"]:
            interior = finish(shape, cfg["inset_mm"]+extra)
            data.append({"option": label, "extra_each_face_mm": extra, "area_sqm": round(area_after(shape, cfg["inset_mm"]+extra, room_data["shafts_mm"]), 6),
                "goal20_met_in_model": area_after(shape, cfg["inset_mm"]+extra, room_data["shafts_mm"]) >= 20,
                "min14_met_in_model": area_after(shape, cfg["inset_mm"]+extra, room_data["shafts_mm"]) >= 14,
                "unchanged_furniture_parts_outside": [i["id"]+":"+part for i in room_data["items"] for part in ["rect_mm", "operation_mm"]
                    if i.get(part) and not interior.buffer(.01).covers(rect(i[part]))],
                "acoustic_performance": "unknown-not-dB-or-selected-construction"})
    front = Polygon(rooms["front"]["polygon_mm"])
    lo, hi = 0., 1000.
    for _ in range(50):
        mid = (lo+hi)/2
        if area_after(front, cfg["inset_mm"]+mid, rooms["front"]["shafts_mm"]) >= 20:
            lo = mid
        else:
            hi = mid
    return {"cases": data, "front_extra_each_face_limit_for20_in_this_area_model_mm": lo,
        "limit_is_not_a_permitted_product_thickness_or_acoustic_spec": True,
        "internal_shaft_lining_airlock_silencer_and_equipment_not_fully_budgeted": True,
        "floor_ceiling_door_seals_vents_and_low_frequency_performance": "unknown"}


def make_front_option(cfg, upper, service):
    source = service["floors"][1]
    keep = [copy.deepcopy(r) for r in source["rooms"] if r["id"] in {"stair", "quiet-living", "dry-protection"}]
    # The old balcony gate would create an acoustic bypass; Q2 has one new stair-side entry.
    next(r for r in keep if r["id"] == "quiet-living")["doors"] = []
    rear = rect(upper["config"]["floors"]["common"]["rear_rect_mm"])
    dry = Polygon(next(r for r in keep if r["id"] == "dry-protection")["polygon_mm"])
    guest = unary_union([rect(p) for p in cfg["guest_parts_mm"]])
    bath, patio = rect(cfg["rear_bath_mm"]), rect(cfg["working_court_mm"])
    access = rear.difference(unary_union([dry, guest, bath, patio]))
    shaft = upper["config"]["floors"]["common"]["private_shaft_mm"]
    rooms = keep+[
        room("front-entertainment", "前側娛樂／隔音空間候選", rect(cfg["front_room_mm"]), cfg["front_furniture"],
            [service["config"]["shared_shaft_mm"]], [cfg["front_entry"]], [[2050, 0, 1000, 0]], "high-activity"),
        room("guest", "後客房／偏位入口", guest, cfg["guest_furniture"], windows=[[250, 17630, 2400, 0]], kind="bedroom"),
        room("rear-bath", "後側有窗公衛候選／對齊2F套衛", bath, cfg["bath_fixtures"], [shaft], windows=[[4750, 17630, 900, 0]], kind="wet"),
        room("working-court", "需RF開口的工作天井候選", patio, doors=[cfg["court_entry"]], kind="wet"),
        room("rear-access", "公共到達／不重算房間面積", access)]
    for r in rooms:
        if r["id"] == "working-court":
            r["outdoor_status"] = "requires-new-RF-void-not-approved-work-balcony"
    return rooms


def explicit_geometry(rooms, cfg, upper):
    pcfg = upper["config"]
    protected = unary_union([Polygon(p) for p in upper["protected_polygons_mm"]])
    storage = rect(upper["palanquin_rect_mm"])
    floor = analyze_floor(rooms, pcfg, protected, storage, {}, "floor-3", [])
    fixed = [{**i, "room": r["id"]} for r in rooms for i in r["items"]]
    shafts = [{"room": r["id"], "rect_mm": s} for r in rooms for s in r["shafts_mm"]]
    surface = unary_union([finish(Polygon(r["polygon_mm"]), cfg["inset_mm"]+(cfg["primary_extra_inset_mm"] if r["id"] == "front-entertainment" else 0)) for r in rooms]
        +[bridge({"a": d["a"], "b": d["b"]}, cfg["inset_mm"]) for d in cfg["sliders"]]
        +[bridge(cfg["front_entry"], cfg["inset_mm"]+cfg["primary_extra_inset_mm"]), rect([0, 3900, 2400, 1000]),
            bridge(cfg["court_entry"], cfg["inset_mm"]),
            bridge({"a": [4770, 11370], "b": [5900, 11370]}, cfg["inset_mm"])])
    route_shapes = {r["id"]: sweep(r["points_mm"], r["width_mm"]) for r in cfg["routes"]}
    routes = [{**r, "within_model_floor": surface.buffer(.01).covers(route_shapes[r["id"]]),
        "outside_sqm": route_shapes[r["id"]].difference(surface).area/1e6,
        "fixed_hits": [i["id"] for i in fixed if hit(route_shapes[r["id"]], rect(i["rect_mm"]))],
        "shaft_hits": [s["room"] for s in shafts if hit(route_shapes[r["id"]], rect(s["rect_mm"]))],
        "operation_shared": [i["room"]+":"+i["id"] for i in fixed if i.get("operation_mm") and hit(route_shapes[r["id"]], rect(i["operation_mm"]))],
        "actual_person_motion_and_door_clear": "unknown"} for r in cfg["routes"]]
    states = []
    for front, guest, bath, court in product(STATES, repeat=4):
        now = {"front": front, "guest": guest, "bath": bath, "court": court}
        parts = [{"door": "front", "shape": door(cfg["front_entry"], STATES[front])},
            {"door": "court", "shape": door(cfg["court_entry"], STATES[court])}]
        parts += [{"door": d["id"], "shape": rect(p)} for d in cfg["sliders"] for p in leaves(d, now[d["id"]])]
        states.append({"states": now, "route_blockers": {r["id"]: sorted({p["door"] for p in parts if hit(route_shapes[r["id"]], p["shape"])}) for r in cfg["routes"]},
            "body_hits": [{"door": p["door"], "body": i["room"]+":"+i["id"]} for p in parts for i in fixed if hit(p["shape"], rect(i["rect_mm"]))],
            "shaft_hits": [{"door": p["door"], "shaft": s["room"]} for p in parts for s in shafts if hit(p["shape"], rect(s["rect_mm"]))],
            "panel_pair_hits": [{"a": a["door"], "b": b["door"]} for a, b in combinations(parts, 2) if hit(a["shape"], b["shape"])]})
    frame = rect([0, 0, *cfg["frame_mm"]])
    travel = [{"door": d["id"], "rect_mm": p,
        "within_planning_frame": frame.covers(rect(p)),
        "shaft_hits": [s["room"] for s in shafts if hit(rect(p), rect(s["rect_mm"]))],
        "fixed_hits": [i["room"]+":"+i["id"] for i in fixed if hit(rect(p), rect(i["rect_mm"]))]}
        for d in cfg["sliders"] for p in panel_travel(d)]
    front_shape = Polygon(next(r for r in rooms if r["id"] == "front-entertainment")["polygon_mm"])
    front_inside = finish(front_shape, cfg["inset_mm"]+cfg["primary_extra_inset_mm"])
    front_items = next(r["items"] for r in rooms if r["id"] == "front-entertainment")
    floor.update(explicit_routes=routes, independent_door_states=states, slider_full_translation=travel,
        quiet_to_rear_connection={"a": [4770, 11370], "b": [5900, 11370], "operation": "no-leaf-open-passage-candidate-fire-and-structure-pending"},
        explicit_door_shapes={state: [{"door": "front", "polygon_mm": list(door(cfg["front_entry"], STATES[state]).exterior.coords)},
            {"door": "court", "polygon_mm": list(door(cfg["court_entry"], STATES[state]).exterior.coords)}]
            +[{"door": d["id"], "polygon_mm": list(rect(p).exterior.coords)} for d in cfg["sliders"] for p in leaves(d, state)] for state in STATES},
        rear_door_openings_on_room_boundary={d["id"]: Polygon(next(r["polygon_mm"] for r in rooms if r["id"] == ("guest" if d["id"] == "guest" else "rear-bath"))).boundary
            .buffer(.01).covers(LineString([d["a"], d["b"]])) for d in cfg["sliders"]},
        primary_acoustic_inset_mm=cfg["inset_mm"]+cfg["primary_extra_inset_mm"],
        working_court_public_access_without_guest=True,
        front_entry_clear_width_in_primary_frame_budget_mm=cfg["front_entry"]["b"][0]-cfg["front_entry"]["a"][0]-2*(cfg["inset_mm"]+cfg["primary_extra_inset_mm"]),
        front_furniture_parts_outside_primary=[i["id"]+":"+part for i in front_items for part in ["rect_mm", "operation_mm"] if i.get(part) and not front_inside.buffer(.01).covers(rect(i[part]))],
        stair_upstream_platform_and_original_side_door="unknown-not-revalidated", ordinary_route_width_mm=700)
    return floor


def roof_overlay(cfg, ground, upper):
    source = ground["stack_and_entry"]["options"][0]["roof_reference"]
    frame = rect([0, 0, *cfg["frame_mm"]])
    void = rect(cfg["working_court_mm"])
    guard = void.buffer(cfg["rf_guard_budget_mm"], join_style=2).intersection(frame)
    existing = [{"id": u["id"], "rect_mm": [u["x_mm"]-u["width_mm"]/2, u["y_mm"]-u["depth_mm"]/2, u["width_mm"], u["depth_mm"]]} for r in source["rooms"] for u in r["features"].get("hvac_units", []) if u["type"] == "outdoor"]
    protected = unary_union([Polygon(p) for p in upper["protected_polygons_mm"]])
    slots = [{"id": "representative-slot-"+str(n), "rect_mm": r, "service_mm": s,
        "actual_unit_identity": None, "new_unit_purchase_count": None} for n, (r, s) in enumerate(zip(cfg["rf_candidate_slots_mm"], cfg["rf_service_mm"], strict=True), 1)]
    specs = [
        {"id": "front-slots", "points_mm": [[2850, 4400], [5350, 4400], [5350, 1100], [3720, 1100]]},
        {"id": "rear-right-unit", "points_mm": [[2850, 4400], [5350, 4400], [5350, 14000], [1870, 14000], [1870, 16800]]},
        {"id": "rear-left-unit", "points_mm": [[2850, 4400], [5350, 4400], [5350, 14000], [530, 14000], [530, 16800]]}]
    routes = [{**r, "width_mm": 700, "within_roof_frame": frame.covers(sweep(r["points_mm"], 700)),
        "void_or_guard_hit": hit(sweep(r["points_mm"], 700), guard),
        "unit_hits": [u["id"] for u in existing+slots if hit(sweep(r["points_mm"], 700), rect(u["rect_mm"]))],
        "scope": "starts-outside-RF-side-door-not-stair-or-whole-machine-transport-proof"} for r in specs]
    return {"original_roof_reference_hash": stable_hash(source), "existing_units": existing, "candidate_slots": slots,
        "original_roof_reference_changed": False, "proposed_roof_overlay_requires_change": True,
        "void_mm": cfg["working_court_mm"], "void_sqm": void.area/1e6,
        "guard_budget_mm": cfg["rf_guard_budget_mm"], "guard_budget_is_not_selected_handrail": True,
        "void_over_existing_service_zone_sqm": void.intersection(rect(next(r["rect_mm"] for r in source["rooms"] if r["id"].endswith(":service-rf")))).area/1e6,
        "straight_old_rear_access_interrupted": True, "alternative_routes": routes,
        "slots_protected_projection_sqm": sum(rect(s["rect_mm"]).intersection(protected).area/1e6 for s in slots),
        "slots_body_pair_hits": [True for a, b in combinations(slots+existing, 2) if hit(rect(a["rect_mm"]), rect(b["rect_mm"]))],
        "void_unit_hits": [u["id"] for u in existing+slots if hit(void, rect(u["rect_mm"]))],
        "requires_roof_replan_structural_opening_legal_outdoor_and_drainage": True,
        "all_existing_or_future_roof_equipment_fitted": False, "roof_finalized_or_changed_in_primary": False,
        "refrigerant_condensate_structure_wind_and_acoustic_isolation": "unknown"}


def validate(floor, roof):
    bad = ["body_hits", "operation_body_hits", "not_inside_115", "shaft_body_hits", "shaft_operation_hits", "fully_open_door_body_hits", "sampled_swing_body_hits"]
    if (any(floor["fixtures"][k] for k in bad) or floor["partition"]["overlaps"] or floor["partition"]["outside_frame_sqm"] > .000001
            or floor["partition"]["unallocated_sqm"] > .000001 or any(v["prohibited_overlap"] for v in floor["religious_projection"])
            or any(not w["on_room_boundary"] for w in floor["windows"]) or floor["front_furniture_parts_outside_primary"]
            or any(not r["within_model_floor"] or r["fixed_hits"] or r["shaft_hits"] for r in floor["explicit_routes"])
            or any(t["fixed_hits"] or t["shaft_hits"] or not t["within_planning_frame"] for t in floor["slider_full_translation"])
            or not all(floor["rear_door_openings_on_room_boundary"].values())):
        raise ContractError("Known B3 planar defect: "+str({k: floor["fixtures"][k] for k in bad if floor["fixtures"][k]})+str(floor["explicit_routes"]))
    for s in floor["independent_door_states"]:
        if s["body_hits"] or s["shaft_hits"] or s["panel_pair_hits"]:
            raise ContractError("B3 door-state collision: "+str(s))
        for r in floor["explicit_routes"]:
            expected = [r["expected_door"]] if r["expected_door"] and s["states"][r["expected_door"]] != "open" else []
            if s["route_blockers"][r["id"]] != expected:
                raise ContractError("B3 independent door blockers disagree: "+r["id"]+str(s))
    if (roof["slots_protected_projection_sqm"] or roof["slots_body_pair_hits"] or roof["void_unit_hits"]
            or any(not r["within_roof_frame"] or r["void_or_guard_hit"] or r["unit_hits"] for r in roof["alternative_routes"])):
        raise ContractError("B3 RF coordination geometry defect")


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    if cfg.get("schema") != "house-b-third-entertainment-v1" or cfg.get("adopted") is not False or cfg["frame_mm"] != [6000, 17630] or cfg["inset_mm"] != 115:
        raise ContractError("Preserve independent B3 comparison within the same planning frame")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen B3 source changed: "+name)
    controls = read_json(root/cfg["protected_controls"])["hashes"]
    cache = {}
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    upper, service, ground = [read_json(root/cfg[k]) for k in ["upper_report", "service_report", "ground_report"]]
    original_ground = {o["id"]: o for o in ground["stack_and_entry"]["options"]}
    if set(original_ground) != {o["id"] for o in service["unchanged_ground_and_roof_hashes"]}:
        raise ContractError("Preserve the two independent ground entry references")
    for ref in service["unchanged_ground_and_roof_hashes"]:
        current = original_ground[ref["id"]]
        if stable_hash(current["states"]) != ref["source_states_hash"] or stable_hash(current["roof_reference"]) != ref["roof_reference_hash"]:
            raise ContractError("B3 ground or RF reference no longer matches the frozen P3 control")
    common = upper["config"]["floors"]["common"]
    for key, original in [("front_furniture", common["third_ktv_furniture"]),
            ("guest_furniture", [i for i in common["third_guest_furniture"] if i["id"] != "screen"]),
            ("bath_fixtures", service["config"]["public_fixtures"])]:
        if {i["id"]: sorted(i["rect_mm"][2:]) for i in cfg[key]} != {i["id"]: sorted(i["rect_mm"][2:]) for i in original}:
            raise ContractError("Do not shrink or delete original B3 furniture or fixtures")
    for d in cfg["sliders"]:
        if (d["b"][0]-d["a"][0] != 1130 or d["a"][1] != d["b"][1]
                or d["leaf_width_mm"] != 660 or d["leaf_thickness_mm"] != 45
                or d["track_y_mm"][1]-d["track_y_mm"][0] != 85
                or any(abs(y-d["a"][1]) > 230 for y in d["track_y_mm"])):
            raise ContractError("Keep B3 slider leaves linked to their actual nominal opening")
    source = service["floors"][1]
    current = next(r for r in source["rooms"] if r["id"] == "ktv-study")
    rooms = make_front_option(cfg, upper, service)
    floor = explicit_geometry(rooms, cfg, upper)
    roof = roof_overlay(cfg, ground, upper)
    validate(floor, roof)
    front = next(r for r in rooms if r["id"] == "front-entertainment")
    acoustics = acoustic_cases({"rear": current, "front": front}, cfg)
    rear = rect(upper["config"]["floors"]["common"]["rear_rect_mm"])
    dry = Polygon(next(r for r in rooms if r["id"] == "dry-protection")["polygon_mm"])
    rear_shaft = upper["config"]["floors"]["common"]["private_shaft_mm"]
    relaxed = finish(rear, 115).difference(dry.buffer(115, join_style=2)).difference(rect(rear_shaft)).area/1e6
    reqs = read_json(root/"inputs/requirements.json")["requirements"]
    originals = [r for r in reqs if r["id"].startswith("B.floor-3.")]
    areas = {a["id"]: a["net115_sqm"] for a in floor["areas"]}
    values = {"B.floor-3.flex_b": areas["quiet-living"], "B.floor-3.ktv": next(c["area_sqm"] for c in acoustics["cases"] if c["option"] == "front" and c["extra_each_face_mm"] == cfg["primary_extra_inset_mm"]),
        "B.floor-3.bath_b3": areas["rear-bath"], "B.floor-3.guest_b": areas["guest"], "B.floor-3.balcony_b3": areas["working-court"]}
    ledger = [{"id": r["id"], "original_status": r["status"], "target_sqm": r["constraints"]["target_sqm"],
        "min_sqm": r["constraints"]["min_sqm"], "modeled_value_sqm": values[r["id"]],
        "target_met_in_area_model_only": values[r["id"]] >= r["constraints"]["target_sqm"],
        "functional_or_legal_requirement_verified": False,
        "legacy_band_or_service_core_changed": r["id"] in {"B.floor-3.bath_b3", "B.floor-3.balcony_b3"}} for r in originals]
    second = {r["id"]: Polygon(r["polygon_mm"]) for r in service["floors"][0]["rooms"]}
    bed = rect(upper["config"]["floors"]["common"]["master_furniture"][0]["rect_mm"])
    projections = [{"room": r["id"], "over_2F_master_sqm": Polygon(r["polygon_mm"]).intersection(second["master"]).area/1e6,
        "over_2F_bed_body_sqm": Polygon(r["polygon_mm"]).intersection(bed).area/1e6} for r in rooms if r["id"] in {"front-entertainment", "rear-bath", "working-court"}]
    if any(r["over_2F_bed_body_sqm"] for r in projections):
        raise ContractError("B3 activity or wet footprint projects over the retained 2F bed")
    if not second["private-bath"].equals(Polygon(next(r["polygon_mm"] for r in rooms if r["id"] == "rear-bath"))):
        raise ContractError("Keep the new 3F public bath aligned with the retained 2F ensuite")
    report = {"schema": "house-b-third-entertainment-report-v1", "date": cfg["date"], "config": cfg,
        "rear_control": source, "rear_service_sliders": service["config"]["sliders"],
        "front_option": floor, "acoustic_space": acoustics, "rf_overlay": roof, "original_3f_requirement_ledger": ledger,
        "fixed_rear_optimistic_bound": {"inset_mm": 115, "includes_original_dry_protection_and_rear_shaft": True,
            "ignores_new_guest_KTV_partition_corridor_and_acoustic_layers": True, "usable_upper_bound_sqm": round(relaxed, 6),
            "guest12_plus_KTV20_sqm": 32, "short_of_two_targets_sqm": round(32-relaxed, 6),
            "scope": "only-fixed-rear-and-this-wall-budget-not-a-global-impossibility-proof"},
        "vertical_projections": projections,
        "old_rear_entertainment_over_2F_master_sqm": upper["options"][1]["upper_stack"]["third_entertainment_over_second_master_sqm"],
        "new_front_enclosed_nominal_sqm": rect(cfg["front_room_mm"]).area/1e6,
        "additional_enclosed_nominal_over_P3_sqm": round(rect(cfg["front_room_mm"]).area/1e6-upper["options"][1]["frontage"]["enclosure_nominal_add_sqm_per_upper_floor"], 6),
        "second_floor_reference_hash": stable_hash(service["floors"][0]),
        "ground_and_roof_controls": service["unchanged_ground_and_roof_hashes"], "protected_controls_unchanged": len(controls),
        "front_2F_pipe_shaft_retained_mm": service["config"]["shared_shaft_mm"], "P3_front_gravity_drainage_resolved": False,
        "preferred_acoustic_placement_for_research": "front-entertainment", "complete_scheme_ready_or_adopted": False,
        "all_original_requirements_met": False, "adopted": False, "professional_approval": "unknown", "rendered_qa": "not-run",
        "primary_abc_or_3d_changed": False, "actual_site_or_product_data_received": 0,
        "conclusion": "前置娛樂較能避樓下主臥及後客房，但需要更大的正式前室內量體、RF機位／天井及聲學新風合圖。100mm額外內縮仍未達20㎡，只保留優先研究方向；原後段與所有需求不取消。"}
    names = [CONFIG, cfg["protected_controls"], *cfg["pinned_sources"], cfg["ground_report"], "inputs/requirements.json", "inputs/brief/B.json", "inputs/planning-register.json",
        "house_design/b_third_entertainment.py", "scripts/export_b_third_entertainment.py", "house_design/b_upper_replan.py", "house_design/b_front_service_detail.py",
        "house_design/contracts.py", "house_design/project_status.py", "scripts/export_b_upper_replan.py", "scripts/export_abc_next_improvements.py",
        "scripts/export_builder_communication.py", "Docs/b-third-entertainment-v1.md"]
    report["source_hashes"] = {name: digest(root, name, cache) for name in names}
    report["report_hash"] = stable_hash(report)
    return report

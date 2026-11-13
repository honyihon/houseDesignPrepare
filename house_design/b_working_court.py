"""Compare a retained RF service strip with an open court and a dry-room fallback."""
from __future__ import annotations

import copy
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

from house_design.b_upper_replan import finish, hit, rect, ring, sweep
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-working-court.json"
OUT = "structured/coordination/b-working-court-v1"


def roof_routes(specs, frame, stair, opening, guard, units, edge):
    surface = finish(frame, edge).difference(unary_union([stair, opening, guard]))
    results = []
    for spec in specs:
        route = sweep(spec["points_mm"], spec["width_mm"])
        results.append({**spec, "within_reserved_roof_surface": surface.buffer(.01).covers(route),
            "outside_sqm": round(route.difference(surface).area/1e6, 8),
            "void_or_guard_hit": hit(route, unary_union([opening, guard])),
            "unit_hits": [u["id"] for u in units if hit(route, rect(u["rect_mm"]))],
            "scope": "outside-RF-side-door-to-listed-units-only-not-stairs-or-machine-transport"})
    return results


def option(cfg, parent, upper, service, key, title, opening_mm, strip_mm):
    court = rect(cfg["court_mm"])
    frame = rect([0, 0, *cfg["frame_mm"]])
    opening = rect(opening_mm) if opening_mm else Polygon()
    guard = opening.buffer(cfg["rf_guard_budget_mm"], join_style=2).intersection(frame).difference(opening)
    guard_parts = []
    if opening_mm:
        a, b, w, h = opening_mm
        g = cfg["rf_guard_budget_mm"]
        guard_parts = [rect(r).intersection(frame) for r in [[a-g, b-g, w+2*g, g], [a-g, b+h, w+2*g, g],
            [a-g, b, g, h], [a+w, b, g, h]] if rect(r).intersection(frame).area > 0]
    stair = Polygon(next(r["polygon_mm"] for r in parent["front_option"]["rooms"] if r["id"] == "stair"))
    units = parent["rf_overlay"]["existing_units"]+parent["rf_overlay"]["candidate_slots"]
    protected = unary_union([Polygon(p) for p in upper["protected_polygons_mm"]])
    second = {r["id"]: Polygon(r["polygon_mm"]) for r in service["floors"][0]["rooms"]}
    bed = rect(upper["config"]["floors"]["common"]["master_furniture"][0]["rect_mm"])
    storage = rect(upper["palanquin_rect_mm"])
    wet = court if key != "R2-dry-room" else Polygon()
    specs = [{"id": "front-slots", "width_mm": cfg["route_width_mm"],
        "points_mm": parent["rf_overlay"]["alternative_routes"][0]["points_mm"]}]
    specs += ([{"id": r["id"], "points_mm": r["points_mm"], "width_mm": cfg["route_width_mm"]}
        for r in parent["rf_overlay"]["alternative_routes"][1:]] if key == "R0-open-court" else [
        {"id": "rear-left-unit", "width_mm": cfg["route_width_mm"], "points_mm": cfg["direct_left_route_mm"]},
        {"id": "rear-right-unit", "width_mm": cfg["route_width_mm"], "points_mm": cfg["direct_right_route_mm"]}])
    straight = sweep([[550, 10700], [550, 16800]], cfg["route_width_mm"])
    areas = {a["id"]: a["net115_sqm"] for a in parent["front_option"]["areas"]}
    free_service = rect([0, 11370, 2400, 6260]).difference(unary_union([opening, guard]))
    return {"id": key, "title": title, "court_floor_mm": cfg["court_mm"],
        "court_floor_nominal_sqm": court.area/1e6, "floor_outline115_sqm": areas["working-court"],
        "rf_opening_mm": opening_mm, "rf_opening_sqm": round(opening.area/1e6, 6),
        "rf_opening_reduction_sqm": round(court.area/1e6-opening.area/1e6, 6),
        "rf_opening_reduction_fraction": round(1-opening.area/court.area, 6),
        "rf_retained_strip_mm": strip_mm, "rf_guard_polygons_mm": [ring(p) for p in guard_parts],
        "rf_front_collar_mm": [cfg["court_mm"][0]+strip_mm[2], cfg["court_mm"][1], cfg["court_mm"][2]-strip_mm[2], cfg["rf_front_collar_budget_mm"]] if strip_mm else None,
        "rf_left_strip_clear_budget_mm": (strip_mm[2]-cfg["rf_left_edge_budget_mm"]-cfg["rf_guard_budget_mm"]) if strip_mm else (None if opening_mm else 2400-cfg["rf_left_edge_budget_mm"]),
        "rf_unobstructed_service_zone_before_equipment_and_walkways_sqm": round(free_service.area/1e6, 6),
        "old_left_corridor_interrupted_by_void_or_guard": hit(straight, unary_union([opening, guard])),
        "rf_routes": roof_routes(specs, frame, stair, opening, guard, units, cfg["rf_left_edge_budget_mm"]),
        "wet_3F_over_2F_master_sqm": round(wet.intersection(second["master"]).area/1e6, 6),
        "wet_3F_over_2F_bed_sqm": round(wet.intersection(bed).area/1e6, 6),
        "wet_3F_over_shrine_or_backing_sqm": round(wet.intersection(protected).area/1e6, 6),
        "wet_3F_over_palanquin_sqm": round(wet.intersection(storage).area/1e6, 6),
        "rf_void_or_guard_over_protected_sqm": round(unary_union([opening, guard]).intersection(protected).area/1e6, 6),
        "rf_void_over_protected_sqm": round(opening.intersection(protected).area/1e6, 6),
        "guard_protected_interface_requires_review": hit(guard, protected),
        "guard_family_or_structural_permission": "unknown-not-inferred-from-original-checks",
        "direct_sky_opening_is_not_rainfall_or_effective_ventilation_area": True,
        "working_court_outdoor_outline115_candidate_sqm": areas["working-court"] if key != "R2-dry-room" else 0,
        "indoor_dry_utility_outline115_sqm": areas["working-court"] if key == "R2-dry-room" else 0,
        "wet_equipment_in_dry_fallback": [], "dry_fallback_effective_daylight_and_fresh_air": "unknown-no-new-side-window",
        "floor3_other_rooms_and_all_furniture_doors_routes_unchanged": True,
        "inherited_floor3_door_state_count": len(parent["front_option"]["independent_door_states"]),
        "inherited_door_results_scope": "identical-floor-geometry-only-no-new-supports-thresholds-or-product-proof",
        "new_3F_supports_drawn": [], "supports_proven_unnecessary": False,
        "outdoor_work_balcony_legal_or_environmental_approval": "unknown" if key != "R2-dry-room" else "original-3F-outdoor-goal-not-met",
        "all_roof_equipment_fitted": False, "adopted": False}


def bounds(cfg, parent, service):
    second_bath = next(r for r in service["floors"][0]["rooms"] if r["id"] == "private-bath")
    stack = finish(Polygon(second_bath["polygon_mm"]), cfg["inset_mm"]).difference(unary_union([rect(p) for p in second_bath["shafts_mm"]]))
    guest = Polygon(next(r["polygon_mm"] for r in parent["front_option"]["rooms"] if r["id"] == "guest"))
    slim = rect(cfg["slender_court_probe_mm"])
    base = next(c["area_sqm"] for c in parent["acoustic_space"]["cases"] if c["option"] == "front" and c["extra_each_face_mm"] == 0)
    main = next(c["area_sqm"] for c in parent["acoustic_space"]["cases"] if c["option"] == "front" and c["extra_each_face_mm"] == 100)
    return {"scope": "fixed-2F-stair-sacred-protection-and-Q2-geometry-not-global-impossibility",
        "rear_stack_only": {"optimistic_available115_after_shaft_sqm": round(stack.area/1e6, 6),
            "bath5_plus_outdoor4_target_sqm": 9, "short_before_new_partition_sqm": round(9-stack.area/1e6, 6)},
        "front_shared_with_outdoor": {"optimistic_front115_after_shaft_sqm": base, "KTV20_plus_outdoor4_target_sqm": 24,
            "short_before_new_partition_or_acoustics_sqm": round(24-base, 6), "short_with_primary_extra100_sqm": round(24-main, 6)},
        "slender_court_without_replanning_guest": {"rect_mm": cfg["slender_court_probe_mm"],
            "outline115_sqm": round(finish(slim, cfg["inset_mm"]).area/1e6, 6),
            "overlap_with_retained_guest_nominal_sqm": round(slim.intersection(guest).area/1e6, 6),
            "guest_remaining_after_recuts_and115_sqm": round(finish(guest.difference(slim), cfg["inset_mm"]).area/1e6, 6),
            "guest_item_hits": [i["id"] for r in parent["front_option"]["rooms"] if r["id"] == "guest" for i in r["items"] if hit(slim, rect(i["rect_mm"]))],
            "rejected_as_simple_swap": True}}


def build(root):
    root, cache = Path(root), {}
    cfg = read_json(root/CONFIG)
    if (cfg.get("schema") != "house-b-working-court-v1" or cfg.get("adopted") is not False
            or cfg["frame_mm"] != [6000, 17630] or cfg["inset_mm"] != 115
            or cfg["rf_retained_strip_width_mm"] <= 0 or cfg["route_width_mm"] != 700):
        raise ContractError("Preserve independent court study, planning frame and listed geometry budget")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen court parent changed: "+name)
    parent = read_json(root/cfg["parent_report"])
    if stable_hash({k: v for k, v in parent.items() if k != "report_hash"}) != parent["report_hash"]:
        raise ContractError("Frozen parent report content does not match its report hash")
    for name, expected in parent["source_hashes"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("Court parent source drift: "+name)
    controls = read_json(root/cfg["protected_controls"])["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    if cfg["court_mm"] != parent["config"]["working_court_mm"]:
        raise ContractError("Do not move the courtyard while claiming identical floor3 door and furniture results")
    upper, service = [read_json(root/parent["config"][k]) for k in ["upper_report", "service_report"]]
    x, y, w, depth = cfg["court_mm"]
    strip_width = cfg["rf_retained_strip_width_mm"]
    collar = cfg["rf_front_collar_budget_mm"]
    if not 0 < strip_width < w or cfg["rf_left_edge_budget_mm"] < 0 or cfg["rf_guard_budget_mm"] <= 0 or not 0 < collar < depth:
        raise ContractError("RF strip or guard budget is invalid")
    options = [option(cfg, parent, upper, service, "R0-open-court", "R0 原完整開洞／右側繞行", cfg["court_mm"], None),
        option(cfg, parent, upper, service, "R1-retained-strip", "R1 留RF左板帶／部分遮頂天井", [x+strip_width, y+collar, w-strip_width, depth-collar], [x, y, strip_width, depth]),
        option(cfg, parent, upper, service, "R2-dry-room", "R2 不開RF洞／三樓乾式家務備案", None, None)]
    for o in options:
        if (o["wet_3F_over_2F_bed_sqm"] or o["wet_3F_over_shrine_or_backing_sqm"] or o["wet_3F_over_palanquin_sqm"]
                or o["rf_void_over_protected_sqm"] or (o["id"] != "R0-open-court" and o["guard_protected_interface_requires_review"])
                or any(not r["within_reserved_roof_surface"] or r["void_or_guard_hit"] or r["unit_hits"] for r in o["rf_routes"])):
            raise ContractError("Court option has a listed roof-path or protected-projection conflict: "+str({
                "option": o["id"], "projections": {k: v for k, v in o.items() if k.startswith(("wet_3F_over_", "rf_void_or_guard_over_"))}, "routes": o["rf_routes"]}))
    if options[1]["rf_left_strip_clear_budget_mm"] < cfg["route_width_mm"]:
        raise ContractError("Retained RF strip cannot fit the declared route budget")
    width_cases = [{"strip_width_mm": width, "guard_budget_mm": cfg["rf_guard_budget_mm"],
        "clear_budget_mm": width-cfg["rf_left_edge_budget_mm"]-cfg["rf_guard_budget_mm"],
        "fits700_in_width_model": width-cfg["rf_left_edge_budget_mm"]-cfg["rf_guard_budget_mm"] >= cfg["route_width_mm"],
        "sky_opening_sqm": round((w-width)*(depth-collar)/1e6, 6)} for width in cfg["rf_strip_width_cases_mm"]]
    guard_cases = [{"guard_budget_mm": budget, "clear_budget_mm": strip_width-cfg["rf_left_edge_budget_mm"]-budget,
        "fits700_after_recentering_in_width_model": strip_width-cfg["rf_left_edge_budget_mm"]-budget >= cfg["route_width_mm"]} for budget in cfg["rf_guard_cases_mm"]]
    requirements = read_json(root/"inputs/requirements.json")["requirements"]
    rf_ledger = [{"id": r["id"], "title": r["title"], "original_status": r["status"],
        "target_sqm": r["constraints"]["target_sqm"], "min_sqm": r["constraints"]["min_sqm"],
        "complete_effective_area_sqm": None, "fitted_and_approved": False,
        "scope": "original-requirement-retained-legacy-coordinate-text-not-restored"} for r in requirements if r["id"].startswith("B.floor-rf.")]
    program = copy.deepcopy(parent["original_3f_requirement_ledger"])
    for r in program:
        r["values_by_option_sqm"] = {o["id"]: (o["working_court_outdoor_outline115_candidate_sqm"] if r["id"] == "B.floor-3.balcony_b3" else r["modeled_value_sqm"]) for o in options}
    front_services = unary_union([rect(s["service_mm"]) for s in parent["rf_overlay"]["candidate_slots"]])
    front_roof = rect(parent["config"]["front_room_mm"])
    report = {"schema": "house-b-working-court-report-v1", "date": cfg["date"], "config": cfg,
        "parent_report_hash": parent["report_hash"], "options": options, "width_sensitivity": width_cases,
        "guard_sensitivity": guard_cases, "fixed_topology_bounds": bounds(cfg, parent, service),
        "floor3_reference": parent["front_option"], "floor3_reference_hash": stable_hash(parent["front_option"]),
        "second_floor_reference_hash": parent["second_floor_reference_hash"],
        "ground_and_roof_controls": parent["ground_and_roof_controls"], "protected_controls_unchanged": len(controls),
        "existing_units": parent["rf_overlay"]["existing_units"], "representative_slots": parent["rf_overlay"]["candidate_slots"],
        "protected_polygons_mm": upper["protected_polygons_mm"], "rf_original_requirement_ledger": rf_ledger,
        "original_3f_requirement_ledger": program,
        "RF_front_optimistic_area_after_two_slot_services_sqm": round(front_roof.difference(front_services).area/1e6, 6),
        "RF_front_short_of_original_deck24_before_other_equipment_sqm": round(24-front_roof.difference(front_services).area/1e6, 6),
        "RF_equipment_purchasing_count_or_actual_machine_identity_assumed": False,
        "P3_front_gravity_drainage_resolved": False, "KTV_primary_area_sqm": 19.2079,
        "all_original_requirements_met": False, "preferred_interface_for_further_research": "R1-retained-strip",
        "preference_is_not_owner_adoption_or_approval": True, "adopted": False,
        "primary_abc_or_3d_changed": False, "actual_site_or_product_data_received": 0,
        "rendered_qa": "not-run", "professional_approval": "unknown",
        "conclusion": "先深化R1留板帶：減少RF開洞並保三樓客房、公衛和工作天井地面，不借縮房或改家規。天井仍在2F更衣乾區上方，開口變窄的採光／乾衣及結構尚未成立；R0保留，R2只作取消RF洞的完整代價備案，不改原工作陽台目標。"}
    names = [CONFIG, cfg["protected_controls"], *cfg["pinned_sources"], *parent["source_hashes"],
        "house_design/b_working_court.py", "scripts/export_b_working_court.py", "Docs/b-working-court-v1.md"]
    report["source_hashes"] = {name: digest(root, name, cache) for name in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

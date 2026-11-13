"""Frozen-R1 roof reservations and conditional envelope checks; no scene generation."""
from __future__ import annotations

import math
from itertools import combinations
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

from house_design.b_upper_replan import finish, hit, rect, sweep
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-roof-equipment.json"
OUT = "structured/coordination/b-roof-equipment-v1"


def reservations(cfg, spec):
    result = [{"id": "tank", "label": "水塔／泵浦整組預留", "rect_mm": spec["tank_mm"], "kind": "wet-equipment", "actual_product": None},
        {"id": "heat-pump", "label": "熱泵整組預留", "rect_mm": spec["heat_pump_mm"], "kind": "wet-equipment", "actual_product": None},
        {"id": "rear-air-zone", "label": "後浴廁空氣出口區／非污水通氣", "rect_mm": cfg["rear_air_zone_mm"], "kind": "air-zone", "actual_product": None},
        {"id": "front-dirty-zone", "label": "前污氣出口協調區", "rect_mm": cfg["front_dirty_zone_mm"], "kind": "air-zone", "actual_product": None},
        {"id": "rear-soil-vent", "label": "後400污水通氣井投影", "rect_mm": cfg["rear_soil_vent_mm"], "kind": "pipe-zone", "actual_product": None}]
    for unit in cfg["front_slots"]+cfg["relocated_existing_units"]:
        result.append({"id": unit["id"], "label": unit["id"]+"含維修預留", "rect_mm": unit["envelope_mm"],
            "body_mm": unit["rect_mm"], "kind": "cooling", "actual_product": None,
            "new_purchase_count": None if unit in cfg["front_slots"] else "existing-ID-relocation-only"})
    return result


def geometric_checks(items, surface, forbidden):
    return {"outside_surface": [i["id"] for i in items if not surface.buffer(.01).covers(rect(i["rect_mm"]))],
        "pair_overlaps": [{"a": a["id"], "b": b["id"], "sqm": round(rect(a["rect_mm"]).intersection(rect(b["rect_mm"])).area/1e6, 6)}
            for a, b in combinations(items, 2) if hit(rect(a["rect_mm"]), rect(b["rect_mm"]))],
        "forbidden_hits": [i["id"] for i in items if hit(rect(i["rect_mm"]), forbidden)]}


def route_row(key, points, cfg, surface, items):
    shape = sweep(points, cfg["route_width_mm"])
    # Unknown machine bodies stay opaque: only the four pinned cooling body examples allow entry to a service area.
    obstacles = [rect(i.get("body_mm", i["rect_mm"])) for i in items]
    return {"id": key, "points_mm": points, "width_mm": cfg["route_width_mm"],
        "within_roof_surface": surface.buffer(.01).covers(shape),
        "obstacle_hits": [i["id"] for i, obstacle in zip(items, obstacles, strict=True) if hit(shape, obstacle)],
        "shared_cooling_service_floor": [i["id"] for i in items if i.get("body_mm") and hit(shape, rect(i["rect_mm"]))],
        "actual_operating_or_machine_transport_access": "unknown"}


def make_option(cfg, spec, parent, common):
    frame, protected, stair, opening_guard, beds, storage = common
    surface = finish(frame, cfg["edge_budget_mm"]).difference(unary_union([stair, opening_guard]))
    items = reservations(cfg, spec)
    checks = geometric_checks(items, surface, protected)
    wet = unary_union([rect(i["rect_mm"]) for i in items if i["kind"] == "wet-equipment"])
    checks.update(wet_over_palanquin_sqm=round(wet.intersection(storage).area/1e6, 6),
        wet_or_cooling_over_listed_beds_sqm=round(unary_union([wet]+[rect(i["body_mm"]) for i in items if i.get("body_mm")]).intersection(beds).area/1e6, 6))
    route_specs = [("front-cooling", cfg["front_inspection_route_mm"]),
        ("rear-left-air", [[2850, 4400], [5350, 4400], [5350, 10700], [550, 10700], [550, 14000], [665, 14000]]),
        ("rear-cooling-03", [[2850, 4400], [5350, 4400], [5350, 12700], [4165, 12700], [4165, 12735]]),
        ("rear-cooling-04", [[2850, 4400], [5350, 4400], [5350, 12700], [5435, 12700], [5435, 12735]]),
        ("tank-boundary", [[2850, 4400], [5350, 4400], [5350, 12700], [3365, 12700], [3365, 15500]])]
    if spec["heat_pump_mm"][1] < 3900:
        route_specs.append(("heat-pump-boundary", [[2850, 4400], [5350, 4400], [5350, 2500], [1715, 2500], [1715, 1715]]))
    else:
        route_specs.append(("heat-pump-boundary", [[2850, 4400], [5350, 4400], [5350, 12700], [3365, 12700], [3365, 16890]]))
    routes = [route_row(key, points, cfg, surface, items) for key, points in route_specs]
    if any(checks[k] for k in ["outside_surface", "pair_overlaps", "forbidden_hits", "wet_over_palanquin_sqm", "wet_or_cooling_over_listed_beds_sqm"]) or any(not r["within_roof_surface"] or r["obstacle_hits"] for r in routes):
        raise ContractError("Roof reservation/route defect: "+str({"option": spec["id"], "checks": checks, "routes": routes}))
    front = finish(rect([0, 0, 6000, 3900]), cfg["edge_budget_mm"])
    daily = sweep(cfg["daily_front_route_mm"], cfg["route_width_mm"])
    front_walk = unary_union([daily]+[sweep(r["points_mm"], r["width_mm"]) for r in routes])
    fixed_reservations = unary_union([rect(i["rect_mm"]) for i in items]+[rect(cfg["front_door_swing_budget_mm"])])
    reserved = unary_union([fixed_reservations, front_walk])
    shared_open_floor = front.difference(fixed_reservations)
    activity = front.difference(reserved)
    if daily.intersection(protected).area or not surface.covers(daily) or any(hit(daily, rect(i["rect_mm"])) for i in items):
        raise ContractError("Proposed daily front approach conflicts with a reserved envelope")
    cases = []
    for margin in cfg["enlargement_each_edge_cases_mm"]:
        enlarged = [{**i, "rect_mm": [i["rect_mm"][0]-margin, i["rect_mm"][1]-margin, i["rect_mm"][2]+2*margin, i["rect_mm"][3]+2*margin]}
            if i["id"] in {"tank", "heat-pump"} else i for i in items]
        cases.append({"extra_each_edge_mm": margin, **geometric_checks(enlarged, surface, protected),
            "scope": "fixed-placement-sensitivity-not-product-installation-minimum-or-global-impossibility"})
    return {"id": spec["id"], "title": spec["title"], "reservations": items, "checks": checks, "inspection_routes": routes,
        "daily_front_route": {"points_mm": cfg["daily_front_route_mm"], "width_mm": 700, "over_protected_sqm": 0,
            "scope": "starts-outside-proposed-RF-front-door-stair-arrival-not-verified"},
        "front_open_outline_including_shared_walkways_sqm": round(shared_open_floor.area/1e6, 6),
        "front_activity_upper_bound_after_explicit_reservations_sqm": round(activity.area/1e6, 6),
        "activity_area_scope": "two-metrics-shared-open-outline-and-residual-excluding-700-routes-neither-a-complete-effective-platform",
        "front_activity_polygons_mm": [{"outer": [list(t) for t in p.exterior.coords], "holes": [[list(t) for t in h.coords] for h in p.interiors]}
            for p in (list(activity.geoms) if activity.geom_type == "MultiPolygon" else [activity]) if not p.is_empty],
        "activity_goal24_met": shared_open_floor.area >= 24e6,
        "shared_outline_reaches_original_min10_in_area_model": shared_open_floor.area >= 10e6,
        "original_min10_function_or_legal_approval": "unknown-not-owner-acceptance-of-reduced-goal",
        "rear_daily_drying_area_credited_sqm": 0, "original_deck24_goal_reduced_or_adopted": False,
        "tank_to_rear_soil_vent_plan_gap_mm": rect(spec["tank_mm"]).distance(rect(cfg["rear_soil_vent_mm"])),
        "tank_to_heat_pump_envelope_plan_gap_mm": rect(spec["tank_mm"]).distance(rect(spec["heat_pump_mm"])),
        "sensitivity": cases, "actual_products_installed_approved_or_all_systems_connected": False,
        "RF_front_door_and_actual_stair_access": "pending", "adopted": False}


def conditions_template(cfg, items):
    return {"schema": "house-b-roof-equipment-conditions-v1", "config_hash": stable_hash(cfg),
        "meaning": "所需包絡含機身、通風、檢修與接管；不填0代替未知。空間數值相容不等於專業核可。",
        "records": [{"id": i["id"], "required_envelope_mm": None, "reference": None} for i in items]}


def evaluate_conditions(cfg, options, document=None):
    template = conditions_template(cfg, options[0]["reservations"])
    document = template if document is None else document
    if (not isinstance(document, dict) or document.get("schema") != template["schema"] or document.get("config_hash") != template["config_hash"]
            or not isinstance(document.get("records"), list)):
        raise ContractError("RF conditions must cite this exact config revision")
    expected, records = {r["id"] for r in template["records"]}, {}
    for row in document["records"]:
        if not isinstance(row, dict) or row.get("id") not in expected or row["id"] in records:
            raise ContractError("Unknown or duplicate RF condition ID")
        value = row.get("required_envelope_mm")
        if value is not None and (not isinstance(value, list) or len(value) != 2 or any(isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n) or n <= 0 for n in value)
                or not isinstance(row.get("reference"), str) or not row["reference"].strip()):
            raise ContractError("RF required envelope needs two positive finite dimensions and a source reference")
        records[row["id"]] = row
    if set(records) != expected:
        raise ContractError("RF condition record set must remain complete; unknown values stay null")
    result = []
    for option in options:
        for item in option["reservations"]:
            required = records[item["id"]].get("required_envelope_mm")
            available = item["rect_mm"][2:]
            fits = required is not None and all(a >= b for a, b in zip(available, required, strict=True))
            result.append({"option": option["id"], "id": item["id"], "required_envelope_mm": required,
                "reserved_envelope_mm": available, "status": "pending" if required is None else "numeric-fit" if fits else "needs-replan",
                "rotation_or_reposition_automatically_allowed": False, "professional_approval": "unknown"})
    return template, result


def build(root, condition_document=None):
    root, cache = Path(root), {}
    cfg = read_json(root/CONFIG)
    if cfg.get("schema") != "house-b-roof-equipment-v1" or cfg.get("adopted") is not False or cfg["frame_mm"] != [6000, 17630] or cfg["edge_budget_mm"] != 115 or cfg["route_width_mm"] != 700:
        raise ContractError("Preserve the independent RF study and declared planning frame")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen RF source changed: "+name)
    parent = read_json(root/cfg["parent_report"])
    for name, expected in parent["source_hashes"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("RF parent source drift: "+name)
    controls = read_json(root/cfg["protected_controls"])["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    r1 = next(o for o in parent["options"] if o["id"] == "R1-retained-strip")
    floors = parent["floor3_reference"]
    service = read_json(root/cfg["service_report"])
    guest_bed = rect(next(i["rect_mm"] for r in floors["rooms"] if r["id"] == "guest" for i in r["items"] if i["id"] == "bed"))
    # The pinned second floor already contains the exact retained bed and bath.
    second = service["floors"][0]
    master = next(r for r in second["rooms"] if r["id"] == "master")
    bed2 = rect(next(i["rect_mm"] for i in master["items"] if i["id"] == "bed"))
    beds = unary_union([guest_bed, bed2])
    stair = Polygon(next(r["polygon_mm"] for r in floors["rooms"] if r["id"] == "stair"))
    protected = unary_union([Polygon(p) for p in parent["protected_polygons_mm"]])
    opening_guard = unary_union([rect(r1["rf_opening_mm"])]+[Polygon(p) for p in r1["rf_guard_polygons_mm"]])
    b3parent = read_json(root/parent["config"]["parent_report"])
    upper = read_json(root/b3parent["config"]["upper_report"])
    common = (rect([0, 0, *cfg["frame_mm"]]), protected, stair, opening_guard, beds, rect(upper["palanquin_rect_mm"]))
    old_units = {i["id"]: i["rect_mm"][2:] for i in parent["existing_units"]}
    if {i["id"]: i["rect_mm"][2:] for i in cfg["relocated_existing_units"]} != old_units:
        raise ContractError("Do not delete, duplicate or shrink the existing RF cooling examples")
    if len(cfg["front_slots"]) != len(parent["representative_slots"]) or {i["id"]: i["rect_mm"][2:] for i in cfg["front_slots"]} != {i["id"]: i["rect_mm"][2:] for i in parent["representative_slots"]}:
        raise ContractError("Retain two unidentified representative slots without shrinking them")
    options = [make_option(cfg, spec, parent, common) for spec in cfg["options"]]
    requirements = parent["rf_original_requirement_ledger"]
    targets = {r["id"].rsplit(".", 1)[-1]: r["target_sqm"] for r in requirements}
    if any(rect(spec[k]).area/1e6 < targets[t] for spec in cfg["options"] for k, t in [("tank_mm", "rf_tank"), ("heat_pump_mm", "rf_hp")]):
        raise ContractError("Do not shrink water or heat-pump reservations below the retained targets")
    air_cfg = read_json(root/"inputs/abc-fresh-air-layout-options.json")
    rotated = rect(cfg["indoor_ERV_rotated_candidate_mm"])
    indoor = []
    for unit, floor, host in [("B2-N", second, "master"), ("B3-R", floors, "rear-access")]:
        old = next(i for i in air_cfg["units"] if i["id"] == unit)
        bath = Polygon(next(r["polygon_mm"] for r in floor["rooms"] if r["id"] in {"private-bath", "rear-bath"}))
        dry = Polygon(next(r["polygon_mm"] for r in floor["rooms"] if r["id"] == host))
        if sorted(old["rect_mm"][2:]) != sorted(cfg["indoor_ERV_rotated_candidate_mm"][2:]) or not finish(dry, 115).buffer(.01).covers(rotated) or hit(rotated, protected) or hit(rotated, beds):
            raise ContractError("Rotated indoor ERV reservation fails the unchanged envelope/dry-zone check")
        indoor.append({"id": unit, "old_rect_mm": old["rect_mm"], "old_overlap_current_bath_sqm": round(rect(old["rect_mm"]).intersection(bath).area/1e6, 6),
            "rotated_candidate_mm": cfg["indoor_ERV_rotated_candidate_mm"], "candidate_bath_or_protected_overlap_sqm": round(rotated.intersection(unary_union([bath, protected])).area/1e6, 6),
            "height_budget_mm": 450, "actual_finished_z_mm": None, "filter_removal_and_maintenance_floor_access": "pending-route-occupation-and-safe-access-review",
            "full_current_KTV_and_sleeping_room_air_distribution": "pending-new-room-and-acoustic-branches-not-inherited", "purchase_count_selected": False})
    template, received = evaluate_conditions(cfg, options, condition_document)
    report = {"schema": "house-b-roof-equipment-report-v1", "date": cfg["date"], "config": cfg, "parent_report_hash": parent["report_hash"],
        "R1_reference": r1, "protected_polygons_mm": parent["protected_polygons_mm"], "stair_mm": [0, 3900, 2400, 5200],
        "guest_bed_mm": next(i["rect_mm"] for r in floors["rooms"] if r["id"] == "guest" for i in r["items"] if i["id"] == "bed"),
        "old_RF_units": parent["existing_units"], "old_RF_units_over_new_guest_bed_sqm": round(sum(rect(i["rect_mm"]).intersection(guest_bed).area/1e6 for i in parent["existing_units"]), 6),
        "options": options, "indoor_fresh_air_interfaces": indoor, "original_RF_requirements": requirements,
        "front_nominal_gross_upper_bound_sqm": 23.4, "front_gross_short_of_deck24_before_any_deductions_sqm": .6,
        "daily_rear_platform_credited_or_sacred_rules_relaxed": False, "actual_RF_stair_arrival_or_front_door_verified": False,
        "original_3F_work_court_credited_in_RF_platform": False,
        "condition_template": template, "condition_evaluations": received, "condition_values_received": sum(r.get("required_envelope_mm") is not None for r in (condition_document or template)["records"]),
        "condition_document_hash": stable_hash(condition_document) if condition_document else None,
        "protected_controls_unchanged": len(controls), "adopted": False, "primary_abc_or_3d_changed": False,
        "all_original_requirements_met": False, "rendered_qa": "not-run", "professional_approval": "unknown",
        "conclusion": "先請建商比較S1前熱泵的維修／振動代價，S2留作較大前平台的備案；兩者都保原24㎡目標缺口，不硬塞後保護區。後冷氣移開新版客床，新風仍留室內分區但舊座標須調整。實際設備、RF前門及完整支管未核，不選定機型或併原3D。"}
    names = [CONFIG, *cfg["pinned_sources"], *parent["source_hashes"], cfg["protected_controls"],
        "house_design/b_roof_equipment.py", "scripts/export_b_roof_equipment.py", "Docs/b-roof-equipment-v1.md"]
    report["source_hashes"] = {n: digest(root, n, cache) for n in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

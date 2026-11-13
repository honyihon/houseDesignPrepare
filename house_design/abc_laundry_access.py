"""Source-bound laundry access counterexample and conditional rear gate, not a care route approval."""
from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box, mapping
from shapely.ops import unary_union

from house_design.abc_ground_laundry import overlap, rect
from house_design.contracts import ContractError, stable_hash
from house_design.project_status import digest, read_public_json

CONFIG = "inputs/abc-laundry-access.json"
OUT = "structured/coordination/abc-laundry-access-v1"
DOC = "Docs/abc-laundry-access-v1.md"
PARENT = "structured/coordination/abc-ground-laundry-v1/review.json"
PARENT_SHA = "70d173aee810bf6965a7612b4146c22b5c665a66844b26593381f4248d9dc26a"
PARENT_HASH = "4d78d285e0efe2623261cb86418c5a0c1b3585fea693ebdc816f8a79d4cec45e"


def validate_config(cfg, owner):
    confirmed = owner.get("confirmed", {})
    if (cfg.get("schema") != "house-abc-laundry-access-v1" or cfg.get("adopted") is not False
            or cfg.get("parent_report") != PARENT or cfg.get("parent_sha256") != PARENT_SHA
            or cfg.get("parent_report_hash") != PARENT_HASH
            or cfg.get("finish_assumption_mm") != 115 or cfg.get("total_frame_budget_mm") != 230
            or cfg.get("route_width_mm") != 900
            or confirmed.get("shared_group_at_ground_floor") != 1
            or confirmed.get("C_floor2_initial_washer_use") != "temporarily-inactive-reserve-space"
            or confirmed.get("A_upper_floor_washer_space_required") is not True):
        raise ContractError("Laundry access must preserve the frozen parent, owner direction and explicit assumptions")
    states = cfg["rear_gate"]["states"]
    if states != [{"id": "open", "label": "全開", "fraction": 1},
            {"id": "half", "label": "半開", "fraction": .5}, {"id": "closed", "label": "關閉", "fraction": 0}]:
        raise ContractError("Laundry access needs independent full, half and closed controls")
    actual = cfg.get("actual_conditions")
    if not isinstance(actual, dict) or not actual or any(v is not None for v in actual.values()):
        raise ContractError("Public laundry access conditions remain unknown until actual evidence arrives")


def sealed_parent(root, cfg, cache):
    if digest(root, PARENT, cache) != cfg["parent_sha256"]:
        raise ContractError("Laundry access parent file changed")
    parent = read_public_json(root, PARENT)
    if (parent.get("schema") != "house-abc-ground-laundry-report-v1"
            or parent.get("report_hash") != PARENT_HASH
            or stable_hash({k: v for k, v in parent.items() if k != "report_hash"}) != PARENT_HASH
            or len(parent.get("source_hashes", {})) != 15
            or parent.get("adopted") is not False or parent.get("original_ABC_or_3d_changed") is not False):
        raise ContractError("Laundry access parent report seal or scope changed")
    for name, expected in parent["source_hashes"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("Laundry access parent source changed: "+name)
    return parent


def front_screen(cfg, rooms):
    """Reject the diagonal-label shortcut without claiming all front replanning is impossible."""
    hall, kitchen = rect(rooms["rear-hall1"]["rect_mm"]), rect(rooms["kitchen"]["rect_mm"])
    proposed = Polygon(cfg["front_counterexample"]["triangle_mm"])
    if not proposed.is_valid or not hall.covers(proposed):
        raise ContractError("The angled-door counterexample must remain within the existing hall")
    combined = unary_union([hall, kitchen])
    relabeled = unary_union([hall.difference(proposed), kitchen.union(proposed)])
    finished = combined.buffer(-cfg["finish_assumption_mm"], join_style=2)
    centers = finished.buffer(-cfg["route_width_mm"]/2)
    parts = list(centers.geoms) if centers.geom_type == "MultiPolygon" else [centers]
    probes = {key: cfg["front_counterexample"][key+"_probe_mm"] for key in ["hall", "kitchen"]}
    components = {key: [n for n, part in enumerate(parts) if part.covers(Point(p))] for key, p in probes.items()}
    shared = hall.intersection(kitchen).length
    diagonal = LineString([cfg["front_counterexample"]["triangle_mm"][0], cfg["front_counterexample"]["triangle_mm"][1]]).length
    return {"rooms": [rooms[k] for k in ["mdf", "rear-hall1", "kitchen", "flex1"]],
        "nominal_shared_edge_mm": shared, "optimistic_finished_shared_edge_mm": shared-2*cfg["finish_assumption_mm"],
        "existing_door_nominal_mm": 900, "existing_door_budget_clear_mm": 900-cfg["total_frame_budget_mm"],
        "triangle_mm": cfg["front_counterexample"]["triangle_mm"], "diagonal_length_mm": round(diagonal, 4),
        "reclassified_triangle_sqm": round(proposed.area/1e6, 6),
        "free_floor_symmetric_difference_sqm": relabeled.symmetric_difference(combined).area/1e6,
        "finished_free_floor": mapping(finished), "circular_body_center_domain": mapping(centers),
        "center_domain_components": len(parts), "probe_components": components, "probes_mm": probes,
        "probes_connected": bool(set(components["hall"]) & set(components["kitchen"])),
        "appliances_and_door_leaves_ignored": True, "global_front_replanning_impossible": False,
        "front_care_route_approved": False, "note": cfg["front_counterexample"]["note"]}


def rear_screen(cfg, compact):
    """Clip the trial envelope at the site boundary; never validate the unknown exterior route."""
    gate = cfg["rear_gate"]
    patio = unary_union([rect(r) for r in compact["region_rects_mm"]])
    site = box(0, 0, 6000, 17630)
    opening = LineString(gate["opening_mm"])
    if (len(gate["opening_mm"]) != 2 or opening.length <= cfg["total_frame_budget_mm"]
            or any(p[1] != 17630 for p in gate["opening_mm"]) or not site.boundary.covers(opening)):
        raise ContractError("Rear opening must stay on the scoped rear boundary")
    closed, opened = rect(gate["closed_leaf_mm"]), rect(gate["open_leaf_mm"])
    if (list(closed.bounds)[1::2] != list(opened.bounds)[1::2]
            or closed.area != opened.area or closed.bounds[2]-closed.bounds[0] != opened.bounds[2]-opened.bounds[0]
            or gate["open_leaf_mm"][0] >= gate["closed_leaf_mm"][0]
            or not closed.covers(opening)):
        raise ContractError("Rear gate needs one constant-size horizontal leaf covering the closed aperture")
    travel = closed.union(opened).convex_hull
    fixed = compact["bodies"]+[f for f in compact["fixed"] if f["kind"] != "door-approach"]
    if not patio.covers(travel) or any(overlap(travel, rect(i["rect_mm"])) for i in fixed):
        raise ContractError("Rear gate travel conflicts with the nominal balcony or retained bodies")
    depth = gate["wall_bridge_depth_mm"]
    inset = cfg["finish_assumption_mm"]
    if type(depth) not in {int, float} or not 0 < depth <= inset+10:
        raise ContractError("Rear gate bridge only crosses the assumed wall band")
    clear = opening.length-cfg["total_frame_budget_mm"]
    left = min(p[0] for p in gate["opening_mm"])+cfg["total_frame_budget_mm"]/2
    bridge = box(left, 17630-depth, left+clear, 17630)
    floor = unary_union([patio.buffer(-inset, join_style=2), bridge])
    route = LineString(gate["route_points_mm"]).buffer(cfg["route_width_mm"]/2, cap_style=3, join_style=2)
    scoped = route.intersection(site)
    if scoped.is_empty or not floor.buffer(.01).covers(scoped):
        raise ContractError("Rear trial route falls outside the scoped finished floor and aperture budget")
    hits = [i["id"] for i in fixed if overlap(scoped, rect(i["rect_mm"]))]
    if hits:
        raise ContractError("Rear trial route conflicts with retained bodies: "+", ".join(hits))
    states = []
    for spec in gate["states"]:
        fraction = spec["fraction"]
        leaf_mm = [gate["closed_leaf_mm"][0]+fraction*(gate["open_leaf_mm"][0]-gate["closed_leaf_mm"][0]),
            *gate["closed_leaf_mm"][1:]]
        area = scoped.intersection(rect(leaf_mm)).area
        states.append({**spec, "leaf_rect_mm": leaf_mm, "scoped_route_leaf_overlap_sqm": round(area/1e6, 6),
            "scoped_route_blocked": area > .01, "whole_route_approved": False})
    if [s["scoped_route_blocked"] for s in states] != [False, True, True]:
        raise ContractError("Rear full-open trial must stay clear and half/closed controls must disclose obstruction")
    min_y = travel.bounds[1]
    gaps = {i["id"]: min_y-rect(i["rect_mm"]).bounds[3]
        for i in compact["bodies"] if i["id"] in {"optional-dryer-bay", "lowered-drying-envelope"}}
    return {"opening_nominal_mm": opening.length, "budget_clear_mm": clear, "actual_clear_mm": None,
        "wall_bridge_rect_mm": [left, 17630-depth, clear, depth],
        "travel_envelope_rect_mm": [travel.bounds[0], travel.bounds[1], travel.bounds[2]-travel.bounds[0], travel.bounds[3]-travel.bounds[1]],
        "travel_body_hits": [], "leaf_travel_body_gaps_mm": gaps, "gaps_are_product_tolerances": False,
        "route_width_mm": cfg["route_width_mm"], "scoped_route": mapping(scoped),
        "outside_route": mapping(route.difference(site)), "scoped_route_sqm": round(scoped.area/1e6, 6),
        "outside_unchecked_route_sqm": round(route.difference(site).area/1e6, 6),
        "scoped_route_inside_finished_assumption": True, "scoped_route_body_hits": hits,
        "shared_operation_bands": [i["id"] for i in compact["operations"] if overlap(scoped, rect(i["rect_mm"]))],
        "states": states, "site_frame_mm": [0, 0, 6000, 17630], "patio_rects_mm": compact["region_rects_mm"],
        "bodies": compact["bodies"], "fixed": compact["fixed"], "operations": compact["operations"],
        "outside_access_rights_verified": False, "threshold_and_door_product_verified": False,
        "whole_route_or_care_approved": False, "parent_laundry_geometry_changed": False}


def build(root):
    root, cache = Path(root), {}
    cfg = read_public_json(root, CONFIG)
    owner = read_public_json(root, cfg["owner_reference"])
    validate_config(cfg, owner)
    parent = sealed_parent(root, cfg, cache)
    if owner != parent["owner_direction"]:
        raise ContractError("Laundry access owner direction differs from the frozen parent")
    controls = read_public_json(root, "inputs/abc-next-protected-controls.json")["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    requirements = dict(Counter(r["status"] for r in read_public_json(root, "inputs/requirements.json")["requirements"]))
    register = dict(Counter(r["status"] for r in read_public_json(root, "inputs/planning-register.json")["items"]))
    if len(controls) != 149 or requirements != {"candidate": 66} or register != {"unknown": 105}:
        raise ContractError("Preserve protected originals and existing formal statuses")
    rooms = {r["id"]: r for r in parent["A1_source_rooms"]}
    front = front_screen(cfg, rooms)
    rear = rear_screen(cfg, parent["A1_options"][0])
    if (front["free_floor_symmetric_difference_sqm"] > .000001 or front["probes_connected"]
            or any(len(v) != 1 for v in front["probe_components"].values())):
        raise ContractError("The fixed-room front counterexample no longer establishes the claimed bottleneck")
    report = {"schema": "house-abc-laundry-access-report-v1", "date": cfg["date"], "config": cfg,
        "parent_report": PARENT, "parent_report_sha256": PARENT_SHA, "parent_report_hash": PARENT_HASH,
        "parent_sources_verified": len(parent["source_hashes"]), "owner_direction": owner,
        "recommendation": cfg["recommended_direction"], "front_entry_screen": front, "rear_entry_screen": rear,
        "C2_space_retained": copy.deepcopy(parent["C2_space_retained"]),
        "A2_reservation_retained": copy.deepcopy(parent["A2_reservation"]),
        "B_source_states_retained": copy.deepcopy(parent["B_source_states_retained"]),
        "parent_laundry_risks_retained": {"compact": parent["A1_options"][0]["screen"],
            "deeper_kitchen_area": parent["A1_options"][1]["kitchen_area"], "doors": parent["doors"],
            "actual_conditions": parent["actual_conditions"], "cross_building_route": parent["cross_building_route"]},
        "actual_conditions": cfg["actual_conditions"], "actual_conditions_received": 0,
        "formal_requirement_statuses": requirements, "formal_register_statuses": register,
        "protected_controls_unchanged": len(controls), "host_building_adopted": False,
        "original_ABC_or_3d_changed": False, "accepted_storage_viewers_changed": False,
        "adopted": False, "professional_approval": "unknown", "rendered_qa": "not-run",
        "geometry_scope": "fixed-front-counterexample-and-site-clipped-rear-envelope-only-no-exterior-route-or-products"}
    names = [CONFIG, DOC, cfg["owner_reference"], PARENT, *parent["source_hashes"],
        "inputs/abc-next-protected-controls.json", "inputs/requirements.json", "inputs/planning-register.json",
        "house_design/abc_laundry_access.py", "scripts/export_abc_laundry_access.py",
        "house_design/contracts.py", "house_design/project_status.py", "scripts/export_b_upper_replan.py",
        "scripts/export_builder_communication.py", "scripts/export_abc_next_improvements.py"]
    report["source_hashes"] = {name: digest(root, name, cache) for name in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

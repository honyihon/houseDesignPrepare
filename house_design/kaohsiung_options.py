"""Local landscape/service rectangles; never a building permit or care approval.

Works only on a supplied frozen model. No scene build, network, solver, drawing
generation or changes to canonical requirements. Soil patches are prospective
recessed planters, not verified soil depth or structural slab excavation.
"""
from __future__ import annotations

import copy
import math
from collections import Counter

from house_design.b32_rear_right import body, rect
from house_design.b32_service_detail import _inside, _route
from house_design.b32_services import _hits
from house_design.contracts import ContractError

SCHEMA = "house-kaohsiung-options-v1"
STATUS = "comparison-only-not-adopted"


def validate_config(cfg):
    if (cfg.get("schema") != SCHEMA or cfg.get("revision") != 1
            or cfg.get("status") != STATUS or not cfg.get("authorization")
            or cfg.get("frame_mm") != [6000, 17630] or cfg.get("default_option") != "c-split"
            or set(cfg.get("professional_status", {}).values()) != {"unknown"}):
        raise ContractError("Preserve the bounded independent study and unknown approvals")


def rooms(floor):
    return {c["key"]: c for c in floor["cells"] if c.get("tour_active")}


def bounds(area):
    x, y, w, h = area
    return {"minX": x, "minY": y, "maxX": x+w, "maxY": y+h}


def box_rect(box):
    return [box["minX"], box["minY"], box["maxX"]-box["minX"], box["maxY"]-box["minY"]]


def _cell_rect(cell):
    return [cell["tour_mm"][k] for k in ("x_mm", "y_mm", "w_mm", "h_mm")]


def _item_box(cell, item):
    return box_rect(cell["furniture_placements"]["tour_mm"][item["id"]]["aabb"])


def _move(cell, local, spec):
    """Translate/rotate original sizes and regenerate the full operation band."""
    from lib.model3d_placement import _candidate

    item = next(i for i in cell["furniture"] if i["id"].rsplit(":", 1)[-1] == local)
    x, y, w, h = spec["rect_mm"]
    yaw, anchor = spec["rotation_deg"], spec["wall_anchor"]
    expected = [item["width_mm"], item["depth_mm"]]
    if yaw % 180:
        expected.reverse()
    if [w, h] != expected:
        raise ContractError("Do not scale the original product: "+local)
    g = cell["tour_mm"]
    gap = {"front": y-g["y_mm"], "right": g["x_mm"]+g["w_mm"]-x-w,
        "left": x-g["x_mm"]}[anchor]
    item.update(rotation_deg=yaw, wall_anchor=anchor, wall_locked=True, wall_gap_mm=gap)
    placement = _candidate(item, x+w/2, y+h/2, yaw, anchor)
    placement["basis"] = "independent-kaohsiung-coordinate-study-not-installed"
    cell["furniture_placements"]["tour_mm"][item["id"]] = placement


def _outdoor_moves(model, cell, targets):
    """Keep pair identity, all 3D polyline copies and estimated lengths coherent."""
    units = [u for u in cell["tour_features"]["hvac_units"] if u["type"] == "outdoor"]
    if set(targets) != {u["id"] for u in units}:
        raise ContractError("Retain every original front outdoor unit")
    services = [r for r in cell["tour_features"]["fixed_reserved_mm"] if r["kind"] == "hvac-service"]
    if len(units) != len(services):
        raise ContractError("Cannot match original outdoor units and service envelopes")
    routes = {}
    for unit, service in zip(units, services, strict=True):
        dx = targets[unit["id"]]-unit["x_mm"]
        unit["x_mm"] += dx
        for key in ("minX", "maxX"):
            service["aabb"][key] += dx
        route = copy.deepcopy(unit["route"])
        if len(route["polyline_mm"]) != 6:
            raise ContractError("Unexpected base air-conditioning route")
        for point in route["polyline_mm"][2:]:
            point[0] += dx
        route["estimated_routed_length_mm"] = round(sum(
            sum(abs(a-b) for a, b in zip(p, q, strict=True))
            for p, q in zip(route["polyline_mm"], route["polyline_mm"][1:], strict=False)
        )+route["bend_service_allowance_mm"])
        route["status"] = "independent-coordinate-reroute-not-engineered"
        route["compliance"] = "unknown"
        routes[unit["id"]] = route

    def replace(value):
        if isinstance(value, dict):
            if value.get("id") in routes and "polyline_mm" in value:
                return copy.deepcopy(routes[value["id"]])
            return {key: replace(v) for key, v in value.items()}
        if isinstance(value, list):
            return [replace(v) for v in value]
        return value

    # Every route copy must be replaced: outdoor, paired indoor and project list.
    for key, value in list(model.items()):
        model[key] = replace(value)


def patch_model(original, cfg, bid, oid, state, *, control=False):
    model = copy.deepcopy(original)
    if not control:
        floor = next(f for f in model["buildings"][0]["floors"] if f["id"] == "floor-2")
        settings = cfg[bid.lower()]
        cell = rooms(floor)[settings["room"]]
        removed = settings.get("replaces_inferred_planter_locals", [])
        removed_items = [i for i in cell["furniture"] if i["id"].rsplit(":", 1)[-1] in removed]
        if len(removed_items) != len(removed) or any(i["shape"] != "planter" or i.get("physical_item_id") for i in removed_items):
            raise ContractError("Only explicitly listed inferred movable planters may be replaced")
        cell["furniture"] = [i for i in cell["furniture"] if i not in removed_items]
        for item in removed_items:
            cell["furniture_placements"]["tour_mm"].pop(item["id"])
        for local, spec in settings.get("moves", {}).items():
            _move(cell, local, spec)
        if bid == "C":
            # The old local route/reserve proof must not survive relocation.
            cell["tour_features"]["fixed_reserved_mm"] = [r for r in cell["tour_features"]["fixed_reserved_mm"]
                if not r["kind"].startswith("basis-")]
            cell["tour_features"].pop("basis_routes", None)
            _outdoor_moves(model, cell, settings["outdoor_x_mm"])
            cell = rooms(model["buildings"][0]["floors"][1])[settings["room"]]
        cell["tour_features"]["kaohsiung_zones"] = {
            "status": STATUS, "garden_mm": settings["garden_mm"],
            "soil_rects_mm": settings["soil_rects_mm"], "woody_points_mm": settings["woody_points_mm"],
            "green_deck_level": "symbolic-flush-finish-no-designed-soil-depth-or-slab-cut",
            "local_route_mm": settings["local_route_mm"],
            "service_routes_mm": settings.get("service_routes_mm", {}),
            "replaces_inferred_planters": [i["id"] for i in removed_items],
            "actual_soil_depth_mm": None, "lawful_area_and_cantilever": "unknown",
            "note": settings["note"],
        }
    model["source"]["kaohsiung_options"] = "inputs/kaohsiung-house-options.json"
    model["bc_option"].update(id=oid, use_state=state, adopted=False,
        geometry_review={"scope": "new-local-zones-only-not-inherited-qa-or-legal-approval"})
    return model


def review(plans, base_plans, settings, bid, *, control=False):
    """Fail closed on changed rooms/windows, hidden equipment or zone conflicts."""
    before, after = base_plans["floors"], plans["floors"]
    for a, b in zip(after, before, strict=True):
        if (a["width_mm"], a["depth_mm"], a["height_mm"], a["base_mm"]) != (
                b["width_mm"], b["depth_mm"], b["height_mm"], b["base_mm"]):
            raise ContractError("No envelope, elevation or stair change in this balcony study")
        if a["id"] != "floor-2" or control:
            aa, bb = copy.deepcopy(a), copy.deepcopy(b)
            aa.pop("plan_file", None)
            bb.pop("plan_file", None)
            # Relocated C outdoor pair needs a matching route on its 1F indoor copy.
            if bid == "C" and not control:
                for floor in (aa, bb):
                    for room in floor["rooms"]:
                        for unit in room["features"].get("hvac_units", []):
                            unit.pop("route", None)
            if aa != bb:
                raise ContractError("Unrelated floor changed")
    second = next(f for f in after if f["id"] == "floor-2")
    originals = {r["id"]: r for r in before[1]["rooms"]}
    changed = next(r for r in second["rooms"] if r["key"] == settings["room"])
    for room in second["rooms"]:
        old = originals[room["id"]]
        if (room["geometry"] != old["geometry"] or room["features"]["doors"] != old["features"]["doors"]
                or room["features"].get("open_connections") != old["features"].get("open_connections")):
            raise ContractError("Preserve rooms and original entrances")
        for key in ("window_face", "window_mm", "window_ratio", "window_review", "stair_geometry", "stair_footprint_mm"):
            if room["features"].get(key) != old["features"].get(key):
                raise ContractError("Do not reuse this comparison to change windows or stairs")
        if room["id"] != changed["id"]:
            aa, bb = copy.deepcopy(room), copy.deepcopy(old)
            if bid == "C" and not control:
                for value in (aa, bb):
                    for unit in value["features"].get("hvac_units", []):
                        unit.pop("route", None)
            if aa != bb:
                raise ContractError("Unrelated second-floor room changed")
    if control:
        return {"control": True, "adopted": False, "professional_approval": "unknown"}
    old = originals[changed["id"]]
    def size(room):
        return Counter((i["id"], i["catalog_id"], i["width_mm"], i["depth_mm"], i["height_mm"])
            for i in room["furniture"] if i["shape"] != "planter")
    if size(changed) != size(old):
        raise ContractError("All functional original furniture sizes and identities must survive")
    if bid == "C":
        washers = [(f["id"], i) for f in after for r in f["rooms"] for i in r["furniture"] if i["catalog_id"] == "washer"]
        if len(washers) != 1 or washers[0][0] != "floor-2":
            raise ContractError("Retain exactly one original 2F washer")
    zone = changed["features"]["kaohsiung_zones"]
    garden, soil = zone["garden_mm"], zone["soil_rects_mm"]
    if not _inside(garden, [rect(changed)], 0) or any(not _inside(r, [garden], 0) for r in soil):
        raise ContractError("Garden and soil must remain in the original outdoor floor")
    if any(_hits(a, b) for n, a in enumerate(soil) for b in soil[n+1:]):
        raise ContractError("Do not double count overlapping green patches")
    green = sum(r[2]*r[3]/1e6 for r in soil)
    area = garden[2]*garden[3]/1e6
    if garden[3] < 2000 or garden[3] > 3000 or area > 10:
        raise ContractError("This comparison keeps a 2-3m nominal depth and at most 10sqm per floor")
    if green+1e-9 < area/3 or len(zone["woody_points_mm"]) < math.ceil(green):
        raise ContractError("Retain the full proposed 1/3 soil and woody-plant count")
    if any(not any(r[0] <= x <= r[0]+r[2] and r[1] <= y <= r[1]+r[3] for r in soil)
            for x, y in zone["woody_points_mm"]):
        raise ContractError("Plant centres must be inside the soil study")
    items = [{"id": i["id"], "rect_mm": body(i)} for i in changed["furniture"]]
    services = [{"id": "hvac-service-"+str(n), "rect_mm": box_rect(r["aabb"])}
        for n, r in enumerate(changed["features"]["fixed_reserved_mm"]) if r["kind"] == "hvac-service"]
    soil_obstacles = [{"id": "soil-"+str(n), "rect_mm": r} for n, r in enumerate(soil)]
    conflicts = [a["id"]+":"+b["id"] for n, a in enumerate(items) for b in items[n+1:]+services+soil_obstacles
        if _hits(a["rect_mm"], b["rect_mm"])]
    conflicts += ["garden:"+r["id"] for r in items+services if _hits(garden, r["rect_mm"])]
    for n, service in enumerate(services):
        if not _inside(service["rect_mm"], [rect(changed)], 0):
            conflicts.append(service["id"]+":outside-original-balcony")
        conflicts += [service["id"]+":"+other["id"] for other in services[n+1:]
            if _hits(service["rect_mm"], other["rect_mm"])]
    # The proposed green/rest area is never also laundry, equipment or service area.
    operations = []
    for item in changed["furniture"]:
        op = item["placement"].get("operation_mm")
        if not op:
            continue
        r = box_rect(op)
        if not _inside(r, [rect(changed)], 115):
            operations.append(item["id"]+":outside-115mm-budget")
        operations += [item["id"]+":"+o["id"] for o in items+services+soil_obstacles
            if o["id"] != item["id"] and _hits(r, o["rect_mm"])]
        if _hits(r, garden):
            operations.append(item["id"]+":operation-in-garden")
    for item in items:
        if not _inside(item["rect_mm"], [rect(changed)], 115):
            conflicts.append(item["id"]+":outside-115mm-budget")
    for s in services:
        conflicts += [s["id"]+":"+p["id"] for p in soil_obstacles if _hits(s["rect_mm"], p["rect_mm"])]
    route = _route(zone["local_route_mm"], 700, 700, [rect(changed)], items+services+soil_obstacles, 115)
    service_routes = {name: _route(points, 700, 700, [rect(changed)], items+services+soil_obstacles, 115)
        for name, points in zone["service_routes_mm"].items()}
    if conflicts or operations or route["coordinate_failures"] or any(r["coordinate_failures"] for r in service_routes.values()):
        raise ContractError("Local layout conflicts: "+str({"body": conflicts, "operation": operations,
            "route": route["coordinate_failures"], "service": {k: r["coordinate_failures"] for k, r in service_routes.items()}}))
    return {"control": False, "garden_nominal_sqm": area, "proposed_soil_sqm": green,
        "minimum_one_third_sqm": area/3, "proposed_green_ratio": green/area,
        "garden_nominal_depth_mm": garden[3], "uncredited_other_outdoor_sqm": rect(changed)[2]*rect(changed)[3]/1e6-area,
        "woody_count": len(zone["woody_points_mm"]), "one_minimum_height_mm": 1200,
        "body_conflicts": conflicts, "operation_conflicts": operations, "local_700mm_rectangle_route": route,
        "service_local_700mm_routes": service_routes,
        "route_scope": "outdoor-local-proxy-only-not-door-or-whole-building-care-approval",
        "lawful_area_roof_cover_cantilever_soil_depth": "unknown",
        "garden_eligibility": "not-approved-conditional-nominal-study",
        "all_original_functional_furniture_sizes_preserved": True,
        "full_scheme_adopted": False, "professional_approval": "unknown"}


def a_and_c_costs():
    """Explicit rejected directions and a stair sensitivity, not new floor plans."""
    return {
        "a_front_uniform_depth_2200": {"extra_depth_mm": 700, "nominal_master_loss_sqm": 4.2,
            "nominal_master_remaining_sqm": 6*(3.280-.700), "remaining_room_depth_mm": 2580,
            "master_area_target_sqm": 16, "landscape_related_room_depth_min_mm": 3000,
            "status": "not-recommended-no-fake-rearranged-master-plan"},
        "a_first_floor_window": {
            "right_boundary_opening": "conditional-on-lawful-side-open-space-no-known-right-now",
            "front_lightwell_1000_square_mm": [5000, 7952, 1000, 1000],
            "living_nominal_loss_sqm": 1.0,
            "upper_public_corridor_intersection": True,
            "status": "whole-stack-replan-required-not-solved-by-a-window-symbol"},
        "c_arcade_height_stair": {
            "current_storey_mm": 3600, "proposed_storey_mm": 4000,
            "conditional_under_beam_target_mm": 3500,
            "current_beam_floor_budget_mm": 100, "proposed_beam_floor_budget_mm": 500,
            "existing_risers": 22, "existing_max_flight_treads": 10, "tread_mm": 270,
            "departure_landing_mm": 1000, "middle_landing_mm": 1000,
            "existing_required_run_and_landings_mm": 4700, "existing_box_depth_mm": 4840,
            "keep_22_risers_at_4000mm": {"riser_mm": 4000/22,
                "required_run_and_landings_mm": 4700, "nominal_box_spare_mm": 140,
                "conditional_article33_fourth_category_rise_limit_mm": 200,
                "status": "lower-disruption-study-usage-class-headroom-and-care-comfort-unknown"},
            "proposed_risers": 24, "proposed_riser_mm": 4000/24,
            "proposed_required_run_and_landings_mm": 4970, "additional_box_depth_needed_mm": 130,
            "upper_floor_base_shift_mm_if_adopted": 400,
            "status": "section-budget-only-no-adopted-height-or-stair-geometry",
            "code_riser_or_headroom_approval": "unknown"}
    }

"""C upstream gates and continuous body-route research, never access approval.

Analytic rigid-leaf envelopes, real paired apertures and specified translations;
no scene, browser, solver, network, requirements or adoption mutation.
"""
from __future__ import annotations

import math

from house_design.b32_rear_right import body, paired, rect
from house_design.b32_service_detail import _circle_hits, _inside, _route
from house_design.b32_services import _hits
from house_design.contracts import ContractError

SCHEMA, STATUS, SOURCE = "house-c-care-route-v1", "discussion-only-not-adopted", "inputs/c-care-route.json"


def validate_config(cfg):
    if (cfg.get("schema") != SCHEMA or cfg.get("revision") != 1 or cfg.get("status") != STATUS
            or not cfg.get("authorization") or cfg.get("frame_mm") != [6000, 17630]
            or cfg.get("insets_mm") != [80, 100, 115] or cfg.get("care_body_mm") != [900, 900]
            or cfg.get("default_option") != "c-route-refined" or set(cfg.get("professional_status", {}).values()) != {"unknown"}):
        raise ContractError("Preserve care targets, independent discussion scope and unknown approvals")
    d = cfg["street_door"]
    if (d["nominal_mm"] != 1200 or d["closed_leaf_mm"][2:] != [1050, 80] or d["height_mm"] != 2100
            or d["open_rotation_degrees"] != -90 or d["operation"] != "hinged-inward-proposal"):
        raise ContractError("Do not shrink or silently replace the generic exterior leaf")


def leaf_at_angle(closed, pivot, degrees):
    """Rigid endpoint bounds, not rescaled/repositioned independent rectangles."""
    x, y, w, h = closed
    angle = math.radians(degrees)
    points = [[pivot[0]+(xx-pivot[0])*math.cos(angle)-(yy-pivot[1])*math.sin(angle),
               pivot[1]+(xx-pivot[0])*math.sin(angle)+(yy-pivot[1])*math.cos(angle)]
              for xx in (x, x+w) for yy in (y, y+h)]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return [min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)]


def full_inward_sweep(closed, pivot):
    """All corner extrema on 0..90 degrees, not a few sampled poses.

    The resulting AABB is conservative. No overlap proves nonintersection;
    overlap would require further design/review, never an optimistic shortcut.
    """
    def extrema(a, b):
        angles = [0.0, math.pi/2]
        stationary = math.atan2(b, a)
        angles += [stationary+k*math.pi for k in range(-2, 3) if 0 < stationary+k*math.pi < math.pi/2]
        values = [a*math.cos(t)+b*math.sin(t) for t in angles]
        return min(values), max(values)
    x, y, w, h = closed
    xs, ys = [], []
    for xx in (x, x+w):
        for yy in (y, y+h):
            dx, dy = xx-pivot[0], yy-pivot[1]
            a, b = extrema(dx, dy)
            xs += [pivot[0]+a, pivot[0]+b]
            a, b = extrema(dy, -dx)
            ys += [pivot[1]+a, pivot[1]+b]
    return [min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)]


def barriers(room, inset=115):
    """Actual wall plus conservative jamb budgets, merging contiguous openings.

    Adjacent open-public subregions must not invent a column/door between them.
    Windows are not walkable openings. No frame deduction is called measured.
    """
    x, y, w, h = rect(room)
    result = []
    for face in ("front", "rear", "left", "right"):
        horizontal = face in {"front", "rear"}
        start, length = (x, w) if horizontal else (y, h)
        raw = []
        for opening in room["features"]["doors"]+room["features"]["open_connections"]:
            if opening["face"] == face:
                center = start+length*opening["ratio"]
                lo, hi = center-opening["width_mm"]/2, center+opening["width_mm"]/2
                if lo < start-.01 or hi > start+length+.01 or hi <= lo:
                    raise ContractError("Actual opening leaves its real shared wall")
                raw.append([lo, hi])
        merged = []
        for lo, hi in sorted(raw):
            if merged and lo <= merged[-1][1]+.01:
                merged[-1][1] = max(hi, merged[-1][1])
            else:
                merged.append([lo, hi])
        cursor = start
        gaps = []
        for lo, hi in merged:
            if hi-lo <= 2*inset:
                raise ContractError("No positive aperture remains after discussion deductions")
            gaps.append([cursor, lo+inset])
            cursor = hi-inset
        gaps.append([cursor, start+length])
        for number, (lo, hi) in enumerate(gaps):
            if hi-lo <= .01:
                continue
            edge = y if face == "front" else y+h if face == "rear" else x if face == "left" else x+w
            r = [lo, edge-inset, hi-lo, 2*inset] if horizontal else [edge-inset, lo, 2*inset, hi-lo]
            result.append({"id": room["key"]+"-"+face+"-wall-or-jamb-"+str(number), "rect_mm": r})
    return result


def review(plans, cfg, state, private_cfg, *, refined):
    cells = {r["key"]: r for r in plans["floors"][0]["rooms"]}
    public = [cells[k] for k in cfg["public_rooms"]]
    all_rooms = public+[cells[k] for k in cfg["private_rooms"]]
    areas = [rect(cells["garage"])]+[rect(r) for r in all_rooms]
    products = [{"id": i["id"], "rect_mm": body(i)} for r in cells.values() for i in r["furniture"] if i["shape"] != "wall-tv"]
    stair = cells["stair1f"]["features"]["stair_footprint_mm"]
    if [stair[k] for k in ("x_mm", "y_mm", "w_mm", "h_mm")] != [3720, 9030, 2200, 4700]:
        raise ContractError("Do not move or shrink the real stair to clear the care route")
    fixed = products+[{"id": "unchanged-stair-footprint", "rect_mm": [stair[k] for k in ("x_mm", "y_mm", "w_mm", "h_mm")]}]
    operations = []
    for r in public:
        for i in r["furniture"]:
            a = i["placement"].get("operation_mm")
            if a:
                operations.append({"id": i["id"]+"-retained-operation", "item": i["id"],
                    "rect_mm": [a["minX"], a["minY"], a["maxX"]-a["minX"], a["maxY"]-a["minY"]]})
    operation_hits = [op["id"]+":hits-"+p["id"] for op in operations for p in products if p["id"] != op["item"] and _hits(op["rect_mm"], p["rect_mm"])]
    walls = [wall for r in all_rooms for wall in barriers(r)]
    leaves = [{"id": leaf["id"]+"-"+leaf["state"]+"-leaf", "rect_mm": leaf["rect_mm"]}
              for r in cells.values() for leaf in r["features"].get("care_entry_leaves", [])]
    rows = {key: _route(points, *cfg["care_body_mm"], areas, fixed+operations+walls+leaves, 115) for key, points in cfg["routes"].items()}
    front = next(d for d in cells["dining"]["features"]["doors"] if d["neighbor"] is None)
    passage_field = "open_connections" if refined else "doors"
    passage = next(d for d in cells["sliding-door"]["features"][passage_field] if d["neighbor"] == cells["living-hall"]["id"])
    gates = [{"id": "street", "nominal_mm": front["width_mm"], "operation": front.get("operation", "unconfirmed")},
             {"id": "living-care", "nominal_mm": passage["width_mm"], "operation": "no-leaf-open-passage" if refined else passage.get("operation", "unconfirmed")}]
    for d in cells["elder"]["features"]["doors"]:
        gates.append({"id": "bedroom" if d["face"] == "front" else "bathroom", "nominal_mm": d["width_mm"], "operation": d["operation"]})
    for gate in gates:
        gate["clear_assumption_at_115mm"] = gate["nominal_mm"]-230
        gate["actual_finished_clear_and_product"] = "unknown"
    result = {"state": state, "body_mm": cfg["care_body_mm"], "gates": gates, "routes": rows,
        "retained_public_operations": operations, "operation_vs_fixed_body": operation_hits,
        "scope": "specified-point-in-arcade-to-bed-and-bath-entry-not-road-level-wheelchair-kinematics-or-full-bath-transfer",
        "private_bed_transfer_and_bath_operations": "not-all-protected-simultaneous-use-not-demonstrated",
        "stair_door_condition": "must-not-open-into-care-route-opening-direction-and-fire-certification-unknown",
        "professional_acceptance": "unknown", "adopted": False}
    if not refined:
        if not rows["arcade-to-bed"]["coordinate_failures"]:
            raise ContractError("Control must not silently pass its known upstream bottlenecks")
        return result
    # Nominal width must describe the same physical aperture on both sides.
    for a, b, face in (("living-hall", "sliding-door", "rear"), ("sliding-door", "sideyard", "rear")):
        transformed = {k: {**r, "features": {**r["features"], "doors": r["features"]["open_connections"]}} for k, r in cells.items()}
        paired(transformed, a, b, face, 3000, 1200)
        if any(d["neighbor"] == cells[b]["id"] for d in cells[a]["features"]["doors"]):
            raise ContractError("Open care passage must not retain a phantom partition door")
    if front["width_mm"] != cfg["street_door"]["nominal_mm"] or abs(rect(cells["dining"])[0]+rect(cells["dining"])[2]*front["ratio"]-cfg["street_door"]["center_x_mm"]) > .001:
        raise ContractError("Street leaf and actual front aperture differ")
    private_rows = []
    for key, door in private_cfg["doors"].items():
        actual = paired(cells, door["a"], door["b"], door["face"], door["center_mm"], door["nominal_mm"])
        leaf_state = "closed" if state == ("bedroom-closed" if key == "bedroom" else "bath-closed") else "open"
        leaves_found = [(r["key"], leaf) for r in cells.values() for leaf in r["features"].get("care_entry_leaves", []) if leaf["id"] == key]
        if (actual["operation"] != "sliding" or len(leaves_found) != 1 or leaves_found[0][0] != door["park_owner"]
                or leaves_found[0][1]["state"] != leaf_state or leaves_found[0][1]["rect_mm"] != door[leaf_state+"_leaf_mm"]
                or leaves_found[0][1]["height_mm"] != private_cfg["leaf_height_mm"] or leaves_found[0][1]["counts_as_furniture"] is not False):
            raise ContractError("Private paired aperture or full-size door leaf differs: "+key)
        if not _inside(door["open_leaf_mm"], [rect(cells[door["park_owner"]])], 115) or any(_hits(door["open_leaf_mm"], p["rect_mm"]) for p in fixed):
            raise ContractError("Private parked leaf borrows fixed product or stair space")
        private_rows.append({"id": key, "state": leaf_state, "nominal_mm": actual["width_mm"], "product": None})
    cx, cy, radius = private_cfg["bedroom_turn_circle_mm"]
    turn_failures = [] if _inside([cx-radius, cy-radius, 2*radius, 2*radius], [rect(cells["elder"])], 115) else ["turn-square:outside-bedroom"]
    turn_failures += ["turn-circle:hits-"+p["id"] for p in fixed+leaves if _circle_hits([cx, cy, radius], p["rect_mm"])]
    bed = body(next(i for i in cells["elder"]["furniture"] if i["shape"] == "bed"))
    bedroom = private_cfg["doors"]["bedroom"]
    entry_faces_bed = min(bedroom["center_mm"]+600, bed[0]+bed[2]) > max(bedroom["center_mm"]-600, bed[0])
    if turn_failures or radius != 750 or entry_faces_bed:
        raise ContractError("Retain the bedroom turning reserve and avoid the bed projection")
    dining = next(i for i in cells["dining"]["furniture"] if i["shape"] == "dining-set")
    a, op = dining["placement"]["aabb"], dining["placement"].get("operation_mm")
    if not op or any(abs(op[k]-(v+(400 if k.startswith("max") else -400))) > .01 for k, v in a.items()):
        raise ContractError("Do not erase or shrink the retained 400mm dining operation surround")
    d = cfg["street_door"]
    expected_state = "closed" if state == "street-closed" else "open"
    found = [leaf for r in cells.values() for leaf in r["features"].get("care_entry_leaves", []) if leaf["id"] == "street"]
    expected_rect = leaf_at_angle(d["closed_leaf_mm"], d["pivot_mm"], 0 if expected_state == "closed" else -90)
    if (len(found) != 1 or found[0]["state"] != expected_state or found[0]["height_mm"] != d["height_mm"]
            or any(abs(a-b) > .001 for a, b in zip(found[0]["rect_mm"], expected_rect, strict=True))):
        raise ContractError("Displayed exterior leaf does not follow the actual rigid hinge")
    sweep = full_inward_sweep(d["closed_leaf_mm"], d["pivot_mm"])
    if sweep[1] < 3900-.001 or not _inside(sweep, [rect(cells["dining"])], 0):
        raise ContractError("Exterior-door sweep may not occupy the arcade or cross a room wall")
    collisions = [p["id"] for p in fixed+operations if _hits(sweep, p["rect_mm"])]
    if collisions or operation_hits:
        raise ContractError("Exterior sweep/public operation conflicts: "+str(collisions+operation_hits))
    window = cells["dining"]["features"]
    g = cells["dining"]["geometry"]
    window_high = g["x_mm"]+g["w_mm"]*window["window_ratio"]+window["window_mm"]/2
    gap = d["center_x_mm"]-d["nominal_mm"]/2-window_high
    if window["window_mm"] != 2400 or gap < 100-.001:
        raise ContractError("Do not shrink or cover the front window to widen the entrance")
    open_leaf = leaf_at_angle(d["closed_leaf_mm"], d["pivot_mm"], -90)
    left = d["center_x_mm"]-d["nominal_mm"]/2+115
    right = min(d["center_x_mm"]+d["nominal_mm"]/2-115, open_leaf[0])
    effective = right-left
    if effective < 900 or any(g["clear_assumption_at_115mm"] < 900 for g in gates):
        raise ContractError("Do not call a leaf-obstructed or narrow gate sufficient for the original 900mm budget")
    expected_blocks = {"open": (False, False), "street-closed": (True, False), "bedroom-closed": (True, False), "bath-closed": (False, True)}[state]
    if tuple(bool(rows[k]["coordinate_failures"]) for k in ("arcade-to-bed", "bed-to-bath")) != expected_blocks:
        raise ContractError("Independent door-state negative controls did not block the intended route")
    if state != "open":
        route_key = "bed-to-bath" if state == "bath-closed" else "arcade-to-bed"
        leaf_key = {"street-closed": "street", "bedroom-closed": "bedroom", "bath-closed": "bathroom"}[state]
        failures = rows[route_key]["coordinate_failures"]
        if not failures or any(not f.endswith("hits-"+leaf_key+"-closed-leaf") for f in failures):
            raise ContractError("A negative control must fail only on its intended closed leaf")
    result.update(street_sweep_mm=sweep, street_pivot_mm=d["pivot_mm"], street_closed_leaf_mm=d["closed_leaf_mm"],
        street_open_leaf_mm=open_leaf, street_sweep_method="all-corner-analytic-extrema-0-to-90-conservative-AABB-not-angle-sampling",
        street_sweep_hits=collisions, front_window_to_opening_budget_mm=gap,
        effective_open_street_width_assumption_mm=effective, arcade_occupied_by_sweep=False,
        leaf_handle_stop_actual_open_angle_and_fire_approval="unknown", continuous_human_access_approval="unknown",
        private_doors=private_rows, bedroom_turn_circle_mm=[cx, cy, radius], turn_coordinate_failures=turn_failures,
        entry_projects_onto_bed_body=entry_faces_bed)
    return result

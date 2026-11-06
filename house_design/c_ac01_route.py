"""Dimensioned C-AC01 coordination candidate; no structural or product approval."""
from __future__ import annotations

import copy
import math

from house_design.contracts import ContractError

CONFIG = "inputs/c-ac01-route-study.json"
RUNTIME = "scripts/templates/c-ac01-route-runtime.js"


def length(points):
    return sum(sum(abs(a-b) for a, b in zip(p, q, strict=True))
        for p, q in zip(points, points[1:], strict=False))


def overlap(a, b):
    return all(min(a[n+3], b[n+3]) > max(a[n], b[n]) for n in range(3))


def unit_box(unit, base):
    w, d = unit["width_mm"], unit["depth_mm"]
    if unit["face"] in {"left", "right"}:
        w, d = d, w
    x, y, z = unit["x_mm"], unit["y_mm"], base+unit["mount_height_mm"]
    return [x-w/2, y-d/2, z, x+w/2, y+d/2, z+unit["height_mm"]]


def low_arcade_segments(points, depth, target=3500, radius=0):
    """Conservative swept-box screen, not a legal clearance or pipe-size test."""
    arcade = [0, 0, -10000, 6000, depth, target]
    result = []
    for n, (a, b) in enumerate(zip(points, points[1:], strict=False)):
        box = [min(a[k], b[k])-radius for k in range(3)]+[max(a[k], b[k])+radius for k in range(3)]
        # A zero-width centreline still needs a closed-boundary intersection screen.
        if (box[0] <= arcade[3] and box[3] >= arcade[0] and box[1] <= depth
                and box[4] >= 0 and box[2] < target):
            result.append(n)
    return result


def _inside_xy(box, g):
    return (g["x_mm"] <= box[0] and box[3] <= g["x_mm"]+g["w_mm"]
        and g["y_mm"] <= box[1] and box[4] <= g["y_mm"]+g["h_mm"])


def patch(model, cfg):
    if (cfg.get("schema") != "house-c-ac01-route-study-v1" or cfg.get("unit") != "C-AC01"
            or cfg.get("status") != "dimensioned-proposal-not-engineered"
            or cfg.get("professional_approval") != "unknown" or cfg.get("option") != "c-split"):
        raise ContractError("Preserve C-AC01 candidate scope and unknown approval")
    values = [*cfg["indoor_xy_mm"], *cfg["riser_xy_mm"], cfg["riser_envelope_mm"],
        cfg["bundle_half_width_budget_mm"], cfg["first_floor_branch_z_mm"], cfg["second_floor_route_relative_z_mm"],
        cfg["front_opening_buffer_budget_mm"]]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values):
        raise ContractError("C-AC01 coordinates and budgets must be positive finite values")
    floors = {f["id"]: f for f in model["buildings"][0]["floors"]}
    rooms = {c["id"]: c for f in floors.values() for c in f["cells"] if c.get("tour_active")}
    old_room, new_room = rooms[cfg["old_room"]], rooms[cfg["new_room"]]
    if old_room["id"] != "C:floor-1:living-right" or new_room["id"] != "C:floor-1:entrance":
        raise ContractError("Unexpected indoor move; review wall and serving space again")
    indoor = next(u for u in old_room["tour_features"]["hvac_units"] if u["id"] == "C-AC01" and u["type"] == "indoor")
    outdoor = next(u for u in rooms["C:floor-2:balcony2f"]["tour_features"]["hvac_units"] if u["id"] == "C-AC01" and u["type"] == "outdoor")
    baseline, before = copy.deepcopy(indoor["route"]), copy.deepcopy(indoor)
    first, second = floors["floor-1"], floors["floor-2"]
    old_box = unit_box(indoor, first["base_mm"])
    gate = rooms["C:floor-1:stair1f"]["tour_features"]["c_front_gate"]
    wall = gate["wall_budgets_mm"][0]
    gate_box = [wall[0], wall[1], first["base_mm"], wall[0]+wall[2], wall[1]+wall[3], first["base_mm"]+first["height_mm"]]
    indoor.update(x_mm=cfg["indoor_xy_mm"][0], y_mm=cfg["indoor_xy_mm"][1])
    body = unit_box(indoor, first["base_mm"])
    if not _inside_xy(body, new_room["tour_mm"]) or overlap(body, gate_box):
        raise ContractError("Candidate indoor unit crosses room bounds or front partition")
    for room in (old_room, new_room):
        for item in room["furniture"]:
            place = room["furniture_placements"]["tour_mm"][item["id"]]
            b, z = place["aabb"], first["base_mm"]+place.get("mount_height_mm", 0)
            if overlap(body, [b["minX"], b["minY"], z, b["maxX"], b["maxY"], z+item["height_mm"]]):
                raise ContractError("Candidate indoor unit intersects furniture: "+item["id"])
    rx, ry = cfg["riser_xy_mm"]
    size, radius = cfg["riser_envelope_mm"], cfg["bundle_half_width_budget_mm"]
    branch, high = cfg["first_floor_branch_z_mm"], second["base_mm"]+cfg["second_floor_route_relative_z_mm"]
    if not (size > radius*2 and first["base_mm"] < branch-radius < branch+radius < second["base_mm"]
            and second["base_mm"] < high-radius < high+radius < second["base_mm"]+second["height_mm"]):
        raise ContractError("Candidate vertical coordination budgets do not fit floor levels")
    envelope = [rx-size/2, ry-size/2, branch-radius, rx+size/2, ry+size/2, high+radius]
    bath, upper = rooms["C:floor-1:public-bath"], rooms["C:floor-2:living2f"]
    if not _inside_xy(envelope, bath["tour_mm"]) or not _inside_xy(envelope, upper["tour_mm"]):
        raise ContractError("Riser candidate must remain inside both stated coordination rooms")
    ug, uf = upper["tour_mm"], upper["tour_features"]
    if uf.get("window_face") != "front" or uf.get("window_review", {}).get("renderable") is not True:
        raise ContractError("Reassess front-wall openings before locating a pipe penetration")
    window_mid = ug["x_mm"]+ug["w_mm"]*uf["window_ratio"]
    openings = [("window", window_mid-uf["window_mm"]/2, window_mid+uf["window_mm"]/2)]
    for door in uf["doors"]:
        if door["face"] == "front":
            mid = ug["x_mm"]+ug["w_mm"]*door["ratio"]
            openings.append(("door", mid-door["width_mm"]/2, mid+door["width_mm"]/2))
    opening_margins = {}
    for kind, lo, hi in openings:
        gap = max(lo-(rx+radius), (rx-radius)-hi)
        if gap < cfg["front_opening_buffer_budget_mm"]:
            raise ContractError("Pipe crossing is too close to a nominal front opening: "+kind)
        opening_margins[kind] = gap
    for room, floor in ((bath, first), (upper, second)):
        for item in room["furniture"]:
            place = room["furniture_placements"]["tour_mm"][item["id"]]
            b, z = place["aabb"], floor["base_mm"]+place.get("mount_height_mm", 0)
            obstacle = [b["minX"], b["minY"], z, b["maxX"], b["maxY"], z+item["height_mm"]]
            if overlap(envelope, obstacle):
                raise ContractError("Riser candidate intersects furniture: "+item["id"])
        for door in room["tour_features"]["doors"]:
            if door["face"] == "front":
                g = room["tour_mm"]
                mid = g["x_mm"]+g["w_mm"]*door["ratio"]
                approach = [mid-door["width_mm"]/2-100, g["y_mm"], floor["base_mm"],
                    mid+door["width_mm"]/2+100, g["y_mm"]+900, floor["base_mm"]+2100]
                if overlap(envelope, approach):
                    raise ContractError("Riser candidate blocks front door approach budget")
    x, y, z = indoor["x_mm"], indoor["y_mm"], first["base_mm"]+indoor["mount_height_mm"]
    ox, oy = outdoor["x_mm"], outdoor["y_mm"]
    end_z = second["base_mm"]+outdoor["mount_height_mm"]+outdoor["height_mm"]/2
    points = [[x, y, z], [x, y, branch], [rx, y, branch], [rx, ry, branch],
        [rx, ry, high], [rx, 3900, high], [rx, oy, high], [ox, oy, high], [ox, oy, end_z]]
    if any(sum(a != b for a, b in zip(p, q, strict=True)) != 1 for p, q in zip(points, points[1:], strict=False)):
        raise ContractError("Candidate route must contain distinct orthogonal legs")
    if any(p[0]-radius < 0 or p[0]+radius > 6000 or p[1]-radius < 0 or p[1]+radius > 17630 for p in points):
        raise ContractError("Candidate pipe bundle extends outside the nominal building frame")
    low = low_arcade_segments(points, 3900, radius=radius)
    if low:
        raise ContractError("Candidate retains low refrigerant pipe over arcade: "+str(low))
    route = {**baseline, "indoor_room": new_room["id"], "polyline_mm": points,
        "estimated_routed_length_mm": length(points)+baseline["bend_service_allowance_mm"],
        "elevation_difference_mm": abs(end_z-z), "status": "dimensioned-interior-riser-candidate-not-engineered",
        "routing_height_note": f"室內支管+{branch:g}、室內立管至2F高位+{high:g}再到室外機；均為候選中心線。梁板穿孔、固定面、保溫、樹冠與維修未核。",
        "compliance": "unknown"}
    old_room["tour_features"]["hvac_units"].remove(indoor)
    new_room["tour_features"]["hvac_units"].append(indoor)
    new_room["name"] = "乾式前室／鞋櫃"
    for room in (old_room, new_room):
        room["tour_features"]["hvac"]["indoor"] = any(u["type"] == "indoor" for u in room["tour_features"]["hvac_units"])

    def replace(value):
        if isinstance(value, dict):
            if value.get("id") == "C-AC01" and "polyline_mm" in value:
                return copy.deepcopy(route)
            return {k: replace(v) for k, v in value.items()}
        if isinstance(value, list):
            return [replace(v) for v in value]
        return value

    for k, value in list(model.items()):
        model[k] = replace(value)
    rooms = {c["id"]: c for f in model["buildings"][0]["floors"] for c in f["cells"] if c.get("tour_active")}
    for rid, bottom, top in ((bath["id"], branch-radius, second["base_mm"]), (upper["id"], second["base_mm"], high+radius)):
        rooms[rid]["tour_features"]["c_ac01_riser_envelope"] = {"rect_mm": [rx-size/2, ry-size/2, size, size],
            "bottom_z_mm": bottom, "top_z_mm": top, "status": "coordination-envelope-not-built-shaft"}
    drain_reach = abs(y-(bath["tour_mm"]["y_mm"]+bath["tour_mm"]["h_mm"]))
    review = {"revision": 1, "status": cfg["status"], "professional_approval": "unknown",
        "baseline": baseline, "before_indoor": {k: v for k, v in before.items() if k != "route"},
        "old_indoor_partition_conflict": overlap(old_box, gate_box), "new_indoor_room": new_room["id"],
        "new_indoor_body_mm": body, "riser_envelope_mm": envelope, "route": route,
        "baseline_low_arcade_segments": low_arcade_segments(baseline["polyline_mm"], 3900),
        "candidate_low_arcade_segments": low, "bundle_half_width_budget_mm": radius,
        "nominal_front_opening_margins_mm": opening_margins,
        "floor2_coordination_floor_footprint_sqm": size*size/1e6,
        "upper_sofa_projection_gap_mm": min(i["aabb"]["minY"] for key, i in upper["furniture_placements"]["tour_mm"].items() if "sofa" in key)-envelope[4],
        "length_reduction_mm": baseline["estimated_routed_length_mm"]-route["estimated_routed_length_mm"],
        "routed_vertical_travel_mm": sum(abs(a[2]-b[2]) for a, b in zip(points, points[1:], strict=False)),
        "condensate_gravity_budget": {"horizontal_to_bath_boundary_mm": drain_reach,
            "fall_sensitivity_mm": {str(slope): drain_reach*slope/100 for slope in [1, 1.5, 2]},
            "actual_drain_port_z_mm": None, "lawful_terminal": None,
            "status": "fall-budget-only-no-positioned-drain-route-or-pump"},
        "notes": cfg["notes"], "products_manuals_anchors_sleeves_drainage_and_care": "unknown"}
    model["c_ac01_routing"] = review
    return review

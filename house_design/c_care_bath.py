"""Bounded care-bath comparisons, not regulation, care or rescue certification."""
from __future__ import annotations

import math

from house_design.b32_rear_right import body, rect
from house_design.b32_service_detail import _circle_hits, _inside, _route
from house_design.b32_services import _hits
from house_design.c_care_route import barriers, full_inward_sweep, leaf_at_angle
from house_design.contracts import ContractError

SCHEMA, STATUS, SOURCE = "house-c-care-bath-v1", "discussion-only-not-adopted", "inputs/c-care-bath.json"
STATES = ("transfer", "shower", "rail-down", "door-closed")


def validate_config(cfg):
    if (cfg.get("schema") != SCHEMA or cfg.get("revision") != 1 or cfg.get("status") != STATUS
            or not cfg.get("authorization") or cfg.get("frame_mm") != [6000, 17630]
            or cfg.get("bath_rect_mm") != [3600, 13800, 2400, 3000] or cfg.get("insets_mm") != [80, 100, 115]
            or cfg.get("body_mm") != [900, 900] or cfg.get("helper_mm") != [600, 600]
            or cfg.get("turn_reserve_mm", [])[2:] != [1500, 1800] or cfg.get("turn_circle_mm", [0]*3)[2] != 750
            or cfg.get("toilet_transfer_mm", [])[2:] != [900, 1200]
            or cfg.get("default_option") != "c-bath-refined" or set(cfg.get("professional_status", {}).values()) != {"unknown"}):
        raise ContractError("Keep original care scope, targets, room and unknown approvals")
    if ([cfg["seat"][k] for k in ("width_mm", "depth_mm", "thickness_mm")] != [480, 450, 45]
            or cfg["toilet_arm"]["length_mm"] != 650 or cfg["toilet_arm"]["diameter_mm"] != 35
            or cfg["rescue_trial"]["body_mm"] != [1800, 600]):
        raise ContractError("Never shrink the generic hardware or rigid-board trial to pass")


def components(cfg, state):
    """Full physical accessory envelopes, separate from furniture/owned items."""
    seat, arm = cfg["seat"], cfg["toilet_arm"]
    closed = [seat["hinge_y_mm"]-seat["depth_mm"], seat["hinge_height_mm"]-seat["thickness_mm"]/2,
              seat["depth_mm"], seat["thickness_mm"]]
    y, z, d, h = leaf_at_angle(closed, [seat["hinge_y_mm"], seat["hinge_height_mm"]], 0 if state == "shower" else -90)
    raised = state != "rail-down"
    data = [
        {"id": "fold-seat", "label": "480×450mm折椅候選", "kind": "box", "state": "deployed" if state == "shower" else "folded",
         "rect_mm": [seat["center_x_mm"]-seat["width_mm"]/2, y, seat["width_mm"], d], "bottom_mm": z, "height_mm": h},
        {"id": "toilet-arm", "label": "650mm可掀扶手候選", "kind": "pipe", "state": "raised" if raised else "lowered", "diameter_mm": arm["diameter_mm"],
         "points_mm": [[arm["x_mm"], arm["hinge_y_mm"], arm["hinge_height_mm"]],
                       [arm["x_mm"], arm["hinge_y_mm"]+(0 if raised else arm["length_mm"]), arm["hinge_height_mm"]+(arm["length_mm"] if raised else 0)]]},
        {"id": "toilet-wall-grab", "label": "馬桶右側L扶手候選", "kind": "pipe", "diameter_mm": 35,
         "points_mm": [[5835, 14150, 700], [5835, 15150, 700], [5835, 15150, 1100]]},
        {"id": "shower-wall-grab", "label": "淋浴L扶手候選", "kind": "pipe", "diameter_mm": 35,
         "points_mm": [[5835, 15585, 700], [5835, 16585, 700], [5835, 16585, 1100]]},
        {"id": "flush-drain", "label": "900mm線性地排候選（坡度／接管未核）", "kind": "box", "rect_mm": [4775, 16635, 900, 50], "bottom_mm": 0, "height_mm": 2, "flush_floor_only": True},
        {"id": "shower-controls", "label": "恆溫防燙及手持蓮蓬頭操作候選", "kind": "pipe", "diameter_mm": 35,
         "points_mm": [[5835, 15585, 1000], [5835, 15585, 1150], [5835, 15685, 1150], [5835, 15685, 1950]]},
        {"id": "alarm-toilet", "label": "馬桶求助拉繩預留（聲光／手機聯動待核）", "kind": "pipe", "diameter_mm": 8,
         "points_mm": [[4750, 13965, 100], [4750, 13965, 1100]]},
        {"id": "alarm-shower", "label": "淋浴求助拉繩預留（低位可及待核）", "kind": "pipe", "diameter_mm": 8,
         "points_mm": [[5835, 16000, 100], [5835, 16000, 1100]]},
    ]
    return [{"state": "planning", "status": "generic-accessory-not-selected-product", "counts_as_furniture": False, **row} for row in data]


def component_box(spec):
    if spec["kind"] == "box":
        x, y, w, d = spec["rect_mm"]
        return [x, y, w, d, spec["bottom_mm"], spec["height_mm"]]
    radius = spec["diameter_mm"]/2
    xs, ys, zs = zip(*spec["points_mm"], strict=True)
    return [min(xs)-radius, min(ys)-radius, max(xs)-min(xs)+2*radius, max(ys)-min(ys)+2*radius, min(zs)-radius, max(zs)-min(zs)+2*radius]


def hardware_sweeps(cfg):
    seat, arm = cfg["seat"], cfg["toilet_arm"]
    yz = full_inward_sweep([seat["hinge_y_mm"]-seat["depth_mm"], seat["hinge_height_mm"]-seat["thickness_mm"]/2,
                            seat["depth_mm"], seat["thickness_mm"]], [seat["hinge_y_mm"], seat["hinge_height_mm"]])
    r = arm["diameter_mm"]/2
    return [{"id": "seat-full-rotation", "box_mm": [seat["center_x_mm"]-seat["width_mm"]/2, yz[0], seat["width_mm"], yz[2], yz[1], yz[3]],
             "method": "analytic-all-corner-rigid-board-0-to-90-conservative-AABB"},
            {"id": "arm-full-rotation", "box_mm": [arm["x_mm"]-r, arm["hinge_y_mm"]-r, 2*r, arm["length_mm"]+2*r, arm["hinge_height_mm"]-r, arm["length_mm"]+2*r],
             "method": "quarter-disc-tube-conservative-AABB-not-endpoints-only"}]


def review(plans, cfg, state, *, refined):
    cells = {r["key"]: r for r in plans["floors"][0]["rooms"]}
    bath = cells["elder-bath"]
    if rect(bath) != cfg["bath_rect_mm"]:
        raise ContractError("Do not borrow the rear outdoor band or bedroom to solve the bath")
    local = [cells["elder"], bath]
    areas = [rect(r) for r in local]
    fixed = [{"id": i["id"], "rect_mm": body(i)} for r in local for i in r["furniture"] if i["shape"] != "wall-tv" and not (refined and i["shape"] == "shower" and i.get("step_free"))]
    walls = [w for r in local for w in barriers(r)]
    leaves = [{"id": leaf["id"]+"-"+leaf["state"]+"-leaf", "rect_mm": leaf["rect_mm"]} for r in cells.values() for leaf in r["features"].get("care_entry_leaves", [])]
    accessories = bath["features"].get("care_bath_components", [])
    if refined and accessories != components(cfg, state):
        raise ContractError("Actual accessory state/envelopes differ from the specified products")
    hardware = [{"id": s["id"], "rect_mm": component_box(s)[:4]} for s in accessories if not s.get("flush_floor_only")]
    obstacles = fixed+walls+leaves+hardware
    paths = {k: _route(points, *cfg["body_mm"], areas, obstacles, 115) for k, points in cfg["routes"].items()}
    helpers = {k: _route(points, *cfg["helper_mm"], areas, obstacles, 115) for k, points in cfg["helper_routes"].items()}
    floor_obstacles = fixed+hardware+leaves
    reserve = cfg["turn_reserve_mm"]
    turn_failures = [] if _inside(reserve, [rect(bath)], 115) else ["reserve:outside-assumed-bath"]
    turn_failures += ["reserve:hits-"+p["id"] for p in floor_obstacles if _hits(reserve, p["rect_mm"])]
    circle = cfg["turn_circle_mm"]
    turn_failures += ["circle:hits-"+p["id"] for p in floor_obstacles if _circle_hits(circle, p["rect_mm"])]
    transfer = cfg["toilet_transfer_mm"]
    transfer_failures = [] if _inside(transfer, [rect(bath)], 115) else ["transfer:outside-bath"]
    transfer_failures += ["transfer:hits-"+p["id"] for p in floor_obstacles if _hits(transfer, p["rect_mm"])]
    rescue = cfg["rescue_trial"]
    board = _route(rescue["points_mm"], *rescue["body_mm"], areas, obstacles, 115)
    diagonal = math.ceil(math.hypot(*rescue["body_mm"]))
    cx, cy = rescue["rotation_center_mm"]
    rotation = [cx-diagonal/2, cy-diagonal/2, diagonal, diagonal]
    rotation_failures = [] if _inside(rotation, [rect(bath)], 115) else ["board-rotation:outside-bath"]
    rotation_failures += ["board-rotation:hits-"+p["id"] for p in floor_obstacles if _hits(rotation, p["rect_mm"])]
    result = {"state": state, "body_mm": cfg["body_mm"], "routes": paths, "helper_routes": helpers,
        "turn_reserve_mm": reserve, "turn_circle_mm": circle, "turn_coordinate_failures": turn_failures,
        "toilet_transfer_mm": transfer, "transfer_coordinate_failures": transfer_failures,
        "rescue_board_translation": board, "rescue_board_rotation_mm": rotation, "rescue_board_rotation_failures": rotation_failures,
        "rescue_scope": rescue["note"], "professional_acceptance": "unknown", "adopted": False,
        "caregiver_strength_reach_real_chair_and_helpers": "unknown", "independent_dry_turn_floor": False,
        "full_bath_rescue_and_public_caregiver_access": "unknown-private-bedroom-access-retained"}
    if not refined:
        if not turn_failures or not transfer_failures:
            raise ContractError("Retain the control's original fixed-shower/fixture limitations")
        return result
    if state not in STATES:
        raise ContractError("Explicit independent bath use state required")
    products = {i["id"].rsplit(":", 1)[-1]: i for i in bath["furniture"]}
    dimensions = {"toilet": [450, 700, 800], "vanity": [600, 450, 850], "accessible-shower": [1200, 1200, 2000]}
    for key, raw in cfg["fixtures"].items():
        item = products[key]
        x, y, w, d = raw["rect_mm"]
        expected_op = {"minX": x, "maxX": x+w,
                       "minY": y+d if raw["wall_anchor"] == "front" else y-700,
                       "maxY": y+d+700 if raw["wall_anchor"] == "front" else y}
        if (body(item) != raw["rect_mm"] or item["placement"]["rotation_deg"] != raw["rotation_deg"]
                or [item[k] for k in ("width_mm", "depth_mm", "height_mm")] != dimensions[key]
                or item["front_clearance_mm"] != 700 or item["placement"].get("operation_mm") != expected_op):
            raise ContractError("Actual fixture differs from the unsqueezed layout: "+key)
    if not products["accessible-shower"].get("step_free") or not products["accessible-shower"].get("care_bath_open_shower"):
        raise ContractError("Shared floor cannot contain a fixed shower curb or glass screen")
    expected = {"transfer": (False, False, False), "shower": (True, False, True), "rail-down": (False, True, False), "door-closed": (False, False, False)}[state]
    if (bool(turn_failures), bool(transfer_failures), bool(rotation_failures)) != expected:
        raise ContractError("Bath turn/transfer/rigid-board negative controls differ: "+str(result))
    blocked_door = state == "door-closed"
    for key, path in paths.items():
        expected_id = "bathroom-closed-leaf" if blocked_door else "toilet-arm" if state == "rail-down" and key == "toilet-transfer" else None
        failures = path["coordinate_failures"]
        if (bool(failures) != bool(expected_id)) or expected_id and any(not f.endswith("hits-"+expected_id) for f in failures):
            raise ContractError("Bath route must fail only on its intended independent obstacle: "+key+str(failures))
    for path in [*helpers.values(), board]:
        if bool(path["coordinate_failures"]) != blocked_door or blocked_door and any(not f.endswith("hits-bathroom-closed-leaf") for f in path["coordinate_failures"]):
            raise ContractError("Helper/board route negative control mismatch")
    # One stationary helper beside the final chair rectangle, not proof of a
    # complete lift or two simultaneous caregivers. Shared floors are explicit.
    for route_key, reserve_key in (("toilet-transfer", "toilet_helper_mm"), ("shower-seat-front", "shower_helper_mm")):
        x, y = cfg["routes"][route_key][-1]
        helper = cfg[reserve_key]
        if not _inside(helper, [rect(bath)], 115) or _hits([x-450, y-450, 900, 900], helper) or any(_hits(helper, p["rect_mm"]) for p in floor_obstacles):
            raise ContractError("Do not claim a helper station inside the chair or a fixture")
    sweeps = hardware_sweeps(cfg)
    collisions = []
    for sweep in sweeps:
        b = sweep["box_mm"]
        if not _inside(b[:4], [rect(bath)], 115):
            collisions.append(sweep["id"]+":outside-bath")
        for p in products.values():
            z, h = p["placement"]["mount_height_mm"], p["height_mm"]
            if p["shape"] != "shower" and _hits(b[:4], body(p)) and min(b[4]+b[5], z+h) > max(b[4], z):
                collisions.append(sweep["id"]+":hits-"+p["id"])
    if collisions:
        raise ContractError("Full-angle hardware sweep conflicts with the fixed bath: "+str(collisions))
    result.update(hardware_sweeps=sweeps, hardware_sweep_conflicts=collisions,
        shared_wet_floor_overlap_sqm=_overlap_area(reserve, body(products["accessible-shower"]))/1e6,
        toilet_center_to_right_assumed_wall_mm=6000-115-(body(products["toilet"])[0]+225),
        door_release="external-release-and-removal-candidate-not-verified-product-or-body-pressure-rescue",
        drainage="flush-linear-drain-proposal-no-designed-slopes-or-pipe-connection",
        ventilation="retained-rear-high-window-and-separate-exhaust-route-candidate-no-airflow-or-legal-approval",
        critical_margins_mm={"entry_body_to_vanity": cfg["routes"]["toilet-transfer"][0][1]-450-sum(body(products["vanity"])[1::2]),
                             "transfer_to_vanity": transfer[0]-sum(body(products["vanity"])[::2]),
                             "rigid_board_rotation_to_folded_seat": component_box(components(cfg, "transfer")[0])[1]-sum(rotation[1::2])},
        construction_tolerance_and_products="unresolved-tight-budget-not-construction-release",
        knee_clearance_credit_mm=0, simultaneous_lift_and_multiple_caregivers="not-demonstrated")
    return result


def _overlap_area(a, b):
    return max(0, min(a[0]+a[2], b[0]+b[2])-max(a[0], b[0]))*max(0, min(a[1]+a[3], b[1]+b[3])-max(a[1], b[1]))

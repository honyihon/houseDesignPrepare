"""Bounded B32 rear-right bathroom studies; no renderer, solver or approvals.

Translation rectangles and full-diagonal rotation squares concern the stored
body only. They do not model carrying people, poles, height or wheelchair motion.
"""
from __future__ import annotations

import math

from house_design.b32_service_detail import _circle_hits, _inside, _route
from house_design.b32_services import _hits
from house_design.contracts import ContractError


def rect(room: dict) -> list:
    return [room["geometry"][k] for k in ("x_mm", "y_mm", "w_mm", "h_mm")]


def body(item: dict) -> list:
    b = item["placement"]["aabb"]
    return [b["minX"], b["minY"], b["maxX"]-b["minX"], b["maxY"]-b["minY"]]


def paired(cells: dict, a: str, b: str, face: str, center: float, width: float) -> dict:
    inverse = {"front": "rear", "rear": "front", "left": "right", "right": "left"}
    axis, length = ("x_mm", "w_mm") if face in {"front", "rear"} else ("y_mm", "h_mm")
    result = None
    for key, other, side in ((a, b, face), (b, a, inverse[face])):
        found = [d for d in cells[key]["features"]["doors"] if d["neighbor"] == cells[other]["id"]]
        if len(found) != 1:
            raise ContractError("Missing/ambiguous actual paired opening: "+a+" / "+b)
        door, g = found[0], cells[key]["geometry"]
        if (door["face"] != side or door["width_mm"] != width
                or abs(g[axis]+g[length]*door["ratio"]-center) > .001):
            raise ContractError("Actual opening differs from tested aperture: "+key)
        if result is not None and result["operation"] != door["operation"]:
            raise ContractError("Paired door operations differ")
        result = door
    return result


def aperture_walls(room: dict, door: dict, inset: int, label: str) -> list:
    """Use actual opening centers and two-sided discussion frame deductions."""
    x, y, w, h = rect(room)
    horizontal = door["face"] in {"front", "rear"}
    center = (x if horizontal else y)+door["ratio"]*(w if horizontal else h)
    lo, hi = center-door["width_mm"]/2+inset, center+door["width_mm"]/2-inset
    if horizontal:
        edge = y if door["face"] == "front" else y+h
        pieces = [[x, edge-inset, lo-x, 2*inset], [hi, edge-inset, x+w-hi, 2*inset]]
    else:
        edge = x if door["face"] == "left" else x+w
        pieces = [[edge-inset, y, 2*inset, lo-y], [edge-inset, hi, 2*inset, y+h-hi]]
    if any(min(r[2:]) < 0 for r in pieces):
        raise ContractError("Door frame cannot extend beyond its actual wall")
    return [{"id": label+str(n), "rect_mm": r} for n, r in enumerate(pieces) if min(r[2:]) > 0]


def variable_route(segments: list, rotations: list, areas: list, obstacles: list, inset: int,
                   stored_body: list) -> dict:
    """Explicit orthogonal translations, with continuity and full-rotation proof."""
    rows, failures = [], []
    width, depth = stored_body
    for index, segment in enumerate(segments):
        yaw = segment["yaw_deg"]
        if yaw not in {0, 90}:
            raise ContractError("Only specified orthogonal transport orientations supported")
        dims = [width, depth] if yaw == 0 else [depth, width]
        if index:
            previous = segments[index-1]
            if previous["points_mm"][-1] != segment["points_mm"][0]:
                raise ContractError("Transport segments must meet at the same actual center")
            if previous["yaw_deg"] != yaw and not any(
                    r["center_mm"] == segment["points_mm"][0]
                    and r["from_yaw_deg"] == previous["yaw_deg"] and r["to_yaw_deg"] == yaw for r in rotations):
                raise ContractError("A change of orientation requires an explicit rotation review")
        route = _route(segment["points_mm"], *dims, areas, obstacles, inset)
        rows.append({**segment, **route})
        failures += [f"translation-{index}:"+s for s in route["coordinate_failures"]]
    squares = []
    diagonal = math.ceil(math.hypot(width, depth))
    for rotation in rotations:
        cx, cy = rotation["center_mm"]
        envelope = [cx-diagonal/2, cy-diagonal/2, diagonal, diagonal]
        issues = [] if _inside(envelope, areas, inset) else ["outside-assumed-turn-floor"]
        issues += ["hits-"+o["id"] for o in obstacles if _hits(envelope, o["rect_mm"])]
        squares.append({**rotation, "full_rotation_envelope_mm": envelope, "coordinate_failures": issues})
        failures += ["rotation:"+s for s in issues]
    return {"segments": rows, "rotations": squares, "coordinate_failures": failures,
            "rotation_method": "ceil-full-body-diagonal-square-all-angles-not-only-endpoints",
            "stored_body_mm": stored_body, "assembled_poles_people_height_and_rehearsal": "unknown"}


def review_state(plans: dict, config: dict, option: dict, state: str) -> dict:
    rooms = {r["key"]: r for r in plans["floors"][0]["rooms"]}
    all_items = [(r, i) for r in rooms.values() for i in r["furniture"]]
    obstacles = [{"id": i["id"], "rect_mm": body(i)} for _, i in all_items if i["shape"] not in {"palanquin", "wall-tv"}]
    bath = rooms["rear-bath"]
    door_x = option["bath_door_center_x_mm"]
    bath_door = paired(rooms, "rear-bath", "bath-approach", "front", door_x, config["bath_door_nominal_mm"])
    if bath_door["operation"] != "sliding":
        raise ContractError("Bathroom study requires its actual sliding-door operation")
    dry_door = paired(rooms, "altar-backing", "corridor1", "right", 12170, 1060)
    entry = next(d for d in rooms["shrine-front"]["features"]["doors"] if d["neighbor"] is None)
    entry_x = rooms["shrine-front"]["geometry"]["x_mm"]+entry["ratio"]*rooms["shrine-front"]["geometry"]["w_mm"]
    if entry["face"] != "front" or entry["width_mm"] != 1800 or abs(entry_x-3400) > .001:
        raise ContractError("Retain the altar-axis street door")
    ritual = []
    for room in rooms.values():
        for zone in room["features"]["fixed_reserved_mm"]:
            if zone["kind"] in {"ritual-approach", "b-separate-seated-operation"}:
                a = zone["aabb"]
                ritual.append({"id": room["id"]+":"+zone["kind"], "rect_mm": [a["minX"], a["minY"], a["maxX"]-a["minX"], a["maxY"]-a["minY"]]})
    allowed = [rect(rooms[k]) for k in ("shrine-front", "shrine", "corridor1", "bath-approach", "rear-bath")]
    bath_obstacles = [o for o in obstacles if o["id"] in {i["id"] for i in bath["furniture"]}]
    laundry_areas = [rect(rooms[k]) for k in ("laundry-front", "laundry-base")]
    rows = []
    for inset in config["insets_mm"]:
        start = door_x-config["bath_door_nominal_mm"]/2
        envelopes = {"park": [start-config["slide_park_length_mm"], 14500+inset,
                               config["slide_park_length_mm"], config["slide_projection_mm"]],
                     "closed": [start, 14500+inset, config["bath_door_nominal_mm"], config["slide_projection_mm"]]}
        panel = {"id": "parked-bath-slider-and-handle-budget", "rect_mm": envelopes["park"]}
        walls = aperture_walls(bath, bath_door, inset, "bath-door-jamb-")
        local = [[door_x, 13820], [door_x, 15525], [4895, 15525]]
        right_turn_y = 5100 if state == "carry" and option["id"] == "front-backup" else 5000
        arrival = [[3400, 4465], [3400, right_turn_y], [door_x, right_turn_y]]+local
        # The last front-hall point and local entry share x; no diagonal shortcuts.
        arrival_review = _route(arrival, 900, 900, allowed, obstacles+walls+[panel], inset)
        ritual_review = _route(arrival, 900, 900, allowed, obstacles+walls+[panel]+ritual, inset)
        basin = _route([[4895, 15525], [4895, 15725], [4015, 15725], [4015, 16615]], 900, 900,
                       [rect(bath)], bath_obstacles+[panel], inset)
        side = _route([[4895, 15525], [4895, 15725], [4015, 15725]], 900, 900, [rect(bath)], bath_obstacles+[panel], inset)
        shower = _route([[4895, 15525], [4895, 15865], [5285, 15865]], 900, 900, [rect(bath)], bath_obstacles+[panel], inset)
        circle = config["turn_circle_mm"]
        cx, cy, radius = circle
        circle_issues = [] if _inside([cx-radius, cy-radius, radius*2, radius*2], [rect(bath)], inset) else ["outside-bath"]
        circle_issues += [o["id"] for o in bath_obstacles+[panel] if _circle_hits(circle, o["rect_mm"])]
        operations = []
        for name, r in config["bath_operations_mm"].items():
            if not _inside(r, [rect(bath)], inset):
                operations.append(name+":outside-bath")
            operations += [name+":hits-"+o["id"] for o in bath_obstacles+[panel] if _hits(r, o["rect_mm"])]
        laundry_issues = []
        for name, r in option["laundry_operations_mm"].items():
            if not _inside(r, laundry_areas, inset):
                laundry_issues.append(name+":outside-private-laundry")
            laundry_issues += [name+":hits-"+o["id"] for o in obstacles if _hits(r, o["rect_mm"])]
        dry_geometry = rect(rooms["altar-backing"])
        dry_right = dry_geometry[0]+dry_geometry[2]-inset
        dry_swing = [dry_right-1105, 11640, 1105, 1060]
        dry_leaf = [dry_right-1060, 11640, 1060, 45]
        dry = _route([[5160, 12170], [3465, 12170]], 700, 700,
                     [rect(rooms[k]) for k in ("corridor1", "altar-backing")],
                     obstacles+aperture_walls(rooms["altar-backing"], dry_door, inset, "dry-jamb-")+
                     [{"id": "dry-open-leaf", "rect_mm": dry_leaf}], inset)
        if option["id"] == "front-backup":
            laundry_door = paired(rooms, "laundry-base", "bath-approach", "right", 13650, 1130)
            laundry_leaf = {"id": "fully-open-laundry-leaf", "rect_mm": [4750-inset-1130, 13085, 1130, 45]}
            laundry_route = _route([[5375, 13650], [3765, 13650], [2915, 13650], [2915, 13535]], 700, 700,
                laundry_areas+[rect(rooms["bath-approach"])], obstacles+
                aperture_walls(rooms["laundry-base"], laundry_door, inset, "laundry-jamb-")+[laundry_leaf], inset)
            laundry_sink = _route([[2915, 13535], [2915, 13935]], 700, 700, laundry_areas, obstacles+[laundry_leaf], inset)
            swing = [4750-inset-1175, 13085, 1175, 1130]
            laundry_issues += ["laundry-door-sweep:hits-"+o["id"] for o in obstacles if _hits(swing, o["rect_mm"])]
            if not _inside(swing, laundry_areas, inset):
                laundry_issues.append("laundry-door-sweep:outside-private-bay")
        else:
            equipment_budgets = [[3005, 13085, 1200, 700], [2400, 13885, 550, 500]]
            for number, budget in enumerate(equipment_budgets):
                if not _inside(budget, laundry_areas, inset):
                    laundry_issues.append(f"small-equipment-budget-{number}:outside-laundry")
                excluded = "dehumidifier" if number == 1 else "small-drying-rack"
                laundry_issues += [f"small-equipment-budget-{number}:hits-"+o["id"] for o in obstacles
                                  if not o["id"].endswith(":"+excluded) and _hits(budget, o["rect_mm"])]
            laundry_route = _route([[680, 13435], [3355, 13435]], 700, 700,
                laundry_areas+[rect(rooms["storage-front"])], obstacles, inset)
            laundry_sink = _route([[3355, 13435], [1925, 13435]], 700, 700, laundry_areas, obstacles, inset)
        rows.append({"inset_mm": inset, "bath_entry_route": arrival_review, "bath_during_ritual": ritual_review,
                     "bath_closed_door_route": _route(local, 900, 900, allowed, obstacles+walls+[panel,
                         {"id": "closed-bath-leaf", "rect_mm": envelopes["closed"]}], inset),
                     "basin_route": basin, "toilet_side_route": side, "shower_route": shower,
                     "turn_circle_failures": circle_issues, "bath_operation_failures": operations,
                     "laundry_operation_failures": laundry_issues, "local_laundry_700mm_route": laundry_route,
                     "local_laundry_sink_700mm_route": laundry_sink,
                     "local_laundry_scope": "equipment-access-body-only-not-public-care-or-during-carry-access",
                     "dry_cabinet_route": dry,
                     "dry_door_swing_failures": [o["id"] for o in obstacles if _hits(dry_swing, o["rect_mm"])],
                     "door_clear_assumption_mm": bath_door["width_mm"]-2*inset,
                     "public_corridor_clear_assumption_mm": min(rect(rooms[k])[2] for k in ("corridor1", "bath-approach"))-2*inset,
                     "door_envelopes_mm": envelopes})
    carry_areas = [rect(rooms[k]) for k in ("storage", "storage-front")]
    palanquin = next(i for i in rooms["storage"]["furniture"] if i["shape"] == "palanquin")
    pal = body(palanquin)
    if pal != config["palanquin_body_mm"] or pal[2:] != [1200, 1700]:
        raise ContractError("Transport must terminate at the actual full-size storage body")
    final_center = [pal[0]+pal[2]/2, pal[1]+pal[3]/2]
    if option["id"] == "rear-alley":
        rear = next(d for d in rooms["storage"]["features"]["doors"] if d["neighbor"] is None and d["face"] == "rear")
        rear_x = rect(rooms["storage"])[0]+rear["ratio"]*rect(rooms["storage"])[2]
        carry_segments = [{"yaw_deg": 0, "points_mm": [[rear_x, 17630-115-pal[3]/2], [rear_x, final_center[1]], final_center]}]
        carry_obstacles = obstacles+aperture_walls(rooms["storage"], rear, 115, "rear-entry-jamb-")
        rotations = []
        clear_min = rear["width_mm"]-230
        entry_gate = rear
        entry_gate_center, entry_body_center = rear_x, rear_x
    else:
        gate = paired(rooms, "storage-front", "left-approach", "front", 875, 1730)
        carry_areas += [rect(rooms[k]) for k in ("shrine-front", "shrine", "turn-bay", "left-approach")]
        carry_obstacles = obstacles+aperture_walls(rooms["shrine-front"], entry, 115, "street-entry-jamb-")
        carry_obstacles += aperture_walls(rooms["storage-front"], gate, 115, "left-storage-jamb-")
        carry_segments = [
            {"yaw_deg": 0, "points_mm": [[3400, 4865], [3400, 6550], [3600, 6550]]},
            {"yaw_deg": 90, "points_mm": [[3600, 6550], [3600, 9815], [1200, 9815], [1200, 10320]]},
            {"yaw_deg": 0, "points_mm": [[1200, 10320], [875, 10320], [875, 15500], [final_center[0], 15500], final_center]}]
        rotations = [{"center_mm": c, "from_yaw_deg": a, "to_yaw_deg": b} for c, a, b in
                     zip(config["front_staging"]["rotation_centers_mm"], (0, 90), (90, 0), strict=True)]
        clear_min = min(entry["width_mm"]-230, gate["width_mm"]-230, rect(rooms["left-approach"])[2]-230)
        entry_gate = entry
        entry_gate_center, entry_body_center = entry_x, carry_segments[0]["points_mm"][0][0]
    carry = variable_route(carry_segments, rotations, carry_areas, carry_obstacles, 115, [1200, 1700])
    gate_span = [entry_gate_center-entry_gate["width_mm"]/2+115, entry_gate_center+entry_gate["width_mm"]/2-115]
    gate_failures = [] if entry_body_center-600 >= gate_span[0] and entry_body_center+600 <= gate_span[1] else ["actual-entry-aperture:narrower-than-positioned-body"]
    carry["entry_aperture_check"] = {"effective_span_mm": gate_span, "body_center_x_mm": entry_body_center,
                                      "body_width_mm": 1200, "coordinate_failures": gate_failures,
                                      "external_crossing_and_turn": "not-modelled-outside-site-boundary"}
    carry["coordinate_failures"] += gate_failures
    protected_target = variable_route(carry_segments, rotations, carry_areas, carry_obstacles, 115, [1500, 1700])
    return {"state": state, "bath_route_sensitivity": rows, "carry_stored_body_115mm": carry,
            "minimum_carry_aperture_assumption_115mm": clear_min,
            "original_continuous_transport_target_mm": 1500,
            "transport_aperture_shortfall_mm": max(0, 1500-clear_min),
            "continuous_1500mm_conservative_envelope_review": protected_target,
            "continuous_target_scope": "1500-wide-by-1700-deep-proxy-not-people-or-assembled-envelope; aperture-zero-shortfall-is-not-overall-approval",
            "bath_window": bath["features"]["window_review"],
            "bath_ritual_simultaneous_scope": "specified-floor-envelope-only-not-family-care-fire-or-crowd-approval",
            "whole_carry": "unknown-stored-body-only-no-people-poles-height-or-rehearsal",
            "rear_access": config["rear_alley"] if option["id"] == "rear-alley" else "not-used-no-rear-door-in-this-version",
            "no_rear_alley_does_not_establish_rear_window_rights": True,
            "care_rescue_door_hardware_and_window_rights": "unknown"}


def cultural_screen(plans: dict) -> dict:
    rooms = {r["key"]: r for r in plans["floors"][0]["rooms"]}
    altar = next(i for i in rooms["shrine"]["furniture"] if i["shape"] == "altar")
    altar_body = body(altar)
    backing = rooms["altar-backing"]
    if (rect(backing) != [2500, 11370, 1820, 1600] or backing["kind"] != "service"
            or any(d["face"] == "front" for d in backing["features"]["doors"])
            or backing["features"]["window_review"]["renderable"]):
        raise ContractError("The altar must retain its unpierced dry backing, not a stair or wet room")
    prohibited = []
    shrine_areas = [rect(rooms[k]) for k in ("shrine-front", "shrine")]
    for floor in plans["floors"][1:]:
        for room in floor["rooms"]:
            if (room["kind"] in {"bath", "kitchen", "stair", "bedroom"}
                    or any(i["shape"] in {"bed", "sofa-bed", "washer"} for i in room["furniture"])):
                if any(_hits(rect(room), area) for area in shrine_areas):
                    prohibited.append(room["id"])
    if prohibited:
        raise ContractError("Inherited upper plan conflicts with the retained strict shrine-use screen")
    return {"scope": "coordinate-family-constraint-screen-not-fengshui-or-religious-approval",
            "street_axis_x_mm": 3400, "altar_center_x_mm": altar_body[0]+altar_body[2]/2,
            "immediate_backing": "solid-dry-cabinet-no-front-opening-not-stair-or-wet-room",
            "shrine_upper_bed_wet_stair_overlaps": prohibited,
            "bath_is_not_directly_on_street_altar_axis": True,
            "backing_finish_margin_deficit_at_115mm": 35,
            "compass_beams_plumbing_noise_and_family_acceptance": "unknown"}

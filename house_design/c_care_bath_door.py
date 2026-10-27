"""Explicit paired sliding leaves and bounded trial routes, never door approval."""
from __future__ import annotations

import math

from house_design.b32_rear_right import body, paired, rect
from house_design.b32_service_detail import _circle_hits, _inside, _route
from house_design.b32_services import _hits
from house_design.c_care_bath import component_box
from house_design.c_care_bath_fit import BASE_REPORT, BASE_VIEWER, STATUS
from house_design.c_care_route import barriers
from house_design.contracts import ContractError

SCHEMA, SOURCE = "house-c-care-bath-door-v1", "inputs/c-care-bath-door.json"
OPTIONS, STATES = ("single-control", "two-panel"), ("open", "half", "closed")
FRACTIONS = {"open": 1, "half": .5, "closed": 0}


def validate_config(cfg):
    if (cfg.get("schema") != SCHEMA or cfg.get("revision") != 1 or cfg.get("status") != STATUS
            or not cfg.get("authorization") or cfg.get("base_report") != BASE_REPORT or cfg.get("base_viewer") != BASE_VIEWER
            or cfg.get("base_option") != "c-bath-refined" or cfg.get("base_state") != "transfer"
            or cfg.get("default_option") != "two-panel" or cfg.get("default_state") != "open"
            or cfg.get("bath_rect_mm") != [3600, 13800, 2400, 3000] or cfg.get("frame_mm") != [6000, 17630]
            or cfg.get("inset_each_face_mm") != 115 or cfg.get("required_clear_mm") != 900
            or cfg.get("nominal_aperture_mm") != 1200 or cfg.get("center_y_mm") != 15025
            or cfg.get("original_center_y_mm") != 14825
            or cfg.get("height_mm") != 2100 or cfg.get("stop_depth_mm") != 20
            or cfg.get("thickness_cases_mm") != [130, 165, 180]
            or set(cfg.get("professional_status", {}).values()) != {"unknown"}):
        raise ContractError("Preserve the frozen room, full opening, care target and unknown approvals")
    expected = {"panel_length_mm": 660, "panel_thickness_mm": 45, "lane_gap_mm": 15, "closed_overlap_mm": 60,
                "pull_projection_mm": 25, "pull_depth_mm": 80, "pull_height_mm": 150, "pull_bottom_mm": 900,
                "turn_reserve_shift_x_mm": 70, "board_trial_shift_x_mm": 50}
    if cfg.get("telescopic") != expected:
        raise ContractError("Changing a door product budget needs a new explicit comparison, never shrink to fit")


def pose(cfg, option, state):
    """One rigid set of leaves, each translated linearly, no independent scaling."""
    if option not in OPTIONS or state not in STATES:
        raise ContractError("Explicit independent door option and use state required")
    t, tc = FRACTIONS[state], cfg["telescopic"]
    start = cfg["bath_rect_mm"][0]+cfg["inset_each_face_mm"]
    if option == "single-control":
        raws, overall = [("bathroom", [start, 14195+1230*t, 95, 1260], 1230)], 95
        park_end = 16685
    else:
        width, gap, length = tc["panel_thickness_mm"], tc["lane_gap_mm"], tc["panel_length_mm"]
        front = cfg["center_y_mm"]-(2*length-tc["closed_overlap_mm"])/2
        raws = [("bathroom-fast", [start+width+gap, front+1260*t, width, length], 1260),
                ("bathroom-slow", [start, front+600+630*t, width, length], 630)]
        overall, park_end = 2*width+gap+tc["pull_projection_mm"], front+1260+length
    leaves = [{"id": key, "state": state, "rect_mm": area, "height_mm": cfg["height_mm"],
               "status": "generic-leaf-envelope-not-selected-product", "counts_as_furniture": False,
               "full_travel_mm": travel, "opening_fraction": t} for key, area, travel in raws]
    parts = [{"id": "bath-door-stop", "label": "20mm止擋／檢修預算（未選品）", "kind": "box",
              "rect_mm": [start, park_end, overall, cfg["stop_depth_mm"]], "bottom_mm": 0, "height_mm": cfg["height_mm"]}]
    if option == "two-panel":
        fast = leaves[0]["rect_mm"]
        parts.append({"id": "bath-door-pull", "label": "主動片25mm把手外凸預算（未選品）", "kind": "box",
            "rect_mm": [fast[0]+fast[2], fast[1]+80, tc["pull_projection_mm"], tc["pull_depth_mm"]],
            "bottom_mm": tc["pull_bottom_mm"], "height_mm": tc["pull_height_mm"]})
    for part in parts:
        part.update(status="generic-accessory-not-selected-product", state=state, counts_as_furniture=False)
    return leaves, parts


def translation_sweeps(cfg, option):
    closed, _ = pose(cfg, option, "closed")
    opened, _ = pose(cfg, option, "open")
    result = []
    for first, last in zip(closed, opened, strict=True):
        a, b = first["rect_mm"], last["rect_mm"]
        result.append({"id": first["id"], "rect_mm": [a[0], a[1], a[2], b[1]+b[3]-a[1]],
                       "method": "exact-union-of-linear-translation-not-angle-sampling"})
    if option == "two-panel":
        a, b = pose(cfg, option, "closed")[1][-1], pose(cfg, option, "open")[1][-1]
        r, end = a["rect_mm"], b["rect_mm"]
        result.append({"id": "bath-door-pull", "rect_mm": [r[0], r[1], r[2], end[1]+end[3]-r[1]],
                       "method": "exact-union-of-linear-translation-not-angle-sampling"})
    return result


def _regions(cfg, bath_cfg, option):
    reserve, circle = bath_cfg["turn_reserve_mm"].copy(), bath_cfg["turn_circle_mm"].copy()
    board = bath_cfg["rescue_trial"]
    points = [p.copy() for p in board["points_mm"]]
    center = board["rotation_center_mm"].copy()
    if option == "two-panel":
        reserve[0] += cfg["telescopic"]["turn_reserve_shift_x_mm"]
        circle[0] += cfg["telescopic"]["turn_reserve_shift_x_mm"]
        for point in points[1:]:
            point[0] += cfg["telescopic"]["board_trial_shift_x_mm"]
        center[0] += cfg["telescopic"]["board_trial_shift_x_mm"]
    diagonal = math.ceil(math.hypot(*board["body_mm"]))
    return reserve, circle, points, [center[0]-diagonal/2, center[1]-diagonal/2, diagonal, diagonal]


def review(plans, cfg, bath_cfg, route_cfg, option, state):
    cells = {r["key"]: r for r in plans["floors"][0]["rooms"]}
    bath = cells["elder-bath"]
    if rect(bath) != cfg["bath_rect_mm"]:
        raise ContractError("Never borrow bedroom or outdoor area for the door study")
    center = cfg["original_center_y_mm"] if option == "single-control" else cfg["center_y_mm"]
    actual = paired(cells, "elder", "elder-bath", "right", center, cfg["nominal_aperture_mm"])
    if actual["operation"] != "sliding":
        raise ContractError("Retain the original sliding-door requirement")
    leaves, parts = pose(cfg, option, state)
    if bath["features"].get("care_entry_leaves") != leaves or bath["features"].get("care_door_parts") != parts:
        raise ContractError("Displayed full door bodies do not follow the specified rigid motions")
    fixed = [{"id": i["id"], "rect_mm": body(i)} for r in cells.values() for i in r["furniture"]
             if i["shape"] != "wall-tv" and not i.get("care_bath_open_shower")]
    hardware = [{"id": c["id"], "rect_mm": component_box(c)[:4]} for c in bath["features"]["care_bath_components"] if not c.get("flush_floor_only")]
    all_leaves = [{"id": leaf["id"], "rect_mm": leaf["rect_mm"]} for r in cells.values() for leaf in r["features"].get("care_entry_leaves", [])]
    auxiliary = [{"id": p["id"], "rect_mm": p["rect_mm"]} for p in parts]
    moving = [{"id": p["id"], "rect_mm": p["rect_mm"]} for p in leaves]+[p for p in auxiliary if p["id"] == "bath-door-pull"]
    floor_obstacles = fixed+hardware+all_leaves+auxiliary
    local_areas = [rect(cells[k]) for k in ("elder", "elder-bath")]
    walls = [w for key in ("elder", "elder-bath") for w in barriers(cells[key])]
    obstacles = floor_obstacles+walls
    def entrance_points(points):
        return [[x, center if y == cfg["original_center_y_mm"] else y] for x, y in points]

    paths = {k: _route(entrance_points(v), *bath_cfg["body_mm"], local_areas, obstacles, 115) for k, v in bath_cfg["routes"].items()}
    helpers = {k: _route(entrance_points(v), *bath_cfg["helper_mm"], local_areas, obstacles, 115) for k, v in bath_cfg["helper_routes"].items()}
    reserve, circle, board_points, board_box = _regions(cfg, bath_cfg, option)
    board_path = _route(board_points, *bath_cfg["rescue_trial"]["body_mm"], local_areas, obstacles, 115)

    def conflicts(area):
        return (["outside-assumed-bath"] if not _inside(area, [rect(bath)], 115) else [])+[
            "hits-"+o["id"] for o in floor_obstacles if _hits(area, o["rect_mm"])]

    turn_issues = conflicts(reserve)+["circle:hits-"+o["id"] for o in floor_obstacles if _circle_hits(circle, o["rect_mm"])]
    translation = translation_sweeps(cfg, option)
    sweep_hits = [s["id"]+":hits-"+o["id"] for s in translation for o in fixed+hardware if _hits(s["rect_mm"], o["rect_mm"])]
    sweep_turns = [s["id"] for s in translation if _hits(s["rect_mm"], reserve)]
    sweep_entry = [s["id"] for s in translation if any(_hits(s["rect_mm"], r) for path in paths.values() for r in path["sweeps_mm"])]
    sweep_stop_hits = [s["id"] for s in translation for p in auxiliary if p["id"] == "bath-door-stop" and _hits(s["rect_mm"], p["rect_mm"])]
    parking = cfg["bath_rect_mm"][1]+cfg["bath_rect_mm"][3]-115-sum(parts[0]["rect_mm"][1::2])
    clear_lo, clear_hi = center-600+115, center+600-115
    spans = sorted((max(clear_lo, p["rect_mm"][1]), min(clear_hi, sum(p["rect_mm"][1::2]))) for p in moving
                   if min(clear_hi, sum(p["rect_mm"][1::2])) > max(clear_lo, p["rect_mm"][1]))
    cursor, apertures = clear_lo, []
    for low, high in spans:
        if low > cursor:
            apertures.append(low-cursor)
        cursor = max(cursor, high)
    apertures.append(max(0, clear_hi-cursor))
    effective = max(apertures)
    # The original two upstream lines are recalculated, never inherited as pass.
    public = [cells[k] for k in route_cfg["public_rooms"]]
    connected = public+[cells[k] for k in route_cfg["private_rooms"]]
    areas = [rect(cells["garage"])]+[rect(r) for r in connected]
    upstream_walls = [w for r in connected for w in barriers(r)]
    operations = []
    for room in public:
        for item in room["furniture"]:
            area = item["placement"].get("operation_mm")
            if area:
                operations.append({"id": item["id"]+"-operation", "rect_mm": [area["minX"], area["minY"], area["maxX"]-area["minX"], area["maxY"]-area["minY"]]})
    stair = cells["stair1f"]["features"]["stair_footprint_mm"]
    upstream_obstacles = floor_obstacles+upstream_walls+operations+[{"id": "unchanged-stair", "rect_mm": [stair[k] for k in ("x_mm", "y_mm", "w_mm", "h_mm")]}]
    upstream = {k: _route(entrance_points(v), 900, 900, areas, upstream_obstacles, 115) for k, v in route_cfg["routes"].items()}
    original_conflicts = [o["id"] for o in moving if _hits(bath_cfg["turn_reserve_mm"], o["rect_mm"])]
    vanity = body(next(i for i in bath["furniture"] if i["shape"] == "vanity"))
    original_open = pose(cfg, "single-control", "open")[0][0]["rect_mm"]
    shifted_single_rear = sum(original_open[1::2])+cfg["center_y_mm"]-cfg["original_center_y_mm"]+cfg["stop_depth_mm"]
    helper_stations = {"toilet-helper": bath_cfg["toilet_helper_mm"], "shower-helper": bath_cfg["shower_helper_mm"]}
    helper_issues = [key+":outside-bath" for key, area in helper_stations.items() if not _inside(area, [rect(bath)], 115)]
    helper_issues += [key+":hits-"+o["id"] for key, area in helper_stations.items() for o in floor_obstacles if _hits(area, o["rect_mm"])]
    result = {"option": option, "state": state, "adopted": False, "professional_acceptance": "unknown",
        "routes": paths, "helper_routes": helpers, "upstream_routes": upstream,
        "helper_stations_mm": helper_stations, "helper_station_failures": helper_issues,
        "turn_reserve_mm": reserve, "turn_circle_mm": circle, "turn_coordinate_failures": turn_issues,
        "toilet_transfer_mm": bath_cfg["toilet_transfer_mm"], "transfer_coordinate_failures": conflicts(bath_cfg["toilet_transfer_mm"]),
        "rescue_board_translation": board_path, "rescue_board_rotation_mm": board_box, "rescue_board_rotation_failures": conflicts(board_box),
        "rescue_scope": bath_cfg["rescue_trial"]["note"], "original_turn_position_door_conflicts": original_conflicts,
        "full_translation_sweeps": translation, "sweep_vs_fixed_conflicts": sweep_hits,
        "current_leaf_vs_fixed_conflicts": [p["id"]+":hits-"+o["id"] for p in moving for o in fixed if _hits(p["rect_mm"], o["rect_mm"])],
        "door_sweep_to_vanity_directional_gap_mm": min(p["rect_mm"][1] for p in translation)-vanity[1]-vanity[3],
        "sweep_vs_stop_conflicts": sweep_stop_hits, "sweep_vs_turn_reserve": sweep_turns,
        "sweep_vs_entry_routes": sweep_entry,
        "operation_requires_empty_sweep": True, "door_opening_nominal_mm": actual["width_mm"], "door_center_y_mm": center,
        "effective_width_assumption_mm": effective, "actual_product_clear_mm": None, "required_clear_mm": 900,
        "rear_parking_after_20mm_stop_mm": parking, "stop_inside_assumed_finish": parking >= 0,
        "single_at_proposed_aperture_rear_spare_mm": sum(cfg["bath_rect_mm"][1::2])-115-shifted_single_rear,
        "selected_product": None, "knee_clearance_credit_mm": 0, "independent_dry_turn_floor": False,
        "old_basin_and_seat_tight_margins_resolved": False,
        "critical_margins_mm": {"entry_to_vanity": paths["toilet-transfer"]["sweeps_mm"][0][1]-vanity[1]-vanity[3],
            "vanity_final_arrival": paths["vanity-front"]["sweeps_mm"][-1][1]-vanity[1]-vanity[3],
            "transfer_to_vanity": bath_cfg["toilet_transfer_mm"][0]-vanity[0]-vanity[2],
            "board_turn_to_folded_seat": component_box(next(c for c in bath["features"]["care_bath_components"] if c["id"] == "fold-seat"))[1]-sum(board_box[1::2])},
        "thickness_sensitivity": [{"total_pack_mm": width, "turn_rect_spare_mm": reserve[0]-(3715+width),
            "board_box_spare_mm": board_box[0]-(3715+width), "scope": "固定標示到總厚度方向預算，非整套商品驗證"} for width in cfg["thickness_cases_mm"]]}
    if option == "two-panel" and (sweep_hits or sweep_stop_hits):
        raise ContractError("Door rigid travel hits a fixed body/stop: "+str(sweep_hits+sweep_stop_hits))
    if option == "single-control" and (not sweep_hits or any(not v.endswith(":vanity") for v in sweep_hits)):
        raise ContractError("Retain the single door's newly identified vanity travel conflict")
    if upstream["arcade-to-bed"]["coordinate_failures"] or turn_issues or helper_issues or result["transfer_coordinate_failures"] or result["rescue_board_rotation_failures"]:
        raise ContractError("Door change lost a specified room reserve or upstream bed route: "+str(result))
    for path in [*paths.values(), *helpers.values(), board_path, upstream["bed-to-bath"]]:
        failures = path["coordinate_failures"]
        if state == "open" and failures or state != "open" and not failures:
            raise ContractError("Independent door route control did not behave as expected: "+str(failures))
        if state != "open" and any("hits-bathroom" not in f and "hits-bath-door-pull" not in f for f in failures):
            raise ContractError("Half/closed state must fail on its actual door, not an unrelated obstacle")
    return result

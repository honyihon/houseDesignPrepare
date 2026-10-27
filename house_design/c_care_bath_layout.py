"""Independent basin/door clearance comparison, not care or product approval.

Only bounded JSON, exact translation rectangles and conservative turn squares.
Read the verified door snapshot without regenerating or writing its sources.
"""
from __future__ import annotations

import copy
import json
import re

from house_design.b32_rear_right import body, rect
from house_design.b32_service_detail import _inside
from house_design.b32_services import _hits
from house_design.c_care_bath import component_box, hardware_sweeps
from house_design.c_care_bath_door import review as door_review
from house_design.c_care_bath_fit import STATUS, _source
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash

SCHEMA, SOURCE = "house-c-care-bath-layout-v1", "inputs/c-care-bath-layout.json"
BASE_REPORT = "structured/candidates/c-care-bath-door/review.json"
BASE_VIEWER = "structured/candidates/c-care-bath-door-3d.html"
OPTIONS, STATES = ("door-control", "side-basin"), ("open", "half", "closed")


def validate_config(cfg):
    expected = {"schema": SCHEMA, "revision": 1, "status": STATUS,
        "base_report": BASE_REPORT, "base_viewer": BASE_VIEWER,
        "base_option": "two-panel", "base_state": "open", "default_option": "side-basin", "default_state": "open",
        "frame_mm": [6000, 17630], "bath_rect_mm": [3600, 13800, 2400, 3000],
        "inset_each_face_mm": 115, "required_clear_mm": 900, "door_center_y_mm": 15175,
        "vanity": {"rect_mm": [3715, 13915, 450, 600], "rotation_deg": 270, "wall_anchor": "left"},
        "vanity_route_mm": [[2650, 14825], [4250, 14825], [4665, 14825], [4665, 14465]],
        "alarm_toilet_shift_x_mm": 200, "board_entry_y_mm": 15115, "board_turn_y_mm": 15620}
    if (any(cfg.get(k) != v for k, v in expected.items()) or not cfg.get("authorization")
            or not cfg.get("limits") or set(cfg.get("professional_status", {}).values()) != {"unknown"}):
        raise ContractError("Preserve the explicit independent comparison, original sizes and unknown approvals")


def frozen_parent(root=ROOT):
    """Verify all frozen source bytes and the model-bearing report's self-hash."""
    report = read_json(root / BASE_REPORT)
    if (report.get("schema") != "house-c-care-bath-door-v1" or report.get("door_display_revision") != 2
            or report.get("status") != STATUS or report.get("adopted") is not False
            or not report.get("source_hashes") or not report.get("report_hash")):
        raise ContractError("Missing frozen door comparison v2")
    for name, digest in report["source_hashes"].items():
        source = _source(root, name)
        if not source.is_file() or sha256_file(source) != digest:
            raise ContractError("Stale frozen door source: "+name)
    raw = re.search(r"^\s*var DATA = (.+);\s*$", (root / BASE_VIEWER).read_text(encoding="utf-8"), re.M)
    if raw is None:
        raise ContractError("Missing frozen door payload")
    payload = json.loads(raw[1]).get("c_care_bath_door", {})
    models = {(o["id"], s["id"]): s["model"] for o in payload.get("options", []) for s in o["states"]}
    reconstructed = copy.deepcopy(report)
    for option in reconstructed["options"]:
        for state in option["states"]:
            try:
                model = models[(option["id"], state["id"])]
            except KeyError as e:
                raise ContractError("Incomplete frozen door option/state") from e
            state["model"] = model
            for floor in state["plans"]["floors"]:
                actual = next(f for f in model["buildings"][0]["floors"] if f["id"] == floor["id"])
                cells = {c["id"]: c for c in actual["cells"] if c["tour_active"]}
                if len(cells) != len(floor["rooms"]):
                    raise ContractError("Frozen door floor is incomplete")
                for room in floor["rooms"]:
                    cell = cells[room["id"]]
                    items = [{**i, "placement": cell["furniture_placements"]["tour_mm"][i["id"]]} for i in cell["furniture"]]
                    if (cell["tour_mm"] != room["geometry"] or cell["tour_features"] != room["features"]
                            or items != room["furniture"]):
                        raise ContractError("Frozen door HTML and 3D disagree")
    if report["report_hash"] != stable_hash({k: v for k, v in reconstructed.items() if k not in {"generated_at", "report_hash"}}):
        raise ContractError("Frozen door report/viewer hash mismatch")
    reference = next(s for o in reconstructed["options"] if o["id"] == "two-panel" for s in o["states"] if s["id"] == "open")
    return report, reference


def trial_configs(cfg, door_cfg, bath_cfg, option):
    if option not in OPTIONS:
        raise ContractError("Unknown independent bath-layout option")
    door, bath = copy.deepcopy(door_cfg), copy.deepcopy(bath_cfg)
    if option == "side-basin":
        door["center_y_mm"] = cfg["door_center_y_mm"]
        bath["fixtures"]["vanity"] = copy.deepcopy(cfg["vanity"])
        bath["routes"]["vanity-front"] = copy.deepcopy(cfg["vanity_route_mm"])
        for point in bath["rescue_trial"]["points_mm"][:2]:
            point[1] = cfg["board_entry_y_mm"]
        bath["rescue_trial"]["points_mm"][-1][1] = cfg["board_turn_y_mm"]
        bath["rescue_trial"]["rotation_center_mm"][1] = cfg["board_turn_y_mm"]
    return door, bath


def _area(bounds):
    return [bounds["minX"], bounds["minY"], bounds["maxX"]-bounds["minX"], bounds["maxY"]-bounds["minY"]]


def review(plans, cfg, door_cfg, bath_cfg, route_cfg, option, state, baseline):
    if option not in OPTIONS or state not in STATES:
        raise ContractError("Explicit bath-layout option and door state required")
    rooms = {r["key"]: r for r in plans["floors"][0]["rooms"]}
    bath = rooms["elder-bath"]
    originals = {r["key"]: r for r in baseline["plans"]["floors"][0]["rooms"]}
    if {k: rect(r) for k, r in rooms.items()} != {k: rect(r) for k, r in originals.items()}:
        raise ContractError("Never enlarge a room or borrow outdoor/bedroom floor")
    for key, room in rooms.items():
        if key != "elder-bath" and room["furniture"] != originals[key]["furniture"]:
            raise ContractError("Do not move furniture outside the private bath")
        for protected in ("window_mm", "window_review", "hvac", "hvac_units", "stair_geometry", "stair_footprint_mm"):
            if room["features"].get(protected) != originals[key]["features"].get(protected):
                raise ContractError("Preserve exterior windows, ventilation and stairs")
        if key not in {"dining", "elder", "elder-bath"} and room != originals[key]:
            raise ContractError("Preserve unrelated rooms, doors and equipment")
    for current, original in zip(plans["floors"][1:], baseline["plans"]["floors"][1:], strict=True):
        a, b = copy.deepcopy(current), copy.deepcopy(original)
        a.pop("plan_file", None)
        b.pop("plan_file", None)
        if a != b:
            raise ContractError("Do not change upper-floor geometry or equipment")
    products = {i["id"].rsplit(":", 1)[-1]: i for i in bath["furniture"]}
    old_items = {i["id"]: i for i in originals["elder-bath"]["furniture"]}
    dimensions = {"toilet": [450, 700, 800], "vanity": [600, 450, 850], "accessible-shower": [1200, 1200, 2000]}
    if set(products) != set(dimensions):
        raise ContractError("Preserve all three full-sized fixtures")
    for key, item in products.items():
        raw, old = bath_cfg["fixtures"][key], old_items[item["id"]]
        x, y, w, d = raw["rect_mm"]
        op = ([x+w, y, 700, d] if raw["wall_anchor"] == "left" else
              [x, y+d, w, 700] if raw["wall_anchor"] == "front" else [x, y-700, w, 700])
        if (body(item) != raw["rect_mm"] or item["placement"]["rotation_deg"] != raw["rotation_deg"]
                or item["placement"]["wall_anchor"] != raw["wall_anchor"]
                or [item[k] for k in ("width_mm", "depth_mm", "height_mm")] != dimensions[key]
                or item["front_clearance_mm"] != 700 or _area(item["placement"]["operation_mm"]) != op
                or item["placement"]["mount_height_mm"] != old["placement"]["mount_height_mm"]
                or key != "vanity" and item != old):
            raise ContractError("Do not shrink fixtures, change height, or erase/reorient the real 700mm operation incorrectly: "+key)
    if not products["vanity"].get("care_bath_wall_hung") or not products["accessible-shower"].get("care_bath_open_shower"):
        raise ContractError("Retain the actual thin wall-hung basin and open step-free shower")
    expected_parts = copy.deepcopy(originals["elder-bath"]["features"]["care_bath_components"])
    if option == "side-basin":
        for part in expected_parts:
            if part["id"] == "alarm-toilet":
                for point in part["points_mm"]:
                    point[0] += cfg["alarm_toilet_shift_x_mm"]
    if bath["features"].get("care_bath_components") != expected_parts:
        raise ContractError("Only the explicit toilet-alarm routing candidate may move; no smaller accessory envelopes")
    result = door_review(plans, door_cfg, bath_cfg, route_cfg, "two-panel", state)
    result.update(option=option, analysis_scope="specified-rectangles-not-centered-seated-reach-or-care-approval")
    for key in ("old_basin_and_seat_tight_margins_resolved", "single_at_proposed_aperture_rear_spare_mm"):
        result.pop(key)
    vanity = body(products["vanity"])
    op = _area(products["vanity"]["placement"]["operation_mm"])
    hardware = [{"id": c["id"], "rect_mm": component_box(c)[:4]} for c in expected_parts if not c.get("flush_floor_only")]
    fixed = [{"id": i["id"], "rect_mm": body(i)} for i in products.values() if i["shape"] != "shower"]
    door_parts = [{"id": p["id"], "rect_mm": p["rect_mm"]} for p in bath["features"]["care_entry_leaves"]+bath["features"]["care_door_parts"]]
    op_hits = [o["id"] for o in fixed+hardware if o["id"] != products["vanity"]["id"] and _hits(op, o["rect_mm"])]
    op_door_hits = [o["id"] for o in door_parts if _hits(op, o["rect_mm"])]
    if not _inside(op, [rect(bath)], 115) or op_hits:
        raise ContractError("Basin's full original operation hits a fixed body/accessory: "+str(op_hits))
    if op_door_hits and (option == "side-basin" or state == "open"):
        raise ContractError("Basin operation unexpectedly blocked by its door: "+str(op_door_hits))
    # Final square may be laterally offset. Report the offset, never turn a
    # positive edge gap into seated tap reach, knee-space or centered-use credit.
    cx, cy = result["routes"]["vanity-front"]["points_mm"][-1]
    arrival = [cx-450, cy-450, 900, 900]
    arrival_issues = ([] if _inside(arrival, [rect(bath)], 115) else ["outside-assumed-bath"])+[
        "hits-"+o["id"] for o in fixed+hardware+door_parts if _hits(arrival, o["rect_mm"])]
    side = option == "side-basin"
    face_gap = arrival[0]-vanity[0]-vanity[2] if side else arrival[1]-vanity[1]-vanity[3]
    lateral = cy-(vanity[1]+vanity[3]/2) if side else cx-(vanity[0]+vanity[2]/2)
    centered = ([arrival[0], vanity[1]+vanity[3]/2-450, 900, 900] if side else
                [vanity[0]+vanity[2]/2-450, arrival[1], 900, 900])
    centered_issues = ([] if _inside(centered, [rect(bath)], 115) else ["outside-assumed-bath"])+[
        "hits-"+o["id"] for o in fixed+hardware+door_parts if _hits(centered, o["rect_mm"])]
    arm = next(h["rect_mm"] for h in hardware if h["id"] == "toilet-arm")
    board = result["rescue_board_rotation_mm"]
    rail = next(h["rect_mm"] for h in hardware if h["id"] == "shower-wall-grab")
    toilet = body(products["toilet"])
    transfer = result["toilet_transfer_mm"]
    overlap = max(0, min(op[0]+op[2], transfer[0]+transfer[2])-max(op[0], transfer[0]))*max(0, min(op[1]+op[3], transfer[1]+transfer[3])-max(op[1], transfer[1]))
    sweeps = hardware_sweeps(bath_cfg)
    sweep_conflicts = [s["id"]+":hits-"+i["id"] for s in sweeps for i in fixed if _hits(s["box_mm"][:4], i["rect_mm"])]
    if sweep_conflicts:
        raise ContractError("Basin relocation conflicts with full-angle fold-seat or arm travel")
    result["critical_margins_mm"]["vanity_final_arrival"] = face_gap
    result.update(vanity_rect_mm=vanity, vanity_operation_mm=op, vanity_operation_fixed_conflicts=op_hits,
        vanity_operation_door_conflicts=op_door_hits,
        basin_arrival_rect_mm=arrival, basin_arrival_coordinate_failures=arrival_issues,
        basin_arrival_facing_axis="-x" if side else "-y",
        basin_arrival_lateral_offset_mm=lateral, centered_basin_arrival_demonstrated=not centered_issues,
        centered_basin_control={"rect_mm": centered, "coordinate_failures": centered_issues,
            "scope": "沿同一面向盆緣距離對齊盆中線的900mm矩形反例，不是重新尋路或真人輪椅"},
        seated_tap_reach="unknown", basin_operation_transfer_overlap_sqm=overlap/1e6,
        simultaneous_basin_and_toilet_transfer=False, hardware_sweeps=sweeps, hardware_sweep_conflicts=sweep_conflicts,
        additional_margins_mm={"basin_arrival_to_front_finish": arrival[1]-(13800+115),
            "basin_arrival_to_raised_arm_y": arrival[1]-arm[1]-arm[3],
            "board_turn_to_toilet_y": board[1]-toilet[1]-toilet[3],
            "board_turn_to_right_rail_x": rail[0]-board[0]-board[2],
            "door_pack_to_turn_reserve": result["turn_reserve_mm"][0]-(3715+130)},
        three_named_coordinate_margins_increased=all(result["critical_margins_mm"][key] > baseline["review"]["door"]["critical_margins_mm"][key]
            for key in ("vanity_final_arrival", "transfer_to_vanity", "board_turn_to_folded_seat")),
        construction_release=False, full_bath_fit_or_care_approval="unknown",
        full_bath_rescue_and_public_caregiver_access="unknown-private-bedroom-access-retained")
    # Simple directional erosion, not a full new path calculation or a
    # statistical tolerance. Retain the small rail/pack gaps as unresolved.
    nominal = {**result["critical_margins_mm"], **result["additional_margins_mm"],
               "parking_after_stop": result["rear_parking_after_20mm_stop_mm"]}
    result["directional_20mm_consumption"] = {"consumption_mm": 20,
        "scope": "每項單獨消耗20mm方向餘量，不是同時公差／新路線／規範",
        "remaining_mm": {key: round(value-20, 3) for key, value in nominal.items()}}
    return result

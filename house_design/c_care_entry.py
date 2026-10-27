"""Local C entry/aperture review, not wheelchair, legal or professional approval.

Only bounded coordinate checks: real-size bodies, paired actual apertures,
specified translations, closed-door negative controls and a turning reserve.
No scene, browser, solver, network, adoption or requirements mutations.
"""
from __future__ import annotations

from house_design.b32_rear_right import aperture_walls, body, paired, rect
from house_design.b32_service_detail import _circle_hits, _inside, _route
from house_design.b32_services import _hits
from house_design.contracts import ContractError

SCHEMA = "house-c-care-entry-v1"
STATUS = "discussion-only-not-adopted"
SOURCE = "inputs/c-care-entry.json"


def validate_config(cfg: dict) -> None:
    if (cfg.get("schema") != SCHEMA or cfg.get("revision") != 1 or cfg.get("status") != STATUS
            or not cfg.get("authorization") or cfg.get("frame_mm") != [6000, 17630]
            or cfg.get("insets_mm") != [80, 100, 115] or cfg.get("care_body_mm") != [900, 900]
            or cfg.get("base_option") != "c-care-refined" or cfg.get("default_option") != "c-entry-refined"
            or cfg.get("leaf_height_mm") != 2100 or cfg.get("bedroom_turn_circle_mm", [None]*3)[2] != 750
            or set(cfg.get("professional_status", {}).values()) != {"unknown"}):
        raise ContractError("Keep the original care target, explicit study scope and unknown approvals")
    for d in cfg["doors"].values():
        if d["operation"] != "sliding" or d["nominal_mm"] != 1200:
            raise ContractError("Retain both 1200mm nominal sliding-door proposals")
        for state in ("open", "closed"):
            if sorted(d[state+"_leaf_mm"][2:]) != [95, 1260]:
                raise ContractError("Do not shrink the actual door-leaf budget")


def review(plans: dict, cfg: dict, state: str, required_clear_mm: int) -> dict:
    if required_clear_mm != 900 or state not in {"open", "closed"}:
        raise ContractError("The original 900mm care target and explicit door state are required")
    cells = {r["key"]: r for r in plans["floors"][0]["rooms"]}
    areas = [rect(cells[k]) for k in ("sliding-door", "sideyard", "elder", "elder-bath")]
    products = [{"id": i["id"], "rect_mm": body(i)} for r in cells.values() for i in r["furniture"] if i["shape"] != "wall-tv"]
    stair = cells["stair1f"]["features"]["stair_footprint_mm"]
    fixed = products+[{"id": "unchanged-stair-footprint", "rect_mm": [stair[k] for k in ("x_mm", "y_mm", "w_mm", "h_mm")]}]
    door_rows, walls, panels = [], [], []
    for key, d in cfg["doors"].items():
        actual = paired(cells, d["a"], d["b"], d["face"], d["center_mm"], d["nominal_mm"])
        if actual["operation"] != "sliding":
            raise ContractError("Both actual paired apertures must describe sliding doors")
        panel = {"id": key+"-"+state+"-leaf", "rect_mm": d[state+"_leaf_mm"]}
        leaves = [leaf for r in cells.values() for leaf in r["features"].get("care_entry_leaves", []) if leaf["id"] == key]
        if (len(leaves) != 1 or leaves[0]["state"] != state or leaves[0]["rect_mm"] != panel["rect_mm"]
                or leaves[0]["height_mm"] != cfg["leaf_height_mm"] or leaves[0]["counts_as_furniture"] is not False
                or leaves[0] not in cells[d["park_owner"]]["features"].get("care_entry_leaves", [])):
            raise ContractError("Actual displayed door leaf differs from the reviewed state: "+key)
        panels.append(panel)
        for rkey in (d["a"], d["b"]):
            opening = next(o for o in cells[rkey]["features"]["doors"] if o["neighbor"] == cells[d["b"] if rkey == d["a"] else d["a"]]["id"])
            walls += aperture_walls(cells[rkey], opening, 115, key+"-"+rkey+"-jamb-")
        owner_areas = [rect(cells[k]) for k in (("sideyard",) if key == "bedroom" else ("elder-bath",))]
        if not _inside(d["open_leaf_mm"], owner_areas, 115):
            raise ContractError("Open leaf leaves its actual allocated parking wall: "+key)
        if any(_hits(d["open_leaf_mm"], o["rect_mm"]) for o in fixed):
            raise ContractError("Open leaf intersects a real fixed product or stair: "+key)
        door_rows.append({"id": key, "room": cells[d["a"]]["id"], "neighbor": cells[d["b"]]["id"],
            "nominal_mm": actual["width_mm"], "operation": actual["operation"], "center_mm": d["center_mm"],
            "sensitivity": [{"inset_each_side_mm": i, "clear_assumption_mm": actual["width_mm"]-2*i,
                             "target_mm": required_clear_mm, "shortfall_mm": max(0, required_clear_mm-(actual["width_mm"]-2*i))} for i in cfg["insets_mm"]],
            "open_leaf_mm": d["open_leaf_mm"], "closed_leaf_mm": d["closed_leaf_mm"], "height_mm": cfg["leaf_height_mm"],
            "selected_product": None, "actual_finished_clear_threshold_and_rescue": "unknown"})
    # Fixed apertures are always checked, even in the fully-open state. A room
    # adjacency graph or route passing through a solid/closed wall is not proof.
    routes = {key: _route(points, *cfg["care_body_mm"], areas, fixed+walls+panels, 115) for key, points in cfg["routes"].items()}
    cx, cy, radius = cfg["bedroom_turn_circle_mm"]
    turn = [cx-radius, cy-radius, 2*radius, 2*radius]
    issues = [] if _inside(turn, [rect(cells["elder"])], 115) else ["turn-square:outside-bedroom"]
    issues += ["turn-circle:hits-"+p["id"] for p in fixed+panels if _circle_hits([cx, cy, radius], p["rect_mm"])]
    bed = next(i for i in cells["elder"]["furniture"] if i["shape"] == "bed")
    b = body(bed)
    entry = cfg["doors"]["bedroom"]
    door_span = [entry["center_mm"]-entry["nominal_mm"]/2, entry["center_mm"]+entry["nominal_mm"]/2]
    aligns_bed = min(door_span[1], b[0]+b[2]) > max(door_span[0], b[0])
    if issues or aligns_bed:
        raise ContractError("Do not solve door width by losing the bedroom turn reserve or facing the bed")
    if state == "open" and any(r["coordinate_failures"] for r in routes.values()):
        raise ContractError("Specified open-door care-body route is blocked: "+str({k: r["coordinate_failures"] for k, r in routes.items()}))
    if state == "closed" and any(not r["coordinate_failures"] for r in routes.values()):
        raise ContractError("Every closed-door negative control must block its intended path")
    upstream = []
    for key, neighbor in (("dining", None), ("sliding-door", cells["living-hall"]["id"])):
        opening = next(o for o in cells[key]["features"]["doors"] if o["neighbor"] == neighbor)
        clear = opening["width_mm"]-230
        upstream.append({"room": cells[key]["id"], "neighbor": neighbor, "nominal_mm": opening["width_mm"],
                         "clear_assumption_at_115mm": clear, "original_target_mm": required_clear_mm,
                         "shortfall_at_115mm": max(0, required_clear_mm-clear), "actual_clear_and_whole_route": "unknown"})
    return {"doors": door_rows, "state": state, "routes": routes, "body_mm": cfg["care_body_mm"],
        "bedroom_turn_circle_mm": [cx, cy, radius], "turn_coordinate_failures": issues,
        "entry_projects_onto_bed_body": aligns_bed, "hall_separate_finished_depth_at_115mm": rect(cells["sideyard"])[3]-230,
        "upstream_door_budgets": upstream,
        "independent_hall_1500mm_turn": "not-demonstrated-30mm-short-in-isolation",
        "route_scope": "stair-side-corridor-to-bed-and-private-bath-only-not-street-to-bed-or-actual-wheelchair-kinematics",
        "bed_bath_private_access_and_family_acceptance": "unknown-original-public-care-access-preference-not-satisfied",
        "full_bathroom_turn_transfer_and_rescue": "unknown-not-approved", "adopted": False, "professional_acceptance": "unknown"}

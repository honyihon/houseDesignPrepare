"""Small use-state screens on B32 plan JSON; no model/scene build or approval.

An empty list only describes explicit rectangles. Public access, family rules,
ventilation performance and whole-body transport are not inferred from it.
"""
from __future__ import annotations

import copy

from house_design.b32_service_detail import _inside, _route
from house_design.b32_services import _covered, _hits
from house_design.contracts import ContractError
from house_design.requirement_reconciliation import discussion_area

KEYS = ("x_mm", "y_mm", "w_mm", "h_mm")


def _rect(room: dict) -> list:
    return [room["geometry"][k] for k in KEYS]


def _xy(aabb: dict) -> list:
    return [aabb["minX"], aabb["minY"], aabb["maxX"]-aabb["minX"], aabb["maxY"]-aabb["minY"]]


def subtract_rect(rect: list, cut: list) -> list[list]:
    """Exact disjoint rectangle subtraction, never double-count a corridor."""
    x, y, w, h = rect
    cx, cy, cw, ch = cut
    x0, y0, x1, y1 = max(x, cx), max(y, cy), min(x+w, cx+cw), min(y+h, cy+ch)
    if x1 <= x0 or y1 <= y0:
        return [rect.copy()]
    return [r for r in ([x, y, w, y0-y], [x, y1, w, y+h-y1], [x, y0, x0-x, y1-y0], [x1, y0, x+w-x1, y1-y0]) if r[2] and r[3]]


def review_daily_use(plans: dict, settings: dict, prior: dict, insets: list, seated_benches: list) -> dict:
    if settings.get("status") != "comparison-only-not-adopted" or not settings.get("authorization"):
        raise ContractError("Daily service is authorized research only, not adoption")
    rooms = {r["key"]: r for r in plans["floors"][0]["rooms"]}
    laundry = [_rect(rooms[k]) for k in ("laundry-front", "laundry-base")]
    allowed = laundry+[_rect(rooms["dry-route"])]
    if settings["laundry_access_body_mm"] != [700, 700]:
        raise ContractError("Retain the explicitly limited local laundry discussion body")
    if any(not isinstance(v, str) or not v.startswith("unknown") for v in settings["mechanical_requirements"].values()):
        raise ContractError("Equipment envelopes may not grant ventilation or drying approval")
    rack = next(i for i in rooms["laundry-base"]["furniture"] if i["catalog_id"] == settings["drying_rack"]["catalog_id"])
    dehum = next(i for i in rooms["laundry-base"]["furniture"] if i["catalog_id"] == "dehumidifier")
    obstacles = [{"id": i["id"], "rect_mm": _xy(i["placement"]["aabb"])} for r in rooms.values() for i in r["furniture"]]
    service = settings["dehumidifier"]["assumed_service_each_side_mm"]
    dx, dy, dw, dh = _xy(dehum["placement"]["aabb"])
    dehum_service = [dx-service, dy-service, dw+service*2, dh+service*2]
    operation = settings["drying_rack"]["front_operation_rect_mm"]
    actual_rack = _xy(rack["placement"]["aabb"])
    if operation[2:] != [1200, 700]:
        raise ContractError("Retain the full 1200x700mm small-rack loading discussion band")
    if actual_rack != settings["drying_rack"]["rect_mm"]:
        raise ContractError("Daily study must use the rendered occupied drying envelope")
    rack_op = rack["placement"]["operation_mm"]
    if not rack_op or _xy(rack_op) != operation:
        raise ContractError("Daily drying operation must match the same-source furniture placement")
    rows = []
    for inset in insets:
        failures = []
        for name, rect in (("occupied-drying-rack", actual_rack), ("drying-loading", operation), ("dehumidifier-service", dehum_service)):
            if not _inside(rect, laundry, inset):
                failures.append(name+":outside-private-laundry")
            for o in obstacles:
                if o["id"] not in {rack["id"], dehum["id"]} and _hits(rect, o["rect_mm"]):
                    failures.append(name+":hits-"+o["id"])
        if _hits(operation, [dx, dy, dw, dh]) or _hits(dehum_service, actual_rack):
            failures.append("drying-operation-or-service:hits-other-new-body")
        retained = prior["bath_route_sensitivity"][insets.index(inset)]
        # Re-screen retained original 900x800 laundry working bands against new
        # bodies; a passing check from an empty bay cannot be inherited.
        for r in rooms.values():
            for z in r["features"]["reserved_mm"]:
                if z["kind"].startswith("b-daily-existing-"):
                    rect = _xy(z["aabb"])
                    for o in obstacles:
                        if o["id"] in {rack["id"], dehum["id"]} and _hits(rect, o["rect_mm"]):
                            failures.append(z["kind"]+":hits-"+o["id"])
        local = _route(settings["laundry_access_points_mm"], *settings["laundry_access_body_mm"], allowed, obstacles, inset)
        # Retained bathroom route is conditional already. Add real seated bench
        # envelopes rather than using daily parked benches during a ceremony.
        base_route = retained["bath_entry_route"]
        ceremony_issues = list(retained["arrival_during_ritual"]["coordinate_failures"])
        ceremony_issues += [f"segment-{n}:hits-{bench['id']}" for n, sweep in enumerate(base_route["sweeps_mm"])
                            for bench in seated_benches if _hits(sweep, bench["rect_mm"])]
        rows.append({"inset_mm": inset, "equipment_and_operation_failures": failures,
                     "local_loading_700mm_body_route": local,
                     "ceremony_bath_access_failures": sorted(set(ceremony_issues)),
                     "ceremony_bath_access_status": "blocked-do-not-treat-pause-or-upstairs-as-accessible-substitute"})
    # A new independent cross-hall would have to be removed from private
    # laundry. This is an explicit rejected local alteration, not a proof that
    # no other whole-floor redesign can work.
    corridor = settings["cross_corridor_rect_mm"]
    if not _covered(corridor, laundry):
        raise ContractError("Cross-hall cost must be carved from the actual laundry union")
    remaining = [part for r in laundry for part in subtract_rect(r, corridor)]
    area = next(r for r in prior["area_rows"] if r["zone"] == "laundry")
    reduced = [{"inset_mm": i, "area_sqm": discussion_area([{"geometry": dict(zip(KEYS, r, strict=True))} for r in remaining], i)} for i in insets]
    rack_count = sum(i["catalog_id"] == settings["drying_rack"]["catalog_id"] for f in plans["floors"] for r in f["rooms"] for i in r["furniture"])
    machines = [{"id": i["id"], "floor": f["id"], "catalog": i["catalog_id"]} for f in plans["floors"] for r in f["rooms"] for i in r["furniture"] if i["catalog_id"] in {"washer", "dryer"}]
    return {"status": "comparison-only-not-adopted", "local_scope": "700mm-loading-body-not-public-care-or-fire-approval",
            "sensitivity": rows, "equipment": {"rack_count": rack_count, "laundry_machines": machines,
                "drying_body_mm": actual_rack, "drying_operation_mm": operation, "dehumidifier_service_mm": dehum_service,
                "drying_capacity_and_clothes_protrusion": "unknown-new-small-envelope-not-shrunk-existing-rack"},
            "cross_corridor": {"rect_mm": corridor, "nominal_area_taken_sqm": round(corridor[2]*corridor[3]/1e6, 4),
                "remaining_laundry_rects_mm": remaining, "remaining_laundry_area_sensitivity": reduced,
                "original_minimum_sqm": area["original_minimum_sqm"], "original_target_sqm": area["original_target_sqm"],
                "corridor_clear_assumption_mm": [{"inset_mm": i, "clear_mm": corridor[3]-2*i} for i in insets],
                "position": "reject-this-local-cut-laundry-below-original-minimum-no-target-reduction",
                "new_doors_hardware_and_complete_route": "not-designed-no-through-route-claim"},
            "next_recommendation": {"strategy": "compare-rear-right-bath-and-rear-left-storage-before-adoption",
                "status": "owner-direction-required-not-drawn-or-adopted",
                "reason": "從街門前段先轉右側，再沿既有側緣到有窗公衛，避開神桌前的祭祀帶；但必須重排後門與完整前門搬運備案。",
                "front_backup": "retain-v6-independent-front-option-no-carry-result-borrowed",
                "scope": "new-room-and-door-layout-needs-owner-direction-not-a-small-door-fix",
                "left_front_lane_nominal_mm_if_only_rooms_swapped": rooms["dry-route"]["geometry"]["w_mm"],
                "left_front_lane_clear_115mm_if_only_rooms_swapped": rooms["dry-route"]["geometry"]["w_mm"]-230,
                "unassembled_body_width_mm": prior["carry_body_115mm"]["body_mm"][0],
                "simple_swap_front_carry_status": "not-accommodated-left-lane-narrower-than-1200mm-body-before-benches-and-doors",
                "rear_access_rights": "unknown-no-rear-alley-assumed"},
            "mechanical_requirements": copy.deepcopy(settings["mechanical_requirements"]),
            "professional_approval": "unknown", "original_work_balcony": "unmet-indoor-drying-is-not-outdoor-balcony",
            "no_new_public_path_through_laundry_or_storage": True}

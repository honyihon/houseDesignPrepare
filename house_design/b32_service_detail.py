"""Isolated compact-service detailing: real-size bodies, not design approval.

No scene runtime, renderer, JS execution, network, measurement or adoption writes.
Routes are specified orthogonal translations of discussion rectangles; they do
not prove wheelchair kinematics, door operation, human rescue or assembled carry.
"""

from __future__ import annotations

import math
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from house_design.b32_services import SOURCE as SERVICE_SOURCE
from house_design.b32_services import _box, _covered, _from_room, _hits, _translation, build_service_study
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, utc_now, write_json
from house_design.requirement_reconciliation import _public_path, _snapshot

SOURCE = "inputs/b32-service-detail.json"
WARNING = "未採用的B32設備／分時座位研究，不改ABC或原B32 HTML／3D。矩形／轉位檢查不是無障礙、救援、消防、風水或搬轎核可；原拉門與收納目標保留。"


def _expand(rect: list, inset: float) -> list:
    x, y, w, d = rect
    return [x-inset, y-inset, w+2*inset, d+2*inset]


def _inside(rect: list, areas: list[list], inset: float) -> bool:
    return _covered(_expand(rect, inset), areas)


def _circle_hits(circle: list, rect: list) -> bool:
    cx, cy, radius = circle
    x0, y0, x1, y1 = _box(rect)
    return math.hypot(cx-max(x0, min(cx, x1)), cy-max(y0, min(cy, y1))) < radius


def _item(raw: dict, catalog: dict, *, generic: dict | None = None) -> dict:
    product = catalog[raw["catalog"]] if raw.get("catalog") else generic
    if product is None or raw.get("rotation_deg") not in {0, 90}:
        raise ContractError("A catalog or explicit generic item and orthogonal rotation are required")
    _box(raw["rect_mm"])
    dims = [product["width_mm"], product["depth_mm"]]
    if raw["rotation_deg"] == 90:
        dims.reverse()
    if raw["rect_mm"][2:] != dims:
        raise ContractError("Products may not be scaled or silently folded to create a fit")
    return {**raw, "height_mm": product["height_mm"], "label": product.get("label", "一般暫估洗槽")}


def _route(points: list[list], width: float, depth: float, areas: list[list], obstacles: list[dict], inset: int) -> dict:
    if len(points) < 2:
        raise ContractError("Route needs at least two points")
    sweeps, failures = [], []
    for index, (a, b) in enumerate(zip(points, points[1:], strict=False)):
        if a[0] != b[0] and a[1] != b[1]:
            raise ContractError("Only explicit orthogonal translation is supported, never a diagonal shortcut")
        sweep = _translation(a, b, width, depth)
        sweeps.append(sweep)
        if not _inside(sweep, areas, inset):
            failures.append(f"segment-{index}:outside-assumed-floor")
        failures += [f"segment-{index}:hits-{o['id']}" for o in obstacles if _hits(sweep, o["rect_mm"])]
    return {"points_mm": points, "body_mm": [width, depth], "sweeps_mm": sweeps,
            "coordinate_failures": failures, "door_hardware_threshold_people_and_real_motion": "unknown"}


def _objects_clear(items: list[dict], operations: list[dict], areas: list[list], inset: int) -> list[str]:
    failures = []
    for index, item in enumerate(items):
        if not _inside(item["rect_mm"], areas, inset):
            failures.append(item["id"]+":outside-assumed-floor")
        failures += [item["id"]+":hits-"+o["id"] for o in items[index+1:] if _hits(item["rect_mm"], o["rect_mm"])]
    # A step-free shower is shared floor only as an explicitly unapproved proposal.
    solid = [i for i in items if not i.get("shared_step_free_floor_proposal")]
    for op in operations:
        if not _inside(op["rect_mm"], areas, inset):
            failures.append(op["id"]+":outside-assumed-floor")
        failures += [op["id"]+":hits-"+i["id"] for i in solid if _hits(op["rect_mm"], i["rect_mm"])]
    return failures


def _shrine_mode(rooms: dict, cfg: dict, catalog: dict, mode: str) -> dict:
    originals = {i["id"].rsplit(":", 1)[-1]: i for i in rooms["shrine"]["furniture"]}

    def existing(key):
        a = originals[key]["placement"]["aabb"]
        return {"id": key, "rect_mm": [a["minX"], a["minY"], a["maxX"]-a["minX"], a["maxY"]-a["minY"]],
                "catalog": originals[key]["catalog_id"], "rotation_deg": 0}

    altar, offering = _item(existing("altar"), catalog), _item(existing("offering"), catalog)
    if altar["rect_mm"] != [2500, 10690, 1800, 600]:
        raise ContractError("New altar geometry needs a new detailing review, never silent relocation")
    original_offering = offering["rect_mm"].copy()
    if mode != "original-table-control":
        offering["rect_mm"][1] += cfg["offering_rear_shift_mm"]
    parked = mode != "ritual-seated"
    raw_benches = cfg["daily_park_benches" if parked else "ritual_seated_benches"]
    if ({i["id"] for i in raw_benches} != {"bench-1", "bench-2"} or len(raw_benches) != 2
            or any(i["catalog"] != "movable-bench" for i in raw_benches)):
        raise ContractError("Both full-size benches must be retained in every mode")
    benches = [_item(i, catalog) for i in raw_benches]
    operations = [{"id": i["id"]+":seated", "rect_mm": i["seated_operation_mm"]} for i in benches if not parked]
    if any(op["rect_mm"][2:] != [600, 1400] for op in operations):
        raise ContractError("Retain the explicit 600mm seated-operation discussion depth")
    reserves = []
    for key in ("shrine-front", "shrine"):
        for r in rooms[key]["features"]["fixed_reserved_mm"]:
            a = r["aabb"]
            reserves.append({"id": r["kind"], "rect_mm": [a["minX"], a["minY"], a["maxX"]-a["minX"], a["maxY"]-a["minY"]]})
    protected_failures = [i["id"]+":hits-"+r["id"] for i in [offering, *benches, *operations]
                          for r in reserves if _hits(i["rect_mm"], r["rect_mm"])]
    return {"id": mode, "items": [altar, offering, *benches], "seated_operations": operations,
            "original_offering_mm": original_offering,
            "offering_rear_shift_mm": offering["rect_mm"][1]-original_offering[1],
            "offering_to_altar_gap_mm": altar["rect_mm"][1]-sum(offering["rect_mm"][1::2]),
            "parked_benches_are_seats": False, "benches_in_seated_use": not parked,
            "reserved_zones": reserves, "protected_reserve_failures": protected_failures,
            "daily_laundry_allowed": parked and mode != "original-table-control",
            "simultaneous_ritual_laundry_carry": False, "bench_reposition_and_capacity": "unknown"}


def _door_review(cfg: dict, rooms: dict, zones: dict, inset: int, requirement: dict) -> dict:
    nominal, cy = cfg["entry_nominal_mm"], cfg["entry_center_y_mm"]
    top, bottom = cy-nominal/2, cy+nominal/2
    corridor = zones["public-carry-passage"][0]
    opening_in_shared_wall = top >= 12970+inset and bottom <= corridor[1]+corridor[3]-inset
    dry_door = rooms["altar-backing"]["features"]["doors"][0]
    dry_rect = _from_room(rooms["altar-backing"])
    dry_cy = dry_rect[1]+dry_rect[3]*dry_door["ratio"]
    dry_span = [dry_cy-dry_door["width_mm"]/2, dry_cy+dry_door["width_mm"]/2]
    north_slide_span = [top-nominal, top]
    slide_overlap = min(north_slide_span[1], dry_span[1]) > max(north_slide_span[0], dry_span[0])
    c = cfg["door_comparisons"]
    clear, hall_clear = nominal-2*inset, corridor[2]-2*inset
    double_remaining = hall_clear-c["double_outward_leaf_each_mm"]-c["assumed_leaf_thickness_mm"]
    return {"opening_nominal_mm": nominal, "opening_center_y_mm": cy, "opening_inside_shared_wall": opening_in_shared_wall,
            "assumed_clear_mm": clear, "original_required_clear_mm": requirement["door_clear_mm"],
            "clear_width_target_met_by_assumption": clear >= requirement["door_clear_mm"],
            "original_door_swing": requirement["door_swing"], "sliding_requirement_satisfied": False,
            "north_surface_slide_span_y_mm": north_slide_span, "existing_dry_door_span_y_mm": dry_span,
            "north_surface_slide_crosses_dry_access": slide_overlap,
            "south_surface_slide_crosses_storage_threshold": bottom < 14330 < bottom+nominal,
            "assumed_corridor_clear_mm": hall_clear,
            "single_outward_remaining_mm": hall_clear-c["single_outward_leaf_mm"]-c["assumed_leaf_thickness_mm"],
            "double_outward_remaining_mm": double_remaining,
            "double_outward_margin_over_900mm": double_remaining-900,
            "comparison_leaf_sizes_mm": {k: c[k] for k in
                                         ("single_outward_leaf_mm", "double_outward_leaf_each_mm", "assumed_leaf_thickness_mm")},
            "double_outward_satisfies_original_sliding": False,
            "carry_when_door_open": "not-assumed-must-stop", "selected_product": None,
            "rescue_hardware_fire_and_emergency_operation": "unknown", "adoptable": False}


def _bathroom(cfg: dict, rooms: dict, zones: dict, catalog: dict, inset: int, shrine: dict, care: list, requirement: dict) -> dict:
    items = [_item(i, catalog) for i in cfg["fixtures"]]
    if ({i["id"]: i["catalog"] for i in items} != {"shower": "shower-accessible", "toilet": "toilet", "basin": "vanity-60"}
            or len(items) != 3 or any(i.get("shared_step_free_floor_proposal") for i in items if i["id"] != "shower")):
        raise ContractError("Keep the shower, toilet and basin as independent unscaled fixtures")
    if ({o["id"]: o["rect_mm"][2:] for o in cfg["operations"]} != {
            "toilet-front": [450, 800], "toilet-side-transfer": [900, 1200], "basin-front": [900, 800]}
            or len(cfg["operations"]) != 3):
        raise ContractError("Do not shrink or omit the independent transfer and operation envelopes")
    solid = [i for i in items if not i.get("shared_step_free_floor_proposal")]
    circle = cfg["turn_circle_mm"]
    if (len(circle) != 3 or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in circle)
            or circle[2] != 750):
        raise ContractError("Retain a finite 1500mm discussion turning circle, never scale to fit")
    cx, cy, radius = circle
    reserve = [cx-radius, cy-radius, radius*2, radius*2]
    circle_failures = [] if _inside(reserve, zones["bathroom"], inset) else ["turn-square:outside-assumed-floor"]
    circle_failures += ["turn-circle:hits-"+i["id"] for i in solid if _circle_hits(circle, i["rect_mm"])]
    allowed = [_from_room(rooms[k]) for k in ("shrine-front", "shrine")]+zones["public-carry-passage"]+zones["bathroom"]
    start = [3400, 3900+inset+care[1]/2]
    entry = [2455, cfg["entry_center_y_mm"]]
    # Turn onto the shrine edge before the reserved 5700mm praying band;
    # the front-carry route, separately, remains a time-separated operation.
    routes = {"street-interior-to-bath": [start, [3400, 5000], [5160, 5000], [5160, entry[1]], entry],
              "basin": [entry, [1810, entry[1]], [1810, 12400]],
              "toilet-side": [entry, [3305, entry[1]], [3305, 14065]],
              "shower": [entry, [1855, entry[1]], [1855, 14215]]}
    results = {name: _route(points, *care, allowed, shrine["items"]+solid, inset) for name, points in routes.items()}
    fallen = cfg["fallen_body_example_mm"]
    return {"fixtures": items, "operations": cfg["operations"], "turn_circle_mm": circle,
            "fixture_operation_failures": _objects_clear(items, cfg["operations"], zones["bathroom"], inset),
            "turn_coordinate_failures": circle_failures,
            "turn_shares_shower_floor": any(i.get("shared_step_free_floor_proposal") and _circle_hits(circle, i["rect_mm"]) for i in items),
            "turn_shared_floor_conditions": "zero-threshold-removable-curtain-no-fixed-screen-rails-slope-unverified",
            "routes": results, "door": _door_review(cfg, rooms, zones, inset, requirement),
            "fallen_body_example_mm": fallen,
            "fallen_body_blocks_normal_entry": any(_hits(fallen, r) for r in results["street-interior-to-bath"]["sweeps_mm"]),
            "rescue_approval": "unknown-no-human-rehearsal", "knee_space_rails_waterproofing_ventilation": "unknown",
            "assumed_fixture_layout_only": True, "adopted": False}


def build_service_detail(root: Path = ROOT) -> dict:
    cfg, service = read_json(root / SOURCE), read_json(root / SERVICE_SOURCE)
    if (cfg.get("schema") != "house-b32-service-detail-v1" or cfg.get("status") != "comparison-only-not-adopted"
            or cfg.get("service_settings") != SERVICE_SOURCE or cfg.get("service_option") != "compact-service"
            or cfg.get("owner_authorization") != "continue-detail-research-only-not-layout-or-target-approval"
            or cfg.get("care_body_mm") != [900, 900] or set(cfg["gates"].values()) != {"unknown"}
            or cfg["bathroom"]["door_comparisons"]["original_sliding_requirement"] != "retained-unresolved"):
        raise ContractError("Detail study is research only; retain original targets and unknown approvals")
    base = build_service_study(root)
    snapshot = _snapshot(_public_path(root, service["source"]), "HOUSE_B32_ENTRY_OPTIONS", "house-b32-entry-options-v1")
    catalog = read_json(root / "inputs/furniture-layout.json")["catalog"]
    requirements = {r["id"]: r for r in read_json(root / "inputs/requirements.json")["requirements"]}
    bath_req, carry_req = (requirements[k]["constraints"] for k in ("B.floor-1.bath_acc", "B.floor-1.palanquin"))
    laundry = [_item(i, catalog, generic=service["common"]["utility_sink"]) for i in cfg["laundry"]["items"]]
    if ({i["id"]: i["catalog"] for i in laundry} != {"washer": "washer", "utility-sink": None} or len(laundry) != 2):
        raise ContractError("Retain the full-size washer and utility sink")
    cases = []
    for source in snapshot["options"]:
        if source.get("entry_mode") != {"b32-rear": "rear", "b32-front": "front"}.get(source["id"]):
            raise ContractError("Rear priority and front fallback must keep their own entry modes")
        partition = next(c for c in base["cases"] if c["base_option"] == source["id"] and c["service_option"] == cfg["service_option"])
        rooms = {r["key"]: r for f in source["plans"]["floors"] if f["id"] == "floor-1" for r in f["rooms"]}
        if any(_from_room(rooms[k]) != r for k, r in {
                "stair1": [0, 3900, 2400, 5200], "shrine-front": [2400, 3900, 3600, 5200],
                "shrine": [0, 9100, 6000, 2270]}.items()):
            raise ContractError("Changed front rooms need a new full-route review")
        ritual_door = next(d for d in rooms["shrine-front"]["features"]["doors"] if d.get("purpose") == "ritual-entry")
        if (ritual_door["face"] != "front" or ritual_door["width_mm"] != 1800 or ritual_door.get("neighbor") is not None
                or not math.isclose(2400+3600*ritual_door["ratio"], 3400, abs_tol=0.01)):
            raise ContractError("Keep the original axial street-facing ritual door")
        zones = partition["zones_mm"]
        shrine_areas = [_from_room(rooms[k]) for k in ("shrine-front", "shrine")]
        modes = [_shrine_mode(rooms, cfg["shrine"], catalog, m) for m in ("original-table-control", "daily-clear", "ritual-seated")]
        sensitivity = []
        for inset in service["insets_mm"]:
            passage = zones["public-housework-passage"][0]
            width = passage[2]-2*inset
            cross_y = 9100+inset+width/2
            start = [3400, 3900+inset+width/2]
            points = [start, [3400, cross_y], [passage[2]/2, cross_y], [passage[2]/2, 15875], [1430, 15875], [1430, 16365]]
            allowed = shrine_areas+zones["public-housework-passage"]+zones["laundry"]
            mode_rows = []
            for mode in modes:
                route = _route(points, width, width, allowed, mode["items"]+laundry+mode["seated_operations"], inset)
                # Includes a second branch to the washer, not just a room-adjacency graph.
                route["washer_branch"] = _route([[1430, 15875], [700, 15875], [700, 16365]], width, width,
                                                allowed, mode["items"]+laundry+mode["seated_operations"], inset)
                mode_rows.append({"mode": mode["id"], "laundry_route": route,
                                  "shrine_object_operation_failures": _objects_clear(mode["items"], mode["seated_operations"], shrine_areas, inset)})
            bath = _bathroom(cfg["bathroom"], rooms, zones, catalog, inset, modes[1], cfg["care_body_mm"], bath_req)
            body = partition["palanquin_body_mm"]
            center, w, d = [body[0]+body[2]/2, body[1]+body[3]/2], body[2], body[3]
            if source["entry_mode"] == "rear":
                carry_points = [[source.get("rear_gate_center_mm", 4500), 17630-inset-d/2],
                                [source.get("rear_gate_center_mm", 4500), center[1]], center]
                carry_areas = zones["storage"]
            else:
                carry_points = [[3400, 3900+inset+d/2], [3400, 6550], [center[0], 6550], center]
                carry_areas = shrine_areas+zones["public-carry-passage"]+zones["storage"]
            carry = _route(carry_points, w, d, carry_areas, modes[1]["items"]+laundry, inset)
            budgets = [{**g, "discussion_clear_mm": g["nominal_mm"]-2*inset, "assumed_frame_each_side_mm": inset}
                       for g in partition["transport"]["gate_budgets"]]
            carry.update(entry_mode=source["entry_mode"], scope="each-options-own-indoor-body-route-no-yaw-no-poles-people-or-threshold",
                         gate_budgets=budgets, body_gate_failures=[g["room_id"] for g in budgets if g["discussion_clear_mm"] < w],
                         original_gate_target_mm=carry_req["door_clear_mm"],
                         original_gate_target_failures=[g["room_id"] for g in budgets if g["discussion_clear_mm"] < carry_req["door_clear_mm"]],
                         continuous_1500mm_requirement="unverified-not-body-packing", assembly_and_outdoor_access="unknown")
            sensitivity.append({"inset_mm": inset, "housework_body_width_mm": width, "modes": mode_rows,
                                "bathroom": bath, "carry": carry,
                                "laundry_object_operation_failures": _objects_clear(laundry, cfg["laundry"]["operations"], zones["laundry"], inset)})
        cases.append({"id": source["id"], "entry_mode": source["entry_mode"], "zones_mm": zones,
                      "unchanged_front_rooms_mm": {k: _from_room(rooms[k]) for k in ("stair1", "shrine-front", "shrine")},
                      "ritual_door": ritual_door,
                      "original_area_rows": partition["area_rows"], "modes": modes, "sensitivity": sensitivity,
                      "laundry": {**cfg["laundry"], "items": laundry}, "palanquin_body_mm": body,
                      "adopted": False, "original_first_floor_idf": "unresolved-unchanged"})
    if {c["id"] for c in cases} != {"b32-rear", "b32-front"} or len(cases) != 2:
        raise ContractError("Keep independent rear-priority and front-fallback options")
    helpers = ("b32_services.py", "requirement_reconciliation.py", "physical_items.py", "contracts.py")
    report = {"schema": "house-b32-service-detail-review-v1", "generated_at": utc_now(), "warning": WARNING,
              "status": cfg["status"], "frame_mm": base["frame_mm"], "land_ping": base["land_ping"], "cases": cases,
              "source_hashes": {**base["source_hashes"], SOURCE: sha256_file(root / SOURCE)},
              "generator_sha256": sha256_file(Path(__file__)),
              "helper_sha256": {n: sha256_file(Path(__file__).with_name(n)) for n in helpers},
              "parent_calculation_hash": base["report_hash"], "embedded_source_mismatches": base["embedded_source_mismatches"],
              "gates": cfg["gates"], "professional_approval": "unknown", "rendered_qa": "not-run",
              "original_requirements": {k: requirements[k]["constraints"] for k in
                                        ("B.floor-1.shrine", "B.floor-1.bath_acc", "B.floor-1.palanquin", "B.floor-1.balcony_b")}}
    report["report_hash"] = stable_hash({k: v for k, v in report.items() if k != "generated_at"})
    return report


def detail_svg(case: dict, mode_id: str = "daily-clear", *, closeup: bool = False) -> str:
    row = case["sensitivity"][0]  # Drawing is 80mm discussion case; JSON keeps 100/115mm separately.
    mode = next(m for m in case["modes"] if m["id"] == mode_id)
    root = Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "width": "900" if closeup else "600",
                           "height": "1000" if closeup else "1600", "viewBox": "950 10850 5200 5800" if closeup else "-400 -1100 7200 19600",
                           "role": "img", "data-case": case["id"], "data-mode": mode_id})
    SubElement(root, "title").text = "B32設備／座位研究，未採用；原拉門、照護、救援及搬轎未核"
    SubElement(root, "desc").text = "80mm假設內縮；150cm轉位共用零門檻淋浴地面。日常停凳非坐席，祭祀時不走家務通道。"

    def text(x, y, label, size=150, color="#0f172a"):
        SubElement(root, "text", {"x": str(x), "y": str(y), "font-size": str(size), "font-family": "sans-serif", "fill": color}).text = label

    def rect(r, fill, dashed=False, stroke="#64748b", thickness=12):
        x, y, w, d = r
        SubElement(root, "rect", {"x": str(x), "y": str(y), "width": str(w), "height": str(d), "fill": fill,
                                  "stroke": stroke, "stroke-width": str(thickness), **({"stroke-dasharray": "50 30"} if dashed else {})})

    if not closeup:
        text(0, -650, f"B32 {case['entry_mode']}｜{mode_id}｜未採用", 210)
        text(0, -300, "設備不縮｜80mm假設｜不等於法規／風水／救援通過", 155)
        rect([0, 0, 6000, 3900], "#f1f5f9")
        text(180, 1700, "前3.9m騎樓／通行候選帶，不停車", 190)
        for key, r in case["unchanged_front_rooms_mm"].items():
            rect(r, "#fef3c7" if key != "stair1" else "#cbd5e1")
        text(150, 5500, "原樓梯不動", 175)
        for y in range(6000, 8700, 270):
            SubElement(root, "path", {"d": f"M 150 {y} H 2200", "stroke": "#64748b", "stroke-width": "12"})
        text(2600, 5100, "朝街中軸門／前廳", 175)
        rect([2500, 3850, 1800, 100], "#16a34a")
        SubElement(root, "path", {"d": "M 3400 4000 V 10690", "stroke": "#b45309", "stroke-width": "14", "stroke-dasharray": "60 40"})
    colors = {"bathroom": "#cffafe", "storage": "#e0e7ff", "laundry": "#f0fdf4", "dry-backing": "#fef3c7",
              "public-housework-passage": "#dcfce7", "public-carry-passage": "#e2e8f0"}
    for key, rs in case["zones_mm"].items():
        for r in rs:
            rect(r, colors[key])
    text(2580, 11700, "乾式神桌背牆不動", 150)
    if not closeup:
        text(100, 13500, "家務", 145)
        text(4480, 12500, "原搬轎側緣", 145)
        text(2620, 15400, "儲藏目標10.5m²仍未達", 140)
        route = next(m["laundry_route"] for m in row["modes"] if m["mode"] == mode_id)
        points = " ".join(f"{x},{y}" for x, y in route["points_mm"])
        SubElement(root, "polyline", {"points": points, "fill": "none", "stroke": "#dc2626" if route["coordinate_failures"] else "#16a34a",
                                       "stroke-width": "45", "stroke-dasharray": "80 50"})
        for i in mode["items"]:
            rect(i["rect_mm"], "#9a3412" if i["id"] == "altar" else "#fed7aa")
            x, y, w, d = i["rect_mm"]
            name = {"altar": "神桌", "offering": "供桌", "bench-1": "凳1", "bench-2": "凳2"}[i["id"]]
            text(x+20, y+min(d-40, 240), name, 140, "#ffffff" if i["id"] == "altar" else "#0f172a")
        for op in mode["seated_operations"]:
            rect(op["rect_mm"], "none", True, "#c2410c")
        for i in case["laundry"]["items"]:
            rect(i["rect_mm"], "#94a3b8")
            text(i["rect_mm"][0]+15, i["rect_mm"][1]+300, "洗衣機" if i["id"] == "washer" else "洗槽", 130)
        for op in case["laundry"]["operations"]:
            rect(op["rect_mm"], "none", True)
        window = case["laundry"]["rear_high_window_proposal"]
        rect([window["center_x_mm"]-window["width_mm"]/2, 17590, window["width_mm"], 60], "#38bdf8")
        text(100, 17450, "後高窗候選／未核", 130)
        rect(case["palanquin_body_mm"], "#a5b4fc")
        text(case["palanquin_body_mm"][0]+20, 16200, f"{case['palanquin_body_mm'][2]/10:g}×{case['palanquin_body_mm'][3]/10:g}轎體", 140)
        carry_points = " ".join(f"{x},{y}" for x, y in row["carry"]["points_mm"])
        SubElement(root, "polyline", {"points": carry_points, "fill": "none", "stroke": "#7c3aed", "stroke-width": "35", "stroke-dasharray": "65 35"})
        if case["entry_mode"] == "rear":
            rect([3520, 17580, 1960, 100], "#7c3aed")
        else:
            text(2570, 17500, "無後門假設", 140)
        text(0, 17980, "綠／紅＝家務試線；紫＝本體搬轎；虛框＝分時操作", 145)
        text(0, 18200, "平日停凳不坐；祭祀停止家務穿越。外巷／人員／裝桿未核", 140)
    bath = row["bathroom"]
    for i in bath["fixtures"]:
        rect(i["rect_mm"], "#bae6fd" if i["id"] == "shower" else "#ffffff")
        x, y, w, d = i["rect_mm"]
        if i["id"] == "shower":
            for delta in (400, 800):
                SubElement(root, "path", {"d": f"M {x+delta} {y} v {d} M {x} {y+delta} h {w}", "stroke": "#7dd3fc", "stroke-width": "10"})
        elif i["id"] == "toilet":
            SubElement(root, "ellipse", {"cx": str(x+w/2), "cy": str(y+d/2), "rx": "150", "ry": "220", "fill": "none", "stroke": "#64748b", "stroke-width": "12"})
        text(x+15, y+min(d-40, 230), {"shower": "120淋浴", "toilet": "馬桶", "basin": "60洗手台"}[i["id"]], 130)
    for op in bath["operations"]:
        rect(op["rect_mm"], "none", True, "#0891b2")
    cx, cy, radius = bath["turn_circle_mm"]
    SubElement(root, "circle", {"cx": str(cx), "cy": str(cy), "r": str(radius), "fill": "none", "stroke": "#0284c7", "stroke-width": "20", "stroke-dasharray": "50 30"})
    text(cx-620, cy+50, "150cm分時轉位＊", 140)
    door = bath["door"]
    rect([4290, door["opening_center_y_mm"]-door["opening_nominal_mm"]/2, 60, door["opening_nominal_mm"]], "#ef4444")
    text(4450, 13800, "門型待解", 145, "#b91c1c")
    if closeup:
        remaining = case["sensitivity"][-1]["bathroom"]["door"]["double_outward_remaining_mm"]
        text(1150, 11100, "設備細排｜未採用｜80mm是假設，不是完成面", 160)
        text(1200, 15250, "＊轉位借零門檻淋浴地面，不可改固定玻璃間", 155)
        text(1200, 15600, "門淨寬／拉門原目標保留；救援與產品未解", 155)
        text(1200, 15950, f"115mm假設下雙扇外開僅餘{remaining}mm，不予採用", 150)
        text(1200, 16300, "便器側移、扶手、膝下、排氣與防水仍需專業確認", 145)
    return tostring(root, encoding="unicode")


def write_service_detail(report: dict, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    directory = output_root if output_root is not None else root / "structured/service-detail"
    paths = {"json": directory / "b32-service-detail.json", "markdown": directory / "b32-service-detail.md"}
    write_json(paths["json"], report)
    lines = ["# B32 緊湊家務案：衛浴／祭祀座位細排", "", report["warning"], "",
             "屋主同意的是繼續研究，不是接受縮減儲藏、移供桌、分時搬凳或外開門。原ABC、B32、需求、實測、封存與上一輪六案均不改。", "",
             "## 先說結論", "",
             "- 建議保留：120cm淋浴移至浴室較寬下段、便器靠右後、60cm洗手台放上段；設備不縮。轉位需借零門檻淋浴地面，功能及照護尚未核。",
             "- 可比較但需家中確認：供桌後移22cm貼神桌前緣，兩張140×45cm長凳平日全尺寸停放、祭祀前移位；祭祀時不走家務通道。",
             "- 原神桌靠後只留80mm；100／115mm假設內縮時固定位置少20／35mm。保留原位置列衝突，不暗移神桌或供桌、也不宣稱較厚完成面已能成立。",
             "- 暫不採用：浴室門型。原拉門要求保留；一般往北表面滑門跨乾櫃入口，往南跨儲藏門口。外開門僅作救援外廓比較，不算滿足原拉門需求。",
             "- 儲藏原10.5m²目標仍未達；1F IDF、KTV、停車、屋頂泵振動及基地權利沒有在本輪被解決。", "",
             "## 本輪明確比較的動線與限制", "",
             "從朝街正門內側起點到家務操作位置、浴室及各設備分支均畫出連續本體試線，不以房間相鄰代替。門檻、門片、扶手突出及真人步態／輪椅旋轉不含在試線內；不是全程無障礙核可。",
             "原供桌即使先移開長凳，約1m家務轉彎仍撞桌。後移供桌是有代價的家規比較，不宣稱既定可行。平日停放位置不算可坐席；祭祀長凳的600mm腿部假設只看設備不碰，不認定人數／照護容量。", "",
             "| 每側假設內縮 | 家務矩形寬 | 原供桌試線 | 移供桌＋停凳試線 | 祭祀坐凳時家務試線 | 衛浴門假設淨寬 | 雙扇外開時側緣餘寬 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    first = report["cases"][0]
    for row in first["sensitivity"]:
        results = {m["mode"]: m["laundry_route"] for m in row["modes"]}
        states = ["有衝突" if results[m]["coordinate_failures"] else "僅矩形未撞" for m in ("original-table-control", "daily-clear", "ritual-seated")]
        door = row["bathroom"]["door"]
        lines.append(f"| {row['inset_mm']}mm | {row['housework_body_width_mm']}mm | {' | '.join(states)} | {door['assumed_clear_mm']}mm | {door['double_outward_remaining_mm']}mm |")
    last_door = first["sensitivity"][-1]["bathroom"]["door"]
    leaves = last_door["comparison_leaf_sizes_mm"]
    lines += ["", f"雙扇外開是假設每扇{leaves['double_outward_leaf_each_mm']}mm、厚{leaves['assumed_leaf_thickness_mm']}mm，不是選品；"
              f"115mm情境比900mm本體餘{last_door['double_outward_margin_over_900mm']}mm，不能據此定門。單扇外開更窄，搬轎與開門不可同時。"
              "倒地範例會阻斷正常入門試線，救援鎖具／拆門／施救實演均未知。", "",
              "浴室原拉門條件沒有放寬。推薦交建築師先整合門洞、門廊／牆袋及乾櫃入口，而不是先買外開門；涉及分區時另做比較，不在此自動減掉浴室或儲藏。", "",
              "## 後門優先／前門備案分開核對", ""]
    for case in report["cases"]:
        lines += [f"### {case['id']}", "", f"[日常停凳全層圖]({case['id']}-daily-clear.svg) · [祭祀坐凳全層圖]({case['id']}-ritual-seated.svg)", "",
                  "前3.9m通行帶、樓梯、朝街中軸門、神桌及乾背牆均保留。所有圖是80mm假設；100／115mm數據在JSON，不冒充已核完成面。", ""]
        for row in case["sensitivity"]:
            carry = row["carry"]
            bath = row["bathroom"]
            lines.append(f"- {row['inset_mm']}mm：搬轎收納本體座標缺口{carry['coordinate_failures']}；原1500mm門目標未達{carry['original_gate_target_failures']}；"
                         f"衛浴設備／操作缺口{bath['fixture_operation_failures']}，轉位缺口{bath['turn_coordinate_failures']}。空陣列不是功能核可。")
            lines.append(f"  祭祀日常停凳模式座標缺口：{row['modes'][1]['shrine_object_operation_failures']}；正門至設備試線仍不含門片實作。")
        for area in case["original_area_rows"]:
            lines.append(f"- {area['requirement_id']}："+"、".join(f"{v['inset_mm']}mm → {v['area_sqm']:.4f}m²" for v in area["sensitivity"])
                         + f"；原目標{area['original_target_sqm']}m²、下限{area['original_minimum_sqm']}m²不變。")
        lines += ["", "前門案不假設後門／後巷；後門案不借用前門搬轎試線。裝桿／人員／輪具／門外迴轉仍未知。", ""]
    lines += ["前門儲藏門原1660mm名義寬，100／115mm框邊假設只餘1460／1430mm；可過1200mm暫估本體不代表達1500mm原要求。側緣名義1680mm在100／115mm時也僅1480／1450mm。後門名義1960mm仍不證明門外可搬。", "",
              "## 其他保留條件", "",
              "- [衛浴設備放大圖](bathroom-detail.svg)。一般60cm洗手台不是已核膝下淨空產品；零門檻、坡度、扶手、側移及救援均待專業。",
              "- 公共衛浴試線在前廳y=5000mm先轉側緣，避開y≥5700mm祭拜暫留帶；上段洗手台需前進／倒退出較寬下段轉位，真人輪椅與門片未演練。",
              "- 洗衣機650×650mm、洗槽600×600mm移靠後牆，前方保留操作及入口轉向假設；後高窗改1200mm窗台提案避設備，但窗權、有效排濕、防雨、污排水與是否外陽台皆未知。外窗不能單獨保證不發霉。",
              "- 全部座標以原尺寸靜態試排，長凳搬移及旋轉過程未驗。供桌是否可貼神桌、祭祀時關閉家務穿越，需要家中同意；本輪不把它記作風水已符合。",
              "- 所有門的產品、牆柱、完成面、消防與通行權未核；家務新接縫不是已核防火門。", ""]
    if report["embedded_source_mismatches"]:
        lines += ["來源已變動，快照比較過期，不沿用通過：", *[f"- `{p}`" for p in report["embedded_source_mismatches"]], ""]
    for case in report["cases"]:
        for mode in ("daily-clear", "ritual-seated"):
            (directory / f"{case['id']}-{mode}.svg").write_text(detail_svg(case, mode), encoding="utf-8")
    (directory / "bathroom-detail.svg").write_text(detail_svg(first, closeup=True), encoding="utf-8")
    lines += [f"source／generator／helper SHA-256見JSON。report_hash：`{report['report_hash']}`。", "",
              "僅檔案與小範圍座標測試；未執行瀏覽器／WebGL／整套場景或專業簽證。", ""]
    paths["markdown"].write_text("\n".join(lines), encoding="utf-8")
    return paths

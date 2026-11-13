"""Bounded B upper-floor alternatives; only explicit planar geometry is checked."""
from __future__ import annotations

import copy
import math
from itertools import combinations
from pathlib import Path

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from house_design.b_claude_round3 import max_axis_rectangle
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-upper-replan.json"
OUT = "structured/coordination/b-upper-replan-v1"


def rect(r):
    return box(r[0], r[1], r[0]+r[2], r[1]+r[3])


def ring(shape):
    if shape.geom_type != "Polygon" or not shape.is_valid or shape.interiors:
        raise ContractError("Expected one simple orthogonal room polygon")
    return [list(p) for p in shape.exterior.coords][:-1]


def hit(a, b):
    return a.intersection(b).area > .1


def sweep(points, width):
    half = width/2
    return unary_union([box(min(a[0], b[0])-half, min(a[1], b[1])-half,
        max(a[0], b[0])+half, max(a[1], b[1])+half) for a, b in zip(points, points[1:], strict=False)])


def door(spec, angle):
    a, b = spec["a"], spec["b"]
    horizontal = a[1] == b[1]
    hinge = b if spec["hinge"] in {"right", "rear"} else a
    endpoint = a if hinge == b else b
    vx, vy = endpoint[0]-hinge[0], endpoint[1]-hinge[1]
    if horizontal:
        dy = 1 if spec["opens"] == "inside" else -1
        # Street bath opens forward inside; P2 opens rearward outside into its foyer.
        if spec["b"][1] <= 3900:
            dy = -1 if spec["opens"] == "inside" else 1
        signed = dy*(1 if vx > 0 else -1)*angle
    else:
        signed = -angle  # rear hinge, outwards to the left of the suite
    t = math.radians(signed)
    end = [hinge[0]+vx*math.cos(t)-vy*math.sin(t), hinge[1]+vx*math.sin(t)+vy*math.cos(t)]
    return LineString([hinge, end]).buffer(47.5, cap_style=2)


def bridge(spec, inset):
    a, b = spec["a"], spec["b"]
    return (box(a[0]+inset, a[1]-inset, b[0]-inset, a[1]+inset) if a[1] == b[1]
        else box(a[0]-inset, a[1]+inset, a[0]+inset, b[1]-inset))


def room(rid, label, shape, items=None, shafts=None, doors=None, windows=None, kind="dry"):
    return {"id": rid, "label": label, "polygon_mm": ring(shape), "kind": kind,
        "items": copy.deepcopy(items or []), "shafts_mm": copy.deepcopy(shafts or []),
        "doors": copy.deepcopy(doors or []), "windows_mm": copy.deepcopy(windows or [])}


def finish(shape, inset):
    return shape.buffer(-inset, join_style=2)


def analyze_floor(rooms, cfg, protected, storage, option, fid, routes):
    shapes = {r["id"]: Polygon(r["polygon_mm"]) for r in rooms}
    inside = {key: finish(s, cfg["primary_inset_mm"]) for key, s in shapes.items()}
    frame = rect([0, 0, *cfg["frame_mm"]])
    union = unary_union(list(shapes.values()))
    overlaps = [{"a": a, "b": b, "sqm": shapes[a].intersection(shapes[b]).area/1e6}
        for a, b in combinations(shapes, 2) if hit(shapes[a], shapes[b])]
    fixtures, shafts, doors = [], [], []
    for r in rooms:
        fixtures.extend({**i, "key": r["id"]+":"+i["id"], "room": r["id"]} for i in r["items"])
        shafts.extend({"room": r["id"], "rect_mm": s} for s in r["shafts_mm"])
        doors.extend({**d, "key": r["id"]+":door-"+str(n)} for n, d in enumerate(r["doors"]))
    body_hits = [{"a": a["key"], "b": b["key"]} for a, b in combinations(fixtures, 2) if hit(rect(a["rect_mm"]), rect(b["rect_mm"]))]
    operation_hits = [{"operation": a["key"], "body": b["key"]} for a in fixtures for b in fixtures
        if a["key"] != b["key"] and a.get("operation_mm") and hit(rect(a["operation_mm"]), rect(b["rect_mm"]))]
    operation_shared = [{"a": a["key"], "b": b["key"], "sqm": rect(a["operation_mm"]).intersection(rect(b["operation_mm"])).area/1e6}
        for a, b in combinations(fixtures, 2) if a.get("operation_mm") and b.get("operation_mm") and hit(rect(a["operation_mm"]), rect(b["operation_mm"]))]
    invalid = [{"item": i["key"], "part": field} for i in fixtures for field in ["rect_mm", "operation_mm"]
        if i.get(field) and not inside[i["room"]].buffer(.01).covers(rect(i[field]))]
    shaft_hits = [{"shaft": s["room"], "body": i["key"]} for s in shafts for i in fixtures if hit(rect(s["rect_mm"]), rect(i["rect_mm"]))]
    shaft_operations = [{"shaft": s["room"], "operation": i["key"]} for s in shafts for i in fixtures
        if i.get("operation_mm") and hit(rect(s["rect_mm"]), rect(i["operation_mm"]))]
    full_door_hits = [{"door": d["key"], "body": i["key"]} for d in doors for i in fixtures
        if hit(door(d, 90), rect(i["rect_mm"]))]
    swing_hits = [{"door": d["key"], "body": i["key"], "angle_deg": n} for d in doors for i in fixtures
        for n in range(0, 91, 15) if hit(door(d, n), rect(i["rect_mm"]))]
    route_floor = unary_union([s for k, s in inside.items() if k != "front-open"]+
        [bridge(d, cfg["primary_inset_mm"]) for d in doors]+[rect([0, 3900, 2400, 1000])])
    if option.get("tea_opening_mm"):
        aa, bb = option["tea_opening_mm"]
        route_floor = unary_union([route_floor, bridge({"a": aa, "b": bb}, cfg["primary_inset_mm"])])
    rr = []
    for r in routes:
        s = sweep(r["points_mm"], r["width_mm"])
        rr.append({**r, "within_model_floor": route_floor.buffer(.1).covers(s),
            "outside_sqm": s.difference(route_floor).area/1e6,
            "body_hits": [i["key"] for i in fixtures if hit(s, rect(i["rect_mm"]))],
            "shaft_hits": [i["room"] for i in shafts if hit(s, rect(i["rect_mm"]))],
            "door_states": [{"angle_deg": angle, "hits": [d["key"] for d in doors if hit(s, door(d, angle))]} for angle in [90, 45, 0]],
            "actual_access": "unknown-not-human-or-wheelchair-kinematics"})
    areas = []
    for r in rooms:
        s = shapes[r["id"]]
        deduction = unary_union([rect(t) for t in r["shafts_mm"]]+[rect(i["rect_mm"]) for i in r["items"] if i["id"] == "screen"])
        cases = [{"inset_each_mm": n, "outline_sqm": round(finish(s, n).area/1e6, 6),
            "after_reserved_shafts_screens_sqm": round(finish(s, n).difference(deduction).area/1e6, 6)} for n in cfg["illustrative_insets_mm"]]
        areas.append({"id": r["id"], "label": r["label"], "nominal_sqm": round(s.area/1e6, 6),
            "cases": cases, "net115_sqm": next(c["after_reserved_shafts_screens_sqm"] for c in cases if c["inset_each_mm"] == 115)})
    religious = []
    for r in rooms:
        if r["kind"] in {"wet", "bedroom", "high-activity"}:
            s = shapes[r["id"]]
            religious.append({"room": r["id"], "kind": r["kind"], "over_shrine_or_backing_sqm": s.intersection(protected).area/1e6,
                "over_palanquin_sqm": s.intersection(storage).area/1e6,
                "prohibited_overlap": hit(s, protected) or (r["kind"] == "wet" and hit(s, storage)),
                "family_rule_scope": "explicit-footprints-only-no-religious-certification"})
    windows = [{"room": r["id"], "rect_mm": w,
        "on_room_boundary": shapes[r["id"]].boundary.buffer(.1).covers(LineString([w[:2], [w[0]+w[2], w[1]]])),
        "legal_effective_opening": "unknown", "side_boundary_assumed_open": False}
        for r in rooms for w in r["windows_mm"]]
    return {"id": fid, "rooms": rooms, "areas": areas, "partition": {"overlaps": overlaps,
        "unallocated_sqm": frame.difference(union).area/1e6, "outside_frame_sqm": union.difference(frame).area/1e6},
        "fixtures": {"body_hits": body_hits, "operation_body_hits": operation_hits, "operation_shared": operation_shared,
            "not_inside_115": invalid, "shaft_body_hits": shaft_hits, "shaft_operation_hits": shaft_operations,
            "fully_open_door_body_hits": full_door_hits, "sampled_swing_body_hits": swing_hits},
        "routes": rr, "religious_projection": religious, "windows": windows,
        "bedroom_largest_axis_rect": {r["id"]: max_axis_rectangle(inside[r["id"]]) for r in rooms if r["kind"] == "bedroom"}}


def floors(cfg, option, protected, storage):
    c = cfg["floors"]["common"]
    frame_front = rect([0, 0, 6000, 3900])
    living = unary_union([rect(r) for r in c["living_parts_mm"]])
    rear, dry, private = rect(c["rear_rect_mm"]), rect(c["dry_rect_mm"]), rect(c["private_bath_rect_mm"])
    master = rear.difference(unary_union([dry, private]))
    guest = unary_union([rect([0, 11370, 2640, 1600]), rect([0, 12970, c["third_guest_split_x_mm"], 4660])])
    ktv = rear.difference(unary_union([dry, guest]))
    result = []
    for fid in ["floor-2", "floor-3"]:
        rooms = [room("stair", "原同軸樓梯／平台，未改本體", rect(c["stair_rect_mm"])),
            room("quiet-living", "安靜起居／閱讀，禁睡及高活動", living, c["living_furniture"], doors=[option["balcony_door"]]),
            room("dry-protection", "獨立乾保護室，禁床／濕管設備", dry, doors=[c["dry_door"]]),
            room("public-bath", "前側有窗公衛", rect(option["public_rect_mm"]), option["public_fixtures"],
                [option["public_shaft_mm"]], [option["public_door"]], [option["public_window_mm"]], "wet"),
            room("front-open", "普通露台／景觀候選與獨立設備區", frame_front.difference(rect(option["enclosure_rect_mm"]))) ]
        if option["tea_rect_mm"]:
            rooms.append(room("tea-foyer", "濕茶水前室" if fid == "floor-2" else "乾式前室／工作預留",
                rect(option["tea_rect_mm"]), option["tea_furniture"] if fid == "floor-2" else [], kind="wet" if fid == "floor-2" else "dry"))
        if fid == "floor-2":
            rooms += [room("master", "主臥乾區（含更衣與入口）", master, c["master_furniture"], doors=[c["master_entry"]],
                windows=[c["master_rear_window_mm"]], kind="bedroom"),
                room("private-bath", "後右有窗套衛", private, c["private_fixtures"], [c["private_shaft_mm"]],
                    [c["private_door"]], [c["private_rear_window_mm"]], "wet")]
            routes = c["routes"]+option["routes"]+[{"id": "ensuite-shower-operation", "width_mm": 700,
                "points_mm": [[4165, 15665], [4635, 16000], [4635, 17065]],
                "purpose": "套衛入口至淋浴操作帶一般方塊，非照護"}]
        else:
            rooms += [room("guest", "後左客房／乾擋板", guest, c["third_guest_furniture"], doors=[c["third_guest_door"]],
                windows=[c["third_guest_window_mm"]], kind="bedroom"),
                room("ktv-study", "後右娛樂候選（低於20㎡目標）", ktv, c["third_ktv_furniture"], [c["private_shaft_mm"]],
                    [c["third_ktv_door"]], [c["third_ktv_window_mm"]], "high-activity")]
            routes = c["third_routes"]+option["routes"]
        if option["id"] == "front-wet-foyer":
            routes = routes+[{"id": "public-shower-operation", "width_mm": 700,
                "points_mm": [[2585, 1415], [1365, 1415]], "purpose": "前公衛至淋浴操作帶一般方塊"}]
        else:
            routes = routes+[{"id": "public-shower-operation", "width_mm": 700,
                "points_mm": [[1765, 3335], [1365, 3335]], "purpose": "前公衛至淋浴操作帶一般方塊"}]
        result.append(analyze_floor(rooms, cfg, protected, storage, option, fid, routes))
    return result


def frontage(cfg, option):
    garden = Polygon(option["garden_polygon_mm"])
    soil = unary_union([rect(v) for v in option["soil_rects_mm"]])
    services = unary_union([rect(v) for v in option["outdoor_service_mm"]])
    x_left = 3720 if option["id"] == "front-wet-foyer" else 530
    points = [[4765, 4500], [4765, 3550], [5600, 3550], [5600, 1100], [x_left, 1100]]
    route = sweep(points, 700)
    accessible = unary_union([rect([0, 0, 6000, 3900]).difference(rect(option["enclosure_rect_mm"])), rect([2400, 3900, 3600, 5200])])
    return {"garden_sqm": round(garden.area/1e6, 6), "soil_sqm": round(soil.area/1e6, 6),
        "soil_ratio": soil.area/garden.area, "service_over_garden_sqm": services.intersection(garden).area/1e6,
        "soil_over_service_sqm": soil.intersection(services).area/1e6, "soil_inside_garden": garden.covers(soil),
        "proposed_woody_count": 4, "soil_depth_load_and_eligibility": "unknown",
        "enclosure_nominal_add_sqm_per_upper_floor": rect(option["enclosure_rect_mm"]).area/1e6,
        "declared_as_exempt_landscape_after_enclosure": False,
        "outdoor_units_mm": option["outdoor_units_mm"], "outdoor_service_mm": option["outdoor_service_mm"],
        "garden_polygon_mm": option["garden_polygon_mm"], "soil_rects_mm": option["soil_rects_mm"],
        "outdoor_700_route": {"points_mm": points, "width_mm": 700, "inside_model_open_or_living_area": accessible.covers(route),
            "soil_hit": hit(route, soil), "unit_hits": [i for i, r in enumerate(option["outdoor_units_mm"]) if hit(route, rect(r))],
            "actual_maintenance_and_wheelchair_access": "unknown"},
        "outdoor_routes_refrigerant_and_service_approval": "unknown"}


def drain_review(cfg, prior):
    d = cfg["drainage"]
    sec = d["arcade_section"]
    length = LineString(d["front_offset_plan_points_mm"]).length
    drops = length/sec["illustrative_slope_denominator"]
    section = [{"structure_mm": structure, "pipe_support_mm": pipe, "hypothetical_fall_mm": drops,
        "remaining_clear_mm": sec["floor2_level_mm"]-structure-pipe-drops-sec["access_allowance_mm"],
        "target_mm": sec["required_illustrative_clear_mm"]} for structure in sec["illustrative_structure_depths_mm"]
        for pipe in sec["pipe_support_envelopes_mm"]]
    options = []
    for o in prior["stack_and_entry"]["options"]:
        source_states = o["states"]
        checks = []
        for state in source_states:
            f = state["floor1"]
            bath = next(r for r in f["rooms"] if r["id"].endswith(":rear-bath"))
            shaft = rect(d["rear_shaft_mm"])
            checks.append({"state": state["id"], "rear_shaft_in_bath_nominal": rect(bath["rect_mm"]).covers(shaft),
                "rear_shaft_fixed_body_hits": [i["id"] for r in f["rooms"] for i in r["furniture"] if hit(shaft, rect(i["rect_mm"]))],
                "ground_care_route_and_turning": "unknown-not-revalidated", "floor1_source_unchanged": True})
        options.append({"id": o["id"], "states": checks, "source_states_hash": stable_hash(source_states),
            "roof_reference_hash": stable_hash(o["roof_reference"]), "rear_legal_access": "unknown",
            "front_downpipe_over_stair_reserved_box": rect([0, 3900, 2400, 5200]).intersection(rect(d["front_offset_ground_candidate_mm"])).area/1e6})
    option_lengths = {spec["id"]: LineString([[spec["public_shaft_mm"][0]+200, spec["public_shaft_mm"][1]+200],
        [d["front_offset_ground_candidate_mm"][0]+200, d["front_offset_ground_candidate_mm"][1]+200]]).length
        for spec in cfg["floors"]["options"]}
    return {**d, "offset_length_mm": length, "section_applies_to": "front-wet-foyer", "option_offset_lengths_mm": option_lengths,
        "section_sensitivity": section, "ground_options": options,
        "front_discharge_constructible": False, "all_gravity_drains_and_vents_designed": False,
        "summary": "前排水是先決工程缺口；樓梯內候選不代表已留空，直落騎樓被拒。假設只有部分剖面能達目標，梁板及消防未知。"}


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    if cfg.get("schema") != "house-b-upper-replan-v1" or cfg.get("adopted") is not False:
        raise ContractError("Only an independent B upper-floor comparison may be exported")
    if cfg["frame_mm"] != [6000, 17630] or cfg["arcade_depth_mm"] != 3900:
        raise ContractError("Changed land envelope requires an explicit new planning basis")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen B input changed: "+name)
    controls = read_json(root/cfg["protected_controls"])["hashes"]
    cache = {}
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    prior = read_json(root/cfg["source_report"])
    strict = read_json(root/cfg["strict_report"])
    if [v["id"] for v in prior["stack_and_entry"]["options"]] != cfg["unchanged_ground_options"]:
        raise ContractError("Preserve separate rear/front ground options")
    for o in prior["stack_and_entry"]["options"]:
        if [s["id"] for s in o["states"]] != cfg["unchanged_ground_states"]:
            raise ContractError("Preserve daily, ritual and carry states")
    protected = unary_union([Polygon(p) for p in strict["options"][0]["protected_polygons_mm"]])
    storage = rect(strict["options"][0]["palanquin_rect_mm"])
    options = []
    for spec in cfg["floors"]["options"]:
        fs = floors(cfg, spec, protected, storage)
        for f in fs:
            if (any(f["fixtures"][key] for key in ["body_hits", "operation_body_hits", "not_inside_115", "shaft_body_hits",
                    "shaft_operation_hits", "fully_open_door_body_hits", "sampled_swing_body_hits"])
                    or f["partition"]["overlaps"] or f["partition"]["unallocated_sqm"] > .000001
                    or f["partition"]["outside_frame_sqm"] > .000001
                    or any(r["prohibited_overlap"] for r in f["religious_projection"])
                    or any(not r["within_model_floor"] or r["body_hits"] or r["shaft_hits"] or r["door_states"][0]["hits"] for r in f["routes"])
                    or any(not w["on_room_boundary"] for w in f["windows"])):
                raise ContractError("Known planar defect in B upper option: "+spec["id"]+" "+f["id"])
        area2 = {r["id"]: r["net115_sqm"] for r in fs[0]["areas"]}
        area3 = {r["id"]: r["net115_sqm"] for r in fs[1]["areas"]}
        garden = frontage(cfg, spec)
        if (garden["service_over_garden_sqm"] > .000001 or garden["soil_over_service_sqm"] > .000001
                or not garden["soil_inside_garden"] or garden["outdoor_700_route"]["soil_hit"]
                or garden["outdoor_700_route"]["unit_hits"] or not garden["outdoor_700_route"]["inside_model_open_or_living_area"]):
            raise ContractError("Known frontage geometry defect")
        goals = [{"id": k, "value_sqm": area2.get(k, 0), "target_sqm": goal,
            "target_met_in_115_model": area2.get(k, 0) >= goal} for k, goal in
            [("master", 20), ("public-bath", 5), ("private-bath", 6), ("quiet-living", 28), ("tea-foyer", 5)]]
        goals += [{"id": "garden", "value_sqm": garden["garden_sqm"], "target_sqm": 7,
            "target_met_in_115_model": garden["garden_sqm"] >= 7},
            {"id": "third-guest", "value_sqm": area3["guest"], "target_sqm": 12, "target_met_in_115_model": area3["guest"] >= 12},
            {"id": "third-ktv", "value_sqm": area3["ktv-study"], "target_sqm": 20, "target_met_in_115_model": area3["ktv-study"] >= 20}]
        r2 = {r["id"]: Polygon(r["polygon_mm"]) for r in fs[0]["rooms"]}
        r3 = {r["id"]: Polygon(r["polygon_mm"]) for r in fs[1]["rooms"]}
        bed2 = rect(cfg["floors"]["common"]["master_furniture"][0]["rect_mm"])
        stack = {"third_wet_over_second_master_sqm": r3["public-bath"].intersection(r2["master"]).area/1e6,
            "third_wet_over_second_bed_body_sqm": r3["public-bath"].intersection(bed2).area/1e6,
            "third_entertainment_over_second_master_sqm": r3["ktv-study"].intersection(r2["master"]).area/1e6,
            "third_entertainment_over_second_bed_body_sqm": r3["ktv-study"].intersection(bed2).area/1e6,
            "acoustic_and_vibration_approval": "unknown-even-if-not-directly-over-bed"}
        options.append({"id": spec["id"], "label": spec["label"], "floors": fs, "frontage": garden,
            "goals": goals, "upper_stack": stack, "third_ktv_meets_14_min_in_model": area3["ktv-study"] >= 14,
            "conclusion": spec["conclusion"], "adopted": False, "buildable": "unknown", "all_requirements_met": False})
    report = {"schema": "house-b-upper-replan-report-v1", "date": cfg["date"], "config": cfg,
        "frame_sqm": 6000*17630/1e6, "frame_land_ping": 6000*17630/1e6*121/400,
        "source_layout_report_sha256": sha256_file(root/cfg["source_report"]),
        "protected_polygons_mm": strict["options"][0]["protected_polygons_mm"],
        "palanquin_rect_mm": strict["options"][0]["palanquin_rect_mm"], "options": options,
        "drainage": drain_review(cfg, prior), "old_rear_bound": prior["area_limits"]["conditional_bound"],
        "old_targets_and_values": {"targets": prior["original_targets_sqm"],
            "case": prior["variants"][1]["current_inset_case"], "public_after_shaft": prior["variants"][1]["public_area_accounting"]},
        "protected_controls_unchanged": len(controls), "primary_abc_or_3d_changed": False,
        "new_geometry_is_independent_comparison": True, "rendered_qa": "not-run", "adopted": False,
        "professional_approval": "unknown", "all_requirements_met": False, "actual_site_or_product_data_received": 0,
        "preferred_research_option": "front-wet-foyer", "research_preference_is_not_owner_adoption": True}
    names = [CONFIG, cfg["protected_controls"], *cfg["pinned_sources"], "inputs/requirements.json", "inputs/planning-register.json",
        "inputs/brief/B.json", "house_design/b_upper_replan.py", "scripts/export_b_upper_replan.py",
        "house_design/b_claude_round3.py", "scripts/export_abc_next_improvements.py", "Docs/b-upper-replan-v1.md"]
    report["source_hashes"] = {name: digest(root, name, cache) for name in names}
    report["report_hash"] = stable_hash(report)
    return report

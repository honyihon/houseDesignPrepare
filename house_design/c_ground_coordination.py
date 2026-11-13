"""Source-bound static whole-ground-floor coordination, without scene generation."""
from __future__ import annotations

import copy
import json
import re
from itertools import combinations, product
from pathlib import Path

from shapely.affinity import rotate
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from house_design.b_upper_replan import bridge, finish, hit, rect, sweep
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/c-ground-coordination.json"
OUT = "structured/coordination/c-ground-coordination-v1"
STATES = {"open": 1, "half": .5, "closed": 0}


def payload_state(root, report, viewer, payload, option, state):
    """Check selected frozen plan against its embedded model; never regenerate old sources."""
    data = re.search(r"^\s*var DATA = (.+);\s*$", (root/viewer).read_text(encoding="utf-8"), re.M)
    if data is None:
        raise ContractError("Missing frozen C payload")
    raw = json.loads(data[1])[payload]
    embedded = next(s for o in raw["options"] if o["id"] == option for s in o["states"] if s["id"] == state)
    source = next(s for o in report["options"] if o["id"] == option for s in o["states"] if s["id"] == state)
    for floor in source["plans"]["floors"]:
        mf = next(f for f in embedded["model"]["buildings"][0]["floors"] if f["id"] == floor["id"])
        cells = {c["id"]: c for c in mf["cells"] if c.get("tour_active")}
        if len(cells) != len(floor["rooms"]):
            raise ContractError("Frozen C plan is incomplete")
        for r in floor["rooms"]:
            c = cells[r["id"]]
            items = [{**i, "placement": c["furniture_placements"]["tour_mm"][i["id"]]} for i in c["furniture"]]
            if c["tour_mm"] != r["geometry"] or c["tour_features"] != r["features"] or items != r["furniture"]:
                raise ContractError("Frozen C plan/model disagree: "+r["id"])
    return source


def aabb(value):
    return [value["minX"], value["minY"], value["maxX"]-value["minX"], value["maxY"]-value["minY"]]


def normalize(room):
    g = room["geometry"]
    return {"id": room["key"], "label": room["name"], "rect_mm": [g[k] for k in ["x_mm", "y_mm", "w_mm", "h_mm"]],
        "source_features": copy.deepcopy(room["features"]),
        "items": [{"id": i["id"], "shape": i["shape"], "body_mm": aabb(i["placement"]["aabb"]),
            "operation_mm": aabb(i["placement"]["operation_mm"]) if i["placement"].get("operation_mm") else None,
            "product_dimensions_mm": [i[k] for k in ["width_mm", "depth_mm", "height_mm"]],
            "rotation_deg": i["placement"]["rotation_deg"], "wall_anchor": i["placement"]["wall_anchor"],
            "mount_height_mm": i["placement"]["mount_height_mm"]} for i in room["furniture"]]}


def component_rect(spec):
    if spec["kind"] == "box":
        return spec["rect_mm"]
    xs, ys, _ = zip(*spec["points_mm"], strict=True)
    radius = spec["diameter_mm"]/2
    return [min(xs)-radius, min(ys)-radius, max(xs)-min(xs)+2*radius, max(ys)-min(ys)+2*radius]


def physical_hit(a, b):
    return hit(rect(a["body_mm"]), rect(b["body_mm"])) and min(a["mount_height_mm"]+a["product_dimensions_mm"][2],
        b["mount_height_mm"]+b["product_dimensions_mm"][2]) > max(a["mount_height_mm"], b["mount_height_mm"])


def propose(main, care, cfg):
    rooms = {r["key"]: normalize(r) for r in main["plans"]["floors"][0]["rooms"]}
    old = copy.deepcopy(rooms)
    for key, area in cfg["room_zones_mm"].items():
        rooms[key]["rect_mm"] = area
    rooms["stair1f"]["label"] = "24級樓梯／共享前平台（本體不縮）"
    rooms["sliding-door"]["label"] = "梯旁照護走道（無新增門牆）"
    rooms["sideyard"]["label"] = "乾式照護前室／共享IDF維修"
    source_bath = next(r for r in care["plans"]["floors"][0]["rooms"] if r["key"] == "elder-bath")
    # Geometry, current HVAC and legal-window metadata remain on the current basis.
    rooms["elder-bath"]["items"] = normalize(source_bath)["items"]
    tv = next(i for r in care["plans"]["floors"][0]["rooms"] if r["key"] == "elder" for i in normalize(r)["items"] if i["shape"] == "wall-tv")
    rooms["elder"]["items"] = [copy.deepcopy(tv) if i["shape"] == "wall-tv" else i for i in rooms["elder"]["items"]]
    for room in rooms.values():
        for item in room["items"]:
            if item["id"] not in cfg["item_rectangles_mm"]:
                continue
            new = cfg["item_rectangles_mm"][item["id"]]
            if new[2:] != item["body_mm"][2:]:
                raise ContractError("Only explicit translations preserve C furniture orientation and size")
            dx, dy = new[0]-item["body_mm"][0], new[1]-item["body_mm"][1]
            item["body_mm"] = new
            if item["operation_mm"]:
                item["operation_mm"][:2] = [item["operation_mm"][0]+dx, item["operation_mm"][1]+dy]
    return list(rooms.values()), list(old.values())


def door_parts(states, cfg, gate, care_states):
    street = rotate(rect(cfg["street_door"]["closed_rect_mm"]), -90*STATES[states["street"]], origin=cfg["street_door"]["pivot_mm"])
    parts = [{"door": "street", "id": "street", "polygon_mm": list(street.exterior.coords)}]
    for key, opened, closed in [("front", gate["parking_rect_mm"], gate["closed_leaf_rect_mm"]),
            ("bedroom", cfg["bedroom_door"]["open_rect_mm"], cfg["bedroom_door"]["closed_rect_mm"])]:
        value = [a+(b-a)*STATES[states[key]] for a, b in zip(closed, opened, strict=True)]
        parts.append({"door": key, "id": key, "polygon_mm": list(rect(value).exterior.coords)})
    bath = next(r for r in care_states[states["bath"]]["plans"]["floors"][0]["rooms"] if r["key"] == "elder-bath")
    for spec in bath["features"]["care_entry_leaves"]+bath["features"]["care_door_parts"]:
        parts.append({"door": "bath", "id": spec["id"], "polygon_mm": list(rect(spec["rect_mm"]).exterior.coords)})
    return parts


def floor_surface(rooms, cfg, gate):
    rs = {r["id"]: r for r in rooms}
    public_ids = ["dining", "living", "entrance", "living-hall", "living-right", "sliding-door", "sideyard"]
    public = finish(unary_union([rect(rs[k]["rect_mm"]) for k in public_ids]+[rect([2400, 8550, 3600, 1210])]), cfg["inset_mm"])
    # These are the already-selected partition and return; other public zone lines stay open.
    walls = unary_union([rect(r) for r in gate["wall_budgets_mm"]])
    aperture = box(2900+115, 8480, 4100-115, 8620)
    public = public.difference(walls.difference(aperture))
    pieces = [public, rect([0, 0, 6000, 3900]), finish(rect(rs["elder"]["rect_mm"]), cfg["inset_mm"]),
        finish(rect(rs["elder-bath"]["rect_mm"]), cfg["inset_mm"]), finish(rect(rs["public-bath"]["rect_mm"]), cfg["inset_mm"])]
    for aa, bb in [cfg["street_door"]["nominal_opening_mm"], cfg["bedroom_door"]["nominal_opening_mm"], cfg["bath_opening_mm"], [[4100, 5700], [5000, 5700]]]:
        pieces.append(bridge({"a": aa, "b": bb}, cfg["inset_mm"]))
    return unary_union(pieces), public


def geometry(rooms, old_rooms, cfg, gate, care_states, care, main):
    fixtures = [{**i, "room": r["id"]} for r in rooms for i in r["items"]]
    flat, public = floor_surface(rooms, cfg, gate)
    shapes = {r["id"]: rect(r["rect_mm"]) for r in rooms}
    frame = rect([0, 0, *cfg["frame_mm"]])
    partition = {"overlaps": [{"a": a, "b": b} for a, b in combinations(shapes, 2) if hit(shapes[a], shapes[b])],
        "unallocated_sqm": frame.difference(unary_union(list(shapes.values()))).area/1e6,
        "outside_frame_sqm": unary_union(list(shapes.values())).difference(frame).area/1e6}
    components = next(r["features"]["care_bath_components"] for r in care["plans"]["floors"][0]["rooms"] if r["key"] == "elder-bath")
    hardware = [{"id": c["id"], "body_mm": component_rect(c)} for c in components if not c.get("flush_floor_only")]
    fixed = [i for i in fixtures if i["shape"] != "shower"]+hardware
    route_specs = copy.deepcopy(cfg["routes"])
    for name, route in care["review"]["layout"]["routes"].items():
        route_specs.append({"id": name, "label": name, "width_mm": 900, "points_mm": route["points_mm"], "expected_doors": ["bath"]})
    base_routes = []
    for route in route_specs:
        shape = sweep(route["points_mm"], route["width_mm"])
        base_routes.append({**route, "within_model_floor": flat.buffer(.01).covers(shape),
            "outside_sqm": shape.difference(flat).area/1e6,
            "fixed_body_hits": [i["id"] for i in fixed if hit(shape, rect(i["body_mm"]))],
            "first_riser_hit": hit(shape, rect([3720, 9760, 1000, 2970])),
            "operation_shared": [i["id"] for i in fixtures if i["operation_mm"] and hit(shape, rect(i["operation_mm"]))],
            "actual_care_access": "unknown-rectangle-study-not-human-or-wheelchair-motion",
            "visitor_door_leaf_hardware_unknown": route["id"] == "visitor-to-wc"})
    cases = []
    for values in product(STATES, repeat=4):
        state = dict(zip(["street", "front", "bedroom", "bath"], values, strict=True))
        panels = door_parts(state, cfg, gate, care_states)
        cases.append({"states": state, "route_door_hits": {r["id"]: sorted({p["door"] for p in panels
            if hit(sweep(r["points_mm"], r["width_mm"]), Polygon(p["polygon_mm"]))}) for r in base_routes},
            "panel_fixed_hits": [{"panel": p["id"], "body": i["id"]} for p in panels for i in fixed
                if hit(Polygon(p["polygon_mm"]), rect(i["body_mm"]))],
            "panel_pair_hits": [{"a": a["id"], "b": b["id"]} for a, b in combinations(panels, 2)
                if hit(Polygon(a["polygon_mm"]), Polygon(b["polygon_mm"]))]})
    open_parts, closed_parts = [door_parts(dict.fromkeys(["street", "front", "bedroom", "bath"], s), cfg, gate, care_states) for s in ["open", "closed"]]
    travel = []
    for a, b in zip(open_parts, closed_parts, strict=True):
        if a["id"] == "street":
            shape = unary_union([rotate(rect(cfg["street_door"]["closed_rect_mm"]), -angle,
                origin=cfg["street_door"]["pivot_mm"]) for angle in range(0, 91, 3)]).convex_hull.buffer(1)
            method = "3deg-swing-hull-inflated-1mm-not-product-hardware"
        else:
            shape = unary_union([Polygon(a["polygon_mm"]), Polygon(b["polygon_mm"])]).convex_hull
            method = "exact-axis-translation-envelope"
        travel.append({"id": a["id"], "door": a["door"], "method": method,
            "polygon_mm": list(shape.exterior.coords), "fixed_hits": [i["id"] for i in fixed if hit(shape, rect(i["body_mm"]))]})
    finish_issues = []
    for i in fixtures:
        area = public if i["room"] in {"dining", "living", "entrance", "sideyard"} else finish(shapes[i["room"]], 115)
        for field in ["body_mm", "operation_mm"]:
            if i[field] and not area.buffer(.01).covers(rect(i[field])):
                finish_issues.append({"item": i["id"], "part": field})
    old_items = {i["id"]: i for r in old_rooms for i in r["items"]}
    changes = [{"id": i["id"], "from_mm": old_items[i["id"]]["body_mm"], "to_mm": i["body_mm"],
        "size_preserved": sorted(old_items[i["id"]]["body_mm"][2:]) == sorted(i["body_mm"][2:])} for i in fixtures if i["body_mm"] != old_items[i["id"]]["body_mm"]]
    operation_shared = [{"a": a["id"], "b": b["id"], "sqm": rect(a["operation_mm"]).intersection(rect(b["operation_mm"])).area/1e6}
        for a, b in combinations(fixtures, 2) if a["operation_mm"] and b["operation_mm"] and hit(rect(a["operation_mm"]), rect(b["operation_mm"]))]
    bed = next(i for i in fixtures if i["shape"] == "bed")
    wet = [r for f in main["plans"]["floors"][1:] for r in f["rooms"] if r["key"] in {"bath2f", "bath3f"}]
    bed_projection = [{"upper_room": r["id"], "over_bed_body_sqm": rect([r["geometry"][k] for k in ["x_mm", "y_mm", "w_mm", "h_mm"]]).intersection(rect(bed["body_mm"])).area/1e6} for r in wet]
    old_stair = rect(next(r["rect_mm"] for r in old_rooms if r["id"] == "stair1f"))
    reassignment = {"old_stair_zone_sqm": old_stair.area/1e6, "new_stair_zone_sqm": shapes["stair1f"].area/1e6,
        "from_old_stair_to_corridor_sqm": old_stair.intersection(shapes["sliding-door"]).area/1e6,
        "from_old_stair_to_care_lobby_sqm": old_stair.intersection(shapes["sideyard"]).area/1e6,
        "new_floor_area_added_sqm": 0, "physical_stair_flights_shrunk": False}
    return {"partition": partition, "fixtures_count": len(fixtures), "body_hits": [{"a": a["id"], "b": b["id"]} for a, b in combinations(fixtures, 2)
            if physical_hit(a, b)], "finish_issues115": finish_issues,
        "operation_body_hits": [{"operation": a["id"], "body": b["id"]} for a in fixtures for b in fixtures
            if a["id"] != b["id"] and a["operation_mm"] and b["shape"] not in {"wall-tv", "shower"} and hit(rect(a["operation_mm"]), rect(b["body_mm"]))],
        "elevated_tv_floor_projection_overlaps": [{"a": a["id"], "b": b["id"], "vertical_intervals_disjoint": True}
            for a, b in combinations(fixtures, 2) if hit(rect(a["body_mm"]), rect(b["body_mm"])) and not physical_hit(a, b)],
        "operation_shared": operation_shared, "routes": base_routes, "door_combinations": cases, "door_full_travel": travel,
        "zone_reassignment": reassignment,
        "components": components, "hardware": hardware, "changes": changes, "bed_projection": bed_projection,
        "all_items_dimensions_preserved": all(i["product_dimensions_mm"] == old_items[i["id"]]["product_dimensions_mm"] for i in fixtures),
        "new_care_route_crosses_shared_landing_at_floor_level": True,
        "first_riser_route_nominal_gap_mm": sweep(cfg["routes"][0]["points_mm"], cfg["routes"][0]["width_mm"]).distance(rect([3720, 9760, 1000, 2970])),
        "care_lobby_finished_depth_mm": 1700-230, "care_lobby_independent_1500_turn_proven": False,
        "visitor_wc_nominal_door_mm": 900, "visitor_wc_hypothetical_finished_mm": 900-230,
        "visitor_wc_door_leaf_and_rescue": "unknown", "public_caregiver_bath_without_bedroom": False,
        "rooms_are_planning_zones_not_permission_to_remove_walls": True}


def bath_review(rooms, care, care_states, cfg):
    bath = next(r for r in rooms if r["id"] == "elder-bath")
    items = {i["id"].rsplit(":", 1)[-1]: i for i in bath["items"]}
    old = care["review"]["layout"]
    op, transfer, board = items["vanity"]["operation_mm"], old["toilet_transfer_mm"], old["rescue_board_rotation_mm"]
    components = next(r["features"]["care_bath_components"] for r in care["plans"]["floors"][0]["rooms"] if r["key"] == "elder-bath")
    hardware = {c["id"]: component_rect(c) for c in components if not c.get("flush_floor_only")}
    arrival = old["basin_arrival_rect_mm"]
    seat, rail = hardware["fold-seat"], hardware["shower-wall-grab"]
    margins = {"basin_arrival_face_mm": arrival[0]-sum(items["vanity"]["body_mm"][::2]),
        "basin_arrival_lateral_offset_mm": arrival[1]+450-(items["vanity"]["body_mm"][1]+items["vanity"]["body_mm"][3]/2),
        "transfer_to_basin_mm": transfer[0]-sum(items["vanity"]["body_mm"][::2]),
        "board_to_folded_seat_mm": seat[1]-board[1]-board[3], "board_to_right_rail_mm": rail[0]-board[0]-board[2],
        "door_pack_to_turn_reserve_mm": old["turn_reserve_mm"][0]-(3715+130)}
    reserve = rect(old["turn_reserve_mm"])
    static_hits = [i["id"] for i in bath["items"] if i["shape"] != "shower" and hit(reserve, rect(i["body_mm"]))]
    static_hits += [key for key, area in hardware.items() if hit(reserve, rect(area))]
    circle = old["turn_circle_mm"]
    return {"nominal_sqm": rect(bath["rect_mm"]).area/1e6, "after115_outline_sqm": finish(rect(bath["rect_mm"]), 115).area/1e6,
        "margins_mm": margins, "transfer_mm": transfer, "turn_reserve_mm": old["turn_reserve_mm"], "turn_circle_mm": circle,
        "reserve_fixed_hits": static_hits, "shared_shower_floor_sqm": reserve.intersection(rect(items["accessible-shower"]["body_mm"])).area/1e6,
        "operation_transfer_overlap_sqm": rect(op).intersection(rect(transfer)).area/1e6,
        "independent_dry_turn_floor": False, "simultaneous_basin_and_transfer": False, "seated_basin_reach": "unknown-offset-250mm",
        "single_20mm_rail_margin_remaining_mm": margins["board_to_right_rail_mm"]-20,
        "centered_basin_control": old["centered_basin_control"], "hardware_full_sweep_source": old["hardware_sweeps"],
        "hardware_full_sweep_fixed_hits": [{"sweep": s["id"], "item": i["id"]} for s in old["hardware_sweeps"] for i in bath["items"]
            if i["shape"] != "shower" and hit(rect(s["box_mm"][:4]), rect(i["body_mm"]))],
        "folded_seat_raised_arm_only": True, "folded_hardware_sweep_not_all_care_states": True,
        "actual_clear_product_anchors_waterproof_rescue_and_care": "unknown"}


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    if cfg.get("schema") != "house-c-ground-coordination-v1" or cfg.get("adopted") is not False or cfg["frame_mm"] != [6000, 17630] or cfg["inset_mm"] != 115:
        raise ContractError("Preserve the independent C 1F planning scope")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen C reference changed: "+name)
    cache = {}
    controls = read_json(root/cfg["protected_controls"])["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    main_report, care_report = read_json(root/cfg["main_report"]), read_json(root/cfg["care_report"])
    main = payload_state(root, main_report, cfg["main_viewer"], "kaohsiung_options", "c-split", "daily")
    care_states = {key: payload_state(root, care_report, cfg["care_viewer"], "c_care_bath_layout", "side-basin", key) for key in STATES}
    care = care_states["open"]
    rooms, baseline = propose(main, care, cfg)
    gate = next(r["features"]["c_front_gate"] for r in main["plans"]["floors"][0]["rooms"] if r["key"] == "stair1f")
    review = geometry(rooms, baseline, cfg, gate, care_states, care, main)
    bath = bath_review(rooms, care, care_states, cfg)
    for key in ["body_hits", "operation_body_hits", "finish_issues115"]:
        if review[key]:
            raise ContractError("C whole-floor defect "+key+": "+str(review[key]))
    if (review["partition"]["overlaps"] or review["partition"]["unallocated_sqm"] > .000001 or review["partition"]["outside_frame_sqm"] > .000001
            or not review["all_items_dimensions_preserved"] or any(p["over_bed_body_sqm"] for p in review["bed_projection"])
            or any(not r["within_model_floor"] or r["fixed_body_hits"] or r["first_riser_hit"] for r in review["routes"])
            or any(t["fixed_hits"] for t in review["door_full_travel"]) or bath["reserve_fixed_hits"] or bath["hardware_full_sweep_fixed_hits"]):
        raise ContractError("C listed whole-floor route, fixture, door travel, wet projection or bath defect")
    for state in review["door_combinations"]:
        if state["panel_fixed_hits"] or state["panel_pair_hits"]:
            raise ContractError("C door state collision")
        for route in review["routes"]:
            expected = sorted(k for k in route["expected_doors"] if state["states"][k] != "open")
            if state["route_door_hits"][route["id"]] != expected:
                raise ContractError("C independent door blockers disagree: "+route["id"]+str(state["states"]))
    drift = [{"source": name, "old_sha256": old, "current_sha256": digest(root, name, cache)} for name, old in care_report["source_hashes"].items()
        if digest(root, name, cache) != old]
    report = {"schema": "house-c-ground-coordination-report-v1", "date": cfg["date"], "config": cfg,
        "rooms": rooms, "baseline_rooms": baseline, "review": review, "bath": bath, "front_gate": gate,
        "care_door_parts": {key: door_parts(dict.fromkeys(["street", "front", "bedroom", "bath"], key), cfg, gate, care_states) for key in STATES},
        "stair_reference": {k: main_report["c_detail"][k] for k in ["first_stair", "surfaces", "floor_bases_mm", "shared_level_apron_mm", "second_floor_floor_level_platform_removed_mm"]},
        "upper_floors_unchanged_hash": stable_hash(main["plans"]["floors"][1:]),
        "source_floor1_hash": stable_hash(main["plans"]["floors"][0]),
        "inherited_windows_and_hvac_hash": stable_hash([{k: v for k, v in r["features"].items() if "window" in k or "hvac" in k} for r in main["plans"]["floors"][0]["rooms"]]),
        "preserved_washer_reference": [{"floor": f["id"], "id": i["id"]} for f in main["plans"]["floors"] for r in f["rooms"] for i in r["furniture"] if i["id"].endswith(":washer")],
        "historical_care_source_drift": drift, "historical_qa_reused": False, "frozen_selected_plans_checked_against_embedded_models": True,
        "protected_controls_unchanged": len(controls), "adopted": False, "professional_approval": "unknown", "rendered_qa": "not-run",
        "primary_abc_or_3d_changed": False, "full_scene_or_old_report_regenerated": False, "actual_site_or_product_data_received": 0,
        "conclusion": "C一樓獨立同版比較可串起新前置門、梯旁走道、孝親房入口與側盆／雙片浴室門；維持家具尺寸、樓梯與上層。僅列明方塊及門態成立，濕地分時、商品／救援、坐姿可及與機電仍未核。"}
    names = [CONFIG, cfg["protected_controls"], *cfg["pinned_sources"], "house_design/c_ground_coordination.py", "scripts/export_c_ground_coordination.py",
        "scripts/export_b_upper_replan.py", "scripts/export_abc_next_improvements.py", "scripts/export_builder_communication.py",
        "house_design/b_upper_replan.py", "house_design/contracts.py", "house_design/project_status.py", "Docs/c-ground-coordination-v1.md",
        "inputs/requirements.json", "inputs/planning-register.json"]
    report["source_hashes"] = {name: digest(root, name, cache) for name in names}
    report["report_hash"] = stable_hash(report)
    return report

"""Frozen-source outdoor/closed-room interfaces, not selected or routed MEP approval."""
from __future__ import annotations

import copy
import math
from pathlib import Path

from house_design.abc_fresh_air_layout import (
    area_overlap,
    contains,
    corridor_rects,
    lookup,
    polygon_rect_area,
    positive,
    protected_room,
    room_polygon,
)
from house_design.abc_fresh_air_layout import (
    build as parent_build,
)
from house_design.c_coordination import public_path
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash

CONFIG = "inputs/abc-fresh-air-detail.json"
OUT = "structured/coordination/abc-fresh-air-detail-v1"


def points(path):
    if not isinstance(path, list) or len(path) < 2:
        raise ContractError("Duct path needs at least two points")
    for p in path:
        if (not isinstance(p, list) or len(p) != 2 or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in p)):
            raise ContractError("Duct coordinates must be finite XY pairs")
    corridor_rects(path, 1)
    return path


def segments(paths):
    return [(a, b) for path in paths for a, b in zip(path, path[1:], strict=False)]


def on_segment(p, a, b):
    return (min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and
        min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))


def crosses(a, b, c, d):
    return (max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0])) and
        max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1])))


def connected(paths, origin):
    """Connectivity includes mid-segment taps, not only matching end vertices."""
    edges = segments(paths)
    reached = {i for i, (a, b) in enumerate(edges) if on_segment(origin, a, b)}
    while True:
        grown = reached | {i for i, (a, b) in enumerate(edges)
            if any(crosses(a, b, *edges[j]) for j in reached)}
        if grown == reached:
            return bool(edges) and len(reached) == len(edges)
        reached = grown


def on_network(p, network):
    return any(on_segment(p, a, b) for a, b in segments(network["paths"]))


def item_id(room, item):
    return item["id"] if item["id"].startswith(room["id"]+":") else room["id"]+":furniture:"+item["id"]


def projection_hits(rects, rooms):
    protected, furniture, kitchens = set(), set(), set()
    for rect in rects:
        for room in rooms:
            if polygon_rect_area(room_polygon(room), rect) <= .01:
                continue
            if protected_room(room):
                protected.add(room["id"])
            if "kitchen" in room["id"]:
                kitchens.add(room["id"])
            for item in room.get("furniture", []):
                if area_overlap(rect, item["rect_mm"]) > .01:
                    furniture.add(item_id(room, item))
    return {"protected_hits": sorted(protected), "furniture_xy_below_or_at_route": sorted(furniture),
        "sealed_kitchen_crossings": sorted(kitchens)}


def screen_paths(paths, width, rooms, external=False):
    bands = []
    for path in paths:
        points(path)
        if any(not (0 <= p[0] <= 6000 and 0 <= p[1] <= 17630) for p in path):
            raise ContractError("Duct point outside nominal building")
        bands.extend(corridor_rects(path, width))
    for x, y, w, d in bands:
        if x < 0 or x+w > 6000 or y < 0 or (not external and y+d > 17630):
            raise ContractError("Full duct band outside nominal building")
    result = projection_hits(bands, rooms)
    if result["protected_hits"]:
        raise ContractError("Duct band intersects protected/wet/stair rooms: "+str(result["protected_hits"]))
    return {**result, "swept_rects_mm": bands, "width_mm": width,
        "polyline_length_m": round(sum(math.dist(a, b) for a, b in segments(paths))/1000, 3),
        "actual_z_mm": None, "actual_pressure_loss_pa": None, "three_dimensional_fit_verified": False}


def stub(tap, end):
    raw = [tap, [end[0], tap[1]], end]
    path = [p for i, p in enumerate(raw) if i == 0 or p != raw[i-1]]
    return points(path)


def branch(original, net, roster, cfg):
    b = copy.deepcopy(original)
    room = lookup(roster, net["building"], net["floor"], b["room"])
    rooms = roster[net["building"]][net["floor"]]
    if not on_network(b["tap"], net):
        raise ContractError("Branch tap is disconnected: "+room["id"])
    b.update(id=room["id"], name=room["name"], building=net["building"], floor=net["floor"])
    side = cfg["terminal_marker_width_mm"]
    for role in ["SA", "RA"]:
        p = b[role]
        if not isinstance(p, list) or len(p) != 2:
            raise ContractError("Missing independent closed-room terminal")
        marker = [p[0]-side/2, p[1]-side/2, side, side]
        if room.get("outdoor") or protected_room(room) or "kitchen" in room["id"] or not contains(room, marker):
            raise ContractError("Ordinary terminal outside its indoor dry host: "+room["id"])
        if projection_hits([marker], rooms)["furniture_xy_below_or_at_route"]:
            raise ContractError("Terminal projects directly on a furniture body: "+room["id"]+":"+role)
        path = b.get(role+"_path", stub(b["tap"], p))
        if path[0] != b["tap"] or path[-1] != p:
            raise ContractError("Terminal stub has a disconnected tap or end")
        b[role+"_path"] = path
        b[role+"_screen"] = screen_paths([path], cfg["single_band_width_mm"], rooms)
    distance = math.dist(b["SA"], b["RA"])
    if distance < cfg["terminal_separation_study_goal_mm"]:
        raise ContractError("Terminal pair below the project-only separation study goal")
    b.update(terminal_plan_separation_mm=round(distance, 2), actual_supply_m3_h=None,
        actual_return_m3_h=None, ordinary_return_does_not_depend_on_door_gap=True,
        room_air_distribution_noise_pressure_verified=False,
        meaning="送回風各自密閉支路；開放區標籤不是新增房間。拓樸可關門，不是實測風量或消防／聲學核可。")
    return b


def opening_overlaps(room, face, point, width):
    poly = room_polygon(room)
    left, right = min(p[0] for p in poly), max(p[0] for p in poly)
    f = room.get("features", {})
    spans = [("door", d.get("ratio", .5), d["width_mm"]) for d in f.get("doors", [])
        if d["face"] == face]
    if f.get("window_face") == face and f.get("window_mm", 0) > 0:
        spans.append(("candidate-window", f.get("window_ratio", .5), f["window_mm"]))
    hits = []
    for kind, ratio, w in spans:
        center = left+(right-left)*ratio
        if max(point[0]-width/2, center-w/2) < min(point[0]+width/2, center+w/2):
            hits.append(kind)
    return {"same_wall_xy_opening_span_hits": hits,
        "existing_window_head_mm": f.get("window_sill_mm", 900)+f.get("window_height_mm", 1200)
            if "candidate-window" in hits else None,
        "opening_survey_complete": False,
        "interpretation": "同牆水平投影重疊需高位剖面核對，不表示與窗同高，也不允許直接改窗／鑽過梁。"}


def outdoor_group(original, net, roster, cfg):
    g = copy.deepcopy(original)
    if g["side"] not in {"front", "rear"}:
        raise ContractError("Do not assume access to a side/party wall")
    bid, fid = net["building"], net["floor"]
    g.update(building=bid, floor=fid)
    for role in ["OA", "EA"]:
        path = points(g[role+"_path"])
        if path[0] != net["origin_mm"]:
            raise ContractError("Outdoor route must start at its own unit interface")
        room = lookup(roster, bid, fid, g[role+"_room"])
        point, poly = path[-1], room_polygon(room)
        y = min(p[1] for p in poly) if g["side"] == "front" else max(p[1] for p in poly)
        if point[1] != y:
            raise ContractError("Outdoor terminal is not on its stated front/rear host wall")
        width = cfg["outdoor_opening_study_width_mm"]
        inside = [point[0]-width/2, y if g["side"] == "front" else y-width, width, width]
        if room.get("outdoor") or not contains(room, inside):
            raise ContractError("Outdoor port does not touch its dry indoor host")
        g[role+"_screen"] = screen_paths([path], cfg["single_band_width_mm"], roster[bid][fid], external=True)
        g[role+"_opening"] = opening_overlaps(room, g["side"], point, width)
    g.update(own_pair_horizontal_distance_mm=round(math.dist(g["OA_path"][-1], g["EA_path"][-1]), 2),
        actual_opening_z_mm=None, own_pair_or_neighbour_short_circuit_verified=False,
        legal_opening_and_access_verified=False, wall_beam_lintel_fire_rain_checked=False,
        adjacent_ABC_site_coordinates_mm=None, wind_and_pollution_source_positions_mm=None,
        approved=False,
        gates=["不得把自己兩口水平距離當排放合格門檻；需原廠／當地適用條件及風向核對。",
            "盤點本棟與鄰棟浴廁、油煙、香火、瓦斯設備、冷氣熱風、車道及可開窗，不能只量ERV兩口。",
            "前側騎樓／陽台不當可任意排放空間；後側有巷不等於取得外牆／開孔權利。",
            "無合法高位實牆即重排；保留原窗門、梁、防火及所有權條件。"])
    return g


def duct_section(columns, rows, cfg):
    positive([columns, rows])
    if any(isinstance(v, bool) or not isinstance(v, int) for v in [columns, rows]):
        raise ContractError("Duct section needs positive integer pipe counts")
    od = cfg["inner_diameter_mm"]+2*cfg["insulation_radial_mm"]
    return {"pipes": columns*rows, "columns": columns, "rows": rows, "outer_diameter_mm": od,
        "width_mm": columns*od+(columns-1)*cfg["pipe_gap_mm"]+2*cfg["edge_mm"],
        "height_mm": rows*od+(rows-1)*cfg["pipe_gap_mm"]+2*cfg["edge_mm"],
        "selected_product_or_insulation_verified": False}


def intersection(rects):
    x, y = max(r[0] for r in rects), max(r[1] for r in rects)
    w, d = min(r[0]+r[2] for r in rects)-x, min(r[1]+r[3] for r in rects)-y
    return [x, y, w, d] if min(w, d) > .01 else None


def crossing_interfaces(net, group):
    clean = net["screen"]["swept_rects_mm"]
    oa, ea = (group[role+"_screen"]["swept_rects_mm"] for role in ["OA", "EA"])
    overlaps = [r for a in clean for b in oa for c in ea if (r := intersection([a, b, c]))]
    return {"outdoor_group": group["id"], "network": net["id"],
        "potential_four_role_xy_intersections": len(overlaps), "sample_rects_mm": overlaps[:4],
        "z_separation_and_ports_unknown": True, "approved": False,
        "required_action": "同高四管不能塞500寬雙管帶；比較950×300橫排或500×500雙層，再合梁／消音／冷媒及檢修。"}


def removal_budget(panel, body, frame_each, hand_each):
    positive([*panel, *body])
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
            for v in [frame_each, hand_each]):
        raise ContractError("Removal allowances must be finite nonnegative numbers")
    clear = [v-2*frame_each for v in panel]
    required = [v+2*hand_each for v in body]
    margin = [a-b for a, b in zip(clear, required, strict=True)]
    return {"nominal_panel_mm": panel, "reference_plan_span_mm": body, "assumed_frame_each_mm": frame_each,
        "assumed_hand_each_mm": hand_each, "clear_panel_mm": clear, "required_straight_plan_mm": required,
        "margin_mm": margin, "straight_plan_budget_fits": min(margin) >= 0,
        "whole_product_replacement_verified": False,
        "meaning": "直向平面算術，未核重量、吊架、四接口、傾斜、落機、架梯、門轉角或全程運出。"}


def service_candidates(unit, rooms, width):
    x, y, w, d = unit["rect_mm"]
    rects = {"left": [x-width, y, width, d], "right": [x+w, y, width, d],
        "front": [x, y-width, w, width], "rear": [x, y+d, w, width]}
    result = []
    for face, r in rects.items():
        hits = projection_hits([r], rooms)
        outside = r[0] < 0 or r[1] < 0 or r[0]+r[2] > 6000 or r[1]+r[3] > 17630
        result.append({"side": face, "assumed_side_strip_mm": r, **hits, "outside_nominal_building": outside,
            "xy_clear_of_listed_protection_and_furniture": not outside and not hits["protected_hits"]
                and not hits["furniture_xy_below_or_at_route"],
            "actual_product_pull_distance_and_direction": None, "service_egress_approved": False})
    return {"unit": unit["id"], "building": unit["building"], "floor": unit["floor"], "sides": result,
        "selected_side": None, "interpretation": "600側條帶是試排假設，不是600檢修孔推導出的原廠抽拉長度；平面空不表示可安全架梯。"}


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    if cfg.get("adopted") is not False or cfg.get("selected_product") is not None:
        raise ContractError("Keep fresh-air detail unadopted and unselected")
    if cfg.get("scope") != "independent-closed-room-and-outdoor-interface-study":
        raise ContractError("Wrong detail comparison scope")
    if sha256_file(root/cfg["parent_report"]) != cfg["parent_file_sha256"]:
        raise ContractError("Fresh-air detail parent file changed")
    parent = parent_build(root)
    if parent["report_hash"] != cfg["parent_report_hash"]:
        raise ContractError("Fresh-air detail parent sources changed")
    if cfg["external_z_mm"] is not None or any(cfg["section_cases"][k] is not None for k in
            ["actual_beam_bottom_mm", "actual_finished_ceiling_z_mm", "actual_selected_product_section"]):
        raise ContractError("Do not promote assumed sections or hole heights to approved geometry")
    if len(cfg["pair_band_mm"]) != 2 or cfg["pair_band_mm"] != [500, 300]:
        raise ContractError("Retain stated pair band budget")
    for k in ["single_band_width_mm", "inner_diameter_mm", "insulation_radial_mm", "edge_mm",
            "pipe_gap_mm", "terminal_marker_width_mm", "terminal_separation_study_goal_mm",
            "outdoor_opening_study_width_mm", "service_side_strip_study_mm"]:
        positive([cfg[k]])
    if cfg["single_band_width_mm"] < cfg["inner_diameter_mm"]+2*cfg["insulation_radial_mm"]+2*cfg["edge_mm"]:
        raise ContractError("Single duct band cannot contain its insulation/edge budget")
    roster, units = parent["roster"], {u["id"]: u for u in parent["units"]}
    networks = []
    for original in cfg["networks"]:
        n = copy.deepcopy(original)
        u = units[n["unit"]]
        if (u["building"], u["floor"]) != (n["building"], n["floor"]):
            raise ContractError("Duct system crosses buildings or floors")
        for path in n["paths"]:
            points(path)
        n["origin_mm"] = n["paths"][0][0]
        p = n["origin_mm"]
        if not contains({"rect_mm": u["rect_mm"]}, [p[0]-.5, p[1]-.5, 1, 1]) or not connected(n["paths"], p):
            raise ContractError("Clean network is disconnected from its own unit")
        n["screen"] = screen_paths(n["paths"], cfg["pair_band_mm"][0], roster[n["building"]][n["floor"]])
        n.update(actual_unit_four_ports_mm=None, door_state_dependency="none-for-ordinary-ducted-return",
            full_mep_verified=False)
        networks.append(n)
    if len(networks) != 8 or len({n["id"] for n in networks}) != 8 or {n["unit"] for n in networks} != set(units):
        raise ContractError("Retain exactly the eight independent unit study networks")
    by_id = {n["id"]: n for n in networks}
    branches = [branch(b, by_id[b["network"]], roster, cfg) for b in cfg["branches"]]
    basis = read_json(root/parent["config"]["parent_report"])
    required = {bid+":"+z["floor"]+":"+key for b in basis["buildings"] for bid in [b["id"]]
        for z in b["zones"] for key in z["supply"]}
    if {b["id"] for b in branches} != required or len(branches) != len(required):
        raise ContractError("Do not drop any of the original dry-space service targets")
    groups = [outdoor_group(g, by_id[g["network"]], roster, cfg) for g in cfg["external_groups"]]
    if len({g["id"] for g in groups}) != len(groups) or len({(g["network"], g["side"]) for g in groups}) != len(groups):
        raise ContractError("Duplicate outdoor alternative or side")
    for n in networks:
        choices = {g["side"] for g in groups if g["network"] == n["id"]}
        if not choices or (n["building"] == "B" and choices != {"front", "rear"}):
            raise ContractError("Keep B independent no-rear-opening ventilation fallback")
    sections = {"two_flat": duct_section(2, 1, cfg), "four_flat": duct_section(4, 1, cfg),
        "four_stacked": duct_section(2, 2, cfg)}
    if sections["two_flat"]["width_mm"] > cfg["pair_band_mm"][0] or sections["two_flat"]["height_mm"] > cfg["pair_band_mm"][1]:
        raise ContractError("Paired corridor budget too small")
    clear_cases = []
    case = cfg["section_cases"]
    for h in case["underslab_clear_height_assumptions_mm"]:
        positive([h])
        for arrangement in ["four_flat", "four_stacked"]:
            zone = max(case["machine_connection_height_budget_mm"], sections[arrangement]["height_mm"])
            clear_cases.append({"hypothetical_underslab_clear_height_mm": h, "duct_arrangement": arrangement,
                "ceiling_drop_study_mm": zone+case["additional_hanging_tolerance_study_mm"],
                "highest_finished_ceiling_in_this_assumption_mm": h-zone-case["additional_hanging_tolerance_study_mm"],
                "actual_beam_bottom_mm": None, "legal_headroom_or_product_fit_verified": False})
    report = {"schema": "house-abc-fresh-air-detail-report-v1", "date": cfg["date"], "config": cfg,
        "parent_report_hash": parent["report_hash"], "source_layout_report_sha256": parent["source_layout_report_sha256"],
        "roster": roster, "units": parent["units"],
        "networks": networks, "branches": branches, "outdoor_groups": groups,
        "interfaces": [crossing_interfaces(by_id[g["network"]], g) for g in groups], "duct_sections": sections,
        "ceiling_cases": clear_cases,
        "service_candidates": [service_candidates(u, roster[u["building"]][u["floor"]], cfg["service_side_strip_study_mm"])
            for u in units.values()],
        "removal_cases": [removal_budget(p, [1230, 637], 25, cfg["removal_hand_margin_each_side_study_mm"])
            for p in [[1260, 700], [1600, 1000]]],
        "research": read_json(root/cfg["research"]), "actual_machine_count": None, "selected_product": None,
        "adopted": False, "full_MEP_fit_verified": False, "professional_approval": "unknown", "browser_qa": "not-run",
        "known_occupancy_total": 9, "unknown_peak_and_third_floor_occupancy_is_zero": False,
        "per_room_flow_not_duplicated_from_floor_total": True,
        "protected_controls_unchanged": parent["protected_controls_unchanged"],
        "retained_b_entries": parent["b_front_and_rear_retained"],
        "open_gates": ["外牆合法開孔、三棟基地相鄰座標及鄰戶污染源／風向", "原窗門與高位實牆、梁柱及防火剖面",
            "四接口／消音／冷媒相遇的三維斷面與完成天花", "真實產品最低風量／濾網積塵工作點及關門夜間實測",
            "地面架梯、照護／逃生與整機落機／全程運出", "B香火獨立補排及上層乾管的指定家規確認；兩衛外窗／原面積取捨不變"]}
    names = [CONFIG, cfg["parent_report"], *parent["source_hashes"], cfg["research"],
        "house_design/abc_fresh_air_detail.py", "scripts/export_abc_fresh_air_detail.py", "Docs/abc-fresh-air-detail-v1.md"]
    report["source_hashes"] = {n: sha256_file(public_path(root, n)) for n in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

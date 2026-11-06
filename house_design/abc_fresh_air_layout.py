"""Independent ERV reservations: exact concept-plan screens, never installation approval."""
from __future__ import annotations

import copy
import math
from pathlib import Path

from house_design.abc_fresh_air import build as parent_build
from house_design.abc_fresh_air import rosters
from house_design.c_coordination import public_path
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash

CONFIG = "inputs/abc-fresh-air-layout-options.json"
OUT = "structured/coordination/abc-fresh-air-layout-v1"
COST_FIELDS = ("equipment", "ducts_insulation_silencers", "outdoor_terminals_weatherproofing",
    "fire_structure", "electrical_controls", "ceiling_hatches", "commissioning",
    "annual_filters", "annual_labor", "annual_electricity", "ten_year_replacements")


def positive(values):
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values):
        raise ContractError("Reservation dimensions must be finite positive numbers")


def rect_polygon(r):
    x, y, w, d = r
    positive([w, d])
    if not all(math.isfinite(v) for v in [x, y]):
        raise ContractError("Reservation position must be finite")
    return [[x, y], [x+w, y], [x+w, y+d], [x, y+d]]


def room_polygon(room):
    return room["polygon_mm"] if "polygon_mm" in room else rect_polygon(room["rect_mm"])


def point_inside(p, polygon):
    x, y = p
    inside = False
    for a, b in zip(polygon, polygon[1:]+polygon[:1], strict=True):
        if (a[1] > y) != (b[1] > y) and x < a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1]):
            inside = not inside
    return inside


def polygon_rect_area(polygon, rect):
    """Exact grid decomposition for these orthogonal polygons, including concave B rooms."""
    for a, b in zip(polygon, polygon[1:]+polygon[:1], strict=True):
        if a[0] != b[0] and a[1] != b[1]:
            raise ContractError("Reservation screen only supports orthogonal room polygons")
    x, y, w, d = rect
    positive([w, d])
    xs = sorted({x, x+w, *(p[0] for p in polygon if x < p[0] < x+w)})
    ys = sorted({y, y+d, *(p[1] for p in polygon if y < p[1] < y+d)})
    return sum((right-left)*(bottom-top)
        for left, right in zip(xs, xs[1:], strict=False)
        for top, bottom in zip(ys, ys[1:], strict=False)
        if point_inside([(left+right)/2, (top+bottom)/2], polygon))


def area_overlap(a, b):
    return max(0, min(a[0]+a[2], b[0]+b[2])-max(a[0], b[0]))*max(
        0, min(a[1]+a[3], b[1]+b[3])-max(a[1], b[1]))


def contains(room, rect):
    return math.isclose(polygon_rect_area(room_polygon(room), rect), rect[2]*rect[3], abs_tol=.01)


def lookup(roster, bid, fid, key):
    return next(r for r in roster[bid][fid] if r["id"].split(":")[-1] == key)


def duct_section(budget):
    positive([budget[k] for k in ["inner_diameter_mm", "insulation_radial_mm", "pair_gap_mm", "edge_mm", "width_mm", "height_mm"]])
    outer = budget["inner_diameter_mm"]+2*budget["insulation_radial_mm"]
    required = 2*outer+budget["pair_gap_mm"]+2*budget["edge_mm"]
    return {**budget, "outer_diameter_mm": outer, "required_pair_width_mm": required,
        "width_margin_mm": budget["width_mm"]-required,
        "height_margin_mm": budget["height_mm"]-outer-2*budget["edge_mm"],
        "physical_product_fit_verified": False}


def velocity(flow, diameter):
    positive([diameter])
    if flow is None:
        return None
    if isinstance(flow, bool) or not isinstance(flow, (int, float)) or not math.isfinite(flow) or flow < 0:
        raise ContractError("Airflow must be nonnegative finite or explicitly unknown")
    return round(flow/3600/(math.pi*(diameter/2000)**2), 3)


def lifecycle_cost(values, years):
    """Unknown quotations stay unknown, never silently treated as free."""
    positive([years])
    if set(values) != set(COST_FIELDS):
        raise ContractError("Quotation must include every equal-scope cost field")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
            for v in values.values() if v is not None):
        raise ContractError("Quotation entries must be nonnegative finite costs")
    if any(v is None for v in values.values()):
        return None
    return sum(v*(years if k.startswith("annual_") else 1) for k, v in values.items())


def protected_room(room):
    key = room["id"].split(":")[-1].lower()
    return (any(token in key for token in ["stair", "bath", "mdf", "idf", "dry-protection"])
        or any(token in room["name"].upper() for token in ["MDF", "IDF"])
        or room.get("features", {}).get("stairs") is True)


def screen_unit(unit, roster, cfg):
    u = copy.deepcopy(unit)
    bid, fid, rect = u["building"], u["floor"], u["rect_mm"]
    if sorted(rect[2:]) != sorted(cfg["planning_envelope"]["unit_and_connections_mm"][:2]):
        raise ContractError("Unit candidate cannot shrink the common comparison envelope")
    room = lookup(roster, bid, fid, u["room"])
    if room.get("outdoor") or not contains(room, rect):
        raise ContractError("Unit reservation outside the stated indoor host: "+u["id"])
    hits, operations, protected = [], [], []
    for r in roster[bid][fid]:
        if protected_room(r):
            if polygon_rect_area(room_polygon(r), rect) > .01:
                protected.append(r["id"])
        for item in r.get("furniture", []):
            if area_overlap(rect, item["rect_mm"]) > .01:
                hits.append(item["id"])
            if item.get("operation_mm") and area_overlap(rect, item["operation_mm"]) > .01:
                operations.append(item["id"])
    if protected or hits:
        raise ContractError("Unit/service projection meets a protected room or fixed furniture: "+u["id"])
    u.update({"host_room_name": room["name"], "inside_nominal_host": True,
        "fixed_furniture_projection_hits": hits, "operation_projection_hits": operations,
        "protected_room_projection_hits": protected, "service_floor_rect_mm": rect[:],
        "service_egress_and_ladder_approved": False, "ceiling_beam_wall_door_checked": False,
        "full_filter_and_body_removal_verified": False, "actual_unit_and_port_geometry": None,
        "status": "plan-envelope-only-vertical-and-service-unknown"})
    return u


def corridor_rects(points, width):
    positive([width])
    result = []
    for a, b in zip(points, points[1:], strict=False):
        if sum(a[k] != b[k] for k in (0, 1)) != 1:
            raise ContractError("Duct corridor needs distinct orthogonal legs")
        result.append([min(a[0], b[0])-width/2, min(a[1], b[1])-width/2,
            abs(a[0]-b[0])+width, abs(a[1]-b[1])+width])
    return result


def screen_corridor(original, roster, cfg, ac01):
    r = copy.deepcopy(original)
    width = cfg["duct_budgets"]["floor_pair"]["width_mm"]
    sweeps = corridor_rects(r["points_mm"], width)
    forbidden, furniture, kitchens = set(), set(), set()
    for rect in sweeps:
        if rect[0] < 0 or rect[1] < 0 or rect[0]+rect[2] > 6000 or rect[1]+rect[3] > 17630:
            raise ContractError("Partial duct corridor outside nominal building")
        for room in roster[r["building"]][r["floor"]]:
            if polygon_rect_area(room_polygon(room), rect) <= .01:
                continue
            key = room["id"].split(":")[-1]
            if protected_room(room):
                forbidden.add(room["id"])
            if "kitchen" in key:
                kitchens.add(room["id"])
            for item in room.get("furniture", []):
                if area_overlap(rect, item["rect_mm"]) > .01:
                    furniture.add(item["id"])
    if forbidden:
        raise ContractError("Partial clean corridor intersects protected/wet/stair area: "+r["id"]+str(sorted(forbidden)))
    ac_boxes = []
    if r["building"] == "C":
        for a, b in zip(ac01["route"]["polyline_mm"], ac01["route"]["polyline_mm"][1:], strict=False):
            z0, z1 = (0, 4000) if r["floor"] == "floor-1" else (4000, 7000)
            if max(a[2], b[2])+75 <= z0 or min(a[2], b[2])-75 >= z1:
                continue
            ac_boxes.append([min(a[0], b[0])-75, min(a[1], b[1])-75, abs(a[0]-b[0])+150, abs(a[1]-b[1])+150])
    ac_hits = [(i, j) for i, a in enumerate(sweeps) for j, b in enumerate(ac_boxes) if area_overlap(a, b) > .01]
    r.update({"width_mm": width, "height_budget_mm": cfg["duct_budgets"]["floor_pair"]["height_mm"],
        "swept_rects_mm": sweeps, "protected_plan_hits": [], "fixed_body_xy_below_or_at_route": sorted(furniture),
        "sealed_kitchen_crossings": sorted(kitchens), "ac01_plan_crossings": ac_hits,
        "route_z_mm": None, "actual_outdoor_ports": None, "actual_supply_return_terminals": None,
        "all_floor_rooms_connected": False, "pressure_noise_condensation_fire_approved": False,
        "meaning": "平面局部帶，不是整層四管施工路由；有家具投影必須剖面合圖，無投影碰撞也不代表梁／門／淨高通過。"})
    return r


def screen_shaft(original, roster, cfg, bdetail):
    s = copy.deepcopy(original)
    r, bid = s["rect_mm"], s["building"]
    inside = {}
    for fid in s["floors"]:
        inside[fid] = [room["id"] for room in roster[bid][fid] if contains(room, r)]
        if len(inside[fid]) != 1:
            raise ContractError("Central shaft needs an unambiguous host on each studied floor")
    host = lookup(roster, bid, s["screen_floor"], s["host_room"])
    if not contains(host, r):
        raise ContractError("Central shaft left declared cross-section host")
    left, right = s["cross_section_x_mm"]
    strips = [max(0, r[0]-left), max(0, right-r[0]-r[2])]
    section = duct_section(cfg["duct_budgets"]["central_pair"])
    lining = cfg["duct_budgets"]["shaft_lining_each_side_mm"]
    s.update({"hosts_by_floor": inside, "reserved_each_floor_sqm": r[2]*r[3]/1e6,
        "remaining_side_strips_mm": strips, "max_straight_bypass_mm": max(strips),
        "meets_study_bypass_goal": max(strips) >= s["required_bypass_mm"],
        "lined_width_mm": r[2]-2*lining, "lined_depth_mm": r[3]-2*lining,
        "section_width_margin_mm": r[2]-2*lining-section["width_mm"],
        "section_depth_margin_mm": r[3]-2*lining-section["height_mm"],
        "candidate_rejected_here": True, "all_central_arrangements_impossible": False,
        "actual_fire_lining_structure_and_replacement_verified": False})
    if bid == "B":
        before = bdetail["geometry"]["retained_master_after_sqm"]
        s.update(master_before_new_shaft_sqm=before,
            master_after_new_shaft_sqm=round(before-s["reserved_each_floor_sqm"], 4),
            meets_original_master_20=before-s["reserved_each_floor_sqm"] >= 20)
    return s


def quote_rows(cfg):
    rows = []
    for bid in "ABC":
        for arch in ["building-central", "floor-zoned", "supply-with-designed-exit"]:
            costs = {k: None for k in cfg["cost_fields"]}
            rows.append({"building": bid, "architecture": arch,
                "scope": "同樣一二樓關門房／三樓使用區；B1香火另列但三案都不可漏報；同濾網、噪音與實測範圍",
                "price_currency": "TWD", "quote_date": None, "model_and_count": None,
                "actual_low_flow_at_pressure": None, "dirty_filter_pressure": None,
                "bedroom_night_noise": None, "OA_EA_legal_external_wall_positions": None,
                "filter_type_price_frequency": None, "shutdown_egress_and_replacement": None,
                **costs, "ten_year_cost": lifecycle_cost(costs, cfg["cost_horizon_years"]),
                "tax_warranty_scope": None, "contractor_evidence": None})
    return rows


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    if cfg.get("scope") != "independent-physical-reservation-comparison-not-routed-mep" or cfg.get("adopted") is not False or cfg.get("selected_product") is not None:
        raise ContractError("Keep ERV comparison unadopted and unselected")
    if sha256_file(root/cfg["parent_report"]) != cfg["parent_file_sha256"]:
        raise ContractError("Fresh-air reservation parent changed")
    parent = parent_build(root)
    if parent["report_hash"] != cfg["parent_report_hash"]:
        raise ContractError("Fresh-air reservation parent inputs changed")
    controls = read_json(root/cfg["protected_controls"])
    for name, digest in controls["hashes"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("Fresh-air reservation protected control changed: "+name)
    base = parent["config"]
    source = read_json(root/base["source_report"])
    bd = read_json(root/base["b_detail_report"])
    roster = rosters(source, bd, read_json(root/base["b_round3_report"]), read_json(root/base["b_strict_report"]), base)
    units = [screen_unit(u, roster, cfg) for u in cfg["units"]]
    required = {(b, "floor-"+str(f)) for b in "AC" for f in [1, 2, 3]} | {("B", "floor-2"), ("B", "floor-3")}
    if {(u["building"], u["floor"]) for u in units} != required or len(units) != 8:
        raise ContractError("Retain five occupied-floor and three current-use reservations, no ordinary B1 ERV")
    ids = {u["id"]: u for u in units}
    if len(ids) != len(units):
        raise ContractError("Duplicate unit reservation ID")
    for route in cfg["partial_clean_duct_corridors"]:
        unit = ids.get(route["unit"])
        if unit is None or (unit["building"], unit["floor"]) != (route["building"], route["floor"]):
            raise ContractError("Corridor must reference a unit on the same building and floor")
        if not contains({"rect_mm": unit["rect_mm"]}, [*route["points_mm"][0], 1, 1]):
            raise ContractError("Partial corridor must start inside its unit reservation")
    if any(u["phase"] != ("install-now" if u["floor"] != "floor-3" else "commission-with-current-use") for u in units):
        raise ContractError("Current-use third floors cannot be deferred to empty future rough-in")
    if set(cfg["cost_fields"]) != set(COST_FIELDS) or len(cfg["cost_fields"]) != len(COST_FIELDS):
        raise ContractError("Equal-scope quotation fields changed")
    corridors = [screen_corridor(r, roster, cfg, source["c_ac01_review"]) for r in cfg["partial_clean_duct_corridors"]]
    shafts = [screen_shaft(s, roster, cfg, bd) for s in cfg["central_shaft_tests"]]
    flow_rows = []
    for b in parent["buildings"]:
        for z in b["zones"]:
            for case in z["night_supply_estimate_cases"]:
                q = case["floor_total_m3_h"]
                flow_rows.append({"building": b["id"], "floor": z["floor"], "people": z["people"],
                    "per_person_assumption_m3_h": case["per_person_assumption_m3_h"], "illustrative_flow_m3_h": q,
                    "single_125mm_duct_velocity_m_s": velocity(q, 125),
                    "actual_minimum_machine_speed_at_pressure": None, "pressure_loss_pa": None,
                    "meaning": "分區風量總額，不是每房各得同風量；125是試排口徑，不是已選風口或噪音結論。"})
    report = {"schema": "house-abc-fresh-air-layout-report-v1", "date": cfg["date"], "config": cfg,
        "source_layout_report_sha256": parent["source_layout_report_sha256"], "parent_report_hash": parent["report_hash"],
        "roster": roster, "owner_people": {b["id"]: b["known_regular_people"] for b in parent["buildings"]},
        "units": units, "partial_corridors": corridors, "central_shaft_tests": shafts,
        "duct_sections": {k: duct_section(cfg["duct_budgets"][k]) for k in ["floor_pair", "central_pair"]},
        "flow_sensitivity": flow_rows, "builder_quotes": quote_rows(cfg), "fixed_gates": cfg["fixed_gates"],
        "conditional_recommendation": "先請建商同範圍報常用層分區案，中央案留替代；三個中央管井試點均不保留，不代表找不到別處。",
        "b_distribution_gap": "B2／B3只試後段局部。前側乾起居仍須送回風；不可省略或擅借乾背櫃室。前側獨立小系統或另條乾式高位帶由建商比較，未確認前不鎖一層一機；不新增未確認的乾風管宗教禁令，也不宣稱已符合。",
        "open_gates": ["實際梁板／完成天花、固定牆與檢修安全", "四接口與完整OA／EA外牆終端／防雨防短路",
            "各關門房的送回風末端／聲學／低速工作點", "浴室油煙香火同開補氣及含濕量／冷凝",
            "B前側乾起居分區路由／台數；原兩衛面積及無窗偏好仍未解", "三樓一期使用範圍／實際同時人數及法規審查"],
        "adopted": False, "selected_product": None, "actual_machine_count": None,
        "full_MEP_fit_verified": False, "professional_approval": "unknown", "browser_qa": "not-run",
        "protected_controls_unchanged": len(controls["hashes"]), "b_front_and_rear_retained": parent["retained_b_entries"]}
    names = [CONFIG, cfg["parent_report"], *parent["source_hashes"], cfg["protected_controls"],
        "house_design/abc_fresh_air_layout.py", "scripts/export_abc_fresh_air_layout.py",
        "scripts/export_abc_next_improvements.py", "Docs/abc-fresh-air-layout-v1.md"]
    report["source_hashes"] = {name: sha256_file(public_path(root, name)) for name in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

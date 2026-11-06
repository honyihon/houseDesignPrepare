"""Independent B upper-bath window/duct study; all terminal/product approvals stay unknown."""
from __future__ import annotations

import copy
import math
from itertools import combinations
from pathlib import Path

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from house_design.abc_next_improvements import selected, square_sweeps
from house_design.b_fengshui_strict import area_shape, collision, measured_room, rect_ring, ring, translate
from house_design.c_coordination import public_path
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash

CONFIG = "inputs/b-bath-ventilation.json"
OUT = "structured/coordination/b-bath-ventilation-v1"


def floor_screen(rooms, reservations, route, wet_ids, protected, storage, inset=115):
    shapes = [Polygon(r["polygon_mm"]) for r in rooms]
    united = unary_union(shapes)
    master = next(r for r in rooms if r["id"] in {"master", "guest"})
    inner = Polygon(master["polygon_mm"]).buffer(-inset, join_style=2)
    reserve = unary_union([area_shape(r) for r in reservations])
    route_boxes = square_sweeps(route, 900)
    furniture = master["furniture"]
    return {"partition_gap_or_outside_sqm": united.symmetric_difference(box(0, 11370, 6000, 17630)).area/1e6,
        "partition_overlap_sqm": (sum(s.area for s in shapes)-united.area)/1e6,
        "master_outline_115_sqm": round(inner.area/1e6, 6),
        "reserved_enclosure_sqm": round(reserve.area/1e6, 6),
        "master_after_enclosure_sqm": round((inner.area-reserve.area)/1e6, 6),
        "reservations_contained": inner.covers(reserve),
        "reservation_body_hits": [i["id"] for i in furniture if collision(reserve, area_shape(i["rect_mm"]))],
        "reservation_operation_hits": [i["id"] for i in furniture if collision(reserve, area_shape(i["operation_mm"]))],
        "master_bodies_and_operations_contained": all(inner.covers(area_shape(i[k])) for i in furniture
            for k in ["rect_mm", "operation_mm"]),
        "master_over_protected_sqm": Polygon(master["polygon_mm"]).intersection(protected).area/1e6,
        "wet_projection": [{"id": r["id"], "protected_overlap_sqm": Polygon(r["polygon_mm"]).intersection(protected).area/1e6,
            "storage_overlap_sqm": Polygon(r["polygon_mm"]).intersection(storage).area/1e6}
            for r in rooms if r["id"] in wet_ids],
        "route": {"points_mm": route, "sweeps_mm": route_boxes,
            "all_inside_115": all(inner.covers(area_shape(s)) for s in route_boxes),
            "body_hits": [{"segment": n, "body": i["id"]} for n, s in enumerate(route_boxes) for i in furniture
                if collision(area_shape(s), area_shape(i["rect_mm"]))],
            "enclosure_hits": [n for n, s in enumerate(route_boxes) if collision(area_shape(s), reserve)],
            "actual_whole_route": "unknown"},
        "full_door_states": "not-checked-products-and-sweeps-unknown", "professional_approval": "unknown"}


def bath_screen(room, shaft=None):
    fixtures = room["furniture"]
    finished = area_shape(room["illustrative_finished_rect_mm"])
    arrivals = area_shape(room["inside_approach_mm"])
    shaft_shape = area_shape(shaft) if shaft else Polygon()
    return {"bodies_inside": all(finished.covers(area_shape(i["rect_mm"])) for i in fixtures),
        "operations_inside": all(finished.covers(area_shape(i["operation_mm"])) for i in fixtures),
        "arrival_inside": finished.covers(arrivals),
        "body_hits": [[a["id"], b["id"]] for a, b in combinations(fixtures, 2)
            if collision(area_shape(a["rect_mm"]), area_shape(b["rect_mm"]))],
        "operation_other_body_hits": [[a["id"], b["id"]] for a in fixtures for b in fixtures
            if a is not b and collision(area_shape(a["operation_mm"]), area_shape(b["rect_mm"]))],
        "arrival_body_hits": [i["id"] for i in fixtures if collision(arrivals, area_shape(i["rect_mm"]))],
        "shaft_hits": [i["id"] for i in fixtures if collision(shaft_shape, area_shape(i["rect_mm"]))
            or collision(shaft_shape, area_shape(i["operation_mm"]))],
        "shaft_arrival_hit": collision(shaft_shape, arrivals),
        "shared_operation_pairs": [[a["id"], b["id"]] for a, b in combinations(fixtures, 2)
            if collision(area_shape(a["operation_mm"]), area_shape(b["operation_mm"]))],
        "outline_finished_sqm": finished.area/1e6,
        "dedicated_shaft_sqm": shaft_shape.area/1e6,
        "after_shaft_sqm": round((finished.area-shaft_shape.area)/1e6, 6)}


def new_bath(spec, rectangle, private, shaft, window=None):
    origin = [rectangle[0]+115, rectangle[1]+115]
    key = "private" if private else "public"
    fixtures = [{"id": k, "rect_mm": translate(v, origin),
        "operation_mm": translate(spec[key+"_operation_local_mm"][k], origin)}
        for k, v in spec[key+"_fixture_local_mm"].items()]
    if private:
        lo, hi = spec["private_door_x_mm"]
        y = rectangle[1]+rectangle[3]
        door = {"a": [lo, y], "b": [hi, y], "nominal_mm": hi-lo, "assumed_clear_mm": hi-lo-230,
            "operation": "從主臥後側入套衛；門組、鉸鏈與所有門態待定，不沿用原公衛前門。"}
        inside = [lo+115, y-115-900, 900, 900]
        outside = [lo+115, y+115, 900, 900]
    else:
        lo, hi = spec["public_door_x_mm"]
        y = rectangle[1]
        door = {"a": [lo, y], "b": [hi, y], "nominal_mm": hi-lo, "assumed_clear_mm": hi-lo-230,
            "operation": "從獨立右側公共通道到達；門框、門扇開啟與消防未核。"}
        inside = [lo+115, y+115, 900, 900]
        outside = [lo+115, y-115-900, 900, 900]
    room = measured_room(key+"-bath", "左前套衛" if private else "後右公衛／候選後窗",
        rect_ring(rectangle), fixtures, [door], copy.deepcopy(window))
    room.update(illustrative_finished_rect_mm=[*origin, rectangle[2]-230, rectangle[3]-230],
        inside_approach_mm=inside, outside_approach_mm=outside, actual_product_pack=None)
    room["screen"] = bath_screen(room, shaft if private else None)
    return room


def door_bed_screen(master, private):
    """Nominal orthogonal aperture projection only; not a complete 3D sightline certificate."""
    bed = next(i["rect_mm"] for i in master["furniture"] if i["id"] == "bed")
    a, b = private["doors"][0]["a"], private["doors"][0]["b"]
    if a[0] == b[0]:
        strip = box(0, min(a[1], b[1]), a[0], max(a[1], b[1]))
    else:
        strip = box(min(a[0], b[0]), a[1], max(a[0], b[0]), 17630)
    overlap = strip.intersection(area_shape(bed)).area/1e6
    return {"door_a_mm": a, "door_b_mm": b, "bed_mm": bed,
        "nominal_orthogonal_strip_mm": ring(strip), "bed_overlap_sqm": overlap,
        "status": "unresolved-door-projects-toward-bed" if overlap else "no-listed-orthogonal-overlap",
        "opaque_fixed_blocker": None, "actual_3d_and_diagonal_sightlines": "unknown",
        "note": "這是門口朝床的平面初篩，不是門片碰撞；關門不作消除對線的證明。"}


def duct_path(points, diameter, insulation, protected, storage, forbidden_strip, sewer, enclosure, roof_outdoors):
    # The square plan budget is conservative at elbows; it is not an elbow fabrication model.
    radius = diameter/2+insulation
    xy = [points[0][:2]]
    for p in points[1:]:
        if p[:2] != xy[-1]:
            xy.append(p[:2])
    shape = LineString(xy).buffer(radius, cap_style=3, join_style=2)
    length = sum(math.dist(a, b) for a, b in zip(points, points[1:], strict=False))
    shaft_shape = area_shape(enclosure)
    return {"points_mm": points, "diameter_assumption_mm": diameter, "insulation_each_assumption_mm": insulation,
        "outer_plan_budget_width_mm": diameter+2*insulation,
        "plan_budget_polygon_mm": ring(shape), "centerline_length_mm": round(length, 3),
        "protected_overlap_sqm": shape.intersection(protected).area/1e6,
        "storage_projection_overlap_sqm": shape.intersection(storage).area/1e6,
        "no_pipe_strip_overlap_sqm": shape.intersection(forbidden_strip).area/1e6,
        "sewage_shaft_overlap_sqm": shape.intersection(sewer).area/1e6,
        "enclosure_over_protected_sqm": shaft_shape.intersection(protected).area/1e6,
        "enclosure_over_storage_sqm": shaft_shape.intersection(storage).area/1e6,
        "enclosure_in_model_roof_outdoor": roof_outdoors.covers(shaft_shape),
        "as_built_length_mm": None, "pressure_loss_pa": None, "fan_model": None,
        "wall_slab_penetration_approval": "unknown", "roof_terminal_approval": "unknown",
        "hood_spacing_weatherproofing_and_air_intakes": "unknown"}


def mechanical_option(parent, cfg, protected, storage, roof_outdoors):
    prior = parent["variants"][1]
    m = cfg["mechanical"]
    floors = []
    for fid, key in [("floor-2", "rooms"), ("floor-3", "third_floor_rooms")]:
        rooms = copy.deepcopy(prior[key])
        for item in rooms[0]["furniture"]:
            if item["id"] in {"bed", "wardrobe"}:
                item["rect_mm"] = m[item["id"]+"_rect_mm"][:]
                r = item["rect_mm"]
                item["operation_mm"] = [r[0]+r[2], r[1], 600, r[3]]
        rooms[0]["hvac_candidate"] = {"id": "B-AC03" if fid == "floor-2" else "B-AC04",
            **copy.deepcopy(m["ac_candidate"])}
        floors.append({"id": fid, "rooms": rooms,
            "screen": floor_screen(rooms, [m["enclosure_mm"]], prior["route"]["points_mm"],
                {"public-bath", "private-bath"} if fid == "floor-2" else {"public-bath"}, protected, storage),
            "public_window": None, "vent_enclosures_mm": [m["enclosure_mm"]]})
    ducts = []
    for fid, xy in zip(["floor-2", "floor-3"], m["clear_pipe_centers_mm"], strict=True):
        base = cfg["floor_base_mm"][fid]
        grille_z, branch_z = base+m["design_ceiling_mm"], base+m["branch_center_relative_z_mm"]
        gx, gy = m["grille_xy_mm"]
        ry = m["branch_rear_y_mm"]
        points = [[gx, gy, grille_z], [gx, gy, branch_z], [gx, ry, branch_z], [xy[0], ry, branch_z], [*xy, branch_z],
            [*xy, m["roof_outlet_candidate_z_mm"]]]
        ducts.append({"floor": fid, **duct_path(points, m["duct_nominal_diameter_mm"], m["insulation_each_mm"],
            protected, storage, area_shape(prior["no_pipe_strip_mm"]), area_shape(prior["shaft"]["rect_mm"]),
            m["enclosure_mm"], roof_outdoors)})
    outside_d = m["duct_nominal_diameter_mm"]+2*m["insulation_each_mm"]
    circles = [area_shape([xy[0]-outside_d/2, xy[1]-outside_d/2, outside_d, outside_d])
        for xy in m["clear_pipe_centers_mm"]]
    ac = m["ac_candidate"]["rect_mm"]
    ac_plan = area_shape(ac)
    new_bed = next(i["rect_mm"] for i in floors[0]["rooms"][0]["furniture"] if i["id"] == "bed")
    airflow_strip = box(ac[0], ac[1]+ac[3], ac[0]+ac[2], 17630)
    ac_checks = {"body_inside_115": Polygon(floors[0]["rooms"][0]["polygon_mm"]).buffer(-115, join_style=2).covers(ac_plan),
        "new_nominal_airflow_strip_bed_overlap_sqm": airflow_strip.intersection(area_shape(new_bed)).area/1e6,
        "exhaust_plan_overlap_sqm": sum(ac_plan.intersection(Polygon(d["plan_budget_polygon_mm"])).area/1e6 for d in ducts),
        "actual_airflow_mirror_heights_and_service": "unknown", "refrigerant_and_condensate_route": None}
    return {"id": "keep-roof-exhaust", "label": "保房間位置／兩層獨立排氣到屋頂", "floors": floors,
        "ducts": ducts, "enclosure_mm": m["enclosure_mm"], "enclosure_sqm": area_shape(m["enclosure_mm"]).area/1e6,
        "two_pipe_budgets_contained": all(area_shape(m["enclosure_mm"]).covers(c) for c in circles),
        "two_pipe_budgets_overlap": collision(*circles),
        "public_after_sewer_sqm": prior["public_area_accounting"]["after_shaft_estimate_sqm"],
        "private_after_sewer_sqm": prior["current_inset_case"]["private_bath"],
        "master_after_reservations_sqm": floors[0]["screen"]["master_after_enclosure_sqm"],
        "public_exterior_window": False, "all_requirements_met": False, "adopted": False,
        "door_bed": door_bed_screen(floors[0]["rooms"][0], floors[0]["rooms"][-1]),
        "furniture_changes": "床前移1815mm、衣櫃後移2030mm，尺寸不縮；避套衛門正向投影，保原2400後窗。",
        "hvac_checks": ac_checks,
        "hvac_change": "原右牆機盒對新床有直吹疑慮，改前臂前壁上方盒體候選；實機、鏡高、氣流與管線待核。",
        "claude_status": "not-reviewed-new-ventilation-study",
        "separate_from_sewage_and_other_bath_exhaust": True,
        "unresolved": ["風量／靜壓／噪音與產品實圖", "梁板穿越、包覆防火、保溫冷凝與檢修",
            "屋頂排風帽、防颱、防水、距離進氣口及相鄰開口", "主臥扣豎道後20.0761㎡餘量很薄",
            "公衛沒有直接外窗，原兩衛5／6㎡目標仍未達"]}


def rear_window_option(parent, cfg, protected, storage, roof_outdoors):
    prior = parent["variants"][1]
    w, m = cfg["rear_window"], cfg["mechanical"]
    dry = copy.deepcopy(prior["rooms"][1])
    corridor = measured_room("public-corridor", "獨立公衛通道／不穿主臥", rect_ring(w["corridor_rect_mm"]))
    pub = new_bath(w, w["public_rect_mm"], False, None, w["candidate_window"])
    private = new_bath(w, w["private_rect_mm"], True, prior["shaft"]["rect_mm"])
    master_shape = box(0, 11370, 6000, 17630).difference(unary_union([
        Polygon(r["polygon_mm"]) for r in [dry, corridor, pub, private]]))
    lo, hi = w["master_door_y_mm"]
    entry = {"a": [4670, lo], "b": [4670, hi], "nominal_mm": hi-lo, "assumed_clear_mm": hi-lo-230,
        "operation": "從右側公共通道側入；完整門片、把手、內開掃掠及救援未定。"}
    master = measured_room("master", "主臥／有窗公衛重排代價", ring(master_shape),
        copy.deepcopy(prior["rooms"][0]["furniture"]), [entry, copy.deepcopy(private["doors"][0])],
        copy.deepcopy(prior["rooms"][0]["window"]))
    # The original right-wall unit would now be in the public corridor; do not inherit it as a bedroom unit.
    master["hvac_candidate"] = None
    master["hvac_status"] = "new-room-and-corridor-require-new-position-and-routing"
    master["inside_approach_mm"], master["outside_approach_mm"] = [3655, 13805, 900, 900], [4785, 13805, 900, 900]
    rooms = [master, dry, corridor, private, pub]
    en = w["private_vent_enclosure_mm"]
    screen = floor_screen(rooms, [en], w["master_route_points_mm"], {"public-bath", "private-bath"}, protected, storage)
    master_finished = master_shape.buffer(-115, join_style=2)
    corridor_finished = Polygon(corridor["polygon_mm"]).buffer(-115, join_style=2)
    arrivals = {"public_outside_in_corridor": corridor_finished.covers(area_shape(pub["outside_approach_mm"])),
        "master_outside_in_corridor": corridor_finished.covers(area_shape(master["outside_approach_mm"])),
        "master_inside_in_master": master_finished.covers(area_shape(master["inside_approach_mm"])),
        "private_outside_in_master": master_finished.covers(area_shape(private["outside_approach_mm"]))}
    arrivals["fixed_body_hits"] = [{"arrival": name, "body": i["id"]} for name, rectangle in
        [("master-inside", master["inside_approach_mm"]), ("private-outside", private["outside_approach_mm"])]
        for i in master["furniture"] if collision(area_shape(rectangle), area_shape(i["rect_mm"]))]
    third = copy.deepcopy(rooms)
    third[0]["id"], third[0]["name"] = "guest", "客房／沿用有窗公衛研究房形"
    third[3] = measured_room("front-dry", "左前乾式預留／不新增三樓套衛", private["polygon_mm"],
        doors=copy.deepcopy(private["doors"]))
    base = cfg["floor_base_mm"]["floor-2"]
    z = base+m["branch_center_relative_z_mm"]
    cx, cy = w["private_vent_pipe_center_mm"]
    points = [[1200, 12000, base+m["design_ceiling_mm"]], [1200, 12000, z], [1200, 13500, z],
        [cx, 13500, z], [cx, cy, z], [cx, cy, m["roof_outlet_candidate_z_mm"]]]
    duct = duct_path(points, 125, 25, protected, storage, area_shape(prior["no_pipe_strip_mm"]),
        area_shape(prior["shaft"]["rect_mm"]), en, roof_outdoors)
    return {"id": "rear-window-replan", "label": "後右有窗公衛／左前套衛／獨立公共通道", "floors": [
        {"id": "floor-2", "rooms": rooms, "screen": screen, "vent_enclosures_mm": [en]},
        {"id": "floor-3", "rooms": third, "screen": floor_screen(third, [en], w["master_route_points_mm"],
            {"public-bath"}, protected, storage), "vent_enclosures_mm": [en]}],
        "door_arrivals": arrivals, "ducts": [{"floor": "floor-2-private", **duct}],
        "public_after_sewer_sqm": pub["screen"]["after_shaft_sqm"],
        "private_after_sewer_sqm": private["screen"]["after_shaft_sqm"],
        "master_after_reservations_sqm": screen["master_after_enclosure_sqm"],
        "public_exterior_window": "candidate-rear-wall-legal-opening-unknown",
        "candidate_window": w["candidate_window"], "retained_sewer_shaft_mm": prior["shaft"]["rect_mm"],
        "public_corridor_nominal_width_mm": 1330, "public_corridor_width_if_115_each_mm": 1100,
        "old_master_ac_would_be_in_public_corridor": True,
        "door_bed": door_bed_screen(master, private), "ready_for_adoption": False,
        "all_requirements_met": False, "adopted": False, "claude_status": "not-reviewed-new-layout",
        "unresolved": ["主臥減至16.0889㎡，未獲同意降低20㎡目標", "移公衛改門、濕區與兩衛管線，套衛仍需獨立排氣",
            "後窗權利與有效開口未知；有窗仍需排濕、防水及防雨",
            "左前套衛後門正向投影碰床，尚未解決；不能用關門或門片不撞床當解法",
            "所有門態、鏡面、梁柱、空調、通道與私密性待核",
            "三樓只有後右公衛，左前保持乾區；過層套衛排水需防水／隔音合圖"]}


def airflow_study(parent, cfg):
    area = parent["variants"][1]["public_area_accounting"]["after_shaft_estimate_sqm"]
    height = cfg["mechanical"]["design_ceiling_mm"]/1000
    volume = area*height
    c = cfg["airflow_comparison"]
    return {"bathroom_area_estimate_sqm": area, "ceiling_height_assumption_m": height, "volume_estimate_m3": volume,
        "ach_cases": [{"air_changes_h": ach, "delivered_q_m3_h": round(volume*ach, 3)}
            for ach in c["air_changes_per_hour_assumptions"]],
        "design_basis": "8／10／12次只是工程比較假設，不是本案法定標準或除黴保證。",
        "velocity_cases": [{"diameter_mm": d, "q_m3_h": c["reference_q_m3_h"],
            "velocity_m_s": (c["reference_q_m3_h"]/3600)/(math.pi*(d/2000)**2)}
            for d in c["duct_diameter_cases_mm"]],
        "required_product_data": ["指定風量下的外部靜壓／P-Q曲線", "實際管徑、長度、彎頭、止回閥與排風帽阻力",
            "安裝後風口實測風量、噪音及震動", "門關時的補氣有效面積與進氣來源", "保溫、冷凝水處理、防火及防颱檢修"],
        "delivered_airflow_verified": None, "actual_free_air_rating_acceptable_as_design": False,
        "moisture_note": "有窗及抽風都不保證不發黴；室外潮濕時要比室內外含濕量，必要時另核除濕。",
        "makeup_air": "從一般公共乾區補氣；不借樓梯、乾保護室或浴室污排氣串接。門縫不能直接視為已足量。"}


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    for name, digest in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("B ventilation source changed: "+name)
    parent = read_json(root/cfg["parent_report"])
    for name, digest in parent["source_hashes"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("B ventilation parent dependency changed: "+name)
    source = read_json(root/cfg["source_report"])
    source_floors = selected(source, "b-rear-split")["floors"]
    if any(f["base_mm"] != cfg["floor_base_mm"].get(f["id"], f["base_mm"]) for f in source_floors):
        raise ContractError("B ventilation floor levels do not match the pinned model")
    roof_units = [{"id": u["id"], "rect_mm": [u["x_mm"]-u["width_mm"]/2,
        u["y_mm"]-u["depth_mm"]/2, u["width_mm"], u["depth_mm"]]}
        for f in source_floors if f["id"] == "floor-4" for r in f["rooms"]
        for u in r["features"].get("hvac_units", []) if u["type"] == "outdoor"]
    controls = read_json(root/cfg["protected_controls"])
    for name, digest in controls["hashes"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("B ventilation control changed: "+name)
    strict = read_json(root/cfg["strict_report"])
    protected = unary_union([Polygon(p) for p in strict["options"][0]["protected_polygons_mm"]])
    storage = area_shape(strict["options"][0]["palanquin_rect_mm"])
    roof = parent["stack_and_entry"]["options"][0]["roof_reference"]
    roof_outdoors = unary_union([area_shape(r["rect_mm"]) for r in roof["rooms"] if r["outdoor"]])
    options = [mechanical_option(parent, cfg, protected, storage, roof_outdoors),
        rear_window_option(parent, cfg, protected, storage, roof_outdoors)]
    for option in options:
        enclosure = option["floors"][0]["vent_enclosures_mm"][0]
        option["roof_enclosure_outdoor_unit_hits"] = [u["id"] for u in roof_units
            if collision(area_shape(enclosure), area_shape(u["rect_mm"]))]
        option["roof_weatherhood_size_and_service_clearance"] = None
    report = {"schema": "house-b-bath-ventilation-report-v1", "date": cfg["date"], "config": cfg,
        "source_layout_report_sha256": parent["source_layout_report_sha256"], "options": options,
        "airflow": airflow_study(parent, cfg), "protected_polygons_mm": strict["options"][0]["protected_polygons_mm"],
        "palanquin_rect_mm": strict["options"][0]["palanquin_rect_mm"],
        "roof_outdoor_unit_bodies": roof_units,
        "retained_entries": [{"id": o["id"], "states": [s["id"] for s in o["states"]],
            "floor1_hashes": {s["id"]: stable_hash(s["floor1"]) for s in o["states"]}}
            for o in parent["stack_and_entry"]["options"]],
        "source_of_floor1_data": cfg["parent_report"], "first_floor_unchanged": True,
        "original_targets_sqm": parent["original_targets_sqm"], "owner_ritual_answers": parent["owner_questions"],
        "side_window": {"legal_opening": None, "side_setback_mm": None,
            "status": "needs-boundary-wall-and-site-evidence-not-assumed-possible-or-forbidden"},
        "recommendation": "暫保留原房間位置，優先核獨立屋頂排氣；有窗重排保留比較，先不接受主臥由20減至16.0889㎡。",
        "decision": {"id": "B-UPPER-VENT-01", "status": "owner-preference-pending", "owner_answer": None,
            "question": "B二三樓一般公衛是否先保主臥20㎡，以獨立機械排氣深化？若公衛必須有窗，需再議重排與主臥面積。"},
        "protected_controls_unchanged": len(controls["hashes"]), "all_requirements_met": False,
        "adopted": False, "browser_qa": "not-run", "professional_approval": "unknown",
        "fengshui_scope": "只檢明列家規與幾何投影，不代表完整風水核可；本批新增方案Claude尚未審閱。"}
    names = [CONFIG, *cfg["pinned_sources"], *parent["source_hashes"], cfg["protected_controls"],
        "house_design/b_bath_ventilation.py", "scripts/export_b_bath_ventilation.py", "Docs/b-bath-ventilation-v1.md"]
    report["source_hashes"] = {n: sha256_file(root/n) for n in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

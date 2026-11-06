"""Source-bound concept overlay; missing discipline drawings stay unknown."""
from __future__ import annotations

import copy
import math
from collections import Counter
from pathlib import Path

from house_design.contracts import ContractError, read_json, sha256_file, stable_hash

CONFIG = "inputs/c-coordination-review.json"
OUT = "structured/coordination/c-current-v1"
STATUSES = {"nominal-no-conflict", "interface-pending", "unknown", "sensitivity-conflict"}


def public_path(root, name):
    p = Path(name)
    if p.is_absolute() or any(part in {"..", "."} or part.startswith(".") for part in p.parts):
        raise ContractError("Coordination source path must be local and public")
    full = (root/p).resolve()
    if not full.is_relative_to(root.resolve()):
        raise ContractError("Coordination source escapes project")
    return full


def cross_plane(points, axis, value):
    found = []
    for n, (a, b) in enumerate(zip(points, points[1:], strict=False)):
        delta = b[axis]-a[axis]
        if delta == 0:
            continue
        t = (value-a[axis])/delta
        if 0 <= t <= 1:
            p = [a[k]+t*(b[k]-a[k]) for k in range(3)]
            if not any(p == q["center_mm"] for q in found):
                found.append({"segment": n, "center_mm": p})
    return found


def rect_box(rect, low, high):
    x, y, w, d = rect
    return [x, y, low, x+w, y+d, high]


def intersect(a, b):
    return all(min(a[k+3], b[k+3]) > max(a[k], b[k]) for k in range(3))


def segment_box(a, b, radius):
    return [min(a[k], b[k])-radius for k in range(3)]+[max(a[k], b[k])+radius for k in range(3)]


def item_box(item, base):
    place = item["placement"]
    b, low = place["aabb"], base+place.get("mount_height_mm", 0)
    return [b["minX"], b["minY"], low, b["maxX"], b["maxY"], low+item["height_mm"]]


def unit_box(unit, base):
    w, d = unit["width_mm"], unit["depth_mm"]
    if unit["face"] in {"left", "right"}:
        w, d = d, w
    return rect_box([unit["x_mm"]-w/2, unit["y_mm"]-d/2, w, d],
        base+unit["mount_height_mm"], base+unit["mount_height_mm"]+unit["height_mm"])


def analyze(source, cfg, balcony_cfg):
    if (source.get("integration_revision") != 2 or source.get("ac01_route_revision") != 1
            or source.get("adopted") is not False or source.get("rendered_qa") != "not-run"):
        raise ContractError("Reassess coordination when the selected source layout changes")
    option = next(o for o in source["options"] if o["id"] == cfg["option"])
    state = next(s for s in option["states"] if s["id"] == cfg["state"])
    plans = copy.deepcopy(state["plans"])
    floors = {f["id"]: f for f in plans["floors"]}
    rooms = {r["id"]: r for f in floors.values() for r in f["rooms"]}
    ac01, detail = source["c_ac01_review"], source["c_detail"]
    route, radius = ac01["route"], ac01["bundle_half_width_budget_mm"]
    points = route["polyline_mm"]
    if not all(len(p) == 3 and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in p) for p in points):
        raise ContractError("Route coordinates must be finite 3D points")
    if any(sum(a != b for a, b in zip(p, q, strict=True)) != 1 for p, q in zip(points, points[1:], strict=False)):
        raise ContractError("Swept-box screen requires distinct orthogonal route legs")
    findings = []

    def issue(oid, title, status, values, responsible, action, scope):
        if status not in STATUSES:
            raise ContractError("Unknown concept-coordination result")
        findings.append({"id": oid, "title": title, "status": status, "measurements": values,
            "responsible": responsible, "required_reply": action, "scope": scope,
            "professional_status": "unknown", "reply_reference": None, "actual_reply": None})

    obstacles = [{"id": i["id"], "floor": f["id"], "box_mm": item_box(i, f["base_mm"])}
        for f in floors.values() for r in f["rooms"] for i in r["furniture"] if not i["placement"]["issues"]]
    bundles = [segment_box(a, b, radius) for a, b in zip(points, points[1:], strict=False)]
    collisions = [{"segment": n, "obstacle": ob["id"]} for n, box in enumerate(bundles)
        for ob in obstacles if intersect(box, ob["box_mm"])]
    indoor = ac01["new_indoor_body_mm"]
    unit_hits = [ob["id"] for ob in obstacles if intersect(indoor, ob["box_mm"])]
    issue("C-CO-01", "室內機與列明家具、冷媒包束", "interface-pending" if collisions or unit_hits else "nominal-no-conflict",
        {"furniture_screened": len(obstacles), "unit_hits": unit_hits, "pipe_hits": collisions,
            "unit_box_mm": indoor, "bundle_width_budget_mm": radius*2}, "空調／裝潢",
        "補實際機型、進出風、維修操作、接管方向與保溫包管外廓；再核實際完成牆面。",
        "只檢查列明家具盒體與正交管束；沒有梁柱、實際天花或完整維修外廓。")

    riser = ac01["riser_envelope_mm"]
    gates = [r["features"]["c_front_gate"] for r in rooms.values() if "c_front_gate" in r["features"]]
    approach_hits = []
    for gate in gates:
        low = floors[gate["floor"]]["base_mm"]
        for kind, rect in gate["approach_rectangles_mm"].items():
            if intersect(riser, rect_box(rect, low, low+2100)):
                approach_hits.append(gate["floor"]+":"+kind)
    issue("C-CO-02", "立管與門前預算、完整平台", "interface-pending" if approach_hits else "nominal-no-conflict",
        {"riser_box_mm": riser, "floor2_footprint_sqm": ac01["floor2_coordination_floor_footprint_sqm"],
            "sofa_y_gap_mm": ac01["upper_sofa_projection_gap_mm"], "front_approach_hits": approach_hits,
            "shared_platform_depth_mm": detail["shared_level_apron_mm"][3]}, "建築師／裝潢／機電",
        "核包管、檢修口及門片退盡所需外廓，保留平台及門前操作；不得縮平台湊設備。",
        "門前高度2100mm僅展示預算，未驗實際門組、側門掃掠或照護全路徑。")

    specifications = [
        ("P01", "1F公衛後方隔牆", 1, rooms["C:floor-1:public-bath"]["geometry"]["y_mm"]+rooms["C:floor-1:public-bath"]["geometry"]["h_mm"],
            "C:floor-1:public-bath", "隔牆上部且投影落在公衛滑門範圍；門楣／梁及套管待核"),
        ("P02", "1F→2F樓板穿越", 2, floors["floor-2"]["base_mm"],
            "C:floor-2:living2f", "新穿板位，沒有梁、鋼筋、套管及防火填塞圖；不可按此座標鑽孔"),
        ("P03", "2F前外牆穿出", 1, rooms["C:floor-2:living2f"]["geometry"]["y_mm"],
            "C:floor-2:living2f", "前窗與陽台門間牆帶；柱梁、門窗框、防水、維修與固定待核"),
    ]
    penetrations = []
    for oid, title, axis, value, rid, note in specifications:
        crossings = cross_plane(points, axis, value)
        if len(crossings) != 1:
            raise ContractError("Expected one distinct crossing for "+oid)
        p = crossings[0]["center_mm"]
        penetrations.append({"id": oid, "title": title, "room": rid, "axis": axis, "plane_mm": value,
            **crossings[0], "bundle_box_mm": [p[k]-radius for k in range(3)]+[p[k]+radius for k in range(3)],
            "pipe_bundle_budget_mm": radius*2, "actual_hole_size_mm": None, "actual_sleeve": None,
            "structural_clearance": "unknown", "fire_waterproofing_and_access": "unknown", "note": note})
    issue("C-CO-03", "三處穿越與梁板／門楣", "unknown", {"penetrations": [p["id"] for p in penetrations],
        "verified_structural_geometry": None}, "建築師／結構技師／機電",
        "按P01～P03回覆梁柱、板厚、鋼筋、孔徑、套管、防火／防水及檢修圖號，與局部控制點對位。",
        "未提供結構圖，沒有繪製假梁柱，不能形成無結構干涉的結論。")

    upper = rooms["C:floor-2:living2f"]
    feat, geom = upper["features"], upper["geometry"]
    win_mid = geom["x_mm"]+geom["w_mm"]*feat["window_ratio"]
    door = next(d for d in feat["doors"] if d["face"] == "front")
    door_mid = geom["x_mm"]+geom["w_mm"]*door["ratio"]
    openings = {"window_x_mm": [win_mid-feat["window_mm"]/2, win_mid+feat["window_mm"]/2],
        "window_bottom_z_mm": floors["floor-2"]["base_mm"]+feat["window_sill_mm"],
        "window_top_z_mm": floors["floor-2"]["base_mm"]+feat["window_sill_mm"]+feat["window_height_mm"],
        "door_x_mm": [door_mid-door["width_mm"]/2, door_mid+door["width_mm"]/2],
        "door_top_illustrative_z_mm": floors["floor-2"]["base_mm"]+2100}
    p03 = next(p for p in penetrations if p["id"] == "P03")
    top_budget = floors["floor-3"]["base_mm"]-p03["bundle_box_mm"][5]
    issue("C-CO-04", "2F門窗、天花與高位包管", "interface-pending",
        {**openings, "front_opening_x_margins_mm": ac01["nominal_front_opening_margins_mm"],
            "pipe_bottom_to_nominal_window_head_mm": p03["bundle_box_mm"][2]-openings["window_top_z_mm"],
            "pipe_top_z_mm": p03["bundle_box_mm"][5], "upper_floor_datum_to_pipe_top_mm": top_budget,
            "actual_beam_bottom_z_mm": None, "actual_ceiling_bottom_z_mm": None}, "建築師／結構技師／裝潢／空調",
        "回覆梁底、吊頂及框外尺寸；高位包管頂+6425mm，不能把3F基準+7000mm當成實際板底。",
        "175／225mm僅名義開口邊距；門高2100是展示值，575mm是到上層基準的預算。")

    drain = copy.deepcopy(ac01["condensate_gravity_budget"])
    start = points[0][:2]
    bath_room = rooms["C:floor-1:public-bath"]
    bath_rear = bath_room["geometry"]["y_mm"]+bath_room["geometry"]["h_mm"]
    drain.update(stub_plan_mm=[start, [start[0], bath_rear]],
        port_z_mm=None, terminal_point_mm=None, slope_selected_percent=None,
        pipe_diameter_mm=None, access_points=None, cross_wall="1F公衛後方隔牆",
        interpretation="只到公衛後界的候選支管方向，不是接入馬桶或污水的完整排水線。")
    issue("C-CO-05", "冷凝水重力坡降與合法接管", "unknown", drain, "水電／空調／建築師",
        "補實際出水口標高、連續坡降、管徑、保溫、清理、防臭／隔離接法及合法終端；不隨冷媒向上走。",
        "800mm只到隔牆；8／12／16mm是敏感度，尚無終端，不增排水泵。")
    issue("C-CO-06", "公衛、洗曬及景觀給排水／排氣", "unknown",
        {"public_bath_legal_exhaust_point": bath_room["features"]["moisture_control"]["independent_outdoor_exhaust"]["legal_discharge_point"], "rainwater_point_mm": None,
            "laundry_waste_point_mm": None, "vent_pipe_mm": None}, "水電／機電／建築師",
        "分列馬桶污水、洗槽／洗衣廢水、冷凝水、雨水／溢流及排氣出口；提供標高、清理及通氣圖。",
        "源模型未定位排水終端，沒有把污水、雨水、冷媒立管合成同一管井。")

    balcony = rooms["C:floor-2:balcony2f"]
    zone = balcony["features"]["kaohsiung_zones"]
    trunk_distances = []
    route_x = next(p for p in penetrations if p["id"] == "P03")["center_mm"][0]
    for n, (x, y) in enumerate(zone["woody_points_mm"]):
        if 275 <= y <= 3900:
            trunk_distances.append({"tree": n+1, "point_mm": [x, y], "horizontal_centerline_distance_mm": abs(x-route_x)})
    issue("C-CO-07", "高位冷媒線與景觀樹冠、固定面", "interface-pending",
        {"tree_projection_distances": trunk_distances, "pipe_center_z_mm": points[4][2],
            "mature_canopy_height_mm": None, "approved_support_geometry": None}, "景觀／空調／建築師／結構技師",
        "第3株示意中心距高位線投影20mm；保留景觀目標，合併調整樹冠／管線固定與清理方式後回圖。",
        "目前未選樹種成熟冠幅，20mm是投影提醒，非實際樹冠碰撞或可修剪結論。")

    sens = balcony_cfg["section_sensitivity"]
    layer = balcony_cfg["section_comparison"]["illustrative_other_layers_mm"]
    soil_cases = []
    for soil in balcony_cfg["load_sensitivity"]["soil_depths_mm"]:
        under = floors["floor-2"]["base_mm"]-soil-sens["illustrative_slab_thickness_mm"]-layer
        soil_cases.append({"soil_mm": soil, "illustrative_underside_z_mm": under,
            "margin_to_target_mm": under-sens["conservative_arcade_clearance_target_mm"]})
    issue("C-CO-08", "景觀降板、土層與騎樓高度預算", "sensitivity-conflict",
        {"soil_cases": soil_cases, "illustrative_slab_mm": sens["illustrative_slab_thickness_mm"],
            "illustrative_other_layers_mm": layer, "coordination_target_mm": sens["conservative_arcade_clearance_target_mm"],
            "actual_soil_depth_mm": None, "actual_ground_datum_mm": None}, "建築師／結構技師／景觀／水電",
        "核根域、飽和荷重、槽底與梁底、地坪基準、防水／排水／溢流；零餘量案例不能視為已可蓋。",
        "土300＋板150＋其他50時名義底為3500mm，未計梁、工差及地面高差；3500非本報告認定的適用法定值。")

    system_rows, by_room = [], {}
    for f in floors.values():
        for r in f["rooms"]:
            for u in r["features"].get("hvac_units", []):
                if u["type"] != "indoor":
                    continue
                by_room.setdefault(r["id"], []).append(u["id"])
                rt = u["route"]
                system_rows.append({"id": u["id"], "room": r["id"], "outdoor_room": rt["outdoor_room"],
                    "estimated_length_mm": rt["estimated_routed_length_mm"], "elevation_difference_mm": rt["elevation_difference_mm"],
                    "product_model": rt["model"], "manual": rt["manual_source"], "compliance": rt["compliance"]})
    duplicate_rooms = {rid: ids for rid, ids in by_room.items() if len(ids) > 1}
    issue("C-CO-09", "同室兩套冷氣與全棟選型", "interface-pending",
        {"multiple_indoor_units": duplicate_rooms, "systems": len(system_rows), "selected_products": sum(r["product_model"] is not None for r in system_rows)},
        "空調設計／屋主／建築師", "C-AC04及C-AC07同屬前左客房，補服務範圍及逐室負荷，釐清雙機或歷史重複預留後再採購。",
        "不擅自刪機、換容量或視為配對已核；本次只是機位及路徑套繪。")
    gap = min((abs(a["x_mm"]-b["x_mm"])-(a["width_mm"]+b["width_mm"])/2)
        for n, a in enumerate(balcony["features"]["hvac_units"]) for b in balcony["features"]["hvac_units"][n+1:])
    issue("C-CO-10", "室外機散熱、換機、用電與排水", "unknown",
        {"minimum_nominal_adjacent_body_gap_mm": gap, "legal_front_fixing": None,
            "manual_service_clearance_mm": None, "circuit_and_isolator": None}, "空調／電氣／建築師／結構技師",
        "補各面吸排風／維修、搬入更換、防颱支架、震動、專用電路／隔離開關、防雨與排水圖。",
        "100mm機身間隙不等散熱與閥側空間；不假設可鎖共壁或欄杆。")
    issue("C-CO-11", "前置門、側門、梯井板洞與消防", "unknown",
        {"front_nominal_mm": 1200, "front_actual_clear_mm": None, "side_nominal_mm": 900,
            "side_actual_clear_mm": None, "platform_depth_mm": detail["shared_level_apron_mm"][3],
            "forbidden_platform_mm": detail["second_floor_floor_level_platform_removed_mm"],
            "headroom_proxy_mm": detail["headroom_proxy"]["minimum_sampled_gap_mm"], "actual_beams_and_headroom": None},
        "建築師／結構技師／門商／消防", "核門框、密封、開關／救援／消防與板洞、護欄、扶手、實際全寬淨高；保留完整平台。",
        "2850mm是離散模型試算，不是實際梁板淨高；不把3D刪底板當成結構洞口核可。")
    issue("C-CO-12", "基地與正式圖面對位", "unknown",
        {"local_frame_mm": [6000, 17630], "surveyed_registration": None,
            "legacy_R000_is_current_structure": False, "external_inputs": cfg["external_inputs"]},
        "建築師／測量／結構技師", "補正式圖號、版本、共同高程及至少兩個平面控制點；再把套繪對入實際梁柱及可建外框。",
        "6×17.63m為概念外框，非地籍、完成面或每層可建面積證明。")
    return {"schema": cfg["schema"], "status": cfg["status"], "building": "C", "option": cfg["option"],
        "state": cfg["state"], "coordinate_axis": cfg["coordination_axis"], "coordinate_registration": "unverified-local-concept",
        "professional_approval": "unknown", "construction_ready": False, "layout_changed": False,
        "plans": plans, "ac01": copy.deepcopy(ac01), "stair_detail": copy.deepcopy(detail),
        "penetrations": penetrations, "drainage": drain, "openings": openings, "systems": system_rows,
        "soil_cases": soil_cases, "findings": findings, "counts": dict(Counter(i["status"] for i in findings)),
        "structural_entities": None, "formal_coordination_engine_used": False,
        "formal_engine_reason": "正式引擎要求已核對位及專業多邊形；本資料為概念尺寸，未冒填 verified。"}


def build(root):
    cfg = read_json(root/CONFIG)
    if (cfg.get("schema") != "house-c-concept-coordination-v1" or cfg.get("option") != "c-split"
            or cfg.get("state") != "daily" or cfg.get("professional_approval") != "unknown"
            or cfg.get("drawing_floors") != ["floor-1", "floor-2"]
            or cfg.get("status") != "concept-overlay-awaiting-discipline-drawings"):
        raise ContractError("Preserve explicit C concept scope and unknown approval")
    if any(v is not None for group in cfg["external_inputs"].values() for k, v in group.items() if k != "responsible"):
        raise ContractError("External discipline inputs require verified registration, not text approval")
    report_path = public_path(root, cfg["source_report"])
    if sha256_file(report_path) != cfg["source_report_sha256"]:
        raise ContractError("Selected C source changed; review a new coordination basis")
    source = read_json(report_path)
    for name, digest in {**source["source_hashes"], **source["artifact_hashes"]}.items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("Current C dependency changed: "+name)
    balcony = read_json(root/"inputs/c-balcony-coordination.json")
    result = analyze(source, cfg, balcony)
    files = [CONFIG, cfg["source_report"], "inputs/c-balcony-coordination.json", "inputs/project.json",
        "inputs/revisions/R000/manifest.json", "inputs/revisions/R000/normalized_model.json",
        "house_design/c_coordination.py", "scripts/export_c_coordination.py", "Docs/coordination-review.md"]
    result["source_hashes"] = {**source["source_hashes"], **source["artifact_hashes"],
        **{name: sha256_file(root/name) for name in files}}
    result["source_layout_report_sha256"] = cfg["source_report_sha256"]
    result["parent_source_and_artifacts_verified"] = [len(source["source_hashes"]), len(source["artifact_hashes"])]
    result["report_hash"] = stable_hash(result)
    return result

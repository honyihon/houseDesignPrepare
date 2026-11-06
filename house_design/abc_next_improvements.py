"""Five bounded, source-pinned design studies. No scene generation or adoption."""
from __future__ import annotations

import copy
import math
from collections import Counter
from pathlib import Path

from house_design.c_coordination import public_path, rect_box, segment_box, unit_box
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash

CONFIG = "inputs/abc-next-improvements.json"
PRODUCTS = "inputs/abc-product-fit-candidates.json"
PROTECTED = "inputs/abc-next-protected-controls.json"
OUT = "structured/coordination/abc-next-v1"


def rect(room):
    return [room["geometry"][k] for k in ("x_mm", "y_mm", "w_mm", "h_mm")]


def item_rect(item):
    b = item["placement"]["aabb"]
    return [b["minX"], b["minY"], b["maxX"]-b["minX"], b["maxY"]-b["minY"]]


def overlap(a, b):
    return max(0, min(a[0]+a[2], b[0]+b[2])-max(a[0], b[0])) * max(
        0, min(a[1]+a[3], b[1]+b[3])-max(a[1], b[1]))


def inside(a, b, eps=.01):
    return all((a[k] >= b[k]-eps and a[k]+a[k+2] <= b[k]+b[k+2]+eps) for k in (0, 1))


def room_map(plans):
    return {r["id"]: r for f in plans["floors"] for r in f["rooms"]}


def selected(source, oid, state="daily"):
    return next(s["plans"] for o in source["options"] if o["id"] == oid for s in o["states"] if s["id"] == state)


def floor(plans, fid):
    return next(f for f in plans["floors"] if f["id"] == fid)


def compact(plans, ids=None):
    return [{"id": f["id"], "base_mm": f["base_mm"], "rooms": [
        {"id": r["id"], "name": r["name"], "rect_mm": rect(r), "outdoor": r["outdoor"],
         "features": copy.deepcopy(r["features"]), "furniture": [
             {"id": i["id"], "label": i["label"], "shape": i["shape"], "rect_mm": item_rect(i),
              "width_mm": i["width_mm"], "depth_mm": i["depth_mm"], "height_mm": i["height_mm"],
              "placement": copy.deepcopy(i["placement"])} for i in r["furniture"]]}
        for r in f["rooms"]]} for f in plans["floors"] if ids is None or f["id"] in ids]


def square_sweeps(points, width):
    sweeps = []
    for a, b in zip(points, points[1:], strict=False):
        if sum(x != y for x, y in zip(a, b, strict=True)) != 1:
            raise ContractError("Care rectangle study requires distinct orthogonal segments")
        sweeps.append([min(a[0], b[0])-width/2, min(a[1], b[1])-width/2,
                       abs(a[0]-b[0])+width, abs(a[1]-b[1])+width])
    return sweeps


def care_study(plans, cfg):
    rooms = room_map(plans)
    bath, elder = rooms["A:floor-1:bath1"], rooms["A:floor-1:flex1"]
    hall, passage = rooms["A:floor-1:rear-hall1"], rooms["A:floor-1:care-passage"]
    b, e, h, p = map(rect, [bath, elder, hall, passage])
    shared_bath = min(b[1]+b[3], p[1]+p[3])-max(b[1], p[1])
    shared_elder = min(e[0]+e[2], h[0]+h[2])-max(e[0], h[0])
    small, wide = copy.deepcopy(cfg["small"]), copy.deepcopy(cfg["wider"])
    new_b = [wide["new_bath_left_mm"], *b[1:]]
    new_b[2] = b[0]+b[2]-new_b[0]
    new_p, new_h = p[:], h[:]
    new_p[2], new_h[2] = new_b[0]-p[0], new_b[0]-h[0]
    elder_items = {i["id"].split(":")[-1]: item_rect(i) for i in elder["furniture"]}
    original_sizes = {i["id"]: [i["width_mm"], i["depth_mm"]] for r in (elder, bath) for i in r["furniture"]}
    new_elder = copy.deepcopy(elder_items)
    new_elder["bed"][0] += wide["elder_bed_shift_mm"][0]
    new_elder["bed"][1] += wide["elder_bed_shift_mm"][1]
    new_elder["wardrobe"] = wide["elder_wardrobe_rect_mm"]
    sweeps = square_sweeps(wide["elder_route_centerline_mm"], wide["route_square_budget_mm"])
    obstacles = [{"id": k, "rect_mm": v} for k, v in new_elder.items()]
    obstacles.extend({"id": k+"-park", "rect_mm": v} for k, v in wide["door_parking_rects_mm"].items())
    hits = [{"segment": n, "body": ob["id"]} for n, sw in enumerate(sweeps)
            for ob in obstacles if overlap(sw, ob["rect_mm"]) > .01]
    turn_hits = [k for k, r in wide["bath_fixture_rects_mm"].items() if overlap(wide["bath_turn_rect_mm"], r) > .01]
    proposed = list(wide["bath_fixture_rects_mm"].items())
    fixture_hits = [[a, bb] for n, (a, ra) in enumerate(proposed)
                    for bb, rb in proposed[n+1:] if overlap(ra, rb) > .01]
    inset = wide["illustrative_wall_inset_mm"]
    finished_b = [new_b[0]+inset, new_b[1]+inset, new_b[2]-2*inset, new_b[3]-2*inset]
    small_bodies = {i["id"].split(":")[-1]: item_rect(i) for i in bath["furniture"]}
    small_bodies["shower"] = small["shower_rect_mm"]
    small_approach = [b[0], small["bath_opening_y_mm"][0], 900, 1200]
    small["body_approach_hits"] = [k for k, r in small_bodies.items() if overlap(small_approach, r) > .01]
    wide.update(bath_rect_mm=new_b, passage_rect_mm=new_p, hall_rect_mm=new_h,
        elder_fixture_rects_mm=new_elder, elder_route_sweeps_mm=sweeps,
        bath_area_sqm=new_b[2]*new_b[3]/1e6, area_transferred_to_dry_sqm=(b[2]-new_b[2])*b[3]/1e6,
        bath_illustrative_inset_rect_mm=finished_b, route_body_hits=hits, bath_turn_body_hits=turn_hits,
        bath_fixture_body_hits=fixture_hits,
        bath_inset_contains_bodies=all(inside(r, finished_b) for r in wide["bath_fixture_rects_mm"].values()),
        bath_turn_min_fixture_gap_mm=wide["bath_fixture_rects_mm"]["vanity"][0]-(wide["bath_turn_rect_mm"][0]+1500),
        elder_1200_route_side_gaps_mm=[sweeps[-1][0]-(new_elder["bed"][0]+new_elder["bed"][2]),
            new_elder["wardrobe"][0]-(sweeps[-1][0]+sweeps[-1][2])],
        all_sizes_preserved=sorted(sorted(v) for v in original_sizes.values()) == sorted(
            sorted(r[2:]) for r in [*new_elder.values(), *wide["bath_fixture_rects_mm"].values()]),
        operation_overlap_note="衣櫃取物與1200方塊路徑、洗手盆操作與浴室1500迴轉分時。20mm名義餘量偏小，不是工差或真人可用證據。",
        net_clearance_status="unknown", care_and_religious_status="unknown", adopted=False)
    # The underlying model's back wall, upper wet projections and all furniture sizes stay explicit.
    bed_wet = []
    for f in plans["floors"]:
        if f["id"] == "floor-1":
            continue
        for r in f["rooms"]:
            if any(i["shape"] == "toilet" for i in r["furniture"]):
                area = overlap(rect(r), new_elder["bed"])/1e6
                if area:
                    bed_wet.append({"floor": f["id"], "room": r["id"], "overlap_sqm": round(area, 6)})
    wide["bed_upper_wet_projection"] = bed_wet
    return {"control_floor": compact(plans, ["floor-1"])[0], "control_bath_rect_mm": b,
        "control_elder_rect_mm": e, "control_shared_bath_wall_mm": shared_bath,
        "control_shared_elder_wall_mm": shared_elder, "original_sizes_mm": original_sizes,
        "small": small, "wider": wide,
        "clear_sensitivity": [{"aperture_mm": aperture, "deduction_mm": d, "clear_mm": aperture-d,
            "margin_to_900_mm": aperture-d-cfg["door_clear_target_mm"]}
            for aperture in [900, 1050, 1200] for d in cfg["illustrative_frame_total_deductions_mm"]],
        "limits": ["門組、門楣及完成面未知；實際900目標未核。", "A1浴室仍無已確認合法外窗，需獨立排氣補氣。",
                   "房門仍有床尾視線；關門不等於家規幾何已消除。", "A2套衛選擇另案；本研究不縮減原需求。"]}


def b_study(source, cfg):
    options = []
    for oid in ["b-rear-split", "b-front-split"]:
        shaft = cfg["shaft_rects_by_option_mm"][oid]
        plans = selected(source, oid)
        rooms = room_map(plans)
        backing = rect(rooms[cfg["protected_backing_room"]])
        altar = next(item_rect(i) for i in rooms["B:floor-1:shrine"]["furniture"] if i["shape"] == "altar")
        wet, fixture_projections, shaft_hits = [], [], []
        shaft_operations = []
        for f in plans["floors"]:
            for r in f["rooms"]:
                for i in r["furniture"]:
                    if overlap(shaft, item_rect(i)):
                        shaft_hits.append({"floor": f["id"], "body": i["id"]})
                    op = i["placement"].get("operation_mm")
                    if op and overlap(shaft, [op["minX"], op["minY"], op["maxX"]-op["minX"], op["maxY"]-op["minY"]]):
                        shaft_operations.append(i["id"])
                if f["id"] == "floor-1" or not any(i["shape"] == "toilet" for i in r["furniture"]):
                    continue
                wet.append({"floor": f["id"], "room": r["id"], "rect_mm": rect(r),
                    "over_backing_sqm": round(overlap(rect(r), backing)/1e6, 6),
                    "over_altar_body_sqm": round(overlap(rect(r), altar)/1e6, 6)})
                for i in r["furniture"]:
                    if overlap(item_rect(i), backing):
                        fixture_projections.append({"floor": f["id"], "item": i["id"],
                            "over_backing_sqm": round(overlap(item_rect(i), backing)/1e6, 6)})
        first = rooms["B:floor-1:bath-approach"]
        main_door = next(d for d in rooms["B:floor-1:shrine-front"]["features"]["doors"] if d["face"] == "front")
        front_rect = rect(rooms["B:floor-1:shrine-front"])
        door_center = front_rect[0]+front_rect[2]*main_door["ratio"]
        opt = {"id": oid, "floors": compact(plans), "backing_rect_mm": backing, "altar_rect_mm": altar,
            "wet_projections": wet, "fixture_projections": fixture_projections,
            "shaft_rect_mm": shaft, "shaft_body_hits": shaft_hits, "shaft_operation_hits": shaft_operations,
            "bath_approach_remaining_nominal_width_mm": (shaft[0]-rect(first)[0]
                if overlap(shaft, rect(first)) else rect(first)[2]),
            "street_door_nominal_mm": main_door["width_mm"], "street_axis_x_mm": door_center,
            "altar_axis_x_mm": altar[0]+altar[2]/2,
            "wet_area_over_backing_by_floor_sqm": {fid: round(sum(r["over_backing_sqm"] for r in wet if r["floor"] == fid), 6)
                for fid in ("floor-2", "floor-3")},
            "state_preserved": {st: {"plans_hash": stable_hash(selected(source, oid, st)),
                "floor1": compact(selected(source, oid, st), ["floor-1"])[0]} for st in cfg["required_states"]},
            "adopted": False, "stack_hole_size_mm": None, "drain_terminal_mm": None,
            "waterproofing_test_report": None, "continuous_1500_carried_route": "unknown",
            "recommendation": "先維持獨立乾背牆、朝街中軸與兩版搬轎；外緣立管列工程預留，不在法器櫃開檢修。",
            "religious_decision": "是否禁止背櫃上方整片濕區仍待家規確認；若禁止，須另重排上層浴室，立管與防水無法取代此決策。"}
        options.append(opt)
    return {"options": options, "recommended_shaft_status": "budget-only-awaiting-discipline-drawings",
        "drainage_layers": [
            {"system": "污水／通氣", "scope": "2／3F便器支管→外緣立管→1F法定終端；坡度／落口／通氣尺寸未知。"},
            {"system": "淋浴／盆廢水", "scope": "與污水分列設計、獨立存水彎與清理；不假設共管或背櫃暗管已准。"},
            {"system": "雨水／冷凝水", "scope": "分列合法終端，不接成一條未核污水管；後巷不是排放許可。"}],
        "detail_requests": ["濕區降板、整體防水上翻、管根與門檻細節、試水方法及保固責任。",
            "立管補強、穿板套管／防火、同層支管坡降、清掃口向可維修乾區。",
            "實際裝桿武轎、抬行人員與後巷權利／門外高差；前門分時整備另獨立演練。",
            "KTV、主臥20㎡、家務乾衣目標仍按原需求對帳，不能因有比較圖自動刪除。"]}


def path_length(points):
    return sum(math.dist(a, b) for a, b in zip(points, points[1:], strict=False))


def point_segment_distance(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


def hvac_study(plans, cfg):
    room = room_map(plans)[cfg["guestroom"]]
    area = rect(room)[2]*rect(room)[3]/1e6
    units = [copy.deepcopy(u) for u in room["features"]["hvac_units"] if u["id"] in cfg["unit_ids"]]
    if sorted(u["id"] for u in units) != sorted(cfg["unit_ids"]):
        raise ContractError("Reassess guestroom comparison when the two AC identities change")
    lengths = {u["id"]: u["route"]["estimated_routed_length_mm"] for u in units}
    return {"room": room["id"], "nominal_area_sqm": area, "room_drawing": compact(plans, ["floor-2"])[0],
        "units": units, "pipe_length_difference_mm": lengths["C-AC04"]-lengths["C-AC07"],
        "load_sensitivity": [{"w_per_sqm": w, "kw": round(area*w/1000, 4)} for w in cfg["sensitivity_w_per_sqm"]],
        "load_note": cfg["load_scope_note"], "preference": cfg["preference"],
        "options": [
            {"id": "rear-single", "use": ["C-AC04"], "retained_alternative": ["C-AC07"],
                "benefit": "減少前景觀側一台機位需求，送風不從前床頭位置開始。",
                "cost": "14.185m概念路徑，衣櫃頂到原機身底150mm，拆洗／氣流及跨區穿牆仍待手冊。"},
            {"id": "front-single", "use": ["C-AC07"], "retained_alternative": ["C-AC04"],
                "benefit": "概念管線10.085m，較後端短4.1m。",
                "cost": "室內機投影靠床頭／前窗；前方3台散熱及景觀配管未解，須核導風與清潔。"},
            {"id": "dual-control", "use": ["C-AC04", "C-AC07"], "retained_alternative": [],
                "benefit": "只有經確認的備援或不同負荷用途才有額外價值。",
                "cost": "同一10.36㎡房兩機增加設備、清潔、電路及機位成本；不能把雙機當省電結論。"}],
        "actual_load_kw": None, "selected_models": [], "adopted": False,
        "served_room_exclusion": "客房關門時，不拿客房機補起居、廚房或樓梯的負荷。"}


def landscape_study(source, plans, cfg):
    balcony = room_map(plans)["C:floor-2:balcony2f"]
    zones = balcony["features"]["kaohsiung_zones"]
    original = source["c_ac01_review"]["route"]
    current = original["polyline_mm"]
    cut = next(n for n, p in enumerate(current) if p == [4450, 3900, 6350])
    bypass = current[:cut]+cfg["left_bypass_after_p03_mm"]
    variants = []
    for oid, label, trees, points in [
            ("control", "原線／原植栽（保留對照）", zones["woody_points_mm"], current),
            ("tree-spacing", "P1調植栽位置、保留原線", cfg["tree_relayout_points_mm"], current),
            ("left-bypass", "P2原植栽、高位線左繞（優先核）", zones["woody_points_mm"], bypass)]:
        # Plan distance only: no fabricated mature crown height or structural supports.
        outdoor = [p for p in points if p[1] <= 3900]
        distances = [min(point_segment_distance(p, a, b) for a, b in zip(outdoor, outdoor[1:], strict=False)) for p in trees]
        minimum = min(distances)
        length = path_length(points)+original["bend_service_allowance_mm"]
        hits = []
        for f in plans["floors"]:
            for r in f["rooms"]:
                obs = [(i["id"], rect_box(item_rect(i), f["base_mm"]+i["placement"].get("mount_height_mm", 0),
                        f["base_mm"]+i["placement"].get("mount_height_mm", 0)+i["height_mm"])) for i in r["furniture"]]
                obs.extend((u["id"]+"-"+u["type"], unit_box(u, f["base_mm"])) for u in r["features"].get("hvac_units", [])
                           if not (u["id"] == "C-AC01" and u["type"] == "indoor"))
                for n, (a, b) in enumerate(zip(points, points[1:], strict=False)):
                    box = segment_box(a, b, cfg["pipe_half_budget_mm"])
                    for key, ob in obs:
                        if all(min(box[k+3], ob[k+3]) > max(box[k], ob[k]) for k in range(3)):
                            # End connection to its own outdoor body is intentional, not free clearance.
                            hits.append({"segment": n, "body": key, "own_connection": key == "C-AC01-outdoor"})
        variants.append({"id": oid, "label": label, "trees_mm": trees, "polyline_mm": points,
            "tree_centerline_plan_distances_mm": [round(d, 3) for d in distances],
            "minimum_plan_distance_mm": round(minimum, 3), "estimated_pipe_length_mm": round(length),
            "extra_length_mm": round(length-original["estimated_routed_length_mm"]),
            "canopy_sensitivity": [{"radius_mm": rad, "margin_with_pipe_and_buffer_mm": round(minimum-rad
                -cfg["pipe_half_budget_mm"]-cfg["additional_canopy_buffer_mm"], 3)}
                for rad in cfg["illustrative_canopy_radii_mm"]], "body_hits": hits,
            "actual_canopy_and_support": "unknown", "adopted": False})
    other_routes = []
    for r in room_map(plans).values():
        for unit in r["features"].get("hvac_units", []):
            if unit["type"] != "indoor" or unit["id"] not in {"C-AC03", "C-AC07"}:
                continue
            pp = [p for p in unit["route"]["polyline_mm"] if p[1] <= 3900]
            distance = min(point_segment_distance(t, a, b) for t in zones["woody_points_mm"]
                           for a, b in zip(pp, pp[1:], strict=False))
            other_routes.append({"id": unit["id"], "minimum_tree_centerline_plan_distance_mm": round(distance),
                "status": "另需同步核樹冠／支架；P2僅改AC01，沒有宣稱全棟空調已解。"})
    garden = zones["garden_mm"]
    return {"balcony_floor": compact(plans, ["floor-2"])[0], "garden_rect_mm": garden,
        "soil_rects_mm": zones["soil_rects_mm"], "garden_sqm": garden[2]*garden[3]/1e6,
        "soil_sqm": round(sum(r[2]*r[3] for r in zones["soil_rects_mm"])/1e6, 6),
        "woody_count": len(zones["woody_points_mm"]), "all_laundry_sizes_preserved": True,
        "variants": variants, "other_front_routes": other_routes,
        "preference": "先核P2：保原植栽／洗曬，代價是AC01增加5.4m；20m機型不能按20.895m概念值硬套。",
        "remaining": ["P2不是降低管線，仍須核+6350高位支承、梁板、門窗及檢修。",
            "多系統不能共用同一150mm包束假設；AC03及保留時的AC07另需並排／錯高設計。",
            "土深、飽和荷重、防水排水、騎樓零餘量及法定景觀資格仍待正式資料。"]}


def fit_rect(item, width, depth):
    """Hold the representative body's back plane; this never verifies its rough-in."""
    old = item_rect(item)
    rotation = round(item["placement"]["rotation_deg"]) % 360
    if rotation == 0:
        return [old[0]+old[2]/2-width/2, old[1]+old[3]-depth, width, depth]
    if rotation == 180:
        return [old[0]+old[2]/2-width/2, old[1], width, depth]
    if rotation == 90:
        return [old[0]+old[2]-depth, old[1]+old[3]/2-width/2, depth, width]
    if rotation == 270:
        return [old[0], old[1]+old[3]/2-width/2, depth, width]
    raise ContractError("Product fit requires an orthogonal representative fixture")


def product_study(source, catalog):
    rows, quote, doors, ac_rows, baths = [], [], [], [], []
    products = catalog["products"]
    by_id = {p["id"]: p for p in products}
    for oid in ["a-rear-study", "b-rear-split", "b-front-split", "c-split"]:
        plans = selected(source, oid)
        current_rooms = room_map(plans)
        bld = oid[0].upper()
        for f in plans["floors"]:
            for room in f["rooms"]:
                fixtures = [i for i in room["furniture"] if i["shape"] in {"toilet", "vanity"}]
                is_bath = any(i["shape"] == "toilet" for i in fixtures)
                care = room["id"] in {"A:floor-1:bath1", "B:floor-1:rear-bath", "C:floor-1:elder-bath"}
                if is_bath:
                    shower = any(i["shape"] == "shower" for i in room["furniture"])
                    basin = next((i for i in fixtures if i["shape"] == "vanity"), None)
                    storage_large = basin is not None and basin["width_mm"] >= 900
                    baths.append({"option": oid, "room": room["id"], "care": care, "shower": shower,
                        "large_storage_retained": storage_large})
                    package = "CARE-SEPARATE" if care else "LARGE-BASIN-SEPARATE" if storage_large else "FULL-1/2/3" if shower else "WC-1/2/3"
                    quote.append({"option": oid, "building": bld, "room_or_system": room["id"], "kind": "bath-package",
                        "quantity": 1, "candidate": package, "scope": "便器／蓋／盆龍頭"+("／淋浴" if shower else "（無淋浴）"),
                        "material_only_historical_twd": None, "model_returned": None, "material_twd": None,
                        "accessories_twd": None, "reinforcement_twd": None, "installation_twd": None,
                        "transport_twd": None, "tax_twd": None, "standard_credit_twd": None, "net_installed_twd": None,
                        "warranty": None, "lead_time": None, "formal_quote_reference": None})
                    for item in fixtures:
                        for product in products:
                            if product["kind"] != ("toilet" if item["shape"] == "toilet" else "basin"):
                                continue
                            w, height, d = product["body_whd_mm"]
                            body = fit_rect(item, w, d)
                            hits = [i["id"] for i in room["furniture"] if i["id"] != item["id"] and overlap(body, item_rect(i)) > .01]
                            loss = item["shape"] == "vanity" and item["width_mm"] >= 900
                            status = ("care-product-response-required" if care else "storage-capacity-not-equivalent" if loss
                                      else "exceeds-representative-body" if not inside(body, item_rect(item))
                                      else "body-only-candidate")
                            rows.append({"option": oid, "building": bld, "room": room["id"], "item": item["id"],
                                "product": product["id"], "model": product["model"], "status": status,
                                "representative_rect_mm": item_rect(item), "candidate_rect_mm": body,
                                "candidate_height_mm": height, "other_body_hits": hits,
                                "finished_room_contains_body": "unknown", "rough_in_as_built_mm": None,
                                "candidate_rough_in_mm": product.get("rough_in_mm"), "valve_and_service_envelope": None,
                                "cabinet_door_swing": None, "mounting_and_care_approval": "unknown",
                                "adopted": False})
                for d in room["features"]["doors"]:
                    neighbor = d.get("neighbor")
                    if (neighbor and neighbor < room["id"] and any(
                            reverse.get("neighbor") == room["id"] for reverse in current_rooms[neighbor]["features"]["doors"])):
                        continue
                    doors.append({"option": oid, "room": room["id"], "neighbor": d.get("neighbor"),
                        "face": d["face"], "aperture_mm": d["width_mm"], "operation": d.get("operation", "unknown"),
                        "actual_full_open_clear_mm": None, "complete_product": None,
                        "clear_if_230_total_mm": d["width_mm"]-230, "is_assumption_only": True,
                        "care_or_ritual_transport_status": "unknown"})
                for u in room["features"].get("hvac_units", []):
                    if u["type"] != "indoor":
                        continue
                    for product in products:
                        if product["kind"] != "hvac":
                            continue
                        actual = product["indoor_whd_mm"]
                        margin = [u["width_mm"]-actual[0], u["height_mm"]-actual[1], u["depth_mm"]-actual[2]]
                        ac_rows.append({"option": oid, "system": u["id"], "room": room["id"], "product": product["id"],
                            "indoor_body_margins_whd_mm": margin,
                            "length_budget_mm": u["route"]["estimated_routed_length_mm"],
                            "length_index_margin_mm": product["catalog_index_max_pipe_mm"]-u["route"]["estimated_routed_length_mm"],
                            "service_area_and_actual_load_kw": None, "current_install_manual": None,
                            "compatibility": "body-or-load-and-manual-pending", "adopted": False})
                    quote.append({"option": oid, "building": bld, "room_or_system": u["id"], "kind": "hvac-complete-set",
                        "quantity": 1, "candidate": "K28/36/40/50依負荷另比，不代表分配或採用", "scope": "精確配對／管線／電路／支架／排水／試車",
                        "material_only_historical_twd": None, "model_returned": None, "material_twd": None,
                        "accessories_twd": None, "reinforcement_twd": None, "installation_twd": None,
                        "transport_twd": None, "tax_twd": None, "standard_credit_twd": None, "net_installed_twd": None,
                        "warranty": None, "lead_time": None, "formal_quote_reference": None})
        for d in (d for d in doors if d["option"] == oid):
            quote.append({"option": oid, "building": bld,
                "room_or_system": d["room"]+" → "+(d["neighbor"] or "戶外")+" / "+d["face"],
                "kind": "complete-door-set", "quantity": 1,
                "candidate": f"{d['aperture_mm']}mm名義洞／{d['operation']}；未核完整門組",
                "scope": "框軌片五金／把手鎖／補強／完成淨寬／救援與密封依用途另核",
                "model_returned": None, "material_twd": None, "accessories_twd": None, "reinforcement_twd": None,
                "installation_twd": None, "transport_twd": None, "tax_twd": None, "standard_credit_twd": None,
                "net_installed_twd": None, "warranty": None, "lead_time": None, "formal_quote_reference": None})
    k, t, c, h = [by_id[i]["historical_material_price_twd"] for i in ("WC-K", "WC-T", "BS-C", "BS-H")]
    shower_price = 3960
    return {"candidate_catalog": catalog, "fit_rows": rows, "door_rows": doors, "hvac_rows": ac_rows,
        "quote_rows": quote, "bathrooms": baths,
        "counts_by_option": {oid: {"bathrooms": sum(b["option"] == oid for b in baths),
            "hvac_sets": sum(q["option"] == oid and q["kind"] == "hvac-complete-set" for q in quote),
            "doors_unique": sum(d["option"] == oid for d in doors)} for oid in ["a-rear-study", "b-rear-split", "b-front-split", "c-split"]},
        "packages": [{"id": "1", "models": ["WC-K", "BS-C", "HCG BF3731"], "historical_full_material_twd": k+c+shower_price,
                      "visitor_no_shower_twd": k+c},
                     {"id": "2", "models": ["WC-T", "BS-C", "HCG BF3731"], "historical_full_material_twd": t+c+shower_price,
                      "visitor_no_shower_twd": t+c},
                     {"id": "3", "models": ["WC-K", "BS-H", "HCG BF3731"], "historical_full_material_twd": k+h+shower_price,
                      "visitor_no_shower_twd": k+h}],
        "quote_rule": "B前後版互斥，C客房AC04/07若單機亦互斥；每包自行計數，禁止相加成全案訂購量。候選型號不等於已配容量。",
        "care_responses_changed": False, "formal_quote_status": "not-received"}


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    source_path = public_path(root, cfg["source_report"])
    if sha256_file(source_path) != cfg["source_report_sha256"]:
        raise ContractError("Current design source changed; reassess five studies before export")
    protected = read_json(root/PROTECTED)
    for name, digest in protected["hashes"].items():
        path = public_path(root, name)
        if sha256_file(path) != digest:
            raise ContractError("Protected control changed: "+name)
    source, catalog = read_json(source_path), read_json(root/PRODUCTS)
    report = {"schema": "house-abc-next-improvements-report-v1", "revision": 1, "adopted": False,
        "professional_approval": "unknown", "rendered_qa": "not-run-static-comparisons",
        "source_layout_report_sha256": cfg["source_report_sha256"], "source_layout_report": cfg["source_report"],
        "protected_control_count": len(protected["hashes"]), "previous_rendered_sources_unchanged": protected["previous_rendered_qa_source_count"],
        "config": cfg, "a_care": care_study(selected(source, "a-rear-study"), cfg["a_care"]),
        "b_coordination": b_study(source, cfg["b_coordination"]),
        "c_hvac": hvac_study(selected(source, "c-split"), cfg["c_hvac"]),
        "c_landscape": landscape_study(source, selected(source, "c-split"), cfg["c_landscape"]),
        "products": product_study(source, catalog)}
    report["source_hashes"] = {p: sha256_file(root/p) for p in [CONFIG, PRODUCTS, PROTECTED,
        "house_design/abc_next_improvements.py", "house_design/c_coordination.py", "house_design/contracts.py",
        "scripts/export_abc_next_improvements.py"]}
    report["product_fit_status_counts"] = dict(Counter(r["status"] for r in report["products"]["fit_rows"]))
    report["report_hash"] = stable_hash(report)
    return report

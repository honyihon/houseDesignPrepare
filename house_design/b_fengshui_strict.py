"""Explicit B ritual constraints; source-pinned polygons, not fengshui certification."""
from __future__ import annotations

import copy
from pathlib import Path

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from house_design.abc_next_improvements import compact, rect, room_map, selected, square_sweeps
from house_design.c_coordination import public_path
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash

CONFIG = "inputs/b-fengshui-strict-study.json"
OUT = "structured/coordination/b-fengshui-strict-v1"


def area_shape(r):
    return box(r[0], r[1], r[0]+r[2], r[1]+r[3])


def ring(shape):
    if shape.geom_type != "Polygon" or not shape.is_valid:
        raise ContractError("Study rooms must be one valid polygon")
    return [list(p) for p in shape.exterior.coords][:-1]


def rect_ring(r):
    x, y, w, d = r
    return [[x, y], [x+w, y], [x+w, y+d], [x, y+d]]


def translate(r, origin):
    return [r[0]+origin[0], r[1]+origin[1], *r[2:]]


def collision(a, b):
    return a.intersection(b).area > .01


def measured_room(rid, name, polygon, items=None, doors=None, window=None):
    shape = Polygon(polygon)
    ring(shape)
    return {"id": rid, "name": name, "polygon_mm": polygon, "nominal_area_sqm": round(shape.area/1e6, 6),
        "furniture": items or [], "doors": doors or [], "window": window, "adopted": False}


def bath(cfg, spec, rid, name, private=False):
    inset = cfg["bath_layout_inset_mm"]
    r = cfg["private_bath_rect_mm" if private else "public_bath_rect_mm"]
    origin = [r[0]+inset, r[1]+inset]
    usable = [*origin, r[2]-2*inset, r[3]-2*inset]
    fixtures = [{"id": key, "rect_mm": translate(body, origin),
                 "operation_mm": translate(spec["operations_local_mm"][key], origin)}
                for key, body in spec["fixtures_local_mm"].items()]
    if private:
        lo, hi = spec["door_nominal_y_mm"]
        clear_lo, clear_hi = spec["door_clear_illustrative_y_mm"]
        a, b = [r[0], lo], [r[0], hi]
        # Rear hinge: the full-open leaf stops behind the illustrated arrival.
        parked = [r[0]-1130, hi-95, 1130, 95]
        rear_window = {"a": [4750, 17630], "b": [5650, 17630], "legal": "unknown"}
    else:
        lo, hi = spec["door_nominal_x_mm"]
        clear_lo, clear_hi = spec["door_clear_illustrative_x_mm"]
        a, b = [lo, r[1]], [hi, r[1]]
        # Right hinge: open leaf sits at the side of the separate dry foyer.
        parked = [hi-95, r[1]-1130, 95, 1130]
        rear_window = None
    room = measured_room(rid, name, rect_ring(r), fixtures,
        [{"a": a, "b": b, "nominal_mm": hi-lo, "assumed_clear_mm": clear_hi-clear_lo,
          "operation": spec["door_operation"], "hinge": "rear" if private else "right",
          "parked_leaf_budget_mm": parked, "swept_rect_mm": spec["door_sweep_budget_mm"]}], rear_window)
    entry = translate(spec["inside_approach_local_mm"], origin)
    body_collisions = [[a["id"], b["id"]] for n, a in enumerate(fixtures) for b in fixtures[n+1:]
                       if collision(area_shape(a["rect_mm"]), area_shape(b["rect_mm"]))]
    operation_hits = [{"operation": a["id"], "body": b["id"]} for a in fixtures for b in fixtures
                      if a["id"] != b["id"] and collision(area_shape(a["operation_mm"]), area_shape(b["rect_mm"]))]
    operation_shared = [[a["id"], b["id"]] for n, a in enumerate(fixtures) for b in fixtures[n+1:]
                        if collision(area_shape(a["operation_mm"]), area_shape(b["operation_mm"]))]
    room.update(illustrative_finished_rect_mm=usable, inside_approach_mm=entry,
        outside_approach_mm=spec["outside_approach_mm"], body_collisions=body_collisions,
        operation_body_hits=operation_hits, sequential_operation_pairs=operation_shared,
        body_and_operations_inside=all(area_shape(usable).covers(area_shape(i[k])) for i in fixtures
            for k in ("rect_mm", "operation_mm")),
        arrival_body_hits=[i["id"] for i in fixtures if collision(area_shape(entry), area_shape(i["rect_mm"]))],
        actual_finished_clear_mm=None, actual_product_pack=None, actual_rescue="unknown")
    return room


def upper_floor(plans, fid, cfg):
    old = room_map(plans)
    private = fid == "floor-2"
    prefix = "B:"+fid+":"
    items = [{"id": key, "rect_mm": value} for key, value in cfg["bedroom_fixtures_mm"].items()]
    for item in items:
        r = item["rect_mm"]
        item["operation_mm"] = ([r[0]+r[2], r[1], 600, r[3]] if item["id"] == "bed" else
            [r[0]-600, r[1], 600, r[3]] if item["id"] == "wardrobe" else [r[0]+r[2], r[1], 700, r[3]])
    lo, hi = cfg["bedroom_entry_x_mm"]
    room = measured_room(prefix+("master2" if private else "guest3"),
        "L形主臥／前臂梳妝" if private else "L形後客房／前臂梳妝", cfg["bedroom_polygon_mm"], items,
        [{"a": [lo, 11370], "b": [hi, 11370], "nominal_mm": hi-lo, "assumed_clear_mm": hi-lo-230,
          "operation": "原入口形式待核，900淨寬目標；不以未建模門片證明通行。"}],
        {"a": [cfg["bedroom_rear_window_x_mm"][0], 17630],
         "b": [cfg["bedroom_rear_window_x_mm"][1], 17630], "legal": "unknown"})
    dry = measured_room(prefix+"dry-protection", "背櫃上方獨立乾室（禁床／濕設備）", rect_ring(cfg["dry_room_rect_mm"]),
        doors=[{"a": [4670, 11605], "b": [4670, 12735], "nominal_mm": 1130, "assumed_clear_mm": 900,
                "operation": "向乾室內開；不占右側公共乾廳，不作公共穿越。"}])
    foyer = measured_room(prefix+"right-foyer", "公共乾廳／公衛獨立到達", cfg["foyer_polygon_mm"])
    public = bath(cfg, cfg["public_bath"], prefix+"public-bath", "後右公衛（排氣待核）")
    if private:
        last = bath(cfg, cfg["private_bath"], prefix+"private-bath", "後右套衛／候選後窗", private=True)
        room["doors"].append(copy.deepcopy(last["doors"][0]))
    else:
        last = measured_room(prefix+"rear-dry", "乾式收納／設備介面預留（禁床）", rect_ring(cfg["private_bath_rect_mm"]),
            doors=[{"a": [3900, 16330], "b": [3900, 17460], "nominal_mm": 1130, "assumed_clear_mm": 900,
                "operation": "候選內部門；不因此承諾KTV或新室內設備已容納。"}])
        room["doors"].append(copy.deepcopy(last["doors"][0]))
    retained = [r for r in compact(plans, [fid])[0]["rooms"] if r["rect_mm"][1] < 11370]
    for r in retained:
        # These rooms lie entirely in front of the replacement area.
        if r["rect_mm"][1]+r["rect_mm"][3] > 11370:
            raise ContractError("Cannot replace only the rear block when a retained room crosses its line")
    previous_room = old[prefix+("master2" if private else "guest3")]
    unit = next(u for u in previous_room["features"]["hvac_units"] if u["type"] == "indoor")
    route = copy.deepcopy(unit["route"])
    x = cfg["ac_new_x_mm"]
    route["polyline_mm"][0][0] = x
    route["polyline_mm"][1][0] = x
    route["estimated_routed_length_mm"] = round(sum(sum(abs(a[k]-b[k]) for k in range(3))
        for a, b in zip(route["polyline_mm"], route["polyline_mm"][1:], strict=False))+route["bend_service_allowance_mm"])
    route["status"] = "independent-static-study-not-engineered"
    room["hvac_candidate"] = {"id": unit["id"], "rect_mm": [x-475, unit["y_mm"]-140, 950, 280],
        "bottom_relative_z_mm": unit["mount_height_mm"], "route": route, "manual": None}
    return {"id": fid, "retained_front": retained, "rooms": [room, dry, foyer, public, last]}


def floor1(plans, cfg, oid, state):
    f = compact(plans, ["floor-1"])[0]
    for room in f["rooms"]:
        suffix = room["id"].split(":")[-1]
        if suffix == "altar-backing":
            room["rect_mm"] = cfg["backing_rect_mm"]
            for item in room["furniture"]:
                item["rect_mm"] = cfg["backing_cabinet_rect_mm"]
            room["features"]["doors"] = [{"face": "right", "ratio": .5, "width_mm": cfg["backing_door_nominal_mm"],
                "neighbor": "B:floor-1:corridor1", "operation": "hinged-inward-proposal"}]
        elif suffix == "corridor1":
            room["rect_mm"] = cfg["right_corridor_rect_mm"]
            room["features"]["doors"] = [{"face": "left", "ratio": .5, "width_mm": cfg["backing_door_nominal_mm"],
                "neighbor": "B:floor-1:altar-backing", "operation": "hinged-inward-proposal"}]
        elif suffix == "laundry-front":
            room["rect_mm"][2] = cfg["backing_rect_mm"][0]-room["rect_mm"][0]
        elif suffix == "turn-bay":
            room["rect_mm"][2] = cfg["backing_rect_mm"][0]
        for d in room["features"]["doors"]:
            if suffix == "shrine-front" and d["face"] == "front":
                d["ratio"] = (cfg["street_axis_x_mm"]-room["rect_mm"][0])/room["rect_mm"][2]
        for item in room["furniture"]:
            key = item["id"].split(":")[-1]
            if key == "altar":
                item["rect_mm"] = cfg["altar_rect_mm"]
            elif key == "offering" and not (oid == "b-front-split" and state == "carry"):
                item["rect_mm"] = cfg["offering_rect_mm"]
            item.pop("placement", None)
        # Do not expose old approach boxes or routes as if re-evaluated after changing the room.
        room["features"] = {key: copy.deepcopy(value) for key, value in room["features"].items()
            if key in {"doors", "window_face", "window_ratio", "window_mm", "window_review"}}
    f["note"] = "只讀出獨立靜態比較；舊features操作帶不作本輪驗證輸入，依rect與下列明列檢查。"
    return f


def analyze_option(source, oid, cfg):
    plans = selected(source, oid)
    floors = [upper_floor(plans, fid, cfg["upper"]) for fid in ("floor-2", "floor-3")]
    states = [{"id": sid, "floor1": floor1(selected(source, oid, sid), cfg["floor1"], oid, sid),
               "source_state_hash": stable_hash(selected(source, oid, sid))} for sid in cfg["states"]]
    old = room_map(plans)
    shrine_shapes = [area_shape(rect(old["B:floor-1:"+key])) for key in ("shrine", "shrine-front")]
    shrine = unary_union(shrine_shapes)
    backing = area_shape(cfg["floor1"]["backing_rect_mm"])
    protected = unary_union([shrine, backing])
    palanquin = area_shape(rect(old["B:floor-1:storage"]))
    result, remaining = [], []

    def finding(fid, title, status, measurements, note):
        result.append({"id": fid, "title": title, "status": status, "measurements": measurements,
                       "note": note, "professional_approval": "unknown"})

    old_wet = [{"room": r["id"], "over_backing_sqm": round(area_shape(rect(r)).intersection(backing).area/1e6, 6)}
        for f in plans["floors"] if f["id"] != "floor-1" for r in f["rooms"]
        if any(i["shape"] == "toilet" for i in r["furniture"])]
    finding("B-FS-01", "原濕區不能以立管／防水解套", "control-conflict", old_wet,
        "原圖仍保留作對照；下列試排重新分配實際濕區，不靠遮擋或換名稱消除投影。")
    bedroom_shape = Polygon(cfg["upper"]["bedroom_polygon_mm"])
    for upper in floors:
        wet_rooms = [r for r in upper["rooms"] if "illustrative_finished_rect_mm" in r]
        overlaps = [{"room": r["id"], "over_protected_sqm": round(Polygon(r["polygon_mm"]).intersection(protected).area/1e6, 6),
            "over_palanquin_sqm": round(Polygon(r["polygon_mm"]).intersection(palanquin).area/1e6, 6),
            "distance_from_backing_mm": Polygon(r["polygon_mm"]).distance(backing)} for r in wet_rooms]
        wet_conflict = any(r["over_protected_sqm"] > 0 or r["over_palanquin_sqm"] > 0 for r in overlaps)
        finding("B-FS-02-"+upper["id"], "濕區避完整祭祀／背櫃與武轎庫投影",
            "conflict" if wet_conflict else "listed-geometry-clear", overlaps,
            "只對明列房間多邊形，實際梁板與給排水未到；200mm是名義分區距離，非施工或防漏保證。")
        bed_overlap = bedroom_shape.intersection(protected).area/1e6
        dry_match = Polygon(upper["rooms"][1]["polygon_mm"]).equals(backing)
        finding("B-FS-03-"+upper["id"], "睡眠用途避完整神明堂及背櫃",
            "listed-geometry-clear" if bed_overlap == 0 and dry_match else "conflict",
            {"bedroom_over_protected_sqm": bed_overlap, "dry_room_matches_backing": dry_match},
            "不是只移床；L形房間輪廓本身退出保護區，該區獨立乾室禁床／浴廁／濕設備。")
        # Full rear replacement must partition the same rectangle without gaps or overlaps.
        all_shapes = [Polygon(r["polygon_mm"]) for r in upper["rooms"]]
        frame = box(0, 11370, 6000, 17630)
        partition_overlap = sum(p.area for p in all_shapes)-unary_union(all_shapes).area
        partition_gap = frame.symmetric_difference(unary_union(all_shapes)).area/1e6
        finding("B-AR-01-"+upper["id"], "後段分區不重複計面積",
            "listed-geometry-clear" if partition_gap == 0 and partition_overlap == 0 else "conflict",
            {"gap_or_outside_sqm": partition_gap,
             "overlap_sqm": partition_overlap/1e6}, "不封前3.9m，不挪入鄰棟或戶外平台。")
        bedroom = upper["rooms"][0]
        inside = bedroom_shape.buffer(-115, join_style=2)
        sweeps = square_sweeps(cfg["upper"]["bedroom_route_points_mm"], cfg["upper"]["bedroom_route_square_mm"])
        route_hits = [{"segment": n, "body": i["id"]} for n, r in enumerate(sweeps) for i in bedroom["furniture"]
                      if collision(area_shape(r), area_shape(i["rect_mm"]))]
        route_inside = all(inside.covers(area_shape(r)) for r in sweeps)
        finding("B-AR-02-"+upper["id"], "L房900方塊局部到達試排",
            "listed-geometry-clear" if not route_hits and route_inside else "conflict",
            {"route_body_hits": route_hits, "route_inside_115_polygon": route_inside,
             "sweeps_mm": sweeps}, "梳妝／衣櫃操作與通行分時。不是輪椅、門口或整棟救援演練；門組仍未知。")
        for r in wet_rooms:
            finding("B-AR-03-"+r["id"], "一般衛浴本體／700操作及門前", "listed-geometry-clear" if not (
                r["body_collisions"] or r["operation_body_hits"] or r["arrival_body_hits"]) and r["body_and_operations_inside"] else "conflict",
                {key: r[key] for key in ["body_collisions", "operation_body_hits", "arrival_body_hits",
                                       "body_and_operations_inside", "sequential_operation_pairs"]},
                "操作可分時，固定器具不能侵入別件操作；1130減230得900只是門框預算，普通盆櫃不可當照護盆。")
    dimensions = []
    for t in cfg["upper"]["inset_sensitivity_mm"]:
        dimensions.append({"inset_each_mm": t, "bedroom_sqm": round(bedroom_shape.buffer(-t, join_style=2).area/1e6, 6),
            "public_bath_sqm": round((2100-2*t)*(2300-2*t)/1e6, 6),
            "private_bath_sqm": round((2100-2*t)*(2160-2*t)/1e6, 6)})
    finding("B-AR-04", "主臥與衛浴面積代價", "target-sensitive", dimensions,
        "主臥115假設20.1141㎡、150假設19.44㎡；套衛115假設3.6091㎡，低於原4.5㎡下限及6㎡目標。不能寫成全需求達標。")
    finding("B-FS-04", "朝街正門與神桌同軸，完整乾背牆", "listed-geometry-clear",
        {"axis_x_mm": cfg["floor1"]["street_axis_x_mm"], "altar_shift_x_mm": 255,
         "backing_area_sqm": backing.area/1e6, "right_corridor_nominal_width_mm": 1330},
        "1F不前移神桌；前門原1800寬保留，實牆材質／梁／香火排風與方向擇位未核。")
    roof = compact(plans, ["floor-4"])[0]
    units = [{"id": u["id"], "rect_mm": [u["x_mm"]-u["width_mm"]/2, u["y_mm"]-u["depth_mm"]/2,
             u["width_mm"], u["depth_mm"]]} for r in roof["rooms"] for u in r["features"].get("hvac_units", [])]
    roof_hits = [u["id"] for u in units if collision(area_shape(u["rect_mm"]), protected)]
    finding("B-FS-05", "屋頂保護投影及列明機身", "listed-geometry-clear" if not roof_hits else "conflict",
        {"listed_roof_units": len(units), "body_over_protected": roof_hits, "future_roof_wet_equipment": None},
        "神明堂及新背櫃的投影向屋頂延伸禁濕設備；目前兩台機身未壓區，不代表未排水塔／熱水器或能源設備已核。")
    remaining.extend([
        {"id": "B-DEC-01", "topic": "套衛完成面積／主臥20㎡餘量", "status": "decision-or-redesign-required",
         "recommendation": "本案作可見嚴格幾何解，暫不採用；不得把3.6091㎡假設套衛稱達4.5㎡下限。待Claude交叉檢討，先保留原需求。", "owner_decision": None},
        {"id": "B-UNK-01", "topic": "污水／通氣與濕設備路線", "status": "unknown",
         "recommendation": "管道必須在後右濕區及其後側外緣設計，禁穿完整祭祀／背櫃上方；未取得線路圖不作通過。", "owner_decision": None},
        {"id": "B-UNK-02", "topic": "梁柱／RC背牆／座向／鏡面／氣流", "status": "unknown",
         "recommendation": "正式圖與現場方向逐項核；沒有神明廳全部風水合格結論。", "owner_decision": None},
        {"id": "B-UNK-03", "topic": "後巷權利與完整裝桿搬轎", "status": "unknown",
         "recommendation": "前後版分開演練；保留原1500完成淨寬目標，1730名義門不等門組已核。", "owner_decision": None}])
    return {"id": oid, "states": states, "upper_floors": floors, "roof_reference": roof,
        "roof_protected_footprints_mm": [ring(shrine), ring(backing)],
        "protected_polygons_mm": [ring(shrine), ring(backing)],
        "palanquin_rect_mm": rect(old["B:floor-1:storage"]), "findings": result, "remaining": remaining,
        "nominal_bedroom_sqm": round(bedroom_shape.area/1e6, 6), "area_sensitivity": dimensions,
        "adopted": False, "all_requirements_met": False, "religious_approval": "unknown"}


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    source_path = public_path(root, cfg["source_report"])
    if sha256_file(source_path) != cfg["source_report_sha256"]:
        raise ContractError("B strict study source changed; reassess before export")
    controls = read_json(root/cfg["protected_controls"])
    for name, digest in controls["hashes"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("Protected control changed: "+name)
    source = read_json(source_path)
    # Preserve complete original requirements; geometric coordinates in their legacy rationale are not re-used as current layout.
    requirements = read_json(root/"inputs/requirements.json")
    sha = cfg["source_report_sha256"]
    report = {"schema": "house-b-strict-study-report-v1", "config": cfg, "source_layout_report_sha256": sha,
        "adopted": False, "professional_approval": "unknown", "all_requirements_met": False,
        "rendered_qa": "not-run-static-study", "requirements_source_sha256": stable_hash(requirements),
        "protected_controls_unchanged": len(controls["hashes"]),
        "options": [analyze_option(source, oid, cfg) for oid in cfg["options"]],
        "claude_discussion": {"status": "timeout-no-completed-discussion", "consensus": False,
            "result_reference": "inputs/references/b-claude-attempt-20261105.json", "retry": "not-attempted"},
        "research_sources": [
            {"url": "https://www.chengji.com.tw/service_detail?item=31", "accessed": "2026-11-05",
             "scope": "佛具商民俗實務：實牆、清淨、通風與不直吹；不是本宅風水驗證。"},
            {"url": "https://www.100.com.tw/article/10204", "accessed": "2026-11-05",
             "scope": "設計媒體談背牆、浴廁與動線；不同流派的化解說法不當作本案通過依據。"}],
        "rejected_options": cfg["rejected"]}
    names = [CONFIG, cfg["protected_controls"], "inputs/requirements.json", "house_design/b_fengshui_strict.py",
        "house_design/abc_next_improvements.py", "house_design/c_coordination.py", "house_design/contracts.py",
        "scripts/export_b_fengshui_strict.py", "scripts/export_abc_next_improvements.py",
        "scripts/review_b_fengshui_with_claude.py", "Docs/claude-b-fengshui-brief-v1.md",
        "Docs/claude-b-fengshui-followup-v2.md", "inputs/references/b-claude-attempt-20261105.json"]
    report["source_hashes"] = {p: sha256_file(root/p) for p in names}
    report["report_hash"] = stable_hash(report)
    return report

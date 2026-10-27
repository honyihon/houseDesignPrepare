#!/usr/bin/env python3
"""Two independent B32 plans and explicit use states, without scene execution.

Only writes its own new comparison directory/pages. Older ten proposals, A/C,
requirements, real-item measurements and frozen archives remain untouched.
"""
from __future__ import annotations

import copy
import html
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import export_interior_improvements as interior
import export_model_3d as viewer
from lib.model3d_openings import review_window
from lib.model3d_plan import plan_data, render_plan

from house_design.b32_rear_right import body, cultural_screen, rect, review_state
from house_design.b32_service_detail import _route
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, utc_now, write_json
from house_design.requirement_reconciliation import build_reconciliation, discussion_area

SOURCE = "inputs/b32-rear-right-study.json"
OUT = "structured/candidates/b32-rear-right"
INDEX = OUT+".html"
VIEWER = OUT+"-3d.html"
BOOTSTRAP = "scripts/templates/b32-rear-right-bootstrap.js"
DISPLAY = "scripts/templates/b32-rear-right-display.js"
DISPLAY_REVISION = 2
STATES = ("daily", "ritual", "carry")
STATE_LABELS = {"daily": "日常停凳", "ritual": "祭祀座位／公衛側緣通行", "carry": "搬轎整備（非同時祭祀）"}
STATUS = "comparison-only-not-adopted"


def validate_config(cfg: dict) -> None:
    if (cfg.get("schema") != "house-b32-rear-right-v1" or cfg.get("revision") != 1
            or cfg.get("status") != STATUS or not cfg.get("authorization")
            or cfg.get("frame_mm") != [6000, 17630] or cfg.get("front_clear_depth_mm") != 3900
            or cfg.get("insets_mm") != [80, 100, 115] or cfg.get("default_option") != "rear-alley"
            or cfg.get("default_state") != "daily" or [o["id"] for o in cfg["options"]] != ["rear-alley", "front-backup"]
            or cfg["rear_alley"]["existence"] != "owner-reported-planning-premise" or not cfg["rear_alley"].get("source")
            or any(v != "unknown" for k, v in cfg["rear_alley"].items() if k not in {"existence", "source"})
            or set(cfg["professional_status"].values()) != {"unknown"}
            or cfg["front_staging"]["family_acceptance"] != "pending"
            or cfg["front_staging"]["assembled_poles_people_height_and_real_rehearsal"] != "unknown"
            or cfg["palanquin_body_mm"][2:] != [1200, 1700]):
        raise ContractError("Preserve two independent authorized comparisons, original frame and unknown approvals")


def _reserve(cell: dict, kind: str, area: list, note: str) -> None:
    cell["tour_features"]["fixed_reserved_mm"].append({"kind": "b-separate-"+kind,
        "aabb": interior._bounds(area), "status": note})


def proposal(source: dict, cfg: dict, option: dict, state: str, root: Path) -> tuple[dict, dict]:
    base_id = "b32-rear" if option["id"] == "rear-alley" else "b32-front"
    model = copy.deepcopy(interior._select(source, base_id, "B"))
    baseline = copy.deepcopy(model["buildings"][0])
    model, _ = interior.b_window_proposal(model, read_json(root / interior.SOURCE), root)
    first = model["buildings"][0]["floors"][0]
    old = copy.deepcopy(interior._rooms(first))
    products = {i["catalog_id"]: i for r in old.values() for i in r["furniture"]}
    laundry = {i["id"].rsplit(":", 1)[-1]: i for r in old.values() for i in r["furniture"]
               if i["id"].rsplit(":", 1)[-1] in {"washer", "utility-sink"}}
    keep = {"garage", "stair1", "shrine-front", "shrine"}
    first["cells"] = [c for c in first["cells"] if c["key"] in keep]
    first["layout_review"]["rooms"] = {k: v for k, v in first["layout_review"]["rooms"].items() if k in keep}
    zones = {**option["zones_mm"], "rear-bath": cfg["rear_bath_mm"], "storage": cfg["storage_mm"]}
    names = {"rear-bath": "後右有窗公衛（乾轉位／淋浴分區）", "storage": "後左武轎庫（本體＋長凳整備）",
             "storage-front": "左側庫房接段（不計公共衛浴通道）", "left-approach": "左側庫房／家務入口",
             "turn-bay": "前門搬轎轉向接段（不計家務面積）", "laundry-front": "家務設備凹間（非工作陽台）",
             "laundry-base": "洗衣／洗槽操作（分時）", "altar-backing": "神桌完整乾背牆／法器櫃（右側門）",
             "corridor1": "右側公共乾通道（避開祭祀中軸）", "bath-approach": "公衛獨立到達接段（不穿武轎庫）"}
    for key, area in zones.items():
        kind = "bath" if key == "rear-bath" else "other" if key in {"left-approach", "turn-bay", "corridor1", "bath-approach"} else "service"
        group = "rr-laundry" if key.startswith("laundry-") else "rr-storage" if key in {"storage", "storage-front"} else "rr-public" if key in {"corridor1", "bath-approach"} else ""
        cell = interior._room(first, key, area, template=old["rear-bath"] if kind == "bath" else old["laundry-base"],
            name=names[key], kind=kind, group=group, role="circulation" if kind == "other" else "", outdoor=False, window_mm=0)
        interior._empty(cell)
        for stale in ("clearance_reservations", "window_face", "window_note", "carry_path_mm", "door_operation"):
            cell["review_spec"].pop(stale, None)
        cell["tour_features"]["fixed_reserved_mm"] = []
        first["layout_review"]["rooms"][key] = copy.deepcopy(cell["review_spec"])
    cells = interior._rooms(first)
    for raw in cfg["fixtures"]:
        item = copy.deepcopy(products[raw["catalog"]])
        item["step_free"] = raw["local"] == "shower"
        interior._place(cells["rear-bath"], item, raw["rect_mm"], raw["rotation_deg"], raw["wall_anchor"], local=raw["local"])
    for raw in option["laundry_items"]:
        interior._place(cells[raw["room"]], laundry[raw["local"]], raw["rect_mm"], raw["rotation_deg"], raw["wall_anchor"], local=raw["local"])
    interior._place(cells["storage"], products["ceremonial-storage"], cfg["palanquin_body_mm"], 0, "", local="ceremonal")
    interior._place(cells["altar-backing"], old["altar-backing"]["furniture"][0], [2615, 11485, 450, 1200], 270, "left", local="cabinet")
    interior._empty(cells["shrine"])
    staging = cfg["front_staging"]
    seated = read_json(root / "inputs/b32-service-detail.json")["shrine"]["ritual_seated_benches"]
    for item in old["shrine"]["furniture"]:
        local = item["id"].rsplit(":", 1)[-1]
        area, yaw, target = interior._body(old["shrine"], item), 0, cells["shrine"]
        if state == "ritual" and local.startswith("bench-"):
            seat = next(p for p in seated if p["id"] == local)
            area, yaw = seat["rect_mm"], seat["rotation_deg"]
        if state == "carry" and option["id"] == "front-backup":
            if local == "offering":
                area, target = staging["offering_mm"], cells["shrine-front"]
            elif local.startswith("bench-"):
                area, target = staging[local.replace("-", "_")+"_mm"], cells["storage"]
        interior._place(target, item, area, yaw, "rear" if local == "altar" else "")
    first["layout_review"]["connections"] = [
        ["shrine-front", "shrine", "open"], ["stair1", "shrine-front", 1000, 4400],
        ["shrine", "corridor1", "open"], ["corridor1", "bath-approach", "open"],
        ["bath-approach", "rear-bath", {"width_mm": 1130, "operation": "sliding", "label": "公衛表面拉門（向左停放／救援未核）"}, option["bath_door_center_x_mm"]],
        ["corridor1", "altar-backing", {"width_mm": 1060, "operation": "hinged-inward-proposal", "label": "法器乾櫃右側內開門（分時）"}, 12170],
        ["storage-front", "storage", "open"], ["laundry-front", "laundry-base", "open"]]
    if option["id"] == "rear-alley":
        first["layout_review"]["connections"] += [["shrine", "left-approach", "open"], ["left-approach", "storage-front", "open"],
            ["left-approach", "laundry-front", "open"], ["storage-front", "laundry-base", "open"]]
    else:
        first["layout_review"]["connections"] += [["shrine", "turn-bay", "open"], ["turn-bay", "left-approach", "open"],
            ["turn-bay", "laundry-front", "open"],
            ["left-approach", "storage-front", {"width_mm": 1730, "operation": "wide-opening-product-unknown", "label": "搬轎寬門組（173cm名義／產品未定）"}, 875],
            ["bath-approach", "laundry-base", {"width_mm": 1130, "operation": "hinged-inward-proposal", "label": "家務內開門（分時／濕氣隔離未核）"}, 13650]]
    first["layout_review"]["entry"] = ["shrine-front", "front", 1800, 3400]
    first["layout_review"]["entry_label"] = "朝街同軸祭祀正門（180cm名義）"
    first["layout_review"]["additional_entries"] = [["stair1", "front", 1000, 1200]]
    if option["rear_gate"]:
        first["layout_review"]["additional_entries"].append(["storage", "rear", option["rear_gate"]["width_mm"], option["rear_gate"]["center_x_mm"]])
    window = cfg["rear_window"]
    bath = cells["rear-bath"]
    bath["window_mm"] = window["width_mm"]
    bath["review_spec"].update(window_mm=window["width_mm"], window_face="rear",
        window_ratio=(window["center_x_mm"]-3330)/2670,
        window_note="後巷有無不等於可開窗；窗權利、鄰地／防火、有效通風與防雨未知，仍須獨立排氣補氣。")
    first["layout_review"]["rooms"]["rear-bath"] = copy.deepcopy(bath["review_spec"])
    interior._rebuild(first)
    if state == "ritual":
        for seat in seated:
            _reserve(cells["shrine"], "seated-operation", seat["seated_operation_mm"], "600mm-seated-band-not-human-or-family-approval")
    interior._exact_pair(cells, "rear-bath", "bath-approach", "front", option["bath_door_center_x_mm"], 1130)
    interior._exact_pair(cells, "altar-backing", "corridor1", "right", 12170, 1060)
    if option["id"] == "front-backup":
        interior._exact_pair(cells, "storage-front", "left-approach", "front", 875, 1730)
        interior._exact_pair(cells, "laundry-base", "bath-approach", "right", 13650, 1130)
        _reserve(cells["laundry-base"], "laundry-door-sweep", [3460, 13085, 1175, 1130], "bounding-square-not-selected-product")
    bath["tour_features"].update(window_mm=900, window_sill_mm=1500, window_height_mm=600)
    review_window(bath, first, {"rear": [(3330, 6000)]})
    if not bath["tour_features"]["window_review"]["renderable"]:
        raise ContractError("Actual rear window failed its geometric screen")
    for name, area in cfg["bath_operations_mm"].items():
        _reserve(bath, name, area, "discussion-operation-not-care-approval")
    cx, cy, radius = cfg["turn_circle_mm"]
    _reserve(bath, "dry-turn", [cx-radius, cy-radius, radius*2, radius*2], "dry-turn-no-shower-borrow-not-rehearsed")
    bath["tour_features"]["fixed_reserved_mm"][-1]["kind"] = "care-turn"
    start = option["bath_door_center_x_mm"]-565
    _reserve(bath, "slider-park", [start-1230, 14615, 1230, 95], "parked-leaf-and-handle-budget-not-product")
    _reserve(bath, "slider-closed", [start, 14615, 1130, 95], "closed-door-not-passable")
    _reserve(cells["altar-backing"], "dry-door-sweep", [3100, 11640, 1105, 1060], "inward-sweep-budget-not-selected-product")
    for name, area in option["laundry_operations_mm"].items():
        _reserve(cells["laundry-base"], name, area, "retained-900x800-operation-rotated-not-reduced")
    if option["small_drying_equipment"]:
        daily_cfg = read_json(root / interior.SOURCE)["b_daily_use"]
        sample = copy.deepcopy(laundry["washer"])
        sample = {k: v for k, v in sample.items() if not k.startswith("physical_")}
        sample.update(physical_item_id=None, basis="room-use-inference", front_clearance_mm=0, rear_clearance_mm=0,
                      left_clearance_mm=0, right_clearance_mm=0, mount_height_mm=0)
        raw = daily_cfg["drying_rack"]
        rack = {**sample, **{k: raw[k] for k in ("catalog_id", "label", "width_mm", "depth_mm", "height_mm")},
                "shape": "clothes-rack", "color": "#15803d", "note": raw["note"]}
        interior._place(cells["laundry-base"], rack, raw["rect_mm"], 0, "rear", local="small-drying-rack")
        product = read_json(root / "inputs/furniture-layout.json")["catalog"]["dehumidifier"]
        interior._place(cells["laundry-base"], {**sample, **product, "catalog_id": "dehumidifier"}, [2500, 13985, 350, 300], 0, "", local="dehumidifier")
        _reserve(cells["laundry-base"], "drying-loading", raw["front_operation_rect_mm"], "small-rack-not-original-2400mm-rack")
        _reserve(cells["laundry-base"], "dehumidifier-service", [2400, 13885, 550, 500], "100mm-assumption-not-manufacturer-clearance")
    for key in zones:
        cells[key]["tour_features"]["interior_entry_review"] = {"status": STATUS, "note": "兩版獨立成對門位，仍非照護／消防／真人搬轎核可。"}
    label = option["label"]+" · "+STATE_LABELS[state]
    notes = ["深化比較未採用；600×1763cm約32地坪，390cm前緣騎樓／通行帶不當房間或車位，實際可建範圍待核。",
             "神桌保留朝街中軸門、完整乾背牆，不背靠樓梯／浴廁；便器不朝正門。家規、羅盤方位、梁柱及上下層濕區仍待核，不宣稱風水通過。",
             "後右公衛從右側乾通道到達，不穿武轎庫／私人洗衣區；可避開目前畫定的祭祀與座椅範圍，不等於人潮、照護或消防核可。",
             "後牆90×60cm候選高窗、150cm窗台，避開120cm淋浴；無後巷不等於窗戶可合法開設，若後界不可開窗，此備案也須另研採光通風。",
             "原浴室7、儲藏10.5、家務5m²及1500mm搬運目標不減；室內家務不是原工作陽台已成立。浴室與家務各須獨立對外排氣、補氣、防水排水，除濕不代替換氣。",
             "只評120×170×180cm收納本體，不含抬桿、人員、門高或門外轉向；搬轎與祭祀、使用公衛／乾櫃及洗衣均須分時。",
             "供桌貼神桌、長凳分時停放及前門整備仍待家中同意；原ABC／十案／需求／實物與封存不改。"]
    if option["id"] == "rear-alley":
        notes.append("預設：屋主回報有後巷，庫房後門移到後左，196cm名義門寬、115mm假設淨173cm；巷寬、通行權、門高、外轉向與高低差未查，不視為已核。家務保留小量晾衣／除濕預留，但5m²目標幾乎無餘裕。")
    else:
        notes.append("備案：不開後門，改左側175cm名義通道與173cm名義庫房門；115mm假設分別152／150cm，門組未選且毫無門寬餘裕。這是不同隔間，不是現場切換一個門就能成立。")
        notes.append("150cm只是原連續寬度目標，不能只看門寬就宣稱滿足：另用150×170cm保護外廓複核，兩處旋轉仍超出本案保守轉向預留；120×170cm收納本體雖能在指定整備狀態旋轉，完整150cm搬運／裝桿人員仍未解，不降低原要求。")
        notes.append("前門搬轎必須切『搬轎整備』：兩張140cm長凳全尺寸移到庫房，120cm供桌移前廳右側，再作兩次本體旋轉；日常／祭祀狀態不可直接搬轎。家務保留原機／洗槽與900×800mm操作帶，但低於5m²目標；不強塞晾衣架／除濕機，完整乾衣能力仍未解。")
        notes.append("家務右側內開門的門扇掃掠、取衣與洗槽分時。左牆洗槽比機器後退50mm對齊操作前緣，保留原600mm本體，不以縮小洗槽消除碰撞；上端750mm凹帶完成面假設僅520mm寬，只留設備／管線，不稱人員通道。")
    notes.append("本輪只深化一樓：上層原家具完成面敏感度缺口、IDF、KTV、停車、樓梯淨高與管線尚未解；神桌背側原80mm餘量在115mm假設仍差35mm，保留待核而非宣稱全棟通過。")
    model = interior._finish(model, "B", option["id"], label, notes)
    model["source"]["rear_right_study"] = SOURCE
    model["bc_option"].update(revision=1, use_state=state, status=STATUS)
    screen = interior._screen(model, cfg["insets_mm"], baseline)
    # Inherited altar/upper-floor gaps stay explicit; do not waive new body issues.
    if (screen["operation_vs_fixed_body"] or any(i["inset_mm"] is None or i["room"].startswith("B:floor-1:")
            and not (i["room"] == "B:floor-1:shrine" and i["inset_mm"] in {100, 115}
                     and i["issue"] == "B:floor-1:shrine:furniture:altar:outside-assumed-floor")
            for i in screen["furniture_body_sensitivity"])):
        raise ContractError("New B32 configuration creates a body or original-operation conflict")
    return model, screen


def route_overlays(model: dict, review: dict, state: str) -> None:
    """One source for plan/3D centerlines and conservative rotation squares."""
    cells = interior._rooms(model["buildings"][0]["floors"][0])
    route = review["carry_stored_body_115mm"]
    lines = ([{"points_mm": s["points_mm"], "yaw_deg": s["yaw_deg"], "kind": "stored-body-carry"} for s in route["segments"]]
             if state == "carry" else [{"points_mm": review["bath_route_sensitivity"][-1]["bath_entry_route"]["points_mm"],
                                        "kind": "900mm-body-public-bath-not-care-approval"}])
    cells["shrine-front"]["tour_features"]["b32_route_overlays"] = lines
    if state == "carry":
        for index, rotation in enumerate(route["rotations"]):
            _reserve(cells["shrine-front"], "body-rotation-"+str(index), rotation["full_rotation_envelope_mm"],
                     "full-diagonal-rotation-not-people-poles-or-height")
            cells["shrine-front"]["tour_features"]["reserved_mm"].append(
                copy.deepcopy(cells["shrine-front"]["tour_features"]["fixed_reserved_mm"][-1]))


def staging_review(daily: dict, carry: dict) -> dict:
    rooms = {r["key"]: r for r in daily["floors"][0]["rooms"]}
    final = {i["id"]: body(i) for r in carry["floors"][0]["rooms"] for i in r["furniture"]}
    objects = {i["id"]: body(i) for r in rooms.values() for i in r["furniture"]}
    areas = [rect(rooms[k]) for k in ("shrine-front", "shrine", "turn-bay", "left-approach", "storage-front", "storage")]
    sequence = [("bench-2", [[1780, 11030], [875, 11030], [875, 15405], [2515, 15405]]),
                ("bench-1", [[1780, 10445], [875, 10445], [875, 14840], [2515, 14840]]),
                ("offering", [[3400, 10440], [3400, 5100], [5285, 5100], [5285, 4265]])]
    rows = []
    for local, points in sequence:
        key = next(k for k in objects if k.endswith(":"+local))
        start, end = objects[key], final[key]
        if points[0] != [start[0]+start[2]/2, start[1]+start[3]/2] or points[-1] != [end[0]+end[2]/2, end[1]+end[3]/2]:
            raise ContractError("Staging route must connect actual full-size daily and stored objects")
        result = _route(points, *start[2:], areas, [{"id": k, "rect_mm": r} for k, r in objects.items() if k != key], 115)
        rows.append({"item_id": key, "from_mm": start, "to_mm": end, **result})
        objects[key] = end
    return {"sequence": rows, "coordinate_failures": [e for r in rows for e in r["coordinate_failures"]],
            "full_size_furniture_retained": True, "family_acceptance_people_height_and_handling": "unknown"}


def build_study(root: Path = ROOT) -> dict:
    cfg = read_json(root / SOURCE)
    validate_config(cfg)
    fresh = build_reconciliation(root)
    if any(s["source_freshness"]["issues"] for s in fresh["scenarios"]):
        raise ContractError("Do not build on stale original snapshots")
    source = interior.read_model(root / "structured/candidates/b32-entry-options-3d.html")
    options = []
    for raw in cfg["options"]:
        states = []
        for state in STATES:
            model, screen = proposal(source, cfg, raw, state, root)
            plans = plan_data(model)["buildings"][0]
            review = review_state(plans, cfg, raw, state)
            for row in review["bath_route_sensitivity"]:
                if (any(row[k]["coordinate_failures"] for k in ("bath_entry_route", "bath_during_ritual", "basin_route", "toilet_side_route", "shower_route", "dry_cabinet_route", "local_laundry_700mm_route", "local_laundry_sink_700mm_route"))
                        or any(row[k] for k in ("turn_circle_failures", "bath_operation_failures", "laundry_operation_failures", "dry_door_swing_failures"))):
                    raise ContractError("Independent public bathroom/operations coordinate screen failed: "+raw["id"]+" / "+state)
            if state == "carry" and review["carry_stored_body_115mm"]["coordinate_failures"]:
                raise ContractError("Prepared stored-body transport still blocked: "+raw["id"])
            route_overlays(model, review, state)
            plans = plan_data(model)["buildings"][0]
            for f in plans["floors"]:
                f["plan_file"] = raw["id"]+"_"+state+"_"+f["id"]+".svg"
            review.update(screen)
            model["bc_option"]["geometry_review"] = review
            states.append({"id": state, "label": STATE_LABELS[state], "model": model, "plans": plans, "review": review})
        first = states[0]["plans"]["floors"][0]
        rooms = {r["key"]: r for r in first["rooms"]}
        areas = []
        requirements = read_json(root / "inputs/requirements.json")["requirements"]
        for zone, keys, rid in (("bathroom", ["rear-bath"], "B.floor-1.bath_acc"),
                                ("storage", ["storage", "storage-front"], "B.floor-1.palanquin"),
                                ("laundry", ["laundry-front", "laundry-base"], "B.floor-1.balcony_b")):
            candidates = [r for r in requirements if r["id"] == rid]
            expected = {"bathroom": (4.5, 7), "storage": (9, 10.5), "laundry": (4, 5)}[zone]
            if len(candidates) != 1:
                raise ContractError("Original B32 area requirement is missing or ambiguous: "+zone)
            requirement = candidates[0]
            if (requirement["constraints"].get("min_sqm"), requirement["constraints"].get("target_sqm")) != expected:
                raise ContractError("Original target changed; update the comparison explicitly, not silently")
            if zone == "storage" and max(requirement["constraints"]["door_clear_mm"], *(r["clear_width_mm"] for r in requirement["relationships"] if r["type"] == "transport_path")) != 1500:
                raise ContractError("Original 1500mm carry goal changed; do not silently reuse a passing width")
            rows = [{"inset_mm": inset, "area_sqm": discussion_area([rooms[k] for k in keys], inset)} for inset in cfg["insets_mm"]]
            areas.append({"zone": zone, "requirement_id": requirement["id"], "original_minimum_sqm": expected[0],
                          "original_target_sqm": expected[1], "sensitivity": rows,
                          "target_shortfall_at_115_sqm": round(max(0, expected[1]-rows[-1]["area_sqm"]), 4),
                          "legal_area_and_functional_approval": "unknown"})
        staging = staging_review(states[0]["plans"], states[2]["plans"]) if raw["id"] == "front-backup" else None
        if staging and staging["coordinate_failures"]:
            raise ContractError("Furniture preparation is not a viable stored-body translation")
        options.append({"id": raw["id"], "label": raw["label"], "role": raw["role"], "states": states,
                        "area_rows": areas, "staging_review": staging, "tradeoffs": states[0]["model"]["bc_option"]["tradeoffs"],
                        "cultural_coordinate_review": cultural_screen(states[0]["plans"]),
                        "mechanical_brief": {"status": "concept-only-no-engineered-duct-or-capacity",
                            "bath": "後右公衛獨立排氣至候選後外牆，避開高窗及補氣口；防雨／防蟲、逆止、噪音、檢修與有效排風待設計。",
                            "laundry": "洗衣區另管，候選天花走向：家務下段→右側乾通道上方→後右公衛上方→候選後外牆；不排入神明堂、法器櫃或武轎庫，也不視為已可穿越防火區劃。",
                            "laundry_candidate_plan_projection_mm": [[4100, 13650], [raw["bath_door_center_x_mm"], 13650], [raw["bath_door_center_x_mm"], 17630]],
                            "wet_dry_separation": "公衛與武轎庫間設完整防潮隔牆；家務須再定隔濕門、排風補氣、冷凝排水及電器安全，不以除濕機代替換氣。",
                            "structure_fire_product_airflow_and_maintenance": "unknown"},
                        "upper_floors": "unchanged-from-corresponding-b32-snapshot-not-new-professional-review"})
    paths = [SOURCE, "scripts/export_b32_rear_right.py", BOOTSTRAP, DISPLAY, "house_design/b32_rear_right.py",
             "scripts/check_b32_rear_right_playwright.cjs", interior.SOURCE, "scripts/export_interior_improvements.py",
             "inputs/b32-service-detail.json", "inputs/b32-service-study.json", "inputs/requirements.json", "inputs/furniture-layout.json",
             "inputs/physical-items.json", "inputs/project.json", "inputs/b32-entry-options.json", "inputs/requirement-dispositions.json",
             "structured/candidates/b32-entry-options-3d.html", "house_design/b32_service_detail.py", "house_design/b32_services.py",
             "house_design/requirement_reconciliation.py", "house_design/contracts.py", "scripts/export_model_3d.py",
             "scripts/templates/model3d.html", "scripts/templates/model3d_facade.js", "scripts/templates/bc-options-controls.html",
             "assets/plan_viewer.js", str(viewer.THREE_FILE.relative_to(ROOT))]
    paths += [str(p.relative_to(ROOT)) for p in (ROOT / "scripts/lib").glob("model3d_*.py")]
    result = {"schema": cfg["schema"], "revision": 1, "display_revision": DISPLAY_REVISION,
              "status": STATUS, "generated_at": utc_now(),
              "default_option": cfg["default_option"], "default_state": cfg["default_state"], "frame_mm": cfg["frame_mm"],
              "rear_alley": cfg["rear_alley"], "professional_status": cfg["professional_status"], "options": options,
              "source_hashes": {p: sha256_file(root / p) for p in sorted(set(paths))},
              "rendered_qa": "not-run", "browser_path": "Browser plugin not available; owner-run Windows Playwright only"}
    result["report_hash"] = stable_hash({k: v for k, v in result.items() if k != "generated_at"})
    return result


def render_index(study: dict) -> str:
    sections = []
    for o in study["options"]:
        zone_labels = {"bathroom": "後右公衛", "storage": "後左武轎庫（含接段）", "laundry": "室內家務（非工作陽台）"}
        area_rows = "".join(f'<tr><th>{zone_labels[r["zone"]]}</th><td>{r["original_target_sqm"]:.2f}</td><td>{r["sensitivity"][-1]["area_sqm"]:.4f}</td><td>{r["target_shortfall_at_115_sqm"]:.4f}</td></tr>' for r in o["area_rows"])
        states = []
        for state in o["states"]:
            link = f'b32-rear-right-3d.html?scheme={o["id"]}&use={state["id"]}#mode=tour&building=B&floor=floor-1&view=plan'
            figures = []
            for f in state["plans"]["floors"]:
                src = "b32-rear-right/"+f["plan_file"]
                figures.append(f'<figure><figcaption>{html.escape(f["label"])} · <a href="{src}">另開SVG</a></figcaption>'
                    '<div data-plan-viewer data-source-width="6600" data-source-height="19030" data-readable-width="660">'
                    '<div data-plan-controls hidden><button type="button" data-plan-action="in">放大</button> <button type="button" data-plan-action="out">縮小</button> '
                    '<button type="button" data-plan-action="readable">讀字</button> <button type="button" data-plan-action="overview">整層</button></div>'
                    '<p data-plan-state role="status">可另開SVG讀圖；展示不是工程比例。</p>'
                    f'<div data-plan-viewport tabindex="0"><object data-plan-content type="image/svg+xml" data="{src}"><a href="{src}">開啟SVG</a></object></div>'
                    '<p data-plan-error hidden>圖面未載入，不算驗收通過。</p></div></figure>')
            issues = state["review"]["carry_stored_body_115mm"]["coordinate_failures"]
            statement = "本狀態本體試線仍受阻，不可搬轎；請看搬轎整備狀態。" if issues else "指定收納本體試線無座標碰撞；仍非裝桿／真人搬轎通過。"
            states.append(f'<details id="{o["id"]}-{state["id"]}" data-use-state="{state["id"]}"'+(" open" if state["id"] == "daily" else "")+f'><summary>{html.escape(state["label"])}</summary>'
                f'<p>{statement} <a href="{html.escape(link, quote=True)}">此狀態同源3D</a></p>'+"".join(figures)+"</details>")
        sections.append(f'<section id="{o["id"]}" data-option="{o["id"]}"><h2>{html.escape(o["label"])}</h2><p class="warning">深化比較未採用；後巷／外窗權利、法規、照護、家規及真人搬轎未核。</p><ul>'+
            "".join('<li>'+html.escape(n)+'</li>' for n in o["tradeoffs"])+ '</ul><table><caption>115mm內縮假設：討論面積m²，非合法淨面積；浴室／庫房／家務</caption><thead><tr><th>區域</th><th>原目標</th><th>本案討論值</th><th>目標缺口</th></tr></thead><tbody>'+area_rows+'</tbody></table>'+"".join(states)+
            '<details><summary>來源、敏感度、搬運與整備研究（非簽證）</summary><pre>'+html.escape(json.dumps({k: v for k, v in o.items() if k != "states"}, ensure_ascii=False, indent=2))+'</pre></details></section>')
    page = '<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B32後右公衛／後左武轎庫 · 兩版深化比較</title><style>body{font:16px/1.7 system-ui,sans-serif;color:#21362b;background:#f8faf7;max-width:1200px;margin:auto;padding:20px}a{color:#17634d}nav{display:flex;gap:16px;flex-wrap:wrap}.warning{padding:12px;background:#fff3d8;color:#6b430b}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{border:1px solid #cbd5ce;padding:8px;text-align:left}summary,button{min-height:44px;cursor:pointer}details{margin:18px 0}figure{margin:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}[data-plan-viewport]{height:620px;overflow:auto;border:1px solid #b8c6bc}[data-plan-content]{display:block;max-width:none}[hidden]{display:none!important}@media(max-width:640px){body{padding:12px}[data-plan-viewport]{height:500px}}</style><body><h1>B32：後右有窗公衛＋後左武轎庫</h1><p class="warning">兩個獨立版本，未採用。預設有後巷，僅為屋主回報的規劃前提；通行權、巷寬、開窗、32地坪可建範圍與施工均未核。前門備案不是日常家具不動即可搬轎。</p><nav><a href="b32-rear-right-3d.html">預設後巷版3D</a><a href="#rear-alley">後巷優先</a><a href="#front-backup">無後巷備案</a><a href="interior-improvements.html">保留舊十案</a><a href="model3d.html">原ABC</a></nav>'+"".join(sections)+'<script src="../../assets/plan_viewer.js"></script></body></html>'
    return page.replace('</nav>', '</nav><p data-display-revision="2">展示v2：3D整層預設只留重點短標籤，房間特寫將設備名稱移到「設備清單」，可另切全部標籤。已有門位只表示已預排，通行、救援與家規仍未核；本次不改任何格局、門窗或家具。</p>', 1)


def write_study(study: dict, root: Path = ROOT) -> dict:
    directory = root / OUT
    directory.mkdir(parents=True, exist_ok=True)
    manifest = copy.deepcopy(study)
    for o in manifest["options"]:
        for s in o["states"]:
            s.pop("model")
    write_json(directory / "review.json", manifest)
    for o in study["options"]:
        for state in o["states"]:
            for f in state["plans"]["floors"]:
                url = f'../b32-rear-right-3d.html?scheme={o["id"]}&use={state["id"]}'
                svg = ET.fromstring(render_plan("B", f, viewer_url=url))
                svg.set("width", "660")
                svg.set("height", "1903")
                svg.set("data-study-option", o["id"])
                svg.set("data-use-state", state["id"])
                for room in f["rooms"]:
                    for route in room["features"].get("b32_route_overlays", []):
                        line = ET.SubElement(svg, "{http://www.w3.org/2000/svg}polyline", {
                            "points": " ".join(f"{x},{y}" for x, y in route["points_mm"]), "fill": "none", "stroke": "#247c98",
                            "stroke-width": "30", "stroke-dasharray": "100 65", "data-b32-route": route["kind"]})
                        ET.SubElement(line, "{http://www.w3.org/2000/svg}title").text = "指定本體中心試線／非照護或搬轎核可"
                ET.SubElement(svg, "{http://www.w3.org/2000/svg}text", {"x": "0", "y": "-820", "font-size": "170"}).text = STATE_LABELS[state["id"]]+"／深化未採用，原需求保留"
                (directory / f["plan_file"]).write_text(ET.tostring(svg, encoding="unicode"), encoding="utf-8")
    (root / INDEX).write_text(render_index(study), encoding="utf-8")
    controls = (root / "scripts/templates/bc-options-controls.html").read_text().replace("bc-options.html", "b32-rear-right.html").replace("B 家規／C 照護", "B32後右公衛／後左武轎庫").replace("B／C比較", "B32兩版深化")
    controls = controls.replace('<div class="bc-study-links">', '<label for="study-use">使用狀態<select id="study-use" style="display:block;width:100%;min-height:44px;background:#132238;color:#eef6ff"></select></label><div class="bc-study-links">')
    controls += '''<style>
      #b32-label-mode{display:block;width:100%;min-height:44px;background:#132238;color:#eef6ff;font:inherit}
      #b32-label-mode:focus-visible{outline:3px solid #ffdda1;outline-offset:2px}
      #b32-room-details-panel{border:1px solid #739ca6;border-radius:6px;padding:10px;margin:10px 0;font-size:12px;line-height:1.6}
      #b32-room-details-panel p{margin:8px 0;overflow-wrap:anywhere}
      #b32-room-details-panel [hidden]{display:none!important}
    </style>'''
    controls = controls.replace('<div class="bc-study-links">', '<label for="b32-label-mode">模型標籤<select id="b32-label-mode"><option value="compact">重點（預設）</option><option value="all">全部標籤（檢視用）</option></select></label><p class="hint">整層只留主要空間；特寫不疊設備名稱，按「設備清單」查尺寸與入口限制。完整房名仍在下方選房清單。</p><div class="bc-study-links">')
    data = {"b32_rear_right": {"default_option": study["default_option"], "default_state": study["default_state"],
        "display_revision": DISPLAY_REVISION,
        "options": [{"id": o["id"], "label": o["label"], "states": [{k: s[k] for k in ("id", "label", "model")}
                    for s in o["states"]]} for o in study["options"]]}}
    text = viewer.render_html(data, viewer.three_source()[0], study_controls=controls, study_bootstrap=(root / BOOTSTRAP).read_text())
    def patch_once(anchor: str, replacement: str) -> None:
        nonlocal text
        if text.count(anchor) != 1:
            raise ContractError("Local B32 display anchor changed: "+anchor[:65])
        text = text.replace(anchor, replacement)

    patch_once('  var furnitureLabelRects=[];', (root / DISPLAY).read_text()+'\n  var furnitureLabelRects=[];')
    patch_once('var enabled = document.getElementById("furniture-names").checked && !!viewState.room;',
        'var enabled = document.getElementById("furniture-names").checked && !!viewState.room && b32DisplayContext().mode==="all";')
    # The shared facade synchronizer runs again after initialization/scope
    # changes. Compose its normal lock with our density policy in this viewer
    # only; never allow it to re-enable compact-mode furniture labels.
    patch_once('      control.disabled=active || (id==="room-cutaway" && presentation!=="tour") ||',
        '      control.disabled=active || (id==="furniture-names" && document.getElementById("b32-label-mode").value!=="all") || (id==="room-cutaway" && presentation!=="tour") ||')
    patch_once('cell.name+(features.access_pending?" · 入口待定":"")', 'b32RoomText(cell,features)')
    patch_once('    label.textContent = text;\n    label.title = "示意定位，未經現勘或建築師核定";',
        '    label.textContent = text;\n    label.dataset.b32FullText=text;\n    if(kind==="room"){label.setAttribute("aria-label",text);}\n    label.title = text+"；示意定位，未經現勘或建築師核定";')
    patch_once('    var occupied=furnitureLabelRects.slice(), area=overlayLabelArea();',
        '    var occupied=furnitureLabelRects.slice(), area=overlayLabelArea(),b32Context=b32DisplayContext(),b32Shown=0;')
    patch_once('      var point=mesh.parent.localToWorld(entry.point.clone());',
        '      if(!b32LabelPolicy(entry,b32Context) || b32Shown>=b32LabelLimit(b32Context)){show=false;}\n'
        '      entry.label.textContent=entry.kind==="room" && b32Context.mode==="compact" ? b32ShortRoomText(mesh.userData.cell) : entry.label.dataset.b32FullText;\n'
        '      var point=mesh.parent.localToWorld(entry.point.clone());')
    patch_once('      occupied.push(placed);\n      entry.label.style.left=placed.x+"px";',
        '      occupied.push(placed);b32Shown+=1;\n      entry.label.style.left=placed.x+"px";')
    patch_once('    actions.hidden = presentation !== "tour" || !viewState.room;',
        '    actions.hidden = presentation !== "tour" || !viewState.room;\n    b32SyncRoomReadout();')
    patch_once('      <p id="room-cutaway-status" role="status" hidden></p>',
        '      <button type="button" class="room-view-button" id="b32-room-details" aria-controls="b32-room-details-panel">設備清單</button>\n      <p id="room-cutaway-status" role="status" hidden></p>')
    patch_once('checked /> 顯示家具名稱（單房）</label>', 'checked /> 全部標籤模式：顯示家具名稱（單房）</label>')
    patch_once('    <div id="furniture-list" aria-label="本房家具清單"></div>',
        '    <section id="b32-room-details-panel" aria-label="設備與入口資料">'
        '<button type="button" class="room-view-button" id="b32-details-back">返回模型</button>'
        '<p id="b32-room-entry-status" role="status" hidden></p>'
        '<div id="furniture-list" aria-label="本房家具清單"></div></section>')
    patch_once('      geomSource: geomSource,', '      b32Display:b32DisplayEvidence(),\n      geomSource: geomSource,')
    anchor = "    var hvac=features.hvac || {};"
    if text.count(anchor) != 1:
        raise ContractError("Local floor-envelope renderer anchor changed")
    overlay = '''    (features.reserved_mm || []).filter(function(r){return r.kind.indexOf("b-separate-")===0;}).forEach(function(r){
      var b=r.aabb,points=[[b.minX,b.minY],[b.maxX,b.minY],[b.maxX,b.maxY],[b.minX,b.maxY],[b.minX,b.minY]].map(function(p){return new THREE.Vector3(p[0]*MM,base+.04,wz(p[1]));});
      var line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineDashedMaterial({color:0xb45309,dashSize:.06,gapSize:.035,clippingPlanes:[clipPlane]}));line.computeLineDistances();line.userData.b32StudyEnvelope=r.kind;group.add(line);
    });
    (features.b32_route_overlays || []).forEach(function(r){
      var points=r.points_mm.map(function(p){return new THREE.Vector3(p[0]*MM,base+.07,wz(p[1]));});
      var line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineDashedMaterial({color:0x247c98,dashSize:.1,gapSize:.065,clippingPlanes:[clipPlane]}));line.computeLineDistances();line.userData.b32Route=r.kind;group.add(line);
    });
'''
    text = text.replace(anchor, overlay+anchor)
    text = text.replace('htmlHref="bc-options.html#"', 'htmlHref="b32-rear-right.html#"')
    warning = '      if(features.access_pending){row("入口待配置", "原格位未提供合適的公共入口相鄰空間，不以浴廁、臥室、弱電間或武轎室充當穿越通道。須補走道／正式門位；不能據本圖確認可進出。");}'
    patch_once(warning, '      if(features.access_pending){row("入口資料／通行未核",escapeHtml(b32EntryDescription(cell,features))+"；門組、完成面、救援與公共通行未核。");}')
    (root / VIEWER).write_text(text, encoding="utf-8")
    return {"index": INDEX, "viewer": VIEWER, "report": OUT+"/review.json", "options": 2, "states": 6, "svgs": 24}


def main() -> None:
    protected = ["inputs/requirements.json", "inputs/physical-items.json", "inputs/furniture-layout.json", interior.SOURCE,
                 "structured/candidates/model3d.html", "structured/candidates/b32-entry-options-3d.html",
                 "structured/candidates/c-integrated-options-3d.html", "structured/candidates/interior-improvements.html",
                 "structured/candidates/interior-improvements-3d.html", "structured/candidates/interior-improvements/review.json",
                 "inputs/revisions/R000/manifest.json"]
    protected += [str(p.relative_to(ROOT)) for p in (ROOT / interior.OUT).glob("*.svg")]
    before = {p: sha256_file(ROOT / p) for p in protected}
    study = build_study()
    paths = write_study(study)
    if before != {p: sha256_file(ROOT / p) for p in protected}:
        raise ContractError("Protected old comparison/requirement/archive changed")
    print(json.dumps({**paths, "report_hash": study["report_hash"], "rendered_qa": "not-run"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

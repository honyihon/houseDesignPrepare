"""Small, isolated B32 service-zone comparisons; no renderer or scene runtime."""

from __future__ import annotations

import math
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, utc_now, write_json
from house_design.physical_items import load_physical_items
from house_design.requirement_reconciliation import _public_path, _snapshot, _union_area, discussion_area

SOURCE = "inputs/b32-service-study.json"
SCHEMA = "house-b32-service-review-v1"
WARNING = "只比較後段分區、代表設備與假設操作外廓；不是已採用的HTML／3D配置。獨立家務通道不等於全程通行、無障礙、消防、搬轎或專業通過。"


def _box(rect: list) -> tuple:
    if not isinstance(rect, list) or len(rect) != 4:
        raise ContractError("Expected [x,y,width,depth]")
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in rect) or min(rect[2:]) <= 0:
        raise ContractError("Finite positive rectangle dimensions required")
    x, y, w, h = rect
    return x, y, x+w, y+h


def _hits(a: list, b: list) -> bool:
    a0, a1, a2, a3 = _box(a)
    b0, b1, b2, b3 = _box(b)
    return min(a2, b2) > max(a0, b0) and min(a3, b3) > max(a1, b1)


def _covered(rect: list, areas: list[list]) -> bool:
    x0, y0, x1, y1 = _box(rect)
    clips = [(max(x0, a), max(y0, b), min(x1, c), min(y1, d)) for a, b, c, d in map(_box, areas)]
    clips = [r for r in clips if r[2] > r[0] and r[3] > r[1]]
    return abs(_union_area(clips) - (x1-x0)*(y1-y0)) < 1e-5


def _area(rects: list[list], inset: int) -> float:
    return discussion_area([{"geometry": dict(zip(("x_mm", "y_mm", "w_mm", "h_mm"), r, strict=True))} for r in rects], inset)


def _from_room(room: dict) -> list:
    return [room["geometry"][k] for k in ("x_mm", "y_mm", "w_mm", "h_mm")]


def _baseline_access(rooms: dict) -> bool:
    graph = {k: set() for k in rooms}
    for key, room in rooms.items():
        for opening in [*room["features"].get("doors", []), *room["features"].get("open_connections", [])]:
            neighbor = opening.get("neighbor")
            if neighbor:
                local = neighbor.rsplit(":", 1)[-1]
                if local in graph:
                    graph[key].add(local)
    pending, visited = ["shrine"], set()
    while pending:
        key = pending.pop()
        if key in visited or key in {"bath1", "bath-extension", "storage"}:
            continue
        if key == "work-reserve":
            return True
        visited.add(key)
        pending.extend(graph.get(key, set()) - visited)
    return False


def _zones(option: dict, common: dict) -> dict[str, list[list]]:
    p, end, work_y, work_w = option["passage_width_mm"], option["bath_end_y_mm"], common["work_front_y_mm"], common["work_width_mm"]
    return {
        "dry-backing": [common["dry_backing_rect_mm"]],
        "public-housework-passage": [[0, 11370, p, work_y-11370]],
        "bathroom": [[p, 11370, 2500-p, 1600], [p, 12970, 4320-p, end-12970]],
        "public-carry-passage": [[4320, 11370, 1680, 2960]],
        "laundry": [[0, work_y, work_w, 17630-work_y]],
        "storage": [[4320, 14330, 1680, 3300], [2500, end, 1820, 17630-end], [p, end, 2500-p, work_y-end]],
    }


def _translation(a: list, b: list, width: float, depth: float) -> list:
    return [min(a[0], b[0])-width/2, min(a[1], b[1])-depth/2,
            abs(a[0]-b[0])+width, abs(a[1]-b[1])+depth]


def _transport(mode: str, zones: dict, body: list, gate_center: float) -> dict:
    x, y, w, d = body
    center = [x+w/2, y+d/2]
    # Rear threshold crossing/outdoor approach are excluded explicitly.
    if mode == "rear":
        points = [[gate_center, 17630-d/2], [gate_center, center[1]], center]
    else:
        points = [[5160, 14330], center]
    sweeps = [_translation(a, b, w, d) for a, b in zip(points, points[1:], strict=False)]
    areas = zones["storage"] + zones["public-carry-passage"]
    failures = [i for i, r in enumerate(sweeps) if not _covered(r, areas)]
    if not _covered(body, zones["storage"]):
        failures.append("parked-body")
    return {"scope": "rear-service-zone-only-body-translation-no-yaw-no-people-poles-wheels", "points_mm": points,
            "sweeps_mm": sweeps, "body_failures": failures, "outdoor_threshold_and_full_route": "unknown",
            "assembled_transport_approval": "unknown"}


def _roof(settings: dict, plans: dict, catalog: dict) -> dict:
    floor = next(f for f in plans["floors"] if f["id"] == "floor-4")
    rooms = {r["key"]: r for r in floor["rooms"]}
    protected = [_from_room(r) for r in floor["rooms"] if r["key"].startswith("shrine-buffer-")]
    allowed = [_from_room(rooms[k]) for k in ("service-rf", "rear-roof")]
    hvac = []
    for r in floor["rooms"]:
        for reserve in r["features"].get("reserved_mm", []):
            if reserve["kind"] == "hvac-service":
                a = reserve["aabb"]
                hvac.append([a["minX"], a["minY"], a["maxX"]-a["minX"], a["maxY"]-a["minY"]])
    items, errors = [], []
    for raw in settings["items"]:
        item, clearance = {**raw}, settings["assumed_service_each_side_mm"]
        product = catalog[raw["catalog"]]
        x, y, w, d = raw["rect_mm"]
        if [w, d] != [product["width_mm"], product["depth_mm"]]:
            raise ContractError("Roof products may not be scaled to fit")
        envelope = [x-clearance, y-clearance, w+2*clearance, d+2*clearance]
        item.update(label=product["label"], height_mm=product["height_mm"], assumed_service_mm=envelope)
        if (not _covered(envelope, allowed) or any(_hits(envelope, r) for r in protected+hvac)
                or _hits(envelope, settings["route_rect_mm"])):
            errors.append(raw["id"])
        items.append(item)
    for index, item in enumerate(items):
        if any(_hits(item["assumed_service_mm"], other["assumed_service_mm"]) for other in items[index+1:]):
            errors.append(item["id"] + ":service-overlap")
    if not _covered(settings["route_rect_mm"], allowed):
        errors.append("roof-route")
    projection = []
    for f in plans["floors"]:
        if f["id"] not in {"floor-2", "floor-3"}:
            continue
        for r in f["rooms"]:
            if r["kind"] == "bedroom":
                projection += [{"equipment_id": i["id"], "bedroom_id": r["id"]} for i in items if _hits(i["rect_mm"], _from_room(r))]
    return {"items": items, "route_rect_mm": settings["route_rect_mm"], "protected_rects_mm": protected,
            "existing_hvac_service_rects_mm": hvac, "coordinate_failures": errors,
            "equipment_over_sleeping_rooms": projection,
            "structure_vibration_manuals_and_replacement": "unknown", "water_only_lower_bound_kg": settings["water_load_lower_bound_kg"],
            "note": settings["note"]}


def build_service_study(root: Path = ROOT) -> dict:
    settings = read_json(root / SOURCE)
    project, requirements = read_json(root / "inputs/project.json"), read_json(root / "inputs/requirements.json")
    base = read_json(_public_path(root, settings["base_settings"]))
    if (settings.get("schema") != "house-b32-service-study-v1" or settings.get("status") != "comparison-only-not-adopted"
            or settings.get("project_id") != project.get("project_id") or settings["frame_mm"] != [6000, 17630]
            or base["frame_mm"] != settings["frame_mm"] or settings["frontage_depth_mm"] != base["frontage_depth_mm"]
            or base["frontage_depth_mm"] != 3900 or settings["insets_mm"] != [80, 100, 115]
            or set(settings["gates"].values()) != {"unknown"}
            or [o["id"] for o in settings["options"]] != ["compact-service", "wide-service", "storage-first"]
            or settings["roof"]["water_load_lower_bound_kg"] != 1000):
        raise ContractError("Service study must preserve B32 frame, arcade and every unknown approval")
    snapshot = _snapshot(_public_path(root, settings["source"]), "HOUSE_B32_ENTRY_OPTIONS", "house-b32-entry-options-v1")
    catalog = read_json(root / "inputs/furniture-layout.json")["catalog"]
    physical = load_physical_items(root / "inputs/physical-items.json")["by_id"]["B.palanquin.primary"]
    dims = physical["active_dimensions"]
    source_paths = [SOURCE, settings["source"], settings["base_settings"], "inputs/project.json", "inputs/requirements.json",
                    "inputs/furniture-layout.json", "inputs/physical-items.json"]
    source_hashes = {p: sha256_file(_public_path(root, p)) for p in source_paths}
    mismatches = []
    for name, expected in snapshot["source_hashes"].items():
        path = _public_path(root, name)
        current = sha256_file(path) if path.is_file() else None
        source_hashes[name] = current
        if current != expected:
            mismatches.append(name)
    reqs = {r["id"]: r for r in requirements["requirements"]}
    common, cases, roof = settings["common"], [], {}
    for source in snapshot["options"]:
        mode, plans = source["entry_mode"], source["plans"]
        if source["id"] not in {"b32-rear", "b32-front"} or plans["id"] != "B":
            raise ContractError("Unexpected B32 entry mode or building")
        first = {r["key"]: r for r in plans["floors"][0]["rooms"]}
        if common["dry_backing_rect_mm"] != _from_room(first["altar-backing"]):
            raise ContractError("The shrine's dry backing may not be repurposed")
        roof[source["id"]] = _roof(settings["roof"], plans, catalog)
        for option in settings["options"]:
            zones = _zones(option, common)
            all_rects = [r for values in zones.values() for r in values]
            if (not _covered([0, 11370, 6000, 6260], all_rects)
                    or any(not _covered(r, [[0, 11370, 6000, 6260]]) for r in all_rects)
                    or sum(r[2]*r[3] for r in all_rects) != 6000*6260):
                raise ContractError("Service partitions must tile the unchanged rear frame without overlaps")
            rows = []
            for zone, rid in (("bathroom", "B.floor-1.bath_acc"), ("storage", "B.floor-1.palanquin"), ("laundry", "B.floor-1.balcony_b")):
                c = reqs[rid]["constraints"]
                sensitivity = [{"inset_mm": i, "area_sqm": _area(zones[zone], i)} for i in settings["insets_mm"]]
                rows.append({"requirement_id": rid, "zone": zone, "sensitivity": sensitivity,
                             "original_minimum_sqm": c["min_sqm"], "original_target_sqm": c["target_sqm"],
                             "below_target_at_80mm": sensitivity[0]["area_sqm"] < c["target_sqm"],
                             "below_minimum_insets_mm": [v["inset_mm"] for v in sensitivity if v["area_sqm"] < c["min_sqm"]],
                             "functional_acceptance": "unknown"})
            laundry_errors = []
            for i in common["laundry_items"]:
                if i["id"] == "washer" and i["rect_mm"][2:] != [catalog[common["washer_catalog"]][k] for k in ("width_mm", "depth_mm")]:
                    raise ContractError("Washer may not be scaled")
                if i["id"] == "utility-sink" and i["rect_mm"][2:] != [common["utility_sink"][k] for k in ("width_mm", "depth_mm")]:
                    raise ContractError("Utility sink may not be scaled")
                if not _covered(i["rect_mm"], zones["laundry"]):
                    laundry_errors.append(i["id"])
            for index, r in enumerate(common["laundry_operation_rects_mm"]):
                if not _covered(r, zones["laundry"]) or any(_hits(r, i["rect_mm"]) for i in common["laundry_items"]):
                    laundry_errors.append(f"operation-{index}")
            x, y = common["palanquin_park_origin_mm"]
            body = [x, y, dims["width_mm"], dims["depth_mm"]]
            transport = _transport(mode, zones, body, source.get("rear_gate_center_mm", 4500))
            transport["gate_budgets"] = source["review"]["program"]["transport"]["gate_budgets"]
            transport["gate_width_failures"] = [g["room_id"] for g in transport["gate_budgets"] if dims["width_mm"] > g["discussion_clear_mm"]]
            transport["storage_dimension_source"] = physical["active_dimension_source"]
            cases.append({
                "id": source["id"]+"-"+option["id"], "base_option": source["id"], "entry_mode": mode,
                "service_option": option["id"], "label": option["label"], "position": option["position"], "note": option["note"],
                "zones_mm": zones, "area_rows": rows, "palanquin_body_mm": body,
                "original_park_mm": [first["storage"]["furniture"][0]["placement"]["aabb"][k] for k in ("minX", "minY")],
                "transport": transport, "baseline_work_access_without_storage_or_bath": _baseline_access(first),
                "new_room_graph_without_storage_or_bath": ["shrine", "public-housework-passage", "laundry"],
                "continuous_front_door_to_laundry_clearance": "unknown-shrine-seating-must-be-redrawn",
                "housework_clear_width_assumptions_mm": [{"inset_mm": i, "width_mm": option["passage_width_mm"]-2*i} for i in settings["insets_mm"]],
                "fire_separation_and_opening_product": "unknown-no-certified-door-proposed",
                "laundry_items": common["laundry_items"], "laundry_operation_rects_mm": common["laundry_operation_rects_mm"],
                "laundry_coordinate_failures": laundry_errors, "bathroom_fixtures_and_rescue": "requires-coordinated-redraw-not-approved",
                "rear_window_and_outdoor_use_rights": "unknown", "adopted": False,
            })
    if len(cases) != 6 or set(roof) != {"b32-rear", "b32-front"}:
        raise ContractError("Study must keep three independent service comparisons for each entry mode")
    backup = settings["idf"]["upper_dry_backup"]
    idf_results = {}
    for source in snapshot["options"]:
        room = next(r for f in source["plans"]["floors"] for r in f["rooms"] if r["id"] == backup["room_id"])
        product = catalog[settings["idf"]["catalog"]]
        if backup["body_rect_mm"][2:] != [product["width_mm"], product["depth_mm"]]:
            raise ContractError("IDF rack may not be scaled")
        bounds = (backup["body_rect_mm"], backup["front_service_rect_mm"])
        occupied = [i["placement"]["aabb"] for i in room.get("furniture", [])]
        obstacles = [[a["minX"], a["minY"], a["maxX"]-a["minX"], a["maxY"]-a["minY"]] for a in occupied]
        valid = (all(_covered(r, [_from_room(room)]) for r in bounds)
                 and not any(_hits(r, o) for r in bounds for o in obstacles)
                 and room["kind"] not in {"bath", "kitchen", "bedroom", "stair"})
        idf_results[source["id"]] = {"body_and_front_service_inside_dry_room": valid,
                                    "first_floor_requirement_satisfied": False, "floor_change_approved": False}
    report = {"schema": SCHEMA, "generated_at": utc_now(), "project_id": project["project_id"], "warning": WARNING,
              "source_hashes": source_hashes, "embedded_source_mismatches": mismatches,
              "frame_mm": settings["frame_mm"], "land_ping": 6000*17630/1e6/(400/121), "cases": cases,
              "roof": roof, "idf": {**settings["idf"], "coordinate_results": idf_results}, "gates": settings["gates"],
              "generator_sha256": sha256_file(Path(__file__)),
              "helper_sha256": {name: sha256_file(Path(__file__).with_name(name))
                                for name in ("requirement_reconciliation.py", "physical_items.py", "contracts.py")},
              "rendered_qa": "not-run", "professional_approval": "unknown"}
    report["report_hash"] = stable_hash({k: v for k, v in report.items() if k != "generated_at"})
    return report


def study_svg(case: dict, *, roof: dict | None = None) -> str:
    tree = Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": "-100 10600 6500 8100", "width": "900", "height": "1122", "role": "img"})
    SubElement(tree, "title").text = "B32家務機電分區比較，未採用，非完整HTML／3D圖"

    def text(x, y, label, size=170):
        SubElement(tree, "text", {"x": str(x), "y": str(y), "font-size": str(size), "font-family": "sans-serif"}).text = label

    def rect(r, color, dashed=False):
        x, y, w, h = r
        SubElement(tree, "rect", {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "fill": color,
                                 "stroke": "#334155", "stroke-width": "12", **({"stroke-dasharray": "50 35"} if dashed else {})})

    text(0, 10850, "B32 分區研究｜未採用，不是施工／全功能圖", 200)
    if roof:
        rect([0, 11370, 6000, 6260], "#f8fafc")
        for r in roof["existing_hvac_service_rects_mm"]:
            rect(r, "#dbeafe", True)
        rect(roof["route_rect_mm"], "#dcfce7", True)
        text(2480, 11600, "1m討論通路", 140)
        for i in roof["items"]:
            rect(i["assumed_service_mm"], "none", True)
            rect(i["rect_mm"], "#cbd5e1")
            text(i["rect_mm"][0], i["rect_mm"][1]+250, i["label"], 155)
        text(0, 11200, "上方神明堂保護區不放設備（本圖裁切未畫）", 160)
        text(0, 18000, "泵浦位於下層睡眠投影：隔振／結構未解，不是選址核可", 165)
    else:
        labels = {"dry-backing": ("乾式法器收納", "#fef3c7"), "public-housework-passage": ("家務通道＊", "#dcfce7"),
                  "bathroom": ("淋浴衛浴重排區＊", "#cffafe"), "public-carry-passage": ("原搬轎側緣", "#e2e8f0"),
                  "laundry": ("後工作陽台候選＊", "#f0fdf4"), "storage": ("武轎儲藏重排區＊", "#e0e7ff")}
        for key, values in case["zones_mm"].items():
            label, color = labels[key]
            for r in values:
                rect(r, color)
            r = max(values, key=lambda r: r[2]*r[3])
            text(r[0]+70, r[1]+230, label, 145)
        rect(case["palanquin_body_mm"], "#a5b4fc")
        text(case["palanquin_body_mm"][0]+40, case["palanquin_body_mm"][1]+300, "武轎本體", 155)
        for i in case["laundry_items"]:
            rect(i["rect_mm"], "#94a3b8")
            text(i["rect_mm"][0]+20, i["rect_mm"][1]+300, "洗衣機" if i["id"] == "washer" else "洗槽", 130)
        for r in case["laundry_operation_rects_mm"]:
            rect(r, "none", True)
        text(0, 11200, "通道起點在祭拜區：座位、連續動線與防火門須另排", 165)
        text(0, 18000, "＊衛浴設備／轉位／救援尚未重排，非照護已通過", 175)
    text(0, 18300, "外框不增；後窗／通行權、原廠、結構及專業條件仍未知", 165)
    return tostring(tree, encoding="unicode")


def write_service_study(report: dict, root: Path, output_root: Path | None = None) -> dict[str, Path]:
    directory = output_root if output_root is not None else root / "structured/service-study"
    paths = {"json": directory / "b32-services.json", "markdown": directory / "b32-services.md"}
    write_json(paths["json"], report)
    lines = ["# B32 家務／機電最小修改比較", "", report["warning"], "",
             "原B32、ABC、需求與實測均不改。三個分區方向 × 後門／前門兩案分開，共六案。", "",
             "優先討論compact-service：保留後側採光／家務位置，新增約1m家務通道，但儲藏低於原10.5m²目標。不是已選案。", "",
             "## 面積與代價（80mm只是討論內縮）", "", "| 搬轎案／家務案 | 衛浴m² | 儲藏m² | 工作區m² | 判讀 |", "| --- | --- | --- | --- | --- |"]
    for c in report["cases"]:
        values = {r["zone"]: r["sensitivity"][0]["area_sqm"] for r in c["area_rows"]}
        lines.append(f"| {c['id']} | {values['bathroom']:.4f} | {values['storage']:.4f} | {values['laundry']:.4f} | {c['note']} |")
    lines += ["", "全案原目標仍保留：衛浴7／儲藏10.5／工作陽台5m²，下限4.5／9／4m²。不是證明所有可能排法都無解。", "",
              "## 不能被圖面掩蓋的問題", "",
              "- 原工作區只能經儲藏室；新圖只成立分區鄰接，祭拜區座椅與正門到通道的完整人行、消防門仍需另排。",
              "- 浴室只比較L形可分配面積，沒有排完設備、轉位、扶手與倒地救援；不能宣稱淋浴／照護可用。",
              "- 後門案武轎本體改停右後，前門案原已在右後；只驗基地內本體平移，不驗組裝外廓、門檻、門外、人員、輪具與實物演練。",
              "- 1F IDF仍未解；梯下缺剖面不能算可用。3F乾式區僅備選，移樓層需屋主決定，不填補原1F需求。",
              "- 屋頂另試排水塔／泵／熱泵及600mm假設維修外廓，避神明堂保護與現有冷氣維修帶；原廠要求未知。泵投影下方臥室，隔振／結構未解。",
              "- 1000L水塔僅水重約1噸，不含塔體基座與地震／動載；不因放得下就有結構或屋突許可。",
              "- 工作區不是已核外陽台，後界窗權利、遮雨、排水、排濕和消防仍未知；洗衣操作與進出需分時演練。", ""]
    if report["embedded_source_mismatches"]:
        lines += ["來源已有變動，以上只作舊快照比較，不能當本版：", *[f"- `{p}`" for p in report["embedded_source_mismatches"]], ""]
    for c in report["cases"]:
        name = c["id"]+".svg"
        (directory / name).write_text(study_svg(c), encoding="utf-8")
        lines += [f"## {c['id']}", "", f"[開啟後段分區圖]({name})", "",
                  "每側內縮／通道討論淨寬：" + "、".join(f"{v['inset_mm']}／{v['width_mm']}mm" for v in c["housework_clear_width_assumptions_mm"]), ""]
        for r in c["area_rows"]:
            lines.append(f"- {r['requirement_id']}："+"、".join(f"{v['inset_mm']}mm → {v['area_sqm']:.4f}m²" for v in r["sensitivity"])
                         + f"；原目標{r['original_target_sqm']}m²、下限{r['original_minimum_sqm']}m²，功能未核。")
        lines += [f"- 本體／操作座標缺口：搬運{c['transport']['body_failures']}；洗衣{c['laundry_coordinate_failures']}。空陣列只代表這些矩形未撞，非整體通過。", ""]
    roof = report["roof"]["b32-rear"]
    (directory / "roof-equipment.svg").write_text(study_svg({}, roof=roof), encoding="utf-8")
    lines += ["## 屋頂代表設備試排", "", "[開啟屋頂設備圖](roof-equipment.svg)", "",
              "後門／前門各自檢查屋頂；不因外框相同就借用結果。下方睡眠投影詳見JSON，未解除隔振／承重待核。", "",
              f"來源、尺寸與矩形結果見同目錄JSON；report_hash：`{report['report_hash']}`", ""]
    paths["markdown"].write_text("\n".join(lines), encoding="utf-8")
    return paths

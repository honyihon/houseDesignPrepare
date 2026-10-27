#!/usr/bin/env python3
"""Patch existing public snapshots only; no full build, solver or browser.

The historical ABC, B32, interior comparisons and archives are read-only.
The new hub holds explicit alternatives, not an implicitly adopted master plan.
"""
from __future__ import annotations

import copy
import html
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import export_interior_improvements as interior
import export_model_3d as viewer
from lib.model3d_plan import plan_data, render_plan

from house_design.b32_rear_right import aperture_walls, cultural_screen, rect, review_state
from house_design.b32_service_detail import _inside, _route
from house_design.b32_services import _hits
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, utc_now, write_json
from house_design.current_design_basis import (
    SCHEMA,
    STATUS,
    engineering_review,
    requirement_ledger,
    sleeping_room,
    validate_config,
)
from house_design.requirement_reconciliation import _public_path

SOURCE = "inputs/current-design-basis.json"
OUT = "structured/candidates/current-design-basis"
INDEX = OUT+".html"
VIEWER = OUT+"-3d.html"
BOOTSTRAP = "scripts/templates/current-design-bootstrap.js"
CAMERA = "scripts/templates/current-design-camera.js"


def _verified_report(root: Path, path: str) -> dict:
    report = read_json(_public_path(root, path))
    if not report.get("source_hashes"):
        raise ContractError("Missing source evidence: "+path)
    for name, digest in report["source_hashes"].items():
        source = _public_path(root, name)
        if not source.is_file() or sha256_file(source) != digest:
            raise ContractError("Stale base source; current study not generated: "+name)
    return report


def _item(cell: dict, local: str) -> dict:
    items = [i for i in cell["furniture"] if i["id"].rsplit(":", 1)[-1] == local]
    if len(items) != 1:
        raise ContractError("Missing/ambiguous original item: "+cell["id"]+":"+local)
    return copy.deepcopy(items[0])


def _move(cell: dict, local: str, area: list, *, yaw: int | None = None, anchor: str | None = None) -> None:
    item = _item(cell, local)
    old = cell["furniture_placements"]["tour_mm"].pop(item["id"])
    cell["furniture"] = [i for i in cell["furniture"] if i["id"] != item["id"]]
    face = old["wall_anchor"] if anchor is None else anchor
    if face:
        x, y, w, d = interior._rect(cell)
        item["wall_gap_mm"] = {"left": area[0]-x, "right": x+w-area[0]-area[2],
            "front": area[1]-y, "rear": y+d-area[1]-area[3]}[face]
    interior._place(cell, item, area, old["rotation_deg"] if yaw is None else yaw, face,
                    freestanding_operation=True)


def _place(cell: dict, item: dict, area: list, yaw: int, anchor: str, **kwargs) -> None:
    item = copy.deepcopy(item)
    if anchor:
        x, y, w, d = interior._rect(cell)
        item["wall_gap_mm"] = {"left": area[0]-x, "right": x+w-area[0]-area[2],
            "front": area[1]-y, "rear": y+d-area[1]-area[3]}[anchor]
    interior._place(cell, item, area, yaw, anchor, **kwargs)


def _reserve(cell: dict, name: str, area: list) -> None:
    cell["tour_features"]["fixed_reserved_mm"].append({"kind": "basis-"+name,
        "aabb": interior._bounds(area), "status": "coordinate-budget-not-product-or-care-approval"})


def _generic(sample: dict, *, catalog: str, label: str, shape: str, size: list, front: int = 0) -> dict:
    result = {k: v for k, v in sample.items() if not k.startswith("physical_")}
    result.update(catalog_id=catalog, label=label, shape=shape, width_mm=size[0], depth_mm=size[1], height_mm=size[2],
        physical_item_id=None, basis="room-use-inference", front_clearance_mm=front, rear_clearance_mm=0,
        left_clearance_mm=0, right_clearance_mm=0, mount_height_mm=0, wall_gap_mm=150,
        note="一般代表尺寸，非選定產品或新增實測；本輪未採用，管線、防雨、防墜及使用仍待核。")
    return result


def _finish(model: dict, bid: str, oid: str, label: str, notes: list, state: str) -> dict:
    interior._finish(model, bid, oid, label, notes)
    model["source"] = {"current_design_basis": SOURCE, "geometry_basis": "explicit-local-snapshot-patches-not-full-build"}
    model["bc_option"].update(revision=1, use_state=state, adopted=False)
    return model


def b_refinement(model: dict, cfg: dict) -> dict:
    baseline = copy.deepcopy(model["buildings"][0])
    before = interior._screen(model, cfg["insets_mm"], baseline)
    for floor in model["buildings"][0]["floors"]:
        changes = cfg["b"]["moves"].get(floor["id"], {})
        cells = interior._rooms(floor)
        for key, items in changes.items():
            for local, area in items.items():
                _move(cells[key], local, area)
        if changes:
            interior._rebuild(floor)
    return {"before_upper_body_flags": sum(not r["room"].startswith("B:floor-1:") for r in before["furniture_body_sensitivity"]),
        "edge_budget_mm": cfg["b"]["edge_budget_mm"], "budget_is_not_measured_wall": True,
        "room_boundaries_doors_windows_product_dimensions_and_counts": "retained",
        "first_floor_altered": False, "adopted": False}


def a_ensuite(model: dict, cfg: dict) -> dict:
    settings = cfg["a"]
    floor = model["buildings"][0]["floors"][1]
    old = copy.deepcopy(interior._rooms(floor))
    group = "basis-A-private-master"
    for key, area in zip(("master", "master-front"), settings["master_regions_mm"], strict=True):
        cell = interior._room(floor, key, area, template=old["master"], name="主臥乾區（套衛取捨比較）" if key == "master" else "主臥前側延伸（非獨立房）",
            kind="bedroom" if key == "master" else "other", group=group, role="" if key == "master" else "circulation", outdoor=False,
            window_mm=old["master"]["window_mm"] if key == "master" else 0, requirement_id="A.floor-2.master")
        if key == "master":
            # Retain the physical center/width of the original front window;
            # reusing a ratio after splitting a room would incorrectly hide it.
            old_rect = interior._rect(old["master"])
            center = old_rect[0]+old["master"]["tour_features"]["window_ratio"]*old_rect[2]
            cell["review_spec"]["window_ratio"] = (center-area[0])/area[2]
            floor["layout_review"]["rooms"][key] = copy.deepcopy(cell["review_spec"])
        interior._empty(cell)
    bath = interior._room(floor, "ensuite-study", settings["ensuite_mm"], template=old["master-bath"],
        name="主臥獨立套衛比較（無外窗／排氣待核）", kind="bath", group="", role="", outdoor=False,
        window_mm=0, requirement_id="A.floor-2.master_bath")
    interior._empty(bath)
    bath["tour_features"]["fixed_reserved_mm"] = []
    cells = interior._rooms(floor)
    for raw in settings["master_products"]:
        _place(cells["master"], _item(old["master"], raw["local"]), raw["rect_mm"], raw["rotation_deg"], raw["wall_anchor"])
    interior._empty(cells["study"])
    for raw in settings["study_products"]:
        item = _item(old[raw["source_room"]], raw["local"])
        if raw["source_room"] != "study":
            item["relocated_from"] = item["id"]
        _place(cells["study"], item, raw["rect_mm"], raw["rotation_deg"], raw["wall_anchor"], local=raw["local"])
    for raw in settings["fixtures"]:
        template = next(i for i in old["master-bath"]["furniture"] if i["catalog_id"] == raw["catalog"])
        product = _generic(template, catalog=template["catalog_id"], label=template["label"], shape=template["shape"],
            size=[template[k] for k in ("width_mm", "depth_mm", "height_mm")], front=template["front_clearance_mm"])
        _place(bath, product, raw["rect_mm"], raw["rotation_deg"], raw["wall_anchor"], local=raw["local"])
    connections = floor["layout_review"]["connections"]
    for connection in connections:
        if set(connection[:2]) == {"master", "front-service"}:
            connection[:] = ["master-front", "front-service", 900, 4800]
    connections += [["master", "master-front", "open"], ["master", "ensuite-study",
        {"width_mm": settings["door_nominal_mm"], "operation": "sliding", "label": "套衛表面拉門（向主臥前側停放／產品未定）"}, settings["door_center_y_mm"]]]
    interior._rebuild(floor)
    _reserve(cells["master"], "ensuite-slider-park", settings["slider_park_mm"])
    door = next(d for d in bath["tour_features"]["doors"] if d["neighbor"] == cells["master"]["id"])
    walls = aperture_walls({"geometry": bath["tour_mm"]}, door, 115, "ensuite-jamb-")
    all_cells = [cells[k] for k in ("master", "master-front", "ensuite-study")]
    obstacles = [{"id": i["id"], "rect_mm": interior._body(c, i)} for c in all_cells for i in c["furniture"]]
    parked = {"id": "ensuite-parked-leaf-budget", "rect_mm": settings["slider_park_mm"]}
    points = [[2800, 4300], [2800, 3500], [4500, 3500]]
    route = _route(points, 700, 700, [interior._rect(c) for c in all_cells], obstacles+walls+[parked], 115)
    closed_leaf = {"id": "closed-ensuite-slider", "rect_mm": [settings["slider_park_mm"][0],
        settings["door_center_y_mm"]-settings["door_nominal_mm"]/2, settings["slider_park_mm"][2], settings["door_nominal_mm"]]}
    closed = _route(points, 700, 700, [interior._rect(c) for c in all_cells], obstacles+walls+[closed_leaf], 115)
    if route["coordinate_failures"]:
        raise ContractError("A suite comparison does not have its specified open-door local body route")
    if not closed["coordinate_failures"]:
        raise ContractError("A suite route must not pass through a closed bathroom door")
    cells["master"]["tour_features"]["basis_routes"] = [{"points_mm": points, "kind": "700mm-adult-local-only-not-care-route"}]
    return {"status": settings["status"], "local_open_door_700mm_body_route": route,
        "local_closed_door_route": closed,
        "finished_door_clear_assumption_115mm": settings["door_nominal_mm"]-230,
        "independent_public_bath_retained": True, "third_floor_rear_window_bath_retained": True,
        "storage_relocations": ["180cm衣櫃一組→書房", "240cm淺櫃→書房"],
        "total_original_storage_product_dimensions_and_counts": "retained",
        "master_original_target_sqm": 16, "ensuite_original_target_sqm": 5,
        "windowless_new_ensuite_and_pipe_route_acceptance": "pending-owner-and-professionals"}


def c_workflow(model: dict, cfg: dict) -> dict:
    washers = [(f["id"], i) for f in model["buildings"][0]["floors"] for c in interior._rooms(f).values()
               for i in c["furniture"] if i["catalog_id"] == "washer"]
    if len(washers) != 1 or washers[0][0] != "floor-2":
        raise ContractError("C must retain exactly one existing washer on floor-2")
    first, second = model["buildings"][0]["floors"][:2]
    elder, balcony = interior._rooms(first)["elder"], interior._rooms(second)["balcony2f"]
    raw, settings = cfg["c"]["linen_basket"], cfg["c"]["balcony"]
    sample = _item(balcony, "washer")
    basket = _generic(sample, catalog="sealed-linen-basket", label="帶蓋污衣籃（非洗衣機）", shape="cabinet", size=[400, 350, raw["height_mm"]])
    _place(elder, basket, raw["rect_mm"], 180, "front", local="linen-basket")
    _reserve(elder, "linen-loading", raw["operation_mm"])
    _move(balcony, "washer", settings["washer_mm"])
    _move(balcony, "planter", settings["planter_mm"], yaw=90, anchor="")
    rack = _item(balcony, "clothes-rack")
    balcony["furniture"] = [i for i in balcony["furniture"] if i["id"] != rack["id"]]
    balcony["furniture_placements"]["tour_mm"].pop(rack["id"])
    rack["front_clearance_mm"] = 900
    _place(balcony, rack, settings["clothes_rack_mm"], 0, "", freestanding_operation=True)
    sink = _generic(sample, catalog="utility-sink-planning", label="獨立預洗槽（給排水待核）", shape="vanity", size=[600, 600, 850], front=800)
    locker = _generic(sample, catalog="locked-cleaner-planning", label="防雨上鎖洗劑櫃（產品待定）", shape="cabinet", size=[600, 450, 1000], front=600)
    _place(balcony, sink, settings["utility_sink_mm"], 270, "left", local="utility-sink")
    _place(balcony, locker, settings["locked_cleaner_mm"], 180, "front", local="locked-cleaner")
    for name, area in (("sink-use", settings["sink_operation_mm"]), ("rack-loading", settings["rack_loading_mm"])):
        _reserve(balcony, name, area)
    balcony["tour_features"]["basis_routes"] = [{"points_mm": settings[k], "kind": k} for k in ("route_mm", "rack_route_mm")]
    return {"workflow": cfg["c"]["workflow"], "washer_count": 1, "washer_floor": "floor-2",
        "first_floor_work_balcony": "unmet-original-4sqm-minimum-4.8sqm-target-retained",
        "accepted_kitchen_geometry_and_public_loss": "unchanged-450mm-1.08sqm",
        "caregiver_stair_carrying_drying_weather_and_balcony_rights": "unknown"}


def _local_c_review(model: dict, cfg: dict) -> dict:
    first, second = model["buildings"][0]["floors"][:2]
    cells, upper = interior._rooms(first), interior._rooms(second)
    elder, balcony = cells["elder"], upper["balcony2f"]
    areas = [interior._rect(balcony)]
    obstacles = [{"id": i["id"], "rect_mm": interior._body(balcony, i)} for i in balcony["furniture"]]
    hvac = [{"id": "hvac-service-"+str(n), "rect_mm": [r["aabb"][k] for k in ("minX", "minY")]+[
        r["aabb"]["maxX"]-r["aabb"]["minX"], r["aabb"]["maxY"]-r["aabb"]["minY"]]}
        for n, r in enumerate(balcony["tour_features"]["fixed_reserved_mm"]) if r["kind"] == "hvac-service"]
    settings = cfg["c"]["balcony"]
    routes = {k: _route(settings[k], 700, 700, areas, obstacles+hvac, 115) for k in ("route_mm", "rack_route_mm")}
    equipment_hvac_hits = [i["id"]+":"+r["id"] for i in obstacles for r in hvac if _hits(i["rect_mm"], r["rect_mm"])]
    ops = [settings["sink_operation_mm"], settings["rack_loading_mm"]]
    operation_failures = [str(n)+":"+r["id"] for n, operation in enumerate(ops) for r in obstacles+hvac if _hits(operation, r["rect_mm"])]
    operation_failures += [str(n)+":outside-balcony" for n, operation in enumerate(ops) if not _inside(operation, areas, 115)]
    elder_obstacles = [{"id": i["id"], "rect_mm": interior._body(elder, i)} for i in elder["furniture"] if i["shape"] != "wall-tv"]
    care = _route([[2900, 14265], [2900, 16600], [2400, 16600]], 700, 700, [interior._rect(elder)], elder_obstacles, 115)
    basket_op = cfg["c"]["linen_basket"]["operation_mm"]
    basket_hits = [o["id"] for o in elder_obstacles if not o["id"].endswith(":linen-basket") and _hits(basket_op, o["rect_mm"])]
    if any(r["coordinate_failures"] for r in routes.values()) or care["coordinate_failures"] or equipment_hvac_hits or operation_failures or basket_hits:
        raise ContractError("C workflow conflicts with body, elder route, original rack or HVAC service envelopes: "+json.dumps({
            "routes": {k: r["coordinate_failures"] for k, r in routes.items()}, "care": care["coordinate_failures"],
            "equipment": equipment_hvac_hits, "operations": operation_failures, "basket": basket_hits}))
    return {"balcony_local_700mm_routes": routes, "equipment_hvac_hits": equipment_hvac_hits,
        "operation_failures": operation_failures, "elder_local_700mm_body_route": care,
        "scope": "local-orthogonal-body-only-not-whole-stair-door-wheelchair-or-simultaneous-use-approval"}


def build_study(root: Path = ROOT) -> dict:
    cfg = read_json(root / SOURCE)
    validate_config(cfg)
    references = {key: _verified_report(root, cfg["sources"][key]) for key in ("interior_report", "b_report")}
    source_models = {key: interior.read_model(root / cfg["sources"][key]) for key in ("interior_model", "b_model")}
    interior_options = source_models["interior_model"]["bc_options"]["options"]
    b_options = source_models["b_model"]["b32_rear_right"]["options"]
    options = []
    specs = [("a-current", "A", "A｜保留現況與三樓後窗公衛", "a-upper-wet-core"),
             ("a-ensuite", "A", "A｜獨立套衛取捨比較（待選擇）", "a-upper-wet-core"),
             ("b-rear-refined", "B", "B｜後巷優先＋上層牆邊預留改善", "rear-alley"),
             ("b-front-refined", "B", "B｜無後巷前門備案＋上層改善", "front-backup"),
             ("c-care-refined", "C", "C｜已接受廚房＋單機家務深化", "c-care-laundry")]
    for oid, bid, label, base_id in specs:
        source = next(o for o in (b_options if bid == "B" else interior_options) if o["id"] == base_id)
        source_states = source["states"] if bid == "B" else [{"id": "daily", "label": "討論配置", "model": source["model"]}]
        states = []
        for base_state in source_states:
            model = copy.deepcopy(base_state["model"])
            source_report = references["b_report" if bid == "B" else "interior_report"]
            option_report = next(o for o in source_report["options"] if o["id"] == base_id)
            expected = next(s for s in option_report["states"] if s["id"] == base_state["id"])["plans"] if bid == "B" else option_report["plans"]
            actual = plan_data(model)["buildings"][0]
            for f, reference in zip(actual["floors"], expected["floors"], strict=True):
                f["plan_file"] = reference["plan_file"]
            if stable_hash(actual) != stable_hash(expected):
                raise ContractError("Base 3D/plan report no longer matches: "+base_id+" / "+base_state["id"])
            baseline = copy.deepcopy(model["buildings"][0])
            notes = ["目前討論基準，不是ABC主案或已採用配置；原需求、停車及專業條件未自動通過。"]
            if bid == "B":
                detail = b_refinement(model, cfg)
                notes += [n for n in base_state["model"]["bc_option"]["tradeoffs"] if not n.startswith("本輪只深化一樓")]
                notes += [cfg["b"]["note"], "本輪調整二、三樓家具，保留一樓神桌與門窗。神桌背側35mm缺口、IDF、KTV、停車與RF設備整合仍未解。"]
            elif oid == "a-ensuite":
                detail = a_ensuite(model, cfg)
                notes += [cfg["a"]["tradeoff"]]
            elif bid == "C":
                detail = c_workflow(model, cfg)
                notes += cfg["c"]["workflow"]+["基礎模型沿用3.6m樓高比較快照，不表示屋主已接受樓高、整套C配置或其他用途取捨；樓梯步階／淨高與結構仍未核。"]
            else:
                detail = {"original_ensuite": "unaccommodated", "third_floor_rear_window": "retained-owner-preference"}
                notes += ["保留原公衛／分散收納；原獨立主臥套衛仍未容納，另列取捨案，不改名充數。"]
            _finish(model, bid, oid, label, notes, base_state["id"])
            if bid == "B":
                # Upper-floor work must also preserve the original first-floor
                # reserve ordering and overlays, not just its room rectangles.
                model["buildings"][0]["floors"][0] = copy.deepcopy(baseline["floors"][0])
            screen = interior._screen(model, cfg["insets_mm"], baseline)
            if bid == "B" and (screen["operation_vs_fixed_body"] or any(not r["room"].startswith("B:floor-1:") for r in screen["furniture_body_sensitivity"])):
                raise ContractError("B upper-floor refinement still has body/operation conflicts")
            if oid == "a-ensuite":
                changed = {"A:floor-2:"+k for k in ("master", "master-front", "ensuite-study", "study")}
                if any(r["room"] in changed for r in screen["furniture_body_sensitivity"]+screen["operation_vs_fixed_body"]):
                    raise ContractError("A suite comparison has new full-size body/operation conflicts")
            if bid == "C":
                detail.update(_local_c_review(model, cfg))
            plans = plan_data(model)["buildings"][0]
            if bid == "B":
                raw = next(o for o in read_json(root / "inputs/b32-rear-right-study.json")["options"] if o["id"] == base_id)
                transport = review_state(plans, read_json(root / "inputs/b32-rear-right-study.json"), raw, base_state["id"])
                detail.update(transport=transport, cultural=cultural_screen(plans))
            for f in plans["floors"]:
                f["plan_file"] = oid+"_"+base_state["id"]+"_"+f["id"]+".svg"
            review = {**screen, "detail": detail}
            model["bc_option"]["geometry_review"] = review
            states.append({"id": base_state["id"], "label": base_state["label"], "model": model, "plans": plans, "review": review})
        options.append({"id": oid, "label": label, "building": bid, "status": STATUS, "adopted": False,
            "source_option": base_id, "states": states, "engineering": engineering_review(states[0]["plans"], cfg),
            "owner_choice": "pending-suite-and-storage-tradeoff" if oid == "a-ensuite" else "direction-only-not-whole-layout-adoption"})
    req_sha = sha256_file(root / "inputs/requirements.json")
    ledger = requirement_ledger(options, read_json(root / "inputs/requirements.json"), read_json(root / "inputs/requirement-dispositions.json"), req_sha)
    paths = [SOURCE, "scripts/export_current_design_basis.py", "house_design/current_design_basis.py", BOOTSTRAP, CAMERA,
        "scripts/check_current_design_playwright.cjs", "inputs/requirement-dispositions.json", "inputs/requirements.json",
        "inputs/b32-rear-right-study.json", *cfg["sources"].values()]
    for report in references.values():
        paths += list(report["source_hashes"])
    study = {"schema": SCHEMA, "revision": 1, "display_revision": 2, "generated_at": utc_now(), "status": STATUS, "adopted": False,
        "default_option": cfg["default_option"], "default_state": "daily", "frame_mm": [6000, 17630],
        "professional_status": cfg["professional_status"], "options": options, "requirement_ledger": ledger,
        "basis_source_reports": {k: v["report_hash"] for k, v in references.items()},
        "source_hashes": {p: sha256_file(root / p) for p in sorted(set(paths))},
        "rendered_qa": "not-run", "browser_path": "Browser plugin not available; owner-run Windows Playwright only"}
    study["report_hash"] = stable_hash({k: v for k, v in study.items() if k != "generated_at"})
    return study


def _engineering_svg(option: dict) -> str:
    ns = "http://www.w3.org/2000/svg"
    svg = ET.Element("{"+ns+"}svg", {"viewBox": "-300 -1800 19200 20430", "width": "880", "height": "936", "role": "img"})
    ET.SubElement(svg, "{"+ns+"}title").text = option["label"]+"：上下層濕區／保護區投影，非管路施工圖"
    for n, floor in enumerate(option["states"][0]["plans"]["floors"][:3]):
        offset = n*6300
        ET.SubElement(svg, "{"+ns+"}text", {"x": str(offset), "y": "-400", "font-size": "270"}).text = floor["id"]+"／同源投影"
        for room in floor["rooms"]:
            x, y, w, d = rect(room)
            color = "#bfdbfe" if room["kind"] in {"bath", "kitchen"} else "#fde68a" if sleeping_room(room) or room["key"] in {"shrine", "shrine-front"} else "#f1f5f9"
            ET.SubElement(svg, "{"+ns+"}rect", {"x": str(x+offset), "y": str(y), "width": str(w), "height": str(d), "fill": color, "stroke": "#64748b", "stroke-width": "14"})
        if n < 2:
            for room in option["states"][0]["plans"]["floors"][n+1]["rooms"]:
                if room["kind"] in {"bath", "kitchen"}:
                    x, y, w, d = rect(room)
                    ET.SubElement(svg, "{"+ns+"}rect", {"x": str(x+offset), "y": str(y), "width": str(w), "height": str(d), "fill": "none", "stroke": "#b91c1c", "stroke-width": "35", "stroke-dasharray": "120 70"})
    ET.SubElement(svg, "{"+ns+"}text", {"x": "0", "y": "-1100", "font-size": "250"}).text = "藍：本層濕區；黃：臥室／神明堂；紅虛線：上一層濕區。立管、梁、坡度及完成面高度未知。"
    return ET.tostring(svg, encoding="unicode")


def _section_svg(option: dict) -> str:
    """System relationships only: no fictitious shaft coordinates or slopes."""
    ns = "http://www.w3.org/2000/svg"
    svg = ET.Element("{"+ns+"}svg", {"viewBox": "0 0 1050 880", "width": "900", "height": "754", "role": "img"})
    def text(x, y, value, size=17):
        ET.SubElement(svg, "{"+ns+"}text", {"x": str(x), "y": str(y), "font-size": str(size), "fill": "#24382e"}).text = value
    ET.SubElement(svg, "{"+ns+"}title").text = option["label"]+"：管線／維修關係剖面示意，非按比例或施工路徑"
    text(25, 35, option["label"], 21)
    text(25, 70, "關係剖面：不按比例。虛線不是管線路徑；梁、管道間位置、管徑、坡度與淨高未設計。")
    floors = option["states"][0]["plans"]["floors"]
    for n, floor in enumerate(reversed(floors)):
        y = 170+n*150
        ET.SubElement(svg, "{"+ns+"}line", {"x1": "30", "x2": "1000", "y1": str(y+65), "y2": str(y+65), "stroke": "#94a3b8", "stroke-width": "4"})
        text(35, y, floor["id"]+" · 來源概念樓高 "+str(floor["height_mm"])+"mm（未核）")
        names = [r["name"].split("（")[0][:16] for r in floor["rooms"] if r["kind"] in {"bath", "kitchen"}]
        text(35, y+33, "／".join(names[:3]) if names else "設備／乾式區：實際用途與合法範圍待核", 15)
        text(540, y+15, "公共／維修側檢修面待配置", 15)
    for x, color, label in ((810, "#0284c7", "排水／通氣"), (950, "#b45309", "排氣／補氣")):
        ET.SubElement(svg, "{"+ns+"}line", {"x1": str(x), "x2": str(x), "y1": "120", "y2": "750", "stroke": color, "stroke-width": "3", "stroke-dasharray": "9 7"})
        text(x-80, 105, label+"關係", 15)
    text(35, 790, "排水：合法接點／清潔口未知；不得憑此假設可穿梁、長橫管、降低天花或跨基地排水。", 16)
    text(35, 822, "排氣：各濕區獨立核排風與補氣，合法出口、防火、逆止、噪音及避免回吸均未核。", 16)
    text(35, 854, "泵浦／冷氣：基座隔振、原廠淨空、維修／換機與漏水斷電另核；非設備安裝核定。", 16)
    return ET.tostring(svg, encoding="unicode")


def render_index(study: dict) -> str:
    esc = html.escape
    sections = []
    for option, scenario in zip(study["options"], study["requirement_ledger"]["scenarios"], strict=True):
        states = []
        for state in option["states"]:
            link = f'current-design-basis-3d.html?scheme={option["id"]}&use={state["id"]}'
            figures = []
            for floor in state["plans"]["floors"]:
                src = "current-design-basis/"+floor["plan_file"]
                figures.append(f'<figure><figcaption>{esc(floor["label"])} · <a href="{src}">另開平面SVG</a></figcaption><div class="plan"><object type="image/svg+xml" data="{src}"><a href="{src}">開啟SVG</a></object></div></figure>')
            opened = " open" if option["id"] == study["default_option"] and state["id"] == "daily" else ""
            states.append(f'<details id="{option["id"]}-{state["id"]}" data-use-state="{state["id"]}"{opened}><summary>{esc(state["label"])}</summary><p><a href="{link}">此狀態同源3D</a>；狀態面積不可加總，仍未採用。</p>'+"".join(figures)+"</details>")
        rows = []
        for row in scenario["rows"]:
            area = row["area"]
            last = area["sensitivity"][-1]["area_sqm"] if area["sensitivity"] else "—"
            minimum, target = ("—" if area[k] is None else area[k] for k in ("minimum_sqm", "target_sqm"))
            door_notes = "".join(f'<p>門洞名義{d["nominal_mm"]}mm，115mm扣除假設下{d["clear_assumption_at_115mm"]}mm；原需求{d["original_required_clear_mm"]}mm，差{d["shortfall_at_115mm"]}mm。實際門組／完成面仍未知。</p>' for d in row["door_budget_checks"] if d["shortfall_at_115mm"])
            rows.append(f'<tr data-requirement="{row["requirement_id"]}"><th>{esc(row["title"])}</th><td>{esc(row["allocation_label"])}</td><td>{last}／{minimum}／{target}</td><td>{esc(row["note"])}{door_notes}</td></tr>')
        engineering = option["engineering"]
        conditions = "".join(f'<li>{esc(engineering[k])}</li>' for k in ("ventilation", "air_conditioning", "maintenance", "rear_window_fallback"))
        overlaps = "".join(f'<li>{esc(r["wet_room"])} → {esc(r["below_room"])}；下層床體交疊 {len(r["below_bed_body_hits"])} 件，仍待管線／防水／家規核對。</li>' for r in engineering["wet_over_sensitive_rooms"])
        overlaps += "".join(f'<li>設備 {esc(r["equipment"])} → {esc(r["below_room"])}；承重、漏水與結構傳音未核，不以避開床體保證安靜。</li>' for r in engineering["equipment_over_sensitive_rooms"])
        pump = engineering["b_pump_alternative"]
        pump_text = f'<p>{esc(pump["note"])} 位置：{pump["rect_mm"]} mm；只在工程比較中保留，未放成已安裝設備。</p>' if pump else ""
        remaining = option["states"][0]["review"]["furniture_body_sensitivity"]
        remaining_list = "".join('<li>'+esc(r["issue"])+"；內縮假設 "+esc(str(r["inset_mm"]))+"mm</li>" for r in remaining)
        sections.append(f'<section id="{option["id"]}" data-option="{option["id"]}"><h2>{esc(option["label"])}</h2><p class="warning">討論基準／未採用，專業未核。屋主接受的局部取捨不代表整棟定案。</p><ul>'+"".join('<li>'+esc(n)+'</li>' for n in option["states"][0]["model"]["bc_option"]["tradeoffs"])+f'</ul><p>目前仍有 {len(remaining)} 筆家具牆邊敏感度提示（同件家具可能重複列入不同假設，不代表這麼多件家具實際越界），不宣稱整棟已完成。</p><details><summary>保留的完成面／家具待核提示</summary><ul>{remaining_list}</ul></details>'+"".join(states)+
            f'<details><summary>上下層濕區／設備整合（不是管線施工圖）</summary><a href="current-design-basis/{option["id"]}_coordination.svg">同源投影SVG</a> · <a href="current-design-basis/{option["id"]}_section.svg">管線／檢修關係剖面SVG</a><ul>{overlaps}</ul><ul>{conditions}</ul>{pump_text}</details>'+
            '<details><summary>完整原需求對帳／未容納與取捨</summary><div class="table"><table><caption>115mm內縮討論值／原下限／原目標，m²；不給共用區獨立面積信用，不能跨列相加。</caption><thead><tr><th>原需求</th><th>配置狀態</th><th>面積</th><th>限制</th></tr></thead><tbody>'+"".join(rows)+'</tbody></table></div></details></section>')
    nav = "".join(f'<a href="#{o["id"]}">{esc(o["label"])}</a>' for o in study["options"])
    return (
        '<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ABC目前討論基準｜整棟使用與工程整合</title><style>body{font:16px/1.7 system-ui,sans-serif;max-width:1180px;margin:auto;padding:20px;color:#24382e;background:#f8faf8}a{color:#17634d}nav{display:flex;flex-wrap:wrap;gap:12px}.warning{background:#fff1d6;padding:12px;color:#65430b}summary,a,button{min-height:44px}summary{cursor:pointer;padding:12px 0}section{border-top:1px solid #cbd5ce;margin-top:30px}.plan{max-height:660px;overflow:auto;border:1px solid #cbd5ce}.plan object{width:660px;max-width:none;display:block}figure{margin:15px 0}.table{overflow:auto}table{border-collapse:collapse;width:100%;min-width:700px}td,th{border:1px solid #cbd5ce;padding:8px;text-align:left;vertical-align:top}caption{text-align:left}@media(max-width:640px){body{padding:12px}.plan{max-height:500px}}</style>'
        '<body><h1>ABC目前討論基準</h1>'
        '<p id="basis-adoption-warning" class="warning" role="note">比較方案，未採用／專業未核。'
        '五個獨立比較：A原配置／套衛取捨、B後巷優先／前門備案、C單機家務深化。'
        '32地坪不是每層合法可建面積。原ABC、歷史方案、原需求與封存均保留。</p>'
        '<p>選擇方向 → 同源HTML／3D → 原需求缺口 → 建築師／機電／家族核對。畫面驗收與專業核可分開，新版尚未瀏覽器／目視驗收。</p><nav>'
        +nav+'</nav><p><a href="current-design-basis-3d.html">開啟同源3D（預設B後巷版）</a> · <a href="model3d.html">歷史ABC主案</a> · <a href="b32-rear-right.html">上輪B一樓兩版</a> · <a href="current-design-basis/requirement-ledger.json">最新完整需求對帳JSON</a></p>'
        +"".join(sections)+"</body></html>"
    )


def write_study(study: dict, root: Path = ROOT) -> dict:
    directory = root / OUT
    directory.mkdir(parents=True, exist_ok=True)
    report = copy.deepcopy(study)
    for option in report["options"]:
        for state in option["states"]:
            state.pop("model")
    write_json(directory / "review.json", report)
    write_json(directory / "requirement-ledger.json", study["requirement_ledger"])
    for option in study["options"]:
        (directory / (option["id"]+"_coordination.svg")).write_text(_engineering_svg(option), encoding="utf-8")
        (directory / (option["id"]+"_section.svg")).write_text(_section_svg(option), encoding="utf-8")
        for state in option["states"]:
            url = f'../current-design-basis-3d.html?scheme={option["id"]}&use={state["id"]}'
            for floor in state["plans"]["floors"]:
                svg = ET.fromstring(render_plan(option["building"], floor, viewer_url=url))
                svg.set("width", "660")
                svg.set("height", "1903")
                svg.set("data-basis-option", option["id"])
                svg.set("data-use-state", state["id"])
                for room in floor["rooms"]:
                    for route in room["features"].get("basis_routes", []):
                        ET.SubElement(svg, "{http://www.w3.org/2000/svg}polyline", {"points": " ".join(f"{x},{y}" for x, y in route["points_mm"]), "fill": "none", "stroke": "#137d9c", "stroke-width": "26", "stroke-dasharray": "90 60", "data-basis-route": route["kind"]})
                (directory / floor["plan_file"]).write_text(ET.tostring(svg, encoding="unicode"), encoding="utf-8")
    (root / INDEX).write_text(render_index(study), encoding="utf-8")
    # Reuse the validated local B32 compact-display layer; shared templates and
    # the old B viewer are not modified. Only our generated page is patched.
    controls = (root / "scripts/templates/bc-options-controls.html").read_text().replace("bc-options.html", "current-design-basis.html").replace("B 家規／C 照護", "ABC目前討論基準")
    controls = controls.replace('<div class="bc-study-links">', '<label for="study-use">使用狀態<select id="study-use"></select></label><label for="b32-label-mode">模型標籤<select id="b32-label-mode"><option value="compact">重點（預設）</option><option value="all">全部標籤</option></select></label><div class="bc-study-links">')
    controls += '<style>#study-use,#b32-label-mode{width:100%;min-height:44px;background:#132238;color:#eef6ff}#b32-room-details-panel{padding:10px;border:1px solid #739ca6}</style>'
    payload = {"current_design_basis": {"display_revision": study["display_revision"], "default_option": study["default_option"], "default_state": "daily", "options": [
        {k: o[k] for k in ("id", "label", "building", "states")} for o in study["options"]]}}
    for o in payload["current_design_basis"]["options"]:
        o["states"] = [{k: s[k] for k in ("id", "label", "model")} for s in o["states"]]
    text = viewer.render_html(payload, viewer.three_source()[0], study_controls=controls, study_bootstrap=(root / BOOTSTRAP).read_text())

    def patch(old: str, new: str) -> None:
        nonlocal text
        if text.count(old) != 1:
            raise ContractError("Current viewer anchor changed; do not silently omit compact display: "+old[:70])
        text = text.replace(old, new)

    display = (root / "scripts/templates/b32-rear-right-display.js").read_text()
    display = display.replace('["stair1","shrine","storage","rear-bath"]', '["stair1","shrine","storage","rear-bath","flex1","elder","public-bath","stair1f"]')
    display = display.replace('["garage","stair1","shrine","storage","rear-bath","laundry-base"]', '["garage","stair1","shrine","storage","rear-bath","laundry-base","flex1","elder","public-bath","stair1f","kitchen"]')
    patch('    var hvac=features.hvac || {};', display_overlay()+ '\n    var hvac=features.hvac || {};')
    patch('  var furnitureLabelRects=[];', display+'\n  var furnitureLabelRects=[];')
    patch('var enabled = document.getElementById("furniture-names").checked && !!viewState.room;',
        'var enabled = document.getElementById("furniture-names").checked && !!viewState.room && b32DisplayContext().mode==="all";')
    patch('cell.name+(features.access_pending?" · 入口待定":"")', 'b32RoomText(cell,features)')
    patch('    var occupied=furnitureLabelRects.slice(), area=overlayLabelArea();', '    var occupied=furnitureLabelRects.slice(), area=overlayLabelArea(),b32Context=b32DisplayContext(),b32Shown=0;')
    patch('      var point=mesh.parent.localToWorld(entry.point.clone());', '      if(!b32LabelPolicy(entry,b32Context)||b32Shown>=b32LabelLimit(b32Context)){show=false;}\n      entry.label.textContent=entry.kind==="room"&&b32Context.mode==="compact"?b32ShortRoomText(mesh.userData.cell):entry.label.dataset.basisFullText;\n      var point=mesh.parent.localToWorld(entry.point.clone());')
    patch('      occupied.push(placed);\n      entry.label.style.left=placed.x+"px";', '      occupied.push(placed);b32Shown++;\n      entry.label.style.left=placed.x+"px";')
    patch('    label.textContent = text;\n    label.title = "示意定位，未經現勘或建築師核定";',
        '    label.textContent = text;label.dataset.basisFullText=text;\n    if(kind==="room"){label.setAttribute("aria-label",text);}\n    label.title = text+"；示意定位，未經現勘或建築師核定";')
    patch('    actions.hidden = presentation !== "tour" || !viewState.room;', '    actions.hidden = presentation !== "tour" || !viewState.room;\n    b32SyncRoomReadout();')
    patch('      <p id="room-cutaway-status" role="status" hidden></p>', '      <button type="button" class="room-view-button" id="b32-room-details">設備清單</button>\n      <p id="room-cutaway-status" role="status" hidden></p>')
    patch('    <div id="furniture-list" aria-label="本房家具清單"></div>', '<section id="b32-room-details-panel"><button type="button" id="b32-details-back">返回模型</button><p id="b32-room-entry-status" role="status" hidden></p><div id="furniture-list" aria-label="本房家具清單"></div></section>')
    patch('      geomSource: geomSource,', '      b32Display:b32DisplayEvidence(),\n      geomSource: geomSource,')
    patch('      control.disabled=active || (id==="room-cutaway" && presentation!=="tour") ||',
        '      control.disabled=active || (id==="furniture-names" && document.getElementById("b32-label-mode").value!=="all") || (id==="room-cutaway" && presentation!=="tour") ||')
    patch('      if(features.access_pending){row("入口待配置", "原格位未提供合適的公共入口相鄰空間，不以浴廁、臥室、弱電間或武轎室充當穿越通道。須補走道／正式門位；不能據本圖確認可進出。");}',
        '      if(features.access_pending){row("入口資料／通行未核",escapeHtml(b32EntryDescription(cell,features))+"；門組、完成面、救援與公共通行未核。");}')
    # Opt in here, not in the shared renderer: historical viewers and the
    # source-bound base studies must remain byte-for-byte unchanged.
    patch('  var cameraFitState=null;', (root / CAMERA).read_text()+'\n  var cameraFitState=null;')
    patch('    // Opt in only for the unadopted C integration. Keep every room visible,\n'
          '    // fit its real bounds and score real furniture bodies, never their labels.',
          '    // Current discussion mobile closeup only; retain the entire floor.\n'
          '    // Score every real product body, not labels or self-reported focus flags.')
    patch('DATA.source && DATA.source.c_integrated_review){', 'DATA.source && DATA.source.current_design_basis){')
    patch('return {id:e.item.id,primary:["bed","treadmill","toilet","vanity"].indexOf(e.item.shape)>=0,box:new THREE.Box3().setFromObject(e.group)};',
          'return {id:e.item.id,budget:basisBodyPixelBudget(e.item),box:new THREE.Box3().setFromObject(e.group)};')
    patch('readable=chooseReadableRoomFrame(box,area,width,height,camera.fov,bodies,frame);frame=readable.frame;',
          'readable=basisChooseRoomFrame(box,area,width,height,camera.fov,bodies,frame);frame=readable.frame;')
    patch('closeupPolicy:readable?"c-integrated-readable-v1":null,',
          'viewport:{width:width,height:height},closeupPolicy:readable?"current-design-readable-v2":null,')
    patch('    window.setTimeout(resize, 220);', '    basisScheduleResize();')
    patch('  window.addEventListener("resize", resize);', '  window.addEventListener("resize", basisScheduleResize);\n  basisObserveViewport();')
    patch('      geomSource: geomSource,', '      currentDesignCamera:basisCameraEvidence(),\n      geomSource: geomSource,')
    patch('    renderer.render(scene, camera);', '    basisRenderFrame();')
    text = text.replace('htmlHref="bc-options.html#"', 'htmlHref="current-design-basis.html#"')
    (root / VIEWER).write_text(text, encoding="utf-8")
    return {"index": INDEX, "viewer": VIEWER, "report": OUT+"/review.json", "options": len(study["options"]),
        "states": sum(len(o["states"]) for o in study["options"]), "requirement_rows": study["requirement_ledger"]["scenario_rows"]}


def display_overlay() -> str:
    return '''    (features.reserved_mm||[]).filter(function(r){return r.kind.indexOf("basis-")===0||r.kind.indexOf("b-separate-")===0;}).forEach(function(r){
      var b=r.aabb,p=[[b.minX,b.minY],[b.maxX,b.minY],[b.maxX,b.maxY],[b.minX,b.maxY],[b.minX,b.minY]].map(function(p){return new THREE.Vector3(p[0]*MM,base+.04,wz(p[1]));});
      var l=new THREE.Line(new THREE.BufferGeometry().setFromPoints(p),new THREE.LineDashedMaterial({color:0xb45309,dashSize:.08,gapSize:.04,clippingPlanes:[clipPlane]}));l.userData.cameraFit=false;l.computeLineDistances();group.add(l);
    });
    (features.basis_routes||features.b32_route_overlays||[]).forEach(function(r){
      var p=r.points_mm.map(function(p){return new THREE.Vector3(p[0]*MM,base+.07,wz(p[1]));});
      var l=new THREE.Line(new THREE.BufferGeometry().setFromPoints(p),new THREE.LineDashedMaterial({color:0x137d9c,dashSize:.1,gapSize:.06,clippingPlanes:[clipPlane]}));l.userData.cameraFit=false;l.computeLineDistances();group.add(l);
    });'''


def main() -> None:
    study = build_study()
    paths = write_study(study)
    print(json.dumps({**paths, "rendered_qa": "not-run", "report_hash": study["report_hash"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

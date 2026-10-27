#!/usr/bin/env python3
"""Patch public model snapshots, then serialize same-source HTML/SVG/3D.

No packing solver, full model build, browser, WebGL, network or archive writes.
Each option remains an unadopted comparison, with original unmet goals intact.
"""
from __future__ import annotations

import copy
import html
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import export_model_3d as viewer
from lib.model3d_openings import review_window
from lib.model3d_placement import _candidate, _door_approach, _operation
from lib.model3d_plan import plan_data, render_plan
from lib.model3d_review import attach_hvac_proposals, proposal_features

from house_design.b32_daily_use import review_daily_use
from house_design.b32_service_detail import _circle_hits, _inside, _route
from house_design.b32_services import _covered, _hits, build_service_study
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, utc_now, write_json
from house_design.requirement_reconciliation import _public_path, build_reconciliation, discussion_area

SOURCE = "inputs/interior-improvements.json"
STATUS = "comparison-only-not-adopted"
REVISION = 7
OUT = "structured/candidates/interior-improvements"
DOOR_ENVELOPES = "scripts/templates/interior-improvements-door-envelopes.js"
KEYS = ("x_mm", "y_mm", "w_mm", "h_mm")
CONFIRMED_CHOICES = {
    "c-washer": "one-washer-retain-2f-no-1f-addition",
    "a-bath-move": "exterior-window-priority-retain-rear-bath",
    "c-kitchen": "front-fridge-450mm-public-area-tradeoff-for-integration",
}
PENDING_DECISIONS = {"b-left-access", "b-table-benches", "b-storage", "c-base"}
C_TRADEOFF_STATUS = "owner-confirmed-for-integration-professional-unknown"
C_LAYOUT_KEYS = ("kitchen_rect_mm", "living_rect_mm", "products", "living_products", "kitchen_entry_nominal_mm",
                 "kitchen_entry_center_y_mm", "fridge_clearance_assumptions_mm")


def _validate_owner_choices(cfg: dict) -> None:
    decisions = cfg["owner_decisions"]
    if (len(decisions) != 7 or {d["id"] for d in decisions} != PENDING_DECISIONS | CONFIRMED_CHOICES.keys()
            or any(d["status"] != "pending" for d in decisions if d["id"] in PENDING_DECISIONS)
            or any(d["status"] != "confirmed-preference" or d.get("choice") != CONFIRMED_CHOICES[d["id"]]
                   or not d.get("source") for d in decisions if d["id"] in CONFIRMED_CHOICES)
            or cfg["a"].get("bath_strategy") != "retain-original-rear-window"
            or cfg["a"].get("wet_stack_priority") != "exterior-window-before-exact-stacking"
            or cfg["c"].get("washer_count") != 1 or cfg["c"].get("washer_floor") != "floor-2"):
        raise ContractError("Preserve confirmed owner preferences without adopting unresolved layouts or approvals")
    accepted = next(d for d in decisions if d["id"] == "c-kitchen").get("accepted_scope", {})
    if (accepted.get("front_partition_shift_mm") != 450 or accepted.get("nominal_public_loss_sqm") != 1.08
            or accepted.get("whole_c_layout_adopted") is not False or accepted.get("professional_approval") != "unknown"
            or not isinstance(accepted.get("basis_report_hash"), str) or len(accepted["basis_report_hash"]) != 64
            or any(ch not in "0123456789abcdef" for ch in accepted["basis_report_hash"])
            or accepted.get("layout_sha256") != stable_hash({k: cfg["c"][k] for k in C_LAYOUT_KEYS})):
        raise ContractError("Confirmed C kitchen scope changed; retain the accepted layout and unresolved approvals")


def read_model(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    marker = "  var DATA = "
    if text.count(marker) != 1:
        raise ContractError("Expected one strict JSON DATA assignment; never execute a viewer")
    raw = text.split(marker, 1)[1]
    value, end = json.JSONDecoder().raw_decode(raw)
    if not raw[end:].startswith(";") or not isinstance(value, dict):
        raise ContractError("Invalid model assignment")
    return value


def _select(source: dict, option_id: str, bid: str) -> dict:
    choices = [o for o in source.get("bc_options", {}).get("options", []) if o.get("id") == option_id]
    if len(choices) != 1 or choices[0].get("building") != bid or choices[0]["model"].get("schema") != "house-model3d-v1":
        raise ContractError("Missing, ambiguous or wrong-building base model: "+option_id)
    return choices[0]["model"]


def _rooms(floor: dict) -> dict:
    return {c["key"]: c for c in floor["cells"] if c.get("tour_active")}


def _rect(cell: dict) -> list:
    return [cell["tour_mm"][k] for k in KEYS]


def _bounds(rect: list) -> dict:
    x, y, w, d = rect
    return {"minX": x, "maxX": x+w, "minY": y, "maxY": y+d}


def _body(cell: dict, item: dict) -> list:
    b = cell["furniture_placements"]["tour_mm"][item["id"]]["aabb"]
    return [b["minX"], b["minY"], b["maxX"]-b["minX"], b["maxY"]-b["minY"]]


def _room(floor: dict, key: str, rect: list, *, template: dict | None = None, **spec) -> dict:
    cells = _rooms(floor)
    if key in cells:
        cell = cells[key]
    else:
        cell = copy.deepcopy(template or next(iter(cells.values())))
        cell.update(key=key, id=cell["id"].rsplit(":", 1)[0]+":"+key, proposal_only=True, furniture=[])
        cell["furniture_placements"] = {"tour_mm": {}, "auto_mm": {}, "declared_mm": {}}
        floor["cells"].append(cell)
    cell["tour_mm"] = dict(zip(KEYS, rect, strict=True))
    cell.update(tour_active=True, name=spec.get("name", cell["name"]), kind=spec.get("kind", cell["kind"]))
    cell["review_spec"] = {**cell["review_spec"], **spec, "rect": rect}
    cell["space_group"], cell["space_role"] = spec.get("group", ""), spec.get("role", "")
    cell["is_outdoor"] = spec.get("outdoor", cell["is_outdoor"])
    cell["window_mm"] = spec.get("window_mm", cell["window_mm"])
    cell["size_text"] = "本輪概念比較，非實測／原HTML尺寸"
    floor["layout_review"]["rooms"][key] = copy.deepcopy(cell["review_spec"])
    return cell


def _place(cell: dict, item: dict, rect: list, rotation: int, anchor: str, *, local: str | None = None,
           freestanding_operation: bool = False) -> None:
    item = copy.deepcopy(item)
    expected = [item["width_mm"], item["depth_mm"]]
    if rotation % 180:
        expected.reverse()
    if expected != rect[2:]:
        raise ContractError("May not scale a product to fit: "+item["id"])
    if local:
        item["id"] = cell["id"]+":furniture:"+local
    item.update(rotation_deg=rotation, wall_anchor=anchor, wall_locked=bool(anchor))
    item["note"] = item.get("note", "")+" 本輪獨立比較；原尺寸不縮，操作與專業條件另列。"
    cell["furniture"].append(item)
    placement = _candidate(item, rect[0]+rect[2]/2, rect[1]+rect[3]/2, rotation, anchor)
    if freestanding_operation and not anchor and item["front_clearance_mm"]:
        # Freestanding seating still needs its original approach band. The
        # absence of a wall anchor must not silently erase that floor space.
        # This is explicit: parked B benches must not acquire usable-seat credit.
        placement["operation_mm"] = _operation(placement["aabb"], {0: "rear", 90: "right", 180: "front", 270: "left"}[rotation], item["front_clearance_mm"])
    placement["basis"] = "coordinate-proposal-not-rehearsed"
    cell["furniture_placements"]["tour_mm"][item["id"]] = placement


def _empty(cell: dict) -> None:
    cell["furniture"] = []
    cell["furniture_placements"]["tour_mm"] = {}


def _rebuild(floor: dict) -> None:
    # Recalculate paired openings only. Preserve real source stair parameters;
    # automatic ceil(height/180) must not silently change a 22-riser comparison.
    stairs = {c["key"]: {k: copy.deepcopy(v) for k, v in c["tour_features"].items()
                          if k in {"stair_geometry", "stair_footprint_mm", "shared_landing_mm"}}
              for c in floor["cells"] if c.get("tour_active") and c["kind"] == "stair"}
    for c in floor["cells"]:
        c["tour_features"]["space_group"] = c.get("space_group", "")
        c["tour_features"]["space_role"] = c.get("space_role", "")
        for key in ("entry_access_review", "b32_transport_segments", "carry_path_mm", "transport_review", "transport_segment_mm"):
            c["tour_features"].pop(key, None)
    proposal_features(floor)
    for c in floor["cells"]:
        if not c["window_mm"]:
            c["tour_features"]["window_mm"] = 0
    for key, values in stairs.items():
        _rooms(floor)[key]["tour_features"].update(values)


def _finish(model: dict, bid: str, option_id: str, label: str, notes: list) -> dict:
    model["buildings"] = [b for b in model["buildings"] if b["id"] == bid]
    building = model["buildings"][0]
    for floor in building["floors"]:
        for cell in floor["cells"]:
            f = cell["tour_features"]
            f["hvac_units"] = []
            f["hvac"] = {"indoor": False, "outdoor": False, "evidence": []}
            f["fixed_reserved_mm"] = [r for r in f.get("fixed_reserved_mm", []) if r["kind"] != "hvac-service"]
    routes = attach_hvac_proposals([building])
    for floor in building["floors"]:
        for cell in floor["cells"]:
            f = cell["tour_features"]
            f["reserved_mm"] = list(f.get("fixed_reserved_mm", []))+[
                {"kind": "door-approach", "aabb": _door_approach(cell["tour_mm"], d)} for d in f["doors"]]
            stair = f.get("stair_footprint_mm")
            if stair:
                f["reserved_mm"].append({"kind": "stairs", "aabb": _bounds([stair[k] for k in KEYS])})
    # Old reports concern different geometry; do not present their passed data.
    model["layout_review"] = {"status": STATUS, "checks": [], "hvac_routes": routes}
    building["layout_review"]["summary"] = label
    for floor in building["floors"]:
        floor["layout_review"].pop("space_efficiency", None)
    model["facade"] = {**model.get("facade", {}), "buildings": [], "status": "not-regenerated-interior-comparison-only"}
    model["compare"] = {"available": False}
    model["source"] = {"interior_improvements": SOURCE, "geometry_basis": "public-snapshot-local-patches-not-full-regeneration"}
    model["bc_option"] = {"id": option_id, "label": label, "revision": REVISION, "status": STATUS, "tradeoffs": notes, "geometry_review": {}}
    items = [i for f in building["floors"] for c in f["cells"] if c.get("tour_active") for i in c["furniture"]]
    model["furniture"]["items"] = len(items)
    model["furniture"]["rooms"] = sum(bool(c["furniture"]) for f in building["floors"] for c in f["cells"] if c.get("tour_active"))
    model["furniture"]["basis_counts"] = {k: sum(i["basis"] == k for i in items) for k in model["furniture"]["basis_counts"]}
    model["overlaps"] = {k: [r for r in rows if r.get("building") == bid] for k, rows in model["overlaps"].items()}
    historical = [c for f in building["floors"] for c in f["cells"] if not c.get("proposal_only")]
    counts = {kind: sum(c["provenance"] == kind for c in historical) for kind in ("auto", "declared", "measured")}
    model["provenance"] = {"cells": counts, "total": len(historical),
                           "auto_pct": round(counts["auto"]/len(historical)*100, 1),
                           "note": "僅此棟歷史格位；新室內比較坐標不是實測或專業核定。"}
    return model


def b_proposal(model: dict, cfg: dict, root: Path) -> tuple[dict, dict]:
    first = model["buildings"][0]["floors"][0]
    rooms = _rooms(first)
    original = copy.deepcopy(rooms)
    mode = model["bc_option"]["id"]
    detail = read_json(root / "inputs/b32-service-detail.json")
    case = next(c for c in build_service_study(root)["cases"] if c["id"] == mode+"-compact-service")
    zones = case["zones_mm"]
    # Change only the L-room's data seams so the door fits one left-wall zone.
    # All three rectangles still have exactly the original bathroom union.
    bath_split_y = 13200
    aliases = {"bath1": ([1140, 11370, 1360, bath_split_y-11370], "衛浴上段／洗手台", "bath", "new-B-bath"),
               "bath-extension": ([1140, bath_split_y, 3180, 14930-bath_split_y], "零門檻淋浴／便器轉位", "bath", "new-B-bath"),
               "bath-shoulder": ([2500, 12970, 1820, bath_split_y-12970], "衛浴L形開放接段", "bath", "new-B-bath"),
               "work-reserve": (zones["laundry"][0], "後側家務（外窗／陽台合法性待核）", "service", ""),
               "storage": ([2500, 14930, 3500, 2700], "武轎儲藏／右後本體", "service", "new-B-storage"),
               "storage-front": ([4320, 14330, 1680, 600], "儲藏入口接段（非獨立第二庫）", "service", "new-B-storage"),
               "storage-shoulder": (zones["storage"][2], "儲藏L形接段", "service", "new-B-storage"),
               "housework-passage": (zones["public-housework-passage"][0], "家務／浴室通道（約1m，照護未核）", "other", "")}
    for key, (rect, name, kind, group) in aliases.items():
        _room(first, key, rect, template=original["bath1"] if kind == "bath" else original["work-reserve"],
              name=name, kind=kind, group=group, window_mm=0, outdoor=False, role="circulation" if key == "housework-passage" else "")
        _empty(_rooms(first)[key])
    rooms = _rooms(first)
    for key in ("bath1", "bath-extension", "bath-shoulder"):
        rooms[key]["color"] = "#3fb6c8"
    products = {i["catalog_id"]: i for r in original.values() for i in r["furniture"]}
    for raw in detail["bathroom"]["fixtures"]:
        key = "bath1" if raw["id"] == "basin" else "bath-extension"
        i = copy.deepcopy(products[raw["catalog"]])
        i["step_free"] = raw["id"] == "shower"
        _place(rooms[key], i, raw["rect_mm"], raw["rotation_deg"], "rear" if raw["id"] != "basin" else "front", local=raw["id"])
    _empty(rooms["storage"])
    _place(rooms["storage"], products["ceremonial-storage"], case["palanquin_body_mm"], 0, "", local="ceremonal")
    # Both original benches and table remain full-size, in the explicit daily
    # parked proposal. This is a family decision, not a newly approved custom.
    _empty(rooms["shrine"])
    for i in original["shrine"]["furniture"]:
        local = i["id"].rsplit(":", 1)[-1]
        r = _body(original["shrine"], i)
        if local == "offering":
            r[1] += detail["shrine"]["offering_rear_shift_mm"]
        if local.startswith("bench-"):
            r = next(p["rect_mm"] for p in detail["shrine"]["daily_park_benches"] if p["id"] == local)
        _place(rooms["shrine"], i, r, 0, "rear" if local == "altar" else "")
    catalog = read_json(root / "inputs/furniture-layout.json")["catalog"]
    sample = next(iter(products.values()))
    for raw in detail["laundry"]["items"]:
        product = catalog[raw["catalog"]] if raw["catalog"] else {
            "label": "一般600mm洗槽", "category": "bath", "shape": "vanity", "color": "#94a3b8",
            "width_mm": 600, "depth_mm": 600, "height_mm": 850}
        i = {**copy.deepcopy(sample), **product, "catalog_id": raw["catalog"] or "generic-utility-sink",
             "front_clearance_mm": 800, "rear_clearance_mm": 0, "left_clearance_mm": 0, "right_clearance_mm": 0,
             "mount_height_mm": 0, "shape": product["shape"], "physical_item_id": None}
        _place(rooms["work-reserve"], i, raw["rect_mm"], 0, "rear", local=raw["id"])
    first["layout_review"]["connections"] = [
        c for c in first["layout_review"]["connections"]
        if not any(k in {"bath1", "bath-extension", "work-reserve", "storage"} for k in c[:2])]
    first["layout_review"]["connections"] += [
        ["shrine", "housework-passage", "open"], ["housework-passage", "work-reserve", "open"],
        ["housework-passage", "bath1", {"width_mm": cfg["bath_entry_nominal_mm"], "operation": "sliding",
           "label": "向後壁內拉門比較（產品／救援未核）"}, cfg["bath_entry_center_y_mm"]],
        ["bath1", "bath-extension", "open"], ["bath-shoulder", "bath-extension", "open"], ["corridor1", "storage-front", 1660, 5160],
        ["storage", "storage-front", "open"]]
    door_end = cfg["bath_entry_center_y_mm"]+cfg["bath_entry_nominal_mm"]/2
    if door_end > bath_split_y:
        raise ContractError("Bath door must fit the upper-leg wall; coordinate revision needed")
    rooms["work-reserve"]["window_mm"] = 1200
    rooms["work-reserve"]["review_spec"].update(window_mm=1200, window_face="rear")
    _rebuild(first)
    # This 230mm same-room open seam is deliberately not a navigable doorway.
    # The generic adjacency helper ignores contacts shorter than 600mm, so
    # explicitly remove this otherwise-false internal wall from both surfaces.
    for key, face, other in (("bath1", "right", "bath-shoulder"), ("bath-shoulder", "left", "bath1")):
        g = rooms[key]["tour_mm"]
        rooms[key]["tour_features"]["open_connections"].append({
            "face": face, "width_mm": 230, "ratio": (13085-g["y_mm"])/g["h_mm"],
            "neighbor": rooms[other]["id"], "status": "same-L-bathroom-no-partition", "operation": "open"})
    for key, face, other in (("storage-shoulder", "right", "storage"), ("storage", "left", "storage-shoulder")):
        g = rooms[key]["tour_mm"]
        rooms[key]["tour_features"]["open_connections"].append({
            "face": face, "width_mm": 340, "ratio": (15100-g["y_mm"])/g["h_mm"],
            "neighbor": rooms[other]["id"], "status": "same-L-storage-no-partition", "operation": "open"})
    rooms["bath1"]["tour_features"]["pocket_door_review"] = {**cfg, "status": "product-wall-structure-and-rescue-unknown"}
    cx, cy, r = detail["bathroom"]["turn_circle_mm"]
    rooms["bath-extension"]["tour_features"]["fixed_reserved_mm"].append({
        "kind": "care-turn", "aabb": _bounds([cx-r, cy-r, r*2, r*2]), "status": "step-free-shower-floor-shared-not-rehearsed"})
    return model, {"zones_mm": zones, "area_rows": case["area_rows"], "bath_access": "left-housework-passage",
                   "pocket_door": cfg, "original_targets_retained": True}


def b_right_proposal(model: dict, cfg: dict, root: Path) -> tuple[dict, dict]:
    """Independent right-access study; never overwrite the left-access control."""
    model, prior = b_proposal(model, cfg["b"], root)
    settings = cfg["b_right_access"]
    if settings["status"] != STATUS:
        raise ContractError("B right access is an unadopted comparison, not owner or professional approval")
    first = model["buildings"][0]["floors"][0]
    cells = _rooms(first)
    basin = copy.deepcopy(cells["bath1"]["furniture"][0])
    cabinet = copy.deepcopy(cells["altar-backing"]["furniture"][0])
    _room(first, "dry-access", settings["dry_access_rect_mm"], template=cells["bath1"],
          name="乾櫃前室（原衛浴上段改乾區）", kind="other", group="", role="circulation", window_mm=0, outdoor=False)
    _empty(_rooms(first)["dry-access"])
    first["cells"] = [c for c in first["cells"] if c["key"] not in {"bath1", "bath-shoulder"}]
    for key in ("bath1", "bath-shoulder"):
        first["layout_review"]["rooms"].pop(key)
    bath = _room(first, "bath-extension", settings["bath_rect_mm"],
                 name="右側入口公衛（淋浴／轉位分時）", kind="bath", group="", window_mm=0, outdoor=False)
    bath["tour_features"]["fixed_reserved_mm"] = []
    shower = copy.deepcopy(next(i for i in bath["furniture"] if i["shape"] == "shower"))
    shower_rect = _body(bath, shower)
    bath["furniture"] = [i for i in bath["furniture"] if i["id"] != shower["id"]]
    bath["furniture_placements"]["tour_mm"].pop(shower["id"])
    _place(bath, shower, shower_rect, 270, "left")
    _place(bath, basin, settings["basin_rect_mm"], 0, "front", local="basin")
    _empty(cells["altar-backing"])
    _place(cells["altar-backing"], cabinet, settings["cabinet_rect_mm"], 90, "right", local="cabinet")
    removed = {"bath1", "bath-extension", "bath-shoulder", "altar-backing", "dry-access"}
    first["layout_review"]["connections"] = [c for c in first["layout_review"]["connections"] if not removed.intersection(c[:2])]
    first["layout_review"]["connections"] += [
        ["housework-passage", "dry-access", "open"],
        ["dry-access", "altar-backing", {"width_mm": settings["dry_entry_nominal_mm"],
            "operation": "hinged-inward-proposal", "label": "乾櫃內開門（取物分時／未核）"}, settings["dry_entry_center_y_mm"]],
        ["corridor1", "bath-extension", {"width_mm": settings["bath_entry_nominal_mm"],
            "operation": "sliding", "label": "右側浴室拉門（向前停門／未核）"}, settings["bath_entry_center_y_mm"]],
    ]
    _rebuild(first)
    cells = _rooms(first)
    # Store exact paired centres; generic ratio rounding is presentation precision,
    # not a reason to lose the final fraction of a millimetre at a 900mm opening.
    for a, b, cy in (("corridor1", "bath-extension", settings["bath_entry_center_y_mm"]),
                     ("dry-access", "altar-backing", settings["dry_entry_center_y_mm"])):
        for key, other in ((a, b), (b, a)):
            door = next(d for d in cells[key]["tour_features"]["doors"] if d["neighbor"] == cells[other]["id"])
            expected_width = settings["bath_entry_nominal_mm"] if a == "corridor1" else settings["dry_entry_nominal_mm"]
            if door["width_mm"] != expected_width:
                raise ContractError("B right-access openings may not be silently clipped")
            door["ratio"] = (cy-cells[key]["tour_mm"]["y_mm"])/cells[key]["tour_mm"]["h_mm"]
    for key, face, other in (("storage-shoulder", "right", "storage"), ("storage", "left", "storage-shoulder")):
        g = cells[key]["tour_mm"]
        cells[key]["tour_features"]["open_connections"].append({
            "face": face, "width_mm": 340, "ratio": (15100-g["y_mm"])/g["h_mm"],
            "neighbor": cells[other]["id"], "status": "same-L-storage-no-partition", "operation": "open"})
    cx, cy, radius = settings["turn_circle_mm"]
    bath["tour_features"]["fixed_reserved_mm"].append({"kind": "care-turn",
        "aabb": _bounds([cx-radius, cy-radius, radius*2, radius*2]), "status": "step-free-shower-floor-shared-not-rehearsed"})
    envelopes = _b_right_envelopes(settings, max(cfg["insets_mm"]))
    bath["tour_features"]["fixed_reserved_mm"] += [
        {"kind": "b-right-slider-"+name, "aabb": _bounds(envelopes[name]), "status": "assumed-budget-not-product"}
        for name in ("park", "closed")]
    cells["altar-backing"]["tour_features"]["fixed_reserved_mm"].append({
        "kind": "b-right-dry-door-sweep", "aabb": _bounds(envelopes["dry_swing"]), "status": "bounding-square-not-product-motion"})
    for key in ("dry-access", "altar-backing", "bath-extension", "corridor1"):
        cells[key]["tour_features"].pop("pocket_door_review", None)
        cells[key]["tour_features"]["interior_entry_review"] = {"status": STATUS, "note": settings["note"]}
    bath["tour_features"]["shared_step_free_floor_review"] = {
        "status": "removable-curtain-and-sequential-only-not-approved",
        "note": "洗手操作與轉位借零門檻淋浴地面；無固定玻璃／基座，不同時洗澡與洗手，濕滑、防水、坡度及照護救援待核。"}
    zones = copy.deepcopy(prior["zones_mm"])
    zones["bathroom"] = [settings["bath_rect_mm"]]
    zones["dry-access"] = [settings["dry_access_rect_mm"]]
    areas = copy.deepcopy(prior["area_rows"])
    row = next(r for r in areas if r["zone"] == "bathroom")
    row["sensitivity"] = [{"inset_mm": i, "area_sqm": discussion_area([{"geometry": dict(zip(KEYS, settings["bath_rect_mm"], strict=True))}], i)} for i in cfg["insets_mm"]]
    row["below_target_at_80mm"] = row["sensitivity"][0]["area_sqm"] < row["original_target_sqm"]
    row["below_minimum_insets_mm"] = [r["inset_mm"] for r in row["sensitivity"] if r["area_sqm"] < row["original_minimum_sqm"]]
    requirement = next(r for r in read_json(root / "inputs/requirements.json")["requirements"] if r["id"] == "B.floor-1.palanquin")
    carry_target = max(requirement["constraints"]["door_clear_mm"],
                       *(r["clear_width_mm"] for r in requirement["relationships"] if r["type"] == "transport_path"))
    return model, {"zones_mm": zones, "area_rows": areas, "bath_access": "right-carry-passage",
                   "dry_access": "left-housework-passage-via-dry-vestibule", "surface_slide_assumptions": settings,
                   "left_control_area_rows": prior["area_rows"],
                   "original_carry_target_mm": carry_target, "carry_target_source": "inputs/requirements.json#B.floor-1.palanquin",
                   "old_left_bathroom_retained_as_separate_control": True, "original_targets_retained": True}


def _b_right_envelopes(settings: dict, inset: int) -> dict:
    start = settings["bath_entry_center_y_mm"]-settings["bath_entry_nominal_mm"]/2
    dry_start = settings["dry_entry_center_y_mm"]-settings["dry_entry_nominal_mm"]/2
    projection = settings["surface_slide_projection_mm"]
    return {"park": [4320+inset, start-settings["surface_slide_park_length_mm"], projection, settings["surface_slide_park_length_mm"]],
            "closed": [4320+inset, start, projection, settings["bath_entry_nominal_mm"]],
            "dry_swing": [2500+inset, dry_start, settings["dry_entry_nominal_mm"]+settings["dry_door_leaf_thickness_budget_mm"], settings["dry_entry_nominal_mm"]],
            "dry_open_leaf": [2500+inset, dry_start, settings["dry_entry_nominal_mm"], settings["dry_door_leaf_thickness_budget_mm"]]}


def _b_window_envelopes(settings: dict, inset: int) -> dict:
    _, y, _, _ = settings["zones_mm"]["rear-bath"]
    start = settings["bath_entry_center_x_mm"]-settings["bath_entry_nominal_mm"]/2
    end = start+settings["bath_entry_nominal_mm"]
    dx, _, dw, _ = settings["zones_mm"]["altar-backing"]
    dry_start = settings["dry_entry_center_y_mm"]-settings["dry_entry_nominal_mm"]/2
    right = dx+dw-inset
    return {"park": [end, y+inset, settings["surface_slide_park_length_mm"], settings["surface_slide_projection_mm"]],
            "closed": [start, y+inset, settings["bath_entry_nominal_mm"], settings["surface_slide_projection_mm"]],
            "dry_swing": [right-settings["dry_entry_nominal_mm"]-settings["dry_door_leaf_thickness_budget_mm"], dry_start,
                          settings["dry_entry_nominal_mm"]+settings["dry_door_leaf_thickness_budget_mm"], settings["dry_entry_nominal_mm"]],
            "dry_open_leaf": [right-settings["dry_entry_nominal_mm"], dry_start,
                              settings["dry_entry_nominal_mm"], settings["dry_door_leaf_thickness_budget_mm"]]}


def _exact_pair(cells: dict, a: str, b: str, face: str, center: float, width: float) -> None:
    inverse = {"front": "rear", "rear": "front", "left": "right", "right": "left"}
    axis, length = ("x_mm", "w_mm") if face in {"front", "rear"} else ("y_mm", "h_mm")
    for key, other, side in ((a, b, face), (b, a, inverse[face])):
        door = next(d for d in cells[key]["tour_features"]["doors"] if d["neighbor"] == cells[other]["id"])
        if door["face"] != side or door["width_mm"] != width:
            raise ContractError("B window-study paired opening may not be clipped or moved")
        g = cells[key]["tour_mm"]
        door["ratio"] = (center-g[axis])/g[length]


def b_window_proposal(model: dict, cfg: dict, root: Path) -> tuple[dict, dict]:
    """New rear-window study, independent of all six preserved comparisons."""
    model, prior = b_proposal(model, cfg["b"], root)
    settings = cfg["b_rear_window"]
    if settings["status"] != STATUS or not settings.get("authorization"):
        raise ContractError("B rear window requires research authorization, not adoption")
    first = model["buildings"][0]["floors"][0]
    original = copy.deepcopy(_rooms(first))
    products = {i["catalog_id"]: i for c in original.values() for i in c["furniture"]}
    laundry = {i["id"].rsplit(":", 1)[-1]: i for i in original["work-reserve"]["furniture"]}
    removed = {"bath1", "bath-extension", "bath-shoulder", "work-reserve", "housework-passage", "storage-front", "storage-shoulder"}
    first["cells"] = [c for c in first["cells"] if c["key"] not in removed]
    for key in removed:
        first["layout_review"]["rooms"].pop(key, None)
    specs = {
        "rear-bath": ("後側有窗公衛（乾轉位／淋浴分區）", "bath", ""),
        "dry-route": ("公衛乾通道（不計洗衣面積）", "other", ""),
        "laundry-front": ("前移洗衣凹間（工作陽台仍未核）", "service", "new-B-window-laundry"),
        "laundry-base": ("洗槽操作接段（非公共通道）", "service", "new-B-window-laundry"),
        "altar-backing": ("神桌背後乾式法器櫃（右側獨立門）", "service", ""),
        "corridor1": ("右側搬轎／乾櫃入口（分時）", "other", ""),
        "storage-front": ("武轎入口接段（同一L形庫房）", "service", "new-B-window-storage"),
        "storage": ("右後武轎儲藏（後門優先／前門備案）", "service", "new-B-window-storage"),
    }
    for key, rect in settings["zones_mm"].items():
        name, kind, group = specs[key]
        cell = _room(first, key, rect, template=original["bath1"] if kind == "bath" else original["work-reserve"],
                     name=name, kind=kind, group=group, role="circulation" if key in {"dry-route", "corridor1"} else "",
                     window_mm=0, outdoor=False, window_ratio=.5)
        _empty(cell)
        for stale in ("carry_path_mm", "clearance_reservations", "window_face"):
            cell["review_spec"].pop(stale, None)
        first["layout_review"]["rooms"][key] = copy.deepcopy(cell["review_spec"])
    cells = _rooms(first)
    bath = cells["rear-bath"]
    bath["color"] = "#3fb6c8"
    for raw in settings["fixtures"]:
        i = copy.deepcopy(products[raw["catalog"]])
        i["step_free"] = raw["local"] == "shower"
        _place(bath, i, raw["rect_mm"], raw["rotation_deg"], raw["wall_anchor"], local=raw["local"])
    for raw in settings["laundry_items"]:
        _place(cells[raw["room"]], laundry[raw["local"]], raw["rect_mm"], 0, raw["wall_anchor"], local=raw["local"])
    _place(cells["altar-backing"], original["altar-backing"]["furniture"][0], settings["cabinet_rect_mm"], 270, "left", local="cabinet")
    palanquin = next(i for i in original["storage"]["furniture"] if i["shape"] == "palanquin")
    _place(cells["storage"], palanquin, _body(original["storage"], palanquin), 0, "", local="ceremonal")
    changed = set(settings["zones_mm"]) | removed
    first["layout_review"]["connections"] = [c for c in first["layout_review"]["connections"] if not changed.intersection(c[:2])]
    first["layout_review"]["connections"] += [
        ["shrine", "dry-route", "open"], ["shrine", "corridor1", "open"],
        ["dry-route", "laundry-front", "open"], ["dry-route", "laundry-base", "open"],
        ["laundry-front", "laundry-base", "open"],
        ["dry-route", "rear-bath", {"width_mm": settings["bath_entry_nominal_mm"], "operation": "sliding",
            "label": "公衛拉門（向右停放／救援未核）"}, settings["bath_entry_center_x_mm"]],
        ["corridor1", "altar-backing", {"width_mm": settings["dry_entry_nominal_mm"], "operation": "hinged-inward-proposal",
            "label": "乾櫃右側內開門（取物與搬轎分時）"}, settings["dry_entry_center_y_mm"]],
        ["corridor1", "storage-front", 1660, 5160], ["storage-front", "storage", "open"],
    ]
    window = settings["rear_window"]
    bath["window_mm"] = window["width_mm"]
    bath["review_spec"].update(window_mm=window["width_mm"], window_face="rear",
        window_ratio=(window["center_x_mm"]-bath["tour_mm"]["x_mm"])/bath["tour_mm"]["w_mm"],
        window_note=" 後側開窗權利、防雨、隱私、有效開啟面積未知；仍需獨立排氣、補氣及防水，不保證不發黴。")
    first["layout_review"]["rooms"]["rear-bath"] = copy.deepcopy(bath["review_spec"])
    _rebuild(first)
    _exact_pair(cells, "rear-bath", "dry-route", "front", settings["bath_entry_center_x_mm"], settings["bath_entry_nominal_mm"])
    _exact_pair(cells, "altar-backing", "corridor1", "right", settings["dry_entry_center_y_mm"], settings["dry_entry_nominal_mm"])
    _exact_pair(cells, "corridor1", "storage-front", "rear", 5160, 1660)
    # Revalidate real local dimensions via the shared window API after changing
    # the generic high-window default; never forge a renderable flag.
    bath["tour_features"].update(window_mm=window["width_mm"], window_sill_mm=window["sill_mm"], window_height_mm=window["height_mm"])
    g = bath["tour_mm"]
    spans = {"rear": [(g["x_mm"], g["x_mm"]+g["w_mm"])]} if g["y_mm"]+g["h_mm"] == first["tour_depth_mm"] else {}
    review_window(bath, first, spans)
    if not bath["tour_features"]["window_review"]["renderable"]:
        raise ContractError("B rear bathroom candidate window failed the geometric opening screen")
    cx, cy, radius = settings["turn_circle_mm"]
    bath["tour_features"]["fixed_reserved_mm"].append({"kind": "care-turn", "aabb": _bounds([cx-radius, cy-radius, radius*2, radius*2]),
        "status": "dry-floor-circle-not-rehearsed"})
    for name, rect in settings["bath_operations_mm"].items():
        bath["tour_features"]["fixed_reserved_mm"].append({"kind": "b-window-"+name, "aabb": _bounds(rect), "status": "discussion-operation-not-approved"})
    envelopes = _b_window_envelopes(settings, max(cfg["insets_mm"]))
    for name in ("park", "closed"):
        bath["tour_features"]["fixed_reserved_mm"].append({"kind": "b-window-slider-"+name, "aabb": _bounds(envelopes[name]), "status": "assumed-budget-not-product"})
    cells["altar-backing"]["tour_features"]["fixed_reserved_mm"].append({"kind": "b-window-dry-door-sweep",
        "aabb": _bounds(envelopes["dry_swing"]), "status": "bounding-square-not-product-motion"})
    for key in settings["zones_mm"]:
        cells[key]["tour_features"].pop("pocket_door_review", None)
        cells[key]["tour_features"]["interior_entry_review"] = {"status": STATUS, "note": settings["note"]}
    areas = copy.deepcopy(prior["area_rows"])
    zones = {"bathroom": [settings["zones_mm"]["rear-bath"]], "storage": [settings["zones_mm"][k] for k in ("storage", "storage-front")],
             "laundry": [settings["zones_mm"][k] for k in ("laundry-front", "laundry-base")]}
    for row in areas:
        geometry = [{"geometry": dict(zip(KEYS, r, strict=True))} for r in zones[row["zone"]]]
        row["sensitivity"] = [{"inset_mm": i, "area_sqm": discussion_area(geometry, i)} for i in cfg["insets_mm"]]
        row["below_target_at_80mm"] = row["sensitivity"][0]["area_sqm"] < row["original_target_sqm"]
        row["below_minimum_insets_mm"] = [r["inset_mm"] for r in row["sensitivity"] if r["area_sqm"] < row["original_minimum_sqm"]]
    req = next(r for r in read_json(root / "inputs/requirements.json")["requirements"] if r["id"] == "B.floor-1.palanquin")
    return model, {"zones_mm": zones, "area_rows": areas, "bath_access": "left-dry-route-not-through-private-laundry",
                   "dry_access": "independent-right-corridor-door", "original_targets_retained": True,
                   "original_carry_target_mm": max(req["constraints"]["door_clear_mm"], *(r["clear_width_mm"] for r in req["relationships"] if r["type"] == "transport_path")),
                   "carry_target_source": "inputs/requirements.json#B.floor-1.palanquin",
                   "old_six_comparisons_retained": True, "laundry_public_route_counted_as_area": False,
                   "independent_outdoor_work_balcony": "unmet-private-indoor-laundry-is-not-a-balcony"}


def b_daily_proposal(model: dict, cfg: dict, root: Path) -> tuple[dict, dict]:
    """Add tentative drying equipment only; preserve v6 rooms and all openings."""
    model, review = b_window_proposal(model, cfg, root)
    settings = cfg["b_daily_use"]
    if settings["status"] != STATUS or not settings.get("authorization"):
        raise ContractError("B daily use may only add an authorized comparison")
    first = model["buildings"][0]["floors"][0]
    cells = _rooms(first)
    sample = copy.deepcopy(cells["laundry-front"]["furniture"][0])
    sample = {k: v for k, v in sample.items() if not k.startswith("physical_")}
    sample.update(physical_item_id=None, physical_dimension_source="planning", physical_measurement_state="pending",
                  basis="room-use-inference", evidence=[SOURCE+"#b_daily_use 新增預留，非既有實物或已選產品。"],
                  rear_clearance_mm=0, left_clearance_mm=0, right_clearance_mm=0, mount_height_mm=0,
                  front_clearance_mm=0, wall_gap_mm=115, shared_operation_with=[], in_front_of="", aligned_with="")
    raw = settings["drying_rack"]
    rack = {**sample, **{k: raw[k] for k in ("catalog_id", "label", "width_mm", "depth_mm", "height_mm")},
            "shape": "clothes-rack", "category": "service", "color": "#15803d", "note": raw["note"],
            "front_clearance_mm": raw["front_operation_rect_mm"][3]}
    if (raw["catalog_id"] != "generic-indoor-drying-envelope-1200" or raw["basis"] != "new-generic-occupied-clothes-envelope-not-scaled-2400mm-catalog-rack"
            or [raw[k] for k in ("width_mm", "depth_mm", "height_mm")] != [1200, 600, 1600]):
        raise ContractError("New small occupied drying envelope may not shrink the existing 2400mm rack")
    _place(cells["laundry-base"], rack, raw["rect_mm"], 0, "rear", local="small-drying-rack")
    raw = settings["dehumidifier"]
    if raw["catalog_id"] != "dehumidifier" or raw["assumed_service_each_side_mm"] != 100:
        raise ContractError("Retain traceable dehumidifier product and 100mm discussion service budget")
    product = read_json(root / "inputs/furniture-layout.json")["catalog"][raw["catalog_id"]]
    dehum = {**sample, **product, "catalog_id": raw["catalog_id"], "note": raw["note"]}
    _place(cells["laundry-base"], dehum, raw["rect_mm"], 0, "", local="dehumidifier")
    # Same-source FLOOR envelopes, not walls, paths, manufacturer clearances or
    # ventilation ducts. Existing 900x800 working bands stay full size.
    for name, rect in cfg["b_rear_window"]["laundry_operations_mm"].items():
        cells["laundry-base"]["tour_features"]["fixed_reserved_mm"].append({"kind": "b-daily-existing-"+name,
            "aabb": _bounds(rect), "status": "retained-operation-not-approved"})
    x, y, w, h = raw["rect_mm"]
    inset = raw["assumed_service_each_side_mm"]
    for name, rect in (("drying-loading", settings["drying_rack"]["front_operation_rect_mm"]),
                       ("dehumidifier-service", [x-inset, y-inset, w+2*inset, h+2*inset])):
        cells["laundry-base"]["tour_features"]["fixed_reserved_mm"].append({"kind": "b-daily-"+name,
            "aabb": _bounds(rect), "status": "discussion-envelope-not-manufacturer-or-care-approval"})
    return model, {**review, "daily_use_equipment": "two-new-tentative-items-no-room-or-opening-move",
                   "original_eight_comparisons_retained": True, "new_exterior_laundry_window": False}


def c_proposal(model: dict, cfg: dict) -> tuple[dict, dict]:
    first = model["buildings"][0]["floors"][0]
    cells = _rooms(first)
    kitchen = cells["kitchen"]
    old_kitchen_rect = _rect(kitchen)
    public_before = [{"key": c["key"], "geometry": copy.deepcopy(c["tour_mm"])} for c in cells.values() if c.get("space_group") == "prep-C-open-public"]
    living = cells["living"]
    living_products = copy.deepcopy(living["furniture"])
    old = {i["id"].rsplit(":", 1)[-1]: i for i in kitchen["furniture"]}
    if {p["local"] for p in cfg["products"]} != {"counter", "fridge"} or len(cfg["products"]) != 2:
        raise ContractError("C keeps one existing second-floor washer; do not reintroduce a first-floor machine")
    washers = [(f["id"], i) for f in model["buildings"][0]["floors"] for c in _rooms(f).values()
               for i in c["furniture"] if i["catalog_id"] == "washer"]
    if len(washers) != cfg["washer_count"] or washers[0][0] != cfg["washer_floor"]:
        raise ContractError("C base must have exactly one existing washer on floor-2")
    if len(cfg["living_products"]) != 4 or {p["local"] for p in cfg["living_products"]} != {i["id"].rsplit(":", 1)[-1] for i in living_products}:
        raise ContractError("Retain all four full-size living products; only explicit unscaled poses are allowed")
    _room(first, "kitchen", cfg["kitchen_rect_mm"])
    _room(first, "living", cfg["living_rect_mm"], group=living["space_group"], role=living["space_role"])
    _empty(living)
    for raw in cfg["living_products"]:
        i = next(i for i in living_products if i["id"].rsplit(":", 1)[-1] == raw["local"])
        if raw["wall_anchor"] == "left":
            i["wall_gap_mm"] = raw["rect_mm"][0]-cfg["living_rect_mm"][0]
        _place(living, i, raw["rect_mm"], raw["rotation_deg"], raw["wall_anchor"], freestanding_operation=True)
    _empty(kitchen)
    for raw in cfg["products"]:
        i = copy.deepcopy(old[raw["local"]])
        i["wall_gap_mm"] = raw["rect_mm"][0]-cfg["kitchen_rect_mm"][0] if raw["wall_anchor"] == "left" else raw["rect_mm"][1]-cfg["kitchen_rect_mm"][1]
        i["note"] += " v3與另一設備沿長向錯開；牆邊距為比較分區坐標，不是實測完成面。冰箱散熱／門扇／抽屜與排煙產品未核。"
        _place(kitchen, i, raw["rect_mm"], raw["rotation_deg"], raw["wall_anchor"], local=raw["local"])
    for c in first["layout_review"]["connections"]:
        if set(c[:2]) == {"stair1f", "kitchen"}:
            c[2:] = [{"width_mm": cfg["kitchen_entry_nominal_mm"], "operation": "sliding",
                      "label": "廚房113cm名義門（備餐／開冰箱分時）"}, cfg["kitchen_entry_center_y_mm"]]
    kitchen["name"] = "一字廚房／前置冰箱（洗衣僅二樓一台）"
    kitchen["review_spec"]["name"] = kitchen["name"]
    _rebuild(first)
    return model, {"new_first_floor_washer": "withdrawn-owner-confirmed-one-machine", "washer_count": 1,
                   "washer_floor": cfg["washer_floor"], "second_floor_washer_retained": True,
                   "prior_kitchen_rect_mm": old_kitchen_rect, "kitchen_rect_mm": _rect(kitchen),
                   "kitchen_layout": "front-fridge-facing-rear-longitudinally-offset-from-counter",
                   "public_area_before": public_before,
                   "partition_and_furniture_tradeoff": C_TRADEOFF_STATUS,
                   "independent_work_balcony_requirement": "unmet-unchanged", "drying_soiled_linen_and_chemical_storage": "unresolved",
                   "food_preparation_fridge_operations": "sequential-not-simultaneous"}


def a_proposal(model: dict, cfg: dict) -> tuple[dict, dict]:
    b = next(b for b in model["buildings"] if b["id"] == "A")
    second, third = b["floors"][1:3]
    source_bath = _rooms(second)["master-bath"]
    bath = _rooms(third)["bath3"]
    window = bath["tour_features"]
    if (cfg["bath_strategy"] != "retain-original-rear-window" or not window["window_review"]["renderable"]
            or window["window_face"] != "rear" or not window["window_mm"]):
        raise ContractError("A must retain the original rear bathroom and renderable exterior window proposal")
    # Keep the source geometry, furniture, openings and high-window dimensions.
    # Confirming a preference is not approval to move wet rooms or widen windows.
    bath["name"] = "3F公衛（保留後側外窗／排濕待核）"
    bath["review_spec"]["name"] = bath["name"]
    third["layout_review"]["rooms"]["bath3"]["name"] = bath["name"]
    return model, {"bath_2f_rect_mm": _rect(source_bath), "bath_3f_rect_mm": _rect(bath),
                   "bathroom_stack": "not-aligned-owner-prioritizes-exterior-window",
                   "windowless_relocation": "withdrawn-owner-prefers-exterior-window",
                   "bath_window": "original-rear-high-window-proposal-retained-professional-acceptance-unknown",
                   "bath_window_mm": {k: window[k] for k in ("window_mm", "window_sill_mm", "window_height_mm")},
                   "original_master_ensuite": "unaccommodated-unchanged", "sofa_bed_open_state": "unknown",
                   "ventilation_and_pipe_route": "unresolved-window-alone-does-not-prevent-mould",
                   "all_floor_geometry_and_furniture_positions": "original-retained-no-wet-core-move",
                   "corridor_reduction_claimed": False}


def _screen(model: dict, insets: list, baseline: dict) -> dict:
    floors, body_issues, operations, gaps, shared_floor_operations = [], [], [], [], []
    reference = {f["id"]: f for f in baseline["floors"]}
    for f in model["buildings"][0]["floors"]:
        cells = list(_rooms(f).values())
        rects = [_rect(c) for c in cells]
        total = sum(r[2]*r[3] for r in rects)
        before = sum(c["tour_mm"]["w_mm"]*c["tour_mm"]["h_mm"] for c in _rooms(reference[f["id"]]).values())
        if (any(not _covered(r, [[0, 0, 6000, 17630]]) for r in rects)
                or total != before
                or any(_hits(a, b) for i, a in enumerate(rects) for b in rects[i+1:])):
            raise ContractError("Changed rooms must partition the original frame exactly: "+f["id"])
        floors.append(f["id"])
        if total != 6000*17630:
            if {k: c["tour_mm"] for k, c in _rooms(f).items()} != {k: c["tour_mm"] for k, c in _rooms(reference[f["id"]]).items()}:
                raise ContractError("Cannot change a partially covered inherited floor without redrawing its missing zone")
            gaps.append({"floor": f["id"], "area_sqm": (6000*17630-total)/1e6,
                         "status": "inherited-unallocated-snapshot-zone-unchanged-not-claimed-as-room"})
        for c in cells:
            group = c.get("space_group")
            areas = [_rect(other) for other in cells if other is c or group and other.get("space_group") == group]
            for inset in insets:
                for i in c["furniture"]:
                    if not _inside(_body(c, i), areas, inset):
                        body_issues.append({"room": c["id"], "inset_mm": inset, "issue": i["id"]+":outside-assumed-floor"})
            for index, i in enumerate(c["furniture"]):
                p = c["furniture_placements"]["tour_mm"][i["id"]]
                z = p["mount_height_mm"]
                for other in c["furniture"][index+1:]:
                    op = c["furniture_placements"]["tour_mm"][other["id"]]
                    oz = op["mount_height_mm"]
                    if _hits(_body(c, i), _body(c, other)) and min(z+i["height_mm"], oz+other["height_mm"]) > max(z, oz):
                        body_issues.append({"room": c["id"], "inset_mm": None, "issue": i["id"]+":hits-"+other["id"]})
            for i in c["furniture"]:
                p = c["furniture_placements"]["tour_mm"][i["id"]]
                op = p.get("operation_mm")
                if not op:
                    continue
                r = [op["minX"], op["minY"], op["maxX"]-op["minX"], op["maxY"]-op["minY"]]
                for other in c["furniture"]:
                    if other["id"] != i["id"] and _hits(r, _body(c, other)):
                        issue = {"room": c["id"], "item": i["id"], "hits": other["id"]}
                        is_shared_floor = (model["bc_option"]["id"].endswith("-right-access")
                            and c["tour_features"].get("shared_step_free_floor_review", {}).get("status") == "removable-curtain-and-sequential-only-not-approved"
                            and other["shape"] == "shower" and other.get("step_free"))
                        if is_shared_floor:
                            shared_floor_operations.append({**issue, "status": "sequential-wet-floor-use-not-fixed-glass-or-simultaneous-approval"})
                        else:
                            operations.append(issue)
    return {"frame_area_preserved_floors": floors, "inherited_unallocated_zones": gaps, "furniture_body_sensitivity": body_issues,
            "operation_vs_fixed_body": operations, "operation_vs_shared_wet_floor": shared_floor_operations,
            "professional_approval": "unknown", "rendered_qa": "not-run"}


def _b_right_review(model: dict, cfg: dict, detail: dict) -> dict:
    first = _rooms(model["buildings"][0]["floors"][0])
    settings = cfg["b_right_access"]
    bath, dry = first["bath-extension"], first["altar-backing"]
    door = next(d for d in bath["tour_features"]["doors"] if d["neighbor"] == first["corridor1"]["id"])
    cy = bath["tour_mm"]["y_mm"]+door["ratio"]*bath["tour_mm"]["h_mm"]
    paired = next(d for d in first["corridor1"]["tour_features"]["doors"] if d["neighbor"] == bath["id"])
    if (door["face"] != "right" or paired["face"] != "left" or door["width_mm"] != paired["width_mm"]
            or door["width_mm"] != settings["bath_entry_nominal_mm"] or door["operation"] != paired["operation"] or door["operation"] != "sliding"
            or cy != settings["bath_entry_center_y_mm"]
            or abs(first["corridor1"]["tour_mm"]["y_mm"]+paired["ratio"]*first["corridor1"]["tour_mm"]["h_mm"]-cy) > .001):
        raise ContractError("B right bathroom needs actual paired openings, not only a line through room rectangles")
    dry_door = next(d for d in dry["tour_features"]["doors"] if d["neighbor"] == first["dry-access"]["id"])
    dry_pair = next(d for d in first["dry-access"]["tour_features"]["doors"] if d["neighbor"] == dry["id"])
    dry_cy = dry["tour_mm"]["y_mm"]+dry_door["ratio"]*dry["tour_mm"]["h_mm"]
    if (dry_door["face"] != "left" or dry_pair["face"] != "right" or dry_door["width_mm"] != dry_pair["width_mm"]
            or dry_door["width_mm"] != settings["dry_entry_nominal_mm"] or dry_cy != settings["dry_entry_center_y_mm"]):
        raise ContractError("B dry cabinet needs a paired left entrance, not the removed corridor door")
    all_obstacles = [{"id": i["id"], "rect_mm": _body(c, i)} for c in first.values() for i in c["furniture"]
                     if i["shape"] not in {"palanquin", "wall-tv"} and not (i["shape"] == "shower" and i.get("step_free"))]
    ritual_reserves = [{"id": c["id"]+":ritual-approach", "rect_mm": [a["minX"], a["minY"], a["maxX"]-a["minX"], a["maxY"]-a["minY"]]}
                      for c in first.values() for z in c["tour_features"]["fixed_reserved_mm"] if z["kind"] == "ritual-approach" for a in [z["aabb"]]]
    allowed = [_rect(first[k]) for k in ("shrine-front", "shrine", "corridor1", "bath-extension")]
    rows = []
    for inset in cfg["insets_mm"]:
        envelopes = _b_right_envelopes(settings, inset)
        # Door-closed states are not traversable. For the fully open state,
        # retain the parked leaf/handle projection and solid wall above/below
        # the actual effective opening; a room-union route alone is not proof.
        start, end = cy-door["width_mm"]/2+inset, cy+door["width_mm"]/2-inset
        opaque = [{"id": "bath-wall-front", "rect_mm": [4320-inset, 12970, inset*2, start-12970]},
                  {"id": "bath-wall-rear", "rect_mm": [4320-inset, end, inset*2, 14930-end]}]
        panel = {"id": "open-slider-leaf-and-handle-budget", "rect_mm": envelopes["park"]}
        route_obstacles = all_obstacles+opaque+[panel]+ritual_reserves
        points = [[3400, 3900+inset+450], [3400, 5000], [5160, 5000], [5160, cy],
                  [3205, cy], [2900, cy], [2900, 13950]]
        route = _route(points, 900, 900, allowed, route_obstacles, inset)
        basin_route = _route([[2900, 13950], [2900, 13985], [1705, 13985]], 900, 900, [_rect(bath)], all_obstacles, inset)
        side_route = _route([[2900, 13950], [3305, 13950], [3305, 14215]], 900, 900, [_rect(bath)], all_obstacles, inset)
        dry_allowed = [_rect(first[k]) for k in ("housework-passage", "dry-access", "altar-backing")]
        dry_start, dry_end = dry_cy-dry_door["width_mm"]/2+inset, dry_cy+dry_door["width_mm"]/2-inset
        dry_walls = [{"id": "dry-wall-front", "rect_mm": [2500-inset, 11370, inset*2, dry_start-11370]},
                     {"id": "dry-wall-rear", "rect_mm": [2500-inset, dry_end, inset*2, 12970-dry_end]}]
        dry_route = _route([[570, 12170], [1810, 12170], [3405, 12170]], 700, 700, dry_allowed,
                           all_obstacles+dry_walls+[{"id": "dry-door-fully-open-leaf", "rect_mm": envelopes["dry_open_leaf"]}], inset)
        circle = settings["turn_circle_mm"]
        cx, circle_y, radius = circle
        turn_failures = ["outside-assumed-bathroom"] if not _inside([cx-radius, circle_y-radius, radius*2, radius*2], [_rect(bath)], inset) else []
        turn_failures += [o["id"] for o in all_obstacles if _circle_hits(circle, o["rect_mm"])]
        fixture_failures = [i["id"] for i in bath["furniture"] if not _inside(_body(bath, i), [_rect(bath)], inset)]
        sweep = envelopes["dry_swing"]
        dry_swing_failures = [o["id"] for o in all_obstacles if _hits(sweep, o["rect_mm"])]
        if not _inside(sweep, [_rect(dry)], inset):
            dry_swing_failures.append("outside-assumed-dry-room")
        rows.append({"inset_mm": inset, "bath_entry_route": route, "basin_approach_route": basin_route,
                     "toilet_side_route": side_route, "dry_cabinet_700mm_body_route": dry_route,
                     "passage_width_before_door_projection_mm": 1680-2*inset,
                     "surface_slide_projection_budget_mm": settings["surface_slide_projection_mm"],
                     "passage_width_mm": 1680-2*inset-settings["surface_slide_projection_mm"],
                     "extra_over_900mm_body": 1680-2*inset-settings["surface_slide_projection_mm"]-900,
                     "door_clear_assumption_mm": door["width_mm"]-2*inset,
                     "dry_door_clear_assumption_mm": settings["dry_entry_nominal_mm"]-2*inset,
                     "left_control_passage_width_mm": 1140-2*inset,
                     "turn_circle_coordinate_failures": turn_failures, "fixture_body_coordinate_failures": fixture_failures,
                     "dry_door_swing_coordinate_failures": dry_swing_failures, "door_envelopes_mm": envelopes})
    body_item = next(i for i in first["storage"]["furniture"] if i["shape"] == "palanquin")
    body = _body(first["storage"], body_item)
    center = [body[0]+body[2]/2, body[1]+body[3]/2]
    rear = model["bc_option"]["id"] == "b-rear-right-access"
    points = ([[4500, 17630-115-body[3]/2], [4500, center[1]], center] if rear else
              [[3400, 3900+115+body[3]/2], [3400, 6550], [center[0], 6550], center])
    carry_areas = [_rect(first[k]) for k in ("storage", "storage-front", "storage-shoulder")]
    if not rear:
        carry_areas += [_rect(first[k]) for k in ("shrine-front", "shrine", "corridor1")]
    carry = _route(points, body[2], body[3], carry_areas,
                   all_obstacles+[{"id": "open-bath-slider", "rect_mm": _b_right_envelopes(settings, 115)["park"]}], 115)
    gate = next(d for d in first["corridor1"]["tour_features"]["doors"] if d["neighbor"] == first["storage-front"]["id"])
    gate_pair = next(d for d in first["storage-front"]["tour_features"]["doors"] if d["neighbor"] == first["corridor1"]["id"])
    if gate["face"] != "rear" or gate_pair["face"] != "front" or gate["width_mm"] != gate_pair["width_mm"]:
        raise ContractError("B storage gate needs actual paired opening widths")
    gate_clear = gate["width_mm"]-230
    entry_room = first["storage"] if rear else first["shrine-front"]
    entry_gate = next(d for d in entry_room["tour_features"]["doors"] if d["neighbor"] is None and d["face"] == ("rear" if rear else "front"))
    entry_clear = entry_gate["width_mm"]-230
    if entry_clear < body[2]:
        carry["coordinate_failures"].append("actual-entry-gate:narrower-than-body")
    if not rear and gate_clear < body[2]:
        carry["coordinate_failures"].append("actual-storage-gate:narrower-than-body")
    old_area = next(r for r in detail["left_control_area_rows"] if r["zone"] == "bathroom")
    new_area = next(r for r in detail["area_rows"] if r["zone"] == "bathroom")
    return {"bath_route_sensitivity": rows, "paired_bath_door_coordinate_review": True,
            "bath_area_lost_from_left_control_sqm": [{"inset_mm": old["inset_mm"], "loss_sqm": round(old["area_sqm"]-new["area_sqm"], 4)}
                for old, new in zip(old_area["sensitivity"], new_area["sensitivity"], strict=True)],
            "care_and_rescue": "unknown-900mm-door-shared-shower-floor-and-real-rescue-not-approved",
            "dry_cabinet_route_scope": "700mm-discussion-body-not-wheelchair-accessible-claim",
            "door_state": "bath-fully-open-dry-door-open-operations-and-carry-sequential-only",
            "bath_window": "none-mechanical-exhaust-makeup-air-and-waterproofing-unknown",
            "shower_controls": settings["shower_control_wall"], "shared_wet_floor_and_slip_control": "sequential-only-not-approved",
            "surface_slide_manual_structure_fire_and_emergency_release": "unknown",
            "family_table_benches": "pending-unadopted", "whole_assembled_carry": "unknown-retain-original-deficits",
            "carry_body_115mm": carry, "carry_entry_mode": "rear" if rear else "front",
            "carry_entry_gate_clear_115mm": entry_clear,
            "front_gate_clear_115mm": gate_clear,
            "front_continuous_1500mm_shortfall_mm": max(0, detail["original_carry_target_mm"]-min(gate_clear, rows[-1]["passage_width_mm"])),
            "rear_gate_exists_and_rights": "unknown", "original_storage_and_laundry_area_preserved": True}


def _b_window_review(model: dict, cfg: dict, detail: dict) -> dict:
    first_floor = model["buildings"][0]["floors"][0]
    cells = _rooms(first_floor)
    settings = cfg["b_rear_window"]
    bath, dry = cells["rear-bath"], cells["altar-backing"]

    def pair(a, b, face, center, width=None):
        door = next(d for d in cells[a]["tour_features"]["doors"] if d["neighbor"] == cells[b]["id"])
        other = next(d for d in cells[b]["tour_features"]["doors"] if d["neighbor"] == cells[a]["id"])
        inverse = {"front": "rear", "rear": "front", "left": "right", "right": "left"}
        axis, length = ("x_mm", "w_mm") if face in {"front", "rear"} else ("y_mm", "h_mm")
        centers = [cells[k]["tour_mm"][axis]+d["ratio"]*cells[k]["tour_mm"][length] for k, d in ((a, door), (b, other))]
        if (door["face"] != face or other["face"] != inverse[face] or door["width_mm"] != other["width_mm"]
                or door["operation"] != other["operation"] or width is not None and door["width_mm"] != width
                or any(abs(value-center) > .001 for value in centers)):
            raise ContractError("B window study requires actual paired openings at the reviewed centers")
        return door

    bath_door = pair("rear-bath", "dry-route", "front", settings["bath_entry_center_x_mm"], settings["bath_entry_nominal_mm"])
    dry_door = pair("altar-backing", "corridor1", "right", settings["dry_entry_center_y_mm"], settings["dry_entry_nominal_mm"])
    storage_door = pair("corridor1", "storage-front", "rear", 5160)
    if bath_door["operation"] != "sliding":
        raise ContractError("B window bathroom must retain the reviewed sliding-door operation")
    obstacles = [{"id": i["id"], "rect_mm": _body(c, i)} for c in cells.values() for i in c["furniture"] if i["shape"] not in {"palanquin", "wall-tv"}]
    bath_obstacles = [o for o in obstacles if o["id"].startswith(bath["id"]+":")]
    ritual = [{"id": c["id"]+":ritual-approach", "rect_mm": [a["minX"], a["minY"], a["maxX"]-a["minX"], a["maxY"]-a["minY"]]}
              for c in cells.values() for z in c["tour_features"]["fixed_reserved_mm"] if z["kind"] == "ritual-approach" for a in [z["aabb"]]]
    allowed = [_rect(cells[k]) for k in ("shrine-front", "shrine", "dry-route", "rear-bath")]
    laundry_areas = [_rect(cells[k]) for k in ("laundry-front", "laundry-base")]
    rows = []
    bx, by, bw, bh = _rect(bath)
    for inset in cfg["insets_mm"]:
        env = _b_window_envelopes(settings, inset)
        start = settings["bath_entry_center_x_mm"]-bath_door["width_mm"]/2+inset
        end = settings["bath_entry_center_x_mm"]+bath_door["width_mm"]/2-inset
        walls = [{"id": "bath-front-left-wall", "rect_mm": [bx, by-inset, start-bx, inset*2]},
                 {"id": "bath-front-right-wall", "rect_mm": [end, by-inset, bx+bw-end, inset*2]}]
        panel = {"id": "open-slider-leaf-handle-budget", "rect_mm": env["park"]}
        local = [[680, by-680], [680, 15525], [1200, 15525]]
        cross = 9100+inset+450
        arrival = [[3400, 3900+inset+450], [3400, cross], [570, cross], [570, 11935], [680, 11935], local[0]]+local[1:]
        route = _route(arrival, 900, 900, allowed, obstacles+walls+[panel], inset)
        during_ritual = _route(arrival, 900, 900, allowed, obstacles+walls+[panel]+ritual, inset)
        local_route = _route(local, 900, 900, [_rect(cells["dry-route"]), _rect(bath)], obstacles+walls+[panel], inset)
        closed_route = _route(local, 900, 900, [_rect(cells["dry-route"]), _rect(bath)], obstacles+walls+[panel, {"id": "closed-slider", "rect_mm": env["closed"]}], inset)
        basin_route = _route([[1200, 15525], [1200, 15725], [1985, 15725], [1985, 16615]], 900, 900, [_rect(bath)], bath_obstacles+[panel], inset)
        side_route = _route([[1200, 15525], [1200, 15725], [1985, 15725]], 900, 900, [_rect(bath)], bath_obstacles+[panel], inset)
        shower_route = _route([[1200, 15525], [1105, 15525], [1105, 15865], [715, 15865]], 900, 900, [_rect(bath)], bath_obstacles+[panel], inset)
        circle = settings["turn_circle_mm"]
        cx, cy, radius = circle
        turn_failures = [] if _inside([cx-radius, cy-radius, radius*2, radius*2], [_rect(bath)], inset) else ["outside-assumed-bathroom"]
        turn_failures += [o["id"] for o in bath_obstacles+[panel] if _circle_hits(circle, o["rect_mm"])]
        operation_failures = []
        for name, rect in settings["bath_operations_mm"].items():
            if not _inside(rect, [_rect(bath)], inset):
                operation_failures.append(name+":outside-assumed-bathroom")
            operation_failures += [name+":hits-"+o["id"] for o in bath_obstacles+[panel] if _hits(rect, o["rect_mm"])]
        laundry_failures = []
        for name, rect in settings["laundry_operations_mm"].items():
            if not _inside(rect, laundry_areas, inset):
                laundry_failures.append(name+":outside-private-laundry")
            laundry_failures += [name+":hits-"+o["id"] for o in obstacles if _hits(rect, o["rect_mm"])]
        dry_start = settings["dry_entry_center_y_mm"]-dry_door["width_mm"]/2+inset
        dry_end = settings["dry_entry_center_y_mm"]+dry_door["width_mm"]/2-inset
        dx, dy, dw, dh = _rect(dry)
        dry_walls = [{"id": "dry-right-front-wall", "rect_mm": [dx+dw-inset, dy, inset*2, dry_start-dy]},
                     {"id": "dry-right-rear-wall", "rect_mm": [dx+dw-inset, dry_end, inset*2, dy+dh-dry_end]}]
        dry_route = _route([[5160, 12170], [3465, 12170]], 700, 700, [_rect(dry), _rect(cells["corridor1"])],
                           obstacles+dry_walls+[{"id": "dry-fully-open-leaf", "rect_mm": env["dry_open_leaf"]}], inset)
        dry_swing_failures = [o["id"] for o in obstacles if _hits(env["dry_swing"], o["rect_mm"])]
        if not _inside(env["dry_swing"], [_rect(dry)], inset):
            dry_swing_failures.append("outside-assumed-dry-room")
        rows.append({"inset_mm": inset, "bath_entry_route": route, "local_bath_open_route": local_route,
                     "closed_door_route": closed_route, "basin_approach_route": basin_route,
                     "toilet_side_route": side_route, "shower_approach_route": shower_route,
                     "arrival_during_ritual": during_ritual,
                     "arrival_scope": "conditional-time-separated-not-public-care-or-fire-approval",
                     "dry_cabinet_700mm_body_route": dry_route, "dry_door_swing_coordinate_failures": dry_swing_failures,
                     "passage_width_mm": cells["dry-route"]["tour_mm"]["w_mm"]-2*inset,
                     "extra_over_900mm_body": cells["dry-route"]["tour_mm"]["w_mm"]-2*inset-900,
                     "door_clear_assumption_mm": bath_door["width_mm"]-2*inset,
                     "dry_door_clear_assumption_mm": dry_door["width_mm"]-2*inset,
                     "turn_circle_coordinate_failures": turn_failures, "bath_operation_coordinate_failures": operation_failures,
                     "laundry_operation_coordinate_failures": laundry_failures, "door_envelopes_mm": env,
                     "local_open_route_leaf_gap_mm": local[1][1]-450-(env["park"][1]+env["park"][3])})
    item = next(i for i in cells["storage"]["furniture"] if i["shape"] == "palanquin")
    body = _body(cells["storage"], item)
    center = [body[0]+body[2]/2, body[1]+body[3]/2]
    rear = model["bc_option"]["id"] in {"b-rear-window", "b-rear-dry-service"}
    entry_room, face = (cells["storage"], "rear") if rear else (cells["shrine-front"], "front")
    entry = next(d for d in entry_room["tour_features"]["doors"] if d["neighbor"] is None and d["face"] == face)
    entry_x = entry_room["tour_mm"]["x_mm"]+entry["ratio"]*entry_room["tour_mm"]["w_mm"]
    points = ([[entry_x, 17630-115-body[3]/2], [entry_x, center[1]], center] if rear else
              [[entry_x, 3900+115+body[3]/2], [entry_x, 6550], [center[0], 6550], center])
    areas = [_rect(cells[k]) for k in ("storage", "storage-front")]+([] if rear else [_rect(cells[k]) for k in ("shrine-front", "shrine", "corridor1")])
    # Effective apertures, not only adjacent floor rectangles, constrain carry.
    cx = 5160
    left, right = cx-storage_door["width_mm"]/2+115, cx+storage_door["width_mm"]/2-115
    storage_walls = [{"id": "storage-front-left-wall", "rect_mm": [2700, 12970-115, left-2700, 230]},
                     {"id": "storage-front-right-wall", "rect_mm": [right, 12970-115, 6000-right, 230]}]
    carry = _route(points, body[2], body[3], areas, obstacles+storage_walls, 115)
    gate_clear, entry_clear = storage_door["width_mm"]-230, entry["width_mm"]-230
    if entry_clear < body[2]:
        carry["coordinate_failures"].append("actual-entry-gate:narrower-than-body")
    if not rear and gate_clear < body[2]:
        carry["coordinate_failures"].append("actual-storage-gate:narrower-than-body")
    op = list(settings["laundry_operations_mm"].values())
    window = bath["tour_features"]["window_review"]
    return {"bath_route_sensitivity": rows, "paired_bath_door_coordinate_review": True,
            "bath_window": "direct-rear-candidate-rights-and-effective-ventilation-unknown",
            "bath_window_review": copy.deepcopy(window),
            "care_and_rescue": "unknown-900mm-door-and-real-rescue-not-approved",
            "dry_cabinet_route_scope": "700mm-discussion-body-not-wheelchair-accessible-claim",
            "shower_controls": "rear-left-solid-wall-away-from-window-and-slider",
            "dry_turn_and_transfer_do_not_borrow_shower": True,
            "arrival_ritual_conflict": "must-time-separate-pending-family-no-simultaneous-passage-claim",
            "door_state": "bath-fully-open-dry-door-open-operations-and-carry-sequential-only",
            "surface_slide_manual_structure_fire_and_emergency_release": "unknown",
            "laundry_operation_bands_overlap": _hits(op[0], op[1]),
            "laundry_use": "sequential-washer-and-sink-no-public-passage-through-private-bay",
            "laundry_exterior_window": "none-after-relocation-exhaust-drying-and-original-balcony-target-unresolved",
            "family_table_benches": "pending-unadopted", "whole_assembled_carry": "unknown-retain-original-deficits",
            "carry_body_115mm": carry, "carry_entry_mode": "rear" if rear else "front",
            "carry_entry_gate_clear_115mm": entry_clear, "front_gate_clear_115mm": gate_clear,
            "front_continuous_1500mm_shortfall_mm": max(0, detail["original_carry_target_mm"]-min(gate_clear, cells["corridor1"]["tour_mm"]["w_mm"]-230)),
            "rear_gate_exists_and_rights": "unknown", "original_storage_and_laundry_area_preserved": False,
            "all_upper_floors_and_altar_stair_footprints": "unchanged"}


def _functional_review(model: dict, bid: str, cfg: dict, detail: dict, root: Path) -> dict:
    b = model["buildings"][0]
    first = _rooms(b["floors"][0])
    rows = []
    if bid == "B" and model["bc_option"]["id"].endswith("-dry-service"):
        window_review = _b_window_review(model, cfg, detail)
        plans = plan_data(model)["buildings"][0]
        seated = read_json(root / "inputs/b32-service-detail.json")["shrine"]["ritual_seated_benches"]
        return {**window_review, "daily_use_review": review_daily_use(plans, cfg["b_daily_use"], {**detail, **window_review}, cfg["insets_mm"], seated)}
    if bid == "B" and model["bc_option"]["id"].endswith("-window"):
        return _b_window_review(model, cfg, detail)
    if bid == "B" and model["bc_option"]["id"].endswith("-right-access"):
        return _b_right_review(model, cfg, detail)
    if bid == "B":
        bath_areas = [_rect(first[k]) for k in ("bath1", "bath-extension", "bath-shoulder")]
        allowed = bath_areas+[_rect(first[k]) for k in ("shrine-front", "shrine", "housework-passage", "work-reserve")]
        obstacles = [{"id": i["id"], "rect_mm": _body(c, i)} for c in first.values() for i in c["furniture"]
                     if i["shape"] not in {"shower", "palanquin", "wall-tv"}]
        for inset in cfg["insets_mm"]:
            cross = 9100+inset+450
            points = [[3400, 3900+inset+450], [3400, cross], [570, cross], [570, cfg["b"]["bath_entry_center_y_mm"]],
                      [1810, cfg["b"]["bath_entry_center_y_mm"]], [1810, 13650], [2455, 13650]]
            route = _route(points, 900, 900, allowed, obstacles, inset)
            rows.append({"inset_mm": inset, "bath_entry_route": route,
                         "passage_width_mm": 1140-2*inset, "extra_over_900mm_body": 1140-2*inset-900,
                         "door_clear_assumption_mm": cfg["b"]["bath_entry_nominal_mm"]-2*inset,
                         "pocket_wall_budget_available_mm": 2*inset,
                         "pocket_wall_budget_meets_proposal": 2*inset >= cfg["b"]["pocket_required_wall_budget_mm"]})
        storage_body = next(i for i in first["storage"]["furniture"] if i["shape"] == "palanquin")
        body = _body(first["storage"], storage_body)
        center = [body[0]+body[2]/2, body[1]+body[3]/2]
        rear = model["bc_option"]["id"] == "b-rear-service"
        carry_points = ([[4500, 17630-115-body[3]/2], [4500, center[1]], center] if rear else
                        [[3400, 3900+115+body[3]/2], [3400, 6550], [center[0], 6550], center])
        carry_areas = [_rect(first[k]) for k in ("storage", "storage-front", "storage-shoulder")]
        if not rear:
            carry_areas += [_rect(first[k]) for k in ("shrine-front", "shrine", "corridor1")]
        carry = _route(carry_points, body[2], body[3], carry_areas, [o for o in obstacles if o["id"] != storage_body["id"]], 115)
        return {"bath_route_sensitivity": rows, "care_and_rescue": "unapproved-narrow-route-and-pocket-product",
                "old_right_bath_door": "removed-in-this-comparison-only", "shower_controls": cfg["b"]["shower_control_wall"],
                "family_table_benches": "pending-unadopted", "whole_assembled_carry": "unknown-retain-original-deficits",
                "carry_body_115mm": carry, "carry_entry_mode": "rear" if rear else "front",
                "front_gate_clear_115mm": 1660-230, "rear_gate_exists_and_rights": "unknown"}
    if bid == "C":
        allowed = [_rect(first[k]) for k in ("kitchen", "stair1f")]
        kitchen = first["kitchen"]
        products = {i["id"].rsplit(":", 1)[-1]: i for i in kitchen["furniture"]}
        counter, fridge = (products[k] for k in ("counter", "fridge"))
        counter_body, fridge_body = (_body(kitchen, i) for i in (counter, fridge))
        operations = {k: kitchen["furniture_placements"]["tour_mm"][i["id"]]["operation_mm"] for k, i in products.items()}
        operation_rects = {k: [op["minX"], op["minY"], op["maxX"]-op["minX"], op["maxY"]-op["minY"]] for k, op in operations.items()}
        g = _rect(kitchen)
        gap = counter_body[1]-(fridge_body[1]+fridge_body[3])
        door_y = cfg["c"]["kitchen_entry_center_y_mm"]
        kitchen_door = next(d for d in kitchen["tour_features"]["doors"] if d["neighbor"] == first["stair1f"]["id"])
        stair_door = next(d for d in first["stair1f"]["tour_features"]["doors"] if d["neighbor"] == kitchen["id"])
        paired_door = (kitchen_door["face"] == "right" and stair_door["face"] == "left"
                       and kitchen_door["width_mm"] == stair_door["width_mm"] == cfg["c"]["kitchen_entry_nominal_mm"]
                       and abs(g[1]+g[3]*kitchen_door["ratio"]-door_y) < .01
                       and abs(first["stair1f"]["tour_mm"]["y_mm"]+first["stair1f"]["tour_mm"]["h_mm"]*stair_door["ratio"]-door_y) < .01)
        if not paired_door or counter["front_clearance_mm"] != 900 or fridge["front_clearance_mm"] != 600:
            raise ContractError("C retains paired kitchen entry and original 900/600mm discussion operation bands")
        obstacles = [{"id": i["id"], "rect_mm": _body(kitchen, i)} for i in kitchen["furniture"]]
        stairs = first["stair1f"]["tour_features"]["stair_footprint_mm"]
        obstacles.append({"id": "real-stair-footprint", "rect_mm": [stairs[k] for k in KEYS]})
        for inset in cfg["insets_mm"]:
            route = _route([[2870, door_y], [1275, door_y], [1275, 10000]], 900, 900, allowed, obstacles, inset)
            center = [fridge_body[0]+fridge_body[2]/2, fridge_body[1]+fridge_body[3]/2]
            replacement = _route([center, [center[0], door_y], [2870, door_y]], fridge_body[2], fridge_body[3],
                                 allowed, [o for o in obstacles if o["id"] != fridge["id"]], inset)
            body_issues = [key for key, item in products.items() if not _inside(_body(kitchen, item), [g], inset)]
            operation_issues = [key+":outside-assumed-floor" for key, rect in operation_rects.items() if not _inside(rect, [g], inset)]
            operation_issues += [key+":hits-"+other for key, rect in operation_rects.items()
                                 for other, item in products.items() if key != other and _hits(rect, _body(kitchen, item))]
            counter_fridge_overlap = min(counter_body[1]+counter_body[3], fridge_body[1]+fridge_body[3]) > max(counter_body[1], fridge_body[1])
            work_end_x = fridge_body[0] if counter_fridge_overlap else g[0]+g[2]-inset
            assumed_back = fridge_body[1]-g[1]-inset
            assumed_side = g[0]+g[2]-inset-fridge_body[0]-fridge_body[2]
            rows.append({"inset_mm": inset, "kitchen_entry_route": route, "fridge_body_replacement_route": replacement,
                         "door_clear_assumption_mm": cfg["c"]["kitchen_entry_nominal_mm"]-2*inset,
                         "paired_door_coordinate_review": paired_door,
                         "kitchen_width_after_assumed_finishes_mm": g[2]-2*inset,
                         "prior_opposed_layout_shortfall_mm": max(0, 600+900+700-(2400-2*inset)),
                         "counter_working_width_at_fixed_products_mm": work_end_x-counter_body[0]-counter_body[2],
                         "counter_operation_depth_mm": counter["front_clearance_mm"],
                         "fridge_operation_depth_mm": fridge["front_clearance_mm"],
                         "counter_fridge_longitudinal_gap_mm": gap,
                         "fridge_back_space_after_inset_mm": assumed_back, "fridge_side_space_after_inset_mm": assumed_side,
                         "fridge_clearance_discussion_assumptions_met": assumed_back >= cfg["c"]["fridge_clearance_assumptions_mm"]["back"]
                             and assumed_side >= cfg["c"]["fridge_clearance_assumptions_mm"]["right_side"]
                             and gap >= cfg["c"]["fridge_clearance_assumptions_mm"]["counter_longitudinal_gap"],
                         "fixed_body_failures": body_issues, "operation_failures": operation_issues})
        public_now = [{"key": c["key"], "geometry": c["tour_mm"]} for c in first.values() if c.get("space_group") == "prep-C-open-public"]
        nominal_before, nominal_now = (round(sum(r["geometry"]["w_mm"]*r["geometry"]["h_mm"] for r in group)/1e6, 4)
                                       for group in (detail["public_area_before"], public_now))
        dining_before, dining_now = (round(sum(r["geometry"]["w_mm"]*r["geometry"]["h_mm"] for r in group if r["key"] != "entrance")/1e6, 4)
                                     for group in (detail["public_area_before"], public_now))
        return {"kitchen_route_sensitivity": rows, "food_fridge": "sequential-shared-operations-not-fixed-body-overlap",
                "public_area_tradeoff": {"status": C_TRADEOFF_STATUS, "front_partition_shift_mm": detail["prior_kitchen_rect_mm"][1]-g[1],
                     "nominal_public_before_sqm": nominal_before, "nominal_public_now_sqm": nominal_now,
                     "public_includes_foyer": True,
                     "nominal_living_dining_without_foyer_before_sqm": dining_before,
                     "nominal_living_dining_without_foyer_now_sqm": dining_now,
                     "nominal_public_loss_sqm": round(nominal_before-nominal_now, 4),
                     "public_sensitivity": [{"inset_mm": inset, "before_sqm": discussion_area(detail["public_area_before"], inset),
                                              "now_sqm": discussion_area(public_now, inset)} for inset in cfg["insets_mm"]],
                     "pure_living_or_legal_area_claimed": False, "stair_and_elder_route_geometry": "unchanged"},
                "kitchen_product_manual_approval": "unknown-100mm-back-and-side-are-discussion-assumptions-not-manufacturer-rules",
                "door_sweep_drawers_pocket_extraction_and_exhaust": "unknown-not-approved",
                "soiled_linen_chemicals_drying_and_work_balcony": "unresolved-not-complete-laundry-room"}
    second, third = _rooms(b["floors"][1]), _rooms(b["floors"][2])
    old_study = _rect(second["study"])
    bath = _rect(third["bath3"])
    areas = []
    requirements = read_json(root / "inputs/requirements.json")
    for rid, key in (("A.floor-3.bath3", "bath3"), ("A.floor-3.multi", "multi")):
        requirement = next(r["constraints"] for r in requirements["requirements"] if r["id"] == rid)
        areas.append({"requirement_id": rid, "original_minimum_sqm": requirement["min_sqm"], "original_target_sqm": requirement["target_sqm"],
                      "sensitivity": [{"inset_mm": i, "area_sqm": discussion_area([{"geometry": third[key]["tour_mm"]}], i)} for i in cfg["insets_mm"]]})
    return {"bath_over_second_floor_study": _hits(bath, old_study), "area_rows": areas,
            "wet_area_over_study_removed": False,
            "window_and_exhaust_approval": "unknown-window-retained-not-a-mould-guarantee",
            "reading_multi_daylight_and_sofa_bed": "unapproved-original-layout-retained"}


def build_study(root: Path = ROOT) -> dict:
    cfg = read_json(root / SOURCE)
    if (cfg.get("schema") != "house-interior-improvements-v1" or cfg.get("revision") != REVISION or cfg.get("status") != STATUS
            or cfg["frame_mm"] != [6000, 17630] or cfg["frontage_depth_mm"] != 3900
            or cfg["insets_mm"] != [80, 100, 115] or set(cfg["professional_status"].values()) != {"unknown"}):
        raise ContractError("Interior improvements preserve the frame, revision and unresolved professional approvals")
    _validate_owner_choices(cfg)
    fresh = build_reconciliation(root)
    if any(s["source_freshness"]["issues"] for s in fresh["scenarios"]):
        raise ContractError("A base snapshot has stale sources; do not build a new proposal on an unlabelled stale model")
    sources = {k: read_model(_public_path(root, p)) for k, p in cfg["sources"].items()}
    options = []
    for oid, bid, model, label in [
        ("b-rear-service", "B", _select(sources["b32"], "b32-rear", "B"), "B32後門優先｜左側家務／浴室拉門比較"),
        ("b-front-service", "B", _select(sources["b32"], "b32-front", "B"), "B32前門備案｜同服務配置／搬運目標待解"),
        ("c-care-laundry", "C", _select(sources["c_integrated"], cfg["c"]["base_option"], "C"), "C有窗公衛整合｜前置冰箱／客餐取捨已確認"),
        ("a-upper-wet-core", "A", sources["abc"], "A有窗公衛優先｜保留三樓後側衛浴"),
        ("b-rear-right-access", "B", _select(sources["b32"], "b32-rear", "B"), "B32後門優先｜右側浴室／左側乾櫃比較"),
        ("b-front-right-access", "B", _select(sources["b32"], "b32-front", "B"), "B32前門備案｜右側浴室／左側乾櫃比較"),
        ("b-rear-window", "B", _select(sources["b32"], "b32-rear", "B"), "B32後門優先｜後窗公衛／家務前移比較"),
        ("b-front-window", "B", _select(sources["b32"], "b32-front", "B"), "B32前門備案｜後窗公衛／家務前移比較"),
        ("b-rear-dry-service", "B", _select(sources["b32"], "b32-rear", "B"), "B32後門優先｜小量晾衣／除濕與祭祀使用研究"),
        ("b-front-dry-service", "B", _select(sources["b32"], "b32-front", "B"), "B32前門備案｜小量晾衣／除濕與祭祀使用研究")]:
        model = copy.deepcopy(model)
        baseline = copy.deepcopy(next(b for b in model["buildings"] if b["id"] == bid))
        is_right = oid.endswith("-right-access")
        is_window = oid.endswith("-window")
        is_daily = oid.endswith("-dry-service")
        if is_daily:
            model, review = b_daily_proposal(model, cfg, root)
        elif is_window:
            model, review = b_window_proposal(model, cfg, root)
        elif is_right:
            model, review = b_right_proposal(model, cfg, root)
        elif bid == "B":
            model, review = b_proposal(model, cfg["b"], root)
        elif bid == "C":
            model, review = c_proposal(model, cfg["c"])
        else:
            model, review = a_proposal(model, cfg["a"])
        notes = [cfg["b_daily_use" if is_daily else "b_rear_window" if is_window else "b_right_access" if is_right else bid.lower()]["note"], *[d["recommendation"] for d in cfg["owner_decisions"] if d["building"] == bid],
                 "獨立比較未採用；原ABC／B32／C比較、需求與實測不改。32地坪不是每層可建面積。"]
        model = _finish(model, bid, oid, label, notes)
        screen = _screen(model, cfg["insets_mm"], baseline)
        if bid == "C" and (any(i["inset_mm"] is None or i["room"] in {"C:floor-1:living", "C:floor-1:kitchen"}
                               for i in screen["furniture_body_sensitivity"])
                           or screen["operation_vs_fixed_body"]):
            raise ContractError("C kitchen tradeoff may not create fixed-body or retained seating-operation conflicts")
        plans = plan_data(model)["buildings"][0]
        for f in plans["floors"]:
            f["plan_file"] = oid+"_"+f["id"]+".svg"
        functional = _functional_review(model, bid, cfg, review, root)
        if bid == "B":
            last = functional["bath_route_sensitivity"][-1]
            if is_daily:
                daily = functional["daily_use_review"]
                cut = daily["cross_corridor"]
                notes.append("新增的120×60×160cm小型晾衣外廓不是把原240cm架縮小，含暫估掛衣範圍；容量、衣物外伸與滴水仍待選品。35×30×60cm除濕機保留原尺寸、另留四周100mm假設散熱／取水預算；不是機型或能力已核。原洗衣機、洗槽及各900×800mm操作帶不動。")
                notes.append("700×700mm本體只從既有左側乾通道測局部取放衣物，非輪椅／公共通行核可；不能藉此說祭祀時從街門也可到達。晾衣／除濕設備不侵入公共乾通道、原洗衣／洗槽操作或搬轎區。家務面積仍僅5.0050m²、無直接窗；屋內小量乾衣不等於工作陽台或全家衣量已滿足。")
                notes.append(f"不推薦只切橫走道：若從家務區另切1130mm名義橫帶，115mm假設僅900mm淨寬，家務需讓出名義{cut['nominal_area_taken_sqm']:.4f}m²，剩{cut['remaining_laundry_area_sensitivity'][-1]['area_sqm']:.4f}m²，低於原4m²下限／5m²目標；新門與完整轉彎也未設計，不當成通路已成立。")
                notes.append("祭祀占用時原如廁路線仍阻擋，兩張長凳改祭祀座位會再影響左側；不能把『暫停祭祀再過』或『改去樓上』當作照護可用解法。若要同時使用，最佳下一步是比較後右公衛／後左武轎庫，須重排後門、重新驗前門搬運；尚未繪入或默認採用。")
                notes.append("排濕預先條件：浴室獨立排氣補氣，家務另設對外排風候選方向，不排到神明堂、法器櫃、武轎庫或封閉天花；跨庫房天花到後外牆的管道、開口與防火仍未設計。除濕不等於換氣；冷凝排水、專用安全插座、防滴水／排水與維修待機電確認，不能拉軟管或延長線跨公共門道。未新增門或隔間，不宣稱已是密閉除濕房，濕氣外逸與法器保存仍未解；乾衣時的門窗／排風／除濕控制未選定。")
                notes.append("保留後窗公衛270×313cm、900×600mm候選後高窗／1500mm窗台及原浴室7.1630、儲藏11.1215m²討論值；前門連續1500mm搬運仍差70mm，後巷與外窗權利未知；原上層、IDF、KTV、停車與神桌完成面邊距缺口不變。")
            elif is_window:
                areas = {r["zone"]: r for r in review["area_rows"]}
                notes.append(f"新浴室270×313cm：80／115mm假設討論面積{areas['bathroom']['sensitivity'][0]['area_sqm']:.4f}／{areas['bathroom']['sensitivity'][-1]['area_sqm']:.4f}m²；儲藏為{areas['storage']['sensitivity'][0]['area_sqm']:.4f}／{areas['storage']['sensitivity'][-1]['area_sqm']:.4f}m²。只是座標初排，不是合法淨面積或功能通過。")
                notes.append(f"前移家務80／115mm假設為{areas['laundry']['sensitivity'][0]['area_sqm']:.4f}／{areas['laundry']['sensitivity'][-1]['area_sqm']:.4f}m²；原4m²下限／5m²目標不減。115mm時僅多0.005m²，實際柱牆或設備可立即吃掉餘裕；不把乾通道加進去湊數，也不當室內洗衣凹間已是工作陽台。兩個900×800mm操作帶保留；晾乾、獨立排濕與同時操作仍未核。")
                notes.append(f"左側乾通道115mm假設淨寬{last['passage_width_mm']}mm，公衛門洞仍只有{last['door_clear_assumption_mm']}mm；門全開後先直進再轉，指定900mm矩形橫移試線距停門凸出預算{last['local_open_route_leaf_gap_mm']}mm，不能稱照護／救援已核。門關時試線被阻擋。乾區轉位與便器側移不借淋浴本體。")
                notes.append("公衛到達路線經神明堂祭祀預留區，必須與祭祀分時；供桌貼桌、兩長凳停放仍待家中同意。乾櫃另從右側進，不穿洗衣工作區；取物與搬轎分時。不是獨立避開祭祀的公共或消防通道。")
                notes.append(f"後牆90×60cm候選窗、窗台150cm，設於洗手台上方／淋浴之外；不假設側界開窗。外牆開窗權利、防雨、有效通風、冷凝水與獨立排氣補氣未核，不保證防黴。前門搬運連續1500mm目標仍差{functional['front_continuous_1500mm_shortfall_mm']}mm；後門通行權及裝桿人員未知。")
                notes.append("只重排一樓後段，不表示B整棟通過：神桌背側原80mm邊距在100／115mm假設仍差20／35mm，原上層完成面、IDF、KTV與停車等缺口保留未解，不拿新浴室面積掩蓋。")
            elif is_right:
                bath_area = next(r for r in review["area_rows"] if r["zone"] == "bathroom")
                notes.append(f"115mm假設下右側扣95mm停門／把手預算後通道{last['passage_width_mm']}mm，門洞仍只{last['door_clear_assumption_mm']}mm；原左側控制通道{last['left_control_passage_width_mm']}mm。浴室80／115mm面積{bath_area['sensitivity'][0]['area_sqm']:.4f}／{bath_area['sensitivity'][-1]['area_sqm']:.4f}m²，低於原7m²目標；不可稱照護已通過。")
                notes.append(f"乾櫃仍120×45cm、改靠右牆；左側乾櫃門115mm假設淨寬{last['dry_door_clear_assumption_mm']}mm，只用700mm討論本體，非輪椅路徑。公衛仍無外窗，須研究獨立機械排氣／補氣、防水與維修，不保證防黴。")
                notes.append(f"右側拉門只比較名義門位與1230mm停門／95mm凸出預算，不是已選產品。即使120cm武轎本體試線不撞，前門連續1500mm目標仍差{functional['front_continuous_1500mm_shortfall_mm']}mm；乾櫃門、搬轎及衛浴操作分時，救援／人員／裝桿外廓未核。")
            else:
                notes.append(f"115mm假設下家務通道{last['passage_width_mm']}mm、對900mm本體僅餘{last['extra_over_900mm_body']}mm；門袋需230mm討論牆，80／100mm內縮預算不足。不是已合格照護方案。")
            notes.append("前門儲藏門115mm假設僅1430mm，原1500mm目標保留未達；後門通行權、裝桿、人員與門外轉向未知。")
        elif bid == "C":
            last = functional["kitchen_route_sensitivity"][-1]
            notes.append(f"115mm內縮假設下，原對向排法仍差{last['prior_opposed_layout_shortfall_mm']}mm；新比較沿長向錯開{last['counter_fridge_longitudinal_gap_mm']}mm，廚具前方討論寬{last['counter_working_width_at_fixed_products_mm']}mm、原操作帶仍900mm。冰箱背／右側各{last['fridge_back_space_after_inset_mm']}mm只作散熱討論預算，不是原廠已核。")
            trade = functional["public_area_tradeoff"]
            notes.append(f"取捨已確認，列後續整合（非整案／施工核可）：不含玄關的開放客餐名義面積由{trade['nominal_living_dining_without_foyer_before_sqm']:.4f}減至{trade['nominal_living_dining_without_foyer_now_sqm']:.4f}m²，少{trade['nominal_public_loss_sqm']:.2f}m²（仍含原通行，非純客廳／法定面積）；連玄關為{trade['nominal_public_now_sqm']:.4f}m²。原孝親通道、梯段、床、公衛與2F／3F均不動；備餐、開冰箱及穿廚房門仍分時。")
            notes.append("保留原C整合案客房／起居面積不足、跑步機原廠與隔振、停車及1F工作陽台缺口；撤下1F洗衣機不等於這些問題已完成。")
        else:
            areas = {r["requirement_id"]: r for r in functional["area_rows"]}
            notes.append(f"保留原3F衛浴：80mm討論面積{areas['A.floor-3.bath3']['sensitivity'][0]['area_sqm']:.4f}m²、115mm為{areas['A.floor-3.bath3']['sensitivity'][-1]['area_sqm']:.4f}m²；115mm時仍低於原4.5m²目標。原多用途區80mm為{areas['A.floor-3.multi']['sensitivity'][0]['area_sqm']:.4f}m²，低於原10m²目標。")
            notes.append("撤回無窗移浴室，不再宣稱濕區集中或避開2F書房投影；公共走道與原家具位置保留，面積過大、閱讀／多用途採光、沙發床展開、原主臥套衛及停車仍未解。")
        model["bc_option"]["owner_decisions"] = [copy.deepcopy(d) for d in cfg["owner_decisions"] if d["building"] == bid]
        if is_daily and (screen["operation_vs_fixed_body"] or any(
                issue["room"] == "B:floor-1:laundry-base" for issue in screen["furniture_body_sensitivity"]) or any(
                row["equipment_and_operation_failures"] or row["local_loading_700mm_body_route"]["coordinate_failures"]
                for row in functional["daily_use_review"]["sensitivity"])):
            raise ContractError("Daily drying study creates an actual fixed-body, retained-operation or local-access conflict")
        model["bc_option"]["geometry_review"] = {**review, **screen, **functional}
        options.append({"id": oid, "building": bid, "label": label, "status": STATUS,
                        "plans": plans, "model": model, "tradeoffs": notes, "review": {**review, **screen, **functional}})
    sources_to_hash = [SOURCE, DOOR_ENVELOPES, "inputs/b32-service-detail.json", "inputs/b32-service-study.json",
                       "inputs/project.json", "inputs/requirements.json", "inputs/physical-items.json", "inputs/furniture-layout.json",
                       *cfg["sources"].values(), "structured/candidates/b32-entry-options/layout.js"]
    sources_to_hash += [str(p.relative_to(ROOT)) for p in [
        ROOT / "scripts/templates/model3d.html", ROOT / "scripts/templates/model3d_facade.js",
        ROOT / "scripts/templates/c-integrated-options.html", ROOT / "scripts/templates/bc-options-controls.html",
        ROOT / "scripts/templates/bc-options-bootstrap.js", ROOT / "assets/plan_viewer.js", viewer.THREE_FILE,
        ROOT / "scripts/export_model_3d.py", ROOT / "scripts/lib/model3d_review.py",
        ROOT / "scripts/lib/model3d_placement.py", ROOT / "scripts/lib/model3d_plan.py", ROOT / "scripts/lib/model3d_tour.py",
        ROOT / "scripts/lib/model3d_openings.py", ROOT / "scripts/lib/model3d_mdf.py", ROOT / "scripts/lib/model3d_facade.py",
        ROOT / "house_design/b32_services.py", ROOT / "house_design/b32_service_detail.py", ROOT / "house_design/b32_daily_use.py",
        ROOT / "house_design/requirement_reconciliation.py", ROOT / "house_design/contracts.py",
        ROOT / "inputs/requirement-dispositions.json", ROOT / "structured/candidates/furniture-plans/layout.js",
        ROOT / "structured/candidates/c-integrated-options/layout.js"]]
    result = {"schema": "house-interior-improvements-review-v1", "revision": REVISION, "generated_at": utc_now(), "status": STATUS,
              "default_option": cfg["default_option"], "frame_mm": cfg["frame_mm"], "options": options,
              "owner_decisions": cfg["owner_decisions"], "professional_status": cfg["professional_status"],
              "source_hashes": {p: sha256_file(_public_path(root, p)) for p in sources_to_hash},
              "base_source_freshness": {s["id"]: s["source_freshness"] for s in fresh["scenarios"]},
              "generator_sha256": sha256_file(Path(__file__)), "rendered_qa": "not-run"}
    result["report_hash"] = stable_hash({k: v for k, v in result.items() if k != "generated_at"})
    return result


def render_index(study: dict) -> str:
    sections = []
    for o in study["options"]:
        figures = []
        for f in o["plans"]["floors"]:
            src = "interior-improvements/"+f["plan_file"]
            link = f"interior-improvements-3d.html?scheme={o['id']}#mode=tour&building={o['building']}&floor={f['id']}&view=plan"
            figures.append(f'<figure><figcaption>{html.escape(f["label"])} · <a href="{src}">另開SVG</a> · <a href="{html.escape(link, quote=True)}">同源3D</a></figcaption>'
                '<div data-plan-viewer data-source-width="6600" data-source-height="19030" data-readable-width="660">'
                '<div data-plan-controls hidden><button type="button" data-plan-action="in">放大</button> <button type="button" data-plan-action="out">縮小</button> '
                '<button type="button" data-plan-action="readable">讀字</button> <button type="button" data-plan-action="overview">整層</button></div>'
                '<p data-plan-state role="status">可另開SVG讀圖；展示不是工程比例。</p>'
                f'<div data-plan-viewport tabindex="0" aria-label="{html.escape(f["label"])}可捲動平面"><object data-plan-content type="image/svg+xml" data="{src}" aria-label="{html.escape(f["label"])}同源平面"><a href="{src}">開啟SVG</a></object></div>'
                '<p data-plan-error hidden>圖面未載入，請使用另開SVG；不算畫面驗收通過。</p></div></figure>')
        sections.append(f'<section id="{o["id"]}" data-option="{o["id"]}"><h2>{html.escape(o["label"])}</h2><p class="warning">比較未採用；原需求與未解項保留。</p><ul>'+
                        ''.join('<li>'+html.escape(n)+'</li>' for n in o["tradeoffs"])+"</ul>"+''.join(figures)+
                        '<details><summary>座標初篩與全部敏感度缺口（非核定）</summary><pre>'+html.escape(json.dumps(o["review"],ensure_ascii=False,indent=2))+'</pre></details></section>')
    template = (ROOT / "scripts/templates/c-integrated-options.html").read_text()
    start = template.index("<h1>")
    end = template.index("__OPTIONS__")
    intro = ('<h1>ABC室內改善比較 · 未採用</h1><p class="warning">v7：新增B小量晾衣／除濕使用比較，不搬房間或門窗；保留原八案。家務5.005m²無直接外窗，預排不等於工作陽台／排濕已核。祭祀占用時原公衛到達仍衝突，不藉暫停祭祀或上樓宣稱照護可用；獨立橫通道會壓縮家務至下限以下，改後右公衛／後左儲藏仍待決。A有窗公衛、C二樓單機及45cm／1.08m²已確認廚房取捨不改。這不是原主案；整套ABC、C樓高與專業仍未核可。</p>'
             '<nav aria-label="改善比較導航"><a href="interior-improvements-3d.html">同源3D</a>'+
             ''.join(f'<a href="#{o["id"]}">{html.escape(o["label"].replace("｜", " · "))}</a>' for o in study["options"])+
             '<a href="model3d.html">原ABC主案</a></nav><p>先讀取捨再看圖；所有門寬為名義，牆厚為假設，不靠縮家具或擴框消除缺口。</p>')
    for status, heading in (("confirmed-preference", "屋主已確認方向（整案與專業仍未核）"), ("pending", "保留待決，不自動採用")):
        intro += '<h2>'+heading+'</h2><ul>'+''.join(
            '<li data-decision="'+html.escape(d["id"])+ '" data-decision-status="'+status+'">'+html.escape(d["recommendation"])+ '</li>'
            for d in study["owner_decisions"] if d["status"] == status)+ '</ul>'
    template = template[:start]+intro+template[end:]
    template = template.replace("__OPTIONS__", "\n".join(sections)).replace('<title>C整合比較｜公衛・有窗客房・運動（未採用）</title>', '<title>ABC室內改善比較（未採用）</title>')
    template = template.replace("</style>", '[data-plan-viewport]{height:620px;overflow:auto;border:1px solid #cbd5ce;background:#fbfbf8} [data-plan-content]{display:block;max-width:none;border:0} [data-plan-controls] button{min-height:44px;padding:6px 12px} @media(max-width:640px){[data-plan-viewport]{height:500px}} [hidden]{display:none!important}</style>')
    return template.replace("</body>", '<script src="../../assets/plan_viewer.js"></script></body>')


def write_study(study: dict, root: Path = ROOT) -> dict:
    directory = root / OUT
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {**study, "options": [{k: v for k, v in o.items() if k != "model"} for o in study["options"]]}
    write_json(directory / "review.json", manifest)
    for o in study["options"]:
        for f in o["plans"]["floors"]:
            svg = ET.fromstring(render_plan(o["building"], f, viewer_url="../interior-improvements-3d.html?scheme="+o["id"]))
            svg.set("width", "660")
            svg.set("height", "1903")
            svg.set("data-improvement-option", o["id"])
            ET.SubElement(svg, "{http://www.w3.org/2000/svg}text", {"x": "0", "y": "-820", "font-size": "170"}).text = "室內改善比較未採用，原需求保留／專業未核"
            (directory / f["plan_file"]).write_text(ET.tostring(svg, encoding="unicode"), encoding="utf-8")
    index = root / "structured/candidates/interior-improvements.html"
    index.write_text(render_index(study), encoding="utf-8")
    controls = (ROOT / "scripts/templates/bc-options-controls.html").read_text().replace("bc-options.html", "interior-improvements.html").replace("B 家規／C 照護", "ABC室內改善").replace("B／C比較", "ABC室內改善比較")
    bootstrap = (ROOT / "scripts/templates/bc-options-bootstrap.js").read_text().replace("bc-options.html", "interior-improvements.html").replace("B 家規／C 照護", "ABC室內改善").replace('"bc-constraints"', '"interior-improvements"')
    data = {"bc_options": {"default_option": study["default_option"], "options": [
        {k: o[k] for k in ("id", "building", "label", "model")} for o in study["options"]]}}
    text = viewer.render_html(data, viewer.three_source()[0], study_controls=controls, study_bootstrap=bootstrap)
    marker = "    var hvac=features.hvac || {};"
    if text.count(marker) != 1:
        raise ContractError("Interior-only door-envelope renderer anchor changed; do not silently omit the review overlays")
    text = text.replace(marker, (ROOT / DOOR_ENVELOPES).read_text()+"\n"+marker)
    access_marker = '      if(features.access_pending){row("入口待配置",'
    if text.count(access_marker) != 1:
        raise ContractError("Interior access-warning anchor changed; retain the conditional-route limitations")
    text = text.replace(access_marker,
        '      if(features.access_pending && features.interior_entry_review){row("B條件式入口仍待核","本輪已有成對門位及基地內矩形試線，仍需經祭祀區。分時、門檻、真人轉彎、照護救援與門外權利未核；不是公共通行或消防核可。");}\n'
        '      if(features.access_pending && !features.interior_entry_review){row("入口待配置",')
    text = text.replace('htmlHref="bc-options.html#"', 'htmlHref="interior-improvements.html#"')
    path3d = root / "structured/candidates/interior-improvements-3d.html"
    path3d.write_text(text, encoding="utf-8")
    return {"index": str(index), "viewer": str(path3d), "report": str(directory / "review.json"), "options": len(study["options"])}


def main() -> None:
    protected = ["inputs/requirements.json", "inputs/physical-items.json", "inputs/concept-layout-review.json",
                 "inputs/b32-entry-options.json", "inputs/c-integrated-options.json",
                 "structured/candidates/model3d.html", "structured/candidates/b32-entry-options-3d.html",
                 "structured/candidates/c-integrated-options-3d.html", "inputs/revisions/R000/manifest.json",
                 "structured/architect_handoffs/R001/handoff-manifest.json"]
    before = {p: sha256_file(ROOT / p) for p in protected}
    study = build_study()
    paths = write_study(study)
    if before != {p: sha256_file(ROOT / p) for p in protected}:
        raise ContractError("A protected original changed")
    print(json.dumps({**paths, "report_hash": study["report_hash"], "rendered_qa": "not-run"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

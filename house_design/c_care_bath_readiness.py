"""Frozen-layout reach/selection preparation, never a new layout or care pass.

Small fixed case sets, exact translation unions and scalar directional budgets.
No scene, solver, network, parent generation or automatic product selection.
"""
from __future__ import annotations

import copy
import json
import math
import re
from datetime import datetime

from house_design.b32_rear_right import body, rect
from house_design.b32_service_detail import _inside, _route
from house_design.b32_services import _hits
from house_design.c_care_bath import component_box
from house_design.c_care_bath_door import pose, translation_sweeps
from house_design.c_care_bath_fit import STATUS, _source
from house_design.c_care_route import barriers
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, utc_now

SCHEMA, SOURCE = "house-c-care-bath-readiness-v1", "inputs/c-care-bath-readiness.json"
PRODUCT_SOURCE = "inputs/c-care-bath-products.json"
BASE_REPORT = "structured/candidates/c-care-bath-layout/review.json"
BASE_VIEWER = "structured/candidates/c-care-bath-layout-3d.html"
OUT = "structured/candidates/c-care-bath-readiness"
PRODUCT_FIELDS = {
    "bath-door": ("full_open_clear", "complete_pack", "rear_extent_from_nominal_aperture_end", "front_projection_from_nominal_aperture_start"),
    "basin": ("body_width", "body_depth", "top_height", "knee_clear_width", "knee_clear_height", "knee_clear_depth", "tap_control_from_front_edge", "supply_drain_outer_projection"),
    "fold-seat": ("open_width", "open_depth", "folded_projection_from_rear_finish"),
    "right-grab-rail": ("complete_projection_from_right_finish",),
}


def validate_config(cfg):
    expected = {"schema": SCHEMA, "revision": 1, "status": STATUS, "base_report": BASE_REPORT,
        "base_viewer": BASE_VIEWER, "base_option": "side-basin", "base_state": "open", "products_source": PRODUCT_SOURCE,
        "base_plan_hash": "59aa1ccee2455b9d3ab0f7c0360d2f3ec2bea992576a91457884c7b71ab57640",
        "body_mm": [900, 900], "inset_each_face_mm": 115, "required_clear_mm": 900, "optional_discussion_margin_mm": 30,
        "arrival_offsets_mm": [0, 150, 200, 217.5, 230, 247.5, 250],
        "basin_and_door_rear_shift_trials_mm": [0, 150, 200, 217.5, 247.5], "board_center_x_trials_mm": [4850, 4830]}
    if (any(cfg.get(k) != value for k, value in expected.items()) or not cfg.get("authorization")
            or not cfg.get("limits") or set(cfg.get("professional_status", {}).values()) != {"unknown"}):
        raise ContractError("Keep frozen basis, explicit bounded trials and original care/product targets")


def frozen_layout(root=ROOT):
    report = read_json(root / BASE_REPORT)
    if (report.get("schema") != "house-c-care-bath-layout-v1" or report.get("layout_display_revision") != 1
            or report.get("adopted") is not False or report.get("status") != STATUS
            or not report.get("source_hashes") or not report.get("report_hash")):
        raise ContractError("Missing frozen side-basin report")
    for name, digest in report["source_hashes"].items():
        source = _source(root, name)
        if not source.is_file() or sha256_file(source) != digest:
            raise ContractError("Stale frozen side-basin source: "+name)
    raw = re.search(r"^\s*var DATA = (.+);\s*$", (root / BASE_VIEWER).read_text(encoding="utf-8"), re.M)
    if raw is None:
        raise ContractError("Missing frozen side-basin viewer data")
    payload = json.loads(raw[1]).get("c_care_bath_layout", {})
    models = {(o["id"], s["id"]): s["model"] for o in payload.get("options", []) for s in o["states"]}
    reconstructed = copy.deepcopy(report)
    for option in reconstructed["options"]:
        for state in option["states"]:
            model = models.get((option["id"], state["id"]))
            if not model or model["bc_option"]["geometry_review"] != state["review"]:
                raise ContractError("Missing/mixed frozen side-basin model/review")
            state["model"] = model
            for floor in state["plans"]["floors"]:
                actual = next(f for f in model["buildings"][0]["floors"] if f["id"] == floor["id"])
                cells = {c["id"]: c for c in actual["cells"] if c["tour_active"]}
                if len(cells) != len(floor["rooms"]):
                    raise ContractError("Incomplete frozen side-basin floor")
                for room in floor["rooms"]:
                    c = cells[room["id"]]
                    items = [{**i, "placement": c["furniture_placements"]["tour_mm"][i["id"]]} for i in c["furniture"]]
                    if c["tour_mm"] != room["geometry"] or c["tour_features"] != room["features"] or items != room["furniture"]:
                        raise ContractError("Frozen side-basin HTML/3D mismatch")
    if report["report_hash"] != stable_hash({k: v for k, v in reconstructed.items() if k not in {"report_hash", "generated_at"}}):
        raise ContractError("Frozen side-basin report/viewer self-hash mismatch")
    option = next(o for o in reconstructed["options"] if o["id"] == "side-basin")
    return report, option


def context(state):
    rooms = {r["key"]: r for r in state["plans"]["floors"][0]["rooms"]}
    bath = rooms["elder-bath"]
    fixtures = [{"id": i["id"], "rect_mm": body(i)} for key in ("elder", "elder-bath") for i in rooms[key]["furniture"]
                if i["shape"] != "wall-tv" and not i.get("care_bath_open_shower")]
    hardware = [{"id": p["id"], "rect_mm": component_box(p)[:4]} for p in bath["features"]["care_bath_components"] if not p.get("flush_floor_only")]
    leaves = [{"id": p["id"], "rect_mm": p["rect_mm"]} for key in ("elder", "elder-bath") for p in rooms[key]["features"].get("care_entry_leaves", [])]
    parts = [{"id": p["id"], "rect_mm": p["rect_mm"]} for p in bath["features"]["care_door_parts"]]
    walls = [p for key in ("elder", "elder-bath") for p in barriers(rooms[key])]
    vanity = next(i for i in bath["furniture"] if i["shape"] == "vanity")
    return {"rooms": rooms, "bath": bath, "vanity": vanity, "fixtures": fixtures, "hardware": hardware,
        "floor_obstacles": fixtures+hardware+leaves+parts, "obstacles": fixtures+hardware+leaves+parts+walls,
        "areas": [rect(rooms[k]) for k in ("elder", "elder-bath")]}


def arrival_study(state, cfg):
    c, detail = context(state), state["review"]["layout"]
    v, half = body(c["vanity"]), cfg["body_mm"][1]/2
    arm = next(p["rect_mm"] for p in c["hardware"] if p["id"] == "toilet-arm")
    center_y = v[1]+v[3]/2
    cases = []
    for offset in cfg["arrival_offsets_mm"]:
        points = copy.deepcopy(detail["routes"]["vanity-front"]["points_mm"])
        points[-1][1] = center_y+offset
        route = _route(points, *cfg["body_mm"], c["areas"], c["obstacles"], 115)
        cases.append({"offset_mm": offset, "route": route, "front_finish_spare_mm": center_y+offset-half-(rect(c["bath"])[1]+115),
            "raised_arm_directional_spare_mm": center_y+offset-half-arm[1]-arm[3], "seated_reach_acceptance": "unknown"})
    min_offset = max(rect(c["bath"])[1]+115, arm[1]+arm[3])+half-center_y
    return {"scope": "固定目前x=4665mm與盆前50mm距離，僅沿y比較；不是全室所有姿勢的最小偏側。",
        "cases": cases, "minimum_offset_zero_spare_mm": min_offset,
        "minimum_offset_for_optional_margin_mm": min_offset+cfg["optional_discussion_margin_mm"],
        "current_offset_mm": detail["basin_arrival_lateral_offset_mm"],
        "recommendation": "保留250mm作足尺驗證，不為降低偏側而把扶手旁32.5mm再壓薄；不能據此認定坐姿可及。"}


def rear_shift_study(state, cfg, parent_door):
    c, d = context(state), state["review"]["layout"]
    original = body(c["vanity"])
    result = []
    for shift in cfg["basin_and_door_rear_shift_trials_mm"]:
        v, door_cfg = original.copy(), copy.deepcopy(parent_door)
        v[1] += shift
        door_cfg["center_y_mm"] = d["door_center_y_mm"]+shift
        leaves, parts = pose(door_cfg, "two-panel", "open")
        fixed = [p for p in c["fixtures"] if p["id"] != c["vanity"]["id"]]+[{"id": c["vanity"]["id"], "rect_mm": v}]
        arrival = [d["basin_arrival_rect_mm"][0], v[1]+v[3]/2-450, 900, 900]
        failures = ([] if _inside(arrival, [rect(c["bath"])], 115) else ["outside-assumed-bath"])+[
            "hits-"+p["id"] for p in fixed+c["hardware"] if _hits(arrival, p["rect_mm"])]
        rear_spare = sum(rect(c["bath"])[1::2])-115-sum(parts[0]["rect_mm"][1::2])
        conflicts = [s["id"]+":hits-"+p["id"] for s in translation_sweeps(door_cfg, "two-panel") for p in fixed+c["hardware"] if _hits(s["rect_mm"], p["rect_mm"])]
        result.append({"rear_shift_mm": shift, "hypothetical_vanity_rect_mm": v, "hypothetical_door_center_y_mm": door_cfg["center_y_mm"],
            "centered_arrival_rect_mm": arrival, "centered_arrival_coordinate_failures": failures,
            "rear_spare_after_existing_stop_mm": rear_spare, "door_sweep_fixed_conflicts": conflicts,
            "named_station_and_parking_budgets_clear": not failures and rear_spare >= 0 and not conflicts,
            "full_route_paired_aperture_and_care": "not-evaluated-no-layout-generated", "adopted": False})
    lower = arrival_study(state, cfg)["minimum_offset_zero_spare_mm"]
    upper = d["rear_parking_after_20mm_stop_mm"]
    return {"scope": "只比較盆與門同量後移，置中靜止矩形及完整門片平移預算；不是完整重排或全室不可行證明。",
        "cases": result, "continuous_shift_bounds_mm": {"minimum_for_current_centered_body": lower,
            "maximum_for_nonnegative_stop_parking": upper, "shortfall_mm": max(0, lower-upper),
            "nonnegative_budget_interval": [lower, upper] if lower <= upper else None},
        "recommendation": "不採只後移盆／門作解法；保留現版，先驗真人可及與完整商品，必要時另立整合重排。"}


def board_trial_study(option, cfg):
    opened = next(s for s in option["states"] if s["id"] == "open")
    c, d = context(opened), opened["review"]["layout"]
    old = d["rescue_board_rotation_mm"]
    half = old[2]/2
    left_edge = max(p["rect_mm"][0]+p["rect_mm"][2] for p in c["bath"]["features"]["care_entry_leaves"]+c["bath"]["features"]["care_door_parts"])
    right_edge = next(p["rect_mm"][0] for p in c["hardware"] if p["id"] == "shower-wall-grab")
    balanced = (left_edge+right_edge)/2
    cases = []
    for cx in [*cfg["board_center_x_trials_mm"], balanced]:
        square = [cx-half, old[1], old[2], old[3]]
        states = []
        for state in option["states"]:
            ctx = context(state)
            points = copy.deepcopy(d["rescue_board_translation"]["points_mm"])
            for point in points[1:]:
                point[0] = cx
            route = _route(points, *d["rescue_board_translation"]["body_mm"], ctx["areas"], ctx["obstacles"], 115)
            failures = ([] if _inside(square, [rect(ctx["bath"])], 115) else ["outside-assumed-bath"])+[
                "hits-"+p["id"] for p in ctx["floor_obstacles"] if _hits(square, p["rect_mm"])]
            states.append({"state": state["id"], "translation": route, "rotation_coordinate_failures": failures})
        cases.append({"center_x_mm": cx, "rotation_square_mm": square, "left_door_pack_spare_mm": square[0]-left_edge,
            "right_rail_spare_mm": right_edge-square[0]-square[2], "states": states, "adopted": False,
            "scope": "僅移剛性板討論標示，不移門、扶手或任何設備；非人員／救援演練。"})
    margin = cfg["optional_discussion_margin_mm"]
    return {"cases": cases, "balanced_center_x_mm": balanced,
        "center_interval_for_optional_margin_mm": [left_edge+half+margin, right_edge-half-margin],
        "geometry_changed": False, "recommendation": "若繼續深化圖面，可先比試點左移20mm；目前僅數值研究，未更新HTML／3D，不能假稱原圖餘量已改善。"}


def product_budgets(state, cfg):
    c, d = context(state), state["review"]["layout"]
    x, y, w, h = rect(c["bath"])
    left, rear, right = x+115, y+h-115, x+w-115
    margin = cfg["optional_discussion_margin_mm"]
    door_start, door_end = d["door_center_y_mm"]-600, d["door_center_y_mm"]+600
    vanity, square = body(c["vanity"]), d["rescue_board_rotation_mm"]
    seat = next(p for p in c["hardware"] if p["id"] == "fold-seat")
    rail = next(p for p in c["hardware"] if p["id"] == "shower-wall-grab")
    specs = [
        ("bath-door", "full_open_clear", "min", 900, None, d["effective_width_assumption_mm"], "實際全開含框／把手淨寬；970只是討論扣框值。"),
        ("bath-door", "complete_pack", "max", d["turn_reserve_mm"][0]-left, d["turn_reserve_mm"][0]-left-margin, 130, "含軌、門片、把手、基座及施工安裝的完整向室內外凸，不只兩片厚度。"),
        ("bath-door", "rear_extent_from_nominal_aperture_end", "max", rear-door_end, rear-door_end-margin, rear-door_end-d["rear_parking_after_20mm_stop_mm"], "由名義洞口後緣向後量，含全開門尾、止擋及檢修；現有20mm已計入，不能又扣一次。"),
        ("bath-door", "front_projection_from_nominal_aperture_start", "max", door_start-vanity[1]-vanity[3], door_start-vanity[1]-vanity[3]-margin, 30, "整個連動行程最前凸出名義洞口前緣的距離，須含五金／把手。"),
        ("fold-seat", "folded_projection_from_rear_finish", "max", rear-square[1]-square[3], rear-square[1]-square[3]-margin, rear-seat["rect_mm"][1], "折起整件含鉸座、背板、安裝離牆等最前外凸，不是只填45mm座板厚。"),
        ("right-grab-rail", "complete_projection_from_right_finish", "max", right-square[0]-square[2], right-square[0]-square[2]-margin, right-rail["rect_mm"][0], "由完成右牆至整件最內側，含底座／離牆握持；不能把35mm管徑當整件外凸。"),
    ]
    return [{"product": product, "field": field, "direction": direction, "zero_spare_boundary_mm": boundary,
        "max_for_optional_margin_mm": optional, "current_discussion_value_mm": current,
        "current_directional_spare_mm": boundary-current if direction == "max" else current-boundary,
        "measurement_definition": note, "approval": "unknown"} for product, field, direction, boundary, optional, current, note in specs]


def product_responses(root, responses, budgets):
    if (responses.get("schema") != "house-c-care-bath-product-responses-v1" or responses.get("revision") != 1
            or responses.get("status") != "unselected-no-verified-product-or-care-approval"
            or [p.get("id") for p in responses.get("products", [])] != list(PRODUCT_FIELDS)):
        raise ContractError("Keep the four explicit unselected product responses")
    result, sources = [], set()
    for product in responses["products"]:
        pid, facts = product["id"], product.get("facts_mm", {})
        if (set(product) != {"id", "manufacturer", "model", "facts_mm", "evidence"}
                or set(facts) != set(PRODUCT_FIELDS[pid]) or not isinstance(product.get("evidence"), list) or len(product["evidence"]) > 8):
            raise ContractError("Only explicit product fields and bounded evidence are supported")
        for value in facts.values():
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 10000):
                raise ContractError("Product facts must be null or bounded finite nonnegative millimetres")
        issues = []
        if any(not isinstance(product.get(k), str) or not product[k].strip() for k in ("manufacturer", "model")):
            issues.append("missing-manufacturer-or-model")
        if not product["evidence"]:
            issues.append("missing-traceable-document")
        for evidence in product["evidence"]:
            if not isinstance(evidence, dict) or any(not isinstance(evidence.get(k), str) or not evidence[k].strip()
                for k in ("document", "sha256", "revision", "checked_by", "checked_at")):
                issues.append("incomplete-document-check-record")
                continue
            try:
                datetime.fromisoformat(evidence["checked_at"].replace("Z", "+00:00"))
            except ValueError:
                issues.append("invalid-check-date")
            if not re.fullmatch(r"[a-f0-9]{64}", evidence["sha256"]):
                issues.append("invalid-document-hash")
                continue
            if not evidence["document"].startswith(("inputs/references/", "assets/references/", "Docs/")):
                raise ContractError("Product evidence must be a project reference document, not a private/configuration path")
            source = _source(root, evidence["document"])
            if not source.is_file():
                issues.append("document-not-readable")
            elif source.stat().st_size > 20_000_000:
                issues.append("document-too-large-for-bounded-check")
            elif sha256_file(source) != evidence["sha256"]:
                issues.append("document-hash-mismatch")
            else:
                sources.add(evidence["document"])
        scalar = []
        for budget in [b for b in budgets if b["product"] == pid]:
            value = None if issues else facts[budget["field"]]
            spare = None if value is None else budget["zero_spare_boundary_mm"]-value if budget["direction"] == "max" else value-budget["zero_spare_boundary_mm"]
            scalar.append({"field": budget["field"], "provided_value_mm": facts[budget["field"]], "evidence_backed_value_mm": value,
                "directional_spare_mm": spare, "status": "unknown" if spare is None else "outside-this-scalar-budget" if spare < 0 else "zero-spare-not-approved" if spare == 0 else "inside-this-scalar-budget-not-approved"})
        result.append({"id": pid, "manufacturer": product["manufacturer"], "model": product["model"], "evidence_issues": issues,
            "facts_mm": facts, "evidence": product["evidence"], "scalar_checks": scalar,
            "status": "unknown" if issues or any(v is None for v in facts.values()) else "needs-complete-model-and-professional-review",
            "selected": False, "product_or_care_approval": "unknown", "knee_clearance_credit_mm": 0})
    return result, sources


def build_study(root=ROOT):
    cfg = read_json(root / SOURCE)
    validate_config(cfg)
    parent, option = frozen_layout(root)
    state = next(s for s in option["states"] if s["id"] == "open")
    if stable_hash(state["plans"]) != cfg["base_plan_hash"]:
        raise ContractError("Frozen side-basin geometry changed; do not reuse these readiness conclusions")
    budgets = product_budgets(state, cfg)
    discussion_facts = {pid: dict.fromkeys(fields) for pid, fields in PRODUCT_FIELDS.items()}
    for budget in budgets:
        discussion_facts[budget["product"]][budget["field"]] = budget["current_discussion_value_mm"]
    basin = context(state)["vanity"]
    discussion_facts["basin"].update(body_width=basin["width_mm"], body_depth=basin["depth_mm"], top_height=basin["height_mm"])
    seat = read_json(root / "inputs/c-care-bath.json")["seat"]
    discussion_facts["fold-seat"].update(open_width=seat["width_mm"], open_depth=seat["depth_mm"])
    products, evidence_sources = product_responses(root, read_json(root / PRODUCT_SOURCE), budgets)
    paths = {SOURCE, PRODUCT_SOURCE, BASE_REPORT, BASE_VIEWER, "house_design/c_care_bath_readiness.py",
        "scripts/export_c_care_bath_readiness.py", *parent["source_hashes"], *evidence_sources}
    result = {"schema": SCHEMA, "revision": 1, "generated_at": utc_now(), "status": STATUS, "adopted": False,
        "geometry_changed": False, "new_viewer_generated": False, "base_option": "side-basin", "base_state": "open",
        "base_report_hash": parent["report_hash"], "base_plan_hash": stable_hash(state["plans"]),
        "optional_discussion_margin_mm": 30, "professional_status": cfg["professional_status"], "limits": cfg["limits"],
        "arrival": arrival_study(state, cfg), "basin_and_door_rear_shift": rear_shift_study(state, cfg, read_json(root / "inputs/c-care-bath-door.json")),
        "board_trials": board_trial_study(option, cfg), "product_budgets": budgets, "product_responses": products,
        "discussion_product_facts_mm": discussion_facts,
        "seated_mockup_acceptance": "unknown-no-person-chair-or-trial-record", "construction_release": False,
        "source_hashes": {p: sha256_file(_source(root, p)) for p in sorted(paths)}}
    result["report_hash"] = stable_hash({k: v for k, v in result.items() if k != "generated_at"})
    return result

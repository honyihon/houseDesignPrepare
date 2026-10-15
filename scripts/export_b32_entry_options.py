#!/usr/bin/env python3
"""B32 rear-entry priority and front-entry fallback, isolated from ABC main.

One computed model owns SVG/HTML/3D. A hypothetical rear opening never proves
an alley, land right, assembled transport, or professional approval.
"""
from __future__ import annotations

import copy
import html
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET

import export_model_3d as model3d
import export_preparation_review as shared
from lib.dimension_overrides import load_overrides
from lib.model3d_facade import build_facade
from lib.model3d_placement import overlaps
from lib.model3d_plan import plan_data, render_plan

from house_design.physical_items import load_physical_items
from house_design.rendering import encode_html_json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "inputs/b32-entry-options.json"
OUT = ROOT / "structured/candidates"
STATUS = "comparison-only-not-adopted"
IDS = ["b32-rear", "b32-front"]
DISPLAY_REVISION = 2
NS = "http://www.w3.org/2000/svg"
PROTECTED = [*shared.PROTECTED,
             "inputs/preparation-review.json", "inputs/bc-constraints-options.json",
             "structured/candidates/preparation-review.html", "structured/candidates/preparation-review-3d.html",
             "structured/candidates/preparation-review/layout.js"]


def validate_settings(s: dict) -> None:
    if (s.get("schema") != "house-b32-entry-options-v1" or s.get("revision") != 1
            or s.get("status") != STATUS or s.get("active_design") != "baseline"
            or s.get("default_option") != IDS[0] or [o["id"] for o in s["options"]] != IDS):
        raise ValueError("B32 is two isolated comparisons, not an adoption")
    w, d = s["frame_mm"]
    if s["land_cap_ping"] != 32 or w * d / 1e6 > 32 * (400 / 121):
        raise ValueError("B32 may not exceed 32 land ping")
    if (s["frame_mm"] != [6000, 17630] or s["frontage_depth_mm"] != 3900
            or s["discussion_inset_mm"] != 80 or s["storey_heights_mm"] != [4000, 3000, 3000, 3000]):
        raise ValueError("Changed frame, level or inset requires a coordinated rearrangement")
    if (set(s["professional_status"]) != {"site", "structure_fire", "accessibility", "religious_acceptance", "plumbing_hvac", "transport", "budget"}
            or set(s["access_evidence"]) != {"rear_route_exists", "rear_route_rights", "rear_opening_permission", "rear_route_clear_dimensions_levels", "rear_turn_staging_people_rehearsal"}):
        raise ValueError("B32 must retain every professional and rear access evidence gate")
    if any(v != "unknown" for v in s["professional_status"].values()) or any(
            v != {"status": "unknown", "value": None, "source": None} for v in s["access_evidence"].values()):
        raise ValueError("This hypothetical study cannot certify a rear alley or a profession")
    for o, mode, reserve in zip(s["options"], ("rear", "front"), (1200, 1520), strict=True):
        if o["entry_mode"] != mode or o["pedestrian_reserve_clear_mm"] != reserve:
            raise ValueError("Entry-mode and area-reserve contract differ")
    if s["options"][0]["rear_gate_nominal_mm"] - 160 < 1800:
        raise ValueError("Rear gate loses its unverified 1800mm discussion target")
    for fid, pair in [("floor-1", ("shrine-front", "shrine")), ("floor-1", ("bath1", "bath-extension")),
                      ("floor-2", ("living2-front", "living2")), ("floor-3", ("quiet-study-front", "quiet-study"))]:
        floor = s["floors"][fid]
        if (floor["rooms"][pair[0]].get("group") != floor["rooms"][pair[1]].get("group")
                or not any(set(c[:2]) == set(pair) and c[2] == "open" for c in floor["connections"])):
            raise ValueError("L-shaped area requires a full open seam, not an invented extra room")


def profiles(furniture: dict) -> None:
    products = {
        "b32-shrine": [("altar", "altar-table"), ("offering", "folding-offering-table"),
                       ("bench-1", "movable-bench"), ("bench-2", "movable-bench")],
        "b32-backing": [("cabinet", "ritual-cabinet")],
        "b32-bath1": [("shower", "shower-accessible"), ("toilet", "toilet"), ("basin", "vanity-60")],
        "b32-storage": [("ceremonal", "ceremonial-storage")],
        "b32-living": [("sofa", "sofa-2"), ("tv", "wall-tv"), ("table", "coffee-table")],
        "b32-public-bath": [("basin", "vanity-60"), ("toilet", "toilet"), ("shower", "shower-90")],
        "b32-ensuite": [("shower", "shower-90"), ("basin", "vanity-90"), ("toilet", "toilet")],
        "b32-bedroom": [("bed", "double-bed"), ("wardrobe", "wardrobe-180"), ("vanity", "vanity-desk")],
    }
    for key, values in products.items():
        furniture["profiles"][key] = shared.profile(*values)
        for item in furniture["profiles"][key]:
            if item["catalog"] == "movable-bench":
                item["front_clearance_mm"] = 300
            if item["catalog"] == "ritual-cabinet":
                item["front_clearance_mm"] = 600
            if item["catalog"] == "wall-tv":
                item["mount_height_mm"] = 1400
            if item["catalog"] in {"toilet", "vanity-60", "vanity-90", "shower-accessible", "shower-90", "wardrobe-180", "ritual-cabinet"}:
                item["shared_operation_with"] = ["door-approach"]
                if item["catalog"] == "shower-accessible":
                    item["shared_operation_with"].append("care-turn")
                item["shared_operation_mode"] = "sequential-only-not-verified"
                item["note"] += " 取物／衛浴與進出分時，非同時使用或救援核可。"


def raw_proposal(settings: dict, option: dict) -> tuple[dict, dict]:
    raw, furniture, old = shared.source_review()
    original = next(o for o in old["options"] if o["id"] == "b-strict")["patch"]["replace_building"]
    b = raw["buildings"]["B"] = copy.deepcopy(original)
    raw["id"], raw["frame_mm"] = "b32-entry-options-v1", settings["frame_mm"]
    b.pop("ritual_access", None)
    b["core"] = copy.deepcopy(settings["core"])
    b["storey_heights_mm"] = settings["storey_heights_mm"]
    b["floors"] = copy.deepcopy(settings["floors"])
    b["summary"] = option["label"]
    b["assumptions"] = ["只畫基地內幾何；後方道路、巷道、通行權及門外轉向未知。",
                        "32地坪是上限，不是每層可建32坪。80mm只是討論內縮。"]
    b["deferred"] = [{"floor": "floor-1", "key": "parking", "note": settings["unresolved"][0]}]
    b["hvac_pairs"] = [["floor-1", "shrine-front", "floor-2", "balcony2", "front"],
                       ["floor-2", "living2-front", "floor-2", "balcony2", "front"],
                       ["floor-2", "master2", "floor-4", "service-rf", "rear"],
                       ["floor-3", "guest3", "floor-4", "service-rf", "rear"]]
    first = b["floors"]["floor-1"]
    if option["entry_mode"] == "rear":
        first["additional_entries"].append(["storage", "rear", option["rear_gate_nominal_mm"], option["rear_gate_center_mm"]])
    # Full-width open seams, not a wall splitting either L-shaped room.
    first["rooms"]["shrine-front"]["clearance_reservations"] = [
        {"kind": "ritual-approach", "rect": [100, 1800, 1800, 3400]},
        {"kind": "circulation", "rect": [3600 - 80 - option["pedestrian_reserve_clear_mm"], 80,
                                            option["pedestrian_reserve_clear_mm"], 5120]},
    ]
    first["rooms"]["shrine"]["clearance_reservations"] = [
        {"kind": "ritual-approach", "rect": [2500, 0, 1800, 790]},
        {"kind": "circulation", "rect": [6000 - 80 - option["pedestrian_reserve_clear_mm"], 0,
                                            option["pedestrian_reserve_clear_mm"], 2190]},
    ]
    profiles(furniture)
    return raw, furniture


def place_products(building: dict, option: dict, source: dict) -> None:
    first = {c["key"]: c for c in building["floors"][0]["cells"] if c.get("tour_active")}
    for c in first.values():
        if c.get("space_group") == "b32-bath1":
            c["color"] = "#3fb6c8"  # one L-shaped bathroom, not two rooms
    specs = {
        "shrine": [("altar", [2500, 10690, 1800, 600], 0, "rear"),
                   ("offering", [2800, 9970, 1200, 500], 0, ""),
                   ("bench-1", [80, 9180, 450, 1400], 270, "left"),
                   ("bench-2", [900, 9800, 1400, 450], 0, "")],
        "altar-backing": [("cabinet", [2580, 11450, 450, 1200], 270, "left")],
        "bath1": [("shower", [80, 11450, 1200, 1200], 180, "front"),
                  ("toilet", [1700, 11450, 450, 700], 180, "front"),
                  ("basin", [1800, 13800, 600, 450], 0, "rear")],
    }
    for key, values in specs.items():
        for local, bounds, rotation, anchor in values:
            shared.set_product(first[key], local, bounds, rotation, anchor)
    for i in first["bath1"]["furniture"]:
        i["shared_operation_with"] = ["care-turn", "door-approach"]
    first["bath1"]["tour_features"]["reserved_mm"].append(
        {"kind": "care-turn", "aabb": shared.box(shared.rect(80, 12750, 1500, 1500)), "status": "not-rehearsed"})
    x, y = option["palanquin_body_origin_mm"]
    dims = source["active_dimensions"]
    shared.set_product(first["storage"], "ceremonal", [x, y, dims["width_mm"], dims["depth_mm"]], 0)
    for index, living, pub, ens, bed in [(1, "living2-front", "bath2", "master-bath2", "master2"),
                                        (2, "quiet-study-front", "bath3", None, "guest3")]:
        rooms = {c["key"]: c for c in building["floors"][index]["cells"] if c.get("tour_active")}
        values = {
            living: [("sofa", [5020, 5700, 900, 1800], 90, "right"),
                     ("tv", [2480, 6200, 80, 1000], 270, "left"),
                     ("table", [3600, 6050, 600, 1100], 90, "")],
            pub: [("basin", [1280, 11450, 450, 600], 270, "left"),
                  ("toilet", [2580, 11470, 700, 450], 90, "right"),
                  ("shower", [2380, 13060, 900, 900], 0, "rear")],
            ens: [("shower", [3440, 11450, 900, 900], 180, "front"),
                  ("basin", [4950, 11450, 900, 550], 180, "front"),
                  ("toilet", [5220, 12710, 700, 450], 90, "right")],
            bed: [("bed", [80, 15100, 2000, 1800], 270, "left"),
                  ("wardrobe", [5320, 14900, 600, 1800], 90, "right"),
                  ("vanity", [2400, 14120, 1200, 500], 180, "front")],
        }
        for key, items in values.items():
            if key is None:
                continue
            for local, bounds, rotation, anchor in items:
                shared.set_product(rooms[key], local, bounds, rotation, anchor)
    # External entries are purpose-labelled on this computed model only.
    gate = next(d for d in first["shrine-front"]["tour_features"]["doors"] if d["neighbor"] is None)
    gate["purpose"] = "ritual-entry"
    if option["entry_mode"] == "rear":
        gate = next(d for d in first["storage"]["tour_features"]["doors"] if d["neighbor"] is None)
        gate.update(purpose="rear-palanquin-entry", operation="unconfirmed",
                    label=f"後門{gate['width_mm']/10:g}cm名義／{(gate['width_mm']-160)/10:g}cm討論淨寬；後巷未核")


def inset_area(rooms: list[dict], inset: int) -> float:
    """Inset an orthogonal union without double-counting its open grid seam.

Axis-aligned square erosion; exact at our orthogonal discussion coordinates.
No dependency on a geometric/legal CAD solver and no measured-wall claim.
"""
    gs = [r["tour_mm"] for r in rooms]
    xs = sorted({x for g in gs for edge in (g["x_mm"], g["x_mm"] + g["w_mm"]) for x in (edge-inset, edge+inset)})
    ys = sorted({y for g in gs for edge in (g["y_mm"], g["y_mm"] + g["h_mm"]) for y in (edge-inset, edge+inset)})
    total = 0
    for left, right in zip(xs, xs[1:], strict=False):
        for front, rear in zip(ys, ys[1:], strict=False):
            cx, cy = (left + right) / 2, (front + rear) / 2
            square = {"minX": cx-inset, "maxX": cx+inset, "minY": cy-inset, "maxY": cy+inset}
            if shared.union_covers(square, rooms):
                total += (right-left) * (rear-front)
    return round(total / 1e6, 4)


def transport(building: dict, option: dict, physical: dict) -> dict:
    cells = {c["key"]: c for c in building["floors"][0]["cells"] if c.get("tour_active")}
    w, d = [physical["active_dimensions"][key] for key in ("width_mm", "depth_mm")]
    px, py = option["palanquin_body_origin_mm"]
    route = []

    def segment(key: str, start: list, end: list, label: str) -> None:
        bounds = {"minX": min(start[0], end[0])-w/2, "maxX": max(start[0], end[0])+w/2,
                  "minY": min(start[1], end[1])-d/2, "maxY": max(start[1], end[1])+d/2}
        value = {"id": option["id"] + "-step-" + str(len(route) + 1),
                 "room_id": cells[key]["id"], "centerline_mm": [start, end], "body_sweep_mm": bounds,
                 "label": label, "method": "translation-no-rotation", "includes_people_poles": False}
        route.append(value)
        cells[key]["tour_features"].setdefault("b32_transport_segments", []).append(value)

    if option["entry_mode"] == "rear":
        axis = option["rear_gate_center_mm"]
        segment("storage", [axis, 17630+d/2], [axis, py+d/2], "後門直進本體試排／門外未核")
        segment("storage", [axis, py+d/2], [px+w/2, py+d/2], "室內橫移收納／裝桿人員未核")
        # Clip only the outside part; do not invent rear land or alley width.
        route[0]["centerline_mm"][0][1] = 17630
        route[0]["body_sweep_mm"]["maxY"] = 17630
        gates = [(cells["storage"], next(g for g in cells["storage"]["tour_features"]["doors"] if g["neighbor"] is None))]
    else:
        axis, staged_y, target_axis = 3400, 6550, px+w/2
        segment("shrine-front", [axis, 3900-d/2], [axis, staged_y], "共用正門直進／祭祀搬運分時")
        route[0]["centerline_mm"][0][1] = 3900
        route[0]["body_sweep_mm"]["minY"] = 3900
        segment("shrine-front", [axis, staged_y], [target_axis, staged_y], "前廳橫移至側緣／人員未核")
        segment("shrine-front", [target_axis, staged_y], [target_axis, 9100], "前廳側緣直送本體試排")
        segment("shrine", [target_axis, 9100], [target_axis, 11370], "祭拜區側緣／分時搬運")
        segment("corridor1", [target_axis, 11370], [target_axis, 14330], "後段直送／浴室操作分時")
        segment("storage", [target_axis, 14330], [target_axis, py+d/2], "儲藏室前門直進本體試排")
        # Cross-room sweeps are checked as one route, not artificially cut at
        # every room seam (which would omit the front/rear half of the body).
        gates = [(cells["shrine-front"], next(g for g in cells["shrine-front"]["tour_features"]["doors"] if g["neighbor"] is None)),
                 (cells["storage"], next(g for g in cells["storage"]["tour_features"]["doors"] if g.get("purpose") == "palanquin-storage"))]
    allowed = [cells[k] for k in (["storage"] if option["entry_mode"] == "rear" else ["shrine-front", "shrine", "corridor1", "storage"])]
    moving_id = next(i["id"] for i in cells["storage"]["furniture"] if i.get("physical_item_id") == physical["id"])
    for part in route:
        bounds = part["body_sweep_mm"]
        if not shared.union_covers(bounds, allowed) or any(overlaps(bounds, wall) for c in allowed for wall in shared.wall_strips(c)):
            raise ValueError("B32 transport sweep crosses a wall or leaves this option")
        for cell in allowed:
            for item in cell["furniture"]:
                if item["id"] != moving_id and overlaps(bounds, cell["furniture_placements"]["tour_mm"][item["id"]]["aabb"]):
                    raise ValueError("B32 transport sweep hits a fixed body")
    gate_budgets = [{"room_id": c["id"], "face": g["face"], "nominal_mm": g["width_mm"],
                     "assumed_frame_each_side_mm": 80, "discussion_clear_mm": g["width_mm"] - 160,
                     "finished_clear_mm": None} for c, g in gates]
    if any(g["discussion_clear_mm"] < physical["transport"]["door_clear_target_mm"] for g in gate_budgets):
        raise ValueError("B32 entry discussion gate budget below inventory target")
    return {"status": "storage-body-sweep-only-not-transport-approval", "entry_mode": option["entry_mode"],
            "physical_item_id": physical["id"], "storage_dimensions": physical["active_dimensions"],
            "storage_dimension_source": physical["active_dimension_source"], "segments": route,
            "gate_budgets": gate_budgets, "assembled_measurement": physical["transport"]["assembled_measurement"],
            "route_rehearsal": physical["transport"]["route_rehearsal"], "people_poles_wheels_rain": "unknown",
            "outdoor_approach": "unknown-not-drawn", "acceptance": "unknown",
            "ritual_carry_use": "time-separated", "front_backup_in_rear_model": "not-claimed-use-separate-front-option"}


def program_screen(building: dict, option: dict, physical: dict) -> dict:
    cells = {c["id"]: c for f in building["floors"] for c in f["cells"] if c.get("tour_active")}
    first = {c["key"]: c for c in building["floors"][0]["cells"] if c.get("tour_active")}
    shrine = [first[k] for k in ("shrine-front", "shrine")]
    altar = first["shrine"]["furniture_placements"]["tour_mm"]["B:floor-1:shrine:furniture:altar"]
    gate = next(d for d in first["shrine-front"]["tour_features"]["doors"] if d.get("purpose") == "ritual-entry")
    axis = shared.box(shared.rect(altar["aabb"]["minX"], 11370, 1800, 6260))
    stairs_behind = [c["id"] for c in first.values() if (c["kind"] == "stair" or c.get("space_role") == "circulation") and overlaps(shared.box(c["tour_mm"]), axis)]
    above = [c["id"] for c in cells.values() if not c["id"].startswith("B:floor-1:") and
             (c["kind"] in {"bedroom", "bath", "kitchen", "stair"} or any(i["shape"] in {"bed", "sofa-bed"} for i in c["furniture"]))
             and any(overlaps(shared.box(c["tour_mm"]), shared.box(r["tour_mm"])) for r in shrine)]
    for c in cells.values():
        if c["kind"] != "stair":
            continue
        features, g = c["tour_features"], c["tour_mm"]
        end = features["stair_footprint_mm"]["y_mm"] + features["stair_geometry"]["departure_offset_mm"]
        for door in features["doors"]:
            if door["neighbor"] is not None and door["face"] in {"left", "right"}:
                centre = g["y_mm"] + g["h_mm"] * door["ratio"]
                if centre-door["width_mm"]/2 < g["y_mm"] or centre+door["width_mm"]/2 > end:
                    raise ValueError("B32 side stair door must reach the floor-level front landing, not a tread")
    front_axis = first["shrine-front"]["tour_mm"]["x_mm"] + gate["ratio"] * first["shrine-front"]["tour_mm"]["w_mm"]
    backing = shared.box(first["altar-backing"]["tour_mm"])
    if (stairs_behind or above or abs(front_axis-altar["center_x_mm"]) > 1
            or backing["minY"] != 11370 or backing["minX"] > axis["minX"] or backing["maxX"] < axis["maxX"]):
        raise ValueError("B32 loses the confirmed shrine rules")
    req = {r["id"]: r for r in json.loads(model3d.REQUIREMENTS_FILE.read_text())["requirements"]}
    groups = {"B.floor-1.shrine": shrine, "B.floor-1.palanquin": [first["storage"]],
              "B.floor-1.bath_acc": [first["bath1"], first["bath-extension"]],
              "B.floor-2.master_b": [cells["B:floor-2:master2"]],
              "B.floor-2.master_bath": [cells["B:floor-2:master-bath2"]],
              "B.floor-2.bath_g": [cells["B:floor-2:bath2"]],
              "B.floor-3.bath_b3": [cells["B:floor-3:bath3"]]}
    areas = []
    for rid, rooms in groups.items():
        val, target = inset_area(rooms, 80), req[rid]["constraints"]["target_sqm"]
        areas.append({"id": rid, "title": req[rid]["title"], "room_ids": [c["id"] for c in rooms],
                      "discussion_inset_sqm": val, "target_sqm": target,
                      "target_state": "below-target" if val < target else "area-only-not-function-approval",
                      "finished_and_legal_area": None})
    whole = inset_area(shrine, 80)
    reserve = option["pedestrian_reserve_clear_mm"] * (11370-3900-160) / 1e6
    sensitivity = [{"assumed_each_side_mm": b, "master_sqm": inset_area([cells["B:floor-2:master2"]], b),
                    "public_bath_sqm": inset_area([cells["B:floor-2:bath2"]], b)} for b in (80, 100, 115)]
    return {"street_facing_axial_door": True, "stair_or_hall_behind_altar": stairs_behind,
            "sleep_wet_stairs_above_whole_shrine": above, "dry_altar_backing": True,
            "shrine_whole_room_discussion_sqm": whole,
            "shrine_after_passage_reserve_sqm": round(whole-reserve, 4),
            "passage_reserve_clear_assumption_mm": option["pedestrian_reserve_clear_mm"],
            "praying_people_and_capacity": "unknown-not-area-only-approval", "area_checks": areas,
            "inset_sensitivity": sensitivity, "transport": transport(building, option, physical),
            "bathroom_rescue_ventilation_waterproofing": "unknown",
            "work_access": "via-storage-not-original-independent-work-balcony-approval",
            "statutory_building_area": None, "rear_access": "unknown"}


def build_study(settings: dict | None = None) -> dict:
    settings = copy.deepcopy(settings) if settings is not None else json.loads(SOURCE.read_text())
    validate_settings(settings)
    physical = load_physical_items(model3d.PHYSICAL_ITEMS_FILE)["by_id"]["B.palanquin.primary"]
    options = []
    program = json.loads(model3d.PROGRAM_FILE.read_text())
    for spec in settings["options"]:
        raw, furniture = raw_proposal(settings, spec)
        payload = model3d.build_payload(program, load_overrides(), model3d.default_drawing_style(),
                                       review_data=raw, furniture_data=furniture, validate_a_arcade=False)
        building = next(b for b in payload["buildings"] if b["id"] == "B")
        building["title"] = spec["label"]
        labels = ["1F 祭祀／搬轎／淋浴預案", "2F 起居／主臥預案", "3F 閱讀／後客房骨架", "RF 設備待排／屋突未核"]
        for floor, label in zip(building["floors"], labels, strict=True):
            floor["label"] = label
        place_products(building, spec, physical)
        review = program_screen(building, spec, physical)
        screen = shared.body_screen(building)
        if (screen["fixed_body_failures"] or screen["pending_solver_items"] or screen["operation_limits"]
                or any(v["issue"] == "operation-vs-body" for v in screen["operation_sharing"])):
            raise ValueError("B32 coordinate defect " + spec["id"] + ": " + json.dumps(screen, ensure_ascii=False))
        payload["facade"] = build_facade(payload["buildings"], payload["standards"])
        plans = next(b for b in plan_data(payload)["buildings"] if b["id"] == "B")
        for floor in plans["floors"]:
            floor["plan_file"] = spec["id"] + "_" + floor["id"] + ".svg"
            if sum(r["geometry"]["w_mm"] * r["geometry"]["h_mm"] for r in floor["rooms"]) != 6000 * 17630:
                raise ValueError("B32 incomplete floor coverage")
        tradeoffs = ["32地坪硬上限；6×17.63m、前3.9m及一樓4m樓高是未核假設。",
                     "比較未採用；原ABC主案與需求不改。主臥20m²目標保留，牆柱餘量極薄。",
                     f"神明堂整廳討論約{review['shrine_whole_room_discussion_sqm']:.2f}m²，扣本案通行暫留後約{review['shrine_after_passage_reserve_sqm']:.2f}m²，非專用祭拜容量通過。",
                     "搬運線只驗收納本體平移，不含裝桿、人員、輪具、門片或巷道轉向。",
                     *(settings["unresolved"])]
        if spec["entry_mode"] == "rear":
            tradeoffs.insert(0, "後門搬轎優先預案；後巷／通行權／開門合法性未知，門外不畫成既有土地。")
        else:
            tradeoffs.insert(0, "無後巷時的獨立前門備案；祭祀與前廳橫移搬轎分時，未實物演練。")
        combined = {"program": review, "coordinate_screen": screen, "professional_status": settings["professional_status"]}
        model = shared.isolate(payload, building, spec, combined, tradeoffs)
        model["bc_option"]["revision"] = 1
        model["source"].pop("preparation_review", None)
        model["source"].pop("preparation_generator", None)
        model["source"]["b32_entry_options"] = "inputs/b32-entry-options.json"
        model["source"]["b32_generator"] = "scripts/export_b32_entry_options.py"
        options.append({**spec, "building": "B", "height_mm": 4000, "frame_mm": settings["frame_mm"],
                        "status": STATUS, "plans": plans, "review": combined, "tradeoffs": tradeoffs, "model": model})
    source_files = [SOURCE, Path(__file__), ROOT / "scripts/templates/b32-entry-options.html",
                    ROOT / "scripts/templates/b32-plan-viewer.js",
                    ROOT / "scripts/templates/b32-entry-routes.js", ROOT / "scripts/check_b32_entry_playwright.cjs",
                    ROOT / "Docs/b32-entry-options-v1.md", ROOT / "scripts/export_preparation_review.py",
                    model3d.REVIEW_FILE, model3d.FURNITURE_FILE, model3d.PROGRAM_FILE, model3d.REQUIREMENTS_FILE,
                    model3d.PHYSICAL_ITEMS_FILE, model3d.FACADE_FILE, model3d.TEMPLATE_FILE, model3d.THREE_FILE,
                    ROOT / "scripts/templates/model3d_facade.js", ROOT / "scripts/templates/bc-options-controls.html",
                    ROOT / "scripts/templates/bc-options-bootstrap.js", ROOT / "scripts/export_model_3d.py",
                    ROOT / "scripts/config/residential_defaults_tw.json", ROOT / "inputs/bc-constraints-options.json",
                    ROOT / "inputs/dimensions.json", *sorted((ROOT / "scripts/lib").glob("*.py")),
                    *sorted((ROOT / "house_design/rendering").glob("*.py")), ROOT / "house_design/physical_items.py"]
    return {**settings, "display_revision": DISPLAY_REVISION, "options": options,
            "source_hashes": {str(p.relative_to(ROOT)): shared.digest(p) for p in source_files},
            "protected_main_hashes": {p: shared.digest(ROOT / p) for p in PROTECTED}}


def render_svg(option: dict, floor: dict) -> str:
    concise = {"garage": "騎樓3.9m｜不計車位", "stair1": "樓梯／平台＊", "shrine-front": "神明堂前廳｜朝街正門",
               "shrine": "神明堂祭拜區｜乾式背牆", "altar-backing": "乾式法器櫃房", "bath1": "一樓淋浴／轉位＊",
               "bath-extension": "衛浴入口｜同室", "corridor1": "側緣公共通道", "storage": "武轎儲藏室＊", "work-reserve": "工作預留＊"}
    tree = ET.fromstring(render_plan("B", floor, room_labels=concise if floor["id"] == "floor-1" else None,
        viewer_url="../b32-entry-options-3d.html?scheme=" + option["id"]))
    tree.set("data-study-option", option["id"])
    tree.set("data-study-status", STATUS)
    ET.SubElement(tree, "{"+NS+"}desc").text = option["label"] + "；32地坪比較未採用，後巷及搬運外廓未核。"
    if floor["id"] == "floor-1":
        for el in tree.findall("{"+NS+"}text"):
            if el.get("y") == "-210":
                el.text = "＊操作／入口未核；全名與限制見同案HTML，不代表核定通行。"
    for el in tree.findall('.//{'+NS+'}text[@data-door-label]'):
        purpose, full = el.get("data-door-purpose"), el.get("data-door-label", "")
        if purpose == "rear-palanquin-entry":
            clear = (float(el.get("data-door-width-mm")) - 160) / 10
            el.text = f"後門｜{clear:g}cm暫估／巷道未核"
        elif purpose == "palanquin-storage":
            el.text = "儲藏前門166cm＊"
        elif full.startswith("乾櫃入口"):
            el.text = "乾櫃門106cm＊"
        elif full.startswith("淋浴側門"):
            el.text = "淋浴門106cm＊"
        elif full.startswith("工作預留區入口"):
            el.text = "工作區門106cm＊"
    for room in floor["rooms"]:
        for segment in room["features"].get("b32_transport_segments", []):
            g = ET.SubElement(tree, "{"+NS+"}g", {"data-b32-route": segment["label"], "data-room-id": room["id"]})
            b = segment["body_sweep_mm"]
            ET.SubElement(g, "{"+NS+"}rect", {"x": str(b["minX"]), "y": str(b["minY"]),
                          "width": str(b["maxX"]-b["minX"]), "height": str(b["maxY"]-b["minY"]),
                          "fill": "none", "stroke": "#287b89", "stroke-width": "1", "stroke-dasharray": "5 3",
                          "vector-effect": "non-scaling-stroke"})
            a, z = segment["centerline_mm"]
            ET.SubElement(g, "{"+NS+"}line", {"x1": str(a[0]), "y1": str(a[1]), "x2": str(z[0]), "y2": str(z[1]),
                          "stroke": "#287b89", "stroke-width": "2", "vector-effect": "non-scaling-stroke"})
            dx, dy = z[0] - a[0], z[1] - a[1]
            length = (dx*dx + dy*dy)**0.5
            if length:
                nx, ny = dx/length, dy/length
                mx, my = (a[0]+z[0])/2, (a[1]+z[1])/2
                ET.SubElement(g, "{"+NS+"}path", {
                    "d": f"M {mx-ny*120-nx*170} {my+nx*120-ny*170} L {mx} {my} L {mx+ny*120-nx*170} {my-nx*120-ny*170}",
                    "fill": "none", "stroke": "#287b89", "stroke-width": "2", "vector-effect": "non-scaling-stroke"})
            ET.SubElement(g, "{"+NS+"}title").text = segment["label"] + "（收納本體試排，非搬運核定）"
    ET.SubElement(tree, "{"+NS+"}text", {"x": "0", "y": "-820", "font-size": "180", "fill": "#8a4b10"}).text = "32地坪預案；未採用／後巷與完成面未核。"
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(tree, encoding="unicode") + "\n"


def render_plan_viewer(option: dict) -> str:
    """A DOM viewport around the unchanged SVG; source units stay inspectable."""
    floor = option["plans"]["floors"][0]
    svg = ET.fromstring(render_svg(option, floor))
    _, _, width, height = map(float, svg.get("viewBox").split())
    fonts = [float(t.get("font-size")) for t in svg.iter("{"+NS+"}text") if t.get("font-size")]
    minimum = min(fonts)
    # At least 14 CSS pixels for explicit notes/door labels in reading mode.
    readable = max(660, math.ceil(14 * width / minimum))
    oid = option["id"]
    title = html.escape(option["label"])
    url = f'b32-entry-options/{floor["plan_file"]}'
    buttons = ''.join(
        f'<button type="button" data-plan-action="{action}" aria-controls="{oid}-viewport"'
        + (f' aria-pressed="{str(action == "readable").lower()}"' if action in {"readable", "overview"} else '')
        + f'>{label}</button>'
        for action, label in [("in", "放大＋"), ("out", "縮小－"), ("readable", "讀字模式"), ("overview", "整層／還原")]
    )
    return (
        f'<figure class="plan-viewer" data-plan-viewer="{oid}" data-plan-mode="readable" '
        f'data-source-width="{width:g}" data-source-height="{height:g}" '
        f'data-readable-width="{readable}" data-min-label-units="{minimum:g}">'
        f'<h3 id="{oid}-plan-title">一樓平面（未採用／未核） · 道路在上、屋後在下</h3>'
        f'<div class="plan-controls" data-plan-controls role="group" aria-label="{title}平面閱讀控制" hidden>{buttons}</div>'
        f'<output class="plan-state" data-plan-state aria-live="polite">讀字模式（非工程比例）；可在圖框內捲動。</output>'
        f'<div class="plan-viewport" data-plan-viewport id="{oid}-viewport" role="region" tabindex="0" '
        f'aria-labelledby="{oid}-plan-title" aria-describedby="{oid}-plan-hint">'
        f'<object type="image/svg+xml" data="{url}" aria-label="{title}一樓同源平面圖" '
        f'style="width:{readable}px;height:{readable * height / width:g}px;aspect-ratio:{width:g}/{height:g}">'
        f'<p>無法顯示時，<a href="{url}">開啟同案原尺寸SVG</a>。</p></object></div>'
        f'<figcaption class="plan-hint" id="{oid}-plan-hint">先用讀字模式看家具編號、門位與尺寸；整層總覽只供辨方向。'
        '手機可在圖框內上下／左右滑動，亦可用按鈕；不攔截瀏覽器縮放。鍵盤Tab到圖框後用方向鍵、PageUp／Down，Home回圖首、End到圖尾。'
        f'<a href="{url}" data-original-plan>開啟同案原尺寸SVG</a>；全名與尺寸見下方家具名錄。未採用／未核。</figcaption>'
        '<p class="warning plan-error" data-plan-error hidden>圖面未載入，請用原尺寸SVG連結查看；不代表圖面驗收通過。</p></figure>'
    )


def render_index(study: dict) -> str:
    sections = []
    for o in study["options"]:
        p = o["review"]["program"]
        rows = "".join(f'<tr><th>{html.escape(a["title"])}</th><td>{a["discussion_inset_sqm"]:.2f}</td><td>{a["target_sqm"]:g}</td><td>僅面積試算／功能未核</td></tr>' for a in p["area_checks"])
        floors = "".join(f'<li><a href="b32-entry-options/{f["plan_file"]}">{html.escape(f["label"])} SVG</a> · <a href="b32-entry-options-3d.html?scheme={o["id"]}#mode=tour&amp;building=B&amp;floor={f["id"]}&amp;view=plan">同案3D</a></li>' for f in o["plans"]["floors"])
        steps = "".join('<li>'+html.escape(s["label"])+'</li>' for s in p["transport"]["segments"])
        catalogs = []
        for f in o["plans"]["floors"]:
            objects = [(room, i) for room in f["rooms"] for i in room["furniture"]]
            if not objects:
                continue
            entries = "".join(f'<tr data-furniture-id="{html.escape(i["id"])}"><td>{n}</td><td>{html.escape(room["name"])}</td><td>{html.escape(i["label"])}</td><td>{i["width_mm"]:g}×{i["depth_mm"]:g}×{i["height_mm"]:g}</td></tr>' for n, (room, i) in enumerate(objects, 1))
            catalogs.append('<h3>'+html.escape(f["label"])+'</h3><div class="scroll"><table><thead><tr><th>圖號</th><th>房間</th><th>家具／實物</th><th>寬×深×高mm</th></tr></thead><tbody>'+entries+'</tbody></table></div>')
        sections.append(f'<section id="{o["id"]}" data-option="{o["id"]}" tabindex="-1"><h2>{html.escape(o["label"])}</h2><p class="warning">比較未採用；後巷、完成面、法規、風水與搬運仍未核。</p>'
                        f'<p data-shrine-area>整間神明堂 {p["shrine_whole_room_discussion_sqm"]:.2f}m²；扣本案通行暫留後 {p["shrine_after_passage_reserve_sqm"]:.2f}m²。不是專用祭拜面積／人數通過。</p>'
                        + render_plan_viewer(o) +
                        '<p>青綠線框＝收納本體平移試排；不是人員／裝桿外廓。琥珀暫留帶不是已核淨空。道路在圖上前端，後門在圖上後端。可切讀字／整層模式、開原尺寸SVG或同案3D房間特寫。</p>'
                        '<details><summary>本案搬運步驟（收納本體試排）</summary><ol data-route-steps>'+steps+'</ol></details>'
                        '<ul>'+floors+'</ul><details data-furniture-catalog><summary>圖上家具編號與原尺寸（每層重新編號）</summary>'+"".join(catalogs)+'</details><details><summary>面積、敏感度與未解需求</summary><div class="scroll"><table><thead><tr><th>原需求</th><th>討論m²</th><th>原目標m²</th><th>狀態</th></tr></thead><tbody>'+rows+'</tbody></table></div><ul>'+"".join('<li>'+html.escape(t)+'</li>' for t in o["tradeoffs"])+
                        '</ul><pre>'+html.escape(json.dumps(o["review"], ensure_ascii=False, indent=2))+'</pre></details></section>')
    template = (ROOT / "scripts/templates/b32-entry-options.html").read_text()
    return (template.replace("__OPTIONS__", "\n".join(sections))
            .replace("__DISPLAY_REVISION__", str(DISPLAY_REVISION))
            .replace("__PLAN_VIEWER__", (ROOT / "scripts/templates/b32-plan-viewer.js").read_text()))


def render_viewer(study: dict) -> str:
    controls = (ROOT / "scripts/templates/bc-options-controls.html").read_text().replace("bc-options.html", "b32-entry-options.html").replace("B 家規／C 照護", "B 32地坪搬轎").replace("B／C比較", "B32搬轎比較")
    bootstrap = (ROOT / "scripts/templates/bc-options-bootstrap.js").read_text().replace("bc-options.html", "b32-entry-options.html").replace("B 家規／C 照護", "B 32地坪搬轎").replace('"bc-constraints"', '"b32-entry"')
    data = {"bc_options": {"default_option": study["default_option"], "options": [
        {"id": o["id"], "label": o["label"], "building": "B", "model": o["model"]} for o in study["options"]]}}
    viewer = model3d.render_html(data, model3d.three_source()[0], study_controls=controls, study_bootstrap=bootstrap)
    marker = "    if(features.transport_segment_mm){"
    if viewer.count(marker) != 1:
        raise ValueError("B32 renderer integration point changed; review rather than silently omit routes")
    viewer = viewer.replace(marker, (ROOT / "scripts/templates/b32-entry-routes.js").read_text() + "\n" + marker)
    fallback_assignment = '  fallbackLink.href = DATA.study_option ? "c1f-options.html#scheme=" + DATA.study_option.id : "../../" + fallbackBuilding + "buildingView.html";'
    if viewer.count(fallback_assignment) != 1:
        raise ValueError("B32 fallback integration point changed")
    viewer = viewer.replace(fallback_assignment, '  fallbackLink.href = "b32-entry-options.html#" + DATA.bc_option.id;')
    viewer = viewer.replace('  fallbackLink.textContent = DATA.study_option ? "返回本方案平面與清單" : "開啟 HTML 共用平面";',
                            '  fallbackLink.textContent = "返回同案平面與未解需求（未採用）";')
    viewer = viewer.replace('htmlHref="bc-options.html#"', 'htmlHref="b32-entry-options.html#"')
    viewer = viewer.replace('ABC v2 固定比較框提案（非地籍或可建容量）', 'B32預先設計（後巷未核／未採用）')
    return viewer.replace('row("標示面積",', 'row("原HTML歷史面積（非本比較）",')


def main() -> None:
    before = {p: shared.digest(ROOT / p) for p in PROTECTED}
    study = build_study()
    folder = OUT / "b32-entry-options"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {**study, "options": [{k: v for k, v in o.items() if k != "model"} for o in study["options"]]}
    (folder / "layout.js").write_text("window.HOUSE_B32_ENTRY_OPTIONS = " + encode_html_json(manifest) + ";\n")
    for o in study["options"]:
        for floor in o["plans"]["floors"]:
            (folder / floor["plan_file"]).write_text(render_svg(o, floor))
    (OUT / "b32-entry-options.html").write_text(render_index(study))
    (OUT / "b32-entry-options-3d.html").write_text(render_viewer(study))
    if before != {p: shared.digest(ROOT / p) for p in PROTECTED}:
        raise RuntimeError("B32 generation changed an existing drawing/source")
    print("Written B32 rear priority and front fallback, 8 same-source floors; ABC main and older comparisons unchanged.")


if __name__ == "__main__":
    main()

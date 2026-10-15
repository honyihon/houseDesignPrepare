#!/usr/bin/env python3
"""Independent ABC parcel/arcade sensitivity study; never adopt or sign off."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import export_model_3d as model3d  # noqa: E402
from lib.dimension_overrides import PING_TO_SQM, load_overrides  # noqa: E402
from lib.model3d_functions import check_a_care_functions  # noqa: E402
from lib.model3d_plan import plan_data, render_plan  # noqa: E402
from lib.model3d_tour import _contacts  # noqa: E402

from house_design.rendering import encode_html_json  # noqa: E402

SOURCE = ROOT / "inputs/abc-arcade-capacity.json"
REFERENCE_REVIEW = ROOT / "inputs/references/abc-before-a-arcade.json"
OUTPUT = ROOT / "structured/candidates"
TEMPLATES = ROOT / "scripts/templates"
STATUS = "comparison-only-not-adopted"
OPTION_IDS = ["baseline", "arcade32", "room-first"]
PROFESSIONAL_KEYS = {
    "parcel_dimensions",
    "arcade_applicability",
    "building_area",
    "coverage_and_far",
    "arcade_clear_height",
    "structure_and_fire",
    "accessibility",
    "daylight_and_ventilation",
    "hvac_installation",
    "feng_shui_and_altar_orientation",
}


def union_area(rectangles: list[list[float]]) -> float:
    """Exact flat union, not legal building area or a parcel aggregation."""
    xs = sorted({v for x, _, w, _ in rectangles for v in (x, x + w)})
    area = 0.0
    for left, right in zip(xs, xs[1:], strict=False):
        ys = sorted((y, y + h) for x, y, w, h in rectangles if x < right and x + w > left)
        end, length = -math.inf, 0.0
        for lo, hi in ys:
            length += max(0, hi - max(lo, end))
            end = max(end, hi)
        area += (right - left) * length
    return area / 1e6


def _mapper(building: str, option: str):
    # Change room boundaries, NEVER furniture sizes. Rear care rooms retain
    # their full rectangles. Piecewise mapping explicitly exposes lost front
    # capacity; no optimizer silently grows the fixed 32-ping frame.
    if option == "room-first":
        start, end, shift = (6100, 10400, 3900) if building == "A" else (9500, 13800, 0)
        return lambda y: y + shift + (0 if y <= start else 900 if y >= end else (y - start) * 900 / (end - start))
    if building == "A":
        return lambda y: (
            y
            if y <= 1500
            else 1500 + (y - 1500) * 3700 / 4600
            if y < 6100
            else 5200 + (y - 6100) * 5200 / 4300
            if y < 10400
            else y
        )
    return lambda y: (
        y
        if y <= 3900
        else 3900 + (y - 3900) * 4700 / 5600
        if y < 9500
        else 8600 + (y - 9500) * 5200 / 4300
        if y < 13800
        else y
    )


def _patch_review(source: dict, raw: dict, option: str) -> tuple[dict, dict]:
    review = copy.deepcopy(source)
    review["id"], review["status"] = raw["id"] + ":" + option, STATUS
    frames = {}
    for bid, spec in review["buildings"].items():
        map_y = _mapper(bid, option)
        depth = (
            raw["assumptions"]["frame_depth_mm"] + (4800 if bid == "A" else 900) if option == "room-first" else 17630
        )
        frames[bid] = [6000, depth]
        spec["summary"] = next(o["summary"] for o in raw["options"] if o["id"] == option)
        spec["assumptions"] = raw["conditions"] + spec["assumptions"]
        spec["parking"].update(displayed_cars=0, verified_spaces=None, status="not-accommodated-in-capacity-study")
        spec["deferred"].extend({"state": "alternative", "note": n} for n in raw["unmet"][bid])
        core = spec["core"]["rect"]
        core[1], core[3] = round(map_y(core[1])), 5200
        for fid, floor in spec["floors"].items():
            old = copy.deepcopy(floor)
            # Door centres on vertical shared walls must follow the changed
            # boundary. Horizontal-wall centres stay in X, not depth ratios.
            for connection in floor["connections"]:
                if len(connection) == 4:
                    a, b = (old["rooms"][k]["rect"] for k in connection[:2])
                    if abs(a[0] + a[2] - b[0]) < 2 or abs(b[0] + b[2] - a[0]) < 2:
                        connection[3] = round(map_y(connection[3]))
            for room in floor["rooms"].values():
                x, y, w, h = room["rect"]
                room["rect"] = [x, round(map_y(y)), w, round(map_y(y + h)) - round(map_y(y))]
                room.pop("frontage_study", None)  # Never borrow conditional private-yard uses in an arcade.
            if option == "room-first" and bid == "A":
                floor["rooms"]["arcade"] = {
                    "rect": [0, 0, 6000, 3900],
                    "name": "騎樓通行預留" if fid == "floor-1" else "上層前緣平台（投影待核）",
                    "kind": "outdoor",
                    "outdoor": True,
                    "clear": True,
                    "window_mm": 0,
                }
            if option == "arcade32" and bid == "A" and fid == "floor-1":
                floor["rooms"]["arcade"] = {
                    "rect": [0, 0, 6000, 3900],
                    "name": "騎樓3.9m通行（不置物／不停車）",
                    "kind": "outdoor",
                    "outdoor": True,
                    "clear": True,
                    "window_mm": 0,
                }
                for key in ("living", "entry"):
                    room = floor["rooms"][key]
                    room["rect"][1:4:2] = [3900, 1300]
                    room["clearance_reservations"] = []
                    room["name"] = (
                        "客餐廳不足（保留原尺寸待排家具）" if key == "living" else "入口不足（150cm轉位未容納）"
                    )
                floor["rooms"]["mdf"]["rect"] = [3600, 5200, 2400, 3100]
                floor["rooms"]["bath1"] = copy.deepcopy(old["rooms"]["bath1"])
                floor["connections"][0][3] = 4550
                floor["connections"][1][3] = 5400  # horizontal wall, X coordinate
                floor["entry"] = ["entry", "front", 1000, 5170]
            if option == "arcade32" and bid == "C" and fid == "floor-1":
                # Preserve the full four-person dining envelope and entry,
                # take 900mm only from the living zone, grow the kitchen/core.
                for key in ("entrance", "dining"):
                    floor["rooms"][key] = copy.deepcopy(old["rooms"][key])
                floor["rooms"]["living"]["rect"] = [0, 7100, 6000, 1500]
                floor["rooms"]["living"]["name"] = "客廳深度不足（茶几／轉位待排）"
                floor["rooms"]["living"]["clearance_reservations"] = [
                    {"kind": "care-route", "rect": [2400, 0, 1200, 1500]},
                    {"kind": "care-turn", "rect": [2400, 0, 1500, 1500]},
                    {"kind": "circulation", "rect": [3600, 0, 2200, 1200]},
                ]
                floor["rooms"]["kitchen"]["rect"] = [0, 8600, 2400, 3500]
                for key in ("sideyard", "sliding-door"):
                    floor["rooms"][key] = copy.deepcopy(old["rooms"][key])
                floor["connections"][:3] = copy.deepcopy(old["connections"][:3])
                floor["connections"][4][3] = 9300
            # Front entry on the road-facing horizontal wall uses X; floor
            # bases and all shared stair coordinates are changed separately.
            for room in floor["rooms"].values():
                for z in room.get("clearance_reservations", []):
                    if z["rect"][1] + z["rect"][3] > room["rect"][3]:
                        raise ValueError("A care reservation cannot be shrunk to manufacture capacity")
            for connection in floor["connections"]:
                if len(connection) != 4:
                    continue
                boxes = [
                    dict(zip(("x_mm", "y_mm", "w_mm", "h_mm"), floor["rooms"][k]["rect"], strict=True))
                    for k in connection[:2]
                ]
                contact = _contacts(*boxes)
                if contact is None:
                    raise ValueError("Nonadjacent comparison opening")
                _, lo, hi = contact
                opening = connection[2]
                width = opening["width_mm"] if isinstance(opening, dict) else hi - lo if opening == "open" else opening
                if width > hi - lo:
                    raise ValueError("Comparison cannot shrink an opening to fit")
                connection[3] = min(hi - width / 2, max(lo + width / 2, connection[3]))
    return review, frames


def _shared_stairs(buildings: list[dict]) -> None:
    """Same well and front landing across levels, differing real riser counts.

    Reserve the 1F longest run on every level. Upper-storey extra depth goes
    only to the middle landing; front/top landing remains exactly aligned.
    """
    for building in buildings:
        for floor in building["floors"]:
            for cell in floor["cells"]:
                if not cell.get("tour_active") or not cell["tour_features"]["stairs"]:
                    continue
                f, g = cell["tour_features"], cell["tour_mm"]
                stair = f["stair_geometry"]
                stair["middle_landing_mm"] = 4970 - stair["run_mm"] - stair["landing_mm"]
                f["stair_footprint_mm"]["h_mm"] = 4970
                stair["fits_reserved_box"] = 2360 <= g["w_mm"] and 5110 <= g["h_mm"]
                stair["note"] += " 比較案中間平台補足共同梯井深度，前／到達平台同軸；梁下淨高、階數交接、消防仍未知。"


def _structural_screens(buildings: list[dict]) -> list[dict]:
    """Keep the independent projection/core gates even when A's care fails."""
    checks = []
    for building in buildings:
        stairs = [
            c["tour_features"]["stair_footprint_mm"]
            for f in building["floors"]
            for c in f["cells"]
            if c.get("tour_active") and c["tour_features"]["stairs"]
        ]
        if len(stairs) != len(building["floors"]) or any(s != stairs[0] for s in stairs):
            raise ValueError("Unaligned comparison stair core: " + building["id"])
        checks.append(
            {
                "id": building["id"] + "-stair-stack",
                "status": "proposal-geometric-screen-only",
                "note": "共同梯井／前到達平台同軸；梁下淨高、結構與消防未知。",
            }
        )
    b = next(b for b in buildings if b["id"] == "B")
    shrine = next(c for c in b["floors"][0]["cells"] if c["key"] == "shrine")["tour_mm"]
    for floor in b["floors"][1:]:
        for cell in floor["cells"]:
            if not cell.get("tour_active"):
                continue
            g = cell["tour_mm"]
            intersects = max(shrine["x_mm"], g["x_mm"]) < min(
                shrine["x_mm"] + shrine["w_mm"], g["x_mm"] + g["w_mm"]
            ) and max(shrine["y_mm"], g["y_mm"]) < min(shrine["y_mm"] + shrine["h_mm"], g["y_mm"] + g["h_mm"])
            hazard = cell["kind"] in {"bath", "kitchen", "stair"} or any(
                s in cell["name"] for s in ("KTV", "水塔", "加壓", "熱泵")
            )
            if intersects and hazard:
                raise ValueError("B altar protection changed: " + cell["id"])
    checks.append(
        {
            "id": "B-shrine-projection",
            "status": "proposal-geometric-screen-only",
            "note": "全層用途幾何避開神桌投影；梁管線／宗教坐向未知。",
        }
    )
    return checks


def _payload(baseline: dict, program: dict, source_review: dict, raw: dict, option: str) -> dict:
    review, frames = _patch_review(source_review, raw, option)
    program = copy.deepcopy(program)
    for b in program["buildings"]:
        for f in b["floors"]:
            if f.get("record_type") == "floor":
                f["storey_height_mm"] = 4000 if f["id"] == "floor-1" else 3000
    result = copy.deepcopy(baseline)
    result["buildings"] = model3d.build_buildings(program, load_overrides(), result["palette"], 3000)[0]
    for b in result["buildings"]:
        per_parcel = copy.deepcopy(review)
        per_parcel["frame_mm"] = frames[b["id"]]
        model3d.prepare_review([b], data=per_parcel)
    result["layout_review"] = {k: copy.deepcopy(v) for k, v in review.items() if k != "buildings"}
    result["furniture"] = model3d.attach_furniture_layout(result["buildings"], model3d.FURNITURE_FILE)
    model3d.attach_tour(result["buildings"])
    _shared_stairs(result["buildings"])
    result["layout_review"]["hvac_routes"] = model3d.attach_hvac_proposals(result["buildings"])
    model3d.attach_placements(result["buildings"])
    # Capacity failure is reportable data, not a reason to omit the study.
    # Main build_payload still uses its original strict A care gate.
    try:
        care = check_a_care_functions(result["buildings"])
    except ValueError as exc:
        care = {"id": "A-1F-care-functions", "status": "not-accommodated", "note": str(exc)}
    result["layout_review"]["checks"] = _structural_screens(result["buildings"]) + [care]
    result["facade"] = model3d.build_facade(result["buildings"], result["standards"])
    result["compare"] = {"available": False}
    result["geom_source_default"] = "auto"
    result["source"]["capacity_study"] = str(SOURCE.relative_to(ROOT))
    return result


def _capacity(building: dict, raw: dict, option: str) -> dict:
    floors = building["floors"]
    ground = floors[0]
    rooms = [c for c in ground["cells"] if c.get("tour_active")]
    all_rooms = [c for f in floors for c in f["cells"] if c.get("tour_active")]
    area = ground["tour_width_mm"] * ground["tour_depth_mm"] / 1e6
    indoor = [list(c["tour_mm"].values()) for c in all_rooms if not c["is_outdoor"]]
    proxy = union_area(indoor)
    pending = [
        {
            "room_id": c["id"],
            "room": c["name"],
            "item_id": i["id"],
            "item": i["label"],
            "dimensions_mm": [i[k] for k in ("width_mm", "depth_mm", "height_mm")],
            "issues": c["furniture_placements"]["tour_mm"][i["id"]]["issues"],
        }
        for c in all_rooms
        for i in c["furniture"]
        if c["furniture_placements"]["tour_mm"][i["id"]]["issues"]
    ]
    bid = building["id"]
    care_gates = []
    if bid in {"A", "C"}:
        elder_key, bath_key = ("flex1", "bath1") if bid == "A" else ("elder", "elder-bath")
        by_key = {c["key"]: c for c in rooms}
        for key in (elder_key, bath_key):
            room = by_key[key]
            care_gates.append(
                {
                    "room": room["name"],
                    "room_id": room["id"],
                    "present": True,
                    "furniture_pending": any(p["room_id"] == room["id"] for p in pending),
                    "turning_reservation_present": any(
                        z["kind"] == "care-turn" for z in room["tour_features"]["reserved_mm"]
                    ),
                    "professional_acceptance": "unknown",
                }
            )
    return {
        "frame_mm": [ground["tour_width_mm"], ground["tour_depth_mm"]],
        "parcel_sqm": round(area, 3),
        "parcel_ping": round(area / PING_TO_SQM, 3),
        "ground_indoor_rectangles_sqm": round(
            sum(c["tour_mm"]["w_mm"] * c["tour_mm"]["h_mm"] / 1e6 for c in rooms if not c["is_outdoor"]), 3
        ),
        "indoor_projection_proxy_sqm": round(proxy, 3),
        "legal_building_area_sqm": None,
        "coverage_sensitivity": [
            {
                "ratio": ratio,
                "hypothetical_limit_sqm": round(area * ratio, 3),
                "proxy_excess_sqm": round(max(0, proxy - area * ratio), 3),
                "legal_result": "unknown",
            }
            for ratio in raw["assumptions"]["coverage_sensitivity"]
        ],
        "front_clear": option != "baseline" or bid != "A",
        "arcade_net_height_verified": None,
        "displayed_cars": 0,
        "verified_parking_spaces": None,
        "pending_furniture": pending,
        "care_rooms": care_gates,
        "unmet": raw["unmet"][bid]
        + (
            ["32坪限制案：A入口150cm轉位與18m²客餐廳最低需求未容納，不能採用此排法。"]
            if option == "arcade32" and bid == "A"
            else ["32坪限制案：C客廳深度僅1.5m，正常茶几／照護轉位不能成立；不縮家具，需重新取捨。"]
            if option == "arcade32" and bid == "C"
            else []
        ),
        "ground_program_status": "conflicts-remain"
        if any(p["room_id"].startswith(bid + ":floor-1:") for p in pending)
        or option == "arcade32"
        and bid in {"A", "C"}
        else "geometry-only-professional-review-pending",
        "status": "conflicts-remain"
        if pending or bid == "A" and option != "room-first"
        else "geometry-only-professional-review-pending",
    }


def build_study(data: dict | None = None) -> dict:
    raw = copy.deepcopy(data) if data is not None else json.loads(SOURCE.read_text(encoding="utf-8"))
    if (
        raw.get("schema") != "house-abc-arcade-capacity-v1"
        or raw.get("status") != STATUS
        or raw.get("active_design") != "main-a32-arcade-v1"
    ):
        raise ValueError("Capacity study must stay separate from the active design")
    if [o["id"] for o in raw["options"]] != OPTION_IDS or raw.get("default_comparison") != "arcade32":
        raise ValueError("Unexpected comparison IDs")
    expected = {
        "area_ping_each": 32,
        "frontage_mm": 6000,
        "front_clear_mm": 3900,
        "frame_depth_mm": 17630,
        "ground_storey_height_mm": 4000,
        "upper_storey_height_mm": 3000,
        "arcade_clear_height_target_mm": 3500,
        "beam_slab_finish_budget_mm": 500,
        "stair_core_depth_mm": 5200,
        "rear_open_sensitivity_mm": [0, 1000, 1500, 1800, 2000],
        "coverage_sensitivity": [0.5, 0.6, 0.7],
    }
    professional_status = raw.get("professional_status")
    if (
        raw["assumptions"] != expected
        or not isinstance(professional_status, dict)
        or set(professional_status) != PROFESSIONAL_KEYS
        or any(s != "unknown" for s in professional_status.values())
    ):
        raise ValueError("Changed assumptions require a new studied geometry; no false professional approval")
    if set(raw) - {
        "schema",
        "id",
        "status",
        "active_design",
        "default_comparison",
        "assumptions",
        "professional_status",
        "conditions",
        "sources",
        "options",
        "unmet",
    }:
        raise ValueError("No product, measurement or site overrides allowed")
    program = json.loads(model3d.PROGRAM_FILE.read_text(encoding="utf-8"))
    # Freeze the failed original skeleton as reference evidence. Do not apply
    # its coordinate mapper to the newly reflowed A main design.
    source_review = json.loads(REFERENCE_REVIEW.read_text(encoding="utf-8"))
    baseline = model3d.build_payload(
        program,
        load_overrides(),
        model3d.default_drawing_style(),
        review_path=REFERENCE_REVIEW,
        review_data=source_review,
        validate_a_arcade=False,
    )
    options = []
    for spec in raw["options"]:
        payload = (
            copy.deepcopy(baseline)
            if spec["id"] == "baseline"
            else _payload(baseline, program, source_review, raw, spec["id"])
        )
        payload["study_option"] = {
            "id": spec["id"],
            "label": spec["label"],
            "status": STATUS,
            "plan_url": "arcade-capacity.html#scheme=" + spec["id"],
        }
        plans = plan_data(payload)
        capacities = {}
        for b, plan in zip(payload["buildings"], plans["buildings"], strict=True):
            capacities[b["id"]] = _capacity(b, raw, spec["id"])
            for f, pf in zip(b["floors"], plan["floors"], strict=True):
                pf["plan_file"] = f"{spec['id']}_{b['id']}_{f['id']}.svg"
                pf["base_mm"], pf["height_mm"] = f["base_mm"], f["height_mm"]
        options.append({**spec, "plans": plans, "capacity": capacities, "model": payload})
    sources = [
        SOURCE,
        REFERENCE_REVIEW,
        model3d.REVIEW_FILE,
        model3d.FURNITURE_FILE,
        model3d.PROGRAM_FILE,
        model3d.PHYSICAL_ITEMS_FILE,
        model3d.FACADE_FILE,
        model3d.REQUIREMENTS_FILE,
        model3d.THREE_FILE,
        ROOT / "inputs/dimensions.json",
        Path(__file__),
        model3d.TEMPLATE_FILE,
        model3d.FACADE_JS_FILE,
        ROOT / "scripts/export_model_3d.py",
        ROOT / "scripts/export_top1_svgs.py",
        ROOT / "scripts/config/residential_defaults_tw.json",
        ROOT / "house_design/contracts.py",
        ROOT / "house_design/physical_items.py",
        *sorted((ROOT / "scripts/lib").glob("*.py")),
        *sorted((ROOT / "house_design/rendering").glob("*.py")),
        *sorted(TEMPLATES.glob("arcade-capacity*")),
    ]
    area = 32 * PING_TO_SQM
    return {
        **{k: v for k, v in raw.items() if k != "options"},
        "reference_review": str(REFERENCE_REVIEW.relative_to(ROOT)),
        "source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        "rear_sensitivity": [
            {
                "rear_mm": rear,
                "rectangular_remainder_sqm": round(area - 23.4 - rear * 6000 / 1e6, 3),
                "not_legal_floor_area": True,
            }
            for rear in raw["assumptions"]["rear_open_sensitivity_mm"]
        ],
        "options": options,
    }


def manifest(study: dict) -> dict:
    return {
        **{k: v for k, v in study.items() if k != "options"},
        "options": [{k: v for k, v in o.items() if k != "model"} for o in study["options"]],
    }


def render_study_plan(option: dict, building: str, floor: dict) -> str:
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    labels = {r["key"]: r["name"].split("（")[0][:10] for r in floor["rooms"]}
    tree = ET.fromstring(render_plan(building, floor, room_labels=labels,
        viewer_url="../arcade-capacity-3d.html?scheme=" + option["id"]))
    tree.set("data-study-option", option["id"])
    tree.set("data-study-status", STATUS)
    ns = {"s": "http://www.w3.org/2000/svg"}
    tree.find("s:title", ns).text = f"{building} 棟 · {floor['label']} · {option['label']}（比較用，未採用）"
    headings = tree.findall("s:text", ns)
    headings[0].text = f"{building} 棟 · {floor['label']} · 容量比較／未採用 · 道路 ↑"
    headings[
        1
    ].text = f"{floor['width_mm'] / 1000:g}×{floor['depth_mm'] / 1000:g}m 比較框；層高{floor['height_mm'] / 1000:g}m非梁下淨高。"
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(tree, encoding="unicode") + "\n"


def render_viewer(study: dict) -> str:
    models = {
        "arcade_capacity": {
            "options": [
                {"id": o["id"], "label": o["label"], "model": o["model"], "capacity": o["capacity"]}
                for o in study["options"]
            ]
        }
    }
    html = model3d.render_html(
        models,
        model3d.three_source()[0],
        study_controls=(TEMPLATES / "arcade-capacity-controls.html").read_text(encoding="utf-8"),
        study_bootstrap=(TEMPLATES / "arcade-capacity-bootstrap.js").read_text(encoding="utf-8"),
    )
    # Isolated renderer adapters, guarded against a changed shared template.
    # Main/C1F artifacts and their checked renderer stay byte-for-byte intact.
    replacements = {
        'history.replaceState(null, "", "#" + values.toString());': 'history.replaceState(null, "", "#" + values.toString()); syncStudyLink();',
        'DATA.study_option ? "c1f-options.html#scheme=" + DATA.study_option.id': "DATA.study_option ? DATA.study_option.plan_url",
    }
    for old, new in replacements.items():
        if html.count(old) != 1:
            raise ValueError("Shared renderer changed: review capacity adapter " + old)
        html = html.replace(old, new)
    return html


def main() -> None:
    study = build_study()
    directory = OUTPUT / "arcade-capacity"
    directory.mkdir(parents=True, exist_ok=True)
    for option in study["options"]:
        for b in option["plans"]["buildings"]:
            for f in b["floors"]:
                (directory / f["plan_file"]).write_text(render_study_plan(option, b["id"], f), encoding="utf-8")
    (directory / "layout.js").write_text(
        "window.HOUSE_ARCADE_CAPACITY = " + encode_html_json(manifest(study)) + ";\n", encoding="utf-8"
    )
    (OUTPUT / "arcade-capacity.html").write_text(
        (TEMPLATES / "arcade-capacity.html").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (OUTPUT / "arcade-capacity-3d.html").write_text(render_viewer(study), encoding="utf-8")
    print("ABC capacity comparison (not adopted): structured/candidates/arcade-capacity.html")
    for option in study["options"]:
        print(
            option["id"],
            {
                b: {"ping": c["parcel_ping"], "status": c["status"], "pending": len(c["pending_furniture"])}
                for b, c in option["capacity"].items()
            },
        )


if __name__ == "__main__":
    main()

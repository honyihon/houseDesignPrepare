#!/usr/bin/env python3
"""Bounded B/C owner-rule comparisons; never silently adopt tradeoffs."""

from __future__ import annotations

import copy
import hashlib
import html
import json
import sys
from collections import deque
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import export_model_3d as model3d  # noqa: E402
from lib.dimension_overrides import load_overrides  # noqa: E402
from lib.model3d_bc_flow import build_bc_flow_checks  # noqa: E402
from lib.model3d_placement import INSET, overlaps  # noqa: E402
from lib.model3d_plan import plan_data, render_plan  # noqa: E402
from lib.model3d_space_efficiency import comparison_source_review  # noqa: E402

from house_design.rendering import encode_html_json  # noqa: E402

SOURCE = ROOT / "inputs/bc-constraints-options.json"
OUTPUT = ROOT / "structured/candidates"
STATUS = "comparison-only-not-adopted"
IDS = ["b-baseline", "b-strict", "c-baseline", "c-side-bed", "c-wet-stack"]
PROFESSIONAL_KEYS = {
    "religious_acceptance",
    "structure_and_fire",
    "site_and_area",
    "accessibility",
    "daylight_and_ventilation",
    "plumbing_and_hvac",
    "transport_rehearsal",
}


def essential_products(building: dict, option_id: str) -> None:
    """Independent ordinary-size minima, not agreement between two bad drawings."""
    demands = {
        "b-strict": {
            "floor-1:shrine:altar": (1800, 600, 1250),
            "floor-1:shrine:offering-table": (1200, 500, 750),
            "floor-1:shrine:bench-left": (1400, 450, 450),
            "floor-1:shrine:bench-right": (1400, 450, 450),
            "floor-1:storage:ceremonial-storage": (1200, 1700, 1800),
            "floor-1:altar-backing:ritual-cabinet": (1200, 450, 2100),
            "floor-2:master2:bed": (1520, 1880, 900),
            "floor-2:master2:vanity": (1200, 500, 750),
            "floor-2:master2:wardrobe": (1800, 600, 2200),
            "floor-3:guest3:bed": (1050, 1880, 850),
            "floor-3:guest3:wardrobe": (1800, 600, 2200),
            "floor-3:guest3:desk": (1400, 700, 750),
            "floor-4:laundry-rf:washer": (650, 650, 1000),
        },
        "c-side-bed": {
            "floor-1:elder:bed": (1520, 1880, 900),
            "floor-1:elder:wardrobe": (1200, 600, 2200),
            "floor-1:elder:tv": (1000, 80, 600),
            "floor-1:elder-bath:accessible-shower": (1200, 1200, 2000),
            "floor-1:elder-bath:toilet": (450, 700, 800),
            "floor-1:elder-bath:vanity": (600, 450, 850),
        },
    }
    if option_id == "c-wet-stack":
        demands[option_id] = {
            **demands["c-side-bed"],
            "floor-2:guestroom2f:bed": (1050, 1880, 850),
            "floor-2:guestroom2f:wardrobe": (1800, 600, 2200),
            "floor-2:guestroom2f:desk": (1400, 700, 750),
        }
    items = {i["id"]: i for f in building["floors"] for c in f["cells"] if c.get("tour_active") for i in c["furniture"]}
    for key, minimum in demands.get(option_id, {}).items():
        floor, room, local = key.split(":")
        obj = items.get(f"{building['id']}:{floor}:{room}:furniture:{local}")
        if obj is None or any(obj[k] < n for k, n in zip(("width_mm", "depth_mm", "height_mm"), minimum, strict=True)):
            raise ValueError("BC comparison loses a full-size required product: " + key)


def program_limits(building: dict, option_id: str) -> dict:
    """Expose brief shortfalls separately from owner choice and legal area."""
    mapping = {
        "b-strict": {
            "B.floor-1.shrine": "B:floor-1:shrine",
            "B.floor-1.palanquin": "B:floor-1:storage",
            "B.floor-2.master_b": "B:floor-2:master2",
            "B.floor-1.bath_acc": "B:floor-1:bath1",
        },
        "c-wet-stack": {"C.floor-2.guest2": "C:floor-2:guestroom2f"},
        "c-side-bed": {"C.floor-2.bath_c2": "C:floor-2:bath2f", "C.floor-3.bath_c3": "C:floor-3:bath3f"},
    }
    requirements = {r["id"]: r for r in json.loads(model3d.REQUIREMENTS_FILE.read_text())["requirements"]}
    rooms = {c["id"]: c for f in building["floors"] for c in f["cells"] if c.get("tour_active")}
    areas = []
    for requirement_id, room_id in mapping.get(option_id, {}).items():
        requirement, g = requirements[requirement_id], rooms[room_id]["tour_mm"]
        nominal = g["w_mm"] * g["h_mm"] / 1e6
        assumed = (g["w_mm"] - 2 * INSET) * (g["h_mm"] - 2 * INSET) / 1e6
        minimum = requirement["constraints"]["min_sqm"]
        target = requirement["constraints"]["target_sqm"]
        areas.append(
            {
                "requirement_id": requirement_id,
                "room_id": room_id,
                "requirement_status": requirement["status"],
                "minimum_sqm": minimum,
                "target_sqm": target,
                "nominal_sqm": round(nominal, 4),
                "assumed_clear_sqm": round(assumed, 4),
                "state": "brief-area-shortfall" if assumed < minimum else "area-only-not-function-approval",
                "target_state": "below-brief-target" if assumed < target else "target-area-only-not-function-approval",
                "source": "inputs/requirements.json",
                "legal_area_sqm": None,
            }
        )
    missing = ["B.floor-2.tea", "B.floor-3.ktv", "B.floor-1.balcony_b"] if option_id == "b-strict" else []
    return {
        "status": "incomplete-not-adoptable-as-full-program",
        "areas": areas,
        "unaccommodated_requirement_ids": missing,
        "owner_tradeoffs_accepted": None,
        "legal_area_sqm": None,
    }


def public_stair_path(floor: dict) -> list[str]:
    graph = {c["key"]: [] for c in floor["cells"] if c.get("tour_active")}
    for a, b, *_ in floor["layout_review"]["connections"]:
        graph[a].append(b)
        graph[b].append(a)
    queue = deque([["public-entry"]])
    visited = set()
    while queue:
        path = queue.popleft()
        if path[-1] == "stair1":
            return path
        for key in graph[path[-1]]:
            if key not in visited and key not in {"shrine", "storage", "altar-backing", "bath1", "idf-cabinet"}:
                visited.add(key)
                queue.append([*path, key])
    raise ValueError("B comparison lacks an independent public route to stairs")


def aabb(g: dict) -> dict:
    return {"minX": g["x_mm"], "maxX": g["x_mm"] + g["w_mm"], "minY": g["y_mm"], "maxY": g["y_mm"] + g["h_mm"]}


def review_geometry(building: dict, option_id: str) -> dict:
    """Use whole rooms and real backing, not mesh parity or renamed bedrooms."""
    floors = {f["id"]: f for f in building["floors"]}
    cells = {c["id"]: c for f in floors.values() for c in f["cells"] if c.get("tour_active")}
    result = {"status": "geometry-and-function-screen-only", "religious_acceptance": "unknown"}
    if building["id"] == "B":
        shrine = cells["B:floor-1:shrine"]
        altar = shrine["furniture_placements"]["tour_mm"]["B:floor-1:shrine:furniture:altar"]
        sg, box = shrine["tour_mm"], altar["aabb"]
        behind = {
            "minX": box["minX"],
            "maxX": box["maxX"],
            "minY": sg["y_mm"] + sg["h_mm"],
            "maxY": floors["floor-1"]["tour_depth_mm"],
        }
        backing = [
            c
            for c in floors["floor-1"]["cells"]
            if c.get("tour_active") and c["tour_mm"]["y_mm"] == behind["minY"] and overlaps(behind, aabb(c["tour_mm"]))
        ]
        bad_backing = [
            c["id"]
            for c in backing
            if c["kind"] in {"bath", "kitchen", "stair"} or c.get("space_role") in {"circulation", "equipment-alcove"}
        ]
        all_rear_stairs = [
            c["id"]
            for c in floors["floor-1"]["cells"]
            if c.get("tour_active")
            and (c["kind"] == "stair" or c.get("space_role") == "circulation")
            and overlaps(behind, aabb(c["tour_mm"]))
        ]
        sleep_rooms = [
            c["id"]
            for f in building["floors"][1:]
            for c in f["cells"]
            if c.get("tour_active")
            and overlaps(aabb(sg), aabb(c["tour_mm"]))
            and (c["kind"] == "bedroom" or any(i["shape"] in {"bed", "sofa-bed"} for i in c["furniture"]))
        ]
        g = next(c for c in floors["floor-1"]["cells"] if c["key"] == "garage")
        front = next(d for d in shrine["tour_features"]["doors"] if d.get("purpose") == "ritual-entry")
        axial = (
            front["face"] == "front"
            and front["neighbor"] == g["id"]
            and abs(sg["x_mm"] + sg["w_mm"] * front["ratio"] - altar["center_x_mm"]) < 1
        )
        result.update(
            {
                "backing_room_ids": [c["id"] for c in backing],
                "prohibited_backing": bad_backing,
                "stair_or_hall_in_rear_axis": all_rear_stairs,
                "sleep_rooms_above_whole_shrine": sleep_rooms,
                "street_facing_axial_door": axial,
                "whole_shrine_geometry": sg,
                "shrine_assumed_clear_sqm": round((sg["w_mm"] - 2 * INSET) * (sg["h_mm"] - 2 * INSET) / 1e6, 4),
            }
        )
        if option_id == "b-strict":
            if bad_backing or all_rear_stairs or sleep_rooms or not axial or result["shrine_assumed_clear_sqm"] < 22:
                raise ValueError("B strict rules are not met by the actual rooms")
            if (
                len(backing) != 1
                or backing[0]["key"] != "altar-backing"
                or backing[0]["tour_mm"]["w_mm"] < 2000
                or backing[0]["tour_mm"]["h_mm"] < 1500
                or aabb(backing[0]["tour_mm"])["minX"] > box["minX"]
                or aabb(backing[0]["tour_mm"])["maxX"] < box["maxX"]
                or not backing[0]["furniture"]
                or any(i["category"] != "storage" for i in backing[0]["furniture"])
            ):
                raise ValueError("B backing must be real usable dry storage, not a fake wall")
            result["public_stair_path"] = public_stair_path(floors["floor-1"])
            master = cells["B:floor-2:master2"]
            products = master["furniture_placements"]["tour_mm"]
            bed_box = products["B:floor-2:master2:furniture:bed"]["aabb"]
            vanity_box = products["B:floor-2:master2:furniture:vanity"]["aabb"]
            result["master_long_side_body_gaps_mm"] = {
                "front": round(bed_box["minY"] - vanity_box["maxY"], 2),
                "rear": round(master["tour_mm"]["y_mm"] + master["tour_mm"]["h_mm"] - INSET - bed_box["maxY"], 2),
            }
            if (
                products["B:floor-2:master2:furniture:bed"]["wall_anchor"] != "right"
                or min(result["master_long_side_body_gaps_mm"].values()) < 600
            ):
                raise ValueError("B master loses side-wall headboard or nominal two-sided body clearance")
            for fid, key in [("floor-2", "master2"), ("floor-3", "guest3")]:
                if cells[f"B:{fid}:{key}"]["kind"] != "bedroom":
                    raise ValueError("B sleeping rooms may not be relabelled to bypass the whole-shrine check")
            for c in cells.values():
                if c["kind"] == "stair" and (
                    not c["tour_features"]["stair_geometry"]["fits_reserved_box"]
                    or not c["tour_features"].get("shared_landing_mm")
                ):
                    raise ValueError("B staircase lacks an aligned, fitting floor-level landing")
                if c["kind"] == "stair" and any(
                    d["neighbor"] != c["tour_features"]["shared_landing_mm"]["space"]
                    for d in c["tour_features"]["doors"] + c["tour_features"]["open_connections"]
                ):
                    raise ValueError("B staircase entry must meet its actual shared landing")
    else:
        elder = cells["C:floor-1:elder"]
        bed = elder["furniture_placements"]["tour_mm"]["C:floor-1:elder:furniture:bed"]
        wet = [
            c
            for f in building["floors"][1:]
            for c in f["cells"]
            if c.get("tour_active") and c["kind"] in {"bath", "kitchen"}
        ]
        result.update(
            {
                "headboard_wall": bed["wall_anchor"],
                "rear_window_mm": elder["window_mm"],
                "wet_rooms_over_bed": [c["id"] for c in wet if overlaps(bed["aabb"], aabb(c["tour_mm"]))],
                "wet_rooms_over_bedroom": [
                    c["id"] for c in wet if overlaps(aabb(elder["tour_mm"]), aabb(c["tour_mm"]))
                ],
                "bathroom_turning_and_rescue": "unknown",
                "visitor_public_bath": "not-provided",
            }
        )
        if option_id in {"c-side-bed", "c-wet-stack"}:
            if bed["wall_anchor"] != "left" or elder["window_mm"] != 2300 or result["wet_rooms_over_bed"]:
                raise ValueError("C comparison loses side-wall bed, original window or wet-room clearance")
            bath = cells["C:floor-1:elder-bath"]
            if elder["tour_mm"] != {"x_mm": 0, "y_mm": 13800, "w_mm": 3600, "h_mm": 3830} or bath["tour_mm"] != {
                "x_mm": 3600,
                "y_mm": 13800,
                "w_mm": 2400,
                "h_mm": 3000,
            }:
                raise ValueError("C comparison must preserve the full elder bedroom and bathroom")
            result["wet_room_to_bed_nominal_gap_mm"] = (
                min(
                    bed["aabb"]["minY"] - aabb(c["tour_mm"])["maxY"]
                    for c in wet
                    if overlaps({**bed["aabb"], "minY": 0}, aabb(c["tour_mm"]))
                )
                if option_id == "c-side-bed"
                else None
            )
        if option_id == "c-wet-stack" and result["wet_rooms_over_bedroom"]:
            raise ValueError("C wet-stack option still puts an upper wet room over the elder bedroom")
        if option_id == "c-side-bed" and result["wet_room_to_bed_nominal_gap_mm"] < 200:
            raise ValueError("C small option loses the extra nominal wet-wall separation")
    return result


def build_study(*, check_furniture: bool = True, raw: dict | None = None) -> dict:
    raw = copy.deepcopy(raw) if raw is not None else json.loads(SOURCE.read_text())
    if (
        raw.get("schema") != "house-bc-constraints-options-v1"
        or raw.get("status") != STATUS
        or raw.get("active_design") != "baseline"
        or raw.get("default_option") != "b-strict"
        or [o["id"] for o in raw["options"]] != IDS
        or any(
            raw.get("confirmed_b_rules", {}).get(k) is not True
            for k in ("altar_door_faces_street", "no_stair_or_hall_behind_altar", "no_sleep_above_whole_shrine")
        )
    ):
        raise ValueError("BC comparisons must retain the unadopted baseline contract")
    if any(
        o.get("status") != STATUS
        or set(o.get("professional_status", {})) != PROFESSIONAL_KEYS
        or set(o["professional_status"].values()) != {"unknown"}
        for o in raw["options"]
    ):
        raise ValueError("BC professional approval must remain unknown")
    source_review, comparison_path = comparison_source_review()
    source_furniture = json.loads(model3d.FURNITURE_FILE.read_text())
    for name, items in raw["profiles"].items():
        if (
            not name.startswith("study-bc-")
            or name in source_furniture["profiles"]
            or any(any(k in i for k in ("width_mm", "depth_mm", "height_mm")) for i in items)
        ):
            raise ValueError("BC profiles may not resize or replace normal catalog products")
    program = json.loads(model3d.PROGRAM_FILE.read_text())
    baseline = model3d.build_payload(program, load_overrides(), model3d.default_drawing_style(), review_path=comparison_path)
    options = []
    for spec in raw["options"]:
        if spec["building"] != spec["id"][0].upper():
            raise ValueError("BC comparison targets the wrong building")
        review, furniture = copy.deepcopy(source_review), copy.deepcopy(source_furniture)
        patch = spec["patch"]
        if spec["id"].endswith("baseline") and patch:
            raise ValueError("BC baseline cannot be modified")
        if set(patch) - {"replace_building", "floors"}:
            raise ValueError("BC study patch exceeds its scope")
        if "replace_building" in patch:
            review["buildings"][spec["building"]] = copy.deepcopy(patch["replace_building"])
        for fid, fp in patch.get("floors", {}).items():
            if fid not in review["buildings"][spec["building"]]["floors"]:
                raise ValueError("BC comparison targets an unknown floor")
            for k, v in fp.items():
                if k not in {"rooms", "connections", "entry", "additional_entries", "stair_landing_space"}:
                    raise ValueError("BC floor patch exceeds geometry scope")
                if k == "rooms":
                    review["buildings"][spec["building"]]["floors"][fid]["rooms"].update(copy.deepcopy(v))
                else:
                    review["buildings"][spec["building"]]["floors"][fid][k] = copy.deepcopy(v)
        furniture["profiles"].update(copy.deepcopy(raw["profiles"]))
        if patch:
            # Historical/main v5 annotations have different obligations. The
            # comparison uses the independent checks below, not false adoption.
            review["id"] = raw["id"] + ":" + spec["id"]
            review.pop("fengshui_minimal", None)
            review["buildings"][spec["building"]].pop("ritual_access", None)
        payload = (
            baseline
            if not patch
            else model3d.build_payload(
                program, load_overrides(), model3d.default_drawing_style(), review_path=comparison_path,
                review_data=review, furniture_data=furniture
            )
        )
        building = next(b for b in payload["buildings"] if b["id"] == spec["building"])
        essential_products(building, spec["id"])
        plans = next(b for b in plan_data(payload)["buildings"] if b["id"] == spec["building"])
        for floor in plans["floors"]:
            floor["plan_file"] = spec["id"] + "_" + floor["id"] + ".svg"
        unresolved = [
            {"room_id": r["id"], "item_id": i["id"], "issues": i["placement"]["issues"]}
            for f in plans["floors"]
            for r in f["rooms"]
            for i in r["furniture"]
            if i["placement"]["issues"]
        ]
        geometry = review_geometry(building, spec["id"])
        geometry["program_screen"] = program_limits(building, spec["id"])
        for floor in plans["floors"]:
            if (floor["width_mm"], floor["depth_mm"]) != (6000, 17630) or sum(
                r["geometry"]["w_mm"] * r["geometry"]["h_mm"] for r in floor["rooms"]
            ) != 6000 * 17630:
                raise ValueError("BC comparison loses the bounded full-floor coverage")
        frontage = next(r for r in plans["floors"][0]["rooms"] if r["key"] == "garage")
        if (
            frontage["geometry"] != {"x_mm": 0, "y_mm": 0, "w_mm": 6000, "h_mm": 3900}
            or not frontage["outdoor"]
            or frontage["furniture"]
        ):
            raise ValueError("BC comparison may not occupy the clear frontage")
        if spec["id"] == "b-strict" and check_furniture:
            building["layout_review"]["ritual_access"] = copy.deepcopy(source_review["buildings"]["B"]["ritual_access"])
            flow = build_bc_flow_checks([building])[0]
            geometry["transport"] = flow["transport"]
            # Refresh plans after adding the actual transport annotations.
            plans = next(b for b in plan_data(payload)["buildings"] if b["id"] == "B")
            for floor in plans["floors"]:
                floor["plan_file"] = spec["id"] + "_" + floor["id"] + ".svg"
        changed_issues = [
            i
            for i in unresolved
            if spec["id"] in {"b-strict", "c-side-bed"}
            or spec["id"] == "c-wet-stack"
            and i["room_id"]
            in {
                "C:floor-1:elder",
                "C:floor-2:guestroom2f",
                "C:floor-2:kitchen2f",
                "C:floor-2:bath2f",
                "C:floor-3:bath3f",
                "C:floor-3:dry-study",
            }
        ]
        declared_pending = {"C:floor-2:guestroom2f:furniture:wardrobe"} if spec["id"] == "c-wet-stack" else set()
        if check_furniture and any(i["item_id"] not in declared_pending for i in changed_issues):
            raise ValueError(
                "Unresolved changed comparison furniture: " + json.dumps(changed_issues, ensure_ascii=False)
            )
        # One renderer and one building. Do not leak A's MDF or claim that this
        # unadopted standalone option has changed the shared ABC main output.
        payload = copy.deepcopy(payload)
        payload["buildings"] = [building]
        payload["facade"]["buildings"] = [b for b in payload["facade"]["buildings"] if b["id"] == spec["building"]]
        payload["compare"] = {"available": False}
        payload["layout_review"]["status"] = STATUS
        payload["layout_review"]["id"] = raw["id"] + ":" + spec["id"]
        payload["layout_review"].pop("mdf_study", None)
        payload["layout_review"].pop("fengshui_minimal", None)
        payload["layout_review"]["checks"] = [
            c
            for c in payload["layout_review"].get("checks", [])
            if c.get("building") == spec["building"] or c.get("id", "").startswith(spec["building"] + "-")
        ]
        payload["layout_review"]["hvac_routes"] = [
            r for r in payload["layout_review"]["hvac_routes"] if r["id"].startswith(spec["building"] + "-")
        ]
        payload["bc_option"] = {
            "id": spec["id"],
            "label": spec["label"],
            "status": STATUS,
            "geometry_review": geometry,
            "tradeoffs": spec["tradeoffs"],
        }
        items = [i for f in building["floors"] for c in f["cells"] for i in c.get("furniture", [])]
        payload["furniture"]["items"] = len(items)
        payload["furniture"]["rooms"] = sum(bool(c.get("furniture")) for f in building["floors"] for c in f["cells"])
        payload["furniture"]["basis_counts"] = {
            k: sum(i["basis"] == k for i in items) for k in payload["furniture"]["basis_counts"]
        }
        active = [c for f in building["floors"] for c in f["cells"] if c.get("tour_active")]
        counts = {k: sum(c["provenance"] == k for c in active) for k in ("auto", "declared", "measured")}
        payload["provenance"] = {
            "cells": counts,
            "total": len(active),
            "auto_pct": round(100 * counts["auto"] / len(active), 1),
        }
        payload["overlaps"] = {
            k: [h for h in v if h.get("building") == spec["building"]] for k, v in payload["overlaps"].items()
        }
        options.append(
            {
                **{k: v for k, v in spec.items() if k != "patch"},
                "plans": plans,
                "geometry_review": geometry,
                "unresolved_furniture": unresolved,
                "model": payload,
            }
        )
    sources = [
        comparison_path,
        ROOT / "scripts/lib/model3d_space_efficiency.py",
        SOURCE,
        model3d.REVIEW_FILE,
        model3d.FURNITURE_FILE,
        model3d.PROGRAM_FILE,
        model3d.PHYSICAL_ITEMS_FILE,
        model3d.FACADE_FILE,
        model3d.REQUIREMENTS_FILE,
        ROOT / "inputs/dimensions.json",
        Path(__file__),
        ROOT / "scripts/export_model_3d.py",
        *sorted((ROOT / "house_design/rendering").glob("*.py")),
        model3d.TEMPLATE_FILE,
        model3d.FACADE_JS_FILE,
        model3d.THREE_FILE,
        *sorted((ROOT / "scripts/lib").glob("*.py")),
        *sorted((ROOT / "scripts/templates").glob("bc-options*")),
    ]
    return {
        **{k: v for k, v in raw.items() if k not in {"profiles", "options"}},
        "baseline_reference": str(comparison_path.relative_to(ROOT)),
        "source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        "options": options,
    }


def render_study_plan(option: dict, floor: dict) -> str:
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    names = {"public-entry": "公共走道", "rear-hall": "共用前平台", "altar-backing": "乾式祭祀收納",
             "corridor1": "搬轎通道", "rear-corridor": "後通道", "garage": "3.9m通行帶"}
    labels = {r["key"]: names.get(r["key"], r["name"].split("（")[0][:8]) for r in floor["rooms"]}
    tree = ET.fromstring(
        render_plan(option["building"], floor, room_labels=labels, viewer_url="../bc-options-3d.html?scheme=" + option["id"])
    )
    tree.set("data-study-option", option["id"])
    tree.set("data-study-status", STATUS)
    ns = {"s": "http://www.w3.org/2000/svg"}
    tree.find("s:title", ns).text = f"{option['label']} · {floor['label']}（比較用，未採用）"
    headings = tree.findall("s:text", ns)
    headings[0].text = f"{option['building']} 棟 · {floor['id'].replace('floor-', '')}層比較 · 道路 ↑"
    headings[1].text = "比較用，未採用；原需求缺口及專業查核尚未完成。"
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(tree, encoding="unicode") + "\n"


def main() -> None:
    study = build_study()
    directory = OUTPUT / "bc-options"
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {**study, "options": [{k: v for k, v in o.items() if k != "model"} for o in study["options"]]}
    (directory / "layout.js").write_text("window.HOUSE_BC_OPTIONS = " + encode_html_json(manifest) + ";\n")
    sections = []
    for o in study["options"]:
        links = []
        for floor in o["plans"]["floors"]:
            (directory / floor["plan_file"]).write_text(render_study_plan(o, floor))
            links.append(
                f'<li><a href="bc-options/{floor["plan_file"]}" target="_blank" rel="noopener">{html.escape(floor["label"])} 等比例圖（放大）</a> · <a href="bc-options-3d.html?scheme={o["id"]}#mode=tour&amp;building={o["building"]}&amp;floor={floor["id"]}&amp;view=plan">同源 3D</a></li>'
            )
        tradeoffs = "".join("<li>" + html.escape(t) + "</li>" for t in o["tradeoffs"])
        sections.append(
            f'<section id="{o["id"]}"><h2>{html.escape(o["label"])}</h2><p>{html.escape(o["summary"])}</p><p class="warning">比較用，未採用；不代表全部原需求或專業查核已滿足。</p><ul>{tradeoffs}</ul><ul>{"".join(links)}</ul><figure><figcaption>一樓比較預覽；放大及上層圖請用上方連結。</figcaption><object type="image/svg+xml" data="bc-options/{o["plans"]["floors"][0]["plan_file"]}" aria-label="{html.escape(o["label"])}一樓比較圖"><a href="bc-options/{o["plans"]["floors"][0]["plan_file"]}">開啟平面圖</a></object></figure><details><summary>實際幾何初篩／未解項目</summary><pre>{html.escape(json.dumps(o["geometry_review"], ensure_ascii=False, indent=2))}</pre><pre>{html.escape(json.dumps(o["unresolved_furniture"], ensure_ascii=False, indent=2))}</pre></details></section>'
        )
    template = (ROOT / "scripts/templates/bc-options.html").read_text()
    (OUTPUT / "bc-options.html").write_text(template.replace("__OPTIONS__", "\n".join(sections)))
    controls = (ROOT / "scripts/templates/bc-options-controls.html").read_text()
    bootstrap = (ROOT / "scripts/templates/bc-options-bootstrap.js").read_text()
    models = {
        "bc_options": {
            "default_option": study["default_option"],
            "options": [
                {"id": o["id"], "label": o["label"], "building": o["building"], "model": o["model"]}
                for o in study["options"]
            ],
        }
    }
    (OUTPUT / "bc-options-3d.html").write_text(
        model3d.render_html(models, model3d.three_source()[0], study_controls=controls, study_bootstrap=bootstrap)
    )
    print("BC comparisons (not adopted): structured/candidates/bc-options.html")
    for o in study["options"]:
        print(
            o["id"],
            "pending items:",
            len(o["unresolved_furniture"]),
            "brief area shortfalls:",
            sum(a["state"] == "brief-area-shortfall" for a in o["geometry_review"]["program_screen"]["areas"]),
        )


if __name__ == "__main__":
    main()

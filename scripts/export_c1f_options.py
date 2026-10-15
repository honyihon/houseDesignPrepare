#!/usr/bin/env python3
"""Export isolated, reversible C1F bathroom/daylight comparisons, never adopt them."""

from __future__ import annotations

import copy
import hashlib
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
from lib.model3d_plan import plan_data, render_plan  # noqa: E402

from house_design.rendering import encode_html_json  # noqa: E402

OPTIONS_FILE = ROOT / "inputs/c1f-bath-daylight-options.json"
OUTPUT = ROOT / "structured/candidates"
TEMPLATES = ROOT / "scripts/templates"
SCHEMA = "house-c1f-options-v1"
PRESERVED = {"garage", "kitchen", "stair1f", "sideyard", "sliding-door", "elder", "elder-bath", "service"}


def _visitor_route(floor: dict, option: dict) -> dict:
    rooms = {r["key"]: r for r in floor["rooms"]}
    route = option["visitor_route"]
    graph = {key: set() for key in rooms}
    for key, room in rooms.items():
        for door in room["features"]["doors"] + room["features"]["open_connections"]:
            if door["neighbor"]:
                graph[key].add(door["neighbor"].split(":")[-1])
    if (
        not route
        or route[0] not in rooms
        or not any(d["neighbor"] is None for d in rooms[route[0]]["features"]["doors"])
    ):
        raise ValueError("Visitor route must start at the proposed exterior entry")
    if any(b not in graph.get(a, set()) for a, b in zip(route, route[1:], strict=False)):
        raise ValueError("Visitor route has a nonadjacent door or opening")
    target = option["public_bath_key"]
    if target and (route[-1] != target or rooms[target]["kind"] != "bath"):
        raise ValueError("Visitor route must end at the ordinary public bathroom")
    # Independent traversal must not use the elder bedroom or its private bath.
    reached, queue = {route[0]}, deque([route[0]])
    while queue:
        for key in graph[queue.popleft()]:
            if key not in reached and rooms[key]["kind"] != "bedroom" and key not in {"elder", "elder-bath"}:
                reached.add(key)
                queue.append(key)
    avoids = bool(target and target in reached and not any(key in {"elder", "elder-bath"} for key in route))
    if target and not avoids:
        raise ValueError("Public bathroom route crosses a private bedroom")
    return {
        "room_keys": route,
        "room_names": [rooms[key]["name"] for key in route],
        "avoids_elder_bedroom": avoids,
        "status": "door-graph-only-not-clearance-proof",
    }


def _c_model(payload: dict, option: dict) -> dict:
    """Only C is loaded in the study's one renderer; never fake an ABC main variant."""
    result = copy.deepcopy(payload)
    result["buildings"] = [b for b in result["buildings"] if b["id"] == "C"]
    result["facade"]["buildings"] = [b for b in result["facade"]["buildings"] if b["id"] == "C"]
    result["compare"] = {"available": False}
    result["overlaps"] = {
        key: [r for r in value if r.get("building") == "C"] for key, value in result["overlaps"].items()
    }
    result["layout_review"]["hvac_routes"] = [
        r for r in result["layout_review"]["hvac_routes"] if r["id"].startswith("C-")
    ]
    result["layout_review"]["checks"] = [r for r in result["layout_review"]["checks"] if r["id"].startswith("C-")]
    result["layout_review"]["status"] = "comparison-only-not-adopted"
    result["layout_review"].pop("mdf_study", None)  # A-only study must not leak into C comparisons.
    result["source"]["c1f_options"] = "inputs/c1f-bath-daylight-options.json"
    result["study_option"] = {"id": option["id"], "label": option["label"], "status": "comparison-only-not-adopted"}
    cells = [c for f in result["buildings"][0]["floors"] for c in f["cells"]]
    items = [i for c in cells for i in c["furniture"]]
    result["furniture"]["items"] = len(items)
    result["furniture"]["rooms"] = sum(bool(c["furniture"]) for c in cells)
    result["furniture"]["basis_counts"] = {
        basis: sum(i["basis"] == basis for i in items) for basis in result["furniture"]["basis_counts"]
    }
    result["provenance"]["total"] = sum(not c.get("proposal_only") for c in cells)
    result["provenance"]["cells"] = {
        p: sum(c["provenance"] == p and not c.get("proposal_only") for c in cells)
        for p in result["provenance"]["cells"]
    }
    result["provenance"]["auto_pct"] = round(
        100 * result["provenance"]["cells"].get("auto", 0) / max(1, result["provenance"]["total"]), 1
    )
    return result


def build_study(data: dict | None = None) -> dict:
    raw = copy.deepcopy(data) if data is not None else json.loads(OPTIONS_FILE.read_text(encoding="utf-8"))
    if (
        raw.get("schema") != SCHEMA
        or raw.get("status") != "comparison-only-not-adopted"
        or raw.get("active_design") != "baseline"
    ):
        raise ValueError("Study must remain a comparison, with baseline as the active design")
    if [o["id"] for o in raw["options"]] != ["baseline", "bath-front", "front-living"]:
        raise ValueError("Unexpected C1F comparison option IDs")
    from lib.model3d_space_efficiency import comparison_source_review
    source_review, comparison_path = comparison_source_review()
    source_furniture = json.loads(model3d.FURNITURE_FILE.read_text(encoding="utf-8"))
    for profile, items in raw["profiles"].items():
        if not profile.startswith("study-c-") or profile in source_furniture["profiles"]:
            raise ValueError("Study furniture must use independent C comparison profiles")
        if any(any(k in item for k in ("width_mm", "depth_mm", "height_mm")) for item in items):
            raise ValueError("Study must not override or shrink catalogue dimensions")
    program = json.loads(model3d.PROGRAM_FILE.read_text(encoding="utf-8"))
    baseline = model3d.build_payload(program, load_overrides(), model3d.default_drawing_style(), review_path=comparison_path)
    base_floor = source_review["buildings"]["C"]["floors"]["floor-1"]
    options = []
    for spec in raw["options"]:
        if any(spec.get(key) is not None for key in ("public_bath_verified", "daylight_verified", "plumbing_verified")):
            raise ValueError("Unverified professional conditions must stay unknown")
        review, furniture = copy.deepcopy(source_review), copy.deepcopy(source_furniture)
        patch = spec["patch"]
        if set(patch) - {"rooms", "connections", "entry"}:
            raise ValueError("Study patch exceeds C1F scope")
        if spec["id"] == "baseline" and patch:
            raise ValueError("Baseline cannot have a comparison patch")
        floor = review["buildings"]["C"]["floors"]["floor-1"]
        for key, room in patch.get("rooms", {}).items():
            if key in PRESERVED or key not in {"living", "dining", "entrance", "public-bath"}:
                raise ValueError("Study cannot modify preserved care, core, frontage or equipment rooms")
            floor["rooms"][key] = copy.deepcopy(room)
        for key in ("connections", "entry"):
            if key in patch:
                floor[key] = copy.deepcopy(patch[key])
        for key in PRESERVED:
            if floor["rooms"][key] != base_floor["rooms"][key]:
                raise ValueError("Preserved main layout changed")
        furniture["profiles"].update(copy.deepcopy(raw["profiles"]))
        if spec["id"] != "baseline":
            # These alternatives retain their own partitions. Do not claim
            # the new main open-living obligation is satisfied by old options.
            open_plan = review["buildings"]["C"].pop("open_living", None)
            if open_plan:
                for room in floor["rooms"].values():
                    if room.get("group") == open_plan["group"]:
                        room.pop("group")
                        room.pop("role", None)
            review["id"] = raw["id"] + ":" + spec["id"]
            review["buildings"]["C"]["summary"] = "比較案，尚未採用。" + spec["summary"]
            review["buildings"]["C"]["assumptions"] = raw["conditions"] + spec["tradeoffs"]
            review["buildings"]["C"]["deferred"].append(
                {"state": "alternative", "note": "比較案尚未容納原玄關120cm鞋櫃；收納需求保留，不縮櫃。"}
            )
        payload = (
            baseline
            if spec["id"] == "baseline"
            else model3d.build_payload(
                program, load_overrides(), model3d.default_drawing_style(), review_path=comparison_path,
                review_data=review, furniture_data=furniture
            )
        )
        shared_floor = plan_data(payload)["buildings"][2]["floors"][0]
        shared_floor["plan_file"] = spec["id"] + ".svg"
        # A/B and all upper-floor coordinates remain main-layout data.
        for b, original in zip(payload["buildings"][:2], baseline["buildings"][:2], strict=True):
            if b != original:
                raise ValueError("C study unexpectedly changed A or B")
        for upper, original in zip(
            payload["buildings"][2]["floors"][1:], baseline["buildings"][2]["floors"][1:], strict=True
        ):
            if [(c["id"], c["tour_mm"], c["furniture"]) for c in upper["cells"]] != [
                (c["id"], c["tour_mm"], c["furniture"]) for c in original["cells"]
            ]:
                raise ValueError("C study unexpectedly changed an upper-floor room or product")
        route = _visitor_route(shared_floor, spec)
        cells = {r["key"]: r for r in shared_floor["rooms"]}

        def area(key: str, cells: dict = cells) -> float:
            return round(cells[key]["geometry"]["w_mm"] * cells[key]["geometry"]["h_mm"] / 1e6, 2)

        unresolved = [
            {"room": r["name"], "item": i["label"], "issues": i["placement"]["issues"]}
            for r in shared_floor["rooms"]
            for i in r["furniture"]
            if i["placement"]["issues"]
        ]
        if spec["id"] != "baseline" and unresolved:
            raise ValueError(f"Unresolved comparison furniture in {spec['id']}: {unresolved}")
        pair = next(r for r in payload["layout_review"]["hvac_routes"] if r["id"] == "C-AC01")
        options.append(
            {
                **{k: copy.deepcopy(v) for k, v in spec.items() if k != "patch"},
                "route": route,
                "floor": shared_floor,
                "areas_sqm": {
                    "living": area("living"),
                    "dining": area("dining"),
                    "entrance": area("entrance"),
                    "public_bath": area("public-bath") if spec["public_bath_key"] else 0,
                },
                "windows": [
                    {
                        "room": r["name"],
                        "key": r["key"],
                        "face": r["features"]["window_face"],
                        "width_mm": r["features"]["window_mm"],
                    }
                    for r in shared_floor["rooms"]
                    if r["features"]["window_face"]
                ],
                "hvac": {
                    k: copy.deepcopy(pair[k])
                    for k in (
                        "id",
                        "outdoor_room",
                        "estimated_routed_length_mm",
                        "elevation_difference_mm",
                        "compliance",
                    )
                },
                "unresolved_furniture": unresolved,
                "model": _c_model(payload, spec),
            }
        )
    sources = [
        comparison_path,
        ROOT / "scripts/lib/model3d_space_efficiency.py",
        OPTIONS_FILE,
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
        ROOT / "scripts/lib/model3d_plan.py",
        ROOT / "scripts/lib/model3d_review.py",
        ROOT / "scripts/lib/model3d_placement.py",
        ROOT / "scripts/lib/model3d_tour.py",
        ROOT / "scripts/lib/model3d_facade.py",
        ROOT / "scripts/lib/model3d_functions.py",
        ROOT / "scripts/lib/model3d_mdf.py",
        ROOT / "scripts/lib/model3d_bc_flow.py",
        ROOT / "scripts/lib/model3d_fengshui.py",
        ROOT / "inputs/a-mdf-under-stair.json",
        ROOT / "scripts/lib/furniture_layout.py",
        ROOT / "scripts/lib/dimension_overrides.py",
        ROOT / "scripts/lib/standards.py",
        ROOT / "scripts/config/residential_defaults_tw.json",
        ROOT / "scripts/export_top1_svgs.py",
        ROOT / "scripts/lib/html_parametric_compare.py",
        ROOT / "house_design/contracts.py",
        ROOT / "house_design/physical_items.py",
        *sorted((ROOT / "house_design/rendering").glob("*.py")),
        ROOT / "scripts/export_model_3d.py",
        *sorted(TEMPLATES.glob("c1f-options*")),
    ]
    return {
        **{k: copy.deepcopy(v) for k, v in raw.items() if k not in {"options", "profiles"}},
        "baseline_reference": str(comparison_path.relative_to(ROOT)),
        "source_hashes": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        "options": options,
    }


def manifest(study: dict) -> dict:
    return {
        **{k: v for k, v in study.items() if k != "options"},
        "options": [{k: v for k, v in option.items() if k != "model"} for option in study["options"]],
    }


def render_study_plan(option: dict) -> str:
    """Same SVG geometry, with short mobile-readable labels and explicit study status."""
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    labels = {
        "garage": "前緣通行（不計車位）",
        "living": "客廳",
        "dining": "四人餐廳",
        "entrance": "玄關／前室",
        "public-bath": "公衛（未核）",
        "kitchen": "一字廚房",
        "stair1f": "樓梯／乾通道",
        "sideyard": "IDF壁龕",
        "sliding-door": "照護前室",
        "elder": "孝親房",
        "elder-bath": "孝親套衛",
        "service": "後檢修帶",
    }
    tree = ET.fromstring(render_plan("C", option["floor"], room_labels=labels,
        viewer_url="../c1f-options-3d.html?scheme=" + option["id"]))
    ns = {"s": "http://www.w3.org/2000/svg"}
    tree.set("data-study-option", option["id"])
    tree.set("data-study-status", "comparison-only-not-adopted")
    tree.find("s:title", ns).text = "C 一樓 · " + option["label"] + "（比較用，未採用）"
    headings = tree.findall("s:text", ns)
    label = {"baseline": "現況", "bath-front": "方案1", "front-living": "方案2"}[option["id"]]
    headings[0].text = "C 棟 1F · " + label + "（比較用）· 道路 ↑"
    headings[1].text = "比較用，未採用／未核；同源 3D。尺寸不是地籍或完成面。"
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(tree, encoding="unicode") + "\n"


def main() -> None:
    study = build_study()
    directory = OUTPUT / "c1f-options"
    directory.mkdir(parents=True, exist_ok=True)
    for option in study["options"]:
        svg = render_study_plan(option)
        (directory / option["floor"]["plan_file"]).write_text(svg, encoding="utf-8")
    (directory / "layout.js").write_text(
        "window.HOUSE_C1F_OPTIONS = " + encode_html_json(manifest(study)) + ";\n", encoding="utf-8"
    )
    page = (TEMPLATES / "c1f-options.html").read_text(encoding="utf-8")
    (OUTPUT / "c1f-options.html").write_text(page, encoding="utf-8")
    models = {
        "c1f_options": {
            **{k: v for k, v in study.items() if k != "options"},
            "options": [{"id": o["id"], "label": o["label"], "model": o["model"]} for o in study["options"]],
        }
    }
    controls = (TEMPLATES / "c1f-options-controls.html").read_text(encoding="utf-8")
    bootstrap = (TEMPLATES / "c1f-options-bootstrap.js").read_text(encoding="utf-8")
    html = model3d.render_html(models, model3d.three_source()[0], study_controls=controls, study_bootstrap=bootstrap)
    (OUTPUT / "c1f-options-3d.html").write_text(html, encoding="utf-8")
    print("C1F comparisons (not adopted): structured/candidates/c1f-options.html")
    for option in study["options"]:
        print(
            f"  {option['id']}: {option['areas_sqm']}; AC01 {option['hvac']['estimated_routed_length_mm'] / 1000:g}m (unverified)"
        )


if __name__ == "__main__":
    main()

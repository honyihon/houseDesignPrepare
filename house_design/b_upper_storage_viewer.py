"""Serialize B polygon surfaces and source-height display objects; no scene runtime."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

from house_design.b_upper_replan import rect
from house_design.contracts import ContractError, stable_hash
from house_design.project_status import digest, read_public_json

CONFIG = "inputs/b-upper-storage-3d.json"
SOURCE = "structured/coordination/b-upper-storage-sync-v1/review.json"
LEGACY = "structured/candidates/kaohsiung-house-options-3d.html"
OUT = "structured/coordination/b-upper-storage-3d-v1"
ARCHIVE = "b-upper-storage-3d.zip"
DOC = "Docs/b-upper-storage-3d-v1.md"
HTML = "scripts/templates/b-upper-storage-viewer.html"
RUNTIME = "scripts/templates/b-upper-storage-viewer.js"
CHECKER = "scripts/check_b_upper_storage_3d_playwright.cjs"


def require(value, message):
    if not value:
        raise ContractError(message)


def polygons(shape):
    parts = [shape] if shape.geom_type == "Polygon" else list(shape.geoms)
    return [{"outer": [list(p) for p in s.exterior.coords],
        "holes": [[list(p) for p in ring.coords] for ring in s.interiors]} for s in parts if not s.is_empty]


def surface(floor):
    """Never use a whole stair-room rectangle as an opaque floor."""
    st = floor["stair_interface"]
    if floor["id"] == "floor-4":
        enclosure = next(r["rect_mm"] for r in floor["fixed"] if r["id"] == "roof-stair")
        base = rect([0, 0, 6000, 17630]).difference(unary_union([rect(enclosure), rect(floor["roof_opening_mm"])]))
        pads = [Polygon(p) for p in st["arrival_polygons_mm"]]
    else:
        base = unary_union([Polygon(r["polygon_mm"]) for r in floor["rooms"] if r["id"] != "stair"])
        pads = [Polygon(st["arrival_polygon_mm"])]
        if st.get("side_threshold_polygon_mm"):
            pads.append(Polygon(st["side_threshold_polygon_mm"]))
    return unary_union([base, *pads])


def stair_objects(floor, q3):
    st = floor["stair_interface"]
    incoming = (q3["original_stairs_by_floor"]["floor-1"] if floor["id"] == "floor-2"
        else copy.deepcopy(q3["original_stairs_by_floor"]["floor-2"]))
    if floor["id"] != "floor-2":
        incoming["footprint"] = copy.deepcopy(q3["upper_stairs"]["primary"]["footprint"])
        incoming["geometry"]["middle_landing_mm"] = q3["upper_stairs"]["primary"]["middle_landing_mm"]
        incoming["base_mm"] = floor["base_mm"]-3000
    records, landings = [], []
    for role, source, treads in [("incoming", incoming, st["incoming_treads"]),
            ("outgoing", st.get("outgoing"), st.get("outgoing_treads", []))]:
        if source is None:
            continue
        rise = source["height_mm"]/source["geometry"]["risers"]
        records += [{"id": role+":"+t["id"], "role": role, "rect_mm": t["rect_mm"],
            "top_mm": t["top_z_mm"], "height_mm": rise} for t in treads]
        fp, g = source["footprint"], source["geometry"]
        landings.append({"id": role+":middle", "role": role, "rect_mm": [fp["x_mm"],
            fp["y_mm"]+g["departure_offset_mm"]+g["run_mm"], fp["w_mm"], g["middle_landing_mm"]],
            "top_mm": source["base_mm"]+source["height_mm"]/2, "surface_only_no_slab_thickness_claim": True})
    return records, landings


def display_objects(floor, state, refs, legacy):
    objects = []
    for original in state["objects"]:
        obj = {"source": copy.deepcopy(original), "key": original["key"], "label": original["label"],
            "rect_mm": copy.deepcopy(original["rect_mm"]), "height_mm": None, "mount_mm": 0,
            "height_basis": "source-footprint-only", "height_reference": None}
        if original.get("storage_case"):
            obj.update(height_mm=original["height_mm"], height_basis="owner-storage-proposal")
        elif original["key"] in refs:
            rid = refs[original["key"]]
            item = legacy[rid]
            require(sorted(original["rect_mm"][2:]) == sorted([item["width_mm"], item["depth_mm"]]),
                "Legacy height body size differs: "+original["key"])
            obj.update(height_mm=item["height_mm"], mount_mm=item.get("mount_height_mm", 0),
                height_basis="same-size-legacy-concept-envelope-not-measured", height_reference=rid)
        objects.append(obj)
    return objects


def build(root):
    root, cache = Path(root), {}
    cfg = read_public_json(root, CONFIG)
    require(cfg["schema"] == "house-b-upper-storage-3d-v1" and cfg["adopted"] is False
        and cfg["boundary_is_annotation_not_actual_wall"] is True and cfg["boundary_display_height_mm"] == 1100
        and cfg["default_floor"] == "B-2F" and cfg["default_state"] == "storage", "Preserve B viewer display scope")
    for name, expected in cfg["pinned_sources"].items():
        require(digest(root, name, cache) == expected, "Frozen B viewer input changed: "+name)
    sync = read_public_json(root, SOURCE)
    require(sync["report_hash"] == stable_hash({k: v for k, v in sync.items() if k != "report_hash"}),
        "B synchronized report seal differs")
    for name, expected in sync["source_hashes"].items():
        require(digest(root, name, cache) == expected, "B synchronized source drift: "+name)
    controls = read_public_json(root, "inputs/abc-next-protected-controls.json")["hashes"]
    for name, expected in controls.items():
        require(digest(root, name, cache) == expected, "Protected original changed: "+name)
    match = re.search(r"^\s*var DATA = (.+);\s*$", (root/LEGACY).read_text(), re.M)
    require(match is not None, "Missing frozen B reference-height model")
    data = json.loads(match[1])["kaohsiung_options"]
    option = next(o for o in data["options"] if o["id"] == cfg["reference_option"])
    model = next(s["model"] for s in option["states"] if s["id"] == cfg["reference_use"])
    legacy = {i["id"]: i for f in model["buildings"][0]["floors"] for c in f["cells"] for i in c["furniture"]}
    q3 = read_public_json(root, sync["config"]["sources"]["floor3"])
    plans, floors = [], []
    for floor in sync["floors"]:
        shape = surface(floor)
        st = floor["stair_interface"]
        forbidden = [t["rect_mm"] for t in st["incoming_treads"]
            if floor["id"] != "floor-2" or t["id"].startswith("right")]
        if floor["id"] == "floor-4":
            forbidden += [floor["roof_opening_mm"], st["stairwell_keep_open_mm"]]
        require(all(shape.intersection(rect(r).buffer(-.2)).area < .1 for r in forbidden),
            "B viewer would cap an incoming tread or opening")
        stairs, middle = stair_objects(floor, q3)
        states = []
        for state in floor["states"]:
            name = state["plan_file"]
            path = "structured/coordination/b-upper-storage-sync-v1/"+name
            plans.append({"file": name, "source": path, "sha256": digest(root, path, cache)})
            states.append({**copy.deepcopy(state),
                "display_objects": display_objects(floor, state, cfg["height_references"].get(floor["key"], {}), legacy)})
        anchors = []
        for room in floor["rooms"]:
            p = Polygon(room["polygon_mm"]).representative_point()
            anchors.append({"id": room["id"], "label": room["label"], "point_mm": [p.x, p.y]})
        floors.append({"id": floor["key"], "base_mm": floor["base_mm"], "source_floor": copy.deepcopy(floor),
            "surface_polygons_mm": polygons(shape), "surface_area_mm2": shape.area, "forbidden_rects_mm": forbidden,
            "stairs": stairs, "middle_landings": middle, "room_anchors": anchors, "states": states})
    entries = copy.deepcopy(sync["entry_options"])
    names = [CONFIG, SOURCE, LEGACY, DOC, HTML, RUNTIME, CHECKER, "house_design/b_upper_storage_viewer.py",
        "scripts/export_b_upper_storage_viewer.py", "scripts/lib/model3d_plan.py", "house_design/plan_readability.py",
        "scripts/templates/upper-floor-storage-viewer.js",
        "assets/vendor/three/three.min.js", "assets/vendor/three/LICENSE", "assets/vendor/three/VERSION.txt",
        "inputs/abc-next-protected-controls.json", *sync["source_hashes"], *cfg["pinned_sources"], *[p["source"] for p in plans]]
    report = {"schema": "house-b-upper-storage-viewer-v1", "date": cfg["date"], "display_revision": 2,
        "config": cfg, "default_floor": cfg["default_floor"], "default_state": cfg["default_state"],
        "source_sync_report_sha256": digest(root, SOURCE, cache), "source_sync_report_hash": sync["report_hash"],
        "floors": floors, "plans": plans, "entry_options": entries, "known_limits": copy.deepcopy(sync["known_limits"]),
        "summary": {"floor_variants": 4, "states": 8, "storage_cases": 4, "ground_entry_options": 2, "ground_reference_states": 6},
        "main_3d_changed": False, "accepted_viewers_changed": False, "protected_controls_unchanged": len(controls),
        "adopted": False, "professional_approval": "unknown", "construction_release": False,
        "rendered_qa": "not-run-owner-separate-terminal-required", "browser_plugin": "absent",
        "source_hashes": {n: digest(root, n, cache) for n in dict.fromkeys(names)}}
    report["report_hash"] = stable_hash(report)
    return report

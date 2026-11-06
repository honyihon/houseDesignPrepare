"""Merge selected C stair detail into the existing frozen comparison payload.

Only local snapshots are patched; no solver, full-scene generation or WebGL.
"""
from __future__ import annotations

import copy
import json
import re

from house_design.c_ac01_route import CONFIG as AC01_CONFIG
from house_design.c_ac01_route import RUNTIME as AC01_RUNTIME
from house_design.c_ac01_route import patch as patch_ac01
from house_design.c_stair_landing import build as stair_detail
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.frozen_kaohsiung import EXPECTED, MANIFEST, historical_artifact

BASE_REPORT = "structured/candidates/kaohsiung-house-options/review.json"
VIEWER = "structured/candidates/kaohsiung-house-options-3d.html"
INDEX = "structured/candidates/kaohsiung-house-options.html"
REPORT = "structured/candidates/kaohsiung-house-options/c-stair-integration.json"
RUNTIME = "scripts/templates/c-stair-merged-runtime.js"
SCHEMA = "house-c-stair-viewer-integration-v1"
BASE_SHA = "84f81465f280ec64931d29e49234b1dbcafc6b0b93a20b2a33f683e14f164fdf"


def frozen_study(root):
    if sha256_file(root/BASE_REPORT) != BASE_SHA:
        raise ContractError("Original comparison report changed; do not retarget it")
    report = read_json(root/BASE_REPORT)
    for name, digest in report["source_hashes"].items():
        if sha256_file(root/name) != digest:
            raise ContractError("Original comparison source changed: "+name)
    for name, digest in report["artifact_hashes"].items():
        path = historical_artifact(root, name, digest) if name in EXPECTED else root/name
        if sha256_file(path) != digest:
            raise ContractError("Original comparison artifact changed: "+name)
    source = historical_artifact(root, VIEWER, EXPECTED[VIEWER][1]).read_text()
    match = re.search(r"^\s*var DATA = (.+);\s*$", source, re.M)
    if match is None:
        raise ContractError("Missing frozen embedded comparison model")
    payload = json.loads(match[1])["kaohsiung_options"]
    study = copy.deepcopy(report)
    study.pop("artifact_hashes")
    for option in study["options"]:
        old = next(o for o in payload["options"] if o["id"] == option["id"])
        for state in option["states"]:
            state["model"] = next(s["model"] for s in old["states"] if s["id"] == state["id"])
    if stable_hash({k: v for k, v in study.items() if k not in {"generated_at", "report_hash"}}) != report["report_hash"]:
        raise ContractError("Original comparison model/report seal differs")
    return study, source


def _portal(cell, neighbor, face, lo, hi):
    """A reciprocal unobstructed opening at the old core boundary, not the new gate."""
    f, g = cell["tour_features"], cell["tour_mm"]
    along_x = face in {"front", "rear"}
    start, length = (g["x_mm"], g["w_mm"]) if along_x else (g["y_mm"], g["h_mm"])
    f["doors"] = [d for d in f["doors"] if not (d["neighbor"] == neighbor and d["face"] == face)]
    f["open_connections"] = [d for d in f["open_connections"] if not (d["neighbor"] == neighbor and d["face"] == face)]
    f["open_connections"].append({"face": face, "ratio": ((lo+hi)/2-start)/length,
        "width_mm": hi-lo, "neighbor": neighbor, "status": "selected-c-stair-integration-not-professionally-approved",
        "operation": "open", "label": "共享平台開口；可關門另在前方"})


def shift_routes(model, old_bases):
    floors = {f["id"]: f for f in model["buildings"][0]["floors"]}
    deltas = {fid: f["base_mm"]-old_bases[fid] for fid, f in floors.items()}
    routes = {}
    for floor in floors.values():
        for cell in floor["cells"]:
            if not cell.get("tour_active"):
                continue
            for unit in cell["tour_features"].get("hvac_units", []):
                if unit["id"] in routes:
                    continue
                route = copy.deepcopy(unit["route"])
                if len(route["polyline_mm"]) != 6:
                    raise ContractError("Unexpected C routing topology; do not guess an elevation")
                inside, outside = route["indoor_room"].split(":")[1], route["outdoor_room"].split(":")[1]
                for n, point in enumerate(route["polyline_mm"]):
                    point[2] += deltas[inside if n < 3 else outside]
                points = route["polyline_mm"]
                route["estimated_routed_length_mm"] = round(sum(sum(abs(a-b) for a, b in zip(p, q, strict=True))
                    for p, q in zip(points, points[1:], strict=False))+route["bend_service_allowance_mm"])
                route["elevation_difference_mm"] = abs(points[-1][2]-points[0][2])
                route["status"] = "integrated-elevation-coordinates-not-engineered"
                route["compliance"] = "unknown"
                routes[unit["id"]] = route

    def replace(value):
        if isinstance(value, dict):
            if value.get("id") in routes and "polyline_mm" in value:
                return copy.deepcopy(routes[value["id"]])
            return {k: replace(v) for k, v in value.items()}
        if isinstance(value, list):
            return [replace(v) for v in value]
        return value

    for k, v in list(model.items()):
        model[k] = replace(v)
    return routes


def patch_c_model(original, detail, ac01_cfg):
    model = copy.deepcopy(original)
    building = model["buildings"][0]
    floors = {f["id"]: f for f in building["floors"]}
    old_bases = {fid: f["base_mm"] for fid, f in floors.items()}
    for fid, floor in floors.items():
        floor["base_mm"] = detail["floor_bases_mm"][fid]
        if fid == "floor-1":
            floor["height_mm"] = 4000
    routes = shift_routes(model, old_bases)
    building = model["buildings"][0]
    floors = {f["id"]: f for f in building["floors"]}
    cells = {fid: {c["key"]: c for c in f["cells"] if c.get("tour_active")} for fid, f in floors.items()}
    _portal(cells["floor-1"]["stair1f"], "C:floor-1:living-hall", "front", 2900, 4000)
    _portal(cells["floor-1"]["stair1f"], "C:floor-1:living-right", "front", 4000, 5920)
    _portal(cells["floor-1"]["living-hall"], "C:floor-1:stair1f", "rear", 2900, 4000)
    _portal(cells["floor-1"]["living-right"], "C:floor-1:stair1f", "rear", 4000, 5920)
    _portal(cells["floor-2"]["stair2f"], "C:floor-2:living2f", "front", 3720, 5920)
    _portal(cells["floor-2"]["living2f"], "C:floor-2:stair2f", "rear", 3720, 5920)
    gates = next(o for o in detail["front_partition_comparison"]["options"] if o["selected"])["floor_details"]
    for fid, rooms in cells.items():
        stair = next(c for c in rooms.values() if c["tour_features"].get("stairs"))
        features = stair["tour_features"]
        features["reserved_mm"] = [r for r in features.get("reserved_mm", []) if r["kind"] != "stairs"
            and not (r["kind"] == "door-approach" and r["aabb"]["minY"] == 8960 and r["aabb"]["maxY"] == 9860)]
        surfaces = [copy.deepcopy(s) for s in detail["surfaces"] if s["storey"] == fid]
        if fid == "floor-2":
            # Draw the union once: left departure overlaps the shared arrival.
            for s in surfaces:
                if s["id"] == "floor-2:departure":
                    s["rect_mm"] = [3720, 9760, 1000, 270]
        # Disjoint floor pieces avoid both stairwell caps and coplanar z-fighting.
        floor_rects = [[2400, 8960, 1320, 4840]]
        if fid == "floor-1":
            floor_rects += [[5920, 8960, 80, 4840], [3720, 9760, 2200, 4040]]
        for n, floor_rect in enumerate(floor_rects):
            surfaces.insert(0, {"id": fid+":walkable-floor-"+str(n), "rect_mm": floor_rect,
                "top_z_mm": floors[fid]["base_mm"], "kind": "corridor-floor", "storey": fid})
        features["c_stair_surfaces"] = surfaces
        features["c_stair_surface_depth_mm"] = 150
        features["c_stair_full_floor_omitted"] = True
        if fid != "floor-4":
            next_fid = "floor-"+str(int(fid.rsplit("-", 1)[-1])+1)
            upper = next(s for s in detail["surfaces"] if s["storey"] == next_fid
                and s["kind"] in {"shared-landing", "departure", "roof-arrival"})
            x, y, w, depth = upper["rect_mm"]
            features["c_stair_context_arrival"] = {"id": fid+":next-arrival-context",
                "rect_mm": [x+w-1000, y, 1000, depth], "top_z_mm": upper["top_z_mm"],
                "only_when_this_floor_is_isolated": True}
        if fid == "floor-1":
            features["stair_geometry"].update(risers=24, riser_mm=4000/24, tread_mm=270,
                departure_offset_mm=730, run_mm=2970, shared_front_landing=True,
                fits_reserved_box="uses-full-shared-apron-not-a-standalone-730mm-landing")
        if fid in {"floor-1", "floor-2"}:
            features["c_front_gate"] = copy.deepcopy(next(g for g in gates if g["floor"] == fid))
        if fid == "floor-2":
            features["c_side_gate"] = {"closed_rect_mm": [2250, 9060, 100, 900],
                "open_rect_mm": [2250, 9960, 100, 900], "height_mm": 2100,
                "nominal_opening_mm": 900, "actual_clear_width_mm": None,
                "status": "existing-side-position-operable-symbol-product-and-clear-width-pending"}
    for fid, key, name in [
        ("floor-1", "living-hall", "客餐通行／前置門前室共用"),
        ("floor-1", "living-right", "前置門側共用前室（非獨立房）"),
        ("floor-2", "living2f", "二樓起居／前置門前室共用"),
    ]:
        cells[fid][key]["name"] = name
        cells[fid][key]["tour_features"]["c_shared_antechamber"] = {
            "partition_y_mm": 8550, "scope": "shared-floor-not-extra-floor-area", "finished_exclusive_area": "unknown"}
    model["c_stair_merge"] = {"revision": 1, "display_revision": 2, "selected_partition": "forward-closing-door",
        "owner_confirmed_layout": True, "complete_scheme_adopted": False,
        "detail_hash": stable_hash(detail), "floor_bases_mm": detail["floor_bases_mm"],
        "forbidden_second_floor_platform_mm": detail["second_floor_floor_level_platform_removed_mm"],
        "front_door_clear_width_mm": None, "side_door_clear_width_mm": None,
        "professional_approval": "unknown", "source_door_product": None,
        "unresolved": ["實際門組／淨寬／消防", "梁板洞口與護欄", "覆土降板及騎樓淨高", "C-AC01候選穿板、固定與冷凝排水待核"]}
    model["bc_option"]["label"] = "C｜4m24級＋前置可關門＋右景觀／左洗曬"
    model["bc_option"]["tradeoffs"] = [
        "屋主已確認前置可關門配置；完整方案未採用／專業未核，門組與實際淨寬未選定。",
        "1F4m、24級、270mm踏面；完整1000mm平台與前室共享200mm，2F到達面分開，孝親套衛及3F通道不縮。",
        "前門線y=8550；前門及2F側門可切換示意開關，沒有以普通滑門宣稱防火或隔音認證。",
        "右側9㎡景觀、左側單機洗曬保留；C-AC01室內機移至乾式前室右壁，採室內立管／二樓高位候選線，穿板、固定與排水仍待核。",
    ]
    model["bc_option"]["geometry_review"] = {**model["bc_option"]["geometry_review"],
        "c_stair_merged": True, "owner_selected_partition": "forward-closing-door", "rendered_qa": "not-run"}
    ac01 = patch_ac01(model, ac01_cfg)
    routes["C-AC01"] = ac01["route"]
    return model, routes


def build(root):
    study, text = frozen_study(root)
    detail = stair_detail(root)
    selected = detail["front_partition_comparison"]["owner_preference"]
    if selected != "forward-closing-door":
        raise ContractError("Owner selection must exist before merging")
    original = copy.deepcopy(study)
    option = next(o for o in study["options"] if o["id"] == "c-split")
    state = option["states"][0]
    state["model"], routes = patch_c_model(state["model"], detail, read_json(root/AC01_CONFIG))
    option["label"] = state["model"]["bc_option"]["label"]
    # Import after root setup in the CLI, as with the other bounded exporters.
    from lib.model3d_plan import plan_data

    state["plans"] = plan_data(state["model"])["buildings"][0]
    for floor in state["plans"]["floors"]:
        floor["plan_file"] = "c-split_integrated_"+floor["id"]+".svg"
    state["review"] = copy.deepcopy(state["model"]["bc_option"]["geometry_review"])
    for old, current in zip(original["options"], study["options"], strict=True):
        if old["id"] != "c-split" and old != current:
            raise ContractError("A/B or C original control was changed")
    before_model = next(o for o in original["options"] if o["id"] == "c-split")["states"][0]["model"]
    before_items = {i["id"]: i for f in before_model["buildings"][0]["floors"]
        for c in f["cells"] if c.get("tour_active") for i in c["furniture"]}
    after_items = {i["id"]: i for f in state["model"]["buildings"][0]["floors"]
        for c in f["cells"] if c.get("tour_active") for i in c["furniture"]}
    if before_items != after_items:
        raise ContractError("Original C furniture identities/sizes were changed")
    sources = {**study["source_hashes"], **detail["source_hashes"]}
    for name in [BASE_REPORT, MANIFEST, "house_design/c_stair_merge.py", RUNTIME,
            AC01_CONFIG, AC01_RUNTIME, "house_design/c_ac01_route.py",
            "scripts/merge_c_stair_into_3d.py", *[v[0] for v in EXPECTED.values()]]:
        sources[name] = sha256_file(root/name)
    study.update(integration_schema=SCHEMA, integration_revision=2, stair_display_revision=2, ac01_route_revision=1, rendered_qa="not-run",
        integration_status="owner-selected-c-layout-merged-professional-review-pending",
        original_frozen_report_sha256=BASE_SHA, source_hashes=sources,
        owner_selected_partition=selected, c_detail=detail,
        c_hvac_routes=routes, c_ac01_review=state["model"]["c_ac01_routing"], preserved_other_options=True,
        original_C_furniture_unchanged=True, full_scene_or_parent_regeneration=False)
    study["report_hash"] = stable_hash({k: v for k, v in study.items() if k not in {"generated_at", "report_hash"}})
    return study, text

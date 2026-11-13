"""Assemble frozen B P4/Q3/roof geometry and storage; no scene or solver run."""
from __future__ import annotations

import copy
from itertools import product
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

from house_design.b_ktv_stair_options import incoming_steps
from house_design.b_upper_replan import rect, sweep
from house_design.contracts import ContractError, stable_hash
from house_design.project_status import digest, read_public_json
from house_design.upper_floor_storage import check_storage, normalize_source

CONFIG = "inputs/b-upper-storage-sync.json"
OUT = "structured/coordination/b-upper-storage-sync-v1"
ARCHIVE = "b-upper-storage-sync.zip"
DOC = "Docs/b-upper-storage-sync-v1.md"


def require(condition, message):
    if not condition:
        raise ContractError(message)


def storage_objects(floor, case, state):
    """Overlay additions; a roof workbench replaces its original table exactly once."""
    objects = [{"key": r["id"]+":"+i["id"], "room": r["id"], **copy.deepcopy(i)}
        for r in floor["rooms"] for i in r["items"]
        if not (state == "storage" and r["id"] == case["room"] and i["id"] == case.get("reuse_item"))]
    if state == "storage":
        objects.append({"key": case["room"]+":"+case.get("reuse_item", "upper-floor-storage"),
            "id": case.get("reuse_item", "upper-floor-storage"), "room": case["room"],
            "label": case["label"], "rect_mm": copy.deepcopy(case["rect_mm"]),
            "operation_mm": copy.deepcopy(case["operation_mm"]), "height_mm": case["height_mm"],
            "storage_case": case["id"], "replaces_id": case.get("reuse_item")})
    require(len({i["key"] for i in objects}) == len(objects), "Duplicate B storage/table object")
    return objects


def check_stair_surfaces(floors):
    """Reject the known wrong full-width 2F pad and capped RF stairwell."""
    stairs, rf = floors[0]["stair_interface"], floors[2]["stair_interface"]
    landing = Polygon(stairs["arrival_polygon_mm"])
    right = [s for s in stairs["incoming_treads"] if s["id"].startswith("right")]
    covered = [s["id"] for s in right if landing.intersection(rect(s["rect_mm"])).area > .1]
    require(not covered, "B 2F landing covers incoming right treads")
    transfer = sweep(stairs["transfer_route_mm"], stairs["transfer_width_mm"])
    require(landing.buffer(.01).covers(transfer), "B 2F L-platform disconnects transfer route")
    third = floors[1]["stair_interface"]
    third_surface = unary_union([Polygon(third["arrival_polygon_mm"]), Polygon(third["side_threshold_polygon_mm"])])
    require(not [s for s in third["incoming_treads"] if third_surface.intersection(rect(s["rect_mm"])).area > .1],
        "B 3F arrival covers Q3 incoming treads")
    require(stairs["outgoing_treads"] == third["incoming_treads"]
        and third["outgoing_treads"] == rf["incoming_treads"], "B stair floors are from different revisions")
    surfaces = unary_union([Polygon(p) for p in rf["arrival_polygons_mm"]])
    require(surfaces.intersection(rect(rf["stairwell_keep_open_mm"])).area < .1, "B RF platform caps the stairwell")
    require(not [s for s in rf["incoming_treads"] if surfaces.intersection(rect(s["rect_mm"])).area > .1],
        "B RF platform covers Q3 treads")
    return {"floor2_incoming_right_tread_hits": covered, "floor2_transfer_inside_L_platform": True,
        "floor3_incoming_tread_hits": [], "RF_void_capped": False, "RF_incoming_tread_hits": [],
        "scope": "listed-platform-and-tread-projections-only-not-full-headroom-or-structure"}


def check_source_floor(floor, frame):
    polygons = [Polygon(r["polygon_mm"]) for r in floor["rooms"]]
    require(all(p.is_valid and frame.buffer(.01).covers(p) for p in polygons), "B polygon outside 32-ping study frame")
    if floor["id"] != "floor-4":
        union = unary_union(polygons)
        require(sum(p.area for p in polygons)-union.area < .1 and frame.symmetric_difference(union).area < .1,
            "B same-revision room partition overlaps or loses floor area")


def build(root):
    root, cache = Path(root), {}
    cfg = read_public_json(root, CONFIG)
    require(cfg["schema"] == "house-b-upper-storage-sync-v1" and cfg["adopted"] is False
        and cfg["frame_mm"] == [6000, 17630]
        and cfg["entry_options"] == ["b-rear-split", "b-front-split"]
        and cfg["ground_use_states"] == ["daily", "ritual", "carry"]
        and cfg["storage_states"] == ["original", "storage"]
        and cfg["roof_options"] == ["Q3-D1-front-heat-pump", "Q3-D2-rear-wet-pair"]
        and cfg["default_entry"] == "b-rear-split", "Preserve B entry, roof and storage alternatives")
    for name, expected in cfg["pinned_sources"].items():
        require(digest(root, name, cache) == expected, "Frozen B synchronization source changed: "+name)
    controls = read_public_json(root, "inputs/abc-next-protected-controls.json")["hashes"]
    for name, expected in controls.items():
        require(digest(root, name, cache) == expected, "Protected original changed: "+name)
    source = {key: read_public_json(root, name) for key, name in cfg["sources"].items()}
    p4, q3, roof, storage, snapshot = [source[k] for k in ["floor2", "floor3", "roof", "storage", "ground_snapshot"]]
    for role in ["floor2", "floor3", "roof"]:
        for name, expected in source[role]["source_hashes"].items():
            require(digest(root, name, cache) == expected, "B upstream source drift: "+name)
    cases = [c for c in storage["cases"] if c["building"] == "B"]
    require([c["id"] for c in cases] == ["B-2F", "B-3F", "B-RF-D1", "B-RF-D2"], "Preserve all four B storage cases")
    primary = q3["upper_stairs"]["primary"]
    outgoing = copy.deepcopy(q3["original_stairs_by_floor"]["floor-2"])
    outgoing["footprint"] = copy.deepcopy(primary["footprint"])
    outgoing["geometry"]["middle_landing_mm"] = primary["middle_landing_mm"]
    upper_incoming = copy.deepcopy(outgoing)
    upper_incoming["base_mm"] = 7000
    arrivals = q3["floor2_arrival_screen"]
    require(roof["q3_report_hash"] == q3["report_hash"] and primary["extension_mm"] == 800
        and roof["floor_requirements"]["landing_mm"] == primary["floor_landing_mm"], "Q3 upper stairs and roof arrival differ")
    floors = []
    for case in cases:
        parent = p4 if case["id"] == "B-2F" else q3 if case["id"] == "B-3F" else roof
        normalized = normalize_source(parent, case)
        require(stable_hash({"rooms": normalized[0], "fixed": normalized[1], "routes": normalized[2]}) == case["source_floor_hash"],
            "B storage belongs to a different whole-floor version: "+case["id"])
        review = check_storage(*normalized, case)
        require(not review["failures"], "B storage conflicts with its synchronized source: "+case["id"])
        level = {"floor-2": 4000, "floor-3": 7000, "floor-4": 10000}[case["floor"]]
        floor = {"key": case["id"], "id": case["floor"], "label": case["id"], "base_mm": level,
            "source": case["source"], "source_floor_hash": case["source_floor_hash"],
            "rooms": copy.deepcopy(normalized[0]), "fixed": copy.deepcopy(normalized[1]), "routes": copy.deepcopy(normalized[2]),
            "storage": {k: copy.deepcopy(case[k]) for k in ["id", "room", "label", "rect_mm", "operation_mm", "height_mm", "note"]},
            "storage_review": review, "states": []}
        if case.get("reuse_item"):
            floor["storage"]["reuse_item"] = case["reuse_item"]
        if case["id"] == "B-2F":
            floor["source_rooms"] = copy.deepcopy(p4["floor"]["rooms"])
            floor["front_service"] = {"sliders": p4["local_reference"]["sliders"],
                "routes": p4["floor"]["front"]["routes"], "shared_shaft_mm": p4["local_reference"]["shared_shaft_mm"]}
            floor["stair_interface"] = {"arrival_polygon_mm": arrivals["floor2_landing_polygon_mm"],
                "transfer_route_mm": arrivals["second_floor_transfer_route_mm"], "transfer_width_mm": 900,
                "incoming_treads": incoming_steps(q3["original_stairs_by_floor"]["floor-1"]),
                "outgoing": copy.deepcopy(outgoing), "outgoing_treads": incoming_steps(outgoing),
                "naive_full_width_tread_conflicts": arrivals["naive_full_width_new_platform_over_incoming_right_steps"],
                "full_headroom_and_structure_approved": False}
        elif case["id"] == "B-3F":
            floor["source_rooms"] = copy.deepcopy(q3["primary"]["rooms"])
            floor["door_interfaces"] = {"front": q3["config"]["front_door"], "side": q3["config"]["side_door"],
                "sliders": q3["retained_guest_bath_sliders"], "rear_opening": q3["retained_quiet_rear_opening"]}
            floor["stair_interface"] = {"arrival_polygon_mm": list(rect(primary["floor_landing_mm"]).exterior.coords),
                "side_threshold_polygon_mm": q3["primary"]["side_threshold_candidate_polygon_mm"],
                "incoming_treads": incoming_steps(outgoing), "outgoing": copy.deepcopy(upper_incoming),
                "outgoing_treads": incoming_steps(upper_incoming), "full_headroom_and_structure_approved": False}
        else:
            option = next(o for o in roof["options"] if o["id"] == case["option"])
            require(option["id"] in cfg["roof_options"], "Unexpected RF option")
            floor["source_roof_option"] = copy.deepcopy(option)
            f = roof["floor_requirements"]
            floor["stair_interface"] = {"arrival_polygons_mm": [list(rect(f[k]).exterior.coords) for k in ["landing_mm", "vestibule_mm", "side_threshold_mm"]]+[f["front_threshold_polygon_mm"]],
                "stairwell_keep_open_mm": f["stairwell_keep_open_mm"], "incoming_treads": f["Q3_incoming_treads"],
                "outgoing": None, "full_headroom_and_structure_approved": False}
            floor["roof_opening_mm"] = roof["R1_reference"]["rf_opening_mm"]
            floor["roof_guard_polygons_mm"] = roof["R1_reference"]["rf_guard_polygons_mm"]
            floor["protected_polygons_mm"] = roof["protected_polygons_mm"]
        for state in cfg["storage_states"]:
            floor["states"].append({"id": state, "label": "原配置" if state == "original" else "加櫃／工作檯下收納（未採用）",
                "objects": storage_objects(floor, case, state), "plan_file": case["id"]+"-"+state+".svg"})
        check_source_floor(floor, rect([0, 0, *cfg["frame_mm"]]))
        floors.append(floor)
    surfaces = check_stair_surfaces(floors)
    require(check_stair_surfaces([floors[0], floors[1], floors[3]]) == surfaces, "RF branches use different stair conditions")
    entries = []
    for oid in cfg["entry_options"]:
        option = next(o for o in snapshot["options"] if o["id"] == oid)
        states = []
        for sid in cfg["ground_use_states"]:
            state = next(s for s in option["states"] if s["id"] == sid)
            original = next(f for f in state["plans"]["floors"] if f["id"] == "floor-1")
            require(original["base_mm"] == 0 and original["height_mm"] == 4000, "Ground stair/elevation changed")
            states.append({"id": sid, "label": state["label"], "source_floor_hash": stable_hash(original),
                "floor": copy.deepcopy(original)})
        entries.append({"id": oid, "default": oid == cfg["default_entry"], "states": states})
    assemblies = [{"id": f"{entry}-{use}-{roofid}-{state}", "ground_entry": entry, "ground_use": use,
        "storage_state": state, "floors": ["B-2F", "B-3F", roofid], "professional_approval": "unknown", "adopted": False}
        for entry, use, roofid, state in product(cfg["entry_options"], cfg["ground_use_states"], ["B-RF-D1", "B-RF-D2"], cfg["storage_states"])]
    protected = unary_union([Polygon(p) for p in q3["protected_polygons_mm"]])
    wet = [{"floor": floor["key"], "room": room["id"],
        "over_protected_sqm": round(Polygon(room["polygon_mm"]).intersection(protected).area/1e6, 6)}
        for floor in floors[:2] for room in floor["source_rooms"] if room.get("kind") == "wet"]
    require(all(r["over_protected_sqm"] == 0 for r in wet), "Synchronized wet room enters shrine/backing protection")
    names = [CONFIG, DOC, "house_design/b_upper_storage_sync.py", "scripts/export_b_upper_storage_sync.py",
        "inputs/abc-next-protected-controls.json", *cfg["pinned_sources"],
        *[n for role in ["floor2", "floor3", "roof"] for n in source[role]["source_hashes"]],
        "house_design/upper_floor_storage.py", "scripts/lib/model3d_plan.py"]
    report = {"schema": "house-b-upper-storage-sync-report-v1", "date": cfg["date"], "config": cfg,
        "floors": floors, "entry_options": entries, "assemblies": assemblies,
        "stair_surface_review": surfaces, "wet_projection": wet,
        "summary": {"floor_variants": 4, "upper_floor_states": 8, "entry_options": 2,
            "ground_states": 6, "assembly_references": len(assemblies), "storage_cases": 4,
            "storage_per_assembly": 3, "RF_tables_duplicated": 0},
        "known_limits": {"frame_sqm": 105.78, "frame_is_legal_buildable_area": False,
            "KTV_source_budget_sqm": q3["primary"]["KTV_area_after_wrap_and_cabinet_sqm"],
            "RF_target_sqm": 24, "RF_optimistic_before_equipment_sqm": roof["parent_daily_capacity"]["front_before_equipment_with_edge_budget_sqm"],
            "RF_known_shortfall_before_equipment_sqm": roof["parent_daily_capacity"]["front_short_of24_before_equipment_sqm"],
            "RF_actual_product_fitting_approved": False, "P4_drainage_or_arcade_clearance_resolved": False,
            "whole_stair_headroom_structure_fire_religion_or_products_approved": False},
        "protected_controls_unchanged": len(controls), "main_3d_changed": False, "existing_viewers_changed": False,
        "formal_requirements_or_register_written": False, "original_family_rules_changed": False,
        "adopted": False, "professional_approval": "unknown", "construction_release": False,
        "rendered_qa": "not-run-static-sync-and-future-scene-input-only",
        "source_hashes": {n: digest(root, n, cache) for n in dict.fromkeys(names)}}
    report["report_hash"] = stable_hash(report)
    return report

"""Six source-matched A/C storage insertions into copies of frozen 3D payloads."""
from __future__ import annotations

import copy
import json
import re
from collections import Counter
from pathlib import Path

from house_design.contracts import ContractError, stable_hash
from house_design.project_status import digest, read_public_json
from scripts.check_upper_floor_storage_merge import BASE, STORAGE, VIEWER
from scripts.check_upper_floor_storage_merge import OUT as MERGE
from scripts.check_upper_floor_storage_merge import build as merge_build

OUT = "structured/coordination/ac-storage-preview-v1"
ARCHIVE = "ac-storage-preview.zip"
DOC = "Docs/ac-upper-floor-storage-preview-v1.md"
RUNTIME = "scripts/templates/ac-storage-preview.js"
EXPORTER = "scripts/export_ac_storage_preview.py"
CHECKER = "scripts/check_ac_storage_preview_playwright.cjs"


def bounds(r):
    x, y, w, d = r
    return {"minX": x, "maxX": x+w, "minY": y, "maxY": y+d}


def new_item(spec):
    x, y, w, d = spec["rect_mm"]
    ox, oy, ow, od = spec["operation_mm"]
    if oy == y+d and ox == x and ow == w:
        angle, anchor, width, depth, clear = 180, "front", w, d, od
    elif ox+ow == x and oy == y and od == d:
        angle, anchor, width, depth, clear = 90, "right", d, w, ow
    else:
        raise ContractError("Unsupported cabinet operation direction; do not guess: " + spec["case"])
    item = {"id": spec["proposed_item_id"], "label": "S1｜"+spec["label"],
        "catalog_id": "upper-floor-storage", "storage_case": spec["case"],
        "category": "storage", "shape": "cabinet", "color": "#eea13b",
        "width_mm": width, "depth_mm": depth, "height_mm": spec["height_mm"],
        "rotation_deg": angle, "basis": "owner-storage-proposal", "x_ratio": .5, "y_ratio": .5,
        "wall_anchor": anchor, "wall_locked": True, "wall_gap_mm": 115,
        "front_clearance_mm": clear, "mount_height_mm": 0,
        "evidence": ["inputs/upper-floor-storage.json｜"+spec["case"]],
        "note": "沿同源收納提案新增；實際產品、門片、容量與真人取物未核。"}
    placement = {"id": item["id"], "center_x_mm": x+w/2, "center_y_mm": y+d/2,
        "rotation_deg": angle, "wall_anchor": anchor, "wall_gap_mm": 115,
        "aabb": bounds(spec["rect_mm"]), "operation_mm": bounds(spec["operation_mm"]),
        "rear_operation_mm": None, "mount_height_mm": 0, "issues": [],
        "status": "source-plan-proposal-not-product-approved"}
    return item, placement


def assert_only_insertions(original, proposed, specs):
    """Reversing the named additions must recover the entire original model."""
    restored = copy.deepcopy(proposed)
    cells = {c["id"]: c for f in restored["buildings"][0]["floors"] for c in f["cells"]}
    active = [c for c in cells.values() if c.get("tour_active")]
    expected_summary = {**copy.deepcopy(original["furniture"]),
        "items": sum(len(c["furniture"]) for c in active), "rooms": sum(bool(c["furniture"]) for c in active),
        "basis_counts": dict(Counter(i["basis"] for c in active for i in c["furniture"]))}
    if proposed["furniture"] != expected_summary or proposed["bc_option"]["use_state"] != "storage":
        raise ContractError("Unexpected furniture summary, product data or use state changed")
    for spec in specs:
        cell, identifier = cells[spec["host_room_id"]], spec["proposed_item_id"]
        expected_item, expected_placement = new_item(spec)
        matches = [i for i in cell["furniture"] if i["id"] == identifier]
        if matches != [expected_item] or cell["furniture_placements"]["tour_mm"].get(identifier) != expected_placement:
            raise ContractError("New storage item/placement differs: " + spec["case"])
        cell["furniture"] = [i for i in cell["furniture"] if i["id"] != identifier]
        del cell["furniture_placements"]["tour_mm"][identifier]
    # These summaries describe the added display state; geometry is checked below.
    restored["furniture"] = copy.deepcopy(original["furniture"])
    restored["bc_option"]["use_state"] = original["bc_option"]["use_state"]
    if stable_hash(restored) != stable_hash(original):
        raise ContractError("An original room, item, placement, stair or system changed")


def patch_model(original, specs):
    proposed = copy.deepcopy(original)
    cells = {c["id"]: c for f in proposed["buildings"][0]["floors"] for c in f["cells"]}
    for spec in specs:
        cell = cells[spec["host_room_id"]]
        item, placement = new_item(spec)
        if any(i["id"] == item["id"] for i in cell["furniture"]):
            raise ContractError("Storage already present; do not add twice")
        if [i["id"] for i in cell["furniture"]] != spec["existing_furniture_ids_to_preserve"]:
            raise ContractError("Original furniture inventory differs")
        cell["furniture"].append(item)
        cell["furniture_placements"]["tour_mm"][item["id"]] = placement
    active = [c for c in cells.values() if c.get("tour_active")]
    proposed["furniture"].update(items=sum(len(c["furniture"]) for c in active),
        rooms=sum(bool(c["furniture"]) for c in active),
        basis_counts=dict(Counter(i["basis"] for c in active for i in c["furniture"])))
    proposed["bc_option"]["use_state"] = "storage"
    assert_only_insertions(original, proposed, specs)
    return proposed


def build(root):
    root, cache = Path(root), {}
    merge = merge_build(root)
    if stable_hash(merge) != stable_hash(read_public_json(root, MERGE)):
        raise ContractError("Merge preparation changed; review its same-source results first")
    if merge["summary"]["same_source_candidates"] != 6 or merge["summary"]["whole_floor_rebase_required"] != 4:
        raise ContractError("Unexpected A/C/B merge scope")
    original = (root/VIEWER).read_text()
    source = json.loads(re.search(r"^\s*var DATA = (.+);\s*$", original, re.M)[1])["kaohsiung_options"]
    storage = read_public_json(root, STORAGE)
    case_by_id = {c["id"]: c for c in storage["cases"]}
    from lib.model3d_plan import plan_data

    options, cases = [], []
    for oid, bid in [("a-rear-study", "A"), ("c-split", "C")]:
        old = next(o for o in source["options"] if o["id"] == oid)
        model = next(s for s in old["states"] if s["id"] == "daily")["model"]
        specs = [s for s in merge["unapplied_insertions"] if s["option"] == oid]
        if len(specs) != 3:
            raise ContractError("Each preview building needs all three upper floors")
        proposed = patch_model(model, specs)
        states = []
        for sid, label, current in [("storage", "加櫃比較（未採用）", proposed), ("daily", "原配置對照", model)]:
            plans = plan_data(current)["buildings"][0]
            for f in plans["floors"]:
                f["plan_file"] = f"{oid}_{sid}_{f['id']}.svg"
            states.append({"id": sid, "label": label, "model": current, "plans": plans,
                "review": copy.deepcopy(current["bc_option"]["geometry_review"])})
        options.append({"id": oid, "building": bid, "label": bid+"棟｜同版收納比較", "states": states,
            "baseline_model_hash": stable_hash(model), "proposed_model_hash": stable_hash(proposed)})
        for spec in specs:
            c = case_by_id[spec["case"]]
            placed = copy.deepcopy(spec)
            placed.pop("applied")
            cases.append({**placed, "building": bid, "note": c["note"],
                "applied_in_preview": True, "applied_to_original_main": False,
                "source_plan_sha256": digest(root, "structured/coordination/upper-floor-storage-v1/"+c["id"]+".svg", cache)})
    names = [MERGE, STORAGE, BASE, VIEWER, DOC, RUNTIME, EXPORTER, CHECKER,
        "house_design/ac_storage_preview.py", "house_design/contracts.py", "house_design/project_status.py",
        "house_design/plan_readability.py", "scripts/merge_c_stair_into_3d.py", *merge["source_hashes"]]
    report = {"schema": "house-ac-upper-floor-storage-preview-v1", "date": "2026-11-12", "revision": 1, "display_revision": 3,
        "default_option": "a-rear-study", "options": options, "cases": cases,
        "professional_status": source["professional_status"], "cost_studies": source["cost_studies"],
        "summary": {"buildings": 2, "states": 4, "floors": 16, "storage_cases": 6, "new_cabinets": 6},
        "scope": "Frozen A/C full-room scenes with before/after storage states; six furniture additions only.",
        "original_main_3d_changed": False, "accepted_storage_viewer_changed": False,
        "B_not_imported_or_rebased": True, "original_furniture_and_architecture_preserved": True,
        "protected_controls_unchanged": merge["protected_controls_unchanged"],
        "rendered_qa": "not-run-owner-separate-terminal-required", "adopted": False,
        "professional_approval": "unknown", "construction_release": False,
        "source_hashes": {n: digest(root, n, cache) for n in dict.fromkeys(names)}}
    # Store model hashes in the report, not duplicate complete model payloads.
    seal = copy.deepcopy(report)
    for option in seal["options"]:
        for state in option["states"]:
            state.pop("model")
    report["report_hash"] = stable_hash(seal)
    return report

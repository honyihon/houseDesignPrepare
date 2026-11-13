#!/usr/bin/env python3
"""Compare storage and embedded floor sources; never build or run a 3D scene."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / "scripts"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from lib.model3d_plan import plan_data  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

from house_design.contracts import ContractError, stable_hash  # noqa: E402
from house_design.project_status import digest, read_public_json  # noqa: E402
from house_design.upper_floor_storage import build as storage_build  # noqa: E402
from house_design.upper_floor_storage import normalize_model, rect  # noqa: E402

STORAGE = "structured/coordination/upper-floor-storage-v1/review.json"
VIEWER = "structured/candidates/kaohsiung-house-options-3d.html"
BASE = "structured/candidates/kaohsiung-house-options/c-stair-integration.json"
EVIDENCE = "inputs/references/upper-floor-storage-rendered-review-20261111.json"
OUT = "structured/coordination/upper-floor-storage-merge-review-v1/review.json"
DOC = "Docs/abc-upper-floor-storage-merge-v1.md"


def compare_floor(case, floor):
    """The whole source must match; a cabinet fitting an old room proves little."""
    rooms, fixed, routes = normalize_model(floor)
    current_hash = stable_hash({"rooms": rooms, "fixed": fixed, "routes": routes})
    target = next((room for room in rooms if room["id"] == case["room"]), None)
    same = current_hash == case["source_floor_hash"]
    body = rect(case["rect_mm"])
    hosts = []
    for room in rooms:
        overlap = Polygon(room["polygon_mm"]).intersection(body).area
        if overlap > .1:
            hosts.append({"id": room["id"], "name": room["label"], "overlap_sqm": round(overlap / 1e6, 6)})
    return {"source_floor_exact": same, "current_floor_hash": current_hash,
        "target_room_id_present": target is not None, "current_rooms_under_cabinet": hosts,
        "source_room_count": len(case["rooms"]), "current_room_count": len(rooms),
        "source_only_room_ids": sorted({r["id"] for r in case["rooms"]} - {r["id"] for r in rooms}),
        "current_only_room_ids": sorted({r["id"] for r in rooms} - {r["id"] for r in case["rooms"]}),
        "same_floor_insertion_candidate": same and target is not None,
        "whole_3d_or_product_approval": "unknown"}


def build(root=ROOT):
    root, cache = Path(root), {}
    storage = storage_build(root)
    if stable_hash(storage) != stable_hash(read_public_json(root, STORAGE)):
        raise ContractError("Storage study is stale; do not plan a merge from mixed sources")
    evidence = read_public_json(root, EVIDENCE)
    if (evidence.get("display_revision") != 3
            or evidence.get("status") != "passed-for-storage-viewer-display-scope"):
        raise ContractError("Missing returned storage-display evidence")
    for name, expected in evidence["source_hashes"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("Previously reviewed storage display source changed: " + name)
    base = read_public_json(root, BASE)
    text = (root / VIEWER).read_text()
    match = re.search(r"^\s*var DATA = (.+);\s*$", text, re.M)
    if not match or hashlib.sha256(match[1].encode()).hexdigest() != base["payload_sha256"]:
        raise ContractError("Embedded main-model payload differs from the selected floor report")
    if digest(root, VIEWER, cache) != base["artifact_hashes"][VIEWER]:
        raise ContractError("Main viewer bytes changed")
    study = json.loads(match[1])["kaohsiung_options"]
    if study["report_hash"] != base["report_hash"]:
        raise ContractError("Embedded main model and floor report are mixed")
    options = {o["id"]: o for o in study["options"]}
    plans = {(o["id"], s["id"]): plan_data(s["model"])["buildings"][0]
        for o in study["options"] for s in o["states"]}
    cases, insertions = [], []
    for case in storage["cases"]:
        ids = [case["option"]] if case["building"] != "B" else ["b-rear-split", "b-front-split"]
        comparisons = []
        for oid in ids:
            for state in options[oid]["states"]:
                floor = next(f for f in plans[oid, state["id"]]["floors"] if f["id"] == case["floor"])
                comparisons.append({"option": oid, "state": state["id"], **compare_floor(case, floor)})
                if comparisons[-1]["same_floor_insertion_candidate"]:
                    room = next(r for r in floor["rooms"] if r["key"] == case["room"])
                    x, y, w, d = case["rect_mm"]
                    g = room["geometry"]
                    insertions.append({"case": case["id"], "option": oid, "state": state["id"],
                        "floor": case["floor"], "host_room_id": room["id"],
                        "proposed_item_id": room["id"] + ":upper-floor-storage", "label": case["label"],
                        "rect_mm": case["rect_mm"], "operation_mm": case["operation_mm"], "height_mm": case["height_mm"],
                        "host_local_rect_mm": [x-g["x_mm"], y-g["y_mm"], w, d],
                        "expected_source_floor_hash": case["source_floor_hash"],
                        "existing_furniture_ids_to_preserve": [i["id"] for i in room["furniture"]],
                        "applied": False})
        cases.append({"id": case["id"], "building": case["building"], "floor": case["floor"],
            "source": case["source"], "source_option": case.get("option"), "room": case["room"],
            "label": case["label"], "note": case["note"],
            "source_floor_hash": case["source_floor_hash"], "comparisons": comparisons,
            "status": "same-source-insertion-candidate" if all(c["same_floor_insertion_candidate"] for c in comparisons)
                else "whole-floor-rebase-required",
            "source_2d_failures": case["review"]["failures"], "applied": False})
    names = [STORAGE, BASE, VIEWER, EVIDENCE, DOC, "scripts/check_upper_floor_storage_merge.py",
        "house_design/upper_floor_storage.py", "scripts/lib/model3d_plan.py", *storage["source_hashes"]]
    report = {"schema": "house-upper-floor-storage-merge-preparation-v1", "date": "2026-11-11",
        "scope": "Embedded-model/floor-source comparison and unapplied insertion coordinates only; no 3D build or rendering.",
        "cases": cases, "unapplied_insertions": insertions,
        "summary": {"storage_cases": len(cases), "floor_state_comparisons": sum(len(c["comparisons"]) for c in cases),
            "same_source_candidates": sum(c["status"] == "same-source-insertion-candidate" for c in cases),
            "whole_floor_rebase_required": sum(c["status"] == "whole-floor-rebase-required" for c in cases),
            "unapplied_insertions": len(insertions)},
        "B_entry_options_retained": ["b-rear-split", "b-front-split"], "B_default_entry": "rear",
        "B_roof_storage_cases_retained": ["B-RF-D1", "B-RF-D2"],
        "same_xy_fit_does_not_authorize_merging_different_floor_versions": True,
        "main_3d_changed": False, "storage_viewer_changed": False, "browser_or_full_scene_started": False,
        "protected_controls_unchanged": storage["protected_controls_unchanged"],
        "adopted": False, "professional_approval": "unknown", "construction_release": False,
        "source_hashes": {name: digest(root, name, cache) for name in dict.fromkeys(names)}}
    report["report_hash"] = stable_hash(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true", help="Write only the bounded JSON preparation report")
    args = parser.parse_args()
    try:
        report = build()
        if args.write_report:
            output = ROOT / OUT
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        elif stable_hash(read_public_json(ROOT, OUT)) != stable_hash(report):
            raise ContractError("Merge preparation report is stale; review changes before using --write-report")
        print(json.dumps({"status": "written" if args.write_report else "checked", **report["summary"],
            "main_3d_changed": False, "browser": "not-run"}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

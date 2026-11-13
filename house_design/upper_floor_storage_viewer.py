"""A source-bound storage-only 3D view; B polygons are never replaced by rectangles."""
from __future__ import annotations

from pathlib import Path

from house_design.contracts import ContractError, stable_hash
from house_design.project_status import digest, read_public_json

OUT = "structured/coordination/upper-floor-storage-viewer-v1"
SOURCE = "structured/coordination/upper-floor-storage-v1/review.json"
ARCHIVE = "upper-floor-storage-3d.zip"


def build(root):
    root, cache = Path(root), {}
    study = read_public_json(root, SOURCE)
    if (study.get("schema") != "house-upper-floor-storage-report-v1"
            or study.get("report_hash") != stable_hash({k:v for k,v in study.items() if k != "report_hash"})
            or study.get("case_count") != 10 or study.get("floors") != 9
            or study.get("primary_3d_changed") is not False):
        raise ContractError("Storage viewer needs the original nine-floor reviewed study")
    for name, expected in study["source_hashes"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("Storage input changed; review before a new 3D copy: "+name)
    manifest_name = "structured/coordination/upper-floor-storage-v1/artifact-manifest.json"
    manifest = read_public_json(root, manifest_name)
    if manifest["report_hash"] != study["report_hash"]:
        raise ContractError("Storage report and drawings are mixed")
    sources = [SOURCE, manifest_name, "house_design/upper_floor_storage_viewer.py",
        "scripts/export_upper_floor_storage_viewer.py", "scripts/templates/upper-floor-storage-viewer.html",
        "scripts/templates/upper-floor-storage-viewer.js", "scripts/check_storage_3d_playwright.cjs",
        "assets/vendor/three/three.min.js", "assets/vendor/three/LICENSE", "assets/vendor/three/VERSION.txt",
        "Docs/abc-upper-floor-storage-3d-v1.md", "inputs/abc-next-protected-controls.json", *study["source_hashes"]]
    cases = []
    for case in study["cases"]:
        if case["review"]["failures"]:
            raise ContractError("Do not present an unresolved listed storage collision as clear")
        plan = "structured/coordination/upper-floor-storage-v1/"+case["id"]+".svg"
        if digest(root, plan, cache) != manifest["artifacts"][case["id"]+".svg"]:
            raise ContractError("Storage plan changed: "+plan)
        # Carry the exact floor model used by the plan, including polygons and
        # reused-table exclusions. Only the new cabinet has a known 3D height.
        cases.append({**case, "plan_file":case["id"]+".svg", "plan_source":plan,
            "plan_sha256":digest(root, plan, cache), "storage_geometry":{
                "rect_mm":case["rect_mm"], "operation_mm":case["operation_mm"], "height_mm":case["height_mm"]},
            "surroundings_display":"2D-footprints-only-no-invented-walls-heights-stair-slabs-or-clearances"})
        sources.append(plan)
    controls = read_public_json(root, "inputs/abc-next-protected-controls.json")["hashes"]
    if any(digest(root,n,cache) != h for n,h in controls.items()):
        raise ContractError("Protected original design changed")
    report = {"schema":"house-upper-floor-storage-viewer-v1", "date":"2026-11-11", "display_revision":3,
        "source_storage_report_sha256":digest(root,SOURCE,cache), "source_storage_report_hash":study["report_hash"],
        "cases":cases, "distinct_floors":9, "case_count":10, "default_case":"A-2F", "primary_3d_changed":False,
        "display_scope":"storage-height-only-with-exact-source-floor-and-object-footprints",
        "original_surrounding_furniture_heights_or_walls_invented":False,
        "two_independent_B_roof_cases_retained":True, "old_QA_reused":False,
        "browser_plugin":"absent", "rendered_qa":"not-run-owner-separate-terminal-required",
        "professional_approval":"unknown", "adopted":False, "protected_controls_unchanged":len(controls),
        "source_hashes":{n:digest(root,n,cache) for n in dict.fromkeys(sources)}}
    report["report_hash"] = stable_hash(report)
    return report

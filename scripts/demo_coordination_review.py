"""Generate synthetic A/B/C coordination reports, never actual project geometry."""

from __future__ import annotations

import argparse
from pathlib import Path

from house_design.contracts import ROOT, read_json, sha256_file, write_json
from house_design.coordination import SCHEMA
from house_design.dashboard import write_dashboard
from house_design.drawings import revision_manifest_content_hash
from house_design.review import build_review, write_review

PROOF = {"verified_by": "SYNTHETIC EXAMPLE ONLY", "verified_at": "2026-10-01", "reference": "DEMO / NOT A REAL DRAWING"}


def box(oid, building, x, y, width, depth, floor="floor-1", **extra):
    return {
        "id": oid,
        "building_id": building,
        "floor_id": floor,
        "polygon_mm": [[x, y], [x + width, y], [x + width, y + depth], [x, y + depth]],
        "geometry_method": "professional_verified_polygon",
        "evidence": PROOF,
        **extra,
    }


def demo(output: Path) -> Path:
    output = output.resolve()
    if any((output / "revisions" / f"DEMO-R{n}").exists() for n in (1, 2)):
        raise ValueError(f"Demo revisions already exist; use a new --output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    project_path = output / "project.json"
    project = read_json(ROOT / "inputs/project.json")
    project["name"] = "三棟合成檢核示範（非實際圖面）"
    write_json(project_path, project)
    previous_overlay = None
    last_directory = output
    for number in (1, 2):
        rid = f"DEMO-R{number}"
        directory = output / "revisions" / rid
        if directory.exists():
            raise ValueError(f"Demo revision already exists; use a new --output: {directory}")
        spaces = [
            box(
                f"{b}-room",
                b,
                0,
                0,
                8000,
                6000,
                boundary_measurement="finished_clear",
                finished_headroom_mm=2100 if b == "A" else 2600,
            )
            for b in "ABC"
        ]
        spaces.append(box("B-upper", "B", 0, 0, 8000, 6000, floor="floor-2", boundary_measurement="finished_clear"))
        storeys = [{"id": f"{b}-level", "building_id": b, "floor_id": "floor-1", "elevation_mm": 0} for b in "ABC"]
        storeys.append({"id": "B-level-2", "building_id": "B", "floor_id": "floor-2", "elevation_mm": 3000})
        model = {
            "schema": "house-normalized-model-v1",
            "revision_id": rid,
            "units": {"length": "mm", "area": "sqm"},
            "coordinate_system": {
                "status": "verified",
                "axis": "synthetic x/y (NOT NORTH)",
                "verified_by": PROOF["verified_by"],
                "verified_at": PROOF["verified_at"],
                "method": "synthetic matching",
                "reference_points": [[0, 0], [8000, 0]],
            },
            "entities": {
                "buildings": [],
                "storeys": storeys,
                "spaces": spaces,
                "walls": [],
                "doors": [],
                "windows": [],
                "equipment": [],
            },
        }
        model_path = directory / "model.json"
        write_json(model_path, model)
        manifest = {
            "schema": "house-drawing-revision-v1",
            "revision_id": rid,
            "label": "合成測試，非施工圖",
            "status": "ready",
            "sources": [],
            "mapping": None,
            "normalized_model": str(model_path),
            "normalized_model_sha256": sha256_file(model_path),
            "issues": [],
        }
        manifest["content_hash"] = revision_manifest_content_hash(manifest)
        write_json(directory / "manifest.json", manifest)
        objects = [
            box("B-altar", "B", 500, 500, 1200, 800, category="altar"),
            box("B-door-sweep", "B", 1500 if number == 1 else 3000, 500, 1000, 1000, category="door_swing"),
            box(
                "B-wet-zone", "B", 1600 if number == 1 else 3500, 500, 1800, 2000, floor="floor-2", category="wet_area"
            ),
            box("C-equipment", "C", 500, 500, 1000, 1000),
            box("C-service-zone", "C", 1600, 500, 1200, 1500),
            box("C-cabinet", "C", 2500 if number == 1 else 4000, 500, 800, 1200),
        ]
        specs = [
            {
                "id": "A-turn",
                "title": "A：指定輪椅迴轉區（示範門檻，非法定）",
                "kind": "turning_circle",
                "domain": "accessibility",
                "subject_id": "A-room",
                "center_mm": [3500, 3500],
                "diameter_mm": 1500,
            },
            {
                "id": "A-headroom",
                "title": "A：完成面最低淨高（示範屋主標準）",
                "kind": "headroom",
                "domain": "structural",
                "subject_id": "A-room",
                "minimum_mm": 2200,
            },
            {
                "id": "B-swing",
                "title": "B：門扇與神桌保護區",
                "kind": "collision",
                "domain": "space_program",
                "subject_id": "B-altar",
                "target_ids": ["B-door-sweep"],
            },
            {
                "id": "B-stack",
                "title": "B：神桌上方濕區投影",
                "kind": "projection",
                "domain": "fengshui",
                "subject_id": "B-altar",
                "target_ids": ["B-wet-zone", "B-door-sweep"],
            },
            {
                "id": "B-carry",
                "title": "B：武轎暫估收納不能當作實測搬運",
                "kind": "carry_route",
                "domain": "maintenance",
                "subject_id": "B-room",
                "obstacle_ids": ["B-altar", "B-door-sweep"],
                "path_mm": [[1800, 3500], [6000, 3500]],
                "width_mm": 1400,
                "route_clear_height_mm": 2600,
                "transport": {"width_mm": 1200, "depth_mm": 2200, "height_mm": 2100, "measurement_state": "estimated"},
            },
            {
                "id": "C-service",
                "title": "C：設備維修抽換操作區",
                "kind": "clearance",
                "domain": "maintenance",
                "subject_id": "C-room",
                "target_ids": ["C-service-zone"],
                "obstacle_ids": ["C-equipment", "C-cabinet"],
            },
        ]
        checks = [{"priority": "must", "evidence": PROOF, **s} for s in specs]
        coverage = []
        all_objects = [*spaces, *objects]
        for s in storeys:
            for domain in {c["domain"] for c in checks}:
                coverage.append(
                    {
                        "building_id": s["building_id"],
                        "floor_id": s["floor_id"],
                        "domain": domain,
                        "complete": True,
                        "evidence": PROOF,
                        "check_ids": [c["id"] for c in checks],
                        "object_ids": [
                            o["id"]
                            for o in all_objects
                            if o["building_id"] == s["building_id"] and o["floor_id"] == s["floor_id"]
                        ],
                    }
                )
        overlay = {
            "schema": SCHEMA,
            "revision_id": rid,
            "revision_hash": manifest["content_hash"],
            "registration": PROOF,
            "objects": objects,
            "checks": checks,
            "coverage": coverage,
        }
        overlay_path = output / f"overlay-{rid}.json"
        write_json(overlay_path, overlay)
        report = build_review(
            revision_id=rid,
            project_path=project_path,
            revision_root=output / "revisions",
            coordination_path=overlay_path,
            previous_revision="DEMO-R1" if number == 2 else None,
            previous_coordination_path=previous_overlay,
        )
        last_directory = write_review(report, output_root=output / "reviews")
        write_dashboard(report, last_directory)
        previous_overlay = overlay_path
    return last_directory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "structured/examples/coordination")
    print(demo(parser.parse_args().output))

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from house_design.contracts import ROOT, sha256_file, write_json
from house_design.drawings import revision_manifest_content_hash
from house_design.model3d import export_revision_model3d


def main() -> None:
    runtime = ROOT / "test-results/runtime-current"
    revision_root = runtime / "revisions"
    directory = revision_root / "RQA"
    source = directory / "source/RQA.dxf"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"browser QA sealed DXF fixture")
    model_path = directory / "normalized_model.json"
    model = {
        "schema": "house-normalized-model-v1",
        "revision_id": "RQA",
        "coordinate_system": {
            "status": "verified",
            "axis": {"x": "east", "y": "north", "z": "up"},
            "verified_by": "browser QA fixture",
            "verified_at": "2026-08-31",
            "method": "two fixture control points",
            "reference_points": [{"id": "P1"}, {"id": "P2"}],
        },
        "entities": {
            "buildings": [],
            "storeys": [
                {
                    "id": "A-1F",
                    "building_id": "A",
                    "floor_id": "floor-1",
                    "elevation_mm": 0,
                    "height_mm": 3200,
                    "geometry_provenance": "professional_verified",
                },
                {
                    "id": "B-2F",
                    "building_id": "B",
                    "floor_id": "floor-2",
                    "elevation_mm": 3200,
                    "height_mm": 3100,
                    "geometry_provenance": "professional_verified",
                },
            ],
            "spaces": [
                {
                    "id": "A-living",
                    "name": "A 棟客廳",
                    "building_id": "A",
                    "floor_id": "floor-1",
                    "bbox_mm": [0, 0, 5000, 4000],
                    "area_sqm": 20,
                    "geometry_provenance": "architect_dxf",
                },
                {
                    "id": "B-bedroom",
                    "name": "B 棟臥室",
                    "building_id": "B",
                    "floor_id": "floor-2",
                    "bbox_mm": [7000, 0, 10500, 4000],
                    "area_sqm": 14,
                    "geometry_provenance": "architect_dxf",
                },
            ],
            "walls": [],
            "doors": [],
            "windows": [],
            "stairs": [],
            "equipment": [],
            "drawing_geometry": [],
        },
        "import_issues": [],
    }
    write_json(model_path, model)
    manifest = {
        "schema": "house-drawing-revision-v2",
        "revision_id": "RQA",
        "label": "Browser QA fixture",
        "status": "ready",
        "immutable": True,
        "sources": [{"kind": "dxf", "file": str(source), "sha256": sha256_file(source)}],
        "mapping": None,
        "normalized_model": str(model_path),
        "normalized_model_sha256": sha256_file(model_path),
        "issues": [],
    }
    manifest["content_hash"] = revision_manifest_content_hash(manifest)
    write_json(directory / "manifest.json", manifest)
    export_revision_model3d(
        revision_id="RQA",
        root=revision_root,
        output=runtime / "model3d.html",
    )


if __name__ == "__main__":
    main()

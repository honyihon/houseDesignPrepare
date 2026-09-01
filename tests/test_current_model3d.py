from __future__ import annotations

from pathlib import Path

import pytest

from house_design.contracts import ContractError, sha256_file, write_json
from house_design.dashboard import dashboard_html, write_dashboard
from house_design.drawings import revision_manifest_content_hash
from house_design.model3d import _model_payload, export_revision_model3d


def _ready_revision(tmp_path: Path) -> tuple[Path, dict]:
    root = tmp_path / "revisions"
    directory = root / "R001"
    source = directory / "source/R001.dxf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"sealed dxf fixture")
    model_path = directory / "normalized_model.json"
    model = {
        "schema": "house-normalized-model-v1",
        "revision_id": "R001",
        "coordinate_system": {
            "status": "verified",
            "axis": {"x": "east", "y": "north", "z": "up"},
            "verified_by": "architect",
            "verified_at": "2026-08-31",
            "method": "control points",
            "reference_points": [{"id": "P1"}, {"id": "P2"}],
        },
        "entities": {
            "buildings": [{"id": "A", "building_id": "A"}],
            "storeys": [
                {
                    "id": "A-1F",
                    "building_id": "A",
                    "floor_id": "floor-1",
                    "elevation_mm": 0,
                    "height_mm": 3200,
                    "geometry_provenance": "professional_verified",
                }
            ],
            "spaces": [
                {
                    "id": "room-1",
                    "name": "孝親房",
                    "building_id": "A",
                    "floor_id": "floor-1",
                    "bbox_mm": [0, 0, 3000, 4000],
                    "area_sqm": 12,
                    "geometry_provenance": "architect_dxf",
                }
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
        "revision_id": "R001",
        "label": "初步設計",
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
    return root, manifest


def test_current_revision_export_is_self_contained_and_honestly_labelled(tmp_path: Path) -> None:
    root, _ = _ready_revision(tmp_path)
    output = tmp_path / "reviews/R001/model3d.html"

    result = export_revision_model3d(revision_id="R001", root=root, output=output)
    document = output.read_text(encoding="utf-8")

    assert result["level"] == "space_block"
    assert result["spaces"] == 1
    assert "空間量體模型" in document
    assert "不是施工精度 walkthrough" in document
    assert 'canvas id="canvas" role="img"' in document
    assert '<script src="http' not in document
    assert '<link rel="stylesheet" href="http' not in document
    assert "window.__spaceBlockDebug" in document


def test_export_refuses_a_revision_that_fails_integrity(tmp_path: Path) -> None:
    root, manifest = _ready_revision(tmp_path)
    Path(manifest["normalized_model"]).write_text("{}", encoding="utf-8")

    with pytest.raises(ContractError, match="integrity verification"):
        export_revision_model3d(revision_id="R001", root=root, output=tmp_path / "model3d.html")


def test_model_payload_tolerates_unreferenced_storey_without_elevation() -> None:
    model = {
        "entities": {
            "storeys": [
                {"building_id": "A", "floor_id": "floor-1", "elevation_mm": 0},
                {"building_id": "B", "floor_id": "floor-2"},
            ],
            "spaces": [
                {
                    "id": "room-1",
                    "building_id": "A",
                    "floor_id": "floor-1",
                    "bbox_mm": [0, 0, 3000, 4000],
                }
            ],
        }
    }

    payload = _model_payload({"revision_id": "R001"}, model)

    assert payload["spaces"][0]["display_height_mm"] == 2800.0
    assert payload["spaces"][0]["height_source"] == "display_only_default"


def test_dashboard_links_model_only_when_ready_artifact_exists(tmp_path: Path) -> None:
    report = {
        "revision": {"revision_id": "R001", "label": "初步設計"},
        "readiness": {"percent": 0, "facts": []},
        "findings": [],
        "model": {"entities": {"spaces": []}},
        "model3d_readiness": {
            "eligible": True,
            "counts": {},
            "coordinate_system": {"status": "verified"},
            "blockers": [],
            "policy": "space block only",
        },
    }
    directory = tmp_path / "R001"
    directory.mkdir()

    without_artifact = dashboard_html(report)
    assert "const model3dArtifactAvailable = false" in without_artifact
    write_dashboard(report, directory)
    assert "const model3dArtifactAvailable = false" in (directory / "index.html").read_text(encoding="utf-8")
    (directory / "model3d.html").write_text("artifact", encoding="utf-8")
    write_dashboard(report, directory)
    assert "const model3dArtifactAvailable = true" in (directory / "index.html").read_text(encoding="utf-8")

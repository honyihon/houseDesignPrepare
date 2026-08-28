from __future__ import annotations

from pathlib import Path

import pytest

from house_design.contracts import ContractError, write_json
from house_design.drawings import (
    _ifc_building_id,
    _ifc_floor_id,
    _ifc_spatial_location,
    compare_models,
    import_revision,
    load_revision,
)


def _model(area: float, door_width: float) -> dict:
    return {
        "schema": "house-normalized-model-v1",
        "revision_id": "test",
        "entities": {
            "spaces": [
                {
                    "id": "space-1",
                    "requirement_id": "A.floor-1.elder",
                    "name": "孝親房",
                    "building_id": "A",
                    "floor_id": "floor-1",
                    "area_sqm": area,
                    "bbox_mm": [0, 0, 3000, 4000],
                }
            ],
            "doors": [
                {
                    "id": "door-1",
                    "source_id": "door-1",
                    "name": "孝親房門",
                    "building_id": "A",
                    "floor_id": "floor-1",
                    "clear_width_mm": door_width,
                }
            ],
            "windows": [],
            "equipment": [],
        },
    }


def test_model_comparison_reports_area_and_door_width_changes() -> None:
    changes = compare_models(_model(10.2, 900), _model(8.4, 800))

    assert len(changes) == 2
    fields = {(change["entity_type"], item["field"]) for change in changes for item in change["fields"]}
    assert ("spaces", "area_sqm") in fields
    assert ("doors", "clear_width_mm") in fields


def test_revision_manifest_can_reference_absolute_normalized_model(tmp_path: Path) -> None:
    revision_root = tmp_path / "revisions"
    directory = revision_root / "R001"
    model_path = directory / "normalized.json"
    write_json(model_path, _model(10.0, 900))
    write_json(
        directory / "manifest.json",
        {
            "schema": "house-drawing-revision-v1",
            "revision_id": "R001",
            "label": "初步設計",
            "normalized_model": str(model_path),
        },
    )

    manifest, model = load_revision("R001", revision_root)

    assert manifest["revision_id"] == "R001"
    assert model["entities"]["spaces"][0]["area_sqm"] == 10.0


def test_imported_revision_is_immutable(tmp_path: Path) -> None:
    revision_root = tmp_path / "revisions"
    source = tmp_path / "drawing.pdf"
    source.write_bytes(b"%PDF-1.4\n% intentionally minimal test fixture")

    first = import_revision(
        revision_id="R001",
        label="初步設計",
        pdf=source,
        root=revision_root,
    )

    assert first["immutable"] is True
    assert first["sources"][0]["sha256"]
    with pytest.raises(ContractError, match="revision already exists"):
        import_revision(
            revision_id="R001",
            label="重複",
            pdf=source,
            root=revision_root,
        )


def test_import_requires_at_least_one_source(tmp_path: Path) -> None:
    with pytest.raises(ContractError, match="at least one"):
        import_revision(revision_id="R001", label="初步設計", root=tmp_path)


def test_mapping_is_copied_and_hashed_inside_immutable_revision(tmp_path: Path) -> None:
    source = tmp_path / "drawing.pdf"
    source.write_bytes(b"%PDF-1.4\n% intentionally minimal test fixture")
    mapping = tmp_path / "mapping.json"
    write_json(mapping, {"layers": {}})
    revision_root = tmp_path / "revisions"

    manifest = import_revision(
        revision_id="R001",
        label="初步設計",
        pdf=source,
        mapping_path=mapping,
        root=revision_root,
    )

    stored = Path(manifest["mapping"]["file"])
    assert stored != mapping
    assert stored.read_bytes() == mapping.read_bytes()
    assert manifest["mapping"]["sha256"]


def test_ifc_location_walks_from_space_to_storey_and_building(monkeypatch: pytest.MonkeyPatch) -> None:
    class Entity:
        def __init__(self, identifier: int) -> None:
            self.identifier = identifier

        def id(self) -> int:
            return self.identifier

    space, zone, storey = Entity(1), Entity(2), Entity(3)
    parents = {space: zone, zone: storey, storey: None}
    monkeypatch.setattr("house_design.drawings._ifc_container", parents.get)

    assert _ifc_spatial_location(space, {3: "floor-1"}, {3: "A"}) == ("floor-1", "A")


def test_ifc_names_normalize_only_explicit_building_and_floor_tokens() -> None:
    assert _ifc_building_id("Building A", "guid-a") == "A"
    assert _ifc_building_id("Building", "guid-generic") == "guid-generic"
    assert _ifc_floor_id("1F", "storey-guid") == "floor-1"
    assert _ifc_floor_id("屋頂層", "storey-guid") == "floor-rf"


def test_real_pdf_and_mapped_dxf_become_ready_revision(tmp_path: Path) -> None:
    ezdxf = pytest.importorskip("ezdxf")
    pytest.importorskip("pymupdf")
    reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    pdf = tmp_path / "R001.pdf"
    pdf_canvas = reportlab_canvas.Canvas(str(pdf))
    pdf_canvas.drawString(72, 760, "R001")
    pdf_canvas.save()
    dxf = tmp_path / "R001.dxf"
    document = ezdxf.new("R2013")
    document.units = ezdxf.units.MM
    document.layers.add("A-1F-ROOM-ELDER")
    document.layers.add("A-1F-DOOR-ELDER")
    document.modelspace().add_lwpolyline(
        [(0, 0), (3000, 0), (3000, 4000), (0, 4000)],
        close=True,
        dxfattribs={"layer": "A-1F-ROOM-ELDER"},
    )
    document.modelspace().add_lwpolyline(
        [(3000, 1500), (3100, 1500), (3100, 2400), (3000, 2400)],
        close=True,
        dxfattribs={"layer": "A-1F-DOOR-ELDER"},
    )
    document.saveas(dxf)
    mapping = tmp_path / "mapping.json"
    write_json(
        mapping,
        {
            "layers": {
                "A-1F-ROOM-ELDER": {
                    "kind": "space",
                    "building_id": "A",
                    "floor_id": "floor-1",
                    "name": "孝親房",
                    "requirement_id": "A.floor-1.elder",
                },
                "A-1F-DOOR-ELDER": {
                    "kind": "door",
                    "building_id": "A",
                    "floor_id": "floor-1",
                    "name": "孝親房門",
                }
            }
        },
    )

    manifest = import_revision(
        revision_id="R001",
        label="初步設計",
        pdf=pdf,
        dxf=dxf,
        mapping_path=mapping,
        root=tmp_path / "revisions",
    )

    assert manifest["status"] == "ready"
    assert manifest["sources"][0]["page_count"] == 1
    assert manifest["mapping"]["sha256"]
    assert manifest["normalized_entity_count"] == 2
    _, model = load_revision("R001", tmp_path / "revisions")
    assert model["entities"]["spaces"][0]["area_sqm"] == 12.0
    assert model["entities"]["doors"][0]["clear_width_mm"] == 900.0

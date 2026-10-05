from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from house_design.architect_handoff import (
    DELIVERY_SCHEMA,
    HANDOFF_SCHEMA,
    create_handoff_package,
    preflight_handoff_package,
)
from house_design.brief import build_design_brief
from house_design.contracts import ContractError, read_json, sha256_file, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_predecessor(root: Path) -> dict[str, bytes]:
    values = {
        "index.html": b"<html><a href='AbuildingView.html'>A</a></html>",
        "AbuildingView.html": b"<html><title>A legacy</title></html>",
        "BbuildingView.html": b"<html><title>B legacy</title></html>",
        "CbuildingView.html": b"<html><title>C legacy</title></html>",
    }
    root.mkdir(parents=True)
    for name, content in values.items():
        (root / name).write_bytes(content)
    return values


def _write_inputs(root: Path, *, selected_site: object = None) -> tuple[Path, Path]:
    project = root / "project.json"
    requirements = root / "requirements.json"
    write_json(
        project,
        {
            "schema": "house-project-v3",
            "project_id": "test-project",
            "stage": "site_search",
            "site_search": {"selected_site": selected_site},
        },
    )
    write_json(
        requirements,
        {
            "schema": "house-requirements-v2",
            "requirements": [
                {
                    "id": "A.floor-1.living",
                    "status": "confirmed",
                    "priority": "must",
                    "applies_to": {"building_id": "A", "floor_id": "floor-1"},
                }
            ],
        },
    )
    return project, requirements


def _create_package(tmp_path: Path) -> Path:
    predecessor = tmp_path / "predecessor"
    _write_predecessor(predecessor)
    project, requirements = _write_inputs(tmp_path)
    output_root = tmp_path / "handoffs"
    create_handoff_package(
        revision_id="R001",
        output_root=output_root,
        predecessor_root=predecessor,
        project_path=project,
        requirements_path=requirements,
    )
    return output_root / "R001"


def test_prepare_handoff_preserves_predecessor_and_does_not_create_revision(tmp_path: Path) -> None:
    predecessor = tmp_path / "predecessor"
    original = _write_predecessor(predecessor)
    project, requirements = _write_inputs(tmp_path)
    output_root = tmp_path / "handoffs"

    result = create_handoff_package(
        revision_id="R001",
        output_root=output_root,
        predecessor_root=predecessor,
        project_path=project,
        requirements_path=requirements,
    )

    package = output_root / "R001"
    assert result["immutable_revision_created"] is False
    assert result["site_selected"] is False
    assert not (tmp_path / "revisions/R001").exists()
    manifest = read_json(package / "handoff-manifest.json")
    assert manifest["schema"] == HANDOFF_SCHEMA
    assert manifest["expected_scope"]["storeys"] == [
        {"building_id": "A", "floor_id": "floor-1"}
    ]
    assert manifest["expected_scope"]["confirmed_must_requirement_ids"] == ["A.floor-1.living"]
    for name, content in original.items():
        copied = package / "legacy-reference" / name
        assert copied.read_bytes() == content
        record = next(item for item in manifest["predecessor"]["files"] if item["file"].endswith(name))
        assert record["sha256"] == sha256_file(copied)
        assert record["authority"] == "historical_requirement_reference_only"
    assert read_json(package / "delivery.json")["schema"] == DELIVERY_SCHEMA
    assert "不會建立或覆寫 `inputs/revisions/R001`" in (package / "README.md").read_text(encoding="utf-8")

    with pytest.raises(ContractError, match="already exists"):
        create_handoff_package(
            revision_id="R001",
            output_root=output_root,
            predecessor_root=predecessor,
            project_path=project,
            requirements_path=requirements,
        )


def test_preflight_reports_template_as_incomplete_json_instead_of_importing(tmp_path: Path) -> None:
    package = _create_package(tmp_path)

    result = preflight_handoff_package(package)

    assert result["ready_for_import"] is False
    assert result["ready_for_space_block"] is False
    assert result["import_preview"] is None
    codes = {item["code"] for item in result["checks"] if item["status"] == "fail"}
    assert {"PREPARER_EVIDENCE", "DELIVERY_DECLARATIONS", "PDF_SOURCE", "MACHINE_SOURCE"} <= codes
    assert not (package / "inputs/revisions/R001").exists()


def test_preflight_rejects_file_reference_outside_package(tmp_path: Path) -> None:
    package = _create_package(tmp_path)
    delivery = read_json(package / "delivery.json")
    delivery["files"]["pdf"] = "../outside.pdf"
    write_json(package / "delivery.json", delivery)

    result = preflight_handoff_package(package)

    path_check = next(item for item in result["checks"] if item["code"] == "PDF_PATH")
    assert path_check["status"] == "fail"
    assert "escapes" in path_check["message"]


def test_preflight_preview_import_can_pass_space_block_without_creating_r001(tmp_path: Path) -> None:
    ezdxf = pytest.importorskip("ezdxf")
    reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    package = _create_package(tmp_path)
    incoming = package / "incoming"
    incoming.mkdir()
    pdf = incoming / "R001.pdf"
    canvas = reportlab_canvas.Canvas(str(pdf))
    canvas.drawString(72, 760, "R001 architect delivery")
    canvas.save()
    dxf = incoming / "R001.dxf"
    document = ezdxf.new("R2013")
    document.units = ezdxf.units.MM
    document.layers.add("ROOM-A-1F")
    document.modelspace().add_lwpolyline(
        [(0, 0), (5000, 0), (5000, 4000), (0, 4000)],
        close=True,
        dxfattribs={"layer": "ROOM-A-1F"},
    )
    document.saveas(dxf)

    mapping = read_json(package / "mapping.json")
    mapping["coordinate_system"] = {
        "status": "verified",
        "unit": "mm",
        "axis": {"x": "east", "y": "north", "z": "up"},
        "verified_by": "王建築師",
        "verified_at": "2026-09-01",
        "method": "two shared control points",
        "reference_points": [
            {"id": "P1", "source_mm": [0, 0], "project_mm": [0, 0]},
            {"id": "P2", "source_mm": [5000, 0], "project_mm": [5000, 0]},
        ],
    }
    mapping["storeys"] = [
        {
            "building_id": "A",
            "floor_id": "floor-1",
            "elevation_mm": 0,
            "height_mm": 3200,
            "verified_by": "王建築師",
            "verified_at": "2026-09-01",
            "evidence": {"type": "level_note", "reference": "A-101 / EL±0"},
        }
    ]
    mapping["layers"] = {
        "ROOM-A-1F": {
            "kind": "space",
            "building_id": "A",
            "floor_id": "floor-1",
            "name": "客廳",
            "requirement_id": "A.floor-1.living",
        }
    }
    mapping["walkthrough_scope"] = {
        "equipment": {
            "status": "verified_not_applicable",
            "verified_by": "王建築師",
            "verified_at": "2026-09-01",
            "evidence": "A-101 equipment scope note",
        }
    }
    write_json(package / "mapping.json", mapping)

    delivery = read_json(package / "delivery.json")
    delivery.update({"prepared_by": "王建築師", "prepared_at": "2026-09-01"})
    delivery["files"].update({"pdf": "incoming/R001.pdf", "dxf": "incoming/R001.dxf"})
    delivery["declarations"] = {
        "building_ids": ["A"],
        "source_files_are_final_for_this_revision": True,
        "coordinate_system_reviewed": True,
        "storey_elevations_reviewed": True,
        "room_boundaries_reviewed": True,
        "openings_include_position_and_height": True,
        "equipment_scope_reviewed": True,
    }
    write_json(package / "delivery.json", delivery)

    result = preflight_handoff_package(package)

    assert result["ready_for_import"] is True
    assert result["ready_for_space_block"] is True
    assert result["ready_for_walkthrough"] is False
    assert result["project_ready_for_design"] is False
    assert result["import_preview"]["status"] == "ready"
    assert result["import_preview"]["normalized_space_count"] == 1
    assert not (package / "inputs/revisions/R001").exists()


def test_preflight_cli_outputs_json_and_nonzero_for_incomplete_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from house_design.cli import main

    package = _create_package(tmp_path)
    monkeypatch.setattr(sys, "argv", ["house-design", "drawings", "preflight", "--package", str(package)])

    with pytest.raises(SystemExit) as exc_info:
        main()

    result = json.loads(capsys.readouterr().out)
    assert exc_info.value.code == 1
    assert result["schema"] == "house-architect-delivery-preflight-v1"


def test_repository_r001_handoff_snapshots_are_sealed_and_still_only_a_template() -> None:
    package = REPO_ROOT / "structured/architect_handoffs/R001"
    manifest = read_json(package / "handoff-manifest.json")

    assert manifest["revision_id"] == "R001"
    assert manifest["immutable_revision_created"] is False
    assert manifest["project_gate"]["site_selected"] is False
    assert len(manifest["expected_scope"]["storeys"]) == 12
    assert manifest["expected_scope"]["requirement_status_counts"] == {"candidate": 64}
    for record in manifest["predecessor"]["files"]:
        assert sha256_file(package / record["file"]) == record["sha256"]
    for record in manifest["snapshots"].values():
        assert sha256_file(package / record["file"]) == record["sha256"]
    assert not (REPO_ROOT / "inputs/revisions/R001/manifest.json").exists()


def _valid_handoff_inputs(root: Path) -> tuple[Path, Path]:
    project = root / "project.json"
    requirements = root / "requirements.json"
    write_json(
        project,
        {
            "schema": "house-project-v3",
            "project_id": "test-project",
            "stage": "site_search",
            "jurisdiction": {"country_code": "TW", "county_code": "KHH", "label": "高雄"},
            "site_search": {
                "selected_site": None,
                "target_scenario": {
                    "parcel_relationship": "adjacent_separate_parcels",
                    "target_parcel_count": 3,
                    "target_area_ping_each": 32.0,
                },
                "candidate_sites": [],
            },
            "buildings": [
                {"id": "A", "role": "主要設備與全齡生活棟", "role_status": "owner_confirmed_predesign_policy"},
                {"id": "B", "role": "祭祀傳承棟", "role_status": "owner_confirmed_predesign_policy"},
                {"id": "C", "role": "長輩友善自住棟", "role_status": "owner_confirmed_predesign_policy"},
            ],
        },
    )
    write_json(
        requirements,
        {
            "schema": "house-requirements-v2",
            "requirements": [
                {
                    "id": "A.floor-1.living",
                    "title": "客廳",
                    "status": "confirmed",
                    "priority": "must",
                    "applies_to": {"building_id": "A", "floor_id": "floor-1"},
                    "source": {"type": "owner_decision", "path": "decision-log"},
                }
            ],
        },
    )
    return project, requirements


def _build_brief(root: Path, project: Path, requirements: Path) -> tuple[Path, dict]:
    brief_path = root / "design-brief.json"
    brief = build_design_brief(
        project_path=project,
        requirements_path=requirements,
        physical_items_path=root / "missing-physical-items.json",
        household_profile_path=root / "missing-household-profile.json",
        design_request_path=root / "missing-design-request.md",
        standards_path=root / "missing-standards.json",
    )
    write_json(brief_path, brief)
    return brief_path, brief


def test_prepare_handoff_snapshots_the_verified_design_brief(tmp_path: Path) -> None:
    predecessor = tmp_path / "predecessor"
    _write_predecessor(predecessor)
    project, requirements = _valid_handoff_inputs(tmp_path)
    brief_path, brief = _build_brief(tmp_path, project, requirements)
    output_root = tmp_path / "handoffs"

    result = create_handoff_package(
        revision_id="R001",
        output_root=output_root,
        predecessor_root=predecessor,
        project_path=project,
        requirements_path=requirements,
        brief_path=brief_path,
    )

    package = output_root / "R001"
    manifest = read_json(package / "handoff-manifest.json")
    snapshot = manifest["snapshots"]["design_brief"]
    assert snapshot["brief_hash"] == brief["brief_hash"]
    assert snapshot["sha256"] == sha256_file(package / "design-brief.snapshot.json")
    assert read_json(package / "design-brief.snapshot.json")["brief_hash"] == brief["brief_hash"]
    assert (package / "design-brief.md").is_file()
    assert result["design_brief"] == str(package / "design-brief.html")
    assert result["brief_hash"] == brief["brief_hash"]
    readme = (package / "README.md").read_text(encoding="utf-8")
    assert "design-brief.html" in readme and "任務書雜湊" in readme
    assert "設計任務書" in (package / "architect-request.html").read_text(encoding="utf-8")


def test_prepare_handoff_refuses_a_tampered_brief_before_writing_anything(tmp_path: Path) -> None:
    predecessor = tmp_path / "predecessor"
    _write_predecessor(predecessor)
    project, requirements = _valid_handoff_inputs(tmp_path)
    brief_path, brief = _build_brief(tmp_path, project, requirements)
    brief["decision_summary"]["requirements"] = 99
    write_json(brief_path, brief)
    output_root = tmp_path / "handoffs"

    with pytest.raises(ContractError, match="does not match its brief_hash"):
        create_handoff_package(
            revision_id="R001",
            output_root=output_root,
            predecessor_root=predecessor,
            project_path=project,
            requirements_path=requirements,
            brief_path=brief_path,
        )
    assert not (output_root / "R001").exists()


def test_prepare_handoff_refuses_a_stale_brief_before_writing_anything(tmp_path: Path) -> None:
    predecessor = tmp_path / "predecessor"
    _write_predecessor(predecessor)
    project, requirements = _valid_handoff_inputs(tmp_path)
    brief_path, _brief = _build_brief(tmp_path, project, requirements)
    register = read_json(requirements)
    register["requirements"][0]["title"] = "客廳（更新）"
    write_json(requirements, register)
    output_root = tmp_path / "handoffs"

    with pytest.raises(ContractError, match="stale"):
        create_handoff_package(
            revision_id="R001",
            output_root=output_root,
            predecessor_root=predecessor,
            project_path=project,
            requirements_path=requirements,
            brief_path=brief_path,
        )
    assert not (output_root / "R001").exists()

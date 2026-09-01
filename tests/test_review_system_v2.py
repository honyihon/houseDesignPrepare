from __future__ import annotations

from pathlib import Path

from house_design.contracts import sha256_file, write_json
from house_design.dashboard import dashboard_html
from house_design.drawings import revision_manifest_content_hash
from house_design.review import build_review, review_markdown, validate_signoff


def _project() -> dict:
    return {
        "schema": "house-project-v2",
        "project_id": "test",
        "name": "測試專案",
        "jurisdiction": {"country_code": "TW", "county_code": "KHH", "label": "高雄"},
        "parcel_relationship": "adjacent_separate_parcels",
        "parcels": [
            {
                "id": key,
                "parcel_area_ping": 32.0,
                "parcel_area_sqm": 105.78512,
                "land_number": None,
                "zoning": None,
                "road": {"status": "unknown"},
                "building_coverage_ratio": None,
                "floor_area_ratio": None,
            }
            for key in ("A", "B", "C")
        ],
        "compound": {"shared_items_to_confirm": []},
    }


def _requirements(status: str = "confirmed") -> dict:
    return {
        "schema": "house-requirements-v2",
        "requirements": [
            {
                "id": "A.floor-1.elder",
                "title": "孝親房",
                "category": "bedroom",
                "applies_to": {"building_id": "A", "floor_id": "floor-1"},
                "status": status,
                "priority": "must",
                "constraints": {"min_sqm": 10.0, "wheelchair_turn": True, "door_clear_mm": 900},
                "source": {"type": "owner_decision", "path": "decision-log"},
            }
        ],
    }


def _model() -> dict:
    return {
        "schema": "house-normalized-model-v1",
        "revision_id": "R001",
        "entities": {
            "buildings": [],
            "storeys": [],
            "spaces": [
                {
                    "id": "space-1",
                    "source_id": "elder",
                    "requirement_id": "A.floor-1.elder",
                    "building_id": "A",
                    "floor_id": "floor-1",
                    "name": "孝親房",
                    "area_sqm": 8.4,
                    "width_mm": 1400,
                    "depth_mm": 6000,
                    "bbox_mm": [0, 0, 1400, 6000],
                }
            ],
            "doors": [
                {
                    "id": "door-1",
                    "to": "elder",
                    "clear_width_mm": 800,
                    "building_id": "A",
                    "floor_id": "floor-1",
                }
            ],
            "windows": [],
            "equipment": [],
            "drawing_geometry": [],
        },
    }


def _build(tmp_path: Path, requirement_status: str = "confirmed") -> dict:
    project_path = tmp_path / "project.json"
    requirements_path = tmp_path / "requirements.json"
    rules_path = tmp_path / "rules.json"
    revision_root = tmp_path / "revisions"
    revision_dir = revision_root / "R001"
    model_path = revision_dir / "model.json"
    write_json(project_path, _project())
    write_json(requirements_path, _requirements(requirement_status))
    write_json(rules_path, {"schema": "house-rule-pack-v2", "rules": []})
    write_json(model_path, _model())
    manifest = {
            "schema": "house-drawing-revision-v1",
            "revision_id": "R001",
            "label": "初步設計",
            "status": "ready",
            "content_hash": "drawing-hash",
            "normalized_model": str(model_path),
            "normalized_model_sha256": sha256_file(model_path),
            "sources": [],
            "mapping": None,
            "issues": [],
        }
    manifest["content_hash"] = revision_manifest_content_hash(manifest)
    write_json(revision_dir / "manifest.json", manifest)
    return build_review(
        revision_id="R001",
        project_path=project_path,
        requirements_path=requirements_path,
        rule_pack_path=rules_path,
        revision_root=revision_root,
    )


def test_confirmed_must_requirement_fails_area_turn_and_door_checks(tmp_path: Path) -> None:
    report = _build(tmp_path)
    failed_rules = {item["rule_id"] for item in report["findings"] if item["status"] == "fail"}

    assert {"REQ-MIN-AREA", "ACC-WHEELCHAIR-TURN", "ACC-DOOR-CLEAR"} <= failed_rules
    assert report["release"]["eligible"] is False
    assert report["readiness"]["percent"] == 0
    assert report["model3d_readiness"]["status"] == "blocked"
    assert report["model3d_readiness"]["eligible"] is False


def test_candidate_requirement_does_not_create_hard_geometry_failures(tmp_path: Path) -> None:
    report = _build(tmp_path, "candidate")
    requirement_failures = [
        item for item in report["findings"] if item["status"] == "fail" and item["rule_id"].startswith(("REQ-", "ACC-"))
    ]

    assert requirement_failures == []
    assert any(item["rule_id"] == "REQ-OWNER-CONFIRMATION" for item in report["findings"])


def test_ai_or_wrong_revision_signoff_is_invalid(tmp_path: Path) -> None:
    report = _build(tmp_path)
    ai = validate_signoff(
        report,
        {
            "decision": "approved",
            "reviewer_kind": "human",
            "reviewer_role": "architect",
            "reviewer_name": "Claude Code",
            "reviewer_date": "2026-08-27",
            "revision_id": "R001",
            "related_report_hash": report["report_hash"],
        },
    )
    wrong_revision = validate_signoff(
        report,
        {
            "decision": "approved",
            "reviewer_kind": "human",
            "reviewer_role": "architect",
            "reviewer_name": "王建築師",
            "reviewer_date": "2026-08-27",
            "revision_id": "R000",
            "related_report_hash": report["report_hash"],
        },
    )

    assert ai["valid"] is False
    assert wrong_revision["valid"] is False


def test_dashboard_is_offline_and_exposes_unknown_as_separate_status(tmp_path: Path) -> None:
    report = _build(tmp_path)
    document = dashboard_html(report)

    assert "住宅設計檢核中心" in document
    assert "未知" in document
    assert "專業確認" in document
    assert 'id="model3dReadiness"' in document
    assert "現行空間量體模型" in document
    assert "SPACE_GEOMETRY_MISSING" not in document
    assert "COORDINATE_SYSTEM_UNVERIFIED" in document
    assert "https://" not in document
    assert "reportData" in document

    markdown = review_markdown(report)
    assert "## 現行 revision 3D" in markdown
    assert "**blocked**" in markdown
    assert "COORDINATE_SYSTEM_UNVERIFIED" in markdown

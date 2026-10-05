from __future__ import annotations

from pathlib import Path

from house_design.contracts import sha256_file, stable_hash, write_json
from house_design.dashboard import dashboard_html
from house_design.drawings import revision_manifest_content_hash
from house_design.intake import relationship_hash
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


def _build_with(tmp_path: Path, requirements: dict, model: dict) -> dict:
    project_path = tmp_path / "project.json"
    requirements_path = tmp_path / "requirements.json"
    rules_path = tmp_path / "rules.json"
    revision_root = tmp_path / "revisions"
    revision_dir = revision_root / "R001"
    model_path = revision_dir / "model.json"
    write_json(project_path, _project())
    write_json(requirements_path, requirements)
    write_json(rules_path, {"schema": "house-rule-pack-v2", "rules": []})
    write_json(model_path, model)
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


def _build(tmp_path: Path, requirement_status: str = "confirmed") -> dict:
    return _build_with(tmp_path, _requirements(requirement_status), _model())


def _decision(relationships: list[dict], *, priority: str = "must") -> dict:
    entry = {
        "sequence": 1,
        "previous": None,
        "status": "confirmed",
        "priority": priority,
        "reason": "測試確認",
        "decided_by": "屋主",
        "decided_at": "2026-09-15",
        "relationship_hashes": [relationship_hash(item) for item in relationships],
        "previous_entry_hash": None,
    }
    entry["entry_hash"] = stable_hash(entry)
    return entry


def _requirement(
    req_id: str,
    title: str,
    *,
    priority: str = "must",
    relationships: list[dict] | None = None,
    confirm_relationships: bool = True,
    status: str = "confirmed",
) -> dict:
    building, floor, _local = req_id.split(".", 2)
    item: dict = {
        "id": req_id,
        "title": title,
        "category": "bedroom",
        "applies_to": {"building_id": building, "floor_id": floor},
        "status": status,
        "priority": priority,
        "constraints": {},
        "source": {"type": "owner_decision", "path": "decision-log"},
    }
    if relationships is not None:
        item["relationships"] = relationships
        if status == "confirmed" and confirm_relationships:
            item["decision_log"] = [_decision(relationships, priority=priority)]
    return item


def _requirements_with(*items: dict) -> dict:
    return {"schema": "house-requirements-v2", "requirements": list(items)}


def _space(req_id: str, bbox: list[int], *, floor: str = "floor-1", exact: bool = True) -> dict:
    x0, y0, x1, y1 = bbox
    space: dict = {
        "id": f"space-{req_id}",
        "source_id": req_id.rsplit(".", 1)[-1],
        "requirement_id": req_id,
        "building_id": req_id.split(".", 1)[0],
        "floor_id": floor,
        "name": req_id,
        "area_sqm": (x1 - x0) * (y1 - y0) / 1e6,
        "width_mm": x1 - x0,
        "depth_mm": y1 - y0,
        "bbox_mm": list(bbox),
    }
    if exact:
        space["geometry_method"] = "closed_dxf_polyline"
        space["polygon_mm"] = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
    return space


def _model_with(spaces: list[dict], *, coordinate_system: dict | None = None) -> dict:
    model = _model()
    model["entities"]["spaces"] = spaces
    if coordinate_system is not None:
        model["coordinate_system"] = coordinate_system
    return model


def _verified_coordinate_system() -> dict:
    return {
        "status": "verified",
        "axis": "world",
        "verified_by": "測試建築師",
        "verified_at": "2026-09-15",
        "method": "圖面對位",
        "reference_points": [{"x": 0, "y": 0}, {"x": 1000, "y": 0}],
    }


def _relationship_findings(report: dict, rule_id: str) -> list[dict]:
    return [item for item in report["findings"] if item["rule_id"] == rule_id]


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


def test_adjacent_relationship_passes_when_exact_rectangles_touch(tmp_path: Path) -> None:
    requirements = _requirements_with(
        _requirement(
            "A.floor-1.elder",
            "孝親房",
            relationships=[{"type": "adjacent", "target": "A.floor-1.bath1", "rationale": "測試"}],
        ),
        _requirement("A.floor-1.bath1", "孝親衛浴"),
    )
    model = _model_with(
        [_space("A.floor-1.elder", [0, 0, 3000, 4000]), _space("A.floor-1.bath1", [3000, 0, 5000, 4000])]
    )
    report = _build_with(tmp_path, requirements, model)

    findings = _relationship_findings(report, "REQ-RELATIONSHIP-ADJACENT")
    assert len(findings) == 1
    assert findings[0]["status"] == "pass"


def test_adjacent_relationship_fails_when_spaces_are_far_apart(tmp_path: Path) -> None:
    requirements = _requirements_with(
        _requirement(
            "A.floor-1.elder",
            "孝親房",
            relationships=[{"type": "adjacent", "target": "A.floor-1.bath1", "rationale": "測試"}],
        ),
        _requirement("A.floor-1.bath1", "孝親衛浴"),
    )
    model = _model_with(
        [_space("A.floor-1.elder", [0, 0, 3000, 4000]), _space("A.floor-1.bath1", [6000, 0, 8000, 4000])]
    )
    report = _build_with(tmp_path, requirements, model)

    findings = _relationship_findings(report, "REQ-RELATIONSHIP-ADJACENT")
    assert len(findings) == 1
    assert findings[0]["status"] == "fail"
    assert findings[0]["severity"] == "error"


def test_adjacent_relationship_is_warning_for_should_priority(tmp_path: Path) -> None:
    requirements = _requirements_with(
        _requirement(
            "A.floor-1.elder",
            "孝親房",
            priority="should",
            relationships=[{"type": "adjacent", "target": "A.floor-1.bath1", "rationale": "測試"}],
        ),
        _requirement("A.floor-1.bath1", "孝親衛浴"),
    )
    model = _model_with(
        [_space("A.floor-1.elder", [0, 0, 3000, 4000]), _space("A.floor-1.bath1", [6000, 0, 8000, 4000])]
    )
    report = _build_with(tmp_path, requirements, model)

    findings = _relationship_findings(report, "REQ-RELATIONSHIP-ADJACENT")
    assert len(findings) == 1
    assert findings[0]["status"] == "warning"


def test_not_stacked_under_passes_when_target_is_below(tmp_path: Path) -> None:
    requirements = _requirements_with(
        _requirement(
            "A.floor-2.elder",
            "孝親房",
            relationships=[{"type": "not_stacked_under", "target": "A.floor-1.bath1", "rationale": "測試"}],
        ),
        _requirement("A.floor-1.bath1", "孝親衛浴"),
    )
    model = _model_with(
        [_space("A.floor-2.elder", [0, 0, 5000, 4000], floor="floor-2"),
         _space("A.floor-1.bath1", [0, 0, 5000, 4000])]
    )
    report = _build_with(tmp_path, requirements, model)

    findings = _relationship_findings(report, "REQ-RELATIONSHIP-NOT_STACKED_UNDER")
    assert len(findings) == 1
    assert findings[0]["status"] == "pass"


def test_not_stacked_under_is_unknown_without_verified_coordinates(tmp_path: Path) -> None:
    requirements = _requirements_with(
        _requirement(
            "A.floor-1.elder",
            "孝親房",
            relationships=[{"type": "not_stacked_under", "target": "A.floor-2.bath1", "rationale": "測試"}],
        ),
        _requirement("A.floor-2.bath1", "孝親衛浴"),
    )
    model = _model_with(
        [_space("A.floor-1.elder", [0, 0, 5000, 4000]),
         _space("A.floor-2.bath1", [0, 0, 5000, 4000], floor="floor-2")]
    )
    report = _build_with(tmp_path, requirements, model)

    findings = _relationship_findings(report, "REQ-RELATIONSHIP-NOT_STACKED_UNDER")
    assert len(findings) == 1
    assert findings[0]["status"] == "unknown"
    assert "座標" in findings[0]["message"]


def test_not_stacked_under_fails_with_verified_overlap(tmp_path: Path) -> None:
    requirements = _requirements_with(
        _requirement(
            "A.floor-1.elder",
            "孝親房",
            relationships=[{"type": "not_stacked_under", "target": "A.floor-2.bath1", "rationale": "測試"}],
        ),
        _requirement("A.floor-2.bath1", "孝親衛浴"),
    )
    model = _model_with(
        [_space("A.floor-1.elder", [0, 0, 5000, 4000]),
         _space("A.floor-2.bath1", [0, 0, 5000, 4000], floor="floor-2")],
        coordinate_system=_verified_coordinate_system(),
    )
    report = _build_with(tmp_path, requirements, model)

    findings = _relationship_findings(report, "REQ-RELATIONSHIP-NOT_STACKED_UNDER")
    assert len(findings) == 1
    assert findings[0]["status"] == "fail"


def test_stacked_over_passes_and_fails_by_alignment_ratio(tmp_path: Path) -> None:
    aligned = _requirements_with(
        _requirement(
            "A.floor-2.shrine_buffer",
            "神明廳上方緩衝",
            relationships=[{"type": "stacked_over", "target": "A.floor-1.shrine", "rationale": "測試"}],
        ),
        _requirement("A.floor-1.shrine", "神明廳"),
    )
    aligned_model = _model_with(
        [_space("A.floor-2.shrine_buffer", [0, 0, 5000, 4000], floor="floor-2"),
         _space("A.floor-1.shrine", [0, 0, 5000, 4000])],
        coordinate_system=_verified_coordinate_system(),
    )
    aligned_report = _build_with(tmp_path, aligned, aligned_model)
    assert _relationship_findings(aligned_report, "REQ-RELATIONSHIP-STACKED_OVER")[0]["status"] == "pass"

    shifted = _requirements_with(
        _requirement(
            "A.floor-2.shrine_buffer",
            "神明廳上方緩衝",
            relationships=[{"type": "stacked_over", "target": "A.floor-1.shrine", "rationale": "測試"}],
        ),
        _requirement("A.floor-1.shrine", "神明廳"),
    )
    shifted_model = _model_with(
        [_space("A.floor-2.shrine_buffer", [4000, 0, 9000, 4000], floor="floor-2"),
         _space("A.floor-1.shrine", [0, 0, 5000, 4000])],
        coordinate_system=_verified_coordinate_system(),
    )
    shifted_report = _build_with(tmp_path, shifted, shifted_model)
    finding = _relationship_findings(shifted_report, "REQ-RELATIONSHIP-STACKED_OVER")[0]
    assert finding["status"] == "fail"
    assert "20%" in finding["message"]


def test_non_geometric_relationships_require_professional_review(tmp_path: Path) -> None:
    requirements = _requirements_with(
        _requirement(
            "A.floor-1.elder",
            "孝親房",
            relationships=[
                {"type": "direct_access", "target": "A.floor-1.bath1", "rationale": "測試"},
                {"type": "separate_ventilation", "target": "exterior", "rationale": "測試"},
            ],
        ),
        _requirement("A.floor-1.bath1", "孝親衛浴"),
    )
    model = _model_with(
        [_space("A.floor-1.elder", [0, 0, 3000, 4000]), _space("A.floor-1.bath1", [3000, 0, 5000, 4000])]
    )
    report = _build_with(tmp_path, requirements, model)

    assert [item["status"] for item in _relationship_findings(report, "REQ-RELATIONSHIP-DIRECT_ACCESS")] == [
        "professional_review"
    ]
    assert [item["status"] for item in _relationship_findings(report, "REQ-RELATIONSHIP-SEPARATE_VENTILATION")] == [
        "professional_review"
    ]


def test_relationship_with_missing_target_space_is_unknown(tmp_path: Path) -> None:
    requirements = _requirements_with(
        _requirement(
            "A.floor-1.elder",
            "孝親房",
            relationships=[{"type": "adjacent", "target": "A.floor-1.bath1", "rationale": "測試"}],
        ),
        _requirement("A.floor-1.bath1", "孝親衛浴"),
    )
    model = _model_with([_space("A.floor-1.elder", [0, 0, 3000, 4000])])
    report = _build_with(tmp_path, requirements, model)

    findings = _relationship_findings(report, "REQ-RELATIONSHIP-ADJACENT")
    assert len(findings) == 1
    assert findings[0]["status"] == "unknown"


def test_unconfirmed_relationship_stays_pending_without_hard_fail(tmp_path: Path) -> None:
    requirements = _requirements_with(
        _requirement(
            "A.floor-1.elder",
            "孝親房",
            relationships=[{"type": "adjacent", "target": "A.floor-1.bath1", "rationale": "測試"}],
            confirm_relationships=False,
        ),
        _requirement("A.floor-1.bath1", "孝親衛浴"),
    )
    model = _model_with(
        [_space("A.floor-1.elder", [0, 0, 3000, 4000]), _space("A.floor-1.bath1", [6000, 0, 8000, 4000])]
    )
    report = _build_with(tmp_path, requirements, model)

    assert _relationship_findings(report, "REQ-RELATIONSHIP-ADJACENT") == []
    pending = _relationship_findings(report, "REQ-RELATIONSHIP-PENDING")
    assert len(pending) == 1
    assert pending[0]["status"] == "unknown"
    assert pending[0]["evidence"][0]["count"] == 1
    assert not [item for item in report["findings"] if item["rule_id"].startswith("REQ-RELATIONSHIP-") and item["status"] == "fail"]

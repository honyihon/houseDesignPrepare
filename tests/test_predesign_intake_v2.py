from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from house_design.contracts import ContractError, write_json
from house_design.intake import (
    actual_parcels,
    decide_requirement,
    migrate_legacy_briefs,
    project_readiness,
    validate_project,
    validate_requirements,
)


ROOT = Path(__file__).resolve().parents[1]


def test_current_project_models_32_ping_as_site_search_target_not_parcel_fact() -> None:
    project = json.loads((ROOT / "inputs/project.json").read_text(encoding="utf-8"))

    assert validate_project(project) == []
    assert project["schema"] == "house-project-v3"
    assert project["stage"] == "site_search"
    assert project["site_search"]["target_scenario"]["target_area_ping_each"] == 32.0
    assert project["site_search"]["target_scenario"]["parcel_relationship"] == "adjacent_separate_parcels"
    assert project["site_search"]["selected_site"] is None
    assert actual_parcels(project) == []
    assert "parcels" not in project


def test_unknown_site_facts_are_not_counted_as_ready() -> None:
    project = json.loads((ROOT / "inputs/project.json").read_text(encoding="utf-8"))

    readiness = project_readiness(project)

    assert readiness["percent"] == 0
    assert readiness["completed"] == 0
    assert readiness["facts"][0]["key"] == "site_selection"
    assert all(fact["known"] is False for fact in readiness["facts"])


def test_site_search_targets_cannot_be_promoted_without_real_selected_parcels() -> None:
    project = json.loads((ROOT / "inputs/project.json").read_text(encoding="utf-8"))
    invalid = deepcopy(project)
    invalid["stage"] = "design"

    issues = validate_project(invalid)

    assert any(item["field"] == "site_search.selected_site" for item in issues)


def test_legacy_briefs_migrate_only_to_candidate_requirements(tmp_path: Path) -> None:
    brief_dir = tmp_path / "brief"
    brief_dir.mkdir()
    (brief_dir / "A.json").write_text(
        json.dumps(
            {
                "schema": "house-area-brief-v1",
                "building_id": "A",
                "floors": [
                    {
                        "floor_id": "floor-1",
                        "rooms": [
                            {
                                "id": "elder",
                                "name": "孝親房",
                                "kind": "bedroom",
                                "min_sqm": 10,
                                "wheelchair_turn": True,
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "requirements.json"

    payload = migrate_legacy_briefs(brief_dir=brief_dir, output=output)

    assert validate_requirements(payload) == []
    assert payload["requirements"][0]["status"] == "candidate"
    assert payload["requirements"][0]["priority"] == "should"
    assert payload["requirements"][0]["verification"]["state"] == "pending_owner_confirmation"


def test_repository_requirement_register_contains_only_unconfirmed_legacy_ideas() -> None:
    payload = json.loads((ROOT / "inputs/requirements.json").read_text(encoding="utf-8"))

    assert validate_requirements(payload) == []
    assert len(payload["requirements"]) == 64
    assert {item["status"] for item in payload["requirements"]} == {"candidate"}


def test_requirement_decisions_append_a_hash_chained_log_atomically(tmp_path: Path) -> None:
    path = tmp_path / "requirements.json"
    payload = {
        "schema": "house-requirements-v2",
        "requirements": [
            {
                "id": "A.floor-1.elder",
                "title": "孝親房",
                "status": "candidate",
                "priority": "should",
                "source": {"type": "owner_interview", "path": "notes"},
                "decision_log": [],
            }
        ],
    }
    write_json(path, payload)

    first = decide_requirement(
        requirement_id="A.floor-1.elder",
        status="confirmed",
        priority="must",
        reason="一樓完整照護生活",
        decided_by="屋主家庭會議",
        decided_at="2026-08-31",
        requirements_path=path,
    )
    second = decide_requirement(
        requirement_id="A.floor-1.elder",
        status="confirmed",
        priority="should",
        reason="預算會議後保留，但可調整面積",
        decided_by="屋主家庭會議",
        decided_at="2026-09-01",
        requirements_path=path,
    )
    stored = json.loads(path.read_text(encoding="utf-8"))
    requirement = stored["requirements"][0]

    assert first["decision_sequence"] == 1
    assert second["decision_sequence"] == 2
    assert requirement["status"] == "confirmed"
    assert requirement["priority"] == "should"
    assert requirement["decision_log"][1]["previous_entry_hash"] == requirement["decision_log"][0]["entry_hash"]
    assert validate_requirements(stored) == []


def test_requirement_decision_rejects_a_tampered_log(tmp_path: Path) -> None:
    path = tmp_path / "requirements.json"
    payload = {
        "schema": "house-requirements-v2",
        "requirements": [
            {
                "id": "A.floor-1.elder",
                "title": "孝親房",
                "status": "candidate",
                "priority": "should",
                "source": {"type": "owner_interview", "path": "notes"},
                "decision_log": [
                    {
                        "status": "confirmed",
                        "priority": "must",
                        "reason": "tampered",
                        "decided_by": "owner",
                        "decided_at": "2026-08-31",
                        "previous_entry_hash": None,
                        "entry_hash": "wrong",
                    }
                ],
            }
        ],
    }
    write_json(path, payload)

    with pytest.raises(ContractError, match="invalid requirement register"):
        decide_requirement(
            requirement_id="A.floor-1.elder",
            status="rejected",
            priority="could",
            reason="不再需要",
            decided_by="owner",
            requirements_path=path,
        )


def test_household_profile_template_keeps_sensitive_completion_private() -> None:
    template = json.loads((ROOT / "inputs/household-profile.template.json").read_text(encoding="utf-8"))

    assert template["schema"] == "house-household-profile-v1"
    assert template["household"]["future_change_scenarios"]
    assert "inputs/private/" in template["privacy_note"]

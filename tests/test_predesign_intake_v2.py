from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from house_design.intake import (
    actual_parcels,
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

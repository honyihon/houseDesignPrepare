from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from house_design.contracts import ContractError, write_json
from house_design.intake import (
    DECISION_SHEET_SCHEMA,
    actual_parcels,
    apply_requirement_decisions,
    decide_requirement,
    export_requirement_sheet,
    migrate_legacy_briefs,
    project_readiness,
    relationship_hash,
    relationship_status,
    requirement_content_hash,
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
    assert len(payload["requirements"]) == 66
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


def _register(*items: dict) -> dict:
    return {"schema": "house-requirements-v2", "requirements": list(items)}


def _req(req_id: str, title: str, *, relationships: list[dict] | None = None) -> dict:
    building, floor, _local = req_id.split(".", 2)
    item: dict = {
        "id": req_id,
        "title": title,
        "category": "bedroom",
        "applies_to": {"building_id": building, "floor_id": floor},
        "status": "candidate",
        "priority": "should",
        "constraints": {},
        "source": {"type": "owner_decision", "path": "decision-log"},
    }
    if relationships is not None:
        item["relationships"] = relationships
    return item


_ADJACENT = {"type": "adjacent", "target": "A.floor-1.bath1", "rationale": "孝親房要緊鄰衛浴"}


def test_decision_sheet_export_carries_stale_guards(tmp_path: Path) -> None:
    requirements_path = tmp_path / "requirements.json"
    write_json(
        requirements_path,
        _register(_req("A.floor-1.elder", "孝親房", relationships=[_ADJACENT]), _req("A.floor-1.bath1", "孝親衛浴")),
    )
    output = tmp_path / "sheet.json"

    result = export_requirement_sheet(requirements_path=requirements_path, output=output)
    sheet = json.loads(output.read_text(encoding="utf-8"))

    assert sheet["schema"] == DECISION_SHEET_SCHEMA
    assert result["rows"] == 2
    assert result["undecided"] == 2
    row = sheet["rows"][0]
    assert row["id"] == "A.floor-1.elder"
    assert row["requirement_hash"] == requirement_content_hash(_req("A.floor-1.elder", "孝親房", relationships=[_ADJACENT]))
    assert row["decision_count"] == 0
    assert row["relationships"] == ["必須相鄰：孝親衛浴（A.floor-1.bath1）"]
    assert (tmp_path / "sheet.md").is_file()


def test_batch_apply_confirms_requirements_and_their_relationships(tmp_path: Path) -> None:
    requirements_path = tmp_path / "requirements.json"
    write_json(
        requirements_path,
        _register(_req("A.floor-1.elder", "孝親房", relationships=[_ADJACENT]), _req("A.floor-1.bath1", "孝親衛浴")),
    )
    sheet_path = tmp_path / "sheet.json"
    export_requirement_sheet(requirements_path=requirements_path, output=sheet_path)
    sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
    sheet["rows"][0].update(decision_status="confirmed", decision_priority="must", reason="全家同意")
    sheet["rows"][1].update(decision_status="rejected", decision_priority="could", reason="改到 B 棟")
    write_json(sheet_path, sheet)

    result = apply_requirement_decisions(
        sheet_path=sheet_path, decided_by="屋主", decided_at="2026-09-15", requirements_path=requirements_path
    )

    assert result["applied"] == 2
    assert result["skipped_rows"] == 0
    payload = json.loads(requirements_path.read_text(encoding="utf-8"))
    assert validate_requirements(payload) == []
    elder = payload["requirements"][0]
    assert elder["status"] == "confirmed"
    assert elder["priority"] == "must"
    assert len(elder["decision_log"]) == 1
    assert elder["decision_log"][0]["relationship_hashes"] == [relationship_hash(_ADJACENT)]
    assert relationship_status(elder, elder["relationships"][0]) == "confirmed"
    assert payload["requirements"][1]["status"] == "rejected"
    assert result["status_counts"]["confirmed"] == 1
    assert result["status_counts"]["rejected"] == 1


def test_batch_apply_rejects_a_sheet_whose_requirement_content_changed(tmp_path: Path) -> None:
    requirements_path = tmp_path / "requirements.json"
    write_json(
        requirements_path,
        _register(_req("A.floor-1.elder", "孝親房", relationships=[_ADJACENT]), _req("A.floor-1.bath1", "孝親衛浴")),
    )
    sheet_path = tmp_path / "sheet.json"
    export_requirement_sheet(requirements_path=requirements_path, output=sheet_path)
    payload = json.loads(requirements_path.read_text(encoding="utf-8"))
    payload["requirements"][0]["title"] = "孝親房（更新說明）"
    write_json(requirements_path, payload)
    sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
    sheet["rows"][0].update(decision_status="confirmed", decision_priority="must", reason="全家同意")
    write_json(sheet_path, sheet)

    with pytest.raises(ContractError, match="requirement changed since the sheet was exported"):
        apply_requirement_decisions(
            sheet_path=sheet_path, decided_by="屋主", decided_at="2026-09-15", requirements_path=requirements_path
        )
    unchanged = json.loads(requirements_path.read_text(encoding="utf-8"))
    assert unchanged["requirements"][0]["status"] == "candidate"
    assert unchanged["requirements"][0].get("decision_log") is None


def test_batch_apply_rejects_a_sheet_superseded_by_a_newer_decision(tmp_path: Path) -> None:
    requirements_path = tmp_path / "requirements.json"
    write_json(
        requirements_path,
        _register(_req("A.floor-1.elder", "孝親房", relationships=[_ADJACENT]), _req("A.floor-1.bath1", "孝親衛浴")),
    )
    sheet_path = tmp_path / "sheet.json"
    export_requirement_sheet(requirements_path=requirements_path, output=sheet_path)
    decide_requirement(
        requirement_id="A.floor-1.elder",
        status="confirmed",
        priority="should",
        reason="會議前先確認",
        decided_by="屋主",
        decided_at="2026-09-14",
        requirements_path=requirements_path,
    )
    sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
    sheet["rows"][0].update(decision_status="rejected", decision_priority="could", reason="會議中改變主意")
    write_json(sheet_path, sheet)

    with pytest.raises(ContractError, match="a newer decision was recorded since the sheet was exported"):
        apply_requirement_decisions(
            sheet_path=sheet_path, decided_by="屋主", decided_at="2026-09-15", requirements_path=requirements_path
        )
    payload = json.loads(requirements_path.read_text(encoding="utf-8"))
    assert payload["requirements"][0]["status"] == "confirmed"
    assert len(payload["requirements"][0]["decision_log"]) == 1


def test_batch_apply_is_all_or_nothing(tmp_path: Path) -> None:
    requirements_path = tmp_path / "requirements.json"
    write_json(
        requirements_path,
        _register(_req("A.floor-1.elder", "孝親房", relationships=[_ADJACENT]), _req("A.floor-1.bath1", "孝親衛浴")),
    )
    sheet_path = tmp_path / "sheet.json"
    export_requirement_sheet(requirements_path=requirements_path, output=sheet_path)
    sheet = json.loads(sheet_path.read_text(encoding="utf-8"))
    sheet["rows"][0].update(decision_status="confirmed", decision_priority="must", reason="全家同意")
    sheet["rows"][1].update(decision_status="confirmed", decision_priority="super", reason="缺漏欄位")
    write_json(sheet_path, sheet)

    with pytest.raises(ContractError, match="nothing was written"):
        apply_requirement_decisions(
            sheet_path=sheet_path, decided_by="屋主", decided_at="2026-09-15", requirements_path=requirements_path
        )
    payload = json.loads(requirements_path.read_text(encoding="utf-8"))
    assert all(item["status"] == "candidate" for item in payload["requirements"])


def test_batch_apply_rejects_a_sheet_with_no_filled_rows(tmp_path: Path) -> None:
    requirements_path = tmp_path / "requirements.json"
    write_json(
        requirements_path,
        _register(_req("A.floor-1.elder", "孝親房", relationships=[_ADJACENT]), _req("A.floor-1.bath1", "孝親衛浴")),
    )
    sheet_path = tmp_path / "sheet.json"
    export_requirement_sheet(requirements_path=requirements_path, output=sheet_path)

    with pytest.raises(ContractError, match="no filled rows"):
        apply_requirement_decisions(
            sheet_path=sheet_path, decided_by="屋主", decided_at="2026-09-15", requirements_path=requirements_path
        )


def test_relationship_validation_rejects_broken_entries(tmp_path: Path) -> None:
    base = _req("A.floor-1.elder", "孝親房")
    cases = [
        {**_ADJACENT, "type": "next_to"},
        {**_ADJACENT, "target": "A.floor-1.ghost"},
        {**_ADJACENT, "target": "A.floor-1.elder"},
        {**_ADJACENT, "rationale": "  "},
        {**_ADJACENT, "status": "confirmed"},
        {**_ADJACENT, "must_not_pass_through": ["entry"]},
    ]
    for relationship in cases:
        payload = _register({**base, "relationships": [relationship]}, _req("A.floor-1.bath1", "孝親衛浴"))
        issues = validate_requirements(payload)
        assert issues, relationship
    payload = _register({**base, "relationships": "adjacent"}, _req("A.floor-1.bath1", "孝親衛浴"))
    assert validate_requirements(payload)


def test_relationship_added_after_confirmation_stays_candidate(tmp_path: Path) -> None:
    requirements_path = tmp_path / "requirements.json"
    write_json(
        requirements_path,
        _register(_req("A.floor-1.elder", "孝親房", relationships=[_ADJACENT]), _req("A.floor-1.bath1", "孝親衛浴")),
    )
    decide_requirement(
        requirement_id="A.floor-1.elder",
        status="confirmed",
        priority="must",
        reason="確認既有關係",
        decided_by="屋主",
        decided_at="2026-09-15",
        requirements_path=requirements_path,
    )
    payload = json.loads(requirements_path.read_text(encoding="utf-8"))
    late = {"type": "direct_access", "target": "A.floor-1.bath1", "rationale": "事後新增"}
    payload["requirements"][0]["relationships"].append(late)
    write_json(requirements_path, payload)

    elder = payload["requirements"][0]
    assert relationship_status(elder, elder["relationships"][0]) == "confirmed"
    assert relationship_status(elder, elder["relationships"][1]) == "candidate"


def test_repository_register_relationships_are_all_pending_owner_confirmation() -> None:
    payload = json.loads((ROOT / "inputs/requirements.json").read_text(encoding="utf-8"))

    assert validate_requirements(payload) == []
    relationships = [
        (item, relationship)
        for item in payload["requirements"]
        for relationship in item.get("relationships") or []
    ]
    assert len(relationships) == 11
    assert all(relationship_status(item, relationship) == "candidate" for item, relationship in relationships)


def test_cli_exports_a_decision_sheet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    import sys

    from house_design.cli import main

    requirements_path = tmp_path / "requirements.json"
    write_json(
        requirements_path,
        _register(_req("A.floor-1.elder", "孝親房", relationships=[_ADJACENT]), _req("A.floor-1.bath1", "孝親衛浴")),
    )
    output = tmp_path / "sheet.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "house-design",
            "intake",
            "requirements-sheet",
            "--requirements",
            str(requirements_path),
            "--output",
            str(output),
        ],
    )
    main()

    result = json.loads(capsys.readouterr().out)
    assert result["rows"] == 2
    assert output.is_file()


def test_cli_rejects_batch_flags_that_belong_in_the_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    import sys

    from house_design.cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "house-design",
            "intake",
            "requirements-decide",
            "--batch",
            str(tmp_path / "sheet.json"),
            "--status",
            "confirmed",
            "--decided-by",
            "屋主",
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    assert "cannot be combined with --batch" in capsys.readouterr().err


def test_cli_rejects_single_decision_with_missing_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    import sys

    from house_design.cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "house-design",
            "intake",
            "requirements-decide",
            "--id",
            "A.floor-1.elder",
            "--status",
            "confirmed",
            "--decided-by",
            "屋主",
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    assert "--id requires" in capsys.readouterr().err

from __future__ import annotations

import json
from pathlib import Path

from house_design.contracts import write_json
from house_design.dashboard import dashboard_html
from house_design.predesign import (
    BUDGET_FIELDS,
    build_predesign_report,
    validate_bundle,
    validate_predesign,
    validate_private_budget,
)
from house_design.review import build_review


ROOT = Path(__file__).resolve().parents[1]


def test_repository_predesign_is_valid_and_blocks_next_phase() -> None:
    report = build_predesign_report(private_budget_path=None)

    assert report["current_phase"] == "site_search"
    assert report["readiness"]["percent"] == 30
    assert report["gate"]["eligible_for_next_phase"] is False
    assert report["gate"]["active_blockers"] == 5
    assert {item["rule_id"] for item in report["findings"] if item["status"] == "pass"} >= {
        "PD-OWNER-ALL-AGE",
        "PD-OWNER-BUILDING-ROLES",
        "PD-OWNER-WHOLE-LIFE-COST",
    }


def test_in_progress_household_interview_surfaces_progress_without_passing_gate() -> None:
    report = build_predesign_report(private_budget_path=None)
    finding = next(item for item in report["findings"] if item["rule_id"] == "PD-OWNER-HOUSEHOLD-PROFILE")

    assert finding["status"] == "unknown"
    assert finding["severity"] == "blocking"
    assert "已私下記錄" in finding["message"]
    assert "must／should／could" in finding["message"]
    assert report["readiness"]["percent"] == 30
    assert report["gate"]["active_blockers"] == 5


def test_future_phase_items_are_planned_warnings_not_active_blockers() -> None:
    report = build_predesign_report(private_budget_path=None)
    future = [item for item in report["findings"] if not item["gate_active"]]

    assert future
    assert {item["status"] for item in future} == {"warning"}
    assert all(item["severity"] == "planned" for item in future)
    assert {
        "PD-DESIGN-STRUCTURE-HAZARDS",
        "PD-DESIGN-LIFE-SAFETY-SHRINE",
        "PD-DESIGN-VERTICAL-MOBILITY",
        "PD-DESIGN-HEALTHY-DURABLE-MATERIALS",
    } <= {item["rule_id"] for item in future}


def test_due_non_blocking_items_remain_warnings() -> None:
    report = build_predesign_report(private_budget_path=None)
    active_non_blocking = [
        item for item in report["findings"] if item["gate_active"] and not item["blocking"]
    ]

    assert active_non_blocking
    assert {item["status"] for item in active_non_blocking} == {"warning"}


def test_verified_predesign_state_requires_evidence() -> None:
    payload = json.loads((ROOT / "inputs/predesign.json").read_text(encoding="utf-8"))
    payload["states"][0]["evidence"] = []

    issues = validate_predesign(payload)

    assert any(item["field"] == "states[0].evidence" for item in issues)


def test_predesign_bundle_rejects_invalid_project_contract() -> None:
    project = json.loads((ROOT / "inputs/project.json").read_text(encoding="utf-8"))
    predesign = json.loads((ROOT / "inputs/predesign.json").read_text(encoding="utf-8"))
    rules = json.loads((ROOT / "rules/predesign_readiness_rules.json").read_text(encoding="utf-8"))
    project["schema"] = "invalid-project-schema"

    result = validate_bundle(project=project, predesign=predesign, rules=rules, private_budget=None)

    assert result["valid"] is False
    assert any(item["field"] == "schema" for item in result["issues"]["project"])


def test_private_budget_rejects_boolean_amounts() -> None:
    amounts = {field: None for field in BUDGET_FIELDS}
    amounts["construction"] = True
    budget = {"schema": "house-budget-private-v1", "currency": "TWD", "amounts": amounts}

    issues = validate_private_budget(budget)

    assert any(item["field"] == "amounts.construction" for item in issues)


def test_private_budget_path_is_gitignored() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "inputs/private/" in ignore


def test_usage_docs_cover_predesign_and_site_search_workflow() -> None:
    usage = (ROOT / "Docs/claude-code-usage.md").read_text(encoding="utf-8")
    guide = (ROOT / "Docs/predesign-owner-readiness.md").read_text(encoding="utf-8")

    assert "house_design predesign validate" in usage
    assert "house_design predesign report" in usage
    assert "inputs/private/budget.json" in usage
    assert "選地目標" in usage
    assert "最容易完工後後悔的十二類事情" in guide


def test_private_budget_values_never_enter_report(tmp_path: Path) -> None:
    amounts = {field: 0 for field in BUDGET_FIELDS}
    amounts["construction"] = 987_654_321
    amounts["total_ceiling"] = 999_999_999
    budget = {"schema": "house-budget-private-v1", "currency": "TWD", "amounts": amounts}
    budget_path = tmp_path / "budget.json"
    write_json(budget_path, budget)

    assert validate_private_budget(budget) == []
    report = build_predesign_report(private_budget_path=budget_path)
    serialized = json.dumps(report, ensure_ascii=False)

    assert report["private_budget"]["present"] is True
    assert report["private_budget"]["populated_fields"] == len(BUDGET_FIELDS)
    assert "987654321" not in serialized
    assert "999999999" not in serialized


def test_complete_private_budget_can_satisfy_public_budget_gates(tmp_path: Path) -> None:
    predesign = json.loads((ROOT / "inputs/predesign.json").read_text(encoding="utf-8"))
    predesign["budget_policy"].update(
        {"ceiling_status": "confirmed", "scope_status": "confirmed", "contingency_status": "confirmed"}
    )
    predesign_path = tmp_path / "predesign.json"
    write_json(predesign_path, predesign)
    amounts = {field: 0 for field in BUDGET_FIELDS}
    amounts["construction"] = 10_000_003
    amounts["total_ceiling"] = 20_000_007
    budget_path = tmp_path / "budget.json"
    write_json(budget_path, {"schema": "house-budget-private-v1", "currency": "TWD", "amounts": amounts})

    report = build_predesign_report(predesign_path=predesign_path, private_budget_path=budget_path)
    statuses = {item["rule_id"]: item["status"] for item in report["findings"]}
    serialized = json.dumps(report, ensure_ascii=False)

    assert statuses["PD-BUDGET-CEILING"] == "pass"
    assert statuses["PD-BUDGET-SCOPE-CONTINGENCY"] == "pass"
    assert "10000003" not in serialized
    assert "20000007" not in serialized


def test_revision_review_includes_only_due_predesign_findings() -> None:
    report = build_review(
        revision_id="R000",
        predesign_path=ROOT / "inputs/predesign.json",
        predesign_rule_pack_path=ROOT / "rules/predesign_readiness_rules.json",
        private_budget_path=None,
    )
    predesign_rules = [item for item in report["findings"] if item["rule_id"].startswith("PD-")]

    assert predesign_rules
    assert all(item["gate_active"] for item in predesign_rules)
    assert not any(item["phase"] == "construction" for item in predesign_rules)
    assert report["predesign"]["gate"]["active_blockers"] == 5
    assert report["release"]["eligible"] is False
    dashboard = dashboard_html(report)
    assert "前期階段閘門" in dashboard
    assert "predesignBlockers" in dashboard

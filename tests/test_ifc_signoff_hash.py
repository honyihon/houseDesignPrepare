from __future__ import annotations

import evaluate_expert_gates as gates


def _report(generated_at: str, signoff: dict | None = None, report_hash: str = "") -> dict:
    report = {
        "schema_version": "expert-review-v1",
        "generated_at": generated_at,
        "input": {"mode": "ifc", "buildings": ["A"]},
        "hard_gate": "pass",
        "critical_failures": [],
        "warnings": [],
        "infos": [],
        "signoff": signoff or {},
        "rule_results": [],
    }
    if report_hash:
        report["report_hash"] = report_hash
    return report


def test_report_content_hash_ignores_volatile_report_fields() -> None:
    first = _report(
        "2026-07-10T01:00:00+00:00",
        signoff={"decision": "pending", "related_report_hash": ""},
        report_hash="old",
    )
    second = _report(
        "2026-07-10T02:00:00+00:00",
        signoff={"decision": "approved", "related_report_hash": "abc"},
        report_hash="new",
    )

    assert gates.report_hash_payload(first) == gates.report_hash_payload(second)
    assert gates.report_content_hash(first) == gates.report_content_hash(second)


def test_validate_signoff_for_report_requires_matching_hash() -> None:
    report = _report("2026-07-10T01:00:00+00:00")
    report["report_hash"] = gates.report_content_hash(report)

    stale = gates.validate_signoff_for_report(
        {"decision": "approved", "related_report_hash": "stale"},
        report,
    )
    fresh = gates.validate_signoff_for_report(
        {
            "decision": "approved",
            "reviewer_role": "owner",
            "reviewer_name": "I29786",
            "reviewer_date": "2026-07-10",
            "related_report_hash": report["report_hash"],
            "related_report_generated_at": report["generated_at"],
        },
        report,
    )

    assert stale["valid"] is False
    assert stale["hash_match"] is False
    assert fresh["valid"] is True
    assert fresh["hash_match"] is True
    assert fresh["related_report_hash"] == report["report_hash"]

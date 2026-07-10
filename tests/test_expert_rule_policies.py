from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

import evaluate_expert_gates as gates


def _context(html: str) -> gates.RuleEvalContext:
    return gates.RuleEvalContext(
        request_text="",
        request_sections={},
        selected_buildings=["A"],
        soups={"A": BeautifulSoup(html, "html.parser")},
        program={},
        candidates={},
        architect_metrics={},
    )


def test_ground_floor_entry_policy_reports_missing_main_entry() -> None:
    ctx = _context(
        """
        <div class="floor-plan" id="floor-1">
          <div class="floor-title"><div>1F</div></div>
          <div class="plan-cell"><span class="cell-name">客廳</span></div>
        </div>
        """
    )

    passed, evidence = gates.evaluate_entry_ground_floor({}, ctx)

    assert passed is False
    assert evidence == ["A:floor-1 entry_count=0"]


def test_ground_floor_entry_policy_uses_floor_icon_not_full_title_text() -> None:
    ctx = _context(
        """
        <div class="floor-plan" id="floor-1">
          <div class="floor-title">
            <div class="floor-title-icon">1F</div>
            <div>
              <div>公共空間 × 孝親房</div>
              <div>主入口與無障礙動線</div>
            </div>
          </div>
          <div class="plan-cell"><span class="cell-name">客廳</span></div>
        </div>
        """
    )

    passed, evidence = gates.evaluate_entry_ground_floor({}, ctx)

    assert passed is False
    assert evidence == ["A:floor-1 entry_count=0"]


def test_ground_floor_entry_policy_ignores_upper_floor() -> None:
    ctx = _context(
        """
        <div class="floor-plan" id="floor-2">
          <div class="floor-title"><div>2F</div></div>
          <div class="plan-cell"><span class="cell-name">起居室</span></div>
        </div>
        """
    )

    passed, evidence = gates.evaluate_entry_ground_floor({}, ctx)

    assert passed is True
    assert evidence == []


def test_accessible_door_policy_supports_aliases_and_full_cell_text() -> None:
    ctx = _context(
        """
        <div class="floor-plan" id="floor-1">
          <div class="plan-cell" data-door-mm="900">
            <span class="cell-name">孝親衛浴</span>
            <span class="badge">無障礙</span>
          </div>
        </div>
        """
    )

    passed, evidence = gates.evaluate_accessible_door_min(
        {"keywords": ["無障礙", "孝親"], "min_mm": 800},
        ctx,
    )

    assert passed is True
    assert evidence == []


def test_accessible_door_policy_supports_room_role_elder() -> None:
    ctx = _context(
        """
        <div class="floor-plan" id="floor-1">
          <div class="plan-cell" data-door-mm="760" data-room-role="elder">
            <span class="cell-name">Guest Room</span>
          </div>
        </div>
        """
    )

    passed, evidence = gates.evaluate_accessible_door_min(
        {"keywords": ["無障礙"], "min_mm": 800},
        ctx,
    )

    assert passed is False
    assert evidence == ["A:Guest Room accessible_door_mm=760<800"]


def test_report_markdown_surfaces_review_items_and_artifacts() -> None:
    md = gates.generate_report_md(
        {
            "generated_at": "2026-07-10T00:00:00+00:00",
            "input": {"mode": "ifc", "buildings": ["A", "B", "C"]},
            "hard_gate": "pass",
            "critical_failures": [],
            "warnings": [
                {
                    "rule_id": "INT-003",
                    "message": "需求文件應包含偏好描述。",
                    "evidence": ["request missing section like '偏好'"],
                    "fix_hint": "補上採光、收納、智能家居偏好。",
                }
            ],
            "infos": [
                {
                    "rule_id": "ARCH-MET-002",
                    "message": "Architect metrics identified items requiring professional review.",
                    "evidence": ["professional_required=18"],
                    "fix_hint": "Keep these items as architect/engineer confirmation tasks.",
                }
            ],
            "score_breakdown": {
                "weights": {},
                "averages": {},
                "pipeline_changed_floor_count": 0,
            },
            "architect_metrics_summary": {},
            "citations": [],
            "artifacts": {
                "domain_checklist": "structured/expert_review/domain_checklist.md",
                "architect_metrics_report": "structured/architect_metrics/report.md",
            },
        }
    )

    assert "## Warnings" in md
    assert "`INT-003` 需求文件應包含偏好描述。" in md
    assert "request missing section like '偏好'" in md
    assert "補上採光、收納、智能家居偏好。" in md
    assert "## Info Items" in md
    assert "`ARCH-MET-002` Architect metrics identified items requiring professional review." in md
    assert "professional_required=18" in md
    assert "## Review Artifacts" in md
    assert "structured/expert_review/domain_checklist.md" in md


def test_artifact_paths_use_markdown_friendly_slashes() -> None:
    path = gates.ROOT / Path("structured") / "expert_review" / "report.md"

    assert gates.artifact_path(path) == "structured/expert_review/report.md"

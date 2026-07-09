from __future__ import annotations

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

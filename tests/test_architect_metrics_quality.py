from __future__ import annotations

from scripts.lib.architect_metrics import (
    STATUS_MISSING,
    build_structure_review_metric,
    summarize_metrics_payload,
)


def test_note_only_rf_reference_does_not_trigger_structure_review() -> None:
    room = {
        "uid": "A:floor-1:stair-door",
        "name": "樓梯口隔斷門",
        "notes_normalized": ["門位與 1F/2F/3F/RF 保持直上直下對位"],
        "notes_rendered": [],
    }
    cell = {"name": "樓梯口隔斷門", "badges": [], "classes": ["stair"]}

    metric = build_structure_review_metric("A", {"id": "floor-1"}, room, cell)

    assert metric is None


def test_named_heat_pump_triggers_structure_review() -> None:
    room = {
        "uid": "C:floor-4:heatpump",
        "name": "熱泵熱水器",
        "notes_normalized": ["設備基座抬高 15cm"],
        "notes_rendered": [],
    }
    cell = {"name": "熱泵熱水器", "badges": [], "classes": []}

    metric = build_structure_review_metric("C", {"id": "floor-4"}, room, cell)

    assert metric is not None
    assert metric["status"] == STATUS_MISSING
    assert metric["inputs"]["matched_keywords"] == ["熱泵"]


def test_explicit_structural_review_marker_triggers_metric() -> None:
    room = {
        "uid": "A:floor-2:custom",
        "name": "彈性空間",
        "structural_review": "required",
        "notes_normalized": ["需由結構技師確認"],
        "notes_rendered": [],
    }
    cell = {"name": "彈性空間", "badges": [], "classes": []}

    metric = build_structure_review_metric("A", {"id": "floor-2"}, room, cell)

    assert metric is not None
    assert metric["status"] != STATUS_MISSING


def _issue_metric(building: str, index: int) -> dict:
    return {
        "building_id": building,
        "floor_id": "floor-1",
        "room_uid": f"{building}:floor-1:room-{index}",
        "metric_type": "structure_load_review",
        "status": STATUS_MISSING,
        "result": {},
        "issues": [f"issue-{building}-{index}"],
    }


def test_top_issues_use_uid_once_and_balance_buildings() -> None:
    metrics = [_issue_metric("A", index) for index in range(21)]
    metrics.extend([_issue_metric("B", 1), _issue_metric("C", 1)])

    summary = summarize_metrics_payload(
        {
            "metrics": metrics,
            "evaluated_floor_count": 3,
            "skipped_floor_count": 0,
        }
    )
    top_issues = summary["top_issues"]

    assert any(issue.startswith("B:floor-1:room-1:") for issue in top_issues)
    assert any(issue.startswith("C:floor-1:room-1:") for issue in top_issues)
    assert not any(
        issue.startswith("A:floor-1:A:floor-1:")
        for issue in top_issues
    )

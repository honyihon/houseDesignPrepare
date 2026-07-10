from __future__ import annotations

from scripts.generate_domain_checklist import build_domain_checklist, render_domain_checklist_md


def test_domain_checklist_contains_current_owner_architect_questions() -> None:
    checklist = build_domain_checklist(
        report={"report_hash": "abc123"},
        html_consistency={"issues": []},
        room_program={"buildings": []},
        metrics={"summary": {"action_groups": {}}},
    )
    text = "\n".join(item["title"] for item in checklist["items"])

    assert "A 2F 高雄厝陽台方向確認" in text
    assert "A 棟低成本冷氣擴散策略" in text
    assert "B 棟神明廳上下疊圖與排煙防火" in text
    assert "C 棟側院、洗衣、運動與 RF 設備確認" in text


def test_domain_checklist_markdown_has_no_compliance_claim() -> None:
    checklist = build_domain_checklist(
        report={"report_hash": "abc123"},
        html_consistency={"issues": []},
        room_program={"buildings": []},
        metrics={"summary": {"action_groups": {}}},
    )
    md = render_domain_checklist_md(checklist)

    assert "不作為法規、結構、消防、採光、通風或無障礙合規證明" in md
    assert "已通過法規" not in md

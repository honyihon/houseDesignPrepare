#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_JSON = ROOT / "structured" / "expert_review" / "report.json"
HTML_CONSISTENCY_JSON = ROOT / "structured" / "expert_review" / "html_consistency.json"
ROOM_PROGRAM_JSON = ROOT / "structured" / "room_program.json"
METRICS_JSON = ROOT / "structured" / "architect_metrics" / "metrics.json"
OUTPUT_JSON = ROOT / "structured" / "expert_review" / "domain_checklist.json"
OUTPUT_MD = ROOT / "structured" / "expert_review" / "domain_checklist.md"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def item(category: str, title: str, owner: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "category": category,
        "title": title,
        "owner": owner,
        "status": "open",
        "evidence": evidence,
        "claim_limit": "discussion_only_not_compliance",
    }


def build_domain_checklist(
    report: dict[str, Any],
    html_consistency: dict[str, Any],
    room_program: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "domain-checklist-v1",
        "generated_at": now_iso(),
        "report_hash": str(report.get("report_hash", "")),
        "items": [
            item("A", "A 2F 高雄厝陽台方向確認", "owner_architect", ["area=9.35m2", "share=16.3%", "visual_grid=bottom-right"]),
            item("A", "A 棟低成本冷氣擴散策略", "architect_mep", ["research low-cost whole-house air distribution before equipment purchase"]),
            item("A", "A RF 太陽能遮光棚架與颱風雨防護", "structural_mep", ["solar shade canopy", "rain exposure", "anchoring"]),
            item("A/C", "A/C 1F 長輩房與衛浴 150cm 迴轉圈", "architect_accessibility", ["elder room", "accessible bath", "furniture placed before confirmation"]),
            item("B", "B 棟神明廳上下疊圖與排煙防火", "architect_mep_fire", ["shrine wall", "beam overlay", "2F wet area", "exhaust", "make-up air", "fire material"]),
            item("C", "C 棟側院、洗衣、運動與 RF 設備確認", "architect_structural_mep", ["side-yard clear width", "2F laundry waterproofing", "3F exercise vibration", "RF anchoring"]),
        ],
        "source_counts": {
            "html_consistency_issues": len(html_consistency.get("issues", [])),
            "room_program_buildings": len(room_program.get("buildings", [])),
            "architect_action_groups": len(metrics.get("summary", {}).get("action_groups", {})),
        },
    }


def render_domain_checklist_md(checklist: dict[str, Any]) -> str:
    lines = [
        "# Domain Review Checklist",
        "",
        "本清單供屋主、建築師、結構技師與機電討論，不作為法規、結構、消防、採光、通風或無障礙合規證明。",
        "",
        f"- Report hash: `{checklist.get('report_hash', '')}`",
        "",
    ]
    for entry in checklist.get("items", []):
        evidence = "; ".join(entry.get("evidence", []))
        lines.append(f"- [{entry.get('status')}] **{entry.get('title')}** ({entry.get('owner')}) - {evidence}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate owner/architect domain review checklist.")
    parser.add_argument("--output-json", type=Path, default=OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=OUTPUT_MD)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    checklist = build_domain_checklist(
        report=load_json(REPORT_JSON),
        html_consistency=load_json(HTML_CONSISTENCY_JSON),
        room_program=load_json(ROOM_PROGRAM_JSON),
        metrics=load_json(METRICS_JSON),
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(checklist, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(render_domain_checklist_md(checklist), encoding="utf-8")
    print(f"Domain checklist JSON: {args.output_json}")
    print(f"Domain checklist MD:   {args.output_md}")


if __name__ == "__main__":
    main()

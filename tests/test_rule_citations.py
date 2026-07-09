from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULE_DIR = ROOT / "scripts" / "rules"
PLACEHOLDER_URLS = {
    "https://example.com/fengshui-guideline",
    "https://example.com/interior-guideline",
    "https://law.moj.gov.tw/",
}


def _rules() -> list[dict]:
    rules: list[dict] = []
    for path in sorted(RULE_DIR.glob("*.yaml")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for rule in payload.get("rules", []):
            rules.append({**rule, "_file": path.name})
    return rules


def test_rule_citations_do_not_use_placeholder_or_homepage_urls() -> None:
    invalid = [
        f"{rule['_file']}:{rule.get('rule_id')}={rule.get('source_url')}"
        for rule in _rules()
        if rule.get("source_url") in PLACEHOLDER_URLS
    ]

    assert invalid == []


def test_regulatory_accessibility_rules_use_official_nlma_source() -> None:
    rules = {
        rule["rule_id"]: rule
        for rule in _rules()
        if rule.get("rule_id") in {"ACC-TW-001", "ACC-TW-002"}
    }

    assert set(rules) == {"ACC-TW-001", "ACC-TW-002"}
    assert all(
        rule["source_url"].startswith(
            "https://www.nlma.gov.tw/ch/legislation/regsearch/927"
        )
        for rule in rules.values()
    )


def test_project_heuristics_cite_repository_governance_document() -> None:
    heuristic_rules = [
        rule
        for rule in _rules()
        if rule["_file"] in {"interior_design.yaml", "fengshui.yaml"}
    ]

    assert heuristic_rules
    assert all(
        "github.com/honyihon/houseDesignPrepare/blob/main/Docs/"
        in rule["source_url"]
        for rule in heuristic_rules
    )

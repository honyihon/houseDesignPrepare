from __future__ import annotations

from copy import deepcopy

from house_design.contracts import ROOT, read_json, write_json
from house_design.sites import build_site_comparison, site_comparison_html, site_comparison_markdown


def fact(value):
    return {"status": "verified", "value": value, "source": {
        "reference": "TEST ONLY document", "reviewer": "fixture reviewer", "checked_at": "2026-10-16",
    }}


def comparison(tmp_path, candidate, criterion_id, threshold):
    project = read_json(ROOT / "inputs/project.json")
    project["site_search"]["candidate_sites"] = [candidate]
    criteria = read_json(ROOT / "inputs/site-criteria.json")
    line = next(c for c in criteria["criteria"] if c["id"] == criterion_id)
    line.update(status="set")
    line["threshold"]["value"] = threshold
    criteria["criteria"] = [line]
    project_path, criteria_path = tmp_path / "project.json", tmp_path / "criteria.json"
    write_json(project_path, project)
    write_json(criteria_path, criteria)
    return build_site_comparison(project_path=project_path, criteria_path=criteria_path)


def test_eliminated_candidate_retains_each_unknown_parcel_in_actions_and_rendered_report(tmp_path):
    candidate = read_json(ROOT / "inputs/site-candidate.template.json")
    candidate["parcels"][0]["frontage_mm"] = fact(5000)
    report = comparison(tmp_path, candidate, "SC-FRONTAGE-MIN", 5500)
    row = report["candidates"][0]
    expected = {f"parcels.{p['parcel_id']}.frontage_mm" for p in candidate["parcels"][1:]}
    assert row["verdict"] == "eliminated"
    assert {m["field"] for m in row["missing_evidence"]} == expected
    assert report["summary"]["open_evidence_items"] == 2
    actions = [a for a in report["next_actions"] if a["kind"] == "evidence"]
    assert {a["field"] for a in actions} == expected
    assert len(actions) == 2
    for field in expected:
        assert field in site_comparison_html(report) and field in site_comparison_markdown(report)


def test_eliminated_system_does_not_hide_other_system_sources_or_duplicate_fields(tmp_path):
    candidate = read_json(ROOT / "inputs/site-candidate.template.json")
    candidate["cross_parcel_utilities"]["water"]["connectivity"] = fact("no")
    report = comparison(tmp_path, candidate, "SC-CROSS-PARCEL-UTILITY", "yes")
    row = report["candidates"][0]
    assert row["verdict"] == "eliminated"
    assert len(row["missing_evidence"]) == 11
    assert len({m["field"] for m in row["missing_evidence"]}) == 11
    assert report["summary"]["open_evidence_items"] == 11
    assert len(report["next_actions"]) == 11
    assert "cross_parcel_utilities.telecom.route_rights" in {m["field"] for m in row["missing_evidence"]}


def test_unknown_single_field_keeps_its_path_and_passes_have_no_evidence_tasks(tmp_path):
    candidate = read_json(ROOT / "inputs/site-candidate.template.json")
    unknown = comparison(tmp_path, candidate, "SC-ROAD-WIDTH", 6)
    assert unknown["candidates"][0]["missing_evidence"][0]["field"] == "official_facts.road"
    candidate["official_facts"]["road"] = fact(8)
    passed = comparison(tmp_path, candidate, "SC-ROAD-WIDTH", 6)
    assert passed["candidates"][0]["verdict"] == "keep"
    assert passed["summary"]["open_evidence_items"] == 0
    assert passed["next_actions"] == []


def test_legacy_missing_evidence_without_field_still_renders_without_empty_path(tmp_path):
    candidate = read_json(ROOT / "inputs/site-candidate.template.json")
    report = comparison(tmp_path, candidate, "SC-ROAD-WIDTH", 6)
    del report["candidates"][0]["missing_evidence"][0]["field"]
    assert "（<code></code>）" not in site_comparison_html(report)
    assert "（``）" not in site_comparison_markdown(report)


def test_missing_evidence_recurses_deduplicates_and_ignores_not_applicable():
    from house_design.sites import _missing_evidence

    metadata = {"criterion_id": "TEST", "label": "TEST", "kind_label": "必問",
                "evidence_required": "document", "responsible_role": "reviewer", "field": "systems"}
    pending = {"state": "unknown", "reason": "missing B", "field": "systems.B"}
    cells = [{**metadata, "state": "eliminated", "components": [
        {"state": "eliminated", "field": "systems.A", "reason": "known failure"},
        {"state": "unknown", "field": "systems", "components": [pending, deepcopy(pending)]},
        {"state": "pass", "field": "systems.C", "reason": "complete"},
        {"state": "not_applicable", "field": "systems.D", "components": [
            {"state": "unknown", "field": "systems.D.child", "reason": "irrelevant"}]},
    ]}]
    missing = _missing_evidence(cells)
    assert len(missing) == 1
    assert missing[0]["field"] == "systems.B" and missing[0]["reason"] == "missing B"

"""Derived planning map tests; never starts browser, scene or formal decision workflow."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from house_design.contracts import ContractError, stable_hash
from house_design.project_next_steps import (
    CONTROLS,
    INDEX,
    OUT,
    REGISTER,
    REQUIREMENTS,
    build,
    keyed,
    validate_tasks,
)
from scripts.export_project_next_steps import index_html, render

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def sources():
    return (keyed(copy.deepcopy(read(INDEX)["work_items"]), "tasks"),
        keyed(read(REQUIREMENTS)["requirements"], "requirements"), keyed(read(REGISTER)["items"], "register"))


def test_fourteen_navigation_rows_do_not_promote_formal_statuses(report):
    assert len(report["rows"]) == report["summary"]["navigation_tasks"] == 14
    assert report["summary"]["formal_requirement_count"] == 66
    assert report["summary"]["formal_register_count"] == 105
    assert report["summary"]["requirement_statuses"] == {"candidate": 66}
    assert report["summary"]["register_statuses"] == {"unknown": 105}
    assert report["actual_conditions_received_here"] == 0
    assert not report["design_or_primary_3d_changed"] and not report["formal_requirements_or_register_written"]
    assert all(r["decision_result"] is None and not r["design_adopted"] for r in report["rows"])
    assert report["professional_approval"] == "unknown" and report["browser_qa"] == "not-run"


def test_original_requirements_and_register_are_only_referenced_not_written(report):
    names = [INDEX, REQUIREMENTS, REGISTER, CONTROLS, "structured/candidates/kaohsiung-house-options-3d.html"]
    before = {n: (ROOT/n).read_bytes() for n in names}
    assert build(ROOT)["report_hash"] == report["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in names}
    assert report["protected_controls_unchanged"] == 149


def test_focus_map_explicitly_retains_every_not_focused_requirement_and_scenario(report):
    remainder = report["not_represented_in_this_focus_map"]
    used_r = {v["id"] for r in report["rows"] for v in r["formal_requirements"]}
    used_p = {v["id"] for r in report["rows"] for v in r["formal_register_items"]}
    assert used_r | set(remainder["requirement_ids"]) == {v["id"] for v in read(REQUIREMENTS)["requirements"]}
    assert used_p | set(remainder["register_ids"]) == {v["id"] for v in read(REGISTER)["items"]}
    assert not used_r.intersection(remainder["requirement_ids"])
    assert not used_p.intersection(remainder["register_ids"])
    assert remainder["requirement_ids"] and remainder["register_ids"]


def test_a_b_c_tradeoffs_and_nonadoption_are_not_blended(report):
    rows = {r["id"]: r for r in report["rows"]}
    assert "12.13" in rows["A-SUITE-001"]["recommendation"]
    assert "1200" in rows["A-CARE-001"]["recommendation"]
    assert "後門" in rows["B-CARRY-001"]["recommendation"] and "前門" in rows["B-CARRY-001"]["recommendation"]
    assert "5／套衛6" in rows["B-WET-001"]["recommendation"]
    assert "不借各版" in rows["C-CARE-001"]["recommendation"]
    assert "不先刪" in rows["C-HVAC-001"]["recommendation"]
    assert rows["C-CARE-001"]["depends_on"] == ["C-PRODUCT-001", "MEP-SITE-001"]
    assert all(r["prepare_now"] and r["when_data_arrives"] for r in report["rows"])


@pytest.mark.parametrize("bad", [None, [{"id": "x"}, {"id": "x"}], [{"id": ""}], [{}]])
def test_missing_or_duplicate_record_ids_are_rejected(bad):
    with pytest.raises(ContractError):
        keyed(bad, "example")


@pytest.mark.parametrize("field,value", [("register_ids", ["UNKNOWN"]), ("requirement_ids", ["UNKNOWN"]),
    ("depends_on", ["UNKNOWN"]), ("buildings", ["D"]), ("prepare_now", []), ("when_data_arrives", ["same", "same"]),
    ("decision_if_needed", True), ("recommendation", "")])
def test_invalid_reference_building_or_text_fields_rejected(field, value):
    tasks, req, reg = sources()
    tasks["C-CARE-001"]["followup"][field] = value
    with pytest.raises(ContractError):
        validate_tasks(tasks, req, reg)


def test_cross_building_references_and_dependency_cycles_are_rejected():
    tasks, req, reg = sources()
    tasks["A-CARE-001"]["followup"]["requirement_ids"] = ["C.floor-1.elder"]
    with pytest.raises(ContractError, match="another building"):
        validate_tasks(tasks, req, reg)
    tasks, req, reg = sources()
    tasks["MEP-SITE-001"]["followup"]["depends_on"] = ["A-CARE-001"]
    with pytest.raises(ContractError, match="cycle"):
        validate_tasks(tasks, req, reg)


def test_nav_work_mode_cannot_be_changed_into_auto_design_adoption(monkeypatch):
    import house_design.project_next_steps as module
    original = module.read_public_json
    changed = read(INDEX)
    changed["work_mode"] = "automatically-adopt-best"
    monkeypatch.setattr(module, "read_public_json", lambda root, p: changed if p == INDEX else original(root, p))
    with pytest.raises(ContractError, match="preplanning-only"):
        build(ROOT)


def test_private_and_missing_references_are_not_silently_loaded(monkeypatch):
    import house_design.project_next_steps as module
    original = module.read_public_json
    changed = read(INDEX)
    changed["work_items"][0]["followup"]["source_documents"] = ["inputs/private/no.json"]
    monkeypatch.setattr(module, "read_public_json", lambda root, p: changed if p == INDEX else original(root, p))
    with pytest.raises(ValueError):
        build(ROOT)


def test_stale_historical_references_stay_visible_and_do_not_fake_qa(report):
    row = next(r for r in report["rows"] if r["id"] == "A-SUITE-001")
    old = next(s for s in row["sources"] if s["path"] == "Docs/current-design-basis-v1.md")
    assert old["indexed_package_scope"] == "history"
    assert old["indexed_source_state"] == "source-changed-rebuild-required"
    assert all(s["professional_approval"] == "unknown" for s in report["rows"])
    assert "歷史來源已改，只作比較" in index_html(report)


def test_report_hash_and_all_file_bindings_are_current(report):
    assert stable_hash({k: v for k, v in report.items() if k != "report_hash"}) == report["report_hash"]
    for name, digest in report["file_hashes"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest


def test_artifact_hashes_and_all_local_links_current_without_browser(report):
    files = render(report)
    assert len(files) == 5
    manifest = json.loads(files["artifact-manifest.json"])
    assert not manifest["adopted"] and manifest["report_hash"] == report["report_hash"]
    for name, digest in manifest["artifacts"].items():
        assert hashlib.sha256(files[name].encode()).hexdigest() == digest
        assert (ROOT/OUT/name).read_bytes() == files[name].encode()
    for href in re.findall(r'href="([^"]+)"', files["index.html"]):
        assert (ROOT/OUT/href).is_file()
    assert "<script" not in files["index.html"]
    assert "未採用" in files["index.html"]


def test_rendered_source_and_task_text_are_escaped(report):
    altered = copy.deepcopy(report)
    altered["rows"][0]["title"] = '<img src=x onerror="alert(1)">'
    text = index_html(altered)
    assert '<img src=x onerror="alert(1)">' not in text
    assert "&lt;img" in text

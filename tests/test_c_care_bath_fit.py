"""Tiny read-only budget tests; never run an exporter for a parent or a scene."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import export_c_care_bath_fit as export
import pytest
from bs4 import BeautifulSoup
from historical_support import (
    assert_historical_sources,
    historical_state,
    historical_study,
    recorded_source_precondition,
)

from house_design import c_care_bath_fit as fit
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash


@pytest.fixture(scope="module")
def study():
    return historical_study("c-care-bath-fit")


def result(study, case, measure):
    return next(r for c in study["cases"] if c["id"] == case for r in c["results"] if r["id"] == measure)


def test_scope_unknowns_and_no_geometry_or_target_changes(study):
    assert study["status"] == fit.STATUS and study["adopted"] is False
    assert study["geometry_changed"] is study["construction_release"] is False
    assert study["rendered_qa"] == "not-run"
    assert set(study["professional_status"].values()) == {"unknown"}
    parent = read_json(ROOT / fit.BASE_REPORT)
    state = parent["options"][1]["states"][0]
    assert study["base_plan_hash"] == stable_hash(state["plans"])
    assert study["base_review_hash"] == stable_hash(state["review"])
    assert study["retained_limits"] == parent["limits"]
    assert study["bath_nominal_mm"] == [2400, 3000] and study["assumed_finished_mm"] == [2170, 2770]
    assert read_json(ROOT / "inputs/c-care-bath.json")["fixtures"]["vanity"]["rect_mm"][2:] == [600, 450]
    assert read_json(ROOT / "inputs/requirements.json")["requirements"]


def test_margins_derived_from_actual_shared_coordinates_include_new_zero_spares(study):
    assert {r["id"]: r["nominal_mm"] for r in study["measurements"]} == {
        "entry-vanity": 10, "basin-arrival": 0, "transfer-vanity": 15, "board-seat": 8.5,
        "door-parking": 0, "door-clear": 70, "door-body-jamb": 35}
    for r in study["measurements"]:
        assert result(study, "nominal", r["id"])["remaining_mm"] == r["nominal_mm"]
    assert result(study, "nominal", "door-parking")["status"] == "zero-spare"


def test_independent_stress_cases_and_combined_do_not_double_deduct_115mm(study):
    assert [c["id"] for c in study["cases"]] == list(fit.CASE_IDS)
    assert result(study, "finish-5", "entry-vanity")["remaining_mm"] == 5
    assert result(study, "finish-5", "door-clear")["remaining_mm"] == 60
    assert result(study, "finish-10", "board-seat")["remaining_mm"] == -1.5
    assert result(study, "product-10", "transfer-vanity")["remaining_mm"] == 5
    assert result(study, "position-5", "door-parking")["remaining_mm"] == -5
    assert result(study, "stop-20", "door-parking")["remaining_mm"] == -20
    assert result(study, "stop-20", "entry-vanity")["remaining_mm"] == 10
    assert result(study, "combined", "door-parking")["remaining_mm"] == -45
    assert result(study, "combined", "door-clear")["remaining_mm"] == 30
    assert result(study, "combined", "door-body-jamb")["remaining_mm"] == 10
    assert result(study, "combined", "entry-vanity")["remaining_mm"] == -15
    assert result(study, "combined", "board-seat")["remaining_mm"] == -16.5
    assert result(study, "finish-10", "entry-vanity")["status"] == "zero-spare"


def test_optional_buffer_is_only_a_discussion_gap_not_a_replan_or_rule(study):
    assert {r["id"]: r["extra_nominal_gap_to_keep_optional_buffer_mm"] for r in study["recommendations"]} == {
        "entry-vanity": 45, "basin-arrival": 55, "transfer-vanity": 40, "board-seat": 46.5, "door-parking": 75}
    assert all(r["adopted"] is False and r["optional_buffer_mm"] == 30 for r in study["recommendations"])


def test_twelve_unselected_products_include_mounts_controls_clearance_and_emergency_access(study):
    products = {p["id"]: p for p in study["products"]}
    assert len(products) == 12 and "bathroom-door" in products
    for row in products.values():
        assert row["status"] == "unknown-no-selected-product" and row["professional_acceptance"] == "unknown"
        assert all(row[k] is None for k in ("manufacturer", "model", "selected_dimensions_mm", "dimensioned_drawing",
                                           "installation_detail", "checked_by", "checked_at", "evidence_hash"))
        assert len(row["nominal_envelope_mm"]) == 6 and row["required_check"]
    assert products["vanity"]["nominal_envelope_mm"][2:4] == [600, 450]
    assert "鉸座" in products["fold-seat"]["required_check"]
    assert "外解鎖" in products["bathroom-door"]["required_check"]
    assert "底座" in products["toilet-arm"]["required_check"]


@pytest.mark.parametrize("value", [-1, True, None, float("nan"), float("inf"), 101, "5"])
def test_invalid_or_optimistic_tolerances_rejected(value):
    cfg = read_json(ROOT / fit.SOURCE)
    cfg["cases"][-1]["extra_finish_mm"] = value
    with pytest.raises(ContractError):
        fit.validate_config(cfg)


@pytest.mark.parametrize("field,value", [("required_door_clear_mm", 800), ("assumed_inset_each_face_mm", 80),
                                         ("base_state", "shower"), ("status", "adopted"),
                                         ("base_report", "../outside.json")])
def test_cannot_change_base_or_reduce_original_targets(field, value):
    cfg = read_json(ROOT / fit.SOURCE)
    cfg[field] = value
    with pytest.raises(ContractError):
        fit.validate_config(cfg)


def test_nominal_zero_and_unknown_approval_required():
    cfg = read_json(ROOT / fit.SOURCE)
    cfg["cases"][0]["extra_finish_mm"] = 1
    with pytest.raises(ContractError):
        fit.validate_config(cfg)
    cfg = read_json(ROOT / fit.SOURCE)
    cfg["professional_status"]["finished_wall_and_door_product"] = "verified"
    with pytest.raises(ContractError):
        fit.validate_config(cfg)


def test_stale_parent_source_and_forged_report_rejected(monkeypatch):
    original = fit.sha256_file
    monkeypatch.setattr(fit, "sha256_file", lambda p: "0"*64 if p.name == "c-care-bath.json" else original(p))
    with pytest.raises(ContractError, match="Stale frozen"):
        fit.build_study()
    monkeypatch.setattr(fit, "sha256_file", original)
    recorded_source_precondition(monkeypatch, fit, "c-care-bath")
    original_read = fit.read_json

    def forged(path):
        data = original_read(path)
        if path == ROOT / fit.BASE_REPORT:
            data["options"][1]["states"][0]["plans"]["floors"][0]["rooms"][-1]["geometry"]["w_mm"] = 1
        return data

    monkeypatch.setattr(fit, "read_json", forged)
    with pytest.raises(ContractError, match="altered frozen"):
        fit.build_study()


@pytest.mark.parametrize("name", ["../escape", "/tmp/outside", "inputs/../../escape"])
def test_source_path_cannot_escape_project(name):
    with pytest.raises(ContractError, match="Unsafe"):
        fit._source(ROOT, name)


def test_budget_is_monotone_and_never_mutates_parent(study):
    parent, state = historical_state("c-care-bath", "c-bath-refined", "transfer")
    before = stable_hash(state)
    cfg = read_json(ROOT / fit.SOURCE)
    rows = fit.measures(state, cfg)
    case = copy.deepcopy(cfg["cases"][-1])
    base = fit.sensitivity(rows, case)
    for key in fit.FIELDS:
        increased = {**case, key: case[key]+1}
        after = fit.sensitivity(rows, increased)
        assert all(a["remaining_mm"] <= b["remaining_mm"] for a, b in zip(after["results"], base["results"], strict=True))
    assert stable_hash(state) == before
    assert parent["report_hash"] == study["base_report_hash"]


def test_static_page_uses_exact_current_numbers_warning_and_same_source_links(study):
    text = export.render_index(study)
    soup = BeautifulSoup(text, "html.parser")
    assert soup.title.string == "C套衛｜完成面、公差與選品檢核"
    assert soup.select_one("#fit-adoption-warning").get_text() == fit.WARNING
    assert not soup.find("script") and not soup.find("iframe")
    assert len(soup.select("table.matrix tbody tr")) == 7
    for case, tr in zip(study["cases"], soup.select("table.matrix tbody tr"), strict=True):
        assert tr.th.get_text() == case["label"]
        for row in case["results"]:
            cell = tr.select_one(f'[data-margin="{row["id"]}"]')
            assert cell.get_text() == f'{row["remaining_mm"]:g}mm' and row["status"] in cell["class"]
    assert len(soup.select("[data-product]")) == 12
    assert "不是隔間移動量" in soup.get_text() and "不是自動重排" in soup.get_text()
    assert soup.select_one("table.matrix").parent.get("tabindex") == "0"
    for a in soup.select("a[href]"):
        target = unquote(urlsplit(a["href"])[2])
        if target.startswith("c-care-bath-fit/"):
            continue
        assert (ROOT / "structured/candidates" / target).is_file()
    assert (ROOT / "structured/candidates" / soup.object["data"]).is_file()


def test_new_outputs_are_source_bound_and_parent_hashes_unchanged(study, tmp_path):
    protected = {**{p: sha256_file(ROOT / p) for p in study["source_hashes"]}, fit.BASE_REPORT: sha256_file(ROOT / fit.BASE_REPORT),
                 fit.BASE_VIEWER: sha256_file(ROOT / fit.BASE_VIEWER)}
    export.write_study(study, tmp_path)
    assert json.loads((tmp_path / fit.OUT / "review.json").read_text())["report_hash"] == study["report_hash"]
    assert (tmp_path / export.INDEX).read_text() == export.render_index(study)
    checklist = json.loads((tmp_path / fit.OUT / "product-checklist.json").read_text())
    assert checklist["products"] == study["products"]
    assert all(sha256_file(ROOT / p) == digest for p, digest in protected.items())


def test_generated_artifacts_match_current_sources_numbers_and_product_unknowns(study):
    published = read_json(ROOT / fit.OUT / "review.json")
    assert published["report_hash"] == study["report_hash"]
    assert {k: v for k, v in published.items() if k != "generated_at"} == {
        k: v for k, v in study.items() if k != "generated_at"}
    assert (ROOT / export.INDEX).read_text(encoding="utf-8") == export.render_index(study)
    assert read_json(ROOT / fit.OUT / "product-checklist.json")["products"] == study["products"]
    assert_historical_sources("c-care-bath-fit", study)


def test_standalone_script_loads_local_package_without_caller_path_or_installs(tmp_path):
    run = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/export_c_care_bath_fit.py"), "--check"],
                         cwd=tmp_path, capture_output=True, text=True, timeout=5, check=False)
    assert run.returncode != 0
    assert "Stale frozen bath source" in run.stderr
    assert "ModuleNotFoundError" not in run.stderr
    assert not list(tmp_path.iterdir())

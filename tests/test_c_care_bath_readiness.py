"""Bounded readiness math/provenance, never scene, browser or clinical testing."""
from __future__ import annotations

import copy
import csv
import io

import export_c_care_bath_readiness as export
import pytest
from historical_support import (
    assert_historical_sources,
    historical_option,
    historical_study,
    recorded_source_precondition,
)

import house_design.c_care_bath_readiness as readiness
from house_design.c_care_bath_readiness import (
    BASE_REPORT,
    BASE_VIEWER,
    OUT,
    PRODUCT_FIELDS,
    PRODUCT_SOURCE,
    SOURCE,
    frozen_layout,
    product_responses,
    validate_config,
)
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash


@pytest.fixture(scope="module")
def study():
    return historical_study("c-care-bath-readiness")


def test_no_new_geometry_or_clinical_product_approval(study):
    assert study["geometry_changed"] is False and study["new_viewer_generated"] is False
    assert study["adopted"] is False and study["construction_release"] is False
    assert set(study["professional_status"].values()) == {"unknown"}
    assert study["seated_mockup_acceptance"] == "unknown-no-person-chair-or-trial-record"
    assert [p["id"] for p in study["product_responses"]] == list(PRODUCT_FIELDS)
    assert sum(len(p["facts_mm"]) for p in study["product_responses"]) == 16
    for product in study["product_responses"]:
        assert set(product["facts_mm"].values()) == {None}
        assert product["selected"] is False and product["product_or_care_approval"] == "unknown"
        assert product["knee_clearance_credit_mm"] == 0 and product["status"] == "unknown"
        assert all(p["evidence_backed_value_mm"] is None and p["status"] == "unknown" for p in product["scalar_checks"])


def test_frozen_layout_matches_current_html_model_and_golden_plan(study):
    parent, option = historical_option("c-care-bath-layout", "side-basin")
    assert study["base_report_hash"] == parent["report_hash"]
    state = next(s for s in option["states"] if s["id"] == "open")
    assert study["base_plan_hash"] == stable_hash(state["plans"]) == read_json(ROOT / SOURCE)["base_plan_hash"]
    assert study["base_plan_hash"] == "59aa1ccee2455b9d3ab0f7c0360d2f3ec2bea992576a91457884c7b71ab57640"
    assert_historical_sources("c-care-bath-readiness", study)
    assert study["report_hash"] == stable_hash({k: v for k, v in study.items() if k not in {"generated_at", "report_hash"}})


def test_offset_study_exposes_217_5_zero_spare_and_247_5_optional_not_care_acceptance(study):
    a = study["arrival"]
    assert a["current_offset_mm"] == 250
    assert a["minimum_offset_zero_spare_mm"] == 217.5
    assert a["minimum_offset_for_optional_margin_mm"] == 247.5
    assert [c["offset_mm"] for c in a["cases"]] == [0, 150, 200, 217.5, 230, 247.5, 250]
    for c in a["cases"]:
        assert bool(c["route"]["coordinate_failures"]) == (c["offset_mm"] < 217.5)
        assert c["route"]["body_mm"] == [900, 900]
        assert c["seated_reach_acceptance"] == "unknown"
        assert c["raised_arm_directional_spare_mm"] == c["offset_mm"]-217.5
        assert c["front_finish_spare_mm"] == c["offset_mm"]-150
    assert "固定目前x=4665mm" in a["scope"] and "不是全室" in a["scope"]


def test_centering_by_only_shifting_basin_and_door_has_empty_continuous_interval(study):
    s = study["basin_and_door_rear_shift"]
    assert s["continuous_shift_bounds_mm"] == {"minimum_for_current_centered_body": 217.5,
        "maximum_for_nonnegative_stop_parking": 200, "shortfall_mm": 17.5, "nonnegative_budget_interval": None}
    for c in s["cases"]:
        assert not c["named_station_and_parking_budgets_clear"] and not c["adopted"]
        assert c["rear_spare_after_existing_stop_mm"] == 200-c["rear_shift_mm"]
        assert c["hypothetical_vanity_rect_mm"][2:] == [450, 600]
        assert c["hypothetical_door_center_y_mm"] == 15175+c["rear_shift_mm"]
        assert not c["door_sweep_fixed_conflicts"]
        assert bool(c["centered_arrival_coordinate_failures"]) == (c["rear_shift_mm"] < 217.5)
        assert c["full_route_paired_aperture_and_care"] == "not-evaluated-no-layout-generated"


def test_board_numerical_trials_keep_real_size_and_closed_door_negative_controls(study):
    b = study["board_trials"]
    assert not b["geometry_changed"] and b["balanced_center_x_mm"] == 4831.25
    assert b["center_interval_for_optional_margin_mm"] == [4824, 4838.5]
    assert [(c["center_x_mm"], c["left_door_pack_spare_mm"], c["right_rail_spare_mm"]) for c in b["cases"]] == [(4850, 56, 18.5), (4830, 36, 38.5), (4831.25, 37.25, 37.25)]
    for case in b["cases"]:
        assert case["rotation_square_mm"][1:] == [14671, 1898, 1898] and case["adopted"] is False
        for state in case["states"]:
            route = state["translation"]
            assert route["body_mm"] == [1800, 600]
            assert route["points_mm"] == [[2650, 15115], [case["center_x_mm"], 15115], [case["center_x_mm"], 15620]]
            assert bool(route["coordinate_failures"]) == (state["state"] != "open")
            assert not state["rotation_coordinate_failures"]
            assert all("hits-bathroom" in f or "hits-bath-door-pull" in f for f in route["coordinate_failures"])


def test_six_product_boundaries_distinguish_original_target_optional_margin_and_whole_product(study):
    b = {c["field"]: c for c in study["product_budgets"]}
    assert len(b) == 6
    assert b["full_open_clear"]["zero_spare_boundary_mm"] == 900
    assert b["full_open_clear"]["max_for_optional_margin_mm"] is None
    assert (b["complete_pack"]["zero_spare_boundary_mm"], b["complete_pack"]["max_for_optional_margin_mm"]) == (165, 135)
    assert (b["rear_extent_from_nominal_aperture_end"]["current_discussion_value_mm"], b["rear_extent_from_nominal_aperture_end"]["zero_spare_boundary_mm"]) == (710, 910)
    assert (b["front_projection_from_nominal_aperture_start"]["zero_spare_boundary_mm"], b["front_projection_from_nominal_aperture_start"]["max_for_optional_margin_mm"]) == (60, 30)
    assert (b["folded_projection_from_rear_finish"]["current_discussion_value_mm"], b["folded_projection_from_rear_finish"]["max_for_optional_margin_mm"]) == (57.5, 86)
    assert (b["complete_projection_from_right_finish"]["current_discussion_value_mm"], b["complete_projection_from_right_finish"]["max_for_optional_margin_mm"]) == (67.5, 56)
    assert all(c["approval"] == "unknown" for c in b.values())
    nominal = study["discussion_product_facts_mm"]
    assert nominal["basin"]["body_width"] == 600 and nominal["basin"]["body_depth"] == 450
    assert nominal["basin"]["top_height"] == 850 and nominal["basin"]["knee_clear_height"] is None
    assert nominal["fold-seat"]["open_width"] == 480 and nominal["fold-seat"]["open_depth"] == 450


def test_filled_dimensions_without_sources_remain_unknown(study):
    response = read_json(ROOT / PRODUCT_SOURCE)
    p = response["products"][0]
    p.update(manufacturer="Synthetic fixture only", model="not-a-real-product")
    p["facts_mm"] = {k: 100 for k in p["facts_mm"]}
    p["facts_mm"]["full_open_clear"] = 970
    result, sources = product_responses(ROOT, response, study["product_budgets"])
    assert result[0]["status"] == "unknown" and not sources
    assert result[0]["scalar_checks"][0]["provided_value_mm"] == 970
    assert all(r["evidence_backed_value_mm"] is None and r["status"] == "unknown" for r in result[0]["scalar_checks"])


def documented_response(tmp_path):
    response = read_json(ROOT / PRODUCT_SOURCE)
    p = response["products"][0]
    p.update(manufacturer="Unit-test fixture; not a supplier", model="synthetic-only")
    p["facts_mm"] = {"full_open_clear": 970, "complete_pack": 130,
        "rear_extent_from_nominal_aperture_end": 710, "front_projection_from_nominal_aperture_start": 30}
    document = tmp_path / "inputs/references/unit-fixture.txt"
    document.parent.mkdir(parents=True)
    document.write_text("Synthetic fixture for provenance tests, not evidence of a real product.", encoding="utf-8")
    p["evidence"] = [{"document": "inputs/references/unit-fixture.txt", "sha256": sha256_file(document),
        "revision": "unit-only-v1", "checked_by": "test-fixture", "checked_at": "2026-10-22"}]
    return response


@pytest.mark.parametrize("fault", ["missing-revision", "missing-checker", "bad-date", "wrong-hash", "bad-hash", "missing-file"])
def test_untraceable_or_tampered_product_evidence_never_receives_numeric_credit(study, tmp_path, fault):
    response = documented_response(tmp_path)
    evidence = response["products"][0]["evidence"][0]
    if fault == "missing-revision":
        evidence["revision"] = None
    elif fault == "missing-checker":
        evidence["checked_by"] = ""
    elif fault == "bad-date":
        evidence["checked_at"] = "not-a-date"
    elif fault == "wrong-hash":
        evidence["sha256"] = "0"*64
    elif fault == "bad-hash":
        evidence["sha256"] = "almost"
    else:
        evidence["document"] = "inputs/references/missing.txt"
    result, _ = product_responses(tmp_path, response, study["product_budgets"])
    assert result[0]["evidence_issues"] and result[0]["status"] == "unknown"
    assert all(r["evidence_backed_value_mm"] is None for r in result[0]["scalar_checks"])


@pytest.mark.parametrize("clear,pack,expected", [(970, 130, "inside-this-scalar-budget-not-approved"),
    (899, 180, "outside-this-scalar-budget"), (900, 165, "zero-spare-not-approved")])
def test_documented_scalar_is_not_complete_product_care_or_adoption(study, tmp_path, clear, pack, expected):
    response = documented_response(tmp_path)
    response["products"][0]["facts_mm"].update(full_open_clear=clear, complete_pack=pack)
    result, sources = product_responses(tmp_path, response, study["product_budgets"])
    door = result[0]
    assert not door["evidence_issues"] and sources == {"inputs/references/unit-fixture.txt"}
    assert door["status"] == "needs-complete-model-and-professional-review"
    assert [r["status"] for r in door["scalar_checks"][:2]] == [expected, expected]
    assert not door["selected"] and door["product_or_care_approval"] == "unknown" and door["knee_clearance_credit_mm"] == 0


@pytest.mark.parametrize("path", ["/etc/passwd", "../../outside.txt", ".git/config", "inputs/references/../../../outside.txt"])
def test_product_documents_cannot_escape_to_private_or_external_paths(study, tmp_path, path):
    response = documented_response(tmp_path)
    response["products"][0]["evidence"][0]["document"] = path
    with pytest.raises(ContractError):
        product_responses(tmp_path, response, study["product_budgets"])


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf"), "970"])
def test_invalid_product_dimensions_cannot_be_treated_as_measurements(study, value):
    response = read_json(ROOT / PRODUCT_SOURCE)
    response["products"][0]["facts_mm"]["full_open_clear"] = value
    with pytest.raises(ContractError):
        product_responses(ROOT, response, study["product_budgets"])


def test_product_input_cannot_sneak_in_adoption_or_claim_approval(study):
    response = read_json(ROOT / PRODUCT_SOURCE)
    response["products"][0]["selected"] = True
    with pytest.raises(ContractError):
        product_responses(ROOT, response, study["product_budgets"])


@pytest.mark.parametrize("key,value", [("body_mm", [800, 800]), ("required_clear_mm", 800),
    ("optional_discussion_margin_mm", 0), ("inset_each_face_mm", 80), ("base_plan_hash", "0"*64)])
def test_scope_contract_refuses_smaller_targets_or_wrong_frozen_basis(key, value):
    cfg = read_json(ROOT / SOURCE)
    cfg[key] = value
    with pytest.raises(ContractError):
        validate_config(cfg)


@pytest.mark.parametrize("fault", ["stale-source", "forged-hash", "adopted"])
def test_frozen_parent_refuses_stale_sources_changed_report_or_adoption(monkeypatch, fault):
    recorded_source_precondition(monkeypatch, readiness, "c-care-bath-layout")
    original = readiness.read_json
    def altered(path):
        data = original(path)
        if path == ROOT / BASE_REPORT:
            data = copy.deepcopy(data)
            if fault == "stale-source":
                data["source_hashes"]["inputs/c-care-bath-layout.json"] = "0"*64
            elif fault == "forged-hash":
                data["limits"].append("forged-content")
            else:
                data["adopted"] = True
        return data
    monkeypatch.setattr(readiness, "read_json", altered)
    expected = {"stale-source": "Stale frozen", "forged-hash": "hash mismatch", "adopted": "Missing frozen"}
    with pytest.raises(ContractError, match=expected[fault]):
        frozen_layout()


def test_summary_and_csv_keep_unfilled_measurements_separate_from_discussion_numbers(study):
    text = export.render_summary(study)
    assert (ROOT / OUT / "summary.md").read_text() == text
    for phrase in ("不改HTML／3D", "217.5mm", "247.5mm", "17.5mm", "18.5", "38.5", "小數不是施工放樣精度", "膝部通行信用仍0", "未採用／未知"):
        assert phrase in text
    csv_text = export.render_supplier_csv(study)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 16 and all(row["廠商實際尺寸mm（待填）"] == "" for row in rows)
    assert all(row["廠商"] == row["型號"] == row["SHA256"] == row["查核人"] == "" for row in rows)
    assert {row["核可狀態"] for row in rows} == {"未知／未採用"}
    assert (ROOT / OUT / "supplier-checklist.csv").read_bytes() == b"\xef\xbb\xbf"+csv_text.encode("utf-8")


def test_exporter_only_writes_four_new_files_and_never_regenerates_existing_drawings_or_inputs(study, tmp_path):
    protected = {**{p: sha256_file(ROOT / p) for p in study["source_hashes"]}, BASE_REPORT: sha256_file(ROOT / BASE_REPORT), BASE_VIEWER: sha256_file(ROOT / BASE_VIEWER)}
    result = export.write_study(study, tmp_path)
    assert result["geometry_changed"] is False and result["browser_required_for_this_pack"] is False
    assert {p.relative_to(tmp_path / OUT).as_posix() for p in tmp_path.rglob("*") if p.is_file()} == {"review.json", "summary.md", "product-checklist.json", "supplier-checklist.csv"}
    assert all(sha256_file(ROOT / p) == digest for p, digest in protected.items())
    assert read_json(tmp_path / OUT / "review.json")["report_hash"] == study["report_hash"]
    assert (tmp_path / OUT / "summary.md").read_text() == export.render_summary(study)

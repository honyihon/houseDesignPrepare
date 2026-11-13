"""Source-bound RF fit and intake contracts; no product, stair or rendered approval."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from shapely.geometry import Polygon

from house_design.b_roof_equipment import CONFIG, OUT, build, evaluate_conditions
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_roof_equipment import private_path, render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_parent_and_protected_designs_are_not_changed_or_adopted(report):
    before = {n: (ROOT/n).read_bytes() for n in report["config"]["pinned_sources"]}
    assert build(ROOT)["report_hash"] == report["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in before}
    assert report["protected_controls_unchanged"] == 149 and not report["adopted"]
    assert not report["primary_abc_or_3d_changed"] and not report["all_original_requirements_met"]
    assert report["professional_approval"] == "unknown" and report["rendered_qa"] == "not-run"
    assert report["condition_values_received"] == 0


def test_both_roof_reservations_avoid_known_projections_and_interference(report):
    assert len(report["options"]) == 2
    for o in report["options"]:
        assert all(not v for v in o["checks"].values())
        assert len(o["inspection_routes"]) == 6
        assert all(r["within_roof_surface"] and not r["obstacle_hits"] for r in o["inspection_routes"])
        assert all(r["actual_operating_or_machine_transport_access"] == "unknown" for r in o["inspection_routes"])
        assert not o["actual_products_installed_approved_or_all_systems_connected"] and not o["adopted"]


def test_original_ids_and_dimensions_remain_without_inventing_purchases(report):
    assert report["old_RF_units_over_new_guest_bed_sqm"] == .2652
    for o in report["options"]:
        cooling = {i["id"]: i for i in o["reservations"] if i["kind"] == "cooling"}
        assert set(cooling) == {"B-AC03", "B-AC04", "representative-slot-1", "representative-slot-2"}
        assert all(i["body_mm"][2:] == [900, 350] and i["rect_mm"][2:] == [900, 1350] for i in cooling.values())
        assert all(cooling[k]["new_purchase_count"] is None for k in ["representative-slot-1", "representative-slot-2"])
        assert o["checks"]["wet_or_cooling_over_listed_beds_sqm"] == 0


def test_24sqm_goal_is_not_replaced_by_smaller_outline_or_rear_sacred_activity(report):
    assert report["front_nominal_gross_upper_bound_sqm"] == 23.4
    assert report["front_gross_short_of_deck24_before_any_deductions_sqm"] == .6
    assert not report["daily_rear_platform_credited_or_sacred_rules_relaxed"]
    assert not report["original_3F_work_court_credited_in_RF_platform"]
    assert not report["actual_RF_stair_arrival_or_front_door_verified"]
    assert len(report["original_RF_requirements"]) == 5
    deck = next(r for r in report["original_RF_requirements"] if r["id"].endswith(".rf_deck"))
    assert deck["target_sqm"] == 24 and deck["min_sqm"] == 10 and deck["original_status"] == "candidate"
    for o in report["options"]:
        assert not o["activity_goal24_met"] and not o["original_deck24_goal_reduced_or_adopted"]
        assert o["rear_daily_drying_area_credited_sqm"] == 0 and o["daily_front_route"]["over_protected_sqm"] == 0
        assert o["RF_front_door_and_actual_stair_access"] == "pending"
        assert o["original_min10_function_or_legal_approval"].startswith("unknown")


def test_platform_metrics_keep_shared_walkways_separate_and_preserve_all_pieces(report):
    s1, s2 = report["options"]
    assert s2["front_open_outline_including_shared_walkways_sqm"]-s1["front_open_outline_including_shared_walkways_sqm"] == 2.5
    for o in report["options"]:
        area = sum(Polygon(p["outer"], p["holes"]).area/1e6 for p in o["front_activity_polygons_mm"])
        assert area == pytest.approx(o["front_activity_upper_bound_after_explicit_reservations_sqm"])
        assert 0 < area < o["front_open_outline_including_shared_walkways_sqm"] < 23.4


def test_tight_rear_option_fails_when_extra_service_space_is_needed(report):
    s1, s2 = report["options"]
    assert s1["tank_to_rear_soil_vent_plan_gap_mm"] == 270
    assert s2["tank_to_rear_soil_vent_plan_gap_mm"] == 0 and s2["tank_to_heat_pump_envelope_plan_gap_mm"] == 65
    enlarged = next(c for c in s2["sensitivity"] if c["extra_each_edge_mm"] == 100)
    pairs = {(p["a"], p["b"]) for p in enlarged["pair_overlaps"]}
    assert {("tank", "heat-pump"), ("tank", "rear-soil-vent")} <= pairs
    assert "heat-pump" in enlarged["outside_surface"] and "not-product-installation" in enlarged["scope"]


def test_stale_erv_locations_are_detected_and_equal_size_dry_candidates_remain_conditional(report):
    assert {i["id"] for i in report["indoor_fresh_air_interfaces"]} == {"B2-N", "B3-R"}
    for i in report["indoor_fresh_air_interfaces"]:
        assert i["old_overlap_current_bath_sqm"] == .25
        assert i["candidate_bath_or_protected_overlap_sqm"] == 0
        assert sorted(i["old_rect_mm"][2:]) == sorted(i["rotated_candidate_mm"][2:]) == [1000, 1600]
        assert i["actual_finished_z_mm"] is None and not i["purchase_count_selected"]
        assert i["filter_removal_and_maintenance_floor_access"].startswith("pending")
        assert i["full_current_KTV_and_sleeping_room_air_distribution"].startswith("pending")
    assert report["R1_reference"]["rf_opening_sqm"] == 2.639
    assert report["R1_reference"]["wet_3F_over_2F_master_sqm"] == 5.112


def test_unknown_conditions_are_pending_and_received_dimensions_do_not_adopt(report):
    assert len(report["condition_evaluations"]) == 18
    assert all(r["status"] == "pending" and r["required_envelope_mm"] is None for r in report["condition_evaluations"])
    template = copy.deepcopy(report["condition_template"])
    row = next(r for r in template["records"] if r["id"] == "tank")
    row.update(required_envelope_mm=[1600, 1900], reference="synthetic dimension test; not project data")
    _, checks = evaluate_conditions(report["config"], report["options"], template)
    tanks = {c["option"]: c for c in checks if c["id"] == "tank"}
    assert all(c["status"] == "needs-replan" for c in tanks.values())  # No automatic rotation to make S1 fit.
    row["required_envelope_mm"] = [1400, 1800]
    _, checks = evaluate_conditions(report["config"], report["options"], template)
    tanks = {c["option"]: c for c in checks if c["id"] == "tank"}
    assert tanks["S1-front-heat-pump"]["status"] == "numeric-fit"
    assert tanks["S2-rear-wet-pair"]["status"] == "needs-replan"
    assert all(c["professional_approval"] == "unknown" and not c["rotation_or_reposition_automatically_allowed"] for c in checks)


@pytest.mark.parametrize("defect", ["zero", "boolean", "nan", "source-missing", "wrong-revision", "duplicate", "missing"])
def test_invalid_condition_data_cannot_masquerade_as_measurements(report, defect):
    data = copy.deepcopy(report["condition_template"])
    row = data["records"][0]
    row.update(required_envelope_mm=[1400, 1800], reference="synthetic")
    if defect == "zero":
        row["required_envelope_mm"][0] = 0
    elif defect == "boolean":
        row["required_envelope_mm"][0] = True
    elif defect == "nan":
        row["required_envelope_mm"][0] = float("nan")
    elif defect == "source-missing":
        row["reference"] = ""
    elif defect == "wrong-revision":
        data["config_hash"] = "0"*64
    elif defect == "duplicate":
        data["records"].append(copy.deepcopy(row))
    else:
        data["records"].pop()
    with pytest.raises(ContractError):
        evaluate_conditions(report["config"], report["options"], data)


@pytest.mark.parametrize("defect", ["shrine", "skylight", "shrink-tank", "shrink-unit", "duplicate-slot", "fresh-in-bath", "parent-drift"])
def test_known_layout_regressions_stop_export(monkeypatch, defect):
    import house_design.b_roof_equipment as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    if defect == "shrine":
        cfg["options"][0]["heat_pump_mm"] = [2500, 6000, 2000, 1250]
    elif defect == "skylight":
        cfg["rear_air_zone_mm"] = [1100, 11470, 1400, 1800]
    elif defect == "shrink-tank":
        cfg["options"][0]["tank_mm"][2] = 1400
    elif defect == "shrink-unit":
        cfg["relocated_existing_units"][0]["rect_mm"][2] = 800
    elif defect == "duplicate-slot":
        cfg["front_slots"].append(copy.deepcopy(cfg["front_slots"][0]))
    elif defect == "fresh-in-bath":
        cfg["indoor_ERV_rotated_candidate_mm"] = [4000, 14615, 1600, 1000]
    else:
        cfg["pinned_sources"][cfg["parent_report"]] = "0"*64
    monkeypatch.setattr(module, "read_json", lambda p: cfg if p == ROOT/CONFIG else read(p))
    with pytest.raises(ContractError):
        build(ROOT)


@pytest.mark.parametrize("value", ["structured/roof-results", "inputs/private", "inputs/private/../public", "/tmp/results", "inputs\\private\\roof"])
def test_received_conditions_cannot_write_the_public_baseline(tmp_path, value):
    with pytest.raises(ContractError):
        private_path(tmp_path, value, new=True)


def test_private_results_never_overwrite_answers_or_follow_escaping_symlinks(tmp_path):
    private = tmp_path/"inputs/private"
    private.mkdir(parents=True)
    existing = private/"result-001"
    existing.mkdir()
    (existing/"answers.csv").write_text("keep")
    with pytest.raises(ContractError):
        private_path(tmp_path, "inputs/private/result-001", new=True)
    assert (existing/"answers.csv").read_text() == "keep"
    outside = tmp_path/"outside"
    outside.mkdir()
    (private/"link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ContractError):
        private_path(tmp_path, "inputs/private/link/new", new=True)


def test_static_exports_bind_current_sources_and_leave_response_fields_blank(report):
    files = render(report)
    assert len(files) == 11 and sum(n.endswith(".svg") for n in files) == 3
    assert all((ROOT/OUT/n).read_bytes() == value.encode() for n, value in files.items())
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in report["source_hashes"].items())
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n, h in manifest["artifacts"].items())
    for n, data in files.items():
        if n.endswith(".svg"):
            svg = ET.fromstring(data)
            assert int(svg.attrib["width"])*int(svg.attrib["height"]) <= 1_680_000
            assert all(0 <= float(t.attrib["y"]) < 1200 for t in svg.iter() if t.tag.endswith("text"))
    assert all((ROOT/OUT/ref).is_file() for ref in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]))
    assert "未採用" in files["index.html"] and "24" in files["index.html"] and "0.25" in files["index.html"]
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"])

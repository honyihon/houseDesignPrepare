"""Q3/RF engineering boundaries and conditional inputs without runtime or approval."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

from house_design.b_q3_engineering_gates import CONFIG, NUMERIC_FIELDS, OUT, build
from house_design.b_upper_replan import rect
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_q3_engineering_gates import private_path, render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_frozen_Q3_RF_and_original_controls_stay_unchanged(report):
    before = {n: (ROOT/n).read_bytes() for n in report["config"]["pinned_sources"]}
    assert report["report_hash"] == build(ROOT)["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in before}
    assert report["protected_controls_unchanged"] == 149
    assert not report["primary_abc_or_3d_changed"] and not report["new_room_door_or_equipment_geometry_generated"]
    assert not report["adopted"] and not report["all_original_requirements_met"]
    assert report["actual_site_values_received"] == report["numeric_condition_values_received"] == 0
    assert report["rendered_qa"] == "not-run" and report["professional_approval"] == "unknown"


def test_all_unknown_transport_records_remain_pending_not_zero_or_approved(report):
    records = report["condition_template"]["records"]
    assert len(records) == 8 and len({r["id"] for r in records}) == 8
    assert all(all(r[k] is None for k in NUMERIC_FIELDS) for r in records)
    assert {r["equipment"] for r in records} == {"tank", "heat-pump", "B-AC03", "B-AC04"}
    assert all(r["status"] == "pending" and r["width_margin_mm"] is None for r in report["condition_evaluations"])
    assert all(not r["full_route_turning_depth_height_stairs_load_religion_or_lifting_approved"] for r in report["condition_evaluations"])


def test_front_heat_pump_and_other_aperture_references_do_not_swap_900_and_770(report):
    for row in report["condition_template"]["records"]:
        front = row["equipment"] == "heat-pump" and "D1" in row["option"]
        assert row["inspection_door_reference_not_a_transport_route"] == ("front" if front else "side")
        assert row["door_budget_mm"] == (900 if front else 770)


def test_width_trials_account_for_both_hands_without_passing_whole_transport(report):
    trials = report["door_width_trials"]
    assert len(trials) == 30
    def case(door, width, reserve):
        return next(r for r in trials if (r["door"], r["declared_transport_width_mm"], r["handling_each_side_mm"]) == (door, width, reserve))
    assert case("side", 770, 0)["margin_mm"] == 0
    assert case("side", 770, 25)["margin_mm"] == -50
    assert case("side", 700, 50)["status"] == "reject-declared-width"
    assert case("side", 700, 25)["status"] == "width-only-compatible"
    assert case("front", 900, 0)["status"] == "width-only-compatible"
    assert case("front", 900, 25)["status"] == "reject-declared-width"
    assert all(not r["actual_product_or_full_route_approved"] for r in trials)


def test_received_width_and_reserve_can_only_resolve_a_single_numeric_aperture(report):
    document = copy.deepcopy(report["condition_template"])
    row = document["records"][0]
    row.update(width_mm=720, handling_each_side_mm=25, height_mm=10000, mass_kg=1000000, reference="synthetic transport example, not a product")
    new = build(ROOT, document)
    evaluated = new["condition_evaluations"][0]
    assert evaluated["width_margin_mm"] == 0 and evaluated["status"] == "width-only-compatible"
    assert not evaluated["actual_finished_aperture_verified"]
    assert not evaluated["minimum_transport_orientation_verified"]
    assert not evaluated["full_route_turning_depth_height_stairs_load_religion_or_lifting_approved"]
    assert new["numeric_condition_values_received"] == 4 and new["condition_document_hash"] == stable_hash(document)
    row["width_mm"] = 721
    assert build(ROOT, document)["condition_evaluations"][0]["status"] == "reject-declared-width"
    assert build(ROOT)["condition_evaluations"][0]["status"] == "pending"


@pytest.mark.parametrize("defect", ["old-revision", "old-parent", "missing-record", "duplicate", "wrong-door", "unknown-field", "bool", "nan", "overflow", "huge-int", "negative", "zero-body", "no-reference", "not-object"])
def test_bad_or_mixed_revision_conditions_are_rejected(report, defect):
    d = copy.deepcopy(report["condition_template"])
    row = d["records"][0]
    if defect == "old-revision":
        d["config_hash"] = "0"*64
    elif defect == "old-parent":
        d["parent_report_hash"] = "0"*64
    elif defect == "missing-record":
        d["records"].pop()
    elif defect == "duplicate":
        d["records"].append(copy.deepcopy(row))
    elif defect == "wrong-door":
        row["door_budget_mm"] = 900
    elif defect == "unknown-field":
        row["automatic_rotation"] = True
    elif defect == "bool":
        row.update(width_mm=True, reference="synthetic")
    elif defect == "nan":
        row.update(width_mm=float("nan"), reference="synthetic")
    elif defect == "overflow":
        row.update(width_mm=1e308, handling_each_side_mm=1e308, reference="synthetic")
    elif defect == "huge-int":
        row.update(width_mm=10**1000, reference="synthetic")
    elif defect == "negative":
        row.update(handling_each_side_mm=-1, reference="synthetic")
    elif defect == "zero-body":
        row.update(width_mm=0, reference="synthetic")
    elif defect == "no-reference":
        row["width_mm"] = 700
    else:
        d = []
    with pytest.raises(ContractError):
        build(ROOT, d)


def test_height_layers_are_not_double_counted_or_presented_as_legal_minima(report):
    cases = report["vertical_cases"]
    assert [r["remaining_vertical_budget_mm"] for r in cases] == [2400, 2300, 2100, 1850]
    assert {r["model_RF_plane_z_mm"]-r["model_3F_plane_z_mm"] for r in cases} == {3000}
    assert cases[1]["remaining_vertical_budget_mm"] == cases[0]["remaining_vertical_budget_mm"]-100
    assert cases[2]["lowest_structure_z_mm"] == cases[2]["slab_bottom_z_mm"]-300
    assert all(not r["legal_minimum_or_actual_material_selected"] and not r["whole_stair_or_room_height_approved"] for r in cases)


def test_RF_floor_and_equipment_downward_projections_use_same_Q3_revision(report):
    p = report["projection_interfaces"]
    parent = json.loads((ROOT/report["config"]["parent_report"]).read_text())
    f = parent["floor_requirements"]
    ground = unary_union([rect(f[k]) for k in ["landing_mm", "vestibule_mm", "side_threshold_mm"]]+[Polygon(f["front_threshold_polygon_mm"])])
    assert ground.equals(Polygon(p["RF_required_floor_polygon_mm"]))
    assert p["RF_floor_over_KTV_nominal_sqm"] == 1.772225
    assert p["RF_floor_over_KTV_inner_sqm"] == 1.1329
    heat = next(r for r in p["equipment"] if "D1" in r["option"] and r["id"] == "heat-pump")
    assert heat["over_KTV_nominal_sqm"] == 2.5 and heat["outline_scope"] == "whole reservation not product body"
    assert len(p["equipment"]) == 12
    assert all(r["load_noise_waterproofing_piping_or_religious_approval"] == "unknown" for r in p["equipment"])


def test_24sqm_optimistic_depth_extension_is_blocked_not_a_design_authorization(report):
    c = report["capacity_boundary"]
    assert c["original_target_sqm"] == 24 and c["fixed_front_upper_bound_before_equipment_sqm"] == 21.83945
    assert c["optimistic_shortfall_sqm"] == 2.16055
    assert c["hypothetical_full_width_depth_lower_bound_mm"] == 4274.445
    assert c["hypothetical_rounded_extra_depth_mm"] == 375
    assert c["extra_band_over_stair_enclosure_sqm"] == .856875
    assert c["extra_band_over_protected_sqm"] == 1.306875
    assert c["extra_band_not_already_blocked_sqm"] == 0
    assert not c["full_width_band_is_an_authorized_or_buildable_design"] and not c["all_global_replans_proven_impossible"]
    assert not c["RF24_target_reduced_or_met"] and not c["indoor_vestibule_rear_daily_area_or_3F_court_credited"]


def test_output_identity_bounds_offline_links_and_blank_engineering_replies(report):
    files = render(report)
    assert len(files) == 12 and sum(n.endswith(".svg") for n in files) == 3
    assert all((ROOT/OUT/n).read_bytes() == v.encode() for n, v in files.items())
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in report["source_hashes"].items())
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n, h in manifest["artifacts"].items())
    for name, value in files.items():
        if name.endswith(".svg"):
            svg = ET.fromstring(value)
            assert int(svg.attrib["width"])*int(svg.attrib["height"]) <= 1_680_000
            assert all(0 <= float(t.attrib["y"]) < 1200 for t in svg.iter() if t.tag.endswith("text"))
    assert all((ROOT/OUT/ref).is_file() for ref in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]))
    assert "未採用" in files["index.html"] and "不是搬運通過" in files["index.html"]
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"])


@pytest.mark.parametrize("path", ["/tmp/result", "structured/result", "inputs/private/../public", "inputs/private", "inputs\\private\\result"])
def test_received_conditions_and_new_results_must_stay_in_private_records(tmp_path, path):
    with pytest.raises(ContractError):
        private_path(tmp_path, path, new=True)


def test_condition_result_cannot_follow_external_symlink_or_overwrite(tmp_path):
    (tmp_path/"inputs/private").mkdir(parents=True)
    outside = tmp_path/"outside"
    outside.mkdir()
    (tmp_path/"inputs/private/escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ContractError):
        private_path(tmp_path, "inputs/private/escape/result", new=True)
    (tmp_path/"inputs/private/exists").mkdir()
    with pytest.raises(ContractError):
        private_path(tmp_path, "inputs/private/exists", new=True)


def test_private_cli_recalculates_only_new_output_and_rejects_second_write(tmp_path, monkeypatch, report):
    import scripts.export_b_q3_engineering_gates as cli
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "build", lambda _, document: build(ROOT, document))
    source = tmp_path/"inputs/private/conditions.json"
    source.parent.mkdir(parents=True)
    d = copy.deepcopy(report["condition_template"])
    d["records"][0].update(width_mm=800, handling_each_side_mm=25, reference="synthetic test")
    source.write_text(json.dumps(d))
    monkeypatch.setattr(sys, "argv", ["export", "--conditions", "inputs/private/conditions.json", "--output", "inputs/private/result-001"])
    assert cli.main() == 0
    result = tmp_path/"inputs/private/result-001/review.json"
    original = result.read_bytes()
    assert json.loads(original)["condition_evaluations"][0]["status"] == "reject-declared-width"
    assert cli.main() == 1 and result.read_bytes() == original
    assert source.read_text() == json.dumps(d)
    assert not (tmp_path/OUT).exists()


def test_parent_source_drift_stops_engineering_export(monkeypatch):
    import house_design.b_q3_engineering_gates as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    cfg["pinned_sources"][cfg["parent_report"]] = "0"*64
    monkeypatch.setattr(module, "read_json", lambda p: cfg if p == ROOT/CONFIG else read(p))
    with pytest.raises(ContractError):
        build(ROOT)

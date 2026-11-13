"""Second-response bounds, provenance and blank actual-data states; no AI or browser."""
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

from house_design.b_front_drop_claude_round2 import CONFIG, OUT, build, drop_lower_bound, drop_upper_bound
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_front_drop_claude_round2 import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_owner_requested_opus_response_is_exact_but_answering_model_not_guessed(report):
    p = report["provenance"]
    assert p["requested_model"] == "claude-opus-5-5" and p["model_reported"] is None
    assert hashlib.sha256((ROOT/p["response_file"]).read_bytes()).hexdigest() == p["response_sha256"]
    assert hashlib.sha256((ROOT/p["prompt_file"]).read_bytes()).hexdigest() == p["prompt_sha256"]
    assert p["exit_code"] == 0 and not p["full_design_consensus"]
    assert all(not p[k] for k in ["recorded_tools_enabled", "recorded_mcp_enabled", "recorded_hooks_enabled"])
    assert report["numeric_and_research_priority_agreement"] and not report["full_design_consensus"]


def test_both_unknown_bounds_remain_unknown_and_zero_is_only_an_explicit_example(report):
    assert drop_lower_bound(3704.9, 3221.521, 50, 50, None) is None
    assert drop_upper_bound(3461.6, None, 0) is None
    assert drop_upper_bound(3461.6, 2800, None) is None
    assert drop_lower_bound(3704.9, 3221.521, 50, 50, 0) == pytest.approx(583.379)
    assert drop_upper_bound(3461.6, 2800, 0) == pytest.approx(661.6)
    assert len(report["drop_bounds"]) == 12
    for row in report["drop_bounds"]:
        assert row["required_additional_reserve_M_mm"] is row["minimum_drop_with_actual_M_mm"] is None
        assert row["maximum_drop_with_actual_lower_requirements_mm"] is row["actual_interval_feasible"] is None


def test_thick_soffit_requires_more_than500_without_selecting600(report):
    rows = {(r["normal_waist_mm"],r["upper_fitting_growth_mm"]):r for r in report["drop_bounds"]}
    assert [rows[t,0]["minimum_drop_with_M0_only_mm"] for t in [150,200,250,300]] == pytest.approx([357.102,415.861,474.620,533.379])
    assert rows[300,50]["minimum_drop_with_M0_only_mm"] == pytest.approx(583.379)
    assert rows[250,25]["minimum_drop_with_M0_only_mm"] == pytest.approx(499.620)
    assert report["selected_drop_mm"] is None
    assert not any(r["adopted"] for r in report["drop_bounds"])


def test_endpoint_centre_and_hypothetical_rear_edge_are_not_whole_room_clearance(report):
    examples = report["drop_examples"]
    assert [r["lowest_endpoint_centre_budget_mm"] for r in examples] == [2961.6,2911.6,2861.6]
    assert [r["if_straight_pipe_to_rear_edge_budget_mm"] for r in examples] == [2957.6,2907.6,2857.6]
    assert all(r["actual_whole_envelope_minimum_clear_height_mm"] is None and not r["selected_drop"] for r in examples)


def test_planar_growth_is_independent_and_just_touching_platform_is_not_approved(report):
    rows = {r["id"]:r for r in report["body_growth_cases"]}
    assert rows["front25-no-shift"]["platform_overlap_sqm"] == .002
    assert rows["all25-no-shift"]["platform_overlap_sqm"] == .00225
    assert rows["front25-shift5"]["front_to_platform_rear_mm"] == 0
    assert rows["all25-shift5"]["platform_overlap_sqm"] == 0
    assert all(not r["upper_growth_coupled_to_planar_growth"] and not r["adopted"] for r in rows.values())
    assert rows["nominal"]["expanded_box_entirely_in_original_return_footprint"]
    assert not rows["all25-shift5"]["expanded_box_entirely_in_original_return_footprint"]


def test_shift_and_rear_growth_do_not_reuse_the_old_soffit_height(report):
    assert report["shift_margin_loss_per_mm"] == pytest.approx(.597283951)
    assert report["shift5_margin_loss_mm"] == pytest.approx(2.98642)
    rows = {r["id"]:r for r in report["body_growth_cases"]}
    assert rows["front25-shift5"]["t250_upper25_M0_minimum_drop_mm"] == pytest.approx(503.106)
    assert rows["all25-shift5"]["t250_upper25_M0_minimum_drop_mm"] == pytest.approx(518.539)
    assert rows["all25-shift5"]["t250_upper25_d500_margin_model_mm"] < 0


def test_upstream_missing_gap_is_not_hidden_by_local_installation_allowance(report):
    u = report["upstream_basin_original_shaft_centre"]
    assert u["pipe_package_top_mm"] == 3788.4 and u["remaining_upper_gap_mm"] == 11.6
    assert u["if_uniform50_required_margin_mm"] == -38.4
    assert not u["local50_is_proof_of_uniform50"] and not u["actual_entire_upstream_fit_known"]


def test_translated_cross_line_has_same_horizontal_length_but_no_door_or_cleanout_approval(report):
    a,b = report["cross_position_examples"]
    assert a["horizontal_cross_y_mm"] == 4500 and b["horizontal_cross_y_mm"] == 4700
    assert a["horizontal_header_mm"] == b["horizontal_header_mm"] == 4375
    assert a["endpoint_basin_top_d500_mm"] == b["endpoint_basin_top_d500_mm"] == 3200.9
    assert a["basin_top_before_d500_drop_mm"] == 3738 and b["basin_top_before_d500_drop_mm"] == 3734
    assert all(not r["selected"] and not r["door_fitting_and_cleanout_envelopes_verified"] for r in [a,b])
    assert report["selected_cross_y_mm"] is None


def test_downward_underpass_does_not_authorize_upward_stack_or_overlapping_four_real_pipes(report):
    assert report["downward_after_stair_underpass_only"] and not report["upward_at_G4_through_stair_permitted"]
    assert not report["vent_return_route_designed"] and not report["four_separate_pipes_can_overlap"]
    assert not report["actual_merged_pipe_fittings_and_hydraulics_known"]
    assert "前段濕區重排" in report["research_priority"][2] and "G5" in report["research_priority"][3]


def test_no_requirements_layouts_or_approval_promoted(report):
    assert report["protected_controls_unchanged"] == 149 and report["actual_site_or_product_data_received"] == 0
    assert report["original_rules_unchanged"] and report["palanquin_front_is_shrine_street_door"]
    assert not report["whole_palanquin_transport_rehearsed"] and not report["primary_abc_or_3d_changed"]
    assert not report["front_legal_connection_approved"] and not report["buried_sacred_crossing_exemption_authorized"]
    assert not report["RF24_Q3_acoustics_R1_waterproofing_resolved"]
    assert not report["adopted"] and report["professional_approval"] == "unknown" and report["rendered_qa"] == "not-run"


@pytest.mark.parametrize("defect",["parent-pin","assume-clearance","adopt","silent-drop","missing-claim","negative-growth","nonfinite-growth","wrong-model"])
def test_mutated_sources_assumptions_or_provenance_are_rejected(monkeypatch,defect):
    import house_design.b_front_drop_claude_round2 as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    prov = copy.deepcopy(read(ROOT/cfg["provenance"]))
    if defect == "parent-pin":
        cfg["pinned_sources"][cfg["parent_report"]] = "0"*64
    elif defect == "assume-clearance":
        cfg["actual_required_local_clear_height_mm"] = 2800
    elif defect == "adopt":
        cfg["adopted"] = True
    elif defect == "silent-drop":
        cfg["illustrative_drop_cases_mm"] = [600]
    elif defect == "missing-claim":
        cfg["claim_review"].pop()
    elif defect == "negative-growth":
        cfg["body_growth_cases"][0]["front_mm"] = -25
    elif defect == "nonfinite-growth":
        cfg["body_growth_cases"][0]["rear_mm"] = float("nan")
    else:
        prov["requested_model"] = "different-model"
    monkeypatch.setattr(module,"read_json",lambda p:cfg if p == ROOT/CONFIG else prov if p == ROOT/cfg["provenance"] else read(p))
    with pytest.raises(ContractError):
        build(ROOT)


def test_artifacts_blank_actual_replies_and_all_source_hashes_are_current(report):
    files = render(report)
    assert len(files) == 13 and sum(n.endswith(".svg") for n in files) == 3
    assert all((ROOT/OUT/n).read_bytes() == v.encode() for n,v in files.items())
    assert report["report_hash"] == stable_hash({k:v for k,v in report.items() if k != "report_hash"})
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n,h in report["source_hashes"].items())
    m = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n,h in m["artifacts"].items())
    for n,v in files.items():
        if n.endswith(".svg"):
            svg=ET.fromstring(v)
            assert int(svg.attrib["width"])*int(svg.attrib["height"]) <= 1_680_000
            assert all(0 <= float(t.attrib["y"]) < 1200 for t in svg.iter() if t.tag.endswith("text"))
    assert all((ROOT/OUT/ref).is_file() for ref in re.findall(r'(?:href|src)="([^"]+)"',files["index.html"]))
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["實際值及單位","專業回覆","屋主選擇","審查與施工圖發行"])

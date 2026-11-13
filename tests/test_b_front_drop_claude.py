"""Source-bound Claude audit and hypothetical G4/G4D/G5 budgets, no adoption."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from house_design.b_front_drop_claude import CONFIG, OUT, build
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_front_drop_claude import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_source_response_is_exact_and_not_promoted_to_consensus(report):
    p = report["provenance"]
    assert hashlib.sha256((ROOT/p["response_file"]).read_bytes()).hexdigest() == p["response_sha256"]
    assert hashlib.sha256((ROOT/p["prompt_file"]).read_bytes()).hexdigest() == p["prompt_sha256"]
    assert p["model_reported"] is None and p["exit_code"] == 0
    assert not p["consensus"] and not report["consensus"] and not report["adopted"]
    assert not p["recorded_tools_enabled"] and not p["recorded_mcp_enabled"] and not p["recorded_hooks_enabled"]
    assert report["second_round_status"] == "not-run-awaiting-owner-separate-terminal"


def test_frozen_parent_and149_original_controls_not_rewritten(report):
    before = {n: (ROOT/n).read_bytes() for n in report["config"]["pinned_sources"]}
    assert report["report_hash"] == build(ROOT)["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in before}
    assert report["protected_controls_unchanged"] == 149
    assert report["actual_site_or_product_data_received"] == 0
    assert not report["primary_abc_or_3d_changed"] and not report["all_original_requirements_met"]
    assert report["professional_approval"] == "unknown" and report["rendered_qa"] == "not-run"


def test_raw_numeric_agreements_keep_complete_branches_and_not_only_new_header(report):
    options = {o["id"]: o for o in report["options"]}
    assert options["G4"]["offset_length_mm"] == options["G4D"]["offset_length_mm"] == 4375
    assert options["G5"]["offset_length_mm"] == 3210
    assert [r["total_horizontal_length_mm"] for r in options["G4"]["fixture_rows"]] == [6165, 4955, 6920, 6750]
    assert [r["total_horizontal_length_mm"] for r in options["G5"]["fixture_rows"]] == [5000, 3790, 5755, 5585]
    assert [r["total_horizontal_length_mm"] for r in options["G4D"]["fixture_rows"]] == [6165, 4955, 6920, 6750]
    assert all(not r["actual_outlet_invert_and_products_known"] for o in options.values() for r in o["fixture_rows"])


def test_new500_drop_is_only_indoors_and_not_counted_as_horizontal_fall(report):
    original, new = report["options"][:2]
    assert new["drop_point_mm"] == [315, 4700] and new["interior_vertical_drop_mm"] == 500
    assert not new["mirror_first_floor_stair"] and original["interior_vertical_drop_mm"] == 0
    for a, b in zip(original["fixture_rows"], new["fixture_rows"], strict=True):
        assert a["total_horizontal_length_mm"] == b["total_horizontal_length_mm"]
        assert a["horizontal_fall_mm"] == b["horizontal_fall_mm"]
        assert math.isclose(a["pipe_package_top_at_riser_center_budget_mm"]-b["pipe_package_top_at_riser_center_budget_mm"], 500)
    assert min(r["lowest_budget_including_original_pipe_support_and_access_mm"] for r in original["fixture_rows"]) == 3461.6
    assert min(r["lowest_budget_including_original_pipe_support_and_access_mm"] for r in new["fixture_rows"]) == 2961.6


def test_package_top_is_not_replaced_by_lowest_clearance_and_front_is_more_conservative(report):
    option = report["options"][1]
    assert max(r["pipe_package_top_at_riser_center_budget_mm"] for r in option["fixture_rows"]) == 3200.9
    assert max(r["conservative_400_chase_top_before_fitting_growth_mm"] for r in option["fixture_rows"]) == 3204.9
    assert all(math.isclose(r["conservative_400_chase_top_before_fitting_growth_mm"]-r["pipe_package_top_at_riser_center_budget_mm"], 4) for r in option["fixture_rows"])
    assert all(math.isclose(r["pipe_package_top_at_riser_center_budget_mm"]-r["lowest_budget_including_original_pipe_support_and_access_mm"], 200) for r in option["fixture_rows"])


def test_original_G4_G5_fail_listed_soffits_while_G4D_retains_thick_and_fitting_failures(report):
    assert sum(len(o["soffit_cases"]) for o in report["options"]) == 36
    for o in report["options"]:
        if o["id"] in {"G4", "G5"}:
            assert all(not c["fits_assumed_soffit_budget_only"] for c in o["soffit_cases"])
    cases = report["options"][1]["soffit_cases"]
    assert sum(c["fits_assumed_soffit_budget_only"] for c in cases) == 8
    thick = next(c for c in cases if c["normal_stair_waist_mm"] == 300 and c["extra_fitting_above_original_package_mm"] == 0)
    assert thick["margin_after_separate_gap_mm"] == -33.379
    thin_margin = next(c for c in cases if c["normal_stair_waist_mm"] == 250 and c["extra_fitting_above_original_package_mm"] == 25)
    assert thin_margin["margin_after_separate_gap_mm"] == .38
    assert all(c["rear_optimistic_soffit_mm"] < c["front_optimistic_soffit_mm"] for c in cases)
    assert all(not c["actual_stair_pipe_access_fire_or_religious_approval"] for o in report["options"] for c in o["soffit_cases"])


def test_G4_body_retreat20_does_not_hide_outer_growth_or_stair_mirror_cost(report):
    for option in report["options"][:2]:
        assert option["shaft_front_to_original_platform_rear_mm"] == 20
        assert option["nominal_shaft_plan_over_original_landing_sqm"] == 0
        assert option["same_original_stair_local_route_hits"] == []
        assert [c["landing_overlap_sqm"] for c in option["chase_growth_cases"]] == [0, .00225, .015]
        assert option["indoor_required_clear_height_mm"] is None
    mirror = report["options"][2]
    assert mirror["same_original_stair_local_route_hits"] is None
    assert mirror["mirror_route_and_all_upper_stairs_require_new_design"]
    assert all(not o["existing_Q3_RF_results_inherited_as_approval"] and not o["whole_landing_door_care_palanquin_or_fire_clearance_approved"] for o in report["options"])


def test_original_rules_arcade_and_terminal_gaps_not_disguised_as_solved(report):
    assert report["arcade_minimum_illustrative_budget_mm"] == 3510.7
    assert report["arcade_extra25_illustrative_budget_mm"] == 3485.7
    assert not report["y3900_or_y4970_beam_presence_or_bottom_known"]
    assert all(o["ground_arcade_floor_obstruction_sqm"] == o["pipe_plan_over_sacred_backing_storage_sqm"] == 0 for o in report["options"])
    assert all(o["overhead_pipe_plan_over_arcade_sqm"] > 0 for o in report["options"])
    assert report["front_underground_path_lower_bound_mm"] == 5190 and report["front_underground_illustrative_fall_mm"] == 103.8
    assert not report["front_legal_connection_depth_cover_foundation_or_excavation_approved"]
    assert report["rear_route_full_width_protected_band_y_mm"] == [9100, 11370]
    assert not report["buried_sacred_crossing_exemption_authorized"]


def test_Q3_front_KTV_is_already_dry_not_a_new_cancelled_branch(report):
    assert set(report["Q3_front_KTV_items"]) == {"sofa", "table", "tv", "service-cabinet"}
    assert not report["Q3_front_KTV_wet_fixture_present"] and not report["new_front_3F_wastewater_load_assumed"]
    assert {c["id"] for c in report["claim_review"]} == {f"CC-{i:02d}" for i in range(1, 11)}
    text = next(c["correction"] for c in report["claim_review"] if c["id"] == "CC-09")
    assert "不是樓梯街門" in text


@pytest.mark.parametrize("defect", ["parent-pin", "drop-omitted", "drop-outdoors", "silent-original-drop", "cross-protection", "off-return", "shrink-shaft", "missing-claim", "report-promotion"])
def test_bad_sources_or_silent_relaxations_stop_crosscheck_export(monkeypatch, defect):
    import house_design.b_front_drop_claude as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    if defect == "parent-pin":
        cfg["pinned_sources"][cfg["parent_report"]] = "0"*64
    elif defect == "drop-omitted":
        cfg["candidates"][1]["interior_vertical_drop_mm"] = 0
    elif defect == "drop-outdoors":
        cfg["candidates"][1]["drop_point_mm"] = [315, 3000]
    elif defect == "silent-original-drop":
        cfg["candidates"][0]["interior_vertical_drop_mm"] = 500
    elif defect == "cross-protection":
        cfg["candidates"][0]["header_route_mm"] = [[315,1980],[315,3900],[3000,3900],[3000,5190],[1480,5190]]
    elif defect == "off-return":
        cfg["candidates"][0]["shaft_mm"][0] = 80
        cfg["candidates"][0]["header_route_mm"][-1][0] = 280
    elif defect == "shrink-shaft":
        cfg["candidates"][1]["shaft_mm"][2] = 200
    elif defect == "missing-claim":
        cfg["claim_review"].pop()
    else:
        cfg["adopted"] = True
    monkeypatch.setattr(module, "read_json", lambda p: cfg if p == ROOT/CONFIG else read(p))
    with pytest.raises(ContractError):
        build(ROOT)


def test_static_artifacts_links_bounds_sources_and_blank_professional_replies(report):
    files = render(report)
    assert len(files) == 12 and sum(n.endswith(".svg") for n in files) == 3
    assert all((ROOT/OUT/n).read_bytes() == value.encode() for n, value in files.items())
    assert report["report_hash"] == stable_hash({k:v for k,v in report.items() if k != "report_hash"})
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n,h in report["source_hashes"].items())
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n,h in manifest["artifacts"].items())
    for name,value in files.items():
        if name.endswith(".svg"):
            svg = ET.fromstring(value)
            assert int(svg.attrib["width"])*int(svg.attrib["height"]) <= 1_680_000
            assert all(0 <= float(t.attrib["y"]) < 1200 for t in svg.iter() if t.tag.endswith("text"))
    assert all((ROOT/OUT/ref).is_file() for ref in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]))
    assert "沒有全共識" in files["index.html"] and "未採用" in files["index.html"]
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["專業回覆", "費用工期保固", "屋主選擇", "審查與施工圖發行"])
    followup = (ROOT/"Docs/claude-b-front-drop-followup-v2.md").read_text()
    assert "不呼叫工具" in followup and "不改家規" in followup and "G4D" in followup

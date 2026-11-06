from __future__ import annotations

import copy
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from house_design.abc_fresh_air_detail import (
    CONFIG,
    OUT,
    branch,
    build,
    connected,
    duct_section,
    opening_overlaps,
    outdoor_group,
    points,
    removal_budget,
    screen_paths,
)
from house_design.contracts import ContractError, read_json, sha256_file
from scripts.export_abc_fresh_air_detail import render, response_rows

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_frozen_current_sources_and_protected_controls(report):
    assert report["protected_controls_unchanged"] == 149
    for name, digest in report["source_hashes"].items():
        assert sha256_file(ROOT/name) == digest
    cfg = read_json(ROOT/CONFIG)
    assert sha256_file(ROOT/cfg["parent_report"]) == cfg["parent_file_sha256"]
    assert report["parent_report_hash"] == cfg["parent_report_hash"]
    assert [e["id"] for e in report["retained_b_entries"]] == ["b-rear-split", "b-front-split"]
    assert all(e["states"] == ["daily", "ritual", "carry"] for e in report["retained_b_entries"])


def test_parent_pin_change_stops_build(monkeypatch, report):
    cfg = copy.deepcopy(report["config"])
    cfg["parent_file_sha256"] = "0"*64
    import house_design.abc_fresh_air_detail as module
    original = module.read_json
    monkeypatch.setattr(module, "read_json", lambda p: cfg if Path(p) == ROOT/CONFIG else original(p))
    with pytest.raises(ContractError, match="parent file changed"):
        build(ROOT)


def test_unknown_products_holes_heights_performance_and_approvals_stay_unknown(report):
    assert report["adopted"] is report["full_MEP_fit_verified"] is False
    assert report["selected_product"] is report["actual_machine_count"] is None
    assert report["professional_approval"] == "unknown" and report["browser_qa"] == "not-run"
    assert report["known_occupancy_total"] == 9
    assert report["unknown_peak_and_third_floor_occupancy_is_zero"] is False
    assert all(n["actual_unit_four_ports_mm"] is None for n in report["networks"])
    assert all(not g["approved"] and not g["legal_opening_and_access_verified"] and
        g["actual_opening_z_mm"] is None for g in report["outdoor_groups"])
    assert all(not g["own_pair_or_neighbour_short_circuit_verified"] for g in report["outdoor_groups"])


def test_no_adoption_or_invented_height_from_continuing(monkeypatch, report):
    import house_design.abc_fresh_air_detail as module
    original = module.read_json
    cfg = copy.deepcopy(report["config"])
    cfg["external_z_mm"] = 2500
    monkeypatch.setattr(module, "read_json", lambda p: cfg if Path(p) == ROOT/CONFIG else original(p))
    with pytest.raises(ContractError, match="assumed sections"):
        build(ROOT)


def test_graph_handles_mid_segment_taps_but_not_isolated_branches():
    base = [[[0, 0], [0, 10]], [[0, 5], [8, 5]]]
    assert connected(base, [0, 0])
    assert connected([*base, [[8, 5], [8, 10]]], [0, 0])
    assert not connected([*base, [[9, 9], [9, 10]]], [0, 0])


@pytest.mark.parametrize("path", [[], [[0, 0]], [[0, 0], [1, 1]], [[0, 0], [0, 0]], [[0, 0], [float("nan"), 0]], [[0, 0], [True, 0]]])
def test_bad_path_is_rejected(path):
    with pytest.raises(ContractError):
        points(path)


def test_all_original_dry_labels_get_dedicated_return_without_duplicate_flows(report):
    assert len(report["networks"]) == 8 and len(report["branches"]) == 24
    assert len({b["id"] for b in report["branches"]}) == 24
    assert all(b["SA"] != b["RA"] and b["ordinary_return_does_not_depend_on_door_gap"] for b in report["branches"])
    assert all(b["actual_supply_m3_h"] is b["actual_return_m3_h"] is None for b in report["branches"])
    assert report["per_room_flow_not_duplicated_from_floor_total"]
    assert not any(":floor-1:" in b["id"] and b["building"] == "B" for b in report["branches"])
    assert all(u["phase"] == "commission-with-current-use" for u in report["units"] if u["floor"] == "floor-3")


def test_terminal_cannot_be_moved_over_the_old_guest_desk(report):
    b = copy.deepcopy(next(b for b in report["config"]["branches"] if b["network"] == "A3" and b["room"] == "guest"))
    b["SA"] = [4900, 14900]
    net = next(n for n in report["networks"] if n["id"] == "A3")
    with pytest.raises(ContractError, match="furniture body"):
        branch(b, net, report["roster"], report["config"])


def test_b_right_neck_connects_front_without_using_dry_protection(report):
    for n in [n for n in report["networks"] if n["building"] == "B"]:
        assert connected(n["paths"], n["origin_mm"])
        assert not n["screen"]["protected_hits"]
        assert [5500, 10300] in n["paths"][0]
        assert [4000, 6500] in n["paths"][0]
        bad = [[[5300, 13950], [4000, 13950], [4000, 10300]]]
        with pytest.raises(ContractError, match="dry-protection"):
            screen_paths(bad, 500, report["roster"]["B"][n["floor"]])


def test_c_full_band_avoids_stair_and_door_cannot_be_used_as_return(report):
    n = next(n for n in report["networks"] if n["id"] == "C1")
    assert [1900, 14200] in n["paths"][0]
    assert not n["screen"]["protected_hits"]
    with pytest.raises(ContractError, match="stair1f"):
        screen_paths([[[1900, 8000], [1900, 13300], [2200, 13300], [2200, 15000]]],
            500, report["roster"]["C"]["floor-1"])
    right = next(b for b in report["branches"] if b["id"] == "C:floor-1:living-right")
    assert max(r[1]+r[3] for role in ["SA", "RA"] for r in right[role+"_screen"]["swept_rects_mm"]) < 8550


def test_b_no_rear_opening_fallback_never_uses_a_rear_terminal(report):
    groups = [g for g in report["outdoor_groups"] if g["building"] == "B"]
    assert len(groups) == 4
    for floor in ["floor-2", "floor-3"]:
        choices = [g for g in groups if g["floor"] == floor]
        assert {g["side"] for g in choices} == {"front", "rear"}
        front = next(g for g in choices if g["side"] == "front")
        assert front["preference"] == "independent-no-rear-opening-fallback"
        assert all(front[r+"_path"][-1][1] == 3900 for r in ["OA", "EA"])
        assert not front["OA_screen"]["protected_hits"] and not front["EA_screen"]["protected_hits"]


def test_outdoor_port_requires_stated_front_or_rear_host_wall(report):
    g = copy.deepcopy(report["config"]["external_groups"][0])
    g["OA_path"][-1][1] = 4400
    net = next(n for n in report["networks"] if n["id"] == g["network"])
    with pytest.raises(ContractError, match="front/rear host wall"):
        outdoor_group(g, net, report["roster"], report["config"])


def test_no_side_or_party_wall_can_be_assumed(report):
    g = copy.deepcopy(report["config"]["external_groups"][0])
    g["side"] = "left"
    net = next(n for n in report["networks"] if n["id"] == g["network"])
    with pytest.raises(ContractError, match="side/party wall"):
        outdoor_group(g, net, report["roster"], report["config"])


def test_window_projection_does_not_approve_hole_height_or_change_window(report):
    room = next(r for r in report["roster"]["C"]["floor-1"] if r["id"].endswith(":dining"))
    hit = opening_overlaps(room, "front", [250, 3900], 250)
    assert "candidate-window" in hit["same_wall_xy_opening_span_hits"]
    assert hit["existing_window_head_mm"] == 2100
    assert hit["opening_survey_complete"] is False
    assert room["features"]["window_mm"] == 2400


def test_four_ducts_do_not_fit_reused_500_pair_band(report):
    cfg = report["config"]
    assert duct_section(2, 1, cfg)["width_mm"] == 500
    flat, stacked = duct_section(4, 1, cfg), duct_section(2, 2, cfg)
    assert [flat["width_mm"], flat["height_mm"]] == [950, 275]
    assert [stacked["width_mm"], stacked["height_mm"]] == [500, 500]
    assert all(i["z_separation_and_ports_unknown"] and not i["approved"] for i in report["interfaces"])
    assert any(i["potential_four_role_xy_intersections"] > 0 for i in report["interfaces"])
    with pytest.raises(ContractError):
        duct_section(1.5, 2, cfg)


def test_ceiling_numbers_are_only_assumptions_not_actual_floor_height(report):
    row = next(v for v in report["ceiling_cases"] if v["hypothetical_underslab_clear_height_mm"] == 2600 and v["duct_arrangement"] == "four_stacked")
    assert row["highest_finished_ceiling_in_this_assumption_mm"] == 2050
    assert row["actual_beam_bottom_mm"] is None and not row["legal_headroom_or_product_fit_verified"]
    assert len(report["ceiling_cases"]) == 8


def test_nominal_hatch_frame_hand_and_removal_are_distinct(report):
    a, b = report["removal_cases"]
    assert a["clear_panel_mm"] == [1210, 650]
    assert a["margin_mm"] == [-120, -87] and not a["straight_plan_budget_fits"]
    assert b["margin_mm"] == [220, 213] and b["straight_plan_budget_fits"]
    assert not b["whole_product_replacement_verified"]
    for bad in [-1, True, float("nan")]:
        with pytest.raises(ContractError):
            removal_budget([1600, 1000], [1230, 637], bad, 50)


def test_service_side_budget_does_not_invent_filter_pull_or_safe_ladder(report):
    assert len(report["service_candidates"]) == 8
    for s in report["service_candidates"]:
        assert s["selected_side"] is None and len(s["sides"]) == 4
        assert all(v["actual_product_pull_distance_and_direction"] is None and not v["service_egress_approved"] for v in s["sides"])
    assert len(response_rows(report)) == 8
    assert all(v["model_count_low_flow_at_dirty_filter_pressure"] is None for v in response_rows(report))


def test_research_does_not_fake_scanned_manual_access_or_select_product(report):
    research = report["research"]
    assert not research["product_selected"] and not research["full_installation_manual_verified"]
    alaska, panasonic = research["sources"][:2]
    assert alaska["listed_airflows_m3_h"][-1] == 90
    assert any("403" in n for n in alaska["notes"])
    assert panasonic["manufacturer_side_maintenance_hatch_suggestion_mm"] == [600, 600]
    assert len(panasonic["pdf_sha256"]) == 64


def test_artifact_manifest_bytes_source_binding_and_bounded_vectors(report):
    files = render(report)
    assert len(files) == 13
    manifest = json.loads(files["artifact-manifest.json"])
    assert manifest["report_hash"] == report["report_hash"]
    for name, digest in manifest["artifacts"].items():
        assert hashlib.sha256(files[name].encode()).hexdigest() == digest
        assert (ROOT/OUT/name).read_bytes() == files[name].encode()
    for name, text in files.items():
        if name.endswith(".svg"):
            svg = ET.fromstring(text)
            assert svg.attrib["viewBox"] == "0 0 1400 1100"
            assert "未採用" in text and report["report_hash"] in text
    for link in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]):
        if not link.startswith("https://"):
            assert (ROOT/OUT/link).is_file()
    assert "瀏覽器／WebGL未執行" in files["index.html"]

"""Focused geometry and source-bound P3 tests; no scene, browser or installation."""
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
from shapely.geometry import LineString, Polygon

from house_design.b_front_service_detail import CONFIG, OUT, build, clear_width, leaves, panel_travel
from house_design.b_upper_replan import hit, rect
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_front_service_detail import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_p3_preserves_parents_and_primary_controls_without_promoting_status(report):
    assert report["option"] == "P3" and report["frame_land_ping"] == pytest.approx(31.99845)
    assert report["protected_controls_unchanged"] == 149
    assert report["parent_p1_p2_changed"] is report["primary_abc_or_3d_changed"] is False
    assert report["adopted"] is report["all_requirements_met"] is False
    assert report["professional_approval"] == "unknown" and report["rendered_qa"] == "not-run"
    original = {n: (ROOT/n).read_bytes() for n in report["config"]["pinned_sources"]}
    assert build(ROOT)["report_hash"] == report["report_hash"]
    assert original == {n: (ROOT/n).read_bytes() for n in original}


def test_only_front_service_changes_and_all_ground_roof_references_survive(report):
    parent = json.loads((ROOT/report["config"]["parent_report"]).read_text())
    p2 = parent["options"][1]
    for f, old in zip(report["floors"], p2["floors"], strict=True):
        unchanged = [r for r in f["rooms"] if r["id"] not in {"public-bath", "tea-foyer"}]
        assert unchanged == [r for r in old["rooms"] if r["id"] not in {"public-bath", "tea-foyer"}]
        assert f["unchanged_rooms_hash"] == stable_hash(unchanged)
    assert report["inherited_frontage"] == p2["frontage"]
    assert report["inherited_upper_stack"] == p2["upper_stack"]
    assert report["inherited_frontage"]["enclosure_nominal_add_sqm_per_upper_floor"] == 12.753
    assert len(report["unchanged_ground_and_roof_hashes"]) == 2
    for current, old in zip(report["unchanged_ground_and_roof_hashes"], parent["drainage"]["ground_options"], strict=True):
        assert current == {k: old[k] for k in current}


def test_shared_shaft_has_one_physical_budget_not_two_fake_deductions(report):
    for f in report["floors"]:
        a = f["area_ledger"]
        assert a["unique_physical_shaft_count_per_floor"] == 1 and a["room_references"] == 2
        assert a["gross_reserved_shaft_sqm"] == .16
        assert a["finish_losses_sqm"] == {"public-bath": .034, "tea-foyer": .034}
        assert a["already_excluded_partition_budget_sqm"] == .092
        assert f["front"]["shared_shaft_within_enclosure_and_straddles_both_rooms"]
        assert sum(a["finish_losses_sqm"].values())+a["already_excluded_partition_budget_sqm"] == pytest.approx(.16)
        assert a["areas115_sqm"]["public-bath"] == 5.286
        assert a["areas115_sqm"]["tea-foyer"] == 5.1036
        assert a["tea_after_worst_modeled_door_occupancy_sqm"] == 5.0838
        assert a["full_panel_translation_reserved_in_tea_finish_sqm"] == .0396
        assert a["tea_after_reserved_full_door_travel_sqm"] == 5.064
        assert a["not_a_statutory_area_method"]
        assert f["partition"] == {"overlaps": [], "unallocated_sqm": 0, "outside_frame_sqm": 0}
    areas = report["floors"][0]["area_ledger"]["areas115_sqm"]
    assert areas["master"] == 23.6651 and areas["private-bath"] == 6.133
    assert any(c["after_reserved_shafts_screens_sqm"] < 5 for a in report["floors"][0]["areas"]
        if a["id"] == "tea-foyer" for c in a["cases"] if c["inset_each_mm"] == 150)


def test_fixed_dimensions_and_exterior_window_candidates_not_reduced(report):
    cfg = report["config"]
    assert {r["id"]: sorted(r["rect_mm"][2:]) for r in cfg["public_fixtures"]} == {
        "shower": [900, 900], "toilet": [450, 700], "basin": [450, 600]}
    assert sorted(cfg["tea_furniture"][0]["rect_mm"][2:]) == [600, 1500]
    for f in report["floors"]:
        assert all(v == [] for k, v in f["fixtures"].items() if k != "operation_shared")
        assert all(w["on_room_boundary"] and not w["side_boundary_assumed_open"] and w["legal_effective_opening"] == "unknown" for w in f["windows"])
        assert not f["front"]["door_axis_over_toilet_body"]


def test_nine_independent_door_combinations_expose_half_and_closed_blockers(report):
    for f in report["floors"]:
        cases = f["front"]["door_combinations"]
        assert len(cases) == 9
        assert len({tuple(c["states"].values()) for c in cases}) == 9
        for c in cases:
            assert c["body_hits"] == [] and not any(c[k] for k in ["shaft_hit", "maintenance_hit", "panel_overlap"])
            expected = sorted(k for k, v in c["states"].items() if v != "open")
            arrival = next(r for r in c["route_blockers"] if r["route"] == "public-arrival")
            assert arrival["doors"] == expected
            assert c["clear_widths_mm"] == {k: {"open": 900, "half": 450, "closed": 0}[v] for k, v in c["states"].items()}
            shower = next(r for r in c["route_blockers"] if r["route"] == "public-shower-operation")
            assert not shower["doors"]
            maintenance = next(r for r in c["route_blockers"] if r["route"] == "dry-maintenance")
            assert maintenance["doors"] == (["stair"] if c["states"]["stair"] != "open" else [])


def test_real_panel_tracks_and_all_intermediate_translation_are_checked(report):
    for d in report["config"]["sliders"]:
        closed, opened = leaves(d, "closed"), leaves(d, "open")
        assert [clear_width(d, s) for s in ["open", "half", "closed"]] == [900, 450, 0]
        assert not hit(rect(closed[0]), rect(closed[1]))  # independent parallel tracks
        assert closed[1][1]-closed[0][1] == 85
        travel = panel_travel(d)
        assert all(rect(t).covers(rect(a)) and rect(t).covers(rect(b)) for t, a, b in zip(travel, closed, opened, strict=True))
    front = report["floors"][0]["front"]
    assert front["fixed_body_clearance_to_parked_panels_mm"]["bath_counter"] == 25
    assert front["fixed_body_clearance_to_parked_panels_mm"]["stair_counter"] > 1400
    assert front["fixed_body_clearance_to_full_panel_translation_mm"]["bath_counter"] == 25
    assert front["fixed_body_clearance_to_full_panel_translation_mm"]["stair_counter"] == pytest.approx((225**2+220**2)**.5)
    assert front["sliders_product_fire_smoke_rescue_and_actual_clear"] == "unknown"
    for f in report["floors"]:
        t = f["front"]["full_panel_translation"]
        assert len(t["envelopes"]) == 4 and not t["body_hits"] and not t["shaft_hit"] and not t["maintenance_hit"]
        assert not t["outside_nominal_front_enclosure"]


def test_maintenance_has_independent_dry_arrival_and_counter_is_sequential(report):
    front = report["floors"][0]["front"]
    assert front["maintenance_inside_tea_finish"] and not front["maintenance_body_hits"] and not front["maintenance_shaft_overlap"]
    assert front["dry_maintenance_mm"][2:] == [700, 900]
    assert front["counter_operation_and_passage_simultaneous"] is False
    for route in front["routes"]:
        assert route["within_model_floor"] and not route["body_hits"] and not route["shaft_hit"]
    arrival = next(r for r in front["routes"] if r["id"] == "public-arrival")
    assert "tea-foyer:tea-counter" in arrival["operation_shared"]
    assert report["floors"][1]["front"]["fixed_body_clearance_to_parked_panels_mm"] == {}


def test_complete_drain_lengths_include_branch_in_both_options(report):
    rows = {(r["option"], r["fixture"]): r for r in report["drainage"]["rows"]}
    totals = {"P2": [5360, 6465, 6530, 5250], "P3": [5065, 6415, 5680, 3900]}
    for name, expected in totals.items():
        for fid, length in zip(report["config"]["branch_fixture_ids"], expected, strict=True):
            r = rows[name, fid]
            assert r["total_length_mm"] == length == LineString(r["branch_points_mm"]).length+LineString(r["offset_points_mm"]).length
            assert r["hypothetical_total_fall_mm"] == length/50
            assert not r["actual_outlet_and_invert_known"] and not r["pipe_envelope_and_bends_designed"]
    assert rows["P3", "basin"]["branch_length_mm"] > rows["P2", "basin"]["branch_length_mm"]
    assert report["drainage"]["length_method"].startswith("fixture-body-centre-placeholder")
    assert "not-3F-or-whole-building" in report["drainage"]["section_scope"]


def test_shorter_offset_false_positive_is_not_promoted_to_approval(report):
    d = report["drainage"]
    assert len(d["full_path_section_sensitivity"]) == 72
    assert d["offset_only_cases"] == [
        {"option": "P2", "length_mm": 3900, "best_case_offset_only_remaining_mm": 3522},
        {"option": "P3", "length_mm": 2235, "best_case_offset_only_remaining_mm": 3555.3}]
    best = {fid: max(r["complete_path_remaining_mm"] for r in d["full_path_section_sensitivity"]
        if r["option"] == "P3" and r["fixture"] == fid) for fid in report["config"]["branch_fixture_ids"]}
    assert best == {"toilet": 3498.7, "basin": 3471.7, "tea-counter": 3486.4, "shower": 3522}
    assert d["offset_only_can_give_false_positive"]
    assert not d["all_gravity_drains_and_vents_designed"] and not d["ground_stair_void_proven"]
    assert d["front_discharge_constructible"] == "unknown" and d["ground_candidate_in_original_stair_sqm"] == .16
    assert d["direct_arcade_drop"].startswith("rejected") and not d["pumps_macerators_or_raised_floors_adopted"]


def test_family_protection_is_not_widened_by_front_service_work(report):
    assert all(not r["centerline_over_protected_footprints"] for r in report["drainage"]["rows"])
    for f in report["floors"]:
        assert all(not r["prohibited_overlap"] for r in f["religious_projection"])
        rooms = {r["id"]: Polygon(r["polygon_mm"]) for r in f["rooms"]}
        assert rooms["public-bath"].bounds[3] < 3900


@pytest.mark.parametrize("defect", ["body", "shrink", "shaft", "counter", "slider", "park-outside", "maintenance", "route", "frozen"])
def test_known_regressions_stop_export(monkeypatch, defect):
    import house_design.b_front_service_detail as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    if defect == "body":
        cfg["public_fixtures"][1]["rect_mm"] = [115, 115, 700, 450]
    elif defect == "shrink":
        cfg["public_fixtures"][0]["rect_mm"][2] = 800
    elif defect == "shaft":
        cfg["shared_shaft_mm"] = [2455, 1415, 400, 400]
    elif defect == "counter":
        cfg["tea_furniture"][0]["rect_mm"][1] = 2065
    elif defect == "slider":
        cfg["sliders"][0]["park_x_mm"] = [1800, 1800]
    elif defect == "park-outside":
        cfg["sliders"][0]["park_x_mm"] = [3500, 3500]
    elif defect == "maintenance":
        cfg["dry_maintenance_mm"] = [2500, 2135, 700, 900]
    elif defect == "route":
        cfg["routes"][0]["points_mm"] = [[1715, 4400], [400, 400]]
    else:
        cfg["pinned_sources"][cfg["parent_report"]] = "0"*64
    monkeypatch.setattr(module, "read_json", lambda p: cfg if p == ROOT/CONFIG else read(p))
    with pytest.raises(ContractError):
        build(ROOT)


def test_artifacts_sources_static_links_reply_blanks_and_bounded_sheets(report):
    files = render(report)
    assert len(files) == 9 and sum(n.endswith(".svg") for n in files) == 3
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    for name, expected in report["source_hashes"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n, h in manifest["artifacts"].items())
    assert all((ROOT/OUT/n).read_bytes() == data.encode() for n, data in files.items())
    for n, data in files.items():
        if n.endswith(".svg"):
            svg = ET.fromstring(data)
            assert int(svg.attrib["width"])*int(svg.attrib["height"]) <= 1_680_000
            assert all(float(el.attrib["y"]) < int(svg.attrib["height"]) for el in svg.iter() if el.tag.endswith("text"))
    assert "未採用" in files["index.html"] and "3498.7" in files["index.html"]
    for ref in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]):
        assert (ROOT/OUT/ref).is_file()
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["專業回覆", "成本工期代價", "負責窗口", "期限", "屋主選擇", "審查或發行依據"])

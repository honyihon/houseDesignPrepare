"""P4 full-size fixtures, independent door states and non-approved drainage budgets."""
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

from house_design.b_front_drainage_layout import CONFIG, OUT, build
from house_design.b_front_service_detail import panel_travel
from house_design.b_upper_replan import rect
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_front_drainage_layout import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_P4_preserves_frozen_P3_Q3_controls_and_approval_boundaries(report):
    before = {n: (ROOT/n).read_bytes() for n in report["config"]["pinned_sources"]}
    assert build(ROOT)["report_hash"] == report["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in before}
    assert report["protected_controls_unchanged"] == 149
    assert not report["adopted"] and not report["primary_abc_or_3d_changed"]
    assert not report["all_original_requirements_met"] and report["actual_site_or_product_data_received"] == 0
    assert report["professional_approval"] == "unknown" and report["rendered_qa"] == "not-run"


def test_only_2F_front_fixture_positions_change_and_no_bodies_or_operations_shrink(report):
    parent = json.loads((ROOT/report["config"]["parent_report"]).read_text())
    old, new = parent["floors"][0], report["floor"]
    assert new["id"] == "floor-2"
    assert {r["id"]: r for r in new["rooms"] if r["id"] not in {"public-bath", "tea-foyer"}} == {
        r["id"]: r for r in old["rooms"] if r["id"] not in {"public-bath", "tea-foyer"}}
    moved = []
    for a, b in zip(old["rooms"], new["rooms"], strict=True):
        assert {k: v for k, v in a.items() if k != "items"} == {k: v for k, v in b.items() if k != "items"}
        for ia, ib in zip(a["items"], b["items"], strict=True):
            for part in ["rect_mm", "operation_mm"]:
                if part in ia:
                    assert sorted(ia[part][2:]) == sorted(ib[part][2:])
            if ia["rect_mm"] != ib["rect_mm"]:
                moved.append(ia["id"])
    assert set(moved) == {"toilet", "basin", "shower", "tea-counter"}
    assert report["unchanged_ground_and_roof_hashes"] == parent["unchanged_ground_and_roof_hashes"]


def test_original_shaft_maintenance_and_Q3_front_pipe_projection_stay_identical(report):
    parent = json.loads((ROOT/report["config"]["parent_report"]).read_text())
    local = report["local_reference"]
    assert local["shared_shaft_mm"] == parent["config"]["shared_shaft_mm"] == [115, 1780, 400, 400]
    assert local["dry_maintenance_mm"] == parent["config"]["dry_maintenance_mm"] == [115, 2180, 700, 900]
    assert report["original_Q3_front_shaft_mm"] == [local["shared_shaft_mm"]]
    assert not report["Q3_shaft_moved_or_3F_fixture_layout_changed"]
    assert report["original_room_outlines_shaft_maintenance_stair_entry_and_windows_retained"]


def test_all_five_routes_recomputed_without_body_or_shaft_hits_and_no_toilet_door_axis(report):
    front = report["floor"]["front"]
    assert len(front["routes"]) == 5
    assert all(r["within_model_floor"] and not r["body_hits"] and not r["shaft_hit"] for r in front["routes"])
    assert not front["door_axis_over_toilet_body"]
    assert front["maintenance_inside_tea_finish"] and not front["maintenance_body_hits"]
    assert not front["counter_operation_and_passage_simultaneous"]
    assert "tea-foyer:tea-counter" in next(r for r in front["routes"] if r["id"] == "dry-maintenance")["operation_shared"]


def test_nine_door_states_keep_half_and_closed_blocking_without_collision(report):
    states = report["floor"]["front"]["door_combinations"]
    assert len(states) == 9
    for s in states:
        assert not s["body_hits"] and not s["shaft_hit"] and not s["maintenance_hit"] and not s["panel_overlap"]
        for door, state in s["states"].items():
            assert s["clear_widths_mm"][door] == {"open": 900, "half": 450, "closed": 0}[state]
        blockers = next(r["doors"] for r in s["route_blockers"] if r["route"] == "public-arrival")
        assert blockers == [k for k in ["bath", "stair"] if s["states"][k] != "open"]


def test_panel_full_motion_and_fixed_body_margins_remain_explicit_not_products(report):
    assert report["clearances_mm"] == {"bath_full_travel_to_shaft_mm": 35, "bath_full_travel_to_counter_mm": 25,
        "arrival_to_shower_body_mm": 20, "arrival_to_counter_body_mm": 40}
    travel = report["floor"]["front"]["full_panel_translation"]
    assert not travel["body_hits"] and not travel["shaft_hit"] and not travel["maintenance_hit"]
    assert not travel["outside_nominal_front_enclosure"]
    bath = report["config"]["bath_slider"]
    old_bad = copy.deepcopy(bath)
    for key in ["a", "b"]:
        old_bad[key][0] -= 100
    for key in ["closed_x_mm", "park_x_mm"]:
        old_bad[key] = [v-100 for v in old_bad[key]]
    assert any(rect(p).intersection(rect(report["local_reference"]["shared_shaft_mm"])).area > 0 for p in panel_travel(old_bad))


def test_model_area_goals_are_preserved_but_thicker_finishes_still_fail(report):
    area = report["floor"]["area_ledger"]
    assert area["areas115_sqm"]["public-bath"] == 5.286
    assert area["areas115_sqm"]["tea-foyer"] == 5.1036
    assert area["tea_after_reserved_full_door_travel_sqm"] == 5.064
    assert area["areas115_sqm"]["master"] == 23.6651 and area["areas115_sqm"]["private-bath"] == 6.133
    thick = next(r for r in report["front_area_sensitivity"] if r["inset_each_mm"] == 150)
    assert thick["tea-foyer"] < 5


def test_complete_path_comparison_includes_worse_shower_and_unchanged_offset(report):
    rows = {r["fixture"]: r for r in report["drainage"]["rows"]}
    assert {k: r["total_length_mm"] for k, r in rows.items()} == {"toilet": 4025, "basin": 2815, "tea-counter": 4780, "shower": 4610}
    assert {k: r["change_total_length_mm"] for k, r in rows.items()} == {"toilet": -1040, "basin": -3600, "tea-counter": -900, "shower": 710}
    assert {r["offset_length_mm"] for r in rows.values()} == {2235}
    assert all(not r["centerline_over_protected_footprints"] and not r["actual_outlet_and_invert_known"] for r in rows.values())
    assert all(not r["pipe_envelope_and_bends_designed"] for r in rows.values())


def test_only_the_best_section_example_reaches_target_and_extra_25_loses_it(report):
    d = report["drainage"]
    assert d["P3_best_case_minimum_remaining_mm"] == 3471.7
    assert d["P4_best_case_minimum_remaining_mm"] == 3504.4
    assert len(d["section_scenarios"]) == 27
    good = [r for r in d["section_scenarios"] if r["all_four_meet_illustrative_target_only"]]
    assert len(good) == 1
    assert (good[0]["structure_mm"], good[0]["pipe_support_mm"], good[0]["extra_below_original_pipe_budget_mm"]) == (200, 150, 0)
    assert good[0]["margin_to_illustrative_target_mm"] == 4.4
    extra = next(r for r in d["section_scenarios"] if (r["structure_mm"], r["pipe_support_mm"], r["extra_below_original_pipe_budget_mm"]) == (200, 150, 25))
    assert extra["minimum_remaining_budget_mm"] == 3479.4
    assert all(not r["gravity_drainage_or_actual_arcade_clearance_approved"] for r in d["section_scenarios"])


def test_ground_stair_drop_and_global_deficits_are_not_hidden(report):
    d = report["drainage"]
    assert d["ground_candidate_in_original_stair_sqm"] == .16
    assert not d["ground_stair_void_proven"] and not d["all_gravity_drains_and_vents_designed"]
    assert d["front_discharge_constructible"] == "unknown"
    assert d["direct_arcade_drop"] == "rejected-new-obstruction-in-arcade"
    assert not d["pumps_macerators_or_raised_floors_adopted"] and not d["minimum_actual_pipe_slope_or_pipe_size_selected"]
    assert "RF24" in report["config"]["limits"][-1]


@pytest.mark.parametrize("defect", ["shrink-body", "shrink-operation", "bad-door", "counter-in-route", "too-late-turn", "narrow-arrival", "wrong-parent"])
def test_known_P4_regressions_stop_export(monkeypatch, defect):
    import house_design.b_front_drainage_layout as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    if defect == "shrink-body":
        cfg["public_fixtures"][0]["rect_mm"][2] -= 100
    elif defect == "shrink-operation":
        cfg["public_fixtures"][0]["operation_mm"][2] -= 100
    elif defect == "bad-door":
        cfg["bath_slider"]["closed_x_mm"][0] -= 100
    elif defect == "counter-in-route":
        cfg["tea_furniture"][0]["rect_mm"] = [1150, 2135, 1500, 600]
    elif defect == "too-late-turn":
        cfg["routes"][0]["points_mm"][1][1] = 3335
        cfg["routes"][0]["points_mm"][2][1] = 3335
    elif defect == "narrow-arrival":
        cfg["routes"][0]["width_mm"] = 700
    else:
        cfg["pinned_sources"][cfg["parent_report"]] = "0"*64
    monkeypatch.setattr(module, "read_json", lambda p: cfg if p == ROOT/CONFIG else read(p))
    with pytest.raises(ContractError):
        build(ROOT)


def test_static_artifacts_sources_svg_bounds_links_and_unknown_outlets(report):
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
    assert "未採用" in files["index.html"] and "4.4mm" in files["index.html"]
    for row in csv.DictReader(io.StringIO(files["actual-outlets.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["產品完整型號與排水圖", "真實排出口XYZ", "管徑坡度及依據", "梁板及騎樓同版剖面"])
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["專業回覆", "費用工期及保固", "屋主選擇", "施工圖發行"])

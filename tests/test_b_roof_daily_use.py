"""Daily-use geometry, door control and fixed-component capacity regressions."""
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
from historical_support import native_geometry_reference
from shapely.geometry import Point, Polygon

from house_design.b_roof_daily_use import CONFIG, OUT, build
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_roof_daily_use import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_sources_formal_goals_and_original_drawings_remain_unchanged(report):
    original = {n: (ROOT/n).read_bytes() for n in report["config"]["pinned_sources"]}
    assert build(ROOT)["report_hash"] == report["report_hash"]
    assert original == {n: (ROOT/n).read_bytes() for n in original}
    assert report["protected_controls_unchanged"] == 149
    assert not report["adopted"] and not report["primary_abc_or_3d_changed"] and not report["all_original_requirements_met"]
    assert report["rendered_qa"] == "not-run" and report["professional_approval"] == "unknown" and report["actual_site_or_product_data_received"] == 0
    assert len(report["original_RF_requirements"]) == 5 and all(r["original_status"] == "candidate" for r in report["original_RF_requirements"])


def test_fixed_front_bound_remains_below24_even_without_all_equipment(report):
    capacity = report["capacity"]
    assert capacity["front_nominal_gross_sqm"] == 23.4
    assert capacity["front_before_equipment_with_edge_budget_sqm"] == 21.83945
    assert capacity["front_short_of24_before_equipment_sqm"] == 2.16055
    assert capacity["RF_deck_original_target_sqm"] == 24 and capacity["RF_deck_original_min_sqm"] == 10
    assert not capacity["min10_is_owner_accepted_target"] and not capacity["removing_equipment_or_changing_only_front_door_can_solve24"]
    assert "not-global-impossibility" in capacity["scope"]


def test_disconnected_rear_is_not_credited_via_unauthorized_daily_route(report):
    c = report["capacity"]
    assert c["disconnected_component_count"] == 2
    assert not c["front_and_rear_daily_areas_added_together"] and not c["ordinary_route_through_protection_authorized"]
    parts = [Polygon(p["outer"], p["holes"]) for p in c["components_mm"]]
    assert sum(p.covers(Point(1715, 2500)) and p.covers(Point(3000, 15000)) for p in parts) == 0


def test_new_left_hinge_removes_old_full_open_corner_collision(report):
    old, new = report["old_right_hinge_door_control"], report["nominal_front_door"]
    assert old["hinge"] == "right" and new == {**old, "hinge": "left"}
    assert new["a"] == [1150, 3900] and new["b"] == [2280, 3900]
    for o in report["options"]:
        assert o["old_right_hinged_door_full_open_blocks_arrival_route"]
        assert not next(s for s in o["door_states"] if s["state"] == "open")["route_blockers"]["arrival-to-front"]
        assert not o["sampled_door_sweep_hits"]


def test_all_door_states_are_checked_without_passing_half_open(report):
    for o in report["options"]:
        assert {s["state"] for s in o["door_states"]} == {"open", "half", "closed"}
        for s in o["door_states"]:
            assert not s["fixed_body_hits"]
            assert s["route_blockers"] == {"arrival-to-front": s["state"] != "open", "rack-operation": False, "table-operation": False}
        assert all(r["inside_conditional_floor"] and not r["fixed_body_hits"] and r["over_protected_sqm"] == 0 for r in o["routes"])


def test_platform_and_door_width_are_checked_as_distinct_conditional_interfaces(report):
    assert report["arrival_platform_mm"] == [1280, 3970, 1000, 1000]
    assert report["original_full_RF_arrival_slab_mm"] == [80, 3970, 2200, 1000]
    assert report["front_connection_strip_mm"] == [1280, 3900, 1000, 70]
    assert report["door_nominal_width_mm"] == 1130 and report["door_clear_budget_after_two_frames_mm"] == 900
    assert report["arrival_platform_vs_door_center_offset_mm"] == 65
    assert report["900_route_left_of_conservative_platform_mm"] == 15
    assert not report["actual_3F_to_RF_stair_flights_levels_or_door_threshold_verified"]
    assert not report["source_full_width_landing_structurally_usable_verified"]
    for o in report["options"]:
        cases = {r["width_mm"]: r for r in o["arrival_width_cases"]}
        assert cases[700]["inside_conditional_floor"] and cases[800]["inside_conditional_floor"]
        assert not cases[900]["inside_conditional_floor"] and cases[900]["outside_conditional_floor_sqm"] > 0
        assert cases[900]["inside_if_source_full_width_landing_confirmed"]
        assert all(not r["fully_open_door_hit"] and not r["fixed_body_hits"] and r["actual_clearance_or_care_approval"] == "unknown" for r in cases.values())


def test_equal_furniture_neither_adds_wet_equipment_nor_invents_capacity(report):
    for o in report["options"]:
        assert {i["id"]: sorted(i["rect_mm"][2:]) for i in o["furniture"]} == {"drying-rack": [600, 1800], "folding-table": [450, 1200]}
        assert not o["furniture_body_or_operation_defects"]
        assert o["front_open_outline_before_daily_furniture_sqm"]-o["front_open_outline_after_daily_furniture_sqm"] == pytest.approx(1.62)
        assert not o["wet_laundry_appliance_or_new_drain_added"] and not o["outdoor_furniture_products_selected"]
        assert not o["goal_reduced_or_owner_adopted"] and o["original_RF_deck_goal_sqm"] == 24 and not o["original_RF_deck_goal_met"]
        assert not o["upstream_stairs_products_structure_weather_or_religion_approved"]


def test_operation_sharing_is_explicit_and_not_claimed_simultaneously_passable(report):
    d1, d2 = report["options"]
    assert d1["arrival_route_shares_folding_operation"] and not d2["arrival_route_shares_folding_operation"]
    assert not any(o["simultaneous_two_person_work_and_escape_verified"] for o in report["options"])
    assert "folding-table" in d1["routes"][0]["shared_operation_ids"]
    assert "folding-table" not in d2["routes"][0]["shared_operation_ids"]


def test_original_equipment_variants_are_inherited_without_silent_improvement(report):
    parent = json.loads((ROOT/report["config"]["parent_report"]).read_text())
    by_id = {o["id"]: o for o in parent["options"]}
    assert report["parent_equipment_options_hash"] == stable_hash(parent["options"])
    for o in report["options"]:
        source = by_id[o["equipment_option_id"]]
        assert o["equipment_reference_hash"] == stable_hash(source)
        assert o["equipment_reservations"] == source["reservations"]
    assert by_id["S2-rear-wet-pair"]["tank_to_heat_pump_envelope_plan_gap_mm"] == 65


@pytest.mark.parametrize("defect", ["door-right", "table-door", "rack-unit", "shrink-rack", "route-protected", "parent-drift"])
def test_known_geometry_regressions_stop_export(monkeypatch, defect):
    import house_design.b_roof_daily_use as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    if defect == "door-right":
        cfg["proposed_front_door"]["hinge"] = "right"
    elif defect == "table-door":
        cfg["options"][0]["furniture"][1]["rect_mm"] = [1150, 3400, 1200, 450]
    elif defect == "rack-unit":
        cfg["options"][0]["furniture"][0]["rect_mm"] = [3270, 115, 600, 1800]
    elif defect == "shrink-rack":
        cfg["options"][0]["furniture"][0]["rect_mm"][3] = 1700
    elif defect == "route-protected":
        cfg["arrival_route_mm"] = [[2850, 4400], [2850, 2500]]
    else:
        cfg["pinned_sources"][cfg["parent_report"]] = "0"*64
    monkeypatch.setattr(module, "read_json", lambda p: cfg if p == ROOT/CONFIG else read(p))
    with pytest.raises(ContractError):
        build(ROOT)


def test_source_bound_outputs_and_blank_decision_forms(report):
    archived = native_geometry_reference(ROOT/OUT/"review.json", report)
    files = render(archived)
    assert len(files) == 12 and sum(n.endswith(".svg") for n in files) == 3
    assert all((ROOT/OUT/n).read_bytes() == text.encode() for n, text in files.items())
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in report["source_hashes"].items())
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n, h in manifest["artifacts"].items())
    assert all((ROOT/OUT/ref).is_file() for ref in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]))
    for n, text in files.items():
        if n.endswith(".svg"):
            svg = ET.fromstring(text)
            assert int(svg.attrib["width"])*int(svg.attrib["height"]) <= 1_680_000
            assert all(0 <= float(t.attrib["y"]) < 1200 for t in svg.iter() if t.tag.endswith("text"))
    assert "未採用" in files["index.html"] and "21.83945" in files["index.html"] and "左鉸鏈" in files["index.html"]
    assert all(p["owner_choice"] is None for p in report["decision_paths"])
    for row in csv.DictReader(io.StringIO(files["decision-paths.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["屋主選擇", "同版專業依據", "正式發行"])
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"])

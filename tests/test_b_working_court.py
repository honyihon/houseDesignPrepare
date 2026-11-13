"""Focused RF/court geometry regressions; no renderer or professional certification."""
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
from shapely.ops import unary_union

from house_design.b_upper_replan import rect, sweep
from house_design.b_working_court import CONFIG, OUT, build
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_working_court import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_study_cannot_adopt_or_rewrite_immutable_parent_and_controls(report):
    assert report["protected_controls_unchanged"] == 149
    assert not report["adopted"] and not report["primary_abc_or_3d_changed"] and not report["all_original_requirements_met"]
    assert report["rendered_qa"] == "not-run" and report["professional_approval"] == "unknown"
    assert report["actual_site_or_product_data_received"] == 0
    before = {n: (ROOT/n).read_bytes() for n in report["config"]["pinned_sources"]}
    assert report["report_hash"] == build(ROOT)["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in before}


def test_partial_cover_preserves_floor_area_and_does_not_hide_wet_projection(report):
    original, strip, dry = report["options"]
    assert original["rf_opening_sqm"] == 5.112 and strip["rf_opening_sqm"] == 2.639
    assert strip["rf_opening_reduction_sqm"] == 2.473
    assert strip["rf_opening_mm"] == [1100, 11470, 1300, 2030]
    assert strip["rf_front_collar_mm"] == [1100, 11370, 1300, 100]
    assert strip["rf_left_strip_clear_budget_mm"] == 885
    assert all(o["floor_outline115_sqm"] == 4.123 for o in report["options"])
    assert original["wet_3F_over_2F_master_sqm"] == strip["wet_3F_over_2F_master_sqm"] == 5.112
    assert dry["wet_3F_over_2F_master_sqm"] == 0
    assert all(o["direct_sky_opening_is_not_rainfall_or_effective_ventilation_area"] for o in report["options"])
    assert all(o[k] == 0 for o in report["options"] for k in ["wet_3F_over_2F_bed_sqm", "wet_3F_over_palanquin_sqm", "wet_3F_over_shrine_or_backing_sqm"])


def test_front_guard_newly_found_interface_is_retained_not_retroactively_passed(report):
    original, strip, dry = report["options"]
    assert original["rf_void_or_guard_over_protected_sqm"] == .25
    assert original["guard_protected_interface_requires_review"]
    assert original["guard_family_or_structural_permission"].startswith("unknown")
    assert strip["rf_void_or_guard_over_protected_sqm"] == dry["rf_void_or_guard_over_protected_sqm"] == 0
    protected = unary_union([Polygon(p) for p in report["protected_polygons_mm"]])
    assert not rect(strip["rf_opening_mm"]).intersects(protected)
    assert all(Polygon(p).intersection(protected).area == 0 for p in strip["rf_guard_polygons_mm"])


def test_left_maintenance_routes_restore_connectivity_only_in_listed_roof_model(report):
    original, strip, dry = report["options"]
    assert original["old_left_corridor_interrupted_by_void_or_guard"]
    assert not strip["old_left_corridor_interrupted_by_void_or_guard"] and not dry["old_left_corridor_interrupted_by_void_or_guard"]
    assert all(r["within_reserved_roof_surface"] and r["outside_sqm"] == 0 and not r["unit_hits"] and not r["void_or_guard_hit"] for o in report["options"] for r in o["rf_routes"])
    route = next(r for r in strip["rf_routes"] if r["id"] == "rear-left-unit")
    clear_strip = rect([115, 11370, 885, 2130])
    through_court = sweep(route["points_mm"], 700).intersection(rect(report["config"]["court_mm"]))
    assert clear_strip.covers(through_court)
    assert "outside-RF-side-door" in route["scope"] and "not-stairs-or-machine-transport" in route["scope"]


def test_width_sensitivity_rejects_thin_strip_and_thick_guard(report):
    cases = {r["strip_width_mm"]: r for r in report["width_sensitivity"]}
    assert cases[900]["clear_budget_mm"] == 685 and not cases[900]["fits700_in_width_model"]
    assert cases[1100]["clear_budget_mm"] == 885 and cases[1100]["fits700_in_width_model"]
    assert cases[1100]["sky_opening_sqm"] == 2.639
    guards = {r["guard_budget_mm"]: r for r in report["guard_sensitivity"]}
    assert guards[300]["clear_budget_mm"] == 685 and not guards[300]["fits700_after_recentering_in_width_model"]
    assert guards[250]["fits700_after_recentering_in_width_model"]


def test_dry_room_is_not_credited_as_an_outdoor_balcony_or_wet_laundry(report):
    dry = report["options"][2]
    assert dry["rf_opening_mm"] is None and dry["rf_opening_sqm"] == 0
    assert dry["working_court_outdoor_outline115_candidate_sqm"] == 0 and dry["indoor_dry_utility_outline115_sqm"] == 4.123
    assert not dry["wet_equipment_in_dry_fallback"]
    assert dry["outdoor_work_balcony_legal_or_environmental_approval"] == "original-3F-outdoor-goal-not-met"
    ledger = {r["id"]: r for r in report["original_3f_requirement_ledger"]}
    assert len(ledger) == 5 and all(r["original_status"] == "candidate" and not r["functional_or_legal_requirement_verified"] for r in ledger.values())
    assert ledger["B.floor-3.balcony_b3"]["target_sqm"] == 4 and ledger["B.floor-3.balcony_b3"]["values_by_option_sqm"]["R2-dry-room"] == 0
    assert ledger["B.floor-3.ktv"]["target_sqm"] == 20 and set(ledger["B.floor-3.ktv"]["values_by_option_sqm"].values()) == {19.2079}
    assert not report["P3_front_gravity_drainage_resolved"]


def test_fixed_topology_bounds_reject_simple_room_swaps_without_global_claims(report):
    b = report["fixed_topology_bounds"]
    assert "not-global-impossibility" in b["scope"]
    assert b["rear_stack_only"]["short_before_new_partition_sqm"] == 2.867
    assert b["front_shared_with_outdoor"]["short_before_new_partition_or_acoustics_sqm"] == 2.9841
    slim = b["slender_court_without_replanning_guest"]
    assert slim["outline115_sqm"] == 4.0719 and slim["overlap_with_retained_guest_nominal_sqm"] == 1.479
    assert slim["guest_remaining_after_recuts_and115_sqm"] == 10.944 < 12
    assert slim["guest_item_hits"] == ["wardrobe"] and slim["rejected_as_simple_swap"]


def test_roof_goals_and_unit_identities_remain_unknown_where_not_fitted(report):
    goals = {r["id"].rsplit(".", 1)[-1]: r for r in report["rf_original_requirement_ledger"]}
    assert {k: r["target_sqm"] for k, r in goals.items()} == {"rf_stair": 6, "rf_tank": 3, "rf_hp": 2.5, "rf_deck": 24, "rf_shrine_buffer": 29.5}
    assert all(r["original_status"] == "candidate" and r["complete_effective_area_sqm"] is None and not r["fitted_and_approved"] for r in goals.values())
    assert report["RF_front_optimistic_area_after_two_slot_services_sqm"] == 20.97
    assert report["RF_front_short_of_original_deck24_before_other_equipment_sqm"] == 3.03
    assert {u["id"] for u in report["existing_units"]} == {"B-AC03", "B-AC04"}
    assert all(u["actual_unit_identity"] is u["new_unit_purchase_count"] is None for u in report["representative_slots"])
    assert not any(o["all_roof_equipment_fitted"] for o in report["options"])


def test_inherited_floor_door_results_are_exact_and_conditional_on_no_new_support(report):
    parent = json.loads((ROOT/report["config"]["parent_report"]).read_text())
    assert report["floor3_reference"] == parent["front_option"]
    assert report["floor3_reference_hash"] == stable_hash(parent["front_option"])
    assert report["second_floor_reference_hash"] == parent["second_floor_reference_hash"]
    assert report["ground_and_roof_controls"] == parent["ground_and_roof_controls"]
    for o in report["options"]:
        assert o["inherited_floor3_door_state_count"] == 81 and o["floor3_other_rooms_and_all_furniture_doors_routes_unchanged"]
        assert not o["new_3F_supports_drawn"] and not o["supports_proven_unnecessary"]
        assert "no-new-supports" in o["inherited_door_results_scope"]


@pytest.mark.parametrize("defect", ["narrow-strip", "guard-in-protection", "hit-unit", "move-court", "source-drift"])
def test_regressions_stop_new_exports(monkeypatch, defect):
    import house_design.b_working_court as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    if defect == "narrow-strip":
        cfg["rf_retained_strip_width_mm"] = 900
    elif defect == "guard-in-protection":
        cfg["rf_front_collar_budget_mm"] = 50
    elif defect == "hit-unit":
        cfg["direct_left_route_mm"][-1] = [550, 17400]
    elif defect == "move-court":
        cfg["court_mm"][1] += 100
    else:
        cfg["pinned_sources"][cfg["parent_report"]] = "0"*64
    monkeypatch.setattr(module, "read_json", lambda p: cfg if p == ROOT/CONFIG else read(p))
    with pytest.raises(ContractError):
        build(ROOT)


def test_source_bound_static_outputs_and_blank_engineering_replies(report):
    files = render(report)
    assert len(files) == 11 and sum(n.endswith(".svg") for n in files) == 3
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in report["source_hashes"].items())
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n, h in manifest["artifacts"].items())
    assert all((ROOT/OUT/n).read_bytes() == data.encode() for n, data in files.items())
    for n, data in files.items():
        if n.endswith(".svg"):
            svg = ET.fromstring(data)
            assert int(svg.attrib["width"])*int(svg.attrib["height"]) <= 1_680_000
            assert all(0 <= float(t.attrib["y"]) < 1200 for t in svg.iter() if t.tag.endswith("text"))
    for ref in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]):
        assert (ROOT/OUT/ref).is_file()
    assert "未採用" in files["index.html"] and "2.639" in files["index.html"] and "0.25" in files["index.html"]
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"])

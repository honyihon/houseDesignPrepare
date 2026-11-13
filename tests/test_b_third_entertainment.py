"""Focused B3 design and immutable-source checks; no scene or acoustic certification."""
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
from shapely.geometry import LineString, Polygon

from house_design.b_third_entertainment import CONFIG, OUT, build
from house_design.b_upper_replan import rect
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_third_entertainment import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_independent_study_preserves_original_sources_and_formal_statuses(report):
    assert report["protected_controls_unchanged"] == 149
    assert report["adopted"] is report["all_original_requirements_met"] is report["primary_abc_or_3d_changed"] is False
    assert not report["complete_scheme_ready_or_adopted"] and report["professional_approval"] == "unknown"
    assert report["rendered_qa"] == "not-run" and report["actual_site_or_product_data_received"] == 0
    before = {n: (ROOT/n).read_bytes() for n in report["config"]["pinned_sources"]}
    assert report["report_hash"] == build(ROOT)["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in before}
    assert not report["P3_front_gravity_drainage_resolved"]


def test_fixed_rear_bound_does_not_claim_a_global_impossibility(report):
    b = report["fixed_rear_optimistic_bound"]
    assert b["usable_upper_bound_sqm"] == 31.0171
    assert b["guest12_plus_KTV20_sqm"] == 32 and b["short_of_two_targets_sqm"] == .9829
    assert b["ignores_new_guest_KTV_partition_corridor_and_acoustic_layers"]
    assert b["includes_original_dry_protection_and_rear_shaft"]
    assert "not-a-global-impossibility" in b["scope"]


def test_area_sensitivity_retains_goal20_and_min14_without_faking_acoustics(report):
    cases = {(c["option"], c["extra_each_face_mm"]): c for c in report["acoustic_space"]["cases"]}
    assert len(cases) == 10
    assert [cases["rear", n]["area_sqm"] for n in [0, 50, 100, 150, 200]] == [14.3141, 13.4541, 12.6141, 11.7941, 10.9941]
    assert [cases["front", n]["area_sqm"] for n in [0, 50, 100, 150, 200]] == [21.0159, 20.1019, 19.2079, 18.3339, 17.4799]
    assert cases["rear", 0]["min14_met_in_model"] and not cases["rear", 50]["min14_met_in_model"]
    assert cases["front", 50]["goal20_met_in_model"] and not cases["front", 100]["goal20_met_in_model"]
    assert cases["front", 100]["unchanged_furniture_parts_outside"] == []
    assert cases["front", 150]["unchanged_furniture_parts_outside"]
    assert all(c["acoustic_performance"].startswith("unknown") for c in cases.values())
    limit = report["acoustic_space"]["front_extra_each_face_limit_for20_in_this_area_model_mm"]
    assert 55 < limit < 56
    assert report["acoustic_space"]["limit_is_not_a_permitted_product_thickness_or_acoustic_spec"]
    assert report["acoustic_space"]["internal_shaft_lining_airlock_silencer_and_equipment_not_fully_budgeted"]


def test_complete_floor_partition_and_planar_routes_are_consistent(report):
    f = report["front_option"]
    assert f["partition"] == {"overlaps": [], "unallocated_sqm": 0, "outside_frame_sqm": 0}
    assert all(v == [] for k, v in f["fixtures"].items() if k != "operation_shared")
    assert len(f["explicit_routes"]) == 6
    assert all(r["within_model_floor"] and r["outside_sqm"] == 0 and not r["fixed_hits"] and not r["shaft_hits"] for r in f["explicit_routes"])
    assert f["primary_acoustic_inset_mm"] == 215 and not f["front_furniture_parts_outside_primary"]
    assert f["front_entry_clear_width_in_primary_frame_budget_mm"] == 700
    assert all(f["rear_door_openings_on_room_boundary"].values())
    assert f["quiet_to_rear_connection"]["operation"].startswith("no-leaf")
    assert f["stair_upstream_platform_and_original_side_door"].startswith("unknown")


def test_four_doors_have_eighty_one_independent_states(report):
    cases = report["front_option"]["independent_door_states"]
    assert len(cases) == 81 and len({tuple(s["states"].values()) for s in cases}) == 81
    for s in cases:
        assert not s["body_hits"] and not s["shaft_hits"] and not s["panel_pair_hits"]
        for r in report["front_option"]["explicit_routes"]:
            expected = [r["expected_door"]] if r["expected_door"] and s["states"][r["expected_door"]] != "open" else []
            assert s["route_blockers"][r["id"]] == expected
    assert len(report["front_option"]["slider_full_translation"]) == 4
    assert all(not s["fixed_hits"] and not s["shaft_hits"] and s["within_planning_frame"] for s in report["front_option"]["slider_full_translation"])
    assert report["front_option"]["working_court_public_access_without_guest"]


def test_religious_and_sleeping_projections_are_not_silently_relaxed(report):
    f = report["front_option"]
    assert all(not r["prohibited_overlap"] for r in f["religious_projection"])
    p = {r["room"]: r for r in report["vertical_projections"]}
    assert report["old_rear_entertainment_over_2F_master_sqm"] == 9.062
    assert p["front-entertainment"]["over_2F_master_sqm"] == 0
    assert p["rear-bath"]["over_2F_master_sqm"] == 0
    assert p["working-court"]["over_2F_master_sqm"] == 5.112  # Still a waterproofing/maintenance cost.
    assert all(v["over_2F_bed_body_sqm"] == 0 for v in p.values())
    guest = next(r for r in f["rooms"] if r["id"] == "guest")
    bed = next(i for i in guest["items"] if i["id"] == "bed")
    doorway = next(s for s in report["config"]["sliders"] if s["id"] == "guest")
    cx = (doorway["a"][0]+doorway["b"][0])/2
    assert not LineString([[cx, 14100], [cx, 17630]]).intersects(rect(bed["rect_mm"]))


def test_original_three_floor_program_is_all_accounted_for_without_promotion(report):
    ledger = {r["id"]: r for r in report["original_3f_requirement_ledger"]}
    assert len(ledger) == 5
    assert {k.rsplit(".", 1)[-1]: r["modeled_value_sqm"] for k, r in ledger.items()} == {
        "flex_b": 29.2948, "ktv": 19.2079, "bath_b3": 6.133, "guest_b": 12.423, "balcony_b3": 4.123}
    assert all(r["original_status"] == "candidate" and not r["functional_or_legal_requirement_verified"] for r in ledger.values())
    assert not ledger["B.floor-3.ktv"]["target_met_in_area_model_only"]
    assert ledger["B.floor-3.ktv"]["target_sqm"] == 20 and ledger["B.floor-3.ktv"]["min_sqm"] == 14
    assert ledger["B.floor-3.balcony_b3"]["target_met_in_area_model_only"]  # Not legal work-balcony approval.
    assert report["new_front_enclosed_nominal_sqm"] == 23.4
    assert report["additional_enclosed_nominal_over_P3_sqm"] == 10.647


def test_furniture_and_bath_sizes_remain_and_windows_do_not_use_partywalls(report):
    rooms = {r["id"]: r for r in report["front_option"]["rooms"]}
    assert {i["id"]: sorted(i["rect_mm"][2:]) for i in rooms["front-entertainment"]["items"]} == {
        "sofa": [900, 1800], "table": [600, 1200], "tv": [80, 1000]}
    assert {i["id"]: sorted(i["rect_mm"][2:]) for i in rooms["guest"]["items"]} == {"bed": [1800, 2000], "wardrobe": [600, 1800]}
    assert {i["id"]: sorted(i["rect_mm"][2:]) for i in rooms["rear-bath"]["items"]} == {
        "basin": [450, 600], "toilet": [450, 700], "shower": [900, 900]}
    assert all(w["on_room_boundary"] and not w["side_boundary_assumed_open"] and w["legal_effective_opening"] == "unknown" for w in report["front_option"]["windows"])
    assert report["front_2F_pipe_shaft_retained_mm"] == [115, 1780, 400, 400]


def test_roof_changes_and_full_existing_equipment_reservations_are_explicit(report):
    roof = report["rf_overlay"]
    assert roof["original_roof_reference_changed"] is False and roof["proposed_roof_overlay_requires_change"]
    assert roof["void_sqm"] == roof["void_over_existing_service_zone_sqm"] == 5.112
    assert roof["straight_old_rear_access_interrupted"]
    assert roof["requires_roof_replan_structural_opening_legal_outdoor_and_drainage"]
    assert not roof["all_existing_or_future_roof_equipment_fitted"] and not roof["roof_finalized_or_changed_in_primary"]
    assert {u["id"] for u in roof["existing_units"]} == {"B-AC03", "B-AC04"}
    assert len(roof["candidate_slots"]) == 2
    assert all(u["actual_unit_identity"] is None and u["new_unit_purchase_count"] is None for u in roof["candidate_slots"])
    assert not roof["slots_body_pair_hits"] and not roof["void_unit_hits"] and roof["slots_protected_projection_sqm"] == 0
    assert all(r["within_roof_frame"] and not r["void_or_guard_hit"] and not r["unit_hits"] for r in roof["alternative_routes"])
    assert roof["guard_budget_is_not_selected_handrail"]
    assert roof["refrigerant_condensate_structure_wind_and_acoustic_isolation"] == "unknown"


def test_upper_ground_and_parent_controls_remain_exact(report):
    p = json.loads((ROOT/report["config"]["service_report"]).read_text())
    assert report["second_floor_reference_hash"] == stable_hash(p["floors"][0])
    assert report["ground_and_roof_controls"] == p["unchanged_ground_and_roof_hashes"]
    assert report["rear_control"] == p["floors"][1]
    old = {r["id"]: r for r in p["floors"][1]["rooms"]}
    new = {r["id"]: r for r in report["front_option"]["rooms"]}
    assert new["stair"] == old["stair"] and new["dry-protection"] == old["dry-protection"]
    assert new["quiet-living"]["polygon_mm"] == old["quiet-living"]["polygon_mm"]
    assert new["quiet-living"]["items"] == old["quiet-living"]["items"]
    assert not new["quiet-living"]["doors"]  # Old balcony bypass must not remain open.
    assert new["rear-bath"]["polygon_mm"] == next(r["polygon_mm"] for r in p["floors"][0]["rooms"] if r["id"] == "private-bath") or Polygon(new["rear-bath"]["polygon_mm"]).equals(
        Polygon(next(r["polygon_mm"] for r in p["floors"][0]["rooms"] if r["id"] == "private-bath")))


@pytest.mark.parametrize("defect", ["shrink", "route", "door", "detached-slider", "court-over-shrine", "bath-stack", "rf-protected", "roof-parent-drift", "frozen-source"])
def test_known_design_regressions_stop_export(monkeypatch, defect):
    import house_design.b_third_entertainment as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    if defect == "shrink":
        cfg["front_furniture"][0]["rect_mm"][2] = 1700
    elif defect == "route":
        cfg["routes"][0]["points_mm"] = [[1715, 4400], [4000, 1500]]
    elif defect == "door":
        cfg["sliders"][0]["park_x_mm"] = [115, 115]
    elif defect == "detached-slider":
        cfg["sliders"][1]["track_y_mm"] = [12000, 12085]
    elif defect == "court-over-shrine":
        cfg["working_court_mm"] = [0, 9100, 2400, 2130]
    elif defect == "bath-stack":
        cfg["rear_bath_mm"] = [3600, 14100, 2400, 3530]
    elif defect == "rf-protected":
        cfg["rf_candidate_slots_mm"][0] = [2500, 5000, 900, 350]
    elif defect == "roof-parent-drift":
        pass  # Alter the in-memory reference below; original files stay untouched.
    else:
        cfg["pinned_sources"][cfg["upper_report"]] = "0"*64
    def altered(p):
        if p == ROOT/CONFIG:
            return cfg
        value = read(p)
        if defect == "roof-parent-drift" and p == ROOT/cfg["ground_report"]:
            value["stack_and_entry"]["options"][0]["roof_reference"]["base_mm"] += 1
        return value
    monkeypatch.setattr(module, "read_json", altered)
    with pytest.raises(ContractError):
        build(ROOT)


def test_static_outputs_bounded_source_hashes_links_and_blank_replies(report):
    archived = native_geometry_reference(ROOT/OUT/"review.json", report)
    files = render(archived)
    assert len(files) == 11 and sum(n.endswith(".svg") for n in files) == 4
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
            assert all(float(t.attrib["y"]) < 1200 for t in svg.iter() if t.tag.endswith("text"))
    for ref in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]):
        assert (ROOT/OUT/ref).is_file()
    assert "未採用" in files["index.html"] and "19.2079" in files["index.html"]
    assert len(list(csv.DictReader(io.StringIO(files["door-route-matrix.csv"].lstrip("\ufeff"))))) == 81
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"])

"""Frozen-source Q3 geometry and stair-arrival regressions; no runtime or certification."""
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

from house_design.b_ktv_stair_options import CONFIG, OUT, build, front_leaf, side_leaf
from house_design.b_upper_replan import rect
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_ktv_stair_options import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_independent_Q3_does_not_adopt_or_rewrite_parent_controls(report):
    before = {n: (ROOT/n).read_bytes() for n in report["config"]["pinned_sources"]}
    assert build(ROOT)["report_hash"] == report["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in before}
    assert report["protected_controls_unchanged"] == 149
    assert not report["adopted"] and not report["primary_abc_or_3d_changed"] and not report["all_original_requirements_met"]
    assert report["rendered_qa"] == "not-run" and report["professional_approval"] == "unknown"
    assert report["actual_site_or_product_data_received"] == 0


def test_frame_is_conserved_and_the_lobe_does_not_add_whole_floor_volume(report):
    primary = report["primary"]
    assert primary["KTV_nominal_outline_sqm"] == 25.32
    assert primary["front_nominal_add_over_Q2_sqm"] == 1.92
    assert primary["additional_whole_floor_enclosed_volume_over_Q2_sqm"] == 0
    assert primary["floor_analysis"]["partition"] == {"overlaps": [], "unallocated_sqm": 0, "outside_frame_sqm": 0}
    front = Polygon(next(r["polygon_mm"] for r in primary["rooms"] if r["id"] == "front-entertainment"))
    assert front.area == 25_320_000
    assert front.intersection(rect([2400, 3900, 3600, 5200])).area == 0
    assert all(not p["prohibited_overlap"] for p in primary["floor_analysis"]["religious_projection"])


def test_original_non_stair_rooms_and_original_ground_family_rules_stay_exact(report):
    parent = json.loads((ROOT/report["config"]["parent_report"]).read_text())
    old = {r["id"]: r for r in parent["front_option"]["rooms"]}
    new = {r["id"]: r for r in report["primary"]["rooms"]}
    assert all(new[key] == value for key, value in old.items() if key not in {"front-entertainment", "stair"})
    assert report["original_frozen_ground_and_roof_controls"] == parent["ground_and_roof_controls"]
    assert report["retained_guest_bath_sliders"] == parent["config"]["sliders"]
    assert report["retained_quiet_rear_opening"] == parent["front_option"]["quiet_to_rear_connection"]
    assert not report["floor1_stair_and_owner_functions_changed"]
    assert not report["second_floor_room_boundaries_and_wet_areas_changed"]
    assert not report["RF24_goal_or_C_care_or_A_space_changed"]
    assert not report["upstream_P3_front_drainage_resolved"]


def test_20sqm_is_counted_after_explicit_wrap_and_floor_cabinet(report):
    p = report["primary"]
    assert p["inset_each_face_mm"] == 215 and p["shaft_extra_wrap_each_mm"] == 50
    assert p["KTV_area_before_cabinet_after_wrap_sqm"] == 20.7289
    assert p["KTV_area_after_wrap_and_cabinet_sqm"] == 20.1889
    assert p["KTV_area_before_cabinet_after_wrap_sqm"]-p["KTV_area_after_wrap_and_cabinet_sqm"] == pytest.approx(.54)
    assert not p["acoustic_dB_or_full_airlock_and_silencer_approved"]
    ledger = {r["id"]: r for r in report["original_3F_requirement_ledger"]}
    assert len(ledger) == 5 and all(r["original_status"] == "candidate" and not r["functional_or_legal_requirement_verified"] for r in ledger.values())
    assert ledger["B.floor-3.ktv"]["target_sqm"] == 20 and ledger["B.floor-3.ktv"]["min_sqm"] == 14
    assert ledger["B.floor-3.ktv"]["modeled_value_sqm"] == 20.1889
    assert {k.rsplit(".", 1)[-1]: r["modeled_value_sqm"] for k, r in ledger.items() if not k.endswith(".ktv")} == {"flex_b": 29.2948, "bath_b3": 6.133, "guest_b": 12.423, "balcony_b3": 4.123}


def test_thicker_acoustics_or_larger_services_show_failure_not_a_thin_product_claim(report):
    cases = {(c["extension_mm"], c["extra_acoustic_each_face_mm"], c["extra_floor_service_sqm"]): c for c in report["capacity_cases"]}
    assert len(cases) == 100
    assert cases[0, 100, .54]["remaining_sqm"] == 18.6129
    assert cases[800, 100, .54]["goal20_met_in_area_model"]
    assert cases[800, 150, .54]["remaining_sqm"] == 19.2399 and not cases[800, 150, .54]["goal20_met_in_area_model"]
    assert cases[900, 150, .54]["remaining_sqm"] == 19.4269 and not cases[900, 150, .54]["goal20_met_in_area_model"]
    assert cases[800, 100, 1]["remaining_sqm"] == 19.7289 and not cases[800, 100, 1]["goal20_met_in_area_model"]
    assert all(c["acoustic_performance_or_legal_approval"] == "unknown" for c in cases.values())


def test_upper_risers_width_and_treads_remain_source_values_while_mid_platform_changes(report):
    old, new = report["upper_stairs"]["original_upper_source"], report["upper_stairs"]["primary"]
    assert old["geometry"]["middle_landing_mm"] == 1900 and new["middle_landing_mm"] == 1100
    assert new["riser_count"] == 18 and new["riser_mm"] == pytest.approx(3000/18)
    assert new["flight_width_mm"] == 1000 and new["tread_mm"] == 270 and new["run_mm"] == 2160
    assert new["new_rear_end_mm"] == new["original_rear_end_mm"] == 9030
    assert new["footprint"]["y_mm"] == 4770 and new["footprint"]["h_mm"] == 4260
    assert new["geometry_depth_sum_mm"] == new["footprint"]["h_mm"]
    assert report["original_stairs_by_floor"]["floor-1"]["geometry"]["risers"] == 24
    assert report["original_stairs_by_floor"]["floor-1"]["height_mm"] == 4000


def test_new_second_floor_platform_keeps_lower_right_stair_open(report):
    a = report["floor2_arrival_screen"]
    assert len(a["naive_full_width_new_platform_over_incoming_right_steps"]) == 3
    assert [r["clearance_under_assumed_slab_mm"] for r in a["naive_full_width_new_platform_over_incoming_right_steps"]] == [300, 133.333, -33.333]
    assert not a["actual_candidate_over_incoming_right_steps"]
    assert a["new_floor2_left_connection_mm"] == [80, 4770, 1000, 1000]
    safe = Polygon(a["floor2_landing_polygon_mm"])
    assert not safe.intersection(rect([1280, 4970, 1000, 800])).area
    assert a["inside_explicit_L_landing_model"] and a["transfer_width_mm"] == 900
    assert a["only_local_minimum_clearance_under_assumed_slab_mm"] == 3300
    assert not a["full_headroom_structural_or_egress_approval"] and not a["first_floor_stair_changed"]


def test_real_upstream_roof_routes_are_not_inherited_from_old_arrival(report):
    assert report["RF_arrival_platform_shift_mm"] == 800
    assert not report["RF_R_S_D_routes_inherited_as_verified"]
    assert report["second_and_third_outgoing_stair_geometry_changes_required"]


def test_two_doors_have_independent_states_and_explicit_advanced_front_y_geometry(report):
    p = report["primary"]
    assert len(p["door_states"]) == 9 and len({(d["front"], d["side"]) for d in p["door_states"]}) == 9
    for d in p["door_states"]:
        assert not d["body_hits"] and not d["door_pair_hit"]
        for route in p["routes"]:
            assert d["route_blockers"][route["id"]] == ([route["door"]] if d[route["door"]] != "open" else [])
    assert not p["sampled_front_and_side_swing_body_hits"]
    assert front_leaf(report["config"]["front_door"], 90).bounds[1] == pytest.approx(3370)
    assert side_leaf(report["config"]["side_door"], 90).bounds[2] == pytest.approx(3400)
    assert p["front_nominal_aperture_mm"] == 1330 and p["front_clear_budget_mm"] == 900
    assert all(r["inside_explicit_surface"] and not r["body_hits"] and not r["shaft_or_wrap_hit"] for r in p["routes"])
    assert next(r for r in p["routes"] if r["id"] == "KTV-arrival900")["actual_person_or_product_clearance"] == "unknown"


@pytest.mark.parametrize("defect", ["shrink", "shaft-wrap", "cabinet-route", "front-door", "side-door", "stair-floor", "source-drift"])
def test_known_geometric_or_contract_regressions_stop_export(monkeypatch, defect):
    import house_design.b_ktv_stair_options as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    if defect == "shrink":
        cfg["front_furniture"][0]["rect_mm"][2] = 1700
    elif defect == "shaft-wrap":
        cfg["shaft_extra_wrap_each_mm"] = 0
    elif defect == "cabinet-route":
        cfg["cabinet_rect_mm"] = [1400, 2500, 600, 900]
    elif defect == "front-door":
        cfg["front_door"]["a"][0] = 1150
    elif defect == "side-door":
        cfg["side_door"]["a"][1] = 3900
        cfg["side_door"]["b"][1] = 4900
    elif defect == "stair-floor":
        cfg["second_floor_transfer_route_mm"] = [[1780, 4470], [1780, 5270], [580, 5270]]
    else:
        cfg["pinned_sources"][cfg["parent_report"]] = "0"*64
    monkeypatch.setattr(module, "read_json", lambda p: cfg if p == ROOT/CONFIG else read(p))
    with pytest.raises(ContractError):
        build(ROOT)


def test_source_bound_static_outputs_and_unanswered_engineering_fields(report):
    files = render(report)
    assert len(files) == 10 and sum(n.endswith(".svg") for n in files) == 3
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    assert all((ROOT/OUT/n).read_bytes() == value.encode() for n, value in files.items())
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in report["source_hashes"].items())
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n, h in manifest["artifacts"].items())
    for name, value in files.items():
        if name.endswith(".svg"):
            svg = ET.fromstring(value)
            assert int(svg.attrib["width"])*int(svg.attrib["height"]) <= 1_680_000
            assert all(0 <= float(t.attrib["y"]) < 1200 for t in svg.iter() if t.tag.endswith("text"))
    assert all((ROOT/OUT/p).is_file() for p in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]))
    assert "未採用" in files["index.html"] and "20.1889" in files["index.html"] and "18.6129" in files["index.html"]
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"])

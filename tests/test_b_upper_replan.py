"""Small independent checks for B comparative geometry; never a scene/runtime test."""
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

from house_design.b_upper_replan import CONFIG, OUT, build, door, hit, rect
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_upper_replan import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_independent_comparison_preserves_32_land_envelope_and_primary_models(report):
    assert report["frame_sqm"] == 105.78
    assert report["frame_land_ping"] == pytest.approx(31.99845)
    assert report["frame_land_ping"] < 32
    assert report["protected_controls_unchanged"] == 149
    assert report["primary_abc_or_3d_changed"] is False
    assert report["adopted"] is report["all_requirements_met"] is False
    assert report["professional_approval"] == "unknown" and report["rendered_qa"] == "not-run"
    names = ["inputs/requirements.json", "inputs/planning-register.json", "structured/candidates/kaohsiung-house-options-3d.html"]
    before = {n: (ROOT/n).read_bytes() for n in names}
    assert report["report_hash"] == build(ROOT)["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in names}


def test_p2_keeps_original_area_goals_without_calling_it_buildable(report):
    p1, p2 = report["options"]
    goals = {r["id"]: r for r in p2["goals"]}
    expected = {"master": 23.6651, "public-bath": 5.16, "private-bath": 6.133,
        "quiet-living": 29.2948, "tea-foyer": 5.1376, "garden": 7.156, "third-guest": 15.5156, "third-ktv": 14.3141}
    assert {key: r["value_sqm"] for key, r in goals.items()} == expected
    assert all(r["target_met_in_115_model"] for r in goals.values() if r["id"] != "third-ktv")
    assert goals["third-ktv"]["target_met_in_115_model"] is False
    assert p2["third_ktv_meets_14_min_in_model"] and p2["buildable"] == "unknown"
    assert p2["frontage"]["enclosure_nominal_add_sqm_per_upper_floor"] == 12.753
    assert p1["frontage"]["enclosure_nominal_add_sqm_per_upper_floor"] == 6.48
    assert next(r for r in p1["goals"] if r["id"] == "tea-foyer")["target_met_in_115_model"] is False
    assert not p2["frontage"]["declared_as_exempt_landscape_after_enclosure"]
    assert p2["upper_stack"]["third_entertainment_over_second_master_sqm"] > 0
    assert p2["upper_stack"]["third_entertainment_over_second_bed_body_sqm"] == 0
    assert p2["upper_stack"]["third_wet_over_second_master_sqm"] == 0
    assert p2["upper_stack"]["acoustic_and_vibration_approval"].startswith("unknown")


def test_full_floor_partition_and_listed_geometry_are_clear(report):
    for option in report["options"]:
        for f in option["floors"]:
            assert f["partition"] == {"overlaps": [], "unallocated_sqm": 0, "outside_frame_sqm": 0}
            for key in ["body_hits", "operation_body_hits", "not_inside_115", "shaft_body_hits", "shaft_operation_hits", "sampled_swing_body_hits"]:
                assert f["fixtures"][key] == []
            assert f["fixtures"]["operation_shared"]  # Do not silently treat shared use as simultaneous.
            for route in f["routes"]:
                assert route["within_model_floor"] and route["outside_sqm"] == 0
                assert route["body_hits"] == route["shaft_hits"] == route["door_states"][0]["hits"] == []
                assert route["actual_access"].startswith("unknown")
            through_doors = [r for r in f["routes"] if r["id"] not in {"ensuite-shower-operation", "public-shower-operation"}]
            assert all(r["door_states"][1]["hits"] and r["door_states"][2]["hits"] for r in through_doors)


def test_explicit_shrine_backing_and_palanquin_projections_are_not_relaxed(report):
    forbidden = Polygon(report["protected_polygons_mm"][0]).union(Polygon(report["protected_polygons_mm"][1]))
    storage = rect(report["palanquin_rect_mm"])
    for option in report["options"]:
        for f in option["floors"]:
            for room in f["rooms"]:
                shape = Polygon(room["polygon_mm"])
                if room["kind"] in {"wet", "bedroom", "high-activity"}:
                    assert not hit(shape, forbidden)
                if room["kind"] == "wet":
                    assert not hit(shape, storage)
            assert all(not v["prohibited_overlap"] for v in f["religious_projection"])
    assert any(r["kind"] == "bedroom" and r["over_palanquin_sqm"] > 0 for r in report["options"][1]["floors"][0]["religious_projection"])


def test_furniture_sizes_windows_and_area_quality_not_faked(report):
    c = report["config"]["floors"]["common"]
    bodies = {r["id"]: sorted(r["rect_mm"][2:]) for r in c["master_furniture"]}
    assert bodies == {"bed": [1800, 2000], "wardrobe": [600, 1800], "vanity": [500, 1200]}
    for option in report["options"]:
        for f in option["floors"]:
            assert all(w["on_room_boundary"] and not w["side_boundary_assumed_open"] and w["legal_effective_opening"] == "unknown" for w in f["windows"])
        f2 = option["floors"][0]
        assert f2["bedroom_largest_axis_rect"]["master"]["area_sqm"] == pytest.approx(14.9291)
        assert f2["bedroom_largest_axis_rect"]["master"]["area_sqm"] < 20
        areas = {r["id"]: r for r in f2["areas"]}
        assert [r["inset_each_mm"] for r in areas["private-bath"]["cases"]] == [80, 115, 150]
        assert areas["private-bath"]["cases"][-1]["after_reserved_shafts_screens_sqm"] < 6


def test_both_ground_entries_three_states_and_roof_references_remain_unchanged(report):
    prior = json.loads((ROOT/report["config"]["source_report"]).read_text())
    for current, original in zip(report["drainage"]["ground_options"], prior["stack_and_entry"]["options"], strict=True):
        assert current["id"] == original["id"]
        assert current["source_states_hash"] == stable_hash(original["states"])
        assert current["roof_reference_hash"] == stable_hash(original["roof_reference"])
        assert [s["state"] for s in current["states"]] == ["daily", "ritual", "carry"]
        assert all(s["floor1_source_unchanged"] and not s["rear_shaft_fixed_body_hits"] for s in current["states"])
        assert all(s["ground_care_route_and_turning"].startswith("unknown") for s in current["states"])


def test_front_arcade_drainage_is_a_real_gate_not_a_claim_of_free_shaft(report):
    d = report["drainage"]
    assert d["front_direct_drop_status"] == "rejected-new-obstruction-in-arcade"
    assert not d["front_discharge_constructible"] and not d["all_gravity_drains_and_vents_designed"]
    assert d["offset_length_mm"] == 3900
    assert d["section_applies_to"] == "front-wet-foyer"
    assert d["option_offset_lengths_mm"] == {"front-bath-only": 2400, "front-wet-foyer": 3900}
    assert all(r["front_downpipe_over_stair_reserved_box"] == .16 for r in d["ground_options"])
    s = d["section_sensitivity"]
    assert len(s) == 9 and max(r["remaining_clear_mm"] for r in s) == 3522
    assert all(r["remaining_clear_mm"] < 3500 for r in s if r["structure_mm"] == 500)
    assert any(r["remaining_clear_mm"] >= r["target_mm"] for r in s)
    assert any(r["remaining_clear_mm"] < r["target_mm"] for r in s)


def test_mechanical_services_and_outdoor_routes_are_not_counted_as_soil(report):
    for option in report["options"]:
        f = option["frontage"]
        assert f["soil_ratio"] >= 1/3 and f["soil_inside_garden"]
        assert f["service_over_garden_sqm"] == f["soil_over_service_sqm"] == 0
        assert len(f["outdoor_units_mm"]) == len(f["outdoor_service_mm"]) == 2
        assert all(r[3] == 1350 for r in f["outdoor_service_mm"])
        assert f["outdoor_700_route"]["inside_model_open_or_living_area"]
        assert not f["outdoor_700_route"]["soil_hit"] and f["outdoor_700_route"]["unit_hits"] == []
        assert f["soil_depth_load_and_eligibility"] == "unknown"


@pytest.mark.parametrize("defect", ["body", "shrine-wet", "route", "shaft", "door", "frontage"])
def test_known_new_geometry_defects_stop_export(monkeypatch, defect):
    import house_design.b_upper_replan as module
    original = module.read_json
    cfg = copy.deepcopy(original(ROOT/CONFIG))
    if defect == "body":
        cfg["floors"]["common"]["master_furniture"][0]["rect_mm"] = cfg["floors"]["common"]["master_furniture"][1]["rect_mm"][:]
    elif defect == "shrine-wet":
        cfg["floors"]["common"]["private_bath_rect_mm"] = [2400, 3900, 3600, 5200]
    elif defect == "route":
        cfg["floors"]["common"]["routes"][0]["points_mm"] = [[300, 15000], [1000, 16000]]
    elif defect == "shaft":
        cfg["floors"]["common"]["private_shaft_mm"] = [5335, 14615, 400, 400]
    elif defect == "door":
        cfg["floors"]["common"]["private_door"]["a"] = [2000, 15100]
        cfg["floors"]["common"]["private_door"]["b"] = [2000, 16230]
    else:
        cfg["floors"]["options"][1]["soil_rects_mm"] = [[3270, 100, 1800, 1400]]
    monkeypatch.setattr(module, "read_json", lambda p: cfg if p == ROOT/CONFIG else original(p))
    with pytest.raises(ContractError):
        build(ROOT)


def test_artifacts_source_hashes_dimensions_and_reply_blanks(report):
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    for name, digest in report["source_hashes"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest
    files = render(report)
    assert len(files) == 11 and sum(n.endswith(".svg") for n in files) == 6
    manifest = json.loads(files["artifact-manifest.json"])
    for name, digest in manifest["artifacts"].items():
        assert hashlib.sha256(files[name].encode()).hexdigest() == digest
    assert all((ROOT/OUT/n).read_bytes() == data.encode() for n, data in files.items())
    for n, data in files.items():
        if n.endswith(".svg"):
            svg = ET.fromstring(data)
            assert int(svg.attrib["width"])*int(svg.attrib["height"]) <= 1_680_000
    for ref in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]):
        assert (ROOT/OUT/ref).is_file(), ref
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["專業回覆", "成本工期代價", "負責窗口", "期限", "屋主選擇", "審查或發行依據"])
    assert "未採用" in files["index.html"] and "前側新增室內" in files["index.html"]


def test_exact_swing_changes_with_door_state(report):
    d = report["config"]["floors"]["common"]["private_door"]
    assert door(d, 0).area == pytest.approx(1130*95)
    assert not door(d, 0).equals(door(d, 90))

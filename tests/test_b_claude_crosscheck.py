"""Focused geometry and evidence tests for the received Claude proposal; no cloud calls."""
import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from shapely.geometry import Polygon

from house_design.b_claude_crosscheck import CONFIG, OUT, analyze_variant, build
from house_design.b_fengshui_strict import area_shape
from house_design.contracts import ContractError, sha256_file
from scripts.export_b_claude_crosscheck import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_changed_source_is_rejected_before_comparison(tmp_path):
    cfg = json.loads((ROOT/CONFIG).read_text())
    cfg["source_report"] = "parent.json"
    (tmp_path/"inputs").mkdir()
    (tmp_path/CONFIG).write_text(json.dumps(cfg))
    (tmp_path/"parent.json").write_text("{}")
    with pytest.raises(ContractError, match="crosscheck source changed"):
        build(tmp_path)


def test_transcript_provenance_is_not_forged_as_original_raw_file(report):
    p = report["response_provenance"]
    assert p["original_files_currently_accessible"] is False
    assert p["archive_method"] == "copied-from-complete-prior-turn-tool-output-not-original-temp-file-bytes"
    assert p["prior_turn_checks"]["stdout_hash_matches_result"] is True
    assert p["prior_turn_checks"]["response_matches_raw_result_text"] is True
    assert sha256_file(ROOT/p["original_prompt_file"]) == p["original_prompt_sha256"]
    assert "20.0161" in (ROOT/p["response_archive"]).read_text()


def test_claude_claims_are_independently_computed_and_all_match(report):
    claims = report["claim_checks"]
    assert len(claims) == 4
    assert all(c["matches"] for c in claims)
    assert next(c for c in claims if c["claim"] == "bathroom_gain_vs_previous_115_sqm")["codex"] == pytest.approx(1.9261)


def test_real_polygon_partition_preserves_footprint(report):
    for variant in report["variants"]:
        assert variant["partition"] == {"gap_or_outside_sqm": 0, "overlap_sqm": 0, "status": "listed-geometry-clear"}
        assert sum(r["nominal_area_sqm"] for r in variant["rooms"]) == pytest.approx(37.56)
        assert len(variant["rooms"]) == 4


def test_whole_bedroom_and_baths_avoid_protected_use_and_storage(report):
    for v in report["variants"]:
        assert v["bedroom_over_protected_sqm"] == 0
        assert all(w["status"] == "listed-geometry-clear" for w in v["wet_projection"])
        assert all(w["over_protected_sqm"] == w["over_palanquin_sqm"] == 0 for w in v["wet_projection"])
        assert v["wet_projection"][0]["distance_to_backing_mm"] == 0  # Shared nominal boundary is not a positive setback.


def test_negative_projection_and_partition_do_not_retain_clear(report):
    previous = json.loads((ROOT/report["config"]["previous_study"]).read_text())
    rooms = copy.deepcopy(report["variants"][0]["rooms"])
    rooms[2]["polygon_mm"][1][0] = 2800  # Intrude into the complete backing protection.
    rooms[2]["polygon_mm"][2][0] = 2800
    result = analyze_variant(report["config"], previous, rooms, "negative", "test")
    assert result["wet_projection"][0]["status"] == "conflict"
    assert result["wet_projection"][0]["over_protected_sqm"] > 0
    assert result["partition"]["status"] == "conflict"


def test_one_extra_millimeter_loses_original_claude_bedroom_target(report):
    v = report["variants"][0]
    cases = {c["inset_each_mm"]: c for c in v["area_sensitivity"]}
    assert cases[115]["bedroom"] == pytest.approx(20.0161)
    assert cases[116]["bedroom"] == pytest.approx(19.992504)
    assert cases[115]["bedroom_meets_20"] is True
    assert cases[116]["bedroom_meets_20"] is False
    assert cases[150]["bedroom"] == pytest.approx(19.195)
    assert not any(c["both_bath_targets"] for c in v["area_sensitivity"])


def test_codex_margin_variant_trades_area_explicitly_without_target_change(report):
    original, margin = report["variants"]
    c = margin["current_inset_case"]
    assert c["bedroom"] == pytest.approx(20.2261)
    assert c["private_bath"] == pytest.approx(4.7124)
    assert c["public_bath"] == original["current_inset_case"]["public_bath"] == pytest.approx(4.5067)
    assert c["private_meets_min"] is True and c["both_bath_targets"] is False
    assert margin["targets_changed"] is margin["adopted"] is False
    assert "尚未送回Claude確認" in margin["author"]


def test_area_targets_still_match_original_requirement_records(report):
    reqs = {r["id"]: r["constraints"] for r in json.loads((ROOT/"inputs/requirements.json").read_text())["requirements"]}
    targets = report["config"]["original_targets_sqm"]
    assert targets["bedroom_target"] == reqs["B.floor-2.master_b"]["target_sqm"] == 20
    assert targets["public_bath_target"] == reqs["B.floor-2.bath_g"]["target_sqm"] == 5
    assert targets["public_bath_min"] == reqs["B.floor-2.bath_g"]["min_sqm"] == 3.6
    assert targets["private_bath_target"] == reqs["B.floor-2.master_bath"]["target_sqm"] == 6
    assert targets["private_bath_min"] == reqs["B.floor-2.master_bath"]["min_sqm"] == 4.5


def test_full_size_furniture_and_basins_preserved(report):
    for v in report["variants"]:
        sizes = {i["id"]: sorted(i["rect_mm"][2:]) for i in v["rooms"][0]["furniture"]}
        assert sizes == {"bed": [1800, 2000], "wardrobe": [600, 1800], "vanity": [500, 1200]}
        for r in v["rooms"][2:]:
            sizes = {i["id"]: sorted(i["rect_mm"][2:]) for i in r["furniture"]}
            assert sizes["toilet"] == [450, 700] and sizes["shower"] == [900, 900]
            assert sizes["basin"] == ([550, 900] if r["id"] == "private-bath" else [450, 600])


def test_operations_do_not_hit_other_fixed_bodies(report):
    for v in report["variants"]:
        assert v["bedroom_bodies_inside_115"] is v["bedroom_operations_inside_115"] is True
        for room in v["rooms"][2:]:
            s = room["screen"]
            assert s["body_hits"] == s["operation_body_hits"] == s["inside_arrival_hits"] == []
            assert s["all_listed_inside"] is s["inside_arrival_contained"] is True
            assert s["shared_operation_pairs"]
            assert room["actual_product_pack"] is room["actual_finished_clear_mm"] is None


def test_public_door_clear_coordinates_are_not_confused_with_local_origin(report):
    room = report["variants"][0]["rooms"][2]
    assert room["inside_approach_mm"] == [1435, 11485, 900, 900]
    assert room["doors"][0]["a"] == [1320, 11370]
    assert room["doors"][0]["b"] == [2450, 11370]
    assert room["doors"][0]["assumed_clear_mm"] == 900


def test_private_door_stays_absolute_when_bath_front_moves(report):
    a, b = [v["rooms"][-1] for v in report["variants"]]
    assert a["doors"] == b["doors"]
    assert a["inside_approach_mm"] == b["inside_approach_mm"] == [4015, 16445, 900, 900]
    a_wc, b_wc = a["furniture"][0]["rect_mm"], b["furniture"][0]["rect_mm"]
    assert b_wc[1]-a_wc[1] == 100
    for v in report["variants"]:
        assert v["bed_rear_to_open_private_leaf_mm"] == 15
        assert all(not d["parked_leaf_hits_arrival"] and not d["swept_rectangle_body_hits"] for d in v["door_arrivals"])


def test_local_route_and_rear_rectangle_not_a_claim_of_entire_care_route(report):
    for v in report["variants"]:
        assert v["route"]["all_inside_115"] is True and v["route"]["body_hits"] == []
        assert v["route"]["actual_whole_route"] == "unknown"
        assert v["rear_inscribed_rect_contained"] is True
        assert v["bedroom_rear_inscribed_rect_sqm"] == pytest.approx(14.4231)
        assert v["bed_to_rear_115_gap_mm"] == 165
        assert Polygon(v["rooms"][0]["polygon_mm"]).covers(area_shape(v["bedroom_rear_inscribed_rect_mm"]))


def test_hvac_box_relocated_inside_bedroom_but_route_not_engineered(report):
    for v in report["variants"]:
        assert v["bedroom_hvac_contained"] is True
        h = v["rooms"][0]["hvac_candidate"]
        assert h["rect_mm"] == [2525, 17225, 950, 280]
        assert h["route"] == "not-re-engineered" and h["manual"] is None


def test_third_floor_uses_same_dry_protection_but_does_not_add_suite(report):
    for v in report["variants"]:
        rooms = v["third_floor_rooms"]
        assert rooms[0]["id"] == "guest" and rooms[0]["hvac_candidate"]["id"] == "B-AC04"
        assert rooms[-1]["id"] == "rear-dry" and rooms[-1]["furniture"] == []
        assert "illustrative_finished_rect_mm" not in rooms[-1]
        assert sum("illustrative_finished_rect_mm" in r for r in rooms) == 1
        assert rooms[1]["polygon_mm"] == v["rooms"][1]["polygon_mm"]


def test_carry_bottleneck_is_conditional_and_variants_not_mixed(report):
    rear, front = report["carry_and_drain"]
    assert rear["rear_entry_nominal_mm"] == 1960
    assert rear["left_segment_nominal_mm"] == 1360
    assert rear["left_segment_required_for_preferred_rear_entry"] is False
    assert front["left_segment_nominal_mm"] == 1750
    assert front["front_door_nominal_mm"] == 1730
    assert front["front_door_clear_if_230_total_mm"] == 1500
    assert all(v["selected_stack_mm"] is None and v["actual_full_carried_route"] == "unknown" for v in [rear, front])
    assert all(any(r["overlap_sqm"] > 0 for r in v["under_public_bath_intersections"]) for v in [rear, front])


def test_agreement_log_never_promotes_codex_variant_to_claude_consensus(report):
    assert report["full_consensus"] is report["adopted"] is report["all_requirements_met"] is False
    rows = {r["id"]: r for r in report["agreement_log"]}
    assert rows["NEW-01"]["state"] == "not-reviewed-by-claude"
    assert rows["CLARIFY-01"]["state"] == "clarification-for-next-discussion"
    assert rows["AGREE-02"]["state"] == "independently-confirmed"


def test_all_prior_controls_unchanged(report):
    protected = json.loads((ROOT/report["config"]["protected_controls"]).read_text())
    assert report["protected_controls_unchanged"] == 149
    for name, digest in protected["hashes"].items():
        assert sha256_file(ROOT/name) == digest, name
    assert sha256_file(ROOT/report["config"]["previous_study"]) == report["previous_study_sha256"]


def test_artifacts_are_bounded_current_and_explicit_about_partial_agreement(report):
    previous = json.loads((ROOT/report["config"]["previous_study"]).read_text())
    files = render(report, previous)
    assert len(files) == 8
    for name, value in files.items():
        assert (ROOT/OUT/name).read_bytes() == value.encode(), name
        if name.endswith(".svg"):
            root = ET.fromstring(value)
            assert float(root.attrib["width"])*float(root.attrib["height"]) <= 1_600_000
            assert report["source_layout_report_sha256"] in value
    page = files["index.html"]
    assert 'lang="zh-Hant"' in page and "尚未採用" in page
    assert "沒有整體風水／施工通過結論" in page
    assert "inputs/private/b-claude-round3-20261106" in page

"""Targeted failure/geometry checks for B round3; no cloud, browser or 3D runtime."""
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from shapely.geometry import Polygon

import house_design.b_claude_round3 as round3
from house_design.b_claude_round3 import CONFIG, OUT, build, check_public_shaft, laundry_screen
from house_design.b_fengshui_strict import area_shape
from house_design.contracts import ContractError, sha256_file
from scripts.export_b_claude_round3 import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_changed_parent_bytes_stop_the_build(tmp_path):
    c = json.loads((ROOT/CONFIG).read_text())
    c["pinned_sources"] = {"parent.json": "0"*64}
    (tmp_path/"inputs").mkdir()
    (tmp_path/CONFIG).write_text(json.dumps(c))
    (tmp_path/"parent.json").write_text("{}")
    with pytest.raises(ContractError, match="round3 source changed: parent.json"):
        build(tmp_path)


def test_exact_response_archive_matches_import_provenance(report):
    p = report["response_provenance"]
    assert p["archive_method"] == "exact-response-file-bytes"
    assert all(p["checks"].values())
    assert sha256_file(ROOT/p["response_archive"]) == p["response_sha256"]
    assert sha256_file(ROOT/p["original_prompt_file"]) == p["prompt_sha256"]
    assert p["elapsed_seconds"] == 801.48


def test_changing_a_family_rule_cannot_inherit_owner_confirmation(monkeypatch):
    original_reader = round3.read_json

    def changed_reader(path):
        data = original_reader(path)
        if Path(path) == ROOT/CONFIG:
            data["owner_questions"][1]["answer"] = True
        return data

    monkeypatch.setattr(round3, "read_json", changed_reader)
    with pytest.raises(ContractError, match="three recorded owner answers"):
        build(ROOT)


def test_both_versions_fill_the_same_rear_block_without_borrowing_area(report):
    for v in report["variants"]:
        assert v["partition"]["gap_or_outside_sqm"] == v["partition"]["overlap_sqm"] == 0
        assert sum(r["nominal_area_sqm"] for r in v["rooms"]) == pytest.approx(37.56)
        assert v["current_inset_case"]["bedroom"] == pytest.approx(20.2261)
        assert v["current_inset_case"]["private_bath"] == pytest.approx(4.7124)
        assert v["bedroom_bodies_inside_115"] is v["bedroom_operations_inside_115"] is True
        assert v["route"]["all_inside_115"] and v["route"]["body_hits"] == []


def test_whole_use_projections_and_original_size_bodies_stay_protected(report):
    for v in report["variants"]:
        assert v["bedroom_over_protected_sqm"] == 0
        assert v["bed_over_palanquin_sqm"] == pytest.approx(3.6)  # Allowed by the owner's new answer, not ignored.
        assert all(w["over_protected_sqm"] == w["over_palanquin_sqm"] == 0 for w in v["wet_projection"])
        sizes = {i["id"]: sorted(i["rect_mm"][2:]) for i in v["rooms"][0]["furniture"]}
        assert sizes == {"bed": [1800, 2000], "wardrobe": [600, 1800], "vanity": [500, 1200]}
        for r in v["rooms"][2:]:
            sizes = {i["id"]: sorted(i["rect_mm"][2:]) for i in r["furniture"]}
            assert sizes["toilet"] == [450, 700] and sizes["shower"] == [900, 900]
            assert sizes["basin"] == ([450, 600] if r["id"] == "public-bath" else [550, 900])


def test_shaft_deducted_instead_of_claiming_area_unchanged(report):
    v = report["variants"][1]
    area = v["public_area_accounting"]
    assert area["outline_finished_estimate_sqm"] == pytest.approx(4.5067)
    assert area["shaft_deduction_sqm"] == pytest.approx(.04)
    assert area["after_shaft_estimate_sqm"] == pytest.approx(4.4667)
    shaft = v["shaft"]
    assert shaft["inside_finished"] and not shaft["arrival_hit"]
    assert shaft["body_hits"] == shaft["operation_hits"] == []
    assert shaft["distance_to_backing_polygon_mm"] == pytest.approx((115**2+185**2)**.5)
    assert shaft["shower_to_backing_mm"] == 315
    assert shaft["actual_pipe_pack"] is shaft["inspection_access"] is None


def test_negative_shaft_in_shower_is_reported_as_collision(report):
    room = report["variants"][1]["rooms"][2]
    shower = next(i for i in room["furniture"] if i["id"] == "shower")["rect_mm"]
    checked = check_public_shaft(room, [shower[0]+100, shower[1]+100, 200, 200])
    assert checked["body_hits"] == ["shower"]
    checked = check_public_shaft(room, [1500, 11550, 200, 200])
    assert checked["arrival_hit"] is True


def test_fixture_bodies_and_operations_not_silently_overlapped(report):
    for v in report["variants"]:
        for r in v["rooms"][2:]:
            screen = r["screen"]
            assert screen["body_hits"] == screen["operation_body_hits"] == screen["inside_arrival_hits"] == []
            assert screen["all_listed_inside"] is screen["inside_arrival_contained"] is True
            assert screen["shared_operation_pairs"]


def test_front_original_collision_and_repair_are_both_visible(report):
    stack = report["stack_and_entry"]
    old = stack["original_front_washer_conflict"]
    assert old["shaft_washer_overlap_sqm"] == pytest.approx(.038)
    rear, front = stack["options"]
    assert len(rear["states"]) == len(front["states"]) == 3
    for state in front["states"]:
        c = state["laundry_check"]
        assert c["relocated"] and c["washer_and_operation_inside_115"]
        assert c["washer_rect_mm"][2:] == old["washer_rect_mm"][2:] == [650, 650]
        assert c["washer_rect_mm"][0]-old["washer_rect_mm"][0] == 990
        assert c["shaft_washer_overlap_sqm"] == c["shaft_washer_operation_overlap_sqm"] == 0
        assert c["door_washer_body_overlap_sqm"] == 0
        assert c["door_washer_operation_overlap_sqm"] == pytest.approx(.44525)
        assert c["shaft_other_body_hits"] == c["fixed_body_hits"] == []
        assert not c["washer_operation_hits_sink_body"] and not c["sink_operation_hits_washer_body"]
    assert all(s["laundry_check"]["shaft_body_hits"] == [] for s in rear["states"])


def test_reverting_only_relocated_washer_restores_real_conflict(report):
    strict = json.loads((ROOT/report["config"]["strict_report"]).read_text())
    floor = strict["options"][1]["states"][0]["floor1"]
    c = laundry_screen(floor, report["stack_and_entry"]["shaft_absolute_mm"],
        report["config"]["codex_front_laundry_repair"], relocate=False)
    assert c["shaft_washer_overlap_sqm"] > 0


def test_corrected_bed_door_distance_and_conditional_handle_cases(report):
    d = report["door_and_ac"]
    assert d["bed_leaf_x_gap_mm"] == 620 and d["bed_leaf_y_projection_gap_mm"] == 15
    assert d["bed_leaf_plan_distance_mm"] == pytest.approx((620**2+15**2)**.5)
    assert d["finished_rear_to_leaf_budget_mm"] == 55
    assert d["leaf_95mm_includes_handle"] is None
    assert [r["remaining_mm"] for r in d["hypothetical_extra_handle_cases"]] == [55, 25, 0, -20]
    assert [r["old_ac_vertical_overlap_mm"] for r in d["height_cases"]] == [0, 0, 50]
    assert all(r["new_ac_plan_overlap_sqm"] == 0 for r in d["height_cases"])
    assert d["leaf_window_x_projection_overlap_mm"] == 380


def test_right_wall_ac_contains_only_a_box_not_inherited_engineering(report):
    v = report["variants"][1]
    ac = v["rooms"][0]["hvac_candidate"]
    assert v["bedroom_hvac_contained"]
    assert sorted(ac["rect_mm"][2:]) == [280, 950] and ac["height_mm"] == 280
    assert ac["route"] is ac["manual"] is None
    assert report["door_and_ac"]["right_ac_to_window_plan_distance_mm"] > 0
    assert v["third_floor_rooms"][0]["hvac_candidate"]["id"] == "B-AC04"


def test_area_limits_are_valid_at_critical_points_without_forged_tolerance(report):
    v = report["variants"][1]
    shape = Polygon(v["rooms"][0]["polygon_mm"])
    critical = report["area_limits"]["shift_cases"][1]["bedroom_20_critical_inset_mm"]
    assert shape.buffer(-(critical-.01), join_style=2).area > 20e6
    assert shape.buffer(-(critical+.01), join_style=2).area < 20e6
    assert report["area_limits"]["whole_design_tolerance_mm"] is None
    largest = v["largest_axis_rectangle"]
    assert largest["area_sqm"] == pytest.approx(14.4231)
    assert shape.buffer(-115, join_style=2).covers(area_shape(largest["rect_mm"]))


def test_conditional_area_bound_and_unfinished_alternative_not_approval(report):
    bound = report["area_limits"]["conditional_bound"]
    assert bound["minimum_gross_sum_sqm"] == pytest.approx(35.37123909)
    assert bound["minimum_shortfall_sqm"] == pytest.approx(1.05923909)
    assert "固定" in bound["assumptions"] and "不是現地無法建造" in bound["scope"]
    alt = report["area_limits"]["two_bath_targets_area_only"]
    assert alt["areas_115_sqm"]["bedroom"] == pytest.approx(18.238)
    assert alt["public_after_same_0_04_shaft_sqm"] == pytest.approx(4.96075)
    assert alt["furnished"] is alt["whole_route_checked"] is alt["ready_for_adoption"] is False


def test_owner_answers_are_recorded_but_not_expanded_to_other_requirements(report):
    answers = report["owner_questions"]
    assert len(answers) == 3 and all(a["answer"] is False and a["status"] == "owner-confirmed" for a in answers)
    source = json.loads((ROOT/report["config"]["owner_answers_reference"]).read_text())
    assert source["reply_exact"] == "1.否 2. 否 3. 否"
    assert source["answers"] == [{"id": a["id"], "question": a["question"], "answer": False} for a in answers]
    assert report["original_targets_sqm"] == {"bedroom_target": 20, "public_bath_target": 5, "public_bath_min": 3.6,
        "private_bath_target": 6, "private_bath_min": 4.5}
    assert report["all_requirements_met"] is report["adopted"] is report["full_consensus"] is False
    ledger = {r["id"]: r["state"] for r in report["agreement_log"]}
    assert ledger["AGREE-100"] == "both-models-research-agreement"
    assert ledger["CODEX-WASHER"] == "codex-only-deterministic-repair"
    assert ledger["CODEX-AC"] == "codex-only-candidate"


def test_rear_front_and_third_floor_roof_conditions_remain_independent(report):
    rear, front = report["stack_and_entry"]["options"]
    assert rear["1360_segment_required_for_direct_rear_entry"] is False
    assert rear["rear_nominal_door_mm"] == 1960 and front["rear_nominal_door_mm"] is None
    assert front["front_clear_if_total_frame_230_mm"] == 1500
    assert front["public_bath_over_front_segments_sqm"] == pytest.approx(3.15)
    for o in [rear, front]:
        assert o["family_rule_above_carry_route"].startswith("owner-does-not-prohibit")
        assert o["palanquin_required_in_shrine"] is o["bedroom_above_storage_prohibited"] is False
        assert o["shaft_over_roof_protected_sqm"] == 0 and o["roof_vent_terminal"] is None
        assert o["rear_alley_legal_access"] == "unknown"
    for v in report["variants"]:
        assert v["third_floor_rooms"][-1]["id"] == "rear-dry"
        assert v["third_floor_rooms"][-1]["furniture"] == []
        assert v["public_exterior_window"]["owner_exterior_window_preference_met"] is False


def test_current_artifacts_and_protected_controls_are_source_bound(report):
    files = render(report)
    assert len(files) == 9
    manifest = json.loads(files["artifact-manifest.json"])
    for name, data in files.items():
        assert (ROOT/OUT/name).read_bytes() == data.encode(), name
        if name in manifest["artifacts"]:
            assert hashlib.sha256(data.encode()).hexdigest() == manifest["artifacts"][name]
        if name.endswith(".svg"):
            svg = ET.fromstring(data)
            assert float(svg.attrib["width"])*float(svg.attrib["height"]) <= 1_600_000
            assert report["report_hash"] in data and report["source_layout_report_sha256"] in data
    for name, digest in report["source_hashes"].items():
        assert sha256_file(ROOT/name) == digest, name
    protected = json.loads((ROOT/report["config"]["protected_controls"]).read_text())
    assert report["protected_controls_unchanged"] == len(protected["hashes"]) == 149
    for name, digest in protected["hashes"].items():
        assert sha256_file(ROOT/name) == digest, name
    page = files["index.html"]
    assert "尚未採用" in page and "沒有整體風水或施工通過結論" in page
    assert "公衛目前沒有直接外窗" in (ROOT/"Docs/b-claude-round3-v1.md").read_text()
    assert "沒有直接外窗" in page and "本輪答覆" in page and "否" in page

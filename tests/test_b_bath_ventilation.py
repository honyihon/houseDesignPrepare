"""Bounded geometry/contract checks; no airflow simulation, browser or cloud calls."""
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

import house_design.b_bath_ventilation as ventilation
from house_design.b_bath_ventilation import CONFIG, OUT, bath_screen, build, door_bed_screen, duct_path, floor_screen
from house_design.b_fengshui_strict import area_shape
from house_design.contracts import ContractError, sha256_file, stable_hash
from scripts.export_b_bath_ventilation import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_changed_parent_bytes_stop_build_before_geometry(tmp_path):
    c = json.loads((ROOT/CONFIG).read_text())
    c["pinned_sources"] = {"parent.json": "0"*64}
    (tmp_path/"inputs").mkdir()
    (tmp_path/CONFIG).write_text(json.dumps(c))
    (tmp_path/"parent.json").write_text("{}")
    with pytest.raises(ContractError, match="ventilation source changed"):
        build(tmp_path)


def test_floor_height_assumption_cannot_silently_disagree_with_source(monkeypatch):
    original = ventilation.read_json

    def changed(path):
        c = original(path)
        if Path(path) == ROOT/CONFIG:
            c["floor_base_mm"]["floor-3"] += 200
        return c

    monkeypatch.setattr(ventilation, "read_json", changed)
    with pytest.raises(ContractError, match="floor levels do not match"):
        build(ROOT)


def test_both_layouts_partition_same_rear_block_and_preserve_protection(report):
    for o in report["options"]:
        for f in o["floors"]:
            s = f["screen"]
            assert s["partition_gap_or_outside_sqm"] == s["partition_overlap_sqm"] == 0
            assert s["master_over_protected_sqm"] == 0
            assert s["master_bodies_and_operations_contained"]
            assert s["reservations_contained"]
            assert s["reservation_body_hits"] == s["reservation_operation_hits"] == []
            assert all(w["protected_overlap_sqm"] == w["storage_overlap_sqm"] == 0 for w in s["wet_projection"])
            assert s["route"]["all_inside_115"]
            assert s["route"]["body_hits"] == s["route"]["enclosure_hits"] == []
            assert s["route"]["actual_whole_route"] == "unknown"


def test_shaft_area_not_hidden_and_twenty_square_metres_is_fragile(report):
    m, w = report["options"]
    assert m["master_after_reservations_sqm"] == pytest.approx(20.0761)
    assert w["master_after_reservations_sqm"] == pytest.approx(16.0889)
    assert m["floors"][0]["screen"]["reserved_enclosure_sqm"] == pytest.approx(.15)
    assert w["floors"][0]["screen"]["reserved_enclosure_sqm"] == pytest.approx(.09)
    assert m["public_after_sewer_sqm"] == pytest.approx(4.4667)
    assert m["private_after_sewer_sqm"] == pytest.approx(4.7124)
    assert w["public_after_sewer_sqm"] == pytest.approx(4.7124)
    assert w["private_after_sewer_sqm"] == pytest.approx(4.5149)


def test_bigger_enclosure_loses_master_target_and_blocks_local_route(report):
    m = report["options"][0]
    protection = unary_union([Polygon(p) for p in report["protected_polygons_mm"]])
    f = m["floors"][0]
    s = floor_screen(f["rooms"], [[1400, 13600, 1200, 600]], f["screen"]["route"]["points_mm"],
        {"public-bath", "private-bath"}, protection, area_shape(report["palanquin_rect_mm"]))
    assert s["master_after_enclosure_sqm"] < 20
    assert s["route"]["enclosure_hits"]


def test_independent_ducts_have_real_budget_and_do_not_inherit_performance(report):
    m = report["options"][0]
    assert m["two_pipe_budgets_contained"] and not m["two_pipe_budgets_overlap"]
    assert len(m["ducts"]) == 2
    assert [d["centerline_length_mm"] for d in m["ducts"]] == [8905, 6155]
    assert m["ducts"][0]["points_mm"][-1][:2] != m["ducts"][1]["points_mm"][-1][:2]
    assert m["separate_from_sewage_and_other_bath_exhaust"] is True
    for o in report["options"]:
        assert o["roof_enclosure_outdoor_unit_hits"] == []
        assert o["roof_weatherhood_size_and_service_clearance"] is None
        for d in o["ducts"]:
            assert d["outer_plan_budget_width_mm"] == 175
            assert d["protected_overlap_sqm"] == d["storage_projection_overlap_sqm"] == 0
            assert d["no_pipe_strip_overlap_sqm"] == d["sewage_shaft_overlap_sqm"] == 0
            assert d["enclosure_in_model_roof_outdoor"] is True
            assert d["fan_model"] is d["pressure_loss_pa"] is d["as_built_length_mm"] is None
            assert d["wall_slab_penetration_approval"] == d["roof_terminal_approval"] == "unknown"


@pytest.mark.parametrize("point,expected", [
    ([3000, 12000], "protected_overlap_sqm"),
    ([2000, 16000], "storage_projection_overlap_sqm"),
    ([2400, 13000], "no_pipe_strip_overlap_sqm"),
    ([2400, 13250], "sewage_shaft_overlap_sqm"),
])
def test_route_crossing_forbidden_budget_cannot_retain_clear(report, point, expected):
    protection = unary_union([Polygon(p) for p in report["protected_polygons_mm"]])
    d = duct_path([[*point, 6500], [point[0]+100, point[1], 6500], [point[0]+100, point[1], 10600]],
        125, 25, protection, area_shape(report["palanquin_rect_mm"]), area_shape([2325, 12455, 200, 700]),
        area_shape([2325, 13155, 200, 200]), [1600, 13600, 500, 300], area_shape([0, 11370, 2400, 6260]))
    assert d[expected] > 0


def test_rear_public_bath_arrives_from_public_corridor_without_entering_master(report):
    o = report["options"][1]
    assert o["public_corridor_nominal_width_mm"] == 1330
    assert o["public_corridor_width_if_115_each_mm"] == 1100
    assert all(v for k, v in o["door_arrivals"].items() if k != "fixed_body_hits")
    assert o["door_arrivals"]["fixed_body_hits"] == []
    r = next(r for r in o["floors"][0]["rooms"] if r["id"] == "public-bath")
    assert r["doors"][0]["a"] == [4770, 14880]
    assert r["outside_approach_mm"] == [4885, 13865, 900, 900]
    assert r["window"]["a"] == [4750, 17630] and r["window"]["b"] == [5650, 17630]


def test_rear_window_fixtures_keep_full_sizes_and_report_sequential_use(report):
    o = report["options"][1]
    for r in o["floors"][0]["rooms"]:
        if r["id"] not in {"public-bath", "private-bath"}:
            continue
        sizes = {i["id"]: sorted(i["rect_mm"][2:]) for i in r["furniture"]}
        assert sizes["toilet"] == [450, 700] and sizes["shower"] == [900, 900]
        assert sizes["basin"] == ([550, 900] if r["id"] == "private-bath" else [450, 600])
        s = r["screen"]
        assert s["bodies_inside"] is s["operations_inside"] is s["arrival_inside"] is True
        assert s["body_hits"] == s["operation_other_body_hits"] == s["arrival_body_hits"] == s["shaft_hits"] == []
        assert not s["shaft_arrival_hit"] and s["shared_operation_pairs"]
        assert r["actual_product_pack"] is None
    master = o["floors"][0]["rooms"][0]
    assert {i["id"]: sorted(i["rect_mm"][2:]) for i in master["furniture"]} == {
        "bed": [1800, 2000], "wardrobe": [600, 1800], "vanity": [500, 1200]}


def test_private_door_shift_into_sewage_shaft_changes_arrival_result(report):
    o = report["options"][1]
    private = json.loads(json.dumps(next(r for r in o["floors"][0]["rooms"] if r["id"] == "private-bath")))
    private["inside_approach_mm"][0] += 20
    assert bath_screen(private, o["retained_sewer_shaft_mm"])["shaft_arrival_hit"] is True


def test_third_floor_does_not_gain_second_bath_or_inherit_wrong_ac(report):
    m, w = report["options"]
    for o in [m, w]:
        rooms = o["floors"][1]["rooms"]
        assert sum(r["id"] in {"private-bath", "public-bath"} for r in rooms) == 1
    assert w["old_master_ac_would_be_in_public_corridor"] is True
    assert w["floors"][0]["rooms"][0]["hvac_candidate"] is None
    assert w["floors"][1]["rooms"][0]["hvac_candidate"] is None
    assert m["floors"][0]["rooms"][0]["hvac_candidate"]["rect_mm"] == [2875, 13095, 950, 280]
    assert m["hvac_checks"]["body_inside_115"]
    assert m["hvac_checks"]["new_nominal_airflow_strip_bed_overlap_sqm"] == 0
    assert m["hvac_checks"]["exhaust_plan_overlap_sqm"] == 0
    assert m["hvac_checks"]["refrigerant_and_condensate_route"] is None


def test_door_bed_projection_regression_not_confused_with_leaf_collision(report):
    m, w = report["options"]
    assert m["door_bed"]["bed_overlap_sqm"] == 0
    assert m["door_bed"]["actual_3d_and_diagonal_sightlines"] == "unknown"
    assert w["door_bed"]["bed_overlap_sqm"] == pytest.approx(1.53)
    assert w["door_bed"]["status"] == "unresolved-door-projects-toward-bed"
    assert w["ready_for_adoption"] is False
    parent = json.loads((ROOT/report["config"]["parent_report"]).read_text())
    prior = parent["variants"][1]
    assert door_bed_screen(prior["rooms"][0], prior["rooms"][-1])["bed_overlap_sqm"] > 0


def test_ventilation_calculations_are_assumptions_not_fan_certification(report):
    flow = report["airflow"]
    assert flow["volume_estimate_m3"] == pytest.approx(10.72008)
    assert [r["delivered_q_m3_h"] for r in flow["ach_cases"]] == [85.761, 107.201, 128.641]
    case = next(c for c in flow["velocity_cases"] if c["diameter_mm"] == 125)
    assert case["velocity_m_s"] == pytest.approx(2.71624436)
    assert "不是本案法定標準" in flow["design_basis"]
    assert flow["delivered_airflow_verified"] is None
    assert flow["actual_free_air_rating_acceptable_as_design"] is False


def test_exterior_window_rights_and_all_targets_remain_unapproved(report):
    assert report["side_window"]["legal_opening"] is None
    w = report["options"][1]["candidate_window"]
    assert w["legal_opening"] is w["effective_opening_sqm"] is None
    assert report["original_targets_sqm"]["bedroom_target"] == 20
    assert report["original_targets_sqm"]["public_bath_target"] == 5
    assert report["original_targets_sqm"]["private_bath_target"] == 6
    assert report["decision"]["owner_answer"] is None
    assert all(q["answer"] is False for q in report["owner_ritual_answers"])
    assert report["adopted"] is report["all_requirements_met"] is False
    assert report["professional_approval"] == "unknown"
    assert all(o["claude_status"].startswith("not-reviewed") for o in report["options"])


def test_retained_rear_and_front_three_states_are_byte_bound_to_parent(report):
    parent = json.loads((ROOT/report["config"]["parent_report"]).read_text())
    assert report["first_floor_unchanged"] is True
    for kept, original in zip(report["retained_entries"], parent["stack_and_entry"]["options"], strict=True):
        assert kept["id"] == original["id"]
        assert kept["states"] == ["daily", "ritual", "carry"]
        assert kept["floor1_hashes"] == {s["id"]: stable_hash(s["floor1"]) for s in original["states"]}


def test_artifacts_sources_and_all_controls_match_current_bytes(report):
    files = render(report)
    assert len(files) == 7
    manifest = json.loads(files["artifact-manifest.json"])
    for name, data in files.items():
        assert (ROOT/OUT/name).read_bytes() == data.encode(), name
        if name in manifest["artifacts"]:
            assert hashlib.sha256(data.encode()).hexdigest() == manifest["artifacts"][name]
        if name.endswith(".svg"):
            svg = ET.fromstring(data)
            assert float(svg.attrib["width"])*float(svg.attrib["height"]) <= 1_600_000
            assert report["report_hash"] in data
    for name, digest in report["source_hashes"].items():
        assert sha256_file(ROOT/name) == digest, name
    controls = json.loads((ROOT/report["config"]["protected_controls"]).read_text())
    assert report["protected_controls_unchanged"] == len(controls["hashes"]) == 149
    for name, digest in controls["hashes"].items():
        assert sha256_file(ROOT/name) == digest, name
    page = files["index.html"]
    assert "尚未採用" in page and "一樓有窗公衛" in page
    assert "不是法定換氣標準" in page and "不能只看無管路時的最大風量" in page

"""Small geometry/numerics regressions for B detail; no CFD, browser or runtime."""
import copy
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

import house_design.b_ventilation_detail as detail
from house_design.b_ventilation_detail import (
    CONFIG,
    OUT,
    assembly_cases,
    build,
    count_bends,
    independent_duct_collisions,
    pressure_cases,
)
from house_design.contracts import ContractError, sha256_file, stable_hash
from scripts.export_b_ventilation_detail import builder_rows, render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_changed_input_evidence_stops_build(tmp_path):
    cfg = json.loads((ROOT/CONFIG).read_text())
    cfg["pinned_sources"] = {"parent.json": "0"*64}
    (tmp_path/"inputs").mkdir()
    (tmp_path/CONFIG).write_text(json.dumps(cfg))
    (tmp_path/"parent.json").write_text("{}")
    with pytest.raises(ContractError, match="vent detail source changed"):
        build(tmp_path)


def test_inconsistent_diameter_does_not_mix_pressure_and_geometry(monkeypatch):
    original = detail.read_json

    def changed(path):
        cfg = original(path)
        if Path(path) == ROOT/CONFIG:
            cfg["pressure_sensitivity"]["diameter_mm"] = 150
        return cfg

    monkeypatch.setattr(detail, "read_json", changed)
    with pytest.raises(ContractError, match="budgets disagree"):
        build(ROOT)


def test_makeup_is_calculated_from_free_area_not_gross_opening(report):
    m = report["makeup"]
    assert [r["ideal_area_sqm"] for r in m["door_undercuts"]] == [.009, .0135, .018]
    assert [r["velocity_m_s"] for r in m["door_undercuts"]] == pytest.approx([3.7037037, 2.4691358, 1.8518519])
    assert m["nominal_transfer_opening_sqm"] == .08
    assert [r["assumed_free_area_sqm"] for r in m["transfer_free_area_cases"]] == pytest.approx([.036, .048])
    assert [r["velocity_m_s"] for r in m["transfer_free_area_cases"]] == pytest.approx([.9259259, .6944444])
    assert m["actual_free_area_sqm"] is m["actual_pressure_loss_pa"] is None
    assert m["outdoor_fresh_air_verified"] is m["closed_door_airflow_verified"] is False
    assert "獨立乾保護室" in m["excluded_sources"] and "樓梯" in m["excluded_sources"]


def test_revised_routes_include_roof_offsets_without_crossing_protected_use(report):
    g = report["geometry"]
    assert [d["centerline_length_mm"] for d in g["ducts"]] == [9260, 6610]
    assert all(count_bends(d["points_mm"]) == 7 for d in g["ducts"])
    assert g["new_makeup_to_extract_plan_mm"] > g["old_makeup_to_extract_plan_mm"]
    assert g["short_circuit_prevention_verified"] is None
    assert g["interior_branch_over_bed_sqm"] == [0, 0]
    for d in g["ducts"]:
        assert d["protected_overlap_sqm"] == d["storage_projection_overlap_sqm"] == 0
        assert d["no_pipe_strip_overlap_sqm"] == d["sewage_shaft_overlap_sqm"] == 0
        assert d["pressure_loss_pa"] is d["fan_model"] is None
        assert d["roof_terminal_approval"] == "unknown"
    assert g["independent_duct_rectangular_budget_hits"] == []


def test_3d_budget_rejects_real_crossing_but_not_same_plan_different_height():
    a = {"floor": "a", "outer_plan_budget_width_mm": 175, "points_mm": [[0, 0, 1000], [1000, 0, 1000]]}
    b = {"floor": "b", "outer_plan_budget_width_mm": 175, "points_mm": [[500, -500, 2000], [500, 500, 2000]]}
    assert independent_duct_collisions([a, b]) == []
    b["points_mm"] = [[500, -500, 1000], [500, 500, 1000]]
    assert independent_duct_collisions([a, b])[0]["rectangular_budget_overlap_mm3"] > 0


@pytest.mark.parametrize("points", [
    [[0, 0, 0], [100, 100, 0]],
    [[0, 0, 0], [0, 0, 0]],
])
def test_diagonal_or_zero_duct_not_silently_counted_as_an_axis_bend(points):
    with pytest.raises(ContractError, match="nonzero axis-aligned"):
        count_bends(points)


def test_roof_hood_and_service_reservations_are_separate_unapproved_products(report):
    g = report["geometry"]
    assert g["old_roof_riser_centers_separation_mm"] == 250
    assert g["roof_centers_separation_mm"] == 1000
    assert g["roof_reservation_overlap_sqm"] == g["roof_service_overlap_sqm"] == 0
    for row in g["roof_terminal_rows"]:
        assert row["nominal_box_inside_roof"] and row["service_inside_roof"]
        assert row["terminal_over_protected_sqm"] == row["service_over_protected_sqm"] == 0
        assert row["terminal_over_storage_sqm"] == 0 and row["known_outdoor_unit_hits"] == []
        assert row["actual_hood_product_and_approach"] is None


def test_servicing_loses_route_access_instead_of_claiming_all_states_clear(report):
    s = report["geometry"]["service"]
    assert s["fan_plan_inside_bath"] is s["hatch_inside_bath"] is s["ladder_inside_bath"] is True
    assert s["fan_or_hatch_body_hits"] == s["ladder_body_hits"] == s["shaft_service_fixed_body_hits"] == []
    assert s["shaft_service_inside_master_115"] is True
    assert s["shaft_service_route_overlap_sqm"] == pytest.approx(.21)
    assert s["actual_product_removal_and_safe_ladder"] is None


def test_pipe_pack_requires_real_wall_allowance_and_reanchoring(report):
    cases = report["assembly"]["enclosure_cases"]
    base = {r["wall_each_assumption_mm"]: r for r in cases[0]["wall_pack_cases"]}
    assert base[50]["inner_width_mm"] == 400 and base[50]["inner_depth_mm"] == 200
    assert base[50]["width_margin_mm"] == 0 and base[50]["reanchored_pipe_pack_fits"] is True
    assert base[75]["depth_margin_mm"] == -25 and base[75]["reanchored_pipe_pack_fits"] is False
    assert all(r["actual_fire_acoustic_and_access_pack"] is None for r in base.values())
    assert report["assembly"]["selected_enclosure"] is None


def test_enlargement_recalculates_master_instead_of_borrowing_floor_area(report):
    cases = report["assembly"]["enclosure_cases"]
    assert [r["master_after_sqm"] for r in cases] == pytest.approx([20.0761, 20.0336, 19.9861])
    assert [r["meets_original_master_20"] for r in cases] == [True, True, False]
    assert not any(r["selected"] for r in cases)
    parent = json.loads((ROOT/report["config"]["parent_report"]).read_text())
    cfg = copy.deepcopy(report["config"])
    cfg["assembly"]["enclosure_cases_mm"] = [[4000, 13095, 700, 500]]
    result = assembly_cases(parent, cfg)
    assert result["enclosure_cases"][0]["master_after_sqm"] < cases[-1]["master_after_sqm"]
    assert result["selected_enclosure"] is None


def test_beam_conflict_is_explicitly_conditional(report):
    a = report["assembly"]
    assert a["duct_bottom_relative_z_mm"] == 2462.5
    assert a["duct_top_relative_z_mm"] == 2637.5
    assert a["gap_above_2400_ceiling_mm"] == 62.5
    cases = {r["assumed_total_depth_from_next_floor_mm"]: r for r in a["beam_cases"]}
    assert cases[300]["rectangular_budget_conflict_if_beam_crosses"] is False
    assert cases[400]["gap_above_duct_mm"] == -37.5
    assert cases[400]["rectangular_budget_conflict_if_beam_crosses"] is True
    assert a["actual_beam_positions_and_depths"] is a["actual_slab_penetrations"] is None


def test_pressure_scales_as_q_squared_for_the_same_assumed_coefficients(report):
    for d in report["pressure_sensitivity"]:
        cases = {r["q_m3_h"]: r for r in d["cases"]}
        for side in ["assumed_low", "assumed_high"]:
            assert cases[120][side]["sum_pa"]/cases[90][side]["sum_pa"] == pytest.approx((120/90)**2)
            assert cases[130][side]["sum_pa"] > cases[120][side]["sum_pa"]
        assert d["actual_required_static_pressure_pa"] is d["actual_fan_model"] is None
        assert "補氣端壓損" in d["exclusions"]
    new_path = copy.deepcopy(report["geometry"]["ducts"][0])
    new_path["centerline_length_mm"] += 5000
    new = pressure_cases(new_path, report["config"])
    assert new["cases"][1]["assumed_low"]["sum_pa"] > report["pressure_sensitivity"][0]["cases"][1]["assumed_low"]["sum_pa"]


def test_frozen_layouts_owner_answers_and_original_goals_not_promoted_to_adoption(report):
    parent = json.loads((ROOT/report["config"]["parent_report"]).read_text())
    assert stable_hash(report["geometry"]["floors"]) == stable_hash(parent["options"][0]["floors"])
    assert report["retained_entries"] == parent["retained_entries"]
    assert len(report["retained_entries"]) == 2
    assert all(len(o["states"]) == 3 for o in report["retained_entries"])
    assert report["owner_no_window_decision"]["owner_answer"] is None
    assert all(q["answer"] is False for q in report["owner_ritual_answers"])
    assert report["original_targets_sqm"] == parent["original_targets_sqm"]
    assert report["adopted"] is report["all_requirements_met"] is report["owner_requirement_changes"] is False
    assert report["professional_approval"] == "unknown" and report["claude_status"] == "no-new-discussion-this-turn"
    assert report["original_1f_and_3d_unchanged"] is True


def test_builder_table_leaves_real_quotes_and_models_unknown(report):
    rows = builder_rows(report)
    assert len(rows) == 8
    assert all(r["model"] is r["actual_dimensions"] is r["quote_twd"] is r["evidence"] is None for r in rows)
    assert all(r["approval"] == "unknown" for r in rows)
    assert any("標配折抵" in r["required_reply"] for r in rows)


def test_current_source_hashes_artifacts_and_149_controls(report):
    files = render(report)
    assert len(files) == 8
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
    assert "尚未採用" in files["index.html"] and "不是實際壓損上下界" in files["index.html"]

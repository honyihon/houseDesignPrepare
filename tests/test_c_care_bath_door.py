"""Bounded math and source parity only; never a browser or full scene runtime."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from xml.etree import ElementTree as ET

import export_c_care_bath_door as export
import pytest
from bs4 import BeautifulSoup
from lib.model3d_plan import plan_data

from house_design.b32_rear_right import body, paired, rect
from house_design.b32_services import _hits
from house_design.c_care_bath_door import FRACTIONS, SOURCE, STATES, pose, review, translation_sweeps, validate_config
from house_design.c_care_bath_fit import BASE_REPORT, BASE_VIEWER, _frozen_parent
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash


@pytest.fixture(scope="module")
def study():
    return export.build_study()


def states(study, oid="two-panel"):
    return next(o["states"] for o in study["options"] if o["id"] == oid)


def rooms(state, index=0):
    return {r["key"]: r for r in state["plans"]["floors"][index]["rooms"]}


def test_display_v2_does_not_change_any_plan_coordinate_review_or_requirement(study):
    assert study["door_display_revision"] == 2
    assert stable_hash([s["plans"] for o in study["options"] for s in o["states"]]) == "0b3ee55bc52d679955687bede3037c1155740b0d3315dd1a63a1bdbea7830383"
    assert stable_hash([s["review"] for o in study["options"] for s in o["states"]]) == "cd7050cd638eb2c9f9c52ae2489b4d7bd1863e522073bc2ebbd74930679d9c43"
    assert study["requirement_ledger"]["ledger_hash"] == "9442a82de6d4432ef385daaafa52bd9543c8f82c3cd44f53f3284cf62539a0c9"


def test_scope_counts_and_requirements_approvals_are_not_adopted(study):
    assert study["adopted"] is False and study["rendered_qa"] == "not-run"
    assert set(study["professional_status"].values()) == {"unknown"}
    assert [o["id"] for o in study["options"]] == ["single-control", "two-panel"]
    snapshots = [s for o in study["options"] for s in o["states"]]
    assert len(snapshots) == 6 and sum(len(s["plans"]["floors"]) for s in snapshots) == 24
    assert sum(len(f["rooms"]) for s in snapshots for f in s["plans"]["floors"]) == 234
    assert sum(len(r["furniture"]) for s in snapshots for f in s["plans"]["floors"] for r in f["rooms"]) == 300
    ledger = study["requirement_ledger"]
    assert (ledger["canonical_requirements"], ledger["scenario_rows"], ledger["verified_requirements"]) == (66, 40, 0)
    assert ledger["ledger_hash"] == stable_hash({k: v for k, v in ledger.items() if k != "ledger_hash"})
    for scenario in ledger["scenarios"]:
        for row in scenario["rows"]:
            assert row["functional_acceptance"] == row["professional_acceptance"] == "unknown"
            if row["requirement_id"] == "C.floor-1.elder_bath":
                assert "公共直達照服偏好未滿足" in row["note"]


def test_no_furniture_wall_frame_window_or_upper_floor_changes(study):
    _, base = _frozen_parent(ROOT)
    old = rooms(base)
    for option in study["options"]:
        for state in option["states"]:
            current = rooms(state)
            assert {k: rect(r) for k, r in current.items()} == {k: rect(r) for k, r in old.items()}
            for key, room in current.items():
                assert room["furniture"] == old[key]["furniture"]
                assert room["features"].get("window_mm") == old[key]["features"].get("window_mm")
                assert room["features"].get("hvac_units") == old[key]["features"].get("hvac_units")
            assert current["service"] == old["service"] and current["stair1f"] == old["stair1f"]
            assert body(next(i for i in current["elder-bath"]["furniture"] if i["shape"] == "vanity")) == [3715, 13915, 600, 450]
            for index in range(1, 4):
                first, second = copy.deepcopy(state["plans"]["floors"][index]), copy.deepcopy(base["plans"]["floors"][index])
                first.pop("plan_file")
                second.pop("plan_file")
                assert first == second


def test_same_model_plan_and_paired_real_apertures_not_just_width_text(study):
    for option in study["options"]:
        for state in option["states"]:
            actual = plan_data(state["model"])["buildings"][0]
            for floor, ref in zip(actual["floors"], state["plans"]["floors"], strict=True):
                floor["plan_file"] = ref["plan_file"]
            assert actual == state["plans"]
            center = 15025 if option["id"] == "two-panel" else 14825
            assert paired(rooms(state), "elder", "elder-bath", "right", center, 1200)["operation"] == "sliding"


def test_rigid_two_panel_coverage_overlap_and_true_linear_translation():
    cfg = read_json(ROOT / SOURCE)
    closed = pose(cfg, "two-panel", "closed")[0]
    opened = pose(cfg, "two-panel", "open")[0]
    half = pose(cfg, "two-panel", "half")[0]
    assert closed[0]["rect_mm"] == [3775, 14395, 45, 660]
    assert closed[1]["rect_mm"] == [3715, 14995, 45, 660]
    assert sum(closed[0]["rect_mm"][1::2])-closed[1]["rect_mm"][1] == 60
    assert sum(closed[1]["rect_mm"][1::2])-closed[0]["rect_mm"][1] == 1260
    for a, b, middle in zip(closed, opened, half, strict=True):
        assert a["rect_mm"][2:] == b["rect_mm"][2:] == middle["rect_mm"][2:] == [45, 660]
        assert a["height_mm"] == b["height_mm"] == middle["height_mm"] == 2100
        assert b["rect_mm"][1] == (15655 if a["id"] == "bathroom-fast" else 15625)
        assert middle["rect_mm"][1] == (a["rect_mm"][1]+b["rect_mm"][1])/2
    assert [panel["full_travel_mm"] for panel in closed] == [1260, 630]
    assert closed[0]["full_travel_mm"] == 2*closed[1]["full_travel_mm"]
    assert pose(cfg, "single-control", "open")[0][0]["rect_mm"] == [3715, 15425, 95, 1260]


def test_full_sweeps_are_exact_for_every_linear_pose_and_not_only_endpoints():
    cfg = read_json(ROOT / SOURCE)
    for oid in ("single-control", "two-panel"):
        bounds = {s["id"]: s["rect_mm"] for s in translation_sweeps(cfg, oid)}
        for fraction in [0, .1, .25, .4, .5, .7, .9, 1]:
            closed, opened = pose(cfg, oid, "closed")[0], pose(cfg, oid, "open")[0]
            for first, last in zip(closed, opened, strict=True):
                x, y, w, d = first["rect_mm"]
                y += fraction*(last["rect_mm"][1]-y)
                bx, by, bw, bd = bounds[first["id"]]
                assert bx <= x and by <= y and bx+bw >= x+w and by+bd >= y+d


def test_control_exposes_vanity_closed_and_sweep_conflict_and_missing_stop(study):
    for state in states(study, "single-control"):
        detail = state["review"]["door"]
        assert detail["sweep_vs_fixed_conflicts"] == ["bathroom:hits-C:floor-1:elder-bath:furniture:vanity"]
        assert detail["door_sweep_to_vanity_directional_gap_mm"] == -170
        assert detail["rear_parking_after_20mm_stop_mm"] == -20 and detail["stop_inside_assumed_finish"] is False
        assert bool(detail["current_leaf_vs_fixed_conflicts"]) == (state["id"] == "closed")


def test_two_panel_reposition_only_trial_floor_and_clear_original_turn_collision(study):
    for state in states(study):
        detail = state["review"]["door"]
        assert detail["turn_reserve_mm"] == [3880, 14785, 1500, 1800]
        assert detail["turn_circle_mm"] == [4630, 15685, 750]
        assert detail["rescue_board_rotation_mm"] == [3901, 14721, 1898, 1898]
        assert detail["original_turn_position_door_conflicts"]
        assert not detail["turn_coordinate_failures"] and not detail["rescue_board_rotation_failures"]
        assert not detail["sweep_vs_fixed_conflicts"] and not detail["current_leaf_vs_fixed_conflicts"]
        assert detail["door_sweep_to_vanity_directional_gap_mm"] == 30
        assert detail["rear_parking_after_20mm_stop_mm"] == 350
        assert detail["single_at_proposed_aperture_rear_spare_mm"] == -220
        assert detail["operation_requires_empty_sweep"] is True
        assert detail["sweep_vs_entry_routes"]
        assert detail["critical_margins_mm"] == {"entry_to_vanity": 210, "vanity_final_arrival": 0, "transfer_to_vanity": 15, "board_turn_to_folded_seat": 8.5}
        assert detail["actual_product_clear_mm"] is None and detail["old_basin_and_seat_tight_margins_resolved"] is False
        assert detail["independent_dry_turn_floor"] is False and detail["knee_clearance_credit_mm"] == 0
        assert [r["turn_rect_spare_mm"] for r in detail["thickness_sensitivity"]] == [35, 0, -15]


def test_full_open_then_half_and_closed_controls_recompute_all_paths(study):
    for option in study["options"]:
        for state in option["states"]:
            detail = state["review"]["door"]
            expected = 970 if state["id"] == "open" else 0 if state["id"] == "closed" else 485 if option["id"] == "two-panel" else 470
            assert detail["effective_width_assumption_mm"] == expected
            assert not detail["upstream_routes"]["arcade-to-bed"]["coordinate_failures"]
            paths = [*detail["routes"].values(), *detail["helper_routes"].values(), detail["rescue_board_translation"], detail["upstream_routes"]["bed-to-bath"]]
            assert all(bool(r["coordinate_failures"]) == (state["id"] != "open") for r in paths)
            if option["id"] == "two-panel":
                assert detail["routes"]["toilet-transfer"]["points_mm"][0][1] == 15025


@pytest.mark.parametrize("key,value", [("required_clear_mm", 800), ("center_y_mm", 14825), ("nominal_aperture_mm", 1000),
                                      ("inset_each_face_mm", 80), ("height_mm", 1500)])
def test_cannot_change_scope_or_shrink_door_target(key, value):
    cfg = read_json(ROOT / SOURCE)
    cfg[key] = value
    with pytest.raises(ContractError):
        validate_config(cfg)


@pytest.mark.parametrize("key,value", [("panel_length_mm", 300), ("panel_thickness_mm", 10), ("pull_projection_mm", 0),
                                      ("turn_reserve_shift_x_mm", -1), ("board_trial_shift_x_mm", float("nan"))])
def test_cannot_fake_smaller_hardware_to_pass(key, value):
    cfg = read_json(ROOT / SOURCE)
    cfg["telescopic"][key] = value
    with pytest.raises(ContractError):
        validate_config(cfg)


@pytest.mark.parametrize("change", ["leaf-scale", "leaf-state", "pull", "wrong-opening", "room"])
def test_mutated_display_or_unmoved_aperture_rejected(study, change):
    state = copy.deepcopy(states(study)[0])
    cells = rooms(state)
    if change == "leaf-scale":
        cells["elder-bath"]["features"]["care_entry_leaves"][0]["rect_mm"][3] = 200
    elif change == "leaf-state":
        cells["elder-bath"]["features"]["care_entry_leaves"][0]["state"] = "closed"
    elif change == "pull":
        cells["elder-bath"]["features"]["care_door_parts"][-1]["rect_mm"][2] = 1
    elif change == "wrong-opening":
        cells["elder-bath"]["features"]["doors"][0]["ratio"] -= .05
    else:
        cells["elder-bath"]["geometry"]["h_mm"] += 100
    with pytest.raises(ContractError):
        review(state["plans"], read_json(ROOT / SOURCE), read_json(ROOT / "inputs/c-care-bath.json"),
               read_json(ROOT / "inputs/c-care-route.json"), "two-panel", "open")


def test_closed_door_no_longer_hits_basin_and_no_furniture_scaled(study):
    state = states(study)[-1]
    bath = rooms(state)["elder-bath"]
    basin = body(next(i for i in bath["furniture"] if i["shape"] == "vanity"))
    assert all(not _hits(panel["rect_mm"], basin) for panel in bath["features"]["care_entry_leaves"])
    assert set(FRACTIONS) == set(STATES)


def test_generated_html_and_bounded_svg_are_source_bound_and_warning_clear(study):
    assert (ROOT / export.INDEX).read_text() == export.render_index(study)
    soup = BeautifulSoup(export.render_index(study), "html.parser")
    assert "未採用" in soup.select_one("#door-adoption-warning").get_text()
    assert len(soup.select("section[data-option]")) == 2 and len(soup.select("details[data-use-state]")) == 6
    assert "130mm" in soup.get_text() and "180mm會侵入15mm" in soup.get_text()
    for option in study["options"]:
        for state in option["states"]:
            for f in state["plans"]["floors"]:
                svg = ET.parse(ROOT / export.OUT / f["plan_file"]).getroot()
                assert int(svg.get("width")) == 660
                assert svg.get("data-door-option") == option["id"] and svg.get("data-use-state") == state["id"]
                assert not svg.findall('.//{http://www.w3.org/2000/svg}image')
            svg = ET.parse(ROOT / export.OUT / f'{option["id"]}_{state["id"]}_detail.svg').getroot()
            assert int(svg.get("width")) == 780 and int(svg.get("height")) == 810
    assert all(sha256_file(ROOT / p) == digest for p, digest in study["source_hashes"].items())


def test_exporter_only_writes_new_package_not_any_parent(study, tmp_path, monkeypatch):
    protected = {**study["source_hashes"], BASE_REPORT: sha256_file(ROOT / BASE_REPORT), BASE_VIEWER: sha256_file(ROOT / BASE_VIEWER)}
    render = export.render_viewer
    monkeypatch.setattr(export, "render_viewer", lambda current, unused: render(current, ROOT))
    result = export.write_study(study, tmp_path)
    assert result["rendered_qa"] == "not-run"
    assert (tmp_path / export.VIEWER).read_text() == (ROOT / export.VIEWER).read_text()
    assert (tmp_path / export.INDEX).read_text() == export.render_index(study)
    report = read_json(tmp_path / export.OUT / "review.json")
    assert report["report_hash"] == study["report_hash"] and all("model" not in s for o in report["options"] for s in o["states"])
    assert all(p.is_relative_to(tmp_path / export.OUT) or p in [tmp_path / export.INDEX, tmp_path / export.VIEWER]
               for p in tmp_path.rglob("*") if p.is_file())
    assert all(sha256_file(ROOT / p) == digest for p, digest in protected.items())


def test_direct_script_works_in_isolated_python_from_other_directory(tmp_path):
    result = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/export_c_care_bath_door.py"), "--check"],
                            cwd=tmp_path, capture_output=True, text=True, check=True, timeout=5)
    assert json.loads(result.stdout) == {"options": 2, "states": 6, "rendered_qa": "not-run"}

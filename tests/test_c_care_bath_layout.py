"""Small file/math tests only: no scene, browser, full solver or parent build."""
from __future__ import annotations

import copy
import json
from xml.etree import ElementTree as ET

import export_c_care_bath_layout as export
import pytest
from bs4 import BeautifulSoup
from lib.model3d_placement import _door_approach
from lib.model3d_plan import plan_data

from house_design.b32_rear_right import body, paired, rect
from house_design.b32_service_detail import _inside
from house_design.b32_services import _hits
from house_design.c_care_bath import component_box
from house_design.c_care_bath_layout import (
    BASE_REPORT,
    BASE_VIEWER,
    SOURCE,
    frozen_parent,
    review,
    trial_configs,
    validate_config,
)
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash


@pytest.fixture(scope="module")
def study():
    return export.build_study()


def states(study, oid="side-basin"):
    return next(o["states"] for o in study["options"] if o["id"] == oid)


def rooms(state, index=0):
    return {r["key"]: r for r in state["plans"]["floors"][index]["rooms"]}


def test_scope_requirements_and_counts_never_imply_adoption(study):
    assert study["adopted"] is False and study["rendered_qa"] == "not-run"
    assert set(study["professional_status"].values()) == {"unknown"}
    assert [o["id"] for o in study["options"]] == ["door-control", "side-basin"]
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


def test_frozen_parent_verified_and_control_geometry_retained(study):
    parent, baseline = frozen_parent()
    assert study["base_report_hash"] == parent["report_hash"]
    assert study["base_plan_hash"] == stable_hash(baseline["plans"])
    for state in states(study, "door-control"):
        reference = next(s for o in parent["options"] if o["id"] == "two-panel" for s in o["states"] if s["id"] == state["id"])
        for current, old in zip(state["plans"]["floors"], reference["plans"]["floors"], strict=True):
            a, b = copy.deepcopy(current), copy.deepcopy(old)
            for floor in (a, b):
                floor.pop("plan_file")
                for room in floor["rooms"]:
                    room["features"].pop("care_route_overlays", None)
                    room["features"].pop("care_bath_regions", None)
            assert a == b
        assert state["review"]["layout"]["critical_margins_mm"] == reference["review"]["door"]["critical_margins_mm"]


def test_frozen_parent_refuses_stale_source_and_forged_self_hash(monkeypatch):
    import house_design.c_care_bath_layout as module
    original = module.read_json
    for mutation in ("source", "report"):
        def altered(path, mutation=mutation):
            data = original(path)
            if path == ROOT / BASE_REPORT:
                data = copy.deepcopy(data)
                if mutation == "source":
                    data["source_hashes"]["inputs/c-care-bath-door.json"] = "0"*64
                else:
                    data["options"][1]["states"][0]["review"]["door"]["required_clear_mm"] = 700
            return data
        monkeypatch.setattr(module, "read_json", altered)
        with pytest.raises(ContractError, match="Stale frozen|hash mismatch"):
            frozen_parent()


def test_same_source_html_3d_all_floors_and_paired_1200mm_doors(study):
    for option in study["options"]:
        for state in option["states"]:
            actual = plan_data(state["model"])["buildings"][0]
            for a, b in zip(actual["floors"], state["plans"]["floors"], strict=True):
                a["plan_file"] = b["plan_file"]
            assert actual == state["plans"]
            center = 15175 if option["id"] == "side-basin" else 15025
            assert paired(rooms(state), "elder", "elder-bath", "right", center, 1200)["operation"] == "sliding"


def test_no_room_window_outdoor_band_bed_tv_other_furniture_or_upper_changes(study):
    _, baseline = frozen_parent()
    old = rooms(baseline)
    for option in study["options"]:
        for state in option["states"]:
            current = rooms(state)
            assert {k: rect(r) for k, r in current.items()} == {k: rect(r) for k, r in old.items()}
            for key, room in current.items():
                assert room["features"].get("window_mm") == old[key]["features"].get("window_mm")
                if key != "elder-bath":
                    assert room["furniture"] == old[key]["furniture"]
            assert rect(current["elder-bath"]) == [3600, 13800, 2400, 3000]
            assert current["service"] == old["service"] and current["stair1f"] == old["stair1f"]
            for index in range(1, 4):
                a, b = copy.deepcopy(state["plans"]["floors"][index]), copy.deepcopy(baseline["plans"]["floors"][index])
                a.pop("plan_file")
                b.pop("plan_file")
                assert a == b
            washers = [f["id"] for f in state["plans"]["floors"] for r in f["rooms"] for i in r["furniture"] if i["catalog_id"] == "washer"]
            assert washers == ["floor-2"]


def test_rotated_full_size_basin_700mm_operation_and_explicit_off_axis_arrival(study):
    for state in states(study):
        bath = rooms(state)["elder-bath"]
        basin = next(i for i in bath["furniture"] if i["shape"] == "vanity")
        d = state["review"]["layout"]
        assert [basin[k] for k in ("width_mm", "depth_mm", "height_mm")] == [600, 450, 850]
        assert basin["care_bath_wall_hung"] and basin["front_clearance_mm"] == 700
        assert body(basin) == [3715, 13915, 450, 600]
        assert basin["placement"]["rotation_deg"] == 270 and basin["placement"]["wall_anchor"] == "left"
        assert d["vanity_operation_mm"] == [4165, 13915, 700, 600]
        assert d["basin_arrival_rect_mm"] == [4215, 14015, 900, 900]
        assert d["basin_arrival_facing_axis"] == "-x" and d["basin_arrival_lateral_offset_mm"] == 250
        assert not d["centered_basin_arrival_demonstrated"] and d["seated_tap_reach"] == "unknown"
        assert d["centered_basin_control"]["rect_mm"] == [4215, 13765, 900, 900]
        assert set(d["centered_basin_control"]["coordinate_failures"]) == {"outside-assumed-bath", "hits-toilet-arm", "hits-alarm-toilet"}
        assert d["knee_clearance_credit_mm"] == 0 and not d["independent_dry_turn_floor"]
        assert not d["vanity_operation_fixed_conflicts"] and not d["vanity_operation_door_conflicts"]
        assert d["basin_operation_transfer_overlap_sqm"] == .2675
        assert d["simultaneous_basin_and_toilet_transfer"] is False


def test_all_three_improvements_and_remaining_small_gaps_are_honest(study):
    for state in states(study):
        d = state["review"]["layout"]
        assert d["critical_margins_mm"] == {"entry_to_vanity": 210, "vanity_final_arrival": 50,
            "transfer_to_vanity": 165, "board_turn_to_folded_seat": 58.5}
        assert d["additional_margins_mm"] == {"basin_arrival_to_front_finish": 100,
            "basin_arrival_to_raised_arm_y": 32.5, "board_turn_to_toilet_y": 56,
            "board_turn_to_right_rail_x": 18.5, "door_pack_to_turn_reserve": 35}
        assert d["rear_parking_after_20mm_stop_mm"] == 200 and d["door_sweep_to_vanity_directional_gap_mm"] == 30
        assert [r["turn_rect_spare_mm"] for r in d["thickness_sensitivity"]] == [35, 0, -15]
        assert d["directional_20mm_consumption"]["remaining_mm"]["board_turn_to_right_rail_x"] == -1.5
        assert d["construction_release"] is False and d["full_bath_fit_or_care_approval"] == "unknown"
        assert d["selected_product"] is d["actual_product_clear_mm"] is None


def test_alarm_moves_only_as_explicit_candidate_and_old_location_fails_new_operation(study):
    _, baseline = frozen_parent()
    old = rooms(baseline)["elder-bath"]["features"]["care_bath_components"]
    for state in states(study):
        d = state["review"]["layout"]
        for a, b in zip(rooms(state)["elder-bath"]["features"]["care_bath_components"], old, strict=True):
            if a["id"] != "alarm-toilet":
                assert a == b
            else:
                assert a["diameter_mm"] == b["diameter_mm"] == 8
                assert all(x[0]-y[0] == 200 and x[1:] == y[1:] for x, y in zip(a["points_mm"], b["points_mm"], strict=True))
                assert _hits(d["vanity_operation_mm"], component_box(b)[:4])
                assert not _hits(d["vanity_operation_mm"], component_box(a)[:4])


def test_recompute_only_shared_wall_door_approaches_preserve_bedroom_front_entry(study):
    _, baseline = frozen_parent()
    old = rooms(baseline)["elder"]["features"]["reserved_mm"]
    for state in states(study):
        for key in ("elder", "elder-bath"):
            room = rooms(state)[key]
            door = next(d for d in room["features"]["doors"] if d["neighbor"] == rooms(state)["elder-bath" if key == "elder" else "elder"]["id"])
            expected = _door_approach(room["geometry"], door)
            assert any(r["aabb"] == expected for r in room["features"]["reserved_mm"] if r["kind"] == "door-approach")
        actual = rooms(state)["elder"]["features"]["reserved_mm"]
        assert actual[-2] == old[-2]


def test_new_real_door_full_sweeps_stop_and_half_closed_negative_controls(study):
    for option in study["options"]:
        for state in option["states"]:
            d = state["review"]["layout"]
            assert d["effective_width_assumption_mm"] == {"open": 970, "half": 485, "closed": 0}[state["id"]]
            assert not d["sweep_vs_fixed_conflicts"] and not d["sweep_vs_stop_conflicts"]
            assert d["operation_requires_empty_sweep"] and d["sweep_vs_entry_routes"]
            assert not d["upstream_routes"]["arcade-to-bed"]["coordinate_failures"]
            paths = [*d["routes"].values(), *d["helper_routes"].values(), d["rescue_board_translation"], d["upstream_routes"]["bed-to-bath"]]
            assert all(bool(r["coordinate_failures"]) == (state["id"] != "open") for r in paths)
            if option["id"] == "door-control":
                assert bool(d["vanity_operation_door_conflicts"]) == (state["id"] != "open")
                assert bool(d["basin_arrival_coordinate_failures"]) == (state["id"] != "open")
            else:
                assert not d["basin_arrival_coordinate_failures"]
            outlines = {o["id"]: o for o in rooms(state)["elder-bath"]["features"]["care_route_overlays"]}
            assert outlines["basin-arrival"]["blocked"] == bool(d["basin_arrival_coordinate_failures"])
            assert outlines["basin-operation"]["blocked"] == bool(d["vanity_operation_door_conflicts"])
            assert not d["turn_coordinate_failures"] and not d["transfer_coordinate_failures"]
            assert not d["rescue_board_rotation_failures"] and not d["helper_station_failures"]


def test_board_full_diagonal_stays_same_and_connects_shifted_entry_to_new_turn(study):
    for state in states(study):
        d = state["review"]["layout"]
        assert d["rescue_board_rotation_mm"] == [3901, 14671, 1898, 1898]
        assert d["rescue_board_translation"]["body_mm"] == [1800, 600]
        assert d["rescue_board_translation"]["points_mm"] == [[2650, 15115], [4850, 15115], [4850, 15620]]
        assert _inside(d["rescue_board_rotation_mm"], [rect(rooms(state)["elder-bath"])], 115)
        assert d["turn_reserve_mm"] == [3880, 14785, 1500, 1800] and d["turn_circle_mm"] == [4630, 15685, 750]
        assert not d["hardware_sweep_conflicts"]


@pytest.mark.parametrize("key,value", [("required_clear_mm", 800), ("inset_each_face_mm", 80),
    ("vanity", {"rect_mm": [3715, 13915, 350, 500], "rotation_deg": 270, "wall_anchor": "left"}),
    ("door_center_y_mm", 15025), ("alarm_toilet_shift_x_mm", 0)])
def test_config_rejects_shortcuts_and_unreviewed_product_changes(key, value):
    cfg = read_json(ROOT / SOURCE)
    cfg[key] = value
    with pytest.raises(ContractError):
        validate_config(cfg)


@pytest.mark.parametrize("change", ["basin-scale", "wrong-operation", "old-alarm", "door", "leaf", "room", "window", "upper"])
def test_geometry_reviewer_rejects_unsynchronized_or_shrunken_payload(study, change):
    state = copy.deepcopy(states(study)[0])
    current, cfg = rooms(state), read_json(ROOT / SOURCE)
    basin = next(i for i in current["elder-bath"]["furniture"] if i["shape"] == "vanity")
    if change == "basin-scale":
        basin["width_mm"] = 500
    elif change == "wrong-operation":
        basin["placement"]["operation_mm"]["maxX"] -= 100
    elif change == "old-alarm":
        for c in current["elder-bath"]["features"]["care_bath_components"]:
            if c["id"] == "alarm-toilet":
                for point in c["points_mm"]:
                    point[0] -= 200
    elif change == "door":
        current["elder"]["features"]["doors"][-1]["ratio"] -= .05
    elif change == "leaf":
        current["elder-bath"]["features"]["care_entry_leaves"][0]["rect_mm"][3] = 400
    elif change == "room":
        current["elder-bath"]["geometry"]["w_mm"] += 50
    elif change == "window":
        current["elder-bath"]["features"]["window_mm"] = 0
    else:
        state["plans"]["floors"][1]["rooms"][0]["geometry"]["w_mm"] += 100
    dc, bc = trial_configs(cfg, read_json(ROOT / "inputs/c-care-bath-door.json"), read_json(ROOT / "inputs/c-care-bath.json"), "side-basin")
    with pytest.raises(ContractError):
        review(state["plans"], cfg, dc, bc, read_json(ROOT / "inputs/c-care-route.json"), "side-basin", "open", frozen_parent()[1])


def test_saved_html_svg_warning_and_geometry_are_same_source_and_pixel_bounded(study):
    assert (ROOT / export.INDEX).read_text() == export.render_index(study)
    soup = BeautifulSoup(export.render_index(study), "html.parser")
    assert "未採用" in soup.select_one("#layout-adoption-warning").get_text()
    assert len(soup.select("section[data-option]")) == 2 and len(soup.select("details[data-use-state]")) == 6
    for text in ("偏側250mm", "0.2675m²", "18.5mm", "350→200mm", "膝部信用"):
        assert text in soup.get_text()
    for option in study["options"]:
        for state in option["states"]:
            for floor in state["plans"]["floors"]:
                path = ROOT / export.OUT / floor["plan_file"]
                svg = ET.parse(path).getroot()
                assert int(svg.get("width")) == 660 and svg.get("data-layout-option") == option["id"]
                assert svg.get("data-use-state") == state["id"] and "c-care-bath-door-3d.html" not in path.read_text()
            detail = ET.parse(ROOT / export.OUT / f'{option["id"]}_{state["id"]}_detail.svg').getroot()
            assert (detail.get("width"), detail.get("height")) == ("780", "810")
            assert detail.findall('.//{http://www.w3.org/2000/svg}polyline[@data-care-route="basin-arrival"]')
    assert all(sha256_file(ROOT / p) == digest for p, digest in study["source_hashes"].items())


def test_exporter_changes_only_new_comparison_and_preserves_all_frozen_sources(study, tmp_path, monkeypatch):
    protected = {**study["source_hashes"], BASE_REPORT: sha256_file(ROOT / BASE_REPORT), BASE_VIEWER: sha256_file(ROOT / BASE_VIEWER)}
    render = export.render_viewer
    monkeypatch.setattr(export, "render_viewer", lambda current, unused: render(current, ROOT))
    export.write_study(study, tmp_path)
    assert (tmp_path / export.INDEX).read_text() == export.render_index(study)
    assert (tmp_path / export.VIEWER).read_text() == (ROOT / export.VIEWER).read_text()
    report = read_json(tmp_path / export.OUT / "review.json")
    assert report["report_hash"] == study["report_hash"]
    for current, saved in zip(study["options"], report["options"], strict=True):
        for model_state, state in zip(current["states"], saved["states"], strict=True):
            assert "model" not in state
            state["model"] = model_state["model"]
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k not in {"generated_at", "report_hash"}})
    assert all(p.is_relative_to(tmp_path / export.OUT) or p in [tmp_path / export.INDEX, tmp_path / export.VIEWER]
               for p in tmp_path.rglob("*") if p.is_file())
    assert all(sha256_file(ROOT / p) == digest for p, digest in protected.items())


def test_directional_budget_is_not_centered_wheelchair_or_stretchers(study):
    for state in states(study):
        d = state["review"]["layout"]
        assert "不是擔架" in d["rescue_scope"]
        assert d["full_bath_rescue_and_public_caregiver_access"] == "unknown-private-bedroom-access-retained"
        assert "不是同時公差" in d["directional_20mm_consumption"]["scope"]
        assert d["directional_20mm_consumption"]["remaining_mm"]["vanity_final_arrival"] == 30
    saved = json.loads((ROOT / export.OUT / "review.json").read_text())
    assert saved["rendered_qa"] == "not-run"

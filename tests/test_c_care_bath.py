"""Small geometry/snapshot checks only; no full build, browser or scene."""
from __future__ import annotations

import copy
from xml.etree import ElementTree as ET

import export_c_care_bath as export
import pytest

from house_design.b32_rear_right import body, rect
from house_design.b32_service_detail import _inside
from house_design.c_care_bath import component_box, components, hardware_sweeps, review, validate_config
from house_design.c_care_route import leaf_at_angle
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash


@pytest.fixture(scope="module")
def study():
    return export.build_study()


def option(study, key="c-bath-refined"):
    return next(o for o in study["options"] if o["id"] == key)


def rooms(state, index=0):
    return {r["key"]: r for r in state["plans"]["floors"][index]["rooms"]}


def test_scope_and_counts_original_requirements_untouched(study):
    assert study["adopted"] is False and study["rendered_qa"] == "not-run"
    assert set(study["professional_status"].values()) == {"unknown"}
    assert [o["id"] for o in study["options"]] == ["c-bath-control", "c-bath-refined"]
    assert [s["id"] for s in option(study)["states"]] == ["transfer", "shower", "rail-down", "door-closed"]
    states = [s for o in study["options"] for s in o["states"]]
    assert len(states) == 5 and sum(len(s["plans"]["floors"]) for s in states) == 20
    assert sum(len(f["rooms"]) for s in states for f in s["plans"]["floors"]) == 195
    assert sum(len(r["furniture"]) for s in states for f in s["plans"]["floors"] for r in f["rooms"]) == 250
    ledger = study["requirement_ledger"]
    assert (ledger["canonical_requirements"], ledger["scenario_rows"], ledger["verified_requirements"]) == (66, 40, 0)


def test_display_v2_preserves_every_v1_plan_requirement_and_coordinate_review(study):
    # Fingerprints captured before the mobile-only fix. Camera/readout changes
    # must not silently change a product, room, door, accessory, care target or
    # existing geometry warning just to make a screenshot check pass.
    assert study["bath_display_revision"] == 2
    assert stable_hash([s["plans"] for o in study["options"] for s in o["states"]]) == "3db1adde0b68502612410bc07dc61f9abeed3685ee592e18133b068da545c02e"
    assert study["requirement_ledger"]["ledger_hash"] == "d9ce0c0959aa2cf7e718a2bba066803bb260b90a996e610f6b748b8dfdc9ef78"
    assert stable_hash([s["review"] for o in study["options"] for s in o["states"]]) == "c27cb3d545dc8d805f6d11d52647c7262cf2023fd698af6b49af1989ba04b744"


def test_control_exact_verified_parent_and_original_limitations_retained(study):
    original = read_json(ROOT / "structured/candidates/c-care-route/review.json")["options"][1]["states"][0]["plans"]
    control = option(study, "c-bath-control")["states"][0]
    actual = copy.deepcopy(control["plans"])
    for f, ref in zip(actual["floors"], original["floors"], strict=True):
        f["plan_file"] = ref["plan_file"]
    assert actual == original
    assert control["review"]["bath"]["turn_coordinate_failures"]
    assert control["review"]["bath"]["transfer_coordinate_failures"]


def test_no_room_expansion_borrowed_outdoor_area_or_other_room_furniture_changes(study):
    control = option(study, "c-bath-control")["states"][0]
    before = rooms(control)
    for s in option(study)["states"]:
        after = rooms(s)
        assert {k: rect(r) for k, r in after.items()} == {k: rect(r) for k, r in before.items()}
        assert rect(after["elder-bath"]) == [3600, 13800, 2400, 3000]
        assert after["service"] == before["service"]
        for key in before:
            if key != "elder-bath":
                assert after[key] == before[key]
        for index in range(1, 4):
            f = copy.deepcopy(s["plans"]["floors"][index])
            f["plan_file"] = control["plans"]["floors"][index]["plan_file"]
            assert f == control["plans"]["floors"][index]


def test_unsqueezed_fixtures_operations_and_explicit_replacement_product(study):
    before = {i["id"]: i for i in rooms(option(study, "c-bath-control")["states"][0])["elder-bath"]["furniture"]}
    for s in option(study)["states"]:
        bath = rooms(s)["elder-bath"]
        assert len(bath["furniture"]) == 3
        for i in bath["furniture"]:
            old = before[i["id"]]
            assert [i[k] for k in ("width_mm", "depth_mm", "height_mm")] == [old[k] for k in ("width_mm", "depth_mm", "height_mm")]
            assert i["front_clearance_mm"] == 700 and i["placement"]["operation_mm"]
            if i["shape"] == "vanity":
                assert i["replacement_for_catalog_id"] == "vanity-60" and i["care_bath_wall_hung"]
                assert i["catalog_id"] == "wall-hung-vanity-60-study"
            if i["shape"] == "shower":
                assert i["step_free"] and i["care_bath_open_shower"] and body(i)[2:] == [1200, 1200]
        assert not s["review"]["operation_vs_fixed_body"]
        assert s["review"]["bath"]["knee_clearance_credit_mm"] == 0


def test_modes_have_only_the_expected_failures_and_upstream_routes_retained(study):
    for s in option(study)["states"]:
        b, r = s["review"]["bath"], s["review"]["route"]
        assert b["body_mm"] == [900, 900] and b["turn_reserve_mm"][2:] == [1500, 1800]
        assert b["shared_wet_floor_overlap_sqm"] == .6875
        assert b["independent_dry_turn_floor"] is False
        assert all(not v["coordinate_failures"] for v in r["routes"].values()) if s["id"] != "door-closed" else r["routes"]["bed-to-bath"]["coordinate_failures"]
        assert not b["hardware_sweep_conflicts"]
        if s["id"] == "shower":
            assert b["turn_coordinate_failures"] and all(f.endswith("hits-fold-seat") for f in b["turn_coordinate_failures"])
            assert b["rescue_board_rotation_failures"] == ["board-rotation:hits-fold-seat"]
        else:
            assert not b["turn_coordinate_failures"] and not b["rescue_board_rotation_failures"]
        if s["id"] == "rail-down":
            assert b["transfer_coordinate_failures"] == ["transfer:hits-toilet-arm"]
        else:
            assert not b["transfer_coordinate_failures"]
        for key, path in b["routes"].items():
            failures = path["coordinate_failures"]
            if s["id"] == "door-closed":
                assert failures and all(f.endswith("hits-bathroom-closed-leaf") for f in failures)
            elif s["id"] == "rail-down" and key == "toilet-transfer":
                assert failures and all(f.endswith("hits-toilet-arm") for f in failures)
            else:
                assert not failures


def test_hardware_poses_come_from_rigid_motion_and_full_angle_bounds():
    cfg = read_json(ROOT / export.SOURCE)
    raised, deployed = components(cfg, "transfer"), components(cfg, "shower")
    assert component_box(raised[0]) == pytest.approx([5045, 16627.5, 480, 45, 427.5, 450])
    assert component_box(deployed[0]) == pytest.approx([5045, 16200, 480, 450, 405, 45])
    swept = hardware_sweeps(cfg)[0]["box_mm"]
    # Regression sampling validates the analytic formula; production uses all
    # corner stationary extrema, not sampling as its proof.
    for angle in range(91):
        yz = leaf_at_angle([16200, 405, 450, 45], [16650, 427.5], -angle)
        assert _inside(yz, [[swept[1], swept[4], swept[3], swept[5]]], 0)
    assert len(raised) == 8 and all(c["counts_as_furniture"] is False for c in raised)


def test_window_and_mechanical_limits_are_retained_not_false_certifications(study):
    old = rooms(option(study, "c-bath-control")["states"][0])["elder-bath"]["features"]
    for s in option(study)["states"]:
        f, detail = rooms(s)["elder-bath"]["features"], s["review"]["bath"]
        for key in ("window_face", "window_ratio", "window_sill_mm", "window_height_mm", "window_mm", "window_review"):
            assert f[key] == old[key]
        assert f["care_bath_vent_route_mm"][-1] == [5700, 17100, 2700]
        assert detail["professional_acceptance"] == "unknown"
        assert detail["critical_margins_mm"] == {"entry_body_to_vanity": 10, "transfer_to_vanity": 15, "rigid_board_rotation_to_folded_seat": 8.5}
        assert detail["construction_tolerance_and_products"].startswith("unresolved")
        assert detail["simultaneous_lift_and_multiple_caregivers"] == "not-demonstrated"


@pytest.mark.parametrize("change", ["glass", "tiny-product", "operation", "short-operation", "seat", "arm", "wrong-state", "expanded-bath"])
def test_false_shared_floor_or_equipment_evidence_is_rejected(study, change):
    state = copy.deepcopy(option(study)["states"][0])
    bath = rooms(state)["elder-bath"]
    if change == "glass":
        next(i for i in bath["furniture"] if i["shape"] == "shower")["step_free"] = False
    elif change == "tiny-product":
        bath["furniture"][0]["width_mm"] = 200
    elif change == "operation":
        bath["furniture"][0]["placement"]["operation_mm"] = None
    elif change == "short-operation":
        bath["furniture"][0]["placement"]["operation_mm"]["maxY"] -= 300
    elif change == "seat":
        bath["features"]["care_bath_components"][0]["rect_mm"][2] = 100
    elif change == "arm":
        bath["features"]["care_bath_components"][1]["points_mm"][1][2] = 200
    elif change == "wrong-state":
        bath["features"]["care_bath_components"][0]["state"] = "deployed"
    else:
        bath["geometry"]["h_mm"] = 3830
    with pytest.raises(ContractError):
        review(state["plans"], read_json(ROOT / export.SOURCE), "transfer", refined=True)


@pytest.mark.parametrize("change", ["body", "turn", "transfer", "seat", "rescue", "adoption"])
def test_original_scope_and_generic_sizes_cannot_be_shrunk(change):
    cfg = read_json(ROOT / export.SOURCE)
    if change == "body":
        cfg["body_mm"] = [700, 700]
    elif change == "turn":
        cfg["turn_reserve_mm"][3] = 1500
    elif change == "transfer":
        cfg["toilet_transfer_mm"][2] = 600
    elif change == "seat":
        cfg["seat"]["width_mm"] = 300
    elif change == "rescue":
        cfg["rescue_trial"]["body_mm"] = [600, 600]
    else:
        cfg["professional_status"]["care_and_occupational_therapy"] = "approved"
    with pytest.raises(ContractError):
        validate_config(cfg)


def test_requirement_deficits_and_source_bound_bounded_svgs(study):
    for p, digest in study["source_hashes"].items():
        assert sha256_file(ROOT / p) == digest
    ledger = study["requirement_ledger"]
    assert ledger["ledger_hash"] == stable_hash({k: v for k, v in ledger.items() if k != "ledger_hash"})
    for row in ledger["scenarios"][1]["rows"]:
        assert row["functional_acceptance"] == row["professional_acceptance"] == "unknown"
        if row["requirement_id"] == "C.floor-1.elder_bath":
            assert "公共直達照服偏好未滿足" in row["note"]
            assert "shared-wet-turning-floor-not-independent-dry-clearance" in row["flags"]
        if row["requirement_id"] == "C.floor-1.idf_c":
            assert row["dedicated_service_area_credit_sqm"] == 0
    for o in study["options"]:
        for s in o["states"]:
            for f in s["plans"]["floors"]:
                svg = ET.parse(ROOT / export.OUT / f["plan_file"]).getroot()
                assert int(svg.get("width")) == 660 and not svg.findall(".//{http://www.w3.org/2000/svg}image")
                assert svg.get("data-bath-option") == o["id"] and svg.get("data-use-state") == s["id"]
            detail = ET.parse(ROOT / export.OUT / (o["id"]+'_'+s["id"]+'_detail.svg')).getroot()
            assert int(detail.get("width")) == 780


def test_no_full_scene_generator_solver_or_parent_export(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Never run full build, solver, scene or regenerate parent")
    monkeypatch.setattr(export.basis.viewer, "build_payload", forbidden)
    monkeypatch.setattr(export.basis.viewer, "attach_placements", forbidden)
    monkeypatch.setattr(export.route, "write_study", forbidden)
    assert len(export.build_study()["options"]) == 2

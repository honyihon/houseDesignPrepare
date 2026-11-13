"""Small coordinate/snapshot tests only. No browser, scene or full build."""
from __future__ import annotations

import copy
from collections import Counter
from xml.etree import ElementTree as ET

import export_c_care_entry as export
import pytest
from historical_support import assert_historical_sources, historical_study

from house_design.b32_rear_right import body, rect
from house_design.c_care_entry import review, validate_config
from house_design.contracts import ROOT, ContractError, read_json, stable_hash


@pytest.fixture(scope="module")
def study():
    return historical_study("c-care-entry")


def option(study, key="c-entry-refined"):
    return next(o for o in study["options"] if o["id"] == key)


def rooms(state, index=0):
    return {r["key"]: r for r in state["plans"]["floors"][index]["rooms"]}


def test_scope_original_targets_and_unknown_approvals(study):
    assert study["adopted"] is False and study["rendered_qa"] == "not-run"
    assert set(study["professional_status"].values()) == {"unknown"}
    assert study["frame_mm"] == [6000, 17630]
    assert [o["id"] for o in study["options"]] == ["c-entry-control", "c-entry-refined"]
    assert [s["id"] for s in option(study)["states"]] == ["open", "closed"]
    assert study["requirement_ledger"]["canonical_requirements"] == 66
    assert study["requirement_ledger"]["scenario_rows"] == 40
    assert study["requirement_ledger"]["verified_requirements"] == 0


def test_original_control_matches_the_verified_source_plan(study):
    report = read_json(ROOT / "structured/candidates/current-design-basis/review.json")
    source = next(o for o in report["options"] if o["id"] == "c-care-refined")["states"][0]["plans"]
    actual = copy.deepcopy(option(study, "c-entry-control")["states"][0]["plans"])
    for f, ref in zip(actual["floors"], source["floors"], strict=True):
        f["plan_file"] = ref["plan_file"]
    assert actual == source


def test_frame_stair_flights_kitchen_wet_stack_and_all_upper_floors_retained(study):
    control = option(study, "c-entry-control")["states"][0]
    before = rooms(control)
    for state in option(study)["states"]:
        after = rooms(state)
        assert sum(rect(r)[2]*rect(r)[3] for r in after.values()) == 6000*17630
        for key in ("elder", "elder-bath", "kitchen", "public-bath", "dining", "living", "garage"):
            assert after[key]["geometry"] == before[key]["geometry"]
        assert after["stair1f"]["features"]["stair_geometry"] == before["stair1f"]["features"]["stair_geometry"]
        assert after["stair1f"]["features"]["stair_footprint_mm"] == before["stair1f"]["features"]["stair_footprint_mm"]
        for index in range(1, 4):
            a, b = copy.deepcopy(state["plans"]["floors"][index]), control["plans"]["floors"][index]
            a["plan_file"] = b["plan_file"]
            assert a == b
        assert not state["review"]["operation_vs_fixed_body"]


def test_all_furniture_is_full_size_and_only_the_tv_is_relocated(study):
    before = rooms(option(study, "c-entry-control")["states"][0])
    def products(rs):
        return Counter((i["id"], i["catalog_id"], i["width_mm"], i["depth_mm"], i["height_mm"]) for r in rs.values() for i in r["furniture"])
    for state in option(study)["states"]:
        after = rooms(state)
        assert products(after) == products(before)
        for key, r in after.items():
            old = {i["id"]: i for i in before[key]["furniture"]}
            for i in r["furniture"]:
                if i["id"] != "C:floor-1:elder:furniture:tv":
                    assert i == old[i["id"]]
                else:
                    assert body(i) == [3405, 15850, 80, 1000]
                    assert i["placement"]["mount_height_mm"] == old[i["id"]]["placement"]["mount_height_mm"]


def test_actual_door_pairing_open_paths_and_closed_negative_controls(study):
    opened, closed = option(study)["states"]
    for state in (opened, closed):
        r = state["review"]["entry"]
        assert r["body_mm"] == [900, 900]
        assert r["entry_projects_onto_bed_body"] is False
        assert r["turn_coordinate_failures"] == []
        assert r["bedroom_turn_circle_mm"][2] == 750
        assert all(d["nominal_mm"] == 1200 and d["operation"] == "sliding" for d in r["doors"])
        assert all(d["sensitivity"][-1]["clear_assumption_mm"] == 970 for d in r["doors"])
        assert all(d["selected_product"] is None for d in r["doors"])
    assert all(not r["coordinate_failures"] for r in opened["review"]["entry"]["routes"].values())
    assert any("bedroom-closed-leaf" in f for f in closed["review"]["entry"]["routes"]["hall-to-bed"]["coordinate_failures"])
    assert any("bathroom-closed-leaf" in f for f in closed["review"]["entry"]["routes"]["bed-to-bath"]["coordinate_failures"])
    assert all(d["neighbor"] != "C:floor-1:stair1f" for d in rooms(opened)["elder"]["features"]["doors"])


def test_upstream_shortfalls_idf_credit_and_bathroom_access_remain_unresolved(study):
    detail = option(study)["states"][0]["review"]["entry"]
    assert detail["hall_separate_finished_depth_at_115mm"] == 1470
    assert [d["clear_assumption_at_115mm"] for d in detail["upstream_door_budgets"]] == [770, 770]
    assert [d["shortfall_at_115mm"] for d in detail["upstream_door_budgets"]] == [130, 130]
    scenario = study["requirement_ledger"]["scenarios"][1]
    for row in scenario["rows"]:
        assert row["functional_acceptance"] == row["professional_acceptance"] == "unknown"
        if row["requirement_id"] in {"C.floor-1.elder", "C.floor-1.elder_bath"}:
            assert row["door_budget_checks"][0]["clear_assumption_at_115mm"] == 970
            assert "upstream-care-route-bottleneck-still-unresolved" in row["flags"]
        if row["requirement_id"] == "C.floor-1.idf_c":
            assert row["dedicated_service_area_credit_sqm"] == 0
    assert "unknown" in detail["full_bathroom_turn_transfer_and_rescue"]
    assert "not-satisfied" in detail["bed_bath_private_access_and_family_acceptance"]


@pytest.mark.parametrize("change", ["width", "operation", "leaf", "leaf-state", "turn", "stair"])
def test_review_rejects_false_aperture_or_missing_obstacle_evidence(study, change):
    state = copy.deepcopy(option(study)["states"][0])
    cells = rooms(state)
    cfg = read_json(ROOT / export.SOURCE)
    if change == "width":
        cells["elder"]["features"]["doors"][0]["width_mm"] = 1000
    elif change == "operation":
        cells["elder"]["features"]["doors"][0]["operation"] = "unconfirmed"
    elif change == "leaf":
        cells["sideyard"]["features"]["care_entry_leaves"][0]["rect_mm"][2] = 600
    elif change == "leaf-state":
        cells["elder-bath"]["features"]["care_entry_leaves"][0]["state"] = "closed"
    elif change == "turn":
        cfg["bedroom_turn_circle_mm"] = [1000, 16700, 750]
    else:
        cells["stair1f"]["features"]["stair_footprint_mm"]["x_mm"] = 2700
    with pytest.raises(ContractError):
        review(state["plans"], cfg, "open", 900)


@pytest.mark.parametrize("change", ["care", "target", "leaf", "adoption"])
def test_original_target_and_leaf_sizes_cannot_be_reduced(change):
    cfg = read_json(ROOT / export.SOURCE)
    if change == "care":
        cfg["care_body_mm"] = [700, 700]
    elif change == "target":
        cfg["doors"]["bedroom"]["nominal_mm"] = 1000
    elif change == "leaf":
        cfg["doors"]["bathroom"]["open_leaf_mm"][3] = 1000
    else:
        cfg["professional_status"]["wheelchair_caregiver_and_rescue"] = "passed"
    with pytest.raises(ContractError):
        validate_config(cfg)


def test_source_evidence_and_bounded_svg_outputs(study):
    assert_historical_sources("c-care-entry", study)
    ledger = study["requirement_ledger"]
    assert ledger["ledger_hash"] == stable_hash({k: v for k, v in ledger.items() if k != "ledger_hash"})
    for o in study["options"]:
        for s in o["states"]:
            for f in s["plans"]["floors"]:
                svg = ET.parse(ROOT / export.OUT / f["plan_file"]).getroot()
                assert int(svg.get("width")) <= 900
                assert not svg.findall(".//{http://www.w3.org/2000/svg}image")
                assert svg.get("data-care-option") == o["id"]
                assert svg.get("data-use-state") == s["id"]


def test_no_full_generator_or_solver_is_needed(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Never run full build, scene runtime or solver")
    monkeypatch.setattr(export.basis.viewer, "build_payload", forbidden)
    monkeypatch.setattr(export.basis.viewer, "attach_placements", forbidden)
    with pytest.raises(ContractError, match="[Ss]tale"):
        export.build_study()

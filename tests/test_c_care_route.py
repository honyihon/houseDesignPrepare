"""Bounded geometry and snapshot regressions; no browser/full build/runtime."""
from __future__ import annotations

import copy
from collections import Counter
from xml.etree import ElementTree as ET

import export_c_care_route as export
import pytest
from historical_support import assert_historical_sources, historical_study

from house_design.b32_rear_right import body, rect
from house_design.b32_service_detail import _inside
from house_design.c_care_route import full_inward_sweep, leaf_at_angle, review, validate_config
from house_design.contracts import ROOT, ContractError, read_json, stable_hash


@pytest.fixture(scope="module")
def study():
    return historical_study("c-care-route")


def option(study, key="c-route-refined"):
    return next(o for o in study["options"] if o["id"] == key)


def rooms(state, index=0):
    return {r["key"]: r for r in state["plans"]["floors"][index]["rooms"]}


def test_scope_counts_targets_and_independent_states(study):
    assert study["adopted"] is False and study["rendered_qa"] == "not-run"
    assert set(study["professional_status"].values()) == {"unknown"}
    assert [o["id"] for o in study["options"]] == ["c-route-control", "c-route-refined"]
    assert [s["id"] for s in option(study)["states"]] == ["open", "street-closed", "bedroom-closed", "bath-closed"]
    states = [s for o in study["options"] for s in o["states"]]
    assert len(states) == 5 and sum(len(s["plans"]["floors"]) for s in states) == 20
    assert sum(len(f["rooms"]) for s in states for f in s["plans"]["floors"]) == 195
    assert sum(len(r["furniture"]) for s in states for f in s["plans"]["floors"] for r in f["rooms"]) == 250
    ledger = study["requirement_ledger"]
    assert (ledger["canonical_requirements"], ledger["scenario_rows"], ledger["verified_requirements"]) == (66, 40, 0)


def test_control_is_exact_previous_open_proposal_and_still_fails_upstream(study):
    source = read_json(ROOT / "structured/candidates/c-care-entry/review.json")["options"][1]["states"][0]["plans"]
    control = option(study, "c-route-control")["states"][0]
    actual = copy.deepcopy(control["plans"])
    for f, ref in zip(actual["floors"], source["floors"], strict=True):
        f["plan_file"] = ref["plan_file"]
    assert actual == source
    failures = control["review"]["route"]["routes"]["arcade-to-bed"]["coordinate_failures"]
    for known in ("dining-front-wall-or-jamb", "living:furniture:sofa", "sliding-door-front-wall-or-jamb"):
        assert any(known in f for f in failures)
    assert control["review"]["route"]["routes"]["bed-to-bath"]["coordinate_failures"] == []


def test_frame_all_regions_actual_stair_and_upper_floors_unchanged(study):
    control = option(study, "c-route-control")["states"][0]
    before = rooms(control)
    for state in option(study)["states"]:
        after = rooms(state)
        assert sum(rect(r)[2]*rect(r)[3] for r in after.values()) == 6000*17630
        assert {k: r["geometry"] for k, r in after.items()} == {k: r["geometry"] for k, r in before.items()}
        for field in ("stair_footprint_mm", "stair_geometry"):
            assert after["stair1f"]["features"][field] == before["stair1f"]["features"][field]
        for index in range(1, 4):
            a, b = copy.deepcopy(state["plans"]["floors"][index]), control["plans"]["floors"][index]
            a["plan_file"] = b["plan_file"]
            assert a == b
        assert not state["review"]["operation_vs_fixed_body"]


def test_full_size_products_only_four_furniture_moves_and_operations_retained(study):
    control = rooms(option(study, "c-route-control")["states"][0])
    def products(rs):
        return Counter((i["catalog_id"], i["width_mm"], i["depth_mm"], i["height_mm"], i.get("physical_item_id")) for r in rs.values() for i in r["furniture"])
    for state in option(study)["states"]:
        after = rooms(state)
        assert products(after) == products(control)
        changed = {k for k, r in after.items() if r["furniture"] != control[k]["furniture"]}
        assert changed == {"dining", "living", "living-right"}
        dining = after["dining"]["furniture"][0]
        assert body(dining) == [515, 4415, 1800, 1800]
        assert dining["placement"]["operation_mm"] == {"minX": 115, "maxX": 2715, "minY": 4015, "maxY": 6615}
        sofa = next(i for i in after["living"]["furniture"] if i["id"].endswith(":sofa"))
        assert body(sofa) == [1615, 6630, 900, 1800]
        assert sofa["placement"]["operation_mm"] == {"minX": 1015, "maxX": 1615, "minY": 6630, "maxY": 8430}
        chair = after["living-right"]["furniture"][0]
        assert chair["relocated_from"] == "C:floor-1:living:furniture:reading-chair"
        assert chair["id"] == "C:floor-1:living-right:furniture:reading-chair"
        assert body(chair) == [4700, 7945, 850, 900]
        assert chair["placement"]["operation_mm"] == {"minX": 4100, "maxX": 4700, "minY": 7945, "maxY": 8845}
        assert state["model"]["furniture"]["rooms"] == 23
        assert not state["review"]["route"]["operation_vs_fixed_body"]


def test_actual_paired_open_passage_and_window_preserved(study):
    before = rooms(option(study, "c-route-control")["states"][0])
    for state in option(study)["states"]:
        after = rooms(state)
        for key in ("window_mm", "window_ratio", "window_face", "window_review"):
            assert after["dining"]["features"].get(key) == before["dining"]["features"].get(key)
        for a, b, face in (("living-hall", "sliding-door", "rear"), ("sliding-door", "living-hall", "front")):
            features = after[a]["features"]
            assert not any(d["neighbor"] == after[b]["id"] for d in features["doors"])
            assert any(d["face"] == face and d["width_mm"] == 1200 and d["neighbor"] == after[b]["id"] for d in features["open_connections"])
        assert next(d for d in after["sliding-door"]["features"]["doors"] if d["neighbor"] == after["stair1f"]["id"])["width_mm"] == 1000
        assert [g["clear_assumption_at_115mm"] for g in state["review"]["route"]["gates"]] == [970]*4


def test_rigid_leaf_analytic_all_angle_sweep_respects_arcade_and_window(study):
    cfg = read_json(ROOT / export.SOURCE)["street_door"]
    sweep = full_inward_sweep(cfg["closed_leaf_mm"], cfg["pivot_mm"])
    assert leaf_at_angle(cfg["closed_leaf_mm"], cfg["pivot_mm"], -90) == pytest.approx([3785, 3940, 80, 1050])
    assert sweep == pytest.approx([2774.238371, 3900, 1090.761629, 1090.761629])
    # Samples are a regression check on the analytic formula, not the proof used
    # by the production review. All corners' stationary extrema form the proof.
    for angle in range(91):
        assert _inside(leaf_at_angle(cfg["closed_leaf_mm"], cfg["pivot_mm"], -angle), [sweep], 0)
    for state in option(study)["states"]:
        r = state["review"]["route"]
        assert not r["street_sweep_hits"] and r["arcade_occupied_by_sweep"] is False
        assert r["front_window_to_opening_budget_mm"] == 100
        assert r["effective_open_street_width_assumption_mm"] == 970
        assert "analytic" in r["street_sweep_method"] and r["continuous_human_access_approval"] == "unknown"


def test_continuous_route_and_three_independent_closed_negative_controls(study):
    expected = {"open": (None, None), "street-closed": ("street", None), "bedroom-closed": ("bedroom", None), "bath-closed": (None, "bathroom")}
    for state in option(study)["states"]:
        route = state["review"]["route"]
        assert route["body_mm"] == [900, 900]
        assert route["turn_coordinate_failures"] == [] and route["entry_projects_onto_bed_body"] is False
        assert route["routes"]["arcade-to-bed"]["points_mm"][0] == [3285, 3000]
        for key, obstacle in zip(("arcade-to-bed", "bed-to-bath"), expected[state["id"]], strict=True):
            failures = route["routes"][key]["coordinate_failures"]
            assert (not failures) if obstacle is None else failures and all(f.endswith("hits-"+obstacle+"-closed-leaf") for f in failures)


@pytest.mark.parametrize("change", ["paired", "private-state", "private-leaf", "street", "street-state", "phantom-door", "stair", "dining-op", "dining-body", "turn"])
def test_false_or_shrunken_evidence_rejected(study, change):
    state = copy.deepcopy(option(study)["states"][0])
    cells, cfg = rooms(state), read_json(ROOT / export.SOURCE)
    private = read_json(ROOT / cfg["private_entry_config"])
    if change == "paired":
        cells["elder"]["features"]["doors"][0]["width_mm"] = 1000
    elif change == "private-state":
        cells["sideyard"]["features"]["care_entry_leaves"][0]["state"] = "closed"
    elif change == "private-leaf":
        cells["sideyard"]["features"]["care_entry_leaves"][0]["rect_mm"][2] = 100
    elif change == "street":
        cells["dining"]["features"]["doors"][0]["ratio"] = .5
    elif change == "street-state":
        cells["dining"]["features"]["care_entry_leaves"][0]["state"] = "closed"
    elif change == "phantom-door":
        cells["living-hall"]["features"]["doors"].append(cells["living-hall"]["features"]["open_connections"][-1])
    elif change == "stair":
        cells["stair1f"]["features"]["stair_footprint_mm"]["x_mm"] = 2700
    elif change == "dining-op":
        cells["dining"]["furniture"][0]["placement"]["operation_mm"] = None
    elif change == "dining-body":
        cells["dining"]["furniture"][0]["placement"]["aabb"]["maxX"] = 3000
    else:
        private["bedroom_turn_circle_mm"] = [1000, 16700, 750]
    with pytest.raises(ContractError):
        review(state["plans"], cfg, "open", private, refined=True)


def test_unresolved_preferences_are_not_resolved_by_a_route_line(study):
    scenario = study["requirement_ledger"]["scenarios"][1]
    for row in scenario["rows"]:
        assert row["functional_acceptance"] == row["professional_acceptance"] == "unknown"
        if row["requirement_id"] in {"C.floor-1.elder", "C.floor-1.elder_bath"}:
            assert row["upstream_discussion_budgets_mm"] == [970, 970]
            assert "unknown" in row["whole_route_care_acceptance"]
        if row["requirement_id"] == "C.floor-1.idf_c":
            assert row["dedicated_service_area_credit_sqm"] == 0
        if row["requirement_id"] == "C.floor-1.elder_bath":
            assert "公共直達照服偏好未滿足" in row["note"]


@pytest.mark.parametrize("change", ["body", "height", "leaf", "nominal", "adoption"])
def test_scope_and_targets_cannot_be_reduced(change):
    cfg = read_json(ROOT / export.SOURCE)
    if change == "body":
        cfg["care_body_mm"] = [700, 700]
    elif change == "adoption":
        cfg["professional_status"]["wheelchair_caregiver_and_rescue"] = "passed"
    else:
        key = {"height": "height_mm", "leaf": "closed_leaf_mm", "nominal": "nominal_mm"}[change]
        cfg["street_door"][key] = [2775, 3900, 800, 80] if change == "leaf" else 800
    with pytest.raises(ContractError):
        validate_config(cfg)


def test_all_svg_outputs_are_bounded_same_source_and_previous_sources_untouched(study):
    assert_historical_sources("c-care-route", study)
    assert_historical_sources("c-care-entry", historical_study("c-care-entry"))
    for o in study["options"]:
        for s in o["states"]:
            for f in s["plans"]["floors"]:
                svg = ET.parse(ROOT / export.OUT / f["plan_file"]).getroot()
                assert int(svg.get("width")) == 660 and not svg.findall(".//{http://www.w3.org/2000/svg}image")
                assert svg.get("data-route-option") == o["id"] and svg.get("data-use-state") == s["id"]
                if f["id"] == "floor-1":
                    actual = {(n.get("data-care-leaf-id"), n.get("data-leaf-state")) for n in svg if n.get("data-care-leaf-id")}
                    expected = {(leaf["id"], leaf["state"]) for r in f["rooms"] for leaf in r["features"].get("care_entry_leaves", [])}
                    assert actual == expected
    ledger = study["requirement_ledger"]
    assert ledger["ledger_hash"] == stable_hash({k: v for k, v in ledger.items() if k != "ledger_hash"})


def test_no_solver_or_parent_regeneration_needed(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Never run full build, scene runtime or solver")
    monkeypatch.setattr(export.basis.viewer, "build_payload", forbidden)
    monkeypatch.setattr(export.basis.viewer, "attach_placements", forbidden)
    with pytest.raises(ContractError, match="[Ss]tale"):
        export.build_study()

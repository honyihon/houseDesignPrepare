"""Small coordinate/contract regressions; no browser or full-scene runtime."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import merge_c_stair_into_3d as export
import pytest
from lib.model3d_plan import room_label

from house_design.c_ac01_route import CONFIG, low_arcade_segments
from house_design.c_stair_landing import build as detail
from house_design.c_stair_merge import build, frozen_study, patch_c_model, shift_routes
from house_design.contracts import ContractError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def basis():
    original, _ = frozen_study(ROOT)
    model = next(o for o in original["options"] if o["id"] == "c-split")["states"][0]["model"]
    return model, detail(ROOT), json.loads((ROOT/CONFIG).read_text())


def candidate(basis, change=None):
    model, stair, cfg = basis
    cfg = copy.deepcopy(cfg)
    if change:
        cfg.update(change)
    return patch_c_model(model, stair, cfg)[0]


def units(model):
    return {u["id"]+u["type"]: u for f in model["buildings"][0]["floors"] for c in f["cells"] if c.get("tour_active")
        for u in c["tour_features"].get("hvac_units", [])}


def test_candidate_removes_low_arcade_route_and_actual_partition_conflict(basis):
    model = candidate(basis)
    r = model["c_ac01_routing"]
    assert r["old_indoor_partition_conflict"] is True
    assert r["baseline_low_arcade_segments"] and not r["candidate_low_arcade_segments"]
    assert r["baseline"]["estimated_routed_length_mm"] == 15735
    assert r["route"]["estimated_routed_length_mm"] == 15495
    assert r["route"]["elevation_difference_mm"] == 2150
    assert r["routed_vertical_travel_mm"] == 5850
    assert r["new_indoor_body_mm"] == [5710, 6025, 2350, 5990, 6975, 2630]
    assert r["riser_envelope_mm"] == [4350, 4900, 3425, 4550, 5100, 6425]
    assert r["nominal_front_opening_margins_mm"] == {"window": 175, "door": 225}
    assert r["floor2_coordination_floor_footprint_sqm"] == .04 and r["upper_sofa_projection_gap_mm"] == 460
    assert all(r["route"][key] is None for key in ["model", "manual_source", "max_pipe_length_mm", "max_elevation_mm"])
    assert r["professional_approval"] == r["route"]["compliance"] == "unknown"
    assert "另走" in r["route"]["drainage"]
    assert r["condensate_gravity_budget"]["fall_sensitivity_mm"] == {"1": 8, "1.5": 12, "2": 16}
    assert r["condensate_gravity_budget"]["lawful_terminal"] is None


def test_all_route_copies_and_other_six_systems_remain_consistent(basis):
    model = candidate(basis)
    current = units(model)
    compare = copy.deepcopy(basis[0])
    old_bases = {f["id"]: f["base_mm"] for f in compare["buildings"][0]["floors"]}
    for f in compare["buildings"][0]["floors"]:
        f["base_mm"] = basis[1]["floor_bases_mm"][f["id"]]
    shift_routes(compare, old_bases)
    for key, unit in units(compare).items():
        if unit["id"] != "C-AC01":
            assert unit == current[key]
    expected = model["c_ac01_routing"]["route"]
    assert current["C-AC01indoor"]["route"] == current["C-AC01outdoor"]["route"] == expected
    assert next(r for r in model["layout_review"]["hvac_routes"] if r["id"] == "C-AC01") == expected
    rooms = {c["id"]: c for f in model["buildings"][0]["floors"] for c in f["cells"] if c.get("tour_active")}
    assert not rooms["C:floor-1:living-right"]["tour_features"]["hvac_units"]
    assert rooms["C:floor-1:entrance"]["tour_features"]["hvac_units"][0]["id"] == "C-AC01"


@pytest.mark.parametrize("change,match", [
    ({"indoor_xy_mm": [5850, 8230]}, "indoor unit crosses"),
    ({"riser_xy_mm": [5900, 5600]}, "intersects furniture"),
    ({"riser_xy_mm": [5840, 4700]}, "blocks front door"),
    ({"riser_xy_mm": [5980, 5000]}, "inside both"),
    ({"bundle_half_width_budget_mm": 110}, "vertical coordination"),
    ({"professional_approval": "passed"}, "unknown approval"),
    ({"riser_xy_mm": [5800, 5000]}, "too close to a nominal front opening"),
])
def test_bad_alternatives_are_rejected_before_serialization(basis, change, match):
    with pytest.raises(ContractError, match=match):
        candidate(basis, change)


def test_pipe_bundle_cannot_hide_under_a_safe_centerline():
    assert low_arcade_segments([[5800, 0, 3550], [5800, 3900, 3550]], 3900, radius=75)
    assert not low_arcade_segments([[5800, 0, 3650], [5800, 3900, 3650]], 3900, radius=75)


def test_main_plans_and_bounded_section_preserve_exact_review_data():
    study, _ = build(ROOT)
    svg = ET.fromstring(export.ac01_svg(study))
    assert int(svg.get("width"))*int(svg.get("height")) <= 1_600_000
    metadata = next(e for e in svg if e.get("data-ac01-route-review") == "1")
    assert json.loads(metadata.text) == study["c_ac01_review"]
    files = export.artifacts(ROOT)
    assert len(files) == 9
    assert all((ROOT/name).read_text() == value for name, value in files.items())
    for fid in ["floor-1", "floor-2"]:
        svg = ET.fromstring(files["structured/candidates/kaohsiung-house-options/c-split_integrated_"+fid+".svg"])
        assert len([e for e in svg.iter() if e.get("data-ac01-route") == fid]) == 1
        assert len([e for e in svg.iter() if e.get("data-ac01-riser") == "candidate"]) == 1
        if fid == "floor-1":
            label = next(e for e in svg.iter() if e.get("data-hvac-label-id") == "C-AC01")
            assert label.get("text-anchor") == "end" and float(label.get("x")) < 6000
    entrance = next(r for o in study["options"] if o["id"] == "c-split" for r in o["states"][0]["plans"]["floors"][0]["rooms"] if r["key"] == "entrance")
    assert room_label(entrance)["hvac_overlap"] is False

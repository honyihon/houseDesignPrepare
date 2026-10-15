"""Minimal geometry improvements and explicit unadopted choices, not approval."""

from __future__ import annotations

import copy
import json
import math
from xml.etree import ElementTree as ET

import export_model_3d as model3d
import pytest
from lib.dimension_overrides import load_overrides
from lib.furniture_layout import FurnitureLayoutError
from lib.model3d_fengshui import attach_fengshui_checks
from lib.model3d_placement import _candidate, overlaps
from lib.model3d_plan import plan_data, render_plan

NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture(scope="module")
def payload():
    return model3d.build_payload(json.loads(model3d.PROGRAM_FILE.read_text()), load_overrides(), "presentation")


def room(payload, rid):
    return next(c for b in payload["buildings"] for f in b["floors"] for c in f["cells"] if c["id"] == rid)


def placement(payload, rid, local_id):
    return room(payload, rid)["furniture_placements"]["tour_mm"][rid + ":furniture:" + local_id]


def test_hob_is_an_actual_full_size_component_outside_upper_wet_rooms_not_just_generic_black_decoration(payload):
    counter = placement(payload, "A:floor-1:kitchen", "counter")
    assert counter["aabb"] == {"minX": 80, "maxX": 680, "minY": 12140, "maxY": 14540}
    assert placement(payload, "A:floor-1:kitchen", "fridge")["aabb"] == {
        "minX": 1620,
        "maxX": 2320,
        "minY": 13004.5,
        "maxY": 13754.5,
    }
    hob, sink = counter["worktop_parts_mm"]
    assert hob["id"] == "hob" and sink["id"] == "sink"
    assert (hob["width_mm"], hob["depth_mm"]) == (600, 500)
    assert hob["aabb"] == {"minX": 130, "maxX": 630, "minY": 12340, "maxY": 12940}
    assert sink["aabb"] == {"minX": 155, "maxX": 605, "minY": 13540, "maxY": 14140}
    check = next(c for c in payload["layout_review"]["checks"] if c["id"] == "A-hob-wet-projection")
    assert check["status"] == "proposal-geometric-screen-only"
    assert check["scope"] == "hob-only-not-whole-kitchen" and check["plumbing_acceptance"] == "unknown"
    bath = room(payload, "A:floor-3:bath3")["tour_mm"]
    box = {
        "minX": bath["x_mm"],
        "maxX": bath["x_mm"] + bath["w_mm"],
        "minY": bath["y_mm"],
        "maxY": bath["y_mm"] + bath["h_mm"],
    }
    assert not overlaps(hob["aabb"], box) and overlaps(sink["aabb"], box)


def test_b_upper_products_preserve_sizes_and_avoid_only_the_altar_body(payload):
    altar = placement(payload, "B:floor-1:shrine", "altar")["aabb"]
    for rid in ["B:floor-2:living2", "B:floor-3:guest3"]:
        c = room(payload, rid)
        for i in c["furniture"]:
            p = c["furniture_placements"]["tour_mm"][i["id"]]
            assert not p["issues"] and not overlaps(p["aabb"], altar)
        assert c["tour_mm"] == {"x_mm": 0, "y_mm": 3900, "w_mm": 4400, "h_mm": 5600}
        assert c["tour_features"]["fengshui_review"]["religious_acceptance"] == "unknown"
    assert placement(payload, "B:floor-3:guest3", "bed")["wall_anchor"] == "left"
    assert placement(payload, "B:floor-3:guest3", "wardrobe")["wall_anchor"] == "left"


def test_c_master_headboard_moves_but_c_1f_suite_and_pending_decisions_do_not(payload):
    assert placement(payload, "C:floor-3:master3f", "bed")["wall_anchor"] == "left"
    assert placement(payload, "C:floor-3:master3f", "bed")["rotation_deg"] == 270
    elder = room(payload, "C:floor-1:elder")
    assert elder["tour_mm"]["w_mm"] == 3600 and elder["window_mm"] == 2300
    assert placement(payload, "C:floor-1:elder", "bed")["aabb"] == {
        "minX": 500,
        "maxX": 2020,
        "minY": 15670,
        "maxY": 17550,
    }
    assert room(payload, "C:floor-1:elder-bath")["tour_mm"]["w_mm"] == 2400
    for rid in ["C:floor-2:bath2f", "C:floor-3:bath3f"]:
        assert room(payload, rid)["tour_mm"]["h_mm"] == 2200
    shrine = room(payload, "B:floor-1:shrine")
    assert placement(payload, shrine["id"], "altar")["center_x_mm"] == 2200
    assert next(d for d in shrine["tour_features"]["doors"] if d.get("purpose") == "ritual-entry")["ratio"] == 0.5
    spec = payload["layout_review"]["fengshui_minimal"]
    assert spec["religious_acceptance"] == spec["structural_acceptance"] == "unknown"
    assert len(spec["pending_decisions"]) == 4 and all(p["status"] == "not-adopted" for p in spec["pending_decisions"])
    assert elder["tour_features"]["fengshui_review"]["status"] == "decision-pending-not-adopted"
    assert "背牆另一側仍" in shrine["tour_features"]["fengshui_review"]["note"]


@pytest.mark.parametrize(
    "bad",
    [
        "approval",
        "missing-contract",
        "wrong-document",
        "adoption",
        "lost-decision",
        "missing-hob",
        "tiny-hob",
        "hob-under-bath",
        "bed-over-altar",
        "pending-sofa",
        "c-headboard-back",
        "lost-c-wardrobe",
    ],
)
def test_minimal_changes_cannot_regress_or_falsely_approve(payload, bad):
    data = copy.deepcopy(payload)
    if bad == "approval":
        data["layout_review"]["fengshui_minimal"]["religious_acceptance"] = "passed"
    elif bad == "missing-contract":
        data["layout_review"].pop("fengshui_minimal")
    elif bad == "wrong-document":
        data["layout_review"]["fengshui_minimal"]["document"] = "Docs/abc-facade-v1.md"
    elif bad == "adoption":
        data["layout_review"]["fengshui_minimal"]["pending_decisions"][0]["status"] = "adopted"
    elif bad == "lost-decision":
        data["layout_review"]["fengshui_minimal"]["pending_decisions"].pop()
    elif bad in {"missing-hob", "tiny-hob", "hob-under-bath"}:
        parts = placement(data, "A:floor-1:kitchen", "counter")["worktop_parts_mm"]
        if bad == "missing-hob":
            parts.pop(0)
        elif bad == "tiny-hob":
            parts[0]["width_mm"] = 300
        else:
            parts[0]["aabb"]["minY"], parts[0]["aabb"]["maxY"] = 13900, 14500
    elif bad == "bed-over-altar":
        placement(data, "B:floor-3:guest3", "bed")["aabb"] = placement(data, "B:floor-1:shrine", "altar")["aabb"]
    elif bad == "pending-sofa":
        placement(data, "B:floor-2:living2", "sofa")["issues"] = ["door-approach"]
    elif bad == "c-headboard-back":
        placement(data, "C:floor-3:master3f", "bed")["wall_anchor"] = "rear"
    else:
        room(data, "C:floor-3:master3f")["furniture"] = [
            i for i in room(data, "C:floor-3:master3f")["furniture"] if not i["id"].endswith(":wardrobe")
        ]
    with pytest.raises(ValueError, match="Minimal fengshui"):
        attach_fengshui_checks(data["buildings"], data["layout_review"])


@pytest.mark.parametrize("bad", ["overflow", "overlap", "duplicate", "empty", "negative", "nan", "wrong-shape"])
def test_worktop_source_rejects_unrenderable_or_shrunk_metadata(bad):
    furniture = json.loads(model3d.FURNITURE_FILE.read_text())
    counter = furniture["profiles"]["review-a-fengshui-kitchen"][0]
    parts = counter["worktop_parts"]
    if bad == "overflow":
        parts[0]["center_x_mm"] = -1200
    elif bad == "overlap":
        parts[1]["center_x_mm"] = parts[0]["center_x_mm"]
    elif bad == "duplicate":
        parts[1]["id"] = parts[0]["id"]
    elif bad == "empty":
        parts.clear()
    elif bad == "negative":
        parts[0]["width_mm"] = -600
    elif bad == "nan":
        parts[0]["center_x_mm"] = float("nan")
    else:
        counter["catalog"] = "sofa-3"
    with pytest.raises(FurnitureLayoutError):
        model3d.build_payload(
            json.loads(model3d.PROGRAM_FILE.read_text()), load_overrides(), "presentation", furniture_data=furniture
        )


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_worktop_plan_projection_obeys_the_renderer_transform_for_every_cardinal_angle(payload, angle):
    counter = room(payload, "A:floor-1:kitchen")["furniture"][0]
    p = _candidate(counter, 3000, 7000, angle, "")
    radians = math.radians(angle)
    for local, actual in zip(counter["worktop_parts"], p["worktop_parts_mm"], strict=True):
        expected_x = 3000 + local["center_x_mm"] * math.cos(radians) - local["center_z_mm"] * math.sin(radians)
        expected_y = 7000 - local["center_x_mm"] * math.sin(radians) - local["center_z_mm"] * math.cos(radians)
        assert actual["center_x_mm"] == pytest.approx(expected_x)
        assert actual["center_y_mm"] == pytest.approx(expected_y)


def test_svg_and_manifest_expose_same_worktop_and_pending_notes(payload):
    data = plan_data(payload)
    floor = data["buildings"][0]["floors"][0]
    svg = ET.fromstring(render_plan("A", floor))
    details = svg.findall(".//s:rect[@data-worktop-part]", NS)
    assert {r.attrib["data-worktop-part"] for r in details} == {"hob", "sink"}
    assert {r.attrib["data-width-mm"] for r in details} == {"600.0"}
    assert all(r.attrib["data-status"] == "planning-not-measured" for r in details)
    for bid, key in [("B", "shrine"), ("C", "elder")]:
        b = next(b for b in data["buildings"] if b["id"] == bid)
        r = next(r for r in b["floors"][0]["rooms"] if r["key"] == key)
        assert r["features"]["fengshui_review"]["status"] == "decision-pending-not-adopted"


def test_historical_comparison_without_the_contract_is_not_implicitly_adopted(payload):
    assert attach_fengshui_checks(payload["buildings"], {}) == []

"""Protect B owner ritual intent and C open-plan functions, not approval."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import export_model_3d as model3d
import pytest
from lib.dimension_overrides import load_overrides
from lib.model3d_bc_flow import build_bc_flow_checks
from lib.model3d_placement import overlaps
from lib.model3d_plan import plan_data, render_plan

ROOT = Path(__file__).resolve().parents[1]
NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture(scope="module")
def payload():
    return model3d.build_payload(json.loads(model3d.PROGRAM_FILE.read_text()), load_overrides(), "presentation")


def rooms(payload, building):
    b = next(b for b in payload["buildings"] if b["id"] == building)
    return {c["key"]: c for c in b["floors"][0]["cells"] if c.get("tour_active")}


def check(payload, key):
    return next(c for c in payload["layout_review"]["checks"] if c["id"] == key)


def test_b_owner_required_front_door_is_axial_without_displacing_the_altar_or_frontage(payload):
    cells, review = rooms(payload, "B"), check(payload, "B-ritual-and-transport-flow")
    front = next(d for d in cells["shrine"]["tour_features"]["doors"] if d.get("purpose") == "ritual-entry")
    altar = cells["shrine"]["furniture_placements"]["tour_mm"]["B:floor-1:shrine:furniture:altar"]
    assert front["face"] == "front" and front["neighbor"] == "B:floor-1:garage" and front["width_mm"] == 1800
    assert cells["shrine"]["tour_mm"]["w_mm"] * front["ratio"] == altar["center_x_mm"] == 2200
    assert altar["wall_anchor"] == "rear" and altar["aabb"] == {"minX": 1300, "maxX": 3100, "minY": 8820, "maxY": 9420}
    assert review["ritual"]["owner_requires_axial_front_door"] is True
    assert review["ritual"]["religious_acceptance"] == "unknown"
    assert "屋主家規" in review["ritual"]["note"]
    assert cells["garage"]["tour_mm"] == {"x_mm": 0, "y_mm": 0, "w_mm": 6000, "h_mm": 3900}
    assert not cells["garage"]["furniture"]
    assert cells["shrine"]["window_mm"] == 1000
    window = next(o for o in payload["facade"]["buildings"][1]["openings"] if o["id"].endswith("shrine:front:window"))
    assert window["rendered"] and not window["issues"]
    assert window["hi"] < 1300  # front door occupies x=1300..3100


def test_b_benches_rotate_to_walls_without_entering_axial_worship_or_side_door_approaches(payload):
    shrine = rooms(payload, "B")["shrine"]
    reservations = shrine["tour_features"]["reserved_mm"]
    worship = next(z["aabb"] for z in reservations if z["kind"] == "ritual-approach")
    assert worship == {"minX": 1300, "maxX": 3100, "minY": 3900, "maxY": 7100}
    for item in shrine["furniture"]:
        p = shrine["furniture_placements"]["tour_mm"][item["id"]]
        assert not p["issues"]
        for zone in reservations:
            assert not overlaps(p["aabb"], zone["aabb"])
            assert not (p["operation_mm"] and overlaps(p["operation_mm"], zone["aabb"]))
        if "bench" in item["id"]:
            assert (item["width_mm"], item["depth_mm"]) == (1400, 450)
            assert p["wall_anchor"] in {"left", "right"}


def test_b_storage_body_route_is_continuous_and_candid_about_both_gates_and_corridor(payload):
    r = check(payload, "B-ritual-and-transport-flow")["transport"]
    assert r["status"] == "storage-body-sweep-only-not-transport-approval"
    assert [s["room_id"].split(":")[-1] for s in r["segments"]] == ["garage", "entry", "corridor1", "storage"]
    assert r["axis_x_mm"] == 5200 and r["bottleneck_assumed_width_mm"] == 1440
    assert r["storage_dimensions"] == {"width_mm": 1200, "depth_mm": 1700, "height_mm": 1800}
    assert r["storage_dimension_source"] == "planning"
    assert [g["nominal_width_mm"] for g in r["gates"]] == [1500, 1500]
    assert [g["body_side_margin_mm"] for g in r["gates"]] == [150, 150]
    assert r["transport_acceptance"] == "unknown" and r["assembled_dimensions"] is None
    assert r["assembled_measurement"]["status"] == r["route_rehearsal"]["status"] == "unknown"
    for a, b in zip(r["segments"], r["segments"][1:], strict=False):
        assert a["centerline_mm"][-1] == b["centerline_mm"][0]
    assert r["segments"][0]["centerline_mm"][0] == [5200, 0]
    cells = rooms(payload, "B")
    stored = cells["storage"]["furniture_placements"]["tour_mm"]["B:floor-1:storage:furniture:ceremonial-storage"]
    assert r["segments"][-1]["centerline_mm"][-1][1] == stored["aabb"]["minY"]
    assert "transport_review" not in cells["shrine"]["tour_features"]


def test_storage_measurement_never_measures_poles_or_rehearses_route(tmp_path):
    raw = json.loads(model3d.PHYSICAL_ITEMS_FILE.read_text())
    raw["items"][0]["measurements"] = [
        {
            "sequence": 1,
            "dimensions": raw["items"][0]["planning_dimensions"],
            "measured_by": "test owner",
            "measured_at": "2026-10-12",
            "method": "full storage envelope",
        }
    ]
    file = tmp_path / "physical-items.json"
    file.write_text(json.dumps(raw))
    data = model3d.build_payload(
        json.loads(model3d.PROGRAM_FILE.read_text()), load_overrides(), "presentation", physical_items_path=file
    )
    r = check(data, "B-ritual-and-transport-flow")["transport"]
    assert r["storage_dimension_source"] == "measured"
    assert r["assembled_dimensions"] is None and r["transport_acceptance"] == "unknown"
    assert r["assembled_measurement"]["status"] == r["route_rehearsal"]["status"] == "unknown"
    assert "拆桿／裝桿" in r["note"]


@pytest.mark.parametrize(
    "bad",
    [
        "missing-door",
        "wrong-axis",
        "false-religious",
        "false-transport",
        "lost-worship",
        "blocked-worship",
        "broken-passage",
        "blocked-route",
        "shrunk-inventory",
        "shrine-through-route",
    ],
)
def test_b_flow_rejects_lost_owner_intent_false_approval_and_bad_movement(payload, bad):
    data = copy.deepcopy(payload)
    b = data["buildings"][1]
    cells = rooms(data, "B")
    if bad == "missing-door":
        cells["shrine"]["tour_features"]["doors"] = [
            d for d in cells["shrine"]["tour_features"]["doors"] if not d.get("purpose")
        ]
    elif bad == "wrong-axis":
        cells["shrine"]["tour_features"]["doors"][0]["ratio"] += 0.1
    elif bad.startswith("false-"):
        b["layout_review"]["ritual_access"][
            "religious_acceptance" if bad == "false-religious" else "transport_acceptance"
        ] = "passed"
    elif bad == "lost-worship":
        cells["shrine"]["tour_features"]["reserved_mm"] = []
    elif bad == "blocked-worship":
        cells["shrine"]["furniture_placements"]["tour_mm"]["B:floor-1:shrine:furniture:bench-left"]["aabb"]["maxX"] = (
            2200
        )
    elif bad == "broken-passage":
        cells["corridor1"]["tour_mm"]["y_mm"] += 100
    elif bad == "blocked-route":
        cells["storage"]["furniture_placements"]["tour_mm"]["B:floor-1:storage:furniture:dehumidifier"]["aabb"] = {
            "minX": 5100,
            "maxX": 5400,
            "minY": 14100,
            "maxY": 14500,
        }
    elif bad == "shrunk-inventory":
        cells["storage"]["furniture"][0]["width_mm"] = 900
    else:
        cells["storage"]["tour_features"]["doors"][0]["neighbor"] = cells["shrine"]["id"]
    with pytest.raises(ValueError, match="B ritual/transport"):
        build_bc_flow_checks(data["buildings"])


def test_c_open_zones_remove_every_partition_without_new_area_or_smaller_furniture(payload):
    cells, r = rooms(payload, "C"), check(payload, "C-open-living-dining")
    assert r["allocation_area_sqm"] == 33.6 and r["living_dining_area_sqm"] == 27.2 and r["added_floor_area_sqm"] == 0
    assert r["geometry"] == {"x_mm": 0, "y_mm": 3900, "w_mm": 6000, "h_mm": 5600}
    assert r["structural_acceptance"] == r["fire_acceptance"] == r["daylight_acceptance"] == "unknown"
    for a, b, width in (("entrance", "dining", 3200), ("entrance", "living", 2000), ("dining", "living", 4000)):
        assert cells[a]["space_group"] == cells[b]["space_group"] == "C1-open-living-dining"
        for key, neighbor in ((a, b), (b, a)):
            f = cells[key]["tour_features"]
            assert next(o for o in f["open_connections"] if o["neighbor"] == cells[neighbor]["id"])["width_mm"] == width
            assert not any(d["neighbor"] == cells[neighbor]["id"] for d in f["doors"])
    assert not cells["garage"]["furniture"]
    assert cells["elder"]["tour_mm"] == {"x_mm": 0, "y_mm": 13800, "w_mm": 3600, "h_mm": 3830}
    assert cells["stair1f"]["tour_mm"] == {"x_mm": 2400, "y_mm": 9500, "w_mm": 3600, "h_mm": 4300}


@pytest.mark.parametrize(
    "bad",
    [
        "partition",
        "fake-door",
        "false-fire",
        "smaller-sofa",
        "missing-table",
        "cross-zone-collision",
        "tv-on-removed-wall",
    ],
)
def test_c_open_plan_rejects_false_merge_or_shrunk_and_conflicting_products(payload, bad):
    data = copy.deepcopy(payload)
    cells = rooms(data, "C")
    if bad == "partition":
        cells["dining"]["tour_features"]["open_connections"][0]["width_mm"] = 1000
    elif bad == "fake-door":
        cells["dining"]["tour_features"]["doors"].append({"neighbor": cells["living"]["id"]})
    elif bad == "false-fire":
        data["buildings"][2]["layout_review"]["open_living"]["fire_acceptance"] = "passed"
    elif bad == "smaller-sofa":
        cells["living"]["furniture"][0]["width_mm"] = 1500
    elif bad == "missing-table":
        cells["dining"]["furniture"] = []
    elif bad == "cross-zone-collision":
        cells["dining"]["furniture_placements"]["tour_mm"]["C:floor-1:dining:furniture:dining-set"]["aabb"] = cells[
            "living"
        ]["furniture_placements"]["tour_mm"]["C:floor-1:living:furniture:sofa"]["aabb"]
    else:
        cells["living"]["furniture_placements"]["tour_mm"]["C:floor-1:living:furniture:tv"]["wall_anchor"] = "front"
    with pytest.raises(ValueError, match="C open living"):
        build_bc_flow_checks(data["buildings"])


def test_b_c_svg_features_and_manifest_have_the_same_doors_routes_and_removed_walls(payload):
    shared = plan_data(payload)
    for bid in ("B", "C"):
        b = next(b for b in shared["buildings"] if b["id"] == bid)
        floor = b["floors"][0]
        svg = render_plan(bid, floor)
        assert (ROOT / "structured/candidates/furniture-plans" / floor["plan_file"]).read_text() == svg
        tree = ET.fromstring(svg)
        if bid == "B":
            assert len(tree.findall(".//s:g[@data-transport-route]", NS)) == 4
            door = tree.find(".//s:text[@data-door-purpose='ritual-entry']", NS)
            assert door is not None and door.attrib["data-door-width-mm"] == "1800"
        else:
            for r in floor["rooms"]:
                if r["key"] not in {"living", "dining", "entrance"}:
                    continue
                group = tree.find(f".//s:g[@data-room-id='{r['id']}']", NS)
                assert group.attrib["data-space-group"] == "C1-open-living-dining"
                if r["key"] == "living":
                    assert not group.findall("s:line[@data-wall-face='front']", NS)
                if r["key"] == "dining":
                    assert not group.findall("s:line[@data-wall-face='rear']", NS)

from __future__ import annotations

import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import export_model_3d as model3d
import pytest
from lib.dimension_overrides import load_overrides
from lib.html_parametric_compare import find_cell_overlaps
from lib.model3d_placement import attach_placements, overlaps
from lib.model3d_review import review_checks
from lib.model3d_tour import attach_tour

ROOT = Path(__file__).resolve().parents[1]


def payload():
    return model3d.build_payload(
        json.loads((ROOT / "structured/room_program.json").read_text()), load_overrides(), "presentation"
    )


def test_tour_uses_a_fixed_comparison_frame_without_overlaps_or_auto_expansion():
    data = payload()
    for building in data["buildings"]:
        for floor in building["floors"]:
            assert floor["tour_status"] == "bounded-proposal-not-authoritative"
            assert (floor["tour_width_mm"], floor["tour_depth_mm"]) == (6000, 17630)
            active = [c for c in floor["cells"] if c["tour_active"]]
            assert not find_cell_overlaps(active, "tour_mm", building["id"], floor["id"])
            for cell in floor["cells"]:
                if cell["tour_active"]:
                    assert cell["tour_mm"]["x_mm"] + cell["tour_mm"]["w_mm"] <= 6000
                    assert cell["tour_mm"]["y_mm"] + cell["tour_mm"]["h_mm"] <= 17630
                assert cell["tour_features"]["stair_geometry_verified"] is False
                assert all(d["status"] != "verified" for d in cell["tour_features"]["doors"])
    a = data["buildings"][0]["floors"][0]["cells"]
    garage = next(c for c in a if c["key"] == "garage")
    assert garage["auto_mm"]["h_mm"] == 1200
    assert garage["declared_mm"]["h_mm"] == 6000
    assert garage["tour_active"] is False
    assert any(d["key"] == "garage" for d in data["buildings"][0]["floors"][0]["deferred_rooms"])


def test_tour_never_mutates_source_geometry_or_furniture():
    buildings = payload()["buildings"]
    fields = ("auto_mm", "declared_mm", "furniture", "x_mm", "y_mm", "w_mm", "h_mm")
    before = {
        c["id"]: deepcopy({k: c.get(k) for k in fields}) for b in buildings for f in b["floors"] for c in f["cells"]
    }
    attach_tour(buildings)
    after = {c["id"]: {k: c.get(k) for k in fields} for b in buildings for f in b["floors"] for c in f["cells"]}
    assert before == after


def test_cold_points_keep_full_html_evidence_and_no_fake_b_shrine_aircon():
    cells = {c["id"]: c for b in payload()["buildings"] for f in b["floors"] for c in f["cells"]}
    assert cells["C:floor-1:elder"]["hvac"]["indoor"]
    assert any("床頭不直吹" in v for v in cells["C:floor-1:elder"]["hvac"]["evidence"])
    assert cells["C:floor-1:service"]["hvac"]["outdoor"]
    assert not cells["B:floor-1:shrine"]["hvac"]["indoor"]
    assert not cells["A:floor-4:laundry-rf"]["hvac"]["indoor"]
    assert not cells["C:floor-4:platform"]["hvac"]["indoor"]
    assert cells["B:floor-1:shrine"]["tour_features"]["window_face"] == "front"
    assert cells["B:floor-1:stair1"]["tour_features"]["stairs"]
    storage = cells["B:floor-1:storage"]
    assert any(d["width_mm"] == 1500 for d in storage["tour_features"]["doors"])
    assert storage["furniture"][0]["width_mm"] == 1200
    assert cells["A:floor-1:living"]["auto_mm"]["y_mm"] == 1200


def test_proposed_interior_openings_are_paired_without_becoming_verified_routes():
    for b in payload()["buildings"]:
        for f in b["floors"]:
            cells = {c["id"]: c for c in f["cells"]}
            inverse = {"front": "rear", "rear": "front", "left": "right", "right": "left"}
            for geometry, feature in (
                ("tour_mm", "tour_features"),
                ("auto_mm", "architecture_auto"),
                ("declared_mm", "architecture_declared"),
            ):
                for cell in cells.values():
                    assert cell[feature]["geometry_source"] == geometry
                    for door in cell[feature]["doors"]:
                        assert 0 <= door["ratio"] <= 1
                        g = cell[geometry]
                        axis, length = ("x_mm", "w_mm") if door["face"] in ("front", "rear") else ("y_mm", "h_mm")
                        centre = g[axis] + door["ratio"] * g[length]
                        assert centre - door["width_mm"] / 2 >= g[axis] - 0.1
                        assert centre + door["width_mm"] / 2 <= g[axis] + g[length] + 0.1
                        if door["neighbor"]:
                            other = cells[door["neighbor"]]
                            pair = next(d for d in other[feature]["doors"] if d["neighbor"] == cell["id"])
                            assert pair["face"] == inverse[door["face"]]
                            assert pair["width_mm"] == door["width_mm"]
                            assert abs(other[geometry][axis] + pair["ratio"] * other[geometry][length] - centre) < 0.1


def test_access_proposals_do_not_route_through_bathroom_or_storage():
    cells = {c["id"]: c for b in payload()["buildings"] for f in b["floors"] for c in f["cells"]}
    shrine = cells["B:floor-1:shrine"]["tour_features"]
    assert not shrine["access_pending"]
    assert {d["neighbor"] for d in shrine["doors"]} == {"B:floor-1:entry"}
    assert {d["neighbor"] for d in cells["B:floor-1:storage"]["tour_features"]["doors"]} == {"B:floor-1:corridor1"}
    assert cells["A:floor-1:dining"]["tour_active"] is False  # merged, not deleted from the source
    assert cells["A:floor-1:living"]["name"] == "前段合併客餐廳（前帶可建待核）"
    elder_bath = cells["C:floor-1:elder-bath"]["tour_features"]
    assert not elder_bath["access_pending"]
    assert {d["neighbor"] for d in elder_bath["doors"]} == {"C:floor-1:elder"}


def test_hvac_pairing_uses_routed_lengths_without_inventing_model_approval():
    data = payload()
    routes = data["layout_review"]["hvac_routes"]
    assert len(routes) == 17
    all_cells = {c["id"]: c for b in data["buildings"] for f in b["floors"] for c in f["cells"]}
    for route in routes:
        assert route["compliance"] == "unknown" and route["model"] is None and route["manual_source"] is None
        assert route["max_pipe_length_mm"] is None and route["max_elevation_mm"] is None
        points = route["polyline_mm"]
        length = sum(sum(abs(a[i] - b[i]) for i in range(3)) for a, b in zip(points, points[1:], strict=False))
        assert route["estimated_routed_length_mm"] == round(length + route["bend_service_allowance_mm"])
        assert any(
            u["id"] == route["id"] and u["type"] == "indoor"
            for u in all_cells[route["indoor_room"]]["tour_features"]["hvac_units"]
        )
        assert any(
            u["id"] == route["id"] and u["type"] == "outdoor"
            for u in all_cells[route["outdoor_room"]]["tour_features"]["hvac_units"]
        )
    assert all(":floor-4:" not in r["outdoor_room"] for r in routes if r["id"].startswith("A-"))


def test_parking_is_separate_from_public_frontage_and_unverified_capacity():
    data = payload()
    for building in data["buildings"]:
        parking = building["layout_review"]["parking"]
        assert parking["verified_spaces"] is None
        floor = building["floors"][0]
        vehicles = [i for c in floor["cells"] for i in c["furniture"] if i["category"] == "vehicle"]
        assert parking["displayed_cars"] == 0 and not vehicles
        garage = next(c for c in floor["cells"] if c["key"] == "garage")
        if building["id"] == "A":
            assert parking["status"] == "not-accommodated-in-care-priority-proposal"
            assert parking["alternative_bay_mm"] == [3000, 6100]
            assert not garage["tour_active"]
        else:
            assert garage["tour_mm"]["h_mm"] == 3900
        assert garage["deferred_furniture_assignment"]  # original wish not silently fulfilled


def test_every_first_floor_keeps_clear_furniture_and_does_not_expand_for_larger_items():
    buildings = payload()["buildings"]
    frame = [(f["tour_width_mm"], f["tour_depth_mm"]) for b in buildings for f in b["floors"]]
    for building in buildings:
        for cell in building["floors"][0]["cells"]:
            assert all(not p["issues"] for p in cell["furniture_placements"]["tour_mm"].values())
    bed = next(c for c in buildings[2]["floors"][0]["cells"] if c["key"] == "elder")
    bed["furniture"][0]["width_mm"] = 6500
    attach_placements(buildings)
    assert bed["furniture"][0]["width_mm"] == 6500
    assert bed["furniture_placements"]["tour_mm"][bed["furniture"][0]["id"]]["status"] == "pending-layout"
    assert frame == [(f["tour_width_mm"], f["tour_depth_mm"]) for b in buildings for f in b["floors"]]


def test_b_storage_has_a_continuous_straight_band_without_routing_through_shrine():
    floor = payload()["buildings"][1]["floors"][0]
    cells = {c["key"]: c for c in floor["cells"]}
    front, rear, store = (cells[k] for k in ("entry", "corridor1", "storage"))
    for c in (front, rear):
        assert c["tour_mm"]["x_mm"] == 4400 and c["tour_mm"]["w_mm"] == 1600
        assert not c["furniture"]
    assert front["tour_mm"]["y_mm"] + front["tour_mm"]["h_mm"] == rear["tour_mm"]["y_mm"]
    assert rear["tour_mm"]["y_mm"] + rear["tour_mm"]["h_mm"] == store["tour_mm"]["y_mm"]
    assert store["tour_features"]["carry_path_mm"] == {"center_x_mm": 5200, "width_mm": 1600}
    assert not store["tour_features"]["stair_geometry_verified"]


def test_aligned_u_stairs_and_c_care_reserves_are_not_approval():
    for building in payload()["buildings"]:
        footprints = []
        for floor in building["floors"]:
            stair = next(c for c in floor["cells"] if c.get("tour_active") and c["kind"] == "stair")
            features = stair["tour_features"]
            footprints.append(features["stair_footprint_mm"])
            flight = features["stair_geometry"]
            assert flight["type"] == "two-flight-u-proposal" and flight["fits_reserved_box"]
            assert flight["connects_to_next_storey"] is (floor["id"] != "floor-4")
            assert flight["risers"] == 18 and flight["tread_mm"] == 270
            assert flight["flight_width_mm"] == flight["landing_mm"] == 1000
            assert features["stair_geometry_verified"] is False
        assert footprints == [footprints[0]] * 4
    elder = next(c for c in payload()["buildings"][2]["floors"][0]["cells"] if c["key"] == "elder")
    care = [r["aabb"] for r in elder["tour_features"]["reserved_mm"] if r["kind"] in {"care-route", "care-turn"}]
    assert len(care) == 2
    for item in elder["furniture_placements"]["tour_mm"].values():
        assert not item["issues"]
        assert all(not overlaps(item["aabb"], reserve) for reserve in care)


def test_b_shrine_projection_rejects_roof_equipment_even_when_first_floor_fits():
    buildings = payload()["buildings"]
    buffer = next(c for c in buildings[1]["floors"][3]["cells"] if c["key"] == "shrine-buffer-rf")
    buffer["name"] = "熱泵候選區"
    with pytest.raises(ValueError, match="B shrine projection"):
        review_checks(buildings)


def test_overlay_label_algorithm_without_browser():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the browser-independent label algorithm tests")
    result = subprocess.run(
        [node, "--test", str(ROOT / "tests/js/model3d-overlay.test.cjs")], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr

from __future__ import annotations

import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

import export_model_3d as model3d
import pytest
from lib.dimension_overrides import load_overrides
from lib.model3d_placement import GEOMETRIES, INSET, ROTATION, attach_placements, overlaps
from lib.model3d_plan import plan_data, render_plan, write_html_plans

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "structured/candidates/furniture-plans"
NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture(scope="module")
def data():
    return model3d.build_payload(
        json.loads((ROOT / "structured/room_program.json").read_text()), load_overrides(), "presentation"
    )


def cells(data):
    return {c["id"]: c for b in data["buildings"] for f in b["floors"] for c in f["cells"]}


def test_committed_html_manifest_and_all_svgs_match_fresh_3d_data(data):
    source = (PLANS / "layout.js").read_text()
    html_data = json.loads(source.removeprefix("window.HOUSE_CONCEPT_LAYOUT = ").removesuffix(";\n"))
    assert html_data == plan_data(data), "Re-export 3D and HTML furniture plans together"
    model_cells = cells(data)
    room_count = item_count = floor_count = 0
    for b in html_data["buildings"]:
        for f in b["floors"]:
            floor_count += 1
            svg_source = (PLANS / f["plan_file"]).read_text()
            assert svg_source == render_plan(b["id"], f)
            svg = ET.fromstring(svg_source)
            rooms = {r.attrib["data-room-id"]: r for r in svg.findall("s:g[@data-room-id]", NS)}
            for room in f["rooms"]:
                cell = model_cells[room["id"]]
                assert room["geometry"] == cell["tour_mm"]
                assert room["features"] == cell["tour_features"]
                for k in ("x", "y", "w", "h"):
                    assert float(rooms[room["id"]].attrib[f"data-{k}-mm"]) == room["geometry"][f"{k}_mm"]
                items = {
                    i.attrib["data-furniture-id"]: i for i in rooms[room["id"]].findall("s:g[@data-furniture-id]", NS)
                }
                assert items.keys() == cell["furniture_placements"]["tour_mm"].keys()
                for item in room["furniture"]:
                    p = cell["furniture_placements"]["tour_mm"][item["id"]]
                    node = items[item["id"]]
                    assert node.attrib["data-status"] == p["status"]
                    for k in ("center_x_mm", "center_y_mm", "rotation_deg", "mount_height_mm"):
                        assert float(node.attrib["data-" + k.replace("_", "-")]) == p[k]
                    for k in ("width_mm", "depth_mm", "height_mm"):
                        assert float(node.attrib["data-" + k.replace("_", "-")]) == item[k]
                    item_count += 1
                room_count += 1
    assert (floor_count, room_count, item_count) == (12, 105, 129)


def test_displayable_furniture_is_clear_and_unsatisfied_furniture_remains_explicit(data):
    for cell in cells(data).values():
        g = cell["tour_mm"]
        placements = cell["furniture_placements"]["tour_mm"]
        for item in cell["furniture"]:
            p = placements[item["id"]]
            if p["issues"]:
                assert p["status"] == "pending-layout"
                continue
            assert p["status"] == "planning-not-measured"
            box = p["aabb"]
            assert box["minX"] >= g["x_mm"] + 79
            assert box["maxX"] <= g["x_mm"] + g["w_mm"] - 79
            assert box["minY"] >= g["y_mm"] + 79
            assert box["maxY"] <= g["y_mm"] + g["h_mm"] - 79
            for zone in cell["tour_features"]["reserved_mm"]:
                assert not overlaps(box, zone["aabb"]), (item["id"], zone)
                if p["operation_mm"] and zone["kind"] not in item.get("shared_operation_with", []):
                    assert not overlaps(p["operation_mm"], zone["aabb"]), (item["id"], zone)
            if item["wall_anchor"]:
                face = p["wall_anchor"]
                assert p["rotation_deg"] == ROTATION[face]
                gap = {
                    "rear": g["y_mm"] + g["h_mm"] - box["maxY"],
                    "front": box["minY"] - g["y_mm"],
                    "left": box["minX"] - g["x_mm"],
                    "right": g["x_mm"] + g["w_mm"] - box["maxX"],
                }[face]
                assert gap == pytest.approx(item["wall_gap_mm"], abs=0.02)
                assert p["operation_mm"] or item["front_clearance_mm"] == 0
        fitted = [p for p in placements.values() if not p["issues"]]
        for i, a in enumerate(fitted):
            for b in fitted[i + 1 :]:
                assert not overlaps(a["aabb"], b["aabb"])
                if a["operation_mm"]:
                    assert not overlaps(a["operation_mm"], b["aabb"])
                if b["operation_mm"]:
                    assert not overlaps(b["operation_mm"], a["aabb"])


@pytest.mark.parametrize(
    "room_id,vanity_id",
    [
        ("A:floor-2:master-bath", "vanity-60"),
        ("B:floor-2:bath2", "vanity-60"),
        ("B:floor-2:master-bath2", "vanity-90"),
    ],
)
def test_upstairs_bathrooms_keep_three_full_size_fixtures_and_operating_space(data, room_id, vanity_id):
    room = cells(data)[room_id]
    catalogue = json.loads((ROOT / "inputs/furniture-layout.json").read_text())["catalog"]
    assert {item["catalog_id"] for item in room["furniture"]} == {vanity_id, "toilet", "shower-90"}
    assert len(room["furniture"]) == 3
    for item in room["furniture"]:
        assert all(item[key] == catalogue[item["catalog_id"]][key] for key in ("width_mm", "depth_mm", "height_mm"))
        assert item["front_clearance_mm"] == 700
        assert item["shared_operation_with"] == []  # no new exception to force a fit
        assert item["basis"] == "room-use-inference"
        assert "非原HTML承諾或實測" in " ".join(item["evidence"])
        p = room["furniture_placements"]["tour_mm"][item["id"]]
        assert not p["issues"] and p["status"] == "planning-not-measured"
        op = p["operation_mm"]
        axis = "Y" if p["wall_anchor"] in {"front", "rear"} else "X"
        assert op[f"max{axis}"] - op[f"min{axis}"] == 700
    # Keep the original HTML assignment and its location restrictions, not a
    # new claim that all of the original private/wet-core requirements passed.
    original = json.loads((ROOT / "inputs/furniture-layout.json").read_text())["rooms"][room_id]
    assert room["deferred_furniture_assignment"] == original


@pytest.mark.parametrize("room_id,gap_mm", [("A:floor-2:master-bath", 151.8), ("B:floor-2:bath2", 180)])
def test_upstairs_toilet_has_real_side_gap_instead_of_merely_nonoverlapping_bodies(data, room_id, gap_mm):
    room = cells(data)[room_id]
    placements = room["furniture_placements"]["tour_mm"]
    by_shape = {item["shape"]: placements[item["id"]] for item in room["furniture"]}
    assert by_shape["toilet"]["wall_anchor"] == by_shape["vanity"]["wall_anchor"] == "front"
    gap = by_shape["toilet"]["aabb"]["minX"] - by_shape["vanity"]["aabb"]["maxX"]
    assert gap == pytest.approx(gap_mm) and gap >= 150
    # A planning side gap, not an accessibility or statutory approval. The
    # old 2200mm room let the solver move the toilet flush against the basin.
    assert all("待" in item["note"] for item in room["furniture"] if item["shape"] == "toilet")


def test_upstairs_partition_transfer_preserves_total_bands_and_other_room_outlines(data):
    rooms = cells(data)
    a_bath, closet = (rooms[key]["tour_mm"] for key in ("A:floor-2:master-bath", "A:floor-2:walkin"))
    assert a_bath == {"x_mm": 0, "y_mm": 4000, "w_mm": 2400, "h_mm": 2100}
    assert closet == {"x_mm": 2400, "y_mm": 4000, "w_mm": 2000, "h_mm": 2100}
    assert a_bath["w_mm"] + closet["w_mm"] == 4400
    assert rooms["A:floor-2:master"]["tour_mm"] == {"x_mm": 0, "y_mm": 1500, "w_mm": 4400, "h_mm": 2500}
    assert rooms["A:floor-2:study"]["tour_mm"] == {"x_mm": 0, "y_mm": 10400, "w_mm": 3600, "h_mm": 5230}
    assert rooms["A:floor-2:bedroom2"]["tour_mm"] == {"x_mm": 3600, "y_mm": 10400, "w_mm": 2400, "h_mm": 5230}
    public, ensuite = (rooms[key]["tour_mm"] for key in ("B:floor-2:bath2", "B:floor-2:master-bath2"))
    assert public == {"x_mm": 0, "y_mm": 13800, "w_mm": 3000, "h_mm": 2000}
    assert ensuite == {"x_mm": 0, "y_mm": 15800, "w_mm": 3000, "h_mm": 1830}
    assert public["y_mm"] + public["h_mm"] == ensuite["y_mm"]
    assert public["h_mm"] + ensuite["h_mm"] == 3830
    assert rooms["B:floor-2:master2"]["tour_mm"] == {"x_mm": 3000, "y_mm": 13800, "w_mm": 3000, "h_mm": 3830}
    assert data["layout_review"]["status"] == "proposal-owner-and-architect-review-pending"
    for building in data["buildings"]:
        for floor in building["floors"]:
            assert (floor["tour_width_mm"], floor["tour_depth_mm"]) == (6000, 17630)


def test_upstairs_cabinet_avoids_doors_but_working_and_passing_are_not_simultaneous(data):
    hall = cells(data)["A:floor-2:hall2"]
    item = hall["furniture"][0]
    p = hall["furniture_placements"]["tour_mm"][item["id"]]
    assert (item["width_mm"], item["depth_mm"], item["height_mm"]) == (2400, 400, 2200)
    assert not p["issues"] and p["wall_anchor"] == "right"
    inside_left = hall["tour_mm"]["x_mm"] + INSET
    assert p["aabb"]["minX"] - inside_left == 1040
    assert p["operation_mm"]["minX"] - inside_left == 440
    assert item["front_clearance_mm"] == 600
    assert item["shared_operation_with"] == []
    assert "不能同時當通道" in item["note"] and "必要時櫃體另移" in item["note"]


def test_only_two_original_full_size_closet_wardrobes_are_pending(data):
    rooms = cells(data)
    pending = {
        p["id"] for room in rooms.values() if room.get("tour_active")
        for p in room["furniture_placements"]["tour_mm"].values() if p["issues"]
    }
    assert pending == {
        "A:floor-2:walkin:furniture:wardrobe-left", "A:floor-2:walkin:furniture:wardrobe-right"
    }
    closet = rooms["A:floor-2:walkin"]
    assert "profile" not in closet["review_spec"]  # do not substitute smaller products
    assert len(closet["furniture"]) == 2
    for item in closet["furniture"]:
        assert item["catalog_id"] == "wardrobe-180"
        assert (item["width_mm"], item["depth_mm"], item["height_mm"]) == (1800, 600, 2200)
        assert item["front_clearance_mm"] == 600
        p = closet["furniture_placements"]["tour_mm"][item["id"]]
        assert p["status"] == "pending-layout" and "door-approach" in p["issues"]


@pytest.mark.parametrize("room_id", ["A:floor-2:master-bath", "B:floor-2:bath2", "B:floor-2:master-bath2"])
def test_upstairs_oversized_fixture_is_pending_without_shrinking_or_hiding_it(data, room_id):
    buildings = deepcopy(data["buildings"])
    room = cells({"buildings": buildings})[room_id]
    fixture = next(item for item in room["furniture"] if item["shape"] == "vanity")
    fixture["width_mm"] = 6000
    attach_placements(buildings)
    assert fixture["width_mm"] == 6000
    assert fixture in room["furniture"]
    p = room["furniture_placements"]["tour_mm"][fixture["id"]]
    assert p["status"] == "pending-layout" and "overflow" in p["issues"]


def test_stair_equipment_is_same_hall_with_no_invented_partition_or_door(data):
    all_cells = cells(data)
    for a_id, b_id in (("A:floor-1:mdf", "A:floor-1:stair-door"), ("B:floor-1:idf-cabinet", "B:floor-1:stair1")):
        a, b = all_cells[a_id], all_cells[b_id]
        assert a["space_group"] == b["space_group"] != ""
        for _geometry, feature in GEOMETRIES:
            assert b_id in {o["neighbor"] for o in a[feature]["open_connections"]}
            assert a_id in {o["neighbor"] for o in b[feature]["open_connections"]}
            assert not any(d["neighbor"] == b_id for d in a[feature]["doors"])
            assert not any(d["neighbor"] == a_id for d in b[feature]["doors"])
    b = all_cells["B:floor-1:idf-cabinet"]
    assert b["furniture"][0]["catalog_id"] == "rack-15u"
    assert "有界合理性提案" in " ".join(b["furniture"][0]["evidence"])
    assert not all_cells["C:floor-1:stair1f"]["furniture"]
    c = all_cells["C:floor-1:sideyard"]
    p = next(iter(c["furniture_placements"]["tour_mm"].values()))
    assert p["wall_anchor"] == "rear" and p["mount_height_mm"] == 1100
    assert not p["issues"]
    rack = all_cells["A:floor-1:mdf"]["furniture"][0]
    assert rack["wall_gap_mm"] == 650  # source requires 600mm rear maintenance


def test_palanquin_keeps_registry_size_and_straight_pull_band(data):
    storage = cells(data)["B:floor-1:storage"]
    item = storage["furniture"][0]
    p = storage["furniture_placements"]["tour_mm"][item["id"]]
    assert (item["width_mm"], item["depth_mm"], item["height_mm"]) == (1200, 1700, 1800)
    assert item["physical_dimension_source"] == "planning"
    path = storage["tour_features"]["carry_path_mm"]
    assert p["center_x_mm"] == path["center_x_mm"]
    assert path["width_mm"] == 1600
    assert any(z["kind"] == "transport-band" for z in storage["tour_features"]["reserved_mm"])
    assert storage["tour_features"]["stair_geometry_verified"] is False


def test_restricted_geometry_never_shrinks_items_or_claims_a_fit(data):
    buildings = deepcopy(data["buildings"])
    cell = buildings[0]["floors"][0]["cells"][2]
    original_items = deepcopy(cell["furniture"])
    cell["tour_mm"].update(w_mm=500, h_mm=500)
    attach_placements(buildings)
    assert cell["furniture"] == original_items
    assert all(
        p["status"] == "pending-layout" and p["issues"] for p in cell["furniture_placements"]["tour_mm"].values()
    )
    # Other source geometries still retain their own constraints.
    assert any(p["issues"] for c in cells(data).values() for p in c["furniture_placements"]["auto_mm"].values())


def test_dining_envelopes_include_real_table_and_chairs(data):
    items = [i for c in cells(data).values() for i in c["furniture"] if i["shape"] == "dining-set"]
    assert items
    for item in items:
        assert item["depth_mm"] >= item["table_depth_mm"] + 2 * 450 + 100
        assert item["width_mm"] > item["table_width_mm"]


def test_coffee_tables_and_tvs_stay_aligned_with_sofas_or_beds(data):
    for cell in cells(data).values():
        placements = cell["furniture_placements"]["tour_mm"]
        for item in cell["furniture"]:
            p = placements[item["id"]]
            if p["issues"]:
                continue
            if item["in_front_of"]:
                sofa = placements[item["in_front_of"]]
                assert p["center_x_mm"] == sofa["center_x_mm"]
                assert p["rotation_deg"] == sofa["rotation_deg"] == 0
                assert sofa["aabb"]["minY"] - p["aabb"]["maxY"] == pytest.approx(item["front_gap_mm"], abs=0.02)
            if item["aligned_with"]:
                ref = placements[item["aligned_with"]]
                axis = "center_y_mm" if p["wall_anchor"] in {"left", "right"} else "center_x_mm"
                assert p[axis] == ref[axis]
                assert (p["rotation_deg"] - ref["rotation_deg"]) % 360 == 180


def test_wider_measured_palanquin_is_pending_instead_of_false_transport_fit(data):
    buildings = deepcopy(data["buildings"])
    storage = cells({"buildings": buildings})["B:floor-1:storage"]
    storage["furniture"][0]["width_mm"] = 1700
    attach_placements(buildings)
    p = storage["furniture_placements"]["tour_mm"][storage["furniture"][0]["id"]]
    assert p["status"] == "pending-layout"
    assert "transport-width" in p["issues"]


def test_cyclic_furniture_relationship_fails_instead_of_silently_drifting(data):
    buildings = deepcopy(data["buildings"])
    room = buildings[0]["floors"][0]["cells"][2]
    sofa, linked = room["furniture"][:2]
    linked["in_front_of"] = sofa["id"]
    sofa["aligned_with"] = linked["id"]
    with pytest.raises(ValueError, match="Cyclic furniture relationship"):
        attach_placements(buildings)


@pytest.mark.parametrize("filename", ["model3d-placement.test.cjs", "html-furniture-bridge.test.cjs", "model3d-facade.test.cjs", "model3d-facade-runtime.test.cjs"])
def test_actual_js_layout_and_html_installation_without_browser(filename):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for actual renderer/HTML bridge algorithm tests")
    result = subprocess.run([node, str(ROOT / "tests/js" / filename)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_owner_consistency_detects_stale_shared_plan_and_svg(data, tmp_path):
    from house_design.owner_consistency import _check_shared_plans

    directory = tmp_path / "structured/candidates/furniture-plans"
    write_html_plans(data, directory)
    findings = []

    def add(status, title, source, detail):
        findings.append({"status": status, "title": title, "source": source, "detail": detail})

    _check_shared_plans(tmp_path, "B", data, add)
    assert len(findings) == 6
    assert all(f["status"] == "consistent" for f in findings)
    manifest = deepcopy(plan_data(data))
    manifest["buildings"][1]["floors"][0]["rooms"][0]["geometry"]["h_mm"] += 1
    (directory / "layout.js").write_text("window.HOUSE_CONCEPT_LAYOUT = " + json.dumps(manifest) + ";\n")
    (directory / "B_floor-1.svg").write_text("stale drawing")
    findings.clear()
    _check_shared_plans(tmp_path, "B", data, add)
    assert findings[0]["status"] == "stale"
    assert findings[1]["status"] == "stale"
    assert findings[-1]["status"] == "consistent"  # separate facade SVG is unchanged
    (directory / "B_facade-front.svg").write_text("stale facade")
    findings.clear()
    _check_shared_plans(tmp_path, "B", data, add)
    assert findings[-1]["status"] == "stale"
    (directory / "layout.js").write_text("not valid data")
    findings.clear()
    _check_shared_plans(tmp_path, "B", data, add)
    assert findings[0]["status"] == "insufficient"

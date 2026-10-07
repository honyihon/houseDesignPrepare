"""C1F use alternatives: bounded layout proof, not buildability approval."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import export_model_3d as model3d
import pytest
from lib.dimension_overrides import load_overrides
from lib.model3d_placement import overlaps
from lib.model3d_plan import plan_data, render_plan, write_html_plans
from lib.model3d_review import frontage_study

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "structured/candidates/furniture-plans"
NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture(scope="module")
def payload():
    return model3d.build_payload(
        json.loads((ROOT / "structured/room_program.json").read_text()), load_overrides(), "presentation"
    )


def rooms(payload):
    return {c["key"]: c for c in payload["buildings"][2]["floors"][0]["cells"] if c.get("tour_active")}


def test_reassigned_ac_alcove_increases_living_dining_without_expanding_frame_or_stairs(payload):
    cells = rooms(payload)
    assert set(cells) == {
        "garage", "entrance", "dining", "living", "kitchen", "stair1f",
        "sideyard", "sliding-door", "elder", "elder-bath", "service",
    }
    expected = {
        "garage": [0, 0, 6000, 3900],
        "dining": [0, 3900, 4000, 3200],
        "entrance": [4000, 3900, 2000, 3200],
        "living": [0, 7100, 6000, 2400],
        "kitchen": [0, 9500, 2400, 2600],
        "stair1f": [2400, 9500, 3600, 4300],
        "elder": [0, 13800, 3600, 3830],
        "elder-bath": [3600, 13800, 2400, 3000],
    }
    for key, rect in expected.items():
        assert list(cells[key]["tour_mm"].values()) == rect
    def area(cell):
        return cell["tour_mm"]["w_mm"] * cell["tour_mm"]["h_mm"]
    assert sum(area(c) for c in cells.values()) == 6000 * 17630
    assert area(cells["living"]) + area(cells["dining"]) == (24 + 3.2) * 1e6
    assert not cells["sideyard"]["is_outdoor"]
    assert cells["sideyard"]["space_group"] == cells["sliding-door"]["space_group"] == "C1-dry-hall"
    assert not cells["stair1f"]["furniture"]
    assert cells["sideyard"]["furniture"][0]["category"] == "network"


def test_dining_lounge_and_care_reserves_keep_normal_products_and_clear_operation(payload):
    cells = rooms(payload)
    catalog = json.loads((ROOT / "inputs/furniture-layout.json").read_text())["catalog"]
    for key, products in {
        "dining": {"dining-4"}, "living": {"sofa-2", "wall-tv", "coffee-table", "reading-chair"},
        "kitchen": {"counter-240-60", "fridge-75"}, "elder": {"queen-bed", "wall-tv", "wardrobe-120"},
    }.items():
        room = cells[key]
        assert {i["catalog_id"] for i in room["furniture"]} == products
        for item in room["furniture"]:
            p = room["furniture_placements"]["tour_mm"][item["id"]]
            assert not p["issues"] and p["status"] == "planning-not-measured"
            assert all(item[k] == catalog[item["catalog_id"]][k] for k in ("width_mm", "depth_mm", "height_mm"))
            for zone in room["tour_features"]["reserved_mm"]:
                assert not overlaps(p["aabb"], zone["aabb"])
                if p["operation_mm"] and zone["kind"] not in item["shared_operation_with"]:
                    assert not overlaps(p["operation_mm"], zone["aabb"])
    living = cells["living"]
    placements = living["furniture_placements"]["tour_mm"]
    sofa, tv, table = (placements[living["id"] + ":furniture:" + key] for key in ("sofa", "tv", "coffee-table"))
    assert sofa["wall_anchor"] == "rear" and tv["wall_anchor"] == "front"
    assert sofa["center_x_mm"] == tv["center_x_mm"] == table["center_x_mm"]
    assert sofa["aabb"]["minY"] - table["aabb"]["maxY"] == 400
    assert any(z["kind"] == "care-turn" and z["aabb"]["maxX"] - z["aabb"]["minX"] == 1500
               for z in living["tour_features"]["reserved_mm"])
    assert cells["dining"]["deferred_furniture_assignment"]["profile"] == "dining-six"
    assert cells["garage"]["deferred_furniture_assignment"]["profile"] == "garage-two-plus-motorcycle"


def test_c_kitchen_uses_distinct_60cm_candidate_not_silent_original_product_resize(payload):
    kitchen = rooms(payload)["kitchen"]
    counter = next(i for i in kitchen["furniture"] if i["shape"] == "counter")
    catalog = json.loads((ROOT / "inputs/furniture-layout.json").read_text())["catalog"]
    assert (counter["width_mm"], counter["depth_mm"], counter["height_mm"]) == (2400, 600, 900)
    assert catalog["counter-240"]["depth_mm"] == 650
    assert catalog["sofa-3"]["width_mm"] == 2400
    assert counter["shared_operation_with"] == ["door-approach"]
    assert counter["front_clearance_mm"] == 900
    assert "非把原240×65cm代表型號縮薄" in counter["note"]
    assert kitchen["deferred_furniture_assignment"]


def test_frontage_study_is_uninstalled_and_separated_from_route_and_indoor_furniture(payload):
    garage = rooms(payload)["garage"]
    study = garage["tour_features"]["frontage_study"]
    assert study["status"] == "conditional-not-installed"
    assert study["active_option"] == "keep-full-clear" and study["site_use_status"] == "unknown"
    assert not garage["furniture"] and len(study["conditions"]) == 4
    assert study["route_mm"] == {"x_mm": 3800, "y_mm": 0, "w_mm": 2120, "h_mm": 3900}
    assert [z["id"] for z in study["zones"]] == ["garden-pocket", "waiting-bench"]
    assert study["zones"][1]["rect"] == [1800, 2200, 1200, 500]
    assert payload["buildings"][2]["layout_review"]["parking"]["verified_spaces"] is None
    assert sum(len(c["furniture"]) for b in payload["buildings"] for f in b["floors"] for c in f["cells"]) == 129
    for building in payload["buildings"]:
        for floor in building["floors"]:
            for room in floor["cells"]:
                if room["id"] != garage["id"]:
                    assert "frontage_study" not in room["tour_features"]


@pytest.mark.parametrize("bad", ["outside", "route", "overlap", "height", "installed", "verified", "furniture", "indoor"])
def test_invalid_or_false_authoritative_frontage_options_are_rejected(payload, bad):
    cell = copy.deepcopy(rooms(payload)["garage"])
    raw = cell["review_spec"]["frontage_study"]
    if bad == "outside":
        raw["zones"][0]["rect"][2] = 7000
    elif bad == "route":
        raw["zones"][0]["rect"] = [3800, 900, 1000, 2000]
    elif bad == "overlap":
        raw["zones"][1]["rect"] = raw["zones"][0]["rect"]
    elif bad == "height":
        raw["zones"][0]["height_mm"] = float("nan")
    elif bad == "installed":
        raw["active_option"] = "garden"
    elif bad == "verified":
        raw["site_use_status"] = "verified"
    elif bad == "furniture":
        cell["furniture"] = [{"id": "fake-installed-bench"}]
    elif bad == "indoor":
        cell["is_outdoor"] = False
    with pytest.raises(ValueError, match="Frontage study|Invalid frontage"):
        frontage_study(cell)


def test_ac_relocation_keeps_all_pairs_and_uses_existing_2f_balcony_without_approval(payload):
    routes = {r["id"]: r for r in payload["layout_review"]["hvac_routes"]}
    assert len(routes) == 17
    assert routes["C-AC01"]["indoor_room"] == "C:floor-1:living"
    assert routes["C-AC01"]["outdoor_room"] == routes["C-AC03"]["outdoor_room"] == "C:floor-2:balcony2f"
    assert (routes["C-AC01"]["estimated_routed_length_mm"], routes["C-AC01"]["elevation_difference_mm"]) == (14645, 1150)
    assert routes["C-AC01"]["manual_source"] is None and routes["C-AC01"]["compliance"] == "unknown"
    balcony = next(c for c in payload["buildings"][2]["floors"][1]["cells"] if c["key"] == "balcony2f")
    assert balcony["tour_mm"]["h_mm"] == 3900
    assert {u["id"] for u in balcony["tour_features"]["hvac_units"]} == {"C-AC01", "C-AC03"}


def test_base_and_optional_html_plans_and_embedded_3d_match_full_shared_payload(payload):
    shared = plan_data(payload)
    viewer = (ROOT / "structured/candidates/model3d.html").read_text()
    embedded = re.search(r"var DATA = (\{.+?\});\n", viewer)
    assert embedded
    stored = json.loads(embedded[1])
    for key in ("schema", "standards", "buildings", "furniture", "layout_review", "facade"):
        assert stored[key] == payload[key], f"Stale embedded 3D {key}"
    for building in shared["buildings"]:
        for floor in building["floors"]:
            if (building["id"], floor["id"]) != ("C", "floor-1"):
                assert "frontage_study_file" not in floor
                continue
            base = ET.fromstring(render_plan(building["id"], floor))
            assert not base.findall(".//s:g[@data-frontage-study]", NS)
            candidate = render_plan(building["id"], floor, show_frontage_study=True)
            assert (PLANS / floor["frontage_study_file"]).read_text() == candidate
            tree = ET.fromstring(candidate)
            zones = {n.attrib["data-study-zone"]: n for n in tree.findall(".//s:rect[@data-study-zone]", NS)}
            study = rooms(payload)["garage"]["tour_features"]["frontage_study"]
            for key, g in [("clear-route", study["route_mm"]), *((z["id"], z["geometry"]) for z in study["zones"])]:
                assert zones[key].attrib["fill"] == "none"
                assert [float(zones[key].attrib[k]) for k in ("x", "y", "width", "height")] == list(g.values())
            assert {i.attrib["data-furniture-id"] for i in base.findall(".//s:g[@data-furniture-id]", NS)} == {
                i.attrib["data-furniture-id"] for i in tree.findall(".//s:g[@data-furniture-id]", NS)
            }


def test_owner_consistency_review_detects_stale_optional_frontage_plan(payload, tmp_path):
    from house_design.owner_consistency import _check_shared_plans

    directory = tmp_path / "structured/candidates/furniture-plans"
    write_html_plans(payload, directory)
    findings = []
    def add(status, title, source, detail):
        findings.append({"status": status, "title": title, "source": source, "detail": detail})
    _check_shared_plans(tmp_path, "C", payload, add)
    title = "HTML 前院待核比較是否使用當前 3D 虛框"
    assert next(f for f in findings if f["title"] == title)["status"] == "consistent"
    file = directory / "C_floor-1_frontage-study.svg"
    file.write_text(file.read_text().replace('width="1200"', 'width="1250"', 1))
    findings.clear()
    _check_shared_plans(tmp_path, "C", payload, add)
    assert next(f for f in findings if f["title"] == title)["status"] == "stale"

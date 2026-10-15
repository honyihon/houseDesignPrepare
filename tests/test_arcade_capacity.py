"""Independent 32-ping capacity evidence, not approval by matched renderers."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import export_arcade_capacity as exporter
import export_model_3d as model3d
import pytest
from lib.dimension_overrides import load_overrides
from lib.model3d_placement import INSET, overlaps
from lib.model3d_plan import plan_data

ROOT = Path(__file__).resolve().parents[1]
NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture(scope="module")
def study():
    return exporter.build_study()


def room_map(option, building, fid="floor-1"):
    b = next(b for b in option["plans"]["buildings"] if b["id"] == building)
    return {r["key"]: r for r in next(f for f in b["floors"] if f["id"] == fid)["rooms"]}


def aabb(g):
    return {"minX": g["x_mm"], "maxX": g["x_mm"] + g["w_mm"], "minY": g["y_mm"], "maxY": g["y_mm"] + g["h_mm"]}


def test_study_is_non_mutating_with_exact_original_baseline(study):
    paths = [
        ROOT / p
        for p in [
            "inputs/project.json",
            "inputs/dimensions.json",
            "inputs/requirements.json",
            "inputs/physical-items.json",
            "inputs/concept-layout-review.json",
            "inputs/furniture-layout.json",
            "AbuildingView.html",
            "BbuildingView.html",
            "CbuildingView.html",
            "structured/candidates/model3d.html",
            "structured/candidates/furniture-plans/layout.js",
            "structured/candidates/c1f-options/layout.js",
        ]
    ]
    before = [p.read_bytes() for p in paths]
    exporter.build_study()
    assert [p.read_bytes() for p in paths] == before
    assert study["status"] == "comparison-only-not-adopted" and study["active_design"] == "main-a32-arcade-v1"
    assert study["reference_review"] == "inputs/references/abc-before-a-arcade.json"
    main = json.loads(paths[-2].read_text().removeprefix("window.HOUSE_CONCEPT_LAYOUT = ").rstrip(";\n"))
    baseline = copy.deepcopy(study["options"][0]["plans"])
    for building in baseline["buildings"]:
        for floor in building["floors"]:
            floor["plan_file"] = f"{building['id']}_{floor['id']}.svg"
    historical = model3d.build_payload(
        json.loads((ROOT / "structured/room_program.json").read_text()),
        load_overrides(),
        "presentation",
        review_path=exporter.REFERENCE_REVIEW,
        validate_a_arcade=False,
    )
    assert baseline == plan_data(historical)
    assert baseline["buildings"][0] != main["buildings"][0]
    assert baseline["buildings"][1:] != main["buildings"][1:]  # current B/C flow revision remains outside this frozen study
    assert all("ritual_access" not in b["layout_review"] and "open_living" not in b["layout_review"] for b in baseline["buildings"])
    assert sum(len(f["rooms"]) for b in baseline["buildings"] for f in b["floors"]) == 105
    assert sum(len(r["furniture"]) for b in baseline["buildings"] for f in b["floors"] for r in f["rooms"]) == 129


@pytest.mark.parametrize("option_index", [1, 2])
def test_rooms_bounded_nonoverlapping_and_frontage_excludes_private_uses(study, option_index):
    option = study["options"][option_index]
    for building in option["plans"]["buildings"]:
        for floor in building["floors"]:
            for i, room in enumerate(floor["rooms"]):
                g = room["geometry"]
                assert 0 <= g["x_mm"] < g["x_mm"] + g["w_mm"] <= floor["width_mm"]
                assert 0 <= g["y_mm"] < g["y_mm"] + g["h_mm"] <= floor["depth_mm"]
                assert all(not overlaps(aabb(g), aabb(other["geometry"])) for other in floor["rooms"][i + 1 :])
            if floor["id"] != "floor-1":
                continue
            assert floor["width_mm"] == 6000
            if option_index == 1:
                assert floor["depth_mm"] == 17630  # Never pad a supposedly 32-ping parcel.
            frontage = next(r for r in floor["rooms"] if r["key"] in {"garage", "arcade"})
            assert frontage["outdoor"] and frontage["geometry"] == {"x_mm": 0, "y_mm": 0, "w_mm": 6000, "h_mm": 3900}
            assert not frontage["furniture"] and "frontage_study" not in frontage["features"]
            for r in floor["rooms"]:
                if r is not frontage:
                    assert r["geometry"]["y_mm"] >= 3900
            assert not any(i["category"] == "vehicle" for r in floor["rooms"] for i in r["furniture"])


@pytest.mark.parametrize("option_index", [1, 2])
def test_elder_normal_products_bathing_routes_and_reservations_not_deleted(study, option_index):
    option = study["options"][option_index]
    for bid, elder, bath in [("A", "flex1", "bath1"), ("C", "elder", "elder-bath")]:
        rooms, base = room_map(option, bid), room_map(study["options"][0], bid)
        for key in (elder, bath):
            for axis in ("w_mm", "h_mm") if key == elder or option_index == 1 else ("w_mm",):
                assert rooms[key]["geometry"][axis] == base[key]["geometry"][axis]
            assert {i["id"] for i in rooms[key]["furniture"]} == {i["id"] for i in base[key]["furniture"]}
            assert all(not i["placement"]["issues"] for i in rooms[key]["furniture"])
            assert not rooms[key]["features"]["access_pending"]
            has_turn = any(
                z["kind"] == "care-turn"
                and z["aabb"]["maxX"] - z["aabb"]["minX"] >= 1500
                and z["aabb"]["maxY"] - z["aabb"]["minY"] >= 1500
                for z in rooms[key]["features"]["reserved_mm"]
            )
            if bid == "C" and key == bath:
                assert not has_turn
                assert not next(r for r in option["capacity"][bid]["care_rooms"] if r["room_id"] == rooms[key]["id"])[
                    "turning_reservation_present"
                ]
                assert any("尚無獨立150cm" in n for n in option["capacity"][bid]["unmet"])
            else:
                assert has_turn
        assert any(
            i["shape"] == "bed" and (i["width_mm"], i["depth_mm"]) == (1520, 1880) for i in rooms[elder]["furniture"]
        )
        assert any(
            i["catalog_id"] == "wardrobe-120" and (i["width_mm"], i["depth_mm"]) == (1200, 600)
            for i in rooms[elder]["furniture"]
        )
        assert {i["shape"] for i in rooms[bath]["furniture"]} >= {"shower", "vanity", "toilet"}
        for i in rooms[elder]["furniture"]:
            assert all(not overlaps(i["placement"]["aabb"], z["aabb"]) for z in rooms[elder]["features"]["reserved_mm"])


def test_catalogue_and_physical_item_envelopes_never_shrunk(study):
    base = {
        i["id"]: i
        for b in study["options"][0]["plans"]["buildings"]
        for f in b["floors"]
        for r in f["rooms"]
        for i in r["furniture"]
    }
    for option in study["options"][1:]:
        products = [
            i for b in option["plans"]["buildings"] for f in b["floors"] for r in f["rooms"] for i in r["furniture"]
        ]
        assert {i["id"] for i in products} == set(base)
        for i in products:
            for key in (
                "catalog_id",
                "width_mm",
                "depth_mm",
                "height_mm",
                "front_clearance_mm",
                "physical_dimension_source",
            ):
                assert i.get(key) == base[i["id"]].get(key)
            assert i["placement"]["status"] != "measured"


def test_independent_capacity_failure_is_not_relabelled_as_a_solution(study):
    option = study["options"][1]
    a = room_map(option, "A")
    c = room_map(option, "C")
    assert a["living"]["geometry"]["h_mm"] == a["entry"]["geometry"]["h_mm"] == 1300
    assert (a["living"]["geometry"]["w_mm"] - 2 * INSET) * (1300 - 2 * INSET) / 1e6 < 18
    assert c["living"]["geometry"]["h_mm"] == 1500
    for bid in ("A", "C"):
        cap = option["capacity"][bid]
        assert cap["status"] == cap["ground_program_status"] == "conflicts-remain"
        assert cap["unmet"] and cap["pending_furniture"]
    assert any(
        i["item"] == "三人沙發" and i["dimensions_mm"][:2] == [2400, 900]
        for i in option["capacity"]["A"]["pending_furniture"]
    )
    assert any(i["item"] == "茶几" and "overflow" in i["issues"] for i in option["capacity"]["C"]["pending_furniture"])
    checks = option["model"]["layout_review"]["checks"]
    assert next(c for c in checks if c["id"] == "A-1F-care-functions")["status"] == "not-accommodated"
    assert {c["id"] for c in checks} >= {"A-stair-stack", "B-stair-stack", "C-stair-stack", "B-shrine-projection"}
    assert (
        next(c for c in study["options"][2]["model"]["layout_review"]["checks"] if c["id"] == "A-1F-care-functions")[
            "status"
        ]
        == "conditional-proposal-function-screen-only"
    )
    assert study["options"][2]["capacity"]["A"]["status"] == "conflicts-remain"  # Upper wardrobes still pending.


def test_parcel_area_not_three_parcel_total_or_usable_floor_area(study):
    for bid in ("A", "B", "C"):
        cap = study["options"][1]["capacity"][bid]
        assert cap["parcel_sqm"] == 105.78 and cap["parcel_ping"] == 31.998
        assert cap["legal_building_area_sqm"] is None
        assert [r["hypothetical_limit_sqm"] for r in cap["coverage_sensitivity"]] == [52.89, 63.468, 74.046]
        assert all(r["legal_result"] == "unknown" for r in cap["coverage_sensitivity"])
    assert study["options"][1]["capacity"]["A"]["indoor_projection_proxy_sqm"] == 85.98  # Upper floors, not just 1F!
    assert study["options"][1]["capacity"]["A"]["ground_indoor_rectangles_sqm"] == 71.196
    assert [c["parcel_ping"] for c in study["options"][2]["capacity"].values()] == [40.71, 33.632, 33.632]
    assert [r["rectangular_remainder_sqm"] for r in study["rear_sensitivity"]] == [
        82.385,
        76.385,
        73.385,
        71.585,
        70.385,
    ]
    assert exporter.union_area([[0, 0, 1000, 1000], [500, 0, 1000, 1000]]) == 1.5


def test_stair_elevations_arrival_landing_and_footprints_are_coherent(study):
    for option in study["options"][1:]:
        for building in option["model"]["buildings"]:
            assert [f["base_mm"] for f in building["floors"]] == [0, 4000, 7000, 10000]
            assert [f["height_mm"] for f in building["floors"]] == [4000, 3000, 3000, 3000]
            well = None
            for f in building["floors"]:
                cell = next(c for c in f["cells"] if c.get("tour_active") and c["tour_features"]["stairs"])
                features, g = cell["tour_features"], cell["tour_mm"]
                stair, footprint = features["stair_geometry"], features["stair_footprint_mm"]
                assert stair["risers"] == (24 if f["id"] == "floor-1" else 18)
                assert stair["riser_mm"] <= 180 and stair["tread_mm"] == 270 and stair["landing_mm"] == 1000
                assert footprint["h_mm"] == stair["run_mm"] + stair["landing_mm"] + stair["middle_landing_mm"] == 4970
                assert g["h_mm"] == 5200 and stair["fits_reserved_box"]
                assert footprint["y_mm"] + footprint["h_mm"] <= g["y_mm"] + g["h_mm"]
                assert well is None or footprint == well
                well = footprint
                assert not features["stair_geometry_verified"]
                assert stair["connects_to_next_storey"] == (f["id"] != "floor-4")


def test_hvac_facade_follow_actual_scenario_bases_not_original_3m(study):
    for option in study["options"][1:]:
        payload = option["model"]
        floors = {f"{b['id']}:{f['id']}": f for b in payload["buildings"] for f in b["floors"]}
        routes = payload["layout_review"]["hvac_routes"]
        assert len(routes) == 17
        for r in routes:
            indoor = floors[":".join(r["indoor_room"].split(":")[:2])]
            outdoor = floors[":".join(r["outdoor_room"].split(":")[:2])]
            assert r["polyline_mm"][0][2] == indoor["base_mm"] + 2350
            assert r["polyline_mm"][-1][2] == outdoor["base_mm"] + 500
            assert r["elevation_difference_mm"] == abs(outdoor["base_mm"] + 500 - indoor["base_mm"] - 2350)
            assert r["compliance"] == "unknown" and r["manual_source"] is r["model"] is None
        assert next(r for r in routes if r["id"] == "C-AC01")["elevation_difference_mm"] == 2150
        for b in payload["facade"]["buildings"]:
            for opening in b["openings"]:
                f = floors[f"{b['id']}:{opening['floor']}"]
                assert opening["box_mm"]["z_mm"] >= f["base_mm"]
                assert opening["box_mm"]["z_mm"] + opening["box_mm"]["h_mm"] <= f["base_mm"] + f["height_mm"]


def test_b_altar_projection_and_palanquin_storage_vs_transport_remain_distinct(study):
    for option in study["options"][1:]:
        b = next(b for b in option["model"]["buildings"] if b["id"] == "B")
        shrine = room_map(option, "B")["shrine"]["geometry"]
        for f in b["floors"][1:]:
            for c in f["cells"]:
                if c.get("tour_active") and (
                    c["kind"] in {"stair", "bath", "kitchen"}
                    or any(s in c["name"] for s in ("KTV", "水塔", "加壓", "熱泵"))
                ):
                    assert not overlaps(aabb(shrine), aabb(c["tour_mm"]))
        storage = room_map(option, "B")["storage"]
        palanquin = next(i for i in storage["furniture"] if i["shape"] == "palanquin")
        assert (palanquin["width_mm"], palanquin["depth_mm"], palanquin["height_mm"]) == (1200, 1700, 1800)
        assert palanquin["physical_dimension_source"] != "measured"
        assert any("搬運人員" in n for n in option["capacity"]["B"]["unmet"])


def test_generated_manifest_36_svg_and_single_scene_share_exact_data(study):
    manifest = json.loads(
        (ROOT / "structured/candidates/arcade-capacity/layout.js")
        .read_text()
        .removeprefix("window.HOUSE_ARCADE_CAPACITY = ")
        .rstrip(";\n")
    )
    assert manifest == exporter.manifest(study)
    for file, digest in manifest["source_hashes"].items():
        assert hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == digest
    html = (ROOT / "structured/candidates/arcade-capacity-3d.html").read_text()
    model = json.loads(re.search(r"var DATA = (\{.+?\});\n", html)[1])["arcade_capacity"]["options"]
    assert html.count('<canvas id="canvas"') == 1 and "__STUDY_" not in html
    assert "var middle=(flight.middle_landing_mm || flight.landing_mm)*MM;" in html
    assert (
        "var departure=(flight.departure_offset_mm===undefined?flight.landing_mm:flight.departure_offset_mm)*MM;"
        in html
    )
    for expected, embedded in zip(study["options"], model, strict=True):
        assert embedded["capacity"] == expected["capacity"]
        for k in ("buildings", "layout_review", "facade", "study_option"):
            assert embedded["model"][k] == expected["model"][k]
        for b in expected["plans"]["buildings"]:
            for f in b["floors"]:
                file = ROOT / "structured/candidates/arcade-capacity" / f["plan_file"]
                assert file.read_text() == exporter.render_study_plan(expected, b["id"], f)
                tree = ET.parse(file)
                assert tree.getroot().get("data-study-option") == expected["id"]
                for r in f["rooms"]:
                    group = tree.find(f".//s:g[@data-room-id='{r['id']}']", NS)
                    assert [float(group.get(k)) for k in ("data-x-mm", "data-y-mm", "data-w-mm", "data-h-mm")] == list(
                        r["geometry"].values()
                    )
                    assert f"?scheme={expected['id']}" in group.find("s:a", NS).get("href")


@pytest.mark.parametrize(
    "bad", ["adoption", "approval", "missing-status", "empty-status", "area", "frontage", "height", "shrink", "IDs"]
)
def test_false_evidence_or_unstudied_assumptions_rejected(bad):
    raw = json.loads(exporter.SOURCE.read_text())
    if bad == "adoption":
        raw["active_design"] = "arcade32"
    elif bad == "approval":
        raw["professional_status"]["coverage_and_far"] = "verified"
    elif bad == "missing-status":
        del raw["professional_status"]["structure_and_fire"]
    elif bad == "empty-status":
        raw["professional_status"] = {}
    elif bad in {"area", "frontage", "height"}:
        raw["assumptions"][
            {"area": "area_ping_each", "frontage": "front_clear_mm", "height": "ground_storey_height_mm"}[bad]
        ] = 0
    elif bad == "shrink":
        raw["profiles"] = {"bed": {"width_mm": 100}}
    else:
        raw["options"][1]["id"] = "approved"
    with pytest.raises(ValueError):
        exporter.build_study(raw)

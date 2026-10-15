"""A current main: bounded arcade + retained functions, not a professional pass."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

import export_model_3d as model3d
import pytest
from lib.dimension_overrides import load_overrides
from lib.model3d_functions import check_a_arcade_functions, check_a_care_functions
from lib.model3d_placement import INSET, overlaps
from lib.model3d_plan import plan_data, render_plan

ROOT = Path(__file__).resolve().parents[1]
NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture(scope="module")
def payload():
    return model3d.build_payload(
        json.loads((ROOT / "structured/room_program.json").read_text()), load_overrides(), "presentation"
    )


def floor_cells(payload, number=1):
    return {c["key"]: c for c in payload["buildings"][0]["floors"][number - 1]["cells"] if c.get("tour_active")}


def test_current_a_frontage_is_inside_each_32ping_frame_and_separate_from_the_old_failure(payload):
    cells = floor_cells(payload)
    arcade = cells["arcade"]
    assert arcade["tour_mm"] == {"x_mm": 0, "y_mm": 0, "w_mm": 6000, "h_mm": 3900}
    assert "騎樓3.9m" in arcade["name"] and arcade["is_outdoor"]
    assert arcade["review_spec"]["clear"] and not arcade["furniture"] and not arcade["tour_features"]["hvac_units"]
    assert all(c is arcade or c["tour_mm"]["y_mm"] >= 3900 for c in cells.values())
    for b in payload["buildings"]:
        assert len(b["floors"]) == 4
        assert all((f["tour_width_mm"], f["tour_depth_mm"]) == (6000, 17630) for f in b["floors"])
        assert b["layout_review"]["parking"]["verified_spaces"] is None
        assert not any(i["category"] == "vehicle" for c in b["floors"][0]["cells"] for i in c["furniture"])
    current = json.loads((ROOT / "inputs/concept-layout-review.json").read_text())
    frozen = json.loads((ROOT / "inputs/references/abc-before-a-arcade.json").read_text())
    assert current["id"] == "abc-rationality-v6-space-efficiency"
    assert current["buildings"]["A"] != frozen["buildings"]["A"]
    for bid in ("B", "C"):
        for fid, floor in current["buildings"][bid]["floors"].items():
            expected = {
                k: r["rect"] for k, r in frozen["buildings"][bid]["floors"][fid]["rooms"].items()
            }
            if bid == "C" and fid in {"floor-2", "floor-3"}:
                expected["living2f" if fid == "floor-2" else "master3f"] = [0, 3900, 6000, 4240]
                expected["front-hall"] = [0, 8140, 6000, 1360]
            assert {k: r["rect"] for k, r in floor["rooms"].items()} == expected
    assert current["buildings"]["B"]["ritual_access"]["owner_requires_axial_front_door"]
    assert current["buildings"]["C"]["open_living"]["status"] == "open-zones-proposal-not-verified"
    assert "arcade" not in frozen["buildings"]["A"]["floors"]["floor-1"]["rooms"]


def test_care_room_normal_products_and_tight_living_margin_are_exposed(payload):
    cells = floor_cells(payload)
    frozen = json.loads((ROOT / "inputs/references/abc-before-a-arcade.json").read_text())
    for key in ("flex1", "balcony1", "kitchen"):
        g = cells[key]["tour_mm"]
        assert list(g.values()) == frozen["buildings"]["A"]["floors"]["floor-1"]["rooms"][key]["rect"]
    products = {i["catalog_id"]: i for i in cells["flex1"]["furniture"]}
    assert (products["queen-bed"]["width_mm"], products["queen-bed"]["depth_mm"]) == (1520, 1880)
    assert (products["wardrobe-120"]["width_mm"], products["wardrobe-120"]["depth_mm"]) == (1200, 600)
    catalog = json.loads((ROOT / "inputs/furniture-layout.json").read_text())["catalog"]
    for key in ("living", "bath1", "kitchen", "flex1"):
        for item in cells[key]["furniture"]:
            assert all(item[k] == catalog[item["catalog_id"]][k] for k in ("width_mm", "depth_mm", "height_mm"))
            p = cells[key]["furniture_placements"]["tour_mm"][item["id"]]
            assert not p["issues"] and p["status"] == "planning-not-measured"
    dining = next(i for i in cells["living"]["furniture"] if i["shape"] == "dining-set")
    assert (dining["table_width_mm"], dining["table_depth_mm"]) == (1200, 800)
    assert (dining["width_mm"], dining["depth_mm"]) == (1200, 1800)
    placement = cells["living"]["furniture_placements"]["tour_mm"][dining["id"]]
    assert all(abs(placement["operation_mm"][k] - placement["aabb"][k]) == 400 for k in placement["aabb"])
    care = check_a_care_functions(payload["buildings"])
    living = next(r for r in care["requirements"] if r["requirement_id"] == "A.floor-1.living")
    assert living["assumed_clear_area_sqm"] == pytest.approx(18.003)
    assert living["assumed_inset_mm"] == INSET and living["source_status"] == "candidate"
    forbidden = {cells[k]["id"] for k in ("stair-door", "mdf")}
    assert all(not forbidden.intersection(route) for route in care["routes"].values())
    assert care["routes"]["entrance_to_elder"] == [
        cells[k]["id"] for k in ("entry", "living", "care-passage", "rear-hall1", "flex1")
    ]
    assert len(cells["bath1"]["tour_features"]["doors"]) == 1
    assert cells["bath1"]["tour_features"]["doors"][0]["neighbor"] == cells["care-passage"]["id"]


def test_four_levels_shared_front_landings_and_stair_math_not_side_flight_access(payload):
    floors = payload["buildings"][0]["floors"]
    assert [f["base_mm"] for f in floors] == [0, 4000, 7000, 10000]
    assert [f["height_mm"] for f in floors] == [4000, 3000, 3000, 3000]
    for f in floors:
        stair = next(c for c in f["cells"] if c.get("tour_active") and c["kind"] == "stair")
        ft = stair["tour_features"]
        g = ft["stair_geometry"]
        assert ft["stair_footprint_mm"] == {"x_mm": 80, "y_mm": 5950, "w_mm": 2000, "h_mm": 3860}
        assert g["flight_width_mm"] == 900 and g["tread_mm"] == 260 and g["landing_mm"] == 1000
        assert g["risers"] == (24 if f["id"] == "floor-1" else 18)
        assert g["riser_mm"] == pytest.approx(f["height_mm"] / g["risers"], abs=0.01)
        assert g["run_mm"] == (g["risers"] // 2 - 1) * g["tread_mm"]
        assert g["departure_offset_mm"] == 0 and g["middle_landing_mm"] >= 1000
        assert g["run_mm"] + g["middle_landing_mm"] == 3860
        landing = ft["shared_landing_mm"]
        assert [landing[k] for k in ("x_mm", "y_mm", "w_mm", "h_mm")] == [80, 4950, 2000, 1000]
        assert not ft["doors"] and len(ft["open_connections"]) == 1
        assert ft["open_connections"][0]["face"] == "front"
        assert ft["open_connections"][0]["neighbor"] == landing["space"]
        assert ft["stair_geometry_verified"] is False
        assert g["connects_to_next_storey"] is (f["id"] != "floor-4")
        shared = next(c for c in f["cells"] if c["id"] == landing["space"])
        box = {"minX": 80, "maxX": 2080, "minY": 4950, "maxY": 5950}
        assert all(not overlaps(box, p["aabb"]) for p in shared["furniture_placements"]["tour_mm"].values())
    check = next(c for c in payload["layout_review"]["checks"] if c["id"] == "A-32ping-arcade-functions")
    assert check["status"] == "bounded-arcade-and-function-screen-only"
    assert check["verified_headroom_mm"] is check["legal_building_area_sqm"] is check["verified_parking_spaces"] is None
    assert check["surveyed_parcel"] == check["arcade_applicability"] == check["professional_acceptance"] == "unknown"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_arcade",
        "occupied_arcade",
        "arcade_hvac",
        "indoor_frontage",
        "encroaching_room",
        "frame_growth",
        "narrow_care_passage",
        "care_through_mdf",
        "care_through_stairs",
        "incorrect_height",
        "verified_parking",
        "fake_care_approval",
        "verified_stair",
        "side_flight_door",
        "missing_landing",
        "wrong_risers",
    ],
)
def test_shared_bad_data_does_not_bypass_the_independent_current_main_guard(payload, mutation):
    p = deepcopy(payload)
    a = p["buildings"][0]
    cells = floor_cells(p)
    care = check_a_care_functions(p["buildings"])
    features = cells["stair-door"]["tour_features"]
    if mutation == "missing_arcade":
        cells["arcade"]["tour_active"] = False
    elif mutation == "occupied_arcade":
        cells["arcade"]["furniture"] = [deepcopy(cells["living"]["furniture"][0])]
    elif mutation == "arcade_hvac":
        cells["arcade"]["tour_features"]["hvac_units"] = [{"type": "outdoor"}]
    elif mutation == "indoor_frontage":
        cells["arcade"]["is_outdoor"] = False
    elif mutation == "encroaching_room":
        cells["entry"]["tour_mm"]["y_mm"] = 0
    elif mutation == "frame_growth":
        a["floors"][0]["tour_depth_mm"] = 20000
    elif mutation == "narrow_care_passage":
        cells["care-passage"]["tour_mm"]["w_mm"] = 1200
    elif mutation in {"care_through_mdf", "care_through_stairs"}:
        care["routes"]["elder_to_bath"].insert(1, cells["mdf" if mutation.endswith("mdf") else "stair-door"]["id"])
    elif mutation == "incorrect_height":
        a["floors"][0]["height_mm"] = 3000
    elif mutation == "verified_parking":
        a["layout_review"]["parking"]["verified_spaces"] = 1
    elif mutation == "fake_care_approval":
        care["professional_accessibility"] = "passed"
    elif mutation == "verified_stair":
        features["stair_geometry_verified"] = True
    elif mutation == "side_flight_door":
        features["doors"] = [{"face": "right", "neighbor": cells["living"]["id"]}]
    elif mutation == "missing_landing":
        features.pop("shared_landing_mm")
    else:
        features["stair_geometry"]["risers"] = 18
    with pytest.raises(ValueError, match="A 32-ping arcade"):
        check_a_arcade_functions(p["buildings"], care)


def test_html_svg_and_3d_share_current_a_and_preserve_all_bc_geometry(payload):
    manifest = json.loads(
        (ROOT / "structured/candidates/furniture-plans/layout.js")
        .read_text()
        .removeprefix("window.HOUSE_CONCEPT_LAYOUT = ")
        .rstrip(";\n")
    )
    assert manifest == plan_data(payload)
    a = manifest["buildings"][0]
    for f in a["floors"]:
        tree = ET.fromstring(render_plan("A", f))
        stair = next(r for r in f["rooms"] if r["features"]["stairs"])
        assert tree.find(f"s:g[@data-room-id='{stair['id']}']", NS) is not None
        assert "共用前平台" in ET.tostring(tree, encoding="unicode")
    frozen = model3d.build_payload(
        json.loads((ROOT / "structured/room_program.json").read_text()),
        load_overrides(),
        "presentation",
        review_path=ROOT / "inputs/references/abc-before-a-arcade.json",
        validate_a_arcade=False,
    )
    historical = plan_data(frozen)
    furniture_only_revisions = {"B:floor-2:living2", "B:floor-3:guest3", "C:floor-3:master3f",
                               "C:floor-2:living2f", "C:floor-2:guestroom2f", "C:floor-2:balcony2f"}
    original_product_fields = ("id", "catalog_id", "shape", "width_mm", "depth_mm", "height_mm")
    for building, old in zip(manifest["buildings"][1:], historical["buildings"][1:], strict=True):
        assert building["floors"] != old["floors"]  # explicit B/C flow revision, not an A/MDF side effect
        for floor, prior in zip(building["floors"], old["floors"], strict=True):
            expected = {r["id"]: r["geometry"] for r in prior["rooms"]}
            if building["id"] == "C" and floor["id"] in {"floor-2", "floor-3"}:
                rid = "living2f" if floor["id"] == "floor-2" else "master3f"
                expected[f"C:{floor['id']}:{rid}"] = {"x_mm": 0, "y_mm": 3900, "w_mm": 6000, "h_mm": 4240}
                expected[f"C:{floor['id']}:front-hall"] = {"x_mm": 0, "y_mm": 8140, "w_mm": 6000, "h_mm": 1360}
            assert {r["id"]: r["geometry"] for r in floor["rooms"]} == expected
            if floor["id"] != "floor-1":
                for room, original in zip(floor["rooms"], prior["rooms"], strict=True):
                    if room["id"] in furniture_only_revisions:
                        # Only these three upper rooms intentionally change placement/copy;
                        # no product may disappear or be resized to make the plan fit.
                        assert [tuple(i[k] for k in original_product_fields) for i in room["furniture"]] == [
                            tuple(i[k] for k in original_product_fields) for i in original["furniture"]
                        ]
                    else:
                        assert room["furniture"] == original["furniture"]
    assert (
        len([c for b in payload["buildings"] for f in b["floors"] for c in f["cells"] if not c.get("proposal_only")])
        == 92
    )
    assert (ROOT / "Docs/a-32ping-arcade-layout-v1.md").is_file()

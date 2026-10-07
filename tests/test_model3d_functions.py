from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import export_model_3d as model3d
import pytest
from lib.dimension_overrides import load_overrides
from lib.furniture_layout import FurnitureLayoutError
from lib.model3d_functions import A_CARE_BINDINGS, check_a_care_functions
from lib.model3d_placement import _issues

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def data():
    return model3d.build_payload(
        json.loads((ROOT / "structured/room_program.json").read_text()), load_overrides(), "presentation"
    )


def a_cells(buildings):
    return {c["key"]: c for c in buildings[0]["floors"][0]["cells"]}


def test_a_1f_care_program_is_retained_separately_from_html_3d_parity(data):
    check = check_a_care_functions(data["buildings"])
    assert {r["requirement_id"] for r in check["requirements"]} == set(A_CARE_BINDINGS.values())
    assert all(r["source_status"] == "candidate" for r in check["requirements"])
    assert check["status"] == "conditional-proposal-function-screen-only"
    assert check["site_legality"] == check["professional_accessibility"] == "unknown"
    assert check["routes"]["elder_to_bath"] == ["A:floor-1:flex1", "A:floor-1:rear-hall1", "A:floor-1:bath1"]
    assert check["routes"]["kitchen_to_work_balcony"] == ["A:floor-1:kitchen", "A:floor-1:balcony1"]
    cells = a_cells(data["buildings"])
    assert (cells["flex1"]["tour_mm"]["w_mm"], cells["flex1"]["tour_mm"]["h_mm"]) == (3600, 3770)
    assert {i["catalog_id"] for i in cells["flex1"]["furniture"]} == {"queen-bed", "wardrobe-120"}
    assert cells["balcony1"]["tour_mm"]["h_mm"] == 1800
    assert not cells["garage"]["tour_active"] and cells["garage"]["deferred_furniture_assignment"]
    assert not cells["water-inlet"]["tour_active"]
    assert cells["mdf"]["space_group"] == cells["stair-door"]["space_group"]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_room",
        "day_use",
        "lost_label",
        "lost_binding",
        "bed_removed",
        "wardrobe_removed",
        "tiny_bed",
        "shower_removed",
        "small_shower",
        "shower_step",
        "turn_removed",
        "small_turn",
        "occupied_turn",
        "pending_bed",
        "narrow_door",
        "inward_door",
        "mdf_through_route",
        "kitchen_night_route",
        "window_overflow",
    ],
)
def test_function_regressions_fail_even_if_both_frontends_would_share_the_same_bad_data(data, mutation):
    buildings = deepcopy(data["buildings"])
    cells = a_cells(buildings)
    elder, bath = cells["flex1"], cells["bath1"]
    if mutation == "missing_room":
        elder["tour_active"] = False
    elif mutation == "day_use":
        elder["kind"] = "other"
    elif mutation == "lost_label":
        elder["name"] = "日間彈性区"
    elif mutation == "lost_binding":
        elder["review_spec"].pop("requirement_id")
    elif mutation in {"bed_removed", "wardrobe_removed"}:
        shape = "bed" if mutation == "bed_removed" else "cabinet"
        elder["furniture"] = [i for i in elder["furniture"] if i["shape"] != shape]
    elif mutation == "tiny_bed":
        next(i for i in elder["furniture"] if i["shape"] == "bed")["width_mm"] = 700
    elif mutation == "shower_removed":
        bath["furniture"] = [i for i in bath["furniture"] if i["shape"] != "shower"]
    elif mutation == "small_shower":
        next(i for i in bath["furniture"] if i["shape"] == "shower")["width_mm"] = 900
    elif mutation == "shower_step":
        next(i for i in bath["furniture"] if i["shape"] == "shower")["step_free"] = False
    elif mutation in {"turn_removed", "small_turn", "occupied_turn"}:
        features = elder["tour_features"]
        turn = next(z for z in features["reserved_mm"] if z["kind"] == "care-turn")
        if mutation == "turn_removed":
            features["reserved_mm"].remove(turn)
        elif mutation == "small_turn":
            turn["aabb"]["maxX"] = turn["aabb"]["minX"] + 1400
        else:
            bed = next(p for fid, p in elder["furniture_placements"]["tour_mm"].items() if fid.endswith(":bed"))
            bed["aabb"] = deepcopy(turn["aabb"])
    elif mutation == "pending_bed":
        next(iter(elder["furniture_placements"]["tour_mm"].values()))["issues"] = ["overflow"]
    elif mutation in {"narrow_door", "inward_door"}:
        for door in elder["tour_features"]["doors"]:
            door["width_mm" if mutation == "narrow_door" else "operation"] = (
                800 if mutation == "narrow_door" else "inward"
            )
    elif mutation == "mdf_through_route":
        for key, neighbor in (("entry", "living"), ("living", "entry")):
            cells[key]["tour_features"]["open_connections"] = [
                d for d in cells[key]["tour_features"]["open_connections"] if d["neighbor"] != cells[neighbor]["id"]
            ]
    elif mutation == "kitchen_night_route":
        hall = cells["rear-hall1"]["tour_features"]
        hall["doors"] = [d for d in hall["doors"] if d["neighbor"] != bath["id"]]
        door = bath["tour_features"]["doors"][0]
        door["neighbor"] = cells["kitchen"]["id"]
        cells["kitchen"]["tour_features"]["doors"].append({**door, "neighbor": bath["id"]})
    else:
        elder["window_mm"] = 3000
    with pytest.raises(ValueError, match="A 1F care requirement"):
        check_a_care_functions(buildings)


def test_export_cannot_silently_defer_elder_room_to_make_both_frontends_agree(tmp_path):
    review = json.loads((ROOT / "inputs/concept-layout-review.json").read_text())
    a = review["buildings"]["A"]
    a["floors"]["floor-1"]["rooms"].pop("flex1")
    a["floors"]["floor-1"]["connections"] = [c for c in a["floors"]["floor-1"]["connections"] if "flex1" not in c[:2]]
    a["hvac_pairs"] = [p for p in a["hvac_pairs"] if p[1] != "flex1"]
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review))
    with pytest.raises(ValueError, match="missing active room for A.floor-1.elder"):
        model3d.build_payload(
            json.loads((ROOT / "structured/room_program.json").read_text()),
            load_overrides(),
            "presentation",
            review_path=path,
        )


def test_function_screen_uses_the_supplied_requirement_source_and_never_promotes_status(tmp_path, data):
    path = ROOT / "inputs/requirements.json"
    before = path.read_bytes()
    source = json.loads(before)
    req = next(r for r in source["requirements"] if r["id"] == "A.floor-1.elder")
    req["constraints"]["min_sqm"] = 25
    altered = tmp_path / "requirements.json"
    altered.write_text(json.dumps(source))
    with pytest.raises(ValueError, match="below source minimum area"):
        check_a_care_functions(data["buildings"], altered)
    with pytest.raises(ValueError, match="below source minimum area"):
        model3d.build_payload(
            json.loads((ROOT / "structured/room_program.json").read_text()),
            load_overrides(),
            "presentation",
            requirements_path=altered,
        )
    assert path.read_bytes() == before


def test_shared_operation_is_explicit_sequential_use_and_never_permits_a_fixture_in_turning_floor(data):
    bath = a_cells(data["buildings"])["bath1"]
    shower = next(i for i in bath["furniture"] if i["shape"] == "shower")
    p = bath["furniture_placements"]["tour_mm"][shower["id"]]
    features = deepcopy(bath["tour_features"])
    assert shower["shared_operation_with"] == ["care-turn"] and "分時共用" in shower["note"]
    assert not _issues(shower, p, bath["tour_mm"], features, [])
    features["reserved_mm"].append({"kind": "care-turn", "aabb": p["aabb"]})
    assert "care-turn" in _issues(shower, p, bath["tour_mm"], features, [])


@pytest.mark.parametrize("mutation", ["bed_sharing", "missing_note", "step_free_cabinet"])
def test_clearance_sharing_and_step_free_metadata_cannot_hide_an_unrelated_fit(tmp_path, mutation):
    furniture = json.loads((ROOT / "inputs/furniture-layout.json").read_text())
    if mutation == "bed_sharing":
        furniture["profiles"]["review-a-care-elder"][0]["shared_operation_with"] = ["care-turn"]
    elif mutation == "missing_note":
        furniture["profiles"]["review-a-care-bath"][0]["note"] = ""
    else:
        furniture["profiles"]["review-a-care-elder"][1]["step_free"] = True
    path = tmp_path / "furniture.json"
    path.write_text(json.dumps(furniture))
    with pytest.raises(FurnitureLayoutError):
        model3d.build_payload(
            json.loads((ROOT / "structured/room_program.json").read_text()),
            load_overrides(),
            "presentation",
            furniture_path=path,
        )

"""Small display-contract tests, not font rendering or HVAC installation QA."""
import json
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from lib.model3d_plan import hvac_plan_mark, render_plan, room_label

ROOT = Path(__file__).resolve().parents[1]
NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture(scope="module")
def shared():
    return json.loads((ROOT / "structured/candidates/furniture-plans/layout.js").read_text()
                      .split(" = ", 1)[1].rstrip(";\n"))


def overlaps(a, b):
    return a["minX"] < b["maxX"] and a["maxX"] > b["minX"] and a["minY"] < b["maxY"] and a["maxY"] > b["minY"]


def bounds(label):
    return {"minX": label["x"], "maxX": label["x"] + label["w"],
            "minY": label["y"], "maxY": label["y"] + label["h"]}


@pytest.mark.parametrize("face", ["front", "rear", "left", "right"])
def test_annotations_reuse_original_unit_transform_and_visible_code(face):
    unit = {"id": "A-AC03", "type": "outdoor", "face": face,
            "x_mm": 530, "y_mm": 275, "width_mm": 900, "depth_mm": 350}
    before = deepcopy(unit)
    mark = hvac_plan_mark(unit)
    w, d = (350, 900) if face in {"left", "right"} else (900, 350)
    assert mark["body"] == {"minX": 530 - w / 2, "maxX": 530 + w / 2,
                            "minY": 275 - d / 2, "maxY": 275 + d / 2}
    assert (mark["x"], mark["y"], mark["font"], mark["text"]) == (630, 425, 155, "A-AC03外")
    assert mark["text_bounds"]["minY"] < mark["y"] < mark["text_bounds"]["maxY"]
    assert unit == before


def test_a2_front_balcony_regression_moves_only_room_name(shared):
    floor = shared["buildings"][0]["floors"][1]
    room = next(r for r in floor["rooms"] if r["key"] == "front-service")
    before = deepcopy(floor)
    old_box = {"minX": 80, "maxX": 1880, "minY": 80, "maxY": 400}
    unit = next(u for u in room["features"]["hvac_units"] if u["id"] == "A-AC03")
    assert overlaps(old_box, hvac_plan_mark(unit)["text_bounds"]), "reproduce the old label conflict"
    label = room_label(room)
    assert (label["x"], label["y"]) != (80, 80)
    assert not label["overlap"] and not label["hvac_overlap"]
    for u in room["features"]["hvac_units"]:
        for obstacle in (hvac_plan_mark(u)["body"], hvac_plan_mark(u)["text_bounds"]):
            assert not overlaps(bounds(label), obstacle)
    svg = ET.fromstring(render_plan("A", floor))
    node = svg.find("s:g[@data-plan-labels='room-names']/s:a[@data-label-room-id='A:floor-2:front-service']", NS)
    assert node.get("data-full-name") == room["name"]
    assert node.get("data-hvac-overlap") == "false"
    assert float(node.get("data-x-mm")) == label["x"]
    assert floor == before, "display placement must not mutate the shared design"


def test_all_main_labels_stay_in_rooms_and_avoid_their_unit_marks(shared):
    for building in shared["buildings"]:
        for floor in building["floors"]:
            for room in floor["rooms"]:
                label, g = room_label(room), room["geometry"]
                assert g["x_mm"] <= label["x"] and g["y_mm"] <= label["y"]
                assert label["x"] + label["w"] <= g["x_mm"] + g["w_mm"]
                assert label["y"] + label["h"] <= g["y_mm"] + g["h_mm"]
                assert not label["hvac_overlap"], room["id"]
                for unit in room["features"].get("hvac_units", []):
                    assert not overlaps(bounds(label), hvac_plan_mark(unit)["body"])
                    assert not overlaps(bounds(label), hvac_plan_mark(unit)["text_bounds"])


def test_no_available_label_position_keeps_overlap_explicit_without_hiding_ac(shared):
    room = deepcopy(next(r for r in shared["buildings"][0]["floors"][1]["rooms"] if r["key"] == "front-service"))
    room["geometry"] = {"x_mm": 0, "y_mm": 0, "w_mm": 600, "h_mm": 600}
    room["features"]["hvac_units"] = [{"id": "A-AC03", "type": "outdoor", "face": "front",
                                       "x_mm": 300, "y_mm": 300, "width_mm": 600, "depth_mm": 600}]
    label = room_label(room)
    assert label["overlap"] and label["hvac_overlap"] and not label["furniture_overlap"]
    floor = {**shared["buildings"][0]["floors"][1], "rooms": [room]}
    svg = ET.fromstring(render_plan("A", floor))
    assert svg.find(".//s:rect[@data-hvac-id='A-AC03']", NS) is not None
    assert svg.find(".//s:text[@data-hvac-label-id='A-AC03']", NS).text == "A-AC03外"
    assert svg.find(".//s:a[@data-label-room-id='A:floor-2:front-service']", NS).get("data-hvac-overlap") == "true"


def test_committed_svg_equipment_positions_and_names_match_the_shared_floor(shared):
    for building in shared["buildings"]:
        for floor in building["floors"]:
            svg = ET.fromstring((ROOT / "structured/candidates/furniture-plans" / floor["plan_file"]).read_text())
            rendered = ET.fromstring(render_plan(building["id"], floor))
            assert ET.tostring(svg) == ET.tostring(rendered), "regenerate the shared SVG outputs"
            for room in floor["rooms"]:
                group = svg.find("s:g[@data-room-id='" + room["id"] + "']", NS)
                for unit in room["features"].get("hvac_units", []):
                    rect = group.find("s:rect[@data-hvac-id='" + unit["id"] + "']", NS)
                    text = group.find("s:text[@data-hvac-label-id='" + unit["id"] + "']", NS)
                    mark = hvac_plan_mark(unit)
                    assert [float(rect.get(k)) for k in ("x", "y", "width", "height")] == [
                        mark["body"]["minX"], mark["body"]["minY"],
                        mark["body"]["maxX"] - mark["body"]["minX"], mark["body"]["maxY"] - mark["body"]["minY"],
                    ]
                    assert text.text == mark["text"] and text.get("data-hvac-label-type") == unit["type"]

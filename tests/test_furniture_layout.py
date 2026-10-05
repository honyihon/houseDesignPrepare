from __future__ import annotations

import json
import re
from pathlib import Path

import export_model_3d as model3d
import pytest
from bs4 import BeautifulSoup
from lib.dimension_overrides import load_overrides
from lib.furniture_layout import FurnitureLayoutError, attach_furniture_layout

ROOT = Path(__file__).resolve().parents[1]


def _repository_payload() -> dict:
    program = json.loads((ROOT / "structured/room_program.json").read_text(encoding="utf-8"))
    plan = json.loads((ROOT / "structured/parametric/plan.json").read_text(encoding="utf-8"))
    return model3d.build_payload(program, load_overrides(), "presentation", plan)


def _cells(payload: dict) -> dict[str, dict]:
    return {
        cell["id"]: cell
        for building in payload["buildings"]
        for floor in building["floors"]
        for cell in floor["cells"]
    }


def test_repository_furniture_draft_covers_html_specific_layouts_at_real_scale() -> None:
    payload = _repository_payload()
    cells = _cells(payload)

    assert payload["furniture"]["available"] is True
    assert payload["furniture"]["rooms"] == 70
    assert payload["furniture"]["items"] == 157

    c_living = {item["catalog_id"]: item for item in cells["C:floor-2:living2f"]["furniture"]}
    assert {"sofa-l", "coffee-table", "tv-console"} <= c_living.keys()
    assert c_living["sofa-l"]["basis"] == "html-explicit"

    c_kitchen = {item["catalog_id"]: item for item in cells["C:floor-2:kitchen2f"]["furniture"]}
    assert c_kitchen["counter-240"]["width_mm"] == 2400
    assert c_kitchen["fridge-75"]["width_mm"] == 750
    assert c_kitchen["fridge-75"]["depth_mm"] == 700

    c_master = {item["catalog_id"]: item for item in cells["C:floor-3:master3f"]["furniture"]}
    assert c_master["double-bed"]["width_mm"] == 1800
    assert c_master["double-bed"]["depth_mm"] == 2000
    assert c_master["wardrobe-360"]["width_mm"] == 3600

    c_garage = cells["C:floor-1:garage"]["furniture"]
    assert [item["catalog_id"] for item in c_garage].count("car") == 2
    assert [item["catalog_id"] for item in c_garage].count("motorcycle") == 1

    palanquin = cells["B:floor-1:storage"]["furniture"][0]
    assert palanquin["physical_item_id"] == "B.palanquin.primary"
    assert (palanquin["width_mm"], palanquin["depth_mm"], palanquin["height_mm"]) == (1200, 1700, 1800)
    assert palanquin["physical_dimension_source"] == "planning"
    assert payload["furniture"]["physical_items"]["pending_measurement"] == 1


def _css_percentage(style: str, name: str) -> float:
    match = re.search(rf"(?:^|;)\s*{re.escape(name)}:\s*([0-9.]+)%", style)
    assert match, f"missing {name} percentage in {style!r}"
    return float(match.group(1)) / 100


def test_every_original_html_room_has_exactly_one_model_room() -> None:
    cells = _cells(_repository_payload())
    expected = set()
    for building in ("A", "B", "C"):
        soup = BeautifulSoup((ROOT / f"{building}buildingView.html").read_text(encoding="utf-8"), "html.parser")
        for floor in soup.select(".floor-plan[id]"):
            for cell in floor.select(".plan-cell[onclick]"):
                match = re.search(r"highlightRoom\(\s*['\"]([^'\"]+)", cell["onclick"])
                assert match is not None
                room_id = f"{building}:{floor['id']}:{match.group(1)}"
                assert room_id not in expected
                expected.add(room_id)
    assert len(expected) == 92
    assert expected == cells.keys()


def test_b1_html_overlays_match_the_resolved_3d_furniture_layout() -> None:
    payload = _repository_payload()
    resolved_cells = _cells(payload)
    soup = BeautifulSoup((ROOT / "BbuildingView.html").read_text(encoding="utf-8"), "html.parser")
    overlay_cells = soup.select('#floor-1 .plan-cell[data-model-room-id][data-layout-source]')

    assert {cell["data-model-room-id"] for cell in overlay_cells} == {
        "B:floor-1:shrine",
        "B:floor-1:storage",
    }
    for html_cell in overlay_cells:
        room_id = html_cell["data-model-room-id"]
        assert html_cell["data-layout-source"] == "inputs/furniture-layout.json"
        room_width = float(html_cell["data-w-mm"])
        room_depth = float(html_cell["data-h-mm"])
        resolved = {item["id"]: item for item in resolved_cells[room_id]["furniture"]}
        html_items = {
            item["data-furniture-id"]: item for item in html_cell.select(".furniture-overlay .layout-item")
        }

        assert html_items.keys() == resolved.keys()
        for item_id, expected in resolved.items():
            html_item = html_items[item_id]
            assert html_item["data-catalog-id"] == expected["catalog_id"]
            assert float(html_item["data-x-ratio"]) == pytest.approx(expected["x_ratio"])
            assert float(html_item["data-y-ratio"]) == pytest.approx(expected["y_ratio"])
            assert float(html_item["data-width-mm"]) == pytest.approx(expected["width_mm"])
            assert float(html_item["data-depth-mm"]) == pytest.approx(expected["depth_mm"])
            assert float(html_item["data-height-mm"]) == pytest.approx(expected["height_mm"])
            assert float(html_item["data-rotation-deg"]) == pytest.approx(expected["rotation_deg"])

            style = html_item.get("style", "")
            assert _css_percentage(style, "--item-x") == pytest.approx(expected["x_ratio"])
            assert _css_percentage(style, "--item-y") == pytest.approx(expected["y_ratio"])
            assert _css_percentage(style, "--item-w") == pytest.approx(
                expected["width_mm"] / room_width, abs=1e-6
            )
            assert _css_percentage(style, "--item-d") == pytest.approx(
                expected["depth_mm"] / room_depth, abs=1e-6
            )

            if expected.get("physical_item_id"):
                assert html_item["data-physical-item-id"] == expected["physical_item_id"]
                assert html_item["data-measurement-state"] == expected["physical_measurement_state"]

    storage = soup.select_one('[data-model-room-id="B:floor-1:storage"]')
    assert storage is not None
    assert storage["data-door-mm"] == "1500"
    assert storage["data-carry-path-mm"] == "1500"
    assert storage["data-access-mode"] == "straight-pull"
    assert not storage.has_attr("data-turning-diameter-mm")


def test_every_furniture_assignment_retains_a_traceable_basis_and_evidence() -> None:
    payload = _repository_payload()
    furniture = [item for cell in _cells(payload).values() for item in cell["furniture"]]

    assert furniture
    assert all(item["basis"] in {"html-explicit", "html-mixed", "room-use-inference"} for item in furniture)
    assert all(item["evidence"] for item in furniture)
    assert sum(payload["furniture"]["basis_counts"].values()) == len(furniture)


def test_unknown_room_assignment_fails_instead_of_silently_disappearing(tmp_path: Path) -> None:
    layout = json.loads((ROOT / "inputs/furniture-layout.json").read_text(encoding="utf-8"))
    layout["rooms"] = {
        "Z:floor-9:missing": {
            "profile": "entry",
            "basis": "room-use-inference",
            "evidence": ["deliberately unknown room"],
        }
    }
    path = tmp_path / "furniture.json"
    path.write_text(json.dumps(layout), encoding="utf-8")
    buildings = [{"floors": [{"cells": [{"id": "A:floor-1:entry"}]}]}]

    with pytest.raises(FurnitureLayoutError, match="does not match any HTML model cell"):
        attach_furniture_layout(buildings, path)


def test_out_of_range_relative_position_is_rejected(tmp_path: Path) -> None:
    layout = json.loads((ROOT / "inputs/furniture-layout.json").read_text(encoding="utf-8"))
    layout["profiles"]["entry"][0]["position"] = [1.2, 0.5]
    layout["rooms"] = {
        "A:floor-1:entry": {
            "profile": "entry",
            "basis": "room-use-inference",
            "evidence": ["test"],
        }
    }
    path = tmp_path / "furniture.json"
    path.write_text(json.dumps(layout), encoding="utf-8")
    buildings = [{"floors": [{"cells": [{"id": "A:floor-1:entry"}]}]}]

    with pytest.raises(FurnitureLayoutError, match="position ratios must be between 0 and 1"):
        attach_furniture_layout(buildings, path)


def test_linked_physical_item_dimensions_cannot_be_duplicated_in_furniture_catalog(tmp_path: Path) -> None:
    layout = json.loads((ROOT / "inputs/furniture-layout.json").read_text(encoding="utf-8"))
    layout["catalog"]["ceremonial-storage"]["width_mm"] = 999
    path = tmp_path / "furniture.json"
    buildings = [{"floors": [{"cells": [{"id": "B:floor-1:storage"}]}]}]
    layout["rooms"] = {
        "B:floor-1:storage": {
            "profile": "ceremonial-storage",
            "basis": "room-use-inference",
            "evidence": ["test"],
        }
    }
    path.write_text(json.dumps(layout), encoding="utf-8")

    with pytest.raises(FurnitureLayoutError, match="must not duplicate dimensions"):
        attach_furniture_layout(buildings, path)

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
        cell["id"]: cell for building in payload["buildings"] for floor in building["floors"] for cell in floor["cells"]
    }


def test_repository_furniture_draft_covers_html_specific_layouts_at_real_scale() -> None:
    payload = _repository_payload()
    cells = _cells(payload)

    assert payload["furniture"]["available"] is True
    assert payload["furniture"]["rooms"] == 61
    assert payload["furniture"]["items"] == 129

    c_living = {item["catalog_id"]: item for item in cells["C:floor-2:living2f"]["furniture"]}
    assert {"sofa-3", "coffee-table", "tv-console"} <= c_living.keys()
    assert cells["C:floor-2:living2f"]["deferred_furniture_assignment"]["profile"] == "living-l"

    c_kitchen = {item["catalog_id"]: item for item in cells["C:floor-2:kitchen2f"]["furniture"]}
    assert c_kitchen["counter-180"]["width_mm"] == 1800
    assert c_kitchen["fridge-75"]["width_mm"] == 750
    assert c_kitchen["fridge-75"]["depth_mm"] == 700

    c_master = {item["catalog_id"]: item for item in cells["C:floor-3:master3f"]["furniture"]}
    assert c_master["double-bed"]["width_mm"] == 1800
    assert c_master["double-bed"]["depth_mm"] == 2000
    assert c_master["wardrobe-180"]["width_mm"] == 1800
    assert cells["C:floor-3:master3f"]["deferred_furniture_assignment"]["profile"] == "hotel-master"

    c_garage = cells["C:floor-1:garage"]["furniture"]
    assert c_garage == []
    assert cells["C:floor-1:garage"]["deferred_furniture_assignment"]["profile"] == "garage-two-plus-motorcycle"

    palanquin = cells["B:floor-1:storage"]["furniture"][0]
    assert palanquin["physical_item_id"] == "B.palanquin.primary"
    assert (palanquin["width_mm"], palanquin["depth_mm"], palanquin["height_mm"]) == (1200, 1700, 1800)
    assert palanquin["physical_dimension_source"] == "planning"
    assert payload["furniture"]["physical_items"]["pending_measurement"] == 1


def test_exterior_proposals_use_distinct_shapes_and_defer_indoor_terrace_furniture() -> None:
    cells = _cells(_repository_payload())
    terrace = cells["B:floor-3:terrace3"]
    assert terrace["is_outdoor"] is True
    assert terrace["furniture"] == []
    assert terrace["deferred_furniture_assignment"]["profile"] == "flex-indoor"
    assert "沙發床" in terrace["deferred_furniture_assignment"]["evidence"][0]
    idf = cells["C:floor-1:sideyard"]
    assert idf["is_outdoor"] is False
    assert idf["kind"] == "service"
    assert idf["furniture"][0]["shape"] == "rack"
    assert "非側院" in idf["name"]
    assert cells["B:floor-2:balcony2"]["furniture"][0]["shape"] == "outdoor-bench"
    assert cells["C:floor-2:balcony2f"]["furniture"][1]["shape"] == "clothes-rack"
    for cell in cells.values():
        if cell.get("tour_active") is False or not cell["is_outdoor"]:
            continue
        assert all(
            item["shape"] not in {"bed", "sofa", "l-sofa", "cabinet", "tv-console", "wall-tv"}
            and item["category"] != "network"
            for item in cell["furniture"]
        ), cell["id"]


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
    assert expected == {cid for cid, c in cells.items() if not c.get("proposal_only")}


def test_b1_html_uses_shared_plans_without_stale_manual_overlays() -> None:
    soup = BeautifulSoup((ROOT / "BbuildingView.html").read_text(encoding="utf-8"), "html.parser")
    assert not soup.select(".furniture-overlay")
    assert soup.select_one('script[src="structured/candidates/furniture-plans/layout.js"]')
    for room_id in ("B:floor-1:shrine", "B:floor-1:storage"):
        cell = soup.select_one(f'[data-model-room-id="{room_id}"]')
        assert cell is not None
        assert cell["data-layout-source"] == "inputs/furniture-layout.json"
        assert "共用家具配置圖" in cell.select_one(".layout-caption").get_text()
    storage = soup.select_one('[data-model-room-id="B:floor-1:storage"]')
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


@pytest.mark.parametrize(
    "key,value,pattern",
    [
        ("wall_anchor", "ceiling", "wall face"),
        ("wall_gap_mm", -1, "not be negative"),
        ("mount_height_mm", float("inf"), "must be finite"),
        ("in_front_of", "absent-sofa", "invalid furniture"),
        ("aligned_with", "shoe-cabinet", "invalid furniture"),
    ],
)
def test_invalid_anchor_clearance_and_furniture_relationships_are_rejected(tmp_path, key, value, pattern):
    layout = json.loads((ROOT / "inputs/furniture-layout.json").read_text(encoding="utf-8"))
    layout["profiles"]["entry"][0][key] = value
    layout["rooms"] = {"A:floor-1:entry": {"profile": "entry", "basis": "room-use-inference", "evidence": ["test"]}}
    path = tmp_path / "furniture.json"
    path.write_text(json.dumps(layout), encoding="utf-8")
    with pytest.raises(FurnitureLayoutError, match=pattern):
        attach_furniture_layout([{"floors": [{"cells": [{"id": "A:floor-1:entry"}]}]}], path)

from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from lib.plan_rules import _check_stacking

ROOT = Path(__file__).resolve().parents[1]


def _rect(node: Tag) -> tuple[float, float, float, float]:
    x = float(node["data-x-mm"])
    y = float(node["data-y-mm"])
    return x, y, x + float(node["data-w-mm"]), y + float(node["data-h-mm"])


def _overlap(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def test_b_floors_share_one_concept_frame_and_keep_forbidden_uses_off_shrine() -> None:
    soup = BeautifulSoup((ROOT / "BbuildingView.html").read_text(encoding="utf-8"), "html.parser")
    floors = [soup.select_one(f"#floor-{index}") for index in range(1, 5)]

    assert all(floor is not None for floor in floors)
    assert {
        (floor["data-floor-width-mm"], floor["data-floor-depth-mm"], floor["data-geometry-source"])
        for floor in floors
    } == {("6000", "17630", "concept-safety-v1")}

    shrine = soup.select_one('#floor-1 .plan-cell[data-room-role="shrine"]')
    assert shrine is not None
    assert _rect(shrine) == (0.0, 12700.0, 6000.0, 17630.0)
    assert shrine["data-overhead-protection"] == "no-stair-wet-mep"

    forbidden_classes = {"stair", "wet", "water", "core"}
    conflicts: list[str] = []
    for floor in floors[1:]:
        for cell in floor.select(".plan-cell[data-x-mm][data-y-mm]"):
            if cell.get("data-equipment-free") == "true":
                continue
            classes = set(cell.get("class", []))
            material = cell.get("data-material", "")
            label = cell.get_text(" ", strip=True)
            forbidden = bool(classes & forbidden_classes) or "service+utility" in material
            if forbidden and _overlap(_rect(shrine), _rect(cell)):
                conflicts.append(f"{floor['id']}:{label}")

    assert conflicts == []

    roof_buffer = soup.select_one('#floor-4 .plan-cell[data-overhead-zone="shrine-protected"]')
    assert roof_buffer is not None
    assert roof_buffer["data-equipment-free"] == "true"
    assert _rect(roof_buffer) == _rect(shrine)


def test_b_shrine_altar_uses_the_shared_125_cm_model_near_the_rear_wall() -> None:
    soup = BeautifulSoup((ROOT / "BbuildingView.html").read_text(encoding="utf-8"), "html.parser")
    altar = soup.select_one('[data-furniture-id="B:floor-1:shrine:furniture:altar"]')

    assert altar is not None
    assert altar["data-height-mm"] == "1250"
    assert altar["data-x-ratio"] == "0.28"
    assert altar["data-y-ratio"] == "0.91"
    assert "模型總高 125cm" in soup.get_text(" ", strip=True)


def test_primary_parametric_b_variant_is_anchored_to_the_reviewed_html_grid() -> None:
    dimensions = json.loads((ROOT / "inputs/dimensions.json").read_text(encoding="utf-8"))
    brief = json.loads((ROOT / "inputs/brief/B.json").read_text(encoding="utf-8"))
    plan = json.loads((ROOT / "structured/parametric/plan.json").read_text(encoding="utf-8"))

    variant = next(item for item in plan["variants"] if item["id"] == "f6000_g1")
    building = variant["buildings"]["B"]
    layout = brief["concept_layout"]
    assert building["geometry_profile"] == "concept-safety-v1"
    assert building["geometry_provenance"] == "auto"
    assert building["protected_zone_start_mm"] == 12700
    assert building["skeleton"]["front_depth_mm"] == 6200

    ground_floor = next(
        floor for floor in building["floors"] if floor["floor_id"] == "floor-1"
    )
    idf_hall = next(cell for cell in ground_floor["cells"] if cell["id"] == "idf_b")
    ground_capacity = next(
        item for item in building["capacity"] if item["floor_id"] == "floor-1"
    )
    assert idf_hall["role"] == "corridor"
    assert idf_hall["counts_as_fixed"] is False
    assert ground_capacity["over_capacity"] is False

    source_ids = {"floor-rf": "floor-4"}
    for floor in building["floors"]:
        floor_id = floor["floor_id"]
        assert floor["anchored_layout"] is True
        assert floor["geometry_profile"] == "concept-safety-v1"
        net_x0, net_y0, net_x1, net_y1 = floor["net_rect"]
        source = dimensions["buildings"]["B"]["floors"][source_ids.get(floor_id, floor_id)]
        actual = {cell["id"]: cell["rect"] for cell in floor["cells"]}
        mapping = layout["cell_map"][floor_id]

        for source_key, raw in source["cells"].items():
            spec = mapping[source_key]
            target_id = spec if isinstance(spec, str) else spec["id"]
            x0 = net_x0 if raw["x_mm"] == 0 else int(raw["x_mm"])
            y0 = net_y0 if raw["y_mm"] == 0 else int(raw["y_mm"])
            raw_x1 = raw["x_mm"] + raw["w_mm"]
            raw_y1 = raw["y_mm"] + raw["h_mm"]
            x1 = net_x1 if raw_x1 == source["width_mm"] else int(raw_x1)
            y1 = net_y1 if raw_y1 == source["depth_mm"] else int(raw_y1)
            assert actual[target_id] == [x0, y0, x1, y1]


def test_primary_parametric_b_variant_keeps_shrine_projection_clear() -> None:
    plan = json.loads((ROOT / "structured/parametric/plan.json").read_text(encoding="utf-8"))
    variant = next(item for item in plan["variants"] if item["id"] == "f6000_g1")
    building = variant["buildings"]["B"]
    ground = next(floor for floor in building["floors"] if floor["floor_id"] == "floor-1")
    shrine = next(cell for cell in ground["cells"] if cell["id"] == "shrine")
    shrine_rect = tuple(shrine["rect"])

    hazards: list[str] = []
    for floor in building["floors"][1:]:
        for cell in floor["cells"]:
            forbidden = (
                cell["kind"] in {"bath", "kitchen", "service"}
                or cell["role"] in {"stair", "shaft"}
                or cell.get("penthouse_class") in {"tank", "open_mep", "energy"}
                or (cell["kind"] == "outdoor" and "陽台" in cell["name"])
            )
            if forbidden and _overlap(shrine_rect, tuple(cell["rect"])):
                hazards.append(f"{floor['floor_id']}:{cell['id']}")

    assert hazards == []
    findings = [
        finding
        for finding in plan["findings"]
        if finding["variant"] == "f6000_g1" and finding["building"] == "B"
    ]
    assert not ({
        "GARAGE_NOT_PARKABLE",
        "WHEELCHAIR_TURN",
        "CAPACITY_OVERFLOW",
        "SHRINE_STACK",
        "ACCESS_UNREALISABLE",
        "BAND_UNREALISABLE",
        "NESTED_ACCESS",
        "BALCONY_NOT_ON_FACADE",
    } & {finding["code"] for finding in findings})


def test_parametric_shrine_rule_catches_wet_stair_and_roof_equipment() -> None:
    shrine = {
        "id": "shrine",
        "name": "神明廳",
        "kind": "living",
        "role": "room",
        "rect": [0, 100, 6000, 5000],
    }
    hazards = [
        {"id": "bath", "name": "衛浴", "kind": "bath", "role": "room"},
        {"id": "stair", "name": "樓梯", "kind": "stair", "role": "stair"},
        {
            "id": "tank",
            "name": "水塔",
            "kind": "service",
            "role": "room",
            "penthouse_class": "tank",
        },
    ]
    building = {
        "floors": [
            {"floor_id": "floor-1", "label": "1F", "cells": [shrine]},
            {
                "floor_id": "floor-2",
                "label": "2F",
                "cells": [{**hazards[0], "rect": [0, 100, 2000, 2000]}],
            },
            {
                "floor_id": "floor-3",
                "label": "3F",
                "cells": [{**hazards[1], "rect": [2000, 100, 4000, 2000]}],
            },
            {
                "floor_id": "floor-rf",
                "label": "RF",
                "cells": [{**hazards[2], "rect": [4000, 100, 6000, 2000]}],
            },
        ]
    }

    findings = _check_stacking(building)
    assert [finding["code"] for finding in findings] == ["SHRINE_STACK"] * 3
    assert {finding["refs"][0] for finding in findings} == {"bath", "stair", "tank"}

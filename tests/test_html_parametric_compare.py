from __future__ import annotations

from lib.html_parametric_compare import (
    aabbs_overlap,
    build_compare,
    compare_floor,
    find_cell_overlaps,
    format_compare_panel,
    pick_variant,
    resolve_html_to_para,
)


def test_aabbs_overlap_detects_intersection() -> None:
    garage = {"x_mm": 0, "y_mm": 0, "w_mm": 5500, "h_mm": 6000}
    entry = {"x_mm": 0, "y_mm": 1200, "w_mm": 3667, "h_mm": 1300}
    living = {"x_mm": 3667, "y_mm": 1200, "w_mm": 7333, "h_mm": 1300}
    assert aabbs_overlap(garage, entry)
    assert aabbs_overlap(garage, living)
    assert not aabbs_overlap(entry, living)


def test_find_cell_overlaps_reports_pairs() -> None:
    cells = [
        {"key": "garage", "name": "前院車庫", "declared_mm": {"x_mm": 0, "y_mm": 0, "w_mm": 5500, "h_mm": 6000}},
        {"key": "entry", "name": "玄關", "declared_mm": {"x_mm": 0, "y_mm": 1200, "w_mm": 3667, "h_mm": 1300}},
        {"key": "kitchen", "name": "廚房", "declared_mm": {"x_mm": 0, "y_mm": 7000, "w_mm": 6000, "h_mm": 1300}},
    ]
    hits = find_cell_overlaps(cells, "declared_mm", "A", "floor-1")
    pairs = {(h["a"], h["b"]) for h in hits}
    assert ("garage", "entry") in pairs
    assert ("garage", "kitchen") not in pairs


def test_resolve_maps_merges_and_hyphens() -> None:
    para = {"living", "elder", "master_bath", "entry"}
    assert resolve_html_to_para("A", "dining", para) == "living"
    assert resolve_html_to_para("A", "flex1", para) == "elder"
    assert resolve_html_to_para("A", "master-bath", para) == "master_bath"
    assert resolve_html_to_para("A", "entry", para) == "entry"
    assert resolve_html_to_para("A", "sideyard", para) is None
    assert resolve_html_to_para("B", "bath1", {"bath_acc"}) == "bath_acc"


def test_compare_floor_living_dining_merge() -> None:
    html_floor = {
        "id": "floor-1",
        "tab_label": "1F",
        "plan_cells": [
            {"target_room_local_id": "living", "name": "客廳"},
            {"target_room_local_id": "dining", "name": "餐廳"},
            {"target_room_local_id": "entry", "name": "玄關"},
            {"target_room_local_id": "sideyard", "name": "側院"},
        ],
    }
    para_floor = {
        "floor_id": "floor-1",
        "cells": [
            {"id": "living", "name": "客餐廳（開放式）", "role": "room"},
            {"id": "entry", "name": "玄關（含車庫進屋緩衝）", "role": "room"},
            {"id": "corridor", "name": "走道", "role": "corridor"},
        ],
    }
    result = compare_floor("A", html_floor, para_floor)
    assert result["merged"][0]["para_id"] == "living"
    html_ids = {h["id"] for h in result["merged"][0]["html"]}
    assert html_ids == {"living", "dining"}
    assert any(c["id"] == "sideyard" for c in result["html_only"])
    assert any(c["html_id"] == "entry" for c in result["matched"])
    assert any(c["id"] == "corridor" for c in result["para_only"])


def test_floor_4_maps_to_rf_label() -> None:
    html_floor = {"id": "floor-4", "tab_label": "RF", "plan_cells": []}
    para_floor = {"floor_id": "floor-rf", "cells": []}
    result = compare_floor("A", html_floor, para_floor)
    assert result["para_floor_id"] == "floor-rf"
    assert "RF" in result["label"]


def test_build_compare_and_panel_from_synthetic_plan() -> None:
    program = {
        "buildings": [
            {
                "id": "A",
                "floors": [
                    {
                        "id": "floor-1",
                        "record_type": "floor",
                        "tab_label": "1F",
                        "geometry_auto_mm": {"width_mm": 11000, "depth_mm": 7700},
                        "plan_cells": [
                            {"target_room_local_id": "living", "name": "客廳"},
                            {"target_room_local_id": "dining", "name": "餐廳"},
                        ],
                    }
                ],
            }
        ]
    }
    plan = {
        "site": {"storey_height_mm": 3000, "parapet_height_mm": 1100, "storeys": 3},
        "variants": [
            {
                "id": "f6000-g1",
                "frontage_mm": 6000,
                "depth_mm": 17630,
                "footprint_ping": 32,
                "garage": {"bays": 1},
                "buildings": {
                    "A": {
                        "frontage_mm": 6000,
                        "depth_mm": 17630,
                        "floors": [
                            {
                                "floor_id": "floor-1",
                                "cells": [
                                    {"id": "living", "name": "客餐廳（開放式）", "role": "room"},
                                ],
                            }
                        ],
                    }
                },
            }
        ],
    }
    compare = build_compare(program, plan)
    assert compare["available"]
    assert compare["ghost"]["frontage_mm"] == 6000
    assert compare["ghost"]["depth_mm"] == 17630
    html = format_compare_panel(compare)
    assert "客餐廳" in html
    assert "客廳" in html
    assert pick_variant(plan, 6000, 1)["id"] == "f6000-g1"

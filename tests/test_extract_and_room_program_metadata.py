from __future__ import annotations

from bs4 import BeautifulSoup

from build_room_program import build_program, transform_floor
from extract_layout_data import SCHEMA_VERSION, extract_floor


def test_extract_floor_emits_v3_orientation_and_cell_spatial() -> None:
    html = """
    <div class="floor-plan" id="floor-2" data-floor-width-mm="11000" data-floor-depth-mm="5200"
         data-north-deg="0" data-front-side="top" data-rear-side="bottom"
         data-site-orientation-note="front faces road">
      <div class="floor-title"><div>2F</div></div>
      <div class="plan-grid-visual">
        <div class="plan-row" data-row-h-mm="1700" style="grid-template-columns:1fr;">
          <div class="plan-cell outdoor" data-x-mm="5500" data-y-mm="3500" data-w-mm="5500" data-h-mm="1700"
               data-window-mm="0" data-zone="rear" data-facing="rear"
               data-outdoor-role="kaohsiung-house-balcony" onclick="highlightRoom('balcony2', this)">
            <span class="cell-name">高雄厝陽台</span>
          </div>
        </div>
      </div>
      <div class="room" id="room-balcony2"></div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    floor = extract_floor(soup.select_one(".floor-plan"), 1)

    assert SCHEMA_VERSION == "house-design-structured-v3"
    assert floor["orientation"] == {
        "front_side": "top",
        "rear_side": "bottom",
        "site_orientation_note": "front faces road",
    }
    assert floor["plan_cells"][0]["spatial"] == {
        "zone": "rear",
        "facing": "rear",
        "outdoor_role": "kaohsiung-house-balcony",
        "is_outdoor_like": True,
        "room_role": "unknown",
        "is_accessible": False,
        "daylight_required": None,
    }


def test_build_room_program_preserves_orientation_and_cell_spatial() -> None:
    floor = {
        "id": "floor-2",
        "order": 1,
        "title": "2F",
        "subtitle": "",
        "direction_badges": [],
        "orientation": {"front_side": "top", "rear_side": "bottom", "site_orientation_note": "front faces road"},
        "geometry_mm": {"width_mm": 11000, "depth_mm": 5200, "north_deg": 0},
        "geometry_source": "test",
        "rooms": [{"order": 1, "id": "balcony2", "name": "高雄厝陽台", "area": "", "details": [], "tags": []}],
        "plan_cells": [
            {
                "order": 1,
                "target_room_id": "balcony2",
                "name": "高雄厝陽台",
                "icon": "",
                "size": "",
                "badges": [],
                "classes": ["outdoor"],
                "row_order": 1,
                "col_order": 1,
                "col_weight": 1,
                "row_template_columns": [1],
                "geometry_mm": {"x_mm": 5500, "y_mm": 3500, "w_mm": 5500, "h_mm": 1700},
                "openings_mm": {"window_mm": 0},
                "is_entry": False,
                "material": "concrete+drain",
                "spatial": {
                    "zone": "rear",
                    "facing": "rear",
                    "outdoor_role": "kaohsiung-house-balcony",
                    "is_outdoor_like": True,
                    "room_role": "unknown",
                    "is_accessible": False,
                    "daylight_required": None,
                },
            }
        ],
        "plan_rows": [],
        "tables": [],
        "checklists": [],
        "section_blocks": [],
    }

    program_floor = transform_floor("A", floor, [])

    assert program_floor["orientation"]["front_side"] == "top"
    assert program_floor["plan_cells"][0]["spatial"]["outdoor_role"] == "kaohsiung-house-balcony"


def test_room_semantics_are_extracted_and_preserved() -> None:
    html = """
    <div class="floor-plan" id="floor-1" data-floor-width-mm="1000" data-floor-depth-mm="1000">
      <div class="floor-title"><div>1F</div></div>
      <div class="plan-grid-visual">
        <div class="plan-row">
          <div class="plan-cell" data-x-mm="0" data-y-mm="0" data-w-mm="500" data-h-mm="500"
               data-window-mm="800" data-room-role="elder" data-accessible="true"
               data-structural-review="required"
               onclick="highlightRoom('elder', this)">
            <span class="cell-name">孝親房</span>
          </div>
        </div>
      </div>
      <div class="room" id="room-elder" data-target-cell="slot-1" data-structural-review="required"
           data-room-role="elder" data-accessible="true">
        <div class="room-name">孝親房</div>
        <div class="room-details"><li>輪椅友善</li></div>
      </div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    floor = extract_floor(soup.select_one(".floor-plan"), 1)
    program_floor = transform_floor("C", floor, [])

    assert floor["plan_cells"][0]["spatial"]["room_role"] == "elder"
    assert floor["rooms"][0]["semantics"]["room_role"] == "elder"
    assert program_floor["plan_cells"][0]["spatial"]["is_accessible"] is True
    assert program_floor["rooms"][0]["semantics"]["is_accessible"] is True
    assert program_floor["rooms"][0]["structural_review"] == "required"
    assert program_floor["plan_cells"][0]["structural_review"] == "required"
    assert program_floor["record_type"] == "floor"


def test_build_program_emits_v3_source_schema_metadata() -> None:
    program = build_program(
        [
            {
                "source_file": "abuilding.html",
                "meta": {"title": "Example"},
                "tabs": [],
                "floors": [],
            }
        ]
    )

    assert program["source_schema_version"] == "house-design-structured-v3"
    assert program["compatible_source_schema_versions"] == [
        "house-design-structured-v2",
        "house-design-structured-v3",
    ]


def test_transform_floor_backfills_v2_shape_metadata_defaults() -> None:
    floor = {
        "id": "floor-1",
        "order": 1,
        "title": "1F",
        "subtitle": "",
        "direction_badges": [],
        "geometry_mm": {"width_mm": 11000, "depth_mm": 5200, "north_deg": 0},
        "geometry_source": "test",
        "rooms": [{"order": 1, "id": "room-1", "name": "Living Room", "area": "", "details": [], "tags": []}],
        "plan_cells": [
            {
                "order": 1,
                "target_room_id": "room-1",
                "name": "Living Room",
                "icon": "",
                "size": "",
                "badges": [],
                "classes": [],
                "row_order": 1,
                "col_order": 1,
                "col_weight": 1,
                "row_template_columns": [1],
                "geometry_mm": {"x_mm": 0, "y_mm": 0, "w_mm": 3000, "h_mm": 3000},
                "openings_mm": {},
                "is_entry": False,
                "material": "",
            }
        ],
        "plan_rows": [],
        "tables": [],
        "checklists": [],
        "section_blocks": [],
    }

    transformed = transform_floor("A", floor, [])

    assert transformed["orientation"] == {
        "front_side": "unknown",
        "rear_side": "unknown",
        "site_orientation_note": "",
    }
    assert transformed["plan_cells"][0]["spatial"] == {
        "zone": "unknown",
        "facing": "unknown",
        "outdoor_role": "none",
        "is_outdoor_like": False,
        "room_role": "unknown",
        "is_accessible": False,
        "daylight_required": None,
    }

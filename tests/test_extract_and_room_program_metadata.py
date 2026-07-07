from __future__ import annotations

from bs4 import BeautifulSoup

from build_room_program import transform_floor
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

from __future__ import annotations

from lib.spatial_metadata import (
    is_outdoor_like,
    nearest_declared_side,
    parse_cell_spatial,
    parse_floor_orientation,
    window_issue_level,
)


def test_parse_floor_orientation_normalizes_known_sides() -> None:
    orientation = parse_floor_orientation(
        {
            "data-front-side": "Top",
            "data-rear-side": "bottom",
            "data-site-orientation-note": " front faces road ",
        }
    )

    assert orientation == {
        "front_side": "top",
        "rear_side": "bottom",
        "site_orientation_note": "front faces road",
    }


def test_parse_floor_orientation_defaults_unknown_sides() -> None:
    orientation = parse_floor_orientation({"data-front-side": "street"})

    assert orientation["front_side"] == "unknown"
    assert orientation["rear_side"] == "unknown"
    assert orientation["site_orientation_note"] == ""


def test_parse_cell_spatial_prefers_explicit_values_and_outdoor_role() -> None:
    spatial = parse_cell_spatial(
        {
            "data-zone": "rear",
            "data-facing": "Side",
            "data-outdoor-role": "kaohsiung-house-balcony",
        },
        classes=["plan-cell", "outdoor"],
    )

    assert spatial == {
        "zone": "rear",
        "facing": "side",
        "outdoor_role": "kaohsiung-house-balcony",
        "is_outdoor_like": True,
    }


def test_outdoor_window_zero_is_not_a_warning() -> None:
    spatial = parse_cell_spatial({"data-outdoor-role": "balcony"}, classes=[])

    assert window_issue_level(spatial, [], True, 0, 300, 3600) == ""


def test_indoor_window_zero_is_warning() -> None:
    spatial = parse_cell_spatial({"data-outdoor-role": "none"}, classes=[])

    assert window_issue_level(spatial, [], True, 0, 300, 3600) == "warning"


def test_indoor_missing_window_is_warning() -> None:
    spatial = parse_cell_spatial({"data-zone": "core"}, classes=[])

    assert window_issue_level(spatial, [], False, None, 300, 3600) == "warning"


def test_outdoor_missing_window_is_not_a_warning() -> None:
    spatial = parse_cell_spatial({"data-outdoor-role": "terrace"}, classes=[])

    assert window_issue_level(spatial, [], False, None, 300, 3600) == ""


def test_nearest_declared_side_detects_front_and_rear() -> None:
    front = nearest_declared_side(
        11000,
        5200,
        {"x_mm": 1000, "y_mm": 200, "w_mm": 1000, "h_mm": 800},
        "top",
        "bottom",
    )
    rear = nearest_declared_side(
        11000,
        5200,
        {"x_mm": 7000, "y_mm": 4200, "w_mm": 1000, "h_mm": 800},
        "top",
        "bottom",
    )

    assert front["nearest_role"] == "front"
    assert front["ambiguous"] is False
    assert rear["nearest_role"] == "rear"
    assert rear["ambiguous"] is False


def test_nearest_declared_side_marks_large_spanning_cells_ambiguous() -> None:
    result = nearest_declared_side(
        11000,
        5200,
        {"x_mm": 0, "y_mm": 1000, "w_mm": 11000, "h_mm": 3600},
        "top",
        "bottom",
    )

    assert result["nearest_role"] == "unknown"
    assert result["ambiguous"] is True

from __future__ import annotations

from lib.spatial_metadata import (
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
        "room_role": "unknown",
        "is_accessible": False,
        "daylight_required": None,
    }


def test_parse_cell_spatial_preserves_semantic_roles() -> None:
    spatial = parse_cell_spatial(
        {
            "data-zone": "rear",
            "data-facing": "internal",
            "data-outdoor-role": "laundry-yard",
            "data-room-role": "accessible-bath",
            "data-accessible": "true",
            "data-daylight-required": "false",
        },
        ["outdoor"],
    )

    assert spatial == {
        "zone": "rear",
        "facing": "internal",
        "outdoor_role": "laundry-yard",
        "is_outdoor_like": True,
        "room_role": "accessible-bath",
        "is_accessible": True,
        "daylight_required": False,
    }


def test_parse_cell_spatial_defaults_semantics() -> None:
    spatial = parse_cell_spatial({}, [])

    assert spatial["room_role"] == "unknown"
    assert spatial["is_accessible"] is False
    assert spatial["daylight_required"] is None


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


def test_nearest_declared_side_marks_wide_top_bottom_span_ambiguous() -> None:
    result = nearest_declared_side(
        11000,
        5200,
        {"x_mm": 1000, "y_mm": 200, "w_mm": 9000, "h_mm": 500},
        "top",
        "bottom",
    )

    assert result["nearest_role"] == "unknown"
    assert result["nearest_side"] == "unknown"
    assert result["ambiguous"] is True


def test_nearest_declared_side_marks_tall_left_right_span_ambiguous() -> None:
    result = nearest_declared_side(
        11000,
        5200,
        {"x_mm": 200, "y_mm": 500, "w_mm": 500, "h_mm": 4000},
        "left",
        "right",
    )

    assert result["nearest_role"] == "unknown"
    assert result["nearest_side"] == "unknown"
    assert result["ambiguous"] is True


def test_nearest_declared_side_uses_depth_for_top_bottom_tolerance() -> None:
    result = nearest_declared_side(
        11000,
        5200,
        {"x_mm": 1000, "y_mm": 2450, "w_mm": 1000, "h_mm": 1000},
        "top",
        "bottom",
    )

    assert result["nearest_role"] == "rear"
    assert result["nearest_side"] == "bottom"
    assert result["ambiguous"] is False


def test_nearest_declared_side_uses_width_for_left_right_tolerance() -> None:
    result = nearest_declared_side(
        5200,
        11000,
        {"x_mm": 2450, "y_mm": 1000, "w_mm": 1000, "h_mm": 1000},
        "left",
        "right",
    )

    assert result["nearest_role"] == "rear"
    assert result["nearest_side"] == "right"
    assert result["ambiguous"] is False

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

FLOOR_SIDES = {"top", "right", "bottom", "left"}
CELL_ZONES = {"front", "rear", "side", "core", "service", "roof", "unknown"}
CELL_FACING = {"front", "rear", "left", "right", "side", "roof", "internal", "unknown"}
OUTDOOR_ROLES = {
    "balcony",
    "kaohsiung-house-balcony",
    "terrace",
    "side-yard",
    "garage",
    "service-yard",
    "roof-platform",
    "planting",
    "utility",
}
OUTDOOR_CLASSES = {"outdoor", "garage", "terrace", "balcony", "side-yard"}


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_token(value: Any, allowed: set[str], default: str = "unknown") -> str:
    token = normalize_text(value).lower()
    return token if token in allowed else default


def parse_floor_orientation(attrs: Mapping[str, Any]) -> dict[str, str]:
    return {
        "front_side": normalize_token(attrs.get("data-front-side"), FLOOR_SIDES),
        "rear_side": normalize_token(attrs.get("data-rear-side"), FLOOR_SIDES),
        "site_orientation_note": normalize_text(attrs.get("data-site-orientation-note")),
    }


def parse_cell_spatial(attrs: Mapping[str, Any], classes: Iterable[str]) -> dict[str, Any]:
    outdoor_role = normalize_token(attrs.get("data-outdoor-role"), OUTDOOR_ROLES | {"none"}, "none")
    spatial = {
        "zone": normalize_token(attrs.get("data-zone"), CELL_ZONES),
        "facing": normalize_token(attrs.get("data-facing"), CELL_FACING),
        "outdoor_role": outdoor_role,
    }
    spatial["is_outdoor_like"] = is_outdoor_like(spatial, classes)
    return spatial


def is_outdoor_like(spatial: Mapping[str, Any], classes: Iterable[str]) -> bool:
    role = normalize_text(spatial.get("outdoor_role")).lower()
    if role and role != "none":
        return True
    class_set = {normalize_text(cls).lower() for cls in classes}
    return bool(class_set & OUTDOOR_CLASSES)


def window_issue_level(
    spatial: Mapping[str, Any],
    classes: Iterable[str],
    has_window_attr: bool,
    window_mm: int | None,
    min_mm: int,
    max_mm: int,
    opening_required_roles: Iterable[str] = (),
) -> str:
    role = normalize_text(spatial.get("outdoor_role")).lower()
    required_roles = {normalize_text(item).lower() for item in opening_required_roles}
    if is_outdoor_like(spatial, classes):
        if not has_window_attr and role in required_roles:
            return "info"
        return ""
    if not has_window_attr:
        return "warning"
    if window_mm is None:
        return "warning"
    if min_mm <= window_mm <= max_mm:
        return ""
    return "warning"


def _distance_to_side(
    floor_width_mm: float,
    floor_depth_mm: float,
    center_x: float,
    center_y: float,
    side: str,
) -> float:
    if side == "top":
        return center_y
    if side == "bottom":
        return floor_depth_mm - center_y
    if side == "left":
        return center_x
    if side == "right":
        return floor_width_mm - center_x
    return float("inf")


def _span_for_side(rect: Mapping[str, float], side: str) -> float:
    if side in {"top", "bottom"}:
        return float(rect.get("h_mm", 0))
    if side in {"left", "right"}:
        return float(rect.get("w_mm", 0))
    return 0.0


def nearest_declared_side(
    floor_width_mm: float | None,
    floor_depth_mm: float | None,
    rect: Mapping[str, float],
    front_side: str,
    rear_side: str,
    tolerance_ratio: float = 0.10,
    span_ratio: float = 0.70,
) -> dict[str, Any]:
    if not floor_width_mm or not floor_depth_mm:
        return {"nearest_role": "unknown", "nearest_side": "unknown", "ambiguous": True}
    if front_side not in FLOOR_SIDES or rear_side not in FLOOR_SIDES or front_side == rear_side:
        return {"nearest_role": "unknown", "nearest_side": "unknown", "ambiguous": True}

    x = float(rect.get("x_mm", 0))
    y = float(rect.get("y_mm", 0))
    w = float(rect.get("w_mm", 0))
    h = float(rect.get("h_mm", 0))
    center_x = x + w / 2
    center_y = y + h / 2

    front_distance = _distance_to_side(floor_width_mm, floor_depth_mm, center_x, center_y, front_side)
    rear_distance = _distance_to_side(floor_width_mm, floor_depth_mm, center_x, center_y, rear_side)
    relevant_dimension = floor_depth_mm if front_side in {"top", "bottom"} else floor_width_mm
    span = max(_span_for_side(rect, front_side), _span_for_side(rect, rear_side))

    if abs(front_distance - rear_distance) < relevant_dimension * tolerance_ratio:
        return {"nearest_role": "unknown", "nearest_side": "unknown", "ambiguous": True}
    if span > relevant_dimension * span_ratio:
        return {"nearest_role": "unknown", "nearest_side": "unknown", "ambiguous": True}

    if front_distance < rear_distance:
        return {"nearest_role": "front", "nearest_side": front_side, "ambiguous": False}
    return {"nearest_role": "rear", "nearest_side": rear_side, "ambiguous": False}

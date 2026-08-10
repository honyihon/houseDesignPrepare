#!/usr/bin/env python3
"""Shared residential defaults for layout conversion/rendering scripts."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "scripts" / "config" / "residential_defaults_tw.json"


def repo_relative(path: Any) -> str:
    """Render a path relative to the repo root, with forward slashes.

    Generated artefacts under ``structured/`` are committed and read on other
    machines; an absolute path like ``D:\\I29786\\...`` baked in on one checkout
    is meaningless everywhere else. Paths outside the repo are returned as-is
    with slashes normalised, since there is nothing better to say about them.
    """

    if not path:
        return ""
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except (ValueError, OSError):
        return str(path).replace("\\", "/")

# Fallback values keep the pipeline usable even when config file is missing.
FALLBACK_DEFAULTS: dict[str, Any] = {
    "schema_version": "residential-defaults-tw-v1",
    "profile": "tw_general_residential_2026",
    "updated_at": "",
    "notes": [
        "Used when source drawing does not provide exact dimensions.",
        "Values are practical defaults for concept/draft layout conversion.",
    ],
    "geometry": {
        "px_per_mm": 0.06,
        "wall_thickness_mm": {"interior": 115, "exterior": 200},
        "door_width_mm": {"entry": 1000, "accessible": 900, "interior": 900, "bathroom": 800, "service": 800},
        "door_height_mm": 2100,
        "window_width_mm": {
            "living": 1800,
            "dining": 1500,
            "bedroom": 1200,
            "kitchen": 900,
            "bath": 600,
            "service": 600,
            "other": 1000,
        },
    },
    "architect_metrics": {
        "room_height_mm": 3000,
        "window_sill_height_mm": 900,
        "window_height_mm": 1200,
        "glazing_transmittance": 0.65,
        "average_reflectance": 0.5,
        "daylight_target_pct": 2.0,
        "egress_proxy_warning_m": 30.0,
    },
    "furniture_mm": {
        "bed_double": {"width": 1500, "depth": 1900},
        "sofa_3": {"width": 2100, "depth": 900},
        "dining_table_6": {"width": 1600, "depth": 800},
        "kitchen_counter_depth": 650,
    },
    # Clear (car-side) dimensions; the generator adds wall thickness itself.
    "vehicle": {
        "suv_mm": {"length": 4900, "width": 1950, "height": 1800},
        "clearance_mm": {
            "driver_side": 700,
            "passenger_side": 350,
            "between_bays": 300,
            "front": 600,
            "rear": 500,
        },
        "ev_charger_mm": {"depth": 400, "width": 600, "clear": 300, "mount": "front_wall"},
    },
    "drawing": {
        "font_family": "Segoe UI, Microsoft JhengHei, sans-serif",
        "default_style": "presentation",
        "interior_wall_factor": 0.32,
        "exterior_wall_extra_px": 1.2,
        "window_line_width_px": 2.2,
        "dimension_line_color": "#777",
        "style_profiles": {
            "presentation": {
                "presentation_version": 2,
                "show_debug_header": False,
                "show_room_notes": False,
                "show_opening_labels": False,
                "show_dimensions": True,
                "show_dimension_subchains": False,
                "show_right_legend": False,
                "show_bottom_legend": True,
                "show_elevation_indices": False,
                "show_furniture": True,
                "show_score_line": False,
                "plan_left_px": 58,
                "plan_top_px": 90,
                "plan_width_px": 1040,
                "right_panel_width_px": 64,
                "bottom_padding_px": 136,
                "furniture_opacity": 0.42,
                "colors": {
                    "paper": "#f3f4f6",
                    "plan_background": "#ffffff",
                    "frame": "#d1d5db",
                    "text": "#111827",
                    "muted": "#64748b",
                    "wall_outer": "#111827",
                    "wall_inner": "#374151",
                    "dimension": "#9ca3af",
                    "door": "#475569",
                    "window": "#2563eb",
                    "furniture_fill": "#ffffff",
                    "furniture_stroke": "#64748b",
                    "label_halo": "#ffffff",
                    "hatch": "#94a3b8",
                },
                "room_fills": {
                    "entry": "#fffaf3",
                    "living": "#fffaf3",
                    "dining": "#fffbeb",
                    "bedroom": "#f7f8ff",
                    "bath": "#f3fdff",
                    "kitchen": "#f5fff8",
                    "service": "#f7f9fc",
                    "stair": "#f8fafc",
                    "outdoor": "#f2fbf5",
                    "other": "#ffffff",
                },
            },
            "technical": {
                "show_debug_header": False,
                "show_room_notes": False,
                "show_opening_labels": True,
                "show_dimensions": True,
                "show_dimension_subchains": True,
                "show_right_legend": False,
                "show_bottom_legend": True,
                "show_elevation_indices": True,
                "show_furniture": True,
                "show_score_line": True,
                "plan_left_px": 58,
                "plan_top_px": 104,
                "plan_width_px": 1010,
                "right_panel_width_px": 48,
                "bottom_padding_px": 144,
                "colors": {
                    "paper": "#f8fafc",
                    "plan_background": "#ffffff",
                    "frame": "#b8c2d2",
                    "text": "#111827",
                    "muted": "#56657a",
                    "wall_outer": "#111111",
                    "wall_inner": "#222222",
                    "dimension": "#6b7280",
                    "door": "#334155",
                    "window": "#1d6fa5",
                    "furniture_fill": "#f6f6f6",
                    "furniture_stroke": "#555555",
                },
                "room_fills": {
                    "entry": "#fff7ed",
                    "living": "#fff7ed",
                    "dining": "#fffbeb",
                    "bedroom": "#eef2ff",
                    "bath": "#ecfeff",
                    "kitchen": "#f0fdf4",
                    "service": "#f1f5f9",
                    "stair": "#f8fafc",
                    "outdoor": "#ecfdf5",
                    "other": "#ffffff",
                },
            },
            "debug": {
                "show_debug_header": True,
                "show_room_notes": True,
                "show_opening_labels": True,
                "show_dimensions": True,
                "show_dimension_subchains": True,
                "show_right_legend": True,
                "show_bottom_legend": False,
                "show_elevation_indices": True,
                "show_furniture": True,
                "show_score_line": True,
                "plan_left_px": 58,
                "plan_top_px": 116,
                "plan_width_px": 980,
                "right_panel_width_px": 236,
                "bottom_padding_px": 152,
                "colors": {
                    "paper": "#f6f6f6",
                    "plan_background": "#ffffff",
                    "frame": "#b5b5b5",
                    "text": "#111111",
                    "muted": "#555555",
                    "wall_outer": "#111111",
                    "wall_inner": "#1d1d1d",
                    "dimension": "#777777",
                    "door": "#666666",
                    "window": "#2d6ea3",
                    "furniture_fill": "#f6f6f6",
                    "furniture_stroke": "#555555",
                },
                "room_fills": {
                    "entry": "#fdfdfd",
                    "living": "#fdfdfd",
                    "dining": "#fdfdfd",
                    "bedroom": "#fdfdfd",
                    "bath": "#fbfbfb",
                    "kitchen": "#fdfdfd",
                    "service": "#fcfcfc",
                    "stair": "#fdfdfd",
                    "outdoor": "#fafafa",
                    "other": "#fdfdfd",
                },
            },
        },
    },
    "validation": {
        "required_markers": ["ENT", "DW:", "WIN:", "DIM:", "LEGEND:", "ELEV:"],
        "min_exported_floor_count": 1,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        current = base.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            _deep_merge(current, value)
        else:
            base[key] = value
    return base


def load_residential_defaults(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or DEFAULT_CONFIG_PATH
    merged = copy.deepcopy(FALLBACK_DEFAULTS)

    meta = {
        "config_path": str(path),
        "config_exists": path.exists(),
        "config_loaded": False,
    }

    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid residential defaults JSON: {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Residential defaults must be a JSON object: {path}")
        _deep_merge(merged, payload)
        meta["config_loaded"] = True

    merged["_meta"] = meta
    return merged


def wall_thickness_mm(defaults: dict[str, Any]) -> dict[str, int]:
    geometry = defaults.get("geometry", {})
    walls = geometry.get("wall_thickness_mm", {})
    return {
        "interior": int(walls.get("interior", 115)),
        "exterior": int(walls.get("exterior", 200)),
    }


def door_width_mm(defaults: dict[str, Any]) -> dict[str, int]:
    geometry = defaults.get("geometry", {})
    doors = geometry.get("door_width_mm", {})
    return {
        "entry": int(doors.get("entry", 1000)),
        "interior": int(doors.get("interior", 900)),
        "bathroom": int(doors.get("bathroom", 800)),
        "service": int(doors.get("service", 800)),
    }


def window_width_mm(defaults: dict[str, Any]) -> dict[str, int]:
    geometry = defaults.get("geometry", {})
    windows = geometry.get("window_width_mm", {})
    return {
        "living": int(windows.get("living", 1800)),
        "dining": int(windows.get("dining", 1500)),
        "bedroom": int(windows.get("bedroom", 1200)),
        "kitchen": int(windows.get("kitchen", 900)),
        "bath": int(windows.get("bath", 600)),
        "service": int(windows.get("service", 600)),
        "other": int(windows.get("other", 1000)),
    }


def px_per_mm(defaults: dict[str, Any]) -> float:
    geometry = defaults.get("geometry", {})
    try:
        return float(geometry.get("px_per_mm", 0.06))
    except (TypeError, ValueError):
        return 0.06


def drawing_font_family(defaults: dict[str, Any]) -> str:
    drawing = defaults.get("drawing", {})
    return str(drawing.get("font_family", "Segoe UI, Microsoft JhengHei, sans-serif"))


def defaults_summary_line(defaults: dict[str, Any]) -> str:
    wall = wall_thickness_mm(defaults)
    door = door_width_mm(defaults)
    return (
        f"Default dims(mm): wall int/ext {wall['interior']}/{wall['exterior']} | "
        f"door entry/int/bath {door['entry']}/{door['interior']}/{door['bathroom']}"
    )

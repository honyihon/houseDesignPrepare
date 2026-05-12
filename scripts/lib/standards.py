#!/usr/bin/env python3
"""Shared residential defaults for layout conversion/rendering scripts."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "scripts" / "config" / "residential_defaults_tw.json"

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
        "door_width_mm": {"entry": 1000, "interior": 900, "bathroom": 800, "service": 800},
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
    "drawing": {
        "font_family": "Segoe UI, Microsoft JhengHei, sans-serif",
        "interior_wall_factor": 0.32,
        "exterior_wall_extra_px": 1.2,
        "window_line_width_px": 2.2,
        "dimension_line_color": "#777",
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
            if isinstance(payload, dict):
                _deep_merge(merged, payload)
                meta["config_loaded"] = True
        except json.JSONDecodeError:
            meta["config_loaded"] = False

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

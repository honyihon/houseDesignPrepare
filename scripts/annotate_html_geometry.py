#!/usr/bin/env python3
"""Batch annotate floor-plan HTML files with geometry/opening data-* attributes.

This script updates all root-level HTML files (including *_tmp) that contain
.floor-plan/.plan-grid-visual structures. Existing data-* values are preserved.

IMPORTANT — these numbers are heuristics, not measurements
----------------------------------------------------------
Nothing in the HTML records a real dimension.  Every ``data-*-mm`` value this
script writes is inferred from CSS: row depth from a class lookup table (see
``row_height_mm``), column widths from the ``grid-template-columns`` ``fr``
weights, floor width from the constant ``DEFAULT_FLOOR_WIDTH_MM``, and north
from ``DEFAULT_NORTH_DEG`` (always 0).  They are a plausible-looking scaffold
so the drawings render, and that is all.

Real dimensions belong in ``inputs/dimensions.json``, which
``scripts/lib/dimension_overrides.py`` layers on top of the room program.
Values from there win over anything written here, and every cell carries a
``geometry_provenance`` marker so downstream consumers can tell a survey from a
guess.  Run ``scripts/seed_dimension_overrides.py`` to see what still needs
measuring (``structured/dimension_todo.md``).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag


ROOT = Path(__file__).resolve().parents[1]
TARGET_GLOB = "*.html"

DEFAULT_FLOOR_WIDTH_MM = 11000
DEFAULT_NORTH_DEG = 0


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = normalize(str(value))
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_grid_template_columns(template_text: str) -> list[float]:
    raw = normalize(template_text)
    if not raw:
        return []

    repeat_match = re.fullmatch(r"repeat\(\s*(\d+)\s*,\s*([0-9]*\.?[0-9]+)\s*fr\s*\)", raw, flags=re.IGNORECASE)
    if repeat_match:
        count = int(repeat_match.group(1))
        value = float(repeat_match.group(2))
        return [value for _ in range(max(0, count))]

    values: list[float] = []
    for token in raw.replace(",", " ").split():
        token = token.strip().lower()
        if token == "fr":
            values.append(1.0)
            continue
        match = re.fullmatch(r"([0-9]*\.?[0-9]+)\s*fr", token, flags=re.IGNORECASE)
        if match:
            values.append(float(match.group(1)))
    return values


def parse_inline_style(style_text: str) -> dict[str, str]:
    style_map: dict[str, str] = {}
    for part in (style_text or "").split(";"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = normalize(key).lower()
        value = normalize(value)
        if key and value:
            style_map[key] = value
    return style_map


def parse_highlight_room(onclick: str) -> str:
    raw = onclick or ""
    match = re.search(r"highlightRoom\(\s*'([^']+)'\s*(?:,|\))", raw)
    if match:
        return normalize(match.group(1))
    match = re.search(r'highlightRoom\(\s*"([^"]+)"\s*(?:,|\))', raw)
    return normalize(match.group(1)) if match else ""


def text_of(node: Tag | None) -> str:
    if node is None:
        return ""
    return normalize(node.get_text(" ", strip=True))


def detect_kind(cell: Tag) -> str:
    classes = set(cell.get("class") or [])
    name = normalize(text_of(cell.select_one(".cell-name"))).lower()
    target = parse_highlight_room(cell.get("onclick", "")).lower()
    text = f"{name} {target}"

    if any(k in text for k in ["玄關", "入口", "entry", "foyer"]):
        return "entry"
    if any(k in text for k in ["衛", "浴", "廁", "bath", "wc", "toilet"]) or "wet" in classes:
        return "bath"
    if any(k in text for k in ["廚", "kitchen"]):
        return "kitchen"
    if any(k in text for k in ["客廳", "起居", "living", "lounge"]):
        return "living"
    if any(k in text for k in ["餐廳", "dining"]):
        return "dining"
    if any(k in text for k in ["臥", "客房", "master", "guest", "bedroom", "flex"]):
        return "bedroom"
    if any(k in text for k in ["梯", "stair"]):
        return "stair"
    if "outdoor" in classes or any(k in text for k in ["陽台", "露台", "庭", "garage", "車庫", "戶外", "terrace", "balcony"]):
        return "outdoor"
    if classes & {"mdf", "core", "water", "emergency"} or any(
        k in text for k in ["mdf", "idf", "機櫃", "機房", "設備", "給水", "配電", "service", "storage"]
    ):
        return "service"
    return "other"


def default_door_mm(kind: str) -> int:
    if kind == "entry":
        return 1000
    if kind in {"bath", "service"}:
        return 800
    return 900


def default_window_mm(kind: str) -> int:
    mapping = {
        "living": 1800,
        "dining": 1500,
        "bedroom": 1200,
        "kitchen": 900,
        "bath": 600,
        "service": 600,
        "entry": 900,
        "stair": 600,
        "outdoor": 0,
        "other": 1000,
    }
    return mapping.get(kind, 1000)


def default_material(kind: str) -> str:
    mapping = {
        "entry": "tile",
        "living": "wood+paint",
        "dining": "tile+paint",
        "bedroom": "wood+paint",
        "kitchen": "tile+stainless",
        "bath": "tile+waterproof",
        "service": "service+utility",
        "stair": "concrete+paint",
        "outdoor": "concrete+drain",
        "other": "paint+default",
    }
    return mapping.get(kind, "paint+default")


def set_if_missing(node: Tag, attr: str, value: str) -> bool:
    if node.has_attr(attr):
        return False
    node[attr] = value
    return True


def set_or_keep_number(node: Tag, attr: str, value: float) -> bool:
    if parse_float(node.get(attr)) is not None:
        return False
    node[attr] = str(int(round(value)))
    return True


def row_height_mm(row_idx: int, row_cells: list[Tag]) -> int:
    """Guess a row's depth from the CSS classes on its cells.

    This is a lookup table, not a measurement: a bathroom comes out 1100mm deep
    because it is tagged ``wet``, not because anyone measured it.  Override real
    depths in ``inputs/dimensions.json`` rather than tuning these constants.
    """

    if not row_cells:
        return 1300
    classes: set[str] = set()
    for cell in row_cells:
        classes.update(cell.get("class") or [])
    if row_idx == 0 and "outdoor" in classes and len(row_cells) == 1:
        return 1200
    if "outdoor" in classes:
        return 1700
    if "wet" in classes:
        return 1100
    if classes & {"mdf", "core", "water", "emergency"}:
        return 1100
    return 1300


def annotate_floor(floor: Tag) -> dict[str, int]:
    counts = {
        "rows": 0,
        "cells": 0,
        "cell_geom_added": 0,
        "cell_opening_added": 0,
        "room_mapping_added": 0,
        "floor_geom_added": 0,
    }

    row_nodes = [r for r in floor.select(".plan-grid-visual > .plan-row")]
    if not row_nodes:
        return counts

    counts["rows"] = len(row_nodes)
    floor_width = parse_float(floor.get("data-floor-width-mm")) or float(DEFAULT_FLOOR_WIDTH_MM)
    y_cursor = 0.0
    room_to_slot: dict[str, str] = {}
    slot_to_geom: dict[str, dict[str, float]] = {}

    for row_idx, row in enumerate(row_nodes):
        row_cells = [c for c in row.find_all(class_="plan-cell", recursive=False) if isinstance(c, Tag)]
        if not row_cells:
            continue

        style_map = parse_inline_style(row.get("style", ""))
        weights = parse_grid_template_columns(style_map.get("grid-template-columns", ""))
        if not weights:
            weights = [1.0] * len(row_cells)
        if len(weights) < len(row_cells):
            weights.extend([weights[-1]] * (len(row_cells) - len(weights)))
        if len(weights) > len(row_cells):
            weights = weights[: len(row_cells)]
        total = sum(weights) or float(len(row_cells))

        row_h = parse_float(row.get("data-row-h-mm"))
        if row_h is None:
            row_h = float(row_height_mm(row_idx, row_cells))
            row["data-row-h-mm"] = str(int(round(row_h)))

        x_cursor = 0.0
        for col_idx, cell in enumerate(row_cells, start=1):
            counts["cells"] += 1
            w = floor_width * (weights[col_idx - 1] / total)
            h = row_h
            x = x_cursor
            y = y_cursor

            before = 0
            before += 1 if set_or_keep_number(cell, "data-x-mm", x) else 0
            before += 1 if set_or_keep_number(cell, "data-y-mm", y) else 0
            before += 1 if set_or_keep_number(cell, "data-w-mm", w) else 0
            before += 1 if set_or_keep_number(cell, "data-h-mm", h) else 0
            if before > 0:
                counts["cell_geom_added"] += 1

            kind = detect_kind(cell)
            opening_added = False
            if set_or_keep_number(cell, "data-door-mm", default_door_mm(kind)):
                opening_added = True
            if set_or_keep_number(cell, "data-window-mm", default_window_mm(kind)):
                opening_added = True
            if opening_added:
                counts["cell_opening_added"] += 1

            if kind == "entry":
                set_if_missing(cell, "data-entry", "true")
            set_if_missing(cell, "data-material", default_material(kind))

            slot_id = f"slot-{counts['cells']}"
            room_id = parse_highlight_room(cell.get("onclick", ""))
            if room_id and room_id not in room_to_slot:
                room_to_slot[room_id] = slot_id
            slot_to_geom[slot_id] = {"x_mm": x, "y_mm": y, "w_mm": w, "h_mm": h}
            x_cursor += w

        y_cursor += row_h

    floor_depth = parse_float(floor.get("data-floor-depth-mm")) or y_cursor
    if set_or_keep_number(floor, "data-floor-width-mm", floor_width):
        counts["floor_geom_added"] += 1
    if set_or_keep_number(floor, "data-floor-depth-mm", floor_depth):
        counts["floor_geom_added"] += 1
    if set_or_keep_number(floor, "data-north-deg", DEFAULT_NORTH_DEG):
        counts["floor_geom_added"] += 1
    if set_if_missing(floor, "data-geometry-source", "auto-grid-v1"):
        counts["floor_geom_added"] += 1

    room_nodes = [r for r in floor.select(".room")]
    for room in room_nodes:
        rid = normalize(room.get("id", ""))
        rid = rid.replace("room-", "", 1) if rid.startswith("room-") else rid
        if not rid:
            continue
        slot_id = room_to_slot.get(rid)
        if not slot_id:
            continue
        if set_if_missing(room, "data-target-cell", slot_id):
            counts["room_mapping_added"] += 1

        geom = slot_to_geom.get(slot_id)
        if not geom:
            continue
        set_or_keep_number(room, "data-x-mm", geom["x_mm"])
        set_or_keep_number(room, "data-y-mm", geom["y_mm"])
        set_or_keep_number(room, "data-w-mm", geom["w_mm"])
        set_or_keep_number(room, "data-h-mm", geom["h_mm"])

    return counts


def annotate_file(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(text, "html.parser")
    floors = [f for f in soup.select(".floor-plan") if isinstance(f, Tag)]
    summary = {
        "floors": 0,
        "rows": 0,
        "cells": 0,
        "cell_geom_added": 0,
        "cell_opening_added": 0,
        "room_mapping_added": 0,
        "floor_geom_added": 0,
    }

    for floor in floors:
        stats = annotate_floor(floor)
        if stats["rows"] <= 0:
            continue
        summary["floors"] += 1
        for key in ("rows", "cells", "cell_geom_added", "cell_opening_added", "room_mapping_added", "floor_geom_added"):
            summary[key] += stats[key]

    if summary["floors"] > 0:
        path.write_text(str(soup), encoding="utf-8")
    return summary


def should_process(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith("_tmp.html"):
        return False
    if name.startswith("storage"):
        return True
    return any(token in name for token in ["building", "view", "_tmp"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Annotate plan geometry data-* attributes in HTML files.")
    parser.add_argument(
        "--include-tmp",
        action="store_true",
        help="Also process *_tmp.html files (default: false).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = []
    for p in sorted(ROOT.glob(TARGET_GLOB)):
        if not p.is_file():
            continue
        if not should_process(p):
            if args.include_tmp and p.name.lower().endswith("_tmp.html"):
                files.append(p)
            continue
        files.append(p)
    if not files:
        print("No target HTML files found.")
        return

    total = {
        "files": 0,
        "floors": 0,
        "rows": 0,
        "cells": 0,
        "cell_geom_added": 0,
        "cell_opening_added": 0,
        "room_mapping_added": 0,
        "floor_geom_added": 0,
    }

    for path in files:
        stats = annotate_file(path)
        if stats["floors"] <= 0:
            print(f"Skip {path.name}: no floor-plan grid detected.")
            continue

        total["files"] += 1
        total["floors"] += stats["floors"]
        total["rows"] += stats["rows"]
        total["cells"] += stats["cells"]
        total["cell_geom_added"] += stats["cell_geom_added"]
        total["cell_opening_added"] += stats["cell_opening_added"]
        total["room_mapping_added"] += stats["room_mapping_added"]
        total["floor_geom_added"] += stats["floor_geom_added"]
        print(
            f"Updated {path.name}: floors={stats['floors']} cells={stats['cells']} "
            f"geom+={stats['cell_geom_added']} openings+={stats['cell_opening_added']}"
        )

    print("----")
    print(
        "Total: files={files} floors={floors} rows={rows} cells={cells} "
        "cell_geom+={cell_geom_added} cell_openings+={cell_opening_added} "
        "room_map+={room_mapping_added} floor_geom+={floor_geom_added}".format(**total)
    )


if __name__ == "__main__":
    main()

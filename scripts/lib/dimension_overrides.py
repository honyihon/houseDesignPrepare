#!/usr/bin/env python3
"""Measured-dimension override layer for the room program.

Why this exists
---------------
``scripts/annotate_html_geometry.py`` manufactures every ``data-*-mm`` value in
the HTML from CSS classes: row depths come from a constant lookup table, floor
width is a hardcoded ``DEFAULT_FLOOR_WIDTH_MM`` split by ``grid-template-columns``
weights, and ``north_deg`` is always 0.  Those numbers are plausible-looking
guesses, not survey data, yet everything downstream (floor area, daylight
factor, egress proxy, the SVG drawings and the print bundle) is computed from
them.

This module lets real measurements be layered on top without touching the HTML.
``inputs/dimensions.json`` supplies whatever is known; anything absent falls
back to the auto-derived value.  Every cell and floor comes out carrying a
``geometry_provenance`` marker so consumers can tell survey data from a guess:

``measured``  taken with a tape measure / from CAD
``declared``  derived from the size text already written in the HTML
``auto``      auto-grid heuristic, i.e. a guess

Deliberately JSON, not YAML: ``pyyaml`` is not a declared dependency of this
project (``scripts/evaluate_expert_gates.py`` carries a hand-rolled fallback
parser precisely because of that), and a geometry source of truth should not
depend on an optional import.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OVERRIDE_PATH = ROOT / "inputs" / "dimensions.json"

SCHEMA_VERSION = "house-dimensions-override-v1"

PROVENANCE_AUTO = "auto"
PROVENANCE_DECLARED = "declared"
PROVENANCE_MEASURED = "measured"
PROVENANCE_LEVELS = (PROVENANCE_AUTO, PROVENANCE_DECLARED, PROVENANCE_MEASURED)

CELL_GEOMETRY_KEYS = ("x_mm", "y_mm", "w_mm", "h_mm")
FLOOR_GEOMETRY_KEYS = ("width_mm", "depth_mm", "north_deg")

# The auto-grid values are copied aside before any override lands on top, so
# that anything reading the program back (the seed script, the consistency
# checks, the 3D viewer's "what was guessed?" mode) can still see what the
# heuristic produced.  Without this the seed script re-reads its own output as
# if it were the heuristic baseline and drifts a little further every run.
AUTO_GEOMETRY_KEY = "geometry_auto_mm"

PING_TO_SQM = 3.305785


def cell_key(cell: dict[str, Any]) -> str:
    """Stable, human-writable key for a plan cell.

    Uses the room binding id (the same token that appears in the HTML as
    ``highlightRoom('garage', this)``) so the override file can be edited by
    hand against the page the user already looks at.  Falls back to the cell
    order for the rare cell with no room binding.
    """

    local_id = str(cell.get("target_room_local_id") or "").strip()
    if local_id:
        return local_id
    return f"cell-{cell.get('order')}"


def auto_geometry(node: dict[str, Any]) -> dict[str, Any]:
    """The auto-grid geometry of a cell or floor, before any override.

    Falls back to ``geometry_mm`` for programs built before the snapshot
    existed; on a freshly built program the two are identical for every entry
    that has no override.
    """

    snapshot = node.get(AUTO_GEOMETRY_KEY)
    if isinstance(snapshot, dict) and snapshot:
        return snapshot
    geo = node.get("geometry_mm")
    return geo if isinstance(geo, dict) else {}


def _as_float(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_provenance(value: Any, default: str = PROVENANCE_AUTO) -> str:
    text = str(value or "").strip().lower()
    return text if text in PROVENANCE_LEVELS else default


def _resolve_provenance(override: dict[str, Any], touched: bool) -> str:
    """An explicit ``_provenance`` always wins.

    The seed script echoes the auto-derived floor sizes back into the override
    file so they are easy to edit; those entries are labelled ``auto`` on
    purpose and must not be promoted just because a value is present.  Only an
    unlabelled entry that actually supplied numbers is assumed to be measured.
    """

    if "_provenance" in override:
        return _normalize_provenance(override["_provenance"])
    return PROVENANCE_MEASURED if touched else PROVENANCE_AUTO


class Overrides:
    """Read-only accessor over ``inputs/dimensions.json``."""

    def __init__(self, data: dict[str, Any], path: Path, loaded: bool) -> None:
        self.data = data if isinstance(data, dict) else {}
        self.path = path
        self.loaded = loaded

    # -- lookups -----------------------------------------------------------
    def site(self) -> dict[str, Any]:
        site = self.data.get("site")
        return site if isinstance(site, dict) else {}

    def site_placement(self, building_id: str) -> dict[str, Any]:
        entry = self.site().get(building_id)
        return entry if isinstance(entry, dict) else {}

    def _floor_node(self, building_id: str, floor_id: str) -> dict[str, Any]:
        buildings = self.data.get("buildings")
        if not isinstance(buildings, dict):
            return {}
        building = buildings.get(building_id)
        if not isinstance(building, dict):
            return {}
        floors = building.get("floors")
        if not isinstance(floors, dict):
            return {}
        floor = floors.get(floor_id)
        return floor if isinstance(floor, dict) else {}

    def floor(self, building_id: str, floor_id: str) -> dict[str, Any]:
        return self._floor_node(building_id, floor_id)

    def cell(self, building_id: str, floor_id: str, key: str) -> dict[str, Any]:
        cells = self._floor_node(building_id, floor_id).get("cells")
        if not isinstance(cells, dict):
            return {}
        entry = cells.get(key)
        return entry if isinstance(entry, dict) else {}

    def default_storey_height_mm(self) -> float | None:
        return _as_float(self.data.get("default_storey_height_mm"))


def load_overrides(path: Path | None = None) -> Overrides:
    """Load the override file.  A missing file is normal and never an error."""

    target = Path(path) if path else DEFAULT_OVERRIDE_PATH
    if not target.exists():
        return Overrides({}, target, loaded=False)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - operator error
        raise SystemExit(f"Failed to read dimension overrides {target}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Dimension overrides must be a JSON object: {target}")
    schema = str(data.get("schema") or data.get("schema_version") or "")
    if schema and schema != SCHEMA_VERSION:
        raise SystemExit(
            f"Unsupported dimension override schema {schema!r} in {target}; expected {SCHEMA_VERSION!r}"
        )
    return Overrides(data, target, loaded=True)


def iter_floor_records(program: dict[str, Any]):
    """Yield ``(building, floor)`` for real floors only.

    Section records (``record_type == 'section'``) and the storage building
    carry no plan cells and no geometry; skipping them here keeps every caller
    from having to rediscover that.
    """

    for building in program.get("buildings", []):
        for floor in building.get("floors", []):
            if floor.get("record_type") != "floor":
                continue
            yield building, floor


def apply_to_room_program(
    program: dict[str, Any],
    overrides: Overrides,
    default_storey_height_mm: float = 3000.0,
) -> dict[str, Any]:
    """Layer overrides onto ``program`` in place and stamp provenance.

    Returns a summary dict suitable for embedding in the program document and
    for downstream honesty reporting (see ``scripts/export_top1_svgs.py``).
    """

    storey_default = overrides.default_storey_height_mm() or default_storey_height_mm

    counts = {level: 0 for level in PROVENANCE_LEVELS}
    floor_counts = {level: 0 for level in PROVENANCE_LEVELS}
    applied_cells = 0
    applied_floors = 0

    for building, floor in iter_floor_records(program):
        building_id = building.get("id", "")
        floor_id = floor.get("id", "")

        floor_ov = overrides.floor(building_id, floor_id)
        floor_geo = floor.setdefault("geometry_mm", {})
        floor.setdefault(AUTO_GEOMETRY_KEY, dict(floor_geo))
        floor_touched = False
        for key in FLOOR_GEOMETRY_KEYS:
            value = _as_float(floor_ov.get(key))
            if value is not None:
                floor_geo[key] = round(value, 3)
                floor_touched = True

        storey = _as_float(floor_ov.get("storey_height_mm")) or storey_default
        floor["storey_height_mm"] = round(storey, 3)

        floor_prov = _resolve_provenance(floor_ov, floor_touched)
        floor["geometry_provenance"] = floor_prov
        floor_counts[floor_prov] += 1
        if floor_touched:
            applied_floors += 1

        for cell in floor.get("plan_cells", []):
            key = cell_key(cell)
            cell["override_key"] = key
            cell_ov = overrides.cell(building_id, floor_id, key)
            geo = cell.setdefault("geometry_mm", {})
            cell.setdefault(AUTO_GEOMETRY_KEY, dict(geo))
            touched = False
            for gk in CELL_GEOMETRY_KEYS:
                value = _as_float(cell_ov.get(gk))
                if value is not None:
                    geo[gk] = round(value, 3)
                    touched = True

            prov = _resolve_provenance(cell_ov, touched)
            cell["geometry_provenance"] = prov
            counts[prov] += 1
            if touched:
                applied_cells += 1

    total = sum(counts.values())
    summary = {
        "schema": SCHEMA_VERSION,
        "source": str(overrides.path.relative_to(ROOT)) if _under_root(overrides.path) else str(overrides.path),
        "loaded": overrides.loaded,
        "default_storey_height_mm": round(storey_default, 3),
        "cells": {
            **counts,
            "total": total,
            "overridden": applied_cells,
            "auto_pct": round(100.0 * counts[PROVENANCE_AUTO] / total, 1) if total else 0.0,
        },
        "floors": {**floor_counts, "total": sum(floor_counts.values()), "overridden": applied_floors},
        "site": {
            "declared": bool(overrides.site()),
            "provenance": _normalize_provenance(overrides.site().get("_provenance"), "assumed")
            if overrides.site()
            else "assumed",
        },
    }
    program["dimension_overrides"] = summary
    return summary


def summarize_provenance(program: dict[str, Any]) -> dict[str, Any]:
    """Recount provenance from an already-built program document."""

    existing = program.get("dimension_overrides")
    if isinstance(existing, dict) and isinstance(existing.get("cells"), dict):
        return existing

    counts = {level: 0 for level in PROVENANCE_LEVELS}
    for _, floor in iter_floor_records(program):
        for cell in floor.get("plan_cells", []):
            counts[_normalize_provenance(cell.get("geometry_provenance"))] += 1
    total = sum(counts.values())
    return {
        "schema": SCHEMA_VERSION,
        "loaded": False,
        "cells": {
            **counts,
            "total": total,
            "overridden": counts[PROVENANCE_DECLARED] + counts[PROVENANCE_MEASURED],
            "auto_pct": round(100.0 * counts[PROVENANCE_AUTO] / total, 1) if total else 0.0,
        },
    }


def is_precise(summary: dict[str, Any]) -> bool:
    """True only when no cell geometry is still an auto-grid guess."""

    cells = summary.get("cells") if isinstance(summary, dict) else None
    if not isinstance(cells, dict) or not cells.get("total"):
        return False
    return int(cells.get(PROVENANCE_AUTO, 0)) == 0


def _under_root(path: Path) -> bool:
    try:
        path.relative_to(ROOT)
    except ValueError:
        return False
    return True

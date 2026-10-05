"""Load the editable furniture draft used by the historical HTML 3D viewer.

The source HTML contains room names, a few explicit furniture call-outs and a
large amount of equipment intent, but it does not contain trustworthy furniture
coordinates.  This module keeps those two facts separate: catalogue dimensions
stay at real-world scale while each room assignment records whether it came
from explicit HTML copy or from a room-use inference.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from house_design.contracts import ContractError
from house_design.physical_items import PHYSICAL_ITEMS_PATH, load_physical_items

SCHEMA = "house-furniture-layout-v1"
ALLOWED_BASIS = {"html-explicit", "html-mixed", "room-use-inference"}
HEX_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")


class FurnitureLayoutError(ValueError):
    """Raised when an editable furniture layout would render ambiguously."""


def _mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FurnitureLayoutError(f"{context} must be an object")
    return value


def _list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise FurnitureLayoutError(f"{context} must be an array")
    return value


def _number(value: Any, context: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FurnitureLayoutError(f"{context} must be a number")
    result = float(value)
    if positive and result <= 0:
        raise FurnitureLayoutError(f"{context} must be greater than zero")
    return result


def _known_cells(buildings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    cells: dict[str, dict[str, Any]] = {}
    for building in buildings:
        for floor in building.get("floors", []):
            for cell in floor.get("cells", []):
                cell_id = str(cell.get("id") or "")
                if not cell_id or cell_id in cells:
                    raise FurnitureLayoutError(f"duplicate or blank model cell id: {cell_id!r}")
                cell["furniture"] = []
                cells[cell_id] = cell
    return cells


def _catalogue(
    raw: dict[str, Any], physical_items: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    catalogue = _mapping(raw.get("catalog"), "catalog")
    out: dict[str, dict[str, Any]] = {}
    for catalog_id, value in catalogue.items():
        context = f"catalog.{catalog_id}"
        item = _mapping(value, context)
        label = str(item.get("label") or "").strip()
        category = str(item.get("category") or "").strip()
        colour = str(item.get("color") or "").strip()
        if not label or not category:
            raise FurnitureLayoutError(f"{context} needs label and category")
        if not HEX_COLOUR.fullmatch(colour):
            raise FurnitureLayoutError(f"{context}.color must be #RRGGBB")

        physical_item_id = str(item.get("physical_item_id") or "").strip()
        linked: dict[str, Any] | None = None
        if physical_item_id:
            linked = physical_items.get(physical_item_id)
            if linked is None:
                raise FurnitureLayoutError(
                    f"{context}.physical_item_id references unknown item {physical_item_id!r}"
                )
            duplicate_dimensions = [key for key in ("width_mm", "depth_mm", "height_mm") if key in item]
            if duplicate_dimensions:
                raise FurnitureLayoutError(
                    f"{context} links a physical item and must not duplicate dimensions: "
                    f"{', '.join(duplicate_dimensions)}"
                )
            dimensions = linked["active_dimensions"]
        else:
            dimensions = {
                "width_mm": _number(item.get("width_mm"), f"{context}.width_mm", positive=True),
                "depth_mm": _number(item.get("depth_mm"), f"{context}.depth_mm", positive=True),
                "height_mm": _number(item.get("height_mm"), f"{context}.height_mm", positive=True),
            }

        resolved = {
            "label": label,
            "category": category,
            "shape": str(item.get("shape") or "box").strip() or "box",
            "color": colour.lower(),
            **dimensions,
        }
        if linked is not None:
            resolved.update(
                {
                    "physical_item_id": physical_item_id,
                    "physical_item_label": linked["label"],
                    "physical_dimension_source": linked["active_dimension_source"],
                    "physical_measurement_state": (
                        "measured" if linked["active_dimension_source"] == "measured" else "pending"
                    ),
                    "physical_dimension_note": linked["source"]["note"],
                }
            )
        out[str(catalog_id)] = resolved
    if not out:
        raise FurnitureLayoutError("catalog must not be empty")
    return out


def _expand_item(
    raw_item: Any,
    *,
    context: str,
    room_id: str,
    ordinal: int,
    catalogue: dict[str, dict[str, Any]],
    basis: str,
    evidence: list[str],
) -> dict[str, Any]:
    spec = _mapping(raw_item, context)
    catalog_id = str(spec.get("catalog") or "")
    if catalog_id not in catalogue:
        raise FurnitureLayoutError(f"{context}.catalog references unknown item {catalog_id!r}")
    position = _list(spec.get("position"), f"{context}.position")
    if len(position) != 2:
        raise FurnitureLayoutError(f"{context}.position must contain x and y ratios")
    x_ratio = _number(position[0], f"{context}.position[0]")
    y_ratio = _number(position[1], f"{context}.position[1]")
    if not (0 <= x_ratio <= 1 and 0 <= y_ratio <= 1):
        raise FurnitureLayoutError(f"{context}.position ratios must be between 0 and 1")

    item = copy.deepcopy(catalogue[catalog_id])
    if item.get("physical_item_id") and any(
        dimension in spec for dimension in ("width_mm", "depth_mm", "height_mm")
    ):
        raise FurnitureLayoutError(
            f"{context} cannot override dimensions linked to physical item {item['physical_item_id']!r}"
        )
    for dimension in ("width_mm", "depth_mm", "height_mm"):
        if dimension in spec:
            item[dimension] = _number(spec[dimension], f"{context}.{dimension}", positive=True)
    local_id = str(spec.get("id") or f"{catalog_id}-{ordinal}").strip()
    if not local_id:
        raise FurnitureLayoutError(f"{context}.id must not be blank")
    item.update(
        {
            "id": f"{room_id}:furniture:{local_id}",
            "catalog_id": catalog_id,
            "label": str(spec.get("label") or item["label"]).strip(),
            "x_ratio": round(x_ratio, 4),
            "y_ratio": round(y_ratio, 4),
            "rotation_deg": round(_number(spec.get("rotation_deg", 0), f"{context}.rotation_deg"), 1),
            "basis": basis,
            "evidence": evidence,
            "note": str(spec.get("note") or "").strip(),
        }
    )
    return item


def attach_furniture_layout(
    buildings: list[dict[str, Any]],
    path: Path,
    physical_items_path: Path = PHYSICAL_ITEMS_PATH,
) -> dict[str, Any]:
    """Attach resolved furniture lists to cells and return display metadata."""

    cells = _known_cells(buildings)
    if not path.is_file():
        return {
            "available": False,
            "status": "missing",
            "note": "家具配置檔不存在。",
            "rooms": 0,
            "items": 0,
            "basis_counts": {basis: 0 for basis in sorted(ALLOWED_BASIS)},
            "categories": {},
        }

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FurnitureLayoutError(f"cannot read furniture layout {path}: {exc}") from exc
    root = _mapping(raw, "furniture layout")
    if root.get("schema") != SCHEMA:
        raise FurnitureLayoutError(f"furniture layout schema must be {SCHEMA}")

    try:
        physical_register = load_physical_items(physical_items_path)
    except ContractError as exc:
        raise FurnitureLayoutError(str(exc)) from exc
    catalogue = _catalogue(root, physical_register["by_id"])
    profiles = _mapping(root.get("profiles"), "profiles")
    rooms = _mapping(root.get("rooms"), "rooms")
    category_labels = {
        str(key): str(value)
        for key, value in _mapping(root.get("category_labels", {}), "category_labels").items()
    }
    basis_counts = {basis: 0 for basis in sorted(ALLOWED_BASIS)}
    categories: dict[str, dict[str, str]] = {}
    used_ids: set[str] = set()
    used_physical_item_ids: set[str] = set()
    total_items = 0

    for room_id, raw_assignment in rooms.items():
        context = f"rooms.{room_id}"
        if room_id not in cells:
            raise FurnitureLayoutError(f"{context} does not match any HTML model cell")
        assignment = _mapping(raw_assignment, context)
        basis = str(assignment.get("basis") or "")
        if basis not in ALLOWED_BASIS:
            raise FurnitureLayoutError(f"{context}.basis must be one of {sorted(ALLOWED_BASIS)}")
        evidence = [str(value).strip() for value in _list(assignment.get("evidence"), f"{context}.evidence")]
        evidence = [value for value in evidence if value]
        if not evidence:
            raise FurnitureLayoutError(f"{context}.evidence must not be empty")
        profile_id = str(assignment.get("profile") or "")
        if profile_id not in profiles:
            raise FurnitureLayoutError(f"{context}.profile references unknown profile {profile_id!r}")
        raw_items = copy.deepcopy(_list(profiles[profile_id], f"profiles.{profile_id}"))
        raw_items.extend(_list(assignment.get("items", []), f"{context}.items"))
        if not raw_items:
            raise FurnitureLayoutError(f"{context} resolves to no furniture")

        resolved: list[dict[str, Any]] = []
        for ordinal, raw_item in enumerate(raw_items, 1):
            item = _expand_item(
                raw_item,
                context=f"{context}.items[{ordinal - 1}]",
                room_id=room_id,
                ordinal=ordinal,
                catalogue=catalogue,
                basis=basis,
                evidence=evidence,
            )
            if item["id"] in used_ids:
                raise FurnitureLayoutError(f"duplicate furniture id: {item['id']}")
            used_ids.add(item["id"])
            if item.get("physical_item_id"):
                used_physical_item_ids.add(item["physical_item_id"])
            item["room_note"] = str(assignment.get("note") or "").strip()
            resolved.append(item)
            total_items += 1
            basis_counts[basis] += 1
            categories.setdefault(
                item["category"],
                {
                    "label": category_labels.get(item["category"], item["category"]),
                    "color": item["color"],
                },
            )
        cells[room_id]["furniture"] = resolved

    linked_physical_items = [physical_register["by_id"][item_id] for item_id in sorted(used_physical_item_ids)]
    return {
        "available": True,
        "schema": SCHEMA,
        "status": str(root.get("status") or "historical-space-planning-draft"),
        "note": str(root.get("note") or "").strip(),
        "rooms": len(rooms),
        "items": total_items,
        "basis_counts": basis_counts,
        "categories": categories,
        "physical_items": {
            "source": str(physical_items_path),
            "registered": physical_register["summary"]["total"],
            "linked": len(linked_physical_items),
            "measured": sum(
                1 for item in linked_physical_items if item["active_dimension_source"] == "measured"
            ),
            "pending_measurement": sum(
                1 for item in linked_physical_items if item["active_dimension_source"] == "planning"
            ),
        },
    }

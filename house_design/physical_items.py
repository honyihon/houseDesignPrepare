from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import Any

from house_design.contracts import ROOT, ContractError, read_json, utc_now, write_json

PHYSICAL_ITEMS_PATH = ROOT / "inputs/physical-items.json"
PHYSICAL_ITEMS_SCHEMA = "house-physical-items-v1"
DIMENSION_KEYS = ("width_mm", "depth_mm", "height_mm")


def _is_positive_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and value > 0
    )


def _validate_dimensions(value: Any, field: str, *, optional: bool = False) -> list[dict[str, str]]:
    if value is None and optional:
        return []
    if not isinstance(value, dict):
        return [{"field": field, "message": "dimensions must be an object"}]
    issues: list[dict[str, str]] = []
    for key in DIMENSION_KEYS:
        if not _is_positive_number(value.get(key)):
            issues.append({"field": f"{field}.{key}", "message": "a positive millimetre value is required"})
    unknown = sorted(set(value) - set(DIMENSION_KEYS))
    if unknown:
        issues.append({"field": field, "message": f"unknown dimension fields: {', '.join(unknown)}"})
    return issues


def validate_physical_items(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Validate the editable owner inventory without treating estimates as measurements."""

    issues: list[dict[str, str]] = []
    if payload.get("schema") != PHYSICAL_ITEMS_SCHEMA:
        issues.append({"field": "schema", "message": f"schema must be {PHYSICAL_ITEMS_SCHEMA}"})
    if payload.get("units") != "mm":
        issues.append({"field": "units", "message": "units must be mm"})
    items = payload.get("items")
    if not isinstance(items, list):
        return [*issues, {"field": "items", "message": "items must be an array"}]

    seen: set[str] = set()
    for index, item in enumerate(items):
        field = f"items[{index}]"
        if not isinstance(item, dict):
            issues.append({"field": field, "message": "item must be an object"})
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            issues.append({"field": f"{field}.id", "message": "id is required"})
        elif item_id in seen:
            issues.append({"field": f"{field}.id", "message": "id must be unique"})
        seen.add(item_id)
        if not str(item.get("label") or "").strip():
            issues.append({"field": f"{field}.label", "message": "label is required"})
        if not str(item.get("category") or "").strip():
            issues.append({"field": f"{field}.category", "message": "category is required"})
        quantity = item.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            issues.append({"field": f"{field}.quantity", "message": "quantity must be a positive integer"})

        location = item.get("location")
        if not isinstance(location, dict):
            issues.append({"field": f"{field}.location", "message": "location must be an object"})
        else:
            for key in ("building_id", "floor_id", "requirement_id"):
                if not str(location.get(key) or "").strip():
                    issues.append({"field": f"{field}.location.{key}", "message": f"{key} is required"})

        issues.extend(_validate_dimensions(item.get("planning_dimensions"), f"{field}.planning_dimensions"))
        measurements = item.get("measurements")
        if not isinstance(measurements, list):
            issues.append({"field": f"{field}.measurements", "message": "measurements must be an array"})
        else:
            for measurement_index, measurement in enumerate(measurements):
                measurement_field = f"{field}.measurements[{measurement_index}]"
                if not isinstance(measurement, dict):
                    issues.append({"field": measurement_field, "message": "measurement must be an object"})
                    continue
                if measurement.get("sequence") != measurement_index + 1:
                    issues.append(
                        {
                            "field": f"{measurement_field}.sequence",
                            "message": "sequence must be contiguous and start at 1",
                        }
                    )
                issues.extend(
                    _validate_dimensions(measurement.get("dimensions"), f"{measurement_field}.dimensions")
                )
                for key in ("measured_by", "measured_at", "method"):
                    if not str(measurement.get(key) or "").strip():
                        issues.append(
                            {"field": f"{measurement_field}.{key}", "message": f"{key} is required"}
                        )

        source = item.get("source")
        if not isinstance(source, dict) or not str(source.get("type") or "").strip() or not str(
            source.get("note") or ""
        ).strip():
            issues.append({"field": f"{field}.source", "message": "source type and note are required"})

        transport = item.get("transport")
        if transport is not None:
            if not isinstance(transport, dict):
                issues.append({"field": f"{field}.transport", "message": "transport must be an object"})
            else:
                removable = transport.get("carrying_poles_removable")
                if removable is not None and not isinstance(removable, bool):
                    issues.append(
                        {
                            "field": f"{field}.transport.carrying_poles_removable",
                            "message": "carrying_poles_removable must be true, false or null",
                        }
                    )
                issues.extend(
                    _validate_dimensions(
                        transport.get("assembled_dimensions"),
                        f"{field}.transport.assembled_dimensions",
                        optional=True,
                    )
                )
                clearance = transport.get("door_clear_target_mm")
                if clearance is not None and not _is_positive_number(clearance):
                    issues.append(
                        {
                            "field": f"{field}.transport.door_clear_target_mm",
                            "message": "door_clear_target_mm must be a positive millimetre value or null",
                        }
                    )
    return issues


def active_dimensions(item: dict[str, Any]) -> tuple[dict[str, float], str]:
    """Return one complete dimension set; never blend estimated and measured axes."""

    measurements = item.get("measurements") or []
    source = "measured" if measurements else "planning"
    values = measurements[-1]["dimensions"] if measurements else item["planning_dimensions"]
    return ({key: float(values[key]) for key in DIMENSION_KEYS}, source)


def record_physical_item_measurement(
    *,
    item_id: str,
    width_mm: float,
    depth_mm: float,
    height_mm: float,
    measured_by: str,
    method: str,
    measured_at: str | None = None,
    note: str = "",
    path: Path = PHYSICAL_ITEMS_PATH,
) -> dict[str, Any]:
    """Append one complete measured envelope and make it the active dimension set."""

    item_id = item_id.strip()
    dimensions = {"width_mm": width_mm, "depth_mm": depth_mm, "height_mm": height_mm}
    dimension_issues = _validate_dimensions(dimensions, "dimensions")
    measured_by = measured_by.strip()
    method = method.strip()
    measured_at = (measured_at or utc_now()).strip()
    if dimension_issues:
        raise ContractError(f"Invalid physical item dimensions: {dimension_issues}")
    if not item_id or not measured_by or not method or not measured_at:
        raise ContractError("item id, measured_by, measured_at and method must be non-empty")

    payload = read_json(path)
    existing_issues = validate_physical_items(payload)
    if existing_issues:
        raise ContractError(f"Cannot update an invalid physical item register: {existing_issues}")
    item = next((value for value in payload["items"] if value.get("id") == item_id), None)
    if item is None:
        raise ContractError(f"Unknown physical item id: {item_id}")
    measurement = {
        "sequence": len(item["measurements"]) + 1,
        "dimensions": dimensions,
        "measured_by": measured_by,
        "measured_at": measured_at,
        "method": method,
        "note": note.strip(),
    }
    item["measurements"].append(measurement)
    payload["updated_at"] = utc_now()
    updated_issues = validate_physical_items(payload)
    if updated_issues:
        raise ContractError(f"Measurement would make physical item register invalid: {updated_issues}")
    write_json(path, payload)
    return {
        "schema": "house-physical-item-measurement-result-v1",
        "item_id": item_id,
        "measurement_sequence": measurement["sequence"],
        "active_dimensions": dimensions,
        "path": str(path),
    }


def load_physical_items(path: Path = PHYSICAL_ITEMS_PATH) -> dict[str, Any]:
    payload = read_json(path)
    issues = validate_physical_items(payload)
    if issues:
        raise ContractError(f"Invalid physical item register {path}: {issues}")

    resolved: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for raw in payload["items"]:
        item = deepcopy(raw)
        dimensions, source = active_dimensions(item)
        item["active_dimensions"] = dimensions
        item["active_dimension_source"] = source
        resolved.append(item)
        by_id[item["id"]] = item
    measured = sum(1 for item in resolved if item["active_dimension_source"] == "measured")
    return {
        "schema": PHYSICAL_ITEMS_SCHEMA,
        "path": str(path),
        "items": resolved,
        "by_id": by_id,
        "summary": {
            "total": len(resolved),
            "measured": measured,
            "pending_measurement": len(resolved) - measured,
        },
    }

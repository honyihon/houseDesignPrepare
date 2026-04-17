#!/usr/bin/env python3
"""Build a unified room-program JSON from structured building layout documents."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.standards import defaults_summary_line, load_residential_defaults  # noqa: E402

STRUCTURED_DIR = ROOT / "structured"
OUTPUT_FILE = STRUCTURED_DIR / "room_program.json"
SCHEMA_VERSION = "room-program-v2"
RESIDENTIAL_DEFAULTS = load_residential_defaults()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def strip_leading_emoji(text: str) -> str:
    text = normalize_whitespace(text)
    return re.sub(r"^[\W_]*", "", text, flags=re.UNICODE).strip()


def building_id_from_source(source_file: str) -> str:
    lower = source_file.lower()
    if lower.startswith("abuilding"):
        return "A"
    if lower.startswith("bbuilding"):
        return "B"
    if lower.startswith("cbuilding"):
        return "C"
    if "storage" in lower:
        return "STORAGE"
    return Path(source_file).stem.upper()


def parse_area_metrics(area_text: str) -> dict[str, Any]:
    raw = normalize_whitespace(area_text)
    result: dict[str, Any] = {
        "raw": raw,
        "ping_values": [],
        "sqm_from_ping_values": [],
        "dimension_m": None,
        "dimension_sqm": None,
    }
    if not raw:
        return result

    ping_values = [float(v) for v in re.findall(r"(\d+(?:\.\d+)?)\s*坪", raw)]
    if ping_values:
        result["ping_values"] = ping_values
        result["sqm_from_ping_values"] = [round(v * 3.305785, 3) for v in ping_values]

    dim_match = re.search(r"(\d+(?:\.\d+)?)\s*m\s*[x×]\s*(\d+(?:\.\d+)?)\s*m", raw, re.IGNORECASE)
    if dim_match:
        w = float(dim_match.group(1))
        d = float(dim_match.group(2))
        result["dimension_m"] = {"width_m": w, "depth_m": d}
        result["dimension_sqm"] = round(w * d, 3)

    return result


def normalize_room_tags(tags: list[Any]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for tag in tags:
        if not isinstance(tag, dict):
            text = normalize_whitespace(str(tag))
            if text:
                normalized.append({"title": "", "content": text})
            continue
        title = normalize_whitespace(str(tag.get("title", "")))
        content = normalize_whitespace(str(tag.get("content", "")))
        if title or content:
            normalized.append({"title": title, "content": content})
    return normalized


def compose_room_notes(details: list[str], tags: list[dict[str, str]]) -> dict[str, Any]:
    notes_raw = {
        "details": details,
        "tags": tags,
    }

    flattened: list[str] = []
    for detail in details:
        text = normalize_whitespace(detail)
        if text and text not in flattened:
            flattened.append(text)

    for tag in tags:
        title = normalize_whitespace(tag.get("title", ""))
        content = normalize_whitespace(tag.get("content", ""))
        if title and content:
            text = f"{title}: {content}"
        else:
            text = content or title
        if text and text not in flattened:
            flattened.append(text)

    return {
        "notes_raw": notes_raw,
        "notes_normalized": flattened,
        "notes_rendered": flattened[:3],
    }


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = normalize_whitespace(str(value)).lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def normalize_mm_map(raw: Any, keys: list[str]) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, float] = {}
    for key in keys:
        value = to_optional_float(raw.get(key))
        if value is not None:
            result[key] = round(value, 3)
    return result


def rows_to_table_objects(headers: list[str], rows: list[list[str]]) -> list[dict[str, Any]]:
    if not headers:
        return [{"row": row} for row in rows]
    objects: list[dict[str, Any]] = []
    for row in rows:
        if len(row) == len(headers):
            objects.append(dict(zip(headers, row)))
        else:
            objects.append({"row": row})
    return objects


def map_tab_label(tabs: list[dict[str, Any]], floor_id: str) -> str:
    for tab in tabs:
        if tab.get("target_floor_id") == floor_id:
            return tab.get("label", "")
    return ""


def fallback_room_id(room: dict[str, Any], room_order: int) -> str:
    rid = normalize_whitespace(room.get("id", ""))
    if rid:
        return rid
    return f"room_{room_order}"


def transform_floor(
    building_id: str,
    floor: dict[str, Any],
    tabs: list[dict[str, Any]],
) -> dict[str, Any]:
    floor_id = floor.get("id") or f"floor-{floor.get('order', 0)}"
    tab_label = map_tab_label(tabs, floor_id)
    floor_geometry_mm = normalize_mm_map(
        floor.get("geometry_mm", {}),
        ["width_mm", "depth_mm", "north_deg"],
    )

    room_map: dict[str, dict[str, Any]] = {}
    normalized_rooms: list[dict[str, Any]] = []
    for room in floor.get("rooms", []):
        room_order = room.get("order", len(normalized_rooms) + 1)
        local_id = fallback_room_id(room, room_order)
        room_uid = f"{building_id}:{floor_id}:{local_id}"
        area_text = normalize_whitespace(room.get("area", ""))
        area_metrics = parse_area_metrics(area_text)
        raw_details = room.get("details", [])
        if not isinstance(raw_details, list):
            raw_details = [raw_details]
        details = [normalize_whitespace(str(d)) for d in raw_details if normalize_whitespace(str(d))]

        raw_tags = room.get("tags", [])
        if not isinstance(raw_tags, list):
            raw_tags = [raw_tags]
        tags = normalize_room_tags(raw_tags)
        notes_payload = compose_room_notes(details, tags)
        room_geometry_mm = normalize_mm_map(
            room.get("geometry_mm", {}),
            ["x_mm", "y_mm", "w_mm", "h_mm"],
        )
        normalized = {
            "uid": room_uid,
            "local_id": local_id,
            "order": room_order,
            "name": normalize_whitespace(room.get("name", "")),
            "area_text": area_text,
            "area_metrics": area_metrics,
            "details": details,
            "tags": tags,
            "notes_raw": notes_payload["notes_raw"],
            "notes_normalized": notes_payload["notes_normalized"],
            "notes_rendered": notes_payload["notes_rendered"],
            "defaults_applied": {
                "standard_profile": RESIDENTIAL_DEFAULTS.get("profile", ""),
                "standard_schema": RESIDENTIAL_DEFAULTS.get("schema_version", ""),
                "used_default_area_assumption": not bool(area_metrics.get("dimension_m") or area_metrics.get("ping_values")),
            },
            "classes": room.get("classes", []),
            "geometry_mm": room_geometry_mm,
            "target_cell_id": normalize_whitespace(room.get("target_cell_id", "")),
        }
        normalized_rooms.append(normalized)
        room_map[local_id] = normalized

    normalized_cells: list[dict[str, Any]] = []
    for cell in floor.get("plan_cells", []):
        target_local_id = normalize_whitespace(cell.get("target_room_id", ""))
        target_uid = room_map[target_local_id]["uid"] if target_local_id in room_map else ""
        row_template = cell.get("row_template_columns", [])
        if not isinstance(row_template, list):
            row_template = []
        layout = {
            "row_order": to_int(cell.get("row_order"), 0),
            "col_order": to_int(cell.get("col_order"), 0),
            "col_weight": round(max(0.1, to_float(cell.get("col_weight"), 1.0)), 3),
            "row_template_columns": [round(max(0.1, to_float(v, 1.0)), 3) for v in row_template],
        }
        geometry_mm = normalize_mm_map(
            cell.get("geometry_mm", {}),
            ["x_mm", "y_mm", "w_mm", "h_mm", "wall_int_mm", "wall_ext_mm"],
        )
        openings_mm = normalize_mm_map(
            cell.get("openings_mm", {}),
            ["door_mm", "window_mm"],
        )
        normalized_cells.append(
            {
                "order": cell.get("order"),
                "name": normalize_whitespace(cell.get("name", "")),
                "icon": normalize_whitespace(cell.get("icon", "")),
                "size_text": normalize_whitespace(cell.get("size", "")),
                "size_metrics": parse_area_metrics(cell.get("size", "")),
                "badges": cell.get("badges", []),
                "classes": cell.get("classes", []),
                "target_room_local_id": target_local_id,
                "target_room_uid": target_uid,
                "layout": layout,
                "geometry_mm": geometry_mm,
                "openings_mm": openings_mm,
                "is_entry": to_bool(cell.get("is_entry"), False),
                "material": normalize_whitespace(cell.get("material", "")),
            }
        )

    normalized_plan_rows: list[dict[str, Any]] = []
    for row in floor.get("plan_rows", []):
        raw_weights = row.get("column_weights", [])
        if not isinstance(raw_weights, list):
            raw_weights = []
        normalized_plan_rows.append(
            {
                "order": to_int(row.get("order"), 0),
                "classes": row.get("classes", []),
                "grid_template_columns": normalize_whitespace(row.get("grid_template_columns", "")),
                "column_weights": [round(max(0.1, to_float(v, 1.0)), 3) for v in raw_weights],
                "cell_orders": [to_int(v, 0) for v in row.get("cell_orders", []) if to_int(v, 0) > 0],
                "row_height_mm": to_optional_float(row.get("row_height_mm")),
            }
        )

    normalized_tables: list[dict[str, Any]] = []
    for table in floor.get("tables", []):
        headers = [normalize_whitespace(h) for h in table.get("headers", []) if normalize_whitespace(h)]
        rows = [[normalize_whitespace(v) for v in row] for row in table.get("rows", [])]
        normalized_tables.append(
            {
                "order": table.get("order"),
                "context_title": normalize_whitespace(table.get("context_title", "")),
                "headers": headers,
                "rows": rows,
                "records": rows_to_table_objects(headers, rows),
            }
        )

    normalized_checklists = []
    for cl in floor.get("checklists", []):
        normalized_checklists.append(
            {
                "order": cl.get("order"),
                "title": normalize_whitespace(cl.get("title", "")),
                "items": [normalize_whitespace(i) for i in cl.get("items", []) if normalize_whitespace(i)],
            }
        )

    normalized_sections = []
    for sec in floor.get("section_blocks", []):
        normalized_sections.append(
            {
                "order": sec.get("order"),
                "title": normalize_whitespace(sec.get("title", "")),
                "classes": sec.get("classes", []),
                "bullet_items": [normalize_whitespace(i) for i in sec.get("bullet_items", []) if normalize_whitespace(i)],
            }
        )

    constraints = []
    for cl in normalized_checklists:
        for item in cl["items"]:
            constraints.append({"source": "checklist", "title": cl["title"], "text": item})
    for sec in normalized_sections:
        for item in sec["bullet_items"]:
            constraints.append({"source": "section_block", "title": sec["title"], "text": item})

    return {
        "id": floor_id,
        "order": floor.get("order"),
        "title": strip_leading_emoji(floor.get("title", "")),
        "raw_title": normalize_whitespace(floor.get("title", "")),
        "subtitle": normalize_whitespace(floor.get("subtitle", "")),
        "tab_label": tab_label,
        "direction_badges": floor.get("direction_badges", []),
        "geometry_mm": floor_geometry_mm,
        "geometry_source": normalize_whitespace(floor.get("geometry_source", "")),
        "plan_rows": normalized_plan_rows,
        "rooms": normalized_rooms,
        "plan_cells": normalized_cells,
        "tables": normalized_tables,
        "checklists": normalized_checklists,
        "sections": normalized_sections,
        "constraints": constraints,
        "summary": {
            "room_count": len(normalized_rooms),
            "room_notes_count": sum(len(r.get("notes_normalized", [])) for r in normalized_rooms),
            "plan_row_count": len(normalized_plan_rows),
            "plan_cell_count": len(normalized_cells),
            "precise_plan_cell_count": sum(
                1
                for cell in normalized_cells
                if all(k in (cell.get("geometry_mm") or {}) for k in ("x_mm", "y_mm", "w_mm", "h_mm"))
            ),
            "table_count": len(normalized_tables),
            "checklist_count": len(normalized_checklists),
            "section_count": len(normalized_sections),
            "constraint_count": len(constraints),
        },
    }


def transform_storage_zones(building_id: str, source_file: str, zones: list[dict[str, Any]]) -> dict[str, Any]:
    room_items = []
    for zone in zones:
        local_id = f"zone_{zone.get('order')}"
        room_uid = f"{building_id}:floor-0:{local_id}"
        details = [normalize_whitespace(zone.get("detail", ""))] if normalize_whitespace(zone.get("detail", "")) else []
        tags: list[dict[str, str]] = []
        notes_payload = compose_room_notes(details, tags)
        room_items.append(
            {
                "uid": room_uid,
                "local_id": local_id,
                "order": zone.get("order"),
                "name": normalize_whitespace(zone.get("name", "")),
                "icon": normalize_whitespace(zone.get("icon", "")),
                "area_text": "",
                "area_metrics": parse_area_metrics(""),
                "details": details,
                "tags": tags,
                "notes_raw": notes_payload["notes_raw"],
                "notes_normalized": notes_payload["notes_normalized"],
                "notes_rendered": notes_payload["notes_rendered"],
                "defaults_applied": {
                    "standard_profile": RESIDENTIAL_DEFAULTS.get("profile", ""),
                    "standard_schema": RESIDENTIAL_DEFAULTS.get("schema_version", ""),
                    "used_default_area_assumption": True,
                },
                "classes": zone.get("classes", []),
            }
        )
    return {
        "id": "floor-0",
        "order": 1,
        "title": "Storage Layout",
        "raw_title": "Storage Layout",
        "subtitle": source_file,
        "tab_label": "",
        "direction_badges": [],
        "geometry_mm": {},
        "geometry_source": "",
        "rooms": room_items,
        "plan_cells": [],
        "tables": [],
        "checklists": [],
        "sections": [],
        "constraints": [],
        "summary": {
            "room_count": len(room_items),
            "room_notes_count": sum(len(r.get("notes_normalized", [])) for r in room_items),
            "plan_cell_count": 0,
            "precise_plan_cell_count": 0,
            "table_count": 0,
            "checklist_count": 0,
            "section_count": 0,
            "constraint_count": 0,
        },
    }


def load_structured_documents() -> list[dict[str, Any]]:
    docs = []
    for path in sorted(STRUCTURED_DIR.glob("*.structured.json")):
        docs.append(json.loads(path.read_text(encoding="utf-8")))
    return docs


def build_program(docs: list[dict[str, Any]]) -> dict[str, Any]:
    buildings: list[dict[str, Any]] = []
    source_files: list[str] = []
    totals = {
        "building_count": 0,
        "floor_count": 0,
        "room_count": 0,
        "room_notes_count": 0,
        "precise_plan_cell_count": 0,
        "constraint_count": 0,
        "table_count": 0,
    }

    for doc in docs:
        source_file = doc.get("source_file", "")
        source_files.append(source_file)
        building_id = building_id_from_source(source_file)

        floors = []
        if doc.get("storage_zones"):
            floors.append(transform_storage_zones(building_id, source_file, doc["storage_zones"]))
        else:
            for floor in doc.get("floors", []):
                floors.append(transform_floor(building_id, floor, doc.get("tabs", [])))

        building_summary = {
            "floor_count": len(floors),
            "room_count": sum(f["summary"]["room_count"] for f in floors),
            "room_notes_count": sum(f["summary"].get("room_notes_count", 0) for f in floors),
            "precise_plan_cell_count": sum(f["summary"].get("precise_plan_cell_count", 0) for f in floors),
            "constraint_count": sum(f["summary"]["constraint_count"] for f in floors),
            "table_count": sum(f["summary"]["table_count"] for f in floors),
        }
        buildings.append(
            {
                "id": building_id,
                "source_file": source_file,
                "document_title": normalize_whitespace(doc.get("meta", {}).get("title", "")),
                "tabs": doc.get("tabs", []),
                "floors": floors,
                "summary": building_summary,
            }
        )

        totals["building_count"] += 1
        totals["floor_count"] += building_summary["floor_count"]
        totals["room_count"] += building_summary["room_count"]
        totals["room_notes_count"] += building_summary["room_notes_count"]
        totals["precise_plan_cell_count"] += building_summary["precise_plan_cell_count"]
        totals["constraint_count"] += building_summary["constraint_count"]
        totals["table_count"] += building_summary["table_count"]

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "source_schema_version": "house-design-structured-v2",
        "source_files": source_files,
        "default_standards": {
            "schema_version": RESIDENTIAL_DEFAULTS.get("schema_version", ""),
            "profile": RESIDENTIAL_DEFAULTS.get("profile", ""),
            "summary_line": defaults_summary_line(RESIDENTIAL_DEFAULTS),
            "config_path": RESIDENTIAL_DEFAULTS.get("_meta", {}).get("config_path", ""),
            "config_loaded": RESIDENTIAL_DEFAULTS.get("_meta", {}).get("config_loaded", False),
        },
        "buildings": buildings,
        "summary": totals,
    }


def main() -> None:
    docs = load_structured_documents()
    if not docs:
        raise SystemExit("No *.structured.json found. Run scripts/extract_layout_data.py first.")

    program = build_program(docs)
    OUTPUT_FILE.write_text(json.dumps(program, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote room program: {OUTPUT_FILE}")
    print(f"Summary: {program['summary']}")


if __name__ == "__main__":
    main()

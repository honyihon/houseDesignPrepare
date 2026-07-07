#!/usr/bin/env python3
"""Extract structured data from static building-plan HTML files."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "structured"
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.spatial_metadata import parse_cell_spatial, parse_floor_orientation  # noqa: E402

INPUT_FILES = [
    "AbuildingView.html",
    "BbuildingView.html",
    "CbuildingView.html",
    "storage.html",
]
SCHEMA_VERSION = "house-design-structured-v3"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def text_of(node: Tag | NavigableString | None) -> str:
    if node is None:
        return ""
    if isinstance(node, NavigableString):
        return normalize_whitespace(str(node))
    return normalize_whitespace(node.get_text(" ", strip=True))


def classes_of(node: Tag | None, remove: set[str] | None = None) -> list[str]:
    if node is None:
        return []
    remove = remove or set()
    return [cls for cls in (node.get("class") or []) if cls not in remove]


def parse_show_floor(onclick: str) -> str:
    match = re.search(r"showFloor\((\d+)\)", onclick or "")
    if not match:
        return ""
    return f"floor-{match.group(1)}"


def parse_highlight_room(onclick: str) -> str:
    raw = onclick or ""
    match = re.search(r"highlightRoom\(\s*'([^']+)'\s*(?:,|\))", raw)
    if match:
        return match.group(1)
    match = re.search(r'highlightRoom\(\s*"([^"]+)"\s*(?:,|\))', raw)
    return match.group(1) if match else ""


def parse_inline_style(style_text: str) -> dict[str, str]:
    style_map: dict[str, str] = {}
    for part in (style_text or "").split(";"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = normalize_whitespace(key).lower()
        value = normalize_whitespace(value)
        if key and value:
            style_map[key] = value
    return style_map


def _to_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    raw = normalize_whitespace(value)
    if not raw:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _attr_float(node: Tag, names: list[str]) -> float | None:
    for name in names:
        value = _to_optional_float(node.get(name))
        if value is not None:
            return value
    return None


def _attr_text(node: Tag, names: list[str]) -> str:
    for name in names:
        raw = normalize_whitespace(node.get(name, ""))
        if raw:
            return raw
    return ""


def _attr_bool(node: Tag, names: list[str], default: bool = False) -> bool:
    for name in names:
        if not node.has_attr(name):
            continue
        raw = normalize_whitespace(node.get(name, "")).lower()
        if raw in {"", "1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False
        return True
    return default


def _clean_mm_map(values: dict[str, float | None]) -> dict[str, float]:
    return {k: round(float(v), 3) for k, v in values.items() if v is not None}


def parse_grid_template_columns(template_text: str) -> list[float]:
    raw = normalize_whitespace(template_text)
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


def split_title_and_subtitle(title_node: Tag | None) -> tuple[str, str]:
    if title_node is None:
        return "", ""
    parts = [normalize_whitespace(s) for s in title_node.stripped_strings]
    parts = [p for p in parts if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " | ".join(parts[1:])


def extract_tabs(soup: BeautifulSoup) -> list[dict[str, Any]]:
    tabs: list[dict[str, Any]] = []
    for idx, tab in enumerate(soup.select(".tab"), start=1):
        icon = text_of(tab.select_one(".tab-icon"))
        label = text_of(tab)
        if icon:
            label = normalize_whitespace(label.replace(icon, "", 1))
        tabs.append(
            {
                "order": idx,
                "icon": icon,
                "label": label,
                "is_active_default": "active" in classes_of(tab),
                "target_floor_id": parse_show_floor(tab.get("onclick", "")),
            }
        )
    return tabs


def extract_plan_cell(
    cell: Tag,
    order: int,
    row_order: int = 0,
    col_order: int = 0,
    col_weight: float = 1.0,
    row_template_columns: list[float] | None = None,
) -> dict[str, Any]:
    badges = [text_of(b) for b in cell.select(".io-badges .badge") if text_of(b)]
    geometry_mm = _clean_mm_map(
        {
            "x_mm": _attr_float(cell, ["data-x-mm", "data-geom-x-mm", "data-mm-x"]),
            "y_mm": _attr_float(cell, ["data-y-mm", "data-geom-y-mm", "data-mm-y"]),
            "w_mm": _attr_float(cell, ["data-w-mm", "data-width-mm", "data-mm-w"]),
            "h_mm": _attr_float(cell, ["data-h-mm", "data-height-mm", "data-mm-h"]),
            "wall_int_mm": _attr_float(cell, ["data-wall-int-mm"]),
            "wall_ext_mm": _attr_float(cell, ["data-wall-ext-mm"]),
        }
    )
    openings_mm = _clean_mm_map(
        {
            "door_mm": _attr_float(cell, ["data-door-mm"]),
            "window_mm": _attr_float(cell, ["data-window-mm"]),
        }
    )
    return {
        "order": order,
        "target_room_id": parse_highlight_room(cell.get("onclick", "")),
        "icon": text_of(cell.select_one(".cell-icon")),
        "name": text_of(cell.select_one(".cell-name")),
        "size": text_of(cell.select_one(".cell-size")),
        "badges": badges,
        "classes": classes_of(cell, remove={"plan-cell"}),
        "row_order": row_order,
        "col_order": col_order,
        "col_weight": round(float(col_weight), 3),
        "row_template_columns": [round(float(v), 3) for v in (row_template_columns or [])],
        "geometry_mm": geometry_mm,
        "openings_mm": openings_mm,
        "is_entry": _attr_bool(cell, ["data-entry", "data-is-entry"]),
        "material": _attr_text(cell, ["data-material"]),
        "spatial": parse_cell_spatial(cell.attrs, classes_of(cell, remove={"plan-cell"})),
    }


def extract_plan_layout(scope: Tag) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []

    plan_grid = scope.select_one(".plan-grid-visual")
    if isinstance(plan_grid, Tag):
        order = 1
        row_nodes = plan_grid.find_all(class_="plan-row", recursive=False)
        for row_idx, row in enumerate(row_nodes, start=1):
            if not isinstance(row, Tag):
                continue

            row_cells = [c for c in row.find_all(class_="plan-cell", recursive=False) if isinstance(c, Tag)]
            if not row_cells:
                continue

            style_map = parse_inline_style(row.get("style", ""))
            template_raw = style_map.get("grid-template-columns", "")
            column_weights = parse_grid_template_columns(template_raw)

            if not column_weights:
                column_weights = [1.0] * len(row_cells)
            elif len(column_weights) < len(row_cells):
                column_weights.extend([column_weights[-1]] * (len(row_cells) - len(column_weights)))
            elif len(column_weights) > len(row_cells):
                column_weights = column_weights[: len(row_cells)]

            row_record = {
                "order": row_idx,
                "classes": classes_of(row, remove={"plan-row"}),
                "grid_template_columns": normalize_whitespace(template_raw),
                "column_weights": [round(float(v), 3) for v in column_weights],
                "cell_orders": [],
                "row_height_mm": _attr_float(row, ["data-row-h-mm", "data-height-mm"]),
            }

            for col_idx, cell in enumerate(row_cells, start=1):
                weight = column_weights[col_idx - 1] if col_idx - 1 < len(column_weights) else 1.0
                cell_payload = extract_plan_cell(
                    cell,
                    order=order,
                    row_order=row_idx,
                    col_order=col_idx,
                    col_weight=weight,
                    row_template_columns=column_weights,
                )
                row_record["cell_orders"].append(cell_payload["order"])
                cells.append(cell_payload)
                order += 1

            rows.append(row_record)

        if cells:
            return rows, cells

    for idx, cell in enumerate(scope.select(".plan-cell"), start=1):
        cells.append(extract_plan_cell(cell, order=idx))
    return rows, cells


def extract_room_tags(room: Tag) -> list[dict[str, Any]]:
    tags: list[dict[str, Any]] = []
    for tag in room.select(".tag"):
        title = text_of(tag.select_one(".tag-title"))
        full_text = text_of(tag)
        content = full_text
        if title and full_text.startswith(title):
            content = normalize_whitespace(full_text[len(title) :])
        tags.append(
            {
                "title": title,
                "content": content,
                "classes": classes_of(tag, remove={"tag"}),
            }
        )
    return tags


def extract_rooms(scope: Tag) -> list[dict[str, Any]]:
    rooms: list[dict[str, Any]] = []
    for idx, room in enumerate(scope.select(".room"), start=1):
        room_id = room.get("id", "")
        room_id = room_id.replace("room-", "", 1) if room_id.startswith("room-") else room_id
        details = [text_of(li) for li in room.select(".room-details li") if text_of(li)]
        geometry_mm = _clean_mm_map(
            {
                "x_mm": _attr_float(room, ["data-x-mm", "data-geom-x-mm", "data-mm-x"]),
                "y_mm": _attr_float(room, ["data-y-mm", "data-geom-y-mm", "data-mm-y"]),
                "w_mm": _attr_float(room, ["data-w-mm", "data-width-mm", "data-mm-w"]),
                "h_mm": _attr_float(room, ["data-h-mm", "data-height-mm", "data-mm-h"]),
            }
        )
        rooms.append(
            {
                "order": idx,
                "id": room_id,
                "name": text_of(room.select_one(".room-name")),
                "area": text_of(room.select_one(".room-area")),
                "details": details,
                "tags": extract_room_tags(room),
                "classes": classes_of(room, remove={"room"}),
                "geometry_mm": geometry_mm,
                "target_cell_id": _attr_text(room, ["data-target-cell", "data-slot-id"]),
            }
        )
    return rooms


def find_context_title(table: Tag, floor_scope: Tag) -> str:
    selectors = [
        ".system-title",
        ".spec-title",
        ".checklist-title",
        ".warning-title",
        ".flow-title",
        ".section-title",
        "h2",
        "h3",
        "h4",
    ]
    parent = table.parent
    while isinstance(parent, Tag) and parent != floor_scope:
        for selector in selectors:
            title_node = parent.select_one(selector)
            if title_node:
                text = text_of(title_node)
                if text:
                    return text
        parent = parent.parent
    return ""


def extract_tables(scope: Tag) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for idx, table in enumerate(scope.select("table"), start=1):
        headers = [text_of(th) for th in table.select("tr th")]
        rows: list[list[str]] = []
        for row in table.select("tr"):
            values = [text_of(td) for td in row.select("td")]
            if values:
                rows.append(values)
        tables.append(
            {
                "order": idx,
                "context_title": find_context_title(table, scope),
                "headers": headers,
                "rows": rows,
            }
        )
    return tables


def extract_checklists(scope: Tag) -> list[dict[str, Any]]:
    checklists: list[dict[str, Any]] = []
    for idx, box in enumerate(scope.select(".checklist-box"), start=1):
        items = [text_of(li) for li in box.select("li") if text_of(li)]
        checklists.append(
            {
                "order": idx,
                "title": text_of(box.select_one(".checklist-title")),
                "items": items,
            }
        )
    return checklists


def extract_section_blocks(scope: Tag) -> list[dict[str, Any]]:
    selector = (
        ".system-box, .spec-box, .warning-box, .checklist-box, "
        ".important-notes, .typhoon-section, .fengshui-section"
    )
    sections: list[dict[str, Any]] = []
    for idx, block in enumerate(scope.select(selector), start=1):
        title = ""
        for title_selector in [
            ".system-title",
            ".spec-title",
            ".warning-title",
            ".checklist-title",
            "h2",
            "h3",
            "h4",
        ]:
            node = block.select_one(title_selector)
            if node:
                title = text_of(node)
                if title:
                    break
        bullet_items = [text_of(li) for li in block.select("li") if text_of(li)]
        sections.append(
            {
                "order": idx,
                "title": title,
                "classes": classes_of(block),
                "bullet_items": bullet_items,
            }
        )
    return sections


def extract_floor(scope: Tag, order: int) -> dict[str, Any]:
    plan_rows, plan_cells = extract_plan_layout(scope)
    title, subtitle = split_title_and_subtitle(scope.select_one(".floor-title"))
    direction_badges = [text_of(node) for node in scope.select(".direction-badge .dir-item") if text_of(node)]
    geometry_mm = _clean_mm_map(
        {
            "width_mm": _attr_float(scope, ["data-floor-width-mm", "data-width-mm"]),
            "depth_mm": _attr_float(scope, ["data-floor-depth-mm", "data-height-mm", "data-depth-mm"]),
        }
    )
    north_deg = _attr_float(scope, ["data-north-deg"])
    if north_deg is not None:
        geometry_mm["north_deg"] = round(float(north_deg), 3)
    return {
        "order": order,
        "id": scope.get("id") or f"floor-{order - 1}",
        "title": title,
        "subtitle": subtitle,
        "direction_badges": direction_badges,
        "orientation": parse_floor_orientation(scope.attrs),
        "geometry_mm": geometry_mm,
        "geometry_source": _attr_text(scope, ["data-geometry-source"]),
        "plan_rows": plan_rows,
        "plan_cells": plan_cells,
        "rooms": extract_rooms(scope),
        "tables": extract_tables(scope),
        "checklists": extract_checklists(scope),
        "section_blocks": extract_section_blocks(scope),
    }


def extract_storage_zones(soup: BeautifulSoup) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    for idx, zone in enumerate(soup.select(".zone"), start=1):
        icon = text_of(zone.select_one(".zone-icon"))
        detail = text_of(zone.select_one(".sedan-detail"))
        strings = [normalize_whitespace(s) for s in zone.stripped_strings]
        strings = [s for s in strings if s]
        if icon and strings and strings[0] == icon:
            strings = strings[1:]
        if detail and strings and strings[-1] == detail:
            strings = strings[:-1]
        name = " ".join(strings)
        zones.append(
            {
                "order": idx,
                "name": name,
                "icon": icon,
                "detail": detail,
                "classes": classes_of(zone, remove={"zone"}),
            }
        )
    return zones


def parse_html_file(path: Path) -> dict[str, Any]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    floors = [extract_floor(floor, idx) for idx, floor in enumerate(soup.select(".floor-plan"), start=1)]
    tabs = extract_tabs(soup)
    storage_zones = extract_storage_zones(soup)

    document = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "source_file": path.name,
        "meta": {
            "title": text_of(soup.title),
            "lang": soup.html.get("lang", "") if soup.html else "",
        },
        "tabs": tabs,
        "floors": floors,
        "storage_zones": storage_zones,
    }
    document["summary"] = {
        "tab_count": len(tabs),
        "floor_count": len(floors),
        "plan_cell_count": sum(len(f["plan_cells"]) for f in floors),
        "precise_plan_cell_count": sum(
            1
            for floor in floors
            for cell in floor["plan_cells"]
            if isinstance(cell.get("geometry_mm"), dict)
            and all(k in cell["geometry_mm"] for k in ("x_mm", "y_mm", "w_mm", "h_mm"))
        ),
        "room_count": sum(len(f["rooms"]) for f in floors),
        "table_count": sum(len(f["tables"]) for f in floors),
        "checklist_count": sum(len(f["checklists"]) for f in floors),
        "storage_zone_count": len(storage_zones),
    }
    return document


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    index_records: list[dict[str, Any]] = []
    for file_name in INPUT_FILES:
        input_path = ROOT / file_name
        if not input_path.exists():
            continue

        document = parse_html_file(input_path)
        output_name = f"{input_path.stem}.structured.json"
        output_path = OUTPUT_DIR / output_name
        write_json(output_path, document)
        index_records.append(
            {
                "source_file": input_path.name,
                "output_file": output_name,
                "summary": document["summary"],
            }
        )
        print(f"Structured: {input_path.name} -> {output_name}")

    index = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "documents": index_records,
    }
    write_json(OUTPUT_DIR / "index.json", index)
    print(f"Wrote index: {OUTPUT_DIR / 'index.json'}")


if __name__ == "__main__":
    main()

"""Compare two historical sketch branches for regression and archive use.

The two models answer different questions and must not be forced to agree.
This module only *names* the differences so both 3D viewers can show them.
"""

from __future__ import annotations

from html import escape
from typing import Any

HTML_TO_PARA_FLOOR = {
    "floor-1": "floor-1",
    "floor-2": "floor-2",
    "floor-3": "floor-3",
    "floor-4": "floor-rf",
}

PARA_TO_HTML_FLOOR = {v: k for k, v in HTML_TO_PARA_FLOOR.items()}

# Generated leftovers that are not a "missing room" in the brief.
PARA_INFRA_ROLES = {"corridor", "flex"}

# HTML local_id → parametric cell id. Building-specific keys win.
GENERIC_ALIASES: dict[str, str] = {
    "dining": "living",
    "flex1": "elder",
    "balcony1": "balcony",
    "water-inlet": "balcony",
    "stair-door": "stair",
    "stair1": "stair",
    "stair2": "stair",
    "stair3": "stair",
    "stair1f": "stair",
    "stair2f": "stair",
    "stair3f": "stair",
    "stair-rf": "rf_stair",
    "stairrf": "rf_stair",
    "walkin": "closet",
    "hall2": "corridor",
    "bedroom2": "bed2",
    "master-bath": "master_bath",
    "entertainment": "media",
    "terrace3": "balcony3",
    "riser": "rf_service_aisle",
    "water-tank": "rf_tank",
    "vf800": "rf_tank",
    "haier": "rf_hp",
    "solar": "rf_solar",
    "laundry-rf": "rf_deck",
    "entrance": "entry",
    "sliding-door": "corridor",
    "elder-bath": "elder_bath",
    "balcony2f": "balcony_c2",
    "living2f": "living2",
    "guestroom2f": "guest2",
    "kitchen2f": "kitchenette",
    "bath2f": "bath_c2",
    "terrace3f": "balcony_c3",
    "master3f": "master_c",
    "fitness3f": "gym",
    "bath3f": "bath_c3",
    "riser-rf": "rf_service_aisle",
    "pump": "rf_hp",
    "heatpump": "rf_hp",
    "platform": "rf_deck",
    "idf-cabinet": "idf_b",
    "storage": "palanquin",
    "living2": "living_b",
    "bar2": "tea",
    "master2": "master_b",
    "ktv3": "ktv",
    "guest3": "guest_b",
    "tank-rf": "rf_tank",
    "pump-rf": "rf_hp",
    "hotwater-rf": "rf_hp",
    "platform-rf": "rf_deck",
}

BUILDING_ALIASES: dict[str, dict[str, str]] = {
    "A": {
        "balcony1": "balcony",
        "terrace3": "balcony3",
        "balcony2": "balcony2",
    },
    "B": {
        "bath1": "bath_acc",
        "balcony1": "balcony_b",
        "balcony2": "balcony_b2",
        "terrace3": "flex_front0",
        "ladder3": "balcony_b3",
        "bath2": "bath_g",
        "bath3": "bath_b3",
        "living2": "living_b",
    },
    "C": {
        "balcony1": "balcony",
        "service": "balcony",
    },
}

DEFAULT_FRONTAGE_MM = 6000
DEFAULT_BAYS = 1
OVERLAP_TOLERANCE_MM = 1.0


def norm_id(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def aabbs_overlap(
    a: dict[str, Any],
    b: dict[str, Any],
    tolerance_mm: float = OVERLAP_TOLERANCE_MM,
) -> bool:
    """True when two {x_mm,y_mm,w_mm,h_mm} boxes overlap by more than *tolerance_mm*."""

    ax1 = float(a.get("x_mm") or 0)
    ay1 = float(a.get("y_mm") or 0)
    ax2 = ax1 + float(a.get("w_mm") or 0)
    ay2 = ay1 + float(a.get("h_mm") or 0)
    bx1 = float(b.get("x_mm") or 0)
    by1 = float(b.get("y_mm") or 0)
    bx2 = bx1 + float(b.get("w_mm") or 0)
    by2 = by1 + float(b.get("h_mm") or 0)
    return (min(ax2, bx2) - max(ax1, bx1) > tolerance_mm) and (
        min(ay2, by2) - max(ay1, by1) > tolerance_mm
    )


def find_cell_overlaps(
    cells: list[dict[str, Any]],
    geom_key: str,
    building_id: str,
    floor_id: str,
    tolerance_mm: float = OVERLAP_TOLERANCE_MM,
) -> list[dict[str, Any]]:
    """Pairwise AABB overlaps among cells, reading geometry from *geom_key*."""

    boxes: list[tuple[str, str, dict[str, Any]]] = []
    for cell in cells:
        geo = cell.get(geom_key) or {}
        w = float(geo.get("w_mm") or 0)
        h = float(geo.get("h_mm") or 0)
        if w <= 0 or h <= 0:
            continue
        boxes.append(
            (
                str(cell.get("key") or cell.get("id") or ""),
                str(cell.get("name") or ""),
                {
                    "x_mm": float(geo.get("x_mm") or 0),
                    "y_mm": float(geo.get("y_mm") or 0),
                    "w_mm": w,
                    "h_mm": h,
                },
            )
        )

    hits: list[dict[str, Any]] = []
    for i, (akey, aname, a) in enumerate(boxes):
        for bkey, bname, b in boxes[i + 1 :]:
            if aabbs_overlap(a, b, tolerance_mm):
                hits.append(
                    {
                        "building": building_id,
                        "floor": floor_id,
                        "a": akey,
                        "b": bkey,
                        "a_name": aname,
                        "b_name": bname,
                    }
                )
    return hits


def resolve_html_to_para(building_id: str, html_id: str, para_ids: set[str]) -> str | None:
    """Map an HTML room key onto a parametric cell id, or None if unmatched."""

    raw = str(html_id or "").strip()
    if not raw:
        return None
    building_map = BUILDING_ALIASES.get(building_id) or {}
    if raw in building_map:
        return building_map[raw]
    if raw in GENERIC_ALIASES:
        return GENERIC_ALIASES[raw]

    by_norm = {norm_id(p): p for p in para_ids}
    n = norm_id(raw)
    if n in by_norm:
        return by_norm[n]
    if raw in para_ids:
        return raw
    return None


def pick_variant(
    plan: dict[str, Any],
    frontage_mm: int = DEFAULT_FRONTAGE_MM,
    bays: int = DEFAULT_BAYS,
) -> dict[str, Any] | None:
    variants = plan.get("variants") or []
    for variant in variants:
        garage = variant.get("garage") or {}
        if int(variant.get("frontage_mm") or 0) == frontage_mm and int(garage.get("bays") or 0) == bays:
            return variant
    return variants[0] if variants else None


def _html_floors(building: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in building.get("floors") or [] if f.get("record_type") == "floor"]


def _cell_key(cell: dict[str, Any]) -> str:
    return str(cell.get("target_room_local_id") or cell.get("override_key") or "").strip()


def _html_envelope(floors: list[dict[str, Any]]) -> tuple[float, float]:
    width = 0.0
    depth = 0.0
    for floor in floors:
        auto = floor.get("geometry_auto_mm") or floor.get("geometry_mm") or {}
        width = max(width, float(auto.get("width_mm") or 0))
        depth = max(depth, float(auto.get("depth_mm") or 0))
    return width, depth


def _floor_label(html_id: str, para_id: str, html_floor: dict[str, Any] | None) -> str:
    if html_floor:
        label = str(html_floor.get("tab_label") or html_floor.get("title") or "").strip()
        if label:
            if para_id == "floor-rf" and "RF" not in label.upper() and "屋頂" not in label:
                return f"{label}（屋頂／RF，非 4F）"
            return label
    if para_id == "floor-rf" or html_id == "floor-4":
        return "RF（屋頂，非 4F）"
    return html_id


def compare_floor(
    building_id: str,
    html_floor: dict[str, Any] | None,
    para_floor: dict[str, Any] | None,
) -> dict[str, Any]:
    html_id = str((html_floor or {}).get("id") or PARA_TO_HTML_FLOOR.get(
        str((para_floor or {}).get("floor_id") or ""), ""
    ))
    para_id = str((para_floor or {}).get("floor_id") or HTML_TO_PARA_FLOOR.get(html_id, html_id))

    html_cells = []
    if html_floor:
        for cell in html_floor.get("plan_cells") or []:
            key = _cell_key(cell)
            if not key:
                continue
            html_cells.append({"id": key, "name": str(cell.get("name") or key)})

    para_cells = []
    para_by_id: dict[str, dict[str, Any]] = {}
    if para_floor:
        for cell in para_floor.get("cells") or []:
            cid = str(cell.get("id") or "")
            if not cid:
                continue
            item = {
                "id": cid,
                "name": str(cell.get("name") or cid),
                "role": str(cell.get("role") or "room"),
            }
            para_cells.append(item)
            para_by_id[cid] = item

    para_ids = set(para_by_id)
    grouped: dict[str, list[dict[str, str]]] = {}
    html_only: list[dict[str, str]] = []
    claimed: set[str] = set()

    for html_cell in html_cells:
        mapped = resolve_html_to_para(building_id, html_cell["id"], para_ids)
        if not mapped or mapped not in para_ids:
            html_only.append(html_cell)
            continue
        grouped.setdefault(mapped, []).append(html_cell)
        claimed.add(mapped)

    matched: list[dict[str, str]] = []
    renamed: list[dict[str, str]] = []
    merged: list[dict[str, Any]] = []
    for para_id_key, html_group in grouped.items():
        para = para_by_id[para_id_key]
        if len(html_group) > 1:
            merged.append(
                {
                    "para_id": para_id_key,
                    "para_name": para["name"],
                    "html": html_group,
                }
            )
            continue
        html_cell = html_group[0]
        row = {
            "html_id": html_cell["id"],
            "html_name": html_cell["name"],
            "para_id": para_id_key,
            "para_name": para["name"],
        }
        if html_cell["id"] != para_id_key and html_cell["name"] != para["name"]:
            renamed.append(row)
        else:
            matched.append(row)

    para_only = [c for c in para_cells if c["id"] not in claimed]

    return {
        "html_floor_id": html_id,
        "para_floor_id": para_id,
        "label": _floor_label(html_id, para_id, html_floor),
        "html_only": html_only,
        "para_only": para_only,
        "matched": matched,
        "renamed": renamed,
        "merged": merged,
    }


def build_compare(
    program: dict[str, Any],
    plan: dict[str, Any] | None,
    frontage_mm: int = DEFAULT_FRONTAGE_MM,
    bays: int = DEFAULT_BAYS,
) -> dict[str, Any]:
    """Build the payload both 3D viewers embed."""

    empty = {
        "schema": "house-html-parametric-compare-v1",
        "available": False,
        "variant": None,
        "ghost": None,
        "buildings": [],
        "note": "沒有參數化 plan.json，略過對照。",
    }
    if not plan:
        return empty

    variant = pick_variant(plan, frontage_mm, bays)
    if not variant:
        return empty

    site = plan.get("site") or {}
    storey = float(site.get("storey_height_mm") or 3000)
    parapet = float(site.get("parapet_height_mm") or 1100)
    storeys = int(site.get("storeys") or 3)
    garage = variant.get("garage") or {}
    frontage = float(variant.get("frontage_mm") or frontage_mm)
    depth = float(variant.get("depth_mm") or 0)
    ghost = {
        "frontage_mm": frontage,
        "depth_mm": depth,
        "height_mm": storeys * storey + parapet,
        "storey_height_mm": storey,
        "parapet_height_mm": parapet,
        "label": (
            f"舊版 32 坪建築面積情境（{frontage / 1000:g} m × "
            f"{int(garage.get('bays') or bays)} 車位）"
        ),
    }

    html_by_id = {str(b.get("id")): b for b in program.get("buildings") or []}
    para_buildings = (variant.get("buildings") or {}) if isinstance(variant.get("buildings"), dict) else {}

    buildings_out: list[dict[str, Any]] = []
    for bid in ("A", "B", "C"):
        html_b = html_by_id.get(bid)
        para_b = para_buildings.get(bid) or {}
        html_floors = _html_floors(html_b) if html_b else []
        html_by_floor = {str(f.get("id")): f for f in html_floors}
        para_floors = {str(f.get("floor_id")): f for f in para_b.get("floors") or []}
        html_w, html_d = _html_envelope(html_floors)
        floor_ids = []
        for html_id in ("floor-1", "floor-2", "floor-3", "floor-4"):
            para_id = HTML_TO_PARA_FLOOR[html_id]
            if html_id in html_by_floor or para_id in para_floors:
                floor_ids.append((html_id, para_id))

        buildings_out.append(
            {
                "id": bid,
                "html_width_mm": html_w,
                "html_depth_mm": html_d,
                "para_frontage_mm": float(para_b.get("frontage_mm") or frontage),
                "para_depth_mm": float(para_b.get("depth_mm") or depth),
                "floors": [
                    compare_floor(bid, html_by_floor.get(hid), para_floors.get(pid))
                    for hid, pid in floor_ids
                ],
            }
        )

    return {
        "schema": "house-html-parametric-compare-v1",
        "available": True,
        "variant": {
            "id": variant.get("id"),
            "frontage_mm": frontage,
            "depth_mm": depth,
            "bays": int(garage.get("bays") or bays),
            "footprint_ping": variant.get("footprint_ping"),
            "label": ghost["label"],
        },
        "ghost": ghost,
        "buildings": buildings_out,
        "note": (
            "HTML 與參數化都是歷史示意；現行 32 坪是基地面積，不是這裡的建築面積。"
            "兩邊房間清單與開間都不同，這是刻意的，不是繪圖錯誤。"
        ),
    }


def format_compare_panel(compare: dict[str, Any]) -> str:
    """Inner HTML for the shared 對照 side panel."""

    if not compare or not compare.get("available"):
        return "<p class=\"hint\">沒有參數化 plan.json，略過對照。</p>"

    variant = compare.get("variant") or {}
    parts: list[str] = [
        f"<p class=\"hint\">{escape(str(compare.get('note') or ''))}</p>",
        f"<p class=\"hint\">對照變體：<b>{escape(str(variant.get('label') or ''))}</b></p>",
    ]
    for building in compare.get("buildings") or []:
        parts.append(f"<div class=\"grp\"><div class=\"grp-head\"><strong>{escape(str(building['id']))} 棟</strong>"
                     f"<span class=\"tag\">{int(building.get('html_width_mm') or 0)}×"
                     f"{int(building.get('html_depth_mm') or 0)} vs "
                     f"{int(building.get('para_frontage_mm') or 0)}×"
                     f"{int(building.get('para_depth_mm') or 0)} mm</span></div>")
        for floor in building.get("floors") or []:
            bits: list[str] = []
            for item in floor.get("merged") or []:
                html_names = "＋".join(h.get("name") or h.get("id") for h in item.get("html") or [])
                bits.append(
                    f"<li>合併：{escape(html_names)} → {escape(item.get('para_name') or item.get('para_id'))}</li>"
                )
            for item in floor.get("renamed") or []:
                bits.append(
                    f"<li>更名：{escape(item['html_name'])} → {escape(item['para_name'])}</li>"
                )
            for item in floor.get("html_only") or []:
                bits.append(f"<li>只在 HTML：{escape(item['name'])}</li>")
            extras = [
                c for c in floor.get("para_only") or []
                if c.get("role") not in PARA_INFRA_ROLES
            ]
            infra = [
                c for c in floor.get("para_only") or []
                if c.get("role") in PARA_INFRA_ROLES
            ]
            for item in extras:
                bits.append(f"<li>只在參數化：{escape(item['name'])}</li>")
            if infra:
                names = "、".join(c["name"] for c in infra)
                bits.append(f"<li class=\"muted\">參數化另有：{escape(names)}</li>")
            if not bits:
                bits.append("<li class=\"muted\">這一層房間大致對得上</li>")
            parts.append(
                f"<details><summary>{escape(floor.get('label') or '')}</summary>"
                f"<ul class=\"compare-list\">{''.join(bits)}</ul></details>"
            )
        parts.append("</div>")
    return "\n".join(parts)

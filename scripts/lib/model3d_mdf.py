"""An honest, non-installed under-stair MDF study from the current stair/rack.

This layer never puts a second rack in the furniture inventory, removes a
backup or frees space. A tread-top sensitivity is not a structural section.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from lib.model3d_placement import overlaps, rectangle

SOURCE = Path(__file__).resolve().parents[2] / "inputs/a-mdf-under-stair.json"
STATUS = "conditional-not-installed"
PROFESSIONAL_KEYS = {
    "structural_section",
    "finished_headroom",
    "fire_and_escape",
    "ventilation_and_heat",
    "water_and_condensation",
    "power_and_earthing",
    "equipment_and_replacement",
}


def _inside(a: dict, b: dict) -> bool:
    return all(a[k] >= b[k] for k in ("minX", "minY")) and all(a[k] <= b[k] for k in ("maxX", "maxY"))


def _finite_positive(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def build_mdf_study(buildings: list[dict], data: dict | None = None) -> dict:
    raw = copy.deepcopy(data) if data is not None else json.loads(SOURCE.read_text(encoding="utf-8"))
    if set(raw) != {
        "schema",
        "id",
        "status",
        "preferred_option",
        "active_design",
        "rack_catalog",
        "return_flight_offset_mm",
        "clearances_mm",
        "maintenance_height_target_mm",
        "underside_deductions_mm",
        "professional_status",
        "evidence",
        "reuse",
        "note",
    }:
        raise ValueError("MDF study source must not include computed or approval claims")
    if (
        raw.get("schema") != "house-mdf-under-stair-study-v1"
        or raw.get("status") != STATUS
        or raw.get("preferred_option") != "under-stair"
        or raw.get("active_design") != "side-backup"
        or raw.get("rack_catalog") != "rack-18u"
        or raw.get("evidence") is not None
        or set(raw.get("professional_status", {})) != PROFESSIONAL_KEYS
        or any(s != "unknown" for s in raw["professional_status"].values())
    ):
        raise ValueError("MDF study cannot adopt, verify or release unapproved space")
    clearance = raw.get("clearances_mm", {})
    minimum = {"front": 800, "rear": 600, "left": 300, "right": 300, "top": 200}
    if set(clearance) != set(minimum) or any(
        not _finite_positive(clearance[k]) or clearance[k] < v for k, v in minimum.items()
    ):
        raise ValueError("MDF study cannot reduce original maintenance clearances")
    if (
        not _finite_positive(raw.get("return_flight_offset_mm"))
        or not _finite_positive(raw.get("maintenance_height_target_mm"))
        or raw["maintenance_height_target_mm"] < 2000
        or raw.get("underside_deductions_mm") != [200, 300]
    ):
        raise ValueError("MDF study requires explicit, unverified section sensitivity")
    reuse = raw.get("reuse", {})
    if (
        reuse.get("status") != STATUS
        or reuse.get("installed") is not False
        or reuse.get("released_area_sqm") is not None
    ):
        raise ValueError("MDF backup is not released before the under-stair option is accepted")
    a = next(b for b in buildings if b["id"] == "A")
    floor = a["floors"][0]
    cells = {c["key"]: c for c in floor["cells"] if c.get("tour_active")}
    stair, backup = cells["stair-door"], cells["mdf"]
    ft = stair["tour_features"]
    g, flight = ft["stair_footprint_mm"], ft["stair_geometry"]
    rack = next(i for i in backup["furniture"] if i["catalog_id"] == raw["rack_catalog"])
    if (rack["width_mm"], rack["depth_mm"], rack["height_mm"]) != (600, 600, 1000):
        raise ValueError("MDF study needs a fresh section for a changed rack, never a resized original")
    p = backup["furniture_placements"]["tour_mm"][rack["id"]]
    if p["issues"] or len(p.get("side_operation_mm", [])) != 2:
        raise ValueError("MDF backup must retain its full left/right maintenance space")
    if any(rack.get(k + "_clearance_mm", 0) < clearance[k] for k in ("front", "rear", "left", "right")):
        raise ValueError("MDF backup lost its original maintenance clearances")
    body0 = rectangle(p["center_x_mm"], p["center_y_mm"], rack["width_mm"], rack["depth_mm"])
    sides0 = [
        {"side": "left", "aabb": dict(body0, minX=body0["minX"] - clearance["left"], maxX=body0["minX"])},
        {"side": "right", "aabb": dict(body0, minX=body0["maxX"], maxX=body0["maxX"] + clearance["right"])},
    ]
    bg0 = backup["tour_mm"]
    room0 = rectangle(bg0["x_mm"] + bg0["w_mm"] / 2, bg0["y_mm"] + bg0["h_mm"] / 2, bg0["w_mm"], bg0["h_mm"])
    if (
        p["rotation_deg"] != 0
        or p["aabb"] != body0
        or p["side_operation_mm"] != sides0
        or any(not _inside(z["aabb"], room0) for z in sides0)
    ):
        raise ValueError("MDF backup side maintenance geometry cannot be clipped or falsified")

    # The return flight rises toward the FRONT. Never put a rack under the
    # low departure flight just because the 2D rectangles overlap.
    fw = flight["flight_width_mm"]
    flight_box = rectangle(
        g["x_mm"] + g["w_mm"] - fw / 2,
        g["y_mm"] + flight["departure_offset_mm"] + flight["run_mm"] / 2,
        fw,
        flight["run_mm"],
    )
    cx = g["x_mm"] + g["w_mm"] - fw / 2
    cy = g["y_mm"] + flight["departure_offset_mm"] + raw["return_flight_offset_mm"]
    body = rectangle(cx, cy, rack["width_mm"], rack["depth_mm"])
    if not _inside(body, flight_box):
        raise ValueError("MDF rack candidate must remain below the actual upper return flight")
    service = {
        "minX": body["minX"] - clearance["left"],
        "maxX": body["maxX"] + clearance["right"],
        "minY": body["minY"] - clearance["front"],
        "maxY": body["maxY"] + clearance["rear"],
    }
    core = stair["tour_mm"]
    core_box = rectangle(core["x_mm"] + core["w_mm"] / 2, core["y_mm"] + core["h_mm"] / 2, core["w_mm"], core["h_mm"])
    segments = []
    n = flight["risers"] // 2
    rise = floor["height_mm"] / flight["risers"]
    for step in range(n - 1):
        y0 = g["y_mm"] + flight["departure_offset_mm"] + flight["run_mm"] - (step + 1) * flight["tread_mm"]
        segments.append(
            {"y0_mm": y0, "y1_mm": y0 + flight["tread_mm"], "tread_top_mm": floor["height_mm"] / 2 + (step + 1) * rise}
        )

    def top(box: dict) -> float | None:
        values = [s["tread_top_mm"] for s in segments if box["minY"] < s["y1_mm"] and box["maxY"] > s["y0_mm"]]
        return round(min(values), 2) if values else None

    issues = []
    if service["maxX"] - service["minX"] > fw:
        issues.append("side-maintenance-exceeds-return-flight")
    if not _inside(service, core_box):
        issues.append("maintenance-crosses-stair-room")
    if not _inside(service, flight_box):
        issues.append("full-maintenance-headroom-not-demonstrated")
    sensitivity = []
    for deduction in raw["underside_deductions_mm"]:
        sensitivity.append(
            {
                "deduction_mm": deduction,
                "deduction_verified": False,
                "rack_only_min_clear_mm": round(top(body) - deduction, 2),
                "return_flight_service_min_clear_mm": round(top(service) - deduction, 2),
                "covers_full_service_width": False,
            }
        )
    protected = [
        (c["id"], z)
        for c in cells.values()
        for z in c["tour_features"]["reserved_mm"]
        if z["kind"] in {"care-route", "care-turn", "door-approach", "stairs-landing"}
    ]
    conflicts = [{"room": rid, "kind": z["kind"]} for rid, z in protected if overlaps(service, z["aabb"])]
    if conflicts:
        issues.append("maintenance-overlaps-protected-reservation")
    rr = reuse.get("storage_rect_mm")
    if not isinstance(rr, list) or len(rr) != 4 or not all(_finite_positive(v) for v in rr):
        raise ValueError("MDF conditional reuse needs a positive, bounded storage rectangle")
    bg = backup["tour_mm"]
    reuse_box = rectangle(bg["x_mm"] + rr[0] + rr[2] / 2, bg["y_mm"] + rr[1] + rr[3] / 2, rr[2], rr[3])
    if not _inside(
        reuse_box, rectangle(bg["x_mm"] + bg["w_mm"] / 2, bg["y_mm"] + bg["h_mm"] / 2, bg["w_mm"], bg["h_mm"])
    ) or any(overlaps(reuse_box, z["aabb"]) for _, z in protected):
        raise ValueError("MDF conditional reuse must not occupy care turns, routes or doors")
    if not _finite_positive(reuse.get("storage_height_mm")):
        raise ValueError("MDF reuse height must remain a positive assumed dimension")
    if not _finite_positive(reuse.get("front_clearance_mm")) or reuse["front_clearance_mm"] < 600:
        raise ValueError("MDF conditional reuse needs its own front operation allowance")
    reuse_operation = dict(reuse_box, minX=reuse_box["maxX"], maxX=reuse_box["maxX"] + reuse["front_clearance_mm"])
    if any(overlaps(reuse_operation, z["aabb"]) for _, z in protected):
        raise ValueError("MDF conditional reuse operation occupies care or doorway space")
    result = raw
    result.update(
        {
            "source": "inputs/a-mdf-under-stair.json",
            "floor": floor["id"],
            "building": "A",
            "rack": {
                "original_item_id": rack["id"],
                "catalog_id": rack["catalog_id"],
                "width_mm": rack["width_mm"],
                "depth_mm": rack["depth_mm"],
                "height_mm": rack["height_mm"],
            },
            "candidate": {
                "center_x_mm": cx,
                "center_y_mm": cy,
                "rotation_deg": 0,
                "body_mm": body,
                "service_mm": service,
                "return_flight_mm": flight_box,
                "rack_tread_top_min_mm": top(body),
                "service_tread_top_min_mm": top(service),
                "flight_width_mm": fw,
                "segments": segments,
                "sensitivity": sensitivity,
                "issues": issues,
                "protected_conflicts": conflicts,
                "section_verified": False,
                "installed": False,
                "counts_as_furniture": False,
            },
            "backup": {
                "room_id": backup["id"],
                "geometry": copy.deepcopy(bg),
                "placement": copy.deepcopy(p),
                "reserved_area_sqm": round(bg["w_mm"] * bg["h_mm"] / 1e6, 4),
                "released_area_sqm": None,
            },
            "section_file": "A_floor-1_mdf-section.svg",
            "plan_file": "A_floor-1_mdf-study.svg",
        }
    )
    result["reuse"]["body_mm"] = reuse_box
    result["reuse"]["operation_mm"] = reuse_operation
    result["reuse"]["counts_as_furniture"] = False
    return result


def draw_mdf_overlay(root: Element, study: dict) -> None:
    """Draw AFTER the stair plan: a candidate is not an installed floor item."""
    group = SubElement(root, "g", {"data-mdf-study": STATUS})
    for name, box, colour in (
        ("service", study["candidate"]["service_mm"], "#b45309"),
        ("rack", study["candidate"]["body_mm"], "#0e7490"),
        ("conditional-reuse", study["reuse"]["body_mm"], "#b45309"),
        ("reuse-operation", study["reuse"]["operation_mm"], "#b45309"),
    ):
        SubElement(
            group,
            "rect",
            {
                "x": str(box["minX"]),
                "y": str(box["minY"]),
                "width": str(box["maxX"] - box["minX"]),
                "height": str(box["maxY"] - box["minY"]),
                "fill": "none",
                "stroke": colour,
                "stroke-width": "30",
                "stroke-dasharray": "100 60",
                "data-mdf-zone": name,
            },
        )
    SubElement(group, "text", {"x": "2450", "y": "6550", "font-size": "180"}).text = "梯下18U候選（非已安裝）"
    SubElement(group, "text", {"x": "2450", "y": "6830", "font-size": "165"}).text = "維修120cm > 梯段90cm"
    SubElement(group, "text", {"x": "140", "y": "11680", "font-size": "140"}).text = "備援未撤銷；再利用未施作"


def render_mdf_section(study: dict) -> str:
    root = Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": "0 0 1100 720",
            "role": "img",
            "aria-labelledby": "mdf-title mdf-desc",
            "data-mdf-study": STATUS,
        },
    )
    SubElement(root, "title", id="mdf-title").text = "A 1F MDF上折梯下候選剖面（非結構剖面）"
    SubElement(root, "desc", id="mdf-desc").text = study["note"]
    SubElement(root, "style").text = "text{font-family:system-ui,sans-serif;fill:#263846;font-size:18px}"
    SubElement(root, "rect", x="0", y="0", width="1100", height="720", fill="#f8fafc")

    def text(x: float, y: float, content: str, **attrs: str) -> None:
        SubElement(root, "text", {"x": str(x), "y": str(y), **attrs}).text = content

    text(28, 34, "梯下MDF優先候選／側壁龕備援", **{"font-size": "26", "font-weight": "700"})
    text(28, 65, "使用共用梯段／機櫃數據，未含實際梁、斜板、裝修、消防或設備選型。")
    c = study["candidate"]
    origin = min(s["y0_mm"] for s in c["segments"])
    scale, baseline = 0.12, 575

    def x(y: float) -> float:
        return 50 + (y - origin) * scale

    for segment in c["segments"]:
        top = baseline - segment["tread_top_mm"] * scale
        SubElement(
            root,
            "rect",
            x=str(x(segment["y0_mm"])),
            y=str(top),
            width=str((segment["y1_mm"] - segment["y0_mm"]) * scale),
            height="14",
            fill="#94a3b8",
        )
        # Not the physical structural underside: two independent allowances.
        for deduction, colour in ((200, "#64748b"), (300, "#b45309")):
            SubElement(
                root,
                "line",
                x1=str(x(segment["y0_mm"])),
                x2=str(x(segment["y1_mm"])),
                y1=str(top + deduction * scale),
                y2=str(top + deduction * scale),
                stroke=colour,
                **{"stroke-dasharray": "5 4", "data-underside-deduction-mm": str(deduction)},
            )
    SubElement(root, "line", x1="45", x2="405", y1=str(baseline), y2=str(baseline), stroke="#334155")
    body, service = c["body_mm"], c["service_mm"]
    SubElement(
        root,
        "rect",
        x=str(x(service["minY"])),
        y=str(baseline - 240),
        width=str((service["maxY"] - service["minY"]) * scale),
        height="240",
        fill="none",
        stroke="#b45309",
        **{"stroke-dasharray": "8 5", "data-service-height-target-mm": "2000"},
    )
    SubElement(
        root,
        "rect",
        x=str(x(body["minY"])),
        y=str(baseline - study["rack"]["height_mm"] * scale),
        width=str(study["rack"]["depth_mm"] * scale),
        height=str(study["rack"]["height_mm"] * scale),
        fill="#0e7490",
        **{"data-rack-height-mm": str(study["rack"]["height_mm"])},
    )
    text(50, 603, "前方80cm → 60cm機櫃 → 後方60cm")
    text(50, 635, "虛線扣200／300mm只是敏感度，並非已核梁板底。")
    text(465, 136, "機櫃 60×60×100cm；頂部暫留20cm")
    text(465, 174, "維修外廓 120×200cm；暫以2m站立高度比較")
    text(465, 212, f"梯段寬{c['flight_width_mm'] / 10:g}cm：左右維修仍有衝突", fill="#b45309")
    text(465, 260, "僅沿上折梯縱向推估（不含兩側）：")
    for i, scenario in enumerate(c["sensitivity"]):
        text(
            465,
            297 + 38 * i,
            f"扣{scenario['deduction_mm']}mm → 本體區{scenario['rack_only_min_clear_mm'] / 1000:.2f}m；"
            f"縱向維修區{scenario['return_flight_service_min_clear_mm'] / 1000:.2f}m",
        )
    text(465, 392, "這些數字不證明完整維修、散熱、承重或避難成立。")
    text(465, 439, "側壁龕備援仍保留，不能同時計入新增可用面積。")
    text(465, 480, "家務櫃只畫40cm深條件式範圍，不列已擺家具。")
    text(28, 692, "下一步：建築師梯剖面／消防分隔 → 弱電實物、散熱與換機演練 → 才決定搬入及再利用。")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="unicode") + "\n"

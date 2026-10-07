"""Offline HTML plan artifacts from the exact conceptual 3D payload."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from xml.etree.ElementTree import Element, SubElement, tostring

from lib.model3d_facade import render_elevation

SCHEMA = "house-concept-furniture-plan-v1"


def _tag(parent: Element, name: str, **attrs: object) -> Element:
    return SubElement(parent, name, {k.replace("_", "-"): str(v) for k, v in attrs.items()})


def _text(parent: Element, content: str, x: float, y: float, **attrs: object) -> Element:
    el = _tag(parent, "text", x=x, y=y, **attrs)
    el.text = content
    return el


def plan_data(payload: dict) -> dict:
    result = {
        "schema": SCHEMA,
        "geometry_source": "tour_mm",
        "status": "concept-not-surveyed",
        "note": "與 3D 共用固定外框合理性提案；不自動加深或縮小家具。未解需求保留，非基地容量或專業通過證明。",
        "layout_review": payload.get("layout_review", {}),
        "facade": payload.get("facade", {}),
        "buildings": [],
    }
    for building in payload["buildings"]:
        floors = []
        for floor in building["floors"]:
            rooms = []
            for cell in floor["cells"]:
                if cell.get("tour_active") is False:
                    continue
                items = [
                    {**item, "placement": cell["furniture_placements"]["tour_mm"][item["id"]]}
                    for item in cell.get("furniture", [])
                ]
                rooms.append(
                    {
                        "id": cell["id"],
                        "key": cell["key"],
                        "name": cell["name"],
                        "source_name": cell.get("source_name", cell["name"]),
                        "color": cell["color"],
                        "kind": cell["kind"],
                        "requirement_id": cell.get("review_spec", {}).get("requirement_id"),
                        "outdoor": cell["is_outdoor"],
                        "geometry": cell["tour_mm"],
                        "features": cell["tour_features"],
                        "furniture": items,
                        "placement_note": items[0].get("room_note", "") if items else "",
                    }
                )
            floors.append(
                {
                    "id": floor["id"],
                    "label": floor["label"],
                    "width_mm": floor.get("tour_width_mm", floor["auto_width_mm"]),
                    "depth_mm": floor["tour_depth_mm"],
                    "original_depth_mm": floor["auto_depth_mm"],
                    "plan_file": f"{building['id']}_{floor['id']}.svg",
                    "rooms": rooms,
                    "deferred_rooms": floor.get("deferred_rooms", []),
                }
            )
            if any(room["features"].get("frontage_study") for room in rooms):
                floors[-1]["frontage_study_file"] = f"{building['id']}_{floor['id']}_frontage-study.svg"
        result["buildings"].append(
            {"id": building["id"], "floors": floors, "layout_review": building.get("layout_review", {})}
        )
    return result


def render_plan(building: str, floor: dict, *, show_frontage_study: bool = False) -> str:
    width, depth = floor["width_mm"], floor["depth_mm"]
    root = Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": f"-300 -1000 {width + 600} {depth + 1400}",
            "role": "img",
            "aria-labelledby": "plan-title plan-desc",
            "data-schema": SCHEMA,
            "data-building": building,
            "data-floor": floor["id"],
            "data-geometry-source": "tour_mm",
            "data-frontage-study": "conditional-not-installed" if show_frontage_study else "keep-full-clear",
        },
    )
    _tag(root, "title", id="plan-title").text = f"{building} 棟 {floor['label']} · HTML／3D 共用家具概念配置"
    _tag(
        root, "desc", id="plan-desc"
    ).text = "道路／前方在上。常見市售暫估尺寸，尚未實測。虛線為操作與入口暫留帶，非驗證動線；未能放入的家具列待調整。"
    _tag(root, "style").text = (
        "text{font-family:system-ui,sans-serif;fill:#263846} .room-name{font-size:210px;font-weight:600} "
        ".item-number{font-size:180px;font-weight:700;fill:#fff;text-anchor:middle} "
        ".wall{stroke:#6b7274;stroke-width:100} .allowance{fill:none;stroke:#c2904c;stroke-width:18;stroke-dasharray:70 40} "
        ".front-mark{stroke:#24394a;stroke-width:22;fill:none}"
    )
    _text(root, f"{building} 棟 · {floor['label']} · 前方／道路 ↑", 0, -560, font_size=250, font_weight=700)
    _text(root, "固定比較框／非地籍可建面積。家具未縮放；未解需求見 HTML。", 0, -210, font_size=175)
    number = 0
    # Paint every zone before the walls so neighbors never erase boundaries.
    for room in floor["rooms"]:
        g = room["geometry"]
        _tag(
            root,
            "rect",
            x=g["x_mm"],
            y=g["y_mm"],
            width=g["w_mm"],
            height=g["h_mm"],
            fill=room["color"],
            fill_opacity="0.18",
        )
    for room in floor["rooms"]:
        g, features = room["geometry"], room["features"]
        group = _tag(
            root,
            "g",
            data_room_id=room["id"],
            data_space_group=features["space_group"],
            data_x_mm=g["x_mm"],
            data_y_mm=g["y_mm"],
            data_w_mm=g["w_mm"],
            data_h_mm=g["h_mm"],
        )
        url = "../model3d.html#" + urlencode(
            {"mode": "tour", "building": building, "floor": floor["id"], "room": room["id"], "view": "plan"}
        )
        anchor = _tag(group, "a", href=url, target="_blank")
        _text(
            anchor,
            room["name"][:16] + (" · 入口待定" if features["access_pending"] else ""),
            g["x_mm"] + 140,
            g["y_mm"] + 320,
            **{"class": "room-name"},
        )
        study = features.get("frontage_study")
        if study and show_frontage_study:
            overlay = _tag(group, "g", data_frontage_study=study["status"])
            for key, box, name, colour in [
                ("clear-route", study["route_mm"], f"{study['route_mm']['w_mm']/10:g}cm通行比較帶（未核）", "#287b89"),
                *((zone["id"], zone["geometry"], zone["name"], "#bf731b") for zone in study["zones"]),
            ]:
                footprint = _tag(
                    overlay,
                    "rect",
                    x=box["x_mm"],
                    y=box["y_mm"],
                    width=box["w_mm"],
                    height=box["h_mm"],
                    fill="none",
                    stroke=colour,
                    stroke_width=25,
                    stroke_dasharray="90 50",
                    data_study_zone=key,
                )
                _tag(footprint, "title").text = name
                _text(overlay, name[:8], box["x_mm"] + 70, box["y_mm"] + 220, font_size=145)
                _text(overlay, "未核" if key == "clear-route" else "未施作", box["x_mm"] + 70, box["y_mm"] + 410, font_size=145)
            _text(overlay, "私有前院條件未明：比較虛框非已擺放，騎樓／公共退縮適用即撤銷。", 140, 620, font_size=140)
        if not room["outdoor"]:
            for face in ("front", "rear", "left", "right"):
                along_x = face in {"front", "rear"}
                length = g["w_mm"] if along_x else g["h_mm"]
                cuts = []
                for opening in features["doors"] + features["open_connections"]:
                    if opening["face"] == face:
                        centre = opening["ratio"] * length
                        cuts.append(
                            (max(0, centre - opening["width_mm"] / 2), min(length, centre + opening["width_mm"] / 2))
                        )
                if features["window_face"] == face and features["window_mm"] < length - 200:
                    centre = length * features["window_ratio"]
                    cuts.append((centre - features["window_mm"] / 2, centre + features["window_mm"] / 2))

                def line(
                    lo: float,
                    hi: float,
                    colour: str = "#6b7274",
                    thickness: int = 100,
                    g: dict = g,
                    group: Element = group,
                    face: str = face,
                    along_x: bool = along_x,
                ) -> None:
                    if hi <= lo:
                        return
                    x = g["x_mm"] + (g["w_mm"] if face == "right" else 0)
                    y = g["y_mm"] + (g["h_mm"] if face == "rear" else 0)
                    _tag(
                        group,
                        "line",
                        x1=x + (lo if along_x else 0),
                        x2=x + (hi if along_x else 0),
                        y1=y + (0 if along_x else lo),
                        y2=y + (0 if along_x else hi),
                        stroke=colour,
                        stroke_width=thickness,
                        data_wall_face=face,
                    )

                breaks = sorted({0, length, *(n for pair in cuts for n in pair)})
                for lo, hi in zip(breaks, breaks[1:], strict=False):
                    if not any(a <= (lo + hi) / 2 <= b for a, b in cuts):
                        line(lo, hi)
                if features["window_face"] == face and features["window_mm"] < length - 200:
                    centre = length * features["window_ratio"]
                    line(centre - features["window_mm"] / 2, centre + features["window_mm"] / 2, "#3b7894", 45)
        for zone in features["reserved_mm"]:
            if zone["kind"] == "stairs":
                continue
            b = zone["aabb"]
            _tag(
                group,
                "rect",
                x=b["minX"],
                y=b["minY"],
                width=b["maxX"] - b["minX"],
                height=b["maxY"] - b["minY"],
                data_reserved=zone["kind"],
                **{"class": "allowance"},
            )
            if zone["kind"] == "care-turn":
                _tag(
                    group,
                    "circle",
                    cx=(b["minX"] + b["maxX"]) / 2,
                    cy=(b["minY"] + b["maxY"]) / 2,
                    r=min(b["maxX"] - b["minX"], b["maxY"] - b["minY"]) / 2,
                    data_care_turn="proposal-not-verified",
                    **{"class": "allowance"},
                )
                _text(group, "Ø150cm轉位暫留", b["minX"] + 100, b["maxY"] - 100, font_size=145)
        for door in features["doors"]:
            if door.get("operation") == "sliding":
                _tag(
                    group, "desc", data_door_operation="sliding"
                ).text = f"滑門提案，門寬暫估{door['width_mm']:g}mm；完成面淨寬未核。"
        if room["key"] == "garage" and building == "A" and any(i["category"] == "vehicle" for i in room["furniture"]):
            _tag(
                group,
                "rect",
                x=g["x_mm"] + (g["w_mm"] - 2500) / 2,
                y=g["y_mm"] + (g["h_mm"] - 5500) / 2,
                width=2500,
                height=5500,
                fill="none",
                stroke="#4c7a93",
                stroke_width=25,
                stroke_dasharray="90 50",
                data_parking_bay="size-screen-only",
            )
            _text(group, "2.5×5.5m 車位尺寸初篩", g["x_mm"] + 140, g["y_mm"] + g["h_mm"] - 140, font_size=170)
        stair = features.get("stair_footprint_mm")
        if stair:
            _tag(
                group,
                "rect",
                x=stair["x_mm"],
                y=stair["y_mm"],
                width=stair["w_mm"],
                height=stair["h_mm"],
                fill="#c5ceca",
                data_stairs="roof-arrival-not-verified"
                if features["stair_geometry"].get("connects_to_next_storey") is False
                else "two-flight-u-proposal-not-verified",
            )
            stair_geometry = features.get("stair_geometry", {})
            landing = stair_geometry.get("landing_mm", 0)
            run = stair_geometry.get("run_mm", stair["h_mm"])
            half = stair_geometry.get("risers", 16) // 2
            for i in range(1, half) if stair_geometry.get("connects_to_next_storey") is not False else ():
                y = stair["y_mm"] + landing + run * i / (half - 1)
                _tag(
                    group,
                    "line",
                    x1=stair["x_mm"],
                    x2=stair["x_mm"] + stair["w_mm"],
                    y1=y,
                    y2=y,
                    stroke="#62716f",
                    stroke_width=20,
                )
            _tag(
                group,
                "line",
                x1=stair["x_mm"] + stair["w_mm"] / 2,
                x2=stair["x_mm"] + stair["w_mm"] / 2,
                y1=stair["y_mm"] + landing,
                y2=stair["y_mm"] + landing + run,
                stroke="#62716f",
                stroke_width=80,
            )
            _text(
                group,
                "↓RF到達／下樓梯井" if stair_geometry.get("connects_to_next_storey") is False else "↑雙折梯↓（初排）",
                stair["x_mm"] + 80,
                stair["y_mm"] + stair["h_mm"] / 2,
                font_size=180,
            )
        for unit in features.get("hvac_units", []):
            w, d = unit["width_mm"], unit["depth_mm"]
            if unit["face"] in {"left", "right"}:
                w, d = d, w
            _tag(
                group,
                "rect",
                x=unit["x_mm"] - w / 2,
                y=unit["y_mm"] - d / 2,
                width=w,
                height=d,
                fill="#54a5bb",
                stroke="#14586c",
                stroke_width=20,
                data_hvac_id=unit["id"],
                data_hvac_type=unit["type"],
            )
            _text(
                group,
                unit["id"] + ("內" if unit["type"] == "indoor" else "外"),
                unit["x_mm"] + 100,
                unit["y_mm"] + 150,
                font_size=155,
            )
        for item in room["furniture"]:
            number += 1
            p = item["placement"]
            fg = _tag(
                group,
                "g",
                data_furniture_id=item["id"],
                data_status=p["status"],
                data_center_x_mm=p["center_x_mm"],
                data_center_y_mm=p["center_y_mm"],
                data_width_mm=item["width_mm"],
                data_depth_mm=item["depth_mm"],
                data_height_mm=item["height_mm"],
                data_rotation_deg=p["rotation_deg"],
                data_mount_height_mm=p["mount_height_mm"],
                data_wall_anchor=p["wall_anchor"],
            )
            _tag(fg, "title").text = (
                f"{number}. {item['label']} · {item['width_mm']:g}×{item['depth_mm']:g}×{item['height_mm']:g}mm"
                + (" · 待調整" if p["issues"] else " · 暫估")
            )
            if p["issues"]:
                continue  # HTML checklist retains exact dimensions and issues.
            op = p["operation_mm"]
            if op:
                _tag(
                    group,
                    "rect",
                    x=op["minX"],
                    y=op["minY"],
                    width=op["maxX"] - op["minX"],
                    height=op["maxY"] - op["minY"],
                    **{"class": "allowance"},
                )
            rear = p.get("rear_operation_mm")
            if rear:
                _tag(
                    group,
                    "rect",
                    x=rear["minX"],
                    y=rear["minY"],
                    width=rear["maxX"] - rear["minX"],
                    height=rear["maxY"] - rear["minY"],
                    **{"class": "allowance"},
                    data_maintenance="rear",
                )
            fg.set("transform", f"translate({p['center_x_mm']} {p['center_y_mm']}) rotate({-p['rotation_deg']})")
            w, d = item["width_mm"], item["depth_mm"]
            _tag(
                fg,
                "rect",
                x=-w / 2,
                y=-d / 2,
                width=w,
                height=d,
                rx=50,
                fill=item["color"],
                stroke="#37434c",
                stroke_width=15,
            )
            if item["shape"] == "bed":
                for x in (-w * 0.35, w * 0.05):
                    _tag(fg, "rect", x=x, y=d * 0.25, width=w * 0.3, height=d * 0.16, rx=35, fill="#f4f1e8")
            if p["wall_anchor"]:
                _tag(
                    fg,
                    "path",
                    d=f"M -100 {-d / 2 + 130} L 0 {-d / 2 + 30} L 100 {-d / 2 + 130}",
                    **{"class": "front-mark"},
                )
            _text(fg, str(number), 0, 70, transform=f"rotate({p['rotation_deg']})", **{"class": "item-number"})
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="unicode") + "\n"


def write_html_plans(payload: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    data = plan_data(payload)
    for building in data["buildings"]:
        for floor in building["floors"]:
            (directory / floor["plan_file"]).write_text(render_plan(building["id"], floor), encoding="utf-8")
            if floor.get("frontage_study_file"):
                (directory / floor["frontage_study_file"]).write_text(
                    render_plan(building["id"], floor, show_frontage_study=True), encoding="utf-8"
                )
    for building in data["facade"].get("buildings", []):
        (directory / building["elevation_file"]).write_text(render_elevation(data["facade"], building), encoding="utf-8")
    (directory / "layout.js").write_text(
        "window.HOUSE_CONCEPT_LAYOUT = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )

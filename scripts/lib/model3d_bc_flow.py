"""B ritual/transport and C open-living checks, not professional approval.

Derive annotations from actual openings and full-size placements. Storage
measurements never establish the assembled transport envelope or a rehearsal.
Historical comparisons without these obligations keep their own geometry.
"""

from __future__ import annotations

from pathlib import Path

from house_design.physical_items import PHYSICAL_ITEMS_PATH, load_physical_items
from lib.model3d_placement import INSET, overlaps
from lib.model3d_tour import _contacts


def _rooms(building: dict) -> dict:
    return {c["key"]: c for c in building["floors"][0]["cells"] if c.get("tour_active")}


def _centre(room: dict, door: dict) -> float:
    g = room["tour_mm"]
    axis, length = ("x_mm", "w_mm") if door["face"] in {"front", "rear"} else ("y_mm", "h_mm")
    return g[axis] + g[length] * door["ratio"]


def _b_flow(building: dict, physical_items_path: Path) -> dict:
    spec, cells = building["layout_review"]["ritual_access"], _rooms(building)

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError("B ritual/transport proposal: " + message)

    require(
        spec.get("status") == "owner-preference-proposal-not-verified"
        and spec.get("owner_requires_axial_front_door") is True
        and spec.get("religious_acceptance") == spec.get("transport_acceptance") == "unknown",
        "retain owner axial-door preference without inventing acceptance",
    )
    require(all(k in cells for k in ("garage", "shrine", "entry", "corridor1", "storage")), "missing route room")
    shrine = cells["shrine"]
    altar = next((i for i in shrine["furniture"] if i["shape"] == "altar"), None)
    require(altar is not None, "missing altar")
    ap = shrine["furniture_placements"]["tour_mm"][altar["id"]]
    require(not ap["issues"] and ap["wall_anchor"] == "rear", "altar must retain a usable rear-wall placement")
    front = [d for d in shrine["tour_features"]["doors"] if d.get("purpose") == "ritual-entry"]
    require(len(front) == 1, "missing or ambiguous front ritual door")
    door = front[0]
    require(
        door["face"] == "front"
        and door["neighbor"] == cells["garage"]["id"]
        and door["width_mm"] >= spec["front_door_width_mm"]
        and abs(_centre(shrine, door) - ap["center_x_mm"]) < 1,
        "front ritual door must face the frontage and align with the altar axis",
    )
    require(cells["garage"]["is_outdoor"] and not cells["garage"]["furniture"], "frontage must remain clear")
    worship_bands = [z["aabb"] for z in shrine["tour_features"]["reserved_mm"] if z["kind"] == "ritual-approach"]
    require(
        any(
            b["maxX"] - b["minX"] >= door["width_mm"]
            and b["maxY"] - b["minY"] >= 3200
            and abs((b["maxX"] + b["minX"]) / 2 - ap["center_x_mm"]) < 1
            for b in worship_bands
        ),
        "lost axial worship reservation",
    )
    for furniture in shrine["furniture"]:
        fp = shrine["furniture_placements"]["tour_mm"][furniture["id"]]
        require(
            not fp["issues"]
            and all(
                not overlaps(fp["aabb"], band) and not (fp["operation_mm"] and overlaps(fp["operation_mm"], band))
                for band in worship_bands
            ),
            "worship approach obstructed by furniture or operation",
        )
    ritual = {
        "status": "owner-preference-proposal-not-verified",
        "owner_requires_axial_front_door": True,
        "axis_x_mm": ap["center_x_mm"],
        "front_door_width_mm": door["width_mm"],
        "religious_acceptance": "unknown",
        "note": "依屋主家規在神桌正前方開門；不自動判為犯忌，也不代表風水已核定。門扇、路沖／坐向、節慶站跪、香火補氣與防雨防颱仍待確認。",
    }
    shrine["tour_features"]["ritual_access_review"] = ritual
    source = load_physical_items(physical_items_path)["by_id"]["B.palanquin.primary"]
    storage = cells["storage"]
    item = next((i for i in storage["furniture"] if i.get("physical_item_id") == source["id"]), None)
    require(item is not None, "missing inventory-linked palanquin")
    require(
        all(item[k] == source["active_dimensions"][k] for k in ("width_mm", "depth_mm", "height_mm")),
        "palanquin dimensions cannot diverge from the physical inventory",
    )
    p = storage["furniture_placements"]["tour_mm"][item["id"]]
    require(not p["issues"] and p["rotation_deg"] == 0, "storage body needs an unrotated full-size placement")
    require(storage["access_mode"] == "straight-pull", "do not substitute an untested indoor turn")
    axis, body_w = p["center_x_mm"], item["width_mm"]
    side_door = next((d for d in cells["entry"]["tour_features"]["doors"] if d["neighbor"] is None), None)
    storage_door = next((d for d in storage["tour_features"]["doors"] if d["face"] == "front"), None)
    require(side_door is not None and storage_door is not None, "missing exterior/storage gate")
    require(storage_door["neighbor"] == cells["corridor1"]["id"], "storage gate cannot enter through the shrine")
    gates = []
    for room, gate in ((cells["entry"], side_door), (storage, storage_door)):
        require(
            gate["face"] == "front" and abs(_centre(room, gate) - axis) < 1, "gates must share the straight-pull axis"
        )
        require(gate["width_mm"] >= body_w, "body wider than a proposed gate")
        gates.append(
            {
                "room_id": room["id"],
                "nominal_width_mm": gate["width_mm"],
                "body_side_margin_mm": (gate["width_mm"] - body_w) / 2,
            }
        )
    passage = next(
        (d for d in cells["entry"]["tour_features"]["open_connections"] if d["neighbor"] == cells["corridor1"]["id"]),
        None,
    )
    require(
        passage is not None and abs(_centre(cells["entry"], passage) - axis) < 1,
        "front and rear passage must join without a turn",
    )
    require(passage["width_mm"] >= body_w, "body wider than the shared passage")
    segments = []
    for key in ("garage", "entry", "corridor1", "storage"):
        room, g = cells[key], cells[key]["tour_mm"]
        end = p["aabb"]["minY"] if key == "storage" else g["y_mm"] + g["h_mm"]
        band = {"minX": axis - body_w / 2, "maxX": axis + body_w / 2, "minY": g["y_mm"], "maxY": end}
        inset = 0 if room["is_outdoor"] else INSET
        require(
            band["minX"] >= g["x_mm"] + inset and band["maxX"] <= g["x_mm"] + g["w_mm"] - inset,
            "body sweep exceeds the assumed clear corridor",
        )
        require(end >= g["y_mm"], "storage body blocks its entry")
        for other in room["furniture"]:
            if other["id"] == item["id"]:
                continue
            op = room["furniture_placements"]["tour_mm"][other["id"]]
            require(
                not overlaps(band, op["aabb"]) and not (op["operation_mm"] and overlaps(band, op["operation_mm"])),
                "fixed furniture or operation blocks the body sweep",
            )
        segments.append(
            {
                "room_id": room["id"],
                "centerline_mm": [[axis, g["y_mm"]], [axis, end]],
                "body_sweep_mm": band,
                "nominal_width_mm": g["w_mm"],
                "assumed_clear_width_mm": g["w_mm"] - 2 * inset,
            }
        )
    require(
        all(
            abs(a["centerline_mm"][-1][1] - b["centerline_mm"][0][1]) < 1
            for a, b in zip(segments, segments[1:], strict=False)
        ),
        "route segments are not continuous",
    )
    transport = source.get("transport", {})
    # Even a measured storage body is not a measured assembled/pole envelope.
    route = {
        "status": "storage-body-sweep-only-not-transport-approval",
        "physical_item_id": source["id"],
        "storage_dimensions": source["active_dimensions"],
        "storage_dimension_source": source["active_dimension_source"],
        "assembled_dimensions": transport.get("assembled_dimensions"),
        "assembled_measurement": transport.get("assembled_measurement", {"status": "unknown", "source": None}),
        "route_rehearsal": transport.get("route_rehearsal", {"status": "unknown", "source": None}),
        "carrying_poles_removable": transport.get("carrying_poles_removable"),
        "transport_acceptance": "unknown",
        "axis_x_mm": axis,
        "gates": gates,
        "segments": segments,
        "assumed_inset_mm": INSET,
        "bottleneck_assumed_width_mm": min(
            [g["nominal_width_mm"] for g in gates] + [s["assumed_clear_width_mm"] for s in segments]
        ),
        "note": "門外通行帶 → 150cm搬轎側門 → 前後1.6m名義通道 → 150cm收納門 → 武轎位；不穿神明堂、不在室內轉向。只初篩收納本體，拆桿／裝桿、輪具高度、人員、門框／門扇、坡度高差及雨天演練未核。騎樓不能當已核准裝桿場。",
    }
    for segment in segments:
        room = next(c for c in cells.values() if c["id"] == segment["room_id"])
        room["tour_features"]["transport_review"] = route
        room["tour_features"]["transport_segment_mm"] = segment
    return {
        "id": "B-ritual-and-transport-flow",
        "status": "proposal-geometric-screen-only",
        "ritual": ritual,
        "transport": route,
    }


def _c_open_living(building: dict) -> dict:
    spec, cells = building["layout_review"]["open_living"], _rooms(building)

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError("C open living proposal: " + message)

    keys = ["entrance", "dining", "living"]
    require(
        spec.get("status") == "open-zones-proposal-not-verified"
        and spec.get("room_keys") == keys
        and all(spec.get(k) == "unknown" for k in ("structural_acceptance", "fire_acceptance", "daylight_acceptance")),
        "no false structural, fire or daylight acceptance",
    )
    require(all(k in cells and cells[k]["space_group"] == spec["group"] for k in keys), "missing shared open-plan zone")
    for i, key in enumerate(keys):
        room = cells[key]
        for other_key in keys[i + 1 :]:
            other = cells[other_key]
            for a, b in ((room, other), (other, room)):
                contact = _contacts(a["tour_mm"], b["tour_mm"])
                require(contact is not None, "open zones no longer share a boundary")
                face, lo, hi = contact
                opens = [o for o in a["tour_features"]["open_connections"] if o["neighbor"] == b["id"]]
                require(
                    len(opens) == 1
                    and opens[0]["face"] == face
                    and abs(opens[0]["width_mm"] - (hi - lo)) < 1
                    and abs(_centre(a, opens[0]) - (lo + hi) / 2) < 1,
                    "a partition remains between open zones",
                )
                require(
                    not any(d["neighbor"] == b["id"] for d in a["tour_features"]["doors"]),
                    "fake door between open zones",
                )
    geometries = [cells[k]["tour_mm"] for k in keys]
    x0, y0 = min(g["x_mm"] for g in geometries), min(g["y_mm"] for g in geometries)
    w = max(g["x_mm"] + g["w_mm"] for g in geometries) - x0
    h = max(g["y_mm"] + g["h_mm"] for g in geometries) - y0
    require(
        sum(g["w_mm"] * g["h_mm"] for g in geometries) == w * h and y0 >= 3900,
        "open zones cannot enclose the reserved frontage or leave an unexplained gap",
    )
    items = [
        (r, i, r["furniture_placements"]["tour_mm"][i["id"]]) for r in (cells[k] for k in keys) for i in r["furniture"]
    ]
    for index, (_, _, p) in enumerate(items):
        require(not p["issues"], "unplaced product cannot prove the open-plan function")
        for _, _, other in items[index + 1 :]:
            require(
                not overlaps(p["aabb"], other["aabb"])
                and not (p["operation_mm"] and overlaps(p["operation_mm"], other["aabb"]))
                and not (other["operation_mm"] and overlaps(p["aabb"], other["operation_mm"])),
                "cross-zone furniture/operation conflict",
            )
    lounge = cells["living"]
    sofa_item = next((i for i in lounge["furniture"] if i["id"].endswith(":sofa")), None)
    table_item = next((i for i in cells["dining"]["furniture"] if i["shape"] == "dining-set"), None)
    require(
        sofa_item is not None and sofa_item["width_mm"] >= 1800 and sofa_item["depth_mm"] >= 900,
        "normal sofa cannot be reduced to prove a fit",
    )
    require(
        table_item is not None
        and table_item["width_mm"] >= 1800
        and table_item["depth_mm"] >= 1800
        and table_item.get("table_width_mm", 0) >= 1200
        and table_item.get("table_depth_mm", 0) >= 800,
        "retain the full-size four-seat table/chair envelope",
    )
    placements = lounge["furniture_placements"]["tour_mm"]
    sofa, tv, table = [placements[lounge["id"] + ":furniture:" + k] for k in ("sofa", "tv", "coffee-table")]
    require(
        not sofa["wall_anchor"]
        and sofa["rotation_deg"] == 90
        and tv["wall_anchor"] == "left"
        and sofa["center_y_mm"] == tv["center_y_mm"] == table["center_y_mm"]
        and sofa["aabb"]["minX"] - table["aabb"]["maxX"] == 400,
        "TV must mount on a retained wall and face the sofa, not the removed dining wall",
    )
    check = {
        "id": "C-open-living-dining",
        "status": "open-zones-proposal-not-verified",
        "group": spec["group"],
        "room_ids": [cells[k]["id"] for k in keys],
        "geometry": {"x_mm": x0, "y_mm": y0, "w_mm": w, "h_mm": h},
        "allocation_area_sqm": w * h / 1e6,
        "living_dining_area_sqm": sum(
            cells[k]["tour_mm"]["w_mm"] * cells[k]["tour_mm"]["h_mm"] for k in ("dining", "living")
        )
        / 1e6,
        "added_floor_area_sqm": 0,
        "structural_acceptance": "unknown",
        "fire_acceptance": "unknown",
        "daylight_acceptance": "unknown",
        "note": "玄關、四人餐桌与客廳是同一6×5.6m開放空間的功能分區，非三間隔間。客餐分配27.2m²、連玄關33.6m²，不是完成面淨面積或新增樓地板；150cm轉位、採光、冷房、結構與樓梯消防仍待核。",
    }
    for key in keys:
        cells[key]["tour_features"]["open_living_review"] = check
    return check


def build_bc_flow_checks(buildings: list[dict], physical_items_path: Path = PHYSICAL_ITEMS_PATH) -> list[dict]:
    checks = []
    for building in buildings:
        if building["id"] == "B" and "ritual_access" in building["layout_review"]:
            checks.append(_b_flow(building, physical_items_path))
        if building["id"] == "C" and "open_living" in building["layout_review"]:
            checks.append(_c_open_living(building))
    return checks

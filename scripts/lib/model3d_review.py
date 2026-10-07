"""Versioned, bounded discussion proposals, kept apart from surveyed inputs.

Neither a packing success nor a doorway graph is professional approval. The
proposal never expands a frame, overwrites dimensions.json or resolves an
owner requirement merely by leaving it out of the displayed design.
"""

from __future__ import annotations

import copy
import json
import math
from collections import deque
from pathlib import Path
from typing import Any

REVIEW_FILE = Path(__file__).resolve().parents[2] / "inputs/concept-layout-review.json"
STATUS = "bounded-proposal-not-authoritative"


def _box(rect: Any, context: str) -> dict[str, float]:
    if not isinstance(rect, list) or len(rect) != 4:
        raise ValueError(f"{context}: expected [x,y,width,depth]")
    if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in rect):
        raise ValueError(f"{context}: finite dimensions required")
    if min(rect[:2]) < 0 or min(rect[2:]) <= 0:
        raise ValueError(f"{context}: negative origin or non-positive size")
    return dict(zip(("x_mm", "y_mm", "w_mm", "h_mm"), rect, strict=True))


def frontage_study(cell: dict) -> dict | None:
    """Conditional comparison footprints, never installed furniture or land rights."""
    raw = cell.get("review_spec", {}).get("frontage_study")
    if raw is None:
        return None
    if (
        not cell["is_outdoor"]
        or not cell["review_spec"].get("clear")
        or raw.get("status") != "conditional-not-installed"
        or raw.get("active_option") != "keep-full-clear"
        or raw.get("site_use_status") != "unknown"
        or not raw.get("conditions")
        or cell.get("furniture")
    ):
        raise ValueError(f"Frontage study must keep the unknown frontage clear: {cell['id']}")
    g = cell["tour_mm"]

    def bounds(rect: list) -> dict:
        box = _box(rect, f"{cell['id']} frontage study")
        if box["x_mm"] + box["w_mm"] > g["w_mm"] or box["y_mm"] + box["h_mm"] > g["h_mm"]:
            raise ValueError(f"Frontage study exceeds proposed frontage: {cell['id']}")
        return {
            "x_mm": g["x_mm"] + box["x_mm"],
            "y_mm": g["y_mm"] + box["y_mm"],
            "w_mm": box["w_mm"],
            "h_mm": box["h_mm"],
        }

    def intersects(a: dict, b: dict) -> bool:
        return max(a["x_mm"], b["x_mm"]) < min(a["x_mm"] + a["w_mm"], b["x_mm"] + b["w_mm"]) and max(
            a["y_mm"], b["y_mm"]
        ) < min(a["y_mm"] + a["h_mm"], b["y_mm"] + b["h_mm"])

    study = copy.deepcopy(raw)
    study["route_mm"] = bounds(raw["route_rect"])
    occupied = [study["route_mm"]]
    ids = set()
    for zone in study["zones"]:
        height = zone.get("height_mm")
        if not zone.get("id") or zone["id"] in ids or isinstance(height, bool) or not isinstance(height, (int, float)):
            raise ValueError(f"Invalid frontage study zone: {cell['id']}")
        if not math.isfinite(height) or height <= 0:
            raise ValueError(f"Invalid frontage study height: {cell['id']}")
        zone["geometry"] = bounds(zone["rect"])
        if any(intersects(zone["geometry"], box) for box in occupied):
            raise ValueError(f"Frontage study blocks route or another zone: {cell['id']}")
        occupied.append(zone["geometry"])
        ids.add(zone["id"])
    return study


def prepare_review(buildings: list[dict], path: Path = REVIEW_FILE) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != "house-bounded-concept-v1":
        raise ValueError("Unsupported bounded concept schema")
    frame = _box([0, 0, *raw["frame_mm"]], "frame")
    for building in buildings:
        spec = raw["buildings"][building["id"]]
        building["layout_review"] = {k: copy.deepcopy(v) for k, v in spec.items() if k != "floors"}
        for floor in building["floors"]:
            proposal = spec["floors"][floor["id"]]
            floor["layout_review"] = copy.deepcopy(proposal)
            floor["review_core"] = copy.deepcopy(spec["core"])
            floor["tour_width_mm"], floor["tour_depth_mm"] = frame["w_mm"], frame["h_mm"]
            known = {c["key"]: c for c in floor["cells"]}
            for key, room in proposal["rooms"].items():
                g = _box(room["rect"], f"{building['id']} {floor['id']} {key}")
                if g["x_mm"] + g["w_mm"] > frame["w_mm"] or g["y_mm"] + g["h_mm"] > frame["h_mm"]:
                    raise ValueError(f"Proposal exceeds fixed frame: {key}")
                if key not in known:
                    cell = {
                        "id": f"{building['id']}:{floor['id']}:{key}",
                        "key": key,
                        "order": len(known),
                        "name": room["name"],
                        "icon": "",
                        "kind": "other",
                        "color": "#94a3b8",
                        "size_text": "有界提案，非實測",
                        **g,
                        "declared_mm": copy.deepcopy(g),
                        "auto_mm": copy.deepcopy(g),
                        "provenance": "auto",
                        "is_outdoor": False,
                        "is_entry": False,
                        "room_role": "unknown",
                        "space_group": "",
                        "space_role": "",
                        "carry_path_mm": 0,
                        "access_mode": "",
                        "door_contact_ratio": None,
                        "zone": "unknown",
                        "facing": "unknown",
                        "area_sqm": g["w_mm"] * g["h_mm"] / 1e6,
                        "area_ping": 0,
                        "declared_sqm": None,
                        "door_mm": 900,
                        "window_mm": 1200,
                        "opening_face": "north",
                        "opening_face_source": "proposal",
                        "badges": [],
                        "hvac": {"indoor": False, "outdoor": False, "evidence": []},
                        "room_uid": "",
                        "proposal_only": True,
                    }
                    known[key] = cell
                    floor["cells"].append(cell)
                cell = known[key]
                cell["source_name"] = cell["name"]
                cell["name"] = room["name"]
                cell["tour_mm"] = g
                cell["tour_active"] = True
                cell["review_spec"] = copy.deepcopy(room)
                cell["kind"] = room.get("kind", cell["kind"])
                cell["room_role"] = room.get("room_role", cell["room_role"])
                cell["space_group"] = room.get("group", "")
                cell["space_role"] = room.get("role", "circulation" if room.get("group") else "")
                cell["is_outdoor"] = room.get("outdoor", cell["is_outdoor"])
                cell["is_entry"] = bool(proposal.get("entry") and proposal["entry"][0] == key)
                for field in ("door_mm", "window_mm", "carry_path_mm", "access_mode"):
                    if field in room:
                        cell[field] = room[field]
                if "kind" in room:
                    cell["color"] = {
                        "stair": "#b0bec5",
                        "outdoor": "#98b99a",
                        "other": "#d4ddd5",
                        "living": "#69a79b",
                        "service": "#90a4ae",
                        "entry": "#e0c99d",
                    }.get(cell["kind"], cell["color"])
            floor["deferred_rooms"] = []
            for key, cell in known.items():
                if key not in proposal["rooms"]:
                    cell["tour_active"] = False
                    cell["tour_mm"] = copy.deepcopy(cell["auto_mm"])
                    detail = next(
                        (d for d in spec["deferred"] if d.get("key") == key and d.get("floor") == floor["id"]), None
                    )
                    floor["deferred_rooms"].append(
                        {
                            "id": cell["id"],
                            "key": key,
                            "name": cell["name"],
                            "note": (detail or {}).get(
                                "note", "原獨立空間在有界提案尚未容納；需求保留，不以擴大外框假裝完成。"
                            ),
                        }
                    )
            active = [c for c in floor["cells"] if c["tour_active"]]
            for i, cell in enumerate(active):
                a = cell["tour_mm"]
                for other in active[i + 1 :]:
                    b = other["tour_mm"]
                    if max(a["x_mm"], b["x_mm"]) < min(a["x_mm"] + a["w_mm"], b["x_mm"] + b["w_mm"]) and max(
                        a["y_mm"], b["y_mm"]
                    ) < min(a["y_mm"] + a["h_mm"], b["y_mm"] + b["h_mm"]):
                        raise ValueError(f"Overlapping proposal rooms: {cell['id']} / {other['id']}")
    return {k: copy.deepcopy(v) for k, v in raw.items() if k != "buildings"}


def proposal_features(floor: dict) -> None:
    # Lazy import avoids a module cycle and reuses the exact adjacency convention.
    from lib.model3d_tour import _common_access, _contacts

    inverse = {"front": "rear", "rear": "front", "left": "right", "right": "left"}
    cells = {c["key"]: c for c in floor["cells"] if c.get("tour_active", True)}
    for cell in floor["cells"]:
        features = cell["tour_features"]
        features["doors"], features["open_connections"] = [], []
        features["stairs"] = cell.get("tour_active", True) and cell["kind"] == "stair"
        features["window_face"] = None
        features["window_pending"] = "側界可能共壁；只有前後外側才畫候選窗。合法採光／通風及神桌實牆待核。"
        features["hvac"] = {"indoor": False, "outdoor": False, "evidence": cell.get("hvac", {}).get("evidence", [])}
        features["hvac_units"] = []
        features["fixed_reserved_mm"] = []
        g = cell["tour_mm"]
        spec = cell.get("review_spec", {})
        study = frontage_study(cell) if cell.get("tour_active") else None
        if study:
            features["frontage_study"] = study
        if cell.get("tour_active") and not cell["is_outdoor"] and cell["window_mm"]:
            faces = {"front": g["y_mm"] == 0, "rear": g["y_mm"] + g["h_mm"] == floor["tour_depth_mm"]}
            # Front/rear service balconies are exterior proposals too, not legal
            # opening evidence. Do not infer side windows on neighboring parcels.
            for other in cells.values():
                contact = _contacts(g, other["tour_mm"])
                if contact and other["is_outdoor"] and contact[0] in faces:
                    faces[contact[0]] = True
            preferred = spec.get("window_face")
            features["window_face"] = (
                preferred if faces.get(preferred) else next((face for face in ("rear", "front") if faces[face]), None)
            )
            if "神明" in cell["name"] and features["window_face"] == "rear":
                features["window_face"] = None
        features["window_ratio"] = spec.get("window_ratio", 0.5)
        features["window_sill_mm"] = 2100 if cell["kind"] == "bath" else 900
        features["window_height_mm"] = 500 if cell["kind"] == "bath" else 1200
        for reservation in spec.get("clearance_reservations", []):
            box = _box(reservation["rect"], f"{cell['id']} clearance")
            if box["x_mm"] + box["w_mm"] > g["w_mm"] or box["y_mm"] + box["h_mm"] > g["h_mm"]:
                raise ValueError(f"Clearance exceeds proposed room: {cell['id']}")
            features["fixed_reserved_mm"].append(
                {
                    "kind": reservation["kind"],
                    "aabb": {
                        "minX": g["x_mm"] + box["x_mm"],
                        "maxX": g["x_mm"] + box["x_mm"] + box["w_mm"],
                        "minY": g["y_mm"] + box["y_mm"],
                        "maxY": g["y_mm"] + box["y_mm"] + box["h_mm"],
                    },
                }
            )
        if features["stairs"]:
            core = floor["review_core"]
            width, tread, landing = 1000, 270, 1000
            risers = math.ceil(floor["height_mm"] / 180)
            risers += risers % 2
            run = (risers // 2 - 1) * tread
            stair_w, stair_d = width * 2 + 200, run + landing * 2
            side = core["flight_side"]
            x = g["x_mm"] + (80 if side == "left" else g["w_mm"] - stair_w - 80)
            features["stair_footprint_mm"] = {"x_mm": x, "y_mm": g["y_mm"] + 70, "w_mm": stair_w, "h_mm": stair_d}
            features["stair_geometry"] = {
                "type": "two-flight-u-proposal",
                "connects_to_next_storey": floor["id"] != "floor-4",
                "risers": risers,
                "riser_mm": round(floor["height_mm"] / risers, 2),
                "tread_mm": tread,
                "flight_width_mm": width,
                "landing_mm": landing,
                "run_mm": run,
                "fits_reserved_box": stair_w + 160 <= g["w_mm"] and stair_d + 140 <= g["h_mm"],
                "note": "兩折梯與平台僅初排；完成面淨寬、扶手、結構、梯井、淨高、消防分隔及屋突資格未核。",
            }
        route = spec.get("route_width_mm")
        if route:
            features["fixed_reserved_mm"].append(
                {
                    "kind": "circulation",
                    "aabb": {
                        "minX": g["x_mm"],
                        "maxX": g["x_mm"] + g["w_mm"],
                        "minY": g["y_mm"],
                        "maxY": g["y_mm"] + g["h_mm"],
                    },
                }
            )
        if cell["key"] == "elder" and cell["id"].startswith("C:"):
            features["fixed_reserved_mm"].extend(
                [
                    {
                        "kind": "care-route",
                        "aabb": {
                            "minX": g["x_mm"] + g["w_mm"] - 1200,
                            "maxX": g["x_mm"] + g["w_mm"],
                            "minY": g["y_mm"],
                            "maxY": g["y_mm"] + g["h_mm"],
                        },
                    },
                    {
                        "kind": "care-turn",
                        "aabb": {
                            "minX": g["x_mm"] + g["w_mm"] - 1500,
                            "maxX": g["x_mm"] + g["w_mm"],
                            "minY": g["y_mm"] + 900,
                            "maxY": g["y_mm"] + 2400,
                        },
                    },
                ]
            )
    graph: dict[str, list[str]] = {key: [] for key in cells}
    for a_key, b_key, opening, *coordinate in floor["layout_review"].get("connections", []):
        a, b = cells[a_key], cells[b_key]
        contact = _contacts(a["tour_mm"], b["tour_mm"])
        if contact is None:
            raise ValueError(f"Nonadjacent proposed opening: {a['id']} / {b['id']}")
        face, lo, hi = contact
        is_open = opening == "open" or isinstance(opening, dict) and opening.get("type") == "open"
        width = opening["width_mm"] if isinstance(opening, dict) else hi - lo if is_open else opening
        centre = (lo + hi) / 2 if not coordinate else coordinate[0]
        if width <= 0 or centre - width / 2 < lo or centre + width / 2 > hi:
            raise ValueError(f"Proposed opening exceeds shared wall: {a['id']} / {b['id']}")
        for room, side, other in ((a, face, b), (b, inverse[face], a)):
            g = room["tour_mm"]
            axis, length = ("x_mm", "w_mm") if side in {"front", "rear"} else ("y_mm", "h_mm")
            item = {
                "face": side,
                "ratio": round((centre - g[axis]) / g[length], 6),
                "width_mm": width,
                "neighbor": other["id"],
                "status": "explicit-bounded-proposal-not-verified",
                "operation": a.get("review_spec", {}).get("door_operation")
                or b.get("review_spec", {}).get("door_operation", "unconfirmed"),
            }
            room["tour_features"]["open_connections" if is_open else "doors"].append(item)
        graph[a_key].append(b_key)
        graph[b_key].append(a_key)
    entry = floor["layout_review"].get("entry")
    roots = [entry[0]] if entry else [key for key, cell in cells.items() if cell["tour_features"]["stairs"]]
    if entry:
        key, face, width, centre = entry
        cell, g = cells[key], cells[key]["tour_mm"]
        axis, length = ("x_mm", "w_mm") if face in {"front", "rear"} else ("y_mm", "h_mm")
        if centre - width / 2 < g[axis] or centre + width / 2 > g[axis] + g[length]:
            raise ValueError(f"Entry exceeds wall: {cell['id']}")
        cell["tour_features"]["doors"].append(
            {
                "face": face,
                "ratio": (centre - g[axis]) / g[length],
                "width_mm": width,
                "neighbor": None,
                "status": "external-entry-proposal-not-verified",
            }
        )
    reached, queue = set(roots), deque(roots)
    while queue:
        key = queue.popleft()
        for neighbor in graph[key]:
            if neighbor not in reached and _common_access(cells[neighbor]) and "神明" not in cells[neighbor]["name"]:
                reached.add(neighbor)
                queue.append(neighbor)
    for key, cell in cells.items():
        direct = key in reached or any(n in reached for n in graph[key])
        # Ensuite exception is a destination, never a common through-route.
        ensuite = cell["kind"] == "bath" and any(
            any(n in reached for n in graph[p])
            for p in graph[key]
            if cells[p]["kind"] == "bedroom" or cells[p].get("room_role") == "elder"
        )
        cell["tour_features"]["access_pending"] = not (direct or ensuite or cell["is_outdoor"])
        cell["tour_features"]["access_reason"] = (
            "公共區相鄰／套衛提案；非已驗證通行。梯段、門扇、轉位、雨天及完成面淨空待核。"
        )


def review_checks(buildings: list[dict], requirements_path: Path | None = None) -> list[dict]:
    from lib.model3d_functions import REQUIREMENTS_FILE, check_a_care_functions

    checks = []
    b = next(building for building in buildings if building["id"] == "B")
    shrine = next(c for c in b["floors"][0]["cells"] if c["key"] == "shrine")["tour_mm"]
    for floor in b["floors"][1:]:
        for cell in floor["cells"]:
            if not cell.get("tour_active"):
                continue
            g = cell["tour_mm"]
            intersects = max(shrine["x_mm"], g["x_mm"]) < min(
                shrine["x_mm"] + shrine["w_mm"], g["x_mm"] + g["w_mm"]
            ) and max(shrine["y_mm"], g["y_mm"]) < min(shrine["y_mm"] + shrine["h_mm"], g["y_mm"] + g["h_mm"])
            hazard = cell["kind"] in {"bath", "kitchen", "stair"} or any(
                s in cell["name"] for s in ("KTV", "水塔", "加壓", "熱泵")
            )
            if intersects and hazard:
                raise ValueError(f"B shrine projection contains proposed wet/noisy/equipment use: {cell['id']}")
    checks.append(
        {
            "id": "B-shrine-projection",
            "status": "proposal-geometric-screen-only",
            "note": "全層用途初篩避開濕區、樓梯、KTV及屋頂設備；梁、管線與宗教坐向未查。",
        }
    )
    for building in buildings:
        stairs = [
            c["tour_features"].get("stair_footprint_mm")
            for f in building["floors"]
            for c in f["cells"]
            if c.get("tour_active") and c["tour_features"]["stairs"]
        ]
        if len(stairs) != len(building["floors"]) or any(s != stairs[0] for s in stairs):
            raise ValueError(f"Unaligned proposed stair core: {building['id']}")
        checks.append(
            {
                "id": f"{building['id']}-stair-stack",
                "status": "proposal-geometric-screen-only",
                "note": "同軸雙折梯初排；淨高、扶手、梯井、結構與消防仍待核。",
            }
        )
    checks.append(check_a_care_functions(buildings, requirements_path or REQUIREMENTS_FILE))
    return checks


def attach_hvac_proposals(buildings: list[dict]) -> list[dict]:
    """Paired ordinary split-system candidates, not a manufacturer sizing result.

    Length follows an orthogonal HIGH-LEVEL route to the front/rear facade,
    then an exterior vertical route, never the straight-line chord. Actual
    bends, minimum pipe length and additions remain installer tasks.
    """
    routes = []
    candidates = {b["id"]: b["layout_review"]["hvac_pairs"] for b in buildings}
    for building in buildings:
        floors = {f["id"]: f for f in building["floors"]}
        by_floor = {fid: {c["key"]: c for c in f["cells"]} for fid, f in floors.items()}
        used: dict[tuple[str, str], list[float]] = {}
        for ordinal, (fid, key, target_fid, target_key, facade) in enumerate(candidates[building["id"]], 1):
            cell, target = by_floor[fid][key], by_floor[target_fid][target_key]
            if (
                facade not in {"front", "rear"}
                or not cell.get("tour_active")
                or not target.get("tour_active")
                or not target["is_outdoor"]
            ):
                raise ValueError(f"Invalid AC facade / active outdoor target: {cell['id']} / {target['id']}")
            g, tg = cell["tour_mm"], target["tour_mm"]
            pair_id = f"{building['id']}-AC{ordinal:02d}"
            # Mount on a solid wall, not a room-wide open-plan connection.
            order = (facade, "right", "left", "rear" if facade == "front" else "front")
            wall, ratio = None, None
            for face in order:
                along_x = face in {"front", "rear"}
                length = g["w_mm"] if along_x else g["h_mm"]
                for position in (0.7, 0.5, 0.3) if facade == "rear" else (0.3, 0.5, 0.7):
                    centre = length * position
                    if centre - 500 < 80 or centre + 500 > length - 80:
                        continue
                    openings = cell["tour_features"]["doors"] + cell["tour_features"]["open_connections"]
                    if any(
                        o["face"] == face and abs(o["ratio"] * length - centre) < (o["width_mm"] + 1000) / 2
                        for o in openings
                    ):
                        continue
                    wall, ratio = face, position
                    break
                if wall:
                    break
            if wall is None:
                raise ValueError(f"No solid wall for indoor AC proposal: {cell['id']}")
            x = g["x_mm"] + (
                g["w_mm"] * ratio if wall in {"front", "rear"} else 150 if wall == "left" else g["w_mm"] - 150
            )
            y = g["y_mm"] + (
                g["h_mm"] * ratio if wall in {"left", "right"} else 150 if wall == "front" else g["h_mm"] - 150
            )
            bank = used.setdefault((target_fid, target_key), [])
            lo, hi = tg["x_mm"] + 530, tg["x_mm"] + tg["w_mm"] - 530
            total = sum(1 for _, _, tf, tk, _ in candidates[building["id"]] if (tf, tk) == (target_fid, target_key))
            pool = {lo + n * (hi - lo) / (total - 1) for n in range(total)} if total > 1 else {min(hi, max(lo, x))}
            xs = sorted(pool, key=lambda v: abs(v - x))
            ox = next((v for v in xs if all(abs(v - previous) >= 1100 for previous in bank)), None)
            if ox is None:
                raise ValueError(f"Outdoor AC bank exceeds target: {target['id']}")
            bank.append(ox)
            oy = tg["y_mm"] + (275 if facade == "front" else tg["h_mm"] - 275)
            iz, oz = floors[fid]["base_mm"] + 2350, floors[target_fid]["base_mm"] + 500
            # Out to the selected building facade at ceiling height first,
            # then a same-facade riser. Roof equipment is not an automatic default.
            edge_y = (
                (tg["y_mm"] + tg["h_mm"] if facade == "front" else tg["y_mm"])
                if fid == target_fid
                else 0
                if facade == "front"
                else floors[fid]["tour_depth_mm"]
            )
            service_z = floors[target_fid]["base_mm"] + 2350
            # Traverse the target equipment area high, then drop at the unit;
            # a low-level chord across roof tanks/heat pumps isn't a pipe route.
            points = [
                [x, y, iz],
                [x, edge_y, iz],
                [ox, edge_y, iz],
                [ox, edge_y, service_z],
                [ox, oy, service_z],
                [ox, oy, oz],
            ]
            base_length = sum(sum(abs(a[i] - b[i]) for i in range(3)) for a, b in zip(points, points[1:], strict=False))
            route = {
                "id": pair_id,
                "indoor_room": cell["id"],
                "outdoor_room": target["id"],
                "status": "unverified-model-and-route",
                "facade": facade,
                "polyline_mm": points,
                "estimated_routed_length_mm": round(base_length + 1000),
                "bend_service_allowance_mm": 1000,
                "elevation_difference_mm": abs(oz - iz),
                "model": None,
                "manual_source": None,
                "max_pipe_length_mm": None,
                "min_pipe_length_mm": None,
                "max_elevation_mm": None,
                "additional_refrigerant_g": None,
                "compliance": "unknown",
                "drainage": "室內機冷凝水另走可檢修重力排水至合法排水點；與冷媒路徑分開核對，不靠室外機位置證明排水。",
                "maintenance": "室外機通風／熱回流、防颱固定、避鄰噪音、端子與閥側維修、排水和運入更換待原廠圖核對。",
                "note": "折線長度是提案量，不是實測或安裝許可；穿牆／梁／防火、實際彎頭及最短管長仍未知。代表機身尺寸非選定產品。",
                "routing_height_note": "設備區高位路徑暫估高2350mm後再降至閥側；屋頂支架、防曬保溫、抗風及實際干涉須機電設計核對。",
            }
            routes.append(route)
            for room, kind, px, py, pz, face in (
                (cell, "indoor", x, y, 2350, wall),
                (target, "outdoor", ox, oy, 100, facade),
            ):
                room["tour_features"]["hvac"][kind] = True
                room["tour_features"]["hvac_units"].append(
                    {
                        "id": pair_id,
                        "type": kind,
                        "x_mm": px,
                        "y_mm": py,
                        "mount_height_mm": pz,
                        "face": face,
                        "width_mm": 950 if kind == "indoor" else 900,
                        "depth_mm": 280 if kind == "indoor" else 350,
                        "height_mm": 280 if kind == "indoor" else 800,
                        "route": route,
                    }
                )
            target["tour_features"]["fixed_reserved_mm"].append(
                {
                    "kind": "hvac-service",
                    "aabb": {
                        "minX": ox - 450,
                        "maxX": ox + 450,
                        "minY": oy - 175 if facade == "front" else oy - 1175,
                        "maxY": oy + 1175 if facade == "front" else oy + 175,
                    },
                }
            )
    return routes

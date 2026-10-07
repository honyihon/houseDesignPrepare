"""Shared conceptual whole-floor geometry; never overwrites surveyed geometry."""

from __future__ import annotations

import copy
import re
from collections import deque
from typing import Any


def attach_tour(buildings: list[dict[str, Any]]) -> None:
    from lib.model3d_review import STATUS, proposal_features

    for building in buildings:
        for floor in building["floors"]:
            cells = floor["cells"]
            # No capacity padding. A furniture conflict must stay a conflict,
            # rather than silently stretching the house to satisfy demand.
            if "layout_review" not in floor:
                for cell in cells:
                    cell["tour_mm"] = copy.deepcopy(cell["auto_mm"])
                floor["tour_width_mm"] = floor["auto_width_mm"]
                floor["tour_depth_mm"] = floor["auto_depth_mm"]
            floor["tour_status"] = STATUS
            for geometry_key, feature_key, width, depth in (
                ("tour_mm", "tour_features", floor["tour_width_mm"], floor["tour_depth_mm"]),
                ("auto_mm", "architecture_auto", floor["auto_width_mm"], floor["auto_depth_mm"]),
                ("declared_mm", "architecture_declared", floor["width_mm"], floor["depth_mm"]),
            ):
                for cell in cells:
                    cell[feature_key] = {
                        "status": "illustrative-pending-professional-review",
                        "geometry_source": geometry_key,
                        "doors": [],
                        "open_connections": [],
                        "space_group": cell.get("space_group", ""),
                        "space_role": cell.get("space_role", ""),
                        "window_face": None,
                        "window_ratio": 0.2
                        if cell.get("space_role") == "circulation-equipment" or "茶水吧" in cell["name"]
                        else 0.5,
                        "stairs": cell["kind"] == "stair" or bool(re.search(r"樓梯|梯間", cell["name"])),
                        "stair_geometry_verified": False,
                        "access_pending": not cell["is_outdoor"],
                        "access_reason": "No suitable common-space adjacency; doorway/corridor needs professional layout.",
                        "hvac": cell.get("hvac", {}),
                    }
                if geometry_key == "tour_mm" and "layout_review" in floor:
                    proposal_features(floor)
                    continue
                _openings([c for c in cells if not c.get("proposal_only")], width, depth, geometry_key, feature_key)
                for cell in cells:
                    features, g = cell[feature_key], cell[geometry_key]
                    if features["stairs"]:
                        w, h = min(g["w_mm"] * 0.5, 1200), min(g["h_mm"] * 0.7, 2600)
                        # C's cabinet and stair symbol share a cell. Reserve
                        # the left side for the symbol, right side for IDF.
                        ratio = 0.3 if any(i["category"] == "network" for i in cell.get("furniture", [])) else 0.5
                        features["stair_footprint_mm"] = {
                            "x_mm": round(g["x_mm"] + g["w_mm"] * ratio - w / 2, 1),
                            "y_mm": round(g["y_mm"] + (g["h_mm"] - h) / 2, 1),
                            "w_mm": round(w, 1),
                            "h_mm": round(h, 1),
                        }


def _contacts(a: dict, b: dict) -> tuple[str, float, float] | None:
    x, y, w, h = (a[k] for k in ("x_mm", "y_mm", "w_mm", "h_mm"))
    bx, by, bw, bh = (b[k] for k in ("x_mm", "y_mm", "w_mm", "h_mm"))
    for face, edge, other, lo, hi in (
        ("front", y, by + bh, max(x, bx), min(x + w, bx + bw)),
        ("rear", y + h, by, max(x, bx), min(x + w, bx + bw)),
        ("left", x, bx + bw, max(y, by), min(y + h, by + bh)),
        ("right", x + w, bx, max(y, by), min(y + h, by + bh)),
    ):
        if abs(edge - other) <= 2 and hi - lo >= 600:
            return face, lo, hi
    return None


def _openings(cells: list[dict], width: float, depth: float, geometry_key: str, feature_key: str) -> None:
    inverse = {"front": "rear", "rear": "front", "left": "right", "right": "left"}
    edges = {
        c["id"]: [
            (b, contact) for b in cells if b is not c and (contact := _contacts(c[geometry_key], b[geometry_key]))
        ]
        for c in cells
    }
    # These are sub-zones of the same hall, not two enclosed rooms.
    for cell in cells:
        group = cell.get("space_group")
        if not group:
            continue
        for neighbor, (face, lo, hi) in edges[cell["id"]]:
            if neighbor.get("space_group") != group:
                continue
            g = cell[geometry_key]
            axis, length = ("x_mm", "w_mm") if face in {"front", "rear"} else ("y_mm", "h_mm")
            cell[feature_key]["open_connections"].append(
                {
                    "face": face,
                    "ratio": round(((lo + hi) / 2 - g[axis]) / g[length], 6),
                    "width_mm": hi - lo,
                    "neighbor": neighbor["id"],
                    "status": "shared-hall-no-partition-proposal",
                }
            )
    entry = next((c for c in cells if c["is_entry"]), None)
    roots = [entry] if entry else [c for c in cells if c[feature_key]["stairs"]]
    distances = {c["id"]: 0 for c in roots}
    queue = deque(roots)
    while queue:
        c = queue.popleft()
        for neighbor, _ in edges[c["id"]]:
            # Adjacency alone must not turn a bathroom, bedroom, equipment
            # room or ceremonial storage into a through-route.
            if _common_access(neighbor) and neighbor["id"] not in distances:
                distances[neighbor["id"]] = distances[c["id"]] + 1
                queue.append(neighbor)
    for cell in sorted(cells, key=lambda c: c["kind"] == "bath"):
        features, g = cell[feature_key], cell[geometry_key]
        exterior = []
        if g["y_mm"] <= 2:
            exterior.append("front")
        if abs(g["y_mm"] + g["h_mm"] - depth) <= 2:
            exterior.append("rear")
        if g["x_mm"] <= 2:
            exterior.append("left")
        if abs(g["x_mm"] + g["w_mm"] - width) <= 2:
            exterior.append("right")
        if cell["window_mm"] > 0 and not cell["is_outdoor"]:
            # The ceremonial brief requires a solid altar backing wall.
            faces = (
                ("left", "right", "front")
                if re.search(r"神明|神桌", cell["name"])
                else ("rear", "left", "right", "front")
            )
            features["window_face"] = next((f for f in faces if f in exterior), None)
        if cell["is_entry"]:
            features["access_pending"] = False
            features["access_reason"] = "External entry proposal; not a surveyed or verified route."
            features["doors"].append(
                {
                    "face": "front",
                    "ratio": 0.5,
                    "width_mm": cell["door_mm"],
                    "neighbor": None,
                    "status": "assumed-entry-not-surveyed",
                }
            )
            continue
        if cell["is_outdoor"] or not cell["door_mm"]:
            continue
        if features["open_connections"] and cell["id"] in distances:
            features["access_pending"] = False
            features["access_reason"] = (
                "Shared stair hall sub-zone; no separate equipment-room door. Fire compartmentation unverified."
            )
        candidates = [
            (b, contact)
            for b, contact in edges[cell["id"]]
            if contact[2] - contact[1] >= cell["door_mm"] + 200
            and _common_access(b)
            and b["id"] in distances
            and (cell["id"] not in distances or distances[b["id"]] < distances[cell["id"]])
        ]
        if not candidates and cell["kind"] == "bath":
            # Ensuite access may come from a bedroom with a public-entry
            # proposal; no other room may use that bathroom as circulation.
            candidates = [
                (b, contact)
                for b, contact in edges[cell["id"]]
                if contact[2] - contact[1] >= cell["door_mm"] + 200
                and _bedroom(b)
                and not b[feature_key]["access_pending"]
            ]
        if not candidates:
            continue
        features["access_pending"] = False
        features["access_reason"] = "Common-space/ensuite adjacency proposal only; openings and clearances unverified."
        neighbor, (face, lo, hi) = min(
            candidates, key=lambda pair: (distances.get(pair[0]["id"], 999), pair[0]["is_outdoor"])
        )
        if cell.get("space_group") and neighbor.get("space_group") == cell["space_group"]:
            continue
        preferred = cell.get("door_contact_ratio")
        if preferred is None:
            preferred = 0.5
        if not isinstance(preferred, (int, float)) or isinstance(preferred, bool) or not 0 <= preferred <= 1:
            raise ValueError(f"Invalid door contact ratio: {cell['id']}")
        # Explicit conceptual door preference can keep the opening beside the
        # seating group (B's right-side circulation spine), rather than through
        # its sofa. Both adjacent cells receive the same absolute door centre.
        half = cell["door_mm"] / 2 + 100
        coord = min(hi - half, max(lo + half, lo + (hi - lo) * preferred))
        for room, side, other in ((cell, face, neighbor), (neighbor, inverse[face], cell)):
            geo = room[geometry_key]
            axis, length = ("x_mm", "w_mm") if side in ("front", "rear") else ("y_mm", "h_mm")
            door = {
                "face": side,
                "ratio": round((coord - geo[axis]) / geo[length], 6),
                "width_mm": cell["door_mm"],
                "neighbor": other["id"],
                "status": "adjacency-proposal-not-verified-route",
            }
            if not any(d["neighbor"] == other["id"] for d in room[feature_key]["doors"]):
                room[feature_key]["doors"].append(door)


def _common_access(cell: dict) -> bool:
    if cell["kind"] == "bath" or _bedroom(cell):
        return False
    return (
        cell["is_entry"]
        or cell["is_outdoor"]
        or cell["kind"] in {"living", "dining", "kitchen", "stair"}
        or cell.get("space_role") == "circulation"
        or (
            bool(cell.get("space_group"))
            and cell.get("space_role") in {"equipment-alcove", "circulation-equipment", "circulation"}
        )
        or bool(re.search(r"走道|廊|前室|梯廳|樓梯|梯間|隔斷門|玄關", cell["name"]))
    )


def _bedroom(cell: dict) -> bool:
    return (
        cell["kind"] == "bedroom" or cell.get("room_role") == "elder" or bool(re.search(r"孝親房|長輩房", cell["name"]))
    )

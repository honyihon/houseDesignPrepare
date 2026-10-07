"""Resolve one physical furniture layout for the 2D HTML and 3D surfaces.

Greedy discussion layout, not a building-code/egress solver. Furniture never
shrinks. An unsatisfied item remains a visible pending record, not a false fit.
"""

from __future__ import annotations

import math
from typing import Any

GEOMETRIES = (("tour_mm", "tour_features"), ("auto_mm", "architecture_auto"), ("declared_mm", "architecture_declared"))
ROTATION = {"rear": 0, "right": 90, "front": 180, "left": 270}
INSET = 80.0  # assumed 100mm wall, 50mm half-thickness + 30mm allowance


def rectangle(cx: float, cy: float, w: float, d: float) -> dict[str, float]:
    return {
        "minX": round(cx - w / 2, 2),
        "maxX": round(cx + w / 2, 2),
        "minY": round(cy - d / 2, 2),
        "maxY": round(cy + d / 2, 2),
    }


def overlaps(a: dict, b: dict, tolerance: float = 1) -> bool:
    return (
        a["minX"] < b["maxX"] - tolerance
        and a["maxX"] > b["minX"] + tolerance
        and a["minY"] < b["maxY"] - tolerance
        and a["maxY"] > b["minY"] + tolerance
    )


def _inside(box: dict, g: dict, inset: float = INSET) -> bool:
    return (
        box["minX"] >= g["x_mm"] + inset - 1
        and box["maxX"] <= g["x_mm"] + g["w_mm"] - inset + 1
        and box["minY"] >= g["y_mm"] + inset - 1
        and box["maxY"] <= g["y_mm"] + g["h_mm"] - inset + 1
    )


def _door_approach(g: dict, door: dict) -> dict:
    along_x = door["face"] in {"front", "rear"}
    centre = g["x_mm" if along_x else "y_mm"] + door["ratio"] * g["w_mm" if along_x else "h_mm"]
    width = door["width_mm"] + 200
    # A conservative approach strip, not a claimed door swing or legal route.
    if door["face"] == "front":
        return rectangle(centre, g["y_mm"] + 450, width, 900)
    if door["face"] == "rear":
        return rectangle(centre, g["y_mm"] + g["h_mm"] - 450, width, 900)
    if door["face"] == "left":
        return rectangle(g["x_mm"] + 450, centre, 900, width)
    return rectangle(g["x_mm"] + g["w_mm"] - 450, centre, 900, width)


def _operation(box: dict, face: str, amount: float, *, dining: bool = False) -> dict | None:
    if dining:
        return {k: v + (400 if k.startswith("max") else -400) for k, v in box.items()}
    if not face or amount <= 0:
        return None
    result = dict(box)
    edge, opposite = {
        "rear": ("minY", "maxY"),
        "front": ("maxY", "minY"),
        "left": ("maxX", "minX"),
        "right": ("minX", "maxX"),
    }[face]
    result[opposite] = box[edge]
    result[edge] += amount * (1 if edge.startswith("max") else -1)
    return result


def _candidate(item: dict, cx: float, cy: float, angle: float, face: str) -> dict:
    radians = math.radians(angle)
    w = abs(math.cos(radians)) * item["width_mm"] + abs(math.sin(radians)) * item["depth_mm"]
    d = abs(math.sin(radians)) * item["width_mm"] + abs(math.cos(radians)) * item["depth_mm"]
    box = rectangle(cx, cy, w, d)
    return {
        "id": item["id"],
        "center_x_mm": round(cx, 2),
        "center_y_mm": round(cy, 2),
        "rotation_deg": angle,
        "wall_anchor": face,
        "wall_gap_mm": item["wall_gap_mm"] if face else None,
        "aabb": box,
        "operation_mm": _operation(box, face, item["front_clearance_mm"], dining=item["shape"] == "dining-set"),
        "rear_operation_mm": _operation(
            box,
            {"front": "rear", "rear": "front", "left": "right", "right": "left"}.get(face, ""),
            item.get("rear_clearance_mm", 0),
        ),
        "mount_height_mm": item["mount_height_mm"],
        "issues": [],
        "status": "planning-not-measured",
    }


def _positions(item: dict, g: dict, features: dict, resolved: dict) -> list[dict]:
    preferred_x = g["x_mm"] + item["x_ratio"] * g["w_mm"]
    preferred_y = g["y_mm"] + item["y_ratio"] * g["h_mm"]
    reference = resolved.get(item.get("in_front_of") or item.get("aligned_with"))
    if item.get("in_front_of") and reference and not reference["issues"]:
        angle = reference["rotation_deg"]
        normal = (
            (reference["aabb"]["maxY"] - reference["aabb"]["minY"])
            if angle % 180 == 0
            else (reference["aabb"]["maxX"] - reference["aabb"]["minX"])
        )
        distance = normal / 2 + item["depth_mm"] / 2 + item["front_gap_mm"]
        radians = math.radians(angle)
        cx = reference["center_x_mm"] - math.sin(radians) * distance
        cy = reference["center_y_mm"] - math.cos(radians) * distance
        return [_candidate(item, cx, cy, angle, "")]
    if item["wall_anchor"]:
        faces = [item["wall_anchor"]]
        if not item["wall_locked"]:
            faces.extend(f for f in ROTATION if f not in faces)
        result = []
        for face in faces:
            along_x = face in {"front", "rear"}
            start, length = (g["x_mm"], g["w_mm"]) if along_x else (g["y_mm"], g["h_mm"])
            lo, hi = start + item["width_mm"] / 2 + INSET, start + length - item["width_mm"] / 2 - INSET
            preferred = (
                (reference["center_x_mm"] if along_x else reference["center_y_mm"])
                if reference
                else (preferred_x if along_x else preferred_y)
            )
            if item.get("aligned_with") and reference:
                values = [preferred]  # never call an off-axis TV an aligned layout
            elif hi < lo:
                values = [preferred]  # keep the actual-size failing envelope
            else:
                values = sorted(
                    {lo, hi, min(hi, max(lo, preferred)), *[lo + i * 100 for i in range(int((hi - lo) / 100) + 1)]},
                    key=lambda v: abs(v - preferred),
                )
            normal = item["depth_mm"] / 2 + item["wall_gap_mm"]
            for along in values:
                cx, cy = {
                    "rear": (along, g["y_mm"] + g["h_mm"] - normal),
                    "front": (along, g["y_mm"] + normal),
                    "left": (g["x_mm"] + normal, along),
                    "right": (g["x_mm"] + g["w_mm"] - normal, along),
                }[face]
                result.append(_candidate(item, cx, cy, ROTATION[face], face))
        return result
    # Small deterministic search around the preferred free-standing position.
    xs, ys = {preferred_x}, {preferred_y}
    for i in range(1, 20):
        xs.update((preferred_x + i * 150, preferred_x - i * 150))
        ys.update((preferred_y + i * 150, preferred_y - i * 150))
    if item["shape"] == "palanquin" and features.get("carry_path_mm"):
        # The storage brief is straight-pull, not a made-up turning circle.
        xs = {features["carry_path_mm"]["center_x_mm"]}
    points = sorted(
        ((x, y) for x in xs for y in ys), key=lambda p: (p[0] - preferred_x) ** 2 + (p[1] - preferred_y) ** 2
    )
    return [_candidate(item, x, y, item["rotation_deg"], "") for x, y in points]


def _issues(item: dict, candidate: dict, g: dict, features: dict, placed: list[dict]) -> list[str]:
    box, op, face = candidate["aabb"], candidate["operation_mm"], candidate["wall_anchor"]
    issues = []
    if not _inside(box, g):
        issues.append("overflow")
    if op and not _inside(op, g):
        issues.append("operation-space")
    rear = candidate.get("rear_operation_mm")
    if rear and not _inside(rear, g, inset=50):
        issues.append("operation-space")
    carry = features.get("carry_path_mm")
    if item["shape"] == "palanquin" and carry and box["maxX"] - box["minX"] > carry["width_mm"]:
        issues.append("transport-width")
    for zone in features["reserved_mm"]:
        # Toilet/vanity approaches may sequentially share a turning floor;
        # kitchen work aisles may share circulation, never physical fixtures.
        # This is an explicitly annotated proposal, not accessibility approval.
        shared_operation = zone["kind"] in item.get("shared_operation_with", [])
        if (
            overlaps(box, zone["aabb"])
            or (op and not shared_operation and overlaps(op, zone["aabb"]))
            or (rear and overlaps(rear, zone["aabb"]))
        ):
            issues.append(zone["kind"])
    if face:
        lo, hi = (box["minX"], box["maxX"]) if face in {"front", "rear"} else (box["minY"], box["maxY"])
        for opening in features["open_connections"] + features["doors"]:
            if opening["face"] != face:
                continue
            start, length = (g["x_mm"], g["w_mm"]) if face in {"front", "rear"} else (g["y_mm"], g["h_mm"])
            centre = start + length * opening["ratio"]
            if lo < centre + opening["width_mm"] / 2 and hi > centre - opening["width_mm"] / 2:
                issues.append("unsupported-wall")
        if features["window_face"] == face and item["height_mm"] + item["mount_height_mm"] > features.get(
            "window_sill_mm", 900
        ):
            start, length = (g["x_mm"], g["w_mm"]) if face in {"front", "rear"} else (g["y_mm"], g["h_mm"])
            centre = start + length * features["window_ratio"]
            if lo < centre + features["window_mm"] / 2 and hi > centre - features["window_mm"] / 2:
                issues.append("window")
    for other in placed:
        if overlaps(box, other["aabb"]):
            issues.append("furniture-overlap")
        if (op and overlaps(op, other["aabb"])) or (other["operation_mm"] and overlaps(box, other["operation_mm"])):
            issues.append("operation-space")
        if (rear and overlaps(rear, other["aabb"])) or (
            other.get("rear_operation_mm") and overlaps(box, other["rear_operation_mm"])
        ):
            issues.append("operation-space")
    return sorted(set(issues))


def attach_placements(buildings: list[dict[str, Any]]) -> None:
    for building in buildings:
        for floor in building["floors"]:
            for cell in floor["cells"]:
                cell["furniture_placements"] = {}
                for geometry_key, feature_key in GEOMETRIES:
                    g, features = cell[geometry_key], cell[feature_key]
                    features["window_mm"] = cell["window_mm"]
                    features["reserved_mm"] = list(features.get("fixed_reserved_mm", [])) + [
                        {"kind": "door-approach", "aabb": _door_approach(g, d)} for d in features["doors"]
                    ]
                    stair = features.get("stair_footprint_mm")
                    if stair:
                        features["reserved_mm"].append(
                            {
                                "kind": "stairs",
                                "aabb": rectangle(
                                    stair["x_mm"] + stair["w_mm"] / 2,
                                    stair["y_mm"] + stair["h_mm"] / 2,
                                    stair["w_mm"],
                                    stair["h_mm"],
                                ),
                            }
                        )
                    if cell.get("access_mode") == "straight-pull" and cell.get("carry_path_mm"):
                        door = next((d for d in features["doors"] if d["face"] == "front"), None)
                        if door:
                            features["carry_path_mm"] = {
                                "center_x_mm": round(g["x_mm"] + g["w_mm"] * door["ratio"], 2),
                                "width_mm": cell["carry_path_mm"],
                            }
                    placed, resolved = [], {}
                    items = sorted(
                        cell.get("furniture", []),
                        key=lambda i: (
                            i["shape"] != "palanquin",
                            not i["wall_locked"],
                            not bool(i["wall_anchor"]),
                            -i["width_mm"] * i["depth_mm"],
                        ),
                    )
                    # Resolve linked coffee tables / aligned TVs AFTER their
                    # sofa or bed; reject cycles instead of silently drifting.
                    pending = items[:]
                    items = []
                    done = set()
                    while pending:
                        ready = [
                            i
                            for i in pending
                            if all(not i.get(k) or i[k] in done for k in ("in_front_of", "aligned_with"))
                        ]
                        if not ready:
                            raise ValueError(f"Cyclic furniture relationship: {cell['id']}")
                        for item in ready:
                            items.append(item)
                            done.add(item["id"])
                            pending.remove(item)
                    for item in items:
                        candidates = _positions(item, g, features, resolved)
                        best = None
                        for candidate in candidates:
                            candidate["issues"] = _issues(item, candidate, g, features, placed)
                            if any(
                                item.get(k) and resolved[item[k]]["issues"] for k in ("in_front_of", "aligned_with")
                            ):
                                candidate["issues"].append("reference-pending")
                            if best is None or len(candidate["issues"]) < len(best["issues"]):
                                best = candidate
                            if not candidate["issues"]:
                                break
                        assert best is not None
                        if not best["issues"]:
                            placed.append(best)
                            carry = features.get("carry_path_mm")
                            if item["shape"] == "palanquin" and carry:
                                path = rectangle(
                                    carry["center_x_mm"],
                                    (g["y_mm"] + best["aabb"]["minY"]) / 2,
                                    carry["width_mm"],
                                    best["aabb"]["minY"] - g["y_mm"],
                                )
                                features["reserved_mm"].append({"kind": "transport-band", "aabb": path})
                        else:
                            best["status"] = "pending-layout"
                        resolved[item["id"]] = best
                    cell["furniture_placements"][geometry_key] = resolved

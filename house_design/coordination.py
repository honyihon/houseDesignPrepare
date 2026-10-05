"""Revision-bound interior and architectural coordination checks, in mm.

Checks certify explicit designer-supplied routes/zones, not all possible routes.
Missing coverage or nominal/hull geometry never proves a clear space.
"""

from __future__ import annotations

import math
from html import escape
from typing import Any

from house_design.contracts import ContractError, stable_hash

SCHEMA = "house-coordination-overlay-v1"
KINDS = {
    "containment",
    "collision",
    "clearance",
    "turning_circle",
    "route",
    "carry_route",
    "projection",
    "sightline",
    "headroom",
    "numeric",
}
METHODS = {"closed_dxf_polyline", "professional_verified_polygon", "surveyed_polygon"}
DOMAINS = {"accessibility", "maintenance", "fengshui", "building_regulation", "structural", "space_program"}


def coordination_template(model: dict[str, Any], revision_hash: str) -> dict[str, Any]:
    """Prepare an unverified handoff; never invent geometry, laws or owner decisions."""
    floors = sorted(
        {
            (o.get("building_id"), o.get("floor_id"))
            for values in model.get("entities", {}).values()
            for o in values
            if o.get("building_id") and o.get("floor_id")
        }
    )
    return {
        "schema": SCHEMA,
        "revision_id": model["revision_id"],
        "revision_hash": revision_hash,
        "registration": {"verified_by": None, "verified_at": None, "reference": None},
        "objects": [],
        "checks": [],
        "coverage": [
            {
                "building_id": b,
                "floor_id": f,
                "domain": d,
                "complete": False,
                "object_ids": [],
                "check_ids": [],
                "evidence": {"verified_by": None, "verified_at": None, "reference": None},
            }
            for b, f in floors
            for d in sorted(DOMAINS)
        ],
        "drawing_entity_ids": {
            key: [o["id"] for o in values if o.get("id")] for key, values in model.get("entities", {}).items()
        },
        "recommended_check_types": sorted(KINDS),
        "notes": [
            "參閱 Docs/coordination-review.md；此空白模板不可當作通過或完整套繪。",
            "暫估武轎收納尺寸不等於實測搬運外廓；轉彎需專業演練。",
        ],
    }


def _number(value: Any) -> bool:
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def _evidence(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(value.get(k), str) and value[k].strip() for k in ("verified_by", "verified_at", "reference")
    )


def validate_overlay(overlay: dict[str, Any], model: dict[str, Any], revision_hash: str) -> None:
    if not isinstance(overlay, dict) or overlay.get("schema") != SCHEMA:
        raise ContractError(f"coordination schema must be {SCHEMA}")
    if overlay.get("revision_id") != model.get("revision_id") or overlay.get("revision_hash") != revision_hash:
        raise ContractError("coordination overlay is stale: revision id/hash does not match")
    for key in ("objects", "checks", "coverage"):
        if not isinstance(overlay.get(key), list):
            raise ContractError(f"coordination.{key} must be an array")
    objects = [o for values in model.get("entities", {}).values() for o in values]
    ids = {str(o.get("id")) for o in objects}
    floor_pairs = {
        (o.get("building_id"), o.get("floor_id")) for o in objects if o.get("building_id") and o.get("floor_id")
    }
    for obj in overlay["objects"]:
        if not isinstance(obj, dict) or not isinstance(obj.get("id"), str) or not obj["id"] or obj["id"] in ids:
            raise ContractError("coordination objects need unique ids distinct from drawing entities")
        ids.add(obj["id"])
        if any(not isinstance(obj.get(k), str) or not obj[k] for k in ("building_id", "floor_id")):
            raise ContractError("coordination objects need building_id and floor_id")
        if (obj["building_id"], obj["floor_id"]) not in floor_pairs:
            raise ContractError("coordination object floor is not present in this drawing revision")
    seen = set()
    for check in overlay["checks"]:
        if (
            not isinstance(check, dict)
            or not isinstance(check.get("id"), str)
            or not check["id"]
            or check["id"] in seen
        ):
            raise ContractError("coordination checks need unique ids")
        seen.add(check["id"])
        if (
            not isinstance(check.get("kind"), str)
            or check["kind"] not in KINDS
            or not isinstance(check.get("domain"), str)
            or check["domain"] not in DOMAINS
        ):
            raise ContractError("unsupported coordination kind/domain")
        if not isinstance(check.get("priority", "should"), str) or check.get("priority", "should") not in {
            "must",
            "should",
            "could",
        }:
            raise ContractError("coordination priority must be must/should/could")
        if check.get("kind") == "numeric" and (
            not isinstance(check.get("operator"), str) or check["operator"] not in {"min", "max"}
        ):
            raise ContractError("numeric operator must be min/max")
        for key in ("subject_id", "requirement_id"):
            if check.get(key) is not None and not isinstance(check[key], str):
                raise ContractError(f"{key} must be an id string")
        for key in ("evidence", "law", "transport"):
            if check.get(key) is not None and not isinstance(check[key], dict):
                raise ContractError(f"{key} must be an object")
        for key in ("target_ids", "obstacle_ids"):
            if not isinstance(check.get(key, []), list) or any(not isinstance(i, str) for i in check.get(key, [])):
                raise ContractError(f"{key} must be an array")
    for item in overlay["coverage"]:
        if not isinstance(item, dict) or not item.get("building_id") or not item.get("floor_id"):
            raise ContractError("coverage needs building_id and floor_id")
        if not isinstance(item.get("domain"), str) or item["domain"] not in DOMAINS:
            raise ContractError("unsupported coverage domain")
        for key in ("object_ids", "check_ids"):
            if not isinstance(item.get(key, []), list) or any(not isinstance(i, str) for i in item.get(key, [])):
                raise ContractError(f"coverage.{key} must be an array of ids")


def _polygon(obj: dict[str, Any]) -> Any:
    from shapely.geometry import Polygon

    points = obj.get("polygon_mm")
    if (
        not isinstance(obj.get("geometry_method"), str)
        or obj["geometry_method"] not in METHODS
        or not isinstance(points, list)
    ):
        return None
    if len(points) < 3 or any(not isinstance(p, list) or len(p) != 2 or not all(_number(v) for v in p) for p in points):
        return None
    shape = Polygon(points)
    return shape if shape.is_valid and not shape.is_empty and shape.area > 0 else None


def _same_floor(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (a.get("building_id"), a.get("floor_id")) == (b.get("building_id"), b.get("floor_id"))


def _verified_coordinates(model: dict[str, Any]) -> bool:
    from house_design.drawings import VERIFIED_COORDINATE_STATUSES

    c = model.get("coordinate_system") or {}
    return (
        (model.get("units") or {}).get("length", "mm") == "mm"
        and c.get("status") in VERIFIED_COORDINATE_STATUSES
        and bool(c.get("axis"))
        and bool(c.get("verified_by"))
        and bool(c.get("verified_at"))
        and bool(c.get("method"))
        and isinstance(c.get("reference_points"), list)
        and len(c["reference_points"]) >= 2
    )


def _evaluate(
    check: dict[str, Any], objects: dict[str, dict[str, Any]], model: dict[str, Any], coverage: list[dict[str, Any]]
) -> tuple[str, str, dict[str, Any]]:
    from shapely.geometry import LineString, Point

    kind = check["kind"]
    measurements: dict[str, Any] = {}
    if not _evidence(check.get("evidence")):
        return "unknown", "缺少此檢查的圖號、查核人或日期。", measurements
    if check["domain"] == "building_regulation":
        law = check.get("law") or {}
        if not all(law.get(k) for k in ("title", "article", "effective_from", "applicability")) or not _evidence(
            law.get("evidence")
        ):
            return "professional_review", "法規版本及基地適用條件尚待建築師確認。", measurements
    if kind == "numeric":
        actual, threshold = check.get("actual"), check.get("threshold")
        measurements.update(actual=actual, threshold=threshold, unit=check.get("unit"))
        if not _number(actual) or not _number(threshold) or not check.get("unit"):
            return "unknown", "缺少可追溯計算值、門檻或單位。", measurements
        if check["domain"] == "building_regulation":
            law = check.get("law") or {}
            if not all(law.get(k) for k in ("title", "article", "effective_from", "applicability")) or not _evidence(
                law.get("evidence")
            ):
                return "professional_review", "法規版本及基地適用條件尚待建築師確認。", measurements
        ok = actual >= threshold if check["operator"] == "min" else actual <= threshold
        return ("pass" if ok else "violation"), "數值符合門檻。" if ok else "數值超出確認門檻。", measurements

    subject = objects.get(check.get("subject_id"))
    target_ids = check.get("target_ids", [])
    obstacle_ids = check.get("obstacle_ids", [])
    if subject is None or any(i not in objects for i in target_ids + obstacle_ids):
        return "unknown", "缺少物件綁定；請補圖面或套繪物件 id。", measurements
    targets = [objects[i] for i in target_ids]
    obstacles = [objects[i] for i in obstacle_ids]
    if kind == "projection":
        targets += obstacles
        obstacles = []
    selected = [subject, *targets, *obstacles]
    if any(not o.get("building_id") or not o.get("floor_id") for o in selected):
        return "unknown", "物件缺少棟層定位。", measurements
    if any(o.get("building_id") != subject.get("building_id") for o in selected):
        return "professional_review", "跨棟關係需另行確認。", measurements
    if kind != "projection" and any(not _same_floor(subject, o) for o in selected):
        return "unknown", "此檢查的物件不在同一樓層。", measurements
    if any(o.get("_overlay") and not _evidence(o.get("evidence")) for o in selected):
        return "unknown", "套繪物件缺少圖號與查核證據。", measurements
    if not _verified_coordinates(model):
        return "unknown", "圖面／套繪共同座標尚未驗證。", measurements

    if kind == "headroom":
        value, minimum = subject.get("finished_headroom_mm"), check.get("minimum_mm")
        measurements.update(actual=value, threshold=minimum, unit="mm")
        if not _number(value) or not _number(minimum) or minimum <= 0:
            return "unknown", "須提供完成面至梁／天花最低點的淨高及門檻。", measurements
        return ("pass" if value >= minimum else "violation"), "完成面淨高比較。", measurements

    polys = [_polygon(o) for o in selected]
    if any(p is None for p in polys):
        return "unknown", "缺少精確有效 polygon；bbox 或 IFC convex hull 不足以判定。", measurements
    shape = polys[0]
    target_polys = polys[1 : 1 + len(targets)]
    obstacle_polys = polys[1 + len(targets) :]
    # Negative results require an explicit, dated completeness declaration.
    needs_coverage = kind in {"clearance", "turning_circle", "route", "carry_route", "sightline", "projection"}

    def complete_floor(building: str, floor: str) -> bool:
        floor_ids = {
            o["id"]
            for o in objects.values()
            if o.get("building_id") == building
            and o.get("floor_id") == floor
            and o.get("_collection") not in {"buildings", "storeys", "drawing_geometry"}
        }
        return any(
            c.get("building_id") == building
            and c.get("floor_id") == floor
            and c.get("domain") == check["domain"]
            and c.get("complete") is True
            and check["id"] in c.get("check_ids", [])
            and _evidence(c.get("evidence"))
            and floor_ids.issubset(set(c.get("object_ids", [])))
            for c in coverage
        )

    complete = complete_floor(subject["building_id"], subject["floor_id"])
    if needs_coverage and not complete:
        return "unknown", "缺少此棟層／專項的完整套繪聲明，不能把未畫障礙當成淨空。", measurements
    if needs_coverage:
        listed = {subject["id"], *target_ids, *obstacle_ids}
        floors = {(subject["building_id"], subject["floor_id"])}
        if kind == "projection":
            floors |= {
                (s.get("building_id"), s.get("floor_id"))
                for s in model.get("entities", {}).get("storeys", [])
                if s.get("building_id") == subject["building_id"]
            }
            if any(not complete_floor(b, f) for b, f in floors):
                return "unknown", "跨層投影需要同棟各樓層的完整圖面聲明。", measurements
        for obj in objects.values():
            if obj.get("_collection") not in {"buildings", "storeys", "spaces", "drawing_geometry"} and (
                not obj.get("building_id") or not obj.get("floor_id")
            ):
                return "unknown", f"潛在障礙物缺少棟層定位：{obj['id']}。", measurements
            if (obj.get("building_id"), obj.get("floor_id")) not in floors or obj["id"] in listed:
                continue
            if obj.get("_collection") in {"buildings", "storeys", "drawing_geometry"}:
                continue
            if obj.get("_collection") == "spaces" and not (
                kind == "projection" and obj.get("category") in {"bathroom", "toilet", "kitchen", "wet_area"}
            ):
                continue
            if obj.get("obstruction") is False and _evidence(obj.get("evidence")):
                continue
            return "unknown", f"未納入比較的潛在障礙物：{obj['id']}；須加入清單或提供非障礙證據。", measurements

    if kind == "containment":
        if len(targets) != 1 or targets[0].get("boundary_measurement") != "finished_clear":
            return "unknown", "需指定一個完成面淨空房間邊界。", measurements
        outside = shape.difference(target_polys[0]).area
        measurements["outside_sqm"] = outside / 1_000_000
        return ("violation" if outside > 1e-6 else "pass"), "物件是否落在完成面房間範圍。", measurements
    if kind == "projection":
        if not targets:
            return "unknown", "需指定保護投影的目標物件。", measurements
        levels = {
            (s.get("building_id"), s.get("floor_id")): s.get("elevation_mm")
            for s in model.get("entities", {}).get("storeys", [])
        }
        base = levels.get((subject["building_id"], subject["floor_id"]))
        hits = []
        for obj, poly in zip(targets, target_polys, strict=True):
            top = levels.get((obj["building_id"], obj["floor_id"]))
            target_complete = complete_floor(obj["building_id"], obj["floor_id"])
            if not _number(base) or not _number(top) or not target_complete:
                return "unknown", "缺少樓層標高或上層完整套繪證據。", measurements
            if top > base and shape.intersection(poly).area > 1e-6:
                hits.append(obj["id"])
        measurements["conflicting_ids"] = hits
        return ("violation" if hits else "pass"), "神桌／保護區與上方物件投影比較。", measurements
    if kind == "collision":
        if not targets:
            return "unknown", "需指定碰撞比較物件。", measurements
        hits = [o["id"] for o, p in zip(targets, target_polys, strict=True) if shape.intersection(p).area > 1e-6]
        measurements["conflicting_ids"] = hits
        measurements["overlap_sqm"] = {
            o["id"]: shape.intersection(p).area / 1_000_000
            for o, p in zip(targets, target_polys, strict=True)
            if o["id"] in hits
        }
        return ("violation" if hits else "pass"), "指定物件實際 polygon 碰撞比較。", measurements

    if kind in {"clearance", "turning_circle", "route", "carry_route"}:
        if subject.get("boundary_measurement") != "finished_clear":
            return "unknown", "動線必須使用完成面淨空邊界。", measurements
        if kind == "clearance":
            if len(target_polys) != 1:
                return "unknown", "需指定一個操作／抽換淨空區。", measurements
            zone = target_polys[0]
        elif kind == "turning_circle":
            center, diameter = check.get("center_mm"), check.get("diameter_mm")
            if (
                not isinstance(center, list)
                or len(center) != 2
                or not all(_number(v) for v in center)
                or not _number(diameter)
                or diameter <= 0
            ):
                return "unknown", "需指定設計師標示的迴轉圓心與直徑。", measurements
            # Circumscribed circle: an inscribed approximation could falsely pass.
            zone = Point(center).buffer(diameter / 2 / math.cos(math.pi / 256), quad_segs=64)
            measurements["diameter_mm"] = diameter
        else:
            points, width = check.get("path_mm"), check.get("width_mm")
            if (
                not isinstance(points, list)
                or len(points) < 2
                or any(not isinstance(p, list) or len(p) != 2 or not all(_number(v) for v in p) for p in points)
                or not _number(width)
                or width <= 0
            ):
                return "unknown", "需指定連續搬運／通行中心線與淨寬。", measurements
            path = LineString(points)
            if not path.is_simple or path.length <= 0:
                return "unknown", "路徑必須連續且無自交。", measurements
            zone = path.buffer(width / 2, cap_style=2, join_style=2)
            measurements["width_mm"] = width
            if kind == "carry_route":
                item = check.get("transport") or {}
                if (
                    item.get("measurement_state") != "measured"
                    or not _evidence(item.get("evidence"))
                    or not all(_number(item.get(k)) and item[k] > 0 for k in ("width_mm", "depth_mm", "height_mm"))
                ):
                    return "unknown", "搬運外廓尚未實測；收納暫估不可證明搬得出去。", measurements
                if len(points) != 2:
                    return "professional_review", "轉彎搬運需另做旋轉掃掠與實物演練。", measurements
                if width < item["width_mm"]:
                    return "violation", "搬運路徑淨寬小於實測搬運外廓。", measurements
                height = check.get("route_clear_height_mm")
                if not _number(height):
                    return "unknown", "缺少全路徑最低完成面淨高。", measurements
                if height < item["height_mm"]:
                    return "violation", "搬運路徑淨高不足。", measurements
                ux = (points[1][0] - points[0][0]) / path.length
                uy = (points[1][1] - points[0][1]) / path.length
                extended = LineString(
                    [
                        [points[0][0] - ux * item["depth_mm"] / 2, points[0][1] - uy * item["depth_mm"] / 2],
                        [points[1][0] + ux * item["depth_mm"] / 2, points[1][1] + uy * item["depth_mm"] / 2],
                    ]
                )
                zone = extended.buffer(width / 2, cap_style=2)
        outside = zone.difference(shape).area
        hits = [o["id"] for o, p in zip(obstacles, obstacle_polys, strict=True) if zone.intersection(p).area > 1e-6]
        measurements.update(outside_sqm=outside / 1_000_000, conflicting_ids=hits)
        return ("violation" if outside > 1e-6 or hits else "pass"), "指定淨空／路徑及其障礙物比較。", measurements
    # A designer supplies the sightline from a door centre to a bed/altar front.
    if subject.get("_collection") != "doors" and subject.get("category") not in {"door", "door_opening"}:
        return "unknown", "視線來源需綁定明確的門洞物件，不可拿整個房間當作門洞。", measurements
    points = check.get("ray_mm")
    if (
        not isinstance(points, list)
        or len(points) != 2
        or any(not isinstance(p, list) or len(p) != 2 or not all(_number(v) for v in p) for p in points)
        or len(target_polys) != 1
    ):
        return "unknown", "需提供門向視線線段與一個目標物件。", measurements
    ray = LineString(points)
    if ray.length == 0 or not shape.covers(Point(points[0])) or not target_polys[0].covers(Point(points[1])):
        return "unknown", "視線端點須位於來源門洞與目標家具內。", measurements
    blocks = [o["id"] for o, p in zip(obstacles, obstacle_polys, strict=True) if ray.intersects(p)]
    if check.get("direction_verified") is not True or any(
        o.get("fixed_opaque_sightline_blocker") is not True for o in obstacles if o["id"] in blocks
    ):
        return "unknown", "門向或固定遮擋高度／不透光性未確認；低矮家具不能視為阻擋。", measurements
    measurements["blocking_ids"] = blocks
    return ("pass" if blocks else "violation"), "指定門向視線是否有固定遮擋。", measurements


def coordination_review(
    model: dict[str, Any], overlay: dict[str, Any] | None, revision_hash: str, requirements: dict[str, Any]
) -> dict[str, Any]:
    if overlay is None:
        return {
            "overlay_hash": None,
            "findings": [
                _finding(
                    {"id": "missing-overlay", "domain": "space_program", "title": "缺少建築／裝潢套繪資料"},
                    "unknown",
                    "請提供與本圖面版次綁定的家具、門扇、梁柱、管線及淨空檢查。",
                    {},
                    [],
                )
            ],
            "objects": [],
            "checks": [],
        }
    validate_overlay(overlay, model, revision_hash)
    try:
        import shapely  # noqa: F401
    except ImportError as exc:
        raise ContractError("Install drawing extras (Shapely) to run coordination checks") from exc
    objects = {
        o["id"]: {**o, "_collection": key}
        for key, values in model.get("entities", {}).items()
        for o in values
        if o.get("id")
    }
    objects.update({o["id"]: {**o, "_overlay": True} for o in overlay["objects"]})
    reqs = {r["id"]: r for r in requirements.get("requirements", [])}
    findings = []
    for check in overlay["checks"]:
        req = reqs.get(check.get("requirement_id"))
        if check.get("requirement_id") and req is None:
            status, message, values = "unknown", "找不到需求 id。", {}
        elif req and req.get("status") == "rejected":
            status, message, values = "not_applicable", "屋主已淘汰此需求。", {}
        else:
            if check["kind"] != "numeric" and not _evidence(overlay.get("registration")):
                status, message, values = "unknown", "缺少裝潢套繪對位至本版圖面的查核證據。", {}
            else:
                status, message, values = _evaluate(check, objects, model, overlay["coverage"])
            if req and req.get("status") != "confirmed" and status in {"pass", "violation"}:
                values["geometric_result"] = status
                status, message = "warning", f"待屋主確認：{message}"
            elif status == "violation":
                # Fengshui cannot silently become a legal mandatory rule.
                hard = req and req.get("priority") == "must"
                if check["domain"] != "fengshui" and not req:
                    hard = check.get("priority") == "must"
                status = "fail" if hard else "warning"
        related = [
            objects[i]
            for i in [check.get("subject_id"), *check.get("target_ids", []), *check.get("obstacle_ids", [])]
            if i in objects
        ]
        findings.append(_finding(check, status, message, values, related))
    if not overlay["checks"]:
        findings.append(
            _finding({"id": "empty-checks", "domain": "space_program"}, "unknown", "套繪尚未設定任何檢查項目。", {}, [])
        )
    return {
        "overlay_hash": stable_hash(overlay),
        "overlay": overlay,
        "findings": findings,
        "objects": list(objects.values()),
        "checks": overlay["checks"],
    }


def _finding(
    check: dict[str, Any], status: str, message: str, values: dict[str, Any], related: list[dict[str, Any]]
) -> dict[str, Any]:
    first = related[0] if related else {}
    return {
        "finding_id": f"COORD-{check['id']}",
        "rule_id": f"COORD-{check.get('kind', 'DATA').upper()}",
        "check_id": check["id"],
        "status": status,
        "status_label": {
            "pass": "通過",
            "fail": "失敗",
            "warning": "警告",
            "unknown": "未知",
            "professional_review": "專業確認",
            "not_applicable": "不適用",
        }[status],
        "severity": "error" if status == "fail" else "advisory",
        "domain": check["domain"],
        "title": check.get("title", check["id"]),
        "message": message,
        "applies_to": {
            "building_id": first.get("building_id"),
            "floor_id": first.get("floor_id"),
            "requirement_id": check.get("requirement_id"),
        },
        "responsible_role": check.get("responsible_role", "建築師／裝潢設計師"),
        "next_action": check.get("next_action", "補齊證據或調整標註範圍後重新檢核。"),
        "source": check.get("law")
        or {
            "type": "design_input_not_law",
            "reference": check.get("evidence"),
            "requirement_id": check.get("requirement_id"),
        },
        "measurements": values,
        "evidence": [
            {
                "kind": "coordination",
                "reference": check.get("evidence"),
                "entity_ids": [o["id"] for o in related],
                "measurements": values,
            }
        ],
    }


def compare_coordination(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    left = {f["check_id"]: f for f in before["findings"]}
    right = {f["check_id"]: f for f in after["findings"]}
    results = []
    good = {"pass", "not_applicable"}
    for key in sorted(left.keys() | right.keys()):
        a, b = left.get(key), right.get(key)
        if b is None:
            state = "evidence_lost"  # removing a check is not resolving its problem
        elif (
            b["status"] in {"unknown", "professional_review"}
            and a
            and a["status"] not in {"unknown", "professional_review"}
        ):
            state = "evidence_lost"
        elif a is None or (a["status"] in good and b["status"] not in good):
            state = "new"
        elif a["status"] not in good and b["status"] in good:
            state = "resolved"
        else:
            state = "persistent"
        results.append({"check_id": key, "state": state, "before": a, "after": b})
    return results


def coordination_html(result: dict[str, Any]) -> str:
    """Offline, printable precise polygons with check ids and cross-floor context."""
    objects = result.get("objects", [])
    by_id = {o["id"]: o for o in objects}
    conflicts = {i for f in result["findings"] for i in f.get("measurements", {}).get("conflicting_ids", [])}
    sections = []
    floors = sorted(
        {(o.get("building_id"), o.get("floor_id")) for o in objects if o.get("building_id") and o.get("floor_id")}
    )
    for building, floor in floors:
        selected = [o for o in objects if o.get("building_id") == building and o.get("floor_id") == floor]
        paths, shapes = [], []
        for obj in selected:
            p = obj.get("polygon_mm")
            if not isinstance(p, list) or len(p) < 3:
                continue
            if any(not isinstance(pt, list) or len(pt) != 2 or not all(_number(v) for v in pt) for pt in p):
                continue
            paths.extend(p)
            points = " ".join(f"{x},{y}" for x, y in p)
            css = ' class="conflict"' if obj["id"] in conflicts else ""
            shapes.append(
                f'<polygon{css} points="{points}"><title>{escape(str(obj["id"]))}</title></polygon>'
                f'<text x="{p[0][0]}" y="{p[0][1]}">{escape(str(obj["id"]))}</text>'
            )
        for check in result.get("checks", []):
            subject = by_id.get(check.get("subject_id"), {})
            if (subject.get("building_id"), subject.get("floor_id")) != (building, floor):
                continue
            label = escape(check["id"])
            if check["kind"] == "projection":
                for oid in [*check.get("target_ids", []), *check.get("obstacle_ids", [])]:
                    obj = by_id.get(oid, {})
                    p = obj.get("polygon_mm", [])
                    if (
                        isinstance(p, list)
                        and len(p) >= 3
                        and all(isinstance(pt, list) and len(pt) == 2 and all(_number(v) for v in pt) for pt in p)
                    ):
                        paths.extend(p)
                        pts = " ".join(f"{x},{y}" for x, y in p)
                        shapes.append(
                            f'<polygon class="projection" points="{pts}"><title>{label}：'
                            f"{escape(str(obj.get('floor_id')))}／{escape(oid)}</title></polygon>"
                        )
            p = check.get("path_mm", check.get("ray_mm", []))
            if (
                isinstance(p, list)
                and len(p) >= 2
                and all(isinstance(pt, list) and len(pt) == 2 and all(_number(v) for v in pt) for pt in p)
            ):
                paths.extend(p)
                width = check.get("width_mm", 20)
                width = width if _number(width) and width > 0 else 20
                pts = " ".join(f"{x},{y}" for x, y in p)
                shapes.append(
                    f'<polyline class="route" stroke-width="{width}" points="{pts}"><title>{label}</title></polyline>'
                    f'<text x="{p[0][0]}" y="{p[0][1]}">{label}</text>'
                )
            center, diameter = check.get("center_mm"), check.get("diameter_mm")
            if (
                isinstance(center, list)
                and len(center) == 2
                and all(_number(v) for v in center)
                and _number(diameter)
                and diameter > 0
            ):
                x, y = center
                paths.extend([[x - diameter / 2, y - diameter / 2], [x + diameter / 2, y + diameter / 2]])
                shapes.append(
                    f'<circle class="turn" cx="{x}" cy="{y}" r="{diameter / 2}"><title>{label}</title></circle>'
                    f'<text x="{x}" y="{y}">{label}</text>'
                )
        if paths:
            x0, y0 = min(p[0] for p in paths), min(p[1] for p in paths)
            w, h = max(p[0] for p in paths) - x0, max(p[1] for p in paths) - y0
            sections.append(
                f"<h2>{escape(str(building))} 棟／{escape(str(floor))}</h2>"
                f'<svg viewBox="{x0 - 100} {y0 - 100} {w + 200} {h + 200}" role="img" '
                f'aria-label="棟層套繪">{"".join(shapes)}</svg>'
            )
    rows = []
    for f in result["findings"]:
        refs = f["evidence"][0].get("entity_ids", []) if f["evidence"] else []
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{escape(str(v))}</td>"
                for v in (
                    f["finding_id"],
                    f["status_label"],
                    f["title"],
                    ", ".join(refs),
                    f["message"],
                    f["measurements"],
                    f["source"],
                    f["responsible_role"],
                    f["next_action"],
                )
            )
            + "</tr>"
        )
    return (
        '<!doctype html><html lang="zh-Hant"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>圖面協調檢核</title>'
        "<style>body{font:16px/1.6 sans-serif;margin:24px;overflow-wrap:anywhere}svg{width:100%;max-height:650px;"
        "border:1px solid #ccc}polygon{fill:#93c5fd44;stroke:#334155;stroke-width:8}"
        ".conflict{fill:#f8717188;stroke:#b91c1c}.projection{fill:#c084fc55;stroke:#9333ea;stroke-dasharray:30 20}"
        ".route{fill:none;stroke:#f59e0b;opacity:.35}.turn{fill:#34d39944;stroke:#059669;stroke-width:10}"
        "text{font-size:100px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;"
        "padding:8px;overflow-wrap:anywhere}@media print{h2{break-before:page}tr{break-inside:avoid}}</style>"
        "<h1>建築與裝潢套繪檢核</h1><p>套繪雜湊：" + escape(str(result.get("overlay_hash"))) + "</p>"
        "<p>單位 mm；沿用共同座標，非指北圖。紅色：衝突物件；紫虛線：跨層投影；橙：指定路徑；綠：迴轉區。"
        "示意圖不可作施工量測；搬運端點延伸及轉彎須看數值與專業審查。未設定的項目不代表通過。</p>"
        + "".join(sections)
        + "<h2>檢核事項</h2><table><thead><tr><th>ID</th><th>結果</th><th>項目</th><th>物件</th>"
        "<th>說明</th><th>數值</th><th>門檻來源</th><th>負責人</th><th>下一步</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></html>"
    )

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from typing import Any

from house_design.contracts import REVIEW_STATUSES, ROOT, ContractError, read_json, stable_hash, utc_now, write_json
from house_design.coordination import compare_coordination, coordination_html, coordination_review
from house_design.drawing_readiness import _valid_bbox, _valid_polygon, assess_model3d_readiness
from house_design.drawings import VERIFIED_COORDINATE_STATUSES, compare_revisions, load_revision
from house_design.intake import (
    PROJECT_PATH,
    RELATIONSHIP_SPECIAL_TARGETS,
    RELATIONSHIP_TYPES,
    REQUIREMENTS_PATH,
    actual_parcels,
    project_readiness,
    relationship_status,
    validate_project,
    validate_requirements,
)
from house_design.predesign import (
    PREDESIGN_PATH,
    PREDESIGN_RULES_PATH,
    PRIVATE_BUDGET_PATH,
    build_predesign_report,
)
from house_design.revision_integrity import REVISION_ROOT

RULE_PACK_PATH = ROOT / "rules/kaohsiung_review_rules.json"
REVIEW_ROOT = ROOT / "structured/reviews"


STATUS_LABELS = {
    "pass": "通過",
    "fail": "失敗",
    "warning": "警告",
    "unknown": "未知",
    "not_applicable": "不適用",
    "professional_review": "專業確認",
}


def _finding(
    *,
    rule_id: str,
    status: str,
    domain: str,
    title: str,
    message: str,
    responsible_role: str,
    next_action: str,
    applies_to: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    source: dict[str, Any] | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    if status not in REVIEW_STATUSES:
        raise ContractError(f"invalid finding status: {status}")
    identifier_seed = {
        "rule_id": rule_id,
        "status": status,
        "applies_to": applies_to or {},
        "message": message,
    }
    return {
        "finding_id": f"{rule_id}-{stable_hash(identifier_seed)[:8]}",
        "rule_id": rule_id,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "severity": severity or ("error" if status == "fail" else "advisory"),
        "domain": domain,
        "title": title,
        "message": message,
        "applies_to": applies_to or {},
        "evidence": evidence or [],
        "source": source or {},
        "responsible_role": responsible_role,
        "next_action": next_action,
    }


def _project_findings(project: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for issue in validate_project(project):
        findings.append(
            _finding(
                rule_id="DATA-PROJECT-CONTRACT",
                status="fail",
                domain="data_governance",
                title="專案資料契約不完整",
                message=f"{issue['field']}: {issue['message']}",
                responsible_role="專案資料管理者",
                next_action="修正 inputs/project.json 後重跑 intake validate。",
                evidence=[{"kind": "json_field", "path": "inputs/project.json", "field": issue["field"]}],
                severity="blocking",
            )
        )
    for parcel in actual_parcels(project):
        parcel_id = str(parcel.get("id"))
        area = parcel.get("parcel_area_ping")
        findings.append(
            _finding(
                rule_id="SITE-PARCEL-AREA",
                status="pass" if isinstance(area, (int, float)) and area > 0 else "unknown",
                domain="site",
                title=f"{parcel_id} 基地面積",
                message=(
                    f"正式資料記錄此筆基地約 {area:.1f} 坪；此值只代表基地面積，不代表可建築面積。"
                    if isinstance(area, (int, float))
                    else "尚未提供基地面積。"
                ),
                responsible_role="屋主／建築師",
                next_action="取得地籍謄本或測量成果後，以實際平方公尺更新並保留來源。",
                applies_to={"parcel_id": parcel_id, "building_id": parcel_id},
                evidence=[{"kind": "selected_site_fact", "path": "inputs/project.json"}],
            )
        )
        coverage = parcel.get("building_coverage_ratio")
        if isinstance(coverage, (int, float)) and isinstance(parcel.get("parcel_area_sqm"), (int, float)):
            footprint = float(parcel["parcel_area_sqm"]) * float(coverage)
            status = "professional_review"
            message = f"依輸入建蔽率初算最大建築面積 {footprint:.2f} m²；仍須套用退縮、法定空地及基地形狀。"
        else:
            status = "unknown"
            message = "建蔽率尚未確認，不能由 32 坪基地直接推定首層可蓋 32 坪。"
        findings.append(
            _finding(
                rule_id="SITE-BUILDABLE-FOOTPRINT",
                status=status,
                domain="building_regulation",
                title=f"{parcel_id} 可建築面積",
                message=message,
                responsible_role="建築師",
                next_action="依地號、分區、道路與退縮條件完成書面法規預檢。",
                applies_to={"parcel_id": parcel_id, "building_id": parcel_id},
                evidence=[{"kind": "json_field", "path": "inputs/project.json", "field": "building_coverage_ratio"}],
                source={"rule_pack": "kaohsiung-house-review-v1"},
            )
        )
    return findings


def _readiness_findings(project: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for fact in project_readiness(project)["facts"]:
        if fact["known"]:
            continue
        missing = [str(item["parcel_id"]) for item in fact["parcels"] if not item["known"]]
        is_selection = fact["key"] == "site_selection"
        results.append(
            _finding(
                rule_id=f"SITE-READINESS-{fact['key'].upper()}",
                status="unknown",
                domain="site",
                title=f"{fact['label']}尚未完成",
                message=(
                    "土地尚未選定；三筆相鄰、每筆約 32 坪目前只是選地目標。"
                    if is_selection
                    else f"缺少基地：{', '.join(missing)}。未知資料不得顯示為法規通過。"
                ),
                responsible_role="建築師／屋主",
                next_action=(
                    "先以候選土地評分與建築師書面初篩選地，再建立正式 selected_site。"
                    if is_selection
                    else f"取得並記錄三筆基地的{fact['label']}、來源文件與確認日期。"
                ),
                applies_to={"parcel_ids": missing},
                evidence=[{"kind": "json_field", "path": "inputs/project.json", "field": fact["key"]}],
            )
        )
    return results


RELATIONSHIP_GEOMETRIC_TYPES = {"adjacent", "not_stacked_over", "not_stacked_under", "stacked_over"}
_EXACT_GEOMETRY_METHODS = {"closed_dxf_polyline", "professional_verified_polygon", "surveyed_polygon"}
_RELATIONSHIP_TOLERANCE_MM = 250.0
_STACKED_OVERLAP_RATIO = 0.8


def _floor_order(floor_id: Any) -> float | None:
    value = str(floor_id or "")
    if value == "floor-rf":
        return 999.0
    if value.startswith("floor-b"):
        suffix = value[len("floor-b"):]
        return -float(suffix) if suffix.isdigit() else None
    if value.startswith("floor-"):
        suffix = value[len("floor-"):]
        return float(suffix) if suffix.isdigit() else None
    return None


def _bbox_separations(bbox_a: Any, bbox_b: Any) -> tuple[float, float]:
    """Per-axis separation between two bboxes: >0 apart, 0 touching, <0 overlapping."""

    ax0, ay0, ax1, ay1 = (float(item) for item in bbox_a)
    bx0, by0, bx1, by1 = (float(item) for item in bbox_b)
    return max(bx0 - ax1, ax0 - bx1), max(by0 - ay1, ay0 - by1)


def _bbox_overlap_extents(bbox_a: Any, bbox_b: Any) -> tuple[float, float]:
    ax0, ay0, ax1, ay1 = (float(item) for item in bbox_a)
    bx0, by0, bx1, by1 = (float(item) for item in bbox_b)
    return min(ax1, bx1) - max(ax0, bx0), min(ay1, by1) - max(ay0, by0)


def _exact_rectangle(space: dict[str, Any]) -> bool:
    """A precise polygon that is exactly the axis-aligned bbox rectangle."""

    bbox = space.get("bbox_mm")
    polygon = space.get("polygon_mm")
    if str(space.get("geometry_method") or "") not in _EXACT_GEOMETRY_METHODS:
        return False
    if not _valid_bbox(bbox) or not _valid_polygon(polygon):
        return False
    points = [(float(point[0]), float(point[1])) for point in polygon]
    if points and points[0] == points[-1]:
        points = points[:-1]
    if len(points) != 4 or len(set(points)) != 4:
        return False
    x0, y0, x1, y1 = (float(item) for item in bbox)
    corners = {(x0, y0), (x1, y0), (x1, y1), (x0, y1)}
    return all(point in corners for point in points)


def _coordinate_verified(model: dict[str, Any]) -> bool:
    """Cross-floor plan comparison is only trustworthy with verified floor alignment."""

    coordinate = model.get("coordinate_system")
    if not isinstance(coordinate, dict) or str(coordinate.get("status") or "") not in VERIFIED_COORDINATE_STATUSES:
        return False
    reference_points = coordinate.get("reference_points")
    return (
        bool(coordinate.get("axis"))
        and all(str(coordinate.get(key) or "").strip() for key in ("verified_by", "verified_at", "method"))
        and isinstance(reference_points, list)
        and len(reference_points) >= 2
    )


def _storey_elevations(model: dict[str, Any]) -> dict[tuple[str, str], float]:
    elevations: dict[tuple[str, str], float] = {}
    for storey in model.get("entities", {}).get("storeys", []) or []:
        if not (isinstance(storey, dict) and storey.get("building_id") and storey.get("floor_id")):
            continue
        elevation = storey.get("elevation_mm")
        if isinstance(elevation, (int, float)) and not isinstance(elevation, bool):
            elevations[(str(storey["building_id"]), str(storey["floor_id"]))] = float(elevation)
    return elevations


def _vertical_order(
    space_a: dict[str, Any], space_b: dict[str, Any], elevations: dict[tuple[str, str], float]
) -> str | None:
    key_a = (str(space_a.get("building_id") or ""), str(space_a.get("floor_id") or ""))
    key_b = (str(space_b.get("building_id") or ""), str(space_b.get("floor_id") or ""))
    elevation_a, elevation_b = elevations.get(key_a), elevations.get(key_b)
    if elevation_a is not None and elevation_b is not None and elevation_a != elevation_b:
        return "above" if elevation_a > elevation_b else "below"
    order_a, order_b = _floor_order(key_a[1]), _floor_order(key_b[1])
    if order_a is None or order_b is None:
        return None
    if order_a > order_b:
        return "above"
    if order_a < order_b:
        return "below"
    return "same"


def _relationship_findings(
    requirement: dict[str, Any],
    model: dict[str, Any],
    spaces: dict[str, dict[str, Any]],
    elevations: dict[tuple[str, str], float],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    pending = 0
    for relationship in requirement.get("relationships") or []:
        if not isinstance(relationship, dict):
            continue
        if relationship_status(requirement, relationship) != "confirmed":
            pending += 1
            continue
        findings.append(_confirmed_relationship_finding(requirement, relationship, model, spaces, elevations))
    if pending:
        requirement_id = str(requirement["id"])
        applies_to = dict(requirement.get("applies_to") or {})
        applies_to["requirement_id"] = requirement_id
        findings.append(
            _finding(
                rule_id="REQ-RELATIONSHIP-PENDING",
                status="unknown",
                domain="space_program",
                title=f"{requirement['title']}：{pending} 條空間關係尚待屋主確認",
                message="需求確認後才新增或修改的空間關係不會自動生效，檢核暫不採計。",
                responsible_role="屋主",
                next_action="重新匯出決策表，把這些關係一併確認。",
                applies_to=applies_to,
                evidence=[{"kind": "relationship", "requirement_id": requirement_id, "count": pending}],
            )
        )
    return findings


def _confirmed_relationship_finding(
    requirement: dict[str, Any],
    relationship: dict[str, Any],
    model: dict[str, Any],
    spaces: dict[str, dict[str, Any]],
    elevations: dict[tuple[str, str], float],
) -> dict[str, Any]:
    relationship_type = str(relationship.get("type") or "")
    target = str(relationship.get("target") or "")
    label = RELATIONSHIP_TYPES.get(relationship_type, relationship_type)
    requirement_id = str(requirement["id"])
    applies_to = dict(requirement.get("applies_to") or {})
    applies_to["requirement_id"] = requirement_id
    source_space = spaces.get(requirement_id)
    target_space = None if target in RELATIONSHIP_SPECIAL_TARGETS else spaces.get(target)
    evidence = [
        {
            "kind": "relationship",
            "type": relationship_type,
            "target": target,
            "source_entity_id": (source_space or {}).get("id"),
            "target_entity_id": (target_space or {}).get("id"),
        }
    ]
    hard = requirement.get("priority") == "must"

    def emit(status: str, message: str, next_action: str, responsible_role: str = "建築師") -> dict[str, Any]:
        return _finding(
            rule_id=f"REQ-RELATIONSHIP-{relationship_type.upper()}",
            status=status,
            domain="space_program",
            title=f"{requirement['title']}空間關係：{label}",
            message=message,
            responsible_role=responsible_role,
            next_action=next_action,
            applies_to=applies_to,
            evidence=evidence,
        )

    if target in RELATIONSHIP_SPECIAL_TARGETS or relationship_type not in RELATIONSHIP_GEOMETRIC_TYPES:
        return emit(
            "professional_review",
            "此關係無法只用圖面幾何自動判定，須由專業者在圖面上複核。",
            "請建築師在平面圖上標示此關係並說明如何滿足。",
        )
    if source_space is None or target_space is None:
        missing = requirement_id if source_space is None else target
        return emit(
            "unknown",
            f"找不到 {missing} 的圖面空間綁定，無法判定此關係。",
            "在 IFC 空間或 DXF layer mapping 中綁定 requirement_id 後重新檢核。",
            responsible_role="建築師／圖面資料管理者",
        )
    bbox_a = source_space.get("bbox_mm")
    bbox_b = target_space.get("bbox_mm")
    if not _valid_bbox(bbox_a) or not _valid_bbox(bbox_b):
        return emit("unknown", "關係兩端缺少可驗證的 bbox 幾何，無法判定。", "補齊圖面空間幾何後重新檢核。")
    if str(source_space.get("building_id") or "") != str(target_space.get("building_id") or ""):
        return emit(
            "professional_review",
            "兩個空間位於不同棟，此關係須由建築師說明如何成立。",
            "請建築師確認跨棟關係的設計意圖。",
        )
    order = _vertical_order(source_space, target_space, elevations)
    if order is None:
        return emit("unknown", "無法判定兩個空間的樓層上下關係。", "請補齊樓層編號或 elevation 證據後重新檢核。")

    def violation(message: str) -> dict[str, Any]:
        return emit("fail" if hard else "warning", message, "請調整平面配置，或與屋主重新確認此關係。")

    if relationship_type == "adjacent":
        if order != "same":
            return violation("兩個空間位於不同樓層，無法相鄰。")
        sep_x, sep_y = _bbox_separations(bbox_a, bbox_b)
        if sep_x > 0 and sep_y > 0:
            return violation(f"兩空間平面分離（X 間距 {sep_x:.0f} mm、Y 間距 {sep_y:.0f} mm），未相鄰。")
        if sep_x < 0 and sep_y < 0:
            return emit(
                "professional_review",
                "兩空間的 bbox 平面範圍重疊，請建築師確認牆體與實際相鄰介面。",
                "請建築師在平面圖上標示兩空間的實際邊界。",
            )
        gap = max(sep_x, sep_y)
        overlap_x, overlap_y = _bbox_overlap_extents(bbox_a, bbox_b)
        shared = overlap_y if sep_x >= sep_y else overlap_x
        if gap > _RELATIONSHIP_TOLERANCE_MM:
            return violation(f"兩空間平面間距 {gap:.0f} mm，超過 {_RELATIONSHIP_TOLERANCE_MM:.0f} mm 門檻，未相鄰。")
        if shared <= 0:
            return violation("兩空間只在角落接觸，沒有可用的相鄰介面。")
        if _exact_rectangle(source_space) and _exact_rectangle(target_space):
            return emit(
                "pass",
                f"兩空間以 {gap:.0f} mm 間距相鄰，共用介面長度 {shared:.0f} mm。",
                "仍請建築師複核牆厚與門位。",
            )
        return emit(
            "professional_review",
            f"兩空間 bbox 相鄰（間距 {gap:.0f} mm），但幾何非精確矩形，請確認實際相鄰介面。",
            "請建築師以精確 polygon 複核相鄰關係。",
        )

    if relationship_type in {"not_stacked_over", "not_stacked_under"}:
        violated = "above" if relationship_type == "not_stacked_over" else "below"
        if order != violated:
            return emit("pass", "樓層上下關係未違反此限制。", "仍請建築師複核結構與管線配置。")
        if not _coordinate_verified(model):
            return emit(
                "unknown",
                "兩空間上下壓疊與否須比對各樓層平面座標，但座標系統尚未驗證。",
                "請先完成樓層平面對位證據（coordinate_system），再重新檢核。",
            )
        overlap_x, overlap_y = _bbox_overlap_extents(bbox_a, bbox_b)
        if overlap_x <= _RELATIONSHIP_TOLERANCE_MM or overlap_y <= _RELATIONSHIP_TOLERANCE_MM:
            return emit(
                "pass",
                f"上下樓層平面投影重疊未超過 {_RELATIONSHIP_TOLERANCE_MM:.0f} mm 門檻，不構成壓疊。",
                "仍請建築師複核結構與管線配置。",
            )
        if _exact_rectangle(source_space) and _exact_rectangle(target_space):
            return violation(
                f"兩空間上下壓疊（X 重疊 {overlap_x:.0f} mm、Y 重疊 {overlap_y:.0f} mm），違反此限制。"
            )
        return emit(
            "professional_review",
            f"上下樓層 bbox 重疊（X {overlap_x:.0f} mm、Y {overlap_y:.0f} mm），但幾何非精確矩形，請確認實際壓疊範圍。",
            "請建築師以精確 polygon 複核壓疊關係。",
        )

    # stacked_over: the source must sit above the target with aligned footprints.
    if order != "above":
        return violation("來源空間未位於目標空間正上方，不符合上下對齊關係。")
    if not _coordinate_verified(model):
        return emit(
            "unknown",
            "上下對齊程度須比對各樓層平面座標，但座標系統尚未驗證。",
            "請先完成樓層平面對位證據（coordinate_system），再重新檢核。",
        )
    overlap_x, overlap_y = _bbox_overlap_extents(bbox_a, bbox_b)
    area_a = (bbox_a[2] - bbox_a[0]) * (bbox_a[3] - bbox_a[1])
    area_b = (bbox_b[2] - bbox_b[0]) * (bbox_b[3] - bbox_b[1])
    smaller = min(float(area_a), float(area_b))
    ratio = max(overlap_x, 0.0) * max(overlap_y, 0.0) / smaller if smaller > 0 else 0.0
    if _exact_rectangle(source_space) and _exact_rectangle(target_space):
        if ratio >= _STACKED_OVERLAP_RATIO:
            return emit("pass", f"上下投影重疊比例 {ratio:.0%}，達到對齊目標。", "仍請建築師複核結構對位。")
        return violation(f"上下投影重疊比例只有 {ratio:.0%}，未達 {_STACKED_OVERLAP_RATIO:.0%} 對齊目標。")
    return emit(
        "professional_review",
        f"上下投影 bbox 重疊比例約 {ratio:.0%}，但幾何非精確矩形，請確認實際對齊狀況。",
        "請建築師以精確 polygon 複核上下對齊。",
    )


def _requirement_findings(requirements: dict[str, Any], model: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    contract_issues = validate_requirements(requirements)
    for issue in contract_issues:
        findings.append(
            _finding(
                rule_id="DATA-REQUIREMENT-CONTRACT",
                status="fail",
                domain="data_governance",
                title="需求資料契約不完整",
                message=f"{issue['field']}: {issue['message']}",
                responsible_role="需求管理者",
                next_action="修正 requirements.json 後再執行檢核。",
                evidence=[{"kind": "json_field", "path": "inputs/requirements.json", "field": issue["field"]}],
                severity="blocking",
            )
        )
    items = requirements.get("requirements", [])
    candidates = [item for item in items if item.get("status") == "candidate"]
    if candidates:
        findings.append(
            _finding(
                rule_id="REQ-OWNER-CONFIRMATION",
                status="unknown",
                domain="requirements",
                title=f"{len(candidates)} 項既有想法尚待屋主確認",
                message="舊版 AI 建議與 area brief 不會自動成為硬需求。",
                responsible_role="屋主",
                next_action="逐項標記 confirmed、rejected，並將 confirmed 項目設定 must／should／could。",
                evidence=[{"kind": "requirement_register", "path": "inputs/requirements.json", "count": len(candidates)}],
            )
        )
    confirmed = [item for item in items if item.get("status") == "confirmed"]
    spaces = {str(item.get("requirement_id")): item for item in model.get("entities", {}).get("spaces", []) if item.get("requirement_id")}
    doors = model.get("entities", {}).get("doors", [])
    elevations = _storey_elevations(model)
    for requirement in confirmed:
        requirement_id = str(requirement["id"])
        space = spaces.get(requirement_id)
        applies_to = dict(requirement.get("applies_to") or {})
        applies_to["requirement_id"] = requirement_id
        findings.extend(_relationship_findings(requirement, model, spaces, elevations))
        if space is None:
            findings.append(
                _finding(
                    rule_id="REQ-DRAWING-BINDING",
                    status="unknown",
                    domain="requirements",
                    title=f"圖面尚未對應需求：{requirement['title']}",
                    message="沒有找到帶有相同 requirement_id 的圖面空間，不能判斷是否滿足。",
                    responsible_role="建築師／圖面資料管理者",
                    next_action="在 IFC 空間或 DXF layer mapping 中綁定 requirement_id。",
                    applies_to=applies_to,
                    evidence=[{"kind": "requirement", "requirement_id": requirement_id}],
                )
            )
            continue
        constraints = requirement.get("constraints") or {}
        minimum = constraints.get("min_sqm")
        actual_area = space.get("area_sqm")
        if isinstance(minimum, (int, float)):
            if not isinstance(actual_area, (int, float)):
                status = "unknown"
                message = "圖面空間缺少可追溯面積。"
            elif actual_area + 1e-6 < minimum:
                status = "fail" if requirement.get("priority") == "must" else "warning"
                message = f"圖面 {actual_area:.2f} m²，小於確認下限 {minimum:.2f} m²。"
            else:
                status = "pass"
                message = f"圖面 {actual_area:.2f} m²，達到確認下限 {minimum:.2f} m²。"
            findings.append(
                _finding(
                    rule_id="REQ-MIN-AREA",
                    status=status,
                    domain="space_program",
                    title=f"{requirement['title']}面積",
                    message=message,
                    responsible_role="建築師／屋主",
                    next_action="在家具與結構配置完成後再次確認淨使用面積。",
                    applies_to=applies_to,
                    evidence=[{"kind": "normalized_space", "entity_id": space.get("id"), "area_sqm": actual_area}],
                )
            )
        if constraints.get("wheelchair_turn"):
            width, depth = space.get("width_mm"), space.get("depth_mm")
            if not isinstance(width, (int, float)) or not isinstance(depth, (int, float)):
                status, message = "unknown", "圖面未提供可驗證淨寬、淨深，家具後迴轉圈仍未知。"
            elif min(width, depth) < 1500:
                status, message = "fail", f"空間短邊 {min(width, depth):.0f} mm，小於 1500 mm 迴轉圈。"
            else:
                status, message = "professional_review", "空房淨尺寸可容納 1500 mm 圈，但仍須放入床、櫃體與衛浴設備複核。"
            findings.append(
                _finding(
                    rule_id="ACC-WHEELCHAIR-TURN",
                    status=status,
                    domain="accessibility",
                    title=f"{requirement['title']}輪椅迴轉",
                    message=message,
                    responsible_role="建築師／無障礙顧問",
                    next_action="在正式家具與設備配置圖上標出直徑 1500 mm 淨空圓。",
                    applies_to=applies_to,
                    evidence=[{"kind": "normalized_space", "entity_id": space.get("id"), "width_mm": width, "depth_mm": depth}],
                )
            )
        minimum_door = constraints.get("door_clear_mm")
        if isinstance(minimum_door, (int, float)):
            local_id = requirement_id.rsplit(".", 1)[-1]
            related = [
                door
                for door in doors
                if door.get("requirement_id") == requirement_id or door.get("to") in {local_id, requirement_id, space.get("source_id")}
            ]
            widths = [float(item["clear_width_mm"]) for item in related if isinstance(item.get("clear_width_mm"), (int, float))]
            if not widths:
                status, message = "unknown", "找不到綁定此空間的門淨寬資料。"
            elif max(widths) < minimum_door:
                status, message = "fail", f"最大可追溯門淨寬 {max(widths):.0f} mm，小於確認值 {minimum_door:.0f} mm。"
            else:
                status, message = "pass", f"可追溯門淨寬 {max(widths):.0f} mm，達到確認值 {minimum_door:.0f} mm。"
            findings.append(
                _finding(
                    rule_id="ACC-DOOR-CLEAR",
                    status=status,
                    domain="accessibility",
                    title=f"{requirement['title']}門淨寬",
                    message=message,
                    responsible_role="建築師",
                    next_action="在門窗表與平面圖交叉確認完成面後淨寬。",
                    applies_to=applies_to,
                    evidence=[{"kind": "normalized_door", "entity_ids": [item.get("id") for item in related]}],
                )
            )
    return findings


def _import_findings(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    revision_id = str(manifest.get("revision_id"))
    status = manifest.get("status")
    if status == "legacy_assumption":
        findings.append(
            _finding(
                rule_id="DRAWING-LEGACY-ASSUMPTION",
                status="fail",
                domain="data_governance",
                title="舊版 32 坪量體不可作為現行基準",
                message="此版將 32 坪選地目標當成每層建築面積；目前土地尚未選定，不能推定任何可建量體。",
                responsible_role="專案資料管理者",
                next_action="收到建築師 PDF＋IFC／DXF 後建立新的不可變 revision。",
                applies_to={"revision_id": revision_id},
                evidence=[{"kind": "revision_manifest", "revision_id": revision_id}],
                severity="blocking",
            )
        )
    elif status in {"needs_mapping", "partial"}:
        findings.append(
            _finding(
                rule_id="DRAWING-SEMANTIC-MAPPING",
                status="unknown",
                domain="drawing_import",
                title="圖面語意對應尚未完成",
                message="原始檔已保存，但樓層、房間、門窗或單位尚未完整對應。",
                responsible_role="圖面資料管理者／建築師",
                next_action="補 mapping JSON 或請設計方輸出含 IfcSpace 的 IFC。",
                applies_to={"revision_id": revision_id},
                evidence=[{"kind": "revision_manifest", "revision_id": revision_id}],
            )
        )
    for issue in manifest.get("issues") or []:
        code = str(issue.get("code") or "DRAWING-IMPORT")
        if code == "LEGACY_FOOTPRINT_ASSUMPTION":
            continue
        severity = issue.get("severity")
        result_status = "fail" if severity == "blocking" and "PARSE_ERROR" in code else "unknown"
        findings.append(
            _finding(
                rule_id=code,
                status=result_status,
                domain="drawing_import",
                title="圖面匯入需要處理",
                message=str(issue.get("message") or code),
                responsible_role="圖面資料管理者",
                next_action="依匯入訊息補依賴、單位或圖層對應後建立新 revision。",
                applies_to={"revision_id": revision_id},
                evidence=[{"kind": "revision_import_issue", "details": issue.get("details")}],
            )
        )
    return findings


def _rule_pack_findings(rule_pack: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rule in rule_pack.get("rules") or []:
        if rule.get("domain") not in {"building_regulation", "accessibility", "fire", "structural", "mep"}:
            continue
        source = rule.get("source") or {}
        release_eligible = bool(rule.get("release_eligible"))
        has_citation = all(source.get(key) for key in ("title", "article", "url", "verified_at"))
        if not release_eligible or not has_citation:
            findings.append(
                _finding(
                    rule_id=f"RULE-SOURCE-{rule.get('rule_id')}",
                    status="professional_review",
                    domain="rule_governance",
                    title=f"規則尚未取得專業法源確認：{rule.get('title')}",
                    message="此規則不會產生法規通過結論，直到精確條文、版本、適用條件及查證人完成。",
                    responsible_role=str(rule.get("verification_owner") or "建築師"),
                    next_action="由負責專業人員確認法源與基地適用性，再將 release_eligible 設為 true。",
                    source=source,
                    evidence=[{"kind": "rule_pack", "path": "rules/kaohsiung_review_rules.json"}],
                )
            )
    return findings


def _coordination_findings(project: dict[str, Any]) -> list[dict[str, Any]]:
    values = []
    for index, title in enumerate(project.get("compound", {}).get("shared_items_to_confirm", []), start=1):
        values.append(
            _finding(
                rule_id=f"COMPOUND-COORD-{index:02d}",
                status="professional_review",
                domain="compound_coordination",
                title=title,
                message="三筆基地分開檢核後，仍需以整體配置確認跨基地介面與權責。",
                responsible_role="建築師／相關技師／屋主",
                next_action="在總配置圖、設備系統圖與產權管理約定上共同確認。",
                applies_to={"parcel_ids": ["A", "B", "C"]},
                evidence=[{"kind": "project_policy", "path": "inputs/project.json"}],
            )
        )
    return values


def _report_hash_payload(report: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(report)
    value.pop("generated_at", None)
    value.pop("report_hash", None)
    value.pop("signoff", None)
    if isinstance(value.get("planning"), dict):
        value["planning"].pop("generated_at", None)
    return value


def validate_signoff(report: dict[str, Any], signoff: dict[str, Any] | None) -> dict[str, Any]:
    if not signoff:
        return {"valid": False, "reason": "missing", "status": "professional_review"}
    allowed = {"approved", "pass", "approved_with_conditions"}
    identity = str(signoff.get("reviewer_name") or "").strip().lower()
    invalid_identity = not identity or any(token in identity for token in ("claude", "chatgpt", "codex", "ai assistant"))
    valid = (
        signoff.get("decision") in allowed
        and signoff.get("reviewer_kind") == "human"
        and bool(signoff.get("reviewer_role"))
        and bool(signoff.get("reviewer_date"))
        and not invalid_identity
        and signoff.get("related_report_hash") == report.get("report_hash")
        and signoff.get("revision_id") == report.get("revision", {}).get("revision_id")
    )
    return {
        "valid": valid,
        "reason": "valid" if valid else "identity_revision_or_hash_mismatch",
        "status": "pass" if valid else "professional_review",
        "reviewer_role": signoff.get("reviewer_role"),
        "decision": signoff.get("decision"),
    }


def build_review(
    *,
    revision_id: str,
    project_path: Path = PROJECT_PATH,
    requirements_path: Path = REQUIREMENTS_PATH,
    rule_pack_path: Path = RULE_PACK_PATH,
    predesign_path: Path | None = None,
    predesign_rule_pack_path: Path = PREDESIGN_RULES_PATH,
    private_budget_path: Path | None = PRIVATE_BUDGET_PATH,
    revision_root: Path = REVISION_ROOT,
    previous_revision: str | None = None,
    signoff_path: Path | None = None,
    coordination_path: Path | None = None,
    previous_coordination_path: Path | None = None,
    planning_register_path: Path | None = None,
) -> dict[str, Any]:
    project = read_json(project_path)
    requirements = read_json(requirements_path)
    rule_pack = read_json(rule_pack_path)
    planning = None
    if planning_register_path is not None or project_path.resolve() == PROJECT_PATH.resolve():
        from house_design.planning import REGISTER_PATH, build_risk_review

        planning = build_risk_review(project_path=project_path, requirements_path=requirements_path,
                                     register_path=planning_register_path or REGISTER_PATH,
                                     rules_path=predesign_rule_pack_path)
    manifest, model = load_revision(revision_id, revision_root)
    if previous_coordination_path and not previous_revision:
        raise ContractError("--previous-coordination requires --previous")
    coordination = coordination_review(
        model, read_json(coordination_path) if coordination_path else None,
        manifest["content_hash"], requirements,
    )
    coordination_changes = None
    if previous_revision:
        previous_manifest, previous_model = load_revision(previous_revision, revision_root)
        previous_coordination = coordination_review(
            previous_model, read_json(previous_coordination_path) if previous_coordination_path else None,
            previous_manifest["content_hash"], requirements,
        )
        coordination_changes = compare_coordination(previous_coordination, coordination)
    model3d_readiness = assess_model3d_readiness(manifest, model)
    if predesign_path is None and project_path.resolve() == PROJECT_PATH.resolve():
        predesign_path = PREDESIGN_PATH
    if predesign_path is not None:
        predesign_report = build_predesign_report(
            project_path=project_path,
            predesign_path=predesign_path,
            rule_pack_path=predesign_rule_pack_path,
            private_budget_path=private_budget_path,
        )
        active_predesign_findings = [item for item in predesign_report["findings"] if item["gate_active"]]
        predesign_summary = {
            "current_phase": predesign_report["current_phase"],
            "readiness": predesign_report["readiness"],
            "gate": predesign_report["gate"],
            "private_budget": predesign_report["private_budget"],
            "report_hash": predesign_report["report_hash"],
        }
    else:
        active_predesign_findings = []
        predesign_summary = None
    findings = [
        *active_predesign_findings,
        *_project_findings(project),
        *_readiness_findings(project),
        *_import_findings(manifest),
        *_requirement_findings(requirements, model),
        *_rule_pack_findings(rule_pack),
        *_coordination_findings(project),
        *coordination["findings"],
    ]
    order = {"fail": 0, "warning": 1, "unknown": 2, "professional_review": 3, "pass": 4, "not_applicable": 5}
    findings.sort(key=lambda item: (order[item["status"]], item["domain"], item["rule_id"], item["finding_id"]))
    counts = Counter(item["status"] for item in findings)
    comparison = None
    if previous_revision:
        comparison = compare_revisions(
            before_revision=previous_revision, after_revision=revision_id, root=revision_root
        )
    report: dict[str, Any] = {
        "schema": "house-review-report-v1",
        "generated_at": utc_now(),
        "project": {
            "project_id": project.get("project_id"),
            "name": project.get("name"),
            "jurisdiction": project.get("jurisdiction"),
            "stage": project.get("stage"),
            "parcel_relationship": project.get("parcel_relationship")
            or (project.get("site_search") or {}).get("target_scenario", {}).get("parcel_relationship"),
        },
        "revision": {
            "revision_id": revision_id,
            "label": manifest.get("label"),
            "status": manifest.get("status"),
            "content_hash": manifest.get("content_hash"),
        },
        "readiness": project_readiness(project),
        "predesign": predesign_summary,
        "requirements_summary": {
            "total": len(requirements.get("requirements", [])),
            "candidate": sum(1 for item in requirements.get("requirements", []) if item.get("status") == "candidate"),
            "confirmed": sum(1 for item in requirements.get("requirements", []) if item.get("status") == "confirmed"),
            "rejected": sum(1 for item in requirements.get("requirements", []) if item.get("status") == "rejected"),
        },
        "model_summary": {key: len(value) for key, value in model.get("entities", {}).items()},
        "model3d_readiness": model3d_readiness,
        "status_counts": {status: counts.get(status, 0) for status in REVIEW_STATUSES},
        "release": {
            "eligible": counts.get("fail", 0) == 0 and counts.get("unknown", 0) == 0 and counts.get("professional_review", 0) == 0,
            "policy": "fail、unknown 或 professional_review 任一存在即不得宣稱整體合規。",
        },
        "findings": findings,
        "comparison": comparison,
        "coordination": coordination,
        "coordination_changes": coordination_changes,
        "planning": planning,
        "model": model,
    }
    if planning:
        report["release"]["eligible"] = bool(report["release"]["eligible"] and planning["readiness"]["eligible_for_decision_freeze"])
        report["release"]["planning_decision_ready"] = planning["readiness"]["eligible_for_decision_freeze"]
    report["report_hash"] = stable_hash(_report_hash_payload(report))
    signoff = read_json(signoff_path) if signoff_path and signoff_path.exists() else None
    report["signoff"] = validate_signoff(report, signoff)
    report["release"]["eligible"] = bool(report["release"]["eligible"] and report["signoff"]["valid"])
    return report


def review_markdown(report: dict[str, Any]) -> str:
    revision = report["revision"]
    counts = report["status_counts"]
    model3d = report.get("model3d_readiness") or {}
    model3d_counts = model3d.get("counts") or {}
    lines = [
        f"# 住宅設計檢核報告 · {revision['revision_id']} {revision.get('label') or ''}",
        "",
        f"- Report hash: `{report['report_hash']}`",
        f"- 基地資料完成度：**{report['readiness']['percent']}%**",
        f"- 前期到期項目完成度：**{(report.get('predesign') or {}).get('readiness', {}).get('percent', 0)}%**",
        f"- 前期硬阻擋：**{(report.get('predesign') or {}).get('gate', {}).get('active_blockers', 0)} 項**",
        f"- 現行 revision 3D：**{'可進入產圖' if model3d.get('eligible') else '已阻擋'}**"
        f"（可渲染權威空間 {model3d_counts.get('authoritative_renderable_spaces', 0)}"
        f"／{model3d_counts.get('total_spaces', 0)}）",
        f"- 需求：{report['requirements_summary']['confirmed']} 已確認／{report['requirements_summary']['candidate']} 待確認",
        f"- 結論：**{'可進入專業放行' if report['release']['eligible'] else '不可宣稱整體合規'}**",
        "",
        "| 狀態 | 數量 |",
        "|---|---:|",
    ]
    for status in ("fail", "warning", "unknown", "professional_review", "pass", "not_applicable"):
        lines.append(f"| {STATUS_LABELS[status]} | {counts.get(status, 0)} |")
    lines.extend(
        [
            "",
            "## 現行 revision 3D",
            "",
            f"- 狀態：**{'ready' if model3d.get('eligible') else 'blocked'}**",
            f"- 來源類型：{', '.join(model3d.get('source_kinds') or []) or '無'}",
            f"- 座標狀態：`{(model3d.get('coordinate_system') or {}).get('status', 'unknown')}`",
            f"- 空間：{model3d_counts.get('authoritative_renderable_spaces', 0)} 個具備權威且可渲染幾何"
            f"／共 {model3d_counts.get('total_spaces', 0)} 個",
            f"- 樓層：{model3d_counts.get('elevated_storeys', 0)} 個有標高"
            f"／共 {model3d_counts.get('total_storeys', 0)} 個",
            f"- 判定原則：{model3d.get('policy') or '未提供'}",
            "",
        ]
    )
    blockers = model3d.get("blockers") or []
    if blockers:
        lines.extend(["### 阻擋原因與下一步", ""])
        for blocker in blockers:
            lines.extend(
                [
                    f"- `{blocker.get('code', 'UNKNOWN')}`：{blocker.get('message', '')}",
                    f"  - 下一步：{blocker.get('next_action', '')}",
                ]
            )
        lines.append("")
    else:
        lines.extend(["目前沒有 3D readiness 阻擋；此判定只代表輸入可產圖，不等同設計合規。", ""])
    if report.get("planning"):
        p = report["planning"]
        lines.extend(["## 防漏項與當期決策", "", "[完整決策／驗收總表](risk-review.html)", "",
                      f"需求已追蹤 {p['summary']['tracked_requirements']}/{p['summary']['total_requirements']}（不代表已驗證）。", "",
                      f"當期未完成：{len(p['readiness']['due_open_ids'])}；未到期項目僅提前提醒。", ""])
    if report.get("coordination"):
        lines.extend(["## 建築／裝潢套繪", "", "[可列印套繪與數值明細](coordination.html)", "",
                      "僅確認指定檢查，不等同全案合規；套繪更新後需重新簽認。", ""])
        for change in report.get("coordination_changes") or []:
            lines.append(f"- `{change['check_id']}`：{change['state']}")
        lines.append("")
    lines.extend(["## 檢核事項", ""])
    for finding in report["findings"]:
        applies = finding.get("applies_to") or {}
        location = "/".join(
            str(applies[key])
            for key in ("building_id", "floor_id")
            if applies.get(key)
        )
        lines.extend(
            [
                f"### [{finding['status_label']}] {finding['title']}",
                "",
                f"- 編號：`{finding['finding_id']}`" + (f" · 位置：{location}" if location else ""),
                f"- 說明：{finding['message']}",
                f"- 負責角色：{finding['responsible_role']}",
                f"- 下一步：{finding['next_action']}",
                "",
            ]
        )
    return "\n".join(lines)


def write_review(
    report: dict[str, Any], *, output_root: Path = REVIEW_ROOT
) -> Path:
    revision_id = str(report["revision"]["revision_id"])
    directory = output_root / revision_id
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "report.json", report)
    if report.get("planning"):
        from house_design.planning import write_risk_review

        write_risk_review(report["planning"], directory)
    (directory / "report.md").write_text(review_markdown(report), encoding="utf-8", newline="\n")
    if report.get("coordination"):
        (directory / "coordination.html").write_text(
            coordination_html(report["coordination"]), encoding="utf-8", newline="\n"
        )
    return directory

from __future__ import annotations

from typing import Any

from house_design.contracts import ContractError

AUTHORITATIVE_GEOMETRY_PROVENANCE = {
    "architect_dxf",
    "architect_ifc",
    "professional_verified",
    "surveyed",
}
VERIFIED_COORDINATE_STATUSES = {"verified", "verified_aligned", "georeferenced"}


def _valid_bbox(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return False
    if not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
        return False
    x0, y0, x1, y1 = (float(item) for item in value)
    return x1 > x0 and y1 > y0


def _valid_polygon(value: Any) -> bool:
    if not isinstance(value, list) or len(value) < 3:
        return False
    points: list[tuple[float, float]] = []
    for point in value:
        if (
            not isinstance(point, (list, tuple))
            or len(point) < 2
            or not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in point[:2])
        ):
            return False
        points.append((float(point[0]), float(point[1])))
    twice_area = sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )
    return abs(twice_area) > 0


def _has_spatial_location(entity: dict[str, Any]) -> bool:
    return bool(entity.get("building_id") and entity.get("floor_id"))


def _verification_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def assess_model3d_readiness(
    manifest: dict[str, Any], model: dict[str, Any], level: str = "space_block"
) -> dict[str, Any]:
    """Assess whether a revision has traceable geometry for current 3D output."""

    if level not in {"space_block", "walkthrough"}:
        raise ContractError("model3d readiness level must be space_block or walkthrough")
    entities = model.get("entities") if isinstance(model.get("entities"), dict) else {}
    spaces = entities.get("spaces") if isinstance(entities.get("spaces"), list) else []
    storeys = entities.get("storeys") if isinstance(entities.get("storeys"), list) else []
    walls = entities.get("walls") if isinstance(entities.get("walls"), list) else []
    doors = entities.get("doors") if isinstance(entities.get("doors"), list) else []
    windows = entities.get("windows") if isinstance(entities.get("windows"), list) else []
    stairs = entities.get("stairs") if isinstance(entities.get("stairs"), list) else []
    equipment = entities.get("equipment") if isinstance(entities.get("equipment"), list) else []
    sources = manifest.get("sources") if isinstance(manifest.get("sources"), list) else []
    source_kinds = sorted(
        {
            str(source.get("kind"))
            for source in sources
            if isinstance(source, dict) and source.get("kind")
        }
    )

    spaces_with_geometry = [
        space for space in spaces if isinstance(space, dict) and _valid_bbox(space.get("bbox_mm"))
    ]
    spaces_with_location = [space for space in spaces if isinstance(space, dict) and _has_spatial_location(space)]
    authoritative_spaces = [
        space
        for space in spaces
        if isinstance(space, dict)
        and space.get("geometry_provenance") in AUTHORITATIVE_GEOMETRY_PROVENANCE
    ]
    elevated_storeys = [
        storey
        for storey in storeys
        if isinstance(storey, dict)
        and storey.get("building_id")
        and storey.get("floor_id")
        and isinstance(storey.get("elevation_mm"), (int, float))
        and not isinstance(storey.get("elevation_mm"), bool)
    ]
    elevated_locations = {
        (str(storey["building_id"]), str(storey["floor_id"])) for storey in elevated_storeys
    }
    renderable_spaces = [
        space
        for space in spaces
        if isinstance(space, dict)
        and _valid_bbox(space.get("bbox_mm"))
        and _has_spatial_location(space)
        and (str(space["building_id"]), str(space["floor_id"])) in elevated_locations
    ]
    authoritative_renderable_spaces = [
        space
        for space in renderable_spaces
        if space.get("geometry_provenance") in AUTHORITATIVE_GEOMETRY_PROVENANCE
    ]
    located_space_keys = {
        (str(space["building_id"]), str(space["floor_id"])) for space in spaces_with_location
    }
    missing_elevation_locations = sorted(located_space_keys - elevated_locations)

    coordinate_system = model.get("coordinate_system")
    if not isinstance(coordinate_system, dict):
        coordinate_system = {"status": "unknown"}
    coordinate_status = str(coordinate_system.get("status") or "unknown")

    import_issues: list[dict[str, Any]] = []
    seen_issues: set[tuple[str, str]] = set()
    manifest_issues = manifest.get("issues") if isinstance(manifest.get("issues"), list) else []
    model_issues = model.get("import_issues") if isinstance(model.get("import_issues"), list) else []
    for issue in [*manifest_issues, *model_issues]:
        if not isinstance(issue, dict) or issue.get("severity") != "blocking":
            continue
        key = (str(issue.get("code") or "UNKNOWN"), str(issue.get("message") or ""))
        if key in seen_issues:
            continue
        seen_issues.add(key)
        import_issues.append(issue)

    blockers: list[dict[str, Any]] = []

    def block(code: str, message: str, next_action: str, **details: Any) -> None:
        item: dict[str, Any] = {"code": code, "message": message, "next_action": next_action}
        if details:
            item["details"] = details
        blockers.append(item)

    provenance_values = {
        str(space.get("geometry_provenance") or "missing")
        for space in spaces
        if isinstance(space, dict)
    }
    legacy_revision = (
        manifest.get("status") == "legacy_assumption"
        or "legacy_parametric_json" in source_kinds
        or "legacy_assumption" in provenance_values
    )
    if legacy_revision:
        block(
            "REVISION_LEGACY_ASSUMPTION",
            "此版是封存的歷史假設，不是建築師現行圖面，不能作為現行 3D。",
            "收到建築師 PDF 加 IFC，或 PDF 加已對應圖層的 DXF 後，以新 revision id 匯入。",
        )
    machine_sources = {"ifc", "dxf"}.intersection(source_kinds)
    if manifest.get("status") != "ready" or not machine_sources:
        block(
            "REVISION_IMPORT_NOT_READY",
            (
                f"版次匯入狀態是 {manifest.get('status') or 'unknown'}，"
                f"machine-readable 來源是 {', '.join(source_kinds) or '無'}，尚未達到 3D 匯入條件。"
            ),
            "修正來源檔、單位與語意 mapping 後，以新的不可變版次重新匯入。",
            revision_status=manifest.get("status") or "unknown",
            source_kinds=source_kinds,
        )
    if import_issues:
        block(
            "IMPORT_BLOCKING_ISSUES",
            f"版次仍有 {len(import_issues)} 個 blocking import issue。",
            "先處理列出的匯入問題，再建立新 revision；不要直接修改既有不可變版次。",
            issue_codes=[str(issue.get("code") or "UNKNOWN") for issue in import_issues],
        )
    if len(spaces_with_geometry) != len(spaces):
        missing = len(spaces) - len(spaces_with_geometry)
        block(
            "SPACE_GEOMETRY_MISSING",
            f"{missing} 個空間缺少有效的 bbox_mm 平面幾何。",
            "由建築師 IFC 擷取空間邊界，或以 DXF 圖層 mapping 提供每個空間的可追溯幾何。",
            missing_spaces=missing,
        )
    if not spaces:
        block(
            "SPACE_GEOMETRY_MISSING",
            "版次沒有任何可供 3D 建模的空間實體。",
            "請在 IFC 提供 IfcSpace，或以 DXF mapping 建立具名空間。",
            missing_spaces=0,
        )
    if len(spaces_with_location) != len(spaces):
        missing = len(spaces) - len(spaces_with_location)
        block(
            "SPACE_LOCATION_MISSING",
            f"{missing} 個空間缺少 building_id 或 floor_id。",
            "在 IFC 修正空間 containment，或在 DXF mapping 明確指定棟別與樓層。",
            missing_spaces=missing,
        )
    if len(authoritative_spaces) != len(spaces):
        missing = len(spaces) - len(authoritative_spaces)
        block(
            "NON_AUTHORITATIVE_GEOMETRY",
            f"{missing} 個空間的幾何不是可追溯的建築師／測量來源。",
            "以 architect_dxf、architect_ifc、professional_verified 或 surveyed 來源取代推估幾何。",
            non_authoritative_spaces=missing,
            provenance=sorted(provenance_values),
        )
    if missing_elevation_locations:
        block(
            "STOREY_ELEVATION_MISSING",
            f"{len(missing_elevation_locations)} 個使用中的棟別／樓層缺少數值標高。",
            "由 IFC 樓層或經建築師確認的 mapping 提供 elevation_mm，包含 1F 的 0 mm。",
            locations=[
                {"building_id": building, "floor_id": floor}
                for building, floor in missing_elevation_locations
            ],
        )
    coordinate_evidence_valid = (
        coordinate_status in VERIFIED_COORDINATE_STATUSES
        and bool(coordinate_system.get("axis"))
        and _verification_value(coordinate_system.get("verified_by"))
        and _verification_value(coordinate_system.get("verified_at"))
        and _verification_value(coordinate_system.get("method"))
        and isinstance(coordinate_system.get("reference_points"), list)
        and len(coordinate_system["reference_points"]) >= 2
    )
    if not coordinate_evidence_valid:
        block(
            "COORDINATE_SYSTEM_UNVERIFIED",
            f"座標系統狀態是 {coordinate_status}，或缺少人員、日期、方法與至少兩個基準點證據。",
            "確認 IFC／DXF 的原點、軸向、單位與樓層基準，並記錄 verified_by、verified_at、method 及 reference_points。",
            coordinate_status=coordinate_status,
        )

    space_blockers = list(blockers)
    walkthrough_extra: list[dict[str, Any]] = []

    def walk_block(code: str, message: str, next_action: str, **details: Any) -> None:
        item: dict[str, Any] = {"code": code, "message": message, "next_action": next_action}
        if details:
            item["details"] = details
        walkthrough_extra.append(item)

    exact_geometry_methods = {"closed_dxf_polyline", "professional_verified_polygon", "surveyed_polygon"}
    exact_spaces = [
        space
        for space in spaces
        if isinstance(space, dict)
        and _valid_polygon(space.get("polygon_mm"))
        and space.get("geometry_method") in exact_geometry_methods
    ]
    if len(exact_spaces) != len(spaces):
        walk_block(
            "EXACT_SPACE_POLYGON_MISSING",
            f"{len(spaces) - len(exact_spaces)} 個空間只有 bbox 或近似 hull，不能宣稱可走入的精確邊界。",
            "由建築師提供閉合 DXF 空間 polyline，或經專業確認的精確 polygon。",
        )
    located_wall_keys = {
        (str(item.get("building_id")), str(item.get("floor_id")))
        for item in walls
        if isinstance(item, dict) and _has_spatial_location(item) and _valid_bbox(item.get("bbox_mm"))
    }
    missing_wall_locations = sorted(located_space_keys - located_wall_keys)
    if missing_wall_locations:
        walk_block(
            "WALL_GEOMETRY_MISSING",
            f"{len(missing_wall_locations)} 個使用中的棟層沒有可追溯牆體幾何。",
            "在 IFC 提供 IfcWall，或以 DXF entity/layer mapping 標記 wall。",
            locations=[{"building_id": item[0], "floor_id": item[1]} for item in missing_wall_locations],
        )
    height_by_location = {
        (str(item.get("building_id")), str(item.get("floor_id"))): item.get("height_mm")
        for item in storeys
        if isinstance(item, dict)
    }
    spaces_without_height = [
        item
        for item in spaces
        if isinstance(item, dict)
        and not (
            isinstance(item.get("height_mm"), (int, float))
            or isinstance(
                height_by_location.get((str(item.get("building_id")), str(item.get("floor_id")))),
                (int, float),
            )
        )
    ]
    if spaces_without_height:
        walk_block(
            "SPACE_HEIGHT_MISSING",
            f"{len(spaces_without_height)} 個空間缺少經確認的樓層或空間高度。",
            "在 storeys.height_mm 或 space.height_mm 記錄設計方確認的高度。",
        )
    incomplete_openings = [
        item
        for item in [*doors, *windows]
        if not isinstance(item, dict)
        or not _valid_bbox(item.get("bbox_mm"))
        or not isinstance(item.get("height_mm"), (int, float))
    ]
    if not doors and not windows:
        walk_block(
            "OPENING_GEOMETRY_MISSING",
            "模型沒有任何門窗開口；走入式模型不能驗證動線、採光或碰撞。",
            "提供帶位置、寬度與高度的門窗 IFC／DXF 幾何。",
        )
    elif incomplete_openings:
        walk_block(
            "OPENING_GEOMETRY_INCOMPLETE",
            f"{len(incomplete_openings)} 個門窗缺少位置或高度。",
            "補齊每個門窗的 bbox/polygon 與 height_mm；完成面淨寬仍須獨立證據。",
        )
    storeys_by_building: dict[str, set[str]] = {}
    for item in storeys:
        if isinstance(item, dict) and item.get("building_id") and item.get("floor_id"):
            storeys_by_building.setdefault(str(item["building_id"]), set()).add(str(item["floor_id"]))
    multistorey_buildings = {building for building, values in storeys_by_building.items() if len(values) > 1}
    stair_buildings = {
        str(item.get("building_id"))
        for item in stairs
        if isinstance(item, dict) and item.get("building_id") and _valid_bbox(item.get("bbox_mm"))
    }
    if multistorey_buildings - stair_buildings:
        walk_block(
            "STAIR_GEOMETRY_MISSING",
            "多樓層棟別缺少可追溯的樓梯幾何。",
            "在 IFC 提供 IfcStair，或以 DXF mapping 明確標示各層樓梯範圍與連接。",
            buildings=sorted(multistorey_buildings - stair_buildings),
        )
    scope = model.get("walkthrough_scope") if isinstance(model.get("walkthrough_scope"), dict) else {}
    equipment_scope = scope.get("equipment") if isinstance(scope.get("equipment"), dict) else {}
    equipment_declared = equipment_scope.get("status") in {"verified_complete", "verified_not_applicable"}
    equipment_evidence = (
        equipment_declared
        and _verification_value(equipment_scope.get("verified_by"))
        and _verification_value(equipment_scope.get("verified_at"))
        and bool(equipment_scope.get("evidence"))
    )
    incomplete_equipment = [
        item for item in equipment if not isinstance(item, dict) or not _valid_bbox(item.get("bbox_mm"))
    ]
    if not equipment_evidence or incomplete_equipment:
        walk_block(
            "EQUIPMENT_SCOPE_UNVERIFIED",
            "固定設備範圍尚未以清單或不適用聲明完成查核。",
            "提供設備位置幾何，並在 walkthrough_scope.equipment 留下查核人、日期與證據。",
            incomplete_equipment=len(incomplete_equipment),
        )

    walkthrough_blockers = [*space_blockers, *walkthrough_extra]
    counts = {
        "total_spaces": len(spaces),
        "spaces_with_geometry": len(spaces_with_geometry),
        "spaces_with_location": len(spaces_with_location),
        "authoritative_spaces": len(authoritative_spaces),
        "renderable_spaces": len(renderable_spaces),
        "authoritative_renderable_spaces": len(authoritative_renderable_spaces),
        "total_storeys": len(storeys),
        "elevated_storeys": len(elevated_storeys),
        "exact_polygon_spaces": len(exact_spaces),
        "walls": len(walls),
        "openings": len(doors) + len(windows),
        "stairs": len(stairs),
        "equipment": len(equipment),
    }
    selected_blockers = space_blockers if level == "space_block" else walkthrough_blockers
    eligible = not selected_blockers
    return {
        "schema": "house-model3d-readiness-v2",
        "revision_id": manifest.get("revision_id") or model.get("revision_id"),
        "level": level,
        "status": "ready" if eligible else "blocked",
        "eligible": eligible,
        "policy": (
            "space_block 只代表可追溯空間量體；walkthrough 還必須具備精確 polygon、牆、門窗高度、樓梯與設備證據。"
        ),
        "levels": {
            "space_block": {
                "status": "ready" if not space_blockers else "blocked",
                "eligible": not space_blockers,
                "blockers": space_blockers,
            },
            "walkthrough": {
                "status": "ready" if not walkthrough_blockers else "blocked",
                "eligible": not walkthrough_blockers,
                "blockers": walkthrough_blockers,
            },
        },
        "source_kinds": source_kinds,
        "coordinate_system": coordinate_system,
        "counts": counts,
        "blockers": selected_blockers,
        "next_actions": [item["next_action"] for item in selected_blockers],
    }

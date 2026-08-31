from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from house_design.contracts import (
    ContractError,
    ROOT,
    read_json,
    relative_to_root,
    sha256_file,
    stable_hash,
    utc_now,
    write_json,
)


REVISION_ROOT = ROOT / "inputs/revisions"
REVISION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
AUTHORITATIVE_GEOMETRY_PROVENANCE = {
    "architect_dxf",
    "architect_ifc",
    "professional_verified",
    "surveyed",
}
VERIFIED_COORDINATE_STATUSES = {"verified", "verified_aligned", "georeferenced"}


def revision_dir(revision_id: str, root: Path = REVISION_ROOT) -> Path:
    if not REVISION_ID_RE.fullmatch(revision_id):
        raise ContractError("revision id may contain only letters, digits, dot, underscore and dash")
    return root / revision_id


def _copy_source(source: Path, destination_dir: Path) -> Path:
    source = source.resolve()
    if not source.is_file():
        raise ContractError(f"Drawing source does not exist: {source}")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    if destination.exists() and sha256_file(destination) != sha256_file(source):
        raise ContractError(f"A different source file already exists at {destination}")
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination


def _source_record(path: Path, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "file": relative_to_root(path),
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _empty_model(revision_id: str) -> dict[str, Any]:
    return {
        "schema": "house-normalized-model-v1",
        "revision_id": revision_id,
        "generated_at": utc_now(),
        "units": {"length": "mm", "area": "sqm"},
        "coordinate_system": {"status": "unknown"},
        "provenance": [],
        "entities": {
            "buildings": [],
            "storeys": [],
            "spaces": [],
            "doors": [],
            "windows": [],
            "equipment": [],
            "drawing_geometry": [],
        },
        "import_issues": [],
    }


def _parse_pdf(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    try:
        try:
            import pymupdf as fitz  # type: ignore[import-not-found]
        except ImportError:
            import fitz  # type: ignore[import-not-found,no-redef]
    except ImportError:
        return (
            {"parser_status": "dependency_missing", "page_count": None, "pages": []},
            [
                {
                    "code": "PDF_DEPENDENCY_MISSING",
                    "severity": "blocking",
                    "message": "Install requirements-import.txt to inspect PDF pages.",
                }
            ],
        )
    try:
        document = fitz.open(path)
        pages = [
            {
                "page": index + 1,
                "width_pt": round(page.rect.width, 3),
                "height_pt": round(page.rect.height, 3),
                "rotation_deg": page.rotation,
            }
            for index, page in enumerate(document)
        ]
        metadata = {key: value for key, value in (document.metadata or {}).items() if value}
        document.close()
    except Exception as exc:  # PyMuPDF raises several format-specific exceptions.
        return (
            {"parser_status": "error", "page_count": None, "pages": []},
            [{"code": "PDF_PARSE_ERROR", "severity": "blocking", "message": str(exc)}],
        )
    return {"parser_status": "parsed", "page_count": len(pages), "pages": pages, "metadata": metadata}, issues


def _unit_scale_from_dxf_code(code: int) -> float | None:
    # DXF $INSUNITS values converted to millimetres.
    return {
        1: 25.4,  # inch
        2: 304.8,  # foot
        4: 1.0,  # millimetre
        5: 10.0,  # centimetre
        6: 1000.0,  # metre
    }.get(code)


def _dxf_bbox(entity: Any, bbox_module: Any) -> list[float] | None:
    try:
        extents = bbox_module.extents([entity], fast=True)
        if not extents.has_data:
            return None
        return [
            round(float(extents.extmin.x), 3),
            round(float(extents.extmin.y), 3),
            round(float(extents.extmax.x), 3),
            round(float(extents.extmax.y), 3),
        ]
    except Exception:
        return None


def _parse_dxf(
    path: Path, model: dict[str, Any], mapping: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        import ezdxf  # type: ignore[import-not-found]
        from ezdxf import bbox  # type: ignore[import-not-found]
    except ImportError:
        return (
            {"parser_status": "dependency_missing"},
            [
                {
                    "code": "DXF_DEPENDENCY_MISSING",
                    "severity": "blocking",
                    "message": "Install requirements-import.txt to inspect DXF geometry.",
                }
            ],
        )
    try:
        document = ezdxf.readfile(path)
    except Exception as exc:
        return (
            {"parser_status": "error"},
            [{"code": "DXF_PARSE_ERROR", "severity": "blocking", "message": str(exc)}],
        )

    unit_code = int(document.header.get("$INSUNITS", 0) or 0)
    scale = _unit_scale_from_dxf_code(unit_code)
    issues: list[dict[str, Any]] = []
    if scale is None:
        declared = mapping.get("dxf_unit_scale_to_mm")
        if isinstance(declared, (int, float)) and declared > 0:
            scale = float(declared)
        else:
            issues.append(
                {
                    "code": "DXF_UNITS_UNKNOWN",
                    "severity": "blocking",
                    "message": "DXF units are unset or unsupported; provide dxf_unit_scale_to_mm in the mapping file.",
                }
            )
            scale = 1.0

    layer_mapping = mapping.get("layers") if isinstance(mapping.get("layers"), dict) else {}
    layers_seen: set[str] = set()
    mapped_count = 0
    drawing_count = 0
    for entity in document.modelspace():
        layer = str(entity.dxf.layer)
        layers_seen.add(layer)
        raw_bbox = _dxf_bbox(entity, bbox)
        if raw_bbox is None:
            continue
        box = [round(value * scale, 3) for value in raw_bbox]
        handle = str(entity.dxf.handle or drawing_count)
        entity_type = entity.dxftype()
        model["entities"]["drawing_geometry"].append(
            {
                "id": f"DXF:{layer}:{handle}",
                "source_id": handle,
                "source_layer": layer,
                "geometry_type": entity_type,
                "bbox_mm": box,
                "source_file": relative_to_root(path),
            }
        )
        drawing_count += 1
        config = layer_mapping.get(layer)
        if not isinstance(config, dict):
            continue
        kind = config.get("kind")
        if kind not in {"space", "door", "window", "equipment"}:
            continue
        collection = {"space": "spaces", "door": "doors", "window": "windows", "equipment": "equipment"}[kind]
        x0, y0, x1, y1 = box
        width, depth = abs(x1 - x0), abs(y1 - y0)
        record: dict[str, Any] = {
            "id": f"DXF:{layer}:{handle}",
            "source_id": handle,
            "source_layer": layer,
            "building_id": config.get("building_id"),
            "floor_id": config.get("floor_id"),
            "name": config.get("name") or layer,
            "bbox_mm": box,
            "width_mm": round(width, 3),
            "depth_mm": round(depth, 3),
            "source_file": relative_to_root(path),
            "geometry_provenance": "architect_dxf",
        }
        if config.get("requirement_id"):
            record["requirement_id"] = config["requirement_id"]
        if kind == "space":
            record["area_sqm"] = round(width * depth / 1_000_000, 4)
        elif kind in {"door", "window"}:
            # Opening symbols are normally a long leaf/opening dimension plus
            # a short wall-thickness dimension. The long extent is therefore
            # the usable width; taking the short extent would report a 100 mm
            # wall thickness as the door clear width.
            record["clear_width_mm"] = round(max(width, depth), 3)
        model["entities"][collection].append(record)
        mapped_count += 1

    unmapped = sorted(layer for layer in layers_seen if layer not in layer_mapping)
    if not layer_mapping:
        issues.append(
            {
                "code": "DXF_LAYER_MAPPING_REQUIRED",
                "severity": "blocking",
                "message": "No semantic layer mapping was supplied; raw geometry is preserved but cannot prove room or door checks.",
                "details": {"layers": sorted(layers_seen)},
            }
        )
    elif unmapped:
        issues.append(
            {
                "code": "DXF_LAYERS_UNMAPPED",
                "severity": "warning",
                "message": f"{len(unmapped)} DXF layers have no semantic mapping.",
                "details": {"layers": unmapped},
            }
        )
    return (
        {
            "parser_status": "parsed",
            "insunits": unit_code,
            "unit_scale_to_mm": scale,
            "layers": sorted(layers_seen),
            "geometry_count": drawing_count,
            "semantic_entity_count": mapped_count,
        },
        issues,
    )


def _ifc_quantity_area(element: Any) -> float | None:
    try:
        import ifcopenshell.util.element as ifc_element  # type: ignore[import-not-found]

        quantities = ifc_element.get_psets(element, qtos_only=True)
    except Exception:
        return None
    for qto in quantities.values():
        for key in ("NetFloorArea", "GrossFloorArea", "Area"):
            value = qto.get(key) if isinstance(qto, dict) else None
            if isinstance(value, (int, float)) and value > 0:
                return float(value)
    return None


def _ifc_container(element: Any) -> Any | None:
    try:
        import ifcopenshell.util.element as ifc_element  # type: ignore[import-not-found]

        # Physical elements are commonly linked with IfcRelContainedInSpatialStructure,
        # while IfcSpace and IfcBuildingStorey are often linked through
        # IfcRelAggregates. Supporting both is required to recover A/B/C + floor.
        return ifc_element.get_container(element) or ifc_element.get_aggregate(element)
    except Exception:
        return None


def _ifc_spatial_location(
    element: Any,
    storey_by_id: dict[int, str],
    storey_building_by_id: dict[int, str | None],
) -> tuple[str | None, str | None]:
    """Walk the IFC containment chain to the nearest known building storey."""

    container = _ifc_container(element)
    seen: set[int] = set()
    while container is not None:
        try:
            container_id = int(container.id())
        except Exception:
            break
        if container_id in seen:
            break
        seen.add(container_id)
        if container_id in storey_by_id:
            return storey_by_id[container_id], storey_building_by_id.get(container_id)
        container = _ifc_container(container)
    return None, None


def _ifc_building_id(name: str, fallback: str) -> str:
    """Recognize an explicit A/B/C token without mistaking 'Building' for B."""

    match = re.search(r"(?<![A-Z0-9])([ABC])(?![A-Z0-9])", name.upper())
    return match.group(1) if match else fallback


def _ifc_floor_id(name: str, fallback: str) -> str:
    compact = re.sub(r"[\s_-]+", "", name.upper())
    if compact in {"RF", "R/F", "ROOF", "ROOFFLOOR", "屋頂", "屋頂層"}:
        return "floor-rf"
    basement = re.search(r"(?:^|[^A-Z0-9])B0*(\d+)(?:F|$|[^A-Z0-9])", name.upper())
    if basement:
        return f"floor-b{int(basement.group(1))}"
    above = re.search(r"(?:^|[^A-Z0-9])0*(\d+)\s*F(?:$|[^A-Z0-9])", name.upper())
    if not above:
        above = re.search(r"(\d+)\s*(?:樓|層)", name)
    return f"floor-{int(above.group(1))}" if above else fallback


def _parse_ifc(path: Path, model: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        import ifcopenshell  # type: ignore[import-not-found]
        import ifcopenshell.util.unit as ifc_unit  # type: ignore[import-not-found]
    except ImportError:
        return (
            {"parser_status": "dependency_missing"},
            [
                {
                    "code": "IFC_DEPENDENCY_MISSING",
                    "severity": "blocking",
                    "message": "Install requirements-import.txt to inspect IFC objects.",
                }
            ],
        )
    try:
        document = ifcopenshell.open(str(path))
        scale = float(ifc_unit.calculate_unit_scale(document)) * 1000.0
    except Exception as exc:
        return (
            {"parser_status": "error"},
            [{"code": "IFC_PARSE_ERROR", "severity": "blocking", "message": str(exc)}],
        )

    building_by_id: dict[int, str] = {}
    storey_by_id: dict[int, str] = {}
    storey_building_by_id: dict[int, str | None] = {}
    for index, building in enumerate(document.by_type("IfcBuilding")):
        identifier = str(building.GlobalId or f"building-{index + 1}")
        name = str(building.Name or identifier)
        building_id = _ifc_building_id(name, identifier)
        building_by_id[building.id()] = building_id
        model["entities"]["buildings"].append(
            {
                "id": identifier,
                "building_id": building_id,
                "name": name,
                "source_file": relative_to_root(path),
                "geometry_provenance": "architect_ifc",
            }
        )
    for index, storey in enumerate(document.by_type("IfcBuildingStorey")):
        identifier = str(storey.GlobalId or f"storey-{index + 1}")
        name = str(storey.Name or identifier)
        floor_id = _ifc_floor_id(name, identifier)
        container = _ifc_container(storey)
        building_id = building_by_id.get(container.id()) if container is not None else None
        raw_elevation = getattr(storey, "Elevation", None)
        elevation = round(float(raw_elevation) * scale, 3) if raw_elevation is not None else None
        storey_by_id[storey.id()] = floor_id
        storey_building_by_id[storey.id()] = building_id
        model["entities"]["storeys"].append(
            {
                "id": identifier,
                "building_id": building_id,
                "floor_id": floor_id,
                "name": name,
                "elevation_mm": elevation,
                "source_file": relative_to_root(path),
                "geometry_provenance": "architect_ifc",
            }
        )

    for index, space in enumerate(document.by_type("IfcSpace")):
        identifier = str(space.GlobalId or f"space-{index + 1}")
        area = _ifc_quantity_area(space)
        storey_id, building_id = _ifc_spatial_location(space, storey_by_id, storey_building_by_id)
        model["entities"]["spaces"].append(
            {
                "id": identifier,
                "source_id": identifier,
                "building_id": building_id,
                "floor_id": storey_id,
                "name": str(space.LongName or space.Name or identifier),
                "area_sqm": round(area, 4) if area is not None else None,
                "source_file": relative_to_root(path),
                "geometry_provenance": "architect_ifc",
            }
        )
    for ifc_type, collection, width_key in (
        ("IfcDoor", "doors", "OverallWidth"),
        ("IfcWindow", "windows", "OverallWidth"),
    ):
        for index, element in enumerate(document.by_type(ifc_type)):
            identifier = str(element.GlobalId or f"{collection[:-1]}-{index + 1}")
            raw_width = getattr(element, width_key, None)
            storey_id, building_id = _ifc_spatial_location(element, storey_by_id, storey_building_by_id)
            overall_width = round(float(raw_width) * scale, 3) if raw_width else None
            model["entities"][collection].append(
                {
                    "id": identifier,
                    "source_id": identifier,
                    "building_id": building_id,
                    "floor_id": storey_id,
                    "name": str(element.Name or identifier),
                    "overall_width_mm": overall_width,
                    "clear_width_mm": None,
                    "width_note": "IFC OverallWidth is nominal; finished clear width requires a door schedule or verified property.",
                    "source_file": relative_to_root(path),
                    "geometry_provenance": "architect_ifc",
                }
            )
    for ifc_type in ("IfcFlowTerminal", "IfcFlowController", "IfcEnergyConversionDevice"):
        for index, element in enumerate(document.by_type(ifc_type)):
            identifier = str(element.GlobalId or f"equipment-{ifc_type}-{index + 1}")
            storey_id, building_id = _ifc_spatial_location(element, storey_by_id, storey_building_by_id)
            model["entities"]["equipment"].append(
                {
                    "id": identifier,
                    "source_id": identifier,
                    "ifc_type": ifc_type,
                    "building_id": building_id,
                    "floor_id": storey_id,
                    "name": str(element.Name or identifier),
                    "source_file": relative_to_root(path),
                    "geometry_provenance": "architect_ifc",
                }
            )
    entity_count = sum(len(value) for value in model["entities"].values())
    issues: list[dict[str, Any]] = []
    if not model["entities"]["spaces"]:
        issues.append(
            {
                "code": "IFC_NO_SPACES",
                "severity": "warning",
                "message": "IFC contains no IfcSpace objects; room-level checks will remain unknown.",
            }
        )
    return (
        {
            "parser_status": "parsed",
            "schema": str(getattr(document, "schema", "unknown")),
            "unit_scale_to_mm": scale,
            "semantic_entity_count": entity_count,
        },
        issues,
    )


def import_revision(
    *,
    revision_id: str,
    label: str,
    pdf: Path | None = None,
    ifc: Path | None = None,
    dxf: Path | None = None,
    mapping_path: Path | None = None,
    root: Path = REVISION_ROOT,
) -> dict[str, Any]:
    if not any((pdf, ifc, dxf)):
        raise ContractError("at least one --pdf, --ifc or --dxf source is required")
    target = revision_dir(revision_id, root)
    manifest_path = target / "manifest.json"
    if manifest_path.exists():
        raise ContractError(f"revision already exists: {manifest_path}; use a new immutable revision id")
    source_dir = target / "source"
    model = _empty_model(revision_id)
    mapping = read_json(mapping_path) if mapping_path else {}
    mapping_record = None
    if mapping_path:
        immutable_mapping = _copy_source(mapping_path, target / "mapping")
        mapping_record = {
            "file": relative_to_root(immutable_mapping),
            "filename": immutable_mapping.name,
            "sha256": sha256_file(immutable_mapping),
        }
    sources: list[dict[str, Any]] = []
    parser_results: dict[str, Any] = {}
    issues: list[dict[str, Any]] = []

    if pdf:
        path = _copy_source(pdf, source_dir)
        record = _source_record(path, "pdf")
        result, found = _parse_pdf(path)
        record.update(result)
        sources.append(record)
        parser_results["pdf"] = result
        issues.extend(found)
    if ifc:
        path = _copy_source(ifc, source_dir)
        record = _source_record(path, "ifc")
        result, found = _parse_ifc(path, model)
        record.update(result)
        sources.append(record)
        parser_results["ifc"] = result
        issues.extend(found)
    if dxf:
        path = _copy_source(dxf, source_dir)
        record = _source_record(path, "dxf")
        result, found = _parse_dxf(path, model, mapping)
        record.update(result)
        sources.append(record)
        parser_results["dxf"] = result
        issues.extend(found)

    model["provenance"] = [{"source": item["file"], "sha256": item["sha256"]} for item in sources]
    model["import_issues"] = issues
    normalized_count = sum(
        len(model["entities"][key]) for key in ("buildings", "storeys", "spaces", "doors", "windows", "equipment")
    )
    blocking = [item for item in issues if item.get("severity") == "blocking"]
    machine_source = bool(ifc or dxf)
    status = "ready" if machine_source and normalized_count and not blocking else "needs_mapping"
    if machine_source and normalized_count and blocking:
        status = "partial"
    model_path = target / "normalized_model.json"
    write_json(model_path, model)
    manifest = {
        "schema": "house-drawing-revision-v1",
        "revision_id": revision_id,
        "label": label,
        "received_at": utc_now(),
        "status": status,
        "immutable": True,
        "sources": sources,
        "mapping": mapping_record,
        "normalized_model": relative_to_root(model_path),
        "normalized_entity_count": normalized_count,
        "issues": issues,
        "content_hash": stable_hash({"sources": sources, "mapping": mapping, "mapping_record": mapping_record}),
    }
    write_json(manifest_path, manifest)
    return manifest


def seed_legacy_parametric_revision(
    *,
    plan_path: Path = ROOT / "structured/parametric/plan.json",
    revision_id: str = "R000",
    variant_id: str = "f6000_g1",
    root: Path = REVISION_ROOT,
) -> dict[str, Any]:
    """Expose the old 32-ping-footprint scenario as a clearly labelled historical revision."""

    target = revision_dir(revision_id, root)
    manifest_path = target / "manifest.json"
    if manifest_path.exists():
        raise ContractError(f"revision already exists: {manifest_path}")
    plan = read_json(plan_path)
    variant = next((item for item in plan.get("variants", []) if item.get("id") == variant_id), None)
    if variant is None:
        raise ContractError(f"legacy variant not found: {variant_id}")
    model = _empty_model(revision_id)
    model["coordinate_system"] = {"status": "local_assumed", "axis": "legacy_parametric"}
    for building_id, building in (variant.get("buildings") or {}).items():
        model["entities"]["buildings"].append(
            {
                "id": f"LEGACY:{building_id}",
                "building_id": building_id,
                "name": f"{building_id}棟",
                "geometry_provenance": "legacy_assumption",
            }
        )
        for floor in building.get("floors") or []:
            floor_id = str(floor.get("floor_id"))
            model["entities"]["storeys"].append(
                {
                    "id": f"LEGACY:{building_id}:{floor_id}",
                    "building_id": building_id,
                    "floor_id": floor_id,
                    "name": floor.get("label") or floor_id,
                    "geometry_provenance": "legacy_assumption",
                }
            )
            for cell in floor.get("cells") or []:
                rect = cell.get("clear_rect") or cell.get("rect")
                if not isinstance(rect, list) or len(rect) != 4:
                    continue
                x0, y0, x1, y1 = [float(value) for value in rect]
                requirement_id = f"{building_id}.{floor_id}.{cell.get('id')}"
                model["entities"]["spaces"].append(
                    {
                        "id": f"LEGACY:{building_id}:{floor_id}:{cell.get('id')}",
                        "source_id": str(cell.get("id")),
                        "requirement_id": requirement_id,
                        "building_id": building_id,
                        "floor_id": floor_id,
                        "name": cell.get("name") or cell.get("id"),
                        "category": cell.get("kind") or cell.get("role"),
                        "bbox_mm": [x0, y0, x1, y1],
                        "width_mm": round(abs(x1 - x0), 3),
                        "depth_mm": round(abs(y1 - y0), 3),
                        "area_sqm": cell.get("area_sqm") or round(abs(x1 - x0) * abs(y1 - y0) / 1_000_000, 4),
                        "geometry_provenance": "legacy_assumption",
                    }
                )
            for door in floor.get("doors") or []:
                model["entities"]["doors"].append(
                    {
                        "id": f"LEGACY:{building_id}:{floor_id}:{door.get('id')}",
                        "source_id": door.get("id"),
                        "building_id": building_id,
                        "floor_id": floor_id,
                        "from": door.get("from"),
                        "to": door.get("to"),
                        "clear_width_mm": door.get("clear_mm"),
                        "geometry_provenance": "legacy_assumption",
                    }
                )
    model["provenance"] = [
        {
            "source": relative_to_root(plan_path),
            "sha256": sha256_file(plan_path),
            "authority": "legacy_assumption",
            "warning": "32 坪在此模型中是每層建築面積，不是現行每筆基地 32 坪條件。",
        }
    ]
    model["import_issues"] = [
        {
            "code": "LEGACY_FOOTPRINT_ASSUMPTION",
            "severity": "blocking",
            "message": "Historical scenario treats 32 ping as floor footprint and cannot prove the current parcel-based design.",
        }
    ]
    model_path = target / "normalized_model.json"
    write_json(model_path, model)
    manifest = {
        "schema": "house-drawing-revision-v1",
        "revision_id": revision_id,
        "label": "舊版概念配置（32坪建築面積假設）",
        "received_at": utc_now(),
        "status": "legacy_assumption",
        "immutable": True,
        "sources": [
            {
                "kind": "legacy_parametric_json",
                "file": relative_to_root(plan_path),
                "sha256": sha256_file(plan_path),
                "variant_id": variant_id,
            }
        ],
        "normalized_model": relative_to_root(model_path),
        "normalized_entity_count": sum(len(values) for values in model["entities"].values()),
        "issues": model["import_issues"],
        "content_hash": stable_hash({"plan": sha256_file(plan_path), "variant": variant_id}),
    }
    write_json(manifest_path, manifest)
    return manifest


def load_revision(revision_id: str, root: Path = REVISION_ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = revision_dir(revision_id, root)
    manifest = read_json(directory / "manifest.json")
    model_reference = manifest.get("normalized_model")
    if not model_reference:
        raise ContractError(f"revision {revision_id} has no normalized model")
    model_path = ROOT / model_reference if not Path(str(model_reference)).is_absolute() else Path(str(model_reference))
    return manifest, read_json(model_path)


def _valid_bbox(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return False
    if not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
        return False
    x0, y0, x1, y1 = (float(item) for item in value)
    return x1 > x0 and y1 > y0


def _has_spatial_location(entity: dict[str, Any]) -> bool:
    return bool(entity.get("building_id") and entity.get("floor_id"))


def assess_model3d_readiness(manifest: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    """Assess whether a drawing revision has enough authoritative geometry for a current 3D model.

    This gate deliberately does not treat the historical parametric model as evidence. A renderable
    space needs a positive 2D bounding box, an explicit building/floor location and a matching
    storey elevation. Every space must also have professional drawing provenance, and the revision's
    coordinate system must be explicitly verified before the revision is eligible for 3D generation.
    """

    entities = model.get("entities") if isinstance(model.get("entities"), dict) else {}
    spaces = entities.get("spaces") if isinstance(entities.get("spaces"), list) else []
    storeys = entities.get("storeys") if isinstance(entities.get("storeys"), list) else []
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
        (str(space["building_id"]), str(space["floor_id"]))
        for space in spaces_with_location
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
    if coordinate_status not in VERIFIED_COORDINATE_STATUSES:
        block(
            "COORDINATE_SYSTEM_UNVERIFIED",
            f"座標系統狀態是 {coordinate_status}，尚未證明不同來源已正確對齊。",
            "確認 IFC／DXF 的原點、軸向、單位與樓層基準，並將 coordinate_system.status 標記為 verified。",
            coordinate_status=coordinate_status,
        )

    counts = {
        "total_spaces": len(spaces),
        "spaces_with_geometry": len(spaces_with_geometry),
        "spaces_with_location": len(spaces_with_location),
        "authoritative_spaces": len(authoritative_spaces),
        "renderable_spaces": len(renderable_spaces),
        "authoritative_renderable_spaces": len(authoritative_renderable_spaces),
        "total_storeys": len(storeys),
        "elevated_storeys": len(elevated_storeys),
    }
    eligible = not blockers
    return {
        "schema": "house-model3d-readiness-v1",
        "revision_id": manifest.get("revision_id") or model.get("revision_id"),
        "status": "ready" if eligible else "blocked",
        "eligible": eligible,
        "policy": "只有現行 ready 版次的全部空間具備權威幾何、棟層位置、樓層標高及已驗證座標時，才可產生現行 3D。",
        "source_kinds": source_kinds,
        "coordinate_system": coordinate_system,
        "counts": counts,
        "blockers": blockers,
        "next_actions": [item["next_action"] for item in blockers],
    }


def revision_model3d_readiness(revision_id: str, root: Path = REVISION_ROOT) -> dict[str, Any]:
    manifest, model = load_revision(revision_id, root)
    return assess_model3d_readiness(manifest, model)


def list_revisions(root: Path = REVISION_ROOT) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    values = []
    for path in sorted(root.glob("*/manifest.json")):
        try:
            values.append(read_json(path))
        except ContractError:
            continue
    return values


def _entity_identity(entity: dict[str, Any]) -> str:
    return str(entity.get("requirement_id") or entity.get("source_id") or entity.get("id"))


def compare_models(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    collections = ("spaces", "doors", "windows", "equipment")
    watched = {
        "spaces": ("name", "building_id", "floor_id", "area_sqm", "width_mm", "depth_mm", "bbox_mm"),
        "doors": (
            "name",
            "building_id",
            "floor_id",
            "clear_width_mm",
            "overall_width_mm",
            "bbox_mm",
            "from",
            "to",
        ),
        "windows": ("name", "building_id", "floor_id", "clear_width_mm", "overall_width_mm", "bbox_mm"),
        "equipment": ("name", "building_id", "floor_id", "bbox_mm"),
    }
    for collection in collections:
        left = {_entity_identity(item): item for item in before.get("entities", {}).get(collection, [])}
        right = {_entity_identity(item): item for item in after.get("entities", {}).get(collection, [])}
        for identity in sorted(left.keys() - right.keys()):
            changes.append({"entity_type": collection, "entity_id": identity, "change": "removed", "before": left[identity]})
        for identity in sorted(right.keys() - left.keys()):
            changes.append({"entity_type": collection, "entity_id": identity, "change": "added", "after": right[identity]})
        for identity in sorted(left.keys() & right.keys()):
            fields = []
            for field in watched[collection]:
                old, new = left[identity].get(field), right[identity].get(field)
                if old != new:
                    fields.append({"field": field, "before": old, "after": new})
            if fields:
                changes.append(
                    {
                        "entity_type": collection,
                        "entity_id": identity,
                        "change": "modified",
                        "name": right[identity].get("name") or left[identity].get("name"),
                        "building_id": right[identity].get("building_id") or left[identity].get("building_id"),
                        "floor_id": right[identity].get("floor_id") or left[identity].get("floor_id"),
                        "fields": fields,
                    }
                )
    return changes


def compare_revisions(
    *, before_revision: str, after_revision: str, root: Path = REVISION_ROOT
) -> dict[str, Any]:
    before_manifest, before_model = load_revision(before_revision, root)
    after_manifest, after_model = load_revision(after_revision, root)
    changes = compare_models(before_model, after_model)
    return {
        "schema": "house-revision-comparison-v1",
        "generated_at": utc_now(),
        "from": {"revision_id": before_revision, "label": before_manifest.get("label")},
        "to": {"revision_id": after_revision, "label": after_manifest.get("label")},
        "summary": {
            "added": sum(1 for item in changes if item["change"] == "added"),
            "removed": sum(1 for item in changes if item["change"] == "removed"),
            "modified": sum(1 for item in changes if item["change"] == "modified"),
        },
        "changes": changes,
    }

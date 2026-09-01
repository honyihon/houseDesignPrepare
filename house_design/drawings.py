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


def revision_manifest_content_hash(manifest: dict[str, Any]) -> str:
    """Hash every persisted manifest field except the hash itself.

    The normalized model digest is a required manifest field, so this seal
    binds source files, mapping, normalized data and revision metadata in one
    reproducible value.
    """

    return stable_hash({key: value for key, value in manifest.items() if key != "content_hash"})


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
            "walls": [],
            "doors": [],
            "windows": [],
            "stairs": [],
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


def _polygon_area_sqm(points: list[list[float]]) -> float:
    if len(points) < 3:
        return 0.0
    twice_area = sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    )
    return abs(twice_area) / 2_000_000


def _convex_hull(points: list[list[float]]) -> list[list[float]]:
    unique = sorted({(round(point[0], 3), round(point[1], 3)) for point in points})
    if len(unique) <= 2:
        return [[x, y] for x, y in unique]

    def cross(origin: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return [[x, y] for x, y in lower[:-1] + upper[:-1]]


def _dxf_polygon(entity: Any, scale: float) -> list[list[float]] | None:
    """Return a flattened closed DXF polyline in millimetres when available."""

    entity_type = entity.dxftype()
    closed = bool(getattr(entity, "closed", False) or getattr(entity, "is_closed", False))
    if entity_type not in {"LWPOLYLINE", "POLYLINE"} or not closed:
        return None
    try:
        from ezdxf.path import make_path  # type: ignore[import-not-found]

        path = make_path(entity)
        # 1 mm flattening tolerance in final coordinates, bounded for unusual scales.
        tolerance = max(0.001, 1.0 / scale)
        vertices = list(path.flattening(distance=tolerance, segments=8))
        points = [[round(float(vertex.x) * scale, 3), round(float(vertex.y) * scale, 3)] for vertex in vertices]
    except Exception:
        try:
            if entity_type == "LWPOLYLINE":
                points = [
                    [round(float(x) * scale, 3), round(float(y) * scale, 3)]
                    for x, y, *_ in entity.get_points("xy")
                ]
            else:
                points = [
                    [round(float(vertex.dxf.location.x) * scale, 3), round(float(vertex.dxf.location.y) * scale, 3)]
                    for vertex in entity.vertices
                ]
        except Exception:
            return None
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    return points if len(points) >= 3 and _polygon_area_sqm(points) > 0 else None


def _verification_value(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _mapping_context(
    mapping: dict[str, Any], model: dict[str, Any]
) -> list[dict[str, Any]]:
    """Validate and apply mapping-v2 coordinate/storey evidence."""

    if not mapping:
        return []
    issues: list[dict[str, Any]] = []
    schema = mapping.get("schema")
    if schema != "house-drawing-mapping-v2":
        issues.append(
            {
                "code": "DRAWING_MAPPING_V2_REQUIRED",
                "severity": "warning" if schema is None else "blocking",
                "message": "Use schema house-drawing-mapping-v2 to carry coordinate, storey and measurement evidence.",
            }
        )

    coordinate = mapping.get("coordinate_system")
    if coordinate is not None and not isinstance(coordinate, dict):
        issues.append(
            {
                "code": "COORDINATE_SYSTEM_MAPPING_INVALID",
                "severity": "blocking",
                "message": "coordinate_system must be an object.",
            }
        )
    elif isinstance(coordinate, dict):
        status = str(coordinate.get("status") or "unknown")
        evidence_valid = (
            status not in VERIFIED_COORDINATE_STATUSES
            or (
                bool(coordinate.get("axis"))
                and _verification_value(coordinate.get("verified_by"))
                and _verification_value(coordinate.get("verified_at"))
                and _verification_value(coordinate.get("method"))
                and isinstance(coordinate.get("reference_points"), list)
                and len(coordinate["reference_points"]) >= 2
            )
        )
        if evidence_valid:
            model["coordinate_system"] = dict(coordinate)
        else:
            model["coordinate_system"] = {
                **coordinate,
                "declared_status": status,
                "status": "verification_evidence_missing",
            }
            issues.append(
                {
                    "code": "COORDINATE_VERIFICATION_EVIDENCE_MISSING",
                    "severity": "blocking",
                    "message": (
                        "A verified coordinate system requires axis, verified_by, verified_at, method "
                        "and at least two reference_points."
                    ),
                }
            )

    walkthrough_scope = mapping.get("walkthrough_scope")
    if walkthrough_scope is not None:
        if isinstance(walkthrough_scope, dict):
            model["walkthrough_scope"] = dict(walkthrough_scope)
        else:
            issues.append(
                {
                    "code": "WALKTHROUGH_SCOPE_INVALID",
                    "severity": "blocking",
                    "message": "walkthrough_scope must be an object when supplied.",
                }
            )

    storey_mapping = mapping.get("storeys")
    if storey_mapping is None:
        storey_mapping = []
    if not isinstance(storey_mapping, list):
        issues.append(
            {
                "code": "STOREY_MAPPING_INVALID",
                "severity": "blocking",
                "message": "storeys must be an array.",
            }
        )
        return issues
    known_locations: set[tuple[str, str]] = set()
    for index, storey in enumerate(storey_mapping):
        if not isinstance(storey, dict):
            issues.append(
                {
                    "code": "STOREY_MAPPING_INVALID",
                    "severity": "blocking",
                    "message": f"storeys[{index}] must be an object.",
                }
            )
            continue
        building_id = str(storey.get("building_id") or "")
        floor_id = str(storey.get("floor_id") or "")
        elevation = storey.get("elevation_mm")
        evidence = storey.get("evidence")
        complete = (
            bool(building_id and floor_id)
            and isinstance(elevation, (int, float))
            and not isinstance(elevation, bool)
            and _verification_value(storey.get("verified_by"))
            and _verification_value(storey.get("verified_at"))
            and (isinstance(evidence, dict) and bool(evidence.get("reference")))
        )
        location = (building_id, floor_id)
        if not complete or location in known_locations:
            issues.append(
                {
                    "code": "STOREY_VERIFICATION_EVIDENCE_MISSING",
                    "severity": "blocking",
                    "message": (
                        f"storeys[{index}] needs a unique building_id/floor_id, numeric elevation_mm, "
                        "verified_by, verified_at and evidence.reference."
                    ),
                }
            )
            continue
        known_locations.add(location)
        existing = next(
            (
                item
                for item in model["entities"]["storeys"]
                if item.get("building_id") == building_id and item.get("floor_id") == floor_id
            ),
            None,
        )
        values = {
            "building_id": building_id,
            "floor_id": floor_id,
            "name": storey.get("name") or floor_id,
            "elevation_mm": round(float(elevation), 3),
            "height_mm": storey.get("height_mm"),
            "verification": {
                "verified_by": storey["verified_by"],
                "verified_at": storey["verified_at"],
                "evidence": evidence,
            },
        }
        if existing is not None:
            existing.update({key: value for key, value in values.items() if value is not None})
            existing.setdefault("geometry_provenance", "professional_verified")
        else:
            model["entities"]["storeys"].append(
                {
                    "id": f"MAPPING:{building_id}:{floor_id}",
                    **{key: value for key, value in values.items() if value is not None},
                    "geometry_provenance": "professional_verified",
                }
            )
        if not any(item.get("building_id") == building_id for item in model["entities"]["buildings"]):
            model["entities"]["buildings"].append(
                {
                    "id": f"MAPPING:{building_id}",
                    "building_id": building_id,
                    "name": f"{building_id}棟",
                    "geometry_provenance": "professional_verified",
                }
            )
    return issues


def _apply_ifc_entity_mapping(mapping: dict[str, Any], model: dict[str, Any]) -> list[dict[str, Any]]:
    configs = mapping.get("ifc_entities")
    if configs is None:
        return []
    if not isinstance(configs, dict):
        return [
            {
                "code": "IFC_ENTITY_MAPPING_INVALID",
                "severity": "blocking",
                "message": "ifc_entities must be an object keyed by IFC GlobalId.",
            }
        ]
    issues: list[dict[str, Any]] = []
    collections = ("spaces", "walls", "doors", "windows", "stairs", "equipment")
    for source_id, config in configs.items():
        if not isinstance(config, dict):
            issues.append(
                {
                    "code": "IFC_ENTITY_MAPPING_INVALID",
                    "severity": "blocking",
                    "message": f"ifc_entities.{source_id} must be an object.",
                }
            )
            continue
        match = next(
            (
                entity
                for collection in collections
                for entity in model["entities"][collection]
                if str(entity.get("source_id") or entity.get("id")) == str(source_id)
            ),
            None,
        )
        if match is None:
            issues.append(
                {
                    "code": "IFC_ENTITY_MAPPING_TARGET_MISSING",
                    "severity": "blocking",
                    "message": f"IFC mapping target {source_id} was not found in the imported model.",
                }
            )
            continue
        for key in ("building_id", "floor_id", "requirement_id", "name", "category"):
            if config.get(key) is not None:
                match[key] = config[key]
    return issues


def _opening_evidence(config: dict[str, Any], geometry_width: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "overall_width_mm": round(geometry_width, 3),
        "clear_width_mm": None,
        "width_note": "DXF symbol extent is nominal/overall; finished clear width requires explicit verified evidence.",
    }
    declaration = config.get("opening_width")
    if not isinstance(declaration, dict):
        return result
    value = declaration.get("value_mm")
    measurement = declaration.get("measurement")
    evidence = declaration.get("evidence")
    complete = (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
        and measurement in {"finished_clear", "overall", "nominal"}
        and _verification_value(declaration.get("verified_by"))
        and _verification_value(declaration.get("verified_at"))
        and isinstance(evidence, dict)
        and bool(evidence.get("reference"))
    )
    if not complete:
        result["width_note"] = "opening_width declaration is incomplete and was not treated as verified clear width."
        return result
    result["width_evidence"] = dict(declaration)
    if measurement == "finished_clear":
        result["clear_width_mm"] = round(float(value), 3)
        result["width_note"] = "Finished clear width supplied with explicit verification evidence."
    else:
        result["overall_width_mm"] = round(float(value), 3)
        result["width_note"] = f"Verified {measurement} width; finished clear width remains unknown."
    return result


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
    entity_mapping = mapping.get("entities") if isinstance(mapping.get("entities"), dict) else {}
    layers_seen: set[str] = set()
    layers_mapped_by_handle: set[str] = set()
    mapped_count = 0
    drawing_count = 0
    for entity in document.modelspace():
        layer = str(entity.dxf.layer)
        layers_seen.add(layer)
        raw_bbox = _dxf_bbox(entity, bbox)
        if raw_bbox is None:
            continue
        handle = str(entity.dxf.handle or drawing_count)
        entity_type = entity.dxftype()
        polygon = _dxf_polygon(entity, scale)
        if polygon:
            xs = [point[0] for point in polygon]
            ys = [point[1] for point in polygon]
            box = [min(xs), min(ys), max(xs), max(ys)]
        else:
            box = [round(value * scale, 3) for value in raw_bbox]
        geometry_record: dict[str, Any] = {
            "id": f"DXF:{layer}:{handle}",
            "source_id": handle,
            "source_layer": layer,
            "geometry_type": entity_type,
            "bbox_mm": box,
            "source_file": relative_to_root(path),
        }
        if polygon:
            geometry_record["polygon_mm"] = polygon
        model["entities"]["drawing_geometry"].append(
            geometry_record
        )
        drawing_count += 1
        layer_config = layer_mapping.get(layer)
        handle_config = entity_mapping.get(handle) or entity_mapping.get(handle.upper())
        if handle_config is not None and not isinstance(handle_config, dict):
            issues.append(
                {
                    "code": "DXF_ENTITY_MAPPING_INVALID",
                    "severity": "blocking",
                    "message": f"entities.{handle} must be an object.",
                }
            )
            continue
        if isinstance(handle_config, dict):
            layers_mapped_by_handle.add(layer)
        config = {
            **(layer_config if isinstance(layer_config, dict) else {}),
            **(handle_config if isinstance(handle_config, dict) else {}),
        }
        if not config or config.get("ignore") is True:
            continue
        kind = config.get("kind")
        if kind not in {"space", "wall", "door", "window", "stair", "equipment"}:
            continue
        collection = {
            "space": "spaces",
            "wall": "walls",
            "door": "doors",
            "window": "windows",
            "stair": "stairs",
            "equipment": "equipment",
        }[kind]
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
        if polygon:
            record["polygon_mm"] = polygon
            record["geometry_method"] = "closed_dxf_polyline"
        if config.get("requirement_id"):
            record["requirement_id"] = config["requirement_id"]
        for key in ("height_mm", "sill_height_mm", "category", "from", "to"):
            if config.get(key) is not None:
                record[key] = config[key]
        if kind == "space":
            record["area_sqm"] = round(
                _polygon_area_sqm(polygon) if polygon else width * depth / 1_000_000,
                4,
            )
            record["area_method"] = "polygon" if polygon else "bounding_box"
        elif kind in {"door", "window"}:
            record.update(_opening_evidence(config, max(width, depth)))

        ifc_guid = config.get("ifc_guid")
        existing = None
        if ifc_guid:
            existing = next(
                (
                    item
                    for item in model["entities"][collection]
                    if str(item.get("source_id") or item.get("id")) == str(ifc_guid)
                ),
                None,
            )
            if existing is None:
                issues.append(
                    {
                        "code": "IFC_DXF_RECONCILIATION_TARGET_MISSING",
                        "severity": "blocking",
                        "message": f"DXF handle {handle} refers to missing IFC GlobalId {ifc_guid}.",
                    }
                )
        if existing is not None:
            original_source = existing.get("source_file")
            existing.update(
                {
                    key: value
                    for key, value in record.items()
                    if key not in {"id", "source_id", "source_file"} and value is not None
                }
            )
            existing["geometry_provenance"] = "architect_dxf"
            existing["reconciliation"] = {
                "method": "explicit_ifc_guid",
                "ifc_guid": str(ifc_guid),
                "dxf_handle": handle,
                "sources": [value for value in (original_source, record["source_file"]) if value],
            }
        else:
            model["entities"][collection].append(record)
        mapped_count += 1

    unmapped = sorted(
        layer for layer in layers_seen if layer not in layer_mapping and layer not in layers_mapped_by_handle
    )
    if not layer_mapping and not entity_mapping:
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


def _ifc_element_geometry(element: Any, element_kind: str = "IFC element") -> dict[str, Any] | None:
    """Extract a world-coordinate 2D footprint envelope from an IFC mesh.

    IfcOpenShell triangulation is expressed in metres; the normalized model is
    always millimetres. The polygon is explicitly labelled as a convex mesh
    hull so it is never mistaken for an exact concave room boundary.
    """

    try:
        import ifcopenshell.geom as ifc_geom  # type: ignore[import-not-found]

        settings = ifc_geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        shape = ifc_geom.create_shape(settings, element)
        values = list(shape.geometry.verts)
    except Exception:
        return None
    if len(values) < 9 or len(values) % 3:
        return None
    points = [
        [round(float(values[index]) * 1000.0, 3), round(float(values[index + 1]) * 1000.0, 3)]
        for index in range(0, len(values), 3)
    ]
    z_values = [round(float(values[index + 2]) * 1000.0, 3) for index in range(0, len(values), 3)]
    hull = _convex_hull(points)
    if len(hull) < 3:
        return None
    xs = [point[0] for point in hull]
    ys = [point[1] for point in hull]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    result = {
        "bbox_mm": bbox,
        "polygon_mm": hull,
        "width_mm": round(bbox[2] - bbox[0], 3),
        "depth_mm": round(bbox[3] - bbox[1], 3),
        "geometry_method": "ifc_mesh_convex_hull",
        "geometry_note": (
            f"Convex display footprint extracted from {element_kind} mesh; "
            "use mapped DXF for exact concave boundaries."
        ),
    }
    if max(z_values) > min(z_values):
        result["height_mm"] = round(max(z_values) - min(z_values), 3)
    return result


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
        geometry = _ifc_element_geometry(space, "IfcSpace")
        storey_id, building_id = _ifc_spatial_location(space, storey_by_id, storey_building_by_id)
        record: dict[str, Any] = {
                "id": identifier,
                "source_id": identifier,
                "building_id": building_id,
                "floor_id": storey_id,
                "name": str(space.LongName or space.Name or identifier),
                "area_sqm": round(area, 4) if area is not None else None,
                "source_file": relative_to_root(path),
                "geometry_provenance": "architect_ifc",
            }
        if geometry:
            record.update(geometry)
            if area is None:
                record["area_sqm"] = round(_polygon_area_sqm(geometry["polygon_mm"]), 4)
                record["area_method"] = "ifc_mesh_convex_hull"
            else:
                record["area_method"] = "ifc_quantity"
        model["entities"]["spaces"].append(record)
    for ifc_type, collection, width_key in (
        ("IfcDoor", "doors", "OverallWidth"),
        ("IfcWindow", "windows", "OverallWidth"),
    ):
        for index, element in enumerate(document.by_type(ifc_type)):
            identifier = str(element.GlobalId or f"{collection[:-1]}-{index + 1}")
            raw_width = getattr(element, width_key, None)
            geometry = _ifc_element_geometry(element, ifc_type)
            storey_id, building_id = _ifc_spatial_location(element, storey_by_id, storey_building_by_id)
            overall_width = round(float(raw_width) * scale, 3) if raw_width else None
            record = {
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
            if geometry:
                record.update(geometry)
            model["entities"][collection].append(record)
    for ifc_type, collection in (("IfcWall", "walls"), ("IfcStair", "stairs")):
        for index, element in enumerate(document.by_type(ifc_type)):
            identifier = str(element.GlobalId or f"{collection[:-1]}-{index + 1}")
            storey_id, building_id = _ifc_spatial_location(element, storey_by_id, storey_building_by_id)
            geometry = _ifc_element_geometry(element, ifc_type)
            record = {
                "id": identifier,
                "source_id": identifier,
                "building_id": building_id,
                "floor_id": storey_id,
                "name": str(element.Name or identifier),
                "source_file": relative_to_root(path),
                "geometry_provenance": "architect_ifc",
            }
            if geometry:
                record.update(geometry)
            model["entities"][collection].append(record)
    for ifc_type in ("IfcFlowTerminal", "IfcFlowController", "IfcEnergyConversionDevice"):
        for index, element in enumerate(document.by_type(ifc_type)):
            identifier = str(element.GlobalId or f"equipment-{ifc_type}-{index + 1}")
            storey_id, building_id = _ifc_spatial_location(element, storey_by_id, storey_building_by_id)
            geometry = _ifc_element_geometry(element, ifc_type)
            record = {
                "id": identifier,
                "source_id": identifier,
                "ifc_type": ifc_type,
                "building_id": building_id,
                "floor_id": storey_id,
                "name": str(element.Name or identifier),
                "source_file": relative_to_root(path),
                "geometry_provenance": "architect_ifc",
            }
            if geometry:
                record.update(geometry)
            model["entities"]["equipment"].append(record)
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
    issues.extend(_mapping_context(mapping, model))
    issues.extend(_apply_ifc_entity_mapping(mapping, model))
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
        len(model["entities"][key])
        for key in ("buildings", "storeys", "spaces", "walls", "doors", "windows", "stairs", "equipment")
    )
    normalized_space_count = len(model["entities"]["spaces"])
    blocking = [item for item in issues if item.get("severity") == "blocking"]
    machine_source = bool(ifc or dxf)
    status = "ready" if machine_source and normalized_space_count and not blocking else "needs_mapping"
    if machine_source and normalized_space_count and blocking:
        status = "partial"
    model_path = target / "normalized_model.json"
    write_json(model_path, model)
    manifest = {
        "schema": "house-drawing-revision-v2",
        "revision_id": revision_id,
        "label": label,
        "received_at": utc_now(),
        "status": status,
        "immutable": True,
        "sources": sources,
        "mapping": mapping_record,
        "normalized_model": relative_to_root(model_path),
        "normalized_model_sha256": sha256_file(model_path),
        "normalized_entity_count": normalized_count,
        "normalized_space_count": normalized_space_count,
        "issues": issues,
    }
    manifest["content_hash"] = revision_manifest_content_hash(manifest)
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
    immutable_plan = _copy_source(plan_path, target / "source")
    plan = read_json(immutable_plan)
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
            "sha256": sha256_file(immutable_plan),
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
        "schema": "house-drawing-revision-v2",
        "revision_id": revision_id,
        "label": "舊版概念配置（32坪建築面積假設）",
        "received_at": utc_now(),
        "status": "legacy_assumption",
        "immutable": True,
        "sources": [
            {
                "kind": "legacy_parametric_json",
                "file": relative_to_root(immutable_plan),
                "sha256": sha256_file(immutable_plan),
                "variant_id": variant_id,
            }
        ],
        "normalized_model": relative_to_root(model_path),
        "normalized_model_sha256": sha256_file(model_path),
        "normalized_entity_count": sum(len(values) for values in model["entities"].values()),
        "normalized_space_count": len(model["entities"]["spaces"]),
        "issues": model["import_issues"],
    }
    manifest["content_hash"] = revision_manifest_content_hash(manifest)
    write_json(manifest_path, manifest)
    return manifest


def _reference_path(reference: Any) -> Path | None:
    if not isinstance(reference, str) or not reference.strip():
        return None
    path = Path(reference)
    return path if path.is_absolute() else ROOT / path


def verify_revision_integrity(revision_id: str, root: Path = REVISION_ROOT) -> dict[str, Any]:
    """Verify that an immutable revision still matches every stored digest."""

    directory = revision_dir(revision_id, root)
    manifest = read_json(directory / "manifest.json")
    checks: list[dict[str, Any]] = []

    def check(name: str, valid: bool, message: str, **details: Any) -> None:
        item: dict[str, Any] = {"name": name, "valid": valid, "message": message}
        if details:
            item["details"] = details
        checks.append(item)

    manifest_revision = manifest.get("revision_id")
    check(
        "manifest_revision_id",
        manifest_revision == revision_id,
        "manifest revision_id matches the requested immutable directory"
        if manifest_revision == revision_id
        else f"manifest revision_id is {manifest_revision!r}; expected {revision_id!r}",
    )

    sources = manifest.get("sources")
    if not isinstance(sources, list):
        check("sources", False, "manifest sources must be an array")
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                check(f"source[{index}]", False, "source record must be an object")
                continue
            path = _reference_path(source.get("file"))
            expected = source.get("sha256")
            exists = path is not None and path.is_file()
            actual = sha256_file(path) if exists and path is not None else None
            valid = bool(exists and isinstance(expected, str) and expected == actual)
            check(
                f"source[{index}]",
                valid,
                "source digest matches" if valid else "source file is missing or its SHA-256 does not match",
                file=source.get("file"),
                expected_sha256=expected,
                actual_sha256=actual,
            )

    mapping = manifest.get("mapping")
    if mapping is not None:
        if not isinstance(mapping, dict):
            check("mapping", False, "mapping record must be an object or null")
        else:
            path = _reference_path(mapping.get("file"))
            expected = mapping.get("sha256")
            exists = path is not None and path.is_file()
            actual = sha256_file(path) if exists and path is not None else None
            valid = bool(exists and isinstance(expected, str) and expected == actual)
            check(
                "mapping",
                valid,
                "mapping digest matches" if valid else "mapping file is missing or its SHA-256 does not match",
                file=mapping.get("file"),
                expected_sha256=expected,
                actual_sha256=actual,
            )

    model_path = _reference_path(manifest.get("normalized_model"))
    expected_model_hash = manifest.get("normalized_model_sha256")
    model_exists = model_path is not None and model_path.is_file()
    actual_model_hash = sha256_file(model_path) if model_exists and model_path is not None else None
    model_hash_valid = bool(
        model_exists and isinstance(expected_model_hash, str) and expected_model_hash == actual_model_hash
    )
    check(
        "normalized_model_sha256",
        model_hash_valid,
        "normalized model digest matches"
        if model_hash_valid
        else "normalized model is missing, unsealed or its SHA-256 does not match",
        file=manifest.get("normalized_model"),
        expected_sha256=expected_model_hash,
        actual_sha256=actual_model_hash,
    )
    if model_exists and model_path is not None:
        try:
            model = read_json(model_path)
            model_revision = model.get("revision_id")
            check(
                "model_revision_id",
                model_revision == revision_id,
                "normalized model revision_id matches"
                if model_revision == revision_id
                else f"normalized model revision_id is {model_revision!r}; expected {revision_id!r}",
            )
        except ContractError as exc:
            check("model_revision_id", False, str(exc))
    else:
        check("model_revision_id", False, "normalized model is unavailable")

    expected_content_hash = manifest.get("content_hash")
    actual_content_hash = revision_manifest_content_hash(manifest)
    content_hash_valid = isinstance(expected_content_hash, str) and expected_content_hash == actual_content_hash
    check(
        "content_hash",
        content_hash_valid,
        "manifest seal matches" if content_hash_valid else "manifest content hash is missing or does not match",
        expected_sha256=expected_content_hash,
        actual_sha256=actual_content_hash,
    )
    errors = [item for item in checks if not item["valid"]]
    return {
        "schema": "house-revision-integrity-v1",
        "revision_id": revision_id,
        "checked_at": utc_now(),
        "valid": not errors,
        "checks": checks,
        "errors": errors,
    }


def load_revision(revision_id: str, root: Path = REVISION_ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    integrity = verify_revision_integrity(revision_id, root)
    if not integrity["valid"]:
        names = ", ".join(str(item["name"]) for item in integrity["errors"])
        raise ContractError(f"revision {revision_id} failed immutable integrity verification: {names}")
    directory = revision_dir(revision_id, root)
    manifest = read_json(directory / "manifest.json")
    model_path = _reference_path(manifest.get("normalized_model"))
    if model_path is None:
        raise ContractError(f"revision {revision_id} has no normalized model")
    return manifest, read_json(model_path)


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
    points: list[list[float]] = []
    for point in value:
        if (
            not isinstance(point, (list, tuple))
            or len(point) < 2
            or not all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in point[:2])
        ):
            return False
        points.append([float(point[0]), float(point[1])])
    return _polygon_area_sqm(points) > 0


def _has_spatial_location(entity: dict[str, Any]) -> bool:
    return bool(entity.get("building_id") and entity.get("floor_id"))


def assess_model3d_readiness(
    manifest: dict[str, Any], model: dict[str, Any], level: str = "space_block"
) -> dict[str, Any]:
    """Assess whether a drawing revision has enough authoritative geometry for a current 3D model.

    This gate deliberately does not treat the historical parametric model as evidence. A renderable
    space needs a positive 2D bounding box, an explicit building/floor location and a matching
    storey elevation. Every space must also have professional drawing provenance, and the revision's
    coordinate system must be explicitly verified before the revision is eligible for 3D generation.
    """

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
            or isinstance(height_by_location.get((str(item.get("building_id")), str(item.get("floor_id")))), (int, float))
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


def revision_model3d_readiness(
    revision_id: str, root: Path = REVISION_ROOT, level: str = "space_block"
) -> dict[str, Any]:
    manifest, model = load_revision(revision_id, root)
    return assess_model3d_readiness(manifest, model, level)


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

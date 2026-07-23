#!/usr/bin/env python3
"""Validate generated room program and SVG bundle for print-quality gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.standards import load_residential_defaults  # noqa: E402

DEFAULT_PROGRAM = ROOT / "structured" / "room_program.json"
DEFAULT_MANIFEST = ROOT / "structured" / "candidates" / "svg" / "manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated drawing bundle.")
    parser.add_argument("--program", type=Path, default=DEFAULT_PROGRAM, help="Path to room_program.json")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to SVG manifest.json")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat validation warnings as errors (recommended for IFC exports).",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_svg(svg_path: Path) -> tuple[set[str], str]:
    root = ET.fromstring(svg_path.read_text(encoding="utf-8"))
    markers = {element.attrib["data-marker"] for element in root.iter() if element.get("data-marker")}
    visible_text = " ".join("".join(element.itertext()) for element in root.iter() if str(element.tag).endswith("text"))
    return markers, visible_text


def validate_program(program: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    standards = program.get("default_standards", {})
    if not standards:
        warnings.append("room_program.json missing default_standards metadata.")

    rooms = 0
    rooms_missing_notes = 0
    for building in program.get("buildings", []):
        for floor in building.get("floors", []):
            for room in floor.get("rooms", []):
                rooms += 1
                if "notes_rendered" not in room:
                    rooms_missing_notes += 1

    if rooms == 0:
        errors.append("No rooms found in room_program.json.")
    elif rooms_missing_notes > 0:
        warnings.append(f"rooms missing notes_rendered: {rooms_missing_notes}/{rooms}")


def expected_floor_keys(program: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (str(building.get("id", "")), str(floor.get("id", "")))
        for building in program.get("buildings", [])
        for floor in building.get("floors", [])
        if floor.get("record_type") == "floor" and floor.get("rooms") and floor.get("plan_cells")
    }


def validate_source_integrity(
    program_path: Path,
    program: dict[str, Any],
    manifest_path: Path,
    manifest: dict[str, Any],
    warnings: list[str],
) -> None:
    integrity = manifest.get("source_integrity")
    if not isinstance(integrity, dict):
        warnings.append("manifest missing source_integrity metadata")
        return

    expected_hash = str(integrity.get("program_sha256", ""))
    if not expected_hash:
        warnings.append("manifest missing source program hash")
    elif expected_hash != sha256_file(program_path):
        warnings.append("manifest is stale: room_program.json hash does not match")

    expected_generated_at = str(integrity.get("program_generated_at", ""))
    actual_generated_at = str(program.get("generated_at", ""))
    if expected_generated_at != actual_generated_at:
        warnings.append("manifest is stale: room_program generated_at does not match")

    source_files = manifest.get("source_files") if isinstance(manifest.get("source_files"), dict) else {}
    candidates_name = str(source_files.get("candidates", ""))
    candidates_path = manifest_path.parent.parent / candidates_name if candidates_name else None
    expected_candidates_hash = str(integrity.get("candidates_sha256", ""))
    if not expected_candidates_hash:
        warnings.append("manifest missing layout candidates hash")
    elif candidates_path is None or not candidates_path.exists():
        warnings.append("manifest source layout candidates file is missing")
    elif expected_candidates_hash != sha256_file(candidates_path):
        warnings.append("manifest is stale: layout_candidates.json hash does not match")


def validate_manifest(
    manifest_path: Path,
    manifest: dict[str, Any],
    program: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    defaults = load_residential_defaults()
    validation = defaults.get("validation", {})
    min_count = int(validation.get("min_exported_floor_count", 1) or 1)

    exports = manifest.get("exports", [])
    exported_count = int(manifest.get("exported_count", 0) or 0)
    if exported_count < min_count:
        errors.append(f"exported_count too low: {exported_count} < {min_count}")

    if len(exports) != exported_count:
        warnings.append(f"exported_count mismatch: header={exported_count}, exports={len(exports)}")

    expected_keys = expected_floor_keys(program)
    exported_keys = {
        (str(record.get("building_id", "")), str(record.get("floor_id", "")))
        for record in exports
    }
    missing_exports = sorted(expected_keys - exported_keys)
    unexpected_exports = sorted(exported_keys - expected_keys)
    if missing_exports:
        warnings.append(f"missing expected floor exports: {missing_exports}")
    if unexpected_exports:
        warnings.append(f"unexpected floor exports: {unexpected_exports}")
    if exported_count != len(expected_keys):
        warnings.append(f"exported floor count mismatch: expected={len(expected_keys)}, actual={exported_count}")

    manifest_dir = manifest_path.parent
    missing_files = 0
    missing_markers = 0

    for rec in exports:
        file_name = rec.get("file", "")
        svg_path = manifest_dir / str(file_name)
        if not svg_path.exists():
            missing_files += 1
            continue

        try:
            markers, visible_text = inspect_svg(svg_path)
        except ET.ParseError as exc:
            errors.append(f"{file_name}: invalid SVG XML: {exc}")
            continue

        expected_markers = {"entrance", "door", "window"}
        svg_info = rec.get("svg", {}) if isinstance(rec.get("svg"), dict) else {}
        if bool(svg_info.get("has_elevation_index")):
            expected_markers.add("elevation")
        missing = sorted(expected_markers - markers)
        if bool(svg_info.get("has_dimensions")) and "DIM:" not in visible_text:
            missing.append("dimensions")
        if bool(svg_info.get("has_legend")) and "LEGEND:" not in visible_text:
            missing.append("legend")
        if missing:
            missing_markers += 1
            warnings.append(f"{file_name}: missing rendered markers: {', '.join(missing)}")

    if missing_files > 0:
        errors.append(f"missing SVG files: {missing_files}")
    if missing_markers > 0:
        warnings.append(f"SVG files missing required markers: {missing_markers}")


def main() -> None:
    args = parse_args()
    program_path = args.program.resolve()
    manifest_path = args.manifest.resolve()

    errors: list[str] = []
    warnings: list[str] = []

    if not program_path.exists():
        errors.append(f"program not found: {program_path}")
    if not manifest_path.exists():
        errors.append(f"manifest not found: {manifest_path}")

    if not errors:
        program = load_json(program_path)
        manifest = load_json(manifest_path)
        validate_program(program, errors, warnings)
        validate_source_integrity(program_path, program, manifest_path, manifest, warnings)
        validate_manifest(manifest_path, manifest, program, errors, warnings)

    print(f"Program:  {program_path}")
    print(f"Manifest: {manifest_path}")
    print(f"Errors:   {len(errors)}")
    print(f"Warnings: {len(warnings)}")

    for item in warnings:
        print(f"[WARN] {item}")
    for item in errors:
        print(f"[ERROR] {item}")

    if errors or (args.strict and warnings):
        raise SystemExit(2)


if __name__ == "__main__":
    main()

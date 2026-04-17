#!/usr/bin/env python3
"""Validate generated room program and SVG bundle for print-quality gates."""

from __future__ import annotations

import argparse
import json
import sys
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
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def validate_manifest(manifest_path: Path, manifest: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    defaults = load_residential_defaults()
    validation = defaults.get("validation", {})
    required_markers = [str(v) for v in validation.get("required_markers", ["ENT", "DW:"])]
    min_count = int(validation.get("min_exported_floor_count", 1) or 1)

    exports = manifest.get("exports", [])
    exported_count = int(manifest.get("exported_count", 0) or 0)
    if exported_count < min_count:
        errors.append(f"exported_count too low: {exported_count} < {min_count}")

    if len(exports) != exported_count:
        warnings.append(f"exported_count mismatch: header={exported_count}, exports={len(exports)}")

    manifest_dir = manifest_path.parent
    missing_files = 0
    missing_markers = 0

    for rec in exports:
        file_name = rec.get("file", "")
        svg_path = manifest_dir / str(file_name)
        if not svg_path.exists():
            missing_files += 1
            continue

        content = svg_path.read_text(encoding="utf-8")
        for marker in required_markers:
            if marker not in content:
                missing_markers += 1
                warnings.append(f"{file_name}: missing marker '{marker}'")
                break

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
        validate_manifest(manifest_path, manifest, errors, warnings)

    print(f"Program:  {program_path}")
    print(f"Manifest: {manifest_path}")
    print(f"Errors:   {len(errors)}")
    print(f"Warnings: {len(warnings)}")

    for item in warnings:
        print(f"[WARN] {item}")
    for item in errors:
        print(f"[ERROR] {item}")

    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

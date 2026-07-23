from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib.standards import load_residential_defaults
from scripts.validate_layout_bundle import expected_floor_keys


ROOT = Path(__file__).resolve().parents[1]


def test_existing_invalid_config_fails_fast(tmp_path: Path) -> None:
    config = tmp_path / "defaults.json"
    config.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid residential defaults JSON"):
        load_residential_defaults(config)


def test_missing_config_uses_fallback(tmp_path: Path) -> None:
    defaults = load_residential_defaults(tmp_path / "missing.json")

    assert defaults["_meta"]["config_exists"] is False
    assert defaults["_meta"]["config_loaded"] is False
    assert defaults["geometry"]["door_width_mm"]["entry"] > 0


def test_strict_validation_fails_on_warning(tmp_path: Path) -> None:
    program = tmp_path / "room_program.json"
    manifest = tmp_path / "manifest.json"
    program.write_text(
        json.dumps({"default_standards": {}, "buildings": [{"floors": [{"rooms": [{"id": "r1"}]}]}]}),
        encoding="utf-8",
    )
    manifest.write_text(json.dumps({"exported_count": 1, "exports": []}), encoding="utf-8")

    command = [
        sys.executable,
        str(ROOT / "scripts" / "validate_layout_bundle.py"),
        "--program",
        str(program),
        "--manifest",
        str(manifest),
    ]
    relaxed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    strict = subprocess.run([*command, "--strict"], cwd=ROOT, capture_output=True, text=True, check=False)

    assert relaxed.returncode == 0
    assert strict.returncode == 2
    assert "Warnings:" in strict.stdout


def test_expected_floor_keys_excludes_sections_and_storage_without_plan_cells() -> None:
    program = {
        "buildings": [
            {
                "id": "A",
                "floors": [
                    {"id": "floor-1", "record_type": "floor", "rooms": [{}], "plan_cells": [{}]},
                    {"id": "notes", "record_type": "section", "rooms": [], "plan_cells": []},
                ],
            },
            {
                "id": "STORAGE",
                "floors": [{"id": "floor-0", "record_type": "section", "rooms": [{}], "plan_cells": []}],
            },
        ]
    }

    assert expected_floor_keys(program) == {("A", "floor-1")}

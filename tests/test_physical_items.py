from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from house_design.contracts import ContractError, write_json
from house_design.intake import validate_intake
from house_design.physical_items import (
    active_dimensions,
    load_physical_items,
    record_physical_item_measurement,
    validate_physical_items,
)

ROOT = Path(__file__).resolve().parents[1]


def _repository_inventory() -> dict:
    return json.loads((ROOT / "inputs/physical-items.json").read_text(encoding="utf-8"))


def test_repository_inventory_keeps_typical_palanquin_dimensions_pending_measurement() -> None:
    payload = _repository_inventory()
    register = load_physical_items(ROOT / "inputs/physical-items.json")
    palanquin = register["by_id"]["B.palanquin.primary"]

    assert validate_physical_items(payload) == []
    assert palanquin["active_dimensions"] == {
        "width_mm": 1200.0,
        "depth_mm": 1700.0,
        "height_mm": 1800.0,
    }
    assert palanquin["active_dimension_source"] == "planning"
    assert palanquin["transport"]["door_clear_target_mm"] == 1500
    assert register["summary"] == {"total": 1, "measured": 0, "pending_measurement": 1}


def test_measurement_command_appends_complete_envelopes_and_latest_one_wins(tmp_path: Path) -> None:
    path = tmp_path / "physical-items.json"
    write_json(path, _repository_inventory())

    first = record_physical_item_measurement(
        item_id="B.palanquin.primary",
        width_mm=1260,
        depth_mm=1740,
        height_mm=1830,
        measured_by="屋主",
        measured_at="2026-10-01",
        method="捲尺量最大外廓",
        path=path,
    )
    second = record_physical_item_measurement(
        item_id="B.palanquin.primary",
        width_mm=1270,
        depth_mm=1750,
        height_mm=1840,
        measured_by="屋主與設計師",
        measured_at="2026-10-02",
        method="複測最大外廓",
        note="含固定裝飾",
        path=path,
    )
    stored = json.loads(path.read_text(encoding="utf-8"))
    item = stored["items"][0]

    assert first["measurement_sequence"] == 1
    assert second["measurement_sequence"] == 2
    assert item["planning_dimensions"] == {"width_mm": 1200, "depth_mm": 1700, "height_mm": 1800}
    assert len(item["measurements"]) == 2
    assert active_dimensions(item) == (
        {"width_mm": 1270.0, "depth_mm": 1750.0, "height_mm": 1840.0},
        "measured",
    )


def test_inventory_rejects_partial_measurement_instead_of_mixing_axes() -> None:
    payload = deepcopy(_repository_inventory())
    payload["items"][0]["measurements"] = [
        {
            "sequence": 1,
            "dimensions": {"width_mm": 1250, "depth_mm": 1720},
            "measured_by": "owner",
            "measured_at": "2026-10-01",
            "method": "tape",
        }
    ]

    issues = validate_physical_items(payload)

    assert any(item["field"].endswith("dimensions.height_mm") for item in issues)


def test_measurement_rejects_unknown_item_without_rewriting_register(tmp_path: Path) -> None:
    path = tmp_path / "physical-items.json"
    write_json(path, _repository_inventory())
    before = path.read_bytes()

    with pytest.raises(ContractError, match="Unknown physical item id"):
        record_physical_item_measurement(
            item_id="missing",
            width_mm=100,
            depth_mm=100,
            height_mm=100,
            measured_by="owner",
            measured_at="2026-10-01",
            method="tape",
            path=path,
        )

    assert path.read_bytes() == before


def test_intake_validation_reports_physical_item_measurement_status() -> None:
    result = validate_intake(
        project_path=ROOT / "inputs/project.json",
        requirements_path=ROOT / "inputs/requirements.json",
        physical_items_path=ROOT / "inputs/physical-items.json",
    )

    assert result["valid"] is True
    assert result["physical_item_issues"] == []
    assert result["physical_items"] == {"total": 1, "measured": 0, "pending_measurement": 1}


def test_physical_item_measurement_cli_updates_the_selected_register(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from house_design.cli import main

    path = tmp_path / "physical-items.json"
    write_json(path, _repository_inventory())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "house-design",
            "intake",
            "physical-item-measure",
            "--id",
            "B.palanquin.primary",
            "--width-mm",
            "1260",
            "--depth-mm",
            "1740",
            "--height-mm",
            "1830",
            "--measured-by",
            "屋主",
            "--measured-at",
            "2026-10-01",
            "--method",
            "捲尺量最大外廓",
            "--physical-items",
            str(path),
        ],
    )

    main()

    result = json.loads(capsys.readouterr().out)
    assert result["measurement_sequence"] == 1
    assert load_physical_items(path)["summary"] == {
        "total": 1,
        "measured": 1,
        "pending_measurement": 0,
    }

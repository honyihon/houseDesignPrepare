from __future__ import annotations

import json
from pathlib import Path

import pytest

import export_walkthrough_3d as walkthrough


def _plan() -> dict:
    return {
        "schema": "house-parametric-plan-v1",
        "site": {
            "storey_height_mm": 3000,
            "parapet_height_mm": 1100,
            "storeys": 3,
        },
        "row": {"gap_mm": 6000},
        "variants": [
            {
                "id": "f6000-g1",
                "frontage_mm": 6000,
                "depth_mm": 17630,
                "footprint_ping": 32.0,
                "garage": {"bays": 1, "label": "1 車位"},
                "buildings": {
                    "A": {
                        "frontage_mm": 6000,
                        "depth_mm": 17630,
                        "floors": [
                            {
                                "floor_id": "floor-1",
                                "label": "1F",
                                "cells": [
                                    {
                                        "id": "corridor",
                                        "name": "走道",
                                        "role": "corridor",
                                    }
                                ],
                                "walls": [],
                            }
                        ],
                    }
                },
            }
        ],
        "findings": [],
    }


def _program() -> dict:
    return {
        "buildings": [
            {
                "id": "A",
                "source_file": "AbuildingView.html",
                "floors": [
                    {
                        "id": "floor-1",
                        "record_type": "floor",
                        "tab_label": "1F",
                        "geometry_auto_mm": {"width_mm": 11000, "depth_mm": 7700},
                        "plan_cells": [],
                    }
                ],
            }
        ]
    }


def _defaults() -> dict:
    return {"geometry": {"door_height_mm": 2100}}


def test_payload_v2_contains_variant_synchronised_comparisons() -> None:
    payload = walkthrough.build_payload(_plan(), _defaults(), _program())

    assert payload["schema"] == "house-walkthrough-v2"
    assert payload["compare"]["schema"] == "house-html-parametric-compare-v2"
    assert list(payload["compare_variants"]) == ["f6000-g1"]
    relation = payload["compare_variants"]["f6000-g1"]["buildings"][0]["floors"][0][
        "relationships"
    ][0]
    assert (relation["para_id"], relation["relation"]) == (
        "corridor",
        "parametric_only",
    )


def test_payload_without_room_program_keeps_3d_and_marks_compare_unavailable() -> None:
    payload = walkthrough.build_payload(_plan(), _defaults(), None)

    assert payload["variants"]
    assert payload["compare"]["available"] is False
    assert payload["compare_variants"] == {}
    assert "room_program.json" in payload["compare"]["note"]


def test_rendered_viewer_exposes_scope_inspector_minimap_and_debug_seam() -> None:
    html = walkthrough.render_html(
        walkthrough.build_payload(_plan(), _defaults(), _program()),
        "window.THREE = {};",
    )

    for control_id in (
        "buildings",
        "floors",
        "room-list",
        "compare",
        "rule-filters",
        "inspector",
    ):
        assert f'id="{control_id}"' in html
    assert 'class="mini-map"' in html
    assert "function floorLabel(floorId)" in html
    assert "function showSourceOnlyRelation(relation)" in html
    assert "window.__walkDebug" in html
    assert "#stage.walking.wheels #turnbadge" in html
    assert "house-walkthrough-v2" in html
    assert "compare_variants" in html


@pytest.mark.parametrize(
    ("plan", "message"),
    [
        ({"schema": "unknown", "variants": [{}]}, "Unsupported parametric plan schema"),
        (
            {"schema": "house-parametric-plan-v1", "variants": []},
            "Parametric plan has no variants",
        ),
    ],
)
def test_main_rejects_invalid_or_empty_plan(
    tmp_path: Path,
    plan: dict,
    message: str,
) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(SystemExit, match=message):
        walkthrough.main(
            [
                "--plan",
                str(plan_path),
                "--program",
                str(tmp_path / "missing-program.json"),
                "--output",
                str(tmp_path / "walkthrough.html"),
            ]
        )


def test_main_generates_when_room_program_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_path = tmp_path / "plan.json"
    output_path = tmp_path / "walkthrough.html"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    monkeypatch.setattr(walkthrough, "load_residential_defaults", _defaults)
    monkeypatch.setattr(
        walkthrough,
        "three_source_checked",
        lambda: ("window.THREE = {};", {"bytes": 18, "version": "test-three"}),
    )

    result = walkthrough.main(
        [
            "--plan",
            str(plan_path),
            "--program",
            str(tmp_path / "missing-program.json"),
            "--output",
            str(output_path),
        ]
    )

    assert result == 0
    html = output_path.read_text(encoding="utf-8")
    assert "缺少 room_program.json" in html
    assert "house-walkthrough-v2" in html

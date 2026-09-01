from __future__ import annotations

import json
from pathlib import Path

import export_model_3d as model3d
from lib.dimension_overrides import load_overrides


ROOT = Path(__file__).resolve().parents[1]


def test_view_presets_keep_orientation_badge_in_sync() -> None:
    html = model3d.render_html({"compare": {}}, "window.THREE = {};")

    assert 'document.getElementById("compass").innerHTML = kind === "plan"' in html
    assert "<span><b>俯視</b><br />上方是道路</span>" in html
    assert "<span><b>正面</b><br />道路側 y=0</span>" in html


def test_repository_payload_preserves_all_html_cells_and_a_living_front_position() -> None:
    program = json.loads((ROOT / "structured" / "room_program.json").read_text(encoding="utf-8"))
    plan = json.loads((ROOT / "structured" / "parametric" / "plan.json").read_text(encoding="utf-8"))
    payload = model3d.build_payload(program, load_overrides(), "presentation", plan)

    cells = {
        cell["id"]: cell
        for building in payload["buildings"]
        for floor in building["floors"]
        for cell in floor["cells"]
    }

    assert len(cells) == 84
    assert cells["A:floor-1:living"]["auto_mm"]["y_mm"] == 1200
    assert cells["A:floor-1:living"]["name"] == "客廳"
    assert payload["buildings"][0]["floors"][0]["front_side"] == "top"


def test_rendered_viewer_exposes_shareable_scope_contract_and_html_backlink() -> None:
    html = model3d.render_html({"compare": {}}, "window.THREE = {};")

    assert 'values.set("building", viewState.building)' in html
    assert 'values.set("floor", viewState.floor)' in html
    assert 'values.set("room", viewState.room)' in html
    assert 'values.set("view", viewState.view === "plan" ? "plan" : "front")' in html
    assert "回到原 HTML 房間說明" in html
    assert "window.__htmlModel3dDebug" in html

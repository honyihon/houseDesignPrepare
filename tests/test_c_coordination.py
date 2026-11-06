"""Bounded coordination geometry/contracts only; no scene, browser or full suite."""
from __future__ import annotations

import copy
import csv
import io
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import export_c_coordination as export
import pytest

from house_design.c_coordination import CONFIG, OUT, analyze, build, cross_plane, public_path
from house_design.contracts import ContractError, stable_hash

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def item(report, oid):
    return next(i for i in report["findings"] if i["id"] == oid)


def test_scope_and_missing_authority_cannot_be_reported_as_professional_clearance(report):
    assert report["construction_ready"] is False and report["layout_changed"] is False
    assert report["coordinate_registration"] == "unverified-local-concept"
    assert report["structural_entities"] is None and report["formal_coordination_engine_used"] is False
    assert report["counts"] == {"nominal-no-conflict": 2, "interface-pending": 3, "unknown": 6, "sensitivity-conflict": 1}
    assert len(report["findings"]) == 12
    assert all(i["professional_status"] == "unknown" and i["actual_reply"] is None and i["reply_reference"] is None for i in report["findings"])
    assert all(i["compliance"] == "unknown" and i["product_model"] is None for i in report["systems"])


def test_penetrations_are_actual_crossings_with_unknown_hole_sizes(report):
    assert {p["id"]: p["center_mm"] for p in report["penetrations"]} == {
        "P01": [4450, 5700, 3500], "P02": [4450, 5000, 4000], "P03": [4450, 3900, 6350]}
    assert all(p["pipe_bundle_budget_mm"] == 150 and p["actual_hole_size_mm"] is None for p in report["penetrations"])
    assert all(p["structural_clearance"] == "unknown" for p in report["penetrations"])
    assert len(cross_plane([[0, 0, 1], [0, 0, 2], [0, 0, 3]], 2, 2)) == 1


def test_diagrams_leave_the_nominal_front_door_aperture_open(report):
    for f in report["plans"]["floors"][:2]:
        gate = next(r["features"]["c_front_gate"] for r in f["rooms"] if "c_front_gate" in r["features"])
        lo, hi = gate["opening_x_mm"]
        for x, y, w, d in export.gate_walls(gate):
            assert min(x+w, hi) <= max(x, lo) or min(y+d, 8600) <= max(y, 8500)


def test_dimensions_include_opening_and_upper_datum_budget_not_fake_beam_bottom(report):
    m = item(report, "C-CO-04")["measurements"]
    assert m["front_opening_x_margins_mm"] == {"window": 175, "door": 225}
    assert m["pipe_top_z_mm"] == 6425 and m["upper_floor_datum_to_pipe_top_mm"] == 575
    assert m["pipe_bottom_to_nominal_window_head_mm"] == 175
    assert m["actual_beam_bottom_z_mm"] is None and m["actual_ceiling_bottom_z_mm"] is None


def test_ground_soil_and_canopy_missing_values_cannot_disappear(report):
    assert [c["margin_to_target_mm"] for c in report["soil_cases"]] == [0, -150, -300]
    assert item(report, "C-CO-08")["status"] == "sensitivity-conflict"
    tree = item(report, "C-CO-07")["measurements"]
    assert min(tree["tree_projection_distances"], key=lambda p: p["horizontal_centerline_distance_mm"])["tree"] == 3
    assert tree["tree_projection_distances"][2]["horizontal_centerline_distance_mm"] == 20
    assert tree["mature_canopy_height_mm"] is None
    drain = report["drainage"]
    assert drain["stub_plan_mm"] == [[5850, 6500], [5850, 5700]]
    assert drain["terminal_point_mm"] is None and drain["port_z_mm"] is None
    assert drain["fall_sensitivity_mm"] == {"1": 8, "1.5": 12, "2": 16}


def test_same_room_duplicate_aircon_remains_an_open_coordination_item(report):
    m = item(report, "C-CO-09")["measurements"]
    assert m["multiple_indoor_units"] == {"C:floor-2:guestroom2f": ["C-AC04", "C-AC07"]}
    assert m["systems"] == 7 and m["selected_products"] == 0


def test_injected_pipe_furniture_conflict_is_not_silently_marked_clear():
    cfg = json.loads((ROOT/CONFIG).read_text())
    source = json.loads((ROOT/cfg["source_report"]).read_text())
    baseline = copy.deepcopy(source)
    current = next(o for o in source["options"] if o["id"] == "c-split")["states"][0]
    entrance = next(r for r in current["plans"]["floors"][0]["rooms"] if r["key"] == "entrance")
    entrance["furniture"][0]["height_mm"] = 4000
    report = analyze(source, cfg, json.loads((ROOT/"inputs/c-balcony-coordination.json").read_text()))
    issue = item(report, "C-CO-01")
    assert issue["status"] == "interface-pending" and issue["measurements"]["unit_hits"]
    assert baseline != source and report["construction_ready"] is False


@pytest.mark.parametrize("path", ["../private.json", "/tmp/file.json", "inputs/.hidden"])
def test_coordination_cannot_read_outside_public_basis(path):
    with pytest.raises(ContractError):
        public_path(ROOT, path)


def test_selected_report_or_any_current_artifact_change_rejects_stale_overlay(monkeypatch):
    import house_design.c_coordination as module

    real = module.sha256_file
    monkeypatch.setattr(module, "sha256_file", lambda p: "0"*64 if p.name == "kaohsiung-house-options-3d.html" else real(p))
    with pytest.raises(ContractError, match="dependency changed"):
        build(ROOT)


def test_authority_cannot_be_promoted_by_filling_a_text_field(monkeypatch):
    import house_design.c_coordination as module

    real = module.read_json

    def fake(path):
        value = real(path)
        if path.name == Path(CONFIG).name:
            value["external_inputs"]["structure"]["drawing_reference"] = "unregistered approval text"
        return value

    monkeypatch.setattr(module, "read_json", fake)
    with pytest.raises(ContractError, match="verified registration"):
        build(ROOT)


def test_artifacts_have_bounded_canvases_blank_reply_cells_and_source_hashes(report):
    files = export.artifacts(ROOT)
    assert len(files) == 8
    for name, content in files.items():
        assert (ROOT/name).read_text(encoding="utf-8") == content
        if name.endswith(".svg"):
            svg = ET.fromstring(content)
            assert int(svg.get("width"))*int(svg.get("height")) <= 1_600_000
            metadata = next(e for e in svg if e.get("data-coordination-metadata") == "1")
            assert json.loads(metadata.text)["construction_ready"] is False
    csv_data = files[OUT+"/reply-checklist.csv"].lstrip("\ufeff")
    rows = list(csv.reader(io.StringIO(csv_data)))
    assert len(rows) == 13 and all(row[-2:] == ["", ""] for row in rows[1:])
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    assert "未提供" in files[OUT+"/index.html"] and "不改已驗3D" in files[OUT+"/index.html"]

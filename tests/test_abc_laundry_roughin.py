"""Small source/interface checks; no system sizing, construction or rendered claims."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from house_design.abc_laundry_roughin import BUILDER, CONFIG, OUT, PARENT, build, validate
from house_design.contracts import ContractError, stable_hash
from scripts.export_abc_laundry_roughin import render

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text())


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_three_location_modes_retain_original_geometry_without_more_active_machines(report):
    parent = read(PARENT)
    assert report["owner_direction"] == parent["owner_direction"]
    assert report["retained_space"] == parent["retained_space"]
    common, upper, dormant = report["locations"]
    assert [r["mode"] for r in report["locations"]] == ["host-not-adopted", "reserve-no-machine-decided", "temporarily-inactive-reserve-space"]
    assert common["rects_mm"] == [[3350, 15945, 850, 750], [3350, 16765, 850, 750]]
    assert upper["rects_mm"] == [[3450, 15945, 850, 750]]
    assert dormant["rects_mm"] == [[800, 115, 650, 650]]
    assert "通氣" in dormant["preserve"] and "不自動拆機" in dormant["preserve"]
    assert "未啟用" in upper["preserve"]


def test_interfaces_reuse_original_questions_with_proposed_not_agreed_windows(report):
    builder = read(BUILDER)
    questions, a_interfaces = ({r["id"] for r in builder[k]} for k in ["questions", "a_interfaces"])
    assert len(report["interfaces"]) == 8
    for row in report["interfaces"]:
        assert set(row["question_ids"]) <= questions and set(row["a_interface_ids"]) <= a_interfaces
        assert row["actual_reply"] is row["agreed_window"] is None
        assert row["professional_approval"] == "unknown" and row["construction_release"] is False
    items = {r["id"]: r for r in report["interfaces"]}
    assert "合法終端" in items["wastewater"]["required"]
    assert "水平穩定" in items["waterproof"]["prepare"]
    assert "不封死通氣或公共排水" in items["maintenance"]["required"]
    assert "不預填110／220V" in items["power"]["required"]
    assert "不接一般ERV" in items["air"]["prepare"]


def test_non_adoption_and_unknown_system_design_survive_the_handoff(report):
    for k in ["adopted", "construction_release", "point_coordinates_decided", "pipe_sizes_decided", "electrical_ratings_decided",
            "equipment_purchase_decided", "host_building_adopted", "exterior_openings_authorized", "original_ABC_or_3d_changed",
            "accepted_storage_viewers_changed"]:
        assert report[k] is False
    assert report["dryer_type_selected"] is None
    assert len(report["actual_conditions"]) == 20 and all(v is None for v in report["actual_conditions"].values())
    assert report["actual_conditions_received"] == 0
    assert report["protected_controls_unchanged"] == 149
    assert report["formal_requirement_statuses"] == {"candidate": 66}
    assert report["formal_register_statuses"] == {"unknown": 105}
    assert report["professional_approval"] == "unknown" and report["rendered_qa"] == "not-run"


@pytest.mark.parametrize("defect", ["adopt", "source-seal", "filled", "missing-actual", "missing-interface", "wrong-BC", "wrong-A", "wrong-LAU", "dryer-selected"])
def test_interface_plan_cannot_silently_drop_evidence_or_replace_original_refs(defect):
    cfg = read(CONFIG)
    if defect == "adopt":
        cfg["adopted"] = True
    elif defect == "source-seal":
        cfg["parent_sha256"] = "0"*64
    elif defect == "filled":
        cfg["actual_conditions"]["electrical_load_panel_and_protection"] = 0
    elif defect == "missing-actual":
        cfg["actual_conditions"].pop("professional_review_and_drawing_issue")
    elif defect == "missing-interface":
        cfg["interfaces"].pop()
    elif defect == "wrong-BC":
        cfg["interfaces"][0]["question_ids"] = ["BC-99"]
    elif defect == "wrong-A":
        cfg["interfaces"][0]["a_interface_ids"] = ["A-IF-99"]
    elif defect == "wrong-LAU":
        cfg["interfaces"][0]["laundry_ids"] = ["LAU-99"]
    else:
        cfg["dryer_alternatives"].pop()
    with pytest.raises(ContractError):
        validate(cfg, read(BUILDER))


@pytest.mark.parametrize("source", [PARENT, BUILDER, "inputs/abc-laundry-access.json", "inputs/requirements.json"])
def test_actual_source_drift_rejects_prior_seals(monkeypatch, source):
    from house_design import abc_laundry_roughin as module
    original = module.digest
    monkeypatch.setattr(module, "digest", lambda root, name, cache: "0"*64 if name == source else original(root, name, cache))
    with pytest.raises(ContractError, match="Laundry rough-in"):
        build(ROOT)


def test_recomputed_report_cannot_hide_changed_parent_contents(monkeypatch):
    from house_design import abc_laundry_roughin as module
    original = module.read_public_json
    parent = copy.deepcopy(read(PARENT))
    parent["equipment_purchase_decided"] = True
    parent["report_hash"] = stable_hash({k: v for k, v in parent.items() if k != "report_hash"})
    monkeypatch.setattr(module, "read_public_json", lambda root, name: parent if name == PARENT else original(root, name))
    with pytest.raises(ContractError, match="parent seal"):
        build(ROOT)


def test_bounded_named_sheet_blank_conditions_and_source_matching_artifacts(report):
    files = render(report)
    assert len(files) == 6 and all((ROOT/OUT/n).read_bytes() == text.encode() for n, text in files.items())
    svg = ET.fromstring(files["roughin-interfaces.svg"])
    assert svg.attrib["viewBox"] == "0 0 1400 1200" and svg.attrib["width"] == "1400"
    assert all(0 <= float(e.attrib["y"]) <= 1183 for e in svg.iter() if e.tag.rsplit("}", 1)[-1] == "text")
    assert not any(e.tag.rsplit("}", 1)[-1] in {"image", "script", "foreignObject"} for e in svg.iter())
    assert "沒有施工點位" in files["roughin-interfaces.svg"] and "未採用" in files["roughin-interfaces.svg"]
    assert all(r["label"] in files["roughin-interfaces.svg"] for r in report["interfaces"])
    assert "inspection-log.csv" in files["index.html"] and "熱泵／冷凝式" in files["index.html"]
    rows = list(csv.DictReader(io.StringIO(files["actual-conditions.csv"])))
    assert len(rows) == 20 and all(r["實際值"] == r["依據圖號版次"] == "" for r in rows)
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n, h in manifest["artifacts"].items())
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in report["source_hashes"].items())
    assert report["parent_sources_verified"] == 30
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})

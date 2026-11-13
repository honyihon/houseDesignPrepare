"""Small geometry/source checks for laundry access; no browsers or full scenes."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from historical_support import native_geometry_reference
from shapely.geometry import shape

from house_design.abc_laundry_access import CONFIG, OUT, PARENT, build, rear_screen, sealed_parent, validate_config
from house_design.contracts import ContractError, stable_hash
from scripts.export_abc_laundry_access import render

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text())


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_angled_relabeling_does_not_connect_the_fixed_free_floor(report):
    front = report["front_entry_screen"]
    assert front["nominal_shared_edge_mm"] == 1040
    assert front["optimistic_finished_shared_edge_mm"] == 810
    assert front["diagonal_length_mm"] == pytest.approx(1253.6347)
    assert front["reclassified_triangle_sqm"] == .364
    assert front["free_floor_symmetric_difference_sqm"] == 0
    assert front["appliances_and_door_leaves_ignored"]
    assert front["center_domain_components"] == 2
    assert all(len(ids) == 1 for ids in front["probe_components"].values())
    assert set(front["probe_components"]["hall"]).isdisjoint(front["probe_components"]["kitchen"])
    assert not front["probes_connected"] and not front["global_front_replanning_impossible"]
    assert front["existing_door_budget_clear_mm"] == 670 and not front["front_care_route_approved"]


def test_rear_gate_scopes_inside_only_and_retains_all_original_bodies(report):
    rear = report["rear_entry_screen"]
    assert rear["opening_nominal_mm"] == 1200 and rear["budget_clear_mm"] == 970
    assert rear["actual_clear_mm"] is None
    assert rear["wall_bridge_rect_mm"] == [2315, 17510, 970, 120]
    assert rear["travel_envelope_rect_mm"] == [910, 17535, 2520, 95]
    assert rear["scoped_route_sqm"] == 1.512 and rear["outside_unchecked_route_sqm"] == .63
    assert shape(rear["scoped_route"]).bounds == (2350, 15950, 3250, 17630)
    assert shape(rear["outside_route"]).bounds == (2350, 17630, 3250, 18330)
    assert rear["scoped_route_inside_finished_assumption"]
    assert rear["scoped_route_body_hits"] == rear["travel_body_hits"] == []
    compact = read(PARENT)["A1_options"][0]
    assert all(rear[k] == compact[k] for k in ["bodies", "fixed", "operations"])
    assert not rear["parent_laundry_geometry_changed"]


def test_independent_door_states_disclose_real_obstructions_and_model_gaps(report):
    rear = report["rear_entry_screen"]
    assert [s["scoped_route_blocked"] for s in rear["states"]] == [False, True, True]
    assert [s["leaf_rect_mm"][0] for s in rear["states"]] == [910, 1540, 2170]
    assert [s["scoped_route_leaf_overlap_sqm"] for s in rear["states"]] == [0, .04275, .0855]
    assert rear["shared_operation_bands"] == ["washer-loading", "dryer-loading"]
    assert rear["leaf_travel_body_gaps_mm"] == {"optional-dryer-bay": 20, "lowered-drying-envelope": 70}
    assert not rear["gaps_are_product_tolerances"]
    assert all(not s["whole_route_approved"] for s in rear["states"])
    assert all(rear[k] is False for k in ["outside_access_rights_verified", "threshold_and_door_product_verified", "whole_route_or_care_approved"])


def test_original_owner_choices_controls_and_parent_risks_are_retained(report):
    parent = read(PARENT)
    assert report["parent_sources_verified"] == 15
    assert report["owner_direction"] == parent["owner_direction"]
    assert report["A2_reservation_retained"] == parent["A2_reservation"]
    assert report["C2_space_retained"] == parent["C2_space_retained"]
    assert report["B_source_states_retained"] == parent["B_source_states_retained"]
    assert report["parent_laundry_risks_retained"]["compact"] == parent["A1_options"][0]["screen"]
    assert report["parent_laundry_risks_retained"]["deeper_kitchen_area"]["loss_nominal_sqm"] == 2.232
    assert report["protected_controls_unchanged"] == 149
    assert report["formal_requirement_statuses"] == {"candidate": 66}
    assert report["formal_register_statuses"] == {"unknown": 105}
    assert report["actual_conditions_received"] == 0 and len(report["actual_conditions"]) == 19
    assert all(v is None for v in report["actual_conditions"].values())
    assert all(report[k] is False for k in ["adopted", "host_building_adopted", "original_ABC_or_3d_changed", "accepted_storage_viewers_changed"])
    assert report["professional_approval"] == "unknown" and report["rendered_qa"] == "not-run"


@pytest.mark.parametrize("defect", ["adopted", "parent", "finish", "states", "filled", "group", "C2", "A-upper"])
def test_owner_scope_and_blank_actual_conditions_cannot_be_relaxed(defect):
    cfg = read(CONFIG)
    owner = read(cfg["owner_reference"])
    if defect == "adopted":
        cfg["adopted"] = True
    elif defect == "parent":
        cfg["parent_sha256"] = "0"*64
    elif defect == "finish":
        cfg["finish_assumption_mm"] = 0
    elif defect == "states":
        cfg["rear_gate"]["states"].pop()
    elif defect == "filled":
        cfg["actual_conditions"]["A_rear_opening_permission"] = True
    elif defect == "group":
        owner["confirmed"]["shared_group_at_ground_floor"] = 3
    elif defect == "C2":
        owner["confirmed"]["C_floor2_initial_washer_use"] = "removed"
    else:
        owner["confirmed"]["A_upper_floor_washer_space_required"] = False
    with pytest.raises(ContractError):
        validate_config(cfg, owner)


@pytest.mark.parametrize("defect", ["narrow-opening", "door-body", "fixed-body", "leaf-resize", "bridge-overreach", "bad-route", "outside-opening"])
def test_gate_and_route_conflicts_are_rejected_instead_of_drawing_an_approved_path(defect):
    cfg, compact = read(CONFIG), read(PARENT)["A1_options"][0]
    if defect == "narrow-opening":
        cfg["rear_gate"]["opening_mm"] = [[2250, 17630], [3350, 17630]]
    elif defect == "door-body":
        cfg["rear_gate"]["open_leaf_mm"][1] -= 200
        cfg["rear_gate"]["closed_leaf_mm"][1] -= 200
    elif defect == "fixed-body":
        compact["bodies"][0]["rect_mm"][0] = 2600
    elif defect == "leaf-resize":
        cfg["rear_gate"]["open_leaf_mm"][2] += 100
    elif defect == "bridge-overreach":
        cfg["rear_gate"]["wall_bridge_depth_mm"] = 1800
    elif defect == "bad-route":
        cfg["rear_gate"]["route_points_mm"][0][0] = 5000
    else:
        cfg["rear_gate"]["opening_mm"][1][0] = 6500
    with pytest.raises(ContractError):
        rear_screen(cfg, compact)


@pytest.mark.parametrize("defect", ["parent-file", "parent-source", "parent-report"])
def test_parent_drift_cannot_inherit_a_previous_pass(monkeypatch, defect):
    from house_design import abc_laundry_access as module
    cfg, parent = read(CONFIG), read(PARENT)
    if defect == "parent-file":
        original = module.digest
        monkeypatch.setattr(module, "digest", lambda root, name, cache: "0"*64 if name == PARENT else original(root, name, cache))
    else:
        if defect == "parent-source":
            original = module.digest
            monkeypatch.setattr(module, "digest", lambda root, name, cache: "0"*64 if name == "inputs/abc-ground-laundry.json" else original(root, name, cache))
            # A live source drift is caught even while the sealed report remains intact.
        else:
            parent["adopted"] = True
        monkeypatch.setattr(module, "read_public_json", lambda *_: copy.deepcopy(parent))
    with pytest.raises(ContractError, match="Laundry access parent"):
        sealed_parent(ROOT, cfg, {})


def test_outputs_are_bounded_named_vectors_with_source_matching_artifacts(report):
    archived = native_geometry_reference(ROOT/OUT/"review.json", report)
    files = render(archived)
    assert len(files) == 8 and all((ROOT/OUT/n).read_bytes() == text.encode() for n, text in files.items())
    for name in ["front-entry-screen.svg", "rear-entry-conditional.svg", "rear-door-states.svg"]:
        svg = ET.fromstring(files[name])
        assert svg.attrib["viewBox"] == "0 0 1400 1200"
        assert svg.attrib["width"] == "1400" and svg.attrib["height"] == "1200"
        assert "未採用" in files[name]
        assert not any(e.tag.rsplit("}", 1)[-1] in {"image", "script", "foreignObject"} for e in svg.iter())
        assert all(0 <= float(e.attrib["y"]) <= 1183 for e in svg.iter() if e.tag.rsplit("}", 1)[-1] == "text")
    assert "MDF維修備援保留" in files["front-entry-screen.svg"]
    assert all(label in files["rear-entry-conditional.svg"] for label in ["共用洗衣備位", "乾衣備位", "晾衣外廓", "冷氣維修", "原淨軟水"])
    rows = list(csv.DictReader(io.StringIO(files["actual-conditions.csv"])))
    assert len(rows) == 19 and all(r["實際值"] == r["來源或產品文件"] == "" for r in rows)
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == sha for n, sha in manifest["artifacts"].items())
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == sha for n, sha in report["source_hashes"].items())
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})

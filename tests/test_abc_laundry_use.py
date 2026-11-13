"""Bounded example schedules and source checks, not real product or laundry capacity tests."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from house_design.abc_laundry_use import CONFIG, OUT, PARENT, build, handling_conflicts, paired_phases, schedule
from house_design.contracts import ContractError, stable_hash
from scripts.export_abc_laundry_use import render

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text())


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_illustrative_workloads_keep_wash_only_distinct_from_dry_completion(report):
    daily, bedding = report["scenarios"]
    assert (daily["batches"], bedding["batches"]) == (3, 6)
    assert [m["elapsed_min"] for m in daily["modes"]] == [360, 555, 720]
    assert [m["elapsed_min"] for m in bedding["modes"]] == [720, 1005, 1440]
    assert [m["example_batches_in_window"] for m in daily["modes"]] == [4, 2, 2]
    for s in report["scenarios"]:
        assert s["basis"] == "hypothetical-not-actual-demand"
        assert s["modes"][0]["completion_scope"] == "wash-only-not-air-dried"
        for mode in s["modes"]:
            assert mode["actual_demand_satisfied"] is None
            assert not mode["real_dry_completion_verified"] and not mode["global_optimum_claimed"]
    assert report["actual_laundry_capacity_sufficient"] is report["air_drying_duration_min"] is None


def test_shared_operation_area_requires_more_than_independent_machine_cycle_timing(report):
    values = report["config"]["illustrative_minutes"]
    assert handling_conflicts(paired_phases(3, values, 135))
    result = schedule(3, values, "separate-dryer")
    assert result["interval_min"] == 150 and not handling_conflicts(result["phases"])
    assert result["example_overrun_min"] == 75
    for batch in range(1, 4):
        phases = [p for p in result["phases"] if p["batch"] == batch]
        assert phases[2]["end_min"] == phases[3]["start_min"]  # No unassigned wet-clothes queue.
    # Programs really overlap, while all manual operations remain separate.
    programs = [p for p in result["phases"] if p["kind"] == "program"]
    assert any(a["resource"] != b["resource"] and max(a["start_min"], b["start_min"]) < min(a["end_min"], b["end_min"])
        for a in programs for b in programs)


@pytest.mark.parametrize("dryer_program", [1, 30, 90, 121, 240])
def test_different_program_lengths_cannot_double_book_the_user_or_machines(report, dryer_program):
    values = copy.deepcopy(report["config"]["illustrative_minutes"])
    values["dryer_program"] = dryer_program
    result = schedule(6, values, "separate-dryer")
    assert not handling_conflicts(result["phases"])
    for resource in ["washer", "dryer"]:
        phases = sorted((p for p in result["phases"] if p["resource"] == resource), key=lambda p: p["start_min"])
        assert all(a["end_min"] <= b["start_min"] for a, b in zip(phases, phases[1:], strict=False))


@pytest.mark.parametrize("value", [None, 0, -1, True, "90", 1.5, 1441])
def test_missing_or_invalid_example_times_are_not_converted_to_zero(report, value):
    values = copy.deepcopy(report["config"]["illustrative_minutes"])
    values["washer_program"] = value
    with pytest.raises(ContractError):
        schedule(3, values, "wash-and-air")


@pytest.mark.parametrize("value", [0, -1, True, None, 13])
def test_unbounded_or_invented_batch_counts_are_rejected(report, value):
    with pytest.raises(ContractError):
        schedule(value, report["config"]["illustrative_minutes"], "separate-dryer")


def test_space_owner_directions_and_unreceived_actual_data_remain_separate(report):
    parent = read(PARENT)
    retained = report["retained_space"]
    assert retained["rack_envelope_mm"][2:] == [1200, 500]
    assert all(r[2:] == [850, 750] for r in retained["machine_bays_mm"])
    assert not retained["rack_envelope_is_kg_capacity"] and not retained["cart_parking_adopted"]
    assert retained["C2_space_retained"] == parent["C2_space_retained"]
    assert retained["A2_reservation_retained"] == parent["A2_reservation_retained"]
    assert retained["B_source_states_retained"] == parent["B_source_states_retained"]
    assert retained["door_travel_gaps_mm"]["optional-dryer-bay"] == 20
    assert retained["shared_operation_bands"] == ["washer-loading", "dryer-loading"]
    assert report["parent_sources_verified"] == 25 and report["protected_controls_unchanged"] == 149
    assert report["formal_requirement_statuses"] == {"candidate": 66}
    assert report["formal_register_statuses"] == {"unknown": 105}
    assert len(report["actual_conditions"]) == 21 and all(v is None for v in report["actual_conditions"].values())
    assert all(report[k] is False for k in ["adopted", "equipment_purchase_decided", "host_building_adopted", "original_ABC_or_3d_changed"])


@pytest.mark.parametrize("defect", ["adopt", "filled", "actual-basis", "workload", "parent-file", "parent-source"])
def test_owner_choices_or_source_seals_cannot_be_overridden(monkeypatch, defect):
    from house_design import abc_laundry_use as module
    cfg = read(CONFIG)
    original_read, original_digest = module.read_public_json, module.digest
    if defect == "adopt":
        cfg["adopted"] = True
    elif defect == "filled":
        cfg["actual_conditions"]["daily_batches"] = 0
    elif defect == "actual-basis":
        cfg["illustrative_minutes"]["basis"] = "actual"
    elif defect == "workload":
        cfg["illustrative_scenarios"][0]["batches_per_household"] = True
    elif defect == "parent-file":
        monkeypatch.setattr(module, "digest", lambda root, name, cache: "0"*64 if name == PARENT else original_digest(root, name, cache))
    else:
        monkeypatch.setattr(module, "digest", lambda root, name, cache: "0"*64 if name == "inputs/abc-ground-laundry.json" else original_digest(root, name, cache))
    monkeypatch.setattr(module, "read_public_json", lambda root, name: copy.deepcopy(cfg) if name == CONFIG else original_read(root, name))
    with pytest.raises(ContractError):
        build(ROOT)


def test_bounded_named_vectors_and_current_source_artifacts(report):
    files = render(report)
    assert len(files) == 7 and all((ROOT/OUT/n).read_bytes() == text.encode() for n, text in files.items())
    for name in ["daily-flow.svg", "capacity-examples.svg"]:
        svg = ET.fromstring(files[name])
        assert svg.attrib["viewBox"] == "0 0 1400 1200"
        assert (svg.attrib["width"], svg.attrib["height"]) == ("1400", "1200")
        assert "示例" in files[name] and "未採用" in files[name]
        assert not any(e.tag.rsplit("}", 1)[-1] in {"image", "script", "foreignObject"} for e in svg.iter())
        assert all(0 <= float(e.attrib["y"]) <= 1183 for e in svg.iter() if e.tag.rsplit("}", 1)[-1] == "text")
    assert "9小時15分" in files["capacity-examples.svg"] and "16小時45分" in files["capacity-examples.svg"]
    assert "只洗完，晾乾未知" in files["index.html"] and "容量是否足夠：未知" in files["index.html"]
    rows = list(csv.DictReader(io.StringIO(files["actual-conditions.csv"])))
    assert len(rows) == 21 and all(r["實際值"] == r["來源與圖號版次"] == "" for r in rows)
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n, h in manifest["artifacts"].items())
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in report["source_hashes"].items())
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})

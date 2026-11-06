"""Small owner-evidence, airflow and network checks; no fan/scene/browser runtime."""
import copy
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

import house_design.abc_fresh_air as fresh
from house_design.abc_fresh_air import CONFIG, OUT, analyze_zones, build, flow_balance, validate_network
from house_design.contracts import ContractError, sha256_file
from scripts.export_abc_fresh_air import equipment_rows, render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_changed_parent_or_owner_bytes_stop_build(tmp_path):
    cfg = json.loads((ROOT/CONFIG).read_text())
    cfg["pinned_sources"] = {"owner.json": "0"*64}
    (tmp_path/"inputs").mkdir()
    (tmp_path/CONFIG).write_text(json.dumps(cfg))
    (tmp_path/"owner.json").write_text("{}")
    with pytest.raises(ContractError, match="fresh-air source changed"):
        build(tmp_path)


def test_owner_counts_are_not_double_counted_per_room(report):
    assert report["known_regular_people_total"] == 9
    counts = {b["id"]: b["known_regular_people"] for b in report["buildings"]}
    assert counts == {"A": 4, "B": 2, "C": 3}
    assert {b["id"]: [r["known_people_only"] for r in b["ordinary_supply_cases_m3_h"]]
        for b in report["buildings"]} == {"A": [100, 120, 140], "B": [50, 60, 70], "C": [75, 90, 105]}
    a2 = report["buildings"][0]["zones"][1]
    assert a2["people"] == 2 and len(a2["supplied_rooms"]) == 3
    assert [r["floor_total_m3_h"] for r in a2["night_supply_estimate_cases"]] == [50, 60, 70]


def test_unknown_third_floor_and_incense_loads_are_not_zero(report):
    for b in report["buildings"]:
        third = b["zones"][-1]
        assert third["people"] is None and third["people_basis"] == "unknown-not-zero"
        assert third["priority"] == "rough-in-before-finishes" and third["supplied_rooms"]
        assert all(r["floor_total_m3_h"] is None for r in third["night_supply_estimate_cases"])
    b1 = report["buildings"][1]["zones"][0]
    assert b1["people"] is None and b1["priority"] == "install-now-separate-incense"
    assert "不進一般ERV回收" in b1["return_strategy"]


def test_changing_occupancy_cannot_inherit_owner_confirmation(monkeypatch):
    original = fresh.read_json

    def changed(path):
        cfg = original(path)
        if Path(path) == ROOT/CONFIG:
            cfg["zones"][0]["people"] = 1
        return cfg

    monkeypatch.setattr(fresh, "read_json", changed)
    with pytest.raises(ContractError, match="occupancy differs"):
        build(ROOT)


@pytest.mark.parametrize("target", ["C:floor-3:terrace3f", "C:floor-1:public-bath"])
def test_outdoor_or_wet_room_cannot_silently_become_ordinary_sleep_supply(monkeypatch, target):
    original = fresh.read_json
    bid, fid, key = target.split(":")

    def changed(path):
        cfg = original(path)
        if Path(path) == ROOT/CONFIG:
            z = next(z for z in cfg["zones"] if z["building"] == bid and z["floor"] == fid)
            z["supply"].append(key)
        return cfg

    monkeypatch.setattr(fresh, "read_json", changed)
    with pytest.raises(ContractError, match="existing indoor room|wet or incense"):
        build(ROOT)


def test_missing_floor_does_not_drop_future_preparation():
    cfg = json.loads((ROOT/CONFIG).read_text())
    cfg["zones"] = []
    with pytest.raises(ContractError, match="all nine floor zones"):
        analyze_zones(cfg, {}, {})


def test_each_building_air_network_is_independent(report):
    for b in report["buildings"]:
        s = b["system"]
        assert validate_network(s["nodes"], s["links"])
        assert all(n["building"] == b["id"] for n in s["nodes"])
        assert s["ordinary_unit_count"] is None
        assert s["physical_routes_and_fire_compartments_approved"] is False
    a, c = report["buildings"][0]["system"], report["buildings"][2]["system"]
    with pytest.raises(ContractError, match="between buildings"):
        validate_network([*a["nodes"], *c["nodes"]], [{"from": "A:ERV", "to": "C:floor-1:dry", "type": "duct"}])


@pytest.mark.parametrize("source", ["B:shrine-source", "B:floor-2:bath"])
def test_dirty_source_cannot_duct_back_into_ordinary_erv(report, source):
    s = report["buildings"][1]["system"]
    with pytest.raises(ContractError, match="cannot share ducts"):
        validate_network(s["nodes"], [*s["links"], {"from": source, "to": "B:ERV", "type": "duct"}])
    nodes = copy.deepcopy(s["nodes"])
    next(n for n in nodes if n["id"] == source)["system"] = "ordinary-erv"
    with pytest.raises(ContractError, match="relabelled"):
        validate_network(nodes, s["links"])


def test_transfer_is_not_added_to_mechanical_outdoor_air(report):
    cases = report["flow_cases"]
    assert [r["mechanical_net_m3_h"] for r in cases] == [0, -120, -110, 0, 120, 0, -720, None]
    assert all(r["predicted_pressure_pa"] is None and not r["whole_building_balance_verified"] for r in cases)
    assert "房間內轉送不增加室外風量" in cases[0]["meaning"]
    assert flow_balance(150, 100, bath=120)["mechanical_net_m3_h"] == -70
    with pytest.raises(ContractError, match="cannot be negative"):
        flow_balance(100, 100, bath=-20)


def test_c_care_partition_and_b_shrine_are_explicit_zone_requirements(report):
    c = report["buildings"][2]
    c1, c2 = c["zones"][:2]
    assert any(r["id"] == "C:floor-1:elder" for r in c1["supplied_rooms"])
    assert "前置門關閉" in c1["return_strategy"]
    assert c2["people"] == 1 and any(r["id"] == "C:floor-2:guestroom2f" for r in c2["supplied_rooms"])
    assert "不開梯門補氣" in c2["return_strategy"]
    b = report["buildings"][1]
    s = b["system"]
    assert any(e["from"] == "B:shrine-OA" and e["to"] == "B:shrine-SA" for e in s["links"])
    assert any(e["from"] == "B:shrine-source" and e["to"] == "B:shrine-EA" for e in s["links"])
    assert any("500×300" in note for note in report["b_revision_notes"])


def test_sleep_room_flow_and_machine_counts_are_not_preapproved(report):
    assert report["new_ventilation_requirement_owner_confirmed"] is True
    assert report["layout_or_product_adopted"] is report["actual_airflow_approved"] is report["all_requirements_met"] is False
    for b in report["buildings"]:
        assert b["mechanical_outdoor_air_required"] is True
        assert b["selected_product"] is b["actual_unit_count"] is b["actual_unit_positions_mm"] is None
        for z in b["zones"]:
            for r in z["supplied_rooms"]:
                assert r["actual_supply_m3_h"] is r["closed_door_return_route"] is r["terminal_position_mm"] is None
    assert [r["initial_erv_count_illustrative"] for r in report["units_comparison"]] == [3, 5]
    assert not any(r["selected"] for r in report["units_comparison"])
    assert all(r["model"] is r["actual_airflow"] is r["quote_twd"] is None for r in equipment_rows(report))


def test_b_previous_rear_front_states_retained(report):
    parent = json.loads((ROOT/report["config"]["b_detail_report"]).read_text())
    assert report["retained_b_entries"] == parent["retained_entries"]
    assert len(report["retained_b_entries"]) == 2
    assert all(r["states"] == ["daily", "ritual", "carry"] for r in report["retained_b_entries"])


def test_sources_and_artifacts_bind_to_current_bytes(report):
    files = render(report)
    assert len(files) == 10
    manifest = json.loads(files["artifact-manifest.json"])
    for name, data in files.items():
        assert (ROOT/OUT/name).read_bytes() == data.encode(), name
        if name in manifest["artifacts"]:
            assert hashlib.sha256(data.encode()).hexdigest() == manifest["artifacts"][name]
        if name.endswith(".svg"):
            svg = ET.fromstring(data)
            assert float(svg.attrib["width"])*float(svg.attrib["height"]) <= 1_600_000
            assert "新風需求已確認" in data and report["report_hash"] in data
    for name, digest in report["source_hashes"].items():
        assert sha256_file(ROOT/name) == digest, name
    controls = json.loads((ROOT/report["config"]["protected_controls"]).read_text())
    assert report["protected_controls_unchanged"] == len(controls["hashes"]) == 149
    for name, digest in controls["hashes"].items():
        assert sha256_file(ROOT/name) == digest, name
    assert "屋主已確認通風需求" in files["index.html"]
    assert "不是法定風量或選機值" in files["index.html"]

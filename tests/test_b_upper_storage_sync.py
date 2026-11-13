"""Bounded B version/geometry/storage checks; no browser, 3D runtime or solver."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from house_design.b_upper_replan import rect
from house_design.b_upper_storage_sync import (
    ARCHIVE,
    CONFIG,
    OUT,
    build,
    check_source_floor,
    check_stair_surfaces,
    storage_objects,
)
from house_design.contracts import ContractError, stable_hash
from house_design.upper_floor_storage import check_storage
from scripts.export_b_upper_storage_sync import render

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text())


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


@pytest.fixture(scope="module")
def files(report):
    return render(report)


def test_four_floor_versions_do_not_adopt_or_change_original_controls(report):
    assert report["summary"] == {"floor_variants": 4, "upper_floor_states": 8, "entry_options": 2,
        "ground_states": 6, "assembly_references": 24, "storage_cases": 4, "storage_per_assembly": 3, "RF_tables_duplicated": 0}
    assert report["protected_controls_unchanged"] == 149
    assert not report["main_3d_changed"] and not report["existing_viewers_changed"]
    assert not report["adopted"] and not report["construction_release"] and not report["original_family_rules_changed"]
    assert report["professional_approval"] == "unknown"
    assert [f["base_mm"] for f in report["floors"]] == [4000, 7000, 10000, 10000]


def test_p4_q3_polygons_fixtures_windows_and_shafts_are_exact_source_copies(report):
    p4, q3 = [read(report["config"]["sources"][name]) for name in ["floor2", "floor3"]]
    assert report["floors"][0]["source_rooms"] == p4["floor"]["rooms"]
    assert report["floors"][1]["source_rooms"] == q3["primary"]["rooms"]
    assert len(next(r for r in report["floors"][1]["source_rooms"] if r["id"] == "front-entertainment")["polygon_mm"]) > 4
    assert report["floors"][0]["front_service"]["sliders"] == p4["local_reference"]["sliders"]


def test_all_four_storage_cases_keep_original_rooms_and_operations(report):
    for floor in report["floors"]:
        spec = floor["storage"]
        assert check_storage(floor["rooms"], floor["fixed"], floor["routes"], spec)["failures"] == []
        original, proposed = floor["states"]
        assert len([i for i in proposed["objects"] if i.get("storage_case")]) == 1
        assert not any(i.get("storage_case") for i in original["objects"])
        old = {i["key"]: i for i in original["objects"]}
        unchanged = [i for i in proposed["objects"] if not i.get("storage_case")]
        assert all(old[i["key"]] == i for i in unchanged)
        if floor["id"] != "floor-4":
            assert len(proposed["objects"]) == len(original["objects"])+1
            assert spec["room"] == "quiet-living"
        else:
            assert len(proposed["objects"]) == len(original["objects"]) == 2
            replacement = next(i for i in proposed["objects"] if i.get("storage_case"))
            prior = old["front-platform:folding-table"]
            assert replacement["rect_mm"] == prior["rect_mm"] and replacement["operation_mm"] == prior["operation_mm"]
            assert replacement["replaces_id"] == "folding-table"


def test_roof_d1_d2_equipment_and_fold_table_positions_are_not_mixed(report):
    source = read(report["config"]["sources"]["roof"])
    for floor, option in zip(report["floors"][2:], source["options"], strict=True):
        assert floor["source_roof_option"] == option
        assert floor["storage"]["rect_mm"] == next(i for i in option["furniture"] if i["id"] == "folding-table")["rect_mm"]
    assert report["floors"][2]["storage"]["rect_mm"] != report["floors"][3]["storage"]["rect_mm"]


def test_both_ground_options_and_three_states_remain_exact_frozen_references(report):
    snapshot = read(report["config"]["sources"]["ground_snapshot"])
    assert [o["id"] for o in report["entry_options"] if o["default"]] == ["b-rear-split"]
    for entry in report["entry_options"]:
        original = next(o for o in snapshot["options"] if o["id"] == entry["id"])
        for state in entry["states"]:
            floor = next(f for s in original["states"] if s["id"] == state["id"] for f in s["plans"]["floors"] if f["id"] == "floor-1")
            assert state["floor"] == floor and state["source_floor_hash"] == stable_hash(floor)
    assert len({a["id"] for a in report["assemblies"]}) == 24
    assert all(len(a["floors"]) == 3 and len([k for k in a["floors"] if k.startswith("B-RF")]) == 1 for a in report["assemblies"])


@pytest.mark.parametrize("defect", ["full-2F-pad", "broken-transfer", "cap-3F", "cap-RF", "mixed-stair"])
def test_wrong_full_width_landing_or_capped_stairwell_is_rejected(report, defect):
    floors = copy.deepcopy(report["floors"])
    if defect == "full-2F-pad":
        floors[0]["stair_interface"]["arrival_polygon_mm"] = list(rect([80, 4770, 2200, 1000]).exterior.coords)
    elif defect == "broken-transfer":
        floors[0]["stair_interface"]["arrival_polygon_mm"] = list(rect([80, 3970, 2200, 1000]).exterior.coords)
    elif defect == "cap-3F":
        floors[1]["stair_interface"]["arrival_polygon_mm"] = list(rect([0, 3900, 2400, 5200]).exterior.coords)
    elif defect == "mixed-stair":
        floors[1]["stair_interface"]["incoming_treads"][0]["top_z_mm"] += 1
    else:
        floors[2]["stair_interface"]["arrival_polygons_mm"] = [list(rect([0, 3900, 2400, 5200]).exterior.coords)]
    with pytest.raises(ContractError):
        check_stair_surfaces(floors)


def test_room_rectangularization_and_frame_expansion_are_rejected(report):
    floor = copy.deepcopy(report["floors"][1])
    room = next(r for r in floor["rooms"] if r["id"] == "front-entertainment")
    room["polygon_mm"] = list(rect([0, 0, 6000, 4700]).exterior.coords)
    with pytest.raises(ContractError, match="partition"):
        check_source_floor(floor, rect([0, 0, 6000, 17630]))
    floor = copy.deepcopy(report["floors"][0])
    floor["rooms"][0]["polygon_mm"][0][0] = 7000
    with pytest.raises(ContractError, match="frame"):
        check_source_floor(floor, rect([0, 0, 6000, 17630]))


def test_duplicate_roof_tables_are_not_silently_rendered(report):
    floor = copy.deepcopy(report["floors"][2])
    floor["rooms"][0]["items"].append(copy.deepcopy(floor["rooms"][0]["items"][0]))
    with pytest.raises(ContractError, match="Duplicate"):
        storage_objects(floor, floor["storage"], "storage")


def test_32ping_and_RF24_shortfall_do_not_turn_into_requirement_relaxation(report):
    limits = report["known_limits"]
    assert limits["frame_sqm"] == 105.78 and not limits["frame_is_legal_buildable_area"]
    assert limits["RF_target_sqm"] == 24 and limits["RF_optimistic_before_equipment_sqm"] == 21.83945
    assert limits["RF_known_shortfall_before_equipment_sqm"] == 2.16055
    assert limits["KTV_source_budget_sqm"] == 20.1889
    assert not limits["P4_drainage_or_arcade_clearance_resolved"]
    assert all(r["over_protected_sqm"] == 0 for r in report["wet_projection"])


def test_vector_plans_keep_all_objects_named_and_polygons_exact(report, files):
    for floor in report["floors"]:
        for state in floor["states"]:
            svg = ET.fromstring(files[state["plan_file"]])
            nodes = list(svg.iter())
            assert len([n for n in nodes if n.get("data-item-key")]) == len(state["objects"])
            assert len([n for n in nodes if n.get("data-storage-case")]) == (state["id"] == "storage")
            text = "".join(svg.itertext())
            assert all(i["label"] in text for i in state["objects"])
            for room in floor["rooms"]:
                polygon = next(n for n in nodes if n.get("data-room-id") == room["id"])
                expected = [(45+x*.052, 150+y*.052) for x, y in room["polygon_mm"]]
                actual = [tuple(map(float, p.split(","))) for p in polygon.get("points").split()]
                assert actual == expected
    assert len([n for n in files if n.endswith(".svg")]) == 9
    assert b"<script" not in files["index.html"]


def test_package_seals_and_determinism_match_current_source(report, files):
    assert len(files) == 17
    assert all((ROOT/OUT/n).read_bytes() == b for n, b in files.items())
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n]).hexdigest() == h for n, h in manifest["artifacts"].items())
    with zipfile.ZipFile(io.BytesIO(files[ARCHIVE])) as z:
        assert len(z.namelist()) == 15
        assert all(z.read(n) == files[n] for n in z.namelist())
    assert files == render(report)
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in report["source_hashes"].items())
    assert read(CONFIG)["retained_goals"]["RF_deck_sqm"] == 24

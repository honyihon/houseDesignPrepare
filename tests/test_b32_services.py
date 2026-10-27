from __future__ import annotations

import copy
import json
import sys
from xml.etree import ElementTree as ET

import pytest

from house_design.b32_services import SOURCE, _covered, _hits, build_service_study, study_svg, write_service_study
from house_design.cli import main
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, write_json
from house_design.requirement_reconciliation import _snapshot


@pytest.fixture
def case(tmp_path):
    for name in (SOURCE, "inputs/project.json", "inputs/requirements.json", "inputs/physical-items.json",
                 "inputs/furniture-layout.json", "inputs/b32-entry-options.json"):
        write_json(tmp_path / name, read_json(ROOT / name))
    path = "structured/candidates/b32-entry-options/layout.js"
    data = _snapshot(ROOT / path, "HOUSE_B32_ENTRY_OPTIONS", "house-b32-entry-options-v1")
    # Keep existing lightweight plan data; never build the complete 3D model.
    data["source_hashes"] = {"inputs/b32-entry-options.json": sha256_file(tmp_path / "inputs/b32-entry-options.json")}
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text("window.HOUSE_B32_ENTRY_OPTIONS = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    return tmp_path


def modify(root, transform):
    settings = read_json(root / SOURCE)
    transform(settings)
    write_json(root / SOURCE, settings)


def row(case, zone):
    return next(r for r in case["area_rows"] if r["zone"] == zone)


def test_real_snapshot_six_comparisons_stay_below_32_ping_and_never_adopt():
    result = build_service_study()
    assert result["land_ping"] <= 32 and result["frame_mm"] == [6000, 17630]
    assert result["embedded_source_mismatches"] == []
    assert len(result["cases"]) == len({c["id"] for c in result["cases"]}) == 6
    assert {c["base_option"] for c in result["cases"]} == {"b32-rear", "b32-front"}
    assert set(result["gates"].values()) == {"unknown"}
    assert result["professional_approval"] == "unknown" and result["rendered_qa"] == "not-run"
    for c in result["cases"]:
        assert not c["adopted"]
        assert not c["baseline_work_access_without_storage_or_bath"]
        assert c["new_room_graph_without_storage_or_bath"] == ["shrine", "public-housework-passage", "laundry"]
        assert "unknown" in c["continuous_front_door_to_laundry_clearance"]
        assert c["bathroom_fixtures_and_rescue"].startswith("requires")
        assert all(r["functional_acceptance"] == "unknown" for r in c["area_rows"])


def test_compact_is_a_tradeoff_not_a_claim_all_original_targets_are_met(case):
    report = build_service_study(case)
    compact = [c for c in report["cases"] if c["service_option"] == "compact-service"]
    for c in compact:
        assert row(c, "bathroom")["sensitivity"][0]["area_sqm"] == 7.356
        assert row(c, "storage")["sensitivity"][0]["area_sqm"] == 9.6404
        assert row(c, "laundry")["sensitivity"][0]["area_sqm"] == 5.148
        assert row(c, "storage")["original_target_sqm"] == 10.5
        assert row(c, "storage")["below_target_at_80mm"]
        assert row(c, "storage")["below_minimum_insets_mm"] == []
        assert row(c, "storage")["sensitivity"][-1]["area_sqm"] == 9.0965
        assert c["housework_clear_width_assumptions_mm"][-1]["width_mm"] == 910


def test_wider_passage_exposes_storage_minimum_failure_and_storage_first_exposes_bath_target(case):
    for c in build_service_study(case)["cases"]:
        if c["service_option"] == "wide-service":
            assert row(c, "storage")["below_minimum_insets_mm"] == [100, 115]
            assert c["position"].startswith("not-recommended")
        if c["service_option"] == "storage-first":
            assert row(c, "bathroom")["below_target_at_80mm"]
            assert row(c, "bathroom")["sensitivity"][0]["area_sqm"] == 6.45
            assert not row(c, "storage")["below_target_at_80mm"]


def test_no_new_partitions_occupy_shrine_backing_or_exceed_original_rear_zone(case):
    for c in build_service_study(case)["cases"]:
        dry = c["zones_mm"]["dry-backing"][0]
        assert dry == [2500, 11370, 1820, 1600]
        assert _covered([0, 11370, 6000, 6260], [r for rs in c["zones_mm"].values() for r in rs])
        for key, rects in c["zones_mm"].items():
            if key != "dry-backing":
                assert not any(_hits(r, dry) for r in rects)


def test_front_and_rear_use_their_own_translation_and_rear_body_relocation_is_explicit(case):
    result = build_service_study(case)
    rear, front = result["cases"][0], result["cases"][3]
    assert rear["entry_mode"] == "rear" and front["entry_mode"] == "front"
    assert rear["original_park_mm"] == [2680, 14550]
    assert front["original_park_mm"] == [4560, 15700]
    assert rear["palanquin_body_mm"] == front["palanquin_body_mm"] == [4560, 15700, 1200, 1700]
    assert rear["transport"]["points_mm"][0][0] == 4500
    assert front["transport"]["points_mm"][0][0] == 5160
    for c in result["cases"]:
        assert c["transport"]["body_failures"] == c["transport"]["gate_width_failures"] == []
        assert c["transport"]["outdoor_threshold_and_full_route"] == "unknown"
        assert c["transport"]["storage_dimension_source"] == "planning"
        assert c["transport"]["assembled_transport_approval"] == "unknown"


def test_larger_real_storage_body_cannot_use_old_clear_result(case):
    path = case / "inputs/physical-items.json"
    data = read_json(path)
    data["items"][0]["planning_dimensions"]["width_mm"] = 2100
    write_json(path, data)
    result = build_service_study(case)
    assert all(c["transport"]["body_failures"] and c["transport"]["gate_width_failures"] for c in result["cases"])


def test_laundry_catalog_is_not_shrunk_and_operation_cannot_overlap_body(case):
    result = build_service_study(case)
    for c in result["cases"]:
        assert c["laundry_items"][0]["rect_mm"][2:] == [650, 650]
        assert c["laundry_coordinate_failures"] == []
    modify(case, lambda s: s["common"]["laundry_operation_rects_mm"].append([80, 15900, 800, 650]))
    assert all(c["laundry_coordinate_failures"] for c in build_service_study(case)["cases"])


def test_roof_protects_shrine_and_hvac_but_does_not_approve_vibration_or_water_load(case):
    result = build_service_study(case)
    for roof in result["roof"].values():
        assert roof["coordinate_failures"] == []
        assert roof["water_only_lower_bound_kg"] == 1000
        assert roof["structure_vibration_manuals_and_replacement"] == "unknown"
        assert {p["equipment_id"] for p in roof["equipment_over_sleeping_rooms"]} == {"pump"}
        assert {p["bedroom_id"] for p in roof["equipment_over_sleeping_rooms"]} == {"B:floor-2:master2", "B:floor-3:guest3"}
        assert roof["route_rect_mm"][2] == 1000


@pytest.mark.parametrize("where", ["shrine", "hvac", "route"])
def test_equipment_service_envelope_cannot_displace_protected_space_or_existing_ac(case, where):
    def change(s):
        s["roof"]["items"][0]["rect_mm"][:2] = {
            "shrine": [4200, 10000], "hvac": [700, 16200], "route": [2700, 12050],
        }[where]
    modify(case, change)
    assert all("tank" in r["coordinate_failures"] for r in build_service_study(case)["roof"].values())


def test_first_floor_idf_stays_unresolved_despite_upper_dry_backup_body_fitting(case):
    result = build_service_study(case)
    assert result["idf"]["first_floor_priority"] == "retained-unresolved"
    assert result["idf"]["under_stair"]["finished_headroom_mm"] is None
    for value in result["idf"]["coordinate_results"].values():
        assert value["body_and_front_service_inside_dry_room"]
        assert not value["first_floor_requirement_satisfied"] and not value["floor_change_approved"]


def test_upper_idf_outside_or_wet_room_is_not_a_valid_body_fit(case):
    modify(case, lambda s: s["idf"]["upper_dry_backup"].update(room_id="B:floor-3:bath3"))
    assert all(not v["body_and_front_service_inside_dry_room"] for v in build_service_study(case)["idf"]["coordinate_results"].values())


@pytest.mark.parametrize("item", ["washer", "roof", "idf"])
def test_products_cannot_be_scaled_to_create_a_fit(case, item):
    def change(s):
        if item == "washer":
            s["common"]["laundry_items"][0]["rect_mm"][2] = 500
        elif item == "roof":
            s["roof"]["items"][0]["rect_mm"][2] = 500
        else:
            s["idf"]["upper_dry_backup"]["body_rect_mm"][2] = 500
    modify(case, change)
    with pytest.raises(ContractError, match="scaled"):
        build_service_study(case)


@pytest.mark.parametrize("change", ["frame", "backing", "gate", "duplicate", "load"])
def test_no_silent_expansion_repurposed_backing_or_unknown_to_approved(case, change):
    def mutate(s):
        if change == "frame":
            s["frame_mm"][1] += 1000
        elif change == "backing":
            s["common"]["dry_backing_rect_mm"][2] -= 500
        elif change == "gate":
            s["gates"]["architect_fire_separation_and_openings"] = "pass"
        elif change == "duplicate":
            s["options"][1] = copy.deepcopy(s["options"][0])
        else:
            s["roof"]["water_load_lower_bound_kg"] = 1
    modify(case, mutate)
    with pytest.raises(ContractError):
        build_service_study(case)


def test_stale_source_hash_is_visible_not_an_old_pass(case):
    path = case / "inputs/b32-entry-options.json"
    data = read_json(path)
    data["updated_at"] = "changed"
    write_json(path, data)
    result = build_service_study(case)
    assert result["embedded_source_mismatches"] == ["inputs/b32-entry-options.json"]


def test_repeat_hash_stable_outputs_only_new_study_and_svg_has_bounded_pixels(case):
    before = {p: sha256_file(p) for p in case.rglob("*") if p.is_file()}
    first, second = build_service_study(case), build_service_study(case)
    assert first["report_hash"] == second["report_hash"]
    assert stable_hash({k: v for k, v in first.items() if k not in {"report_hash", "generated_at"}}) == first["report_hash"]
    files = write_service_study(first, case)
    assert len(list(files["json"].parent.glob("*.svg"))) == 7
    assert read_json(files["json"]) == first
    for path in files["json"].parent.glob("*.svg"):
        tree = ET.fromstring(path.read_text())
        assert tree.attrib["width"] == "900" and tree.attrib["height"] == "1122"
        assert "未採用" in path.read_text() and "<script" not in path.read_text()
    assert all(sha256_file(p) == digest for p, digest in before.items())
    assert "原B32、ABC、需求與實測均不改" in files["markdown"].read_text()


def test_svg_is_new_partition_study_not_a_claim_of_complete_bathroom(case):
    result = build_service_study(case)
    svg = study_svg(result["cases"][0])
    assert "轉位／救援尚未重排" in svg
    assert "座位、連續動線與防火門須另排" in svg


def test_cli_is_a_small_explicit_file_workflow(case, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["house-design", "predesign", "b32-service-study", "--root", str(case)])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["comparisons"] == 6 and result["professional_approval"] == "unknown"

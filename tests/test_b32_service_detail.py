from __future__ import annotations

import json
import sys
from xml.etree import ElementTree as ET

import pytest

from house_design.b32_service_detail import (
    SOURCE,
    _circle_hits,
    _route,
    build_service_detail,
    detail_svg,
    write_service_detail,
)
from house_design.b32_services import SOURCE as SERVICE_SOURCE
from house_design.cli import main
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, write_json
from house_design.requirement_reconciliation import _snapshot


@pytest.fixture
def case(tmp_path):
    for name in (SOURCE, SERVICE_SOURCE, "inputs/project.json", "inputs/requirements.json", "inputs/physical-items.json",
                 "inputs/furniture-layout.json", "inputs/b32-entry-options.json"):
        write_json(tmp_path / name, read_json(ROOT / name))
    name = "structured/candidates/b32-entry-options/layout.js"
    snapshot = _snapshot(ROOT / name, "HOUSE_B32_ENTRY_OPTIONS", "house-b32-entry-options-v1")
    snapshot["source_hashes"] = {"inputs/b32-entry-options.json": sha256_file(tmp_path / "inputs/b32-entry-options.json")}
    path = tmp_path / name
    path.parent.mkdir(parents=True)
    path.write_text("window.HOUSE_B32_ENTRY_OPTIONS = "+json.dumps(snapshot, ensure_ascii=False)+";\n", encoding="utf-8")
    return tmp_path


def change(root, transform, name=SOURCE):
    data = read_json(root / name)
    transform(data)
    write_json(root / name, data)


def test_real_public_sources_are_current_and_studies_never_adopt_or_reduce_original_goals():
    report = build_service_detail()
    assert report["embedded_source_mismatches"] == []
    assert report["frame_mm"] == [6000, 17630] and report["land_ping"] <= 32
    assert report["professional_approval"] == "unknown" and report["rendered_qa"] == "not-run"
    assert set(report["gates"].values()) == {"unknown"}
    for c in report["cases"]:
        assert not c["adopted"] and c["original_first_floor_idf"] == "unresolved-unchanged"
        storage = next(a for a in c["original_area_rows"] if a["zone"] == "storage")
        assert storage["original_target_sqm"] == 10.5 and storage["below_target_at_80mm"]
        assert storage["sensitivity"][0]["area_sqm"] == 9.6404
        assert c["zones_mm"]["dry-backing"] == [[2500, 11370, 1820, 1600]]
        assert c["ritual_door"]["purpose"] == "ritual-entry"
        assert c["ritual_door"]["face"] == "front" and c["ritual_door"]["width_mm"] == 1800
    assert report["original_requirements"]["B.floor-1.bath_acc"]["door_swing"] == "sliding"


def test_original_offering_is_a_real_obstacle_even_with_benches_parked(case):
    for c in build_service_detail(case)["cases"]:
        control, daily, ritual = c["modes"]
        assert control["offering_rear_shift_mm"] == 0
        assert daily["offering_rear_shift_mm"] == ritual["offering_rear_shift_mm"] == 220
        assert daily["offering_to_altar_gap_mm"] == ritual["offering_to_altar_gap_mm"] == 0
        for row in c["sensitivity"]:
            modes = {m["mode"]: m for m in row["modes"]}
            assert any("hits-offering" in f for f in modes["original-table-control"]["laundry_route"]["coordinate_failures"])
            assert modes["daily-clear"]["laundry_route"]["coordinate_failures"] == []
            assert modes["daily-clear"]["laundry_route"]["washer_branch"]["coordinate_failures"] == []
            assert modes["ritual-seated"]["laundry_route"]["coordinate_failures"]


def test_two_benches_are_full_size_in_each_mode_and_parked_bodies_are_not_seats(case):
    for c in build_service_detail(case)["cases"]:
        for mode in c["modes"]:
            benches = [i for i in mode["items"] if i["id"].startswith("bench-")]
            assert len(benches) == 2
            assert all(sorted(i["rect_mm"][2:]) == [450, 1400] and i["height_mm"] == 450 for i in benches)
            assert not mode["parked_benches_are_seats"] and not mode["simultaneous_ritual_laundry_carry"]
            assert mode["protected_reserve_failures"] == []
            assert mode["bench_reposition_and_capacity"] == "unknown"
        for row in c["sensitivity"]:
            # Keep the original altar position: its 80mm rear gap is not
            # silently reused as a proof that thicker finishes will fit.
            expected = [] if row["inset_mm"] == 80 else ["altar:outside-assumed-floor"]
            assert all(m["shrine_object_operation_failures"] == expected for m in row["modes"])


def test_actual_fixture_and_turning_envelopes_work_only_as_conditional_floor_proposal(case):
    for c in build_service_detail(case)["cases"]:
        for row in c["sensitivity"]:
            bath = row["bathroom"]
            assert bath["fixture_operation_failures"] == bath["turn_coordinate_failures"] == []
            assert all(r["coordinate_failures"] == [] for r in bath["routes"].values())
            assert bath["turn_circle_mm"][2] == 750 and bath["turn_shares_shower_floor"]
            assert bath["rescue_approval"] == "unknown-no-human-rehearsal" and not bath["adopted"]
            assert bath["fallen_body_blocks_normal_entry"]
            fixtures = {i["id"]: i for i in bath["fixtures"]}
            assert fixtures["shower"]["rect_mm"][2:] == [1200, 1200]
            assert fixtures["toilet"]["rect_mm"][2:] == [450, 700]
            assert fixtures["basin"]["rect_mm"][2:] == [600, 450]


def test_bathroom_front_edge_route_does_not_cross_reserved_praying_bands(case):
    from house_design.b32_services import _hits

    for c in build_service_detail(case)["cases"]:
        protected = [r["rect_mm"] for r in c["modes"][1]["reserved_zones"] if r["id"] == "ritual-approach"]
        for row in c["sensitivity"]:
            sweeps = row["bathroom"]["routes"]["street-interior-to-bath"]["sweeps_mm"]
            assert not any(_hits(s, p) for s in sweeps for p in protected)


def test_fixed_glass_shower_cannot_keep_shared_turning_or_old_route_result(case):
    change(case, lambda c: c["bathroom"]["fixtures"][0].update(shared_step_free_floor_proposal=False))
    for c in build_service_detail(case)["cases"]:
        for row in c["sensitivity"]:
            bath = row["bathroom"]
            assert "turn-circle:hits-shower" in bath["turn_coordinate_failures"]
            assert not bath["turn_shares_shower_floor"]
            assert bath["routes"]["shower"]["coordinate_failures"]


def test_upper_narrow_leg_does_not_hide_thicker_wall_shower_failure(case):
    change(case, lambda c: c["bathroom"]["fixtures"][0].update(rect_mm=[1220, 11450, 1200, 1200]))
    report = build_service_detail(case)
    for c in report["cases"]:
        for row in c["sensitivity"][1:]:
            assert "shower:outside-assumed-floor" in row["bathroom"]["fixture_operation_failures"]


def test_basin_or_toilet_body_cannot_be_counted_as_turning_floor(case):
    change(case, lambda c: c["bathroom"]["fixtures"][1].update(rect_mm=[2400, 13600, 450, 700]))
    for c in build_service_detail(case)["cases"]:
        assert all("turn-circle:hits-toilet" in r["bathroom"]["turn_coordinate_failures"] for r in c["sensitivity"])


def test_laundry_rear_wall_layout_preserves_sizes_and_both_operation_branches(case):
    for c in build_service_detail(case)["cases"]:
        assert [i["rect_mm"][2:] for i in c["laundry"]["items"]] == [[650, 650], [600, 600]]
        assert c["laundry"]["rear_high_window_proposal"]["rights_and_effective_ventilation"] == "unknown"
        assert all(r["laundry_object_operation_failures"] == [] for r in c["sensitivity"])
    change(case, lambda c: c["laundry"]["items"][0].update(rect_mm=[115, 15500, 650, 650]))
    for c in build_service_detail(case)["cases"]:
        assert all(r["modes"][1]["laundry_route"]["coordinate_failures"] for r in c["sensitivity"])


def test_original_sliding_goal_is_not_satisfied_by_other_door_shapes(case):
    for c in build_service_detail(case)["cases"]:
        assert [s["bathroom"]["door"]["assumed_clear_mm"] for s in c["sensitivity"]] == [970, 930, 900]
        assert [s["bathroom"]["door"]["double_outward_remaining_mm"] for s in c["sensitivity"]] == [975, 935, 905]
        for row in c["sensitivity"]:
            door = row["bathroom"]["door"]
            assert door["opening_inside_shared_wall"] and door["north_surface_slide_crosses_dry_access"]
            assert door["south_surface_slide_crosses_storage_threshold"]
            assert door["single_outward_remaining_mm"] < 900
            assert not door["sliding_requirement_satisfied"] and not door["double_outward_satisfies_original_sliding"]
            assert door["selected_product"] is None and not door["adoptable"]
            assert door["rescue_hardware_fire_and_emergency_operation"] == "unknown"


def test_small_door_width_or_moved_opening_is_reported_not_approved(case):
    change(case, lambda c: c["bathroom"].update(entry_nominal_mm=1000, entry_center_y_mm=14600))
    for c in build_service_detail(case)["cases"]:
        assert all(not r["bathroom"]["door"]["opening_inside_shared_wall"] for r in c["sensitivity"])
        assert all(not r["bathroom"]["door"]["clear_width_target_met_by_assumption"] for r in c["sensitivity"])


def test_front_and_rear_never_borrow_each_others_route_or_clearance(case):
    rear, front = build_service_detail(case)["cases"]
    assert rear["entry_mode"] == "rear" and front["entry_mode"] == "front"
    for c in (rear, front):
        for row in c["sensitivity"]:
            carry = row["carry"]
            assert carry["coordinate_failures"] == carry["body_gate_failures"] == []
            assert carry["continuous_1500mm_requirement"] == "unverified-not-body-packing"
            assert carry["assembly_and_outdoor_access"] == "unknown"
    assert all(r["carry"]["original_gate_target_failures"] == [] for r in rear["sensitivity"])
    assert [r["carry"]["original_gate_target_failures"] for r in front["sensitivity"]] == [[], ["B:floor-1:storage"], ["B:floor-1:storage"]]
    assert rear["sensitivity"][0]["carry"]["points_mm"][0][1] > 16000
    assert front["sensitivity"][0]["carry"]["points_mm"][0][1] < 5000


def test_larger_actual_palanquin_cannot_reuse_old_body_result(case):
    change(case, lambda d: d["items"][0]["planning_dimensions"].update(width_mm=2100), "inputs/physical-items.json")
    for c in build_service_detail(case)["cases"]:
        assert all(r["carry"]["body_gate_failures"] for r in c["sensitivity"])


@pytest.mark.parametrize("what", ["shower", "washer", "sink", "bench", "transfer", "circle", "care", "missing-bench", "gate", "approval", "fake-floor"])
def test_no_silent_scaling_disappearance_or_approval(case, what):
    def mutate(c):
        if what == "shower":
            c["bathroom"]["fixtures"][0]["rect_mm"][2] = 900
        elif what == "washer":
            c["laundry"]["items"][0]["rect_mm"][2] = 500
        elif what == "sink":
            c["laundry"]["items"][1]["rect_mm"][2] = 500
        elif what == "bench":
            c["shrine"]["daily_park_benches"][0]["rect_mm"][2] = 900
        elif what == "transfer":
            c["bathroom"]["operations"][1]["rect_mm"][2] = 600
        elif what == "circle":
            c["bathroom"]["turn_circle_mm"][2] = 600
        elif what == "care":
            c["care_body_mm"] = [600, 600]
        elif what == "missing-bench":
            c["shrine"]["ritual_seated_benches"].pop()
        elif what == "gate":
            c["gates"]["storage_target_tradeoff"] = "approved"
        elif what == "fake-floor":
            c["bathroom"]["fixtures"][1]["shared_step_free_floor_proposal"] = True
        else:
            c["status"] = "adopted"
    change(case, mutate)
    with pytest.raises(ContractError):
        build_service_detail(case)


def test_changed_snapshot_provenance_cannot_be_claimed_as_current(case):
    change(case, lambda c: c.update(updated_at="new-source"), "inputs/b32-entry-options.json")
    result = build_service_detail(case)
    assert result["embedded_source_mismatches"] == ["inputs/b32-entry-options.json"]
    files = write_service_detail(result, case)
    assert "快照比較過期" in files["markdown"].read_text()


def test_circle_corner_is_not_a_false_rectangle_hit_and_route_rejects_diagonal():
    assert not _circle_hits([0, 0, 10], [9, 9, 3, 3])
    assert _circle_hits([0, 0, 10], [0, 0, 3, 3])
    with pytest.raises(ContractError, match="diagonal"):
        _route([[1, 1], [2, 2]], 1, 1, [[0, 0, 3, 3]], [], 0)


def test_outputs_bounded_svg_only_in_new_directory_and_exact_hashes_are_repeatable(case):
    before = {p: sha256_file(p) for p in case.rglob("*") if p.is_file()}
    report, again = build_service_detail(case), build_service_detail(case)
    assert report["report_hash"] == again["report_hash"]
    assert stable_hash({k: v for k, v in report.items() if k not in {"report_hash", "generated_at"}}) == report["report_hash"]
    files = write_service_detail(report, case)
    assert read_json(files["json"]) == report
    assert len(list(files["json"].parent.glob("*.svg"))) == 5
    for svg in files["json"].parent.glob("*.svg"):
        tree = ET.fromstring(svg.read_text())
        assert int(tree.attrib["width"])*int(tree.attrib["height"]) <= 960000
        assert "未採用" in svg.read_text() and "<script" not in svg.read_text()
    assert all(sha256_file(p) == digest for p, digest in before.items())
    text = files["markdown"].read_text()
    assert "原拉門要求保留" in text and "原目標10.5m²" in text
    assert "1460／1430mm" in text and "屋主同意的是繼續研究" in text
    assert "無後門假設" in detail_svg(report["cases"][1])


def test_small_cli_only_generates_isolated_files(case, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["house-design", "predesign", "b32-service-detail", "--root", str(case)])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["comparisons"] == 2 and result["professional_approval"] == "unknown"

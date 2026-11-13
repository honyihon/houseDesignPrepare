"""Focused C whole-floor geometry and source checks; no scene or browser."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from historical_support import native_geometry_reference

from house_design.c_ground_coordination import CONFIG, OUT, build, physical_hit
from house_design.contracts import ContractError, stable_hash
from scripts.export_c_ground_coordination import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_independent_whole_floor_preserves_originals_and_statuses(report):
    assert report["protected_controls_unchanged"] == 149
    assert report["adopted"] is report["primary_abc_or_3d_changed"] is report["full_scene_or_old_report_regenerated"] is False
    assert report["professional_approval"] == "unknown" and report["rendered_qa"] == "not-run"
    assert report["actual_site_or_product_data_received"] == 0
    assert report["frozen_selected_plans_checked_against_embedded_models"]
    assert not report["historical_qa_reused"]
    assert {x["source"] for x in report["historical_care_source_drift"]} == {"scripts/lib/model3d_openings.py", "scripts/lib/model3d_review.py"}
    original = {n: (ROOT/n).read_bytes() for n in report["config"]["pinned_sources"]}
    assert build(ROOT)["report_hash"] == report["report_hash"]
    assert original == {n: (ROOT/n).read_bytes() for n in original}


def test_repartition_conserves_ground_area_without_shrinking_stair_body(report):
    result = report["review"]
    assert result["partition"] == {"overlaps": [], "unallocated_sqm": 0, "outside_frame_sqm": 0}
    z = result["zone_reassignment"]
    assert z == {"old_stair_zone_sqm": 17.424, "new_stair_zone_sqm": 11.616,
        "from_old_stair_to_corridor_sqm": 3.768, "from_old_stair_to_care_lobby_sqm": 2.04,
        "new_floor_area_added_sqm": 0, "physical_stair_flights_shrunk": False}
    assert z["new_stair_zone_sqm"]+z["from_old_stair_to_corridor_sqm"]+z["from_old_stair_to_care_lobby_sqm"] == pytest.approx(z["old_stair_zone_sqm"])
    assert result["first_riser_route_nominal_gap_mm"] == 150
    assert report["stair_reference"]["floor_bases_mm"] == {"floor-1": 0, "floor-2": 4000, "floor-3": 7000, "floor-4": 10000}
    assert result["new_care_route_crosses_shared_landing_at_floor_level"]


def test_all_eighteen_original_item_sizes_and_operation_bands_remain(report):
    result = report["review"]
    assert result["fixtures_count"] == 18 and result["all_items_dimensions_preserved"]
    assert result["body_hits"] == result["operation_body_hits"] == result["finish_issues115"] == []
    old = {i["id"]: i for r in report["baseline_rooms"] for i in r["items"]}
    current = {i["id"]: i for r in report["rooms"] for i in r["items"]}
    assert current.keys() == old.keys()
    assert all(i["product_dimensions_mm"] == old[k]["product_dimensions_mm"] for k, i in current.items())
    assert len(result["changes"]) == 13 and all(c["size_preserved"] for c in result["changes"])
    assert current["C:floor-1:elder:furniture:tv"]["wall_anchor"] == "right"
    assert current["C:floor-1:elder:furniture:bed"]["body_mm"] == [115, 15995, 1880, 1520]
    assert len(result["elevated_tv_floor_projection_overlaps"]) == 2
    assert all(r["vertical_intervals_disjoint"] for r in result["elevated_tv_floor_projection_overlaps"])
    tv, table = [current["C:floor-1:living:furniture:"+n] for n in ["tv", "coffee-table"]]
    assert not physical_hit(tv, table)
    assert all(i["operation_mm"] is not None for i in current.values() if old[i["id"]]["operation_mm"] is not None)


def test_routes_recomputed_for_new_front_gate_and_care_openings(report):
    routes = {r["id"]: r for r in report["review"]["routes"]}
    assert len(routes) == 6
    for r in routes.values():
        assert r["within_model_floor"] and r["outside_sqm"] == 0 and not r["fixed_body_hits"] and not r["first_riser_hit"]
        assert r["actual_care_access"].startswith("unknown")
    assert [3500, 9160] in routes["arcade-to-bed"]["points_mm"]
    assert [3000, 9160] in routes["arcade-to-bed"]["points_mm"]
    assert routes["arcade-to-bed"]["width_mm"] == routes["bed-to-bath"]["width_mm"] == 900
    assert routes["visitor-to-wc"]["width_mm"] == 600
    assert routes["visitor-to-wc"]["visitor_door_leaf_hardware_unknown"]
    assert report["review"]["visitor_wc_hypothetical_finished_mm"] == 670
    assert report["review"]["visitor_wc_door_leaf_and_rescue"] == "unknown"


def test_eighty_one_independent_states_have_their_own_blockers(report):
    cases = report["review"]["door_combinations"]
    assert len(cases) == 81 and len({tuple(c["states"].values()) for c in cases}) == 81
    for c in cases:
        assert not c["panel_fixed_hits"] and not c["panel_pair_hits"]
        assert c["route_door_hits"]["arcade-to-bed"] == sorted(k for k in ["street", "front", "bedroom"] if c["states"][k] != "open")
        assert c["route_door_hits"]["bed-to-bath"] == (["bath"] if c["states"]["bath"] != "open" else [])
        assert not c["route_door_hits"]["visitor-to-wc"]  # Its own unmodeled door stays explicitly unknown.
    assert len(report["review"]["door_full_travel"]) == 7
    assert all(not t["fixed_hits"] for t in report["review"]["door_full_travel"])
    assert all(t["method"] == "exact-axis-translation-envelope" for t in report["review"]["door_full_travel"] if t["door"] != "street")


def test_bath_retains_wet_and_offset_reach_costs_and_tight_margins(report):
    b = report["bath"]
    assert b["nominal_sqm"] == 7.2 and b["after115_outline_sqm"] == pytest.approx(6.0109)
    assert b["margins_mm"] == {"basin_arrival_face_mm": 50, "basin_arrival_lateral_offset_mm": 250,
        "transfer_to_basin_mm": 165, "board_to_folded_seat_mm": 58.5, "board_to_right_rail_mm": 18.5, "door_pack_to_turn_reserve_mm": 35}
    assert b["single_20mm_rail_margin_remaining_mm"] == -1.5
    assert b["shared_shower_floor_sqm"] > 0 and not b["independent_dry_turn_floor"]
    assert b["operation_transfer_overlap_sqm"] == .2675 and not b["simultaneous_basin_and_transfer"]
    assert b["folded_seat_raised_arm_only"] and b["folded_hardware_sweep_not_all_care_states"]
    assert not b["reserve_fixed_hits"] and not b["hardware_full_sweep_fixed_hits"]
    assert b["centered_basin_control"]["coordinate_failures"]
    assert report["review"]["care_lobby_finished_depth_mm"] == 1470
    assert not report["review"]["care_lobby_independent_1500_turn_proven"]
    assert not report["review"]["public_caregiver_bath_without_bedroom"]


def test_upper_stair_hvac_window_and_single_washer_references_preserved(report):
    parent = json.loads((ROOT/report["config"]["main_report"]).read_text())
    original = next(s for o in parent["options"] if o["id"] == "c-split" for s in o["states"] if s["id"] == "daily")
    assert report["upper_floors_unchanged_hash"] == stable_hash(original["plans"]["floors"][1:])
    original_rooms = {r["key"]: r for r in original["plans"]["floors"][0]["rooms"]}
    assert all(r["source_features"] == original_rooms[r["id"]]["features"] for r in report["rooms"])
    assert report["front_gate"] == original_rooms["stair1f"]["features"]["c_front_gate"]
    assert report["preserved_washer_reference"] == [{"floor": "floor-2", "id": "C:floor-2:balcony2f:furniture:washer"}]
    assert all(r["over_bed_body_sqm"] == 0 for r in report["review"]["bed_projection"])
    assert [r["upper_room"] for r in report["review"]["bed_projection"]] == ["C:floor-2:bath2f", "C:floor-3:bath3f"]
    for key in ["garage", "elder", "elder-bath", "public-bath", "service"]:
        assert next(r["rect_mm"] for r in report["rooms"] if r["id"] == key) == next(r["rect_mm"] for r in report["baseline_rooms"] if r["id"] == key)


@pytest.mark.parametrize("defect", ["body", "old-reading-chair", "old-route", "wet-bed", "shrink", "parent-hash"])
def test_real_regressions_fail_without_rendering(monkeypatch, defect):
    import house_design.c_ground_coordination as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    if defect == "body":
        cfg["item_rectangles_mm"]["C:floor-1:living:furniture:sofa"] = [115, 6815, 900, 1800]
    elif defect == "old-reading-chair":
        cfg["item_rectangles_mm"]["C:floor-1:living:furniture:reading-chair"] = [4700, 7945, 900, 850]
    elif defect == "old-route":
        cfg["routes"][0]["points_mm"] = [[3285, 3000], [3285, 7200], [3000, 7200], [3000, 12950], [2850, 12950], [2850, 14600], [2650, 14600], [2650, 16700]]
    elif defect == "wet-bed":
        cfg["item_rectangles_mm"]["C:floor-1:elder:furniture:bed"] = [115, 15500, 1880, 1520]
    elif defect == "shrink":
        cfg["item_rectangles_mm"]["C:floor-1:elder:furniture:bed"][2] = 1780
    else:
        cfg["pinned_sources"][cfg["main_report"]] = "0"*64
    monkeypatch.setattr(module, "read_json", lambda p: cfg if p == ROOT/CONFIG else read(p))
    with pytest.raises(ContractError):
        build(ROOT)


def test_artifact_hashes_bounded_sheets_local_links_and_reply_blanks(report):
    archived = native_geometry_reference(ROOT/OUT/"review.json", report)
    files = render(archived)
    assert len(files) == 9 and sum(n.endswith(".svg") for n in files) == 3
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    for name, expected in report["source_hashes"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n, h in manifest["artifacts"].items())
    assert all((ROOT/OUT/n).read_bytes() == data.encode() for n, data in files.items())
    for n, data in files.items():
        if n.endswith(".svg"):
            svg = ET.fromstring(data)
            assert int(svg.attrib["width"])*int(svg.attrib["height"]) <= 1_680_000
            assert all(float(t.attrib["y"]) < 1200 for t in svg.iter() if t.tag.endswith("text"))
    assert "未採用" in files["index.html"] and "18.5mm" in files["index.html"]
    assert len(list(csv.DictReader(io.StringIO(files["door-route-matrix.csv"].lstrip("\ufeff"))))) == 81
    for ref in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]):
        assert (ROOT/OUT/ref).is_file()
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"])

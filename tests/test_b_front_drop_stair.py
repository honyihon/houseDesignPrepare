"""Local G0/G1 landing and G2/G3 vertical tread conflicts, not global impossibility."""
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

from house_design.b_front_drop_stair import CONFIG, OUT, build
from house_design.b_upper_replan import rect
from house_design.contracts import ContractError, stable_hash
from scripts.export_b_front_drop_stair import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_sources_original_ground_versions_and_all_controls_stay_unchanged(report):
    before = {n: (ROOT/n).read_bytes() for n in report["config"]["pinned_sources"]}
    assert report["report_hash"] == build(ROOT)["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in before}
    assert report["protected_controls_unchanged"] == 149 and report["actual_site_or_product_data_received"] == 0
    assert not report["primary_abc_or_3d_changed"] and not report["adopted"] and not report["all_original_requirements_met"]
    assert report["professional_approval"] == "unknown" and report["rendered_qa"] == "not-run"


def test_local_square_routes_lie_in_original_platform_before_shaft_not_full_access(report):
    s = report["stair_screen"]
    assert s["landing_mm"] == [80, 3970, 2200, 1000]
    assert s["source"]["geometry"]["risers"] == 24 and s["source"]["height_mm"] == 4000
    assert len(s["local_routes"]) == 2
    assert all(r["width_mm"] == 700 and r["inside_original_landing_without_new_shaft"] for r in s["local_routes"])
    assert all(r["actual_door_or_full_access_approval"] == "unknown" for r in s["local_routes"])
    assert not s["entire_human_route_all_possible_chases_headroom_or_structure_checked"]


def test_G0_and_G1_cannot_be_passed_as_free_shaft_from_no_furniture_collision(report):
    candidates = {c["id"]: c for c in report["stair_screen"]["candidates"]}
    assert candidates["G0"]["landing_overlap_sqm"] == .16
    assert {r["route"] for r in candidates["G0"]["local_route_hits"]} == {"street-to-left-flight", "shrine-side-to-left-flight"}
    assert {r["route"] for r in candidates["G1"]["local_route_hits"]} == {"shrine-side-to-left-flight"}
    assert not candidates["G0"]["tread_hits_in_hypothetical_vertical_column"]
    assert not report["G0_can_continue_as_free_shaft_without_landing_redesign"]
    assert all(not c["adopted"] and not c["new_structural_hole_or_actual_pipe_route_approved"] for c in candidates.values())


def test_G2_exceeds_central_gap_and_G3_is_not_a_free_vertical_understair_column(report):
    screen = report["stair_screen"]
    candidates = {c["id"]: c for c in screen["candidates"]}
    assert screen["central_gap_width_mm"] == 200 and screen["required_reserved_shaft_width_mm"] == 400
    assert len(candidates["G2"]["tread_hits_in_hypothetical_vertical_column"]) == 6
    assert {r["id"] for r in candidates["G3"]["tread_hits_in_hypothetical_vertical_column"]} == {"left-2", "left-3", "left-4"}
    assert [r["top_z_mm"] for r in candidates["G3"]["tread_hits_in_hypothetical_vertical_column"]] == [333.333, 500, 666.667]
    assert screen["hypothetical_column_z_mm"] == [0, 3504.4]
    assert screen["all_listed_candidates_conflict"] and report["no_all_global_solutions_possible_claim"]


def test_both_ground_options_all_three_states_retain_sacred_arcade_and_body_evidence(report):
    states = report["ground_states"]
    assert len(states) == 6
    assert {(s["option"], s["state"]) for s in states} == {(o, state) for o in ["b-rear-split", "b-front-split"] for state in ["daily", "ritual", "carry"]}
    ground = json.loads((ROOT/report["config"]["ground_report"]).read_text())
    for row in states:
        f = next(s["floor1"] for o in ground["stack_and_entry"]["options"] if o["id"] == row["option"] for s in o["states"] if s["id"] == row["state"])
        assert row["floor1_source_hash"] == stable_hash(f)
        assert row["G0_over_entrance_landing_sqm"] == row["G0_over_stair_sqm"] == .16
        assert row["G0_over_arcade_sqm"] == row["G0_over_sacred_or_backing_sqm"] == row["G0_over_palanquin_storage_sqm"] == 0
        assert not row["G0_fixed_body_hits"] and not row["no_furniture_hit_means_free_shaft"]
        assert not row["ground_geometry_modified"] and not row["full_carry_route_door_motion_and_care_revalidated"]


def test_nominal_widening_preserves_flights_but_has_unapproved_shrine_cost(report):
    w = report["width_boundary"]
    assert w["source_flight_width_mm"] == 1000 and w["source_stair_footprint_width_mm"] == 2200
    assert w["two_flights_plus_shaft_width_before_new_chase_walls_mm"] == 2400
    assert w["minimum_extra_nominal_footprint_width_before_chase_walls_mm"] == 200
    assert w["hypothetical_widening_over_sacred_front_sqm"] == 1.04
    assert rect(w["hypothetical_same_outer_edges_room_widening_mm"]).area/1e6 == 1.04
    assert not w["hypothetical_widening_approved_or_minimum_legal_stair_width_selected"]
    assert not report["source_P4_positive_section_budget_resolves_ground_conflict"]


@pytest.mark.parametrize("defect", ["parent-drift", "move-G0", "shrink-shaft", "route-outside", "shrink-route"])
def test_mixed_sources_or_promoted_free_shaft_inputs_stop_export(monkeypatch, defect):
    import house_design.b_front_drop_stair as module
    read = module.read_json
    cfg = copy.deepcopy(read(ROOT/CONFIG))
    if defect == "parent-drift":
        cfg["pinned_sources"][cfg["p4_report"]] = "0"*64
    elif defect == "move-G0":
        cfg["candidates"][0]["rect_mm"][0] += 500
    elif defect == "shrink-shaft":
        cfg["candidates"][2]["rect_mm"][2] = 200
    elif defect == "route-outside":
        cfg["local_routes"][0]["points_mm"][0][1] = 3000
    else:
        cfg["local_route_width_mm"] = 500
    monkeypatch.setattr(module, "read_json", lambda p: cfg if p == ROOT/CONFIG else read(p))
    with pytest.raises(ContractError):
        build(ROOT)


def test_static_sources_artifacts_links_bounds_blank_replies_and_no_AI_consensus(report):
    files = render(report)
    assert len(files) == 10 and sum(n.endswith(".svg") for n in files) == 3
    assert all((ROOT/OUT/n).read_bytes() == value.encode() for n, value in files.items())
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in report["source_hashes"].items())
    manifest = json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest() == h for n, h in manifest["artifacts"].items())
    for name, value in files.items():
        if name.endswith(".svg"):
            svg = ET.fromstring(value)
            assert int(svg.attrib["width"])*int(svg.attrib["height"]) <= 1_680_000
            assert all(0 <= float(t.attrib["y"]) < 1200 for t in svg.iter() if t.tag.endswith("text"))
    assert all((ROOT/OUT/ref).is_file() for ref in re.findall(r'(?:href|src)="([^"]+)"', files["index.html"]))
    assert "局部反例不是全域無解" in files["index.html"] and "未採用" in files["index.html"]
    for row in csv.DictReader(io.StringIO(files["engineering-replies.csv"].lstrip("\ufeff"))):
        assert all(row[k] == "" for k in ["建築機電結構回覆", "費用工期及保固", "屋主選擇", "審查及施工圖發行"])
    brief = (ROOT/"Docs/claude-b-front-drop-brief-v1.md").read_text()
    assert "不呼叫工具" in brief and "不縮" in brief and "不是只避神桌本體" in brief
    assert "本輪沒有回應或共識" in report["recommended_sequence"][-1]

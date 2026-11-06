"""Meaningful geometry/requirements boundaries, with no browser, CLI cloud or full scene."""
import copy
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

from house_design.b_fengshui_strict import CONFIG, OUT, analyze_option, area_shape, build, collision
from house_design.contracts import ContractError, sha256_file
from scripts.export_b_fengshui_strict import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_source_mismatch_rejected_before_export(tmp_path):
    cfg = json.loads((ROOT/CONFIG).read_text())
    cfg["source_report"] = "changed.json"
    (tmp_path/"inputs").mkdir()
    (tmp_path/CONFIG).write_text(json.dumps(cfg))
    (tmp_path/"changed.json").write_text("{}")
    with pytest.raises(ContractError, match="source changed"):
        build(tmp_path)


def test_never_stamp_all_requirements_religion_or_claude_consensus(report):
    assert report["adopted"] is report["all_requirements_met"] is False
    assert report["professional_approval"] == "unknown"
    assert report["claude_discussion"]["consensus"] is False
    assert report["claude_discussion"]["status"] == "timeout-no-completed-discussion"
    status = json.loads((ROOT/report["claude_discussion"]["result_reference"]).read_text())
    assert status["own_process_group_closed"] is True and status["retry"] == "not-attempted"
    assert status["stdout_sha256"] == hashlib.sha256(b"").hexdigest()


def test_both_versions_and_all_states_remain_independent(report):
    assert [o["id"] for o in report["options"]] == ["b-rear-split", "b-front-split"]
    for o in report["options"]:
        assert [s["id"] for s in o["states"]] == ["daily", "ritual", "carry"]
    assert report["options"][0]["states"][2]["source_state_hash"] != report["options"][1]["states"][2]["source_state_hash"]


def test_complete_rooms_not_only_beds_avoid_ritual_and_backing(report):
    for o in report["options"]:
        protected = unary_union([Polygon(p) for p in o["protected_polygons_mm"]])
        backing = area_shape(report["config"]["floor1"]["backing_rect_mm"])
        for f in o["upper_floors"]:
            bed = Polygon(f["rooms"][0]["polygon_mm"])
            assert bed.intersection(protected).area == 0
            assert Polygon(f["rooms"][1]["polygon_mm"]).equals(backing)
            for room in f["rooms"]:
                if "illustrative_finished_rect_mm" in room:
                    wet = Polygon(room["polygon_mm"])
                    assert not collision(wet, protected)
                    assert wet.distance(backing) >= 200
                    assert not collision(wet, area_shape(o["palanquin_rect_mm"]))


def test_regressed_wet_projection_and_route_cannot_keep_clear_status(report):
    source = json.loads((ROOT/report["config"]["source_report"]).read_text())
    cfg = copy.deepcopy(report["config"])
    cfg["upper"]["public_bath_rect_mm"][1] = 12570
    cfg["upper"]["bedroom_route_points_mm"][0][0] = -100
    cfg["upper"]["bedroom_route_points_mm"][1][0] = -100
    changed = analyze_option(source, "b-rear-split", cfg)
    rows = {f["id"]: f for f in changed["findings"]}
    assert rows["B-FS-02-floor-2"]["status"] == "conflict"
    assert rows["B-AR-01-floor-2"]["status"] == "conflict"
    assert rows["B-AR-02-floor-2"]["status"] == "conflict"


def test_partition_has_no_gaps_borrowed_area_or_duplicates(report):
    target = area_shape([0, 11370, 6000, 6260])
    for o in report["options"]:
        for f in o["upper_floors"]:
            polys = [Polygon(r["polygon_mm"]) for r in f["rooms"]]
            assert unary_union(polys).equals(target)
            assert sum(p.area for p in polys) == target.area
            assert len([r for r in f["rooms"] if "illustrative_finished_rect_mm" in r]) == (2 if f["id"] == "floor-2" else 1)


def test_l_area_uses_real_polygon_and_preserves_shortfall(report):
    o = report["options"][0]
    assert o["nominal_bedroom_sqm"] == pytest.approx(22.398)
    cases = {r["inset_each_mm"]: r for r in o["area_sensitivity"]}
    assert cases[115]["bedroom_sqm"] == pytest.approx(20.1141)
    assert cases[150]["bedroom_sqm"] == pytest.approx(19.44)
    assert cases[150]["bedroom_sqm"] < 20
    assert cases[115]["private_bath_sqm"] == pytest.approx(3.6091)
    assert cases[115]["private_bath_sqm"] < 4.5
    assert cases[115]["private_bath_sqm"]+cases[115]["public_bath_sqm"] == pytest.approx(7.48)
    assert o["remaining"][0]["status"] == "decision-or-redesign-required"


def test_all_original_bedroom_sizes_and_bath_bodies_preserved(report):
    for o in report["options"]:
        for f in o["upper_floors"]:
            sizes = {i["id"]: sorted(i["rect_mm"][2:]) for i in f["rooms"][0]["furniture"]}
            assert sizes == {"bed": [1800, 2000], "wardrobe": [600, 1800], "vanity": [500, 1200]}
            window = f["rooms"][0]["window"]
            assert window["b"][0]-window["a"][0] == 2400
            for room in f["rooms"]:
                if "illustrative_finished_rect_mm" not in room:
                    continue
                sizes = {i["id"]: sorted(i["rect_mm"][2:]) for i in room["furniture"]}
                assert sizes["toilet"] == [450, 700] and sizes["shower"] == [900, 900]
                assert sizes["basin"] == ([550, 900] if "private" in room["id"] else [450, 600])


def test_operations_only_share_each_other_not_other_fixed_bodies(report):
    for o in report["options"]:
        for f in o["upper_floors"]:
            for r in f["rooms"]:
                if "illustrative_finished_rect_mm" not in r:
                    continue
                assert r["body_collisions"] == r["operation_body_hits"] == r["arrival_body_hits"] == []
                assert r["body_and_operations_inside"] is True
                assert r["sequential_operation_pairs"]
                assert r["actual_product_pack"] is r["actual_finished_clear_mm"] is None


def test_door_arrivals_and_open_leaf_budgets_do_not_hit_bodies(report):
    for o in report["options"]:
        for f in o["upper_floors"]:
            bedroom = f["rooms"][0]
            foyer = Polygon(f["rooms"][2]["polygon_mm"])
            bed_poly = Polygon(bedroom["polygon_mm"])
            for r in f["rooms"]:
                if "illustrative_finished_rect_mm" not in r:
                    continue
                other = bedroom if "private" in r["id"] else f["rooms"][2]
                clear_room = bed_poly.buffer(-115, join_style=2) if "private" in r["id"] else foyer.buffer(-115, join_style=2)
                assert clear_room.covers(area_shape(r["outside_approach_mm"]))
                door = r["doors"][0]
                assert not collision(area_shape(door["parked_leaf_budget_mm"]), area_shape(r["outside_approach_mm"]))
                for item in other["furniture"]:
                    assert not collision(area_shape(door["swept_rect_mm"]), area_shape(item["rect_mm"]))


def test_nine_hundred_local_route_handles_l_corner_and_closet(report):
    for o in report["options"]:
        for row in o["findings"]:
            if row["id"].startswith("B-AR-02"):
                assert row["measurements"]["route_inside_115_polygon"] is True
                assert row["measurements"]["route_body_hits"] == []
                assert "門組仍未知" in row["note"]


def test_shifted_altar_axis_and_original_carry_furniture_survive(report):
    for o in report["options"]:
        for st in o["states"]:
            rooms = {r["id"].split(":")[-1]: r for r in st["floor1"]["rooms"]}
            altar = next(i for i in rooms["shrine"]["furniture"] if i["id"].endswith(":altar"))
            assert altar["rect_mm"] == [2755, 10690, 1800, 600]
            door = next(d for d in rooms["shrine-front"]["features"]["doors"] if d["face"] == "front")
            assert rooms["shrine-front"]["rect_mm"][0]+door["ratio"]*3600 == 3655
            assert door["width_mm"] == 1800
            assert rooms["corridor1"]["rect_mm"] == [4670, 11370, 1330, 1600]
            items = [i for r in rooms.values() for i in r["furniture"]]
            assert len([i for i in items if i["id"].endswith(":bench-1") or i["id"].endswith(":bench-2")]) == 2
            assert len([i for i in items if i["id"].endswith(":offering")]) == 1
            assert all("placement" not in i for i in items)


def test_moved_indoor_units_are_in_bedrooms_and_route_lengths_recalculated(report):
    for o in report["options"]:
        for f in o["upper_floors"]:
            room = f["rooms"][0]
            u = room["hvac_candidate"]
            assert Polygon(room["polygon_mm"]).covers(area_shape(u["rect_mm"]))
            assert u["rect_mm"][0]+475 == 3000
            assert u["route"]["estimated_routed_length_mm"] == (10405 if f["id"] == "floor-2" else 8745)
            assert u["manual"] is None


def test_protected_controls_remain_current(report):
    protected = json.loads((ROOT/report["config"]["protected_controls"]).read_text())
    assert report["protected_controls_unchanged"] == 149
    for name, sha in protected["hashes"].items():
        assert sha256_file(ROOT/name) == sha


def test_roof_projection_stays_explicit_and_missing_equipment_unknown(report):
    for o in report["options"]:
        assert o["roof_protected_footprints_mm"] == o["protected_polygons_mm"]
        f = next(f for f in o["findings"] if f["id"] == "B-FS-05")
        assert f["measurements"]["listed_roof_units"] == 2
        assert f["measurements"]["body_over_protected"] == []
        assert f["measurements"]["future_roof_wet_equipment"] is None


def test_outputs_current_small_and_explicit_about_unfinished_review(report):
    outputs = render(report)
    assert len(outputs) == 8
    for name, value in outputs.items():
        assert (ROOT/OUT/name).read_bytes() == value.encode()
        if name.endswith(".svg"):
            el = ET.fromstring(value)
            assert float(el.attrib["width"])*float(el.attrib["height"]) <= 1_600_000
            assert report["source_layout_report_sha256"] in value
    assert "沒有取得Claude建議" in outputs["index.html"]
    assert "未達原4.5㎡下限" in outputs["B03-upper-detail.svg"] or "不把本體放得下當面積要求已達標" in outputs["B03-upper-detail.svg"]
    assert "--timeout 900" in outputs["index.html"]

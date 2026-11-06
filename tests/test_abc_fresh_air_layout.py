"""Small ERV reservation/quotation checks; no browser, scene or fan generation."""
import copy
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

import pytest

import house_design.abc_fresh_air_layout as layout
from house_design.abc_fresh_air_layout import (
    CONFIG,
    COST_FIELDS,
    OUT,
    build,
    contains,
    corridor_rects,
    duct_section,
    lifecycle_cost,
    polygon_rect_area,
    protected_room,
    screen_corridor,
    screen_unit,
    velocity,
)
from house_design.contracts import ContractError, read_json, sha256_file
from scripts.export_abc_fresh_air_layout import render, service_rows

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_parent_file_and_semantic_revision_cannot_be_silently_rebound(monkeypatch):
    original = layout.read_json

    def wrong_file(path):
        cfg = original(path)
        if Path(path) == ROOT/CONFIG:
            cfg["parent_file_sha256"] = "0"*64
        return cfg

    monkeypatch.setattr(layout, "read_json", wrong_file)
    with pytest.raises(ContractError, match="parent changed"):
        build(ROOT)

    def wrong_semantics(path):
        cfg = original(path)
        if Path(path) == ROOT/CONFIG:
            cfg["parent_report_hash"] = "0"*64
        return cfg

    monkeypatch.setattr(layout, "read_json", wrong_semantics)
    with pytest.raises(ContractError, match="parent inputs changed"):
        build(ROOT)


def test_eight_plan_reservations_do_not_approve_eight_machines_or_service(report):
    assert len(report["units"]) == 8
    assert report["owner_people"] == {"A": 4, "B": 2, "C": 3}
    assert report["actual_machine_count"] is report["selected_product"] is None
    assert report["adopted"] is report["full_MEP_fit_verified"] is False
    assert report["professional_approval"] == "unknown" and report["browser_qa"] == "not-run"
    for u in report["units"]:
        assert u["inside_nominal_host"] and not u["fixed_furniture_projection_hits"]
        assert not u["protected_room_projection_hits"]
        assert not u["ceiling_beam_wall_door_checked"] and not u["service_egress_and_ladder_approved"]
        assert not u["full_filter_and_body_removal_verified"]
        assert u["actual_unit_and_port_geometry"] is None
        assert u["phase"] == ("commission-with-current-use" if u["floor"] == "floor-3" else "install-now")
    for row in service_rows(report):
        assert row["approved"] is False and row["whole_unit_replacement_path"] is None


def test_concave_orthogonal_host_is_not_its_bounding_box():
    room = {"polygon_mm": [[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]]}
    assert polygon_rect_area(room["polygon_mm"], [0, 0, 4, 4]) == 7
    assert contains(room, [0, 0, 1, 4])
    assert not contains(room, [.5, .5, 2, 2])
    with pytest.raises(ContractError, match="orthogonal"):
        polygon_rect_area([[0, 0], [3, 0], [2, 2]], [0, 0, 1, 1])


def test_unit_and_service_cannot_be_put_over_a_bed_or_idf(report):
    cfg = report["config"]
    unit = copy.deepcopy(cfg["units"][0])
    unit.update(building="C", floor="floor-1", room="elder", rect_mm=[100, 16100, 1600, 1000])
    with pytest.raises(ContractError, match="fixed furniture"):
        screen_unit(unit, report["roster"], cfg)
    assert protected_room({"id": "C:floor-1:sideyard", "name": "IDF乾式壁龕"})
    assert not protected_room({"id": "A:floor-2:rear-hall", "name": "後梯廳乾區"})


def test_partial_corridors_keep_unknown_heights_and_all_four_full_routes_pending(report):
    assert len(report["partial_corridors"]) == 5
    for r in report["partial_corridors"]:
        assert r["width_mm"] == 500 and r["height_budget_mm"] == 300
        assert r["route_z_mm"] is r["actual_outdoor_ports"] is r["actual_supply_return_terminals"] is None
        assert not r["all_floor_rooms_connected"] and not r["pressure_noise_condensation_fire_approved"]
        assert not r["protected_plan_hits"]
    c1 = next(r for r in report["partial_corridors"] if r["id"] == "C1-D")
    c2 = next(r for r in report["partial_corridors"] if r["id"] == "C2-D")
    assert any("fridge" in i for i in c1["fixed_body_xy_below_or_at_route"])
    assert any("wardrobe" in i for i in c2["fixed_body_xy_below_or_at_route"])
    assert c1["sealed_kitchen_crossings"] == ["C:floor-1:kitchen"]


def test_500mm_band_not_just_centerline_avoids_c_stair(report):
    cfg = report["config"]
    c1 = next(r for r in cfg["partial_clean_duct_corridors"] if r["id"] == "C1-D")
    bad = copy.deepcopy(c1)
    bad["points_mm"] = [[4900, 8400], [1900, 8400], [1900, 13300], [2200, 13300], [2200, 15000]]
    base = read_json(ROOT/read_json(ROOT/"inputs/abc-fresh-air-basis.json")["source_report"])
    with pytest.raises(ContractError, match="stair1f"):
        screen_corridor(bad, report["roster"], cfg, base["c_ac01_review"])
    u = next(u for u in report["units"] if u["id"] == "C1-N")
    assert u["room"] == "dining" and u["rect_mm"][1]+u["rect_mm"][3] < 8550
    with pytest.raises(ContractError, match="orthogonal"):
        corridor_rects([[0, 0], [5, 5]], 500)


def test_corridor_cannot_reference_another_building_or_drop_third_floor_use(monkeypatch):
    original = layout.read_json

    def wrong_unit(path):
        cfg = original(path)
        if Path(path) == ROOT/CONFIG:
            cfg["partial_clean_duct_corridors"][0]["unit"] = "B2-N"
        return cfg

    monkeypatch.setattr(layout, "read_json", wrong_unit)
    with pytest.raises(ContractError, match="same building and floor"):
        build(ROOT)

    def empty_future(path):
        cfg = original(path)
        if Path(path) == ROOT/CONFIG:
            cfg["units"][2]["phase"] = "rough-in-only"
        return cfg

    monkeypatch.setattr(layout, "read_json", empty_future)
    with pytest.raises(ContractError, match="third floors"):
        build(ROOT)


def test_rejected_shaft_sites_do_not_reject_all_central_architectures(report):
    shafts = {s["building"]: s for s in report["central_shaft_tests"]}
    assert shafts["A"]["remaining_side_strips_mm"] == [90, 1370]
    assert shafts["B"]["remaining_side_strips_mm"] == [130, 500]
    assert shafts["C"]["remaining_side_strips_mm"] == [885, 100]
    assert shafts["B"]["master_after_new_shaft_sqm"] == 19.7611
    assert not shafts["B"]["meets_original_master_20"]
    for s in shafts.values():
        assert s["reserved_each_floor_sqm"] == .315
        assert s["candidate_rejected_here"] and not s["meets_study_bypass_goal"]
        assert not s["all_central_arrangements_impossible"]
        assert not s["actual_fire_lining_structure_and_replacement_verified"]
        assert s["section_width_margin_mm"] == s["section_depth_margin_mm"] == 50


def test_duct_arithmetic_is_not_pressure_or_noise_selection(report):
    floor, central = (report["duct_sections"][s] for s in ["floor_pair", "central_pair"])
    assert (floor["outer_diameter_mm"], floor["required_pair_width_mm"], floor["width_margin_mm"], floor["height_margin_mm"]) == (175, 500, 0, 25)
    assert (central["outer_diameter_mm"], central["required_pair_width_mm"]) == (200, 550)
    assert velocity(60, 125) == 1.358 and velocity(30, 125) == .679
    assert velocity(None, 125) is None
    assert len(report["flow_sensitivity"]) == 27
    assert all(r["illustrative_flow_m3_h"] is None and r["single_125mm_duct_velocity_m_s"] is None
        for r in report["flow_sensitivity"] if r["floor"] == "floor-3")
    assert all(r["pressure_loss_pa"] is r["actual_minimum_machine_speed_at_pressure"] is None
        for r in report["flow_sensitivity"])


@pytest.mark.parametrize("bad", [-1, True, float("nan"), float("inf")])
def test_invalid_flow_or_section_dimensions_rejected(bad):
    with pytest.raises(ContractError):
        velocity(bad, 125)
    budget = read_json(ROOT/CONFIG)["duct_budgets"]["floor_pair"]
    budget["width_mm"] = bad
    with pytest.raises(ContractError):
        duct_section(budget)


def test_cost_unknown_never_zero_and_every_scope_must_be_present():
    costs = dict.fromkeys(COST_FIELDS, 0)
    assert lifecycle_cost(costs, 10) == 0
    costs.update(equipment=100, annual_filters=2, annual_labor=3, annual_electricity=4, ten_year_replacements=5)
    assert lifecycle_cost(costs, 10) == 195
    costs["annual_filters"] = None
    assert lifecycle_cost(costs, 10) is None
    costs["annual_labor"] = -1
    with pytest.raises(ContractError, match="nonnegative"):
        lifecycle_cost(costs, 10)
    with pytest.raises(ContractError, match="every equal-scope"):
        lifecycle_cost({}, 10)


def test_b_front_distribution_not_finished_and_both_entry_options_remain(report):
    assert "前側" in report["b_distribution_gap"] and "不鎖一層一機" in report["b_distribution_gap"]
    assert len(report["b_front_and_rear_retained"]) == 2
    assert all(r["states"] == ["daily", "ritual", "carry"] for r in report["b_front_and_rear_retained"])
    assert len(report["builder_quotes"]) == 9
    assert {(r["building"], r["architecture"]) for r in report["builder_quotes"]} == {
        (b, a) for b in "ABC" for a in ["building-central", "floor-zoned", "supply-with-designed-exit"]}
    for row in report["builder_quotes"]:
        assert row["model_and_count"] is row["ten_year_cost"] is row["quote_date"] is None
        assert all(row[k] is None for k in COST_FIELDS)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.urls.extend(a[k] for k in ["href", "src"] if k in a)
        if "id" in a:
            self.ids.add(a["id"])


def test_bounded_artifacts_current_sources_controls_and_local_links(report):
    files = render(report)
    manifest = json.loads(files["artifact-manifest.json"])
    assert len(files) == 11 and len(manifest["artifacts"]) == 10
    for name, content in files.items():
        assert (ROOT/OUT/name).read_bytes() == content.encode(), name
        if name in manifest["artifacts"]:
            assert hashlib.sha256(content.encode()).hexdigest() == manifest["artifacts"][name]
        if name.endswith(".svg"):
            svg = ET.fromstring(content)
            assert svg.attrib["viewBox"] == "0 0 1400 1100"
            assert float(svg.attrib["width"])*float(svg.attrib["height"]) <= 1_600_000
            assert report["report_hash"] in content and "未採用" in content
    for name, digest in report["source_hashes"].items():
        assert sha256_file(ROOT/name) == digest, name
    controls = read_json(ROOT/report["config"]["protected_controls"])
    assert len(controls["hashes"]) == report["protected_controls_unchanged"] == 149
    for name, digest in controls["hashes"].items():
        assert sha256_file(ROOT/name) == digest, name
    parser = Links()
    parser.feed(files["index.html"])
    for url in parser.urls:
        part = urlsplit(url)
        assert not part.scheme and not part.netloc
        if not part.path:
            assert part.fragment in parser.ids
        else:
            assert (ROOT/OUT/unquote(part.path)).is_file(), url

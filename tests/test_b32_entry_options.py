"""B32 geometry, option isolation and evidence boundaries; not a legal solver."""
from __future__ import annotations

import copy
import json
import re
from xml.etree import ElementTree as ET

import export_b32_entry_options as export
import pytest
from lib.model3d_placement import overlaps


@pytest.fixture(scope="module")
def study():
    return export.build_study()


def cells(option):
    return {c["id"]: c for f in option["model"]["buildings"][0]["floors"] for c in f["cells"] if c.get("tour_active")}


def test_existing_main_and_seven_comparisons_unchanged(study):
    assert study["protected_main_hashes"] == {p: export.shared.digest(export.ROOT / p) for p in export.PROTECTED}
    assert study["default_option"] == "b32-rear"
    assert [o["id"] for o in study["options"]] == ["b32-rear", "b32-front"]
    assert study["active_design"] == "baseline" and study["status"] == export.STATUS
    original = json.loads((export.OUT / "furniture-plans/layout.js").read_text().split(" = ", 1)[1].rstrip(";\n"))
    assert sum(len(f["rooms"]) for b in original["buildings"] for f in b["floors"]) == 112
    assert sum(len(r["furniture"]) for b in original["buildings"] for f in b["floors"] for r in f["rooms"]) == 128


@pytest.mark.parametrize("index", [0, 1])
def test_full_floors_32_land_ping_product_sizes_and_stairs(study, index):
    o = study["options"][index]
    assert o["frame_mm"] == [6000, 17630]
    assert 6000 * 17630 / 1e6 / (400 / 121) <= 32
    assert [f["base_mm"] for f in o["plans"]["floors"]] == [0, 4000, 7000, 10000]
    cores = []
    for f in o["plans"]["floors"]:
        assert sum(r["geometry"]["w_mm"] * r["geometry"]["h_mm"] for r in f["rooms"]) == 6000 * 17630
        for n, r in enumerate(f["rooms"]):
            assert not any(overlaps(export.shared.box(r["geometry"]), export.shared.box(t["geometry"])) for t in f["rooms"][n+1:])
            if r["kind"] == "stair":
                s = r["features"]["stair_geometry"]
                cores.append(r["features"]["stair_footprint_mm"])
                assert s["fits_reserved_box"] and s["flight_width_mm"] == 1000
                assert s["risers"] == (24 if f["id"] == "floor-1" else 18)
                assert s["middle_landing_mm"] >= 1000
                assert s["run_mm"] + s["middle_landing_mm"] + s["departure_offset_mm"] == cores[-1]["h_mm"]
                for door in r["features"]["doors"]:
                    if door["neighbor"] is not None and door["face"] in {"left", "right"}:
                        assert r["geometry"]["y_mm"] + r["geometry"]["h_mm"] * door["ratio"] + door["width_mm"]/2 <= cores[-1]["y_mm"] + s["departure_offset_mm"]
            for item in r["furniture"]:
                b, rot = item["placement"]["aabb"], item["placement"]["rotation_deg"] % 180
                assert b["maxX"] - b["minX"] == pytest.approx(item["depth_mm"] if rot else item["width_mm"])
                assert b["maxY"] - b["minY"] == pytest.approx(item["width_mm"] if rot else item["depth_mm"])
    assert len(cores) == 4 and all(c == cores[0] for c in cores)
    c = o["review"]["coordinate_screen"]
    assert c["fixed_body_failures"] == c["pending_solver_items"] == c["operation_limits"] == []
    assert not any(v["issue"] == "operation-vs-body" for v in c["operation_sharing"])
    assert c["full_human_door_sweeps"] == "unknown"


def test_shared_area_math_not_double_counting_or_overclaiming(study):
    for index, o in enumerate(study["options"]):
        p = o["review"]["program"]
        assert p["shrine_whole_room_discussion_sqm"] == 30.2104
        assert p["shrine_after_passage_reserve_sqm"] == (21.4384 if index == 0 else 19.0992)
        values = {r["id"]: r for r in p["area_checks"]}
        for rid, value in [("B.floor-1.bath_acc", 8.736), ("B.floor-1.palanquin", 10.8016),
                           ("B.floor-2.master_b", 20.0312), ("B.floor-2.master_bath", 6.2248), ("B.floor-2.bath_g", 5.02)]:
            assert values[rid]["discussion_inset_sqm"] == value
            assert values[rid]["finished_and_legal_area"] is None
        assert p["inset_sensitivity"][1]["master_sqm"] == 19.662
        assert p["inset_sensitivity"][1]["public_bath_sqm"] == 4.8412
        assert p["praying_people_and_capacity"].startswith("unknown")
        c = cells(o)
        assert c["B:floor-1:shrine"]["color"] == c["B:floor-1:shrine-front"]["color"]
        assert c["B:floor-1:bath1"]["color"] == c["B:floor-1:bath-extension"]["color"]


def test_rear_and_front_routes_do_not_leak_between_models(study):
    for index, o in enumerate(study["options"]):
        c = cells(o)
        storage = c["B:floor-1:storage"]
        external = [d for d in storage["tour_features"]["doors"] if d["neighbor"] is None]
        assert len(external) == (1 if index == 0 else 0)
        if external:
            assert external[0]["face"] == "rear" and external[0]["width_mm"] == 1960
        t = o["review"]["program"]["transport"]
        assert len(t["segments"]) == (2 if index == 0 else 6)
        assert t["storage_dimensions"] == {"width_mm": 1200, "depth_mm": 1700, "height_mm": 1800}
        assert t["assembled_measurement"]["status"] == t["route_rehearsal"]["status"] == "unknown"
        assert t["acceptance"] == "unknown" and t["outdoor_approach"] == "unknown-not-drawn"
        assert t["front_backup_in_rear_model"] == "not-claimed-use-separate-front-option"
        assert not any(part["includes_people_poles"] for part in t["segments"])
        assert all(part["body_sweep_mm"]["minY"] >= 3900 and part["body_sweep_mm"]["maxY"] <= 17630 for part in t["segments"])
        assert t["gate_budgets"][0]["discussion_clear_mm"] == (1800 if index == 0 else 1640)
        b = storage["furniture_placements"]["tour_mm"]["B:floor-1:storage:furniture:ceremonal"]["aabb"]
        assert [b["minX"], b["minY"]] == ([2680, 14550] if index == 0 else [4560, 15700])


def test_family_rules_cover_whole_l_shape_and_unknowns_remain(study):
    for o in study["options"]:
        p = o["review"]["program"]
        assert p["street_facing_axial_door"] and p["dry_altar_backing"]
        assert p["stair_or_hall_behind_altar"] == p["sleep_wet_stairs_above_whole_shrine"] == []
        assert set(o["review"]["professional_status"].values()) == {"unknown"}
        assert p["statutory_building_area"] is None and p["rear_access"] == "unknown"
        assert any("車位" in t for t in o["tradeoffs"]) and any("KTV" in t for t in o["tradeoffs"])
        assert any("IDF" in t for t in o["tradeoffs"])
        assert "guest-bath3" not in o["model"]["buildings"][0]["floors"][2]["layout_review"]["rooms"]


@pytest.mark.parametrize("defect", ["over32", "approval", "missing-evidence", "fake-alley", "thin-gate", "partitioned-shrine", "height"])
def test_settings_cannot_hide_missing_data_or_expand_site(defect):
    s = json.loads(export.SOURCE.read_text())
    if defect == "over32":
        s["frame_mm"][1] = 20530
    elif defect == "approval":
        s["professional_status"]["transport"] = "passed"
    elif defect == "missing-evidence":
        s["access_evidence"] = {}
    elif defect == "fake-alley":
        s["access_evidence"]["rear_route_exists"]["status"] = "verified"
    elif defect == "thin-gate":
        s["options"][0]["rear_gate_nominal_mm"] = 1800
    elif defect == "partitioned-shrine":
        s["floors"]["floor-1"]["connections"][0][2] = 900
    else:
        s["storey_heights_mm"][0] = 3000
    with pytest.raises(ValueError):
        export.validate_settings(s)


@pytest.mark.parametrize("mode", ["rear", "front"])
def test_route_rejects_geometry_that_only_has_an_entry_name(study, mode):
    o = copy.deepcopy(study["options"][0 if mode == "rear" else 1])
    b = o["model"]["buildings"][0]
    physical = export.load_physical_items(export.model3d.PHYSICAL_ITEMS_FILE)["by_id"]["B.palanquin.primary"]
    if mode == "rear":
        o["rear_gate_center_mm"] = 2500
    else:
        o["palanquin_body_origin_mm"] = [2800, 15700]
    with pytest.raises(ValueError, match="sweep"):
        export.transport(b, o, physical)


def test_family_screen_rejects_sleep_over_front_part(study):
    o = copy.deepcopy(study["options"][0])
    b = o["model"]["buildings"][0]
    front = next(c for c in b["floors"][1]["cells"] if c["key"] == "living2-front")
    front["kind"] = "bedroom"
    physical = export.load_physical_items(export.model3d.PHYSICAL_ITEMS_FILE)["by_id"]["B.palanquin.primary"]
    with pytest.raises(ValueError, match="shrine rules"):
        export.program_screen(b, o, physical)


def test_generated_html_svg_and_3d_are_same_source(study):
    src = (export.OUT / "b32-entry-options-3d.html").read_text()
    data = json.loads(re.search(r"^\s*var DATA = (.+);\s*$", src, re.M).group(1))["bc_options"]
    assert data["default_option"] == "b32-rear"
    assert 'htmlHref="b32-entry-options.html#"' in src
    assert "B32-only body translation annotation" in src
    for o in study["options"]:
        m = next(v["model"] for v in data["options"] if v["id"] == o["id"])
        assert m["bc_option"]["geometry_review"] == o["review"]
        for index, f in enumerate(o["plans"]["floors"]):
            active = {c["id"]: c for c in m["buildings"][0]["floors"][index]["cells"] if c.get("tour_active")}
            tree = ET.parse(export.OUT / "b32-entry-options" / f["plan_file"])
            assert tree.getroot().get("data-study-option") == o["id"]
            for r in f["rooms"]:
                assert active[r["id"]]["tour_mm"] == r["geometry"]
                assert active[r["id"]]["tour_features"] == r["features"]
                for i in r["furniture"]:
                    svg = tree.find('.//*[@data-furniture-id="' + i["id"] + '"]')
                    assert svg is not None and float(svg.get("data-width-mm")) == i["width_mm"]
                    assert float(svg.get("data-center-x-mm")) == i["placement"]["center_x_mm"]
        assert all(export.shared.digest(export.ROOT / p) == h for p, h in study["source_hashes"].items())


def test_display_revision_only_wraps_unchanged_source_vectors(study):
    assert study["revision"] == 1 and study["display_revision"] == 2
    page = export.render_index(study)
    assert page == (export.OUT / "b32-entry-options.html").read_text()
    assert 'data-display-revision="2"' in page
    assert page.count('data-plan-viewer=') == 2
    assert all(token not in page for token in ["__OPTIONS__", "__PLAN_VIEWER__", "__DISPLAY_REVISION__"])
    assert "scripts/templates/b32-plan-viewer.js" in study["source_hashes"]
    for option in study["options"]:
        viewer = export.render_plan_viewer(option)
        floor = option["plans"]["floors"][0]
        svg = ET.fromstring(export.render_svg(option, floor))
        _, _, width, height = map(float, svg.get("viewBox").split())
        assert f'data-source-width="{width:g}"' in viewer
        assert f'data-source-height="{height:g}"' in viewer
        readable = float(re.search(r'data-readable-width="(\d+)"', viewer).group(1))
        minimum = min(float(t.get("font-size")) for t in svg.iter("{" + export.NS + "}text") if t.get("font-size"))
        assert minimum * readable / width >= 14
        assert f'data="b32-entry-options/{floor["plan_file"]}"' in viewer
        assert f'id="{option["id"]}-viewport" role="region" tabindex="0"' in viewer
        for action in ["in", "out", "readable", "overview"]:
            assert f'data-plan-action="{action}"' in viewer
        for f in option["plans"]["floors"]:
            assert ET.tostring(ET.fromstring(export.render_svg(option, f))) == ET.tostring(
                ET.parse(export.OUT / "b32-entry-options" / f["plan_file"]).getroot()
            )  # Namespace aliases depend on other renderers in the same test process.


def test_generator_refuses_coordinate_findings(monkeypatch):
    monkeypatch.setattr(export.shared, "body_screen", lambda _: {"fixed_body_failures": ["fixture"], "pending_solver_items": [], "operation_limits": [], "operation_sharing": []})
    with pytest.raises(ValueError, match="coordinate defect"):
        export.build_study()

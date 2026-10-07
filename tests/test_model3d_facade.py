from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from xml.etree.ElementTree import fromstring

import export_model_3d as model3d
import pytest
from lib.dimension_overrides import load_overrides
from lib.model3d_facade import FACADE_FILE, boundary_segments, build_facade, decoration_issues
from lib.model3d_plan import plan_data, write_html_plans

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def payload():
    program = json.loads((ROOT / "structured/room_program.json").read_text(encoding="utf-8"))
    return model3d.build_payload(program, load_overrides(), "presentation")


def test_facade_is_non_mutating_and_not_a_second_floor_plan(payload):
    before = copy.deepcopy(payload["buildings"])
    rebuilt = build_facade(payload["buildings"], payload["standards"])
    assert payload["buildings"] == before
    assert rebuilt == payload["facade"]
    assert rebuilt["geometry_source"] == "tour_mm"
    assert rebuilt["status"] == "proposal-owner-and-architect-review-pending"
    assert len([f for b in before for f in b["floors"]]) == 12
    assert len([c for b in before for f in b["floors"] for c in f["cells"] if c.get("tour_active")]) == 105
    assert sum(len(c["furniture"]) for b in before for f in b["floors"] for c in f["cells"]) == 129
    assert all(c["compliance"] == "unknown" for b in rebuilt["buildings"] for c in b["components"])
    assert all(b["checks"]["compliance"] == "unknown" for b in rebuilt["buildings"])
    assert all(b["layout_review"]["parking"]["verified_spaces"] is None for b in before)


def test_actual_floor_levels_balcony_depths_and_roof_caps_are_preserved(payload):
    for building, facade in zip(payload["buildings"], payload["facade"]["buildings"], strict=True):
        for floor, level in zip(building["floors"], facade["floors"], strict=True):
            assert (level["base_mm"], level["height_mm"], level["width_mm"], level["depth_mm"]) == (
                floor["base_mm"],
                floor["height_mm"],
                floor["tour_width_mm"],
                floor["tour_depth_mm"],
            )
            if floor["index"] in (1, 2):
                assert level["front_balconies"][0]["geometry"]["h_mm"] == (1500 if building["id"] == "A" else 3900)
            for cap in [c for c in facade["components"] if c["floor"] == floor["id"] and c["role"] == "roof-cap"]:
                assert floor["is_roof"]
                cell = next(c for c in floor["cells"] if c["id"] == cap["source_room"])
                assert not cell["is_outdoor"]
                assert (cap["box_mm"]["w_mm"], cap["box_mm"]["d_mm"]) == (
                    cell["tour_mm"]["w_mm"],
                    cell["tour_mm"]["h_mm"],
                )
                assert cap["box_mm"]["z_mm"] == floor["base_mm"] + floor["height_mm"]


def test_boundary_union_removes_even_short_shared_faces():
    a = {"tour_mm": {"x_mm": 0, "y_mm": 0, "w_mm": 6000, "h_mm": 4000}}
    b = {"tour_mm": {"x_mm": 2000, "y_mm": -500, "w_mm": 3000, "h_mm": 500}}
    c = {"tour_mm": {"x_mm": 0, "y_mm": -500, "w_mm": 300, "h_mm": 500}}
    assert boundary_segments(a, [a, b, c], "front") == [(300, 2000), (5000, 6000)]
    assert boundary_segments(a, [a, b, c], "rear") == [(0, 6000)]


def test_exterior_openings_use_source_ratios_widths_and_heights_without_moving_them(payload):
    rooms = {c["id"]: (c, f) for b in payload["buildings"] for f in b["floors"] for c in f["cells"]}
    for facade in payload["facade"]["buildings"]:
        for opening in facade["openings"]:
            cell, floor = rooms[opening["room"]]
            g, f = cell["tour_mm"], cell["tour_features"]
            along_x = opening["face"] in {"front", "rear"}
            origin, length = (g["x_mm"], g["w_mm"]) if along_x else (g["y_mm"], g["h_mm"])
            if opening["kind"] == "window":
                assert opening["source"]["width_mm"] == cell["window_mm"]
                assert opening["source"]["ratio"] == f["window_ratio"]
                assert opening["bottom"] == f["window_sill_mm"]
                assert opening["top"] - opening["bottom"] == f["window_height_mm"]
            else:
                assert opening["source"] in f["doors" if opening["kind"] == "door" else "open_connections"]
            assert (opening["lo"] + opening["hi"]) / 2 == pytest.approx(origin + length * opening["source"]["ratio"])
            assert opening["hi"] - opening["lo"] == pytest.approx(opening["source"]["width_mm"])
            assert opening["rendered"] is (not opening["issues"])
            if opening["rendered"]:
                walls = [
                    c
                    for c in facade["components"]
                    if c["role"] == "wall" and c["source_room"] == cell["id"] and c["face"] == opening["face"]
                ]
                for wall in walls:
                    box = wall["box_mm"]
                    lo = box["x_mm" if along_x else "y_mm"]
                    hi = lo + box["w_mm" if along_x else "d_mm"]
                    z0, z1 = box["z_mm"], box["z_mm"] + box["h_mm"]
                    assert not (
                        lo < opening["hi"] - 1
                        and hi > opening["lo"] + 1
                        and z0 < floor["base_mm"] + opening["top"] - 1
                        and z1 > floor["base_mm"] + opening["bottom"] + 1
                    )


def test_bad_source_windows_remain_pending_not_clipped_or_reinvented(payload):
    pending = {o["id"]: o for b in payload["facade"]["buildings"] for o in b["openings"] if not o["rendered"]}
    assert "overlaps-source-door" in pending["A:floor-1:entry:front:window"]["issues"]
    assert "candidate-outside-source-wall" in pending["B:floor-1:shrine:front:window"]["issues"]
    assert pending["B:floor-1:shrine:front:window"]["source"]["width_mm"] == 2400
    c = payload["facade"]["buildings"][2]
    assert not any(o["id"] == "C:floor-1:living:front:window" for o in c["openings"])
    dining_window = next(o for o in c["openings"] if o["id"] == "C:floor-1:dining:front:window")
    assert dining_window["rendered"] and dining_window["source"]["width_mm"] == 2400
    assert not any(o["id"] == "C:floor-1:entrance:front:window" for o in c["openings"])
    for building in payload["facade"]["buildings"]:
        assert not any(c["module"] in pending and c["rendered"] for c in building["components"])


def test_guardrails_are_not_mistaken_for_obstructions_at_distant_balcony_doors(payload):
    for building in payload["facade"]["buildings"]:
        for fid in ("floor-2", "floor-3"):
            glass = [
                c
                for c in building["components"]
                if c["floor"] == fid and c["face"] == "front" and c["role"] == "rail-glass"
            ]
            assert glass and all(c["rendered"] for c in glass)
        assert not any(
            c["role"] in {"rail-glass", "rail-post", "gold-slat", "finish-return"}
            for c in building["components"]
            if c["floor"] == "floor-1"
        )


def test_reserved_bands_and_window_shading_are_not_marked_installed(payload):
    b = payload["buildings"][1]
    floor = b["floors"][1]
    facade = payload["facade"]["buildings"][1]
    slat = next(p for p in facade["pending"] if p["id"] == "B:floor-2:gold-slat-option")
    assert "window-projection" in slat["issues"]
    assert not any(c["module"] == slat["id"] and c["rendered"] for c in facade["components"])
    for building in payload["buildings"]:
        for floor in building["floors"]:
            for room in floor["cells"]:
                if room.get("tour_active") is False:
                    continue
                for zone in room["tour_features"]["reserved_mm"]:
                    if zone["kind"] not in {"care-route", "care-turn", "circulation", "door-approach", "hvac-service"}:
                        continue
                    a = zone["aabb"]
                    box = {
                        "x_mm": a["minX"],
                        "y_mm": a["minY"],
                        "z_mm": floor["base_mm"] + 100,
                        "w_mm": a["maxX"] - a["minX"],
                        "d_mm": a["maxY"] - a["minY"],
                        "h_mm": 900,
                    }
                    assert zone["kind"] in decoration_issues(box, floor, [])


def test_html_elevation_and_3d_share_every_component_and_material(payload, tmp_path):
    shared = plan_data(payload)
    assert shared["facade"] == payload["facade"]
    write_html_plans(payload, tmp_path)
    ns = {"s": "http://www.w3.org/2000/svg"}
    for building in shared["facade"]["buildings"]:
        root = fromstring((tmp_path / building["elevation_file"]).read_text(encoding="utf-8"))
        assert root.attrib["data-facade-id"] == payload["facade"]["id"]
        assert root.attrib["data-geometry-source"] == "tour_mm"
        rects = {r.attrib["data-component-id"]: r for r in root.findall("s:rect[@data-component-id]", ns)}
        assert set(rects) == {c["id"] for c in building["components"] if c["rendered"]}
        for c in building["components"]:
            assert all(math.isfinite(v) for v in c["box_mm"].values())
            if not c["rendered"]:
                continue
            rect = rects[c["id"]]
            for key, value in c["box_mm"].items():
                assert float(rect.attrib["data-" + key.replace("_", "-")]) == value
            assert rect.attrib["fill"] == shared["facade"]["palette"][c["material"]]["color"]


def test_facade_config_errors_fail_instead_of_fake_geometry(payload, tmp_path):
    data = json.loads(FACADE_FILE.read_text(encoding="utf-8"))
    file = tmp_path / "facade.json"
    data["assumptions_mm"]["slat_pitch"] = data["assumptions_mm"]["slat_width"]
    file.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="slat pitch"):
        build_facade(payload["buildings"], payload["standards"], file)
    data["geometry_source"] = "auto_mm"
    file.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="tour_mm"):
        build_facade(payload["buildings"], payload["standards"], file)

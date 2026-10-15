"""Isolated C1F comparison contracts; geometry is not professional approval."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import export_c1f_options as study_export
import pytest
from lib.model3d_placement import overlaps

ROOT = Path(__file__).resolve().parents[1]
NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.fixture(scope="module")
def study():
    return study_export.build_study()


def test_comparison_does_not_change_any_source_or_main_artifact(study):
    paths = [
        ROOT / "inputs/concept-layout-review.json",
        ROOT / "inputs/furniture-layout.json",
        ROOT / "inputs/requirements.json",
        ROOT / "structured/candidates/model3d.html",
        ROOT / "structured/candidates/furniture-plans/layout.js",
    ]
    before = [p.read_bytes() for p in paths]
    study_export.build_study()
    assert [p.read_bytes() for p in paths] == before
    assert study["active_design"] == "baseline" and study["status"] == "comparison-only-not-adopted"
    shared = json.loads(paths[-1].read_text().removeprefix("window.HOUSE_CONCEPT_LAYOUT = ").rstrip(";\n"))
    baseline = copy.deepcopy(study["options"][0]["floor"])
    baseline["plan_file"] = "C_floor-1.svg"
    frozen = study_export.model3d.build_payload(
        json.loads(study_export.model3d.PROGRAM_FILE.read_text()), study_export.load_overrides(), "presentation",
        review_path=ROOT / study["baseline_reference"])
    assert baseline == study_export.plan_data(frozen)["buildings"][2]["floors"][0]
    assert sum(len(f["rooms"]) for b in shared["buildings"] for f in b["floors"]) == 112
    assert sum(len(r["furniture"]) for b in shared["buildings"] for f in b["floors"] for r in f["rooms"]) == 127


def test_bounded_options_cover_same_frame_and_preserve_core_care_and_frontage(study):
    baseline = {r["key"]: r for r in study["options"][0]["floor"]["rooms"]}
    for option in study["options"]:
        floor = option["floor"]
        rooms = {r["key"]: r for r in floor["rooms"]}
        assert (floor["width_mm"], floor["depth_mm"]) == (6000, 17630)
        assert sum(r["geometry"]["w_mm"] * r["geometry"]["h_mm"] for r in rooms.values()) == 6000 * 17630
        for i, room in enumerate(floor["rooms"]):
            g = room["geometry"]
            a = {"minX": g["x_mm"], "maxX": g["x_mm"] + g["w_mm"], "minY": g["y_mm"], "maxY": g["y_mm"] + g["h_mm"]}
            for other in floor["rooms"][i + 1 :]:
                b = other["geometry"]
                assert not overlaps(
                    a,
                    {
                        "minX": b["x_mm"],
                        "maxX": b["x_mm"] + b["w_mm"],
                        "minY": b["y_mm"],
                        "maxY": b["y_mm"] + b["h_mm"],
                    },
                )
        for key in study_export.PRESERVED:
            for field in ("geometry", "name", "outdoor", "furniture"):
                assert rooms[key][field] == baseline[key][field], f"Changed preserved {key} {field} in {option['id']}"
        assert (
            rooms["stair1f"]["features"]["stair_footprint_mm"] == baseline["stair1f"]["features"]["stair_footprint_mm"]
        )
        assert any(
            z["kind"] == "care-turn" and z["aabb"]["maxX"] - z["aabb"]["minX"] == 1500
            for r in rooms.values()
            for z in r["features"]["reserved_mm"]
        )
        assert rooms["garage"]["outdoor"] and not rooms["garage"]["furniture"]
        assert option["public_bath_verified"] is option["daylight_verified"] is option["plumbing_verified"] is None
        assert option["model"]["buildings"][0]["layout_review"]["parking"]["verified_spaces"] is None


def test_public_routes_avoid_private_bedroom_only_in_comparisons(study):
    assert not study["options"][0]["route"]["avoids_elder_bedroom"]
    assert "elder" in study["options"][0]["route"]["room_keys"]
    for option in study["options"][1:]:
        assert option["route"]["avoids_elder_bedroom"]
        assert not set(option["route"]["room_keys"]) & {"elder", "elder-bath"}
        assert option["route"]["room_keys"][-1] == "public-bath"
        wc = next(r for r in option["floor"]["rooms"] if r["key"] == "public-bath")
        assert {i["catalog_id"] for i in wc["furniture"]} == {"toilet", "vanity-60"}
        assert len(wc["features"]["doors"]) == 1
        assert wc["features"]["doors"][0]["neighbor"] == "C:floor-1:entrance"
        assert wc["features"]["doors"][0]["operation"] == "sliding"
        assert not wc["features"]["access_pending"]


def test_normal_products_reserves_actual_window_changes_and_hvac_recomputed(study):
    catalog = json.loads((ROOT / "inputs/furniture-layout.json").read_text())["catalog"]
    for option in study["options"]:
        assert not option["unresolved_furniture"]
        for r in option["floor"]["rooms"]:
            for item in r["furniture"]:
                p = item["placement"]
                assert not p["issues"] and p["status"] == "planning-not-measured"
                for key in ("width_mm", "depth_mm", "height_mm"):
                    assert item[key] == catalog[item["catalog_id"]][key]
                for zone in r["features"]["reserved_mm"]:
                    assert not overlaps(p["aabb"], zone["aabb"])
        assert all(w["face"] in {"front", "rear"} for w in option["windows"])
        assert option["hvac"]["compliance"] == "unknown"
    assert [o["areas_sqm"]["public_bath"] for o in study["options"]] == [0, 4.4, 5.6]
    front = study["options"][2]
    assert next(w for w in front["windows"] if w["key"] == "living")["width_mm"] == 1200
    assert not any(w["key"] in {"dining", "public-bath"} for w in front["windows"])
    assert [o["hvac"]["estimated_routed_length_mm"] for o in study["options"]] == [14325, 14645, 10845]
    assert all(o["hvac"]["outdoor_room"] == "C:floor-2:balcony2f" for o in study["options"])
    for option in study["options"][1:]:
        upper = option["model"]["buildings"][0]["floors"][1:]
        for f, base in zip(upper, study["options"][0]["model"]["buildings"][0]["floors"][1:], strict=True):
            assert [(c["id"], c["tour_mm"], c["furniture"]) for c in f["cells"]] == [
                (c["id"], c["tour_mm"], c["furniture"]) for c in base["cells"]
            ]


def test_generated_comparison_svg_manifest_and_3d_are_identical_data(study):
    stored = json.loads(
        (ROOT / "structured/candidates/c1f-options/layout.js")
        .read_text()
        .removeprefix("window.HOUSE_C1F_OPTIONS = ")
        .rstrip(";\n")
    )
    assert stored == study_export.manifest(study)
    assert {
        "inputs/requirements.json",
        "scripts/config/residential_defaults_tw.json",
        "scripts/lib/model3d_functions.py",
        "scripts/lib/model3d_facade.py",
        "house_design/physical_items.py",
        "house_design/rendering/html_payload.py",
        "assets/vendor/three/three.min.js",
    } <= stored["source_hashes"].keys()
    for source, digest in stored["source_hashes"].items():
        assert hashlib.sha256((ROOT / source).read_bytes()).hexdigest() == digest
    html = (ROOT / "structured/candidates/c1f-options-3d.html").read_text()
    models = json.loads(re.search(r"var DATA = (\{.+?\});\n", html)[1])["c1f_options"]["options"]
    assert html.count('<canvas id="canvas"') == 1
    assert "__STUDY_" not in html and "__MODEL_DATA__" not in html
    for option, model in zip(study["options"], models, strict=True):
        for key in ("buildings", "layout_review", "facade", "furniture", "study_option"):
            assert option["model"][key] == model["model"][key]
        file = ROOT / "structured/candidates/c1f-options" / option["floor"]["plan_file"]
        assert file.read_text() == study_export.render_study_plan(option)
        tree = ET.parse(file)
        assert tree.getroot().attrib["data-study-status"] == "comparison-only-not-adopted"
        for room in option["floor"]["rooms"]:
            group = tree.find(f".//s:g[@data-room-id='{room['id']}']", NS)
            assert [float(group.attrib[k]) for k in ("data-x-mm", "data-y-mm", "data-w-mm", "data-h-mm")] == list(
                room["geometry"].values()
            )
            label = tree.find(f"s:g[@data-plan-labels='room-names']/s:a[@data-label-room-id='{room['id']}']", NS)
            assert label is not None and label.get("data-full-name") == room["name"]
            assert "c1f-options-3d.html?scheme=" + option["id"] in label.attrib["href"]
        for room in option["floor"]["rooms"]:
            for item in room["furniture"]:
                p = tree.find(f".//s:g[@data-furniture-id='{item['id']}']", NS)
                assert float(p.attrib["data-center-x-mm"]) == item["placement"]["center_x_mm"]
                assert float(p.attrib["data-center-y-mm"]) == item["placement"]["center_y_mm"]


@pytest.mark.parametrize("bad", ["adopted", "approved", "baseline-patch", "care-room", "route", "scope", "shrink"])
def test_invalid_scope_or_false_approval_is_rejected(bad):
    raw = json.loads(study_export.OPTIONS_FILE.read_text())
    if bad == "adopted":
        raw["active_design"] = "front-living"
    elif bad == "approved":
        raw["options"][1]["daylight_verified"] = True
    elif bad == "baseline-patch":
        raw["options"][0]["patch"] = {"entry": ["dining", "front", 900, 3400]}
    elif bad == "care-room":
        raw["options"][1]["patch"]["rooms"]["elder"] = {"rect": [0, 0, 10, 10]}
    elif bad == "route":
        raw["options"][1]["visitor_route"] = ["dining", "public-bath"]
    elif bad == "scope":
        raw["options"][1]["patch"]["frame_mm"] = [6000, 30000]
    elif bad == "shrink":
        raw["profiles"]["study-c-public-front"][0]["width_mm"] = 10
    with pytest.raises(ValueError):
        if bad == "shrink":
            # Profiles may never mutate a catalogue product's real envelope.
            study_export.build_study(raw)
            pytest.fail("dimension override was not rejected")
        else:
            study_export.build_study(raw)

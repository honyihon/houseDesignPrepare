"""File and local geometry tests only; never execute Three.js or a complete scene."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

from house_design.b_upper_replan import rect
from house_design.b_upper_storage_viewer import ARCHIVE, OUT, build, display_objects, surface
from house_design.contracts import ContractError
from scripts.export_b_upper_storage_viewer import render

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text())


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


@pytest.fixture(scope="module")
def files(report):
    return render(ROOT, report)


def test_b_all_versions_and_original_sources_remain_independent(report):
    source = read("structured/coordination/b-upper-storage-sync-v1/review.json")
    assert [f["source_floor"] for f in report["floors"]] == source["floors"]
    assert report["entry_options"] == source["entry_options"]
    assert report["known_limits"] == source["known_limits"]
    assert report["summary"] == {"floor_variants": 4, "states": 8, "storage_cases": 4, "ground_entry_options": 2, "ground_reference_states": 6}
    assert not report["main_3d_changed"] and not report["adopted"] and not report["accepted_viewers_changed"]
    assert report["professional_approval"] == "unknown" and report["protected_controls_unchanged"] == 149
    assert report["display_revision"] == 2


def test_source_surfaces_keep_true_polygons_and_stair_court_openings(report):
    for f in report["floors"]:
        shape = unary_union([Polygon(p["outer"], p["holes"]) for p in f["surface_polygons_mm"]])
        assert abs(shape.area-f["surface_area_mm2"]) < .1
        assert shape.symmetric_difference(surface(f["source_floor"])).area < .1
        for r in f["forbidden_rects_mm"]:
            assert shape.intersection(rect(r).buffer(-.2)).area < .1
    assert report["floors"][0]["surface_area_mm2"] < 105780000
    assert report["floors"][2]["surface_area_mm2"] < 105780000


def test_all_display_objects_preserve_source_inventory_and_height_provenance(report):
    for f in report["floors"]:
        for s in f["states"]:
            assert [i["source"] for i in s["display_objects"]] == s["objects"]
            for i in s["display_objects"]:
                if i["height_mm"] is None:
                    assert i["height_basis"] == "source-footprint-only" and i["height_reference"] is None
                elif i["source"].get("storage_case"):
                    assert i["height_mm"] == i["source"]["height_mm"]
                else:
                    assert i["height_reference"] and i["height_basis"] == "same-size-legacy-concept-envelope-not-measured"
    assert all(i["height_mm"] is None for f in report["floors"][2:] for s in f["states"] for i in s["display_objects"] if not i["source"].get("storage_case"))


def test_mismatched_legacy_size_is_not_a_height_reference(report):
    f = report["floors"][0]["source_floor"]
    state = f["states"][0]
    key = state["objects"][0]["key"]
    with pytest.raises(ContractError, match="size differs"):
        display_objects(f, state, {key: "wrong"}, {"wrong": {"width_mm": 9999, "depth_mm": 123, "height_mm": 900}})


def test_steps_middle_landings_and_floor_levels_are_source_bound(report):
    for f in report["floors"]:
        assert f["base_mm"] in [4000, 7000, 10000]
        source = f["source_floor"]["stair_interface"]
        assert {s["id"].split(":", 1)[1] for s in f["stairs"] if s["role"] == "incoming"} == {s["id"] for s in source["incoming_treads"]}
        assert len(f["stairs"]) == len(source["incoming_treads"])+len(source.get("outgoing_treads", []))
        assert all(s["height_mm"] > 0 for s in f["stairs"])
    assert len(report["floors"][2]["stairs"]) == 16
    assert len(report["floors"][0]["stairs"]) == 38


def test_source_report_build_does_not_mutate_existing_files(report):
    paths = ["structured/coordination/b-upper-storage-sync-v1/review.json", "structured/candidates/kaohsiung-house-options-3d.html",
        "structured/coordination/ac-storage-preview-v1/ac-storage-preview.zip", "structured/coordination/upper-floor-storage-viewer-v1/upper-floor-storage-3d.zip"]
    before = {p: (ROOT/p).read_bytes() for p in paths}
    assert build(ROOT) == report
    assert before == {p: (ROOT/p).read_bytes() for p in paths}


def test_eight_upper_plans_are_exact_and_six_ground_references_have_visible_names(report, files):
    for p in report["plans"]:
        assert files[p["file"]] == (ROOT/p["source"]).read_bytes()
    ground = [n for n in files if n.endswith("_floor-1.svg")]
    assert len(ground) == 6
    assert all(b"data-visible-equipment-legend" in files[n] for n in ground)


def test_offline_links_and_archive_are_complete(report, files):
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.refs = []

        def handle_starttag(self, tag, attrs):
            if tag not in {"a", "script"}:
                return
            self.refs += [v for k, v in attrs if k in {"src", "href"}]

    for name in ["index.html", "plans.html"]:
        parser = Links()
        parser.feed(files[name].decode())
        assert all(not urlsplit(p).scheme and urlsplit(p).path in files for p in parser.refs)
    with zipfile.ZipFile(io.BytesIO(files[ARCHIVE])) as z:
        assert len(z.namelist()) == len(files)-2
        assert all(z.read(n) == files[n] for n in z.namelist())
    assert files == render(ROOT, report)
    assert all((ROOT/OUT/n).read_bytes() == raw for n, raw in files.items())
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in report["source_hashes"].items())

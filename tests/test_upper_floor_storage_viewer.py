"""Source/copy checks only; do not initialize a 3D scene or browser."""
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import pytest

from house_design.upper_floor_storage_viewer import ARCHIVE, OUT, SOURCE, build
from scripts.export_upper_floor_storage_viewer import render

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_all_ten_3d_cases_match_the_nine_floor_storage_plan_source(report):
    original=json.loads((ROOT/SOURCE).read_text())
    assert report["case_count"]==10 and report["distinct_floors"]==9
    for case,old in zip(report["cases"],original["cases"],strict=True):
        for key in old:
            assert case[key]==old[key]
        assert case["storage_geometry"]=={k:old[k] for k in ["rect_mm","operation_mm","height_mm"]}
    assert report["primary_3d_changed"] is report["original_surrounding_furniture_heights_or_walls_invented"] is False
    assert report["protected_controls_unchanged"]==149 and not report["old_QA_reused"]


def test_B_L_shapes_and_each_roof_table_remain_exact(report):
    b=next(c for c in report["cases"] if c["id"]=="B-3F")
    ktv=next(r for r in b["rooms"] if r["id"]=="front-entertainment")
    assert len(ktv["polygon_mm"])>4
    roofs=[c for c in report["cases"] if c["id"].startswith("B-RF")]
    assert len(roofs)==2 and roofs[0]["rect_mm"]!=roofs[1]["rect_mm"]
    assert all(c["reuse_item"]=="folding-table" for c in roofs)


def test_offline_viewer_carries_matching_plans_scripts_license_and_no_network(report):
    files=render(ROOT,report)
    page=files["index.html"].decode()
    embedded=json.loads(re.search(r'<script id="storage-data" type="application/json">([\s\S]+?)</script>',page)[1])
    assert embedded==report
    assert '周邊房間、家具與設備只畫原平面投影' in page
    assert all(files[c["plan_file"]]==(ROOT/c["plan_source"]).read_bytes() for c in report["cases"])
    assert files["vendor/three.min.js"]==(ROOT/"assets/vendor/three/three.min.js").read_bytes()
    assert files["vendor/LICENSE"]==(ROOT/"assets/vendor/three/LICENSE").read_bytes()
    assert not re.search(r'(?:src|href)="(?:https?:|//)',page)
    with zipfile.ZipFile(io.BytesIO(files[ARCHIVE])) as z:
        archive=json.loads(files["archive-manifest.json"])
        assert sorted(z.namelist())==archive["archive_contains"]
        assert all(z.read(n)==files[n] for n in z.namelist())
        assert hashlib.sha256(files[ARCHIVE]).hexdigest()==archive["sha256"]
    assert all((ROOT/OUT/n).read_bytes()==v for n,v in files.items())


def test_browser_and_product_approval_remain_unverified(report):
    assert report["display_revision"] == 3
    assert report["rendered_qa"]=="not-run-owner-separate-terminal-required"
    assert report["professional_approval"]=="unknown" and not report["adopted"]
    assert report["browser_plugin"]=="absent"

"""Storage must add usable space without quietly consuming existing furniture/paths."""
import copy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from house_design.upper_floor_storage import build, check_storage
from scripts.export_upper_floor_storage import render

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_every_upper_floor_has_dedicated_storage_and_two_B_roof_controls(report):
    assert {(c["building"],c["floor"]) for c in report["cases"]} == {(b,f) for b in "ABC" for f in ["floor-2","floor-3","floor-4"]}
    assert report["case_count"] == 10 and report["protected_controls_unchanged"] == 149
    assert not report["primary_3d_changed"] and not report["original_wardrobes_furniture_room_outlines_and_hvac_changed"]
    assert all(not c["review"]["failures"] for c in report["cases"])
    assert all(c["review"]["footprint_sqm"] >= .4 for c in report["cases"])


def test_B_storage_avoids_KTV_and_backing_and_roof_reuses_own_table(report):
    for c in report["cases"]:
        if c["building"] != "B":
            continue
        if c["floor"] == "floor-4":
            assert c["reuse_item"] == "folding-table" and c["review"]["additional_floor_footprint_sqm"] == 0
        else:
            assert c["room"] == "quiet-living"


@pytest.mark.parametrize("defect",["body","operation","outside","old-operation"])
def test_new_body_and_operation_cannot_hide_existing_conflicts(report,defect):
    c=copy.deepcopy(next(c for c in report["cases"] if c["id"] == "A-2F"))
    if defect == "outside":
        c["rect_mm"][0]=-100
    else:
        old=next(i for r in c["rooms"] for i in r["items"] if i.get("operation_mm"))
        c["operation_mm" if defect == "operation" else "rect_mm"] = old["operation_mm" if defect == "old-operation" else "rect_mm"]
    assert check_storage(c["rooms"],c["fixed"],c["routes"],c)["failures"]


def test_new_plans_have_visible_item_names_not_only_numbers(report):
    files=render(report)
    for c in report["cases"]:
        root=ET.fromstring(files[c["id"]+".svg"])
        text="".join(n.text or "" for n in root.iter() if n.tag.endswith("text"))
        assert c["label"] in text and "現有家具／設備名稱對照" in text
        for room in c["rooms"]:
            for i in room["items"]:
                if i["id"] == c.get("reuse_item"):
                    continue
                assert i["label"] in text


def test_reusing_roof_table_cannot_grow_the_footprint(report):
    c=copy.deepcopy(next(c for c in report["cases"] if c["id"] == "B-RF-D1"))
    c["rect_mm"][2]+=100
    assert "reused-table-footprint-or-operation-changed" in check_storage(c["rooms"],c["fixed"],c["routes"],c)["failures"]

"""Source preservation and exact oriented cabinet insertion; no scene execution."""
import copy
import io
import json
import math
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from house_design.ac_storage_preview import ARCHIVE, OUT, assert_only_insertions, build
from house_design.contracts import ContractError, stable_hash
from scripts.export_ac_storage_preview import render

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_before_models_are_original_and_reversing_six_additions_recovers_the_complete_models(report):
    text = (ROOT/"structured/candidates/kaohsiung-house-options-3d.html").read_text()
    original = json.loads(re.search(r"^\s*var DATA = (.+);\s*$", text, re.M)[1])["kaohsiung_options"]
    assert report["summary"] == {"buildings": 2, "states": 4, "floors": 16, "storage_cases": 6, "new_cabinets": 6}
    assert report["display_revision"] == 3
    for option in report["options"]:
        before = next(s for s in option["states"] if s["id"] == "daily")["model"]
        source = next(o for o in original["options"] if o["id"] == option["id"])["states"][0]["model"]
        after = next(s for s in option["states"] if s["id"] == "storage")["model"]
        assert before == source
        specs = [c for c in report["cases"] if c["option"] == option["id"]]
        assert_only_insertions(before, after, specs)
    assert report["protected_controls_unchanged"] == 149
    assert not report["original_main_3d_changed"] and not report["accepted_storage_viewer_changed"]
    assert not report["adopted"]


def test_rotation_preserves_floor_plan_dimensions_and_the_operation_side(report):
    for option in report["options"]:
        model = next(s for s in option["states"] if s["id"] == "storage")["model"]
        cells = {c["id"]: c for f in model["buildings"][0]["floors"] for c in f["cells"]}
        for spec in [c for c in report["cases"] if c["option"] == option["id"]]:
            cell = cells[spec["host_room_id"]]
            item = next(i for i in cell["furniture"] if i["id"] == spec["proposed_item_id"])
            p = cell["furniture_placements"]["tour_mm"][item["id"]]
            radians = math.radians(p["rotation_deg"])
            w = abs(math.cos(radians))*item["width_mm"] + abs(math.sin(radians))*item["depth_mm"]
            d = abs(math.sin(radians))*item["width_mm"] + abs(math.cos(radians))*item["depth_mm"]
            assert w == pytest.approx(spec["rect_mm"][2]) and d == pytest.approx(spec["rect_mm"][3])
            assert item["height_mm"] == spec["height_mm"] and not p["issues"]
            if spec["case"] == "C-3F":
                assert item["width_mm"] == 1000 and item["depth_mm"] == 450
                assert p["operation_mm"]["maxX"] == p["aabb"]["minX"]
            else:
                assert p["operation_mm"]["minY"] == p["aabb"]["maxY"]


@pytest.mark.parametrize("defect", ["old-item", "old-stair", "new-height", "duplicate", "product-summary"])
def test_unrelated_or_duplicate_changes_cannot_be_blessed_as_storage_only(report, defect):
    option = report["options"][1]
    before = next(s for s in option["states"] if s["id"] == "daily")["model"]
    after = copy.deepcopy(next(s for s in option["states"] if s["id"] == "storage")["model"])
    specs = [c for c in report["cases"] if c["option"] == option["id"]]
    if defect == "old-stair":
        after["c_stair_merge"]["floor_bases_mm"]["floor-2"] += 1
    elif defect == "product-summary":
        after["furniture"]["physical_items"]["measured"] = 1
    else:
        cells = [c for f in after["buildings"][0]["floors"] for c in f["cells"]]
        if defect == "old-item":
            cell = next(c for c in cells if any(not i.get("storage_case") for i in c["furniture"]))
            next(i for i in cell["furniture"] if not i.get("storage_case"))["width_mm"] += 1
        else:
            cell = next(c for c in cells if any(i.get("storage_case") for i in c["furniture"]))
            item = next(i for i in cell["furniture"] if i.get("storage_case"))
            if defect == "new-height":
                item["height_mm"] += 1
            else:
                cell["furniture"].append(copy.deepcopy(item))
    with pytest.raises(ContractError):
        assert_only_insertions(before, after, specs)


def test_C_stair_hvac_and_one_washer_are_retained_in_both_states(report):
    option = report["options"][1]
    before, after = [next(s for s in option["states"] if s["id"] == name)["model"] for name in ["daily", "storage"]]
    assert before["c_stair_merge"] == after["c_stair_merge"]
    assert before["c_ac01_routing"] == after["c_ac01_routing"]
    for model in [before, after]:
        washers = [(f["id"], i) for f in model["buildings"][0]["floors"] for c in f["cells"]
            for i in c["furniture"] if i["catalog_id"] == "washer"]
        assert len(washers) == 1 and washers[0][0] == "floor-2"


def test_offline_archive_and_sixteen_state_specific_named_plans(report):
    files = render(ROOT, report)
    assert len(files) == 24
    assert len([n for n in files if n.endswith(".svg")]) == 16
    for option in report["options"]:
        for state in option["states"]:
            for floor in state["plans"]["floors"]:
                svg = ET.fromstring(files[floor["plan_file"]])
                assert any(n.get("data-visible-equipment-legend") for n in svg.iter())
                text = "".join(n.text or "" for n in svg.iter() if n.tag.endswith("text"))
                case = next((c for c in report["cases"] if c["option"] == option["id"] and c["floor"] == floor["id"]), None)
                if case:
                    assert (case["label"] in text) == (state["id"] == "storage")
    with zipfile.ZipFile(io.BytesIO(files[ARCHIVE])) as z:
        assert all(z.read(n) == files[n] for n in z.namelist())
    stored = json.loads(files["review.json"])
    assert stable_hash({k: v for k, v in stored.items() if k != "report_hash"}) == report["report_hash"]
    assert all((ROOT/OUT/n).read_bytes() == value for n, value in files.items())

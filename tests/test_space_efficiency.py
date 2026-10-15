"""Independent space allocation and preserved constraints, not professional QA."""
import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import export_model_3d as model
import pytest
from lib.dimension_overrides import load_overrides
from lib.model3d_plan import plan_data, render_plan, room_label
from lib.model3d_space_efficiency import attach_space_efficiency, comparison_source_review

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def payload():
    return model.build_payload(json.loads(model.PROGRAM_FILE.read_text()), load_overrides(), "presentation")


def test_real_area_transfer_without_frame_growth_or_fake_professional_status(payload):
    a = payload["layout_review"]["space_efficiency_review"]
    stats = next(f for f in a["floors"] if f["building"] == "A" and f["floor"] == "floor-2")
    assert stats["circulation_nominal_sqm"] == 20.52
    assert stats["baseline"]["circulation_nominal_sqm"] == 34.2
    assert stats["room_areas_sqm"]["A:floor-2:master"] == 19.68
    assert stats["room_areas_sqm"]["A:floor-2:bedroom2"] == 12.292
    assert stats["bedroom_nominal_sqm"] == 31.972
    assert stats["stairs_reserved_sqm"] == 8.64 and stats["stairs_footprint_sqm"] == 7.72
    assert stats["professional_acceptance"] == "unknown" and not a["heuristic_is_law"]
    assert len(a["floors"]) == 12


def test_preserved_first_roof_and_b_floors_and_real_ordinary_products(payload):
    before = json.loads((ROOT / "inputs/references/abc-before-space-efficiency-20261014.json").read_text())
    catalog = json.loads(model.FURNITURE_FILE.read_text())["catalog"]
    for b in payload["buildings"]:
        assert b["layout_review"]["core"] == before["buildings"][b["id"]]["core"]
        for f in b["floors"]:
            assert (f["tour_width_mm"], f["tour_depth_mm"]) == (6000, 17630)
            for c in f["cells"]:
                if not c.get("tour_active"):
                    continue
                if f["id"] in {"floor-1", "floor-4"} or b["id"] == "B":
                    assert list(c["tour_mm"].values()) == before["buildings"][b["id"]]["floors"][f["id"]]["rooms"][c["key"]]["rect"]
                for i in c["furniture"]:
                    if i["catalog_id"] == "ceremonial-storage":
                        continue  # dimensions are owned by the physical-item ledger
                    assert all(i[k] == catalog[i["catalog_id"]][k] for k in ["width_mm", "depth_mm", "height_mm"])
    a = payload["buildings"][0]["floors"][1]
    master = next(c for c in a["cells"] if c["key"] == "master")
    assert next(i for i in master["furniture"] if i["catalog_id"] == "wardrobe-180")["width_mm"] == 1800
    assert all(not p["issues"] for p in master["furniture_placements"]["tour_mm"].values())


def test_public_c_entrances_and_correct_room_use(payload):
    c = payload["buildings"][2]
    for f, key in [(c["floors"][1], "guestroom2f"), (c["floors"][2], "fitness3f")]:
        room = next(r for r in f["cells"] if r["key"] == key)
        assert any(d["neighbor"] == f"C:{f['id']}:front-hall" for d in room["tour_features"]["doors"])
        assert not any(d["neighbor"] == "C:floor-3:master3f" for d in room["tour_features"]["doors"])
    assert next(r for r in c["floors"][0]["cells"] if r["key"] == "elder")["kind"] == "bedroom"
    assert next(r for r in payload["buildings"][0]["floors"][1]["cells"] if r["key"] == "master-bath")["kind"] == "bath"
    assert next(r for r in payload["buildings"][1]["floors"][1]["cells"] if r["key"] == "master-bath2")["kind"] == "bath"
    b2 = next(f for f in payload["layout_review"]["space_efficiency_review"]["floors"]
              if f["building"] == "B" and f["floor"] == "floor-2")
    assert b2["bedroom_nominal_sqm"] == 11.49
    assert "B:floor-2:master-bath2" not in b2["bedroom_room_ids"]


def test_remaining_issues_not_hidden_and_old_comparisons_do_not_silently_adopt_v6(payload):
    s = payload["layout_review"]["space_efficiency_review"]
    assert s["b_priority"]["preferred"] == "b32-rear" and s["b_priority"]["fallback"] == "b32-front"
    assert next(f for f in s["floors"] if f["building"] == "A" and f["floor"] == "floor-3")["findings"]
    assert all(not f["findings"] for f in s["floors"] if f["roof"])
    prior, path = comparison_source_review()
    assert path.name == "abc-before-space-efficiency-20261014.json"
    assert prior["id"] == "abc-rationality-v5-minimal-fengshui"
    assert prior["buildings"]["A"]["floors"]["floor-2"]["rooms"]["master"]["rect"] == [0, 1500, 4560, 2500]
    assert plan_data(payload)["layout_review"]["space_efficiency_review"] == s


def test_followup_relocates_all_original_storage_and_activates_a_real_work_area(payload):
    rooms = {c["id"]: c for f in payload["buildings"][0]["floors"] for c in f["cells"] if c.get("tour_active")}
    audit = payload["layout_review"]["space_efficiency_review"]
    followup = audit["a_followup"]
    assert audit["revision"] == 2 and followup["wardrobe_capacity_mm"] == 5400
    assert followup["professional_acceptance"] == "unknown"
    assert not rooms["A:floor-2:hall2"]["furniture"]
    all_items = {i["id"]: i for c in rooms.values() for i in c["furniture"]}
    for relocation in followup["relocations"]:
        assert relocation["from"] not in all_items
        assert all_items[relocation["to"]]["relocated_from"] == relocation["from"]
        assert all_items[relocation["to"]]["catalog_id"] == relocation["catalog"]
    closet = rooms["A:floor-2:walkin"]
    assert len(closet["furniture"]) == 1
    assert closet["furniture"][0]["shared_operation_mode"] == "sequential-only-not-verified"
    assert closet["furniture"][0]["shared_operation_with"] == ["door-approach"]
    reading = rooms["A:floor-3:rear-common"]
    assert {i["catalog_id"] for i in reading["furniture"]} == {"desk-120", "shelf-180"}
    assert reading["space_role"] == "work-zone"
    assert not any(p["issues"] for p in reading["furniture_placements"]["tour_mm"].values())
    a3 = next(f for f in audit["floors"] if f["building"] == "A" and f["floor"] == "floor-3")
    assert a3["circulation_nominal_sqm"] == 25.468
    assert any(f["code"] == "large-circulation-allocation" for f in a3["findings"])
    assert rooms["A:floor-3:front-hall"]["tour_mm"]["w_mm"] == 1360
    assert rooms["A:floor-3:multi"]["tour_mm"]["w_mm"] == 2480
    assert not any(d["neighbor"] == reading["id"] for d in rooms["A:floor-3:back-hall"]["tour_features"]["doors"])


def test_svg_room_labels_are_bounded_and_keep_full_identity_outside_furniture_layer(payload):
    ns = {"s": "http://www.w3.org/2000/svg"}
    for b in plan_data(payload)["buildings"]:
        for f in b["floors"]:
            svg = ET.fromstring(render_plan(b["id"], f))
            labels = svg.find("s:g[@data-plan-labels='room-names']", ns)
            assert labels is not None and len(labels) == len(f["rooms"])
            for r, node in zip(f["rooms"], labels, strict=True):
                label = room_label(r)
                g = r["geometry"]
                assert node.get("data-label-room-id") == r["id"]
                assert node.get("data-full-name") == r["name"]
                assert label["x"] >= g["x_mm"] and label["y"] >= g["y_mm"]
                assert label["x"] + label["w"] <= g["x_mm"] + g["w_mm"]
                assert label["y"] + label["h"] <= g["y_mm"] + g["h_mm"]
                assert len(node.findall("s:text/s:tspan", ns)) == len(label["lines"])
                if r["id"] in {"A:floor-2:master", "A:floor-3:rear-common"}:
                    assert not label["overlap"]


@pytest.mark.parametrize("defect", ["shrink", "fake-reading", "hallway-storage", "false-approval", "move-wet-zone"])
def test_followup_cannot_hide_regressions_with_new_names(payload, defect):
    p = copy.deepcopy(payload)
    rooms = {c["key"]: c for f in p["buildings"][0]["floors"] for c in f["cells"] if c.get("tour_active")}
    if defect == "shrink":
        next(c for c in p["buildings"][0]["floors"][1]["cells"] if c["key"] == "master")["furniture"][1]["width_mm"] = 1200
    elif defect == "fake-reading":
        rooms["rear-common"]["furniture"] = []
    elif defect == "hallway-storage":
        rooms["hall2"]["furniture"] = [{"id": "invented"}]
    elif defect == "false-approval":
        p["layout_review"]["space_efficiency"]["a_followup"]["professional_acceptance"] = "passed"
    else:
        rooms["bath3"]["tour_mm"]["h_mm"] += 100
    with pytest.raises(ValueError):
        attach_space_efficiency(p["buildings"], p["layout_review"])


@pytest.mark.parametrize("defect", ["approval", "missing-contract", "stair", "frame", "first-floor", "bath-use", "ensuite-use"])
def test_bad_data_cannot_bypass_allocation_boundary(payload, defect):
    p = copy.deepcopy(payload)
    if defect == "approval":
        p["layout_review"]["space_efficiency"]["professional_acceptance"] = "passed"
    elif defect == "missing-contract":
        p["layout_review"].pop("space_efficiency")
    elif defect == "stair":
        p["buildings"][0]["layout_review"]["core"]["flight_width_mm"] = 800
    elif defect == "frame":
        p["buildings"][0]["floors"][1]["tour_depth_mm"] = 20000
    elif defect == "first-floor":
        next(c for c in p["buildings"][0]["floors"][0]["cells"] if c.get("tour_active"))["tour_mm"]["w_mm"] += 1
    elif defect == "bath-use":
        next(c for c in p["buildings"][0]["floors"][1]["cells"] if c["key"] == "master-bath")["kind"] = "bedroom"
    else:
        next(c for c in p["buildings"][1]["floors"][1]["cells"] if c["key"] == "master-bath2")["kind"] = "bedroom"
    with pytest.raises(ValueError):
        attach_space_efficiency(p["buildings"], p["layout_review"])

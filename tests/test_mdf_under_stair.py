from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

import export_model_3d as model3d
import pytest
from lib.dimension_overrides import load_overrides
from lib.model3d_mdf import SOURCE, build_mdf_study, render_mdf_section
from lib.model3d_placement import _candidate, _issues, overlaps
from lib.model3d_plan import plan_data, render_plan

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def payload():
    return model3d.build_payload(
        json.loads((ROOT / "structured/room_program.json").read_text()), load_overrides(), "presentation"
    )


def test_mdf_candidate_is_derived_from_actual_return_flight_and_never_installed(payload):
    before = deepcopy(payload["buildings"])
    s = build_mdf_study(payload["buildings"])
    assert s == payload["layout_review"]["mdf_study"]
    assert payload["buildings"] == before
    assert s["active_design"] == "side-backup" and s["preferred_option"] == "under-stair"
    assert s["candidate"]["body_mm"] == {"minX": 1330, "maxX": 1930, "minY": 6900, "maxY": 7500}
    assert s["candidate"]["service_mm"] == {"minX": 1030, "maxX": 2230, "minY": 6100, "maxY": 8100}
    assert s["candidate"]["rack_tread_top_min_mm"] == 3000
    assert s["candidate"]["service_tread_top_min_mm"] == 2500
    assert [r["return_flight_service_min_clear_mm"] for r in s["candidate"]["sensitivity"]] == [2300, 2200]
    assert all(
        not r["covers_full_service_width"] and not r["deduction_verified"] for r in s["candidate"]["sensitivity"]
    )
    assert set(s["candidate"]["issues"]) == {
        "side-maintenance-exceeds-return-flight",
        "maintenance-crosses-stair-room",
        "full-maintenance-headroom-not-demonstrated",
    }
    assert not s["candidate"]["installed"] and not s["candidate"]["counts_as_furniture"]
    assert not s["candidate"]["section_verified"] and s["evidence"] is None
    assert set(s["professional_status"].values()) == {"unknown"}
    assert payload["furniture"]["items"] == 128


def test_backup_repairs_both_side_clearances_without_reducing_care_or_adding_space(payload):
    cells = {c["key"]: c for c in payload["buildings"][0]["floors"][0]["cells"] if c.get("tour_active")}
    s = payload["layout_review"]["mdf_study"]
    assert cells["mdf"]["tour_mm"] == {"x_mm": 0, "y_mm": 9880, "w_mm": 1360, "h_mm": 2180}
    assert s["backup"]["reserved_area_sqm"] == 2.9648 and s["backup"]["released_area_sqm"] is None
    assert cells["rear-hall1"]["tour_mm"] == {"x_mm": 1360, "y_mm": 10000, "w_mm": 2160, "h_mm": 2060}
    turn = next(z["aabb"] for z in cells["rear-hall1"]["tour_features"]["reserved_mm"] if z["kind"] == "care-turn")
    assert turn == {"minX": 1940, "maxX": 3440, "minY": 10080, "maxY": 11580}
    assert cells["flex1"]["tour_mm"] == {"x_mm": 2400, "y_mm": 12060, "w_mm": 3600, "h_mm": 3770}
    assert cells["arcade"]["tour_mm"]["h_mm"] == 3900
    item = cells["mdf"]["furniture"][0]
    p = cells["mdf"]["furniture_placements"]["tour_mm"][item["id"]]
    assert len(p["side_operation_mm"]) == 2
    assert all(z["aabb"]["maxX"] - z["aabb"]["minX"] == 300 for z in p["side_operation_mm"])
    assert not p["issues"]
    assert s["reuse"]["released_area_sqm"] is None and not s["reuse"]["installed"]
    for zone in (s["reuse"]["body_mm"], s["reuse"]["operation_mm"]):
        assert not overlaps(zone, turn)
    current = json.loads((ROOT / "inputs/concept-layout-review.json").read_text())
    frozen = json.loads((ROOT / "inputs/references/abc-before-space-efficiency-20261014.json").read_text())
    for bid in ("B", "C"):
        for fid, floor in current["buildings"][bid]["floors"].items():
            old = frozen["buildings"][bid]["floors"][fid]
            expected = {k: r["rect"] for k, r in old["rooms"].items()}
            if bid == "C" and fid in {"floor-2", "floor-3"}:
                expected["living2f" if fid == "floor-2" else "master3f"] = [0, 3900, 6000, 4240]
                expected["front-hall"] = [0, 8140, 6000, 1360]
            assert {k: r["rect"] for k, r in floor["rooms"].items()} == expected
            if fid != "floor-1":
                normalized = deepcopy(floor)
                for key, profile in {
                    ("B", "floor-2"): {"living2": "review-b-fengshui-living"},
                    ("B", "floor-3"): {"guest3": "review-b-fengshui-guest"},
                    ("C", "floor-3"): {"master3f": "review-c-efficient-master"},
                }.get((bid, fid), {}).items():
                    # These furniture-only revisions are independent of MDF;
                    # every other room attribute and all floor connections stay frozen.
                    assert normalized["rooms"][key]["profile"] == profile
                    if "profile" in old["rooms"][key]:
                        normalized["rooms"][key]["profile"] = old["rooms"][key]["profile"]
                    else:
                        normalized["rooms"][key].pop("profile")
                if bid == "B" and fid == "floor-2":
                    assert normalized["rooms"]["master-bath2"]["kind"] == "bath"
                    normalized["rooms"]["master-bath2"].pop("kind")
                if bid == "C" and fid in {"floor-2", "floor-3"}:
                    living_key = "living2f" if fid == "floor-2" else "master3f"
                    other_key = "guestroom2f" if fid == "floor-2" else "fitness3f"
                    expected_connections = deepcopy(old["connections"])
                    expected_connections[0] = [living_key, "front-hall", 900, 5200]
                    expected_connections = [c for c in expected_connections if set(c[:2]) != {living_key, other_key}
                                            and set(c[:2]) != {"stair2f", other_key}]
                    expected_connections.append(["front-hall", other_key, 900, 1200])
                    if fid == "floor-2":
                        next(c for c in expected_connections if set(c[:2]) == {"living2f", "balcony2f"})[3] = 5200
                    assert normalized["connections"] == expected_connections
                    for key in (living_key, "front-hall"):
                        normalized["rooms"][key] = deepcopy(old["rooms"][key])
                    normalized["connections"] = deepcopy(old["connections"])
                    if fid == "floor-3":
                        assert normalized["rooms"]["terrace3f"]["kind"] == "outdoor"
                        normalized["rooms"]["terrace3f"].pop("kind")
                assert normalized == old


@pytest.mark.parametrize("angle,face", [(0, "rear"), (90, "right"), (180, "front"), (270, "left")])
def test_generic_side_maintenance_rotates_and_detects_obstacles(payload, angle, face):
    cell = next(c for c in payload["buildings"][0]["floors"][0]["cells"] if c["key"] == "mdf")
    item = deepcopy(cell["furniture"][0])
    p = _candidate(item, 2000, 2000, angle, face)
    room = {"x_mm": 0, "y_mm": 0, "w_mm": 4000, "h_mm": 4000}
    features = {"reserved_mm": [], "open_connections": [], "doors": [], "window_face": None}
    assert not _issues(item, p, room, features, [])
    for side in p["side_operation_mm"]:
        box = side["aabb"]
        assert min(box["maxX"] - box["minX"], box["maxY"] - box["minY"]) == 300
        blocked = deepcopy(features)
        blocked["reserved_mm"] = [{"kind": "care-route", "aabb": box}]
        assert "care-route" in _issues(item, p, room, blocked, [])
        other = {"aabb": box, "operation_mm": None}
        assert "operation-space" in _issues(item, p, room, features, [other])


@pytest.mark.parametrize(
    "mutation",
    [
        "adopt",
        "approved",
        "release",
        "install_reuse",
        "shrink_maintenance",
        "tiny_height",
        "fake_section",
        "body_outside",
        "reuse_turn",
        "extra_approval",
    ],
)
def test_mdf_refuses_unapproved_adoption_lost_clearances_or_unsafe_reuse(payload, mutation):
    raw = json.loads(SOURCE.read_text())
    if mutation == "adopt":
        raw["active_design"] = "under-stair"
    elif mutation == "approved":
        raw["professional_status"]["fire_and_escape"] = "passed"
    elif mutation == "release":
        raw["reuse"]["released_area_sqm"] = 2.9648
    elif mutation == "install_reuse":
        raw["reuse"]["installed"] = True
    elif mutation == "shrink_maintenance":
        raw["clearances_mm"]["left"] = 150
    elif mutation == "tiny_height":
        raw["maintenance_height_target_mm"] = 1000
    elif mutation == "fake_section":
        raw["evidence"] = {"verified": True}
    elif mutation == "body_outside":
        raw["return_flight_offset_mm"] = 4000
    elif mutation == "reuse_turn":
        raw["reuse"]["storage_rect_mm"] = [1940, 200, 1500, 1500]
    else:
        raw["verified"] = True
    with pytest.raises(ValueError, match="MDF"):
        build_mdf_study(payload["buildings"], raw)


@pytest.mark.parametrize("mutation", ["missing_sides", "clipped_sides", "narrow_backup", "rack_shrunk"])
def test_mdf_rejects_matched_but_falsified_backup_geometry(payload, mutation):
    buildings = deepcopy(payload["buildings"])
    cell = next(c for c in buildings[0]["floors"][0]["cells"] if c["key"] == "mdf")
    rack = cell["furniture"][0]
    p = cell["furniture_placements"]["tour_mm"][rack["id"]]
    if mutation == "missing_sides":
        p.pop("side_operation_mm")
    elif mutation == "clipped_sides":
        p["side_operation_mm"][0]["aabb"]["minX"] = 300
    elif mutation == "narrow_backup":
        cell["tour_mm"]["w_mm"] = 1100
    else:
        rack["height_mm"] = 500
    with pytest.raises(ValueError, match="MDF"):
        build_mdf_study(buildings)


def test_mdf_plan_section_and_viewer_share_sources_but_not_installed_furniture(payload):
    s = payload["layout_review"]["mdf_study"]
    floor = plan_data(payload)["buildings"][0]["floors"][0]
    plain = ET.fromstring(render_plan("A", floor))
    overlay = ET.fromstring(render_plan("A", floor, mdf_study=s))
    namespace = {"s": "http://www.w3.org/2000/svg"}
    assert len(plain.findall(".//s:g[@data-furniture-id]", namespace)) == len(
        overlay.findall(".//s:g[@data-furniture-id]", namespace)
    )
    assert len(overlay.findall(".//s:rect[@data-mdf-zone]", namespace)) == 4
    assert len(plain.findall(".//s:rect[@data-maintenance='left']", namespace)) == 1
    assert len(plain.findall(".//s:rect[@data-maintenance='right']", namespace)) == 1
    section = ET.fromstring(render_mdf_section(s))
    assert section.attrib["data-mdf-study"] == "conditional-not-installed"
    assert section.find(".//s:rect[@data-rack-height-mm='1000.0']", namespace) is not None
    assert "90cm" in ET.tostring(section, encoding="unicode")
    assert (ROOT / "structured/candidates/furniture-plans" / s["section_file"]).read_text() == render_mdf_section(s)

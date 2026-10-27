"""Cheap opening regressions; no scene runtime, browser or packing rebuild."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from lib.model3d_openings import is_shrine_room, review_window, set_window_request

ROOT = Path(__file__).resolve().parents[1]


def candidate(key="guest", name="後段客房（不在神明堂上方）", width=1200, wall=2400):
    return {"key": key, "name": name, "room_role": "bedroom", "is_outdoor": False,
            "window_mm": width, "tour_mm": {"x_mm": 0, "y_mm": 0, "w_mm": wall, "h_mm": 3000},
            "tour_features": {"window_face": "rear", "window_ratio": .5,
                              "window_sill_mm": 900, "window_height_mm": 1200,
                              "doors": [], "open_connections": []}}


def test_room_identity_not_explanatory_name_controls_solid_altar_backing():
    cell = candidate()
    assert not is_shrine_room(cell)
    assert review_window(cell, {"height_mm": 3000}, {"rear": [(0, 2400)]})["renderable"]
    shrine = candidate("shrine", "新名字不影響祭祀實牆")
    assert is_shrine_room(shrine)
    r = review_window(shrine, {"height_mm": 3000}, {"rear": [(0, 2400)]})
    assert r["status"] == "protected-solid-backing" and shrine["tour_features"]["window_face"] is None


@pytest.mark.parametrize("defect", ["oversize", "off-centre", "door", "open", "partial-exterior", "height"])
def test_invalid_windows_remain_traceable_not_clipped_or_counted(defect):
    cell = candidate()
    spans = {"rear": [(0, 2400)]}
    f = cell["tour_features"]
    if defect == "oversize":
        cell["window_mm"] = 3100
    elif defect == "off-centre":
        f["window_ratio"] = .15
    elif defect in {"door", "open"}:
        f["doors" if defect == "door" else "open_connections"] = [{"face": "rear", "width_mm": 900, "ratio": .5}]
    elif defect == "partial-exterior":
        spans = {"rear": [(0, 1400)]}
    else:
        f["window_sill_mm"] = 2500
    original = deepcopy(cell)
    r = review_window(cell, {"height_mm": 3000}, spans)
    assert not r["renderable"] and r["status"] == "invalid-candidate" and r["issues"]
    assert cell["window_mm"] == original["window_mm"]
    assert f["window_ratio"] == original["tour_features"]["window_ratio"]
    assert r["requested_width_mm"] == original["window_mm"]
    assert f["window_face"] is None and r["professional_acceptance"] == "unknown"


@pytest.mark.parametrize("defect", ["oversize", "off-centre", "door", "open", "partial-exterior", "height"])
def test_reassessment_keeps_intent_and_recovers_only_after_real_repair(defect):
    cell = candidate()
    f, spans = cell["tour_features"], {"rear": [(0, 2400)]}
    if defect == "oversize":
        cell["window_mm"] = 3100
    elif defect == "off-centre":
        f["window_ratio"] = .15
    elif defect in {"door", "open"}:
        f["doors" if defect == "door" else "open_connections"] = [{"face": "rear", "width_mm": 900, "ratio": .5}]
    elif defect == "partial-exterior":
        spans = {"rear": [(0, 1400)]}
    else:
        f["window_sill_mm"] = 2500
    first = review_window(cell, {"height_mm": 3000}, spans)
    assert first["status"] == "invalid-candidate" and f["window_face"] is None
    assert cell["window_request"] == {"face": "rear"}
    assert review_window(cell, {"height_mm": 3000}, spans) == first
    # Repair the actual source condition, not the cleared drawing field.
    cell["window_mm"] = 1200
    f.update(window_ratio=.5, window_sill_mm=900, doors=[], open_connections=[])
    repaired = review_window(cell, {"height_mm": 3000}, {"rear": [(0, 2400)]})
    assert repaired["renderable"] and repaired["requested_face"] == f["window_face"] == "rear"
    assert repaired["professional_acceptance"] == "unknown"


def test_cancel_and_redirect_replace_the_explicit_request_not_old_review():
    cell = candidate(width=3100)
    review_window(cell, {"height_mm": 3000}, {"rear": [(0, 2400)]})
    set_window_request(cell, None)
    cell["window_mm"] = 1200
    cancelled = review_window(cell, {"height_mm": 3000}, {"rear": [(0, 2400)]})
    assert not cancelled["renderable"] and cancelled["requested_face"] is None
    assert cell["tour_features"]["window_face"] is None
    set_window_request(cell, "front")
    assert "window_review" not in cell["tour_features"]
    redirected = review_window(cell, {"height_mm": 3000}, {"front": [(0, 2400)]})
    assert redirected["renderable"] and cell["tour_features"]["window_face"] == "front"


def test_zero_width_and_solid_shrine_backing_never_resurrect_a_window():
    cell = candidate()
    review_window(cell, {"height_mm": 3000}, {"rear": [(0, 2400)]})
    cell["window_mm"] = 0
    for _ in range(2):
        assert review_window(cell, {"height_mm": 3000}, {"rear": [(0, 2400)]})["status"] == "not-requested"
        assert cell["tour_features"]["window_face"] is None
    shrine = candidate("shrine")
    for _ in range(2):
        result = review_window(shrine, {"height_mm": 3000}, {"rear": [(0, 2400)]})
        assert result["status"] == "protected-solid-backing" and not result["renderable"]
        assert shrine["tour_features"]["window_face"] is None


def test_legacy_review_cannot_recover_a_missing_or_cancelled_request():
    cell = candidate()
    cell["tour_features"].update(window_face=None, window_review={"requested_face": "rear"})
    result = review_window(cell, {"height_mm": 3000}, {"rear": [(0, 2400)]})
    assert not result["renderable"] and result["requested_face"] is None
    assert cell["window_request"] == {"face": None}


def test_existing_plan_and_3d_consumers_use_effective_face_not_raw_request():
    # Source-contract checks only: no scene, WebGL or full renderer invocation.
    for name in ("scripts/lib/model3d_plan.py", "scripts/lib/model3d_facade.py", "scripts/templates/model3d.html"):
        source = (ROOT / name).read_text(encoding="utf-8")
        assert "window_face" in source and "window_request" not in source


def test_proposal_rebuild_respects_explicit_cancel_and_never_redirects_unavailable_face():
    from lib.model3d_review import proposal_features

    cell = candidate()
    cell.update(id="A:floor-1:guest", kind="bedroom", tour_active=True, review_spec={"window_face": "front"})
    floor = {"cells": [cell], "tour_width_mm": 2400, "tour_depth_mm": 6000,
        "height_mm": 3000, "layout_review": {"rooms": {"guest": {}}}}
    proposal_features(floor)
    assert cell["tour_features"]["window_face"] == "front"
    cell["review_spec"]["window_face"] = None
    proposal_features(floor)
    assert cell["window_request"] == {"face": None}
    assert cell["tour_features"]["window_face"] is None
    cell["review_spec"]["window_face"] = "rear"
    proposal_features(floor)
    result = cell["tour_features"]["window_review"]
    assert result["requested_face"] == "rear" and not result["renderable"]
    assert "not-fully-on-candidate-exterior" in result["issues"]
    assert cell["tour_features"]["window_face"] is None
    cell["review_spec"]["window_face"] = "front"
    proposal_features(floor)
    assert cell["tour_features"]["window_face"] == "front"


def load_plans(rel):
    return json.loads((ROOT / rel).read_text().split(" = ", 1)[1].rstrip(";\n"))


def test_main_current_openings_and_a3_maintenance_access_match_svg():
    data = load_plans("structured/candidates/furniture-plans/layout.js")
    rooms = {r["id"]: r for b in data["buildings"] for f in b["floors"] for r in f["rooms"]}
    assert len(rooms) == 112
    assert sum(len(r["furniture"]) for r in rooms.values()) == 128
    kitchen = rooms["C:floor-2:kitchen2f"]["features"]
    assert kitchen["window_face"] == "rear" and kitchen["window_mm"] == 1200
    assert kitchen["window_review"]["renderable"]
    for r in rooms.values():
        assert r["features"]["window_review"]["status"] != "invalid-candidate", r["id"]
    door = next(d for d in rooms["A:floor-3:entertainment"]["features"]["doors"] if d.get("purpose") == "ac-maintenance")
    assert door["neighbor"] == "A:floor-3:front-service" and door["width_mm"] == 900
    paired = next(d for d in rooms["A:floor-3:front-service"]["features"]["doors"] if d.get("purpose") == "ac-maintenance")
    assert paired["neighbor"] == "A:floor-3:entertainment"
    for bid, fid, key in [("C", "floor-2", "kitchen2f"), ("A", "floor-2", "master"), ("A", "floor-3", "guest")]:
        tree = ET.parse(ROOT / f"structured/candidates/furniture-plans/{bid}_{fid}.svg")
        group = tree.find(f'.//*[@data-room-id="{bid}:{fid}:{key}"]')
        assert group.get("data-window-status") == "candidate-geometry-only"
        assert group.findall('.//*[@stroke="#3b7894"]')


def test_b32_both_rear_guest_windows_survive_explanatory_names():
    data = load_plans("structured/candidates/b32-entry-options/layout.js")
    for option in data["options"]:
        guest = next(r for f in option["plans"]["floors"] for r in f["rooms"] if r["id"] == "B:floor-3:guest3")
        assert "神明堂" in guest["name"]
        assert guest["features"]["window_face"] == "rear"
        assert guest["features"]["window_mm"] == 2400
        tree = ET.parse(ROOT / "structured/candidates/b32-entry-options" / f"{option['id']}_floor-3.svg")
        group = tree.find('.//*[@data-room-id="B:floor-3:guest3"]')
        assert group.get("data-window-status") == "candidate-geometry-only"
        assert group.findall('.//*[@stroke="#3b7894"]')

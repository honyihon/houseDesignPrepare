"""Selected-C snapshot and plan merge only; no scene or browser runtime."""
from __future__ import annotations

import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import merge_c_stair_into_3d as export
import pytest

from house_design.c_balcony_coordination import _area, _overlap
from house_design.c_stair_merge import INDEX, REPORT, VIEWER, build, frozen_study
from house_design.contracts import ContractError, sha256_file
from house_design.frozen_kaohsiung import EXPECTED, historical_artifact

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def study():
    merged, original = build(ROOT)
    base, _ = frozen_study(ROOT)
    return merged, base, original


def state(study, oid="c-split"):
    return next(o for o in study["options"] if o["id"] == oid)["states"][0]


def test_other_options_and_all_C_furniture_are_preserved(study):
    merged, base, _ = study
    for a, b in zip(merged["options"], base["options"], strict=True):
        if a["id"] != "c-split":
            assert a == b
    before = {i["id"]: i for f in state(base)["model"]["buildings"][0]["floors"]
        for c in f["cells"] if c.get("tour_active") for i in c["furniture"]}
    after = {i["id"]: i for f in state(merged)["model"]["buildings"][0]["floors"]
        for c in f["cells"] if c.get("tour_active") for i in c["furniture"]}
    assert after == before and len(after) == 49
    assert merged["adopted"] is False and merged["rendered_qa"] == "not-run"


def test_floor_levels_treads_and_protected_room_geometries_match_detail(study):
    merged, base, _ = study
    current, previous = state(merged), state(base)
    assert [(f["base_mm"], f["height_mm"]) for f in current["plans"]["floors"]] == [
        (0, 4000), (4000, 3000), (7000, 3000), (10000, 3000)]
    for old, new in zip(previous["plans"]["floors"], current["plans"]["floors"], strict=True):
        assert {r["id"]: r["geometry"] for r in old["rooms"]} == {r["id"]: r["geometry"] for r in new["rooms"]}
    first = next(r for r in current["plans"]["floors"][0]["rooms"] if r["key"] == "stair1f")
    assert first["features"]["stair_geometry"]["risers"] == 24
    assert first["features"]["stair_geometry"]["tread_mm"] == 270
    assert first["features"]["stair_geometry"]["departure_offset_mm"] == 730


def test_second_floor_surface_union_does_not_cap_incoming_last_tread(study):
    merged, _, _ = study
    floor = state(merged)["plans"]["floors"][1]
    stair = next(r for r in floor["rooms"] if r["key"] == "stair2f")
    features = stair["features"]
    assert features["c_stair_full_floor_omitted"] is True
    platforms = [s for s in features["c_stair_surfaces"] if s["top_z_mm"] == 4000]
    for surface in platforms:
        assert _area(_overlap(surface["rect_mm"], [4720, 9760, 1200, 270])) == 0
    assert next(s for s in platforms if s["id"] == "floor-2:departure")["rect_mm"] == [3720, 9760, 1000, 270]
    assert next(s for s in platforms if s["id"] == "floor-2:shared-arrival")["rect_mm"] == [3720, 8760, 2200, 1000]
    first = next(r for r in state(merged)["plans"]["floors"][0]["rooms"] if r["key"] == "stair1f")
    floors = [s for s in first["features"]["c_stair_surfaces"] if s["top_z_mm"] == 0]
    for n, a in enumerate(floors):
        for b in floors[n+1:]:
            assert _area(_overlap(a["rect_mm"], b["rect_mm"])) == 0
    assert first["features"]["c_stair_context_arrival"]["rect_mm"] == [4920, 8760, 1000, 1000]


def test_raised_C_routes_recompute_all_copies_without_claiming_engineering(study):
    merged, _, _ = study
    model = state(merged)["model"]
    units = [u for f in model["buildings"][0]["floors"] for c in f["cells"] if c.get("tour_active")
        for u in c["tour_features"].get("hvac_units", [])]
    for uid in {u["id"] for u in units}:
        pair = [u for u in units if u["id"] == uid]
        assert len(pair) == 2 and pair[0]["route"] == pair[1]["route"]
        route = pair[0]["route"]
        assert route["compliance"] == "unknown" and route["model"] is None
        assert route["estimated_routed_length_mm"] == sum(sum(abs(a-b) for a, b in zip(p, q, strict=True))
            for p, q in zip(route["polyline_mm"], route["polyline_mm"][1:], strict=False))+route["bend_service_allowance_mm"]
    ac01 = next(u for u in units if u["id"] == "C-AC01")["route"]
    assert ac01["estimated_routed_length_mm"] == 15495
    assert ac01["elevation_difference_mm"] == 2150
    assert model["c_ac01_routing"]["baseline"]["estimated_routed_length_mm"] == 15735
    assert model["c_ac01_routing"]["candidate_low_arcade_segments"] == []


def test_old_boundary_portals_are_reciprocal_and_new_gate_is_separate(study):
    merged, _, _ = study
    floor = state(merged)["plans"]["floors"][0]
    rooms = {r["key"]: r for r in floor["rooms"]}
    stair = rooms["stair1f"]["features"]
    front = [o for o in stair["open_connections"] if o["face"] == "front"]
    assert sorted(o["width_mm"] for o in front) == [1100, 1920]
    assert not [d for d in stair["doors"] if d["face"] == "front"]
    assert stair["c_front_gate"]["plane_y_mm"] == 8550
    assert stair["c_front_gate"]["opening_width_nominal_mm"] == 1200


def test_live_files_and_plan_feature_metadata_match_model(study):
    merged, _, _ = study
    files = export.artifacts(ROOT)
    assert len(files) == 9
    for name, value in files.items():
        assert (ROOT/name).read_text() == value
    payload = json.loads(re.search(r"^\s*var DATA = (.+);\s*$", files[VIEWER], re.M)[1])["kaohsiung_options"]
    assert state(payload)["model"] == state(merged)["model"]
    for floor in state(merged)["plans"]["floors"]:
        svg = ET.fromstring(files["structured/candidates/kaohsiung-house-options/"+floor["plan_file"]])
        metadata = next(e for e in svg.iter() if e.get("data-c-stair-source-features") == "1")
        expected = {r["id"]: {k: v for k, v in r["features"].items() if k.startswith("c_")}
            for r in floor["rooms"] if any(k.startswith("c_") for k in r["features"])}
        assert json.loads(metadata.text) == expected
    report = json.loads(files[REPORT])
    assert report["rendered_qa"] == "not-run" and report["integration_revision"] == 2
    assert report["stair_display_revision"] == 2
    assert "C已整合：4m／24級／270mm踏面" in files[INDEX]
    assert "本頁3D維持原3.6m" not in files[INDEX]


def test_history_exceptions_are_exact_and_cannot_hide_unrelated_changes(monkeypatch):
    with pytest.raises(ContractError, match="No historical exception"):
        historical_artifact(ROOT, "inputs/requirements.json", "0"*64)
    import house_design.frozen_kaohsiung as history

    real = history.sha256_file
    monkeypatch.setattr(history, "sha256_file", lambda p: "0"*64 if p.name == "viewer.html.txt" else real(p))
    with pytest.raises(ContractError, match="Historical artifact bytes"):
        historical_artifact(ROOT, VIEWER, EXPECTED[VIEWER][1])


def test_archived_viewer_is_original_and_live_viewer_is_new(study):
    _, _, original = study
    assert sha256_file(ROOT/EXPECTED[VIEWER][0]) == EXPECTED[VIEWER][1]
    assert (ROOT/VIEWER).read_text() != original
    assert "csBuildParts(mesh,group,features);" in (ROOT/VIEWER).read_text()
    assert "csBuildParts(mesh,group,features);" not in original

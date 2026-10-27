"""Small geometry/serialization regressions only: no renderer or full pipeline."""
from __future__ import annotations

import copy
from collections import Counter
from xml.etree import ElementTree as ET

import export_b32_rear_right as export
import pytest

from house_design.b32_rear_right import body, cultural_screen, rect, review_state, variable_route
from house_design.b32_services import _hits
from house_design.contracts import ROOT, ContractError, read_json, sha256_file


@pytest.fixture(scope="module")
def study():
    return export.build_study()


def find(study, option, state="daily"):
    o = next(o for o in study["options"] if o["id"] == option)
    return next(s for s in o["states"] if s["id"] == state)


def rooms(state):
    return {r["key"]: r for r in state["plans"]["floors"][0]["rooms"]}


def test_scope_default_and_unknowns(study):
    assert study["default_option"] == "rear-alley" and study["default_state"] == "daily"
    assert study["status"] == "comparison-only-not-adopted" and study["rendered_qa"] == "not-run"
    assert study["revision"] == 1 and study["display_revision"] == 2
    assert [o["id"] for o in study["options"]] == ["rear-alley", "front-backup"]
    assert study["rear_alley"]["existence"] == "owner-reported-planning-premise"
    assert study["rear_alley"]["access_rights_and_opening_permission"] == "unknown"
    assert set(study["professional_status"].values()) == {"unknown"}
    assert "Browser plugin not available" in study["browser_path"]


def test_no_solver_scene_or_old_study_rebuild(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No scene runtime, packing solver or regeneration of older comparisons")
    monkeypatch.setattr(export.viewer, "build_payload", forbidden)
    monkeypatch.setattr(export.viewer, "attach_placements", forbidden)
    monkeypatch.setattr(export.interior, "build_study", forbidden)
    assert len(export.build_study()["options"]) == 2


def test_original_frame_partition_and_paired_html_model_states(study):
    for o in study["options"]:
        assert [s["id"] for s in o["states"]] == ["daily", "ritual", "carry"]
        for s in o["states"]:
            model = s["model"]
            assert len(model["buildings"]) == 1 and model["buildings"][0]["id"] == "B"
            assert model["bc_option"]["use_state"] == s["id"]
            assert model["bc_option"]["geometry_review"] == s["review"]
            for f, mf in zip(s["plans"]["floors"], model["buildings"][0]["floors"], strict=True):
                assert [f["width_mm"], f["depth_mm"]] == [6000, 17630]
                if f["id"] == "floor-1":
                    assert sum(rect(r)[2]*rect(r)[3] for r in f["rooms"]) == 6000*17630
                for index, r in enumerate(f["rooms"]):
                    assert not any(_hits(rect(r), rect(other)) for other in f["rooms"][index+1:])
                    c = next(c for c in mf["cells"] if c["id"] == r["id"])
                    assert c["tour_mm"] == r["geometry"] and c["tour_features"] == r["features"]
                    for item in r["furniture"]:
                        assert item["placement"] == c["furniture_placements"]["tour_mm"][item["id"]]
            first = rooms(s)
            assert rect(first["garage"]) == [0, 0, 6000, 3900]
            assert first["garage"]["outdoor"] and not first["garage"]["furniture"]
            assert rect(first["rear-bath"]) == [3330, 14500, 2670, 3130]
            assert rect(first["storage"]) == [0, 14500, 3330, 3130]


def test_goals_preserved_and_backup_explicitly_below_target(study):
    expected = {"rear-alley": [7.076, 10.7189, 5.005], "front-backup": [7.076, 11.3156, 4.277]}
    for o in study["options"]:
        rows = o["area_rows"]
        assert [a["original_minimum_sqm"] for a in rows] == [4.5, 9, 4]
        assert [a["original_target_sqm"] for a in rows] == [7, 10.5, 5]
        assert [a["sensitivity"][-1]["area_sqm"] for a in rows] == expected[o["id"]]
        assert rows[-1]["target_shortfall_at_115_sqm"] == (0 if o["id"] == "rear-alley" else .723)
        assert all(a["legal_area_and_functional_approval"] == "unknown" for a in rows)
        assert all(not r["outdoor"] for r in rooms(o["states"][0]).values() if r["key"].startswith("laundry-"))


def test_ritual_and_open_closed_public_bath_operations(study):
    for o in study["options"]:
        for s in o["states"]:
            for row in s["review"]["bath_route_sensitivity"]:
                for key in ("bath_entry_route", "bath_during_ritual", "basin_route", "toilet_side_route", "shower_route", "dry_cabinet_route", "local_laundry_700mm_route", "local_laundry_sink_700mm_route"):
                    assert row[key]["coordinate_failures"] == []
                assert row["bath_closed_door_route"]["coordinate_failures"]
                for key in ("turn_circle_failures", "bath_operation_failures", "laundry_operation_failures", "dry_door_swing_failures"):
                    assert row[key] == []
            assert s["review"]["bath_route_sensitivity"][-1]["door_clear_assumption_mm"] == 900
            assert s["review"]["bath_route_sensitivity"][-1]["public_corridor_clear_assumption_mm"] == (1450 if o["id"] == "rear-alley" else 1020)
        seats = rooms(find(study, o["id"], "ritual"))["shrine"]["features"]["fixed_reserved_mm"]
        assert len([r for r in seats if r["kind"] == "b-separate-seated-operation"]) == 2


def test_window_and_independent_rear_gate(study):
    for o in study["options"]:
        for s in o["states"]:
            first = rooms(s)
            window = first["rear-bath"]["features"]
            assert window["window_review"]["renderable"]
            assert (window["window_face"], window["window_mm"], window["window_sill_mm"], window["window_height_mm"]) == ("rear", 900, 1500, 600)
            assert 3330+2670*window["window_ratio"] == pytest.approx(4050)
            assert window["window_review"]["professional_acceptance"] == "unknown"
            gates = [d for d in first["storage"]["features"]["doors"] if d["neighbor"] is None]
            assert len(gates) == (1 if o["id"] == "rear-alley" else 0)
            if gates:
                assert gates[0]["face"] == "rear" and gates[0]["width_mm"] == 1960
                assert gates[0]["ratio"]*3330 == pytest.approx(1150)
            assert s["review"]["no_rear_alley_does_not_establish_rear_window_rights"] is True


def test_front_actual_staging_not_hidden_furniture_or_borrowed_rear_pass(study):
    for o in study["options"]:
        counts = [Counter((i["id"], i["width_mm"], i["depth_mm"], i["height_mm"]) for r in rooms(s).values() for i in r["furniture"]) for s in o["states"]]
        assert counts[0] == counts[1] == counts[2]
        carry = o["states"][2]["review"]
        assert not carry["carry_stored_body_115mm"]["coordinate_failures"]
        assert carry["minimum_carry_aperture_assumption_115mm"] == (1730 if o["id"] == "rear-alley" else 1500)
        assert carry["original_continuous_transport_target_mm"] == 1500
        assert carry["transport_aperture_shortfall_mm"] == 0
        assert carry["whole_carry"].startswith("unknown")
    for state in ("daily", "ritual"):
        assert find(study, "front-backup", state)["review"]["carry_stored_body_115mm"]["coordinate_failures"]
    carry = find(study, "front-backup", "carry")
    first = rooms(carry)
    assert len([i for i in first["storage"]["furniture"] if i["id"].rsplit(":", 1)[-1].startswith("bench-")]) == 2
    assert body(next(i for i in first["shrine-front"]["furniture"] if i["id"].endswith(":offering"))) == [4685, 4015, 1200, 500]
    rotations = carry["review"]["carry_stored_body_115mm"]["rotations"]
    assert len(rotations) == 2 and all(r["full_rotation_envelope_mm"][2:] == [2081, 2081] for r in rotations)
    assert [r["center_mm"] for r in rotations] == [[3600, 6550], [1200, 10320]]
    assert carry["review"]["continuous_1500mm_conservative_envelope_review"]["coordinate_failures"]
    assert len([r for r in first["shrine-front"]["features"]["reserved_mm"] if r["kind"].startswith("b-separate-body-rotation-")]) == 2
    o = study["options"][1]
    assert o["staging_review"]["coordinate_failures"] == []
    assert [r["item_id"].rsplit(":", 1)[-1] for r in o["staging_review"]["sequence"]] == ["bench-2", "bench-1", "offering"]


def test_rotation_requires_continuity_and_full_sweep_not_just_endpoints():
    segments = [{"yaw_deg": 0, "points_mm": [[2000, 1800], [2000, 2000]]},
                {"yaw_deg": 90, "points_mm": [[2000, 2000], [2000, 2200]]}]
    rotations = [{"center_mm": [2000, 2000], "from_yaw_deg": 0, "to_yaw_deg": 90}]
    with pytest.raises(ContractError, match="explicit rotation"):
        variable_route(segments, [], [[0, 0, 5000, 5000]], [], 0, [1200, 1700])
    result = variable_route(segments, rotations, [[0, 0, 5000, 5000]], [{"id": "mid-turn-only-obstacle", "rect_mm": [2950, 1980, 40, 40]}], 0, [1200, 1700])
    assert all(not r["coordinate_failures"] for r in result["segments"])
    assert result["rotations"][0]["coordinate_failures"] == ["hits-mid-turn-only-obstacle"]
    shifted = copy.deepcopy(segments)
    shifted[1]["points_mm"][0] = [2000, 2001]
    with pytest.raises(ContractError, match="same actual center"):
        variable_route(shifted, rotations, [[0, 0, 5000, 5000]], [], 0, [1200, 1700])


def test_real_paired_opening_mutation_cannot_inherit_pass(study):
    cfg = read_json(ROOT / export.SOURCE)
    plans = copy.deepcopy(find(study, "front-backup", "carry")["plans"])
    bath = next(r for r in plans["floors"][0]["rooms"] if r["key"] == "rear-bath")
    door = next(d for d in bath["features"]["doors"] if d["neighbor"] == "B:floor-1:bath-approach")
    door["width_mm"] = 900
    with pytest.raises(ContractError, match="actual|Actual"):
        review_state(plans, cfg, cfg["options"][1], "carry")


def test_staging_wrong_target_and_altar_backing_fail_closed(study):
    daily = find(study, "front-backup")["plans"]
    carry = copy.deepcopy(find(study, "front-backup", "carry")["plans"])
    bench = next(i for r in carry["floors"][0]["rooms"] for i in r["furniture"] if i["id"].endswith(":bench-1"))
    bench["placement"]["aabb"]["minX"] += 50
    with pytest.raises(ContractError, match="actual full-size"):
        export.staging_review(daily, carry)
    plans = copy.deepcopy(daily)
    backing = next(r for r in plans["floors"][0]["rooms"] if r["key"] == "altar-backing")
    backing["kind"] = "bath"
    with pytest.raises(ContractError, match="dry backing"):
        cultural_screen(plans)


def test_reject_automatic_approval_and_wrong_default():
    for change in ("rights", "default", "adopt"):
        cfg = read_json(ROOT / export.SOURCE)
        if change == "rights":
            cfg["rear_alley"]["access_rights_and_opening_permission"] = "verified"
        elif change == "default":
            cfg["default_option"] = "front-backup"
        else:
            cfg["status"] = "adopted"
        with pytest.raises(ContractError):
            export.validate_config(cfg)


def test_cultural_projection_and_no_side_window_assumptions(study):
    for o in study["options"]:
        review = o["cultural_coordinate_review"]
        assert review["street_axis_x_mm"] == review["altar_center_x_mm"] == 3400
        assert review["shrine_upper_bed_wet_stair_overlaps"] == []
        assert review["backing_finish_margin_deficit_at_115mm"] == 35
        assert review["compass_beams_plumbing_noise_and_family_acceptance"] == "unknown"
        assert o["mechanical_brief"]["status"] == "concept-only-no-engineered-duct-or-capacity"
        assert "武轎庫" in o["mechanical_brief"]["laundry"]


def test_original_upper_floors_and_primary_abc_preserved(study):
    source = export.interior.read_model(ROOT / "structured/candidates/b32-entry-options-3d.html")
    for o in study["options"]:
        base = export.interior._select(source, "b32-rear" if o["id"] == "rear-alley" else "b32-front", "B")
        originals = export.plan_data(base)["buildings"][0]["floors"]
        for s in o["states"]:
            for old, new in zip(originals[1:], s["plans"]["floors"][1:], strict=True):
                assert [(r["id"], r["geometry"], r["furniture"]) for r in old["rooms"]] == [(r["id"], r["geometry"], r["furniture"]) for r in new["rooms"]]
    assert len(read_json(ROOT / "structured/candidates/interior-improvements/review.json")["options"]) == 10


def test_sources_match_and_output_svgs_are_bounded(study):
    for path, digest in study["source_hashes"].items():
        assert sha256_file(ROOT / path) == digest
    for o in study["options"]:
        for s in o["states"]:
            for f in s["plans"]["floors"]:
                svg = ET.parse(ROOT / export.OUT / f["plan_file"]).getroot()
                assert (svg.get("width"), svg.get("height")) == ("660", "1903")
                assert svg.get("data-study-option") == o["id"] and svg.get("data-use-state") == s["id"]
                if f["id"] == "floor-1":
                    assert any(n.get("data-b32-route") for n in svg.iter())


def test_new_writer_does_not_touch_other_outputs(study, tmp_path):
    # Output-only writer needs only fixed, read-only renderer assets/templates.
    # Test its actual paths in a clean directory; never rerender old viewers.
    for p in ("scripts/templates", "assets/vendor/three"):
        (tmp_path / p).mkdir(parents=True, exist_ok=True)
    for p in (export.BOOTSTRAP, export.DISPLAY, "scripts/templates/bc-options-controls.html"):
        (tmp_path / p).write_text((ROOT / p).read_text())
    export.write_study(study, tmp_path)
    written = [str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file() and not str(p.relative_to(tmp_path)).startswith("scripts/")]
    assert len(written) == 27
    assert all(p.startswith(export.OUT) for p in written)

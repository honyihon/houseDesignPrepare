"""Small, sequential snapshot/geometry checks; no scene runtime or browser."""
from __future__ import annotations

import copy
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

import export_current_design_basis as export
import pytest
from historical_support import assert_historical_sources, historical_study

from house_design.b32_rear_right import body, rect
from house_design.b32_service_detail import _inside
from house_design.contracts import ROOT, ContractError, read_json, stable_hash
from house_design.current_design_basis import engineering_review, requirement_ledger, validate_config


@pytest.fixture(scope="module")
def study():
    return historical_study("current-design-basis")


def option(study, oid):
    return next(o for o in study["options"] if o["id"] == oid)


def rooms(state, index):
    return {r["key"]: r for r in state["plans"]["floors"][index]["rooms"]}


def source_option(oid):
    path = "structured/candidates/b32-rear-right/review.json" if oid in {"rear-alley", "front-backup"} else "structured/candidates/interior-improvements/review.json"
    return next(o for o in read_json(ROOT / path)["options"] if o["id"] == oid)


def test_current_scope_and_no_automatic_adoption(study):
    assert study["default_option"] == "b-rear-refined"
    assert len(study["options"]) == 5 and sum(len(o["states"]) for o in study["options"]) == 9
    assert study["adopted"] is False and study["rendered_qa"] == "not-run"
    assert study["revision"] == 1 and study["display_revision"] == 2
    assert export.CAMERA in study["source_hashes"]
    assert set(study["professional_status"].values()) == {"unknown"}
    ledger = study["requirement_ledger"]
    assert ledger["canonical_requirements"] == 66 and ledger["scenario_rows"] == 112
    assert ledger["verified_requirements"] == 0
    for scenario in ledger["scenarios"]:
        assert all(row["functional_acceptance"] == row["professional_acceptance"] == "unknown" for row in scenario["rows"])
        assert all(row["area"]["additive_across_requirements"] is False for row in scenario["rows"])
        assert not any(row["missing_room_ids"] for row in scenario["rows"]+scenario["supplementary"])


def test_index_first_warning_is_explicit_unique_and_not_in_closed_details(study):
    class Warnings(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows, self.current = [], None

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag == "p" and "warning" in values.get("class", "").split():
                self.current = {"attrs": values, "text": ""}
                self.rows.append(self.current)

        def handle_data(self, data):
            if self.current is not None:
                self.current["text"] += data

        def handle_endtag(self, tag):
            if tag == "p":
                self.current = None

    source = export.render_index(study)
    parser = Warnings()
    parser.feed(source)
    first = parser.rows[0]
    assert first["attrs"]["id"] == "basis-adoption-warning"
    assert first["text"].startswith("比較方案，未採用／專業未核。")
    assert source.count('id="basis-adoption-warning"') == 1
    assert source.index('id="basis-adoption-warning"') < source.index("<details")


def test_no_full_rebuild_solver_or_scene(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No full build/renderer/solver allowed")
    monkeypatch.setattr(export.viewer, "build_payload", forbidden)
    monkeypatch.setattr(export.viewer, "attach_placements", forbidden)
    monkeypatch.setattr(export.interior, "build_study", forbidden)
    with pytest.raises(ContractError, match="[Ss]tale"):
        export.build_study()


def test_b_upper_full_size_furniture_and_first_floor_preserved(study):
    for oid, oldid in (("b-rear-refined", "rear-alley"), ("b-front-refined", "front-backup")):
        current, old = option(study, oid), source_option(oldid)
        assert [s["id"] for s in current["states"]] == ["daily", "ritual", "carry"]
        for state, previous in zip(current["states"], old["states"], strict=True):
            assert state["plans"]["floors"][0]["rooms"] == previous["plans"]["floors"][0]["rooms"]
            for index in range(4):
                now_rooms, old_rooms = rooms(state, index), rooms(previous, index)
                assert {k: r["geometry"] for k, r in now_rooms.items()} == {k: r["geometry"] for k, r in old_rooms.items()}
                for key, room in now_rooms.items():
                    previous_room = old_rooms[key]
                    assert room["features"]["doors"] == previous_room["features"]["doors"]
                    for field in ("window_mm", "window_ratio", "window_face", "window_sill_mm", "window_height_mm"):
                        assert room["features"].get(field) == previous_room["features"].get(field)
                    def products(r):
                        return Counter((i["catalog_id"], i["width_mm"], i["depth_mm"], i["height_mm"]) for i in r["furniture"])
                    assert products(room) == products(previous_room)
                    if index in {0, 3}:
                        assert [body(i) for i in room["furniture"]] == [body(i) for i in previous_room["furniture"]]
            assert not state["review"]["operation_vs_fixed_body"]
            assert state["review"]["detail"]["before_upper_body_flags"] > 0
            assert {r["room"] for r in state["review"]["furniture_body_sensitivity"]} == {"B:floor-1:shrine"}
            assert state["review"]["detail"]["cultural"]["shrine_upper_bed_wet_stair_overlaps"] == []
            if state["id"] == "carry":
                assert not state["review"]["detail"]["transport"]["carry_stored_body_115mm"]["coordinate_failures"]
                if oid == "b-front-refined":
                    assert state["review"]["detail"]["transport"]["continuous_1500mm_conservative_envelope_review"]["coordinate_failures"]


def test_care_and_transport_not_implied_by_furniture_adjustments(study):
    for oid in ("b-rear-refined", "b-front-refined"):
        for s in option(study, oid)["states"]:
            t = s["review"]["detail"]["transport"]
            assert t["whole_carry"].startswith("unknown-")
            assert t["original_continuous_transport_target_mm"] == 1500
            assert t["no_rear_alley_does_not_establish_rear_window_rights"] is True
            assert t["care_rescue_door_hardware_and_window_rights"] == "unknown"


def test_c_care_door_budget_shortfall_remains_visible(study):
    scenario = next(s for s in study["requirement_ledger"]["scenarios"] if s["id"] == "c-care-refined")
    elder = next(r for r in scenario["rows"] if r["requirement_id"] == "C.floor-1.elder")
    entrance = next(d for d in elder["door_budget_checks"] if d["neighbor"] == "C:floor-1:stair1f")
    assert entrance["nominal_mm"] == 1000 and entrance["clear_assumption_at_115mm"] == 770
    assert entrance["original_required_clear_mm"] == 900 and entrance["shortfall_at_115mm"] == 130
    assert "door-clear-budget-below-original-target" in elder["flags"]
    assert entrance["actual_product_finished_clear_and_rescue"] == "unknown"


def test_a_suite_is_real_additional_bath_and_keeps_public_and_rear_window(study):
    state = option(study, "a-ensuite")["states"][0]
    second = rooms(state, 1)
    assert second["ensuite-study"]["requirement_id"] == "A.floor-2.master_bath"
    assert second["master-bath"]["requirement_id"] == "A.floor-2.bath2"
    assert second["ensuite-study"]["features"]["window_mm"] == 0
    assert rooms(state, 2)["bath3"]["features"]["window_review"]["renderable"]
    assert second["master"]["features"]["window_review"]["renderable"]
    original = source_option("a-upper-wet-core")["plans"]["floors"][1]
    old_master = next(r for r in original["rooms"] if r["key"] == "master")
    new_master = second["master"]
    old_center = rect(old_master)[0]+rect(old_master)[2]*old_master["features"]["window_ratio"]
    new_center = rect(new_master)[0]+rect(new_master)[2]*new_master["features"]["window_ratio"]
    assert old_center == pytest.approx(new_center, abs=.01)
    assert old_master["features"]["window_mm"] == new_master["features"]["window_mm"]
    door = second["ensuite-study"]["features"]["doors"]
    assert len(door) == 1 and door[0]["neighbor"] == "A:floor-2:master"
    assert state["review"]["detail"]["local_open_door_700mm_body_route"]["coordinate_failures"] == []
    assert state["review"]["detail"]["local_closed_door_route"]["coordinate_failures"]
    assert second["master-front"]["kind"] == "other"
    assert not second["master-front"]["features"]["hvac_units"]  # One room must not acquire two AC proposals.
    assert all(i.get("physical_item_id") is None for i in second["ensuite-study"]["furniture"])
    assert all(i["id"].startswith(second["study"]["id"]+":furniture:") for i in second["study"]["furniture"])


def test_a_suite_preserves_storage_and_reports_area_tradeoff(study):
    state = option(study, "a-ensuite")["states"][0]
    old_rooms = source_option("a-upper-wet-core")["plans"]["floors"][1]["rooms"]
    def selector(rs):
        return Counter((i["catalog_id"], i["width_mm"], i["depth_mm"]) for r in rs for i in r["furniture"] if i["catalog_id"] in {"wardrobe-180", "hall-cabinet"})
    assert selector(state["plans"]["floors"][1]["rooms"]) == selector(old_rooms)
    scenario = next(s for s in study["requirement_ledger"]["scenarios"] if s["id"] == "a-ensuite")
    master = next(r for r in scenario["rows"] if r["requirement_id"] == "A.floor-2.master")
    bath = next(r for r in scenario["rows"] if r["requirement_id"] == "A.floor-2.master_bath")
    assert master["area"]["sensitivity"][-1]["area_sqm"] == 12.1265
    assert bath["area"]["sensitivity"][-1]["area_sqm"] == 4.4485
    assert master["area"]["target_sqm"] == 16 and bath["area"]["target_sqm"] == 5
    assert option(study, "a-ensuite")["owner_choice"] == "pending-suite-and-storage-tradeoff"
    current = next(s for s in study["requirement_ledger"]["scenarios"] if s["id"] == "a-current")
    assert next(r for r in current["rows"] if r["requirement_id"] == "A.floor-2.master_bath")["allocation"] == "unaccommodated"


def test_c_single_washer_full_rack_hvac_and_care_route(study):
    state = option(study, "c-care-refined")["states"][0]
    washers = [(f["id"], i) for f in state["plans"]["floors"] for r in f["rooms"] for i in r["furniture"] if i["catalog_id"] == "washer"]
    assert len(washers) == 1 and washers[0][0] == "floor-2"
    balcony = rooms(state, 1)["balcony2f"]
    rack = next(i for i in balcony["furniture"] if i["catalog_id"] == "clothes-rack")
    assert [rack["width_mm"], rack["depth_mm"]] == [2400, 600]
    assert [i["id"].split(":")[-1] for i in balcony["furniture"] if i["catalog_id"].endswith("planning")] == ["utility-sink", "locked-cleaner"]
    detail = state["review"]["detail"]
    assert detail["equipment_hvac_hits"] == detail["operation_failures"] == []
    assert not detail["elder_local_700mm_body_route"]["coordinate_failures"]
    assert all(not r["coordinate_failures"] for r in detail["balcony_local_700mm_routes"].values())
    assert detail["first_floor_work_balcony"].startswith("unmet-")
    assert not any(r["room"] == "C:floor-2:balcony2f" for r in state["review"]["furniture_body_sensitivity"])
    original = source_option("c-care-laundry")["plans"]["floors"][0]
    old_kitchen = next(r for r in original["rooms"] if r["key"] == "kitchen")
    assert rooms(state, 0)["kitchen"] == old_kitchen


def test_engineering_does_not_hide_wet_projection_or_install_pump(study):
    a = option(study, "a-current")["engineering"]
    assert any(r["wet_room"] == "A:floor-3:bath3" and r["below_room"] == "A:floor-2:study" for r in a["wet_over_sensitive_rooms"])
    c = option(study, "c-care-refined")["engineering"]
    overlap = next(r for r in c["wet_over_sensitive_rooms"] if r["wet_room"] == "C:floor-2:bath2f" and r["below_room"] == "C:floor-1:elder")
    assert overlap["below_bed_body_hits"] == []  # Only the bed-body restriction was accepted.
    b = option(study, "b-rear-refined")
    pump = b["engineering"]["b_pump_alternative"]
    assert pump["body_over_protected_room_ids"] == pump["envelope_over_protected_room_ids"] == []
    assert pump["service_envelope_inside_rear_roof_115mm"]
    assert pump["status"] == "projection-study-only-not-installed"
    assert not b["states"][0]["plans"]["floors"][3]["rooms"][0]["furniture"]
    for o in study["options"]:
        assert o["engineering"]["professional_approval"] == "unknown"
        assert o["engineering"]["pipe_shafts_diameter_slopes_beams_and_ceiling_heights"].startswith("unknown-")


def test_pump_must_not_project_over_bed_or_shrine(study):
    cfg = read_json(ROOT / export.SOURCE)
    cfg["b"]["pump_alternative"]["service_envelope_mm"] = [3650, 14500, 2000, 1800]
    with pytest.raises(ContractError, match="protected"):
        engineering_review(option(study, "b-rear-refined")["states"][0]["plans"], cfg)


@pytest.mark.parametrize("change", ["washer", "scope", "approval"])
def test_confirmed_preferences_and_unknowns_fail_closed(change):
    cfg = read_json(ROOT / export.SOURCE)
    if change == "washer":
        cfg["c"]["washer_count"] = 2
    elif change == "scope":
        cfg["c"]["accepted_public_area_loss_sqm"] = 0
    else:
        cfg["professional_status"]["care_rescue_and_real_transport"] = "passed"
    with pytest.raises(ContractError):
        validate_config(cfg)


def test_shrinking_bed_is_rejected(study):
    model = copy.deepcopy(option(study, "b-rear-refined")["states"][0]["model"])
    cell = export.interior._rooms(model["buildings"][0]["floors"][1])["master2"]
    with pytest.raises(ContractError, match="scale"):
        export._move(cell, "bed", [150, 15100, 1900, 1800])


def test_source_model_and_plan_report_must_match(monkeypatch):
    # Isolate the geometry mismatch guard using sealed reports, not a live freshness claim.
    reports = {"interior-improvements": historical_study("interior-improvements"),
               "b32-rear-right": historical_study("b32-rear-right")}
    monkeypatch.setattr(export, "_verified_report", lambda root, path: reports[Path(path).parent.name])
    original = export.interior.read_model
    def altered(path: Path):
        model = original(path)
        if path.name == "interior-improvements-3d.html":
            source = next(o for o in model["bc_options"]["options"] if o["id"] == "a-upper-wet-core")
            cell = next(c for c in source["model"]["buildings"][0]["floors"][0]["cells"] if c.get("tour_active"))
            cell["name"] += " altered"
        return model
    monkeypatch.setattr(export.interior, "read_model", altered)
    with pytest.raises(ContractError, match="no longer matches: a-upper-wet-core"):
        export.build_study()


def test_changed_requirement_anchor_cannot_keep_numeric_credit(study):
    with pytest.raises(ContractError, match="requirements changed"):
        requirement_ledger(study["options"], read_json(ROOT / "inputs/requirements.json"), read_json(ROOT / "inputs/requirement-dispositions.json"), "0"*64)


def test_outputs_are_bounded_vectors_and_same_source(study):
    for o in study["options"]:
        for render in (export._engineering_svg, export._section_svg):
            svg = ET.fromstring(render(o))
            assert int(svg.get("width")) <= 900
            assert svg.get("viewBox") and not svg.findall(".//{http://www.w3.org/2000/svg}image")
        for state in o["states"]:
            for floor, mf in zip(state["plans"]["floors"], state["model"]["buildings"][0]["floors"], strict=True):
                for room in floor["rooms"]:
                    cell = next(c for c in mf["cells"] if c["id"] == room["id"])
                    assert room["geometry"] == cell["tour_mm"] and room["features"] == cell["tour_features"]
                    for i in room["furniture"]:
                        assert i["placement"] == cell["furniture_placements"]["tour_mm"][i["id"]]


def test_history_primary_and_archives_remain_read_only(study):
    assert_historical_sources("current-design-basis", study)
    assert all(s["review"]["professional_approval"] == "unknown" for o in study["options"] for s in o["states"])
    assert study["requirement_ledger"]["ledger_hash"] == stable_hash({k: v for k, v in study["requirement_ledger"].items() if k != "ledger_hash"})


def test_changed_new_items_fit_their_assumed_finished_floor(study):
    for oid, floor_index, keys in (("a-ensuite", 1, {"master", "master-front", "ensuite-study", "study"}), ("c-care-refined", 1, {"balcony2f"})):
        table = rooms(option(study, oid)["states"][0], floor_index)
        for key in keys:
            room = table[key]
            areas = [rect(room)]
            if key.startswith("master"):
                areas = [rect(table[k]) for k in ("master", "master-front")]
            assert all(_inside(body(i), areas, 115) for i in room["furniture"])

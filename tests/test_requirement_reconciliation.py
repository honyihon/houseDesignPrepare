from __future__ import annotations

import copy
import json
import sys

import pytest

from house_design.cli import main
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, write_json
from house_design.requirement_reconciliation import (
    REGISTRY,
    _public_path,
    build_reconciliation,
    discussion_area,
    reconciliation_markdown,
    write_reconciliation,
)


def room(identifier, x=0, y=0, w=3000, h=4000):
    return {"id": identifier, "key": identifier.rsplit(":", 1)[-1], "name": "TEST ONLY room",
            "geometry": {"x_mm": x, "y_mm": y, "w_mm": w, "h_mm": h}, "furniture": [], "features": {}}


def assignment(path, variable, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"window.{variable} = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")


@pytest.fixture
def case(tmp_path):
    reqs = [{"id": rid, "title": "TEST ONLY requirement", "applies_to": {"building_id": "A", "floor_id": floor},
             "status": "candidate", "priority": "should", "constraints": {"min_sqm": 9, "target_sqm": 12}}
            for rid, floor in (("A.floor-2.master", "floor-2"), ("A.floor-2.closet", "floor-2"), ("A.floor-rf.tank", "floor-rf"))]
    requirements = {"schema": "house-requirements-v2", "requirements": reqs}
    write_json(tmp_path / "inputs/requirements.json", requirements)
    write_json(tmp_path / "inputs/project.json", {"project_id": "TEST-LEDGER"})
    profile = {
        "A.floor-2.master": {"allocation": "mapped", "rooms": ["A:floor-2:bed"], "note": "TEST ONLY master"},
        "A.floor-2.closet": {"allocation": "shared", "rooms": ["A:floor-2:bed"], "note": "TEST ONLY distributed closet"},
        "A.floor-rf.tank": {"allocation": "mapped", "rooms": ["A:floor-4:tank"], "note": "TEST ONLY roof tank"},
    }
    building = {"id": "A", "floors": [
        {"id": "floor-2", "plan_file": "A_floor-2.svg", "rooms": [room("A:floor-2:bed")]},
        {"id": "floor-4", "plan_file": "A_floor-4.svg", "rooms": [room("A:floor-4:tank")]},
    ]}
    layout = {"schema": "house-concept-furniture-plan-v1", "buildings": [building]}
    main_path = "structured/main/layout.js"
    assignment(tmp_path / main_path, "HOUSE_CONCEPT_LAYOUT", layout)
    study_path = "structured/study/layout.js"
    opts = []
    for sid, width in (("smaller", 2000), ("larger", 4000)):
        b = copy.deepcopy(building)
        b["floors"][0]["rooms"][0]["geometry"]["w_mm"] = width
        area = discussion_area([b["floors"][0]["rooms"][0]], 80)
        opts.append({"id": sid, "plans": b, "review": {"program": {"area_checks": [{
            "id": "A.floor-2.master", "room_ids": ["A:floor-2:bed"], "discussion_inset_sqm": area,
        }]}}})
    study = {"schema": "house-fixture-study-v1", "options": opts,
             "source_hashes": {"inputs/requirements.json": sha256_file(tmp_path / "inputs/requirements.json")}}
    assignment(tmp_path / study_path, "HOUSE_TEST_STUDY", study)
    scenarios = [{"id": "main", "label": "TEST ONLY main", "building_ids": ["A"], "profile": "base",
                  "path": main_path, "assignment": "HOUSE_CONCEPT_LAYOUT", "schema": layout["schema"], "viewer": "structured/model.html"}]
    scenarios += [{"id": sid, "label": "TEST ONLY " + sid, "building_ids": ["A"], "profile": "base", "path": study_path,
                   "assignment": "HOUSE_TEST_STUDY", "schema": study["schema"], "viewer": "structured/study.html?scheme=" + sid}
                  for sid in ("smaller", "larger")]
    registry = {"schema": "house-requirement-dispositions-v1", "project_id": "TEST-LEDGER",
                "requirements_sha256": sha256_file(tmp_path / "inputs/requirements.json"),
                "discussion_insets_mm": [80, 100, 115], "floor_aliases": {"floor-rf": "floor-4"},
                "profiles": {"base": profile}, "scenarios": scenarios, "supplementary": []}
    write_json(tmp_path / REGISTRY, registry)
    return {"root": tmp_path, "registry": registry, "requirements": requirements, "layout": layout,
            "study": study, "main_path": main_path, "study_path": study_path}


def update_registry(case):
    write_json(case["root"] / REGISTRY, case["registry"])


def select(report, sid="main", rid="A.floor-2.master"):
    return next(r for s in report["scenarios"] if s["id"] == sid for r in s["rows"] if r["requirement_id"] == rid)


def test_current_66_requirements_have_full_per_scenario_dispositions_including_rf():
    report = build_reconciliation()
    assert report["summary"]["canonical_requirements"] == 66
    assert report["summary"]["by_building"] == {"A": 24, "B": 22, "C": 20}
    assert report["summary"]["scenario_count"] == 6
    assert report["summary"]["scenario_rows"] == 170
    assert report["summary"]["verified_requirements"] == 0
    assert report["registry_requirements_anchor_matches"]
    reqs = read_json(ROOT / "inputs/requirements.json")["requirements"]
    for s in report["scenarios"]:
        expected = {r["id"] for r in reqs if r["applies_to"]["building_id"] in s["building_ids"]}
        assert {r["requirement_id"] for r in s["rows"]} == expected
        assert s["summary"]["disposition_rows"] == len(expected)
        assert any(r["floor_id"] == "floor-rf" for r in s["rows"])
        assert not s["adopted"]
        assert all(r["functional_acceptance"] == r["professional_acceptance"] == "unknown" for r in s["rows"])
        assert not any(set(r["flags"]) & {"missing-room-reference", "room-scope-mismatch", "existing-area-table-disagrees",
                                           "snapshot-requirement-id-conflict"} for r in s["rows"])
    assert report["summary"]["orphaned_binding_ids"] == []


def test_same_room_name_does_not_make_a_second_independent_a_master_bath():
    report = build_reconciliation()
    bath = select(report, "abc-main", "A.floor-2.master_bath")
    assert bath["allocation"] == "unaccommodated"
    assert bath["area"]["discussion_inset_sqm"] is None
    assert select(report, "abc-main", "A.floor-2.bath2")["room_ids"] == ["A:floor-2:master-bath"]


def test_b32_missing_functions_cannot_borrow_from_old_b_or_another_floor():
    report = build_reconciliation()
    for sid in ("b32-rear", "b32-front"):
        s = next(s for s in report["scenarios"] if s["id"] == sid)
        assert s["summary"]["original_partial_area_rows"] == 7
        for rid in ("B.floor-1.idf_b", "B.floor-1.balcony_b", "B.floor-rf.rf_tank", "B.floor-rf.rf_hp"):
            row = select(report, sid, rid)
            assert row["allocation"] == "unaccommodated" and row["room_ids"] == []
            assert row["area"]["discussion_inset_sqm"] is None
        assert select(report, sid, "B.floor-3.ktv")["allocation"] == "separate-study"
        assert select(report, sid, "B.floor-1.bath_acc")["area"]["discussion_inset_sqm"] == 8.736
        assert "sensitivity-below-target" in select(report, sid, "B.floor-2.master_b")["flags"]
    rear = select(report, "b32-rear", "B.floor-1.shrine")["context_metrics"]
    front = select(report, "b32-front", "B.floor-1.shrine")["context_metrics"]
    assert rear["shrine_whole_room_discussion_sqm"] == front["shrine_whole_room_discussion_sqm"] == 30.2104
    assert rear["shrine_after_passage_reserve_sqm"] != front["shrine_after_passage_reserve_sqm"]
    assert rear["shrine_after_passage_reserve_sqm"] < 22 and front["shrine_after_passage_reserve_sqm"] < 22


def test_c_guest_area_sensitivity_and_height_options_never_mix():
    report = build_reconciliation()
    for sid in ("c-integrated-3000", "c-integrated-3600", "c-integrated-4000"):
        row = select(report, sid, "C.floor-2.guest2")
        assert row["area"]["discussion_inset_sqm"] == 9.3456
        assert row["area"]["target_sqm"] == 12
        assert row["area"]["state"] == "below-target"
        assert row["area"]["sensitivity"][-1]["area_sqm"] == 8.9179
        assert "sensitivity-below-minimum" in row["flags"]
    assert select(report, "c-integrated-3600", "C.floor-3.master_c")["area"]["state"] == "discussion-only"
    assert select(report, "c-integrated-4000", "C.floor-3.master_c")["area"]["state"] == "below-target"


def test_parking_and_c_public_wc_are_supplementary_not_silently_dropped_or_credited():
    report = build_reconciliation()
    main = next(s for s in report["scenarios"] if s["id"] == "abc-main")
    assert {r["requirement_id"] for r in main["supplementary"]} == {"A-parking", "B-parking", "C-parking", "C-public-wc"}
    assert all(r["allocation"] == "unaccommodated" for r in main["supplementary"])
    c = next(s for s in report["scenarios"] if s["id"] == "c-integrated-3600")
    public = next(r for r in c["supplementary"] if r["requirement_id"] == "C-public-wc")
    assert public["room_ids"] == ["C:floor-1:public-bath"] and public["functional_acceptance"] == "unknown"


@pytest.mark.parametrize("rects,expected", [
    ([room("x")], 10.9056),
    ([room("x"), room("y", x=3000)], 22.4256),
    ([room("x"), room("y", x=2000)], 18.5856),
    ([room("x"), room("y")], 10.9056),
    ([room("x"), room("y", x=6000)], 21.8112),
    ([room("x", w=6000, h=2000), room("y", y=2000, h=2000)], 16.4256),
    ([room("x", w=100)], 0), ([], 0),
])
def test_exact_discussion_union_does_not_double_count_open_seams_or_overlaps(rects, expected):
    assert discussion_area(rects, 80) == expected


@pytest.mark.parametrize("value", [-1, True, "80", float("nan"), float("inf")])
def test_invalid_inset_rejected(value):
    with pytest.raises(ContractError):
        discussion_area([room("x")], value)


def test_nominal_area_is_union_not_rectangle_sum():
    assert discussion_area([room("x"), room("y", x=2000)], 0) == 20


def test_full_coverage_is_not_a_completion_status_and_shared_closet_does_not_credit_bedroom(case):
    report = build_reconciliation(case["root"])
    assert report["summary"]["verified_requirements"] == 0
    assert select(report)["requirement_status"] == "candidate"
    closet = select(report, rid="A.floor-2.closet")
    assert closet["area"]["state"] == "shared-not-independent"
    assert closet["area"]["nominal_union_sqm"] is None
    assert closet["shared_with_requirement_ids"] == ["A.floor-2.master"]
    assert not select(report)["area"]["additive_across_requirements"]


def test_added_requirement_still_appears_and_changes_invalidate_mapping_anchor(case):
    added = copy.deepcopy(case["requirements"]["requirements"][0])
    added["id"] = "A.floor-2.new-room"
    case["requirements"]["requirements"].append(added)
    write_json(case["root"] / "inputs/requirements.json", case["requirements"])
    report = build_reconciliation(case["root"])
    assert not report["registry_requirements_anchor_matches"]
    row = select(report, rid=added["id"])
    assert row["allocation"] == "unmapped" and "missing-binding" in row["flags"]
    assert "requirements-changed-binding-needs-review" in select(report)["flags"]
    assert len(report["scenarios"][0]["rows"]) == 4


def test_removed_requirement_is_visible_as_orphaned_mapping(case):
    case["requirements"]["requirements"].pop()
    write_json(case["root"] / "inputs/requirements.json", case["requirements"])
    report = build_reconciliation(case["root"])
    assert report["summary"]["orphaned_binding_ids"] == ["A.floor-rf.tank"]
    assert not report["registry_requirements_anchor_matches"]


def test_broken_room_reference_never_keeps_a_numeric_area(case):
    case["registry"]["profiles"]["base"]["A.floor-2.master"]["rooms"] = ["A:floor-2:missing"]
    update_registry(case)
    row = select(build_reconciliation(case["root"]))
    assert row["area"]["discussion_inset_sqm"] is None and row["area"]["state"] == "unknown"
    assert row["missing_room_ids"] == ["A:floor-2:missing"]


def test_rf_floor_alias_does_not_allow_wrong_floor_as_a_match(case):
    case["registry"]["profiles"]["base"]["A.floor-rf.tank"]["rooms"] = ["A:floor-2:bed"]
    update_registry(case)
    row = select(build_reconciliation(case["root"]), rid="A.floor-rf.tank")
    assert "room-scope-mismatch" in row["flags"] and row["area"]["state"] == "unknown"


def test_snapshot_requirement_id_disagreement_is_visible_not_inferred_from_name(case):
    case["layout"]["buildings"][0]["floors"][0]["rooms"][0]["requirement_id"] = "A.floor-2.other"
    assignment(case["root"] / case["main_path"], "HOUSE_CONCEPT_LAYOUT", case["layout"])
    row = select(build_reconciliation(case["root"]))
    assert "snapshot-requirement-id-conflict" in row["flags"] and row["area"]["state"] == "unknown"


def test_option_specific_values_and_area_table_crosscheck(case):
    report = build_reconciliation(case["root"])
    assert select(report, "smaller")["area"]["state"] == "below-minimum"
    assert select(report, "larger")["area"]["state"] == "discussion-only"
    case["study"]["options"][0]["review"]["program"]["area_checks"][0]["discussion_inset_sqm"] = 999
    assignment(case["root"] / case["study_path"], "HOUSE_TEST_STUDY", case["study"])
    report = build_reconciliation(case["root"])
    assert "existing-area-table-disagrees" in select(report, "smaller")["flags"]
    assert "existing-area-table-disagrees" not in select(report, "larger")["flags"]


@pytest.mark.parametrize("fault", ["missing", "malformed", "executable", "wrong-schema", "duplicate-option"])
def test_unavailable_snapshot_cannot_make_requirements_disappear(case, fault):
    path = case["root"] / case["study_path"]
    if fault == "missing":
        path.unlink()  # Synthetic temporary fixture only.
    elif fault == "malformed":
        path.write_text("window.HOUSE_TEST_STUDY = {broken};")
    elif fault == "executable":
        path.write_text("window.HOUSE_TEST_STUDY = {}; throw new Error('must never execute');")
    else:
        data = copy.deepcopy(case["study"])
        if fault == "wrong-schema":
            data["schema"] = "wrong"
        else:
            data["options"].append(copy.deepcopy(data["options"][0]))
        assignment(path, "HOUSE_TEST_STUDY", data)
    report = build_reconciliation(case["root"])
    small = next(s for s in report["scenarios"] if s["id"] == "smaller")
    assert len(small["rows"]) == 3 and small["source_freshness"]["state"] == "stale-or-incomplete"
    assert select(report, "smaller")["area"]["state"] == "unknown"


def test_recorded_hash_change_is_visible_without_regenerating_or_hiding_snapshot(case):
    case["study"]["source_hashes"]["inputs/requirements.json"] = "not-the-current-hash"
    assignment(case["root"] / case["study_path"], "HOUSE_TEST_STUDY", case["study"])
    report = build_reconciliation(case["root"])
    small = next(s for s in report["scenarios"] if s["id"] == "smaller")
    assert small["source_freshness"]["state"] == "stale-or-incomplete"
    assert "source-stale-or-incomplete" in select(report, "smaller")["flags"]
    assert select(report, "smaller")["area"]["state"] == "below-minimum"  # Describes old snapshot, never approves.


@pytest.mark.parametrize("name", ["../outside.json", "/tmp/outside.json", "inputs/private/budget.json", ".git/config", "inputs/a\\b.json"])
def test_provenance_cannot_open_private_or_external_files(case, name):
    with pytest.raises(ContractError):
        _public_path(case["root"], name)


def test_source_symlink_escape_is_rejected(case, tmp_path_factory):
    outside = tmp_path_factory.mktemp("ledger-external") / "public.json"
    outside.write_text("TEST ONLY outside")
    link = case["root"] / "inputs/linked.json"
    link.symlink_to(outside)
    with pytest.raises(ContractError):
        _public_path(case["root"], "inputs/linked.json")


def test_public_alias_cannot_resolve_to_a_private_file_inside_project(case):
    private = case["root"] / "inputs/private/test-only.json"
    write_json(private, {"note": "TEST ONLY PRIVATE CONTENT"})
    link = case["root"] / "inputs/public-alias.json"
    link.symlink_to(private)
    with pytest.raises(ContractError, match="nonpublic"):
        _public_path(case["root"], "inputs/public-alias.json")


@pytest.mark.parametrize("mutation", ["project", "duplicate-scenario", "pass-status", "missing-note", "unallocated-with-rooms", "bad-insets"])
def test_invalid_registry_fails_before_any_output_write(case, mutation):
    reg = case["registry"]
    binding = reg["profiles"]["base"]["A.floor-2.master"]
    if mutation == "project":
        reg["project_id"] = "another project"
    elif mutation == "duplicate-scenario":
        reg["scenarios"].append(copy.deepcopy(reg["scenarios"][0]))
    elif mutation == "pass-status":
        binding["allocation"] = "pass"
    elif mutation == "missing-note":
        binding["note"] = ""
    elif mutation == "unallocated-with-rooms":
        binding["allocation"] = "unaccommodated"
    else:
        reg["discussion_insets_mm"] = [115, 80]
    update_registry(case)
    with pytest.raises(ContractError):
        build_reconciliation(case["root"])
    assert not (case["root"] / "structured/reconciliation").exists()


def test_stable_hash_and_writes_only_new_report_files(case, tmp_path):
    before = {p: sha256_file(p) for p in case["root"].rglob("*") if p.is_file()}
    first, second = build_reconciliation(case["root"]), build_reconciliation(case["root"])
    assert first["report_hash"] == second["report_hash"]
    assert stable_hash({k: v for k, v in first.items() if k not in {"report_hash", "generated_at"}}) == first["report_hash"]
    directory = tmp_path / "outputs"
    paths = write_reconciliation(first, case["root"], directory)
    assert read_json(paths["json"]) == first
    content = paths["markdown"].read_text()
    assert "共用，不計獨立面積" in content and "各案分開" in content
    assert all(sha256_file(p) == digest for p, digest in before.items())
    assert {p.name for p in directory.iterdir()} == {"requirement-ledger.json", "requirement-ledger.md"}


def test_markdown_table_handles_pipes_and_newlines_without_losing_ids(case):
    case["registry"]["profiles"]["base"]["A.floor-2.master"]["note"] = "a|b\nc"
    update_registry(case)
    report = build_reconciliation(case["root"])
    markdown = reconciliation_markdown(report, case["root"], case["root"] / "out")
    assert "a／b c" in markdown
    assert "A.floor-2.master" in markdown and "A.floor-rf.tank" in markdown
    assert "?scheme=smaller" in markdown


def test_cli_writes_only_the_explicit_lightweight_ledger(case, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["house-design", "predesign", "requirement-ledger", "--root", str(case["root"])])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["summary"]["canonical_requirements"] == 3
    assert read_json(case["root"] / "structured/reconciliation/requirement-ledger.json")["summary"]["verified_requirements"] == 0

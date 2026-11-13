"""Counterexamples for merging a cabinet into a different floor version."""
import copy
import json
from pathlib import Path

import pytest

from house_design.contracts import stable_hash
from scripts.check_upper_floor_storage_merge import OUT, build, compare_floor

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def test_only_the_six_same_source_AC_cases_get_unapplied_insertion_coordinates(report):
    assert stable_hash(report) == stable_hash(json.loads((ROOT/OUT).read_text()))
    assert report["summary"] == {"storage_cases": 10, "floor_state_comparisons": 30,
        "same_source_candidates": 6, "whole_floor_rebase_required": 4, "unapplied_insertions": 6}
    assert {p["case"] for p in report["unapplied_insertions"]} == {
        "A-2F", "A-3F", "A-RF", "C-2F", "C-3F", "C-RF"}
    assert all(not p["applied"] and isinstance(p["existing_furniture_ids_to_preserve"], list)
        for p in report["unapplied_insertions"])
    c2 = next(p for p in report["unapplied_insertions"] if p["case"] == "C-2F")
    assert c2["existing_furniture_ids_to_preserve"] == []  # The dry reserve is currently empty.
    assert not report["main_3d_changed"] and not report["storage_viewer_changed"]
    assert report["protected_controls_unchanged"] == 149


def test_B_cabinet_fits_old_XY_but_all_six_entry_states_still_require_full_floor_rebase(report):
    for case in [c for c in report["cases"] if c["building"] == "B"]:
        assert case["status"] == "whole-floor-rebase-required"
        assert len(case["comparisons"]) == 6
        assert {c["option"] for c in case["comparisons"]} == {"b-rear-split", "b-front-split"}
        assert {c["state"] for c in case["comparisons"]} == {"daily", "ritual", "carry"}
        assert all(not c["source_floor_exact"] and not c["same_floor_insertion_candidate"] for c in case["comparisons"])
        assert all(sum(r["overlap_sqm"] for r in c["current_rooms_under_cabinet"]) == .54 for c in case["comparisons"])


def test_change_elsewhere_on_same_floor_cannot_be_hidden_by_a_matching_target_room():
    storage = json.loads((ROOT/"structured/coordination/upper-floor-storage-v1/review.json").read_text())
    source = json.loads((ROOT/"structured/candidates/kaohsiung-house-options/c-stair-integration.json").read_text())
    case = next(c for c in storage["cases"] if c["id"] == "A-2F")
    option = next(o for o in source["options"] if o["id"] == case["option"])
    floor = next(f for f in option["states"][0]["plans"]["floors"] if f["id"] == case["floor"])
    assert compare_floor(case, floor)["same_floor_insertion_candidate"]
    changed = copy.deepcopy(floor)
    other = next(r for r in changed["rooms"] if r["key"] != case["room"] and r["furniture"])
    other["furniture"][0]["placement"]["aabb"]["maxX"] += 1
    result = compare_floor(case, changed)
    assert result["target_room_id_present"]
    assert not result["source_floor_exact"] and not result["same_floor_insertion_candidate"]
    assert floor != changed

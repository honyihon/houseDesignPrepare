from __future__ import annotations

from scripts.generate_layout_candidates import (
    RoomTraits,
    SlotTraits,
    build_floor_candidates,
    generate_weighted_assignment,
)


def _room(uid: str, name: str) -> RoomTraits:
    return RoomTraits(
        uid=uid,
        name=name,
        is_public=False,
        is_private=False,
        is_wet=False,
        is_service=False,
        needs_daylight=False,
        mep_heavy=False,
        daylight_metric_score=None,
        daylight_metric_status="",
        daylight_metric_source="",
        daylight_metric_confidence=0.25,
    )


def _slot(slot_id: str, order: int, name: str) -> SlotTraits:
    return SlotTraits(
        slot_id=slot_id,
        order=order,
        name=name,
        entrance_proximity=1.0,
        is_outdoor=False,
        is_wet=False,
        is_service=False,
    )


def test_weighted_assignment_preserves_locked_pairs() -> None:
    rooms = [_room("A:floor-1:garage", "車庫"), _room("A:floor-1:living", "客廳")]
    slots = [_slot("slot-1", 1, "車庫"), _slot("slot-2", 2, "客廳")]

    assignment, unplaced = generate_weighted_assignment(
        rooms,
        slots,
        {"circulation": 1.0, "daylight": 0.0, "mep": 0.0},
        "circulation",
        {"A:floor-1:garage": "slot-1"},
    )

    assert assignment["A:floor-1:garage"] == "slot-1"
    assert assignment["A:floor-1:living"] == "slot-2"
    assert unplaced == []


def test_all_strategies_keep_explicit_source_bindings() -> None:
    floor = {
        "id": "floor-1",
        "title": "1F",
        "tab_label": "1F",
        "rooms": [
            {"uid": "A:floor-1:garage", "local_id": "garage", "name": "車庫", "semantics": {}},
            {"uid": "A:floor-1:living", "local_id": "living", "name": "客廳", "semantics": {}},
        ],
        "plan_cells": [
            {"order": 1, "name": "車庫", "target_room_uid": "A:floor-1:garage", "classes": [], "badges": []},
            {"order": 2, "name": "客廳", "target_room_uid": "A:floor-1:living", "classes": [], "badges": []},
        ],
    }

    result = build_floor_candidates({"id": "A"}, floor)

    for candidate in result["candidates"]:
        assert candidate["room_to_slot"] == {
            "A:floor-1:garage": "slot-1",
            "A:floor-1:living": "slot-2",
        }
        assert candidate["locked_room_count"] == 2
    assert result["best_candidate_id"] == "baseline"

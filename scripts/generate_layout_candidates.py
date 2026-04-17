#!/usr/bin/env python3
"""Generate and score layout candidates from room_program.json."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROGRAM_FILE = ROOT / "structured" / "room_program.json"
OUTPUT_DIR = ROOT / "structured" / "candidates"
OUTPUT_FILE = OUTPUT_DIR / "layout_candidates.json"
SUMMARY_MD = OUTPUT_DIR / "summary.md"
SCHEMA_VERSION = "layout-candidates-v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_match_text(value: str) -> str:
    value = normalize_whitespace(value).lower()
    # Keep CJK, english letters and digits for matching.
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value)
    return value


def has_any_keyword(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def similarity_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        short = min(len(a), len(b))
        long = max(len(a), len(b))
        return short / long
    set_a = set(a)
    set_b = set(b)
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union


@dataclass
class RoomTraits:
    uid: str
    name: str
    is_public: bool
    is_private: bool
    is_wet: bool
    is_service: bool
    needs_daylight: bool
    mep_heavy: bool


@dataclass
class SlotTraits:
    slot_id: str
    order: int
    name: str
    entrance_proximity: float  # 1.0 near entrance, 0.0 deep/private side
    is_outdoor: bool
    is_wet: bool
    is_service: bool


def room_traits(room: dict[str, Any]) -> RoomTraits:
    name = normalize_whitespace(room.get("name", ""))
    text = normalize_match_text(name)

    is_public = has_any_keyword(text, ["客廳", "餐廳", "玄關", "娛樂", "茶水", "書房", "神明廳"])
    is_private = has_any_keyword(text, ["主臥", "臥", "客房", "孝親"])
    is_wet = has_any_keyword(text, ["廚", "衛", "浴", "洗", "陽台", "茶水"])
    is_service = has_any_keyword(
        text,
        ["mdf", "idf", "機櫃", "設備", "水塔", "熱泵", "儲藏", "工具", "配電", "機房", "弱電"],
    )
    needs_daylight = is_public or is_private or has_any_keyword(text, ["書房", "運動", "客房"])
    mep_heavy = is_wet or is_service

    return RoomTraits(
        uid=room["uid"],
        name=name,
        is_public=is_public,
        is_private=is_private,
        is_wet=is_wet,
        is_service=is_service,
        needs_daylight=needs_daylight,
        mep_heavy=mep_heavy,
    )


def slot_traits(slot: dict[str, Any], max_order: int) -> SlotTraits:
    name = normalize_whitespace(slot.get("name", ""))
    text = normalize_match_text(name + " " + " ".join(slot.get("badges", [])) + " " + " ".join(slot.get("classes", [])))
    classes = set(slot.get("classes", []))

    is_outdoor = "outdoor" in classes or has_any_keyword(text, ["陽台", "露台", "側院", "車庫", "戶外", "庭"])
    is_wet = "wet" in classes or "water" in classes or has_any_keyword(text, ["廚", "衛", "浴", "水", "洗", "茶水"])
    is_service = bool(classes & {"core", "mdf", "water", "emergency"}) or has_any_keyword(
        text, ["mdf", "idf", "機櫃", "設備", "機房", "儲藏", "配電", "弱電"]
    )

    order = int(slot.get("order", 1))
    if max_order <= 1:
        entrance_proximity = 1.0
    else:
        entrance_proximity = 1.0 - ((order - 1) / (max_order - 1))

    return SlotTraits(
        slot_id=f"slot-{order}",
        order=order,
        name=name,
        entrance_proximity=entrance_proximity,
        is_outdoor=is_outdoor,
        is_wet=is_wet,
        is_service=is_service,
    )


def base_dimension_scores(room: RoomTraits, slot: SlotTraits) -> dict[str, float]:
    # Each dimension score ranges roughly in [-1.0, 1.0].
    circulation = 0.0
    if room.is_public:
        circulation += 0.6 * slot.entrance_proximity
    if room.is_private:
        circulation += 0.7 * (1.0 - slot.entrance_proximity)
    if room.is_service:
        circulation += 0.3 * (1.0 - slot.entrance_proximity)

    daylight = 0.0
    if room.needs_daylight:
        daylight += 1.0 if slot.is_outdoor else -0.35
    else:
        daylight += 0.2 if not slot.is_outdoor else -0.1

    mep = 0.0
    if room.mep_heavy:
        if slot.is_wet:
            mep += 0.8
        elif slot.is_service:
            mep += 0.5
        else:
            mep -= 0.6
    if room.is_service:
        mep += 0.5 if slot.is_service else -0.25
    if room.is_wet and slot.is_wet:
        mep += 0.4

    # Clamp to stable range.
    return {
        "circulation": max(-1.0, min(1.0, circulation)),
        "daylight": max(-1.0, min(1.0, daylight)),
        "mep": max(-1.0, min(1.0, mep)),
    }


def strategy_fit_score(room: RoomTraits, slot: SlotTraits, weights: dict[str, float]) -> float:
    dims = base_dimension_scores(room, slot)
    return (
        dims["circulation"] * weights["circulation"]
        + dims["daylight"] * weights["daylight"]
        + dims["mep"] * weights["mep"]
    )


def room_priority(room: RoomTraits, strategy: str) -> tuple[int, str]:
    if strategy == "mep":
        return (2 if room.mep_heavy else 1 if room.is_service else 0, room.name)
    if strategy == "daylight":
        return (2 if room.needs_daylight else 0, room.name)
    if strategy == "circulation":
        return (2 if room.is_public or room.is_private else 0, room.name)
    return (1 if room.is_public or room.is_private or room.mep_heavy else 0, room.name)


def generate_weighted_assignment(
    rooms: list[RoomTraits],
    slots: list[SlotTraits],
    weights: dict[str, float],
    strategy: str,
) -> tuple[dict[str, str], list[str]]:
    available_slots = {s.slot_id: s for s in slots}
    room_to_slot: dict[str, str] = {}
    ordered_rooms = sorted(rooms, key=lambda r: room_priority(r, strategy), reverse=True)

    for room in ordered_rooms:
        if not available_slots:
            break
        best_slot_id = max(
            available_slots.keys(),
            key=lambda sid: strategy_fit_score(room, available_slots[sid], weights),
        )
        room_to_slot[room.uid] = best_slot_id
        del available_slots[best_slot_id]

    unplaced = [r.uid for r in rooms if r.uid not in room_to_slot]
    return room_to_slot, unplaced


def build_baseline_assignment(
    floor: dict[str, Any],
    rooms: list[RoomTraits],
    slots: list[SlotTraits],
) -> tuple[dict[str, str], list[str]]:
    room_map = {r.uid: r for r in rooms}
    local_to_uid = {r["local_id"]: r["uid"] for r in floor["rooms"]}
    room_to_slot: dict[str, str] = {}
    used_rooms: set[str] = set()
    slot_lookup = {s.slot_id: s for s in slots}

    # 1) direct link from target_room_uid
    for slot in floor["plan_cells"]:
        order = slot["order"]
        sid = f"slot-{order}"
        uid = slot.get("target_room_uid", "")
        if uid and uid in room_map and uid not in used_rooms:
            room_to_slot[uid] = sid
            used_rooms.add(uid)

    # 2) fallback by local id link
    for slot in floor["plan_cells"]:
        order = slot["order"]
        sid = f"slot-{order}"
        if sid in room_to_slot.values():
            continue
        local_id = slot.get("target_room_local_id", "")
        uid = local_to_uid.get(local_id, "")
        if uid and uid in room_map and uid not in used_rooms:
            room_to_slot[uid] = sid
            used_rooms.add(uid)

    # 3) fuzzy name match for remaining slots/rooms
    remaining_rooms = [r for r in rooms if r.uid not in used_rooms]
    used_slots = set(room_to_slot.values())
    for slot in floor["plan_cells"]:
        sid = f"slot-{slot['order']}"
        if sid in used_slots:
            continue
        cell_text = normalize_match_text(slot.get("name", ""))
        if not cell_text:
            continue
        best_room = None
        best_score = 0.0
        for room in remaining_rooms:
            s = similarity_score(cell_text, normalize_match_text(room.name))
            if s > best_score:
                best_score = s
                best_room = room
        if best_room and best_score >= 0.35:
            room_to_slot[best_room.uid] = sid
            used_rooms.add(best_room.uid)
            used_slots.add(sid)
            remaining_rooms = [r for r in remaining_rooms if r.uid != best_room.uid]

    unplaced = [r.uid for r in rooms if r.uid not in room_to_slot]
    return room_to_slot, unplaced


def invert_assignment(room_to_slot: dict[str, str]) -> dict[str, str]:
    return {slot_id: room_uid for room_uid, slot_id in room_to_slot.items()}


def score_candidate(
    room_to_slot: dict[str, str],
    rooms: list[RoomTraits],
    slots: list[SlotTraits],
) -> dict[str, Any]:
    room_map = {r.uid: r for r in rooms}
    slot_map = {s.slot_id: s for s in slots}
    slot_to_room = invert_assignment(room_to_slot)

    dim_values = {"circulation": [], "daylight": [], "mep": []}
    pair_details = []
    for slot in slots:
        uid = slot_to_room.get(slot.slot_id, "")
        if not uid:
            continue
        room = room_map[uid]
        dims = base_dimension_scores(room, slot)
        for k in dim_values:
            dim_values[k].append(dims[k])
        pair_details.append(
            {
                "slot_id": slot.slot_id,
                "slot_order": slot.order,
                "slot_name": slot.name,
                "room_uid": uid,
                "room_name": room.name,
                "dimension_fit": dims,
            }
        )

    def to_100(values: list[float]) -> float:
        if not values:
            return 0.0
        avg = sum(values) / len(values)
        return round(((avg + 1.0) / 2.0) * 100.0, 2)

    circulation = to_100(dim_values["circulation"])
    daylight = to_100(dim_values["daylight"])
    mep = to_100(dim_values["mep"])

    assigned_count = len(room_to_slot)
    room_count = max(1, len(rooms))
    slot_count = max(1, len(slots))
    utilization = round((assigned_count / min(room_count, slot_count)) * 100.0, 2)

    unplaced_ratio = max(0.0, (room_count - assigned_count) / room_count)
    penalty = 20.0 * unplaced_ratio
    total = round(max(0.0, (circulation * 0.35 + daylight * 0.30 + mep * 0.35) - penalty), 2)

    return {
        "scores": {
            "circulation": circulation,
            "daylight": daylight,
            "mep": mep,
            "utilization": utilization,
            "total": total,
            "penalty_unplaced_rooms": round(penalty, 2),
        },
        "pair_details": sorted(pair_details, key=lambda x: x["slot_order"]),
        "unassigned_slots": [s.slot_id for s in slots if s.slot_id not in slot_to_room],
        "assigned_count": assigned_count,
    }


def candidate_rationale(strategy: str) -> list[str]:
    if strategy == "baseline":
        return ["使用原始圖面格位與房間的既有對應（含名稱模糊匹配補位）。"]
    if strategy == "circulation":
        return ["優先優化動線：公共區靠近入口，私領域往內層。"]
    if strategy == "daylight":
        return ["優先優化採光：客廳/臥室/書房盡量放在戶外或採光友善格位。"]
    if strategy == "mep":
        return ["優先優化機電維護：濕區/設備區集中到 wet/core/service 友善格位。"]
    return []


def build_floor_candidates(building: dict[str, Any], floor: dict[str, Any]) -> dict[str, Any]:
    room_items = floor["rooms"]
    slot_items = floor["plan_cells"]
    room_traits_list = [room_traits(r) for r in room_items]
    slot_traits_list = [slot_traits(s, max_order=len(slot_items)) for s in slot_items]

    baseline_map, baseline_unplaced = build_baseline_assignment(floor, room_traits_list, slot_traits_list)

    strategies = [
        ("baseline", {"circulation": 0.34, "daylight": 0.33, "mep": 0.33}, baseline_map, baseline_unplaced),
        ("circulation", {"circulation": 0.65, "daylight": 0.20, "mep": 0.15}, None, None),
        ("daylight", {"circulation": 0.20, "daylight": 0.65, "mep": 0.15}, None, None),
        ("mep", {"circulation": 0.15, "daylight": 0.15, "mep": 0.70}, None, None),
    ]

    candidates = []
    for strategy, weights, predefined, predefined_unplaced in strategies:
        if predefined is not None:
            room_to_slot = predefined
            unplaced = predefined_unplaced or []
        else:
            room_to_slot, unplaced = generate_weighted_assignment(room_traits_list, slot_traits_list, weights, strategy)

        scored = score_candidate(room_to_slot, room_traits_list, slot_traits_list)
        candidates.append(
            {
                "id": strategy,
                "strategy": strategy,
                "weights": weights,
                "rationale": candidate_rationale(strategy),
                "room_to_slot": room_to_slot,
                "unplaced_room_uids": unplaced,
                "unassigned_slots": scored["unassigned_slots"],
                "scores": scored["scores"],
                "pair_details": scored["pair_details"],
            }
        )

    candidates.sort(key=lambda c: c["scores"]["total"], reverse=True)
    best = candidates[0] if candidates else None

    return {
        "building_id": building["id"],
        "floor_id": floor["id"],
        "floor_title": floor["title"],
        "tab_label": floor.get("tab_label", ""),
        "room_count": len(room_items),
        "slot_count": len(slot_items),
        "candidates": candidates,
        "best_candidate_id": best["id"] if best else "",
        "best_total_score": best["scores"]["total"] if best else 0.0,
    }


def generate_summary_md(floor_results: list[dict[str, Any]]) -> str:
    lines = []
    lines.append("# Layout Candidate Summary")
    lines.append("")
    lines.append(f"- Generated at: `{now_iso()}`")
    lines.append(f"- Evaluated floors: **{len(floor_results)}**")
    lines.append("")
    lines.append("## Best Candidate by Floor")
    lines.append("")
    lines.append("| Building | Floor | Best Strategy | Total | Circulation | Daylight | MEP |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for fr in floor_results:
        if not fr["candidates"]:
            continue
        best = fr["candidates"][0]
        s = best["scores"]
        lines.append(
            f"| {fr['building_id']} | {fr['floor_id']} {fr['floor_title']} | {best['id']} | "
            f"{s['total']} | {s['circulation']} | {s['daylight']} | {s['mep']} |"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `baseline` uses original mapping (+ fuzzy fallback).")
    lines.append("- `circulation/daylight/mep` are greedy strategy candidates based on weighted heuristics.")
    lines.append("- Use this as a fast screening layer before manual architectural refinement.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    if not PROGRAM_FILE.exists():
        raise SystemExit("room_program.json not found. Run scripts/build_room_program.py first.")

    data = json.loads(PROGRAM_FILE.read_text(encoding="utf-8"))
    floor_results: list[dict[str, Any]] = []
    skipped_floors = []

    for building in data.get("buildings", []):
        for floor in building.get("floors", []):
            if not floor.get("rooms") or not floor.get("plan_cells"):
                skipped_floors.append(
                    {
                        "building_id": building.get("id", ""),
                        "floor_id": floor.get("id", ""),
                        "reason": "missing rooms or plan_cells",
                    }
                )
                continue
            floor_results.append(build_floor_candidates(building, floor))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "source_program_file": str(PROGRAM_FILE.name),
        "evaluated_floor_count": len(floor_results),
        "skipped_floor_count": len(skipped_floors),
        "floors": floor_results,
        "skipped_floors": skipped_floors,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    SUMMARY_MD.write_text(generate_summary_md(floor_results), encoding="utf-8")

    print(f"Wrote candidates: {OUTPUT_FILE}")
    print(f"Wrote summary:    {SUMMARY_MD}")
    print(f"Evaluated floors: {len(floor_results)}; skipped: {len(skipped_floors)}")


if __name__ == "__main__":
    main()

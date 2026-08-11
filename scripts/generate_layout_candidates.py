#!/usr/bin/env python3
"""Generate and score layout candidates from room_program.json."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.architect_metrics import build_daylight_score_index


ROOT = Path(__file__).resolve().parents[1]
PROGRAM_FILE = ROOT / "structured" / "room_program.json"
ARCHITECT_METRICS_FILE = ROOT / "structured" / "architect_metrics" / "metrics.json"
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
    daylight_metric_score: float | None
    daylight_metric_status: str
    daylight_metric_source: str
    daylight_metric_confidence: float


@dataclass
class SlotTraits:
    slot_id: str
    order: int
    name: str
    entrance_proximity: float  # 1.0 near entrance, 0.0 deep/private side
    is_outdoor: bool
    is_wet: bool
    is_service: bool


def load_daylight_score_index() -> tuple[dict[str, dict[str, Any]], str]:
    if not ARCHITECT_METRICS_FILE.exists():
        return {}, "missing"
    try:
        payload = json.loads(ARCHITECT_METRICS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, "invalid_json"
    return build_daylight_score_index(payload), "loaded"


def room_traits(room: dict[str, Any], daylight_index: dict[str, dict[str, Any]] | None = None) -> RoomTraits:
    name = normalize_whitespace(room.get("name", ""))
    text = normalize_match_text(name)
    daylight_index = daylight_index or {}
    daylight_metric = daylight_index.get(str(room.get("uid", "")), {})
    daylight_metric_score = None
    confidence_label = str(daylight_metric.get("confidence", "low"))
    daylight_metric_confidence = {"high": 0.75, "medium": 0.5, "low": 0.25}.get(confidence_label, 0.25)
    if "fit_score" in daylight_metric:
        try:
            daylight_metric_score = float(daylight_metric.get("fit_score"))
        except (TypeError, ValueError):
            daylight_metric_score = None

    is_public = has_any_keyword(text, ["客廳", "餐廳", "玄關", "娛樂", "茶水", "書房", "神明廳"])
    is_private = has_any_keyword(text, ["主臥", "臥", "客房", "孝親"])
    is_wet = has_any_keyword(text, ["廚", "衛", "浴", "洗", "陽台", "茶水"])
    is_service = has_any_keyword(
        text,
        ["mdf", "idf", "機櫃", "設備", "水塔", "熱泵", "儲藏", "工具", "配電", "機房", "弱電"],
    )
    declared_daylight = (room.get("semantics") or {}).get("daylight_required")
    needs_daylight = (
        bool(declared_daylight)
        if declared_daylight is not None
        else is_public or is_private or has_any_keyword(text, ["書房", "運動", "客房"])
    )
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
        daylight_metric_score=daylight_metric_score,
        daylight_metric_status=str(daylight_metric.get("status", "")),
        daylight_metric_source=str(daylight_metric.get("source", "")),
        daylight_metric_confidence=daylight_metric_confidence,
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
        if room.daylight_metric_score is not None:
            slot_score = 1.0 if slot.is_outdoor else -0.35
            confidence = room.daylight_metric_confidence
            daylight += room.daylight_metric_score * confidence + slot_score * (1.0 - confidence)
        else:
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


def dimension_fit_sources(room: RoomTraits) -> dict[str, str]:
    if room.needs_daylight and room.daylight_metric_score is not None:
        daylight = (
            f"{room.daylight_metric_source or 'architect_metrics:daylight_factor'}"
            f";confidence={room.daylight_metric_confidence:.2f};blended_with_slot"
        )
    elif room.needs_daylight:
        daylight = "fallback:outdoor_slot_heuristic"
    else:
        daylight = "fallback:non_daylight_room_heuristic"
    return {
        "circulation": "heuristic:room_privacy_and_entrance_proximity",
        "daylight": daylight,
        "mep": "heuristic:wet_service_slot_fit",
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
    locked_assignment: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    room_uids = {room.uid for room in rooms}
    slot_ids = {slot.slot_id for slot in slots}
    room_to_slot = {
        room_uid: slot_id
        for room_uid, slot_id in (locked_assignment or {}).items()
        if room_uid in room_uids and slot_id in slot_ids
    }
    used_slots = set(room_to_slot.values())
    available_slots = {s.slot_id: s for s in slots if s.slot_id not in used_slots}
    ordered_rooms = sorted(
        (room for room in rooms if room.uid not in room_to_slot),
        key=lambda r: room_priority(r, strategy),
        reverse=True,
    )

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


def build_locked_assignment(
    floor: dict[str, Any],
    rooms: list[RoomTraits],
) -> dict[str, str]:
    """Preserve explicit source bindings as hard layout constraints."""
    room_map = {room.uid: room for room in rooms}
    local_to_uid = {room["local_id"]: room["uid"] for room in floor["rooms"]}
    room_to_slot: dict[str, str] = {}
    used_slots: set[str] = set()

    for slot in floor["plan_cells"]:
        slot_id = f"slot-{slot['order']}"
        uid = str(slot.get("target_room_uid", ""))
        if not uid:
            uid = local_to_uid.get(str(slot.get("target_room_local_id", "")), "")
        if uid and uid in room_map and uid not in room_to_slot and slot_id not in used_slots:
            room_to_slot[uid] = slot_id
            used_slots.add(slot_id)

    return room_to_slot


def build_baseline_assignment(
    floor: dict[str, Any],
    rooms: list[RoomTraits],
    slots: list[SlotTraits],
) -> tuple[dict[str, str], list[str]]:
    room_to_slot = build_locked_assignment(floor, rooms)
    used_rooms = set(room_to_slot)

    # Fuzzy matching is only a baseline fallback for source cells without an
    # explicit target binding. Weighted strategies never move locked pairs.
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
                "dimension_fit_sources": dimension_fit_sources(room),
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


def build_floor_candidates(
    building: dict[str, Any],
    floor: dict[str, Any],
    daylight_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    room_items = floor["rooms"]
    slot_items = floor["plan_cells"]
    room_traits_list = [room_traits(r, daylight_index) for r in room_items]
    slot_traits_list = [slot_traits(s, max_order=len(slot_items)) for s in slot_items]

    baseline_map, baseline_unplaced = build_baseline_assignment(floor, room_traits_list, slot_traits_list)
    locked_map = build_locked_assignment(floor, room_traits_list)

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
            room_to_slot, unplaced = generate_weighted_assignment(
                room_traits_list,
                slot_traits_list,
                weights,
                strategy,
                locked_map,
            )

        scored = score_candidate(room_to_slot, room_traits_list, slot_traits_list)
        candidates.append(
            {
                "id": strategy,
                "strategy": strategy,
                "weights": weights,
                "rationale": candidate_rationale(strategy),
                "room_to_slot": room_to_slot,
                "locked_room_to_slot": locked_map,
                "locked_room_count": len(locked_map),
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
    lines.append("> **早期草圖存檔（HTML 分支）** —— 非現行設計基準。")
    lines.append("> 這裡的分數建立在 HTML 推測出來的幾何上（約 8 成為 `auto`），")
    lines.append("> 保留作存檔與需求追溯。現行基準見 `structured/parametric/capacity.md`。")
    lines.append("")
    lines.append(f"- Generated at: `{now_iso()}`")
    lines.append(f"- Evaluated floors: **{len(floor_results)}**")
    lines.append("")
    lines.append("## Best Candidate by Floor")
    lines.append("")
    lines.append("| Building | Floor | Best Strategy | Grade | Total | vs Baseline | Circulation | Daylight | MEP |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    low_score_reviews: list[tuple[str, str, float]] = []
    for fr in floor_results:
        if not fr["candidates"]:
            continue
        best = fr["candidates"][0]
        baseline = next((item for item in fr["candidates"] if item["id"] == "baseline"), best)
        s = best["scores"]
        delta = round(s["total"] - baseline["scores"]["total"], 2)
        grade = "good" if s["total"] >= 80 else "review" if s["total"] >= 65 else "weak"
        lines.append(
            f"| {fr['building_id']} | {fr['floor_id']} {fr['floor_title']} | {best['id']} | {grade} | "
            f"{s['total']} | {delta:+.2f} | {s['circulation']} | {s['daylight']} | {s['mep']} |"
        )
        if s["total"] < 65:
            weakest = min(("circulation", "daylight", "mep"), key=lambda key: s[key])
            low_score_reviews.append((f"{fr['building_id']}:{fr['floor_id']}", weakest, s[weakest]))
    if low_score_reviews:
        lines.extend(["", "## Low-score Review", "", "| Floor | Weakest Dimension | Score |", "|---|---|---:|"])
        for floor_label, weakest, score in low_score_reviews:
            lines.append(f"| {floor_label} | {weakest} | {score} |")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `baseline` uses original mapping (+ fuzzy fallback).")
    lines.append("- `circulation/daylight/mep` move only rooms without explicit source bindings; locked room-slot pairs are preserved.")
    lines.append("- Daylight score uses `structured/architect_metrics/metrics.json` when available, then falls back to the original outdoor-slot heuristic.")
    lines.append("- Use this as a fast screening layer before manual architectural refinement.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    if not PROGRAM_FILE.exists():
        raise SystemExit("room_program.json not found. Run scripts/build_room_program.py first.")

    data = json.loads(PROGRAM_FILE.read_text(encoding="utf-8"))
    daylight_index, architect_metrics_status = load_daylight_score_index()
    floor_results: list[dict[str, Any]] = []
    skipped_floors = []
    non_floor_sections = []

    for building in data.get("buildings", []):
        for floor in building.get("floors", []):
            if not floor.get("rooms") or not floor.get("plan_cells"):
                non_floor_sections.append(
                    {
                        "building_id": building.get("id", ""),
                        "floor_id": floor.get("id", ""),
                        "record_type": floor.get("record_type", "section"),
                    }
                )
                continue
            floor_results.append(build_floor_candidates(building, floor, daylight_index))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "source_program_file": str(PROGRAM_FILE.name),
        "architect_metrics_file": str(ARCHITECT_METRICS_FILE.relative_to(ROOT)),
        "architect_metrics_status": architect_metrics_status,
        "architect_daylight_metric_count": len(daylight_index),
        "evaluated_floor_count": len(floor_results),
        "skipped_floor_count": len(skipped_floors),
        "non_floor_section_count": len(non_floor_sections),
        "floors": floor_results,
        "skipped_floors": skipped_floors,
        "non_floor_sections": non_floor_sections,
    }
    OUTPUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    SUMMARY_MD.write_text(generate_summary_md(floor_results), encoding="utf-8")

    print(f"Wrote candidates: {OUTPUT_FILE}")
    print(f"Wrote summary:    {SUMMARY_MD}")
    print(
        f"Evaluated floors: {len(floor_results)}; skipped: {len(skipped_floors)}; "
        f"non-floor sections: {len(non_floor_sections)}"
    )


if __name__ == "__main__":
    main()

"""Current discussion ledger and bounded engineering projections, not approvals.

Consumes explicit, same-source plan data. No renderer, optimisation, browser,
network or edits to requirements/archives. Historical reconciliation is retained.
"""
from __future__ import annotations

import copy
from collections import Counter

from house_design.b32_rear_right import body, rect
from house_design.b32_services import _hits
from house_design.contracts import ContractError, stable_hash
from house_design.requirement_reconciliation import _binding, _index, _row

SCHEMA = "house-current-design-basis-v1"
STATUS = "discussion-only-not-adopted"


def sleeping_room(room: dict) -> bool:
    """Legacy display kinds can be 'other'; use explicit use/real bed data too."""
    if room.get("outdoor"):
        return False
    return (room["kind"] == "bedroom" or room.get("requirement_id") in {
        "A.floor-1.flex1", "A.floor-2.master", "A.floor-2.bed2", "A.floor-3.guest",
        "B.floor-2.master_b", "B.floor-3.guest_b", "C.floor-1.elder", "C.floor-2.guest2", "C.floor-3.master_c"}
        or any(i["shape"] in {"bed", "sofa-bed"} for i in room["furniture"]))


def validate_config(cfg: dict) -> None:
    if (cfg.get("schema") != SCHEMA or cfg.get("revision") != 1 or cfg.get("status") != STATUS
            or not cfg.get("authorization") or cfg.get("insets_mm") != [80, 100, 115]
            or cfg.get("default_option") != "b-rear-refined"
            or cfg["a"].get("status") != "comparison-owner-choice-required"
            or cfg["c"].get("washer_count") != 1 or cfg["c"].get("washer_floor") != "floor-2"
            or cfg["c"].get("accepted_public_area_loss_sqm") != 1.08
            or set(cfg["professional_status"].values()) != {"unknown"}):
        raise ContractError("Keep the authorized discussion scope, owner preferences and unknown approvals")


def profiles(registry: dict) -> dict:
    """Explicit overrides: do not infer mappings from a room's display name."""
    a = copy.deepcopy(registry["profiles"]["abc-main"])
    b = copy.deepcopy(registry["profiles"]["b32"])
    c = copy.deepcopy(registry["profiles"]["c-integrated"])
    b["B.floor-1.palanquin"].update(rooms=["B:floor-1:storage", "B:floor-1:storage-front"],
        note="後左庫房與同室接段取聯集；不計公共通道，分別用本案前／後門，完整裝桿人員搬運未核。")
    b["B.floor-1.bath_acc"].update(rooms=["B:floor-1:rear-bath"],
        note="後右有窗公衛、獨立右側到達；原7m²目標保留，窗權利／淋浴照護／救援未核。")
    b["B.floor-1.balcony_b"] = {"allocation": "partial",
        "rooms": ["B:floor-1:laundry-front", "B:floor-1:laundry-base"],
        "note": "室內洗衣凹間，不是獨立工作陽台；後門版5.005m²餘量極薄，前門版4.277m²低於5m²目標，完整乾衣仍未解。"}
    c["C.floor-1.kitchen"]["note"] = "沿用屋主已接受的450mm／1.08m²取捨；不改其幾何與設備，冰箱／備餐仍分時，專業未核。"
    c["C.floor-1.balcony"]["note"] = "原1F至少4m²／目標4.8m²工作陽台仍未容納；2F單機洗槽／晾衣提案不抵銷本列，1F污衣籃不給獨立家務面積。"
    c["C.floor-2.balcony_c2"]["note"] = "保留2F唯一洗衣機／240cm晾衣架，補洗槽及防雨上鎖洗劑櫃；前陽台兼空調維修，防雨防墜及合法使用未核。"
    suite = copy.deepcopy(a)
    suite["A.floor-2.master"].update(rooms=["A:floor-2:master", "A:floor-2:master-front"],
        note="新增套衛後L形主臥取聯集，低於16m²目標；不借書房或套衛面積補數，兩件收納移書房須另選擇。")
    suite["A.floor-2.master_bath"] = {"allocation": "partial", "rooms": ["A:floor-2:ensuite-study"],
        "note": "新獨立套衛只由主臥進出，2F公衛仍保留；低於5m²目標、沒有外窗，獨立排氣／立管／防水未設計，未採用。"}
    suite["A.floor-2.study"]["note"] = "書桌、書櫃保留，另承接原180cm衣櫃一組及240cm淺櫃；使用與收納位置取捨待屋主決定，不減總收納件數。"
    for p in (a, b, c, suite):
        for binding in p.values():
            _binding(binding)
    return {"a-current": a, "a-ensuite": suite, "b-rear-refined": b, "b-front-refined": b, "c-care-refined": c}


def requirement_ledger(options: list, requirements: dict, registry: dict, requirement_sha: str) -> dict:
    if registry["requirements_sha256"] != requirement_sha:
        raise ContractError("Original requirements changed; review mappings before crediting current scenarios")
    mapping = profiles(registry)
    scenarios = []
    for option in options:
        plans = option["states"][0]["plans"]
        index = _index([plans], [option["building"]])
        profile = mapping[option["id"]]
        rows = [_row(r, profile.get(r["id"]), index, registry["floor_aliases"], registry["discussion_insets_mm"])
                for r in requirements["requirements"] if r["applies_to"]["building_id"] == option["building"]]
        originals = {r["id"]: r for r in requirements["requirements"]}
        for row in rows:
            target = originals[row["requirement_id"]].get("constraints", {}).get("door_clear_mm")
            row["door_budget_checks"] = []
            if isinstance(target, (int, float)) and not isinstance(target, bool):
                for rid in row["room_ids"]:
                    for opening in index[rid]["features"].get("doors", []):
                        nominal = opening["width_mm"]
                        row["door_budget_checks"].append({"room": rid, "neighbor": opening["neighbor"],
                            "nominal_mm": nominal, "original_required_clear_mm": target,
                            "clear_assumption_at_115mm": nominal-230,
                            "shortfall_at_115mm": max(0, target-(nominal-230)),
                            "actual_product_finished_clear_and_rescue": "unknown"})
                if any(d["shortfall_at_115mm"] for d in row["door_budget_checks"]):
                    row["flags"].append("door-clear-budget-below-original-target")
                if not row["door_budget_checks"]:
                    row["flags"].append("door-clear-evidence-missing")
        if any(set(r["flags"]) & {"missing-binding", "missing-room-reference", "room-scope-mismatch", "snapshot-requirement-id-conflict"} for r in rows):
            raise ContractError("Current discussion requirement mapping is incomplete or inconsistent")
        supplements = []
        base_profile = "abc-main" if option["building"] == "A" else "b32" if option["building"] == "B" else "c-integrated"
        for extra in registry["supplementary"]:
            if extra["building_id"] != option["building"]:
                continue
            binding = extra["profile_bindings"].get(base_profile)
            supplements.append(_row({"id": extra["id"], "title": extra["title"],
                "applies_to": {k: extra[k] for k in ("building_id", "floor_id")}}, binding,
                index, registry["floor_aliases"], registry["discussion_insets_mm"]))
        scenarios.append({"id": option["id"], "label": option["label"], "building": option["building"],
            "adopted": False, "rows": rows, "supplementary": supplements,
            "state_scope": "daily geometry; other use states are not additive area",
            "counts": dict(Counter(r["allocation"] for r in rows))})
    result = {"schema": "house-current-requirement-ledger-v1", "canonical_requirements": len(requirements["requirements"]),
        "scenario_rows": sum(len(s["rows"]) for s in scenarios), "scenarios": scenarios,
        "verified_requirements": 0, "adopted": False, "requirements_sha256": requirement_sha,
        "area_policy": "Orthogonal union, 80/100/115mm discussion insets; not legal/finished area; never sum shared rows"}
    result["ledger_hash"] = stable_hash(result)
    return result


def engineering_review(plans: dict, cfg: dict) -> dict:
    """Conservative projections flag issues; no route is treated as a pipe design."""
    wet, protected, overlaps = [], [], []
    floors = plans["floors"]
    for n, floor in enumerate(floors):
        for room in floor["rooms"]:
            if room["kind"] in {"bath", "kitchen"}:
                wet.append({"floor": floor["id"], "id": room["id"], "rect_mm": rect(room)})
                if n:
                    for lower in floors[n-1]["rooms"]:
                        if _hits(rect(room), rect(lower)) and (sleeping_room(lower) or lower["kind"] == "study"
                                or lower["key"] in {"study", "altar-backing", "storage", "shrine", "shrine-front"}):
                            overlaps.append({"wet_room": room["id"], "below_room": lower["id"],
                                "below_bed_body_hits": [i["id"] for i in lower["furniture"] if i["shape"] in {"bed", "sofa-bed"} and _hits(rect(room), body(i))],
                                "status": "requires-pipe-waterproofing-noise-and-family-review"})
            if sleeping_room(room) or room["key"] in {"shrine", "shrine-front"}:
                protected.append({"floor": floor["id"], "id": room["id"], "rect_mm": rect(room)})
    equipment_projection = []
    for n, floor in enumerate(floors):
        for room in floor["rooms"]:
            for item in room["furniture"]:
                if item["catalog_id"] not in {"pressure-pump", "water-tank", "heat-pump"}:
                    continue
                for lower in floors[:n]:
                    for target in lower["rooms"]:
                        if (sleeping_room(target) or target["key"] in {"shrine", "shrine-front"}) and _hits(body(item), rect(target)):
                            equipment_projection.append({"equipment": item["id"], "below_room": target["id"],
                                "status": "projection-warning-load-leakage-and-structureborne-noise-unknown"})
    pump = None
    if plans["id"] == "B":
        pump = copy.deepcopy(cfg["b"]["pump_alternative"])
        roof = next(f for f in floors if f["id"] == "floor-4")
        allowed = [rect(r) for r in roof["rooms"] if r["key"] == "rear-roof"]
        from house_design.b32_service_detail import _inside
        pump["service_envelope_inside_rear_roof_115mm"] = _inside(pump["service_envelope_mm"], allowed, 115)
        pump["body_over_protected_room_ids"] = [r["id"] for r in protected if _hits(r["rect_mm"], pump["rect_mm"])]
        pump["envelope_over_protected_room_ids"] = [r["id"] for r in protected if _hits(r["rect_mm"], pump["service_envelope_mm"])]
        if not pump["service_envelope_inside_rear_roof_115mm"] or pump["envelope_over_protected_room_ids"]:
            raise ContractError("Pump comparison must not borrow protected shrine/bedroom space")
    return {"status": "coordination-study-not-engineered", "wet_areas": wet, "protected_areas": protected,
        "wet_over_sensitive_rooms": overlaps, "equipment_over_sensitive_rooms": equipment_projection, "b_pump_alternative": pump,
        "pipe_shafts_diameter_slopes_beams_and_ceiling_heights": "unknown-not-drawn-as-approved-routes",
        "ventilation": "外窗另核合法性／有效開口／防雨；浴廁、家務分管排氣及補氣，避免排到神明堂／武轎庫或回吸。除濕不能代替換氣。",
        "air_conditioning": "既有室內外機及估計連線保留；依實際機型核對總長、高差、冷媒、冷凝排水、噪音、維修及換機通路，不用一般距離保證可裝。",
        "maintenance": "立管清潔口、閥件、電盤／IDF、泵浦基座及漏水斷電要從公共／維修側到達；目前未核防火區劃或工法。",
        "rear_window_fallback": "沒有後巷不能推論可開後窗。若後界不得開窗，兩個B版本都不能宣稱有窗需求成立；另研究合法退縮／天井及面積代價，機械排氣不等於已滿足外窗偏好。",
        "professional_approval": "unknown"}

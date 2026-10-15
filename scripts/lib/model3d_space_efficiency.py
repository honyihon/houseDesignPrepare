"""Area allocation diagnostics from tour coordinates, never legal/net-area QA.

Keep stairs separate from hallways, roofs separate from residential floors,
and unmet needs visible. A heuristic warning is not a reason to resize a stair.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CURRENT_ID = "abc-rationality-v6-space-efficiency"


def comparison_source_review() -> tuple[dict, Path]:
    """Older unadopted studies retain their pre-v6 geometry, not silent adoption."""
    path = ROOT / "inputs/concept-layout-review.json"
    raw = json.loads(path.read_text())
    if raw.get("id") == CURRENT_ID:
        path = ROOT / "inputs/references/abc-before-space-efficiency-20261014.json"
        raw = json.loads(path.read_text())
    return raw, path


def area(g: dict) -> float:
    return round(g["w_mm"] * g["h_mm"] / 1e6, 4)


def floor_allocation(building: str, floor: dict, baseline: dict | None = None) -> dict:
    rooms = [c for c in floor["cells"] if c.get("tour_active")]
    indoor = [c for c in rooms if not c["is_outdoor"]]
    circulation = [c for c in indoor if c.get("space_role") == "circulation" and c["kind"] != "stair"]
    stairs = [c for c in indoor if c["tour_features"].get("stairs")]
    bedrooms = [c for c in indoor if c["kind"] == "bedroom"]
    total = round(sum(area(c["tour_mm"]) for c in indoor), 4)
    circulation_area = round(sum(area(c["tour_mm"]) for c in circulation), 4)
    sleep_area = round(sum(area(c["tour_mm"]) for c in bedrooms), 4)
    roof = floor["id"] == "floor-4"
    findings = []
    # Deliberately a discussion trigger, not a building-code minimum/maximum.
    if not roof and total and circulation_area / total > .30:
        findings.append({"code": "large-circulation-allocation", "status": "needs-layout-review",
                         "note": "通行／待排乾區超過室內名義面積30%；是討論觸發值，不是法規。不得直接縮樓梯或侵占照護帶。"})
    if not roof and bedrooms and circulation_area > sleep_area:
        findings.append({"code": "circulation-larger-than-bedrooms", "status": "needs-layout-review",
                         "note": "通行／待排乾區大於本層臥室合計；須連同濕區、外窗與公共陽台通路檢視，不能只改房名。"})
    for c in indoor:
        if c["tour_features"].get("access_pending"):
            findings.append({"code": "public-access-pending", "room_id": c["id"], "status": "needs-layout-review",
                             "note": c["name"] + " 尚未具公共區／套衛相鄰入口，不能靠穿過私人房間宣稱可用。"})
        if c["kind"] == "bedroom" and any(term in c["name"] for term in ("衛浴", "套衛", "浴廁")):
            raise ValueError("Space allocation: bathroom incorrectly classified as bedroom: " + c["id"])
    before = None
    if baseline:
        specs = baseline["rooms"]
        def prior(c):
            x, y, w, h = specs[c["key"]]["rect"]
            return round(w * h / 1e6, 4)
        before = {
            "circulation_nominal_sqm": round(sum(
                r["rect"][2] * r["rect"][3] / 1e6 for r in specs.values()
                if r.get("role", "circulation" if r.get("group") else "") == "circulation"
                and r.get("kind") != "stair" and not r.get("outdoor")
            ), 4),
            "bedroom_nominal_sqm": round(sum(prior(c) for c in bedrooms), 4),
            "room_areas_sqm": {c["id"]: prior(c) for c in rooms},
            "classification": "archived-circulation-role-current-corrected-bedroom-use",
        }
    result = {
        "building": building, "floor": floor["id"], "roof": roof,
        "geometry_source": "tour_mm", "area_basis": "nominal-axis-box-not-finished-or-legal",
        "indoor_nominal_sqm": total, "circulation_nominal_sqm": circulation_area,
        "circulation_ratio": round(circulation_area / total, 4) if total else None,
        "circulation_room_ids": [c["id"] for c in circulation],
        "stairs_reserved_sqm": round(sum(area(c["tour_mm"]) for c in stairs), 4),
        "stairs_footprint_sqm": round(sum(area(c["tour_features"]["stair_footprint_mm"]) for c in stairs), 4),
        "bedroom_nominal_sqm": sleep_area, "bedroom_room_ids": [c["id"] for c in bedrooms],
        "room_areas_sqm": {c["id"]: area(c["tour_mm"]) for c in rooms},
        "baseline": before, "findings": findings, "professional_acceptance": "unknown",
    }
    for c in rooms:
        c["tour_features"]["allocation_review"] = {
            "nominal_area_sqm": area(c["tour_mm"]),
            "area_basis": result["area_basis"],
            "floor_circulation_sqm": circulation_area,
            "floor_bedroom_sqm": sleep_area,
            "room_use": c["kind"], "professional_acceptance": "unknown",
            "note": "外框面積不扣實際牆柱；通行統計含未完成收納／彈性乾區，不含樓梯本體與屋外區。屋頂另列，不作臥室效率評分。",
        }
    return result


def a_followup_review(buildings: list[dict], spec: dict) -> dict | None:
    """Verify real storage moves and functional dry zones, not just new names."""
    if spec.get("revision") != 2:
        return None
    followup = spec.get("a_followup", {})
    snapshot = "inputs/references/abc-before-a-storage-20261014.json"
    sha = "58b71451d315442ea01edc8ebd6b0574180789996975179eebf85ba97dea8e30"
    if (followup.get("schema") != "house-a-storage-dry-zone-v1"
            or followup.get("status") != "proposal-not-professionally-approved"
            or followup.get("owner_storage_choice") != "distributed-capacity-preserved"
            or followup.get("professional_acceptance") != "unknown"
            or followup.get("baseline_file") != snapshot or followup.get("baseline_sha256") != sha
            or hashlib.sha256((ROOT / snapshot).read_bytes()).hexdigest() != sha):
        raise ValueError("A storage followup needs its unchanged baseline and unapproved contract")
    before = json.loads((ROOT / snapshot).read_text())
    rooms = {c["id"]: c for b in buildings for f in b["floors"] for c in f["cells"] if c.get("tour_active")}
    changed = {
        "front-hall": [4640, 4780, 1360, 6460], "front-landing": [0, 4780, 4640, 1100],
        "rear-hall": [0, 9880, 4640, 1360], "multi": [2160, 5880, 2480, 4000],
    }
    for b in buildings:
        prior = before["buildings"][b["id"]]
        if b["layout_review"]["core"] != prior["core"]:
            raise ValueError("A storage followup may not change the stair core")
        for f in b["floors"]:
            for c in f["cells"]:
                if not c.get("tour_active"):
                    continue
                expected = prior["floors"][f["id"]]["rooms"][c["key"]]["rect"]
                if b["id"] == "A" and f["id"] == "floor-3":
                    expected = changed.get(c["key"], expected)
                if list(c["tour_mm"].values()) != expected:
                    raise ValueError("A storage followup changed a preserved room: " + c["id"])
    expected_moves = [
        {"from": "A:floor-2:walkin:furniture:wardrobe-right", "to": "A:floor-2:master:furniture:wardrobe-right", "catalog": "wardrobe-180"},
        {"from": "A:floor-2:hall2:furniture:hall-cabinet", "to": "A:floor-2:master:furniture:hall-cabinet", "catalog": "hall-cabinet"},
        {"from": "A:floor-3:multi:furniture:desk", "to": "A:floor-3:rear-common:furniture:desk", "catalog": "desk-120"},
    ]
    if followup.get("relocations") != expected_moves or followup.get("added_furniture") != ["A:floor-3:rear-common:furniture:shelf"]:
        raise ValueError("A storage followup lost its original-item relocation ledger")
    items = {i["id"]: i for c in rooms.values() for i in c.get("furniture", [])}
    for move in expected_moves:
        item = items.get(move["to"])
        if move["from"] in items or not item or item["catalog_id"] != move["catalog"]:
            raise ValueError("A storage followup duplicates or loses relocated furniture")
        item["relocated_from"] = move["from"]
    sizes = {
        "wardrobe": (1800, 600, 2200), "wardrobe-right": (1800, 600, 2200), "hall-cabinet": (2400, 400, 2200),
    }
    master = rooms["A:floor-2:master"]
    for key, size in sizes.items():
        item = items.get(master["id"] + ":furniture:" + key)
        if not item:
            raise ValueError("A storage followup loses original master storage")
        if tuple(item[k] for k in ("width_mm", "depth_mm", "height_mm")) != size or master["furniture_placements"]["tour_mm"][item["id"]]["issues"]:
            raise ValueError("A storage followup shrinks or cannot place full-size master storage")
    closet, hall = rooms["A:floor-2:walkin"], rooms["A:floor-2:hall2"]
    if (hall.get("furniture") or closet["space_role"] != "storage-zone" or len(closet["furniture"]) != 1
            or closet["furniture"][0]["catalog_id"] != "wardrobe-180"
            or tuple(closet["furniture"][0][k] for k in ("width_mm", "depth_mm", "height_mm")) != (1800, 600, 2200)
            or any(p["issues"] for p in closet["furniture_placements"]["tour_mm"].values())):
        raise ValueError("A storage followup puts storage in public access or loses the closet")
    reading = rooms["A:floor-3:rear-common"]
    if (reading["space_role"] != "work-zone" or {i["catalog_id"] for i in reading["furniture"]} != {"desk-120", "shelf-180"}
            or any(p["issues"] for p in reading["furniture_placements"]["tour_mm"].values())):
        raise ValueError("A reading area needs actual full-size desk and shelf, not just a renamed hallway")
    for item in reading["furniture"]:
        size = (1200, 600, 750) if item["catalog_id"] == "desk-120" else (1800, 400, 2100)
        if tuple(item[k] for k in ("width_mm", "depth_mm", "height_mm")) != size:
            raise ValueError("A reading furniture cannot be resized to fit")
    if any(opening.get("neighbor") == reading["id"] for opening in
           rooms["A:floor-3:back-hall"]["tour_features"]["doors"]
           + rooms["A:floor-3:back-hall"]["tour_features"]["open_connections"]):
        raise ValueError("A reading area must not replace the public bathroom/terrace access")
    result = {**followup, "status": "geometry-only-professional-review-pending", "wardrobe_capacity_mm": 5400,
              "shallow_storage_width_mm": 2400, "resolved_pending_items": 3,
              "a3_geometric_recovery_sqm": .96, "a3_activated_work_zone_sqm": 5.0976}
    for key in ("master", "walkin", "hall2"):
        rooms["A:floor-2:" + key]["tour_features"]["storage_resolution"] = result
    reading["tour_features"]["storage_resolution"] = result
    return result


def attach_space_efficiency(buildings: list[dict], review: dict) -> dict | None:
    if review.get("id") != CURRENT_ID:
        return None  # independent comparisons keep their own layout contracts
    spec = review.get("space_efficiency")
    if (not spec or spec.get("schema") != "house-space-efficiency-contract-v1"
            or spec.get("status") != "geometry-review-not-professional-approval"
            or spec.get("professional_acceptance") != "unknown"):
        raise ValueError("Current space allocation is missing its unverified contract")
    path = spec.get("baseline_file")
    if path != "inputs/references/abc-before-space-efficiency-20261014.json":
        raise ValueError("Space allocation needs the immutable pre-change layout")
    before = json.loads((ROOT / path).read_text())
    if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != "d6ae3eda9fc69c7c3dc3fc5cfe39cf475dc3715f1a273746ab2b6da1b5c1bc4f":
        raise ValueError("Space allocation baseline changed; do not rewrite historical evidence")
    for b in buildings:
        prior = before["buildings"][b["id"]]
        if b["layout_review"]["core"] != prior["core"]:
            raise ValueError("Space allocation may not shrink or relocate a stair core")
        for f in b["floors"]:
            if (f["tour_width_mm"], f["tour_depth_mm"]) != (6000, 17630):
                raise ValueError("Space allocation may not expand the fixed comparison frame")
            if b["id"] == "B" or f["id"] in {"floor-1", "floor-4"}:
                actual = {c["key"]: list(c["tour_mm"].values()) for c in f["cells"] if c.get("tour_active")}
                if actual != {k: r["rect"] for k, r in prior["floors"][f["id"]]["rooms"].items()}:
                    raise ValueError("Space allocation changed a preserved first/roof/B floor")
    audits = [floor_allocation(b["id"], f, before["buildings"][b["id"]]["floors"][f["id"]])
              for b in buildings for f in b["floors"]]
    followup = a_followup_review(buildings, spec)
    return {"schema": "house-space-efficiency-review-v1", "status": "diagnostics-not-approval", "revision": spec["revision"],
            "baseline_file": path, "professional_acceptance": "unknown",
            "heuristic_circulation_ratio": .30, "heuristic_is_law": False,
            "b_priority": spec["b_priority"], "floors": audits, "a_followup": followup}

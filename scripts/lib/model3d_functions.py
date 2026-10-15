"""Protect the owner's A 1F care program independently of HTML/3D parity.

Only a conditional furniture/function screen: no parcel, code, wheelchair
manoeuvre or professional acceptance is inferred from this check.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from lib.model3d_placement import INSET, overlaps

REQUIREMENTS_FILE = Path(__file__).resolve().parents[2] / "inputs/requirements.json"
# Explicit bindings, not fuzzy room-name matching. These obligations cannot
# disappear merely by removing a room or its binding from the proposal input.
A_CARE_BINDINGS = {
    "entry": "A.floor-1.entry",
    "living": "A.floor-1.living",
    "flex1": "A.floor-1.elder",
    "bath1": "A.floor-1.bath1",
    "kitchen": "A.floor-1.kitchen",
    "balcony1": "A.floor-1.balcony",
    "mdf": "A.floor-1.mdf",
}


def check_a_care_functions(buildings: list[dict], requirements_path: Path = REQUIREMENTS_FILE) -> dict:
    requirements = json.loads(requirements_path.read_text(encoding="utf-8"))["requirements"]
    by_id = {r["id"]: r for r in requirements}
    a = next(b for b in buildings if b["id"] == "A")
    floor = next(f for f in a["floors"] if f["id"] == "floor-1")
    cells = {c["key"]: c for c in floor["cells"] if c.get("tour_active")}

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(f"A 1F care requirement: {message}")

    coverage = []
    for key, rid in A_CARE_BINDINGS.items():
        require(rid in by_id, f"missing source requirement {rid}")
        require(key in cells, f"missing active room for {rid}")
        cell, req = cells[key], by_id[rid]
        require(req["applies_to"] == {"building_id": "A", "floor_id": "floor-1"}, f"wrong source floor for {rid}")
        require(cell.get("review_spec", {}).get("requirement_id") == rid, f"lost explicit binding for {rid}")
        require(
            sum(c.get("review_spec", {}).get("requirement_id") == rid for c in cells.values()) == 1,
            f"ambiguous room binding for {rid}",
        )
        g = cell["tour_mm"]
        # Conservative assumed inset for furniture only, not measured wall
        # thickness or legally calculated floor area.
        clear_area = max(0, g["w_mm"] - 2 * INSET) * max(0, g["h_mm"] - 2 * INSET) / 1e6
        require(clear_area >= req["constraints"]["min_sqm"], f"room below source minimum area: {rid}")
        require(not cell["tour_features"]["access_pending"], f"no common access for {rid}")
        require(
            all(not p["issues"] for p in cell["furniture_placements"]["tour_mm"].values()),
            f"pending furniture cannot prove function: {rid}",
        )
        coverage.append(
            {
                "requirement_id": rid,
                "room_id": cell["id"],
                "title": req["title"],
                "source_status": req["status"],
                "proposal_box_area_sqm": round(g["w_mm"] * g["h_mm"] / 1e6, 3),
                "assumed_clear_area_sqm": round(clear_area, 3),
                "assumed_inset_mm": INSET,
            }
        )

    def component(key: str, shape: str, *, catalog_prefix: str = "", width: int = 0, depth: int = 0) -> dict:
        matching = [
            item
            for item in cells[key]["furniture"]
            if item["shape"] == shape
            and item["catalog_id"].startswith(catalog_prefix)
            and item["width_mm"] >= width
            and item["depth_mm"] >= depth
        ]
        require(bool(matching), f"{key} missing full-size {catalog_prefix or shape}")
        return matching[0]

    elder = cells["flex1"]
    require(elder["kind"] == "bedroom" and elder["room_role"] == "elder", "elder bedroom downgraded to flex/day use")
    require("孝親房" in elder["name"], "elder bedroom lost its visible functional label")
    component("flex1", "bed", width=1000, depth=1800)
    component("flex1", "cabinet", catalog_prefix="wardrobe-", width=1200, depth=600)
    component("bath1", "toilet")
    component("bath1", "vanity", width=600)
    shower = component("bath1", "shower", width=1200, depth=1200)
    require(shower.get("step_free") is True, "missing step-free shower proposal")
    component("living", "sofa", width=1800)
    dining = component("living", "dining-set", width=1200, depth=1800)
    require(
        dining.get("table_width_mm", 0) >= 1200
        and dining.get("table_depth_mm", 0) >= 800
        and (dining["width_mm"] >= 1800 or dining["catalog_id"] == "dining-4-sides"),
        "four-seat table cannot be shrunk or replaced by a tiny unverified envelope",
    )
    component("living", "cabinet", catalog_prefix="shoe-cabinet")
    component("kitchen", "counter", width=2400)
    component("kitchen", "cabinet", catalog_prefix="fridge-")
    component("balcony1", "appliance", catalog_prefix="washer")
    component("balcony1", "appliance", catalog_prefix="water-filter")
    component("mdf", "rack", catalog_prefix="rack-18u")
    require(cells["balcony1"]["is_outdoor"], "work balcony must remain an exterior proposal")
    require(cells["balcony1"]["tour_mm"]["h_mm"] >= 1800, "lost 1.8m work-balcony depth from source rationale")

    def turn(key: str) -> None:
        g = cells[key]["tour_mm"]
        zones = [z["aabb"] for z in cells[key]["tour_features"]["reserved_mm"] if z["kind"] == "care-turn"]
        adequate = [
            z
            for z in zones
            if z["maxX"] - z["minX"] >= 1500
            and z["maxY"] - z["minY"] >= 1500
            and z["minX"] >= g["x_mm"] + INSET
            and z["maxX"] <= g["x_mm"] + g["w_mm"] - INSET
            and z["minY"] >= g["y_mm"] + INSET
            and z["maxY"] <= g["y_mm"] + g["h_mm"] - INSET
        ]
        require(bool(adequate), f"{key} lost 1500mm turning reservation")
        for box in adequate:
            require(
                all(not overlaps(box, p["aabb"]) for p in cells[key]["furniture_placements"]["tour_mm"].values()),
                f"{key} furniture occupies turning reservation",
            )

    for key in ("entry", "living", "rear-hall1", "flex1", "bath1"):
        require(key in cells, f"missing care circulation: {key}")
        turn(key)
    for key in ("entry", "living", "flex1"):
        zones = [z["aabb"] for z in cells[key]["tour_features"]["reserved_mm"] if z["kind"] == "care-route"]
        require(
            any(min(z["maxX"] - z["minX"], z["maxY"] - z["minY"]) >= 1200 for z in zones),
            f"{key} lost proposed 1200mm clear route",
        )

    for key in ("flex1", "bath1"):
        minimum = by_id[A_CARE_BINDINGS[key]]["constraints"]["door_clear_mm"]
        features = cells[key]["tour_features"]
        require(
            any(d["width_mm"] >= minimum and d.get("operation") == "sliding" for d in features["doors"]),
            f"{key} lost 900mm sliding-door proposal",
        )
        require(not features["open_connections"], f"{key} lost private enclosure")
    require(
        any(d["neighbor"] is None and d["width_mm"] >= 900 for d in cells["entry"]["tour_features"]["doors"]),
        "lost accessible entrance proposal",
    )
    require(
        elder["tour_features"]["window_face"] in {"front", "rear"} and elder["window_mm"] >= 900,
        "elder bedroom has no front/rear daylight proposal",
    )
    window = elder["tour_features"]
    length = elder["tour_mm"]["w_mm"]
    centre = length * window["window_ratio"]
    require(
        centre - elder["window_mm"] / 2 >= INSET and centre + elder["window_mm"] / 2 <= length - INSET,
        "elder window extends past wall",
    )

    by_cell_id = {c["id"]: c for c in cells.values()}
    graph = {key: [] for key in cells}
    for key, cell in cells.items():
        features = cell["tour_features"]
        for door in features["doors"] + features["open_connections"]:
            other = by_cell_id.get(door["neighbor"])
            if other and door["width_mm"] >= 900:
                reciprocal = other["tour_features"]["doors"] + other["tour_features"]["open_connections"]
                require(
                    any(d["neighbor"] == cell["id"] and d["width_mm"] == door["width_mm"] for d in reciprocal),
                    f"unpaired care opening: {key} / {other['key']}",
                )
                graph[key].append(other["key"])

    def route(start: str, target: str, permitted: set[str]) -> list[str]:
        queue, seen = deque([[start]]), {start}
        while queue:
            path = queue.popleft()
            if path[-1] == target:
                return [cells[k]["id"] for k in path]
            for key in graph[path[-1]]:
                if key not in seen and (key in permitted or key == target):
                    seen.add(key)
                    queue.append([*path, key])
        require(False, f"no 900mm common route: {start} -> {target}")
        return []

    common = {"entry", "living", "stair-door", "rear-hall1", "care-passage"}
    routes = {
        "entrance_to_elder": route("entry", "flex1", common),
        "elder_to_bath": route("flex1", "bath1", common),
        "entrance_to_bath": route("entry", "bath1", common),
    }
    require("balcony1" in graph["kitchen"], "kitchen must directly reach balcony without crossing elder room")
    routes["kitchen_to_work_balcony"] = [cells[k]["id"] for k in ("kitchen", "balcony1")]
    return {
        "id": "A-1F-care-functions",
        "status": "conditional-proposal-function-screen-only",
        "source": "inputs/requirements.json",
        "requirements": coverage,
        "routes": routes,
        "site_legality": "unknown",
        "professional_accessibility": "unknown",
        "deviations_pending_review": [
            {
                "requirement_id": "A.floor-1.living",
                "note": "客餐廳由原需求後帶改前帶，為本次照護回補替代配置，不視為位置條件已滿足。",
            },
            {
                "requirement_id": "A.floor-1.entry",
                "note": "車庫進屋緩衝改街側乾式入口，原停車需求未容納；須比較合法外部停車與一車替代案。",
            },
            {
                "requirement_id": "A.floor-1.mdf",
                "note": "MDF優先研究上折梯下，梯廳側維修壁龕保留備援；候選未成立前不釋放備援，不假定梯段下方淨高、防火或散熱足夠。",
            },
        ],
        "note": "保護孝親房、床與衣櫃、150cm轉位、淋浴／馬桶／洗手台及公共動線，不只檢查HTML／3D一致。基地容量、門框後淨寬、輪椅與照護演練、扶手、浴簾、防水及避難未核。浴廁操作與轉位地面、廚房操作與通行分時共用，設備本體不占暫留區；不是法規通過。客餐廳前移與停車替代仍待方案確認，原需求狀態不變。"
        + (" 本版已保留3.9m騎樓；適用、牆柱與梁下淨高仍未知。" if "arcade" in cells else " 歷史骨架以前帶可建為條件。"),
    }


def check_a_arcade_functions(buildings: list[dict], care: dict) -> dict:
    """Protect the agreed A design basis, independently of frontend parity.

    This checks a provisional 32-ping frame, NOT surveyed land, legal floor
    area, headroom, accessibility or parking approval. Historical comparisons
    must explicitly opt out rather than quietly inherit the new main basis.
    """
    a = next(b for b in buildings if b["id"] == "A")
    floors = a["floors"]
    rooms = {c["key"]: c for c in floors[0]["cells"] if c.get("tour_active")}

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError("A 32-ping arcade: " + message)

    parking = a["layout_review"]["parking"]
    require(
        parking["verified_spaces"] is None and parking["displayed_cars"] == 0, "parking is not verified or accommodated"
    )
    require(
        care["site_legality"] == care["professional_accessibility"] == "unknown",
        "function screen is not professional approval",
    )
    require(
        all((f["tour_width_mm"], f["tour_depth_mm"]) == (6000, 17630) for f in floors), "fixed parcel frame changed"
    )
    arcade = rooms.get("arcade")
    require(arcade is not None, "missing visible arcade room")
    require(arcade["tour_mm"] == {"x_mm": 0, "y_mm": 0, "w_mm": 6000, "h_mm": 3900}, "lost full-width 3.9m frontage")
    require(arcade["is_outdoor"] and arcade["review_spec"].get("clear"), "frontage cannot be private indoor use")
    require(not arcade["furniture"] and not arcade["tour_features"]["hvac_units"], "private item occupies arcade")
    require(all(c is arcade or c["tour_mm"]["y_mm"] >= 3900 for c in rooms.values()), "room encroaches on arcade")
    require(
        not any(i["category"] == "vehicle" for c in rooms.values() for i in c["furniture"]),
        "parking cannot be counted in arcade",
    )
    require([f["base_mm"] for f in floors] == [0, 4000, 7000, 10000], "storey bases disagree with ground height")
    require([f["height_mm"] for f in floors] == [4000, 3000, 3000, 3000], "nominal heights changed")
    passage = rooms.get("care-passage")
    require(passage is not None and passage["tour_mm"]["w_mm"] - 2 * INSET >= 1200, "lost 120cm assumed clear passage")
    forbidden = {c["id"] for c in rooms.values() if c["kind"] == "stair" or c.get("space_role") == "equipment-alcove"}
    require(
        all(not forbidden.intersection(route) for route in care["routes"].values()), "care route crosses stairs or MDF"
    )
    common_landing = None
    for floor in floors:
        stair = next(c for c in floor["cells"] if c.get("tour_active") and c["tour_features"]["stairs"])
        features = stair["tour_features"]
        geometry, landing = features["stair_geometry"], features.get("shared_landing_mm")
        require(
            geometry["fits_reserved_box"] and geometry["shared_front_landing"], "stair has no fitting shared landing"
        )
        require(
            geometry["flight_width_mm"] == 900 and geometry["tread_mm"] == 260, "stair discussion dimensions changed"
        )
        require(features["stair_geometry_verified"] is False, "stair is not professionally verified")
        require(
            geometry["risers"] == (24 if floor["id"] == "floor-1" else 18) and geometry["departure_offset_mm"] == 0,
            "stair run disagrees with proposed storey",
        )
        require(landing is not None and landing["h_mm"] == 1000, "lost full 1m front landing")
        box = {
            "minX": landing["x_mm"],
            "maxX": landing["x_mm"] + landing["w_mm"],
            "minY": landing["y_mm"],
            "maxY": landing["y_mm"] + landing["h_mm"],
        }
        shared = next(c for c in floor["cells"] if c["id"] == landing["space"])
        require(
            any(
                o["neighbor"] == shared["id"] and o["face"] == "front" and o["width_mm"] >= landing["w_mm"]
                for o in features["open_connections"]
            ),
            "landing not connected at floor level",
        )
        require(
            not features["doors"] and all(o["face"] == "front" for o in features["open_connections"]),
            "side/rear door opens into a stair flight",
        )
        require(
            all(not overlaps(box, p["aabb"]) for p in shared["furniture_placements"]["tour_mm"].values()),
            "furniture occupies shared landing",
        )
        footprint = {k: landing[k] for k in ("x_mm", "y_mm", "w_mm", "h_mm")}
        require(common_landing is None or footprint == common_landing, "front landings are not stacked")
        common_landing = footprint
    return {
        "id": "A-32ping-arcade-functions",
        "status": "bounded-arcade-and-function-screen-only",
        "arcade_depth_mm": 3900,
        "arcade_area_sqm": 23.4,
        "assumed_clear_passage_mm": 1200,
        "nominal_ground_storey_mm": 4000,
        "nominal_headroom_budget_mm": 3500,
        "surveyed_parcel": "unknown",
        "arcade_applicability": "unknown",
        "legal_building_area_sqm": None,
        "verified_headroom_mm": None,
        "professional_acceptance": "unknown",
        "verified_parking_spaces": None,
        "note": "32坪含騎樓的概念功能初篩；前3.9m只通行，沒有新增基地或停車。90cm梯段、平台、牆柱、梁下淨高、建蔽／容積、採光、消防及照護演練仍待核。客餐廳假設淨面積僅約18.00m²，施工餘裕很小。",
    }

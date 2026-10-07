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
    component("living", "dining-set", width=1800, depth=1800)
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

    common = {"entry", "living", "stair-door", "rear-hall1"}
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
                "note": "樓梯下機櫃改梯廳側維修壁龕，不假定梯段下方淨高、防火或散熱足夠。",
            },
        ],
        "note": "保護孝親房、床與衣櫃、150cm轉位、淋浴／馬桶／洗手台及公共動線，不只檢查HTML／3D一致。前帶可建、基地容量、門框後淨寬、輪椅與照護演練、扶手、浴簾、防水及避難未核。浴廁操作與轉位地面、廚房操作與通行分時共用，設備本體不占暫留區；不是法規通過。客餐廳前移與停車替代仍待方案確認，原需求狀態不變。",
    }

"""Bounded owner-preference improvements, never a feng-shui certificate.

Check the adopted hob/upper-furniture changes against actual placements.
Historical studies without this contract retain their old geometry/profiles.
The unadopted backing and care-suite options must remain visible as decisions.
"""

from __future__ import annotations

from lib.model3d_placement import overlaps


def attach_fengshui_checks(buildings: list[dict], review: dict) -> list[dict]:
    spec = review.get("fengshui_minimal")
    if spec is None:
        if review.get("id") in {"abc-rationality-v5-minimal-fengshui", "abc-rationality-v6-space-efficiency"}:
            raise ValueError("Minimal fengshui proposal: current source is missing its decision contract")
        return []

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError("Minimal fengshui proposal: " + message)

    require(
        spec.get("id") == "abc-minimal-fengshui-v1"
        and spec.get("document") == "Docs/fengshui-minimal-v1.md"
        and spec.get("status") == "partial-proposal-not-approved"
        and spec.get("religious_acceptance") == spec.get("structural_acceptance") == "unknown",
        "do not invent religious/structural acceptance",
    )
    pending = spec.get("pending_decisions", [])
    require(
        {p.get("id") for p in pending} == {"B1-backing", "B-upper-use", "C1-care-suite", "A-door-and-kitchen-scope"}
        and len(pending) == 4
        and all(p.get("status") == "not-adopted" for p in pending),
        "retain unadopted family/accessibility decisions",
    )
    rooms = {c["id"]: c for b in buildings for f in b["floors"] for c in f["cells"] if c.get("tour_active")}

    def item(room_id: str, local_id: str, width: int, depth: int) -> tuple[dict, dict]:
        room = rooms[room_id]
        matches = [i for i in room["furniture"] if i["id"] == room_id + ":furniture:" + local_id]
        require(len(matches) == 1, "missing/ambiguous original item " + room_id + ":" + local_id)
        obj = matches[0]
        p = room["furniture_placements"]["tour_mm"][obj["id"]]
        require(obj["width_mm"] >= width and obj["depth_mm"] >= depth and not p["issues"], "lost full-size usable item")
        return obj, p

    def annotate(room_id: str, note: str, *, adopted: bool) -> None:
        rooms[room_id]["tour_features"]["fengshui_review"] = {
            "status": "partial-geometric-proposal-only" if adopted else "decision-pending-not-adopted",
            "religious_acceptance": "unknown",
            "note": note,
        }

    _, counter = item("A:floor-1:kitchen", "counter", 2400, 600)
    parts = counter.get("worktop_parts_mm", [])
    require(len(parts) == 2 and {p["kind"] for p in parts} == {"hob", "sink"}, "retain distinct hob and sink")
    hob = next(p for p in parts if p["kind"] == "hob")
    sink = next(p for p in parts if p["kind"] == "sink")
    require(
        counter["wall_anchor"] == "left"
        and hob["width_mm"] >= 600
        and hob["depth_mm"] >= 500
        and sink["width_mm"] >= 600
        and sink["depth_mm"] >= 450
        and hob["aabb"]["maxY"] + 600 <= sink["aabb"]["minY"] + 1,
        "retain forward hob, full-size fixtures and 600mm preparation segment",
    )
    wet_rooms = [
        c
        for f in buildings[0]["floors"][1:]
        for c in f["cells"]
        if c.get("tour_active") and c["kind"] in {"bath", "kitchen"}
    ]
    for room in wet_rooms:
        g = room["tour_mm"]
        box = {"minX": g["x_mm"], "maxX": g["x_mm"] + g["w_mm"], "minY": g["y_mm"], "maxY": g["y_mm"] + g["h_mm"]}
        require(not overlaps(hob["aabb"], box), "hob still intersects an upper wet room: " + room["id"])
    checks = [
        {
            "id": "A-hob-wet-projection",
            "status": "proposal-geometric-screen-only",
            "scope": "hob-only-not-whole-kitchen",
            "hob_aabb": hob["aabb"],
            "sink_aabb": sink["aabb"],
            "wet_room_ids": [r["id"] for r in wet_rooms],
            "plumbing_acceptance": "unknown",
        }
    ]
    annotate(
        "A:floor-1:kitchen",
        "240cm廚具前移約117cm，前爐後槽、中間60cm備料；只初篩爐台避上層濕區。洗槽及整間廚房並未全部避開浴廁；產品、排煙、配管與宗教接受未核。",
        adopted=True,
    )
    _, altar = item("B:floor-1:shrine", "altar", 1800, 600)
    upper = []
    for rid, demands in [
        ("B:floor-2:living2", [("sofa", 2400, 900), ("coffee-table", 1100, 600), ("tv", 1800, 450)]),
        ("B:floor-3:guest3", [("bed", 1050, 1880), ("wardrobe", 1800, 600), ("desk", 1400, 700)]),
    ]:
        for local_id, width, depth in demands:
            obj, p = item(rid, local_id, width, depth)
            require(not overlaps(p["aabb"], altar["aabb"]), "upper furniture overlaps the altar: " + obj["id"])
            upper.append(obj["id"])
        annotate(
            rid,
            "原尺寸家具轉向靠側牆，只避一樓神桌本體外廓；整個房間仍在神明堂上層。整廳上方禁睡已採作屋主硬條件，現三樓客房用途仍有衝突。B嚴格重排另列未採用比較，不把家具分離當宗教核可。",
            adopted=True,
        )
    checks.append(
        {
            "id": "B-upper-furniture-altar-projection",
            "status": "proposal-geometric-screen-only",
            "scope": "altar-body-only-not-whole-shrine",
            "altar_aabb": altar["aabb"],
            "item_ids": upper,
            "whole_shrine_sleep_acceptance": "unknown",
        }
    )
    _, bed = item("C:floor-3:master3f", "bed", 1800, 2000)
    require(bed["wall_anchor"] == "left" and bed["rotation_deg"] == 270, "C3 bed must retain the side-wall headboard")
    for local_id, width, depth in [("wardrobe", 1800, 600), ("vanity", 1200, 500)]:
        item("C:floor-3:master3f", local_id, width, depth)
    annotate(
        "C:floor-3:master3f",
        "180×200cm床頭改左側中段實牆，不再貼後梯／運動區；門窗、原衣櫃尺寸保留，梳妝台沿原右牆微調。樑位、鏡面角度、鄰界及聲學未核。",
        adopted=True,
    )
    checks.append(
        {
            "id": "C3-side-wall-headboard",
            "status": "proposal-geometric-screen-only",
            "headboard_wall": "left",
            "beam_acceptance": "unknown",
            "acoustic_acceptance": "unknown",
        }
    )
    annotate(
        "B:floor-1:shrine",
        "朝道路／騎樓的正前方180cm祭祀門保留；神桌背牆另一側仍為樓梯／梯廳，違反本輪屋主比較硬條件。舊右移108cm仍接梯廳，不再推薦；真正乾式背牆與整廳上方禁睡重排見B／C比較頁，取捨未定、不用假牆宣稱解決。",
        adopted=False,
    )
    annotate(
        "C:floor-1:elder",
        "主案床頭仍靠230cm後窗，上層衛浴部分投影到床尾；另有保窗側牆床與濕區同軸比較，均未採用。首選比較不縮房間／套衛；分時操作、套衛救援、輪椅及完成面未核，不能縮窗、縮床或把照護帶變窄。",
        adopted=False,
    )
    annotate(
        "A:floor-1:entry",
        "入口見梯尚未列為屋主硬禁忌；先保留共享前平台與照護通路，不加阻路屏風。若必須避直線視線，須連門位與客餐廳另排。",
        adopted=False,
    )
    annotate(
        "A:floor-1:flex1",
        "床頭實牆與照護帶保留，房門仍朝床尾；轉床會占操作／轉位。若列門床對線為硬禁忌，須另排公共乾區及門位，不把關門當作幾何已消除。",
        adopted=False,
    )
    return checks

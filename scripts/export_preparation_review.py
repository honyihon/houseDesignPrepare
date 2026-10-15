#!/usr/bin/env python3
"""Isolated C window/B program comparisons and an owner-professional meeting packet.

Never adopts a drawing, changes a surveyed value, rewrites an archived dialogue,
or infers professional acceptance from a dimensional screen.
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
import math
import sys
from collections import deque
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import export_model_3d as model3d
from lib.dimension_overrides import load_overrides
from lib.model3d_facade import build_facade, render_elevation
from lib.model3d_placement import _candidate, _issues, overlaps
from lib.model3d_plan import plan_data, render_plan
from lib.model3d_space_efficiency import comparison_source_review  # noqa: E402
from house_design.rendering import encode_html_json

SOURCE = ROOT / "inputs/preparation-review.json"
SCENARIOS = ROOT / "inputs/abc-use-scenarios.json"
OUT = ROOT / "structured/candidates"
STATUS = "comparison-only-not-adopted"
NS = "http://www.w3.org/2000/svg"
PROTECTED = [
    "AbuildingView.html", "BbuildingView.html", "CbuildingView.html",
    "inputs/concept-layout-review.json", "inputs/furniture-layout.json", "inputs/requirements.json",
    "inputs/dimensions.json", "inputs/facade-concept.json", "inputs/physical-items.json",
    "structured/candidates/model3d.html", "structured/candidates/furniture-plans/layout.js",
    "structured/candidates/bc-options/layout.js", "structured/candidates/c1f-options/layout.js",
    "Docs/c1f-kimi-discussion-brief-v1.md",
    "scripts/templates/model3d.html", "scripts/lib/model3d_placement.py",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rect(x: float, y: float, w: float, d: float) -> dict:
    return dict(zip(("x_mm", "y_mm", "w_mm", "h_mm"), (x, y, w, d), strict=True))


def box(g: dict) -> dict:
    return {"minX": g["x_mm"], "maxX": g["x_mm"] + g["w_mm"],
            "minY": g["y_mm"], "maxY": g["y_mm"] + g["h_mm"]}


def area(g: dict, inset: int = 0) -> float:
    return round((g["w_mm"] - 2 * inset) * (g["h_mm"] - 2 * inset) / 1e6, 4)


def common(a: str, b: str, width: int | None = None, centre: int | None = None) -> list:
    result = [a, b, "open" if width is None else {"type": "open", "width_mm": width}]
    return result if centre is None else [*result, centre]


def room(r: list, name: str, kind: str = "other", profile: str | None = None, **extra) -> dict:
    return {"rect": r, "name": name, "kind": kind, "outdoor": False,
            **({"profile": profile} if profile else {"clear": True}), **extra}


def profile(*products: tuple) -> list:
    clearances = {"shoe-cabinet": 600, "sofa-2": 400, "reading-chair": 600,
                  "toilet": 700, "vanity-60": 700, "shower-accessible": 700,
                  "double-bed": 600, "wardrobe-180": 600, "vanity-desk": 700,
                  "shower-90": 700, "vanity-90": 700}
    return [{"id": key, "catalog": catalog, "position": [0.5, 0.5],
             "front_clearance_mm": clearances.get(catalog, 0),
             "note": "原代表產品外廓；本輪獨立坐標初排，操作／完成面與實物演練未核。"}
            for key, catalog in products]


def source_review() -> tuple[dict, dict, dict]:
    raw, _ = comparison_source_review()
    furniture = json.loads(model3d.FURNITURE_FILE.read_text())
    old = json.loads((ROOT / "inputs/bc-constraints-options.json").read_text())
    furniture["profiles"].update(copy.deepcopy(old["profiles"]))
    raw["id"] = "preparation-review-isolated-v2"
    raw.pop("fengshui_minimal", None)
    raw["buildings"]["B"].pop("ritual_access", None)
    return raw, furniture, old


def c_proposal(raw: dict, furniture: dict, old: dict, height: int, risers: int) -> dict:
    patch = next(o for o in old["options"] if o["id"] == "c-side-bed")["patch"]
    for fid, changes in patch["floors"].items():
        for key, value in changes.items():
            if key == "rooms":
                raw["buildings"]["C"]["floors"][fid][key].update(copy.deepcopy(value))
            else:
                raw["buildings"]["C"]["floors"][fid][key] = copy.deepcopy(value)
    b = raw["buildings"]["C"]
    b.pop("open_living", None)
    b.pop("ritual_access", None)
    b["storey_heights_mm"] = [height, 3000, 3000, 3000]
    depth = (risers // 2 - 1) * 270 + 2000
    core_y = 13800 - depth - 140
    b["core"]["well_depth_mm"] = depth
    b["summary"] = "有窗訪客公衛＋開放客餐＋廚房目標＋側牆床的合併比較，未採用。"
    b["assumptions"] = ["一樓樓高與較大梯井僅敏感度，不是騎樓或消防核定。", "外窗不取代獨立排氣／補氣。"]
    b["deferred"].append({"floor": "floor-1", "key": "parking", "note": "原車位與機車需求未容納，前帶不計車位。"})
    f = b["floors"]["floor-1"]
    base = copy.deepcopy(f["rooms"])
    furniture["profiles"].update({
        "prep-c-living": profile(("sofa", "sofa-2"), ("tv", "wall-tv"), ("coffee-table", "coffee-table"), ("reading-chair", "reading-chair")),
        "prep-c-entry": profile(("shoe-cabinet", "shoe-cabinet")),
        "prep-c-wc": profile(("toilet", "toilet"), ("vanity", "vanity-60")),
    })
    group = "prep-C-open-public"
    f["rooms"] = {
        **{k: v for k, v in base.items() if k not in {"living", "dining", "entrance", "kitchen", "stair1f"}},
        "dining": {**base["dining"], "window_ratio": 0.35, "group": group, "role": "dining"},
        "entrance": room([4000, 5700, 2000, 1800], "開放乾式前室／120cm鞋櫃", "entry", "prep-c-entry", group=group, role="circulation", window_mm=0),
        "public-bath": room([4000, 3900, 2000, 1800], "有可開高窗的訪客公衛（排氣待核）", "bath", "prep-c-wc", room_role="bathroom", window_face="front", window_ratio=0.5, window_mm=600, door_operation="sliding"),
        "living": room([0, 7100, 2400, 1930], "開放客餐｜沙發電視區", "living", "prep-c-living", group=group, role="living", window_mm=0),
        "living-hall": room([2400, 7100, 1600, core_y - 7100], "客餐共用通行／轉位（非獨立房）", group=group, role="circulation", window_mm=0),
        "living-right": room([4000, 7500, 2000, core_y - 7500], "開放客餐｜彈性照護／通行（不固定擺椅）", "living", group=group, role="living", window_mm=0),
        "kitchen": {**base["kitchen"], "rect": [0, 9030, 2400, 3070], "name": "廚房原目標比較（工作帶仍分時）"},
        "stair1f": {**base["stair1f"], "rect": [2400, core_y, 3600, 13800 - core_y]},
    }
    f["entry"] = ["dining", "front", 1000, 3400]
    f["connections"] = [
        common("dining", "entrance"), common("dining", "living"), common("dining", "living-hall"),
        common("living", "living-hall"), common("living-hall", "living-right"), common("entrance", "living-right"),
        ["entrance", "public-bath", {"width_mm": 900, "operation": "sliding", "label": "訪客公衛90cm名義滑門（淨寬／門片／救援未核）"}, 4550],
        ["living-hall", "stair1f", 1000, 3400], ["stair1f", "kitchen", 900, 10200],
        ["stair1f", "sliding-door", "open"], ["sliding-door", "sideyard", "open"],
        ["stair1f", "elder", 1000, 3000], ["elder", "elder-bath", 1000, 14900],
    ]
    # Move the common vertical core on every storey, not just its 1F mesh.
    for fid, left, front in [("floor-2", "guestroom2f", "living2f"), ("floor-3", "fitness3f", "master3f")]:
        upper = b["floors"][fid]
        rooms = upper["rooms"]
        rooms[front]["rect"][3] = core_y - 3900
        rooms["front-hall"]["rect"][3] = core_y - 3900
        rooms[left]["rect"] = [0, core_y, 2400, 13800 - core_y]
        rooms["stair" + ("2f" if fid == "floor-2" else "3f")]["rect"] = [2400, core_y, 3600, 13800 - core_y]
    rf = b["floors"]["floor-4"]["rooms"]
    rf["platform"]["rect"][3] = core_y
    rf["stair-rf"]["rect"] = [2400, core_y, 3600, 13800 - core_y]
    rf["riser-rf"]["rect"] = [0, core_y, 2400, 13800 - core_y]
    # AC belongs to the right public-zone wall, not to an invisible partition.
    b["hvac_pairs"][0][1] = "living-right"
    return {"core_y_mm": core_y, "well_depth_mm": depth, "shared_landing": False}


def b_proposal(raw: dict, furniture: dict, old: dict, height: int, risers: int) -> dict:
    original = next(o for o in old["options"] if o["id"] == "b-strict")["patch"]["replace_building"]
    b = raw["buildings"]["B"] = copy.deepcopy(original)
    raw["frame_mm"] = [6000, 20530]
    b["storey_heights_mm"] = [height, 3000, 3000, 3000]
    depth = (risers // 2 - 1) * 270 + 1000
    core_y = 20530 - depth - 140
    b["core"]["well_depth_mm"] = depth
    b["summary"] = "條件式擴框功能研究：1F淋浴、武轎收納目標及20m²主臥／套衛，非32坪成立或最小土地證明。"
    b["deferred"].extend([
        {"key": "ktv", "floor": "floor-3", "note": "KTV／茶水仍未容納，跨棟未驗證。"},
        {"key": "balcony1", "floor": "floor-1", "note": "原1F洗衣工作陽台仍未容納；RF僅候選。"},
    ])
    furniture["profiles"].update({
        "prep-b-shower": profile(("accessible-shower", "shower-accessible"), ("toilet", "toilet"), ("vanity", "vanity-60")),
        "prep-b-master": profile(("bed", "double-bed"), ("wardrobe", "wardrobe-180"), ("vanity", "vanity-desk")),
        "prep-b-master-bath": profile(("shower", "shower-90"), ("toilet", "toilet"), ("vanity", "vanity-90")),
    })
    f = b["floors"]["floor-1"]
    f["rooms"].update({
        "shrine": {**f["rooms"]["shrine"], "rect": [1200, 3900, 3120, 7700],
                   "name": "神明堂（通道連動／朝道路乾式背牆）",
                   "clearance_reservations": [{"kind": "ritual-approach", "rect": [1240, 0, 1800, 4200]}]},
        "public-entry": room([0, 3900, 1200, 9500], "公共道（不穿神明堂）"),
        "idf-cabinet": {**f["rooms"]["idf-cabinet"], "rect": [1200, 11600, 1200, 1800]},
        "altar-backing": {**f["rooms"]["altar-backing"], "rect": [2400, 11600, 1920, 1800]},
        "entry": room([4320, 3900, 1680, 9500], "右側搬轎通道（168cm名義／完成面待核）", role="circulation", route_width_mm=1680),
        "corridor1": room([4320, 13400, 1680, 3830], "後段搬轎直線通道（168cm名義）", role="circulation", route_width_mm=1680),
        "rear-hall": room([0, 13400, 2400, core_y - 13400], "公共乾式梯廳／共用平台（不得置物）"),
        "stair1": {**f["rooms"]["stair1"], "rect": [0, core_y, 2400, 20530 - core_y]},
        "bath1": room([2400, 13400, 1920, 3830], "1F淋浴比較（救援／轉位未核）", "bath", "prep-b-shower", room_role="bathroom", window_mm=0, door_operation="sliding"),
        "storage": {**f["rooms"]["storage"], "rect": [2400, 17230, 3600, 3300], "name": "武轎收納目標比較（裝桿搬運未核）", "carry_path_mm": 1680, "door_mm": 1660},
    })
    f["connections"] = [
        ["shrine", "garage", {"width_mm": 1800, "purpose": "ritual-entry", "label": "朝街同軸祭祀門（未核）"}, 3340],
        ["public-entry", "shrine", 900, 5500], common("public-entry", "rear-hall"),
        common("rear-hall", "stair1"), ["rear-hall", "bath1", {"width_mm": 1060, "operation": "sliding", "label": "106cm名義淋浴滑門（淨寬／門片／救援未核）"}, 15000],
        common("entry", "corridor1"), ["entry", "shrine", 1500, 6500],
        ["entry", "altar-backing", 900, 12200],
        ["corridor1", "storage", {"width_mm": 1660, "purpose": "palanquin-storage", "operation": "sliding", "label": "武轎收納門（166cm名義／門框待核）"}, 5160],
        common("public-entry", "idf-cabinet"),
    ]
    f["entry"] = ["entry", "front", 1660, 5160]
    f["entry_label"] = "搬轎側門（166cm名義／完成面待核）"
    for fid in ("floor-2", "floor-3", "floor-4"):
        uf = b["floors"][fid]
        r = uf["rooms"]
        r["rear-hall"]["rect"] = [0, 13400, 2400, core_y - 13400]
        stair = "stair" + {"floor-2": "2", "floor-3": "3", "floor-4": "RF"}[fid]
        r[stair]["rect"] = [0, core_y, 2400, 20530 - core_y]
        left = "front-hall" if fid == "floor-4" else "corridor" + fid[-1]
        r[left]["rect"][3] = 9500
        front = {"floor-2": "living2", "floor-3": "quiet-study", "floor-4": "shrine-buffer-rf"}[fid]
        r[front]["rect"] = [1200, 3900, 3120, 7700]
        right = "right-platform" if fid == "floor-4" else "front-hall"
        r[right]["rect"] = [4320, 3900, 1680, 7700]
        if fid == "floor-2":
            r["bath2"]["rect"] = [1200, 11600, 2400, 1800]
            r["master-bath2"] = room([3600, 11600, 2400, 2950], "主臥套衛目標比較", "bath", "prep-b-master-bath", window_mm=0, door_operation="sliding")
            r["master-entry"] = room([2400, 13400, 1200, 1150], "主臥乾式入口")
            r["master2"] = room([2400, 14550, 3600, 5980], "主臥20m²目標／180cm床（完成面待核）", "bedroom", "prep-b-master", window_face="rear", window_mm=2400)
            uf["connections"] = [
                ["living2", "corridor2", 900, 5500], ["living2", "front-hall", 900, 5500],
                ["living2", "balcony2", 900, 3340], ["corridor2", "bath2", 900, 12800],
                common("corridor2", "rear-hall"), common("rear-hall", "stair2"),
                ["rear-hall", "master-entry", 900, 13975], ["master-entry", "master2", 1000, 3000],
                ["master2", "master-bath2", 800, 4700],
            ]
        elif fid == "floor-3":
            r["bath3"]["rect"] = [1200, 11600, 2400, 1800]
            r["buffer3"]["rect"] = [3600, 11600, 2400, 1800]
            r["rear-corridor"]["rect"] = [2400, 13400, 1200, 7130]
            r["guest3"]["rect"] = [3600, 13400, 2400, 7130]
            uf["connections"] = [
                ["quiet-study", "corridor3", 900, 5500], ["quiet-study", "front-hall", 900, 5500],
                ["quiet-study", "terrace3", 900, 3340], ["corridor3", "bath3", 900, 12800],
                common("corridor3", "rear-hall"), common("rear-hall", "stair3"),
                common("rear-hall", "rear-corridor"), ["rear-corridor", "guest3", 900, 14500],
                common("front-hall", "buffer3"), ["buffer3", "guest3", 900, 4140],
            ]
        else:
            for key in ("service-rf", "laundry-rf"):
                r[key]["rect"][1] = 11600
                r[key]["rect"][3] = 1800
            r["service-rf"]["rect"][2] = 3120
            r["laundry-rf"]["rect"][0:3:2] = [4320, 1680]
            for key in ("tank-rf", "pump-rf", "hotwater-rf"):
                r[key]["rect"][1:] = [13400, r[key]["rect"][2], 7130]
            uf["connections"] = [
                common("front-hall", "rear-hall"), common("rear-hall", "stairRF"),
                common("front-hall", "platform-rf"), common("right-platform", "platform-rf"),
                common("rear-hall", "tank-rf"), common("tank-rf", "pump-rf"), common("pump-rf", "hotwater-rf"),
                common("right-platform", "laundry-rf"), common("laundry-rf", "service-rf"), common("service-rf", "tank-rf"),
            ]
    return {"core_y_mm": core_y, "well_depth_mm": depth, "shared_landing": True}


def set_product(cell: dict, local: str, body: list, rotation: int, anchor: str = "", *, mount: int | None = None) -> None:
    item = next(i for i in cell["furniture"] if i["id"].endswith(":" + local))
    x, y, w, d = body
    dims = (item["width_mm"], item["depth_mm"]) if rotation % 180 == 0 else (item["depth_mm"], item["width_mm"])
    if (w, d) != dims:
        raise ValueError("Comparison may not resize a product: " + item["id"])
    if mount is not None:
        item["mount_height_mm"] = mount
    item["wall_anchor"] = anchor
    item["wall_locked"] = bool(anchor)
    item["rotation_deg"] = rotation
    operating_face = anchor or {0: "rear", 90: "right", 180: "front", 270: "left"}[rotation]
    p = _candidate(item, x + w / 2, y + d / 2, rotation, operating_face)
    # A free-standing sofa still needs front space; do not invent a backing wall.
    p["wall_anchor"], p["wall_gap_mm"] = anchor, item["wall_gap_mm"] if anchor else None
    p["basis"] = "independent-coordinate-screen-not-rehearsal"
    cell["furniture_placements"]["tour_mm"][item["id"]] = p


def c_products(building: dict, core: dict) -> None:
    cells = {c["key"]: c for c in building["floors"][0]["cells"] if c.get("tour_active")}
    # This 400mm edge is an internal bookkeeping seam in ONE open public
    # room, not a 400mm access doorway. The main adjacency helper deliberately
    # rejects contacts <600mm, so preserve that helper and join this seam only.
    hall, entry = cells["living-hall"], cells["entrance"]
    for a, b, face in [(hall, entry, "right"), (entry, hall, "left")]:
        g = a["tour_mm"]
        a["tour_features"]["open_connections"].append(
            {"face": face, "ratio": (7300 - g["y_mm"]) / g["h_mm"], "width_mm": 400,
             "neighbor": b["id"], "status": "same-open-space-grid-seam-not-access-door",
             "not_a_route_opening": True, "operation": "unconfirmed"})
    set_product(cells["dining"], "dining-set", [500, 4380, 1800, 1800], 0)
    sofa = next(i for i in cells["living"]["furniture"] if i["id"].endswith(":sofa"))
    sofa["front_clearance_mm"] = 600
    sofa["note"] += " 前留60cm；跨開放客餐資料分格，不是穿牆。右側120cm照護帶仍保留，非輪椅坐位核可。"
    set_product(cells["living"], "sofa", [1580, 6810, 900, 1800], 90)
    set_product(cells["living"], "tv", [80, 7500, 80, 1000], 270, "left", mount=1400)
    set_product(cells["living"], "coffee-table", [380, 7730, 600, 1100], 270)
    chair = next(i for i in cells["living"]["furniture"] if i["id"].endswith(":reading-chair"))
    chair["label"] = "90cm可移陪伴椅（面餐區／不占照護帶）"
    chair["note"] += " 移回沙發鄰近區、面餐區而非隔著照護帶；餐椅拉出／起身操作仍分時，旋轉擺位未核，電視主看位仍為沙發。"
    set_product(cells["living"], "reading-chair", [80, 6780, 900, 850], 0)
    set_product(cells["entrance"], "shoe-cabinet", [5570, 6700, 350, 1200], 90, "right")
    set_product(cells["public-bath"], "toilet", [5220, 5170, 700, 450], 90, "right")
    set_product(cells["public-bath"], "vanity", [5470, 4050, 450, 600], 90, "right")
    wc = cells["public-bath"]["tour_features"]
    wc["window_operable"] = "proposed-not-selected"
    wc["moisture_control"] = json.loads((ROOT / "inputs/c1f-window-moisture-brief.json").read_text())["moisture_controls"]
    toilet = next(i for i in cells["public-bath"]["furniture"] if i["id"].endswith(":toilet"))
    toilet["shared_operation_with"] = ["door-approach"]
    toilet["note"] += " 洗手操作離開門前；如廁操作仍與門前進出分時，不是多人／輪椅救援通過。"
    for key, local in [("entrance", "shoe-cabinet"), ("public-bath", "vanity")]:
        item = next(i for i in cells[key]["furniture"] if i["id"].endswith(":" + local))
        item["note"] += " 操作外廓與公衛門前暫留帶分離；門片／把手與真人進出未核。"
    turn = {"kind": "care-turn", "aabb": box(rect(2800, 6800, 1500, 1500)),
            "status": "cross-open-zone-proposal-not-rehearsed"}
    cells["living-hall"]["tour_features"]["reserved_mm"].append(turn)
    cells["living-hall"]["tour_features"]["reserved_mm"].append({
        "kind": "care-route", "aabb": box(rect(2800, 3980, 1200, core["core_y_mm"] - 4060)),
        "status": "open-public-band-only-not-door-or-finished-clearance", "label": "120cm客餐照護暫留帶（門框／柱位未核）"})
    for item in cells["elder-bath"]["furniture"]:
        if item["shape"] == "shower":
            item["label"] = "120cm照護淋浴候選（救援未核）"
    for zone in cells["elder"]["tour_features"]["reserved_mm"]:
        if zone["kind"] == "care-turn":
            zone["aabb"]["minX"] -= 80
            zone["aabb"]["maxX"] -= 80
            zone["status"] = "inset-adjusted-not-rehearsed"
    # Keep AC on a real exterior right wall and recompute its route below.
    for unit in cells["living-right"]["tour_features"]["hvac_units"]:
        unit["y_mm"] = 7500 + (core["core_y_mm"] - 7500) / 2
        unit["face"] = "right"
        route = unit["route"]
        route["polyline_mm"][0][1] = unit["y_mm"]
        route["estimated_routed_length_mm"] = sum(math.dist(a, b) for a, b in zip(
            route["polyline_mm"], route["polyline_mm"][1:])) + route["bend_service_allowance_mm"]


def b_products(building: dict) -> None:
    f1 = {c["key"]: c for c in building["floors"][0]["cells"] if c.get("tour_active")}
    set_product(f1["shrine"], "altar", [2440, 10920, 1800, 600], 0, "rear")
    set_product(f1["shrine"], "offering-table", [2740, 9025, 1200, 500], 0)
    set_product(f1["bath1"], "accessible-shower", [2480, 15950, 1200, 1200], 0, "rear")
    set_product(f1["bath1"], "toilet", [3540, 14000, 700, 450], 90, "right")
    set_product(f1["bath1"], "vanity", [2480, 13480, 600, 450], 180, "front")
    set_product(f1["storage"], "ceremonial-storage", [4560, 18600, 1200, 1700], 0)
    shower = next(i for i in f1["bath1"]["furniture"] if i["shape"] == "shower")
    shower["label"] = "120cm淋浴候選（照護／救援未核）"
    f1["bath1"]["tour_features"]["reserved_mm"].append(
        {"kind": "care-turn", "aabb": box(rect(2480, 14450, 1500, 1500)), "status": "not-rehearsed"})
    for i in f1["bath1"]["furniture"]:
        i["shared_operation_with"] = ["care-turn", "door-approach"]
        i["note"] += " Ø150cm地面暫留與開門／衛浴操作分時共用，不是無障礙或救援核可。"
    f2 = {c["key"]: c for c in building["floors"][1]["cells"] if c.get("tour_active")}
    set_product(f2["master2"], "bed", [3920, 18000, 2000, 1800], 90, "right")
    set_product(f2["master2"], "wardrobe", [2480, 17600, 600, 1800], 270, "left")
    set_product(f2["master2"], "vanity", [5420, 15500, 500, 1200], 90, "right")
    set_product(f2["master-bath2"], "shower", [3680, 11680, 900, 900], 180, "front")
    set_product(f2["master-bath2"], "vanity", [4950, 11680, 900, 550], 180, "front")
    set_product(f2["master-bath2"], "toilet", [5220, 13100, 700, 450], 90, "right")
    for index, key in ((1, "bath2"), (2, "bath3")):
        bath = next(c for c in building["floors"][index]["cells"] if c["key"] == key and c.get("tour_active"))
        for item in bath["furniture"]:
            item["shared_operation_with"] = ["door-approach"]
            item["note"] += " 濕區後移避整廳投影，改從左側公共道入內；洗手／如廁與進出分時，救援未核。"
        set_product(bath, "vanity", [1280, 11680, 600, 450], 180, "front")
        set_product(bath, "toilet", [2120, 12620, 450, 700], 0, "rear")
        set_product(bath, "shower", [2620, 12420, 900, 900], 0, "rear")


def refresh_stairs(building: dict, height: int, risers: int, core: dict) -> None:
    for index, floor in enumerate(building["floors"]):
        cell = next(c for c in floor["cells"] if c.get("tour_active") and c["kind"] == "stair")
        s = cell["tour_features"]["stair_geometry"]
        n = risers if index == 0 else 18
        s.update(risers=n, riser_mm=round(floor["height_mm"] / n, 2), run_mm=(n // 2 - 1) * 270,
                 middle_landing_mm=core["well_depth_mm"] - (n // 2 - 1) * 270 - (0 if core["shared_landing"] else 1000))
        if s["middle_landing_mm"] < 1000:
            raise ValueError("Sensitivity may not steal a landing")


def wall_strips(cell: dict) -> list[dict]:
    """Nominal 80mm discussion buffers along physical walls, not open grid seams."""
    if cell["is_outdoor"]:
        return []
    g, features = cell["tour_mm"], cell["tour_features"]
    strips = []
    for face in ("front", "rear", "left", "right"):
        along_x = face in {"front", "rear"}
        start, length = (g["x_mm"], g["w_mm"]) if along_x else (g["y_mm"], g["h_mm"])
        cuts = sorted((start + d["ratio"] * length - d["width_mm"] / 2,
                       start + d["ratio"] * length + d["width_mm"] / 2)
                      for d in features["doors"] + features["open_connections"] if d["face"] == face)
        cursor = start
        for lo, hi in [*cuts, (start + length, start + length)]:
            lo, hi = max(start, lo), min(start + length, hi)
            if lo > cursor + 1:
                if face == "front":
                    strips.append(box(rect(cursor, g["y_mm"], lo - cursor, 80)))
                elif face == "rear":
                    strips.append(box(rect(cursor, g["y_mm"] + g["h_mm"] - 80, lo - cursor, 80)))
                elif face == "left":
                    strips.append(box(rect(g["x_mm"], cursor, 80, lo - cursor)))
                else:
                    strips.append(box(rect(g["x_mm"] + g["w_mm"] - 80, cursor, 80, lo - cursor)))
            cursor = max(cursor, hi)
    return strips


def union_covers(bounds: dict, cells: list[dict]) -> bool:
    covered = sum(max(0, min(bounds["maxX"], box(r["tour_mm"])["maxX"]) - max(bounds["minX"], box(r["tour_mm"])["minX"])) *
                  max(0, min(bounds["maxY"], box(r["tour_mm"])["maxY"]) - max(bounds["minY"], box(r["tour_mm"])["minY"])) for r in cells)
    return abs(covered - (bounds["maxX"] - bounds["minX"]) * (bounds["maxY"] - bounds["minY"])) <= 1


def body_screen(building: dict) -> dict:
    """Whole-floor union, fixed bodies and physical wall support, not legal clearances."""
    failures, shared, pending, operation_limits = [], [], [], []
    for floor in building["floors"]:
        active = [c for c in floor["cells"] if c.get("tour_active")]
        if sum(area(c["tour_mm"]) for c in active) != round(floor["tour_width_mm"] * floor["tour_depth_mm"] / 1e6, 4):
            # Sum unrounded integer areas to avoid decimal presentation errors.
            if sum(c["tour_mm"]["w_mm"] * c["tour_mm"]["h_mm"] for c in active) != floor["tour_width_mm"] * floor["tour_depth_mm"]:
                raise ValueError("Comparison loses full floor coverage")
        objects = [(c, i, c["furniture_placements"]["tour_mm"][i["id"]]) for c in active for i in c["furniture"]]
        for c, item, p in objects:
            group = c.get("space_group")
            allowed = [r for r in active if r is c or group and r.get("space_group") == group]
            body = p["aabb"]
            if not union_covers(body, allowed):
                failures.append({"item": item["id"], "issue": "body-outside-physical-room-or-open-group"})
            local_issues = _issues(item, p, c["tour_mm"], c["tour_features"], [])
            actual_issues = sorted(set(p["issues"] + [i for i in local_issues if i not in {"overflow", "operation-space"}]))
            if actual_issues:
                pending.append({"item": item["id"], "issues": actual_issues})
            for bounds in [p.get("operation_mm"), p.get("rear_operation_mm"),
                           *[s["aabb"] for s in p.get("side_operation_mm", [])]]:
                if bounds and (not union_covers(bounds, allowed) or any(
                        overlaps(bounds, w) for r in allowed for w in wall_strips(r))):
                    operation_limits.append({"item": item["id"], "issue": "operation-outside-clear-room-or-group", "status": "unresolved"})
            if any(overlaps(body, w) for r in allowed for w in wall_strips(r)):
                failures.append({"item": item["id"], "issue": "body-in-discussion-wall-buffer"})
            for owner in active:
                for zone in owner["tour_features"].get("reserved_mm", []):
                    bounds = dict(zone["aabb"])
                    if zone["kind"] == "door-approach":
                        # An approach's +100mm drawing allowance may spill
                        # across a partition; it is not floor inside that wall.
                        owner_box = box(owner["tour_mm"])
                        bounds = {k: (max if k.startswith("min") else min)(v, owner_box[k]) for k, v in bounds.items()}
                    if overlaps(body, bounds) and item.get("mount_height_mm", 0) < 2100:
                        failures.append({"item": item["id"], "issue": "body-over-" + zone["kind"]})
                    if p.get("operation_mm") and overlaps(p["operation_mm"], bounds):
                        shared.append({"item": item["id"], "issue": "operation-shares-" + zone["kind"], "status": "not-verified-simultaneous-use"})
        for index, (c, i, p) in enumerate(objects):
            for d, j, q in objects[index + 1:]:
                z1, z2 = i.get("mount_height_mm", 0), j.get("mount_height_mm", 0)
                if overlaps(p["aabb"], q["aabb"]) and z1 < z2 + j["height_mm"] and z2 < z1 + i["height_mm"]:
                    failures.append({"items": [i["id"], j["id"]], "issue": "fixed-body-overlap"})
                for lhs, rhs, label in ((p.get("operation_mm"), q.get("operation_mm"), "operation-shared"),
                                         (p.get("operation_mm"), q["aabb"], "operation-vs-body"),
                                         (q.get("operation_mm"), p["aabb"], "operation-vs-body")):
                    if lhs and rhs and overlaps(lhs, rhs):
                        shared.append({"items": [i["id"], j["id"]], "issue": label, "status": "not-verified-simultaneous-use"})
    return {"status": "limited-coordinate-screen-not-professional-approval", "fixed_body_failures": failures,
            "pending_solver_items": pending, "operation_limits": operation_limits,
            "operation_sharing": shared, "full_human_door_sweeps": "unknown"}


def graph_path(floor: dict, start: str, target: str, excluded: set[str] | None = None) -> list[str]:
    rooms = {c["key"]: c for c in floor["cells"] if c.get("tour_active")}
    graph = {k: [d["neighbor"].split(":")[-1] for d in c["tour_features"]["doors"] + c["tour_features"]["open_connections"] if d["neighbor"] and not d.get("not_a_route_opening")]
             for k, c in rooms.items()}
    queue, seen = deque([[start]]), {start}
    while queue:
        path = queue.popleft()
        if path[-1] == target:
            return path
        for nxt in graph[path[-1]]:
            if nxt not in seen and nxt not in (excluded or set()):
                seen.add(nxt)
                queue.append([*path, nxt])
    return []


def requirement_areas(building: dict) -> list[dict]:
    mapping = {
        "B": {"floor-1.shrine": "floor-1:shrine", "floor-1.palanquin": "floor-1:storage",
              "floor-1.bath_acc": "floor-1:bath1", "floor-2.master_b": "floor-2:master2",
              "floor-2.master_bath": "floor-2:master-bath2", "floor-2.bath_g": "floor-2:bath2",
              "floor-3.bath_b3": "floor-3:bath3"},
        "C": {"floor-1.entry": "floor-1:entrance", "floor-1.kitchen": "floor-1:kitchen",
              "floor-1.elder": "floor-1:elder", "floor-1.elder_bath": "floor-1:elder-bath",
              "floor-2.bath_c2": "floor-2:bath2f", "floor-3.bath_c3": "floor-3:bath3f"},
    }
    requirements = {r["id"]: r for r in json.loads(model3d.REQUIREMENTS_FILE.read_text())["requirements"]}
    cells = {c["id"]: c for f in building["floors"] for c in f["cells"] if c.get("tour_active")}
    results = []
    for key, cell in mapping[building["id"]].items():
        rid, cid = building["id"] + "." + key, building["id"] + ":" + cell
        r, g = requirements[rid], cells[cid]["tour_mm"]
        size, minimum, target = area(g, 80), r["constraints"]["min_sqm"], r["constraints"]["target_sqm"]
        results.append({"id": rid, "title": r["title"], "room_id": cid,
                        "nominal_sqm": area(g), "discussion_inset_sqm": size,
                        "minimum_sqm": minimum, "target_sqm": target,
                        "minimum_state": "below-minimum" if size < minimum else "area-only-not-function-approval",
                        "target_state": "below-target" if size < target else "area-only-not-function-approval",
                        "source": "inputs/requirements.json", "finished_and_legal_area": None})
    return results


def transport_budget(building: dict) -> dict:
    """Unverified per-side buffers, separate from actual finished/transport proof."""
    cells = {c["key"]: c for c in building["floors"][0]["cells"] if c.get("tour_active")}
    physical = next(i for i in json.loads(model3d.PHYSICAL_ITEMS_FILE.read_text())["items"] if i["id"] == "B.palanquin.primary")
    target = physical["transport"]["door_clear_target_mm"]
    entry, storage = cells["entry"], cells["storage"]
    exterior = next(d for d in entry["tour_features"]["doors"] if d["neighbor"] is None)
    gate = next(d for d in storage["tour_features"]["doors"] if d.get("purpose") == "palanquin-storage")
    segments = []
    for key, nominal in [("entry-corridor", entry["tour_mm"]["w_mm"]),
                         ("rear-corridor", cells["corridor1"]["tour_mm"]["w_mm"]),
                         ("external-gate", exterior["width_mm"]), ("storage-gate", gate["width_mm"])]:
        segments.append({"id": key, "nominal_mm": nominal, "assumed_each_side_mm": 80,
                         "discussion_clear_mm": nominal - 160, "target_mm": target,
                         "target_state": "below-target" if nominal - 160 < target else "nominal-budget-only",
                         "finished_clear_mm": None})
    return {"status": "unverified-discussion-budget-not-transport-approval", "segments": segments,
            "target_source": {"path": "inputs/physical-items.json", "item_id": "B.palanquin.primary", "field": "transport.door_clear_target_mm"},
            "minimum_discussion_clear_mm": min(s["discussion_clear_mm"] for s in segments),
            "frame_product": "unknown", "columns_handles_tracks": "unknown", "people_poles_rehearsal": "unknown"}


def c_revision_screen(cells: dict) -> dict:
    def placement(key, local):
        return cells["C:floor-1:" + key]["furniture_placements"]["tour_mm"]["C:floor-1:" + key + ":furniture:" + local]
    wc, entry = cells["C:floor-1:public-bath"], cells["C:floor-1:entrance"]
    vanity, shoe = placement("public-bath", "vanity"), placement("entrance", "shoe-cabinet")
    wash_shares = any(overlaps(vanity["operation_mm"], z["aabb"]) for z in wc["tour_features"]["reserved_mm"] if z["kind"] == "door-approach")
    shoe_shares = any(overlaps(shoe["operation_mm"], z["aabb"]) for z in entry["tour_features"]["reserved_mm"] if z["kind"] == "door-approach")
    sofa, coffee = placement("living", "sofa"), placement("living", "coffee-table")
    gap = sofa["aabb"]["minX"] - coffee["aabb"]["maxX"]
    dining = cells["C:floor-1:dining"]
    dg, features = dining["tour_mm"], dining["tour_features"]
    door = next(d for d in features["doors"] if d["neighbor"] is None)
    separation = (dg["x_mm"] + door["ratio"] * dg["w_mm"] - door["width_mm"] / 2 -
                  (dg["x_mm"] + features["window_ratio"] * dg["w_mm"] + features["window_mm"] / 2))
    if wash_shares or shoe_shares or gap < 600 or separation < 300:
        raise ValueError("C v2 loses wash/shoe separation, sofa gap or window/door buffer")
    return {"status": "coordinate-only-not-human-or-finished-approval", "wash_shares_door_approach": wash_shares,
            "shoe_shares_door_approach": shoe_shares, "sofa_coffee_gap_mm": gap,
            "front_window_door_nominal_separation_mm": separation, "visitor_door_nominal_mm": wc["tour_features"]["doors"][0]["width_mm"],
            "toilet_entry_use": "sequential-not-verified", "chair_dining_use": "sequential-not-verified",
            "sliding_leaf_track_handle_and_rescue": "unknown"}


def bathroom_interfaces(cell: dict) -> dict:
    """Missing interfaces are questions, not a invented pipe or door product."""
    door = next(d for d in cell["tour_features"]["doors"] if d["neighbor"])
    return {"status": "pending-professional-detail", "door_nominal_mm": door["width_mm"],
            "finished_door_clear_mm": None, "door_leaf_track_handle_and_rescue": "unknown",
            "proposed_external_window": bool(cell["tour_features"]["window_mm"]),
            "effective_ventilation": "unknown", "independent_exhaust_outlet_and_makeup_air": "unknown",
            "drain_vent_riser_maintenance": "unknown", "waterproofing_slope_condensation": "unknown",
            "full_turn_and_fallen_person_rehearsal": "unknown",
            "exhaust_into_shrine_network_or_palanquin_storage_allowed": False}


def program_screen(building: dict, option: dict, screen: dict) -> dict:
    cells = {c["id"]: c for f in building["floors"] for c in f["cells"] if c.get("tour_active")}
    if building["id"] == "C":
        public = sum(area(c["tour_mm"]) for c in cells.values() if c["id"].startswith("C:floor-1:") and c["key"] in {"dining", "living", "living-hall", "living-right"})
        elder = cells["C:floor-1:elder"]
        bed = next(p for iid, p in elder["furniture_placements"]["tour_mm"].items() if iid.endswith(":bed"))
        wet = [c["id"] for c in cells.values() if not c["id"].startswith("C:floor-1:") and c["kind"] in {"bath", "kitchen"} and overlaps(box(c["tour_mm"]), bed["aabb"])]
        route = graph_path(building["floors"][0], "dining", "public-bath", {"elder", "elder-bath"})
        if wet or not route:
            raise ValueError("C loses the agreed bed/visitor separation")
        return {"living_dining_nominal_sqm": round(public, 4), "old_living_dining_nominal_sqm": 27.2,
                "kitchen_discussion_inset_sqm": area(cells["C:floor-1:kitchen"]["tour_mm"], 80),
                "entry_discussion_inset_sqm": area(cells["C:floor-1:entrance"]["tour_mm"], 80),
                "visitor_route": route, "route_proof": "door-graph-only-not-clearance-proof", "wet_rooms_over_bed": wet,
                "revision_checks": c_revision_screen(cells),
                "public_wc_interfaces": bathroom_interfaces(cells["C:floor-1:public-bath"]),
                "public_wc_has_proposed_front_window": True, "ventilation_effective_area": None,
                "unaccommodated": ["原兩車＋機車", "孝親套衛完整轉位／救援", "公衛有效排氣／補氣及防水", "玄關6.5m²原目標"]}
    shrine = cells["B:floor-1:shrine"]
    altar = next(p for iid, p in shrine["furniture_placements"]["tour_mm"].items() if iid.endswith(":altar"))
    shrine_back = shrine["tour_mm"]["y_mm"] + shrine["tour_mm"]["h_mm"]
    axis = {"minX": altar["aabb"]["minX"], "maxX": altar["aabb"]["maxX"], "minY": shrine_back, "maxY": building["floors"][0]["tour_depth_mm"]}
    forbidden = [c["id"] for c in cells.values() if c["id"].startswith("B:floor-1:") and
                 (c["kind"] == "stair" or c.get("space_role") == "circulation") and overlaps(box(c["tour_mm"]), axis)]
    above_sleep = [c["id"] for c in cells.values() if not c["id"].startswith("B:floor-1:") and
                   (c["kind"] == "bedroom" or any(i["shape"] in {"bed", "sofa-bed"} for i in c["furniture"])) and overlaps(box(c["tour_mm"]), box(shrine["tour_mm"]))]
    door = next(d for d in shrine["tour_features"]["doors"] if d.get("purpose") == "ritual-entry")
    axial = abs(shrine["tour_mm"]["x_mm"] + door["ratio"] * shrine["tour_mm"]["w_mm"] - altar["center_x_mm"]) < 1
    above_wet = [c["id"] for c in cells.values() if not c["id"].startswith("B:floor-1:") and
                 c["kind"] in {"bath", "kitchen"} and overlaps(box(c["tour_mm"]), box(shrine["tour_mm"]))]
    backing = box(cells["B:floor-1:altar-backing"]["tour_mm"])
    dry_back = backing["minY"] == shrine_back and backing["minX"] <= axis["minX"] and backing["maxX"] >= axis["maxX"]
    budget = transport_budget(building)
    if option["id"].startswith("b-program") and (area(shrine["tour_mm"], 80) < 22 or any(s["target_state"] == "below-target" for s in budget["segments"])):
        raise ValueError("B v2 loses the shrine minimum or discussion transport budget")
    if forbidden or above_sleep or above_wet or not axial or not dry_back:
        raise ValueError("B violates the confirmed family rules")
    storage, master, mbath = [cells[p] for p in ("B:floor-1:storage", "B:floor-2:master2", "B:floor-2:master-bath2")]
    route = graph_path(building["floors"][0], "entry", "storage", {"shrine"})
    public = graph_path(building["floors"][0], "public-entry", "stair1", {"shrine", "storage", "altar-backing", "bath1", "idf-cabinet"})
    return {"street_facing_axial_door": axial, "stair_or_hall_behind_altar": forbidden,
            "sleep_above_whole_shrine": above_sleep,
            "wet_above_whole_shrine": above_wet, "dry_altar_backing": dry_back,
            "storage_discussion_inset_sqm": area(storage["tour_mm"], 80),
            "master_discussion_inset_sqm": area(master["tour_mm"], 80), "master_target_sqm": 20,
            "master_bath_discussion_inset_sqm": area(mbath["tour_mm"], 80), "master_bath_target_sqm": 6,
            "first_floor_shower_body_present": any(i["shape"] == "shower" for i in cells["B:floor-1:bath1"]["furniture"]),
            "first_floor_bath_interfaces": bathroom_interfaces(cells["B:floor-1:bath1"]),
            "carry_route": route, "public_stair_route": public,
            "transport": {"status": "storage-body-candidate-only", "assembled_envelope_measured": False, "full_people_poles_and_rain_rehearsal": "unknown", "clearance_budget": budget},
            "unaccommodated": ["原一車位", "KTV／茶水（跨棟未驗證）", "原1F洗衣工作陽台", "武轎裝桿與搬運演練", "衛浴轉位／救援"]}


def isolate(payload: dict, building: dict, option: dict, review: dict, tradeoffs: list) -> dict:
    result = copy.deepcopy(payload)
    result["buildings"] = [copy.deepcopy(building)]
    result["facade"]["buildings"] = [b for b in result["facade"]["buildings"] if b["id"] == building["id"]]
    result["compare"] = {"available": False}
    result["layout_review"].pop("mdf_study", None)
    result["layout_review"].pop("fengshui_minimal", None)
    result["layout_review"]["status"] = STATUS
    result["layout_review"]["checks"] = []
    result["layout_review"]["hvac_routes"] = [r for r in result["layout_review"]["hvac_routes"] if r["id"].startswith(building["id"] + "-")]
    result["bc_option"] = {"id": option["id"], "label": option["label"], "revision": 2, "status": STATUS, "tradeoffs": tradeoffs, "geometry_review": review}
    result["source"]["preparation_review"] = "inputs/preparation-review.json"
    result["geom_source_default"] = "tour"
    items = [i for f in building["floors"] for c in f["cells"] if c.get("tour_active") for i in c["furniture"]]
    result["furniture"]["items"] = len(items)
    result["furniture"]["rooms"] = sum(bool(c["furniture"]) for f in building["floors"] for c in f["cells"] if c.get("tour_active"))
    result["furniture"]["basis_counts"] = {k: sum(i["basis"] == k for i in items) for k in result["furniture"]["basis_counts"]}
    result["overlaps"] = {k: [v for v in rows if v.get("building") == building["id"]] for k, rows in result["overlaps"].items()}
    historical = [c for f in building["floors"] for c in f["cells"] if not c.get("proposal_only")]
    counts = {level: sum(c["provenance"] == level for c in historical) for level in ("auto", "declared", "measured")}
    result["provenance"] = {"cells": counts, "total": len(historical),
                            "auto_pct": round(counts["auto"] / len(historical) * 100, 1),
                            "note": "僅此棟歷史來源格位；新比較坐標均為未核提案，非實測。"}
    result["source"]["preparation_generator"] = "scripts/export_preparation_review.py"
    for f in result["buildings"][0]["floors"]:
        for c in f["cells"]:
            if c.get("tour_active") and not c.get("proposal_only"):
                if c.get("size_text"):
                    c["size_text"] = "原HTML歷史標示：" + c["size_text"] + "（非本比較尺寸）"
                c["badges"] = ["原HTML提及／本比較未核：" + b for b in c["badges"]]
    return result


def build_study() -> dict:
    settings = json.loads(SOURCE.read_text())
    if settings.get("revision") != 2:
        raise ValueError("Unsupported revision requires a coordinated redraw")
    if settings["status"] != STATUS or settings["active_design"] != "baseline" or set(settings["professional_status"].values()) != {"unknown"}:
        raise ValueError("Preparatory comparisons may not be adopted or professionally approved")
    if settings["c_frame_mm"] != [6000, 17630] or settings["b_conditional_frame_mm"] != [6000, 20530] or settings["frontage_depth_mm"] != 3900:
        raise ValueError("Changed frame/front strip requires an explicit coordinated redraw, not ignored settings")
    old_manifest = json.loads((OUT / "bc-options/layout.js").read_text().split(" = ", 1)[1].rstrip(";\n"))
    # Refuse stale geometry references, rather than silently treating them as current.
    for rel, sha in old_manifest["source_hashes"].items():
        if digest(ROOT / rel) != sha:
            raise ValueError("Stale B/C comparison reference: " + rel)
    options = []
    program = json.loads(model3d.PROGRAM_FILE.read_text())
    for spec in settings["options"]:
        raw, furniture, old = source_review()
        case = next(c for c in settings["height_cases"] if c["height_mm"] == spec["height_mm"])
        if spec["id"].startswith("b-fixed"):
            raw["buildings"]["B"] = copy.deepcopy(next(o for o in old["options"] if o["id"] == "b-strict")["patch"]["replace_building"])
            core = None
        else:
            core = (c_proposal if spec["building"] == "C" else b_proposal)(raw, furniture, old, spec["height_mm"], case["risers"])
        raw["buildings"]["B"].pop("ritual_access", None)
        payload = model3d.build_payload(program, load_overrides(), model3d.default_drawing_style(),
                                       review_data=raw, furniture_data=furniture, validate_a_arcade=False)
        building = next(b for b in payload["buildings"] if b["id"] == spec["building"])
        if core:
            refresh_stairs(building, spec["height_mm"], case["risers"], core)
            (c_products(building, core) if spec["building"] == "C" else b_products(building))
        # Refresh facade after the final same-source product/window/core changes.
        payload["facade"] = build_facade(payload["buildings"], payload["standards"])
        screen = body_screen(building)
        if screen["fixed_body_failures"] or screen["pending_solver_items"] or screen["operation_limits"] or any(
                r["issue"] == "operation-vs-body" for r in screen["operation_sharing"]):
            raise ValueError("Resolve coordinate defects before publishing this comparison: " + spec["id"])
        brief = program_screen(building, spec, screen)
        brief["area_checks"] = requirement_areas(building)
        brief["unaccommodated"] += [r["title"] + "面積仍低於原目標" for r in brief["area_checks"] if r["target_state"] == "below-target"]
        p = next(b for b in plan_data(payload)["buildings"] if b["id"] == spec["building"])
        for floor in p["floors"]:
            floor["plan_file"] = spec["id"] + "_" + floor["id"] + ".svg"
        frame = [p["floors"][0]["width_mm"], p["floors"][0]["depth_mm"]]
        tradeoffs = [
            f"固定比較框 {frame[0]/1000:g}×{frame[1]/1000:g}m；名義基地 {frame[0]*frame[1]/1e6/3.305785:.2f}坪，非地籍／可建面積。",
            "每邊80mm只供家具與面積討論，完成面、結構、法規、照護、風水與造價均未核。",
            "未採用；切換比較不改ABC主案。操作共享、原需求缺口與實物演練保持可見。",
        ]
        if spec["building"] == "C":
            tradeoffs += [f"客餐名義 {brief['living_dining_nominal_sqm']:.3f}m²（原27.2）；樓高敏感度擴梯井後不可重複計回公共區。",
                          "v2：沙發前留60cm，90cm可移單椅回同側、面餐區；不是4～6人會客或旋轉擺位已核。120cm客餐照護帶不含門框淨寬。",
                          "v2：洗手／鞋櫃操作移離公衛門前；馬桶進出及餐椅起身仍分時。90cm名義公衛滑門的實際門片、軌道、把手與救援待核。",
                          "入口經餐廳；餐窗／主門名義間距改30cm，60×50cm高窗尚未產品／結構核定；獨立排氣補氣與防雨、防水須專業設計。"]
        else:
            budget = brief["transport"]["clearance_budget"]
            tradeoffs += [f"主臥討論內縮 {brief['master_discussion_inset_sqm']:.4f}m²／原20m²目標；1F淋浴是否有實際產品分開列。",
                          f"搬轎最窄討論預算 {budget['minimum_discussion_clear_mm']}mm：牆側／門框每側80mm為未核假設，不是完成面或裝桿搬運通過。",
                          "B擴框只是條件式容量例子，不是32坪已放得下、最小基地或已核准增加土地。"]
            if spec["id"].startswith("b-program"):
                tradeoffs += ["v2：168cm名義通道、166cm名義搬轎門；按每側80mm暫扣為152cm通道／150cm門，門框／柱位／軌道／門片及人員餘量仍未核。",
                              "v2：神明堂改312×770cm，背牆及全層濕區後移20cm；2F／3F公衛改由左公共道進入，仍只3.6736m²討論面積（原5m²）。",
                              "1F保留120cm淋浴候選，106cm名義滑門；排氣補氣、防水、倒地救援及門片開啟未核，不稱為無障礙通過。"]
        tradeoffs += brief["unaccommodated"]
        review = {"program": brief, "coordinate_screen": screen, "professional_status": settings["professional_status"]}
        options.append({**spec, "status": STATUS, "frame_mm": frame, "plans": p, "review": review,
                         "tradeoffs": tradeoffs, "model": isolate(payload, building, spec, review, tradeoffs)})
    files = [SOURCE, SCENARIOS, model3d.REVIEW_FILE, model3d.FURNITURE_FILE, model3d.PROGRAM_FILE,
             model3d.REQUIREMENTS_FILE, model3d.PHYSICAL_ITEMS_FILE, model3d.FACADE_FILE,
             ROOT / "inputs/dimensions.json", ROOT / "inputs/bc-constraints-options.json",
             ROOT / "inputs/c1f-window-moisture-brief.json", OUT / "bc-options/layout.js", Path(__file__),
             ROOT / "scripts/templates/model3d.html", ROOT / "scripts/templates/model3d_facade.js",
             ROOT / "scripts/templates/bc-options-bootstrap.js", ROOT / "scripts/templates/bc-options-controls.html",
             ROOT / "scripts/templates/preparation-review.html", ROOT / "scripts/check_preparation_playwright.cjs", model3d.THREE_FILE,
             ROOT / "Docs/abc-preparation-review-v2.md",
             ROOT / "scripts/export_model_3d.py", ROOT / "scripts/config/residential_defaults_tw.json",
             *sorted((ROOT / "house_design/rendering").glob("*.py")),
             *sorted((ROOT / "scripts/lib").glob("*.py"))]
    return {**settings, "options": options, "source_hashes": {str(p.relative_to(ROOT)): digest(p) for p in files},
            "protected_main_hashes": {p: digest(ROOT / p) for p in PROTECTED}}


def render_svg(option: dict, floor: dict) -> str:
    raw = render_plan(option["building"], floor, viewer_url="../preparation-review-3d.html?scheme=" + option["id"])
    tree = ET.fromstring(raw)
    tree.set("data-study-status", STATUS)
    tree.set("data-study-option", option["id"])
    ET.SubElement(tree, "{" + NS + "}text", {"x": "0", "y": "-820", "font-size": "185", "fill": "#8a4b10"}).text = "比較案未採用；尺寸初篩不是專業核定。"
    if option["building"] == "C" and floor["id"] == "floor-1":
        g = ET.SubElement(tree, "{" + NS + "}g", {"data-moisture-note": "unverified"})
        ET.SubElement(g, "{" + NS + "}text", {"x": "4200", "y": "4350", "font-size": "130"}).text = "可開高窗／排氣待核"
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(tree, encoding="unicode") + "\n"


def sensitivity(study: dict) -> list:
    rows = []
    for option in study["options"]:
        stair = next(r for r in option["plans"]["floors"][0]["rooms"] if r["kind"] == "stair")
        s, g = stair["features"]["stair_geometry"], stair["geometry"]
        rows.append({"option": option["id"], "building": option["building"], "height_mm": option["height_mm"],
                     "risers": s["risers"], "riser_mm": s["riser_mm"], "parallel_flight_run_mm": s["run_mm"],
                     "well_depth_mm": stair["features"]["stair_footprint_mm"]["h_mm"], "core_front_y_mm": g["y_mm"],
                     "level_bases_mm": [f["base_mm"] for f in option["plans"]["floors"]],
                     "legal_arcade_height": None, "beam_and_stair_headroom": None,
                     "living_dining_nominal_sqm": option["review"]["program"].get("living_dining_nominal_sqm"),
                     "master_discussion_inset_sqm": option["review"]["program"].get("master_discussion_inset_sqm")})
    return rows


def render_index(study: dict) -> str:
    sections = []
    for option in study["options"]:
        links = []
        for f in option["plans"]["floors"]:
            url = f'preparation-review-3d.html?scheme={option["id"]}#mode=tour&building={option["building"]}&floor={f["id"]}&view=plan'
            links.append(f'<li><a href="preparation-review/{f["plan_file"]}">{html.escape(f["label"])} SVG</a> · <a href="{html.escape(url)}">同源3D</a></li>')
        areas = "".join(f'<tr><td>{html.escape(r["title"])}</td><td>{r["discussion_inset_sqm"]:.4f}</td><td>{r["minimum_sqm"]}／{r["target_sqm"]}</td><td>{"未達目標" if r["target_state"] == "below-target" else "僅面積數值達標，功能未核"}</td></tr>' for r in option["review"]["program"]["area_checks"])
        brief = option["review"]["program"]
        if option["building"] == "B":
            budget = brief["transport"]["clearance_budget"]
            names = {"entry-corridor": "前搬轎通道", "rear-corridor": "後搬轎通道", "external-gate": "搬轎外門", "storage-gate": "武轎收納門"}
            rows = "".join(f'<tr><td>{names[s["id"]]}</td><td>{s["nominal_mm"]}</td><td>{s["assumed_each_side_mm"]}</td><td>{s["discussion_clear_mm"]}</td><td>{s["target_mm"]}</td><td>{"低於目標" if s["target_state"] == "below-target" else "僅討論預算達標；完成面未核"}</td></tr>' for s in budget["segments"])
            revision = '<div class="scroll" data-clearance-budget><table><thead><tr><th>搬轎段落</th><th>名義mm</th><th>每側暫扣mm</th><th>討論餘寬mm</th><th>原目標mm</th><th>結果</th></tr></thead><tbody>'+rows+'</tbody></table></div><p>牆與門框扣除不是實測；門柱、軌道、把手、輪具、裝桿與人員未核。名義洞寬不等於淨開口。</p>'
        else:
            r = brief["revision_checks"]
            revision = f'<p data-revision-checks>v2坐標初篩：沙發／茶几間距 {r["sofa_coffee_gap_mm"]:g}mm；餐窗／主門名義間距 {r["front_window_door_nominal_separation_mm"]:g}mm；公衛滑門名義 {r["visitor_door_nominal_mm"]}mm。洗手及鞋櫃操作不重疊公衛門前暫留帶，但如廁／進出與餐椅起身仍分時，救援及完整門片未核。</p>'
        sections.append(f'<section id="{option["id"]}" data-option="{option["id"]}"><h2>{html.escape(option["label"])}</h2><p class="warning">比較未採用／專業未核</p><ul>'+"".join('<li>'+html.escape(t)+'</li>' for t in option["tradeoffs"])+
                        '</ul>'+revision+'<div class="scroll"><table><thead><tr><th>原需求</th><th>80mm討論內縮 m²</th><th>下限／目標 m²</th><th>結果（非核定）</th></tr></thead><tbody>'+areas+'</tbody></table></div><p>80mm不是確定牆厚；客餐為共用空間，不把通行與轉位再算成獨立淨空。</p><ul>'+"".join(links)+
                        f'</ul><p><a href="preparation-review/{option["id"]}_front.svg">同源前立面</a></p><object type="image/svg+xml" data="preparation-review/{option["plans"]["floors"][0]["plan_file"]}" aria-label="一樓同源比較圖"></object><details><summary>需求缺口、座標檢查與操作共享</summary><pre>'+html.escape(json.dumps(option["review"],ensure_ascii=False,indent=2))+'</pre></details></section>')
    template = (ROOT / "scripts/templates/preparation-review.html").read_text()
    rows = "".join(f'<tr><td>{r["option"]}</td><td>{r["height_mm"]/1000:g}</td><td>{r["well_depth_mm"]}</td><td>{r["living_dining_nominal_sqm"] or "—"}</td><td>{r["master_discussion_inset_sqm"] or "—"}</td></tr>' for r in sensitivity(study))
    table = '<div class="scroll"><table><thead><tr><th>比較案</th><th>1F樓高m</th><th>梯井深mm</th><th>C客餐名義m²</th><th>B主臥討論m²</th></tr></thead><tbody>'+rows+'</tbody></table></div>'
    return template.replace("__OPTIONS__", "\n".join(sections)).replace("__HEIGHTS__", table)


def meeting_packet(study: dict, cases: dict) -> str:
    rows = "".join(f'<tr><td>{html.escape(r["building"])}</td><td>{html.escape(r["scenario"])}</td><td>{html.escape(r["expectation"])}</td><td>{html.escape(r["evidence_needed"])}</td><td>未知／待演練</td></tr>' for r in cases["scenarios"])
    questions = [
        ("建築師／地政", "逐筆面寬深、建築線、騎樓、退縮、建蔽容積、申照方式與可建面積？", "正式逐筆圖件、書面認定與來源"),
        ("建築師／結構", "一樓騎樓梁下條件與3m/3.6m/4m敏感度，梯井、扶手、淨高與全部標高怎樣聯動？", "套繪剖面及法規適用依據"),
        ("建築師／室內設計", "C有窗公衛的移門移窗、鞋櫃、原尺寸家具與照護動線是否成立？", "完成面門窗／家具操作圖與現場演練"),
        ("建築師／門窗／搬運", "v2 B通道168cm、搬轎門166cm各暫扣每側8cm後是否仍保住150cm淨開口？門柱、軌道、把手與裝桿人員餘量如何核？", "門框／門片實物及完成面套繪，不以名義洞寬當淨寬"),
        ("室內設計／照護", "v2 C沙發前60cm、單椅與餐椅分時、公衛名義90cm滑門；門片開啟和倒地救援是否仍需再重排？", "桌椅、門片、輪具與真人演練；有窗不等於防黴"),
        ("屋主／建築師", "v2 B神明堂22.3184m²、1F衛浴6.4592m²、2F／3F公衛3.6736m²仍低於原目標；完成面加入後怎樣保住下限？", "保留原目標的面積帳與替代配置，不藉修搬轎默刪衛浴需求"),
        ("建築師／機電", "C高窗與獨立排氣／補氣、B1F淋浴的立管、通氣、合法出口、防水與檢修如何設計？上下濕區不完全同軸，如何避梁／神明堂接管？", "管道／梁圖、風量及防水詳圖"),
        ("祭祀顧問／家人", "B朝街同軸門、真正乾式背牆與整廳上方不睡的安排是否被家中接受？", "家規書面記錄與座向現勘，不靠模型簽證"),
        ("搬運／實物", "武轎拆桿、裝桿外廓、重量、輪具、人員與雨天搬運如何安排？", "收納與組裝兩組尺寸、實物演練"),
        ("照護／室內設計", "ABC夜間如廁、轉位、淋浴、倒地救援與大型家具換機怎樣驗證？", "完整產品、輪具與操作演練"),
        ("屋主／建築師", "B條件式37.3坪擴框例子或固定32坪重排的取捨？原車位、KTV與1F洗衣需求如何保留？", "不默改32坪目標；可行性、估價與候選基地比較"),
    ]
    qa = "".join(f'<tr><td>{html.escape(a)}</td><td>{html.escape(q)}</td><td>{html.escape(e)}</td><td class="answer">待回覆：<br><br>來源／日期：</td></tr>' for a,q,e in questions)
    sr = "".join(f'<tr><td>{r["option"]}</td><td>{r["height_mm"]}</td><td>{r["risers"]}</td><td>{r["parallel_flight_run_mm"]}</td><td>{r["well_depth_mm"]}</td><td>{r["level_bases_mm"]}</td><td>未知</td></tr>' for r in sensitivity(study))
    sources = "".join('<li>'+html.escape(p)+': <code>'+sha+'</code></li>' for p,sha in study["source_hashes"].items())
    return '<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ABC前期設計會談補充包（未採用）</title><style>body{font:16px/1.65 system-ui,sans-serif;color:#243c48;background:#f5f3ed;margin:0}main{max-width:1160px;margin:auto;padding:24px}section{background:white;padding:20px;margin:18px 0;border:1px solid #d1d8d3;border-radius:8px}a{color:#166974}h1{font-size:26px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #bcc9c7;padding:10px;vertical-align:top}.scroll{overflow:auto}.warning{background:#fff1d6;padding:14px;border-left:4px solid #a77520}.answer{min-width:180px}code,li{overflow-wrap:anywhere}@media print{body{background:white}main{padding:0}section{break-inside:auto}.scroll{overflow:visible}a{color:inherit}}@media(max-width:600px){main{padding:12px}section{padding:12px}table{min-width:780px}}</style><main><h1>ABC前期設計會談補充包</h1><p class="warning">土地未選定；比較未採用，不是建築／裝潢施工圖、法規／宗教或照護簽證。未知不算通過。本包不取代R000封存或R001正式交付。</p><nav><a href="../candidates/preparation-review.html">新比較圖與3D</a> · <a href="../candidates/model3d.html">原ABC主案</a> · <a href="../../Docs/proposal-screening-v1.md">屋主決定／原需求缺口</a></nav><section><h2>會談目的與已確認條件</h2><p>B維持朝街同軸祭祀門、背後無梯間、整間神明堂上方不睡眠、主臥20m²原目標；武轎、1F淋浴優先，KTV保留另案研究。C訪客不穿孝親房、公衛有外窗優先，客餐保持開放、側牆床避上層濕區投影，原床／淋浴／鞋櫃不縮。公共面積與移門移窗尚未採用。</p></section><section><h2>一樓樓高／梯井敏感度（僅算術與幾何）</h2><div class="scroll"><table><thead><tr><th>方案</th><th>1F樓高mm</th><th>級數</th><th>並排單跑深mm</th><th>梯井深mm</th><th>各層底標高mm</th><th>專業判定</th></tr></thead><tbody>'+sr+'</tbody></table></div><p>梁下淨高不等於樓高；級數、平台與梯井是研究假設，C較高梯井會占公共區。B擴框不是最小基地或32坪通過。法定面積／騎樓適用仍未知。</p></section><section><h2>需帶回可追溯回答的問題</h2><div class="scroll"><table><thead><tr><th>負責討論</th><th>問題</th><th>所需證據</th><th>會議記錄</th></tr></thead><tbody>'+qa+'</tbody></table></div></section><section><h2>ABC日常／特殊使用情境</h2><p>下列全為待核／待演練。模型坐標檢查不能代替實物操作；輪椅、門扇、雨天與救援需真人／產品外廓。</p><div class="scroll"><table><thead><tr><th>棟</th><th>情境</th><th>要保住的功能</th><th>缺的證據</th><th>狀態</th></tr></thead><tbody>'+rows+'</tbody></table></div></section><section><h2>下一步採用門檻</h2><p>圖面與3D同源→家具／門／設備操作檢查→Windows互動與目視→屋主同意取捨→建築師按基地／完成面及機電套繪。本輪只完成前期資料，不把檔案／自動測試當專業審查。預算與造價仍待設計範圍和估價，未提供無來源金額。</p></section><section><h2>資料版本與來源</h2><details><summary>展開SHA-256來源清單</summary><ul>'+sources+'</ul></details></section></main></html>\n'


def main() -> None:
    before = {p: digest(ROOT / p) for p in PROTECTED}
    study = build_study()
    folder = OUT / "preparation-review"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {**study, "options": [{k:v for k,v in o.items() if k != "model"} for o in study["options"]]}
    (folder / "layout.js").write_text("window.HOUSE_PREPARATION_REVIEW = " + encode_html_json(manifest) + ";\n")
    for option in study["options"]:
        for floor in option["plans"]["floors"]:
            (folder / floor["plan_file"]).write_text(render_svg(option, floor))
        facade = option["model"]["facade"]
        (folder / (option["id"] + "_front.svg")).write_text(render_elevation(facade, facade["buildings"][0]))
    (OUT / "preparation-review.html").write_text(render_index(study))
    controls = (ROOT / "scripts/templates/bc-options-controls.html").read_text().replace("bc-options.html", "preparation-review.html").replace("B 家規／C 照護", "ABC前期整合").replace("B／C比較", "前期整合比較")
    bootstrap = (ROOT / "scripts/templates/bc-options-bootstrap.js").read_text().replace("bc-options.html", "preparation-review.html").replace("B 家規／C 照護", "ABC前期整合").replace('"bc-constraints"', '"preparation-review"')
    data = {"bc_options": {"default_option": study["default_option"], "options": [
        {"id": o["id"], "label": o["label"], "building": o["building"], "model": o["model"]} for o in study["options"]]}}
    viewer = model3d.render_html(data, model3d.three_source()[0], study_controls=controls, study_bootstrap=bootstrap)
    viewer = viewer.replace('htmlHref="bc-options.html#"', 'htmlHref="preparation-review.html#"')
    viewer = viewer.replace('ABC v2 固定比較框提案（非地籍或可建容量）', '前期整合比較框（未採用；非地籍或可建容量）')
    viewer = viewer.replace('row("標示面積",', 'row("原HTML歷史面積（非本比較）",')
    (OUT / "preparation-review-3d.html").write_text(viewer)
    meeting = ROOT / "structured/discussions"
    meeting.mkdir(parents=True, exist_ok=True)
    cases = json.loads(SCENARIOS.read_text())
    (meeting / "abc-preparation-meeting.html").write_text(meeting_packet(study, cases))
    (meeting / "abc-preparation-meeting.json").write_text(json.dumps({"schema":"house-preparation-meeting-v1", "revision":study["revision"], "status":STATUS,
        "source_hashes":study["source_hashes"], "sensitivity":sensitivity(study), "scenarios":cases["scenarios"],
        "professional_approval":"unknown", "active_design":"baseline"}, ensure_ascii=False, indent=2) + "\n")
    if {p: digest(ROOT / p) for p in PROTECTED} != before:
        raise RuntimeError("An existing source/main/archive changed during generation")
    for option in study["options"]:
        review = option["review"]
        print(option["id"], "fixed-body findings:", len(review["coordinate_screen"]["fixed_body_failures"]),
              "pending solver items:", len(review["coordinate_screen"]["pending_solver_items"]))
    print("Written seven isolated comparisons and ABC meeting supplement; main drawings unchanged, no adoption/approval.")


if __name__ == "__main__":
    main()

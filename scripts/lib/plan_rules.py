#!/usr/bin/env python3
"""Rule checks over generated parametric plans.

These are not generic "good design" heuristics. Each one answers a question
that is already written down in ``inputs/design_request.md`` - mostly the twelve
questions in section 7 - so that a finding can be traced back to the sentence
that asked for it.

The checks run on the circulation graph (rooms as nodes, doors as edges) plus
plain rectangle geometry. Nothing here modifies the plan: a room that cannot be
reached without walking through a bedroom is reported, not quietly re-plumbed,
because that is the answer the user needs before the architect starts.
"""

from __future__ import annotations

import collections
from typing import Any, Iterable

from .plan_geometry import Rect, garage_min_bay_mm

EYE_MM = 1500  # sight-line height for the "does it face the dining table" test

CODES = {
    "CAPACITY_OVERFLOW": "該層需求超過可用面積",
    "WHEELCHAIR_TURN": "輪椅迴轉圈放不下",
    "DOOR_CLEAR_WIDTH": "門淨寬不足",
    "BATH_FACES_DINING": "廁所門正對餐廳",
    "KITCHEN_TO_BALCONY": "廚房到後陽台必須穿越臥室",
    "FRONT_REAR_ALIGNED": "大門與後陽台對穿（穿堂煞）",
    "PALANQUIN_PATH": "武轎搬運路徑淨寬不足",
    "PENTHOUSE_OVER_LIMIT": "屋頂突出物水平投影面積之和超過上限（12.5%，未達 25 m² 者為 25 m²）",
    "NO_DAYLIGHT": "需採光的房間沒有外牆",
    "GARAGE_NOT_PARKABLE": "車庫放不下一台休旅車＋充電樁",
    "GARAGE_FEWER_BAYS": "車庫寬度放不下要求的車位數",
    "GARAGE_DOOR_NARROW": "臨路面寬做不出足夠的車庫門",
    "ACCESS_UNREALISABLE": "需求指定的出入關係在這個配置下做不到",
    "NESTED_ACCESS": "唯一入口要穿越私密空間",
    "NO_ACCESS": "沒有任何可開門的共用牆",
    "BAND_UNREALISABLE": "需求指定的前後分帶沒有做到",
    "BALCONY_NOT_ON_FACADE": "後陽台沒有貼到後外牆",
    "OUTDOOR_LANDLOCKED": "戶外空間四面都是室內，沒有任何外牆",
    "SHRINE_STACK": "神明廳正上方是衛浴或廚房",
}

ROOF_CLASS_LABEL = {
    "enclosed": "梯間／機械房",
    "tank": "水塔",
    "open_mep": "露天機電",
    "energy": "節能設施",
}

SEVERITY = {
    "CAPACITY_OVERFLOW": "error",
    "WHEELCHAIR_TURN": "error",
    "DOOR_CLEAR_WIDTH": "error",
    "PENTHOUSE_OVER_LIMIT": "error",
    "GARAGE_NOT_PARKABLE": "error",
    "NO_ACCESS": "error",
    # Raised from warning: 武轎 is the reason B has a dedicated store room at
    # all. A route it cannot pass through is not a note, it is the room failing
    # to do its one job.
    "PALANQUIN_PATH": "error",
    "ACCESS_UNREALISABLE": "error",
    # A balcony with no exterior wall has no drying, no drainage to outside and
    # no air. It is a windowless interior room that the report was still calling
    # 後工作陽台, which is the kind of thing this model exists to stop.
    "OUTDOOR_LANDLOCKED": "error",
    # design_request.md 第 340 行 lists 「2F 衛浴／排水管不要壓到神桌」 as 必做 and
    # calls it 「B 棟風水最大紅線之一」. The plan assumed the fixed stacked core made
    # this structurally impossible; it does not - only core wet areas stack, and
    # 3F 衛浴 / 2F 客用衛浴 are placed by the guillotine split like any other room.
    "SHRINE_STACK": "error",
    "KITCHEN_TO_BALCONY": "warning",
    "BAND_UNREALISABLE": "warning",
    "BALCONY_NOT_ON_FACADE": "warning",
    "GARAGE_DOOR_NARROW": "warning",
    "NESTED_ACCESS": "warning",
    "NO_DAYLIGHT": "warning",
    "GARAGE_FEWER_BAYS": "warning",
    "EQUIP_ACCESS_TIGHT": "warning",
    "PENTHOUSE_UNCLASSIFIED": "warning",
    "BATH_FACES_DINING": "note",
    "FRONT_REAR_ALIGNED": "note",
}


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------


def _segment_hits_box(p: tuple[float, float], q: tuple[float, float],
                      box: list[int]) -> float | None:
    """First intersection of segment pq with an axis-aligned box, as a
    parameter in [0, 1], or None. Standard slab method."""

    x0, y0, x1, y1 = box
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for lo, hi, origin, delta in ((x0, x1, p[0], dx), (y0, y1, p[1], dy)):
        if abs(delta) < 1e-9:
            if origin < lo or origin > hi:
                return None
            continue
        a, b = (lo - origin) / delta, (hi - origin) / delta
        if a > b:
            a, b = b, a
        t0, t1 = max(t0, a), min(t1, b)
        if t0 > t1:
            return None
    return t0


def _line_of_sight(p: tuple[float, float], q: tuple[float, float],
                   walls: list[dict[str, Any]]) -> bool:
    """True when nothing solid stands between p and q at eye height.

    A wall that is hit inside one of its openings does not block - that is the
    whole point of the check: a bathroom door lines up with the dining table
    precisely when the sight line passes through the door hole.
    """

    for wall in walls:
        t = _segment_hits_box(p, q, wall["box"])
        if t is None:
            continue
        hx = p[0] + (q[0] - p[0]) * t
        hy = p[1] + (q[1] - p[1]) * t
        along = hy if wall["orientation"] == "v" else hx
        through = False
        for op in wall["openings"]:
            if op["t0"] - 1 <= along <= op["t1"] + 1 and op["z0"] <= EYE_MM <= op["z1"]:
                through = True
                break
        if not through:
            return False
    return True


def _door_point(door: dict[str, Any], net: Rect) -> tuple[float, float]:
    if door["orientation"] == "v":
        return (float(door["line"]), float(door["center"]))
    return (float(door["center"]), float(door["line"]))


def _inscribed_mm(cell: dict[str, Any]) -> int:
    """Largest circle that fits. For a rectangle that is just the short side."""
    r = Rect(*cell["clear_rect"])
    return min(r.w, r.d)


# --------------------------------------------------------------------------
# circulation graph
# --------------------------------------------------------------------------


class Circulation:
    """Rooms as nodes, doors as edges.

    Two kinds of edge are deliberately left out. A hatch is the door on an
    MDF/IDF cabinet - a leaf, but not a way through to anywhere, and counting
    it made equipment niches look like corridors. And ``outside`` is kept out
    of ``adj`` on purpose: walking out of the front door and round the house is
    not how you get from the kitchen to the rear balcony, so the indoor checks
    must not be able to route through it. Checks that genuinely start at the
    street use :meth:`widest_from_outside` instead.
    """

    def __init__(self, floor: dict[str, Any]):
        self.cells = {c["id"]: c for c in floor["cells"]}
        self.doors = floor["doors"]
        self.adj: dict[str, list[tuple[str, dict[str, Any]]]] = collections.defaultdict(list)
        self.outside: list[tuple[str, dict[str, Any]]] = []
        for d in self.doors:
            if d.get("role") == "hatch":
                continue
            if d["from"] == "outside":
                self.outside.append((d["to"], d))
                continue
            self.adj[d["from"]].append((d["to"], d))
            self.adj[d["to"]].append((d["from"], d))

    def path(self, start: str, goal: str, avoid: set[str] | None = None) -> list[str] | None:
        avoid = avoid or set()
        if start == goal:
            return [start]
        seen = {start}
        queue = collections.deque([[start]])
        while queue:
            trail = queue.popleft()
            for nxt, _ in self.adj[trail[-1]]:
                if nxt in seen or (nxt in avoid and nxt != goal):
                    continue
                seen.add(nxt)
                if nxt == goal:
                    return trail + [nxt]
                queue.append(trail + [nxt])
        return None

    def widest_path(self, start: str, goal: str) -> tuple[int, list[str]] | None:
        """Path whose narrowest door is as wide as possible - the question a
        removals crew asks, not the shortest-route question."""
        best: dict[str, int] = {start: 10 ** 9}
        trail: dict[str, list[str]] = {start: [start]}
        pool = {start}
        while pool:
            node = max(pool, key=lambda n: best[n])
            pool.discard(node)
            if node == goal:
                return best[node], trail[node]
            for nxt, door in self.adj[node]:
                width = min(best[node], int(door["clear_mm"]))
                if width > best.get(nxt, -1):
                    best[nxt] = width
                    trail[nxt] = trail[node] + [nxt]
                    pool.add(nxt)
        return None

    def widest_from_outside(self, goal: str) -> tuple[int, list[str]] | None:
        """Same, but starting at the street rather than at whichever room the
        caller guessed. The bottleneck on a carry route is very often the front
        door itself, and a path that begins inside the entry hall can never
        see it."""

        best: tuple[int, list[str]] | None = None
        for first, door in self.outside:
            if door.get("role") == "vehicle_door":
                continue          # the sofa does not come in through the garage
            found = self.widest_path(first, goal)
            if found is None:
                continue
            width = min(found[0], int(door["clear_mm"]))
            if best is None or width > best[0]:
                best = (width, found[1])
        return best


# --------------------------------------------------------------------------
# individual checks
# --------------------------------------------------------------------------


def _find(cells: dict[str, dict[str, Any]], **kw: Any) -> list[dict[str, Any]]:
    out = []
    for c in cells.values():
        if all(c.get(k) == v for k, v in kw.items()):
            out.append(c)
    return out


def _check_floor(floor: dict[str, Any], cap: dict[str, Any], building_id: str,
                 site: dict[str, Any], defaults: dict[str, Any],
                 garage_variant: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    circ = Circulation(floor)
    cells = circ.cells
    walls = floor["walls"]
    net = Rect(*floor["net_rect"])
    turn = int(site.get("corridor", {}).get("wheelchair_turn_mm", 1500))

    def add(code: str, message: str, refs: Iterable[str] = ()) -> None:
        out.append({
            "code": code,
            "severity": SEVERITY.get(code, "note"),
            "message": message,
            "refs": list(refs),
        })

    # --- capacity ------------------------------------------------------
    if cap and cap.get("over_capacity"):
        add("CAPACITY_OVERFLOW",
            f"需求 {cap['required_sqm']:.1f} m² 大於可用 {cap['usable_sqm']:.1f} m²，"
            f"超出 {cap['gap_ping']:.2f} 坪")

    # --- garage actually parkable ---------------------------------------
    # The user's condition is concrete: the car lives inside the building, and
    # the garage has to take an SUV plus a charging point. Measured on the
    # clear rect, because that is the space the car occupies.
    for g in (c for c in cells.values() if c["role"] == "garage"):
        want_bays = int((garage_variant or {}).get("bays", 1))
        one = garage_min_bay_mm(defaults, 1)
        r = Rect(*g["clear_rect"])
        if r.d < one["depth"] or r.w < one["width"]:
            short = "深" if r.d < one["depth"] else "寬"
            add("GARAGE_NOT_PARKABLE",
                f"車庫淨 {r.w}×{r.d} mm，{short}度不足（一台休旅車＋充電樁需要 "
                f"{one['width']}×{one['depth']} mm）",
                [g["id"]])
        else:
            fit = 0
            while garage_min_bay_mm(defaults, fit + 1)["width"] <= r.w:
                fit += 1
            if fit < want_bays:
                add("GARAGE_FEWER_BAYS",
                    f"車庫淨寬 {r.w} mm 只放得下 {fit} 台，要求 {want_bays} 台需要 "
                    f"{garage_min_bay_mm(defaults, want_bays)['width']} mm",
                    [g["id"]])

    # --- wheelchair turning circles (Q2, Q10) ---------------------------
    for cell in cells.values():
        if not cell.get("wheelchair_turn"):
            continue
        got = _inscribed_mm(cell)
        if got < turn:
            add("WHEELCHAIR_TURN",
                f"{cell['name']} 短邊 {got} mm < {turn} mm 迴轉圈",
                [cell["id"]])
    corridor = [c for c in cells.values() if c["role"] == "corridor"]
    want_corridor = int(site.get("corridor", {}).get("width_mm", 1200))
    for c in corridor:
        r = Rect(*c["clear_rect"])
        if min(r.w, r.d) < want_corridor:
            add("WHEELCHAIR_TURN",
                f"走道淨寬 {min(r.w, r.d)} mm < {want_corridor} mm", [c["id"]])

    # --- door clear width (Q3) -----------------------------------------
    # Only the designated entrance is tested. Under the old every-shared-edge
    # door policy this rule fired on incidental openings - a WC that happened to
    # touch the garage produced a finding about a door nobody would build - and
    # the one door that matters got the same weight as the accidents.
    for door in circ.doors:
        if door.get("role") not in ("entrance", "main_entrance"):
            continue
        cell = cells.get(door.get("to") or "")
        if not cell or cell.get("niche"):
            continue
        if cell.get("role") == "garage":
            # The garage's declared clear width is the vehicle opening, and that
            # is on the facade with its own check. Testing the pedestrian door
            # from the hallway against it produced 30 findings demanding a
            # 2400 mm internal door.
            continue
        need = 0
        if cell.get("wheelchair_turn"):
            need = int(defaults["geometry"]["door_width_mm"].get("accessible", 900))
        if cell.get("min_door_mm"):
            need = max(need, int(cell["min_door_mm"]))
        if need and int(door["clear_mm"]) < need:
            where = cells.get(door.get("from") or "", {}).get("name") or "室外"
            add("DOOR_CLEAR_WIDTH",
                f"{cell['name']} 由 {where} 進入的門淨寬 {door['clear_mm']} mm < {need} mm",
                [cell["id"]])

    # --- access the brief asked for and the layout could not give ---------
    # Name the space on the other side of the door. "唯一入口穿越私密空間" on its
    # own is a category, not a finding; "要穿過主臥" is something you can move.
    host_of = {d["to"]: d.get("from") for d in circ.doors
               if d.get("role") in ("entrance", "opening")}
    for cell in cells.values():
        flags = cell.get("flags") or []
        via = cells.get(host_of.get(cell["id"]) or "", {}).get("name") or "室外"
        if "ACCESS_UNREALISABLE" in flags:
            # The brief writes ids ("master"); the report is read by people who
            # know the room as 主臥室. Roles and kinds stay as written - they are
            # already words ("corridor" reads as a category, not a room).
            wanted = "、".join(cells.get(w, {}).get("name") or w
                              for w in (cell.get("access_from") or []))
            add("ACCESS_UNREALISABLE",
                f"{cell['name']} 要求由 {wanted} 進入，"
                f"但這一版配置裡兩者沒有共用牆，改由 {via} 進入",
                [cell["id"]])
        if "NESTED_ACCESS" in flags:
            add("NESTED_ACCESS",
                f"{cell['name']} 唯一的通路要穿過 {via}（臥室／衛浴等私密空間）",
                [cell["id"]])
        if "NO_ACCESS" in flags:
            add("NO_ACCESS", f"{cell['name']} 沒有任何可開門的共用牆 —— 進不去",
                [cell["id"]])
        if "GARAGE_DOOR_NARROW" in flags:
            add("GARAGE_DOOR_NARROW",
                f"{cell['name']} 臨路面寬只做得出 {Rect(*cell['rect']).w - 300} mm 車庫門，"
                f"休旅車進出需要 2200 mm 以上", [cell["id"]])

    # --- bathroom door facing the dining table (Q7) ---------------------
    # ``kind="dining"`` alone matched nothing: A and C merged 客廳 and 餐廳 into
    # one 客餐廳（開放式） carrying ``kind: living``, and B has no dining room at
    # all. So this check ran zero times in 120 floors while reading as a pass -
    # the same failure mode as the 穿堂煞 skip. The dining table is wherever the
    # brief says 餐, so that is what to look for.
    dining = [c for c in cells.values()
              if c.get("kind") == "dining"
              or (c.get("kind") == "living" and "餐" in c["name"])]
    baths = {c["id"] for c in cells.values() if c.get("kind") == "bath"}
    for room in dining:
        rr = Rect(*room["clear_rect"])
        for door in circ.doors:
            if door["from"] not in baths and door["to"] not in baths:
                continue
            pt = _door_point(door, net)
            if _line_of_sight((rr.cx, rr.cy), pt, walls):
                bath_id = door["from"] if door["from"] in baths else door["to"]
                add("BATH_FACES_DINING",
                    f"{cells[bath_id]['name']} 的門與 {room['name']} 之間視線無阻擋",
                    [room["id"], bath_id])

    # --- kitchen to the service balcony without crossing a bedroom (Q8) --
    kitchens = _find(cells, kind="kitchen")
    balconies = [c for c in cells.values()
                 if c.get("kind") == "outdoor" and c.get("counts_in_footprint")]
    private = {c["id"] for c in cells.values() if c.get("private")}
    for k in kitchens:
        for b in balconies:
            clean = circ.path(k["id"], b["id"], avoid=private)
            if clean is None and circ.path(k["id"], b["id"]) is not None:
                add("KITCHEN_TO_BALCONY",
                    f"{k['name']} 到 {b['name']} 的唯一路徑會穿越臥室或衛浴",
                    [k["id"], b["id"]])

    # --- the brief said front or rear and the layout said otherwise -------
    # ``assign_zones`` honours ``band`` "where stated" and quietly overrides it
    # when the band it wants is full. Nothing compared the two afterwards, so a
    # 後工作陽台 sat on the street facade in four variants without a word.
    BAND_ZH = {"front": "前段", "rear": "後段"}
    for cell in cells.values():
        want, got = cell.get("band"), cell.get("band_actual")
        if want in BAND_ZH and got in BAND_ZH and want != got:
            add("BAND_UNREALISABLE",
                f"{cell['name']} 需求指定在{BAND_ZH[want]}，實際落在{BAND_ZH[got]}",
                [cell["id"]])

    # --- an outdoor space has to reach the outside ------------------------
    # Two checks, because they fail differently. A balcony surrounded by rooms
    # is not a balcony at all; one that reaches only a side wall is usable but
    # is not the 後工作陽台 the brief asked for - the water risers, the drain and
    # the drying line are all on the rear service wall, and the rear yard is the
    # only side with room to work.
    for b in (c for c in cells.values()
              if c.get("kind") == "outdoor" and "陽台" in c["name"]):
        sides = b.get("exterior_sides") or []
        if not sides:
            add("OUTDOOR_LANDLOCKED",
                f"{b['name']} 四周都是室內，沒有任何外牆 —— 無法排水、曬衣、通風，"
                "這不是陽台", [b["id"]])
        elif "rear" not in sides:
            where = "、".join({"left": "左", "right": "右", "front": "前（臨路）"}.get(s, s)
                             for s in sides)
            # The 穿堂煞 clause only belongs on the floor that has the front
            # door. Said on 3F it reads as a rule misfiring, which costs the
            # finding the credibility the other 30 need.
            why = ("給水進線與排水立管在後側，且穿堂煞檢查因此無法評估這個空間"
                   if floor.get("floor_id") == "floor-1"
                   else "排水立管要上下對齊，與樓下的後陽台不同側就接不起來")
            add("BALCONY_NOT_ON_FACADE",
                f"{b['name']} 只貼到{where}外牆，沒有貼到後外牆 —— {why}",
                [b["id"]])

    # --- front door lined up with the rear balcony (Q11) ----------------
    main = next((d for d in circ.doors if d.get("role") == "main_entrance"), None)
    if main is not None:
        for b in balconies:
            br = Rect(*b["clear_rect"])
            if br.y1 < net.y1 - 100:
                # Not on the rear facade, so there is no front-to-rear view to
                # measure. The skip used to be the whole story and read as a
                # pass; BALCONY_NOT_ON_FACADE above now says out loud that this
                # floor's 穿堂煞 was never actually tested.
                continue
            if abs(br.cx - main["center"]) > 600:
                continue
            p = (float(main["center"]), float(net.y0) + 100.0)
            if _line_of_sight(p, (br.cx, br.cy), walls):
                add("FRONT_REAR_ALIGNED",
                    f"大門中心與 {b['name']} 前後對齊且視線直通（偏移 "
                    f"{abs(br.cx - main['center']):.0f} mm）—— 需要屏風、拉門或半高櫃",
                    [b["id"]])

    # --- palanquin carry route (B building) -----------------------------
    # Measured from the street. The old version started at the entry hall, so
    # the front door - 1000 mm by default, and the narrowest thing on the whole
    # route - was never part of the answer.
    for cell in cells.values():
        if not cell.get("carry_path") and cell.get("id") != "palanquin" \
                and "武轎" not in cell["name"]:
            continue
        need = int(cell.get("min_door_mm") or 1200)
        found = circ.widest_from_outside(cell["id"])
        if found is None:
            add("PALANQUIN_PATH", f"{cell['name']} 與大門之間沒有連通路徑", [cell["id"]])
        elif found[0] < need:
            add("PALANQUIN_PATH",
                f"大門到 {cell['name']} 的最寬路徑瓶頸只有 {found[0]} mm < {need} mm"
                f"（路徑：大門 → {' → '.join(cells[n]['name'] for n in found[1])}）—— "
                f"抬轎進不去",
                [cell["id"]])

    # --- daylight -------------------------------------------------------
    for cell in cells.values():
        if cell.get("light") == "required" and not cell.get("exterior_sides"):
            add("NO_DAYLIGHT", f"{cell['name']} 需要採光但沒有外牆", [cell["id"]])

    return out


def _check_roof(floor: dict[str, Any], cap: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if cap and cap.get("over"):
        # Name the biggest contributor. "over by 3.55" is not actionable; "the
        # solar array is 15.68 of it" points straight at the thing to change.
        parts = sorted(cap.get("penthouse_by_class", {}).items(),
                       key=lambda kv: -kv[1])
        driver = (f"，最大宗是 {ROOF_CLASS_LABEL.get(parts[0][0], parts[0][0])} "
                  f"{parts[0][1]:.2f} m²" if parts else "")
        out.append({
            "code": "PENTHOUSE_OVER_LIMIT",
            "severity": SEVERITY["PENTHOUSE_OVER_LIMIT"],
            "message": (f"屋頂突出物水平投影 {cap['penthouse_sqm']:.2f} m² 超過上限 "
                        f"{cap['limit_sqm']:.2f} m²（{cap['limit_ping']:.2f} 坪，"
                        f"依 {cap.get('limit_basis', '建築技術規則第 1 條')}）{driver}"),
            "refs": [c["id"] for c in floor["cells"] if c.get("penthouse_class")],
        })
    # An unclassified penthouse box is counted as 第一目 so the total stays
    # honest, but which 目 it lands in changes whether it eats 容積 - that is a
    # gap in the brief, not something the generator should decide silently.
    for cid in (cap or {}).get("unclassified", []):
        out.append({
            "code": "PENTHOUSE_UNCLASSIFIED",
            "severity": SEVERITY.get("PENTHOUSE_UNCLASSIFIED", "warning"),
            "message": (f"{cid} 標為屋突但沒有指定法規目別（penthouse_class），"
                        f"暫以第一目計入投影面積；是否計入容積要看實際做法"),
            "refs": [cid],
        })
    for cell in floor["cells"]:
        if "EQUIP_ACCESS_TIGHT" in cell.get("flags", []):
            clear = cell["clear_rect"]
            short = min(clear[2] - clear[0], clear[3] - clear[1])
            out.append({
                "code": "EQUIP_ACCESS_TIGHT",
                "severity": SEVERITY.get("EQUIP_ACCESS_TIGHT", "warning"),
                "message": (f"{cell['name']} 短邊 {short} mm，不足維修通道 900 mm —— "
                            f"設備擺得下不代表人進得去維修"),
                "refs": [cell["id"]],
            })
    return out


# --------------------------------------------------------------------------


def _check_stacking(building: dict[str, Any]) -> list[dict[str, Any]]:
    """Cross-floor check: nothing that drains may sit over the 神明廳.

    ``design_request.md`` line 340 lists 「2F 衛浴／排水管不要壓到神桌」 as 必做 and
    「B 棟風水最大紅線之一」, and §2 spells out 馬桶、淋浴區、排水立管、天花排水.
    The original plan claimed the fixed stacked core made this structurally
    impossible. It does not: only the core's own wet areas stack, and 客用衛浴 /
    3F 衛浴 are placed by the guillotine split like any other room. Eight
    layouts put one directly over the shrine and nothing said a word.

    Whole-footprint, not 神桌-only: the model does not carry the altar's
    position, and the altar is the least movable thing in the room. Flagging
    the room is the honest resolution of what we actually know.
    """
    out: list[dict[str, Any]] = []
    floors = building["floors"]
    ground = next((f for f in floors if f["floor_id"] == "floor-1"), None)
    if ground is None:
        return out
    shrine = next((c for c in ground["cells"] if "神明廳" in c["name"]), None)
    if shrine is None:
        return out
    s = Rect(*shrine["rect"])
    WET = {"bath": "衛浴排水", "kitchen": "廚房排水"}
    for floor in floors:
        if floor["floor_id"] == "floor-1":
            continue
        for cell in floor["cells"]:
            what = WET.get(cell.get("kind"))
            if what is None and cell.get("kind") == "outdoor" and "陽台" in cell["name"]:
                what = "陽台落水頭"
            if what is None:
                continue
            r = Rect(*cell["rect"])
            ox = max(0, min(s.x1, r.x1) - max(s.x0, r.x0))
            oy = max(0, min(s.y1, r.y1) - max(s.y0, r.y0))
            area = ox * oy / 1e6
            if area < 0.05:
                continue
            out.append({
                "code": "SHRINE_STACK",
                "severity": SEVERITY["SHRINE_STACK"],
                "message": (f"{cell['name']} 壓在 {shrine['name']} 正上方 "
                            f"{area:.2f} m²（{what}在神桌上方）—— "
                            f"design_request 第 340 行列為必做紅線；"
                            f"神桌確切位置與排水立管走向仍須建築師確認"),
                "refs": [cell["id"], shrine["id"]],
                "floor": floor["label"],
                "floor_id": floor["floor_id"],
            })
    return out


def evaluate(doc: dict[str, Any], site: dict[str, Any],
             defaults: dict[str, Any]) -> list[dict[str, Any]]:
    """Run every check over every variant. Returns a flat list so the report and
    the 3D rule panel can both filter it however they like."""

    findings: list[dict[str, Any]] = []
    for variant in doc["variants"]:
        for bid in ("A", "B", "C"):
            building = variant["buildings"][bid]
            caps = {c.get("floor_id"): c for c in building["capacity"]}
            for floor in building["floors"]:
                cap = caps.get(floor["floor_id"], {})
                if cap.get("roof"):
                    got = _check_roof(floor, cap)
                else:
                    got = _check_floor(floor, cap, bid, site, defaults,
                                       variant["garage"])
                for f in got:
                    f.update({
                        "variant": variant["id"],
                        "frontage_mm": variant["frontage_mm"],
                        "garage": variant["garage"].get("label", ""),
                        "building": bid,
                        "floor": floor["label"],
                        "floor_id": floor["floor_id"],
                    })
                findings.extend(got)
            # Cross-floor, so it cannot live in _check_floor: it needs 1F and
            # the floor above in the same frame.
            for f in _check_stacking(building):
                f.update({
                    "variant": variant["id"],
                    "frontage_mm": variant["frontage_mm"],
                    "garage": variant["garage"].get("label", ""),
                    "building": bid,
                })
                findings.append(f)
    return findings


def summarise(findings: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """code -> variant -> count, for the matrix at the top of the report."""
    out: dict[str, dict[str, int]] = {}
    for f in findings:
        out.setdefault(f["code"], {}).setdefault(f["variant"], 0)
        out[f["code"]][f["variant"]] += 1
    return out

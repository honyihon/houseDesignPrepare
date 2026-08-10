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

from .plan_geometry import PING_TO_SQM, Rect, garage_min_bay_mm

EYE_MM = 1500  # sight-line height for the "does it face the dining table" test

CODES = {
    "CAPACITY_OVERFLOW": "該層需求超過可用面積",
    "WHEELCHAIR_TURN": "輪椅迴轉圈放不下",
    "DOOR_CLEAR_WIDTH": "門淨寬不足",
    "BATH_FACES_DINING": "廁所門正對餐廳",
    "KITCHEN_TO_BALCONY": "廚房到後陽台必須穿越臥室",
    "FRONT_REAR_ALIGNED": "大門與後陽台對穿（穿堂煞）",
    "PALANQUIN_PATH": "武轎搬運路徑淨寬不足",
    "PENTHOUSE_OVER_LIMIT": "屋突面積超過建築面積 1/8",
    "NO_DAYLIGHT": "需採光的房間沒有外牆",
    "GARAGE_NOT_PARKABLE": "車庫放不下一台休旅車＋充電樁",
    "GARAGE_FEWER_BAYS": "車庫寬度放不下要求的車位數",
}

SEVERITY = {
    "CAPACITY_OVERFLOW": "error",
    "WHEELCHAIR_TURN": "error",
    "DOOR_CLEAR_WIDTH": "error",
    "PENTHOUSE_OVER_LIMIT": "error",
    "GARAGE_NOT_PARKABLE": "error",
    "KITCHEN_TO_BALCONY": "warning",
    "PALANQUIN_PATH": "warning",
    "NO_DAYLIGHT": "warning",
    "GARAGE_FEWER_BAYS": "warning",
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
    def __init__(self, floor: dict[str, Any]):
        self.cells = {c["id"]: c for c in floor["cells"]}
        self.doors = floor["doors"]
        self.adj: dict[str, list[tuple[str, dict[str, Any]]]] = collections.defaultdict(list)
        self.outside: list[tuple[str, dict[str, Any]]] = []
        for d in self.doors:
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
    for door in circ.doors:
        for side in (door.get("from"), door.get("to")):
            cell = cells.get(side or "")
            if not cell:
                continue
            need = 0
            if cell.get("wheelchair_turn") or cell.get("kind") == "bath":
                need = int(defaults["geometry"]["door_width_mm"].get("accessible", 900))
            if cell.get("kind") == "bath" and not cell.get("wheelchair_turn"):
                need = 0  # only the accessible bathrooms carry the 90 cm rule
            other_id = door.get("to") if side == door.get("from") else door.get("from")
            if cells.get(other_id or "", {}).get("niche"):
                # The far side is an equipment niche (MDF/IDF rack). Q3 is about
                # getting a wheelchair through a doorway, and nobody wheels into
                # a 90 cm deep cabinet - flagging it buries the real findings.
                need = 0
            if need and int(door["clear_mm"]) < need:
                # Name the other side too: a room with two narrow doors otherwise
                # produces two rows that look like the same finding twice.
                where = cells.get(other_id or "", {}).get("name") or "室外"
                add("DOOR_CLEAR_WIDTH",
                    f"{cell['name']} 對 {where} 的門淨寬 {door['clear_mm']} mm < {need} mm",
                    [cell["id"]])
                break

    # --- bathroom door facing the dining table (Q7) ---------------------
    dining = _find(cells, kind="dining")
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

    # --- front door lined up with the rear balcony (Q11) ----------------
    main = next((d for d in circ.doors if d.get("role") == "main_entrance"), None)
    if main is not None:
        for b in balconies:
            br = Rect(*b["clear_rect"])
            if br.y1 < net.y1 - 100:
                continue  # not on the rear facade, no through-draught to worry about
            if abs(br.cx - main["center"]) > 600:
                continue
            p = (float(main["center"]), float(net.y0) + 100.0)
            if _line_of_sight(p, (br.cx, br.cy), walls):
                add("FRONT_REAR_ALIGNED",
                    f"大門中心與 {b['name']} 前後對齊且視線直通（偏移 "
                    f"{abs(br.cx - main['center']):.0f} mm）—— 需要屏風、拉門或半高櫃",
                    [b["id"]])

    # --- palanquin carry route (B building) -----------------------------
    for cell in cells.values():
        if not cell.get("id"):
            continue
        brief_note = cell.get("note") or ""
        if cell["id"] != "palanquin" and "武轎" not in cell["name"]:
            continue
        entries = [c for c in cells.values() if c.get("kind") == "entry"]
        start = entries[0]["id"] if entries else (circ.outside[0][0] if circ.outside else None)
        if start is None:
            continue
        found = circ.widest_path(start, cell["id"])
        need = int(cell.get("min_door_mm") or 1200)
        if found is None:
            add("PALANQUIN_PATH", f"{cell['name']} 與玄關之間沒有連通路徑", [cell["id"]])
        elif found[0] < need:
            add("PALANQUIN_PATH",
                f"玄關到 {cell['name']} 的最寬路徑瓶頸只有 {found[0]} mm < {need} mm"
                f"（路徑：{' → '.join(cells[n]['name'] for n in found[1])}）",
                [cell["id"]])

    # --- daylight -------------------------------------------------------
    for cell in cells.values():
        if cell.get("light") == "required" and not cell.get("exterior_sides"):
            add("NO_DAYLIGHT", f"{cell['name']} 需要採光但沒有外牆", [cell["id"]])

    return out


def _check_roof(floor: dict[str, Any], cap: dict[str, Any]) -> list[dict[str, Any]]:
    if cap and cap.get("over"):
        return [{
            "code": "PENTHOUSE_OVER_LIMIT",
            "severity": SEVERITY["PENTHOUSE_OVER_LIMIT"],
            "message": (f"屋突 {cap['penthouse_sqm']:.2f} m² 超過建築面積 1/8 上限 "
                        f"{cap['limit_sqm']:.2f} m²（{cap['limit_ping']:.2f} 坪）"),
            "refs": [c["id"] for c in floor["cells"] if c.get("penthouse")],
        }]
    return []


# --------------------------------------------------------------------------


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
    return findings


def summarise(findings: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """code -> variant -> count, for the matrix at the top of the report."""
    out: dict[str, dict[str, int]] = {}
    for f in findings:
        out.setdefault(f["code"], {}).setdefault(f["variant"], 0)
        out[f["code"]][f["variant"]] += 1
    return out

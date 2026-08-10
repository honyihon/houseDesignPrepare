#!/usr/bin/env python3
"""Parametric floor-plan generation for the pre-architect design stage.

The rest of this repo reads geometry *out of* the HTML pages. This module goes
the other way: nobody has drawn a plan yet, so we generate one from an area
brief plus a handful of massing parameters, and let the user push the
parameters around until the result feels right.

Everything here is axis-aligned rectangles in millimetres, footprint
coordinates, origin at the front-left corner of the outer face of the exterior
wall:

    x -> right (as seen on a plan drawn with the front facade at the bottom)
    y -> toward the rear of the building

The layout skeleton is deliberately one shape, not a search over many:

      x=0                                            x=W
    y=0 +--------------------------------+-----------+
        |          FRONT ZONE            |  GARAGE   |   garage on 1F only
        |     (entry, living, ...)       |           |
   y=fd +--------------------------------+-----------+
        |            CORRIDOR  (full width)          |
 y=fd+cw+------------------------+-------+-----------+
        |                        | spine |   CORE    |   stair + shaft + annex
        |       REAR ZONE        |       +-----------+
        |                        |       | REAR-RIGHT|
    y=D +------------------------+-------+-----------+

Front-zone rooms touch the corridor on their rear edge; rear-zone rooms touch
it on their front edge or on the spine. The core sits at the same coordinates
on every floor, so stairs align and the pipe shaft runs straight up without
anyone having to check afterwards.

Within each zone, rooms are placed by recursive binary (guillotine) division
weighted by target area. Guillotine is chosen over free packing for one
concrete reason: it tiles the zone exactly, so the generated plan can never
grow the 1 mm slivers and floor-sized holes that the CSS-derived geometry in
``structured/room_program.json`` is full of.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Sequence

PING_TO_SQM = 3.305785

# A door needs the wall segment it sits in to be wider than the door itself,
# or the opening eats the corner and there is nothing left to hang it on.
DOOR_EDGE_MARGIN_MM = 150
MIN_ROOM_DIM_MM = 1500

# The garage cannot take the whole frontage: the front door has to be beside it,
# and an entry narrower than this is not an entry.
GARAGE_SIDE_STRIP_MM = 2400


# --------------------------------------------------------------------------
# Rect
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def w(self) -> int:
        return self.x1 - self.x0

    @property
    def d(self) -> int:
        return self.y1 - self.y0

    @property
    def area_mm2(self) -> int:
        return self.w * self.d

    @property
    def area_sqm(self) -> float:
        return self.area_mm2 / 1_000_000.0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def valid(self) -> bool:
        return self.w > 0 and self.d > 0

    def as_list(self) -> list[int]:
        return [self.x0, self.y0, self.x1, self.y1]

    def inset(self, left: int = 0, front: int = 0, right: int = 0, rear: int = 0) -> "Rect":
        return Rect(self.x0 + left, self.y0 + front, self.x1 - right, self.y1 - rear)


def _split_x(rect: Rect, x: int) -> tuple[Rect, Rect]:
    return Rect(rect.x0, rect.y0, x, rect.y1), Rect(x, rect.y0, rect.x1, rect.y1)


def _split_y(rect: Rect, y: int) -> tuple[Rect, Rect]:
    return Rect(rect.x0, rect.y0, rect.x1, y), Rect(rect.x0, y, rect.x1, rect.y1)


# --------------------------------------------------------------------------
# Placed cells
# --------------------------------------------------------------------------


Role = Literal["room", "corridor", "core", "stair", "garage", "shaft"]


@dataclass
class Cell:
    """A tile of the floor. ``rect`` is the structural grid cell; the clear
    (finished) rect is derived later by pulling back half a wall on every edge
    that is an interior split."""

    id: str
    name: str
    kind: str
    role: Role
    rect: Rect
    brief: dict[str, Any] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    clear: Rect | None = None


# --------------------------------------------------------------------------
# Guillotine subdivision
# --------------------------------------------------------------------------


def _aspect(rect: Rect) -> float:
    if rect.w <= 0 or rect.d <= 0:
        return 99.0
    return max(rect.w, rect.d) / min(rect.w, rect.d)


def guillotine(rect: Rect, items: Sequence[tuple[str, float]]) -> dict[str, Rect]:
    """Tile ``rect`` among ``items`` (id, weight) by recursive binary division.

    The split axis is always the longer one, which keeps rooms from degenerating
    into corridors. The split *index* is chosen to minimise the worse of the two
    children's aspect ratios, so a large room and a tiny one end up side by side
    rather than the tiny one being smeared across the full width.
    """

    if not items:
        return {}
    if len(items) == 1:
        return {items[0][0]: rect}

    total = sum(max(w, 0.01) for _, w in items)
    best: tuple[float, int] | None = None
    for k in range(1, len(items)):
        left_w = sum(max(w, 0.01) for _, w in items[:k])
        frac = left_w / total
        if rect.w >= rect.d:
            cut = rect.x0 + int(round(rect.w * frac))
            a, b = _split_x(rect, cut)
        else:
            cut = rect.y0 + int(round(rect.d * frac))
            a, b = _split_y(rect, cut)
        if not a.valid or not b.valid:
            continue
        score = max(_aspect(a) / max(len(items[:k]), 1), _aspect(b) / max(len(items[k:]), 1))
        if best is None or score < best[0]:
            best = (score, k)

    k = best[1] if best else len(items) // 2 or 1
    left_w = sum(max(w, 0.01) for _, w in items[:k])
    frac = left_w / total
    if rect.w >= rect.d:
        cut = rect.x0 + int(round(rect.w * frac))
        a, b = _split_x(rect, cut)
    else:
        cut = rect.y0 + int(round(rect.d * frac))
        a, b = _split_y(rect, cut)

    out: dict[str, Rect] = {}
    out.update(guillotine(a, items[:k]))
    out.update(guillotine(b, items[k:]))
    return out


# --------------------------------------------------------------------------
# Stair / core sizing
# --------------------------------------------------------------------------


def stair_dims(site: dict[str, Any]) -> dict[str, int]:
    core = site.get("core", {})
    run_w = int(core.get("stair_run_width_mm", 1000))
    riser = int(core.get("stair_riser_mm", 175))
    tread = int(core.get("stair_tread_mm", 260))
    landing = int(core.get("landing_depth_mm", 1100))
    height = int(site.get("storey_height_mm", 3000))

    risers = max(2, int(round(height / riser)))
    flight_a = math.ceil(risers / 2)
    run_len = max(1, flight_a - 1) * tread

    return {
        "risers": risers,
        "riser_mm": int(round(height / risers)),
        "tread_mm": tread,
        "run_width_mm": run_w,
        "landing_mm": landing,
        "flight_a": flight_a,
        "flight_b": risers - flight_a,
        # Two parallel runs plus a 100 mm well, landing across the far end.
        "w_mm": run_w * 2 + 100,
        "d_mm": run_len + landing,
    }


# --------------------------------------------------------------------------
# Skeleton
# --------------------------------------------------------------------------


@dataclass
class Skeleton:
    net: Rect
    front_depth: int
    corridor_w: int
    core: Rect
    stair: Rect
    core_annex: Rect | None
    garage: Rect | None
    spine: Rect | None
    notes: list[str] = field(default_factory=list)


def garage_min_bay_mm(defaults: dict[str, Any], bays: int = 1) -> dict[str, int]:
    """Clear dimensions a garage needs before a car can actually use it.

    Derived from the vehicle spec rather than written down, so "does it fit"
    has one answer that both the generator and the rule checker read. The
    numbers are clear dimensions - what is left between the finished wall
    faces - because that is what the car occupies.

    The charging point shares the depth in front of the bumper with the
    walking clearance instead of adding to it: you stand in the same strip you
    plug in from.
    """

    veh = defaults.get("vehicle", {})
    suv = veh.get("suv_mm", {})
    clr = veh.get("clearance_mm", {})
    evc = veh.get("ev_charger_mm", {})

    length = int(suv.get("length", 4900))
    width = int(suv.get("width", 1950))
    front = max(int(clr.get("front", 600)),
                int(evc.get("depth", 400)) + int(evc.get("clear", 300)))
    rear = int(clr.get("rear", 500))
    bays = max(1, int(bays))

    return {
        "bays": bays,
        "width": (width * bays + int(clr.get("driver_side", 700))
                  + int(clr.get("passenger_side", 350))
                  + int(clr.get("between_bays", 300)) * (bays - 1)),
        "depth": length + front + rear,
        "front_service": front,
        "car_length": length,
        "car_width": width,
    }


def _choose_garage(net: Rect, variant: dict[str, Any], defaults: dict[str, Any],
                   avail_w: int, avail_d: int,
                   notes: list[str]) -> tuple[int, int, list[str]]:
    """Size the garage against what a car actually needs, and refuse to lie.

    Two things this deliberately does not do. It does not rotate the garage 90
    degrees: the three buildings sit in a row with their only street frontage
    at the front, so a side-facing garage door would open onto the 6 m gap
    between houses with no driveway behind it - the car drives in nose-first or
    not at all, which makes depth a hard requirement rather than a preference.
    And it does not squeeze below the parkable minimum silently; it clamps to
    the space that exists and flags what broke, so an 8 m frontage that cannot
    take a garage says so instead of reporting a 3.0 m deep "garage".

    ``avail_d`` is the same front-zone budget ``build_skeleton`` will actually
    apply. Passing it in is the point: the old code checked against a looser
    limit than the one that later clipped the rect, so the garage came out
    shorter than the check had approved.
    """

    flags: list[str] = []
    ins = int(defaults["geometry"]["wall_thickness_mm"]["interior"])
    bays = int(variant.get("bays", 1))
    need = garage_min_bay_mm(defaults, bays)
    need_one = garage_min_bay_mm(defaults, 1)

    # Brief values are clear dimensions; the reserved rect carries the two
    # interior partitions (left edge and rear edge) on top of them.
    want_w = int(variant.get("w_mm", need["width"])) + ins
    want_d = int(variant.get("d_mm", need["depth"])) + ins

    w = min(want_w, max(0, avail_w))
    d = min(want_d, max(0, avail_d))
    clear_w, clear_d = w - ins, d - ins

    if clear_d < need_one["depth"]:
        flags.append(f"GARAGE_TOO_SHALLOW:{clear_d}<{need_one['depth']}")
        notes.append(
            f"車庫淨深只有 {clear_d}mm，放不下一台休旅車＋充電樁（需要 {need_one['depth']}mm："
            f"車長 {need_one['car_length']} + 車頭 {need_one['front_service']} + 車尾 500）。"
            f"這個開間的建築進深太淺，車庫塞不進建築體內。"
        )
    # How many bays the width can genuinely take, as opposed to how many were asked for.
    fit_bays = 0
    while garage_min_bay_mm(defaults, fit_bays + 1)["width"] <= clear_w:
        fit_bays += 1
    if fit_bays < bays:
        flags.append(f"GARAGE_TOO_NARROW:{clear_w}<{need['width']}")
        notes.append(
            f"車庫淨寬 {clear_w}mm 只放得下 {fit_bays} 台（要求 {bays} 台需要 {need['width']}mm）。"
        )

    return w, d, flags


def build_skeleton(frontage_mm: int, depth_mm: int, site: dict[str, Any],
                   defaults: dict[str, Any], garage_variant: dict[str, Any] | None,
                   core_annex_sqm: float) -> Skeleton:
    ext = int(defaults["geometry"]["wall_thickness_mm"]["exterior"])
    ins = int(defaults["geometry"]["wall_thickness_mm"]["interior"])
    # ``corridor.width_mm`` is the width someone actually walks in. The band has a
    # partition on both long edges, so the structural band has to be that much
    # wider or every corridor in the building comes out one wall thickness short.
    corridor_clear = int(site.get("corridor", {}).get("width_mm", 1200))
    corridor_w = corridor_clear + ins
    notes: list[str] = []

    net = Rect(ext, ext, frontage_mm - ext, depth_mm - ext)

    stair = stair_dims(site)
    shaft_w = int(site.get("core", {}).get("shaft_w_mm", 600))
    shaft_d = int(site.get("core", {}).get("shaft_d_mm", 600))

    core_w = min(stair["w_mm"] + shaft_w, max(2100, net.w // 2))
    stair_d = stair["d_mm"]
    annex_d = 0
    if core_annex_sqm > 0:
        annex_d = max(900, int(round(core_annex_sqm * 1_000_000 / core_w)))

    # The front-zone budget has to be known before the garage is sized, not
    # after: it is what ends up clipping the garage, so it is what the garage
    # must be measured against.
    max_front = net.d - corridor_w - stair_d - annex_d - 1200
    if max_front < 3000:
        # Extremely shallow footprint: give the front zone what is left and let
        # the capacity report carry the bad news.
        max_front = max(2400, net.d - corridor_w - 3000)

    # Garage first: it sets the front-zone depth on every floor, because keeping
    # the corridor line at one y for the whole building is what makes the
    # partition walls stack instead of floating over open space.
    garage_w = garage_d = 0
    garage_flags: list[str] = []
    if garage_variant:
        garage_w, garage_d, garage_flags = _choose_garage(
            net, garage_variant, defaults,
            net.w - GARAGE_SIDE_STRIP_MM,  # keep a strip beside it for the entry
            max_front, notes)

    front_depth = min(max(garage_d, 3000), max_front)

    corridor_y0 = net.y0 + front_depth
    core_y0 = corridor_y0 + corridor_w
    core_d = min(stair_d + annex_d, net.y1 - core_y0)
    core = Rect(net.x1 - core_w, core_y0, net.x1, core_y0 + core_d)
    stair_rect = Rect(core.x0, core.y0, core.x1, min(core.y0 + stair_d, core.y1))
    annex = Rect(core.x0, stair_rect.y1, core.x1, core.y1) if core.y1 - stair_rect.y1 >= 600 else None

    garage_rect = None
    if garage_variant and garage_w > 0:
        gx0 = max(net.x0, net.x1 - garage_w)
        garage_rect = Rect(gx0, net.y0, net.x1, net.y0 + min(garage_d, front_depth))

    # Spine: only when there is a rear-right pocket behind the core worth reaching
    # directly, and only when the rear-left zone can spare the width.
    spine = None
    pocket_d = net.y1 - core.y1
    if pocket_d >= 2400 and (core.x0 - net.x0) - corridor_w >= 2400:
        spine = Rect(core.x0 - corridor_w, core.y0, core.x0, net.y1)

    return Skeleton(
        net=net,
        front_depth=front_depth,
        corridor_w=corridor_w,
        core=core,
        stair=stair_rect,
        core_annex=annex,
        garage=garage_rect,
        spine=spine,
        notes=notes + ([f"車庫旗標：{'、'.join(garage_flags)}"] if garage_flags else []),
    )


# --------------------------------------------------------------------------
# Zone assignment
# --------------------------------------------------------------------------


def free_rects(net: Rect, reserved: Sequence[Rect]) -> list[Rect]:
    """Decompose ``net`` minus ``reserved`` into non-overlapping rectangles that
    cover the remainder exactly.

    Deriving the leftover zones by hand is how a generator ends up with a
    garage-shaped hole on the second floor. Cutting the whole net area on the
    coordinate grid of the reserved rects instead makes "no holes" a property of
    the method rather than something to remember.
    """

    xs = sorted({net.x0, net.x1} | {c for r in reserved for c in (r.x0, r.x1)
                                    if net.x0 < c < net.x1})
    ys = sorted({net.y0, net.y1} | {c for r in reserved for c in (r.y0, r.y1)
                                    if net.y0 < c < net.y1})
    nx, ny = len(xs) - 1, len(ys) - 1
    if nx <= 0 or ny <= 0:
        return []

    covered = [[False] * nx for _ in range(ny)]
    for r in reserved:
        for j in range(ny):
            if ys[j] >= r.y1 or ys[j + 1] <= r.y0:
                continue
            for i in range(nx):
                if xs[i] >= r.x1 or xs[i + 1] <= r.x0:
                    continue
                covered[j][i] = True

    strips: list[tuple[int, int, int]] = []  # (band, i0, i1)
    for j in range(ny):
        i = 0
        while i < nx:
            if covered[j][i]:
                i += 1
                continue
            i0 = i
            while i < nx and not covered[j][i]:
                i += 1
            strips.append((j, i0, i))

    by_band: dict[int, list[int]] = {}
    for k, (j, _, _) in enumerate(strips):
        by_band.setdefault(j, []).append(k)

    out: list[Rect] = []
    used = [False] * len(strips)
    for k, (j, i0, i1) in enumerate(strips):
        if used[k]:
            continue
        used[k] = True
        last = j
        while True:
            nxt = None
            for k2 in by_band.get(last + 1, []):
                if not used[k2] and strips[k2][1] == i0 and strips[k2][2] == i1:
                    nxt = k2
                    break
            if nxt is None:
                break
            used[nxt] = True
            last += 1
        out.append(Rect(xs[i0], ys[j], xs[i1], ys[last + 1]))
    return out


@dataclass
class Zone:
    id: str
    band: str          # "front" | "rear"
    rect: Rect
    rooms: list[dict[str, Any]] = field(default_factory=list)

    @property
    def load(self) -> float:
        return sum(float(r.get("target_sqm", 4.0)) for r in self.rooms)


def make_zones(sk: Skeleton, reserved: Sequence[Rect]) -> list[Zone]:
    corridor_y0 = sk.net.y0 + sk.front_depth
    zones: list[Zone] = []
    for n, rect in enumerate(free_rects(sk.net, reserved)):
        band = "front" if rect.cy < corridor_y0 else "rear"
        zones.append(Zone(id=f"{band}{n}", band=band, rect=rect))
    return zones


def assign_zones(rooms: list[dict[str, Any]], zones: list[Zone]) -> None:
    """Hand each room to a zone in place, honouring ``band`` where stated."""

    if not zones:
        return

    front_cap = sum(z.rect.area_sqm for z in zones if z.band == "front")
    rear_cap = sum(z.rect.area_sqm for z in zones if z.band == "rear")
    bands: dict[str, list[Zone]] = {"front": [z for z in zones if z.band == "front"],
                                    "rear": [z for z in zones if z.band == "rear"]}
    band_load = {"front": 0.0, "rear": 0.0}
    band_cap = {"front": front_cap, "rear": rear_cap}

    # Biggest rooms first: a 20 m2 living room placed last has no zone left that
    # can hold it without deforming everything around it.
    for room in sorted(rooms, key=lambda r: -float(r.get("target_sqm", 4.0))):
        want = room.get("band", "auto")
        if want not in bands or not bands[want]:
            want = max(bands, key=lambda b: band_cap[b] - band_load[b] if bands[b] else -1e9)
        if not bands[want]:
            want = "front" if bands["front"] else "rear"
        if not bands[want]:
            continue
        zone = max(bands[want], key=lambda z: z.rect.area_sqm - z.load)
        zone.rooms.append(room)
        band_load[want] += float(room.get("target_sqm", 4.0))

    # A zone nobody wanted would become a hole in the floor. Borrow the largest
    # room from the most crowded zone rather than leaving dead space.
    for zone in zones:
        if zone.rooms:
            continue
        donor = max((z for z in zones if len(z.rooms) > 1),
                    key=lambda z: z.load / max(z.rect.area_sqm, 0.01), default=None)
        if donor is None:
            continue
        room = max(donor.rooms, key=lambda r: float(r.get("target_sqm", 4.0)))
        donor.rooms.remove(room)
        zone.rooms.append(room)


# --------------------------------------------------------------------------
# Floor assembly
# --------------------------------------------------------------------------


def _room_order_key(room: dict[str, Any]) -> tuple[int, float]:
    # Daylight-hungry rooms first so the guillotine hands them the outer slices.
    light = room.get("light", "preferred")
    rank = {"required": 0, "preferred": 1, "none": 2}.get(light, 1)
    return (rank, -float(room.get("target_sqm", 4.0)))


def _touches_exterior(rect: Rect, net: Rect) -> list[str]:
    sides = []
    if rect.x0 <= net.x0:
        sides.append("left")
    if rect.x1 >= net.x1:
        sides.append("right")
    if rect.y0 <= net.y0:
        sides.append("front")
    if rect.y1 >= net.y1:
        sides.append("rear")
    return sides


def _swap_for_daylight(cells: list[Cell], net: Rect) -> None:
    """Post-pass: a bedroom in the middle and a bathroom on the window is the
    one mistake this kind of generator makes most often. Swap them when the two
    rooms are close enough in size that the trade costs nothing."""

    dark = [c for c in cells
            if c.role == "room" and c.brief.get("light") == "required"
            and not _touches_exterior(c.rect, net)]
    lit = [c for c in cells
           if c.role == "room" and c.brief.get("light") == "none"
           and _touches_exterior(c.rect, net)]

    for d in dark:
        for l in lit:
            a, b = d.rect.area_sqm, l.rect.area_sqm
            if min(a, b) / max(a, b) < 0.6:
                continue
            d.rect, l.rect = l.rect, d.rect
            lit.remove(l)
            break


def build_floor(floor_brief: dict[str, Any], sk: Skeleton, site: dict[str, Any],
                defaults: dict[str, Any]) -> dict[str, Any]:
    net = sk.net
    corridor_y0 = net.y0 + sk.front_depth
    cells: list[Cell] = []
    notes: list[str] = list(sk.notes)

    rooms = [dict(r) for r in floor_brief.get("rooms", [])]
    has_garage = bool(floor_brief.get("has_garage")) and sk.garage is not None

    if floor_brief.get("fill") == "fixed":
        _place_roof(rooms, sk, cells)
    else:
        reserved: list[Rect] = []

        corridor_rect = Rect(net.x0, corridor_y0, net.x1, corridor_y0 + sk.corridor_w)
        cells.append(Cell("corridor", "走道", "other", "corridor", corridor_rect))
        reserved.append(corridor_rect)
        if sk.spine:
            cells.append(Cell("corridor_spine", "走道（後段）", "other", "corridor", sk.spine))
            reserved.append(sk.spine)

        cells.append(Cell("stair", "樓梯間", "stair", "stair", sk.stair))
        reserved.append(sk.stair)

        if has_garage:
            cells.append(Cell("garage", "車庫", "service", "garage", sk.garage,
                              brief={"light": "none", "counts_in_footprint": True,
                                     "door_clear_mm": 2400, "private": False}))
            reserved.append(sk.garage)

        # Core-band rooms (MDF/IDF cabinets, tea bar) live in the core annex so
        # they land beside the riser instead of eating a daylit wall.
        core_rooms = [r for r in rooms if r.get("band") == "core"]
        other_rooms = [r for r in rooms if r.get("band") != "core"]
        if core_rooms and sk.core_annex is not None:
            reserved.append(sk.core_annex)
            placed = guillotine(sk.core_annex,
                                [(r["id"], float(r.get("target_sqm", 1.5))) for r in core_rooms])
            for r in core_rooms:
                rect = placed.get(r["id"])
                if rect:
                    cells.append(Cell(r["id"], r["name"], r.get("kind", "other"),
                                      "room", rect, brief=r))
        else:
            # No core-band rooms on this floor: give the annex strip back to the
            # zone pool rather than reserving dead space.
            other_rooms = rooms

        zones = make_zones(sk, reserved)
        assign_zones(other_rooms, zones)
        for zone in zones:
            picks = sorted(zone.rooms, key=_room_order_key)
            if not picks:
                cells.append(Cell(f"spare_{zone.id}", "未指定空間", "other", "room", zone.rect,
                                  brief={"light": "preferred", "private": False},
                                  flags=["UNASSIGNED_ZONE"]))
                continue
            placed = guillotine(zone.rect,
                                [(r["id"], float(r.get("target_sqm", 4.0))) for r in picks])
            for r in picks:
                rect = placed.get(r["id"])
                if rect:
                    cells.append(Cell(r["id"], r["name"], r.get("kind", "other"),
                                      "room", rect, brief=r))

        _swap_for_daylight(cells, net)

    # --- clear rects, walls, openings -----------------------------------
    ti = int(defaults["geometry"]["wall_thickness_mm"]["interior"])
    for cell in cells:
        cell.clear = _clear_rect(cell.rect, net, ti)

    walls = _build_walls(cells, net, defaults)
    doors = _build_doors(cells, net, site, defaults)
    windows = _build_windows(cells, net, defaults, doors)
    _cut_openings(walls, doors, windows, defaults)

    stair_info = stair_dims(site)
    stair_info["rect"] = sk.stair.as_list()

    return {
        "floor_id": floor_brief.get("floor_id"),
        "label": floor_brief.get("label"),
        "fill": floor_brief.get("fill", "expand"),
        "net_rect": net.as_list(),
        "front_depth_mm": sk.front_depth,
        "cells": [_cell_payload(c, net) for c in cells],
        "walls": walls,
        "doors": doors,
        "windows": windows,
        "stairs": stair_info,
        "notes": notes,
    }


def _place_roof(rooms: list[dict[str, Any]], sk: Skeleton, cells: list[Cell]) -> None:
    """RF is not a storey. Penthouse boxes keep their stated size (they are
    capped at 1/8 of the building area by law, so inflating them to fill the
    roof would be exactly the wrong answer); everything else is open deck."""

    net = sk.net
    stair_brief = next((r for r in rooms if r.get("kind") == "stair"), None)
    penthouse = [r for r in rooms if r.get("penthouse") and r is not stair_brief]
    deck = [r for r in rooms if not r.get("penthouse") and r is not stair_brief]

    # The stair head is the stair, not a second box beside it.
    cells.append(Cell(
        stair_brief["id"] if stair_brief else "rf_stair",
        stair_brief["name"] if stair_brief else "梯間屋突",
        "stair", "stair", sk.stair,
        brief=stair_brief or {"penthouse": True, "light": "none"},
    ))
    reserved: list[Rect] = [sk.stair]

    if penthouse:
        want = sum(float(r.get("target_sqm", 3.0)) for r in penthouse) * 1_000_000
        pw = int(min(max(want / max(sk.stair.d, 1), 1200), sk.stair.x0 - net.x0))
        if pw >= 1200:
            strip = Rect(sk.stair.x0 - pw, sk.stair.y0, sk.stair.x0, sk.stair.y1)
            reserved.append(strip)
            placed = guillotine(strip, [(r["id"], float(r.get("target_sqm", 3.0)))
                                        for r in penthouse])
            for r in penthouse:
                rect = placed.get(r["id"])
                if rect:
                    cells.append(Cell(r["id"], r["name"], r.get("kind", "service"),
                                      "room", rect, brief=r))

    zones = make_zones(sk, reserved)
    assign_zones(deck, zones)
    for zone in zones:
        picks = zone.rooms
        if not picks:
            cells.append(Cell(f"deck_{zone.id}", "露臺", "outdoor", "room", zone.rect,
                              brief={"counts_in_footprint": False, "light": "required",
                                     "penthouse": False}))
            continue
        placed = guillotine(zone.rect, [(r["id"], float(r.get("target_sqm", 8.0)))
                                        for r in picks])
        for r in picks:
            rect = placed.get(r["id"])
            if rect:
                cells.append(Cell(r["id"], r["name"], r.get("kind", "outdoor"),
                                  "room", rect, brief=r))


def _clear_rect(rect: Rect, net: Rect, ti: int) -> Rect:
    half = ti // 2
    return Rect(
        rect.x0 + (0 if rect.x0 <= net.x0 else half),
        rect.y0 + (0 if rect.y0 <= net.y0 else half),
        rect.x1 - (0 if rect.x1 >= net.x1 else half),
        rect.y1 - (0 if rect.y1 >= net.y1 else half),
    )


def _cell_payload(cell: Cell, net: Rect) -> dict[str, Any]:
    clear = cell.clear or cell.rect
    brief = cell.brief or {}
    flags = list(cell.flags)
    min_sqm = float(brief.get("min_sqm", 0) or 0)
    # A core-band service cell is an equipment niche beside the riser (MDF/IDF
    # rack, water manifold), not a room anybody stands in. Its depth is set by
    # the core annex, not by the guillotine, so the habitable-room minimum
    # dimension says nothing actionable about it.
    niche = brief.get("band") == "core" and cell.kind == "service"
    if cell.role == "room" and min_sqm and clear.area_sqm < min_sqm:
        flags.append("BELOW_MIN_AREA")
    if min(clear.w, clear.d) < MIN_ROOM_DIM_MM and cell.role == "room" and not niche:
        flags.append("TOO_NARROW")
    return {
        "id": cell.id,
        "name": cell.name,
        "kind": cell.kind,
        "role": cell.role,
        "rect": cell.rect.as_list(),
        "clear_rect": clear.as_list(),
        "area_sqm": round(clear.area_sqm, 2),
        "area_ping": round(clear.area_sqm / PING_TO_SQM, 2),
        "target_sqm": brief.get("target_sqm"),
        "min_sqm": brief.get("min_sqm"),
        "exterior_sides": _touches_exterior(cell.rect, net),
        "light": brief.get("light", "preferred"),
        "private": bool(brief.get("private")),
        "counts_in_footprint": brief.get("counts_in_footprint", cell.kind != "outdoor"),
        "penthouse": bool(brief.get("penthouse")),
        "wheelchair_turn": bool(brief.get("wheelchair_turn")),
        "niche": niche,
        "note": brief.get("note"),
        "flags": flags,
    }


# --------------------------------------------------------------------------
# Walls
# --------------------------------------------------------------------------


def _merge_intervals(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans)
    out = [list(spans[0])]
    for a, b in spans[1:]:
        if a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _build_walls(cells: list[Cell], net: Rect, defaults: dict[str, Any]) -> list[dict[str, Any]]:
    ext = int(defaults["geometry"]["wall_thickness_mm"]["exterior"])
    ti = int(defaults["geometry"]["wall_thickness_mm"]["interior"])
    walls: list[dict[str, Any]] = []

    # Exterior shell: four boxes, corners assigned to the side walls so nothing
    # is drawn twice.
    shell = [
        ("left", Rect(net.x0 - ext, net.y0 - ext, net.x0, net.y1 + ext), "v"),
        ("right", Rect(net.x1, net.y0 - ext, net.x1 + ext, net.y1 + ext), "v"),
        ("front", Rect(net.x0, net.y0 - ext, net.x1, net.y0), "h"),
        ("rear", Rect(net.x0, net.y1, net.x1, net.y1 + ext), "h"),
    ]
    for name, rect, orient in shell:
        walls.append({
            "id": f"wall_ext_{name}",
            "kind": "exterior",
            "orientation": orient,
            "box": rect.as_list(),
            "thickness_mm": ext,
            "openings": [],
        })

    # Interior partitions: every grid line that separates two cells.
    vertical: dict[int, list[tuple[int, int]]] = {}
    horizontal: dict[int, list[tuple[int, int]]] = {}
    for cell in cells:
        r = cell.rect
        if r.x0 > net.x0:
            vertical.setdefault(r.x0, []).append((r.y0, r.y1))
        if r.x1 < net.x1:
            vertical.setdefault(r.x1, []).append((r.y0, r.y1))
        if r.y0 > net.y0:
            horizontal.setdefault(r.y0, []).append((r.x0, r.x1))
        if r.y1 < net.y1:
            horizontal.setdefault(r.y1, []).append((r.x0, r.x1))

    half = ti // 2
    for x, spans in sorted(vertical.items()):
        for a, b in _merge_intervals(spans):
            walls.append({
                "id": f"wall_v_{x}_{a}",
                "kind": "interior",
                "orientation": "v",
                "box": [x - half, a, x - half + ti, b],
                "thickness_mm": ti,
                "openings": [],
            })
    for y, spans in sorted(horizontal.items()):
        for a, b in _merge_intervals(spans):
            walls.append({
                "id": f"wall_h_{y}_{a}",
                "kind": "interior",
                "orientation": "h",
                "box": [a, y - half, b, y - half + ti],
                "thickness_mm": ti,
                "openings": [],
            })

    return walls


# --------------------------------------------------------------------------
# Adjacency, doors, windows
# --------------------------------------------------------------------------


def _shared_edge(a: Rect, b: Rect) -> tuple[str, int, int, int] | None:
    """Return (orientation, line, span0, span1) for a shared wall, or None."""

    if a.x1 == b.x0 or b.x1 == a.x0:
        line = a.x1 if a.x1 == b.x0 else a.x0
        lo, hi = max(a.y0, b.y0), min(a.y1, b.y1)
        if hi - lo > 0:
            return ("v", line, lo, hi)
    if a.y1 == b.y0 or b.y1 == a.y0:
        line = a.y1 if a.y1 == b.y0 else a.y0
        lo, hi = max(a.x0, b.x0), min(a.x1, b.x1)
        if hi - lo > 0:
            return ("h", line, lo, hi)
    return None


def _door_width(cell: Cell, defaults: dict[str, Any]) -> int:
    doors = defaults["geometry"]["door_width_mm"]
    brief = cell.brief or {}
    if brief.get("door_clear_mm"):
        return int(brief["door_clear_mm"])
    kind = cell.kind
    if cell.role == "garage":
        return 2400
    if kind == "bath":
        return int(doors.get("bathroom", 800))
    if kind == "service":
        return int(doors.get("service", 800))
    if kind == "outdoor":
        return int(doors.get("service", 800))
    return int(doors.get("interior", 900))


def _build_doors(cells: list[Cell], net: Rect, site: dict[str, Any],
                 defaults: dict[str, Any]) -> list[dict[str, Any]]:
    doors: list[dict[str, Any]] = []
    by_id = {c.id: c for c in cells}
    circulation = {c.id for c in cells if c.role in ("corridor", "stair")}

    # Front door: on the front facade, into the entry (or whatever is at the front).
    entry = next((c for c in cells if c.kind == "entry"), None)
    if entry is None:
        entry = next((c for c in cells if c.role == "room" and c.rect.y0 <= net.y0), None)
    if entry is not None:
        w = int(defaults["geometry"]["door_width_mm"].get("entry", 1000))
        w = min(w, max(800, entry.rect.w - 2 * DOOR_EDGE_MARGIN_MM))
        doors.append({
            "id": "door_main",
            "from": "outside",
            "to": entry.id,
            "orientation": "h",
            "line": net.y0,
            "center": int(entry.rect.cx),
            "clear_mm": w,
            "swing": "outward",
            "role": "main_entrance",
        })

    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(cells):
        for b in cells[i + 1:]:
            key = tuple(sorted((a.id, b.id)))
            if key in seen:
                continue
            edge = _shared_edge(a.rect, b.rect)
            if edge is None:
                continue
            orient, line, lo, hi = edge

            # Which of the pair drives the door width? The more private one.
            target = b if (b.brief or {}).get("private") else a
            width = _door_width(target, defaults)
            usable = hi - lo - 2 * DOOR_EDGE_MARGIN_MM
            if usable < 700:
                continue
            width = min(width, usable)

            pair_roles = {a.role, b.role}
            wants_door = bool(circulation & {a.id, b.id}) or pair_roles & {"room", "garage"}
            if not wants_door:
                continue
            # Outdoor-to-outdoor (deck to deck) needs no door leaf.
            if a.kind == "outdoor" and b.kind == "outdoor":
                continue

            open_plan = (
                a.role == "room" and b.role == "room"
                and not (a.brief or {}).get("private") and not (b.brief or {}).get("private")
                and a.kind in ("living", "dining", "entry", "kitchen", "other")
                and b.kind in ("living", "dining", "entry", "kitchen", "other")
            )

            seen.add(key)
            doors.append({
                "id": f"door_{a.id}_{b.id}",
                "from": a.id,
                "to": b.id,
                "orientation": orient,
                "line": line,
                "center": int((lo + hi) / 2),
                "clear_mm": int(width),
                "swing": (b.brief or {}).get("door_swing") or (a.brief or {}).get("door_swing")
                          or ("open" if open_plan else "hinged"),
                "role": "opening" if open_plan else "door",
            })

    return doors


def _build_windows(cells: list[Cell], net: Rect, defaults: dict[str, Any],
                   doors: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    widths = defaults["geometry"]["window_width_mm"]
    metrics = defaults.get("architect_metrics", {})
    sill = int(metrics.get("window_sill_height_mm", 900))
    height = int(metrics.get("window_height_mm", 1200))

    out: list[dict[str, Any]] = []
    for cell in cells:
        if cell.role not in ("room", "stair") or cell.kind == "outdoor":
            continue
        if (cell.brief or {}).get("light") == "none" and cell.kind != "bath":
            continue
        sides = _touches_exterior(cell.rect, net)
        if not sides:
            continue

        # One window per room, on its longest exterior wall - enough to read the
        # space in 3D without pretending to be a fenestration study.
        best = None
        for side in sides:
            if side in ("left", "right"):
                span, line, orient = cell.rect.d, (net.x0 if side == "left" else net.x1), "v"
            else:
                span, line, orient = cell.rect.w, (net.y0 if side == "front" else net.y1), "h"
            if best is None or span > best[0]:
                best = (span, line, orient, side)
        span, line, orient, side = best

        w = int(widths.get(cell.kind, widths.get("other", 1000)))
        w = min(w, max(600, span - 2 * DOOR_EDGE_MARGIN_MM))
        if w < 600:
            continue

        if orient == "v":
            center = int(cell.rect.cy)
            lo, hi = cell.rect.y0, cell.rect.y1
        else:
            center = int(cell.rect.cx)
            lo, hi = cell.rect.x0, cell.rect.x1

        # A window centred on the room's exterior side can land exactly on top of
        # the front door, which is not a bay window - it is a door with a wall
        # across it. Slide the window clear, or drop it if there is no room.
        blocked = [d for d in (doors or [])
                   if d["orientation"] == orient and d["line"] == line]
        moved = _slide_clear(center, w, lo, hi, blocked)
        if moved is None:
            continue
        center = moved

        s, h = (1500, 600) if cell.kind == "bath" else (sill, height)
        out.append({
            "id": f"win_{cell.id}",
            "room": cell.id,
            "orientation": orient,
            "side": side,
            "line": line,
            "center": center,
            "width_mm": int(w),
            "sill_mm": s,
            "height_mm": h,
        })
    return out


def _slide_clear(center: int, width: int, lo: float, hi: float,
                 doors: list[dict[str, Any]]) -> int | None:
    """Nudge an opening of `width` off any door it overlaps, within [lo, hi].

    Returns the new centre, or None when the wall has no clear stretch wide
    enough - in which case the room simply gets no window, which is honest.
    """

    def hit(c: int) -> dict[str, Any] | None:
        a, b = c - width / 2, c + width / 2
        for d in doors:
            da = d["center"] - d["clear_mm"] / 2 - 60
            db = d["center"] + d["clear_mm"] / 2 + 60
            if b > da and a < db:
                return d
        return None

    if hit(center) is None:
        return center
    for d in sorted(doors, key=lambda x: x["center"]):
        for cand in (int(d["center"] - d["clear_mm"] / 2 - 60 - width / 2),
                     int(d["center"] + d["clear_mm"] / 2 + 60 + width / 2)):
            if cand - width / 2 < lo + DOOR_EDGE_MARGIN_MM:
                continue
            if cand + width / 2 > hi - DOOR_EDGE_MARGIN_MM:
                continue
            if hit(cand) is None:
                return cand
    return None


def _cut_openings(walls: list[dict[str, Any]], doors: list[dict[str, Any]],
                  windows: list[dict[str, Any]], defaults: dict[str, Any]) -> None:
    """Record each opening against the wall box it pierces.

    Stored as (t0, t1, z0, z1) along the wall's own axis so the 3D exporter can
    split the box into lintel/sill pieces without any CSG.
    """

    door_h = int(defaults["geometry"].get("door_height_mm", 2100))

    def attach(orientation: str, line: int, center: int, width: int,
               z0: int, z1: int, ref: str) -> bool:
        for wall in walls:
            if wall["orientation"] != orientation:
                continue
            x0, y0, x1, y1 = wall["box"]
            if orientation == "v":
                if not (x0 - 1 <= line <= x1 + 1):
                    continue
                lo, hi = y0, y1
            else:
                if not (y0 - 1 <= line <= y1 + 1):
                    continue
                lo, hi = x0, x1
            t0, t1 = center - width // 2, center + width // 2
            if t0 < lo or t1 > hi:
                continue
            wall["openings"].append({"t0": t0, "t1": t1, "z0": z0, "z1": z1, "ref": ref})
            return True
        return False

    for d in doors:
        z1 = door_h
        if d.get("role") == "opening":
            z1 = door_h + 200
        attach(d["orientation"], d["line"], d["center"], d["clear_mm"], 0, z1, d["id"])

    for w in windows:
        attach(w["orientation"], w["line"], w["center"], w["width_mm"],
               w["sill_mm"], w["sill_mm"] + w["height_mm"], w["id"])

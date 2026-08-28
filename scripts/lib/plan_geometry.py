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

Within each zone, rooms are placed by recursive division weighted by target
area. Guillotine is chosen over free packing for one concrete reason: it tiles
the zone exactly, so the generated plan can never grow the 1 mm slivers and
floor-sized holes that the CSS-derived geometry in
``structured/room_program.json`` is full of.

Pure guillotine has one failure mode worth naming, because the whole point of
this tool is to make bad fits visible rather than to hide them: with two items
every partition gives each a full-length strip, so a 5 m2 bathroom sharing a
5.6 x 6.2 m zone can only be 0.9 m wide or 0.8 m deep. Neither is a room. The
partitioner therefore also carves a corner - the move a human draughtsman makes
- and pays for it with a leftover rectangle, which becomes named slack instead
of being smeared into the neighbours. When no arrangement keeps every room over
``MIN_ROOM_DIM_MM``, the partition is reported infeasible rather than silently
returning the least-bad strip.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Sequence

PING_TO_SQM = 3.305785

# A door needs the wall segment it sits in to be wider than the door itself,
# or the opening eats the corner and there is nothing left to hang it on.
DOOR_EDGE_MARGIN_MM = 150
# Below this a shared edge cannot hold a door leaf at all. It used to be the
# gate that decided *whether* two rooms were connected, which is how a 1083 mm
# party wall ended up with a 783 mm door in it; now it only rules out edges too
# short to build in, and the connection itself is a stated decision.
DOOR_MIN_CLEAR_MM = 700
MIN_ROOM_DIM_MM = 1500

# Roof equipment is not a room. A water tank stand or a heat-pump pad is sized
# by the machine plus the space a technician needs to reach it, so the 1500 mm
# habitable minimum says nothing useful about it - it would condemn a perfectly
# ordinary 1.2 m wide plant strip while ignoring a 2 m square with no way in.
# The classes here are the statutory 目 from 建築技術規則建築設計施工編 第 1 條;
# only 第一目 (enclosed stair hall / machine room) is a space people occupy.
EQUIPMENT_PENTHOUSE_CLASSES = ("tank", "open_mep", "energy")
EQUIP_ACCESS_MM = 900

# The garage cannot take the whole frontage: the front door has to be beside it,
# and an entry narrower than this is not an entry.
GARAGE_SIDE_STRIP_MM = 2400

# Tiling a zone completely is a generator policy, not something the brief owes
# us. When a zone holds more area than its rooms asked for, the surplus used to
# be smeared across those rooms in proportion to target_sqm - which is how a
# 20 m2 media room came out at 34.5 and a 5 m2 toilet at 20. Rooms may grow by
# FLEX_TOLERANCE (real rooms need slack for furniture and wall build-up); the
# rest becomes one named cell so the leftover has to be looked at instead of
# quietly inflating a bedroom.
FLEX_TOLERANCE = 0.15
# Below this a flex cell is a sliver nobody can use, and the rooms are better
# off absorbing it.
FLEX_MIN_SQM = 4.0


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
    # Which band the room actually landed in, filled once the rects are final.
    # ``assign_zones`` honours the brief's ``band`` "where stated", and where it
    # could not the room simply moved - silently, because nothing compared the
    # two afterwards. A 後工作陽台 ended up on the street facade in four variants
    # and no report said so.
    band_actual: str = ""


# --------------------------------------------------------------------------
# Guillotine subdivision
# --------------------------------------------------------------------------


def _aspect(rect: Rect) -> float:
    if rect.w <= 0 or rect.d <= 0:
        return 99.0
    return max(rect.w, rect.d) / min(rect.w, rect.d)


@dataclass
class Partition:
    """A tiling of one rectangle.

    ``placed`` maps item id to rect. ``residual`` holds rectangles a corner
    carve left over - real floor area belonging to nobody, which the caller
    turns into named slack so it stays visible. ``feasible`` is False when any
    rect in the tiling is under the usable minimum; the caller decides whether
    to fall back to another arrangement or to place it anyway and flag it.
    """

    placed: dict[str, Rect] = field(default_factory=dict)
    residual: list[Rect] = field(default_factory=list)
    feasible: bool = True


def _fits_any(rect: Rect) -> bool:
    return rect.valid


def _merge(a: Partition, b: Partition) -> Partition:
    placed = dict(a.placed)
    placed.update(b.placed)
    return Partition(placed, a.residual + b.residual, a.feasible and b.feasible)


def _score(part: Partition, items: Sequence[tuple[str, float]]) -> tuple:
    """Rank candidate tilings. Feasibility first - a partition that leaves a
    bedroom 0.9 m wide is not merely a worse score, it is not a plan. Then
    leftover area (a corner carve should not be used to dodge a fine split),
    then how far each room lands from its requested share, then squareness.
    """
    total = sum(max(w, 0.01) for _, w in items) or 1.0
    assigned = sum(r.area_sqm for r in part.placed.values())
    leftover = sum(r.area_sqm for r in part.residual)
    pool = assigned + leftover
    err = 0.0
    for iid, weight in items:
        rect = part.placed.get(iid)
        if rect is None:
            continue
        want = pool * max(weight, 0.01) / total
        err += ((rect.area_sqm - want) / max(want, 0.01)) ** 2
    worst = max((_aspect(r) for r in part.placed.values()), default=99.0)
    return (0 if part.feasible else 1, round(leftover, 2), round(err, 4), round(worst, 3))


def _split_candidates(rect: Rect, items: Sequence[tuple[str, float]],
                      fits) -> Iterable[Partition]:
    """Every binary cut: both axes, every contiguous grouping of the items.

    The old version only ever cut the longer side, which is a reasonable
    anti-corridor heuristic and also the reason a 14 m2 room and a 5 m2 bathroom
    in a 5.6 m wide zone could never come out as anything but two bands.
    """
    total = sum(max(w, 0.01) for _, w in items)
    for k in range(1, len(items)):
        frac = sum(max(w, 0.01) for _, w in items[:k]) / total
        for horizontal in (True, False):
            if horizontal:
                a, b = _split_x(rect, rect.x0 + int(round(rect.w * frac)))
            else:
                a, b = _split_y(rect, rect.y0 + int(round(rect.d * frac)))
            if not a.valid or not b.valid:
                continue
            yield _merge(_partition(a, items[:k], fits),
                         _partition(b, items[k:], fits))


def _carve_candidates(rect: Rect, items: Sequence[tuple[str, float]],
                      fits) -> Iterable[Partition]:
    """Take the smallest item out of a corner and split the L-shaped remainder.

    The remainder of a corner cut is an L, and an L is not a rect, so it is
    decomposed into two rectangles - two ways round, four corners, a few aspect
    ratios for the carved room. Whatever the remaining items do not use becomes
    residual. Candidates whose residual is itself unusable are dropped: leftover
    area is acceptable, leftover slivers are not, and dropping them is also what
    keeps the zone exactly tiled.
    """
    idx = min(range(len(items)), key=lambda i: max(items[i][1], 0.01))
    cid, weight = items[idx]
    rest = [it for i, it in enumerate(items) if i != idx]
    total = sum(max(w, 0.01) for _, w in items)
    want_mm2 = rect.w * rect.d * max(weight, 0.01) / total

    widths = {int(math.sqrt(want_mm2)), MIN_ROOM_DIM_MM,
              int(want_mm2 // MIN_ROOM_DIM_MM), rect.w // 2}
    for cw in sorted(widths):
        if not (MIN_ROOM_DIM_MM <= cw <= rect.w - MIN_ROOM_DIM_MM):
            continue
        cd = int(round(want_mm2 / cw))
        if not (MIN_ROOM_DIM_MM <= cd <= rect.d - MIN_ROOM_DIM_MM):
            continue
        for right in (False, True):
            for rear in (False, True):
                cx0 = rect.x1 - cw if right else rect.x0
                cy0 = rect.y1 - cd if rear else rect.y0
                carve = Rect(cx0, cy0, cx0 + cw, cy0 + cd)
                side_x = Rect(rect.x0, cy0, cx0, cy0 + cd) if right \
                    else Rect(cx0 + cw, cy0, rect.x1, cy0 + cd)
                band_y = Rect(rect.x0, rect.y0, rect.x1, cy0) if rear \
                    else Rect(rect.x0, cy0 + cd, rect.x1, rect.y1)
                side_y = Rect(cx0, rect.y0, cx0 + cw, cy0) if rear \
                    else Rect(cx0, cy0 + cd, cx0 + cw, rect.y1)
                band_x = Rect(rect.x0, rect.y0, cx0, rect.y1) if right \
                    else Rect(cx0 + cw, rect.y0, rect.x1, rect.y1)
                for first, second in ((side_x, band_y), (side_y, band_x)):
                    if not (first.valid and second.valid):
                        continue
                    for k in range(0, len(rest) + 1):
                        pa = _partition(first, rest[:k], fits)
                        pb = _partition(second, rest[k:], fits)
                        cand = _merge(pa, pb)
                        cand.placed[cid] = carve
                        cand.feasible = cand.feasible and fits(carve)
                        yield cand


def _partition(rect: Rect, items: Sequence[tuple[str, float]], fits) -> Partition:
    """Tile ``rect`` among ``items`` (id, weight), best arrangement first."""
    if not items:
        return Partition({}, [rect] if rect.valid else [], rect.valid and fits(rect))
    if len(items) == 1:
        return Partition({items[0][0]: rect}, [], rect.valid and fits(rect))

    best: Partition | None = None
    best_score: tuple | None = None
    for cand in _split_candidates(rect, items, fits):
        score = _score(cand, items)
        if best_score is None or score < best_score:
            best, best_score = cand, score
    # A corner carve costs floor area, so it is only worth trying when no clean
    # cut exists. Reaching for it earlier would trade real rooms for slack.
    if best is None or not best.feasible:
        for cand in _carve_candidates(rect, items, fits):
            score = _score(cand, items)
            if best_score is None or score < best_score:
                best, best_score = cand, score

    if best is not None:
        return best
    # Nothing valid at all (degenerate rect): fall back to a proportional cut so
    # the zone still tiles, and let the caller see it as infeasible.
    total = sum(max(w, 0.01) for _, w in items)
    k = max(1, len(items) // 2)
    frac = sum(max(w, 0.01) for _, w in items[:k]) / total
    if rect.w >= rect.d:
        a, b = _split_x(rect, rect.x0 + int(round(rect.w * frac)))
    else:
        a, b = _split_y(rect, rect.y0 + int(round(rect.d * frac)))
    out = _merge(_partition(a, items[:k], fits), _partition(b, items[k:], fits))
    out.feasible = False
    return out


def guillotine(rect: Rect, items: Sequence[tuple[str, float]]) -> dict[str, Rect]:
    """Tile ``rect`` among ``items`` with no minimum-dimension constraint.

    Used where the caller has already fixed the geometry (core annex niches,
    roof strips) and only wants the weighted division.
    """
    return _partition(rect, items, _fits_any).placed


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
    # The historical generator does not draw an independent pipe-shaft cell.
    # This legacy setting only reserves extra width in the overall core; actual
    # shaft geometry must come from an architect drawing revision.
    core_service_w = int(site.get("core", {}).get("shaft_w_mm", 600))

    core_w = min(stair["w_mm"] + core_service_w, max(2100, net.w // 2))
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
        fits = [r for r in donor.rooms
                if float(r.get("target_sqm", 4.0)) <= zone.rect.area_sqm] or donor.rooms
        room = min(fits, key=lambda r: float(r.get("target_sqm", 4.0)))
        donor.rooms.remove(room)
        zone.rooms.append(room)


def _narrow_ids(placed: dict[str, Rect], rooms: list[dict],
                net: Rect, ti: int) -> set:
    """Ids of `rooms` whose *clear* rectangle is under the minimum dimension.

    Measured after wall build-up, the same way `_cell_payload` decides
    TOO_NARROW - a margin guessed on the gross rect is either too slack to
    catch anything or strict enough to veto placements that are actually fine.
    """
    out = set()
    for r in rooms:
        rect = placed.get(r["id"])
        if rect is None:
            continue
        clear = _clear_rect(rect, net, ti)
        if min(clear.w, clear.d) < MIN_ROOM_DIM_MM:
            out.add(r["id"])
    return out


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
    # Flex cells are donors too: unassigned area sitting on the facade while a
    # bedroom looks at an internal wall is the worst trade on the floor.
    lit = [c for c in cells
           if _touches_exterior(c.rect, net)
           and ((c.role == "room" and c.brief.get("light") == "none")
                or c.role == "flex")]

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
        ti_clear = int(defaults["geometry"]["wall_thickness_mm"]["interior"])
        for zone in zones:
            picks = sorted(zone.rooms, key=_room_order_key)
            if not picks:
                cells.append(Cell(f"spare_{zone.id}", "未指定空間", "other", "room", zone.rect,
                                  brief={"light": "preferred", "private": False},
                                  flags=["UNASSIGNED_ZONE"]))
                continue
            items = [(r["id"], float(r.get("target_sqm", 4.0))) for r in picks]
            # The minimum is on the *clear* rect, after wall build-up - the
            # dimension somebody actually stands in, and the same one
            # `_cell_payload` flags on. Checking the gross rect instead would
            # pass rooms that finish 1.44 m wide.
            def fits(rect: Rect, _net=net, _ti=ti_clear) -> bool:
                clear = _clear_rect(rect, _net, _ti)
                return min(clear.w, clear.d) >= MIN_ROOM_DIM_MM
            # Surplus beyond what the rooms asked for (plus tolerance) becomes a
            # named cell rather than being shared out. It goes last in the item
            # list so the daylight-ordered rooms get the outer slices first.
            flex_id = f"flex_{zone.id}"
            flex_sqm = zone.rect.area_sqm - zone.load * (1.0 + FLEX_TOLERANCE)
            part = _partition(zone.rect, items, fits)
            if flex_sqm >= FLEX_MIN_SQM:
                with_flex = _partition(zone.rect, items + [(flex_id, flex_sqm)], fits)
                # Withholding area from the rooms is only an improvement while
                # they stay usable. A cut that leaves a bedroom 1.36 m deep so
                # the leftover can be 1.59 m has made the plan worse, and the
                # honest reading is that this zone's surplus really is the rooms'
                # breathing room. Only keep the flex cell when it does not push a
                # room under the minimum it was already clearing.
                if not (_narrow_ids(with_flex.placed, picks, net, ti_clear)
                        - _narrow_ids(part.placed, picks, net, ti_clear)):
                    part = with_flex
            placed = part.placed
            # No arrangement of this zone keeps every room usable. That is a
            # statement about the brief, not about this particular cut, so it is
            # flagged separately from the per-cell TOO_NARROW it also produces.
            zone_flags = [] if part.feasible else ["ZONE_NO_FIT"]
            for r in picks:
                rect = placed.get(r["id"])
                if rect:
                    cells.append(Cell(r["id"], r["name"], r.get("kind", "other"),
                                      "room", rect, brief=r,
                                      flags=list(zone_flags)))
            slack = [placed[flex_id]] if flex_id in placed else []
            # Corner carves buy a usable room shape by leaving a rectangle over.
            # It is floor area somebody is paying for, so it gets drawn and named
            # like any other slack rather than quietly disappearing.
            slack.extend(part.residual)
            for n, rect in enumerate(slack):
                cells.append(Cell(f"{flex_id}_{n}" if n else flex_id,
                                  "彈性餘裕（未指定用途）", "other", "flex", rect,
                                  brief={"light": "preferred", "private": False},
                                  flags=["UNPROGRAMMED"] + zone_flags))

        _swap_for_daylight(cells, net)

    # --- clear rects, walls, openings -----------------------------------
    ti = int(defaults["geometry"]["wall_thickness_mm"]["interior"])
    # Same line make_zones splits on, applied to where the room finally sits
    # rather than to the zone it was handed. Guillotine cuts and daylight swaps
    # both move rooms after assignment, so the zone's band is not the answer.
    corridor_y0 = sk.net.y0 + sk.front_depth
    for cell in cells:
        cell.clear = _clear_rect(cell.rect, net, ti)
        cell.band_actual = "front" if cell.rect.cy < corridor_y0 else "rear"

    walls = _build_walls(cells, net, defaults)
    doors = _build_doors(cells, net, site, defaults, floor_brief.get("floor_id"))
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
    """RF is not a storey. Penthouse boxes keep their stated size - the law caps
    the *sum* of roof projections, so inflating them to fill the roof would be
    exactly the wrong answer; everything else is open deck."""

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
        span = sk.stair.x0 - net.x0
        want = sum(float(r.get("target_sqm", 3.0)) for r in penthouse) * 1_000_000
        pw = int(min(max(want / max(sk.stair.d, 1), 1200), span))
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

            # Whatever is left between the plant strip and the outer wall is the
            # aisle somebody stands in to service the tank and the heat pump.
            # Unnamed, it surfaced as a 1.1 m "露臺" on all three roofs - dead
            # space in the report and a TOO_NARROW that meant nothing. It is not
            # 屋頂突出物 either: clearance is not a box, so it stays out of the
            # projection sum.
            # Capped: an aisle is a place to stand, and past ~1.8 m the rest is
            # just roof. At a 10 m frontage the uncapped version swallowed
            # 15.7 m² and called it clearance.
            aisle = min(span - pw, 1800)
            rest = Rect(strip.x0 - aisle, sk.stair.y0, strip.x0, sk.stair.y1)
            if rest.valid and rest.w >= 600:
                reserved.append(rest)
                cells.append(Cell(
                    "rf_service_aisle", "設備維修淨空", "outdoor", "room", rest,
                    brief={"counts_in_footprint": False, "light": "none",
                           "penthouse": False, "service_clearance": True,
                           "note": "水塔與熱泵旁的維修動線。不是露臺，也不計入屋突水平投影面積。"}))

    zones = make_zones(sk, reserved)
    assign_zones(deck, zones)
    # Zones the brief left empty become open deck. Two of them on one roof used
    # to come out both called 露臺, which reads as a duplicate in every table and
    # in the 3D picker; name them by where they actually are.
    band_label = {"front": "前側露臺", "rear": "後側露臺"}
    empty_bands = [z.band for z in zones if not z.rooms]
    seq: dict[str, int] = {}
    for zone in zones:
        picks = zone.rooms
        if not picks:
            base = band_label.get(zone.band, "露臺")
            seq[zone.band] = seq.get(zone.band, 0) + 1
            name = base if empty_bands.count(zone.band) == 1 else f"{base} {seq[zone.band]}"
            cells.append(Cell(f"deck_{zone.id}", name, "outdoor", "room", zone.rect,
                              brief={"counts_in_footprint": False, "light": "required",
                                     "penthouse": False}))
            continue
        items = [(r["id"], float(r.get("target_sqm", 8.0))) for r in picks]
        # Deck rooms expand to fill their zone, which is right for a drying yard
        # and wrong for equipment: a solar array is as big as the array, not as
        # big as the roof it stands on. Left to inflate, A's 12 m² of panels came
        # out at 36 m² and pushed the building over the 屋頂突出物 cap - a limit
        # breached by the fill policy rather than by the design. Anything with a
        # statutory class keeps its stated size; the surplus becomes named deck.
        want = sum(w for _, w in items)
        spare = zone.rect.area_sqm - want
        filler = None
        if (any(r.get("penthouse_class") for r in picks)
                and spare > max(FLEX_MIN_SQM, want * FLEX_TOLERANCE)):
            filler = f"deck_{zone.id}"
            items.append((filler, spare))
        placed = guillotine(zone.rect, items)
        if filler and placed.get(filler):
            cells.append(Cell(filler, band_label.get(zone.band, "露臺"), "outdoor",
                              "room", placed[filler],
                              brief={"counts_in_footprint": False,
                                     "light": "required", "penthouse": False}))
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
    niche = _is_niche(cell)
    pclass = brief.get("penthouse_class")
    equipment = pclass in EQUIPMENT_PENTHOUSE_CLASSES
    clearance = bool(brief.get("service_clearance"))
    if cell.role == "room" and min_sqm and clear.area_sqm < min_sqm:
        flags.append("BELOW_MIN_AREA")
    if clearance:
        pass          # an aisle is as wide as what is left; nothing to assert
    elif equipment:
        # Machines, not people: what matters is whether a technician can get to
        # the thing, so the test is an access aisle rather than a room width.
        if min(clear.w, clear.d) < EQUIP_ACCESS_MM:
            flags.append("EQUIP_ACCESS_TIGHT")
    # Flex is checked too: leftover area shaped like a 1 m corridor is not
    # usable by anybody, and that is exactly the thing worth seeing.
    elif (min(clear.w, clear.d) < MIN_ROOM_DIM_MM
            and cell.role in ("room", "flex") and not niche):
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
        "band": brief.get("band", "auto"),
        "band_actual": cell.band_actual,
        "light": brief.get("light", "preferred"),
        "private": bool(brief.get("private")),
        "counts_in_footprint": brief.get("counts_in_footprint", cell.kind != "outdoor"),
        "penthouse": bool(brief.get("penthouse")),
        "penthouse_class": pclass,
        "counts_in_projection": brief.get("counts_in_projection"),
        "service_clearance": clearance,
        "wheelchair_turn": bool(brief.get("wheelchair_turn")),
        # The rule layer asks for these by name; without them the palanquin
        # check silently fell back to a 1200 default and the declared 900 mm
        # accessible-WC width was never actually the number being tested.
        "min_door_mm": brief.get("door_clear_mm"),
        "access_from": brief.get("access_from") or [],
        "open_plan": bool(brief.get("open_plan")),
        "carry_path": bool(brief.get("carry_path")),
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


def _is_niche(cell: Cell) -> bool:
    """An equipment cabinet beside the riser (MDF/IDF rack, water manifold).
    It has a door leaf in reality, but it is a hatch you reach into, not a way
    through to anywhere."""

    return (cell.brief or {}).get("band") == "core" and cell.kind == "service"


def _access_tier(host: Cell) -> int | None:
    """How willing we are to walk through ``host`` to reach somewhere else.

    Tier 0-1 is what circulation exists for. Tier 2 is the entry hall. Tier 3
    is a shared room - acceptable, and worth saying out loud. Tier 4 means the
    only way through is somebody's bedroom, which is a finding, not a plan.
    ``None`` means never: a riser has no door, and you do not walk through a
    rack cabinet to get somewhere - left in the running it won on width alone
    and 神明廳 came out entered via the IDF cupboard.
    """

    if host.role == "shaft" or _is_niche(host):
        return None
    if host.role == "corridor":
        return 0
    if host.role == "stair":
        return 1
    if host.kind == "entry":
        return 2
    if host.role in ("room", "garage", "flex"):
        return 4 if (host.brief or {}).get("private") else 3
    return None


def _widest_route(doors: list[dict[str, Any]], start: str,
                  goal: str) -> list[dict[str, Any]] | None:
    """The route whose narrowest opening is as wide as possible, returned as
    the doors on it. Same question the palanquin check asks; asked here so the
    generator can widen those doors instead of only reporting them.

    The two must be asked over the same graph or the widening lands on doors
    nobody checks: left to itself this walked the 武轎 in through the 2815 mm
    garage roller door, widened that route, and the front door - which is what
    the rule actually measures - stayed at 1000. Hatches are out for the same
    reason they are out of :class:`Circulation`: a rack cabinet is not a way
    through.
    """

    adj: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for d in doors:
        if d.get("role") in ("hatch", "vehicle_door"):
            continue
        adj.setdefault(d["from"], []).append((d["to"], d))
        adj.setdefault(d["to"], []).append((d["from"], d))
    best = {start: 10 ** 9}
    trail: dict[str, list[dict[str, Any]]] = {start: []}
    pool = {start}
    while pool:
        node = max(pool, key=lambda n: best[n])
        pool.discard(node)
        if node == goal:
            return trail[node]
        for nxt, door in adj.get(node, []):
            width = min(best[node], int(door["clear_mm"]))
            if width > best.get(nxt, -1):
                best[nxt] = width
                trail[nxt] = trail[node] + [door]
                pool.add(nxt)
    return None


def _build_doors(cells: list[Cell], net: Rect, site: dict[str, Any],
                 defaults: dict[str, Any],
                 floor_id: str | None = None) -> list[dict[str, Any]]:
    """One designated way into every space, plus whatever the brief declares open.

    The earlier version put a door on every shared edge where either side was a
    room or circulation. That is not a plan, it is a graph: a 1F came out with
    fifteen doors, the accessible WC opened onto the corridor *and* the entry
    hall *and* the garage, and a 1083 mm party wall produced a 783 mm door
    nobody had asked for. Worse, the rule checks then ran on that graph - the
    kitchen reached the balcony because of an accidental opening, and the
    palanquin route measured a bottleneck that was never designed.

    So access is now stated rather than discovered. Each space gets exactly one
    entrance, from the brief's ``access_from`` when it says, otherwise from the
    nearest thing that is meant to be walked through. Extra openings exist only
    where the brief declares ``open_plan`` - which also keeps 穿堂煞 an explicit
    decision instead of a side effect of two rooms happening to touch.
    """

    doors: list[dict[str, Any]] = []
    by_id = {c.id: c for c in cells}
    index: dict[frozenset[str], dict[str, Any]] = {}

    # --- adjacency: every shared edge long enough to hold a leaf ------------
    edges: dict[str, dict[str, tuple[str, int, int, int, int]]] = {c.id: {} for c in cells}
    for i, a in enumerate(cells):
        for b in cells[i + 1:]:
            edge = _shared_edge(a.rect, b.rect)
            if edge is None:
                continue
            orient, line, lo, hi = edge
            usable = hi - lo - 2 * DOOR_EDGE_MARGIN_MM
            if usable < DOOR_MIN_CLEAR_MM:
                continue
            info = (orient, line, lo, hi, usable)
            edges[a.id][b.id] = info
            edges[b.id][a.id] = info

    def connect(host: Cell, served: Cell, role: str,
                want: int | None = None) -> dict[str, Any] | None:
        key = frozenset((host.id, served.id))
        if key in index:
            return index[key]
        orient, line, lo, hi, usable = edges[host.id][served.id]
        width = min(want or _door_width(served, defaults), usable)
        swing = ((served.brief or {}).get("door_swing")
                 or (host.brief or {}).get("door_swing")
                 or ("open" if role == "opening" else "hinged"))
        door = {
            "id": f"door_{host.id}_{served.id}",
            "from": host.id,
            "to": served.id,
            "orientation": orient,
            "line": line,
            "center": int((lo + hi) / 2),
            "clear_mm": int(width),
            "usable_mm": int(usable),
            "swing": "open" if role == "opening" else swing,
            "role": role,
        }
        doors.append(door)
        index[key] = door
        return door

    # --- front door --------------------------------------------------------
    # 1F only. This block ran on every floor, and above 1F there is no 玄關, so
    # the fallback below picked whichever room happened to sit on the front
    # edge and cut a 1000 mm door from it to "outside" - a hole in the 3F
    # facade opening onto nothing. It also handed ``FRONT_REAR_ALIGNED`` a fake
    # 大門 on three floors out of four, so the 穿堂煞 result on those floors was
    # measured against a door that does not exist.
    entry = None
    if floor_id == "floor-1":
        entry = next((c for c in cells if c.kind == "entry"), None)
        if entry is None:
            entry = next((c for c in cells
                          if c.role == "room" and c.rect.y0 <= net.y0), None)
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
            "usable_mm": int(entry.rect.w - 2 * DOOR_EDGE_MARGIN_MM),
            "swing": "outward",
            "role": "main_entrance",
        })

    # --- the car's own way in ---------------------------------------------
    # The garage was reachable only from inside the house, which is the one
    # thing a garage cannot be. It fronts the street, so the vehicle door goes
    # on the front facade at the width of the bay.
    for g in (c for c in cells if c.role == "garage"):
        if g.rect.y0 > net.y0:
            continue
        leaf = min(g.rect.w - 2 * DOOR_EDGE_MARGIN_MM, 3000)
        if leaf < 2200:
            g.flags.append("GARAGE_DOOR_NARROW")
        doors.append({
            "id": f"door_{g.id}_street", "from": "outside", "to": g.id,
            "orientation": "h", "line": net.y0, "center": int(g.rect.cx),
            "clear_mm": int(max(leaf, 0)),
            "usable_mm": int(g.rect.w - 2 * DOOR_EDGE_MARGIN_MM),
            "swing": "roller", "role": "vehicle_door",
        })

    # --- circulation is continuous by construction, not by door ------------
    # With one exception, and it is the one the brief spells out twice: the
    # stair mouth on 1F. design_request.md asks for 樓梯口氣密門 as B's stair line
    # (「避開神桌正沖，加氣密防煙」) and again as Q8 (「樓梯口氣密門是否能防止香火味
    # 往上跑？」), and the HTML sketches carry it as a named cell on A 1F
    # (樓梯口隔斷門) and C 1F (樓梯前拉門阻隔). Left to the general rule it came out
    # as a 2400 mm hole with no leaf - the exact condition Q8 was asking about,
    # built into the model that was supposed to answer it.
    #
    # 1F only: nothing in either source asks for one upstairs, and the smoke it
    # exists to stop starts at the 神明廳 on 1F.
    seal_stair = floor_id == "floor-1"
    circulation = [c for c in cells if c.role in ("corridor", "stair")]
    for i, a in enumerate(circulation):
        for b in circulation[i + 1:]:
            if b.id not in edges[a.id]:
                continue
            if seal_stair and {a.role, b.role} == {"corridor", "stair"}:
                host, served = (a, b) if a.role == "corridor" else (b, a)
                connect(host, served, "smoke_door",
                        want=int(defaults["geometry"]["door_width_mm"]
                                 .get("interior", 900)))
            else:
                connect(a, b, "opening", want=edges[a.id][b.id][4])

    # --- one designated entrance per space ---------------------------------
    # Grown outwards from the circulation rather than chosen room by room. The
    # per-room version looked equivalent and was not: two rooms whose best
    # neighbour was each other picked each other, sharing a single door and
    # forming an island with no way to the stairs. The plan looked plausible
    # and A's master bedroom was unreachable.
    parent: dict[str, str] = {c.id: c.id for c in cells}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Seeded with the circulation alone. Having a front door is not the same as
    # being connected to the house: B's entry hall opens only onto the palanquin
    # store, and seeding it as reached declared the problem solved and left the
    # hall a dead end.
    reached = circulation[0].id if circulation else None
    if reached is None:
        return doors
    for c in circulation:
        union(c.id, reached)

    def link(host: Cell, served: Cell) -> None:
        role = "hatch" if _is_niche(served) else "entrance"
        width = None
        if served.kind == "entry" and host.role in ("corridor", "stair"):
            # A 玄關 opens onto the hallway; nobody hangs a leaf between them.
            role, width = "opening", edges[served.id][host.id][4]
        elif served.role == "garage":
            # The 2400 in _door_width is the vehicle opening, already on the
            # facade; the way through from the house is an ordinary door.
            width = int(defaults["geometry"]["door_width_mm"].get("interior", 900))
        connect(host, served, role, want=width)
        union(served.id, host.id)

    needs = [c for c in cells if c.role not in ("corridor", "stair", "shaft")]

    # Declared relations first, and unconditionally: "衛浴由主臥進" is a decision
    # about this pair, not about how the pair reaches the stairs. Wiring it up
    # front lets the ensuite and the master arrive as one component.
    for cell in needs:
        declared = (cell.brief or {}).get("access_from") or []
        if not declared:
            continue
        pick = next((nid for want in declared for nid in edges[cell.id]
                     if want in (nid, by_id[nid].role, by_id[nid].kind)), None)
        if pick is None:
            # "從主臥進" cannot be honoured when the master bedroom ended up on
            # the other side of the plan. Falling back silently would turn a
            # brief the layout failed to satisfy into a layout that looks fine.
            cell.flags.append("ACCESS_UNREALISABLE")
            continue
        link(by_id[pick], cell)

    # Then pull the remaining components in, best edge first.
    while True:
        best: tuple[int, int, str, str] | None = None
        for cell in needs:
            if find(cell.id) == find(reached):
                continue
            for nid, edge in edges[cell.id].items():
                if find(nid) != find(reached):
                    continue
                tier = _access_tier(by_id[nid])
                if tier is None:
                    continue
                cand = (tier, -edge[4], cell.id, nid)
                if best is None or cand < best:
                    best = cand
        if best is None:
            break
        tier, _, cid, hid = best
        if tier == 4 and not (by_id[cid].brief or {}).get("access_from"):
            by_id[cid].flags.append("NESTED_ACCESS")
        link(by_id[hid], by_id[cid])

    facade = {d["to"] for d in doors if d["from"] == "outside"}
    for cell in needs:
        if find(cell.id) != find(reached) and cell.id not in facade:
            cell.flags.append("NO_ACCESS")

    # --- declared open plan ------------------------------------------------
    for i, a in enumerate(cells):
        if not (a.brief or {}).get("open_plan"):
            continue
        for b in cells[i + 1:]:
            if not (b.brief or {}).get("open_plan"):
                continue
            if b.id not in edges[a.id]:
                continue
            connect(a, b, "opening", want=edges[a.id][b.id][4])

    # --- carry routes ------------------------------------------------------
    # 武轎: the object is rigid and the crew carries it shoulder-high, so every
    # opening on the way has to take it - including the front door, which the
    # 1000 mm entry default does not. Widening here rather than only reporting
    # it means the walkthrough shows the doorway the carry actually needs.
    for cell in cells:
        if not (cell.brief or {}).get("carry_path"):
            continue
        need = int((cell.brief or {}).get("door_clear_mm") or 1200)
        route = _widest_route(doors, "outside", cell.id)
        if route is None:
            cell.flags.append("NO_CARRY_ROUTE")
            continue
        for door in route:
            if door["clear_mm"] >= need:
                continue
            door["clear_mm"] = min(need, door["usable_mm"])
            door["carry_route"] = True
            if door["clear_mm"] < need:
                cell.flags.append("CARRY_ROUTE_TIGHT")

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

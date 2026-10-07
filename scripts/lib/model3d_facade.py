"""Non-mutating facade proposal, shared by the offline 3D and HTML elevations.

All boxes use plan X/Y and absolute elevation Z in millimetres. Boundary walls
come from the union of active indoor ``tour_mm`` cells, not a second floor plan.
Checks are conservative concept geometry screens, NEVER regulatory approval.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from lib.model3d_placement import overlaps
from lib.standards import repo_relative

ROOT = Path(__file__).resolve().parents[2]
FACADE_FILE = ROOT / "inputs/facade-concept.json"
SCHEMA = "house-facade-layer-v1"
STATUS = "proposal-owner-and-architect-review-pending"
FACES = ("front", "rear", "left", "right")


def _interval(g: dict, face: str) -> tuple[float, float, float]:
    if face in {"front", "rear"}:
        return g["x_mm"], g["x_mm"] + g["w_mm"], g["y_mm"] + (g["h_mm"] if face == "rear" else 0)
    return g["y_mm"], g["y_mm"] + g["h_mm"], g["x_mm"] + (g["w_mm"] if face == "right" else 0)


def boundary_segments(cell: dict, neighbors: list[dict], face: str) -> list[tuple[float, float]]:
    """Subtract every touching neighbor, including contacts narrower than doors."""
    lo, hi, edge = _interval(cell["tour_mm"], face)
    opposite = {"front": "rear", "rear": "front", "left": "right", "right": "left"}[face]
    cuts = []
    for other in neighbors:
        if other is cell:
            continue
        a, b, other_edge = _interval(other["tour_mm"], opposite)
        if abs(edge - other_edge) < 2 and min(hi, b) > max(lo, a):
            cuts.append((max(lo, a), min(hi, b)))
    breaks = sorted({lo, hi, *(v for cut in cuts for v in cut)})
    return [
        (a, b)
        for a, b in zip(breaks, breaks[1:], strict=False)
        if b > a and not any(c <= (a + b) / 2 <= d for c, d in cuts)
    ]


def face_box(g: dict, face: str, lo: float, hi: float, bottom: float, top: float, thickness: float) -> dict:
    """A box centred on the source wall axis; finishes do not change room sizes."""
    edge = _interval(g, face)[2]
    if face in {"front", "rear"}:
        return {
            "x_mm": lo,
            "y_mm": edge - thickness / 2,
            "z_mm": bottom,
            "w_mm": hi - lo,
            "d_mm": thickness,
            "h_mm": top - bottom,
        }
    return {
        "x_mm": edge - thickness / 2,
        "y_mm": lo,
        "z_mm": bottom,
        "w_mm": thickness,
        "d_mm": hi - lo,
        "h_mm": top - bottom,
    }


def _aabb(box: dict) -> dict:
    return {
        "minX": box["x_mm"],
        "maxX": box["x_mm"] + box["w_mm"],
        "minY": box["y_mm"],
        "maxY": box["y_mm"] + box["d_mm"],
    }


def _z_overlap(a: dict, b: dict) -> bool:
    return a["z_mm"] < b["z_mm"] + b["h_mm"] - 1 and a["z_mm"] + a["h_mm"] > b["z_mm"] + 1


def decoration_issues(box: dict, floor: dict, openings: list[dict], *, opaque: bool = True) -> list[str]:
    """Do not install a decorative element inside an existing reserved band.

    Door/window projection is deliberately conservative: a screen in front of a
    recessed opening is a conflict even if their physical AABBs do not touch.
    Transparent perimeter rails still require a separate effective-daylight check.
    """
    issues = set()
    a = _aabb(box)
    if a["minX"] < 0 or a["maxX"] > floor["tour_width_mm"] or a["minY"] < 0 or a["maxY"] > floor["tour_depth_mm"]:
        issues.add("outside-comparison-frame")
    for cell in floor["cells"]:
        if cell.get("tour_active") is False:
            continue
        for zone in cell["tour_features"].get("reserved_mm", []):
            if zone["kind"] != "stairs" and overlaps(a, zone["aabb"]):
                issues.add(zone["kind"])
    for opening in openings:
        if opening["floor"] != floor["id"] or opening["kind"] == "window" and not opaque:
            continue
        b = opening["box_mm"]
        if not _z_overlap(box, b):
            continue
        face = opening["face"]
        if opening["kind"] in {"door", "open"}:
            # Balcony edge protection several metres from its access door is
            # not a door obstruction. Screen the actual approach depth, not
            # an infinite corridor projected out through the falling edge.
            separation = abs(box["y_mm"] - b["y_mm"]) if face in {"front", "rear"} else abs(box["x_mm"] - b["x_mm"])
            if separation > 900 + max(box["d_mm"], box["w_mm"] if face in {"left", "right"} else 0):
                continue
        if face == "front" and box["y_mm"] <= b["y_mm"] and a["minX"] < b["x_mm"] + b["w_mm"] and a["maxX"] > b["x_mm"]:
            issues.add(opening["kind"] + "-projection")
        elif (
            face == "rear"
            and box["y_mm"] + box["d_mm"] >= b["y_mm"]
            and a["minX"] < b["x_mm"] + b["w_mm"]
            and a["maxX"] > b["x_mm"]
        ):
            issues.add(opening["kind"] + "-projection")
        elif face in {"left", "right"} and overlaps(a, _aabb(b)):
            issues.add(opening["kind"] + "-projection")
    return sorted(issues)


def _floor_openings(floor: dict, indoor: list[dict], standards: dict) -> list[dict]:
    result = []
    for cell in indoor:
        g, f = cell["tour_mm"], cell["tour_features"]
        for face in FACES:
            boundary = boundary_segments(cell, indoor, face)
            if not boundary:
                continue
            origin, end, _ = _interval(g, face)
            length = end - origin
            holes = []
            for kind, entries in (("door", f["doors"]), ("open", f["open_connections"])):
                for index, entry in enumerate(entries):
                    if entry["face"] != face:
                        continue
                    centre = origin + entry["ratio"] * length
                    width = entry["width_mm"]
                    if kind == "door" and (centre - width / 2 < origin or centre + width / 2 > end):
                        # Match the interior renderer's tolerance/acceptance.
                        continue
                    if not any(a < centre + width / 2 and b > centre - width / 2 for a, b in boundary):
                        continue  # internal door, not facade
                    holes.append(
                        {
                            "id": f"{cell['id']}:{face}:{kind}-{index}",
                            "kind": kind,
                            "lo": centre - width / 2,
                            "hi": centre + width / 2,
                            "bottom": 0,
                            "top": floor["height_mm"] if kind == "open" else standards["door_height_mm"],
                            "source": copy.deepcopy(entry),
                        }
                    )
            if f.get("window_face") == face and 0 < cell["window_mm"] < length - 200:
                width, centre = cell["window_mm"], origin + length * f["window_ratio"]
                # Keep a superseded candidate visible in the DATA, not rendered
                # across a door, clipped smaller, or silently re-centred.
                conflicts = any(h["lo"] < centre + width / 2 and h["hi"] > centre - width / 2 for h in holes)
                sill = f.get("window_sill_mm") or standards["window_sill_height_mm"]
                holes.append(
                    {
                        "id": f"{cell['id']}:{face}:window",
                        "kind": "window",
                        "lo": centre - width / 2,
                        "hi": centre + width / 2,
                        "bottom": sill,
                        "top": sill + (f.get("window_height_mm") or standards["window_height_mm"]),
                        "source": {
                            "face": face,
                            "ratio": f["window_ratio"],
                            "width_mm": width,
                            "sill_mm": sill,
                            "height_mm": f.get("window_height_mm") or standards["window_height_mm"],
                        },
                        "issues": ["overlaps-source-door"] if conflicts else [],
                    }
                )
            for hole in holes:
                issues = hole.get("issues", [])[:]
                if hole["lo"] < origin - 1 or hole["hi"] > end + 1:
                    issues.append("candidate-outside-source-wall")
                if not any(a <= hole["lo"] + 1 and b >= hole["hi"] - 1 for a, b in boundary):
                    issues.append("candidate-not-fully-exterior")
                if hole["top"] > floor["height_mm"]:
                    issues.append("candidate-above-storey")
                result.append(
                    {
                        **hole,
                        "floor": floor["id"],
                        "room": cell["id"],
                        "face": face,
                        "box_mm": face_box(
                            g,
                            face,
                            hole["lo"],
                            hole["hi"],
                            floor["base_mm"] + hole["bottom"],
                            floor["base_mm"] + hole["top"],
                            16,
                        ),
                        "issues": issues,
                        "rendered": not issues,
                        "status": "pending-opening" if issues else "candidate-not-verified",
                    }
                )
    return result


def build_facade(buildings: list[dict], standards: dict, path: Path = FACADE_FILE) -> dict:
    concept = json.loads(path.read_text(encoding="utf-8"))
    if concept.get("schema") != "house-facade-concept-v1" or concept.get("geometry_source") != "tour_mm":
        raise ValueError("Facade concept must use house-facade-concept-v1 / tour_mm")
    dims = concept["assumptions_mm"]
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in dims.values()):
        raise ValueError("Facade visual dimensions must be finite and positive")
    if dims["slat_pitch"] <= dims["slat_width"] or dims["rail_height"] <= 2 * dims["rail_frame"]:
        raise ValueError("Invalid facade slat pitch or rail frame")
    alternatives = concept.get("slat_alternative_x_mm", [])
    if not isinstance(alternatives, list) or any(
        not isinstance(x, (int, float)) or not math.isfinite(x) for x in alternatives
    ):
        raise ValueError("Facade slat alternative positions must be finite numbers")
    result = {
        "schema": SCHEMA,
        "id": concept["id"],
        "status": STATUS,
        "geometry_source": "tour_mm",
        "source": repo_relative(path),
        "reference": copy.deepcopy(concept["reference"]),
        "palette": copy.deepcopy(concept["palette"]),
        "assumptions_mm": dict(dims),
        "assumption_note": concept["assumption_note"],
        "pending_checks": copy.deepcopy(concept["pending_checks"]),
        "sources": copy.deepcopy(concept["sources"]),
        "buildings": [],
    }
    for building in buildings:
        record = {
            "id": building["id"],
            **copy.deepcopy(concept["buildings"][building["id"]]),
            "elevation_file": f"{building['id']}_facade-front.svg",
            "components": [],
            "openings": [],
            "floors": [],
            "pending": [],
        }

        def add(
            floor: dict,
            role: str,
            material: str,
            box: dict,
            source_room: str = "",
            *,
            face: str = "",
            decorative: bool = False,
            opaque: bool = True,
            module: str = "",
            record: dict = record,
        ) -> None:
            if box["w_mm"] <= 0 or box["d_mm"] <= 0 or box["h_mm"] <= 0:
                return
            issues = decoration_issues(box, floor, record["openings"], opaque=opaque) if decorative else []
            component = {
                "id": f"{record['id']}:{floor['id']}:facade:{len(record['components']) + 1}",
                "floor": floor["id"],
                "role": role,
                "material": material,
                "source_room": source_room,
                "face": face,
                "module": module,
                "box_mm": {k: round(v, 3) for k, v in box.items()},
                "rendered": not issues,
                "issues": issues,
                "status": "pending-conflict" if issues else "proposal-not-installed",
                "compliance": "unknown",
            }
            record["components"].append(component)

        for floor in building["floors"]:
            active = [c for c in floor["cells"] if c.get("tour_active") is not False]
            indoor = [c for c in active if not c["is_outdoor"]]
            openings = _floor_openings(floor, indoor, standards)
            record["openings"].extend(openings)
            record["floors"].append(
                {
                    "id": floor["id"],
                    "base_mm": floor["base_mm"],
                    "height_mm": floor["height_mm"],
                    "is_roof": floor["is_roof"],
                    "width_mm": floor["tour_width_mm"],
                    "depth_mm": floor["tour_depth_mm"],
                    "front_balconies": [
                        {"room": c["id"], "geometry": copy.deepcopy(c["tour_mm"])}
                        for c in active
                        if c["is_outdoor"] and c["tour_mm"]["y_mm"] == 0
                    ],
                }
            )
            for cell in indoor:
                g, base, top = cell["tour_mm"], floor["base_mm"], floor["base_mm"] + floor["height_mm"]
                for face in FACES:
                    holes = [h for h in openings if h["room"] == cell["id"] and h["face"] == face and h["rendered"]]
                    for lo, hi in boundary_segments(cell, indoor, face):
                        breaks = sorted(
                            {lo, hi, *(v for h in holes for v in (max(lo, h["lo"]), min(hi, h["hi"])) if lo <= v <= hi)}
                        )
                        for a, b in zip(breaks, breaks[1:], strict=False):
                            gaps = [h for h in holes if h["lo"] <= (a + b) / 2 <= h["hi"]]
                            bottom, ceiling = (
                                (min(h["bottom"] for h in gaps), max(h["top"] for h in gaps))
                                if gaps
                                else (floor["height_mm"], floor["height_mm"])
                            )
                            add(
                                floor,
                                "wall",
                                "dark" if floor["index"] == 0 and face == "front" else "wall",
                                face_box(g, face, a, b, base, base + bottom, dims["wall_thickness"]),
                                cell["id"],
                                face=face,
                            )
                            add(
                                floor,
                                "wall",
                                "dark" if floor["index"] == 0 and face == "front" else "wall",
                                face_box(g, face, a, b, base + ceiling, top, dims["wall_thickness"]),
                                cell["id"],
                                face=face,
                            )
                    for hole in holes:
                        if hole["kind"] == "open":
                            continue
                        lo, hi, bot, ht = hole["lo"], hole["hi"], base + hole["bottom"], base + hole["top"]
                        frame = 40
                        for a, b, z0, z1 in (
                            (lo, lo + frame, bot, ht),
                            (hi - frame, hi, bot, ht),
                            (lo, hi, ht - frame, ht),
                        ):
                            add(
                                floor,
                                "opening-frame",
                                "dark",
                                face_box(g, face, a, b, z0, z1, 110),
                                cell["id"],
                                face=face,
                                module=hole["id"],
                            )
                        if hole["kind"] == "window":
                            add(
                                floor,
                                "opening-frame",
                                "dark",
                                face_box(g, face, lo, hi, bot, bot + frame, 110),
                                cell["id"],
                                face=face,
                                module=hole["id"],
                            )
                            add(
                                floor,
                                "window-glass",
                                "glass",
                                face_box(g, face, lo + frame, hi - frame, bot + frame, ht - frame, 16),
                                cell["id"],
                                face=face,
                                module=hole["id"],
                            )
                        else:
                            # An open doorway, not a guessed leaf/swing/shutter.
                            record["pending"].append(
                                {
                                    "id": hole["id"] + ":leaf",
                                    "status": "unknown",
                                    "note": "門扇、淨寬、門檻、防水及開啟方式未選；外觀只示意原門洞，不增設鐵捲門。",
                                }
                            )
                if floor["is_roof"]:
                    add(
                        floor,
                        "roof-cap",
                        "light",
                        {
                            "x_mm": g["x_mm"],
                            "y_mm": g["y_mm"],
                            "z_mm": top,
                            "w_mm": g["w_mm"],
                            "d_mm": g["h_mm"],
                            "h_mm": 120,
                        },
                        cell["id"],
                    )
            # Fascias follow the EXISTING slab perimeter; no invented columns
            # or ground-level gates. Slab tops remain the original room meshes.
            if floor["index"] > 0:
                w, d, base = floor["tour_width_mm"], floor["tour_depth_mm"], floor["base_mm"]
                for face, y in (("front", 0), ("rear", d - 80)):
                    add(
                        floor,
                        "slab-fascia",
                        "dark",
                        {
                            "x_mm": 0,
                            "y_mm": y,
                            "z_mm": base - dims["fascia_height"],
                            "w_mm": w,
                            "d_mm": 80,
                            "h_mm": dims["fascia_height"],
                        },
                        face=face,
                    )
                    add(
                        floor,
                        "light-band",
                        "light",
                        {
                            "x_mm": 180,
                            "y_mm": -2 if face == "front" else d,
                            "z_mm": base - 155,
                            "w_mm": w - 360,
                            "d_mm": 2,
                            "h_mm": 100,
                        },
                        face=face,
                    )
                for cell in active:
                    if not cell["is_outdoor"]:
                        continue
                    g = cell["tour_mm"]
                    for face in FACES:
                        for lo, hi in boundary_segments(cell, active, face):
                            # Rail centres 40mm inside the conceptual slab.
                            rg = dict(g)
                            if face == "front":
                                rg["y_mm"] += 40
                            elif face == "rear":
                                rg["h_mm"] -= 40
                            elif face == "left":
                                rg["x_mm"] += 40
                            else:
                                rg["w_mm"] -= 40
                            lo, hi = lo + 40, hi - 40
                            rf, rh, base = dims["rail_frame"], dims["rail_height"], floor["base_mm"]
                            # Validate whole rail first. A blocked guardrail is
                            # retained as pending (safety needs redesign), not
                            # a partially installed/open-edge approval.
                            envelope = face_box(rg, face, lo, hi, base, base + rh, rf)
                            issues = decoration_issues(envelope, floor, record["openings"], opaque=False)
                            module = f"{cell['id']}:{face}:guardrail"
                            if issues:
                                record["pending"].append(
                                    {
                                        "id": module,
                                        "status": "pending-conflict",
                                        "issues": issues,
                                        "box_mm": envelope,
                                        "note": "防墜欄與原預留帶衝突；尚未畫成完成欄杆，需維修／防墜整合設計。",
                                    }
                                )
                                continue
                            for z0, z1 in ((base + 80, base + 80 + rf), (base + rh - rf, base + rh)):
                                add(
                                    floor,
                                    "rail-frame",
                                    "dark",
                                    face_box(rg, face, lo, hi, z0, z1, rf),
                                    cell["id"],
                                    face=face,
                                    module=module,
                                )
                            panels = max(1, math.ceil((hi - lo) / 1200))
                            for n in range(panels + 1):
                                x = lo + (hi - lo) * n / panels
                                a, b = max(lo, x - rf / 2), min(hi, x + rf / 2)
                                add(
                                    floor,
                                    "rail-post",
                                    "dark",
                                    face_box(rg, face, a, b, base, base + rh, rf),
                                    cell["id"],
                                    face=face,
                                    module=module,
                                )
                                if n < panels:
                                    add(
                                        floor,
                                        "rail-glass",
                                        "glass",
                                        face_box(
                                            rg,
                                            face,
                                            x + rf / 2,
                                            lo + (hi - lo) * (n + 1) / panels - rf / 2,
                                            base + 80 + rf,
                                            base + rh - rf,
                                            dims["glass_visual_thickness"],
                                        ),
                                        cell["id"],
                                        face=face,
                                        module=module,
                                    )
                front = next((c for c in active if c["is_outdoor"] and c["tour_mm"]["y_mm"] == 0), None)
                if front and not floor["is_roof"]:
                    for x in (0, w - dims["frame_width"]):
                        add(
                            floor,
                            "finish-return",
                            "dark",
                            {
                                "x_mm": x,
                                "y_mm": 0,
                                "z_mm": base + rh,
                                "w_mm": dims["frame_width"],
                                "d_mm": 80,
                                "h_mm": floor["height_mm"] - rh - 200,
                            },
                            front["id"],
                            face="front",
                            decorative=True,
                        )
                    # Prefer a small left module. Never move a window/HVAC unit
                    # to manufacture room for gold bars: conflicting proposal
                    # stays in the pending register and is not rendered.
                    box = {
                        "x_mm": 190,
                        "y_mm": 100,
                        "z_mm": base + rh + 80,
                        "w_mm": dims["slat_module_width"],
                        "d_mm": dims["slat_depth"],
                        "h_mm": floor["height_mm"] - rh - 280,
                    }
                    module = f"{building['id']}:{floor['id']}:gold-slat-option"
                    issues = decoration_issues(box, floor, record["openings"])
                    if issues:
                        record["pending"].append(
                            {
                                "id": module,
                                "status": "pending-conflict",
                                "issues": issues,
                                "box_mm": box,
                                "note": "局部直條會遮候選開口或佔用維修／通行帶；不搬家具／設備、不改窗，先留待調整。",
                            }
                        )
                        alternative = next(
                            (
                                {**box, "x_mm": x}
                                for x in concept.get("slat_alternative_x_mm", [])
                                if not decoration_issues({**box, "x_mm": x}, floor, record["openings"])
                            ),
                            None,
                        )
                        if alternative:
                            for n in range(int(dims["slat_module_width"] // dims["slat_pitch"])):
                                add(
                                    floor,
                                    "gold-slat",
                                    "metal",
                                    {
                                        **alternative,
                                        "x_mm": alternative["x_mm"] + n * dims["slat_pitch"],
                                        "w_mm": dims["slat_width"],
                                    },
                                    front["id"],
                                    face="front",
                                    module=module + ":free-alternative",
                                )
                    else:
                        for n in range(int(dims["slat_module_width"] // dims["slat_pitch"])):
                            add(
                                floor,
                                "gold-slat",
                                "metal",
                                {**box, "x_mm": box["x_mm"] + n * dims["slat_pitch"], "w_mm": dims["slat_width"]},
                                front["id"],
                                face="front",
                                module=module,
                            )
                    # A narrow side return can carry the same material family
                    # without covering the front windows. It is independent of
                    # the full front-module option, and uses the same checks.
                    side = {
                        "x_mm": w - 80,
                        "y_mm": 190,
                        "z_mm": base + rh + 80,
                        "w_mm": dims["slat_depth"],
                        "d_mm": dims["slat_module_width"],
                        "h_mm": floor["height_mm"] - rh - 280,
                    }
                    if not decoration_issues(side, floor, record["openings"]):
                        for n in range(int(dims["slat_module_width"] // dims["slat_pitch"])):
                            add(
                                floor,
                                "gold-slat",
                                "metal",
                                {**side, "y_mm": side["y_mm"] + n * dims["slat_pitch"], "d_mm": dims["slat_width"]},
                                front["id"],
                                face="right",
                                module=module + ":side-return",
                            )
            for opening in openings:
                if opening["issues"]:
                    record["pending"].append(
                        {
                            "id": opening["id"],
                            "status": "pending-opening",
                            "issues": opening["issues"],
                            "note": "原候選開口重疊門洞、越出牆端或部分位於內牆；保留原值，不假裝已裝、不偷偷縮窄或搬窗。",
                        }
                    )
        record["pending"].append(
            {
                "id": building["id"] + ":equipment-screen",
                "status": "unknown",
                "note": "前後設備遮蔽未選機型／合法逃生與採光條件；保留冷氣原位置及維修帶，不畫封閉遮屏。",
            }
        )
        record["checks"] = {
            "scope": "concept-geometry-only",
            "compliance": "unknown",
            "source_geometry_mutated": False,
            "rendered_components": sum(c["rendered"] for c in record["components"]),
            "pending_components": sum(not c["rendered"] for c in record["components"]),
            "pending_records": len(record["pending"]),
        }
        result["buildings"].append(record)
    return result


def render_elevation(facade: dict, building: dict) -> str:
    """Front projection of exactly the components used by the 3D facade layer."""
    width = max(f["width_mm"] for f in building["floors"])
    top = max(f["base_mm"] + f["height_mm"] for f in building["floors"]) + 120
    root = Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "viewBox": f"-1300 -950 {width + 2800} {top + 2100}",
            "role": "img",
            "aria-labelledby": "facade-title facade-desc",
            "data-schema": SCHEMA,
            "data-building": building["id"],
            "data-facade-id": facade["id"],
            "data-geometry-source": "tour_mm",
        },
    )
    SubElement(root, "title", id="facade-title").text = building["id"] + " 棟 · 照片風格正立面提案（與3D共用）"
    SubElement(
        root, "desc", id="facade-desc"
    ).text = "非核准立面或結構圖。候選門窗沿共用平面；衝突元件不展示，詳見待確認清單。1F不新增車庫／柱子；屋頂不新增整片棚架。"
    SubElement(
        root, "style"
    ).text = "text{font-family:system-ui,sans-serif;fill:#314451;font-size:180px} .level{stroke:#a8b3b6;stroke-width:12;stroke-dasharray:60 45}"
    SubElement(root, "rect", x="-1300", y="-950", width=str(width + 2800), height=str(top + 2100), fill="#f7f8f6")
    # Paint rear/deeper geometry first; same plan-space depth as exterior 3D.
    for component in sorted(building["components"], key=lambda c: -c["box_mm"]["y_mm"]):
        if not component["rendered"]:
            continue
        b = component["box_mm"]
        el = SubElement(
            root,
            "rect",
            {
                "x": str(b["x_mm"]),
                "y": str(top - b["z_mm"] - b["h_mm"]),
                "width": str(b["w_mm"]),
                "height": str(b["h_mm"]),
                "fill": facade["palette"][component["material"]]["color"],
                "fill-opacity": "0.38" if component["material"] == "glass" else "1",
                "data-component-id": component["id"],
                "data-role": component["role"],
                "data-source-room": component["source_room"],
                **{"data-" + k.replace("_", "-"): str(v) for k, v in b.items()},
            },
        )
        SubElement(el, "title").text = component["role"] + " · 表現用暫估，法規／施工未核"
    # Dashed annotations are unresolved SOURCE candidates, not installed
    # components or a smaller replacement window invented by the exporter.
    for opening in building["openings"]:
        if opening["rendered"] or opening["face"] != "front":
            continue
        b = opening["box_mm"]
        marker = SubElement(
            root,
            "rect",
            {
                "x": str(b["x_mm"]),
                "y": str(top - b["z_mm"] - b["h_mm"]),
                "width": str(b["w_mm"]),
                "height": str(b["h_mm"]),
                "fill": "none",
                "stroke": "#bf751e",
                "stroke-width": "22",
                "stroke-dasharray": "70 45",
                "data-pending-opening-id": opening["id"],
                "data-status": "pending-not-installed",
            },
        )
        SubElement(marker, "title").text = "原候選開口待調整，未展示為已裝：" + "、".join(opening["issues"])
    for floor in building["floors"]:
        y = top - floor["base_mm"]
        SubElement(root, "line", {"x1": "-250", "y1": str(y), "x2": str(width + 300), "y2": str(y), "class": "level"})
        SubElement(root, "text", x="-1200", y=str(y - 70)).text = (
            "RF" if floor["is_roof"] else floor["id"].replace("floor-", "") + "F"
        ) + f" +{floor['base_mm'] / 1000:g}m"
    SubElement(root, "text", x="0", y="-510", **{"font-size": "270", "font-weight": "700"}).text = (
        building["id"] + " 棟 · 照片風格外觀 v1"
    )
    SubElement(root, "text", x="0", y="-160").text = "既有提案門窗／陽台，未增車庫、門廊柱或屋頂棚架"
    SubElement(root, "text", x="0", y=str(top + 370)).text = f"{width / 1000:g}m 比較框；層高／欄杆／材質均未核定"
    SubElement(
        root, "text", x="0", y=str(top + 700)
    ).text = f"{len(building['pending'])} 項待確認／衝突未展示；採光與停車不視為通過"
    SubElement(root, "text", x="0", y=str(top + 1000)).text = "橘色虛框＝原候選開口待調整，非已裝門窗"
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="unicode") + "\n"

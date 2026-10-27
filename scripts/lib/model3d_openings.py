"""Opening identity and dimensional screens shared by plan and 3D proposals.

No automatic clipping/recentring and no inference of legal daylight, ventilation
or a buildable wall. Invalid requests stay traceable, but are not drawn as real
windows. The 100mm budgets below are discussion allowances, not code minima.
"""
from __future__ import annotations

import math


def is_shrine_room(cell: dict) -> bool:
    """A bedroom mentioning the shrine in its name is not a shrine itself."""
    return (cell.get("key") in {"shrine", "altar"}
            or cell.get("room_role") in {"shrine", "altar", "ritual"}
            or cell.get("review_spec", {}).get("role") == "shrine")


def set_window_request(cell: dict, face: str | None) -> None:
    """Replace the explicit intent; window_face remains drawing output only.

    Call when rebuilding a proposal or changing/cancelling its requested face.
    Width remains authoritative on cell.window_mm. Never recover intent from a
    previous window_review, which may describe a now-cancelled window.
    """
    if face not in {None, "front", "rear", "left", "right"}:
        raise ValueError("Unsupported requested window face")
    cell["window_request"] = {"face": face}
    cell["tour_features"]["window_face"] = None
    cell["tour_features"].pop("window_review", None)


def review_window(cell: dict, floor: dict, exterior_spans: dict[str, list[tuple]]) -> dict:
    f, g = cell["tour_features"], cell["tour_mm"]
    # Legacy/fresh callers provide the initial candidate face in window_face.
    # Capture it once, before validation clears the effective drawing output.
    # A saved legacy review is not an authoritative request and is not read.
    if "window_request" not in cell:
        set_window_request(cell, f.get("window_face"))
    face, width = cell["window_request"]["face"], cell["window_mm"]
    issues = []
    if cell["is_outdoor"]:
        state = "not-applicable-outdoor"
    elif not width:
        state = "not-requested"
    elif is_shrine_room(cell) and face == "rear":
        state = "protected-solid-backing"
        issues.append("altar-rear-backing-must-stay-solid")
    elif not face:
        state = "no-exterior-face"
        issues.append("no-confirmed-candidate-exterior-face")
    else:
        length = g["w_mm"] if face in {"front", "rear"} else g["h_mm"]
        origin = g["x_mm"] if face in {"front", "rear"} else g["y_mm"]
        ratio = f["window_ratio"]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in (width, ratio)) or width <= 0:
            issues.append("invalid-window-dimensions")
        else:
            lo, hi = length * ratio - width / 2, length * ratio + width / 2
            if width >= length - 200 or lo < 100 or hi > length - 100:
                issues.append("insufficient-assumed-jamb-budget")
            for opening in f["doors"] + f["open_connections"]:
                if opening["face"] != face:
                    continue
                centre, half = opening["ratio"] * length, opening["width_mm"] / 2
                if lo < centre + half + 100 - 1 and hi > centre - half - 100 + 1:
                    issues.append("overlaps-opening-or-assumed-buffer")
                    break
            merged = []
            for a, b in sorted(exterior_spans.get(face, [])):
                if merged and a <= merged[-1][1] + 1:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], b))
                else:
                    merged.append((a, b))
            if not any(a <= origin + lo + 1 and b >= origin + hi - 1 for a, b in merged):
                issues.append("not-fully-on-candidate-exterior")
            if f["window_sill_mm"] + f["window_height_mm"] > floor["height_mm"]:
                issues.append("window-above-storey")
        state = "invalid-candidate" if issues else "candidate-geometry-only"
    renderable = state == "candidate-geometry-only"
    explanations = {
        "candidate-geometry-only": "候選窗已避門洞並留模型窗邊；有效採光、通風、柱梁、窗框與防雨未核。",
        "not-requested": "本段不另畫獨立窗；不把門洞或玻璃門當作已核採光／通風。",
        "not-applicable-outdoor": "戶外區不計室內窗。",
        "protected-solid-backing": "神桌背牆保持實牆，不開後窗；宗教接受及梁管線未核。",
        "no-exterior-face": "尚無可畫的前後外窗，不假設側界可以開窗；採光／通風未解。",
        "invalid-candidate": "原候選窗與牆長、門洞或窗邊預算衝突，暫不畫成實窗；需重排，不計為已滿足採光／通風。",
    }
    result = {"status": state, "requested_face": face, "requested_width_mm": width,
              "renderable": renderable, "issues": issues, "assumed_jamb_budget_mm": 100,
              "assumed_opening_buffer_mm": 100, "professional_acceptance": "unknown",
              "note": explanations[state] + cell.get("review_spec", {}).get("window_note", "")}
    f["window_face"] = face if renderable else None
    f["window_review"] = result
    return result

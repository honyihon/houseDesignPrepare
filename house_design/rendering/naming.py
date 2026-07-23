from __future__ import annotations

import re


def safe_slug(value: str) -> str:
    text = " ".join((value or "").split()).lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "unknown"


def stable_svg_filename(building_id: str, floor_id: str) -> str:
    return f"{safe_slug(building_id)}_{safe_slug(floor_id)}.svg"

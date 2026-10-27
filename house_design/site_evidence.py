"""Evidence-bound selected-parcel area, never a buildability approval."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

PING_TO_SQM = 400 / 121
AREA_TOLERANCE_SQM = 0.01  # Rounding allowance, not cadastral/survey accuracy.
_PLACEHOLDERS = {
    "", "unknown", "pending", "unverified", "assumed", "estimated", "__fill__", "tbd",
    "none", "null", "n/a", "待填", "待確認", "未知", "ai", "chatgpt", "codex", "claude",
}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _text(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() not in _PLACEHOLDERS


def assess_parcel_area(parcel: dict[str, Any]) -> dict[str, Any]:
    """Keep legacy scalars readable; only a matching checked fact can pass.

    ``parcel_area_evidence`` is additive to v2/v3 parcel records. References
    may identify private documents; this module never opens them or certifies
    authenticity. A contradictory m²/ping pair is a data failure, not a claim
    that the land itself is unsuitable.
    """
    sqm, ping = parcel.get("parcel_area_sqm"), parcel.get("parcel_area_ping")
    issues: list[dict[str, str]] = []

    def missing(code: str, message: str) -> None:
        issues.append({"code": code, "message": message})

    if not _number(sqm):
        missing("MISSING_AREA_SQM", "缺有效的地籍平方公尺面積；坪數或 32 地坪目標不能代替。")
    if ping is not None and not _number(ping):
        missing("INVALID_AREA_PING", "已填坪數須為有限正數，不接受布林值、字串或無限值。")
    conflict = bool(_number(sqm) and _number(ping) and abs(sqm - ping * PING_TO_SQM) > AREA_TOLERANCE_SQM)
    if conflict:
        missing("AREA_UNIT_MISMATCH", "平方公尺與坪數換算不一致；須查對同一筆地籍資料，不能擇一當成已查核。")

    fact = parcel.get("parcel_area_evidence")
    if not isinstance(fact, dict):
        fact = {}
    if fact.get("status") != "verified":
        missing("AREA_NOT_VERIFIED", "缺 status=verified 的 parcel_area_evidence；舊數值保留但不視為已查核。")
    if not _text(parcel.get("id")) or fact.get("parcel_id") != parcel.get("id"):
        missing("AREA_PARCEL_MISMATCH", "面積證據未綁定同一筆 parcel id。")
    land = parcel.get("land_number")
    if isinstance(land, dict):
        land = land.get("value") if land.get("status") == "verified" else None
    if not _text(land) or fact.get("land_number") != land:
        missing("AREA_LAND_NUMBER_MISMATCH", "缺同一地號的面積證據；地號須含可唯一識別的行政區／段／小段及號碼。")
    if (
        not _number(fact.get("value")) or not _number(sqm)
        or abs(fact["value"] - sqm) > AREA_TOLERANCE_SQM
        or not isinstance(fact.get("unit"), str) or fact["unit"] not in {"m2", "m²"}
    ):
        missing("AREA_VALUE_MISMATCH", "面積證據的 value／unit 必須對應本筆 parcel_area_sqm（m2 或 m²）。")
    source = fact.get("source")
    if not isinstance(source, dict) or not all(_text(source.get(k)) for k in ("reference", "reviewer", "checked_at")):
        missing("AREA_SOURCE_MISSING", "缺可追溯文件 reference、具名查核人 reviewer 或查核日期 checked_at。")
        source = source if isinstance(source, dict) else {}
    else:
        try:
            if date.fromisoformat(source["checked_at"]).isoformat() != source["checked_at"]:
                raise ValueError("non-canonical date")
        except ValueError:
            missing("AREA_SOURCE_DATE_INVALID", "checked_at 須為有效的 YYYY-MM-DD 查核日期。")
    return {
        "status": "fail" if conflict else "unknown" if issues else "pass",
        "parcel_id": parcel.get("id"),
        "area_sqm": sqm,
        "area_ping": ping,
        "derived_area_ping": sqm / PING_TO_SQM if _number(sqm) else None,
        "issues": issues,
        "source": {key: source.get(key) for key in ("reference", "reviewer", "checked_at")},
        "policy": "只確認面積紀錄、換算與來源綁定完整，不證明來源真偽、可建量體或專業批准。",
    }

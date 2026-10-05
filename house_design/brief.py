"""Consolidated design brief for the first architect and interior-designer meetings.

The brief collects what is otherwise spread across the requirement register, the
physical-item inventory, the private household profile and the design-request
prose. It never decides anything: candidate requirements stay candidates, and the
private household profile only contributes coarse, non-identifying counts.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from pathlib import Path
from typing import Any

from house_design.contracts import (
    ROOT,
    ContractError,
    read_json,
    relative_to_root,
    sha256_file,
    stable_hash,
    utc_now,
    write_json,
)
from house_design.intake import (
    PROJECT_PATH,
    RELATIONSHIP_TYPES,
    REQUIREMENTS_PATH,
    describe_relationship,
    relationship_hash,
    relationship_status,
    relationship_target_label,
    validate_project,
    validate_requirements,
)
from house_design.physical_items import PHYSICAL_ITEMS_PATH, load_physical_items
from house_design.predesign import PREDESIGN_OUTPUT_ROOT

BRIEF_SCHEMA = "house-design-brief-v1"
HOUSEHOLD_PROFILE_SCHEMA = "house-household-profile-v1"
HOUSEHOLD_PROFILE_PATH = ROOT / "inputs/private/household-profile.json"
HOUSEHOLD_TEMPLATE = "inputs/household-profile.template.json"
DESIGN_REQUEST_PATH = ROOT / "inputs/design_request.md"
STANDARDS_PATH = ROOT / "scripts/config/residential_defaults_tw.json"
SQM_PER_PING = 3.305785

SITE_WARNING = "土地尚未選定：本任務書只整理需求與待決事項，不是可建量體、法規檢討或設計結論。"
SELECTED_SITE_WARNING = "基地資料仍須以正式文件、法規預檢與專業簽證確認；本任務書不是合規結論。"
LEGACY_LAYOUT_NOTICE = (
    "面積、位置帶、樓層與部分說明沿用舊版 area brief（每層 32 坪假設）的初始配置，只是討論起點；"
    "土地選定並確認法定條件後，須由建築師重新推導。"
)
NO_CONFIRMED_NOTICE = "目前沒有任何需求經屋主確認；以下全部是待決定的想法，請以提問與建議回應，不要直接當成設計條件。"

STATUS_SECTIONS = (
    ("confirmed", "已確認", "屋主已在決策紀錄中確認，可作為設計條件；仍需圖面證據驗證。"),
    ("candidate", "待屋主決定", "舊版想法或建議，歡迎建築師與設計師提出替代方案，但不可當成硬需求。"),
    ("rejected", "已淘汰", "屋主已否決，保留理由供追溯，請勿再納入設計。"),
)
STATUS_LABELS = {key: label for key, label, _note in STATUS_SECTIONS}
PRIORITY_LABELS = {"must": "必須", "should": "應該", "could": "可以"}
BAND_LABELS = {"front": "前帶", "rear": "後帶", "core": "中段核心", "auto": "不限"}
LIGHT_LABELS = {"required": "必須採光", "preferred": "宜有採光", "none": "不需採光"}
DOOR_SWING_LABELS = {"sliding": "橫拉門"}
LOCAL_SPACE_LABELS = {"corridor": "走道"}
ROLE_STATUS_LABELS = {"owner_confirmed_predesign_policy": "屋主已確認的前期定位"}
VERIFICATION_LABELS = {
    "pending_owner_confirmation": "待屋主確認",
    "owner_confirmed": "屋主已確認，待圖面證據",
    "owner_rejected": "屋主已淘汰",
}
DIMENSION_SOURCE_LABELS = {"measured": "實測", "planning": "暫估（待實測）"}
STANDARD_KEY_LABELS = {
    "entry": "大門",
    "accessible": "無障礙",
    "interior": "室內",
    "exterior": "外牆",
    "bathroom": "浴廁",
    "service": "服務空間",
    "bed_double": "雙人床",
    "sofa_3": "三人沙發",
    "dining_table_6": "六人餐桌",
    "kitchen_counter_depth": "流理台深度",
    "driver_side": "駕駛側",
    "passenger_side": "副駕側",
    "between_bays": "車位之間",
    "front": "車頭",
    "rear": "車尾",
    "length": "長",
    "width": "寬",
    "depth": "深",
    "height": "高",
    "clear": "操作淨空",
    "mount": "安裝位置",
    "front_wall": "車頭端牆面",
}

QUESTION_HEADING = re.compile(r"^#{1,6}\s+.*直接問這\s*\d+\s*題")
QUESTION_ITEM = re.compile(r"^\s*(\d{1,2})\.\s+(.+?)\s*$")
BUILDING_MARKER = re.compile(r"^'''\s*([ABC])\s*棟")
HEADING_BUILDING = re.compile(r"([ABC])\s*棟")
QUESTION_POINTER = re.compile(r"(?<![A-Za-z0-9])([ABC])-Q(\d{1,2})(?!\d)")
RATIONALE_QUESTION = re.compile(r"(?<![A-Za-z0-9-])Q(\d{1,2})(?!\d)")

HOUSEHOLD_BUILDINGS = ("A", "B", "C")
AGE_RANGE = re.compile(r"(\d{1,3})\s*歲?\s*[-–~～_]\s*(\d{1,3})\s*歲?")
AGE_AT_LEAST = re.compile(r"(\d{1,3})\s*歲?\s*(?:\+|以上|_?plus)")
AGE_AT_MOST = re.compile(r"(\d{1,3})\s*歲?\s*以下")
AGE_UNDER = re.compile(r"(?:under|below)[_\s-]?(\d{1,3})")
AGE_OVER = re.compile(r"(?:over|above)[_\s-]?(\d{1,3})")
AGE_WORD = re.compile(r"([a-z]+)(?:[_\s-]?\d{1,3})?")
AGE_WORD_LABELS = {
    "infant": "幼兒",
    "child": "兒童",
    "kid": "兒童",
    "teen": "青少年",
    "youth": "青少年",
    "adult": "成人",
    "senior": "長者",
    "elder": "長者",
    "elderly": "長者",
}
AGE_KEYWORDS = (
    (("嬰", "幼兒"), "幼兒"),
    (("兒童", "小孩"), "兒童"),
    (("青少年",), "青少年"),
    (("長輩", "長者", "高齡", "老年", "銀髮"), "長者"),
    (("成人", "成年"), "成人"),
)
AGE_UNBANDED = "未分級"
UNKNOWN_TOKENS = {"", "unknown", "未知", "不明", "待確認", "未填"}
MOBILITY_TOKENS = {
    "independent": "可獨立行走",
    "walking_aid": "需助行器具",
    "walker": "需助行器具",
    "cane": "需助行器具",
    "wheelchair": "使用輪椅",
}
MOBILITY_KEYWORDS = (
    (("輪椅",), "使用輪椅"),
    (("助行器", "拐杖", "助步"), "需助行器具"),
    (("獨立行走", "自行行走"), "可獨立行走"),
)
NEGATION_MARKERS = ("不", "無", "未", "沒", "非", "免")
MOBILITY_OTHER = "其他（細節僅保存在私有檔）"
VEHICLE_KEYWORDS = (
    (("機車", "motorcycle", "scooter"), "機車"),
    (("腳踏車", "自行車", "bicycle", "bike"), "腳踏車"),
    (("汽車", "休旅", "轎車", "電動車", "car", "suv"), "汽車"),
)
PET_KEYWORDS = ((("狗", "犬", "dog"), "狗"), (("貓", "cat"), "貓"))
HOUSEHOLD_WITHHELD = (
    "成員代號、稱謂與決策者",
    "照護與健康細節",
    "訪客與照護頻率文字",
    "神位位置偏好文字",
    "家庭變化、未來情境、設計方向與優先問題的自由文字",
    "填寫人、訪談紀錄路徑與同意紀錄",
)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _floor_label(floor_id: str) -> str:
    match = re.fullmatch(r"floor-(\d+|rf)", floor_id or "")
    if not match:
        return floor_id or "未指定"
    return "RF" if match.group(1) == "rf" else f"{match.group(1)}F"


def _floor_order(floor_id: str) -> tuple[int, str]:
    match = re.fullmatch(r"floor-(\d+)", floor_id or "")
    if match:
        return int(match.group(1)), floor_id
    return (99 if floor_id == "floor-rf" else 100), floor_id or ""


def _area_label(label: str, sqm: float) -> str:
    return f"{label} {sqm:g} m²（約 {sqm / SQM_PER_PING:.1f} 坪）"


def _local_space_label(local_id: str, applies_to: dict[str, Any], titles: dict[str, str]) -> str:
    building = str(applies_to.get("building_id") or "")
    floor = str(applies_to.get("floor_id") or "")
    same_floor = f"{building}.{floor}.{local_id}"
    if same_floor in titles:
        return relationship_target_label(same_floor, titles)
    same_building = sorted(key for key in titles if key.startswith(f"{building}.") and key.endswith(f".{local_id}"))
    if same_building:
        return relationship_target_label(same_building[0], titles)
    return LOCAL_SPACE_LABELS.get(local_id, local_id)


def constraint_labels(requirement: dict[str, Any], titles: dict[str, str]) -> list[str]:
    """Readable zh-TW labels for the single-room constraints of one requirement."""

    constraints = requirement.get("constraints") or {}
    applies_to = requirement.get("applies_to") or {}
    labels: list[str] = []
    if _number(constraints.get("target_sqm")):
        labels.append(_area_label("目標面積", constraints["target_sqm"]))
    if _number(constraints.get("min_sqm")):
        labels.append(_area_label("最小面積", constraints["min_sqm"]))
    if constraints.get("band"):
        labels.append(f"位置帶：{BAND_LABELS.get(str(constraints['band']), str(constraints['band']))}")
    if constraints.get("light"):
        labels.append(LIGHT_LABELS.get(str(constraints["light"]), f"採光：{constraints['light']}"))
    if constraints.get("private") is True:
        labels.append("私密空間")
    if _number(constraints.get("door_clear_mm")):
        labels.append(f"門淨寬 ≥ {constraints['door_clear_mm']:g} mm")
    if constraints.get("door_swing"):
        labels.append(f"門型：{DOOR_SWING_LABELS.get(str(constraints['door_swing']), str(constraints['door_swing']))}")
    if constraints.get("wheelchair_turn") is True:
        labels.append("需留 150 cm 輪椅迴轉圈")
    access_from = constraints.get("access_from")
    if isinstance(access_from, list) and access_from:
        names = "、".join(_local_space_label(str(value), applies_to, titles) for value in access_from)
        labels.append(f"由 {names} 進出")
    if constraints.get("penthouse") is True:
        labels.append("位於屋頂突出物（法定分類待建築師確認）")
    return labels


def extract_open_questions(text: str) -> dict[str, list[dict[str, Any]]]:
    """Pull the numbered "ask these next time" lists out of the design-request prose."""

    questions: dict[str, list[dict[str, Any]]] = {}
    building = "A"
    active: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        marker = BUILDING_MARKER.match(line)
        if marker:
            building = marker.group(1)
            active = None
            continue
        if line.startswith("#"):
            active = None
            if QUESTION_HEADING.match(line):
                named = HEADING_BUILDING.search(line)
                active = named.group(1) if named else building
                questions.setdefault(active, [])
            continue
        if active is None:
            continue
        if line.strip() == "---":
            active = None
            continue
        item = QUESTION_ITEM.match(line)
        if item:
            number = int(item.group(1))
            if any(existing["number"] == number for existing in questions[active]):
                continue
            questions[active].append(
                {
                    "id": f"{active}-Q{number}",
                    "number": number,
                    "text": item.group(2).replace("**", "").strip(),
                }
            )
    return questions


def _question_links(requirements: list[dict[str, Any]]) -> dict[str, set[str]]:
    links: dict[str, set[str]] = {}
    for requirement in requirements:
        requirement_id = str(requirement.get("id") or "")
        building = str((requirement.get("applies_to") or {}).get("building_id") or "")
        for relationship in requirement.get("relationships") or []:
            pointer = str(((relationship or {}).get("source") or {}).get("pointer") or "")
            for match in QUESTION_POINTER.finditer(pointer):
                links.setdefault(f"{match.group(1)}-Q{int(match.group(2))}", set()).add(requirement_id)
        if building in HOUSEHOLD_BUILDINGS:
            for match in RATIONALE_QUESTION.finditer(str(requirement.get("rationale") or "")):
                links.setdefault(f"{building}-Q{int(match.group(1))}", set()).add(requirement_id)
    return links


def source_label(source: dict[str, Any] | None) -> str:
    """Design-request pointers are already readable question ids; other pointers need their file."""

    if not source:
        return ""
    pointer = str(source.get("pointer") or "")
    if source.get("type") == "design_request" and pointer:
        return pointer
    return " ".join(part for part in (str(source.get("path") or ""), pointer) if part)


def _relationship_entry(
    requirement: dict[str, Any], relationship: dict[str, Any], titles: dict[str, str]
) -> dict[str, Any]:
    status = relationship_status(requirement, relationship)
    relationship_type = str(relationship.get("type") or "")
    target = str(relationship.get("target") or "")
    source = relationship.get("source") if isinstance(relationship.get("source"), dict) else None
    pointer = str((source or {}).get("pointer") or "")
    question = QUESTION_POINTER.search(pointer)
    return {
        "requirement_id": requirement.get("id"),
        "requirement_title": requirement.get("title"),
        "building_id": (requirement.get("applies_to") or {}).get("building_id"),
        "type": relationship_type,
        "type_label": RELATIONSHIP_TYPES.get(relationship_type, relationship_type),
        "target": target,
        "target_label": relationship_target_label(target, titles),
        "description": describe_relationship(relationship, titles),
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "rationale": str(relationship.get("rationale") or ""),
        "source": (
            {"type": source.get("type"), "path": source.get("path"), "pointer": source.get("pointer")}
            if source
            else None
        ),
        "question_id": f"{question.group(1)}-Q{int(question.group(2))}" if question else None,
        "relationship_hash": relationship_hash(relationship),
    }


def _requirement_entry(requirement: dict[str, Any], titles: dict[str, str]) -> dict[str, Any]:
    applies_to = requirement.get("applies_to") or {}
    floor_id = str(applies_to.get("floor_id") or "")
    status = str(requirement.get("status") or "candidate")
    priority = str(requirement.get("priority") or "")
    decisions = [entry for entry in requirement.get("decision_log") or [] if isinstance(entry, dict)]
    latest = decisions[-1] if decisions else None
    verification = requirement.get("verification") if isinstance(requirement.get("verification"), dict) else {}
    verification_state = str(verification.get("state") or "")
    source = requirement.get("source") if isinstance(requirement.get("source"), dict) else {}
    return {
        "id": requirement.get("id"),
        "title": requirement.get("title"),
        "category": requirement.get("category"),
        "building_id": applies_to.get("building_id"),
        "floor_id": floor_id,
        "floor_label": _floor_label(floor_id),
        "floor_note": "屋主建議，可調整",
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "priority": priority,
        "priority_label": PRIORITY_LABELS.get(priority, priority),
        "rationale": str(requirement.get("rationale") or ""),
        "rationale_is_legacy": source.get("type") == "legacy_brief",
        "constraints": dict(requirement.get("constraints") or {}),
        "constraint_labels": constraint_labels(requirement, titles),
        "relationships": [
            _relationship_entry(requirement, relationship, titles)
            for relationship in requirement.get("relationships") or []
            if isinstance(relationship, dict)
        ],
        "verification_state": verification_state,
        "verification_label": VERIFICATION_LABELS.get(verification_state, verification_state or "未記錄"),
        # decided_by is deliberately left out: the brief is shared outside the family.
        "last_decision": (
            {"sequence": latest.get("sequence"), "decided_at": latest.get("decided_at"), "reason": latest.get("reason")}
            if latest
            else None
        ),
        "source": {"type": source.get("type"), "path": source.get("path"), "pointer": source.get("pointer")},
    }


def _classify(value: Any, keywords: tuple[tuple[tuple[str, ...], str], ...], fallback: str) -> str:
    text = str(value or "").strip().lower()
    for words, label in keywords:
        if any(word in text for word in words):
            return label
    return fallback


def _age_band_label(value: Any) -> str:
    """Only open or ranged bands and coarse life stages are published; an exact age stays private."""

    text = str(value or "").strip()
    token = text.lower()
    if not text:
        return "未填"
    if match := AGE_RANGE.fullmatch(token):
        return f"{int(match.group(1))}–{int(match.group(2))} 歲"
    if match := AGE_AT_LEAST.fullmatch(token):
        return f"{int(match.group(1))} 歲以上"
    if match := AGE_AT_MOST.fullmatch(token):
        return f"{int(match.group(1))} 歲以下"
    if match := AGE_UNDER.fullmatch(token):
        return f"未滿 {int(match.group(1))} 歲"
    if match := AGE_OVER.fullmatch(token):
        return f"超過 {int(match.group(1))} 歲"
    if (match := AGE_WORD.fullmatch(token)) and match.group(1) in AGE_WORD_LABELS:
        return AGE_WORD_LABELS[match.group(1)]
    matches = {label for words, label in AGE_KEYWORDS if any(word in text for word in words)}
    if len(matches) == 1 and not re.search(r"\d", text):
        return matches.pop()
    return AGE_UNBANDED


def _mobility_category(value: Any) -> str:
    text = str(value or "").strip()
    token = text.lower()
    if token in UNKNOWN_TOKENS:
        return "未知"
    if token in MOBILITY_TOKENS:
        return MOBILITY_TOKENS[token]
    matches = {label for words, label in MOBILITY_KEYWORDS if any(word in text for word in words)}
    # Free text such as "不需輪椅" must not be misread; anything ambiguous stays private.
    if len(matches) != 1 or any(marker in text for marker in NEGATION_MARKERS):
        return MOBILITY_OTHER
    return matches.pop()


def _count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else None


def household_summary(path: Path) -> dict[str, Any]:
    """Aggregate the private household profile without names, health details or free text."""

    if not path.is_file():
        return {
            "provided": False,
            "note": f"未提供私有家庭檔案；請複製 {HOUSEHOLD_TEMPLATE} 到 inputs/private/ 後填寫。",
        }
    payload = read_json(path)
    if payload.get("schema") != HOUSEHOLD_PROFILE_SCHEMA:
        return {
            "provided": True,
            "readable": False,
            "note": f"私有家庭檔案的 schema 不是 {HOUSEHOLD_PROFILE_SCHEMA}，未輸出摘要。",
        }
    household = payload.get("household") if isinstance(payload.get("household"), dict) else {}
    members = [item for item in household.get("members") or [] if isinstance(item, dict)]
    people = 0
    age_bands: Counter[str] = Counter()
    buildings: Counter[str] = Counter()
    mobility_now: Counter[str] = Counter()
    mobility_outlook: Counter[str] = Counter()
    for member in members:
        count = member.get("count")
        weight = count if isinstance(count, int) and not isinstance(count, bool) and count > 0 else 1
        people += weight
        age_bands[_age_band_label(member.get("age_band"))] += weight
        building = str(member.get("usual_building") or "").strip().upper()
        buildings[building if building in HOUSEHOLD_BUILDINGS else "未指定"] += weight
        mobility_now[_mobility_category(member.get("mobility_now"))] += weight
        mobility_outlook[_mobility_category(member.get("mobility_10_year_outlook"))] += weight

    vehicles = [
        {
            "category": _classify(item.get("type"), VEHICLE_KEYWORDS, "其他車輛"),
            "current_count": _count(item.get("current_count")),
            "future_count": _count(item.get("future_count")),
        }
        for item in household.get("vehicles") or []
        if isinstance(item, dict)
    ]
    pets = []
    for item in household.get("pets") or []:
        if not isinstance(item, dict):
            continue
        building = str(item.get("building_id") or "").strip().upper()
        pets.append(
            {
                "category": _classify(item.get("animal"), PET_KEYWORDS, "其他寵物"),
                "count": _count(item.get("count")),
                "building_id": building if building in HOUSEHOLD_BUILDINGS else None,
            }
        )
    guests = household.get("frequent_guests_or_caregivers")
    guests = guests if isinstance(guests, dict) else {}
    religion = household.get("religious_practice")
    religion = religion if isinstance(religion, dict) else {}

    def _bool(value: Any) -> bool | None:
        return value if isinstance(value, bool) else None

    def _people(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

    def _entries(value: Any) -> int:
        return len(value) if isinstance(value, list) else 0

    status = str(payload.get("status") or "")
    return {
        "provided": True,
        "readable": True,
        "profile_is_template": status.startswith("template"),
        "member_entries": len(members),
        "people_total": people,
        "age_bands": dict(sorted(age_bands.items())),
        "usual_building": {key: buildings.get(key, 0) for key in (*HOUSEHOLD_BUILDINGS, "未指定")},
        "mobility_now": dict(sorted(mobility_now.items())),
        "mobility_10_year_outlook": dict(sorted(mobility_outlook.items())),
        "vehicles": vehicles,
        "pets": pets,
        "overnight_guests": _bool(guests.get("overnight_guests")),
        "shared_meals_people": _people(household.get("shared_meals_people")),
        "festival_or_large_gathering_people": _people(household.get("festival_or_large_gathering_people")),
        "religious_practice": {
            "has_shrine_or_incense": _bool(religion.get("has_shrine_or_incense")),
            "smoke_and_fire_controls_required": _bool(religion.get("smoke_and_fire_controls_required")),
        },
        "entry_counts": {
            "planned_household_changes": _entries(household.get("planned_household_changes")),
            "future_change_scenarios": _entries(household.get("future_change_scenarios")),
            "design_directions": _entries(household.get("design_directions")),
            "daily_routines": _entries(household.get("daily_routines")),
            "priority_questions": _entries(payload.get("priority_questions")),
        },
        "withheld": list(HOUSEHOLD_WITHHELD),
        "note": (
            "只輸出人數、年齡級距、慣用棟別、行動力類別與車輛／寵物統計；"
            "自由文字若要讓建築師看到，請改寫成可公開的需求並登錄到 inputs/requirements.json。"
        ),
    }


def _physical_items(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"provided": False, "summary": {"total": 0, "measured": 0, "pending_measurement": 0}, "items": []}
    loaded = load_physical_items(path)
    policy = read_json(path).get("policy") or {}
    items = []
    for item in loaded["items"]:
        location = item.get("location") or {}
        transport = item.get("transport") if isinstance(item.get("transport"), dict) else None
        source = item.get("source") if isinstance(item.get("source"), dict) else {}
        items.append(
            {
                "id": item["id"],
                "label": item.get("label"),
                "category": item.get("category"),
                "quantity": item.get("quantity"),
                "building_id": location.get("building_id"),
                "floor_id": location.get("floor_id"),
                "requirement_id": location.get("requirement_id"),
                "active_dimensions_mm": item["active_dimensions"],
                "dimension_source": item["active_dimension_source"],
                "dimension_source_label": DIMENSION_SOURCE_LABELS[item["active_dimension_source"]],
                "measurement_count": len(item.get("measurements") or []),
                "transport": (
                    {
                        "door_clear_target_mm": transport.get("door_clear_target_mm"),
                        "carrying_poles_removable": transport.get("carrying_poles_removable"),
                        "assembled_dimensions_mm": transport.get("assembled_dimensions"),
                        "note": transport.get("note"),
                    }
                    if transport
                    else None
                ),
                "source_note": source.get("note"),
            }
        )
    return {"provided": True, "summary": loaded["summary"], "policy_note": policy.get("note"), "items": items}


def _public_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _public_values(item) for key, item in value.items() if not str(key).startswith("_")}
    if isinstance(value, list):
        return [_public_values(item) for item in value]
    return value


def _standards(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    config = read_json(path)
    geometry = config.get("geometry") or {}
    vehicle = config.get("vehicle") or {}
    return {
        "profile": config.get("profile"),
        "note": "前期討論用的一般住宅預設值；不是法規下限、完工淨寬或施工尺寸，個別需求的門寬與迴轉條件以需求登錄為準。",
        "door_width_mm": _public_values(geometry.get("door_width_mm")),
        "door_height_mm": geometry.get("door_height_mm"),
        "wall_thickness_mm": _public_values(geometry.get("wall_thickness_mm")),
        "furniture_mm": _public_values(config.get("furniture_mm")),
        "vehicle": {
            "suv_mm": _public_values(vehicle.get("suv_mm")),
            "clearance_mm": _public_values(vehicle.get("clearance_mm")),
            "ev_charger_mm": _public_values(vehicle.get("ev_charger_mm")),
        },
    }


def _source(key: str, path: Path, role: str) -> dict[str, Any]:
    exists = path.is_file()
    return {
        "key": key,
        "path": relative_to_root(path),
        "role": role,
        "exists": exists,
        "sha256": sha256_file(path) if exists else None,
    }


def build_design_brief(
    *,
    project_path: Path = PROJECT_PATH,
    requirements_path: Path = REQUIREMENTS_PATH,
    physical_items_path: Path = PHYSICAL_ITEMS_PATH,
    household_profile_path: Path = HOUSEHOLD_PROFILE_PATH,
    design_request_path: Path = DESIGN_REQUEST_PATH,
    standards_path: Path = STANDARDS_PATH,
    generated_at: str | None = None,
    planning_register_path: Path | None = None,
    planning_rules_path: Path = ROOT / "rules/predesign_readiness_rules.json",
) -> dict[str, Any]:
    project = read_json(project_path)
    project_issues = validate_project(project)
    if project_issues:
        raise ContractError(f"Cannot build a design brief from an invalid project: {project_issues}")
    physical_items = _physical_items(physical_items_path)
    physical_item_ids = {item["id"] for item in physical_items["items"]} if physical_items["provided"] else None
    register = read_json(requirements_path)
    requirement_issues = validate_requirements(register, physical_item_ids=physical_item_ids)
    if requirement_issues:
        raise ContractError(f"Cannot build a design brief from an invalid requirement register: {requirement_issues}")

    requirements = [item for item in register.get("requirements", []) if isinstance(item, dict)]
    titles = {str(item.get("id")): str(item.get("title") or "") for item in requirements}
    entries = [_requirement_entry(item, titles) for item in requirements]
    relationships = [relationship for entry in entries for relationship in entry["relationships"]]

    site_search = project.get("site_search") if isinstance(project.get("site_search"), dict) else {}
    target = site_search.get("target_scenario") if isinstance(site_search.get("target_scenario"), dict) else {}
    site_selected = site_search.get("selected_site") is not None
    ping = target.get("target_area_ping_each")
    buildings = [
        {
            "id": item.get("id"),
            "role": item.get("role"),
            "role_status": item.get("role_status"),
            "role_status_label": ROLE_STATUS_LABELS.get(str(item.get("role_status")), item.get("role_status")),
        }
        for item in project.get("buildings") or []
        if isinstance(item, dict)
    ]
    building_order = [str(item["id"]) for item in buildings if item.get("id")]
    building_order += sorted({str(entry["building_id"]) for entry in entries} - set(building_order))
    roles = {str(item["id"]): item.get("role") for item in buildings}

    by_building = []
    for building_id in building_order:
        scoped = sorted(
            (entry for entry in entries if str(entry["building_id"]) == building_id),
            key=lambda entry: (_floor_order(entry["floor_id"]), str(entry["id"])),
        )
        by_building.append(
            {
                "building_id": building_id,
                "role": roles.get(building_id),
                "counts": {key: sum(1 for entry in scoped if entry["status"] == key) for key in STATUS_LABELS},
                "sections": [
                    {
                        "status": key,
                        "label": label,
                        "note": note,
                        "requirements": [entry for entry in scoped if entry["status"] == key],
                    }
                    for key, label, note in STATUS_SECTIONS
                ],
            }
        )

    statuses = Counter(entry["status"] for entry in entries)
    priorities = Counter(entry["priority"] for entry in entries)
    relationship_statuses = Counter(relationship["status"] for relationship in relationships)
    confirmed = statuses.get("confirmed", 0)

    question_text = design_request_path.read_text(encoding="utf-8") if design_request_path.is_file() else ""
    extracted = extract_open_questions(question_text)
    links = _question_links(requirements)
    open_questions = [
        {
            "building_id": building_id,
            "role": roles.get(building_id),
            "questions": [
                {**question, "related_requirement_ids": sorted(links.get(question["id"], set()))}
                for question in extracted[building_id]
            ],
        }
        for building_id in [*building_order, *sorted(set(extracted) - set(building_order))]
        if building_id in extracted
    ]

    warnings = [SELECTED_SITE_WARNING if site_selected else SITE_WARNING, LEGACY_LAYOUT_NOTICE]
    if confirmed == 0:
        warnings.append(NO_CONFIRMED_NOTICE)

    brief: dict[str, Any] = {
        "schema": BRIEF_SCHEMA,
        "generated_at": generated_at or utc_now(),
        "project": {
            "project_id": project.get("project_id"),
            "name": project.get("name"),
            "stage": project.get("stage"),
            "jurisdiction": (project.get("jurisdiction") or {}).get("label"),
            "site_selected": site_selected,
            "selection_status": site_search.get("selection_status"),
            "candidate_site_count": len(site_search.get("candidate_sites") or []),
            "target_scenario": {
                "parcel_count": target.get("target_parcel_count"),
                "area_ping_each": ping,
                "area_sqm_each": round(ping * SQM_PER_PING, 1) if _number(ping) else None,
                "order_left_to_right": target.get("order_left_to_right"),
                "note": target.get("note"),
            },
            "authority_note": (project.get("authority") or {}).get("note"),
        },
        "warnings": warnings,
        "buildings": buildings,
        "shared_items_to_confirm": list((project.get("compound") or {}).get("shared_items_to_confirm") or []),
        "decision_summary": {
            "requirements": len(entries),
            "status_counts": {key: statuses.get(key, 0) for key in STATUS_LABELS},
            "priority_counts": {key: priorities.get(key, 0) for key in PRIORITY_LABELS},
            "confirmed_must": sum(1 for entry in entries if entry["status"] == "confirmed" and entry["priority"] == "must"),
            "relationships": len(relationships),
            "relationship_status_counts": {key: relationship_statuses.get(key, 0) for key in STATUS_LABELS},
        },
        "requirements_by_building": by_building,
        "relationships": relationships,
        "physical_items": physical_items,
        "household": household_summary(household_profile_path),
        "open_questions": open_questions,
        "standards": _standards(standards_path),
        "sources": [
            _source("project", project_path, "基地事實與未知欄位"),
            _source("requirements", requirements_path, "屋主需求狀態與決策紀錄"),
            _source("physical_items", physical_items_path, "大型實物規劃與實測尺寸"),
            _source("design_request", design_request_path, "原始需求討論（開會待問問題來源）"),
            _source("standards", standards_path, "前期預設尺寸"),
            {
                "key": "household_profile",
                "path": relative_to_root(household_profile_path),
                "role": "私有家庭檔案（只輸出去識別化統計，不列雜湊）",
                "exists": household_profile_path.is_file(),
                "sha256": None,
            },
        ],
    }
    if planning_register_path is not None or project_path.resolve() == PROJECT_PATH.resolve():
        from house_design.planning import REGISTER_PATH, build_risk_review, risk_summary

        brief["planning"] = risk_summary(build_risk_review(
            project_path=project_path, requirements_path=requirements_path,
            register_path=planning_register_path or REGISTER_PATH, rules_path=planning_rules_path,
            physical_items_path=physical_items_path,
        ))
        brief["sources"].extend([
            _source("planning_register", planning_register_path or REGISTER_PATH, "公開防漏項與情境決策清單"),
            _source("planning_rules", planning_rules_path, "情境與階段規則引用"),
        ])
    brief["brief_hash"] = design_brief_hash(brief)
    return brief


def design_brief_hash(brief: dict[str, Any]) -> str:
    return stable_hash({key: value for key, value in brief.items() if key not in {"generated_at", "brief_hash"}})


def _md(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "／").replace("\n", " ")


def _dimensions(value: dict[str, Any] | None) -> str:
    if not value:
        return "未知"
    return " × ".join(f"{value[key]:g}" for key in ("width_mm", "depth_mm", "height_mm") if _number(value.get(key)))


def _yes_no(value: bool | None) -> str:
    return "是" if value is True else "否" if value is False else "未填"


def _counts_text(values: dict[str, int]) -> str:
    return "、".join(f"{key} {count} 人" for key, count in values.items() if count) or "未填"


def _household_lines(household: dict[str, Any]) -> list[str]:
    if not household.get("provided") or not household.get("readable"):
        return [f"- {household.get('note')}"]
    lines = []
    if household.get("profile_is_template"):
        lines.append("- 私有家庭檔案仍標示為範本；以下統計不得視為事實。")
    lines.extend(
        [
            f"- 人數：{household['people_total']} 人（{household['member_entries']} 筆成員資料）",
            f"- 年齡級距：{_counts_text(household['age_bands'])}",
            f"- 慣用棟別：{_counts_text(household['usual_building'])}",
            f"- 目前行動力：{_counts_text(household['mobility_now'])}",
            f"- 10 年後行動力預估：{_counts_text(household['mobility_10_year_outlook'])}",
        ]
    )
    vehicles = "、".join(
        f"{item['category']} 現有 {item['current_count'] if item['current_count'] is not None else '未填'}"
        f"／未來 {item['future_count'] if item['future_count'] is not None else '未填'}"
        for item in household["vehicles"]
    )
    pets = "、".join(
        f"{item['category']} {item['count'] if item['count'] is not None else '數量未填'}"
        + (f"（{item['building_id']} 棟）" if item["building_id"] else "")
        for item in household["pets"]
    )
    religion = household["religious_practice"]
    entry_counts = household["entry_counts"]
    lines.extend(
        [
            f"- 車輛：{vehicles or '未填'}",
            f"- 寵物：{pets or '未填'}",
            f"- 過夜訪客：{_yes_no(household['overnight_guests'])}",
            f"- 日常共餐人數：{household['shared_meals_people'] if household['shared_meals_people'] is not None else '未填'}",
            "- 節慶聚會人數："
            + str(
                household["festival_or_large_gathering_people"]
                if household["festival_or_large_gathering_people"] is not None
                else "未填"
            ),
            f"- 祭祀或焚香：{_yes_no(religion['has_shrine_or_incense'])}；需煙火控制：{_yes_no(religion['smoke_and_fire_controls_required'])}",
            (
                f"- 私有檔另有：家庭變化 {entry_counts['planned_household_changes']} 筆、未來情境 "
                f"{entry_counts['future_change_scenarios']} 筆、設計方向 {entry_counts['design_directions']} 筆、"
                f"日常作息 {entry_counts['daily_routines']} 筆、優先問題 {entry_counts['priority_questions']} 題（內容不公開）"
            ),
            f"- 未輸出：{'；'.join(household['withheld'])}",
            f"- {household['note']}",
        ]
    )
    return lines


def design_brief_markdown(brief: dict[str, Any]) -> str:
    project = brief["project"]
    summary = brief["decision_summary"]
    target = project["target_scenario"]
    lines = [
        f"# 設計任務書（前期討論版）：{project['name']}",
        "",
        *[f"> ⚠ {warning}" for warning in brief["warnings"]],
        "",
        f"- 產生時間：{brief['generated_at']}",
        f"- 專案階段：`{project['stage']}`；管轄：{project['jurisdiction'] or '未填'}",
        f"- 任務書雜湊：`{brief['brief_hash']}`",
        "",
        "## 一、怎麼使用這份任務書",
        "",
        *[f"- 「{label}」：{note}" for _key, label, note in STATUS_SECTIONS],
        "- 需求 id 內含舊格局樓層（例如 `A.floor-1.elder`）；樓層只代表屋主建議位置，可以調整。",
        "- 空間關係只有在屋主確認所屬需求、且決策紀錄涵蓋該條關係時才算已確認；之後新增或修改的關係會回到待決定。",
        "- 更新流程：`intake requirements-sheet` 匯出決策表 → 家庭會議填寫 → "
        "`intake requirements-decide --batch` 套用 → `predesign brief` 重新產生本任務書。",
        "",
        "## 二、專案與基地狀態",
        "",
        f"- 選地狀態：{'已選定' if project['site_selected'] else '尚未選定'}（`{project['selection_status']}`，"
        f"候選土地 {project['candidate_site_count']} 筆）",
        f"- 目標情境：{target['parcel_count']} 筆相鄰土地，每筆約 {target['area_ping_each']} 坪"
        f"（約 {target['area_sqm_each']} m²），由左至右 {'／'.join(target['order_left_to_right'] or [])}",
        f"- {target['note'] or ''}",
        f"- {project['authority_note'] or ''}",
        "",
        "## 三、三棟定位",
        "",
        "| 棟 | 定位 | 狀態 |",
        "|---|---|---|",
        *[f"| {_md(item['id'])} | {_md(item['role'])} | {_md(item['role_status_label'])} |" for item in brief["buildings"]],
        "",
        "## 四、跨棟待確認事項",
        "",
        *[f"- {item}" for item in brief["shared_items_to_confirm"]],
        "",
        "## 五、需求決策摘要",
        "",
        "| 項目 | 已確認 | 待屋主決定 | 已淘汰 |",
        "|---|---|---|---|",
        "| 需求 | "
        + " | ".join(str(summary["status_counts"][key]) for key in STATUS_LABELS)
        + " |",
        "| 空間關係 | "
        + " | ".join(str(summary["relationship_status_counts"][key]) for key in STATUS_LABELS)
        + " |",
        "",
        f"- 需求共 {summary['requirements']} 項；優先度：必須 {summary['priority_counts']['must']}、"
        f"應該 {summary['priority_counts']['should']}、可以 {summary['priority_counts']['could']}；"
        f"已確認且必須 {summary['confirmed_must']} 項。",
        "- 待屋主決定的優先度只是舊版預設值，不代表屋主已排序。",
        "",
        "## 六、各棟需求",
        "",
    ]
    for group in brief["requirements_by_building"]:
        counts = group["counts"]
        lines.extend(
            [
                f"### {group['building_id']} 棟：{group['role'] or '未定義定位'}",
                "",
                f"已確認 {counts['confirmed']}、待屋主決定 {counts['candidate']}、已淘汰 {counts['rejected']}。",
                "",
            ]
        )
        for section in group["sections"]:
            lines.extend([f"#### {section['label']}（{len(section['requirements'])}）", ""])
            if not section["requirements"]:
                lines.extend([f"目前沒有{section['label']}的需求。", ""])
                continue
            for entry in section["requirements"]:
                lines.extend(
                    [
                        f"##### {entry['title']} `{entry['id']}`",
                        "",
                        f"- 樓層：{entry['floor_label']}（{entry['floor_note']}）；優先度：{entry['priority_label']}；"
                        f"驗證：{entry['verification_label']}",
                    ]
                )
                if entry["constraint_labels"]:
                    lines.append(f"- 條件：{'；'.join(entry['constraint_labels'])}")
                for relationship in entry["relationships"]:
                    label = source_label(relationship["source"])
                    lines.append(
                        f"- 空間關係［{relationship['status_label']}］{relationship['description']}。"
                        f"理由：{relationship['rationale']}" + (f"（來源：{label}）" if label else "")
                    )
                if entry["rationale"]:
                    label = "舊版說明（含舊情境尺寸，僅供理解）" if entry["rationale_is_legacy"] else "說明"
                    lines.append(f"- {label}：{entry['rationale']}")
                if entry["last_decision"]:
                    decision = entry["last_decision"]
                    lines.append(
                        f"- 最近決策：第 {decision['sequence']} 次，{decision['decided_at']}，理由：{decision['reason']}"
                    )
                lines.append("")
    lines.extend(
        [
            "## 七、空間關係總表",
            "",
            "| 需求 | 關係 | 狀態 | 理由 | 來源 |",
            "|---|---|---|---|---|",
        ]
    )
    for relationship in brief["relationships"]:
        lines.append(
            f"| {_md(relationship['requirement_title'])} `{relationship['requirement_id']}` "
            f"| {_md(relationship['description'])} | {relationship['status_label']} "
            f"| {_md(relationship['rationale'])} | {_md(source_label(relationship['source']))} |"
        )
    if not brief["relationships"]:
        lines.append("| （尚無結構化空間關係） | | | | |")
    physical = brief["physical_items"]
    lines.extend(["", "## 八、大型實物", ""])
    if not physical["provided"]:
        lines.extend(["- 未提供實物清單。", ""])
    else:
        lines.extend(
            [
                f"- 共 {physical['summary']['total']} 件；已實測 {physical['summary']['measured']}、"
                f"待實測 {physical['summary']['pending_measurement']}。",
                f"- {physical.get('policy_note') or ''}",
                "",
                "| id | 名稱 | 棟／樓層 | 寬 × 深 × 高 (mm) | 尺寸來源 | 搬運條件 |",
                "|---|---|---|---|---|---|",
            ]
        )
        for item in physical["items"]:
            transport = item["transport"] or {}
            transport_text = "；".join(
                part
                for part in (
                    f"門淨寬目標 ≥ {transport['door_clear_target_mm']:g} mm"
                    if _number(transport.get("door_clear_target_mm"))
                    else "",
                    f"抬桿可拆：{_yes_no(transport.get('carrying_poles_removable'))}" if transport else "",
                    f"組裝外廓 {_dimensions(transport.get('assembled_dimensions_mm'))}" if transport else "",
                    transport.get("note") or "",
                )
                if part
            )
            lines.append(
                f"| `{item['id']}` | {_md(item['label'])} | {_md(item['building_id'])}／{_floor_label(str(item['floor_id']))} "
                f"| {_dimensions(item['active_dimensions_mm'])} | {item['dimension_source_label']} | {_md(transport_text)} |"
            )
        lines.append("")
    lines.extend(["## 九、家庭概況（去識別化）", "", *_household_lines(brief["household"]), ""])
    lines.extend(["## 十、開會待問問題", ""])
    if not brief["open_questions"]:
        lines.extend(["- 未從原始需求討論擷取到問題清單。", ""])
    for group in brief["open_questions"]:
        lines.extend([f"### {group['building_id']} 棟（{len(group['questions'])} 題）", ""])
        for question in group["questions"]:
            related = question["related_requirement_ids"]
            suffix = f"（相關需求：{'、'.join(f'`{value}`' for value in related)}）" if related else ""
            lines.append(f"{question['number']}. **{question['id']}** {question['text']}{suffix}")
        lines.append("")
    standards = brief["standards"]
    lines.extend(["## 十一、基準值附錄", ""])
    if standards is None:
        lines.extend(["- 未提供預設尺寸設定檔。", ""])
    else:
        vehicle = standards["vehicle"]
        lines.extend(
            [
                f"- {standards['note']}",
                f"- 名目門寬 (mm)：{_standard_items(standards['door_width_mm'])}",
                f"- 門高：{standards['door_height_mm']} mm；牆厚 (mm)：{_standard_items(standards['wall_thickness_mm'])}",
                f"- 家具 (mm)：{_standard_items(standards['furniture_mm'])}",
                f"- 休旅車外廓 (mm)：{_dimensions_pair(vehicle['suv_mm'])}；車位淨空 (mm)：{_standard_items(vehicle['clearance_mm'])}",
                f"- 壁掛充電樁 (mm)：{_dimensions_pair(vehicle['ev_charger_mm'])}",
                "",
            ]
        )
    if brief.get("planning"):
        p = brief["planning"]
        lines.extend(["## 防漏項與當期決策", "", "[完整情境／驗收總表](risk-review.html)", "",
                      f"需求已追蹤 {p['summary']['tracked_requirements']}/{p['summary']['total_requirements']}（不等於已驗證）。", ""])
        lines.extend(f"- {i['id']}：{i['question']}（責任：{i['responsible_role']}）" for i in p["open_decisions"])
        lines.append("")
    lines.extend(["## 十二、資料來源", "", "| 檔案 | 用途 | SHA-256 |", "|---|---|---|"])
    for source in brief["sources"]:
        digest = f"`{source['sha256']}`" if source["sha256"] else ("存在，不列雜湊" if source["exists"] else "未提供")
        lines.append(f"| `{source['path']}` | {_md(source['role'])} | {digest} |")
    lines.extend(["", "---", "", f"任務書雜湊：`{brief['brief_hash']}`", ""])
    from house_design.owner_workspace import records_markdown

    return "\n".join(lines) + records_markdown(brief.get("planning", {}).get("owner_records", {}))


def _standard_label(key: Any) -> str:
    return STANDARD_KEY_LABELS.get(str(key), str(key))


def _dimensions_pair(value: Any) -> str:
    if _number(value):
        return f"{value:g}"
    if not isinstance(value, dict):
        return _standard_label(value) if value is not None else "未知"
    ordered = [key for key in ("length", "width", "depth", "height", "clear") if _number(value.get(key))]
    parts = [f"{_standard_label(key)} {value[key]:g}" for key in ordered]
    parts += [f"{_standard_label(key)} {_standard_label(item)}" for key, item in value.items() if key not in ordered]
    return "／".join(parts)


def _standard_items(values: dict[str, Any] | None) -> str:
    return "、".join(f"{_standard_label(key)} {_dimensions_pair(value)}" for key, value in (values or {}).items())


BRIEF_CSS = (
    "body{font:16px/1.65 system-ui,sans-serif;color:#17212b;background:#fff;max-width:960px;margin:32px auto;"
    "padding:0 20px}h1,h2,h3,h4,h5{line-height:1.25}h2{border-bottom:2px solid #d5dde5;padding-bottom:4px;"
    "margin-top:40px}.warn{border-left:5px solid #b45309;background:#fff7ed;padding:14px 16px;margin:8px 0}"
    "table{border-collapse:collapse;width:100%}th,td{border:1px solid #b8c2cc;padding:8px;text-align:left;"
    "vertical-align:top}code{background:#eef2f6;padding:2px 5px;overflow-wrap:anywhere}.table-wrap{overflow-x:auto}"
    ".req{border:1px solid #d5dde5;border-radius:6px;padding:10px 14px;margin:10px 0;break-inside:avoid}"
    ".req h5{margin:0 0 6px;font-size:17px}.req ul{margin:0;padding-left:20px}.meta{color:#475569}"
    ".badge{display:inline-block;border-radius:999px;padding:0 8px;font-size:13px;border:1px solid #94a3b8;"
    "margin-right:4px}.s-confirmed{background:#dcfce7;border-color:#15803d}.s-candidate{background:#fef9c3;"
    "border-color:#a16207}.s-rejected{background:#fee2e2;border-color:#b91c1c}nav ol{columns:2}"
    "footer{margin-top:40px;color:#475569;font-size:14px}@media (max-width:600px){nav ol{columns:1}}"
    "@media print{body{margin:0;max-width:none}nav{display:none}h2{break-after:avoid}}"
)


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _badge(status: str, label: str) -> str:
    return f'<span class="badge s-{_e(status)}">{_e(label)}</span>'


def _markdown_list_html(lines: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{_e(line[2:] if line.startswith('- ') else line)}</li>" for line in lines) + "</ul>"


def design_brief_html(brief: dict[str, Any]) -> str:
    project = brief["project"]
    summary = brief["decision_summary"]
    target = project["target_scenario"]
    sections = [
        ("usage", "一、怎麼使用這份任務書"),
        ("project", "二、專案與基地狀態"),
        ("buildings", "三、三棟定位"),
        ("shared", "四、跨棟待確認事項"),
        ("summary", "五、需求決策摘要"),
        ("requirements", "六、各棟需求"),
        ("relationships", "七、空間關係總表"),
        ("physical", "八、大型實物"),
        ("household", "九、家庭概況（去識別化）"),
        ("questions", "十、開會待問問題"),
        ("standards", "十一、基準值附錄"),
        ("sources", "十二、資料來源"),
    ]
    parts = [
        '<!doctype html>\n<html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>設計任務書：{_e(project['name'])}</title><style>{BRIEF_CSS}</style></head><body>",
        f"<h1>設計任務書（前期討論版）<br>{_e(project['name'])}</h1>",
        *[f'<p class="warn" role="note">⚠ {_e(warning)}</p>' for warning in brief["warnings"]],
        f'<p class="meta">產生時間：{_e(brief["generated_at"])}｜專案階段：<code>{_e(project["stage"])}</code>'
        f"｜任務書雜湊：<code>{_e(brief['brief_hash'])}</code></p>",
        '<nav aria-label="目錄"><ol>'
        + "".join(f'<li><a href="#{anchor}">{_e(title)}</a></li>' for anchor, title in sections)
        + "</ol></nav>",
        f'<h2 id="usage">{sections[0][1]}</h2><ul>',
        *[f"<li>{_badge(key, label)}{_e(note)}</li>" for key, label, note in STATUS_SECTIONS],
        "<li>需求 id 內含舊格局樓層（例如 <code>A.floor-1.elder</code>）；樓層只代表屋主建議位置，可以調整。</li>",
        "<li>空間關係只有在屋主確認所屬需求、且決策紀錄涵蓋該條關係時才算已確認；之後新增或修改的關係會回到待決定。</li>",
        "<li>更新流程：<code>intake requirements-sheet</code> 匯出決策表 → 家庭會議填寫 → "
        "<code>intake requirements-decide --batch</code> 套用 → <code>predesign brief</code> 重新產生本任務書。</li></ul>",
        f'<h2 id="project">{sections[1][1]}</h2><ul>',
        f"<li>選地狀態：{'已選定' if project['site_selected'] else '尚未選定'}（<code>{_e(project['selection_status'])}</code>，"
        f"候選土地 {_e(project['candidate_site_count'])} 筆）</li>",
        f"<li>目標情境：{_e(target['parcel_count'])} 筆相鄰土地，每筆約 {_e(target['area_ping_each'])} 坪"
        f"（約 {_e(target['area_sqm_each'])} m²），由左至右 {_e('／'.join(target['order_left_to_right'] or []))}</li>",
        f"<li>{_e(target['note'])}</li><li>{_e(project['authority_note'])}</li></ul>",
        f'<h2 id="buildings">{sections[2][1]}</h2><div class="table-wrap"><table><thead><tr><th>棟</th><th>定位</th>'
        "<th>狀態</th></tr></thead><tbody>",
        *[
            f"<tr><td>{_e(item['id'])}</td><td>{_e(item['role'])}</td><td>{_e(item['role_status_label'])}</td></tr>"
            for item in brief["buildings"]
        ],
        "</tbody></table></div>",
        f'<h2 id="shared">{sections[3][1]}</h2><ul>',
        *[f"<li>{_e(item)}</li>" for item in brief["shared_items_to_confirm"]],
        "</ul>",
        f'<h2 id="summary">{sections[4][1]}</h2><div class="table-wrap"><table><thead><tr><th>項目</th>',
        *[f"<th>{_e(label)}</th>" for label in STATUS_LABELS.values()],
        "</tr></thead><tbody><tr><td>需求</td>",
        *[f"<td>{summary['status_counts'][key]}</td>" for key in STATUS_LABELS],
        "</tr><tr><td>空間關係</td>",
        *[f"<td>{summary['relationship_status_counts'][key]}</td>" for key in STATUS_LABELS],
        "</tr></tbody></table></div>",
        f"<p>需求共 {summary['requirements']} 項；優先度：必須 {summary['priority_counts']['must']}、"
        f"應該 {summary['priority_counts']['should']}、可以 {summary['priority_counts']['could']}；"
        f"已確認且必須 {summary['confirmed_must']} 項。待屋主決定的優先度只是舊版預設值，不代表屋主已排序。</p>",
        f'<h2 id="requirements">{sections[5][1]}</h2>',
    ]
    for group in brief["requirements_by_building"]:
        counts = group["counts"]
        parts.append(
            f"<h3>{_e(group['building_id'])} 棟：{_e(group['role'] or '未定義定位')}</h3>"
            f'<p class="meta">已確認 {counts["confirmed"]}、待屋主決定 {counts["candidate"]}、已淘汰 {counts["rejected"]}。</p>'
        )
        for section in group["sections"]:
            parts.append(f"<h4>{_badge(section['status'], section['label'])}{len(section['requirements'])} 項</h4>")
            if not section["requirements"]:
                parts.append(f'<p class="meta">目前沒有{_e(section["label"])}的需求。</p>')
                continue
            for entry in section["requirements"]:
                items = [
                    f"樓層：{_e(entry['floor_label'])}（{_e(entry['floor_note'])}）；優先度：{_e(entry['priority_label'])}；"
                    f"驗證：{_e(entry['verification_label'])}"
                ]
                if entry["constraint_labels"]:
                    items.append("條件：" + _e("；".join(entry["constraint_labels"])))
                for relationship in entry["relationships"]:
                    label = source_label(relationship["source"])
                    items.append(
                        "空間關係 "
                        + _badge(relationship["status"], relationship["status_label"])
                        + f"<strong>{_e(relationship['description'])}</strong>。理由：{_e(relationship['rationale'])}"
                        + (f"（來源：{_e(label)}）" if label else "")
                    )
                if entry["rationale"]:
                    label = "舊版說明（含舊情境尺寸，僅供理解）" if entry["rationale_is_legacy"] else "說明"
                    items.append(f"{label}：{_e(entry['rationale'])}")
                if entry["last_decision"]:
                    decision = entry["last_decision"]
                    items.append(
                        f"最近決策：第 {_e(decision['sequence'])} 次，{_e(decision['decided_at'])}，理由：{_e(decision['reason'])}"
                    )
                parts.append(
                    f'<article class="req" id="req-{_e(entry["id"])}"><h5>{_badge(entry["status"], entry["status_label"])}'
                    f"{_e(entry['title'])} <code>{_e(entry['id'])}</code></h5><ul>"
                    + "".join(f"<li>{item}</li>" for item in items)
                    + "</ul></article>"
                )
    parts.append(
        f'<h2 id="relationships">{sections[6][1]}</h2><div class="table-wrap"><table><thead><tr><th>需求</th>'
        "<th>關係</th><th>狀態</th><th>理由</th><th>來源</th></tr></thead><tbody>"
    )
    for relationship in brief["relationships"]:
        parts.append(
            f"<tr><td>{_e(relationship['requirement_title'])}<br><code>{_e(relationship['requirement_id'])}</code></td>"
            f"<td>{_e(relationship['description'])}</td><td>{_badge(relationship['status'], relationship['status_label'])}</td>"
            f"<td>{_e(relationship['rationale'])}</td><td>{_e(source_label(relationship['source']))}</td></tr>"
        )
    if not brief["relationships"]:
        parts.append('<tr><td colspan="5">尚無結構化空間關係。</td></tr>')
    parts.append("</tbody></table></div>")
    physical = brief["physical_items"]
    parts.append(f'<h2 id="physical">{sections[7][1]}</h2>')
    if not physical["provided"]:
        parts.append("<p>未提供實物清單。</p>")
    else:
        parts.append(
            f"<p>共 {physical['summary']['total']} 件；已實測 {physical['summary']['measured']}、待實測 "
            f"{physical['summary']['pending_measurement']}。{_e(physical.get('policy_note'))}</p>"
            '<div class="table-wrap"><table><thead><tr><th>id</th><th>名稱</th><th>棟／樓層</th>'
            "<th>寬 × 深 × 高 (mm)</th><th>尺寸來源</th><th>搬運條件</th></tr></thead><tbody>"
        )
        for item in physical["items"]:
            transport = item["transport"] or {}
            notes = []
            if _number(transport.get("door_clear_target_mm")):
                notes.append(f"門淨寬目標 ≥ {transport['door_clear_target_mm']:g} mm")
            if transport:
                notes.append(f"抬桿可拆：{_yes_no(transport.get('carrying_poles_removable'))}")
                notes.append(f"組裝外廓 {_dimensions(transport.get('assembled_dimensions_mm'))}")
            if transport.get("note"):
                notes.append(str(transport["note"]))
            parts.append(
                f"<tr><td><code>{_e(item['id'])}</code></td><td>{_e(item['label'])}</td>"
                f"<td>{_e(item['building_id'])}／{_e(_floor_label(str(item['floor_id'])))}</td>"
                f"<td>{_e(_dimensions(item['active_dimensions_mm']))}</td><td>{_e(item['dimension_source_label'])}</td>"
                f"<td>{'<br>'.join(_e(note) for note in notes)}</td></tr>"
            )
        parts.append("</tbody></table></div>")
    parts.append(f'<h2 id="household">{sections[8][1]}</h2>' + _markdown_list_html(_household_lines(brief["household"])))
    parts.append(f'<h2 id="questions">{sections[9][1]}</h2>')
    if not brief["open_questions"]:
        parts.append("<p>未從原始需求討論擷取到問題清單。</p>")
    for group in brief["open_questions"]:
        parts.append(f"<h3>{_e(group['building_id'])} 棟（{len(group['questions'])} 題）</h3><ol>")
        for question in group["questions"]:
            related = question["related_requirement_ids"]
            suffix = (
                '<br><span class="meta">相關需求：'
                + "、".join(f'<a href="#req-{_e(value)}"><code>{_e(value)}</code></a>' for value in related)
                + "</span>"
                if related
                else ""
            )
            parts.append(
                f'<li value="{question["number"]}" id="{_e(question["id"])}"><strong>{_e(question["id"])}</strong> '
                f"{_e(question['text'])}{suffix}</li>"
            )
        parts.append("</ol>")
    parts.append(f'<h2 id="standards">{sections[10][1]}</h2>')
    standards = brief["standards"]
    if standards is None:
        parts.append("<p>未提供預設尺寸設定檔。</p>")
    else:
        vehicle = standards["vehicle"]
        parts.append(
            f"<p>{_e(standards['note'])}</p><ul>"
            f"<li>名目門寬 (mm)：{_e(_standard_items(standards['door_width_mm']))}</li>"
            f"<li>門高：{_e(standards['door_height_mm'])} mm；牆厚 (mm)：{_e(_standard_items(standards['wall_thickness_mm']))}</li>"
            f"<li>家具 (mm)：{_e(_standard_items(standards['furniture_mm']))}</li>"
            f"<li>休旅車外廓 (mm)：{_e(_dimensions_pair(vehicle['suv_mm']))}；"
            f"車位淨空 (mm)：{_e(_standard_items(vehicle['clearance_mm']))}</li>"
            f"<li>壁掛充電樁 (mm)：{_e(_dimensions_pair(vehicle['ev_charger_mm']))}</li></ul>"
        )
    parts.append(
        f'<h2 id="sources">{sections[11][1]}</h2><div class="table-wrap"><table><thead><tr><th>檔案</th><th>用途</th>'
        "<th>SHA-256</th></tr></thead><tbody>"
    )
    for source in brief["sources"]:
        digest = (
            f"<code>{_e(source['sha256'])}</code>"
            if source["sha256"]
            else ("存在，不列雜湊" if source["exists"] else "未提供")
        )
        parts.append(f"<tr><td><code>{_e(source['path'])}</code></td><td>{_e(source['role'])}</td><td>{digest}</td></tr>")
    parts.append("</tbody></table></div>")
    if brief.get("planning"):
        p = brief["planning"]
        from house_design.owner_workspace import records_html

        parts.append(records_html(p.get("owner_records", {})))
        parts.append('<h2 id="planning">防漏項與當期決策</h2><p><a href="risk-review.html">完整情境／驗收總表</a></p>'
                     f'<p>需求已追蹤 {p["summary"]["tracked_requirements"]}/{p["summary"]["total_requirements"]}；不等於已驗證。</p><ul>')
        parts.extend(f'<li><strong>{_e(i["id"])}</strong>：{_e(i["question"])}（{_e(i["responsible_role"])}）</li>' for i in p["open_decisions"])
        parts.append('</ul>')
    parts.append(f"<footer>任務書雜湊：<code>{_e(brief['brief_hash'])}</code></footer></body></html>\n")
    return "".join(parts)


def write_design_brief(brief: dict[str, Any], output_root: Path = PREDESIGN_OUTPUT_ROOT) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": output_root / "design-brief.json",
        "markdown": output_root / "design-brief.md",
        "html": output_root / "design-brief.html",
    }
    write_json(paths["json"], brief)
    from house_design.owner_workspace import tool_links

    paths["markdown"].write_text(design_brief_markdown(brief), encoding="utf-8", newline="\n")

    paths["html"].write_text(tool_links(design_brief_html(brief), output_root), encoding="utf-8", newline="\n")
    return paths

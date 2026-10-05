from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from house_design.contracts import (
    REQUIREMENT_PRIORITIES,
    REQUIREMENT_STATUSES,
    ROOT,
    ContractError,
    read_json,
    relative_to_root,
    require_choice,
    stable_hash,
    utc_now,
    write_json,
)
from house_design.physical_items import PHYSICAL_ITEMS_PATH, validate_physical_items

PROJECT_PATH = ROOT / "inputs/project.json"
REQUIREMENTS_PATH = ROOT / "inputs/requirements.json"
DECISION_SHEET_SCHEMA = "house-requirement-decision-sheet-v1"
DECISION_SHEET_PATH = ROOT / "structured/predesign/requirements-sheet.json"
SITE_CRITERIA_PATH = ROOT / "inputs/site-criteria.json"

# Structured room-to-room constraints. Each entry lives on the requirement that
# owns the constraint and points at another requirement id (or a special target).
RELATIONSHIP_TYPES: dict[str, str] = {
    "adjacent": "必須相鄰",
    "direct_access": "須直接可達，不穿越其他房間",
    "not_facing": "門不得正對",
    "not_stacked_over": "不得位於其上方",
    "not_stacked_under": "不得位於其下方",
    "stacked_over": "應上下對齊（位於其上方）",
    "no_through_view": "不得一眼看穿（穿堂）",
    "transport_path": "須保留搬運路徑",
    "separate_ventilation": "須獨立排氣，不得共管",
}
RELATIONSHIP_SPECIAL_TARGETS: dict[str, str] = {
    "entry": "大門／入口",
    "exterior": "戶外",
    "street": "道路",
    "stair": "樓梯",
}

SITE_FACTS: tuple[tuple[str, str], ...] = (
    ("land_number", "地號"),
    ("zoning", "使用分區"),
    ("road", "道路條件"),
    ("building_coverage_ratio", "建蔽率"),
    ("floor_area_ratio", "容積率"),
    ("setbacks", "退縮條件"),
)

PROJECT_SCHEMAS = {"house-project-v2", "house-project-v3"}
PROJECT_STAGES = {"site_search", "site_due_diligence", "design", "tender", "construction", "handover"}


UNKNOWN_STATUSES = {"unknown", "pending", "needs_confirmation"}


def is_known(value: Any) -> bool:
    """One shared answer to "has anyone actually established this yet?".

    Site screening asks the same question of candidate-site fields that parcel
    readiness asks of selected parcels, so the rule lives in one place: an
    explicit unknown status beats any sibling value that happens to be filled.
    """

    if value is None or value == "":
        return False
    if isinstance(value, str) and value.strip().lower() in UNKNOWN_STATUSES | {"", "unverified", "assumed", "estimated"}:
        return False
    if isinstance(value, dict):
        if value.get("status") in UNKNOWN_STATUSES:
            return False
        return any(is_known(item) for key, item in value.items() if not key.startswith("_"))
    return True


def validate_project(project: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    schema = project.get("schema")
    if schema not in PROJECT_SCHEMAS:
        return [{"field": "schema", "message": "schema must be house-project-v2 or house-project-v3"}]
    jurisdiction = project.get("jurisdiction") or {}
    if jurisdiction.get("country_code") != "TW" or jurisdiction.get("county_code") != "KHH":
        issues.append({"field": "jurisdiction", "message": "project must identify Taiwan / Kaohsiung (KHH)"})

    if schema == "house-project-v2":
        return [*issues, *_validate_v2_project(project)]
    return [*issues, *_validate_v3_project(project)]


def _validate_v2_project(project: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if project.get("parcel_relationship") != "adjacent_separate_parcels":
        issues.append(
            {
                "field": "parcel_relationship",
                "message": "legacy v2 scenario must be adjacent_separate_parcels",
            }
        )
    parcels = project.get("parcels")
    if not isinstance(parcels, list) or len(parcels) != 3:
        issues.append({"field": "parcels", "message": "exactly three adjacent parcel records are required"})
        return issues
    ids = [str(parcel.get("id") or "") for parcel in parcels if isinstance(parcel, dict)]
    if sorted(ids) != ["A", "B", "C"]:
        issues.append({"field": "parcels[].id", "message": "parcel ids must be A, B and C"})
    for index, parcel in enumerate(parcels):
        if not isinstance(parcel, dict):
            issues.append({"field": f"parcels[{index}]", "message": "parcel must be an object"})
            continue
        area = parcel.get("parcel_area_ping")
        if not isinstance(area, (int, float)) or area <= 0:
            issues.append(
                {"field": f"parcels[{index}].parcel_area_ping", "message": "positive parcel area is required"}
            )
        if "footprint_ping" in parcel:
            issues.append(
                {
                    "field": f"parcels[{index}].footprint_ping",
                    "message": "parcel area must not be stored as an assumed building footprint",
                }
            )
    return issues


def _validate_v3_project(project: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    stage = str(project.get("stage") or "")
    if stage not in PROJECT_STAGES:
        issues.append({"field": "stage", "message": f"stage must be one of: {', '.join(sorted(PROJECT_STAGES))}"})
    if "parcels" in project:
        issues.append(
            {
                "field": "parcels",
                "message": "v3 stores actual parcels under site_search.selected_site; targets are not parcel facts",
            }
        )
    search = project.get("site_search")
    if not isinstance(search, dict):
        return [*issues, {"field": "site_search", "message": "site_search object is required"}]
    target = search.get("target_scenario")
    if not isinstance(target, dict):
        issues.append({"field": "site_search.target_scenario", "message": "target_scenario object is required"})
    else:
        if target.get("parcel_relationship") != "adjacent_separate_parcels":
            issues.append(
                {
                    "field": "site_search.target_scenario.parcel_relationship",
                    "message": "target scenario must be adjacent_separate_parcels",
                }
            )
        if target.get("target_parcel_count") != 3:
            issues.append(
                {"field": "site_search.target_scenario.target_parcel_count", "message": "target parcel count must be 3"}
            )
        area = target.get("target_area_ping_each")
        if not isinstance(area, (int, float)) or area <= 0:
            issues.append(
                {
                    "field": "site_search.target_scenario.target_area_ping_each",
                    "message": "positive target area is required",
                }
            )
    candidates = search.get("candidate_sites")
    if not isinstance(candidates, list):
        issues.append({"field": "site_search.candidate_sites", "message": "candidate_sites must be an array"})
    else:
        candidate_ids: set[str] = set()
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                issues.append(
                    {"field": f"site_search.candidate_sites[{index}]", "message": "candidate must be an object"}
                )
                continue
            candidate_id = str(candidate.get("candidate_id") or "")
            if not candidate_id or candidate_id in candidate_ids:
                issues.append(
                    {
                        "field": f"site_search.candidate_sites[{index}].candidate_id",
                        "message": "candidate_id is required and unique",
                    }
                )
            candidate_ids.add(candidate_id)
            if candidate.get("status") not in {"screening", "due_diligence", "rejected", "selected"}:
                issues.append(
                    {
                        "field": f"site_search.candidate_sites[{index}].status",
                        "message": "status must be screening, due_diligence, rejected or selected",
                    }
                )
    buildings = project.get("buildings")
    if not isinstance(buildings, list) or sorted(str(item.get("id")) for item in buildings if isinstance(item, dict)) != [
        "A",
        "B",
        "C",
    ]:
        issues.append({"field": "buildings", "message": "building planning roles A, B and C are required"})
    selected = search.get("selected_site")
    if selected is not None:
        if not isinstance(selected, dict):
            issues.append({"field": "site_search.selected_site", "message": "selected_site must be an object or null"})
        else:
            parcels = selected.get("parcels")
            if not isinstance(parcels, list) or len(parcels) != 3:
                issues.append(
                    {"field": "site_search.selected_site.parcels", "message": "a selected site requires three parcel records"}
                )
            else:
                parcel_ids = [str(parcel.get("id") or "") for parcel in parcels if isinstance(parcel, dict)]
                if sorted(parcel_ids) != ["A", "B", "C"]:
                    issues.append(
                        {
                            "field": "site_search.selected_site.parcels[].id",
                            "message": "selected parcel ids must be A, B and C",
                        }
                    )
                for index, parcel in enumerate(parcels):
                    if not isinstance(parcel, dict):
                        issues.append(
                            {"field": f"site_search.selected_site.parcels[{index}]", "message": "parcel must be an object"}
                        )
                    elif "footprint_ping" in parcel:
                        issues.append(
                            {
                                "field": f"site_search.selected_site.parcels[{index}].footprint_ping",
                                "message": "parcel area must not be stored as an assumed building footprint",
                            }
                        )
                    elif parcel.get("parcel_area_sqm") is not None and (
                        not isinstance(parcel.get("parcel_area_sqm"), (int, float))
                        or parcel["parcel_area_sqm"] <= 0
                    ):
                        issues.append(
                            {
                                "field": f"site_search.selected_site.parcels[{index}].parcel_area_sqm",
                                "message": "parcel_area_sqm must be null or positive",
                            }
                        )
    if stage != "site_search" and selected is None:
        issues.append(
            {"field": "site_search.selected_site", "message": f"selected_site is required once stage is {stage}"}
        )
    return issues


def actual_parcels(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only real selected parcel records, never site-search targets."""

    if project.get("schema") == "house-project-v3":
        selected = (project.get("site_search") or {}).get("selected_site") or {}
        values = selected.get("parcels") or []
    else:
        values = project.get("parcels") or []
    return [item for item in values if isinstance(item, dict)]


def target_parcel_ids(project: dict[str, Any]) -> list[str]:
    if project.get("schema") == "house-project-v3":
        ids = [str(item.get("id")) for item in project.get("buildings") or [] if isinstance(item, dict)]
        return sorted(value for value in ids if value)
    return sorted(str(item.get("id")) for item in actual_parcels(project) if item.get("id"))


def project_readiness(project: dict[str, Any]) -> dict[str, Any]:
    parcels = actual_parcels(project)
    expected_ids = target_parcel_ids(project)
    facts: list[dict[str, Any]] = []
    if project.get("schema") == "house-project-v3":
        selected = bool(parcels) and len(parcels) == len(expected_ids)
        facts.append(
            {
                "key": "site_selection",
                "label": "土地選定",
                "known": selected,
                "known_count": 1 if selected else 0,
                "total_count": 1,
                "parcels": [{"parcel_id": "site", "known": selected, "value": "selected" if selected else None}],
            }
        )
    for key, label in SITE_FACTS:
        parcel_states = []
        by_id = {str(parcel.get("id")): parcel for parcel in parcels}
        for parcel_id in expected_ids:
            parcel = by_id.get(parcel_id, {})
            value = parcel.get(key)
            parcel_states.append({"parcel_id": parcel_id, "known": is_known(value), "value": value})
        known_count = sum(1 for state in parcel_states if state["known"])
        facts.append(
            {
                "key": key,
                "label": label,
                "known": bool(parcel_states) and known_count == len(parcel_states),
                "known_count": known_count,
                "total_count": len(parcel_states),
                "parcels": parcel_states,
            }
        )
    completed = sum(1 for item in facts if item["known"])
    return {
        "completed": completed,
        "total": len(facts),
        "percent": round(completed / len(facts) * 100) if facts else 0,
        "facts": facts,
    }


def _validate_relationships(
    item: dict[str, Any],
    field: str,
    known_ids: set[str],
    physical_item_ids: set[str] | None,
) -> list[dict[str, str]]:
    relationships = item.get("relationships")
    if relationships is None:
        return []
    if not isinstance(relationships, list):
        return [{"field": field, "message": "relationships must be an array"}]
    issues: list[dict[str, str]] = []
    own_id = str(item.get("id") or "")

    def _check_target(value: Any, target_field: str, *, allow_special: bool) -> None:
        target = str(value or "").strip()
        if not target:
            issues.append({"field": target_field, "message": "target requirement id is required"})
        elif target == own_id:
            issues.append({"field": target_field, "message": "a relationship cannot point at its own requirement"})
        elif target in known_ids or (allow_special and target in RELATIONSHIP_SPECIAL_TARGETS):
            return
        else:
            issues.append({"field": target_field, "message": f"unknown relationship target: {target}"})

    for index, relationship in enumerate(relationships):
        entry_field = f"{field}[{index}]"
        if not isinstance(relationship, dict):
            issues.append({"field": entry_field, "message": "relationship must be an object"})
            continue
        relationship_type = str(relationship.get("type") or "")
        if relationship_type not in RELATIONSHIP_TYPES:
            issues.append(
                {
                    "field": f"{entry_field}.type",
                    "message": f"type must be one of: {', '.join(sorted(RELATIONSHIP_TYPES))}",
                }
            )
        _check_target(relationship.get("target"), f"{entry_field}.target", allow_special=True)
        avoid = relationship.get("must_not_pass_through")
        if avoid is not None:
            if not isinstance(avoid, list):
                issues.append({"field": f"{entry_field}.must_not_pass_through", "message": "must be an array"})
            else:
                for avoid_index, value in enumerate(avoid):
                    _check_target(value, f"{entry_field}.must_not_pass_through[{avoid_index}]", allow_special=False)
        if not str(relationship.get("rationale") or "").strip():
            issues.append({"field": f"{entry_field}.rationale", "message": "rationale is required"})
        if "status" in relationship:
            issues.append(
                {
                    "field": f"{entry_field}.status",
                    "message": "relationship status is derived from the requirement decision log; remove it",
                }
            )
        source = relationship.get("source")
        if source is not None and (not isinstance(source, dict) or not source.get("type") or not source.get("path")):
            issues.append({"field": f"{entry_field}.source", "message": "source type and path are required"})
        clear_width = relationship.get("clear_width_mm")
        if clear_width is not None and (
            isinstance(clear_width, bool) or not isinstance(clear_width, (int, float)) or clear_width <= 0
        ):
            issues.append({"field": f"{entry_field}.clear_width_mm", "message": "must be a positive millimetre value"})
        object_id = relationship.get("object_id")
        if relationship_type == "transport_path" and not str(object_id or "").strip():
            issues.append({"field": f"{entry_field}.object_id", "message": "transport_path requires a physical item id"})
        elif object_id is not None and physical_item_ids is not None and str(object_id) not in physical_item_ids:
            issues.append({"field": f"{entry_field}.object_id", "message": f"unknown physical item: {object_id}"})
    return issues


# Fields that record the owner's decision rather than what the requirement says.
DECISION_STATE_FIELDS = frozenset({"status", "priority", "decision_log", "verification"})


def requirement_content_hash(requirement: dict[str, Any]) -> str:
    """Hash what the owner reads when deciding, so stale decision sheets can be refused."""

    return stable_hash({key: value for key, value in requirement.items() if key not in DECISION_STATE_FIELDS})


def relationship_hash(relationship: dict[str, Any]) -> str:
    return stable_hash(relationship)


def relationship_target_label(target: str, titles: dict[str, str]) -> str:
    if target in RELATIONSHIP_SPECIAL_TARGETS:
        return RELATIONSHIP_SPECIAL_TARGETS[target]
    title = titles.get(target)
    return f"{title}（{target}）" if title else target


def describe_relationship(relationship: dict[str, Any], titles: dict[str, str]) -> str:
    """One readable zh-TW line, shared by the decision sheet and the design brief."""

    relationship_type = str(relationship.get("type") or "")
    parts = [
        f"{RELATIONSHIP_TYPES.get(relationship_type, relationship_type)}："
        f"{relationship_target_label(str(relationship.get('target') or ''), titles)}"
    ]
    avoid = relationship.get("must_not_pass_through") or []
    if avoid:
        parts.append("不得穿越 " + "、".join(relationship_target_label(str(value), titles) for value in avoid))
    if relationship.get("object_id"):
        parts.append(f"搬運物件 {relationship['object_id']}")
    if isinstance(relationship.get("clear_width_mm"), (int, float)):
        parts.append(f"淨寬目標 ≥ {relationship['clear_width_mm']:g} mm")
    return "；".join(parts)


def relationship_status(requirement: dict[str, Any], relationship: dict[str, Any]) -> str:
    """Derive a relationship's status from the owner's latest logged decision.

    A confirmed requirement only confirms the relationships whose exact content was
    recorded in that decision entry; anything added or edited afterwards stays a
    candidate until the owner decides again.
    """

    status = str(requirement.get("status") or "candidate")
    if status != "confirmed":
        return status
    decision_log = requirement.get("decision_log") or []
    latest = decision_log[-1] if decision_log and isinstance(decision_log[-1], dict) else {}
    covered = latest.get("relationship_hashes")
    if isinstance(covered, list) and relationship_hash(relationship) in covered:
        return "confirmed"
    return "candidate"


def validate_requirements(
    payload: dict[str, Any], *, physical_item_ids: set[str] | None = None
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if payload.get("schema") != "house-requirements-v2":
        issues.append({"field": "schema", "message": "schema must be house-requirements-v2"})
    items = payload.get("requirements")
    if not isinstance(items, list):
        return [*issues, {"field": "requirements", "message": "requirements must be an array"}]
    known_ids = {str(item.get("id")) for item in items if isinstance(item, dict) and item.get("id")}
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append({"field": f"requirements[{index}]", "message": "requirement must be an object"})
            continue
        requirement_id = str(item.get("id") or "")
        if not requirement_id:
            issues.append({"field": f"requirements[{index}].id", "message": "id is required"})
        elif requirement_id in seen:
            issues.append({"field": f"requirements[{index}].id", "message": "id must be unique"})
        seen.add(requirement_id)
        try:
            require_choice(str(item.get("status")), REQUIREMENT_STATUSES, f"requirements[{index}].status")
            require_choice(str(item.get("priority")), REQUIREMENT_PRIORITIES, f"requirements[{index}].priority")
        except ContractError as exc:
            issues.append({"field": f"requirements[{index}]", "message": str(exc)})
        source = item.get("source") or {}
        if not source.get("type") or not source.get("path"):
            issues.append(
                {"field": f"requirements[{index}].source", "message": "source type and path are required"}
            )
        issues.extend(
            _validate_relationships(item, f"requirements[{index}].relationships", known_ids, physical_item_ids)
        )
        decision_log = item.get("decision_log")
        if decision_log is not None:
            if not isinstance(decision_log, list):
                issues.append(
                    {"field": f"requirements[{index}].decision_log", "message": "decision_log must be an array"}
                )
            else:
                previous_hash = None
                for decision_index, decision in enumerate(decision_log):
                    field = f"requirements[{index}].decision_log[{decision_index}]"
                    if not isinstance(decision, dict):
                        issues.append({"field": field, "message": "decision entry must be an object"})
                        continue
                    stored_hash = decision.get("entry_hash")
                    expected_hash = stable_hash({key: value for key, value in decision.items() if key != "entry_hash"})
                    required = all(
                        isinstance(decision.get(key), str) and bool(decision[key].strip())
                        for key in ("status", "priority", "reason", "decided_by", "decided_at")
                    )
                    if not required:
                        issues.append({"field": field, "message": "decision entry is missing required fields"})
                    covered = decision.get("relationship_hashes")
                    if covered is not None and (
                        not isinstance(covered, list) or not all(isinstance(value, str) for value in covered)
                    ):
                        issues.append({"field": field, "message": "relationship_hashes must be an array of hashes"})
                    if decision.get("previous_entry_hash") != previous_hash:
                        issues.append({"field": field, "message": "decision hash chain is broken"})
                    if stored_hash != expected_hash:
                        issues.append({"field": field, "message": "decision entry hash does not match"})
                    previous_hash = stored_hash
    return issues


def decide_requirement(
    *,
    requirement_id: str,
    status: str,
    priority: str,
    reason: str,
    decided_by: str,
    decided_at: str | None = None,
    requirements_path: Path = REQUIREMENTS_PATH,
) -> dict[str, Any]:
    """Apply an owner decision and append a hash-chained, never-rewritten log entry."""

    payload = read_json(requirements_path)
    existing_issues = validate_requirements(payload)
    if existing_issues:
        raise ContractError(f"Cannot decide an invalid requirement register: {existing_issues}")
    entry = _apply_decision(
        payload,
        requirement_id=requirement_id,
        status=status,
        priority=priority,
        reason=reason,
        decided_by=decided_by,
        decided_at=decided_at or utc_now(),
    )
    payload["updated_at"] = utc_now()
    issues = validate_requirements(payload)
    if issues:
        raise ContractError(f"Decision would make requirement register invalid: {issues}")
    write_json(requirements_path, payload)
    return {
        "schema": "house-requirement-decision-result-v1",
        "requirement_id": requirement_id,
        "status": status,
        "priority": priority,
        "decision_sequence": entry["sequence"],
        "entry_hash": entry["entry_hash"],
        "requirements_path": str(requirements_path),
    }


def _apply_decision(
    payload: dict[str, Any],
    *,
    requirement_id: str,
    status: str,
    priority: str,
    reason: str,
    decided_by: str,
    decided_at: str,
) -> dict[str, Any]:
    """Append one hash-chained decision to an in-memory register; the caller writes the file."""

    require_choice(status, {"confirmed", "rejected"}, "status")
    require_choice(priority, REQUIREMENT_PRIORITIES, "priority")
    reason = reason.strip()
    decided_by = decided_by.strip()
    decided_at = decided_at.strip()
    if not requirement_id.strip() or not reason or not decided_by or not decided_at:
        raise ContractError("id, reason, decided_by and decided_at must be non-empty")
    requirement = next(
        (item for item in payload.get("requirements", []) if item.get("id") == requirement_id),
        None,
    )
    if requirement is None:
        raise ContractError(f"Unknown requirement id: {requirement_id}")
    decision_log = requirement.setdefault("decision_log", [])
    if not isinstance(decision_log, list):
        raise ContractError(f"requirement {requirement_id} has an invalid decision_log")
    previous_hash = decision_log[-1].get("entry_hash") if decision_log else None
    entry: dict[str, Any] = {
        "sequence": len(decision_log) + 1,
        "previous": {
            "status": requirement.get("status"),
            "priority": requirement.get("priority"),
        },
        "status": status,
        "priority": priority,
        "reason": reason,
        "decided_by": decided_by,
        "decided_at": decided_at,
        "relationship_hashes": [
            relationship_hash(relationship)
            for relationship in requirement.get("relationships") or []
            if isinstance(relationship, dict)
        ],
        "previous_entry_hash": previous_hash,
    }
    entry["entry_hash"] = stable_hash(entry)
    decision_log.append(entry)
    requirement["status"] = status
    requirement["priority"] = priority
    verification = requirement.setdefault("verification", {})
    if isinstance(verification, dict):
        verification["state"] = "owner_confirmed" if status == "confirmed" else "owner_rejected"
        verification["last_decision_hash"] = entry["entry_hash"]
    return entry


SHEET_DECISION_FIELDS = ("decision_status", "decision_priority", "reason")


def export_requirement_sheet(
    *, requirements_path: Path = REQUIREMENTS_PATH, output: Path = DECISION_SHEET_PATH
) -> dict[str, Any]:
    """Write a fill-in sheet so a whole family meeting can be recorded in one batch."""

    payload = read_json(requirements_path)
    issues = validate_requirements(payload)
    if issues:
        raise ContractError(f"Cannot export an invalid requirement register: {issues}")
    titles = {str(item.get("id")): str(item.get("title") or "") for item in payload.get("requirements", [])}
    rows = []
    for item in payload.get("requirements", []):
        applies_to = item.get("applies_to") or {}
        rows.append(
            {
                "id": item["id"],
                "title": item.get("title"),
                "building_id": applies_to.get("building_id"),
                "floor_id": applies_to.get("floor_id"),
                "current_status": item.get("status"),
                "current_priority": item.get("priority"),
                "relationships": [describe_relationship(value, titles) for value in item.get("relationships") or []],
                "requirement_hash": requirement_content_hash(item),
                "decision_count": len(item.get("decision_log") or []),
                "decision_status": None,
                "decision_priority": None,
                "reason": None,
            }
        )
    sheet = {
        "schema": DECISION_SHEET_SCHEMA,
        "generated_at": utc_now(),
        "source_requirements": relative_to_root(requirements_path),
        "instructions": [
            "只填要在這次會議決定的列：decision_status 填 confirmed 或 rejected，decision_priority 填 must／should／could，reason 填決定理由。",
            "三欄留空的列會被略過；只填一部分的列會讓整批被拒絕，不會寫入任何決策。",
            "confirmed 會同時確認該列 relationships 列出的空間關係；不同意其中一條時，先修改需求登錄再重新匯出本表。",
            "匯出後若需求內容被修改或該列已另有新決策，requirement_hash／decision_count 會不符，整批會被拒絕；請重新匯出。",
            "填好後在專案根目錄執行：.venv/bin/python -m house_design intake requirements-decide --batch <本檔> --decided-by <決策者>。",
            "決策以 hash-chained decision log 追加，不會改寫歷史；改變主意時再追加新決策。",
        ],
        "rows": rows,
    }
    write_json(output, sheet)
    markdown_path = output.with_suffix(".md")
    markdown_path.write_text(_sheet_markdown(sheet), encoding="utf-8", newline="\n")
    return {
        "schema": DECISION_SHEET_SCHEMA,
        "sheet": str(output),
        "markdown": str(markdown_path),
        "rows": len(rows),
        "undecided": sum(1 for row in rows if row["current_status"] == "candidate"),
    }


def _sheet_markdown(sheet: dict[str, Any]) -> str:
    lines = [
        "# 需求決策表（會議用）",
        "",
        f"- 來源：`{sheet['source_requirements']}`",
        f"- 產生時間：{sheet['generated_at']}",
        "- 在 JSON 版填入 decision_status／decision_priority／reason，再以 `intake requirements-decide --batch` 套用。",
        "",
        "- 決定 confirmed 時，同列「空間關係」也一併確認。",
        "",
        "| id | 需求 | 棟 | 樓層 | 目前狀態 | 目前優先 | 空間關係 | 決定 | 優先 | 理由 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in sheet["rows"]:
        relationships = "<br>".join(_table_cell(value) for value in row.get("relationships") or [])
        lines.append(
            f"| `{row['id']}` | {_table_cell(row.get('title'))} | {row.get('building_id') or ''} "
            f"| {row.get('floor_id') or ''} | {row.get('current_status')} | {row.get('current_priority')} "
            f"| {relationships} | | | |"
        )
    lines.append("")
    return "\n".join(lines)


def _table_cell(value: Any) -> str:
    return str(value or "").replace("|", "／").replace("\n", " ")


def apply_requirement_decisions(
    *,
    sheet_path: Path,
    decided_by: str,
    decided_at: str | None = None,
    requirements_path: Path = REQUIREMENTS_PATH,
) -> dict[str, Any]:
    """Validate every filled row first, then append all decisions and write once."""

    decided_by = decided_by.strip()
    decided_at = (decided_at or utc_now()).strip()
    if not decided_by:
        raise ContractError("decided_by must be non-empty")
    sheet = read_json(sheet_path)
    if sheet.get("schema") != DECISION_SHEET_SCHEMA:
        raise ContractError(f"sheet schema must be {DECISION_SHEET_SCHEMA}")
    rows = sheet.get("rows")
    if not isinstance(rows, list):
        raise ContractError("sheet rows must be an array")
    payload = read_json(requirements_path)
    existing_issues = validate_requirements(payload)
    if existing_issues:
        raise ContractError(f"Cannot decide an invalid requirement register: {existing_issues}")
    by_id = {str(item.get("id")): item for item in payload.get("requirements", [])}

    problems: list[str] = []
    decisions: list[dict[str, str]] = []
    seen: set[str] = set()
    skipped = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"rows[{index}]: row must be an object")
            continue
        values = {key: (str(row.get(key) or "").strip()) for key in SHEET_DECISION_FIELDS}
        if not any(values.values()):
            skipped += 1
            continue
        row_id = str(row.get("id") or "").strip()
        if not row_id or row_id not in by_id:
            problems.append(f"rows[{index}]: unknown requirement id {row_id!r}")
        elif row_id in seen:
            problems.append(f"rows[{index}]: duplicate decision for {row_id}")
        elif row.get("requirement_hash") != requirement_content_hash(by_id[row_id]):
            problems.append(
                f"rows[{index}] ({row_id}): requirement changed since the sheet was exported; export a new sheet"
            )
        elif row.get("decision_count") != len(by_id[row_id].get("decision_log") or []):
            # Re-applying an old sheet must not replay or override a decision recorded after export.
            problems.append(
                f"rows[{index}] ({row_id}): a newer decision was recorded since the sheet was exported; "
                "export a new sheet"
            )
        seen.add(row_id)
        if values["decision_status"] not in {"confirmed", "rejected"}:
            problems.append(f"rows[{index}] ({row_id}): decision_status must be confirmed or rejected")
        if values["decision_priority"] not in REQUIREMENT_PRIORITIES:
            problems.append(f"rows[{index}] ({row_id}): decision_priority must be must, should or could")
        if not values["reason"]:
            problems.append(f"rows[{index}] ({row_id}): reason is required")
        decisions.append({"id": row_id, **values})
    if problems:
        raise ContractError("Decision sheet rejected; nothing was written: " + "; ".join(problems))
    if not decisions:
        raise ContractError("Decision sheet has no filled rows; nothing to apply")

    entries = []
    for decision in decisions:
        entries.append(
            _apply_decision(
                payload,
                requirement_id=decision["id"],
                status=decision["decision_status"],
                priority=decision["decision_priority"],
                reason=decision["reason"],
                decided_by=decided_by,
                decided_at=decided_at,
            )
        )
    payload["updated_at"] = utc_now()
    issues = validate_requirements(payload)
    if issues:
        raise ContractError(f"Batch would make requirement register invalid: {issues}")
    write_json(requirements_path, payload)
    items = payload.get("requirements", [])
    return {
        "schema": "house-requirement-batch-decision-result-v1",
        "requirements_path": str(requirements_path),
        "sheet": str(sheet_path),
        "applied": len(entries),
        "skipped_rows": skipped,
        "decided_by": decided_by,
        "decided_at": decided_at,
        "decisions": [
            {"requirement_id": decision["id"], "status": decision["decision_status"],
             "priority": decision["decision_priority"], "entry_hash": entry["entry_hash"]}
            for decision, entry in zip(decisions, entries, strict=True)
        ],
        "status_counts": {
            status: sum(1 for item in items if item.get("status") == status) for status in sorted(REQUIREMENT_STATUSES)
        },
        "priority_counts": {
            priority: sum(1 for item in items if item.get("priority") == priority)
            for priority in sorted(REQUIREMENT_PRIORITIES)
        },
    }


def _legacy_brief_files(brief_dir: Path) -> Iterable[Path]:
    for building_id in ("A", "B", "C"):
        path = brief_dir / f"{building_id}.json"
        if path.exists():
            yield path


def migrate_legacy_briefs(
    *, brief_dir: Path = ROOT / "inputs/brief", output: Path = REQUIREMENTS_PATH
) -> dict[str, Any]:
    """Convert legacy area briefs into an explicitly unconfirmed requirement register."""

    brief_dir = brief_dir.resolve()
    output = output.resolve()
    requirements: list[dict[str, Any]] = []
    for path in _legacy_brief_files(brief_dir):
        brief = read_json(path)
        building_id = str(brief.get("building_id") or path.stem)
        for floor_index, floor in enumerate(brief.get("floors") or []):
            floor_id = str(floor.get("floor_id") or f"floor-{floor_index + 1}")
            for room_index, room in enumerate(floor.get("rooms") or []):
                local_id = str(room.get("id") or f"room-{room_index + 1}")
                requirement_id = f"{building_id}.{floor_id}.{local_id}"
                constraints = {
                    key: room[key]
                    for key in (
                        "target_sqm",
                        "min_sqm",
                        "band",
                        "light",
                        "private",
                        "door_clear_mm",
                        "door_swing",
                        "wheelchair_turn",
                        "access_from",
                        "counts_in_footprint",
                        "penthouse",
                        "penthouse_class",
                    )
                    if key in room
                }
                requirements.append(
                    {
                        "id": requirement_id,
                        "title": str(room.get("name") or local_id),
                        "category": str(room.get("kind") or "other"),
                        "applies_to": {"building_id": building_id, "floor_id": floor_id},
                        "status": "candidate",
                        "priority": "should",
                        "rationale": room.get("note") or "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
                        "constraints": constraints,
                        "verification": {
                            "method": "owner_confirmation_then_drawing_evidence",
                            "state": "pending_owner_confirmation",
                        },
                        "source": {
                            "type": "legacy_brief",
                            "path": relative_to_root(path),
                            "pointer": f"/floors/{floor_index}/rooms/{room_index}",
                        },
                        "decision_log": [],
                    }
                )
    payload = {
        "schema": "house-requirements-v2",
        "generated_at": utc_now(),
        "policy": {
            "default_status": "candidate",
            "hard_gate_status": "confirmed",
            "note": "舊版 AI 建議與 area brief 一律先視為待確認想法。",
        },
        "requirements": requirements,
    }
    issues = validate_requirements(payload)
    if issues:
        raise ContractError(f"Generated requirement register is invalid: {issues}")
    write_json(output, payload)
    return payload


def validate_intake(
    *,
    project_path: Path = PROJECT_PATH,
    requirements_path: Path = REQUIREMENTS_PATH,
    physical_items_path: Path = PHYSICAL_ITEMS_PATH,
    site_criteria_path: Path = SITE_CRITERIA_PATH,
) -> dict[str, Any]:
    # Imported here because house_design.sites reads validate_project from this
    # module; a top-level import either way would close the loop.
    from house_design.sites import validate_site_criteria

    project = read_json(project_path)
    requirements = read_json(requirements_path)
    physical_items = read_json(physical_items_path)
    project_issues = validate_project(project)
    physical_item_issues = validate_physical_items(physical_items)
    site_criteria = read_json(site_criteria_path) if site_criteria_path.is_file() else None
    site_criteria_issues = validate_site_criteria(site_criteria) if site_criteria is not None else []
    physical_item_ids = {
        str(item.get("id")) for item in physical_items.get("items", []) if isinstance(item, dict) and item.get("id")
    }
    requirement_issues = validate_requirements(requirements, physical_item_ids=physical_item_ids)
    candidates = sum(1 for item in requirements.get("requirements", []) if item.get("status") == "candidate")
    confirmed = sum(1 for item in requirements.get("requirements", []) if item.get("status") == "confirmed")
    relationships = sum(len(item.get("relationships") or []) for item in requirements.get("requirements", []))
    inventory = [item for item in physical_items.get("items", []) if isinstance(item, dict)]
    measured = sum(1 for item in inventory if item.get("measurements"))
    return {
        "schema": "house-intake-validation-v1",
        "generated_at": utc_now(),
        "valid": not project_issues
        and not requirement_issues
        and not physical_item_issues
        and not site_criteria_issues,
        "project_issues": project_issues,
        "requirement_issues": requirement_issues,
        "physical_item_issues": physical_item_issues,
        "site_criteria_issues": site_criteria_issues,
        "project_readiness": project_readiness(project),
        "requirements": {
            "total": len(requirements.get("requirements", [])),
            "candidate": candidates,
            "confirmed": confirmed,
            "relationships": relationships,
        },
        "physical_items": {
            "total": len(inventory),
            "measured": measured,
            "pending_measurement": len(inventory) - measured,
        },
        "site_criteria": _site_criteria_summary(site_criteria),
    }


def _site_criteria_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Report how much of the elimination register is usable, never why."""

    if payload is None:
        return {"provided": False, "total": 0, "with_threshold": 0, "hard_eliminate": 0}
    criteria = [item for item in payload.get("criteria") or [] if isinstance(item, dict)]
    return {
        "provided": True,
        "total": len(criteria),
        "with_threshold": sum(1 for item in criteria if (item.get("threshold") or {}).get("value") is not None),
        "hard_eliminate": sum(1 for item in criteria if item.get("kind") == "hard_eliminate"),
    }

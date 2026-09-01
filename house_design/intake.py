from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from house_design.contracts import (
    ContractError,
    REQUIREMENT_PRIORITIES,
    REQUIREMENT_STATUSES,
    ROOT,
    read_json,
    relative_to_root,
    require_choice,
    stable_hash,
    utc_now,
    write_json,
)


PROJECT_PATH = ROOT / "inputs/project.json"
REQUIREMENTS_PATH = ROOT / "inputs/requirements.json"

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


def _known(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, dict):
        if value.get("status") in {"unknown", "pending", "needs_confirmation"}:
            return False
        return any(_known(item) for key, item in value.items() if not key.startswith("_"))
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
            parcel_states.append({"parcel_id": parcel_id, "known": _known(value), "value": value})
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


def validate_requirements(payload: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if payload.get("schema") != "house-requirements-v2":
        issues.append({"field": "schema", "message": "schema must be house-requirements-v2"})
    items = payload.get("requirements")
    if not isinstance(items, list):
        return [*issues, {"field": "requirements", "message": "requirements must be an array"}]
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

    require_choice(status, {"confirmed", "rejected"}, "status")
    require_choice(priority, REQUIREMENT_PRIORITIES, "priority")
    reason = reason.strip()
    decided_by = decided_by.strip()
    decided_at = (decided_at or utc_now()).strip()
    if not requirement_id.strip() or not reason or not decided_by or not decided_at:
        raise ContractError("id, reason, decided_by and decided_at must be non-empty")
    payload = read_json(requirements_path)
    existing_issues = validate_requirements(payload)
    if existing_issues:
        raise ContractError(f"Cannot decide an invalid requirement register: {existing_issues}")
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
    *, project_path: Path = PROJECT_PATH, requirements_path: Path = REQUIREMENTS_PATH
) -> dict[str, Any]:
    project = read_json(project_path)
    requirements = read_json(requirements_path)
    project_issues = validate_project(project)
    requirement_issues = validate_requirements(requirements)
    candidates = sum(1 for item in requirements.get("requirements", []) if item.get("status") == "candidate")
    confirmed = sum(1 for item in requirements.get("requirements", []) if item.get("status") == "confirmed")
    return {
        "schema": "house-intake-validation-v1",
        "generated_at": utc_now(),
        "valid": not project_issues and not requirement_issues,
        "project_issues": project_issues,
        "requirement_issues": requirement_issues,
        "project_readiness": project_readiness(project),
        "requirements": {
            "total": len(requirements.get("requirements", [])),
            "candidate": candidates,
            "confirmed": confirmed,
        },
    }

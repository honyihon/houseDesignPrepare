from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from house_design.contracts import ContractError, ROOT, read_json, stable_hash, utc_now, write_json
from house_design.intake import validate_project


PREDESIGN_PATH = ROOT / "inputs/predesign.json"
PREDESIGN_RULES_PATH = ROOT / "rules/predesign_readiness_rules.json"
PREDESIGN_OUTPUT_ROOT = ROOT / "structured/predesign"
PRIVATE_BUDGET_PATH = ROOT / "inputs/private/budget.json"

PHASES = (
    "owner_brief",
    "finance",
    "site_search",
    "site_due_diligence",
    "design",
    "tender",
    "construction",
    "handover",
)
PREDESIGN_STATES = {"unknown", "in_progress", "verified", "not_applicable"}
SOURCE_TIERS = {"official", "professional", "experience", "owner_policy"}
STATUS_LABELS = {
    "pass": "通過",
    "fail": "失敗",
    "warning": "警告",
    "unknown": "未知",
    "not_applicable": "不適用",
    "professional_review": "專業確認",
}
BUDGET_FIELDS = (
    "land_and_acquisition",
    "professional_fees",
    "permits_and_taxes",
    "construction",
    "interior_and_fixed_furniture",
    "equipment_and_appliances",
    "financing_and_insurance",
    "contingency",
    "total_ceiling",
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_predesign(payload: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if payload.get("schema") != "house-predesign-v1":
        issues.append({"field": "schema", "message": "schema must be house-predesign-v1"})
    if not payload.get("project_id"):
        issues.append({"field": "project_id", "message": "project_id is required"})
    phase = str(payload.get("current_phase") or "")
    if phase not in PHASES:
        issues.append({"field": "current_phase", "message": f"current_phase must be one of: {', '.join(PHASES)}"})
    policy = payload.get("policy")
    if not isinstance(policy, dict):
        issues.append({"field": "policy", "message": "policy object is required"})
    else:
        required_policy = {
            "household_baseline": "all_age_accessible",
            "cost_strategy": "whole_life_cycle",
            "timeline_strategy": "phase_gates",
            "gate_policy": "blocking",
            "source_policy": "tiered_evidence",
            "budget_storage": "bands_in_git_exact_private",
        }
        for field, expected in required_policy.items():
            if policy.get(field) != expected:
                issues.append({"field": f"policy.{field}", "message": f"must be {expected}"})
    states = payload.get("states")
    if not isinstance(states, list):
        return [*issues, {"field": "states", "message": "states must be an array"}]
    seen: set[str] = set()
    for index, state in enumerate(states):
        if not isinstance(state, dict):
            issues.append({"field": f"states[{index}]", "message": "state must be an object"})
            continue
        rule_id = str(state.get("rule_id") or "")
        if not rule_id:
            issues.append({"field": f"states[{index}].rule_id", "message": "rule_id is required"})
        elif rule_id in seen:
            issues.append({"field": f"states[{index}].rule_id", "message": "rule_id must be unique"})
        seen.add(rule_id)
        status = str(state.get("status") or "")
        if status not in PREDESIGN_STATES:
            issues.append(
                {"field": f"states[{index}].status", "message": f"status must be one of: {', '.join(sorted(PREDESIGN_STATES))}"}
            )
        evidence = state.get("evidence") or []
        if not isinstance(evidence, list):
            issues.append({"field": f"states[{index}].evidence", "message": "evidence must be an array"})
        if status == "verified" and not evidence:
            issues.append({"field": f"states[{index}].evidence", "message": "verified state requires evidence"})
        if status == "not_applicable" and not str(state.get("note") or "").strip():
            issues.append({"field": f"states[{index}].note", "message": "not_applicable state requires a reason"})
    budget = payload.get("budget_policy")
    if not isinstance(budget, dict):
        issues.append({"field": "budget_policy", "message": "budget_policy object is required"})
    else:
        if budget.get("exact_amounts") != "private_gitignored_file":
            issues.append(
                {"field": "budget_policy.exact_amounts", "message": "exact amounts must use private_gitignored_file"}
            )
        for field in ("ceiling_status", "scope_status", "contingency_status"):
            if budget.get(field) not in {"unknown", "in_progress", "confirmed"}:
                issues.append(
                    {"field": f"budget_policy.{field}", "message": "must be unknown, in_progress or confirmed"}
                )
    return issues


def validate_rule_pack(payload: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if payload.get("schema") != "house-predesign-rule-pack-v1":
        issues.append({"field": "schema", "message": "schema must be house-predesign-rule-pack-v1"})
    sources = payload.get("sources")
    if not isinstance(sources, list):
        return [*issues, {"field": "sources", "message": "sources must be an array"}]
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            issues.append({"field": f"sources[{index}]", "message": "source must be an object"})
            continue
        source_id = str(source.get("source_id") or "")
        if not source_id or source_id in source_ids:
            issues.append({"field": f"sources[{index}].source_id", "message": "source_id is required and unique"})
        source_ids.add(source_id)
        if source.get("tier") not in SOURCE_TIERS:
            issues.append({"field": f"sources[{index}].tier", "message": "invalid source tier"})
        if source.get("tier") in {"official", "professional"} and not source.get("url"):
            issues.append({"field": f"sources[{index}].url", "message": "official/professional source requires URL"})
    rules = payload.get("rules")
    if not isinstance(rules, list):
        return [*issues, {"field": "rules", "message": "rules must be an array"}]
    rule_ids: set[str] = set()
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            issues.append({"field": f"rules[{index}]", "message": "rule must be an object"})
            continue
        rule_id = str(rule.get("rule_id") or "")
        if not rule_id or rule_id in rule_ids:
            issues.append({"field": f"rules[{index}].rule_id", "message": "rule_id is required and unique"})
        rule_ids.add(rule_id)
        if rule.get("phase") not in PHASES:
            issues.append({"field": f"rules[{index}].phase", "message": "invalid phase"})
        if rule.get("source_tier") not in SOURCE_TIERS:
            issues.append({"field": f"rules[{index}].source_tier", "message": "invalid source tier"})
        for source_id in rule.get("source_ids") or []:
            if source_id not in source_ids:
                issues.append(
                    {"field": f"rules[{index}].source_ids", "message": f"unknown source_id: {source_id}"}
                )
        for required in ("title", "domain", "responsible_role", "next_action"):
            if not rule.get(required):
                issues.append({"field": f"rules[{index}].{required}", "message": f"{required} is required"})
    return issues


def validate_private_budget(payload: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if payload.get("schema") != "house-budget-private-v1":
        issues.append({"field": "schema", "message": "schema must be house-budget-private-v1"})
    if payload.get("currency") != "TWD":
        issues.append({"field": "currency", "message": "currency must be TWD"})
    amounts = payload.get("amounts")
    if not isinstance(amounts, dict):
        return [*issues, {"field": "amounts", "message": "amounts object is required"}]
    for field in BUDGET_FIELDS:
        value = amounts.get(field)
        if value is not None and (not _is_number(value) or value < 0):
            issues.append({"field": f"amounts.{field}", "message": "amount must be null or a non-negative number"})
    values = [amounts.get(field) for field in BUDGET_FIELDS[:-1]]
    ceiling = amounts.get("total_ceiling")
    if _is_number(ceiling) and all(_is_number(value) for value in values):
        if sum(float(value) for value in values) > float(ceiling):
            issues.append({"field": "amounts.total_ceiling", "message": "category total exceeds total ceiling"})
    return issues


def validate_bundle(
    *,
    project: dict[str, Any],
    predesign: dict[str, Any],
    rules: dict[str, Any],
    private_budget: dict[str, Any] | None,
) -> dict[str, Any]:
    issues = {
        "project": validate_project(project),
        "predesign": validate_predesign(predesign),
        "rules": validate_rule_pack(rules),
        "private_budget": validate_private_budget(private_budget) if private_budget is not None else [],
    }
    if predesign.get("project_id") != project.get("project_id"):
        issues["predesign"].append({"field": "project_id", "message": "must match project.json"})
    project_phase = str(project.get("stage") or predesign.get("current_phase") or "")
    if project_phase != predesign.get("current_phase"):
        issues["predesign"].append({"field": "current_phase", "message": "must match project stage"})
    known_rule_ids = {str(item.get("rule_id")) for item in rules.get("rules") or [] if isinstance(item, dict)}
    rules_by_id = {
        str(item.get("rule_id")): item for item in rules.get("rules") or [] if isinstance(item, dict)
    }
    for index, state in enumerate(predesign.get("states") or []):
        if state.get("rule_id") not in known_rule_ids:
            issues["predesign"].append(
                {"field": f"states[{index}].rule_id", "message": "rule_id is not defined in rule pack"}
            )
            continue
        rule = rules_by_id[str(state["rule_id"])]
        if state.get("status") == "not_applicable" and not rule.get("allow_not_applicable", False):
            issues["predesign"].append(
                {"field": f"states[{index}].status", "message": "this rule cannot be marked not_applicable"}
            )
        if state.get("status") == "verified" and rule.get("source_tier") in {"official", "professional"}:
            evidence = state.get("evidence") or []
            professionally_verified = any(item.get("verified_by") and item.get("verified_at") for item in evidence)
            if not professionally_verified:
                issues["predesign"].append(
                    {
                        "field": f"states[{index}].evidence",
                        "message": "official/professional verification requires verified_by and verified_at",
                    }
                )
    valid = not any(values for values in issues.values())
    budget_amounts = (private_budget or {}).get("amounts") or {}
    return {
        "schema": "house-predesign-validation-v1",
        "generated_at": utc_now(),
        "valid": valid,
        "issues": issues,
        "private_budget": {
            "present": private_budget is not None,
            "valid": private_budget is not None and not issues["private_budget"],
            "populated_fields": sum(1 for field in BUDGET_FIELDS if _is_number(budget_amounts.get(field))),
            "total_fields": len(BUDGET_FIELDS),
        },
    }


def _finding_id(rule_id: str, status: str, message: str) -> str:
    return f"{rule_id}-{stable_hash({'rule_id': rule_id, 'status': status, 'message': message})[:8]}"


def build_predesign_report(
    *,
    project_path: Path = ROOT / "inputs/project.json",
    predesign_path: Path = PREDESIGN_PATH,
    rule_pack_path: Path = PREDESIGN_RULES_PATH,
    private_budget_path: Path | None = PRIVATE_BUDGET_PATH,
) -> dict[str, Any]:
    project = read_json(project_path)
    predesign = read_json(predesign_path)
    rule_pack = read_json(rule_pack_path)
    private_budget = read_json(private_budget_path) if private_budget_path and private_budget_path.exists() else None
    validation = validate_bundle(
        project=project, predesign=predesign, rules=rule_pack, private_budget=private_budget
    )
    if not validation["valid"]:
        raise ContractError(f"Invalid predesign inputs: {validation['issues']}")

    current_phase = str(predesign["current_phase"])
    current_index = PHASES.index(current_phase)
    states = {str(item["rule_id"]): item for item in predesign.get("states") or []}
    source_map = {str(item["source_id"]): item for item in rule_pack.get("sources") or []}
    findings: list[dict[str, Any]] = []

    for rule in rule_pack.get("rules") or []:
        rule_id = str(rule["rule_id"])
        phase = str(rule["phase"])
        due = PHASES.index(phase) <= current_index
        state = states.get(rule_id, {"status": "unknown", "evidence": []})
        state_status = str(state.get("status") or "unknown")

        if not due:
            status = "warning"
            message = "尚未進入此階段；現在先保留需求、介面與未來查驗責任，避免前一步封死後續選項。"
            severity = "planned"
        elif state_status == "verified":
            status = "pass"
            message = str(state.get("note") or "已有可追溯證據完成此項前期決策或查核。")
            severity = "advisory"
        elif state_status == "not_applicable":
            status = "not_applicable"
            message = str(state.get("note"))
            severity = "advisory"
        else:
            tier = str(rule.get("source_tier"))
            if not rule.get("blocking"):
                status = "warning"
            else:
                status = "professional_review" if tier in {"official", "professional"} else "unknown"
            message = str(rule.get("incomplete_message") or "尚未完成或缺少可追溯證據。")
            severity = "blocking" if rule.get("blocking") else "advisory"

        if rule_id in {"PD-BUDGET-CEILING", "PD-BUDGET-SCOPE-CONTINGENCY"} and due:
            budget_policy = predesign.get("budget_policy", {})
            if rule_id == "PD-BUDGET-CEILING":
                public_confirmed = budget_policy.get("ceiling_status") == "confirmed"
            else:
                public_confirmed = (
                    budget_policy.get("scope_status") == "confirmed"
                    and budget_policy.get("contingency_status") == "confirmed"
                )
            private_complete = validation["private_budget"]["populated_fields"] == validation["private_budget"]["total_fields"]
            if public_confirmed and private_complete:
                status = "pass"
                severity = "advisory"
                message = "私有預算表與公開完成狀態一致；精確金額未帶入報告。"
            else:
                status = "unknown"
                severity = "blocking"
                message = "預算政策或私有預算表尚未完整；報告只顯示完成狀態，不會輸出精確金額。"

        sources = [source_map[source_id] for source_id in rule.get("source_ids") or [] if source_id in source_map]
        evidence = list(state.get("evidence") or [])
        evidence.extend(
            {
                "kind": "research_source",
                "source_id": source["source_id"],
                "tier": source["tier"],
                "title": source["title"],
                "url": source.get("url"),
            }
            for source in sources
        )
        findings.append(
            {
                "finding_id": _finding_id(rule_id, status, message),
                "rule_id": rule_id,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "severity": severity,
                "domain": str(rule["domain"]),
                "title": str(rule["title"]),
                "message": message,
                "phase": phase,
                "gate_active": due,
                "blocking": bool(rule.get("blocking")),
                "applies_to": dict(rule.get("applies_to") or {}),
                "evidence": evidence,
                "source": sources[0] if sources else {},
                "responsible_role": str(rule["responsible_role"]),
                "next_action": str(rule["next_action"]),
            }
        )

    due_rules = 0
    completed_rules = 0
    by_phase = {phase: {"completed": 0, "total": 0} for phase in PHASES}
    for finding in findings:
        phase = str(finding["phase"])
        by_phase[phase]["total"] += 1
        if finding["status"] in {"pass", "not_applicable"}:
            by_phase[phase]["completed"] += 1
        if finding["gate_active"]:
            due_rules += 1
            if finding["status"] in {"pass", "not_applicable"}:
                completed_rules += 1

    order = {"fail": 0, "unknown": 1, "professional_review": 2, "warning": 3, "pass": 4, "not_applicable": 5}
    findings.sort(key=lambda item: (not item["gate_active"], order[item["status"]], PHASES.index(item["phase"]), item["rule_id"]))
    counts = Counter(item["status"] for item in findings)
    active_blockers = [
        item
        for item in findings
        if item["gate_active"] and item["blocking"] and item["status"] not in {"pass", "not_applicable"}
    ]
    report = {
        "schema": "house-predesign-report-v1",
        "generated_at": utc_now(),
        "project_id": project.get("project_id"),
        "current_phase": current_phase,
        "policy": predesign.get("policy"),
        "readiness": {
            "completed": completed_rules,
            "total": due_rules,
            "percent": round(completed_rules / due_rules * 100) if due_rules else 0,
            "by_phase": by_phase,
        },
        "status_counts": {status: counts.get(status, 0) for status in STATUS_LABELS},
        "gate": {
            "eligible_for_next_phase": not active_blockers,
            "active_blockers": len(active_blockers),
            "policy": "目前及先前階段的 blocking 項目必須 verified 或有理由地 not_applicable。",
        },
        "private_budget": validation["private_budget"],
        "findings": findings,
        "sources": rule_pack.get("sources") or [],
    }
    hash_payload = dict(report)
    hash_payload.pop("generated_at", None)
    report["report_hash"] = stable_hash(hash_payload)
    return report


def predesign_markdown(report: dict[str, Any]) -> str:
    gate = report["gate"]
    lines = [
        "# 自建住宅前期準備檢核報告",
        "",
        f"- 目前階段：`{report['current_phase']}`",
        f"- 到期項目完成度：**{report['readiness']['percent']}%**",
        f"- 目前阻擋項目：**{gate['active_blockers']}**",
        f"- 下一階段：**{'可進入' if gate['eligible_for_next_phase'] else '不可進入'}**",
        f"- Report hash：`{report['report_hash']}`",
        "- 精確預算不寫入本報告；只呈現私有預算表的存在與完整狀態。",
        "",
        "## 現在要處理",
        "",
    ]
    for finding in report["findings"]:
        if not finding["gate_active"]:
            continue
        lines.extend(
            [
                f"### [{finding['status_label']}] {finding['title']}",
                "",
                f"- 階段：`{finding['phase']}`",
                f"- 說明：{finding['message']}",
                f"- 負責角色：{finding['responsible_role']}",
                f"- 下一步：{finding['next_action']}",
                "",
            ]
        )
    lines.extend(["## 後續階段預留", ""])
    for finding in report["findings"]:
        if finding["gate_active"]:
            continue
        lines.append(f"- `{finding['phase']}` · {finding['title']} — {finding['next_action']}")
    lines.append("")
    return "\n".join(lines)


def sources_markdown(report: dict[str, Any]) -> str:
    labels = {"official": "官方", "professional": "專業指引", "experience": "經驗", "owner_policy": "屋主政策"}
    lines = [
        "# 前期準備研究來源",
        "",
        "法規結論只能由官方來源與負責專業人員確認；經驗來源只用來發現可能後悔的問題。",
        "",
    ]
    for source in report.get("sources") or []:
        url = source.get("url")
        title = f"[{source['title']}]({url})" if url else source["title"]
        lines.extend(
            [
                f"## {labels.get(source['tier'], source['tier'])} · {title}",
                "",
                f"- 機關／來源：{source.get('organization') or '專案決策'}",
                f"- 查證日期：{source.get('verified_at') or '待查證'}",
                f"- 使用限制：{source.get('scope_limit') or '須依實際基地與圖說再次確認。'}",
                "",
            ]
        )
    return "\n".join(lines)


def write_predesign_report(report: dict[str, Any], output_root: Path = PREDESIGN_OUTPUT_ROOT) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    write_json(output_root / "report.json", report)
    (output_root / "report.md").write_text(predesign_markdown(report), encoding="utf-8", newline="\n")
    (output_root / "sources.md").write_text(sources_markdown(report), encoding="utf-8", newline="\n")
    return output_root

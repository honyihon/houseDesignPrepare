"""Candidate-site screening: elimination criteria applied to candidate parcels.

The owner is still searching for land, so the first architect meeting is a
feasibility consultation rather than a layout review. That meeting needs two
things this module produces: the elimination lines written down as data, and a
side-by-side comparison that says which candidate is out, which is still in,
and exactly which document is missing before anyone can tell.

The screening rule is deliberately pessimistic. A criterion whose threshold the
owner has not set yet, or a candidate field nobody has confirmed, reads as
``unknown`` - never as a pass. A site can only be kept once every hard line and
every must-ask question has a real answer behind it.
"""

from __future__ import annotations

import html
import math
from datetime import date
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
from house_design.intake import PROJECT_PATH, is_known, validate_project
from house_design.rendering.naming import safe_slug

SITE_CRITERIA_SCHEMA = "house-site-criteria-v1"
SITE_CANDIDATE_SCHEMA = "house-site-candidate-v1"
SITE_COMPARE_SCHEMA = "house-site-compare-v1"
SITE_CRITERIA_PATH = ROOT / "inputs/site-criteria.json"
SITE_CANDIDATE_TEMPLATE = ROOT / "inputs/site-candidate.template.json"
PREDESIGN_OUTPUT_ROOT = ROOT / "structured/predesign"

CRITERION_KINDS = {
    "hard_eliminate": "硬淘汰",
    "must_ask": "必問",
    "preference": "偏好",
}
CRITERION_STATES = {"unknown", "set", "not_applicable"}
COMPARATORS = {">=", "<=", ">", "<", "=="}
CANDIDATE_STATUSES = {"screening", "due_diligence", "rejected", "selected"}

CELL_LABELS = {
    "pass": "符合",
    "eliminated": "不符合",
    "unknown": "未知",
    "not_applicable": "不適用",
}
VERDICT_LABELS = {
    "keep": "可續評估",
    "eliminated": "淘汰",
    "unknown": "資料不足，不得視為通過",
}

COMPARE_WARNING = (
    "未知永遠不是通過：任一硬淘汰條件缺資料時，該候選地的結論只能是「資料不足」，不得當成可行、合規或已通過初篩。"
)
NO_CRITERIA_WARNING = "尚未設定任何淘汰門檻：本表只能列出缺什麼資料，無法做出任何篩選結論。"
NO_CANDIDATE_WARNING = "尚未登錄任何候選土地：請先以 intake site-add 建立候選地，再逐格填入官方查得的事實。"
AUTHORITY_WARNING = (
    "本表是屋主與建築師共同約定的篩選條件，不是法規檢討；分區、建蔽率、容積率、退縮與建築線"
    "必須由高雄市執業建築師依個案正式認定。"
)


def _field_value(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in (path or "").split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _resolve(value: Any) -> Any:
    """Unwrap the ``{status, value, source}`` cells the candidate template uses."""

    if isinstance(value, dict):
        if not is_known(value):
            return None
        return _resolve(value.get("value"))
    return value if is_known(value) else None


def fact_evidence_issue(raw: Any) -> str | None:
    """Require a traceable, checked fact, not an owner's assertion of verification.

    References may point to private documents; contents are not copied here.
    This checks completeness, not authenticity or professional approval.
    """
    if not isinstance(raw, dict) or raw.get("status") != "verified":
        return "尚未查核；請保存 status=verified 的事實欄位與來源"
    source = raw.get("source")
    if not isinstance(source, dict) or not all(
        isinstance(source.get(key), str) and is_known(source[key]) and source[key].strip()
        for key in ("reference", "reviewer", "checked_at")
    ):
        return "缺可追溯文件 reference、查核人 reviewer 或查核日期 checked_at"
    try:
        date.fromisoformat(source["checked_at"])
    except ValueError:
        return "checked_at 須為有效的 YYYY-MM-DD 查核日期"
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def validate_site_criteria(payload: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if payload.get("schema") != SITE_CRITERIA_SCHEMA:
        return [{"field": "schema", "message": f"schema must be {SITE_CRITERIA_SCHEMA}"}]
    criteria = payload.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return [*issues, {"field": "criteria", "message": "at least one criterion is required"}]
    seen: set[str] = set()
    for index, item in enumerate(criteria):
        field = f"criteria[{index}]"
        if not isinstance(item, dict):
            issues.append({"field": field, "message": "criterion must be an object"})
            continue
        criterion_id = str(item.get("id") or "")
        if not criterion_id or criterion_id in seen:
            issues.append({"field": f"{field}.id", "message": "id is required and unique"})
        seen.add(criterion_id)
        if item.get("kind") not in CRITERION_KINDS:
            issues.append(
                {"field": f"{field}.kind", "message": f"kind must be one of: {', '.join(sorted(CRITERION_KINDS))}"}
            )
        if not str(item.get("label") or "").strip():
            issues.append({"field": f"{field}.label", "message": "label is required"})
        if not str(item.get("field") or "").strip():
            issues.append({"field": f"{field}.field", "message": "field path into the candidate site is required"})
        required = item.get("all_fields", [])
        if not isinstance(required, list) or any(not isinstance(path, str) or not path.strip() for path in required):
            issues.append({"field": f"{field}.all_fields", "message": "all_fields must contain non-empty field paths"})
        if "parcel_field" in item and (not isinstance(item["parcel_field"], str) or not item["parcel_field"].strip()):
            issues.append({"field": f"{field}.parcel_field", "message": "parcel_field must be a non-empty field path"})
        if not str(item.get("responsible_role") or "").strip():
            issues.append({"field": f"{field}.responsible_role", "message": "responsible_role is required"})
        if not str(item.get("evidence_required") or "").strip():
            issues.append({"field": f"{field}.evidence_required", "message": "evidence_required is required"})
        status = item.get("status")
        if status not in CRITERION_STATES:
            issues.append(
                {"field": f"{field}.status", "message": f"status must be one of: {', '.join(sorted(CRITERION_STATES))}"}
            )
        threshold = item.get("threshold")
        if not isinstance(threshold, dict):
            issues.append({"field": f"{field}.threshold", "message": "threshold object is required"})
            continue
        if threshold.get("comparator") not in COMPARATORS:
            issues.append(
                {
                    "field": f"{field}.threshold.comparator",
                    "message": f"comparator must be one of: {', '.join(sorted(COMPARATORS))}",
                }
            )
        # An unset threshold that claims to be set would silently pass every
        # candidate, which is the exact failure this register exists to stop.
        if threshold.get("value") is None and status == "set":
            issues.append(
                {
                    "field": f"{field}.status",
                    "message": "status cannot be set while threshold.value is null; use unknown",
                }
            )
    return issues


def validate_candidate_site(candidate: dict[str, Any], field: str = "candidate") -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if candidate.get("schema") != SITE_CANDIDATE_SCHEMA:
        issues.append({"field": f"{field}.schema", "message": f"schema must be {SITE_CANDIDATE_SCHEMA}"})
    if not str(candidate.get("candidate_id") or "").strip():
        issues.append({"field": f"{field}.candidate_id", "message": "candidate_id is required"})
    if not str(candidate.get("label") or "").strip():
        issues.append({"field": f"{field}.label", "message": "label is required"})
    if candidate.get("status") not in CANDIDATE_STATUSES:
        issues.append(
            {"field": f"{field}.status", "message": f"status must be one of: {', '.join(sorted(CANDIDATE_STATUSES))}"}
        )
    return issues


def add_candidate_site(
    *,
    candidate_id: str,
    label: str,
    project_path: Path = PROJECT_PATH,
    template_path: Path = SITE_CANDIDATE_TEMPLATE,
) -> dict[str, Any]:
    """Append one candidate site, every fact still unknown.

    The template is copied verbatim on purpose: an agent listing or a viewing
    impression is not a fact, so nothing arrives pre-filled. Facts are added
    later, one at a time, with a source beside them.
    """

    candidate_id = (candidate_id or "").strip()
    label = (label or "").strip()
    if not candidate_id:
        raise ContractError("candidate_id must be non-empty")
    if not label:
        raise ContractError("label must be non-empty")

    project = read_json(project_path)
    if project.get("schema") != "house-project-v3":
        raise ContractError("candidate sites are only stored in house-project-v3 projects")
    search = project.get("site_search")
    if not isinstance(search, dict):
        raise ContractError("project has no site_search block")
    candidates = search.get("candidate_sites")
    if not isinstance(candidates, list):
        raise ContractError("site_search.candidate_sites must be an array")
    if any(str(item.get("candidate_id")) == candidate_id for item in candidates if isinstance(item, dict)):
        raise ContractError(f"candidate_id already exists: {candidate_id}")

    candidate = read_json(template_path)
    candidate["candidate_id"] = candidate_id
    candidate["label"] = label
    candidate["status"] = "screening"
    candidate["added_at"] = utc_now()
    issues = validate_candidate_site(candidate)
    if issues:
        raise ContractError(f"Candidate template is invalid: {issues}")

    candidates.append(candidate)
    project_issues = validate_project(project)
    if project_issues:
        raise ContractError(f"Adding the candidate would invalidate the project: {project_issues}")
    write_json(project_path, project)
    return {
        "project": relative_to_root(project_path),
        "candidate_id": candidate_id,
        "label": label,
        "status": candidate["status"],
        "candidate_count": len(candidates),
        "note": "所有欄位維持 unknown；請逐項補上官方查得的事實與來源，不要把仲介說法寫成已確認。",
    }


def _evaluate(criterion: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    if criterion.get("status") == "not_applicable":
        return {"state": "not_applicable", "reason": "本案不適用", "observed": None}
    if criterion.get("parcel_field"):
        parcels = candidate.get("parcels")
        if not isinstance(parcels, list) or len(parcels) != 3 or any(not isinstance(p, dict) for p in parcels):
            return {
                "state": "unknown",
                "reason": "須提供 A／B／C 三筆基地資料，不得以合計面積或面寬替代",
                "observed": None,
            }
        if {p.get("building_id") for p in parcels} != {"A", "B", "C"} or len(
            {p.get("parcel_id") for p in parcels if p.get("parcel_id")}
        ) != 3:
            return {"state": "unknown", "reason": "三筆基地須有獨立 parcel_id 並各自對應 A／B／C", "observed": None}
        children = [
            {
                "field": f"parcels.{p['parcel_id']}.{criterion['parcel_field']}",
                **_evaluate(
                    {**criterion, "field": criterion["parcel_field"], "parcel_field": None, "all_fields": []}, p
                ),
            }
            for p in parcels
        ]
        return _aggregate(children)
    if criterion.get("all_fields"):
        children = [
            {"field": path, **_evaluate({**criterion, "field": path, "all_fields": []}, candidate)}
            for path in criterion["all_fields"]
        ]
        return _aggregate(children)
    threshold = criterion.get("threshold") or {}
    limit = threshold.get("value")
    comparator = threshold.get("comparator")
    unit = threshold.get("unit")
    raw = _field_value(candidate, str(criterion.get("field") or ""))
    resolved = _resolve(raw)

    if criterion.get("status") == "not_applicable":
        return {"state": "not_applicable", "reason": "本案不適用", "observed": None}
    if limit is None or criterion.get("status") != "set":
        return {"state": "unknown", "reason": "門檻尚未設定", "observed": resolved}
    if not is_known(raw) or resolved is None:
        return {"state": "unknown", "reason": "候選地尚未填入此項事實", "observed": None}
    evidence_issue = fact_evidence_issue(raw)
    if evidence_issue:
        return {"state": "unknown", "reason": evidence_issue, "observed": resolved}

    if comparator == "==":
        matched = str(resolved).strip() == str(limit).strip()
        return {
            "state": "pass" if matched else "eliminated",
            "reason": f"實際 {resolved}，要求 {limit}",
            "observed": resolved,
            "source": raw["source"],
        }

    observed = _number(resolved)
    wanted = _number(limit)
    if observed is None or wanted is None:
        return {
            "state": "unknown",
            "reason": f"值無法與門檻比較（實際 {resolved!r}，門檻 {limit!r}）",
            "observed": resolved,
        }
    comparisons = {
        ">=": observed >= wanted,
        "<=": observed <= wanted,
        ">": observed > wanted,
        "<": observed < wanted,
    }
    suffix = f" {unit}" if unit and unit not in {"qualitative"} else ""
    return {
        "state": "pass" if comparisons[comparator] else "eliminated",
        "reason": f"實際 {observed:g}{suffix}，要求 {comparator} {wanted:g}{suffix}",
        "observed": observed,
        "source": raw["source"],
    }


def _aggregate(children: list[dict[str, Any]]) -> dict[str, Any]:
    states = [child["state"] for child in children]
    state = "eliminated" if "eliminated" in states else "unknown" if not states or "unknown" in states else "pass"
    return {
        "state": state,
        "reason": "；".join(f"{c['field']}：{c['reason']}" for c in children),
        "observed": {c["field"]: c["observed"] for c in children},
        "components": children,
    }


def _verdict(cells: list[dict[str, Any]]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    blocking = [cell for cell in cells if cell["kind"] in {"hard_eliminate", "must_ask"}]
    failed = [cell for cell in blocking if cell["state"] == "eliminated"]
    if failed:
        reasons = [f"{cell['label']}：{cell['reason']}" for cell in failed]
        return "eliminated", reasons
    pending = [cell for cell in blocking if cell["state"] == "unknown"]
    if pending:
        reasons = [f"{cell['label']}：{cell['reason']}" for cell in pending]
        return "unknown", reasons
    if not blocking:
        return "unknown", ["沒有任何硬淘汰或必問條件可以判定"]
    return "keep", ["所有硬淘汰與必問條件都有證據支持"]


def build_site_comparison(
    *,
    project_path: Path = PROJECT_PATH,
    criteria_path: Path = SITE_CRITERIA_PATH,
) -> dict[str, Any]:
    project = read_json(project_path)
    project_issues = validate_project(project)
    if project_issues:
        raise ContractError(f"Cannot screen sites against an invalid project: {project_issues}")
    criteria_payload = read_json(criteria_path)
    criteria_issues = validate_site_criteria(criteria_payload)
    if criteria_issues:
        raise ContractError(f"Invalid site criteria register: {criteria_issues}")

    criteria = [item for item in criteria_payload.get("criteria", []) if isinstance(item, dict)]
    search = project.get("site_search") or {}
    candidates = [item for item in search.get("candidate_sites") or [] if isinstance(item, dict)]

    warnings = [COMPARE_WARNING, AUTHORITY_WARNING]
    if all(((item.get("threshold") or {}).get("value") is None) for item in criteria):
        warnings.insert(0, NO_CRITERIA_WARNING)
    if not candidates:
        warnings.insert(0, NO_CANDIDATE_WARNING)

    criteria_rows = [
        {
            "id": item.get("id"),
            "label": item.get("label"),
            "kind": item.get("kind"),
            "kind_label": CRITERION_KINDS.get(str(item.get("kind")), str(item.get("kind"))),
            "field": item.get("field"),
            "all_fields": item.get("all_fields", []),
            "parcel_field": item.get("parcel_field"),
            "threshold": item.get("threshold"),
            "threshold_set": (item.get("threshold") or {}).get("value") is not None,
            "status": item.get("status"),
            "rationale": item.get("rationale"),
            "evidence_required": item.get("evidence_required"),
            "responsible_role": item.get("responsible_role"),
            "note": item.get("note"),
        }
        for item in criteria
    ]

    results: list[dict[str, Any]] = []
    for candidate in candidates:
        cells: list[dict[str, Any]] = []
        for item in criteria:
            outcome = _evaluate(item, candidate)
            cells.append(
                {
                    "criterion_id": item.get("id"),
                    "label": item.get("label"),
                    "kind": item.get("kind"),
                    "kind_label": CRITERION_KINDS.get(str(item.get("kind")), str(item.get("kind"))),
                    "state": outcome["state"],
                    "state_label": CELL_LABELS[outcome["state"]],
                    "reason": outcome["reason"],
                    "observed": outcome["observed"],
                    "components": outcome.get("components", []),
                    "fact_sources": {c["field"]: c.get("source") for c in outcome.get("components", [])}
                    if outcome.get("components")
                    else {str(item.get("field")): outcome.get("source")},
                    "evidence_required": item.get("evidence_required"),
                    "responsible_role": item.get("responsible_role"),
                }
            )
        verdict, reasons = _verdict(cells)
        location = candidate.get("location") or {}
        results.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "label": candidate.get("label"),
                "status": candidate.get("status"),
                "district": location.get("district"),
                "land_section": location.get("land_section"),
                "land_numbers": location.get("land_numbers") or [],
                "verdict": verdict,
                "verdict_label": VERDICT_LABELS[verdict],
                "verdict_reasons": reasons,
                "cells": cells,
                "state_counts": {key: sum(1 for cell in cells if cell["state"] == key) for key in CELL_LABELS},
                "missing_evidence": [
                    {
                        "criterion_id": cell["criterion_id"],
                        "label": cell["label"],
                        "kind_label": cell["kind_label"],
                        "evidence_required": cell["evidence_required"],
                        "responsible_role": cell["responsible_role"],
                        "reason": cell["reason"],
                    }
                    for cell in cells
                    if cell["state"] == "unknown"
                ],
            }
        )

    unset = [row for row in criteria_rows if not row["threshold_set"]]
    report: dict[str, Any] = {
        "schema": SITE_COMPARE_SCHEMA,
        "generated_at": utc_now(),
        "project": {
            "project_id": project.get("project_id"),
            "name": project.get("name"),
            "stage": project.get("stage"),
            "selection_status": search.get("selection_status"),
        },
        "warnings": warnings,
        "policy": criteria_payload.get("policy") or {},
        "criteria": criteria_rows,
        "candidates": results,
        "summary": {
            "criteria_total": len(criteria_rows),
            "criteria_with_threshold": len(criteria_rows) - len(unset),
            "criteria_without_threshold": len(unset),
            "candidates_total": len(results),
            "verdict_counts": {key: sum(1 for item in results if item["verdict"] == key) for key in VERDICT_LABELS},
            "open_evidence_items": sum(len(item["missing_evidence"]) for item in results),
        },
        "next_actions": _next_actions(unset, results),
        "sources": [
            _source(project_path, "候選土地與專案階段"),
            _source(criteria_path, "選地淘汰條件"),
        ],
    }
    report["compare_hash"] = stable_hash({key: value for key, value in report.items() if key != "generated_at"})
    return report


def _next_actions(unset: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for row in unset:
        actions.append(
            {
                "kind": "threshold",
                "target": str(row["id"]),
                "action": f"與建築師談定「{row['label']}」的門檻值，填回 inputs/site-criteria.json",
                "responsible_role": str(row["responsible_role"]),
            }
        )
    seen: set[tuple[str, str]] = set()
    for item in results:
        for missing in item["missing_evidence"]:
            key = (str(item["candidate_id"]), str(missing["criterion_id"]))
            if key in seen:
                continue
            seen.add(key)
            actions.append(
                {
                    "kind": "evidence",
                    "target": f"{item['candidate_id']} / {missing['criterion_id']}",
                    "action": f"取得{missing['evidence_required']}，補上「{missing['label']}」",
                    "responsible_role": str(missing["responsible_role"]),
                }
            )
    return actions


def _source(path: Path, role: str) -> dict[str, Any]:
    exists = path.is_file()
    return {
        "path": relative_to_root(path),
        "role": role,
        "exists": exists,
        "sha256": sha256_file(path) if exists else None,
    }


def _cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "／").replace("\n", " ")


def site_comparison_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 候選土地淘汰比較表",
        "",
        f"- 專案：{report['project']['name']}（階段 `{report['project']['stage']}`）",
        f"- 產生時間：{report['generated_at']}",
        f"- 比較表雜湊：`{report['compare_hash']}`",
        "",
    ]
    lines.extend(f"> ⚠ {warning}" for warning in report["warnings"])
    lines.extend(
        [
            "",
            "## 一、結論摘要",
            "",
            f"- 候選土地 {summary['candidates_total']} 筆："
            f"淘汰 {summary['verdict_counts']['eliminated']}、"
            f"資料不足 {summary['verdict_counts']['unknown']}、"
            f"可續評估 {summary['verdict_counts']['keep']}",
            f"- 淘汰條件 {summary['criteria_total']} 條，其中 {summary['criteria_without_threshold']} 條門檻尚未設定",
            f"- 待補證據 {summary['open_evidence_items']} 項",
            "",
            "## 二、淘汰條件",
            "",
            "| id | 條件 | 類型 | 門檻 | 依據 | 需要的證據 | 負責角色 |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for row in report["criteria"]:
        threshold = row["threshold"] or {}
        value = threshold.get("value")
        text = (
            f"{threshold.get('comparator', '')} {value} {threshold.get('unit', '')}".strip()
            if value is not None
            else "**未設定**"
        )
        lines.append(
            f"| `{row['id']}` | {_cell(row['label'])} | {row['kind_label']} | {text} "
            f"| {_cell(row['rationale'])} | {_cell(row['evidence_required'])} | {_cell(row['responsible_role'])} |"
        )

    lines.extend(["", "## 三、候選地比較", ""])
    if not report["candidates"]:
        lines.extend(
            [
                "目前沒有登錄任何候選土地。建立方式：",
                "",
                "```bash",
                '.venv/bin/python -m house_design intake site-add --id SITE-001 --label "候選地名稱"',
                "```",
                "",
            ]
        )
    else:
        header = "| 條件 | " + " | ".join(_cell(item["label"]) for item in report["candidates"]) + " |"
        divider = "|---|" + "---|" * len(report["candidates"])
        lines.extend([header, divider])
        for index, row in enumerate(report["criteria"]):
            cells = [item["cells"][index] for item in report["candidates"]]
            rendered = " | ".join(f"{cell['state_label']}（{_cell(cell['reason'])}）" for cell in cells)
            lines.append(f"| {_cell(row['label'])}（{row['kind_label']}） | {rendered} |")
        verdicts = " | ".join(f"**{item['verdict_label']}**" for item in report["candidates"])
        lines.append(f"| **結論** | {verdicts} |")
        lines.append("")
        for item in report["candidates"]:
            lines.extend([f"### {item['label']}（`{item['candidate_id']}`）", ""])
            lines.append(f"- 結論：**{item['verdict_label']}**")
            lines.extend(f"- {reason}" for reason in item["verdict_reasons"])
            if item["missing_evidence"]:
                lines.extend(["", "待補證據：", ""])
                lines.extend(
                    f"- {missing['label']}：{missing['evidence_required']}（{missing['responsible_role']}）"
                    for missing in item["missing_evidence"]
                )
            lines.append("")

    lines.extend(["## 四、下一步", ""])
    if report["next_actions"]:
        lines.extend(
            [
                "| 類型 | 對象 | 要做的事 | 負責角色 |",
                "|---|---|---|---|",
            ]
        )
        for action in report["next_actions"]:
            kind = "設定門檻" if action["kind"] == "threshold" else "補證據"
            lines.append(
                f"| {kind} | `{_cell(action['target'])}` | {_cell(action['action'])} "
                f"| {_cell(action['responsible_role'])} |"
            )
    else:
        lines.append("沒有待辦項目。")

    lines.extend(["", "## 五、資料來源", "", "| 檔案 | 用途 | SHA-256 |", "|---|---|---|"])
    for source in report["sources"]:
        digest = f"`{source['sha256']}`" if source["sha256"] else "未提供"
        lines.append(f"| `{source['path']}` | {source['role']} | {digest} |")
    lines.append("")
    return "\n".join(lines)


COMPARE_CSS = (
    "body{font:16px/1.65 system-ui,sans-serif;color:#17212b;background:#fff;max-width:1100px;margin:32px auto;"
    "padding:0 20px;overflow-wrap:anywhere}h1,h2{line-height:1.25}h2{border-bottom:2px solid #d5dde5;padding-bottom:4px;margin-top:36px}"
    ".warn{border-left:5px solid #b45309;background:#fff7ed;padding:14px 16px;margin:8px 0}"
    "table{border-collapse:collapse;width:100%}th,td{border:1px solid #b8c2cc;padding:8px;text-align:left;"
    "vertical-align:top}code{background:#eef2f6;padding:2px 5px;overflow-wrap:anywhere}.table-wrap{overflow-x:auto}"
    ".meta{color:#475569}.badge{display:inline-block;border-radius:999px;padding:0 8px;font-size:13px;"
    "border:1px solid #94a3b8}.v-keep{background:#dcfce7;border-color:#15803d}.v-unknown{background:#fef9c3;"
    "border-color:#a16207}.v-eliminated{background:#fee2e2;border-color:#b91c1c}"
    ".c-pass{background:#dcfce7}.c-unknown{background:#fef9c3}.c-eliminated{background:#fee2e2}"
    ".c-not_applicable{background:#f1f5f9;color:#475569}footer{margin-top:40px;color:#475569;font-size:14px}"
    "@media print{body{margin:0;max-width:none}h2{break-after:avoid}}"
)


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def site_comparison_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    parts = [
        '<!doctype html>\n<html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>候選土地淘汰比較：{_e(report['project']['name'])}</title><style>{COMPARE_CSS}</style></head><body>",
        f"<h1>候選土地淘汰比較表<br>{_e(report['project']['name'])}</h1>",
        *[f'<p class="warn" role="note">⚠ {_e(warning)}</p>' for warning in report["warnings"]],
        f'<p class="meta">產生時間：{_e(report["generated_at"])}｜階段：<code>{_e(report["project"]["stage"])}</code>'
        f"｜比較表雜湊：<code>{_e(report['compare_hash'])}</code></p>",
        "<h2>一、結論摘要</h2><ul>",
        f"<li>候選土地 {summary['candidates_total']} 筆："
        f"淘汰 {summary['verdict_counts']['eliminated']}、"
        f"資料不足 {summary['verdict_counts']['unknown']}、"
        f"可續評估 {summary['verdict_counts']['keep']}</li>",
        f"<li>淘汰條件 {summary['criteria_total']} 條，其中 {summary['criteria_without_threshold']} 條門檻尚未設定</li>",
        f"<li>待補證據 {summary['open_evidence_items']} 項</li></ul>",
        '<h2>二、淘汰條件</h2><div class="table-wrap"><table><thead><tr><th>id</th><th>條件</th><th>類型</th>'
        "<th>門檻</th><th>依據</th><th>需要的證據</th><th>負責角色</th></tr></thead><tbody>",
    ]
    for row in report["criteria"]:
        threshold = row["threshold"] or {}
        value = threshold.get("value")
        text = (
            f"{threshold.get('comparator', '')} {value} {threshold.get('unit', '')}".strip()
            if value is not None
            else "<strong>未設定</strong>"
        )
        parts.append(
            f"<tr><td><code>{_e(row['id'])}</code></td><td>{_e(row['label'])}</td><td>{_e(row['kind_label'])}</td>"
            f"<td>{text if value is None else _e(text)}</td><td>{_e(row['rationale'])}</td>"
            f"<td>{_e(row['evidence_required'])}</td><td>{_e(row['responsible_role'])}</td></tr>"
        )
    parts.append("</tbody></table></div><h2>三、候選地比較</h2>")

    if not report["candidates"]:
        parts.append(
            "<p>目前沒有登錄任何候選土地。建立方式："
            "<code>python -m house_design intake site-add --id SITE-001 --label &quot;候選地名稱&quot;</code></p>"
        )
    else:
        parts.append('<div class="table-wrap"><table><thead><tr><th>條件</th>')
        parts.extend(f"<th>{_e(item['label'])}</th>" for item in report["candidates"])
        parts.append("</tr></thead><tbody>")
        for index, row in enumerate(report["criteria"]):
            parts.append(f'<tr><td>{_e(row["label"])}<br><span class="meta">{_e(row["kind_label"])}</span></td>')
            for item in report["candidates"]:
                cell = item["cells"][index]
                parts.append(
                    f'<td class="c-{_e(cell["state"])}">{_e(cell["state_label"])}'
                    f'<br><span class="meta">{_e(cell["reason"])}</span></td>'
                )
            parts.append("</tr>")
        parts.append("<tr><td><strong>結論</strong></td>")
        for item in report["candidates"]:
            parts.append(f'<td><span class="badge v-{_e(item["verdict"])}">{_e(item["verdict_label"])}</span></td>')
        parts.append("</tr></tbody></table></div>")
        for item in report["candidates"]:
            parts.append(
                f'<h3 id="site-{_e(safe_slug(str(item["candidate_id"])))}">{_e(item["label"])}'
                f"（<code>{_e(item['candidate_id'])}</code>）</h3><ul>"
            )
            parts.extend(f"<li>{_e(reason)}</li>" for reason in item["verdict_reasons"])
            parts.append("</ul>")
            if item["missing_evidence"]:
                parts.append("<p>待補證據：</p><ul>")
                parts.extend(
                    f"<li>{_e(missing['label'])}：{_e(missing['evidence_required'])}"
                    f"（{_e(missing['responsible_role'])}）</li>"
                    for missing in item["missing_evidence"]
                )
                parts.append("</ul>")

    parts.append("<h2>四、下一步</h2>")
    if report["next_actions"]:
        parts.append(
            '<div class="table-wrap"><table><thead><tr><th>類型</th><th>對象</th><th>要做的事</th>'
            "<th>負責角色</th></tr></thead><tbody>"
        )
        for action in report["next_actions"]:
            kind = "設定門檻" if action["kind"] == "threshold" else "補證據"
            parts.append(
                f"<tr><td>{_e(kind)}</td><td><code>{_e(action['target'])}</code></td>"
                f"<td>{_e(action['action'])}</td><td>{_e(action['responsible_role'])}</td></tr>"
            )
        parts.append("</tbody></table></div>")
    else:
        parts.append("<p>沒有待辦項目。</p>")

    parts.append(
        '<h2>五、資料來源</h2><div class="table-wrap"><table><thead><tr><th>檔案</th><th>用途</th>'
        "<th>SHA-256</th></tr></thead><tbody>"
    )
    for source in report["sources"]:
        digest = f"<code>{_e(source['sha256'])}</code>" if source["sha256"] else "未提供"
        parts.append(
            f"<tr><td><code>{_e(source['path'])}</code></td><td>{_e(source['role'])}</td><td>{digest}</td></tr>"
        )
    parts.append(
        f"</tbody></table></div><footer>比較表雜湊：<code>{_e(report['compare_hash'])}</code></footer></body></html>\n"
    )
    return "".join(parts)


def write_site_comparison(report: dict[str, Any], output_root: Path = PREDESIGN_OUTPUT_ROOT) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": output_root / "site-compare.json",
        "markdown": output_root / "site-compare.md",
        "html": output_root / "site-compare.html",
    }
    write_json(paths["json"], report)
    paths["markdown"].write_text(site_comparison_markdown(report), encoding="utf-8", newline="\n")
    paths["html"].write_text(site_comparison_html(report), encoding="utf-8", newline="\n")
    return paths

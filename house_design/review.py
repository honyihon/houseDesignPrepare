from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from typing import Any

from house_design.contracts import ContractError, REVIEW_STATUSES, ROOT, read_json, stable_hash, utc_now, write_json
from house_design.drawings import REVISION_ROOT, assess_model3d_readiness, compare_revisions, load_revision
from house_design.intake import (
    PROJECT_PATH,
    REQUIREMENTS_PATH,
    actual_parcels,
    project_readiness,
    validate_project,
    validate_requirements,
)
from house_design.predesign import (
    PREDESIGN_PATH,
    PREDESIGN_RULES_PATH,
    PRIVATE_BUDGET_PATH,
    build_predesign_report,
)


RULE_PACK_PATH = ROOT / "rules/kaohsiung_review_rules.json"
REVIEW_ROOT = ROOT / "structured/reviews"


STATUS_LABELS = {
    "pass": "通過",
    "fail": "失敗",
    "warning": "警告",
    "unknown": "未知",
    "not_applicable": "不適用",
    "professional_review": "專業確認",
}


def _finding(
    *,
    rule_id: str,
    status: str,
    domain: str,
    title: str,
    message: str,
    responsible_role: str,
    next_action: str,
    applies_to: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    source: dict[str, Any] | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    if status not in REVIEW_STATUSES:
        raise ContractError(f"invalid finding status: {status}")
    identifier_seed = {
        "rule_id": rule_id,
        "status": status,
        "applies_to": applies_to or {},
        "message": message,
    }
    return {
        "finding_id": f"{rule_id}-{stable_hash(identifier_seed)[:8]}",
        "rule_id": rule_id,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "severity": severity or ("error" if status == "fail" else "advisory"),
        "domain": domain,
        "title": title,
        "message": message,
        "applies_to": applies_to or {},
        "evidence": evidence or [],
        "source": source or {},
        "responsible_role": responsible_role,
        "next_action": next_action,
    }


def _project_findings(project: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for issue in validate_project(project):
        findings.append(
            _finding(
                rule_id="DATA-PROJECT-CONTRACT",
                status="fail",
                domain="data_governance",
                title="專案資料契約不完整",
                message=f"{issue['field']}: {issue['message']}",
                responsible_role="專案資料管理者",
                next_action="修正 inputs/project.json 後重跑 intake validate。",
                evidence=[{"kind": "json_field", "path": "inputs/project.json", "field": issue["field"]}],
                severity="blocking",
            )
        )
    for parcel in actual_parcels(project):
        parcel_id = str(parcel.get("id"))
        area = parcel.get("parcel_area_ping")
        findings.append(
            _finding(
                rule_id="SITE-PARCEL-AREA",
                status="pass" if isinstance(area, (int, float)) and area > 0 else "unknown",
                domain="site",
                title=f"{parcel_id} 基地面積",
                message=(
                    f"正式資料記錄此筆基地約 {area:.1f} 坪；此值只代表基地面積，不代表可建築面積。"
                    if isinstance(area, (int, float))
                    else "尚未提供基地面積。"
                ),
                responsible_role="屋主／建築師",
                next_action="取得地籍謄本或測量成果後，以實際平方公尺更新並保留來源。",
                applies_to={"parcel_id": parcel_id, "building_id": parcel_id},
                evidence=[{"kind": "selected_site_fact", "path": "inputs/project.json"}],
            )
        )
        coverage = parcel.get("building_coverage_ratio")
        if isinstance(coverage, (int, float)) and isinstance(parcel.get("parcel_area_sqm"), (int, float)):
            footprint = float(parcel["parcel_area_sqm"]) * float(coverage)
            status = "professional_review"
            message = f"依輸入建蔽率初算最大建築面積 {footprint:.2f} m²；仍須套用退縮、法定空地及基地形狀。"
        else:
            status = "unknown"
            message = "建蔽率尚未確認，不能由 32 坪基地直接推定首層可蓋 32 坪。"
        findings.append(
            _finding(
                rule_id="SITE-BUILDABLE-FOOTPRINT",
                status=status,
                domain="building_regulation",
                title=f"{parcel_id} 可建築面積",
                message=message,
                responsible_role="建築師",
                next_action="依地號、分區、道路與退縮條件完成書面法規預檢。",
                applies_to={"parcel_id": parcel_id, "building_id": parcel_id},
                evidence=[{"kind": "json_field", "path": "inputs/project.json", "field": "building_coverage_ratio"}],
                source={"rule_pack": "kaohsiung-house-review-v1"},
            )
        )
    return findings


def _readiness_findings(project: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for fact in project_readiness(project)["facts"]:
        if fact["known"]:
            continue
        missing = [str(item["parcel_id"]) for item in fact["parcels"] if not item["known"]]
        is_selection = fact["key"] == "site_selection"
        results.append(
            _finding(
                rule_id=f"SITE-READINESS-{fact['key'].upper()}",
                status="unknown",
                domain="site",
                title=f"{fact['label']}尚未完成",
                message=(
                    "土地尚未選定；三筆相鄰、每筆約 32 坪目前只是選地目標。"
                    if is_selection
                    else f"缺少基地：{', '.join(missing)}。未知資料不得顯示為法規通過。"
                ),
                responsible_role="建築師／屋主",
                next_action=(
                    "先以候選土地評分與建築師書面初篩選地，再建立正式 selected_site。"
                    if is_selection
                    else f"取得並記錄三筆基地的{fact['label']}、來源文件與確認日期。"
                ),
                applies_to={"parcel_ids": missing},
                evidence=[{"kind": "json_field", "path": "inputs/project.json", "field": fact["key"]}],
            )
        )
    return results


def _requirement_findings(requirements: dict[str, Any], model: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    contract_issues = validate_requirements(requirements)
    for issue in contract_issues:
        findings.append(
            _finding(
                rule_id="DATA-REQUIREMENT-CONTRACT",
                status="fail",
                domain="data_governance",
                title="需求資料契約不完整",
                message=f"{issue['field']}: {issue['message']}",
                responsible_role="需求管理者",
                next_action="修正 requirements.json 後再執行檢核。",
                evidence=[{"kind": "json_field", "path": "inputs/requirements.json", "field": issue["field"]}],
                severity="blocking",
            )
        )
    items = requirements.get("requirements", [])
    candidates = [item for item in items if item.get("status") == "candidate"]
    if candidates:
        findings.append(
            _finding(
                rule_id="REQ-OWNER-CONFIRMATION",
                status="unknown",
                domain="requirements",
                title=f"{len(candidates)} 項既有想法尚待屋主確認",
                message="舊版 AI 建議與 area brief 不會自動成為硬需求。",
                responsible_role="屋主",
                next_action="逐項標記 confirmed、rejected，並將 confirmed 項目設定 must／should／could。",
                evidence=[{"kind": "requirement_register", "path": "inputs/requirements.json", "count": len(candidates)}],
            )
        )
    confirmed = [item for item in items if item.get("status") == "confirmed"]
    spaces = {str(item.get("requirement_id")): item for item in model.get("entities", {}).get("spaces", []) if item.get("requirement_id")}
    doors = model.get("entities", {}).get("doors", [])
    for requirement in confirmed:
        requirement_id = str(requirement["id"])
        space = spaces.get(requirement_id)
        applies_to = dict(requirement.get("applies_to") or {})
        applies_to["requirement_id"] = requirement_id
        if space is None:
            findings.append(
                _finding(
                    rule_id="REQ-DRAWING-BINDING",
                    status="unknown",
                    domain="requirements",
                    title=f"圖面尚未對應需求：{requirement['title']}",
                    message="沒有找到帶有相同 requirement_id 的圖面空間，不能判斷是否滿足。",
                    responsible_role="建築師／圖面資料管理者",
                    next_action="在 IFC 空間或 DXF layer mapping 中綁定 requirement_id。",
                    applies_to=applies_to,
                    evidence=[{"kind": "requirement", "requirement_id": requirement_id}],
                )
            )
            continue
        constraints = requirement.get("constraints") or {}
        minimum = constraints.get("min_sqm")
        actual_area = space.get("area_sqm")
        if isinstance(minimum, (int, float)):
            if not isinstance(actual_area, (int, float)):
                status = "unknown"
                message = "圖面空間缺少可追溯面積。"
            elif actual_area + 1e-6 < minimum:
                status = "fail" if requirement.get("priority") == "must" else "warning"
                message = f"圖面 {actual_area:.2f} m²，小於確認下限 {minimum:.2f} m²。"
            else:
                status = "pass"
                message = f"圖面 {actual_area:.2f} m²，達到確認下限 {minimum:.2f} m²。"
            findings.append(
                _finding(
                    rule_id="REQ-MIN-AREA",
                    status=status,
                    domain="space_program",
                    title=f"{requirement['title']}面積",
                    message=message,
                    responsible_role="建築師／屋主",
                    next_action="在家具與結構配置完成後再次確認淨使用面積。",
                    applies_to=applies_to,
                    evidence=[{"kind": "normalized_space", "entity_id": space.get("id"), "area_sqm": actual_area}],
                )
            )
        if constraints.get("wheelchair_turn"):
            width, depth = space.get("width_mm"), space.get("depth_mm")
            if not isinstance(width, (int, float)) or not isinstance(depth, (int, float)):
                status, message = "unknown", "圖面未提供可驗證淨寬、淨深，家具後迴轉圈仍未知。"
            elif min(width, depth) < 1500:
                status, message = "fail", f"空間短邊 {min(width, depth):.0f} mm，小於 1500 mm 迴轉圈。"
            else:
                status, message = "professional_review", "空房淨尺寸可容納 1500 mm 圈，但仍須放入床、櫃體與衛浴設備複核。"
            findings.append(
                _finding(
                    rule_id="ACC-WHEELCHAIR-TURN",
                    status=status,
                    domain="accessibility",
                    title=f"{requirement['title']}輪椅迴轉",
                    message=message,
                    responsible_role="建築師／無障礙顧問",
                    next_action="在正式家具與設備配置圖上標出直徑 1500 mm 淨空圓。",
                    applies_to=applies_to,
                    evidence=[{"kind": "normalized_space", "entity_id": space.get("id"), "width_mm": width, "depth_mm": depth}],
                )
            )
        minimum_door = constraints.get("door_clear_mm")
        if isinstance(minimum_door, (int, float)):
            local_id = requirement_id.rsplit(".", 1)[-1]
            related = [
                door
                for door in doors
                if door.get("requirement_id") == requirement_id or door.get("to") in {local_id, requirement_id, space.get("source_id")}
            ]
            widths = [float(item["clear_width_mm"]) for item in related if isinstance(item.get("clear_width_mm"), (int, float))]
            if not widths:
                status, message = "unknown", "找不到綁定此空間的門淨寬資料。"
            elif max(widths) < minimum_door:
                status, message = "fail", f"最大可追溯門淨寬 {max(widths):.0f} mm，小於確認值 {minimum_door:.0f} mm。"
            else:
                status, message = "pass", f"可追溯門淨寬 {max(widths):.0f} mm，達到確認值 {minimum_door:.0f} mm。"
            findings.append(
                _finding(
                    rule_id="ACC-DOOR-CLEAR",
                    status=status,
                    domain="accessibility",
                    title=f"{requirement['title']}門淨寬",
                    message=message,
                    responsible_role="建築師",
                    next_action="在門窗表與平面圖交叉確認完成面後淨寬。",
                    applies_to=applies_to,
                    evidence=[{"kind": "normalized_door", "entity_ids": [item.get("id") for item in related]}],
                )
            )
    return findings


def _import_findings(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    revision_id = str(manifest.get("revision_id"))
    status = manifest.get("status")
    if status == "legacy_assumption":
        findings.append(
            _finding(
                rule_id="DRAWING-LEGACY-ASSUMPTION",
                status="fail",
                domain="data_governance",
                title="舊版 32 坪量體不可作為現行基準",
                message="此版將 32 坪選地目標當成每層建築面積；目前土地尚未選定，不能推定任何可建量體。",
                responsible_role="專案資料管理者",
                next_action="收到建築師 PDF＋IFC／DXF 後建立新的不可變 revision。",
                applies_to={"revision_id": revision_id},
                evidence=[{"kind": "revision_manifest", "revision_id": revision_id}],
                severity="blocking",
            )
        )
    elif status in {"needs_mapping", "partial"}:
        findings.append(
            _finding(
                rule_id="DRAWING-SEMANTIC-MAPPING",
                status="unknown",
                domain="drawing_import",
                title="圖面語意對應尚未完成",
                message="原始檔已保存，但樓層、房間、門窗或單位尚未完整對應。",
                responsible_role="圖面資料管理者／建築師",
                next_action="補 mapping JSON 或請設計方輸出含 IfcSpace 的 IFC。",
                applies_to={"revision_id": revision_id},
                evidence=[{"kind": "revision_manifest", "revision_id": revision_id}],
            )
        )
    for issue in manifest.get("issues") or []:
        code = str(issue.get("code") or "DRAWING-IMPORT")
        if code == "LEGACY_FOOTPRINT_ASSUMPTION":
            continue
        severity = issue.get("severity")
        result_status = "fail" if severity == "blocking" and "PARSE_ERROR" in code else "unknown"
        findings.append(
            _finding(
                rule_id=code,
                status=result_status,
                domain="drawing_import",
                title="圖面匯入需要處理",
                message=str(issue.get("message") or code),
                responsible_role="圖面資料管理者",
                next_action="依匯入訊息補依賴、單位或圖層對應後建立新 revision。",
                applies_to={"revision_id": revision_id},
                evidence=[{"kind": "revision_import_issue", "details": issue.get("details")}],
            )
        )
    return findings


def _rule_pack_findings(rule_pack: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rule in rule_pack.get("rules") or []:
        if rule.get("domain") not in {"building_regulation", "accessibility", "fire", "structural", "mep"}:
            continue
        source = rule.get("source") or {}
        release_eligible = bool(rule.get("release_eligible"))
        has_citation = all(source.get(key) for key in ("title", "article", "url", "verified_at"))
        if not release_eligible or not has_citation:
            findings.append(
                _finding(
                    rule_id=f"RULE-SOURCE-{rule.get('rule_id')}",
                    status="professional_review",
                    domain="rule_governance",
                    title=f"規則尚未取得專業法源確認：{rule.get('title')}",
                    message="此規則不會產生法規通過結論，直到精確條文、版本、適用條件及查證人完成。",
                    responsible_role=str(rule.get("verification_owner") or "建築師"),
                    next_action="由負責專業人員確認法源與基地適用性，再將 release_eligible 設為 true。",
                    source=source,
                    evidence=[{"kind": "rule_pack", "path": "rules/kaohsiung_review_rules.json"}],
                )
            )
    return findings


def _coordination_findings(project: dict[str, Any]) -> list[dict[str, Any]]:
    values = []
    for index, title in enumerate(project.get("compound", {}).get("shared_items_to_confirm", []), start=1):
        values.append(
            _finding(
                rule_id=f"COMPOUND-COORD-{index:02d}",
                status="professional_review",
                domain="compound_coordination",
                title=title,
                message="三筆基地分開檢核後，仍需以整體配置確認跨基地介面與權責。",
                responsible_role="建築師／相關技師／屋主",
                next_action="在總配置圖、設備系統圖與產權管理約定上共同確認。",
                applies_to={"parcel_ids": ["A", "B", "C"]},
                evidence=[{"kind": "project_policy", "path": "inputs/project.json"}],
            )
        )
    return values


def _report_hash_payload(report: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(report)
    value.pop("generated_at", None)
    value.pop("report_hash", None)
    value.pop("signoff", None)
    return value


def validate_signoff(report: dict[str, Any], signoff: dict[str, Any] | None) -> dict[str, Any]:
    if not signoff:
        return {"valid": False, "reason": "missing", "status": "professional_review"}
    allowed = {"approved", "pass", "approved_with_conditions"}
    identity = str(signoff.get("reviewer_name") or "").strip().lower()
    invalid_identity = not identity or any(token in identity for token in ("claude", "chatgpt", "codex", "ai assistant"))
    valid = (
        signoff.get("decision") in allowed
        and signoff.get("reviewer_kind") == "human"
        and bool(signoff.get("reviewer_role"))
        and bool(signoff.get("reviewer_date"))
        and not invalid_identity
        and signoff.get("related_report_hash") == report.get("report_hash")
        and signoff.get("revision_id") == report.get("revision", {}).get("revision_id")
    )
    return {
        "valid": valid,
        "reason": "valid" if valid else "identity_revision_or_hash_mismatch",
        "status": "pass" if valid else "professional_review",
        "reviewer_role": signoff.get("reviewer_role"),
        "decision": signoff.get("decision"),
    }


def build_review(
    *,
    revision_id: str,
    project_path: Path = PROJECT_PATH,
    requirements_path: Path = REQUIREMENTS_PATH,
    rule_pack_path: Path = RULE_PACK_PATH,
    predesign_path: Path | None = None,
    predesign_rule_pack_path: Path = PREDESIGN_RULES_PATH,
    private_budget_path: Path | None = PRIVATE_BUDGET_PATH,
    revision_root: Path = REVISION_ROOT,
    previous_revision: str | None = None,
    signoff_path: Path | None = None,
) -> dict[str, Any]:
    project = read_json(project_path)
    requirements = read_json(requirements_path)
    rule_pack = read_json(rule_pack_path)
    manifest, model = load_revision(revision_id, revision_root)
    model3d_readiness = assess_model3d_readiness(manifest, model)
    if predesign_path is None and project_path.resolve() == PROJECT_PATH.resolve():
        predesign_path = PREDESIGN_PATH
    if predesign_path is not None:
        predesign_report = build_predesign_report(
            project_path=project_path,
            predesign_path=predesign_path,
            rule_pack_path=predesign_rule_pack_path,
            private_budget_path=private_budget_path,
        )
        active_predesign_findings = [item for item in predesign_report["findings"] if item["gate_active"]]
        predesign_summary = {
            "current_phase": predesign_report["current_phase"],
            "readiness": predesign_report["readiness"],
            "gate": predesign_report["gate"],
            "private_budget": predesign_report["private_budget"],
            "report_hash": predesign_report["report_hash"],
        }
    else:
        active_predesign_findings = []
        predesign_summary = None
    findings = [
        *active_predesign_findings,
        *_project_findings(project),
        *_readiness_findings(project),
        *_import_findings(manifest),
        *_requirement_findings(requirements, model),
        *_rule_pack_findings(rule_pack),
        *_coordination_findings(project),
    ]
    order = {"fail": 0, "warning": 1, "unknown": 2, "professional_review": 3, "pass": 4, "not_applicable": 5}
    findings.sort(key=lambda item: (order[item["status"]], item["domain"], item["rule_id"], item["finding_id"]))
    counts = Counter(item["status"] for item in findings)
    comparison = None
    if previous_revision:
        comparison = compare_revisions(
            before_revision=previous_revision, after_revision=revision_id, root=revision_root
        )
    report: dict[str, Any] = {
        "schema": "house-review-report-v1",
        "generated_at": utc_now(),
        "project": {
            "project_id": project.get("project_id"),
            "name": project.get("name"),
            "jurisdiction": project.get("jurisdiction"),
            "stage": project.get("stage"),
            "parcel_relationship": project.get("parcel_relationship")
            or (project.get("site_search") or {}).get("target_scenario", {}).get("parcel_relationship"),
        },
        "revision": {
            "revision_id": revision_id,
            "label": manifest.get("label"),
            "status": manifest.get("status"),
            "content_hash": manifest.get("content_hash"),
        },
        "readiness": project_readiness(project),
        "predesign": predesign_summary,
        "requirements_summary": {
            "total": len(requirements.get("requirements", [])),
            "candidate": sum(1 for item in requirements.get("requirements", []) if item.get("status") == "candidate"),
            "confirmed": sum(1 for item in requirements.get("requirements", []) if item.get("status") == "confirmed"),
            "rejected": sum(1 for item in requirements.get("requirements", []) if item.get("status") == "rejected"),
        },
        "model_summary": {key: len(value) for key, value in model.get("entities", {}).items()},
        "model3d_readiness": model3d_readiness,
        "status_counts": {status: counts.get(status, 0) for status in REVIEW_STATUSES},
        "release": {
            "eligible": counts.get("fail", 0) == 0 and counts.get("unknown", 0) == 0 and counts.get("professional_review", 0) == 0,
            "policy": "fail、unknown 或 professional_review 任一存在即不得宣稱整體合規。",
        },
        "findings": findings,
        "comparison": comparison,
        "model": model,
    }
    report["report_hash"] = stable_hash(_report_hash_payload(report))
    signoff = read_json(signoff_path) if signoff_path and signoff_path.exists() else None
    report["signoff"] = validate_signoff(report, signoff)
    report["release"]["eligible"] = bool(report["release"]["eligible"] and report["signoff"]["valid"])
    return report


def review_markdown(report: dict[str, Any]) -> str:
    revision = report["revision"]
    counts = report["status_counts"]
    model3d = report.get("model3d_readiness") or {}
    model3d_counts = model3d.get("counts") or {}
    lines = [
        f"# 住宅設計檢核報告 · {revision['revision_id']} {revision.get('label') or ''}",
        "",
        f"- Report hash: `{report['report_hash']}`",
        f"- 基地資料完成度：**{report['readiness']['percent']}%**",
        f"- 前期到期項目完成度：**{(report.get('predesign') or {}).get('readiness', {}).get('percent', 0)}%**",
        f"- 前期硬阻擋：**{(report.get('predesign') or {}).get('gate', {}).get('active_blockers', 0)} 項**",
        f"- 現行 revision 3D：**{'可進入產圖' if model3d.get('eligible') else '已阻擋'}**"
        f"（可渲染權威空間 {model3d_counts.get('authoritative_renderable_spaces', 0)}"
        f"／{model3d_counts.get('total_spaces', 0)}）",
        f"- 需求：{report['requirements_summary']['confirmed']} 已確認／{report['requirements_summary']['candidate']} 待確認",
        f"- 結論：**{'可進入專業放行' if report['release']['eligible'] else '不可宣稱整體合規'}**",
        "",
        "| 狀態 | 數量 |",
        "|---|---:|",
    ]
    for status in ("fail", "warning", "unknown", "professional_review", "pass", "not_applicable"):
        lines.append(f"| {STATUS_LABELS[status]} | {counts.get(status, 0)} |")
    lines.extend(
        [
            "",
            "## 現行 revision 3D",
            "",
            f"- 狀態：**{'ready' if model3d.get('eligible') else 'blocked'}**",
            f"- 來源類型：{', '.join(model3d.get('source_kinds') or []) or '無'}",
            f"- 座標狀態：`{(model3d.get('coordinate_system') or {}).get('status', 'unknown')}`",
            f"- 空間：{model3d_counts.get('authoritative_renderable_spaces', 0)} 個具備權威且可渲染幾何"
            f"／共 {model3d_counts.get('total_spaces', 0)} 個",
            f"- 樓層：{model3d_counts.get('elevated_storeys', 0)} 個有標高"
            f"／共 {model3d_counts.get('total_storeys', 0)} 個",
            f"- 判定原則：{model3d.get('policy') or '未提供'}",
            "",
        ]
    )
    blockers = model3d.get("blockers") or []
    if blockers:
        lines.extend(["### 阻擋原因與下一步", ""])
        for blocker in blockers:
            lines.extend(
                [
                    f"- `{blocker.get('code', 'UNKNOWN')}`：{blocker.get('message', '')}",
                    f"  - 下一步：{blocker.get('next_action', '')}",
                ]
            )
        lines.append("")
    else:
        lines.extend(["目前沒有 3D readiness 阻擋；此判定只代表輸入可產圖，不等同設計合規。", ""])
    lines.extend(["## 檢核事項", ""])
    for finding in report["findings"]:
        applies = finding.get("applies_to") or {}
        location = "/".join(
            str(applies[key])
            for key in ("building_id", "floor_id")
            if applies.get(key)
        )
        lines.extend(
            [
                f"### [{finding['status_label']}] {finding['title']}",
                "",
                f"- 編號：`{finding['finding_id']}`" + (f" · 位置：{location}" if location else ""),
                f"- 說明：{finding['message']}",
                f"- 負責角色：{finding['responsible_role']}",
                f"- 下一步：{finding['next_action']}",
                "",
            ]
        )
    return "\n".join(lines)


def write_review(
    report: dict[str, Any], *, output_root: Path = REVIEW_ROOT
) -> Path:
    revision_id = str(report["revision"]["revision_id"])
    directory = output_root / revision_id
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "report.json", report)
    (directory / "report.md").write_text(review_markdown(report), encoding="utf-8", newline="\n")
    return directory

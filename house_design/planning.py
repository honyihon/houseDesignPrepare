"""Public, phase-aware scenario decisions. Tracking is never proof of compliance."""

from __future__ import annotations

import copy
import json
import math
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from house_design.contracts import ROOT, ContractError, read_json, stable_hash, utc_now, write_json
from house_design.predesign import PHASES

REGISTER_PATH = ROOT / "inputs/planning-register.json"
RULES_PATH = ROOT / "rules/predesign_readiness_rules.json"
TOPICS = {
    "household": "家庭與未來變化",
    "accessibility": "全齡與緊急救援",
    "parking": "車庫與出入口",
    "ritual": "B 棟祭祀運作",
    "storage": "武轎與收納",
    "routines": "家務與寵物",
    "structure": "結構與垂直核心",
    "comfort": "高雄熱濕與舒適",
    "waterproof": "防水與極端天氣",
    "shared": "三棟共同介面",
    "outage": "設備與故障備援",
    "delivery": "發包施工與交屋",
}
LABELS = {
    "unknown": "待確認",
    "in_progress": "進行中",
    "verified": "已驗證",
    "not_applicable": "不適用",
    "needs_review": "待複核",
    "professional_review": "待專業確認",
}
GOOD = {"verified", "not_applicable"}
WARNING = "已追蹤不等於已驗證；未檢查不等於通過。本表不是法規簽證、施工授權或風水保證。"
CONFLICT_POLICY = [
    "依法適用的法規／安全要求與已確認全齡基準先守住，適用性由專業確認。",
    "土地、結構、樓梯／升降設備、管道、防水及跨棟介面先決定。",
    "風水與配置衝突列替代、空間／成本／維護代價，屋主確認，不自動取捨。",
    "可分期的裝飾及設備晚決定；容量、空管與結構預留提前討論。",
]


def _proof(value: Any) -> bool:
    complete = isinstance(value, dict) and all(
        isinstance(value.get(k), str) and value[k].strip() for k in ("verified_by", "verified_at", "reference")
    )
    if not complete or any(
        value[k].strip().lower() in {"__fill__", "unknown", "待確認", "待填", "ai", "chatgpt", "codex", "claude"}
        for k in ("verified_by", "verified_at", "reference")
    ):
        return False
    try:
        datetime.fromisoformat(value["verified_at"].replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_register(register: dict[str, Any]) -> None:
    if register.get("schema") != "house-planning-register-v1" or not register.get("project_id"):
        raise ContractError("Expected house-planning-register-v1 and project_id")
    if not isinstance(register.get("items"), list):
        raise ContractError("planning.items must be an array")
    ids = set()
    for item in register["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or item["id"] in ids:
            raise ContractError("Planning item ids must be nonempty and unique")
        ids.add(item["id"])
        for key in ("title", "scenario", "question", "recommendation"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ContractError(f"{item['id']}: missing {key}")
        for key in ("topic", "due_phase", "status", "basis", "urgency"):
            if not isinstance(item.get(key), str):
                raise ContractError(f"{item['id']}: {key} must be a string")
        if item.get("physical_item_id") is not None and not isinstance(item["physical_item_id"], str):
            raise ContractError(f"{item['id']}: physical_item_id must be an id string")
        if item.get("requires_transport_measurement") is not None and not isinstance(
            item["requires_transport_measurement"], bool
        ):
            raise ContractError(f"{item['id']}: requires_transport_measurement must be boolean")
        if item.get("topic") not in TOPICS or item.get("due_phase") not in PHASES:
            raise ContractError(f"{item['id']}: invalid topic/phase")
        if item.get("status") not in LABELS or item.get("status") == "needs_review":
            raise ContractError(f"{item['id']}: invalid stored status (needs_review is computed)")
        if item.get("basis") not in {
            "proposal",
            "owner_preference",
            "verified_fact",
            "estimate",
            "professional_required",
        }:
            raise ContractError(f"{item['id']}: invalid basis")
        if item.get("urgency") not in {"P0", "P1", "P2"}:
            raise ContractError(f"{item['id']}: urgency must be P0/P1/P2 (not a legal minimum)")
        for key in ("building_ids", "requirement_ids", "rule_ids", "check_ids", "dependencies", "alternatives"):
            if not isinstance(item.get(key), list) or any(not isinstance(v, str) or not v.strip() for v in item[key]):
                raise ContractError(f"{item['id']}: {key} must be an array of nonempty strings")
        if any(b not in {"A", "B", "C"} for b in item["building_ids"]):
            raise ContractError(f"{item['id']}: unsupported building")
        if not isinstance(item.get("evidence", []), list) or any(
            not isinstance(v, dict) for v in item.get("evidence", [])
        ):
            raise ContractError(f"{item['id']}: evidence must be an array of objects")
    graph = {i["id"]: i["dependencies"] for i in register["items"]}
    visited, active = set(), set()

    def visit(key: str) -> None:
        if key in active:
            raise ContractError(f"Planning dependency cycle: {key}")
        if key in visited or key not in graph:
            return  # missing refs are visible gaps, not silently discarded
        active.add(key)
        for other in graph[key]:
            visit(other)
        active.remove(key)
        visited.add(key)

    for key in graph:
        visit(key)


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    """Allowlist output; private household/budget files are never read by this module."""
    keys = (
        "id",
        "title",
        "topic",
        "scenario",
        "question",
        "recommendation",
        "alternatives",
        "building_ids",
        "floor_id",
        "requirement_ids",
        "rule_ids",
        "check_ids",
        "dependencies",
        "due_phase",
        "responsible_role",
        "evidence_required",
        "status",
        "basis",
        "urgency",
        "reason",
        "physical_item_id",
        "requires_transport_measurement",
    )
    result = {k: copy.deepcopy(item.get(k)) for k in keys}
    result["evidence"] = [
        {k: e.get(k) for k in ("verified_by", "verified_at", "reference", "context_hash")}
        for e in item.get("evidence", [])
    ]
    return result


def build_risk_review(
    *,
    project_path: Path = ROOT / "inputs/project.json",
    requirements_path: Path = ROOT / "inputs/requirements.json",
    register_path: Path = REGISTER_PATH,
    rules_path: Path = RULES_PATH,
    drawing_report_path: Path | None = None,
    previous_report_path: Path | None = None,
    revision_root: Path = ROOT / "inputs/revisions",
    physical_items_path: Path = ROOT / "inputs/physical-items.json",
) -> dict[str, Any]:
    project, requirements, rules = read_json(project_path), read_json(requirements_path), read_json(rules_path)
    phase = project.get("stage")
    if phase not in PHASES:
        raise ContractError("Project stage must be a supported planning phase")
    reqs = {r["id"]: r for r in requirements.get("requirements", [])}
    rule_map = {r["rule_id"]: r for r in rules.get("rules", [])}
    physical = read_json(physical_items_path) if physical_items_path.is_file() else {"items": []}
    physical_map = {i["id"]: i for i in physical.get("items", [])}
    missing_register = not register_path.is_file()
    register = (
        read_json(register_path)
        if not missing_register
        else {"schema": "house-planning-register-v1", "project_id": project["project_id"], "items": []}
    )
    validate_register(register)
    from house_design.owner_workspace import owner_summary

    owner_records = owner_summary(project["project_id"], project_path.parent / "owner-records.json")
    if register["project_id"] != project.get("project_id"):
        raise ContractError("Planning register belongs to another project")
    drawing = read_json(drawing_report_path) if drawing_report_path else None
    checks = {}
    drawing_verified = False
    if drawing:
        # Review hashes bind the snapshot; never import its signoff or overall release conclusion.
        from house_design.review import _report_hash_payload

        drawing_verified = (
            drawing.get("schema") == "house-review-report-v1"
            and drawing.get("project", {}).get("project_id") == project["project_id"]
            and stable_hash(_report_hash_payload(drawing)) == drawing.get("report_hash")
        )
        if drawing_verified:
            from house_design.drawings import load_revision

            try:
                manifest, model = load_revision(drawing.get("revision", {}).get("revision_id", ""), revision_root)
                drawing_verified = manifest["content_hash"] == drawing["revision"].get("content_hash") and stable_hash(
                    model
                ) == stable_hash(drawing.get("model"))
            except (ContractError, KeyError, TypeError):
                drawing_verified = False
        checks = {c["check_id"]: c for c in drawing.get("coordination", {}).get("findings", [])}
    items, gaps = [], []
    raw_items = {i["id"]: i for i in register["items"]}
    linked = set()
    for raw in register["items"]:
        item = _public_item(raw)
        links = item["requirement_ids"]
        linked.update(r for r in links if r in reqs)
        context = {k: v for k, v in item.items() if k not in {"status", "evidence", "reason"}}
        context.update(
            owner_records_hash=owner_records["record_hash"],
            project=project,
            requirements={r: reqs.get(r) for r in links},
            rules={r: rule_map.get(r) for r in item["rule_ids"]},
            dependencies={i: _public_item(raw_items[i]) for i in item["dependencies"] if i in raw_items},
            physical_item=physical_map.get(item.get("physical_item_id")),
            drawing_hash=drawing.get("report_hash") if drawing else None,
        )
        item["context_hash"] = stable_hash(context)
        issues = []
        if not isinstance(item.get("responsible_role"), str) or not item["responsible_role"].strip():
            issues.append("缺責任角色")
        if not isinstance(item.get("evidence_required"), str) or not item["evidence_required"].strip():
            issues.append("缺驗收方式／證據要求")
        if not item["alternatives"]:
            issues.append("缺替代方案與代價")
        if item.get("physical_item_id") and item["physical_item_id"] not in physical_map:
            issues.append("實物清冊引用失效")
        if item.get("requires_transport_measurement"):
            transport = physical_map.get(item.get("physical_item_id"), {}).get("transport") or {}
            dimensions = transport.get("assembled_dimensions") or {}
            if (
                transport.get("measurement_state") != "measured"
                or not _proof(transport.get("evidence"))
                or not all(
                    isinstance(dimensions.get(k), (int, float))
                    and not isinstance(dimensions[k], bool)
                    and math.isfinite(dimensions[k])
                    and dimensions[k] > 0
                    for k in ("width_mm", "depth_mm", "height_mm")
                )
            ):
                issues.append("武轎搬運外廓尚未完成具名實測；暫估收納尺寸不能證明搬運")
        for key, known in (("requirement_ids", reqs), ("rule_ids", rule_map), ("dependencies", raw_items)):
            issues += [f"失效引用 {key}: {v}" for v in item[key] if v not in known]
        item["check_results"] = []
        for cid in item["check_ids"]:
            check = checks.get(cid)
            item["check_results"].append(
                {"check_id": cid, "status": check.get("status") if check and drawing_verified else "unknown"}
            )
            if not drawing_verified or not check:
                issues.append(f"尚未檢查／缺可信本版報告：{cid}")
            elif check["status"] != "pass":
                issues.append(f"指定檢查未通過：{cid} ({check['status']})")
        proofs = item["evidence"]
        effective = item["status"]
        if effective in GOOD:
            if not any(_proof(e) and e.get("context_hash") == item["context_hash"] for e in proofs):
                issues.append("缺本版具名、日期、來源與 context_hash 證據")
            if effective == "not_applicable" and not item.get("reason"):
                issues.append("不適用缺理由")
            if effective == "verified" and any(reqs.get(r, {}).get("status") != "confirmed" for r in links):
                issues.append("關聯需求尚未確認或已淘汰；須另行決策不適用")
            if issues:
                effective = "needs_review"
        item.update(
            status=effective,
            status_label=LABELS[effective],
            gaps=issues,
            due=PHASES.index(item["due_phase"]) <= PHASES.index(phase),
            requirement_states=[
                {"id": r, "title": reqs[r].get("title"), "status": reqs[r].get("status")} for r in links if r in reqs
            ],
        )
        items.append(item)
    lookup = {i["id"]: i for i in items}
    changed = True
    while changed:
        changed = False
        for item in items:
            blocked = [d for d in item["dependencies"] if d not in lookup or lookup[d]["status"] not in GOOD]
            item["pending_dependencies"] = blocked
            if blocked and item["status"] in GOOD:
                item.update(status="needs_review", status_label=LABELS["needs_review"])
                item["gaps"].append("前置決策未完成：" + "、".join(blocked))
                changed = True
    for rid in sorted(reqs.keys() - linked):
        gaps.append(
            {"code": "UNTRACKED_REQUIREMENT", "id": rid, "message": f"未追蹤需求：{reqs[rid].get('title', rid)}"}
        )
    for topic in TOPICS.keys() - {i["topic"] for i in items}:
        gaps.append({"code": "MISSING_TOPIC", "id": topic, "message": f"缺情境主題：{TOPICS[topic]}"})
    if missing_register:
        gaps.append({"code": "MISSING_REGISTER", "id": "register", "message": "缺防漏項清單"})
    for item in items:
        gaps += [{"code": "ITEM_GAP", "id": item["id"], "message": message} for message in item["gaps"]]
    items.sort(key=lambda i: (not i["due"], i["urgency"], PHASES.index(i["due_phase"]), i["id"]))
    due = [i for i in items if i["due"]]
    structural_gaps = [g for g in gaps if g["code"] != "ITEM_GAP"]
    report = {
        "schema": "house-planning-review-v1",
        "generated_at": utc_now(),
        "project": {
            "project_id": project["project_id"],
            "name": project.get("name"),
            "stage": phase,
            "buildings": project.get("buildings", []),
        },
        "warnings": [WARNING, "土地尚未選定：不推定實際尺寸、造價或可建量體。"]
        if not (project.get("site_search") or {}).get("selected_site")
        else [WARNING],
        "conflict_policy": CONFLICT_POLICY,
        "items": items,
        "gaps": gaps,
        "summary": {
            "total_items": len(items),
            "total_requirements": len(reqs),
            "tracked_requirements": len(linked),
            "untracked_requirements": sorted(reqs.keys() - linked),
            "topic_count": len({i["topic"] for i in items}),
            "status_counts": dict(Counter(i["status"] for i in items)),
            "due_items": len(due),
            "due_completed": sum(i["status"] in GOOD for i in due),
        },
        "readiness": {
            "eligible_for_decision_freeze": bool(due) and not structural_gaps and all(i["status"] in GOOD for i in due),
            "policy": "僅當期決策準備度；未到期項目提前提醒。不取代前期閘門或專業放行。",
            "due_open_ids": [i["id"] for i in due if i["status"] not in GOOD],
        },
        "inputs": {
            "project": stable_hash(project),
            "requirements": stable_hash(requirements),
            "register": stable_hash(register),
            "rules": stable_hash(rules),
            "physical_items": stable_hash(physical),
            "drawing_report": drawing.get("report_hash") if drawing_verified else None,
        },
        "changes": [],
        "owner_records": owner_records,
    }
    if previous_report_path:
        previous = read_json(previous_report_path)
        if (
            previous.get("schema") != report["schema"]
            or previous.get("project", {}).get("project_id") != project["project_id"]
        ):
            raise ContractError("Previous risk report belongs to another schema/project")
        if stable_hash({k: v for k, v in previous.items() if k not in {"generated_at", "report_hash"}}) != previous.get(
            "report_hash"
        ):
            raise ContractError("Previous risk report hash is invalid")
        old = {i["id"]: i for i in previous["items"]}
        for key in sorted(old.keys() | lookup.keys()):
            a, b = old.get(key), lookup.get(key)
            state = (
                "removed_needs_review"
                if b is None
                else "new"
                if a is None
                else "needs_review"
                if b["context_hash"] != a["context_hash"] or (a["status"] in GOOD and b["status"] not in GOOD)
                else "resolved"
                if a["status"] not in GOOD and b["status"] in GOOD
                else "persistent"
            )
            report["changes"].append({"id": key, "state": state})
            if b is None:
                report["gaps"].append(
                    {
                        "code": "REMOVED_ITEM",
                        "id": key,
                        "message": "已移除項目不得當成已解決；需保留原項目並具名說明不適用。",
                    }
                )
                report["readiness"]["eligible_for_decision_freeze"] = False
    report["report_hash"] = stable_hash({k: v for k, v in report.items() if k != "generated_at"})
    return report


def risk_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_hash": report["report_hash"],
        "summary": report["summary"],
        "readiness": report["readiness"],
        "warnings": report["warnings"],
        "conflict_policy": report["conflict_policy"],
        "owner_records": report.get("owner_records", {}),
        "open_decisions": [
            {k: i[k] for k in ("id", "title", "question", "building_ids", "due_phase", "responsible_role", "status")}
            for i in report["items"]
            if i["due"] and i["status"] not in GOOD
        ],
    }


def risk_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 三棟防漏項與決策驗收總表",
        "",
        *report["warnings"],
        "",
        f"需求已追蹤：{s['tracked_requirements']}/{s['total_requirements']}；主題 {s['topic_count']}/12。",
        f"當期已驗證／不適用：{s['due_completed']}/{s['due_items']}；已追蹤不代表已完成。",
        "",
        "## 衝突取捨",
        "",
        *[f"- {p}" for p in report["conflict_policy"]],
        "",
    ]
    for heading, selected in (
        ("現在要決定", [i for i in report["items"] if i["due"]]),
        ("後續不可忘", [i for i in report["items"] if not i["due"]]),
    ):
        lines += [f"## {heading}", ""]
        for i in selected:
            lines += [
                f"### {i['id']} · {i['title']} [{i['status_label']}]",
                "",
                f"- 主題／棟層：{TOPICS[i['topic']]}／{'、'.join(i['building_ids']) or '全棟'} {i.get('floor_id') or ''}",
                f"- 情境：{i['scenario']}",
                f"- 待決策：{i['question']}",
                f"- 建議（未定案）：{i['recommendation']}",
                f"- 替代／代價：{'；'.join(i['alternatives'])}",
                f"- 最晚確認：{i['due_phase']}；責任：{i.get('responsible_role') or '缺責任人'}",
                f"- 驗收證據：{i['evidence_required']}",
                f"- 關聯需求：{'、'.join(i['requirement_ids']) or '跨專項'}",
                f"- 待補：{'；'.join(i['gaps']) or '仍需完成決策與證據'}",
                f"- 本版 context_hash：`{i['context_hash']}`",
                "",
            ]
    lines += [
        "## 尚未檢查與失效引用",
        "",
        *[f"- {g['id']}：{g['message']}" for g in report["gaps"]],
        "",
        "## 變更追蹤",
        "",
        *[f"- {c['id']}：{c['state']}" for c in report["changes"]],
        "",
        f"Report hash: `{report['report_hash']}`",
    ]
    from house_design.owner_workspace import records_markdown

    return "\n".join(lines) + records_markdown(report.get("owner_records", {}))


def risk_html(report: dict[str, Any]) -> str:
    from house_design.owner_workspace import records_html
    def e(value: Any) -> str:
        return escape(str(value if value is not None else ""))

    sections = []
    buckets = [
        ("due", "現在要決定", lambda i: i["due"] and i["status"] not in GOOD),
        ("later", "後續不可忘", lambda i: not i["due"]),
        ("professional", "專業待確認", lambda i: i["basis"] == "professional_required" and i["status"] not in GOOD),
        ("unchecked", "尚未檢查／待複核", lambda i: bool(i["gaps"]) or i["status"] not in GOOD),
        ("all", "全部追蹤項目", lambda i: True),
    ]
    for bid, title, predicate in buckets:
        cards = []
        for i in report["items"]:
            if not predicate(i):
                continue
            cards.append(
                f'<article data-buildings="{e(" ".join(i["building_ids"]))}" data-topic="{e(i["topic"])}" '
                f'data-phase="{e(i["due_phase"])}" data-status="{e(i["status"])}">'
                f'<h3>{e(i["id"])} · {e(i["title"])}</h3><p class="tag">{e(i["status_label"])} · '
                f"{e(TOPICS[i['topic']])} · {e('／'.join(i['building_ids']))} · 最晚 {e(i['due_phase'])} · {e(i['urgency'])} 優先討論</p>"
                f"<p><strong>情境</strong> {e(i['scenario'])}</p><p><strong>待決策</strong> {e(i['question'])}</p>"
                f"<p><strong>建議（未定案）</strong> {e(i['recommendation'])}</p><details><summary>替代方案、責任與驗收證據</summary>"
                f"<p>替代／代價：{e('；'.join(i['alternatives']))}</p><p>責任：{e(i.get('responsible_role') or '缺責任人')}</p>"
                f"<p>驗收證據：{e(i['evidence_required'])}</p><p>需求：{e('、'.join(i['requirement_ids']) or '跨專項')}</p>"
                f"<p>前置未完成：{e('、'.join(i['pending_dependencies']) or '無')}</p>"
                f"<p>待補：{e('；'.join(i['gaps']) or '仍需決策與證據')}</p>"
                f"<p>指定檢查：{e(json.dumps(i['check_results'], ensure_ascii=False))}</p>"
                f"<p>本版 context_hash：<code>{e(i['context_hash'])}</code></p></details></article>"
            )
        sections.append(
            f'<section data-bucket="{bid}" hidden><h2>{title}</h2>{"".join(cards) or "<p>此分類無項目</p>"}</section>'
        )
    s = report["summary"]

    def options(values: Any) -> str:
        return "".join(f'<option value="{e(k)}">{e(v)}</option>' for k, v in values)

    payload = json.dumps(report["gaps"], ensure_ascii=False).replace("<", "\\u003c")
    return (
        '<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>三棟防漏項與決策總表</title><style>*{box-sizing:border-box}body{font:16px/1.65 system-ui,sans-serif;"
        "margin:0;color:#172b3a;background:#f5f7f9;overflow-wrap:anywhere}main{max-width:1100px;margin:auto;padding:24px}"
        "h1{line-height:1.3}article{padding:18px;margin:12px 0;border:1px solid #ccd6df;border-radius:8px;background:white}"
        ".warning{border-left:5px solid #b45309;background:#fff7ed;padding:12px}.tag{color:#526579;font-size:14px}"
        ".filters{display:flex;flex-wrap:wrap;gap:12px;margin:18px 0}label{display:flex;flex-direction:column}"
        "select,button{font:inherit;padding:8px;min-height:44px}code{font-size:13px}details p{margin:8px 0}"
        "[hidden]{display:none!important}@media print{.filters,button{display:none}body{background:white}main{padding:0}"
        "article{break-inside:avoid}details>summary{display:none}}@media(max-width:500px){main{padding:16px}h1{font-size:26px}}</style>"
        "<main><h1>三棟防漏項與決策總表</h1><p>"
        + e(report["project"]["name"])
        + " · "
        + e(report["project"]["stage"])
        + "</p>"
        + "".join(f'<p class="warning">{e(w)}</p>' for w in report["warnings"])
        + records_html(report.get("owner_records", {}))
        + f'<p id="coverage">需求已追蹤 {s["tracked_requirements"]}/{s["total_requirements"]}；主題 {s["topic_count"]}/12；'
        f"當期已驗證／不適用 {s['due_completed']}/{s['due_items']}。未設定或缺證據不代表通過。</p>"
        "<details><summary>衝突處理與棟別定位</summary>"
        + "".join(f"<p>{e(p)}</p>" for p in report["conflict_policy"])
        + "".join(f"<p>{e(b.get('id'))}：{e(b.get('role'))}</p>" for b in report["project"]["buildings"])
        + '</details><div class="filters"><label>分類<select id="bucket">'
        + options((b, t) for b, t, _ in buckets)
        + '</select></label><label>棟別<select id="building"><option value="">全部</option>'
        + options((b, b + " 棟") for b in "ABC")
        + '</select></label><label>主題<select id="topic"><option value="">全部</option>'
        + options(TOPICS.items())
        + '</select></label><label>最晚階段<select id="phase"><option value="">全部</option>'
        + options((p, p) for p in PHASES)
        + '</select></label><label>狀態<select id="status"><option value="">全部</option>'
        + options(LABELS.items())
        + '</select></label></div><button id="print" type="button">列印目前篩選</button>'
        '<p id="count" role="status"></p>'
        + "".join(sections)
        + '<section><h2>漏項與資料問題</h2><ul id="gapList"></ul></section>'
        + "<section><h2>新增、移除與複核追蹤</h2><ul>"
        + "".join(
            f"<li>{e(c['id'])}：{e({'new': '新增', 'removed_needs_review': '已移除／不可當作解決', 'needs_review': '內容或驗證失效／待複核', 'resolved': '已驗證／不適用', 'persistent': '持續追蹤'}[c['state']])}</li>"
            for c in report["changes"]
        )
        + "</ul></section>"
        + "<p>Report hash：<code>"
        + e(report["report_hash"])
        + "</code></p></main><script>"
        'const fields=["building","topic","phase","status"],bucket=document.getElementById("bucket");'
        'function render(){let count=0;document.querySelectorAll("[data-bucket]").forEach(s=>{s.hidden=s.dataset.bucket!==bucket.value;'
        's.querySelectorAll("article").forEach(a=>{a.hidden=fields.some(k=>{const v=document.getElementById(k).value;'
        'return v&&(k==="building"?!a.dataset.buildings.split(" ").includes(v):a.dataset[k]!==v)});if(!s.hidden&&!a.hidden)count++})});'
        'document.getElementById("count").textContent=`目前顯示 ${count} 項`;}'
        'document.querySelectorAll("select").forEach(s=>s.addEventListener("change",render));'
        'document.getElementById("print").addEventListener("click",()=>window.print());'
        'addEventListener("beforeprint",()=>document.querySelectorAll("details").forEach(d=>{d.dataset.wasOpen=String(d.open);d.open=true}));'
        'addEventListener("afterprint",()=>document.querySelectorAll("details").forEach(d=>{d.open=d.dataset.wasOpen==="true"}));'
        "const gaps="
        + payload
        + ';gaps.forEach(g=>{const li=document.createElement("li");li.textContent=g.id+"："+g.message;'
        'document.getElementById("gapList").append(li)});render();</script></html>'
    )


def write_risk_review(report: dict[str, Any], output_root: Path) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": output_root / "risk-review.json",
        "markdown": output_root / "risk-review.md",
        "html": output_root / "risk-review.html",
    }
    write_json(paths["json"], report)
    from house_design.owner_workspace import tool_links

    paths["markdown"].write_text(risk_markdown(report), encoding="utf-8")

    paths["html"].write_text(tool_links(risk_html(report), output_root), encoding="utf-8")
    return paths

"""One printable, offline packet for the first architect meeting.

The owner is still looking for land, so this packet is not a layout review. It
is the material for a site-feasibility consultation: what the family is trying
to build, what would disqualify a parcel, what is known about the candidates so
far, one hypothetical envelope scenario, and the questions that have to come
back answered.

This module **composes, it does not compute**. Every section quotes an artifact
another command already produced and records that artifact's SHA-256, so a
printed page can be traced to the exact inputs it came from. When a source is
missing or was generated before its own inputs changed, the section says so
rather than quietly showing stale numbers - an architect reading a confident
page has no way to tell it was out of date.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from house_design.contracts import (
    ROOT,
    read_json,
    relative_to_root,
    sha256_file,
    stable_hash,
    utc_now,
)

MEETING_PACK_SCHEMA = "house-meeting-pack-v1"
AUDIENCES = ("architect",)
PREDESIGN_OUTPUT_ROOT = ROOT / "structured/predesign"
PROJECT_PATH = ROOT / "inputs/project.json"
PREDESIGN_PATH = ROOT / "inputs/predesign.json"
SITE_CRITERIA_PATH = ROOT / "inputs/site-criteria.json"
HANDOFF_ROOT = ROOT / "structured/architect_handoffs/R001"

PACK_WARNING = (
    "本資料夾全部是屋主端的前期整理，不是法規檢討、不是設計圖、也不是可行性意見。"
    "所有分區、建蔽率、容積率、退縮、建築線、結構與消防結論，都必須由高雄市執業建築師"
    "依個案正式認定並簽證。"
)
UNKNOWN_WARNING = "未知永遠不是通過：本包內任何標示「未知／資料不足」的項目，都不得被當成已通過或已合規。"
LAND_WARNING = "土地尚未選定。三筆相鄰、每筆約 32 坪是選地目標，不是已取得的基地，更不是每層可建面積。"

MEETING_QUESTIONS = [
    {
        "number": 1,
        "text": "以三筆各約 32 坪相鄰地、每棟 3 層＋RF 為前提，最小可接受的面寬與深度是多少？",
        "why": "這兩個數字直接填回 SC-FRONTAGE-MIN 與 SC-DEPTH-MIN，沒有它們，候選地比較表無法做出任何篩選。",
        "writes_back": "inputs/site-criteria.json · SC-FRONTAGE-MIN / SC-DEPTH-MIN",
        "answer": "",
    },
    {
        "number": 2,
        "text": "三筆地要各自申照還是合併申請？對建蔽率、法定空地、防火間隔與棟距分別有什麼影響？",
        "why": "影響三棟的量體、棟距與設備策略；也決定跨基地管線是否可行。",
        "writes_back": "inputs/site-criteria.json · SC-THREE-PERMITS / SC-CROSS-PARCEL-UTILITY",
        "answer": "",
    },
    {
        "number": 3,
        "text": "室內車庫（單車位淨 3000 × 6100 mm）在這種面寬下是否成立？不成立時的替代方案是什麼？",
        "why": "車位在室內是屋主的硬需求；此淨尺寸由休旅車加壁掛充電樁推導，不是抓的。",
        "writes_back": "inputs/site-criteria.json · SC-FRONTAGE-MIN；envelope 情境的 ENV-GARAGE-1BAY",
        "answer": "",
    },
    {
        "number": 4,
        "text": "B 棟神明廳與武轎搬運路徑（目前規劃目標淨寬 1500 mm），在結構與法規上有哪些早期限制？",
        "why": "神明廳位置與武轎進出會鎖住樓梯、開口與結構，愈晚改代價愈高。",
        "writes_back": "envelope 情境的 ENV-SHRINE-STACK / ENV-PALANQUIN-PATH",
        "answer": "",
    },
    {
        "number": 5,
        "text": "全齡無障礙基準下，1F 完整生活圈（出入、衛浴、睡眠、用餐）的最小合理面積是多少？",
        "why": "全齡無障礙是不可妥協的家庭基準，但專案目前沒有可引用的最小面積依據，只能標 unknown。",
        "writes_back": "envelope 情境的 ENV-GROUND-FLOOR-LIFE / ENV-ELDER-SUITE",
        "answer": "",
    },
    {
        "number": 6,
        "text": "你需要我在簽約買地前準備哪些文件，才能給出書面可行性意見？費用與時程大概是多少？",
        "why": "這場會議的目的就是把「憑印象買地」換成「有書面意見再出價」。",
        "writes_back": "inputs/predesign.json · PD-SITE-SELECTED 的 evidence pointer",
        "answer": "",
    },
]


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def _source(path: Path, role: str, *, produced_by: str = "") -> dict[str, Any]:
    exists = path.is_file()
    return {
        "path": relative_to_root(path),
        "role": role,
        "exists": exists,
        "produced_by": produced_by,
        "sha256": sha256_file(path) if exists else None,
    }


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return read_json(path)
    except Exception:  # noqa: BLE001 - a corrupt artifact must degrade, not crash the packet
        return None


def _missing(role: str, command: str) -> dict[str, Any]:
    return {
        "available": False,
        "note": f"{role}尚未產生。請先執行 `{command}`，再重新產生本開會包。",
        "command": command,
    }


def build_meeting_pack(
    *,
    audience: str = "architect",
    project_path: Path = PROJECT_PATH,
    predesign_path: Path = PREDESIGN_PATH,
    criteria_path: Path = SITE_CRITERIA_PATH,
    predesign_root: Path = PREDESIGN_OUTPUT_ROOT,
    handoff_root: Path = HANDOFF_ROOT,
    requirements_path: Path = ROOT / "inputs/requirements.json",
    planning_register_path: Path = ROOT / "inputs/planning-register.json",
    planning_rules_path: Path = ROOT / "rules/predesign_readiness_rules.json",
    physical_items_path: Path = ROOT / "inputs/physical-items.json",
) -> dict[str, Any]:
    if audience not in AUDIENCES:
        raise ValueError(f"Unsupported audience {audience!r}; expected one of {AUDIENCES}")

    project = read_json(project_path)
    predesign = _load(predesign_path) or {}
    criteria = _load(criteria_path)
    compare = _load(predesign_root / "site-compare.json")
    envelope = _load(predesign_root / "envelope.json")
    brief = _load(predesign_root / "design-brief.json")
    readiness = _load(predesign_root / "report.json")
    handoff = _load(handoff_root / "handoff-manifest.json")

    sections = [
        _section_identity(project, predesign, brief),
        _section_criteria(criteria),
        _section_candidates(compare),
        _section_envelope(envelope),
        _section_brief(brief),
        _section_blockers(readiness),
        _section_handoff(handoff, handoff_root),
        _section_questions(),
        _section_planning(_load(predesign_root / "risk-review.json"), project, requirements_path,
                          planning_register_path, planning_rules_path, physical_items_path),
    ]

    pack: dict[str, Any] = {
        "schema": MEETING_PACK_SCHEMA,
        "audience": audience,
        "generated_at": utc_now(),
        "project": {
            "project_id": project.get("project_id"),
            "name": project.get("name"),
            "stage": project.get("stage"),
        },
        "warnings": [PACK_WARNING, LAND_WARNING, UNKNOWN_WARNING],
        "sections": sections,
        "missing_sections": [item["title"] for item in sections if not item["available"]],
        "sources": [
            _source(project_path, "基地事實與候選土地", produced_by="屋主維護"),
            _source(predesign_path, "階段閘門與三棟定位", produced_by="屋主維護"),
            _source(criteria_path, "選地淘汰條件", produced_by="屋主與建築師共同填寫"),
            _source(predesign_root / "site-compare.json", "候選地比較", produced_by="predesign site-compare"),
            _source(predesign_root / "envelope.json", "假設量體試算", produced_by="predesign envelope"),
            _source(predesign_root / "design-brief.json", "設計任務書", produced_by="predesign brief"),
            _source(predesign_root / "report.json", "前期準備完成度", produced_by="predesign report"),
            _source(handoff_root / "handoff-manifest.json", "交付契約", produced_by="drawings prepare-handoff"),
            _source(predesign_root / "risk-review.json", "防漏項與當期決策", produced_by="predesign risk-review"),
        ],
    }
    pack["pack_hash"] = stable_hash({key: value for key, value in pack.items() if key != "generated_at"})
    return pack


def _section_planning(report: dict[str, Any] | None, project: dict[str, Any], requirements_path: Path,
                      register_path: Path, rules_path: Path, physical_items_path: Path) -> dict[str, Any]:
    section = {"id": "planning", "number": 9, "title": "防漏項與當期決策"}
    if not report:
        return {**section, **_missing("防漏項總表", "predesign risk-review")}
    valid = (report.get("schema") == "house-planning-review-v1"
             and stable_hash({k: v for k, v in report.items() if k not in {"report_hash", "generated_at"}}) == report.get("report_hash")
             and report.get("inputs", {}).get("project") == stable_hash(project))
    for key, path in (("requirements", requirements_path), ("register", register_path), ("rules", rules_path),
                      ("physical_items", physical_items_path)):
        payload = _load(path)
        valid = valid and payload is not None and stable_hash(payload) == report.get("inputs", {}).get(key)
    if report.get("owner_records"):
        from house_design.owner_workspace import owner_summary

        valid = valid and stable_hash(owner_summary(project["project_id"], requirements_path.parent / "owner-records.json")) == stable_hash(report["owner_records"])
    if not valid:
        return {**section, "available": False, "note": "防漏項總表已過期或證據雜湊不符；請重跑 predesign risk-review，不引用舊決策。"}
    from house_design.planning import risk_summary

    return {**section, "available": True, **risk_summary(report),
            "note": "本節只引用當期問題；完整十二組情境及驗收總表見 ../../risk-review.html。"}


def _section_identity(project: dict[str, Any], predesign: dict[str, Any], brief: dict[str, Any] | None) -> dict[str, Any]:
    search = project.get("site_search") or {}
    target = search.get("target_scenario") or {}
    roles = (predesign.get("building_roles") or {}) if isinstance(predesign.get("building_roles"), dict) else {}
    if brief:
        buildings = [
            {"id": item.get("id"), "role": item.get("role"), "status": item.get("role_status_label")}
            for item in brief.get("buildings") or []
        ]
    else:
        buildings = [{"id": key, "role": value, "status": "—"} for key, value in sorted(roles.items())]

    return {
        "id": "identity",
        "number": 1,
        "title": "我們是誰、要蓋什麼",
        "available": True,
        "facts": [
            ("專案", project.get("name")),
            ("目前階段", project.get("stage")),
            ("土地狀態", search.get("selection_status")),
            ("選地目標", target.get("summary") or "三筆相鄰土地，每筆約 32 坪"),
            ("已登錄候選地", len(search.get("candidate_sites") or [])),
            ("層數政策", "每棟 3 層＋RF（RF 是屋頂層，不是第四層）"),
        ],
        "buildings": buildings,
        "shared_items": (brief or {}).get("shared_items_to_confirm") or [],
        "household": _household(brief),
        "note": LAND_WARNING,
    }


def _household(brief: dict[str, Any] | None) -> dict[str, Any]:
    household = (brief or {}).get("household") or {}
    if not household.get("provided"):
        return {"provided": False, "note": "家庭概況尚未登錄。"}
    return {
        "provided": True,
        "people_total": household.get("people_total"),
        "age_bands": household.get("age_bands") or {},
        "usual_building": household.get("usual_building") or {},
        "mobility_now": household.get("mobility_now") or {},
        "vehicles": household.get("vehicles") or [],
        "note": "僅呈現去識別化統計；個人資料保留在未進版控的私有檔。",
    }


def _section_criteria(criteria: dict[str, Any] | None) -> dict[str, Any]:
    if criteria is None:
        return {
            "id": "criteria",
            "number": 2,
            "title": "選地淘汰條件",
            **_missing("選地淘汰條件", "建立 inputs/site-criteria.json"),
        }
    items = [item for item in criteria.get("criteria") or [] if isinstance(item, dict)]
    unset = [item for item in items if (item.get("threshold") or {}).get("value") is None]
    return {
        "id": "criteria",
        "number": 2,
        "title": "選地淘汰條件",
        "available": True,
        "policy": criteria.get("policy") or {},
        "criteria": [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "kind": item.get("kind"),
                "threshold": (item.get("threshold") or {}).get("value"),
                "unit": (item.get("threshold") or {}).get("unit"),
                "comparator": (item.get("threshold") or {}).get("comparator"),
                "rationale": item.get("rationale"),
                "evidence_required": item.get("evidence_required"),
                "responsible_role": item.get("responsible_role"),
            }
            for item in items
        ],
        "unset_count": len(unset),
        "note": (
            f"{len(items)} 條中有 {len(unset)} 條門檻尚未設定。會議第 1、2 題的答案就是要填回這裡。"
            if unset
            else f"{len(items)} 條門檻皆已設定。"
        ),
    }


def _section_candidates(compare: dict[str, Any] | None) -> dict[str, Any]:
    if compare is None:
        return {
            "id": "candidates",
            "number": 3,
            "title": "候選地比較與缺件",
            **_missing("候選地比較表", "python -m house_design predesign site-compare"),
        }
    return {
        "id": "candidates",
        "number": 3,
        "title": "候選地比較與缺件",
        "available": True,
        "summary": compare.get("summary") or {},
        "candidates": [
            {
                "candidate_id": item.get("candidate_id"),
                "label": item.get("label"),
                "verdict": item.get("verdict"),
                "verdict_label": item.get("verdict_label"),
                "state_counts": item.get("state_counts") or {},
                "missing_evidence": item.get("missing_evidence") or [],
            }
            for item in compare.get("candidates") or []
        ],
        "next_actions": compare.get("next_actions") or [],
        "compare_hash": compare.get("compare_hash"),
        "note": UNKNOWN_WARNING,
    }


def _section_envelope(envelope: dict[str, Any] | None) -> dict[str, Any]:
    if envelope is None:
        return {
            "id": "envelope",
            "number": 4,
            "title": "假設量體試算（假設情境）",
            **_missing("假設量體試算", "python -m house_design predesign envelope --assume-bcr … --assume-far …"),
        }
    return {
        "id": "envelope",
        "number": 4,
        "title": "假設量體試算（假設情境）",
        "available": True,
        "scenario": envelope.get("scenario"),
        "inputs": envelope.get("inputs") or {},
        "area": envelope.get("area") or {},
        "checks": envelope.get("core_function_checks") or [],
        "overall_verdict": envelope.get("overall_verdict"),
        "overall_verdict_label": envelope.get("overall_verdict_label"),
        "scenario_hash": envelope.get("scenario_hash"),
        "warnings": envelope.get("warnings") or [],
        "note": "此頁每個數字都是假設。請建築師直接指出哪個假設不成立。",
    }


def _section_brief(brief: dict[str, Any] | None) -> dict[str, Any]:
    if brief is None:
        return {
            "id": "brief",
            "number": 5,
            "title": "設計任務書摘要",
            **_missing("設計任務書", "python -m house_design predesign brief"),
        }
    summary = brief.get("decision_summary") or {}
    questions = [
        {"building_id": group.get("building_id"), "role": group.get("role"), "questions": group.get("questions") or []}
        for group in brief.get("open_questions") or []
    ]
    return {
        "id": "brief",
        "number": 5,
        "title": "設計任務書摘要",
        "available": True,
        "summary": summary,
        "relationships": [
            {
                "requirement_title": item.get("requirement_title"),
                "building_id": item.get("building_id"),
                "type_label": item.get("type_label"),
                "description": item.get("description"),
                "status_label": item.get("status_label"),
                "rationale": item.get("rationale"),
            }
            for item in brief.get("relationships") or []
        ],
        "physical_items": (brief.get("physical_items") or {}).get("items") or [],
        "physical_items_policy": (brief.get("physical_items") or {}).get("policy_note"),
        "open_questions": questions,
        "brief_hash": brief.get("brief_hash"),
        "note": (
            f"{summary.get('requirements', 0)} 項需求中，已確認 {summary.get('status_counts', {}).get('confirmed', 0)} 項。"
            "未確認的項目代表屋主尚未取捨，不是建築師可以自由決定的空白。"
        ),
    }


def _section_blockers(readiness: dict[str, Any] | None) -> dict[str, Any]:
    if readiness is None:
        return {
            "id": "blockers",
            "number": 6,
            "title": "目前的硬阻擋與責任分工",
            **_missing("前期準備報告", "python -m house_design predesign report"),
        }
    findings = [item for item in readiness.get("findings") or [] if isinstance(item, dict)]
    blocking = [item for item in findings if item.get("blocking") and item.get("status") != "verified"]
    return {
        "id": "blockers",
        "number": 6,
        "title": "目前的硬阻擋與責任分工",
        "available": True,
        "readiness": readiness.get("readiness") or {},
        "gate": readiness.get("gate") or {},
        "blockers": [
            {
                "rule_id": item.get("rule_id"),
                "title": item.get("title"),
                "phase": item.get("phase"),
                "status_label": item.get("status_label"),
                "responsible_role": item.get("responsible_role"),
                "next_action": item.get("next_action"),
            }
            for item in blocking
        ],
        "report_hash": readiness.get("report_hash"),
        "note": "這些阻擋不是程式可以自行解除的；每一項都要由負責角色補上證據後，由屋主手動改狀態。",
    }


def _section_handoff(handoff: dict[str, Any] | None, handoff_root: Path) -> dict[str, Any]:
    if handoff is None:
        return {
            "id": "handoff",
            "number": 7,
            "title": "圖面交付契約預告",
            **_missing("交付契約", "python -m house_design drawings prepare-handoff"),
        }
    return {
        "id": "handoff",
        "number": 7,
        "title": "圖面交付契約預告",
        "available": True,
        "revision": handoff.get("revision"),
        "label": handoff.get("label"),
        "root": relative_to_root(handoff_root),
        "expectations": [
            "PDF 圖面（不可變版次的主文件）",
            "IFC 或 DXF 幾何；只有 2D CAD 時請將 DWG 另存 DXF",
            "圖層對應表（mapping v2）：圖層 → 棟別、樓層、空間／門窗／設備",
            "匯入時原圖與 mapping 會一併雜湊並鎖定在該版次，之後不得就地修改",
        ],
        "note": "土地尚未選定，因此這只是未來的交付契約，不是現在的委託。",
    }


def _section_questions() -> dict[str, Any]:
    return {
        "id": "questions",
        "number": 8,
        "title": "本次會議要拿到的答案",
        "available": True,
        "questions": MEETING_QUESTIONS,
        "note": "每一題都標明答案會寫回哪個檔案。會後請照這個對應更新，不要只留在記憶裡。",
    }


PACK_CSS = (
    "*{box-sizing:border-box}body{font:16px/1.7 system-ui,'Noto Sans TC',sans-serif;color:#17212b;background:#f6f8fa;"
    "margin:0;padding:0}main{max-width:1040px;margin:0 auto;padding:32px 20px 64px;background:#fff}"
    "h1{font-size:30px;line-height:1.25;margin:0 0 8px}h2{font-size:22px;border-bottom:3px solid #1f3d5c;"
    "padding-bottom:6px;margin:44px 0 14px}h3{font-size:17px;margin:22px 0 8px}"
    "p{margin:10px 0}ul,ol{margin:10px 0;padding-left:1.5em}li{margin:4px 0}"
    ".warn{border-left:5px solid #b45309;background:#fff7ed;padding:12px 16px;margin:10px 0}"
    ".scenario{border:3px solid #b91c1c;background:#fef2f2;padding:12px 16px;margin:12px 0;font-weight:700}"
    ".missing{border:2px dashed #94a3b8;background:#f8fafc;padding:12px 16px;margin:10px 0;color:#334155}"
    ".meta{color:#475569;font-size:14px}.note{color:#334155;background:#eef2f6;padding:10px 14px;"
    "border-radius:6px;margin:10px 0}"
    ".table-wrap{overflow-x:auto;margin:12px 0}table{border-collapse:collapse;width:100%;font-size:15px}"
    "th,td{border:1px solid #b8c2cc;padding:8px 10px;text-align:left;vertical-align:top}"
    "th{background:#eef2f6}code{background:#eef2f6;padding:2px 5px;border-radius:3px;overflow-wrap:anywhere;"
    "font-size:14px}"
    ".badge{display:inline-block;border-radius:999px;padding:1px 10px;font-size:13px;border:1px solid #94a3b8;"
    "white-space:nowrap}"
    ".v-fits,.v-keep{background:#dcfce7;border-color:#15803d}.v-tight{background:#fef9c3;border-color:#a16207}"
    ".v-does_not_fit,.v-eliminated{background:#fee2e2;border-color:#b91c1c}.v-unknown{background:#f1f5f9}"
    ".toc{background:#f1f5f9;border:1px solid #cbd5e1;border-radius:8px;padding:14px 20px;margin:20px 0}"
    ".toc ol{margin:6px 0}.q{border:1px solid #cbd5e1;border-radius:8px;padding:14px 18px;margin:14px 0}"
    ".q .ask{font-weight:700;font-size:17px}.answer{border:1px dashed #94a3b8;border-radius:6px;min-height:72px;"
    "margin-top:10px;padding:8px 10px;color:#94a3b8;font-size:14px}"
    "footer{margin-top:48px;padding-top:16px;border-top:1px solid #cbd5e1;color:#475569;font-size:14px}"
    "@media print{body{background:#fff}main{max-width:none;padding:0}h2{break-after:avoid;page-break-after:avoid}"
    ".q,.table-wrap{break-inside:avoid}.answer{min-height:96px}section{break-before:page;page-break-before:always}"
    "section:first-of-type{break-before:auto;page-break-before:auto}}"
)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{_e(item)}</th>" for item in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _badge(value: Any, label: Any = None) -> str:
    return f'<span class="badge v-{_e(value)}">{_e(label if label is not None else value)}</span>'


def _render_section(section: dict[str, Any]) -> str:
    parts = [f'<section id="s{section["number"]}"><h2>{section["number"]}. {_e(section["title"])}</h2>']
    if not section["available"]:
        parts.append(
            f'<p class="missing">{_e(section["note"])}</p></section>'
        )
        return "".join(parts)

    handler = {
        "identity": _render_identity,
        "criteria": _render_criteria,
        "candidates": _render_candidates,
        "envelope": _render_envelope,
        "brief": _render_brief,
        "blockers": _render_blockers,
        "handoff": _render_handoff,
        "questions": _render_questions,
        "planning": _render_planning,
    }[section["id"]]
    parts.append(handler(section))
    if section.get("note"):
        parts.append(f'<p class="note">{_e(section["note"])}</p>')
    parts.append("</section>")
    return "".join(parts)


def _render_planning(section: dict[str, Any]) -> str:
    from house_design.owner_workspace import records_html

    s = section["summary"]
    return (f'<p>需求已追蹤 {s["tracked_requirements"]}/{s["total_requirements"]}；已追蹤不等於已驗證。</p>'
            '<p><a href="../../risk-review.html">完整情境與驗收總表</a></p>'
            + records_html(section.get("owner_records", {}))
            + ''.join(f'<p class="warn">{_e(w)}</p>' for w in section["warnings"])
            + ''.join(f'<div class="q"><strong>{_e(i["id"])}：{_e(i["question"])}</strong>'
                      f'<p>責任：{_e(i["responsible_role"])} · 最晚 {_e(i["due_phase"])}</p>'
                      '<div class="answer">會議答案與證據引用（填回同一 planning-register）</div></div>'
                      for i in section["open_decisions"]))


def _render_identity(section: dict[str, Any]) -> str:
    parts = [_table(["項目", "內容"], [[_e(key), _e(value)] for key, value in section["facts"]])]
    parts.append("<h3>三棟定位</h3>")
    parts.append(
        _table(
            ["棟別", "定位", "狀態"],
            [[_e(item.get("id")), _e(item.get("role")), _e(item.get("status"))] for item in section["buildings"]],
        )
    )
    if section["shared_items"]:
        parts.append("<h3>三棟共用、必須一起決定的事</h3><ul>")
        parts.extend(f"<li>{_e(item)}</li>" for item in section["shared_items"])
        parts.append("</ul>")
    household = section["household"]
    if household.get("provided"):
        parts.append("<h3>家庭概況（去識別化）</h3>")
        vehicles = "、".join(
            f"{item.get('category')} 現有 {item.get('current_count')} 未來 {item.get('future_count')}"
            for item in household.get("vehicles") or []
        )
        parts.append(
            _table(
                ["項目", "內容"],
                [
                    ["總人數", _e(household.get("people_total"))],
                    ["年齡分布", _e("、".join(f"{k} {v} 人" for k, v in (household.get("age_bands") or {}).items()))],
                    ["常住棟別", _e("、".join(f"{k} {v} 人" for k, v in (household.get("usual_building") or {}).items()))],
                    ["行動能力", _e("、".join(f"{k} {v} 人" for k, v in (household.get("mobility_now") or {}).items()))],
                    ["車輛", _e(vehicles)],
                ],
            )
        )
        parts.append(f'<p class="meta">{_e(household.get("note"))}</p>')
    return "".join(parts)


def _render_criteria(section: dict[str, Any]) -> str:
    policy = section.get("policy") or {}
    parts = []
    if policy.get("verdict_rule"):
        parts.append(f'<p class="warn">{_e(policy["verdict_rule"])}</p>')
    rows = []
    for item in section["criteria"]:
        threshold = item.get("threshold")
        shown = (
            f"{_e(item.get('comparator'))} {_e(threshold)} {_e(item.get('unit'))}"
            if threshold is not None
            else "<strong>未設定</strong>"
        )
        rows.append(
            [
                f"<code>{_e(item.get('id'))}</code>",
                _e(item.get("label")),
                _e(item.get("kind")),
                shown,
                _e(item.get("rationale")),
                _e(item.get("evidence_required")),
                _e(item.get("responsible_role")),
            ]
        )
    parts.append(_table(["id", "條件", "類型", "門檻", "依據", "需要的證據", "負責角色"], rows))
    return "".join(parts)


def _render_candidates(section: dict[str, Any]) -> str:
    summary = section["summary"]
    parts = [
        f'<p class="meta">候選地 {_e(summary.get("candidates_total"))} 筆｜淘汰條件 '
        f'{_e(summary.get("criteria_total"))} 條（{_e(summary.get("criteria_without_threshold"))} 條門檻未設定）'
        f'｜待補證據 {_e(summary.get("open_evidence_items"))} 項</p>'
    ]
    if not section["candidates"]:
        parts.append(
            '<p class="missing">尚未登錄任何候選土地。先用 '
            "<code>python -m house_design intake site-add --id SITE-001 --label &quot;地段名&quot;</code> 建立，"
            "再逐格填入官方查得的事實。</p>"
        )
    else:
        parts.append(
            _table(
                ["候選地", "結論", "符合", "不符合", "未知", "待補證據"],
                [
                    [
                        f"{_e(item.get('label'))}<br><code>{_e(item.get('candidate_id'))}</code>",
                        _badge(item.get("verdict"), item.get("verdict_label")),
                        _e((item.get("state_counts") or {}).get("pass", 0)),
                        _e((item.get("state_counts") or {}).get("eliminated", 0)),
                        _e((item.get("state_counts") or {}).get("unknown", 0)),
                        _e(len(item.get("missing_evidence") or [])),
                    ]
                    for item in section["candidates"]
                ],
            )
        )
    if section["next_actions"]:
        parts.append("<h3>會議後的待辦（含負責角色）</h3>")
        parts.append(
            _table(
                ["類型", "對象", "要做的事", "負責角色"],
                [
                    [
                        _e(item.get("kind_label") or item.get("kind")),
                        f"<code>{_e(item.get('target'))}</code>",
                        _e(item.get("action")),
                        _e(item.get("responsible_role")),
                    ]
                    for item in section["next_actions"]
                ],
            )
        )
    return "".join(parts)


def _render_envelope(section: dict[str, Any]) -> str:
    area = section["area"]
    inputs = section["inputs"]
    parts = [f'<p class="scenario">假設情境（scenario: {_e(section["scenario"])}）—— {_e(section["warnings"][0])}</p>']
    parts.extend(f'<p class="warn">{_e(item)}</p>' for item in section["warnings"][1:])
    parts.append("<h3>使用的假設</h3>")
    parts.append(
        _table(
            ["項目", "值"],
            [
                ["基地面積", _e(inputs.get("parcel_area_sqm"))],
                ["建蔽率", _e(inputs.get("building_coverage_ratio"))],
                ["容積率", _e(inputs.get("floor_area_ratio"))],
                ["面寬", _e(inputs.get("frontage_mm"))],
                ["深度", _e(inputs.get("depth_mm"))],
                ["四邊退縮", _e(inputs.get("setback_mm"))],
            ],
        )
    )
    parts.append("<h3>面積帶</h3>")
    parts.append(
        _table(
            ["項目", "值"],
            [
                ["建蔽率允許建築面積", f"{_e(area.get('legal_footprint_sqm'))} m²"],
                ["退縮後幾何可建面積", f"{_e(area.get('geometric_footprint_sqm'))} m²"],
                ["每層建築面積（取小值）", f"{_e(area.get('effective_footprint_sqm'))} m²"],
                ["限制來源", _e(area.get("binding_constraint"))],
                ["可用深度", f"{_e(area.get('working_depth_mm'))} mm（{_e(area.get('working_depth_basis'))}）"],
                ["3 層總樓地板", f"{_e(area.get('total_floor_sqm_at_storeys'))} m²"],
                ["容積率允許總樓地板", f"{_e(area.get('legal_total_floor_sqm'))} m²"],
            ],
        )
    )
    parts.append(
        f"<h3>核心功能容量檢查｜整體：{_badge(section['overall_verdict'], section['overall_verdict_label'])}</h3>"
    )
    parts.append(
        _table(
            ["檢查", "棟", "需要", "結論", "說明"],
            [
                [
                    _e(item.get("label")),
                    _e(item.get("building")),
                    _e(item.get("required")),
                    _badge(item.get("verdict"), VERDICT_TEXT.get(item.get("verdict"), item.get("verdict"))),
                    _e(item.get("reason")),
                ]
                for item in section["checks"]
            ],
        )
    )
    return "".join(parts)


VERDICT_TEXT = {"fits": "放得下", "tight": "勉強", "does_not_fit": "放不下", "unknown": "無法判斷"}


def _render_brief(section: dict[str, Any]) -> str:
    summary = section["summary"]
    status = summary.get("status_counts") or {}
    parts = [
        _table(
            ["項目", "數量"],
            [
                ["需求總數", _e(summary.get("requirements"))],
                ["已確認 / 待決定 / 已淘汰", f"{_e(status.get('confirmed'))} / {_e(status.get('candidate'))} / {_e(status.get('rejected'))}"],
                ["已確認的 must", _e(summary.get("confirmed_must"))],
                ["空間關係規則", _e(summary.get("relationships"))],
            ],
        )
    ]
    if section["relationships"]:
        parts.append("<h3>空間關係規則（會鎖住格局的硬條件）</h3>")
        parts.append(
            _table(
                ["棟", "規則", "說明", "狀態"],
                [
                    [
                        _e(item.get("building_id")),
                        _e(item.get("type_label")),
                        _e(item.get("rationale") or item.get("description")),
                        _e(item.get("status_label")),
                    ]
                    for item in section["relationships"]
                ],
            )
        )
    if section["physical_items"]:
        parts.append("<h3>既有大型實物</h3>")
        parts.append(
            _table(
                ["物件", "棟／層", "目前採用尺寸 (mm)", "尺寸來源"],
                [
                    [
                        _e(item.get("label")),
                        f"{_e(item.get('building_id'))} / {_e(item.get('floor_id'))}",
                        _e(
                            "×".join(
                                str(int(value))
                                for value in (
                                    (item.get("active_dimensions_mm") or {}).get("width_mm"),
                                    (item.get("active_dimensions_mm") or {}).get("depth_mm"),
                                    (item.get("active_dimensions_mm") or {}).get("height_mm"),
                                )
                                if value
                            )
                        ),
                        _e(item.get("dimension_source_label")),
                    ]
                    for item in section["physical_items"]
                ],
            )
        )
        if section.get("physical_items_policy"):
            parts.append(f'<p class="meta">{_e(section["physical_items_policy"])}</p>')
    for group in section["open_questions"]:
        questions = group.get("questions") or []
        if not questions:
            continue
        parts.append(f"<h3>{_e(group.get('building_id'))} 棟 · {_e(group.get('role'))}：待屋主決定 {len(questions)} 題</h3><ol>")
        parts.extend(f"<li>{_e(item.get('text'))}</li>" for item in questions)
        parts.append("</ol>")
    return "".join(parts)


def _render_blockers(section: dict[str, Any]) -> str:
    readiness = section["readiness"]
    gate = section["gate"]
    parts = [
        f'<p class="meta">到期項目完成度 {_e(readiness.get("percent"))}%'
        f'｜目前阻擋 {_e(gate.get("active_blockers"))} 項'
        f'｜可否進入下一階段：{_e("可以" if gate.get("eligible_for_next_phase") else "不可")}</p>'
    ]
    if section["blockers"]:
        parts.append(
            _table(
                ["階段", "項目", "狀態", "負責角色", "下一步"],
                [
                    [
                        f"<code>{_e(item.get('phase'))}</code>",
                        _e(item.get("title")),
                        _e(item.get("status_label")),
                        _e(item.get("responsible_role")),
                        _e(item.get("next_action")),
                    ]
                    for item in section["blockers"]
                ],
            )
        )
    else:
        parts.append("<p>目前沒有到期的阻擋項目。</p>")
    return "".join(parts)


def _render_handoff(section: dict[str, Any]) -> str:
    parts = [
        f'<p class="meta">版次 <code>{_e(section.get("revision"))}</code>'
        f'｜{_e(section.get("label"))}｜登錄於 <code>{_e(section.get("root"))}</code></p>',
        "<p>未來建築師交圖時，希望收到：</p><ul>",
    ]
    parts.extend(f"<li>{_e(item)}</li>" for item in section["expectations"])
    parts.append("</ul>")
    return "".join(parts)


def _render_questions(section: dict[str, Any]) -> str:
    parts = []
    for item in section["questions"]:
        parts.append(
            f'<div class="q"><p class="ask">Q{item["number"]}. {_e(item["text"])}</p>'
            f'<p class="meta">為什麼要問：{_e(item["why"])}</p>'
            f'<p class="meta">答案寫回：<code>{_e(item["writes_back"])}</code></p>'
            f'<div class="answer">建築師回答（現場填寫）</div></div>'
        )
    return "".join(parts)


def meeting_pack_html(pack: dict[str, Any]) -> str:
    project = pack["project"]
    parts = [
        '<!doctype html>\n<html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>建築師開會包：{_e(project['name'])}</title><style>{PACK_CSS}</style></head><body><main>",
        f"<h1>建築師開會包<br>{_e(project['name'])}</h1>",
        f'<p class="meta">對象：建築師（選地可行性諮詢）｜產生時間：{_e(pack["generated_at"])}'
        f'｜階段：<code>{_e(project["stage"])}</code>｜開會包雜湊：<code>{_e(pack["pack_hash"])}</code></p>',
    ]
    parts.extend(f'<p class="warn" role="note">⚠ {_e(item)}</p>' for item in pack["warnings"])
    parts.append('<nav class="toc"><strong>本包內容</strong><ol>')
    for section in pack["sections"]:
        mark = "" if section["available"] else "（尚未產生）"
        parts.append(f'<li><a href="#s{section["number"]}">{_e(section["title"])}</a>{mark}</li>')
    parts.append("</ol></nav>")
    parts.extend(_render_section(section) for section in pack["sections"])

    parts.append('<h2>資料來源與雜湊</h2>')
    parts.append(
        _table(
            ["檔案", "用途", "產生方式", "SHA-256"],
            [
                [
                    f"<code>{_e(item['path'])}</code>",
                    _e(item["role"]),
                    f"<code>{_e(item['produced_by'])}</code>" if item["produced_by"] else "—",
                    f"<code>{_e(item['sha256'])}</code>" if item["sha256"] else "<strong>檔案不存在</strong>",
                ]
                for item in pack["sources"]
            ],
        )
    )
    parts.append(
        f'<footer>開會包雜湊 <code>{_e(pack["pack_hash"])}</code>。{_e(PACK_WARNING)}</footer></main></body></html>\n'
    )
    return "".join(parts)


def meeting_pack_markdown(pack: dict[str, Any]) -> str:
    lines = [
        "# 建築師開會包",
        "",
        f"- 專案：{pack['project']['name']}（階段 `{pack['project']['stage']}`）",
        "- 對象：建築師（選地可行性諮詢）",
        f"- 產生時間：{pack['generated_at']}",
        f"- 開會包雜湊：`{pack['pack_hash']}`",
        "",
    ]
    lines.extend(f"> ⚠ {item}" for item in pack["warnings"])
    lines.extend(["", "## 內容", ""])
    for section in pack["sections"]:
        mark = "" if section["available"] else "（尚未產生）"
        lines.append(f"{section['number']}. {section['title']}{mark}")
    if pack["missing_sections"]:
        lines.extend(["", f"**尚未產生的分節：{'、'.join(pack['missing_sections'])}**", ""])
    lines.extend(["", "## 本次會議要拿到的答案", ""])
    for item in MEETING_QUESTIONS:
        lines.append(f"{item['number']}. {item['text']}")
        lines.append(f"   - 為什麼要問：{item['why']}")
        lines.append(f"   - 答案寫回：`{item['writes_back']}`")
    planning = next((s for s in pack["sections"] if s["id"] == "planning"), None)
    if planning and planning["available"]:
        lines.extend(["", "## 當期防漏項待決策", "", "[完整情境／驗收總表](../../risk-review.html)", ""])
        lines.extend(f"- {i['id']}：{i['question']}（{i['responsible_role']}）" for i in planning["open_decisions"])
    lines.extend(["", "## 資料來源與雜湊", "", "| 檔案 | 用途 | 產生方式 | SHA-256 |", "|---|---|---|---|"])
    for item in pack["sources"]:
        digest = f"`{item['sha256']}`" if item["sha256"] else "**檔案不存在**"
        lines.append(f"| `{item['path']}` | {item['role']} | `{item['produced_by']}` | {digest} |")
    lines.append("")
    from house_design.owner_workspace import records_markdown

    return "\n".join(lines) + records_markdown(planning.get("owner_records", {}) if planning and planning.get("available") else {})


def write_meeting_pack(
    pack: dict[str, Any], output_root: Path = PREDESIGN_OUTPUT_ROOT
) -> dict[str, Path]:
    directory = output_root / "meeting-pack" / pack["audience"]
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "html": directory / "index.html",
        "markdown": directory / "index.md",
        "json": directory / "pack.json",
    }
    from house_design.owner_workspace import tool_links

    paths["html"].write_text(tool_links(meeting_pack_html(pack), output_root, prefix="../../"), encoding="utf-8", newline="\n")
    paths["markdown"].write_text(meeting_pack_markdown(pack), encoding="utf-8", newline="\n")
    from house_design.contracts import write_json  # local: keeps the write helpers together at call site

    write_json(paths["json"], pack)
    return paths

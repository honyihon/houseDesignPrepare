"""Hypothetical buildable-envelope scenarios for the land-search conversation.

Thirty-two ping is a search target for parcel area, not a permitted footprint.
This module answers the question the owner actually has to ask an architect -
"if a parcel had this coverage ratio, this frontage and this setback, would the
three buildings still work?" - while refusing to pretend the answer is a
regulatory finding.

Three rules hold everywhere in here:

* every output carries ``scenario: "hypothetical"`` and the warning text, so a
  printed page can never be mistaken for a feasibility opinion;
* the verdicts are ``fits`` / ``tight`` / ``does_not_fit`` / ``unknown`` - this
  module never emits ``pass``;
* a dimension nobody has established stays ``unknown`` and turns into a
  question for the architect, instead of being filled with a plausible number.

Only checks with a real derived number behind them are evaluated: the garage
comes from ``garage_min_bay_mm()`` in ``scripts/lib/plan_geometry.py``, the
palanquin from ``inputs/physical-items.json``, the wheelchair turning circle
from ``inputs/site.json``. Everything else is reported as an open question.
"""

from __future__ import annotations

import html
import math
import sys
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
from house_design.intake import is_known
from house_design.physical_items import PHYSICAL_ITEMS_PATH, active_dimensions, validate_physical_items
from house_design.sites import fact_evidence_issue

ENVELOPE_SCHEMA = "house-envelope-scenario-v1"
PROJECT_PATH = ROOT / "inputs/project.json"
SITE_CRITERIA_PATH = ROOT / "inputs/site-criteria.json"
STANDARDS_PATH = ROOT / "scripts/config/residential_defaults_tw.json"
PARAMETRIC_SITE_PATH = ROOT / "inputs/site.json"
PREDESIGN_OUTPUT_ROOT = ROOT / "structured/predesign"

SQM_PER_PING = 3.305785
HABITABLE_STOREYS = 3

SCENARIO_WARNING = (
    "假設情境試算，非法規結論；實際可建量體必須由高雄市執業建築師依基地、建築線、法定空地與各項法規個案認定。"
)
INPUT_WARNING = (
    "本頁每一個輸入值都是假設或未經查驗的候選地資料；任何一項改變，結論都會改變。"
    "請把它當成向建築師提問的素材，不要當成答案。"
)
SIMPLIFICATION_WARNING = (
    "幾何極度簡化：矩形基地、四邊等值退縮、不含法定空地位置、騎樓、地界線斜率、"
    "防火間隔與屋突計算。真實基地幾乎不會這麼乾淨。"
)

VERDICTS = ("fits", "tight", "does_not_fit", "unknown")
VERDICT_LABELS = {
    "fits": "放得下",
    "tight": "勉強，需設計驗證",
    "does_not_fit": "放不下",
    "unknown": "無法判斷",
}
TIGHT_MARGIN_MM = 300


def _plan_geometry() -> Any:
    """Load the parametric geometry helpers without duplicating their numbers.

    ``scripts/`` is not an installed package, so this repeats the sys.path hop
    ``scripts/generate_parametric_plan.py`` already uses. The point is that the
    garage minimum has exactly one definition in the repository.
    """

    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from lib import plan_geometry  # noqa: PLC0415 - see docstring

    return plan_geometry


def _verdict(available_mm: float | None, required_mm: float | None) -> tuple[str, str]:
    if available_mm is None or required_mm is None:
        return "unknown", "缺少可比較的尺寸"
    margin = available_mm - required_mm
    if margin < 0:
        return "does_not_fit", f"短少 {abs(margin):.0f} mm（可用 {available_mm:.0f}，需要 {required_mm:.0f}）"
    if margin < TIGHT_MARGIN_MM:
        return "tight", f"僅餘 {margin:.0f} mm（可用 {available_mm:.0f}，需要 {required_mm:.0f}）"
    return "fits", f"餘裕 {margin:.0f} mm（可用 {available_mm:.0f}，需要 {required_mm:.0f}）"


def _worst(verdicts: list[str]) -> str:
    for key in ("does_not_fit", "unknown", "tight"):
        if key in verdicts:
            return key
    return "fits" if verdicts else "unknown"


def _official(facts: dict[str, Any], key: str) -> Any:
    """Read one official fact, treating an explicit unknown as no value at all."""

    cell = facts.get(key)
    if fact_evidence_issue(cell):
        return None
    value = cell.get("value")
    return value if is_known(value) else None


def _candidate_inputs(project: dict[str, Any], candidate_id: str, parcel_id: str | None = None) -> dict[str, Any]:
    search = project.get("site_search") or {}
    for item in search.get("candidate_sites") or []:
        if not isinstance(item, dict) or str(item.get("candidate_id")) != candidate_id:
            continue
        facts = item.get("official_facts") or {}
        parcels = item.get("parcels") or []
        matches = [p for p in parcels if isinstance(p, dict) and p.get("parcel_id") == parcel_id]
        if parcel_id and len(matches) != 1:
            raise ContractError(f"Candidate {candidate_id} requires one unique parcel named {parcel_id}")
        parcel = matches[0] if matches else {}
        if parcel and parcel.get("building_id") not in {"A", "B", "C"}:
            raise ContractError("Selected parcel must map to building A, B or C")
        facts = {**facts, **(parcel.get("official_facts") or {})}
        return {
            "candidate_id": candidate_id,
            "label": item.get("label"),
            "building_coverage_ratio": _official(facts, "building_coverage_ratio"),
            "floor_area_ratio": _official(facts, "floor_area_ratio"),
            "setback_mm": None,
            "parcel_id": parcel_id,
            "building_id": parcel.get("building_id"),
            "frontage_mm": _official(parcel, "frontage_mm"),
            "depth_mm": _official(parcel, "depth_mm"),
            "parcel_area_sqm": _official(parcel, "area_sqm"),
            "parcel_area_source": "逐筆基地 area_sqm；缺查核證據維持未知，不採三筆合計或選地目標",
            "provenance": "candidate_checked_inputs_hypothetical_model",
            "input_sources": {
                key: cell.get("source") if isinstance(cell, dict) and fact_evidence_issue(cell) is None else None
                for key, cell in {
                    "building_coverage_ratio": facts.get("building_coverage_ratio"),
                    "floor_area_ratio": facts.get("floor_area_ratio"),
                    "frontage_mm": parcel.get("frontage_mm"),
                    "depth_mm": parcel.get("depth_mm"),
                    "parcel_area_sqm": parcel.get("area_sqm"),
                }.items()
            },
            "scope_note": "僅試算指定單筆基地，不代表其他棟成立。"
            if parcel
            else "未指定單筆基地，逐筆幾何保持未知；不得採總面積或目標面積替代。",
        }
    raise ContractError(f"No candidate site named {candidate_id}")


def _resolve_inputs(
    project: dict[str, Any],
    *,
    candidate_id: str | None,
    parcel_id: str | None,
    bcr: float | None,
    far: float | None,
    frontage_mm: float | None,
    depth_mm: float | None,
    setback_mm: float | None,
    parcel_area_sqm: float | None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "candidate_id": None,
        "label": None,
        "building_coverage_ratio": None,
        "floor_area_ratio": None,
        "setback_mm": None,
        "frontage_mm": None,
        "depth_mm": None,
        "parcel_area_sqm": None,
        "provenance": "assumed",
    }
    if candidate_id:
        base.update(_candidate_inputs(project, candidate_id, parcel_id))
    elif parcel_id:
        raise ContractError("--parcel requires --candidate")

    overrides = {
        "building_coverage_ratio": bcr,
        "floor_area_ratio": far,
        "frontage_mm": frontage_mm,
        "depth_mm": depth_mm,
        "setback_mm": setback_mm,
        "parcel_area_sqm": parcel_area_sqm,
    }
    assumed_keys = []
    for key, value in overrides.items():
        if value is not None:
            base[key] = value
            assumed_keys.append(key)
            base.setdefault("input_sources", {})[key] = {"type": "explicit_assumption", "value": value}
            if key == "parcel_area_sqm":
                base["parcel_area_source"] = "explicit_assumption（明確指定的單筆假設面積，非地籍事實）"
    if candidate_id and assumed_keys:
        base["provenance"] = "candidate_with_explicit_assumptions"

    if base["parcel_area_sqm"] is None and not candidate_id:
        target = (project.get("site_search") or {}).get("target_scenario") or {}
        ping = target.get("target_area_ping_each")
        if isinstance(ping, (int, float)) and ping > 0:
            base["parcel_area_sqm"] = round(float(ping) * SQM_PER_PING, 2)
            base["parcel_area_source"] = "site_search.target_scenario.target_area_ping_each（選地目標，非已取得基地）"
            assumed_keys.append("parcel_area_sqm")
    base["assumed_fields"] = assumed_keys
    for key in (
        "parcel_area_sqm",
        "frontage_mm",
        "depth_mm",
        "building_coverage_ratio",
        "floor_area_ratio",
        "setback_mm",
    ):
        value = base[key]
        if value is not None and (not _num(value) or value < 0 or (key != "setback_mm" and value == 0)):
            raise ContractError(f"{key} must be a finite positive number (setback may be zero)")
    if base["building_coverage_ratio"] is not None and base["building_coverage_ratio"] > 1:
        raise ContractError("building_coverage_ratio must be a ratio between 0 and 1, not a percentage")
    return base


def _palanquin(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"provided": False}
    payload = read_json(path)
    for item in payload.get("items") or []:
        if not isinstance(item, dict) or item.get("category") != "ceremonial_equipment":
            continue
        planning = item.get("planning_dimensions") or {}
        transport = item.get("transport") or {}
        return {
            "provided": True,
            "id": item.get("id"),
            "label": item.get("label"),
            "width_mm": planning.get("width_mm"),
            "depth_mm": planning.get("depth_mm"),
            "door_clear_target_mm": transport.get("door_clear_target_mm"),
            "storage_measured": not validate_physical_items(payload) and active_dimensions(item)[1] == "measured",
            "transport_measured": (
                isinstance(transport.get("assembled_dimensions"), dict)
                and all(
                    _num(transport["assembled_dimensions"].get(axis)) and transport["assembled_dimensions"][axis] > 0
                    for axis in ("width_mm", "depth_mm", "height_mm")
                )
                and fact_evidence_issue(transport.get("assembled_measurement")) is None
                and (transport.get("assembled_measurement") or {}).get("value") == "yes"
            ),
            "route_rehearsed": (
                fact_evidence_issue(transport.get("route_rehearsal")) is None
                and (transport.get("route_rehearsal") or {}).get("value") == "yes"
            ),
        }
    return {"provided": False}


def build_envelope_scenario(
    *,
    project_path: Path = PROJECT_PATH,
    physical_items_path: Path = PHYSICAL_ITEMS_PATH,
    standards_path: Path = STANDARDS_PATH,
    parametric_site_path: Path = PARAMETRIC_SITE_PATH,
    candidate_id: str | None = None,
    parcel_id: str | None = None,
    bcr: float | None = None,
    far: float | None = None,
    frontage_mm: float | None = None,
    depth_mm: float | None = None,
    setback_mm: float | None = None,
    parcel_area_sqm: float | None = None,
    storeys: int = HABITABLE_STOREYS,
) -> dict[str, Any]:
    if not isinstance(storeys, int) or isinstance(storeys, bool) or storeys < 1:
        raise ContractError("storeys must be a positive integer")
    project = read_json(project_path)
    inputs = _resolve_inputs(
        project,
        candidate_id=candidate_id,
        parcel_id=parcel_id,
        bcr=bcr,
        far=far,
        frontage_mm=frontage_mm,
        depth_mm=depth_mm,
        setback_mm=setback_mm,
        parcel_area_sqm=parcel_area_sqm,
    )
    standards = read_json(standards_path) if standards_path.is_file() else {}
    geometry_defaults = standards.get("geometry") or {}
    wall = geometry_defaults.get("wall_thickness_mm") or {}
    exterior_wall_mm = float(wall.get("exterior") or 200)

    area = _area_bands(inputs, storeys)
    clearances = _clear_dimensions(area, exterior_wall_mm)
    checks = _core_function_checks(
        clearances,
        palanquin=_palanquin(physical_items_path),
        parametric_site=read_json(parametric_site_path) if parametric_site_path.is_file() else {},
        plan_geometry=_plan_geometry(),
        standards=standards,
    )
    if inputs.get("building_id"):
        building = inputs["building_id"]
        checks = [c for c in checks if c["building"] in {building, "A／B／C"}]
        for check in checks:
            check["building"] = building

    report: dict[str, Any] = {
        "schema": ENVELOPE_SCHEMA,
        "scenario": "hypothetical",
        "generated_at": utc_now(),
        "project": {
            "project_id": project.get("project_id"),
            "name": project.get("name"),
            "stage": project.get("stage"),
        },
        "warnings": [
            SCENARIO_WARNING,
            INPUT_WARNING,
            SIMPLIFICATION_WARNING,
            inputs.get("scope_note") or "選地前共用的假設單筆基地情境，不代表 A／B／C 均已驗證。",
        ],
        "inputs": inputs,
        "storeys": {
            "habitable": storeys,
            "roof": "RF 是屋頂層（女兒牆、樓梯間、水塔、熱泵、太陽能），不是第四層。",
        },
        "area": area,
        "clearances": clearances,
        "core_function_checks": checks,
        "overall_verdict": _worst([item["verdict"] for item in checks]),
        "open_questions": _open_questions(checks, inputs),
        "sources": [
            _source(project_path, "選地目標與候選地"),
            _source(standards_path, "牆厚與車輛淨空基準"),
            _source(physical_items_path, "武轎規劃量體與目標門淨寬"),
            _source(parametric_site_path, "輪椅迴轉圈檢查值（歷史參數化情境）"),
        ],
    }
    report["overall_verdict_label"] = VERDICT_LABELS[report["overall_verdict"]]
    report["scenario_hash"] = stable_hash({key: value for key, value in report.items() if key != "generated_at"})
    _assert_no_pass(report)
    return report


def _area_bands(inputs: dict[str, Any], storeys: int) -> dict[str, Any]:
    parcel = inputs.get("parcel_area_sqm")
    bcr = inputs.get("building_coverage_ratio")
    far = inputs.get("floor_area_ratio")
    frontage = inputs.get("frontage_mm")
    depth = inputs.get("depth_mm")
    setback = inputs.get("setback_mm")

    legal_footprint = round(parcel * bcr, 2) if _num(parcel) and _num(bcr) else None
    legal_total = round(parcel * far, 2) if _num(parcel) and _num(far) else None

    net_frontage = net_depth = geometric_footprint = None
    if _num(frontage) and _num(setback):
        net_frontage = max(0.0, float(frontage) - 2 * float(setback))
    elif _num(frontage):
        net_frontage = float(frontage)
    if _num(depth) and _num(setback):
        net_depth = max(0.0, float(depth) - 2 * float(setback))
    elif _num(depth):
        net_depth = float(depth)
    if net_frontage is not None and net_depth is not None:
        geometric_footprint = round(net_frontage * net_depth / 1_000_000, 2)

    binding = None
    binding_caveat = ""
    footprint = None
    if legal_footprint is not None and geometric_footprint is not None:
        footprint = min(legal_footprint, geometric_footprint)
        binding = "建蔽率" if legal_footprint <= geometric_footprint else "退縮後幾何"
    elif legal_footprint is not None:
        footprint = legal_footprint
        binding = "建蔽率"
        binding_caveat = "未給面寬或深度，未檢查基地幾何是否放得下"
    elif geometric_footprint is not None:
        footprint = geometric_footprint
        binding = "退縮後幾何"
        binding_caveat = "未給建蔽率，未檢查法規建築面積上限"

    total_floor = round(footprint * storeys, 2) if footprint is not None else None
    far_storeys = None
    if legal_total is not None and footprint:
        far_storeys = round(legal_total / footprint, 2)

    # When coverage - not the parcel - is what limits the footprint, the usable
    # depth is shorter than the parcel depth. Stating that implied depth is what
    # makes the garage check answerable at all; it is labelled as derived so the
    # architect can see it was computed, not surveyed.
    working_depth = net_depth
    depth_basis = "退縮後基地深度"
    if footprint is not None and net_frontage:
        implied_depth = footprint * 1_000_000 / net_frontage
        if working_depth is None or implied_depth < working_depth:
            working_depth = implied_depth
            depth_basis = f"由{binding}反推：建築面積 ÷ 退縮後面寬，假設量體佔滿面寬"

    return {
        "parcel_area_sqm": parcel,
        "parcel_area_ping": round(parcel / SQM_PER_PING, 2) if _num(parcel) else None,
        "legal_footprint_sqm": legal_footprint,
        "legal_total_floor_sqm": legal_total,
        "net_frontage_mm": net_frontage,
        "net_depth_mm": net_depth,
        "working_depth_mm": round(working_depth, 1) if working_depth is not None else None,
        "working_depth_basis": depth_basis if working_depth is not None else "未知",
        "geometric_footprint_sqm": geometric_footprint,
        "effective_footprint_sqm": footprint,
        "effective_footprint_ping": round(footprint / SQM_PER_PING, 2) if footprint is not None else None,
        "binding_constraint": binding,
        "binding_caveat": binding_caveat,
        "total_floor_sqm_at_storeys": total_floor,
        "storeys_allowed_by_far": far_storeys,
        "far_note": (
            f"容積率允許約 {far_storeys} 層的此面積；超過 {storeys} 層時須另行檢討"
            if far_storeys is not None
            else "未給容積率，無法檢查總樓地板上限"
        ),
    }


def _clear_dimensions(area: dict[str, Any], exterior_wall_mm: float) -> dict[str, Any]:
    net_frontage = area.get("net_frontage_mm")
    working_depth = area.get("working_depth_mm")
    clear_width = net_frontage - 2 * exterior_wall_mm if net_frontage is not None else None
    clear_depth = working_depth - 2 * exterior_wall_mm if working_depth is not None else None
    return {
        "exterior_wall_mm": exterior_wall_mm,
        "net_frontage_mm": net_frontage,
        "working_depth_mm": working_depth,
        "working_depth_basis": area.get("working_depth_basis"),
        "working_depth_derived": str(area.get("working_depth_basis") or "").startswith("由"),
        "interior_clear_width_mm": round(clear_width, 1) if clear_width is not None else None,
        "interior_clear_depth_mm": round(clear_depth, 1) if clear_depth is not None else None,
        "note": "室內淨尺寸＝可用量體扣兩道外牆；未扣內隔牆、樓梯、管道間與裝修完成面，"
        "也未扣樓梯與車庫以外的任何機能，因此這是樂觀上限。",
    }


def _core_function_checks(
    clearances: dict[str, Any],
    *,
    palanquin: dict[str, Any],
    parametric_site: dict[str, Any],
    plan_geometry: Any,
    standards: dict[str, Any],
) -> list[dict[str, Any]]:
    width = clearances["interior_clear_width_mm"]
    depth = clearances["interior_clear_depth_mm"]
    depth_note = "（深度為推算值，見面積帶）" if clearances.get("working_depth_derived") else ""
    checks: list[dict[str, Any]] = []

    bay = plan_geometry.garage_min_bay_mm(standards, 1)
    width_verdict, width_reason = _verdict(width, float(bay["width"]))
    depth_verdict, depth_reason = _verdict(depth, float(bay["depth"]))
    checks.append(
        {
            "id": "ENV-GARAGE-1BAY",
            "building": "A／B／C",
            "label": "室內單車位車庫（休旅車＋壁掛充電樁）",
            "required": f"淨 {bay['width']} × {bay['depth']} mm",
            "verdict": _worst([width_verdict, depth_verdict]),
            "reason": f"寬度：{width_reason}；深度：{depth_reason}{depth_note}",
            "basis": "scripts/lib/plan_geometry.py garage_min_bay_mm()，由 residential_defaults_tw.json 的 vehicle 推導",
            "basis_kind": "derived",
        }
    )

    bay2 = plan_geometry.garage_min_bay_mm(standards, 2)
    two_width_verdict, two_width_reason = _verdict(width, float(bay2["width"]))
    checks.append(
        {
            "id": "ENV-GARAGE-2BAY",
            "building": "A／B／C",
            "label": "室內雙車位車庫",
            "required": f"淨 {bay2['width']} × {bay2['depth']} mm",
            "verdict": _worst([two_width_verdict, depth_verdict]),
            "reason": f"寬度：{two_width_reason}；深度：{depth_reason}{depth_note}",
            "basis": "同上，bays=2",
            "basis_kind": "derived",
        }
    )

    door_target = palanquin.get("door_clear_target_mm") if palanquin.get("provided") else None
    transport_verdict, transport_reason = _verdict(width, float(door_target) if _num(door_target) else None)
    checks.append(
        {
            "id": "ENV-PALANQUIN-PATH",
            "building": "B",
            "label": "武轎搬運路徑淨寬",
            "required": f"淨寬 {door_target} mm" if door_target else "未知",
            "verdict": transport_verdict,
            "reason": transport_reason
            + (
                "；此為規劃目標值，搬運外廓尚未完整實測並附查核證據，抬桿與轉彎需求未確認（收納實測不能替代）"
                if palanquin.get("provided") and not palanquin.get("transport_measured")
                else ""
            )
            + ("；尚未完成有證據的實際路徑搬運演練" if not palanquin.get("route_rehearsed") else "")
            + "；僅比較量體寬度與規劃門寬，不是門位、轉角、淨高或搬運安全核可",
            "storage_measured": bool(palanquin.get("storage_measured")),
            "transport_measured": bool(palanquin.get("transport_measured")),
            "route_rehearsed": bool(palanquin.get("route_rehearsed")),
            "basis": "inputs/physical-items.json transport.door_clear_target_mm",
            "basis_kind": "planning_value",
        }
    )

    turn = (parametric_site.get("corridor") or {}).get("wheelchair_turn_mm")
    turn_verdict, turn_reason = _verdict(width, float(turn) if _num(turn) else None)
    checks.append(
        {
            "id": "ENV-WHEELCHAIR-TURN",
            "building": "A／B／C",
            "label": "關鍵節點輪椅迴轉圈",
            "required": f"淨短邊 {turn} mm" if turn else "未知",
            "verdict": turn_verdict,
            "reason": turn_reason + "；只檢查量體短邊，未檢查個別房間",
            "basis": "inputs/site.json corridor.wheelchair_turn_mm",
            "basis_kind": "planning_value",
        }
    )

    # Deliberately unresolved: nobody has established these minimums, so they
    # stay unknown and become questions for the architect instead of numbers
    # this module invented.
    for identifier, building, label, question in (
        (
            "ENV-GROUND-FLOOR-LIFE",
            "A",
            "1F 完整全齡生活圈最小合理面積",
            "全齡無障礙基準下，1F 要同時容納出入、衛浴、起居與照護動作，最小合理面積是多少？",
        ),
        (
            "ENV-SHRINE-STACK",
            "B",
            "神明廳與武轎儲藏的上下疊圖關係",
            "神明廳位置、背牆、排水立管與武轎儲藏的上下對位，在結構與法規上有哪些早期限制？",
        ),
        (
            "ENV-ELDER-SUITE",
            "C",
            "孝親房＋無障礙衛浴最小合理面積",
            "含床、衣櫃、輪椅迴轉、淋浴椅與扶手後，孝親房與無障礙衛浴的最小合理面積是多少？",
        ),
    ):
        checks.append(
            {
                "id": identifier,
                "building": building,
                "label": label,
                "required": "未知",
                "verdict": "unknown",
                "reason": "沒有可引用的最小面積依據；本模組不自行發明數字。",
                "basis": "待建築師提供",
                "basis_kind": "open_question",
                "question": question,
            }
        )
    return checks


def _open_questions(checks: list[dict[str, Any]], inputs: dict[str, Any]) -> list[str]:
    questions = [item["question"] for item in checks if item.get("question")]
    missing = [
        key
        for key in (
            "parcel_area_sqm",
            "building_coverage_ratio",
            "floor_area_ratio",
            "frontage_mm",
            "depth_mm",
            "setback_mm",
        )
        if inputs.get(key) is None
    ]
    if missing:
        questions.insert(0, f"以下輸入尚未給值，結論因此不完整：{'、'.join(missing)}")
    return questions


def _assert_no_pass(report: dict[str, Any]) -> None:
    """Fail loudly rather than ship a scenario that reads like an approval."""

    for check in report["core_function_checks"]:
        if check["verdict"] not in VERDICTS:
            raise ContractError(f"Envelope verdicts must be one of {VERDICTS}; got {check['verdict']!r}")
    if report["scenario"] != "hypothetical":
        raise ContractError("Envelope reports must stay marked hypothetical")


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _source(path: Path, role: str) -> dict[str, Any]:
    exists = path.is_file()
    return {
        "path": relative_to_root(path),
        "role": role,
        "exists": exists,
        "sha256": sha256_file(path) if exists else None,
    }


def _fmt(value: Any, unit: str = "") -> str:
    if value is None:
        return "未給值"
    if isinstance(value, float):
        return f"{value:g}{unit}"
    return f"{value}{unit}"


def envelope_markdown(report: dict[str, Any]) -> str:
    area = report["area"]
    inputs = report["inputs"]
    lines = [
        "# 可建量體假設情境試算",
        "",
        f"- 情境類型：**{report['scenario']}（假設情境）**",
        f"- 專案：{report['project']['name']}（階段 `{report['project']['stage']}`）",
        f"- 產生時間：{report['generated_at']}",
        f"- 情境雜湊：`{report['scenario_hash']}`",
        f"- 整體結論：**{report['overall_verdict_label']}**",
        "",
    ]
    lines.extend(f"> ⚠ {warning}" for warning in report["warnings"])
    lines.extend(
        [
            "",
            "## 一、輸入值",
            "",
            "| 項目 | 值 | 來源 |",
            "|---|---|---|",
            f"| 候選地 | {_fmt(inputs.get('label') or inputs.get('candidate_id'))} | {inputs['provenance']} |",
            f"| 單筆基地／棟別 | {_fmt(inputs.get('parcel_id'))}／{_fmt(inputs.get('building_id'))} | 單筆範圍，非三筆合計 |",
            f"| 基地面積 | {_fmt(inputs.get('parcel_area_sqm'), ' m²')} | "
            f"{inputs.get('parcel_area_source') or inputs['provenance']} |",
            f"| 建蔽率 | {_fmt(inputs.get('building_coverage_ratio'))} | {inputs['provenance']} |",
            f"| 容積率 | {_fmt(inputs.get('floor_area_ratio'))} | {inputs['provenance']} |",
            f"| 面寬 | {_fmt(inputs.get('frontage_mm'), ' mm')} | {inputs['provenance']} |",
            f"| 深度 | {_fmt(inputs.get('depth_mm'), ' mm')} | {inputs['provenance']} |",
            f"| 四邊退縮 | {_fmt(inputs.get('setback_mm'), ' mm')} | {inputs['provenance']} |",
            f"| 層數 | {report['storeys']['habitable']} 層＋RF | 屋主政策 |",
            "",
            f"> {report['storeys']['roof']}",
            "",
            "## 二、面積帶",
            "",
            "| 項目 | 值 |",
            "|---|---|",
            f"| 建蔽率允許建築面積 | {_fmt(area['legal_footprint_sqm'], ' m²')} |",
            f"| 退縮後幾何可建面積 | {_fmt(area['geometric_footprint_sqm'], ' m²')} |",
            f"| 取小值（每層建築面積） | {_fmt(area['effective_footprint_sqm'], ' m²')}"
            f"（約 {_fmt(area['effective_footprint_ping'], ' 坪')}） |",
            f"| 限制來源 | {_fmt(area['binding_constraint'])}"
            f"{'（' + area['binding_caveat'] + '）' if area['binding_caveat'] else ''} |",
            f"| 可用深度 | {_fmt(area['working_depth_mm'], ' mm')}（{area['working_depth_basis']}） |",
            f"| {report['storeys']['habitable']} 層總樓地板 | {_fmt(area['total_floor_sqm_at_storeys'], ' m²')} |",
            f"| 容積率允許總樓地板 | {_fmt(area['legal_total_floor_sqm'], ' m²')} |",
            "",
            f"> {area['far_note']}",
            "",
            "## 三、核心功能容量檢查",
            "",
            "| 檢查 | 棟 | 需要 | 結論 | 說明 | 依據 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for check in report["core_function_checks"]:
        lines.append(
            f"| {check['label']} | {check['building']} | {check['required']} "
            f"| **{VERDICT_LABELS[check['verdict']]}** | {check['reason']} | {check['basis']} |"
        )
    lines.extend(["", "## 四、要問建築師的問題", ""])
    lines.extend(f"{index}. {question}" for index, question in enumerate(report["open_questions"], start=1))
    lines.extend(["", "## 五、資料來源", "", "| 檔案 | 用途 | SHA-256 |", "|---|---|---|"])
    for source in report["sources"]:
        digest = f"`{source['sha256']}`" if source["sha256"] else "未提供"
        lines.append(f"| `{source['path']}` | {source['role']} | {digest} |")
    lines.append("")
    return "\n".join(lines)


ENVELOPE_CSS = (
    "body{font:16px/1.65 system-ui,sans-serif;color:#17212b;background:#fff;max-width:1000px;margin:32px auto;"
    "padding:0 20px;overflow-wrap:anywhere}h1,h2{line-height:1.25}h2{border-bottom:2px solid #d5dde5;padding-bottom:4px;margin-top:36px}"
    ".warn{border-left:5px solid #b45309;background:#fff7ed;padding:14px 16px;margin:8px 0}"
    ".scenario{border:3px solid #b91c1c;background:#fef2f2;padding:12px 16px;margin:12px 0;font-weight:700}"
    "table{border-collapse:collapse;width:100%}th,td{border:1px solid #b8c2cc;padding:8px;text-align:left;"
    "vertical-align:top}code{background:#eef2f6;padding:2px 5px;overflow-wrap:anywhere}.table-wrap{overflow-x:auto}"
    ".meta{color:#475569}.badge{display:inline-block;border-radius:999px;padding:0 8px;font-size:13px;"
    "border:1px solid #94a3b8}.v-fits{background:#dcfce7;border-color:#15803d}.v-tight{background:#fef9c3;"
    "border-color:#a16207}.v-does_not_fit{background:#fee2e2;border-color:#b91c1c}.v-unknown{background:#f1f5f9}"
    "footer{margin-top:40px;color:#475569;font-size:14px}"
    "@media print{body{margin:0;max-width:none}h2{break-after:avoid}}"
)


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def envelope_html(report: dict[str, Any]) -> str:
    area = report["area"]
    inputs = report["inputs"]
    parts = [
        '<!doctype html>\n<html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>可建量體假設情境：{_e(report['project']['name'])}</title><style>{ENVELOPE_CSS}</style></head><body>",
        f"<h1>可建量體假設情境試算<br>{_e(report['project']['name'])}</h1>",
        f'<p class="scenario" role="note">假設情境（scenario: {_e(report["scenario"])}）—— {_e(SCENARIO_WARNING)}</p>',
        *[f'<p class="warn" role="note">⚠ {_e(warning)}</p>' for warning in report["warnings"][1:]],
        f'<p class="meta">產生時間：{_e(report["generated_at"])}｜整體結論：'
        f'<span class="badge v-{_e(report["overall_verdict"])}">{_e(report["overall_verdict_label"])}</span>'
        f"｜情境雜湊：<code>{_e(report['scenario_hash'])}</code></p>",
        '<h2>一、輸入值</h2><div class="table-wrap"><table><thead><tr><th>項目</th><th>值</th><th>來源</th>'
        "</tr></thead><tbody>",
    ]
    rows = (
        ("候選地", _fmt(inputs.get("label") or inputs.get("candidate_id")), inputs["provenance"]),
        (
            "基地面積",
            _fmt(inputs.get("parcel_area_sqm"), " m²"),
            inputs.get("parcel_area_source") or inputs["provenance"],
        ),
        ("建蔽率", _fmt(inputs.get("building_coverage_ratio")), inputs["provenance"]),
        ("容積率", _fmt(inputs.get("floor_area_ratio")), inputs["provenance"]),
        ("面寬", _fmt(inputs.get("frontage_mm"), " mm"), inputs["provenance"]),
        ("深度", _fmt(inputs.get("depth_mm"), " mm"), inputs["provenance"]),
        ("四邊退縮", _fmt(inputs.get("setback_mm"), " mm"), inputs["provenance"]),
        ("層數", f"{report['storeys']['habitable']} 層＋RF", "屋主政策"),
    )
    parts.extend(
        f"<tr><td>{_e(label)}</td><td>{_e(value)}</td><td>{_e(source)}</td></tr>" for label, value, source in rows
    )
    parts.append(f'</tbody></table></div><p class="meta">{_e(report["storeys"]["roof"])}</p>')

    parts.append(
        '<h2>二、面積帶</h2><div class="table-wrap"><table><thead><tr><th>項目</th><th>值</th></tr></thead><tbody>'
    )
    area_rows = (
        ("建蔽率允許建築面積", _fmt(area["legal_footprint_sqm"], " m²")),
        ("退縮後幾何可建面積", _fmt(area["geometric_footprint_sqm"], " m²")),
        (
            "取小值（每層建築面積）",
            f"{_fmt(area['effective_footprint_sqm'], ' m²')}（約 {_fmt(area['effective_footprint_ping'], ' 坪')}）",
        ),
        (
            "限制來源",
            _fmt(area["binding_constraint"]) + (f"（{area['binding_caveat']}）" if area["binding_caveat"] else ""),
        ),
        ("可用深度", f"{_fmt(area['working_depth_mm'], ' mm')}（{area['working_depth_basis']}）"),
        (f"{report['storeys']['habitable']} 層總樓地板", _fmt(area["total_floor_sqm_at_storeys"], " m²")),
        ("容積率允許總樓地板", _fmt(area["legal_total_floor_sqm"], " m²")),
    )
    parts.extend(f"<tr><td>{_e(label)}</td><td>{_e(value)}</td></tr>" for label, value in area_rows)
    parts.append(f'</tbody></table></div><p class="meta">{_e(area["far_note"])}</p>')

    parts.append(
        '<h2>三、核心功能容量檢查</h2><div class="table-wrap"><table><thead><tr><th>檢查</th><th>棟</th>'
        "<th>需要</th><th>結論</th><th>說明</th><th>依據</th></tr></thead><tbody>"
    )
    for check in report["core_function_checks"]:
        parts.append(
            f"<tr><td>{_e(check['label'])}</td><td>{_e(check['building'])}</td><td>{_e(check['required'])}</td>"
            f'<td><span class="badge v-{_e(check["verdict"])}">{_e(VERDICT_LABELS[check["verdict"]])}</span></td>'
            f"<td>{_e(check['reason'])}</td><td>{_e(check['basis'])}</td></tr>"
        )
    parts.append("</tbody></table></div><h2>四、要問建築師的問題</h2><ol>")
    parts.extend(f"<li>{_e(question)}</li>" for question in report["open_questions"])
    parts.append(
        '</ol><h2>五、資料來源</h2><div class="table-wrap"><table><thead><tr><th>檔案</th><th>用途</th>'
        "<th>SHA-256</th></tr></thead><tbody>"
    )
    for source in report["sources"]:
        digest = f"<code>{_e(source['sha256'])}</code>" if source["sha256"] else "未提供"
        parts.append(
            f"<tr><td><code>{_e(source['path'])}</code></td><td>{_e(source['role'])}</td><td>{digest}</td></tr>"
        )
    parts.append(
        f"</tbody></table></div><footer>情境雜湊：<code>{_e(report['scenario_hash'])}</code>"
        f"｜{_e(SCENARIO_WARNING)}</footer></body></html>\n"
    )
    return "".join(parts)


def write_envelope_scenario(report: dict[str, Any], output_root: Path = PREDESIGN_OUTPUT_ROOT) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": output_root / "envelope.json",
        "markdown": output_root / "envelope.md",
        "html": output_root / "envelope.html",
    }
    write_json(paths["json"], report)
    paths["markdown"].write_text(envelope_markdown(report), encoding="utf-8", newline="\n")
    paths["html"].write_text(envelope_html(report), encoding="utf-8", newline="\n")
    return paths

"""Read-only directional budgets for a frozen bath, not a fit or care approval.

No scene, solver, network or parent generation. Added dimensions are hypothetical
worst-direction budget consumption, not manufactured-product measurements or a
replanned layout. A negative number rejects only that frozen coordinate trial.
"""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

from house_design.b32_rear_right import body, rect
from house_design.c_care_bath import component_box
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, utc_now

SOURCE = "inputs/c-care-bath-fit.json"
SCHEMA = "house-c-care-bath-fit-v1"
STATUS = "discussion-only-not-adopted"
BASE_REPORT = "structured/candidates/c-care-bath/review.json"
BASE_VIEWER = "structured/candidates/c-care-bath-3d.html"
BASE_INDEX = "structured/candidates/c-care-bath.html"
BASE_DETAIL = "structured/candidates/c-care-bath/c-bath-refined_transfer_detail.svg"
OUT = "structured/candidates/c-care-bath-fit"
CASE_IDS = ("nominal", "finish-5", "finish-10", "product-10", "position-5", "stop-20", "combined")
FIELDS = ("extra_finish_mm", "extra_jamb_each_mm", "extra_vanity_width_mm", "extra_vanity_depth_mm",
          "extra_folded_seat_projection_mm", "extra_leaf_length_mm", "relative_position_error_mm",
          "end_stop_allowance_mm", "extra_handle_clear_loss_total_mm")
WARNING = "公差／選品研究，未採用／專業未核。不改ABC、已驗收套衛HTML或3D；不是輪椅、救援、風水或施工核可。"


def validate_config(cfg):
    if (cfg.get("schema") != SCHEMA or cfg.get("revision") != 1 or cfg.get("status") != STATUS
            or not cfg.get("authorization") or cfg.get("base_report") != BASE_REPORT
            or cfg.get("base_viewer") != BASE_VIEWER or cfg.get("base_option") != "c-bath-refined"
            or cfg.get("base_state") != "transfer" or cfg.get("assumed_inset_each_face_mm") != 115
            or cfg.get("required_door_clear_mm") != 900 or cfg.get("optional_discussion_margin_mm") != 30
            or set(cfg.get("professional_status", {}).values()) != {"unknown"}
            or [c.get("id") for c in cfg.get("cases", [])] != list(CASE_IDS)):
        raise ContractError("Keep frozen source, original 900mm target and unknown professional approvals")
    for case in cfg["cases"]:
        for key in FIELDS:
            value = case.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
                raise ContractError("Only finite, bounded nonnegative sensitivity increments: "+key)
        if case["id"] == "nominal" and any(case[k] for k in FIELDS):
            raise ContractError("Nominal control must not consume or invent a clearance")


def _source(root, name):
    relative = Path(name)
    resolved = (root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts or not resolved.is_relative_to(root.resolve()):
        raise ContractError("Unsafe bath-fit source path")
    return resolved


def _frozen_parent(root):
    report = read_json(root / BASE_REPORT)
    if (report.get("schema") != "house-c-care-bath-v1" or report.get("bath_display_revision") != 2
            or report.get("status") != STATUS or report.get("adopted") is not False
            or not report.get("source_hashes") or not report.get("report_hash")):
        raise ContractError("Missing or altered frozen bath report")
    for name, digest in report["source_hashes"].items():
        source = _source(root, name)
        if not source.is_file() or sha256_file(source) != digest:
            raise ContractError("Stale frozen bath source: "+name)
    # Read JSON only; never execute the viewer or regenerate the parent.
    text = (root / BASE_VIEWER).read_text(encoding="utf-8")
    payload = re.search(r"^\s*var DATA = (.+);\s*$", text, re.M)
    if payload is None:
        raise ContractError("Missing frozen bath viewer payload")
    models = {(o["id"], s["id"]): s["model"] for o in json.loads(payload[1])["c_care_bath"]["options"] for s in o["states"]}
    # The original exporter hashes the model-bearing study, then strips models
    # from review.json. Reconstruct that exact payload instead of treating the
    # stripped report as if it had originally been independently hashed.
    reconstructed = copy.deepcopy(report)
    for option in reconstructed["options"]:
        for use in option["states"]:
            use["model"] = models[(option["id"], use["id"])]
    if report["report_hash"] != stable_hash({k: v for k, v in reconstructed.items() if k not in {"generated_at", "report_hash"}}):
        raise ContractError("Missing or altered frozen bath report/viewer")
    model = models[("c-bath-refined", "transfer")]
    state = next(s for o in report["options"] if o["id"] == "c-bath-refined"
                 for s in o["states"] if s["id"] == "transfer")
    cells = {c["id"]: c for c in model["buildings"][0]["floors"][0]["cells"] if c["tour_active"]}
    for room in state["plans"]["floors"][0]["rooms"]:
        cell = cells[room["id"]]
        items = [{**item, "placement": cell["furniture_placements"]["tour_mm"][item["id"]]} for item in cell["furniture"]]
        if (cell["tour_mm"] != room["geometry"] or cell["tour_features"] != room["features"]
                or items != room["furniture"]):
            raise ContractError("Frozen bath HTML/3D payload differs")
    return report, state


def measures(state, cfg):
    bath = next(r for r in state["plans"]["floors"][0]["rooms"] if r["key"] == "elder-bath")
    if rect(bath) != [3600, 13800, 2400, 3000]:
        raise ContractError("Do not expand the bath in a tolerance report")
    detail = state["review"]["bath"]
    vanity = body(next(i for i in bath["furniture"] if i["shape"] == "vanity"))
    leaf = next(panel for panel in bath["features"]["care_entry_leaves"] if panel["id"] == "bathroom")
    seat = next(c for c in bath["features"]["care_bath_components"] if c["id"] == "fold-seat")
    opening = bath["features"]["doors"][0]
    entry = detail["routes"]["toilet-transfer"]["sweeps_mm"][0]
    basin = detail["routes"]["vanity-front"]["sweeps_mm"][-1]
    transfer, board = detail["toilet_transfer_mm"], detail["rescue_board_rotation_mm"]
    inset = cfg["assumed_inset_each_face_mm"]
    clear = opening["width_mm"]-2*inset
    rows = [
        ("entry-vanity", "入口900mm試線到洗手台", entry[1]-vanity[1]-vanity[3],
         {"extra_finish_mm": 1, "extra_vanity_depth_mm": 1, "relative_position_error_mm": 1}, "前牆完成面及盆前緣向試線推進"),
        ("basin-arrival", "洗手台前最後到位點", basin[1]-vanity[1]-vanity[3],
         {"extra_finish_mm": 1, "extra_vanity_depth_mm": 1, "relative_position_error_mm": 1}, "原指定矩形恰貼盆前緣；可重排試線，不能當膝部可鑽入"),
        ("transfer-vanity", "側移預留到洗手台右緣", transfer[0]-vanity[0]-vanity[2],
         {"extra_finish_mm": 1, "extra_vanity_width_mm": 1, "relative_position_error_mm": 1}, "左牆完成面及盆右緣向預留推進"),
        ("board-seat", "剛性示意板轉向到收起折椅", component_box(seat)[1]-board[1]-board[3],
         {"extra_finish_mm": 1, "extra_folded_seat_projection_mm": 1, "relative_position_error_mm": 1}, "後牆／折椅／鉸座額外凸出向前吃掉餘量；仍非真人救援"),
        ("door-parking", "開啟門片尾端到後完成面", sum(rect(bath)[1::2])-inset-sum(leaf["rect_mm"][1::2]),
         {"extra_finish_mm": 1, "extra_leaf_length_mm": 1, "relative_position_error_mm": 1, "end_stop_allowance_mm": 1}, "1260mm門片停放已到假設完成面；止擋／檢修尚未另留"),
        ("door-clear", "名義扣框淨寬超過900mm的餘量", clear-cfg["required_door_clear_mm"],
         {"extra_jamb_each_mm": 2, "extra_handle_clear_loss_total_mm": 1}, "門框雙側各扣，把手損失為總量；門片已完全打開仍待商品證明"),
        ("door-body-jamb", "置中900mm試線到單側門框", (clear-detail["body_mm"][1])/2,
         {"extra_jamb_each_mm": 1, "extra_handle_clear_loss_total_mm": .5, "relative_position_error_mm": 1}, "把手以兩側均分作討論；偏心商品須重算較差側，不能視為實測"),
    ]
    return [{"id": key, "label": label, "nominal_mm": round(value, 3), "consumption_coefficients": weights,
             "interpretation": note} for key, label, value, weights, note in rows]


def sensitivity(rows, case):
    result = []
    for row in rows:
        consumed = sum(case[k]*weight for k, weight in row["consumption_coefficients"].items())
        remaining = round(row["nominal_mm"]-consumed, 3)
        result.append({"id": row["id"], "consumed_mm": consumed, "remaining_mm": remaining,
                       "status": "negative-budget" if remaining < 0 else "zero-spare" if remaining == 0 else "positive-budget-not-approved"})
    return {"id": case["id"], "label": case["label"], "parameters": {k: case[k] for k in FIELDS}, "results": result,
            "meaning": "固定座標的方向性餘量；不是重新尋路或證明整個房間不可能，也非同時照護或統計機率。"}


def product_ledger(state):
    bath = next(r for r in state["plans"]["floors"][0]["rooms"] if r["key"] == "elder-bath")
    specifics = {
        "toilet": "總外廓含水箱／沖水維修、座高、排污孔距與側移側別；總高800mm不是座高。",
        "vanity": "含盆緣龍頭與排水管外廓、壁掛補強、檯高、檯下淨高寬深及熱管隔熱；膝部通行信用仍0。",
        "accessible-shower": "1200×1200地面保留；無固定玻璃，地坪坡度、防滑、降板、門口止水與防水接續。",
        "bathroom-door": "全開實際淨寬至少原目標900mm；含把手／止擋的停門尺寸、軌道補強、外解鎖及門外拆卸。",
        "fold-seat": "折起含鉸座厚度、全角度掃掠、放下480×450、荷重及牆體錨定；不可只給座板尺寸。",
        "toilet-arm": "650mm長35mm管外尚有底座／握持間隙；全角度與承重、掀起定位及回落風險。",
        "toilet-wall-grab": "離牆淨空、底座外凸、手握及錨定承重；目前只畫管身不是完整商品。",
        "shower-wall-grab": "離牆淨空、底座及錨定承重；核對與龍頭／蓮蓬頭操作是否互擋。",
        "flush-drain": "含排水槽本體高度、防水翼、坡度、落水孔與清潔維修，不只900×50平面。",
        "shower-controls": "龍頭本體、突出把手、軟管、手持滑軌、坐姿可及及防燙，圖中管線不能當產品外廓。",
        "alarm-toilet": "低位可及、避免纏繞、聲光／手機聯動及斷電離線備援，核操作位置。",
        "alarm-shower": "濕區防水、倒地可及及避免纏繞，核聲光／手機及離線備援。",
    }
    items = [{"id": i["id"].rsplit(":", 1)[-1], "label": i["label"], "nominal_envelope_mm": [*body(i), 0, i["height_mm"]]}
             for i in bath["furniture"]]
    leaf = next(panel for panel in bath["features"]["care_entry_leaves"] if panel["id"] == "bathroom")
    items.append({"id": "bathroom-door", "label": "1200mm名義套衛拉門", "nominal_envelope_mm": [*leaf["rect_mm"], 0, leaf["height_mm"]]})
    items += [{"id": c["id"], "label": c["label"], "nominal_envelope_mm": component_box(c)} for c in bath["features"]["care_bath_components"]]
    for item in items:
        item.update(status="unknown-no-selected-product", manufacturer=None, model=None, selected_dimensions_mm=None,
                    dimensioned_drawing=None, installation_detail=None, checked_by=None, checked_at=None,
                    evidence_hash=None, professional_acceptance="unknown", required_check=specifics[item["id"]])
    return items


def build_study(root: Path = ROOT):
    cfg = read_json(root / SOURCE)
    validate_config(cfg)
    parent, state = _frozen_parent(root)
    rows = measures(state, cfg)
    cases = [sensitivity(rows, case) for case in cfg["cases"]]
    combined = {r["id"]: r for r in cases[-1]["results"]}
    recommendations = []
    for row in rows[:5]:
        recommendations.append({"id": row["id"], "label": row["label"],
            "extra_nominal_gap_to_keep_optional_buffer_mm": max(0, round(cfg["optional_discussion_margin_mm"]-combined[row["id"]]["remaining_mm"], 3)),
            "optional_buffer_mm": cfg["optional_discussion_margin_mm"], "adopted": False,
            "scope": "只是可討論的方向性增加量，不是牆／門的移動量、商品縮小量或規範；須回套完整動線。"})
    paths = {SOURCE, BASE_REPORT, BASE_VIEWER, BASE_INDEX, BASE_DETAIL, "house_design/c_care_bath_fit.py",
             "scripts/export_c_care_bath_fit.py", *parent["source_hashes"]}
    result = {"schema": SCHEMA, "revision": 1, "generated_at": utc_now(), "status": STATUS, "adopted": False,
        "geometry_changed": False, "rendered_qa": "not-run", "base_report_hash": parent["report_hash"],
        "base_plan_hash": stable_hash(state["plans"]), "base_review_hash": stable_hash(state["review"]),
        "base_viewer": BASE_VIEWER, "base_option": cfg["base_option"], "base_state": cfg["base_state"],
        "bath_nominal_mm": [2400, 3000], "assumed_finished_mm": [2170, 2770],
        "assumption_note": cfg["assumption_note"], "warning": WARNING, "measurements": rows, "cases": cases,
        "products": product_ledger(state), "recommendations": recommendations,
        "analysis_scope": "directional-clearance-budget-not-replanning-no-mesh-runtime",
        "construction_release": False, "professional_status": cfg["professional_status"],
        "retained_limits": parent["limits"],
        "source_hashes": {p: sha256_file(_source(root, p)) for p in sorted(paths)}}
    result["report_hash"] = stable_hash({k: v for k, v in result.items() if k != "generated_at"})
    return result

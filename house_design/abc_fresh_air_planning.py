"""Condition intake and independent numeric comparisons; never edits or adopts drawings."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

from house_design.abc_fresh_air_detail import build as detail_build
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash

CONFIG = "inputs/abc-fresh-air-planning.json"
OUT = "structured/coordination/abc-fresh-air-planning-v1"
CSV_FIELDS = ["id", "label", "unit", "value", "source", "date", "model_ref", "baseline_report_hash", "registry_hash"]
DUCT_IDS = ["common.duct."+k for k in ["inner_mm", "insulation_each_mm", "gap_mm", "edge_mm"]]
PRODUCT_FIELDS = {"installed_box_mm", "pull_required_mm", "removal_required_wh_mm", "fan_min_flow_m3_h",
    "fan_max_flow_m3_h", "curve_flow_m3_h", "curve_available_pressure_pa"}


def registry(parent):
    fields = {}

    def add(key, label, unit, kind, scope):
        fields[key] = {"id": key, "label": label, "unit": unit, "kind": kind, "scope": scope}

    for key, label, kind in [("inner_mm", "風管實際內徑", "positive"),
            ("insulation_each_mm", "徑向保溫厚度", "nonnegative"), ("gap_mm", "管間淨預留", "nonnegative"),
            ("edge_mm", "管帶兩外側各預留", "nonnegative"), ("extra_hanging_mm", "額外吊掛／施工公差", "nonnegative")]:
        add("common.duct."+key, label, "mm", kind, "共用研究；多種管材／保溫時需另分版本，不混填。")
    add("B.rear_alley_exists", "B實際後巷前提", "boolean", "boolean", "只作搬轎備案提示，不推定後牆可開孔。")
    specs = [
        ("model", "候選設備同一型號／版次", "text", "text"),
        ("installed_box_mm", "含接口／消音的主機安裝包絡[寬,深,高]，不含另列吊掛公差", "mm[W,D,H]", "positive3"),
        ("available_box_mm", "該機位可用安裝淨包絡[寬,深,高]", "mm[W,D,H]", "positive3"),
        ("beam_bottom_z_mm", "該段最低梁板底標高（本層完成地坪為0）", "mm", "positive"),
        ("ceiling_target_z_mm", "目標完成天花標高（同一地坪基準）", "mm", "positive"),
        ("duct_available_wh_mm", "四管路段可用管帶[寬,高]；不是房間走道寬", "mm[W,H]", "positive2"),
        ("pull_required_mm", "同型號實際濾芯／交換芯所需抽拉行程", "mm", "nonnegative"),
        ("pull_available_mm", "選定方向可提供的抽拉淨長", "mm", "nonnegative"),
        ("removal_required_wh_mm", "含操作餘量的整機直進所需完成淨孔[寬,深]", "mm[W,D]", "positive2"),
        ("removal_available_wh_mm", "扣框料後實際可拆完成淨孔[寬,深]", "mm[W,D]", "positive2"),
        ("design_flow_m3_h", "該分區設計室外風量（每層不重複派給每房）", "m3/h", "positive"),
        ("fan_min_flow_m3_h", "同型號／指定靜壓下可用最低風量", "m3/h", "nonnegative"),
        ("fan_max_flow_m3_h", "同型號／指定靜壓下可用最高風量", "m3/h", "positive"),
        ("required_pressure_pa", "設計路由及髒濾網所需機外靜壓", "Pa", "nonnegative"),
        ("curve_flow_m3_h", "所提供風機曲線點對應風量", "m3/h", "positive"),
        ("curve_available_pressure_pa", "該相同風量曲線點的可用靜壓", "Pa", "nonnegative")]
    for n in parent["networks"]:
        for suffix, label, unit, kind in specs:
            add(n["id"]+"."+suffix, label, unit, kind, n["building"]+"棟 "+n["floor"]+"／"+n["unit"])
            if suffix in PRODUCT_FIELDS:
                fields[n["id"]+"."+suffix]["candidate_model_field"] = n["id"]+".model"
    for g in parent["outdoor_groups"]:
        add(g["id"]+".opening_permitted", "此樓層／側向兩個候選口的開孔條件已有可用證據", "boolean", "boolean",
            g["id"]+"指定位置，不套到其他樓層；填true不是工具核發合法開孔許可。")
        for role in ["OA", "EA"]:
            add(g["id"]+"."+role+".solid_z_interval_mm", "既定候選XY處實牆可用高位區間[下界,上界]", "mm[low,high]", "interval",
                g["id"]+" "+role+"，本層完成地坪為0；需核定完整外罩寬度內的實牆。")
            add(g["id"]+"."+role+".required_opening_height_mm", "含外罩／框及邊界要求的安裝孔高", "mm", "positive", g["id"]+" "+role)
    return fields


def input_template(parent, fields, schema):
    return {"schema": schema, "baseline_report_hash": parent["report_hash"], "registry_hash": stable_hash(fields),
        "values": {key: {"value": None, "unit": f["unit"], "source": None, "date": None, "model_ref": None} for key, f in fields.items()}}


def finite(v):
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def validate_value(value, field):
    kind = field["kind"]
    if kind == "boolean":
        valid = type(value) is bool
    elif kind == "text":
        valid = isinstance(value, str) and bool(value.strip()) and len(value) <= 250
    elif kind in {"positive", "nonnegative"}:
        valid = finite(value) and (value > 0 if kind == "positive" else value >= 0)
    else:
        length = 3 if kind == "positive3" else 2
        valid = isinstance(value, list) and len(value) == length and all(finite(v) for v in value)
        if valid:
            valid = (0 <= value[0] < value[1]) if kind == "interval" else min(value) > 0
    if not valid:
        raise ContractError("Invalid condition type/range: "+field["id"])


def normalize(document, parent, fields, cfg):
    template = input_template(parent, fields, cfg["input_schema"])
    if document is None:
        return template["values"]
    if not isinstance(document, dict) or set(document) != set(template):
        raise ContractError("Input root must contain only schema, baseline_report_hash, registry_hash and values")
    if any(document[k] != template[k] for k in ["schema", "baseline_report_hash", "registry_hash"]):
        raise ContractError("Condition input baseline/registry changed; migrate explicitly, do not apply to a new plan")
    if not isinstance(document["values"], dict) or set(document["values"])-set(fields):
        raise ContractError("Unknown condition ID; cannot edit fixed requirements through data intake")
    result = template["values"]
    for key, raw in document["values"].items():
        if not isinstance(raw, dict) or set(raw) != {"value", "unit", "source", "date", "model_ref"}:
            raise ContractError("Condition must contain value/unit/source/date/model_ref: "+key)
        if raw["unit"] != fields[key]["unit"]:
            raise ContractError("Condition unit mismatch: "+key)
        if raw["value"] is not None:
            validate_value(raw["value"], fields[key])
            if not isinstance(raw["source"], str) or not raw["source"].strip() or len(raw["source"]) > 1000:
                raise ContractError("Filled condition needs a source reference: "+key)
            try:
                if not isinstance(raw["date"], str) or date.fromisoformat(raw["date"]).isoformat() != raw["date"]:
                    raise ValueError
            except ValueError as exc:
                raise ContractError("Filled condition needs an ISO YYYY-MM-DD source date: "+key) from exc
        elif raw["source"] is not None or raw["date"] is not None or raw["model_ref"] is not None:
            raise ContractError("Unknown values keep source/date/model_ref null; put pending notes outside the intake: "+key)
        result[key] = copy.deepcopy(raw)
    for key, raw in result.items():
        model_key = fields[key].get("candidate_model_field")
        if raw["value"] is not None and model_key:
            model = result[model_key]["value"]
            if not isinstance(model, str) or raw["model_ref"] != model:
                raise ContractError("Product condition must bind to the same candidate model/revision: "+key)
        elif raw["model_ref"] is not None:
            raise ContractError("Non-product or unknown condition must not have a model_ref: "+key)
    return result


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("Duplicate JSON field: "+key)
        result[key] = value
    return result


def parse_json(text):
    def invalid_constant(_):
        raise ContractError("Nonfinite JSON number is not a condition")
    try:
        return json.loads(text, object_pairs_hook=no_duplicates, parse_constant=invalid_constant)
    except json.JSONDecodeError as exc:
        raise ContractError("Invalid condition JSON") from exc


def load_input(path, fields, cfg):
    path = Path(path)
    if path.stat().st_size > cfg["input_byte_limit"]:
        raise ContractError("Condition input exceeds the bounded intake size")
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    if path.suffix.lower() == ".json":
        document = parse_json(text)
    elif path.suffix.lower() == ".csv":
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if reader.fieldnames is None or len(reader.fieldnames) != len(CSV_FIELDS) or set(reader.fieldnames) != set(CSV_FIELDS):
            raise ContractError("CSV headers changed or duplicated")
        values, pins = {}, set()
        for row in reader:
            if set(row) != set(CSV_FIELDS) or any(v is None for v in row.values()):
                raise ContractError("CSV has malformed rows")
            key = row["id"]
            if key not in fields or key in values:
                raise ContractError("Unknown or duplicate CSV condition ID")
            value = row["value"].strip()
            values[key] = {"value": (value if fields[key]["kind"] == "text" else parse_json(value)) if value else None,
                "unit": row["unit"], "source": row["source"].strip() or None, "date": row["date"].strip() or None,
                "model_ref": row["model_ref"].strip() or None}
            pins.add((row["baseline_report_hash"], row["registry_hash"]))
        if len(pins) != 1:
            raise ContractError("CSV must use one pinned baseline/registry")
        baseline, registry_hash = next(iter(pins))
        document = {"schema": cfg["input_schema"], "baseline_report_hash": baseline,
            "registry_hash": registry_hash, "values": values}
    else:
        raise ContractError("Conditions must be JSON or CSV, never executable expressions")
    return document, hashlib.sha256(raw).hexdigest()


def sections(values):
    inner, insulation, gap, edge = values
    od = inner+2*insulation
    return {"four-flat": [4*od+3*gap+2*edge, od+2*edge],
        "four-stacked": [2*od+gap+2*edge, 2*od+gap+2*edge]}


def box_comparison(required, available):
    # XY rotation only, never flips a ceiling unit or proves a full transport sweep.
    rotations = [required, [required[1], required[0], *required[2:]]]
    margins = [[a-b for a, b in zip(available, r, strict=True)] for r in rotations]
    best = max(margins, key=min)
    return {"status": "numeric-fit" if min(best) >= 0 else "conflict", "margin_mm": best,
        "meaning": "直進尺寸比較，可平面旋轉；不當接口方向／安裝方式或整機運出核可。"}


def duct_comparison(dimensions, available):
    options = sections(dimensions)
    fits = [key for key, size in options.items() if all(a >= b for a, b in zip(available, size, strict=True))]
    return {"status": "numeric-fit" if fits else "conflict", "required_sections_mm": options, "eligible": fits,
        "meaning": "只比較含所填保溫／間距的四管矩形預算，不含未提供的彎頭、消防、冷媒或實際路由。"}


def evaluate(parent, cfg, fields, records):
    values = {key: row["value"] for key, row in records.items()}
    checks = []

    def add(key, label, needs, rule, next_action):
        missing = [f for f in needs if values[f] is None]
        result = {"status": "pending", "reason": "等待資料；不以規劃假設或空白代替。"} if missing else rule([values[f] for f in needs])
        checks.append({"id": key, "label": label, "needs": needs, "missing": missing, **result,
            "next_action": next_action, "independent_evidence_verification": False, "professional_approval": "unknown"})

    for n in parent["networks"]:
        nid = n["id"]
        def ids(suffixes, nid=nid):
            return [nid+"."+s for s in suffixes]
        add(nid+":model", nid+"候選型號", ids(["model"]),
            lambda v: {"status": "condition-recorded", "candidate": v[0]}, "同一型號／版次的尺寸與曲線不得混搭，記錄不等於採購。")
        add(nid+":machine", nid+"主機含接口包絡", ids(["installed_box_mm", "available_box_mm"]),
            lambda v: box_comparison(*v), "不合則改機型／機位；不縮床櫃、照護或原房間需求。")
        duct_needs = DUCT_IDS+ids(["duct_available_wh_mm"])
        add(nid+":ducts", nid+"四管斷面", duct_needs, lambda v: duct_comparison(v[:4], v[4]),
            "橫排／雙層均不足就改路由或機位，不把四管重塞原雙管帶。")

        def ceiling(v):
            d = duct_comparison(v[:4], v[4])
            beam, target, machine, hanging = v[5:]
            if not d["eligible"]:
                return {"status": "conflict", "reason": "四管可用斷面已不足，不能先當天花高度通過。"}
            required = min(max(machine[2], d["required_sections_mm"][a][1])+hanging for a in d["eligible"])
            margin = beam-target-required
            return {"status": "numeric-fit" if margin >= 0 else "conflict", "drop_required_mm": required,
                "available_drop_mm": beam-target, "margin_mm": margin, "actual_route_z_selected": False}

        add(nid+":ceiling", nid+"梁下／完成天花", duct_needs+ids(["beam_bottom_z_mm", "ceiling_target_z_mm", "installed_box_mm"])
            +["common.duct.extra_hanging_mm"], ceiling, "不足則重比機位／斷面；不能自動降低屋主目標或鑽梁。")
        add(nid+":pull", nid+"側抽行程", ids(["pull_required_mm", "pull_available_mm"]),
            lambda v: {"status": "numeric-fit" if v[1] >= v[0] else "conflict", "margin_mm": v[1]-v[0]},
            "還要核方向、障礙、架梯與檢修期間逃生，長度足夠不等於操作安全。")
        add(nid+":removal", nid+"完成淨孔", ids(["removal_required_wh_mm", "removal_available_wh_mm"]),
            lambda v: box_comparison(*v), "輸入必須已扣框料並含所需操作餘量；整機落機及運出另核。")

        def flow(v):
            target, low, high = v
            return {"status": "numeric-fit" if low <= target <= high else "conflict",
                "data_contradiction": low > high, "target_m3_h": target, "range_m3_h": [low, high]}

        add(nid+":flow", nid+"夜間風量範圍", ids(["design_flow_m3_h", "fan_min_flow_m3_h", "fan_max_flow_m3_h"]), flow,
            "設計總量不重複派給每房；不合則改低負載機型或系統設計，不能省略通風。")

        def pressure(v):
            target, required, measured_q, available = v
            if not math.isclose(target, measured_q, rel_tol=0, abs_tol=1e-6):
                return {"status": "pending", "reason": "曲線點與目標風量不同，不借用最大靜壓。"}
            return {"status": "numeric-fit" if available >= required else "conflict", "margin_pa": available-required}

        add(nid+":pressure", nid+"同風量工作點", ids(["design_flow_m3_h", "required_pressure_pa", "curve_flow_m3_h", "curve_available_pressure_pa"]),
            pressure, "同型號、髒濾網、全路由及支路平衡需與機電確認，不用自由風量／堵轉最大靜壓替代。")

    for g in parent["outdoor_groups"]:
        gid = g["id"]
        add(gid+":wall", gid+"外牆條件", [gid+".opening_permitted"],
            lambda v: {"status": "condition-recorded" if v[0] else "conflict", "opening_condition_received": v[0]},
            "指定候選位置仍須風雨／鄰戶污染源及合法開孔簽認；true不是自動許可。")
        for role in ["OA", "EA"]:
            def opening(v):
                interval, h = v
                margin = interval[1]-interval[0]-h
                return {"status": "numeric-fit" if margin >= 0 else "conflict", "margin_mm": margin,
                    "center_z_range_mm": [interval[0]+h/2, interval[1]-h/2] if margin >= 0 else None,
                    "actual_hole_z_selected": False}
            add(gid+":"+role, gid+" "+role+"高位實牆", [gid+"."+role+".solid_z_interval_mm", gid+"."+role+".required_opening_height_mm"],
                opening, "不足就保留別端／重排，不能改窗、門楣、梁或未確認共壁。")
    add("B:rear-alley", "B後巷與搬轎比較提示", ["B.rear_alley_exists"],
        lambda v: {"status": "condition-recorded", "suggested_comparison": "rear-default-retained" if v[0] else "front-entry-fallback-priority",
            "transport_or_opening_approval": False}, "只改比較提示，不自動變更搬轎入口／外牆權利或刪原後門版。")
    for i, label in enumerate(cfg["manual_gates"], 1):
        checks.append({"id": "manual:"+str(i), "label": label, "needs": [], "missing": [], "status": "pending",
            "reason": "人工關卡，不由數值填齊自動通過。", "next_action": label,
            "independent_evidence_verification": False, "professional_approval": "unknown"})
    by_id = {c["id"]: c for c in checks}
    choices = []
    for nid in ["B2", "B3"]:
        states = {}
        for side in ["rear", "front"]:
            rows = [by_id[nid+"-"+side+":"+r] for r in ["wall", "OA", "EA"]]
            states[side] = "conflict" if any(r["status"] == "conflict" for r in rows) else (
                "supported-for-comparison" if all(r["status"] in {"numeric-fit", "condition-recorded"} for r in rows) else "pending")
        recommended = "retain-both-await-conditions"
        if states["rear"] == "supported-for-comparison":
            recommended = "compare-rear-default-first"
        elif states["front"] == "supported-for-comparison":
            recommended = "compare-front-fallback-first"
        elif set(states.values()) == {"conflict"}:
            recommended = "reroute-required-no-party-wall-assumption"
        choices.append({"network": nid, "external_interface_states": states, "next_comparison": recommended,
            "rear_and_front_retained": True, "entry_layout_selected": None, "adopted": False})
    impact = [{**f, "value_received": values[key] is not None,
        "affected_checks": [c["id"] for c in checks if key in c["needs"]]} for key, f in fields.items()]
    return checks, choices, impact


def context(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    if cfg.get("scope") != "preplanning-condition-intake-and-independent-recalculation-only" or cfg.get("adopted") is not False or cfg.get("automatic_primary_3d_write") is not False:
        raise ContractError("Planning-only workflow cannot adopt or write the primary model")
    if sha256_file(root/cfg["parent_report"]) != cfg["parent_file_sha256"]:
        raise ContractError("Planning parent file changed")
    parent = detail_build(root)
    if parent["report_hash"] != cfg["parent_report_hash"]:
        raise ContractError("Planning parent sources changed")
    owner = read_json(root/cfg["owner_direction"])
    if not all(owner["confirmed"].get(k) is True for k in ["current_work_is_preplanning", "prepare_condition_intake_and_recalculation", "wait_for_real_data_before_actual_integration"]):
        raise ContractError("Need owner planning-only direction")
    return cfg, parent, registry(parent)


def build(root, document=None, input_sha256=None):
    root = Path(root)
    cfg, parent, fields = context(root)
    records = normalize(document, parent, fields, cfg)
    checks, choices, impact = evaluate(parent, cfg, fields, records)
    counts = dict(Counter(c["status"] for c in checks))
    assumed = [parent["config"][k] for k in ["inner_diameter_mm", "insulation_radial_mm", "pipe_gap_mm", "edge_mm"]]
    report = {"schema": "house-abc-fresh-air-planning-report-v1", "date": cfg["date"],
        "scope": cfg["scope"], "source_layout_report_sha256": parent["source_layout_report_sha256"],
        "baseline_report_hash": parent["report_hash"], "registry_hash": stable_hash(fields),
        "fixed_requirements": parent["config"]["unchanged_requirements"],
        "planning_assumptions_only": {"four_duct_sections_mm": sections(assumed),
            "source": "frozen-concept-only-not-measurement", "actual_installed": False},
        "registry": fields, "input_records": records, "input_document_sha256": input_sha256 or (stable_hash(document) if document is not None else None),
        "conditions_received": sum(r["value"] is not None for r in records.values()), "conditions_total": len(fields),
        "checks": checks, "comparison_choices": choices, "impact_map": impact, "summary": counts,
        "adopted": False, "selected_product": None, "primary_or_3d_written": False,
        "professional_approval": "unknown", "actual_integration_performed": False, "browser_qa": "not-run",
        "protected_controls_unchanged": parent["protected_controls_unchanged"],
        "retained_b_entries": parent["retained_b_entries"],
        "usage": "分批填條件即可獨立重算；缺資料不是0或失敗。數值相容不是施工、產品、法規、風水或照護核可。"}
    names = [CONFIG, cfg["parent_report"], *parent["source_hashes"], cfg["owner_direction"],
        "house_design/abc_fresh_air_planning.py", "scripts/export_abc_fresh_air_planning.py", "Docs/abc-conditional-planning-v1.md"]
    report["source_hashes"] = {n: sha256_file(root/n) for n in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

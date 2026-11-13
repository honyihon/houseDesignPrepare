"""Builder-facing G4D data contract; partial inputs yield local arithmetic, never release."""
from __future__ import annotations

import copy
import math
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

from house_design.b_front_drop_claude_round2 import build as build_round2
from house_design.b_upper_replan import rect
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-front-drop-conditions.json"
OUT = "structured/coordination/b-front-drop-conditions-v1"

# A reported value must identify its source, drawing revision and common datum.
# No numeric hypothesis from the earlier study is inserted into actual-data fields.
GROUPS = {
    "local-drop": [
        ("highest_package_top_before_drop_z_mm", "落差前整盒最高管頂標高", "z", "保守包絡頂，不是管心；不含另列的上凸及安裝間隔"),
        ("lowest_package_bottom_before_drop_z_mm", "落差前整盒最低管底標高", "z", "實體包絡底，不先扣另列的下凸或下方操作空間"),
        ("lowest_soffit_over_complete_box_z_mm", "完整外框上方最低構造底", "z", "覆蓋本次完整外框與全部梁板，不只中心或鼻線推算"),
        ("finished_floor_z_mm", "相應位置完成地坪標高", "z", "與管頂、管底及梯底同一標高基準"),
        ("upper_installation_gap_mm", "上方安裝間隔", "nonnegative", "實際需求；不與額外穩定餘量互抵"),
        ("extra_upper_fitting_mm", "超出原包絡的上凸", "nonnegative", "只填未含在最高管頂的增量，避免重複扣"),
        ("additional_upper_reserve_mm", "額外穩定餘量M", "nonnegative", "由專業依據指定，不能將空白當0"),
        ("extra_lower_fitting_mm", "超出原包絡的下凸", "nonnegative", "未含在最低管底的增量，與上凸分開"),
        ("operating_space_below_mm", "管底下方操作空間", "nonnegative", "需要扣出的檢修／操作包絡，不假定50已足夠"),
        ("required_finished_clear_height_mm", "相應位置所需完成淨高", "positive", "同口徑要求及依據；工具不預填法規值"),
    ],
    "upstream-gap": [
        ("pipe_package_top_z_mm", "指定上游點管包絡頂標高", "z", "同版實際包絡；不能借梯下末端數字"),
        ("lowest_structure_z_mm", "指定上游點最低構造底", "z", "與管頂同一點／段與標高基準"),
        ("required_upper_gap_mm", "此點所需上方間隔", "nonnegative", "局部50不是全線已足夠的證明"),
        ("extra_upper_fitting_mm", "未含在管頂的上凸", "nonnegative", "已含包絡者此增量明填0並附依據"),
        ("additional_reserve_mm", "此點額外餘量", "nonnegative", "未知保留null，不猜0"),
    ],
    "front-terminal": [
        ("rights_record", "通行／埋管權利文件狀態", "record", "documented只代表有文件待專業核，不是本工具授權"),
        ("connection_record", "接管位置／權責文件狀態", "record", "documented或not-available，未知維持null"),
        ("start_invert_z_mm", "指定埋管段起點管內底標高", "z", "由給排水圖提供，不從上方管頂自動換算"),
        ("connection_invert_z_mm", "指定接入點管內底標高", "z", "同一標高基準，包含正負標高"),
        ("horizontal_route_mm", "同坡指定段完整水平長", "positive", "包含平面轉折，不拿5190直線下界當實際線長"),
        ("slope_denominator", "指定等坡段1:n的n", "positive", "由設計回覆，不預填50或認證坡度合規"),
        ("additional_fall_reserve_mm", "額外落差預留", "nonnegative", "明列未納入標高的落差／誤差；不同坡段需另案"),
    ],
    "plan-envelope": [
        ("front_growth_mm", "400框前向外擴", "nonnegative", "只與原研究框比，並非基地實測位置"),
        ("rear_growth_mm", "400框後向外擴", "nonnegative", "後緣梯底需按完整外框另取"),
        ("left_growth_mm", "400框左向外擴", "nonnegative", "與上凸、右擴分開"),
        ("right_growth_mm", "400框右向外擴", "nonnegative", "不得侵入既有保護投影"),
        ("shift_back_mm", "相對原研究框名義後移", "nonnegative", "只回算宣告值，不自動移井或接主3D"),
        ("required_platform_gap_mm", "平台邊另需間隔", "nonnegative", "相切不等於有施工餘量；有依據才明填0"),
    ],
}


def finite(value, kind):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        if not math.isfinite(value) or abs(value) > 10_000_000:
            return False
        return kind == "z" or kind == "nonnegative" and value >= 0 or kind == "positive" and value > 0
    except OverflowError:
        return False


def template(cfg, parent):
    return {"schema": "house-b-front-drop-actual-conditions-v1", "config_hash": stable_hash(cfg),
        "parent_report_hash": parent["report_hash"], "reference_case": cfg["reference_case"],
        "basis": {"drawing_revision": "", "datum_id": "", "coordinate_note": ""},
        "groups": [{"id": name, "reference": "", "values": dict.fromkeys(f[0] for f in fields)} for name,fields in GROUPS.items()]}


def validate_conditions(base, document):
    received = copy.deepcopy(base if document is None else document)
    if (not isinstance(received, dict) or set(received) != set(base)
            or any(received[k] != base[k] for k in ["schema", "config_hash", "parent_report_hash", "reference_case"])
            or not isinstance(received["basis"], dict) or set(received["basis"]) != set(base["basis"])
            or any(not isinstance(v, str) or len(v) > 4000 for v in received["basis"].values())
            or not isinstance(received["groups"], list)):
        raise ContractError("Use this exact G4D source revision, reference case and blank-data contract")
    groups, count = {}, 0
    for group in received["groups"]:
        if (not isinstance(group, dict) or set(group) != {"id", "reference", "values"}
                or not isinstance(group.get("id"), str) or group["id"] not in GROUPS or group["id"] in groups):
            raise ContractError("Unknown, missing or duplicate G4D condition group")
        fields = GROUPS[group["id"]]
        if (not isinstance(group["values"], dict) or set(group["values"]) != {f[0] for f in fields}
                or not isinstance(group["reference"], str) or len(group["reference"]) > 4000):
            raise ContractError("Keep every G4D field; unknown values stay null and need explicit references")
        populated = [name for name,_,_,_ in fields if group["values"][name] is not None]
        for name,_,kind,_ in fields:
            value = group["values"][name]
            if value is None:
                continue
            if kind == "record":
                if not isinstance(value, str) or value not in {"documented", "not-available"}:
                    raise ContractError("Legal document status is recorded, not an approval or free-text yes")
            elif not finite(value,kind):
                raise ContractError("G4D inputs require finite millimetres, explicit zero or positive dimensions as declared")
        if populated and (not group["reference"].strip() or not received["basis"]["drawing_revision"].strip()):
            raise ContractError("Each received G4D value needs a source and common drawing revision")
        if any(group["values"][name] is not None and kind == "z" for name,_,kind,_ in fields) and not received["basis"]["datum_id"].strip():
            raise ContractError("Every declared elevation uses one explicit common datum; do not mix revisions or baselines")
        if populated and group["id"] == "plan-envelope" and not received["basis"]["coordinate_note"].strip():
            raise ContractError("Plan values must declare how they relate to the original G4D frame")
        count += len(populated)
        groups[group["id"]] = group
    if set(groups) != set(GROUPS):
        raise ContractError("Keep all four G4D groups, including unknown groups")
    local = groups["local-drop"]["values"]
    if all(local[k] is not None for k in ["highest_package_top_before_drop_z_mm", "lowest_package_bottom_before_drop_z_mm"]) and local["highest_package_top_before_drop_z_mm"] < local["lowest_package_bottom_before_drop_z_mm"]:
        raise ContractError("Package top cannot be below its bottom at the same declared envelope basis")
    return received, groups, count


def evaluate(groups, ground):
    result = []
    for name,fields in GROUPS.items():
        values = groups[name]["values"]
        missing = [f[0] for f in fields if values[f[0]] is None]
        row = {"id": name, "missing_fields": missing, "status": "pending", "dimension_or_interval_compatible_only": None,
            "whole_route_or_professional_approval": "unknown", "may_release_work": False}
        if name == "local-drop":
            row.update(minimum_effective_drop_mm=None, maximum_effective_drop_mm=None, interval_width_mm=None, selected_drop_mm=None)
        else:
            row["margin_mm"] = None
        if not missing:
            collision = False
            if name == "local-drop":
                dmin = max(0, values["highest_package_top_before_drop_z_mm"]+values["extra_upper_fitting_mm"]+values["upper_installation_gap_mm"]+values["additional_upper_reserve_mm"]-values["lowest_soffit_over_complete_box_z_mm"])
                dmax = values["lowest_package_bottom_before_drop_z_mm"]-values["extra_lower_fitting_mm"]-values["operating_space_below_mm"]-values["finished_floor_z_mm"]-values["required_finished_clear_height_mm"]
                row.update(minimum_effective_drop_mm=round(dmin,3), maximum_effective_drop_mm=round(dmax,3), interval_width_mm=round(dmax-dmin,3))
                margin = dmax-dmin
            elif name == "upstream-gap":
                margin = values["lowest_structure_z_mm"]-values["pipe_package_top_z_mm"]-values["required_upper_gap_mm"]-values["extra_upper_fitting_mm"]-values["additional_reserve_mm"]
            elif name == "front-terminal":
                fall = values["horizontal_route_mm"]/values["slope_denominator"]
                if not math.isfinite(fall):
                    raise ContractError("Declared terminal fall exceeds finite range")
                margin = values["start_invert_z_mm"]-values["connection_invert_z_mm"]-fall-values["additional_fall_reserve_mm"]
                row["required_slope_fall_mm"] = round(fall,3)
            else:
                front,rear,left,right,shift,gap = [values[k] for k in ["front_growth_mm","rear_growth_mm","left_growth_mm","right_growth_mm","shift_back_mm","required_platform_gap_mm"]]
                shape = rect([1280-left,4990+shift-front,400+left+right,400+front+rear])
                platform = rect([80,3970,2200,1000])
                protected = unary_union([Polygon(p) for p in ground["stack_and_entry"]["options"][0]["roof_protected_footprints_mm"]])
                storage = rect([0,14500,3330,3130])
                margin = 20+shift-front-gap
                row.update(body_rect_mm=[1280-left,4990+shift-front,400+left+right,400+front+rear],
                    platform_overlap_sqm=round(shape.intersection(platform).area/1e6,6),
                    protected_or_storage_overlap_sqm=round(shape.intersection(protected.union(storage)).area/1e6,6),
                    wholly_in_reference_return_footprint=rect([1280,4970,1000,2970]).covers(shape),
                    within_reference_stair_enclosure=rect([0,3900,2400,5200]).covers(shape),
                    expanded_box_structure_verified=False)
                collision = (shape.intersection(platform.union(protected).union(storage)).area > .01
                    or not row["within_reference_stair_enclosure"])
            if name != "local-drop":
                row["margin_mm"] = round(margin,6)
            compatible = margin >= 0 and not collision
            row.update(status="declared-local-arithmetic-compatible" if compatible else "reject-declared-local-arithmetic",
                dimension_or_interval_compatible_only=compatible)
        if name == "front-terminal" and any(values[k] == "not-available" for k in ["rights_record","connection_record"]):
            row.update(status="front-terminal-not-documented-available-stop-locking",dimension_or_interval_compatible_only=False)
        result.append(row)
    return result


def build(root, condition_document=None):
    root, cache = Path(root), {}
    cfg = read_json(root/CONFIG)
    if (cfg.get("schema") != "house-b-front-drop-conditions-v1" or cfg.get("adopted") is not False
            or cfg["reference_case"] != "G4D-original-shaft-platform-and-stair-only"
            or [cfg[k] for k in ["sequence_id","comparison_id","task_id"]] != ["SEQ-04","BC-CMP-01","B-WET-001"]
            or [g["id"] for g in cfg["gates"]] != [f"BFD-{i:02d}" for i in range(1,9)]):
        raise ContractError("Keep G4D builder questions attached to existing research and decision identities")
    for n,h in cfg["pinned_sources"].items():
        if sha256_file(public_path(root,n)) != h:
            raise ContractError("Frozen G4D round2 source changed: "+n)
    parent = read_json(root/cfg["parent_report"])
    if build_round2(root)["report_hash"] != parent["report_hash"]:
        raise ContractError("Round2 basis drift; prepare a new reviewed reference before applying data")
    base = template(cfg,parent)
    received,groups,count = validate_conditions(base,condition_document)
    ground = read_json(root/"structured/coordination/b-claude-round3-v1/review.json")
    evaluations = evaluate(groups,ground)
    fields = [{"group":name,"field":key,"label":label,"unit":"document-status" if kind == "record" else "1:n denominator" if key == "slope_denominator" else "mm",
        "value_rule":kind,"meaning":note,"public_default":None} for name,items in GROUPS.items() for key,label,kind,note in items]
    names=[CONFIG,*cfg["pinned_sources"],*parent["source_hashes"],"house_design/b_front_drop_conditions.py",
        "scripts/export_b_front_drop_conditions.py","Docs/b-front-drop-builder-interface-v1.md"]
    report={"schema":"house-b-front-drop-conditions-report-v1","date":cfg["date"],"config":cfg,"parent_report_hash":parent["report_hash"],
        "condition_template":base,"received_conditions":received,"condition_document_hash":None if condition_document is None else stable_hash(condition_document),
        "condition_values_received":count,"field_guide":fields,"condition_evaluations":evaluations,
        "engineering_gates":[{**g,"received_reply":None,"owner_choice":None,"professional_review":"unknown","construction_release":False} for g in cfg["gates"]],
        "any_declared_conflict":any(r["dimension_or_interval_compatible_only"] is False for r in evaluations),
        "local_arithmetic_is_not_whole_design_approval":True,"automatic_next_layout_selection":None,
        "protected_controls_unchanged":parent["protected_controls_unchanged"],"primary_abc_or_3d_changed":False,
        "original_family_rules_changed":False,"adopted":False,"full_design_consensus":False,"professional_approval":"unknown","rendered_qa":"not-run",
        "source_hashes":{n:digest(root,n,cache) for n in dict.fromkeys(names)}}
    report["report_hash"]=stable_hash(report)
    return report

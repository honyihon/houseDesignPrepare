"""Source-bound round-three checks; research agreement is not design adoption."""
from __future__ import annotations

import copy
import math
from itertools import combinations
from pathlib import Path

import shapely
from shapely.geometry import LineString, Polygon, box

from house_design.b_claude_crosscheck import analyze_variant, proposed_rooms
from house_design.b_fengshui_strict import area_shape, collision, translate
from house_design.c_coordination import public_path
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash

CONFIG = "inputs/b-claude-round3.json"
OUT = "structured/coordination/b-claude-round3-v1"


def max_axis_rectangle(shape):
    """Vertex-grid maximum for this small, orthogonal finished-room polygon."""
    xs = sorted({p[0] for p in shape.exterior.coords})
    ys = sorted({p[1] for p in shape.exterior.coords})
    best = (0, None)
    for x0, x1 in combinations(xs, 2):
        for y0, y1 in combinations(ys, 2):
            candidate = box(x0, y0, x1, y1)
            if candidate.area > best[0] and shape.covers(candidate):
                best = candidate.area, [x0, y0, x1-x0, y1-y0]
    return {"rect_mm": best[1], "area_sqm": best[0]/1e6,
        "method": "orthogonal-vertex-grid-enumeration"}


def check_public_shaft(room, shaft):
    shape = area_shape(shaft)
    return {"rect_mm": shaft, "area_sqm": shape.area/1e6,
        "inside_finished": area_shape(room["illustrative_finished_rect_mm"]).covers(shape),
        "body_hits": [i["id"] for i in room["furniture"] if collision(shape, area_shape(i["rect_mm"]))],
        "operation_hits": [i["id"] for i in room["furniture"] if collision(shape, area_shape(i["operation_mm"]))],
        "arrival_hit": collision(shape, area_shape(room["inside_approach_mm"])),
        "actual_pipe_pack": None, "inspection_access": None, "approval": "unknown"}


def variant(prior_cfg, strict, cfg, revised):
    local = copy.deepcopy(prior_cfg)
    if revised:
        pub = local["upper"]["public_bath"]
        pub["fixtures_local_mm"] = cfg["new01b"]["public_fixtures_local_mm"]
        pub["operations_local_mm"] = cfg["new01b"]["public_operations_local_mm"]
    rooms = proposed_rooms(local, margin=True)
    result = analyze_variant(local, strict, rooms, "NEW-01b" if revised else "NEW-01",
        "Claude提出／Codex核算；洗衣機與右牆冷氣修正僅Codex提出" if revised else "Claude第三輪明確同意作研究基線")
    # The inherited value is a one-axis projection, not a collision clearance.
    result["bed_leaf_y_projection_gap_mm"] = result.pop("bed_rear_to_open_private_leaf_mm")
    finished = Polygon(rooms[0]["polygon_mm"]).buffer(-115, join_style=2)
    result["largest_axis_rectangle"] = max_axis_rectangle(finished)
    if revised:
        ac = {"id": "B-AC03", **copy.deepcopy(cfg["codex_right_wall_ac"])}
        rooms[0]["hvac_candidate"] = ac
        result["third_floor_rooms"][0]["hvac_candidate"] = {**copy.deepcopy(ac), "id": "B-AC04"}
    result["bedroom_hvac_contained"] = finished.covers(area_shape(rooms[0]["hvac_candidate"]["rect_mm"]))
    outline = result["current_inset_case"]["public_bath"]
    shaft_area = 0
    if revised:
        public = rooms[2]
        origin = public["illustrative_finished_rect_mm"][:2]
        shaft = translate(cfg["new01b"]["shaft_local_mm"], origin)
        result["shaft"] = check_public_shaft(public, shaft)
        result["no_pipe_strip_mm"] = translate(cfg["new01b"]["no_pipe_strip_local_mm"], origin)
        backing = Polygon(rooms[1]["polygon_mm"])
        shower = next(i for i in public["furniture"] if i["id"] == "shower")
        result["shaft"]["distance_to_backing_polygon_mm"] = area_shape(shaft).distance(backing)
        result["shaft"]["shower_to_backing_mm"] = area_shape(shower["rect_mm"]).distance(backing)
        shaft_area = result["shaft"]["area_sqm"]
    result["public_area_accounting"] = {"outline_finished_estimate_sqm": outline,
        "shaft_deduction_sqm": shaft_area, "after_shaft_estimate_sqm": round(outline-shaft_area, 6),
        "method": "115-per-side-outline-estimate-minus-dedicated-shaft-only",
        "actual_finished_survey": None, "original_target_sqm": 5, "original_min_sqm": 3.6}
    result["public_exterior_window"] = {"present": False, "mechanical_ventilation_route": None,
        "owner_exterior_window_preference_met": False}
    result["bed_over_palanquin_sqm"] = round(area_shape(rooms[0]["furniture"][0]["rect_mm"]).intersection(
        area_shape(strict["options"][0]["palanquin_rect_mm"])).area/1e6, 6)
    result["religious_family_rules"] = "three-owner-answers-recorded-other-conditions-still-unverified"
    return result


def door_and_ac_check(baseline, revised, cfg):
    master, private = baseline["rooms"][0], baseline["rooms"][-1]
    bed = next(i["rect_mm"] for i in master["furniture"] if i["id"] == "bed")
    leaf = private["doors"][0]["parked_leaf_budget_mm"]
    bshape, lshape = area_shape(bed), area_shape(leaf)
    finished_rear_y = 17630-115
    rear_gap = finished_rear_y-(leaf[1]+leaf[3])
    old_ac = master["hvac_candidate"]
    new_ac = revised["rooms"][0]["hvac_candidate"]
    heights = []
    for top in cfg["door_z_sensitivity_mm"]:
        heights.append({"assumed_door_top_including_head_mm": top,
            "old_ac_vertical_overlap_mm": max(0, min(top, 2630)-2350),
            "old_ac_plan_overlap_sqm": lshape.intersection(area_shape(old_ac["rect_mm"])).area/1e6,
            "new_ac_plan_overlap_sqm": lshape.intersection(area_shape(new_ac["rect_mm"])).area/1e6})
    window = LineString([master["window"]["a"], master["window"]["b"]])
    return {"leaf_budget_mm": leaf, "bed_mm": bed,
        "bed_leaf_x_gap_mm": leaf[0]-(bed[0]+bed[2]),
        "bed_leaf_y_projection_gap_mm": leaf[1]-(bed[1]+bed[3]),
        "bed_leaf_plan_distance_mm": bshape.distance(lshape),
        "correction": "15mm只是y軸投影差；兩個平面矩形最短距離約620.18mm。先前把15mm稱實際床門餘量並不正確。",
        "finished_rear_to_leaf_budget_mm": rear_gap,
        "leaf_95mm_includes_handle": None,
        "hypothetical_extra_handle_cases": [{"extra_if_not_included_mm": e, "remaining_mm": rear_gap-e}
            for e in cfg["extra_handle_sensitivity_mm"]],
        "handle_cases_note": "純假設敏感度；95mm若已含把手不可重扣。未提供實品，不能稱55或75mm是市場標準。",
        "height_cases": heights, "rear_window_x_mm": [750, 3150],
        "leaf_window_x_projection_overlap_mm": max(0, min(3150, leaf[0]+leaf[2])-max(750, leaf[0])),
        "right_ac_to_window_plan_distance_mm": area_shape(new_ac["rect_mm"]).distance(window),
        "right_ac_author": "Codex-only-candidate-not-reviewed-by-Claude",
        "right_ac_route": None, "right_ac_airflow_and_service": "unknown",
        "actual_complete_door_window_ac_pack": None}


def laundry_screen(floor, shaft, repair, relocate):
    f = copy.deepcopy(floor)
    laundry = next(r for r in f["rooms"] if r["id"].endswith(":laundry-base"))
    washer = next(i for r in f["rooms"] for i in r["furniture"] if i["id"].endswith(":washer"))
    sink = next(i for i in laundry["furniture"] if i["id"].endswith(":utility-sink"))
    if relocate:
        washer["rect_mm"] = repair["washer_rect_mm"][:]
    # All cases here are the front layout; retain the original 800mm operation depth.
    wr = washer["rect_mm"]
    op = [wr[0]+wr[2], wr[1], 800, wr[3]]
    sink_op = repair["sink_operation_mm"]
    door = repair["family_door_swept_rectangle_mm"]
    shaft_shape, door_shape = area_shape(shaft), area_shape(door)
    body, operation = area_shape(wr), area_shape(op)
    inset = area_shape(laundry["rect_mm"]).buffer(-115, join_style=2)
    fixed_hits = [{"a": i["id"], "b": j["id"]} for i, j in combinations(laundry["furniture"], 2)
        if collision(area_shape(i["rect_mm"]), area_shape(j["rect_mm"]))]
    return {"floor1": f, "relocated": relocate, "washer_rect_mm": wr, "washer_operation_mm": op,
        "sink_rect_mm": sink["rect_mm"], "sink_operation_mm": sink_op,
        "door_swept_rectangle_mm": door, "fixed_body_hits": fixed_hits,
        "washer_and_operation_inside_115": inset.covers(body) and inset.covers(operation),
        "shaft_washer_overlap_sqm": shaft_shape.intersection(body).area/1e6,
        "shaft_washer_operation_overlap_sqm": shaft_shape.intersection(operation).area/1e6,
        "door_washer_body_overlap_sqm": door_shape.intersection(body).area/1e6,
        "door_washer_operation_overlap_sqm": door_shape.intersection(operation).area/1e6,
        "washer_operation_hits_sink_body": collision(operation, area_shape(sink["rect_mm"])),
        "sink_operation_hits_washer_body": collision(area_shape(sink_op), body),
        "shaft_other_body_hits": [i["id"] for r in f["rooms"] for i in r["furniture"]
            if i is not washer and collision(shaft_shape, area_shape(i["rect_mm"]))],
        "shaft_inspection_access": None, "actual_door_sweep_and_meps": None,
        "sequential_use": "洗衣機操作與家務門開啟預算重疊，必須分時；不把操作區當同時暢通。"}


def stack_and_entry(strict, revised, cfg):
    shaft = revised["shaft"]["rect_mm"]
    public = Polygon(revised["rooms"][2]["polygon_mm"])
    options = []
    for o in strict["options"]:
        rear = o["id"] == "b-rear-split"
        states = []
        for state in o["states"]:
            f = copy.deepcopy(state["floor1"])
            if not rear:
                evidence = laundry_screen(f, shaft, cfg["codex_front_laundry_repair"], relocate=True)
                f = evidence.pop("floor1")
            else:
                evidence = {"shaft_body_hits": [i["id"] for r in f["rooms"] for i in r["furniture"]
                    if collision(area_shape(shaft), area_shape(i["rect_mm"]))],
                    "actual_door_sweep_and_meps": None, "shaft_inspection_access": None}
            states.append({"id": state["id"], "floor1": f, "laundry_check": evidence})
        by_id = {r["id"].split(":")[-1]: r for r in states[0]["floor1"]["rooms"]}
        route_overlap = sum(public.intersection(area_shape(by_id[key]["rect_mm"])).area
            for key in ["left-approach", "storage-front"])/1e6
        options.append({"id": o["id"], "states": states,
            "rear_entry_direct_to_storage": rear, "rear_nominal_door_mm": 1960 if rear else None,
            "1360_segment_required_for_direct_rear_entry": False if rear else None,
            "internal_route_to_shrine_verified": False,
            "front_nominal_connection_mm": 1750 if not rear else None,
            "front_nominal_door_mm": 1730 if not rear else None,
            "front_clear_if_total_frame_230_mm": 1500 if not rear else None,
            "public_bath_over_front_segments_sqm": route_overlap,
            "family_rule_above_carry_route": "owner-does-not-prohibit-bath-or-sewage-above-route",
            "palanquin_required_in_shrine": False, "bedroom_above_storage_prohibited": False,
            "owner_answers_reference": cfg["owner_answers_reference"], "rear_alley_legal_access": "unknown",
            "roof_reference": copy.deepcopy(o["roof_reference"]),
            "roof_protected_footprints_mm": copy.deepcopy(o["roof_protected_footprints_mm"]),
            "shaft_over_roof_protected_sqm": sum(area_shape(shaft).intersection(Polygon(p)).area
                for p in o["protected_polygons_mm"])/1e6,
            "roof_vent_terminal": None, "all_transport_clearances_approved": False, "adopted": False})
    front = strict["options"][1]["states"][0]["floor1"]
    original = laundry_screen(front, shaft, cfg["codex_front_laundry_repair"], relocate=False)
    original.pop("floor1")
    return {"shaft_absolute_mm": shaft, "original_front_washer_conflict": original, "options": options,
        "public_toilet_horizontal_drain_route": None, "private_bath_shaft": None,
        "public_shaft_does_not_resolve_over_route_religious_rule": True}


def critical_inset(shape, net_sqm):
    a, p = shape.area, shape.length
    # Stable orthogonal topology only; source polygons are checked in tests.
    return (p-math.sqrt(p*p-16*(a-net_sqm*1e6)))/8


def area_limits(prior_cfg, strict, revised):
    rows = []
    for shift in [0, 100, 150]:
        c = copy.deepcopy(prior_cfg)
        c["codex_margin_comparison"]["private_bath_front_shift_mm"] = shift
        rooms = proposed_rooms(c, margin=True)
        bedroom, suite = Polygon(rooms[0]["polygon_mm"]), Polygon(rooms[-1]["polygon_mm"])
        bcrit, scrit = critical_inset(bedroom, 20), critical_inset(suite, 4.5)
        rows.append({"suite_front_shift_mm": shift,
            "bedroom_115_sqm": bedroom.buffer(-115, join_style=2).area/1e6,
            "suite_115_sqm": suite.buffer(-115, join_style=2).area/1e6,
            "bedroom_20_critical_inset_mm": bcrit, "suite_4_5_critical_inset_mm": scrit,
            "selected_fixture_reanchored_limit_mm": 125,
            "selected_analytical_min_mm": min(bcrit, scrit, 125)})
    required = {str(n): (math.sqrt(n)+.230)**2 for n in [20, 5, 6]}
    available = 37.56-3.248
    # This is an AREA-ONLY alternative; fixtures, doors and routes have not been redesigned.
    b_rooms = copy.deepcopy(revised["rooms"])
    for r in b_rooms:
        for p in r["polygon_mm"]:
            if p[1] == 13470:
                p[1] = 13675
            elif p[1] == 14880:
                p[1] = 14191
    areas = {k: Polygon(r["polygon_mm"]).buffer(-115, join_style=2).area/1e6
        for k, r in zip(["bedroom", "dry", "public_bath", "private_bath"], b_rooms, strict=True)}
    return {"shift_cases": rows,
        "fixture_limit_scope": "兩條1850mm器具尺寸鏈；須隨完成牆重定位。不是把本案坐標凍住後仍可125，更不是施工工差。",
        "whole_design_tolerance_mm": None,
        "conditional_bound": {"rear_nominal_sqm": 37.56, "fixed_dry_gross_sqm": 3.248,
            "available_sqm": available, "minimum_gross_by_target_sqm": required,
            "minimum_gross_sum_sqm": sum(required.values()),
            "minimum_shortfall_sqm": sum(required.values())-available,
            "assumptions": "固定後段37.56㎡、獨立乾室3.248㎡、三房各自每面115mm直角內縮；不計重疊牆帶的其他口徑。",
            "scope": "此獨立內縮模型內的必要面積界；不是現地無法建造的通用證明，不能套用其他牆線或外框。"},
        "two_bath_targets_area_only": {"bedroom_polygon_mm": b_rooms[0]["polygon_mm"],
            "public_polygon_mm": b_rooms[2]["polygon_mm"], "suite_polygon_mm": b_rooms[-1]["polygon_mm"],
            "areas_115_sqm": areas, "public_after_same_0_04_shaft_sqm": areas["public_bath"]-.04,
            "furnished": False, "whole_route_checked": False, "ready_for_adoption": False,
            "note": "18.238／5.00075／6.00083只是輪廓面積；扣同立管後公衛4.96075，尚未完整試排。不得把名義窄段直接判死路或當通行通過。"},
        "original_targets_unchanged": True}


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    for name, digest in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("B round3 source changed: "+name)
    answers = read_json(root/cfg["owner_answers_reference"])["answers"]
    configured = [{"id": q["id"], "question": q["question"], "answer": q["answer"]} for q in cfg["owner_questions"]]
    if answers != configured or len(answers) != 3 or any(q["answer"] is not False for q in answers):
        raise ContractError("B round3 requires the three recorded owner answers; changed rules require redesign")
    controls = read_json(root/cfg["protected_controls"])
    for name, digest in controls["hashes"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("B round3 protected control changed: "+name)
    provenance = read_json(root/cfg["response_provenance"])
    for field, hashfield in [("original_prompt_file", "prompt_sha256"), ("response_archive", "response_sha256")]:
        if sha256_file(public_path(root, provenance[field])) != provenance[hashfield]:
            raise ContractError("B round3 response evidence changed: "+provenance[field])
    previous = read_json(root/cfg["prior_report"])
    for name, digest in previous["source_hashes"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("B round3 parent dependency changed: "+name)
    prior_cfg, strict = read_json(root/cfg["prior_config"]), read_json(root/cfg["strict_report"])
    baseline, revised = [variant(prior_cfg, strict, cfg, changed) for changed in [False, True]]
    ledger = [
        {"id": "AGREE-100", "topic": "套衛後移100mm研究基線", "state": "both-models-research-agreement", "adopted": False,
         "evidence": "Claude第三輪同意NEW-01優於原案；Codex重算20.2261／4.5067／4.7124。"},
        {"id": "CLARIFY-1360", "topic": "後門直入不經1360", "state": "both-models-scope-correction", "adopted": False,
         "evidence": "只限後巷到庫房；從庫房進神明堂的內部路線仍未知。前門備案另外保留。"},
        {"id": "CORRECT-15", "topic": "床與門片的15mm說法", "state": "claude-correction-independently-confirmed", "adopted": False,
         "evidence": "15是y軸投影差，真正矩形距離620.18；後牆55mm及後窗／門頭另核。"},
        {"id": "NEW-01b", "topic": "公衛便器移150、淋浴移200及200立管候選", "state": "claude-proposal-codex-checked-with-corrections", "adopted": False,
         "evidence": "列明本體不撞；立管扣0.04㎡後公衛4.4667。原前門洗衣機被立管撞0.038㎡。"},
        {"id": "CODEX-WASHER", "topic": "前門洗衣機右移990", "state": "codex-only-deterministic-repair", "adopted": False,
         "evidence": "原650×650機身保留；移位避立管與門掃掠本體，洗衣操作與門開預算分時。Claude未看此修正。"},
        {"id": "CODEX-AC", "topic": "主臥及三樓機盒改右牆", "state": "codex-only-candidate", "adopted": False,
         "evidence": "保950×280×280機盒，避後窗／門片；氣流、冷媒、排水與維修路徑未核，Claude未看。"},
        {"id": "LIMITS", "topic": "115內縮模型中的面積限制", "state": "claude-bound-independently-confirmed-conditionally", "adopted": False,
         "evidence": "固定後段及乾室下，20／5／6理想三房至少缺1.05924㎡；只限明列假設，原需求不改。"},
        {"id": "OWNER-THREE", "topic": "屋主三項家規答覆", "state": "owner-confirmed-not-model-inferred", "adopted": False,
         "evidence": "不必搬進神明堂、不禁轎路上方浴廁污水管、不禁庫房上方臥室。僅限這三項，既有保護規則不變。"},
        {"id": "PENDING", "topic": "保護界線、現地、門組與機電", "state": "no-full-consensus-or-professional-approval", "adopted": False,
         "evidence": "牆帶／梁柱／排氣／開窗權利及完整配管待專業資料；不能從三項家規答覆推出整體採用。"}]
    report = {"schema": "house-b-claude-round3-report-v1", "date": cfg["date"], "config": cfg,
        "source_layout_report_sha256": prior_cfg["source_report_sha256"],
        "response_provenance": provenance, "variants": [baseline, revised],
        "door_and_ac": door_and_ac_check(baseline, revised, cfg), "stack_and_entry": stack_and_entry(strict, revised, cfg),
        "area_limits": area_limits(prior_cfg, strict, revised), "agreement_log": ledger,
        "owner_questions": copy.deepcopy(cfg["owner_questions"]),
        "professional_open_items": ["祭祀／背櫃邊界是否連整道牆厚都須退出", "柱位、法定外框、降板與防水",
            "公衛缺直接外窗；獨立排氣補氣及終端未排", "200管井實際管徑、通氣、橫管坡度與清掃檢修",
            "後巷權利、搬轎裝桿尺寸、人員及足尺搬運", "門高、門擋、把手是否包含在95mm及窗簾／窗型"],
        "original_targets_sqm": copy.deepcopy(prior_cfg["original_targets_sqm"]),
        "protected_controls_unchanged": len(controls["hashes"]), "shapely_version": shapely.__version__,
        "full_consensus": False, "adopted": False, "all_requirements_met": False,
        "rendered_qa": "not-run-static-comparison", "religious_and_engineering_approval": "unknown"}
    names = [CONFIG, *cfg["pinned_sources"], *previous["source_hashes"], cfg["protected_controls"],
        cfg["response_provenance"], provenance["response_archive"], provenance["original_prompt_file"],
        "house_design/b_claude_round3.py", "scripts/export_b_claude_round3.py", "Docs/b-claude-round3-v1.md"]
    report["source_hashes"] = {p: sha256_file(root/p) for p in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

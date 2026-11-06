"""Independent checks of a received Claude proposal; partial agreement stays scoped."""
from __future__ import annotations

import copy
from pathlib import Path

import shapely
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from house_design.abc_next_improvements import square_sweeps
from house_design.b_fengshui_strict import area_shape, collision, measured_room, rect_ring, translate
from house_design.c_coordination import public_path
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash

CONFIG = "inputs/b-claude-crosscheck.json"
OUT = "structured/coordination/b-claude-crosscheck-v1"


def bath_room(cfg, rectangle, private=False):
    kind = "private_bath" if private else "public_bath"
    spec, inset = cfg[kind], cfg["bath_layout_inset_mm"]
    origin = [rectangle[0]+inset, rectangle[1]+inset]
    fixtures = [{"id": key, "rect_mm": translate(value, origin),
        "operation_mm": translate(spec["operations_local_mm"][key], origin)} for key, value in spec["fixtures_local_mm"].items()]
    finished = [*origin, rectangle[2]-2*inset, rectangle[3]-2*inset]
    if private:
        lo, hi = spec["door_nominal_y_mm"]
        door = {"a": [rectangle[0], lo], "b": [rectangle[0], hi], "nominal_mm": hi-lo,
            "assumed_clear_mm": hi-lo-230, "hinge": "rear", "operation": "向主臥外開，後端鉸鏈預算，非已選成品。",
            "parked_leaf_budget_mm": [rectangle[0]-1130, hi-95, 1130, 95],
            "swept_rect_mm": [rectangle[0]-1130, lo, 1130, 1130]}
        inside = spec["inside_approach_absolute_mm"]
        outside = [rectangle[0]-1015, lo+115, 900, 900]
        window = {"a": [4750, 17630], "b": [5650, 17630], "legal": "unknown"}
    else:
        lo, hi = spec["door_nominal_x_mm"]
        door = {"a": [lo, rectangle[1]], "b": [hi, rectangle[1]], "nominal_mm": hi-lo,
            "assumed_clear_mm": hi-lo-230, "hinge": "right", "operation": "向前乾區外開；完整門組與消防待核。",
            "parked_leaf_budget_mm": [hi-95, rectangle[1]-1130, 95, 1130],
            "swept_rect_mm": [lo, rectangle[1]-1130, 1130, 1130]}
        inside = translate(spec["inside_approach_local_mm"], origin)
        outside = [lo+115, rectangle[1]-1015, 900, 900]
        window = None
    room = measured_room(kind.replace("_", "-"), "套衛" if private else "左前公衛", rect_ring(rectangle), fixtures, [door], window)
    room.update(illustrative_finished_rect_mm=finished, inside_approach_mm=inside, outside_approach_mm=outside,
        actual_product_pack=None, actual_finished_clear_mm=None, drainage_terminal=None)
    bodies = [[a["id"], b["id"]] for n, a in enumerate(fixtures) for b in fixtures[n+1:]
        if collision(area_shape(a["rect_mm"]), area_shape(b["rect_mm"]))]
    operation_hits = [[a["id"], b["id"]] for a in fixtures for b in fixtures if a["id"] != b["id"]
        and collision(area_shape(a["operation_mm"]), area_shape(b["rect_mm"]))]
    room["screen"] = {"body_hits": bodies, "operation_body_hits": operation_hits,
        "inside_arrival_hits": [i["id"] for i in fixtures if collision(area_shape(inside), area_shape(i["rect_mm"]))],
        "all_listed_inside": all(area_shape(finished).covers(area_shape(i[key])) for i in fixtures for key in ["rect_mm", "operation_mm"]),
        "inside_arrival_contained": area_shape(finished).covers(area_shape(inside)),
        "shared_operation_pairs": [[a["id"], b["id"]] for n, a in enumerate(fixtures) for b in fixtures[n+1:]
            if collision(area_shape(a["operation_mm"]), area_shape(b["operation_mm"]))]}
    return room


def proposed_rooms(cfg, margin=False):
    polygon = copy.deepcopy(cfg["upper"]["bedroom_polygon_mm"])
    u = cfg["upper"]
    private_rect = u["private_bath_rect_mm"][:]
    if margin:
        delta = cfg["codex_margin_comparison"]["private_bath_front_shift_mm"]
        for p in polygon:
            if p[1] == private_rect[1]:
                p[1] += delta
        private_rect[1] += delta
        private_rect[3] -= delta
    fixtures = [{"id": key, "rect_mm": value[:]} for key, value in u["bedroom_fixtures_mm"].items()]
    for i in fixtures:
        r = i["rect_mm"]
        i["operation_mm"] = ([r[0]+r[2], r[1], 600, r[3]] if i["id"] in {"bed", "wardrobe"}
            else [r[0], r[1]+r[3], r[2], 700])
    lo, hi = u["bedroom_entry_x_mm"]
    bedroom = measured_room("master", "L形主臥", polygon, fixtures,
        [{"a": [lo, 11370], "b": [hi, 11370], "nominal_mm": hi-lo, "assumed_clear_mm": hi-lo-230,
            "operation": "候選門，向房內開；門片／成品／救援仍待核。"}],
        {"a": [u["bedroom_rear_window_x_mm"][0], 17630], "b": [u["bedroom_rear_window_x_mm"][1], 17630], "legal": "unknown"})
    # The air conditioner cannot remain in the new private bath at the original x4200.
    bedroom["hvac_candidate"] = {"id": "B-AC03", "rect_mm": [u["ac_new_x_mm"]-475, u["codex_ac_new_center_y_mm"]-140, 950, 280],
        "bottom_relative_z_mm": 2350, "route": "not-re-engineered", "manual": None}
    drylo, dryhi = u["dry_room_entry_x_mm"]
    dry = measured_room("dry-protection", "獨立乾保護室", rect_ring(u["dry_room_rect_mm"]),
        doors=[{"a": [drylo, 11370], "b": [dryhi, 11370], "nominal_mm": dryhi-drylo,
            "assumed_clear_mm": dryhi-drylo-230, "operation": "前壁獨立門，向室內開；不穿臥室。"}])
    public, private = bath_room(u, u["public_bath_rect_mm"]), bath_room(u, private_rect, private=True)
    bedroom["doors"].append(copy.deepcopy(private["doors"][0]))
    return [bedroom, dry, public, private]


def analyze_variant(cfg, previous, rooms, variant_id, author):
    shapes = [Polygon(r["polygon_mm"]) for r in rooms]
    rear_frame = box(0, 11370, 6000, 17630)
    protected = unary_union([Polygon(p) for p in previous["options"][0]["protected_polygons_mm"]])
    backing = Polygon(rooms[1]["polygon_mm"])
    palanquin = area_shape(previous["options"][0]["palanquin_rect_mm"])
    bedroom = rooms[0]
    bed_shape = Polygon(bedroom["polygon_mm"])
    inset = cfg["upper"]["bath_layout_inset_mm"]
    inner_bed = bed_shape.buffer(-inset, join_style=2)
    sweeps = square_sweeps(cfg["upper"]["bedroom_route_points_mm"], cfg["upper"]["bedroom_route_square_mm"])
    routes = {"points_mm": cfg["upper"]["bedroom_route_points_mm"], "sweeps_mm": sweeps,
        "all_inside_115": all(inner_bed.covers(area_shape(r)) for r in sweeps),
        "body_hits": [{"segment": n, "body": i["id"]} for n, r in enumerate(sweeps) for i in bedroom["furniture"]
            if collision(area_shape(r), area_shape(i["rect_mm"]))],
        "actual_whole_route": "unknown"}
    partition = {"gap_or_outside_sqm": rear_frame.symmetric_difference(unary_union(shapes)).area/1e6,
        "overlap_sqm": (sum(s.area for s in shapes)-unary_union(shapes).area)/1e6}
    partition["status"] = "listed-geometry-clear" if all(v == 0 for v in partition.values()) else "conflict"
    # Frame sensitivity is recalculated from the real L polygon and each independent bath.
    cases = []
    targets = cfg["original_targets_sqm"]
    for d in cfg["upper"]["inset_sensitivity_mm"]+[116]:
        areas = {key: round(shape.buffer(-d, join_style=2).area/1e6, 6)
            for key, shape in zip(["bedroom", "dry_room", "public_bath", "private_bath"], shapes, strict=True)}
        cases.append({"inset_each_mm": d, **areas,
            "bedroom_meets_20": areas["bedroom"] >= targets["bedroom_target"],
            "public_meets_min": areas["public_bath"] >= targets["public_bath_min"],
            "private_meets_min": areas["private_bath"] >= targets["private_bath_min"],
            "both_bath_targets": areas["public_bath"] >= targets["public_bath_target"] and areas["private_bath"] >= targets["private_bath_target"]})
    current = next(c for c in cases if c["inset_each_mm"] == inset)
    wet = [{"id": r["id"], "over_protected_sqm": Polygon(r["polygon_mm"]).intersection(protected).area/1e6,
        "over_palanquin_sqm": Polygon(r["polygon_mm"]).intersection(palanquin).area/1e6,
        "distance_to_backing_mm": Polygon(r["polygon_mm"]).distance(backing),
        "status": "listed-geometry-clear" if not collision(Polygon(r["polygon_mm"]), protected)
            and not collision(Polygon(r["polygon_mm"]), palanquin) else "conflict"} for r in rooms[2:]]
    floor_clear = box(115, 9215, 5885, 11255)  # A local rectangle within retained, open-front dry area.
    arrivals = []
    for r in rooms[2:]:
        door = r["doors"][0]
        outside = area_shape(r["outside_approach_mm"])
        target = inner_bed if r["id"] == "private-bath" else floor_clear
        obstacles = bedroom["furniture"] if r["id"] == "private-bath" else []
        collisions = [i["id"] for i in obstacles if collision(area_shape(door["swept_rect_mm"]), area_shape(i["rect_mm"]))]
        arrivals.append({"room": r["id"], "outside_arrival_inside_budget": target.covers(outside),
            "parked_leaf_hits_arrival": collision(area_shape(door["parked_leaf_budget_mm"]), outside),
            "swept_rectangle_body_hits": collisions,
            "complete_product_and_all_states": "unknown"})
    bed = next(i["rect_mm"] for i in bedroom["furniture"] if i["id"] == "bed")
    private_door = rooms[-1]["doors"][0]
    retained_front = previous["options"][0]["upper_floors"][0]["retained_front"]
    roof = previous["options"][0]["roof_reference"]
    rear_rect = [115, 13585, 3670, 3930]
    third_floor = copy.deepcopy(rooms)
    third_floor[0]["id"], third_floor[0]["name"] = "guest", "L形客房"
    third_floor[0]["hvac_candidate"]["id"] = "B-AC04"
    last = third_floor[-1]
    third_floor[-1] = measured_room("rear-dry", "後段乾式預留（不新增套衛）", last["polygon_mm"],
        doors=copy.deepcopy(last["doors"]), window=last["window"])
    return {"id": variant_id, "author": author, "rooms": rooms, "partition": partition, "wet_projection": wet,
        "bedroom_over_protected_sqm": bed_shape.intersection(protected).area/1e6,
        "bedroom_bodies_inside_115": all(inner_bed.covers(area_shape(i["rect_mm"])) for i in bedroom["furniture"]),
        "bedroom_operations_inside_115": all(inner_bed.covers(area_shape(i["operation_mm"])) for i in bedroom["furniture"]),
        "route": routes, "area_sensitivity": cases, "current_inset_case": current,
        "door_arrivals": arrivals, "bed_to_rear_115_gap_mm": 17630-115-(bed[1]+bed[3]),
        "bed_rear_to_open_private_leaf_mm": private_door["parked_leaf_budget_mm"][1]-(bed[1]+bed[3]),
        "bedroom_hvac_contained": inner_bed.covers(area_shape(bedroom["hvac_candidate"]["rect_mm"])),
        "bedroom_rear_inscribed_rect_mm": rear_rect,
        "bedroom_rear_inscribed_rect_sqm": area_shape(rear_rect).area/1e6,
        "rear_inscribed_rect_contained": inner_bed.covers(area_shape(rear_rect)),
        "bedroom_area_quality_note": "20㎡包含狹長入口與轉折／梳妝區；後段可完整內接矩形約14.4231㎡，不能只用總面積認定方正寬敞。",
        "retained_front_floor2": retained_front, "roof_reference": roof, "third_floor_rooms": third_floor,
        "targets_changed": False, "all_requirements_met": False, "adopted": False,
        "fengshui_overall_approval": "unknown", "professional_approval": "unknown",
        "third_floor": "同房形與左前公衛；右後保持乾式預留，不新增套衛。"}


def carry_and_drain(previous, new_public):
    rows = []
    pub = Polygon(new_public["polygon_mm"])
    for o in previous["options"]:
        daily = next(st for st in o["states"] if st["id"] == "daily")["floor1"]
        by_id = {r["id"].split(":")[-1]: r for r in daily["rooms"]}
        rear = o["id"] == "b-rear-split"
        store = by_id["storage"]
        rear_door = next((d for d in store["features"]["doors"] if d["face"] == "rear"), None)
        rows.append({"option": o["id"], "floor1": daily,
            "rear_entry_nominal_mm": rear_door["width_mm"] if rear_door else None,
            "left_segment_nominal_mm": by_id["left-approach"]["rect_mm"][2],
            "left_segment_required_for_preferred_rear_entry": False if rear else None,
            "front_door_nominal_mm": 1730 if not rear else None,
            "front_door_clear_if_230_total_mm": 1500 if not rear else None,
            "front_segment_clear_if_230_total_mm": by_id["left-approach"]["rect_mm"][2]-230 if not rear else None,
            "under_public_bath_intersections": [{"id": key, "overlap_sqm": round(pub.intersection(area_shape(by_id[key]["rect_mm"])).area/1e6, 6)}
                for key in ["left-approach", "storage-front", "laundry-front", "laundry-base"] if key in by_id],
            "drainage_candidate_zone": "公衛右側下方家務區可研究，實際立管尺寸／位置尚未選定。禁止侵入前門搬轎接段或背櫃保護區。",
            "selected_stack_mm": None, "actual_full_carried_route": "unknown",
            "interpretation": "後門直接進後左庫，1360不在此必要路線；不得稱該段已達1500。" if rear else
                "前門備案需經1750接段與1730名義門；230假設後僅1500，沒有產品／施工餘量。"})
    return rows


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    for key, hashkey in [("source_report", "source_report_sha256"), ("previous_study", "previous_study_sha256")]:
        if sha256_file(public_path(root, cfg[key])) != cfg[hashkey]:
            raise ContractError("B Claude crosscheck source changed: "+cfg[key])
    controls = read_json(root/cfg["protected_controls"])
    for name, digest in controls["hashes"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("Protected control changed: "+name)
    provenance = read_json(root/cfg["response_provenance"])
    if sha256_file(root/provenance["original_prompt_file"]) != provenance["original_prompt_sha256"]:
        raise ContractError("The prompt that produced Claude's response has changed")
    previous = read_json(root/cfg["previous_study"])
    claude = analyze_variant(cfg, previous, proposed_rooms(cfg), "claude-front-dry", "Claude回覆／Codex獨立核算")
    margin = analyze_variant(cfg, previous, proposed_rooms(cfg, margin=True), "codex-margin-100", "Codex新比較，尚未送回Claude確認")
    actual = claude["current_inset_case"]
    claims = cfg["source_claims_to_recheck"]
    prior_case = next(c for c in previous["options"][0]["area_sensitivity"] if c["inset_each_mm"] == 115)
    gain = round(actual["public_bath"]+actual["private_bath"]-prior_case["public_bath_sqm"]-prior_case["private_bath_sqm"], 6)
    checks = {"bedroom_115_sqm": actual["bedroom"], "public_bath_115_sqm": actual["public_bath"],
        "private_bath_115_sqm": actual["private_bath"], "bathroom_gain_vs_previous_115_sqm": gain}
    comparisons = [{"claim": key, "claude": value, "codex": checks[key], "matches": abs(value-checks[key]) < .00001}
        for key, value in claims.items()]
    if not all(c["matches"] for c in comparisons):
        raise ContractError("Claude source claims do not match the independent geometry calculation")
    agreement = [
        {"id": "AGREE-01", "topic": "前方乾區三入口／四區拓樸", "state": "codex-accepts-received-proposal-for-comparison",
         "evidence": "四區37.56㎡無重疊／缺漏；完整臥室與濕區退出祭祀／乾背櫃投影。", "adopted": False},
        {"id": "AGREE-02", "topic": "面積算術與原目標不能偷改", "state": "independently-confirmed",
         "evidence": "115假設主臥20.0161、公衛4.5067、套衛4.8994；原5＋6仍差1.5939㎡。", "adopted": False},
        {"id": "AGREE-03", "topic": "兩衛獨立，暫不改共用雙門浴室", "state": "codex-accepts-received-preference",
         "evidence": "避免把同一濕區算兩次或讓訪客穿主臥；正式配置尚未採用。", "adopted": False},
        {"id": "CLARIFY-01", "topic": "1360接段的必要路線範圍", "state": "clarification-for-next-discussion",
         "evidence": "若經過即不足1500，這句同意；後門直接進庫不經1360，不能把它列成後門路線必經瓶頸。", "adopted": False},
        {"id": "NEW-01", "topic": "套衛前牆後移100換0.21㎡主臥餘量", "state": "not-reviewed-by-claude",
         "evidence": "Codex比較：115假設20.2261／4.5067／4.7124；仍未達兩衛目標，未採用。", "adopted": False},
        {"id": "NEW-02", "topic": "主臥含狹長入口／機身回套", "state": "not-reviewed-by-claude",
         "evidence": "後段可內接14.4231㎡矩形；室內機候選再向內115避免超出假設完成牆。完整鏡面／氣流／路線待核。", "adopted": False},
        {"id": "OPEN-01", "topic": "公衛立管／完成牆／原面積目標", "state": "unresolved-no-full-consensus",
         "evidence": "公衛貼保護區名義界線，新增排水未定位；整體尚無施工、宗教或搬運核可。", "adopted": False}]
    report = {"schema": "house-b-claude-crosscheck-report-v1", "date": "2026-11-06", "config": cfg,
        "source_layout_report_sha256": cfg["source_report_sha256"], "previous_study_sha256": cfg["previous_study_sha256"],
        "response_provenance": provenance, "claim_checks": comparisons, "variants": [claude, margin],
        "carry_and_drain": carry_and_drain(previous, claude["rooms"][2]), "agreement_log": agreement,
        "protected_controls_unchanged": len(controls["hashes"]), "shapely_version": shapely.__version__,
        "full_consensus": False, "adopted": False, "all_requirements_met": False,
        "rendered_qa": "not-run-static-comparison", "religious_and_engineering_approval": "unknown",
        "previous_study_summary": {"options": len(previous["options"]), "case_115": prior_case}}
    names = [CONFIG, cfg["previous_study"], cfg["response_provenance"], cfg["response_archive"], cfg["protected_controls"],
        "house_design/b_claude_crosscheck.py", "house_design/b_fengshui_strict.py", "house_design/abc_next_improvements.py",
        "house_design/c_coordination.py", "house_design/contracts.py", "scripts/export_b_claude_crosscheck.py",
        "scripts/export_b_fengshui_strict.py", "scripts/export_abc_next_improvements.py", "inputs/requirements.json",
        "Docs/claude-b-fengshui-followup-v3.md", "scripts/review_b_fengshui_with_claude.py"]
    report["source_hashes"] = {p: sha256_file(root/p) for p in names}
    report["report_hash"] = stable_hash(report)
    return report

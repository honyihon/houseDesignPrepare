"""Local first-floor landing/tread screening for the frozen P4 discharge candidate."""
from __future__ import annotations

import copy
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

from house_design.b_ktv_stair_options import incoming_steps
from house_design.b_upper_replan import hit, rect, sweep
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-front-drop-stair.json"
OUT = "structured/coordination/b-front-drop-stair-v1"


def stair_screen(cfg, q3, p4):
    source = copy.deepcopy(q3["original_stairs_by_floor"]["floor-1"])
    fp, g = source["footprint"], source["geometry"]
    if source["height_mm"] != 4000 or g["risers"] != 24 or g["flight_width_mm"] != 1000 or fp["w_mm"] != 2200:
        raise ContractError("Ground screen must use the frozen first-floor24-riser stair")
    landing = [fp["x_mm"], fp["y_mm"], fp["w_mm"], g["landing_mm"]]
    floor = rect(landing)
    routes = [{**r, "width_mm": cfg["local_route_width_mm"], "inside_original_landing_without_new_shaft": floor.covers(sweep(r["points_mm"], cfg["local_route_width_mm"])),
        "actual_door_or_full_access_approval": "unknown"} for r in cfg["local_routes"]]
    if not all(r["inside_original_landing_without_new_shaft"] for r in routes):
        raise ContractError("Only compare explicitly local routes on the original landing")
    treads = incoming_steps(source)
    column_top = p4["drainage"]["P4_best_case_minimum_remaining_mm"]
    rows = []
    for candidate in cfg["candidates"]:
        shape = rect(candidate["rect_mm"])
        overlaps = [{"route": r["id"], "sqm": round(shape.intersection(sweep(r["points_mm"], r["width_mm"])).area/1e6, 6)} for r in routes
            if hit(shape, sweep(r["points_mm"], r["width_mm"]))]
        step_hits = [{"id": s["id"], "top_z_mm": round(s["top_z_mm"], 3), "plan_overlap_sqm": round(shape.intersection(rect(s["rect_mm"])).area/1e6, 6)}
            for s in treads if hit(shape, rect(s["rect_mm"])) and source["base_mm"] <= s["top_z_mm"] <= column_top]
        status = "conflicts-listed-platform-routes" if overlaps else "intersects-listed-treads" if step_hits else "unverified-no-clearance-approval"
        rows.append({**candidate, "inside_nominal_stair_room": rect([0, 3900, 2400, 5200]).covers(shape),
            "landing_overlap_sqm": round(shape.intersection(floor).area/1e6, 6), "local_route_hits": overlaps,
            "tread_hits_in_hypothetical_vertical_column": step_hits, "status": status, "adopted": False,
            "new_structural_hole_or_actual_pipe_route_approved": False})
    gap = fp["w_mm"]-2*g["flight_width_mm"]
    return {"source": source, "landing_mm": landing, "local_routes": routes, "treads": treads,
        "hypothetical_column_z_mm": [source["base_mm"], column_top],
        "central_gap_mm": [fp["x_mm"]+g["flight_width_mm"], fp["y_mm"]+g["departure_offset_mm"], gap, g["run_mm"]],
        "central_gap_width_mm": gap, "required_reserved_shaft_width_mm": 400,
        "candidates": rows, "all_listed_candidates_conflict": all(r["local_route_hits"] or r["tread_hits_in_hypothetical_vertical_column"] for r in rows),
        "entire_human_route_all_possible_chases_headroom_or_structure_checked": False}


def ground_states(cfg, ground, p4, screen):
    original = cfg["candidates"][0]["rect_mm"]
    if original != p4["drainage"]["ground_candidate_mm"]:
        raise ContractError("G0 must equal the frozen P4 ground-drop candidate")
    rows = []
    for option in ground["stack_and_entry"]["options"]:
        protected = unary_union([Polygon(p) for p in option["roof_protected_footprints_mm"]])
        for state in option["states"]:
            f = state["floor1"]
            stair = next(r for r in f["rooms"] if r["id"].endswith(":stair1"))
            arcade = next(r for r in f["rooms"] if r["id"].endswith(":garage"))
            storage = next(r for r in f["rooms"] if r["id"].endswith(":storage"))
            street = next(d for d in stair["features"]["doors"] if d["face"] == "front")
            side = next(d for d in stair["features"]["doors"] if d["face"] == "right")
            street_center = stair["rect_mm"][0]+stair["rect_mm"][2]*street["ratio"]
            side_center = stair["rect_mm"][1]+stair["rect_mm"][3]*side["ratio"]
            if abs(street_center-1200) > .01 or abs(side_center-4400) > .01:
                raise ContractError("Source ground doors no longer match the local study datums")
            shape = rect(original)
            rows.append({"option": option["id"], "state": state["id"], "floor1_source_hash": stable_hash(f),
                "nominal_stair_room_mm": stair["rect_mm"], "nominal_front_door_center_x_mm": street_center,
                "nominal_side_door_center_y_mm": round(side_center, 3), "G0_over_stair_sqm": round(shape.intersection(rect(stair["rect_mm"])).area/1e6, 6),
                "G0_over_entrance_landing_sqm": round(shape.intersection(rect(screen["landing_mm"])).area/1e6, 6),
                "G0_over_arcade_sqm": round(shape.intersection(rect(arcade["rect_mm"])).area/1e6, 6),
                "G0_over_sacred_or_backing_sqm": round(shape.intersection(protected).area/1e6, 6),
                "G0_over_palanquin_storage_sqm": round(shape.intersection(rect(storage["rect_mm"])).area/1e6, 6),
                "G0_fixed_body_hits": [i["id"] for r in f["rooms"] for i in r["furniture"] if hit(shape, rect(i["rect_mm"]))],
                "no_furniture_hit_means_free_shaft": False, "ground_geometry_modified": False,
                "full_carry_route_door_motion_and_care_revalidated": False})
    if len(rows) != 6 or {r["option"] for r in rows} != {"b-rear-split", "b-front-split"}:
        raise ContractError("Keep the two independent ground versions and all three states")
    return rows


def build(root):
    root, cache = Path(root), {}
    cfg = read_json(root/CONFIG)
    if (cfg.get("schema") != "house-b-front-drop-stair-v1" or cfg.get("adopted") is not False
            or cfg["local_route_width_mm"] != 700
            or [r["id"] for r in cfg["candidates"]] != ["G0", "G1", "G2", "G3"]
            or any(r["rect_mm"][2:] != [400, 400] for r in cfg["candidates"])):
        raise ContractError("Keep the local fixed-size ground-drop alternatives as unadopted screens")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen ground-drop source changed: "+name)
    p4, q3, ground = [read_json(root/cfg[k]) for k in ["p4_report", "q3_report", "ground_report"]]
    for parent in [p4, q3, ground]:
        for name, expected in parent["source_hashes"].items():
            if digest(root, name, cache) != expected:
                raise ContractError("Ground-drop source drift: "+name)
    controls = read_json(root/cfg["protected_controls"])["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    screen = stair_screen(cfg, q3, p4)
    states = ground_states(cfg, ground, p4, screen)
    protected = unary_union([Polygon(p) for p in ground["stack_and_entry"]["options"][0]["roof_protected_footprints_mm"]])
    extra_strip = [2400, 3900, 200, 5200]
    width = {"source_flight_width_mm": 1000, "source_stair_footprint_width_mm": 2200,
        "source_gap_width_mm": screen["central_gap_width_mm"], "reserved_shaft_width_mm": 400,
        "two_flights_plus_shaft_width_before_new_chase_walls_mm": 2400,
        "minimum_extra_nominal_footprint_width_before_chase_walls_mm": 200,
        "hypothetical_same_outer_edges_room_widening_mm": extra_strip,
        "hypothetical_widening_over_sacred_front_sqm": round(rect(extra_strip).intersection(protected).area/1e6, 6),
        "hypothetical_widening_approved_or_minimum_legal_stair_width_selected": False}
    report = {"schema": "house-b-front-drop-stair-report-v1", "date": cfg["date"], "config": cfg,
        "p4_report_hash": p4["report_hash"], "q3_report_hash": q3["report_hash"], "ground_report_hash": ground["report_hash"],
        "stair_screen": screen, "ground_states": states, "width_boundary": width,
        "source_P4_minimum_section_budget_mm": p4["drainage"]["P4_best_case_minimum_remaining_mm"],
        "source_P4_positive_section_budget_resolves_ground_conflict": False,
        "G0_can_continue_as_free_shaft_without_landing_redesign": False,
        "no_all_global_solutions_possible_claim": True,
        "recommended_sequence": ["G0不再當原平台內免費落管；保留P4器具方向供完整建築／機電重排，不進施工圖。", "先由建築師同版整合管井、原1000梯寬、入口平台及兩門，結構與機電核梁板／通氣／清掃；不占騎樓或侵祭祀。", "若整合仍不成立，再比較完整濕區拓樸及代價；P1也缺濕茶水，回退不等於全部滿足，不預設泵或抬地坪。", "找不到更好解法時可用獨立Claude討論稿交叉研究；長討論另終端執行，本輪沒有回應或共識。"],
        "protected_controls_unchanged": len(controls), "actual_site_or_product_data_received": 0,
        "primary_abc_or_3d_changed": False, "adopted": False, "all_original_requirements_met": False,
        "rendered_qa": "not-run", "professional_approval": "unknown",
        "conclusion": "原G0占1F入口平台0.16㎡，碰兩條局部試線；G1右角仍擋側門，中央200縫不夠400且G2／G3穿踏步投影。四個明列位置都不能直接套現行梯／門，不代表所有建築整合無解。保P4短支管研究但先做井、平台及梁板整合，不縮梯、不占騎樓、不放寬祭祀，未併主3D。"}
    names = [CONFIG, *cfg["pinned_sources"], *p4["source_hashes"], *q3["source_hashes"], *ground["source_hashes"], cfg["protected_controls"],
        "house_design/b_front_drop_stair.py", "scripts/export_b_front_drop_stair.py", "Docs/b-front-drop-stair-v1.md", "Docs/claude-b-front-drop-brief-v1.md"]
    report["source_hashes"] = {n: digest(root, n, cache) for n in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

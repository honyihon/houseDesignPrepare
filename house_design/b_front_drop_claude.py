"""Cross-check the owner-run Claude response and conditional under-return drain routes."""
from __future__ import annotations

import math
from pathlib import Path

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from house_design.b_upper_replan import hit, rect, sweep
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-front-drop-claude-options.json"
OUT = "structured/coordination/b-front-drop-claude-v1"


def section_cases(cfg, spec, source, rows):
    fp, g = source["footprint"], source["geometry"]
    rise = source["height_mm"]/g["risers"]
    slope = rise/g["tread_mm"]
    cosine = 1/math.hypot(1, slope)
    start_y = fp["y_mm"]+g["departure_offset_mm"]
    front_y, rear_y = spec["shaft_mm"][1], spec["shaft_mm"][1]+spec["shaft_mm"][3]
    def nose(y):
        return source["base_mm"]+source["height_mm"]-rise-slope*(y-start_y)
    result = []
    for waist in cfg["normal_stair_waist_cases_mm"]:
        soffit = nose(rear_y)-waist/cosine
        for extra in cfg["extra_fitting_above_original_package_cases_mm"]:
            pipe_top = max(r["conservative_400_chase_top_before_fitting_growth_mm"] for r in rows)+extra
            gap = soffit-pipe_top-cfg["separate_gap_above_package_to_soffit_mm"]
            result.append({"normal_stair_waist_mm": waist, "front_optimistic_soffit_mm": round(nose(front_y)-waist/cosine, 3),
                "rear_optimistic_soffit_mm": round(soffit, 3), "extra_fitting_above_original_package_mm": extra,
                "highest_chase_top_budget_mm": round(pipe_top, 3), "separate_gap_above_package_mm": cfg["separate_gap_above_package_to_soffit_mm"],
                "margin_after_separate_gap_mm": round(gap, 3), "fits_assumed_soffit_budget_only": gap >= 0,
                "actual_stair_pipe_access_fire_or_religious_approval": False})
    return result


def candidate(cfg, spec, parent, p4, ground):
    screen = parent["stair_screen"]
    source = screen["source"]
    points = spec["header_route_mm"]
    if (points[0] != [315, 1980] or points[-1] != [spec["shaft_mm"][0]+200, spec["shaft_mm"][1]+200]
            or any(b[1] < a[1] or a[0] != b[0] and a[1] != b[1] for a, b in zip(points, points[1:], strict=False))):
        raise ContractError("Keep explicit downstream orthogonal header routes and the400mm shaft centre")
    if spec["id"] == "G4D" and (spec["drop_point_mm"] != [315, 4700] or spec["interior_vertical_drop_mm"] != 500 or spec["drop_point_mm"] not in points):
        raise ContractError("G4D must declare its new500mm indoor drop at the exact4700mm station")
    if spec["id"] != "G4D" and (spec["interior_vertical_drop_mm"] != 0 or spec["drop_point_mm"] is not None):
        raise ContractError("Do not silently add vertical drops to Claude's original proposals")
    length = LineString(points).length
    assumptions = p4["drainage"]["assumptions"]
    denominator = assumptions["illustrative_slope_denominator"]
    if denominator != 50:
        raise ContractError("Keep the original illustrative slope, not a flatter selected pipe design")
    rows = []
    for old in p4["drainage"]["rows"]:
        total = old["branch_length_mm"]+length
        package_top = assumptions["floor2_level_mm"]-min(assumptions["illustrative_structure_depths_mm"])-total/denominator-spec["interior_vertical_drop_mm"]
        rows.append({"fixture": old["fixture"], "P4_branch_length_mm": old["branch_length_mm"], "new_header_length_mm": length,
            "total_horizontal_length_mm": total, "horizontal_fall_mm": round(total/denominator, 3),
            "additional_vertical_drop_mm": spec["interior_vertical_drop_mm"], "pipe_package_top_at_riser_center_budget_mm": round(package_top, 3),
            "conservative_400_chase_top_before_fitting_growth_mm": round(package_top+spec["shaft_mm"][3]/2/denominator, 3),
            "lowest_budget_including_original_pipe_support_and_access_mm": round(package_top-min(assumptions["pipe_support_envelopes_mm"])-assumptions["access_allowance_mm"], 3),
            "actual_outlet_invert_and_products_known": False})
    protected = unary_union([Polygon(p) for p in ground["stack_and_entry"]["options"][0]["roof_protected_footprints_mm"]])
    storage = rect(next(r["rect_mm"] for r in ground["stack_and_entry"]["options"][0]["states"][0]["floor1"]["rooms"] if r["id"].endswith(":storage")))
    pipe_plan = sweep(points, 400)
    body = rect(spec["shaft_mm"])
    fp, g = source["footprint"], source["geometry"]
    return_run = rect([fp["x_mm"]+(0 if spec["mirror_first_floor_stair"] else fp["w_mm"]-g["flight_width_mm"]),
        fp["y_mm"]+g["departure_offset_mm"], g["flight_width_mm"], g["run_mm"]])
    if not return_run.covers(body):
        raise ContractError("The soffit comparison applies only inside the stated return-flight footprint")
    if hit(pipe_plan.union(body), protected.union(storage)):
        raise ContractError("New header/chase enters listed sacred, backing or storage protection")
    landing = rect(screen["landing_mm"])
    growth = []
    for value in cfg["chase_outward_growth_cases_mm"]:
        x, y, w, h = spec["shaft_mm"]
        shape = rect([x-value, y-value, w+2*value, h+2*value])
        growth.append({"extra_outward_growth_each_face_mm": value, "landing_overlap_sqm": round(shape.intersection(landing).area/1e6, 6),
            "body_size_or_growth_selected_as_product": False})
    return {**spec, "offset_length_mm": length, "fixture_rows": rows,
        "soffit_cases": section_cases(cfg, spec, source, rows),
        "nominal_shaft_plan_over_original_landing_sqm": round(body.intersection(landing).area/1e6, 6),
        "shaft_front_to_original_platform_rear_mm": spec["shaft_mm"][1]-(screen["landing_mm"][1]+screen["landing_mm"][3]),
        "same_original_stair_local_route_hits": None if spec["mirror_first_floor_stair"] else [r["id"] for r in screen["local_routes"] if hit(body, sweep(r["points_mm"], r["width_mm"]))],
        "mirror_route_and_all_upper_stairs_require_new_design": spec["mirror_first_floor_stair"],
        "existing_Q3_RF_results_inherited_as_approval": False, "chase_growth_cases": growth,
        "ground_arcade_floor_obstruction_sqm": round(body.intersection(rect([0, 0, 6000, 3900])).area/1e6, 6),
        "overhead_pipe_plan_over_arcade_sqm": round(pipe_plan.intersection(rect([0, 0, 6000, 3900])).area/1e6, 6),
        "pipe_plan_over_sacred_backing_storage_sqm": 0,
        "whole_landing_door_care_palanquin_or_fire_clearance_approved": False,
        "indoor_required_clear_height_mm": None, "adopted": False}


def build(root):
    root, cache = Path(root), {}
    cfg = read_json(root/CONFIG)
    if (cfg.get("schema") != "house-b-front-drop-claude-options-v1" or cfg.get("adopted") is not False
            or [c["id"] for c in cfg["candidates"]] != ["G4", "G4D", "G5"]
            or any(c["shaft_mm"][2:] != [400, 400] for c in cfg["candidates"])
            or cfg["normal_stair_waist_cases_mm"] != [150, 200, 250, 300]
            or cfg["extra_fitting_above_original_package_cases_mm"] != [0, 25, 50]
            or cfg["separate_gap_above_package_to_soffit_mm"] != 50
            or cfg["chase_outward_growth_cases_mm"] != [0, 25, 50]
            or [r["id"] for r in cfg["claim_review"]] != [f"CC-{i:02d}" for i in range(1, 11)]):
        raise ContractError("Keep independent, explicitly hypothetical original/proposed under-return comparisons")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen Claude drop study source changed: "+name)
    provenance = read_json(root/cfg["provenance"])
    if (provenance.get("schema") != "house-b-front-drop-claude-provenance-v1"
            or provenance["response_sha256"] != sha256_file(public_path(root, cfg["response"]))
            or provenance["prompt_sha256"] != sha256_file(public_path(root, provenance["prompt_file"]))
            or provenance["consensus"] is not False or provenance["exit_code"] != 0
            or any(provenance[k] is not False for k in ["recorded_tools_enabled", "recorded_mcp_enabled", "recorded_hooks_enabled"])):
        raise ContractError("Claude response/provenance must remain exact and not a consensus stamp")
    parent = read_json(root/cfg["parent_report"])
    for name, expected in parent["source_hashes"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("Claude drop parent source drift: "+name)
    controls = read_json(root/parent["config"]["protected_controls"])["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    p4, q3, ground = [read_json(root/parent["config"][key]) for key in ["p4_report", "q3_report", "ground_report"]]
    front = next(r for r in q3["primary"]["rooms"] if r["id"] == "front-entertainment")
    if {i["id"] for i in front["items"]} != {"sofa", "table", "tv", "service-cabinet"} or front["kind"] != "high-activity":
        raise ContractError("Q3 KTV scope changed; do not assume a nonexistent3F wet tea branch")
    options = [candidate(cfg, spec, parent, p4, ground) for spec in cfg["candidates"]]
    sec = p4["drainage"]["assumptions"]
    arcade = [{"fixture": r["fixture"], "branch_plus_header_to_y3900_mm": r["branch_length_mm"]+1920,
        "illustrative_remaining_budget_mm": round(sec["floor2_level_mm"]-200-150-50-(r["branch_length_mm"]+1920)/50, 3)} for r in p4["drainage"]["rows"]]
    report = {"schema": "house-b-front-drop-claude-report-v1", "date": cfg["date"], "config": cfg,
        "provenance": provenance, "parent_report_hash": parent["report_hash"], "claim_review": cfg["claim_review"],
        "options": options, "original_landing_mm": parent["stair_screen"]["landing_mm"],
        "original_stair_source": parent["stair_screen"]["source"], "original_first_floor_treads": parent["stair_screen"]["treads"],
        "arcade_to_indoor_boundary_cases": arcade, "arcade_minimum_illustrative_budget_mm": min(r["illustrative_remaining_budget_mm"] for r in arcade),
        "arcade_extra25_illustrative_budget_mm": round(min(r["illustrative_remaining_budget_mm"] for r in arcade)-25, 3),
        "y3900_or_y4970_beam_presence_or_bottom_known": False,
        "Q3_front_KTV_items": [i["id"] for i in front["items"]], "Q3_front_KTV_wet_fixture_present": False,
        "new_front_3F_wastewater_load_assumed": False,
        "front_underground_path_lower_bound_mm": 5190, "front_underground_illustrative_fall_mm": 103.8,
        "front_legal_connection_depth_cover_foundation_or_excavation_approved": False,
        "rear_route_full_width_protected_band_y_mm": [9100, 11370], "buried_sacred_crossing_exemption_authorized": False,
        "first_round_numeric_agreements_only": True, "second_round_status": "not-run-awaiting-owner-separate-terminal",
        "recommended_next": "先請Claude第二輪核G4D的500落差與整組管頂／梯底算式，再由建築／機電／結構核合法前終端、騎樓及平台界線、梯板與通氣清掃；G5保重大備案。未有全案可採用解法。",
        "consensus": False, "protected_controls_unchanged": len(controls), "actual_site_or_product_data_received": 0,
        "primary_abc_or_3d_changed": False, "adopted": False, "all_original_requirements_met": False,
        "rendered_qa": "not-run", "professional_approval": "unknown"}
    names = [CONFIG, cfg["provenance"], cfg["response"], *cfg["pinned_sources"], *parent["source_hashes"],
        "house_design/b_front_drop_claude.py", "scripts/export_b_front_drop_claude.py", "Docs/b-front-drop-claude-crosscheck-v1.md", "Docs/claude-b-front-drop-followup-v2.md"]
    report["source_hashes"] = {n: digest(root, n, cache) for n in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

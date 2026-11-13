"""Source-bound second-response review and bounded G4D hypotheses, never an adopted layout."""
from __future__ import annotations

import math
from pathlib import Path

from shapely.geometry import LineString

from house_design.b_front_drop_claude import build as build_round1
from house_design.b_upper_replan import rect
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-front-drop-claude-round2.json"
OUT = "structured/coordination/b-front-drop-claude-v2"


def drop_lower_bound(pipe_top_before_drop, rear_soffit, upper_gap, upper_extra, reserve):
    """All heights share one reference; reserve=None remains unknown, never zero-filled."""
    if reserve is None:
        return None
    return pipe_top_before_drop + upper_gap + upper_extra + reserve - rear_soffit


def drop_upper_bound(lower_budget_before_drop, required_clear, lower_extra):
    if required_clear is None or lower_extra is None:
        return None
    return lower_budget_before_drop - required_clear - lower_extra


def build(root):
    root, cache = Path(root), {}
    cfg = read_json(root/CONFIG)
    unknowns = ["actual_required_upper_reserve_mm", "actual_required_local_clear_height_mm", "actual_extra_lower_fitting_mm"]
    if (cfg.get("schema") != "house-b-front-drop-claude-round2-v1" or cfg.get("adopted") is not False
            or any(cfg[k] is not None for k in unknowns)
            or cfg["normal_stair_waist_cases_mm"] != [150, 200, 250, 300]
            or cfg["extra_upper_fitting_cases_mm"] != [0, 25, 50]
            or cfg["illustrative_drop_cases_mm"] != [500, 550, 600]
            or cfg["horizontal_cross_y_cases_mm"] != [4500, 4700]
            or [r["id"] for r in cfg["claim_review"]] != [f"R2-{i:02d}" for i in range(1, 9)]
            or len(cfg["engineering_questions"]) != 8):
        raise ContractError("Keep conditional bounds and unknown actual data; no silent500/600 selection or adoption")
    cases = cfg["body_growth_cases"]
    if (len(cases) != 6 or len({c["id"] for c in cases}) != 6
            or any(not isinstance(c[k], (int, float)) or not math.isfinite(c[k]) or not 0 <= c[k] <= 50
                for c in cases for k in ["front_mm", "rear_mm", "side_mm", "shift_back_mm"])):
        raise ContractError("Keep six bounded, independent front/rear/side/shift hypotheses")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen round2 source changed: "+name)
    parent = read_json(root/cfg["parent_report"])
    if parent["report_hash"] != stable_hash({k:v for k,v in parent.items() if k != "report_hash"}):
        raise ContractError("Round1 report seal changed")
    if build_round1(root)["report_hash"] != parent["report_hash"]:
        raise ContractError("Round1 source drift; do not rewrite its findings or historical status")
    prov = read_json(root/cfg["provenance"])
    if (prov.get("schema") != "house-b-front-drop-claude-round2-provenance-v1"
            or prov["response_sha256"] != sha256_file(public_path(root, cfg["response"]))
            or prov["prompt_sha256"] != sha256_file(public_path(root, prov["prompt_file"]))
            or prov["requested_model"] != "claude-opus-5-5" or prov["full_design_consensus"] is not False
            or prov["exit_code"] != 0
            or any(prov[k] is not False for k in ["recorded_tools_enabled", "recorded_mcp_enabled", "recorded_hooks_enabled"])):
        raise ContractError("Keep exact owner-run response and provenance, without a consensus stamp")
    old = next(o for o in parent["options"] if o["id"] == "G4D")
    rows = old["fixture_rows"]
    highest = max(r["pipe_package_top_at_riser_center_budget_mm"] + 500 for r in rows)
    top = max(r["conservative_400_chase_top_before_fitting_growth_mm"] + 500 for r in rows)
    below = min(r["lowest_budget_including_original_pipe_support_and_access_mm"] + 500 for r in rows)
    stair = parent["original_stair_source"]
    g, fp = stair["geometry"], stair["footprint"]
    slope = stair["height_mm"]/g["risers"]/g["tread_mm"]
    cosine = 1/math.hypot(1, slope)
    x, y, w, h = old["shaft_mm"]
    start_y = fp["y_mm"]+g["departure_offset_mm"]
    gap = parent["config"]["separate_gap_above_package_to_soffit_mm"]

    def soffit(rear, thickness):
        return stair["base_mm"]+stair["height_mm"]-stair["height_mm"]/g["risers"]-slope*(rear-start_y)-thickness/cosine

    bounds = []
    for thick in cfg["normal_stair_waist_cases_mm"]:
        for extra in cfg["extra_upper_fitting_cases_mm"]:
            bottom = soffit(y+h, thick)
            bounds.append({"normal_waist_mm": thick, "upper_fitting_growth_mm": extra,
                "rear_soffit_model_mm": round(bottom, 3),
                "minimum_drop_with_M0_only_mm": round(drop_lower_bound(top, bottom, gap, extra, 0), 3),
                "required_additional_reserve_M_mm": None,
                "minimum_drop_with_actual_M_mm": drop_lower_bound(top, bottom, gap, extra, cfg[unknowns[0]]),
                "maximum_drop_with_actual_lower_requirements_mm": drop_upper_bound(below, cfg[unknowns[1]], cfg[unknowns[2]]),
                "actual_interval_feasible": None, "adopted": False})
    drop_examples = [{"illustrative_drop_mm": d, "lowest_endpoint_centre_budget_mm": round(below-d, 3),
        "if_straight_pipe_to_rear_edge_budget_mm": round(below-d-h/2/50, 3),
        "extra_lower_growth_assumed_for_this_example_mm": 0,
        "actual_whole_envelope_minimum_clear_height_mm": None, "selected_drop": False} for d in cfg["illustrative_drop_cases_mm"]]
    platform = rect(parent["original_landing_mm"])
    return_box = rect([fp["x_mm"]+fp["w_mm"]-g["flight_width_mm"], start_y, g["flight_width_mm"], g["run_mm"]])
    growth = []
    for c in cases:
        front, rear, side, shift = [c[k] for k in ["front_mm", "rear_mm", "side_mm", "shift_back_mm"]]
        body = rect([x-side, y+shift-front, w+2*side, h+front+rear])
        # Explicit conservative extension of the same slope budget; no real fitting shape inferred.
        new_top = top-shift/50+front/50
        rear_y = y+h+shift+rear
        s250 = soffit(rear_y, 250)
        dmin = drop_lower_bound(new_top, s250, gap, 25, 0)
        growth.append({**c, "body_rect_mm": [x-side, y+shift-front, w+2*side, h+front+rear],
            "front_to_platform_rear_mm": round(y+shift-front-(parent["original_landing_mm"][1]+parent["original_landing_mm"][3]), 3),
            "platform_overlap_sqm": round(body.intersection(platform).area/1e6, 6),
            "expanded_box_entirely_in_original_return_footprint": return_box.covers(body),
            "conservative_top_before_drop_model_mm": round(new_top, 3),
            "rear_y_mm": rear_y, "t250_upper25_M0_minimum_drop_mm": round(dmin, 3),
            "t250_upper25_d500_margin_model_mm": round(500-dmin, 3),
            "upper_growth_coupled_to_planar_growth": False, "actual_full_box_structure_known": False,
            "adopted": False})
    routes = []
    basin = next(r for r in rows if r["fixture"] == "basin")
    for cross_y in cfg["horizontal_cross_y_cases_mm"]:
        points = [[315,1980],[315,3900],[315,cross_y],[1480,cross_y],[1480,5190]]
        length = LineString(points).length
        before_drop_top = 3800-(basin["P4_branch_length_mm"]+cross_y-1980)/50
        routes.append({"horizontal_cross_y_mm": cross_y, "points_mm": points,
            "horizontal_header_mm": length, "basin_top_before_d500_drop_mm": round(before_drop_top, 3),
            "basin_top_after_d500_drop_mm": round(before_drop_top-500, 3),
            "endpoint_basin_top_d500_mm": round(3800-(basin["P4_branch_length_mm"]+length)/50-500, 3),
            "door_fitting_and_cleanout_envelopes_verified": False, "selected": False})
    upstream_gap = basin["P4_branch_length_mm"]/50
    report = {"schema": "house-b-front-drop-claude-round2-report-v1", "date": cfg["date"], "config": cfg,
        "provenance": prov, "parent_report_hash": parent["report_hash"], "claim_review": cfg["claim_review"],
        "highest_endpoint_centre_top_before_drop_mm": highest, "conservative_front_top_before_drop_mm": top,
        "lowest_endpoint_centre_budget_before_drop_mm": below, "local_upper_installation_gap_assumption_mm": gap,
        "drop_bounds": bounds, "drop_examples": drop_examples, "body_growth_cases": growth, "cross_position_examples": routes,
        "shift_margin_loss_per_mm": round(slope-1/50, 9),
        "shift5_margin_loss_mm": round(5*(slope-1/50), 6),
        "upstream_basin_original_shaft_centre": {"hypothetical_slab_bottom_mm": 3800,
            "pipe_package_top_mm": round(3800-upstream_gap, 3), "remaining_upper_gap_mm": upstream_gap,
            "if_uniform50_required_margin_mm": round(upstream_gap-gap, 3),
            "local50_is_proof_of_uniform50": False, "actual_entire_upstream_fit_known": False},
        "downward_after_stair_underpass_only": True, "upward_at_G4_through_stair_permitted": False,
        "vent_return_route_designed": False, "four_separate_pipes_can_overlap": False,
        "actual_merged_pipe_fittings_and_hydraulics_known": False,
        "research_priority": ["合法終端與上游界面先核", "G4D家族完整局部包絡", "前段濕區重排", "G5全梯鏡像重大重排"],
        "original_rules_unchanged": True, "palanquin_front_is_shrine_street_door": True,
        "whole_palanquin_transport_rehearsed": False, "protected_controls_unchanged": parent["protected_controls_unchanged"],
        "actual_site_or_product_data_received": 0, "numeric_and_research_priority_agreement": True,
        "full_design_consensus": False, "adopted": False, "selected_drop_mm": None,
        "selected_cross_y_mm": None, "primary_abc_or_3d_changed": False, "professional_approval": "unknown",
        "front_legal_connection_approved": False, "buried_sacred_crossing_exemption_authorized": False,
        "RF24_Q3_acoustics_R1_waterproofing_resolved": False, "rendered_qa": "not-run"}
    names = [CONFIG, cfg["provenance"], cfg["response"], *cfg["pinned_sources"], *parent["source_hashes"],
        "scripts/review_b_fengshui_with_claude_v2.py", "house_design/b_front_drop_claude_round2.py",
        "scripts/export_b_front_drop_claude_round2.py", "Docs/b-front-drop-claude-crosscheck-v2.md"]
    report["source_hashes"] = {n: digest(root, n, cache) for n in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

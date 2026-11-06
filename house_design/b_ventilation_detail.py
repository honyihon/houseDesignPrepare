"""Small B ventilation fit/airflow budgets with explicit unknown structure and products."""
from __future__ import annotations

import copy
import math
from pathlib import Path

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from house_design.b_bath_ventilation import duct_path, floor_screen
from house_design.b_fengshui_strict import area_shape
from house_design.c_coordination import public_path
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash

CONFIG = "inputs/b-ventilation-detail.json"
OUT = "structured/coordination/b-ventilation-detail-v1"


def overlap(a, b):
    return area_shape(a).intersection(area_shape(b)).area/1e6


def independent_duct_collisions(ducts):
    hits = []
    for i, a in enumerate(ducts):
        for b in ducts[i+1:]:
            ra, rb = a["outer_plan_budget_width_mm"]/2, b["outer_plan_budget_width_mm"]/2
            for n, (a0, a1) in enumerate(zip(a["points_mm"], a["points_mm"][1:], strict=False)):
                for m, (b0, b1) in enumerate(zip(b["points_mm"], b["points_mm"][1:], strict=False)):
                    overlaps = [min(max(a0[k], a1[k])+ra, max(b0[k], b1[k])+rb)
                        -max(min(a0[k], a1[k])-ra, min(b0[k], b1[k])-rb) for k in range(3)]
                    if all(v > 0 for v in overlaps):
                        hits.append({"floor_a": a["floor"], "segment_a": n, "floor_b": b["floor"], "segment_b": m,
                            "rectangular_budget_overlap_mm3": math.prod(overlaps)})
    return hits


def makeup_air(cfg):
    m = cfg["makeup_air"]
    q = m["design_comparison_q_m3_h"]/3600
    width = m["door_illustrative_clear_mm"]
    cases = []
    for height in m["door_undercut_cases_mm"]:
        area = width*height/1e6
        cases.append({"gap_mm": height, "ideal_area_sqm": area, "velocity_m_s": q/area,
            "actual_flow_or_noise_test": None})
    gross = m["candidate_opening_width_mm"]*m["candidate_opening_height_mm"]/1e6
    grille = [{"assumed_free_fraction": f, "assumed_free_area_sqm": gross*f, "velocity_m_s": q/(gross*f)}
        for f in m["free_area_ratio_assumptions"]]
    return {"comparison_q_m3_h": m["design_comparison_q_m3_h"], "door_undercuts": cases,
        "nominal_transfer_opening_sqm": gross, "transfer_free_area_cases": grille,
        "front_wall_candidate_x_mm": m["front_wall_candidate_x_mm"],
        "door_panel_candidate_x_mm": m["door_panel_candidate_x_mm"],
        "opening_bottom_relative_z_mm": m["opening_bottom_relative_z_mm"],
        "actual_free_area_sqm": None, "actual_pressure_loss_pa": None,
        "closed_door_airflow_verified": False, "outdoor_fresh_air_verified": False,
        "recommended_bidding_basis": "先比較原廠門片消音補氣與門旁牆消音補氣兩種完整構造；不加大門下縫作唯一解。",
        "scope": "速度只按理想面積算，不是噪音、壓差、有效風量、隱私或防火核可。",
        "source": "一般公共乾區；其合法室外進氣、關窗及同時排風的壓力平衡尚未設計。",
        "excluded_sources": ["樓梯", "獨立乾保護室", "其他浴廁", "神明堂排煙管", "污水通氣管"],
        "product_conditions": ["實際自由面積與指定風量壓損", "阻視與聲學實測，不能只靠百葉名稱",
            "門片厚度／重量／把手及900淨開口", "完整牆種、RC／防火限制與可清潔檢修"]}


def count_bends(points):
    directions = []
    for a, b in zip(points, points[1:], strict=False):
        delta = [b[i]-a[i] for i in range(3)]
        axes = [i for i, value in enumerate(delta) if value]
        if len(axes) != 1:
            raise ContractError("Ventilation detail only budgets nonzero axis-aligned duct segments")
        axis = axes[0]
        directions.append((axis, 1 if delta[axis] > 0 else -1))
    return sum(a != b for a, b in zip(directions, directions[1:], strict=False))


def pressure_cases(path, cfg):
    p = cfg["pressure_sensitivity"]
    diameter_m = p["diameter_mm"]/1000
    length_m = path["centerline_length_mm"]/1000
    bends = count_bends(path["points_mm"])
    coeffs = p["fitting_K_assumptions"]
    rows = []
    for q in p["q_cases_m3_h"]:
        velocity = (q/3600)/(math.pi*diameter_m**2/4)
        dynamic = .5*p["air_density_assumption_kg_m3"]*velocity**2
        bounds = []
        for i in [0, 1]:
            friction = p["darcy_friction_assumptions"][i]
            k = bends*coeffs["each_90_bend"][i]+sum(coeffs[key][i] for key in ["intake", "backdraft", "roof_hood"])
            straight_loss = friction*length_m/diameter_m*dynamic
            fittings_loss = k*dynamic
            bounds.append({"darcy_f_assumption": friction, "total_K_assumption": k,
                "straight_pa": straight_loss, "fittings_pa": fittings_loss, "sum_pa": straight_loss+fittings_loss})
        rows.append({"q_m3_h": q, "velocity_m_s": velocity, "assumed_low": bounds[0], "assumed_high": bounds[1]})
    return {"floor": path["floor"], "axis_bends": bends, "diameter_assumption_mm": p["diameter_mm"],
        "centerline_length_mm": path["centerline_length_mm"], "cases": rows,
        "method": "Darcy-Weisbach fL/D*rho*v^2/2 plus selected sumK*rho*v^2/2",
        "actual_required_static_pressure_pa": None, "actual_fan_model": None,
        "exclusions": ["補氣端壓損", "另加消音器／濾網與積塵", "真實管材、彎頭及風帽曲線", "風壓與同時排風壓力平衡"],
        "scope": "只供同一假設下的發包敏感度；不是實測壓損上下界或可選機的核定工作點，長軟管不沿用此模型。"}


def assembly_cases(parent, cfg):
    o = parent["options"][0]
    a = cfg["assembly"]
    size = a["pipe_outer_mm"]
    gap = a["inter_pipe_gap_assumption_mm"]
    rows = []
    floors = o["floors"]
    protected = unary_union([Polygon(p) for p in parent["protected_polygons_mm"]])
    store = area_shape(parent["palanquin_rect_mm"])
    for enclosure in a["enclosure_cases_mm"]:
        screen = floor_screen(floors[0]["rooms"], [enclosure], floors[0]["screen"]["route"]["points_mm"],
            {"public-bath", "private-bath"}, protected, store)
        fits = []
        for wall in a["wall_each_cases_mm"]:
            inner_w, inner_d = enclosure[2]-2*wall, enclosure[3]-2*wall
            fits.append({"wall_each_assumption_mm": wall, "inner_width_mm": inner_w, "inner_depth_mm": inner_d,
                "two_pipe_plus_gap_width_mm": 2*size+gap, "pipe_outer_depth_mm": size,
                "width_margin_mm": inner_w-2*size-gap, "depth_margin_mm": inner_d-size,
                "reanchored_pipe_pack_fits": inner_w >= 2*size+gap and inner_d >= size,
                "actual_fire_acoustic_and_access_pack": None})
        rows.append({"enclosure_mm": enclosure, "reserved_sqm": screen["reserved_enclosure_sqm"],
            "master_after_sqm": screen["master_after_enclosure_sqm"],
            "meets_original_master_20": screen["master_after_enclosure_sqm"] >= 20,
            "floor_screen": screen, "wall_pack_cases": fits, "selected": False})
    outer = size
    center = a["duct_center_relative_z_mm"]
    ceiling = a["ceiling_relative_z_mm"]
    duct_lo, duct_hi = center-outer/2, center+outer/2
    return {"enclosure_cases": rows, "selected_enclosure": None,
        "pipe_pair_gap_mm_is_assumption": gap,
        "duct_bottom_relative_z_mm": duct_lo, "duct_top_relative_z_mm": duct_hi,
        "gap_above_2400_ceiling_mm": duct_lo-ceiling,
        "slab_cases": [{"assumed_slab_thickness_mm": t, "assumed_underside_mm": 3000-t,
            "gap_above_duct_mm": 3000-t-duct_hi} for t in a["slab_thickness_cases_mm"]],
        "beam_cases": [{"assumed_total_depth_from_next_floor_mm": depth, "assumed_underside_mm": 3000-depth,
            "gap_above_duct_mm": 3000-depth-duct_hi,
            "rectangular_budget_conflict_if_beam_crosses": 3000-depth < duct_hi}
            for depth in a["beam_depth_cases_mm"]],
        "actual_beam_positions_and_depths": None, "actual_slab_penetrations": None,
        "scope": "矩形包覆與標高敏感度，假設管心2550／每層3000；未核真實牆厚、彎頭掃掠、風機及結構。"}


def route_and_service(parent, cfg):
    o = parent["options"][0]
    r = cfg["revised_exhaust"]
    p_cfg = parent["config"]
    protection = unary_union([Polygon(p) for p in parent["protected_polygons_mm"]])
    storage = area_shape(parent["palanquin_rect_mm"])
    roof = box(2400, 11370, 6000, 17630)
    ducts = []
    old_grille = p_cfg["mechanical"]["grille_xy_mm"]
    new_grille = r["grille_center_mm"]
    makeup_center = [1000, 11370]
    diameter = p_cfg["mechanical"]["duct_nominal_diameter_mm"]
    insulation = p_cfg["mechanical"]["insulation_each_mm"]
    for old, roof_center in zip(o["ducts"], r["roof_centers_mm"], strict=True):
        floor = old["floor"]
        base = p_cfg["floor_base_mm"][floor]
        px, py = old["points_mm"][-1][:2]
        branch_z = base+p_cfg["mechanical"]["branch_center_relative_z_mm"]
        gx, gy = new_grille
        points = [[gx, gy, base+cfg["assembly"]["ceiling_relative_z_mm"]], [gx, gy, branch_z], [gx, r["branch_rear_y_mm"], branch_z],
            [px, r["branch_rear_y_mm"], branch_z], [px, py, branch_z], [px, py, r["roof_offset_z_mm"]],
            [px, roof_center[1], r["roof_offset_z_mm"]], [*roof_center, r["roof_offset_z_mm"]],
            [*roof_center, r["roof_terminal_z_mm"]]]
        path = duct_path(points, diameter, insulation, protection, storage, area_shape([2325, 12455, 200, 700]),
            area_shape([2325, 13155, 200, 200]), o["enclosure_mm"], roof)
        path["floor"] = floor
        path["old_centerline_length_mm"] = old["centerline_length_mm"]
        ducts.append(path)
    bath = o["floors"][0]["rooms"][2]
    finished = area_shape(bath["illustrative_finished_rect_mm"])
    body_rects = [(i["id"], i["rect_mm"]) for i in bath["furniture"]]
    hatch, ladder = r["fan_hatch_rect_mm"], r["ladder_budget_rect_mm"]
    fan = r["fan_reserved_box_mm"]
    fan_plan = [fan[0], fan[1], fan[3], fan[4]]
    master = o["floors"][0]["rooms"][0]
    master_inner = Polygon(master["polygon_mm"]).buffer(-115, join_style=2)
    access = r["shaft_service_rect_mm"]
    roof_rows = []
    for index, (reserved, service) in enumerate(zip(r["roof_terminal_reservations_mm"], r["roof_service_reservations_mm"], strict=True)):
        roof_rows.append({"floor": ducts[index]["floor"], "terminal_reservation_mm": reserved,
            "service_reservation_mm": service, "nominal_box_inside_roof": roof.covers(area_shape(reserved)),
            "service_inside_roof": roof.covers(area_shape(service)),
            "terminal_over_protected_sqm": area_shape(reserved).intersection(protection).area/1e6,
            "service_over_protected_sqm": area_shape(service).intersection(protection).area/1e6,
            "terminal_over_storage_sqm": area_shape(reserved).intersection(storage).area/1e6,
            "known_outdoor_unit_hits": [u["id"] for u in parent["roof_outdoor_unit_bodies"]
                if overlap(reserved, u["rect_mm"]) > 0 or overlap(service, u["rect_mm"]) > 0],
            "actual_hood_product_and_approach": None})
    radius = diameter/2+insulation
    bed = next(i["rect_mm"] for i in master["furniture"] if i["id"] == "bed")
    bed_project = []
    # Interior branches, excluding roof offsets; roof device projection is a separate check.
    for d in ducts:
        points = [p[:2] for p in d["points_mm"][:5]]
        bed_project.append(LineString(points).buffer(radius, cap_style=3, join_style=2).intersection(area_shape(bed)).area/1e6)
    return {"floors": copy.deepcopy(o["floors"]), "ducts": ducts, "roof_terminal_rows": roof_rows,
        "roof_centers_separation_mm": math.dist(*r["roof_centers_mm"]),
        "old_roof_riser_centers_separation_mm": math.dist(*p_cfg["mechanical"]["clear_pipe_centers_mm"]),
        "roof_reservation_overlap_sqm": overlap(*r["roof_terminal_reservations_mm"]),
        "roof_service_overlap_sqm": overlap(*r["roof_service_reservations_mm"]),
        "independent_duct_rectangular_budget_hits": independent_duct_collisions(ducts),
        "old_makeup_to_extract_plan_mm": math.dist(makeup_center, old_grille),
        "new_makeup_to_extract_plan_mm": math.dist(makeup_center, new_grille),
        "short_circuit_prevention_verified": None,
        "interior_branch_over_bed_sqm": bed_project,
        "service": {"fan_reserved_box_mm": fan, "fan_hatch_rect_mm": hatch, "ladder_budget_rect_mm": ladder,
            "fan_plan_inside_bath": finished.covers(area_shape(fan_plan)),
            "hatch_inside_bath": finished.covers(area_shape(hatch)), "ladder_inside_bath": finished.covers(area_shape(ladder)),
            "fan_or_hatch_body_hits": [name for name, body in body_rects if overlap(fan_plan, body) > 0 or overlap(hatch, body) > 0],
            "ladder_body_hits": [name for name, body in body_rects if overlap(ladder, body) > 0],
            "shaft_service_rect_mm": access, "shaft_service_inside_master_115": master_inner.covers(area_shape(access)),
            "shaft_service_fixed_body_hits": [i["id"] for i in master["furniture"] if overlap(access, i["rect_mm"]) > 0],
            "shaft_service_route_overlap_sqm": unary_union([area_shape(s) for s in o["floors"][0]["screen"]["route"]["sweeps_mm"]]).intersection(area_shape(access)).area/1e6,
            "use": "浴室停用後檢修；主臥豎道檢修暫占房內路徑，不當成使用中仍可通行。",
            "actual_product_removal_and_safe_ladder": None,
            "fan_box_z_vs_horizontal_duct": "空間預留含管接，不是兩件固定實品相撞；真正風機／接管／檢修尺寸待廠商。"},
        "retained_master_after_sqm": o["master_after_reservations_sqm"],
        "retained_public_sqm": o["public_after_sewer_sqm"], "retained_private_sqm": o["private_after_sewer_sqm"],
        "actual_roof_weather_and_fire_design": None}


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    for name, digest in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("B vent detail source changed: "+name)
    parent = read_json(root/cfg["parent_report"])
    for name, digest in parent["source_hashes"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("B vent detail parent dependency changed: "+name)
    parent_m = parent["config"]["mechanical"]
    if (cfg["pressure_sensitivity"]["diameter_mm"] != parent_m["duct_nominal_diameter_mm"]
            or cfg["assembly"]["pipe_outer_mm"] != parent_m["duct_nominal_diameter_mm"]+2*parent_m["insulation_each_mm"]
            or cfg["assembly"]["duct_center_relative_z_mm"] != parent_m["branch_center_relative_z_mm"]
            or cfg["assembly"]["ceiling_relative_z_mm"] != parent_m["design_ceiling_mm"]):
        raise ContractError("B vent detail diameter/insulation/ceiling budgets disagree with the frozen parent")
    controls = read_json(root/cfg["protected_controls"])
    for name, digest in controls["hashes"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("B vent detail protected control changed: "+name)
    geometry = route_and_service(parent, cfg)
    report = {"schema": "house-b-ventilation-detail-report-v1", "date": cfg["date"], "config": cfg,
        "source_layout_report_sha256": parent["source_layout_report_sha256"],
        "makeup": makeup_air(cfg), "geometry": geometry, "assembly": assembly_cases(parent, cfg),
        "pressure_sensitivity": [pressure_cases(d, cfg) for d in geometry["ducts"]],
        "original_targets_sqm": copy.deepcopy(parent["original_targets_sqm"]),
        "owner_ritual_answers": copy.deepcopy(parent["owner_ritual_answers"]),
        "retained_entries": copy.deepcopy(parent["retained_entries"]),
        "original_1f_and_3d_unchanged": True, "protected_controls_unchanged": len(controls["hashes"]),
        "owner_no_window_decision": copy.deepcopy(parent["decision"]), "owner_requirement_changes": False,
        "adopted": False, "all_requirements_met": False, "browser_qa": "not-run", "claude_status": cfg["claude_status"],
        "professional_approval": "unknown", "recommendation": "以二三樓一般公衛發包資料準備為範圍，先核補氣、牆柱及風機性能；原無窗偏好待答，不併主案。"}
    names = [CONFIG, *cfg["pinned_sources"], *parent["source_hashes"], cfg["protected_controls"],
        "house_design/b_ventilation_detail.py", "scripts/export_b_ventilation_detail.py", "Docs/b-ventilation-detail-v1.md"]
    report["source_hashes"] = {name: sha256_file(root/name) for name in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

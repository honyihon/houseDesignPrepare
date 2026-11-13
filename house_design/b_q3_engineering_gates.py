"""Bounded Q3/RF vertical budgets, replacement apertures and conditional inputs."""
from __future__ import annotations

import copy
import math
from itertools import product
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

from house_design.b_upper_replan import rect, ring
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-q3-engineering-gates.json"
OUT = "structured/coordination/b-q3-engineering-gates-v1"
NUMERIC_FIELDS = ("width_mm", "depth_mm", "height_mm", "mass_kg", "handling_each_side_mm")


def finite(value, *, zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and (value >= 0 if zero else value > 0)
    except OverflowError:
        return False


def template_and_results(cfg, parent, document):
    records = []
    for option in parent["options"]:
        for item, route_id in cfg["transport_targets"].items():
            route = next(r for r in option["routes"] if r["id"] == route_id)
            aperture = route["door"]
            records.append({"id": option["id"]+":"+item, "option": option["id"], "equipment": item,
                "inspection_door_reference_not_a_transport_route": aperture,
                "door_budget_mm": parent[aperture+"_door_clear_budget_mm"],
                **dict.fromkeys(NUMERIC_FIELDS), "reference": ""})
    template = {"schema": "house-b-q3-engineering-conditions-v1", "config_hash": stable_hash(cfg),
        "parent_report_hash": parent["report_hash"], "records": records}
    received = copy.deepcopy(template if document is None else document)
    if (not isinstance(received, dict) or set(received) != set(template)
            or any(received[k] != template[k] for k in ("schema", "config_hash", "parent_report_hash"))
            or not isinstance(received["records"], list)):
        raise ContractError("Q3 engineering conditions require this exact source revision")
    indexed, values = {r["id"]: r for r in records}, {}
    for row in received["records"]:
        if not isinstance(row, dict) or row.get("id") not in indexed or row["id"] in values:
            raise ContractError("Unknown or duplicate Q3 transport record")
        base = indexed[row["id"]]
        if set(row) != set(base) or any(row[k] != base[k] for k in set(base)-set(NUMERIC_FIELDS)-{"reference"}):
            raise ContractError("Do not edit Q3 equipment, door or aperture identity")
        if not isinstance(row["reference"], str) or any(row[k] is not None and not finite(row[k], zero=k == "handling_each_side_mm") for k in NUMERIC_FIELDS):
            raise ContractError("Q3 transport values must be finite dimensions/mass; only handling reserve may be zero")
        if any(row[k] is not None for k in NUMERIC_FIELDS) and not row["reference"].strip():
            raise ContractError("Received Q3 transport values need a product/transport reference")
        values[row["id"]] = row
    if set(values) != set(indexed):
        raise ContractError("Keep all Q3 condition records; unknown values stay null")
    results = []
    for base in records:
        row = values[base["id"]]
        needed = None if row["width_mm"] is None or row["handling_each_side_mm"] is None else row["width_mm"]+2*row["handling_each_side_mm"]
        if needed is not None and not finite(needed):
            raise ContractError("Q3 combined aperture budget exceeds finite numeric range")
        margin = None if needed is None else base["door_budget_mm"]-needed
        results.append({**row, "required_aperture_mm": needed, "width_margin_mm": margin,
            "status": "pending" if margin is None else "width-only-compatible" if margin >= 0 else "reject-declared-width",
            "minimum_transport_orientation_verified": False, "actual_finished_aperture_verified": False,
            "full_route_turning_depth_height_stairs_load_religion_or_lifting_approved": False})
    return template, results, sum(v[k] is not None for v in values.values() for k in NUMERIC_FIELDS)


def vertical_budgets(cfg, q3):
    source = q3["original_stairs_by_floor"]["floor-3"]
    base, height = source["base_mm"], source["height_mm"]
    if base != 7000 or height != 3000:
        raise ContractError("Q3 height cases must attach to the frozen model datums")
    fields = ("roof_build_below_RF_plane_mm", "slab_mm", "beam_extra_below_slab_mm", "ceiling_and_services_below_lowest_structure_mm", "KTV_floor_raise_above_3F_plane_mm")
    result = []
    ids = set()
    for row in cfg["vertical_cases"]:
        if row["id"] in ids or any(not finite(row[k], zero=k != "slab_mm") for k in fields):
            raise ContractError("Use unique vertical cases and explicit nonnegative layer budgets")
        ids.add(row["id"])
        rf = base+height
        slab_top = rf-row[fields[0]]
        slab_bottom = slab_top-row[fields[1]]
        lowest = slab_bottom-row[fields[2]]
        ceiling = lowest-row[fields[3]]
        floor = base+row[fields[4]]
        result.append({**row, "model_3F_plane_z_mm": base, "model_RF_plane_z_mm": rf,
            "slab_top_z_mm": slab_top, "slab_bottom_z_mm": slab_bottom, "lowest_structure_z_mm": lowest,
            "KTV_ceiling_z_mm": ceiling, "KTV_floor_z_mm": floor, "remaining_vertical_budget_mm": ceiling-floor,
            "datum_convention": "RF reference plane held; roof layers below it, 3F extra floor above its plane",
            "legal_minimum_or_actual_material_selected": False, "whole_stair_or_room_height_approved": False})
    return result


def projection_interfaces(parent, q3):
    f = parent["floor_requirements"]
    floor = unary_union([rect(f[k]) for k in ("landing_mm", "vestibule_mm", "side_threshold_mm")]+[Polygon(f["front_threshold_polygon_mm"])])
    ktv = next(r for r in q3["primary"]["rooms"] if r["id"] == "front-entertainment")
    nominal, inner = Polygon(ktv["polygon_mm"]), Polygon(q3["primary"]["KTV_inner_polygon_mm"])
    overlap = floor.intersection(nominal)
    equipment = []
    for option in parent["options"]:
        for item in option["equipment_reservations"]:
            if item["id"] not in {"tank", "heat-pump", "B-AC03", "B-AC04", "representative-slot-1", "representative-slot-2"}:
                continue
            shape = rect(item.get("body_mm", item["rect_mm"]))
            equipment.append({"option": option["id"], "id": item["id"], "rect_mm": item.get("body_mm", item["rect_mm"]),
                "outline_scope": "source representative body not chosen product" if item.get("body_mm") else "whole reservation not product body",
                "over_KTV_nominal_sqm": round(shape.intersection(nominal).area/1e6, 6),
                "below_rooms": [{"id": r["id"], "sqm": round(shape.intersection(Polygon(r["polygon_mm"])).area/1e6, 6)} for r in q3["primary"]["rooms"] if shape.intersection(Polygon(r["polygon_mm"])).area > .01],
                "load_noise_waterproofing_piping_or_religious_approval": "unknown"})
    return {"RF_required_floor_polygon_mm": ring(floor), "KTV_nominal_polygon_mm": ktv["polygon_mm"],
        "RF_floor_over_KTV_nominal_sqm": round(overlap.area/1e6, 6),
        "RF_floor_over_KTV_inner_sqm": round(floor.intersection(inner).area/1e6, 6),
        "RF_floor_over_KTV_polygon_mm": ring(overlap), "equipment": equipment,
        "structural_transmission_and_machine_base_load_verified": False}


def capacity_boundary(parent, q3):
    width, edge, front_y = parent["config"]["frame_mm"][0], parent["config"]["edge_budget_mm"], 3900
    target = parent["parent_daily_capacity"]["RF_deck_original_target_sqm"]
    finished_w = width-2*edge
    upper = finished_w*(front_y-edge)/1e6
    if abs(upper-parent["parent_daily_capacity"]["front_before_equipment_with_edge_budget_sqm"]) > .000001:
        raise ContractError("RF optimistic capacity convention changed")
    depth = target*1e6/finished_w+edge
    extra = math.ceil(depth)-front_y
    band = rect([edge, front_y, finished_w, extra])
    protected = unary_union([Polygon(p) for p in q3["protected_polygons_mm"]])
    stair = rect(parent["config"]["roof_enclosure_mm"])
    return {"original_target_sqm": target, "fixed_front_upper_bound_before_equipment_sqm": round(upper, 6),
        "optimistic_shortfall_sqm": round(target-upper, 6), "finished_width_budget_mm": finished_w,
        "hypothetical_full_width_depth_lower_bound_mm": round(depth, 3), "hypothetical_rounded_extra_depth_mm": extra,
        "hypothetical_extra_band_mm": [edge, front_y, finished_w, extra],
        "extra_band_over_protected_sqm": round(band.intersection(protected).area/1e6, 6),
        "extra_band_over_stair_enclosure_sqm": round(band.intersection(stair).area/1e6, 6),
        "extra_band_not_already_blocked_sqm": round(band.difference(unary_union([protected, stair])).area/1e6, 6),
        "full_width_band_is_an_authorized_or_buildable_design": False,
        "all_global_replans_proven_impossible": False, "RF24_target_reduced_or_met": False,
        "indoor_vestibule_rear_daily_area_or_3F_court_credited": False}


def build(root, condition_document=None):
    root, cache = Path(root), {}
    cfg = read_json(root/CONFIG)
    if (cfg.get("schema") != "house-b-q3-engineering-gates-v1" or cfg.get("adopted") is not False
            or cfg["transport_targets"] != {"tank": "inspect-tank-boundary", "heat-pump": "inspect-heat-pump-boundary", "B-AC03": "inspect-rear-cooling-03", "B-AC04": "inspect-rear-cooling-04"}
            or cfg["width_trial_cases_mm"] != [700, 770, 800, 900, 1000] or cfg["handling_each_side_cases_mm"] != [0, 25, 50]):
        raise ContractError("Keep independent Q3 interface scope and fixed reference identities")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen Q3 engineering parent changed: "+name)
    parent = read_json(root/cfg["parent_report"])
    for name, expected in parent["source_hashes"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("Q3 engineering parent source drift: "+name)
    controls = read_json(root/cfg["protected_controls"])["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    q3 = read_json(root/parent["config"]["q3_report"])
    template, received, count = template_and_results(cfg, parent, condition_document)
    trials = [{"door": name, "aperture_budget_mm": parent[name+"_door_clear_budget_mm"], "declared_transport_width_mm": width,
        "handling_each_side_mm": gap, "required_width_mm": width+2*gap,
        "margin_mm": parent[name+"_door_clear_budget_mm"]-width-2*gap,
        "status": "width-only-compatible" if width+2*gap <= parent[name+"_door_clear_budget_mm"] else "reject-declared-width",
        "actual_product_or_full_route_approved": False}
        for name, width, gap in product(["front", "side"], cfg["width_trial_cases_mm"], cfg["handling_each_side_cases_mm"])]
    report = {"schema": "house-b-q3-engineering-gates-report-v1", "date": cfg["date"], "config": cfg,
        "parent_report_hash": parent["report_hash"], "parent_equipment_and_furniture_hash": stable_hash([{k: o[k] for k in ("id", "equipment_reservations", "furniture")} for o in parent["options"]]),
        "vertical_cases": vertical_budgets(cfg, q3), "projection_interfaces": projection_interfaces(parent, q3),
        "capacity_boundary": capacity_boundary(parent, q3), "door_width_trials": trials,
        "front_door_clear_budget_mm": parent["front_door_clear_budget_mm"], "side_door_clear_budget_mm": parent["side_door_clear_budget_mm"],
        "condition_template": template, "condition_evaluations": received, "numeric_condition_values_received": count,
        "condition_document_hash": None if condition_document is None else stable_hash(condition_document),
        "engineering_gates": cfg["engineering_gates"], "all_engineering_gate_statuses": "pending",
        "recommended_sequence": ["先保S1／D1供建商核維修與振動，S2／D2保前平台備案，兩案都不是施工定案。", "建築／結構先核Q3上下平台、RF前室及標高，再讓設備／聲學拿同版剖面核對。", "首裝與全壽命汰換分開回覆；單一門寬相容也要完整轉彎、梯段及重量演練。", "24㎡仍缺，若不能取捨需整棟完整重排；縮平台或改家規需屋主另行決定，現在不改。"],
        "protected_controls_unchanged": len(controls), "actual_site_values_received": 0,
        "primary_abc_or_3d_changed": False, "new_room_door_or_equipment_geometry_generated": False,
        "all_original_requirements_met": False, "adopted": False, "rendered_qa": "not-run", "professional_approval": "unknown"}
    names = [CONFIG, *cfg["pinned_sources"], *parent["source_hashes"], cfg["protected_controls"],
        "house_design/b_q3_engineering_gates.py", "scripts/export_b_q3_engineering_gates.py", "Docs/b-q3-engineering-gates-v1.md"]
    report["source_hashes"] = {n: digest(root, n, cache) for n in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

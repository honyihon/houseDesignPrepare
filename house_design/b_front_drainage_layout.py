"""Independent P4 2F fixture re-layout with fixed shaft and complete-path comparison."""
from __future__ import annotations

import copy
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

from house_design.b_front_service_detail import (
    assert_geometry,
    drainage_review,
    front_review,
    panel_travel,
    shaft_accounting,
)
from house_design.b_upper_replan import analyze_floor, finish, rect, sweep
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-front-drainage-layout.json"
OUT = "structured/coordination/b-front-drainage-layout-v1"


def local_layout(cfg, parent, upper):
    local = copy.deepcopy(parent["config"])
    for key in ["public_fixtures", "tea_furniture", "routes"]:
        local[key] = copy.deepcopy(cfg[key])
    bath = cfg["bath_slider"]
    old_bath = next(d for d in local["sliders"] if d["id"] == "bath")
    expected = copy.deepcopy(old_bath)
    for key in ["a", "b"]:
        expected[key][0] -= 550
    for key in ["closed_x_mm", "park_x_mm"]:
        expected[key] = [v-550 for v in expected[key]]
    if {k: v for k, v in bath.items() if k != "label"} != {k: v for k, v in expected.items() if k != "label"}:
        raise ContractError("P4 only shifts the original bath slider550mm left; keep full product budgets")
    local["sliders"] = [copy.deepcopy(bath) if d["id"] == "bath" else d for d in local["sliders"]]
    def sizes(rows):
        return {i["id"]: {part: sorted(i[part][2:]) for part in ["rect_mm", "operation_mm"]} for i in rows}
    for key in ["public_fixtures", "tea_furniture"]:
        if sizes(local[key]) != sizes(parent["config"][key]):
            raise ContractError("Do not shrink or remove P3 fixture bodies")
    previous = parent["floors"][0]
    if previous["id"] != "floor-2":
        raise ContractError("P4 can only change the second-floor front service area")
    rooms = copy.deepcopy(previous["rooms"])
    for r in rooms:
        if r["id"] == "public-bath":
            r["items"] = copy.deepcopy(local["public_fixtures"])
        elif r["id"] == "tea-foyer":
            r["items"] = copy.deepcopy(local["tea_furniture"])
    routes = [{k: r[k] for k in ["id", "width_mm", "points_mm", "purpose"]} for r in previous["routes"]]
    protected = unary_union([Polygon(p) for p in upper["protected_polygons_mm"]])
    floor = analyze_floor(rooms, upper["config"], protected, rect(upper["palanquin_rect_mm"]), {}, "floor-2", routes)
    floor["front"] = front_review(floor, local, upper["config"])
    floor["area_ledger"] = shaft_accounting(floor, local)
    floor["unchanged_other_rooms_hash"] = stable_hash([r for r in rooms if r["id"] not in {"public-bath", "tea-foyer"}])
    if floor["unchanged_other_rooms_hash"] != stable_hash([r for r in previous["rooms"] if r["id"] not in {"public-bath", "tea-foyer"}]):
        raise ContractError("P4 changed rooms outside its 2F front-only scope")
    if any([{k: v for k, v in new.items() if k != "items"} != {k: v for k, v in old.items() if k != "items"}
            for new, old in zip(rooms, previous["rooms"], strict=True)]):
        raise ContractError("P4 must preserve every original room outline, shaft and window")
    assert_geometry([floor], local)
    for state in floor["front"]["door_combinations"]:
        for route in local["routes"]:
            blockers = next(r["doors"] for r in state["route_blockers"] if r["route"] == route["id"])
            expected = ([name for name in ["bath", "stair"] if state["states"][name] != "open"] if route["id"] == "public-arrival"
                else ["stair"] if route["id"] == "dry-maintenance" and state["states"]["stair"] != "open" else [])
            if blockers != expected:
                raise ContractError("P4 independent door states or fixture-operation route changed")
    body = {i["id"]: rect(i["rect_mm"]) for i in local["public_fixtures"]+local["tea_furniture"]}
    arrival = sweep(local["routes"][0]["points_mm"], 900)
    panel_shape = unary_union([rect(r) for d in local["sliders"] if d["id"] == "bath" for r in panel_travel(d)])
    clearances = {"bath_full_travel_to_shaft_mm": panel_shape.distance(rect(local["shared_shaft_mm"])),
        "bath_full_travel_to_counter_mm": panel_shape.distance(body["tea-counter"]),
        "arrival_to_shower_body_mm": arrival.distance(body["shower"]), "arrival_to_counter_body_mm": arrival.distance(body["tea-counter"])}
    return local, floor, clearances


def drainage_comparison(cfg, local, parent, upper, floor):
    new = drainage_review(local, upper, [floor])
    rows = []
    for fid in parent["config"]["branch_fixture_ids"]:
        old = next(r for r in parent["drainage"]["rows"] if r["option"] == "P3" and r["fixture"] == fid)
        current = next(r for r in new["rows"] if r["option"] == "P3" and r["fixture"] == fid)
        rows.append({**copy.deepcopy(current), "option": "P4", "P3_branch_length_mm": old["branch_length_mm"],
            "P3_total_length_mm": old["total_length_mm"], "change_total_length_mm": current["total_length_mm"]-old["total_length_mm"],
            "P3_hypothetical_total_fall_mm": old["hypothetical_total_fall_mm"]})
    sec = new["assumptions"]
    scenarios = []
    for structure in sec["illustrative_structure_depths_mm"]:
        for pipe in sec["pipe_support_envelopes_mm"]:
            for extra in cfg["extra_below_original_pipe_budget_cases_mm"]:
                results = [{"fixture": r["fixture"], "remaining_budget_mm": round(sec["floor2_level_mm"]-structure-pipe-extra-r["hypothetical_total_fall_mm"]-sec["access_allowance_mm"], 3)} for r in rows]
                minimum = min(r["remaining_budget_mm"] for r in results)
                scenarios.append({"structure_mm": structure, "pipe_support_mm": pipe, "extra_below_original_pipe_budget_mm": extra,
                    "fixture_results": results, "minimum_remaining_budget_mm": minimum,
                    "margin_to_illustrative_target_mm": round(minimum-sec["required_illustrative_clear_mm"], 3),
                    "all_four_meet_illustrative_target_only": minimum >= sec["required_illustrative_clear_mm"],
                    "gravity_drainage_or_actual_arcade_clearance_approved": False})
    return {**{k: v for k, v in new.items() if k not in {"rows", "full_path_section_sensitivity", "offset_only_cases", "offset_only_can_give_false_positive"}},
        "rows": rows, "section_scenarios": scenarios,
        "P3_best_case_minimum_remaining_mm": min(r["complete_path_remaining_mm"] for r in parent["drainage"]["full_path_section_sensitivity"]
            if r["option"] == "P3" and r["structure_mm"] == min(sec["illustrative_structure_depths_mm"]) and r["pipe_support_mm"] == min(sec["pipe_support_envelopes_mm"])),
        "P4_best_case_minimum_remaining_mm": max(r["minimum_remaining_budget_mm"] for r in scenarios),
        "best_case_only_does_not_resolve_actual_arcade_or_ground_drop": True,
        "minimum_actual_pipe_slope_or_pipe_size_selected": False,
        "extra_allowance_scope": "increment below original pipe/support budget only, not repeated fitting/support depth"}


def build(root):
    root, cache = Path(root), {}
    cfg = read_json(root/CONFIG)
    if (cfg.get("schema") != "house-b-front-drainage-layout-v1" or cfg.get("adopted") is not False
            or cfg["extra_below_original_pipe_budget_cases_mm"] != [0, 25, 50]
            or [(r["id"], r["width_mm"]) for r in cfg["routes"]] != [("public-arrival", 900), ("public-shower-operation", 700), ("dry-maintenance", 700), ("toilet-operation", 700), ("basin-operation", 700)]):
        raise ContractError("Keep the independent P4 study, full arrival width and declared sensitivity cases")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen P4 parent changed: "+name)
    parent, q3 = [read_json(root/cfg[key]) for key in ["parent_report", "q3_report"]]
    for report in [parent, q3]:
        for name, expected in report["source_hashes"].items():
            if digest(root, name, cache) != expected:
                raise ContractError("P4 parent source drift: "+name)
    controls = read_json(root/cfg["protected_controls"])["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    upper = read_json(root/parent["config"]["parent_report"])
    local, floor, clearances = local_layout(cfg, parent, upper)
    q3_shaft = next(r for r in q3["primary"]["rooms"] if r["id"] == "front-entertainment")["shafts_mm"]
    if q3_shaft != [local["shared_shaft_mm"]]:
        raise ContractError("P4 cannot silently move the retained Q3 KTV pipe shaft")
    drainage = drainage_comparison(cfg, local, parent, upper, floor)
    if any(r["centerline_over_protected_footprints"] for r in drainage["rows"]):
        raise ContractError("P4 centreline enters listed shrine, backing or palanquin protection")
    area_cases = [{"inset_each_mm": inset,
        **{r["id"]: round(finish(Polygon(r["polygon_mm"]), inset).difference(rect(local["shared_shaft_mm"])).area/1e6, 6)
            for r in floor["rooms"] if r["id"] in {"public-bath", "tea-foyer"}}}
        for inset in upper["config"]["illustrative_insets_mm"]]
    report = {"schema": "house-b-front-drainage-layout-report-v1", "date": cfg["date"], "config": cfg,
        "parent_report_hash": parent["report_hash"], "local_reference": local, "floor": floor,
        "clearances_mm": clearances, "drainage": drainage, "front_area_sensitivity": area_cases,
        "original_Q3_front_shaft_mm": q3_shaft, "Q3_shaft_moved_or_3F_fixture_layout_changed": False,
        "inherited_frontage": copy.deepcopy(parent["inherited_frontage"]),
        "unchanged_ground_and_roof_hashes": copy.deepcopy(parent["unchanged_ground_and_roof_hashes"]),
        "original_room_outlines_shaft_maintenance_stair_entry_and_windows_retained": True,
        "actual_site_or_product_data_received": 0, "protected_controls_unchanged": len(controls),
        "primary_abc_or_3d_changed": False, "adopted": False, "all_original_requirements_met": False,
        "rendered_qa": "not-run", "professional_approval": "unknown",
        "conclusion": "P4保原房界／井位／乾檢修，靠左WC／面盆、橫置茶水及左移公衛門，讓三條完整排水假線縮短；淋浴增加710mm。保公衛5.286與茶水扣門活動5.064，九門態及五試線同版核算。最有利剖面僅4.4mm餘量，額外25即失守，1F梯核落水與全棟排水未解，不當工程完成或併主3D。"}
    names = [CONFIG, *cfg["pinned_sources"], *parent["source_hashes"], *q3["source_hashes"], cfg["protected_controls"],
        "house_design/b_front_drainage_layout.py", "scripts/export_b_front_drainage_layout.py", "Docs/b-front-drainage-layout-v1.md"]
    report["source_hashes"] = {n: digest(root, n, cache) for n in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

"""Independent P3 front-service study; explicit sliders and full-path sensitivity."""
from __future__ import annotations

import copy
from itertools import product
from pathlib import Path

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from house_design.b_upper_replan import analyze_floor, bridge, finish, hit, rect, sweep
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG = "inputs/b-front-service-detail.json"
OUT = "structured/coordination/b-front-service-detail-v1"
STATES = {"open": 1, "half": .5, "closed": 0}


def leaves(spec, state):
    """Two separate tracks, interpolating closed to parked positions; no fake hinge."""
    amount = STATES[state]
    return [[closed+(park-closed)*amount, y, spec["leaf_width_mm"], spec["leaf_thickness_mm"]]
        for closed, park, y in zip(spec["closed_x_mm"], spec["park_x_mm"], spec["track_y_mm"], strict=True)]


def clear_width(spec, state):
    left = spec["a"][0]+spec["frame_budget_each_mm"]
    right = spec["b"][0]-spec["frame_budget_each_mm"]
    line = LineString([[left, 0], [right, 0]])
    blocked = unary_union([box(r[0], -1, r[0]+r[2], 1) for r in leaves(spec, state)])
    remaining = line.difference(blocked)
    parts = list(remaining.geoms) if hasattr(remaining, "geoms") else [remaining]
    return max((p.length for p in parts), default=0)


def panel_travel(spec):
    """Exact axis-aligned translation envelope, including unsampled intermediate states."""
    return [[min(a, b), y, abs(a-b)+spec["leaf_width_mm"], spec["leaf_thickness_mm"]]
        for a, b, y in zip(spec["closed_x_mm"], spec["park_x_mm"], spec["track_y_mm"], strict=True)]


def front_review(floor, cfg, parent_cfg):
    inset = parent_cfg["primary_inset_mm"]
    rs = {r["id"]: r for r in floor["rooms"]}
    interiors = {key: finish(Polygon(r["polygon_mm"]), inset) for key, r in rs.items()}
    surface = unary_union([s for key, s in interiors.items() if key != "front-open"]+
        [bridge(d, inset) for d in cfg["sliders"]]+[rect([0, 3900, 2400, 1000])])
    fixtures = [{**i, "key": r["id"]+":"+i["id"]} for r in floor["rooms"] for i in r["items"]]
    shaft = rect(cfg["shared_shaft_mm"])
    maintenance = rect(cfg["dry_maintenance_mm"])
    routes = []
    for route in cfg["routes"]:
        shape = sweep(route["points_mm"], route["width_mm"])
        routes.append({**route, "within_model_floor": surface.buffer(.01).covers(shape),
            "body_hits": [i["key"] for i in fixtures if hit(shape, rect(i["rect_mm"]))],
            "shaft_hit": hit(shape, shaft),
            "operation_shared": [i["key"] for i in fixtures if i.get("operation_mm") and hit(shape, rect(i["operation_mm"]))],
            "actual_access": "unknown-rectangles-not-person-or-wheelchair-kinematics"})
    combinations = []
    for bath, stair in product(STATES, repeat=2):
        states = {"bath": bath, "stair": stair}
        panels = [{"door": d["id"], "leaf": n, "rect_mm": r} for d in cfg["sliders"]
            for n, r in enumerate(leaves(d, states[d["id"]]), 1)]
        blockers = [{"route": r["id"], "doors": sorted({p["door"] for p in panels
            if hit(sweep(r["points_mm"], r["width_mm"]), rect(p["rect_mm"]))})} for r in cfg["routes"]]
        occupancy = interiors["tea-foyer"].intersection(unary_union([rect(p["rect_mm"]) for p in panels])).area/1e6
        combinations.append({"states": states, "panels": panels, "route_blockers": blockers,
            "body_hits": [{"door": p["door"], "body": i["key"]} for p in panels for i in fixtures if hit(rect(p["rect_mm"]), rect(i["rect_mm"]))],
            "shaft_hit": any(hit(rect(p["rect_mm"]), shaft) for p in panels),
            "maintenance_hit": any(hit(rect(p["rect_mm"]), maintenance) for p in panels),
            "panel_overlap": any(hit(rect(a["rect_mm"]), rect(b["rect_mm"])) for n, a in enumerate(panels) for b in panels[n+1:]),
            "clear_widths_mm": {d["id"]: clear_width(d, states[d["id"]]) for d in cfg["sliders"]},
            "door_occupancy_in_tea_finish_sqm": round(occupancy, 6)})
    toilet = next(i for i in rs["public-bath"]["items"] if i["id"] == "toilet")
    bath_door = next(d for d in cfg["sliders"] if d["id"] == "bath")
    axis_x = (bath_door["a"][0]+bath_door["b"][0])/2
    axis = LineString([[axis_x, 0], [axis_x, bath_door["a"][1]]])
    moving = [{"door": d["id"], "rect_mm": r} for d in cfg["sliders"] for r in panel_travel(d)]
    enclosure = unary_union([Polygon(rs[key]["polygon_mm"]) for key in ["public-bath", "tea-foyer"]])
    counter = next((i for i in fixtures if i["id"] == "tea-counter"), None)
    clearances = {d["id"]+"_counter": min(rect(r).distance(rect(counter["rect_mm"])) for r in leaves(d, "open"))
        for d in cfg["sliders"]} if counter else {}
    travel_clearances = {d["id"]+"_counter": min(rect(r).distance(rect(counter["rect_mm"])) for r in panel_travel(d))
        for d in cfg["sliders"]} if counter else {}
    return {"routes": routes, "door_combinations": combinations,
        "dry_maintenance_mm": cfg["dry_maintenance_mm"],
        "maintenance_inside_tea_finish": interiors["tea-foyer"].covers(maintenance),
        "maintenance_body_hits": [i["key"] for i in fixtures if hit(maintenance, rect(i["rect_mm"]))],
        "maintenance_shaft_overlap": hit(maintenance, shaft),
        "door_axis_over_toilet_body": axis.intersects(rect(toilet["rect_mm"])),
        "sliders_product_fire_smoke_rescue_and_actual_clear": "unknown",
        "full_panel_translation": {"envelopes": moving,
            "body_hits": [{"door": p["door"], "body": i["key"]} for p in moving for i in fixtures if hit(rect(p["rect_mm"]), rect(i["rect_mm"]))],
            "shaft_hit": any(hit(rect(p["rect_mm"]), shaft) for p in moving),
            "maintenance_hit": any(hit(rect(p["rect_mm"]), maintenance) for p in moving),
            "outside_nominal_front_enclosure": any(not enclosure.covers(rect(p["rect_mm"])) for p in moving)},
        "shared_shaft_within_enclosure_and_straddles_both_rooms": enclosure.covers(shaft)
            and all(hit(shaft, Polygon(rs[key]["polygon_mm"])) for key in ["public-bath", "tea-foyer"]),
        "fixed_body_clearance_to_parked_panels_mm": clearances,
        "fixed_body_clearance_to_full_panel_translation_mm": travel_clearances,
        "counter_operation_and_passage_simultaneous": False}


def shaft_accounting(floor, cfg):
    shape = rect(cfg["shared_shaft_mm"])
    areas = {a["id"]: a["net115_sqm"] for a in floor["areas"]}
    rooms = {r["id"]: Polygon(r["polygon_mm"]) for r in floor["rooms"]}
    losses = {key: round(finish(rooms[key], 115).intersection(shape).area/1e6, 6) for key in ["public-bath", "tea-foyer"]}
    occupancies = [r["door_occupancy_in_tea_finish_sqm"] for r in floor["front"]["door_combinations"]]
    reserved = finish(rooms["tea-foyer"], 115).intersection(unary_union([
        rect(r) for d in cfg["sliders"] for r in panel_travel(d)])).area/1e6
    return {"unique_physical_shaft_count_per_floor": 1, "room_references": 2,
        "gross_reserved_shaft_sqm": shape.area/1e6, "finish_losses_sqm": losses,
        "already_excluded_partition_budget_sqm": round(shape.area/1e6-sum(losses.values()), 6),
        "not_a_statutory_area_method": True, "areas115_sqm": areas,
        "tea_after_worst_modeled_door_occupancy_sqm": round(areas["tea-foyer"]-max(occupancies), 6),
        "full_panel_translation_reserved_in_tea_finish_sqm": round(reserved, 6),
        "tea_after_reserved_full_door_travel_sqm": round(areas["tea-foyer"]-reserved, 6)}


def center(body):
    return [body[0]+body[2]/2, body[1]+body[3]/2]


def drainage_review(cfg, parent, floors):
    p2 = next(o for o in parent["config"]["floors"]["options"] if o["id"] == cfg["parent_option"])
    d = parent["drainage"]
    section = d["arcade_section"]
    ground = center(d["front_offset_ground_candidate_mm"])
    shafts = {"P2": center(p2["public_shaft_mm"]), "P3": center(cfg["shared_shaft_mm"])}
    fixture_lists = {"P2": p2["public_fixtures"]+p2["tea_furniture"], "P3": cfg["public_fixtures"]+cfg["tea_furniture"]}
    forbidden = unary_union([Polygon(p) for p in parent["protected_polygons_mm"]]+[rect(parent["palanquin_rect_mm"])])
    rows = []
    for name, shaft in shafts.items():
        offset = [shaft, [shaft[0], ground[1]], ground]
        offset_length = LineString(offset).length
        for fid in cfg["branch_fixture_ids"]:
            body = next(i["rect_mm"] for i in fixture_lists[name] if i["id"] == fid)
            source = center(body)
            branch = [source, [shaft[0], source[1]], shaft]
            length = LineString(branch).length
            rows.append({"option": name, "fixture": fid, "branch_points_mm": branch, "offset_points_mm": offset,
                "branch_length_mm": length, "offset_length_mm": offset_length, "total_length_mm": length+offset_length,
                "hypothetical_total_fall_mm": (length+offset_length)/section["illustrative_slope_denominator"],
                "centerline_over_protected_footprints": LineString(branch+offset[1:]).intersects(forbidden),
                "actual_outlet_and_invert_known": False, "pipe_envelope_and_bends_designed": False})
    sensitivity = []
    for row in rows:
        for structure in section["illustrative_structure_depths_mm"]:
            for pipe in section["pipe_support_envelopes_mm"]:
                value = section["floor2_level_mm"]-structure-pipe-row["hypothetical_total_fall_mm"]-section["access_allowance_mm"]
                sensitivity.append({"option": row["option"], "fixture": row["fixture"], "structure_mm": structure,
                    "pipe_support_mm": pipe, "complete_path_remaining_mm": round(value, 3),
                    "illustrative_target_mm": section["required_illustrative_clear_mm"],
                    "meets_illustrative_target_only": value >= section["required_illustrative_clear_mm"]})
    offset_cases = [{"option": name, "length_mm": LineString([shaft, ground]).length,
        "best_case_offset_only_remaining_mm": round(section["floor2_level_mm"]-min(section["illustrative_structure_depths_mm"])
            -min(section["pipe_support_envelopes_mm"])-LineString([shaft, ground]).length/section["illustrative_slope_denominator"]
            -section["access_allowance_mm"], 3)} for name, shaft in shafts.items()]
    stair = next(r for r in floors[0]["rooms"] if r["id"] == "stair")
    return {"assumptions": section, "rows": rows, "full_path_section_sensitivity": sensitivity, "offset_only_cases": offset_cases,
        "section_scope": "listed-2F-fixture-branches-plus-under-2F-offset-only-not-3F-or-whole-building-drainage",
        "length_method": "fixture-body-centre-placeholder-orthogonal-branches-plus-offset-not-product-outlets",
        "slope_method": "same-start-invert-uniform-1-to-50-sensitivity-not-prescribed-or-designed-slope",
        "ground_candidate_mm": d["front_offset_ground_candidate_mm"],
        "ground_candidate_in_original_stair_sqm": rect(d["front_offset_ground_candidate_mm"]).intersection(Polygon(stair["polygon_mm"])).area/1e6,
        "ground_stair_void_proven": False, "direct_arcade_drop": "rejected-new-obstruction-in-arcade",
        "all_gravity_drains_and_vents_designed": False, "front_discharge_constructible": "unknown",
        "offset_only_can_give_false_positive": any(r["option"] == "P3" and not r["meets_illustrative_target_only"]
            and r["structure_mm"] == min(section["illustrative_structure_depths_mm"])
            and r["pipe_support_mm"] == min(section["pipe_support_envelopes_mm"]) for r in sensitivity),
        "beam_slab_actual_level_vent_cleanout_and_terminal": "unknown",
        "pumps_macerators_or_raised_floors_adopted": False}


def assert_geometry(floors, cfg):
    for f in floors:
        if (any(f["fixtures"][k] for k in ["body_hits", "operation_body_hits", "not_inside_115", "shaft_body_hits", "shaft_operation_hits",
                "fully_open_door_body_hits", "sampled_swing_body_hits"])
                or f["partition"]["overlaps"] or f["partition"]["unallocated_sqm"] > .000001 or f["partition"]["outside_frame_sqm"] > .000001
                or any(r["prohibited_overlap"] for r in f["religious_projection"]) or any(not w["on_room_boundary"] for w in f["windows"])
                or any(not r["within_model_floor"] or r["body_hits"] or r["shaft_hits"] or r["door_states"][0]["hits"] for r in f["routes"])):
            raise ContractError("P3 inherited planar defect: "+f["id"])
        front = f["front"]
        travel = front["full_panel_translation"]
        if (not front["maintenance_inside_tea_finish"] or front["maintenance_body_hits"] or front["maintenance_shaft_overlap"]
                or front["door_axis_over_toilet_body"] or travel["body_hits"] or travel["shaft_hit"] or travel["maintenance_hit"]
                or travel["outside_nominal_front_enclosure"] or not front["shared_shaft_within_enclosure_and_straddles_both_rooms"]
                or any(not r["within_model_floor"] or r["body_hits"] or r["shaft_hit"] for r in front["routes"])):
            raise ContractError("P3 front fixture, route, maintenance or toilet-axis defect")
        for state in front["door_combinations"]:
            if state["body_hits"] or state["shaft_hit"] or state["maintenance_hit"] or state["panel_overlap"]:
                raise ContractError("P3 moving slider collision")
            arrival = next(r for r in state["route_blockers"] if r["route"] == "public-arrival")
            if (not arrival["doors"]) != all(v == "open" for v in state["states"].values()):
                raise ContractError("P3 door states do not expose the expected route blockers")
        if f["area_ledger"]["areas115_sqm"]["public-bath"] < 5 or f["area_ledger"]["tea_after_reserved_full_door_travel_sqm"] < 5:
            raise ContractError("P3 lost the modeled public/tea area goals")
    for spec in cfg["sliders"]:
        if (len(spec["closed_x_mm"]) != 2 or spec["leaf_thickness_mm"] != 45 or spec["leaf_width_mm"] != 660
                or spec["track_y_mm"][1]-spec["track_y_mm"][0] != spec["leaf_thickness_mm"]+spec["track_gap_mm"]
                or [clear_width(spec, s) for s in STATES] != [900, 450, 0]):
            raise ContractError("P3 slider envelope or clear target changed")
        if (spec["b"][0]-spec["a"][0] != 1130 or spec["a"][1] != spec["b"][1]
                or spec["clear_target_mm"] != 900 or spec["frame_budget_each_mm"] != 115):
            raise ContractError("Keep nominal openings and clear-width assumptions explicit")


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    if cfg.get("schema") != "house-b-front-service-detail-v1" or cfg.get("adopted") is not False:
        raise ContractError("P3 is only an independent, unadopted front-service study")
    for name, expected in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != expected:
            raise ContractError("Frozen P2 source changed: "+name)
    controls = read_json(root/cfg["protected_controls"])["hashes"]
    cache = {}
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    parent = read_json(root/cfg["parent_report"])
    p2 = next(o for o in parent["options"] if o["id"] == cfg["parent_option"])
    pcfg = parent["config"]
    pspec = next(o for o in pcfg["floors"]["options"] if o["id"] == cfg["parent_option"])
    if cfg["shared_shaft_mm"][2:] != [400, 400]:
        raise ContractError("Keep the full 400x400 shaft reservation")
    for key, original in [("public_fixtures", pspec["public_fixtures"]), ("tea_furniture", pspec["tea_furniture"])]:
        if {i["id"]: sorted(i["rect_mm"][2:]) for i in cfg[key]} != {i["id"]: sorted(i["rect_mm"][2:]) for i in original}:
            raise ContractError("Do not shrink or remove original fixtures to fit P3")
    protected = unary_union([Polygon(p) for p in parent["protected_polygons_mm"]])
    storage = rect(parent["palanquin_rect_mm"])
    fs = []
    for previous in p2["floors"]:
        rooms = copy.deepcopy(previous["rooms"])
        for r in rooms:
            if r["id"] == "public-bath":
                r.update(items=copy.deepcopy(cfg["public_fixtures"]), shafts_mm=[cfg["shared_shaft_mm"]], doors=[])
            elif r["id"] == "tea-foyer":
                r.update(items=copy.deepcopy(cfg["tea_furniture"]) if previous["id"] == "floor-2" else [], shafts_mm=[cfg["shared_shaft_mm"]])
                if previous["id"] == "floor-3":
                    r["label"] = "乾式前室／同軸濕管井，非無濕管室"
        inherited_routes = [{k: r[k] for k in ["id", "width_mm", "points_mm", "purpose"]} for r in previous["routes"]
            if r["id"] not in {"public-arrival", "public-shower-operation"}]
        floor = analyze_floor(rooms, pcfg, protected, storage, pspec, previous["id"], inherited_routes)
        floor["front"] = front_review(floor, cfg, pcfg)
        floor["area_ledger"] = shaft_accounting(floor, cfg)
        floor["unchanged_rooms_hash"] = stable_hash([r for r in rooms if r["id"] not in {"public-bath", "tea-foyer"}])
        if floor["unchanged_rooms_hash"] != stable_hash([r for r in previous["rooms"] if r["id"] not in {"public-bath", "tea-foyer"}]):
            raise ContractError("P3 modified a room outside the front service scope")
        fs.append(floor)
    assert_geometry(fs, cfg)
    drainage = drainage_review(cfg, parent, fs)
    if any(r["centerline_over_protected_footprints"] for r in drainage["rows"]):
        raise ContractError("A new illustrative pipe centreline enters a protected footprint")
    report = {"schema": "house-b-front-service-detail-report-v1", "date": cfg["date"], "config": cfg, "option": "P3",
        "source_layout_report_sha256": sha256_file(root/cfg["parent_report"]), "floors": fs, "drainage": drainage,
        "inherited_frontage": p2["frontage"], "inherited_upper_stack": p2["upper_stack"],
        "unchanged_ground_and_roof_hashes": [{k: o[k] for k in ["id", "source_states_hash", "roof_reference_hash"]} for o in parent["drainage"]["ground_options"]],
        "frame_sqm": parent["frame_sqm"], "frame_land_ping": parent["frame_land_ping"],
        "protected_controls_unchanged": len(controls), "primary_abc_or_3d_changed": False, "parent_p1_p2_changed": False,
        "adopted": False, "all_requirements_met": False, "professional_approval": "unknown", "rendered_qa": "not-run",
        "actual_site_or_product_data_received": 0,
        "conclusion": "P3讓乾側檢修及兩組可關門狀態明確，保指定模型面積與原尺寸；完整支管＋偏移仍未解除騎樓淨高及原梯核落水缺口，保留配置方向而不宣稱排水成立。"}
    names = [CONFIG, cfg["protected_controls"], *cfg["pinned_sources"], "house_design/b_front_service_detail.py",
        "scripts/export_b_front_service_detail.py", "Docs/b-front-service-detail-v1.md", "house_design/b_claude_round3.py",
        "house_design/contracts.py", "house_design/project_status.py", "inputs/requirements.json", "inputs/planning-register.json"]
    report["source_hashes"] = {name: digest(root, name, cache) for name in names}
    report["report_hash"] = stable_hash(report)
    return report

"""Read-only geometry/engineering sensitivities from the frozen C balcony.

No model rebuild, network, product selection, compliance or construction approval.
"""
from __future__ import annotations

import copy
import math

from house_design.contracts import ContractError, read_json, sha256_file
from house_design.frozen_kaohsiung import MANIFEST, historical_artifact

SCHEMA = "house-c-balcony-coordination-v1"
CONFIG = "inputs/c-balcony-coordination.json"


def _path(root, name):
    target = (root/name).resolve()
    if target == root.resolve() or root.resolve() not in target.parents:
        raise ContractError("Source must be inside the project")
    return target


def _rect(geometry):
    return [geometry[k] for k in ("x_mm", "y_mm", "w_mm", "h_mm")]


def _box(box):
    return [box["minX"], box["minY"], box["maxX"]-box["minX"], box["maxY"]-box["minY"]]


def _overlap(a, b):
    x, y = max(a[0], b[0]), max(a[1], b[1])
    w = min(a[0]+a[2], b[0]+b[2])-x
    h = min(a[1]+a[3], b[1]+b[3])-y
    return [x, y, max(0, w), max(0, h)]


def _area(rect):
    return rect[2]*rect[3]/1e6


def _union_area(rects):
    """Exact axis-aligned area; overlapping upper projections count only once."""
    rects = [r for r in rects if r[2] > 0 and r[3] > 0]
    xs = sorted({x for r in rects for x in (r[0], r[0]+r[2])})
    total = 0
    for lo, hi in zip(xs, xs[1:], strict=False):
        intervals = sorted((r[1], r[1]+r[3]) for r in rects if r[0] < hi and r[0]+r[2] > lo)
        merged = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        total += (hi-lo)*sum(b-a for a, b in merged)
    return total/1e6


def _arcade_low_segments(points, arcade, target=3500):
    """Flag horizontal proxy pipe centrelines, not a pipe/beam clearance verdict."""
    result = []
    for a, b in zip(points, points[1:], strict=False):
        if a[2] != b[2] or a[2] >= target:
            continue
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        # Zero-width horizontal segments still cross a positive length of floor.
        if a[0] == b[0] and arcade[0] < a[0] < arcade[0]+arcade[2]:
            length = min(y1, arcade[1]+arcade[3])-max(y0, arcade[1])
        elif a[1] == b[1] and arcade[1] < a[1] < arcade[1]+arcade[3]:
            length = min(x1, arcade[0]+arcade[2])-max(x0, arcade[0])
        else:
            length = 0
        if length > 0:
            result.append({"from_mm": a, "to_mm": b, "overlap_length_mm": length,
                "centreline_z_mm": a[2], "conditional_under_beam_target_mm": target})
    return result


def _extension_impact(plans, core, extra, direction):
    """Whole-core strip sensitivity; it is not a proposed wall/door relocation."""
    x, y, w, depth = core
    strip = [x, y-extra if direction == "front" else y+depth, w, extra]
    floors = []
    for floor in plans["floors"]:
        if floor["id"] == "floor-4":
            continue
        affected = []
        for room in floor["rooms"]:
            overlap = _overlap(strip, _rect(room["geometry"]))
            if _area(overlap) > 0:
                g = room["geometry"]
                affected.append({"room": room["id"], "name": room["name"],
                    "overlap_rect_mm": overlap, "overlap_sqm": _area(overlap),
                    "nominal_remaining_depth_mm": g["h_mm"]-extra,
                    "actual_clear_width_after_walls_and_doors": "unknown"})
        floors.append({"floor": floor["id"], "affected": affected,
            "union_overlap_sqm": _union_area([r["overlap_rect_mm"] for r in affected])})
    return {"direction": direction, "whole_core_strip_mm": strip, "extra_depth_mm": extra,
        "floors": floors, "scope": "whole-core-envelope-only-not-required-final-stair-shape"}


def compare_sections(plans, cfg):
    floors = {f["id"]: f for f in plans["floors"]}
    stair = next(r for r in floors["floor-1"]["rooms"] if r["key"] == "stair1f")
    core = _rect(stair["geometry"])
    geometry = stair["features"]["stair_geometry"]
    footprint = _rect(stair["features"]["stair_footprint_mm"])
    existing_spare = core[3]-footprint[3]
    reference_run = (geometry["risers"]//2-1)*geometry["tread_mm"]
    if (geometry["risers"] % 2 or footprint[3] != reference_run+geometry["departure_offset_mm"]
            +geometry["middle_landing_mm"] or existing_spare < 0):
        raise ContractError("Unexpected original stair/landing allocation")
    detail, sensitivity = cfg["section_comparison"], cfg["section_sensitivity"]
    other_layers = detail["illustrative_other_layers_mm"]
    if isinstance(other_layers, bool) or not isinstance(other_layers, (int, float)) or not math.isfinite(other_layers) or other_layers < 0:
        raise ContractError("Other layer assumption must be a finite nonnegative value")
    options = []
    ids = set()
    for spec in detail["options"]:
        height, risers, tread = spec["first_storey_mm"], spec["risers"], spec["tread_mm"]
        if (spec["id"] in ids or any(isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v) or v <= 0 for v in (height, risers, tread))
                or not isinstance(risers, int) or risers % 2):
            raise ContractError("Section options need unique IDs and positive even riser counts")
        ids.add(spec["id"])
        run = (risers//2-1)*tread
        depth = run+geometry["departure_offset_mm"]+geometry["middle_landing_mm"]
        minimal_extra = max(0, depth-core[3])
        retained_extra = max(0, depth+existing_spare-core[3])
        shift = height-floors["floor-1"]["height_mm"]
        cases = []
        for soil in cfg["load_sensitivity"]["soil_depths_mm"]:
            underside = height-soil-sensitivity["illustrative_slab_thickness_mm"]-other_layers
            cases.append({"soil_depth_mm": soil, "illustrative_underside_mm": underside,
                "margin_to_conservative_target_mm": underside-sensitivity["conservative_arcade_clearance_target_mm"],
                "actual_soil_slab_layers_and_ground_datum": "unknown"})
        options.append({**copy.deepcopy(spec), "selected": False, "construction_approval": "unknown",
            "riser_mm": height/risers, "risers_per_flight": risers//2,
            "treads_per_flight": risers//2-1,
            "riser_change_vs_existing_mm": height/risers-floors["floor-1"]["height_mm"]/geometry["risers"],
            "tread_change_vs_existing_mm": tread-geometry["tread_mm"],
            "departure_landing_mm": geometry["departure_offset_mm"],
            "middle_landing_mm": geometry["middle_landing_mm"],
            "required_flight_and_landing_depth_mm": depth,
            "existing_core_rect_mm": core,
            "remaining_in_existing_box_mm": core[3]-depth,
            "minimum_extension_using_all_existing_spare_mm": minimal_extra,
            "extension_retaining_existing_spare_mm": retained_extra,
            "retained_front_and_rear_budget_mm": [footprint[1]-core[1], core[1]+core[3]-footprint[1]-footprint[3]],
            "front_extension_minimum": _extension_impact(plans, core, minimal_extra, "front"),
            "front_extension_with_existing_spare": _extension_impact(plans, core, retained_extra, "front"),
            "rear_extension_with_existing_spare": _extension_impact(plans, core, retained_extra, "rear"),
            "floor_bases_mm": {f["id"]: f["base_mm"]+(shift if f["id"] != "floor-1" else 0)
                for f in plans["floors"]},
            "upper_base_shift_mm": shift,
            "front_and_rear_gross_added_elevation_sqm": 2*floors["floor-1"]["width_mm"]*shift/1e6,
            "soil_cases_with_other_layer_assumption": cases,
            "stair_headroom_handrails_slab_openings_and_doors": "unknown",
            "all_upper_stair_arrivals": "must-recheck-not-automatically-aligned-by-base-shift"})
    if len(options) != 4:
        raise ContractError("Keep the original plus three explicit comparisons")
    return {"revision": 2, "original_core_rect_mm": core,
        "original_flight_footprint_mm": footprint, "original_total_depth_spare_mm": existing_spare,
        "illustrative_other_layers_mm": other_layers,
        "same_living_garden_laundry_direction": True, "all_options_unselected": True,
        "preferred_next_design_study": "c40-24-270",
        "preference_scope": "comfort-first-study-requires-corridor-replan-and-cost-review-not-adoption",
        "options": options}


def analyze(plans, cfg):
    """Copy source data; every physical/approval unknown remains explicit."""
    floors = {f["id"]: f for f in plans["floors"]}
    second = floors["floor-2"]
    balcony = next(r for r in second["rooms"] if r["key"] == "balcony2f")
    garden = balcony["features"]["kaohsiung_zones"]["garden_mm"]
    soils = balcony["features"]["kaohsiung_zones"]["soil_rects_mm"]
    footprint = _rect(balcony["geometry"])
    soil_area = sum(_area(r) for r in soils)
    upper = floors["floor-3"]
    projection = [{"room": r["id"], "outdoor": r["outdoor"],
        "rect_mm": _overlap(garden, _rect(r["geometry"]))}
        for r in upper["rooms"] if _area(_overlap(garden, _rect(r["geometry"]))) > 0]
    lower = floors["floor-1"]
    arcade = next(r for r in lower["rooms"] if r["key"] == "garage")
    fixed = [r for r in balcony["features"]["fixed_reserved_mm"] if r["kind"] == "hvac-service"]
    units = [u for u in balcony["features"]["hvac_units"] if u["type"] == "outdoor"]
    if len(units) != len(fixed):
        raise ContractError("Outdoor body and fixed service records must match")
    equipment = []
    for u, service in zip(units, fixed, strict=True):
        route = u["route"]
        points = route["polyline_mm"]
        length = sum(sum(abs(x-y) for x, y in zip(a, b, strict=True))
            for a, b in zip(points, points[1:], strict=False))
        lower_bound = sum(abs(x-y) for x, y in zip(points[0], points[-1], strict=True))
        allowance = route["bend_service_allowance_mm"]
        if not math.isclose(route["estimated_routed_length_mm"], length+allowance, abs_tol=1):
            raise ContractError("Stored HVAC length is inconsistent with source polyline")
        body = [u["x_mm"]-u["width_mm"]/2, u["y_mm"]-u["depth_mm"]/2,
            u["width_mm"], u["depth_mm"]]
        band = _box(service["aabb"])
        equipment.append({"id": u["id"], "indoor_room": route["indoor_room"],
            "body_rect_mm": body, "height_mm": u["height_mm"], "service_rect_mm": band,
            "service_to_garden_gap_mm": garden[1]-band[1]-band[3],
            "body_to_front_boundary_mm": body[1]-footprint[1],
            "estimated_routed_length_mm": length+allowance,
            "coordinate_lower_bound_with_same_allowance_mm": lower_bound+allowance,
            "excess_above_coordinate_lower_bound_mm": length-lower_bound,
            "elevation_difference_mm": abs(points[-1][2]-points[0][2]),
            "vertical_travel_mm": sum(abs(b[2]-a[2]) for a, b in zip(points, points[1:], strict=False)),
            "low_arcade_proxy_segments": _arcade_low_segments(points, _rect(arcade["geometry"])),
            "model": route["model"], "manual_source": route["manual_source"],
            "fan_discharge_direction": "unknown", "product_clearance_approval": "unknown",
            "shorter_route_status": "mathematical-bound-only-no-routed-alternative"})
    items = [{"id": i["id"], "label": i["label"], "body_rect_mm": _box(i["placement"]["aabb"]),
        "operation_rect_mm": _box(i["placement"]["operation_mm"])} for i in balcony["furniture"]]
    sink = next(i for i in items if i["id"].endswith(":utility-sink"))
    rack = next(i for i in items if i["id"].endswith(":clothes-rack"))
    living = next(r for r in second["rooms"] if r["key"] == "living2f")
    budget = cfg["load_sensitivity"]
    soil_sensitivity = []
    for depth in budget["soil_depths_mm"]:
        volume = soil_area*depth/1000
        load = volume*budget["saturated_unit_weight_kN_m3"]
        soil_sensitivity.append({"depth_mm": depth, "volume_m3": round(volume, 6),
            "soil_only_load_kN": round(load, 6), "soil_only_mass_tonnes": round(load/9.80665, 6)})
    floor_falls = [{"slope_percent": slope,
        "over_balcony_depth_mm": footprint[3]*slope/100,
        "over_service_depth_mm": (garden[1]-footprint[1])*slope/100,
        "over_garden_depth_mm": garden[3]*slope/100} for slope in cfg["drain_sensitivity"]["slopes_percent"]]
    section = cfg["section_sensitivity"]
    section_cases = []
    for height in section["storey_heights_mm"]:
        for depth in budget["soil_depths_mm"]:
            upper_bound = height-depth-section["illustrative_slab_thickness_mm"]
            section_cases.append({"storey_height_mm": height, "soil_depth_mm": depth,
                "slab_underside_upper_bound_mm": upper_bound,
                "remaining_for_other_layers_mm": upper_bound-section["conservative_arcade_clearance_target_mm"],
                "status": "optimistic-section-budget-only-not-structural-or-lawful-clearance"})
    return {"schema": SCHEMA, "detail_revision": 2, "status": cfg["status"], "owner_use_direction": "accepted-for-development",
        "full_scheme_adopted": False, "professional_approval": "unknown", "drawings_or_products_changed": False,
        "option": "c-split", "state": "daily", "balcony_rect_mm": footprint,
        "garden_rect_mm": copy.deepcopy(garden), "soil_rects_mm": copy.deepcopy(soils),
        "woody_points_mm": copy.deepcopy(balcony["features"]["kaohsiung_zones"]["woody_points_mm"]),
        "local_route_mm": copy.deepcopy(balcony["features"]["kaohsiung_zones"]["local_route_mm"]),
        "service_routes_mm": copy.deepcopy(balcony["features"]["kaohsiung_zones"]["service_routes_mm"]),
        "garden_sqm": _area(garden), "soil_sqm": soil_area,
        "soil_ratio": soil_area/_area(garden), "soil_depth_selected_mm": None,
        "upper_projection": {"floor": upper["id"], "floor_base_mm": upper["base_mm"],
            "balcony_base_mm": second["base_mm"], "nominal_floor_to_floor_mm": second["height_mm"],
            "overlaps": projection, "union_projected_sqm": _union_area([p["rect_mm"] for p in projection]),
            "actual_solid_cover_slab_and_legal_eligibility": "unknown"},
        "under_soil": {"room": arcade["id"],
            "overlap_sqm": _union_area([_overlap(s, _rect(arcade["geometry"])) for s in soils]),
            "use": "first-floor-front-arcade-proxy-not-lawful-area"},
        "connected_living_room": {"id": living["id"], "nominal_rect_mm": _rect(living["geometry"]),
            "nominal_sqm": _area(_rect(living["geometry"])), "legal_measurement": "unknown"},
        "items": items, "hvac": equipment,
        "coordinate_margins_mm": {"sink_operation_to_garden": garden[1]-sum(sink["operation_rect_mm"][1::2]),
            "rack_operation_width": rack["operation_rect_mm"][2],
            "soil_rear_to_indoor_wall": footprint[1]+footprint[3]-max(r[1]+r[3] for r in soils)},
        "soil_load_sensitivity": {"saturated_unit_weight_kN_m3": budget["saturated_unit_weight_kN_m3"],
            "cases": soil_sensitivity,
            "exclusions": ["slab", "waterproofing-and-drainage-layers", "retaining-edge", "plants",
                "people", "other-ponding", "wind-and-seismic", "load-combinations"],
            "not_a_minimum_soil_depth_or_capacity_check": True},
        "ponding_sensitivity": {"depth_mm": budget["ponding_depth_mm"],
            "over_garden_only_mass_tonnes": _area(garden)*budget["ponding_depth_mm"]/1000,
            "acceptable_ponding_or_overflow_level": "unknown"},
        "drain_fall_sensitivity": floor_falls, "actual_drain_outlets_and_diameters": None,
        "section_sensitivity": {**copy.deepcopy(section), "cases": section_cases,
            "all_upper_elevations_and_stairs_if_height_changes": "separate-replan-required"},
        "section_comparison": compare_sections(plans, cfg),
        "service_routes_scope": "existing-700mm-rectangle-only-not-wheelchair-or-product-maintenance",
        "legacy_reserved_mm": "not-used-as-current-service-proof-use-fixed_reserved_mm-only"}


def build(root):
    cfg = read_json(root/CONFIG)
    if (cfg.get("schema") != SCHEMA or cfg.get("option") != "c-split" or cfg.get("state") != "daily"
            or cfg.get("status") != "engineering-coordination-not-construction"
            or cfg.get("professional_approval") != "unknown"):
        raise ContractError("Preserve C-only coordination scope and unknown approvals")
    sensitivities = [*cfg["load_sensitivity"]["soil_depths_mm"],
        cfg["load_sensitivity"]["saturated_unit_weight_kN_m3"],
        *cfg["drain_sensitivity"]["slopes_percent"],
        *cfg["section_sensitivity"]["storey_heights_mm"],
        cfg["section_sensitivity"]["illustrative_slab_thickness_mm"],
        cfg["section_sensitivity"]["conservative_arcade_clearance_target_mm"]]
    if (not sensitivities or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
            for v in sensitivities) or not cfg["load_sensitivity"]["soil_depths_mm"]
            or not cfg["drain_sensitivity"]["slopes_percent"]
            or not cfg["section_sensitivity"]["storey_heights_mm"]
            or not math.isfinite(cfg["load_sensitivity"]["ponding_depth_mm"])
            or cfg["load_sensitivity"]["ponding_depth_mm"] < 0):
        raise ContractError("Sensitivity assumptions must be finite positive values")
    source = _path(root, cfg["base_report"])
    if sha256_file(source) != cfg["base_report_sha256"]:
        raise ContractError("Frozen balcony report changed; review new basis explicitly")
    report = read_json(source)
    if report.get("adopted") is not False or not report.get("source_hashes") or not report.get("artifact_hashes"):
        raise ContractError("Missing independent frozen comparison evidence")
    for group in (report["source_hashes"], report["artifact_hashes"]):
        for name, digest in group.items():
            if sha256_file(_path(root, name)) != digest:
                if name not in report["artifact_hashes"] or sha256_file(historical_artifact(root, name, digest)) != digest:
                    raise ContractError("Frozen dependency changed: "+name)
    option = next(o for o in report["options"] if o["id"] == cfg["option"])
    state = next(s for s in option["states"] if s["id"] == cfg["state"])
    result = analyze(state["plans"], cfg)
    inputs = [CONFIG, cfg["base_report"], "house_design/c_balcony_coordination.py",
        "scripts/export_c_balcony_coordination.py", "house_design/frozen_kaohsiung.py", MANIFEST]
    result["source_hashes"] = {name: sha256_file(root/name) for name in inputs}
    result["frozen_parent_sources_verified"] = len(report["source_hashes"])
    result["frozen_parent_artifacts_verified"] = len(report["artifact_hashes"])
    return result

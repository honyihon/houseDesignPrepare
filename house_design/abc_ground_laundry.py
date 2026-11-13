"""Independent laundry reservations from frozen plans; no original models or decisions written."""
from __future__ import annotations

import copy
from collections import Counter
from itertools import combinations
from pathlib import Path

from shapely.geometry import LineString, box
from shapely.ops import unary_union

from house_design.contracts import ContractError, stable_hash
from house_design.project_status import digest, read_public_json

CONFIG = "inputs/abc-ground-laundry.json"
OUT = "structured/coordination/abc-ground-laundry-v1"
DOC = "Docs/abc-ground-laundry-v1.md"
SOURCE = "structured/candidates/kaohsiung-house-options/c-stair-integration.json"


def rect(value):
    if not isinstance(value, list) or len(value) != 4 or any(type(v) not in {int, float} for v in value) or min(value[2:]) <= 0:
        raise ContractError("Laundry rectangles need xy/width/depth, with positive dimensions")
    return box(value[0], value[1], value[0]+value[2], value[1]+value[3])


def aabb(value):
    return [value["minX"], value["minY"], value["maxX"]-value["minX"], value["maxY"]-value["minY"]]


def room_rect(room):
    return [room["geometry"][k] for k in ["x_mm", "y_mm", "w_mm", "h_mm"]]


def overlap(a, b):
    return a.intersection(b).area > .01


def plan_floor(source, option, floor):
    states = next(o["states"] for o in source["options"] if o["id"] == option)
    return next(f for s in states if s["id"] == "daily" for f in s["plans"]["floors"] if f["id"] == floor)


def normalized_rooms(floor):
    return [{"id": r["key"], "label": r["name"], "rect_mm": room_rect(r),
        "items": [{"id": i["id"], "label": i["label"], "rect_mm": aabb(i["placement"]["aabb"])}
            for i in r["furniture"]]} for r in floor["rooms"]]


def reservations(room):
    return [{"id": f"{r['kind']}-{n}", "kind": r["kind"], "rect_mm": aabb(r["aabb"])}
        for n, r in enumerate(room["features"].get("reserved_mm", []))]


def screen_plan(spec, fixed, inset, width):
    """Check only listed bodies/operations and a local square-envelope route, not door products."""
    floor = unary_union([rect(r) for r in spec["region_rects_mm"]])
    finished = floor.buffer(-inset, join_style=2)
    bodies = spec["bodies"]
    operations = spec["operations"]
    route = LineString(spec["route_points_mm"]).buffer(width/2, cap_style=3, join_style=2)
    turn = rect(spec["turn_rect_mm"]) if spec.get("turn_rect_mm") else None
    physical_fixed = [f for f in fixed if f["kind"] != "door-approach"]
    result = {
        "nominal_region_sqm": round(floor.area/1e6, 6),
        "finished_region_sqm_assumption": round(finished.area/1e6, 6),
        "new_body_outside_finished": [i["id"] for i in bodies if not finished.buffer(.01).covers(rect(i["rect_mm"]))],
        "operation_outside_finished": [i["id"] for i in operations if not finished.buffer(.01).covers(rect(i["rect_mm"]))],
        "body_pair_hits": [{"a": a["id"], "b": b["id"]} for a, b in combinations(bodies, 2)
            if overlap(rect(a["rect_mm"]), rect(b["rect_mm"]))],
        "new_body_fixed_hits": [{"body": i["id"], "fixed": f["id"]} for i in bodies for f in fixed
            if overlap(rect(i["rect_mm"]), rect(f["rect_mm"]))],
        "operation_fixed_hits": [{"operation": i["id"], "fixed": f["id"]} for i in operations for f in physical_fixed
            if overlap(rect(i["rect_mm"]), rect(f["rect_mm"]))],
        "operation_other_body_hits": [{"operation": op["id"], "body": i["id"]} for op in operations for i in bodies
            if overlap(rect(op["rect_mm"]), rect(i["rect_mm"]))],
        "operation_shared": [{"a": a["id"], "b": b["id"],
            "overlap_sqm": round(rect(a["rect_mm"]).intersection(rect(b["rect_mm"])).area/1e6, 6)}
            for a, b in combinations(operations, 2) if overlap(rect(a["rect_mm"]), rect(b["rect_mm"]))],
        "operation_door_approach_shared": [{"operation": op["id"], "approach": f["id"]} for op in operations for f in fixed
            if f["kind"] == "door-approach" and overlap(rect(op["rect_mm"]), rect(f["rect_mm"]))],
        "local_route_width_mm": width,
        "local_route_inside_finished": finished.buffer(.01).covers(route),
        "local_route_fixed_hits": [i["id"] for i in bodies+physical_fixed if overlap(route, rect(i["rect_mm"]))],
        "turn_inside_finished": finished.buffer(.01).covers(turn) if turn is not None else None,
        "turn_lowered_body_hits": [i["id"] for i in bodies+physical_fixed if turn is not None and overlap(turn, rect(i["rect_mm"]))],
        "turn_if_drying_fully_stowed_body_hits": [i["id"] for i in bodies+physical_fixed
            if turn is not None and i.get("kind") != "drying" and overlap(turn, rect(i["rect_mm"]))],
        "stowed_drying_headroom_and_product_verified": False,
        "existing_fixed_outside_finished": [f["id"] for f in physical_fixed if not finished.buffer(.01).covers(rect(f["rect_mm"]))],
        "whole_route_or_care_approved": False, "product_door_sweeps_verified": False,
    }
    failures = [key for key in ["new_body_outside_finished", "operation_outside_finished", "body_pair_hits",
        "new_body_fixed_hits", "operation_fixed_hits", "operation_other_body_hits", "local_route_fixed_hits"] if result[key]]
    if not result["local_route_inside_finished"]:
        failures.append("local_route_outside_finished")
    if failures:
        raise ContractError("Laundry local geometry conflict in "+spec["id"]+": "+", ".join(failures))
    return result


def validate_config(cfg, owner):
    required = owner.get("confirmed", {})
    if (cfg.get("schema") != "house-abc-ground-laundry-preplanning-v1" or cfg.get("adopted") is not False
            or required.get("shared_group_at_ground_floor") != 1
            or required.get("C_floor2_initial_washer_use") != "temporarily-inactive-reserve-space"
            or required.get("A_upper_floor_washer_space_required") is not True
            or cfg.get("source_options") != {"A": "a-rear-study", "B": ["b-rear-split", "b-front-split"], "C": "c-split"}
            or cfg.get("finished_inset_assumption_mm") != 115
            or cfg.get("assumed_total_door_frame_budget_mm") != 230
            or cfg.get("discussion_route_target_mm") != 900
            or cfg.get("a_upper_reserve", {}).get("floor") != "floor-2"):
        raise ContractError("Preserve the latest shared-laundry direction, source alternatives and explicit assumptions")
    for key in ["compact", "expanded"]:
        bodies = cfg[key]["bodies"]
        if (sum(i["kind"] == "washer" for i in bodies) != 1 or sum(i["kind"] == "drying" for i in bodies) != 1
                or sum(i["id"] == "optional-dryer-bay" for i in bodies) != 1
                or len({i["id"] for i in bodies}) != len(bodies)):
            raise ContractError("Each independent laundry comparison needs one washer and distinct drying reservations")
    if not cfg["open_actual_conditions"] or any(v is not None for v in cfg["open_actual_conditions"].values()):
        raise ContractError("Public laundry conditions remain blank until actual evidence is supplied")


def build(root):
    root, cache = Path(root), {}
    cfg = read_public_json(root, CONFIG)
    owner = read_public_json(root, cfg["owner_reference"])
    validate_config(cfg, owner)
    for name, expected in cfg["pinned_sources"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("Frozen laundry basis changed: "+name)
    controls = read_public_json(root, "inputs/abc-next-protected-controls.json")["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    source = read_public_json(root, SOURCE)
    first = plan_floor(source, "a-rear-study", "floor-1")
    second = plan_floor(source, "a-rear-study", "floor-2")
    a1 = {r["key"]: r for r in first["rooms"]}
    a2 = {r["key"]: r for r in second["rooms"]}
    balcony, kitchen = a1["balcony1"], a1["kitchen"]
    filter_item = next(i for i in balcony["furniture"] if i["label"] == "淨軟水／過濾設備")
    old_washer = next(i for i in balcony["furniture"] if i["label"] == "洗衣機")
    fixed = reservations(balcony)
    filter_fixed = {"id": filter_item["id"], "kind": "existing-filter", "rect_mm": aabb(filter_item["placement"]["aabb"])}
    compact = copy.deepcopy(cfg["compact"])
    compact["fixed"] = fixed+[filter_fixed]
    compact["screen"] = screen_plan(compact, compact["fixed"], 115, 900)
    expanded = copy.deepcopy(cfg["expanded"])
    expanded["fixed"] = fixed
    # The rear door/approach moves with the proposed kitchen rear boundary in this comparison only.
    expanded["fixed"] = [r for r in expanded["fixed"] if r["kind"] != "door-approach"]
    expanded["fixed"].append({"id": "proposed-kitchen-rear-approach", "kind": "door-approach", "rect_mm": [1200, 14900, 1100, 900]})
    expanded["screen"] = screen_plan(expanded, expanded["fixed"], 115, 900)
    if expanded["screen"]["turn_lowered_body_hits"]:
        raise ContractError("The deeper laundry comparison must disclose any permanent turning conflict")
    old_kitchen = room_rect(kitchen)
    new_kitchen = [*old_kitchen[:3], expanded["kitchen_new_rear_y_mm"]-old_kitchen[1]]
    expanded["kitchen_area"] = {"before_nominal_sqm": round(rect(old_kitchen).area/1e6, 6),
        "after_nominal_sqm": round(rect(new_kitchen).area/1e6, 6),
        "loss_nominal_sqm": round((rect(old_kitchen).area-rect(new_kitchen).area)/1e6, 6),
        "new_rect_mm": new_kitchen,
        "original_fixture_bodies_inside_nominal": all(rect(new_kitchen).covers(rect(aabb(i["placement"]["aabb"]))) for i in kitchen["furniture"]),
        "finished_kitchen_and_door_sweeps_verified": False}
    if expanded["kitchen_area"]["loss_nominal_sqm"] != 2.232:
        raise ContractError("Do not hide or change the deeper bay's kitchen area cost")
    upper = copy.deepcopy(cfg["a_upper_reserve"])
    upper["region_rects_mm"] = [room_rect(a2["balcony2"])]
    upper["bodies"], upper["operations"] = [upper.pop("body")], [upper.pop("operation")]
    upper["fixed"] = reservations(a2["balcony2"])
    upper["screen"] = screen_plan(upper, upper["fixed"], 115, 900)
    c2 = plan_floor(source, "c-split", "floor-2")
    c_balcony = next(r for r in c2["rooms"] if r["key"] == "balcony2f")
    c_washer = next(i for i in c_balcony["furniture"] if i["id"].endswith(":washer"))
    c_ground = read_public_json(root, "structured/coordination/c-ground-coordination-v1/review.json")
    c_service = next(r for r in c_ground["rooms"] if r["id"] == "service")
    b = read_public_json(root, "structured/coordination/b-claude-round3-v1/review.json")
    b_evidence = []
    for option in b["stack_and_entry"]["options"]:
        for state in option["states"]:
            washers = [i for r in state["floor1"]["rooms"] for i in r["furniture"] if i["id"].endswith(":washer")]
            b_evidence.append({"option": option["id"], "state": state["id"], "existing_washer_rects_mm": [i["rect_mm"] for i in washers],
                "new_shared_laundry_host_adopted": False})
    if len(b_evidence) != 6 or any(len(r["existing_washer_rects_mm"]) != 1 for r in b_evidence):
        raise ContractError("Preserve B rear/front and all three usage states without deleting source washers")
    doors = [{"id": "A1-public-to-kitchen", "nominal_mm": next(d["width_mm"] for d in kitchen["features"]["doors"] if d["face"] == "front")},
        {"id": "A1-kitchen-to-balcony", "nominal_mm": next(d["width_mm"] for d in kitchen["features"]["doors"] if d["face"] == "rear")},
        {"id": "A2-study-to-balcony", "nominal_mm": next(d["width_mm"] for d in a2["balcony2"]["features"]["doors"] if d["neighbor"].endswith(":study"))}]
    for door in doors:
        door.update({"assumed_clear_mm": door["nominal_mm"]-230, "target_mm": 900,
            "shortfall_mm": max(0, 900-(door["nominal_mm"]-230)), "actual_clear_mm": None, "verified": False})
    shared_boundary = min(old_kitchen[0]+old_kitchen[2], room_rect(a1["rear-hall1"])[0]+room_rect(a1["rear-hall1"])[2])-max(old_kitchen[0], room_rect(a1["rear-hall1"])[0])
    route_issue = {"A1_public_hall_to_kitchen_nominal_shared_edge_mm": shared_boundary,
        "required_nominal_for_900_clear_if_frame230_mm": 1130,
        "widening_requires_adjacent_replanning": shared_boundary < 1130,
        "MDF_alcove_released": False, "bedroom_pass_through_proposed": False,
        "note": "A公共乾區與廚房只接1040名義邊，不能直接在原邊硬畫1130／1200洞；若要實際900淨寬，需連分區、門組與MDF維修另排。"}
    requirements = read_public_json(root, "inputs/requirements.json")["requirements"]
    register = read_public_json(root, "inputs/planning-register.json")["items"]
    report = {"schema": "house-abc-ground-laundry-report-v1", "date": cfg["date"], "config": cfg,
        "owner_direction": owner, "recommended_research_host": "A-1F",
        "recommendation": "優先深化A一樓原後陽台轉向洗衣：既有機位改為共用、平放乾衣機只留位，晾衣降到可及高度。先不減廚房；需要不與晾衣共用的1500轉位時，再比較左側加深灣及其2.232㎡廚房代價。三棟總平面與實際門組未到，還不能把A位置定成全體長輩自行可達的共用區。",
        "host_comparison": [
            {"building": "A", "priority": "first-local-study-conditional-on-common-access", "basis": "既有6×1.8m後工作陽台、洗衣與給水設備，可先研究原占地轉向；不必動祭祀、C照護浴室或客餐。", "limits": "目前需經廚房；兩個900名義洞及跨棟遮雨通路未核，靠孝親房需核噪音振動。"},
            {"building": "B", "priority": "retain-source-not-first-shared-hub", "basis": "後門版已有家務、1200小晾架及原洗衣機，前門版乾衣仍不足。", "limits": "共享人流／濕衣不宜經祭祀與搬轎，香火氣味、乾背保護及排濕須分開；不把後巷當三棟已連通。"},
            {"building": "C", "priority": "not-in-current-830mm-rear-strip", "basis": f"現一樓後檢修帶深{c_service['rect_mm'][3]}mm，孝親與浴室不能借用作公用洗衣通路。", "limits": "新安裝預留寬750加操作900及兩側115，共1880mm，比830多1050；強塞會改照護／後濕區，暫不推薦。"}],
        "A1_source_rooms": normalized_rooms(first), "A2_source_rooms": normalized_rooms(second),
        "A1_existing_washer": {"id": old_washer["id"], "rect_mm": aabb(old_washer["placement"]["aabb"]), "product_reuse_verified": False},
        "A1_options": [compact, expanded], "A2_reservation": upper,
        "C2_space_retained": {"source_item": c_washer["id"], "rect_mm": aabb(c_washer["placement"]["aabb"]),
            "new_direction_use": "temporarily-inactive-reserve-space", "source_model_changed": False,
            "removed_from_original": False, "new_washer_purchased": False},
        "B_source_states_retained": b_evidence, "doors": doors, "A1_entry_constraint": route_issue,
        "cross_building_route": {"site_order": None, "adjacent_walls_can_open": None, "distance_mm": None,
            "front_route": "只研究既有合法通行空間平層取送，需核遮雨、濕滑、門框與高差；不在騎樓裝機、晾衣或停推車。",
            "rear_route": "僅在A／B／C各後口及共同後巷權利、轉向、門檻和遮雨均核實後比較；不能只憑B回報有後巷就採用。",
            "if_owner_cannot_travel": "家人／照服以分戶小衣籃或推車平層取送到同一組，長輩不提濕衣上樓；若沒有合法便利的共用到達，先退回整個共享位置研究。",
            "approved": False},
        "actual_conditions": cfg["open_actual_conditions"], "actual_conditions_received": 0,
        "formal_requirement_statuses": dict(Counter(r["status"] for r in requirements)),
        "formal_register_statuses": dict(Counter(r["status"] for r in register)),
        "protected_controls_unchanged": len(controls), "shared_active_group_direction": 1,
        "A_upper_active_machine_count_decided": False, "host_building_adopted": False,
        "original_ABC_or_3d_changed": False, "accepted_storage_viewers_changed": False,
        "adopted": False, "professional_approval": "unknown", "rendered_qa": "not-run",
        "geometry_scope": "listed-installation-reservations-and-local-square-route-only-not-products-person-motion-or-whole-route",
    }
    names = [CONFIG, cfg["owner_reference"], *cfg["pinned_sources"], DOC,
        "house_design/abc_ground_laundry.py", "scripts/export_abc_ground_laundry.py"]
    report["source_hashes"] = {n: digest(root, n, cache) for n in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

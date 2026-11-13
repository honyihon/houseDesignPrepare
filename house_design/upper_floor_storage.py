"""Nine-floor storage study from explicitly selected frozen models; no main-model writes."""
from __future__ import annotations

import copy
from pathlib import Path

from shapely.geometry import LineString, Polygon, box

from house_design.contracts import ContractError, stable_hash
from house_design.project_status import digest, read_public_json

CONFIG = "inputs/upper-floor-storage.json"
OUT = "structured/coordination/upper-floor-storage-v1"


def rect(values):
    x, y, w, h = values
    return box(x, y, x+w, y+h)


def aabb(values):
    return [values["minX"], values["minY"], values["maxX"]-values["minX"], values["maxY"]-values["minY"]]


def hit(a, b):
    return a.intersection(b).area > .1


def normalize_model(floor):
    rooms, fixed = [], []
    for room in floor["rooms"]:
        g, features = room["geometry"], room["features"]
        area = [g[k] for k in ["x_mm", "y_mm", "w_mm", "h_mm"]]
        items = [{"id":i["id"], "label":i["label"], "rect_mm":aabb(i["placement"]["aabb"]),
            "operation_mm":aabb(i["placement"]["operation_mm"]) if i["placement"].get("operation_mm") else None}
            for i in room["furniture"]]
        doors = []
        for door in features.get("doors", [])+features.get("open_connections", []):
            face, t, width = door["face"], door["ratio"], door["width_mm"]
            x, y, w, h = area
            if face in {"front", "rear"}:
                doors.append({"a":[x+w*t-width/2, y+(h if face == "rear" else 0)],
                    "b":[x+w*t+width/2, y+(h if face == "rear" else 0)]})
            else:
                doors.append({"a":[x+(w if face == "right" else 0), y+h*t-width/2],
                    "b":[x+(w if face == "right" else 0), y+h*t+width/2]})
        for n, reserve in enumerate(features.get("reserved_mm", [])):
            fixed.append({"id":room["key"]+":reserve:"+str(n), "label":reserve.get("kind", "原預留"), "rect_mm":aabb(reserve["aabb"])})
        for unit in features.get("hvac_units", []):
            w, h = unit["width_mm"], unit["depth_mm"]
            if unit["face"] in {"left", "right"}:
                w, h = h, w
            fixed.append({"id":unit["id"]+":"+unit["type"], "label":unit["id"]+"｜冷氣"+("室內機" if unit["type"] == "indoor" else "室外機"),
                "rect_mm":[unit["x_mm"]-w/2, unit["y_mm"]-h/2, w, h]})
        windows = []
        face = features.get("window_face")
        if face and features.get("window_review", {}).get("renderable"):
            x, y, w, h = area
            t, width = features.get("window_ratio", .5), features["window_mm"]
            if face in {"front", "rear"}:
                windows.append([x+w*t-width/2, y+(h if face == "rear" else 0), width])
        rooms.append({"id":room["key"], "label":room["name"], "polygon_mm":list(rect(area).exterior.coords),
            "items":items, "doors":doors, "windows_mm":windows, "shafts_mm":[], "outdoor":room["outdoor"], "kind":room["kind"]})
    return rooms, fixed, []


def normalize_source(source, spec):
    if spec["format"] == "model":
        option = next(o for o in source["options"] if o["id"] == spec["option"])
        floor = next(f for f in option["states"][0]["plans"]["floors"] if f["id"] == spec["floor"])
        return normalize_model(floor)
    if spec["format"] in {"p4", "q3"}:
        floor = source["floor"] if spec["format"] == "p4" else source["primary"]
        rooms = copy.deepcopy(floor["rooms"])
        fixed = [{"id":r["id"]+":shaft:"+str(n), "label":"管道井預留", "rect_mm":s}
            for r in rooms for n, s in enumerate(r["shafts_mm"])]
        for r in rooms:
            for n, door in enumerate(r["doors"]):
                if door.get("swing_rect_mm"):
                    fixed.append({"id":r["id"]+":door:"+str(n), "label":"原門活動包絡", "rect_mm":door["swing_rect_mm"]})
        return rooms, fixed, copy.deepcopy(floor["routes"])
    option = next(o for o in source["options"] if o["id"] == spec["option"])
    rooms = [{"id":"front-platform", "label":"RF前平台／24㎡目標仍未解", "polygon_mm":[[0,0],[6000,0],[6000,3900],[0,3900]],
        "items":copy.deepcopy(option["furniture"]), "doors":[option["front_door"]], "shafts_mm":[], "outdoor":True, "kind":"outdoor"}]
    fixed = copy.deepcopy(option["equipment_reservations"])
    for item in fixed:
        if item["kind"] == "cooling":
            item["label"] = item["id"]+"｜冷氣室外機及維修預留（非新購台數）"
    fixed += [{"id":"roof-stair", "label":"樓梯屋突／保留樓梯洞", "rect_mm":source["config"]["roof_enclosure_mm"]}]
    return rooms, fixed, copy.deepcopy(option["routes"])


def check_storage(rooms, fixed, routes, spec):
    room = next(r for r in rooms if r["id"] == spec["room"])
    body, operation = rect(spec["rect_mm"]), rect(spec["operation_mm"])
    boundary = Polygon(room["polygon_mm"]).buffer(-115, join_style=2)
    failures = []
    if not boundary.buffer(.01).covers(body) or not boundary.buffer(.01).covers(operation):
        failures.append("body-or-operation-outside-115mm-room-budget")
    reused = spec.get("reuse_item")
    bodies = [{**i, "id":r["id"]+":"+i["id"]} for r in rooms for i in r["items"]
        if not (r["id"] == spec["room"] and i["id"] == reused)]
    obstacles = bodies+fixed
    for label, shape in [("body", body), ("operation", operation)]:
        failures += [label+":"+i["id"] for i in obstacles if hit(shape, rect(i["rect_mm"]))]
    operations = [{"id":r["id"]+":"+i["id"], "shape":rect(i["operation_mm"])}
        for r in rooms for i in r["items"] if i.get("operation_mm") and not (r["id"] == spec["room"] and i["id"] == reused)]
    failures += ["body-over-old-operation:"+i["id"] for i in operations if hit(body, i["shape"])]
    shared_operations = [i["id"] for i in operations if hit(operation, i["shape"])]
    route_hits = []
    shared_routes = []
    for route in routes:
        path = LineString(route["points_mm"]).buffer(route["width_mm"]/2, cap_style=2, join_style=2)
        if hit(body, path):
            route_hits.append(route["id"])
        if hit(operation, path):
            shared_routes.append(route["id"])
    failures += ["body-over-route:"+value for value in route_hits]
    if reused:
        old = next(i for i in room["items"] if i["id"] == reused)
        if old["rect_mm"] != spec["rect_mm"] or old["operation_mm"] != spec["operation_mm"]:
            failures.append("reused-table-footprint-or-operation-changed")
    return {"failures":failures, "footprint_sqm":round(body.area/1e6, 4),
        "additional_floor_footprint_sqm":0 if reused else round(body.area/1e6, 4),
        "shared_operation_ids":shared_operations, "shared_route_ids":shared_routes,
        "scope":"listed-2D-bodies-reservations-and-routes-only-not-whole-route-or-professional-approval",
        "actual_height_load_product_door_operation_and_access":"unknown"}


def build(root):
    root, cache = Path(root), {}
    cfg = read_public_json(root, CONFIG)
    if cfg.get("schema") != "house-upper-floor-storage-v1":
        raise ContractError("Unknown storage study")
    for name, expected in cfg["pinned_sources"].items():
        if digest(root, name, cache) != expected:
            raise ContractError("Selected storage source changed: "+name)
    controls = read_public_json(root, "inputs/abc-next-protected-controls.json")["hashes"]
    for name, expected in controls.items():
        if digest(root, name, cache) != expected:
            raise ContractError("Protected original changed: "+name)
    sources = {name:read_public_json(root, name) for name in {s["source"] for s in cfg["cases"]}}
    cases = []
    for spec in cfg["cases"]:
        rooms, fixed, routes = normalize_source(sources[spec["source"]], spec)
        result = check_storage(rooms, fixed, routes, spec)
        if result["failures"]:
            raise ContractError(spec["id"]+": "+str(result["failures"]))
        if spec["building"] == "B" and spec["floor"] != "floor-4":
            if spec["room"] != "quiet-living":
                raise ContractError("Do not consume KTV, shrine backing protection or bedroom capacity")
        cases.append({**spec, "rooms":rooms, "fixed":fixed, "routes":routes, "review":result,
            "source_floor_hash":stable_hash({"rooms":rooms,"fixed":fixed,"routes":routes}), "adopted":False})
    if {(s["building"],s["floor"]) for s in cases} != {(b,f) for b in "ABC" for f in ["floor-2","floor-3","floor-4"]}:
        raise ContractError("Every ABC upper floor including RF needs an explicit storage study")
    names = [CONFIG, "house_design/upper_floor_storage.py", "scripts/export_upper_floor_storage.py",
        "Docs/abc-upper-floor-storage-v1.md", "inputs/abc-next-protected-controls.json", *cfg["pinned_sources"]]
    report = {"schema":"house-upper-floor-storage-report-v1", "date":cfg["date"], "owner_request":cfg["owner_request"],
        "cases":cases, "floors":9, "case_count":len(cases), "protected_controls_unchanged":len(controls),
        "original_wardrobes_furniture_room_outlines_and_hvac_changed":False,
        "primary_3d_changed":False, "professional_approval":"unknown", "browser_qa":"not-run", "adopted":False,
        "requirements_file_changed":False, "new_storage_intent_recorded_here":True,
        "source_hashes":{n:digest(root,n,cache) for n in names}}
    report["report_hash"] = stable_hash(report)
    return report

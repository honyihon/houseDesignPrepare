"""ABC owner-confirmed fresh-air programme; topology and budgets, not routed MEP design."""
from __future__ import annotations

import copy
from pathlib import Path

from house_design.abc_next_improvements import compact, selected
from house_design.c_coordination import public_path
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash

CONFIG = "inputs/abc-fresh-air-basis.json"
OUT = "structured/coordination/abc-fresh-air-v1"


def flow_balance(supply, erv_exhaust, bath=0, hood=0, shrine=0, extra_makeup=0):
    flows = [supply, erv_exhaust, bath, hood, shrine, extra_makeup]
    if any(v is not None and v < 0 for v in flows):
        raise ContractError("Outdoor airflow cannot be negative")
    net = None if any(v is None for v in flows) else supply+extra_makeup-erv_exhaust-bath-hood-shrine
    return {"outdoor_supply_m3_h": supply, "erv_to_outdoors_m3_h": erv_exhaust,
        "local_bath_m3_h": bath, "cooking_hood_m3_h": hood, "incense_m3_h": shrine,
        "additional_outdoor_makeup_m3_h": extra_makeup, "mechanical_net_m3_h": net,
        "predicted_pressure_pa": None, "whole_building_balance_verified": False,
        "meaning": "只算機械進出差，正數仍須排出路徑，負數仍須補氣；房間內轉送不增加室外風量。"}


def validate_network(nodes, links):
    mapping = {n["id"]: n for n in nodes}
    if len(mapping) != len(nodes):
        raise ContractError("Fresh-air network IDs must be unique")
    if any(n["system"] == "ordinary-erv" and n["role"] in {"incense-source", "cooking-source", "bath-exhaust"} for n in nodes):
        raise ContractError("Contaminated source cannot be relabelled as ordinary ERV return")
    for edge in links:
        if edge["from"] not in mapping or edge["to"] not in mapping:
            raise ContractError("Fresh-air link references a missing node")
        a, b = mapping[edge["from"]], mapping[edge["to"]]
        if a["building"] != b["building"]:
            raise ContractError("ABC cannot share air ducts between buildings")
        if edge["type"] == "duct" and a["system"] != b["system"]:
            raise ContractError("Dirty exhaust, incense and ordinary ERV cannot share ducts")
        if edge["type"] == "room-transfer" and not (a["role"] == "dry-space" and b["role"] == "bath-exhaust"):
            raise ContractError("Only the explicitly listed dry-to-bath transfer is budgeted here")
    return True


def network(zones, bid):
    nodes, links = [], []
    for suffix, role in [("OA", "outdoor-air"), ("ERV", "unselected-device-group"), ("EA", "outdoor-exhaust")]:
        nodes.append({"id": bid+":"+suffix, "building": bid, "system": "ordinary-erv", "role": role})
    links.extend([{"from": bid+":OA", "to": bid+":ERV", "type": "duct"},
        {"from": bid+":ERV", "to": bid+":EA", "type": "duct"}])
    for zone in zones:
        fid = zone["floor"]
        if zone["supply"]:
            zid = bid+":"+fid+":dry"
            nodes.append({"id": zid, "building": bid, "system": "ordinary-erv", "role": "dry-space"})
            links.extend([{"from": bid+":ERV", "to": zid, "type": "duct", "purpose": "SA"},
                {"from": zid, "to": bid+":ERV", "type": "duct", "purpose": "clean-return"}])
        if zone["wet"]:
            bath_id, outside = bid+":"+fid+":bath", bid+":"+fid+":bath-outdoor"
            nodes.extend([{"id": bath_id, "building": bid, "system": "local-bath", "role": "bath-exhaust"},
                {"id": outside, "building": bid, "system": "local-bath", "role": "outdoor-exhaust"}])
            links.append({"from": bath_id, "to": outside, "type": "duct"})
            if zone["supply"]:
                links.append({"from": bid+":"+fid+":dry", "to": bath_id, "type": "room-transfer",
                    "makeup_air_product_and_route": None})
        if zone["hood"]:
            hi, ho = bid+":"+fid+":hood", bid+":"+fid+":hood-outdoor"
            nodes.extend([{"id": hi, "building": bid, "system": "cooking-hood", "role": "cooking-source"},
                {"id": ho, "building": bid, "system": "cooking-hood", "role": "outdoor-exhaust"}])
            links.append({"from": hi, "to": ho, "type": "duct"})
    if bid == "B":
        for suffix, system, role in [("shrine-OA", "incense-makeup", "outdoor-air"),
            ("shrine-SA", "incense-makeup", "filtered-source-makeup"),
            ("shrine-source", "incense-exhaust", "incense-source"), ("shrine-EA", "incense-exhaust", "outdoor-exhaust")]:
            nodes.append({"id": "B:"+suffix, "building": "B", "system": system, "role": role})
        links.extend([{"from": "B:shrine-OA", "to": "B:shrine-SA", "type": "duct"},
            {"from": "B:shrine-source", "to": "B:shrine-EA", "type": "duct"}])
    validate_network(nodes, links)
    return {"nodes": nodes, "links": links, "ordinary_unit_count": None,
        "physical_routes_and_fire_compartments_approved": False,
        "scope": "系統拓樸；沒有表示風管已定位、開孔、無噪音或機房已容納。"}


def rosters(source, bdetail, round3, strict, cfg):
    result = {}
    for bid in ["A", "C"]:
        plans = selected(source, cfg["source_options"][bid])
        result[bid] = {f["id"]: f["rooms"] for f in compact(plans) if f["id"] != "floor-4"}
    bfirst = round3["stack_and_entry"]["options"][0]["states"][0]["floor1"]["rooms"]
    result["B"] = {"floor-1": copy.deepcopy(bfirst)}
    for f, front in zip(bdetail["geometry"]["floors"], strict["options"][0]["upper_floors"], strict=True):
        normalized = []
        for room in f["rooms"]:
            r = copy.deepcopy(room)
            r["id"] = "B:"+f["id"]+":"+r["id"]
            r["outdoor"] = False
            normalized.append(r)
        result["B"][f["id"]] = [*copy.deepcopy(front["retained_front"]), *normalized]
    return result


def analyze_zones(cfg, owner, roster):
    rows = []
    for original in cfg["zones"]:
        z = copy.deepcopy(original)
        bid, fid = z["building"], z["floor"]
        if z["people"] != owner["occupancy_by_building"][bid][fid]:
            raise ContractError("Fresh-air occupancy differs from the recorded owner reply")
        rooms = roster[bid][fid]
        by_id = {r["id"].split(":")[-1]: r for r in rooms}
        supplied = []
        for key in z["supply"]:
            if key not in by_id or by_id[key]["outdoor"]:
                raise ContractError("Fresh-air supply must name an existing indoor room: "+bid+":"+fid+":"+key)
            room = by_id[key]
            if (key in z["wet"]+z["hood"] or "illustrative_finished_rect_mm" in room
                    or any(i.get("shape") in {"toilet", "shower", "altar"} for i in room["furniture"])):
                raise ContractError("Ordinary fresh-air supply list cannot silently reuse wet or incense rooms")
            supplied.append({"id": room["id"], "name": room["name"], "actual_supply_m3_h": None,
                "closed_door_return_route": None, "terminal_position_mm": None})
        for key in z["wet"]+z["hood"]:
            if key not in by_id or by_id[key]["outdoor"]:
                raise ContractError("Local exhaust references an absent indoor room: "+key)
        z["supplied_rooms"] = supplied
        z["people_basis"] = "owner-confirmed-floor-total" if z["people"] is not None else "unknown-not-zero"
        z["night_supply_estimate_cases"] = [{"per_person_assumption_m3_h": q,
            "floor_total_m3_h": z["people"]*q if z["people"] is not None else None}
            for q in cfg["per_person_flow_assumptions_m3_h"]]
        z["installed_or_approved"] = False
        rows.append(z)
    if {(z["building"], z["floor"]) for z in rows} != {(b, "floor-"+str(f)) for b in "ABC" for f in [1, 2, 3]}:
        raise ContractError("Fresh-air study must retain all nine floor zones")
    return rows


def commissioning_rows():
    return [
        {"id": "FA-CLOSE", "item": "一二樓睡房關門／梯門關閉", "required": "各睡房實測室外送風與回風／轉送，不能只測客廳或主機口", "actual": None},
        {"id": "FA-EXHAUST", "item": "浴室、油煙、B香火獨排加強", "required": "同時運作時測送排風、補氣、門壓與氣味流向，不能用ERV銘牌微正壓代替", "actual": None},
        {"id": "FA-NIGHT", "item": "夜間低速", "required": "睡房CO2、風噪、床旁直吹與可關門條件，不能只用公共回風感測器", "actual": None},
        {"id": "FA-HUMID", "item": "高雄濕熱／濾網積塵", "required": "夏季含濕量、冷凝、防霉、實際靜壓與風量；全熱不當除濕機", "actual": None},
        {"id": "FA-SERVICE", "item": "濾網與整機拆換", "required": "實際可抽濾網、檢修與搬出，不踩床、不拆固定櫃、不侵占照護及樓梯淨高", "actual": None},
        {"id": "FA-FUTURE", "item": "三樓先預留", "required": "封口支路、管道／套管、電源、排出路徑與檢修；啟用後重新平衡，不假設現在可任意鑽梁", "actual": None},
    ]


def build(root):
    root = Path(root)
    cfg = read_json(root/CONFIG)
    for name, digest in cfg["pinned_sources"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("ABC fresh-air source changed: "+name)
    owner = read_json(root/cfg["owner_reference"])
    if owner["confirmed_requirement"]["mechanical_outdoor_air_required"] is not True:
        raise ContractError("ABC mechanical outdoor-air requirement needs owner evidence")
    parent = read_json(root/cfg["b_detail_report"])
    for name, digest in parent["source_hashes"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("ABC fresh-air prior dependency changed: "+name)
    controls = read_json(root/cfg["protected_controls"])
    for name, digest in controls["hashes"].items():
        if sha256_file(public_path(root, name)) != digest:
            raise ContractError("ABC fresh-air control changed: "+name)
    source = read_json(root/cfg["source_report"])
    round3, strict = read_json(root/cfg["b_round3_report"]), read_json(root/cfg["b_strict_report"])
    roster = rosters(source, parent, round3, strict, cfg)
    zones = analyze_zones(cfg, owner, roster)
    buildings = []
    for bid in "ABC":
        bz = [z for z in zones if z["building"] == bid]
        people = sum(z["people"] for z in bz if z["people"] is not None)
        buildings.append({"id": bid, "zones": bz, "known_regular_people": people,
            "ordinary_supply_cases_m3_h": [{"per_person_assumption": q, "known_people_only": people*q}
                for q in cfg["per_person_flow_assumptions_m3_h"]],
            "not_included_in_people_case": "三樓／訪客尖峰、法定背景通風、浴廁／油煙／香火補氣及實際靜壓",
            "system": network(bz, bid), "mechanical_outdoor_air_required": True,
            "selected_product": None, "actual_unit_count": None, "actual_unit_positions_mm": None,
            "actual_intake_exhaust_positions_mm": None})
    scenarios = [
        {"label": "ERV平衡低速示意", **flow_balance(120, 120)},
        {"label": "同一ERV＋浴室120獨排", **flow_balance(120, 120, bath=120)},
        {"label": "微增送風10＋浴室120獨排", **flow_balance(130, 120, bath=120)},
        {"label": "另補120配合浴室120（容量未核）", **flow_balance(120, 120, bath=120, extra_makeup=120)},
        {"label": "僅新風120、無已定排出", **flow_balance(120, 0)},
        {"label": "僅新風120＋浴室120示意", **flow_balance(120, 0, bath=120)},
        {"label": "油煙600及浴室120同開示意", **flow_balance(120, 120, bath=120, hood=600)},
        {"label": "B1香火補排量尚未核", **flow_balance(60, 60, shrine=None, extra_makeup=None)},
    ]
    report = {"schema": "house-abc-fresh-air-report-v1", "date": cfg["date"], "config": cfg,
        "source_layout_report_sha256": sha256_file(root/cfg["source_report"]), "owner_evidence": owner,
        "buildings": buildings, "known_regular_people_total": sum(b["known_regular_people"] for b in buildings),
        "flow_cases": scenarios, "units_comparison": [
            {"id": "building-central", "scope": "每棟獨立主機，分層分支可調節；B1香火另系統", "initial_erv_count_illustrative": 3,
             "benefit": "機台／濾網較少", "risk": "跨層送回風主幹、低速調節與防火／噪音／檢修要另排，不能借既有浴室井", "selected": False},
            {"id": "floor-zoned", "scope": "常用層各自小機，三樓先預留；B1香火另系統", "initial_erv_count_illustrative": 5,
             "benefit": "常用樓層可獨立運轉、少跨層主幹", "risk": "主機／濾網／外牆開口與維護成本較多；不代表實際一定五台", "selected": False}],
        "regret_priorities": ["現在做一二樓常睡房的有效室外送風，不只把主機放客廳", "現在做關門回風／消音轉送，保持C前室及樓梯門可關",
            "現在留主機整機拆換、濾網、風管、電源與正確孔位，不能只預留插座", "三樓先留封口支路與可用檢修空間，不先假設永遠不住",
            "B1獨立香火補排與隔煙；ERV不吸香火回收", "補氣、濕度、髒濾網與夜間噪音要實測，不把有全熱等同不會發黴"],
        "b_revision_notes": ["原兩條浴室獨排與關門轉送預案仍有用途，但要納入ERV／新風總風量平衡",
            "400×200補氣候選未定案；全熱只提供室外氣源，不能消除門內轉送的尺寸／阻視要求",
            "500×300只預算兩條浴室排氣，沒有容納ERV送回風主幹或主機",
            "B1香火新風與獨排分管，不把上層常住2人的60m³/h初估當香火補氣量",
            "仍未接受無窗公衛或兩衛面積取捨；原3D與前後門三態保留"],
        "commissioning": commissioning_rows(), "retained_b_entries": parent["retained_entries"],
        "new_ventilation_requirement_owner_confirmed": True, "layout_or_product_adopted": False,
        "all_requirements_met": False, "protected_controls_unchanged": len(controls["hashes"]),
        "browser_qa": "not-run", "actual_airflow_approved": False, "professional_approval": "unknown",
        "sources": read_json(root/cfg["research_reference"])}
    names = [CONFIG, *cfg["pinned_sources"], *parent["source_hashes"], cfg["protected_controls"],
        "house_design/abc_fresh_air.py", "scripts/export_abc_fresh_air.py", "Docs/abc-fresh-air-v1.md"]
    report["source_hashes"] = {name: sha256_file(root/name) for name in dict.fromkeys(names)}
    report["report_hash"] = stable_hash(report)
    return report

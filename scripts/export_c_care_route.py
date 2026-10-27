#!/usr/bin/env python3
"""Independent local snapshot patches. Never regenerate the verified parent."""
from __future__ import annotations

import copy
import html
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import export_c_care_entry as entry
from lib.model3d_placement import _door_approach
from lib.model3d_plan import plan_data, render_plan

from house_design.c_care_route import SCHEMA, SOURCE, STATUS, full_inward_sweep, leaf_at_angle, review, validate_config
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, utc_now, write_json
from house_design.current_design_basis import requirement_ledger

basis = entry.basis
OUT = "structured/candidates/c-care-route"
INDEX, VIEWER = OUT+".html", OUT+"-3d.html"
BOOTSTRAP = "scripts/templates/c-care-route-bootstrap.js"
OVERLAY = "scripts/templates/c-care-route-overlay.js"
CHECK = "scripts/check_c_care_route_playwright.cjs"
LABELS = {"baseline": "上版全開控制（前段仍有缺口）", "open": "三門全開／連續矩形試線",
          "street-closed": "只關朝街門／入房試線應阻擋", "bedroom-closed": "只關房門／入房試線應阻擋",
          "bath-closed": "只關浴室門／去衛浴試線應阻擋"}


def refine(model, cfg, state, private_cfg):
    floor = model["buildings"][0]["floors"][0]
    cells = basis.interior._rooms(floor)
    for key in cfg["public_rooms"]:
        c = cells[key]
        group = cells["living"]["space_group"]
        c["space_group"] = c["tour_features"]["space_group"] = group
        c["review_spec"]["group"] = group
        floor["layout_review"]["rooms"][key]["group"] = group
    cells["sliding-door"]["name"] = "梯旁照護走道（客餐接續無門片）"
    for a, b in (("living-hall", "sliding-door"), ("sliding-door", "living-hall")):
        cells[a]["tour_features"]["doors"] = [d for d in cells[a]["tour_features"]["doors"] if d["neighbor"] != cells[b]["id"]]
    entry._pair(cells, "living-hall", "sliding-door", "rear", 1200, 3000,
                "open-passage", "120cm連續通口（無門片／消防分隔待核）", opened=True)
    connections = floor["layout_review"]["connections"]
    connections[:] = [c for c in connections if set(c[:2]) != {"living-hall", "sliding-door"}]
    connections.append(["living-hall", "sliding-door", "open"])
    d, c = cfg["street_door"], cells["dining"]
    front = next(o for o in c["tour_features"]["doors"] if o["neighbor"] is None)
    front.update(width_mm=d["nominal_mm"], ratio=(d["center_x_mm"]-c["tour_mm"]["x_mm"])/c["tour_mm"]["w_mm"],
                 operation=d["operation"], label="朝街120cm名義內開門（門組／消防待核）")
    leaf_state = "closed" if state == "street-closed" else "open"
    c["tour_features"].setdefault("care_entry_leaves", []).append({"id": "street", "state": leaf_state,
        "rect_mm": leaf_at_angle(d["closed_leaf_mm"], d["pivot_mm"], 0 if leaf_state == "closed" else d["open_rotation_degrees"]),
        "height_mm": d["height_mm"], "status": "generic-leaf-envelope-not-selected-product", "counts_as_furniture": False})
    for key, door in private_cfg["doors"].items():
        value = "closed" if state == ("bedroom-closed" if key == "bedroom" else "bath-closed") else "open"
        leaf = next(panel for panel in cells[door["park_owner"]]["tour_features"]["care_entry_leaves"] if panel["id"] == key)
        leaf.update(state=value, rect_mm=copy.deepcopy(door[value+"_leaf_mm"]))
    for local, move in cfg["moves"].items():
        source = cells[move["room"]]
        destination = cells[move.get("destination", move["room"])]
        if source is destination:
            basis._move(source, local, move["rect_mm"], yaw=move["rotation_deg"], anchor="")
        else:
            item = basis._item(source, local)
            source["furniture"] = [i for i in source["furniture"] if i["id"] != item["id"]]
            source["furniture_placements"]["tour_mm"].pop(item["id"])
            item["relocated_from"] = item["id"]
            basis._place(destination, item, move["rect_mm"], move["rotation_deg"], "", local=local, freestanding_operation=True)
    model["furniture"]["rooms"] = sum(bool(c["furniture"]) for f in model["buildings"][0]["floors"] for c in basis.interior._rooms(f).values())
    # _candidate retains the original dining-set's 400mm surround even though
    # front_clearance_mm is zero. review() rejects losing/shrinking that space.
    for c in cells.values():
        f = c["tour_features"]
        f["reserved_mm"] = copy.deepcopy(f.get("fixed_reserved_mm", []))+[
            {"kind": "door-approach", "aabb": _door_approach(c["tour_mm"], o)} for o in f["doors"]]
        if f.get("stair_footprint_mm"):
            f["reserved_mm"].append({"kind": "stairs", "aabb": basis.interior._bounds([f["stair_footprint_mm"][k] for k in basis.interior.KEYS])})
        f["basis_routes"] = []
    overlays = [{"id": k, "kind": "900mm-body-centerline-only-not-wheelchair", "points_mm": v,
                 "blocked": (k == "arcade-to-bed" and state in {"street-closed", "bedroom-closed"}) or (k == "bed-to-bath" and state == "bath-closed")}
                for k, v in cfg["routes"].items()]
    x, y, w, depth = full_inward_sweep(d["closed_leaf_mm"], d["pivot_mm"])
    overlays.append({"id": "street-sweep", "kind": "sweep", "blocked": False,
                     "points_mm": [[x, y], [x+w, y], [x+w, y+depth], [x, y+depth], [x, y]]})
    cells["dining"]["tour_features"]["care_route_overlays"] = overlays


def _ledger(options, root):
    result = requirement_ledger([{**o, "id": "c-care-refined"} for o in options], read_json(root / "inputs/requirements.json"),
        read_json(root / "inputs/requirement-dispositions.json"), sha256_file(root / "inputs/requirements.json"))
    for scenario, option in zip(result["scenarios"], options, strict=True):
        scenario["id"], scenario["label"] = option["id"], option["label"]
        for row in scenario["rows"]:
            if row["requirement_id"] == "C.floor-1.idf_c":
                row.update(dedicated_service_area_credit_sqm=0, note="原IDF壁龕及600×600mm機櫃保留；共享前室不給獨立機房面積信用。")
            if row["requirement_id"] == "C.floor-1.elder_bath":
                row["note"] += " 仍由私人臥室進入，原公共直達照服偏好未滿足；完整轉位／排氣未核。"
            if row["requirement_id"] in {"C.floor-1.elder", "C.floor-1.elder_bath"}:
                row["flags"].append("whole-route-human-care-and-rescue-still-unknown")
                row["whole_route_care_acceptance"] = "unknown-specified-900mm-rectangle-is-not-wheelchair-approval"
                row["upstream_discussion_budgets_mm"] = [770, 770] if option["id"] == "c-route-control" else [970, 970]
    result["ledger_hash"] = stable_hash({k: v for k, v in result.items() if k != "ledger_hash"})
    return result


def build_study(root: Path = ROOT):
    cfg = read_json(root / SOURCE)
    validate_config(cfg)
    parent = basis._verified_report(root, cfg["base_report"])
    raw = basis.interior.read_model(root / cfg["base_viewer"])["c_care_entry"]
    option = next(o for o in raw["options"] if o["id"] == cfg["base_option"])
    base = next(s for s in option["states"] if s["id"] == cfg["base_state"])["model"]
    expected = next(s for o in parent["options"] if o["id"] == cfg["base_option"] for s in o["states"] if s["id"] == cfg["base_state"])["plans"]
    actual = plan_data(base)["buildings"][0]
    for f, ref in zip(actual["floors"], expected["floors"], strict=True):
        f["plan_file"] = ref["plan_file"]
    if stable_hash(actual) != stable_hash(expected):
        raise ContractError("Verified care-entry plan and actual source viewer differ")
    requirements = {r["id"]: r for r in read_json(root / "inputs/requirements.json")["requirements"]}
    if any(requirements[k]["constraints"]["door_clear_mm"] != 900 for k in ("C.floor-1.elder", "C.floor-1.elder_bath")):
        raise ContractError("Keep original 900mm targets; changed requirements need explicit review")
    private_cfg = read_json(root / cfg["private_entry_config"])
    original, options = base["buildings"][0], []
    for oid, label, states in (("c-route-control", "C｜上版入口控制（前段770mm缺口）", ["baseline"]),
                               ("c-route-refined", "C｜騎樓內側至照護入口連續動線提案", ["open", "street-closed", "bedroom-closed", "bath-closed"])):
        rows = []
        for state in states:
            model, refined = copy.deepcopy(base), oid == "c-route-refined"
            if refined:
                refine(model, cfg, state, private_cfg)
            model["bc_option"] = {"id": oid, "label": label, "revision": 1, "use_state": state, "status": STATUS,
                "adopted": False, "tradeoffs": cfg["limits"], "geometry_review": {}}
            model["source"] = {"c_care_route": SOURCE, "geometry_basis": "verified-parent-local-snapshot-patch-not-full-regeneration"}
            model["layout_review"].update(status=STATUS, checks=[])
            plans = plan_data(model)["buildings"][0]
            screen = basis.interior._screen(model, cfg["insets_mm"], original)
            if screen["operation_vs_fixed_body"]:
                raise ContractError("Do not lose furniture operation to widen a route")
            screen["route"] = review(plans, cfg, state, private_cfg, refined=refined)
            model["bc_option"]["geometry_review"] = screen
            for f in plans["floors"]:
                f["plan_file"] = oid+"_"+state+"_"+f["id"]+".svg"
            rows.append({"id": state, "label": LABELS[state], "plans": plans, "model": model, "review": screen})
        options.append({"id": oid, "label": label, "building": "C", "adopted": False, "status": STATUS, "states": rows})
    paths = {SOURCE, cfg["base_report"], cfg["base_viewer"], "scripts/export_c_care_route.py", "house_design/c_care_route.py", CHECK, BOOTSTRAP, OVERLAY, *parent["source_hashes"]}
    result = {"schema": SCHEMA, "revision": 1, "display_revision": 2, "generated_at": utc_now(), "status": STATUS,
        "adopted": False, "rendered_qa": "not-run", "frame_mm": cfg["frame_mm"], "default_option": cfg["default_option"], "default_state": "open",
        "professional_status": cfg["professional_status"], "limits": cfg["limits"], "options": options, "requirement_ledger": _ledger(options, root),
        "base_report_hash": parent["report_hash"], "browser_path": "Browser plugin not available; owner-run Windows Playwright only",
        "source_hashes": {p: sha256_file(root / p) for p in sorted(paths)}}
    result["report_hash"] = stable_hash({k: v for k, v in result.items() if k != "generated_at"})
    return result


def render_index(study):
    esc, sections = html.escape, []
    for option in study["options"]:
        states = []
        for s in option["states"]:
            oid, sid, detail = option["id"], s["id"], s["review"]["route"]
            route_text = '；'.join(k+('：指定試線被阻擋' if r["coordinate_failures"] else '：指定矩形試線無座標衝突') for k, r in detail["routes"].items())
            files = ''.join(f'<figure><figcaption>{esc(f["label"])}</figcaption><object type="image/svg+xml" data="c-care-route/{f["plan_file"]}"></object></figure>' for f in s["plans"]["floors"])
            opened = ' open' if oid == study["default_option"] and sid == 'open' else ''
            states.append(f'<details id="{oid}-{sid}" data-use-state="{sid}"{opened}><summary>{esc(s["label"])}</summary><p>{esc(route_text)}。關門阻擋是反例，不是通行通過。</p><a href="c-care-route-3d.html?scheme={oid}&amp;use={sid}">此狀態同源3D</a><figure><figcaption>1F 全路徑（騎樓內指定點至床／衛浴入口，非道路至室內通行核可）</figcaption><object type="image/svg+xml" data="c-care-route/{oid}_{sid}_floor-1.svg"></object></figure><details><summary>四層對照（上層不改）</summary>{files}</details></details>')
        sections.append(f'<section data-option="{option["id"]}"><h2>{esc(option["label"])}</h2>'+''.join(states)+'</section>')
    return ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>C騎樓至照護動線｜保留上版與連續路徑比較</title>'
        '<style>body{font:16px/1.65 system-ui,sans-serif;max-width:1120px;margin:auto;padding:18px;background:#f8faf8;color:#24382e}a{color:#17634d}.warning{background:#fff1d6;padding:12px;color:#65430b}section{border-top:1px solid #cbd5ce;margin-top:24px}summary{cursor:pointer;padding:12px 0;min-height:44px}figure{margin:12px 0;max-height:740px;overflow:auto;border:1px solid #cbd5ce}object{display:block;width:660px;max-width:none}table{border-collapse:collapse;width:100%}th,td{border:1px solid #cbd5ce;padding:8px;text-align:left}@media(max-width:640px){body{padding:12px}figure{max-height:600px}}</style><body><h1>C 騎樓至照護動線比較</h1>'
        '<p id="route-adoption-warning" class="warning">比較方案，未採用／專業未核。起於騎樓內側，不含道路高差、真實輪椅、消防或門組核可。</p>'
        '<p><a href="c-care-route-3d.html">開啟新版3D</a> · <a href="c-care-entry.html">上一版入口比較（不動）</a> · <a href="c-care-route/requirement-ledger.json">40列C需求對帳</a> · <a href="c-care-route/review.json">座標／門片／來源證據</a></p>'
        '<h2>本輪建議</h2><p>朝街門改120cm名義內開門，客餐至照護走道改120cm連續無門片通口；樓梯本體分隔門保留待消防核。四人餐桌、沙發、茶几與閱覽椅原尺寸／件數都保留，閱覽椅移右側公共彈性區，不刪椅子換通路。</p>'
        '<table><tr><th>項目</th><th>上版控制</th><th>新比較</th></tr><tr><td>朝街／客餐照護入口</td><td>各1000mm名義、770mm假設</td><td>各1200mm名義、970mm假設</td></tr><tr><td>前窗</td><td>2400mm</td><td>同寬同位置；窗與門洞100mm討論餘量</td></tr><tr><td>孝親房／套衛門</td><td>各1200mm名義拉門</td><td>原尺寸及停門不變，另作各自關門反例</td></tr></table>'
        '<p>970mm是每側扣115mm的討論值，不是實測。門片有實際外廓及解析全開掃掠檢查；把手、止擋、開角和門檻未知。內開不占公共騎樓，但仍須核開向；如法規要求外開，另比較退縮門斗並明列室內面積代價。</p><ul>'+''.join('<li>'+esc(n)+'</li>' for n in study["limits"])+'</ul>'+''.join(sections)+'</body></html>')


def write_study(study, root: Path = ROOT):
    directory = root / OUT
    directory.mkdir(parents=True, exist_ok=True)
    report = copy.deepcopy(study)
    for o in report["options"]:
        for s in o["states"]:
            s.pop("model")
    write_json(directory / "review.json", report)
    write_json(directory / "requirement-ledger.json", study["requirement_ledger"])
    ns = "{http://www.w3.org/2000/svg}"
    for o in study["options"]:
        for s in o["states"]:
            url = f'../c-care-route-3d.html?scheme={o["id"]}&use={s["id"]}'
            for f in s["plans"]["floors"]:
                svg = ET.fromstring(render_plan("C", f, viewer_url=url))
                svg.set("width", "660")
                svg.set("height", "1903")
                svg.set("data-route-option", o["id"])
                svg.set("data-use-state", s["id"])
                if f["id"] == "floor-1":
                    detail = s["review"]["route"]
                    if "street_sweep_mm" in detail:
                        x, y, w, d = detail["street_sweep_mm"]
                        ET.SubElement(svg, ns+"rect", {"x": str(x), "y": str(y), "width": str(w), "height": str(d), "fill": "none", "stroke": "#b45309", "stroke-width": "14", "stroke-dasharray": "50 30", "data-street-sweep": "conservative-analytic-not-certified"})
                    for r in f["rooms"]:
                        turn = r["features"].get("care_entry_turn_circle_mm")
                        if turn:
                            ET.SubElement(svg, ns+"circle", {"cx": str(turn[0]), "cy": str(turn[1]), "r": str(turn[2]), "fill": "none", "stroke": "#6d28d9", "stroke-width": "22", "stroke-dasharray": "80 60", "data-care-turn": "1500mm-reserve-not-wheelchair-rehearsal"})
                        for leaf in r["features"].get("care_entry_leaves", []):
                            x, y, w, d = leaf["rect_mm"]
                            ET.SubElement(svg, ns+"rect", {"x": str(x), "y": str(y), "width": str(w), "height": str(d), "fill": "#b45309", "fill-opacity": ".4", "stroke": "#b45309", "stroke-width": "18", "data-care-leaf-id": leaf["id"], "data-leaf-state": leaf["state"]})
                    for key, route in detail["routes"].items():
                        ET.SubElement(svg, ns+"polyline", {"points": ' '.join(f'{x},{y}' for x, y in route["points_mm"]), "fill": "none", "stroke": "#b43b25" if route["coordinate_failures"] else "#137d9c", "stroke-width": "24", "stroke-dasharray": "90 60", "data-care-route": key})
                (directory / f["plan_file"]).write_text(ET.tostring(svg, encoding="unicode"), encoding="utf-8")
    (root / INDEX).write_text(render_index(study), encoding="utf-8")
    cfg = read_json(root / SOURCE)
    text = (root / cfg["base_viewer"]).read_text()
    payload = {"c_care_route": {"default_option": study["default_option"], "options": [
        {"id": o["id"], "label": o["label"], "building": "C", "states": [{k: s[k] for k in ("id", "label", "model")} for s in o["states"]]} for o in study["options"]]}}
    text, count = re.subn(r'^\s*var DATA = .+;\s*$', lambda _: '  var DATA = '+json.dumps(payload, ensure_ascii=False, separators=(',', ':'))+';', text, count=1, flags=re.M)
    old = (root / entry.BOOTSTRAP).read_text()
    if count != 1 or text.count(old) != 1 or text.count('DATA.source.c_care_entry') != 2:
        raise ContractError("Care-entry snapshot anchors changed; do not mix old and new viewers")
    text = text.replace(old, (root / BOOTSTRAP).read_text()).replace('DATA.source.c_care_entry', 'DATA.source.c_care_route')
    text = text.replace('c-care-entry.html', 'c-care-route.html').replace('C孝親房入口比較', 'C騎樓至照護動線比較')
    text = text.replace('C騎樓至照護動線比較比較（未採用）', 'C騎樓至照護動線比較（未採用）')
    text = text.replace('aria-label="B／C比較方案控制（未採用）"', 'aria-label="C連續動線比較控制（未採用）"')
    if text.count('    var hvac=features.hvac || {};') != 1 or text.count('      careEntry:careEntryEvidence(),') != 1:
        raise ContractError("Missing local route overlay/evidence integration point")
    text = text.replace('    var hvac=features.hvac || {};', (root / OVERLAY).read_text()+'\n    var hvac=features.hvac || {};')
    evidence = '''  function careRouteEvidence(){
    return pickables.filter(function(m){return m.visible&&m.parent.visible&&m.userData.shell.visible;}).flatMap(function(m){
      return m.userData.shell.children.filter(function(p){return !!p.userData.careRoute;}).map(function(p){
        p.updateWorldMatrix(true,false);
        var matrix=new THREE.Matrix4().copy(m.parent.matrixWorld).invert().multiply(p.matrixWorld),a=p.geometry.attributes.position,points=[];
        for(var n=0;n<a.count;n++){var v=new THREE.Vector3().fromBufferAttribute(a,n).applyMatrix4(matrix);points.push([v.x/MM,-v.z/MM]);}
        return {room:m.userData.cell.id,...p.userData.careRoute,actualPointsMm:points};
      });
    });
  }
'''
    text = text.replace('  window.__htmlModel3dDebug = function () {', evidence+'\n  window.__htmlModel3dDebug = function () {')
    text = text.replace('      careEntry:careEntryEvidence(),', '      careRoute:careRouteEvidence(),\n      careEntry:careEntryEvidence(),')
    # Actual mesh leaf rendering/debug and mobile fit are inherited unchanged.
    (root / VIEWER).write_text(text, encoding="utf-8")
    return {"index": INDEX, "viewer": VIEWER, "report": OUT+"/review.json", "rendered_qa": "not-run", "report_hash": study["report_hash"]}


def main():
    print(json.dumps(write_study(build_study()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

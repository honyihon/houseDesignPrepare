#!/usr/bin/env python3
"""Independent C entry comparison from verified public snapshots, no full build."""
from __future__ import annotations

import copy
import html
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import export_current_design_basis as basis
from lib.model3d_placement import _door_approach
from lib.model3d_plan import plan_data, render_plan

from house_design.c_care_entry import SCHEMA, SOURCE, STATUS, review, validate_config
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, utc_now, write_json
from house_design.current_design_basis import requirement_ledger

OUT = "structured/candidates/c-care-entry"
INDEX, VIEWER = OUT+".html", OUT+"-3d.html"
BOOTSTRAP = "scripts/templates/c-care-entry-bootstrap.js"
OVERLAY = "scripts/templates/c-care-entry-overlay.js"


def _pair(cells, a, b, face, width, center, operation="unconfirmed", label="", *, opened=False):
    inverse = {"front": "rear", "rear": "front", "left": "right", "right": "left"}
    for key, other, side in ((a, b, face), (b, a, inverse[face])):
        g, t = basis.interior._rect(cells[key]), basis.interior._rect(cells[other])
        along_x = side in {"front", "rear"}
        axis, length = (0, 2) if along_x else (1, 3)
        edge = g[1] if side == "front" else g[1]+g[3] if side == "rear" else g[0] if side == "left" else g[0]+g[2]
        other_edge = t[1]+t[3] if side == "front" else t[1] if side == "rear" else t[0]+t[2] if side == "left" else t[0]
        if edge != other_edge or center-width/2 < max(g[axis], t[axis]) or center+width/2 > min(g[axis]+g[length], t[axis]+t[length]):
            raise ContractError("Actual paired opening leaves its shared wall: "+a+" / "+b)
        opening = {"face": side, "ratio": (center-g[axis])/g[length], "width_mm": width,
            "neighbor": cells[other]["id"], "operation": operation, "status": "explicit-bounded-proposal-not-verified"}
        if label:
            opening["label"] = label
        cells[key]["tour_features"]["open_connections" if opened else "doors"].append(opening)


def refine(model, cfg, state):
    floor = model["buildings"][0]["floors"][0]
    old = copy.deepcopy(basis.interior._rooms(floor))
    specs = {
        "stair1f": ("正式樓梯本體（梯段不動／消防待核）", "stair", "", ""),
        "sliding-door": ("梯旁照護走道（原客餐門淨寬仍待改善）", "other", "C1-care-dry-hall", "circulation"),
        "sideyard": ("乾式照護前室／共享IDF壁龕（非機房）", "other", "C1-care-dry-hall", "circulation")}
    for key, (name, kind, group, role) in specs.items():
        cell = basis.interior._room(floor, key, cfg["zones_mm"][key], name=name, kind=kind, group=group, role=role, outdoor=False)
        f = cell["tour_features"]
        f.update(space_group=group, space_role=role, stairs=key == "stair1f")
        f.pop("allocation_review", None)
    cells = basis.interior._rooms(floor)
    affected = set(specs)|{"elder", "elder-bath"}
    affected_ids = {cells[k]["id"] for k in affected}
    for key, c in cells.items():
        for field in ("doors", "open_connections"):
            c["tour_features"][field] = [] if key in affected else [d for d in c["tour_features"][field] if d["neighbor"] not in affected_ids]
    connections = [c for c in floor["layout_review"]["connections"] if not affected.intersection(c[:2])]
    _pair(cells, "living-hall", "sliding-door", "rear", 1000, 3000, label="原100cm名義門（仍非全程900mm淨寬）")
    _pair(cells, "kitchen", "sliding-door", "right", 1130, 10450, "sliding", "廚房113cm名義拉門（原尺寸／備餐分時）")
    _pair(cells, "sliding-door", "sideyard", "rear", 1200, 3000, opened=True)
    _pair(cells, "sliding-door", "stair1f", "right", 1000, 9500, label="樓梯前平台入口（淨高／門組未核）")
    connections += [["living-hall", "sliding-door", 1000, 3000], ["kitchen", "sliding-door", {"width_mm": 1130, "operation": "sliding"}, 10450],
                    ["sliding-door", "sideyard", "open"], ["sliding-door", "stair1f", 1000, 9500]]
    for key, d in cfg["doors"].items():
        label = "孝親房120cm名義拉門（淨寬與救援未核）" if key == "bedroom" else "套衛120cm名義拉門（向後停放／未核）"
        _pair(cells, d["a"], d["b"], d["face"], d["nominal_mm"], d["center_mm"], d["operation"], label)
        connections.append([d["a"], d["b"], {"width_mm": d["nominal_mm"], "operation": d["operation"], "label": label}, d["center_mm"]])
        owner = cells[d["park_owner"]]["tour_features"]
        owner.setdefault("care_entry_leaves", []).append({"id": key, "state": state, "rect_mm": d[state+"_leaf_mm"],
            "height_mm": cfg["leaf_height_mm"], "status": "generic-leaf-envelope-not-selected-product", "counts_as_furniture": False})
    floor["layout_review"]["connections"] = connections
    basis._move(cells["elder"], "tv", cfg["tv_mm"], yaw=90, anchor="right")
    cx, cy, radius = cfg["bedroom_turn_circle_mm"]
    fixed = cells["elder"]["tour_features"]["fixed_reserved_mm"]
    fixed[:] = [r for r in fixed if r["kind"] != "care-turn"]
    fixed.append({"kind": "care-turn", "aabb": basis.interior._bounds([cx-radius, cy-radius, 2*radius, 2*radius]),
        "status": "1500mm-square-reserve-not-wheelchair-rehearsal"})
    cells["elder"]["tour_features"]["care_entry_turn_circle_mm"] = [cx, cy, radius]
    cells["elder"]["tour_features"]["basis_routes"] = [{"kind": k+"-900mm-local-body-not-wheelchair", "points_mm": v} for k, v in cfg["routes"].items()]
    for c in cells.values():
        f = c["tour_features"]
        f["reserved_mm"] = copy.deepcopy(f.get("fixed_reserved_mm", []))+[
            {"kind": "door-approach", "aabb": _door_approach(c["tour_mm"], d)} for d in f["doors"]]
        if f.get("stair_footprint_mm"):
            f["reserved_mm"].append({"kind": "stairs", "aabb": basis.interior._bounds([f["stair_footprint_mm"][k] for k in basis.interior.KEYS])})
    if any(cells["stair1f"]["tour_features"][k] != old["stair1f"]["tour_features"][k] for k in ("stair_footprint_mm", "stair_geometry")):
        raise ContractError("Care entry work must not relocate or resize any real stair flight")


def _ledger(options, root):
    # Reuse the current explicit C mappings, recompute every area from these
    # plans, then name the independent comparison scenarios. No old area credit.
    source = [{**o, "id": "c-care-refined"} for o in options]
    result = requirement_ledger(source, read_json(root / "inputs/requirements.json"),
        read_json(root / "inputs/requirement-dispositions.json"), sha256_file(root / "inputs/requirements.json"))
    for scenario, option in zip(result["scenarios"], options, strict=True):
        scenario["id"], scenario["label"] = option["id"], option["label"]
        if option["id"] == "c-entry-refined":
            for row in scenario["rows"]:
                if row["requirement_id"] == "C.floor-1.idf_c":
                    row.update(dedicated_service_area_credit_sqm=0, note="原壁龕及600×600mm代表機櫃保留；共享前室非獨立機房，不以6.12m²通行面積抵銷1m²／1.5m²機房需求。")
                if row["requirement_id"] == "C.floor-1.elder_bath":
                    row["note"] += " 本輪門改為滑門，但仍只由臥室進入，原照服員公共直達偏好尚未滿足；轉位／排氣未核。"
                if row["requirement_id"] in {"C.floor-1.elder", "C.floor-1.elder_bath"}:
                    row["flags"].append("upstream-care-route-bottleneck-still-unresolved")
                    row["whole_route_care_acceptance"] = "unknown-local-door-improvement-only"
    result["ledger_hash"] = stable_hash({k: v for k, v in result.items() if k != "ledger_hash"})
    return result


def build_study(root: Path = ROOT):
    cfg = read_json(root / SOURCE)
    validate_config(cfg)
    base_report = basis._verified_report(root, cfg["base_report"])
    raw = basis.interior.read_model(root / cfg["base_viewer"])["current_design_basis"]
    base = next(o for o in raw["options"] if o["id"] == cfg["base_option"])["states"][0]["model"]
    expected = next(o for o in base_report["options"] if o["id"] == cfg["base_option"])["states"][0]["plans"]
    actual = plan_data(base)["buildings"][0]
    for f, ref in zip(actual["floors"], expected["floors"], strict=True):
        f["plan_file"] = ref["plan_file"]
    if stable_hash(actual) != stable_hash(expected):
        raise ContractError("Base C plan/3D source mismatch; do not inherit its approval or geometry")
    original = base["buildings"][0]
    requirements = {r["id"]: r for r in read_json(root / "inputs/requirements.json")["requirements"]}
    if any(requirements[k]["constraints"]["door_clear_mm"] != 900 for k in ("C.floor-1.elder", "C.floor-1.elder_bath")):
        raise ContractError("Original care targets changed; explicit review is required")
    options = []
    for oid, label, states in (("c-entry-control", "C｜原入口控制案（淨寬不足保留）", ["daily"]),
                               ("c-entry-refined", "C｜梯旁走道＋前室120cm拉門提案", ["open", "closed"])):
        rows = []
        for state in states:
            model = copy.deepcopy(base)
            if oid == "c-entry-refined":
                refine(model, cfg, state)
            notes = cfg["limits"] if oid == "c-entry-refined" else ["保留目前C配置作控制案；兩道1000mm名義門在115mm假設下仍為770mm，低於原900mm目標。"]
            model["bc_option"] = {"id": oid, "label": label, "revision": 1, "use_state": state, "status": STATUS,
                "adopted": False, "tradeoffs": notes, "geometry_review": {}}
            model["source"] = {"c_care_entry": SOURCE, "geometry_basis": "source-bound-local-patch-not-full-regeneration"}
            model["layout_review"]["status"] = STATUS
            model["layout_review"]["checks"] = []
            plans = plan_data(model)["buildings"][0]
            screen = basis.interior._screen(model, cfg["insets_mm"], original)
            if screen["operation_vs_fixed_body"]:
                raise ContractError("Entry proposal must retain all full-size fixture operations")
            detail = review(plans, cfg, state, 900) if oid == "c-entry-refined" else {"original_door_clear_at_115mm": 770, "original_target_mm": 900, "professional_acceptance": "unknown"}
            screen.update(entry=detail)
            model["bc_option"]["geometry_review"] = screen
            for f in plans["floors"]:
                f["plan_file"] = oid+"_"+state+"_"+f["id"]+".svg"
            rows.append({"id": state, "label": {"daily": "原配置控制", "open": "兩門全開／局部試線", "closed": "兩門關閉／禁止穿越示意"}[state], "plans": plans, "model": model, "review": screen})
        options.append({"id": oid, "label": label, "building": "C", "adopted": False, "status": STATUS, "states": rows})
    paths = {SOURCE, cfg["base_report"], cfg["base_viewer"], "scripts/export_c_care_entry.py", "house_design/c_care_entry.py",
        "scripts/check_c_care_entry_playwright.cjs", BOOTSTRAP, OVERLAY, *base_report["source_hashes"]}
    ledger = _ledger(options, root)
    result = {"schema": SCHEMA, "revision": 1, "display_revision": 2, "generated_at": utc_now(), "status": STATUS,
        "adopted": False, "rendered_qa": "not-run", "frame_mm": cfg["frame_mm"], "default_option": cfg["default_option"],
        "default_state": "open", "professional_status": cfg["professional_status"], "limits": cfg["limits"], "options": options,
        "requirement_ledger": ledger, "base_report_hash": base_report["report_hash"], "browser_path": "Browser plugin not available; owner-run Windows Playwright only",
        "source_hashes": {p: sha256_file(root / p) for p in sorted(paths)}}
    result["report_hash"] = stable_hash({k: v for k, v in result.items() if k != "generated_at"})
    return result


def render_index(study):
    esc, sections = html.escape, []
    for o in study["options"]:
        states = []
        for s in o["states"]:
            link = 'c-care-entry-3d.html?scheme='+o["id"]+'&use='+s["id"]
            figures = ''.join('<figure><figcaption>'+esc(f["label"])+f' · <a href="c-care-entry/{f["plan_file"]}">同源SVG</a></figcaption><object type="image/svg+xml" data="c-care-entry/{f["plan_file"]}"></object></figure>' for f in s["plans"]["floors"])
            state_open = ' open' if o["id"] == study["default_option"] and s["id"] == 'open' else ''
            detail = s["review"]["entry"]
            summary = ('兩道名義1200mm門，115mm假設下各970mm；原900mm目標保留。關門狀態兩條試線均須被阻擋；前方大門／客餐門仍有770mm缺口，不能宣稱全程無障礙。'
                       if o["id"] == "c-entry-refined" else '原兩道1000mm名義門：115mm假設下770mm，仍差130mm；原方案保持不動。')
            if o["id"] == "c-entry-refined":
                summary += ' 本狀態局部試線缺口：'+str(sum(len(r["coordinate_failures"]) for r in detail["routes"].values()))+'（關門時有阻擋是預期，不是通行通過）。'
            states.append(f'<details id="{o["id"]}-{s["id"]}" data-use-state="{s["id"]}"{state_open}><summary>{esc(s["label"])}</summary><p>{esc(summary)}</p><a href="{link}">此狀態3D</a><figure><figcaption>照護局部放大（仍是概念／未採用）</figcaption><object class="detail" type="image/svg+xml" data="c-care-entry/{o["id"]}_{s["id"]}_detail.svg"></object></figure><details><summary>完整四層對照（上層不改）</summary>{figures}</details></details>')
        sections.append(f'<section id="{o["id"]}" data-option="{o["id"]}"><h2>{esc(o["label"])}</h2>'+''.join(states)+'</section>')
    limits = ''.join('<li>'+esc(n)+'</li>' for n in study["limits"])
    return ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>C孝親房入口｜原案與120cm拉門比較</title><style>body{font:16px/1.65 system-ui,sans-serif;max-width:1120px;margin:auto;padding:18px;background:#f8faf8;color:#24382e}a{color:#17634d}.warning{background:#fff1d6;padding:12px;color:#65430b}section{border-top:1px solid #cbd5ce;margin-top:24px}summary,a{min-height:44px}summary{cursor:pointer;padding:12px 0}figure{margin:12px 0;max-height:740px;overflow:auto;border:1px solid #cbd5ce}object{display:block;width:660px;max-width:none}.detail{width:780px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #cbd5ce;padding:8px;text-align:left}@media(max-width:640px){body{padding:12px}figure{max-height:600px}}</style><body><h1>C 孝親房入口比較</h1>'
        '<p id="care-adoption-warning" class="warning">比較方案，未採用／專業未核。保留原案，另排乾式前室與兩道120cm名義拉門；不是實測、輪椅演練或全程無障礙核可。</p>'
        '<p><a href="c-care-entry-3d.html">開啟新版3D（預設全開提案）</a> · <a href="current-design-basis.html">上輪五案討論包（不改）</a> · <a href="c-care-entry/requirement-ledger.json">本輪40列C需求對帳</a> · <a href="c-care-entry/review.json">座標／門框／來源證據</a></p>'
        '<h2>最小實體調整</h2><p>梯段、床、衣櫃、污衣籃、IDF機櫃、廚房、衛浴設備及上層全部保留。原梯廳重新分清樓梯本體、梯旁走道、乾式前室；孝親房入口改接前室並避床體正投影，電視移至右牆；套衛改拉門並向後停放。不是把1.2m牆段硬改成寬門。</p><ul>'+limits+'</ul>'+''.join(sections)+'</body></html>')


def write_study(study, root: Path = ROOT):
    directory = root / OUT
    directory.mkdir(parents=True, exist_ok=True)
    report = copy.deepcopy(study)
    for o in report["options"]:
        for s in o["states"]:
            s.pop("model")
    write_json(directory / "review.json", report)
    write_json(directory / "requirement-ledger.json", study["requirement_ledger"])
    for o in study["options"]:
        for s in o["states"]:
            url = f'../c-care-entry-3d.html?scheme={o["id"]}&use={s["id"]}'
            for f in s["plans"]["floors"]:
                svg = ET.fromstring(render_plan("C", f, viewer_url=url))
                svg.set("width", "660")
                svg.set("height", "1903")
                svg.set("data-care-option", o["id"])
                svg.set("data-use-state", s["id"])
                for r in f["rooms"]:
                    turn = r["features"].get("care_entry_turn_circle_mm")
                    if turn:
                        ET.SubElement(svg, "{http://www.w3.org/2000/svg}circle", {"cx": str(turn[0]), "cy": str(turn[1]), "r": str(turn[2]),
                            "fill": "none", "stroke": "#6d28d9", "stroke-width": "22", "stroke-dasharray": "80 60", "data-care-turn": "1500mm-reserve-not-wheelchair-rehearsal"})
                    for leaf in r["features"].get("care_entry_leaves", []):
                        x, y, w, d = leaf["rect_mm"]
                        ET.SubElement(svg, "{http://www.w3.org/2000/svg}rect", {"x": str(x), "y": str(y), "width": str(w), "height": str(d),
                            "fill": "#b45309", "fill-opacity": ".4", "stroke": "#b45309", "stroke-width": "18", "data-care-leaf-id": leaf["id"], "data-leaf-state": leaf["state"]})
                    for route in r["features"].get("basis_routes", []):
                        ET.SubElement(svg, "{http://www.w3.org/2000/svg}polyline", {"points": ' '.join(f'{x},{y}' for x, y in route["points_mm"]),
                            "fill": "none", "stroke": "#137d9c", "stroke-width": "24", "stroke-dasharray": "90 60", "data-care-route": route["kind"]})
                (directory / f["plan_file"]).write_text(ET.tostring(svg, encoding="unicode"), encoding="utf-8")
                if f["id"] == "floor-1":
                    svg.set("viewBox", "-250 8600 6500 9400")
                    svg.set("width", "780")
                    svg.set("height", "1128")
                    (directory / (o["id"]+'_'+s["id"]+'_detail.svg')).write_text(ET.tostring(svg, encoding="unicode"), encoding="utf-8")
    (root / INDEX).write_text(render_index(study), encoding="utf-8")
    cfg = read_json(root / SOURCE)
    text = (root / cfg["base_viewer"]).read_text()
    payload = {"c_care_entry": {"default_option": study["default_option"], "options": [
        {"id": o["id"], "label": o["label"], "building": "C", "states": [{k: s[k] for k in ("id", "label", "model")} for s in o["states"]]} for o in study["options"]]}}
    text, count = re.subn(r'^\s*var DATA = .+;\s*$', lambda _: '  var DATA = '+json.dumps(payload, ensure_ascii=False, separators=(',', ':'))+';', text, count=1, flags=re.M)
    if count != 1:
        raise ContractError("Missing unique source model payload")
    old = (root / basis.BOOTSTRAP).read_text()
    if text.count(old) != 1 or text.count('    var hvac=features.hvac || {};') != 1 or text.count('      currentDesignCamera:basisCameraEvidence(),') != 1:
        raise ContractError("Source viewer integration anchor changed; do not silently drop care rendering")
    text = text.replace(old, (root / BOOTSTRAP).read_text())
    text = text.replace('current-design-basis.html', 'c-care-entry.html').replace('ABC目前討論基準', 'C孝親房入口比較')
    text = text.replace('DATA.source.current_design_basis', 'DATA.source.c_care_entry')
    text = text.replace('    var hvac=features.hvac || {};', (root / OVERLAY).read_text()+'\n    var hvac=features.hvac || {};')
    text = text.replace('      currentDesignCamera:basisCameraEvidence(),', '      careEntry:careEntryEvidence(),\n      currentDesignCamera:basisCameraEvidence(),')
    # Function declaration inside this page only, never patch the shared/source viewer.
    evidence = '''  function careEntryEvidence(){
    return pickables.filter(function(m){return m.visible&&m.parent.visible&&m.userData.shell.visible;}).flatMap(function(m){
      return m.userData.shell.children.filter(function(p){return !!p.userData.careEntryLeaf;}).map(function(p){
        p.updateWorldMatrix(true,false);p.geometry.computeBoundingBox();
        var matrix=new THREE.Matrix4().copy(m.parent.matrixWorld).invert().multiply(p.matrixWorld);
        var b=p.geometry.boundingBox.clone().applyMatrix4(matrix);
        return {room:m.userData.cell.id,...p.userData.careEntryLeaf,actualBoundsMm:{minX:b.min.x/MM,maxX:b.max.x/MM,minY:-b.max.z/MM,maxY:-b.min.z/MM,minHeight:b.min.y/MM,maxHeight:b.max.y/MM}};
      });
    });
  }
'''
    if text.count('  window.__htmlModel3dDebug = function () {') != 1:
        raise ContractError("Missing actual-mesh debug evidence anchor")
    text = text.replace('  window.__htmlModel3dDebug = function () {', evidence+'\n  window.__htmlModel3dDebug = function () {')
    (root / VIEWER).write_text(text, encoding="utf-8")
    return {"index": INDEX, "viewer": VIEWER, "report": OUT+"/review.json", "rendered_qa": "not-run", "report_hash": study["report_hash"]}


def main():
    print(json.dumps(write_study(build_study()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

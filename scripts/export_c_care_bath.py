#!/usr/bin/env python3
"""Local care-bath snapshots only. Keep all verified parents immutable."""
from __future__ import annotations

import copy
import html
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import export_c_care_route as route
from lib.model3d_plan import plan_data, render_plan

from house_design.c_care_bath import SCHEMA, SOURCE, STATES, STATUS, component_box, components, review, validate_config
from house_design.c_care_route import review as route_review
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, utc_now, write_json
from house_design.current_design_basis import requirement_ledger

basis = route.basis
OUT = "structured/candidates/c-care-bath"
INDEX, VIEWER = OUT+".html", OUT+"-3d.html"
BOOTSTRAP, OVERLAY = "scripts/templates/c-care-bath-bootstrap.js", "scripts/templates/c-care-bath-overlay.js"
CAMERA = "scripts/templates/c-care-bath-camera.js"
CHECK = "scripts/check_c_care_bath_playwright.cjs"
LABELS = {"baseline": "上版固定隔間控制", "transfer": "折椅收起／扶手掀起：轉位試線",
          "shower": "折椅放下：不再計完整轉位地面", "rail-down": "扶手放下：轉位試線應被擋", "door-closed": "只關套衛門：各入浴試線應被擋"}


def refine(model, cfg, state):
    cells = basis.interior._rooms(model["buildings"][0]["floors"][0])
    bath = cells["elder-bath"]
    for key, raw in cfg["fixtures"].items():
        basis._move(bath, key, raw["rect_mm"], yaw=raw["rotation_deg"], anchor=raw["wall_anchor"])
    for i in bath["furniture"]:
        if i["shape"] == "shower":
            i.update(step_free=True, care_bath_open_shower=True, label="120cm零門檻開放淋浴候選（無固定玻璃）")
            i["note"] += " 原1200×1200外廓不縮；改用開放濕地面候選，不沿用原固定隔間的通行信用。"
        if i["shape"] == "vanity":
            i.update(care_bath_wall_hung=True, replacement_for_catalog_id=i["catalog_id"], catalog_id="wall-hung-vanity-60-study",
                     label="60cm壁掛洗手台候選（檯下膝部未核）")
            i["note"] += " 外廓600×450×850保留，取代一般落地櫃候選；商品、檯高、檯下及熱管隔熱未知，不計可鑽入膝部空間。"
    f = bath["tour_features"]
    f["care_bath_components"] = components(cfg, state)
    f["care_bath_vent_route_mm"] = cfg["vent_route_mm"]
    f["care_bath_state"] = state
    bath["name"] = "孝親套衛比較（無固定玻璃／濕地分時轉位）"
    f["care_entry_leaves"][0].update(state="closed" if state == "door-closed" else "open",
        rect_mm=[3715, 14195 if state == "door-closed" else 15425, 95, 1260])


def _annotate(model, cfg, detail):
    bath = basis.interior._rooms(model["buildings"][0]["floors"][0])["elder-bath"]
    f = bath["tour_features"]
    regions = [{"id": "turn-reserve", "rect_mm": cfg["turn_reserve_mm"], "blocked": bool(detail["turn_coordinate_failures"]), "kind": "1500x1800-shared-wet-floor-not-independent-dry-space"},
               {"id": "toilet-transfer", "rect_mm": cfg["toilet_transfer_mm"], "blocked": bool(detail["transfer_coordinate_failures"]), "kind": "900x1200-side-transfer-budget"},
               {"id": "toilet-helper", "rect_mm": cfg["toilet_helper_mm"], "blocked": False, "kind": "600x600-single-helper-budget"},
               {"id": "shower-helper", "rect_mm": cfg["shower_helper_mm"], "blocked": False, "kind": "600x600-single-helper-budget"},
               {"id": "rigid-board-turn", "rect_mm": detail["rescue_board_rotation_mm"], "blocked": bool(detail["rescue_board_rotation_failures"]), "kind": "600x1800-rigid-board-all-angle-square-not-rescue-approval"}]
    # Centre lines and outlines remain explanatory, not additional room area.
    f["care_bath_regions"] = regions
    f["care_bath_circle_mm"] = cfg["turn_circle_mm"]
    f["care_route_overlays"] = [{"id": "bath-"+k, "kind": "900mm-body-centerline-only-not-wheelchair", "points_mm": r["points_mm"], "blocked": bool(r["coordinate_failures"])} for k, r in detail["routes"].items()]
    for r in regions:
        x, y, w, d = r["rect_mm"]
        f["care_route_overlays"].append({"id": r["id"], "kind": r["kind"], "blocked": r["blocked"], "points_mm": [[x, y], [x+w, y], [x+w, y+d], [x, y+d], [x, y]]})


def _ledger(options, root):
    ledger = requirement_ledger([{**o, "id": "c-care-refined"} for o in options], read_json(root / "inputs/requirements.json"),
        read_json(root / "inputs/requirement-dispositions.json"), sha256_file(root / "inputs/requirements.json"))
    for scenario, option in zip(ledger["scenarios"], options, strict=True):
        scenario["id"], scenario["label"] = option["id"], option["label"]
        for row in scenario["rows"]:
            if row["requirement_id"] == "C.floor-1.idf_c":
                row.update(dedicated_service_area_credit_sqm=0, note="原壁龕保留，共享前室非獨立機房，不給專用機房面積信用。")
            if row["requirement_id"] == "C.floor-1.elder_bath":
                row["note"] += " 原公共直達照服偏好未滿足；本輪改濕地分時轉位，不表示採用或照護／救援已核。"
                row["flags"] += ["private-bedroom-caregiver-access-unresolved", "shared-wet-turning-floor-not-independent-dry-clearance"]
                row["whole_route_care_acceptance"] = "unknown"
    ledger["ledger_hash"] = stable_hash({k: v for k, v in ledger.items() if k != "ledger_hash"})
    return ledger


def build_study(root: Path = ROOT):
    cfg = read_json(root / SOURCE)
    validate_config(cfg)
    parent = basis._verified_report(root, cfg["base_report"])
    payload = basis.interior.read_model(root / cfg["base_viewer"])["c_care_route"]
    base = next(s["model"] for o in payload["options"] if o["id"] == cfg["base_option"] for s in o["states"] if s["id"] == cfg["base_state"])
    expected = next(s["plans"] for o in parent["options"] if o["id"] == cfg["base_option"] for s in o["states"] if s["id"] == cfg["base_state"])
    actual = plan_data(base)["buildings"][0]
    for f, ref in zip(actual["floors"], expected["floors"], strict=True):
        f["plan_file"] = ref["plan_file"]
    if actual != expected:
        raise ContractError("Care-route parent plan/viewer mismatch")
    pcfg = read_json(root / "inputs/c-care-entry.json")
    rcfg = read_json(root / "inputs/c-care-route.json")
    targets = {r["id"]: r for r in read_json(root / "inputs/requirements.json")["requirements"]}
    if any(targets[k]["constraints"]["door_clear_mm"] != 900 for k in ("C.floor-1.elder", "C.floor-1.elder_bath")):
        raise ContractError("Keep original 900mm care targets")
    options = []
    for oid, label, states in (("c-bath-control", "C｜已驗收上版套衛控制（固定隔間未解）", ["baseline"]),
                               ("c-bath-refined", "C｜原外框開放淋浴／折椅／扶手比較", STATES)):
        rows = []
        for state in states:
            model = copy.deepcopy(base)
            refined = oid == "c-bath-refined"
            if refined:
                refine(model, cfg, state)
            model["source"] = {"c_care_bath": SOURCE, "geometry_basis": "verified-parent-local-bath-snapshot-no-full-build"}
            model["bc_option"] = {"id": oid, "label": label, "revision": 1, "use_state": state, "status": STATUS, "adopted": False,
                "tradeoffs": cfg["limits"], "geometry_review": {}}
            model["layout_review"].update(status=STATUS, checks=[])
            plans = plan_data(model)["buildings"][0]
            detail = review(plans, cfg, state, refined=refined)
            upstream = route_review(plans, rcfg, "bath-closed" if state == "door-closed" else "open", pcfg, refined=True)
            if refined:
                _annotate(model, cfg, detail)
                plans = plan_data(model)["buildings"][0]
            screen = basis.interior._screen(model, cfg["insets_mm"], base["buildings"][0])
            if screen["operation_vs_fixed_body"]:
                raise ContractError("Do not lose original 700mm fixture operations to pass")
            screen.update(bath=detail, route=upstream)
            model["bc_option"]["geometry_review"] = screen
            for f in plans["floors"]:
                f["plan_file"] = oid+"_"+state+"_"+f["id"]+".svg"
            rows.append({"id": state, "label": LABELS[state], "plans": plans, "model": model, "review": screen})
        options.append({"id": oid, "label": label, "building": "C", "status": STATUS, "adopted": False, "states": rows})
    paths = {SOURCE, cfg["base_report"], cfg["base_viewer"], "house_design/c_care_bath.py", "scripts/export_c_care_bath.py", CHECK, BOOTSTRAP, OVERLAY, CAMERA, *parent["source_hashes"]}
    result = {"schema": SCHEMA, "revision": 1, "display_revision": 2, "generated_at": utc_now(), "status": STATUS, "adopted": False,
        "bath_display_revision": 2,
        "rendered_qa": "not-run", "frame_mm": cfg["frame_mm"], "default_option": cfg["default_option"], "default_state": "transfer",
        "professional_status": cfg["professional_status"], "limits": cfg["limits"], "options": options, "requirement_ledger": _ledger(options, root),
        "base_report_hash": parent["report_hash"], "browser_path": "Browser plugin not available; owner-run Windows Playwright only",
        "source_hashes": {p: sha256_file(root / p) for p in sorted(paths)}}
    result["report_hash"] = stable_hash({k: v for k, v in result.items() if k != "generated_at"})
    return result


def render_index(study):
    esc, sections = html.escape, []
    for o in study["options"]:
        states = []
        for s in o["states"]:
            oid, sid, detail = o["id"], s["id"], s["review"]["bath"]
            opened = ' open' if oid == study["default_option"] and sid == 'transfer' else ''
            summary = ('完整轉位預留有阻擋' if detail["turn_coordinate_failures"] else '指定完整轉位預留無座標衝突')+'；'+('馬桶側移預留有阻擋' if detail["transfer_coordinate_failures"] else '指定馬桶側移預留無座標衝突')
            equipment = ''.join('<li>'+esc(c["label"])+" · "+esc(c["state"])+"；未選產品／錨定未核</li>" for r in s["plans"]["floors"][0]["rooms"] for c in r["features"].get("care_bath_components", []))
            all_floors = ''.join(f'<figure><figcaption>{esc(f["label"])}</figcaption><object type="image/svg+xml" data="c-care-bath/{f["plan_file"]}"></object></figure>' for f in s["plans"]["floors"])
            states.append(f'<details id="{oid}-{sid}" data-use-state="{sid}"{opened}><summary>{esc(s["label"])}</summary><p>{esc(summary)}。不同狀態不能相加；關門及扶手放下是反例。</p><a href="c-care-bath-3d.html?scheme={oid}&amp;use={sid}#mode=tour&amp;building=C&amp;floor=floor-1&amp;room=C%3Afloor-1%3Aelder-bath&amp;focus=room&amp;view=plan">此狀態套衛3D特寫</a><figure><figcaption>套衛放大：紫＝轉位、青＝指定試線、紅＝受阻、橙＝剛性示意板全轉向；不是照護或救援核可</figcaption><object class="detail" type="image/svg+xml" data="c-care-bath/{oid}_{sid}_detail.svg"></object></figure><details><summary>扶手／折椅／機電候選清單（非已購實物）</summary><ul>{equipment}</ul></details><details><summary>完整四層對照（其餘分區不動）</summary>{all_floors}</details></details>')
        sections.append(f'<section data-option="{o["id"]}"><h2>{esc(o["label"])}</h2>'+''.join(states)+'</section>')
    return ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>C孝親套衛｜轉位與照護狀態比較</title>'
        '<style>body{font:16px/1.65 system-ui,sans-serif;max-width:1120px;margin:auto;padding:18px;background:#f8faf8;color:#24382e}a{color:#17634d}.warning{background:#fff1d6;padding:12px;color:#65430b}section{border-top:1px solid #cbd5ce;margin-top:24px}summary{cursor:pointer;padding:12px 0;min-height:44px}figure{margin:12px 0;max-height:740px;overflow:auto;border:1px solid #cbd5ce}object{display:block;width:660px;max-width:none}.detail{width:780px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #cbd5ce;padding:8px;text-align:left}@media(max-width:640px){body{padding:12px}figure{max-height:600px}}</style><body><h1>C 孝親套衛照護比較</h1>'
        '<p id="bath-adoption-warning" class="warning">比較方案，未採用／專業未核。濕地分時轉位，不是獨立乾區、真人照護、救援或法規核可。</p>'
        '<p><a href="c-care-bath-3d.html">新版套衛3D</a> · <a href="c-care-route.html">已驗收動線版（不動）</a> · <a href="c-care-bath/requirement-ledger.json">40列C需求對帳</a> · <a href="c-care-bath/review.json">座標及來源證據</a></p>'
        '<h2>不擴房間的建議</h2><p>保留2.4×3m套衛外框、600mm高窗、後側830mm戶外通風帶、原床及上層。馬桶改靠前牆，600mm洗手台改前左壁掛候選，120cm淋浴改後右零門檻開放濕地。三件原外廓及700mm操作不縮；壁掛洗手台是替代產品候選，檯下空間未核，不計膝部通行信用。</p>'
        '<p class="warning">仍是緊餘量研究：入口試線距洗手台約10mm、側移預留距洗手台15mm，剛性板轉向距收起折椅8.5mm；完成面、把手、商品及施工公差未核，不能當作可施工定案。</p>'
        '<table><tr><th>狀態</th><th>完整轉位預留</th><th>馬桶指定入位</th><th>剛性示意板轉向</th></tr><tr><td>折椅收起／扶手掀起</td><td>借淋浴地面</td><td>指定矩形試線</td><td>僅600×1800板的保守幾何</td></tr><tr><td>折椅放下</td><td>受阻，不能仍計轉位</td><td>不等於淋浴與如廁可同時照護</td><td>受阻</td></tr><tr><td>扶手放下</td><td>不是同時轉位的保證</td><td>受阻，須先處理扶手</td><td>非真人救援</td></tr><tr><td>浴室門關閉</td><td>室內地面不等於可進入</td><td>門片阻擋</td><td>門片阻擋</td></tr></table>'
        '<p>仍須穿孝親房進套衛，公共直達照服偏好未滿足。原150×180cm預留與900mm目標保留；一般折椅480×450、扶手650mm只是候選尺寸，不是商品、承重或職能治療處方。</p><ul>'+''.join('<li>'+esc(v)+'</li>' for v in study["limits"])+'</ul>'+''.join(sections)+'</body></html>')


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
            for f in s["plans"]["floors"]:
                svg = ET.fromstring(render_plan("C", f, viewer_url=f'../c-care-bath-3d.html?scheme={o["id"]}&use={s["id"]}'))
                svg.set("width", "660")
                svg.set("height", "1903")
                svg.set("data-bath-option", o["id"])
                svg.set("data-use-state", s["id"])
                if f["id"] == "floor-1":
                    for r in f["rooms"]:
                        for leaf in r["features"].get("care_entry_leaves", []):
                            x, y, w, d = leaf["rect_mm"]
                            ET.SubElement(svg, ns+"rect", {"x": str(x), "y": str(y), "width": str(w), "height": str(d), "fill": "#b45309", "fill-opacity": ".4", "data-care-leaf-id": leaf["id"], "data-leaf-state": leaf["state"]})
                        for c in r["features"].get("care_bath_components", []):
                            x, y, w, d, _, _ = component_box(c)
                            ET.SubElement(svg, ns+"rect", {"x": str(x), "y": str(y), "width": str(w), "height": str(d), "fill": "#475569", "fill-opacity": ".55", "data-bath-component": c["id"], "data-component-state": c["state"]})
                        for spec in r["features"].get("care_route_overlays", []):
                            color = "#b43b25" if spec["blocked"] else "#b45309" if spec["id"] == "rigid-board-turn" or spec["kind"] == "sweep" else "#6d28d9" if spec["id"] == "turn-reserve" else "#137d9c"
                            ET.SubElement(svg, ns+"polyline", {"points": ' '.join(f'{x},{y}' for x, y in spec["points_mm"]), "fill": "none", "stroke": color, "stroke-width": "18", "stroke-dasharray": "80 60", "data-care-route": spec["id"]})
                        circle = r["features"].get("care_bath_circle_mm")
                        if circle:
                            ET.SubElement(svg, ns+"circle", {"cx": str(circle[0]), "cy": str(circle[1]), "r": str(circle[2]), "fill": "none", "stroke": "#b43b25" if s["id"] == "shower" else "#6d28d9", "stroke-width": "18", "stroke-dasharray": "80 60", "data-bath-turn": "shared-wet-floor-not-approved"})
                        vent = r["features"].get("care_bath_vent_route_mm")
                        if vent:
                            ET.SubElement(svg, ns+"polyline", {"points": ' '.join(f'{x},{y}' for x, y, _ in vent), "fill": "none", "stroke": "#b45309", "stroke-width": "18", "stroke-dasharray": "80 60", "data-bath-vent": "high-level-exhaust-candidate-not-pipe-or-airflow-design"})
                    (directory / f["plan_file"]).write_text(ET.tostring(svg, encoding="unicode"), encoding="utf-8")
                    svg.set("viewBox", "2350 13400 3900 4050")
                    svg.set("width", "780")
                    svg.set("height", "810")
                    (directory / (o["id"]+'_'+s["id"]+'_detail.svg')).write_text(ET.tostring(svg, encoding="unicode"), encoding="utf-8")
                else:
                    (directory / f["plan_file"]).write_text(ET.tostring(svg, encoding="unicode"), encoding="utf-8")
    (root / INDEX).write_text(render_index(study), encoding="utf-8")
    cfg = read_json(root / SOURCE)
    text = (root / cfg["base_viewer"]).read_text()
    payload = {"c_care_bath": {"default_option": study["default_option"], "options": [
        {"id": o["id"], "label": o["label"], "building": "C", "states": [{k: s[k] for k in ("id", "label", "model")} for s in o["states"]]} for o in study["options"]]}}
    text, count = re.subn(r'^\s*var DATA = .+;\s*$', lambda _: '  var DATA = '+json.dumps(payload, ensure_ascii=False, separators=(',', ':'))+';', text, count=1, flags=re.M)
    old = (root / route.BOOTSTRAP).read_text()
    if count != 1 or text.count(old) != 1 or text.count('DATA.source.c_care_route') != 2:
        raise ContractError("Verified viewer/bootstrap anchors changed")
    text = text.replace(old, (root / BOOTSTRAP).read_text()).replace('DATA.source.c_care_route', 'DATA.source.c_care_bath')
    text = text.replace('c-care-route.html', 'c-care-bath.html').replace('C騎樓至照護動線比較', 'C孝親套衛照護比較')
    color_anchor = 'color:spec.kind==="sweep"?0xb45309:spec.blocked?0xb43b25:0x137d9c'
    if text.count(color_anchor) != 1:
        raise ContractError("Missing local region-color legend anchor")
    text = text.replace(color_anchor, 'color:spec.blocked?0xb43b25:spec.kind==="sweep"||spec.id==="rigid-board-turn"?0xb45309:spec.id==="turn-reserve"?0x6d28d9:0x137d9c')
    anchor = '    var hvac=features.hvac || {};'
    if text.count(anchor) != 1 or text.count('      careEntry:careEntryEvidence(),') != 1:
        raise ContractError("Missing local bath mesh/evidence anchor")
    text = text.replace(anchor, (root / OVERLAY).read_text()+'\n'+anchor)
    text = text.replace('      careEntry:careEntryEvidence(),', '      careBath:careBathEvidence(),\n      careEntry:careEntryEvidence(),')
    evidence = '''  function careBathEvidence(){
    return pickables.filter(function(m){return m.visible&&m.parent.visible&&m.userData.shell.visible;}).flatMap(function(m){
      return m.userData.shell.children.filter(function(p){return !!p.userData.careBath;}).map(function(p){
        p.updateWorldMatrix(true,true);
        var matrix=new THREE.Matrix4().copy(m.parent.matrixWorld).invert(),box=new THREE.Box3();
        p.traverse(function(c){if(!c.geometry){return;}c.geometry.computeBoundingBox();var transform=new THREE.Matrix4().copy(matrix).multiply(c.matrixWorld);box.union(c.geometry.boundingBox.clone().applyMatrix4(transform));});
        return {room:m.userData.cell.id,...p.userData.careBath,actualBoundsMm:{minX:box.min.x/MM,maxX:box.max.x/MM,minY:-box.max.z/MM,maxY:-box.min.z/MM,minHeight:box.min.y/MM,maxHeight:box.max.y/MM}};
      });
    });
  }
'''
    text = text.replace('  window.__htmlModel3dDebug = function () {', evidence+'\n  window.__htmlModel3dDebug = function () {')
    # Local product visualization only: no edits to the verified shared renderer.
    vanity_anchor = '    if (shape === "vanity") {\n      return ['
    shower_anchor = '    if (shape === "shower") {\n      if (item.step_free) {'
    if text.count(vanity_anchor) != 1 or text.count(shower_anchor) != 1:
        raise ContractError("Missing unique generic fixture renderer anchors")
    text = text.replace(vanity_anchor, '    if (shape === "vanity" && item.care_bath_wall_hung) {\n      return [{x:0,z:0,w:1,d:1,h:70/item.height_mm,bottom:780/item.height_mm,color:0xf1f5f9},{x:0,z:-.4,w:.8,d:.1,h:100/item.height_mm,bottom:680/item.height_mm,color:0x94a3b8}];\n    }\n'+vanity_anchor)
    text = text.replace(shower_anchor, '    if (shape === "shower" && item.care_bath_open_shower) {\n      return [{x:0,z:0,w:1,d:1,h:.001,bottom:0,opacity:.35}];\n    }\n'+shower_anchor)
    camera_anchor = '  function basisMobileCloseup() {'
    fit_anchor = 'readable=basisChooseRoomFrame(box,area,width,height,camera.fov,bodies,frame);'
    title_anchor = '    syncRoomViewActions();\n    var building=buildingRecord(viewState.building), review=building && building.layout_review;'
    metadata_anchor = 'bodyScore:readable?readable.score:null,baselineBodyScore:readable?readable.baselineScore:null};'
    if any(text.count(anchor) != 1 for anchor in (camera_anchor, fit_anchor, title_anchor, metadata_anchor)):
        raise ContractError("Missing unique local mobile-bath camera anchors")
    text = text.replace(camera_anchor, (root / CAMERA).read_text()+'\n'+camera_anchor)
    text = text.replace(fit_anchor, 'readable=bathChooseRoomFrame(box,area,width,height,camera.fov,bodies,frame);')
    text = text.replace(title_anchor, '    bathSyncRoomTitle(mesh,name);\n'+title_anchor)
    text = text.replace(metadata_anchor, 'bodyScore:readable?readable.score:null,baselineBodyScore:readable?readable.baselineScore:null,bathDisplayRevision:2,bodyProjectionBasis:"actual-mesh-bounds-not-nominal-empty-envelope"};')
    (root / VIEWER).write_text(text, encoding="utf-8")
    return {"index": INDEX, "viewer": VIEWER, "report": OUT+"/review.json", "rendered_qa": "not-run", "report_hash": study["report_hash"]}


def main():
    print(json.dumps(write_study(build_study()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

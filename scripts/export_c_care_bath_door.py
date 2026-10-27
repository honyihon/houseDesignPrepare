#!/usr/bin/env python3
"""Local door comparison only, no scene, solver or changes to verified parents."""
from __future__ import annotations

import argparse
import copy
import html
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for local_dir in (PROJECT_ROOT, Path(__file__).resolve().parent):
    if str(local_dir) not in sys.path:
        sys.path.insert(0, str(local_dir))

from lib.model3d_plan import plan_data, render_plan  # noqa: E402

from house_design.c_care_bath import component_box  # noqa: E402
from house_design.c_care_bath_door import (  # noqa: E402
    OPTIONS,
    SCHEMA,
    SOURCE,
    STATES,
    _regions,
    pose,
    review,
    validate_config,
)
from house_design.c_care_bath_fit import BASE_REPORT, BASE_VIEWER, STATUS, _frozen_parent  # noqa: E402
from house_design.contracts import (  # noqa: E402
    ROOT,
    ContractError,
    read_json,
    sha256_file,
    stable_hash,
    utc_now,
    write_json,
)

OUT = "structured/candidates/c-care-bath-door"
INDEX, VIEWER = OUT+".html", OUT+"-3d.html"
OVERLAY = "scripts/templates/c-care-bath-door-overlay.js"
DISPLAY = "scripts/templates/c-care-bath-door-display.js"
CHECK = "scripts/check_c_care_bath_door_playwright.cjs"
LABELS = {"single-control": "C｜原單片拉門控制（盆體／止擋衝突保留）", "two-panel": "C｜門洞後移20cm＋兩片共同後收疊比較"}
STATE_LABELS = {"open": "全開：先核停放與轉位", "half": "半開：不可通行反例", "closed": "全關：不可通行反例"}


def _patch(model, cfg, bath_cfg, option, state):
    cells = {c["key"]: c for c in model["buildings"][0]["floors"][0]["cells"] if c["tour_active"]}
    bath, elder = cells["elder-bath"], cells["elder"]
    leaves, parts = pose(cfg, option, state)
    features = bath["tour_features"]
    features["care_entry_leaves"], features["care_door_parts"] = leaves, parts
    if option == "two-panel":
        for room, other in ((bath, elder), (elder, bath)):
            door = next(d for d in room["tour_features"]["doors"] if d["neighbor"] == other["id"])
            door["ratio"] = (cfg["center_y_mm"]-room["tour_mm"]["y_mm"])/room["tour_mm"]["h_mm"]
            door["label"] = "120cm名義兩片連動後收疊（門組未選／後移20cm比較）"
            for reserve in room["tour_features"].get("reserved_mm", []):
                if reserve["kind"] == "door-approach" and room is bath:
                    reserve["aabb"]["minY"] += 200
                    reserve["aabb"]["maxY"] += 200
    reserve, circle, _, _ = _regions(cfg, bath_cfg, option)
    features["care_bath_circle_mm"] = circle
    features["care_bath_regions"] = [{"id": "turn-reserve", "rect_mm": reserve}]
    model["source"] = {"c_care_bath_door": SOURCE, "geometry_basis": "frozen-bath-local-door-snapshot-not-full-build"}


def _annotate(model, detail):
    cells = {c["key"]: c for c in model["buildings"][0]["floors"][0]["cells"] if c["tour_active"]}
    f = cells["elder-bath"]["tour_features"]
    f["care_bath_regions"] = [
        {"id": "turn-reserve", "rect_mm": detail["turn_reserve_mm"], "blocked": bool(detail["turn_coordinate_failures"]), "kind": "shared-wet-floor-not-independent-dry-clearance"},
        {"id": "toilet-transfer", "rect_mm": detail["toilet_transfer_mm"], "blocked": bool(detail["transfer_coordinate_failures"]), "kind": "side-transfer-budget"},
        {"id": "rigid-board-turn", "rect_mm": detail["rescue_board_rotation_mm"], "blocked": bool(detail["rescue_board_rotation_failures"]), "kind": "rigid-board-not-rescue-approval"}]
    f["care_bath_regions"] += [{"id": key, "rect_mm": area, "blocked": False, "kind": "single-stationary-helper-budget-not-full-lift"} for key, area in detail["helper_stations_mm"].items()]
    f["care_route_overlays"] = [{"id": "bath-"+key, "kind": "900mm-body-centerline-only-not-wheelchair", "points_mm": r["points_mm"], "blocked": bool(r["coordinate_failures"])} for key, r in detail["routes"].items()]
    for region in f["care_bath_regions"]:
        x, y, w, d = region["rect_mm"]
        f["care_route_overlays"].append({**region, "points_mm": [[x, y], [x+w, y], [x+w, y+d], [x, y+d], [x, y]]})
    # Regenerate the existing upstream overlay, not a stale parent's green line.
    overlays = cells["dining"]["tour_features"]["care_route_overlays"]
    for overlay in overlays:
        if overlay["id"] in detail["upstream_routes"]:
            route = detail["upstream_routes"][overlay["id"]]
            overlay.update(points_mm=route["points_mm"], blocked=bool(route["coordinate_failures"]))


def build_study(root: Path = ROOT):
    cfg = read_json(root / SOURCE)
    validate_config(cfg)
    parent, reference = _frozen_parent(root)
    bath_cfg, route_cfg = read_json(root / "inputs/c-care-bath.json"), read_json(root / "inputs/c-care-route.json")
    text = (root / BASE_VIEWER).read_text(encoding="utf-8")
    payload = json.loads(re.search(r"^\s*var DATA = (.+);\s*$", text, re.M)[1])["c_care_bath"]
    base = next(s["model"] for o in payload["options"] if o["id"] == "c-bath-refined" for s in o["states"] if s["id"] == "transfer")
    options = []
    for oid in OPTIONS:
        states = []
        for state in STATES:
            model = copy.deepcopy(base)
            _patch(model, cfg, bath_cfg, oid, state)
            detail = review(plan_data(model)["buildings"][0], cfg, bath_cfg, route_cfg, oid, state)
            _annotate(model, detail)
            model["bc_option"] = {"id": oid, "label": LABELS[oid], "revision": 1, "use_state": state,
                                  "status": STATUS, "adopted": False, "tradeoffs": cfg["limits"], "geometry_review": {"door": detail}}
            plans = plan_data(model)["buildings"][0]
            for floor in plans["floors"]:
                floor["plan_file"] = oid+"_"+state+"_"+floor["id"]+".svg"
            states.append({"id": state, "label": STATE_LABELS[state], "model": model, "plans": plans, "review": {"door": detail}})
        options.append({"id": oid, "building": "C", "label": LABELS[oid], "adopted": False, "status": STATUS, "states": states})
    ledger = copy.deepcopy(parent["requirement_ledger"])
    for scenario, option in zip(ledger["scenarios"], options, strict=True):
        template = copy.deepcopy(parent["requirement_ledger"]["scenarios"][1])
        scenario.clear()
        scenario.update(template, id=option["id"], label=option["label"])
        for row in scenario["rows"]:
            if row["requirement_id"] == "C.floor-1.elder_bath":
                row["note"] += " 門組獨立比較未採用：單片閉門碰盆／止擋不足；兩片門洞後移200mm、移轉位標示，商品與救援仍未知。"
                row["flags"] += ["bath-door-product-and-care-unknown"]
    ledger["ledger_hash"] = stable_hash({k: v for k, v in ledger.items() if k != "ledger_hash"})
    paths = {SOURCE, BASE_REPORT, BASE_VIEWER, "house_design/c_care_bath_fit.py", "house_design/c_care_bath_door.py",
             "scripts/export_c_care_bath_door.py", OVERLAY, DISPLAY, CHECK, *parent["source_hashes"]}
    result = {"schema": SCHEMA, "revision": 1, "display_revision": 2, "bath_display_revision": 2,
        "door_display_revision": 2,
        "generated_at": utc_now(), "status": STATUS, "adopted": False, "rendered_qa": "not-run",
        "default_option": cfg["default_option"], "default_state": "open", "frame_mm": cfg["frame_mm"],
        "limits": cfg["limits"], "professional_status": cfg["professional_status"], "options": options,
        "base_plan_hash": stable_hash(reference["plans"]), "base_report_hash": parent["report_hash"],
        "requirement_ledger": ledger, "source_hashes": {p: sha256_file(root / p) for p in sorted(paths)}}
    result["report_hash"] = stable_hash({k: v for k, v in result.items() if k != "generated_at"})
    return result


def render_index(study):
    esc, sections, rows = html.escape, [], []
    for option in study["options"]:
        states = []
        for state in option["states"]:
            oid, sid, d = option["id"], state["id"], state["review"]["door"]
            rows.append(f'<tr><th scope="row">{esc(option["label"])}／{esc(state["label"])}</th><td>{d["effective_width_assumption_mm"]:g}mm</td><td>{d["rear_parking_after_20mm_stop_mm"]:g}mm</td><td>'+('有：洗手台' if d["sweep_vs_fixed_conflicts"] else '指定外廓無衝突；商品未知')+'</td></tr>')
            link = f'c-care-bath-door-3d.html?scheme={oid}&amp;use={sid}#mode=tour&amp;building=C&amp;floor=floor-1&amp;room=C%3Afloor-1%3Aelder-bath&amp;focus=room&amp;view=plan'
            complete = ''.join(f'<figure><figcaption>{esc(f["label"])}（其餘分區／設備不搬）</figcaption><object type="image/svg+xml" data="c-care-bath-door/{f["plan_file"]}" width="660" height="1903"></object></figure>' for f in state["plans"]["floors"])
            states.append(f'<details id="{oid}-{sid}" data-use-state="{sid}"'+(' open' if oid == 'two-panel' and sid == 'open' else '')+f'><summary>{esc(state["label"])}</summary><p><a href="{link}">對應3D特寫</a></p><figure><object type="image/svg+xml" data="c-care-bath-door/{oid}_{sid}_detail.svg" width="780" height="810"><a href="c-care-bath-door/{oid}_{sid}_detail.svg">套衛放大圖</a></object></figure><details><summary>完整四層對照</summary>{complete}</details></details>')
        sections.append(f'<section data-option="{option["id"]}"><h2>{esc(option["label"])}</h2>'+''.join(states)+'</section>')
    return ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>C套衛門組｜單片與兩片後收疊比較</title><style>body{font:16px/1.65 system-ui,sans-serif;max-width:1120px;margin:auto;padding:18px;background:#f8faf8;color:#24382e}a{color:#17634d}.warning{background:#fff1d6;padding:12px;color:#65430b}section{border-top:1px solid #cbd5ce;margin-top:24px}summary{cursor:pointer;padding:12px 0;min-height:44px}figure{margin:12px 0;overflow:auto;max-height:740px;border:1px solid #cbd5ce}object{display:block;max-width:none}table{border-collapse:collapse;width:100%}th,td{border:1px solid #cbd5ce;padding:8px;text-align:left}.scroll{overflow:auto}.matrix{min-width:750px}@media(max-width:640px){body{padding:12px}figure{max-height:600px}}</style><body>'
        '<h1>C 套衛門組比較</h1><p id="door-adoption-warning" class="warning">比較方案，未採用／專業未核。門片與轉位只作指定幾何研究，不是商品、照護、救援或施工核可。</p>'
        '<p><a href="c-care-bath-door-3d.html">新門組3D</a> · <a href="c-care-bath-fit.html">原公差檢核</a> · <a href="c-care-bath.html">保留父版</a> · <a href="c-care-bath-door/review.json">同源座標及限制</a> · <a href="c-care-bath-door/requirement-ledger.json">40列C需求對帳</a></p>'
        '<h2>建議：門洞後移20cm，兩片共同向後收疊</h2><p>不動房間外框、隔間位置或三件設備。門洞仍1200mm名義寬，扣框假設970mm，原900mm目標不降。'
        '兩片各660mm長、搭接60mm，關閉覆蓋1260mm；每片45mm厚、軌道間15mm及把手25mm，總厚暫估130mm，不是選好的產品。</p>'
        '<p class="warning">原單片全行程會與盆體重疊，門後另加20mm止擋也超出假設完成面。兩片若沿用原轉位位置同樣會侵入；新比較把1500×1800mm預留與1500mm圓右移70mm，剛性板試線右移50mm，不是把門片變薄或把轉位縮小。</p>'
        '<p>新案指定門片全行程距盆體30mm，停門含20mm止擋後餘350mm；全開仍只是假設970mm。半開約485mm，不能通行。拉門要先全開再進出，軌道補強、夾傷保護、濕區耐用及外解鎖／外拆卸待產品圖確認。</p>'
        '<p>若只把原單片門洞也後移20cm，含止擋的停放餘量反而是−220mm，並不能只移門位解決。兩片模型暫按主動片1260mm／從動片630mm的2:1連動行程比較；實際同步機構、搭接與關閉密合另核。</p>'
        '<p>總厚130mm時到新轉位預留仍僅35mm；總厚165mm即零餘量，180mm會侵入15mm。因此只推薦作選品與深化方向，不是可任選兩片門。原洗手台最後到位點0mm、馬桶側移旁15mm及剛性板到折椅8.5mm仍未解，轉位仍借淋浴濕地。</p>'
        '<figure><figcaption>門片軌道局部剖示意：數值為假設，不是施工剖面</figcaption><object type="image/svg+xml" data="c-care-bath-door/track-section.svg" width="840" height="320"><a href="c-care-bath-door/track-section.svg">查看總厚度與轉位餘量</a></object></figure>'
        '<div class="scroll" tabindex="0" role="region" aria-label="門組狀態比較可左右捲動"><table class="matrix"><thead><tr><th scope="col">方案／狀態</th><th scope="col">假設可用開口</th><th scope="col">門後扣20mm止擋餘量</th><th scope="col">完整行程碰固定物</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
        '<ul>'+''.join('<li>'+esc(v)+'</li>' for v in study["limits"])+'</ul>'+''.join(sections)+
        '<p>新包 rendered_qa=not-run；舊passed不能覆蓋新門組。四層與需求保留，瀏覽器／WebGL由屋主另外驗收。</p></body></html>')


def _svg(floor, option, state):
    ns = "{http://www.w3.org/2000/svg}"
    svg = ET.fromstring(render_plan("C", floor, viewer_url=f'../c-care-bath-door-3d.html?scheme={option}&use={state}'))
    svg.set("width", "660")
    svg.set("height", "1903")
    svg.set("data-door-option", option)
    svg.set("data-use-state", state)
    if floor["id"] == "floor-1":
        for room in floor["rooms"]:
            f = room["features"]
            specs = [(p, "data-care-leaf-id") for p in f.get("care_entry_leaves", [])]
            specs += [(p, "data-door-part") for p in f.get("care_door_parts", [])]
            specs += [({**p, "rect_mm": component_box(p)[:4]}, "data-bath-component") for p in f.get("care_bath_components", [])]
            for spec, attr in specs:
                x, y, w, d = spec["rect_mm"]
                ET.SubElement(svg, ns+"rect", {"x": str(x), "y": str(y), "width": str(w), "height": str(d), "fill": "#a65d16", "fill-opacity": ".5", attr: spec["id"], "data-leaf-state": spec["state"]})
            for spec in f.get("care_route_overlays", []):
                ET.SubElement(svg, ns+"polyline", {"points": ' '.join(f'{x},{y}' for x, y in spec["points_mm"]), "fill": "none", "stroke": "#b43b25" if spec["blocked"] else "#b45309" if spec["id"] == "rigid-board-turn" else "#6d28d9" if spec["id"] == "turn-reserve" else "#137d9c", "stroke-width": "18", "stroke-dasharray": "80 60", "data-care-route": spec["id"]})
            circle = f.get("care_bath_circle_mm")
            if circle:
                ET.SubElement(svg, ns+"circle", {"cx": str(circle[0]), "cy": str(circle[1]), "r": str(circle[2]), "fill": "none", "stroke": "#6d28d9", "stroke-width": "18", "stroke-dasharray": "80 60"})
    return svg


def render_viewer(study, root):
    text = (root / BASE_VIEWER).read_text(encoding="utf-8")
    payload = {"c_care_bath_door": {"default_option": "two-panel", "options": [
        {"id": o["id"], "label": o["label"], "building": "C", "states": [{k: s[k] for k in ("id", "label", "model")} for s in o["states"]]} for o in study["options"]]}}
    text, count = re.subn(r'^\s*var DATA = .+;\s*$', lambda _: '  var DATA = '+json.dumps(payload, ensure_ascii=False, separators=(',', ':'))+';', text, count=1, flags=re.M)
    old = (root / "scripts/templates/c-care-bath-bootstrap.js").read_text()
    if count != 1 or text.count(old) != 1:
        raise ContractError("Frozen bath viewer/bootstrap anchor changed")
    boot = old.replace("DATA.c_care_bath", "DATA.c_care_bath_door").replace("c-care-bath", "c-care-bath-door")
    boot = boot.replace("C 孝親套衛照護比較", "C 套衛門組比較")
    boot = boot.replace("原ABC及已驗收動線版不動。原2.4×3m套衛比較零門檻開放淋浴、折椅與扶手；轉位借濕地分時使用。不是照護、濕滑、門組或救援核可。",
                        "原ABC與父版不動。新比較門洞後移20cm、兩片向後收疊；三件設備不動，轉位標示右移。半開／關門不可通行；未選產品、未採用或核可照護救援。")
    boot = boot.replace('var shortStates={baseline:"上版控制",transfer:"轉位比較",shower:"折椅放下","rail-down":"扶手放下","door-closed":"套衛關門"};',
                        'var shortStates={open:"門組全開",half:"半開不可通行",closed:"關門不可通行"};')
    badge_anchor = 'badge.textContent=shortStates[useChoice.id]+" · 未採用／濕地分時／照護救援未核";'
    if boot.count(badge_anchor) != 1 or text.count('    bathSyncRoomTitle(mesh,name);') != 1:
        raise ContractError("Missing unique door identity display anchors")
    boot = boot.replace(badge_anchor, 'doorLabelBadge(badge,studyChoice,useChoice);')
    boot = boot.replace('specs.forEach(function(spec){', 'specs.concat(mesh?(featuresOf(mesh.userData.cell).care_door_parts||[]):[]).forEach(function(spec){')
    boot = boot.replace('bathEquipment.hidden=!specs.length;', 'bathEquipment.hidden=!specs.length&&!(mesh&&(featuresOf(mesh.userData.cell).care_door_parts||[]).length);')
    text = text.replace(old, boot).replace('DATA.source.c_care_bath', 'DATA.source.c_care_bath_door')
    text = text.replace('    bathSyncRoomTitle(mesh,name);', '    doorSyncRoomTitle(mesh,name);')
    title_anchor = '  function bathSyncRoomTitle(mesh,name) {'
    if text.count(title_anchor) != 1:
        raise ContractError("Missing local title helper anchor")
    text = text.replace(title_anchor, (root / DISPLAY).read_text(encoding="utf-8")+'\n'+title_anchor)
    text = text.replace('c-care-bath.html', 'c-care-bath-door.html').replace('C孝親套衛照護比較', 'C套衛門組比較')
    anchor = '    var hvac=features.hvac || {};'
    if text.count(anchor) != 1 or text.count('      careBath:careBathEvidence(),') != 1:
        raise ContractError("Missing door hardware/evidence anchor")
    text = text.replace(anchor, (root / OVERLAY).read_text()+'\n'+anchor)
    # Identical actual-mesh bound extractor, distinct tag/field for door hardware.
    evidence = text[text.index('  function careBathEvidence(){'):text.index('  window.__htmlModel3dDebug = function () {')]
    evidence = evidence.replace('careBathEvidence', 'careDoorEvidence').replace('careBath', 'careDoor')
    text = text.replace('  window.__htmlModel3dDebug = function () {', evidence+'\n  window.__htmlModel3dDebug = function () {')
    text = text.replace('      careBath:careBathEvidence(),', '      careDoor:careDoorEvidence(),\n      careBath:careBathEvidence(),')
    return text


def render_section():
    # Pixel-bounded vector only; no conversion from a millimetre viewBox.
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="840" height="320" viewBox="0 0 840 320" role="img" aria-labelledby="track-title track-desc">'
        '<title id="track-title">兩片門軌道假設剖示意</title><desc id="track-desc">45mm門片、15mm軌道間距、45mm門片與25mm把手，共130mm。原轉位起點95mm會被侵入；新起點165mm仍留35mm。不是選品或施工圖。</desc>'
        '<style>text{font:16px system-ui,sans-serif;fill:#263846}.dim{stroke:#334155;stroke-width:2}.warn{stroke:#b43b25;stroke-width:3;stroke-dasharray:7 5}</style>'
        '<rect width="840" height="320" fill="#f8faf8"/><text x="24" y="30">局部剖示意：由左完成面向浴室內側看</text>'
        '<path d="M140 80H660 M140 72V90 M660 72V90" class="dim"/><text x="290" y="65">總厚130mm（未選品）</text>'
        '<rect x="140" y="110" width="180" height="75" fill="#d6aa69"/><rect x="320" y="110" width="60" height="75" fill="#e2e8f0"/>'
        '<rect x="380" y="110" width="180" height="75" fill="#b48445"/><rect x="560" y="130" width="100" height="35" fill="#475569"/>'
        '<text x="175" y="210">從動片45</text><text x="323" y="240">間距15</text><text x="420" y="210">主動片45</text><text x="565" y="240">把手25</text>'
        '<path d="M520 95V270" class="warn"/><text x="300" y="294" fill="#b43b25">原轉位起點95mm（會侵入）</text>'
        '<path d="M800 95V265" class="dim"/><text x="670" y="105">新轉位起點</text><text x="680" y="125">165mm</text>'
        '<path d="M660 180H800" class="dim"/><text x="695" y="202">餘35mm</text></svg>')


def write_study(study, root: Path = ROOT):
    directory = root / OUT
    directory.mkdir(parents=True, exist_ok=True)
    report = copy.deepcopy(study)
    for option in report["options"]:
        for state in option["states"]:
            state.pop("model")
    write_json(directory / "review.json", report)
    write_json(directory / "requirement-ledger.json", study["requirement_ledger"])
    (directory / "track-section.svg").write_text(render_section(), encoding="utf-8")
    for option in study["options"]:
        for state in option["states"]:
            for floor in state["plans"]["floors"]:
                svg = _svg(floor, option["id"], state["id"])
                (directory / floor["plan_file"]).write_text(ET.tostring(svg, encoding="unicode"), encoding="utf-8")
                if floor["id"] == "floor-1":
                    svg.set("viewBox", "2350 13400 3900 4050")
                    svg.set("width", "780")
                    svg.set("height", "810")
                    (directory / (option["id"]+'_'+state["id"]+'_detail.svg')).write_text(ET.tostring(svg, encoding="unicode"), encoding="utf-8")
    (root / INDEX).write_text(render_index(study), encoding="utf-8")
    (root / VIEWER).write_text(render_viewer(study, root), encoding="utf-8")
    return {"index": INDEX, "viewer": VIEWER, "report": OUT+"/review.json", "rendered_qa": "not-run"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Sources and bounded math only, no output or browser")
    cfg = parser.parse_args()
    study = build_study()
    result = {"options": 2, "states": 6, "rendered_qa": "not-run"} if cfg.check else write_study(study)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

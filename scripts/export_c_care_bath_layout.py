#!/usr/bin/env python3
"""Local independent clearance comparison; no scene or verified-parent writes."""
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

import export_c_care_bath_door as door_export  # noqa: E402
from export_current_design_basis import _move  # noqa: E402
from lib.model3d_placement import _door_approach  # noqa: E402
from lib.model3d_plan import plan_data  # noqa: E402

from house_design.c_care_bath_door import pose  # noqa: E402
from house_design.c_care_bath_fit import STATUS  # noqa: E402
from house_design.c_care_bath_layout import (  # noqa: E402
    BASE_REPORT,
    BASE_VIEWER,
    OPTIONS,
    SCHEMA,
    SOURCE,
    STATES,
    frozen_parent,
    review,
    trial_configs,
    validate_config,
)
from house_design.contracts import (  # noqa: E402
    ROOT,
    ContractError,
    read_json,
    sha256_file,
    stable_hash,
    utc_now,
    write_json,
)

OUT = "structured/candidates/c-care-bath-layout"
INDEX, VIEWER = OUT+".html", OUT+"-3d.html"
DISPLAY = "scripts/templates/c-care-bath-layout-display.js"
CHECK = "scripts/check_c_care_bath_layout_playwright.cjs"
LABELS = {"door-control": "C｜保留原兩片門組／前牆盆控制", "side-basin": "C｜側牆盆＋門洞再後移15cm餘量比較"}
STATE_LABELS = {"open": "全開：折椅／扶手收起", "half": "半開：不可通行反例", "closed": "全關：不可通行反例"}


def _patch(model, cfg, door_cfg, option, state):
    cells = {c["key"]: c for c in model["buildings"][0]["floors"][0]["cells"] if c["tour_active"]}
    bath, elder = cells["elder-bath"], cells["elder"]
    if option == "side-basin":
        raw = cfg["vanity"]
        _move(bath, "vanity", raw["rect_mm"], yaw=raw["rotation_deg"], anchor=raw["wall_anchor"])
        for room, other in ((bath, elder), (elder, bath)):
            door = next(d for d in room["tour_features"]["doors"] if d["neighbor"] == other["id"])
            door["ratio"] = (cfg["door_center_y_mm"]-room["tour_mm"]["y_mm"])/room["tour_mm"]["h_mm"]
            door["label"] = "120cm名義兩片後收疊（較門組版再後移15cm，未選品）"
            # The frozen elder-side reserve still carries the earliest door
            # center. Recompute only this shared-wall approach from the actual
            # paired opening; never shift the unrelated front bedroom entry.
            near = _door_approach(room["tour_mm"], door)
            matches = [r for r in room["tour_features"].get("reserved_mm", [])
                       if r["kind"] == "door-approach" and r["aabb"]["minX"] == near["minX"]
                       and r["aabb"]["maxX"] == near["maxX"]]
            if len(matches) != 1:
                raise ContractError("Missing unique bath-side door approach")
            matches[0]["aabb"] = near
        for part in bath["tour_features"]["care_bath_components"]:
            if part["id"] == "alarm-toilet":
                for point in part["points_mm"]:
                    point[0] += cfg["alarm_toilet_shift_x_mm"]
    features = bath["tour_features"]
    features["care_entry_leaves"], features["care_door_parts"] = pose(door_cfg, "two-panel", state)
    model["source"] = {"c_care_bath_layout": SOURCE, "geometry_basis": "frozen-door-local-basin-and-door-snapshot-not-full-build"}


def _annotate(model, detail):
    door_export._annotate(model, detail)
    bath = next(c for c in model["buildings"][0]["floors"][0]["cells"] if c["tour_active"] and c["key"] == "elder-bath")
    f = bath["tour_features"]
    for key, area, kind, blocked in (
            ("basin-arrival", detail["basin_arrival_rect_mm"], "offset-900mm-arrival-not-centered-seated-use", bool(detail["basin_arrival_coordinate_failures"])),
            ("basin-operation", detail["vanity_operation_mm"], "original-700mm-operation-sequential-with-toilet-transfer", bool(detail["vanity_operation_door_conflicts"]))):
        f["care_bath_regions"].append({"id": key, "rect_mm": area, "blocked": blocked, "kind": kind})
        x, y, w, d = area
        f["care_route_overlays"].append({"id": key, "kind": kind, "blocked": blocked,
            "points_mm": [[x, y], [x+w, y], [x+w, y+d], [x, y+d], [x, y]]})


def build_study(root: Path = ROOT):
    cfg = read_json(root / SOURCE)
    validate_config(cfg)
    parent, reference = frozen_parent(root)
    parent_door = read_json(root / "inputs/c-care-bath-door.json")
    parent_bath, route_cfg = read_json(root / "inputs/c-care-bath.json"), read_json(root / "inputs/c-care-route.json")
    options = []
    for oid in OPTIONS:
        states = []
        door_cfg, bath_cfg = trial_configs(cfg, parent_door, parent_bath, oid)
        for state in STATES:
            model = copy.deepcopy(reference["model"])
            _patch(model, cfg, door_cfg, oid, state)
            detail = review(plan_data(model)["buildings"][0], cfg, door_cfg, bath_cfg, route_cfg, oid, state, reference)
            _annotate(model, detail)
            model["bc_option"] = {"id": oid, "label": LABELS[oid], "revision": 1, "use_state": state,
                "status": STATUS, "adopted": False, "tradeoffs": cfg["limits"], "geometry_review": {"layout": detail}}
            plans = plan_data(model)["buildings"][0]
            for floor in plans["floors"]:
                floor["plan_file"] = oid+"_"+state+"_"+floor["id"]+".svg"
            states.append({"id": state, "label": STATE_LABELS[state], "model": model, "plans": plans, "review": {"layout": detail}})
        options.append({"id": oid, "building": "C", "label": LABELS[oid], "adopted": False, "status": STATUS, "states": states})
    ledger = copy.deepcopy(parent["requirement_ledger"])
    for scenario, option in zip(ledger["scenarios"], options, strict=True):
        template = copy.deepcopy(parent["requirement_ledger"]["scenarios"][1])
        scenario.clear()
        scenario.update(template, id=option["id"], label=option["label"])
        for row in scenario["rows"]:
            if row["requirement_id"] == "C.floor-1.elder_bath":
                row["note"] += (" 獨立餘量比較未採用：側盆偏側250mm到位與求助繩候選移位；700mm操作與馬桶側移分時，"
                                "停門餘量200mm，仍無坐姿可及／公差／照護／救援核可。") if option["id"] == "side-basin" else " 本方案保留門組控制的0／15／8.5mm緊餘量，不冒稱已改善。"
                row["flags"] += ["basin-reach-tolerance-and-sequential-use-unknown"]
    ledger["ledger_hash"] = stable_hash({k: v for k, v in ledger.items() if k != "ledger_hash"})
    paths = {SOURCE, BASE_REPORT, BASE_VIEWER, door_export.INDEX,
        "house_design/c_care_bath_layout.py", "scripts/export_c_care_bath_layout.py", DISPLAY, CHECK, *parent["source_hashes"]}
    result = {"schema": SCHEMA, "revision": 1, "display_revision": 2, "bath_display_revision": 2, "layout_display_revision": 1,
        "generated_at": utc_now(), "status": STATUS, "adopted": False, "rendered_qa": "not-run",
        "default_option": "side-basin", "default_state": "open", "frame_mm": cfg["frame_mm"],
        "limits": cfg["limits"], "professional_status": cfg["professional_status"], "options": options,
        "base_report_hash": parent["report_hash"], "base_plan_hash": stable_hash(reference["plans"]),
        "requirement_ledger": ledger, "source_hashes": {p: sha256_file(root / p) for p in sorted(paths)}}
    result["report_hash"] = stable_hash({k: v for k, v in result.items() if k != "generated_at"})
    return result


def render_index(study):
    esc, sections, rows = html.escape, [], []
    for option in study["options"]:
        states = []
        for state in option["states"]:
            oid, sid, d = option["id"], state["id"], state["review"]["layout"]
            if sid == "open":
                m = d["critical_margins_mm"]
                rows.append(f'<tr><th scope="row">{esc(option["label"])}</th><td>{m["vanity_final_arrival"]:g}mm</td><td>{m["transfer_to_vanity"]:g}mm</td><td>{m["board_turn_to_folded_seat"]:g}mm</td><td>{d["rear_parking_after_20mm_stop_mm"]:g}mm</td></tr>')
            link = f'c-care-bath-layout-3d.html?scheme={oid}&amp;use={sid}#mode=tour&amp;building=C&amp;floor=floor-1&amp;room=C%3Afloor-1%3Aelder-bath&amp;focus=room&amp;view=plan'
            full = ''.join(f'<figure><figcaption>{esc(f["label"])}</figcaption><object type="image/svg+xml" data="c-care-bath-layout/{f["plan_file"]}" width="660" height="1903"></object></figure>' for f in state["plans"]["floors"])
            states.append(f'<details id="{oid}-{sid}" data-use-state="{sid}"'+(' open' if oid == 'side-basin' and sid == 'open' else '')+f'><summary>{esc(state["label"])}</summary><p><a href="{link}">對應3D特寫</a>；開口假設{d["effective_width_assumption_mm"]:g}mm（商品實際淨寬未知）</p><figure><object type="image/svg+xml" data="c-care-bath-layout/{oid}_{sid}_detail.svg" width="780" height="810"><a href="c-care-bath-layout/{oid}_{sid}_detail.svg">套衛放大圖</a></object></figure><details><summary>完整四層對照</summary>{full}</details></details>')
        sections.append(f'<section data-option="{option["id"]}"><h2>{esc(option["label"])}</h2>'+''.join(states)+'</section>')
    return ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>C套衛餘量比較｜原門組與側牆盆</title><style>body{font:16px/1.65 system-ui,sans-serif;max-width:1120px;margin:auto;padding:18px;background:#f8faf8;color:#24382e}a{color:#17634d}.warning{background:#fff1d6;padding:12px;color:#65430b}section{border-top:1px solid #cbd5ce;margin-top:24px}summary{cursor:pointer;padding:12px 0;min-height:44px}figure{margin:12px 0;overflow:auto;max-height:740px;border:1px solid #cbd5ce}object{display:block;max-width:none}table{border-collapse:collapse;width:100%}th,td{border:1px solid #cbd5ce;padding:8px;text-align:left}.scroll{overflow:auto}.matrix{min-width:700px}@media(max-width:640px){body{padding:12px}figure{max-height:600px}}</style><body>'
        '<h1>C 套衛餘量比較</h1><p id="layout-adoption-warning" class="warning">比較方案，未採用／專業未核。只核指定外廓；不是坐姿可及、輪椅、照護、救援或施工核可。</p>'
        '<p><a href="c-care-bath-layout-3d.html">新比較3D</a> · <a href="c-care-bath-door.html">保留已驗收門組版</a> · <a href="c-care-bath-layout/review.json">同源座標與限制</a> · <a href="c-care-bath-layout/requirement-ledger.json">40列C需求對帳</a></p>'
        '<h2>建議：先深化側牆盆，不擴套衛</h2><p>原600×450mm盆體轉向左牆，平面450×600mm，尺寸沒有縮。原700mm操作深度保留；馬桶、淋浴、折椅、扶手與房間外框不動。配對門洞較上一門組版再後移150mm，較最早原洞共350mm；1200mm名義門洞與900mm原目標不降。</p>'
        '<div class="scroll" tabindex="0" role="region" aria-label="餘量比較可左右捲動"><table class="matrix"><thead><tr><th scope="col">方案（全開）</th><th scope="col">盆前指定到位餘量</th><th scope="col">側移旁盆緣</th><th scope="col">板轉向至折椅</th><th scope="col">停門含20mm止擋</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
        '<p>盆前到位改按實際朝向量測：控制為-y、側盆為-x，不能沿用原y差公式。新900mm矩形相對盆中線偏側250mm；面向盆緣餘50mm，但坐姿龍頭可及、檯下膝部與排水管未核，不給膝部信用。</p>'
        '<p class="warning">代價／新限制：門後餘量350→200mm；原求助繩會落進旋轉後的700mm操作區，候選右移200mm並重核低位可及與防纏繞。盆前操作與馬桶側移重疊0.2675m²，只能分時，不能當兩人同時使用。</p>'
        '<p>剛性板入口試線隨洞後移150mm、轉向試點前移50mm，仍保留600×1800mm板與1898mm全角度方框，不是抬抱或擔架核可。新方框到馬桶56mm、到折椅58.5mm；到右側扶手仍僅18.5mm。門組到轉位仍35mm，厚度165mm即零餘量、180mm侵入15mm，仍需產品與施工公差完整回套。</p>'
        '<p>兩案各有全開／半開／全關三個獨立狀態；全開扣框假設970mm，半開485mm與全關0mm必須實際受門片阻擋。門先全開才進出，折椅／扶手收起，仍借淋浴濕地分時轉位。</p>'
        '<ul>'+''.join('<li>'+esc(v)+'</li>' for v in study["limits"])+'</ul>'+''.join(sections)+
        '<p>ABC主案與已驗收門組包不覆寫。新包rendered_qa=not-run；舊passed不能覆蓋新排法。真人照護、風水、法規、選品與施工仍未知。</p></body></html>')


def _replace(text, old, new):
    if text.count(old) != 1:
        raise ContractError("Frozen layout viewer anchor changed: "+old[:100])
    return text.replace(old, new)


def render_viewer(study, root):
    text = (root / BASE_VIEWER).read_text(encoding="utf-8")
    payload = {"c_care_bath_layout": {"default_option": "side-basin", "options": [
        {"id": o["id"], "label": o["label"], "building": "C", "states": [{k: s[k] for k in ("id", "label", "model")} for s in o["states"]]} for o in study["options"]]}}
    text, count = re.subn(r'^\s*var DATA = .+;\s*$', lambda _: '  var DATA = '+json.dumps(payload, ensure_ascii=False, separators=(',', ':'))+';', text, count=1, flags=re.M)
    if count != 1:
        raise ContractError("Missing single frozen viewer DATA declaration")
    text = _replace(text, (root / door_export.DISPLAY).read_text(encoding="utf-8"), (root / DISPLAY).read_text(encoding="utf-8"))
    text = text.replace("DATA.c_care_bath_door", "DATA.c_care_bath_layout").replace("DATA.source.c_care_bath_door", "DATA.source.c_care_bath_layout")
    text = text.replace("c-care-bath-door", "c-care-bath-layout").replace("C 套衛門組比較", "C 套衛餘量比較").replace("C套衛門組比較", "C套衛餘量比較")
    text = _replace(text, "doorLabelBadge(badge,studyChoice,useChoice);", "layoutLabelBadge(badge,studyChoice,useChoice);")
    text = _replace(text, "    doorSyncRoomTitle(mesh,name);", "    layoutSyncRoomTitle(mesh,name);")
    old_notice = "原ABC與父版不動。新比較門洞後移20cm、兩片向後收疊；三件設備不動，轉位標示右移。半開／關門不可通行；未選產品、未採用或核可照護救援。"
    text = _replace(text, old_notice, "原ABC與門組版保留。側盆比較：原600×450盆轉向左牆、門洞再後移15cm、求助繩候選右移20cm；盆前偏側250mm到位未核可及，操作與側移分時。原門組控制保留0／15／8.5mm緊餘量，兩案未採用／照護救援未核。")
    return text


def _svg(floor, option, state):
    svg = door_export._svg(floor, option, state)
    svg.attrib.pop("data-door-option")
    svg.set("data-layout-option", option)
    for node in svg.iter():
        for key, value in list(node.attrib.items()):
            if "c-care-bath-door-3d.html" in value:
                node.set(key, value.replace("c-care-bath-door-3d.html", "c-care-bath-layout-3d.html"))
    return svg


def write_study(study, root: Path = ROOT):
    directory = root / OUT
    directory.mkdir(parents=True, exist_ok=True)
    report = copy.deepcopy(study)
    for option in report["options"]:
        for state in option["states"]:
            state.pop("model")
    write_json(directory / "review.json", report)
    write_json(directory / "requirement-ledger.json", study["requirement_ledger"])
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
    parser.add_argument("--check", action="store_true", help="Bounded files/math only; no output or browser")
    args = parser.parse_args()
    study = build_study()
    print(json.dumps({"options": 2, "states": 6, "rendered_qa": "not-run"} if args.check else write_study(study), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

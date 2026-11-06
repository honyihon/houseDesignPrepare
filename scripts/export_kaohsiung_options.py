#!/usr/bin/env python3
"""Bounded frozen-snapshot patches and SVG serialization; no full 3D build.

The two superseded opening modules are verified via explicit historical copies.
This creates a new independent package; it never retargets or blesses old QA.
"""
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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.model3d_plan import plan_data, render_plan  # noqa: E402

from house_design.contracts import (  # noqa: E402
    ROOT,
    ContractError,
    read_json,
    sha256_file,
    stable_hash,
    utc_now,
    write_json,
)
from house_design.kaohsiung_options import (  # noqa: E402
    SCHEMA,
    STATUS,
    a_and_c_costs,
    patch_model,
    review,
    validate_config,
)
from house_design.requirement_reconciliation import _public_path  # noqa: E402

SOURCE = "inputs/kaohsiung-house-options.json"
OUT = "structured/candidates/kaohsiung-house-options"
INDEX, VIEWER = OUT+".html", OUT+"-3d.html"
OVERLAY = "scripts/templates/kaohsiung-options-overlay.js"


def frozen_base(cfg, root=ROOT):
    for key in ("base_report", "base_viewer"):
        if sha256_file(_public_path(root, cfg[key])) != cfg.get(key+"_sha256"):
            raise ContractError("Frozen parent bytes changed; review the selected input: "+key)
    report = read_json(root/cfg["base_report"])
    if (report.get("schema") != "house-current-design-basis-v1" or report.get("adopted") is not False
            or not report.get("source_hashes") or not report.get("report_hash")):
        raise ContractError("Missing frozen discussion parent")
    historical = read_json(root/cfg["historical_source_manifest"])
    expected = {
        "scripts/lib/model3d_openings.py": "inputs/references/source-history/20261027-before-model3d_openings.py.txt",
        "scripts/lib/model3d_review.py": "inputs/references/source-history/20261027-before-model3d_review.py.txt",
    }
    refs = {f["original"]: f for f in historical["files"]}
    if set(refs) != set(expected):
        raise ContractError("No additional historical-source exceptions allowed")
    evidence = []
    for name, digest in report["source_hashes"].items():
        target = _public_path(root, name)
        if sha256_file(target) == digest:
            continue
        if name not in expected or refs[name]["reference"] != expected[name]:
            raise ContractError("Unexplained frozen source change: "+name)
        reference = _public_path(root, expected[name])
        if refs[name]["sha256"] != digest or sha256_file(reference) != digest:
            raise ContractError("Historical opening-source bytes do not match frozen report")
        evidence.append({"original": name, "historical_reference": expected[name], "frozen_sha256": digest,
            "current_sha256": sha256_file(target), "scope": "historical-input-not-current-qa"})
    text = (root/cfg["base_viewer"]).read_text()
    match = re.search(r"^\s*var DATA = (.+);\s*$", text, re.M)
    if match is None:
        raise ContractError("Missing frozen embedded model")
    payload = json.loads(match[1])["current_design_basis"]
    reconstructed = copy.deepcopy(report)
    for option in reconstructed["options"]:
        source_option = next(o for o in payload["options"] if o["id"] == option["id"])
        for state in option["states"]:
            state["model"] = next(s["model"] for s in source_option["states"] if s["id"] == state["id"])
            actual = plan_data(state["model"])["buildings"][0]
            for floor, previous in zip(actual["floors"], state["plans"]["floors"], strict=True):
                floor["plan_file"] = previous["plan_file"]
            if actual != state["plans"]:
                raise ContractError("Frozen model and parent plan differ")
    if stable_hash({k: v for k, v in reconstructed.items() if k not in {"generated_at", "report_hash"}}) != report["report_hash"]:
        raise ContractError("Frozen report/model seal mismatch")
    return reconstructed, evidence


def build_study(root=ROOT):
    cfg = read_json(root/SOURCE)
    validate_config(cfg)
    parent, history = frozen_base(cfg, root)
    options = []
    specs = [
        ("a-rear-study", "a-current", "A", "A｜後側8㎡條件比較；前側加深另列代價", False),
        ("b-rear-split", "b-rear-refined", "B", "B｜後巷優先＋9.12㎡景觀分區", False),
        ("b-front-split", "b-front-refined", "B", "B｜前門備案＋9.12㎡景觀分區", False),
        ("c-control", "c-care-refined", "C", "C｜原洗曬／空調控制案", True),
        ("c-split", "c-care-refined", "C", "C｜右側9㎡景觀＋左側單機洗曬比較", False),
    ]
    for oid, source, bid, label, control in specs:
        original = next(o for o in parent["options"] if o["id"] == source)
        states = []
        for old_state in original["states"]:
            model = patch_model(old_state["model"], cfg, bid, oid, old_state["id"], control=control)
            model["bc_option"].update(label=label, tradeoffs=[
                "獨立高雄厝比較，未採用／專業未核；基地、法定面積、覆土、支承、外窗與能效仍未知。",
                "只改二樓陽台分區及指定設備位置，原房間、床櫃、門窗、樓梯與標高保留。",
                cfg[bid.lower()]["note"] if not control else "原C控制案；沒有新增景觀區，原格局不視為符合高雄厝。",
                "C照護側盆／門組續版仍另案；本圖不默認合併，公衛／客餐及一樓工作陽台原需求保留。"
                if bid == "C" else "B祭祀與前後門三種使用狀態保留；A1照護外窗、電梯及完整機電尚未解。",
            ])
            plans = plan_data(model)["buildings"][0]
            for floor in plans["floors"]:
                floor["plan_file"] = f"{oid}_{old_state['id']}_{floor['id']}.svg"
            result = review(plans, old_state["plans"], cfg[bid.lower()], bid, control=control)
            model["bc_option"]["geometry_review"] = copy.deepcopy(result)
            states.append({"id": old_state["id"], "label": old_state["label"], "model": model,
                "plans": plans, "review": result})
        options.append({"id": oid, "label": label, "building": bid, "source_option": source,
            "adopted": False, "states": states})
    source_paths = [SOURCE, cfg["base_report"], cfg["base_viewer"], cfg["historical_source_manifest"],
        "scripts/export_kaohsiung_options.py", "house_design/kaohsiung_options.py", OVERLAY,
        "house_design/contracts.py", "house_design/b32_service_detail.py", "house_design/b32_services.py",
        "house_design/b32_rear_right.py", "house_design/requirement_reconciliation.py",
        "scripts/lib/model3d_plan.py", "scripts/lib/model3d_placement.py",
        "scripts/lib/model3d_facade.py", "scripts/lib/model3d_mdf.py",
        "inputs/references/kaohsiung-house-review-20261103.json",
        "inputs/references/kaohsiung-house-law-excerpts-20261103.txt",
        "inputs/project.json", "inputs/requirements.json", "inputs/c-care-bath-products.json",
        *[e["historical_reference"] for e in history]]
    # Bind current source bytes too. Historical references describe only the
    # old input; a new result can never claim the current generators ran then.
    source_paths += list(parent["source_hashes"])
    study = {"schema": SCHEMA, "revision": 1, "display_revision": 2, "generated_at": utc_now(), "status": STATUS,
        "adopted": False, "rendered_qa": "not-run", "default_option": cfg["default_option"],
        "frame_mm": cfg["frame_mm"], "options": options, "cost_studies": a_and_c_costs(),
        "professional_status": cfg["professional_status"], "historical_input_resolution": history,
        "parent_report_hash": parent["report_hash"],
        "source_hashes": {p: sha256_file(_public_path(root, p)) for p in sorted(set(source_paths))},
        "original_requirements_changed": False, "full_scene_or_parent_regeneration": False}
    study["report_hash"] = stable_hash({k: v for k, v in study.items() if k not in {"generated_at", "report_hash"}})
    return study


def _rect(svg, area, *, fill, stroke, identifier):
    x, y, w, h = area
    return ET.SubElement(svg, "{http://www.w3.org/2000/svg}rect", {
        "x": str(x), "y": str(y), "width": str(w), "height": str(h),
        "fill": fill, "stroke": stroke, "stroke-width": "25", "data-kh-zone": identifier,
        "pointer-events": "none"})


def svg_plan(option, state, floor):
    svg = ET.fromstring(render_plan(option["building"], floor,
        viewer_url=f"../kaohsiung-house-options-3d.html?scheme={option['id']}&use={state['id']}"))
    svg.set("width", "660")
    svg.set("height", "1903")
    svg.set("data-kh-option", option["id"])
    svg.set("data-use-state", state["id"])
    for room in floor["rooms"]:
        zone = room["features"].get("kaohsiung_zones")
        if not zone:
            continue
        _rect(svg, zone["garden_mm"], fill="none", stroke="#2563eb", identifier="garden")
        for n, r in enumerate(zone["soil_rects_mm"]):
            _rect(svg, r, fill="#86b68b", stroke="#25583c", identifier="soil-"+str(n))
        for n, (x, y) in enumerate(zone["woody_points_mm"]):
            ET.SubElement(svg, "{http://www.w3.org/2000/svg}circle", {
                "cx": str(x), "cy": str(y), "r": "110", "fill": "#285735", "data-kh-tree": str(n)})
        y = zone["garden_mm"][1]+zone["garden_mm"][3]-500
        text = ET.SubElement(svg, "{http://www.w3.org/2000/svg}text", {
            "x": str(zone["garden_mm"][0]+140), "y": str(y), "font-size": "170", "fill": "#194a36"})
        result = state["review"]
        text.text = f"景觀{result['garden_nominal_sqm']:g}㎡／覆土比較{result['proposed_soil_sqm']:g}㎡；未核"
    return svg


def render_index(study):
    esc = html.escape
    sections = []
    for o in study["options"]:
        state_blocks = []
        for s in o["states"]:
            link = f"kaohsiung-house-options-3d.html?scheme={o['id']}&use={s['id']}#mode=tour&building={o['building']}&floor=floor-2&view=plan"
            figures = "".join(f'<figure><figcaption>{esc(f["label"])} · <a href="kaohsiung-house-options/{f["plan_file"]}">另開SVG</a></figcaption><div class="plan"><object type="image/svg+xml" data="kaohsiung-house-options/{f["plan_file"]}"><a href="kaohsiung-house-options/{f["plan_file"]}">開啟平面</a></object></div></figure>' for f in s["plans"]["floors"])
            result = s["review"]
            text = ("控制案，沒有新景觀區。" if result["control"] else
                f'景觀區名義{result["garden_nominal_sqm"]:g}㎡，覆土比較{result["proposed_soil_sqm"]:g}㎡（{result["proposed_green_ratio"]:.1%}），木本示意{result["woody_count"]}株、至少一株120cm；土深及結構未知。其餘{result["uncredited_other_outdoor_sqm"]:g}㎡不給景觀免計信用。')
            detail = f'kaohsiung-house-options/{o["id"]}_{s["id"]}_balcony-detail.svg'
            zoom = f'<figure><figcaption>本次二樓陽台細部 · <a href="{detail}">另開放大圖</a></figcaption><div class="plan"><object type="image/svg+xml" data="{detail}"><a href="{detail}">開啟陽台細部</a></object></div></figure>'
            state_blocks.append(f'<details id="{o["id"]}-{s["id"]}" {"open" if s["id"]=="daily" else ""}><summary>{esc(s["label"])}：<a href="{esc(link,quote=True)}">開此狀態3D</a></summary><p>{text}</p>'+zoom+'<details><summary>各層完整平面對照</summary>'+figures+'</details></details>')
        notes = "".join('<li>'+esc(n)+'</li>' for n in o["states"][0]["model"]["bc_option"]["tradeoffs"])
        sections.append(f'<section data-option="{o["id"]}" id="{o["id"]}"><h2>{esc(o["label"])}</h2><ul>{notes}</ul>'+"".join(state_blocks)+'</section>')
    return ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>ABC高雄厝陽台分區比較</title><style>body{font:16px/1.7 system-ui;max-width:1120px;margin:auto;padding:18px;background:#f7faf8;color:#20382c}a{color:#075a75}nav{display:flex;flex-wrap:wrap;gap:14px}.warning{background:#fff0ce;padding:12px}section{border-top:1px solid #b8c9bf;margin-top:30px}summary{cursor:pointer;padding:12px 0;min-height:44px}.plan{max-height:650px;overflow:auto;border:1px solid #bac9c0}.plan object{width:660px;max-width:none;display:block}figure{margin:16px 0}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #bac9c0;text-align:left}@media(max-width:640px){body{padding:12px}.plan{max-height:480px}}</style><body>'
        '<h1>ABC高雄厝陽台分區比較</h1><p class="warning" id="kh-adoption-warning">獨立比較，未採用／專業未核。既有房間、門窗、樓梯及標高保留；C照護續版仍另案。局部座標無衝突不等於高雄厝或建照合格。</p>'
        '<p>藍框：擬申報景觀範圍；綠色：降板覆土候選投影，非已完成土深／支承設計。原陽台剩餘面積仍須另核合法性。</p><nav>'+"".join(f'<a href="#{o["id"]}">{esc(o["label"])}</a>' for o in study["options"])+
        '</nav><p><a href="kaohsiung-house-options-3d.html">開啟3D</a> · <a href="../../Docs/kaohsiung-house-options-v1.md">取捨與手動驗收</a> · <a href="current-design-basis.html">原整棟方案</a></p>'+"".join(sections)+
        '<section id="costs"><h2>A外窗／前陽台與C騎樓樓梯：先看代價</h2><table><tr><th>方向</th><th>這輪判斷</th></tr>'
        '<tr><td>A前陽台全寬1.5→2.2m</td><td>主臥減4.2㎡，名義僅15.48㎡、深2.58m；低於原16㎡目標且不足景觀所在居室3m深，不推薦直接改。</td></tr>'
        '<tr><td>A1外窗</td><td>側界合法外空間尚未知；1×1m前天井會吃掉1㎡客餐，並穿過上層公共走道，須整棟重排，沒有畫成已解。</td></tr>'
        '<tr><td>C一樓3.6→4m假設</td><td>保留22級則每級約181.82mm，原梯深有機會保留，但適用類組、淨高與照護舒適性未核；改24級約166.67mm則需4970mm梯深，比現4840mm多130mm。兩案上層標高均差400mm。僅剖面預算，本頁3D維持原3.6m。</td></tr></table></section>'
        '<p>尚缺基地／後巷與開口權利、法定面積表、懸臂／覆土防水剖面、第一＋級能效與浴廁完整設計。沒有新增電梯或默認任何免計面積。</p></body></html>')


def render_viewer(study, root=ROOT):
    text = (root/"structured/candidates/current-design-basis-3d.html").read_text()
    payload = {"kaohsiung_options": {"default_option": study["default_option"], "display_revision": study["display_revision"],
        "report_hash": study["report_hash"], "source_hashes": study["source_hashes"],
        "cost_studies": study["cost_studies"], "professional_status": study["professional_status"], "options": [
        {"id": o["id"], "label": o["label"], "building": o["building"], "states": [
            {k: s[k] for k in ("id", "label", "model")} for s in o["states"]]} for o in study["options"]]}}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    text, count = re.subn(r"(^\s*var DATA = ).+(;\s*$)", lambda m: m[1]+encoded+m[2], text, count=1, flags=re.M)
    if count != 1:
        raise ContractError("Missing frozen viewer payload anchor")
    replacements = {
        "var study=DATA.current_design_basis,studyUrl=": "var study=DATA.kaohsiung_options,studyUrl=",
        'dataset.studyKind="current-design-basis"': 'dataset.studyKind="kaohsiung-options";document.body.dataset.khDisplayRevision="2"',
        'textContent="ABC目前討論基準 · 未採用"': 'textContent="ABC高雄厝分區比較 · 未採用"',
        'if(!studyHash.get("floor"))studyHash.set("floor","floor-1")': 'if(!studyHash.get("floor"))studyHash.set("floor","floor-2")',
        'next.hash="mode=tour&building="+choice.building+"&floor=floor-1&view=plan"': 'next.hash="mode=tour&building="+choice.building+"&floor=floor-2&view=plan"',
        '"current-design-basis.html#"': '"kaohsiung-house-options.html#"',
        '  var furnitureLabelRects=[];': (root/OVERLAY).read_text()+'\n  var furnitureLabelRects=[];',
        '    var full = document.getElementById("full-walls").checked;': '    var full = document.getElementById("full-walls").checked;\n    khBuildZones(mesh,group,base,features);',
        '      geomSource: geomSource,': '      kaohsiung:khEvidence(),\n      geomSource: geomSource,',
        '    var mesh = viewState.room && meshById[viewState.room];\n    var name = mesh ?':
            '    var mesh = viewState.room && meshById[viewState.room];\n    if(mesh){khAppendEquipmentReadout(list,mesh.userData.cell,featuresOf(mesh.userData.cell));}\n    var name = mesh ?',
        'fallbackLink.href = DATA.study_option ? "c1f-options.html#scheme=" + DATA.study_option.id : "../../" + fallbackBuilding + "buildingView.html";':
            'fallbackLink.href = "kaohsiung-house-options.html#"+studyChoice.id+"-"+useChoice.id;',
    }
    for old, new in replacements.items():
        expected_count = 2 if old == '"current-design-basis.html#"' else 1
        if text.count(old) != expected_count:
            raise ContractError("Frozen viewer adapter anchor changed: "+old[:70])
        text = text.replace(old, new)
    # Eliminate the old package's return link and stale study explanation.
    text = text.replace('href="current-design-basis.html"', 'href="kaohsiung-house-options.html"')
    text = text.replace("ABC目前討論基準", "ABC高雄厝分區比較")
    text = text.replace("返回 ABC 主案", "原ABC歷史對照")
    text = text.replace('aria-label="B／C比較方案控制（未採用）"', 'aria-label="ABC高雄厝比較方案控制（未採用）"')
    text = text.replace('新A套衛與收納取捨待屋主選擇。', '景觀申報、覆土支承及第一＋級能效待核；A前側及C樓高僅列代價。')
    return text


def write_study(study, root=ROOT):
    directory = root/OUT
    directory.mkdir(parents=True, exist_ok=True)
    report = copy.deepcopy(study)
    for option in report["options"]:
        for state in option["states"]:
            state.pop("model")
    for option in study["options"]:
        for state in option["states"]:
            for floor in state["plans"]["floors"]:
                svg = svg_plan(option, state, floor)
                (directory/floor["plan_file"]).write_text(ET.tostring(svg, encoding="unicode"))
                if floor["id"] == "floor-2":
                    svg.set("viewBox", "-250 -350 6500 4750" if option["building"] != "A" else "-250 15130 6500 3000")
                    svg.set("height", "500")
                    (directory/(option["id"]+"_"+state["id"]+"_balcony-detail.svg")).write_text(ET.tostring(svg, encoding="unicode"))
    (root/INDEX).write_text(render_index(study))
    (root/VIEWER).write_text(render_viewer(study, root))
    # Output hashes bind this exact viewer, index and all SVGs to the report.
    files = [INDEX, VIEWER, *[str(p.relative_to(root)) for p in sorted(directory.glob("*.svg"))]]
    report["artifact_hashes"] = {p: sha256_file(root/p) for p in files}
    write_json(directory/"review.json", report)
    return {"index": INDEX, "viewer": VIEWER, "report": OUT+"/review.json", "options": len(study["options"]),
        "states": sum(len(o["states"]) for o in study["options"]), "rendered_qa": "not-run"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Bounded source/geometry checks only; no output")
    args = parser.parse_args()
    study = build_study()
    print(json.dumps({"options": len(study["options"]), "states": sum(len(o["states"]) for o in study["options"]),
        "report_hash": study["report_hash"], "rendered_qa": "not-run"} if args.check else write_study(study), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Patch frozen HTML/data copies and serialize SVGs; no solver or scene runtime."""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT/"scripts"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import export_kaohsiung_options as kh  # noqa: E402
from merge_c_stair_into_3d import floor_svg as c_floor_svg  # noqa: E402

from house_design.ac_storage_preview import ARCHIVE, OUT, RUNTIME, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from house_design.plan_readability import readable_svg  # noqa: E402
from scripts.check_upper_floor_storage_merge import VIEWER  # noqa: E402


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ContractError("Frozen A/C viewer anchor differs: "+old[:80])
    return text.replace(old, new, 1)


def replace_line(text, prefix, value):
    lines = text.splitlines(keepends=True)
    indexes = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    if len(indexes) != 1:
        raise ContractError("Frozen viewer line differs: "+prefix)
    lines[indexes[0]] = value+"\n"
    return "".join(lines)


def viewer_text(root, report):
    payload = {"kaohsiung_options": {k: report[k] for k in (
        "default_option", "report_hash", "source_hashes", "cost_studies", "professional_status")}}
    study = payload["kaohsiung_options"]
    study.update(display_revision=report["display_revision"], integration_revision=2, stair_display_revision=2, ac01_route_revision=1,
        storage_cases=report["cases"], options=[{"id": o["id"], "label": o["label"], "building": o["building"],
            "states": [{k: s[k] for k in ("id", "label", "model")} for s in o["states"]]} for o in report["options"]])
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("&", "\\u0026")
    text = (root/VIEWER).read_text()
    text, count = re.subn(r"(^\s*var DATA = ).+(;\s*$)", lambda m: m[1]+encoded+m[2], text, count=1, flags=re.M)
    if count != 1:
        raise ContractError("Missing frozen main-viewer data")
    controls = '''<section id="bc-study-controls" class="bc-study-controls" aria-label="A與C收納比較">
<h2>A／C上層收納比較</h2><p class="bc-study-warning" id="ac-adoption-warning">原配置與加櫃比較；尚未採用。產品、門片、照護與工程仍待核。</p>
<label for="study-scheme">棟別<select id="study-scheme"></select></label>
<label for="study-use">比較版本<select id="study-use"></select></label>
<label for="ac-storage-floor">樓層與收納<select id="ac-storage-floor"></select></label>
<p id="ac-storage-readout" aria-live="polite"></p>
<div class="ac-storage-actions"><button id="ac-storage-focus" type="button">看新增櫃體</button><button id="ac-storage-floor-view" type="button">看完整樓層</button></div>
<label for="b32-label-mode">圖上品名<select id="b32-label-mode"><option value="all">全部品名</option><option value="compact">重點品名</option></select></label>
<p id="ac-name-help" class="hint">全部品名可另外開關家具名稱；重點品名只保留重要空間標示。</p>
<a id="study-plan-link" href="plans.html">開同版平面與中文圖例</a> · <a href="plans.html">全部平面及使用限制</a>
<details><summary>原方案保留條件</summary><p id="bc-study-tradeoffs"></p></details></section>'''
    text, count = re.subn(r'<section id="bc-study-controls"[\s\S]*?</section>', lambda _: controls, text, count=1)
    if count != 1:
        raise ContractError("Missing original comparison controls")
    # Only rewrite static HTML links. Never run regex over embedded JS or model strings.
    split = text.index("<script>")
    head, body = text[:split], text[split:]
    head = re.sub(r'href="[^"]*"', 'href="plans.html"', head)
    text = head+body
    text = replace_line(text, '  document.querySelector("h1").textContent=',
        '  document.querySelector("h1").textContent="A／C整層收納比較 · 未採用";')
    text = replace_line(text, '  document.getElementById("tour-notice").textContent=',
        '  document.getElementById("tour-notice").textContent="只新增各棟2F、3F及RF的三件收納，原房界、門窗、樓梯與家具保留。C3取物需進主臥；RF只作防雨工具收納，商品與固定待核。1F沿來源配置，未合併其他照護續案。";')
    text = replace_once(text, 'dataset.studyKind="kaohsiung-options"', 'dataset.studyKind="ac-storage-preview"')
    text = replace_once(text, '  b32LabelMode.value=new URL(location.href).searchParams.get("labels")==="all"?"all":"compact";',
        '  b32LabelMode.value=new URL(location.href).searchParams.get("labels")==="compact"?"compact":"all";')
    text = replace_once(text, 'if(!studyHash.get("view"))studyHash.set("view","plan");',
        'if(!studyHash.get("view"))studyHash.set("view","front");')
    text = replace_line(text, '  document.getElementById("study-plan-link").href=',
        '  document.getElementById("study-plan-link").href="plans.html";')
    text = replace_once(text, '    next.hash="mode=tour&building="+choice.building+"&floor=floor-2&view=plan";location.assign(next.href);',
        '    var values=new URLSearchParams(location.hash.slice(1)),floor=values.get("floor")||"floor-2";\n'
        '    values.set("mode","tour");values.set("building",choice.building);values.set("floor",floor);\n'
        '    var targetCase=study.storage_cases.find(function(c){return c.option===choice.id&&c.floor===floor;});\n'
        '    if(values.get("room")&&targetCase){values.set("room",targetCase.host_room_id);}else{values.delete("room");values.delete("focus");}\n'
        '    if(!values.get("room")||values.get("focus")!=="room"){next.searchParams.delete("cabinet");}\n'
        '    next.hash=values.toString();location.assign(next.href);')
    text = replace_once(text, '    window.requestAnimationFrame(function(){basisResizePending=false;resize();});',
        '    window.requestAnimationFrame(function(){basisResizePending=false;acStorageResize();});')
    text = replace_once(text, '    basisLastDraw={clipped:clipped,area:clipped?{left:left,right:right,top:top,bottom:bottom}:null,\n'
        '      stage:{width:width,height:height},renderSize:{width:size.x,height:size.y},clearedOutside:clipped};',
        '    basisLastDraw={clipped:clipped,area:clipped?{left:left,right:right,top:top,bottom:bottom}:null,\n'
        '      stage:{width:width,height:height},renderSize:{width:size.x,height:size.y},clearedOutside:clipped};\n'
        '    acStorageLastDrawStamp=acStorageViewStamp();')
    text = replace_once(text, '  try { renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true }); }',
        '  try { renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, preserveDrawingBuffer: true }); }')
    text = replace_line(text, '  fallbackLink.href =', '  fallbackLink.href = "plans.html";')
    text = replace_once(text, '    if(DATA.bc_option){htmlHref="kaohsiung-house-options.html#"+encodeURIComponent(DATA.bc_option.id);}',
        '    if(DATA.bc_option){htmlHref="plans.html";}')
    # Project-only detail links do not exist after independently unpacking this preview.
    text = text.replace('source.href="../../Docs/abc-facade-v1.md"', 'source.href="plans.html"')
    text = text.replace('detail.href="kaohsiung-house-options/c-ac01-route-study.svg"', 'detail.href="plans.html"')
    text = text.replace("href='../../Docs/abc-rationality-followup-v1.md'", "href='plans.html'")
    text = text.replace("href='../../Docs/a-storage-dry-zone-v2.md'", "href='plans.html'")
    text = replace_once(text, '    if (spec.color != null) { return spec.color; }',
        '    if(entry.item.storage_case){return 0xeea13b;}\n    if (spec.color != null) { return spec.color; }')
    text = replace_once(text, '    var counts = DATA.furniture.basis_counts || {};',
        '    var counts=furnitureEntries.reduce(function(r,e){var key=e.item.basis;r[key]=(r[key]||0)+1;return r;},{});')
    text = replace_once(text, 'DATA.furniture.rooms + " 個空間、" + DATA.furniture.items + " 件；"',
        'new Set(furnitureEntries.map(function(e){return e.cell.id;})).size + " 個空間、" + furnitureEntries.length + " 件；"')
    text = replace_once(text, '  window.__htmlModel3dDebug = function () {',
        (root/RUNTIME).read_text()+'\n  window.__htmlModel3dDebug = function () {')
    text = replace_once(text, '    syncRoomViewActions();\n    var building=buildingRecord(viewState.building), review=building && building.layout_review;',
        '    acStorageReadout();\n    syncRoomViewActions();\n    var building=buildingRecord(viewState.building), review=building && building.layout_review;')
    text = replace_once(text, '      presentation = button.getAttribute("data-presentation");', '      presentation = "tour";')
    text = replace_once(text, '    presentation=!location.hash?"tour":values.get("mode")==="tour"?"tour":values.get("mode")==="diagnostic"?"diagnostic":"interior";',
        '    presentation="tour";')
    text = replace_once(text, '</head>', '''<style id="ac-storage-style">
#presentation-mode button:not([data-presentation="tour"]),#geom-source,#tour-actions,#furniture-start,.review-details,#mdf-section-link,#facade-actions{display:none!important}
#ac-storage-readout{font-size:14px;line-height:1.5;overflow-wrap:anywhere}.ac-storage-actions{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}.ac-storage-actions button{min-height:44px;padding:7px 10px;font:inherit}
#ac-storage-floor{display:block;width:100%;min-height:44px}#study-plan-link{display:inline-block;min-height:44px;padding:8px 0}.bc-study-controls a{color:#9bd8f5}
</style></head>''')
    return text.encode()


def plan_index(report):
    esc = html.escape
    rows = []
    for o in report["options"]:
        for s in o["states"]:
            items = []
            for f in s["plans"]["floors"]:
                url = "index.html?scheme="+o["id"]+"&use="+s["id"]+"#mode=tour&building="+o["building"]+"&floor="+f["id"]+"&view=front"
                items.append('<li><a href="'+esc(url, quote=True)+'">'+esc(o["building"]+"棟 "+f["label"])+
                    ' 3D</a> · <a href="'+f["plan_file"]+'">同版平面與中文品名</a></li>')
            rows.append('<section><h2>'+esc(o["label"]+"／"+s["label"])+'</h2><ul>'+"".join(items)+'</ul></section>')
    return ('''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>A／C收納比較：平面與使用限制</title><style>body{font:16px/1.7 system-ui;max-width:1000px;margin:auto;padding:20px;color:#243d36;background:#f6f8f4}a{color:#075e79}li{margin:10px 0}.warning{padding:12px;background:#fff0cf}section{border-top:1px solid #b8cbbc;margin-top:20px}</style>
<h1>A／C同版上層收納比較</h1><p class="warning">未採用／新畫面待驗。只新增六件收納，不修改原房界、門窗、樓梯、空調與家具。B較新整層尚未同步，因此不放入本比較。</p>
<p>橙色是新增櫃體，可切「原配置／加櫃比較」、整層或櫃體特寫。尺寸為提案；門片、真實容量、完成面、照護與搬入取物未核。1F保留來源原配置，不默認套入其他續案。</p>
<p>C3取物須進主臥；RF只存耐候工具／備品，固定、防雨、防鏽、荷重與維修待核。A裝潢另與設計師討論；C唯一洗衣機仍在2F。</p>'''+"".join(rows)+
        '<p>本批來源：'+report["report_hash"]+'。本頁及3D均可離線開啟，沒有採購、連外或專業核可。</p></html>').encode()


def render(root, report):
    root = Path(root)
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    stored = copy.deepcopy(report)
    for o in stored["options"]:
        for s in o["states"]:
            s.pop("model")
    files = {"index.html": viewer_text(root, report), "plans.html": plan_index(report),
        "review.json": (json.dumps(stored, ensure_ascii=False, indent=2)+"\n").encode(),
        "LICENSE-three.txt": (root/"assets/vendor/three/LICENSE").read_bytes(),
        "README.md": ("# A／C同版收納3D比較\n\n解壓整包，開[index.html](index.html)，或[全部平面](plans.html)。不需WSL、Node、伺服器或網路。\n\n"
            "可切原配置／加櫃；六件橙色櫃體用既有房界與家具作比較。B不同版整層不混入。C3取物需進主臥；RF固定／防雨與商品待核。\n\n"
            "顯示第3版保留全部品名預設；側欄縮放與櫃體重取景在同一次更新完成，驗收等實際繪圖與視口相符後量測。重點模式的名稱勾選框維持停用。\n\n"
            "本版尚未瀏覽器／目視驗收，不沿用獨立收納檢視的passed；原主3D及其來源保持。\n").encode()}
    for option in report["options"]:
        for state in option["states"]:
            for floor in state["plans"]["floors"]:
                svg = c_floor_svg(option, state, floor) if option["building"] == "C" else kh.svg_plan(option, state, floor)
                for node in svg.iter():
                    if node.tag == "{http://www.w3.org/2000/svg}a":
                        for key in list(node.attrib):
                            if key.endswith("href"):
                                node.set(key, "index.html?scheme="+option["id"]+"&use="+state["id"]+"#mode=tour&building="+option["building"]+"&floor="+floor["id"]+"&view=front")
                files[floor["plan_file"]] = readable_svg(ET.tostring(svg, encoding="utf-8"))[0]
    files["artifact-manifest.json"] = (json.dumps({"schema": "house-ac-storage-preview-artifacts-v1",
        "report_hash": report["report_hash"], "source_hashes": report["source_hashes"], "rendered_qa": "not-run",
        "artifacts": {n: hashlib.sha256(data).hexdigest() for n, data in files.items()}}, ensure_ascii=False, indent=2)+"\n").encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 11, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    names = sorted(files)
    files[ARCHIVE] = stream.getvalue()
    files["archive-manifest.json"] = (json.dumps({"schema": "house-ac-storage-preview-archive-v1",
        "archive": ARCHIVE, "sha256": hashlib.sha256(files[ARCHIVE]).hexdigest(), "archive_contains": names}, indent=2)+"\n").encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files = render(ROOT, report)
        target = ROOT/OUT
        if args.check:
            if any(not (target/n).is_file() or (target/n).read_bytes() != data for n, data in files.items()):
                raise ContractError("A/C storage preview is stale")
        else:
            target.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (target/name).write_bytes(data)
        print(json.dumps({"status": "checked" if args.check else "exported", **report["summary"],
            "files": len(files), "zip_bytes": len(files[ARCHIVE]), "original_main_3d_changed": False,
            "browser": "not-run"}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

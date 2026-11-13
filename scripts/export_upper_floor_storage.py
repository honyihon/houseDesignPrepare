#!/usr/bin/env python3
"""Bounded static upper-floor storage plans with visible Chinese item legends."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import textwrap
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.upper_floor_storage import OUT, build  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_builder_communication import page  # noqa: E402


def sheet(report, case):
    entries = []
    for room in case["rooms"]:
        for item in room["items"]:
            if room["id"] == case["room"] and item["id"] == case.get("reuse_item"):
                continue
            entries.append((room, item))
    legends = [str(n)+"｜"+i["label"]+"｜平面"+"×".join(f"{v:g}" for v in i["rect_mm"][2:])+"mm"
        for n, (_, i) in enumerate(entries, 1)]
    legends += [i["label"] for i in case["fixed"]]
    lines = [line for value in legends for line in textwrap.wrap(value, 44)]
    height = max(1280, 390+len(lines)*25)
    root = ET.Element("svg", {"xmlns":"http://www.w3.org/2000/svg", "viewBox":f"0 0 1400 {height}",
        "width":"1400", "height":str(height), "role":"img", "aria-label":case["id"]+"儲藏與品名圖"})
    def add(tag, text=None, **kw):
        node=ET.SubElement(root, tag, {k.replace("_","-"):str(v) for k,v in kw.items()})
        node.text=text
        return node
    def text(value, x, y, size=16, **kw):
        return add("text",value,x=x,y=y,font_size=size,**kw)
    def point(p): return [55+p[0]*.052, 150+p[1]*.052]
    def drawbox(r, **kw):
        x,y=point(r)
        return add("rect",x=x,y=y,width=r[2]*.052,height=r[3]*.052,**kw)
    add("title",case["id"]+"｜"+case["label"])
    add("style","text{font-family:system-ui,sans-serif;fill:#263e49}")
    add("rect",x=0,y=0,width=1400,height=height,fill="#fafbf8")
    text(case["id"]+"｜"+case["label"],28,40,26,font_weight="700")
    text("橙色＝本輪儲藏櫃；橙虛線＝取物操作帶。編號對照名稱直接列在右側，不用滑鼠提示。",28,76)
    text("2D提案／未併主3D。房界、原家具、衣櫃與空調尺寸保留；完成面、門組、荷重及工程待核。",28,105)
    for room in case["rooms"]:
        pts=room["polygon_mm"]
        fill="#e4edf1" if room.get("kind") in {"wet","bath"} else "#e9eee3"
        add("polygon",points=" ".join(",".join(str(v) for v in point(p)) for p in pts),fill=fill,stroke="#688477",stroke_width="1")
        from shapely.geometry import Polygon
        centre=Polygon(pts).representative_point()
        name=room.get("label",room["id"]).split("（")[0]
        short={"quiet-living":"安靜起居", "dry-protection":"乾背保護", "front-entertainment":"KTV", "front-platform":"RF平台"}.get(room["id"],name[:7])
        text(short,*point([centre.x,centre.y]),11,text_anchor="middle")
        for d in room["doors"]:
            a,b=point(d["a"]),point(d["b"])
            add("line",x1=a[0],y1=a[1],x2=b[0],y2=b[1],stroke="#00a3bb",stroke_width="3")
        for window in room.get("windows_mm", []):
            a,b=point(window[:2]),point([window[0]+window[2],window[1]])
            add("line",x1=a[0],y1=a[1],x2=b[0],y2=b[1],stroke="#164fce",stroke_width="4")
    for fixed in case["fixed"]:
        drawbox(fixed["rect_mm"],fill="none",stroke="#7c8a92",stroke_width=".7",stroke_dasharray="3 2")
    for n,(_,item) in enumerate(entries,1):
        r=item["rect_mm"]
        drawbox(r,fill="#b8cabd",stroke="#446952",stroke_width=".7")
        text(str(n),*point([r[0]+r[2]/2,r[1]+r[3]/2]),11,text_anchor="middle")
    drawbox(case["operation_mm"],fill="none",stroke="#b75916",stroke_width="1.4",stroke_dasharray="4 3")
    drawbox(case["rect_mm"],fill="#f6bd69",stroke="#a74e19",stroke_width="1.6",data_storage_id=case["id"])
    r=case["rect_mm"]
    text("S1",*point([r[0]+r[2]/2,r[1]+r[3]/2]),11,text_anchor="middle")
    text("道路／前方 ↑",55,130)
    text("6000×17630mm研究框；不是可建量或地籍測量",55,1100,12)
    text("S1｜"+case["label"],430,155,21,font_weight="700")
    text("櫃體平面 "+"×".join(str(v) for v in case["rect_mm"][2:])+f"mm；高{case['height_mm']}mm（提案）",430,186)
    text(f"占地{case['review']['footprint_sqm']:.3f}㎡；額外占地{case['review']['additional_floor_footprint_sqm']:.3f}㎡",430,213)
    for n,line in enumerate(textwrap.wrap(case["note"],44)):
        text(line,430,244+n*25)
    text("現有家具／設備名稱對照",430,350,20,font_weight="700")
    for n,line in enumerate(lines):
        text(line,430,382+n*25,15)
    text("列明本體／操作／通路2D篩檢無新增衝突；不是全路線、門扇、真人、風水或施工核可。",28,height-70,14)
    text("來源與本批："+report["report_hash"],28,height-42,12)
    text("RF只放耐候用品，不新增室內房間；B折衣檯收納沿原操作帶分時，不解除原RF24㎡缺口。",28,height-18,13)
    return ET.tostring(root,encoding="unicode")+"\n"


def render(report):
    files={c["id"]+".svg":sheet(report,c) for c in report["cases"]}
    rows=[{"棟層版本":c["id"],"儲藏名稱":c["label"],"平面尺寸mm":"×".join(map(str,c["rect_mm"][2:])),
        "櫃高mm（提案）":c["height_mm"],"占地㎡":c["review"]["footprint_sqm"],"額外占地㎡":c["review"]["additional_floor_footprint_sqm"],
        "保留與代價":c["note"],"原操作帶共用":"／".join(c["review"]["shared_operation_ids"]+c["review"]["shared_route_ids"]),
        "完成面商品門組結構核對":"待資料","主3D同步":"未併入"} for c in report["cases"]]
    files["storage-schedule.csv"]=csv_text(rows)
    body='<h1>ABC 2F以上逐層儲藏與品名圖</h1><p class="note">依屋主新需求，每棟2F／3F及RF各有獨立儲藏提案。10張圖涵蓋9個棟層，B RF兩案不相加；不扣原衣櫃容量，不新增屋頂房間。主3D尚未加入本輪櫃體。</p>'
    body+='<p>數字／機號不能只靠滑鼠提示：各圖右側都有名稱對照。S1是新雜物櫃；灰虛線為原預留、橙虛線為新取物帶。既有圖內家電只代表尺寸，未因此選型或增加台數。</p>'
    body+='<div class="table">'+table(list(rows[0]),[list(r.values()) for r in rows])+"</div>"
    for c in report["cases"]:
        name=c["id"]+".svg"
        body+='<section id="'+c["id"]+'"><h2>'+html.escape(c["id"]+"｜"+c["label"])+"</h2><p>"+html.escape(c["note"])+"</p>"
        body+='<p><a href="'+name+'">開啟完整向量圖與中文圖例</a></p><img style="width:100%;height:auto" src="'+name+'" alt="'+html.escape(c["id"]+c["label"],quote=True)+'"></section>'
    body+='<p>本批只篩列明2D房界、原本體／操作、預留及既有試線；實際門活動、結構防水荷重、櫃內有效容量、全程取物／搬入及高處取物仍待核。C3公共取物會進主臥，B取物須維持安靜乾燥，RF防雨櫃不存棉被及怕潮物品。</p>'
    body+='<p><a href="storage-schedule.csv">逐層櫃表</a>／<a href="review.json">來源與篩檢</a>／<a href="../../../Docs/abc-upper-floor-storage-v1.md">說明</a></p>'
    files["index.html"]=page("ABC逐層儲藏與中文品名",body)
    files["review.json"]=json.dumps(report,ensure_ascii=False,indent=2)+"\n"
    files["artifact-manifest.json"]=json.dumps({"schema":"house-upper-floor-storage-artifacts-v1","report_hash":report["report_hash"],
        "source_hashes":report["source_hashes"],"artifacts":{n:hashlib.sha256(v.encode()).hexdigest() for n,v in files.items()}},ensure_ascii=False,indent=2)+"\n"
    return files


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    try:
        report=build(ROOT)
        files=render(report)
        target=ROOT/OUT
        if args.check:
            if any(not (target/n).is_file() or (target/n).read_text()!=v for n,v in files.items()):
                raise ValueError("Storage study is stale")
        else:
            target.mkdir(parents=True,exist_ok=True)
            for n,v in files.items():
                (target/n).write_text(v,encoding="utf-8")
        print(json.dumps({"status":"checked" if args.check else "exported","floors":9,"cases":len(report["cases"]),
            "files":len(files),"controls":report["protected_controls_unchanged"],"primary_3d_changed":False,"browser":"not-run"}))
        return 0
    except (OSError,ValueError,KeyError,StopIteration) as exc:
        print(str(exc),file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

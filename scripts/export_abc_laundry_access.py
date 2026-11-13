#!/usr/bin/env python3
"""Export three bounded laundry access SVGs; no scenes, browser or original-plan writes."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.abc_laundry_access import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_upper_replan import Draw  # noqa: E402
from scripts.export_b_upper_replan import Sheet as BaseSheet  # noqa: E402
from scripts.export_builder_communication import page, ul  # noqa: E402


class Sheet(BaseSheet):
    def __init__(self, title, report):
        self.root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": "0 0 1400 1200",
            "width": "1400", "height": "1200", "role": "img", "aria-label": title})
        self.add("title", text=title)
        self.add("style", text="text{font:17px system-ui,sans-serif;fill:#263e49}.title{font-size:26px;font-weight:700}.small{font-size:13px}.room{font-size:15px;font-weight:650}")
        self.add("rect", x=0, y=0, width=1400, height=1200, fill="#fafbf8")
        self.text(title, 28, 40, class_="title")
        self.text("獨立到達研究／未採用｜mm座標；只核固定房界反例與基地內試線，未核門外動線、實際門組或照護。", 28, 78)
        self.text("三棟共用一組；C2暫不用保空間、A2以上另留機位。A原室內分區及洗衣設備備位保留。", 28, 106)
        self.text("本批 "+report["report_hash"], 28, 1157, class_="small")
        self.text("原3D與已驗ZIP不改；無新瀏覽器／WebGL或專業驗收。圖上空白與模型餘量不能當實測或商品安全距離。", 28, 1183, class_="small")


class LocalDraw(Draw):
    def __init__(self, sheet, origin, scale, y0):
        super().__init__(sheet, origin, scale)
        self.y0 = y0

    def point(self, p):
        return super().point([p[0], p[1]-self.y0])


def geometry(d, value, **attrs):
    geom = shape(value)
    parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    paths = []
    for part in parts:
        for ring in [part.exterior, *part.interiors]:
            paths.append("M"+" L".join(",".join(str(round(v, 3)) for v in d.point(p)) for p in ring.coords)+" Z")
    d.s.add("path", d=" ".join(paths), fill_rule="evenodd", **attrs)


def front_sheet(report):
    s = Sheet("A前側入口｜斜向門長不能代替真正通行寬", report)
    data = report["front_entry_screen"]
    d = LocalDraw(s, (45, 170), .1, 9800)
    labels = {"mdf": "MDF維修備援保留", "rear-hall1": "公共乾區", "kitchen": "廚房原範圍", "flex1": "孝親房保留"}
    for room in data["rooms"]:
        d.box(room["rect_mm"], fill="#e6ece2" if room["id"] != "flex1" else "#f0e4c8", stroke="#799184")
        x, y, w, h = room["rect_mm"]
        s.text(labels[room["id"]], *d.point([x+w/2, y+h/2]), text_anchor="middle", class_="small")
    geometry(d, data["finished_free_floor"], fill="#fff", fill_opacity=.7, stroke="#538a91", stroke_width=1)
    geometry(d, data["circular_body_center_domain"], fill="#93bdd9", fill_opacity=.6, stroke="#367c9c", stroke_width=1)
    d.poly(data["triangle_mm"], fill="#f3b66c", fill_opacity=.7, stroke="#a3692b", stroke_dasharray="5 3")
    for key, label in [("hall", "乾區試點"), ("kitchen", "廚房試點")]:
        x, y = d.point(data["probes_mm"][key])
        s.add("circle", cx=x, cy=y, r=5, fill="#27536b")
        s.text(label, x+12, y-10, class_="small")
    s.text("上方接原公共區；藍色是900圓形本體中心可行域", 45, 810)
    s.text("只畫完成預算邊界，特意忽略廚具與門片，仍不相通", 45, 839)
    y = 170
    for text in ["現況公共乾區與廚房只共1040mm名義邊；每側先留115mm完成預算，最樂觀只餘810mm。",
        "原900mm名義門扣總框230mm，只能先估670mm；不是900mm實際通行。",
        "橙色三角區重分給廚房，斜邊約1254mm、移標面積0.364㎡。但公共區與廚房的合併地面完全沒增加。",
        "900圓形本體的中心可行域分成兩塊，兩個試點各在不同塊。斜門較長不能作為角落已可轉過的證據。",
        "本反例只否決這種固定房界的門長算法。要保前側自行操作，須連入口、相鄰分區及MDF完整維修一起重新排，不代表所有前側方案都無解。"]:
        y = s.paragraph(text, 720, y, width=36, step=25)
    y = 900
    for text in ["本輪不改廚房、孝親房、照護通道或MDF，也不把未核成的梯下機房當成已可釋出。",
        "前門備案：家人／照服以分戶小籃或推車平層取送，長輩不提濕衣上樓。這只是協助流程，原前門全程通路仍未核。",
        "若要求三棟長輩都能完全自行抵達，而合法後路或前側完整重排都不成立，就回到共享位置比較，不硬塞此廚房。"]:
        y = s.paragraph(text, 45, y, width=73, step=24)
    return s.output()


BODY_NAMES = {"shared-washer-bay": "共用洗衣備位", "optional-dryer-bay": "可選乾衣備位",
    "lowered-drying-envelope": "降下晾衣外廓"}


def balcony(d, data, labels=True):
    for r in data["patio_rects_mm"]:
        d.box(r, fill="#edf0e9", stroke="#6b8779", stroke_width=1)
    for item in data["fixed"]:
        label = "原廚房門前" if item["kind"] == "door-approach" else "冷氣維修" if item["kind"] == "hvac-service" else "原淨軟水"
        d.box(item["rect_mm"], fill="none" if item["kind"] == "door-approach" else "#c9d5ce",
            stroke="#738577", stroke_dasharray="5 3", stroke_width=1)
        if labels:
            x, y, w, h = item["rect_mm"]
            d.s.text(label, *d.point([x+w/2, y+h/2]), text_anchor="middle", class_="small")
    for item in data["bodies"]:
        d.box(item["rect_mm"], fill="#cce5c4" if item["id"] == "lowered-drying-envelope" else "#f2b668", stroke="#986a36")
        if labels:
            x, y, w, h = item["rect_mm"]
            d.s.text(BODY_NAMES[item["id"]], *d.point([x+w/2, y+h/2]), text_anchor="middle", class_="small")
    for item in data["operations"]:
        d.box(item["rect_mm"], fill="none", stroke="#a86e39", stroke_dasharray="6 4")


def rear_sheet(report):
    s = Sheet("A後側候選｜直入共用洗衣陽台，外側通路待確認", report)
    data = report["rear_entry_screen"]
    d = LocalDraw(s, (65, 190), .19, 15600)
    balcony(d, data)
    geometry(d, data["scoped_route"], fill="#9dc9e2", fill_opacity=.45, stroke="#367c9c", stroke_dasharray="6 3")
    geometry(d, data["outside_route"], fill="#e6d9f0", fill_opacity=.6, stroke="#886c9b", stroke_dasharray="6 4")
    d.box(data["travel_envelope_rect_mm"], fill="none", stroke="#a54c37", stroke_dasharray="5 3", stroke_width=1.5)
    d.box(data["states"][0]["leaf_rect_mm"], fill="#b99374", stroke="#67472e", stroke_width=1.2)
    d.line(*report["config"]["rear_gate"]["opening_mm"], stroke="#2f86a0", stroke_width=3)
    s.text("後門名義1200 → 扣總框230預算970；藍色只核基地內900試線", 65, 160)
    s.text("棕色：全開門板；紅虛線：完整滑動包絡。移動時人與推車退出行程。", 65, 755)
    y = 820
    for text in ["紫色門外引線是未建模範圍，不表示共同後巷已連通；A／C合法接入、轉向、高差、雨棚及防滑都待資料。B有後巷不能推定A也能開門。",
        "陽台與原室內分區不減，衣物取送可在後口成立時避開A廚房及室內私領域。試線與洗／乾操作帶重疊，須先到達停妥再操作，不能同時穿越。",
        "門片包絡到乾衣備位20mm、到衣物外廓70mm，僅模型餘量。產品五金、接管、風雨、防盜、消防及平門檻／排水需同版核，未選門或機型。",
        "原小晾架容量、降下占1500轉位、設備完成面／完整維修、噪音振動與雨天排濕仍待核；新增後口不會自動解決。"]:
        y = s.paragraph(text, 45, y, width=73, step=24)
    return s.output()


def states_sheet(report):
    s = Sheet("後門三態｜只有全開的基地內試線局部不碰", report)
    data = report["rear_entry_screen"]
    for n, state in enumerate(data["states"]):
        origin = (35+n*455, 220)
        d = LocalDraw(s, origin, .07, 15600)
        s.text(state["label"]+"｜"+("局部試線不碰門板" if not state["scoped_route_blocked"] else "900試線被門板阻擋"), origin[0], 165, class_="room")
        balcony(d, data, labels=False)
        geometry(d, data["scoped_route"], fill="#9dc9e2", fill_opacity=.5, stroke="#367c9c")
        geometry(d, data["outside_route"], fill="none", stroke="#886c9b", stroke_dasharray="4 3")
        d.box(data["travel_envelope_rect_mm"], fill="none", stroke="#a54c37", stroke_dasharray="4 3")
        d.box(state["leaf_rect_mm"], fill="#b99374", stroke="#67472e", stroke_width=1.5)
        s.text("門板與試線重疊："+str(state["scoped_route_leaf_overlap_sqm"])+"㎡", origin[0], 465, class_="small")
    y = 545
    for text in ["三態使用同一片1260×95mm概念門板：全開停左，半開與關閉會阻斷900試線。不是只憑名義開口1200mm宣稱三態都可通行。",
        "本體名稱：橙色上方是共用洗衣備位，橙色下方是可選乾衣備位，綠色是降下晾衣含衣物外廓，灰色是原淨軟水與冷氣維修。細框是原廚房門前，虛線是取放操作帶。",
        "灰／橙／綠的原安裝備位均不改。全開門板到試線側緣180mm；平移包絡到乾衣機備位20mm、到降下衣物70mm，均不是實品安全或維修距離。",
        "先開到定位→人／推車進入→停妥並離開行程→再關門。門在移動時不得與通行同時安排；停電手開、操作力、可及高度與緊急釋放仍未知。",
        "上吊、地面無突出軌道只作討論目標，並非已證無門檻。門外地坪、遮雨、止水與排水不能拿室內900試線代替。",
        "前側協助取送備案保留；若後路不成立且要長輩自行使用，再做A入口／共享位置的整體重排。沒有藉此縮孝親房、把MDF移走或宣稱全程照護可達。"]:
        y = s.paragraph(text, 45, y, width=73, step=26)
    return s.output()


def render(report):
    files = {"front-entry-screen.svg": front_sheet(report), "rear-entry-conditional.svg": rear_sheet(report),
        "rear-door-states.svg": states_sheet(report)}
    files["actual-conditions-template.json"] = json.dumps(report["actual_conditions"], ensure_ascii=False, indent=2)+"\n"
    files["actual-conditions.csv"] = csv_text([{"欄位": key, "實際值": "", "單位口徑及圖號版次": "", "來源或產品文件": ""}
        for key in report["actual_conditions"]])
    body = '<h1>共用洗衣到達：前側瓶頸與條件式後口</h1><p class="note">獨立研究／未採用。三棟一樓共用一組、C2先暫不用保空間、A上層另留機位。沒有選定A為正式共用位置，原室內分區、洗衣預留與已驗3D不改。</p>'
    body += "<p>"+html.escape(report["recommendation"])+"</p>"
    body += '<p>斜門候選的三角區重分沒有增加可走地面；1040mm共邊扣兩側115mm只剩810mm，900圓形本體中心無法連通。這否決該斜門算法，沒有宣稱所有前側重排無解。</p>'
    body += '<p>後口全開時，900試線在基地內可避列明本體；門外0.63㎡試線未核。洗／乾操作仍共用，須分時。A後口與共同後路尚無權利、高差及遮雨依據，不能當全程長輩自行可達。</p>'
    for name, title in [("front-entry-screen.svg", "前側固定房界反例"),
            ("rear-entry-conditional.svg", "條件式後口與原陽台"), ("rear-door-states.svg", "同門全開／半開／關閉")]:
        body += '<section><h2>'+title+f'</h2><p><a href="{name}">開向量圖</a></p><img style="width:100%;height:auto" src="{name}" alt="'+title+'"></section>'
    body += '<h2>三態核算</h2>'+table(["狀態", "與900試線重疊㎡", "本輪結果", "完整通路"],
        [[r["label"], r["scoped_route_leaf_overlap_sqm"], "阻擋" if r["scoped_route_blocked"] else "基地內局部不碰", "未核"]
            for r in report["rear_entry_screen"]["states"]])
    body += '<h2>與建商／A設計師先核</h2>'+ul(report["config"]["limits"])
    body += '<p>回饋繼續用原生活走查ABC-DAILY-CHAIN及建商動線問題列；沒有新增一套必填程序。下列'+str(len(report["actual_conditions"]))+'欄實際條件全空，另存私人副本後按圖號、版次與依據填寫；不自動套圖。</p>'
    body += '<p>'+"／".join(f'<a href="{name}">{html.escape(name)}</a>' for name in
        ["actual-conditions-template.json", "actual-conditions.csv", "review.json", "artifact-manifest.json"])+"</p>"
    body += '<p><a href="../abc-ground-laundry-v1/index.html">上一批三棟位置比較與A洗曬配置</a>／<a href="../../planning/design-discussion-basis/life-walkthrough.html#laundry-access">既有討論包的洗衣到達章節</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；15項父來源逐一核對，靜態幾何不是商品、使用或專業核可。</small>'
    files["index.html"] = page("ABC共用洗衣到達研究", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-abc-laundry-access-artifacts-v1",
        "report_hash": report["report_hash"], "source_hashes": report["source_hashes"], "adopted": False,
        "artifacts": {n: hashlib.sha256(text.encode()).hexdigest() for n, text in files.items()}}, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files, out = render(report), ROOT/OUT
        if args.check:
            stale = [n for n, value in files.items() if not (out/n).is_file() or (out/n).read_bytes() != value.encode()]
            if stale:
                raise ContractError("Laundry access outputs stale: "+", ".join(stale))
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, value in files.items():
                (out/name).write_text(value, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "files": len(files), "drawings": 3,
            "rear_door_states": 3, "parent_sources": report["parent_sources_verified"],
            "actual_conditions": len(report["actual_conditions"]), "protected_controls": report["protected_controls_unchanged"],
            "front_counterexample_connected": report["front_entry_screen"]["probes_connected"],
            "whole_route_approved": False, "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

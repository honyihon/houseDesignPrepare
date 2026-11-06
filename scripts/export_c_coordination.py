#!/usr/bin/env python3
"""Bounded C concept coordination sheets; never rebuild a scene or start a browser."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.c_coordination import OUT, build, unit_box  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402

NS = "http://www.w3.org/2000/svg"
LABELS = {"nominal-no-conflict": "列明幾何未見重疊", "interface-pending": "介面待調整／確認",
    "unknown": "缺資料待核", "sensitivity-conflict": "敏感度出現不足"}


class Sheet:
    def __init__(self, title, report, height=1300, width=1200):
        self.width, self.height = width, height
        self.root = ET.Element(f"{{{NS}}}svg", {"viewBox": f"0 0 {width} {height}",
            "width": str(width), "height": str(height), "role": "img", "aria-labelledby": "title desc"})
        self.add("title", title, id="title")
        self.add("desc", "C概念套繪，尺寸mm，共同座標未實測。結構與排水終端缺資料，禁止據此鑽孔施工。", id="desc")
        self.add("style", "text{font-family:system-ui,sans-serif;fill:#253c47;font-size:17px} .title{font-size:25px;font-weight:700} .small{font-size:13px} .label{font-size:14px;font-weight:650} .pipe{fill:none;stroke:#216f91;stroke-width:3} .pending{fill:#9c5424}")
        self.add("rect", x=0, y=0, width=width, height=height, fill="#f8faf8")
        self.text(title, 30, 43, class_="title")
        self.text("概念合圖／未核施工｜x向右、y向屋後、z向上；mm；道路在平面上方。", 30, 80)
        self.text("建築與機電：現有配置　　結構：尚無正式圖　　排水：只有待核方向／終端未定", 30, 111)
        self.text("來源 "+report["source_layout_report_sha256"][:20]+"…｜合圖 "+report["report_hash"][:16]+"…", 30, height-54, class_="small")
        self.text("梁板、完成面、穿孔、機型、樹冠及實際淨空待合圖；所有尺寸為來源模型或明列假設。", 30, height-28, class_="small")
        self.add("metadata", json.dumps({"source_report_sha256": report["source_layout_report_sha256"],
            "coordination_report_hash": report["report_hash"], "status": report["status"], "construction_ready": False}, separators=(",", ":")),
            data_coordination_metadata="1")

    def add(self, tag, content=None, parent=None, **attrs):
        node = ET.SubElement(self.root if parent is None else parent, f"{{{NS}}}"+tag,
            {k.rstrip("_").replace("_", "-"): str(v) for k, v in attrs.items()})
        node.text = content
        return node

    def text(self, value, x, y, **attrs):
        return self.add("text", value, x=x, y=y, **attrs)

    def lines(self, values, x, y, step=29, **attrs):
        for n, value in enumerate(values):
            self.text(value, x, y+n*step, **attrs)

    def box(self, r, **attrs):
        return self.add("rect", x=r[0], y=r[1], width=r[2], height=r[3], **attrs)

    def line(self, a, b, **attrs):
        return self.add("line", x1=a[0], y1=a[1], x2=b[0], y2=b[1], **attrs)

    def pin(self, label, x, y, color="#a85b23"):
        self.add("circle", cx=x, cy=y, r=6, fill=color, stroke="white", stroke_width=2)
        self.text(label, x+10, y-7, class_="label", fill=color)

    def output(self):
        return ET.tostring(self.root, encoding="unicode")+"\n"


def finding(report, oid):
    return next(i for i in report["findings"] if i["id"] == oid)


def gate_walls(gate):
    x, y, w, d = gate["wall_budgets_mm"][0]
    lo, hi = gate["opening_x_mm"]
    return [[x, y, lo-x, d], [hi, y, x+w-hi, d], gate["wall_budgets_mm"][1]]


def front_plan(report, fid):
    floor = next(f for f in report["plans"]["floors"] if f["id"] == fid)
    s = Sheet("C合圖 D01｜一樓建築／冷氣／排水" if fid == "floor-1" else "C合圖 D02｜二樓家務／景觀／立管", report)
    ox, oy, scale, depth = 45, 190, .08, 9200
    s.text(f"{floor['label']}｜基準 +{floor['base_mm']:g}mm；前段套繪", ox, 158)
    s.text("平面取至y=9200；其後樓梯／孝親空間見D04及原平面。", 580, 158, class_="small")
    defs = s.add("defs")
    clip = s.add("clipPath", parent=defs, id="front-clip")
    s.add("rect", parent=clip, x=ox, y=oy, width=6000*scale, height=depth*scale)
    group = s.add("g", clip_path="url(#front-clip)")

    def rect(r, **attrs):
        return s.box([ox+r[0]*scale, oy+r[1]*scale, r[2]*scale, r[3]*scale], parent=group, **attrs)

    def line(a, b, **attrs):
        return s.line([ox+a[0]*scale, oy+a[1]*scale], [ox+b[0]*scale, oy+b[1]*scale], parent=group, **attrs)

    visible = [r for r in floor["rooms"] if r["geometry"]["y_mm"] < depth]
    for n, room in enumerate(visible, 1):
        g = room["geometry"]
        r = [g["x_mm"], g["y_mm"], g["w_mm"], g["h_mm"]]
        rect(r, fill="#efe8ce" if room["outdoor"] else "#edf2ed", stroke="#96a7a5", stroke_width=1)
        s.text(str(n), ox+(r[0]+100)*scale, oy+min(r[1]+290, depth-100)*scale, parent=group, class_="label")
        feat = room["features"]
        if feat.get("kaohsiung_zones"):
            zone = feat["kaohsiung_zones"]
            rect(zone["garden_mm"], fill="#dcebd5", fill_opacity=.7, stroke="#608c5b", stroke_dasharray="5 3")
            for soil in zone["soil_rects_mm"]:
                rect(soil, fill="#bfd5b6", stroke="#6e8e67")
            for k, (x, y) in enumerate(zone["woody_points_mm"], 1):
                s.add("circle", parent=group, cx=ox+x*scale, cy=oy+y*scale, r=6, fill="#4b754a")
                s.text("T"+str(k), ox+(x-110)*scale, oy+(y-200)*scale, parent=group, class_="small")
        for item in room["furniture"]:
            p = item["placement"]
            if p["issues"]:
                continue
            b = p["aabb"]
            rect([b["minX"], b["minY"], b["maxX"]-b["minX"], b["maxY"]-b["minY"]], fill="#c7cecb", stroke="#8b9894")
            if p.get("operation_mm"):
                b = p["operation_mm"]
                rect([b["minX"], b["minY"], b["maxX"]-b["minX"], b["maxY"]-b["minY"]], fill="none", stroke="#bc9858", stroke_width=1, stroke_dasharray="4 3")
        for door in feat["doors"]:
            face, width = door["face"], door["width_mm"]
            if face in {"front", "rear"}:
                mid, y = r[0]+r[2]*door["ratio"], r[1]+(r[3] if face == "rear" else 0)
                a, b = [mid-width/2, y], [mid+width/2, y]
            else:
                mid, x = r[1]+r[3]*door["ratio"], r[0]+(r[2] if face == "right" else 0)
                a, b = [x, mid-width/2], [x, mid+width/2]
            line(a, b, stroke="#39786a", stroke_width=4)
        if feat.get("window_review", {}).get("renderable") and feat["window_face"] in {"front", "rear"}:
            mid = r[0]+r[2]*feat["window_ratio"]
            y = r[1]+(r[3] if feat["window_face"] == "rear" else 0)
            line([mid-feat["window_mm"]/2, y], [mid+feat["window_mm"]/2, y], stroke="#5b8da3", stroke_width=5)
        for unit in feat.get("hvac_units", []):
            b = unit_box(unit, floor["base_mm"])
            rect([b[0], b[1], b[3]-b[0], b[4]-b[1]], fill="#81abbc", stroke="#466e85")
        for res in feat.get("fixed_reserved_mm", []):
            if res["kind"] == "hvac-service":
                b = res["aabb"]
                rect([b["minX"], b["minY"], b["maxX"]-b["minX"], b["maxY"]-b["minY"]], fill="none", stroke="#bc9858", stroke_dasharray="4 3")
        gate = feat.get("c_front_gate")
        if gate:
            for rwall in gate_walls(gate):
                rect(rwall, fill="#6c8078", fill_opacity=.6)
            rect(gate["closed_leaf_rect_mm"], fill="none", stroke="#947749", stroke_dasharray="4 3")
    points = report["ac01"]["route"]["polyline_mm"]
    pp = points[:4] if fid == "floor-1" else points[4:]
    s.add("polyline", parent=group, points=" ".join(f"{ox+p[0]*scale},{oy+p[1]*scale}" for p in pp), class_="pipe")
    box = report["ac01"]["riser_envelope_mm"]
    rect([box[0], box[1], box[3]-box[0], box[4]-box[1]], fill="#e5c397", stroke="#a56d28", stroke_width=2)
    for p in report["penetrations"]:
        if (fid == "floor-1" and p["id"] != "P03") or (fid == "floor-2" and p["id"] != "P01"):
            s.pin(p["id"], ox+p["center_mm"][0]*scale, oy+p["center_mm"][1]*scale)
    if fid == "floor-1":
        a, b = report["drainage"]["stub_plan_mm"]
        line(a, b, stroke="#985d9e", stroke_width=3, stroke_dasharray="6 4")
        s.pin("D01", ox+b[0]*scale, oy+b[1]*scale, "#985d9e")
        notes = ["P01：隔牆穿越 x4450、y5700、z3500。", "投影落公衛門範圍上方，須核門楣。",
            "P02：穿2F樓板 x4450、y5000、z4000。", "150管束／200立管帶均為預算，孔徑未定。",
            "室內機：乾式前室右壁；底+2350。", "機身與前置牆已避開；維修／送風待選型。",
            "D01：紫線只到公衛後界，非完整排水線。", "800mm敏感度：1／1.5／2%→8／12／16mm。",
            "冷凝水不隨冷媒升到二樓，接管點未知。", "污水、雨水、冷凝水及排氣須分別設計。"]
    else:
        notes = ["P02：200×200立管候選占0.04㎡。", "到原沙發投影：Y向460、X向470mm。",
            "P03：x4450、y3900、z6350，前牆穿出。", "150包束到名義窗／門：175／225mm。",
            "冷媒高位線投影近第3株T3中心20mm。", "成熟冠幅及固定面未定，須同步調整。",
            "洗衣機一台、原洗槽、240cm晾衣架保留。", "3台室外機原機位保留，散熱需原廠圖。",
            "家具／設備灰藍塊為原尺寸投影。", "橘虛框：操作或維修預算，非通行證明。"]
    s.lines(notes, 580, 210, step=37)
    s.text("平面索引（數字只定位，不另算房間面積）", 580, 645, class_="label")
    for n, room in enumerate(visible, 1):
        name = room["name"].split("（")[0]
        s.text(f"{n}　{name[:25]}", 580, 680+n*28, class_="small")
    s.lines(["藍線：冷媒中心線投影，並非地面管線。", "橘實框：未核立管協調帶；綠線：名義門洞。",
        "細分區線非施工牆；結構梁柱未提供。", "完整後段、照護動線及屋頂工程另待整棟合圖。"], 45, 1020, step=38)
    s.line([ox, oy+depth*scale], [ox+6000*scale, oy+depth*scale], stroke="#7e938b", stroke_dasharray="5 3")
    s.text("y=9200截斷；後段續D04及原整層圖。", ox, oy+depth*scale+32, class_="small")
    return s.output()


def section_sheet(report):
    s = Sheet("C合圖 D03｜穿孔、樓高、門窗與降板", report, height=1200, width=1300)
    s.text("A｜y-z投影：X向折線省略；水平／垂直比例不同", 35, 154, class_="label")
    ox, oy, sy, sz = 45, 730, .075, .064
    def proj(p):
        return [ox+p[1]*sy, oy-p[2]*sz]
    for z, label in [(0, "1F模型基準"), (3500, "3500協調線"), (4000, "2F +4000"), (7000, "3F +7000")]:
        y = oy-z*sz
        s.line([ox, y], [730, y], stroke="#a3afad", stroke_dasharray="5 4")
        s.text(label, ox, y-8, class_="small")
    s.box([ox, oy-3500*sz, 3900*sy, 3500*sz], fill="#f2e6c1", fill_opacity=.55)
    s.add("polyline", points=" ".join(",".join(map(str, proj(p))) for p in report["ac01"]["route"]["polyline_mm"]), class_="pipe")
    for p in report["penetrations"]:
        x, y = proj(p["center_mm"])
        s.pin(p["id"], x, y)
    s.text("騎樓投影", 110, 710)
    s.text("樓層線只標基準，沒有假設梁底。", 35, 790, class_="small")
    s.text("B｜2F前牆立面局部（名義開口）", 780, 154, class_="label")
    openings = report["openings"]
    xx, zz = lambda x: 790+(x-2800)*.14, lambda z: 635-(z-4000)*.14
    s.box([xx(2800), zz(7000), 3200*.14, 3000*.14], fill="#edf1ed", stroke="#889b93")
    s.box([xx(openings["window_x_mm"][0]), zz(openings["window_top_z_mm"]),
        (openings["window_x_mm"][1]-openings["window_x_mm"][0])*.14,
        (openings["window_top_z_mm"]-openings["window_bottom_z_mm"])*.14], fill="#b9d6e1", stroke="#597d8b")
    s.box([xx(openings["door_x_mm"][0]), zz(openings["door_top_illustrative_z_mm"]),
        (openings["door_x_mm"][1]-openings["door_x_mm"][0])*.14, 2100*.14], fill="#d6d6bf", stroke="#69806b")
    p = next(p for p in report["penetrations"] if p["id"] == "P03")
    s.box([xx(p["bundle_box_mm"][0]), zz(p["bundle_box_mm"][5]), 150*.14, 150*.14], fill="#c8914e", stroke="#87602f")
    s.pin("P03", xx(p["center_mm"][0]), zz(p["center_mm"][2]))
    s.lines(["窗：x3000～4200；門：4750～5650。", "包束到窗／門側175／225mm。", "包束下緣+6275，名義窗頂+6100。",
        "包束上緣+6425，到3F基準餘575mm。", "575mm包含尚未知的板、梁、天花等。", "門高2100是展示預算，非選定門組。"], 780, 685, step=29, class_="small")
    s.text("C｜景觀土層／板與騎樓高度敏感度", 35, 856, class_="label")
    s.text("假設土面+4000、板150、其他50；地面高程及梁深未知，未選土深。", 35, 888)
    for n, case in enumerate(report["soil_cases"]):
        y = 930+n*47
        s.text(f"土{case['soil_mm']:g}mm → 名義底+{case['illustrative_underside_z_mm']:g}mm；對3500協調線餘{case['margin_to_target_mm']:+g}mm", 50, y)
    s.text("土300案例零餘量，不能視為剖面成立；3500是協調目標，適用法規與測量基準另核。", 35, 1080, class_="small")
    return s.output()


def stair_sheet(report):
    s = Sheet("C合圖 D04｜樓梯、前置門與機電保留區", report, height=1200)
    s.text("1F：24級／踏面270", 45, 160, class_="label")
    s.text("2F：到達面分開、側門待選型", 635, 160, class_="label")
    for fid, ox in [("floor-1", 50), ("floor-2", 640)]:
        f = next(f for f in report["plans"]["floors"] if f["id"] == fid)
        stair = next(r for r in f["rooms"] if r["features"].get("c_stair_surfaces"))
        scale, oy = .09, 200

        def rect(area, _ox=ox, _scale=scale, _oy=oy, **attrs):
            return s.box([_ox+(area[0]-2300)*_scale, _oy+(area[1]-7400)*_scale, area[2]*_scale, area[3]*_scale], **attrs)

        g = stair["geometry"]
        rect([g["x_mm"], g["y_mm"], g["w_mm"], g["h_mm"]], fill="none", stroke="#7e938b", stroke_width=2)
        for surface in stair["features"]["c_stair_surfaces"]:
            rect(surface["rect_mm"], fill="#abc8b4" if surface["kind"] != "tread" else "#c3d3dc", stroke="#7b9697")
        gate = stair["features"]["c_front_gate"]
        for wall in gate_walls(gate):
            rect(wall, fill="#6c8078")
        for approach in gate["approach_rectangles_mm"].values():
            rect(approach, fill="none", stroke="#b6894e", stroke_width=2, stroke_dasharray="5 4")
        rect(gate["closed_leaf_rect_mm"], fill="#bbab88", stroke="#846f4d")
        rect(gate["parking_rect_mm"], fill="none", stroke="#846f4d", stroke_dasharray="5 4")
        rect(report["stair_detail"]["shared_level_apron_mm"], fill="none", stroke="#2c735b", stroke_width=3)
        if fid == "floor-2":
            rect(report["stair_detail"]["second_floor_floor_level_platform_removed_mm"], fill="none", stroke="#aa5650", stroke_width=2, stroke_dasharray="4 3")
            side = stair["features"]["c_side_gate"]
            rect(side["closed_rect_mm"], fill="#9da68f", stroke="#657860")
        s.lines(["門線y=8550；名義前門1200。", "實框關門／虛框停放；非同時兩扇。", "完整共享平台1000，前室借地200。", "門片內側到首級1060；到平台餘60。"], ox, 825, step=32)
    s.text("二樓紅虛線0.324㎡範圍須避開舊整片平台，實際洞口、梁邊及護欄由結構合圖。", 35, 995)
    s.text("本次AC01立管在y=5000，沒有移入本區；包管／支架不得事後侵占門前或完整平台。", 35, 1032)
    s.text("前門1200／側門900為名義洞口；實際淨寬、門組、扶手、全寬淨高及消防均待核。", 35, 1069)
    return s.output()


def csv_text(report, penetrations=False):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    if penetrations:
        writer.writerow(["id", "位置", "中心x_mm", "中心y_mm", "中心z_mm", "管束預算_mm", "實際孔徑_mm", "套管", "結構查核", "圖號與回覆"])
        for p in report["penetrations"]:
            writer.writerow([p["id"], p["title"], *p["center_mm"], p["pipe_bundle_budget_mm"], "", "", "待核", ""])
    else:
        writer.writerow(["id", "項目", "概念檢查", "負責", "需回覆內容", "現有依據與限制", "實際回覆", "圖號與版本"])
        for i in report["findings"]:
            writer.writerow([i["id"], i["title"], LABELS[i["status"]], i["responsible"], i["required_reply"], i["scope"], "", ""])
    return "\ufeff"+stream.getvalue()


def render_index(report):
    esc = html.escape
    rows = "".join(f'<tr><td>{esc(i["id"])}</td><td>{esc(i["title"])}</td><td>{esc(LABELS[i["status"]])}</td>'
        f'<td>{esc(i["responsible"])}</td><td>{esc(i["required_reply"])}<br><small>{esc(i["scope"])}</small></td></tr>' for i in report["findings"])
    images = "".join(f'<section id="{name}"><h2>{title}</h2><p><a href="{name}.svg">另開原圖放大／列印</a></p>'
        f'<img src="{name}.svg" alt="{title}：概念套繪，梁板、穿孔及排水待核"></section>' for name, title in [
            ("D01-floor-1", "D01 一樓建築、冷媒與冷凝水"), ("D02-floor-2", "D02 二樓家務、景觀與立管"),
            ("D03-sections", "D03 穿孔、門窗與降板"), ("D04-stair-doors", "D04 樓梯、門組與保留區")])
    return ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>C棟概念合圖｜建築、樓梯、空調與排水</title><style>'
        'body{font-family:system-ui,sans-serif;color:#243c43;background:#f6f9f6;margin:0;line-height:1.8}main{max-width:1240px;margin:auto;padding:24px}'
        'a{color:#226c7d}h1{line-height:1.4}section{margin:36px 0;border-top:1px solid #b7c7c0;padding-top:20px}.notice{background:#fff1cd;padding:16px;border-left:4px solid #ac7b29}'
        'img{width:100%;height:auto;background:white}.table{overflow:auto}table{border-collapse:collapse;width:100%;min-width:850px}td,th{text-align:left;vertical-align:top;padding:12px;border:1px solid #bfcbc6}'
        'small{color:#52665e}nav a{display:inline-block;margin:6px 16px 6px 0}@media print{main{padding:0}section{break-before:page}table{min-width:0}a{color:inherit}}</style><main>'
        '<h1>C棟概念合圖：建築、樓梯、空調與排水</h1>'
        '<p class="notice">以目前C新配置套繪。列明幾何可核對，結構梁柱、完成面、冷氣商品及排水終端未提供，尚未達施工合圖。'
        '本圖不指示鑽孔、拆梁、縮門或移除原需求；不改已驗3D與配置。</p>'
        '<p>共同座標：x向平面右、y自道路往後、z向上，單位mm；不是地籍對位或實測完成面。'
        'A／B及C其他比較不混用；正式圖號與對位資料補齊後再更新本包。</p>'
        '<nav><a href="../../candidates/kaohsiung-house-options-3d.html">目前3D</a>'
        '<a href="../../candidates/kaohsiung-house-options.html">同源配置平面</a>'
        '<a href="../../../Docs/c-coordination-review-v1.md">合圖說明與處理順序</a>'
        '<a href="reply-checklist.csv">下載12項回覆表CSV</a><a href="penetration-schedule.csv">下載3處穿孔表CSV</a>'
        '<a href="review.json">尺寸及來源JSON</a></nav>'
        '<p>本次重點：P01公衛門楣、P02樓板、P03前牆；第3株木本中心距管線投影20mm；'
        '土300＋板150＋其他50時騎樓名義高度零餘量；客房C-AC04／07兩套服務範圍待釐清。</p>'
        '<section><h2>12項合圖介面與具體回覆</h2><p>「列明幾何未見重疊」只針對指定盒體，沒有完整結構或現場證據。</p>'
        '<div class="table"><table><thead><tr><th>ID</th><th>項目</th><th>概念結果</th><th>負責</th><th>回覆與限制</th></tr></thead><tbody>'+rows+'</tbody></table></div></section>'
        +images+'<p>只輸出靜態套繪、CSV及JSON；未啟動完整場景、瀏覽器或正式版次簽認。建商／技師回覆表目前留空。</p></main></html>\n')


def artifacts(root=ROOT):
    report = build(root)
    files = {OUT+"/D01-floor-1.svg": front_plan(report, "floor-1"),
        OUT+"/D02-floor-2.svg": front_plan(report, "floor-2"), OUT+"/D03-sections.svg": section_sheet(report),
        OUT+"/D04-stair-doors.svg": stair_sheet(report), OUT+"/reply-checklist.csv": csv_text(report),
        OUT+"/penetration-schedule.csv": csv_text(report, penetrations=True), OUT+"/index.html": render_index(report)}
    report["artifact_hashes"] = {name: hashlib.sha256(value.encode()).hexdigest() for name, value in files.items()}
    files[OUT+"/review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only source/artifact byte check")
    args = parser.parse_args()
    try:
        files = artifacts()
        for name, text in files.items():
            p = ROOT/name
            if args.check:
                if not p.exists() or p.read_text(encoding="utf-8") != text:
                    raise ContractError("Concept coordination artifact missing or stale: "+name)
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
        print(f"C concept coordination {'checked' if args.check else 'written'}: {len(files)} files; no scene/browser or layout changes.")
        return 0
    except (ContractError, OSError, KeyError, StopIteration) as exc:
        print("C concept coordination failed: "+str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export only small, static ABC comparison sheets and editable reply schedules."""
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

from house_design.abc_next_improvements import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402

NS = "http://www.w3.org/2000/svg"


class Sheet:
    def __init__(self, title, report, width=1400, height=1100):
        self.root = ET.Element(f"{{{NS}}}svg", {"viewBox": f"0 0 {width} {height}", "width": str(width),
            "height": str(height), "role": "img", "aria-labelledby": "title desc"})
        self.add("title", title, id="title")
        self.add("desc", "ABC獨立深化比較，未採用。毫米局部模型座標，道路在上方；完整門組、結構及專業核對未完成。", id="desc")
        self.add("style", "text{font-family:system-ui,sans-serif;font-size:17px;fill:#263e49} .title{font-size:25px;font-weight:700}.label{font-size:18px;font-weight:650}.small{font-size:14px}.tiny{font-size:12px}")
        self.add("rect", x=0, y=0, width=width, height=height, fill="#fafbf8")
        self.text(title, 30, 42, class_="title")
        self.text("深化比較／未採用｜單位mm；來源是概念模型，梁柱、完成面、商品及實際路徑待核。", 30, 78)
        self.text("來源 "+report["source_layout_report_sha256"][:16]+"…｜本批 "+report["report_hash"][:16]+"…", 30, height-47, class_="small")
        self.text("原ABC／目前3D及正式產品回覆保留。圖上名義尺寸與方塊試排，不等於施工、照護、風水或搬運核可。", 30, height-23, class_="small")
        self.add("metadata", json.dumps({"source_sha256": report["source_layout_report_sha256"],
            "report_hash": report["report_hash"], "adopted": False}, ensure_ascii=False))

    def add(self, tag, text=None, parent=None, **attrs):
        el = ET.SubElement(self.root if parent is None else parent, f"{{{NS}}}{tag}",
            {k.rstrip("_").replace("_", "-"): str(v) for k, v in attrs.items()})
        el.text = text
        return el

    def text(self, text, x, y, **attrs):
        return self.add("text", str(text), x=x, y=y, **attrs)

    def lines(self, lines, x, y, step=28, **attrs):
        for n, line in enumerate(lines):
            self.text(line, x, y+n*step, **attrs)

    def box(self, r, **attrs):
        return self.add("rect", x=r[0], y=r[1], width=r[2], height=r[3], **attrs)

    def line(self, a, b, **attrs):
        return self.add("line", x1=a[0], y1=a[1], x2=b[0], y2=b[1], **attrs)

    def path(self, points, **attrs):
        return self.add("polyline", points=" ".join(f"{p[0]},{p[1]}" for p in points), fill="none", **attrs)

    def output(self):
        return ET.tostring(self.root, encoding="unicode")+"\n"


class Plan:
    def __init__(self, sheet, origin, scale, offset=(0, 0)):
        self.s, self.origin, self.scale, self.offset = sheet, origin, scale, offset

    def p(self, xy):
        return [self.origin[k]+(xy[k]-self.offset[k])*self.scale for k in (0, 1)]

    def box(self, r, **attrs):
        return self.s.box([*self.p(r), r[2]*self.scale, r[3]*self.scale], **attrs)

    def line(self, a, b, **attrs):
        return self.s.line(self.p(a), self.p(b), **attrs)

    def path(self, points, **attrs):
        return self.s.path([self.p(p) for p in points], **attrs)

    def text(self, value, x, y, **attrs):
        return self.s.text(value, *self.p([x, y]), **attrs)

    def rooms(self, rooms, furniture=True, min_y=None, max_y=None):
        for room in rooms:
            r = room["rect_mm"]
            if (min_y is not None and r[1]+r[3] <= min_y) or (max_y is not None and r[1] >= max_y):
                continue
            self.box(r, fill="#eee9d8" if room["outdoor"] else "#edf1ec", stroke="#9bada6", stroke_width=.8)
            if furniture:
                for i in room["furniture"]:
                    self.box(i["rect_mm"], fill="#bfc9c6", stroke="#7e9390", stroke_width=.8)
            self.openings(room)

    def openings(self, room):
        x, y, w, d = room["rect_mm"]
        for door in room["features"]["doors"]:
            length = door["width_mm"]
            if door["face"] in {"front", "rear"}:
                mid, yy = x+w*door["ratio"], y+(d if door["face"] == "rear" else 0)
                a, b = [mid-length/2, yy], [mid+length/2, yy]
            else:
                mid, xx = y+d*door["ratio"], x+(w if door["face"] == "right" else 0)
                a, b = [xx, mid-length/2], [xx, mid+length/2]
            self.line(a, b, stroke="#397e70", stroke_width=3)
        self.window(room)

    def window(self, room):
        feat = room["features"]
        if not feat.get("window_review", {}).get("renderable"):
            return
        x, y, w, depth = room["rect_mm"]
        face, width = feat.get("window_face"), feat.get("window_mm", 0)
        if face in {"front", "rear"}:
            mid, yy = x+w*feat["window_ratio"], y+(depth if face == "rear" else 0)
            self.line([mid-width/2, yy], [mid+width/2, yy], stroke="#59a7c5", stroke_width=5,
                data_element_kind="candidate-window")
        elif face in {"left", "right"}:
            mid, xx = y+depth*feat["window_ratio"], x+(w if face == "right" else 0)
            self.line([xx, mid-width/2], [xx, mid+width/2], stroke="#59a7c5", stroke_width=5,
                data_element_kind="candidate-window")


def a_sheet(report):
    a = report["a_care"]
    s = Sheet("A01｜一樓公衛與孝親房：三案同尺寸比較", report)
    source = a["control_floor"]["rooms"]
    wanted = {"bath1", "flex1", "care-passage", "rear-hall1"}
    rooms = [r for r in source if r["id"].split(":")[-1] in wanted]
    s.text("取一樓中後段；上方接原客餐廳，左側MDF／廚房、後側工作陽台均不擴入。", 30, 117)
    for n, (kind, title) in enumerate([("control", "原控制：兩門900"), ("small", "A1小改：浴1200／房1050"), ("wider", "A2優先深化：兩門1200")]):
        ox = 30+n*460
        s.text(title, ox, 157, class_="label")
        plan = Plan(s, (ox, 195), .064, (1200, 8800))
        for room in rooms:
            r = room["rect_mm"][:]
            key = room["id"].split(":")[-1]
            if kind == "wider":
                r = a["wider"].get({"bath1": "bath_rect_mm", "care-passage": "passage_rect_mm", "rear-hall1": "hall_rect_mm"}.get(key, "none"), r)
            plan.box(r, fill="#e4eeee" if key == "bath1" else "#edf1ec", stroke="#8fa19c")
            if key in {"bath1", "flex1"}:
                plan.text("公衛" if key == "bath1" else "孝親房", r[0]+100, r[1]+300, class_="small")
            for item in room["furniture"]:
                ir, ik = item["rect_mm"][:], item["id"].split(":")[-1]
                if kind == "small" and ik == "shower":
                    ir = a["small"]["shower_rect_mm"]
                if kind == "wider":
                    ir = (a["wider"]["elder_fixture_rects_mm"] if key == "flex1" else a["wider"]["bath_fixture_rects_mm"]).get(ik, ir)
                plan.box(ir, fill="#b6cece" if key == "bath1" else "#c5c5d4", stroke="#708a8d", stroke_width=1)
                label = {"bed": "床", "wardrobe": "櫃", "vanity": "盆", "toilet": "WC", "shower": "1200淋浴"}[ik]
                plan.text(label, ir[0]+40, ir[1]+220, class_="tiny")
            if kind == "control":
                plan.openings(room)
            else:
                plan.window(room)
        if kind == "small":
            plan.line([3520, 10020], [3520, 11220], stroke="#a15d26", stroke_width=4)
            plan.line([2420, 12060], [3470, 12060], stroke="#a15d26", stroke_width=4)
            plan.box(a["small"]["bath_park_rect_mm"], fill="none", stroke="#a15d26", stroke_dasharray="4 3")
        if kind == "wider":
            detail = a["wider"]
            for r in detail["elder_route_sweeps_mm"]:
                plan.box(r, fill="#c6deb6", fill_opacity=.35, stroke="#709961", stroke_dasharray="4 3")
            for key in ("bath_turn_rect_mm", "elder_turn_rect_mm"):
                r = detail[key]
                plan.s.add("circle", cx=plan.p([r[0]+750, r[1]+750])[0], cy=plan.p([r[0]+750, r[1]+750])[1],
                    r=750*plan.scale, fill="none", stroke="#69935c", stroke_dasharray="5 3")
            for r in detail["door_parking_rects_mm"].values():
                plan.box(r, fill="#edd4b3", stroke="#a66a34")
            plan.line([3800, 9140], [3800, 10340], stroke="#a15d26", stroke_width=4)
            plan.line([2500, 12060], [3700, 12060], stroke="#a15d26", stroke_width=4)
        notes = {
            "control": ["公衛／通道共邊1048；房／廳共邊1120。", "不能把原兩門直接標成1200。", "900減230假設＝670；框實品未知。", "床1520×1880、櫃1200×600保留。"],
            "small": ["浴室門改對後廳，1200淋浴移右。", "房門1050減230假設＝820，未達900。", "房間／浴室面積不變，床櫃不動。", "房門只在總扣框≤150時達900。"],
            "wider": ["浴左界右移280：公衛少0.870㎡。", "房門共邊1400；兩門1200減230＝970。", "床左移15、櫃旋轉到右牆，容量不減。", "盆／迴轉、櫃／通行分時；非照護核可。"]}[kind]
        s.lines(notes, ox, 700, step=32, class_="small")
    s.lines(["A2有界試排：浴室1500轉位不碰列明器具；房內1200方塊路徑與床／櫃最近各20mm，偏緊。",
        "115mm內縮是假設；雖列明盒體未重疊，完整門框、門片／把手、壁面工差、輪椅轉向與救援仍須重核。",
        "淺藍線為原後窗候選，細分區線不另砌牆。公衛無合法外窗依據，排氣／補氣及房門床尾視線仍待核。"], 30, 885, step=35)
    return s.output()


def b_sheet(report, option):
    s = Sheet("B01｜後門優先：整棟濕區／祭祀／搬轎" if option["id"] == "b-rear-split" else "B02｜無後巷前門備案：整棟濕區協調", report)
    s.text("藍灰家具／橘濕區／紅虛框背櫃／紫框立管預算；藍線僅搬轎方向，非裝桿／人員掃掠。", 30, 116)
    for n, f in enumerate(option["floors"]):
        ox = 30+n*345
        s.text(f["id"].split("-")[-1]+"F", ox, 155, class_="label")
        plan = Plan(s, (ox, 180), .0395)
        plan.rooms(f["rooms"])
        plan.box(option["backing_rect_mm"], fill="none", stroke="#ad4c3f", stroke_width=2, stroke_dasharray="5 3")
        for w in option["wet_projections"]:
            if w["floor"] == f["id"]:
                plan.box(w["rect_mm"], fill="#dda56f", fill_opacity=.4, stroke="#b8783c")
        plan.box(option["altar_rect_mm"], fill="none", stroke="#943b40", stroke_width=2)
        plan.box(option["shaft_rect_mm"], fill="#b58ba9", stroke="#7f4775", stroke_width=2)
        if f["id"] == "floor-1":
            axis = option["street_axis_x_mm"]
            plan.line([axis, 3900], [axis, 10690], stroke="#a8674d", stroke_dasharray="6 4", stroke_width=1.8)
            pp = [[1150, 17630], [1150, 16550]] if option["id"] == "b-rear-split" else [
                [axis, 3900], [axis, 9400], [900, 9800], [900, 14800], [1000, 16550]]
            plan.path(pp, stroke="#3a819a", stroke_width=3, stroke_dasharray="5 3")
            plan.text("神桌", 2500, 10380, class_="tiny")
            plan.text("背櫃", 2600, 12150, class_="tiny")
        total = option["wet_area_over_backing_by_floor_sqm"].get(f["id"])
        if total is not None:
            s.text(f"背櫃上方濕區 {total:g}㎡", ox, 910, class_="small")
    shaft = option["shaft_rect_mm"]
    s.lines(["2F兩間衛浴合計投影背櫃2.912㎡；3F公衛投影1.376㎡。神桌本體不在這些濕區內。",
        f"本版立管預算x{shaft[0]}～{shaft[0]+shaft[2]}、y13480～13730；接段名義通道餘{option['bath_approach_remaining_nominal_width_mm']}mm。",
        "立管不消除濕區投影，亦未畫成已核排水。若家規禁止背櫃上方濕區，須另排上層，不能靠防水宣稱符合。"], 30, 948, step=29, class_="small")
    return s.output()


def hvac_sheet(report):
    h = report["c_hvac"]
    s = Sheet("C01｜前左客房：AC04／AC07服務與負荷比較", report)
    s.text("單機優先；先研究後端AC04，前端AC07留短管備案，原圖兩機目前都保留。", 30, 119)
    room = next(r for r in h["room_drawing"]["rooms"] if r["id"] == h["room"])
    plan = Plan(s, (45, 185), .14, (0, 3900))
    plan.rooms([room])
    for unit in h["units"]:
        x, y = unit["x_mm"], unit["y_mm"]
        r = [x-475, y-140, 950, 280]
        plan.box(r, fill="#6fabb9", stroke="#39677c", stroke_width=2)
        plan.text(unit["id"], x-420, y+(700 if unit["id"] == "C-AC07" else -200), class_="small")
    s.lines(["房間名義2800×3700＝10.36㎡。", "床1050×1880、桌1400×700、櫃1800×600不變。",
        "後機：原機身底到衣櫃頂僅150mm。", "前機：投影在床頭／前窗附近，導風與拆洗待核。"], 45, 760, step=34, class_="small")
    s.lines(["後端單機 AC04", "14.185m管線／後側室外機。", "前景觀側可少一個機位需求。", "服務維修、穿牆及長管實測待核。", "",
        "前端單機 AC07", "10.085m管線，少4.1m。", "須核床頭直吹與前三台散熱。", "門關時只服務客房，不借補起居。"], 600, 193, step=32)
    s.text("負荷敏感度（不是選容量計算）", 600, 555, class_="label")
    for n, r in enumerate(h["load_sensitivity"]):
        s.text(f"10.36㎡ × {r['w_per_sqm']} W/㎡ ＝ {r['kw']:.3f} kW", 600, 600+n*38)
    s.lines(["朝向、窗玻璃、遮陽、外殼、人數與潛熱未知。", "2.8kW只作詢價級距，不直接認定適用。",
        "雙機只有已確認的備援／用途才再評估。", "兩套2.8kW的總額定5.6kW不能推論比較省電。"], 600, 755, step=34)
    s.text("完整機型要連散熱、出風、除濕、最小能力、管長／高差、冷凝水、電路及保固一起報；尚未採購或刪機。", 30, 965, class_="small")
    return s.output()


def garden_sheet(report):
    g = report["c_landscape"]
    s = Sheet("C02｜9㎡景觀與高位冷媒：原案／植栽改位／左繞", report)
    s.text("三案均保留原覆土面積與洗衣、洗槽、上鎖櫃、240cm晾衣設備。高位線不是地面障礙。", 30, 117)
    balcony = next(r for r in g["balcony_floor"]["rooms"] if r["id"] == "C:floor-2:balcony2f")
    for n, variant in enumerate(g["variants"]):
        ox = 30+n*460
        s.text(variant["label"], ox, 157, class_="label")
        plan = Plan(s, (ox, 200), .067)
        plan.rooms([balcony])
        for unit in balcony["features"].get("hvac_units", []):
            width, depth = unit["width_mm"], unit["depth_mm"]
            plan.box([unit["x_mm"]-width/2, unit["y_mm"]-depth/2, width, depth], fill="#a4bfce",
                stroke="#6f91a0", data_element_kind="outdoor-unit-footprint")
        plan.box(g["garden_rect_mm"], fill="#d5e8cb", fill_opacity=.7, stroke="#5f8d59")
        for soil in g["soil_rects_mm"]:
            plan.box(soil, fill="#b0cda2", stroke="#5a855b")
        for k, point in enumerate(variant["trees_mm"], 1):
            x, y = plan.p(point)
            s.add("circle", cx=x, cy=y, r=6, fill="#3c7548")
            s.add("circle", cx=x, cy=y, r=600*plan.scale, fill="none", stroke="#79a56d", stroke_dasharray="3 3")
            s.text("T"+str(k), x-8, y+26, class_="tiny")
        points = [p for p in variant["polyline_mm"] if p[1] <= 3900]
        plan.path(points, stroke="#276f9c", stroke_width=3)
        if variant["id"] == "left-bypass":
            plan.text("+6350候選線", 1800, 3300, class_="tiny")
        s.lines([f"AC01估長 {variant['estimated_pipe_length_mm']/1000:g}m（含1m預留）。",
            f"較原線 {variant['extra_length_mm']/1000:+g}m。",
            f"最近樹中心投影 {variant['minimum_plan_distance_mm']:g}mm。",
            "樹冠半徑600＋75管束＋100預留：",
            f"投影餘量 {variant['canopy_sensitivity'][-1]['margin_with_pipe_and_buffer_mm']:+g}mm。"], ox, 540, step=34, class_="small")
    s.lines(["P2優先核：保原植栽、管線增加5.4m至20.895m。最大20m的候選不能硬套，應另找合負荷與管長的精確配對。",
        "P1最近480mm只對較小冠幅敏感度有餘量；未選定樹種，不能要求永久修剪成假定大小。",
        "圖中虛圓是假設600半徑的投影提醒，並非成熟樹冠或法規覆蓋率；4株木本／一株至少1200mm的要求仍保留。",
        "AC03原線距原樹中心230mm，AC07原線170mm，也須同步協調；本圖沒有把三套冷媒塞進同一150mm束。",
        "前排淺藍為室外機投影；高位線不等同地面穿過機身。土深荷重、騎樓高度、支架與排水仍待合圖。"], 30, 800, step=37)
    return s.output()


def product_sheet(report):
    s = Sheet("P01｜全屋選品回套：平整馬桶與完整工程範圍", report)
    s.text("只比已列候選；一般衛浴與照護套衛分開。較小商品不自動釋放原模型空間或減少收納需求。", 30, 118)
    s.text("便器平面疊圖｜後緣對齊只作本體比較", 35, 170, class_="label")
    # Common back plane; no invented drain point or completed wall.
    ox, oy, scale = 85, 235, .58
    s.box([ox, oy, 450*scale, 700*scale], fill="#e6eae6", stroke="#82968e", stroke_width=2)
    s.box([ox+39*scale, oy+21*scale, 372*scale, 679*scale], fill="none", stroke="#367d95", stroke_width=3)
    s.box([ox+30*scale, oy-7*scale, 390*scale, 707*scale], fill="none", stroke="#bc7039", stroke_width=3)
    s.lines(["灰：模型450×700。", "藍：KOHLER372×679，寬餘78／深餘21。", "橘：TOTO390×707，深度多7。",
        "兩款305管距；現況／完成牆管距未提供。", "不預設偏心接頭、後移排污或縮小前淨空。"], 35, 710, step=34, class_="small")
    s.lines(["三組一般全衛歷史材料小計", "① KOHLER＋凱撒盆龍頭＋淋浴：26,360。",
        "② TOTO含TC301＋同盆龍頭＋淋浴：27,060。", "③ KOHLER＋HCG小浴櫃＋淋浴：36,490。",
        "只有KOHLER含蓋公開價本輪重閱；其餘沿用10/22。", "以上不等整間完工價，也不代表建商已含。", "",
        "不能直接換的地方", "A1／B1／C孝親：座高、轉位、盆下、門、扶手另核。",
        "B主臥900mm盆櫃：不以510mm小櫃取代收納。", "K系列室內機295高，比模型280高15mm。",
        "VILLES5700只是五金，完整濕區門組尚未找到定案。"], 600, 190, step=36)
    s.lines(["報價要同範圍：型號／全部配件／支架補強／配管與防水／安裝／搬運／稅／保固／原標配折抵／交期。",
        "CSV已逐浴室、逐門及逐冷氣配對列項；實際回覆與報價金額留白，不能把歷史公開價填成廠商正式報價。",
        "B前後門是互斥版本；C客房兩機是比較，未確定雙機採購。候選數量不能跨版本相加。"], 30, 925, step=33, class_="small")
    return s.output()


def table(headers, rows):
    def esc(value):
        return html.escape(str(value))
    return '<div class="table"><table><thead><tr>'+"".join("<th>"+esc(h)+"</th>" for h in headers)+"</tr></thead><tbody>"+"".join(
        "<tr>"+"".join("<td>"+esc(v)+"</td>" for v in row)+"</tr>" for row in rows)+"</tbody></table></div>"


def index_html(report):
    a, b, h, g, p = (report[k] for k in ("a_care", "b_coordination", "c_hvac", "c_landscape", "products"))
    esc = html.escape
    a_table = table(["方案", "面積與家具", "門洞／條件", "建議"], [
        ["原控制", "床與櫃不動", "兩門900；共邊1048／1120", "保留對照"],
        ["A1小改", "房間／浴室面積不變；淋浴移右", "浴1200、房1050；房總扣框須≤150才有900", "成本較低，照護門仍卡實品"],
        ["A2加寬乾區", "浴室讓0.87024㎡；床左移15；120cm櫃轉右牆", "兩洞1200；230假設扣框後970", "優先深化，20mm側餘量仍偏小"]])
    b_table = table(["項目", "後門優先", "前門備案"], [
        ["祭祀正門", "朝街、正對神桌；名義1800", "同樣保留朝街中軸"],
        ["搬轎", "由後門直接進後左庫；後巷權利／高差／裝桿外廓待核", "經前廳側緣；長凳／供桌分時整備，須獨立實演"],
        ["2F背櫃上方濕區", "2.912㎡，不是神桌本體上方", "同樣2.912㎡，不能用換入口消除"],
        ["3F背櫃上方濕區", "1.376㎡", "同樣1.376㎡"],
        ["250×250立管預算", "右側接段；名義通道餘1280", "家務乾區；右側接段維持1250，不借後門版位置"]])
    h_table = table(["比較", "優點", "代價"], [[v["id"], v["benefit"], v["cost"]] for v in h["options"]])
    g_table = table(["方案", "AC01含預留估長", "最近樹投影中心", "600半徑＋75束＋100預留"], [
        [v["label"], f"{v['estimated_pipe_length_mm']/1000:g} m", f"{v['minimum_plan_distance_mm']:g} mm",
         f"{v['canopy_sensitivity'][-1]['margin_with_pipe_and_buffer_mm']:+g} mm（假設）"] for v in g["variants"]])
    fit_table = table(["候選", "回套發現", "下一個條件"], [
        ["KOHLER K-28020T-S-0＋20970T-0", "372×679可落入450×700代表本體", "305完成牆管距、角閥／維修／座高；未採用"],
        ["TOTO CW981GUR／SW981GR＋TC301", "390×707，比模型深7", "按整組圖回套，不用700冒充"],
        ["CAESAR L2150S＋B260C", "500×400本體候選", "支承／膝部／管線／操作點未知"],
        ["HCG LCS4175-3132E", "510×410小浴櫃", "A1/B1/C照護不可直套；B主臥900櫃不縮"],
        ["Panasonic K28／36／40／50精確配對候選", "室內295高超模型280高15；容量未分配", "逐室負荷、安裝手冊、散熱、排水及管長另核"],
        ["VILLES5700", "只有五金資料，不是完整門組", "全開900、完整外凸／收疊、門楣、救援另報"]])
    counts = table(["獨立版本", "衛浴間數", "冷氣原配對", "門洞去重列項"], [
        [key, v["bathrooms"], v["hvac_sets"], v["doors_unique"]] for key, v in p["counts_by_option"].items()])
    sources = "".join('<li><a href="'+esc(r["url"], quote=True)+'">'+esc(r["id"])+"</a>："+esc(r["access"])+"；"+esc(r["facts"])+"</li>" for r in p["candidate_catalog"]["sources"])
    return f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ABC下一輪深化｜照護、祭祀、空調、景觀與選品</title>
<style>body{{font:17px/1.75 system-ui,sans-serif;color:#243d47;background:#f7f9f5;margin:0}}main{{max-width:1180px;margin:auto;padding:26px 22px 70px}}h1{{font-size:29px;line-height:1.4}}h2{{font-size:23px;margin-top:0}}h3{{font-size:18px}}a{{color:#17657f;text-underline-offset:3px}}a:focus-visible{{outline:3px solid #b36832;outline-offset:4px}}nav,.links{{display:flex;gap:14px;flex-wrap:wrap}}section{{background:white;padding:25px;margin:26px 0;border:1px solid #d9e2da;border-radius:12px;scroll-margin-top:16px}}.notice{{border-left:5px solid #af6b32;background:#fff4e6;padding:15px}}.table{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:15px;min-width:630px}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dbe2dc;vertical-align:top}}th{{background:#edf2ed}}.drawing{{display:block;max-width:100%;height:auto;margin:20px auto;border:1px solid #d7e1db}}small{{font-size:14px}}details{{padding:15px;background:#eef3ed}}@media(max-width:600px){{main{{padding:15px 12px 40px}}section{{padding:18px 14px}}h1{{font-size:25px}}.drawing{{min-height:0}}}}</style></head><body><main>
<h1>ABC下一輪深化：五項一起做</h1>
<p>先看A門位與B濕區疊圖，再看C單機／景觀及全屋選品。原尺寸、前後門備案與目前3D保留；這份新增的是有尺寸的獨立比較。</p>
<p class="notice"><strong>未採用的深化比較。</strong> 列明盒體可放入，不代表完成牆面、照護、宗教、搬轎、結構或法定可建條件已通過。實際商品及工程回覆留白，不拿假設填成核定資料。</p>
<nav aria-label="五項深化"><a href="#a-care">A照護門位</a><a href="#b-wet">B整棟協調</a><a href="#c-ac">C客房冷氣</a><a href="#c-garden">C景觀配管</a><a href="#products">ABC選品／報價</a><a href="#decisions">待討論</a></nav>
<p class="links"><a href="../../candidates/kaohsiung-house-options-3d.html">目前3D控制版</a><a href="../c-current-v1/index.html">C原四張合圖</a><a href="review.json">本批尺寸／來源資料</a></p>
<section id="a-care"><h2>1. A一樓：優先把兩道門做成1200名義洞口比較</h2>
<p>A2將公衛左界右移280mm，0.87024㎡改作乾區；孝親房仍13.572㎡，原床只左移15mm，120cm衣櫃旋轉到右牆，客餐家具與廚房不必搬。原通道與後廳交界不加牆，讓公衛1200門洞跨兩段乾區。</p>
{a_table}
<a href="A01-care-doors.svg">開啟A三案原尺寸圖</a><img class="drawing" width="1400" height="1100" src="A01-care-doors.svg" alt="A原控制、小改與加寬乾區的門位、床櫃及轉位比較" loading="lazy">
<p>浴室1500轉位在115mm假設內縮後避開列明本體；房內1200方塊路徑兩側最近各20mm，仍偏緊。衣櫃取物與通行、盆操作與轉位分時；完整門組、工差與真人轉向仍須核。外窗／排氣及門床視線未因此全部解決。</p></section>
<section id="b-wet"><h2>2. B：保留朝街祭祀及兩版搬轎，先把濕區風險說清楚</h2>
<p>2F兩間衛浴覆蓋整個2.912㎡背櫃區，3F公衛覆蓋其中1.376㎡；部分便器／淋浴本體也在背櫃投影內。神桌本體在其前方，不能把兩者混稱。原屋頂及2F乾式祭祀上方區仍保留。</p>
{b_table}<p class="links"><a href="B01-rear-coordination.svg">後門優先整棟疊圖</a><a href="B02-front-coordination.svg">無後巷前門備案疊圖</a><a href="b-engineering-replies.csv">B工程回覆表</a></p>
<img class="drawing" width="1400" height="1100" src="B01-rear-coordination.svg" alt="B後門版一至屋頂濕區、神桌背櫃投影與外緣立管預算" loading="lazy">
<p>建議先保乾背牆，不在法器櫃開清掃口。後門版250×250立管放右側接段，名義通道餘1280mm；前門版另放家務乾區，公衛接段維持1250mm，避開洗槽／洗衣操作及家務門前900矩形預算。完成淨寬／梁板／防火仍待核。污水通氣、盆淋浴廢水、冷凝水與雨水分列，終端都未核。</p>
<p class="notice">若家規也禁止「背櫃上方有浴廁」，就要重排上層濕區。新增立管、防水或裝飾天花都不能宣稱消除了這項投影。兩版的日常／祭祀／搬轎狀態仍獨立保留，方向線不是裝桿掃掠驗證。</p></section>
<section id="c-ac"><h2>3. C客房：單機優先，後端AC04先核，AC07留備案</h2>
<p>同一間10.36㎡房目前同時預留AC04與AC07。關門時兩者都只服務客房；不能把客房機拿來補起居空間。後端比前端概念管線長4.1m，但能減少前方景觀側機位需求。</p>
{h_table}<a href="C01-guest-hvac.svg">開啟客房服務比較圖</a><img class="drawing" width="1400" height="1100" src="C01-guest-hvac.svg" alt="C客房前後兩台冷氣與單機服務、負荷敏感度比較" loading="lazy">
<p>120／180／240W/㎡的面積敏感度為1.243／1.865／2.486kW，尚無正式負荷。2.8kW只是報價候選級距，沒有直接配置或移除兩套機器。衣櫃上方拆洗、床頭導風及所有實機限制要一起核。</p></section>
<section id="c-garden"><h2>4. C景觀：優先核高位線左繞，保植栽與洗曬</h2>
<p>保留右側9㎡景觀、3.393㎡覆土、四株木本示意與左側洗曬，提供P1改植栽、P2改AC01路線兩個方向。P2未降低配管，仍為+6350mm候選高位線。</p>
{g_table}<a href="C02-landscape-pipes.svg">開啟景觀／管線三案</a><img class="drawing" width="1400" height="1100" src="C02-landscape-pipes.svg" alt="C原植栽原線、調樹位及高位管線左繞的長度與樹冠敏感度" loading="lazy">
<p>P2增加5.4m至20.895m，已超過本批K系列索引20m上限，不能硬套；需另找符合負荷、管長及高差的精確配對。AC03及保留時AC07的原線亦近樹冠，尚需同步排支架／並排，不把三套當成同一束。土層與騎樓高度問題仍在原工程回覆表追蹤。</p></section>
<section id="products"><h2>5. ABC：候選本體回套、逐房與同範圍詢價</h2>
{fit_table}<p class="links"><a href="product-fit.csv">衛浴逐件回套</a><a href="door-schedule.csv">門洞逐樘核對</a><a href="hvac-fit.csv">冷氣候選回套</a><a href="quote-schedule.csv">完整工程報價空表</a><a href="P01-product-fit.svg">選品疊圖</a></p>
{counts}<p>三組一般全衛歷史材料小計26,360／27,060／36,490元；C訪客公衛無淋浴則22,400／23,100／32,530元。含蓋、配件與安裝範圍要一致；照護、較大浴櫃及特殊門分項另報。無正式施工總價，沒有把材料價填進報價回覆。</p>
<p>逐房核對採現行控制版；A2等新方案另列圖，不把未採用尺寸混入採購數量。B前後互斥、C客房雙機用途待定，表列數量不能跨版本加總。</p>
<details><summary>產品來源與價格口徑</summary><p>市場候選資料與實際廠商回覆分開。價格及部分尺寸沿用2026-10-22資料；本輪重閱KOHLER含蓋公開價及TOTO707圖，新增國際牌K系列研究。部分原廠型錄只有搜尋索引摘錄、直接連結404，已明列，不當完整安裝手冊。</p><ul>{sources}</ul></details></section>
<section id="decisions"><h2>需要討論的三個選擇</h2>
{table(["選擇", "我的建議", "還缺什麼"], [
    ["A是否用公衛0.870㎡換較寬入口", "A2先深化，A1保留低改動對照", "完整門組、完成牆與輪椅轉向；20mm側餘量偏小"],
    ["B背櫃上方濕區是否也屬禁忌", "未明確禁止前先保乾背牆、核外緣立管；若禁止則重排上層", "家規範圍；防水不能代替宗教決策"],
    ["C客房是否需要真正雙機備援", "單機、後端AC04先核；AC07留備案", "負荷、使用習慣、實機氣流／拆洗及後側散熱"]])}
<p><a href="decision-log.csv">下載含其他工程待核項的決策表</a>。已知偏好沿用；沒有替屋主填採用或替建商簽工程回覆。</p></section>
<details><summary>來源與驗收範圍</summary><p>本批是靜態圖與表格，不啟動瀏覽器、WebGL或完整場景重建。{report['protected_control_count']}份控制檔雜湊保留，其中上一輪141份畫面驗收來源沒有改。這不代表新增比較有瀏覽器驗收或專業通過。<a href="artifact-manifest.json">輸出清單</a>／<a href="../../../Docs/abc-next-improvements-v1.md">交付說明</a>。</p></details>
</main></body></html>'''


def csv_text(rows):
    if not rows:
        return ""
    columns = list(dict.fromkeys(k for row in rows for k in row))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v, ensure_ascii=False, separators=(",", ":")) if isinstance(v, (list, dict)) else
            "" if v is None else v for k, v in row.items()})
    return "\ufeff"+output.getvalue()


def render(report):
    p = report["products"]
    decisions = [
        {"id": "A-01", "topic": "A1兩門及乾區", "recommendation": "A2讓公衛0.87024㎡、兩洞1200先深化；保小改對照", "owner_decision": None,
         "actual_evidence": None, "status": "comparison-pending", "responsible": "屋主／建築／門商／照護"},
        {"id": "B-01", "topic": "背櫃上方濕區家規", "recommendation": "確認禁忌是否延伸到背櫃上層；若禁止另重排", "owner_decision": None,
         "actual_evidence": None, "status": "decision-required", "responsible": "屋主／祭祀慣例確認者"},
        {"id": "B-02", "topic": "後巷搬轎／前門備案", "recommendation": "保兩版；補巷權、門外高差及完整裝桿搬運外廓", "owner_decision": "後巷為屋主陳述預設；前門備案保留",
         "actual_evidence": None, "status": "evidence-pending", "responsible": "屋主／測量／搬運"},
        {"id": "C-01", "topic": "客房單雙機", "recommendation": "單機、後端AC04先核；AC07保留比較", "owner_decision": None,
         "actual_evidence": None, "status": "comparison-pending", "responsible": "屋主／空調"},
        {"id": "C-02", "topic": "景觀與AC01配管", "recommendation": "P2左繞先核；20.895m需另核適用精確機型", "owner_decision": None,
         "actual_evidence": None, "status": "engineering-pending", "responsible": "空調／景觀／結構／建築"},
        {"id": "ABC-01", "topic": "建商完整同範圍報價", "recommendation": "逐房三組候選；門／照護／大櫃／冷氣獨立報", "owner_decision": None,
         "actual_evidence": None, "status": "quote-not-received", "responsible": "建商／設備商"}]
    engineering = [{"id": f"B-E{n:02}", "request": request, "drawing_revision": None,
                    "actual_reply": None, "reply_reference": None, "status": "unknown"}
                   for n, request in enumerate(report["b_coordination"]["detail_requests"], 1)]
    quote_labels = {"option": "版本（互斥勿加總）", "building": "棟別", "room_or_system": "房間／設備ID", "kind": "工程項目",
        "quantity": "數量", "candidate": "候選／用途", "scope": "包含範圍", "material_only_historical_twd": "歷史材料算術（非報價）",
        "model_returned": "回覆完整型號", "material_twd": "材料價", "accessories_twd": "附件價", "reinforcement_twd": "補強／防水價",
        "installation_twd": "安裝價", "transport_twd": "運搬價", "tax_twd": "稅額", "standard_credit_twd": "原標配折抵",
        "net_installed_twd": "含工淨價", "warranty": "保固", "lead_time": "交期", "formal_quote_reference": "正式報價單號"}
    quote_rows = [{quote_labels.get(k, k): v for k, v in row.items()} for row in p["quote_rows"]]
    files = {"A01-care-doors.svg": a_sheet(report), "C01-guest-hvac.svg": hvac_sheet(report),
        "C02-landscape-pipes.svg": garden_sheet(report), "P01-product-fit.svg": product_sheet(report),
        "index.html": index_html(report), "review.json": json.dumps(report, ensure_ascii=False, indent=2)+"\n",
        "product-fit.csv": csv_text(p["fit_rows"]), "door-schedule.csv": csv_text(p["door_rows"]),
        "hvac-fit.csv": csv_text(p["hvac_rows"]), "quote-schedule.csv": csv_text(quote_rows),
        "decision-log.csv": csv_text(decisions), "b-engineering-replies.csv": csv_text(engineering)}
    for option in report["b_coordination"]["options"]:
        files["B01-rear-coordination.svg" if option["id"] == "b-rear-split" else "B02-front-coordination.svg"] = b_sheet(report, option)
    manifest = {"schema": "house-abc-next-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "source_layout_report_sha256": report["source_layout_report_sha256"],
        "artifacts": {name: hashlib.sha256(content.encode()).hexdigest() for name, content in sorted(files.items())},
        "rendered_qa": "not-run-static-comparisons", "adopted": False}
    files["artifact-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare source and output bytes without writing")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files, directory = render(report), ROOT/OUT
        if args.check:
            stale = [name for name, value in files.items() if not (directory/name).is_file() or
                     (directory/name).read_bytes() != value.encode()]
            if stale:
                raise ContractError("Static ABC outputs stale: "+", ".join(stale))
        else:
            directory.mkdir(parents=True, exist_ok=True)
            for name, value in files.items():
                (directory/name).write_text(value, encoding="utf-8", newline="")
        print(json.dumps({"status": "source-and-output-bytes-current" if args.check else "exported-static-comparisons",
            "artifacts": len(files), "protected_controls_unchanged": report["protected_control_count"],
            "a_wide_route_body_hits": len(report["a_care"]["wider"]["route_body_hits"]),
            "adopted": False, "browser": "not-run"}, ensure_ascii=False))
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

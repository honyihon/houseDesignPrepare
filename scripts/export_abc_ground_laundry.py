#!/usr/bin/env python3
"""Export three bounded laundry reservation sheets without changing the accepted 3D viewers."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.abc_ground_laundry import OUT, build  # noqa: E402
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
        self.add("style", text="text{font:17px system-ui,sans-serif;fill:#263e49}.title{font-size:26px;font-weight:700}.small{font-size:13px}.room{font-size:11px}")
        self.add("rect", x=0, y=0, width=1400, height=1200, fill="#fafbf8")
        self.text(title, 28, 40, class_="title")
        self.text("獨立預先規劃／未採用｜橙：安裝備位；綠：晾衣含衣物外廓；虛線：操作預算，不是實品門片或完整通路。", 28, 78)
        self.text("圖內尺寸mm；三棟共享到達、產品、噪音、防水、排水及專業核對待資料。原ABC、3D與已驗ZIP不改。", 28, 106)
        self.text("本批 "+report["report_hash"], 28, 1157, class_="small")
        self.text("局部矩形／路徑不當輪椅、風水、法規或施工核可；未啟動瀏覽器或點陣轉圖。", 28, 1183, class_="small")


def floor_context(sheet, rooms, upper=False):
    d = Draw(sheet, (40, 175), .044)
    for room in rooms:
        d.box(room["rect_mm"], fill="#eaf0e9", stroke="#91a298", stroke_width=.7)
        x, y, w, h = room["rect_mm"]
        labels = {"entry": "公共玄關", "living": "客餐", "mdf": "MDF備援／未釋放", "stair-door": "樓梯", "bath1": "照護公衛",
            "kitchen": "廚房", "flex1": "孝親房", "balcony1": "後工作陽台", "arcade": "騎樓不放設備", "care-passage": "照護通道",
            "rear-hall1": "公共乾區", "balcony2": "後工作陽台", "master": "主臥", "study": "書房", "bedroom2": "次臥",
            "master-bath": "公衛", "walkin": "更衣", "hall2": "公共走道", "front-service": "前設備陽台",
            "stair2": "樓梯", "rear-hall": "後乾區", "front-landing": "到達平台"}
        sheet.text(labels.get(room["id"], room["label"]), *d.point([x+w/2, y+h/2]), text_anchor="middle", class_="room")
        for item in room["items"]:
            d.box(item["rect_mm"], fill="#aabdb3", stroke="#5e7f71", stroke_width=.5)
    sheet.text("來源A二樓" if upper else "來源A一樓；前方在上", 40, 150)
    sheet.text("原分區與尺寸只供上下文", 40, 990, class_="small")
    sheet.text("不畫跨棟或穿共壁捷徑", 40, 1012, class_="small")
    return d


def detail(sheet, spec, offset_y=14900):
    class LocalDraw(Draw):
        def point(self, p):
            return super().point([p[0], p[1]-offset_y])

    d = LocalDraw(sheet, (470, 170), .125)
    for region in spec["region_rects_mm"]:
        d.box(region, fill="#edf0e9", stroke="#607c73", stroke_width=1)
    for f in spec["fixed"]:
        d.box(f["rect_mm"], fill="#d1d9d4" if f["kind"] != "door-approach" else "none",
            stroke="#7c897d", stroke_width=1, stroke_dasharray="4 3")
    for i in spec["bodies"]:
        color = "#cce5c4" if i["kind"] == "drying" else "#c1d1d3" if i["kind"] == "existing-relocated" else "#f2b668"
        d.box(i["rect_mm"], fill=color, stroke="#935b21", stroke_width=1)
        x, y, w, h = i["rect_mm"]
        name = {"shared-washer-bay": "共用洗衣備位", "optional-dryer-bay": "乾衣備位",
            "lowered-drying-envelope": "降下晾衣外廓", "moved-water-filter": "原淨軟水移位", "upper-washer-reserve": "洗衣備位"}[i["id"]]
        sheet.text(name, *d.point([x+w/2, y+h/2]), text_anchor="middle", class_="small")
    for op in spec["operations"]:
        d.box(op["rect_mm"], fill="none", stroke="#a76e38", stroke_dasharray="5 3", stroke_width=1)
    if spec.get("turn_rect_mm"):
        d.box(spec["turn_rect_mm"], fill="none", stroke="#286a84", stroke_dasharray="7 4", stroke_width=1.5)
    for a, b in zip(spec["route_points_mm"], spec["route_points_mm"][1:], strict=False):
        d.line(a, b, stroke="#348468", stroke_width=2.3)
    sheet.text("右側灰框：原冷氣維修；門前灰虛框：沿來源或另列改位預算", 470, 575, class_="small")
    return d


def ground_sheet(report, spec):
    sheet = Sheet(spec["label"], report)
    d = floor_context(sheet, report["A1_source_rooms"])
    for item in spec["bodies"]:
        d.box(item["rect_mm"], fill="#f2b668" if item["kind"] != "drying" else "#cce5c4", stroke="#935b21", stroke_width=.7)
    if spec["id"] == "A1-deeper":
        d.box([0, 14900, 2400, 930], fill="#efc1ac", stroke="#9c4634", stroke_width=1)
    detail(sheet, spec)
    sheet.text("後陽台局部｜6m研究寬；不是核定可建量", 470, 146)
    text = [spec["note"],
        "洗衣／可選乾衣機安裝包絡各850×750；機器朝左，不是商品尺寸，操作帶與門片／接管需依實機重核。",
        "1200×500晾衣外廓含衣物預算；降到可及高度，不站椅子、不跨濕地。容量未證三戶足夠，雨天乾衣／獨排補氣另核。",
        "兩個A一樓900名義門，總框230假設只剩670；公共乾區與廚房共邊1040，不能直接硬放1130／1200洞。",
        "洗衣與乾衣操作帶共用，單人分時；900方塊只核陽台內列明路徑。三棟共享通路尚無總平面，不當完整照護可達。",
        "機器鄰孝親房，須核噪音／振動、止水、合法污水、防水、地排及設備維修。原三棟人流、B祭祀搬轎均不改。"]
    if spec["id"] == "A1-compact":
        text.insert(1, "優先續研，不減廚房。藍色1500方格碰降下衣物外廓；只在完全收起條件下局部不碰，本輪未核收起淨高或真實產品。")
    else:
        text.insert(1, "左側加深2400×930，占廚房2.232㎡；原9.048→6.816㎡，不減孝親房。原淨軟水設備移位，後門與管線另排，不直接採用。")
    y = 620
    for value in text:
        y = sheet.paragraph(value, 440, y, width=55, step=23)
    return sheet.output()


def upper_sheet(report):
    spec = report["A2_reservation"]
    sheet = Sheet("A二樓後工作陽台｜洗衣備位／暫不放實機", report)
    d = floor_context(sheet, report["A2_source_rooms"], upper=True)
    d.box(spec["bodies"][0]["rect_mm"], fill="#f2b668", stroke="#935b21", stroke_width=1)
    detail(sheet, spec)
    sheet.text("兩端冷氣原維修預留不動；850×750安裝備位＋1200×900取放帶", 470, 146)
    y = 620
    for value in [spec["note"],
        "先在二樓留水、電、合法排水、止水與防水條件，不直接採購。設備外廓與換機、漏水警示、隔振與排濕待實機。",
        "備位與列明冷氣維修不碰；取放帶與書房陽台門前有共用，必須連真實門片與維修工況核。現門900名義，不當900實際淨寬。",
        "機位上下投影在一樓後工作陽台，但仍鄰睡房；不把位置對齊當排水／噪音／結構通過。A裝潢另接設計師，預埋前與建商同版核。",
        "C二樓改列暫不用／保空間：原650×650機位、給排水及恢復使用的操作不放固定櫃。原圖仍畫原機，未實際搬到A或拆除。",
        "二樓備位不取代一樓共用組；長輩不應因此被要求上樓洗衣。一樓跨棟合法、遮雨平整取送仍優先。"]:
        y = sheet.paragraph(value, 440, y, width=55, step=24)
    return sheet.output()


def render(report):
    files = {spec["id"]+".svg": ground_sheet(report, spec) for spec in report["A1_options"]}
    files["A2-reserve.svg"] = upper_sheet(report)
    files["actual-conditions-template.json"] = json.dumps(report["actual_conditions"], ensure_ascii=False, indent=2)+"\n"
    files["actual-conditions.csv"] = csv_text([{"欄位": key, "實際值": "", "單位口徑及圖號版次": "", "來源或產品文件": ""}
        for key in report["actual_conditions"]])
    files["builder-interfaces.csv"] = csv_text([{"ID": row[0], "主題": row[1], "須同版核對": row[2],
        **dict.fromkeys(["建商／A設計師回覆", "圖號版次", "費用工期保固", "已議定窗口", "屋主選擇", "專業核對"], "")}
        for row in report["config"]["engineering_topics"]])
    body = '<h1>三棟一樓共用洗衣／晾衣與A上層備位</h1><p class="note">最新方向：一樓共用一組；C二樓先暫不用、保空間，A二樓以上另留機位。獨立預先規劃，未選A為正式共用位置、未採用或核准施工；原3D與已驗收檔不改。</p>'
    body += "<p>"+html.escape(report["recommendation"])+"</p>"
    body += '<h2>先比三棟哪裡適合</h2>'+table(["棟別", "研究順位", "依據", "限制"],
        [[row[k] for k in ["building", "priority", "basis", "limits"]] for row in report["host_comparison"]])
    body += '<h2>A一樓兩版與A二樓備位</h2><p>先研究保廚房版；加深灣只保代價比較，不替屋主選縮廚房。橙色是安裝包絡／備位，不是已安裝商品。</p>'
    for spec, name in [(report["A1_options"][0], "A1-compact.svg"), (report["A1_options"][1], "A1-deeper.svg"), (report["A2_reservation"], "A2-reserve.svg")]:
        body += '<section><h3>'+html.escape(spec["label"])+"</h3><p>"+html.escape(spec["note"])+f'</p><p><a href="{name}">開向量圖</a></p><img style="width:100%;height:auto" src="{name}" alt="'+html.escape(spec["label"], quote=True)+'"></section>'
    body += '<h2>門與全程到達的缺口</h2>'+table(["門", "名義mm", "扣總框230假設mm", "900目標缺mm", "實際產品"],
        [[r["id"], r["nominal_mm"], r["assumed_clear_mm"], r["shortfall_mm"], "未知"] for r in report["doors"]])
    body += "<p>"+html.escape(report["A1_entry_constraint"]["note"])+"</p>"
    body += '<h2>三棟共用怎麼取送</h2>'+ul([report["cross_building_route"][k] for k in ["front_route", "rear_route", "if_owner_cannot_travel"]])
    body += '<h2>長輩洗、晾與雨天乾衣</h2>'+ul([
        "污衣小批平層到達→洗衣→同高度籃／檯暫放→降下晾架掛衣→升起後乾衣→分戶潔衣取回；不提濕衣上樓，操作不要靠站椅子或上方疊放機。",
        "可選乾衣機先留平放位置；機器一組不等於已買兩台。實際衣量／床單、洗烘容量與輪用時間未知，不能說1200mm小架夠三戶。",
        "A1保廚房版的洗／乾操作分時；晾架降下會占1500轉位，收起後淨高與衣物外廓尚未核。設備局部能排不等於全程輪椅或多使用者可達。",
        "雨天用核定乾衣／獨立排濕及補氣，不以日照、外窗或全熱保證防黴；不把濕衣氣味帶往孝親床、神明堂或樓上。",
        "原淨軟水與空調的完整維修包絡待資料；原來源80mm邊距不當115mm完成面已成立，新增預留的局部檢查不替既有設備背書。"])
    body += '<h2>C二樓先保空間，A裝潢另合圖</h2><p>C二樓原機位及水電、晾衣、操作空間保持，只將新研究用法列暫不用；未永久取消或拆除。A二樓機位尚須穿書房，主臥／次臥原收納不減；預埋由建商與另聘A設計師同版核。</p>'
    body += '<h2>工程接口與未填實際條件</h2>'+table(["ID", "主題", "須核對"], report["config"]["engineering_topics"])
    body += '<p>實際條件'+str(len(report["actual_conditions"]))+'欄全空；另存私人副本再補，空白不是0，不自動匯入或套圖。</p>'+ul(report["config"]["protection_rules"])
    body += '<p>'+"／".join(f'<a href="{n}">{html.escape(n)}</a>' for n in ["actual-conditions-template.json", "actual-conditions.csv", "builder-interfaces.csv", "review.json", "artifact-manifest.json"])+"</p>"
    body += '<small>本批 '+report["report_hash"]+'。只有檔案與局部幾何；沒有新瀏覽器、WebGL、真人操作或專業驗收。</small>'
    files["index.html"] = page("ABC一樓共用洗衣預先規劃", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-abc-ground-laundry-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "adopted": False,
        "artifacts": {n: hashlib.sha256(v.encode()).hexdigest() for n, v in files.items()}}, ensure_ascii=False, indent=2)+"\n"
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
                raise ContractError("Laundry preplanning output stale: "+", ".join(stale))
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, value in files.items():
                (out/name).write_text(value, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "files": len(files), "ground_options": 2,
            "A_upper_reservations": 1, "C2_space_retained_inactive": True, "actual_conditions": len(report["actual_conditions"]),
            "protected_controls": report["protected_controls_unchanged"], "whole_route_approved": False,
            "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

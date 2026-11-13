#!/usr/bin/env python3
"""Export bounded B daily roof plans and capacity/arrival evidence without a browser."""
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

from house_design.b_roof_daily_use import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_upper_replan import Draw  # noqa: E402
from scripts.export_b_upper_replan import Sheet as BaseSheet  # noqa: E402
from scripts.export_builder_communication import page, ul  # noqa: E402


class Sheet(BaseSheet):
    def __init__(self, title, report):
        self.root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": "0 0 1400 1200", "width": "1400", "height": "1200", "role": "img", "aria-label": title})
        self.add("title", text=title)
        self.add("style", text="text{font:17px system-ui,sans-serif;fill:#263e49}.title{font-size:26px;font-weight:700}.small{font-size:13px}.room{font-size:14px;font-weight:650}")
        self.add("rect", x=0, y=0, width=1400, height=1200, fill="#fafbf8")
        self.text(title, 28, 40, class_="title")
        self.text("獨立日常試排／未採用｜原24㎡目標與家規保留，原ABC／3D、RF與搬轎版本不變。未驗產品或真正梯段。", 28, 76)
        self.text("本批 "+report["report_hash"], 28, 1158, class_="small")
        self.text("指定面積、門態與方塊不是法規、風水、結構、通風、產品、輪椅或施工核可；未跑瀏覽器／WebGL。", 28, 1182, class_="small")


def daily_sheet(report, option):
    s = Sheet(option["title"], report)
    d = Draw(s, (45, 165), .15)
    d.box([0, 0, 6000, 3900], fill="#e9efdd", stroke="#607c73", stroke_width=1.5)
    d.box([0, 3900, 2400, 1070], fill="#edf0e9", stroke="#687b80")
    d.box([2400, 3900, 3600, 1070], fill="#f1ded6", stroke="#b88b7a")
    d.box(report["original_full_RF_arrival_slab_mm"], fill="#dae0e1", stroke="#869093", stroke_dasharray="5 3")
    d.box(report["arrival_platform_mm"], fill="#bdcfc9", stroke="#3c7462", stroke_width=2)
    d.box(report["front_connection_strip_mm"], fill="#f0c17f", stroke="#bd834c")
    for item in option["equipment_reservations"]:
        if item["rect_mm"][1] >= 3900:
            continue
        d.box(item["rect_mm"], fill="#d3d8cf", stroke="#786749", stroke_dasharray="5 3")
        if item.get("body_mm"):
            d.box(item["body_mm"], fill="#9eafb2", stroke="#486650")
        x, y = d.point([item["rect_mm"][0]+item["rect_mm"][2]/2, item["rect_mm"][1]+item["rect_mm"][3]/2])
        label = {"heat-pump": "熱泵預留", "front-dirty-zone": "污氣區", "representative-slot-1": "代表槽1", "representative-slot-2": "代表槽2"}[item["id"]]
        s.text(label, x, y, text_anchor="middle", class_="room")
    for item in option["furniture"]:
        d.box(item["operation_mm"], fill="#d7e7ee", fill_opacity=.75, stroke="#668b9a", stroke_dasharray="4 3")
        d.box(item["rect_mm"], fill="#c7b99b", stroke="#796745", stroke_width=1.5)
        cx, cy = [item["rect_mm"][0]+item["rect_mm"][2]/2, item["rect_mm"][1]+item["rect_mm"][3]/2]
        s.text("晾衣" if item["id"] == "drying-rack" else "折衣", *d.point([cx, cy]), text_anchor="middle", class_="room")
    for route in option["routes"]:
        for a, b in zip(route["points_mm"], route["points_mm"][1:], strict=False):
            d.line(a, b, stroke="#267f74", stroke_width=2, stroke_dasharray="5 4")
    for state in option["door_states"]:
        d.poly(state["leaf_polygon_mm"], fill="#c79a73" if state["state"] == "open" else "none", stroke="#8a5a3b", stroke_width=1, stroke_dasharray="4 3" if state["state"] != "open" else "none")
    s.text("前道路側／上方均為RF平面，不新增屋頂層", 45, 135, class_="small")
    s.text("保守只用右側到達平台", *d.point([1340, 4830]), class_="small")
    s.text("祭祀保護投影：非日常通路", *d.point([2850, 4500]), class_="room")
    y = 145
    for text in [f"原24㎡目標保留。設備／門扣除後輪廓{option['front_open_outline_before_daily_furniture_sqm']:.4f}㎡，再扣桌架機身{option['front_open_outline_after_daily_furniture_sqm']:.4f}㎡，均含共用通路，非合法淨平台。",
        "晾衣架1800×600、折衣桌1200×450，兩案同尺寸；藍虛線區為操作預算，不當選定產品或曬被容量。",
        "原右鉸鏈全開仍卡外轉角；本輪保洞改左鉸鏈。綠虛線700mm全開才不受門阻，半開及關閉另表。",
        "1130洞扣框預算900，不等於全程900；平台與門中心偏65，指定900試線會超左側15mm。",
        "操作分時：衣籃／衣物不得封門。D1折衣與到達共用；D2桌位較獨立，但後設備緊迫未解。",
        "黃色70mm銜接仍是假設。900若用來源2200mm全寬平台可另比容納，須確認可用平地；真實梯段、門檻與消防未核。"]:
        y = s.paragraph(text, 990, y, width=22, step=22)
    y = 1000
    for text in ["前平台不能直接連後曬衣；現行RF祭祀保護區只留必要巡檢。後空地、三樓天井不抵本層24㎡，也不放寬家規。",
        "本圖只試日常平面。熱泵／冷氣熱風、污氣、香火與新風回吸、防颱固定、晾衣容量及設備拆換仍待實際資料。"]:
        y = s.paragraph(text, 40, y, width=82, step=23)
    return s.output()


def capacity_sheet(report):
    s = Sheet("B RF容量與到達｜不再用移設備湊24㎡", report)
    d = Draw(s, (45, 165), .044)
    d.box([0, 0, *report["config"]["frame_mm"]], fill="#eef0e7", stroke="#607c73")
    for comp in report["capacity"]["components_mm"]:
        d.poly(comp["outer"], fill="#d7e7c0", stroke="#708738")
        for hole in comp["holes"]:
            d.poly(hole, fill="#eef0e7")
    for p in report["protected_polygons_mm"]:
        d.poly(p, fill="#f1ded6", stroke="#b88b7a")
    d.box(report["stair_source_room"]["rect_mm"], fill="#d2d9e0", stroke="#66758b")
    d.box(report["R1_opening_mm"], fill="#c8dce4", stroke="#217eac")
    s.text("前：獨立日常候選", 55, 230, class_="room")
    s.text("中：保護／梯核分隔", 55, 600, class_="room")
    s.text("後：未與前日常相通", 55, 840, class_="room")
    s.text("6000×17630約32地坪，外框未擴大", 40, 1005, class_="small")
    y = 145
    for text in ["固定前帶名義23.4㎡；只扣外緣115mm、不扣設備或交界內牆的樂觀上界21.83945㎡，已比24少2.16055㎡。",
        "因此即使移走全部設備，或只改RF前門，固定前帶也達不到24；這只針對本固定拓樸，不是所有整棟方案皆不可能。",
        "後側有空地但與前側分開。現行RF保護用途不允許當日常曬衣通路，不能把兩塊面積相加後稱24已解。",
        "到達平台只用前一層右跑對應1000×1000；原RF圖畫的2200全寬板不當任意可用。70mm前銜接仍是條件，未驗樓板。",
        "門中心1715、到達平台中心1780，偏65mm；900方塊以門中心延伸到平台時左緣1265，超出平台左緣1280共15mm。",
        "原右鉸鏈全開仍卡外轉角，同洞改左後全開不阻700／800試線；900仍須調整到達平台。門框、扶手與產品淨寬未知。",
        "D1保較多後設備餘量但折衣與通道共用；D2日常較順，但後熱泵／水塔包絡緊，不能用生活圖取代設備核對。"]:
        y = s.paragraph(text, 400, y, width=48, step=23)
    s.text("真正的後續路徑", 400, y+12, class_="room")
    y += 50
    for row in report["decision_paths"]:
        y = s.paragraph(row["title"]+"："+row["recommendation"], 400, y, width=48, step=22)
    return s.output()


def render(report):
    files = {o["id"]+".svg": daily_sheet(report, o) for o in report["options"]}
    files["capacity-and-arrival.svg"] = capacity_sheet(report)
    files["capacity.csv"] = csv_text([{"口徑": "固定前帶名義外框", "面積㎡": report["capacity"]["front_nominal_gross_sqm"], "原目標㎡": 24, "可當完成面積": "否"},
        {"口徑": "只扣外緣預算但不扣設備的樂觀上界", "面積㎡": report["capacity"]["front_before_equipment_with_edge_budget_sqm"], "原目標㎡": 24, "可當完成面積": "否"}]+
        [{"口徑": o["id"]+"設備／門後含通路輪廓", "面積㎡": o["front_open_outline_before_daily_furniture_sqm"], "原目標㎡": 24, "可當完成面積": "否"} for o in report["options"]])
    files["door-route-matrix.csv"] = csv_text([{"方案": o["id"], "前門": s["state"], "角度": s["angle_deg"], "碰家具或設備": ",".join(s["fixed_body_hits"]),
        **{k+"受門阻擋": v for k, v in s["route_blockers"].items()}, "實際淨寬及消防": "未知"} for o in report["options"] for s in o["door_states"]])
    files["arrival-widths.csv"] = csv_text([{"方案": o["id"], "試線寬mm": c["width_mm"], "在條件地面內": c["inside_conditional_floor"],
        "若確認來源全寬平台可容納": c["inside_if_source_full_width_landing_confirmed"],
        "超出條件地面㎡": c["outside_conditional_floor_sqm"], "全開門仍阻擋": c["fully_open_door_hit"], "實際或照護核可": "未知"} for o in report["options"] for c in o["arrival_width_cases"]])
    files["operation-sharing.csv"] = csv_text([{"方案": o["id"], "試線": r["id"], "與操作帶共用": ",".join(r["shared_operation_ids"]), "多人同用核可": "未知", "專用面積可重算": "否"} for o in report["options"] for r in o["routes"]])
    files["decision-paths.csv"] = csv_text([{"路徑ID": p["id"], "方向": p["title"], "建議與代價": p["recommendation"], "屋主選擇": "", "同版專業依據": "", "正式發行": ""} for p in report["decision_paths"]])
    files["engineering-replies.csv"] = csv_text([{"問題ID": f"BDU-{n:02d}", "待核": value, **dict.fromkeys(["同版資料圖號", "專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"], "")} for n, value in enumerate(report["config"]["limits"], 1)])
    body = '<h1>B屋頂日常使用與24㎡容量界</h1><p class="note">獨立比較／未採用。原24㎡活動曬衣及家規保留；不把10㎡下限當接受縮平台，不改ABC／3D或搬轎版本。</p>'
    body += '<p>'+html.escape(report["conclusion"])+"</p>"
    body += '<p>固定前帶只扣外緣的樂觀上界21.83945㎡，還沒扣設備就比24少2.16055㎡；後側因現行保護／梯核分隔不能以日常路徑相加。不是靠再微移一台設備能補足。</p>'
    body += table(["方案", "設備／門後輪廓㎡", "再扣桌架機身㎡", "折衣與到達共用", "原24㎡目標"], [[o["title"], f"{o['front_open_outline_before_daily_furniture_sqm']:.4f}", f"{o['front_open_outline_after_daily_furniture_sqm']:.4f}", "有，需分時" if o["arrival_route_shares_folding_operation"] else "列明操作帶不共用", "保留缺口，未接受縮小"] for o in report["options"]])
    body += '<p>面積均含共用通路，是紙上輪廓，不能當完整功能、合法淨面積或產品核可。晾衣架1800×600與折衣桌1200×450只是同尺寸比較，未增加洗衣機或排水。</p>'
    for name, title in [(o["id"]+".svg", o["title"]) for o in report["options"]]+[("capacity-and-arrival.svg", "為何24㎡不足與前門到達的真正缺口")]:
        body += f'<section><h2>{html.escape(title)}</h2><p><a href="{name}">開啟向量圖</a></p><img style="width:100%;height:auto" src="{name}" alt="{html.escape(title)}"></section>'
    body += '<h2>門洞預算與連續到達分開</h2><p>原候選RF右鉸鏈門全開仍卡外側轉角，本輪保同洞改左鉸鏈，只有全開才不阻本輪700mm到達。1130洞扣兩邊115後雖有900預算，但平台中心與門偏65mm，指定900試線向保守平台左側超出15mm；若來源2200mm全寬平台確認為可用平地，900可在另一候選模型內容納。700／800只是條件地面試線；真實樓梯、70mm前銜接、門檻與產品仍未知，半開及關閉均受阻。</p>'
    body += '<h2>保留的決策路徑</h2>'+ul([p["title"]+"："+p["recommendation"] for p in report["decision_paths"]])
    body += '<h2>其餘條件與未解代價</h2>'+ul(report["config"]["limits"])
    body += '<p>'+"／".join(f'<a href="{n}">{n}</a>' for n in files if n.endswith(".csv"))+'</p><p><a href="review.json">完整來源與幾何</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；未跑瀏覽器／WebGL，未取得專業或風水核可。</small>'
    files["index.html"] = page("B屋頂日常使用與容量比較", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-b-roof-daily-use-artifacts-v1", "report_hash": report["report_hash"], "source_hashes": report["source_hashes"],
        "adopted": False, "artifacts": {n: hashlib.sha256(v.encode()).hexdigest() for n, v in files.items()}}, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files, out = render(report), ROOT/OUT
        if args.check:
            if any(not (out/n).is_file() or (out/n).read_bytes() != data.encode() for n, data in files.items()):
                raise ContractError("Daily roof study stale")
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (out/name).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "options": 2, "door_cases": 6, "files": len(files),
            "protected_controls": report["protected_controls_unchanged"], "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

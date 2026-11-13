#!/usr/bin/env python3
"""Export static B3 placement, acoustic-space and RF coordination comparisons."""
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

from house_design.b_third_entertainment import OUT, build  # noqa: E402
from house_design.b_upper_replan import door  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_upper_replan import Draw  # noqa: E402
from scripts.export_b_upper_replan import Sheet as BaseSheet  # noqa: E402
from scripts.export_builder_communication import page, ul  # noqa: E402


class Sheet(BaseSheet):
    def __init__(self, title, report):
        self.root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": "0 0 1400 1200", "width": "1400", "height": "1200", "role": "img", "aria-label": title})
        self.add("title", text=title)
        self.add("style", text="text{font:17px system-ui,sans-serif;fill:#263e49}.title{font-size:26px;font-weight:700}.small{font-size:13px}.room{font-size:13px;font-weight:650}")
        self.add("rect", x=0, y=0, width=1400, height=1200, fill="#fafbf8")
        self.text(title, 28, 40, class_="title")
        self.text("獨立比較／未採用｜前量體、隔音、新風、RF天井與機位未核；原ABC／3D及P1／P2／P3保留。", 28, 76)
        self.text("本批來源 "+report["report_hash"], 28, 1158, class_="small")
        self.text("僅指定模型的幾何／算式，不代表聲學、產品、法規、風水、消防、搬運或施工核可。", 28, 1182, class_="small")


def plan(report, front):
    s = Sheet("Q2｜前側娛樂、後客房／公衛與工作天井" if front else "Q1｜保留原後段：安靜用途研究，20㎡KTV仍缺", report)
    floor = report["front_option"] if front else report["rear_control"]
    d = Draw(s, (45, 145), .052)
    labels = {"stair": "原梯核", "quiet-living": "安靜起居／通行", "dry-protection": "完整乾保護室", "front-entertainment": "前娛樂候選", "guest": "後客房",
        "rear-bath": "後公衛", "working-court": "工作天井候選", "rear-access": "公共到達", "public-bath": "原前公衛", "front-open": "原前開放帶", "tea-foyer": "原前室", "ktv-study": "原後娛樂候選"}
    for r in floor["rooms"]:
        from shapely.geometry import Polygon
        fill = "#e8dff2" if r["kind"] == "high-activity" else "#dceff4" if r["kind"] == "wet" else "#f1e7cd" if r["kind"] == "bedroom" else "#edf0e9"
        d.poly(r["polygon_mm"], fill=fill, stroke="#607c73", stroke_width=.8)
        point = Polygon(r["polygon_mm"]).representative_point()
        s.text(labels[r["id"]], *d.point([point.x, point.y]), text_anchor="middle", class_="room")
        for i in r["items"]:
            d.box(i["rect_mm"], fill="#b9c9be", stroke="#3c6355", stroke_width=.7)
        for shaft in r["shafts_mm"]:
            d.box(shaft, fill="#ca9d8b", stroke="#9c4634")
        for w in r["windows_mm"]:
            d.line(w[:2], [w[0]+w[2], w[1]], stroke="#168cae", stroke_width=3)
        for spec in r["doors"]:
            d.line(spec["a"], spec["b"], stroke="#fafbf8", stroke_width=3)
            d.poly(list(door(spec, 90).exterior.coords), fill="#bb9474", stroke="#805534", stroke_width=.6)
    routes = floor.get("explicit_routes", []) if front else floor.get("routes", [])
    for r in routes:
        for a, b in zip(r["points_mm"], r["points_mm"][1:], strict=False):
            d.line(a, b, stroke="#277c79", stroke_width=1.5, stroke_dasharray="4 3")
    from house_design.b_front_service_detail import leaves
    for spec in report["config"]["sliders"] if front else report["rear_service_sliders"]:
        d.line(spec["a"], spec["b"], stroke="#fafbf8", stroke_width=3)
        for p in leaves(spec, "open"):
            d.box(p, fill="#bb9474", stroke="#805534", stroke_width=.6)
    if front:
        connection = floor["quiet_to_rear_connection"]
        d.line(connection["a"], connection["b"], stroke="#fafbf8", stroke_width=3)
    s.text("前方道路／1F騎樓在此下方", 45, 120, class_="small")
    s.text("6×17.63m研究框，約32地坪；不是可建量核定", 45, 1090, class_="small")
    notes = (["前娛樂基準扣井21.0159㎡；再加100mm／面空間預算後19.2079㎡，未達20目標；14下限不等於屋主已接受縮房。",
        "客房12.423、公衛6.133、工作天井115輪廓4.123㎡；公衛對齊2F套衛，前彈性／安靜區29.2948㎡仍保護祭祀投影。",
        "前側室內23.400㎡，較P3多10.647㎡；原前景觀／設備位置被取代，全部須納入正式量體與結構設計。",
        "2F前井400×400仍穿娛樂室；3F浴室移後不代表P3騎樓／梯核排水缺口解除。",
        "取消原露台門作固定分隔，娛樂先由梯核進；原梯段、側門／平台與新聲學門組未核，不宣稱消防成立。",
        "後客房原雙人床與櫃保尺寸；偏位門中軸避床體，沒有完整家規或照護核可。",
        "四組門各三態共81組；天井由公共起居直達，不穿客房。全開才通相關700方塊，門淨寬、門檻防雨與救援未知。",
        "天井在2F部分梳妝更衣乾區上方，防水與漏水維護未核；需RF板洞及另圖機位／護欄／繞行，不當已核陽台。",
        "前側位置較少壓樓下睡眠區；窗門、風管、樓板和機位仍傳聲，沒有dB或夜間使用承諾。"] if front else
        ["Q1保留原P3三樓資料；低音量／閱讀只是比較方向，不取消原20㎡KTV目標，也不承諾夜間噪音合格。",
        "後娛樂扣井14.3141㎡、後客房15.5156㎡；聲學再內縮會繼續吃面積，不能把原14㎡下限當20㎡。",
        "固定後段、115每面預算、完整乾保護室及後井，連不加客房／KTV分隔的樂觀上界也只有31.0171㎡。",
        "12客房＋20KTV共32㎡，已高於此上界；微移分隔無法在這組固定條件下解決，並非證明全棟不能換拓樸。",
        "後娛樂仍投影二樓主臥乾區9.062㎡，並與客房共牆；未壓床體不等於低頻／振動合理。",
        "三樓工作陽台尚未在Q1獨立核成完整方案；不把既有景觀、設備或屋頂曬衣直接算作已達工作陽台目標。",
        "原兩個1F搬轎入口、祭祀朝街門及乾保護範圍維持；Q1與Q2不混用面積、門位或聲學結果。"])
    y = 145
    for text in notes:
        y = s.paragraph(text, 445, y, width=48, step=24)
    return s.output()


def acoustic_sheet(report):
    s = Sheet("B3｜面積與聲學空間敏感度，沒有dB承諾", report)
    s.text("額外內縮是每一面再加；基準已115mm。只算平面損失，牆地天花、門窗、消音和實際效果未選定。", 35, 135)
    for x, title in [(40, "配置"), (230, "每面額外mm"), (450, "扣井後㎡"), (650, "20目標"), (850, "14下限"), (1060, "原候選家具")]:
        s.text(title, x, 195)
    y = 245
    for c in report["acoustic_space"]["cases"]:
        for x, value in [(40, "原後段" if c["option"] == "rear" else "新前側"), (230, str(c["extra_each_face_mm"])),
                (450, f"{c['area_sqm']:.4f}"), (650, "算術達標" if c["goal20_met_in_model"] else "未達"),
                (850, "算術達標" if c["min14_met_in_model"] else "未達"),
                (1060, "需調整" if c["unchanged_furniture_parts_outside"] else "本假設容納")]:
            s.text(value, x, y)
        y += 41
    y += 25
    bound = report["fixed_rear_optimistic_bound"]
    for text in [f"固定後段樂觀上界{bound['usable_upper_bound_sqm']:.4f}㎡，已短於12＋20目標{bound['short_of_two_targets_sqm']:.4f}㎡；還沒扣新增分隔／走道／隔音。",
        f"新前側維持20㎡時，額外四面內縮容許量約{report['acoustic_space']['front_extra_each_face_limit_for20_in_this_area_model_mm']:.1f}mm／面；不是可指定產品厚度或聲學規格。",
        "50mm案例20.1019㎡不代表50mm材料就能唱歌；若實際需要100mm，本模型只有19.2079㎡，原20需求仍保留待取捨。",
        "前置活動不壓2F主臥／床體；仍可能經門、窗、風管及梁板傳聲。關門新風需核風量、消音、壓損、檢修，與香火／浴廁分系統。",
        "次序：先核合法量體／屋頂改動，再由聲學、建築、機電用實際包絡回套面積與費用；資料不足前不選最薄值當通過。"]:
        y = s.paragraph(text, 35, y, width=82, step=23)
    return s.output()


def roof_sheet(report):
    s = Sheet("Q2必要代價｜RF代表機位、工作天井板洞與繞行", report)
    d = Draw(s, (45, 145), .052)
    d.box([0, 0, 6000, 17630], fill="#eef0e7", stroke="#607c73")
    for room in report["front_option"]["rooms"]:
        if room["id"] in {"quiet-living", "dry-protection"}:
            d.poly(room["polygon_mm"], fill="#f1ded6", stroke="#b88b7a", fill_opacity=.65)
    d.box([0, 3900, 2400, 5200], fill="#d2d9e0", stroke="#66758b")
    d.box(report["rf_overlay"]["void_mm"], fill="#c8dce4", stroke="#497589", stroke_width=2)
    for r in report["rf_overlay"]["candidate_slots"]:
        d.box(r["service_mm"], fill="none", stroke="#b78447", stroke_dasharray="4 3")
        d.box(r["rect_mm"], fill="#c2ccd6", stroke="#536b80")
    for u in report["rf_overlay"]["existing_units"]:
        d.box(u["rect_mm"], fill="#b2c6b7", stroke="#486650")
    for r in report["rf_overlay"]["alternative_routes"]:
        for a, b in zip(r["points_mm"], r["points_mm"][1:], strict=False):
            d.line(a, b, stroke="#277c79", stroke_width=1.8, stroke_dasharray="4 3")
    s.text("RF前側：兩個替代代表機位", 45, 130, class_="small")
    s.text("天井需RF板洞", 48, 780, class_="room")
    s.text("原B-AC03／04保留", 50, 1090, class_="small")
    y = 145
    for text in ["本圖是Q2所需的RF介面比較，原屋頂快照沒有修改；不是原RF不需調整的方案。",
        "兩個900×350代表位置及1350深維修預算由三樓前帶轉到RF前側比較；身分／服務範圍未定，不能當兩台新機或重複加購。",
        "原B-AC03／04後機位保持來源位置。屋頂其他水塔／熱泵／新風與結構需求仍保留，空白不當可任意放設備。",
        "工作天井板洞5.112㎡占原後機位區前端，原直走入口被截斷。虛線從RF側門外指定點繞右側、再從天井後緣繞回。",
        "700方塊只比列明平面，另留100護欄預算；實際屋突門、梯段、護欄、雨天防滑、設備拆運與承重／防颱均未核。",
        "機位與新板洞避名義祭祀保護／列明機身，但管線、排水、穿孔及振動沒有因此取得家規或工程核可。",
        "新冷媒／冷凝水與天井雨水、生活污廢水分系統重排；不借舊機位路線或400井預算稱容量足。",
        "若合法量體、RF開口或機位不成立，Q2不能整套採用；Q1和所有原功能目標繼續保留。"]:
        y = s.paragraph(text, 445, y, width=48, step=24)
    return s.output()


def render(report):
    files = {"Q1-rear-control.svg": plan(report, False), "Q2-front-entertainment.svg": plan(report, True),
        "acoustic-space.svg": acoustic_sheet(report), "roof-interfaces.svg": roof_sheet(report)}
    files["program-ledger.csv"] = csv_text([{"原需求ID": r["id"], "原狀態": r["original_status"], "原目標㎡": r["target_sqm"], "原下限㎡": r["min_sqm"],
        "Q2模型㎡": r["modeled_value_sqm"], "僅模型達目標": r["target_met_in_area_model_only"], "功能法規核可": "未知", "已採用": "否"} for r in report["original_3f_requirement_ledger"]])
    files["acoustic-area.csv"] = csv_text([{"配置": r["option"], "每面額外內縮mm": r["extra_each_face_mm"], "面積㎡": r["area_sqm"],
        "20目標算術達標": r["goal20_met_in_model"], "14下限算術達標": r["min14_met_in_model"], "聲學實際效果": "未知"} for r in report["acoustic_space"]["cases"]])
    files["door-route-matrix.csv"] = csv_text([{"前門": s["states"]["front"], "客房門": s["states"]["guest"], "公衛門": s["states"]["bath"], "天井門": s["states"]["court"],
        **{k+"阻門": ",".join(v) for k, v in s["route_blockers"].items()}, "實際產品與消防": "未知"} for s in report["front_option"]["independent_door_states"]])
    files["engineering-replies.csv"] = csv_text([{"問題ID": f"B3E-{n:02d}", "待核": text,
        **dict.fromkeys(["同版資料圖號", "專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"], "")} for n, text in enumerate(report["config"]["limits"], 1)])
    body = '<h1>B三樓：娛樂配置與隔音空間比較</h1><p class="note">獨立比較／未採用。保留原20㎡KTV、12㎡客房、5㎡公衛及4㎡工作陽台目標；Q1／Q2不混用，原ABC／3D與P1／P2／P3保留。</p>'
    body += "<p>"+html.escape(report["conclusion"])+"</p><p>Q2後客房12.423、公衛6.133、工作天井115輪廓4.123㎡；前娛樂扣井基準21.0159㎡，再加100mm／面空間預算後19.2079㎡，仍低於20目標。</p>"
    for name, title in [("Q1-rear-control.svg", "Q1保留後段與面積缺口"), ("Q2-front-entertainment.svg", "Q2前側娛樂的完整三樓比較"), ("acoustic-space.svg", "隔音空間敏感度與原需求對帳"), ("roof-interfaces.svg", "必要的RF機位／天井／維修代價")]:
        body += f'<section><h2>{title}</h2><p><a href="{name}">開啟向量圖</a></p><img style="width:100%;height:auto" src="{name}" alt="{title}"></section>'
    body += '<h2>原需求逐項保留</h2>'+table(["ID", "目標㎡", "本模型㎡", "狀態"], [[r["id"], str(r["target_sqm"]), f"{r['modeled_value_sqm']:.4f}", "面積算術達標，功能／合法未核" if r["target_met_in_area_model_only"] else "原目標仍缺"] for r in report["original_3f_requirement_ledger"]])
    body += '<h2>先決條件與未解代價</h2>'+ul(report["config"]["limits"])
    body += '<p><a href="program-ledger.csv">原需求對帳CSV</a>／<a href="acoustic-area.csv">面積敏感度CSV</a>／<a href="door-route-matrix.csv">81門態CSV</a>／<a href="engineering-replies.csv">工程回覆模板</a>／<a href="review.json">完整來源與幾何JSON</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；靜態檢查不等於聲學或法規核可，未跑瀏覽器／WebGL／轉圖。</small>'
    files["index.html"] = page("B三樓娛樂與隔音空間比較", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-b-third-entertainment-artifacts-v1", "report_hash": report["report_hash"], "source_hashes": report["source_hashes"], "adopted": False,
        "artifacts": {n: hashlib.sha256(v.encode()).hexdigest() for n, v in files.items()}}, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    try:
        report = build(ROOT)
        files, out = render(report), ROOT/OUT
        if args.check:
            stale = [n for n, v in files.items() if not (out/n).is_file() or (out/n).read_bytes() != v.encode()]
            if stale:
                raise ContractError("B3 comparison stale: "+", ".join(stale))
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (out/name).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "options": 2, "door_combinations": len(report["front_option"]["independent_door_states"]), "files": len(files),
            "protected_controls": report["protected_controls_unchanged"], "original_requirements_met": False, "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

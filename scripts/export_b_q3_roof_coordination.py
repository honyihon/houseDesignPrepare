#!/usr/bin/env python3
"""Export bounded same-revision Q3 roof arrival, doors and equipment references."""
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

from house_design.b_ktv_stair_options import side_leaf  # noqa: E402
from house_design.b_q3_roof_coordination import OUT, build  # noqa: E402
from house_design.b_upper_replan import door  # noqa: E402
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
        self.text("Q3改梯後RF獨立合圖／未採用｜新完整平台、前室及樓板需結構核定，舊圖只保對照，未併原ABC／3D。", 28, 76)
        self.text("本批 "+report["report_hash"], 28, 1158, class_="small")
        self.text("門態與方塊是本批來源的靜態算式，非結構、法規、風水、產品、消防、照護或施工核可。未跑瀏覽器。", 28, 1182, class_="small")


def roof_sheet(report, option):
    s = Sheet(option["title"], report)
    d = Draw(s, (45, 145), .052)
    d.box([0, 0, 6000, 17630], fill="#eef0e7", stroke="#607c73")
    for p in report["protected_polygons_mm"]:
        d.poly(p, fill="#f1ded6", stroke="#b88b7a", fill_opacity=.7)
    d.box(report["config"]["roof_enclosure_mm"], fill="#e3e9e5", stroke="#66758b")
    f = report["floor_requirements"]
    d.box(f["stairwell_keep_open_mm"], fill="#f7f7f4", stroke="#a55748", stroke_dasharray="5 3")
    d.box(f["landing_mm"], fill="#b9d0b3", stroke="#4c7750", stroke_width=1.2)
    d.box(f["vestibule_mm"], fill="#d9dfbf", stroke="#74803e", stroke_width=1.2)
    d.box(report["R1_reference"]["rf_retained_strip_mm"], fill="#b8c9b5", stroke="#537b51")
    d.box(report["R1_reference"]["rf_opening_mm"], fill="#c8dce4", stroke="#217eac")
    for p in report["R1_reference"]["rf_guard_polygons_mm"]:
        d.poly(p, fill="#bd8f56")
    for item in option["equipment_reservations"]:
        fill = "#cbd7c1" if item["kind"] == "wet-equipment" else "#d3d0df" if item["kind"] in {"air-zone", "pipe-zone"} else "none"
        d.box(item["rect_mm"], fill=fill, stroke="#786749", stroke_dasharray="4 3")
        if item.get("body_mm"):
            d.box(item["body_mm"], fill="#a6bdb0", stroke="#486650")
    for item in option["furniture"]:
        d.box(item["rect_mm"], fill="#c7b99b", stroke="#796745")
    for spec, func in [(option["front_door"], door), (option["side_door"], side_leaf)]:
        d.line(spec["a"], spec["b"], stroke="#fafbf8", stroke_width=3)
        d.poly(list(func(spec, 90).exterior.coords), fill="#bb9474", stroke="#805534", stroke_width=.7)
    for route in option["routes"]:
        for a, b in zip(route["points_mm"], route["points_mm"][1:], strict=False):
            d.line(a, b, stroke="#277c79" if route["use"] == "daily" else "#9b753f", stroke_width=1.8 if route["use"] == "daily" else 1.1, stroke_dasharray="4 3")
    s.text("綠：日常由前門／棕：必要巡檢依門路表", 45, 125, class_="small")
    s.text("整個梯核不能鋪實心地板", 45, 1090, class_="small")
    y = 145
    for value in ["新到達平台y4770，前室接回前門與原研究RF側門y4400。外框不擴大，RF側門不必僅因改梯後移；不是現場開洞許可。",
        "全寬2200×1000平台、2170×755前室及門檻是新結構條件；保2200×3260後梯井，不蓋三樓上來的踏步。",
        "日常700／800／900試線不進祭祀保護投影，前門全開才通；900扣框預算無工差，不當實際或輪椅核可。",
        "後設備巡檢接原側門，前熱泵改由前門避晾衣架；700試線不代表整機搬運，須各自門全開才通。",
        "S1／S2設備及D1／D2桌架原位保留；D1折衣分時、D2後設備緊。香火、一般新風、浴廁及污水通氣仍分系統。",
        f"前平台設備／門後輪廓{option['front_open_outline_before_daily_furniture_sqm']:.4f}㎡、再扣桌架{option['front_open_outline_after_daily_furniture_sqm']:.4f}㎡均含通路。24㎡目標未達、不把室內前室計入。",
        "RF前室位於Q3 KTV凹部上方，腳步、門振動與樓板聲學未核。Q3的20.1889㎡只是指定預算，150mm厚度等仍不足20。",
        "原P3前排水、R1防水／乾衣及RF全部性能未解。本圖只補同版接法，原梯屋頂比較不被覆寫或套新passed。"]:
        y = s.paragraph(value, 445, y, width=48, step=23)
    return s.output()


def floor_sheet(report):
    s = Sheet("Q3 RF到達／前室｜保原側門，梯井保持開口", report)
    f = report["floor_requirements"]
    d = Draw(s, (45, -275), .14)
    d.box([0, 3900, 2400, 5200], fill="#eef0e7", stroke="#607c73", stroke_width=1.5)
    d.box(f["stairwell_keep_open_mm"], fill="#f7f7f4", stroke="#a55748", stroke_width=2, stroke_dasharray="6 4")
    d.box(f["landing_mm"], fill="#b9d0b3", stroke="#4c7750", stroke_width=1.8)
    d.box(f["vestibule_mm"], fill="#d9dfbf", stroke="#74803e", stroke_width=1.8)
    d.box(f["side_threshold_mm"], fill="#f0c17f", stroke="#bd834c")
    d.poly(f["front_threshold_polygon_mm"], fill="#f0c17f", stroke="#bd834c")
    for step in f["Q3_incoming_treads"]:
        d.box(step["rect_mm"], fill="none", stroke="#b88b7a", stroke_width=.8)
    option = report["options"][0]
    for spec, func in [(option["front_door"], door), (option["side_door"], side_leaf)]:
        d.line(spec["a"], spec["b"], stroke="#fafbf8", stroke_width=4)
        d.poly(list(func(spec, 90).exterior.coords), fill="#bb9474", stroke="#805534", stroke_width=.8)
    for points, colour in [(report["config"]["daily_arrival_route_mm"][:3], "#277c79"), (report["config"]["inspection_prefix_mm"]+[[2850, 4400]], "#9b753f")]:
        for a, b in zip(points, points[1:], strict=False):
            d.line(a, b, stroke=colour, stroke_width=2, stroke_dasharray="5 3")
    s.text("僅畫RF梯核局部；樓梯洞下方是3F梯段", 40, 135, class_="small")
    s.text("乾式前室", *d.point([350, 4470]), class_="room")
    s.text("完整新到達平台", *d.point([220, 5500]), class_="room")
    s.text("後梯井：不可鋪滿", *d.point([350, 7550]), class_="room")
    s.text("RF側門y4400保原研究位置", 420, 350, class_="room")
    y = 145
    for value in ["綠色完整平台承接Q3後移800mm到達，黃綠前室接回原前門與側門。新的完整平地、同標高與支承是待核條件，並非舊圖證據。",
        "棕色下方示意16個踏步；列明RF地面不蓋其投影。若整塊梯核鋪實心地板，16踏全部受蓋，明列排除。",
        "僅保平台／前室／門檻，2200×3260梯井保持開口；護欄、扶手、梁板、淨高及實際樓板邊界尚未核定。",
        "RF側門y4400保留，不等於三樓也保同門位；Q3三樓側門已到y5270，兩層各看自己的平台及門圖。",
        "前門1130扣兩側115→900；側門1000同口徑→770，巡檢只用700。前門900算式不套到後機位或整機搬運。",
        "外框12.48㎡仍只是研究梯核框，不是合法屋突面積。新前室／到達板可能改有效樓板與申照計算，必須建築／結構同核。",
        "本批沒有跑實際樓梯、梁底或頭部路徑；踏步不被蓋不等於全程安全或消防核可。"]:
        y = s.paragraph(value, 600, y, width=43, step=23)
    return s.output()


def render(report):
    files = {o["id"]+".svg": roof_sheet(report, o) for o in report["options"]}
    files["RF-floor-and-void.svg"] = floor_sheet(report)
    files["door-route-matrix.csv"] = csv_text([{"方案": o["id"], "RF前門": state["front"], "RF側門": state["side"],
        **{key+"阻門": ",".join(value) for key, value in state["route_blockers"].items()}, "成品消防核可": "未知"} for o in report["options"] for state in o["door_states"]])
    files["routes.csv"] = csv_text([{"方案": o["id"], "試線": r["id"], "用途": r["use"], "方塊寬mm": r["width_mm"], "同版條件地面內": r["inside_explicit_same_revision_surface"],
        "碰列明實體": ",".join(r["fixed_body_hits"]), "祭祀投影交集㎡": r["over_protected_sqm"], "操作共用": ",".join(r["shared_operation_ids"]), "實際通行核可": "未知"} for o in report["options"] for r in o["routes"]])
    files["arrival-widths.csv"] = csv_text([{"方案": o["id"], "前門到達方塊mm": r["width_mm"], "新完整平台前室內": r["inside_required_full_platform_and_vestibule"], "真實樓板與成品核可": "未知"} for o in report["options"] for r in o["arrival_width_cases"]])
    files["engineering-replies.csv"] = csv_text([{"問題ID": f"BQR-{n:02d}", "待核": text, **dict.fromkeys(["同版資料圖號", "專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"], "")} for n, text in enumerate(report["config"]["limits"], 1)])
    body = '<h1>B Q3改梯後的RF到達、門路與設備</h1><p class="note">獨立同版研究／未採用。明列新平台與前室條件，保原RF側門位置；原ABC／3D、Q2原梯及RF舊版不改，不沿用舊passed。</p>'
    body += '<p>'+html.escape(report["conclusion"])+"</p>"
    body += table(["項目", "本輪條件"], [["新到達", "x80／y4770／2200×1000mm完整平台，待結構核"], ["前室", "x115／y4015／2170×755mm乾式地面，前／側門檻同版"], ["RF側門", "中心y4400／1000mm名義洞保留，與3F y5270不同層"], ["下樓梯洞", "2200×3260mm保持開口，不可鋪滿"], ["前門／側門", "900／770mm扣框預算；日常與巡檢不混用"]])
    for name, title in [(o["id"]+".svg", o["title"]) for o in report["options"]]+[("RF-floor-and-void.svg", "新平台／前室與不能封閉的下樓梯井")]:
        body += f'<section><h2>{html.escape(title)}</h2><p><a href="{name}">開啟向量圖</a></p><img style="width:100%;height:auto" src="{name}" alt="{html.escape(title)}"></section>'
    body += '<h2>兩案的原代價保留</h2>'+table(["方案", "設備／門後輪廓㎡", "再扣桌架㎡", "日常操作"], [[o["title"], f"{o['front_open_outline_before_daily_furniture_sqm']:.4f}", f"{o['front_open_outline_after_daily_furniture_sqm']:.4f}", "折衣與通行分時" if o["arrival_shares_folding_operation"] else "桌位較獨立，後設備緊"] for o in report["options"]])
    body += '<p>上列面積均含通路，不是完整功能或合法淨面積。原24㎡目標仍缺；前室是室內，不能加算戶外，也不拿後區日常或三樓4㎡天井互抵。</p>'
    body += '<h2>條件與待核</h2>'+ul(report["config"]["limits"])
    body += '<p>'+"／".join(f'<a href="{n}">{n}</a>' for n in files if n.endswith(".csv"))+'</p><p><a href="review.json">來源與幾何JSON</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；樓板與成品、法規、結構、風水、聲學及通風仍未知，未跑瀏覽器／WebGL。</small>'
    files["index.html"] = page("B Q3屋頂同版到達與設備", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-b-q3-roof-coordination-artifacts-v1", "report_hash": report["report_hash"], "source_hashes": report["source_hashes"],
        "adopted": False, "artifacts": {n: hashlib.sha256(value.encode()).hexdigest() for n, value in files.items()}}, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files, out = render(report), ROOT/OUT
        if args.check:
            if any(not (out/n).is_file() or (out/n).read_bytes() != value.encode() for n, value in files.items()):
                raise ValueError("Q3 RF coordination stale")
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, value in files.items():
                (out/name).write_text(value, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "options": 2, "door_cases": 18, "files": len(files),
            "protected_controls": report["protected_controls_unchanged"], "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

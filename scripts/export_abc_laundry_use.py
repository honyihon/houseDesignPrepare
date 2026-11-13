#!/usr/bin/env python3
"""Export bounded laundry flow and illustrative timing sheets; no browsers or new layout."""
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

from house_design.abc_laundry_use import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_upper_replan import Sheet as BaseSheet  # noqa: E402
from scripts.export_builder_communication import page, ul  # noqa: E402

MODE_LABELS = {"wash-and-air": "只洗＋晾衣", "separate-dryer": "洗衣＋獨立乾衣候選", "combined-machine": "單台洗乾候選"}


def duration(minutes):
    hours, mins = divmod(minutes, 60)
    return (str(hours)+"小時" if hours else "")+(str(mins)+"分" if mins or not hours else "")


class Sheet(BaseSheet):
    def __init__(self, title, report):
        self.root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": "0 0 1400 1200",
            "width": "1400", "height": "1200", "role": "img", "aria-label": title})
        self.add("title", text=title)
        self.add("style", text="text{font:17px system-ui,sans-serif;fill:#263e49}.title{font-size:26px;font-weight:700}.small{font-size:13px}.card{font-size:19px;font-weight:700}")
        self.add("rect", x=0, y=0, width=1400, height=1200, fill="#fafbf8")
        self.text(title, 28, 40, class_="title")
        self.text("預先規劃／未採用｜批數、程序與分鐘均為示例，非實際衣量、原廠性能或容量核可。", 28, 78)
        self.text("三棟1F共用一組、C2先暫不用保空間、A上層另留機位；原格局、機位與已驗3D保持。", 28, 106)
        self.text("本批 "+report["report_hash"], 28, 1157, class_="small")
        self.text("尚未選機、確認共享位置或驗證長輩操作。時程不等於衣物適用性、實際乾燥、照護、風水或施工核可。", 28, 1183, class_="small")


def flow_sheet(report):
    s = Sheet("三棟共用洗衣｜晴雨、分戶與長輩使用流程", report)
    for n, (number, title, note) in enumerate(report["config"]["use_steps"]):
        x, y = 35+(n % 3)*455, 150+(n//3)*230
        s.add("rect", x=x, y=y, width=425, height=205, rx=12, fill="#e9eee5", stroke="#8aa08e")
        s.text(number+" "+title, x+17, y+35, class_="card")
        s.paragraph(note, x+17, y+76, width=22, step=25)
    y = 650
    for value in [report["recommendation"],
        "原1200×500mm晾衣含衣物外廓，只是空間預算，不能換成三戶可晾kg數。床單是否掛得開、晴雨乾燥時間與升降承重需實物／產品依據。",
        "一組洗衣不等只留一個插座或一條排水；先保兩機的平放備位，電力同時負載、合法污水、乾衣冷凝水／排氣及獨立排濕依機種核。一般全熱不當除濕保證。",
        "共享取放區須分時；示例採一位操作者，沒有新增籃車或固定櫃的合格停位。門板行程與900通路保持淨空，不能因示例排得下就宣稱空間已足夠。",
        "若集中床品量或雨天輪用超出實際可用時間，先比較分散日期、送洗或其他乾衣安排的代價；不自行增第二組、不取消C2空間或要求長輩上樓。"]:
        y = s.paragraph(value, 45, y, width=73, step=24)
    return s.output()


def timing_sheet(report):
    s = Sheet("輪用時間示例｜機器可並行，人工取放須錯開", report)
    values = report["config"]["illustrative_minutes"]
    daily = {m["mode"]: m for m in report["scenarios"][0]["modes"]}
    x0, width = 260, 1060
    end = max(m["elapsed_min"] for m in daily.values())+60
    scale = width/end
    for minute in range(0, end+1, 120):
        x = x0+minute*scale
        s.add("line", x1=x, y1=160, x2=x, y2=685, stroke="#c9d2c9", stroke_dasharray="4 4")
        s.text(str(minute//60)+"h", x, 149, text_anchor="middle", class_="small")
    x = x0+values["available_window"]*scale
    s.add("line", x1=x, y1=160, x2=x, y2=685, stroke="#a64737", stroke_width=2, stroke_dasharray="7 4")
    s.text("示例可用窗口 "+duration(values["available_window"]), x-8, 713, text_anchor="end", class_="small")
    rows = [("wash-and-air", "washer", "只洗／仍待晾乾", 205),
        ("separate-dryer", "washer", "分機候選：洗衣", 355),
        ("separate-dryer", "dryer", "分機候選：乾衣", 455),
        ("combined-machine", "combined", "單機洗乾候選", 615)]
    for mode, resource, label, y in rows:
        s.text(label, 35, y+25)
        for p in daily[mode]["phases"]:
            if p["resource"] != resource:
                continue
            color = "#87b2c6" if p["kind"] == "program" else "#efb76e"
            s.add("rect", x=x0+p["start_min"]*scale, y=y, width=(p["end_min"]-p["start_min"])*scale,
                height=40, fill=color, stroke="#fafbf8")
            if p["kind"] == "program":
                s.text("批"+str(p["batch"]), x0+(p["start_min"]+p["end_min"])/2*scale, y+26, text_anchor="middle", class_="small")
    s.text("只洗："+duration(daily["wash-and-air"]["elapsed_min"])+"，乾燥時間未知", 260, 280)
    s.text("分機："+duration(daily["separate-dryer"]["elapsed_min"])+"，先假設一批只需一個乾衣程序", 260, 535)
    y = 770
    for value in ["三戶各一批只是示例；藍色是機器程序，橙色是人工裝／取／轉送，橙色彼此不可同時。指定固定間隔排法不是所有可能排程的最短時間。",
        "示例分鐘：洗衣裝15＋程序90＋取轉15；乾衣程序120＋取15；單機裝15＋洗乾程序210＋取15。這些不是市售型號性能，也未計三棟到達或使用者延誤。"]:
        y = s.paragraph(value, 45, y, width=73, step=24)
    for scenario in report["scenarios"]:
        text = scenario["label"]+"："+"；".join(MODE_LABELS[m["mode"]]+duration(m["elapsed_min"])+
            ("（只洗完）" if m["mode"] == "wash-and-air" else "") for m in scenario["modes"])
        y = s.paragraph(text, 45, y, width=73, step=24)
    s.paragraph("床品適用、洗／乾kg容量不同或需分批時，以上排法必須重算；不能用洗衣機kg數代替乾衣機容量，更不能把只洗完當雨天已乾。", 45, y, width=73, step=24)
    return s.output()


def render(report):
    files = {"daily-flow.svg": flow_sheet(report), "capacity-examples.svg": timing_sheet(report)}
    body = '<h1>三棟共用洗衣：日常、床單與雨天輪用</h1><p class="note">所有批數與分鐘均為壓力示例，不是屋主實際衣量、原廠性能或選機結果。共享主位置、真實乾衣容量與長輩操作均未核；原格局不改。</p>'
    body += "<p>"+html.escape(report["recommendation"])+"</p>"
    rows = []
    for scenario in report["scenarios"]:
        for m in scenario["modes"]:
            rows.append([scenario["label"], MODE_LABELS[m["mode"]], duration(m["elapsed_min"]),
                "只洗完，晾乾未知" if m["mode"] == "wash-and-air" else "假設每批一個乾衣程序，未實測",
                str(m["example_batches_in_window"])+"批（示例）"])
    body += '<h2>輪用時間比較</h2><p>窗口先用'+duration(report["config"]["illustrative_minutes"]["available_window"])+"作示例；不是已允許連續運轉或夜間洗衣。</p>"
    body += table(["假設工作量", "配置方向", "示例時間", "完成口徑", "窗口內示例批數"], rows)
    for name, title in [("daily-flow.svg", "先看長輩與晴雨流程"), ("capacity-examples.svg", "再看兩機與人工取放如何錯開")]:
        body += f'<h2>{title}</h2><p><a href="{name}">開向量圖</a></p><img style="width:100%;height:auto" src="{name}" alt="{title}">'
    body += '<h2>先跟建商／A設計師對齊的接口</h2>'+table(["原議題ID", "主題", "待資料後核對"], report["config"]["engineering_interfaces"])
    body += '<h2>保留的限制</h2>'+ul(report["config"]["limits"])
    body += '<p>實際容量是否足夠：未知；晾乾時間：未知。'+str(len(report["actual_conditions"]))+'欄實際條件全空，不把未知當0。回饋沿原ABC-DAILY-CHAIN與LAU-03～08，不另要求重填需求。</p>'
    body += '<p><a href="actual-conditions-template.json">空白實際條件JSON</a>／<a href="actual-conditions.csv">空白條件CSV</a>／<a href="review.json">來源報告</a>／<a href="artifact-manifest.json">產物清單</a>／<a href="../../planning/design-discussion-basis/life-walkthrough.html#laundry-use">原討論包生活頁</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；只有檔案與示例排程檢查，未啟動瀏覽器、實機、長輩操作或專業驗收。</small>'
    files["index.html"] = page("ABC洗衣輪用與雨天預規劃", body)
    files["actual-conditions-template.json"] = json.dumps(report["actual_conditions"], ensure_ascii=False, indent=2)+"\n"
    files["actual-conditions.csv"] = csv_text([{"欄位": key, "實際值": "", "來源與圖號版次": ""} for key in report["actual_conditions"]])
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-abc-laundry-use-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "adopted": False,
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
                raise ContractError("Laundry use outputs stale: "+", ".join(stale))
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, value in files.items():
                (out/name).write_text(value, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "files": len(files), "drawings": 2,
            "hypothetical_workloads": len(report["scenarios"]), "actual_conditions": len(report["actual_conditions"]),
            "actual_capacity_sufficient": None, "protected_controls": report["protected_controls_unchanged"],
            "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export one laundry rough-in discussion sheet without sizing systems or locating services."""
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

from house_design.abc_laundry_roughin import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_upper_replan import Sheet as BaseSheet  # noqa: E402
from scripts.export_builder_communication import page, ul  # noqa: E402


class Sheet(BaseSheet):
    def __init__(self, report):
        self.root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": "0 0 1400 1200",
            "width": "1400", "height": "1200", "role": "img", "aria-label": "洗衣預埋前八項接口與三處機位用途"})
        self.add("title", text="洗衣預埋前八項接口與三處機位用途")
        self.add("style", text="text{font:17px system-ui,sans-serif;fill:#263e49}.title{font-size:26px;font-weight:700}.small{font-size:13px}.card{font-size:19px;font-weight:700}")
        self.add("rect", x=0, y=0, width=1400, height=1200, fill="#fafbf8")
        self.text("洗衣預埋前溝通單｜先保接口，實際資料後再定位", 28, 40, class_="title")
        self.text("預先討論／未採用｜本圖不按比例，沒有施工點位或管線路徑；電壓、管徑、高度及外口仍未知。", 28, 78)
        self.text("先確認合法共用位置與產品，再由建商、A設計師及相應專業同版核對；未購機、未授權開孔或施工。", 28, 106)
        self.text("本批 "+report["report_hash"], 28, 1157, class_="small")
        self.text("原ABC、已驗ZIP及舊交付保持。來源／檔案檢查不等產品、風水、照護、機電或施工核可。", 28, 1183, class_="small")


def interface_sheet(report):
    s = Sheet(report)
    for n, row in enumerate(report["interfaces"]):
        x, y = 30+(n % 2)*685, 135+(n//2)*170
        s.add("rect", x=x, y=y, width=655, height=155, rx=9, fill="#e8eee5", stroke="#8aa08e")
        s.text(row["label"], x+14, y+28, class_="card")
        s.text(row["before"]+"｜"+"／".join(row["laundry_ids"]), x+14, y+50, class_="small")
        s.paragraph(row["prepare"], x+14, y+77, width=36, step=22)
    s.text("三處用途分開，沒有增加已決定啟用的洗衣機數量", 30, 836, class_="card")
    for n, row in enumerate(report["locations"]):
        x, y = 30+n*455, 858
        s.add("rect", x=x, y=y, width=425, height=242, rx=9, fill="#e5edf0", stroke="#8b9fa7")
        yy = s.paragraph(row["label"], x+14, y+29, width=21, step=24)
        s.paragraph(row["preserve"], x+14, yy+12, width=22, step=23)
    return s.output()


def render(report):
    files = {"roughin-interfaces.svg": interface_sheet(report)}
    body = '<h1>洗衣預埋前：給排水、電力、排濕與維修</h1><p class="note">這是預先溝通單，未選共用主位置、機型或施工點位，未決定管徑／電氣規格、外口或採購。原格局及已驗3D不改；有圖不等核准施工。</p>'
    body += "<p>"+html.escape(report["recommendation"])+"</p>"
    body += '<p><a href="roughin-interfaces.svg">開單頁接口圖</a></p><img style="width:100%;height:auto" src="roughin-interfaces.svg" alt="洗衣預埋前八項接口與三處機位用途">'
    body += '<h2>三處保留用途</h2>'+table(["位置", "保留範圍"], [[r["label"], r["preserve"]] for r in report["locations"]])
    body += '<h2>依既有議題交給建商與A設計師</h2>'+table(["接口", "最晚核對時點", "現在先保留", "資料到齊後須核", "原問題／A接口", "建議窗口，未議定"],
        [[r["label"], r["before"], r["prepare"], r["required"], "／".join(r["question_ids"]+r["a_interface_ids"]), r["proposed_window"]]
            for r in report["interfaces"]])
    body += '<h2>乾衣兩方向，接口分別核</h2>'+table(["研究方向", "要保的條件", "仍有的限制"],
        [[r["label"], r["keep"], r["condition"]] for r in report["config"]["dryer_alternatives"]])
    body += '<h2>收到資料後怎麼處理</h2>'+ul([
        "先核共用位置／合法通路及完成牆柱，再核同型號的機身、全開門、接管、散熱及整機換出；不把850×750預算當實際產品核可。",
        "機電依產品及現場條件出同版點位、系統與剖面，所有數值注明依據；完成設計審查、費用與工期確認後，施工圖另行發行。",
        "埋管、套管、防水與封板等工序前，沿原檢查表記通知／試驗／照片／缺失覆查；本頁未代填任何通過。",
        "A設計師另談裝潢，預埋與保固分界由建商共同核；C2暫不用仍保恢復路線，不封死公共排水或通氣。",
        "回覆用原builder-replies.csv的BC問題列、a-interface-matrix.csv及inspection-log.csv，不另加必填表；報價仍按原範圍拆明預留／實作／選配。"])
    body += '<p>'+str(len(report["actual_conditions"]))+'欄實際條件仍全空，空白不是0或不需要；另存副本補資料，不讀私人回覆或自動套圖。</p>'
    body += '<p><a href="actual-conditions-template.json">空白條件JSON</a>／<a href="actual-conditions.csv">空白條件CSV</a>／<a href="review.json">同版報告</a>／<a href="artifact-manifest.json">產物清單</a>／<a href="../../planning/design-discussion-basis/systems.html#laundry-roughin">原討論包設備頁</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；30項父來源與149保護項保持。靜態文件核對，未啟動瀏覽器、實機或專業驗收。</small>'
    files["index.html"] = page("ABC洗衣預埋與交接接口", body)
    files["actual-conditions-template.json"] = json.dumps(report["actual_conditions"], ensure_ascii=False, indent=2)+"\n"
    files["actual-conditions.csv"] = csv_text([{"欄位": key, "實際值": "", "依據圖號版次": ""} for key in report["actual_conditions"]])
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-abc-laundry-roughin-artifacts-v1", "report_hash": report["report_hash"],
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
            stale = [n for n, v in files.items() if not (out/n).is_file() or (out/n).read_bytes() != v.encode()]
            if stale:
                raise ContractError("Laundry rough-in outputs stale: "+", ".join(stale))
        else:
            out.mkdir(parents=True, exist_ok=True)
            for n, value in files.items():
                (out/n).write_text(value, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "files": len(files), "drawings": 1,
            "interfaces": len(report["interfaces"]), "location_scopes": len(report["locations"]),
            "actual_conditions": len(report["actual_conditions"]), "protected_controls": 149,
            "point_design_or_construction_release": False, "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

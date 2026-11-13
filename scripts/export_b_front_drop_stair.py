#!/usr/bin/env python3
"""Export bounded ground landing/tread conflict drawings; no scene or browser."""
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

from house_design.b_front_drop_stair import OUT, build  # noqa: E402
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
        self.text("P4原1F落管位置的局部反例／未採用｜四位置均不直接套現行梯門；未改格局或併主3D。", 28, 76)
        self.text("本批 "+report["report_hash"], 28, 1158, class_="small")
        self.text("局部平台／踏步只作篩檢，非全域無解證明，亦非結構、風水、消防、搬轎、照護或施工核可。", 28, 1182, class_="small")


def landing_sheet(report):
    s = Sheet("B P4落水｜原候選占入口平台，四個位置各有衝突", report)
    screen = report["stair_screen"]
    d = Draw(s, (45, -275), .13)
    d.box([0, 3900, 2400, 5200], fill="#edf0e9", stroke="#607c73")
    d.box(screen["landing_mm"], fill="#d9dfbf", stroke="#74803e")
    d.box(screen["central_gap_mm"], fill="#dae3e7", stroke="#75929d", stroke_dasharray="5 3")
    for step in screen["treads"]:
        d.box(step["rect_mm"], fill="#e2e6df", stroke="#7c9484", stroke_width=.8)
    for candidate in screen["candidates"]:
        d.box(candidate["rect_mm"], fill="#e6b2a3", fill_opacity=.7, stroke="#b95142", stroke_width=2)
        s.text(candidate["id"], *d.point([candidate["rect_mm"][0], candidate["rect_mm"][1]-30]), class_="room")
    for route in screen["local_routes"]:
        for a, b in zip(route["points_mm"], route["points_mm"][1:], strict=False):
            d.line(a, b, stroke="#277c79", stroke_width=2, stroke_dasharray="4 3")
    s.text("街門名義中心x1200", 45, 175, class_="small")
    s.text("側門名義中心y4400 →", 365, 292, class_="small")
    s.text("兩條700局部試線；未模擬門片", 45, 960, class_="small")
    y = 145
    for value in ["G0原400×400占完整入口平台0.16㎡。不是已留的免費空井；列明街門／側門至左跑的兩條局部方塊都被切到。",
        "G1右前角避街門那一條，仍碰側門內到達；不能只說家具沒撞就判一樓不受影響。",
        "G2想放中央，但兩跑各1000、總幅2200只剩200mm縫，400井超出縫並碰左右踏步投影。",
        "G3左跑下方的直立柱穿列明低踏步，不能把樓梯下方全部當垂直貫通空間。",
        "四位置都是反例，沒有找到可直接套用的落水。需重新整合井、平台與真實梁板；不宣稱所有建築解法無效。",
        "兩入口各三態原來源保留；只核G0與房界／器具及局部平台，沒有重演完整搬轎、門扇或照護路線。",
        "街／側門只有名義中心，700試線也不當法定寬、扶手後完成淨寬或逃生核可。原24級、踏面270及1000單跑不減。"]:
        y = s.paragraph(value, 590, y, width=43, step=24)
    return s.output()


def section_sheet(report):
    s = Sheet("B一樓梯｜400直立柱不能穿踏步，中央200不是400井", report)
    screen = report["stair_screen"]
    z0, z1 = screen["hypothetical_column_z_mm"]
    def x(value):
        return 60+(value-3900)*.15
    def y(value):
        return 1030-value*.16
    s.text("左跑局部側視：不是施工剖面，踏步僅畫示意頂面", 45, 140)
    s.add("line", x1=x(3900), y1=y(0), x2=x(9100), y2=y(0), stroke="#64766b")
    for step in screen["treads"]:
        if step["id"].startswith("left"):
            r = step["rect_mm"]
            s.add("line", x1=x(r[1]), y1=y(step["top_z_mm"]), x2=x(r[1]+r[3]), y2=y(step["top_z_mm"]), stroke="#64766b", stroke_width=3)
    for candidate in screen["candidates"]:
        if candidate["id"] not in {"G0", "G3"}:
            continue
        r = candidate["rect_mm"]
        s.add("rect", x=x(r[1]), y=y(z1), width=r[3]*.15, height=(z1-z0)*.16, fill="#e6b2a3", fill_opacity=.6, stroke="#b95142")
        s.text(candidate["id"]+"假直立柱", x(r[1]), y(z1)-15, class_="small")
    s.text("柱頂3504.4只是P4最有利預算平面，非真實接入標高", 45, 1115, class_="small")
    ytext = 170
    for value in ["G0在平台邊緣，不碰列明踏面卻擋平台局部試線；不碰踏步不等於可用。",
        "G3覆左跑第2、3、4示意踏步，頂高約333／500／667mm。直立400柱貫到3504.4時會穿這些高程。",
        "G2中央超寬後同時碰左右共六個示意踏步；樓梯板、梯梁、扶手與支承尚未有真實剖面。",
        "保兩跑1000而加400井，名義總幅至少2400，比原2200多200，還沒計井壁／結構。",
        "照原外緣加200至右側，名義梯核新增帶會占祭祀前廳1.04㎡；未取得屋主允許，也不是可採用小改。",
        "需要建築／結構／機電在新建設計階段整合，不能先畫一條穿梯板的水管再讓現場想辦法。"]:
        ytext = s.paragraph(value, 875, ytext, width=27, step=24)
    return s.output()


def consequence_sheet(report):
    s = Sheet("B前排水｜能先保留什麼、哪些必須重排", report)
    y = 145
    for value in ["目前結論：P4縮短三條2F假支管，但原G0一樓落水不再當可直接沿用。27個高度例中最有利的4.4mm餘量不能抵消平台衝突。",
        "保留：P4原尺寸器具／兩衛外窗方向與共牆井研究；原P1／P2／P3、Q3及1F後門搬轎預設／無後巷前門備案全部保留。",
        "優先設計工作：建築師重整井、入口平台與樓梯構造；同核真實梁板、降板／高程、立管清掃、防火、聲學及合法終端。",
        "硬條件：不縮原單跑1000、不把騎樓當可落地井、不侵神明堂／乾背或武轎庫、不未經同意取消側門與前門備案。",
        "替代不是自動採用：P1少改但濕茶水未落位；改濕區拓樸要同時保面積與外窗。泵、粉碎或抬地坪有維修／停電與階差代價，不是預設。",
        "可先準備：帶標高的梁板／完整梯段／兩入口平台剖面、真實器具排口及立管容量／清掃資料、完整費用工期與功能代價。現在無需屋主補量測。",
        "四位置無解只限本輪局部模型，不代表整棟不能建；未作全域搜尋、正式結構／法規設計或全程人體／搬運演練。",
        "如需第二模型提出更好拓樸，已備Claude工具關閉的獨立討論稿，長任務交屋主另一終端執行；本輪沒有取得回應或共識。"]:
        y = s.paragraph(value, 45, y, width=78, step=25)
    s.text("交給建商時：不要只拿P4短管圖就進施工，必須附這張一樓衝突與同版剖面條件。", 45, 1050)
    return s.output()


def render(report):
    files = {"ground-landing-candidates.svg": landing_sheet(report), "stair-column-section.svg": section_sheet(report), "design-consequences.svg": consequence_sheet(report)}
    files["candidate-conflicts.csv"] = csv_text([{"候選": r["id"], "說明": r["label"], "平台交集㎡": r["landing_overlap_sqm"],
        "碰局部路線": "/".join(q["route"] for q in r["local_route_hits"]), "碰踏步": "/".join(q["id"] for q in r["tread_hits_in_hypothetical_vertical_column"]),
        "狀態": r["status"], "可直接採用": False} for r in report["stair_screen"]["candidates"]])
    files["ground-state-checks.csv"] = csv_text(report["ground_states"])
    files["tread-column-hits.csv"] = csv_text([{"候選": r["id"], **q, "真實接入及結構核可": "未知"} for r in report["stair_screen"]["candidates"] for q in r["tread_hits_in_hypothetical_vertical_column"]])
    files["engineering-replies.csv"] = csv_text([{"ID": f"GDS-{i:02d}", "待核": value,
        **dict.fromkeys(["同版圖號與依據", "建築機電結構回覆", "費用工期及保固", "窗口", "期限", "屋主選擇", "審查及施工圖發行"], "")} for i, value in enumerate(report["config"]["limits"], 1)])
    body = '<h1>B前排水一樓落點：平台與踏步不能當空井</h1><p class="note">四個明列位置均不能直接套現行梯門，未採用；局部反例不是全域無解證明。P4三條短管保留研究，1F落水仍須重排，不併主3D。</p>'
    body += "<p>"+html.escape(report["conclusion"])+"</p>"
    for name, title in [("ground-landing-candidates.svg", "原平台與四個400候選位置"), ("stair-column-section.svg", "直立柱碰踏步與中央200mm限制"), ("design-consequences.svg", "保留、重排及替代條件")]:
        body += f'<section><h2>{html.escape(title)}</h2><p><a href="{name}">開啟向量圖</a></p><img src="{name}" style="width:100%;height:auto" alt="{html.escape(title)}"></section>'
    body += '<h2>兩入口各三態保持原來源</h2>'+table(["版本", "狀態", "G0占平台㎡", "G0占騎樓㎡", "已核可搬運"], [[r["option"], r["state"], r["G0_over_entrance_landing_sqm"], r["G0_over_arcade_sqm"], "否，未重演"] for r in report["ground_states"]])
    body += '<h2>建議先做</h2>'+ul(report["recommended_sequence"])+"<h2>假設與限制</h2>"+ul(report["config"]["limits"])
    body += '<p>'+"／".join(f'<a href="{n}">{n}</a>' for n in files if n.endswith(".csv"))+'</p><p><a href="review.json">來源與幾何JSON</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；無實測、產品或專業核可，未執行瀏覽器／WebGL、轉圖、外部AI或主3D生成。</small>'
    files["index.html"] = page("B前排水一樓落點與樓梯", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-b-front-drop-stair-artifacts-v1", "report_hash": report["report_hash"], "source_hashes": report["source_hashes"],
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
            if any(not (out/n).is_file() or (out/n).read_bytes() != value.encode() for n, value in files.items()):
                raise ValueError("Ground-drop stair screen stale")
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, value in files.items():
                (out/name).write_text(value, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "files": len(files), "candidates": 4,
            "ground_states": len(report["ground_states"]), "all_listed_candidates_conflict": report["stair_screen"]["all_listed_candidates_conflict"],
            "protected_controls": report["protected_controls_unchanged"], "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

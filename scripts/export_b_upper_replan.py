#!/usr/bin/env python3
"""Export six bounded static sheets for B upper-floor alternatives; no browsers or 3D."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import textwrap
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.b_upper_replan import OUT, build, door  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_builder_communication import page, ul  # noqa: E402

NS = "http://www.w3.org/2000/svg"


class Sheet:
    def __init__(self, title, report, height=1200):
        self.root = ET.Element("svg", {"xmlns": NS, "viewBox": f"0 0 1400 {height}", "width": "1400", "height": str(height),
            "role": "img", "aria-label": title})
        self.add("title", text=title)
        self.add("style", text="text{font:17px system-ui,sans-serif;fill:#263e49}.title{font-size:26px;font-weight:700}.small{font-size:13px}.room{font-size:13px;font-weight:650}")
        self.add("rect", x=0, y=0, width=1400, height=height, fill="#fafbf8")
        self.text(title, 28, 40, class_="title")
        self.text("獨立重排比較／未採用｜mm座標；前陽台改室內為重大代價，須正式建築設計，不可自行封陽台。", 28, 76)
        self.text("來源 "+report["source_layout_report_sha256"][:16]+"…｜本批 "+report["report_hash"][:16]+"…", 28, height-42, class_="small")
        self.text("指定平面幾何不等於法規／風水／照護／搬運／產品或施工核可。前排水及結構未完成；原ABC／3D保留。", 28, height-18, class_="small")

    def add(self, tag, text=None, **attrs):
        el = ET.SubElement(self.root, tag, {k.rstrip("_").replace("_", "-"): str(v) for k, v in attrs.items()})
        el.text = text
        return el

    def text(self, value, x, y, **attrs):
        return self.add("text", text=value, x=x, y=y, **attrs)

    def paragraph(self, text, x, y, width=42, step=26):
        lines = textwrap.wrap(text, width=width)
        for n, line in enumerate(lines):
            self.text(line, x, y+n*step)
        return y+len(lines)*step+12

    def output(self):
        return ET.tostring(self.root, encoding="unicode")+"\n"


class Draw:
    def __init__(self, sheet, origin=(60, 140), scale=.052):
        self.s, self.origin, self.scale = sheet, origin, scale

    def point(self, p):
        return [self.origin[0]+p[0]*self.scale, self.origin[1]+p[1]*self.scale]

    def poly(self, points, **attrs):
        return self.s.add("polygon", points=" ".join(",".join(str(v) for v in self.point(p)) for p in points), **attrs)

    def box(self, r, **attrs):
        x, y = self.point(r)
        return self.s.add("rect", x=x, y=y, width=r[2]*self.scale, height=r[3]*self.scale, **attrs)

    def line(self, a, b, **attrs):
        x, y = self.point(a)
        xx, yy = self.point(b)
        return self.s.add("line", x1=x, y1=y, x2=xx, y2=yy, **attrs)

    def floor(self, floor, report):
        colors = {"wet": "#dceff4", "bedroom": "#f1e7cd", "high-activity": "#e8dff2"}
        labels = {"stair": "原梯核", "quiet-living": "安靜起居／閱讀", "dry-protection": "乾保護室", "public-bath": "前公衛",
            "front-open": "前開放帶", "tea-foyer": "茶水／前室", "master": "主臥乾區", "private-bath": "套衛", "guest": "客房", "ktv-study": "娛樂候選"}
        from shapely.geometry import Polygon
        for r in floor["rooms"]:
            self.poly(r["polygon_mm"], fill=colors.get(r["kind"], "#edf0e9"), stroke="#607c73", stroke_width=1)
            centre = Polygon(r["polygon_mm"]).representative_point()
            x, y = self.point([centre.x, centre.y])
            self.s.text(labels[r["id"]], x, y, text_anchor="middle", class_="room")
            for item in r["items"]:
                self.box(item["rect_mm"], fill="#b9c9be", stroke="#3c6355", stroke_width=.8)
            for shaft in r["shafts_mm"]:
                self.box(shaft, fill="#ca9d8b", stroke="#9c4634", stroke_width=1)
            for window in r["windows_mm"]:
                self.line(window[:2], [window[0]+window[2], window[1]], stroke="#1a9ac0", stroke_width=4)
            for spec in r["doors"]:
                self.line(spec["a"], spec["b"], stroke="#fafbf8", stroke_width=4)
                self.poly(list(door(spec, 90).exterior.coords), fill="#be987d", stroke="#875137", stroke_width=.8)
        for route in floor["routes"]:
            for a, b in zip(route["points_mm"], route["points_mm"][1:], strict=False):
                self.line(a, b, stroke="#3a8f78", stroke_width=1.8, stroke_dasharray="5 3")
        self.s.text("道路／前方", *self.point([3000, -350]), text_anchor="middle")
        self.s.text("6000 × 17630mm；1F騎樓前帶不改", *self.point([0, 18100]), class_="small")


def plan_sheet(report, option, floor):
    title = option["label"]+"｜"+("2F" if floor["id"] == "floor-2" else "3F")
    s = Sheet(title, report)
    d = Draw(s)
    d.floor(floor, report)
    y = 145
    values = {a["id"]: a["net115_sqm"] for a in floor["areas"]}
    order = ["quiet-living", "master", "public-bath", "private-bath", "tea-foyer", "guest", "ktv-study"]
    for key in order:
        if key in values:
            label = next(r["label"] for r in floor["rooms"] if r["id"] == key)
            y = s.paragraph(label+f"：{values[key]:.4f}㎡（115mm假設）", 440, y)
    notes = [option["conclusion"], "藍色為候選濕區、米色為睡眠乾區、紫色為娛樂候選；虛線只是列明方塊試線。",
        "所有濕／睡眠／高活動輪廓避開名義神明堂及乾背櫃；濕區另避武轎庫。管線、牆體及振動未核，不能稱全案風水通過。",
        "公衛朝前、套衛朝後，側界未畫假窗。公衛框線只代表候選直接外口；獨排補氣、防雨隱私與有效開口待核。",
        "門畫全開，半開及關閉仍可能阻路。梯廳新接茶水前室是否需門，及原1000門能否達900淨寬，均未核。"]
    if floor["id"] == "floor-3":
        notes += ["娛樂區扣0.16㎡後通氣井僅14.3141㎡，低於原20㎡目標。若聲學構造再吃面積，14㎡下限也可能不成立；與客房共牆及法器櫃振動待評。",
            "客房床頭靠左實牆，100mm乾擋板阻中軸視線；床尾約635mm，未當700mm全環繞或照護空間。"]
        notes += [f"娛樂區仍投影二樓主臥乾區{option['upper_stack']['third_entertainment_over_second_master_sqm']:.4f}㎡；即使未壓床體，也不是夜間隔音／振動成立。"]
    for text in notes:
        y = s.paragraph(text, 440, y)
    return s.output()


def frontage_sheet(report):
    s = Sheet("B前側代價｜P2室內／景觀／設備重新分區", report, height=1120)
    o = report["options"][1]
    spec = report["config"]["floors"]["options"][1]
    d = Draw(s, (45, 150), .115)
    d.box(spec["enclosure_rect_mm"], fill="#dceff4", stroke="#607c73", stroke_width=2)
    d.line([0, 1980], [3270, 1980], stroke="#607c73", stroke_width=2)
    d.poly(spec["garden_polygon_mm"], fill="#e8efce", stroke="#708738", stroke_width=2)
    for r in spec["soil_rects_mm"]:
        d.box(r, fill="#96b573", stroke="#708738")
    for r in spec["outdoor_service_mm"]:
        d.box(r, fill="none", stroke="#ba823e", stroke_dasharray="5 3")
    for r in spec["outdoor_units_mm"]:
        d.box(r, fill="#c7d4d6", stroke="#52676d")
    for a, b in zip(o["frontage"]["outdoor_700_route"]["points_mm"], o["frontage"]["outdoor_700_route"]["points_mm"][1:], strict=False):
        d.line(a, b, stroke="#286a84", stroke_width=2, stroke_dasharray="5 3")
    s.text("公衛：5.1600㎡", 90, 265)
    s.text("茶水前室：5.1376㎡", 90, 485)
    s.text("設備與拆換不當綠化", 840, 185)
    s.text("前室內新增名義12.753㎡／層", 50, 675)
    y = 235
    for text in ["景觀比較區7.156㎡，覆土投影2.52㎡，約35.22%；四株木本僅示意，土深／荷重／資格未核。",
        "兩台室外機數量／代表尺寸及原1350mm深維修預算保留；左機移到x3270，不借舊冷媒路線稱完成。",
        "700mm平面試線繞土區到設備，並非實際原廠維修／輪椅或熱回流驗證。",
        "新室內必須列入正式可建量和結構設計，不再享原陽台的面積計法；整體仍在約32地坪研究框內，不代表申照可建。"]:
        y = s.paragraph(text, 820, y, width=28)
    y = 735
    for text in ["1F仍保留6000×3900通行帶；不能用新增落地排水井擋騎樓。", "前公衛／茶水是否能落地排水是本案先決缺口，詳下一張剖面表，不因房間面積達標而略過。"]:
        y = s.paragraph(text, 50, y, width=70)
    return s.output()


def drainage_sheet(report):
    s = Sheet("B工程先決缺口｜騎樓、前落水與兩個入口版本", report)
    d = report["drainage"]
    y = 135
    for text in [d["summary"], *d["notes"]]:
        y = s.paragraph(text, 35, y, width=75)
    s.text("P2假設2F +4000，偏移3900mm／坡1:50降78mm，再留50mm；不是實際梁板／管徑或規定坡度。", 35, y+8)
    y += 55
    for row in d["section_sensitivity"]:
        s.text(f"結構 {row['structure_mm']} + 管含支撐 {row['pipe_support_mm']} → 淨高 {row['remaining_clear_mm']:.0f}mm；比較目標3500", 50, y)
        y += 32
    y += 20
    s.text("P1對應直線偏移2400mm，假設坡降48mm；仍有同一梯核落水及騎樓淨高缺口。", 35, y)
    y += 40
    for o in d["ground_options"]:
        s.text(o["id"]+"：日常／祭祀／搬運來源不改，後井在1F浴室列明本體未撞。", 35, y)
        y += 32
        s.text(f"前落水候選占原梯核預留 {o['front_downpipe_over_stair_reserved_box']:.2f}㎡，不是免費管井；1F轉位／淨高／消防仍待重核。", 35, y)
        y += 44
    s.paragraph("結論：P2是保住面積與外窗的研究方向，必須先由建築／結構／機電證明前室內與排水成立；不成立就退回P1／重新換位，不可改口說後巷可排或借用騎樓。", 35, y+10, width=75)
    return s.output()


def render(report):
    files = {}
    for index, option in enumerate(report["options"], 1):
        for floor in option["floors"]:
            files[f"P{index}-{floor['id']}.svg"] = plan_sheet(report, option, floor)
    files["frontage.svg"], files["drainage.svg"] = frontage_sheet(report), drainage_sheet(report)
    comparison = []
    for option in report["options"]:
        for goal in option["goals"]:
            comparison.append({"方案": option["label"], "目標": goal["id"], "115模型或景觀值㎡": goal["value_sqm"],
                "原目標㎡": goal["target_sqm"], "僅指定假設達標": goal["target_met_in_115_model"],
                "全案採用": "否", "實際可建": "未知"})
    files["area-comparison.csv"] = csv_text(comparison)
    files["engineering-replies.csv"] = csv_text([{"問題ID": f"BUP-{n:02d}", "待核": text,
        **dict.fromkeys(["資料與圖號版次", "專業回覆", "成本工期代價", "負責窗口", "期限", "屋主選擇", "審查或發行依據"], "")}
        for n, text in enumerate(report["config"]["open_items"], 1)])
    cards = []
    for index, o in enumerate(report["options"], 1):
        rows = [[v["id"], f"{v['value_sqm']:.4f}", str(v["target_sqm"]), "僅本假設達標" if v["target_met_in_115_model"] else "原目標仍缺"] for v in o["goals"]]
        cards.append("<section><h2>"+html.escape(o["label"])+"</h2><p>"+html.escape(o["conclusion"])+
            '</p><div class="table">'+table(["項目", "比較㎡", "原目標㎡", "狀態"], rows)+"</div>"+
            "".join(f'<p><a href="P{index}-{fid}.svg">開啟{fid}向量圖</a></p><img style="width:100%;height:auto" src="P{index}-{fid}.svg" alt="P{index} {fid}獨立比較">' for fid in ["floor-2", "floor-3"])+"</section>")
    body = ('<h1>B棟上層整層重排比較</h1><p class="note">獨立比較／未採用。原ABC、3D、後門預設與前門備案均保留。'
        'P2在指定假設下保20／5／6㎡及兩衛外窗方向，但前側新增室內、排水和結構尚未成立，不能當可以直接建造。</p>'
        '<p>原後段固定分配不足，新的方向是把公衛前置，後段改主臥＋後右套衛。不是再將舊房間微移100mm，也不假設側界有窗。</p>'
        '<p>外框6000×17630mm＝105.78㎡，約31.99845地坪。這只核概念外框，所有建蔽、容積、法定空地、騎樓及前室內量體須正式建築設計。</p>'
        '<p><a href="../../../Docs/b-upper-replan-v1.md">使用說明</a>／<a href="area-comparison.csv">面積表</a>／<a href="engineering-replies.csv">先決工程回覆</a>／'
        '<a href="../b-claude-round3-v1/index.html">原第三輪基線</a>／<a href="../../planning/design-discussion-basis/index.html">ABC討論包</a></p>')
    body += "".join(cards)
    body += '<section><h2>前側室內／景觀與設備代價</h2><img style="width:100%;height:auto" src="frontage.svg" alt="前側重新分區"><h2>不能略過的排水剖面</h2><img style="width:100%;height:auto" src="drainage.svg" alt="騎樓排水假設與缺口"></section>'
    body += "<h2>先解這些，才能談採用</h2>"+ul(report["config"]["open_items"])
    body += '<p><a href="review.json">完整幾何、路徑與反例JSON</a>／<a href="artifact-manifest.json">產物雜湊</a></p><small>來源 '+report["report_hash"]+'；未啟動瀏覽器／WebGL，未取得專業、宗教、照護、搬運或施工核可。</small>'
    files["index.html"] = page("B上層整層重排比較", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    manifest = {"schema": "house-b-upper-replan-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "adopted": False,
        "artifacts": {n: hashlib.sha256(data.encode()).hexdigest() for n, data in files.items()}}
    files["artifact-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    try:
        r = build(ROOT)
        files, out = render(r), ROOT/OUT
        if args.check:
            changed = [n for n, value in files.items() if not (out/n).is_file() or (out/n).read_bytes() != value.encode()]
            if changed:
                raise ContractError("B upper comparison stale: "+", ".join(changed))
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (out/name).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "options": len(r["options"]),
            "floors": sum(len(o["floors"]) for o in r["options"]), "files": len(files),
            "protected_controls": r["protected_controls_unchanged"], "primary_3d_changed": False,
            "adopted": False, "professional_approval": "unknown", "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

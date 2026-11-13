#!/usr/bin/env python3
"""Static C whole-ground-floor comparison; no browser or scene runtime."""
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

from house_design.c_ground_coordination import OUT, build  # noqa: E402
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
        self.text("獨立完整1F比較／未採用｜原ABC、3D與上層不改；115mm完成預算，實際門組、照護及施工未核。", 28, 76)
        self.text("本批來源 "+report["report_hash"], 28, 1158, class_="small")
        self.text("只有指定名義幾何；不沿用舊passed，不當產品、風水、照護、救援、消防、法規或施工核可。", 28, 1182, class_="small")


def floor_drawing(sheet, report, origin=(45, 135), scale=.052):
    d = Draw(sheet, origin, scale)
    short = {"garage": "騎樓／接送", "entrance": "乾前室／鞋櫃", "living": "客廳", "dining": "四人餐桌", "living-hall": "客餐通行",
        "living-right": "前室共享", "kitchen": "一字廚房", "stair1f": "24級梯段", "sliding-door": "照護走道", "sideyard": "照護前室／IDF",
        "elder": "孝親房", "elder-bath": "側盆照護浴室", "public-bath": "獨立訪客公衛", "service": "後通風830"}
    for room in report["rooms"]:
        color = "#dceff4" if "bath" in room["id"] else "#f1e7cd" if room["id"] == "elder" else "#edf0e9"
        d.box(room["rect_mm"], fill=color, stroke="#82958f", stroke_width=.8, stroke_dasharray="3 2")
        x, y, w, h = room["rect_mm"]
        sheet.text(short[room["id"]], *d.point([x+w/2, y+h/2]), text_anchor="middle", class_="room")
        for item in room["items"]:
            d.box(item["body_mm"], fill="#b9c9be", stroke="#3c6355", stroke_width=.7,
                fill_opacity=.55 if item["shape"] == "wall-tv" else 1)
        f = room["source_features"]
        if f.get("window_mm") and f.get("window_face") in {"front", "rear"}:
            cx = x+w*f.get("window_ratio", .5)
            yy = y if f["window_face"] == "front" else y+h
            d.line([cx-f["window_mm"]/2, yy], [cx+f["window_mm"]/2, yy], stroke="#168cae", stroke_width=3)
    d.box([3720, 9760, 1000, 2970], fill="#c9ced7", stroke="#5d687b")
    d.box([4920, 9760, 1000, 2970], fill="#c9ced7", stroke="#5d687b")
    d.box([3720, 12730, 2200, 1000], fill="#e0e3e9", stroke="#5d687b")
    d.box([3720, 8760, 2200, 1000], fill="none", stroke="#5d687b", stroke_dasharray="4 3")
    for y in range(9760, 12731, 270):
        d.line([3720, y], [4720, y], stroke="#758195", stroke_width=.5)
        d.line([4920, y], [5920, y], stroke="#758195", stroke_width=.5)
    gate = report["front_gate"]
    d.box([2400, 8500, 3600, 100], fill="#737e79")
    d.line([2900, 8550], [4100, 8550], stroke="#fafbf8", stroke_width=6)
    for p in report["care_door_parts"]["open"]:
        d.poly(p["polygon_mm"], fill="#bb9474", stroke="#805534", stroke_width=.7)
    for a, b in [([0, 13800], [3600, 13800]), ([3600, 13800], [3600, 16800]), ([4000, 5700], [6000, 5700])]:
        d.line(a, b, stroke="#607c73", stroke_width=1.7)
    for a, b in [([2250, 13800], [3450, 13800]), ([3600, 14575], [3600, 15775]), ([4100, 5700], [5000, 5700])]:
        d.line(a, b, stroke="#fafbf8", stroke_width=3)
    for r in report["review"]["routes"][:3]:
        for a, b in zip(r["points_mm"], r["points_mm"][1:], strict=False):
            d.line(a, b, stroke="#277c79" if r["width_mm"] == 900 else "#aa7540", stroke_width=1.8, stroke_dasharray="4 3")
    sheet.text("前方／道路", *d.point([3000, -220]), text_anchor="middle", class_="small")
    sheet.text("6×17.63m研究框；騎樓深3.9m，非可建量簽證", 45, 1090, class_="small")
    return gate


def whole_sheet(report):
    s = Sheet("C一樓｜24級樓梯＋可關前室＋連續照護配置比較", report)
    floor_drawing(s, report)
    y = 140
    notes = ["完整一樓同版對位；虛線區分用途，不是每條線都新增實牆。原騎樓、孝親房、套衛與後830通風帶不擴縮。",
        "原梯廳標籤17.424㎡重新分為梯段區11.616㎡、走道3.768㎡及後前室分攤2.040㎡；地面不重複相加。",
        "2200×4700梯段框、24級／270踏面、完整1000平台及上層到達維持；不是把實際樓梯縮小。",
        "900試線經新前置門後轉向，再沿1200名義走道到孝親房；與第一級名義餘150mm，實際扶手／梁板未核。",
        "四組門81態獨立核；門半開／關閉的反例保留。只有相關門全開才通指定方塊，不代表實際輪椅或門淨寬。",
        "訪客公衛不穿孝親房；900洞減230預算僅670mm。橘線為600方塊，公衛門片五金未核，沒有照護通過信用。",
        "保原18件1F家具／設備尺寸；電視轉右牆，部分物件移15～35mm、沙發10mm，完整操作帶保留。壁掛電視與低家具投影重疊不等於立體相撞。",
        "孝親房床頭靠左實牆；二／三樓浴廁投影不壓本版床體。臥室前段上方仍有浴廁，管線及完整家規未知。",
        "前後候選窗保留；廚房與梯旁無確認外側窗，不借共壁畫假窗。全熱／新風、兩衛排濕及關門補氣仍待合圖。",
        "2F唯一洗衣機、景觀洗曬、C-AC01及所有上層原樣保留。這張可討論配置，不能直接當施工或整合3D已採用。"]
    for text in notes:
        y = s.paragraph(text, 445, y, width=48, step=23)
    return s.output()


def entry_sheet(report):
    s = Sheet("C入口與門態｜新前置門接舊照護直線的修正", report)
    d = Draw(s, (45, 145), .105)
    # Show 1F y=7500..14000 in a translated local view.
    def local(r):
        return [r[0], r[1]-7500, r[2], r[3]]
    d.box([2400, 0, 3600, 2260], fill="#edf0e9", stroke="#85978e")
    d.box(local([2400, 8960, 1200, 3140]), fill="#e7efdc", stroke="#85978e")
    d.box(local([0, 12100, 3600, 1700]), fill="#e7efdc", stroke="#85978e")
    d.box(local([3720, 9760, 2200, 3970]), fill="#c9ced7", stroke="#617185")
    for r in report["front_gate"]["wall_budgets_mm"]:
        d.box(local(r), fill="#7f8b84")
    d.box(local([2900, 8500, 1200, 100]), fill="#fafbf8")
    for p in report["care_door_parts"]["open"]:
        if p["door"] in {"front", "bedroom"}:
            d.poly([[x, y-7500] for x, y in p["polygon_mm"]], fill="#bb9474", stroke="#805534")
    route = report["review"]["routes"][0]["points_mm"]
    for a, b in zip(route, route[1:], strict=False):
        if a[0] == b[0] and min(a[1], b[1]) <= 14000 and max(a[1], b[1]) >= 7500:
            aa, bb = [a[0], min(14000, max(7500, a[1]))], [b[0], min(14000, max(7500, b[1]))]
        elif 7500 <= a[1] <= 14000 and a[1] == b[1]:
            aa, bb = a, b
        else:
            continue
        d.line([aa[0], aa[1]-7500], [bb[0], bb[1]-7500], stroke="#277c79", stroke_width=3, stroke_dasharray="5 3")
    s.text("前置門 y8550", 350, 235, class_="room")
    s.text("第一級 y9760", 445, 370, class_="room")
    s.text("梯旁名義1200", 305, 520, class_="room")
    s.text("後照護前室／IDF", 100, 760, class_="room")
    y = 145
    for text in ["不能直接疊舊圖：舊900試線沿x3000，碰新門固定面；新線在門處改x3500，門後平地再轉x3000。",
        "保原門線與家具，不將舊照護版右側閱讀椅搬到新門區。孝親電視轉側牆，避免前入口加寬與電視重疊。",
        "四組門各三態，共81組；半開／關閉分別阻擋其相關路線，朝街到床只受街門／前室門／臥室門，入浴另受浴室門。",
        "朝街1200、公衛900、孝親及浴室1200都是名義洞。公衛不因此取得900完成淨寬；其門片與廚房門組仍未知。",
        "前室1700深扣230後1470，不當獨立1500轉位；IDF需共享檢修，不可擺櫃阻斷照護動線。",
        "門移動行程須先清空。把手、止擋、防夾、外解鎖、無凸軌、防火密封與關門新風／排氣均待實際產品與專業資料。"]:
        y = s.paragraph(text, 760, y, width=32, step=24)
    s.text("900方塊路徑示意；未核道路高差、門檻、抬抱人員或全程救援。", 45, 1040)
    return s.output()


def bath_sheet(report):
    s = Sheet("C照護浴室｜側牆盆、雙片門與仍緊的餘量", report)
    d = Draw(s, (50, 155), .17)
    def local(r):
        return [r[0]-3600, r[1]-13800, r[2], r[3]]
    d.box([0, 0, 2400, 3000], fill="#dceff4", stroke="#607c73", stroke_width=2)
    bath = next(r for r in report["rooms"] if r["id"] == "elder-bath")
    for i in bath["items"]:
        d.box(local(i["body_mm"]), fill="#b9c9be", stroke="#3c6355")
        d.box(local(i["operation_mm"]), fill="none", stroke="#8ba694", stroke_dasharray="4 3")
    for h in report["review"]["hardware"]:
        d.box(local(h["body_mm"]), fill="#c4aa8b", stroke="#916b41")
    d.box(local(report["bath"]["turn_reserve_mm"]), fill="none", stroke="#3c8a7d", stroke_width=2, stroke_dasharray="6 3")
    for p in report["care_door_parts"]["open"]:
        if p["door"] == "bath":
            d.poly([[x-3600, y-13800] for x, y in p["polygon_mm"]], fill="#bb9474", stroke="#805534")
    s.text("600mm後高窗候選 → 830mm戶外帶", 55, 735, class_="small")
    s.text("2.4×3m名義；115假設完成輪廓約6.0109㎡", 55, 780, class_="small")
    y = 145
    for text in ["側牆盆600×450轉向、馬桶450×700及1200淋浴保留；折椅與扶手等八類配件沒有刪除或縮小。",
        "盆前900方塊有50mm面向餘量，但偏中線250mm；坐姿龍頭、膝部、熱管及實際可及未知。",
        "盆操作與馬桶側移重疊0.2675㎡，必須分時；1500×1800及1500圓仍借淋浴濕地，不是專用乾地轉位。",
        "全開／半開／關閉的兩片門及25把手／20止擋都列入；門組到轉位35mm，實際更厚產品可能侵入。",
        "局部板框到右扶手18.5mm，單項消耗20mm後為−1.5mm；這仍是未解風險，不是施工誤差已足。",
        "折椅收起、扶手掀起是本輪操作前提，放下狀態不能借同一預留宣稱通過。整套錨定承重、防水排水、外救援待核。",
        "套衛仍經臥室；訪客用前公衛，照服公共直達偏好尚未滿足。局部板框不代表真人從騎樓抬抱到床或浴室救援成立。",
        "新風、兩衛獨排及關門補氣須合圖；外窗只代表候選，不證明有效換氣或免除機械排濕。"]:
        y = s.paragraph(text, 560, y, width=44, step=24)
    return s.output()


def render(report):
    files = {"whole-floor.svg": whole_sheet(report), "entry-and-doors.svg": entry_sheet(report), "care-bath.svg": bath_sheet(report)}
    files["furniture-changes.csv"] = csv_text([{"物件": r["id"], "原座標xywd毫米": str(r["from_mm"]), "新座標xywd毫米": str(r["to_mm"]), "原尺寸保留": r["size_preserved"], "採用": "否"} for r in report["review"]["changes"]])
    files["door-route-matrix.csv"] = csv_text([{"街門": c["states"]["street"], "前室門": c["states"]["front"], "臥室門": c["states"]["bedroom"], "浴室門": c["states"]["bath"],
        **{k+"阻門": ",".join(v) for k, v in c["route_door_hits"].items()}, "實際產品照護": "未知"} for c in report["review"]["door_combinations"]])
    files["engineering-replies.csv"] = csv_text([{"問題ID": f"CGC-{n:02d}", "待核": text,
        **dict.fromkeys(["同版資料與圖號", "專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"], "")} for n, text in enumerate(report["config"]["limits"], 1)])
    body = '<h1>C一樓：完整平面與照護局部同版比較</h1><p class="note">獨立比較／未採用；原ABC、主3D與上層保留。前置可關門方向已確認，整套照護／產品及工程尚未核定。</p>'
    body += "<p>"+html.escape(report["conclusion"])+"</p>"
    body += '<p>重新分區不增加室內面積；梯段、完整平台不縮。保18件一樓家具／設備尺寸；小移完成面邊距，電視轉側牆。訪客公衛仍獨立，C仍只有2F一台洗衣機。</p>'
    for name, title in [("whole-floor.svg", "完整一樓配置"), ("entry-and-doors.svg", "入口接法與81組門態"), ("care-bath.svg", "浴室局部與保留風險")]:
        body += f'<section><h2>{title}</h2><p><a href="{name}">開啟向量圖</a></p><img style="width:100%;height:auto" src="{name}" alt="{title}"></section>'
    body += '<h2>可用範圍與還需要的資料</h2>'+ul(report["config"]["limits"])
    body += '<h2>舊照護來源差異保留</h2>'+table(["來源", "處理"], [[d["source"], "使用凍結計畫／模型對位，重算本批幾何；不借舊passed"] for d in report["historical_care_source_drift"]])
    body += '<p><a href="furniture-changes.csv">逐件變更CSV</a>／<a href="door-route-matrix.csv">81門態路徑矩陣</a>／<a href="engineering-replies.csv">空白回覆表</a>／<a href="review.json">來源與計算JSON</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；僅靜態檢查，沒有啟動瀏覽器、WebGL、完整場景或轉圖。</small>'
    files["index.html"] = page("C完整一樓整合比較", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-c-ground-coordination-artifacts-v1", "report_hash": report["report_hash"], "source_hashes": report["source_hashes"], "adopted": False,
        "artifacts": {n: hashlib.sha256(data.encode()).hexdigest() for n, data in files.items()}}, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    try:
        report = build(ROOT)
        files, out = render(report), ROOT/OUT
        if args.check:
            stale = [n for n, data in files.items() if not (out/n).is_file() or (out/n).read_bytes() != data.encode()]
            if stale:
                raise ContractError("C whole-ground-floor study stale: "+", ".join(stale))
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (out/name).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "floor": "C-1F", "files": len(files),
            "fixtures": report["review"]["fixtures_count"], "independent_door_states": len(report["review"]["door_combinations"]),
            "protected_controls": report["protected_controls_unchanged"], "primary_3d_changed": False, "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

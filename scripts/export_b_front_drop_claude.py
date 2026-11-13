#!/usr/bin/env python3
"""Export Claude cross-check and conditional under-return drain comparisons, statically."""
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

from house_design.b_front_drop_claude import OUT, build  # noqa: E402
from house_design.b_upper_replan import sweep  # noqa: E402
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
        self.text("Claude第一輪交叉核對＋Codex條件提案／未採用｜G4D待第二輪，不是共識、施工或專業核可。", 28, 76)
        self.text("本批 "+report["report_hash"], 28, 1158, class_="small")
        self.text("原ABC／3D及149控制保留；數值為列明模型，無實測、產品、風水、消防或搬運核可，未跑瀏覽器。", 28, 1182, class_="small")


def route_sheet(report):
    s = Sheet("G4D｜室內高位先落500，保原梯及兩門的待核方向", report)
    option = next(r for r in report["options"] if r["id"] == "G4D")
    d = Draw(s, (45, -25), .1)
    d.box([0, 1980, 2400, 1920], fill="#e2e8e7", stroke="#7d9492")
    d.box([0, 3900, 2400, 5200], fill="#edf0e9", stroke="#607c73")
    d.box([2400, 3900, 1000, 5200], fill="#efd6ce", stroke="#b88b7a")
    for step in report["original_first_floor_treads"]:
        d.box(step["rect_mm"], fill="#e2e6df", stroke="#7c9484", stroke_width=.7)
    d.box(report["original_landing_mm"], fill="#d9dfbf", stroke="#74803e")
    d.box([115, 1780, 400, 400], fill="#ca9d8b", stroke="#9c4634")
    footprint = sweep(option["header_route_mm"], 400)
    d.poly(list(footprint.exterior.coords), fill="#b9d9dd", fill_opacity=.65, stroke="#2d8297", stroke_width=1)
    d.box(option["shaft_mm"], fill="#98c4b7", stroke="#3c7968", stroke_width=2)
    for a, b in zip(option["header_route_mm"], option["header_route_mm"][1:], strict=False):
        d.line(a, b, stroke="#277c79", stroke_width=2, stroke_dasharray="4 3")
    s.text("2F原井投影，不是現場井", 45, 125, class_="small")
    s.text("騎樓／室內界y3900：梁未知", 45, 350, class_="small")
    s.text("高位落500", *d.point([335, 4640]), class_="small")
    s.text("G4落點，名義退平台20mm", 45, 545, class_="small")
    s.text("右側為祭祀保護，管線不進入", 45, 1020, class_="small")
    y = 145
    for value in ["Claude的G4回程梯下區域保留研究；原G4高管位仍碰梯底。Codex另比G4D：先在室內平台上方[315,4700]落500，再橫接右回程下。",
        "G4D落點仍[1280,4990,400,400]，不是原G0全高平台柱；原24級、1000單跑、平台及街／側門位置都不動。上層井與Q3／RF不自動改圖。",
        "500是向下高位落差，不泵、不抬地坪，也不折成水平1:50。總水平匯管仍4375mm，四條支管都照列。",
        "需比整組最高管頂與後緣梯底，而不是拿3461.6等通行預算當管頂。400前緣較中心再高4mm；額外接頭及安裝間隔另列。",
        "這仍不是空間已夠：400外框距平台只20mm，再向前長25便占平台。檢修開門、地面、消防及搬運沒有重演。",
        "騎樓段仍薄：y3900最有利預算3510.7，再需25則3485.7；高位落差在室內，沒有改善此段，也未證明邊界有梁或可通管。",
        "前側合法終端與深度先核。落點至道路邊界直線至少5190，地梁、覆土、清掃、權利及復舊未知；不能批准埋管或用後側祭祀地下補路。"]:
        y = s.paragraph(value, 465, y, width=46, step=24)
    return s.output()


def soffit_sheet(report):
    s = Sheet("G4／G4D／G5｜管頂與最不利後緣梯底分開列帳", report)
    s.text("樂觀鼻線平行梯底；未有真實階梯、梯板、梯梁／平台梁，不能當施工剖面。", 40, 130)
    names = ["G4", "G4D", "G5"]
    for x, label in [(40, "法向板厚例"), (245, "後緣假梯底"), (510, "G4上方餘量"), (760, "G4D上方餘量"), (1050, "G5上方餘量")]:
        s.text(label, x, 190)
    for n, thick in enumerate(report["config"]["normal_stair_waist_cases_mm"]):
        rows = [next(c for o in report["options"] if o["id"] == name for c in o["soffit_cases"] if c["normal_stair_waist_mm"] == thick and c["extra_fitting_above_original_package_mm"] == 0) for name in names]
        y = 240+n*48
        for x, text in [(40, str(thick)+"mm"), (245, f"{rows[0]['rear_optimistic_soffit_mm']:.1f}mm"),
            (510, f"{rows[0]['margin_after_separate_gap_mm']:.1f}mm"), (760, f"{rows[1]['margin_after_separate_gap_mm']:.1f}mm"), (1050, f"{rows[2]['margin_after_separate_gap_mm']:.1f}mm")]:
            s.text(text, x, y)
    s.text("表內已扣上方50安裝間隔，額外接頭0例；另有25／50例，並非產品不用接頭。", 40, 465)
    s.text("200mm假板厚例：鼻線／假梯底與兩個管頂界", 40, 525)
    base = next(c for o in report["options"] if o["id"] == "G4" for c in o["soffit_cases"] if c["normal_stair_waist_mm"] == 200 and c["extra_fitting_above_original_package_mm"] == 0)
    def ypos(z):
        return 1070-(z-3000)*.53
    s.add("line", x1=70, y1=ypos(base["front_optimistic_soffit_mm"]), x2=590, y2=ypos(base["rear_optimistic_soffit_mm"]), stroke="#687d70", stroke_width=5)
    for name, colour in [("G4", "#b95142"), ("G4D", "#277c79")]:
        value = max(r["conservative_400_chase_top_before_fitting_growth_mm"] for o in report["options"] if o["id"] == name for r in o["fixture_rows"])
        s.add("line", x1=70, y1=ypos(value), x2=590, y2=ypos(value), stroke=colour, stroke_width=3, stroke_dasharray="5 3")
        s.text(f"{name}最高管頂界 {value:.1f}", 75, ypos(value)-12, class_="small")
    s.text("前緣y4990 → 後緣y5390；後方梯底較低", 70, 1110, class_="small")
    y = 570
    for value in ["原G4和G5的高管位在列明厚度例都容不下；高回程下有地面空間，不等於進管高程也成立。",
        "G4D向下落500，最高管頂界約3204.9；在部分假設可避梯底，但300mm例仍失守。250mm再多25接頭只餘約0.4，不能當穩定設計餘量。",
        "垂直落差降低室內包管；最小末端預算2961.6，不是已核室內淨高。各區淨高、防火、門上構造、水力、通氣及檢修全待核。",
        "鼻線減t／cos只是樂觀近似，不含真正台階構造、梯梁或平台梁。上方50與下方檢修50不同面，不互相抵用。"]:
        y = s.paragraph(value, 680, y, width=35, step=24)
    return s.output()


def claims_sheet(report):
    s = Sheet("Claude第一輪交叉核對｜保留G4，修正事實再續談", report)
    y = 145
    values = ["已驗原prompt／stdout／response，第一輪水平長度與部分問題範圍一致。沒有完整解法或全共識；G4D是Codex新增提案，待Claude第二輪。",
        "修正一：y3900／4970目前只是構造界線，有無梁與梁底未知，不能把未知梁說成既有實體衝突。",
        "修正二：Q3三樓前KTV本來就是乾區，沒有濕茶水；不能靠取消不存在的KTV污水得到減量，也不能取消2F通氣。",
        "修正三：搬轎前門為神明堂朝街門，不是樓梯街門。沒有重演全程含桿人員、門片或施工影響，不能寫兩版本不受影響。",
        "家規不亂加減：搬轎通道上方不禁污水是屋主既有答覆，不延伸成神明堂／乾背地下可穿；也不發明所有通路上方一律禁管。",
        "G4D先留低改動研究：原梯門與上層井不動，室內高位下落500；檢修、防火、整組外框及真實騎樓／梯板仍待核。G5全梯鏡像牽動上層與屋突，只留重大備案。",
        "前終端未知就保持未解：地下前出至少5190、假坡103.8只是幾何下界。若只可後出，2270全寬祭祀保護帶不能默認地下豁免。",
        "下一輪先請Claude找G4D算式或拓樸反例，再讓建築／結構／機電核實際構造。現在不要求屋主接受占平台、縮梯、放寬祭祀或取消功能。"]
    for value in values:
        y = s.paragraph(value, 45, y, width=77, step=25)
    s.text("已備第二輪工具關閉討論稿，長任務另開終端；本批沒有第二輪回答。", 45, 1085)
    return s.output()


def render(report):
    files = {"G4D-route.svg": route_sheet(report), "pipe-soffit-budget.svg": soffit_sheet(report), "claude-claim-review.svg": claims_sheet(report)}
    files["claim-review.csv"] = csv_text(report["claim_review"])
    files["pipe-lengths.csv"] = csv_text([{"candidate": o["id"], **r} for o in report["options"] for r in o["fixture_rows"]])
    files["soffit-cases.csv"] = csv_text([{"candidate": o["id"], **r} for o in report["options"] for r in o["soffit_cases"]])
    files["chase-growth.csv"] = csv_text([{"candidate": o["id"], **r} for o in report["options"] for r in o["chase_growth_cases"]])
    files["arcade-boundary.csv"] = csv_text(report["arcade_to_indoor_boundary_cases"])
    files["engineering-replies.csv"] = csv_text([{"ID": f"CG4-{i:02d}", "待核": value,
        **dict.fromkeys(["同版圖號及依據", "專業回覆", "費用工期保固", "窗口", "期限", "屋主選擇", "審查與施工圖發行"], "")} for i, value in enumerate(report["config"]["limits"], 1)])
    body = '<h1>B前排水Claude第一輪：交叉核對與G4D條件提案</h1><p class="note">第一輪已取得並核來源；部分算式一致，沒有全共識。G4D為Codex新增、待Claude第二輪，未採用或併主3D，非工程／風水核可。</p>'
    body += '<p>'+html.escape(report["recommended_next"])+"</p>"
    for name, label in [("G4D-route.svg", "原梯保留的G4D高位落差方向"), ("pipe-soffit-budget.svg", "管頂、最不利後緣梯底及失守案例"), ("claude-claim-review.svg", "哪些同意、哪些修正、哪些仍待核")]:
        body += f'<section><h2>{html.escape(label)}</h2><p><a href="{name}">開啟向量圖</a></p><img src="{name}" style="width:100%;height:auto" alt="{html.escape(label)}"></section>'
    body += '<h2>原案與新條件分開</h2>'+table(["案", "來源", "水平匯管mm", "室內下落mm", "改梯", "施工核可"], [[o["id"], o["origin"], o["offset_length_mm"], o["interior_vertical_drop_mm"], "須全棟重排" if o["mirror_first_floor_stair"] else "原梯保留", "未知"] for o in report["options"]])
    body += '<h2>逐項交叉核對</h2>'+table(["ID", "Claude論點", "核對", "修正及限制"], [[r["id"], r["topic"], r["assessment"], r["correction"]] for r in report["claim_review"]])
    body += '<h2>未解的騎樓及地下終端</h2><p>y3900最有利假預算3510.7、額外25只3485.7；G4D不改善此段。前地下直線至少5190、假坡103.8，不含覆土／地梁／權利及接管深度，後側祭祀保護不默認地下豁免。</p>'
    body += '<h2>使用邊界</h2>'+ul(report["config"]["limits"])
    body += '<p>'+"／".join(f'<a href="{n}">{n}</a>' for n in files if n.endswith(".csv"))+'</p><p><a href="review.json">來源與算式JSON</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；第一輪原始回應及來源另存研究副本。未執行第二輪AI、瀏覽器／WebGL或轉圖，沒有實測、專業或施工核可。</small>'
    files["index.html"] = page("B前排水Claude交叉核對", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-b-front-drop-claude-artifacts-v1", "report_hash": report["report_hash"], "source_hashes": report["source_hashes"],
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
                raise ValueError("Claude front-drop cross-check stale")
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, value in files.items():
                (out/name).write_text(value, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "files": len(files), "options": len(report["options"]),
            "soffit_cases": sum(len(o["soffit_cases"]) for o in report["options"]), "claim_checks": len(report["claim_review"]),
            "protected_controls": report["protected_controls_unchanged"], "consensus": False, "adopted": False, "second_round": "not-run", "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

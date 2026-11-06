#!/usr/bin/env python3
"""Export bounded B ventilation coordination and an unfilled builder reply schedule."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.b_ventilation_detail import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import Plan, Sheet, csv_text, table  # noqa: E402
from scripts.export_b_fengshui_strict import new_rooms  # noqa: E402


def bath_roof_sheet(report):
    g, spec = report["geometry"], report["config"]["revised_exhaust"]
    s = Sheet("B排濕深化01｜濕區抽氣、浴室檢修與屋頂分開出管", report)
    s.text("只深化二三樓一般公衛；床櫃、門窗、原房間邊界及主臥扣豎道20.0761㎡不再更動。", 30, 116)
    s.text("公衛：抽氣移後，進氣／抽氣分開", 35, 160, class_="label")
    p = Plan(s, (35, 200), .135, (0, 11370))
    bath = g["floors"][0]["rooms"][2]
    new_rooms(p, [bath], labels=True)
    p.line([800, 11370], [1200, 11370], stroke="#4d8b69", stroke_width=7)
    p.path([[1000, 11250], [1000, 12200], [1150, 12950]], stroke="#4d8b69", stroke_width=3, stroke_dasharray="6 4")
    p.box(spec["fan_hatch_rect_mm"], fill="none", stroke="#426e9c", stroke_width=2, stroke_dasharray="5 3")
    p.box(spec["ladder_budget_rect_mm"], fill="#d8c2a8", fill_opacity=.3, stroke="#a97c45", stroke_dasharray="4 3")
    p.text("抽風／檢修", 820, 13200, class_="tiny")
    s.lines(["風口中心由(1200,12000)改為(1150,12950)。", "綠線是補氣方向，不是CFD或短路氣流驗證。",
        "500×500檢修、600×800梯位為討論預留，", "平面避列明器具；實際商品拆換與安全架梯待核。",
        "風機留浴室可檢修區，不藏死在臥室天花。"], 35, 565, step=32, class_="small")
    s.text("RF：兩個出口與檢修預留，中心相距1000", 650, 160, class_="label")
    roof = Plan(s, (650, 200), .075, (2400, 11370))
    roof.box([2400, 11370, 3600, 6260], fill="#edf1e8", stroke="#7d988a")
    roof.box([2640, 11370, 2030, 1600], fill="#dae8d5", stroke="#789369", stroke_dasharray="5 3")
    for n, row in enumerate(g["roof_terminal_rows"]):
        color = "#4d82a4" if n == 0 else "#946a9d"
        roof.box(row["service_reservation_mm"], fill="none", stroke=color, stroke_dasharray="5 3")
        roof.box(row["terminal_reservation_mm"], fill="#c2d5e0" if n == 0 else "#d7c5da", stroke=color)
        pts = g["ducts"][n]["points_mm"][5:]
        roof.path([p[:2] for p in pts], stroke=color, stroke_width=2)
        roof.text("2F" if n == 0 else "3F", row["terminal_reservation_mm"][0]+80,
            row["terminal_reservation_mm"][1]+300, class_="tiny")
    s.lines(["原出管中心只隔250mm；", "不能推定兩個風帽與維修可放下。", "",
        "新圖每處500×500終端預留，", "700×700局部服務預留，各自分開。", "都是預留，不是已選商品尺寸，", "1000mm也不是法定排放退距。", "",
        "到屋頂完整安全路線、風帽", "防雨防颱、進氣口與鄰房距離", "及所有屋頂設備仍待核。"], 1005, 200, step=33, class_="small")
    lengths = "／".join(f"{d['centerline_length_mm']/1000:.3f}" for d in g["ducts"])
    s.lines([f"包含屋頂外移後，二／三樓中心線估長 {lengths}m，各7處直角轉向；非等效管長。",
        "列明風管／終端預留避祭祀乾保護區、武轎庫投影與污水井；沒有核可穿梁、穿板或屋頂開孔。",
        "屋頂出口方向與補氣來源需一起驗證；不能只靠位置拉開，就宣稱沒有回吸或氣味問題。"], 30, 895, step=33, class_="small")
    return s.output()


def makeup_sheet(report):
    m = report["makeup"]
    s = Sheet("B排濕深化02｜關門補氣：不只在門下留縫", report)
    s.text("以120m³/h作同條件比較；門縫、自由面積、阻視與聲學都沒有取得實物或實測。", 30, 116)
    s.text("前牆立面示意：兩處候選擇一，不自動開洞", 35, 160, class_="label")
    ox, oy, scale = 35, 605, .17
    s.box([ox, oy-2400*scale, 2640*scale, 2400*scale], fill="#e9eee7", stroke="#85988b")
    s.box([ox+1320*scale, oy-2100*scale, 1130*scale, 2100*scale], fill="#d5ddd5", stroke="#72887b")
    for xs, color in [(m["front_wall_candidate_x_mm"], "#477ca0"), (m["door_panel_candidate_x_mm"], "#a37649")]:
        s.box([ox+xs[0]*scale, oy-400*scale, (xs[1]-xs[0])*scale, 200*scale],
            fill=color, fill_opacity=.65, stroke=color, stroke_width=2)
    s.text("400×200牆旁候選", ox+20, oy+35, class_="small")
    s.text("原廠門片補氣候選", ox+225, oy+60, class_="small")
    s.lines(["上圖門高2100只為立面圖例，不是已選門組。", "名義門1130與900完成淨開口仍須門商整樘核圖。",
        "藍：牆旁低位消音補氣，先核RC／防火／牆厚。", "棕：原廠門片消音補氣，核重量、阻視、框軌與開啟。",
        "兩種都要有可清潔構造；不能用普通百葉當隔音保證。"], 35, 745, step=32, class_="small")
    s.text("只靠900mm門底縫：理想平均速度", 600, 185, class_="label")
    for n, r in enumerate(m["door_undercuts"]):
        y = 240+n*85
        s.text(f"{r['gap_mm']}mm縫", 600, y, class_="small")
        s.box([720, y-20, r["velocity_m_s"]*90, 28], fill="#c79b7b")
        s.text(f"{r['velocity_m_s']:.2f}m/s", 1100, y, class_="small")
    s.lines(["400×200開口、自由面積45～60%假設：", "理想有效面積0.036～0.048㎡，", "同風量流速約0.69～0.93m/s。", "這不是噪音或壓損合格結論。", "",
        "來源是一般公共乾區；其室外補氣尚未設計。", "不能從樓梯、獨立乾室或其他浴室串氣，", "也不能用開著大門才抽得動當交屋驗收。"], 600, 560, step=33, class_="small")
    return s.output()


def assembly_sheet(report):
    a, g = report["assembly"], report["geometry"]
    s = Sheet("B排濕深化03｜管井包覆、天花與風量工作點", report)
    s.text("以下厚度、摩擦、彎頭阻力均為敏感度假設；實際結構、商品與施工工作點仍未核定。", 30, 116)
    s.text("500×300外預留：兩條175外廓＋50間距", 35, 160, class_="label")
    s.box([35, 195, 500*.65, 300*.65], fill="#e4d4df", stroke="#8d617f")
    s.box([35+50*.65, 195+50*.65, 400*.65, 200*.65], fill="#fafbf7", stroke="#a8849d")
    for x in [35+50*.65, 35+275*.65]:
        s.box([x, 195+62.5*.65, 175*.65, 175*.65], fill="#c4d7df", stroke="#5b8b9e")
    s.lines(["若每側包覆50mm：內框400×200，", "兩管175＋175＋間隔50恰好400。", "沒有把檢修、套管或真正防火構造算成已放下。",
        "每側75mm時內深150，小於175外廓。"], 35, 445, step=32, class_="small")
    s.text("尺寸加大仍需扣主臥，不偷借面積", 35, 635, class_="label")
    for n, r in enumerate(a["enclosure_cases"]):
        s.text(f"{r['enclosure_mm'][2]}×{r['enclosure_mm'][3]} → 主臥 {r['master_after_sqm']:.4f}㎡"
            +("　低於20" if not r["meets_original_master_20"] else ""), 35, 685+n*42, class_="small")
    s.text("2.4m天花與管心2.55m：標高預算", 650, 160, class_="label")
    ox, oy = 650, 520
    s.line([ox, oy], [1260, oy], stroke="#8b9a90", stroke_width=3)
    s.text("假設完成天花 +2400", ox, oy+35, class_="small")
    s.box([ox+30, oy-(2637.5-2400)*.6, 400, 175*.6], fill="#bdd5df", stroke="#58839a")
    s.text("外廓下2462.5／上2637.5", ox+35, oy-165, class_="small")
    s.text("上方62.5mm只是本條直管預算", ox, oy+80, class_="small")
    s.lines(["若梁從上層地坪向下400mm，梁底+2600，", "與管頂預算重疊37.5mm（只有梁真跨此處才成立）。", "不能鑽梁或假裝梁不存在；應改線或局部降頂再核。",
        "風機預留高度250mm比直管更大，另核風機上方。", "",
        "兩層均有7處直角轉向；依選定假設算壓損，", "再請廠商提供P-Q曲線及安裝後風量，", "不是看最大無管風量就可選機。"], 650, 650, step=29, class_="small")
    service = g["service"]["shaft_service_route_overlap_sqm"]
    s.text(f"豎道檢修預留暫占房內路徑{service:.3f}㎡，維修與居住分時；完整拆換與安全登高未核。", 30, 985, class_="small")
    return s.output()


def builder_rows(report):
    topics = [
        ("2F／3F排氣風機各一", "90／120／130m³/h比較，DN125概念路徑", "型號、外廓、P-Q曲線、噪音與可拆檢修；不是最大風量"),
        ("每層關門補氣擇一", "門片或牆旁400×200候選，不累計兩處", "實際自由面積、壓損、阻視、聲學、牆種及整樘淨開口"),
        ("兩條獨立風管", "DN125＋每側25保溫僅假設，長度含屋頂外移", "實際內外徑、管材、彎頭、吊架、止回、保溫與冷凝處理"),
        ("排氣豎道", "500×300控制；550×350厚壁預案未選，600×400使主臥不足20", "包覆厚度、套管、耐火與可檢修淨空，回填實際占地"),
        ("天花／結構", "2400天花、2550管心及500×400×250風機討論箱", "梁板正式圖、穿孔與防火封堵、風機上下淨空及局部降頂"),
        ("RF兩個終端", "中心隔1000，每處500×500及700×700服務預留", "完整風帽、防雨防颱、防水、開口距離、噪音與屋頂安全路線"),
        ("試運轉與交屋", "每間關門／開門各量，並測兩層同時運作", "風口實測風量、室內外補氣、壓差、止回及濕區排乾；含保固責任"),
        ("材料與施工報價", "風機、門／牆補氣、管道、包覆、孔洞、防水、調試分項", "原標配折抵、含稅運裝、維修口與替代品送審，不默認建商全含"),
    ]
    return [{"id": f"B-VENT-BID-{n:02d}", "item": topic, "study_allowance": allowance,
        "required_reply": required, "model": None, "actual_dimensions": None, "evidence": None,
        "quote_twd": None, "approval": "unknown"} for n, (topic, allowance, required) in enumerate(topics, 1)]


def index_html(report):
    g, m, a = report["geometry"], report["makeup"], report["assembly"]
    roof_length = "／".join(f"{d['centerline_length_mm']/1000:.3f}m" for d in g["ducts"])
    gap_table = table(["理想開口／120m³/h", "面積㎡", "平均速度m/s"], [
        [f"900mm門底{r['gap_mm']}mm縫", f"{r['ideal_area_sqm']:.4f}", f"{r['velocity_m_s']:.2f}"]
        for r in m["door_undercuts"]]+[
        [f"400×200，假設自由面積{r['assumed_free_fraction']:.0%}", f"{r['assumed_free_area_sqm']:.4f}", f"{r['velocity_m_s']:.2f}"]
        for r in m["transfer_free_area_cases"]])
    pack_table = table(["管井外預留mm", "扣後主臥㎡", "相對20㎡目標"], [
        [f"{r['enclosure_mm'][2]}×{r['enclosure_mm'][3]}", f"{r['master_after_sqm']:.4f}",
         "估算暫達，未核真實構造" if r["meets_original_master_20"] else "不足，不能自動加大採用"]
        for r in a["enclosure_cases"]])
    pressures = []
    for d in report["pressure_sensitivity"]:
        for c in d["cases"]:
            pressures.append([d["floor"], c["q_m3_h"], f"{c['assumed_low']['sum_pa']:.1f}～{c['assumed_high']['sum_pa']:.1f}",
                "指定假設的結果；實際補氣／濾網等壓損未含"])
    pressure_table = table(["樓層", "比較風量m³/h", "風管估算Pa", "範圍"], pressures)
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B排濕深化｜關門補氣、檢修與建商規格</title>
<style>body{{font:17px/1.75 system-ui,sans-serif;color:#283e46;background:#f5f8f3;margin:0}}main{{max-width:1180px;margin:auto;padding:25px 20px 65px}}section{{background:#fff;border:1px solid #d7e1d6;padding:24px;margin:26px 0;border-radius:10px}}h1{{font-size:29px}}h2{{font-size:23px}}a{{color:#17687d}}a:focus-visible{{outline:3px solid #ac7035;outline-offset:3px}}nav{{display:flex;gap:16px;flex-wrap:wrap}}.notice{{padding:17px;background:#fff1de;border-left:5px solid #ae6e32}}.table{{overflow:auto}}table{{width:100%;min-width:650px;border-collapse:collapse;font-size:15px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #dbe2d7;vertical-align:top}}th{{background:#edf2e9}}img{{max-width:100%;height:auto;display:block;margin:18px auto}}small{{font-size:14px}}code{{overflow-wrap:anywhere}}</style></head><body><main>
<h1>B排濕續作：把補氣、檢修與發包條件一起畫出來</h1>
<p>二、三樓一般公衛的抽風口移向後方濕區，屋頂兩個終端另留分開位置；同時補關門補氣、管井包覆及施工回覆表。</p>
<p class="notice"><strong>工程討論預案，尚未採用。</strong> 屋主尚未明確選擇無窗公衛或接受兩衛面積取捨；繼續研究不代表同意。主臥仍估20.0761㎡、公衛4.4667㎡、套衛4.7124㎡，原20／5／6㎡目標不變；原3D與一樓前後門三態保留。</p>
<nav><a href="#changes">這次修正</a><a href="#drawings">三張圖</a><a href="#air">關門補氣</a><a href="#fit">管井與天花</a><a href="#fan">選機與建商回覆</a></nav>
<section id="changes"><h2>先修正排濕位置與維修預留</h2><p>抽氣口由(1200,12000)移至(1150,12950)，減少貼近前方補氣處的疑慮；風管在後方再繞到主臥前臂豎道，列明外廓避床、祭祀保護區、武轎庫與污水井。這只是幾何配置，沒有CFD或實測短路氣流通過結論。</p>
<p>原屋頂兩根豎管中心只隔250mm，現在另畫每處500×500終端及700×700局部檢修預留，中心隔1000mm。這些不是商品尺寸或法定退距；風帽、防水防颱、周圍開口與完整屋頂安全路線仍需核圖。</p>
<p>含屋頂外移後，二／三樓中心線估長{roof_length}，各7次直角轉向。屋頂外移需要新的彎頭，不能沿用上輪估長當最終風機條件。</p>
<p>風機與檢修口留在公衛；模型內的500×500檢修口與600×800梯位未碰列明器具。主臥豎道檢修會暫占房內路徑，維修和居住分時，不能說所有狀態都暢通。</p></section>
<section id="drawings"><h2>三張新圖</h2><p><a href="B01-bath-roof.svg">濕區抽氣與屋頂終端</a>／<a href="B02-makeup.svg">關門補氣立面</a>／<a href="B03-assembly.svg">包覆與天花尺寸</a></p>
<img src="B01-bath-roof.svg" width="1400" height="1100" alt="後移抽風口、浴室檢修預留與屋頂兩個分開終端的候選平面">
<img src="B02-makeup.svg" width="1400" height="1100" loading="lazy" alt="門下縫與門片或牆旁消音補氣的自由面積和流速比較，候選擇一">
<img src="B03-assembly.svg" width="1400" height="1100" loading="lazy" alt="管井包覆、主臥扣面積、2400天花與梁底敏感度"></section>
<section id="air"><h2>關著門，也要有可驗證的補氣來源</h2>{gap_table}
<p>以上按理想開口算平均速度，不能據此認定某門縫一定夠或一定吵。先讓建商比較「原廠門片消音補氣」及「門旁牆消音補氣」兩種完整做法，400×200mm只是候選開口，實際自由面積與壓損不得用標稱長寬代替。</p>
<p>低位補氣仍要阻視、可清潔及聲學實測。門片方案須核整樘門厚、重量、把手、開啟與900mm完成淨寬；牆旁方案先核RC／牆厚／防火，不自動在未知結構上開孔。它們是替代方案，不累計兩個洞來湊風量。</p>
<p>一般公共乾區只是中間補氣來源；其室外進氣、關窗和同時排風的壓力平衡尚未設計。不能借樓梯、獨立乾保護室、其他浴廁、神明堂排煙或污水通氣管補氣；也不以開著大門才抽得動當完成。</p></section>
<section id="fit"><h2>管井放得下管，不等於完整構造已放下</h2>{pack_table}
<p>兩條外廓175mm風管加50mm假設間距需400mm；500×300mm外預留若每側包覆50mm，內框只400×200mm，寬度恰好沒有餘量。這假設管中心隨完成內牆重新排，不是原中心點不動仍適用。每側75mm時內深只150mm，放不下175外廓。</p>
<p>選定真實構造前，不採用550×350厚壁預案，也不把600×400放大當已解；後者主臥估19.9861㎡，低於原20㎡目標。</p>
<p>假設2400mm完成天花、2550mm管心，175mm外廓下緣2462.5、上緣2637.5，天花上方只餘62.5mm。若400mm深梁確實跨此線，梁底2600mm會與矩形預算重疊37.5mm。梁位未知，不能宣稱一定碰梁；也不能以未知當沒有梁。風機高度250mm、彎頭、支架與檢修還需另外核。</p></section>
<section id="fan"><h2>給建商的選機資料要包含工作點與交屋量測</h2>{pressure_table}
<p>這是Darcy-Weisbach與指定摩擦／彎頭K假設的比較，<strong>不是實際壓損上下界或已核定靜壓</strong>。另加消音器、濾網、積塵、補氣與外部風壓均未含，真實長軟管也不能直接套此模型。實際風機型號仍未選。</p>
<p>請建商回填指定風量下的P-Q曲線、外廓、噪音、可拆換方式，並分列風機、門／牆補氣、管道、包覆、防水、孔洞、調試、標配折抵及保固。低總價不能以省略補氣、檢修或安裝後風量測試達成。</p>
<p><a href="builder-response.csv">可直接給建商的八項回覆表</a>／<a href="pressure-assumptions.csv">逐層壓損假設表</a>／<a href="review.json">全部坐標與計算</a>／<a href="../b-bath-ventilation-v1/index.html">上輪外窗／排氣兩案</a>／<a href="../../../Docs/b-ventilation-detail-v1.md">說明文件</a>。</p>
<p>19項上輪測試或舊瀏覽器passed不沿用為本包驗收；本批另取當前來源的靜態紀錄。原三項家規與其餘祭祀保護要求維持；新工程預案沒有再送Claude，沒有整體風水、法規或施工核可。</p></section>
<small>2026-11-06｜來源 <code>{html.escape(report['source_layout_report_sha256'])}</code><br>本批 <code>{html.escape(report['report_hash'])}</code>｜靜態深化，未執行瀏覽器或WebGL。</small>
</main></body></html>'''


def render(report):
    pressure_rows = [{"floor": d["floor"], "q_m3_h": c["q_m3_h"], "length_mm": d["centerline_length_mm"],
        "diameter_mm": d["diameter_assumption_mm"], "axis_bends": d["axis_bends"],
        "assumed_low_pa": c["assumed_low"]["sum_pa"], "assumed_high_pa": c["assumed_high"]["sum_pa"],
        "actual_required_pa": None, "actual_fan_model": None, "actual_curve_reference": None}
        for d in report["pressure_sensitivity"] for c in d["cases"]]
    files = {"B01-bath-roof.svg": bath_roof_sheet(report), "B02-makeup.svg": makeup_sheet(report),
        "B03-assembly.svg": assembly_sheet(report), "index.html": index_html(report),
        "builder-response.csv": csv_text(builder_rows(report)), "pressure-assumptions.csv": csv_text(pressure_rows),
        "review.json": json.dumps(report, ensure_ascii=False, indent=2)+"\n"}
    manifest = {"schema": "house-b-ventilation-detail-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "adopted": False,
        "artifacts": {name: hashlib.sha256(data.encode()).hexdigest() for name, data in files.items()}}
    files["artifact-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files, out = render(report), ROOT/OUT
        if args.check:
            stale = [n for n, data in files.items() if not (out/n).is_file() or (out/n).read_bytes() != data.encode()]
            if stale:
                raise ContractError("B vent detail artifacts stale: "+", ".join(stale))
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (out/name).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported-static-detail", "artifacts": len(files),
            "protected_controls_unchanged": report["protected_controls_unchanged"], "adopted": False, "browser": "not-run"}))
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Render small B upper-bath comparisons; never start a browser or rebuild ABC."""
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

from house_design.b_bath_ventilation import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import Plan, Sheet, csv_text, table  # noqa: E402
from scripts.export_b_fengshui_strict import new_rooms, polygon  # noqa: E402


def comparison_sheet(report):
    s = Sheet("B排濕01｜二三樓公衛：保格局排氣／後窗重排", report)
    s.text("本輪只比較B二三樓；一樓有窗公衛、祭祀正門、後門優先與前門備案不改。", 30, 116)
    for n, o in enumerate(report["options"]):
        ox = 30+n*480
        s.text("保位置：500×300獨立排氣豎道" if n == 0 else "後右公衛有窗：增加公共通道", ox, 158, class_="label")
        p = Plan(s, (ox, 195), .073, (0, 11370))
        rooms = o["floors"][0]["rooms"]
        new_rooms(p, rooms, labels=False)
        p.box(o["floors"][0]["vent_enclosures_mm"][0], fill="#c297b7", stroke="#854d79", stroke_width=2)
        p.path(o["floors"][0]["screen"]["route"]["points_mm"], stroke="#548a63", stroke_width=1.5, stroke_dasharray="5 4")
        p.text("主臥", 300, 15100, class_="small")
        p.text("乾保護室", 2800, 12100, class_="tiny")
        if n == 0:
            p.text("公衛", 700, 12100, class_="small")
            p.text("套衛", 4200, 15900, class_="small")
        else:
            polygon(p, o["door_bed"]["nominal_orthogonal_strip_mm"], fill="#d99c92", fill_opacity=.18,
                stroke="#ae6256", stroke_dasharray="5 4")
            p.text("套衛", 700, 12100, class_="small")
            p.text("公衛", 4200, 15900, class_="small")
            p.text("公", 5090, 12500, class_="tiny")
            p.text("共", 5090, 12900, class_="tiny")
            p.text("通", 5090, 13300, class_="tiny")
            p.text("道", 5090, 13700, class_="tiny")
        s.lines([f"主臥扣新增豎道 {o['master_after_reservations_sqm']:.4f}㎡",
            f"公衛 {o['public_after_sewer_sqm']:.4f}㎡／套衛 {o['private_after_sewer_sqm']:.4f}㎡",
            "原床、櫃、梳妝及2400後窗均保留。",
            "床櫃換位避門口正向投影；無直接窗。" if n == 0 else "通道1100假設；紅帶套衛門朝床仍未解。"], ox, 705, step=32, class_="small")
    s.lines(["同一32坪概念框內，", "不外擴、沒有側窗假設。", "",
        "左案原20㎡主臥只餘", "0.0761㎡，梁柱／包覆", "再加大即可能不足。", "",
        "右案主臥降至16.0889㎡，", "且套衛門朝床仍未解。", "左前套衛仍無直接窗，", "也要排氣到屋頂。", "原主臥冷氣須重選位置。"], 1015, 200, step=33, class_="small")
    s.lines(["三樓：左案維持左前公衛、後右乾區；右案改後右公衛、左前乾區，均不新增第二間浴廁。",
        "左案新機盒改前臂上方避床；氣流、鏡高與管線未知。兩案濕區／風管預算均避明列保護投影。",
        "左案較少重排，暫列優先工程核對；右案保留外窗比較，兩案均未達原兩衛5／6㎡目標，也未採用。"], 30, 910, step=32, class_="small")
    return s.output()


def roof_duct_sheet(report):
    option = report["options"][0]
    s = Sheet("B排濕02｜兩條獨立排氣：平面預算與標高示意", report)
    s.text("紫框500×300豎道占主臥0.15㎡；兩管分開，不和200×200污水管井共用。", 30, 116)
    p = Plan(s, (35, 190), .079, (0, 11370))
    new_rooms(p, option["floors"][0]["rooms"], labels=False)
    for d in option["ducts"]:
        polygon(p, d["plan_budget_polygon_mm"], fill="#c3d6e7", fill_opacity=.45, stroke="#4d82a4", stroke_dasharray="5 3")
    p.box(option["enclosure_mm"], fill="#d4a6c5", fill_opacity=.65, stroke="#925b81", stroke_width=2)
    p.text("新排氣豎道", 3500, 13880, class_="tiny")
    p.box([2325, 13155, 200, 200], fill="#a7847c", stroke="#70483e")
    p.text("污水管井", 1700, 13070, class_="tiny")
    p.box(report["palanquin_rect_mm"], fill="none", stroke="#aa7553", stroke_dasharray="5 3")
    p.text("下層武轎庫投影", 150, 15000, class_="tiny")
    s.lines(["床前移1815、衣櫃後移2030mm，尺寸不縮。", "豎道移前臂，避乾保護室、污水井與庫房；", "平面幾何不代表門窗、結構或宗教認證。"], 35, 735, step=31, class_="small")
    def z_y(z):
        return 190+(11000-z)*.079
    s.text("標高示意：不是同一切面施工剖面", 640, 160, class_="label")
    for z, title in [(4000, "2F +4000"), (7000, "3F +7000"), (10000, "RF +10000")]:
        y = z_y(z)
        s.line([640, y], [1140, y], stroke="#84968e", stroke_width=1.5)
        s.text(title, 1150, y+5, class_="small")
    for n, d in enumerate(option["ducts"]):
        x = 930+n*75
        z0 = d["points_mm"][0][2]
        z1 = d["points_mm"][1][2]
        end = d["points_mm"][-1][2]
        s.path([[720, z_y(z0)], [720, z_y(z1)], [x, z_y(z1)], [x, z_y(end)]],
            stroke="#3b83a4" if n == 0 else "#9872a6", stroke_width=5)
        s.text(d["floor"]+f" 估長{d['centerline_length_mm']/1000:.3f}m", 650, z_y(z0)+30, class_="small")
    s.lines(["RF是模型戶外服務區；出管+10600僅候選。", "排風帽尺寸、兩帽距離、防水／防颱及", "進氣口／開口距離待核，沒有終端核可。", "",
        "DN125＋每側25保溫：外預算175mm。", "兩層各有自己的風機、管路及止回設備；", "不能只憑無管路時最大風量選機。", "樓層3m、天花2.4m、管心2.55m為假設；", "梁、板、吊架、防火及維修未核。"], 640, 805, step=24, class_="small")
    return s.output()


def window_bath_sheet(report):
    o = report["options"][1]
    s = Sheet("B排濕03｜有窗重排：兩衛原尺寸試排與通道代價", report)
    s.text("2F後右公衛從公共通道進；左前套衛只由主臥進。兩衛仍獨立，不穿臥室上公衛。", 30, 116)
    rooms = o["floors"][0]["rooms"]
    baths = [next(r for r in rooms if r["id"] == key) for key in ["public-bath", "private-bath"]]
    for n, r in enumerate(baths):
        ox = 40+n*425
        offset = (3900, 14880) if n == 0 else (0, 11370)
        scale = .125 if n == 0 else .11
        p = Plan(s, (ox, 210), scale, offset)
        s.text(r["name"], ox, 165, class_="label")
        new_rooms(p, [r], operations=True)
        p.box(r["inside_approach_mm"], fill="none", stroke="#4d956d", stroke_dasharray="5 4")
        if n == 1:
            p.box(o["retained_sewer_shaft_mm"], fill="#b686ac", stroke="#7d4975")
        notes = ["900×600候選後窗，窗台1500。", "名義窗面0.54㎡，有效開口未知。", "公衛600盆、450×700便器與", "900淋浴不縮；全門態未核。"] if n == 0 else [
            "套衛原900×550盆櫃保留。", "便器旋轉90度，尺寸不變。", "加深20mm，扣原200管井後", "4.5149㎡，只略高於4.5下限。"]
        s.lines(notes, ox, 615, step=33, class_="small")
    s.lines(["代價不只有搬浴室：", "新增公共通道約3.608㎡", "（115假設），主臥扣豎道", "後剩16.0889㎡，低於20目標。", "套衛門朝床仍未解，不能採用。",
        "後窗權利與外部遮擋未知；", "無後巷的前門版也不能假設", "後牆能開窗或排風。", "",
        "左前套衛仍需自己的排氣。", "原右牆主臥冷氣落入新通道，", "不能沿用成已完成空調。", "管線、鏡面及門窗另合圖。"], 930, 210, step=33, class_="small")
    s.lines(["原床1800×2000、衣櫃1800×600、梳妝台1200×500及主臥2400後窗不縮；二樓房內900局部直段可試排。",
        "操作虛框與900門前到達可分時互疊；器具、管井及新增豎道未碰列明固定本體，但不等所有門態／照護已核。",
        "三樓只有後右公衛；二樓左前套衛污水向下排，通氣管上引經三樓左前乾區的防火／隔音與檢修待核。"], 30, 895, step=33, class_="small")
    return s.output()


def index_html(report):
    m, w = report["options"]
    comparison = table(["項目", "保格局、獨立屋頂排氣", "後右有窗公衛重排"], [
        ["主臥扣新增豎道", f"{m['master_after_reservations_sqm']:.4f}㎡", f"{w['master_after_reservations_sqm']:.4f}㎡"],
        ["二樓公衛／套衛", "4.4667／4.7124㎡", "4.7124／4.5149㎡"],
        ["一般公衛外窗", "沒有；機械排氣待工程核圖", "900×600後窗候選，合法與有效開口未知"],
        ["三樓", "左前公衛、後右乾區；不新增套衛", "後右公衛、左前乾區；不新增套衛"],
        ["工程代價", "新500×300豎道0.15㎡，兩層各自管路", "搬兩衛、增通道、改門，套衛仍需300×300排氣豎道"],
        ["門口朝床初篩", "床前移、衣櫃後移，套衛門正向投影未碰床", "左前套衛後門投影碰床，尚未解決"],
        ["原要求", "主臥暫守20、餘量僅0.0761；兩衛原5／6未達", "主臥未達20；兩衛原5／6也未達，尚未同意取捨"]])
    flow = table(["工程比較假設", "本案估算需要送出的風量"], [
        [f"{r['air_changes_h']}次／小時", f"{r['delivered_q_m3_h']:.1f}m³/h"] for r in report["airflow"]["ach_cases"]])
    opened = table(["下一步資料", "要回答的問題"], [
        ["側界／後界外牆與合法開口", "先核側窗是否有條件；若可合法開側窗，才可能有更小改法"],
        ["結構與天花", "穿板、防火、梁底與檢修包覆能否留在預算內，主臥20㎡會不會再不足"],
        ["風機及管道", "按實際阻力核P-Q曲線，再核噪音、補氣、保溫、防雨及防颱"],
        ["面積與外窗偏好", "兩案都有代價；尚未替屋主降低主臥／衛浴目標或接受無窗公衛"]])
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B二三樓公衛｜外窗與獨立排氣比較</title>
<style>body{{font:17px/1.75 system-ui,sans-serif;color:#283e46;background:#f5f8f3;margin:0}}main{{max-width:1180px;margin:auto;padding:25px 20px 65px}}section{{background:#fff;border:1px solid #d7e1d6;padding:24px;margin:26px 0;border-radius:10px}}h1{{font-size:29px}}h2{{font-size:23px}}a{{color:#17687d}}a:focus-visible{{outline:3px solid #ac7035;outline-offset:3px}}nav{{display:flex;gap:16px;flex-wrap:wrap}}.notice{{padding:17px;background:#fff1de;border-left:5px solid #ae6e32}}.table{{overflow:auto}}table{{width:100%;min-width:650px;border-collapse:collapse;font-size:15px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #dbe2d7;vertical-align:top}}th{{background:#edf2e9}}img{{max-width:100%;height:auto;display:block;margin:18px auto}}small{{font-size:14px}}code{{overflow-wrap:anywhere}}</style></head><body><main>
<h1>B二三樓公衛：先比外窗的代價，再核獨立排氣</h1>
<p>同一6000×17630mm概念框內，補上後右有窗公衛的原尺寸器具與獨立到達；保格局方向則補兩層分開排氣到屋頂的候選。</p>
<p class="notice"><strong>獨立比較，尚未採用，也不是風水、通風或建照核可。有窗重排案的套衛門朝床仍未解，不列可採用方案。</strong> 本批沒有改一樓有窗公衛、祭祀正門、後門優先或前門備案；原3D與149份控制保留。新方案尚未由Claude審閱，不能繼承上輪局部共識或舊畫面passed。</p>
<nav><a href="#compare">兩案代價</a><a href="#drawings">三張圖</a><a href="#duct">排氣與防黴</a><a href="#window">外窗條件</a><a href="#decision">建議與待決定</a></nav>
<section id="compare"><h2>建議暫保主臥20㎡，先核屋頂排氣</h2>{comparison}
<p>後窗方案要讓訪客從右側公共通道進公衛，不能借主臥當走道；所以主臥由20.2261㎡降至輪廓16.1789㎡，再扣0.09㎡排氣豎道後為16.0889㎡。這是已試排原尺寸家具的比較，仍沒有替屋主接受縮房。</p>
<p>保格局方案新增500×300mm排氣豎道，原主臥扣0.15㎡後只剩20.0761㎡，餘量很薄。該預算包括兩條DN125與每側25mm保溫的示意外廓，實際包覆、防火及檢修若更大，20㎡可能守不住。</p>
<p>逐門初篩發現，原套衛門正向投影會碰床，與門片碰撞是不同問題。本批保房間位置案將床前移1815mm、衣櫃後移2030mm，尺寸不縮；排氣豎道移至主臥前臂，正向投影不再碰床。實際斜視線、鏡面、窗扇與門組仍待核。有窗案原尺寸家具雖放得下，套衛門朝床尚未解決，不因關門就視為已避開。</p>
<p>床前移後，原右牆機盒可能直吹床；本批另畫前臂前壁上方的950×280×280mm冷氣盒候選，平面朝後投影避床、也未碰排氣外廓。它在梳妝區上方，鏡高、實機、冷媒／冷凝水、氣流與維修都需重新核對。</p>
<p>原主臥20／公衛5／套衛6㎡目標及兩衛3.6／4.5㎡下限不變；兩案沒有完成全部原要求。每面115mm內縮仍只是敏感度模型，不是實測或合法淨面積。</p></section>
<section id="drawings"><h2>三張新圖</h2><p><a href="B01-options.svg">同框兩案</a>／<a href="B02-independent-ducts.svg">兩層獨立屋頂排氣</a>／<a href="B03-rear-window-baths.svg">有窗兩衛器具及通道</a></p>
<img src="B01-options.svg" width="1400" height="1100" alt="保格局排氣與後窗公衛重排：主臥20.0761與16.0889平方米的代價">
<img src="B02-independent-ducts.svg" width="1400" height="1100" loading="lazy" alt="500乘300毫米豎道與二三樓各自排氣管到屋頂的平面及標高示意">
<img src="B03-rear-window-baths.svg" width="1400" height="1100" loading="lazy" alt="後右公衛600毫米盆與900淋浴，左前套衛保900毫米盆櫃並旋轉便器，公共通道獨立到達"></section>
<section id="duct"><h2>機械排氣有具體預算，性能仍待核</h2><p>二樓與三樓分別用自己的排氣管及止回設備到模型RF戶外服務區，不共用污水通氣管、樓梯、乾保護室或封閉夾層。兩管中心線估長8.905m／6.155m，尚未計實際彎頭等效阻力或風帽損失。</p>
<p>管道與豎道的列明平面預算避祭祀保護區、武轎庫及原污水管井，沒有核定穿梁或穿板。新機盒位置、梁底、樓板、防火包覆、防水、檢修與屋頂出風帽另需正式圖說。</p>
<p>以公衛扣污水管井4.4667㎡、天花2.4m估容積10.72m³，以下只是工程比較假設，<strong>不是法定換氣標準或除黴保證</strong>：</p>{flow}
<p>例如120m³/h經125mm內徑管，直管平均流速約2.72m/s；這不能替代實際阻力與風機曲線。需確認門關時的補氣、安裝後風口實測風量、噪音與震動，不能只看無管路時的最大風量。</p>
<p>補氣從一般公共乾區進，不從神明堂乾保護室或其他浴廁串氣。室外高濕時，通風未必能降低室內含濕量；防水、乾濕分區、保溫與必要的除濕仍要一起檢查，不保證有窗或有風機就不發黴。</p></section>
<section id="window"><h2>側窗不能預設，後窗也要核對實際外部條件</h2><p>現有資料只確認側界可能共壁，沒有地籍棟距或合法開窗依據，因此沒有把側窗畫成可用。若正式圖證明左側可合法對外開窗，才可能保原位置而少改格局；也沒有斷言側窗永久不可行。</p>
<p>後窗方案使用原後牆900×600mm候選，名義窗面0.54㎡不能當有效通風開口；框料、開啟方式、紗網、防雨及外部遮擋尚未核。後巷可搬轎也不等於合法開窗；無後巷前門版更不能借用後巷權利。</p>
<p>後右公衛有窗，移到左前的套衛仍須獨立屋頂排氣。一般浴廁機械通風與高雄厝申報浴廁的直接外窗條件要分開核對，本輪沒有取得任何申報資格或法規核可。</p></section>
<section id="decision"><h2>暫保房間位置，先取得能否落實的工程資料</h2>{opened}
<p><a href="decision-and-engineering.csv">偏好與工程回覆空表</a>／<a href="review.json">全部坐標、計算與來源</a>／<a href="../b-claude-round3-v1/index.html">上輪祭祀、管井與前後門比較</a>／<a href="../../../Docs/b-bath-ventilation-v1.md">說明文件</a>。</p>
<p>屋主已確認武轎不必進神明堂、不禁轎路上方浴廁污水管、不禁庫房上方臥室；其他祭祀／乾背櫃保護規則照舊。本輪偏好尚未答覆，沒有因繼續工作就改成採用。</p></section>
<small>2026-11-06｜來源 <code>{html.escape(report['source_layout_report_sha256'])}</code><br>本批 <code>{html.escape(report['report_hash'])}</code>｜靜態比較，沒有瀏覽器或WebGL驗收。</small>
</main></body></html>'''


def render(report):
    replies = [{"id": "B-UPPER-VENT-01", "topic": "二三樓公衛外窗與主臥取捨", "recommendation": report["recommendation"],
        "owner_reply": None, "engineering_evidence": None, "status": "pending"}]
    replies += [{"id": f"B-VENT-ENG-{n:02d}", "topic": topic, "recommendation": "依本版候選坐標核對",
        "owner_reply": None, "engineering_evidence": None, "status": "unknown"}
        for n, topic in enumerate(report["airflow"]["required_product_data"], 1)]
    files = {"B01-options.svg": comparison_sheet(report), "B02-independent-ducts.svg": roof_duct_sheet(report),
        "B03-rear-window-baths.svg": window_bath_sheet(report), "index.html": index_html(report),
        "decision-and-engineering.csv": csv_text(replies), "review.json": json.dumps(report, ensure_ascii=False, indent=2)+"\n"}
    manifest = {"schema": "house-b-bath-ventilation-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "adopted": False, "professional_approval": "unknown",
        "artifacts": {name: hashlib.sha256(value.encode()).hexdigest() for name, value in files.items()}}
    files["artifact-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files, output = render(report), ROOT/OUT
        if args.check:
            stale = [n for n, data in files.items() if not (output/n).is_file() or (output/n).read_bytes() != data.encode()]
            if stale:
                raise ContractError("B ventilation static artifacts stale: "+", ".join(stale))
        else:
            output.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (output/name).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported-static-comparisons", "artifacts": len(files),
            "options": len(report["options"]), "protected_controls_unchanged": report["protected_controls_unchanged"],
            "browser": "not-run", "adopted": False}))
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

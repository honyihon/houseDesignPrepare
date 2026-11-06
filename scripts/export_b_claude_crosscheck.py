#!/usr/bin/env python3
"""Render bounded, independent comparisons of Claude's B layout and Codex checks."""
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

from house_design.b_claude_crosscheck import OUT, build  # noqa: E402
from house_design.contracts import ContractError, read_json  # noqa: E402
from scripts.export_abc_next_improvements import Plan, Sheet, csv_text, table  # noqa: E402
from scripts.export_b_fengshui_strict import new_rooms, polygon  # noqa: E402


def compare_sheet(report, previous):
    s = Sheet("B-Claude01｜前案／Claude新案／Codex餘量比較", report)
    s.text("三案保持一樓同軸祭祀門、獨立乾背櫃與前後搬轎兩版；本張只比較二樓後段。", 30, 116)
    cases = [("前案：公衛與套衛均在後右", previous["options"][0]["upper_floors"][0]["rooms"], None),
        ("Claude：左前公衛、右後套衛", report["variants"][0]["rooms"], report["variants"][0]),
        ("Codex：套衛前牆再後移100", report["variants"][1]["rooms"], report["variants"][1])]
    for n, (title, rooms, variant) in enumerate(cases):
        ox = 30+n*460
        s.text(title, ox, 158, class_="label")
        plan = Plan(s, (ox, 195), .062, (0, 11370))
        new_rooms(plan, rooms, labels=False)
        if variant:
            plan.box(variant["bedroom_rear_inscribed_rect_mm"], fill="none", stroke="#809a85", stroke_dasharray="5 4")
            plan.path(variant["route"]["points_mm"], stroke="#407d57", stroke_width=1.5, stroke_dasharray="5 4")
            area = variant["current_inset_case"]
            values = [area["bedroom"], area["public_bath"], area["private_bath"]]
            more = ["後段虛框可完整內接14.423㎡。", "主臥總面積含狹長入口與轉折。"]
        else:
            area = report["previous_study_summary"]["case_115"]
            values = [area["bedroom_sqm"], area["public_bath_sqm"], area["private_bath_sqm"]]
            more = ["套衛未達原4.5㎡下限。", "本案保留歷史比較。"]
        s.lines(["每面115mm假設內縮：", f"主臥 {values[0]:.4f}㎡", f"公衛 {values[1]:.4f}㎡", f"套衛 {values[2]:.4f}㎡", *more], ox, 635, step=32, class_="small")
    s.lines(["原面積目標仍保留：主臥20、公衛5、套衛6㎡；兩衛下限3.6／4.5㎡。Claude新案兩衛目標仍差1.5939㎡。",
        "Claude主臥115假設只餘0.0161㎡；每面多扣1mm即19.9925㎡。Codex100mm比較換到20.2261㎡，未經Claude確認。",
        "兩個新案的普通器具本體與700操作帶可試排；正式牆柱、完整門組、鏡面、排水與家規核可仍待資料。"], 30, 895, step=37, class_="small")
    return s.output()


def floors_sheet(report, previous):
    variant = report["variants"][0]
    s = Sheet("B-Claude02｜新拓樸上下層：完整用途與濕區投影", report)
    s.text("一樓沿用上輪嚴格比較，原3D尚未改；二三樓採Claude四區拓樸作尺寸比較，不代表採用。", 30, 116)
    for n, title in enumerate(["1F 後門優先參照", "2F 三室獨立入口", "3F 公衛／乾式後區", "上下層保護投影"]):
        ox = 30+n*345
        s.text(title, ox, 158, class_="label")
        plan = Plan(s, (ox, 185), .0395)
        if n == 0:
            plan.rooms(report["carry_and_drain"][0]["floor1"]["rooms"])
        elif n in {1, 2}:
            front = previous["options"][0]["upper_floors"][n-1]["retained_front"]
            plan.rooms(front)
            rooms = variant["rooms"] if n == 1 else variant["third_floor_rooms"]
            new_rooms(plan, rooms, labels=False)
            plan.text("乾室", 2800, 12150, class_="tiny")
            plan.text("公衛", 200, 12150, class_="tiny")
            plan.text("主臥" if n == 1 else "客房", 200, 15000, class_="tiny")
            plan.text("套衛" if n == 1 else "乾預留", 4200, 15850, class_="tiny")
        else:
            plan.box([0, 0, 6000, 17630], fill="#f0f2e9", stroke="#92a497")
            for poly in previous["options"][0]["protected_polygons_mm"]:
                polygon(plan, poly, fill="#d5e6cf", stroke="#699061", stroke_dasharray="5 3")
            for r in variant["rooms"][2:]:
                polygon(plan, r["polygon_mm"], fill="#e0b787", stroke="#a57645")
            plan.box(previous["options"][0]["palanquin_rect_mm"], fill="none", stroke="#5f86a7", stroke_width=2)
    s.lines(["綠保護投影＝完整神明堂＋乾背櫃；橘為新二樓濕區；藍框為一樓後左武轎庫。房間投影沒有面積重疊。",
        "左前公衛與保護區名義邊界相接，沒有前案200mm分區餘距；實際牆、防水與立管必須再合圖。",
        "公衛從前方公共乾區直接進，不穿主臥；乾室有自己的前門，右後套衛僅通主臥。3F不新增第二衛浴。"], 30, 935, step=33, class_="small")
    return s.output()


def interfaces_sheet(report):
    s = Sheet("B-Claude03｜搬轎與新公衛管道：兩版分開判斷", report)
    s.text("上層公衛移左前，管道不能任意落在下層搬轎接段；尚無選定立管或排水終端。", 30, 116)
    for n, row in enumerate(report["carry_and_drain"]):
        ox = 35+n*465
        s.text("後門直接入庫" if n == 0 else "無後巷前門備案", ox, 160, class_="label")
        plan = Plan(s, (ox, 195), .058, (0, 11370))
        plan.rooms(row["floor1"]["rooms"], min_y=11370)
        plan.box(report["config"]["upper"]["public_bath_rect_mm"], fill="#dcb282", fill_opacity=.25,
            stroke="#ad713b", stroke_dasharray="6 4", stroke_width=2)
        plan.text("上層新公衛投影", 150, 11850, class_="small")
        if n == 0:
            plan.line([1150, 17630], [1150, 15700], stroke="#367896", stroke_width=3)
        else:
            plan.line([875, 11670], [875, 15100], stroke="#367896", stroke_width=3, stroke_dasharray="5 4")
        notes = ["後門名義1960，直接入後左庫。", "1360接段不在此必經路線。", "若改經1360，必定不足1500目標。", "外巷、門框、抬桿及人員仍待演練。"] if n == 0 else [
            "接段1750、寬門1730名義。", "門扣230假設後僅1500，零餘量。", "不能用後門版路線替它背書。", "搬轎分時整備條件保留。"]
        s.lines(notes, ox, 650, step=35, class_="small")
    s.lines(["新立管與檢修：", "下方家務區可研究，", "未指定可施工落點。", "不得縮接段或穿保護區。", "公衛沒有後外窗；", "獨立排氣／補氣未核。", "不拿側界假窗補通風。", "",
        "門片與床：", "套衛外開門全開預算", "到原床後緣僅15mm。", "薄餘量仍須門商合圖。", "鏡面／斜視／梁未知。"], 1000, 195, step=36, class_="small")
    s.lines(["藍線只標必要路線方向；橘虛框是上層公衛投影，不等於下層新增浴室／管井或搬運掃掠。",
        "立管位置、尺寸與完成牆仍是unknown；不能因上層器具放下，就稱風水、消防或搬轎全部符合。"], 30, 925, step=38, class_="small")
    return s.output()


def index_html(report):
    variants = report["variants"]
    data = table(["115mm假設內縮", "主臥㎡", "公衛㎡", "套衛㎡", "判讀"], [
        ["上一輪Codex案", 20.1141, 3.8709, 3.6091, "套衛未達4.5下限"],
        ["Claude三入口案", 20.0161, 4.5067, 4.8994, "達列明下限，主臥僅餘0.0161"],
        ["Codex100mm餘量比較", variants[1]["current_inset_case"]["bedroom"], 4.5067,
         variants[1]["current_inset_case"]["private_bath"], "套衛讓部分面積予主臥；尚未送Claude確認"]])
    agreement = table(["議題", "交叉核對結果"], [[r["topic"], r["evidence"]] for r in report["agreement_log"]])
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B與Claude交叉核對｜兩衛與祭祀</title>
<style>body{{font:17px/1.75 system-ui,sans-serif;color:#273e46;background:#f6f8f3;margin:0}}main{{max-width:1180px;margin:auto;padding:25px 20px 65px}}section{{background:white;border:1px solid #d7e1d6;padding:24px;margin:26px 0;border-radius:10px}}h1{{font-size:29px}}h2{{font-size:23px}}a{{color:#17687d}}a:focus-visible{{outline:3px solid #ac7035;outline-offset:3px}}nav{{display:flex;gap:15px;flex-wrap:wrap}}.notice{{padding:17px;background:#fff1de;border-left:5px solid #ae6e32}}.table{{overflow:auto}}table{{width:100%;min-width:650px;border-collapse:collapse;font-size:15px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #dbe2d7;vertical-align:top}}th{{background:#edf2e9}}img{{max-width:100%;height:auto;display:block;margin:18px auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;padding:17px;background:#edf2e9;font-size:14px}}small{{font-size:14px}}</style></head><body><main>
<h1>Claude新排法已核對：改善兩衛，保留未解</h1><p>Claude回覆改採「前方乾區三入口、左前公衛、右後套衛」。Codex獨立重算面積、房間分割、家具與門前；本頁把前案、新案及新增餘量比較放一起。</p>
<p class="notice"><strong>比較方案，尚未採用，也未達全部原目標。</strong> 兩衛仍少於原5＋6㎡目標。Claude主臥每面多扣1mm即跌至19.9925㎡；正式梁柱、管道、完整門組、坐向與鏡面仍未知，沒有整體風水／施工通過結論。</p>
<nav><a href="#areas">面積與空間感</a><a href="#drawings">比較圖</a><a href="#carry">搬轎／排水</a><a href="#discussion">共識與待討論</a><a href="#claude">回覆與下一輪</a></nav>
<section id="areas"><h2>數字正確，但主臥餘量不足</h2>{data}<p>Claude四區恰好拼滿原6000×6260後段，沒有額外借面積，兩衛比前案增加1.9261㎡。原5＋6㎡目標仍差1.5939㎡；Codex100mm比較的差額更大，不默默改原需求。</p>
<p>20㎡包括狹長入口、轉折與梳妝區。後段可完整內接的矩形約14.4231㎡；因此整間總面積達20，也還需要看實際空間感與收納使用。原床1800×2000、1800衣櫃、1200梳妝台、2400後窗及900盆櫃保留。</p>
<p>Codex另比較套衛前牆後移100mm：主臥115假設增至20.2261㎡、套衛降至4.7124㎡，仍過4.5下限；但150mm假設下仍有不足。這是待Claude挑錯的新比較，沒有替屋主接受縮減目標。</p></section>
<section id="drawings"><h2>三張新圖</h2><p><a href="B01-comparison.svg">三案同尺度</a>／<a href="B02-projection.svg">上下層投影與三入口</a>／<a href="B03-carry-drain.svg">前後搬轎與新立管介面</a></p>
<img src="B01-comparison.svg" width="1400" height="1100" alt="前案、Claude三入口與Codex100mm比較的同尺度房間與面積圖">
<img src="B02-projection.svg" width="1400" height="1100" loading="lazy" alt="完整神明堂背櫃保護投影及左前公衛、右後套衛的新排法"></section>
<section id="carry"><h2>後門直接入庫，前門接段仍要獨立核</h2><p>同意Claude的條件句：若經1360mm接段，即使不扣裝修也不足1500mm。但後門直接進後左武轎庫，不必經該段；不能把這個斷面直接當成後門方案的必經瓶頸。</p>
<p>前門版確實需經1750mm接段及1730名義寬門，門在230mm扣框假設下恰好1500，沒有施工、把手或產品餘量。兩版的巷道權利、抬桿、人員及真正門組仍待核，原1500完成淨寬目標不改。</p>
<p>新公衛在一樓搬轎／家務區上方，且與祭祀／背櫃保護區的名義界線相接。管井不能隨便落在搬轎接段；下方家務區可研究，尚無選定尺寸、位置或合法終端。若機電做不到，應淘汰該排法，不能只以面積表採用。</p></section>
<section id="discussion"><h2>已能同意的範圍與還沒同意的事項</h2>{agreement}<p>Codex接受Claude的新拓樸作優先比較，也同意兩衛維持獨立、暫不改共用雙門浴室。這些局部意見相符，不等於我們已就所有空間、管道與風水達成完整共識。</p>
<p><a href="agreement-log.csv">交叉核對記錄</a>／<a href="open-items.csv">未決與工程資料空表</a>／<a href="review.json">全部幾何與來源</a>。原3D與149份控制保留；<a href="../b-fengshui-strict-v1/index.html">前案</a>仍可比較。</p></section>
<section id="claude"><h2>回覆保留與下一輪具體檢討</h2><p>上回已核對來源prompt、原stdout雜湊及回覆內容相符；原TEMP路徑本回合不可讀。這裡保存<a href="../../../inputs/references/b-claude-response-v2-transcript-20261105.md">當時完整讀取的回覆轉存稿</a>與<a href="../../../inputs/references/b-claude-response-v2-provenance.json">取得方式及當時核對紀錄</a>，不偽稱目前仍有原始stdout檔。</p>
<p>下一輪請Claude回應1360路線範圍、主臥含入口的空間品質、Codex100mm餘量比較與左前公衛立管。依專案20秒／逾時分流規則，較長雲端討論由屋主另WSL終端執行；輸出這次存專案私有目錄，避免TEMP遺失：</p>
<pre>cd /root/workspace/houseDesignPrepare
python3 scripts/review_b_fengshui_with_claude.py \
  --brief Docs/claude-b-fengshui-followup-v3.md \
  --timeout 900 \
  --output inputs/private/b-claude-round3-20261106</pre>
<p>只讀，不改圖、不自動採用或登入。目錄需為新建／空目錄，避免覆蓋舊回覆。完成後貼最後Result路徑即可；目前未自動再呼叫Claude。</p></section>
<small>2026-11-06｜來源 {html.escape(report['source_layout_report_sha256'])}<br>本批 {html.escape(report['report_hash'])}｜靜態比較，未執行瀏覽器／WebGL。</small>
</main></body></html>'''


def render(report, previous):
    open_rows = [
        {"id": "B-OPEN-01", "topic": "原20／5／6㎡目標與工差", "status": "not-all-met", "recommendation": "先比較新拓樸及100mm餘量版本；未改需求或採用", "owner_decision": None, "engineering_reply": None},
        {"id": "B-OPEN-02", "topic": "左前公衛立管／排氣", "status": "unknown", "recommendation": "不得侵入搬轎接段或祭祀保護區，補具體管道／檢修圖", "owner_decision": None, "engineering_reply": None},
        {"id": "B-OPEN-03", "topic": "門／鏡面／梁板／座向", "status": "unknown", "recommendation": "完整門組與正式圖再核；15mm葉片／床餘量不能視為施工容差", "owner_decision": None, "engineering_reply": None},
        {"id": "B-OPEN-04", "topic": "前後兩版全路徑搬轎", "status": "unknown", "recommendation": "後門直入與前門1750／1730分開核；保1500完成淨寬目標", "owner_decision": None, "engineering_reply": None}]
    files = {"B01-comparison.svg": compare_sheet(report, previous), "B02-projection.svg": floors_sheet(report, previous),
        "B03-carry-drain.svg": interfaces_sheet(report), "index.html": index_html(report),
        "review.json": json.dumps(report, ensure_ascii=False, indent=2)+"\n",
        "agreement-log.csv": csv_text(report["agreement_log"]), "open-items.csv": csv_text(open_rows)}
    manifest = {"schema": "house-b-claude-crosscheck-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "adopted": False, "full_consensus": False,
        "artifacts": {name: hashlib.sha256(value.encode()).hexdigest() for name, value in files.items()}}
    files["artifact-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files, directory = render(report, read_json(ROOT/report["config"]["previous_study"])), ROOT/OUT
        if args.check:
            stale = [name for name, data in files.items() if not (directory/name).is_file() or
                     (directory/name).read_bytes() != data.encode()]
            if stale:
                raise ContractError("B Claude static comparisons stale: "+", ".join(stale))
        else:
            directory.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (directory/name).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported-static-comparisons", "artifacts": len(files),
            "claude_claims_independently_matched": len(report["claim_checks"]), "controls_unchanged": report["protected_controls_unchanged"],
            "full_consensus": False, "adopted": False, "browser": "not-run"}))
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

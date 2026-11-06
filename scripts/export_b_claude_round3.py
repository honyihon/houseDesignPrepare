#!/usr/bin/env python3
"""Export three bounded B research sheets, without modifying the original 3D."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path

from shapely.geometry import Polygon, box

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.b_claude_round3 import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import Plan, Sheet, csv_text, table  # noqa: E402
from scripts.export_b_fengshui_strict import new_rooms, polygon  # noqa: E402


def upper_sheet(report):
    v = report["variants"][1]
    s = Sheet("B第三輪01｜100mm基線＋公衛器具／立管深化", report)
    s.text("Claude同意100mm基線；紫框管井為候選，洗衣機及右牆機盒修正尚未由Claude審閱。", 30, 116)
    p = Plan(s, (35, 185), .09, (0, 11370))
    new_rooms(p, v["rooms"], operations=True)
    p.box(v["shaft"]["rect_mm"], fill="#b98db4", stroke="#7b4376", stroke_width=2)
    p.box(v["no_pipe_strip_mm"], fill="#e2e8ba", stroke="#839653", stroke_dasharray="3 2")
    for room in v["rooms"][2:]:
        p.box(room["inside_approach_mm"], fill="none", stroke="#4f9467", stroke_dasharray="5 4")
        d = room["doors"][0]
        if room["id"] == "private-bath":
            p.box(d["parked_leaf_budget_mm"], fill="#dec49e", stroke="#ad7946")
    p.path(v["route"]["points_mm"], stroke="#4d855b", stroke_width=2, stroke_dasharray="5 4")
    p.text("獨立乾室", 2810, 12200, class_="small")
    p.text("主臥", 800, 14800, class_="small")
    p.text("右牆機盒", 4700, 14550, class_="tiny")
    s.lines(["每面115mm內縮估算：", "主臥 20.2261㎡", "公衛輪廓 4.5067㎡", "減200×200管井 0.0400㎡", "公衛扣管井後 4.4667㎡", "套衛 4.7124㎡", "",
        "完整家具保留：", "床1800×2000／櫃1800×600", "梳妝1200×500／後窗2400", "公衛盆600×450／套衛盆900×550", "便器450×700／淋浴900×900"], 650, 185, step=32)
    s.lines(["公衛新試排：", "便器離左完成牆150mm。", "淋浴向左移200mm；濕面到", "乾室名義左界由115增至315mm。", "管井到乾室角部約218mm；", "東側綠條不排管。", "200管井能否裝管及檢修未知。", "公衛向前外開門片在本圖外。",
        "左前公衛沒有直接外窗。", "排氣、補氣與排水坡另核。", "700操作虛框／900到達有共享，", "只能分時，不代表照護核可。"], 1020, 185, step=32, class_="small")
    s.lines(["房間輪廓沿用NEW-01；20㎡含狹長入口／梳妝與轉折，後段最大內接矩形只有14.4231㎡。",
        "原目標20／5／6㎡及兩衛下限3.6／4.5㎡不改；本案仍未全達原目標。",
        "三樓延用公衛器具與管井候選，右後保持乾預留；屋頂只核對管井投影，通氣終端未選。"], 30, 880, step=36, class_="small")
    return s.output()


def entry_sheet(report):
    v, stack = report["variants"][1], report["stack_and_entry"]
    s = Sheet("B第三輪02｜後門／前門：管井落點與洗衣機修正", report)
    s.text("同一200×200立管投影到兩版1F，不能把後門配置與前門洗衣機混用。橘線為上層公衛。", 30, 116)
    for n, o in enumerate(stack["options"]):
        ox = 35+n*470
        s.text("後門優先：直接入庫" if n == 0 else "無後巷備案：前門經側緣", ox, 160, class_="label")
        p = Plan(s, (ox, 195), .063, (0, 11370))
        f = o["states"][0]["floor1"]
        p.rooms(f["rooms"], min_y=11370)
        p.box([0, 11370, 2640, 2100], fill="#e1bd8b", fill_opacity=.13, stroke="#b47d3f", stroke_dasharray="6 4")
        p.box(stack["shaft_absolute_mm"], fill="#bb8db7", stroke="#703a71", stroke_width=2)
        if n == 0:
            p.path([[1150, 17630], [1150, 15700]], stroke="#367e9c", stroke_width=3)
        else:
            p.path([[875, 11670], [875, 15100]], stroke="#367e9c", stroke_width=3, stroke_dasharray="5 4")
            old = stack["original_front_washer_conflict"]["washer_rect_mm"]
            p.box(old, fill="none", stroke="#b5574a", stroke_dasharray="4 3")
            check = o["states"][0]["laundry_check"]
            p.box(check["washer_operation_mm"], fill="#d2e1d1", fill_opacity=.45, stroke="#688d67", stroke_dasharray="4 3")
            p.box(check["door_swept_rectangle_mm"], fill="none", stroke="#b9864d", stroke_dasharray="5 4")
            p.text("洗衣機", 2820, 13550, class_="tiny")
        notes = ["後門名義1960，直接進後左庫。", "1360接段不在後巷到庫房必要線。", "屋主確認武轎不必搬入神明堂。", "管井未碰列明家具；檢修仍未知。"] if n == 0 else [
            "管井與原洗衣機重疊0.038㎡（紅虛框）。", "新機位右移990，650×650機身不縮。", "機身避開管井及門開矩形預算。", "洗衣操作與門開共享0.44525㎡，須分時。"]
        s.lines(notes, ox, 650, step=34, class_="small")
    s.lines(["兩版共同未解：", "200×200只是預算，", "DN100／通氣／清掃口", "及維修可達未核。", "",
        "前門接段1750／門1730，", "門扣230假設僅1500。", "公衛投影前接段3.15㎡。", "屋主確認不禁止通道", "上方浴廁及污水管。", "工程與檢修仍待核。", "",
        "本張藍線是路線方向，", "不等裝桿／抬轎掃掠。"], 1010, 195, step=34, class_="small")
    s.lines(["後門優先與前門備案各保留日常／祭祀／搬運三態；祭祀中軸門及神桌、乾背櫃與原庫房位置不改。",
        "新洗衣機要重排給排水／插座，家務門鉸鏈與完整門組仍未提供；沒有完成施工或搬運驗證。",
        f"公衛東側乾條 {v['no_pipe_strip_mm']} 不排管；立管橫向污水與屋頂終端尚未設計。"], 30, 885, step=35, class_="small")
    return s.output()


def door_sheet(report):
    a, b = report["variants"]
    d = report["door_and_ac"]
    s = Sheet("B第三輪03｜更正床門距離，另排右牆冷氣候選", report)
    s.text("上方仍朝道路、下方是後牆；只示2F主臥後段，3F機盒同位但不新增右後套衛。", 30, 116)
    p = Plan(s, (35, 185), .105, (0, 12970))
    cropped = Polygon(b["rooms"][0]["polygon_mm"]).intersection(box(0, 12970, 6000, 17630))
    polygon(p, list(cropped.exterior.coords), fill="#edf1ec", stroke="#819990")
    polygon(p, b["rooms"][-1]["polygon_mm"], fill="#e1ecee", stroke="#819990")
    for i in b["rooms"][0]["furniture"]:
        p.box(i["rect_mm"], fill="#bdccce", stroke="#718d92")
        p.text({"bed": "原床", "wardrobe": "衣櫃", "vanity": "梳妝"}[i["id"]], i["rect_mm"][0]+50,
            i["rect_mm"][1]+220, class_="small")
    door = b["rooms"][-1]["doors"][0]
    p.line(door["a"], door["b"], stroke="#4f8667", stroke_width=4)
    p.box(d["leaf_budget_mm"], fill="#d5b37f", stroke="#a4753e", stroke_width=2)
    p.box(b["rooms"][-1]["outside_approach_mm"], fill="none", stroke="#5f986c", stroke_dasharray="4 3")
    old_ac, new_ac = [v["rooms"][0]["hvac_candidate"]["rect_mm"] for v in [a, b]]
    p.box(old_ac, fill="none", stroke="#bd6658", stroke_dasharray="5 3", stroke_width=2)
    p.box(new_ac, fill="#7eb5cd", stroke="#3d7893", stroke_width=2)
    p.line([750, 17630], [3150, 17630], stroke="#5aa6c4", stroke_width=5)
    p.line([2150, 17100], [2770, 17100], stroke="#a16e40", stroke_width=2)
    p.text("x向620", 2180, 16980, class_="tiny")
    p.text("後窗2400保留", 800, 17960, class_="small")
    p.text("右牆機盒候選", 4250, 14200, class_="tiny")
    p.text("右後套衛", 4250, 15600, class_="small")
    s.lines(["更正先前15mm判讀：", "床止於x2150、門片始於x2770，", "x相隔620；y相隔15。", f"兩矩形最短距離 {d['bed_leaf_plan_distance_mm']:.2f}mm。", "所以15mm不是床門碰撞餘量。", "",
        "真正待核的是後牆／窗／門頭：", "全開葉片到假設後完成牆55mm。", "95mm預算有沒有含把手未知；", "門擋、開角、窗簾與窗扇需實品。", "原後牆機盒與門片平面重疊；", "假設2400高門頭會碰2350底機盒。"], 760, 185, step=33)
    s.lines(["Codex候選：機盒改右壁，保留950×280×280mm尺寸與2350mm底高。", "列明盒體在115假設房內，平面避後窗及全開門片；未承接舊配管作通過。",
        "冷媒、冷凝水、風吹床、服務淨空與實機固定位置都需重新設計；Claude尚未看此修正。",
        "本圖裁取y12970以後的實際房形；紅虛框是原後牆機盒，藍為新候選，棕為全開門片。",
        "完整前臂與900局部路徑見第1張；這是候選套繪，不是竣工尺寸。"], 30, 840, step=38, class_="small")
    return s.output()


def index_html(report):
    baseline, revised = report["variants"]
    areas = table(["研究版本／115mm假設", "主臥㎡", "公衛輪廓㎡", "扣管井後㎡", "套衛㎡"], [
        [v["id"], f"{v['current_inset_case']['bedroom']:.4f}",
         f"{v['public_area_accounting']['outline_finished_estimate_sqm']:.4f}",
         "未設管井" if v["id"] == "NEW-01" else f"{v['public_area_accounting']['after_shaft_estimate_sqm']:.4f}",
         f"{v['current_inset_case']['private_bath']:.4f}"] for v in [baseline, revised]])
    agreements = table(["議題", "核對結果"], [[r["topic"], r["evidence"]] for r in report["agreement_log"]])
    questions = table(["屋主已確認的家規", "本輪答覆", "影響"], [
        [r["question"], "未確認" if r["answer"] is None else "是" if r["answer"] else "否", r["impact"]]
        for r in report["owner_questions"]])
    alternatives = report["area_limits"]["two_bath_targets_area_only"]
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B第三輪深化｜100mm基線、立管與前後門</title>
<style>body{{font:17px/1.75 system-ui,sans-serif;color:#273e46;background:#f6f8f3;margin:0}}main{{max-width:1180px;margin:auto;padding:25px 20px 65px}}section{{background:#fff;border:1px solid #d7e1d6;padding:24px;margin:26px 0;border-radius:10px}}h1{{font-size:29px}}h2{{font-size:23px}}a{{color:#17687d}}a:focus-visible{{outline:3px solid #ac7035;outline-offset:3px}}nav{{display:flex;gap:16px;flex-wrap:wrap}}.notice{{padding:17px;background:#fff1de;border-left:5px solid #ae6e32}}.table{{overflow:auto}}table{{width:100%;min-width:650px;border-collapse:collapse;font-size:15px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #dbe2d7;vertical-align:top}}th{{background:#edf2e9}}img{{max-width:100%;height:auto;display:block;margin:18px auto}}small{{font-size:14px}}code{{overflow-wrap:anywhere}}</style></head><body><main>
<h1>B棟第三輪：以套衛後移100mm為深化基線</h1>
<p>Claude第三輪同意100mm比較；Codex已核對公衛器具、管井、兩版一樓及床門距離，另畫出洗衣機與右牆冷氣修正。</p>
<p class="notice"><strong>研究比較，尚未採用，沒有整體風水或施工通過結論。</strong> 原主臥20㎡、公衛5㎡、套衛6㎡目標未更動；前後門兩版、原3D及149份控制保留。兩模型只對明列內容形成局部共識。</p>
<nav><a href="#areas">面積與代價</a><a href="#drawings">三張深化圖</a><a href="#entry">搬轎與管道</a><a href="#decisions">已確認家規</a><a href="#ledger">共識範圍</a></nav>
<section id="areas"><h2>主臥多留餘量，兩衛仍低於原目標</h2>{areas}
<p>NEW-01b的管井占0.04㎡，公衛可用估算降到4.4667㎡；不能把輪廓4.5067㎡當作扣完管井的面積。兩衛仍高於原3.6／4.5㎡下限，但不等於接受降低5／6㎡目標。</p>
<p>主臥20.2261㎡包含入口與轉折，後段最大內接矩形14.4231㎡。100mm後移只把主臥守住20㎡的每面內縮臨界由115.68增至124.60mm，不代表多100mm施工工差。</p>
<p><strong>公衛外窗是本案代價：</strong>左前公衛沒有直接外窗。獨立排氣、補氣與終端尚未排，不能把側界假窗當合法外窗；若外窗是硬條件，須重排此案。</p>
<p>在固定後段37.56㎡、乾室3.248㎡及三房各自每面內縮115mm的模型內，20／5／6㎡理想三房至少還缺1.05924㎡。這是指定假設的必要面積界，不是土地不能建的通用證明。</p>
<p>Claude另提「保兩衛5／6㎡」的輪廓：主臥{alternatives['areas_115_sqm']['bedroom']:.3f}㎡、公衛5.00075㎡、套衛6.00083㎡；若加同管井，公衛只剩4.96075㎡。<strong>此方向尚未完整排器具、門窗與路徑，不列為完成方案，也沒有放棄20㎡主臥。</strong></p></section>
<section id="drawings"><h2>先看這三張</h2>
<p><a href="B01-new01b.svg">二樓完整配置與公衛</a>／<a href="B02-stack-entry.svg">後門、前門與洗衣機</a>／<a href="B03-door-ac.svg">床門距離與冷氣</a></p>
<img src="B01-new01b.svg" width="1400" height="1100" alt="NEW-01b二樓後段：原尺寸家具、兩衛器具、獨立乾室與200毫米管井候選">
<img src="B02-stack-entry.svg" width="1400" height="1100" loading="lazy" alt="兩個獨立一樓：後門直接入庫及前門洗衣機右移990毫米避管井">
<img src="B03-door-ac.svg" width="1400" height="1100" loading="lazy" alt="床與全開門片最短距離620.18毫米；右牆冷氣避後窗及門片的候選"></section>
<section id="entry"><h2>後門直入與前門備案各自保留</h2><p>後巷到後左庫不必經1360mm接段，這點兩模型已一致。屋主本輪確認武轎不必搬進神明堂，因此不把該內部接段當本方案的祭祀必經搬轎線；若將來改用途，要另重排。</p>
<p>前門版的公衛管井原本撞洗衣機0.038㎡。Codex將650×650mm機身右移990mm，避開管井及家務門的矩形開啟預算；洗衣操作與門開仍共享0.44525㎡，必須分時。給排水與插座要重排，此修正尚未給Claude審閱。</p>
<p>前門1730名義門扣230假設後僅1500mm，沒有產品或施工餘量；公衛在前方搬轎接段上方投影3.15㎡。屋主本輪確認不禁止通道上方浴廁污水管，這項家規已釐清；橫管、降板、防水與維修仍待工程核圖。</p>
<p>200×200管井、橫排坡度、清掃口、樓板降板、防水與屋頂通氣終端未核；三樓只有一間公衛，右後仍是乾區。右牆冷氣只核盒體位置，完整配管與氣流未知。</p></section>
<section id="decisions"><h2>三項家規已確認，面積與外窗尚未定案</h2>{questions}<p>本輪答覆原文「1.否 2. 否 3. 否」已保存在<a href="../../../inputs/references/b-owner-ritual-answers-20261106.json">屋主答覆來源</a>。沒有取消神桌朝街、中軸門、完整神明堂／乾背櫃保護或武轎庫上方禁浴廁等原規則。</p>
<p>仍需用正式牆線釐清「神明堂／背櫃投影是否連整道共牆厚度都須避開」。本案名義界線雖不重疊，並未證明牆厚、梁柱及污水橫管都已避開。</p>
<p><a href="owner-questions.csv">三項家規回覆表</a>／<a href="engineering-open-items.csv">工程待核表</a>。三項家規答覆沒有擴大為整套採用，也沒有改原面積或外窗偏好。</p></section>
<section id="ledger"><h2>模型共識與Codex新增修正分開記錄</h2>{agreements}
<p><a href="agreement-log.csv">完整共識表</a>／<a href="review.json">坐標、計算與來源</a>／<a href="../../../inputs/references/b-claude-round3-response-20261106.md">Claude第三輪原回覆</a>／<a href="../b-claude-crosscheck-v1/index.html">上輪凍結比較</a>。</p>
<p>第三輪回覆按原response檔bytes保存，prompt／stdout雜湊與原結果已核。這輪沒有再啟動雲端討論、瀏覽器或WebGL；原畫面的歷史passed沒有當作本批驗收。</p></section>
<small>2026-11-06｜來源 <code>{html.escape(report['source_layout_report_sha256'])}</code><br>本批 <code>{html.escape(report['report_hash'])}</code>｜靜態比較，沒有採用或專業核可。</small>
</main></body></html>'''


def render(report):
    engineering = [{"id": f"B-ENG-{n:02d}", "topic": topic, "status": "unknown", "reply": None, "reference": None}
        for n, topic in enumerate(report["professional_open_items"], 1)]
    files = {"B01-new01b.svg": upper_sheet(report), "B02-stack-entry.svg": entry_sheet(report),
        "B03-door-ac.svg": door_sheet(report), "index.html": index_html(report),
        "agreement-log.csv": csv_text(report["agreement_log"]), "owner-questions.csv": csv_text(report["owner_questions"]),
        "engineering-open-items.csv": csv_text(engineering), "review.json": json.dumps(report, ensure_ascii=False, indent=2)+"\n"}
    manifest = {"schema": "house-b-claude-round3-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "full_consensus": False, "adopted": False,
        "artifacts": {name: hashlib.sha256(value.encode()).hexdigest() for name, value in files.items()}}
    files["artifact-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files, directory = render(report), ROOT/OUT
        if args.check:
            stale = [name for name, text in files.items() if not (directory/name).is_file()
                or (directory/name).read_bytes() != text.encode()]
            if stale:
                raise ContractError("B round3 static artifacts stale: "+", ".join(stale))
        else:
            directory.mkdir(parents=True, exist_ok=True)
            for name, text in files.items():
                (directory/name).write_text(text, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported-static-comparisons", "artifacts": len(files),
            "controls_unchanged": report["protected_controls_unchanged"], "partial_research_agreement": True,
            "full_consensus": False, "adopted": False, "browser": "not-run"}))
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

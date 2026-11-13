#!/usr/bin/env python3
"""Export bounded static P3 front-service sheets without browser or scene work."""
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

from house_design.b_front_service_detail import OUT, build, leaves  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_upper_replan import Draw, Sheet  # noqa: E402
from scripts.export_builder_communication import page, ul  # noqa: E402

FIXTURES = {"toilet": "馬桶", "basin": "面盆", "tea-counter": "茶水槽候選", "shower": "淋浴"}
STATES = {"open": "全開", "half": "半開", "closed": "關閉"}


def front_drawing(sheet, report, origin=(55, 155), scale=.145, states=None, labels=True):
    """Front-only view; this is an overlay on frozen P2, not a new full-floor baseline."""
    states = states or {"bath": "open", "stair": "open"}
    cfg = report["config"]
    d = Draw(sheet, origin, scale)
    d.box([0, 0, 3270, 1980], fill="#dceff4", stroke="#537380", stroke_width=2)
    d.box([0, 1980, 3270, 1920], fill="#edf0df", stroke="#607c73", stroke_width=2)
    d.box([0, 3900, 2400, 1000], fill="#e4e6e0", stroke="#607c73", stroke_width=2)
    for item in cfg["public_fixtures"]+cfg["tea_furniture"]:
        d.box(item["operation_mm"], fill="none", stroke="#88a18c", stroke_dasharray="4 3")
        d.box(item["rect_mm"], fill="#b9c9be", stroke="#3c6355", stroke_width=1)
        if labels:
            x, y, w, h = item["rect_mm"]
            sheet.text(FIXTURES.get(item["id"], item["id"]), *d.point([x+w/2, y+h/2]), text_anchor="middle", class_="room")
    d.box(cfg["shared_shaft_mm"], fill="#ca9d8b", stroke="#9c4634", stroke_width=1)
    d.box(cfg["dry_maintenance_mm"], fill="none", stroke="#945c33", stroke_width=2, stroke_dasharray="6 3")
    d.line([2050, 0], [3050, 0], stroke="#1a9ac0", stroke_width=5)
    for spec in cfg["sliders"]:
        d.line(spec["a"], spec["b"], stroke="#fafbf8", stroke_width=5)
        for panel in leaves(spec, states[spec["id"]]):
            d.box(panel, fill="#ad896b", stroke="#744d30", stroke_width=1)
    route = cfg["routes"][0]["points_mm"]
    for a, b in zip(route, route[1:], strict=False):
        d.line(a, b, stroke="#286a84", stroke_width=2, stroke_dasharray="5 3")
    if labels:
        sheet.text("朝街外窗候選；不能借側界開窗", *d.point([0, -180]), class_="small")
        sheet.text("單一管井", *d.point([540, 1830]), class_="small")
        sheet.text("乾側檢修預留", *d.point([180, 2700]), class_="small")
        sheet.text("原梯核／平台，未改本體", *d.point([150, 4650]), class_="small")
    return d


def plan_sheet(report):
    s = Sheet("P3｜前公衛、可關茶水前室與乾側檢修", report)
    front_drawing(s, report)
    ledger = report["floors"][0]["area_ledger"]
    areas = ledger["areas115_sqm"]
    y = 145
    notes = [
        f"2F公衛 {areas['public-bath']:.4f}㎡、茶水前室 {areas['tea-foyer']:.4f}㎡；沿用115mm每面內縮假設。",
        f"主臥 {areas['master']:.4f}㎡、後套衛 {areas['private-bath']:.4f}㎡及景觀／室外機沿用P2；這張僅是前段局部深化。",
        "原900淋浴／450×700馬桶／600面盆／1500×600茶水台尺寸保留，只換位置與方向；門中軸避馬桶本體，並非完整風水核可。",
        "同一400×400井跨共牆；總0.1600㎡＝兩完成面各0.0340＋已扣牆帶0.0920㎡。不把兩個引用當兩井。",
        "井後留700×900乾側檢修；位置不在茶水台上方，工具與拆管、密封、聲學及操作高度仍未知。",
        "兩組雙扇門全開才有900模型淨帶；公衛門疊包距茶水台25mm，梯門全程活動與台最近約315mm，五金／公差未核。",
        "虛線為900方塊試線；與茶水操作帶重疊，需分時，不保證人體／照護或搬運。",
        f"扣實體門片前室{ledger['tea_after_worst_modeled_door_occupancy_sqm']:.4f}㎡；保守留完整移動範圍後{ledger['tea_after_reserved_full_door_travel_sqm']:.4f}㎡，不是法定面積。",
        "3F沿同一公衛／井／門，前室不放濕茶水台，但有同軸濕管；3F後客房與娛樂區、隔音／振動缺口不變。",
        "前側12.753㎡／層新室內量體沿用P2，仍須正式設計／申照；這次沒有增加量體，也未解決前排水。"
    ]
    for note in notes:
        y = s.paragraph(note, 610, y, width=42, step=23)
    s.paragraph("保留方向：可關前室＋乾側檢修更明確；先不指定門產品，不把短偏移當重力排水完成。", 55, 950, width=80)
    return s.output()


def doors_sheet(report):
    s = Sheet("P3｜兩組雙扇門，九種獨立門態", report)
    cases = report["floors"][0]["front"]["door_combinations"]
    for n, case in enumerate(cases):
        col, row = n % 3, n // 3
        x, y = 40+col*455, 145+row*300
        front_drawing(s, report, (x, y+35), .045, case["states"], labels=False)
        bath, stair = [STATES[case["states"][key]] for key in ["bath", "stair"]]
        s.text(f"公衛{bath}／梯門{stair}", x, y, class_="room")
        blocked = next(r["doors"] for r in case["route_blockers"] if r["route"] == "public-arrival")
        s.text("900試線："+("被門片阻擋" if blocked else "兩門全開可通"), x+170, y+65, class_="small")
        s.text(f"公衛淨帶 {case['clear_widths_mm']['bath']:.0f}mm", x+170, y+100, class_="small")
        s.text(f"梯門淨帶 {case['clear_widths_mm']['stair']:.0f}mm", x+170, y+130, class_="small")
        s.text("各門獨立，無假開口", x+170, y+165, class_="small")
    s.paragraph("名義洞1130，總框預算230只得到900目標。660×45雙葉、軌間40／深130是幾何候選；半開淨帶450、關閉0，不能通行。", 35, 1060, width=85, step=23)
    s.text("防火／隔煙／自閉、關門補排氣、五金操作力、濕區耐用及外救援未核；不能直接指定一般滑門施工。", 35, 1130, class_="small")
    return s.output()


def drainage_sheet(report):
    s = Sheet("P3｜排水支管＋偏移全長，不能只算短偏移", report)
    d = report["drainage"]
    s.text("以器具本體中心代排出口，折線長＋偏移；同起算高程、統一1:50敏感度，非真實管線／規定坡度。", 35, 137)
    s.text("項目", 40, 190)
    for x, text in [(250, "P2支管＋偏移"), (535, "P3支管＋偏移"), (835, "P3總坡降"), (1060, "最有利完整剖面")]:
        s.text(text, x, 190)
    y = 245
    for fid in report["config"]["branch_fixture_ids"]:
        old, new = [next(r for r in d["rows"] if r["fixture"] == fid and r["option"] == name) for name in ["P2", "P3"]]
        best = max(r["complete_path_remaining_mm"] for r in d["full_path_section_sensitivity"] if r["fixture"] == fid and r["option"] == "P3")
        s.text(FIXTURES[fid], 40, y)
        for x, text in [(250, f"{old['branch_length_mm']:.0f}＋{old['offset_length_mm']:.0f}＝{old['total_length_mm']:.0f}"),
                (535, f"{new['branch_length_mm']:.0f}＋{new['offset_length_mm']:.0f}＝{new['total_length_mm']:.0f}"),
                (835, f"{new['hypothetical_total_fall_mm']:.1f}mm"), (1060, f"{best:.1f}mm")]:
            s.text(text, x, y)
        y += 57
    y += 10
    notes = [
        "僅P3偏移2235mm降44.7mm，最有利剖面看似3555.3mm；完整WC為3498.7、面盆3471.7、茶水3486.4mm，仍低於3500比較目標。",
        "假設式：2F +4000－結構200－管含支撐150－完整坡降－檢修50；另列200／300／500結構與150／200／250管包絡共72例於JSON。",
        "真實器具排出口、存水彎與接入標高各異，部分支管可能走不同高度；本式暴露風險，不代表實際一定只差1.3mm或已證明法規不能建。",
        "1F候選井仍在原梯核，400×400占0.16㎡；不是已留空洞。騎樓直落仍拒絕，不借神明堂／乾背櫃或武轎庫落管。",
        "中心折線避已列保護投影，管徑與彎頭包絡／梁板／消防、全程通氣及清掃終端仍未設計；不能當風水或重力排水全案通過。",
        "壓力泵／粉碎馬桶有供電、故障保養代價；抬地坪影響門檻／階差與梯段。均不作預設。",
        "下一份需同版帶標高梁板、騎樓／梯段剖面、逐器具接入高程及門產品包絡；配置可先留，前排水仍是採用前必解事項。"
    ]
    for text in notes:
        y = s.paragraph(text, 35, y, width=82, step=24)
    return s.output()


def render(report):
    files = {"front-plan.svg": plan_sheet(report), "door-states.svg": doors_sheet(report), "full-drainage.svg": drainage_sheet(report)}
    files["drainage-comparison.csv"] = csv_text([{"方案": r["option"], "器具": FIXTURES[r["fixture"]],
        "假想中心支管mm": r["branch_length_mm"], "偏移mm": r["offset_length_mm"], "完整長mm": r["total_length_mm"],
        "1比50假設坡降mm": r["hypothetical_total_fall_mm"], "真實排出口高程": "未知", "施工核可": "未取得"} for r in report["drainage"]["rows"]])
    files["door-states.csv"] = csv_text([{"公衛門": STATES[r["states"]["bath"]], "梯廳門": STATES[r["states"]["stair"]],
        "公衛模型最大淨帶mm": r["clear_widths_mm"]["bath"], "梯門模型最大淨帶mm": r["clear_widths_mm"]["stair"],
        "900試線門阻擋": ",".join(next(v["doors"] for v in r["route_blockers"] if v["route"] == "public-arrival")),
        "實際產品淨寬及消防適用性": "未知"} for r in report["floors"][0]["front"]["door_combinations"]])
    files["engineering-replies.csv"] = csv_text([{"問題ID": f"BFS-{n:02d}", "待核": text,
        **dict.fromkeys(["資料與圖號版次", "專業回覆", "成本工期代價", "負責窗口", "期限", "屋主選擇", "審查或發行依據"], "")}
        for n, text in enumerate(report["config"]["open_items"], 1)])
    ledger = report["floors"][0]["area_ledger"]
    rows = [[key, f"{ledger['areas115_sqm'][key]:.4f}"] for key in ["public-bath", "tea-foyer", "master", "private-bath"]]
    body = '<h1>B棟P3：前公衛與茶水前室深化</h1><p class="note">獨立比較／未採用；P1／P2及原ABC／3D保留。前側室內量體、前排水與梯核仍未核。</p>'
    body += "<p>"+html.escape(report["conclusion"])+"</p><h2>指定115mm模型面積</h2>"+table(["區域", "扣井後㎡"], rows)
    body += '<p>同一井0.16㎡＝兩完成面各0.034＋已扣牆帶0.092。前室扣實體門片5.0838㎡，保守留完整移動範圍後5.0640㎡；通行與茶水操作需分時。這不是法定面積或實測。</p>'
    for name, title in [("front-plan.svg", "前段配置與乾側檢修"), ("door-states.svg", "兩組門九態"), ("full-drainage.svg", "完整排水與騎樓剖面敏感度")]:
        body += f'<section><h2>{title}</h2><p><a href="{name}">開啟向量圖</a></p><img style="width:100%;height:auto" src="{name}" alt="{title}"></section>'
    body += '<p><strong>完整排水仍未成立：</strong>200結構／150管含支撐／50檢修的最有利假設，WC3498.7、面盆3471.7、茶水3486.4mm，低於3500比較目標。短偏移3555.3mm不能代完整管路。</p>'
    body += "<h2>交給建築／機電與門商的問題</h2>"+ul(report["config"]["open_items"])
    body += '<p><a href="drainage-comparison.csv">完整排水CSV</a>／<a href="door-states.csv">門態CSV</a>／<a href="engineering-replies.csv">空白工程回覆表</a>／<a href="review.json">來源與幾何JSON</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>來源 '+report["report_hash"]+'。未啟動瀏覽器、WebGL或點陣轉圖；沒有法規、宗教、產品、照護、救援或施工核可。</small>'
    files["index.html"] = page("B前公衛／茶水前室P3", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-b-front-service-detail-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "adopted": False,
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
            changed = [n for n, data in files.items() if not (out/n).is_file() or (out/n).read_bytes() != data.encode()]
            if changed:
                raise ContractError("P3 static sheets stale: "+", ".join(changed))
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (out/name).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "option": "P3", "floors": len(report["floors"]),
            "independent_door_combinations_per_floor": 9, "files": len(files), "protected_controls": report["protected_controls_unchanged"],
            "complete_front_drainage": "unresolved", "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

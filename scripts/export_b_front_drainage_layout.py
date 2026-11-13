#!/usr/bin/env python3
"""Export three small static P4 front-service/complete-drainage comparison sheets."""
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

from house_design.b_front_drainage_layout import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_front_service_detail import FIXTURES, STATES, front_drawing  # noqa: E402
from scripts.export_b_upper_replan import Sheet as BaseSheet  # noqa: E402
from scripts.export_builder_communication import page, ul  # noqa: E402


class Sheet(BaseSheet):
    def __init__(self, title, report):
        self.root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": "0 0 1400 1200", "width": "1400", "height": "1200", "role": "img", "aria-label": title})
        self.add("title", text=title)
        self.add("style", text="text{font:17px system-ui,sans-serif;fill:#263e49}.title{font-size:26px;font-weight:700}.small{font-size:13px}.room{font-size:13px;font-weight:650}")
        self.add("rect", x=0, y=0, width=1400, height=1200, fill="#fafbf8")
        self.text(title, 28, 40, class_="title")
        self.text("P4僅2F前段獨立比較／未採用｜不改房界、井位與其他房間，不併原ABC／3D；排水及消防待核。", 28, 76)
        self.text("本批 "+report["report_hash"], 28, 1158, class_="small")
        self.text("指定靜態幾何／假設剖面不是法規、風水、結構、產品、照護或施工核可；未跑瀏覽器及轉圖。", 28, 1182, class_="small")


def plan_sheet(report):
    s = Sheet("P4｜保原管井、器具靠左與橫置茶水台", report)
    front_drawing(s, {"config": report["local_reference"]})
    f = report["floor"]
    y = 145
    for value in ["原900淋浴、700×450馬桶、600×450面盆及1500×600台全保尺寸；只重排2F四件座標，公衛門向左550mm。",
        "公衛5.2860、茶水5.1036㎡；保留完整門片活動後前室5.0640。主臥23.6651／後套衛6.1330㎡、兩窗方向及房界不動。",
        "單一400×400井仍x115／y1780，乾側700×900檢修原位保留；與Q3前KTV井相同投影，不移3F井或套用2F器具。",
        "900到達先繞橫台，公衛門全開後進入；五條試線另含馬桶、盆、淋浴與乾檢修。操作帶與通行分時，不當照護。",
        "公衛門活動距井35mm、疊包距台25mm；900試線離淋浴20、離茶水台40mm，成品五金與施工工差仍緊。",
        "馬桶背靠左牆，門中軸不穿本體；梁位、實際馬桶形體及全案風水未核。側牆不畫假外窗。",
        "WC／盆／茶水假排水線縮短，淋浴多710mm；最有利完整剖面僅4.4mm餘量，額外25mm就失守，未解1F梯核落水。",
        "原12.753㎡前室內量體、井內容量、合法終端及3F匯流仍未核，P1／P2／P3與兩種搬轎版完整留，不指定門產品。"]:
        y = s.paragraph(value, 610, y, width=42, step=23)
    s.text("五條試線皆按新配置重核，兩門全開才通900到達。", 55, 960)
    s.text("茶水與檢修共享路面，維修時停止泡茶；不當同時兩人無衝突。", 55, 998)
    s.text(f"公衛門中軸穿馬桶本體：{f['front']['door_axis_over_toilet_body']}；僅列明幾何，不是風水簽認。", 55, 1036, class_="small")
    return s.output()


def doors_sheet(report):
    s = Sheet("P4｜兩組門九態與五條指定通路", report)
    for n, state in enumerate(report["floor"]["front"]["door_combinations"]):
        x, y = 40+n % 3*455, 145+n//3*300
        front_drawing(s, {"config": report["local_reference"]}, (x, y+35), .045, states=state["states"], labels=False)
        s.text("公衛"+STATES[state["states"]["bath"]]+"／梯門"+STATES[state["states"]["stair"]], x, y, class_="room")
        blockers = next(r["doors"] for r in state["route_blockers"] if r["route"] == "public-arrival")
        s.text("900到達："+("門片阻擋" if blockers else "指定試線可通"), x+170, y+65, class_="small")
        s.text(f"公衛淨帶 {state['clear_widths_mm']['bath']:.0f}mm", x+170, y+100, class_="small")
        s.text(f"梯門淨帶 {state['clear_widths_mm']['stair']:.0f}mm", x+170, y+130, class_="small")
        s.text("關閉不碰井／台／檢修區", x+170, y+165, class_="small")
    s.paragraph("1130名義洞扣兩側115，只給900模型目標；660×45雙葉／軌間40預算沿P3。半開450、關閉0，不以開口框冒充可走。", 35, 1060, width=85, step=23)
    s.text("防火、隔煙、自閉、逃生、門檻、濕區耐久及關門補排氣仍待整樘產品與正式建築／消防回覆。", 35, 1130, class_="small")
    return s.output()


def drainage_sheet(report):
    s = Sheet("P4｜同井完整支管比較，最緊只多4.4mm", report)
    d = report["drainage"]
    s.text("同口徑：器具本體中心代排口，先橫後縱＋2235mm偏移；統一1:50為假設，不是實際管線或法定坡度。", 35, 137)
    for x, text in [(40, "器具"), (230, "P3完整線mm"), (465, "P4完整線mm"), (700, "增減mm"), (900, "P4假坡降"), (1110, "最有利剖面")]:
        s.text(text, x, 195)
    for n, row in enumerate(d["rows"]):
        y = 245+n*55
        result = d["assumptions"]["floor2_level_mm"]-200-150-50-row["hypothetical_total_fall_mm"]
        for x, text in [(40, FIXTURES[row["fixture"]]), (230, str(int(row["P3_total_length_mm"]))), (465, str(int(row["total_length_mm"]))),
            (700, f"{row['change_total_length_mm']:+.0f}"), (900, f"{row['hypothetical_total_fall_mm']:.1f}mm"), (1110, f"{result:.1f}mm")]:
            s.text(text, x, y)
    y = 495
    for value in ["最有利例：4000－結構200－管含支撐150－假坡降－檢修50。P3最小3471.7，P4最小3504.4mm，但不是實際只差4.4mm。",
        "同口徑四線都達3500比較值的只有結構200＋管預留150且無額外深度這一例；再需25mm便降至3479.4mm，其他梁板／管徑案例也失守。",
        "不能選薄梁、變小排水管或較平坡度湊綠色結果。實際排出口、存水彎、彎頭與接入高程可能不同，必須分段出同版剖面。",
        "1F落水候選仍占原梯核0.16㎡；無證據就是未知，不能直落騎樓或借神明堂／乾背／武轎庫。兩種搬轎入口及24級梯本體都未改。",
        "3F支管、立管同時匯流／通氣、井內容量、清掃、防火及合法終端仍未完成。維持Q3井投影不等於整棟排水、聲學或風水通過。"]:
        y = s.paragraph(value, 40, y, width=76, step=24)
    s.text("原室內量體、RF24㎡、天井防水及Q3樓梯／KTV工程缺口不因P4而解除。", 40, 1065)
    return s.output()


def render(report):
    files = {"P4-front-layout.svg": plan_sheet(report), "P4-nine-door-states.svg": doors_sheet(report), "P4-complete-drainage.svg": drainage_sheet(report)}
    files["routes.csv"] = csv_text(report["floor"]["front"]["routes"])
    files["door-states.csv"] = csv_text([{"bath": r["states"]["bath"], "stair": r["states"]["stair"],
        **{q["route"]+"_blocked_by": "/".join(q["doors"]) for q in r["route_blockers"]}, "actual_product_approval": "unknown"} for r in report["floor"]["front"]["door_combinations"]])
    files["drainage-lengths.csv"] = csv_text(report["drainage"]["rows"])
    files["section-scenarios.csv"] = csv_text([{**{k: v for k, v in r.items() if k != "fixture_results"}, **{q["fixture"]+"_remaining_mm": q["remaining_budget_mm"] for q in r["fixture_results"]}} for r in report["drainage"]["section_scenarios"]])
    files["actual-outlets.csv"] = csv_text([{"器具ID": r["fixture"], "參考方案": "P4／2F前段，非真實排口", "參考全線mm": r["total_length_mm"],
        **dict.fromkeys(["產品完整型號與排水圖", "真實排出口XYZ", "存水彎及接入標高", "管徑坡度及依據", "分段路徑及管含支撐包絡", "立管通氣清掃與終端", "梁板及騎樓同版剖面", "負責窗口與期限"], "")} for r in report["drainage"]["rows"]])
    files["engineering-replies.csv"] = csv_text([{"ID": f"P4-{i:02d}", "待核事項": text,
        **dict.fromkeys(["同版圖號及依據", "專業回覆", "費用工期及保固", "窗口", "期限", "屋主選擇", "施工圖發行"], "")} for i, text in enumerate(report["config"]["limits"], 1)])
    body = '<h1>B P4：保原井位，調整前公衛／茶水短支管</h1><p class="note">獨立2F前段比較／未採用、未併原ABC或3D。只調四件器具及公衛門；最有利算式僅4.4mm餘量，排水與1F梯核落水仍未核。</p>'
    body += "<p>"+html.escape(report["conclusion"])+"</p>"
    for name, title in [("P4-front-layout.svg", "P4配置：原房界、井及乾檢修保留"), ("P4-nine-door-states.svg", "九種門態：半開與關閉仍不能通900"), ("P4-complete-drainage.svg", "完整四線與剖面：改善及失守同列")]:
        body += f'<section><h2>{html.escape(title)}</h2><p><a href="{name}">開啟向量圖</a></p><img src="{name}" style="width:100%;height:auto" alt="{html.escape(title)}"></section>'
    body += '<h2>面積口徑與餘量</h2>'+table(["完成面內縮假設mm", "公衛㎡", "茶水㎡，未扣門活動"], [[r["inset_each_mm"], r["public-bath"], r["tea-foyer"]] for r in report["front_area_sensitivity"]])
    body += '<p>115mm模型茶水扣完整門片移動後5.064㎡；其他口徑亦須再核門組，不能用較薄完成面硬保面積。</p>'
    body += '<h2>小餘量，不是產品已可用</h2>'+table(["項目", "平面距離mm"], list(report["clearances_mm"].items()))
    body += '<h2>帶給建築／機電及門商</h2>'+ul(report["config"]["limits"])
    body += '<p>'+"／".join(f'<a href="{n}">{n}</a>' for n in files if n.endswith(".csv"))+'</p><p><a href="review.json">來源與算式JSON</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；未執行瀏覽器、WebGL或轉圖，未收到實際產品／基地／梁板資料，也沒有法規、風水、照護、消防或施工核可。</small>'
    files["index.html"] = page("B P4前公衛與短支管研究", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-b-front-drainage-layout-artifacts-v1", "report_hash": report["report_hash"], "source_hashes": report["source_hashes"],
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
                raise ContractError("P4 front drainage study stale")
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, value in files.items():
                (out/name).write_text(value, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "files": len(files), "door_states": 9,
            "routes": 5, "section_cases": len(report["drainage"]["section_scenarios"]),
            "best_case_margin_mm": round(report["drainage"]["P4_best_case_minimum_remaining_mm"]-3500, 3),
            "protected_controls": report["protected_controls_unchanged"], "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

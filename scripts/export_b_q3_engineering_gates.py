#!/usr/bin/env python3
"""Export bounded Q3/RF engineering interfaces; optional new private width recalculation."""
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

from house_design.b_q3_engineering_gates import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_roof_equipment import private_path  # noqa: E402
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
        self.text("Q3／RF同版工程接口｜未採用，原格局與主3D保留；高度及門寬僅列明預算，不是成品或施工核可。", 28, 76)
        self.text("本批 "+report["report_hash"], 28, 1158, class_="small")
        self.text("未執行瀏覽器／轉圖；結構、聲學、風水、消防、照護、外吊及全程搬運均待核。", 28, 1182, class_="small")


def vertical_sheet(report):
    s = Sheet("B Q3：RF前室／機器向下投影與高度預算", report)
    p = report["projection_interfaces"]
    d = Draw(s, (45, 160), .055)
    d.poly(p["KTV_nominal_polygon_mm"], fill="#e8dff2", stroke="#7f6b95", stroke_width=1)
    d.poly(p["RF_required_floor_polygon_mm"], fill="#b9d0b3", stroke="#4c7750", fill_opacity=.7)
    d.poly(p["RF_floor_over_KTV_polygon_mm"], fill="#e1ae87", stroke="#a66f46", fill_opacity=.9)
    front = report["condition_template"]["records"][0]["option"]
    for item in p["equipment"]:
        if item["option"] == front and item["over_KTV_nominal_sqm"]:
            d.box(item["rect_mm"], fill="none", stroke="#a66f46", stroke_width=1.5, stroke_dasharray="5 3")
    s.text("紫：3F KTV名義範圍；綠：RF候選地面", 45, 125, class_="small")
    s.text(f"橘色RF地面壓KTV名義 {p['RF_floor_over_KTV_nominal_sqm']:.4f}㎡", 45, 515, class_="small")
    s.text(f"對KTV內縮後地面 {p['RF_floor_over_KTV_inner_sqm']:.4f}㎡", 45, 541, class_="small")
    s.text("虛框：S1熱泵／前冷氣代表位置，非型號實機", 45, 567, class_="small")
    s.text("投影只指出需核腳步、荷重、隔振與穿孔的位置。", 45, 607)
    s.text("梁可能將振動傳到其他房間，不能只查正下方。", 45, 637)
    y = 145
    for value in ["RF新前室位在KTV左後入口凹部上方；到達板不壓踏步，不等於腳步或門振動已隔絕。",
        "S1前熱泵位於前KTV上方，另核基座／隔振／運轉及維修；S2後濕設備保留為備案，不因此解除後端緊餘量。",
        "概念基準為3F模型+7000、RF模型+10000；兩者暫按本圖構造帳解讀。這不是已知梁板或實際完成面。",
        "RF構造先向下占高度，再扣樓板、板底以外梁突出、最低結構下的吊頂服務帶及3F額外地坪；同一層厚不得重複扣。",
        "若RF完成面改上抬，須重算末級／門檻及整段樓梯；不能一面保原18級，一面無代價加厚。"]:
        y = s.paragraph(value, 465, y, width=46, step=23)
    for i, row in enumerate(report["vertical_cases"]):
        s.text(f"{row['id']}：剩餘高度預算 {row['remaining_vertical_budget_mm']:.0f}mm；非淨高通過", 45, 710+i*36)
    h = report["vertical_cases"][0]
    def z(value):
        return 1085-(value-7000)*.12
    x, width = 645, 400
    layers = [(10000, h["slab_top_z_mm"], "RF防水／找坡等向下預算", "#bfd9dd"),
        (h["slab_top_z_mm"], h["slab_bottom_z_mm"], "候選樓板", "#a7b7ae"),
        (h["lowest_structure_z_mm"], h["KTV_ceiling_z_mm"], "吊頂／聲學／管線服務帶", "#dbd1e5")]
    for top, bottom, label, colour in layers:
        s.add("rect", x=x, y=z(top), width=width, height=(top-bottom)*.12, fill=colour, stroke="#64766b")
        s.text(label, x+width+12, z(bottom)+12, class_="small")
    for value, label in [(10000, "RF模型基準"), (h["KTV_ceiling_z_mm"], "H0假設天花"), (h["KTV_floor_z_mm"], "H0假設KTV地坪")]:
        s.add("line", x1=x-20, y1=z(value), x2=x+width+10, y2=z(value), stroke="#64766b", stroke_dasharray="4 3")
        s.text(label, x-180, z(value)+5, class_="small")
    s.text("H0僅示層厚，非真實梁／防水／聲學剖面", 650, 1120, class_="small")
    return s.output()


def replacement_sheet(report):
    s = Sheet("B RF設備：首裝、巡檢與整機汰換分開核", report)
    s.text("前門900／側門770mm皆是預算；700巡檢方塊不代表機器可搬。", 45, 130)
    s.text("以下純試數值：每側持握／保護預留25mm，未指定任何產品。", 45, 165)
    for n, (name, label) in enumerate([("front", "前門"), ("side", "側門")]):
        x, w = 65+n*650, report[name+"_door_clear_budget_mm"]
        s.add("rect", x=x, y=215, width=w*.5, height=35, fill="#b9d0b3", stroke="#4c7750")
        s.text(f"{label}洞口預算 {w}mm → 每側25時物件寬上界 {w-50}mm", x, 285)
        for i, r in enumerate(v for v in report["door_width_trials"] if v["door"] == name and v["handling_each_side_mm"] == 25):
            y = 340+i*55
            s.add("rect", x=x, y=y-22, width=r["required_width_mm"]*.5, height=25, fill="#e7b7a6" if r["margin_mm"] < 0 else "#d9dfbf")
            s.text(f"物件{r['declared_transport_width_mm']}＋兩側50＝{r['required_width_mm']}；餘{r['margin_mm']}mm", x, y+28, class_="small")
    y = 685
    for value in ["水塔／熱泵框是整組預留，不是機身尺寸；冷氣代表槽也不當已選台數。先取實機或原廠可拆運模組的寬、深、高、重與依據。",
        "S1前熱泵巡檢經前門；水塔、後冷氣及S2熱泵巡檢經側門。這只是選擇本表洞口參考，不是證明機器能循人員巡檢折線搬出。",
        "寬度相容仍要核門高、把手、包裝、長物轉彎、1100折返平台、扶手、踏步、荷重及搬運人員；本輪沒有整機實物演練。",
        "若全門梯路線不能換機，才比較原廠可拆模組或外吊。外吊需合法到達、吊點、落放、護欄／防水恢復及費用；目前不當已存在備援。",
        "日後條件只回算新的私人結果，未知保null。不得自動縮機器、旋轉、拆機、借保護區、增加採購數或覆寫已填回覆。"]:
        y = s.paragraph(value, 45, y, width=74, step=24)
    return s.output()


def capacity_sheet(report):
    s = Sheet("B RF24㎡：保原目標，先辨認必須重排的邊界", report)
    c = report["capacity_boundary"]
    d = Draw(s, (50, 175), .075)
    d.box([0, 0, 6000, 5400], fill="#eef0e7", stroke="#607c73")
    d.box([115, 115, 5770, 3785], fill="#d9dfbf", stroke="#74803e")
    d.box([0, 3900, 2400, 1500], fill="#cbd6db", stroke="#66758b")
    d.box([2400, 3900, 3600, 1500], fill="#efd6ce", stroke="#b88b7a")
    d.box(c["hypothetical_extra_band_mm"], fill="none", stroke="#b95142", stroke_width=3, stroke_dasharray="5 3")
    s.text("前方／道路", 220, 140)
    s.text("名義6000×3900＝23.4㎡", 70, 295)
    s.text("扣外緣樂觀上界21.83945㎡", 70, 330)
    s.text("梯核", 100, 515)
    s.text("現行祭祀保護投影", 265, 515)
    s.text("紅虛線只是假算新增帶，不是可採用格局", 50, 630, class_="small")
    y = 145
    for value in [f"在5770mm寬、後邊尚不扣牆也不扣設備的樂觀口徑，24㎡需前帶深度至少{c['hypothetical_full_width_depth_lower_bound_mm']:.3f}mm；向後整毫米加帶{c['hypothetical_rounded_extra_depth_mm']}mm。",
        f"但這條假帶會占原梯核{c['extra_band_over_stair_enclosure_sqm']:.4f}㎡及保護投影{c['extra_band_over_protected_sqm']:.4f}㎡；未受阻部分{c['extra_band_not_already_blocked_sqm']:.4f}㎡。不能直接採用。",
        "因此固定前帶只移機／改門無法保24㎡；這是當前樓梯與祭祀位置的限制，不是所有整棟重排都無解，也不代表建築可外挑或增層。",
        "S1保較可核維修的設備，D1折衣分時；S2保較大前帶，後設備零／65mm仍緊。兩者都保原24㎡及未接受縮平台狀態。",
        "請建商先確認完整可建量及同版Q3結構，若24㎡不能取捨再提出全棟重排與代價。室內前室、三樓天井或後區必要巡檢不拿來補日常面積。"]:
        y = s.paragraph(value, 565, y, width=43, step=24)
    s.text("這輪工程回覆順序", 50, 730, class_="title")
    y = 780
    for n, value in enumerate(report["recommended_sequence"], 1):
        y = s.paragraph(str(n)+". "+value, 50, y, width=76, step=24)
    return s.output()


def render(report):
    files = {"vertical-interfaces.svg": vertical_sheet(report), "replacement-access.svg": replacement_sheet(report), "capacity-boundary.svg": capacity_sheet(report)}
    files["vertical-budgets.csv"] = csv_text(report["vertical_cases"])
    files["door-width-trials.csv"] = csv_text(report["door_width_trials"])
    files["replacement-conditions.csv"] = csv_text(report["condition_evaluations"])
    files["equipment-projections.csv"] = csv_text([{**{k: v for k, v in r.items() if k not in {"below_rooms", "rect_mm"}}, "below_rooms": ";".join(v["id"]+":"+str(v["sqm"]) for v in r["below_rooms"])} for r in report["projection_interfaces"]["equipment"]])
    files["engineering-replies.csv"] = csv_text([{"ID": r["id"], "議題": r["topic"], "建議窗口": r["roles"], "需回覆": r["reply"],
        **dict.fromkeys(["同版圖號或產品資料", "專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"], "")} for r in report["engineering_gates"]])
    files["actual-data-template.json"] = json.dumps(report["condition_template"], ensure_ascii=False, indent=2)+"\n"
    body = '<h1>B Q3／RF：剖面、整機汰換與工程先決條件</h1><p class="note">獨立同版工程研究／未採用。原格局與主3D不改，門寬數值相容不是搬運通過；高度預算不是法定或實測淨高。</p>'
    body += '<p>這輪把新前室與機器向下投影、KTV高度預算、首裝／巡檢／汰換及RF24㎡邊界放在同一版，供建商統籌建築、結構、機電與聲學。</p>'
    for name, label in [("vertical-interfaces.svg", "垂直投影與四種高度預算"), ("replacement-access.svg", "前900／側770：整機換出還差哪些條件"), ("capacity-boundary.svg", "24㎡必要邊界及工程回覆順序")]:
        body += f'<section><h2>{html.escape(label)}</h2><p><a href="{name}">開啟向量圖</a></p><img src="{name}" style="width:100%;height:auto" alt="{html.escape(label)}"></section>'
    body += '<h2>層厚算式沒有選材或淨高通過</h2>'+table(["例", "RF構造", "樓板", "梁增量", "吊頂服務帶", "3F增高地坪", "剩餘預算mm"], [[r["id"], r["roof_build_below_RF_plane_mm"], r["slab_mm"], r["beam_extra_below_slab_mm"], r["ceiling_and_services_below_lowest_structure_mm"], r["KTV_floor_raise_above_3F_plane_mm"], r["remaining_vertical_budget_mm"]] for r in report["vertical_cases"]])
    body += '<h2>日後產品條件回套</h2><p>下載actual-data-template.json，另存私人條件檔；八列分兩案四種有身分／用途的設備，全部未知保null。寬與兩側持握預算有資料才比洞口，深、高、重及產品／運輸依據保留供整段人工核對；不自動旋轉或拆機。</p>'
    body += table(["方案／設備", "巡檢門參考", "洞口預算mm", "本輪條件狀態", "完整搬運核可"], [[r["id"], r["inspection_door_reference_not_a_transport_route"], r["door_budget_mm"], r["status"], "未知"] for r in report["condition_evaluations"]])
    body += '<h2>九項工程回覆</h2>'+table(["ID", "議題", "窗口", "回覆內容"], [[r["id"], r["topic"], r["roles"], r["reply"]] for r in report["engineering_gates"]])
    body += '<h2>條件及限制</h2>'+ul(report["config"]["limits"])
    body += '<p>'+"／".join(f'<a href="{n}">{n}</a>' for n in files if n.endswith((".csv", ".json")))+'</p><p><a href="review.json">來源與算式JSON</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；未跑瀏覽器／WebGL，未取得結構、消防、聲學、風水、吊運或施工核可。</small>'
    files["index.html"] = page("B Q3／RF工程先決條件", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-b-q3-engineering-gates-artifacts-v1", "report_hash": report["report_hash"], "source_hashes": report["source_hashes"],
        "adopted": False, "artifacts": {n: hashlib.sha256(v.encode()).hexdigest() for n, v in files.items()}}, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--conditions")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        if bool(args.conditions) != bool(args.output) or args.check and args.conditions:
            raise ContractError("Use conditions with a new private output; --check is for the public baseline")
        document = None
        if args.conditions:
            source = private_path(ROOT, args.conditions)
            if source.stat().st_size > 1_000_000:
                raise ContractError("Q3 engineering condition input exceeds 1MB")
            document = json.loads(source.read_text(encoding="utf-8"))
        out = private_path(ROOT, args.output, new=True) if args.output else ROOT/OUT
        report = build(ROOT, document)
        files = render(report)
        if args.check:
            if any(not (out/n).is_file() or (out/n).read_bytes() != value.encode() for n, value in files.items()):
                raise ContractError("Q3 engineering interfaces stale")
        else:
            out.mkdir(parents=True, exist_ok=not bool(args.conditions))
            for name, value in files.items():
                (out/name).write_text(value, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "private-recalculation" if args.conditions else "exported", "files": len(files),
            "height_cases": len(report["vertical_cases"]), "door_width_trials": len(report["door_width_trials"]), "engineering_gates": len(report["engineering_gates"]),
            "numeric_condition_values_received": report["numeric_condition_values_received"], "protected_controls": report["protected_controls_unchanged"], "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

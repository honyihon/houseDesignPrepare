#!/usr/bin/env python3
"""Export independent static Q3 L-shaped KTV, upper stair and space sensitivity."""
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

from house_design.b_front_service_detail import leaves  # noqa: E402
from house_design.b_ktv_stair_options import OUT, build, front_leaf, side_leaf  # noqa: E402
from house_design.b_upper_replan import door as retained_leaf  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
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
        self.text("獨立Q3比較／未採用｜改上層梯及RF到達有結構代價；一樓功能及原Q2保留，不代表隔音或樓梯核可。", 28, 76)
        self.text("本批 "+report["report_hash"], 28, 1158, class_="small")
        self.text("指定幾何、局部踏步與面積算式不是法規、風水、結構、消防、產品或聲學簽證。未跑瀏覽器／WebGL。", 28, 1182, class_="small")


def plan_sheet(report):
    from shapely.geometry import Polygon
    s = Sheet("Q3｜L形KTV保20㎡的條件與完整三樓比較", report)
    d = Draw(s, (45, 145), .052)
    labels = {"front-entertainment": "L形KTV候選", "stair": "新上層梯候選", "quiet-living": "安靜保護／通行", "dry-protection": "乾背保護室", "guest": "原後客房", "rear-bath": "原後公衛", "working-court": "原工作天井", "rear-access": "原公共到達"}
    for room in report["primary"]["rooms"]:
        colour = "#e8dff2" if room["kind"] == "high-activity" else "#dceff4" if room["kind"] == "wet" else "#f1e7cd" if room["kind"] == "bedroom" else "#edf0e9"
        d.poly(room["polygon_mm"], fill=colour, stroke="#607c73", stroke_width=.7)
        center = Polygon(room["polygon_mm"]).representative_point()
        s.text(labels[room["id"]], *d.point([center.x, center.y]), text_anchor="middle", class_="room")
        for item in room["items"]:
            d.box(item["rect_mm"], fill="#b9c9be", stroke="#3c6355", stroke_width=.6)
        for shaft in room["shafts_mm"]:
            d.box(shaft, fill="#ca9d8b", stroke="#9c4634")
        for w in room["windows_mm"]:
            d.line(w[:2], [w[0]+w[2], w[1]], stroke="#168cae", stroke_width=3)
        for spec in room["doors"] if room["id"] != "front-entertainment" else []:
            d.line(spec["a"], spec["b"], stroke="#fafbf8", stroke_width=3)
            d.poly(list(retained_leaf(spec, 90).exterior.coords), fill="#bb9474", stroke="#805534", stroke_width=.6)
    for spec in report["retained_guest_bath_sliders"]:
        d.line(spec["a"], spec["b"], stroke="#fafbf8", stroke_width=3)
        for panel in leaves(spec, "open"):
            d.box(panel, fill="#bb9474", stroke="#805534", stroke_width=.6)
    connection = report["retained_quiet_rear_opening"]
    d.line(connection["a"], connection["b"], stroke="#fafbf8", stroke_width=3)
    d.poly(report["primary"]["KTV_inner_polygon_mm"], fill="none", stroke="#7f55a0", stroke_dasharray="4 3")
    p = report["upper_stairs"]["primary"]["footprint"]
    d.box([p["x_mm"], p["y_mm"], p["w_mm"], p["h_mm"]], fill="none", stroke="#617981", stroke_dasharray="5 3")
    for spec in [report["config"]["front_door"], report["config"]["side_door"]]:
        d.line(spec["a"], spec["b"], stroke="#fafbf8", stroke_width=3)
    d.poly(list(front_leaf(report["config"]["front_door"], 90).exterior.coords), fill="#bb9474", stroke="#805534", stroke_width=.7)
    d.poly(list(side_leaf(report["config"]["side_door"], 90).exterior.coords), fill="#bb9474", stroke="#805534", stroke_width=.7)
    for route in report["primary"]["routes"]:
        for a, b in zip(route["points_mm"], route["points_mm"][1:], strict=False):
            d.line(a, b, stroke="#277c79", stroke_width=1.5, stroke_dasharray="4 3")
    s.text("道路／1F騎樓在前下方，1F配置不改", 45, 125, class_="small")
    s.text("同6×17.63m研究框；不增加Q2整層量體", 45, 1090, class_="small")
    y = 145
    for value in ["KTV左後800×2400mm從原梯核重分名義1.92㎡，右側不伸進完整祭祀保護區；整層量體不增加，但Q2原10.647㎡前新增量體仍待核。",
        "115＋額外100mm／面、原400井再包50mm、另扣600×900機櫃後20.1889㎡。這只有0.1889㎡餘量，沒有dB、完整聲閘或消音選型。",
        "客房12.423、公衛6.133、天井4.123㎡原輪廓不改；主臥與2F兩衛、1F祭祀／搬轎及一樓梯也保原幾何。",
        "2F→3F及3F→RF兩梯折返平台1900→1100mm；18級／1000寬／270踏面及來源3000層高不變，後端y9030不動。",
        "1330名義KTV門扣兩側215預算900；原梯核側門改中心y5270，避免落在新KTV邊界形成聲學旁通，兩門九態列明。",
        "新增主要是入口凹部與通路，不等於座位增加或無柱20㎡大矩形。900到達只到空地，沙發仍700試線；機櫃操作共用路線。",
        "RF到達後移800mm，既有D1／D2屋頂門路結果不繼承，原24㎡缺口不因KTV改善解除。",
        "2F新平台不可整塊鋪滿；需保原前平台＋左接段與右下樓梯洞，詳下一張。梁、板洞、扶手、全程淨高及消防未核。"]:
        y = s.paragraph(value, 445, y, width=48, step=23)
    return s.output()


def stairs_sheet(report):
    s = Sheet("Q3樓梯代價｜二樓L形接段，不能蓋住原下樓梯", report)
    p = report["upper_stairs"]["primary"]
    for x, title, full in [(40, "排除：直接鋪新矩形平台", True), (520, "Q3候選：保原前平台＋左接段", False)]:
        s.text(title, x, 140, class_="room")
        d = Draw(s, (x, -255), .13)
        d.box([0, 3900, 2400, 5200], fill="#edf0e9", stroke="#607c73")
        d.box([p["footprint"]["x_mm"], p["footprint"]["y_mm"], p["footprint"]["w_mm"], p["footprint"]["h_mm"]], fill="none", stroke="#537d73", stroke_dasharray="5 3")
        for step in range(11):
            d.box([1280, 4970+step*270, 1000, 270], fill="#e5c5b7", stroke="#b88b7a", stroke_width=.5)
        if full:
            d.box(p["floor_landing_mm"], fill="#bc7f74", fill_opacity=.8, stroke="#9e4939")
        else:
            d.poly(report["floor2_arrival_screen"]["floor2_landing_polygon_mm"], fill="#b9d0b3", stroke="#4c7750", stroke_width=1.8)
            for a, b in zip(report["config"]["second_floor_transfer_route_mm"], report["config"]["second_floor_transfer_route_mm"][1:], strict=False):
                d.line(a, b, stroke="#277c79", stroke_width=2, stroke_dasharray="5 3")
        s.text("原1F右跑下樓梯洞", *d.point([1290, 7000]), class_="small")
    y = 145
    for value in ["左圖錯誤鋪板壓原右跑末段三踏；200mm板厚示意下局部餘量300／133／−33mm，因此排除。",
        "右圖保原2200×1000前平台，加左側1000×1000接段。900方塊先橫過原平台，再沿左側接到新出發位。",
        "右側下樓梯洞保留，不拿房間矩形把梯洞填平；本輪沒有動一樓梯。",
        "左接段下方少數左跑踏步局部最小3300mm只來自來源步高及200mm板厚假設，不是整座梯淨高驗收。",
        "2F／3F上層折返平台1100mm仍只比1000模型下限多100mm，扶手、梁板與防火未知。",
        "3F與RF到達後移800mm；屋頂前室／門路要另回套，不能沿用舊passed。"]:
        y = s.paragraph(value, 1000, y, width=21, step=22)
    y = 1020
    for value in ["上下層高仍用來源4m／3m／3m，原一樓24級、上層18級；未新增第五層，也未用陡梯或縮踏面換KTV。",
        "樓板形狀與門檻均是新結構設計候選。上層梁板改動可能影響下層，不保證一樓施工完全不受影響。"]:
        y = s.paragraph(value, 40, y, width=82, step=23)
    return s.output()


def sensitivity_sheet(report):
    s = Sheet("Q3面積敏感度｜20㎡取決於真實聲學包絡", report)
    s.text("下表都保原400井、另加50mm／面包覆及0.54㎡機櫃；額外內縮不是聲學材料規格或dB。", 35, 135)
    columns = [(40, "KTV延伸mm"), (300, "折返平台mm"), (570, "加100／面後㎡"), (890, "加150／面後㎡")]
    for x, label in columns:
        s.text(label, x, 200)
    y = 250
    for extension in report["config"]["extension_depth_cases_mm"]:
        rows = {r["extra_acoustic_each_face_mm"]: r for r in report["capacity_cases"] if r["extension_mm"] == extension and r["extra_floor_service_sqm"] == .54}
        for x, value in [(40, str(extension)), (300, str(rows[100]["middle_landing_mm"])), (570, f"{rows[100]['remaining_sqm']:.4f}"), (890, f"{rows[150]['remaining_sqm']:.4f}")]:
            s.text(value, x, y)
        y += 55
    y += 40
    for value in ["Q3主比較取800mm：折返平台1100、加100／面後20.1889㎡，保全部原5項3F目標列帳但不當功能／合法已通過。",
        "同Q3若加150／面只19.2399㎡；900mm延伸也只有19.4269㎡且平台到1000模型下限，未把它當穩健替代案。",
        "若額外100mm但實際需1㎡地面服務空間，800mm延伸只19.7289㎡。雙門聲閘、機櫃或其他器材若吃面積，必須重新扣帳。",
        "只算面積能放20，不代表唱歌、低頻、樓板振動、鄰戶或關門新風成立；聲學、結構與機電需用同版真實包絡回套。",
        "前門1330扣兩側215只給900預算，不是產品淨開口。門組重量、把手、防火／隔煙與實際聲學門資料仍未知。",
        "若改梯、聲學或申照不成立，就保Q2原梯與20㎡原目標，不自動接受14㎡、取消客房／外窗或侵入祭祀上方。"]:
        y = s.paragraph(value, 35, y, width=80, step=23)
    return s.output()


def render(report):
    files = {"Q3-whole-floor.svg": plan_sheet(report), "upper-stair-arrival.svg": stairs_sheet(report), "acoustic-stair-sensitivity.svg": sensitivity_sheet(report)}
    files["capacity-cases.csv"] = csv_text([{"延伸mm": c["extension_mm"], "折返平台mm": c["middle_landing_mm"], "每面額外聲學mm": c["extra_acoustic_each_face_mm"],
        "井外包各面mm": c["shaft_wrap_each_mm"], "另扣地面服務㎡": c["extra_floor_service_sqm"], "剩餘㎡": c["remaining_sqm"], "面積達20": c["goal20_met_in_area_model"], "聲學／樓梯核可": "未知"} for c in report["capacity_cases"]])
    files["door-route-matrix.csv"] = csv_text([{"KTV門": d["front"], "梯核側門": d["side"], **{key+"阻門": ",".join(value) for key, value in d["route_blockers"].items()}, "門片碰撞": d["door_pair_hit"], "實際產品及消防": "未知"} for d in report["primary"]["door_states"]])
    files["program-ledger.csv"] = csv_text([{"原ID": r["id"], "原狀態": r["original_status"], "原目標㎡": r["target_sqm"], "Q3模型㎡": r["modeled_value_sqm"], "功能及合法核可": "未知", "已採用": "否"} for r in report["original_3F_requirement_ledger"]])
    files["engineering-replies.csv"] = csv_text([{"問題ID": f"BKS-{n:02d}", "待核": value, **dict.fromkeys(["同版資料圖號", "專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"], "")} for n, value in enumerate(report["config"]["limits"], 1)])
    body = '<h1>B三樓Q3：L形KTV與上層樓梯重分</h1><p class="note">獨立比較／未採用。原Q2及其樓梯、RF R／S／D、一樓祭祀及搬轎兩版保留；不改原ABC／3D或正式需求。</p>'
    body += '<p>'+html.escape(report["conclusion"])+"</p><p>在115＋額外100mm／面、原400井另包50mm及0.54㎡機櫃預留後，Q3為20.1889㎡；同口徑Q2僅18.6129㎡。Q3只多0.1889㎡餘量，完整聲學／新風與結構尚未成立。</p>"
    body += '<p>從既有梯核重分名義1.92㎡，Q2整層量體不增加；原前帶新增10.647㎡的合法量體條件仍保留。二樓、三樓18級出發梯改折返平台1900→1100mm，RF到達後移800mm，屋頂門路須另回套。</p>'
    for name, title in [("Q3-whole-floor.svg", "完整三樓與兩門九態"), ("upper-stair-arrival.svg", "二樓L形接段與不能鋪滿的下樓梯洞"), ("acoustic-stair-sensitivity.svg", "什麼厚度／服務面積又會失敗")]:
        body += f'<section><h2>{title}</h2><p><a href="{name}">開啟向量圖</a></p><img style="width:100%;height:auto" src="{name}" alt="{title}"></section>'
    body += '<h2>原三樓需求不取消</h2>'+table(["原需求", "原目標㎡", "本輪模型㎡", "功能／法規"], [[r["id"], str(r["target_sqm"]), f"{r['modeled_value_sqm']:.4f}", "未知"] for r in report["original_3F_requirement_ledger"]])
    body += '<h2>樓梯與聲學是同一個取捨</h2>'+ul(report["config"]["limits"])
    body += '<p>'+"／".join(f'<a href="{n}">{n}</a>' for n in files if n.endswith(".csv"))+'</p><p><a href="review.json">來源與計算JSON</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；無瀏覽器／WebGL驗收，無專業或風水核可，不沿用舊屋頂passed。</small>'
    files["index.html"] = page("B Q3 KTV與上層樓梯比較", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-b-ktv-stair-options-artifacts-v1", "report_hash": report["report_hash"], "source_hashes": report["source_hashes"],
        "adopted": False, "artifacts": {n: hashlib.sha256(value.encode()).hexdigest() for n, value in files.items()}}, ensure_ascii=False, indent=2)+"\n"
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
                raise ContractError("Q3 KTV/stair comparison stale")
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, value in files.items():
                (out/name).write_text(value, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "files": len(files), "door_states": 9,
            "primary_KTV_sqm": report["primary"]["KTV_area_after_wrap_and_cabinet_sqm"], "protected_controls": report["protected_controls_unchanged"], "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

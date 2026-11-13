#!/usr/bin/env python3
"""Export bounded B working-court/RF interface comparisons without rendering scenes."""
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

from house_design.b_upper_replan import rect  # noqa: E402
from house_design.b_working_court import OUT, build  # noqa: E402
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
        self.text("獨立介面比較／未採用｜原ABC／3D、B兩個搬轎入口、Q1／Q2及RF快照保留。不是工程或風水核可。", 28, 76)
        self.text("本批 "+report["report_hash"], 28, 1158, class_="small")
        self.text("僅指定平面與算式；合法戶外、結構、防水、通風乾衣、護欄及實物拆運未知。未跑瀏覽器／WebGL。", 28, 1182, class_="small")


def court_comparison(report):
    s = Sheet("B工作天井｜地面不動、RF開洞與留板帶分開比較", report)
    for index, option in enumerate(report["options"]):
        ox = 40+index*455
        s.text(option["title"], ox, 135, class_="room")
        d = Draw(s, (ox, -515.5), .065)
        d.box([0, 10700, 3600, 4500], fill="#edf0e9", stroke="#607c73")
        for r in report["floor3_reference"]["rooms"]:
            from shapely.geometry import Polygon
            cropped = Polygon(r["polygon_mm"]).intersection(rect([0, 10700, 3600, 4500]))
            if not cropped.is_empty and cropped.geom_type == "Polygon":
                d.poly(list(cropped.exterior.coords), fill="#e1ebd8" if r["id"] == "guest" else "#edf0e9", stroke="#8c9b90", stroke_width=.6)
        d.box(option["court_floor_mm"], fill="#dceff4" if index != 2 else "#efdfbe", stroke="#397b8e", stroke_width=1.8)
        if option["rf_retained_strip_mm"]:
            d.box(option["rf_retained_strip_mm"], fill="#b8c9b5", fill_opacity=.8, stroke="#537b51", stroke_width=1.5)
            d.box(option["rf_front_collar_mm"], fill="#b8c9b5", stroke="#537b51")
        if option["rf_opening_mm"]:
            d.box(option["rf_opening_mm"], fill="none", stroke="#217eac", stroke_width=2.5, stroke_dasharray="7 4")
        for points in option["rf_guard_polygons_mm"]:
            d.poly(points, fill="#bd8f56", fill_opacity=.7)
        d.line([1150, 11370], [2280, 11370], stroke="#e28b2e", stroke_width=4)
        d.line([550, 10700], [550, 15000], stroke="#aa5147" if option["old_left_corridor_interrupted_by_void_or_guard"] else "#277c79", stroke_width=2, stroke_dasharray="4 3")
        s.text("橘：同一三樓公共外門／入口", ox, 500, class_="small")
        s.text("虛線：RF開洞；綠：RF留板帶", ox, 525, class_="small")
        s.text(f"RF洞 {option['rf_opening_sqm']:.3f}㎡", ox, 565)
        s.text(f"三樓戶外地面候選 {option['working_court_outdoor_outline115_candidate_sqm']:.3f}㎡", ox, 598)
        s.text(f"新濕地面壓2F乾區 {option['wet_3F_over_2F_master_sqm']:.3f}㎡", ox, 631)
        text = (["原RF完整洞截斷左路，保右側繞行。三樓地面115輪廓4.123㎡，戶外與晾衣資格未核。",
                 "原井前護欄占位伸入保護投影0.25㎡，介面尚未核可；保留原比較，不沿用避讓通過。"],
                ["RF左保1100，扣左緣115＋井側護欄100剩885mm；700方塊餘185mm，非實際淨寬。",
                 "井前另退100，RF洞1300×2030，少2.473㎡；三樓濕地面仍5.112㎡，不當減少漏水比例。",
                 "較值得深化RF介面；採光、乾衣、結構與工作陽台資格仍待核。"],
                ["三樓改乾式折衣／收納，無洗衣機、水槽或地排。完整覆頂，室內通風採光仍未核。",
                 "三樓戶外工作目標仍缺4㎡；RF曬衣另有24㎡原需求且未排位，不能互抵。"])[index]
        yy = 680
        for value in text:
            yy = s.paragraph(value, ox, yy, width=22, step=23)
    s.text("RF板帶在上層，不能加算三樓使用面積；圖只疊介面，未把兩個高度拼成同層平面。", 40, 1085)
    return s.output()


def roof_sheet(report):
    o = report["options"][1]
    s = Sheet("R1｜RF左板帶直達後機位：完整屋頂需求仍待排", report)
    d = Draw(s, (45, 145), .052)
    d.box([0, 0, 6000, 17630], fill="#eef0e7", stroke="#607c73")
    for poly in report["protected_polygons_mm"]:
        d.poly(poly, fill="#f1ded6", stroke="#b88b7a", fill_opacity=.7)
    d.box([0, 3900, 2400, 5200], fill="#d2d9e0", stroke="#66758b")
    d.box(o["rf_retained_strip_mm"], fill="#b8c9b5", stroke="#537b51", stroke_width=1.5)
    d.box(o["rf_front_collar_mm"], fill="#b8c9b5", stroke="#537b51")
    d.box(o["rf_opening_mm"], fill="#c8dce4", stroke="#217eac", stroke_width=1.5)
    for poly in o["rf_guard_polygons_mm"]:
        d.poly(poly, fill="#bd8f56")
    for u in report["existing_units"]:
        d.box(u["rect_mm"], fill="#b2c6b7", stroke="#486650")
    for u in report["representative_slots"]:
        d.box(u["service_mm"], fill="none", stroke="#b78447", stroke_dasharray="4 3")
        d.box(u["rect_mm"], fill="#c2ccd6", stroke="#536b80")
    for route in o["rf_routes"]:
        for a, b in zip(route["points_mm"], route["points_mm"][1:], strict=False):
            d.line(a, b, stroke="#277c79", stroke_width=1.8, stroke_dasharray="4 3")
    s.text("前兩代表槽：身分／新購數未定", 45, 130, class_="small")
    s.text("後兩原B-AC03／04保留", 45, 1090, class_="small")
    y = 145
    for text in ["RF左留1100mm板帶，三樓只是部分遮頂；沒有新柱腳、梁深或結構可行的既成證據。",
        "井前護欄後退100到天井上方，避開原R0占祭祀投影0.25㎡的待核介面。700方塊從RF側門外沿左板帶到後機位。",
        "粉紅區為完整祭祀／乾背保護投影；只容必要巡檢通行，不在這裡放機器或作日常曬衣。",
        "既有兩台及兩個前代表槽只作列明平面避讓。原機的維修包絡、全熱、機型及整機拆運仍需同版正式資料。",
        "其餘水塔／泵浦3㎡、熱泵2.5㎡、活動曬衣24㎡、梯間6㎡及保護29.5㎡原目標全部保留，未畫入不當取消或屋頂已足。",
        "只看RF前23.4㎡，扣兩個代表維修槽就剩20.97㎡；未扣其他設備或走道仍比24㎡平台少3.03㎡。",
        "不能因此搬回舊水塔文字座標，亦不拿不同樓層曬衣互抵。屋頂全部設備尚未完成排位，荷重／防颱／振動未核。",
        "R1能改善開洞及通行介面，不能解除三樓天井壓2F更衣乾區的防水風險、KTV20缺口或P3前排水問題。"]:
        y = s.paragraph(text, 445, y, width=48, step=24)
    return s.output()


def section_sheet(report):
    s = Sheet("R1上下關係｜部分遮頂仍須完整天井防水", report)
    s.text("橫向沿天井中段看x=0～2400；高度僅關係示意，未假定正式樓高、梁深或排水標高。", 40, 130)
    left, top, scale = 90, 250, .39
    s.add("rect", x=left, y=top, width=1100*scale, height=22, fill="#a7b9a5", stroke="#537b51")
    s.text("RF留板帶1100mm（支承／梁深未核）", left, top-60)
    s.add("line", x1=left+1100*scale, y1=top, x2=left+2400*scale, y2=top, stroke="#217eac", stroke_width=3, stroke_dasharray="8 6")
    s.text("上方開口1300mm", left+1200*scale, top-28)
    s.add("rect", x=left+1000*scale, y=top-65, width=100*scale, height=65, fill="#bd8f56")
    s.text("井側100mm僅占位", 1080, 230)
    s.add("line", x1=left, y1=top+22, x2=left, y2=580, stroke="#607c73", stroke_width=4)
    s.add("line", x1=left+2400*scale, y1=top+22, x2=left+2400*scale, y2=580, stroke="#607c73", stroke_width=4)
    s.add("rect", x=left, y=580, width=2400*scale, height=18, fill="#b7cedb", stroke="#397b8e")
    s.text("3F完整天井地面2400mm；全地面防水／溢流／門檻仍要核", left, 560)
    s.text("2F更衣／梳妝乾區在下方，並未移走", left+120, 680)
    for x in [left+1350*scale, left+1700*scale, left+2100*scale]:
        s.add("line", x1=x, y1=290, x2=x-40, y2=475, stroke="#217eac", stroke_width=2, stroke_dasharray="6 5")
    s.text("風雨可能濺入遮頂區；板洞變小不等於濕地面減半", 110, 760)
    y = 825
    for text in ["留板帶只減RF名義板洞，不提供隔熱、防水、採光或乾衣性能。天井地面名義5.112㎡，115輪廓4.123㎡；井前另退100後，上方洞2.639㎡不是有效通風口認證。",
        "圖未補入洗衣機、晾衣架、排水口或維修管；需完整排好才能稱可用工作陽台。雨水、污廢水及通氣分系統，既有400井不證明容量足。",
        "若結構需三樓柱腳、墩座或新梁侵入，原地面、門片與81態結果須重算。R2室內乾區也不能偷加濕洗衣後沿用此結果。"]:
        y = s.paragraph(text, 40, y, width=82, step=23)
    return s.output()


def render(report):
    files = {"court-comparison.svg": court_comparison(report), "R1-roof-service.svg": roof_sheet(report), "R1-section.svg": section_sheet(report)}
    files["options.csv"] = csv_text([{"方案": o["id"], "RF名義板洞㎡": o["rf_opening_sqm"], "RF少開洞㎡": o["rf_opening_reduction_sqm"],
        "三樓戶外候選輪廓㎡": o["working_court_outdoor_outline115_candidate_sqm"], "三樓室內乾區輪廓㎡": o["indoor_dry_utility_outline115_sqm"],
        "新濕地面壓2F乾區㎡": o["wet_3F_over_2F_master_sqm"], "舊左路遭板洞擋住": o["old_left_corridor_interrupted_by_void_or_guard"],
        "合法戶外核可": o["outdoor_work_balcony_legal_or_environmental_approval"], "已採用": "否"} for o in report["options"]])
    files["RF-requirements.csv"] = csv_text([{"原需求ID": r["id"], "原需求": r["title"], "原狀態": r["original_status"], "目標㎡": r["target_sqm"], "下限㎡": r["min_sqm"],
        "完整有效面積㎡": "", "完整排位及核可": "否", "備註": "保留目標，舊文字座標不回填祭祀投影"} for r in report["rf_original_requirement_ledger"]])
    files["strip-width-sensitivity.csv"] = csv_text([{"RF板帶寬mm": r["strip_width_mm"], "左緣預算mm": report["config"]["rf_left_edge_budget_mm"], "護欄占位mm": r["guard_budget_mm"],
        "剩餘寬mm": r["clear_budget_mm"], "寬度模型容700": r["fits700_in_width_model"], "RF開洞㎡": r["sky_opening_sqm"], "實際產品核可": "未知"} for r in report["width_sensitivity"]])
    files["roof-routes.csv"] = csv_text([{"方案": o["id"], "試線": r["id"], "寬mm": r["width_mm"], "列明屋頂輪廓內": r["within_reserved_roof_surface"],
        "碰洞或護欄預算": r["void_or_guard_hit"], "碰列明機身": ",".join(r["unit_hits"]), "實際通行及整機搬運": "未知"} for o in report["options"] for r in o["rf_routes"]])
    files["engineering-replies.csv"] = csv_text([{"問題ID": f"BWC-{n:02d}", "待核": text,
        **dict.fromkeys(["同版資料圖號", "專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"], "")} for n, text in enumerate(report["config"]["limits"], 1)])
    body = '<h1>B工作天井與RF維修介面</h1><p class="note">獨立比較／未採用。R1優先深化介面，R0完整洞及R2乾式家務代價備案保留；不是取消三樓戶外工作陽台。原ABC／3D及搬轎版本不變。</p>'
    body += '<p>'+html.escape(report["conclusion"])+"</p>"
    body += table(["方案", "RF洞㎡", "三樓戶外候選㎡", "新濕地面壓2F乾區㎡", "RF左直路"], [[o["title"], f"{o['rf_opening_sqm']:.3f}",
        f"{o['working_court_outdoor_outline115_candidate_sqm']:.3f}", f"{o['wet_3F_over_2F_master_sqm']:.3f}", "需繞行" if o["old_left_corridor_interrupted_by_void_or_guard"] else "列明方塊可直達"] for o in report["options"]])
    body += '<p>R1留1100mm板帶，扣115左緣與100護欄預算後885mm；井前護欄退回天井上方，避原R0占祭祀投影0.25㎡的待核介面。RF少開2.473㎡，三樓濕地面仍完整5.112㎡；不是費用或漏水風險減少48.38%。RF上方1300×2030開口的採光、乾衣及合法戶外未知。</p>'
    for name, title in [("court-comparison.svg", "三個介面與目標代價"), ("R1-roof-service.svg", "R1 RF通行與未完成的全設備排位"), ("R1-section.svg", "上下關係：部分遮頂仍需完整防水")]:
        body += f'<section><h2>{title}</h2><p><a href="{name}">開啟向量圖</a></p><img style="width:100%;height:auto" src="{name}" alt="{title}"></section>'
    b = report["fixed_topology_bounds"]
    body += '<h2>不直接換位置的原因</h2>'+ul([
        f"後右濕區樂觀輪廓{b['rear_stack_only']['optimistic_available115_after_shaft_sqm']:.3f}㎡，公衛5＋陽台4要9㎡；尚未新加隔間就短2.867㎡。",
        "前KTV20＋戶外4要24㎡，前帶115基準只21.0159㎡；不默默縮KTV。",
        f"1700×3000瘦長天井雖有4.0719㎡，卻與原客房重疊1.479㎡並碰衣櫃；重切後客房115輪廓僅{b['slender_court_without_replanning_guest']['guest_remaining_after_recuts_and115_sqm']:.4f}㎡，不能沿用原12.423㎡。",
        "上述只針對固定二樓、梯核、祭祀保護與Q2前帶，並非所有整棟方案不可能。"])
    body += '<h2>原RF需求全部保留</h2>'+table(["需求", "目標㎡", "原下限㎡", "完整排位／核可"], [[r["title"], str(r["target_sqm"]), str(r["min_sqm"]), "未知"] for r in report["rf_original_requirement_ledger"]])
    body += '<p>前RF扣兩代表維修槽後樂觀餘20.97㎡，尚未扣其他機器與路線就比24㎡曬衣少3.03㎡。R2不能以「全部搬RF」稱原三樓目標已解。KTV19.2079㎡未達20、前量體新增10.647㎡、P3前排水缺口仍在。</p>'
    body += '<h2>條件到齊後依序回套</h2>'+ul(report["config"]["limits"])
    body += '<p>'+"／".join(f'<a href="{n}">{html.escape(n)}</a>' for n in files if n.endswith(".csv"))+'</p><p><a href="review.json">來源與計算JSON</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；沒有借用舊瀏覽器passed作本批驗收，專業核可未知。</small>'
    files["index.html"] = page("B工作天井與RF介面比較", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-b-working-court-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "adopted": False, "artifacts": {n: hashlib.sha256(v.encode()).hexdigest() for n, v in files.items()}}, ensure_ascii=False, indent=2)+"\n"
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
                raise ContractError("Working court comparison stale: "+", ".join(stale))
        else:
            out.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (out/name).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "options": 3, "files": len(files),
            "protected_controls": report["protected_controls_unchanged"], "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

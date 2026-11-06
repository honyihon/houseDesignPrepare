#!/usr/bin/env python3
"""Small standalone C balcony detail; never regenerate the frozen 3D viewer."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.c_balcony_coordination import build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402

OUT = "structured/candidates/c-balcony-coordination"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def render_svg(data):
    svg = ET.Element(f"{{{NS}}}svg", {
        "width": "1200", "height": "1220", "viewBox": "0 0 1200 1220",
        "role": "img", "aria-labelledby": "title desc", "lang": "zh-Hant"})
    ET.SubElement(svg, f"{{{NS}}}title", {"id": "title"}).text = "C棟2F景觀／洗曬深化：平面、上下層與剖面協調"
    ET.SubElement(svg, f"{{{NS}}}desc", {"id": "desc"}).text = (
        "依已確認的右側9平方公尺景觀與左側單機洗曬配置繪製。三樓平台平面完整重疊，"
        "但樓板、降板與土深未定。一樓冷氣概念管線有低位跨騎樓問題。僅工程協調，不是施工圖。")
    ET.SubElement(svg, f"{{{NS}}}style").text = (
        "text{font-family:'Noto Sans CJK TC','Microsoft JhengHei',sans-serif;fill:#203b35}"
        ".small{font-size:14px}.note{font-size:16px}.head{font-size:21px;font-weight:700}"
        ".pending{fill:#8b3d17}.dim{fill:none;stroke:#5f7770;stroke-width:1}")

    def node(tag, attrs=None, text=None):
        e = ET.SubElement(svg, f"{{{NS}}}"+tag, {k: str(v) for k, v in (attrs or {}).items()})
        e.text = text
        return e

    def label(x, y, text, cls="note", **attrs):
        return node("text", {"x": x, "y": y, "class": cls, **attrs}, text)

    def rect(x, y, w, h, fill, stroke="none", **attrs):
        return node("rect", {"x": x, "y": y, "width": w, "height": h,
            "fill": fill, "stroke": stroke, **attrs})

    def plan_rect(r, fill, stroke, **attrs):
        return rect(65+r[0]*.12, 180+r[1]*.12, r[2]*.12, r[3]*.12, fill, stroke, **attrs)

    rect(0, 0, 1200, 1220, "#f6faf7")
    label(40, 48, "C 棟 2F｜右景觀、左洗曬：深化協調圖", "head", **{"font-size": 27})
    label(40, 79, "使用方向已確認；平面取自 c-split／daily，未改原3D、設備尺寸、門窗或樓高。")
    rect(40, 96, 1120, 38, "#fff0d5")
    label(54, 121, "工程協調／非施工圖：土深、降板、實際排水點、冷氣機型及合法面積均未核定。", "note pending")
    label(65, 163, "道路／騎樓方向（圖上方）；尺寸單位 mm", "small")
    plan_rect(data["balcony_rect_mm"], "#edf2f0", "#365e53", **{"stroke-width": 2})
    plan_rect(data["garden_rect_mm"], "#e0f0df", "#2563b8", **{"stroke-dasharray": "7 5", "stroke-width": 2})
    for unit in data["hvac"]:
        plan_rect(unit["service_rect_mm"], "#ffce7b", "#bd731e", **{"fill-opacity": .12, "stroke-dasharray": "4 4"})
    for item in data["items"]:
        plan_rect(item["operation_rect_mm"], "#77b6d1", "#4e94b0", **{"fill-opacity": .12, "stroke-dasharray": "3 4"})
    for soil in data["soil_rects_mm"]:
        plan_rect(soil, "#90b78a", "#447448")
    for x, y in data["woody_points_mm"]:
        node("circle", {"cx": 65+x*.12, "cy": 180+y*.12, "r": 12, "fill": "#335e3b"})
    codes = {"washer": "W", "utility-sink": "S", "locked-cleaner": "D", "clothes-rack": "R"}
    for item in data["items"]:
        body = item["body_rect_mm"]
        code = codes[item["id"].rsplit(":", 1)[-1]]
        plan_rect(body, "#c9d6df", "#486275", **{"stroke-width": 1.5})
        label(65+(body[0]+body[2]/2)*.12, 185+(body[1]+body[3]/2)*.12, code,
            **{"text-anchor": "middle", "font-weight": 700})
    for n, unit in enumerate(data["hvac"], 1):
        body = unit["body_rect_mm"]
        plan_rect(body, "#d2d9dc", "#53636c", **{"stroke-width": 1.5})
        label(65+(body[0]+body[2]/2)*.12, 185+(body[1]+body[3]/2)*.12, "H"+str(n),
            **{"text-anchor": "middle", "font-weight": 700})
    route = data["service_routes_mm"]["washer"]
    node("polyline", {"points": " ".join(f"{65+x*.12},{180+y*.12}" for x, y in route),
        "fill": "none", "stroke": "#187b79", "stroke-width": 3, "stroke-dasharray": "7 5"})
    label(355, 523, "覆土投影 3.393㎡／四株木本示意", "note", **{"font-weight": 700})
    label(346, 552, "右側景觀 9㎡；土深 D 未定", "note", **{"font-weight": 700})
    label(350, 579, "後側通行／休憩帶：名義深1235", "small")
    label(350, 602, "保留門口及試線，不在此補放固定桌椅", "small")
    node("line", {"x1": 635, "x2": 743, "y1": 648, "y2": 648, "stroke": "#f6faf7", "stroke-width": 9})
    label(620, 675, "原900名義門洞／實際淨寬未核", "small")
    node("line", {"x1": 40, "x2": 40, "y1": 180, "y2": 648, "class": "dim"})
    label(25, 454, "3900", "small", transform="rotate(-90 25 454)")
    label(398, 701, "← 6000 →（全幅比較框，非地籍或合法申報尺寸）", "small", **{"text-anchor": "middle"})
    label(830, 180, "本輪保留與新增核對", "head")
    notes = [
        "W 洗衣機 650×650，僅一台",
        "S 預洗槽 600×600",
        "D 洗劑櫃 600×450",
        "R 晾衣架 2400×600，原尺寸",
        "藍虛框：原操作帶，不是多餘空地",
        "橙虛框：冷氣原維修預留",
        "H1＝C-AC01；H2＝C-AC03",
        "H3＝C-AC07；機身900×350",
        "風口方向／原廠淨空尚未知",
        "機身距前界僅100，勿封實外罩",
        "洗槽操作帶→景觀：135（名義）",
        "冷氣維修帶→景觀：200（名義）",
        "青線：700方塊中心試線",
        "不是已核輪椅或搬機路線",
        "覆土下方為1F騎樓通行區",
        "三樓同位平台投影覆蓋9㎡",
        "完整實板／支承仍待剖面核對",
    ]
    for n, text in enumerate(notes):
        label(830, 212+n*26, text, "small")
    node("line", {"x1": 40, "x2": 1160, "y1": 729, "y2": 729, "stroke": "#b8ccc1"})
    label(40, 766, "上下層剖面概念｜水平沿前後方向，土深／板厚未按比例，不可作放樣", "head")
    rect(80, 808, 702, 14, "#bcc8c5")
    label(90, 798, "3F 同位平台（基準 +6600）；完整樓板、懸臂系統與排水未核", "small")
    node("line", {"x1": 80, "x2": 782, "y1": 1092, "y2": 1092, "stroke": "#436657", "stroke-width": 3})
    node("line", {"x1": 782, "x2": 782, "y1": 822, "y2": 1092, "stroke": "#436657", "stroke-width": 3})
    rect(377, 838, 405, 254, "#ddeddf", **{"fill-opacity": .6})
    label(424, 879, "2F景觀投影深2250", "note")
    label(99, 922, "左：道路／前緣", "small")
    label(596, 922, "右：室內外牆", "small")
    label(100, 1068, "2F 基準 +3600；原上下層差3000", "small")
    rect(397.7, 1092, 162, 61, "#a4bb8b", "#47764b", **{"stroke-dasharray": "5 4"})
    label(411, 1121, "D 未定", "note", **{"font-weight": 700})
    label(88, 1169, "降板須與騎樓淨高／樓高一併核算；不得完工後切板或新增占用通行的落柱。", "small")
    for n, text in enumerate([
        "優先協調事項",
        "① 降板＋覆土荷重＋排水剖面",
        "② 土區檢修／溢流不經門口",
        "③ 冷媒、冷凝水另核管路",
        "④ C-AC01原管線15.335m",
        "其中一段2350高跨前騎樓",
        "若適用3500梁下要求須重排",
        "11.085m僅幾何下界，非新配管",
        "一樓樓高與梁底須同步協調",
    ]):
        label(830, 799+n*28, text, "head" if n == 0 else "small pending")
    label(40, 1200, "資料：c-split/daily凍結平面；本圖只讀衍生，未變更主案、產品、冷氣配管或核准任何高雄厝面積。", "small")
    return ET.tostring(svg, encoding="unicode")+"\n"


def render_section_options(data):
    """Four bounded section/stair budgets and a non-located pipe sequence."""
    svg = ET.Element(f"{{{NS}}}svg", {"width": "1200", "height": "1280", "viewBox": "0 0 1200 1280",
        "role": "img", "aria-labelledby": "title desc", "lang": "zh-Hant"})
    ET.SubElement(svg, f"{{{NS}}}title", {"id": "title"}).text = "C棟樓高、覆土與樓梯四案比較"
    ET.SubElement(svg, f"{{{NS}}}desc", {"id": "desc"}).text = (
        "原3.6m22級、4m22級、4m24級踏面270及4m24級踏面250。"
        "原140mm梯段前後預算需另保留；四案皆未採用，未驗結構淨高及新配管。")
    ET.SubElement(svg, f"{{{NS}}}style").text = (
        "text{font-family:'Noto Sans CJK TC','Microsoft JhengHei',sans-serif;fill:#203b35}"
        ".head{font-size:22px;font-weight:700}.body{font-size:16px}.small{font-size:14px}"
        ".pending{fill:#93461e}")

    def node(tag, attrs=None, text=None):
        e = ET.SubElement(svg, f"{{{NS}}}"+tag, {k: str(v) for k, v in (attrs or {}).items()})
        e.text = text
        return e

    def text(x, y, value, cls="body", **attrs):
        return node("text", {"x": x, "y": y, "class": cls, **attrs}, value)

    def box(x, y, w, h, fill, stroke="none", **attrs):
        return node("rect", {"x": x, "y": y, "width": w, "height": h,
            "fill": fill, "stroke": stroke, **attrs})

    def line(x0, y0, x1, y1, color, **attrs):
        return node("line", {"x1": x0, "y1": y0, "x2": x1, "y2": y1,
            "stroke": color, **attrs})

    box(0, 0, 1200, 1280, "#f6faf7")
    text(35, 43, "C 棟｜樓高、降板、樓梯與配管：四案一起比較", "head")
    text(35, 74, "保留右景觀／左洗曬使用方向；以下均為剖面及空間預算，未修改原3D、房間或門窗。")
    box(30, 91, 1140, 38, "#fff0d5")
    text(42, 116, "土深300、板厚150、其他層次50均為假設；3.5m為整段騎樓的保守協調目標，非逐處法規判決。", "small pending")
    comparison = data["section_comparison"]
    labels = {"c36-22": "原方案基準，降板淨高預算不足",
        "c40-22": "保留框體但級高增加，非首選",
        "c40-24-270": "舒適性優先續研；通道須重排",
        "c40-24-250": "緊湊比較；踏面減20，需確認接受度"}
    for n, option in enumerate(comparison["options"]):
        x, y = (30 if n % 2 == 0 else 615), (145 if n < 2 else 540)
        box(x, y, 555, 380, "#ffffff", "#b6ccc1", rx=8)
        text(x+16, y+32, option["label"], "head")
        bases = option["floor_bases_mm"]
        text(x+16, y+58, f'2F +{bases["floor-2"]}／3F +{bases["floor-3"]}／RF +{bases["floor-4"]}', "small")
        text(x+315, y+58, "梯段／平台深度預算", "small")
        ground = y+274
        floor_y = ground-option["first_storey_mm"]*.04
        target_y = ground-3500*.04
        soil = option["soil_cases_with_other_layer_assumption"][0]
        box(x+95, floor_y, 105, .04*soil["soil_depth_mm"], "#a5bf90", "#6e8d58")
        box(x+95, floor_y+.04*soil["soil_depth_mm"], 105, .04*comparison["illustrative_other_layers_mm"], "#80b7d3")
        slab_y = ground-soil["illustrative_underside_mm"]*.04
        box(x+95, slab_y-.04*150, 105, .04*150, "#a6b4af")
        line(x+20, floor_y, x+265, floor_y, "#315c4c", **{"stroke-width": 2})
        line(x+20, target_y, x+265, target_y, "#bb761e", **{"stroke-dasharray": "6 4"})
        line(x+20, ground, x+265, ground, "#315c4c", **{"stroke-width": 2})
        text(x+22, y+90, "2F土面／板厚均待核", "small")
        text(x+22, y+201, f'參考槽底：{soil["illustrative_underside_mm"]:g}', "small")
        text(x+22, y+224, f'相對3500餘量：{soil["margin_to_conservative_target_mm"]:+g}', "small pending")
        text(x+22, y+249, "未計實際梁深／地坪高差", "small")
        text(x+22, y+295, "土300案例；不是選定根域", "small")

        scale = .044
        core = option["existing_core_rect_mm"]
        extra = option["extension_retaining_existing_spare_mm"]
        ox, oy = x+322, y+85
        box(ox, oy, core[2]*scale, core[3]*scale, "#eef3f0", "#688579", **{"stroke-dasharray": "4 3"})
        if extra:
            box(ox, oy-extra*scale, core[2]*scale, extra*scale, "#f4d6bc", "#bb6a32")
        box(ox, oy-extra*scale, core[2]*scale, (core[3]+extra)*scale, "none", "#b47b25")
        old = comparison["original_flight_footprint_mm"]
        fx = ox+(old[0]-core[0])*scale
        fy = oy-extra*scale+option["retained_front_and_rear_budget_mm"][0]*scale
        fw = old[2]*scale
        fd = option["required_flight_and_landing_depth_mm"]*scale
        box(fx, fy, fw, fd, "#dce8ee", "#567b8b")
        departure = option["departure_landing_mm"]*scale
        middle = option["middle_landing_mm"]*scale
        box(fx, fy, fw, departure, "#c1d9c7", "#6c9d79")
        box(fx, fy+fd-middle, fw, middle, "#c1d9c7", "#6c9d79")
        for k in range(option["treads_per_flight"]+1):
            sy = fy+departure+k*option["tread_mm"]*scale
            line(fx, sy, fx+1000*scale, sy, "#6b8d9b")
            line(fx+1200*scale, sy, fx+fw, sy, "#6b8d9b")
        text(x+16, y+323, f'級高{option["riser_mm"]:.2f}｜梯段需{option["required_flight_and_landing_depth_mm"]}｜原框餘{option["remaining_in_existing_box_mm"]:+g}', "small")
        text(x+16, y+346, f'最少加{option["minimum_extension_using_all_existing_spare_mm"]}；保留原140總預留則加{extra}mm', "small")
        text(x+16, y+369, labels[option["id"]], "small pending")

    text(35, 950, "C-AC01配管順序示意｜先在室內側上升，再到設備區；新立管尚未定位", "head")
    box(65, 996, 300, 196, "#e5ece8", "#7b9487")
    box(365, 996, 420, 196, "#f2f5f3", "#7b9487")
    line(365, 1055, 785, 1055, "#597b69", **{"stroke-width": 4})
    text(95, 1024, "室內側可檢修機電帶待合圖", "small")
    text(505, 1024, "2F陽台／原室外機位置", "small")
    text(510, 1170, "1F騎樓通行比較區", "small")
    node("polyline", {"points": "190,1130 700,1130 700,1035", "fill": "none",
        "stroke": "#bb5946", "stroke-width": 3, "stroke-dasharray": "8 5"})
    node("polyline", {"points": "190,1130 190,984 700,984 700,1035", "fill": "none",
        "stroke": "#197f79", "stroke-width": 3, "stroke-dasharray": "5 4"})
    box(680, 1029, 40, 24, "#bacbd3", "#59727c")
    text(393, 1120, "紅：原2350低位跨越，需重排", "small pending")
    for n, message in enumerate([
        "不是已定位的新管路",
        "先核梁板、門窗與檢修可及",
        "冷凝水另走可清理排水",
        "原15.335m只對應3.6m基準",
        "升高樓層後必須重新配管",
        "不能直接沿用原估長或冷媒量",
    ]):
        text(820, 1007+n*30, message, "small")
    text(35, 1223, "加深影響按整座3600mm梯廳框試算，未定位新門洞／梯板；13cm是用光原預留的最小值，保留預留須27cm。", "small")
    text(35, 1253, "四案皆未選定／專業未核。新剖面預算不能沿用原3D驗收；實際淨高、結構、根域、法規與工程費仍待確認。", "small pending")
    return ET.tostring(svg, encoding="unicode")+"\n"


def artifacts(root=ROOT):
    report = build(root)
    return {OUT+"/review.json": json.dumps(report, ensure_ascii=False, indent=2)+"\n",
        OUT+"/plan-section.svg": render_svg(report),
        OUT+"/section-options.svg": render_section_options(report)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only check of existing detail outputs")
    args = parser.parse_args()
    try:
        outputs = artifacts()
        for name, content in outputs.items():
            target = ROOT/name
            if args.check:
                if not target.exists() or target.read_text(encoding="utf-8") != content:
                    raise ContractError("Detail artifact missing or stale: "+name)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
        print(f"C balcony coordination {'checked' if args.check else 'exported'}: {len(outputs)} static files; no 3D/browser run.")
    except (ContractError, KeyError, StopIteration, OSError) as exc:
        print("C balcony coordination failed: "+str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

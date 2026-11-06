#!/usr/bin/env python3
"""Export a local shared-landing plan and stair section, without a 3D build."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.c_stair_landing import build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402

OUT = "structured/candidates/c-stair-shared-landing"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


class Drawing:
    def __init__(self, title, description, height):
        self.root = ET.Element(f"{{{NS}}}svg", {"width": "1200", "height": str(height),
            "viewBox": f"0 0 1200 {height}", "role": "img", "aria-labelledby": "title desc", "lang": "zh-Hant"})
        self.node("title", {"id": "title"}, title)
        self.node("desc", {"id": "desc"}, description)
        self.node("style", text="text{font-family:'Noto Sans CJK TC','Microsoft JhengHei',sans-serif;fill:#203b35}"
            ".head{font-size:22px;font-weight:700}.body{font-size:16px}.small{font-size:14px}.warn{fill:#a54a29}")
        self.rect(0, 0, 1200, height, "#f6faf7")

    def node(self, tag, attrs=None, text=None):
        result = ET.SubElement(self.root, f"{{{NS}}}"+tag, {k: str(v) for k, v in (attrs or {}).items()})
        result.text = text
        return result

    def text(self, x, y, text, cls="body", **attrs):
        return self.node("text", {"x": x, "y": y, "class": cls, **attrs}, text)

    def rect(self, x, y, w, h, fill, stroke="none", **attrs):
        return self.node("rect", {"x": x, "y": y, "width": w, "height": h,
            "fill": fill, "stroke": stroke, **attrs})

    def line(self, x0, y0, x1, y1, stroke, **attrs):
        return self.node("line", {"x1": x0, "y1": y0, "x2": x1, "y2": y1,
            "stroke": stroke, **attrs})

    def finish(self):
        return ET.tostring(self.root, encoding="unicode")+"\n"


def render_plan(data):
    d = Drawing("C棟24級270mm踏面：共享前平台細排", "1F及2F平台與門口提案。共享前室200mm，保留1000mm平台及原梯廳外框，2F平台避開下方最後一級。", 1200)
    d.text(35, 44, "C 棟｜4m樓高、24級、270mm踏面：共享前平台細排", "head")
    d.text(35, 76, "兩折梯維持原外框；前平台完整1000mm，向公共前室共享200mm。3F橫向通道／孝親房／套衛不縮。")
    d.rect(30, 93, 1140, 42, "#fff0d5")
    d.text(43, 120, "屋主已選前置可關門：原梯廳前緣仍保持開口，門線另設在前方y=8550，不在平台內硬加門。", "small warn")
    for n, fid in enumerate(("floor-1", "floor-2")):
        card_x = 30 if n == 0 else 615
        d.rect(card_x, 151, 555, 572, "#ffffff", "#b5cbbf", rx=8)
        d.text(card_x+15, 184, "1F 出發／側通道" if n == 0 else "2F 到達／接續18級上樓", "head")
        px, py, scale = card_x+25, 198, .080

        def point(x, y, px=px, py=py, scale=scale):
            return px+(x-2200)*scale, py+(y-8400)*scale

        def rect(area, fill, stroke, *, point=point, scale=scale, **attrs):
            x, y = point(area[0], area[1])
            return d.rect(x, y, area[2]*scale, area[3]*scale, fill, stroke, **attrs)

        rect([2400, 8400, 3600, 560], "#eef4ec", "#bbcfc1")
        rect(data["core_rect_mm"], "#f5f8f6", "#526f60", **{"stroke-width": 2})
        rect(data["left_public_corridor_nominal_mm"], "#eef4ec", "#85a78a", **{"stroke-dasharray": "4 3"})
        rect(data["flight_footprint_mm"], "none", "#93a9a1", **{"stroke-dasharray": "5 4"})
        rect([2400, 13800, 1200, 500], "#f3e9d8", "#bba47d")
        rect([3600, 13800, 2400, 500], "#f3e9d8", "#bba47d")
        for s in data["surfaces"]:
            if s["storey"] != fid or s["kind"] == "shared-landing":
                continue
            rect(s["rect_mm"], "#dae6ed" if s["kind"] == "tread" else "#bddac8", "#7295a1")
        rect(data["shared_level_apron_mm"], "#b5dec7", "#247958", **{"stroke-width": 2})
        rect(data["shared_front_strip_mm"], "#f1ce8d", "#b77e24", **{"stroke-width": 1.5})
        if fid == "floor-2":
            rect(data["second_floor_floor_level_platform_removed_mm"], "#f7d4ca", "#b44c38", **{"stroke-dasharray": "4 3"})
        opening = next(o for o in data["opening_proposals"] if o["floor"] == fid)
        x0, y0 = point(opening["x_range_mm"][0], opening["y_mm"])
        x1, _ = point(opening["x_range_mm"][1], opening["y_mm"])
        d.line(x0, y0, x1, y0, "#f8fcf9", **{"stroke-width": 7})
        d.line(x0, y0, x1, y0, "#aa6940", **{"stroke-width": 2, "stroke-dasharray": "7 3"})
        x, y = point(3000, 11900)
        d.text(x, y, "1200 名義側通道", "small", transform=f"rotate(-90 {x} {y})", **{"text-anchor": "middle"})
        x, y = point(4820, 13300)
        d.text(x, y, "中間平台", "small", **{"text-anchor": "middle"})
        x, y = point(3000, 14125)
        d.text(x, y, "孝親房" if fid == "floor-1" else "後走道", "small", **{"text-anchor": "middle"})
        x, y = point(4800, 14125)
        d.text(x, y, "套衛（不縮）" if fid == "floor-1" else "後小廚房", "small", **{"text-anchor": "middle"})
        x, y = point(4800, 8640)
        d.text(x, y, "公共前室" if fid == "floor-1" else "二樓起居", "small", **{"text-anchor": "middle"})
        notes = (["24級＝12＋12", "級高166.67", "每梯段11踏面", "踏面270不縮", "平台1000不縮", "前移共享200", "兩區共用0.44㎡", "不是增加樓地板", "前開口3020待核"] if fid == "floor-1" else
            ["接續上樓仍18級", "左側出發平台保留", "右側到達面分開畫", "紅區不可整片封板", "保留最後一級上來", "起居共用0.44㎡", "沙發／櫃體不移", "前開口2200待核", "新板洞／護欄待核"])
        for k, message in enumerate(notes):
            d.text(card_x+350, 238+k*30, message, "small")
        d.text(card_x+16, 691, "固定梯廳3600×4840；灰虛框為原2200×4700梯段外框。", "small")
    d.text(35, 763, "共享的200mm是平整平台，沒有把階梯伸進三樓通道", "head")
    explanations = [
        "前平台從 y=8760 到9760，完整1000；原梯廳前緣 y=8960，所以200mm與公共前室共用。",
        "1F／2F各有0.44㎡公共地面同時供平台使用，不重複加算面積，不在此擺鞋櫃、椅子或門片。",
        "1F開口由原1000調整為合計3020；2F由原900調整為2200。這是門牆改動，結構／防火尚未核。",
        "二樓到達面不能照搬舊的整片平台：須避開1200×270mm區域，其中包含下方最後一級的上方空間。",
        "3F既有橫向通道名義深1360mm與前門位置保留；RF到達位置保留，未向屋頂平台新增封閉屋突。",
        "1F孝親房與套衛的牆線、床櫃及衛浴設備保留。名義側通道1200不是已扣牆、扶手的完成面淨寬。",
    ]
    for n, message in enumerate(explanations):
        d.text(40, 801+n*38, message, "small")
    d.rect(30, 1030, 1140, 104, "#fff0d5")
    d.text(45, 1058, "這個排法的代價", "head")
    d.text(45, 1087, "梯間較開放，起居區會更容易聽到樓梯聲；門牆分隔、隱私及門見梯的接受度仍須討論。", "body")
    d.text(45, 1114, "若需獨立門扇，不能把門塞進730mm偏移內；必須重新設計完整平台與門的位置。", "body warn")
    d.text(35, 1167, "另案仍保留250mm踏面比較。這次是局部細排，不代表降板、冷媒立管、實際淨高或建照已解決。", "small")
    return d.finish()


def render_section(data):
    d = Drawing("C棟24級樓梯上下層到達與回程梯段剖面", "沿右側回程梯段的概念剖面。二樓平台避開最後一級；離散踏面中心試算不等於實際淨高。", 1120)
    d.text(35, 44, "C 棟｜右側回程梯段剖面：檢查二樓平台會不會蓋住最後一級", "head")
    d.text(35, 77, "1F→2F：24級／4m；2F→3F及3F→RF保留18級／3m，所有上層基準提高400mm。")
    d.rect(30, 94, 1140, 42, "#fff0d5")
    d.text(42, 121, "這是既列水平踏面與平台的協調剖面，未設計斜梯板、梁、欄杆、門楣、管線或實際樓板洞口。", "small warn")
    px, py, xs, zs = 70, 982, .112, .071

    def xy(y, z):
        return px+(y-8500)*xs, py-z*zs

    colors = {"floor-1": "#237d72", "floor-2": "#397ea7", "floor-3": "#7d64a4"}
    for fid, z in data["floor_bases_mm"].items():
        x, y = xy(8500, z)
        d.line(50, y, 691, y, "#b2c5bd", **{"stroke-dasharray": "5 4"})
        d.text(52, y-10, f'{fid.rsplit("-", 1)[-1]+"F" if fid != "floor-4" else "RF"} +{z}', "small")
    right_x = data["flight_footprint_mm"][0]+data["flight_footprint_mm"][2]-500
    for surface in data["surfaces"]:
        r = surface["rect_mm"]
        if not r[0] <= right_x <= r[0]+r[2]:
            continue
        x0, y0 = xy(r[1], surface["top_z_mm"])
        x1, _ = xy(r[1]+r[3], surface["top_z_mm"])
        color = colors.get(surface["storey"], "#4c6f5d")
        d.line(x0, y0, x1, y0, color, **{"stroke-width": 4})
        if surface["kind"] == "tread":
            x2, y2 = xy(r[1]+r[3], surface["top_z_mm"]-166.6666666667)
            d.line(x1, y0, x2, y2, color, **{"stroke-width": 2})
    old_rect = data["second_floor_floor_level_platform_removed_mm"]
    x0, y0 = xy(old_rect[1], data["floor_bases_mm"]["floor-2"])
    x1, _ = xy(old_rect[1]+old_rect[3], data["floor_bases_mm"]["floor-2"])
    d.line(x0, y0, x1, y0, "#bd4f38", **{"stroke-width": 5, "stroke-dasharray": "5 3"})
    d.text(105, y0-24, "紅虛線：舊整片平台必須避開此段", "small warn")
    for n, message in enumerate([
        "平台怎麼分開？",
        "1F出發及2F到達採完整1000mm共享平台。",
        "2F接續上樓只保留左側1000mm出發面；",
        "右側及中間270mm區段不再整片封板。",
        "3F／RF仍按原平台位置到達。",
        "",
        "這裡不能直接照舊圖蓋板",
        f'若保留舊整片平台，最後一級上方試算只剩約{data["naive_full_width_platform_gap_over_last_incoming_tread_mm"]:.1f}mm。',
        "所以不只改階數，二樓板洞與護欄須另畫。",
        "",
        "離散試算的範圍",
        f'踏面中心共{data["headroom_proxy"]["sample_count"]}點；已列上方梯面最小距離',
        f'扣假設150mm後約{data["headroom_proxy"]["minimum_sampled_gap_mm"]:.0f}mm。',
        f'{data["headroom_proxy"]["samples_without_modelled_overhead"]}點沒有已列上方構造，狀態仍未知。',
        "沒有驗過梁底、斜梯板、欄杆或全寬淨高。",
        "",
        "門牆及消防是使用這個排法的前提",
        "前置門已選作深化，產品與消防仍待核；",
        "若需認證防火門，門牆及平台必須再合圖。",
        "",
        "覆土及C-AC01立管仍另案待設計。",
    ]):
        d.text(745, 180+n*35, message, "head" if n in (0, 6, 10) else "small")
    d.text(110, 1023, "← 前方共享平台　／　往後到中間平台 →（y座標，水平與垂直比例不同）", "small")
    d.text(35, 1070, "樓梯以外房間、家具及床位均保留；本剖面不是新整棟3D或法規／結構／照護驗收。", "small warn")
    return d.finish()


def render_partition_options(data):
    d = Drawing("C棟共享平台：開放與前置可關門比較", "門線前移410mm的幾何比較，平台仍完整。前室每層用原公共地面1.476平方米；門開時仍有斜視線，二樓側門未關就仍有旁通。", 1200)
    d.text(35, 44, "C 棟｜已確認前置可關門；開放梯間保留比較", "head")
    d.text(35, 77, "屋主已接受分隔配置，24級／270mm踏面保留；門組產品、淨寬、密封、防火及結構仍待核。")
    d.rect(30, 94, 1140, 52, "#fff0d5")
    d.text(43, 117, "前置門線 y=8550，比原梯廳前緣向前410mm；1200mm是名義開口，兩側另作100mm門前預算。", "small warn")
    d.text(43, 137, "圖示門關閉，虛框為開門停放預算；遮視線須使用適當不透視面，透明門扇不能達到相同效果。", "small warn")
    comparison = data["front_partition_comparison"]
    gates = next(o for o in comparison["options"] if o["id"] == "forward-closing-door")["floor_details"]
    for n, gate in enumerate(gates):
        cx = 30 if n == 0 else 615
        d.rect(cx, 163, 555, 500, "#ffffff", "#b5cbbf", rx=8)
        d.text(cx+16, 195, "1F 前置門／客餐通行" if n == 0 else "2F 前置門／起居側", "head")
        scale, px, py = .084, cx+25, 220

        def point(x, y, scale=scale, px=px, py=py):
            return px+(x-2200)*scale, py+(y-7300)*scale

        def rect(r, fill, stroke, *, point=point, scale=scale, **attrs):
            x, y = point(r[0], r[1])
            return d.rect(x, y, r[2]*scale, r[3]*scale, fill, stroke, **attrs)

        rect([2400, 7300, 3600, 2900], "#f5f8f6", "#bbcec3")
        rect(gate["vestibule_proxy_mm"], "#e2eee2", "#abc2a7")
        for r in gate["approach_rectangles_mm"].values():
            rect(r, "#e4f2f7", "#689cae", **{"fill-opacity": .6, "stroke-dasharray": "4 3"})
        rect(data["shared_level_apron_mm"], "none", "#28815d", **{"stroke-width": 2})
        for r in gate["wall_budgets_mm"]:
            rect(r, "#a9b8b0", "#617c6c")
        rect([gate["opening_x_mm"][0], 8500, 1200, 100], "#f5f8f6", "#926932")
        rect(gate["closed_leaf_rect_mm"], "#dfc79d", "#926932")
        rect(gate["parking_rect_mm"], "none", "#926932", **{"stroke-dasharray": "3 2", "stroke-width": 2})
        x0, y0 = point(2400, 8960)
        x1, _ = point(6000, 8960)
        d.line(x0, y0, x1, y0, "#1b7b68", **{"stroke-dasharray": "6 3"})
        if gate["floor"] == "floor-1":
            for ray in comparison["sightline_proxy_first_floor"]["rays"]:
                start, end = ray["from_mm"], ray["to_mm"]
                clipped_x = start[0]+(7300-start[1])/(end[1]-start[1])*(end[0]-start[0])
                x0, y0 = point(clipped_x, 7300)
                x1, y1 = point(ray["at_partition_x_mm"], gate["plane_y_mm"])
                d.line(x0, y0, x1, y1, "#b98031", **{"stroke-dasharray": "4 3"})
            d.text(cx+38, 244, "入口視線：上段省略", "small")
        else:
            rect([5020, 7300, 900, 660], "#d3dade", "#8198a3")
            d.text(cx+245, 262, "原沙發末段", "small")
        x, y = point(4820, 9520)
        d.text(x, y, "原1000平台完整保留", "small", **{"text-anchor": "middle"})
        for k, message in enumerate([
            "橙色：關門示意",
            "棕虛框：門片停放",
            "藍框：門前／後預算",
            "綠框：共享前平台",
            "綠虛線：原前緣8960",
            f'門後至第一級{gate["inner_leaf_face_to_first_riser_mm"]:g}',
            f'門後至平台前緣{gate["leaf_to_shared_apron_gap_mm"]:g}',
            "每層前室用1.476㎡",
            "含原共享平台0.44㎡",
            "另增加公共前室1.036㎡",
            "門框、扶手、密封待核",
        ]):
            d.text(cx+355, 232+k*31, message, "small")
        d.text(cx+16, 592, "名義門洞1200；完成門框／全開淨寬未確認，不等同已核照護淨寬。", "small")
        d.text(cx+16, 622, "只截取門前區域；其餘梯段、床位及三樓通道維持前輪細排。", "small")
    d.text(35, 706, "兩版的生活取捨", "head")
    notes = [
        "開放版：前室不再擴大，少一組門與回牆，但聲音、視線及冷氣可直接互通，不能用格柵補稱隔音。",
        "前置門版：門關時有機會減少直通；每層需用原公共地面1.476㎡作前室，含先前0.44㎡共享平台。",
        "一、二樓門洞及停放方向不同，不能把同一門組位置直接複製；原家具與操作帶的局部碰撞未發現衝突。",
        "門打開後仍有斜向看見梯段的平面視線；不把偏門或局部霧玻璃當成所有角度的風水／隱私核可。",
        "二樓還有起居延伸→乾式預留→梯廳側門的旁通，前門關閉不等於側門關閉，也不保證空調分區。",
        "若要隔音，門組密封、固定面到板底的封閉、側門及其他介面要一起核，尚無產品測試可提供dB數值。",
        "門前／後900mm、兩側100mm及100mm隔屏厚度只是本輪幾何預算；實際救援、門片、把手及淨寬待核。",
    ]
    for n, message in enumerate(notes):
        d.text(40, 747+n*42, message, "small")
    d.rect(30, 1060, 1140, 83, "#fff0d5")
    d.text(44, 1090, "屋主已接受前置可關門作深化方向；產品及消防／結構仍待合圖。", "head")
    d.text(44, 1120, "分隔已併入原3D的C新配置；瀏覽器待驗，防火區劃、隔音、照護或施工未核。", "body warn")
    d.text(35, 1174, "同一份新細排資料衍生；不新增虛構面積，不縮孝親套衛，不把舊Windows通過結果當新門組驗收。", "small")
    return d.finish()


def render_door_fit(data):
    d = Drawing("C棟已確認前置門：完成淨寬、停放及二樓側門核對", "屋主接受配置，門組未選定。1200名義開口維持900完成淨寬目標；100mm門組運行深度只有60mm平台前餘量。側門須與前門一併核。", 1250)
    d.text(35, 44, "C 棟｜前置可關門已確認：門組尺寸與二樓側門協調", "head")
    d.text(35, 78, "保留24級／270mm踏面、1000mm完整平台、孝親套衛及三樓通道；開放版留比較。")
    d.rect(30, 95, 1140, 43, "#fff0d5")
    d.text(43, 122, "以下均為門組選型前的扣減／停放敏感度；沒有選定產品，也不將900mm名義側門當成900mm完成淨寬。", "small warn")
    fit = data["door_fit_review"]
    gates = fit["floor_details"]
    d.text(35, 179, "前門：1200名義開口，守住900淨寬目標", "head")
    d.text(635, 179, "門片停放：左右不能當成相同尺寸", "head")
    for x, label in ((40, "總扣除"), (185, "計算淨寬"), (355, "對900餘量"),
                     (640, "假設門片寬"), (820, "1F餘量"), (1000, "2F餘量")):
        d.text(x, 214, label, "small")
    for n, case in enumerate(gates[0]["clear_width_cases"]):
        y = 246+n*29
        d.text(40, y, str(case["total_frame_stop_overlap_mm"]), "body")
        d.text(185, y, str(case["calculated_clear_width_mm"]), "body")
        d.text(355, y, f'{case["margin_to_900mm_mm"]:+g}', "body warn" if case["margin_to_900mm_mm"] <= 0 else "body")
    for n, first in enumerate(gates[0]["leaf_width_cases"]):
        y = 246+n*29
        second = gates[1]["leaf_width_cases"][n]
        d.text(640, y, str(first["assumed_leaf_width_mm"]), "body")
        d.text(820, y, f'{first["parking_margin_mm"]:+g}', "body")
        d.text(1000, y, f'{second["parking_margin_mm"]:+g}', "body warn" if second["parking_margin_mm"] <= 0 else "body")
    d.text(40, 414, "扣除含框、止擋及未退盡門片；不是逐項相加的產品規格。", "small")
    d.text(640, 414, "先扣100mm角部預算：1F可用1800、2F可用1500。", "small")
    d.text(40, 440, "剩900只是達到算術目標，尚無實際門框／淨寬核可。", "small warn")
    d.text(640, 440, "門片可能比洞口寬，不能只留1200便當能全開。", "small warn")
    d.line(30, 462, 1170, 462, "#c0d3c7")
    d.text(35, 499, "門組深度：不要把框軌／把手吃掉的平台空間漏算", "head")
    for x, label in ((40, "假設深度"), (240, "原門線距平台"), (470, "保留原60餘量需前移"), (790, "兩層各多用前室")):
        d.text(x, 533, label, "small")
    for n, case in enumerate(gates[0]["track_and_leaf_depth_cases"]):
        y = 566+n*27
        d.text(40, y, str(case["assumed_track_leaf_depth_mm"]))
        d.text(240, y, f'{case["margin_to_apron_at_current_line_mm"]:+g}', "body warn" if case["margin_to_apron_at_current_line_mm"] <= 0 else "body")
        d.text(470, y, str(case["forward_shift_to_keep_original_60mm_budget_mm"]))
        d.text(790, y, f'{case["extra_public_floor_if_shifted_sqm"]:.3f}㎡')
    d.text(40, 774, "180深若保留原餘量，需前移80mm；2F門外預算距電視操作帶僅20mm，不能直接採用。", "small warn")
    d.text(40, 799, "220深需前移120mm時已碰2F電視操作帶。實際門線維持8550；表中前移都尚未選定。", "small warn")
    d.line(30, 820, 1170, 820, "#c0d3c7")
    d.text(35, 857, "二樓前門與側門：兩道一起處理，不能只關前門", "head")
    states = fit["two_door_states"]
    descriptions = ["前門＋側門兩路", "仍有前門一路", "仍可經乾式預留繞側門", "未見這兩路敞開；不等於隔音或氣密"]
    for n, state in enumerate(states):
        d.text(40, 895+n*32,
            f'前門{"開" if state["front_door_open"] else "關"}／側門{"開" if state["side_door_open"] else "關"}：{descriptions[n]}', "body")
    d.text(40, 1035, "側門原900名義洞口，沒有額外框預算；完成淨寬目標仍900。必要時擴洞須另核，不默縮側通道。", "small warn")
    d.text(40, 1064, "上述只列敞開門洞路徑：人仍可開門通行，不是逃生圖，也沒有計算門縫漏氣或聲學數值。", "small")
    d.rect(30, 1090, 1140, 110, "#fff0d5")
    d.text(44, 1119, "交門商／建築師一次回覆", "head")
    d.text(44, 1148, "框外／洞口定義、完成淨寬、實際門片寬、退盡停放、軌與把手深度、雙面操作、順平地面及救援方式。", "small")
    d.text(44, 1177, "再核密封、固定面到板底收口、側門及消防適用；沒有門型可把未知淨高、結構或防火需求直接抵銷。", "small")
    d.text(35, 1230, "配置已併原3D；產品、側門擴洞及門線再前移未選定，瀏覽器待驗，無施工核可。", "small warn")
    return d.finish()


def artifacts(root=ROOT):
    result = build(root)
    return {OUT+"/review.json": json.dumps(result, ensure_ascii=False, indent=2)+"\n",
        OUT+"/plans-1f-2f.svg": render_plan(result), OUT+"/return-flight-section.svg": render_section(result),
        OUT+"/partition-options.svg": render_partition_options(result),
        OUT+"/door-fit-and-side-door.svg": render_door_fit(result)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        files = artifacts()
        for name, content in files.items():
            path = ROOT/name
            if args.check:
                if not path.exists() or path.read_text(encoding="utf-8") != content:
                    raise ContractError("Stair detail missing or stale: "+name)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        print(f"C shared stair landing {'checked' if args.check else 'exported'}: {len(files)} static files; no scene/browser run.")
        return 0
    except (ContractError, KeyError, StopIteration, OSError) as exc:
        print("C shared stair landing failed: "+str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

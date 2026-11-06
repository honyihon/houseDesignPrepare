#!/usr/bin/env python3
"""Bounded static ERV duct interfaces and service sections; never browser/3D generation."""
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

from house_design.abc_fresh_air_detail import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_fresh_air_layout import draw_rooms  # noqa: E402
from scripts.export_abc_next_improvements import Plan, Sheet, csv_text, table  # noqa: E402


def plans(report, bid):
    s = Sheet(bid+"棟｜關門支路／前後外口研究", report)
    s.text("藍底＝500mm乾淨雙管帶；細藍SA／紅RA；綠OA／橙EA。各色線不等於已排開的真實風管。", 30, 118)
    for k, fid in enumerate(["floor-1", "floor-2", "floor-3"]):
        x = 30+280*k
        s.text(str(k+1)+"F｜街／騎樓 ↑", x, 156, class_="label")
        p = Plan(s, (x, 178), .038)
        rooms = report["roster"][bid][fid]
        draw_rooms(p, rooms)
        for room in rooms:
            if "rect_mm" in room and room.get("features"):
                p.openings(room)
        for n in report["networks"]:
            if (n["building"], n["floor"]) != (bid, fid):
                continue
            for r in n["screen"]["swept_rects_mm"]:
                p.box(r, fill="#4a9bb4", opacity=.24, data_kind="clean-pair-band")
            for path in n["paths"]:
                p.path(path, stroke="#25708c", stroke_width=2)
        for g in report["outdoor_groups"]:
            if (g["building"], g["floor"]) != (bid, fid):
                continue
            alternate = "fallback" in g["preference"]
            for role, color in [("OA", "#258444"), ("EA", "#b66614")]:
                path = g[role+"_path"]
                p.path(path, stroke=color, stroke_width=2, stroke_dasharray="5 4" if alternate else "none",
                    data_kind="unapproved-external-route", data_group=g["id"], data_role=role)
                pos = p.p(path[-1])
                s.add("circle", cx=pos[0], cy=pos[1], r=4, fill=color)
                s.text(role, pos[0]-7, pos[1]+(-7 if g["side"] == "front" else 15), class_="tiny", fill=color)
        for b in report["branches"]:
            if (b["building"], b["floor"]) != (bid, fid):
                continue
            for role, color in [("SA", "#2d63bd"), ("RA", "#a73d42")]:
                p.path(b[role+"_path"], stroke=color, stroke_width=1.1, data_kind="closed-room-branch")
                pos = p.p(b[role])
                s.add("circle", cx=pos[0], cy=pos[1], r=3, fill=color, data_room=b["id"], data_role=role)
        for u in report["units"]:
            if (u["building"], u["floor"]) == (bid, fid):
                p.box(u["rect_mm"], fill="#bda4d1", opacity=.8, stroke="#683c86", stroke_width=1.5)
                p.text(u["id"], u["rect_mm"][0]+40, u["rect_mm"][1]+350, class_="tiny")
        if bid == "B" and k == 0:
            p.text("香火專用補排另案", 2500, 6800, class_="small")
    notes = {
        "A": ["A1前口；A2／A3後口。", "睡房／書房各有SA及RA研究。", "檢修不踩床、不借MDF。"],
        "B": ["後口預設，前口虛線獨立備案。", "兩組替代，不是同時安裝。", "右側乾頸部接通前起居／閱讀。", "不穿乾保護室或浴廁。", "乾管祭祀投影／梁底仍待核。"],
        "C": ["三層前口，高位實牆待核。", "前置門／梯門保持可關。", "1F側帶避完整樓梯區。", "2F唯一洗衣機不動。"]}
    s.lines(notes[bid], 875, 185, class_="label")
    s.lines(["米色＝樓梯／濕區／設備保護", "灰＝既有家具投影", "窗門仍保留，外口高度未定。", "同牆投影碰窗門須補剖面。", "不能直接在玻璃／梁／共壁開孔。"], 875, 390, class_="small")
    s.lines(["所有Z／梁底／消音／產品未知。", "四管交會不能共塞500×300。", "橫排研究950×300；", "雙層研究500×500。", "風量／噪音／壓差仍須實測。", "三樓既定用途一期啟用通風。"], 875, 590, class_="label")
    s.text("24乾區服務標籤均保留；開放區不是新隔間，48標記不是已指定採購風口數。", 30, 925)
    s.text("所有前後口均未核合法開孔／防雨／短路／鄰戶污染源；B前後搬轎兩版與原3D不改。", 30, 958)
    s.text("只看平面相連不能當可施工；需另核關門支路、三維轉彎、全機抽換及檢修期間逃生。", 30, 991)
    return s.output()


def section_sheet(report):
    s = Sheet("新風四管／天花／檢修拆換剖面比較", report)
    s.lines(["兩支Ø125＋各側25保溫＝外徑175；管間50、邊界各50，均為未選型研究預算。",
        "四管不能重用500×300雙管帶；這不是產品／防火／消音最小安裝尺寸。"], 30, 125)
    for x, key, title in [(30, "four_flat", "四管橫排：比較950×300"), (750, "four_stacked", "四管雙層：比較500×500")]:
        d = report["duct_sections"][key]
        s.text(title, x, 210, class_="label")
        scale, y = .5, 230
        s.box([x, y, (950 if key == "four_flat" else 500)*scale, (300 if key == "four_flat" else 500)*scale],
            fill="#edf3f5", stroke="#4d7c88", stroke_width=1.5)
        for row in range(d["rows"]):
            for col in range(d["columns"]):
                cx, cy = x+(50+87.5+col*225)*scale, y+(50+87.5+row*225)*scale
                s.add("circle", cx=cx, cy=cy, r=87.5*scale, fill="#9bc2d0", stroke="#3c7284")
        s.text("所需寬／高 "+str([d["width_mm"], d["height_mm"]])+" mm", x, 520)
    s.lines(["完成天花高度僅敏感度；實際梁底、板厚、管口及冷媒交叉未提供。",
        "假設板下2600mm：橫排＋450機位＋50吊掛公差 → 最多2100mm；雙層 → 2050mm。",
        "以上不是現場層高、法定淨高或已接受低天花；不指示鑽梁。"], 30, 565)
    s.text("名義可拆板≠完成淨口≠全機運出", 30, 685, class_="label")
    for y, case in zip([730, 840], report["removal_cases"], strict=True):
        s.text("名義 "+str(case["nominal_panel_mm"])+" − 各側25框料 → 淨口 "+str(case["clear_panel_mm"]), 30, y)
        s.text("參考外形1230×637＋各側50手部 → 需1330×737；餘量 "+str(case["margin_mm"])+" mm", 30, y+32)
        s.text("直向平面預算"+("容得下；仍非全機可換" if case["straight_plan_budget_fits"] else "不足，不當合格開口"), 30, y+64, fill="#a23b34")
    s.lines(["原廠日常濾網側孔與抽芯區另核；本案600側條帶是假設，不能從600方孔推導抽拉長度。",
        "還要核吊架／接口斷開、重量落機、架梯與照護／逃生、門轉角及全程運出；一項未核就不宣稱完成。"], 30, 965, step=28)
    return s.output()


def response_rows(report):
    return [{"network": n["id"], "unit": n["unit"], "building": n["building"], "floor": n["floor"],
        "window_head_beam_ceiling_section": None, "legal_OA_EA_wall_and_neighbours": None,
        "chosen_front_or_rear_alternative": None, "actual_four_duct_and_silencer_section": None,
        "model_count_low_flow_at_dirty_filter_pressure": None, "closed_room_measured_SA_RA_noise": None,
        "filter_pull_hatch_and_whole_body_replacement": None, "safe_ladder_care_egress": None,
        "local_exhaust_simultaneous_makeup_and_humidity": None, "supplier_dated_drawing_reference": None,
        "professional_acceptance": "unknown"} for n in report["networks"]]


def index_html(r):
    esc = html.escape
    branch_table = table(["乾區服務標籤", "送風SA座標mm", "回風RA座標mm", "風量／高度"],
        [[b["id"]+"｜"+b["name"], b["SA"], b["RA"], "未知；每層風量不重複派給各房"] for b in r["branches"]])
    external_table = table(["替代組", "OA／EA水平距離mm（非法定門檻）", "OA同牆投影", "EA同牆投影", "狀態"],
        [[g["id"], g["own_pair_horizontal_distance_mm"], g["OA_opening"]["same_wall_xy_opening_span_hits"],
          g["EA_opening"]["same_wall_xy_opening_span_hits"], "未核Z／實牆／合法外口／污染源"] for g in r["outdoor_groups"]])
    service_table = table(["機位", "600側抽條帶平面未遇列出障礙的方向（非產品核可）", "待核"],
        [[s["unit"], [v["side"] for v in s["sides"] if v["xy_clear_of_listed_protection_and_furniture"]],
          "實際濾芯行程／安全架梯／整機落機及運出"] for s in r["service_candidates"]])
    images = "".join(f'<figure><a href="{b}-routes.svg">開啟{b}棟可放大圖</a><img src="{b}-routes.svg" width="1400" height="1100" alt="{b}棟三層新風路由研究，未採用"></figure>' for b in "ABC")
    links = "".join(f'<li><a href="{name}">{label}</a></li>' for name, label in [
        ("room-branches.csv", "24乾區送回風與下方投影"), ("outdoor-interfaces.csv", "10組室外口及待核"),
        ("crossings.csv", "四管可能交會"), ("service-candidates.csv", "8處機位四方向側抽研究"),
        ("ceiling-cases.csv", "板下高度敏感度"), ("contractor-response.csv", "建商逐層八列回覆")])
    refs = "".join(f'<li><a href="{esc(s["url"], quote=True)}">{esc(s["publisher"])}｜{esc(s["id"])}</a></li>' for s in r["research"]["sources"])
    gaps = "".join("<li>"+esc(t)+"</li>" for t in r["open_gates"])
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ABC新風關門支路／室外口／檢修比較</title><style>body{{font:16px/1.65 system-ui,sans-serif;background:#fafbf8;color:#263e49;margin:0}}main{{max-width:1400px;margin:auto;padding:24px}}h1{{font-size:27px}}h2{{font-size:22px}}.warning{{border-left:5px solid #ac4c2e;padding:16px;background:#fff0e8}}table{{border-collapse:collapse;width:100%;margin:18px 0}}th,td{{border:1px solid #bdcbc7;text-align:left;padding:9px;overflow-wrap:anywhere}}section{{overflow-x:auto}}figure{{margin:25px 0}}img{{max-width:100%;height:auto}}small{{overflow-wrap:anywhere}}a{{color:#176b83}}</style></head><body><main>
<h1>ABC新風深化：關門支路、前後外口與檢修</h1>
<p class="warning">獨立比較／未採用。8機位不是確定8台；24乾區標籤不是新隔間；48末端只是座標研究。沒有核定風量、高度、合法開孔、產品或施工／照護／消防／風水核可。原ABC、目前3D與149控制不改。</p>
<p>本批先接續常用層分區，不封死其他集中架構。三樓既定用途一期要通風，未知人數不當0。<a href="../abc-fresh-air-layout-v1/index.html">上一批機位／同範圍報價</a>／<a href="../../../Docs/abc-fresh-air-detail-v1.md">尺寸與代價完整說明</a>。</p>
<h2>本輪具體進展</h2><p>B2／B3沿右側乾頸部接通前起居／閱讀，500mm整帶避浴廁、樓梯及乾保護室，不先增加機台；但梁底、乾管祭祀投影與性能仍未核。C前置門／梯門可關，各乾區有密閉送回風研究，不借梯間或浴廁當一般回收。B香火另系統。</p>
<p>室外口只比前後端，不擅用側界共壁。B後側預設與無後口的前側備案各自保留，兩組替代。後巷前提不是合法開孔或乾淨空氣保證。</p>
<h2>四管與檢修</h2><p>雙管500×300不能塞四管；同高四管以950×300、雙層以500×500比較，需再加真實消音／分歧與梁冷媒剖面。天花敏感度不是已知層高或法定淨高。1260×700名義拆板扣假設框料／手部後不足；1600×1000整片可拆板僅平面預算容納，不是全機運出已完成。</p>
<p><a href="service-sections.svg">開啟四管／天花／拆板剖面</a></p><img src="service-sections.svg" width="1400" height="1100" alt="四管斷面與檢修算術比較，實際產品未知">
<section><h2>室外口：同牆窗門投影不能忽略</h2>{external_table}<p>投影重疊須取得窗頭以上實牆剖面，不改窗、不鑽梁；無記錄也不代表沒有窗門。另查鄰戶排氣、香火、道路、熱風及可開窗，不能把兩口距離當合格簽證。</p></section>
<section><h2>各乾區關門供回風</h2>{branch_table}</section><section><h2>日常維護與全機拆換分開</h2>{service_table}</section>
<h2>官方商品資料仍不是本案選型</h2><p>VH-T15D官網最低檔90m³/h，高於C2一人前批25～35初估；只提示低負載工作點須核，不能直接說不適用。Panasonic FY-15ZY1W型錄設計頁建議側方600方孔，不能拿宣傳450點檢口當整機拆換口；本案600側條帶也不是原廠抽拉行程。</p><ul>{refs}</ul>
<h2>建商回覆與可下載資料</h2><ul>{links}</ul><p>未知欄留空，不當0、不造價格。等同服務範圍的三架構報價仍用前批九列表。</p>
<h2>三棟圖面</h2>{images}<h2>尚未完成的核對</h2><ul>{gaps}</ul>
<p><a href="review.json">本批計算與來源</a>／<a href="artifact-manifest.json">產物雜湊</a></p>
<small>來源 {esc(r['source_layout_report_sha256'])}<br>本批 {esc(r['report_hash'])}<br>靜態輸出；瀏覽器／WebGL未執行，不能沿用舊passed。屋主前置決策、法規／宗教／照護／產品／施工核可均不從此圖推定。</small></main></body></html>'''


def render(report):
    files = {b+"-routes.svg": plans(report, b) for b in "ABC"}
    files.update({"service-sections.svg": section_sheet(report), "index.html": index_html(report),
        "room-branches.csv": csv_text(report["branches"]), "outdoor-interfaces.csv": csv_text(report["outdoor_groups"]),
        "crossings.csv": csv_text(report["interfaces"]), "service-candidates.csv": csv_text(report["service_candidates"]),
        "ceiling-cases.csv": csv_text(report["ceiling_cases"]), "contractor-response.csv": csv_text(response_rows(report)),
        "review.json": json.dumps(report, ensure_ascii=False, indent=2)+"\n"})
    manifest = {"schema": "house-abc-fresh-air-detail-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "adopted": False,
        "artifacts": {n: hashlib.sha256(v.encode()).hexdigest() for n, v in files.items()}}
    files["artifact-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    try:
        report = build(ROOT)
        files, out = render(report), ROOT/OUT
        if args.check:
            stale = [n for n, v in files.items() if not (out/n).is_file() or (out/n).read_bytes() != v.encode()]
            if stale:
                raise ContractError("Fresh-air detail artifacts stale: "+", ".join(stale))
        else:
            out.mkdir(parents=True, exist_ok=True)
            for n, v in files.items():
                (out/n).write_text(v, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "artifacts": len(files),
            "networks": len(report["networks"]), "dry_space_labels": len(report["branches"]),
            "outdoor_alternative_pairs": len(report["outdoor_groups"]), "protected_controls_unchanged": report["protected_controls_unchanged"],
            "adopted": False, "full_MEP_fit_verified": False, "browser": "not-run"}))
        return 0
    except (ContractError, OSError, ValueError, KeyError) as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

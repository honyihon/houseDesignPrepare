#!/usr/bin/env python3
"""Export three bounded ERV reservation sheets; no 3D/browser/model generation."""
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

from house_design.abc_fresh_air_layout import OUT, build, protected_room, room_polygon  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import Plan, Sheet, csv_text, table  # noqa: E402


def draw_rooms(plan, rooms):
    for r in rooms:
        fill = "#f0e4d6" if protected_room(r) else "#edf1ec"
        if r.get("outdoor"):
            fill = "#e4ecef"
        polygon = room_polygon(r)
        plan.s.add("polygon", points=" ".join(f"{x},{y}" for x, y in [plan.p(p) for p in polygon]),
            fill=fill, stroke="#94a49d", stroke_width=.7, data_room=r["id"])
        for item in r.get("furniture", []):
            plan.box(item["rect_mm"], fill="#c5ccc8", stroke="#788e82", stroke_width=.6)


def sheet(report, bid):
    s = Sheet(bid+"棟｜新風機位／分層預留 vs 集中管井", report)
    s.text("左：常用層機位及局部送回風帶。右：檢修與管井比較。兩種架構不能疊成同時安裝。", 30, 119)
    shaft = next(r for r in report["central_shaft_tests"] if r["building"] == bid)
    notes = {
        "A": ["優先報常住層分區，三樓使用區一期做。", "A1避MDF／梯下；A2後廳檢修暫占走道。", "主臥、次臥、書房分支與關門回風另排。"],
        "B": ["B1香火獨立補排，沒有一般ERV回收。", "B2機位只試後主臥；前側起居尚未接通。", "B3客房先留，前閱讀不能當已送到風。"],
        "C": ["C1走左側高位帶，不穿樓梯區。", "前置門／梯門可關，孝親房專支回風。", "C2睡房分支；保留唯一2F洗衣機。"]}
    for fid, ox in [("floor-1", 30), ("floor-2", 300)]:
        s.text(fid.replace("floor-", "")+"F 常用層", ox, 157, class_="label")
        p = Plan(s, (ox, 175), .04)
        draw_rooms(p, report["roster"][bid][fid])
        for route in report["partial_corridors"]:
            if (route["building"], route["floor"]) == (bid, fid):
                for band in route["swept_rects_mm"]:
                    p.box(band, fill="#72b7bc", opacity=.3, data_kind="partial-duct-band")
                p.path(route["points_mm"], stroke="#147d8b", stroke_width=2)
        for unit in report["units"]:
            if (unit["building"], unit["floor"]) == (bid, fid):
                p.box(unit["rect_mm"], fill="#bda4d1", opacity=.85, stroke="#693b82", stroke_width=2,
                    data_kind="unit-envelope", data_unit=unit["id"])
                p.text(unit["id"], unit["rect_mm"][0]+40, unit["rect_mm"][1]+400, class_="tiny")
        # Dashed shaft is an ALTERNATIVE, deliberately rejected; not part of floor-zoned route.
        if fid in shaft["floors"]:
            p.box(shaft["rect_mm"], fill="none", stroke="#ad3329", stroke_width=2,
                stroke_dasharray="5 3", data_kind="rejected-central-shaft")
        if bid == "B" and fid == "floor-1":
            p.text("香火另系統", 2500, 6800, class_="small")
        s.text("街／騎樓 ↑", ox+30, 907, class_="small")
    s.lines(notes[bid], 580, 160, step=28, class_="label")
    s.text("紫框＝1600×1000×450試排預算，可旋轉", 580, 265)
    s.text("綠帶＝500×300局部密閉送／回風帶，非整層四管", 580, 293)
    s.text("紅虛框＝集中式替代井試點，本次不留", 580, 321, fill="#a43a30")
    s.text("灰＝家具；米色＝衛浴／樓梯／設備或乾保護區", 580, 349)
    s.text("整機拆換剖面必須補圖，不能只留小檢修孔", 580, 405, class_="label")
    # A controlled diagram of the planning box; not a selected-product installation drawing.
    frame = [610, 435, 1600*.25, 1000*.25]
    s.box(frame, fill="#ece5f2", stroke="#693b82", stroke_width=2)
    s.box([640, 466, 1230*.25, 637*.25], fill="#c5b0d5", stroke="#693b82")
    s.lines(["封存尺寸例 1230×637×220", "非已選型／接口及濾網抽拉待核"], 655, 526, step=28)
    s.text("1260×700名義拆板也未核框料／手部／轉向", 610, 708, class_="small")
    s.text("450高含管接是預算；實際梁底／完成天花Z未知", 580, 746)
    s.text("地面檢修不能以「不碰家具」當作逃生可通行", 580, 774)
    strips = "／".join(f"{v:g}" for v in shaft["remaining_side_strips_mm"])
    s.text(f"集中井 {shaft['id']}：兩旁剩 {strips} mm", 580, 835, class_="label")
    s.text(f"本次旁通目標 {shaft['required_bypass_mm']} mm 未保住；此試點不留。", 580, 866)
    if bid == "B":
        s.text("主臥20.0761 − 0.315＝19.7611㎡，低於原20㎡。", 580, 897)
    elif bid == "C":
        s.text("廚房原1685 → 885mm；非完整照護動線核可。", 580, 897)
    else:
        s.text("1370mm旁通不是1500mm轉位面，不能當通過。", 580, 897)
    future = next(u for u in report["units"] if u["building"] == bid and u["floor"] == "floor-3")
    s.text(f"3F使用預留 {future['id']}：{future['host_room_name']}，XY {future['rect_mm']} mm", 30, 953)
    s.text("尚缺：OA／EA外牆終端、完整支路、梁門剖面、消防、濾網靜壓、低速噪音及補氣平衡。", 30, 987)
    return s.output()


def service_rows(report):
    return [{"id": u["id"], "building": u["building"], "floor": u["floor"],
        "nominal_service_floor_rect_mm": u["service_floor_rect_mm"],
        "filter_access_direction_and_dimensions": None, "actual_clear_removal_panel_mm": None,
        "whole_unit_replacement_path": None, "four_ports_and_silencer_envelope": None,
        "finished_ceiling_z_and_headroom": None, "safe_ladder_and_egress_while_servicing": None,
        "signed_product_section_reference": None, "approved": False} for u in report["units"]]


def index_html(report):
    esc = html.escape
    unit_table = table(["候選", "室內乾區", "平面預算mm", "階段", "仍需處理"], [
        [u["id"], u["host_room_name"], u["rect_mm"], "常住層一期" if u["phase"] == "install-now" else "三樓使用區一期，不只留管", u["note"]]
        for u in report["units"]])
    shaft_table = table(["集中井替代試點", "兩旁剩mm", "比較目標mm", "代價", "處理"], [
        [s["id"], s["remaining_side_strips_mm"], s["required_bypass_mm"],
         "主臥19.7611㎡，低於20㎡" if s["building"] == "B" else s["criterion"], "這個點不留，不代表所有中央案不可行"]
        for s in report["central_shaft_tests"]])
    routes = table(["部分帶", "用途", "下方家具XY投影", "C-AC01同層XY交叉", "完成狀態"], [
        [r["id"], r["purpose"], r["fixed_body_xy_below_or_at_route"] or "列出物件無投影交叉",
         r["ac01_plan_crossings"] if r["building"] == "C" else "不適用", "高度未知／不是整層接通"] for r in report["partial_corridors"]])
    images = "".join(f'<figure><a href="{b}-reservations.svg"><img src="{b}-reservations.svg" alt="{b}棟新風機位、管帶與拒留管井比較"></a><figcaption>{b}棟：可放大SVG；框線不是施工核可。</figcaption></figure>' for b in "ABC")
    gates = "".join("<li>"+esc(n)+"</li>" for n in report["fixed_gates"])
    gaps = "".join("<li>"+esc(n)+"</li>" for n in report["open_gates"])
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ABC全熱／新風機位、管井與費用比較</title><style>
body{{margin:0;background:#f5f6ef;color:#243e40;font:17px/1.8 system-ui,sans-serif}}main{{max-width:1240px;margin:auto;padding:24px}}h1{{font-size:30px}}h2{{margin-top:34px}}a{{color:#146c76}}.warning{{border-left:6px solid #a85230;background:#fff0da;padding:14px}}.table{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:650px}}td,th{{border:1px solid #b8c4be;padding:10px;text-align:left;vertical-align:top}}th{{background:#dfe9e2}}img{{width:100%;height:auto}}figure{{margin:25px 0}}code{{word-break:break-all}}.note{{background:#e2ece6;padding:14px}}@media print{{main{{padding:0}}figure{{break-inside:avoid}}}}
</style></head><body><main><h1>ABC全熱／新風：先留得下、修得到，再選機</h1>
<p class="warning">獨立深化比較／未採用。原ABC與3D、床櫃門窗、B前後搬轎兩版及149份控制均保留。尚未選機型、台數或完整路由；不是施工、消防、照護或風水核可。</p>
<nav><a href="#choice">先看結論</a> · <a href="#positions">機位</a> · <a href="#ducts">局部管帶</a> · <a href="#cost">報價</a> · <a href="#sheets">三圖</a> · <a href="../abc-fresh-air-v1/index.html">前批人數／分區</a></nav>
<section id="choice"><h2>建議：優先深化常用層分區，集中式保留替代報價</h2><p>{esc(report['conditional_recommendation'])}</p>{shaft_table}
<p>A照護、B入口與主臥、C廚房是三個試點的實際代價。不能為了把管井塞進去自動縮掉房間或宣稱可轉位。集中機位可先比較A1／B2／C1相同乾區，但容量、實際機體及跨層幹線未核，不能當成三台即可解決。</p></section>
<section id="positions"><h2>8處機位／檢修預算，不等於採購8台</h2>{unit_table}
<p>常住層有5處候選、3F有3處使用預留；三樓已規劃使用區一期要供風，不是只留空管。全部只是含管接1600×1000×450mm試排。相同地面投影暫作檢修帶，沒有障礙不代表架梯、門扇、逃生與整機運出已可行。</p>
<p>封存尺寸例本體1230×637×220mm未選型。1260×700名義可拆面板仍未核框料、手部、公差、轉向與接口；不可當成合格孔徑，800×800小孔也不能自動證明全機可拆換。</p>
<p class="note">{esc(report['b_distribution_gap'])}</p></section>
<section id="ducts"><h2>局部密閉管帶，不是完整四管施工合圖</h2>{routes}
<p>500×300帶內兩支Ø125內徑、各側25保溫，含間距及邊緣的寬度預算剛好500mm，沒有多餘寬度。中央新井另用兩支Ø150作預算。兩管獨立，浴廁、油煙與香火不併一般回收。</p>
<p>各帶尚無完成面高度Z。C1冰箱／C2衣櫃等下方投影必須有剖面核對；C-AC01只檢查既有候選線同層XY，不是三維無碰撞。外牆OA／EA位置、防雨、防短路與合法開口完全未定；不能擅用鄰地側牆。</p></section>
<section id="cost"><h2>三棟各報三種等範圍案，未知費用不當0</h2>
<p>中央／分層／過濾新風＋有設計排出，各案同樣涵蓋關門睡房、近期使用3F、獨排補氣、濾網、噪音、維修與實測；B1香火獨立列費但不能漏報。分層可能增加機台、濾網及外牆口，中央可能增加管井、防火與跨層消音；沒有同範圍報價不宣布哪個最省。</p>
<p>10年簡算＝一次工程費＋10×（年濾網＋年人工＋年電費）＋十年換件；稅保另註。任一項未知，總額留空。不是折現評估，也沒有捏造價格或耗電。</p>
<p><a href="builder-quotes.csv">9列建商等範圍報價表</a>／<a href="service-checklist.csv">8處檢修與整機拆換回覆</a>／<a href="unit-reservations.csv">機位座標</a>／<a href="duct-corridors.csv">部分管帶</a>／<a href="flow-sensitivity.csv">風量／風速敏感度</a>。</p>
<p>25～35m³/h每人只是初估。C2一人低速工作點特別要核；大風量機器可調速不等於能在髒濾網靜壓下穩定供少量新風。全熱不當主動除濕／冷氣／香火排煙／MDF散熱。</p></section>
<section><h2>不得默默放寬的條件</h2><ul>{gates}</ul><h2>還沒完成的關卡</h2><ul>{gaps}</ul>
<p>純平面預算暫未找到床櫃／樓梯保護區交叉，不是完整可裝結論。B原兩衛面積與公衛無窗偏好仍未解，也沒有因裝新風就算接受。</p></section>
<section id="sheets"><h2>三棟局部套繪</h2>{images}</section>
<p><a href="review.json">來源／計算JSON</a>／<a href="artifact-manifest.json">輸出雜湊</a>／<a href="../../../Docs/abc-fresh-air-layout-v1.md">詳細假設與代價</a>。</p>
<small>來源 {esc(report['source_layout_report_sha256'])}<br>本批 {esc(report['report_hash'])}<br>靜態輸出；瀏覽器／WebGL未執行。法規、產品、消防、宗教及照護核可未知。</small></main></body></html>'''


def render(report):
    files = {b+"-reservations.svg": sheet(report, b) for b in "ABC"}
    files.update({"index.html": index_html(report), "unit-reservations.csv": csv_text(report["units"]),
        "duct-corridors.csv": csv_text(report["partial_corridors"]), "flow-sensitivity.csv": csv_text(report["flow_sensitivity"]),
        "builder-quotes.csv": csv_text(report["builder_quotes"]), "service-checklist.csv": csv_text(service_rows(report)),
        "review.json": json.dumps(report, ensure_ascii=False, indent=2)+"\n"})
    manifest = {"schema": "house-abc-fresh-air-layout-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "adopted": False, "product_selected": False,
        "artifacts": {n: hashlib.sha256(data.encode()).hexdigest() for n, data in files.items()}}
    files["artifact-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files, output = render(report), ROOT/OUT
        if args.check:
            stale = [n for n, data in files.items() if not (output/n).is_file() or (output/n).read_bytes() != data.encode()]
            if stale:
                raise ContractError("ERV reservation artifacts stale: "+", ".join(stale))
        else:
            output.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (output/name).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "artifacts": len(files),
            "unit_reservations": len(report["units"]), "partial_corridors": len(report["partial_corridors"]),
            "rejected_shaft_sites": len(report["central_shaft_tests"]),
            "protected_controls_unchanged": report["protected_controls_unchanged"],
            "adopted": False, "full_MEP_fit_verified": False, "browser": "not-run"}))
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

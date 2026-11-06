#!/usr/bin/env python3
"""Export owner-confirmed ABC fresh-air zoning; no 3D rebuild or browser launch."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.abc_fresh_air import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import Sheet, csv_text, table  # noqa: E402


def wrap(value, width=40):
    return textwrap.wrap(value, width=width, break_long_words=True, break_on_hyphens=False)


def system_sheet(report, b):
    bid = b["id"]
    s = Sheet(bid+"棟新風｜一二樓現在做、三樓先預留", report)
    for el in s.root:
        if el.tag.endswith("desc"):
            el.text = "本圖為系統拓樸，沒有實際風管座標、機位、尺寸或施工開孔核可。新風需求已由屋主確認。"
        if el.text and el.text.startswith("深化比較／未採用"):
            el.text = "新風需求已確認｜系統分區預案：主機台數、風量、機位、風管與工程尚待核圖。"
        if el.text and el.text.startswith("原ABC／目前3D"):
            el.text = "原ABC／3D保留；本圖為送回風分區，線條不是實際管線或風水／法規／施工通過證明。"
    s.text(f"{bid}棟已述常住{b['known_regular_people']}人；三樓人數未指定。每棟空氣系統各自獨立，不跨棟共管。", 30, 116)
    defs = s.add("defs")
    for key, color in [("supply", "#497d9b"), ("return", "#568565")]:
        marker = s.add("marker", parent=defs, id=key, markerWidth=8, markerHeight=8, refX=7, refY=4, orient="auto")
        s.add("polygon", parent=marker, points="0,0 8,4 0,8", fill=color)
    s.box([35, 350, 240, 230], fill="#dce8e2", stroke="#789688", stroke_width=2)
    s.lines([bid+"棟一般新風主機群", "ERV優先", "最低：過濾室外新風", "＋有設計的排出路徑", "台數／實機未選"], 52, 390, step=33)
    colors = {"floor-3": "#e9ece8", "floor-2": "#e1edf0", "floor-1": "#e3ecdf"}
    for n, z in enumerate(reversed(b["zones"])):
        y = 180+n*230
        f = z["floor"].split("-")[-1]
        people = "未指定人數" if z["people"] is None else f"常住{z['people']}人"
        suffix = "先留支路／電源／檢修" if z["priority"] == "rough-in-before-finishes" else "現在做可運作系統"
        s.box([350, y, 710, 205], fill=colors[z["floor"]], stroke="#94a69b")
        s.text(f"{f}F {people}｜{suffix}", 370, y+32, class_="label")
        names = "／".join(r["name"].split("（")[0].split("｜")[0] for r in z["supplied_rooms"])
        if z["supply"]:
            s.lines(wrap("送風："+names, 37), 370, y+64, step=23, class_="small")
            if z["people"] is not None:
                s.text(f"本層已述人數初估{z['people']*25}～{z['people']*35}m³/h；非選機值。", 370, y+116, class_="small")
            else:
                s.text("三樓風量未定，不視為0；客房／活動按使用調節。", 370, y+116, class_="small")
            s.lines(wrap(z["return_strategy"], 42), 370, y+145, step=23, class_="small")
            s.path([[275, 410], [305+n*8, 410], [305+n*8, y+75], [350, y+75]], stroke="#497d9b", stroke_width=2,
                stroke_dasharray="5 4" if z["people"] is None else "none", marker_end="url(#supply)")
            s.path([[350, y+190], [330+n*5, y+190], [330+n*5, 535], [275, 535]], stroke="#568565",
                stroke_width=1.5, stroke_dasharray="5 4", marker_end="url(#return)")
        else:
            s.lines(["過濾室外新風 → 香火區 → 獨立源頭排氣 → 室外", "不接一般全熱回收；補氣不可直吹神桌。", "隔煙／樓梯門關閉，補排風量與祭祀人數待核。"],
                370, y+76, step=32, class_="small")
        systems = "浴廁獨排"+("＋油煙獨排" if z["hood"] else "")
        s.lines([systems, "不與一般ERV共管", "關門轉送另核"], 1090, y+62, step=29, class_="small")
    if bid == "A":
        note = "孝親房、主臥先做有效室外送風；次臥、書房及三樓劇院／客房保留支路，隔音門不靠大門縫換氣。"
    elif bid == "B":
        note = "B1香火補排獨立，上層ERV不能當其補氣；原500×300浴室井不塞新風主幹，避完整祭祀保護區另合圖。"
    else:
        note = "C1孝親房與客餐各有乾淨回風路徑，C2常睡單人房必有送風；已接受的前置門保持可關，不借樓梯回風。"
    s.text("三樓若近期常用劇院／健身等活動，該區一期啟用；藍為送風、綠虛線為乾淨回風，非實際管路。", 30, 885, class_="small")
    s.lines(wrap(note, 72), 30, 925, step=29, class_="small")
    return s.output()


def equipment_rows(report):
    topics = [
        ("配置與台數", "每棟中央分層與常用層小機兩案，同範圍比較，B1香火另系統"),
        ("逐房送回風", "依已述人數及實際使用填常態／夜間／加強風量，關門仍成立"),
        ("靜壓與過濾", "送排兩側P-Q曲線、髒濾網工作點、過濾等級及可取得耗材"),
        ("主機與檢修", "實際外廓、檢修／抽濾網／整機拆換尺寸，避床／梯廳／照護／MDF"),
        ("管線與孔洞", "送回風主幹、消音／保溫／防火及結構核准孔位，不沿用100～150套管文字"),
        ("室外進排氣", "污染源、油煙、香火、浴廁、熱泵、鄰房與風向；不以1m示意距離直接核可"),
        ("加強補氣聯動", "浴廁／油煙／香火獨排同開時的實際補氣；壓差、門阻力及氣味流向"),
        ("高雄濕熱與夜間", "通風潛熱、冷凝、除濕、夜間噪音、CO2／溫濕度感測位置與控制"),
        ("三樓預留", "封口支路、風管／電源／可用檢修與日後啟用平衡，不只是留插座"),
        ("分項價格與交屋", "材料、安裝、開孔／封堵、濾網、調試、保固、標配折抵及後續耗材"),
    ]
    return [{"id": f"FA-BID-{i:02d}", "building": bid, "topic": topic, "required_reply": required,
        "model": None, "actual_airflow": None, "drawings_and_manual": None, "quote_twd": None, "approval": "unknown"}
        for bid in "ABC" for i, (topic, required) in enumerate(topics, 1)]


def index_html(report):
    people = table(["棟別", "1F", "2F", "常住已述合計", "25～35m³/h每人初估"], [
        ["A", "2人", "2人", "4人", "100～140m³/h"],
        ["B", "燒香；祭祀人數未定", "2人", "2人＋祭祀另核", "50～70m³/h；香火另加"],
        ["C", "2人", "1人", "3人", "75～105m³/h"]])
    balances = table(["示意工況", "室外送風", "ERV排風", "局部獨排", "額外補氣", "機械淨差m³/h"], [
        [r["label"], r["outdoor_supply_m3_h"], r["erv_to_outdoors_m3_h"],
         "未定" if r["incense_m3_h"] is None else r["local_bath_m3_h"]+r["cooking_hood_m3_h"]+r["incense_m3_h"],
         "未定" if r["additional_outdoor_makeup_m3_h"] is None else r["additional_outdoor_makeup_m3_h"],
         "無法計算" if r["mechanical_net_m3_h"] is None else r["mechanical_net_m3_h"]] for r in report["flow_cases"]])
    priorities = table(["現在做，避免日後拆裝", "設計要達到的效果"], [
        ["一、二樓常睡房各自有效送風", "房門關上、客廳感測正常時，睡房仍有換氣；C2單人房也不漏"],
        ["關門回風／消音轉送", "C前置門與樓梯門可關，不靠開門或大門縫保持風量"],
        ["完整主機及濾網拆換空間", "不放床上方、不借照護轉位或MDF、不能只留一個檢修洞"],
        ["三樓支路／主幹／電源／檢修", "先留可啟用條件，人數未指定不代表未來不用；台數仍可比較"],
        ["B1香火專屬補排與隔煙", "煙不進一般ERV回風，也不被抽向樓梯及樓上臥室"],
        ["濾網、送排平衡及濕度管理", "有全熱不等於有除濕，標示微正壓不等於獨排加強時仍有足量補氣"]])
    units = table(["方案", "比較台數，非採購數量", "好處", "代價"], [
        [r["scope"], f"初期ERV示意{r['initial_erv_count_illustrative']}台；B1獨立補排及浴廁另計", r["benefit"], r["risk"]]
        for r in report["units_comparison"]])
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ABC全熱／新風｜常睡樓層與香火整合</title>
<style>body{{font:17px/1.75 system-ui,sans-serif;color:#283e46;background:#f5f8f3;margin:0}}main{{max-width:1180px;margin:auto;padding:25px 20px 65px}}section{{background:#fff;border:1px solid #d7e1d6;padding:24px;margin:26px 0;border-radius:10px}}h1{{font-size:29px}}h2{{font-size:23px}}a{{color:#17687d}}a:focus-visible{{outline:3px solid #ac7035;outline-offset:3px}}nav{{display:flex;gap:16px;flex-wrap:wrap}}.notice{{padding:17px;background:#e4efdf;border-left:5px solid #66875d}}.pending{{padding:17px;background:#fff1de;border-left:5px solid #ae6e32}}.table{{overflow:auto}}table{{width:100%;min-width:650px;border-collapse:collapse;font-size:15px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #dbe2d7;vertical-align:top}}th{{background:#edf2e9}}img{{max-width:100%;height:auto;display:block;margin:18px auto}}small{{font-size:14px}}code{{overflow-wrap:anywhere}}</style></head><body><main>
<h1>ABC都納入全熱交換；最低也要有可運作的新風系統</h1>
<p class="notice"><strong>屋主已確認通風需求及一、二樓已述常住人數。</strong> 三棟各自獨立，全熱交換優先；若採新風機備案，仍要有過濾室外進氣、逐房分配、關門回風／轉送及設計好的排出路徑。</p>
<p class="pending">這次確認沒有擴大為採用現有格局、無窗公衛、縮小面積或指定機型。主機位置、實際風量／靜壓、台數、風管、孔位與工程仍待核；原ABC及3D保留。</p>
<nav><a href="#people">人數與風量</a><a href="#regret">最值得現在做</a><a href="#zones">三棟分區圖</a><a href="#balance">補氣要重算</a><a href="#equipment">配置與建商回覆</a></nav>
<section id="people"><h2>先做常睡的一、二樓，三樓保留未來條件</h2>{people}
<p>25／30／35m³/h每人是本輪初估比較假設，<strong>不是法定風量或選機值</strong>；還要核背景通風、訪客／三樓活動、局部獨排補氣、髒濾網與實際管路靜壓。A二樓2人是整層，不在主臥、次臥、書房各重複加2人。</p>
<p>白天A四人或C三人集中客餐時，新風需能分配到使用區；夜間轉向各睡房。已述同一批人不能在每個房間再重複累加，但客房／劇院／運動的額外來客尖峰要另核。B一樓香火通風不能由樓上2人的初估代替。</p></section>
<section id="regret"><h2>不裝、或只留插座，最可能後悔的地方</h2>{priorities}
<p>預算有限時，先保住已經常睡的房間、新風可到達、關門回風、B香火分管及實際檢修；三樓先做封口支路與可用空間。主機可以比較配置，結構／風管／檢修條件留錯，裝潢後補做更容易影響房間與照護動線。</p>
<p>三樓若劇院、閱讀、健身或客房近期就會常用，該區須一期啟用；不常睡人不等於可以沒有通風。「先預留」只適用尚未使用的區域，不是建議已使用時只留管。</p></section>
<section id="zones"><h2>三棟各自送回風，不跨棟共用空氣</h2><p>這三張是系統分區圖，線條沒有對應實際房屋風管座標，不能當成已完成路由或機房已放得下。</p>
<p><a href="A-system.svg">A棟</a>／<a href="B-system.svg">B棟</a>／<a href="C-system.svg">C棟</a>／<a href="zone-schedule.csv">逐層房間與人數表</a></p>
<img src="A-system.svg" width="1400" height="1100" alt="A一二樓各2人，客餐孝親與主臥等獨立供氣，三樓劇院與客房先預留">
<img src="B-system.svg" width="1400" height="1100" loading="lazy" alt="B一樓香火專屬過濾補氣與獨排，不進一般全熱；二樓2人睡房供氣，三樓保留支路">
<img src="C-system.svg" width="1400" height="1100" loading="lazy" alt="C一樓2人與二樓1人睡房獨立送回風，前置門保持可關，三樓主臥與運動支路先預留"></section>
<section id="balance"><h2>有全熱，浴室補氣仍然要計算</h2>{balances}
<p>平衡ERV送120、排120，本身不提供額外120給浴室獨排；若只多送10，浴室仍可能缺110。上述是機械風量差，<strong>不能直接換算壓差，也不證明零差就已平衡或空氣品質合格</strong>。新風機只送不排也需要明確的排出路徑，不能依賴未知漏風。</p>
<p>本案將一般ERV乾淨回風、浴廁獨排、油煙及B香火分管。這是本案保守系統條件，並非宣稱所有品牌ERV都不能接浴室；具體可接場所仍依實際安裝手冊。香火排氣及油煙不接一般ERV回收。</p>
<p>B棟原400×200補氣構造未定案：新風提供氣源，但進浴室的門內轉送／阻視／聲學仍要核。原500×300井只預算兩條浴室排氣，沒有容納ERV送回風主幹或主機。全熱不得借神明堂乾背櫃保護室當主機房，機位與新主幹另合圖。</p>
<p>C棟維持前置門可關；孝親房與客餐各自有乾淨回風路徑，不用開樓梯門補氣。後段小廚房及浴廁有自己的獨排，不能把味道送回睡房。</p></section>
<section id="equipment"><h2>請建商同範圍報兩案，現在不鎖死台數</h2>{units}
<p>原A圖說的品牌與Ø100～150mm套管只是舊文字預留。官方薄型產品例的本體長約1.23m，還要有抽濾網、管接與整機搬出空間；不能因房子有一個孔，就認定全熱已放得下。那個產品只作尺寸參考，未選型。</p>
<p>高雄濕熱季節，全熱回收能量也不等於主動除濕；仍要計室外含濕量、空調潛熱、保溫冷凝與必要除濕。睡房CO2不能只靠客廳回風感測，PM2.5／濾網、夜間風噪與關門實測也要一起核。</p>
<p>MDF／IDF的設備散熱仍是獨立負荷，新風或全熱不當冷氣；電機櫃也不拿來作其他房間的補氣或回風通道。</p>
<p><a href="building-system-reply.csv">三棟同範圍建商回覆表</a>／<a href="commissioning.csv">關門、夜間及同時排風驗收表</a>／<a href="balance-cases.csv">風量差示意數據</a>／<a href="review.json">分區與來源</a>／<a href="../../../Docs/abc-fresh-air-v1.md">完整說明</a>／<a href="../b-ventilation-detail-v1/index.html">原B排濕工程預案</a>。</p>
<p>參考：<a href="https://bsesc.energy.gov/energy-basics/hvac-whole-house-ventilation-0">DOE通風系統原理</a>、<a href="https://basc.pnnl.gov/resource-guides/ventilation-and-exhaust-strategies-multifamily-housing">PNNL送排與補氣</a>、<a href="https://www.alaska.com.tw/thin-housing-erv">生原官方薄型產品／安裝提醒</a>。外國資料只作原理參考，不當本案台灣法規。</p></section>
<small>2026-11-06｜來源 <code>{html.escape(report['source_layout_report_sha256'])}</code><br>本批 <code>{html.escape(report['report_hash'])}</code>｜通風需求已確認，尚未選型或取得施工／風水核可；未執行瀏覽器或WebGL。</small>
</main></body></html>'''


def render(report):
    zone_rows = [{"building": b["id"], "floor": z["floor"], "known_regular_people": z["people"], "priority": z["priority"],
        "supply_rooms": [r["id"] for r in z["supplied_rooms"]], "return_strategy": z["return_strategy"],
        "night_estimate_cases": z["night_supply_estimate_cases"], "actual_supply_m3_h": None,
        "actual_route_and_closed_door_test": None, "enable_when_used": z.get("enable_when_used"), "constraints": z["constraints"]}
        for b in report["buildings"] for z in b["zones"]]
    files = {b["id"]+"-system.svg": system_sheet(report, b) for b in report["buildings"]}
    files.update({"index.html": index_html(report), "zone-schedule.csv": csv_text(zone_rows),
        "building-system-reply.csv": csv_text(equipment_rows(report)), "commissioning.csv": csv_text(report["commissioning"]),
        "balance-cases.csv": csv_text(report["flow_cases"]), "review.json": json.dumps(report, ensure_ascii=False, indent=2)+"\n"})
    manifest = {"schema": "house-abc-fresh-air-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "new_requirement_owner_confirmed": True, "layout_or_product_adopted": False,
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
                raise ContractError("ABC fresh-air artifacts stale: "+", ".join(stale))
        else:
            output.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (output/name).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported-fresh-air-basis", "artifacts": len(files),
            "known_regular_people": report["known_regular_people_total"], "floor_zones": 9,
            "protected_controls_unchanged": report["protected_controls_unchanged"], "owner_requirement_confirmed": True,
            "layout_or_product_adopted": False, "browser": "not-run"}))
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

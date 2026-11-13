#!/usr/bin/env python3
"""Export bounded B same-revision vector plans and future-scene input; no rendering."""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import sys
import textwrap
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shapely.geometry import Polygon  # noqa: E402

from house_design.b_upper_storage_sync import ARCHIVE, OUT, build  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_upper_replan import Draw  # noqa: E402
from scripts.export_builder_communication import page  # noqa: E402


class Sheet:
    def __init__(self, title, report, height=1320):
        self.root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": f"0 0 1400 {height}",
            "width": "1400", "height": str(height), "role": "img", "aria-label": title})
        self.add("title", text=title)
        self.add("style", text="text{font-family:system-ui,sans-serif;fill:#263e49}.small{font-size:13px}.room{font-size:12px}")
        self.add("rect", x=0, y=0, width=1400, height=height, fill="#fafbf8")
        self.text(title, 28, 40, font_size=26, font_weight=700)
        self.text("B同版底圖／未採用｜保原P4／Q3多邊形、設備及兩入口；只比儲藏，不把完整梯核鋪成實心樓板。", 28, 76)
        self.text("橙：新增／桌下儲藏；橙虛線：取物帶。綠：列明到達地面；紅虛線：梯井或天井，不得封滿。", 28, 106)
        self.text("來源 "+report["report_hash"], 28, height-42, class_="small")
        self.text("只核列明2D投影；不是新3D、整座梯淨高、實際門片、風水、聲學、結構、法規或施工核可。", 28, height-18, class_="small")

    def add(self, tag, text=None, **attrs):
        node = ET.SubElement(self.root, tag, {k.replace("_", "-"): str(v) for k, v in attrs.items()})
        node.text = text
        return node

    def text(self, text, x, y, **attrs):
        return self.add("text", text=text, x=x, y=y, font_size=attrs.pop("font_size", 16), **attrs)

    def output(self):
        return ET.tostring(self.root, encoding="unicode")+"\n"


def plan_sheet(report, floor, state):
    legends = [str(n)+"｜"+i["label"]+"｜平面"+"×".join(f"{v:g}" for v in i["rect_mm"][2:])+"mm"
        +("；高"+str(i["height_mm"])+"mm（提案）" if i.get("storage_case") else "") for n, i in enumerate(state["objects"], 1)]
    legends += ["預留｜"+r["label"] for r in floor["fixed"]]
    lines = [line for value in legends for line in textwrap.wrap(value, 45)]
    s = Sheet(floor["key"]+"｜"+state["label"]+"｜標高+"+str(floor["base_mm"])+"mm", report, max(1320, 500+len(lines)*25))
    d = Draw(s, (45, 150), .052)
    d.box([0, 0, 6000, 17630], fill="#eef0e7", stroke="#607c73")
    for room in floor["rooms"]:
        fill = "#dceff4" if room.get("kind") == "wet" else "#f2e1d9" if room["id"] == "dry-protection" else "#edf0e9"
        d.poly(room["polygon_mm"], fill=fill, stroke="#607c73", stroke_width=.9, data_room_id=room["id"])
        centre = Polygon(room["polygon_mm"]).representative_point()
        name = {"quiet-living": "安靜起居", "dry-protection": "乾背保護", "front-entertainment": "Q3 L形KTV",
            "front-platform": "RF前平台", "stair": "梯核（不可鋪滿）"}.get(room["id"], room["label"][:6])
        s.text(name, *d.point([centre.x, centre.y]), text_anchor="middle", font_size=11)
        for door in room["doors"]:
            d.line(door["a"], door["b"], stroke="#00a3bb", stroke_width=3)
        for window in room.get("windows_mm", []):
            d.line(window[:2], [window[0]+window[2], window[1]], stroke="#164fce", stroke_width=3)
    for fixed in floor["fixed"]:
        d.box(fixed["rect_mm"], fill="none", stroke="#777d8c", stroke_dasharray="3 2")
    stair = floor["stair_interface"]
    if floor["id"] == "floor-4":
        for p in floor["protected_polygons_mm"]:
            d.poly(p, fill="#efd9d1", fill_opacity=.65, stroke="#ba897d", stroke_dasharray="4 3")
        for p in stair["arrival_polygons_mm"]:
            d.poly(p, fill="#b8d4af", stroke="#4d7a50", stroke_width=1.3)
        d.box(stair["stairwell_keep_open_mm"], fill="#fafbf8", stroke="#ad493b", stroke_dasharray="5 3")
        d.box(floor["roof_opening_mm"], fill="#d7edf3", stroke="#ad493b", stroke_dasharray="5 3")
        for p in floor["roof_guard_polygons_mm"]:
            d.poly(p, fill="#b89965")
        for key in ["front_door", "side_door"]:
            door = floor["source_roof_option"][key]
            d.line(door["a"], door["b"], stroke="#00a3bb", stroke_width=3)
    else:
        d.poly(stair["arrival_polygon_mm"], fill="#b8d4af", stroke="#4d7a50", stroke_width=1.3)
        for step in stair["incoming_treads"]:
            d.box(step["rect_mm"], fill="none", stroke="#aa7d69", stroke_width=.5)
        if floor["id"] == "floor-2":
            route = stair["transfer_route_mm"]
            for a, b in zip(route, route[1:], strict=False):
                d.line(a, b, stroke="#3c7180", stroke_dasharray="4 3")
            for slider in floor["front_service"]["sliders"]:
                d.line(slider["a"], slider["b"], stroke="#00a3bb", stroke_width=3)
        else:
            for key in ["front", "side", "rear_opening"]:
                door = floor["door_interfaces"][key]
                d.line(door["a"], door["b"], stroke="#00a3bb", stroke_width=3)
            for slider in floor["door_interfaces"]["sliders"]:
                d.line(slider["a"], slider["b"], stroke="#00a3bb", stroke_width=3)
    for n, item in enumerate(state["objects"], 1):
        is_storage = bool(item.get("storage_case"))
        if is_storage:
            d.box(item["operation_mm"], fill="none", stroke="#b75916", stroke_dasharray="4 3")
        d.box(item["rect_mm"], fill="#f6bd69" if is_storage else "#b8cabd", stroke="#a74e19" if is_storage else "#446952",
            stroke_width=1.4 if is_storage else .7, data_item_key=item["key"], data_storage_case=item.get("storage_case", ""))
        r = item["rect_mm"]
        s.text(str(n), *d.point([r[0]+r[2]/2, r[1]+r[3]/2]), text_anchor="middle", font_size=11)
    s.text("道路／前方 ↑", 45, 132)
    s.text("6000×17630mm＝105.78㎡研究地坪框；不是每層可建量", 45, 1100, font_size=12)
    s.text("本層資料與圖例", 430, 155, font_size=21, font_weight=700)
    notes = [floor["storage"]["note"]]
    if floor["id"] == "floor-2":
        notes += ["P4房界與前公衛／茶水、乾背區保留；上層梯用Q3，二樓到達只能用來源L形平地，不把新平台全寬鋪滿。前排水與騎樓淨高仍待核。"]
    elif floor["id"] == "floor-3":
        notes += ["完整保Q3 L形KTV及後客房、公衛、工作天井；20.1889㎡只對來源厚度／井包／機櫃預算，仍需聲學、結構及關門新風。"]
    else:
        notes += ["D1／D2各沿自己的桌位改下櫃，不另畫舊桌；設備與檢修預留不縮。RF24㎡目標仍未達，前室不算戶外平台。"]
    y = 188
    for note in notes:
        for line in textwrap.wrap(note, 45):
            s.text(line, 430, y)
            y += 25
        y += 10
    s.text("物件編號／完整品名（均沿本版）", 430, y+10, font_size=20, font_weight=700)
    y += 45
    for line in lines:
        s.text(line, 430, y, font_size=15)
        y += 25
    return s.output()


def stair_sheet(report):
    s = Sheet("B上下層接口｜2F L形到達、3F Q3與RF梯井", report, 1500)
    for col, floor in enumerate([report["floors"][0], report["floors"][1], report["floors"][2]]):
        d = Draw(s, (35+col*455, -430), .13)
        st = floor["stair_interface"]
        d.box([0, 3900, 2400, 5200], fill="#edf0e9", stroke="#607c73")
        for step in st["incoming_treads"]:
            d.box(step["rect_mm"], fill="none", stroke="#a2755e", stroke_width=.7)
        for p in st.get("arrival_polygons_mm", [st.get("arrival_polygon_mm")]):
            d.poly(p, fill="#b8d4af", stroke="#4d7a50", stroke_width=1.5)
        if st.get("stairwell_keep_open_mm"):
            d.box(st["stairwell_keep_open_mm"], fill="none", stroke="#ad493b", stroke_width=2, stroke_dasharray="5 3")
        s.text(floor["key"]+"｜+"+str(floor["base_mm"])+"mm", 35+col*455, 145, font_weight=700)
    y = 845
    notes = ["2F：一樓原24級梯不改；二樓新到達用L形來源多邊形，900mm指定轉接線在列明地面內。若誤鋪2200×1000新全寬平台，會壓到一樓上來的right-9／10／11。局部200mm板厚假設不是全梯淨高核可。",
        "3F：承接二樓Q3的18級／270mm踏面上層梯，後移800mm，折返平台1900縮至1100mm。L形KTV房界、前門及側門位置各保自己的來源，不能拿舊矩形房間或舊平台套用。",
        "RF：到達平台2200×1000、乾前室2170×755及列明門檻合用；只鋪這些地面，後梯井2200×3260保持開口，不蓋三樓上來16個列明踏步。RF側門y4400與3F側門y5270是不同層。",
        "本批是同版平面／標高與未來場景輸入，不是新3D畫面或專業簽證；梁板、扶手、實際門片、整段淨高、防火、救援與屋突資格仍待資料。"]
    for note in notes:
        for line in textwrap.wrap(note, 80):
            s.text(line, 35, y)
            y += 27
        y += 18
    return s.output()


def render(report):
    files = {state["plan_file"]: plan_sheet(report, floor, state) for floor in report["floors"] for state in floor["states"]}
    files["stair-interfaces.svg"] = stair_sheet(report)
    files["storage-schedule.csv"] = csv_text([{"棟層版本": f["key"], "品名": f["storage"]["label"],
        "平面mm": "×".join(map(str, f["storage"]["rect_mm"][2:])), "高mm（提案）": f["storage"]["height_mm"],
        "額外占地㎡": f["storage_review"]["additional_floor_footprint_sqm"], "保留與代價": f["storage"]["note"]}
        for f in report["floors"]])
    files["assembly-references.csv"] = csv_text([{"組合ID": a["id"], "一樓入口": a["ground_entry"], "一樓使用": a["ground_use"],
        "收納狀態": a["storage_state"], "上層來源": "／".join(a["floors"]), "採用或專業核可": "尚無"} for a in report["assemblies"]])
    body = '<h1>B上層同版底圖與逐層收納</h1><p class="note">P4二樓、Q3三樓及兩個RF版本的獨立同版資料。後門搬轎預設／前門備案均保留，未覆寫原ABC或已驗收3D；尚未採用。</p>'
    body += '<p>先看<a href="stair-interfaces.svg">上下層樓梯／平台／梯井接口</a>，再比下面各層原配置與加櫃。兩個RF方案互斥，不把面積、設備或櫃體相加。原目標RF24㎡仍有缺口。</p>'
    body += '<p>這輪完成的是同版底圖及未來3D輸入；沒有產生新3D或啟動瀏覽器。原有A／C比較的passed不套到本批。</p>'
    for f in report["floors"]:
        body += '<section><h2>'+html.escape(f["key"]+'｜'+f["storage"]["label"])+'</h2><p>'+html.escape(f["storage"]["note"])+'</p>'
        body += '<p>'+"／".join('<a href="'+s["plan_file"]+'">'+html.escape(s["label"])+'</a>' for s in f["states"])+'</p>'
        body += '<img style="width:100%;height:auto" src="'+f["states"][1]["plan_file"]+'" alt="'+html.escape(f["key"]+'同版加櫃平面', quote=True)+'"></section>'
    body += '<h2>兩個一樓入口，各保留三種使用狀態</h2>'+table(["入口", "狀態", "保留方式"],
        [[o["id"], "／".join(s["id"] for s in o["states"]), "原floor-1資料與hash逐項留在review.json；本批不更動一樓格局或搬運路線"] for o in report["entry_options"]])
    k = report["known_limits"]
    body += '<h2>沒有因加櫃而解掉的問題</h2>'+table(["項目", "本輪狀態"], [
        ["地坪／可建量", "6000×17630mm＝105.78㎡研究框；約32地坪不代表每層可建量"],
        ["Q3 KTV", str(k["KTV_source_budget_sqm"])+"㎡是指定厚度與機櫃預算；聲學、樓板、設備與關門通風待核"],
        ["RF24㎡", "未扣設備的樂觀上界"+str(k["RF_optimistic_before_equipment_sqm"])+"㎡，仍少"+str(k["RF_known_shortfall_before_equipment_sqm"])+"㎡；未接受縮目標"],
        ["P4排水", "完整支管、偏移、1F梯核落水與騎樓淨高未解，不因同版合圖視為完成"],
        ["梯／門／屋突", "新L形到達與RF平台／前室是待核條件，沒有整段淨高、結構、防火、搬運或法規核可"]])
    body += '<p><a href="storage-schedule.csv">四版收納表</a>／<a href="assembly-references.csv">24組獨立版本對照</a>／<a href="review.json">完整同版資料與來源</a></p>'
    files["index.html"] = page("B上層同版底圖與收納", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["README.md"] = "# B上層同版底圖與逐層收納\n\n開[index.html](index.html)。P4二樓、Q3三樓、RF D1／D2分開對照原配置與收納；後門／前門及日常／祭祀／搬運狀態各保原來源。\n\n這是靜態向量與未來3D輸入，不是新3D或可施工圖。原RF24㎡缺口、P4排水與各專業待核仍保留。原ABC及兩份已驗收收納ZIP未改。\n"
    files = {n: value.encode() for n, value in files.items()}
    files["artifact-manifest.json"] = (json.dumps({"schema": "house-b-upper-storage-sync-artifacts-v1",
        "report_hash": report["report_hash"], "source_hashes": report["source_hashes"],
        "rendered_qa": "not-run", "artifacts": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}},
        ensure_ascii=False, indent=2)+"\n").encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    names = sorted(files)
    files[ARCHIVE] = stream.getvalue()
    files["archive-manifest.json"] = (json.dumps({"schema": "house-b-upper-storage-sync-archive-v1",
        "archive": ARCHIVE, "sha256": hashlib.sha256(files[ARCHIVE]).hexdigest(), "archive_contains": names}, indent=2)+"\n").encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files = render(report)
        target = ROOT/OUT
        if args.check:
            if any(not (target/n).is_file() or (target/n).read_bytes() != b for n, b in files.items()):
                raise ValueError("B upper storage synchronization is stale")
        else:
            target.mkdir(parents=True, exist_ok=True)
            for n, b in files.items():
                (target/n).write_bytes(b)
        print(json.dumps({"status": "checked" if args.check else "exported", **report["summary"],
            "files": len(files), "protected_controls": report["protected_controls_unchanged"],
            "main_3d_changed": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

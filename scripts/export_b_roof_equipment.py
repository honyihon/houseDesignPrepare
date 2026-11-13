#!/usr/bin/env python3
"""Export static B RF reservations; received dimensions write only to a new private folder."""
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

from house_design.b_roof_equipment import OUT, build  # noqa: E402
from house_design.b_upper_replan import door, rect  # noqa: E402
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
        self.text("獨立RF預留／未採用｜非選機、機身容量或完整管路核可。原ABC／3D、天井與B前後門方案保留。", 28, 76)
        self.text("本批 "+report["report_hash"], 28, 1158, class_="small")
        self.text("只有指定幾何及條件回算，實際樓梯到達、產品、結構、風水、聲音與施工未知；未跑瀏覽器／WebGL。", 28, 1182, class_="small")


def roof_sheet(report, option):
    s = Sheet(option["title"]+"｜屋頂設備與前平台同圖", report)
    d = Draw(s, (45, 145), .052)
    d.box([0, 0, 6000, 17630], fill="#eef0e7", stroke="#607c73")
    for p in report["protected_polygons_mm"]:
        d.poly(p, fill="#f1ded6", stroke="#b88b7a", fill_opacity=.7)
    for p in option["front_activity_polygons_mm"]:
        d.poly(p["outer"], fill="#d4e5b9", stroke="#708738", stroke_width=.5)
        for hole in p["holes"]:
            d.poly(hole, fill="#eef0e7")
    d.box(report["stair_mm"], fill="#d2d9e0", stroke="#66758b")
    d.box(report["R1_reference"]["rf_retained_strip_mm"], fill="#b8c9b5", stroke="#537b51")
    d.box(report["R1_reference"]["rf_opening_mm"], fill="#c8dce4", stroke="#217eac", stroke_width=1.5)
    for p in report["R1_reference"]["rf_guard_polygons_mm"]:
        d.poly(p, fill="#bd8f56")
    for item in option["reservations"]:
        fill = "#cbd7c1" if item["kind"] == "wet-equipment" else "#d3d0df" if item["kind"] in {"air-zone", "pipe-zone"} else "none"
        d.box(item["rect_mm"], fill=fill, stroke="#786749", stroke_dasharray="4 3")
        if item.get("body_mm"):
            d.box(item["body_mm"], fill="#b2c6b7", stroke="#486650")
    d.box(report["guest_bed_mm"], fill="none", stroke="#a74d4d", stroke_dasharray="6 3", stroke_width=1.2)
    for r in option["inspection_routes"]:
        for a, b in zip(r["points_mm"], r["points_mm"][1:], strict=False):
            d.line(a, b, stroke="#277c79", stroke_width=1.3, stroke_dasharray="4 3")
    for a, b in zip(report["config"]["daily_front_route_mm"], report["config"]["daily_front_route_mm"][1:], strict=False):
        d.line(a, b, stroke="#8b6526", stroke_width=2)
    spec = report["config"]["proposed_RF_front_door"]
    d.line(spec["a"], spec["b"], stroke="#d4833a", stroke_width=4)
    d.poly(list(door(spec, 90).exterior.coords), fill="#d7b28e", stroke="#805534", stroke_width=.7)
    s.text("前側道路／綠色僅平台面積上界", 45, 130, class_="small")
    s.text("後冷氣移到右側；紅虛線為3F客床投影", 45, 1090, class_="small")
    y = 145
    text = [f"扣設備／門後的前開放輪廓{option['front_open_outline_including_shared_walkways_sqm']:.4f}㎡（含共用通行）；再扣700試線餘{option['front_activity_upper_bound_after_explicit_reservations_sqm']:.4f}㎡。兩種口徑都非完整淨平台，未達原24㎡目標。",
        "粉紅保護投影不放設備或作日常曬衣，後側只留必要巡檢。RF側門不能自動當日常通路，橘色另比RF前門；樓梯／門片與消防仍未知。",
        "後水塔／泵浦至少3㎡、熱泵2.5㎡作整組預留，不是已選產品；形狀與維修方向需真實包絡回套。",
        "原B-AC03／04機身900×350保留身分尺寸、移到後右公共到達上方；前兩代表槽不是已定兩台新購。所有管路及聲音重核。",
        "兩個出口協調區與400後污水通氣井分開。浴廁空氣、污水、雨水、香火及一般新風不混管；完整支管與出口容量未知。",
        f"水塔至後井平面距離{option['tank_to_rear_soil_vent_plan_gap_mm']:.0f}mm；只算兩個包絡，不能當原廠檢修空間。額外100／200mm敏感度另列JSON。",
        "700方塊從RF側門外指定點起算，對未知水塔／熱泵只到預留區邊緣。沒有驗整機拆運、原梯段、荷重、防颱或實際操作。",
        "三樓天井輪廓4.123㎡、RF洞2.639㎡維持；沒有借此解除二樓更衣乾區上方防水、KTV20與P3排水缺口。"]
    for value in text:
        y = s.paragraph(value, 445, y, width=48, step=23)
    return s.output()


def fresh_air_sheet(report, root):
    s = Sheet("B新風介面｜同尺寸轉回乾區，屋頂只留必要室外接口", report)
    service = json.loads((root/report["config"]["service_report"]).read_text())
    parent = json.loads((root/report["config"]["parent_report"]).read_text())
    for index, (item, floor) in enumerate(zip(report["indoor_fresh_air_interfaces"], [service["floors"][0], parent["floor3_reference"]], strict=True)):
        ox = 40+index*450
        d = Draw(s, (ox, -615), .07)
        for room in floor["rooms"]:
            from shapely.geometry import Polygon
            part = Polygon(room["polygon_mm"]).intersection(rect([0, 11370, 6000, 6260]))
            if part.area == 0:
                continue
            fill = "#dceff4" if room["kind"] == "wet" else "#f1ded6" if room["id"] == "dry-protection" else "#edf0e9"
            d.poly(list(part.exterior.coords), fill=fill, stroke="#607c73", stroke_width=.7)
            for furniture in room["items"]:
                d.box(furniture["rect_mm"], fill="#cbd5c8", stroke="#758372", stroke_width=.5)
        d.box(item["old_rect_mm"], fill="none", stroke="#b3504c", stroke_width=2, stroke_dasharray="6 4")
        d.box(item["rotated_candidate_mm"], fill="#b1d6cb", fill_opacity=.8, stroke="#267d6a", stroke_width=2)
        s.text(item["id"]+"｜"+("2F主臥入口乾區" if index == 0 else "3F公共到達乾區"), ox, 140, class_="room")
        s.text("紅：舊位碰浴室0.25㎡；綠：同尺寸旋轉候選", ox, 665, class_="small")
    y = 145
    for text in ["1600×1000mm整組預算維持，不縮機身、不進乾保護室或床上；只是候選天花投影，沒有占掉地面作機房。",
        "450mm厚度是舊試排預算，梁下、天花、管接、吊架與防振未核；不能當有實際安裝淨高。",
        "濾網側抽／整機下放會占通路，架梯、暫時清空與安全通行要另核；機位乾區算術容納不等於檢修可用。",
        "一樓香火專用補排不進一般ERV；浴廁／污水通氣與一般新風室外口也不共管。",
        "前後OA／EA備案保留。熱泵／污氣／香火回吸需實際Z、風向、距離與排放依據，不在本圖畫已合法共壁開口。",
        "三樓新前KTV仍需專支、回風及消音，原前閱讀的路由不能直接算已服務KTV；不鎖一層一機或購買台數。"]:
        y = s.paragraph(text, 970, y, width=23, step=22)
    y = 755
    for text in ["本圖對應新版P3／Q2局部乾區，原新風研究及條件工具保留；不同版本的路線長度、壓損與風機工作點不能混用。",
        "新風主機優先室內分區，RF試排未增加一台戶外ERV。實際廠商若提屋頂式機組，需要另列全戶外機身、保溫防雨、維修及乾淨風管，不用空白屋頂當已留足。",
        "本輪無真實設備資料；條件模板僅能回算預留包絡，其他氣流、結構、宗教及產品關卡仍未知。"]:
        y = s.paragraph(text, 40, y, width=72, step=23)
    return s.output()


def render(report, root=ROOT):
    files = {o["id"]+".svg": roof_sheet(report, o) for o in report["options"]}
    files["fresh-air-interfaces.svg"] = fresh_air_sheet(report, root)
    files["equipment-reservations.csv"] = csv_text([{"方案": o["id"], "ID": i["id"], "用途": i["label"], "x_mm": i["rect_mm"][0], "y_mm": i["rect_mm"][1],
        "預留寬mm": i["rect_mm"][2], "預留深mm": i["rect_mm"][3], "實際所需完整包絡": "", "型號與來源圖號": "", "屋主採用": "", "專業核可": ""} for o in report["options"] for i in o["reservations"]])
    files["program-ledger.csv"] = csv_text([{"原ID": r["id"], "原目標㎡": r["target_sqm"], "原下限㎡": r["min_sqm"], "原狀態": r["original_status"],
        "完整功能與法規核可": "未知", "已減需求或採用": "否"} for r in report["original_RF_requirements"]])
    files["condition-checks.csv"] = csv_text([{"方案": r["option"], "ID": r["id"], "所需包絡mm": json.dumps(r["required_envelope_mm"]),
        "預留mm": json.dumps(r["reserved_envelope_mm"]), "數值狀態": r["status"], "專業核可": "未知"} for r in report["condition_evaluations"]])
    files["engineering-replies.csv"] = csv_text([{"問題ID": f"BRF-{n:02d}", "待核": text,
        **dict.fromkeys(["同版資料圖號", "專業回覆", "費用工期代價", "負責窗口", "期限", "屋主選擇", "審查及發行依據"], "")} for n, text in enumerate(report["config"]["limits"], 1)])
    files["conditions-template.json"] = json.dumps(report["condition_template"], ensure_ascii=False, indent=2)+"\n"
    body = '<h1>B屋頂設備、曬衣與新風介面</h1><p class="note">獨立預留比較／未採用。原24㎡RF活動曬衣、三樓4㎡工作陽台及家規均保留。原ABC／3D、R0／R1／R2與搬轎版本不變。</p>'
    body += '<p>'+html.escape(report["conclusion"])+"</p>"
    body += table(["方案", "扣設備／門的開放輪廓㎡（含通行）", "再扣700試線的餘塊㎡", "原24㎡目標", "水塔到後井mm"], [[o["title"], f"{o['front_open_outline_including_shared_walkways_sqm']:.4f}", f"{o['front_activity_upper_bound_after_explicit_reservations_sqm']:.4f}", "仍缺", f"{o['tank_to_rear_soil_vent_plan_gap_mm']:.0f}"] for o in report["options"]])
    body += '<p>兩種口徑都可能含狹長、不連續餘塊，並非完整平台淨面積；再扣試線是另看專用晾衣餘量，並非宣稱法規禁止通路算面積。RF前帶名義23.4㎡本來就比24少0.6㎡，沒有借後保護區或三樓天井湊足，也沒有把10㎡下限當已接受縮需求。</p>'
    body += '<p>原後冷氣在新版3F客床上方合計0.2652㎡投影；本批移開比較。舊B2／B3新風各有0.25㎡碰新版浴室，另比同尺寸轉回室內乾區，未選機或保證聲音／天花／檢修。</p>'
    for name, title in [(o["id"]+".svg", o["title"]) for o in report["options"]]+[("fresh-air-interfaces.svg", "新風乾區與室外接口")]:
        body += f'<section><h2>{html.escape(title)}</h2><p><a href="{name}">開啟向量圖</a></p><img style="width:100%;height:auto" src="{name}" alt="{html.escape(title)}"></section>'
    body += '<h2>固定位置包絡敏感度</h2>'+table(["方案", "每邊額外mm", "超出預留屋頂", "碰其他包絡"], [[o["id"], str(c["extra_each_edge_mm"]), ", ".join(c["outside_surface"]) or "無列明衝突", "; ".join(p["a"]+"／"+p["b"] for p in c["pair_overlaps"]) or "無列明衝突"] for o in report["options"] for c in o["sensitivity"]])
    body += '<h2>實際資料後回套</h2><p>每個所需包絡要含機身、通風、檢修與接管，附來源圖號；未知留null。模板綁當前config雜湊，有資料只輸出到新私人目錄，不改公開預設。數值相容也不等於專業核可。</p>'
    body += table(["方案", "ID", "數值狀態"], [[r["option"], r["id"], r["status"]] for r in report["condition_evaluations"]])
    body += '<h2>仍需完整核對</h2>'+ul(report["config"]["limits"])
    body += '<p>'+"／".join(f'<a href="{n}">{n}</a>' for n in files if n.endswith(".csv") or n == "conditions-template.json")+'</p><p><a href="review.json">完整來源與幾何</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>本批 '+report["report_hash"]+'；未取得結構、風水、通風、聲音或施工核可，未跑瀏覽器／WebGL。</small>'
    files["index.html"] = page("B屋頂設備與新風介面", body)
    files["review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema": "house-b-roof-equipment-artifacts-v1", "report_hash": report["report_hash"], "source_hashes": report["source_hashes"],
        "adopted": False, "artifacts": {n: hashlib.sha256(v.encode()).hexdigest() for n, v in files.items()}}, ensure_ascii=False, indent=2)+"\n"
    return files


def private_path(root, value, new=False):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or path.parts[:2] != ("inputs", "private") or len(path.parts) < 3:
        raise ContractError("Received RF conditions and results must stay under inputs/private")
    target = (root/path).resolve()
    if not target.is_relative_to((root/"inputs/private").resolve()) or not target.is_relative_to(root.resolve()):
        raise ContractError("RF private path escapes through a symlink")
    if new and target.exists():
        raise ContractError("RF result folder already exists; choose a new folder")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--conditions")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        if bool(args.conditions) != bool(args.output) or args.check and args.conditions:
            raise ContractError("Use conditions with a new private output; --check is for the public baseline")
        document = json.loads(private_path(ROOT, args.conditions).read_text(encoding="utf-8")) if args.conditions else None
        out = private_path(ROOT, args.output, new=True) if args.output else ROOT/OUT
        report = build(ROOT, document)
        files = render(report)
        if args.check:
            if any(not (out/n).is_file() or (out/n).read_bytes() != data.encode() for n, data in files.items()):
                raise ContractError("RF equipment comparison stale")
        else:
            out.mkdir(parents=True, exist_ok=not bool(args.conditions))
            for name, data in files.items():
                (out/name).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "private-recalculation" if args.conditions else "exported", "options": 2, "files": len(files),
            "conditions_received": report["condition_values_received"], "protected_controls": report["protected_controls_unchanged"], "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

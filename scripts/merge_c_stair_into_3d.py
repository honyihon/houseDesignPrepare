#!/usr/bin/env python3
"""Owner-authorized merge at the existing viewer URL, using bounded snapshots."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import export_kaohsiung_options as kh  # noqa: E402

from house_design.c_ac01_route import RUNTIME as AC01_RUNTIME  # noqa: E402
from house_design.c_stair_merge import INDEX, REPORT, RUNTIME, VIEWER, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402

NS = "http://www.w3.org/2000/svg"


def viewer_text(study, original, root):
    payload = {"kaohsiung_options": {k: study[k] for k in (
        "default_option", "display_revision", "report_hash", "source_hashes", "cost_studies", "professional_status")}}
    payload["kaohsiung_options"]["integration_revision"] = study["integration_revision"]
    payload["kaohsiung_options"]["stair_display_revision"] = study["stair_display_revision"]
    payload["kaohsiung_options"]["ac01_route_revision"] = study["ac01_route_revision"]
    payload["kaohsiung_options"]["options"] = [{"id": o["id"], "label": o["label"], "building": o["building"],
        "states": [{k: s[k] for k in ("id", "label", "model")} for s in o["states"]]} for o in study["options"]]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    text, count = re.subn(r"(^\s*var DATA = ).+(;\s*$)", lambda m: m[1]+encoded+m[2], original, count=1, flags=re.M)
    if count != 1:
        raise ContractError("Original viewer data anchor changed")
    replacements = {
        "  var furnitureLabelRects=[];": (root/RUNTIME).read_text()+"\n"+(root/AC01_RUNTIME).read_text()+"\n  var furnitureLabelRects=[];",
        "    khBuildZones(mesh,group,base,features);": "    khBuildZones(mesh,group,base,features);\n    csBuildParts(mesh,group,features);\n    caBuildParts(mesh,group,features);",
        "    if (features.stairs) {": "    if (features.stairs && !features.c_stair_surfaces) {",
        "    });\n    renderLegend();": "      csPrepareFloor(mesh);\n    });\n    renderLegend();",
        "      kaohsiung:khEvidence(),": "      kaohsiung:khEvidence(),\n      cStair:csEvidence(),\n      cAc01Routing:caEvidence(),",
    }
    for old, new in replacements.items():
        if text.count(old) != 1:
            raise ContractError("Original viewer integration anchor changed: "+old[:65])
        text = text.replace(old, new)
    return text


def floor_svg(option, state, floor):
    render_floor = copy.deepcopy(floor)
    for room in render_floor["rooms"]:
        if room["features"].get("c_stair_surfaces"):
            room["features"].pop("stair_footprint_mm", None)
    svg = kh.svg_plan(option, {**state, "plans": {"floors": [render_floor]}, "review": state["review"]}, render_floor)
    if floor["id"] == "floor-1":
        for node in svg.iter():
            if node.get("data-hvac-label-id") == "C-AC01" and node.get("data-hvac-label-type") == "indoor":
                node.set("x", "5610")
                node.set("y", "6600")
                node.set("text-anchor", "end")
    overlay = ET.SubElement(svg, f"{{{NS}}}g", {"data-c-stair-integration": "1"})

    def rect(area, attrs):
        x, y, w, h = area
        return ET.SubElement(overlay, f"{{{NS}}}rect", {"x": str(x), "y": str(y), "width": str(w), "height": str(h), **attrs})

    for room in floor["rooms"]:
        features = room["features"]
        surfaces = features.get("c_stair_surfaces", [])
        for s in surfaces:
            rect(s["rect_mm"], {"fill": "#d1dfd5" if s["kind"] != "tread" else "#b9cbd3",
                "stroke": "#557781", "stroke-width": "14", "data-cs-part": s["id"],
                "data-top-mm": str(s["top_z_mm"])})
        gate = features.get("c_front_gate")
        if gate:
            x, y, w, h = gate["wall_budgets_mm"][0]
            lo, hi = gate["opening_x_mm"]
            rect([x, y, lo-x, h], {"fill": "#9eada5", "data-cs-part": "front-fixed-left"})
            rect([hi, y, x+w-hi, h], {"fill": "#9eada5", "data-cs-part": "front-fixed-right"})
            rect(gate["wall_budgets_mm"][1], {"fill": "#9eada5", "data-cs-part": "front-return"})
            rect(gate["parking_rect_mm"], {"fill": "#bda77f", "stroke": "#80673d", "stroke-width": "16",
                "data-cs-part": "front-leaf", "data-door-state": "open"})
            ET.SubElement(overlay, f"{{{NS}}}text", {"x": str(lo), "y": str(y-180), "font-size": "155"}).text = "前置門1200名義／圖示開門"
        side = features.get("c_side_gate")
        if side:
            rect(side["open_rect_mm"], {"fill": "#9b9d85", "data-cs-part": "side-leaf", "data-door-state": "open"})
        riser = features.get("c_ac01_riser_envelope")
        if riser:
            rect(riser["rect_mm"], {"fill": "#c88d44", "fill-opacity": ".25", "stroke": "#a36724",
                "stroke-width": "22", "stroke-dasharray": "50 35", "data-ac01-riser": "candidate"})
    route = state["model"]["c_ac01_routing"]["route"]
    if floor["id"] in {"floor-1", "floor-2"}:
        points = route["polyline_mm"][:4] if floor["id"] == "floor-1" else route["polyline_mm"][4:]
        ET.SubElement(overlay, f"{{{NS}}}polyline", {"points": " ".join(f"{p[0]},{p[1]}" for p in points),
            "fill": "none", "stroke": "#247b94", "stroke-width": "28", "stroke-dasharray": "65 35",
            "data-ac01-route": floor["id"]})
    ET.SubElement(svg, f"{{{NS}}}metadata", {"data-c-stair-source-features": "1"}).text = json.dumps(
        {r["id"]: {k: v for k, v in r["features"].items() if k.startswith("c_")}
            for r in floor["rooms"] if any(k.startswith("c_") for k in r["features"])}, ensure_ascii=False, separators=(",", ":"))
    return svg


def ac01_svg(study):
    review = study["c_ac01_review"]
    svg = ET.Element(f"{{{NS}}}svg", {"viewBox": "0 0 1200 1080", "width": "1200", "height": "1080",
        "role": "img", "aria-labelledby": "title desc"})

    def el(tag, text=None, **attrs):
        node = ET.SubElement(svg, f"{{{NS}}}"+tag, {k.rstrip("_").replace("_", "-"): str(v) for k, v in attrs.items()})
        node.text = text
        return node

    el("title", "C-AC01：室內機前移與室內立管候選", id="title")
    el("desc", "兩層平面及側向中心線比較。藍線為預排，紅線為舊問題；穿板、梁窗、固定、排水及機型未核。", id="desc")
    el("style", "text{font-family:system-ui,sans-serif;fill:#263d48;font-size:16px} .head{font-size:25px;font-weight:700} .small{font-size:13px} .new{fill:none;stroke:#247b94;stroke-width:3} .old{fill:none;stroke:#b85c4d;stroke-width:2;stroke-dasharray:7 4}")
    el("rect", x=0, y=0, width=1200, height=1080, fill="#f7faf9")
    el("text", "C-AC01｜室內機前移、室內立管、二樓高位接機", x=35, y=46, class_="head")
    el("text", "預排／未採用：200mm立管及150mm包束為協調預算，梁板穿孔、固定面與產品未核。", x=35, y=84)
    el("text", "原49件家具與景觀／洗曬保留；二樓協調帶占0.04㎡，不能當成已設計的管井。", x=35, y=114)
    el("text", "藍線：新候選　　紅虛線：舊路徑／機位　　橘框：立管協調帶", x=35, y=150)
    old, points = review["baseline"]["polyline_mm"], review["route"]["polyline_mm"]
    plans = next(o for o in study["options"] if o["id"] == "c-split")["states"][0]["plans"]
    for n, floor in enumerate(plans["floors"][:2]):
        left, top, scale = 40+n*330, 230, .045
        el("text", "1F｜室內機避開前置牆" if n == 0 else "2F｜立管避開沙發／門口", x=left, y=198)

        def box(area, _left=left, _top=top, _scale=scale, **attrs):
            x, y, w, h = area
            return el("rect", x=_left+x*_scale, y=_top+y*_scale, width=w*_scale, height=h*_scale, **attrs)

        box([0, 0, 6000, 8960], fill="none", stroke="#809194")
        if n == 0:
            box([0, 0, 6000, 3900], fill="#f6e8bc")
            box([4000, 3900, 2000, 1800], fill="#d8e2e7", stroke="#809194")
            box([4000, 5700, 2000, 1800], fill="#e1ece1", stroke="#809194")
            box([2400, 8500, 3600, 100], fill="#809194")
            b = review["new_indoor_body_mm"]
            box([b[0], b[1], b[3]-b[0], b[4]-b[1]], fill="#75a3b0")
            el("text", "騎樓", x=left+80, y=top+90)
            el("text", "公衛上方", x=left+154, y=top+217, class_="small")
            el("text", "新室內機", x=left+95, y=top+295, class_="small")
            el("polyline", points=" ".join(f"{left+p[0]*scale},{top+p[1]*scale}" for p in old[:3]), class_="old")
            old_unit = review["before_indoor"]
            box([old_unit["x_mm"]-140, old_unit["y_mm"]-475, 280, 950], fill="none", stroke="#b85c4d")
            pp = points[:4]
        else:
            box([0, 0, 6000, 3900], fill="#e9edeb")
            box([2000, 1650, 4000, 2250], fill="#d9e9cc", stroke="#80a775")
            room = next(r for r in floor["rooms"] if r["key"] == "living2f")
            sofa = next(i for i in room["furniture"] if "sofa" in i["id"])["placement"]["aabb"]
            box([sofa["minX"], sofa["minY"], sofa["maxX"]-sofa["minX"], sofa["maxY"]-sofa["minY"]], fill="#a5b8b1")
            el("text", "右側9㎡景觀", x=left+120, y=top+115, class_="small")
            el("text", "高位線在景觀上方", x=left+40, y=top+145, class_="small")
            el("text", "原沙發", x=left+140, y=top+310, class_="small")
            pp = points[4:]
        envelope = review["riser_envelope_mm"]
        box([envelope[0], envelope[1], envelope[3]-envelope[0], envelope[4]-envelope[1]], fill="#e7bd7f", stroke="#9b672d")
        el("polyline", points=" ".join(f"{left+p[0]*scale},{top+p[1]*scale}" for p in pp), class_="new")
    el("text", "側向剖面｜省略X向偏移", x=720, y=198)
    hx, vy = lambda y: 720+y*.05, lambda z: 650-z*.05
    el("rect", x=hx(0), y=vy(3500), width=3900*.05, height=3500*.05, fill="#f6e8bc")
    for z, name in [(0, "1F"), (3500, "3.5m協調線"), (4000, "2F +4m"), (7000, "3F +7m")]:
        el("line", x1=720, y1=vy(z), x2=1160, y2=vy(z), stroke="#9faeae", stroke_dasharray="5 4")
        el("text", name, x=720, y=vy(z)-7, class_="small")
    for pp, style in [(old, "old"), (points, "new")]:
        el("polyline", points=" ".join(f"{hx(p[1])},{vy(p[2])}" for p in pp), class_=style)
    el("text", "騎樓投影", x=760, y=632)
    el("text", "室內立管候選", x=980, y=396, class_="small")
    el("circle", cx=hx(5000), cy=vy(4000), r=6, fill="#c88d44")
    el("text", "穿板候選（未核）", x=995, y=440, class_="small")
    el("text", "橘點需核梁板／套管，不指示鑽孔", x=835, y=680, class_="small")
    lines = [
        f"舊估長 {review['baseline']['estimated_routed_length_mm']/1000:.3f}m → 新候選 {review['route']['estimated_routed_length_mm']/1000:.3f}m，均含原1m彎折／維修預算。",
        f"首尾高差 {review['route']['elevation_difference_mm']/1000:.2f}m；上下垂直折線累計 {review['routed_vertical_travel_mm']/1000:.2f}m，不能只看首尾高差。",
        f"室內支管中心+{points[3][2]/1000:.2f}m；2F高位中心+{points[4][2]/1000:.2f}m；不是梁下淨高或完成面。",
        f"立管中心x={(review['riser_envelope_mm'][0]+review['riser_envelope_mm'][3])/2:g}、y=5000；200×200名義帶至沙發投影餘量{review['upper_sofa_projection_gap_mm']:.0f}mm。",
        "150mm包束低點試線未再跨騎樓3500mm協調線；不是合法淨高、鑽孔或支撐通過。",
        "冷凝水另核重力坡降／檢修／合法終端；不能跟著冷媒先升高，未加排水泵。",
        "待回覆：配對機型、負荷、管長／高差／追加冷媒、梁板鋼筋、防水防火、樹冠及維修。",
    ]
    for n, line in enumerate(lines):
        el("text", line, x=35, y=760+n*39)
    el("metadata", json.dumps(review, ensure_ascii=False, separators=(",", ":")), data_ac01_route_review="1")
    return ET.tostring(svg, encoding="unicode")+"\n"


def artifacts(root=ROOT):
    study, original = build(root)
    files = {}
    option = next(o for o in study["options"] if o["id"] == "c-split")
    state = option["states"][0]
    for floor in state["plans"]["floors"]:
        svg = floor_svg(option, state, floor)
        name = "structured/candidates/kaohsiung-house-options/"+floor["plan_file"]
        files[name] = ET.tostring(svg, encoding="unicode")+"\n"
        if floor["id"] == "floor-2":
            svg.set("viewBox", "-250 -350 6500 4750")
            svg.set("height", "500")
            files["structured/candidates/kaohsiung-house-options/c-split_integrated_balcony-detail.svg"] = ET.tostring(svg, encoding="unicode")+"\n"
    index = kh.render_index(study)
    index = index.replace("獨立比較，未採用／專業未核。既有房間、門窗、樓梯及標高保留；C照護續版仍另案。", "完整方案未採用／專業未核。C棟已併入4m24級與前置可關門；孝親套衛及三樓通道保留，產品與結構仍待核。")
    index = index.replace(
        '<tr><td>C一樓3.6→4m假設</td><td>保留22級則每級約181.82mm，原梯深有機會保留，但適用類組、淨高與照護舒適性未核；改24級約166.67mm則需4970mm梯深，比現4840mm多130mm。兩案上層標高均差400mm。僅剖面預算，本頁3D維持原3.6m。</td></tr>',
        '<tr><td>C已整合：4m／24級／270mm踏面</td><td>每級約166.67mm，完整1000mm前平台向公共前室共享200mm，保留梯廳外框、孝親套衛及三樓通道；二樓到達面分開，前置門設於平台之前。2F／3F／RF標高為+4／+7／+10m。原3.6m／22級保留於C控制案；降板、實際淨高、梁板及門組未核。</td></tr>')
    index = index.replace("<nav>", '<p><a href="../../Docs/c-stair-shared-landing-v1.md">C樓梯與門組整合說明</a>；3D側欄可切換前門／二樓側門開關，平面圖預設開門。</p><nav>', 1)
    index = index.replace("kaohsiung-house-options/c-split_daily_balcony-detail.svg", "kaohsiung-house-options/c-split_integrated_balcony-detail.svg")
    ac01_file = "structured/candidates/kaohsiung-house-options/c-ac01-route-study.svg"
    files[ac01_file] = ac01_svg(study)
    route_review = study["c_ac01_review"]
    route_section = ('<section id="c-ac01-route"><h2>C客餐冷氣：室內立管候選</h2>'
        '<p>室內機移至乾式前室右壁，避開前置分隔牆；公衛上方升至二樓起居空白角，再走二樓高位接室外機。'
        '200×200mm協調帶占二樓0.04㎡，沒有縮家具、孝親房或景觀區。</p>'
        f'<p>舊估長{route_review["baseline"]["estimated_routed_length_mm"]/1000:.3f}m → 候選{route_review["route"]["estimated_routed_length_mm"]/1000:.3f}m；'
        '沒有再排2350mm低位跨騎樓線，但梁板穿孔、固定、機型限制、樹冠與冷凝排水仍待核，未採用／非施工圖。</p>'
        '<p><a href="../../Docs/c-ac01-route-study-v1.md">尺寸、代價與未解條件</a> · '
        '<a href="kaohsiung-house-options/c-ac01-route-study.svg">新舊管線／兩層剖面圖</a></p>'
        '<img alt="C-AC01新舊冷媒管線及室內立管候選，未核穿板、產品及排水" src="kaohsiung-house-options/c-ac01-route-study.svg" style="width:100%;height:auto"></section>')
    index = index.replace("</main>", route_section+"</main>") if "</main>" in index else index.replace("</body>", route_section+"</body>")
    files[INDEX] = index
    files[VIEWER] = viewer_text(study, original, root)
    report = copy.deepcopy(study)
    for o in report["options"]:
        for s in o["states"]:
            s.pop("model")
    report["payload_sha256"] = hashlib.sha256(re.search(r"^\s*var DATA = (.+);\s*$", files[VIEWER], re.M)[1].encode()).hexdigest()
    report["artifact_hashes"] = {name: hashlib.sha256(value.encode()).hexdigest() for name, value in files.items()}
    files[REPORT] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Static snapshot and byte checks only; never WebGL")
    args = parser.parse_args()
    try:
        outputs = artifacts()
        for name, content in outputs.items():
            path = ROOT/name
            if args.check:
                if not path.exists() or path.read_text(encoding="utf-8") != content:
                    raise ContractError("Merged artifact missing or stale: "+name)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        print(f"C stair merged {'checked' if args.check else 'written'} at existing 3D URL: {len(outputs)} files; no scene/browser run.")
        return 0
    except (ContractError, KeyError, StopIteration, OSError) as exc:
        print("C stair merge failed: "+str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

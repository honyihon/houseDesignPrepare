#!/usr/bin/env python3
"""C-only integrated comparisons. Never adopt a plan or change a requirement."""
from __future__ import annotations

import copy
import html
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import export_b32_entry_options as b32
import export_preparation_review as shared
from lib.dimension_overrides import load_overrides
from lib.model3d_facade import build_facade, render_elevation
from lib.model3d_placement import overlaps
from lib.model3d_plan import plan_data, render_plan

from house_design.rendering import encode_html_json

ROOT, OUT, STATUS = shared.ROOT, shared.OUT, shared.STATUS
SOURCE = ROOT / "inputs/c-integrated-options.json"
PROTECTED = [*shared.PROTECTED, "inputs/b32-entry-options.json",
             "structured/candidates/b32-entry-options/layout.js",
             *[str(p.relative_to(ROOT)) for p in sorted((ROOT / "inputs/revisions").rglob("*")) if p.is_file()]]


def upper_proposal(raw: dict, furniture: dict, core: dict, settings: dict) -> int:
    b = raw["buildings"]["C"]
    cy = core["core_y_mm"]
    furniture["profiles"].update({
        "integrated-c-guest": shared.profile(("bed", "single-bed"), ("desk", "desk-140"), ("wardrobe", "wardrobe-180")),
        "integrated-c-living": shared.profile(("sofa", "sofa-3"), ("tv", "tv-console"), ("coffee-table", "coffee-table")),
        "integrated-c-kitchen": shared.profile(("counter", "counter-240"), ("fridge", "fridge-75")),
        "integrated-c-gym": shared.profile(("treadmill", "treadmill"), ("yoga-mat", "yoga-mat"), ("dumbbell-rack", "dumbbell-rack")),
    })
    for item in furniture["profiles"]["integrated-c-guest"]:
        item["front_clearance_mm"] = 600 if item["id"] != "desk" else 700
    for item in furniture["profiles"]["integrated-c-living"]:
        item["front_clearance_mm"] = {"sofa": 400, "tv": 600, "coffee-table": 0}[item["id"]]
    for item in furniture["profiles"]["integrated-c-kitchen"]:
        item["front_clearance_mm"] = 900 if item["id"] == "counter" else 600
    next(i for i in furniture["profiles"]["integrated-c-gym"] if i["id"] == "dumbbell-rack")["front_clearance_mm"] = 700
    f = b["floors"]["floor-2"]
    prior = f["rooms"]
    group = "C2-integrated-open-living"
    f["rooms"] = {
        **{k: copy.deepcopy(v) for k, v in prior.items()
           if k not in {"living2f", "front-hall", "guestroom2f", "stair2f", "kitchen2f"}},
        "guestroom2f": shared.room(settings["guest_rect_mm"], "前左有窗客房（單人床／位置取捨未定）", "bedroom", "integrated-c-guest",
                                   window_mm=1200, window_face="front", window_ratio=2000/2800),
        "living2f": shared.room([2800, 3900, 3200, cy-3900], "二樓開放起居｜三人沙發電視區", "living", "integrated-c-living",
                               group=group, role="living", window_mm=1200, window_face="front", window_ratio=.25),
        "living-nook": shared.room([0, 7600, 2800, cy-7600], "開放起居延伸／通行（不重複計面積）", "living",
                                  group=group, role="living", window_mm=0),
        "day-reserve": shared.room([0, cy, 2400, 13800-cy], "乾式彈性預留（不睡眠／未排設備）", window_mm=0),
        "stair2f": shared.room([2400, cy, 3600, 13800-cy], "同軸樓梯／公共到達", "stair", window_mm=0),
        "kitchen2f": shared.room([3600, 13800, 2400, 3830], "240cm後小廚房（原65cm深／操作分時）", "kitchen", "integrated-c-kitchen",
                                window_mm=1200, window_face="rear"),
    }
    f["rooms"]["rear-hall"].update(window_mm=600, window_face="rear")
    f["connections"] = [
        shared.common("living2f", "living-nook"), ["living2f", "guestroom2f", 900, 4700],
        ["living2f", "balcony2f", 900, 5200], ["living2f", "stair2f", 900, 5200],
        ["living-nook", "day-reserve", "open"], ["day-reserve", "stair2f", 900, cy+550],
        ["stair2f", "rear-hall", "open"], ["rear-hall", "kitchen2f", 800, 14400],
        ["rear-hall", "bath2f", 900, 15100], ["rear-hall", "rear-service", 900, 16700],
    ]
    # Preserve 1.36m nominal common hall even in the taller 1F case. The
    # 4m case pays for this by reducing the master, never the stair/landing.
    master_end = min(7600, cy-1360)
    f = b["floors"]["floor-3"]
    for key, dims, name in [
        ("master3f", [0, 3900, 6000, master_end-3900], "前側主臥（4m樓高案面積取捨）"),
        ("front-hall", [2400, master_end, 3600, cy-master_end], "公共橫向通道（不穿主臥）"),
        ("fitness3f", [0, master_end, 2400, 13800-master_end], "加深運動區（原廠／隔振仍待核）"),
    ]:
        f["rooms"][key]["rect"], f["rooms"][key]["name"] = dims, name
    f["rooms"]["master3f"].update(profile="review-c-efficient-master", window_mm=2100, window_face="front", window_ratio=.2)
    f["rooms"]["front-hall"].update(clear=True, window_mm=0,
        clearance_reservations=[{"kind": "circulation", "rect": [80, 80, 3440, cy-master_end-160]}])
    f["rooms"]["fitness3f"].update(profile="integrated-c-gym", kind="other", window_mm=0)
    f["connections"] = [
        ["master3f", "front-hall", 900, 5200], ["front-hall", "stair3f", 900, 5200],
        ["front-hall", "fitness3f", 900, (master_end+cy)/2],
        ["stair3f", "rear-hall", 1000, 3000], ["rear-hall", "bath3f", 900, 15100],
        ["master3f", "terrace3f", 900, 3500],
    ]
    b["summary"] = "有窗公衛／側牆床＋前客房／開放起居＋運動外廓避客房的整合比較，未採用。"
    b["hvac_pairs"].append(["floor-2", "guestroom2f", "floor-2", "balcony2f", "front"])
    return master_end


def products(building: dict, core: dict, master_end: int, settings: dict) -> None:
    shared.c_products(building, core)
    floors = [{c["key"]: c for c in f["cells"] if c.get("tour_active")} for f in building["floors"]]
    c, cy = floors[1], core["core_y_mm"]
    values = {
        "guestroom2f": [("bed", [80, 3980, 1050, 1880], 180, "front"),
                        ("desk", [2020, 5470, 700, 1400], 90, "right"),
                        ("wardrobe", [80, 6920, 1800, 600], 0, "rear")],
        "living2f": [("sofa", [5020, cy-3400, 900, 2400], 90, "right"),
                     ("tv", [2880, 5700, 450, 1800], 270, "left"),
                     ("coffee-table", [4000, cy-2750, 600, 1100], 90, "")],
        "kitchen2f": [("counter", [3680, 15150, 650, 2400], 270, "left"),
                      ("fridge", [5220, 13880, 700, 750], 90, "right")],
    }
    for key, items in values.items():
        for local, bounds, rotation, anchor in items:
            shared.set_product(c[key], local, bounds, rotation, anchor)
    c = floors[2]
    for local, bounds, rotation, anchor in [
        ("bed", [80, master_end-2800, 2000, 1800], 270, "left"),
        ("wardrobe", [2820, master_end-680, 1800, 600], 0, "rear"),
        ("vanity", [5420, master_end-2300, 500, 1200], 90, "right"),
    ]:
        shared.set_product(c["master3f"], local, bounds, rotation, anchor)
    for local, bounds, rotation, anchor in [
        ("treadmill", settings["treadmill_body_mm"], 0, ""),
        ("yoga-mat", [80, 11920, 700, 1800], 0, ""),
        ("dumbbell-rack", [1120, 13220, 1200, 500], 0, "rear"),
    ]:
        shared.set_product(c["fitness3f"], local, bounds, rotation, anchor)
    # Distinct overlays, not generic circulation reserves or permission to
    # install a model whose manufacturer requires a larger safety envelope.
    x, y, w, d = settings["treadmill_body_mm"]
    side, rear = [settings["exercise_allowances_mm"][k] for k in ("side", "rear")]
    zones = [{"kind": "treadmill-rear-discussion", "aabb": shared.box(shared.rect(x-side, y+d, w+2*side, rear))},
             *[{"kind": "treadmill-side-discussion", "aabb": shared.box(shared.rect(sx, y, side, d))}
               for sx in (x-side, x+w)]]
    c["fitness3f"]["tour_features"]["exercise_review"] = {
        "status": "discussion-envelope-only-not-manufacturer-or-acoustic-approval", "zones": zones,
        "rear_budget_mm": rear, "side_budget_mm": side,
        "front_budget_after_assumed_wall_mm": y-master_end-80,
        "manufacturer_front_minimum_mm": None, "manual_source": None,
        "simultaneous_entry_and_exercise": "not-verified-use-sequentially",
        "note": "跑步機後方2m、兩側各50cm為討論暫留，不是原廠核定。前端餘量很薄，原廠若要更多必須重排。門前與側邊動作分時，未核多人使用、梁板承重、振動及結構傳音；瑜伽與啞鈴本體不占後方暫留。"}


def integrated_screen(building: dict) -> dict:
    floors = [{c["key"]: c for c in f["cells"] if c.get("tour_active")} for f in building["floors"]]
    guest, living, gym = floors[1]["guestroom2f"], floors[1]["living2f"], floors[2]["fitness3f"]
    exercise = gym["tour_features"]["exercise_review"]
    equipment = [gym["furniture_placements"]["tour_mm"][i["id"]]["aabb"] for i in gym["furniture"]]
    envelopes = equipment + [z["aabb"] for z in exercise["zones"]]
    under_sleep = [r for r in floors[1].values() if r["kind"] == "bedroom"]
    overlap = [r["id"] for r in under_sleep if any(overlaps(shared.box(r["tour_mm"]), a) for a in envelopes)]
    if overlap or not guest["tour_features"]["window_review"]["renderable"]:
        raise ValueError("Integrated C loses guest daylight or exercise projection separation")
    for z in exercise["zones"]:
        if not shared.union_covers(z["aabb"], [gym]) or any(overlaps(z["aabb"], a) for a in equipment):
            raise ValueError("Integrated C exercise discussion envelope is obstructed")
    reqs = {r["id"]: r for r in json.loads(shared.model3d.REQUIREMENTS_FILE.read_text())["requirements"]}
    area_rows = []
    groups = {"C.floor-2.living2": [living, floors[1]["living-nook"]], "C.floor-2.guest2": [guest],
              "C.floor-2.kitchenette": [floors[1]["kitchen2f"]], "C.floor-3.master_c": [floors[2]["master3f"]],
              "C.floor-3.gym": [gym]}
    for rid, rooms in groups.items():
        r = reqs[rid]
        values = [{"assumed_each_side_mm": i, "area_sqm": b32.inset_area(rooms, i)} for i in (80, 100, 115)]
        val, minimum, target = values[0]["area_sqm"], r["constraints"]["min_sqm"], r["constraints"]["target_sqm"]
        area_rows.append({"id": rid, "title": r["title"], "room_ids": [c["id"] for c in rooms],
                          "discussion_inset_sqm": val, "minimum_sqm": minimum, "target_sqm": target,
                          "minimum_state": "below-minimum" if val < minimum else "area-only-not-function-approval",
                          "target_state": "below-target" if val < target else "area-only-not-function-approval",
                          "inset_sensitivity": values, "finished_and_legal_area": None})
    if any(r["minimum_state"] == "below-minimum" for r in area_rows):
        raise ValueError("Integrated C fails an original minimum even with the assumed 80mm inset")
    return {"exercise_over_sleep_rooms": overlap, "exercise_separation_scope": "equipment-and-discussion-envelopes-not-entire-room-or-structure-borne-noise",
            "exercise": exercise, "upper_area_checks": area_rows,
            "guest_location_deviation": "front-instead-of-original-rear-preference-owner-decision-pending",
            "guest_bed_choice": "single-bed-already-allowed-in-original-brief-not-sofa-bed-capacity-claim",
            "guest_window": guest["tour_features"]["window_review"]}


def build_study() -> dict:
    s = json.loads(SOURCE.read_text())
    if (s["schema"] != "house-c-integrated-options-v1" or s["revision"] != 1
            or s["status"] != STATUS or s["active_design"] != "baseline"
            or s["frame_mm"] != [6000, 17630] or s["frontage_depth_mm"] != 3900
            or s["guest_rect_mm"] != [0, 3900, 2800, 3700]
            or s["treadmill_body_mm"] != [580, 7830, 900, 2000]
            or s["exercise_allowances_mm"] != {"side": 500, "rear": 2000, "manufacturer_front_minimum": None}
            or [(o["id"], o["height_mm"], o["risers"]) for o in s["options"]] != [
                ("c-integrated-3000", 3000, 18), ("c-integrated-3600", 3600, 22), ("c-integrated-4000", 4000, 24)]
            or s["default_option"] != "c-integrated-3600"
            or set(s["professional_status"].values()) != {"unknown"}
            or any(d["status"] != "pending" for d in s["owner_decisions"])):
        raise ValueError("C integration needs a coordinated redraw; may not silently adopt/approve/change its scope")
    options = []
    for spec in s["options"]:
        raw, furniture, old = shared.source_review()
        core = shared.c_proposal(raw, furniture, old, spec["height_mm"], spec["risers"])
        raw["id"] = "c-integrated-comparison-v1"
        master_end = upper_proposal(raw, furniture, core, s)
        payload = shared.model3d.build_payload(json.loads(shared.model3d.PROGRAM_FILE.read_text()), load_overrides(),
            shared.model3d.default_drawing_style(), review_data=raw, furniture_data=furniture, validate_a_arcade=False)
        b = next(b for b in payload["buildings"] if b["id"] == "C")
        shared.refresh_stairs(b, spec["height_mm"], spec["risers"], core)
        products(b, core, master_end, s)
        screen = shared.body_screen(b)
        if (screen["fixed_body_failures"] or screen["pending_solver_items"] or screen["operation_limits"]
                or any(r["issue"] == "operation-vs-body" for r in screen["operation_sharing"])):
            raise ValueError("C integration coordinate defects: " + spec["id"] + " " + json.dumps(screen, ensure_ascii=False))
        brief = shared.program_screen(b, {**spec, "building": "C"}, screen)
        brief["area_checks"] = shared.requirement_areas(b)
        brief.update(integrated_screen(b))
        payload["facade"] = build_facade(payload["buildings"], payload["standards"])
        plans = next(b for b in plan_data(payload)["buildings"] if b["id"] == "C")
        for f in plans["floors"]:
            f["plan_file"] = spec["id"] + "_" + f["id"] + ".svg"
        tradeoffs = ["比較未採用，ABC主案、B32後門優先／前門備案及原需求不變。6×17.63m約32地坪，不是可建樓地板面積。",
                    "1F沿用有窗公衛／側牆床整合比較，保原230cm後窗；上層浴廁避床體，不代表整間臥室上方無浴廁。",
                    "2F前客房採原需求允許的105×188cm單人床，原140cm桌及180cm櫃不縮；客房前移與原後段偏好不同，需屋主決定。",
                    "2F保240×65cm廚具及75cm冰箱，錯開靠牆擺；冰箱、取物及進出仍分時。起居／客房原目標不刪，面積表列不足。",
                    "三樓器材與討論運動外廓避二樓客房；運動房門前過渡可能仍投影客房尾端，不能宣稱整間運動房完全不在客房上方，更不保證結構傳音已解。",
                    "跑步機後留2m、兩側50cm僅討論假設，前端餘量薄；未選機型、無原廠手冊、未核結構及衝擊音，不能當可立即使用。",
                    "全層樓梯同軸，樓高越高佔梯井越深；4m案保公共橫向通道，主臥面積需取捨。3.6m只是優先討論，不是騎樓法定高度。",
                    "停車、玄關原面積、孝親套衛救援、屋頂合法量體及原360cm主臥衣櫃／電視仍未完整容納。"]
        review = {"program": brief, "coordinate_screen": screen, "professional_status": s["professional_status"]}
        option = {**spec, "building": "C", "status": STATUS, "frame_mm": s["frame_mm"], "plans": plans,
                  "review": review, "tradeoffs": tradeoffs}
        option["model"] = shared.isolate(payload, b, option, review, tradeoffs)
        option["model"]["bc_option"]["revision"] = 1
        option["model"]["source"].pop("preparation_review", None)
        option["model"]["source"].pop("preparation_generator", None)
        option["model"]["source"]["c_integrated_review"] = "inputs/c-integrated-options.json"
        option["model"]["source"]["c_integrated_generator"] = "scripts/export_c_integrated_options.py"
        options.append(option)
    files = [SOURCE, Path(__file__), ROOT / "scripts/export_preparation_review.py", ROOT / "scripts/export_b32_entry_options.py",
             *[ROOT / p for p in ("inputs/concept-layout-review.json", "inputs/references/abc-before-space-efficiency-20261014.json",
               "inputs/furniture-layout.json", "inputs/requirements.json", "inputs/bc-constraints-options.json",
               "inputs/c1f-window-moisture-brief.json", "inputs/physical-items.json", "inputs/facade-concept.json",
               "inputs/dimensions.json", "structured/room_program.json", "scripts/templates/model3d.html",
               "scripts/templates/model3d_facade.js", "scripts/templates/bc-options-controls.html", "scripts/templates/bc-options-bootstrap.js",
               "scripts/templates/c-integrated-options.html", "scripts/export_model_3d.py", "scripts/config/residential_defaults_tw.json")],
             ROOT / "scripts/check_c_integrated_playwright.cjs", ROOT / "Docs/abc-rationality-followup-v1.md",
             shared.model3d.THREE_FILE, *sorted((ROOT / "scripts/lib").glob("*.py")),
             *sorted((ROOT / "house_design/rendering").glob("*.py"))]
    return {**s, "display_revision": 2, "options": options, "source_hashes": {str(p.relative_to(ROOT)): shared.digest(p) for p in files},
            "protected_main_hashes": {p: shared.digest(ROOT / p) for p in PROTECTED}}


def render_index(study: dict) -> str:
    sections = []
    for o in study["options"]:
        p = o["review"]["program"]
        rows = "".join('<tr><td>'+html.escape(r["title"])+f'</td><td>{r["discussion_inset_sqm"]:.4f}</td><td>{r["minimum_sqm"]}／{r["target_sqm"]}</td><td>'+
                       ("低於原目標，未刪需求" if r["target_state"] == "below-target" else "只達面積討論值，功能未核")+'</td></tr>'
                       for r in p["area_checks"] + p["upper_area_checks"])
        figures = "".join(f'<figure><figcaption>{html.escape(f["label"])} · <a href="c-integrated-options/{f["plan_file"]}">放大SVG</a> · <a href="c-integrated-options-3d.html?scheme={o["id"]}#mode=tour&amp;building=C&amp;floor={f["id"]}&amp;view=plan">同源3D</a></figcaption><object type="image/svg+xml" data="c-integrated-options/{f["plan_file"]}" aria-label="{html.escape(f["label"])}同源平面"></object></figure>' for f in o["plans"]["floors"])
        sections.append(f'<section id="{o["id"]}" data-option="{o["id"]}"><h2>{html.escape(o["label"])}</h2><p class="warning">未採用／專業未核。窗、門、照護、跑步機安全與防振不能據此定案。</p><ul>'+"".join('<li>'+html.escape(t)+'</li>' for t in o["tradeoffs"])+
                        f'</ul><p>1F客餐名義 {p["living_dining_nominal_sqm"]:.3f}m²；3F跑步機前端扣模型牆邊後暫剩 {p["exercise"]["front_budget_after_assumed_wall_mm"]}mm，原廠最低要求未知。</p>'+
                        '<div class="scroll"><table><thead><tr><th>保留的原需求</th><th>80mm討論內縮m²</th><th>原下限／目標m²</th><th>判讀</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+figures+
                        '<details><summary>座標初篩、牆厚敏感度與操作共享（非核定）</summary><pre>'+html.escape(json.dumps(o["review"],ensure_ascii=False,indent=2))+'</pre></details></section>')
    decisions = "".join('<li data-decision="'+html.escape(d["id"])+'">'+html.escape(d["recommendation"])+"（待屋主確認）</li>" for d in study["owner_decisions"])
    return (ROOT / "scripts/templates/c-integrated-options.html").read_text().replace("__DECISIONS__", decisions).replace("__OPTIONS__", "\n".join(sections))


def main() -> None:
    before = {p: shared.digest(ROOT / p) for p in PROTECTED}
    study = build_study()
    directory = OUT / "c-integrated-options"
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {**study, "options": [{k:v for k,v in o.items() if k != "model"} for o in study["options"]]}
    (directory / "layout.js").write_text("window.HOUSE_C_INTEGRATED_OPTIONS = " + encode_html_json(manifest) + ";\n")
    for o in study["options"]:
        for f in o["plans"]["floors"]:
            svg = render_plan("C", f, viewer_url="../c-integrated-options-3d.html?scheme="+o["id"])
            tree = ET.fromstring(svg)
            tree.set("data-study-option", o["id"])
            tree.set("data-study-status", STATUS)
            ET.SubElement(tree, "{"+shared.NS+"}text", {"x":"0", "y":"-820", "font-size":"185"}).text = "整合比較未採用；原面積目標保留，專業未核。"
            (directory / f["plan_file"]).write_text('<?xml version="1.0" encoding="UTF-8"?>\n'+ET.tostring(tree,encoding="unicode")+"\n")
        facade = o["model"]["facade"]
        (directory / (o["id"]+"_front.svg")).write_text(render_elevation(facade, facade["buildings"][0]))
    (OUT / "c-integrated-options.html").write_text(render_index(study))
    controls = (ROOT / "scripts/templates/bc-options-controls.html").read_text().replace("bc-options.html", "c-integrated-options.html").replace("B 家規／C 照護", "C有窗公衛／客房／運動整合").replace("B／C比較", "C整合比較")
    bootstrap = (ROOT / "scripts/templates/bc-options-bootstrap.js").read_text().replace("bc-options.html", "c-integrated-options.html").replace("B 家規／C 照護", "C有窗公衛／客房／運動整合").replace('"bc-constraints"', '"c-integrated"')
    data = {"bc_options": {"default_option": study["default_option"], "options": [
        {"id": o["id"], "label": o["label"], "building": "C", "model": o["model"]} for o in study["options"]]}}
    viewer = shared.model3d.render_html(data, shared.model3d.three_source()[0], study_controls=controls, study_bootstrap=bootstrap)
    viewer = viewer.replace('htmlHref="bc-options.html#"', 'htmlHref="c-integrated-options.html#"')
    viewer = viewer.replace('row("標示面積",', 'row("原HTML歷史面積（非本比較）",')
    (OUT / "c-integrated-options-3d.html").write_text(viewer)
    if {p: shared.digest(ROOT / p) for p in PROTECTED} != before:
        raise RuntimeError("C integration changed a main drawing, B32 or an archive")
    print("Written 3 C-only integrated comparisons; ABC/B32/requirements/archives unchanged. Not adopted or approved.")


if __name__ == "__main__":
    main()

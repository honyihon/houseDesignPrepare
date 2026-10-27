#!/usr/bin/env python3
"""Write a bounded decision/inquiry pack, not HTML, 3D or product approval."""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from house_design.c_care_bath_readiness import (  # noqa: E402
    BASE_REPORT,
    BASE_VIEWER,
    OUT,
    PRODUCT_FIELDS,
    PRODUCT_SOURCE,
    build_study,
)
from house_design.contracts import ROOT, write_json  # noqa: E402

PRODUCT_LABELS = {"bath-door": "兩片後收疊門組", "basin": "壁掛洗手台", "fold-seat": "折椅完整商品", "right-grab-rail": "淋浴右側完整扶手"}
FIELD_LABELS = {
    "full_open_clear": "實際全開淨寬（框／把手均計入）",
    "complete_pack": "含軌道與把手的整組室內外凸",
    "rear_extent_from_nominal_aperture_end": "洞口後緣至全開尾端／止擋／檢修最遠處",
    "front_projection_from_nominal_aperture_start": "全行程凸出洞口前緣的最前距離",
    "body_width": "盆體未旋轉的原產品總寬", "body_depth": "盆體未旋轉的原產品總深", "top_height": "安裝完成盆頂高度",
    "knee_clear_width": "含底座／配管後實際檯下淨寬", "knee_clear_height": "含底座／配管後實際檯下淨高", "knee_clear_depth": "含底座／配管後實際檯下淨深",
    "tap_control_from_front_edge": "盆前緣至龍頭操作點水平距離", "supply_drain_outer_projection": "給排水與保溫外廓",
    "open_width": "折椅放下整件寬", "open_depth": "折椅放下整件深", "folded_projection_from_rear_finish": "折起整件含鉸座／背板距後完成面外凸",
    "complete_projection_from_right_finish": "整件含底座／握持距右完成面最內凸",
}


def render_summary(study):
    lines = ["# C 套衛：坐姿可及與選品決策包", "",
        "這輪不改HTML／3D或任何配置，不需因此重跑WebGL。未採用、未選品；沒有真人可及、照護、救援或施工核可。", "",
        f"來源：[保留側盆版HTML](../c-care-bath-layout.html) · [同版3D](../{Path(BASE_VIEWER).name}) · [本次座標與來源](review.json) · [16項廠商填答表](supplier-checklist.csv) · [選品交付JSON](product-checklist.json)", "",
        "## 建議結論", "",
        "先保留側盆版250mm偏側與原門位，做足尺坐姿驗證並取得完整商品圖，不先把盆／門再往後推。", "",
        "若足尺驗證不能順利操作龍頭或膝／腳／管線互擋，就另立盆、馬桶及門的整合重排，保留原案比較，不降低900mm討論目標或假借膝部空間。", "",
        "## 為何是250mm偏側", "",
        study["arrival"]["scope"], "",
        f"固定外廓只求不重疊時，需要至少{study['arrival']['minimum_offset_zero_spare_mm']:g}mm偏側；如再保留30mm可選討論餘量，需要{study['arrival']['minimum_offset_for_optional_margin_mm']:g}mm。30mm不是法規、施工容差或照護標準。", "",
        "| 偏側mm | 前完成面餘量mm | 掀起扶手旁餘量mm | 指定900mm到位試線 |", "| ---: | ---: | ---: | --- |"]
    for case in study["arrival"]["cases"]:
        status = "受阻："+'、'.join(case["route"]["coordinate_failures"]) if case["route"]["coordinate_failures"] else "指定矩形無重疊；坐姿可及未知"
        lines.append(f"| {case['offset_mm']:g} | {case['front_finish_spare_mm']:g} | {case['raised_arm_directional_spare_mm']:g} | {status} |")
    bounds = study["basin_and_door_rear_shift"]["continuous_shift_bounds_mm"]
    lines += ["", "## 為何不能只把盆與門往後移來置中", "",
        study["basin_and_door_rear_shift"]["scope"], "",
        f"要讓目前置中900mm外廓避開前方扶手，至少後移{bounds['minimum_for_current_centered_body']:g}mm；但保留目前兩片門／20mm止擋時最多只剩{bounds['maximum_for_nonnegative_stop_parking']:g}mm後移預算。兩個條件相差{bounds['shortfall_mm']:g}mm，沒有同時非負的後移區間。這不證明整間浴室無解。", "",
        "| 盆／門同量後移mm | 置中靜止矩形 | 停門含既有止擋餘量mm |", "| ---: | --- | ---: |"]
    for case in study["basin_and_door_rear_shift"]["cases"]:
        lines.append(f"| {case['rear_shift_mm']:g} | "+("有外框／配件衝突" if case["centered_arrival_coordinate_failures"] else "指定靜止外廓無重疊，未重算完整動線")+f" | {case['rear_spare_after_existing_stop_mm']:g} |")
    lines += ["", "## 18.5mm右側緊餘量：只研究板試點，不移扶手", "",
        "下表只是1800×600mm剛性板及1898mm全角度方框的討論標示，不是擔架、真人或照護者。數值試線在全開時無指定衝突、半開與關門時仍須被真門片阻擋，原HTML／3D完全沒有改。", "",
        "| 板轉向中心x mm | 至門組側餘量mm | 至右扶手餘量mm | 是否已畫入原HTML／3D |", "| ---: | ---: | ---: | --- |"]
    for case in study["board_trials"]["cases"]:
        lines.append(f"| {case['center_x_mm']:g} | {case['left_door_pack_spare_mm']:g} | {case['right_rail_spare_mm']:g} | "+("原試點" if case["center_x_mm"] == 4850 else "否，僅計算候選")+" |")
    interval = study["board_trials"]["center_interval_for_optional_margin_mm"]
    lines += ["", f"若只求門組與右扶手各留30mm討論餘量，中心x可討論區間為{interval[0]:g}～{interval[1]:g}mm；等分兩側的純數學點為{study['board_trials']['balanced_center_x_mm']:g}mm，兩側各37.25mm。小數不是施工放樣精度，也不消除配件基座、安裝及真人救援未知。", "",
        "## 交給門廠／衛浴廠的條件", "",
        "以下邊界只針對目前固定座標；等於邊界是0餘量，不是合格值。取得商品全包絡後仍須回套整個模型，不能只看單項數字。", "",
        "| 廠商項目 | 現模型討論值mm | 零餘量方向邊界mm | 若另留30mm的上限mm |", "| --- | ---: | --- | ---: |"]
    for b in study["product_budgets"]:
        boundary = ("至少" if b["direction"] == "min" else "最多")+f"{b['zero_spare_boundary_mm']:g}"
        optional = "另核，原900mm目標不降" if b["max_for_optional_margin_mm"] is None else f"{b['max_for_optional_margin_mm']:g}"
        lines.append(f"| {FIELD_LABELS[b['field']]} | {b['current_discussion_value_mm']:g} | {boundary} | {optional} |")
    lines += ["", "右扶手目前模型向內凸67.5mm，而欲在原板試點旁多留30mm時上限僅56mm，不能叫廠商把必要握持間隙硬縮小。優先取得完整底座／握持圖，再比板試點或整合配置。", "",
        "盆600×450mm、頂高850mm只是現模型預算，不是已選產品或照護適用高度；170mm可見薄盆網格也不能充當檯下淨空證明。須取得龍頭操作點、實際檯下高寬深、支架與冷熱／排水管完整剖面；膝部通行信用仍0。", "",
        "### 文件與填答方式", "",
        f"請在專案`{PRODUCT_SOURCE}`填廠商回覆；CSV只是詢問表，不會自動匯入或覆寫來源。四類共16個尺寸目前全部未知，不用把模型數字抄成實測。", "",
        "每項提供品牌、型號及evidence紀錄：document（專案inputs/references/、assets/references/或Docs/內的相對路徑）、sha256、revision、checked_by、checked_at（ISO日期）。無文件、檔案無法讀取、雜湊不符或缺查核資訊時，已填尺寸仍不得用作通過依據。文件存在與雜湊正確也只證明檔案一致，不替代內容真實性、商品完整性或專業審核。", "",
        "| 項目 | 本次資料狀態 | 採用／商品／照護 |", "| --- | --- | --- |"]
    for p in study["product_responses"]:
        lines.append(f"| {PRODUCT_LABELS[p['id']]} | "+("未知，待文件及實際尺寸" if p["status"] == "unknown" else "已有部分可追溯資料，仍待整體回套")+" | 未採用／未知 |")
    lines += ["", "## 足尺坐姿驗證計畫，不是已做的試驗", "",
        "1. 先記錄實際使用者需求、椅型、坐姿座高、含腳踏板／輪框寬深及照護人數；900mm矩形不是實際輪椅或身體模型。未取得資料前，不設平均人體可及結論。",
        "2. 用足尺膠帶／紙板標出盆600×450mm、完成面、900mm指定到位點、250mm偏側、扶手、管線及門片包絡；只確認靜態位置，不先作抬抱或冒險轉位。",
        "3. 由本人在安全陪同及適當職能治療／照護評估下，記錄能否自然操作冷熱／龍頭、膝腳與管線有無互擋、照護者是否可協助；不得用身體過度扭轉或降低900mm來換通過。",
        "4. 門組另外取得全開、全行程、開關施力、夾傷保護、濕區耐用、外解鎖／可拆及倒地受壓應對的原廠圖／程序；足尺坐姿試驗不當成救援測試。",
        "5. 保留日期、操作者、匿名使用者／椅型識別、實際測量與問題紀錄；不成功就保留問題，另提整合重排，不直接採用。盆前操作與馬桶側移仍分時，淋浴濕地、風水、消防與施工未核。", "",
        "## 驗證範圍", "",
        "只做檔案／來源雜湊與小範圍座標檢核；無瀏覽器、WebGL、3D runtime或自動選品。本包不覆寫任何父版檔案、需求或輸入回覆；新試點未改進原圖，原QA只對應凍結圖面。", "",
        "| 保留限制 |", "| --- |"]
    lines += ["| "+item.replace("|", "／")+" |" for item in study["limits"]]
    return '\n'.join(lines)+'\n'


def render_supplier_csv(study):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["項目", "尺寸欄位", "廠商實際尺寸mm（待填）", "目前模型值mm（非實測）", "零餘量方向邊界mm", "另留30mm上限（非標準）", "尺寸定義", "廠商", "型號", "文件路徑", "版本", "SHA256", "查核人", "查核日期", "核可狀態"])
    budgets = {(b["product"], b["field"]): b for b in study["product_budgets"]}
    for pid, fields in PRODUCT_FIELDS.items():
        for field in fields:
            b = budgets.get((pid, field))
            nominal = study["discussion_product_facts_mm"][pid][field]
            writer.writerow([PRODUCT_LABELS[pid], FIELD_LABELS[field], "", nominal if nominal is not None else "",
                ((">=" if b["direction"] == "min" else "<=")+str(b["zero_spare_boundary_mm"])) if b else "需人因／商品協調，無自動通過界線",
                b["max_for_optional_margin_mm"] if b and b["max_for_optional_margin_mm"] is not None else "",
                b["measurement_definition"] if b else "完整商品與安裝剖面，不得縮模型或假借膝部淨空",
                "", "", "", "", "", "", "", "未知／未採用"])
    return output.getvalue()


def write_study(study, root: Path = ROOT):
    directory = root / OUT
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "review.json", study)
    write_json(directory / "product-checklist.json", {"schema": "house-c-care-bath-readiness-products-v1", "adopted": False,
        "base_report": BASE_REPORT, "base_plan_hash": study["base_plan_hash"], "report_hash": study["report_hash"],
        "budgets": study["product_budgets"], "products": study["product_responses"], "professional_status": study["professional_status"]})
    (directory / "summary.md").write_text(render_summary(study), encoding="utf-8")
    (directory / "supplier-checklist.csv").write_text(render_supplier_csv(study), encoding="utf-8-sig", newline="")
    return {"summary": OUT+"/summary.md", "report": OUT+"/review.json", "supplier_checklist": OUT+"/supplier-checklist.csv",
        "arrival_cases": len(study["arrival"]["cases"]), "rear_shift_cases": len(study["basin_and_door_rear_shift"]["cases"]),
        "board_trials": len(study["board_trials"]["cases"]), "product_fields": sum(map(len, PRODUCT_FIELDS.values())),
        "geometry_changed": False, "browser_required_for_this_pack": False, "product_and_care_approval": "unknown"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check frozen sources and bounded math only; no writes or browser")
    args = parser.parse_args()
    study = build_study()
    result = {"status": "files-and-bounded-math-checked", "geometry_changed": False, "sources": len(study["source_hashes"]),
        "product_and_care_approval": "unknown"} if args.check else write_study(study)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

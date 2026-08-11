#!/usr/bin/env python3
"""Pre-bake parametric floor plans for the three buildings.

Nobody has drawn a plan yet and the lot dimensions are not decided. The only
hard number is 32 ping of building area per building. So instead of asking for
dimensions we do not have, this script sweeps the frontage (6-10 m, with the
depth back-solved to keep the area locked at 32 ping) and the garage size, and
writes every resulting plan out at once. The 3D viewer then just switches
between them as the user drags a slider.

Outputs:
    structured/parametric/plan.json    geometry for every variant
    structured/parametric/capacity.md  the area ledger, in Chinese, for humans

Usage:
    python scripts/generate_parametric_plan.py
    python scripts/generate_parametric_plan.py --frontage 8000 --pretty
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import plan_geometry as pg  # noqa: E402
from lib.standards import ROOT, load_residential_defaults, repo_relative  # noqa: E402

try:  # optional: rules land in a later step, geometry must not depend on them
    from lib import plan_rules  # type: ignore
except ImportError:  # pragma: no cover
    plan_rules = None  # type: ignore

SCHEMA = "house-parametric-plan-v1"
SITE_PATH = ROOT / "inputs" / "site.json"
BRIEF_DIR = ROOT / "inputs" / "brief"
OUT_DIR = ROOT / "structured" / "parametric"


# --------------------------------------------------------------------------


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def derive_depth_mm(footprint_sqm: float, frontage_mm: int) -> int:
    """Depth is not a free parameter: it is whatever keeps the area at 32 ping."""
    raw = footprint_sqm * 1_000_000.0 / frontage_mm
    return int(round(raw / 10.0) * 10)


def core_annex_demand(brief: dict[str, Any]) -> float:
    """Largest core-band demand across the storeys, so the core is sized once
    and holds still on every floor."""
    best = 0.0
    for floor in brief.get("floors", []):
        if floor.get("fill") == "fixed":
            continue
        total = sum(float(r.get("target_sqm", 0) or 0)
                    for r in floor.get("rooms", []) if r.get("band") == "core")
        best = max(best, total)
    return best


# --------------------------------------------------------------------------
# Capacity ledger
# --------------------------------------------------------------------------


def floor_capacity(floor_payload: dict[str, Any], brief_floor: dict[str, Any],
                   footprint_sqm: float) -> dict[str, Any]:
    cells = floor_payload["cells"]

    def counted(cell: dict[str, Any]) -> bool:
        return bool(cell.get("counts_in_footprint", True))

    clear_total = sum(c["area_sqm"] for c in cells)
    net_sqm = pg.Rect(*floor_payload["net_rect"]).area_sqm
    wall_sqm = round(net_sqm - clear_total, 2)

    # The grid cells must tile the net area exactly. Any residue here means a
    # hole (or an overlap) in the plan, and every area figure below it is fiction
    # -- so it is reported rather than absorbed into the wall allowance.
    grid_total = sum(pg.Rect(*c["rect"]).area_sqm for c in cells)
    tile_error = round(net_sqm - grid_total, 3)

    demand = 0.0
    for room in brief_floor.get("rooms", []):
        if room.get("counts_in_footprint") is False:
            continue
        demand += float(room.get("target_sqm", 0) or 0)

    fixed = 0.0
    for cell in cells:
        if cell["role"] in ("corridor", "stair", "garage"):
            fixed += cell["area_sqm"]

    # Area the brief never asked for. It is neither demand nor fixed cost, so
    # it belongs in its own column - a floor with 15 m2 of it is a floor whose
    # programme is incomplete, which is a different problem from being short.
    flex = sum(c["area_sqm"] for c in cells if c["role"] == "flex")

    usable = round(net_sqm - wall_sqm, 2)
    required = round(demand + fixed, 2)
    gap = round(required - usable, 2)

    shortfalls = [
        {"id": c["id"], "name": c["name"], "area_sqm": c["area_sqm"], "min_sqm": c["min_sqm"]}
        for c in cells if "BELOW_MIN_AREA" in c.get("flags", [])
    ]
    narrow = [
        {"id": c["id"], "name": c["name"], "rect": c["clear_rect"]}
        for c in cells if "TOO_NARROW" in c.get("flags", [])
    ]
    # Rooms sharing a zone the partitioner could not tile with everybody over
    # 1.5 m. Distinct from TOO_NARROW: that says "this room came out thin", this
    # says "no arrangement of these rooms in this pocket works", which is a
    # statement about the brief rather than about the cut that was chosen.
    no_fit = [
        {"id": c["id"], "name": c["name"]}
        for c in cells if "ZONE_NO_FIT" in c.get("flags", [])
    ]

    return {
        "floor_id": floor_payload["floor_id"],
        "label": floor_payload["label"],
        "footprint_sqm": round(footprint_sqm, 2),
        "net_sqm": round(net_sqm, 2),
        "wall_sqm": wall_sqm,
        "tile_error_sqm": tile_error,
        "usable_sqm": usable,
        "rooms_demand_sqm": round(demand, 2),
        "fixed_sqm": round(fixed, 2),
        "flex_sqm": round(flex, 2),
        "flex_ping": round(flex / pg.PING_TO_SQM, 2),
        "required_sqm": required,
        "gap_sqm": gap,
        "gap_ping": round(gap / pg.PING_TO_SQM, 2),
        "over_capacity": gap > 0.5,
        "below_min": shortfalls,
        "too_narrow": narrow,
        "no_fit": no_fit,
    }


def penthouse_check(floor_payload: dict[str, Any], footprint_sqm: float,
                    ratio: float) -> dict[str, Any]:
    total = sum(c["area_sqm"] for c in floor_payload["cells"] if c.get("penthouse"))
    limit = footprint_sqm * ratio
    return {
        "penthouse_sqm": round(total, 2),
        "limit_sqm": round(limit, 2),
        "limit_ping": round(limit / pg.PING_TO_SQM, 2),
        "over": total > limit + 0.05,
    }


# --------------------------------------------------------------------------


def build_building(brief: dict[str, Any], frontage_mm: int, depth_mm: int,
                   site: dict[str, Any], defaults: dict[str, Any],
                   garage_variant: dict[str, Any]) -> dict[str, Any]:
    footprint_sqm = frontage_mm * depth_mm / 1_000_000.0
    annex = core_annex_demand(brief)

    sk = pg.build_skeleton(frontage_mm, depth_mm, site, defaults, garage_variant, annex)

    floors: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    for brief_floor in brief.get("floors", []):
        payload = pg.build_floor(brief_floor, sk, site, defaults)
        floors.append(payload)
        if brief_floor.get("fill") == "fixed":
            ledger.append({
                "floor_id": payload["floor_id"],
                "label": payload["label"],
                "roof": True,
                **penthouse_check(payload, footprint_sqm,
                                  float(site.get("roof", {}).get("penthouse_max_ratio", 0.125))),
            })
        else:
            ledger.append(floor_capacity(payload, brief_floor, footprint_sqm))

    return {
        "building_id": brief["building_id"],
        "name": brief.get("name"),
        "positioning": brief.get("positioning"),
        "frontage_mm": frontage_mm,
        "depth_mm": depth_mm,
        "footprint_sqm": round(footprint_sqm, 2),
        "footprint_ping": round(footprint_sqm / pg.PING_TO_SQM, 2),
        "skeleton": {
            "net_rect": sk.net.as_list(),
            "front_depth_mm": sk.front_depth,
            "corridor_w_mm": sk.corridor_w,
            "core_rect": sk.core.as_list(),
            "stair_rect": sk.stair.as_list(),
            "core_annex_rect": sk.core_annex.as_list() if sk.core_annex else None,
            "garage_rect": sk.garage.as_list() if sk.garage else None,
            "spine_rect": sk.spine.as_list() if sk.spine else None,
            "notes": sk.notes,
        },
        "floors": floors,
        "capacity": ledger,
    }


def build_variant(site: dict[str, Any], briefs: dict[str, dict[str, Any]],
                  defaults: dict[str, Any], frontage_mm: int,
                  garage_variant: dict[str, Any]) -> dict[str, Any]:
    footprint_sqm = float(site["footprint_ping"]) * float(site["ping_to_sqm"])
    depth_mm = derive_depth_mm(footprint_sqm, frontage_mm)

    buildings = {}
    for bid in ("A", "B", "C"):
        buildings[bid] = build_building(briefs[bid], frontage_mm, depth_mm,
                                        site, defaults, garage_variant)

    return {
        "id": f"f{frontage_mm}_g{garage_variant.get('bays', 1)}",
        "frontage_mm": frontage_mm,
        "depth_mm": depth_mm,
        "footprint_sqm": round(frontage_mm * depth_mm / 1_000_000.0, 2),
        "footprint_ping": round(frontage_mm * depth_mm / 1_000_000.0 / pg.PING_TO_SQM, 3),
        "garage": dict(garage_variant),
        "buildings": buildings,
    }


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def _ping(v: float) -> str:
    return f"{v / pg.PING_TO_SQM:.2f}"


def write_capacity_report(doc: dict[str, Any], path: Path) -> None:
    site = doc["site"]
    lines: list[str] = []
    lines.append("# 參數化平面 · 容量帳與規則檢查")
    lines.append("")
    lines.append(f"產生時間：{doc['generated_at']}")
    lines.append("")
    lines.append("> 這份報告的前提：**建築師還沒開始設計，地的長寬還沒決定。**")
    lines.append("> 唯一的硬條件是每棟建築面積 32 坪。開間是滑桿，進深由面積反推，")
    lines.append("> 所以每個變體的建築面積都一樣，只有形狀不同。")
    lines.append("")
    lines.append(f"- 每棟每層建築面積：**{site['footprint_ping']} 坪 "
                 f"= {site['footprint_ping'] * site['ping_to_sqm']:.2f} m²**")
    lines.append(f"- 樓層：**{site['storeys']} 層 + RF**（RF 不是第四層，只有女兒牆與屋突）")
    lines.append(f"- 屋突免計容積上限：建築面積 × {site['roof']['penthouse_max_ratio']} "
                 f"= {site['footprint_ping'] * site['roof']['penthouse_max_ratio']:.2f} 坪")
    lines.append(f"- 三棟由左至右（平面圖上）：{' → '.join(doc['row']['order_left_to_right'])}"
                 f"　＝ 站在前院面對房子時，右手邊 A、中間 B、左手邊 C")
    lines.append("")

    lines.append("## 1. 容量結論（先看這個）")
    lines.append("")
    lines.append("兩個問題要一起看，只過一關沒有意義：**車停不停得進去**，以及**房間放不放得下**。")
    lines.append("")
    lines.append("| 開間 | 進深 | 車位 | 車庫停得進車 | A 棟 1F | B 棟 1F | C 棟 1F |")
    lines.append("|---|---|---|---|---|---|---|")
    # A finding whose garage does not take an SUV + charger is a different kind
    # of failure from a floor that is 2 ping short, and the earlier version of
    # this table showed only the second one - so 9 m read as "fits" while its
    # garage was 3.5 m deep. Both columns, same row.
    garage_ng: dict[str, set[str]] = {}
    for fnd in doc.get("findings", []):
        if fnd.get("code") in ("GARAGE_NOT_PARKABLE", "GARAGE_FEWER_BAYS"):
            garage_ng.setdefault(fnd["variant"], set()).add(fnd["building"])
    clean: list[str] = []
    for var in doc["variants"]:
        row = [f"{var['frontage_mm'] / 1000:.1f} m",
               f"{var['depth_mm'] / 1000:.1f} m",
               var["garage"].get("label", "")]
        ng = sorted(garage_ng.get(var["id"], ()))
        row.append("停得進" if not ng else f"**{'、'.join(ng)} 棟停不進**")
        over = False
        for bid in ("A", "B", "C"):
            cap = next((c for c in var["buildings"][bid]["capacity"]
                        if c.get("floor_id") == "floor-1"), None)
            if cap is None:
                row.append("-")
            elif cap["gap_sqm"] > 0.5:
                over = True
                row.append(f"**超出 {cap['gap_ping']:.2f} 坪**")
            else:
                row.append(f"放得下（餘 {abs(cap['gap_ping']):.2f} 坪）")
        if not ng and not over:
            clean.append(var["id"])
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    if len(clean) == 1:
        lines.append(f"**兩關都過的只有 `{clean[0]}` 一個變體。**")
    elif clean:
        lines.append("兩關都過的變體：" + "、".join(f"`{c}`" for c in clean) + "。")
    else:
        lines.append("**沒有任何變體同時通過兩關。**")
    lines.append("")
    lines.append("「超出」不代表產生器失敗 —— 平面照樣畫得出來，只是每間房都被壓小。"
                 "要解決只有四條路：**減車位、把某個機能移到 2F、放大建築面積、或接受變小。**"
                 "「停不進」則是另一回事：車庫淨尺寸放不下休旅車＋充電樁，"
                 "那個開間下所謂的「車庫」只是一個停不了車的房間。"
                 "這正是要拿去跟建築師談的那張表。")
    lines.append("")

    lines.append("## 2. 逐變體逐層明細")
    lines.append("")
    lines.append(
        "「彈性餘裕」是需求表沒有安排、也不是走道車庫樓梯的那塊面積。它會在平面上"
        "畫成一格具名空間（標記 `UNPROGRAMMED`），而不是按比例灌進各房間 —— "
        "灌進去的話，20 m² 的娛樂室會變 34.5、5 m² 的廁所會變 20，而且看不出來是誰"
        "多給的。這一欄有數字，代表那層的需求表還沒寫完，該補的是儲藏、更衣、露臺"
        "或直接把房間目標調大，由使用者決定而不是由產生器代決。"
        "但餘裕不會切到讓房間短邊低於 1500 mm —— 會的話就退回讓房間吸收，"
        "所以有些樓層仍看得到房間明顯大於目標。")
    lines.append("")
    lines.append(
        "分割器除了直切，也會**從角落挖一塊**，剩下的 L 形拆成兩個矩形 —— 這是製圖員"
        "會做、純 guillotine 做不到的動作。少了它，兩間房共用一區時只能各切一條通長"
        "條狀，5 m² 的廁所在 5.6 m 寬的區裡就只能是 0.9 m 寬。角落挖出來的剩料不會偷偷"
        "灌給鄰居，一樣列為彈性餘裕。若**所有**切法都會讓某間房短邊低於 1500 mm，該區"
        "標記 `ZONE_NO_FIT`：那是需求表在這個開間下放不下的意思，改切法沒有用。")
    lines.append("")
    for var in doc["variants"]:
        lines.append(f"### 開間 {var['frontage_mm'] / 1000:.1f} m × 進深 "
                     f"{var['depth_mm'] / 1000:.1f} m　·　{var['garage'].get('label', '')}"
                     f"　（{var['footprint_ping']:.2f} 坪／棟）")
        lines.append("")
        for bid in ("A", "B", "C"):
            b = var["buildings"][bid]
            lines.append(f"**{b['name']}**")
            if b["skeleton"]["notes"]:
                for note in b["skeleton"]["notes"]:
                    lines.append(f"> ⚠ {note}")
            lines.append("")
            lines.append("| 樓層 | 樓層淨面積 | 牆體 | 可用 | 需求(房間) | 固定(車庫/走道/梯) | 彈性餘裕 | 合計需求 | 差額 |")
            lines.append("|---|---|---|---|---|---|---|---|---|")
            for cap in b["capacity"]:
                if cap.get("roof"):
                    mark = "❌ 超過" if cap["over"] else "✅"
                    lines.append(f"| {cap['label']} | — | — | — | 屋突 "
                                 f"{cap['penthouse_sqm']:.2f} m² | 上限 "
                                 f"{cap['limit_sqm']:.2f} m² | — | — | {mark} |")
                    continue
                gap = cap["gap_sqm"]
                mark = f"**+{gap:.2f}**" if gap > 0.5 else f"{gap:.2f}"
                flex = cap.get("flex_sqm", 0.0)
                flex_txt = f"{flex:.2f}（{cap.get('flex_ping', 0.0):.2f} 坪）" if flex else "—"
                lines.append(
                    f"| {cap['label']} | {cap['net_sqm']:.2f} | {cap['wall_sqm']:.2f} | "
                    f"{cap['usable_sqm']:.2f} | {cap['rooms_demand_sqm']:.2f} | "
                    f"{cap['fixed_sqm']:.2f} | {flex_txt} | {cap['required_sqm']:.2f} | {mark} |"
                )
            lines.append("")
            issues = []
            for cap in b["capacity"]:
                for s in cap.get("below_min", []):
                    issues.append(f"{cap['label']} {s['name']}：{s['area_sqm']:.1f} m² "
                                  f"< 下限 {s['min_sqm']} m²")
                for s in cap.get("too_narrow", []):
                    issues.append(f"{cap['label']} {s['name']}：短邊不足 1.5 m")
                names = "、".join(s["name"] for s in cap.get("no_fit", []))
                if names:
                    issues.append(f"{cap['label']} 這一區怎麼切都放不下（`ZONE_NO_FIT`）："
                                  f"{names} —— 要減項目或換開間，不是調切法")
            if issues:
                lines.append("面積／比例不合格：")
                for i in issues:
                    lines.append(f"- {i}")
                lines.append("")

    findings = doc.get("findings")
    if findings is not None:
        lines.append("## 3. 規則檢查")
        lines.append("")
        if not findings:
            lines.append("所有變體都沒有觸發規則檢查 —— 這通常代表檢查沒跑到，值得懷疑。")
        else:
            # Matrix first. Which frontage is least bad is the question the reader
            # actually has, and it is not answerable by scrolling a hundred rows.
            variant_ids = [v["id"] for v in doc["variants"]]
            matrix = plan_rules.summarise(findings) if plan_rules else {}
            if matrix:
                lines.append("### 3.1 代碼 × 變體對照")
                lines.append("")
                lines.append("| 代碼 | 嚴重度 | " + " | ".join(variant_ids) + " |")
                lines.append("|---" * (len(variant_ids) + 2) + "|")
                order = sorted(matrix, key=lambda c: -sum(matrix[c].values()))
                for code in order:
                    row = matrix[code]
                    cells_ = " | ".join(str(row.get(v, 0) or "·") for v in variant_ids)
                    lines.append(f"| `{code}` | {plan_rules.SEVERITY.get(code, '')} "
                                 f"| {cells_} |")
                totals = [sum(1 for f in findings if f.get("variant") == v)
                          for v in variant_ids]
                lines.append("| **合計** |  | " + " | ".join(str(t) for t in totals) + " |")
                lines.append("")
                best = variant_ids[totals.index(min(totals))]
                lines.append(f"問題最少的變體是 **{best}**（{min(totals)} 項）。"
                             "這只是計數，不是評分 —— `CAPACITY_OVERFLOW` "
                             "一項的份量遠大於一項 `BATH_FACES_DINING`。")
                lines.append("")
                lines.append("### 3.2 逐項明細")
                lines.append("")
            lines.append("| 變體 | 棟 | 樓層 | 代碼 | 內容 |")
            lines.append("|---|---|---|---|---|")
            for f in findings:
                lines.append(f"| {f.get('variant', '')} | {f.get('building', '')} | "
                             f"{f.get('floor', '')} | `{f.get('code', '')}` | "
                             f"{f.get('message', '')} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("資料來源：`inputs/site.json`（量體參數，全部為假設值）＋ "
                 "`inputs/brief/{A,B,C}.json`（面積需求，轉寫自 `inputs/design_request.md`）。")
    lines.append("重跑：`python scripts/generate_parametric_plan.py`")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path, default=SITE_PATH)
    ap.add_argument("--brief-dir", type=Path, default=BRIEF_DIR)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--frontage", type=int, action="append",
                    help="只產生這些開間（可重複），預設用 site.json 的全部變體")
    ap.add_argument("--pretty", action="store_true", help="縮排輸出 plan.json（檔案會大很多）")
    args = ap.parse_args(argv)

    site = load_json(args.site)
    defaults = load_residential_defaults()
    briefs = {bid: load_json(args.brief_dir / f"{bid}.json") for bid in ("A", "B", "C")}

    frontages = args.frontage or site["frontage_variants_mm"]
    garages = site["garage_variants"]

    variants = [build_variant(site, briefs, defaults, f, g)
                for f in frontages for g in garages]

    doc: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {
            "site": repo_relative(args.site),
            "briefs": [repo_relative(args.brief_dir / f"{b}.json") for b in ("A", "B", "C")],
        },
        "site": {
            "footprint_ping": site["footprint_ping"],
            "ping_to_sqm": site["ping_to_sqm"],
            "storeys": site["storeys"],
            "storey_height_mm": site["storey_height_mm"],
            "slab_thickness_mm": site["slab_thickness_mm"],
            "parapet_height_mm": site["parapet_height_mm"],
            "roof": site["roof"],
            "corridor": site["corridor"],
        },
        "row": site["row"],
        "provenance": site.get("_provenance", "assumed"),
        "variants": variants,
    }

    if plan_rules is not None:
        doc["findings"] = plan_rules.evaluate(doc, site, defaults)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = args.out_dir / "plan.json"
    with plan_path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2 if args.pretty else None,
                  separators=None if args.pretty else (",", ":"))
        fh.write("\n")

    report_path = args.out_dir / "capacity.md"
    write_capacity_report(doc, report_path)

    over = sum(1 for v in variants for b in v["buildings"].values()
               for c in b["capacity"] if c.get("over_capacity"))
    print(f"[parametric] {len(variants)} 變體 × 3 棟 × "
          f"{site['storeys']}層+RF → {repo_relative(plan_path)}")
    print(f"[parametric] 容量超出的樓層數：{over}")
    if plan_rules is not None:
        print(f"[parametric] 規則檢查：{len(doc.get('findings', []))} 項")
    print(f"[parametric] 報告：{repo_relative(report_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

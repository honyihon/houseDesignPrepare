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
from lib.standards import (BASELINE_LABEL, BASELINE_NOTE, ROOT,  # noqa: E402
                           load_residential_defaults, penthouse_limit_sqm,
                           repo_relative, roof_penthouse)

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
                    defaults: dict[str, Any]) -> dict[str, Any]:
    """屋頂突出物 against 建築技術規則建築設計施工編 第 1 條 / 第 162 條.

    Two different numbers get conflated by the "1/8 of the footprint" shorthand,
    and this project sat on the wrong side of both:

    * The cap in 第 1 條 applies to 屋頂突出物**水平投影面積之和** - every 目
      together, not just the stair hall - but it carries a 但書: when 12.5% of
      the building area comes to less than 25 m², 25 m² is allowed anyway. At a
      105.79 m² footprint that is 13.22 m² < 25, so **25 m² is the cap here**.
      The old code used 13.22 and reported a roof that was nearly full; it is
      barely half full.
    * 第 162 條 excludes only 第一目 (樓梯間、昇降機間、無線電塔、機械房) from
      容積總樓地板面積. A water tank or an open heat-pump pad is still a 屋頂
      突出物, it just is not floor area - so it is counted in the projection sum
      and reported separately from the volume-exempt subtotal.

    Neither number is an approval. Whether the three houses are one 幢 or three
    decides how 建築面積 is read in the first place; that is an architect's
    written pre-check, which is why the report says so next to the table.
    """

    cfg = roof_penthouse(defaults)
    limit = penthouse_limit_sqm(defaults, footprint_sqm)

    by_class: dict[str, float] = {}
    unclassified: list[str] = []
    excluded: list[dict[str, Any]] = []
    for cell in floor_payload["cells"]:
        pclass = cell.get("penthouse_class")
        # A brief may declare a projection out of the sum - a flush deck-mounted
        # solar array is the case this exists for - but only explicitly, and it
        # is reported so the exclusion is visible rather than assumed.
        if pclass and cell.get("counts_in_projection") is False:
            excluded.append({"id": cell["id"], "name": cell["name"],
                             "class": pclass, "area_sqm": cell["area_sqm"]})
            continue
        if pclass:
            by_class[pclass] = by_class.get(pclass, 0.0) + cell["area_sqm"]
        elif cell.get("penthouse"):
            # Flagged as a penthouse box but with no 目 stated - it still takes
            # up projection area, so count it and name it rather than drop it.
            by_class["enclosed"] = by_class.get("enclosed", 0.0) + cell["area_sqm"]
            unclassified.append(cell["id"])

    projection = sum(by_class.values())
    volume_exempt = sum(
        area for cls, area in by_class.items()
        if cfg["classes"].get(cls, {}).get("volume_exempt")
    )
    return {
        "penthouse_sqm": round(projection, 2),
        "penthouse_ping": round(projection / pg.PING_TO_SQM, 2),
        "penthouse_by_class": {k: round(v, 2) for k, v in sorted(by_class.items())},
        "volume_exempt_sqm": round(volume_exempt, 2),
        "limit_sqm": round(limit, 2),
        "limit_ping": round(limit / pg.PING_TO_SQM, 2),
        "limit_basis": ("25 m² 但書" if footprint_sqm * cfg["ratio"] < cfg["floor_sqm"]
                        else f"建築面積 × {cfg['ratio']}"),
        "ratio_sqm": round(footprint_sqm * cfg["ratio"], 2),
        "headroom_sqm": round(limit - projection, 2),
        "unclassified": unclassified,
        "excluded": excluded,
        "over": projection > limit + 0.05,
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
                **penthouse_check(payload, footprint_sqm, defaults),
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


ROOF_CLASS_LABEL = {
    "enclosed": "梯間／機械房",
    "tank": "水塔",
    "open_mep": "露天機電",
    "energy": "節能設施",
}


def _ping(v: float) -> str:
    return f"{v / pg.PING_TO_SQM:.2f}"


def write_capacity_report(doc: dict[str, Any], path: Path,
                          defaults: dict[str, Any]) -> None:
    site = doc["site"]
    lines: list[str] = []
    lines.append("# 參數化平面 · 容量帳與規則檢查")
    lines.append("")
    lines.append(f"**{BASELINE_LABEL}**　·　產生時間：{doc['generated_at']}")
    lines.append("")
    lines.append(f"> {BASELINE_NOTE}")
    lines.append("> 與最早的 HTML 草圖（`structured/candidates/`）不一致時，以這份為準。")
    lines.append("")
    lines.append("> 這份報告的前提：**建築師還沒開始設計，地的長寬還沒決定。**")
    lines.append("> 唯一的硬條件是每棟建築面積 32 坪。開間是滑桿，進深由面積反推，")
    lines.append("> 所以每個變體的建築面積都一樣，只有形狀不同。")
    lines.append("")
    lines.append(f"- 每棟每層建築面積：**{site['footprint_ping']} 坪 "
                 f"= {site['footprint_ping'] * site['ping_to_sqm']:.2f} m²**")
    lines.append(f"- 樓層：**{site['storeys']} 層 + RF**（RF 不是第四層，只有女兒牆與屋突）")
    roof_cfg = roof_penthouse(defaults)
    fp_sqm = site["footprint_ping"] * site["ping_to_sqm"]
    roof_limit = penthouse_limit_sqm(defaults, fp_sqm)
    lines.append(
        f"- 屋頂突出物水平投影面積上限：**{roof_limit:.2f} m²"
        f"（{roof_limit / site['ping_to_sqm']:.2f} 坪）**"
        f"　—— 建築面積 × {roof_cfg['ratio']} = {fp_sqm * roof_cfg['ratio']:.2f} m² 未達 25 m²，"
        f"依建築技術規則建築設計施工編第 1 條但書「其未達二十五平方公尺者，得建築二十五平方公尺」，"
        f"以 25 m² 計")
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

    lines.append("### 1b. 屋頂突出物（2026-08-11 更正）")
    lines.append("")
    lines.append(
        f"先前這份報告寫「屋突免計容積上限 = 建築面積 1/8 = 4.0 坪」，**這是錯的**，"
        f"漏掉了條文但書。建築技術規則建築設計施工編第 1 條：屋頂突出物水平投影面積之和"
        f"以建築面積 12.5% 為限，「**其未達二十五平方公尺者，得建築二十五平方公尺**」。"
        f"本案建築面積 {fp_sqm:.2f} m²，12.5% = {fp_sqm * roof_cfg['ratio']:.2f} m² 未達 25，"
        f"因此上限是 **{roof_limit:.2f} m²（{roof_limit / site['ping_to_sqm']:.2f} 坪）**，"
        f"不是 4 坪。實際數字：梯間 8.10 ＋ 水塔 2.62 ＋ 熱泵 2.15 = 12.87 m²，"
        f"B、C 兩棟只用掉一半；A 棟再加上太陽能設備區才接近上限。"
        f"換句話說「屋突已經滿了、樓梯要縮成爬梯」這個結論不成立。")
    lines.append("")
    lines.append(
        "另外，「屋突」不是一個桶子。第 1 條把它分目，第 162 條只讓**第一目**"
        "（樓梯間、昇降機間、無線電塔、機械房）不計入容積總樓地板面積：")
    lines.append("")
    lines.append("| 目 | 內容 | 本案 | 計入投影面積 | 計入容積 |")
    lines.append("|---|---|---|---|---|")
    lines.append("| 第一目 | 樓梯間、昇降機間、無線電塔、機械房 | 梯間屋突 | ✅ | 免計 |")
    lines.append("| 第二目 | 水塔、水箱、女兒牆、防火牆 | 水塔／VF800 | ✅ | 非樓地板 |")
    lines.append("| 第三目 | 露天機電設備、淨水設備、煙囪等 | 熱泵 | ✅ | 非樓地板 |")
    lines.append("| 第四目 | 突出屋面之管道間、採光換氣或再生能源等節能設施 | 太陽能設備區 | ✅ | 非樓地板 |")
    lines.append("")
    lines.append(
        "水塔與熱泵仍然**是**屋頂突出物 —— 露天不等於不算 —— 只是它們不形成樓地板面積。"
        "反過來說，如果之後決定幫熱泵加牆加頂做成設備室，它就可能落回第一目的機械房，"
        "那時候才會開始吃容積。這個決定要在建築師畫圖前講清楚。")
    lines.append("")
    lines.append(
        "> ⚠ **這裡算的是條文字面，不是核准結論。** 三棟在建照上算一幢、連棟還是三幢，"
        "會直接改變「建築面積」怎麼認定，25 m² 但書也就跟著變。屋頂設備的高度、載重、"
        "防颱錨定另有規定。**請建築師做一次書面法規預檢**，不要拿這份報告當依據。")
    lines.append("")
    lines.append(
        "露天設備區不再套用居室 1500 mm 短邊規則 —— 那條規則量的是人住不住得下，"
        "對一台熱泵沒有意義。改量維修通道：短邊低於 "
        f"{roof_cfg['equipment_access_mm']} mm 時標 `EQUIP_ACCESS_TIGHT`，"
        "意思是設備擺得下但人擠不進去維修。散熱間距與拆裝空間仍要看機電圖說。"
        "水塔與熱泵旁的剩料也不再當成露臺，改名為「設備維修淨空」—— 那條 1.1 m 的走道"
        "本來就是要留給人繞到機器後面的，叫它露臺會讓人以為那裡可以曬衣服。")
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
                    mark = ("❌ 超過" if cap["over"]
                            else f"✅ 尚餘 {cap['headroom_sqm']:.2f} m²")
                    breakdown = "＋".join(
                        f"{ROOF_CLASS_LABEL.get(k, k)} {v:.2f}"
                        for k, v in cap.get("penthouse_by_class", {}).items()) or "—"
                    lines.append(f"| {cap['label']} | — | — | — | 屋突投影 "
                                 f"{cap['penthouse_sqm']:.2f} m²（{breakdown}） | 上限 "
                                 f"{cap['limit_sqm']:.2f} m² | — | 免計容積 "
                                 f"{cap['volume_exempt_sqm']:.2f} m² | {mark} |")
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
        # The reader is about to be told 「唯一的通路要穿過主臥」. That sentence only
        # means something if they know the plan has one designated way into each
        # room by policy - under the earlier every-shared-edge door rule there was
        # no "唯一", and the same finding would have been noise.
        roles: dict[str, int] = {}
        for _v in doc["variants"]:
            for _b in _v["buildings"].values():
                for _f in _b["floors"]:
                    for _d in _f.get("doors", []):
                        roles[_d.get("role", "?")] = roles.get(_d.get("role", "?"), 0) + 1
        lines.append("### 3.1 動線與出入口原則（先讀這段，下面的檢查才讀得懂）")
        lines.append("")
        lines.append("門不是「兩間房碰到就開一扇」，而是**每個空間指定一個入口**：")
        lines.append("")
        lines.append("| 門的種類 | 意思 | 數量 |")
        lines.append("|---|---|---|")
        for key, label in (
            ("main_entrance", "大門"),
            ("vehicle_door", "車庫捲門（臨路面）"),
            ("entrance", "該空間**指定的**唯一入口"),
            ("opening", "無門扇的開口（走道↔樓梯、玄關↔走道、宣告開放的區域）"),
            ("hatch", "設備櫃檢修門（MDF/IDF）—— **不算通路**，動線檢查會跳過"),
        ):
            if roles.get(key):
                lines.append(f"| `{key}` | {label} | {roles[key]} |")
        lines.append("")
        lines.append("入口的來源有兩種：需求表寫了 `access_from`（例如「主臥衛浴由主臥進」）就照寫的做，"
                     "沒寫就由產生器從走道／樓梯往外長，優先順序是 "
                     "**走道 → 樓梯 → 玄關 → 一般房間 → 私密空間**。"
                     "落到最後一級會標 `NESTED_ACCESS`；需求指定的關係在該版配置下做不到（兩者根本沒有共用牆），"
                     "標 `ACCESS_UNREALISABLE` 而不是靜靜改走別條路。")
        lines.append("")
        lines.append("**開放式格局要明講。** 需求表沒宣告 `open_plan` 的相鄰空間之間不會自動打通 —— "
                     "客餐廳與廚房要連成一個大空間，是要寫下來的決定，"
                     "不然「穿堂煞要用屏風擋」這類要求會被自動打通的開口默默抵銷。")
        lines.append("")
        if not findings:
            lines.append("所有變體都沒有觸發規則檢查 —— 這通常代表檢查沒跑到，值得懷疑。")
        else:
            # Matrix first. Which frontage is least bad is the question the reader
            # actually has, and it is not answerable by scrolling a hundred rows.
            variant_ids = [v["id"] for v in doc["variants"]]
            matrix = plan_rules.summarise(findings) if plan_rules else {}
            if matrix:
                lines.append("### 3.2 代碼 × 變體對照")
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
                lines.append("### 3.3 逐項明細")
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
    write_capacity_report(doc, report_path, defaults)

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

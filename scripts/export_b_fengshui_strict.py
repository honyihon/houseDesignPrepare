#!/usr/bin/env python3
"""Small static B ritual studies; never regenerate the accepted 3D or run a browser."""
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

from house_design.b_fengshui_strict import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import Plan, Sheet, csv_text, table  # noqa: E402


def polygon(plan, points, **attrs):
    plan.s.add("polygon", points=" ".join(",".join(map(str, plan.p(p))) for p in points), **attrs)


def new_rooms(plan, rooms, operations=False, labels=True):
    for room in rooms:
        fill = "#d6e7d7" if "dry-protection" in room["id"] else "#e1ecee" if "bath" in room["id"] else "#edf1ec"
        polygon(plan, room["polygon_mm"], fill=fill, stroke="#819990", stroke_width=1)
        for item in room["furniture"]:
            plan.box(item["rect_mm"], fill="#b9c9cc", stroke="#6e8c91")
            if labels:
                text_labels = {"bed": "床", "wardrobe": "衣櫃", "vanity": "梳妝台", "toilet": "WC", "basin": "盆", "shower": "900淋浴"}
                plan.text(text_labels.get(item["id"], item["id"]), item["rect_mm"][0]+35,
                    item["rect_mm"][1]+220, class_="tiny")
            if operations and item.get("operation_mm"):
                plan.box(item["operation_mm"], fill="none", stroke="#ba9255", stroke_dasharray="4 3")
        for door in room["doors"]:
            plan.line(door["a"], door["b"], stroke="#388470", stroke_width=4)
        window = room["window"]
        if window:
            plan.line(window["a"], window["b"], stroke="#53a5bc", stroke_width=5)
        if room.get("hvac_candidate"):
            plan.box(room["hvac_candidate"]["rect_mm"], fill="#76adc4", stroke="#477b90")


def whole_sheet(report, option):
    rear = option["id"] == "b-rear-split"
    s = Sheet("B嚴格01｜後門優先／前門備案保留" if rear else "B嚴格02｜無後巷前門備案", report)
    s.text("獨立比較：一樓只右移255；二三樓以L房避完整背櫃，後右濕區避神明堂與後左武轎庫。", 30, 117)
    frame = report["config"]["floor1"]["backing_rect_mm"]
    for n, label in enumerate(["1F 日常", "2F 兩間衛浴", "3F 公衛＋乾區", "上下層保護投影"]):
        ox = 30+n*345
        s.text(label, ox, 158, class_="label")
        plan = Plan(s, (ox, 185), .0395)
        if n == 0:
            plan.rooms(option["states"][0]["floor1"]["rooms"])
            axis = report["config"]["floor1"]["street_axis_x_mm"]
            plan.line([axis, 3900], [axis, 10690], stroke="#ac7041", stroke_dasharray="6 4", stroke_width=2)
        elif n in {1, 2}:
            f = option["upper_floors"][n-1]
            plan.rooms(f["retained_front"])
            new_rooms(plan, f["rooms"], labels=False)
        else:
            plan.box([0, 0, 6000, 17630], fill="#f0f1e9", stroke="#8ea298")
            for p in option["protected_polygons_mm"]:
                polygon(plan, p, fill="#cee3cb", fill_opacity=.55, stroke="#548451", stroke_dasharray="5 3")
            for room in option["upper_floors"][0]["rooms"]:
                if "illustrative_finished_rect_mm" in room:
                    polygon(plan, room["polygon_mm"], fill="#ddb486", fill_opacity=.65, stroke="#a16b35")
            plan.box(option["palanquin_rect_mm"], fill="none", stroke="#5e83a0", stroke_width=2)
        plan.box(frame, fill="none", stroke="#b45751", stroke_width=2, stroke_dasharray="5 3")
        if n in {1, 2}:
            plan.text("L形房", 250, 13700, class_="tiny")
            plan.text("獨立乾室", 2780, 12170, class_="tiny")
            plan.text("公衛", 4250, 13600, class_="tiny")
            plan.text("套衛" if n == 1 else "乾區", 4250, 16300, class_="tiny")
    s.lines(["綠色完整保護區：神明堂＋神桌乾背櫃；橘色：新上層浴廁；藍框：後左武轎庫。名義投影不重疊。",
        "不是只移床：背櫃正上方改成獨立乾室，整間L房也退出保護區；後窗2400保留、機位移回臥室。",
        "代價：套衛115假設內縮僅3.6091㎡，未達原4.5㎡下限；主臥20.1141㎡餘量薄。本案未採用。"], 30, 937, step=32, class_="small")
    return s.output()


def detail_sheet(report):
    opt = report["options"][0]
    f = opt["upper_floors"][0]
    s = Sheet("B嚴格03｜L形主臥與兩衛浴：原尺寸／門前／操作", report)
    s.text("每面115為假設；橘虛框為700操作帶，可分時共用，不能被另一固定本體占用。", 30, 115)
    plan = Plan(s, (40, 180), .082, (0, 11370))
    new_rooms(plan, f["rooms"], operations=True)
    for point in report["config"]["upper"]["bedroom_route_points_mm"]:
        x, y = plan.p(point)
        s.add("circle", cx=x, cy=y, r=3, fill="#4c8b54")
    plan.path(report["config"]["upper"]["bedroom_route_points_mm"], stroke="#4c8b54", stroke_width=2, stroke_dasharray="5 4")
    for room in f["rooms"]:
        for door in room["doors"]:
            if door.get("parked_leaf_budget_mm"):
                plan.box(door["parked_leaf_budget_mm"], fill="#ddbc8c", stroke="#9b6a38")
        if room.get("inside_approach_mm"):
            plan.box(room["inside_approach_mm"], fill="none", stroke="#549567", stroke_dasharray="6 3")
    s.lines(["L房原尺寸：", "床1800×2000、衣櫃1800×600、", "梳妝台1200×500，均不縮。", "900方塊只驗房內若干直段；", "前臂轉彎已避床與固定衣櫃。", "衣櫃／梳妝與通行必須分時。", "",
        "公衛前門從公共乾廳到達。", "套衛側門只通主臥，向房內外開。", "套衛採後鉸鏈，開到底的門片", "預算在到達後方，產品尚未核。", "",
        "便器450×700、900淋浴不縮。", "公衛盆600×450；套衛保留", "原900×550盆櫃，轉右牆排列。", "兩衛浴均有700操作帶試排。"], 600, 180, step=31)
    s.lines(["不能直接定案：", "套衛名義4.536㎡，115假設後3.6091㎡；", "公衛名義4.83㎡，115假設後3.8709㎡。", "完成面、門組、角閥、馬桶管距、櫃門與", "排水坡／地漏及排氣均未知。", "不把本體放得下當面積要求已達標。"], 600, 775, step=31, class_="small")
    s.lines(["床／浴廁門直角投影已錯開，梳妝台放前臂避床；完整鏡面、斜視線及坐向仍未核。",
        "普通兩衛浴不是1F照護衛浴；新後窗保留自然通風候選，不等開窗權利或排氣已核。"], 30, 930, step=33, class_="small")
    return s.output()


def states_sheet(report):
    s = Sheet("B嚴格04｜兩版各三態：家具不消失、搬運不借另一版", report)
    s.text("一樓六種使用狀態均保留來源；此圖只讀後段，門外巷道／抬桿／人員掃掠仍未取得。", 30, 117)
    for n, opt in enumerate(report["options"]):
        for k, st in enumerate(opt["states"]):
            ox, oy = 30+k*460, 185+n*395
            s.text(("後門" if n == 0 else "前門")+"／"+{"daily": "日常", "ritual": "祭祀", "carry": "搬轎"}[st["id"]], ox, oy-20, class_="label")
            plan = Plan(s, (ox, oy), .039, (0, 9100))
            plan.rooms(st["floor1"]["rooms"], min_y=9100)
            # shrine-front ends at9100 and is omitted; carry offering is explicitly listed below.
            parked = [i for r in st["floor1"]["rooms"] if r["id"].endswith(":shrine-front") for i in r["furniture"]]
            if parked:
                s.text("供桌移原前廳停放點；原尺寸保留。", ox+250, oy+45, class_="tiny")
            s.text("保留後門庫入口" if n == 0 else "長凳／供桌分時整備", ox+250, oy+92, class_="tiny")
            s.text("本體1200×1700" if n == 0 else "1730名義門未核成品", ox+250, oy+123, class_="tiny")
            s.text("不等裝桿完成外廓。", ox+250, oy+154, class_="tiny")
    s.lines(["前移神桌的排法已排除：它會縮掉樓梯後方轉向帶；本案只向右255，前後版的原搬轎條件不互相挪用。",
        "1F後右1200×1200淋浴、後左庫與洗衣設備不動；乾背櫃加寬2030，右公共段改1330名義寬。"], 30, 961, step=31, class_="small")
    return s.output()


def index_html(report):
    opt = report["options"][0]
    measurements = table(["項目", "本案結果", "判讀"], [
        ["一樓祭祀門／神桌", "同軸x3655，只右移255；正門1800不縮", "仍朝道路／騎樓"],
        ["完整背櫃上方", "獨立乾室2030×1600；房間用途不是臥室", "禁床、浴廁、洗衣、污水立管"],
        ["上層濕區", "改後右；與背櫃後緣名義距200", "避整廳／背櫃／後左武轎庫投影；管線尚未核"],
        ["L形主臥", "22.398㎡名義；115假設20.1141㎡；150假設19.44㎡", "20㎡目標對完成面很敏感"],
        ["公衛", "4.83㎡名義；115假設3.8709㎡", "普通器具與700操作可排，排氣待核"],
        ["套衛", "4.536㎡名義；115假設3.6091㎡", "尚未達原4.5㎡下限與6㎡目標，不能採用為完成版"],
        ["原家具／後窗", "床、衣櫃、梳妝與900盆櫃不縮；後窗仍2400", "實品、收納操作／鏡面與氣流仍待核"]])
    status_labels = {"control-conflict": "原控制有衝突", "listed-geometry-clear": "列明幾何未見重疊",
        "target-sensitive": "面積未全達／對工差敏感", "conflict": "有衝突"}
    findings = table(["檢查", "結果", "範圍"], [[f["title"], status_labels.get(f["status"], f["status"]), f["note"]] for f in opt["findings"]])
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>B嚴格祭祀排法與Claude交叉檢討</title>
<style>body{{font:17px/1.75 system-ui,sans-serif;background:#f6f8f4;color:#283e47;margin:0}}main{{max-width:1160px;margin:auto;padding:26px 20px 70px}}h1{{font-size:28px}}h2{{font-size:22px}}section{{padding:23px;background:white;border:1px solid #d9e2d8;border-radius:10px;margin:26px 0}}a{{color:#19677c}}.notice{{background:#fff0dc;border-left:5px solid #a86632;padding:17px}}.table{{overflow:auto}}table{{min-width:650px;width:100%;border-collapse:collapse;font-size:15px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #dbe1d9;vertical-align:top}}th{{background:#eef2eb}}img{{display:block;width:100%;height:auto}}nav{{display:flex;gap:15px;flex-wrap:wrap}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf1eb;padding:17px;font-size:14px}}</style></head><body><main>
<h1>B棟：把已知祭祀衝突真正移開</h1><p>本案以完整房間用途及濕區投影檢查，不靠加防水、假天花或只移床。保留後門優先及無後巷前門備案，各三態。</p>
<p class="notice"><strong>嚴格幾何比較，尚未採用。</strong> 已列投影有改善，但套衛完成面積仍有缺口，梁柱、管線、座向、鏡面與成品門等資料未知，不能宣稱「全屋風水沒有任何問題」。原3D及149份控制維持。</p>
<nav><a href="#proposal">新排法</a><a href="#drawings">四張圖</a><a href="#checks">逐項核對</a><a href="#claude">Claude討論</a><a href="../abc-next-v1/index.html">上一輪五項比較</a></nav>
<section id="proposal"><h2>優先研究L形臥室＋獨立乾保護區＋後右濕區</h2>{measurements}<p>一樓背櫃加寬後，右側公共段名義1330mm；兩版的洗衣、後右照護浴室及後左庫不搬。二樓保兩間完整普通衛浴器具，三樓保一間公衛與後段乾區。</p>
<p>從朝街祭祀正門進行祭拜是屋主已確認規矩；不拿其他流派「一般宅門不對神位」的說法反向改掉需求。這份研究以已確認家規為準，再加保守投影條件；沒有把網路文章或模型意見當作統一標準。</p></section>
<section id="drawings"><h2>圖面與狀態</h2><p><a href="B01-rear.svg">後門優先整棟圖</a>／<a href="B02-front.svg">前門備案整棟圖</a>／<a href="B03-upper-detail.svg">L房／兩衛浴細圖</a>／<a href="B04-use-states.svg">一樓兩版六態</a></p>
<img src="B01-rear.svg" width="1400" height="1100" alt="B後門優先：一至三樓與完整神明堂背櫃投影"><img src="B03-upper-detail.svg" width="1400" height="1100" alt="L形臥室與公衛套衛的原尺寸器具、操作與門前圖" loading="lazy"></section>
<section id="checks"><h2>哪些清楚，哪些還沒通過</h2>{findings}<p><a href="review.json">完整尺寸與來源</a>／<a href="decision-and-replies.csv">待決與工程回覆空表</a>。資料未知維持unknown，原66項需求及正式產品回覆沒有被改成通過。</p>
<p>已排除兩條捷徑：只移立管不能消除上層濕區；只把神桌前移，會擋住前門繞到後左庫的局部轉向。主臥不把外包矩形當L形實際面積，套衛不足也不因器具排入就掩蓋。</p></section>
<section id="claude"><h2>Claude Code：已嘗試，尚無回覆或共識</h2><p>上一輪工具全停用的只讀請求17秒逾時，已終止自己的程序組，沒有背景重試，也沒有取得Claude建議。<a href="../../../inputs/references/b-claude-attempt-20261105.json">原始狀態</a>另存；最新排法另寫v2檢討稿。</p>
<p>依屋主要求，耗時雲端討論交另一個WSL終端執行，最多15分鐘；輸出會保留原文、來源與未達共識狀態。這不修改圖面或授權自動採用：</p>
<pre>cd /root/workspace/houseDesignPrepare
python3 scripts/review_b_fengshui_with_claude.py --brief Docs/claude-b-fengshui-followup-v2.md --timeout 900</pre>
<p>將最後的Result路徑貼回來即可。我會逐項核對套衛面積、主臥目標、投影、門片與搬轎，不把Claude單方面回答當兩人共識。</p></section>
<section><h2>下一個實際卡點</h2><p>先請Claude檢討能否在32地坪概念外框內，保背櫃獨立乾區、主臥20㎡及兩衛浴原面積；目前這份不能全部滿足。若仍無法達成，就把兩間衛浴是否共享、主臥面積或基地可建條件的具體取捨交屋主決定，原要求先保留。</p>
<p>本案不是全屋風水保證。梁壓神桌／床、RC背牆、真正方位／路沖、獨立香火排風與補氣、管線及後巷搬運需正式資料才能核實。參考：<a href="https://www.chengji.com.tw/service_detail?item=31">佛具商實務</a>、<a href="https://www.100.com.tw/article/10204">設計媒體背牆整理</a>，只作民俗觀點，不採其化解說法當證明。</p></section>
<p><small>來源 {html.escape(report['source_layout_report_sha256'])}<br>本研究 {html.escape(report['report_hash'])}。靜態比較，未啟動瀏覽器、WebGL或整套3D重建。</small></p></main></body></html>'''


def render(report):
    files = {"B01-rear.svg": whole_sheet(report, report["options"][0]),
        "B02-front.svg": whole_sheet(report, report["options"][1]), "B03-upper-detail.svg": detail_sheet(report),
        "B04-use-states.svg": states_sheet(report), "index.html": index_html(report),
        "review.json": json.dumps(report, ensure_ascii=False, indent=2)+"\n",
        "decision-and-replies.csv": csv_text(report["options"][0]["remaining"])}
    manifest = {"schema": "house-b-strict-study-artifacts-v1", "report_hash": report["report_hash"],
        "sources": report["source_hashes"], "adopted": False,
        "artifacts": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()}}
    files["artifact-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        directory, files = ROOT/OUT, render(report)
        if args.check:
            stale = [name for name, value in files.items() if not (directory/name).is_file() or
                (directory/name).read_bytes() != value.encode()]
            if stale:
                raise ContractError("B strict static outputs stale: "+", ".join(stale))
        else:
            directory.mkdir(parents=True, exist_ok=True)
            for name, value in files.items():
                (directory/name).write_text(value, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "static-study-exported", "artifacts": len(files),
            "options": 2, "states": 6, "controls_unchanged": report["protected_controls_unchanged"],
            "all_requirements_met": False, "claude_consensus": False, "browser": "not-run"}))
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

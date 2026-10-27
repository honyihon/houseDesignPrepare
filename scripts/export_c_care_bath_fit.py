#!/usr/bin/env python3
"""Export a small static dimension-budget study; never regenerate any 3D scene."""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

# Direct script execution otherwise sees scripts/ but not the local package.
# Resolve against this file, never the caller's working directory or installs.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from house_design.c_care_bath_fit import OUT, build_study  # noqa: E402
from house_design.contracts import ROOT, write_json  # noqa: E402

INDEX = OUT+".html"


def render_index(study):
    esc = html.escape
    measures = study["measurements"]
    measured = ''.join(f'<tr><th scope="row">{esc(r["label"])}</th><td>{r["nominal_mm"]:g}mm</td>'
                       f'<td>{esc(r["interpretation"])}</td></tr>' for r in measures)
    headers = ''.join('<th scope="col">'+esc(r["label"])+'</th>' for r in measures)
    cases = ''.join('<tr><th scope="row">'+esc(case["label"])+'</th>'+''.join(
        f'<td class="{r["status"]}" data-margin="{r["id"]}">{r["remaining_mm"]:g}mm</td>' for r in case["results"])
        +'</tr>' for case in study["cases"])
    params = ''.join('<details><summary>'+esc(c["label"])+'</summary><dl>'+''.join(
        '<dt>'+esc(k)+'</dt><dd>'+str(v)+'mm</dd>' for k, v in c["parameters"].items())+'</dl></details>' for c in study["cases"])
    products = ''.join('<details data-product="'+p["id"]+'"><summary>'+esc(p["label"])+' — 尚未選品</summary><p>'
        +esc(p["required_check"])+'</p><p>原模型包絡 [x,y,寬,深,底高,高] mm：<code>'+esc(json.dumps(p["nominal_envelope_mm"]))
        +'</code></p><p>品牌、型號、尺寸圖、安裝圖、查核人、日期及文件雜湊均未知；未給任何通過信用。</p></details>' for p in study["products"])
    buffers = ''.join('<tr><th scope="row">'+esc(r["label"])+'</th><td>'+f'{r["extra_nominal_gap_to_keep_optional_buffer_mm"]:g}'
                     +'mm</td></tr>' for r in study["recommendations"])
    return ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>C套衛｜完成面、公差與選品檢核</title><style>'
        'body{font:16px/1.65 system-ui,sans-serif;max-width:1120px;margin:auto;padding:20px;background:#f8faf8;color:#24382e}'
        'a{color:#17634d}h1{font-size:1.8rem}h2{font-size:1.35rem;margin-top:1.8em}'
        '.warning{padding:14px;background:#fff1d6;color:#65430b;border-left:4px solid #bd7618}'
        '.scroll{max-width:100%;overflow:auto;margin:14px 0}.scroll:focus{outline:3px solid #17634d}'
        'table{border-collapse:collapse;width:100%}th,td{border:1px solid #cbd5ce;padding:10px;text-align:left;vertical-align:top}'
        'caption{text-align:left;margin-bottom:10px;font-weight:600}.matrix{min-width:1080px}.matrix td{white-space:nowrap}'
        '.negative-budget{background:#fce5e1;color:#852b1f}.zero-spare{background:#fff1d6;color:#65430b}'
        'summary{cursor:pointer;min-height:44px;padding:10px 0}details{border-top:1px solid #cbd5ce}'
        'dt{font-family:monospace;overflow-wrap:anywhere}dd{margin-bottom:8px}code{overflow-wrap:anywhere}'
        'figure{margin:0;overflow:auto;max-height:700px;border:1px solid #cbd5ce}object{display:block;width:780px;height:810px}'
        '@media(max-width:640px){body{padding:12px}h1{font-size:1.55rem}th,td{padding:8px}}'
        '</style></head><body><h1>C 棟套衛：先核尺寸，再定隔間</h1>'
        '<p id="fit-adoption-warning" class="warning">'+esc(study["warning"])+'</p>'
        '<p>原外框2.4×3m、假設扣除後2170×2770mm、三件設備原尺寸及後高窗都不變。本頁只檢查既有座標的餘量，沒有新增配置版本。</p>'
        '<p><a href="c-care-bath.html">原套衛五狀態比較</a> · '
        '<a href="c-care-bath-3d.html?scheme=c-bath-refined&amp;use=transfer#mode=tour&amp;building=C&amp;floor=floor-1&amp;room=C%3Afloor-1%3Aelder-bath&amp;focus=room&amp;view=plan">對應原配置3D</a>'
        ' · <a href="c-care-bath-fit/review.json">檢核座標／參數與來源</a> · <a href="c-care-bath-fit/product-checklist.json">12項選品交付清單</a></p>'
        '<h2>先處理拉門，再確認洗手台與折椅</h2><p class="warning">新發現：門片開啟尾端到假設後完成面只有0mm；洗手台前最後到位點也恰貼盆緣。'
        '原10／15／8.5mm只是其中三個餘量，不代表門組與整套照護已完成。</p>'
        '<ol><li>先取得1200mm名義門組的全開、把手、軌道、止擋及外救援拆卸尺寸。單片1260mm後停放沒有另留止擋，不能直接定案。'
        '若商品仍放不下，優先比較「兩片連動、共同向後收疊」的實際門組，不直接改普通雙扇對開；須重核增加的厚度、淨寬與完整動線，未選型。</li>'
        '<li>洗手台保持600×450mm原尺寸，先核盆緣、龍頭、管路及壁掛支架。不要只縮畫模型或假借檯下空間；目前膝部信用仍為0。</li>'
        '<li>折椅須核含鉸座的收起厚度及全行程，扶手須核底座、握持與補強，不可只拿座板和管徑當完整商品。</li>'
        '<li>最後才協調門位／隔間與設備；保留後窗、830mm戶外帶及原床。不先借臥室或通風帶來掩蓋問題，若確需借用另列比較與代價。</li></ol>'
        '<h2>從HTML／3D共同座標算出的原餘量</h2><div class="scroll" tabindex="0" role="region" aria-label="原餘量表可左右捲動">'
        '<table><caption>方向性淨距，不是法規或人體運動學結論</caption><thead><tr><th scope="col">位置</th><th scope="col">餘量</th><th scope="col">含義</th></tr></thead><tbody>'
        +measured+'</tbody></table></div>'
        '<h2>七組小範圍壓力研究</h2><p>'+esc(study["assumption_note"])+'</p>'
        '<p>負數＝原固定試線／預留的方向性預算不足；0＝沒有多餘空間；正數也不等於核可。這不是自動重排、整間不可行的證明或發生機率。'
        '牆面假設讓貼牆設備跟著完成面內移；門框與把手另外按各自參數扣，不重複當作115mm牆厚。</p>'
        '<div class="scroll" tabindex="0" role="region" aria-label="七組壓力研究餘量可左右捲動"><table class="matrix"><caption>各情境剩餘餘量，單位mm</caption>'
        '<thead><tr><th scope="col">假設情境</th>'+headers+'</tr></thead><tbody>'+cases+'</tbody></table></div>'
        '<details><summary>查看每組參數（非實測／法規）</summary>'+params+'</details>'
        '<h2>若想多留30mm討論餘量，需要多少空間</h2><p>下列數字是相對不利組合的「額外名義淨距」，不是隔間移動量或設備縮小量。'
        '30mm僅供比較，未寫入原需求，也不是照護安全標準。不能把各項直接相加成房間加大需求。</p>'
        '<table><thead><tr><th scope="col">位置</th><th scope="col">需額外增加的名義淨距</th></tr></thead><tbody>'+buffers+'</tbody></table>'
        '<h2>12項商品／工程交付清單</h2><p>尚未選任何品牌型號。帶這份清單找門窗、衛浴、水電／防水及照護專業，取得資料後才回套；圖面與產品不同時必須重新驗證。</p>'
        +products+'<h2>原配置放大圖（未按壓力情境改動）</h2>'
        '<figure><object type="image/svg+xml" data="c-care-bath/c-bath-refined_transfer_detail.svg" aria-label="原配置套衛放大圖">'
        '<a href="c-care-bath/c-bath-refined_transfer_detail.svg">開啟原套衛放大圖</a></object></figure>'
        '<h2>仍未解決的使用條件</h2><p>轉位仍借濕淋浴地面且須分時；折椅／扶手放下與關門的阻擋反例保留。'
        '私人臥室穿越、實際輪椅／照護／救援、承重補強、合法開窗、排風、防水及消防未核。沒有把既有passed升級為施工核可。</p>'
        '<p>本頁為新靜態檢核表，尚未瀏覽器目視驗收；原版畫面證據不涵蓋本頁。原配置與需求不改，來源雜湊可在檢核JSON核對。</p></body></html>')


def write_study(study, root: Path = ROOT):
    write_json(root / OUT / "review.json", study)
    write_json(root / OUT / "product-checklist.json", {
        "schema": "house-c-care-bath-product-checklist-v1", "status": study["status"], "adopted": False,
        "base_plan_hash": study["base_plan_hash"], "report_hash": study["report_hash"], "products": study["products"],
        "professional_status": study["professional_status"]})
    (root / INDEX).write_text(render_index(study), encoding="utf-8")
    return {"index": INDEX, "report": OUT+"/review.json", "cases": len(study["cases"]),
            "products": len(study["products"]), "geometry_changed": False, "rendered_qa": "not-run"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check current sources and budgets without writing files or opening a browser")
    args = parser.parse_args(argv)
    study = build_study()
    result = ({"status": "files-and-budgets-checked-not-rendered", "cases": len(study["cases"]),
               "products": len(study["products"]), "sources": len(study["source_hashes"]),
               "geometry_changed": False, "rendered_qa": "not-run"} if args.check else write_study(study))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Small static planning map from existing IDs; never changes requirements or scenes."""
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

from house_design.contracts import ContractError  # noqa: E402
from house_design.project_next_steps import OUT, build  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402


def markdown(r):
    lines = ["# ABC下一階段決策與條件總表", "", "由inputs/project-status.json既有work_items衍生；不另存已確認需求或自動採用。", "",
        "現在只做預先規劃，實際資料到齊後再統一合圖。原需求／情境狀態按原檔列示，不因本表建議而更改。", ""]
    for row in r["rows"]:
        lines += ["## "+row["id"]+"｜"+row["title"], "", "建議方向："+row["recommendation"], "", "現在可準備：", ""]
        lines += ["- "+v for v in row["prepare_now"]]
        lines += ["", "資料進來後：", "", *("- "+v for v in row["when_data_arrives"])]
        lines += ["", "屆時才需討論："+(row["decision_if_needed"] or "目前沒有新增要屋主立即選的題目。"), "",
            "依賴議題："+(", ".join(row["depends_on"]) or "無前置議題；不表示已有實測／核可。"), ""]
        lines += ["原清單引用："+(", ".join(v["id"]+"="+v["status"] for v in row["formal_requirements"]+row["formal_register_items"]) or "導覽／維護議題，沒有代替正式需求狀態。"), ""]
        lines += ["來源："+"／".join("["+s["path"]+"](../../../"+s["path"]+")" for s in row["sources"]), ""]
    lines += ["## 保留完整清單", "", "本表不是全量驗收或完成率。未列為優先的需求／情境ID完整列於review.json，仍由原需求與planning-register維護。", "",
        "來源綁定 "+r["report_hash"], "瀏覽器／WebGL未執行，法規、風水、照護、搬運及施工核可未知。"]
    return "\n".join(lines)+"\n"


def index_html(r):
    esc = html.escape
    cards = []
    for row in r["rows"]:
        needs = "、".join(row["depends_on"]) or "無；可先備妥資料接口"
        sources = "／".join('<a href="../../../'+esc(v["path"], quote=True)+'">'+esc(v["path"])+"</a>"+
            ("（歷史來源已改，只作比較）" if v["indexed_source_state"] == "source-changed-rebuild-required" else "")
            for v in row["sources"])
        formal = "；".join(v["id"]+"＝"+v["status"] for v in row["formal_requirements"]+row["formal_register_items"])
        now = "".join("<li>"+esc(v)+"</li>" for v in row["prepare_now"])
        later = "".join("<li>"+esc(v)+"</li>" for v in row["when_data_arrives"])
        cards.append(f'''<section id="{esc(row['id'], quote=True)}"><h2>{esc(row['id'])}｜{esc(row['title'])}</h2><p>棟別：{esc('／'.join(row['building_ids']))}；導覽狀態：{esc(row['navigation_task_status'])}</p>
<p><strong>建議方向：</strong>{esc(row['recommendation'])}</p><h3>現在可先準備</h3><ul>{now}</ul><h3>實際資料進來後</h3><ul>{later}</ul>
<p><strong>屆時才需討論：</strong>{esc(row['decision_if_needed'] or '目前沒有新增要屋主立即選的題目。')}</p><p>前置議題：{esc(needs)}。前置項目未有實測，不妨礙先完成本列的預先規劃。</p>
<details><summary>原清單及來源，不是已採用</summary><p>{esc(formal or '導覽／維護議題；不代替正式需求狀態。')}</p><p>{sources}</p></details></section>''')
    quick = table(["議題", "棟別", "建議先保留什麼", "屆時需要決定"],
        [[row["id"]+"｜"+row["title"], "／".join(row["building_ids"]), row["recommendation"],
          row["decision_if_needed"] or "現在不用新增決定"] for row in r["rows"] if row["priority"] == 2])
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ABC決策與條件總表</title><style>body{{font:16px/1.7 system-ui,sans-serif;color:#263e49;background:#fafbf8;margin:0}}main{{max-width:1200px;margin:auto;padding:24px}}h1{{font-size:27px}}h2{{font-size:21px}}h3{{font-size:17px}}.note{{border-left:5px solid #a74e32;background:#fff0e8;padding:16px}}section{{border-top:1px solid #b7c6bf;padding:18px 0}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #b7c6bf;padding:10px;text-align:left;vertical-align:top;overflow-wrap:anywhere}}.table{{overflow-x:auto}}small{{overflow-wrap:anywhere}}a{{color:#176b83}}</style></head><body><main>
<h1>ABC下一階段：決策與條件總表</h1><p class="note">只做預先規劃／未採用。{len(r['rows'])}個既有導覽議題整理為現在可準備、等資料後重算與屆時再討論。實際條件收到0筆，原需求／情境／圖面不改，不把本表當完整設計或專業核可。</p>
<p>來源為同一份project-status工作索引，不另建已確認需求表。原{r['summary']['formal_requirement_count']}項需求與{r['summary']['formal_register_count']}項情境仍由原清單維護。這只是優先議題，不是完成率；其餘項目在JSON明列保留，不當已解決。</p>
<p><a href="../../../Docs/project-status-v1.md">目前入口</a>／<a href="../../../Docs/project-next-steps-v1.md">使用邊界</a>／<a href="project-next-steps.md">可列印閱讀版Markdown</a>／<a href="work-items.csv">建商／家庭討論CSV</a>／<a href="review.json">來源及全部引用</a></p>
<div class="table">{quick}</div><p>A套衛、B浴廁外窗／原面積及C照護續版是獨立取捨，不能把不同方案的優點拼成完成案。全熱新風先保接口，不因此改成接受無窗／縮房。後巷／通行權／後牆開孔各自核實。</p>
{''.join(cards)}<p><a href="../../../inputs/planning-register.json">完整情境清單</a>／<a href="../../../inputs/requirements.json">正式需求狀態</a>／<a href="artifact-manifest.json">產物雜湊</a></p>
<small>本表 {esc(r['report_hash'])}<br>原149控制保留，未啟動瀏覽器／WebGL或全套pytest；數值、畫面、使用者採用及專業簽認分開。</small></main></body></html>'''


def render(r):
    files = {"index.html": index_html(r), "project-next-steps.md": markdown(r),
        "work-items.csv": csv_text(r["rows"]), "review.json": json.dumps(r, ensure_ascii=False, indent=2)+"\n"}
    manifest = {"schema": "house-project-next-steps-artifacts-v1", "report_hash": r["report_hash"],
        "file_hashes": r["file_hashes"], "adopted": False,
        "artifacts": {name: hashlib.sha256(data.encode()).hexdigest() for name, data in files.items()}}
    files["artifact-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        r = build(ROOT)
        files, out = render(r), ROOT/OUT
        if args.check:
            stale = [p for p, data in files.items() if not (out/p).is_file() or (out/p).read_bytes() != data.encode()]
            if stale:
                raise ContractError("Next-step map stale: "+", ".join(stale))
        else:
            out.mkdir(parents=True, exist_ok=True)
            for p, data in files.items():
                (out/p).write_text(data, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "artifacts": len(files),
            "navigation_tasks": len(r["rows"]), "formal_requirement_changes": 0, "formal_register_changes": 0,
            "actual_conditions_received": 0, "protected_controls": r["protected_controls_unchanged"],
            "adopted": False, "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

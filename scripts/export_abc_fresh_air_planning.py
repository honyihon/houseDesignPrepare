#!/usr/bin/env python3
"""Generate planning-only intake templates; actual conditions never overwrite primary drawings."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.abc_fresh_air_planning import (  # noqa: E402
    CSV_FIELDS,
    OUT,
    build,
    context,
    input_template,
    load_input,
)
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402

STATUS = {"pending": "待資料／人工核對", "conflict": "條件衝突，需重比", "numeric-fit": "僅數值相容",
    "condition-recorded": "已記錄所提供條件，未簽認"}
CHOICES = {"retain-both-await-conditions": "前後兩案保留，等待條件", "compare-rear-default-first": "優先比較後口預設",
    "compare-front-fallback-first": "優先比較前口備案", "reroute-required-no-party-wall-assumption": "兩端條件衝突，須重排，不能借未確認共壁"}


def template_for(report, schema):
    return input_template({"report_hash": report["baseline_report_hash"]}, report["registry"], schema)


def template_csv(report):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for key, f in report["registry"].items():
        writer.writerow({"id": key, "label": f["label"], "unit": f["unit"], "value": "", "source": "", "date": "",
            "model_ref": "", "baseline_report_hash": report["baseline_report_hash"], "registry_hash": report["registry_hash"]})
    return stream.getvalue()


def display(value):
    if value is None:
        return "待資料（不是0／false）"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def index_html(report):
    esc = html.escape
    totals = "、".join(STATUS[k]+" "+str(v)+"項" for k, v in report["summary"].items())
    checks = table(["檢核", "狀態", "缺項／說明", "下一步"], [[c["label"], STATUS[c["status"]],
        c.get("reason") or ("；".join(c["missing"]) if c["missing"] else "依輸入比較；仍未簽認"), c["next_action"]] for c in report["checks"]])
    conditions = table(["欄位ID", "條件／單位", "收到的值", "來源／日期", "受影響檢核"],
        [[r["id"], r["label"]+"｜"+r["unit"], display(report["input_records"][r["id"]]["value"]),
          str(report["input_records"][r["id"]]["source"] or "未提供")+"／"+str(report["input_records"][r["id"]]["date"] or "未提供"),
          ", ".join(r["affected_checks"])] for r in report["impact_map"]])
    choices = table(["分區", "條件提示（不是自動採用）", "不變條件"],
        [[c["network"], CHOICES[c["next_comparison"]], "前後搬轎與外口各自獨立；兩案均保留"] for c in report["comparison_choices"]])
    fixed = "".join("<li>"+esc(v)+"</li>" for v in report["fixed_requirements"])
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ABC條件式預先規劃／資料套入入口</title><style>body{{font:16px/1.7 system-ui,sans-serif;background:#fafbf8;color:#263e49;margin:0}}main{{max-width:1400px;padding:24px;margin:auto}}h1{{font-size:27px}}h2{{font-size:21px}}.warning{{background:#fff0e8;border-left:5px solid #a64e32;padding:16px}}table{{border-collapse:collapse;width:100%;margin:16px 0}}td,th{{padding:9px;border:1px solid #bac9c3;text-align:left;vertical-align:top;overflow-wrap:anywhere}}section{{overflow-x:auto}}small{{overflow-wrap:anywhere}}a{{color:#176b83}}code{{overflow-wrap:anywhere}}</style></head><body><main>
<h1>ABC條件式預先規劃：現在準備，資料到了再重算</h1>
<p class="warning">只做預先規劃，未採用／未整合施工資料。收到 {report['conditions_received']}／{report['conditions_total']} 欄條件。缺資料保留待核，不當0、不當false，也不是設計已失敗。即使全部數值相容，也不會自動修改原ABC或3D、不鎖機型／台數、不核發法規／風水／照護／施工核可。</p>
<p>{esc(totals)}。原149份控制及B前後兩版三態保留。這批先支援新風／機電介面，不代表全專案已完成參數化。</p>
<nav><a href="#workflow">怎麼用</a> · <a href="#alternatives">B前後備案</a> · <a href="#checks">影響與待核</a> · <a href="#conditions">條件表</a> · <a href="#fixed">固定條件</a></nav>
<h2 id="workflow">等資料來之前不用先填數字</h2><p>固定需求、研究假設、實際資料分開保存。未填表仍能先看要準備什麼；有部分資料就先重算受影響項目，不用等全部到齊。模板每欄填value／unit／source／date，JSON的未知用null，CSV則留空。</p>
<p><a href="conditions-template.json">JSON空白輸入表</a>／<a href="conditions-template.csv">CSV空白輸入表</a>，選一種作輸入，不合併衝突。向量按欄位單位順序、尺寸全為mm；來源需有圖號／量測紀錄與日期。產品尺寸／曲線另填model_ref，必須對上該區候選機型版次。舊版基準、混型號、欄位錯誤、重複ID或非有限數值會拒收。</p>
<p>輸入後預設只讀列摘要；明確指定新的<code>inputs/private/</code>子目錄才保存獨立結果。不自動覆寫原設計、既有輸入或歷史結果。<a href="../../../Docs/abc-conditional-planning-v1.md">填寫方式與日後重算指令</a>。</p>
<h2 id="alternatives">條件只決定先比較哪個，不自動採用</h2>{choices}
<p>後巷有無、後牆能否開孔是兩個欄位。外牆條件按樓層／側向候選組分開，不把B2許可套給B3。兩端都不合就列重排，不借未確認共壁、不縮房間或放寬家規。</p>
<h2>可重算的範圍</h2><p>含管接主機包絡、四管橫排／雙層、梁下與目標天花、濾芯側抽、整機拆換完成淨孔、低負載風量與同風量靜壓、各外口高位實牆。尺寸相容只是一項算術比較，不證明整條三維路由或實際運出。價格、法規、完整場地模型與家規變更不從空表推定。</p>
<section id="checks"><h2>條件檢核與下一步</h2>{checks}</section>
<section id="conditions"><h2>可分批填寫的條件與影響對照</h2>{conditions}</section>
<h2 id="fixed">不能被輸入表改掉的需求</h2><ul>{fixed}</ul>
<h2>資料下載與原圖</h2><ul><li><a href="condition-dictionary.csv">固定欄位／單位字典</a></li><li><a href="impact-map.csv">欄位→受影響檢核</a></li><li><a href="checks.csv">待核／衝突清單</a></li><li><a href="alternatives.csv">前後備案提示</a></li><li><a href="../abc-fresh-air-detail-v1/index.html">既有路由與剖面比較，未改圖</a></li><li><a href="review.json">條件、數值比較及來源JSON</a></li><li><a href="artifact-manifest.json">產物雜湊</a></li></ul>
<small>基準 {esc(report['baseline_report_hash'])}<br>本批 {esc(report['report_hash'])}<br>檔案／小範圍檢查；未啟動瀏覽器、WebGL、全套pytest或外部AI。資料全部相容仍有人工簽認關卡，未自動採用。</small></main></body></html>'''


def render(report, schema):
    files = {"index.html": index_html(report),
        "conditions-template.json": json.dumps(template_for(report, schema), ensure_ascii=False, indent=2, allow_nan=False)+"\n",
        "conditions-template.csv": template_csv(report), "condition-dictionary.csv": csv_text(list(report["registry"].values())),
        "impact-map.csv": csv_text(report["impact_map"]), "checks.csv": csv_text(report["checks"]),
        "alternatives.csv": csv_text(report["comparison_choices"]),
        "review.json": json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n"}
    manifest = {"schema": "house-abc-fresh-air-planning-artifacts-v1", "report_hash": report["report_hash"],
        "baseline_report_hash": report["baseline_report_hash"], "source_hashes": report["source_hashes"],
        "actual_integration_performed": False, "adopted": False,
        "artifacts": {key: hashlib.sha256(text.encode()).hexdigest() for key, text in files.items()}}
    files["artifact-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)+"\n"
    return files


def private_target(root, name):
    root = Path(root).resolve()
    original = root/Path(name)
    path = original.resolve()
    private = root/"inputs/private"
    if private.resolve() != private or path == private or not path.is_relative_to(private):
        raise ContractError("Actual condition files/results must use a specific inputs/private child; never overwrite source drawings")
    if original.is_symlink() or path.exists():
        raise ContractError("Refusing to overwrite an existing input or result; choose a new private path")
    return path


def write_new_result(root, name, files):
    target = private_target(root, name)
    target.mkdir(parents=True, exist_ok=False)
    for key, text in files.items():
        with (target/key).open("x", encoding="utf-8", newline="") as stream:
            stream.write(text)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="only check the frozen empty-input planning artifacts")
    parser.add_argument("--inputs", help="existing JSON or CSV condition file; default summary only")
    parser.add_argument("--out", help="new specific inputs/private child directory for actual-condition output")
    parser.add_argument("--init-input", help="new inputs/private .json/.csv template; refuses overwrite")
    args = parser.parse_args(argv)
    if args.check and (args.inputs or args.out or args.init_input):
        parser.error("--check cannot be combined with actual inputs/output/initialization")
    if args.init_input and (args.inputs or args.out):
        parser.error("--init-input cannot be combined with actual inputs/output")
    if args.out and not args.inputs:
        parser.error("--out requires --inputs; generated empty planning files have a fixed output")
    try:
        cfg, parent, fields = context(ROOT)
        if args.init_input:
            target = private_target(ROOT, args.init_input)
            if target.suffix.lower() not in {".json", ".csv"}:
                raise ContractError("Initialize only a JSON or CSV condition file")
            report = build(ROOT)
            text = (json.dumps(template_for(report, cfg["input_schema"]), ensure_ascii=False, indent=2)+"\n"
                if target.suffix.lower() == ".json" else template_csv(report))
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8", newline="") as stream:
                stream.write(text)
            print(json.dumps({"status": "empty-private-template-created", "path": str(target), "primary_written": False}))
            return 0
        document = input_sha = None
        if args.inputs:
            source = ROOT/args.inputs
            document, input_sha = load_input(source, fields, cfg)
        report = build(ROOT, document, input_sha)
        out = None
        if args.inputs:
            if args.out:
                out = write_new_result(ROOT, args.out, render(report, cfg["input_schema"]))
        else:
            files, out = render(report, cfg["input_schema"]), ROOT/OUT
            if args.check:
                stale = [key for key, text in files.items() if not (out/key).is_file() or (out/key).read_bytes() != text.encode()]
                if stale:
                    raise ContractError("Planning artifacts stale: "+", ".join(stale))
            else:
                out.mkdir(parents=True, exist_ok=True)
                for key, text in files.items():
                    (out/key).write_text(text, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "independent-comparison" if args.inputs else "empty-planning-exported",
            "conditions_received": report["conditions_received"], "conditions_total": report["conditions_total"],
            "checks": report["summary"], "protected_controls_unchanged": report["protected_controls_unchanged"],
            "output_written": str(out) if out else None, "primary_or_3d_written": False, "actual_integration_performed": False,
            "adopted": False, "professional_approval": "unknown", "browser": "not-run"}))
        return 0
    except (ContractError, OSError, UnicodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

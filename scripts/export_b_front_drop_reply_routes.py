#!/usr/bin/env python3
"""Export conditional research routes; optionally read one explicit private arithmetic result."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from house_design.b_front_drop_reply_routes import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_roof_equipment import private_path  # noqa: E402
from scripts.export_builder_communication import page  # noqa: E402


def route_rows(report):
    return [{"路線ID":r["id"],"議題":r["title"],"本次資料觸發":r["activated_for_declared_inputs"],
        "目前範圍":"研究下一步，不是採用" if r["activated_for_declared_inputs"] else "本次未觸發，不代表排除",
        "原問題ID":"／".join(r["gate_ids"]),"接續動作":r["next_action"],"保留條件":r["retained"],
        "不能由此推定":r["not_authorized"],"估價範圍ID":"／".join(r["quote_scope_ids"]),"何時請屋主取捨":r["owner_decision_when"],
        "決策節點":report["config"]["sequence_id"],"原比較":report["config"]["comparison_id"],
        **dict.fromkeys(["同版依據及回覆","窗口及期限","完整替代方案版次","屋主選擇及日期","專業核對","施工圖發行"],"")}
        for r in report["reply_actions"]]


def quote_rows(report):
    return [{"範圍ID":r["id"],"項目":r["title"],"類別":r["kind"],"應含範圍":r["scope"],"估價口徑":r["pricing_rule"],
        "互斥設計組":"BFC-02／03／04，僅比較不相加" if r["id"] in report["alternative_scope_ids_not_to_add_together"] else "",
        **dict.fromkeys(["實際圖號及版次","已議定承作範圍","原契約已含或折抵","研究設計費及幣別","施工價及幣別","數量及計價單位","費用差額","工期影響","保固責任","不包含項","屋主選擇及日期"],"")}
        for r in report["quote_scopes"]]


def render(r):
    files={"response-routes.csv":csv_text(route_rows(r)),"quote-scopes.csv":csv_text(quote_rows(r))}
    body='<h1>B前排水：回覆後先研究什麼、費用怎樣比</h1><p class="note">條件式研究路線，沒有新格局或採用；缺資料不等於失敗，局部數字相容也不放行。</p>'
    body+='<p>本批收到'+str(r["condition_values_received"])+('個宣告值，來自明確指定的私人算式結果。' if r["condition_report_imported"] else '個實際值，只有空白接口。')+'未被本次資料觸發的路線仍保留。合法前終端是共同前提，後續局部研究不能據此自動解除。</p>'
    body+='<h2>依回覆分流</h2>'+table(["ID","議題","本次狀態","下一步研究","保留／不能省略","何時請屋主取捨"],[[a["id"],a["title"],"研究下一步，不是採用" if a["activated_for_declared_inputs"] else "本次未觸發，不代表排除",a["next_action"],a["retained"]+a["not_authorized"],a["owner_decision_when"]] for a in r["reply_actions"]])
    body+='<h2>同範圍估價，互斥方案不相加</h2>'+table(["ID","類別","項目","應含範圍","估價口徑"],[[a[k] for k in ["id","kind","title","scope","pricing_rule"]] for a in r["quote_scopes"]])
    body+='<p>共通工作只列一次；G4D局部、前濕區重排、G5鏡像為互斥研究方向。先列是否原契約已含，再比較同口徑差額；目前金額、幣別、工期與選擇全空白，不作自動總額或宣稱哪個最便宜。</p>'
    body+='<h2>使用方式</h2><p>本頁沿SEQ-04／BC-CMP-01與原BFD八題，不新增正式需求或比較案。回覆與可建、宗教、搬運、聲學、RF容量及施工發行分開；原ABC／3D、家規與搬轎兩版保留。</p>'
    body+='<p>'+"／".join('<a href="'+n+'">'+html.escape(n)+'</a>' for n in files)+'</p><p><a href="review.json">同版依據與分流</a>／<a href="artifact-manifest.json">產物清單</a></p><small>本批 '+r["report_hash"]+'。沒有新AI、瀏覽器／3D或專業核可。</small>'
    files["index.html"]=page("B前排水回覆與估價分流",body)
    files["review.json"]=json.dumps(r,ensure_ascii=False,indent=2)+"\n"
    files["artifact-manifest.json"]=json.dumps({"schema":"house-b-front-drop-reply-routes-artifacts-v1","report_hash":r["report_hash"],
        "source_hashes":r["source_hashes"],"adopted":False,"artifacts":{n:hashlib.sha256(v.encode()).hexdigest() for n,v in files.items()}},ensure_ascii=False,indent=2)+"\n"
    return files


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--result",help="An explicit source-verified G4D private review.json, never a glob or automatic search")
    parser.add_argument("--output",help="New inputs/private result directory")
    args=parser.parse_args(argv)
    try:
        if bool(args.result)!=bool(args.output) or args.check and args.result:
            raise ContractError("Use one private result and a new private output; --check checks only the public blank baseline")
        document=None
        if args.result:
            source=private_path(ROOT,args.result)
            if source.stat().st_size>1_000_000:
                raise ContractError("G4D arithmetic result exceeds1MB")
            document=json.loads(source.read_text(encoding="utf-8"))
        out=private_path(ROOT,args.output,new=True) if args.output else ROOT/OUT
        report=build(ROOT,document)
        files=render(report)
        if args.check:
            if any(not (out/n).is_file() or (out/n).read_bytes()!=v.encode() for n,v in files.items()):
                raise ContractError("G4D reply routes stale")
        else:
            out.mkdir(parents=True,exist_ok=not bool(args.result))
            for n,v in files.items():
                (out/n).write_text(v,encoding="utf-8",newline="")
        print(json.dumps({"status":"checked" if args.check else "private-reply-routing" if args.result else "exported","files":len(files),
            "routes":len(report["reply_actions"]),"quote_scopes":len(report["quote_scopes"]),"active_research_actions":report["active_action_ids"],
            "condition_values_received":report["condition_values_received"],"selected_layout":None,"adopted":False,"browser":"not-run"}))
        return 0
    except (OSError,ValueError,KeyError) as exc:
        print(str(exc),file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

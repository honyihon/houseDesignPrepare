#!/usr/bin/env python3
"""Export blank follow-up records or summarize one explicit private meeting record."""
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

from house_design.abc_meeting_followup import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_roof_equipment import private_path  # noqa: E402
from scripts.export_builder_communication import page, ul  # noqa: E402

LABELS={"not-received":"尚未收到","partial":"回報部分收到，待核","received-for-review":"回報已收到，內容待核",
    "conflict-reported":"回報有衝突，需完整替代","unknown":"未知","requested":"已提出回覆需求","documented":"回報有紀錄，未驗真",
    "not-recorded":"尚未記錄","deferred":"已明示暫緩，範圍依紀錄"}


def ledger_rows(r):
    return [{"議程ID":x["slot_id"],"議題":x["topic"],"原問題ID":"／".join(x["question_ids"]),
        "資料回覆狀態":LABELS[x["reply_state"]],"回覆收到日期":x["reply_received_date"] or "",
        "回覆摘要":x["reply_summary"],"回覆來源":x["reply_reference"],"回覆圖面版次":x["drawing_revision"],
        "待補項目":"；".join(x["missing_items"]),"已議定窗口":x["agreed_contact"],"回覆期限":x["agreed_due_date"] or "",
        "費用工期紀錄狀態":LABELS[x["cost_schedule_state"]],"費用工期依據":x["cost_schedule_reference"],
        "屋主選擇紀錄狀態":LABELS[x["owner_choice_state"]],"屋主選擇範圍":x["owner_choice_scope"],"屋主選擇依據":x["owner_choice_reference"],"屋主選擇日期":x["owner_choice_date"] or "",
        "專業文件紀錄狀態":LABELS[x["professional_record_state"]],"專業文件範圍":x["professional_scope"],"專業文件依據":x["professional_reference"],"專業文件日期":x["professional_record_date"] or "",
        "圖面發行紀錄狀態":LABELS[x["drawing_release_record_state"]],"圖面發行版次":x["drawing_release_revision"],"圖面發行窗口":x["drawing_release_issuer"],"圖面發行依據":x["drawing_release_reference"],"圖面發行日期":x["drawing_release_date"] or "",
        "受影響圖號":"／".join(x["affected_drawing_ids"]),"工具核准施工":"否；文件內容與權責另核"}
        for x in r["slot_evaluations"]]


def render(r):
    files={"record-template.json":json.dumps(r["record_template"],ensure_ascii=False,indent=2)+"\n",
        "followup-ledger.csv":csv_text(ledger_rows(r))}
    body='<h1>ABC會後回覆與變更追蹤</h1><p class="note">沿用六段COORD議程與原BC問題，只整理宣告紀錄，不採用、不認證文件內容或權責，也不放行施工。</p>'
    body+='<p>目前'+('明確匯入一份私人紀錄。' if r["actual_record_imported"] else '只有空白模板，沒有實際回覆。')+'回報收到'+str(r["replies_reported"])+"段資料；回報專業文件"+str(r["professional_records_documented"])+"段、發行紀錄"+str(r["drawing_release_records_documented"])+"段。收到／已選擇／有文件／已發行紀錄均分開，不由任一欄推定其他欄。</p>"
    body+='<h2>使用原則</h2>'+ul(r["config"]["operating_rules"])
    body+='<h2>六段回覆紀錄</h2>'+table(["議程","回覆","待補","已議定窗口／期限","費用工期","屋主選擇","專業文件","發行紀錄"],
        [[x["slot_id"]+"｜"+x["topic"],LABELS[x["reply_state"]],"；".join(x["missing_items"]) or "尚未列報",x["agreed_contact"]+"／"+(x["agreed_due_date"] or "未議定"),LABELS[x["cost_schedule_state"]],LABELS[x["owner_choice_state"]],LABELS[x["professional_record_state"]],LABELS[x["drawing_release_record_state"]]] for x in r["slot_evaluations"]])
    body+='<p>文件及圖面只回報存在，未驗內容、權責或有效版次；期限不自動判逾期，缺件不自動關閉或封鎖整個專案。B家規、前後搬轎版、A另與設計師談及C原照護範圍保留。</p>'
    body+='<p>'+"／".join('<a href="'+n+'">'+html.escape(n)+'</a>' for n in files)+'</p><p><a href="review.json">來源與紀錄狀態</a>／<a href="artifact-manifest.json">產物清單</a></p><small>本批 '+r["report_hash"]+'。沒有自動讀其他私人資料、寄信、安排會議、改需求／圖面或專業核可。</small>'
    files["index.html"]=page("ABC會後回覆追蹤",body)
    files["review.json"]=json.dumps(r,ensure_ascii=False,indent=2)+"\n"
    files["artifact-manifest.json"]=json.dumps({"schema":"house-abc-meeting-followup-artifacts-v1","report_hash":r["report_hash"],
        "source_hashes":r["source_hashes"],"adopted":False,"artifacts":{n:hashlib.sha256(v.encode()).hexdigest() for n,v in files.items()}},ensure_ascii=False,indent=2)+"\n"
    return files


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check",action="store_true")
    p.add_argument("--records")
    p.add_argument("--output")
    args=p.parse_args(argv)
    try:
        if bool(args.records)!=bool(args.output) or args.check and args.records:
            raise ContractError("Use one explicit private record and a new private output; --check checks the blank public baseline")
        document=None
        if args.records:
            source=private_path(ROOT,args.records)
            if source.stat().st_size>1_000_000:
                raise ContractError("Meeting record exceeds1MB")
            document=json.loads(source.read_text(encoding="utf-8"))
        out=private_path(ROOT,args.output,new=True) if args.output else ROOT/OUT
        report=build(ROOT,document)
        files=render(report)
        if args.check:
            if any(not (out/n).is_file() or (out/n).read_bytes()!=v.encode() for n,v in files.items()):
                raise ContractError("Meeting follow-up baseline stale")
        else:
            out.mkdir(parents=True,exist_ok=not bool(args.records))
            for n,v in files.items():
                (out/n).write_text(v,encoding="utf-8",newline="")
        print(json.dumps({"status":"checked" if args.check else "private-record-summary" if args.records else "exported","files":len(files),
            "slots":len(report["slot_evaluations"]),"replies_reported":report["replies_reported"],"protected_controls":report["protected_controls_unchanged"],
            "automatically_closed_records":0,"adopted":False,"construction_release":False,"browser":"not-run"}))
        return 0
    except (OSError,ValueError,KeyError) as exc:
        print(str(exc),file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export blank G4D builder interface or explicitly requested new private arithmetic result."""
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

from house_design.b_front_drop_conditions import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_roof_equipment import private_path  # noqa: E402
from scripts.export_builder_communication import page  # noqa: E402


def gate_reply_rows(report):
    return [{"問題ID":g["id"],"議題":g["topic"],"建議窗口未議定":g["roles"],"請交回":g["deliver"],
        "最晚核對工序":g["before"],"未成立時先保留":g["if_unresolved"],
        "原決策節點":report["config"]["sequence_id"],"原比較":report["config"]["comparison_id"],"依據研究hash":report["parent_report_hash"],
        **dict.fromkeys(["回覆狀態","圖號版次及標高基準","文件或產品依據","建商專業回覆","費用工期保固","已議定窗口","回覆期限","屋主選擇及日期","專業核對","施工圖發行"],"")}
        for g in report["engineering_gates"]]


def render(r):
    files={"actual-data-template.json":json.dumps(r["condition_template"],ensure_ascii=False,indent=2)+"\n",
        "field-guide.csv":csv_text(r["field_guide"]),"builder-replies.csv":csv_text(gate_reply_rows(r)),
        "local-evaluations.csv":csv_text(r["condition_evaluations"])}
    brief=("# B前排水：建商第一次同版核對\n\n"
        "這是G4D條件式預先規劃，未選落差、未併主3D；神桌與兩種搬轎版保留。請先回合法接管與完整前出路線，再給騎樓上游、梯底及管件完整包絡。\n\n"
        "先開index.html。八題用同一圖號、版次與標高基準回覆；尚未議定的窗口、期限、費用及所有專業／屋主選擇留白。數字相容不自動解除未核工項。\n\n")
    for g in r["engineering_gates"]:
        brief += f"- {g['id']} {g['topic']}：{g['deliver']} 最晚在{g['before']}核對。\n"
    brief += "\nactual-data-template.json另存inputs/private後分批填，未知用null；field-guide.csv說明口徑。只允許同一個研究框回算，改井位／樓梯／分段坡度時先另立版次。\n\n"
    brief += "符合數字只回報局部算式，不驗法規、水力、結構、宗教、搬運或施工。沒有合法前終端時不得默認地下穿祭祀；需完整替代再交屋主討論。\n"
    files["meeting-brief.md"]=brief
    body='<h1>B前排水：建商回覆與資料回套接口</h1><p class="note">預先規劃／未採用。先核合法接管、騎樓上游及完整梯底／管件包絡；不選500或600、不改主3D或家規。</p>'
    body+='<p>目前收到'+str(r["condition_values_received"])+('個宣告值。這是新私人重算結果，無施工放行。' if r["condition_document_hash"] else '個實際值，全部欄位留白。現在無須屋主補實測。')+'</p>'
    body+='<h2>會議順序與八題</h2>'+table(["ID","要問什麼","建議協作窗口，未議定","請交回","最晚工序","未成立時"],[[g[k] for k in ["id","topic","roles","deliver","before","if_unresolved"]] for g in r["engineering_gates"]])
    body+='<h2>回套結果只算局部</h2>'+table(["區段","狀態","尚缺欄位","局部相容","施工放行"],[[x["id"],x["status"],"／".join(x["missing_fields"]),"未知" if x["dimension_or_interval_compatible_only"] is None else str(x["dimension_or_interval_compatible_only"]),"否"] for x in r["condition_evaluations"]])
    body+='<p>落差下限取整盒最高管頂＋上凸＋上方安裝＋額外餘量－最低梯底，且不得負；上限取整盒最低管底－下凸－下方操作空間－完成地坪－所需淨高。有效落差不是直管下料長度，兩界缺一就保持未知，不自動選取。</p>'
    body+='<p>前終端只核宣告等坡段的落差算術，不由上方管頂推管內底；文件documented代表有資料待核，不能當合法授權。上游只核宣告點，平面只比原G4D框，均不是整條路線成立。</p>'
    body+='<h2>欄位、單位與口徑</h2>'+table(["區段","欄位","名稱","單位","口徑"],[[f[k] for k in ["group","field","label","unit","meaning"]] for f in r["field_guide"]])
    body+='<h2>收到資料後怎樣用</h2><p>下載空白JSON另存私人條件檔，分批填；非空欄位要有來源與同一圖面版次，標高要有共同基準，空白不能改成0。每次另產新私人結果，不覆寫原討論或已填回覆。</p>'
    body+='<p>'+"／".join('<a href="'+n+'">'+html.escape(n)+'</a>' for n in files)+'</p><p><a href="review.json">同版依據</a>／<a href="artifact-manifest.json">產物清單</a></p><small>本批 '+r["report_hash"]+'。沒有新瀏覽器／AI或專業驗收，不自動更新屋主需求、格局、開孔、選材或施工圖。</small>'
    files["index.html"]=page("B前排水建商回覆接口",body)
    files["review.json"]=json.dumps(r,ensure_ascii=False,indent=2)+"\n"
    files["artifact-manifest.json"]=json.dumps({"schema":"house-b-front-drop-conditions-artifacts-v1","report_hash":r["report_hash"],
        "source_hashes":r["source_hashes"],"adopted":False,"artifacts":{n:hashlib.sha256(v.encode()).hexdigest() for n,v in files.items()}},ensure_ascii=False,indent=2)+"\n"
    return files


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check",action="store_true")
    p.add_argument("--conditions")
    p.add_argument("--output")
    args=p.parse_args(argv)
    try:
        if bool(args.conditions) != bool(args.output) or args.check and args.conditions:
            raise ContractError("Use conditions with a new private output; --check checks the blank public baseline")
        document=None
        if args.conditions:
            source=private_path(ROOT,args.conditions)
            if source.stat().st_size>1_000_000:
                raise ContractError("G4D condition document exceeds1MB")
            document=json.loads(source.read_text(encoding="utf-8"))
        out=private_path(ROOT,args.output,new=True) if args.output else ROOT/OUT
        report=build(ROOT,document)
        files=render(report)
        if args.check:
            if any(not (out/n).is_file() or (out/n).read_bytes()!=v.encode() for n,v in files.items()):
                raise ContractError("G4D builder interface stale")
        else:
            out.mkdir(parents=True,exist_ok=not bool(args.conditions))
            for n,v in files.items():
                (out/n).write_text(v,encoding="utf-8",newline="")
        print(json.dumps({"status":"checked" if args.check else "private-recalculation" if args.conditions else "exported","files":len(files),
            "fields":len(report["field_guide"]),"gates":len(report["engineering_gates"]),"condition_values_received":report["condition_values_received"],
            "protected_controls":report["protected_controls_unchanged"],"selected_drop":None,"adopted":False,"browser":"not-run"}))
        return 0
    except (OSError,ValueError,KeyError) as exc:
        print(str(exc),file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

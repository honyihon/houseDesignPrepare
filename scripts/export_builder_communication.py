#!/usr/bin/env python3
"""Export a small builder meeting kit, or initialize new private reply records."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.builder_communication import OUT, build  # noqa: E402
from house_design.contracts import ContractError  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402


def forms(plan):
    replies = [{"問題ID": q["id"], "階段": q["stage"], "棟別": "/".join(q["buildings"]),
        "議題": q["title"], "提問": q["ask"], "應交資料": q["evidence"], "關聯議題ID": "/".join(q["task_ids"]),
        **dict.fromkeys(["圖號版次", "回覆狀態", "建商回覆", "依據文件", "回覆窗口", "回覆期限", "下次動作",
            "屋主選擇", "專業審查狀態", "施工圖發行"], "")} for q in plan["questions"]]
    interfaces = [{"介面ID": a["id"], "應討論階段": a["stage"], "項目": a["topic"],
        "建商側建議提供": a["builder"], "A設計師側建議提供": a["designer"], "共同核對": a["joint"],
        "應交資料": a["evidence"], **dict.fromkeys(["已議定設計方", "已議定施工方", "已議定供料方", "圖面提供人",
            "最晚決定日", "保固銜接約定", "核對狀態", "建商確認", "設計師確認", "屋主確認", "依據圖號版次"], "")}
        for a in plan["a_interfaces"]]
    quotes = [{"估價包ID": q["id"], "棟別": q["buildings"], "估價範圍": q["topic"], "計價邊界": q["boundary"],
        **dict.fromkeys(["完整方案ID及狀態", "圖號版次", "廠商及報價編號", "報價日期及有效期", "型號規格及尺寸",
            "數量單位", "標配含項", "取消折抵", "追加材料", "追加工資", "配件供電排水吊運", "測試調試及交付",
            "不含項", "稅金", "同範圍總額", "工期及付款條件", "保固及責任介面", "替代品條件", "待補資料", "屋主選擇"], "")}
        for q in plan["quote_packages"]]
    blanks = {
        "meeting-decisions.csv": ["會議ID", "日期", "參與角色", "階段", "問題或介面ID", "棟別方案及狀態", "圖號版次",
            "討論結論", "屋主選擇", "屋主確認日期及依據", "專業審查狀態及依據", "施工圖發行依據",
            "未解項", "下一步", "負責窗口", "回覆期限", "覆查依據"],
        "change-log.csv": ["變更ID", "日期", "關聯問題或決定ID", "棟別方案及狀態", "原圖號版次", "新圖號版次",
            "變更原因", "原作法", "新作法", "影響功能淨尺寸及上下層", "影響專業及責任方", "標配折抵", "追加含稅差額",
            "工期影響", "保固影響", "替代方案", "屋主選擇及日期", "專業審查及依據", "施工圖發行依據", "舊版停用通知"],
        "inspection-log.csv": ["檢查ID", "工序及覆蓋節點", "棟別位置", "圖號版次", "約定通知時間", "測試方法及判定依據",
            "見證及責任窗口", "實施日期", "尺寸照片及原始紀錄", "結果", "缺失", "改善期限", "覆查日期及結果", "覆蓋前確認依據"],
        "drawing-register.csv": ["文件ID", "日期", "棟別樓層", "完整方案及使用狀態", "圖名圖號", "版次", "提供人",
            "檔案位置", "使用目的", "取代舊版", "發行確認依據", "待核事項", "已通知角色"]}
    return {"builder-replies.csv": csv_text(replies), "a-interface-matrix.csv": csv_text(interfaces),
        "same-scope-quotes.csv": csv_text(quotes),
        **{name: csv_text([dict.fromkeys(columns, "")]) for name, columns in blanks.items()}}


def ul(values):
    return "<ul>"+"".join("<li>"+html.escape(v)+"</li>" for v in values)+"</ul>"


def page(title, body):
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{font:16px/1.75 system-ui,sans-serif;color:#263e49;background:#fafbf8;margin:0}}main{{max-width:1200px;margin:auto;padding:24px}}h1{{font-size:28px}}h2{{font-size:23px}}h3{{font-size:19px}}section{{padding:16px 0;border-top:1px solid #bac9c2}}.note{{border-left:5px solid #a74e32;background:#fff0e8;padding:16px}}.table{{overflow:auto}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #bac9c2;padding:10px;text-align:left;vertical-align:top;min-width:125px;overflow-wrap:anywhere}}a{{color:#176b83}}small,code{{overflow-wrap:anywhere}}blockquote{{border-left:3px solid #78978b;margin:0;padding:12px 20px;background:#edf3ef}}@media print{{body{{background:white;font-size:11pt}}main{{padding:0}}.table{{overflow:visible}}th,td{{min-width:0;padding:5px}}a{{color:inherit}}h2,h3{{break-after:avoid}}}}</style></head><body><main>{body}</main></body></html>'''


def first_meeting(plan):
    first = plan["first_meeting"]
    agenda = table(["時間", "要談什麼"], [[a["minutes"], a["topic"]] for a in first["agenda"]])
    wanted = set(first["question_ids"])
    questions = "".join("<h3>"+html.escape(q["id"]+"｜"+q["title"])+"</h3><p>"+html.escape(q["ask"])+
        "</p><p>請交回："+html.escape(q["evidence"])+"</p>" for q in plan["questions"] if q["id"] in wanted)
    return f'''<h1>第一次與建商討論</h1><p>{html.escape(first['duration'])}。帶這份議程、ABC當次比較圖及五題回覆表即可；完整資料分階段交接。</p>
<p class="note">預先溝通資料；比較圖未作整套採用或施工核可。約32地坪不等於可建量。A裝潢另與設計師討論，基礎工程介面要在預埋前一起核對。</p>
<h2>可直接改寫後給建商的開場</h2><blockquote>{html.escape(first['opening_message'])}</blockquote>
<h2>三棟先看這些目標</h2>{building_brief(plan)}
<h2>建議議程</h2><div class="table">{agenda}</div><h2>本次五題</h2>{questions}<h2>離開會議前記下</h2>{ul(first['finish_with'])}'''


def building_brief(plan):
    rows = [[b["building"], b["known_use"], b["early_topics"]] for b in plan["building_brief"]]
    return '<div class="table">'+table(["棟別", "已述使用", "要提早核對"], rows)+"</div><p>"+html.escape(plan["shared_brief"])+"</p>"


def markdown(r):
    p = r["plan"]
    lines = ["# ABC建商分階段溝通包", "", p["date"]+"｜只做預先規劃；責任分工、圖面及施工另核。", "",
        "## 可先給建商的開場", "", p["first_meeting"]["opening_message"], "", "## 使用方式", ""]
    lines += ["- "+v for v in p["operating_rules"]]
    lines += ["", "## 三棟目標摘要", "", p["shared_brief"], ""]
    lines += ["- "+b["building"]+"："+b["known_use"]+" "+b["early_topics"] for b in p["building_brief"]]
    for s in p["stages"]:
        lines += ["", "## "+s["id"]+"｜"+s["title"], "", "時間："+s["timing"], "", "參與："+s["participants"],
            "", "先準備：", "", *("- "+v for v in s["prepare"]), "", "請交回：", "", *("- "+v for v in s["deliver"]),
            "", "該工項鎖定前："+s["hold"], ""]
        for q in (q for q in p["questions"] if q["stage"] == s["id"]):
            lines += ["### "+q["id"]+"｜"+q["title"], "", q["ask"], "", "應交資料："+q["evidence"], ""]
    lines += ["## A建商／裝潢介面：全部待議定", "", p["owner_direction"]["scope_boundary"], ""]
    for a in p["a_interfaces"]:
        lines += ["### "+a["id"]+"｜"+a["topic"], "", "建商側建議提供："+a["builder"], "", "A設計師側建議提供："+a["designer"],
            "", "共同核對："+a["joint"], "", "應交資料："+a["evidence"], ""]
    lines += ["## 同範圍估價包", ""]
    lines += ["- "+q["id"]+"｜"+q["topic"]+"："+q["boundary"] for q in p["quote_packages"]]
    lines += ["", "所有CSV為空白回覆範本；請先建立私人工作副本再填，生成器不匯入回覆、不採用設計。", "",
        "來源綁定："+r["report_hash"], "瀏覽器未執行；法規、風水、照護、搬運及施工核可未知。"]
    return "\n".join(lines)+"\n"


def index_html(r, form_names):
    e, p = html.escape, r["plan"]
    stages = []
    for s in p["stages"]:
        questions = [[q["id"]+"｜"+"/".join(q["buildings"])+"｜"+q["title"], q["ask"], q["evidence"]]
            for q in p["questions"] if q["stage"] == s["id"]]
        stages.append(f'''<section id="{e(s['id'])}"><h2>{e(s['id']+'｜'+s['title'])}</h2><p>{e(s['timing'])}</p><p>參與：{e(s['participants'])}</p>
<h3>先準備</h3>{ul(s['prepare'])}<h3>請對方交回</h3>{ul(s['deliver'])}<p class="note">該工項鎖定前：{e(s['hold'])}</p>
<details><summary>本階段逐題討論／應交資料</summary><div class="table">{table(['問題','怎麼問','請交回'], questions)}</div></details></section>''')
    links = "／".join('<a href="../../../'+e(v["path"], quote=True)+'">'+e(v["label"])+"</a>" for v in p["references"])
    downloads = "".join('<li><a href="'+e(n)+'">'+e(n)+"</a></li>" for n in form_names)
    matrix = table(["介面／階段", "建商側建議提供", "A設計師側建議提供", "共同核對／應交資料"],
        [[a["id"]+"｜"+a["topic"]+"（"+a["stage"]+"）", a["builder"], a["designer"], a["joint"]+"；"+a["evidence"]] for a in p["a_interfaces"]])
    quotes = table(["估價包", "棟別", "範圍", "計價邊界"], [[q["id"], q["buildings"], q["topic"], q["boundary"]] for q in p["quote_packages"]])
    nav = " → ".join('<a href="#'+s["id"]+'">'+e(s["title"])+"</a>" for s in p["stages"])
    body = f'''<h1>ABC建商分階段溝通包</h1><p>{e(p['date'])}｜先把討論順序、提問、應交資料與工程介面準備好，實際條件到齊後再合圖。</p>
<p class="note">溝通預備／未採用。6階段、22題、11項A介面及12組估價範圍；建商回覆0筆。角色分工是建議議程，尚未議定合約責任。原圖、正式需求及149控制保留；不替代工程簽認。</p>
<p><a href="first-meeting.html">先開這份：第一次會議與開場文字</a>／<a href="communication-guide.md">完整閱讀版</a>／<a href="../../../Docs/builder-communication-v1.md">怎樣使用、建立私人回覆副本</a></p>
<p><strong>討論順序：</strong>{nav}</p><h2>A另談裝潢，基礎工程要早交接</h2><p>{e(p['owner_direction']['a_interior'])}</p><p>{e(p['owner_direction']['scope_boundary'])}</p>
<h2>三棟先看這些目標</h2>{building_brief(p)}<details><summary>每次會議的共同規則</summary>{ul(p['operating_rules'])}</details>{''.join(stages)}
<section id="a-interfaces"><h2>A建商／設計師介面</h2><p>以下是建議提供資料與核對方式；實際設計、供料、施工、測試及保固方逐列議定。A設計師尚未介入時先保留最後決定日，不先代選裝潢。</p><div class="table">{matrix}</div></section>
<section><h2>同範圍報價</h2><p>B前後版、新風系統替代方案、設備候選分開比完整總價，不能全部相加。不得用空白當零元、已含或不需要。</p><div class="table">{quotes}</div></section>
<section><h2>會議回覆與變更怎樣留下</h2><p>提問ID → 對方回覆及依據 → 未解衝突／替代成本 → 屋主選擇 → 相應專業核對 → 發行圖面／停用舊版 → 工程檢查與複驗。每個動作分欄記，不把回覆「可以」當整條流程通過。</p>
<p>先建立新的私人工作副本再填CSV，避免重產公開模板覆蓋紀錄。工具只建立表格，不讀取回覆或自動回填需求／3D。尚未詢問、已答待核、需補資料、需屋主取捨可作回覆狀態；原始空白代表未紀錄。</p><ul>{downloads}</ul></section>
<section><h2>看圖與正式資料</h2><p>{links}</p><p>只帶與本次議題相關的比較圖。歷史研究仍保留，引用前重核來源；這份新表沒有把歷史passed變成新圖通過。</p>
<p><a href="review.json">來源與原議題引用</a>／<a href="artifact-manifest.json">本包產物雜湊</a></p><small>來源 {e(r['report_hash'])}。瀏覽器未執行；法規、家規、照護、搬運與施工核可未知。</small></section>'''
    return page("ABC建商分階段溝通包", body)


def render(r):
    files = forms(r["plan"])
    files.update({"index.html": index_html(r, list(files)), "first-meeting.html": page("第一次與建商討論", first_meeting(r["plan"])),
        "communication-guide.md": markdown(r), "review.json": json.dumps(r, ensure_ascii=False, indent=2)+"\n"})
    manifest = {"schema": "house-builder-communication-artifacts-v1", "report_hash": r["report_hash"],
        "source_hashes": r["source_hashes"], "adopted": False,
        "artifacts": {n: hashlib.sha256(data.encode()).hexdigest() for n, data in files.items()}}
    files["artifact-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)+"\n"
    return files


def init_records(root, relative, report):
    """Create a new ignored workspace; never touch an existing reply directory."""
    root = Path(root).resolve()
    path = PurePosixPath(relative)
    if (not relative or "\\" in relative or path.parts[:2] != ("inputs", "private") or len(path.parts) < 3
            or any(p in {".", ".."} or p.startswith(".") for p in path.parts)):
        raise ContractError("Records must use a new project-relative inputs/private subdirectory")
    target = root.joinpath(*path.parts)
    if not target.resolve().is_relative_to(root/"inputs/private"):
        raise ContractError("Records resolve outside inputs/private")
    target.mkdir(parents=True, exist_ok=False)
    data = forms(report["plan"])
    data["basis-review.json"] = json.dumps(report, ensure_ascii=False, indent=2)+"\n"
    data["RECORDS.md"] = ("# 建商會議私人工作副本\n\n基準來源："+report["report_hash"]+
        "\n\n本目錄CSV可填寫；公開structured/planning/builder-communication仍是空白模板。\n"
        "basis-review.json保留當次議程與來源，請勿覆寫。空白不是零、通過或責任已議定。\n"
        "每次使用同一問題／介面ID記回覆，選擇、專業審查與施工圖發行分開。\n"
        "檔案不會自動回填原需求、圖面或3D；有採用或條件變動仍走正式版次及合圖流程。\n"
        "請自行保管及備份，此私人目錄不進Git。若要給建商／設計師，只分享本次必要副本。\n")
    for name, content in data.items():
        with (target/name).open("x", encoding="utf-8", newline="") as output:
            output.write(content)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--init-records", metavar="inputs/private/NEW-DIRECTORY")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        if args.init_records:
            target = init_records(ROOT, args.init_records, report)
            print(json.dumps({"status": "private-records-created", "path": str(target), "responses_received": 0,
                "design_changes": 0, "adopted": False}))
            return 0
        files, target = render(report), ROOT/OUT
        if args.check:
            stale = [n for n, content in files.items() if not (target/n).is_file() or (target/n).read_bytes() != content.encode()]
            if stale:
                raise ContractError("Builder kit stale: "+", ".join(stale))
        else:
            target.mkdir(parents=True, exist_ok=True)
            for name, content in files.items():
                (target/name).write_text(content, encoding="utf-8", newline="")
        print(json.dumps({"status": "checked" if args.check else "exported", "artifacts": len(files),
            **report["summary"], "protected_controls": report["protected_controls_unchanged"], "browser": "not-run"}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

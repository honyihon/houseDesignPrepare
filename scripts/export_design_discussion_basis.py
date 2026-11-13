#!/usr/bin/env python3
"""Export a self-contained static design discussion package without rendering scenes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.contracts import ContractError  # noqa: E402
from house_design.design_discussion_basis import BASIS_LABELS, OUT, build, readable_copy  # noqa: E402
from house_design.project_status import public_path  # noqa: E402
from scripts.export_abc_laundry_use import MODE_LABELS, duration  # noqa: E402
from scripts.export_abc_meeting_followup import ledger_rows as followup_ledger_rows  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_front_drop_conditions import gate_reply_rows  # noqa: E402
from scripts.export_b_front_drop_reply_routes import quote_rows, route_rows  # noqa: E402
from scripts.export_builder_communication import first_meeting, forms, page, ul  # noqa: E402

NAV = {"index.html": "先讀這頁", "floors.html": "ABC逐層版本", "a-designer-brief.html": "A設計師任務書",
    "a-first-meeting.html": "A首次會議", "decision-sequence.html": "決定順序與節點",
    "abc-coordination.html": "ABC聯席會議",
    "b-drainage-intake.html": "B前排水回覆接口",
    "bc-comparison.html": "B／C比較", "life-walkthrough.html": "生活走查", "systems.html": "長期系統",
    "first-meeting.html": "第一次會議", "source-index.html": "圖面與來源清單"}
ARCHIVE = "ABC-discussion-package.zip"


def frame(title, body, report):
    nav = "／".join('<a href="'+n+'">'+html.escape(label)+"</a>" for n, label in NAV.items())
    return page(title, '<nav aria-label="討論包目錄">'+nav+"</nav><h1>"+html.escape(title)+
        '</h1><p class="note">'+html.escape(report["date"])+
        "｜預先討論基準，未整套採用。B最新局部與C照護續版尚未全部併入整棟；合法可建量、產品及專業核對待資料。A裝潢另談，預埋前共同合圖。</p>"+
        '<p class="note">最新洗衣方向：三棟1F共用一組、C2F先暫不用但保原機位與空間，A2F以上另預留機位。依<a href="life-walkthrough.html#ground-laundry">洗曬平面</a>、<a href="life-walkthrough.html#laundry-access">前側瓶頸／條件式後口</a>及<a href="life-walkthrough.html#laundry-use">日常／雨天輪用</a>討論；原圖內機位保持，未選A為共享主位置。</p>'+
        body+'<hr><small>本包依據 '+report["report_hash"]+
        '。靜態閱讀副本，沒有新瀏覽器／3D或專業驗收；<a href="source-index.html">來源與使用邊界</a>。</small>')


def figures(report, ids):
    attachments = {a["id"]: a for a in report["attachments"]}
    blocks = []
    for key in ids:
        a = attachments[key]
        warning = "（歷史來源已漂移，只作局部研究參考）" if a["package_source_state"] == "source-changed-rebuild-required" else ""
        blocks.append('<figure><figcaption><strong>'+html.escape(a["caption"]+warning)+
            '</strong></figcaption><img loading="lazy" style="width:100%;height:auto" src="'+a["attachment"]+
            '" alt="'+html.escape(a["caption"], quote=True)+'"></figure>')
    return "".join(blocks)


def worksheets(report):
    files = forms(report["builder_meeting_plan"])
    # Extend existing blank forms; keep the frozen builder exporter intact.
    for name,columns in {
        "drawing-register.csv":["檔案格式","原始檔SHA256","所據會議或問題ID","座標與標高基準","完整樓層範圍","缺件或混版說明","本次接收狀態（僅收件）","需同步重核的圖面"],
        "change-log.csv":["原檔SHA256","新檔SHA256","變更範圍與對照依據","需重核的原需求ID","同版模型或差異報告","影響A設計師／建商介面","對應估價或客變單","未解條件及受影響工項"],
        "same-scope-quotes.csv": ["報價比較組ID", "報價列ID", "原契約或基準報價版次", "估價依據文件及SHA256",
            "費用口徑（基準總價／增減差額／替代完整價）", "互斥替代組ID", "重複工項及一次計價歸屬", "跨棟共用工程與分攤依據"],
        "inspection-log.csv": ["對應檢查提醒ID", "本批完整範圍與未檢部分", "材料產品／施工規範版次", "試驗條件及要求值來源",
            "實測值／單位與儀器紀錄", "隱蔽位置圖與原始檔SHA256", "變更／改善關聯ID", "A進場前後基準及責任分界"],
    }.items():
        rows=list(csv.DictReader(io.StringIO(files[name].lstrip("\ufeff"))))
        files[name]=csv_text([{**row,**dict.fromkeys(columns,"")} for row in rows])
    p = report["plan"]
    files["floor-versions.csv"] = csv_text([{"版本列ID": r["id"], "棟別": r["building"], "樓層": r["floor"],
        "底圖ID": "/".join(r["base_assets"]), "局部圖ID": "/".join(r["supplement_assets"]), "使用目的": r["use"],
        "限制及缺口": r["limits"], "原工作議題ID": "/".join(r["task_ids"]), "本次選擇": "", "依據版次": ""}
        for r in p["floor_versions"]])
    files["life-walkthrough.csv"] = csv_text([{"情境ID": r["id"], "棟別": r["building"], "情境": r["scenario"],
        "期待及限制": r["expectation"], "紙上檢視狀態": r["paper_observation"]["state"],
        "現有資料發現": r["paper_observation"]["finding"], "發現來源": "/".join(r["paper_observation"]["source_refs"]),
        "所需依據": r["evidence_needed"], "原情境狀態": r["original_status"],
        **dict.fromkeys(["討論圖號版次", "使用者回饋", "同時使用衝突", "待改事項", "負責窗口", "期限", "證據及專業核對"], "")}
        for r in report["walkthroughs"]])
    files["systems-replies.csv"] = csv_text([{"系統ID": r["id"], "系統": r["topic"], "現在準備": r["prepare"],
        "日後資料": r["data_later"], "應先核對節點": r["hold_before"], "原登錄ID": "/".join(r["register_ids"]),
        **dict.fromkeys(["回覆", "依據文件", "負責窗口", "回覆期限", "費用影響", "工期影響", "屋主選擇", "專業核對"], "")}
        for r in p["systems"]])
    files["bc-comparison-replies.csv"] = csv_text([{"議題ID": r["id"], "棟別": r["building"], "主題": r["topic"],
        "目前比較": r["current"], "替代及代價": r["alternative"], "研究建議": r["recommendation"], "何時需要取捨": r["decision_trigger"],
        **dict.fromkeys(["新圖號版次", "新增資料", "建商設計回覆", "完整費用差額", "屋主選擇", "專業核對"], "")}
        for r in p["bc_comparisons"]])
    files["decision-sequence.csv"] = csv_text([{"順序ID": r["id"], "議題": r["title"], "棟別": "/".join(r["building_ids"]),
        "階段": r["stage"], "現在先做": r["first_action"], "最晚核對工序": r["before_lock"],
        "定案前依據項": "/".join(r["lock_after"]), "須並行核對": "/".join(r["coordinate_with"]),
        "建議協作窗口未議定": r["proposed_lead"], "應交資料": "；".join(r["required_reply"]),
        "暫不決定怎樣保留": r["defer_strategy"], "何時需要屋主取捨": r["decision_when"],
        "原議題ID": "/".join(r["task_ids"]), "建商問題ID": "/".join(r["question_ids"]),
        **dict.fromkeys(["實際最晚日期", "已議定窗口", "資料回覆及依據", "屋主選擇及日期", "專業核對", "施工圖發行"], "")}
        for r in p["decision_sequence"]])
    files["a-first-meeting-replies.csv"] = csv_text([{"問題ID": r["id"], "主題": r["topic"], "提問": r["ask"],
        "建議請交回": r["deliver"], "原任務ID": "/".join(r["brief_ids"]),
        "建商介面ID": "/".join(r["a_interface_ids"]), "節點ID": "/".join(r["sequence_ids"]),
        **dict.fromkeys(["設計師回覆", "所需建商資料", "圖號版次及依據", "回覆窗口", "回覆期限", "屋主回饋", "下次動作"], "")}
        for r in p["a_first_meeting"]["questions"]])
    files["b-review-replies.csv"] = csv_text([{"問題ID": r["id"], "主題": r["topic"], "建議窗口未議定": r["roles"],
        "需回覆": r["reply"], "目前依據狀態": r["basis_status"], "依據研究hash": report["b_review"]["source_report_hash"],
        "原建商問題ID": "/".join(p["b_review_route"]["question_ids"]), "決策節點ID": p["b_review_route"]["sequence_id"],
        "B比較ID": p["b_review_route"]["comparison_id"],
        **dict.fromkeys(["回覆狀態", "同版圖號及證據", "建商專業回覆", "費用工期及保固影響", "已議定窗口", "回覆期限", "屋主選擇及日期", "專業核對", "施工圖發行"], "")}
        for r in report["b_review"]["gates"]])
    files["b-drainage-replies.csv"] = csv_text(gate_reply_rows(report["b_drainage_intake"]))
    files["b-drainage-response-routes.csv"] = csv_text(route_rows(report["b_drainage_reply_routes"]))
    files["b-drainage-quote-scopes.csv"] = csv_text(quote_rows(report["b_drainage_reply_routes"]))
    followup_rows={r["議程ID"]:r for r in followup_ledger_rows(report["coordination_followup"])}
    files["abc-coordination-actions.csv"] = csv_text([{"議程ID":r["id"],"建議分鐘":str(r["start_minute"])+"–"+str(r["end_minute"]),
        "議題":r["title"],"棟別":"／".join(r["buildings"]),"建議窗口未議定":r["proposed_lead"],"請帶回":r["request"],
        "保留條件":r["retain"],"何時需屋主取捨":r["decision_when"],"原問題ID":"／".join(r["question_ids"]),
        "原工作ID":"／".join(r["task_ids"]),"工程節點ID":"／".join(r["sequence_ids"]),
        **dict.fromkeys(["本次回覆","圖號版次及來源","已議定窗口","回覆期限","下次動作","費用工期影響","屋主選擇及日期","專業核對","施工圖發行"],""),
        **followup_rows[r["id"]]}
        for r in report["coordination_agenda"]["slots"]])
    return files


def local_refs(names, filename, titles):
    return "、".join('<a href="'+filename+"#"+html.escape(key, quote=True)+'">'+html.escape(key+"｜"+titles[key])+"</a>" for key in names) or "無額外前項；可先備資料"


def b_review_section(report):
    route, review = report["plan"]["b_review_route"], report["b_review"]
    assets = {a["id"]: a for a in report["attachments"]}
    body = '<section id="b-review-route"><h2>B條件回覆與退回路線</h2><p>'+html.escape(route["purpose"])+"</p>"
    if review["known_capacity_conflict"]:
        body += ('<p class="note"><strong>已知需求缺口：</strong>RF原目標'+str(review["original_RF_target_sqm"])+
            '㎡，固定前帶在尚不扣設備的樂觀上界為'+str(review["fixed_front_optimistic_upper_bound_sqm"])+
            '㎡，仍差'+str(review["known_RF_shortfall_sqm"])+
            '㎡。即使其他回覆都說「可以」，也不能把Q3整套視為滿足。需同版完整重排解除，或另經屋主明示的需求取捨；本次沒有縮減目標。</p>')
    body += "<p><strong>現在可繼續：</strong>獨立研究、同版回覆、替代成本與工序核對。這張表不採用任何方案、不進行專業核可或施工圖發行。</p>"
    body += ('<p>前排水另沿SEQ-04／BC-CMP-01使用<a href="b-drainage-intake.html">G4D八題回覆與28欄接口</a>；先核合法接管、上游及梯底，'
        '數字來後只回算局部，不與RF九題混為同一項已解或新增比較案。</p>')
    body += "<h3>先保留的條件</h3>"+ul(route["preserve"])+"<h3>跟建商依序談</h3>"+ul(route["meeting_order"])
    body += ('<p><a href="b-review-replies.csv">九項同版工程回覆表</a>沿用BQG-01～09，接'+html.escape("／".join(route["question_ids"]))+
        '、SEQ-04及BC-CMP-07；沒有新增正式需求或比較案。依據研究hash：'+html.escape(review["source_report_hash"])+"。</p>")
    body += '<div class="table">'+table(["ID", "議題", "目前依據狀態", "需交回"], [[r["id"], r["topic"],
        "已知24㎡不足，完整修正待核" if r["basis_status"] == "known-capacity-conflict" else "待同版專業證據", r["reply"]] for r in review["gates"]])+"</div>"
    for row in review["fallbacks"]:
        body += '<section id="'+row["id"]+'"><h3>'+html.escape(row["id"]+"｜"+row["title"])+"</h3>"
        for label, key in [("何時比較", "trigger"), ("下一個動作", "action"), ("尚未成立或不能省略", "limits"), ("估價範圍，未議定", "cost_scope")]:
            body += "<p><strong>"+label+"：</strong>"+html.escape(row[key])+"</p>"
        body += "<p>對照圖："+"／".join('<a href="'+assets[k]["attachment"]+'">'+html.escape(k)+"</a>" for k in row["assets"])+"</p></section>"
    body += '<p>收到回覆後沿<a href="#reply-workflow">原五步流程</a>核同版、完整功能、費用及工期，再記屋主選擇、專業審查及正式發行。口頭可以、單門寬相容或測試passed都不是已採用。</p></section>'
    return body


def drainage_page(report):
    intake = report["b_drainage_intake"]
    routes = report["b_drainage_reply_routes"]
    body = ('<p>沿SEQ-04／BC-CMP-01與B-WET-001收同版資料，未新增比較或正式需求。現在不用屋主補實測；先請建商統籌合法接管、騎樓上游、梯底與完整管件包絡。</p>'
        '<p class="note">公開模板0個實際值。數字相容只表示局部算式，不能放行施工、不改家規或兩種搬轎版，也不自動選500／600mm。</p>'
        '<p><a href="b-drainage-replies.csv">八題回覆CSV</a>／<a href="b-drainage-conditions.json">28欄空白JSON</a>／<a href="#response-routes">回覆後怎樣分流與估價</a>／<a href="bc-comparison.html#BC-CMP-01">原比較與代價</a>。</p>')
    for g in intake["engineering_gates"]:
        body += '<section id="'+g["id"]+'"><h2>'+html.escape(g["id"]+"｜"+g["topic"])+"</h2>"
        for label,key in [("建議窗口，未議定","roles"),("請交回","deliver"),("最晚核對工序","before"),("未成立時先保留","if_unresolved")]:
            body += "<p><strong>"+label+"：</strong>"+html.escape(g[key])+"</p>"
        body += "</section>"
    body += '<section id="response-routes"><h2>回覆後的研究與估價分流</h2><p>本包沒有實際回覆，目前只觸發資料未齊；下列各路線供日後同版核對，未觸發不代表排除。合法前終端是共同前提，任何後續局部研究都不能自動解除；多個問題會同時保留。</p>'
    body += table(["路線ID","議題","下一步研究","保留與限制","何時請屋主取捨"],[[a["id"],a["title"],a["next_action"],a["retained"]+a["not_authorized"],a["owner_decision_when"]] for a in routes["reply_actions"]])
    body += '<h3>六種估價範圍</h3>'+table(["範圍ID","項目","應含範圍","估價口徑"],[[q[k] for k in ["id","title","scope","pricing_rule"]] for q in routes["quote_scopes"]])
    body += ('<p>共通工作只列一次；G4D局部、前濕區重排及G5鏡像是互斥研究方向，不能把三套當同時施作相加。目前金額、工期、原約已含／折抵及選擇全空白，沒有自動總額。</p>'
        '<p><a href="b-drainage-response-routes.csv">七條回覆研究路線CSV</a>／<a href="b-drainage-quote-scopes.csv">六種同範圍估價CSV</a>。日後明確指定私人算式結果才重核原條件並產新私人分流，不讀取或匯入本包。</p></section>')
    body += '<h2>分批資料的欄位口徑</h2><p>未知保留null，不能當0；每個非空區段要來源、共同圖號版次，有標高就需共同datum_id，平面要coordinate_note。數字來源是否確實同版仍需人工對圖。四組分開，單點上游或單段埋管不代表全線完成。</p>'
    body += table(["區段","欄位","名稱","單位","口徑"],[[f[k] for k in ["group","field","label","unit","meaning"]] for f in intake["field_guide"]])
    body += ('<h2>回覆來後怎樣用</h2><p>CSV先另存私人工作副本；將空白JSON另存專案inputs/private後分批填，使用'
        'scripts/export_b_front_drop_conditions.py --conditions inputs/private/b-front-drop-conditions-001.json --output inputs/private/b-front-drop-result-001'
        '另產新私人結果。原快照及資料不覆寫，結果也不自動匯入交付包。</p>'
        '<p>局部落差從實體包絡頂／底起算；前輪已扣操作空間的預算不能當實體管底再扣一次。有效落差不是直管下料長；合流、水力通氣、防火及清掃仍由專業完整核算。前終端documented僅記有文件待核，不自動認定權利或合法。</p>'
        '<p>原研究框、梯核或路線改變就先另立研究版次；回覆與估價沿<a href="decision-sequence.html#reply-workflow">既有五步流程</a>，有具體衝突才回屋主討論。</p>')
    return frame("B前排水：建商回覆與條件接口",body,report)


def sequence_page(report):
    p = report["plan"]
    titles = {r["id"]: r["title"] for r in p["decision_sequence"]}
    stages = {r["id"]: r["title"] for r in report["builder_meeting_plan"]["stages"]}
    body = ("<p>先用SEQ-01核基地／範圍、SEQ-02啟動A設計師訪談；各棟格局研究可先備資料，未要求現在全部定案。</p>"
        "<p>「定案前依據項」只列鎖定受影響工項前的前提，不阻擋先準備。「須並行核對」可來回修正，不是一條單向等待鏈。實際日期、窗口、選擇及核可目前留白，須依建商排程和各方約定填。</p>"
        '<p><a href="decision-sequence.csv">12項決定順序及回覆表</a>／<a href="a-first-meeting.html">A設計師第一次怎麼談</a>／<a href="#b-review-route">B條件回覆與退回路線</a>／<a href="#reply-workflow">回覆收到後的五步</a></p>')
    body += "<p>"+html.escape(p["workflow_scope"])+"</p>"
    for r in p["decision_sequence"]:
        body += '<section id="'+r["id"]+'"><h2>'+html.escape(r["id"]+"｜"+r["title"])+"</h2>"
        body += "<p>棟別："+"／".join(r["building_ids"])+"｜討論階段："+html.escape(r["stage"]+" "+stages[r["stage"]])+"</p>"
        body += "<p><strong>現在先做：</strong>"+html.escape(r["first_action"])+"</p>"
        body += '<p class="note"><strong>最晚核對工序：</strong>'+html.escape(r["before_lock"])+"。實際日期待建商排程。</p>"
        body += "<p>建議協作窗口（未議定）："+html.escape(r["proposed_lead"])+"</p>"
        body += "<h3>請對方交回</h3>"+ul(r["required_reply"])
        body += "<p><strong>暫不決定怎樣保留：</strong>"+html.escape(r["defer_strategy"])+"</p>"
        body += "<p><strong>何時才要屋主取捨：</strong>"+html.escape(r["decision_when"])+"</p>"
        body += "<p>定案前依據項："+local_refs(r["lock_after"], "decision-sequence.html", titles)+"</p>"
        body += "<p>須並行核對："+local_refs(r["coordinate_with"], "decision-sequence.html", titles)+"</p></section>"
        if r["id"] == p["b_review_route"]["sequence_id"]:
            body += b_review_section(report)
        if r["id"] == "SEQ-10":
            body += quote_review_section(report)
        if r["id"] == "SEQ-11":
            body += inspection_review_section(report)
    body += '<section id="reply-workflow"><h2>回覆收到後怎樣處理</h2><p>以下是建議人工核對流程，沒有自動讀取私人回覆、採用或改圖。</p>'
    for r in p["reply_workflow"]:
        body += "<h3>"+html.escape(r["id"]+"｜"+r["title"])+"</h3><p>"+html.escape(r["action"])+"</p><p>下一步："+html.escape(r["outcome"])+"</p>"
        body += "<p>記錄在："+"／".join('<a href="'+name+'">'+name+"</a>" for name in r["records"])+"</p>"
    return frame("ABC決定順序、最晚工序與回覆銜接", body+"</section>", report)


def quote_review_section(report):
    guide = report["plan"]["quote_review"]
    packages = {r["id"]: r for r in report["builder_meeting_plan"]["quote_packages"]}
    body = '<section id="quote-review"><h2>同範圍報價怎麼核對</h2><p>'+html.escape(guide["purpose"])+"</p>"
    body += '<p><a href="same-scope-quotes.csv">原12組估價表，增比較組／列ID及計價歸屬欄</a>。每家廠商、方案及價單版次各列；分類ID保留，實際報價、折抵、稅金、付款及選擇全部留白。</p>'
    body += ul(guide["principles"])
    body += '<h3>核價六步</h3><ol>'+"".join("<li><strong>"+html.escape(s["title"])+"</strong>："+html.escape(s["check"])+"</li>" for s in guide["steps"])+"</ol>"
    body += '<h3>原12組最容易漏項或重複的地方</h3><div class="table">'+table(
        ["原估價議題", "容易混淆的範圍", "請交回或逐項核對", "原問題／A介面"],
        [[r["package_id"]+"｜"+packages[r["package_id"]]["topic"], r["risk"], r["ask"],
            "／".join(r["question_ids"]+r["a_interface_ids"])] for r in guide["package_checks"]])+"</div>"
    body += '<p>有不含項、暫估或互斥案時先標待核，不直接比較總價或自動加總。圖面依<a href="source-index.html#drawing-return">回圖核對</a>，實際變更回<a href="change-log.csv">原變更表</a>，A分工回<a href="a-interface-matrix.csv">原介面表</a>；收到價單、屋主選擇、專業核對及正式發行各自記錄。沒有匯入私人報價或新增採購。</p></section>'
    return body


def inspection_review_section(report):
    guide = report["plan"]["inspection_review"]
    body = '<section id="inspection-handoff"><h2>隱蔽工程分批檢查與A裝潢交接</h2><p>'+html.escape(guide["purpose"])+"</p>"
    body += '<p><a href="inspection-log.csv">原工序檢查表，增完整範圍／要求值來源／原始紀錄及A交接欄</a>。以下是提醒，尚無實際工序、查驗、通知或結果；各批檢查ID另編，提醒ID供追溯，不是新增需求或實際驗收通過。</p>'
    body += ul(guide["principles"])
    for row in guide["checkpoints"]:
        body += '<section id="'+row["id"]+'"><h3>'+html.escape(row["id"]+"｜"+row["title"])+"</h3>"
        body += "<p><strong>何時約定及檢查：</strong>"+html.escape(row["before"])+"。</p><p><strong>本批要核：</strong>"+html.escape(row["check"])+"</p>"
        body += "<p><strong>請保留：</strong>"+html.escape(row["evidence"])+"</p><p>棟別："+"／".join(row["buildings"])+"；原問題／A介面／工序："+html.escape("／".join(row["question_ids"]+row["a_interface_ids"]+row["sequence_ids"]))+"。</p></section>"
    body += '<p>日期、窗口、試驗要求值、實測、結果及覆蓋前確認目前全留白；方法與允收依採用設計／產品／規範及相應專業，不自填通用試壓或試水時數。缺失與變更沿<a href="change-log.csv">原變更表</a>，A承作與保固沿<a href="a-interface-matrix.csv">原介面表</a>，所需測試費沿<a href="#quote-review">核價範圍</a>。目前沒有讀取私人檢查紀錄、通知施工方或放行工項。</p></section>'
    return body


def coordination_page(report):
    agenda,p=report["coordination_agenda"],report["plan"]
    floors={r["id"]:r["use"] for r in p["floor_versions"]}
    comparisons={r["id"]:r["topic"] for r in p["bc_comparisons"]}
    sequences={r["id"]:r["title"] for r in p["decision_sequence"]}
    a_briefs={r["id"]:r["topic"] for r in p["a_brief"]}
    systems={r["id"]:r["topic"] for r in p["systems"]}
    questions={r["id"]:r["title"] for r in report["builder_meeting_plan"]["questions"]}
    assets={r["id"]:r for r in report["attachments"]}
    body='<p>'+html.escape(agenda["purpose"])+"</p><p>首次接洽後的格局與預埋聯席會議，建議"+str(agenda["duration_minutes"])+"分鐘，可依實際議程另議；實際日期、出席人與窗口尚未約定，會議尚未舉行。</p>"
    body+='<p><a href="first-meeting.html">首次接洽議程</a>／<a href="a-first-meeting.html">A設計師另談的六題</a>／<a href="abc-coordination-actions.csv">六段聯席待件與行動表</a>。</p>'
    body+='<h2>會前先確認</h2>'+ul(agenda["before_meeting"])+"<h2>建議參與窗口，待議定</h2>"+ul(agenda["participants"])
    body+='<h2>可用的開場文字</h2><blockquote>'+html.escape(agenda["opening_message"])+"</blockquote>"
    body+='<h2>建議議程</h2>'+table(["分鐘","議題","建議窗口，未議定"],[[str(s["start_minute"])+"–"+str(s["end_minute"]),s["title"],s["proposed_lead"]] for s in agenda["slots"]])
    for s in agenda["slots"]:
        body+='<section id="'+s["id"]+'"><h2>'+html.escape(s["id"]+"｜"+s["title"])+"</h2><p>本段目標："+html.escape(s["objective"])+"</p>"
        if s["floor_ids"]:
            body+='<p>先開逐層對照：'+local_refs(s["floor_ids"],"floors.html",floors)+"</p>"
        if s["asset_ids"]:
            body+='<p>本段參考圖：'+"／".join('<a href="'+assets[key]["attachment"]+'">'+html.escape(key+"｜"+assets[key]["caption"])+"</a>" for key in s["asset_ids"])+"。原使用限制隨來源保留。</p>"
        if s["comparison_ids"]:
            body+='<p>比較與代價：'+local_refs(s["comparison_ids"],"bc-comparison.html",comparisons)+"</p>"
        if s["a_brief_ids"]:
            body+='<p>A設計師任務：'+local_refs(s["a_brief_ids"],"a-designer-brief.html",a_briefs)+"</p>"
        if s["a_interface_ids"]:
            body+='<p><a href="a-interface-matrix.csv">A預埋交接介面表</a>：'+html.escape("／".join(s["a_interface_ids"]))+"，承作、供料及保固待逐列議定。</p>"
        if s["system_ids"]:
            body+='<p>共同系統：'+local_refs(s["system_ids"],"systems.html",systems)+"</p>"
        body+='<h3>照這幾題談</h3>'+ul(s["ask"])+"<p><strong>請交回：</strong>"+html.escape(s["request"])+"</p>"
        body+='<p><strong>先保留：</strong>'+html.escape(s["retain"])+"</p><p><strong>何時才請屋主取捨：</strong>"+html.escape(s["decision_when"])+"</p>"
        body+='<p>沿用建商問題：'+html.escape("／".join(q+"｜"+questions[q] for q in s["question_ids"]))+'，填<a href="builder-replies.csv">原問題回覆表</a>。對應工序：'+local_refs(s["sequence_ids"],"decision-sequence.html",sequences)+"。</p>"
        if s["buildings"]==["B"]:
            body+='<p><a href="b-drainage-intake.html">B前排水八題與28欄</a>／<a href="b-drainage-intake.html#response-routes">回覆分流與互斥估價</a>；RF24已知缺口仍見<a href="decision-sequence.html#b-review-route">B條件與退回路線</a>。</p>'
        body+='</section>'
    body+='<h2>離開會議前留下</h2>'+ul(agenda["finish_with"])
    body+='<p><a href="abc-coordination-actions.csv">聯席行動表</a>先另存私人副本再填；已議定窗口、日期、回覆、費用與選擇均空白。各問題仍沿原ID記錄，收到回覆後走<a href="decision-sequence.html#reply-workflow">原五步核對流程</a>；本頁不寄出訊息、不安排會議、不採用或發行施工圖。</p>'
    body+='<section id="after-meeting"><h2>會後回覆、費用與變更追蹤</h2><p>沿用同一六列行動表，不另開問題清單。資料收到／待補、費用工期、屋主選擇、專業文件及圖面發行各自記錄；目前0段實際回覆、會議未回報舉行，所有實際內容留白。</p>'
    body+=table(["要記什麼","需要的依據","不能由此推定"],[
        ["回覆／待補","摘要、收到日、來源與圖面版次；缺件逐列、窗口及期限已議定才填","收到或口頭可以不代表尺寸相容、採用或已核"],
        ["費用工期","原同範圍估價、折抵與變更依據，未議定保留未知","有價單不代表已接受，不自動合計互斥方案"],
        ["屋主選擇","選擇的具體範圍、來源及日期；明示暫緩另記","選擇不等於專業核可或已發行施工圖"],
        ["專業文件","文件範圍、依據及日期；內容與權責人工核","回報有文件不代表工具認證其核可"],
        ["圖面發行紀錄","版次、發行窗口、依據與日期，受影響圖號另列","有紀錄不代表工具授權開工或其他未解項結案"]])
    body+='<p><a href="abc-followup-records.json">六段空白JSON紀錄</a>可另存專案inputs/private後分批填。日後明確指定一份紀錄，使用scripts/export_abc_meeting_followup.py --records inputs/private/abc-followup-records-001.json --output inputs/private/abc-followup-summary-001產新私人摘要；不搜尋或合併舊回覆，也不將私人摘要自動放回本包。</p>'
    body+='<p>沒有約定日期就不判逾期、不自動催辦；任一段缺件不封鎖整個專案。即使各欄都有紀錄也不自動結案，正式需求、家規、兩搬轎版與3D均不回寫，仍沿原五步及有權責方程序處理。</p></section>'
    return frame(agenda["title"],body,report)


def a_meeting_page(report):
    p = report["plan"]["a_first_meeting"]
    seq_titles = {r["id"]: r["title"] for r in report["plan"]["decision_sequence"]}
    body = "<p>"+html.escape(p["duration"])+"</p><p>"+html.escape(p["purpose"])+"</p>"
    body += "<h2>可給設計師的開場文字</h2><blockquote>"+html.escape(p["opening_message"])+"</blockquote>"
    body += '<p>先讀<a href="a-designer-brief.html">A任務書</a>與<a href="floors.html#A-1F">A逐層底圖</a>；11項建商介面見<a href="a-interface-matrix.csv">原介面表</a>。設計師提出的成果與費用按實際服務約定，不由本議程指定合約義務。</p>'
    body += '<h2>建議議程</h2><div class="table">'+table(["時間", "要談什麼"], [[r["minutes"], r["topic"]] for r in p["agenda"]])+"</div><h2>本次六題</h2>"
    for r in p["questions"]:
        body += '<section id="'+r["id"]+'"><h3>'+html.escape(r["id"]+"｜"+r["topic"])+"</h3><p>"+html.escape(r["ask"])+"</p>"
        body += "<p>建議請交回："+html.escape(r["deliver"])+"</p><p>對應工序："+local_refs(r["sequence_ids"], "decision-sequence.html", seq_titles)+"</p>"
        body += "<p>任務／介面："+html.escape("、".join(r["brief_ids"]+r["a_interface_ids"]))+"</p></section>"
    body += "<h2>離開會議前記下</h2>"+ul(p["finish_with"])
    body += '<p><a href="a-first-meeting-replies.csv">六題回覆表</a>用同一問題ID記待件與下一步，不重抄成新需求；<a href="decision-sequence.html#reply-workflow">收到答覆再沿五步核對</a>。</p>'
    return frame("A設計師首次會議：先談格局與預埋", body, report)


def floor_page(report):
    body = "<p>這張表指定每一層現在拿什麼討論，沒有將各張局部圖拼成已完成的整棟。RF對應舊檔floor-4命名，是屋頂／屋突，不能當第四層住宅。</p>"
    for r in report["plan"]["floor_versions"]:
        body += ('<section id="'+r["id"]+'"><h2>'+r["id"]+"</h2><p>"+html.escape(r["use"])+
            '</p><p class="note">'+html.escape(r["limits"])+"</p>")
        if r["supplement_assets"]:
            body += "<h3>先看局部深化與尚未整合之處</h3>"+figures(report, r["supplement_assets"])
        body += "<details><summary>看整層討論底圖／背景對照</summary>"+figures(report, r["base_assets"])+"</details></section>"
    return frame("ABC逐層版本對照", body, report)


def a_brief_page(report):
    p = report["plan"]
    body = ("<p>A已述1F兩人、2F兩人常睡；三樓原用途保留。此任務書供屋主與A設計師討論，建商／設計師的承作、供料、測試與保固須另約定。</p>"
        "<p>每題區分屋主已確認方向、原需求目標、研究建議與待選擇。這些對話依據不會將原正式需求的candidate狀態自動改成已確認；尺寸也不冒充現場量測。</p>")
    for r in p["a_brief"]:
        body += ('<section id="'+r["id"]+'"><h2>'+html.escape(r["id"]+"｜"+r["topic"])+"</h2><p><strong>"+BASIS_LABELS[r["basis"]]+
            "</strong></p><p>"+html.escape(r["instruction"])+"</p><details><summary>依據來源</summary>"+ul(r["source_refs"])+"</details></section>")
    body += "<h2>建議請設計師提出的成果</h2>"+ul(p["a_requested_deliverables"])+figures(report, ["A-care", "A-mdf"])
    body += '<p><a href="a-first-meeting.html">A首次會議議程與六題</a>／<a href="a-interface-matrix.csv">A與建商介面表（待議定）</a>／<a href="floors.html#A-2F">看A二樓底圖與套衛缺口</a></p>'
    body += "<details><summary>原A需求ID／原狀態，保留完整範圍</summary><div class=\"table\">"+table(["ID", "原標題", "原狀態"],
        [[r["id"], r["title"], r["status"]] for r in report["a_original_requirement_references"]])+"</div></details>"
    return frame("A棟裝潢設計師專用討論任務書", body, report)


def comparison_page(report):
    body = "<p>以下比較均未採用。本輪只統整既有研究的完整代價，沒有生成新的B／C格局，也沒有以建商／兩個模型同意取代屋主與專業判斷。</p>"
    for r in report["plan"]["bc_comparisons"]:
        body += '<section id="'+r["id"]+'"><h2>'+html.escape(r["id"]+"｜"+r["topic"])+"</h2>"
        for label, key in [("目前比較", "current"), ("替代與代價", "alternative"), ("建議深化方向", "recommendation"), ("屆時才需取捨", "decision_trigger")]:
            body += "<h3>"+label+"</h3><p>"+html.escape(r[key])+"</p>"
        body += figures(report, r["assets"])+"</section>"
    body += '<p><a href="bc-comparison-replies.csv">B／C比較回覆表</a>：先補同版資料，再記屋主選擇；空白不是已接受縮面積、無窗或取消備案。</p>'
    return frame("B／C尚未完成的同版比較", body, report)


def life_page(report):
    scenario_rows = [[r["id"]+"｜"+r["building"], r["scenario"], r["expectation"],
        r["paper_observation"]["state"]+"："+r["paper_observation"]["finding"], r["evidence_needed"]] for r in report["walkthroughs"]]
    guide = report["storage_owner_review"]
    laundry = report["laundry_preplanning"]
    body = '<section id="ground-laundry"><h2>新方向：長輩一樓共用洗衣、晾衣與A上層機位</h2><p>'+html.escape(laundry["recommendation"])+"</p>"
    body += '<p>以下三張是獨立安裝備位平面，原3D仍未修改；A1優先不減廚房版，加深灣只保代價比較，A2只留位不買機。三棟位置／權利／遮雨通路未知，不畫共壁捷徑或稱全程照護可達；C2原機位與水電、洗曬空間保留，暫不用不等永久取消。</p>'
    body += figures(report, ["LAU-A1-compact", "LAU-A1-deeper", "LAU-A2-reserve"])
    body += '<p>先核三棟合法平層取送、A一樓兩個900名義洞及1040共邊、雨天乾衣容量、噪音、防水、污水終端與完整產品／換機；A另聘設計師與建商在預埋前同版合圖。回饋沿原ABC-DAILY-CHAIN列，不代填接受縮廚房或選定機器。</p></section>'
    access = report["laundry_access"]
    body += '<section id="laundry-access"><h2>續看：到達洗衣區的前側瓶頸與條件式後口</h2><p>'+html.escape(access["recommendation"])+"</p>"
    body += '<p>斜門三角移標不增加可走地面；1040共邊扣兩側115完成預算只810，900本體中心仍不相通。這只否決該固定房界算法，不表示所有前側重排無解；MDF完整維修與孝親房保持。</p>'
    body += '<p>後口1200名義洞先估970淨寬，實際未知；只有全開900試線在基地內不碰列明本體，門外0.63㎡不在核算內。半開與關閉阻路，取送與洗／乾操作須分時。乾衣備位20mm及衣物70mm僅模型間距，不當產品安全距離。</p>'
    body += figures(report, ["LAU-front-screen", "LAU-rear-entry", "LAU-rear-states"])
    body += '<p>A後口及共同後路的權利、轉向、高差、遮雨、防滑、門組與排水待實際資料；B有後巷不能推定A／C可接入。前門協助取送備案保留，未核全程照護可達。回饋仍用ABC-DAILY-CHAIN，不新增必填表，亦未取消原2.232㎡加深代價或小晾架容量等缺口。</p></section>'
    use = report["laundry_use"]
    body += '<section id="laundry-use"><h2>接著比較日常、床單與雨天輪用</h2><p>'+html.escape(use["recommendation"])+"</p>"
    body += '<p class="note">以下批數與分鐘全部是假設壓力示例，不是屋主實際衣量、原廠性能或選機承諾。只洗的結果不含晾乾；洗乾結果先假設每批只需一個乾衣程序，床品適用與洗／乾kg容量待核。</p>'
    timing_rows = [[s["label"], MODE_LABELS[m["mode"]], duration(m["elapsed_min"]),
        "只洗完，晾乾未知" if m["mode"] == "wash-and-air" else "指定洗乾示例，未實測"]
        for s in use["scenarios"] for m in s["modes"]]
    body += table(["假設工作量", "候選方向", "示例時間", "完成口徑"], timing_rows)
    body += figures(report, ["LAU-use-flow", "LAU-use-time"])
    body += '<p>保一組洗衣與旁側平放乾衣機備位，先不買機；小晾架當補充，床品分日、分戶預約。兩機可同跑，但原取放區共用，人工操作錯開；示例窗口不是可連跑或夜間使用核可。籃車停位尚未核，不新增固定櫃占通路。</p>'
    body += '<p>原LAU-03～08續核產品完整安裝／開門／拆換、電力同時負載、合法污水與冷凝水、獨立排濕、噪音振動及A建商／設計師分工。實際批數與容量未知，不把一般全熱當除濕；回饋仍沿ABC-DAILY-CHAIN，沒有新增必填流程。</p></section>'
    body += '<p><a href="systems.html#laundry-roughin">預埋前用這張溝通單對接口</a>：一樓共用候選、A上層備位、C2暫不用保恢復使用分開；沿原建商及A設計師表記錄。</p>'
    body += '<section id="storage-review"><h2>先看各層收納是否符合生活習慣</h2><p>'+html.escape(guide["purpose"])+"</p>"
    body += ('<p>先開<a href="ac-storage-preview.zip">A／C同版收納3D ZIP</a>或<a href="b-upper-storage-3d.zip">B同版上層收納3D ZIP</a>，各自解壓後開index.html。A／C選棟別、樓層，B選B-2F／B-3F／B-RF-D1／D2；依序比原配置、加櫃、特寫、整層與同層平面。展示通過不等於已接受位置或取物習慣。</p>'
        '<p>尺寸沿原案例，平面X×Y有些因櫃體轉向而不同，不是櫃內有效容量；櫃前操作帶不是已核門片淨空。A裝潢仍另與設計師談；B後門預設／前門備案、兩個RF均保留；C2F洗衣機按最新方向暫不用，但原空間不放固定櫃。</p>'
        '<p class="note">優先看C三樓主臥內取物的隱私、A三樓展床後能否取物，以及各RF櫃只供耐候備品。建議是續研方向，尚未替屋主選擇或移櫃。</p>')
    assets = {a["id"]: a for a in report["attachments"]}
    for building in "ABC":
        items = [r for r in guide["items"] if r["building"] == building]
        storage_rows = [[r["case"]+"｜"+r["label"],
            "平面X×Y "+"×".join(str(v) for v in r["rect_mm"][2:])+"mm；高"+str(r["height_mm"])+"mm；櫃前帶"+"×".join(str(v) for v in r["operation_mm"][2:])+"mm",
            r["access"], r["recommendation"], r["check"]] for r in items]
        body += '<h3>'+building+'棟</h3><div class="table">'+table(["棟層／品名", "原研究尺寸", "取物會進哪裡", "建議續研方向", "看圖先確認的代價"], storage_rows)+"</div>"
        if building == "B":
            body += '<p>完整同版平面與梯接口：解壓<a href="b-upper-storage-3d.zip">B同版3D ZIP</a>後開plans.html，或使用檢視器內同層平面連結，按B-2F／B-3F／RF D1／D2及原配置／加櫃選圖。</p>'
        else:
            body += '<p>同版品名平面：'+"／".join('<a href="'+assets[r["asset"]]["attachment"]+'">'+html.escape(r["case"])+"</a>" for r in items)+"。</p>"
    body += ('<p>回饋仍填<a href="life-walkthrough.csv">原生活走查表</a>的'+html.escape(guide["feedback_scenario_id"])+
        '列，在「使用者回饋」寫案例ID與用途，例如C-3F供誰取物；不必另填十份表。圖號版次、同時使用衝突與待改事項沿原欄位，暫無答案留白。</p></section>')
    body += ("<h2>原28題生活情境</h2><p>先在圖上核正常一天、訪客、夜間與雨天，再按真實商品及適當專業協助確認。尚未做實物演練；不要求危險抬抱、倒地或載人試搬。</p>"
        "<p>原22題均保留，B搬轎與背牆的舊路線文字按最新研究補上下文；原檔不修改。另加6題熱水、新風、香火、停電、上下樓與家務串聯，共28題。每題已有現有資料的紙上發現及來源；沒有重新計算幾何、實物演練或專業核可。</p>"
        '<p><a href="life-walkthrough.csv">填使用回饋、衝突與待改事項</a>。這份回饋不會自動修改圖面或核可。</p><div class="table">')
    return frame("ABC生活情境走查", body+table(["情境ID", "怎麼使用", "要核對什麼", "紙上檢視發現", "仍需依據"], scenario_rows)+"</div>", report)


def systems_page(report):
    body = "<p>先把方案、要問的資料與最後核對工序備好；實際日期、型號、容量、金額及選擇留白。這些議題原已有登錄，本包將它們接到工序與回覆方式。</p>"
    roughin = report["laundry_roughin"]
    body += '<section id="laundry-roughin"><h2>洗衣預埋前：三處用途與八項接口</h2><p>'+html.escape(roughin["recommendation"])+"</p>"
    body += '<p>先核主位置與合法到達，再核同型號與完成牆柱；850×750備位不是實際產品安裝核可，A後門到乾衣備位20mm模型餘量仍需重核。此圖不按比例，沒有施工點位或管線路徑。</p>'
    body += figures(report, ["LAU-roughin"])
    body += table(["位置／用途", "先保留"], [[r["label"], r["preserve"]] for r in roughin["locations"]])
    body += table(["預埋接口", "最晚核對工序", "現在先保留", "實際資料後核對", "沿原問題／A接口"],
        [[r["label"], r["before"], r["prepare"], r["required"], "／".join(r["question_ids"]+r["a_interface_ids"])] for r in roughin["interfaces"]])
    body += table(["乾衣方向，未選", "預留條件", "尚須依據"],
        [[r["label"], r["keep"], r["condition"]] for r in roughin["config"]["dryer_alternatives"]])
    body += '<p>電壓／容量、迴路、線徑、管徑、坡度、接管與插座高度、外口及風量均待產品與現場設計，不先開孔或封板。熱泵／冷凝式仍核散熱與環境；排氣式不接一般ERV、浴廁或油煙共管。未規劃燃氣，也未選型或核准施工。</p>'
    body += '<p>原<a href="builder-replies.csv">建商回覆表</a>按BC問題列回覆，A設計師沿<a href="a-interface-matrix.csv">A介面表</a>核分工，檢查沿<a href="inspection-log.csv">工序檢查表</a>與估價／變更表；責任、費用工期與保固仍待議定，沒有新增必填表。資料到齊後先在新比較版合圖，再由相應設計者核對並另發施工文件。</p>'
    body += '<p><a href="life-walkthrough.html#laundry-use">回看日常／雨天輪用</a>。20欄實際條件全空，沒有代填已通過或自動採用。</p></section>'
    for r in report["plan"]["systems"]:
        body += '<section id="'+r["id"]+'"><h2>'+html.escape(r["id"]+"｜"+r["topic"])+"</h2>"
        for label, key in [("現在先準備", "prepare"), ("資料進來後", "data_later"), ("應先核對節點", "hold_before")]:
            body += "<p><strong>"+label+"：</strong>"+html.escape(r[key])+"</p>"
        body += "<details><summary>沿用原登錄，不改狀態</summary>"+ul([v+"｜"+report["system_register_references"][v]["title"]+
            "｜"+report["system_register_references"][v]["status"] for v in r["register_ids"]])+"</details></section>"
    return frame("長期使用與設備規劃", body+'<p><a href="systems-replies.csv">七組系統回覆表</a></p>', report)


def source_page(report):
    guide=report["plan"]["drawing_return_review"]
    rows = [[a["id"], a["caption"], a["source"], a["package_source_state"]] for a in report["attachments"]]
    body = ("<p>附件來自既有向量圖，副本去除離包導航／事件，設計幾何及原文字保留；編號家具與冷氣另在原畫布下方加可見名稱圖例，不用滑鼠提示。新增逐層儲藏圖亦有完整中文清單，尚未併主3D。來源路徑供追溯，副本不需原專案。</p>"
        "<p>歷史來源漂移只是揭露，沒有替舊包重建、改預期hash或沿用舊passed。特別是C側牆盆歷史局部圖，不能當已通過當前來源的設計。</p>"
        '<div class="table">'+table(["附件ID", "使用範圍", "原專案路徑", "原包來源狀態"], rows)+"</div>"
        '<details><summary>本次全部引用來源與SHA-256</summary><div class="table">'+
        table(["原專案路徑", "SHA-256"], list(report["source_hashes"].items()))+"</div></details>"
        '<p><a href="review.json">完整依據JSON</a>／<a href="artifact-manifest.json">閱讀檔案完整性清單</a></p>')
    body+='<section id="drawing-return"><h2>建商／建築師回圖怎麼核對</h2><p>'+html.escape(guide["purpose"])+"</p>"
    body+='<p><a href="drawing-register.csv">原圖面目錄，增收件與雜湊欄</a>／<a href="change-log.csv">原變更表，增原新版對照與估價依據欄</a>。實際提供方、日期、檔案、狀態與變更均空白，沒有收到或匯入新圖。</p>'
    body+='<h3>格式與比對邊界</h3>'+ul(guide["format_rules"])
    body+='<div class="table">'+table(["步驟","棟別／主題","怎麼核對","須同步重核／保留","沿用問題與工序"],
        [[r["id"],"／".join(r["buildings"])+"｜"+r["topic"],r["check"],r["recheck"],"／".join(r["question_ids"])+"；"+"／".join(r["sequence_ids"])] for r in guide["steps"]])+"</div>"
    body+='<h3>既有正式流程</h3><p>已有drawings preflight、不可變revision及compare；這輪只補收件與人工影響核對，沒有建立R001或再開一套匯入器。實際收到完整資料後先按本次目的試匯入及核範圍，再決定何時建立正式版次。原R000與概念SVG不能當新圖已通過的比較基準。</p>'
    body+='<p>有兩個正式且來源可核的版次後，可用drawings compare列模型欄位的新增／移除／修改；實體ID或mapping不同要人工對帳，不靠名稱猜。差異不是自動合規、價格或採用判定，未列到的濕區家規／照護／聲學／權利仍需相應核對。</p>'
    body+='<p>正式操作說明於原專案'+html.escape("／".join(guide["formal_workflow_refs"][:2]))+'；回覆仍沿<a href="abc-coordination.html#after-meeting">會後紀錄</a>與<a href="decision-sequence.html#reply-workflow">原五步流程</a>，不改正式需求、家規或主3D。</p></section>'
    return frame("附件、版本與來源", body, report)


def quick_read_section(report):
    """Reuse agenda/brief/comparison text instead of maintaining another summary input."""
    p = report["plan"]
    slots = {r["buildings"][0]: r for r in report["coordination_agenda"]["slots"] if len(r["buildings"]) == 1}
    brief = {r["id"]: r for r in p["a_brief"]}
    comparisons = {r["id"]: r for r in p["bc_comparisons"]}
    assets = {r["id"]: r for r in report["attachments"]}
    selections = {
        "A": [("A1", "一樓討論底圖"), ("ST-A-2F", "二樓新雜物櫃／品名圖"), ("ST-A-3F", "三樓新雜物櫃／品名圖")],
        "B": [("B-entry", "入口修正研究"), ("B-rear-1", "後門版一樓背景"), ("B-front-1", "前門版一樓背景"), ("ST-B-2F", "二樓新雜物櫃／品名圖"), ("ST-B-3F", "三樓新雜物櫃／品名圖")],
        "C": [("C-coord-whole", "完整一樓比較"), ("C-coord-bath", "套衛局部比較"), ("ST-C-2F", "二樓家務儲藏／品名圖"), ("ST-C-3F", "三樓換季備品櫃／品名圖")],
    }
    titles = {"A": "裝潢另談，先保生活與預埋交接", "B": "祭祀、兩入口與上層缺口分清", "C": "先看完整客餐、公衛與照護"}
    notes = {"A": "先核生活與收納，門組、MDF與套衛等候選仍按原任務狀態。",
        "B": "入口修正與整層背景分開；最新上層研究仍看完整版本表，未整套併主3D。",
        "C": "完整1F及套衛屬獨立比較，二樓為整棟底圖；照護續版尚未併主3D。"}
    body = '<section id="quick-review"><h2>三棟快速看圖：先看是否接近你要的生活</h2>'
    body += '<p>先看下面各棟的圖、保留目標與未解問題，再用<a href="life-walkthrough.html">原生活情境</a>記不順的地方。現在不用填工程數據、選機型或一次讀完全部附件。</p>'
    body += '<p><a href="life-walkthrough.html#ground-laundry">最新：三棟一樓共用洗衣與A上層備位平面</a>，優先研究A1原陽台轉向、不減廚房；C2先暫不用保空間。加深灣會少廚房2.232㎡，未替屋主接受；跨棟到達、門組與產品仍待核。</p>'
    body += '<p><a href="life-walkthrough.html#laundry-access">續看洗衣到達：斜門反例與條件式後口三態</a>；後門僅全開的基地內試線局部不碰，權利、高差與門外轉向未核，前側協助取送保留。</p>'
    body += '<p><a href="life-walkthrough.html#laundry-use">共用一組是否夠用：日常／床單／雨天流程與示例輪用</a>，先保乾衣備位、床品分日與分戶預約，真實衣量和產品未到，不承諾小晾架足夠。</p>'
    body += '<p><a href="systems.html#laundry-roughin">洗衣預埋前溝通單</a>：八項接口沿原建商問題與A設計師表回覆，三處機位用途分開；未定電壓、管徑、高度、外口或施工。</p>'
    body += '<p><a href="life-walkthrough.html#storage-review">下一步：逐層收納看圖清單</a>，沿十個同源案例核位置、尺寸、取物入口與代價；C三樓主臥取物、A三樓展床及屋頂櫃用途優先看，回饋沿原表。</p>'
    body += '<p>「保留目標」沿原聯席議程；已確認方向、原需求、研究建議與待取捨的標示仍按原任務／比較頁。它們不會把正式需求自動改為已確認，也不表示各局部圖已合成可施工主案。圖內尺寸是研究尺寸，仍待實際基地、完成面及商品資料核對。</p>'
    body += '<p><a href="upper-floor-storage-3d.zip">另下載同源儲藏立體檢視ZIP，解壓後開index.html</a>。櫃體按指定高度呈現，周邊只保原平面投影，不補造牆高／樓梯；原主3D未改。儲藏顯示驗收另按該ZIP的來源留證，不代表本靜態閱讀包或整棟設計已驗收。</p>'
    body += '<p><a href="ac-storage-preview.zip">A／C完整場景加櫃比較ZIP，解壓後開index.html</a>。可切原配置／加櫃、整層／特寫；只新增六件收納，原家具及房界保留。此ZIP另有188項顯示檢查、24案例及36張截圖目視紀錄，來源與檔案逐項相符。手機整層標籤較密，周邊文字局部裁切；細節用特寫及平面核對。C3取物需進主臥；B不同版整層未混入，設計尚未採用。</p>'
    for building in "ABC":
        slot = slots[building]
        body += '<section id="quick-'+building+'"><h3>'+building+'棟｜'+titles[building]+"</h3>"
        body += "<p><strong>保留目標與分工：</strong>"+html.escape(slot["retain"])+"</p>"
        if building == "A":
            row = brief["A-BR-05"]
            body += "<p><strong>"+html.escape(BASIS_LABELS[row["basis"]]+"｜"+row["topic"])+"：</strong>"+html.escape(row["instruction"])+"</p>"
        elif building == "B":
            qa = report["b_upper_storage_3d_archive"]["display_review"]
            body += ('<p><a href="b-upper-storage-3d.zip">B同版上層／收納3D比較ZIP</a>，解壓後開index.html。沿來源多邊形、L形到達及梯井，尺寸相符的概念家具沿用高度，其餘只畫投影；房界線框不代表牆高。此ZIP已有'+str(qa["checks"])+"項顯示檢查、"+str(qa["cases"])+"案例及"+str(qa["screenshots_reviewed"])+"張截圖目視紀錄，綁定相同來源與檔案。位置與用途仍待生活確認，一樓兩入口另看原同版平面。</p>")
            body += '<p><a href="b-upper-storage-sync.zip">另下載B上層同版底圖ZIP</a>：P4二樓、Q3三樓、RF D1／D2各比原配置／收納；附L形到達與梯井接口。這是靜態底圖與未來3D輸入，未產新3D，原RF24㎡缺口保留。</p>'
            body += "<p><strong>兩入口前提：</strong>"+html.escape(comparisons["BC-CMP-02"]["current"])+"後巷權利、開口與完整搬運仍須核對。</p>"
            review = report["b_review"]
            if review["known_capacity_conflict"]:
                body += '<p class="note"><strong>已知屋頂RF缺口：</strong>原目標'+str(review["original_RF_target_sqm"])+"㎡，現固定前帶尚不扣設備的樂觀上界"+str(review["fixed_front_optimistic_upper_bound_sqm"])+"㎡，仍差"+str(review["known_RF_shortfall_sqm"])+"㎡。局部排水改善或工程回覆可以，均不解除這個缺口；本次未接受縮平台或放寬家規。</p>"
        else:
            body += "<p><strong>新完整1F比較仍有的代價：</strong>"+html.escape(comparisons["BC-CMP-03"]["alternative"])+"</p>"
        body += "<p><strong>本次優先請交回：</strong>"+html.escape(slot["request"])+"</p>"
        body += '<p><strong>先開這幾張圖：</strong>'+"／".join('<a href="'+assets[key]["attachment"]+'">'+html.escape(label)+"</a>" for key,label in selections[building])+"。"+html.escape(notes[building])+"</p>"
        body += '<p><a href="abc-coordination.html#'+slot["id"]+'">對應原聯席議題與提問</a>／'+(
            '<a href="a-designer-brief.html">A任務書及方向狀態</a>' if building == "A" else '<a href="bc-comparison.html">B／C完整比較與代價</a>')+"。</p></section>"
    body += '<p>看完沿<a href="life-walkthrough.csv">原生活走查回饋表</a>記「討論圖號版次、使用者回饋、同時使用衝突、待改事項」。回饋與工程待件分開，尚未有答案的工程條件不由看圖推定通過；本包沒有新增屋主選擇或改圖。</p></section>'
    return body


def render(root, report):
    files = worksheets(report)
    rows = [[r["id"], r["use"], r["limits"]] for r in report["plan"]["floor_versions"]]
    anchors = "<ul>"+"".join('<li><a href="floors.html#'+r["id"]+'">'+r["id"]+"</a></li>" for r in report["plan"]["floor_versions"])+"</ul>"
    body = ('<p><a href="#quick-review">屋主先看ABC圖與未解問題</a>／<a href="#reading-order">依討論進度找文件</a>／<a href="#all-floors">全部樓層版本</a>／<a href="#all-forms">全部原表格</a>。</p>'
        +quick_read_section(report)+
        '<section id="reading-order"><h2>接著按討論進度使用</h2><ol>'
        '<li>第一次與建商談：<a href="first-meeting.html">原五題議程</a>。先收範圍、可建量、版本與估價方式；實際回覆留白。</li>'
        '<li>A裝潢另談：<a href="a-first-meeting.html">首次會議六題</a>及<a href="a-designer-brief.html">任務書</a>，預埋前再一起核介面。</li>'
        '<li>ABC格局與預埋一起核：<a href="abc-coordination.html">原聯席議程</a>及<a href="decision-sequence.html">12項工程節點</a>，同版待件與回覆窗口依序記。</li>'
        '<li>B深化：<a href="decision-sequence.html#b-review-route">RF已知缺口與退回路線</a>、<a href="b-drainage-intake.html">前排水八題與28欄</a>，原目標及兩入口保留。</li>'
        '<li>收到圖與報價：<a href="source-index.html#drawing-return">回圖核對</a>、<a href="decision-sequence.html#quote-review">同範圍核價</a>，沿原圖面／估價／變更表記錄。</li>'
        '<li>發包排程與交接：<a href="decision-sequence.html#inspection-handoff">隱蔽工程、調試與A交接</a>，先約定分批檢查及留證；具體值與結果待實際資料。</li>'
        '</ol></section>'
        '<section id="all-floors"><h2>全部樓層版本</h2><details><summary>展開12層的底圖與尚未整合範圍</summary>'+anchors+'<div class="table">'+table(["樓層", "這次拿來做什麼", "尚未整合／待核"], rows)+"</div></details></section>"
        f"<h2>怎樣交給對方</h2><p>整個資料夾或ZIP一起提供，收件者解壓後開index.html，內含{len(report['attachments'])}張靜態圖與所有回覆表，不需WSL、Node、原專案或網路3D服務。沒有代為寄出。</p>"
        "<p>可編輯工作副本請另存新的目錄；公開生成目錄會再產生空白模板。每次填答注明當次圖號、版次、依據與期限，屋主選擇、專業審查及施工圖發行分開。</p>"
        '<section id="all-forms"><h2>全部原表格</h2><details><summary>依本次議題取用表格，不用一次填完</summary><ul>'+"".join('<li><a href="'+n+'">'+n+"</a></li>" for n in files)+"</ul></details></section>")
    files.update({"index.html": frame("ABC設計討論基準與交付包", body, report), "floors.html": floor_page(report),
        "a-designer-brief.html": a_brief_page(report), "bc-comparison.html": comparison_page(report),
        "life-walkthrough.html": life_page(report), "systems.html": systems_page(report),
        "decision-sequence.html": sequence_page(report), "a-first-meeting.html": a_meeting_page(report),
        "b-drainage-intake.html": drainage_page(report),
        "abc-coordination.html": coordination_page(report),
        "abc-followup-records.json": json.dumps(report["coordination_followup"]["record_template"],ensure_ascii=False,indent=2)+"\n",
        "b-drainage-conditions.json": json.dumps(report["b_drainage_intake"]["condition_template"], ensure_ascii=False, indent=2)+"\n",
        "first-meeting.html": frame("第一次與建商討論", first_meeting(report["builder_meeting_plan"]).removeprefix("<h1>第一次與建商討論</h1>"), report),
        "source-index.html": source_page(report), "review.json": json.dumps(report, ensure_ascii=False, indent=2)+"\n",
        "README.md": "# ABC靜態討論包\n\n先開[index.html](index.html)的[三棟快速看圖](index.html#quick-review)及[討論進度導覽](index.html#reading-order)。A設計師讀[首次會議](a-first-meeting.html)及[任務書](a-designer-brief.html)，建商先讀[第一次會議](first-meeting.html)。[全部樓層](index.html#all-floors)與[原表格](index.html#all-forms)按本次議題展開，不用一次讀填全部附件。\n\n整個目錄一起複製，或使用旁附ZIP解壓；所有閱讀頁與圖均在包內，不需WSL或網路。\n\n"
            "未整套採用。B後門／前門與C整棟／照護續版仍分開，附件來源差異見[來源頁](source-index.html)。RF不是已核第四住宅層。\n\n"
            "另附[儲藏立體檢視ZIP](upper-floor-storage-3d.zip)，另解壓後開index.html。只有新櫃有指定高度，周邊為原平面投影；未併主3D。顯示驗收另按該ZIP來源留證，不代表本靜態閱讀包或整棟設計已驗收。\n\n"
            "另附[A／C完整場景加櫃比較ZIP](ac-storage-preview.zip)，可切原配置／加櫃與整層／特寫。六件收納以外的家具、房界與樓梯保留；C3取物需進主臥，B未混入。此ZIP另有來源相符的188項顯示檢查／24案例及36張截圖目視紀錄，仍有手機整層較密、周邊文字局部裁切等限制，設計尚未採用。詳見review.json內ac_storage_3d_archive.display_review；不是本靜態閱讀包或整棟設計核可。\n\n"
            "另附[B上層同版底圖ZIP](b-upper-storage-sync.zip)：P4二樓／Q3三樓／兩個RF，原配置與加櫃共八張平面，另附樓梯到達／梯井接口；一樓後門預設與前門備案各保原來源。這是靜態底圖與後續3D輸入，不沿用A／C的passed，原RF24㎡、排水及專業缺口保留。\n\n"
            "另附[B同版上層／收納3D比較ZIP](b-upper-storage-3d.zip)，解壓開index.html。顯示第2版已核同源127項檢查／16案例及32張桌機手機截圖，二樓梯名分清一樓原梯與Q3上層改梯；詳見review.json內b_upper_storage_3d_archive.display_review。保多邊形、L形到達、上下層梯與開口；來源概念高度與只畫平面者分開，房界線框不是牆高，整層閱讀仍需特寫／平面。ZIP內待驗說明是產製當時狀態，後收驗收另綁同版，不改已驗檔案。原一樓兩入口各三態連同版平面，不擴張為已核搬運；RF24㎡及工程待件保留，未採用或核准施工。\n\n"
            "CSV先另存工作副本再填。這是溝通、原圖及空白表快照；不會自動回寫需求或3D，工程／家規／照護等仍須相應核對。\n\n"
            "本包不含私人回覆、預算、聯絡方式或完整專案，原文來源以相對路徑與hash追溯。來源hash不是專業核可。\n"})
    payload = {n: value.encode("utf-8") for n, value in files.items()}
    for a in report["attachments"]:
        raw = public_path(Path(root), a["source"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != a["source_sha256"]:
            raise ContractError("Drawing changed during export")
        content, _, _ = readable_copy(raw)
        if hashlib.sha256(content).hexdigest() != a["attachment_sha256"]:
            raise ContractError("Static drawing copy differs from its declared transform")
        payload[a["attachment"]] = content
    for key in ["storage_3d_archive", "ac_storage_3d_archive", "b_upper_storage_archive", "b_upper_storage_3d_archive"]:
        bundle=report[key]
        archive_bytes=public_path(Path(root),bundle["source"]).read_bytes()
        if hashlib.sha256(archive_bytes).hexdigest()!=bundle["sha256"]:
            raise ContractError("Storage 3D ZIP changed during handoff export: "+key)
        payload[bundle["filename"]]=archive_bytes
    manifest = {"schema": "house-design-discussion-artifacts-v1", "report_hash": report["report_hash"],
        "source_hashes": report["source_hashes"], "adopted": False,
        "artifacts": {n: hashlib.sha256(data).hexdigest() for n, data in payload.items()}}
    payload["artifact-manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2)+"\n").encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 9, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    payload[ARCHIVE] = stream.getvalue()
    payload["archive-manifest.json"] = (json.dumps({"schema": "house-design-discussion-archive-v1", "report_hash": report["report_hash"],
        "archive": ARCHIVE, "sha256": hashlib.sha256(payload[ARCHIVE]).hexdigest(),
        "archive_contains": sorted(n for n in payload if n != ARCHIVE),
        "note": "ZIP內含閱讀檔及artifact-manifest；本封裝清單及ZIP自身不放入ZIP。"}, ensure_ascii=False, indent=2)+"\n").encode()
    return payload


def write_files(target, files, *, exclusive=False):
    target.mkdir(parents=True, exist_ok=not exclusive)
    for name, data in files.items():
        path = target/name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb" if exclusive else "wb") as output:
            output.write(data)


def new_share_path(root, relative):
    root, path = Path(root).resolve(), PurePosixPath(relative)
    if (not relative or "\\" in relative or path.parts[:2] != ("inputs", "private") or len(path.parts) < 3
            or any(p in {".", ".."} or p.startswith(".") for p in path.parts)):
        raise ContractError("Share copies require a new project-relative inputs/private subdirectory")
    target = root.joinpath(*path.parts)
    if not target.resolve().is_relative_to(root/"inputs/private"):
        raise ContractError("Share copy leaves inputs/private")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--create-share", metavar="inputs/private/NEW-DIRECTORY")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files = render(ROOT, report)
        target = new_share_path(ROOT, args.create_share) if args.create_share else ROOT/OUT
        if args.check:
            stale = [n for n, data in files.items() if not (target/n).is_file() or (target/n).read_bytes() != data]
            if stale:
                raise ContractError("Discussion package stale: "+", ".join(stale))
        else:
            write_files(target, files, exclusive=bool(args.create_share))
        print(json.dumps({"status": "checked" if args.check else "share-copy-created" if args.create_share else "exported",
            **report["summary"], "artifacts": len(files), "zip_bytes": len(files[ARCHIVE]),
            "protected_controls": report["protected_controls_unchanged"], "adopted": False,
            "browser": "not-run", "path": str(target)}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Export second-response G4D bounds and independent envelope budgets; static only."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.b_front_drop_claude_round2 import OUT, build  # noqa: E402
from scripts.export_abc_next_improvements import csv_text, table  # noqa: E402
from scripts.export_b_upper_replan import Sheet as BaseSheet  # noqa: E402
from scripts.export_builder_communication import page, ul  # noqa: E402


class Sheet(BaseSheet):
    def __init__(self, title, report):
        self.root = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": "0 0 1400 1200", "width": "1400", "height": "1200", "role": "img", "aria-label": title})
        self.add("title", text=title)
        self.add("style", text="text{font:17px system-ui,sans-serif;fill:#263e49}.title{font-size:26px;font-weight:700}.small{font-size:13px}")
        self.add("rect", x=0, y=0, width=1400, height=1200, fill="#fafbf8")
        self.text(title, 28, 40, class_="title")
        self.text("Claude第二輪已交叉核對｜部分算式與研究排序一致，未有完整解法、採用或專業核可。", 28, 76)
        self.text("本批 "+report["report_hash"], 28, 1158, class_="small")
        self.text("全部尺寸為列明假設；實際資料留白。原ABC／3D、家規與149控制不動，未跑瀏覽器。", 28, 1182, class_="small")


def bounds_sheet(r):
    s = Sheet("G4D落差d｜上方要容納，下方也要保留空間", r)
    s.text("d下限＝3704.9＋上方50＋接頭上凸e＋額外餘量M－假梯底；不能直接指定500或600。", 40, 140)
    s.text("表列僅M＝0的邊界，不是施工餘量；真正M、下方要求C及下凸量仍未知。", 40, 180)
    for x, label in [(40, "法向板厚t"), (280, "上凸e"), (490, "M0落差下限mm"), (850, "實際落差上限／可行區間")]:
        s.text(label, x, 240)
    for i, row in enumerate(r["drop_bounds"]):
        yy = 280+i*32
        for x, text in [(40, row["normal_waist_mm"]), (280, row["upper_fitting_growth_mm"]),
            (490, f"{row['minimum_drop_with_M0_only_mm']:.3f}"), (850, "未知／未驗證")]:
            s.text(str(text), x, yy)
    y = 730
    for value in ["t300＋上凸50需至少583.379mm，才只是消除算式負餘量。不能因此逕改600；加大落差也會減少平台上方空間。",
        "最低末端中心預算＝3461.6－d。d500／550／600分別2961.6／2911.6／2861.6，不是整室或整盒最低淨高。",
        "若沿同坡示意管再延至後緣200，分別再少4mm；實際接頭、下凸、清掃及完成面未知，真正下限不能由此確定。",
        "C必須與預算用相同高程及扣帳口徑；實際可接受的d上限與M未到，數字表不能判定有可施工區間。"]:
        y = s.paragraph(value, 40, y, width=78, step=25)
    return s.output()


def envelope_sheet(r):
    s = Sheet("G4D外擴與上游｜上凸、平面外擴及檢修分開核", r)
    s.text("以下高程欄另以t250、上凸25、M0比較；上凸25並不等於前後側各外擴25。", 40, 140)
    labels = [(40,"案例"),(370,"前／後／側增量"),(640,"後移"),(770,"平台間隔"),(980,"d下限mm"),(1200,"d500餘量")]
    for x, label in labels:
        s.text(label, x, 205, class_="small")
    for i, row in enumerate(r["body_growth_cases"]):
        yy = 250+i*44
        values = [(40,row["id"]),(370,f"{row['front_mm']}／{row['rear_mm']}／{row['side_mm']}"),
            (640,row["shift_back_mm"]),(770,row["front_to_platform_rear_mm"]),
            (980,f"{row['t250_upper25_M0_minimum_drop_mm']:.3f}"),(1200,f"{row['t250_upper25_d500_margin_model_mm']:.3f}")]
        for x, text in values:
            s.text(str(text),x,yy,class_="small")
    y = 565
    for value in ["平台間隔負數就是侵入，0只是接觸邊界。前擴25需至少後移5才不侵入，但原包絡每後移1，高程餘量約少0.5973；前／後緣新增量仍要另算。",
        "側向外擴也會讓部分外框超出原右回程踏步投影；本表只延伸同一樂觀模型，並未取得整個擴大外框的真實構造證據。",
        "上游不能借局部50：盆線到原井心的假管頂3788.4，距假板底3800僅11.6；若全線同樣要求50，這裡缺38.4。實際排口與構造未知，不等於全域無解。",
        "橫移y4500與y4700的水平總長都4375，末端盆頂都3200.9（d500）；只能改轉折位置，不能直接當門扇、接頭或清掃改善。",
        "梯下接入後只研究向下落管。G4不能再默認向上直穿梯段，通氣須另外回保留井至RF；四條比較中心線也不代表四根實管可重疊。"]:
        y = s.paragraph(value, 40, y, width=78, step=25)
    return s.output()


def review_sheet(r):
    s = Sheet("第二輪收斂｜保留G4D家族，不放寬家規或定落差", r)
    y = 140
    for row in r["claim_review"]:
        y = s.paragraph(row["id"]+" "+row["topic"]+"："+row["assessment"]+"。"+row["limit"],40,y,width=78,step=24)
    s.text("先確認合法終端與上游，再局部G4D、前濕區重排，最後全梯鏡像；不因未知就要求屋主犧牲家規。",40,1035,class_="small")
    s.text("尚未完成：全程管件／合流通氣／清掃、真實梯底、騎樓與終端；RF24、Q3聲學及R1防水仍另核。",40,1080,class_="small")
    return s.output()


def render(r):
    files = {"bounded-drop.svg": bounds_sheet(r), "envelope-and-upstream.svg": envelope_sheet(r), "round2-findings.svg": review_sheet(r)}
    for name, key in [("drop-bounds.csv","drop_bounds"),("drop-examples.csv","drop_examples"),("body-growth.csv","body_growth_cases"),
        ("cross-positions.csv","cross_position_examples"),("claim-review.csv","claim_review")]:
        files[name] = csv_text(r[key])
    files["upstream-gap.csv"] = csv_text([r["upstream_basin_original_shaft_centre"]])
    files["engineering-replies.csv"] = csv_text([{"ID":f"CG2-{i:02d}","待核":value,
        **dict.fromkeys(["實際值及單位","同版圖號及依據","專業回覆","費用工期保固","屋主選擇","審查與施工圖發行"],"")} for i,value in enumerate(r["config"]["engineering_questions"],1)])
    body = '<h1>B落管第二輪交叉核對：G4D的落差範圍與完整包絡</h1><p class="note">第二輪回應已核來源。只有部分算式與研究排序一致，沒有完整設計共識、採用或專業核可；不固定500或改定600。</p>'
    body += '<p>先確認合法終端與上游，再深化G4D局部家族；前濕區重排居次、全梯鏡像最後。尚無需屋主放寬家規或取消前後搬轎任一版。</p>'
    for name,label in [("bounded-drop.svg","落差的上下限，不只往下壓管"),("envelope-and-upstream.svg","獨立外擴與上游間隔"),("round2-findings.svg","同意、修正與待核範圍")]:
        body += f'<section><h2>{html.escape(label)}</h2><p><a href="{name}">開啟向量圖</a></p><img src="{name}" style="width:100%;height:auto" alt="{html.escape(label)}"></section>'
    body += '<h2>假落差例，沒有選用</h2>'+table(["d mm","末端中心預算mm","若直管到後緣mm","真正整盒最低淨高"],[[x["illustrative_drop_mm"],x["lowest_endpoint_centre_budget_mm"],x["if_straight_pipe_to_rear_edge_budget_mm"],"未知"] for x in r["drop_examples"]])
    body += '<h2>交叉核對</h2>'+table(["ID","議題","核對","限制"],[[x["id"],x["topic"],x["assessment"],x["limit"]] for x in r["claim_review"]])
    body += '<h2>等資料後一起核</h2>'+ul(r["config"]["engineering_questions"])
    body += '<p>'+"／".join(f'<a href="{n}">{n}</a>' for n in files if n.endswith(".csv"))+'</p><p><a href="review.json">同版來源與算式</a>／<a href="artifact-manifest.json">產物清單</a></p>'
    body += '<small>本批 '+r["report_hash"]+'；本次未發出新AI請求、未跑瀏覽器／WebGL。原ABC、家規與149控制保留。</small>'
    files["index.html"] = page("B落管第二輪與G4D範圍",body)
    files["review.json"] = json.dumps(r,ensure_ascii=False,indent=2)+"\n"
    files["artifact-manifest.json"] = json.dumps({"schema":"house-b-front-drop-claude-round2-artifacts-v1","report_hash":r["report_hash"],
        "source_hashes":r["source_hashes"],"adopted":False,"artifacts":{n:hashlib.sha256(v.encode()).hexdigest() for n,v in files.items()}},ensure_ascii=False,indent=2)+"\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        report = build(ROOT)
        files, out = render(report), ROOT/OUT
        if args.check:
            if any(not (out/n).is_file() or (out/n).read_bytes() != v.encode() for n,v in files.items()):
                raise ValueError("Round2 drop limits stale")
        else:
            out.mkdir(parents=True,exist_ok=True)
            for n,v in files.items():
                (out/n).write_text(v,encoding="utf-8",newline="")
        print(json.dumps({"status":"checked" if args.check else "exported","files":len(files),"drop_bounds":len(report["drop_bounds"]),
            "growth_cases":len(report["body_growth_cases"]),"protected_controls":report["protected_controls_unchanged"],
            "selected_drop":None,"full_design_consensus":False,"adopted":False,"browser":"not-run"}))
        return 0
    except (OSError,ValueError,KeyError) as exc:
        print(str(exc),file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

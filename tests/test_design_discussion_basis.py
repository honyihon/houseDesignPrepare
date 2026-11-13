"""Bounded static-package tests; no scene builders, browsers or product decisions."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

import pytest

from house_design.contracts import ContractError, stable_hash
from house_design.design_discussion_basis import (
    AC_STORAGE_QA,
    B_STORAGE_QA,
    INDEX,
    OUT,
    PLAN,
    SCENARIOS,
    ac_storage_rendered_qa,
    b_drainage_basis,
    b_drainage_routes_basis,
    b_review_basis,
    b_storage_rendered_qa,
    build,
    laundry_access_basis,
    laundry_preplanning_basis,
    laundry_roughin_basis,
    laundry_use_basis,
    meeting_followup_basis,
    readable_copy,
    static_svg,
    storage_owner_review,
    validate,
    validate_coordination_agenda,
    validate_workflow,
)
from house_design.project_next_steps import CONTROLS, REGISTER, REQUIREMENTS, keyed
from scripts.export_design_discussion_basis import ARCHIVE, new_share_path, render, worksheets, write_files

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


@pytest.fixture(scope="module")
def files(report):
    return render(ROOT, report)


def test_six_requested_preparations_retain_original_controls_and_formal_statuses(report):
    assert report["summary"] == {"floors": 12, "drawings": 88, "a_topics": 11, "bc_comparisons": 7,
        "walkthroughs": 28, "systems": 7, "decision_items": 12, "a_meeting_questions": 6, "reply_review_steps": 5,
        "formal_requirement_statuses": {"candidate": 66},
        "formal_register_statuses": {"unknown": 105}}
    assert report["protected_controls_unchanged"] == 149
    assert report["layout_or_primary_3d_changed"] is report["new_geometry_generated"] is False
    assert not report["formal_requirements_or_register_written"] and not report["adopted"]
    assert report["professional_approval"] == "unknown" and report["browser_qa"] == "not-run"


def test_builder_is_read_only_and_deterministic(report):
    names = [REQUIREMENTS, REGISTER, CONTROLS, SCENARIOS, "inputs/brief/A.json", "structured/candidates/kaohsiung-house-options-3d.html"]
    before = {n: (ROOT/n).read_bytes() for n in names}
    assert build(ROOT)["report_hash"] == report["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in names}


def test_a_b_c_map_does_not_promote_partial_versions(report):
    rows = report["plan"]["floor_versions"]
    assert {(r["building"], r["floor"]) for r in rows} == {(b, f) for b in "ABC" for f in ["floor-1", "floor-2", "floor-3", "floor-rf"]}
    assert all(r["integration"] == "local-research-not-merged-in-main-3d" for r in rows if r["building"] == "B")
    c1 = next(r for r in rows if r["id"] == "C-1F")
    assert c1["integration"] == "whole-floor-independent-coordination-not-merged-in-3d" and "C-care" in c1["supplement_assets"]
    old = next(a for a in report["attachments"] if a["id"] == "C-care")
    assert old["package_source_state"] == "source-changed-rebuild-required" and not old["adopted"]


def test_a_brief_keeps_sources_and_late_decisions_distinct(report):
    brief = {r["id"]: r for r in report["plan"]["a_brief"]}
    assert brief["A-BR-01"]["basis"] == "owner-confirmed-direction"
    assert brief["A-BR-05"]["basis"] == "pending-owner-choice"
    assert "12.1265" in brief["A-BR-05"]["instruction"] and "未接受" in brief["A-BR-05"]["instruction"]
    assert "不作" in brief["A-BR-11"]["instruction"] and "inputs/brief/A.json" in brief["A-BR-11"]["source_refs"]
    assert all(r["status"] == "candidate" for r in report["a_original_requirement_references"])
    assert "540cm" in brief["A-BR-04"]["instruction"] and "240" in brief["A-BR-04"]["instruction"]


def test_b_p3_overlay_is_bound_to_sources_and_not_mixed_into_old_full_floors(report):
    assets = {r["id"]: r for r in report["attachments"]}
    expected = {"B-service-2F", "B-service-doors", "B-service-drainage"}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    rows = {r["id"]: r for r in report["plan"]["floor_versions"]}
    assert expected <= set(rows["B-2F"]["supplement_assets"])
    assert "B-service-2F" not in rows["B-3F"]["supplement_assets"]
    assert "3F不放濕茶水台" in rows["B-3F"]["use"]
    comparison = report["plan"]["bc_comparisons"][0]
    assert expected <= set(comparison["assets"])
    assert "支管＋偏移" in comparison["alternative"] and "3500" in comparison["alternative"]
    assert "Docs/b-front-service-detail-v1.md" in comparison["source_refs"]
    assert "主3D" in comparison["decision_trigger"]


def test_c_whole_floor_static_comparison_is_independent_and_does_not_reuse_old_qa(report):
    expected = {"C-coord-whole", "C-coord-entry", "C-coord-bath"}
    assets = {r["id"]: r for r in report["attachments"]}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    row = next(r for r in report["plan"]["floor_versions"] if r["id"] == "C-1F")
    assert expected <= set(row["supplement_assets"])
    assert "C-care" in row["supplement_assets"] and "主3D不改" in row["use"]
    comparison = next(r for r in report["plan"]["bc_comparisons"] if r["id"] == "BC-CMP-03")
    assert expected <= set(comparison["assets"])
    assert "Docs/c-ground-coordination-v1.md" in comparison["source_refs"]
    assert "18.5" in comparison["alternative"] and "250" in comparison["alternative"]


def test_b3_program_acoustic_and_roof_tradeoffs_remain_visible_in_handoff(report):
    expected = {"B3-rear-control", "B3-front-study", "B3-acoustic-space", "B3-roof-interface"}
    assets = {r["id"]: r for r in report["attachments"]}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    rows = {r["id"]: r for r in report["plan"]["floor_versions"]}
    assert expected <= set(rows["B-3F"]["supplement_assets"])
    assert "B3-roof-interface" in rows["B-RF"]["supplement_assets"]
    comparison = next(r for r in report["plan"]["bc_comparisons"] if r["id"] == "BC-CMP-05")
    assert expected <= set(comparison["assets"])
    assert "Docs/b-third-entertainment-v1.md" in comparison["source_refs"]
    assert "19.2079" in comparison["alternative"] and "5.112" in comparison["alternative"]
    assert "20" in comparison["recommendation"] and "31.0171" in comparison["current"]
    sequence = next(r for r in report["plan"]["decision_sequence"] if r["id"] == "SEQ-04")
    assert "BC-CMP-05" in sequence["comparison_ids"]


def test_court_interface_tradeoffs_and_old_guard_issue_are_visible_in_handoff(report):
    expected = {"B-court-options", "B-court-roof", "B-court-section"}
    assets = {r["id"]: r for r in report["attachments"]}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    rows = {r["id"]: r for r in report["plan"]["floor_versions"]}
    assert all(expected <= set(rows[key]["supplement_assets"]) for key in ["B-3F", "B-RF"])
    comparison = next(r for r in report["plan"]["bc_comparisons"] if r["id"] == "BC-CMP-05")
    assert expected <= set(comparison["assets"])
    assert "2.639" in comparison["alternative"] and "5.112" in comparison["alternative"]
    assert "0.25" in comparison["recommendation"] and "計0戶外" in comparison["recommendation"]
    assert "Docs/b-working-court-v1.md" in comparison["source_refs"]


def test_roof_equipment_and_new_fresh_air_conflicts_are_not_hidden_in_handoff(report):
    expected = {"B-roof-S1", "B-roof-S2", "B-fresh-dry-candidate"}
    assets = {r["id"]: r for r in report["attachments"]}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    rows = {r["id"]: r for r in report["plan"]["floor_versions"]}
    assert expected <= set(rows["B-RF"]["supplement_assets"])
    assert all("B-fresh-dry-candidate" in rows[key]["supplement_assets"] for key in ["B-2F", "B-3F"])
    assert "21.83945" in rows["B-RF"]["limits"] and "24" in rows["B-RF"]["limits"]
    comparison = next(r for r in report["plan"]["bc_comparisons"] if r["id"] == "BC-CMP-05")
    assert expected <= set(comparison["assets"]) and "Docs/b-roof-equipment-v1.md" in comparison["source_refs"]


def test_daily_roof_capacity_and_left_hinge_repair_stay_visible_without_reducing_goals(report):
    expected = {"B-daily-D1", "B-daily-D2", "B-daily-capacity"}
    assets = {r["id"]: r for r in report["attachments"]}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    row = next(r for r in report["plan"]["floor_versions"] if r["id"] == "B-RF")
    assert expected <= set(row["supplement_assets"])
    comparison = next(r for r in report["plan"]["bc_comparisons"] if r["id"] == "BC-CMP-06")
    assert expected <= set(comparison["assets"])
    assert "21.83945" in comparison["current"] and "左鉸鏈" in comparison["alternative"]
    assert "24" in comparison["recommendation"] and "屋主明示" in comparison["decision_trigger"]
    sequence = next(r for r in report["plan"]["decision_sequence"] if r["id"] == "SEQ-04")
    assert "BC-CMP-06" in sequence["comparison_ids"]


def test_Q3_area_stair_exchange_is_not_presented_as_thin_acoustic_or_inherited_roof_approval(report):
    expected = {"B-Q3-plan", "B-Q3-stair", "B-Q3-sensitivity"}
    assets = {r["id"]: r for r in report["attachments"]}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    rows = {r["id"]: r for r in report["plan"]["floor_versions"]}
    assert expected <= set(rows["B-3F"]["supplement_assets"])
    assert all("B-Q3-stair" in rows[k]["supplement_assets"] for k in ["B-2F", "B-RF"])
    assert "不可繼承" in rows["B-RF"]["limits"]
    comparison = next(r for r in report["plan"]["bc_comparisons"] if r["id"] == "BC-CMP-07")
    assert expected <= set(comparison["assets"])
    assert "18.6129" in comparison["current"] and "20.1889" in comparison["alternative"]
    assert "19.2399" in comparison["recommendation"] and "RF" in comparison["decision_trigger"]
    assert "Docs/b-ktv-stair-options-v1.md" in comparison["source_refs"]
    assert "BC-CMP-07" in next(r for r in report["plan"]["decision_sequence"] if r["id"] == "SEQ-04")["comparison_ids"]


def test_Q3_roof_same_revision_conditions_and_repaired_heat_pump_access_are_visible(report):
    expected = {"B-Q3-RF-D1", "B-Q3-RF-D2", "B-Q3-RF-floor"}
    assets = {r["id"]: r for r in report["attachments"]}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    row = next(r for r in report["plan"]["floor_versions"] if r["id"] == "B-RF")
    assert expected <= set(row["supplement_assets"])
    assert "18門態" in row["limits"] and "前900／側770" in row["limits"]
    comparison = next(r for r in report["plan"]["bc_comparisons"] if r["id"] == "BC-CMP-07")
    assert expected <= set(comparison["assets"])
    assert "前熱泵巡檢改前門避晾衣架" in comparison["decision_trigger"]
    assert "Docs/b-q3-roof-coordination-v1.md" in comparison["source_refs"]


def test_Q3_engineering_interfaces_keep_height_replacement_and_capacity_limits_visible(report):
    expected = {"B-Q3-engineering-vertical", "B-Q3-engineering-replacement", "B-Q3-engineering-capacity"}
    assets = {r["id"]: r for r in report["attachments"]}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    rows = {r["id"]: r for r in report["plan"]["floor_versions"]}
    assert expected <= set(rows["B-RF"]["supplement_assets"])
    assert "B-Q3-engineering-vertical" in rows["B-3F"]["supplement_assets"]
    assert "整機汰換" in rows["B-RF"]["limits"] and "375" in rows["B-RF"]["limits"]
    comparison = next(r for r in report["plan"]["bc_comparisons"] if r["id"] == "BC-CMP-07")
    assert expected <= set(comparison["assets"])
    assert "寬度相容不是搬運通過" in comparison["decision_trigger"]
    assert "Docs/b-q3-engineering-gates-v1.md" in comparison["source_refs"]


def test_P4_changes_only_2F_front_references_and_does_not_promote_a_44mm_example(report):
    expected = {"B-P4-plan", "B-P4-doors", "B-P4-drainage"}
    assets = {r["id"]: r for r in report["attachments"]}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    rows = {r["id"]: r for r in report["plan"]["floor_versions"]}
    assert expected <= set(rows["B-2F"]["supplement_assets"])
    assert not (expected & set(rows["B-3F"]["supplement_assets"]))
    comparison = next(r for r in report["plan"]["bc_comparisons"] if r["id"] == "BC-CMP-01")
    assert expected <= set(comparison["assets"])
    assert "4.4mm" in comparison["recommendation"] and "淋浴多710" in comparison["alternative"]
    assert "額外25即失守" in comparison["alternative"]
    assert "Docs/b-front-drainage-layout-v1.md" in comparison["source_refs"]
    assert report["b_review"]["known_capacity_conflict"] and not report["b_review"]["whole_design_adoption_allowed_here"]


def test_ground_drop_conflict_is_visible_on_both_floors_and_not_a_global_no_solution_claim(report):
    expected = {"B-drop-platform", "B-drop-section", "B-drop-consequences"}
    assets = {a["id"]: a for a in report["attachments"]}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    rows = {r["id"]: r for r in report["plan"]["floor_versions"]}
    assert all(expected <= set(rows[f]["supplement_assets"]) for f in ["B-1F", "B-2F"])
    assert "平台0.16" in rows["B-1F"]["limits"] and "非全域無解" in rows["B-1F"]["limits"]
    comparison = next(r for r in report["plan"]["bc_comparisons"] if r["id"] == "BC-CMP-01")
    assert expected <= set(comparison["assets"])
    assert "G0已知占平台" in comparison["decision_trigger"] and "四點反例不證全域無解" in comparison["decision_trigger"]
    assert "Docs/b-front-drop-stair-v1.md" in comparison["source_refs"]
    assert any("G0落水已占入口平台" in r for r in report["plan"]["b_review_route"]["meeting_order"])


def test_Claude_crosscheck_reaches_handoff_without_adopting_G4D_or_inventing_KTV_sewage(report, files):
    expected = {"B-drop-claude-route", "B-drop-claude-section", "B-drop-claude-claims"}
    assets = {a["id"]: a for a in report["attachments"]}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    rows = {r["id"]: r for r in report["plan"]["floor_versions"]}
    assert all(expected <= set(rows[f]["supplement_assets"]) for f in ["B-1F", "B-2F"])
    comparison = next(r for r in report["plan"]["bc_comparisons"] if r["id"] == "BC-CMP-01")
    assert expected <= set(comparison["assets"])
    assert "原高程各列不容" in comparison["alternative"] and "部分板厚／接頭假設容納" in comparison["alternative"]
    assert "沒有全共識或採用" in comparison["recommendation"]
    assert "Q3前KTV已乾" in comparison["decision_trigger"] and "第二輪已核" in comparison["decision_trigger"]
    assert "20mm" in rows["B-1F"]["limits"] and "騎樓段未改善" in rows["B-2F"]["limits"]
    assert "Docs/b-front-drop-claude-crosscheck-v1.md" in comparison["source_refs"]
    for page in ["floors.html", "bc-comparison.html", "decision-sequence.html"]:
        assert "G4D" in files[page].decode("utf-8")
    assert "inputs/references/b-front-drop-claude-round1-20261110.md" in report["source_hashes"]
    assert "Docs/claude-b-front-drop-followup-v2.md" in report["source_hashes"]


def test_second_Claude_response_updates_handoff_with_bounds_and_partial_agreement_only(report, files):
    expected = {"B-drop-r2-bounds", "B-drop-r2-envelope", "B-drop-r2-findings"}
    assets = {a["id"]:a for a in report["attachments"]}
    assert expected <= assets.keys()
    assert all(assets[k]["package_source_state"] == "local-study-file-hash-only" and not assets[k]["adopted"] for k in expected)
    floors = {r["id"]:r for r in report["plan"]["floor_versions"]}
    assert all(expected <= set(floors[k]["supplement_assets"]) for k in ["B-1F", "B-2F"])
    comp = next(c for c in report["plan"]["bc_comparisons"] if c["id"] == "BC-CMP-01")
    assert expected <= set(comp["assets"]) and "583.379" in comp["recommendation"]
    assert "不直接選500或600" in comp["alternative"] and "部分算式與研究排序" in comp["decision_trigger"]
    assert "11.6" in comp["decision_trigger"] and "不得再向上穿梯" in comp["decision_trigger"]
    assert "Docs/b-front-drop-claude-crosscheck-v2.md" in comp["source_refs"]
    assert "inputs/references/b-front-drop-claude-round2-20261110.md" in report["source_hashes"]
    assert "structured/coordination/b-front-drop-claude-v2/review.json" in report["source_hashes"]
    for page in ["floors.html", "bc-comparison.html", "decision-sequence.html"]:
        text = files[page].decode("utf-8")
        assert "第二輪已核" in text and "全共識" in text


def test_G4D_intake_is_portable_blank_and_does_not_add_design_comparisons(report,files):
    intake=report["b_drainage_intake"]
    assert intake["condition_values_received"]==0 and intake["condition_document_hash"] is None
    assert len(intake["field_guide"])==28 and len(intake["engineering_gates"])==8
    doc=json.loads(files["b-drainage-conditions.json"])
    assert doc==intake["condition_template"]
    assert all(v is None for g in doc["groups"] for v in g["values"].values())
    assert files["b-drainage-conditions.json"]==(ROOT/"structured/coordination/b-front-drop-conditions-v1/actual-data-template.json").read_bytes()
    rows=list(csv.DictReader(io.StringIO(files["b-drainage-replies.csv"].decode("utf-8-sig"))))
    assert [r["問題ID"] for r in rows]==[f"BFD-{i:02d}" for i in range(1,9)]
    assert all(r["原決策節點"]=="SEQ-04" and r["原比較"]=="BC-CMP-01" for r in rows)
    for name in ["index.html","decision-sequence.html"]:
        assert 'href="b-drainage-intake.html"' in files[name].decode()
    assert "28欄" in files["b-drainage-intake.html"].decode() and "局部算式" in files["b-drainage-intake.html"].decode()
    assert report["summary"]["bc_comparisons"]==7 and report["summary"]["drawings"]==88
    assert sum(n.endswith(".html") for n in files)==12


@pytest.mark.parametrize("defect",["private-path","wrong-pin","seal","actual-document","filled-template","missing-gate","source-drift"])
def test_G4D_intake_rejects_private_filled_or_stale_handoff_basis(monkeypatch,defect):
    import house_design.design_discussion_basis as module
    p=copy.deepcopy(read(PLAN))
    basis=p["b_drainage_intake"]
    name=basis["report"]
    received=copy.deepcopy(read(name))
    if defect=="private-path":
        basis["report"]="inputs/private/conditions.json"
    elif defect=="wrong-pin":
        basis["report_sha256"]="0"*64
    elif defect=="seal":
        received["report_hash"]="0"*64
    elif defect=="actual-document":
        received["condition_document_hash"]="a"*64
    elif defect=="filled-template":
        received["condition_template"]["groups"][0]["values"]["extra_upper_fitting_mm"]=0
        received["received_conditions"]=copy.deepcopy(received["condition_template"])
    elif defect=="missing-gate":
        received["engineering_gates"].pop()
    else:
        source=next(iter(received["source_hashes"]))
        received["source_hashes"][source]="0"*64
    if defect not in {"private-path","wrong-pin","seal"}:
        received["report_hash"]=stable_hash({k:v for k,v in received.items() if k!="report_hash"})
    original_read=module.read_public_json
    monkeypatch.setattr(module,"read_public_json",lambda root,path:received if path==name else original_read(root,path))
    with pytest.raises(ContractError):
        b_drainage_basis(ROOT,p,{})


def test_G4D_response_routes_and_quote_scopes_stay_blank_portable_and_nonadopting(report,files):
    routing=report["b_drainage_reply_routes"]
    assert routing["active_action_ids"]==["BFR-07"] and routing["condition_values_received"]==0
    assert not routing["condition_report_imported"] and routing["overall_quote_total"] is None
    assert routing["automatic_next_layout_selection"] is None and not routing["construction_release"]
    assert len(routing["reply_actions"])==7 and len(routing["quote_scopes"])==6
    assert all(q["fee_amount"] is q["construction_cost"] is q["owner_choice"] is None for q in routing["quote_scopes"])
    for name,source in [("b-drainage-response-routes.csv","response-routes.csv"),("b-drainage-quote-scopes.csv","quote-scopes.csv")]:
        assert files[name]==(ROOT/"structured/planning/b-front-drop-reply-routes"/source).read_bytes()
    body=files["b-drainage-intake.html"].decode()
    assert 'id="response-routes"' in body and "共通工作只列一次" in body and "互斥研究方向" in body
    assert 'href="b-drainage-response-routes.csv"' in body and 'href="b-drainage-quote-scopes.csv"' in body
    assert report["summary"]["bc_comparisons"]==7 and report["summary"]["drawings"]==88


@pytest.mark.parametrize("defect",["private-path","wrong-pin","private-import","invented-total","missing-route","source-drift"])
def test_G4D_handoff_rejects_private_or_changed_routing_results(monkeypatch,defect):
    import house_design.design_discussion_basis as module
    plan=copy.deepcopy(read(PLAN))
    basis=plan["b_drainage_reply_routes"]
    name=basis["report"]
    received=copy.deepcopy(read(name))
    if defect=="private-path":
        basis["report"]="inputs/private/routing/review.json"
    elif defect=="wrong-pin":
        basis["report_sha256"]="0"*64
    elif defect=="private-import":
        received["condition_report_imported"]=True
    elif defect=="invented-total":
        received["overall_quote_total"]=0
    elif defect=="missing-route":
        received["reply_actions"].pop()
    else:
        received["source_hashes"][next(iter(received["source_hashes"]))]="0"*64
    received["report_hash"]=stable_hash({k:v for k,v in received.items() if k!="report_hash"})
    original=module.read_public_json
    monkeypatch.setattr(module,"read_public_json",lambda root,path:received if path==name else original(root,path))
    with pytest.raises(ContractError):
        b_drainage_routes_basis(ROOT,plan,{})


def test_ABC_coordination_meeting_is_source_bound_separate_from_A_interiors_and_not_held(report,files):
    agenda=report["coordination_agenda"]
    assert agenda==read("inputs/abc-coordination-agenda.json")
    assert agenda["duration_minutes"]==90
    assert [(s["start_minute"],s["end_minute"]) for s in agenda["slots"]]==[(0,10),(10,30),(30,50),(50,65),(65,80),(80,90)]
    assert [s["buildings"] for s in agenda["slots"]]==[["A","B","C"],["B"],["C"],["A"],["A","B","C"],["A","B","C"]]
    status=report["coordination_meeting_status"]
    assert not status["meeting_held"] and status["actual_date"] is None and status["actual_participants"]==[]
    assert status["received_replies"]==status["owner_choices_received"]==0 and not status["construction_release"]
    body=files["abc-coordination.html"].decode()
    assert "A設計師另談的六題" in body and "B前排水八題與28欄" in body
    assert "600方塊不是900照護通路" in body and "原16㎡主臥" in body
    assert 'href="abc-coordination.html"' in files["index.html"].decode()
    rows=list(csv.DictReader(io.StringIO(files["abc-coordination-actions.csv"].decode("utf-8-sig"))))
    assert [r["議程ID"] for r in rows]==[f"COORD-{i:02d}" for i in range(1,7)]
    assert all(r["本次回覆"]==r["已議定窗口"]==r["回覆期限"]=="" for r in rows)
    assert sum(n.endswith(".html") for n in files)==12


@pytest.mark.parametrize("defect",["time-gap","time-overlap","time-overrun","duplicate-slot","unknown-question","other-building-question",
    "other-building-asset","other-building-task","other-building-interface","other-building-floor","unbound-source","decision-field","boolean-time"])
def test_ABC_agenda_rejects_wrong_versions_cross_building_references_and_implied_results(defect):
    plan=read(PLAN)
    a=copy.deepcopy(read("inputs/abc-coordination-agenda.json"))
    if defect=="time-gap":
        a["slots"][1]["start_minute"]=11
    elif defect=="time-overlap":
        a["slots"][1]["start_minute"]=9
    elif defect=="time-overrun":
        a["slots"][-1]["end_minute"]=91
    elif defect=="duplicate-slot":
        a["slots"][1]["id"]=a["slots"][0]["id"]
    elif defect=="unknown-question":
        a["slots"][1]["question_ids"]=["BC-99"]
    elif defect=="other-building-question":
        a["slots"][1]["question_ids"]=["BC-10"]
    elif defect=="other-building-asset":
        a["slots"][1]["asset_ids"]=["C-coord-whole"]
    elif defect=="other-building-task":
        a["slots"][1]["task_ids"]=["A-CARE-001"]
    elif defect=="other-building-interface":
        a["slots"][1]["a_interface_ids"]=["A-IF-03"]
    elif defect=="other-building-floor":
        a["slots"][1]["floor_ids"]=["C-1F"]
    elif defect=="unbound-source":
        a["source_refs"]=["inputs/private/meeting-notes.json"]
    elif defect=="decision-field":
        a["slots"][1]["adopted"]=True
    else:
        a["slots"][0]["start_minute"]=False
    tasks=keyed(read(INDEX)["work_items"],"Tasks")
    with pytest.raises(ContractError):
        validate_coordination_agenda(a,plan,tasks,read("inputs/builder-communication-plan.json"))


def test_meeting_followup_reuses_six_rows_and_keeps_all_actual_records_private_and_blank(report,files):
    followup=report["coordination_followup"]
    assert followup["replies_reported"]==0 and not followup["actual_record_imported"]
    assert followup["received_records"]==followup["record_template"]
    assert not followup["meeting_reported"] and followup["automatically_closed_records"]==0
    template=json.loads(files["abc-followup-records.json"])
    assert template==followup["record_template"]
    assert files["abc-followup-records.json"]==(ROOT/"structured/planning/abc-meeting-followup/record-template.json").read_bytes()
    rows=list(csv.DictReader(io.StringIO(files["abc-coordination-actions.csv"].decode("utf-8-sig"))))
    assert len(rows)==6 and all(r["資料回覆狀態"]=="尚未收到" for r in rows)
    assert all(r[k]=="" for r in rows for k in ["回覆來源","已議定窗口","回覆期限","屋主選擇範圍","專業文件依據","圖面發行日期"])
    assert all(r["工具核准施工"].startswith("否") for r in rows)
    page=files["abc-coordination.html"].decode()
    assert 'id="after-meeting"' in page and 'href="abc-followup-records.json"' in page
    assert "不自動結案" in page and "沒有約定日期就不判逾期" in page
    assert sum(n.endswith(".csv") for n in files)==18 and sum(n.endswith(".html") for n in files)==12


@pytest.mark.parametrize("defect",["private-path","wrong-pin","private-record","invented-choice","edited-source"])
def test_followup_handoff_rejects_private_or_edited_records(monkeypatch,defect):
    import house_design.design_discussion_basis as module
    plan=copy.deepcopy(read(PLAN))
    basis=plan["meeting_followup"]
    name=basis["report"]
    received=copy.deepcopy(read(name))
    if defect=="private-path":
        basis["report"]="inputs/private/meeting/review.json"
    elif defect=="wrong-pin":
        basis["report_sha256"]="0"*64
    elif defect=="private-record":
        received["actual_record_imported"]=True
    elif defect=="invented-choice":
        received["owner_choices_documented"]=1
    else:
        received["source_hashes"][next(iter(received["source_hashes"]))]="0"*64
    received["report_hash"]=stable_hash({k:v for k,v in received.items() if k!="report_hash"})
    original=module.read_public_json
    monkeypatch.setattr(module,"read_public_json",lambda root,path:received if path==name else original(root,path))
    with pytest.raises(ContractError):
        meeting_followup_basis(ROOT,plan,{})


def test_B_known_capacity_conflict_remains_distinct_from_pending_professional_evidence(report):
    review = report["b_review"]
    assert review["original_RF_target_sqm"] == 24
    assert review["fixed_front_optimistic_upper_bound_sqm"] == 21.83945
    assert review["known_RF_shortfall_sqm"] == 2.16055 and review["known_capacity_conflict"]
    assert len(review["gates"]) == 9
    assert [r["id"] for r in review["gates"] if r["basis_status"] == "known-capacity-conflict"] == ["BQG-07"]
    assert sum(r["basis_status"] == "pending-evidence" for r in review["gates"]) == 8
    assert all(r["received_reply"] is r["owner_choice"] is None and r["professional_review"] == "unknown" for r in review["gates"])
    assert not review["whole_design_adoption_allowed_here"] and not review["construction_release_allowed_here"]
    assert not review["all_positive_reply_text_would_resolve_capacity"] and review["actual_replies_imported"] == 0


def test_B_fallbacks_are_research_routes_and_do_not_adopt_Q2_or_shrink_RF(report):
    routes = {r["id"]: r for r in report["b_review"]["fallbacks"]}
    assert len(routes) == 5
    assert all(r["owner_choice"] is None and not r["adopted"] and not r["all_original_goals_met"] for r in routes.values())
    assert "18.6129" in routes["B-ROUTE-03"]["limits"] and "未達KTV20" in routes["B-ROUTE-03"]["limits"]
    assert "目前沒有這份新格局" in routes["B-ROUTE-04"]["action"]
    assert "本次沒有接受" in routes["B-ROUTE-05"]["trigger"]
    assert "不把RF24改成10" in routes["B-ROUTE-05"]["limits"]


@pytest.mark.parametrize("change", ["cross-sequence", "cross-question", "missing-route", "approval-field", "unknown-drawing", "unbound-report", "bad-hash", "wrong-capacity-gate"])
def test_B_routes_reject_cross_building_unbound_or_promoted_plans(change):
    p = copy.deepcopy(read(PLAN))
    route = p["b_review_route"]
    if change == "cross-sequence":
        route["sequence_id"] = "SEQ-05"
    elif change == "cross-question":
        route["question_ids"] = ["BC-10"]
    elif change == "missing-route":
        route["fallbacks"].pop()
    elif change == "approval-field":
        route["fallbacks"][0]["adopted"] = True
    elif change == "unknown-drawing":
        route["fallbacks"][0]["assets"] = ["unknown"]
    elif change == "unbound-report":
        route["engineering_report"] = "inputs/private/answers.json"
    elif change == "bad-hash":
        route["engineering_report_sha256"] = "not-a-sha256"
    else:
        route["capacity_gate_id"] = "BQG-99"
    with pytest.raises(ContractError):
        validate_workflow(p, keyed(read(INDEX)["work_items"], "Tasks"), read("inputs/builder-communication-plan.json"))


@pytest.mark.parametrize("change", ["file-hash", "report-seal", "source-drift"])
def test_B_reply_basis_stops_on_changed_report_seal_or_sources(monkeypatch, change):
    import house_design.design_discussion_basis as module
    p = copy.deepcopy(read(PLAN))
    name = p["b_review_route"]["engineering_report"]
    original_digest, original_read = module.digest, module.read_public_json
    if change == "file-hash":
        p["b_review_route"]["engineering_report_sha256"] = "0"*64
    elif change == "report-seal":
        changed = copy.deepcopy(read(name))
        changed["capacity_boundary"]["original_target_sqm"] = 10
        monkeypatch.setattr(module, "read_public_json", lambda root, n: changed if n == name else original_read(root, n))
    else:
        target = "house_design/b_q3_engineering_gates.py"
        monkeypatch.setattr(module, "digest", lambda root, n, cache: "0"*64 if n == target else original_digest(root, n, cache))
    with pytest.raises(ContractError):
        b_review_basis(ROOT, p, {})


def test_positive_engineering_summary_cannot_remove_known_capacity_or_grant_adoption(monkeypatch):
    import house_design.design_discussion_basis as module
    p = copy.deepcopy(read(PLAN))
    name = p["b_review_route"]["engineering_report"]
    changed = copy.deepcopy(read(name))
    changed["all_engineering_gate_statuses"] = "hypothetical-positive-summary"
    changed["report_hash"] = stable_hash({k: v for k, v in changed.items() if k != "report_hash"})
    checksum = hashlib.sha256(json.dumps(changed, ensure_ascii=False).encode()).hexdigest()
    p["b_review_route"]["engineering_report_sha256"] = checksum
    original_digest, original_read = module.digest, module.read_public_json
    monkeypatch.setattr(module, "digest", lambda root, n, cache: checksum if n == name else original_digest(root, n, cache))
    monkeypatch.setattr(module, "read_public_json", lambda root, n: changed if n == name else original_read(root, n))
    reviewed, _ = b_review_basis(ROOT, p, {})
    assert reviewed["known_capacity_conflict"] and reviewed["known_RF_shortfall_sqm"] == 2.16055
    assert not reviewed["whole_design_adoption_allowed_here"] and not reviewed["construction_release_allowed_here"]
    assert next(r for r in reviewed["gates"] if r["id"] == "BQG-07")["basis_status"] == "known-capacity-conflict"


def test_all_existing_scenarios_retained_with_context_corrected_only_in_derived_view(report):
    original = keyed(read(SCENARIOS)["scenarios"], "Scenarios")
    derived = {r["id"]: r for r in report["walkthroughs"]}
    assert set(original) <= set(derived) and len(derived) == len(original)+6
    for key, r in original.items():
        assert derived[key]["original_expectation"] == r["expectation"]
        assert derived[key]["original_status"] == r["status"]
    assert "後門直接入庫" in derived["B-CARRY-BODY"]["expectation"]
    assert "庫房上方可臥室" in derived["B-BACKING"]["expectation"]
    assert all(r["result"] is None and not r["approved"] for r in derived.values())
    for r in derived.values():
        assert r["paper_observation"]["state"] and r["paper_observation"]["finding"]
        assert all(s in report["source_hashes"] for s in r["paper_observation"]["source_refs"])
    assert "跨層搬運" in derived["ABC-DAILY-CHAIN"]["paper_observation"]["finding"]


def test_owner_storage_walkthrough_uses_frozen_dimensions_and_does_not_choose_or_add_forms(report, files):
    source = read("inputs/upper-floor-storage.json")
    guide = report["storage_owner_review"]
    assert [r["case"] for r in guide["items"]] == [r["id"] for r in source["cases"]]
    for row, case in zip(guide["items"], source["cases"], strict=True):
        assert all(row[k] == case[k] for k in ["label", "rect_mm", "height_mm", "operation_mm"])
        assert row["owner_choice"] is None and not row["adopted"] and row["professional_approval"] == "unknown"
        assert row["viewer_archive"] == ("b-upper-storage-3d.zip" if case["building"] == "B" else "ac-storage-preview.zip")
    c3 = next(r for r in guide["items"] if r["case"] == "C-3F")
    assert "主臥" in c3["access"] and "隱私" in c3["access"]
    html = files["life-walkthrough.html"].decode()
    assert 'id="storage-review"' in html
    assert all(r["id"] in html for r in report["walkthroughs"])
    assert "plans.html" in html and "原28題生活情境" in html
    assert 'life-walkthrough.html#storage-review' in files["index.html"].decode()
    assert "新畫面待驗" not in files["index.html"].decode()
    rows = list(csv.DictReader(io.StringIO(files["life-walkthrough.csv"].decode("utf-8-sig"))))
    assert len(rows) == 28 and all(r["使用者回饋"] == r["待改事項"] == "" for r in rows)
    assert sum(n.endswith(".csv") for n in files) == 18


def test_latest_laundry_direction_is_bound_without_rewriting_older_washer_or_storage_snapshots(report, files):
    study = report["laundry_preplanning"]
    assert study == read(report["plan"]["laundry_preplanning"])
    assert study["shared_active_group_direction"] == 1 and not study["host_building_adopted"]
    assert study["C2_space_retained"]["new_direction_use"] == "temporarily-inactive-reserve-space"
    assert study["A2_reservation"]["floor"] == "floor-2"
    assert not study["original_ABC_or_3d_changed"] and not study["accepted_storage_viewers_changed"]
    assert all(name in report["source_hashes"] for name in study["source_hashes"])
    ids = {a["id"] for a in report["attachments"]}
    assert {"LAU-A1-compact", "LAU-A1-deeper", "LAU-A2-reserve"} <= ids
    for name in ["index.html", "life-walkthrough.html", "floors.html", "a-designer-brief.html"]:
        page = files[name].decode()
        assert "C2F先暫不用" in page and "A2F以上另預留機位" in page
        assert 'life-walkthrough.html#ground-laundry' in page
    walkthrough = files["life-walkthrough.html"].decode()
    assert 'id="ground-laundry"' in walkthrough and "2.232" in walkthrough
    assert "1040" in walkthrough and "洗衣機按最新方向暫不用" in walkthrough
    assert all("drawings/"+i+".svg" in walkthrough for i in ["LAU-A1-compact", "LAU-A1-deeper", "LAU-A2-reserve"])
    rows = list(csv.DictReader(io.StringIO(files["life-walkthrough.csv"].decode("utf-8-sig"))))
    daily = next(r for r in rows if r["情境ID"] == "ABC-DAILY-CHAIN")
    assert "一組" in daily["現有資料發現"] and "670" in daily["現有資料發現"]
    assert daily["使用者回饋"] == daily["待改事項"] == ""


@pytest.mark.parametrize("defect", ["owner-group", "host-adopted", "stale-source"])
def test_laundry_direction_or_source_cannot_be_silently_promoted_or_changed(monkeypatch, defect):
    plan = read(PLAN)
    study = read(plan["laundry_preplanning"])
    if defect == "owner-group":
        study["owner_direction"]["confirmed"]["shared_group_at_ground_floor"] = 3
    elif defect == "host-adopted":
        study["host_building_adopted"] = True
    else:
        study["source_hashes"]["inputs/abc-ground-laundry.json"] = "0"*64
    study["report_hash"] = stable_hash({k: v for k, v in study.items() if k != "report_hash"})
    monkeypatch.setattr("house_design.design_discussion_basis.read_public_json", lambda *_: study)
    with pytest.raises(ContractError, match="[Ll]aundry preplanning"):
        laundry_preplanning_basis(ROOT, plan, {})


def test_laundry_access_drawings_share_existing_workflow_and_keep_the_exterior_unknown(report, files):
    study = report["laundry_access"]
    assert study == read(report["plan"]["laundry_access"])
    assert study["parent_report_hash"] == report["laundry_preplanning"]["report_hash"]
    assert study["parent_sources_verified"] == 15 and not study["host_building_adopted"]
    assert not study["rear_entry_screen"]["whole_route_or_care_approved"]
    assert all(name in report["source_hashes"] for name in study["source_hashes"])
    ids = {"LAU-front-screen", "LAU-rear-entry", "LAU-rear-states"}
    a1 = next(r for r in report["plan"]["floor_versions"] if r["id"] == "A-1F")
    assert ids <= set(a1["supplement_assets"])
    life = files["life-walkthrough.html"].decode()
    assert 'id="laundry-access"' in life and "0.63" in life and "20mm" in life
    assert all("drawings/"+key+".svg" in life for key in ids)
    assert "不表示所有前側重排無解" in life
    assert 'life-walkthrough.html#laundry-access' in files["index.html"].decode()
    rows = list(csv.DictReader(io.StringIO(files["life-walkthrough.csv"].decode("utf-8-sig"))))
    daily = next(r for r in rows if r["情境ID"] == "ABC-DAILY-CHAIN")
    assert "半開" in daily["現有資料發現"] and "權利" in daily["現有資料發現"]
    assert daily["使用者回饋"] == daily["待改事項"] == ""
    assert len(rows) == 28 and sum(n.endswith(".csv") for n in files) == 18


@pytest.mark.parametrize("defect", ["exterior-approval", "global-impossibility", "wrong-parent", "false-geometry", "source"])
def test_laundry_access_scope_or_geometry_cannot_be_silently_promoted(monkeypatch, defect):
    plan = read(PLAN)
    study = read(plan["laundry_access"])
    if defect == "exterior-approval":
        study["rear_entry_screen"]["whole_route_or_care_approved"] = True
    elif defect == "global-impossibility":
        study["front_entry_screen"]["global_front_replanning_impossible"] = True
    elif defect == "wrong-parent":
        study["parent_report"] = "other.json"
    elif defect == "false-geometry":
        study["rear_entry_screen"]["states"][1]["scoped_route_blocked"] = False
    else:
        study["source_hashes"]["inputs/abc-laundry-access.json"] = "0"*64
    study["report_hash"] = stable_hash({k: v for k, v in study.items() if k != "report_hash"})
    monkeypatch.setattr("house_design.design_discussion_basis.read_public_json", lambda *_: study)
    with pytest.raises(ContractError, match="Laundry access"):
        laundry_access_basis(ROOT, plan, {})


def test_laundry_use_stays_hypothetical_and_reuses_existing_feedback(report, files):
    use = report["laundry_use"]
    assert use == read(report["plan"]["laundry_use"])
    assert use["parent_report_hash"] == report["laundry_access"]["report_hash"]
    assert use["actual_laundry_capacity_sufficient"] is None and not use["equipment_purchase_decided"]
    assert all(name in report["source_hashes"] for name in use["source_hashes"])
    life = files["life-walkthrough.html"].decode()
    assert 'id="laundry-use"' in life and "9小時15分" in life and "只洗完，晾乾未知" in life
    assert "假設壓力示例" in life and "一般全熱當除濕" in life
    assert all("drawings/"+key+".svg" in life for key in ["LAU-use-flow", "LAU-use-time"])
    assert 'life-walkthrough.html#laundry-use' in files["index.html"].decode()
    rows = list(csv.DictReader(io.StringIO(files["life-walkthrough.csv"].decode("utf-8-sig"))))
    daily = next(r for r in rows if r["情境ID"] == "ABC-DAILY-CHAIN")
    assert "示例3批" in daily["現有資料發現"] and "容量仍未知" in daily["現有資料發現"]
    assert daily["使用者回饋"] == daily["待改事項"] == ""
    assert len(rows) == 28 and sum(n.endswith(".csv") for n in files) == 18


@pytest.mark.parametrize("defect", ["actual-capacity", "purchase", "timing", "source"])
def test_laundry_use_cannot_turn_examples_into_actual_performance(monkeypatch, defect):
    plan = read(PLAN)
    use = read(plan["laundry_use"])
    if defect == "actual-capacity":
        use["actual_laundry_capacity_sufficient"] = True
    elif defect == "purchase":
        use["equipment_purchase_decided"] = True
    elif defect == "timing":
        use["scenarios"][0]["modes"][1]["elapsed_min"] = 1
    else:
        use["source_hashes"]["inputs/abc-laundry-use.json"] = "0"*64
    use["report_hash"] = stable_hash({k: v for k, v in use.items() if k != "report_hash"})
    monkeypatch.setattr("house_design.design_discussion_basis.read_public_json", lambda *_: use)
    with pytest.raises(ContractError, match="Laundry use"):
        laundry_use_basis(ROOT, plan, {})


def test_laundry_roughin_keeps_original_reply_workflow_and_source_bound_unknowns(report, files):
    study = report["laundry_roughin"]
    assert study == read(report["plan"]["laundry_roughin"])
    assert study["parent_report_hash"] == report["laundry_use"]["report_hash"]
    assert study["construction_release"] is False and study["dryer_type_selected"] is None
    assert all(name in report["source_hashes"] for name in study["source_hashes"])
    html = files["systems.html"].decode()
    assert 'id="laundry-roughin"' in html and "drawings/LAU-roughin.svg" in html
    assert all(r["label"] in html for r in study["interfaces"])
    assert "C2原機位" in html and "未啟用" in html and "熱泵／冷凝式" in html
    assert all('href="'+n+'"' in html and n in files for n in ["builder-replies.csv", "a-interface-matrix.csv", "inspection-log.csv"])
    assert 'systems.html#laundry-roughin' in files["life-walkthrough.html"].decode()
    assert 'systems.html#laundry-roughin' in files["index.html"].decode()
    assert sum(n.endswith(".csv") for n in files) == 18 and len(report["walkthroughs"]) == 28


@pytest.mark.parametrize("defect", ["construction", "ratings", "dryer", "invented-reply", "source"])
def test_laundry_roughin_cannot_promote_design_specs_or_builder_responses(monkeypatch, defect):
    plan = read(PLAN)
    study = read(plan["laundry_roughin"])
    if defect == "construction":
        study["construction_release"] = True
    elif defect == "ratings":
        study["electrical_ratings_decided"] = True
    elif defect == "dryer":
        study["dryer_type_selected"] = "heatpump-condensing"
    elif defect == "invented-reply":
        study["interfaces"][0]["agreed_window"] = "builder"
    else:
        study["source_hashes"]["inputs/abc-laundry-roughin.json"] = "0"*64
    study["report_hash"] = stable_hash({k: v for k, v in study.items() if k != "report_hash"})
    monkeypatch.setattr("house_design.design_discussion_basis.read_public_json", lambda *_: study)
    with pytest.raises(ContractError, match="Laundry rough-in"):
        laundry_roughin_basis(ROOT, plan, {})


@pytest.mark.parametrize("change", ["missing", "duplicate", "foreign-case", "choice", "dimensions", "feedback"])
def test_storage_review_cannot_lose_a_roof_case_or_invent_choices_dimensions_or_forms(change):
    plan = copy.deepcopy(read(PLAN))
    guide = plan["storage_owner_review"]
    if change == "missing":
        guide["items"].pop(6)
    elif change == "duplicate":
        guide["items"][6]["case"] = "B-RF-D1"
    elif change == "foreign-case":
        guide["items"][0]["case"] = "A-1F"
    elif change == "choice":
        guide["items"][0]["owner_choice"] = "accepted"
    elif change == "dimensions":
        guide["items"][0]["height_mm"] = 900
    else:
        guide["feedback_scenario_id"] = "NEW-STORAGE-FORM"
    with pytest.raises(ContractError, match="Storage owner review"):
        storage_owner_review(plan, read("inputs/upper-floor-storage.json"))


@pytest.mark.parametrize("change", ["missing-floor", "duplicate-floor", "rf-residential", "unknown-asset", "unknown-task", "promote-b", "unknown-register", "unknown-basis", "unknown-scenario", "missing-paper-observation", "unbound-paper-source"])
def test_bad_floor_and_existing_id_mappings_are_rejected(change):
    p = copy.deepcopy(read(PLAN))
    tasks = keyed(read(INDEX)["work_items"], "Tasks")
    register = keyed(read(REGISTER)["items"], "Register")
    scenarios = keyed(read(SCENARIOS)["scenarios"], "Scenarios")
    if change == "missing-floor":
        p["floor_versions"].pop()
    elif change == "duplicate-floor":
        p["floor_versions"][-1]["floor"] = "floor-3"
    elif change == "rf-residential":
        p["floor_versions"][-1]["floor"] = "floor-4"
    elif change == "unknown-asset":
        p["floor_versions"][0]["base_assets"] = ["unknown"]
    elif change == "unknown-task":
        p["floor_versions"][0]["task_ids"] = ["unknown"]
    elif change == "promote-b":
        p["floor_versions"][4]["integration"] = "merged-and-approved"
    elif change == "unknown-register":
        p["systems"][0]["register_ids"] = ["unknown"]
    elif change == "unknown-basis":
        p["a_brief"][0]["basis"] = "construction-approved"
    elif change == "missing-paper-observation":
        p["paper_observations"].pop("A-ENTRY")
    elif change == "unbound-paper-source":
        p["paper_observations"]["A-ENTRY"]["source_refs"] = ["inputs/private/unbound.json"]
    else:
        p["scenario_overrides"]["missing"] = "new route"
    with pytest.raises(ContractError):
        validate(p, tasks, register, scenarios)


def test_static_copies_keep_real_geometry_and_labels_while_removing_old_navigation(report):
    ns = "{http://www.w3.org/2000/svg}"
    for asset in report["attachments"]:
        raw = (ROOT/asset["source"]).read_bytes()
        transformed, removed, entries = readable_copy(raw)
        before, after = ET.fromstring(raw), ET.fromstring(transformed)
        legend = after.find(ns+"g[@data-visible-equipment-legend='1']")
        if entries:
            assert legend is not None and all(value in "".join(legend.itertext()) for value in entries)
            after.remove(legend)
            assert after.get("data-original-viewbox") == before.get("viewBox")
        else:
            assert before.attrib["viewBox"] == after.attrib["viewBox"]
        for tag in ["rect", "path", "line", "circle", "polyline", "text", "tspan"]:
            assert [(e.attrib, e.text) for e in before.iter(ns+tag)] == [(e.attrib, e.text) for e in after.iter(ns+tag)]
        assert hashlib.sha256(transformed).hexdigest() == asset["attachment_sha256"]
        assert removed == asset["navigation_attributes_removed"]
        assert all(not k.lower().startswith("on") and (k.rsplit("}", 1)[-1] not in {"href", "src"} or v.startswith("#"))
            for n in after.iter() for k, v in n.attrib.items())


@pytest.mark.parametrize("body", ['<script>alert(1)</script>', '<image href="https://example.com/a.png"/>',
    '<style>@import "https://example.com/font";</style>', '<rect style="fill:url(https://example.com/x)"/>', '<foreignObject/>'])
def test_svg_external_resources_are_rejected(body):
    with pytest.raises(ContractError):
        static_svg(('<svg xmlns="http://www.w3.org/2000/svg">'+body+"</svg>").encode())


def test_local_svg_gradients_work_and_events_are_removed():
    value, count = static_svg(b'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(#g)" onclick="alert(1)" width="12"/></svg>')
    assert b"onclick" not in value and b"url(#g)" in value and b'width="12"' in value and count == 1


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if data.get("id"):
            self.ids.add(data["id"])
        self.refs.extend(data[k] for k in ["href", "src"] if data.get(k))
        assert tag not in {"script", "iframe", "object"}


def test_zip_is_a_complete_offline_handoff_after_unpacking_elsewhere(tmp_path, files):
    root = tmp_path/"unpacked"
    with zipfile.ZipFile(io.BytesIO(files[ARCHIVE])) as archive:
        assert all(not n.startswith("/") and ".." not in Path(n).parts for n in archive.namelist())
        archive.extractall(root)
        assert len(archive.namelist()) == 127
    for path in root.glob("*.html"):
        parser = Links()
        parser.feed(path.read_text(encoding="utf-8"))
        for ref in parser.refs:
            url = urlsplit(ref)
            assert not url.scheme and not url.netloc
            target = path.parent/unquote(url.path) if url.path else path
            assert target.resolve().is_relative_to(root) and target.is_file(), (path.name, ref)
            if url.fragment:
                other = Links()
                other.feed(target.read_text(encoding="utf-8"))
                assert unquote(url.fragment) in other.ids
    assert (root/"drawings/A1.svg").is_file() and (root/"a-designer-brief.html").is_file()
    assert b"\xe6\xad\xb7\xe5\x8f\xb2\xe4\xbe\x86\xe6\xba\x90\xe5\xb7\xb2\xe6\xbc\x82\xe7\xa7\xbb" in files["floors.html"]


def test_existing_and_new_reply_forms_leave_choices_money_and_approvals_blank(report):
    forms = worksheets(report)
    assert len(forms) == 18
    for name, columns in {
        "drawing-register.csv": ["檔案格式", "原始檔SHA256", "所據會議或問題ID", "座標與標高基準", "完整樓層範圍", "缺件或混版說明", "本次接收狀態（僅收件）", "需同步重核的圖面"],
        "change-log.csv": ["原檔SHA256", "新檔SHA256", "變更範圍與對照依據", "需重核的原需求ID", "同版模型或差異報告", "影響A設計師／建商介面", "對應估價或客變單", "未解條件及受影響工項"],
        "bc-comparison-replies.csv": ["新增資料", "建商設計回覆", "完整費用差額", "屋主選擇", "專業核對"],
        "life-walkthrough.csv": ["使用者回饋", "同時使用衝突", "期限", "證據及專業核對"],
        "systems-replies.csv": ["回覆", "費用影響", "屋主選擇", "專業核對"],
        "same-scope-quotes.csv": ["同範圍總額", "屋主選擇", "報價比較組ID", "報價列ID", "原契約或基準報價版次", "估價依據文件及SHA256", "費用口徑（基準總價／增減差額／替代完整價）", "互斥替代組ID", "重複工項及一次計價歸屬", "跨棟共用工程與分攤依據"],
        "inspection-log.csv": ["實施日期", "結果", "覆查日期及結果", "覆蓋前確認依據", "對應檢查提醒ID", "本批完整範圍與未檢部分", "材料產品／施工規範版次", "試驗條件及要求值來源", "實測值／單位與儀器紀錄", "隱蔽位置圖與原始檔SHA256", "變更／改善關聯ID", "A進場前後基準及責任分界"],
        "decision-sequence.csv": ["實際最晚日期", "已議定窗口", "資料回覆及依據", "屋主選擇及日期", "專業核對", "施工圖發行"],
        "a-first-meeting-replies.csv": ["設計師回覆", "所需建商資料", "回覆窗口", "回覆期限", "屋主回饋"],
        "b-review-replies.csv": ["回覆狀態", "同版圖號及證據", "建商專業回覆", "費用工期及保固影響", "已議定窗口", "回覆期限", "屋主選擇及日期", "專業核對", "施工圖發行"],
        "b-drainage-replies.csv": ["回覆狀態", "圖號版次及標高基準", "建商專業回覆", "費用工期保固", "已議定窗口", "回覆期限", "屋主選擇及日期", "專業核對", "施工圖發行"],
        "b-drainage-response-routes.csv": ["同版依據及回覆", "窗口及期限", "完整替代方案版次", "屋主選擇及日期", "專業核對", "施工圖發行"],
        "b-drainage-quote-scopes.csv": ["已議定承作範圍", "原契約已含或折抵", "研究設計費及幣別", "施工價及幣別", "費用差額", "工期影響", "屋主選擇及日期"],
        "abc-coordination-actions.csv": ["本次回覆", "圖號版次及來源", "已議定窗口", "回覆期限", "下次動作", "費用工期影響", "屋主選擇及日期", "專業核對", "施工圖發行"]}.items():
        rows = list(csv.DictReader(io.StringIO(forms[name].lstrip("\ufeff"))))
        assert all(r[k] == "" for r in rows for k in columns)


def test_share_copy_does_not_overwrite_existing_working_answers(tmp_path, files):
    target = new_share_path(tmp_path, "inputs/private/share-001")
    write_files(target, files, exclusive=True)
    p = target/"life-walkthrough.csv"
    p.write_text("owner feedback", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_files(target, files, exclusive=True)
    assert p.read_text(encoding="utf-8") == "owner feedback"


@pytest.mark.parametrize("value", ["structured/share", "inputs/private", "inputs/private/../public", "/tmp/share", "inputs\\private\\share"])
def test_share_path_cannot_escape_private_records(tmp_path, value):
    with pytest.raises(ContractError):
        new_share_path(tmp_path, value)


def test_share_rejects_private_symlink_escape(tmp_path):
    (tmp_path/"inputs/private").mkdir(parents=True)
    (tmp_path/"public").mkdir()
    (tmp_path/"inputs/private/outside").symlink_to(tmp_path/"public", target_is_directory=True)
    with pytest.raises(ContractError):
        new_share_path(tmp_path, "inputs/private/outside/share")


def test_report_artifacts_zip_and_source_bindings_are_current(report, files):
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    for name, digest in report["source_hashes"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest
    manifest = json.loads(files["artifact-manifest.json"])
    for name, digest in manifest["artifacts"].items():
        assert hashlib.sha256(files[name]).hexdigest() == digest
    archive = json.loads(files["archive-manifest.json"])
    assert hashlib.sha256(files[ARCHIVE]).hexdigest() == archive["sha256"]
    with zipfile.ZipFile(io.BytesIO(files[ARCHIVE])) as z:
        assert sorted(z.namelist()) == archive["archive_contains"]
        assert all(z.read(n) == files[n] for n in z.namelist())
    assert len(files) == 129
    assert files == render(ROOT, report)
    assert all((ROOT/OUT/name).read_bytes() == data for name, data in files.items())


def test_AC_scene_comparison_is_bundled_without_replacing_the_accepted_storage_viewer(report, files):
    bundle = report["ac_storage_3d_archive"]
    raw = files[bundle["filename"]]
    assert raw == (ROOT/bundle["source"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == bundle["sha256"]
    assert bundle["new_cabinets"] == 6 and not bundle["adopted"]
    assert bundle["rendered_qa"] == "passed-for-comparison-display-scope"
    assert bundle["display_review"]["source"] == AC_STORAGE_QA
    assert bundle["display_review"]["screenshots_reviewed"] == 36
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert "index.html" in z.namelist() and "plans.html" in z.namelist()
        assert len([n for n in z.namelist() if n.endswith(".svg")]) == 16
    accepted = report["storage_3d_archive"]
    assert files[accepted["filename"]] == (ROOT/accepted["source"]).read_bytes()


def test_b_same_revision_plans_are_bundled_separately_without_promoting_rendered_qa(report, files):
    bundle = report["b_upper_storage_archive"]
    raw = files[bundle["filename"]]
    assert raw == (ROOT/bundle["source"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == bundle["sha256"]
    assert bundle["summary"]["upper_floor_states"] == 8
    assert bundle["rendered_qa"] == "not-run-static-sync-and-future-scene-input-only"
    assert not bundle["adopted"]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert len([n for n in z.namelist() if n.endswith(".svg")]) == 9
        b_report = json.loads(z.read("review.json"))
        assert len(b_report["entry_options"]) == 2 and len(b_report["assemblies"]) == 24
        assert b_report["known_limits"]["RF_target_sqm"] == 24
        assert not b_report["main_3d_changed"]


def test_b_source_height_3d_zip_binds_completed_display_review_without_changing_accepted_zips(report, files):
    bundle = report["b_upper_storage_3d_archive"]
    assert files[bundle["filename"]] == (ROOT/bundle["source"]).read_bytes()
    assert hashlib.sha256(files[bundle["filename"]]).hexdigest() == bundle["sha256"]
    assert bundle["summary"]["states"] == 8 and not bundle["adopted"]
    assert bundle["rendered_qa"] == "passed-for-comparison-display-scope"
    assert bundle["display_review"]["source"] == B_STORAGE_QA
    assert bundle["display_review"]["checks"] == 127
    assert bundle["display_review"]["screenshots_reviewed"] == 32
    with zipfile.ZipFile(io.BytesIO(files[bundle["filename"]])) as z:
        assert all(n in z.namelist() for n in ["index.html", "viewer.js", "label-layout.js", "vendor/three.min.js", "plans.html"])
        assert len([n for n in z.namelist() if n.endswith(".svg")]) == 14
        # Keep production-time pending metadata inside the frozen ZIP for traceability.
        assert json.loads(z.read("review.json"))["rendered_qa"] == "not-run-owner-separate-terminal-required"
    assert report["ac_storage_3d_archive"]["rendered_qa"] == "passed-for-comparison-display-scope"


@pytest.mark.parametrize("defect", ["source", "artifact", "current-artifact", "report", "archive", "revision",
    "incomplete", "not-reviewed", "screenshots", "cases", "console", "not-closed", "adopted", "release"])
def test_b_display_pass_cannot_transfer_to_changed_incomplete_or_expanded_evidence(monkeypatch, defect):
    qa = read(B_STORAGE_QA)
    viewer = read("structured/coordination/b-upper-storage-3d-v1/review.json")
    files = {n: (ROOT/"structured/coordination/b-upper-storage-3d-v1"/n).read_bytes()
        for n in qa["viewer_artifacts_sha256"]}
    if defect == "source":
        qa["source_hashes"][next(iter(qa["source_hashes"]))] = "0"*64
    elif defect == "artifact":
        qa["viewer_artifacts_sha256"]["viewer.js"] = "0"*64
    elif defect == "current-artifact":
        monkeypatch.setattr("house_design.design_discussion_basis.digest", lambda root, name, cache:
            "0"*64 if name.endswith("b-upper-storage-3d-v1/viewer.js") else hashlib.sha256((root/name).read_bytes()).hexdigest())
    elif defect == "report":
        qa["report_hash"] = "0"*64
    elif defect == "archive":
        qa["raw_evidence"]["tested_viewer_zip_sha256"] = "0"*64
    elif defect == "revision":
        qa["display_revision"] = 1
    elif defect == "incomplete":
        qa["automated"]["status"] = "incomplete"
    elif defect == "not-reviewed":
        qa["visual_review"]["screenshots_reviewed"] = 0
    elif defect == "screenshots":
        qa["screenshots_sha256"].pop(next(iter(qa["screenshots_sha256"])))
    elif defect == "cases":
        qa["cases"].pop()
    elif defect == "console":
        qa["automated"]["console_errors"] = ["error"]
    elif defect == "not-closed":
        qa["automated"]["closed"] = False
    elif defect == "adopted":
        qa["constraints"]["adopted"] = True
    else:
        qa["constraints"]["construction_release"] = True
    monkeypatch.setattr("house_design.design_discussion_basis.read_public_json", lambda *_: qa)
    with pytest.raises(ContractError, match="B display review"):
        b_storage_rendered_qa(ROOT, viewer, files, {})


@pytest.mark.parametrize("defect", ["source", "artifact", "current-artifact", "report", "archive", "incomplete", "not-reviewed"])
def test_ac_display_pass_cannot_transfer_to_changed_or_incomplete_evidence(monkeypatch, defect):
    qa = read(AC_STORAGE_QA)
    preview = read("structured/coordination/ac-storage-preview-v1/review.json")
    files = {n: (ROOT/"structured/coordination/ac-storage-preview-v1"/n).read_bytes()
        for n in qa["viewer_artifacts_sha256"]}
    if defect == "source":
        qa["source_hashes"][next(iter(qa["source_hashes"]))] = "0"*64
    elif defect == "artifact":
        qa["viewer_artifacts_sha256"]["index.html"] = "0"*64
    elif defect == "current-artifact":
        monkeypatch.setattr("house_design.design_discussion_basis.digest", lambda root, name, cache:
            "0"*64 if name.endswith("ac-storage-preview-v1/index.html") else hashlib.sha256((root/name).read_bytes()).hexdigest())
    elif defect == "report":
        qa["report_hash"] = "0"*64
    elif defect == "archive":
        qa["raw_evidence"]["tested_preview_zip_sha256"] = "0"*64
    elif defect == "incomplete":
        qa["automated"]["status"] = "incomplete"
    else:
        qa["visual_review"]["screenshots_reviewed"] = 0
    monkeypatch.setattr("house_design.design_discussion_basis.read_public_json", lambda *_: qa)
    with pytest.raises(ContractError, match="display review"):
        ac_storage_rendered_qa(ROOT, preview, files, {})


def test_package_bytes_do_not_depend_on_python_hash_seed():
    code = ("import hashlib,json; from pathlib import Path; "
        "from house_design.reproducible_export import canonical_zip_metadata; "
        "context=canonical_zip_metadata(); context.__enter__(); "
        "from house_design.design_discussion_basis import build; "
        "from scripts.export_design_discussion_basis import render; r=Path.cwd(); "
        "print(json.dumps({n:hashlib.sha256(d).hexdigest() for n,d in render(r,build(r)).items()},sort_keys=True))")
    outputs = []
    for seed in ["7", "23"]:
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, check=True,
            capture_output=True, timeout=8, env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"})
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]


def test_sequencing_is_relative_and_not_a_fabricated_schedule_or_choice(report):
    sequence = {r["id"]: r for r in report["decision_execution"]}
    assert len(sequence) == 12
    for r in sequence.values():
        assert r["before_lock"] and r["defer_strategy"] and r["first_action"]
        assert r["actual_deadline"] is r["agreed_lead"] is r["owner_choice"] is None
        assert r["received_evidence"] == [] and r["professional_review"] == "unknown"
        assert not r["construction_drawing_issued"]
    assert sequence["SEQ-01"]["lock_after"] == [] and sequence["SEQ-02"]["lock_after"] == []
    assert "SEQ-08" in sequence["SEQ-07"]["coordinate_with"]
    assert "SEQ-07" in sequence["SEQ-08"]["coordinate_with"]
    assert "SEQ-08" not in sequence["SEQ-07"]["lock_after"]
    assert "SEQ-07" not in sequence["SEQ-08"]["lock_after"]
    assert "20／5／6" in sequence["SEQ-04"]["defer_strategy"]
    assert "約12.13" in sequence["SEQ-06"]["defer_strategy"]
    assert "施工前" in sequence["SEQ-08"]["before_lock"]


@pytest.mark.parametrize("change", ["unknown-sequence", "cycle", "later-prerequisite", "self-coordinate", "unknown-stage",
    "unknown-question", "unknown-interface", "unknown-brief", "unknown-record", "missing-reserve", "b-only-in-a-meeting"])
def test_unknown_or_circular_sequencing_and_cross_building_meeting_are_rejected(change):
    p = copy.deepcopy(read(PLAN))
    tasks = keyed(read(INDEX)["work_items"], "Tasks")
    builder = read("inputs/builder-communication-plan.json")
    first = p["decision_sequence"][0]
    if change == "unknown-sequence":
        first["lock_after"] = ["SEQ-99"]
    elif change == "cycle":
        first["lock_after"] = ["SEQ-02"]
        p["decision_sequence"][1]["lock_after"] = ["SEQ-01"]
    elif change == "later-prerequisite":
        first["lock_after"] = ["SEQ-12"]
    elif change == "self-coordinate":
        first["coordinate_with"] = ["SEQ-01"]
    elif change == "unknown-stage":
        first["stage"] = "S99"
    elif change == "unknown-question":
        first["question_ids"] = ["BC-99"]
    elif change == "unknown-interface":
        p["a_first_meeting"]["questions"][0]["a_interface_ids"] = ["A-IF-99"]
    elif change == "unknown-brief":
        p["a_first_meeting"]["questions"][0]["brief_ids"] = ["A-BR-99"]
    elif change == "unknown-record":
        p["reply_workflow"][0]["records"] = ["missing.csv"]
    elif change == "missing-reserve":
        first["defer_strategy"] = ""
    else:
        p["a_first_meeting"]["questions"][0]["sequence_ids"] = ["SEQ-04"]
    with pytest.raises(ContractError):
        validate_workflow(p, tasks, builder)


def test_mutual_product_mep_coordination_is_supported_without_a_finalization_cycle(report):
    p = report["plan"]
    validate_workflow(p, keyed(read(INDEX)["work_items"], "Tasks"), report["builder_meeting_plan"])
    meeting = p["a_first_meeting"]
    assert len(meeting["questions"]) == 6
    assert all(r["brief_ids"] and r["a_interface_ids"] and r["sequence_ids"] for r in meeting["questions"])
    assert "預埋" in meeting["opening_message"]
    assert [s["id"] for s in p["reply_workflow"]] == ["REPLY-01", "REPLY-02", "REPLY-03", "REPLY-04", "REPLY-05"]

"""Synthetic follow-up records must not close work, approve design or change sources."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
from pathlib import Path

import pytest

from house_design.abc_meeting_followup import OUT, build, template, validate_records
from house_design.contracts import ContractError, stable_hash
from scripts import export_abc_meeting_followup as exporter

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def baseline():
    return build(ROOT)


def synthetic(baseline):
    return copy.deepcopy(baseline["record_template"])


def reply(row):
    row.update(reply_state="received-for-review",reply_summary="Synthetic report only",reply_reference="TEST-REPLY-001",
        drawing_revision="TEST-REV-001",reply_received_date="2026-11-11")


def test_baseline_retains_six_original_slots_without_actual_meeting_or_reply(baseline):
    assert [r["slot_id"] for r in baseline["slot_evaluations"]]==[f"COORD-{i:02d}" for i in range(1,7)]
    assert baseline["replies_reported"]==baseline["owner_choices_documented"]==baseline["professional_records_documented"]==0
    assert not baseline["meeting_reported"] and not baseline["actual_record_imported"]
    assert baseline["received_records"]==baseline["record_template"]
    assert baseline["automatically_closed_records"]==0 and baseline["automatic_fee_total"] is None
    assert all(r["deadline_overdue"] is None and not r["record_closed"] for r in baseline["slot_evaluations"])


def test_laundry_revision_preserves_the_original_config_and_rejects_automatic_old_record_transfer(baseline):
    cfg=baseline["config"]
    assert cfg["revision"]==2 and cfg["supersedes_config"]["source"]=="inputs/abc-meeting-followup.json"
    old=ROOT/cfg["supersedes_config"]["source"]
    assert hashlib.sha256(old.read_bytes()).hexdigest()==cfg["supersedes_config"]["sha256"]
    agenda=json.loads((ROOT/cfg["agenda"]).read_text())
    previous=template(json.loads(old.read_text()),agenda)
    assert [r["question_ids"] for r in previous["records"]]==[r["question_ids"] for r in baseline["record_template"]["records"]]
    with pytest.raises(ContractError,match="exact coordination source revision"):
        validate_records(baseline["record_template"],previous)


def test_receiving_a_reply_does_not_create_meeting_choice_approval_or_release(baseline):
    d=synthetic(baseline)
    reply(d["records"][1])
    r=build(ROOT,d)
    assert r["replies_reported"]==1 and not r["meeting_reported"]
    assert r["owner_choices_documented"]==r["professional_records_documented"]==r["drawing_release_records_documented"]==0
    row=r["slot_evaluations"][1]
    assert "reply-reported-not-yet-verified" in row["record_flags"]
    assert not row["adopted"] and not row["construction_release"] and row["professional_approval"]=="unknown"


def test_missing_items_without_agreed_deadline_remain_pending_not_overdue_or_global_block(baseline):
    d=synthetic(baseline)
    row=d["records"][2]
    reply(row)
    row.update(reply_state="partial",missing_items=["TEST product dimensions","TEST full route"])
    r=build(ROOT,d)
    flags=r["slot_evaluations"][2]["record_flags"]
    assert {"partial-reply-needs-evidence","declared-missing-items","reply-contact-not-agreed","reply-deadline-not-agreed"}<=set(flags)
    assert r["slot_evaluations"][2]["deadline_overdue"] is None and not r["whole_project_blocked"]


def test_all_document_records_present_still_need_manual_content_and_authority_check(baseline):
    d=synthetic(baseline)
    row=d["records"][3]
    reply(row)
    row.update(cost_schedule_state="documented",cost_schedule_reference="TEST cost scope",
        owner_choice_state="documented",owner_choice_scope="TEST limited scope",owner_choice_reference="TEST owner note",owner_choice_date="2026-11-11",
        professional_record_state="documented",professional_scope="TEST specific check",professional_reference="TEST document",professional_record_date="2026-11-11",
        drawing_release_record_state="documented",drawing_release_revision="TEST-REV-002",drawing_release_issuer="TEST issuer",drawing_release_reference="TEST issue note",drawing_release_date="2026-11-11")
    r=build(ROOT,d)
    assert r["owner_choices_documented"]==r["professional_records_documented"]==r["drawing_release_records_documented"]==1
    row=r["slot_evaluations"][3]
    assert row["documented_professional_record_not_content_verified"] and row["documented_drawing_release_not_authority_verified"]
    assert row["professional_approval"]=="unknown" and not row["construction_release"] and not row["record_closed"]
    assert not r["adopted"] and not r["formal_requirements_written"] and r["automatically_closed_records"]==0


def test_reported_conflict_and_deferred_owner_choice_are_separate(baseline):
    d=synthetic(baseline)
    row=d["records"][1]
    reply(row)
    row.update(reply_state="conflict-reported",owner_choice_state="deferred",owner_choice_scope="Wait for complete alternatives")
    r=build(ROOT,d)
    assert r["conflicts_reported"]==1 and r["owner_choices_documented"]==0
    assert "declared-conflict-needs-complete-alternatives" in r["slot_evaluations"][1]["record_flags"]
    assert "owner-choice-deferred" in r["slot_evaluations"][1]["record_flags"]


@pytest.mark.parametrize("defect",["source-revision","agenda","missing-slot","duplicate-slot","wrong-building","wrong-question","approval-state","extra-approval",
    "invalid-date","hidden-reply","reply-no-reference","reply-no-date","deadline-no-contact","hidden-choice","choice-no-scope","professional-no-source",
    "hidden-release","release-no-issuer","meeting-no-reference","boolean-date","duplicate-missing"])
def test_mixed_sources_hidden_content_and_unsupported_state_promotion_rejected(baseline,defect):
    d=synthetic(baseline)
    row=d["records"][1]
    if defect=="source-revision":
        d["config_hash"]="0"*64
    elif defect=="agenda":
        d["agenda_sha256"]="0"*64
    elif defect=="missing-slot":
        d["records"].pop()
    elif defect=="duplicate-slot":
        d["records"].append(copy.deepcopy(row))
    elif defect=="wrong-building":
        row["buildings"]=["C"]
    elif defect=="wrong-question":
        row["question_ids"]=["BC-10"]
    elif defect=="approval-state":
        row["professional_record_state"]="approved"
    elif defect=="extra-approval":
        row["construction_release"]=True
    elif defect=="invalid-date":
        row["agreed_due_date"]="2026-02-30"
    elif defect=="hidden-reply":
        row["reply_summary"]="Received but hidden"
    elif defect=="reply-no-reference":
        reply(row)
        row["reply_reference"]=""
    elif defect=="reply-no-date":
        reply(row)
        row["reply_received_date"]=None
    elif defect=="deadline-no-contact":
        row["agreed_due_date"]="2026-11-30"
    elif defect=="hidden-choice":
        row["owner_choice_scope"]="Unrecorded choice"
    elif defect=="choice-no-scope":
        row.update(owner_choice_state="documented",owner_choice_reference="Test",owner_choice_date="2026-11-11")
    elif defect=="professional-no-source":
        row.update(professional_record_state="documented",professional_scope="Test",professional_record_date="2026-11-11")
    elif defect=="hidden-release":
        row["drawing_release_revision"]="TEST"
    elif defect=="release-no-issuer":
        row.update(drawing_release_record_state="documented",drawing_release_revision="Test",drawing_release_reference="Test",drawing_release_date="2026-11-11")
    elif defect=="meeting-no-reference":
        d["meeting_date"]="2026-11-11"
    elif defect=="boolean-date":
        d["meeting_date"]=False
    else:
        row["missing_items"]=["same","same"]
    with pytest.raises(ContractError):
        validate_records(baseline["record_template"],d)


def test_reordered_records_normalize_to_original_slot_order(baseline):
    d=synthetic(baseline)
    d["records"].reverse()
    assert validate_records(baseline["record_template"],d)==baseline["record_template"]


def test_public_artifacts_sources_and_empty_actual_values_match(baseline):
    files=exporter.render(baseline)
    assert len(files)==5
    assert all((ROOT/OUT/n).read_bytes()==v.encode() for n,v in files.items())
    assert baseline["report_hash"]==stable_hash({k:v for k,v in baseline.items() if k!="report_hash"})
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in baseline["source_hashes"].items())
    manifest=json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest()==h for n,h in manifest["artifacts"].items())
    assert all((ROOT/OUT/ref).is_file() for ref in re.findall(r'(?:href|src)="([^"]+)"',files["index.html"]))
    rows=list(csv.DictReader(io.StringIO(files["followup-ledger.csv"].lstrip("\ufeff"))))
    assert len(rows)==6 and all(x["資料回覆狀態"]=="尚未收到" for x in rows)
    assert all(x[k]=="" for x in rows for k in ["回覆摘要","已議定窗口","回覆期限","屋主選擇範圍","專業文件依據","圖面發行日期"])
    assert baseline["protected_controls_unchanged"]==149 and not baseline["primary_abc_or_3d_changed"]


def test_private_summary_does_not_overwrite_input_existing_results_or_public_template(monkeypatch,tmp_path,baseline):
    d=synthetic(baseline)
    reply(d["records"][1])
    source=tmp_path/"inputs/private/records.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(d),encoding="utf-8")
    original=source.read_bytes()
    monkeypatch.setattr(exporter,"ROOT",tmp_path)
    monkeypatch.setattr(exporter,"build",lambda root,document=None:build(ROOT,document))
    args=["--records","inputs/private/records.json","--output","inputs/private/summary-001"]
    assert exporter.main(args)==0
    result=tmp_path/"inputs/private/summary-001/review.json"
    saved=result.read_bytes()
    assert json.loads(saved)["replies_reported"]==1
    assert exporter.main(args)==1
    assert result.read_bytes()==saved and source.read_bytes()==original and not (tmp_path/OUT).exists()


@pytest.mark.parametrize("args",[["--records","README.md","--output","inputs/private/summary"],["--output","inputs/private/summary"],
    ["--check","--records","inputs/private/records.json","--output","inputs/private/summary"]])
def test_cli_rejects_invalid_modes_or_nonprivate_input_before_build(monkeypatch,tmp_path,args):
    monkeypatch.setattr(exporter,"ROOT",tmp_path)
    monkeypatch.setattr(exporter,"build",lambda *a:pytest.fail("Must not read/build invalid input"))
    assert exporter.main(args)==1

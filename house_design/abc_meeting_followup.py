"""Track six declared coordination records without interpreting them as approvals."""
from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG="inputs/abc-meeting-followup-laundry-v1.json"
OUT="structured/planning/abc-meeting-followup"
STATUS_FIELDS={
    "reply_state":{"not-received","partial","received-for-review","conflict-reported"},
    "cost_schedule_state":{"unknown","requested","documented"},
    "owner_choice_state":{"not-recorded","deferred","documented"},
    "professional_record_state":{"unknown","pending","documented"},
    "drawing_release_record_state":{"not-recorded","documented"},
}
TEXT_FIELDS=["reply_summary","reply_reference","drawing_revision","agreed_contact","cost_schedule_reference",
    "owner_choice_scope","owner_choice_reference","professional_scope","professional_reference",
    "drawing_release_revision","drawing_release_issuer","drawing_release_reference"]
DATE_FIELDS=["reply_received_date","agreed_due_date","owner_choice_date","professional_record_date","drawing_release_date"]


def valid_date(value):
    if value is None:
        return True
    try:
        return isinstance(value,str) and date.fromisoformat(value).isoformat()==value
    except ValueError:
        return False


def template(cfg,agenda):
    rows=[]
    for slot in agenda["slots"]:
        row={"slot_id":slot["id"],"buildings":slot["buildings"],"question_ids":slot["question_ids"],
            "reply_state":"not-received","cost_schedule_state":"unknown","owner_choice_state":"not-recorded",
            "professional_record_state":"unknown","drawing_release_record_state":"not-recorded",
            **dict.fromkeys(TEXT_FIELDS,""),**dict.fromkeys(DATE_FIELDS),"missing_items":[],"affected_drawing_ids":[]}
        rows.append(row)
    return {"schema":"house-abc-meeting-followup-records-v1","config_hash":stable_hash(cfg),
        "agenda_sha256":cfg["pinned_sources"][cfg["agenda"]],"meeting_date":None,"meeting_reference":"","records":rows}


def validate_records(base,document):
    received=copy.deepcopy(base if document is None else document)
    if (not isinstance(received,dict) or set(received)!=set(base)
            or any(received[k]!=base[k] for k in ["schema","config_hash","agenda_sha256"])
            or not valid_date(received["meeting_date"]) or not isinstance(received["meeting_reference"],str)
            or len(received["meeting_reference"])>4000 or not isinstance(received["records"],list)):
        raise ContractError("Follow-up records must use this exact coordination source revision and ISO dates")
    if received["meeting_date"] is not None and not received["meeting_reference"].strip():
        raise ContractError("A reported meeting date needs an explicit meeting record reference")
    indexed={r["slot_id"]:r for r in base["records"]}
    seen={}
    for row in received["records"]:
        if (not isinstance(row,dict) or not isinstance(row.get("slot_id"),str)
                or row["slot_id"] not in indexed or row["slot_id"] in seen):
            raise ContractError("Keep the six unique original coordination record identities")
        old=indexed[row["slot_id"]]
        if set(row)!=set(old) or any(row[k]!=old[k] for k in ["slot_id","buildings","question_ids"]):
            raise ContractError("Do not mix buildings, alter question references or add approval fields")
        for key,allowed in STATUS_FIELDS.items():
            if not isinstance(row[key],str) or row[key] not in allowed:
                raise ContractError("Unknown declared record state: "+key)
        if any(not isinstance(row[k],str) or len(row[k])>4000 for k in TEXT_FIELDS):
            raise ContractError("Follow-up text fields must be bounded strings")
        if any(not valid_date(row[k]) for k in DATE_FIELDS):
            raise ContractError("Follow-up dates use YYYY-MM-DD or null, not empty or guessed dates")
        for key in ["missing_items","affected_drawing_ids"]:
            if (not isinstance(row[key],list) or len(row[key])>50 or any(not isinstance(v,str) or not v.strip() or len(v)>1000 for v in row[key])
                    or len(row[key])!=len(set(row[key]))):
                raise ContractError("Use bounded unique missing items and affected drawing IDs")
        if row["reply_state"]!="not-received" and any(not row[k].strip() for k in ["reply_summary","reply_reference","drawing_revision"]):
            raise ContractError("A reported reply needs its summary, source and declared drawing revision")
        if row["reply_state"]!="not-received" and row["reply_received_date"] is None:
            raise ContractError("A reported reply needs its received date")
        if row["reply_state"]=="not-received" and any(row[k] for k in ["reply_summary","reply_reference","drawing_revision","reply_received_date"]):
            raise ContractError("Do not hide received reply content under a not-received state")
        if row["owner_choice_state"]=="not-recorded" and any(row[k] for k in ["owner_choice_scope","owner_choice_reference","owner_choice_date"]):
            raise ContractError("An owner choice note needs an explicit deferred or documented state")
        if row["drawing_release_record_state"]=="not-recorded" and any(row[k] for k in ["drawing_release_revision","drawing_release_issuer","drawing_release_reference","drawing_release_date"]):
            raise ContractError("Do not hide reported drawing release content under a not-recorded state")
        if row["agreed_due_date"] is not None and not row["agreed_contact"].strip():
            raise ContractError("An agreed reply deadline needs an agreed contact; otherwise keep both pending")
        requirements={
            "cost_schedule_state":["cost_schedule_reference"],
            "owner_choice_state":["owner_choice_scope","owner_choice_reference","owner_choice_date"],
            "professional_record_state":["professional_scope","professional_reference","professional_record_date"],
            "drawing_release_record_state":["drawing_release_revision","drawing_release_issuer","drawing_release_reference","drawing_release_date"],
        }
        for state,keys in requirements.items():
            if row[state]=="documented" and any(row[k] is None or isinstance(row[k],str) and not row[k].strip() for k in keys):
                raise ContractError("A documented record needs independent source/scope/date fields: "+state)
        seen[row["slot_id"]]=row
    if set(seen)!=set(indexed):
        raise ContractError("Keep all six slots; unused records remain blank, not deleted")
    received["records"]=[seen[r["slot_id"]] for r in base["records"]]
    return received


def evaluate(received,agenda):
    definitions={s["id"]:s for s in agenda["slots"]}
    rows=[]
    for r in received["records"]:
        flags=[]
        if r["reply_state"]=="not-received":
            flags.append("reply-not-received")
        elif r["reply_state"]=="partial":
            flags.append("partial-reply-needs-evidence")
        elif r["reply_state"]=="conflict-reported":
            flags.append("declared-conflict-needs-complete-alternatives")
        else:
            flags.append("reply-reported-not-yet-verified")
        if r["missing_items"]:
            flags.append("declared-missing-items")
        if r["missing_items"] and not r["agreed_contact"].strip():
            flags.append("reply-contact-not-agreed")
        if r["missing_items"] and r["agreed_due_date"] is None:
            flags.append("reply-deadline-not-agreed")
        if r["cost_schedule_state"]!="documented":
            flags.append("cost-schedule-not-documented")
        if r["owner_choice_state"]!="documented":
            flags.append("owner-choice-not-recorded" if r["owner_choice_state"]=="not-recorded" else "owner-choice-deferred")
        if r["professional_record_state"]!="documented":
            flags.append("professional-record-not-documented")
        if r["drawing_release_record_state"]!="documented":
            flags.append("drawing-release-not-recorded")
        rows.append({**r,"topic":definitions[r["slot_id"]]["title"],"record_flags":flags,
            "documented_professional_record_not_content_verified":r["professional_record_state"]=="documented",
            "documented_drawing_release_not_authority_verified":r["drawing_release_record_state"]=="documented",
            "deadline_overdue":None,"record_closed":False,"adopted":False,"professional_approval":"unknown","construction_release":False})
    return rows


def build(root,record_document=None):
    root,cache=Path(root),{}
    cfg=read_json(root/CONFIG)
    previous=cfg.get("supersedes_config",{})
    if (cfg.get("revision")!=2 or previous.get("source")!="inputs/abc-meeting-followup.json"
            or sha256_file(public_path(root,previous["source"]))!=previous.get("sha256")
            or cfg.get("owner_direction_reference")!="inputs/references/abc-laundry-owner-20261113.json"):
        raise ContractError("Use the explicit laundry follow-up revision without changing the original template source")
    if (cfg.get("schema")!="house-abc-meeting-followup-v1"
            or cfg.get("authority")!="declared-meeting-records-only-not-design-adoption-or-professional-approval"
            or cfg.get("agenda")!="inputs/abc-coordination-agenda.json"
            or cfg.get("builder_plan")!="inputs/builder-communication-plan.json"):
        raise ContractError("Meeting follow-up records do not adopt designs or replace the original agenda")
    for n,h in cfg["pinned_sources"].items():
        if sha256_file(public_path(root,n))!=h:
            raise ContractError("Follow-up agenda/question revision changed: "+n)
    agenda=read_json(root/cfg["agenda"])
    controls=read_json(root/cfg["protected_controls"])["hashes"]
    for n,h in controls.items():
        if digest(root,n,cache)!=h:
            raise ContractError("Protected original changed: "+n)
    base=template(cfg,agenda)
    received=validate_records(base,record_document)
    rows=evaluate(received,agenda)
    names=[CONFIG,previous["source"],*cfg["pinned_sources"],cfg["protected_controls"],"house_design/abc_meeting_followup.py",
        "scripts/export_abc_meeting_followup.py","Docs/abc-meeting-followup-v1.md"]
    report={"schema":"house-abc-meeting-followup-report-v1","date":cfg["date"],"config":cfg,
        "record_template":base,"received_records":received,"record_document_hash":None if record_document is None else stable_hash(record_document),
        "slot_evaluations":rows,"replies_reported":sum(r["reply_state"]!="not-received" for r in rows),
        "conflicts_reported":sum(r["reply_state"]=="conflict-reported" for r in rows),
        "owner_choices_documented":sum(r["owner_choice_state"]=="documented" for r in rows),
        "professional_records_documented":sum(r["professional_record_state"]=="documented" for r in rows),
        "drawing_release_records_documented":sum(r["drawing_release_record_state"]=="documented" for r in rows),
        "meeting_reported":received["meeting_date"] is not None,"actual_record_imported":record_document is not None,
        "whole_project_blocked":False,"automatically_closed_records":0,"automatic_fee_total":None,
        "protected_controls_unchanged":len(controls),"formal_requirements_written":False,"primary_abc_or_3d_changed":False,
        "adopted":False,"professional_approval":"unknown","construction_release":False,"rendered_qa":"not-run",
        "source_hashes":{n:digest(root,n,cache) for n in dict.fromkeys(names)}}
    report["report_hash"]=stable_hash(report)
    return report

"""Research reply routes and non-additive quote scope; no automatic design selection."""
from __future__ import annotations

from pathlib import Path

from house_design.b_front_drop_conditions import build as build_intake
from house_design.contracts import ContractError, read_json, sha256_file, stable_hash
from house_design.project_status import digest, public_path

CONFIG="inputs/b-front-drop-response-routes.json"
OUT="structured/planning/b-front-drop-reply-routes"
TRIGGERS=["terminal-not-available","terminal-arithmetic-conflict","upstream-conflict","drop-interval-conflict",
    "plan-envelope-conflict","all-local-arithmetic-compatible","partial-data"]


def reply_actions(cfg,intake):
    rows={r["id"]:r for r in intake["condition_evaluations"]}
    if set(rows)!={"local-drop","upstream-gap","front-terminal","plan-envelope"}:
        raise ContractError("Reply routing requires all four source-verified G4D evaluations")
    terminal=rows["front-terminal"]["status"]
    missing={key:r["missing_fields"] for key,r in rows.items() if r["missing_fields"]}
    activated={
        "terminal-not-available":terminal=="front-terminal-not-documented-available-stop-locking",
        "terminal-arithmetic-conflict":terminal=="reject-declared-local-arithmetic",
        "upstream-conflict":rows["upstream-gap"]["status"]=="reject-declared-local-arithmetic",
        "drop-interval-conflict":rows["local-drop"]["status"]=="reject-declared-local-arithmetic",
        "plan-envelope-conflict":rows["plan-envelope"]["status"]=="reject-declared-local-arithmetic",
        "all-local-arithmetic-compatible":all(r["dimension_or_interval_compatible_only"] is True for r in rows.values()),
        "partial-data":bool(missing)}
    state=("declared-front-terminal-not-available" if activated["terminal-not-available"]
        else "declared-front-terminal-arithmetic-conflict" if activated["terminal-arithmetic-conflict"]
        else "documented-and-dimensionally-compatible-only" if rows["front-terminal"]["dimension_or_interval_compatible_only"] is True
        else "pending")
    result=[]
    for route in cfg["response_routes"]:
        active=activated[route["trigger_code"]]
        result.append({**route,"activated_for_declared_inputs":active,
            "status":"research-next-action-only" if active else "not-triggered-by-current-inputs",
            "front_terminal_precondition_state":state,
            "downstream_action_is_conditional_on_terminal_review":route["trigger_code"] not in {"terminal-not-available","terminal-arithmetic-conflict","partial-data"},
            "selected_layout":None,"owner_choice":None,"professional_approval":"unknown","construction_release":False})
    return result,missing,state


def build(root,condition_report=None):
    root,cache=Path(root),{}
    cfg=read_json(root/CONFIG)
    if (cfg.get("schema")!="house-b-front-drop-response-routes-v1" or cfg.get("adopted") is not False
            or cfg["intake_report"]!="structured/coordination/b-front-drop-conditions-v1/review.json"
            or [cfg[k] for k in ["sequence_id","comparison_id","task_id"]]!=["SEQ-04","BC-CMP-01","B-WET-001"]
            or [r["id"] for r in cfg["response_routes"]]!=[f"BFR-{i:02d}" for i in range(1,8)]
            or [r["trigger_code"] for r in cfg["response_routes"]]!=TRIGGERS
            or [r["priority"] for r in cfg["response_routes"]]!=list(range(1,8))
            or [r["id"] for r in cfg["quote_scopes"]]!=[f"BFC-{i:02d}" for i in range(1,7)]):
        raise ContractError("Keep seven conditional research routes, six quote scopes and the existing B decision identities")
    for name,h in cfg["pinned_sources"].items():
        if sha256_file(public_path(root,name))!=h:
            raise ContractError("G4D intake revision changed: "+name)
    baseline=read_json(root/cfg["intake_report"])
    if baseline.get("report_hash")!=stable_hash({k:v for k,v in baseline.items() if k!="report_hash"}):
        raise ContractError("G4D public intake report seal changed")
    current=build_intake(root)
    if current["report_hash"]!=baseline["report_hash"] or baseline["condition_values_received"]!=0:
        raise ContractError("Routing requires the reviewed blank public intake, not rewritten or private baseline data")
    gate_ids={r["id"] for r in baseline["engineering_gates"]}
    scopes={r["id"] for r in cfg["quote_scopes"]}
    for r in cfg["response_routes"]:
        if not r["gate_ids"] or set(r["gate_ids"])-gate_ids or not r["quote_scope_ids"] or set(r["quote_scope_ids"])-scopes:
            raise ContractError("Reply routes must reference existing builder questions and quote scopes")
    selected=baseline
    if condition_report is not None:
        if (not isinstance(condition_report,dict) or condition_report.get("schema")!=baseline["schema"]
                or condition_report.get("report_hash")!=stable_hash({k:v for k,v in condition_report.items() if k!="report_hash"})):
            raise ContractError("Private input must be an intact G4D arithmetic report, not reply text or edited statuses")
        document=condition_report.get("received_conditions") if condition_report.get("condition_document_hash") is not None else None
        expected=build_intake(root,document)
        if expected!=condition_report:
            raise ContractError("Private G4D result does not match its declared conditions and current source revision")
        selected=expected
    actions,missing,state=reply_actions(cfg,selected)
    report={"schema":"house-b-front-drop-reply-routes-report-v1","date":cfg["date"],"config":cfg,
        "baseline_intake_report_hash":baseline["report_hash"],"evaluated_intake_report_hash":selected["report_hash"],
        "condition_report_imported":condition_report is not None,"condition_values_received":selected["condition_values_received"],
        "reply_actions":actions,"missing_fields_by_group":missing,"front_terminal_precondition_state":state,
        "active_action_ids":[a["id"] for a in actions if a["activated_for_declared_inputs"]],
        "quote_scopes":[{**r,"agreed_scope":None,"fee_amount":None,"currency":None,"contract_inclusion_or_credit":None,
            "construction_cost":None,"schedule_days":None,"owner_choice":None,"accepted":False} for r in cfg["quote_scopes"]],
        "alternative_scope_ids_not_to_add_together":["BFC-02","BFC-03","BFC-04"],
        "overall_quote_total":None,"automatic_next_layout_selection":None,"owner_decision_required_now":False,
        "protected_controls_unchanged":baseline["protected_controls_unchanged"],"original_family_rules_changed":False,
        "primary_abc_or_3d_changed":False,"RF24_Q3_acoustics_R1_waterproofing_resolved":False,
        "adopted":False,"professional_approval":"unknown","construction_release":False,"rendered_qa":"not-run"}
    names=[CONFIG,*cfg["pinned_sources"],*baseline["source_hashes"],"house_design/b_front_drop_reply_routes.py",
        "scripts/export_b_front_drop_reply_routes.py","Docs/b-front-drop-response-routes-v1.md"]
    report["source_hashes"]={n:digest(root,n,cache) for n in dict.fromkeys(names)}
    report["report_hash"]=stable_hash(report)
    return report

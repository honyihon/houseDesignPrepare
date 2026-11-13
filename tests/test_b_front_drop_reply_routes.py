"""Typed response routing with synthetic declarations; no actual replies or external tools."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
from pathlib import Path

import pytest

from house_design.b_front_drop_conditions import build as build_intake
from house_design.b_front_drop_reply_routes import CONFIG, OUT, build
from house_design.contracts import ContractError, stable_hash
from scripts import export_b_front_drop_reply_routes as exporter

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def baseline():
    return build(ROOT)


@pytest.fixture(scope="module")
def all_compatible_document():
    d=copy.deepcopy(build_intake(ROOT)["condition_template"])
    d["basis"]={"drawing_revision":"SYNTHETIC-ONLY","datum_id":"SYNTHETIC-Z","coordinate_note":"Original G4D test frame; not site data"}
    for g in d["groups"]:
        g["reference"]="Synthetic declarations for software test only"
    values={g["id"]:g["values"] for g in d["groups"]}
    values["local-drop"].update(highest_package_top_before_drop_z_mm=3500,lowest_package_bottom_before_drop_z_mm=3300,
        lowest_soffit_over_complete_box_z_mm=3400,finished_floor_z_mm=0,upper_installation_gap_mm=20,
        extra_upper_fitting_mm=0,additional_upper_reserve_mm=20,extra_lower_fitting_mm=0,operating_space_below_mm=50,required_finished_clear_height_mm=2800)
    values["upstream-gap"].update(pipe_package_top_z_mm=3500,lowest_structure_z_mm=3600,required_upper_gap_mm=50,
        extra_upper_fitting_mm=0,additional_reserve_mm=10)
    values["front-terminal"].update(rights_record="documented",connection_record="documented",start_invert_z_mm=-300,
        connection_invert_z_mm=-500,horizontal_route_mm=6000,slope_denominator=50,additional_fall_reserve_mm=25)
    values["plan-envelope"].update(front_growth_mm=0,rear_growth_mm=0,left_growth_mm=0,right_growth_mm=0,
        shift_back_mm=0,required_platform_gap_mm=10)
    return d


def changed(document,group,**updates):
    d=copy.deepcopy(document)
    next(g for g in d["groups"] if g["id"]==group)["values"].update(updates)
    return d


def test_blank_baseline_activates_only_data_preparation_without_failure_or_choice(baseline):
    assert baseline["active_action_ids"]==["BFR-07"] and baseline["condition_values_received"]==0
    assert len(baseline["missing_fields_by_group"])==4
    assert baseline["front_terminal_precondition_state"]=="pending"
    assert baseline["automatic_next_layout_selection"] is None and not baseline["owner_decision_required_now"]
    assert all(a["selected_layout"] is a["owner_choice"] is None and not a["construction_release"] for a in baseline["reply_actions"])
    assert not baseline["condition_report_imported"] and baseline["professional_approval"]=="unknown"


def test_all_local_numbers_compatible_still_requests_full_review_without_release(all_compatible_document):
    condition=build_intake(ROOT,all_compatible_document)
    r=build(ROOT,condition)
    assert r["active_action_ids"]==["BFR-06"] and r["condition_values_received"]==28
    assert r["front_terminal_precondition_state"]=="documented-and-dimensionally-compatible-only"
    assert not r["adopted"] and not r["construction_release"] and not r["RF24_Q3_acoustics_R1_waterproofing_resolved"]
    assert all(a["professional_approval"]=="unknown" for a in r["reply_actions"])


@pytest.mark.parametrize("group,updates,expected",[
    ("front-terminal",{"rights_record":"not-available"},"BFR-01"),
    ("front-terminal",{"connection_invert_z_mm":-350},"BFR-02"),
    ("upstream-gap",{"lowest_structure_z_mm":3510},"BFR-03"),
    ("local-drop",{"required_finished_clear_height_mm":3200},"BFR-04"),
    ("plan-envelope",{"front_growth_mm":25},"BFR-05"),
])
def test_each_numeric_or_document_failure_has_a_specific_nonadopting_research_action(all_compatible_document,group,updates,expected):
    r=build(ROOT,build_intake(ROOT,changed(all_compatible_document,group,**updates)))
    assert r["active_action_ids"]==[expected]
    a=next(a for a in r["reply_actions"] if a["id"]==expected)
    assert a["status"]=="research-next-action-only" and a["selected_layout"] is None
    assert a["gate_ids"] and a["quote_scope_ids"] and not r["original_family_rules_changed"]


def test_common_terminal_problem_is_listed_before_but_does_not_hide_other_failures(all_compatible_document):
    d=changed(all_compatible_document,"front-terminal",rights_record="not-available")
    d=changed(d,"local-drop",required_finished_clear_height_mm=3200)
    d=changed(d,"upstream-gap",lowest_structure_z_mm=3510)
    r=build(ROOT,build_intake(ROOT,d))
    assert r["active_action_ids"]==["BFR-01","BFR-03","BFR-04"]
    assert r["front_terminal_precondition_state"]=="declared-front-terminal-not-available"
    assert next(a for a in r["reply_actions"] if a["id"]=="BFR-04")["downstream_action_is_conditional_on_terminal_review"]
    assert r["automatic_next_layout_selection"] is None


def test_missing_data_is_not_conflict_and_can_coexist_with_a_specific_failure(all_compatible_document):
    d=changed(all_compatible_document,"upstream-gap",pipe_package_top_z_mm=None)
    d=changed(d,"plan-envelope",front_growth_mm=25)
    r=build(ROOT,build_intake(ROOT,d))
    assert r["active_action_ids"]==["BFR-05","BFR-07"]
    assert r["missing_fields_by_group"]=={"upstream-gap":["pipe_package_top_z_mm"]}
    assert "BFR-03" not in r["active_action_ids"] and not r["owner_decision_required_now"]


@pytest.mark.parametrize("defect",["seal","edited-status","foreign-condition-revision","edited-count","edited-source","reply-text"])
def test_private_import_recomputes_declared_conditions_and_rejects_edited_or_unrelated_results(all_compatible_document,defect):
    r=build_intake(ROOT,all_compatible_document)
    if defect=="seal":
        r["report_hash"]="0"*64
    elif defect=="edited-status":
        r["condition_evaluations"][0]["status"]="pending"
    elif defect=="foreign-condition-revision":
        r["received_conditions"]["parent_report_hash"]="0"*64
    elif defect=="edited-count":
        r["condition_values_received"]=0
    elif defect=="edited-source":
        r["source_hashes"][next(iter(r["source_hashes"]))]="0"*64
    else:
        r={"reply":"可以","adopted":True}
    if defect not in {"seal","reply-text"}:
        r["report_hash"]=stable_hash({k:v for k,v in r.items() if k!="report_hash"})
    with pytest.raises(ContractError):
        build(ROOT,r)


def test_common_and_exclusive_quote_scopes_leave_fees_and_total_unknown(baseline):
    assert len(baseline["quote_scopes"])==6
    assert baseline["alternative_scope_ids_not_to_add_together"]==["BFC-02","BFC-03","BFC-04"]
    assert baseline["overall_quote_total"] is None
    for q in baseline["quote_scopes"]:
        assert q["fee_amount"] is q["construction_cost"] is q["currency"] is q["schedule_days"] is q["owner_choice"] is None
        assert not q["accepted"]
    rows=exporter.quote_rows(baseline)
    assert sum(bool(r["互斥設計組"]) for r in rows)==3
    assert all(r["研究設計費及幣別"]==r["施工價及幣別"]==r["屋主選擇及日期"]=="" for r in rows)


def test_public_artifacts_sources_and_blank_reply_fields_are_current(baseline):
    files=exporter.render(baseline)
    assert len(files)==5
    assert all((ROOT/OUT/n).read_bytes()==v.encode() for n,v in files.items())
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in baseline["source_hashes"].items())
    m=json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest()==h for n,h in m["artifacts"].items())
    assert all((ROOT/OUT/ref).is_file() for ref in re.findall(r'(?:href|src)="([^"]+)"',files["index.html"]))
    rows=list(csv.DictReader(io.StringIO(files["response-routes.csv"].lstrip("\ufeff"))))
    assert len(rows)==7
    assert all(r[k]=="" for r in rows for k in ["屋主選擇及日期","專業核對","施工圖發行"])
    assert baseline["protected_controls_unchanged"]==149 and not baseline["primary_abc_or_3d_changed"]


def test_private_routing_preserves_input_old_results_and_public_baseline(monkeypatch,tmp_path,all_compatible_document):
    condition=build_intake(ROOT,all_compatible_document)
    source=tmp_path/"inputs/private/arithmetic/review.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps(condition),encoding="utf-8")
    before=source.read_bytes()
    monkeypatch.setattr(exporter,"ROOT",tmp_path)
    monkeypatch.setattr(exporter,"build",lambda root,report=None:build(ROOT,report))
    args=["--result","inputs/private/arithmetic/review.json","--output","inputs/private/routing-001"]
    assert exporter.main(args)==0
    output=tmp_path/"inputs/private/routing-001/review.json"
    data=output.read_bytes()
    assert json.loads(data)["active_action_ids"]==["BFR-06"]
    assert exporter.main(args)==1
    assert output.read_bytes()==data and source.read_bytes()==before
    assert not (tmp_path/OUT).exists()


@pytest.mark.parametrize("args",[
    ["--result","structured/review.json","--output","inputs/private/routing"],
    ["--output","inputs/private/routing"],
    ["--check","--result","inputs/private/review.json","--output","inputs/private/routing"]])
def test_invalid_import_or_output_modes_stop_before_any_computation(monkeypatch,tmp_path,args):
    monkeypatch.setattr(exporter,"ROOT",tmp_path)
    monkeypatch.setattr(exporter,"build",lambda *a:pytest.fail("Invalid modes must not start evaluation"))
    assert exporter.main(args)==1


def test_original_intake_hash_and_routing_config_remain_source_bound(baseline):
    cfg=json.loads((ROOT/CONFIG).read_text())
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in cfg["pinned_sources"].items())
    assert baseline["report_hash"]==stable_hash({k:v for k,v in baseline.items() if k!="report_hash"})

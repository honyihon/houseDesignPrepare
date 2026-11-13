"""Bounded interface tests using synthetic inputs only; no site values or approvals."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
from pathlib import Path

import pytest

from house_design.b_front_drop_conditions import CONFIG, GROUPS, OUT, build, validate_conditions
from house_design.contracts import ContractError, stable_hash
from scripts import export_b_front_drop_conditions as exporter

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def synthetic(report):
    d=copy.deepcopy(report["condition_template"])
    d["basis"]={"drawing_revision":"SYNTHETIC-ONLY", "datum_id":"SYNTHETIC-Z", "coordinate_note":"Original G4D model frame for tests only"}
    for g in d["groups"]:
        g["reference"]="Synthetic unit test; not site/product or professional evidence"
    return d


def by_group(document, key):
    return next(g for g in document["groups"] if g["id"]==key)["values"]


def local_values():
    return {"highest_package_top_before_drop_z_mm":3704.9,"lowest_package_bottom_before_drop_z_mm":3511.6,
        "lowest_soffit_over_complete_box_z_mm":3221.521,"finished_floor_z_mm":0,"upper_installation_gap_mm":50,
        "extra_upper_fitting_mm":50,"additional_upper_reserve_mm":0,"extra_lower_fitting_mm":0,
        "operating_space_below_mm":50,"required_finished_clear_height_mm":2800}


def test_public_interface_is_blank_and_all_four_groups_and_gates_remain_unknown(report):
    assert len(report["field_guide"])==28 and report["condition_values_received"]==0
    assert all(v is None for g in report["condition_template"]["groups"] for v in g["values"].values())
    assert all(r["status"]=="pending" and r["dimension_or_interval_compatible_only"] is None for r in report["condition_evaluations"])
    assert [g["id"] for g in report["engineering_gates"]]==[f"BFD-{i:02d}" for i in range(1,9)]
    assert all(g["received_reply"] is g["owner_choice"] is None and g["professional_review"]=="unknown" for g in report["engineering_gates"])


def test_partial_conditions_never_zero_fill_or_reuse_hypothetical_numbers(report):
    d=synthetic(report)
    by_group(d,"local-drop")["highest_package_top_before_drop_z_mm"]=3704.9
    r=build(ROOT,d)
    assert r["condition_values_received"]==1
    assert r["condition_evaluations"][0]["status"]=="pending"
    assert r["condition_evaluations"][0]["maximum_effective_drop_mm"] is None
    assert by_group(r["received_conditions"],"local-drop")["extra_lower_fitting_mm"] is None


def test_local_interval_uses_physical_bottom_without_double_counting_lower_access(report):
    d=synthetic(report)
    by_group(d,"local-drop").update(local_values())
    r=build(ROOT,d)
    row=r["condition_evaluations"][0]
    assert row["minimum_effective_drop_mm"]==pytest.approx(583.379)
    assert row["maximum_effective_drop_mm"]==pytest.approx(661.6)
    assert row["interval_width_mm"]==pytest.approx(78.221)
    assert row["dimension_or_interval_compatible_only"] is True
    assert row["selected_drop_mm"] is None and not row["may_release_work"]
    assert not r["adopted"] and r["professional_approval"]=="unknown"
    assert all(g["professional_review"]=="unknown" for g in r["engineering_gates"])


def test_lower_space_conflict_does_not_auto_lower_ceiling_or_select_another_layout(report):
    d=synthetic(report)
    by_group(d,"local-drop").update(local_values(),required_finished_clear_height_mm=3000)
    r=build(ROOT,d)
    row=r["condition_evaluations"][0]
    assert row["maximum_effective_drop_mm"]==pytest.approx(461.6)
    assert row["interval_width_mm"]<0 and row["status"]=="reject-declared-local-arithmetic"
    assert r["automatic_next_layout_selection"] is None and r["any_declared_conflict"]


def test_uniform_datum_shift_does_not_change_interval_or_gap(report):
    d=synthetic(report)
    by_group(d,"local-drop").update(local_values())
    first=build(ROOT,d)["condition_evaluations"][0]
    for name in by_group(d,"local-drop"):
        if name.endswith("_z_mm"):
            by_group(d,"local-drop")[name]-=1000
    second=build(ROOT,d)["condition_evaluations"][0]
    assert first==second


def test_upstream_comparison_is_independent_of_compatible_local_drop(report):
    d=synthetic(report)
    by_group(d,"local-drop").update(local_values())
    by_group(d,"upstream-gap").update(pipe_package_top_z_mm=3788.4,lowest_structure_z_mm=3800,
        required_upper_gap_mm=50,extra_upper_fitting_mm=0,additional_reserve_mm=0)
    r=build(ROOT,d)
    assert r["condition_evaluations"][0]["dimension_or_interval_compatible_only"]
    assert r["condition_evaluations"][1]["margin_mm"]==pytest.approx(-38.4)
    assert r["condition_evaluations"][1]["status"]=="reject-declared-local-arithmetic"


def test_terminal_uses_declared_inverts_length_and_slope_not_top_or_straight_lower_bound(report):
    d=synthetic(report)
    by_group(d,"front-terminal").update(rights_record="documented",connection_record="documented",start_invert_z_mm=-300,
        connection_invert_z_mm=-500,horizontal_route_mm=6000,slope_denominator=50,additional_fall_reserve_mm=25)
    row=build(ROOT,d)["condition_evaluations"][2]
    assert row["required_slope_fall_mm"]==120 and row["margin_mm"]==55
    assert row["status"]=="declared-local-arithmetic-compatible" and not row["may_release_work"]
    assert row["whole_route_or_professional_approval"]=="unknown"


def test_unavailable_terminal_stops_locking_even_with_other_values_missing(report):
    d=synthetic(report)
    by_group(d,"front-terminal")["rights_record"]="not-available"
    r=build(ROOT,d)
    assert r["condition_evaluations"][2]["status"]=="front-terminal-not-documented-available-stop-locking"
    assert r["any_declared_conflict"] and not r["original_family_rules_changed"]


def test_plan_growth_uses_original_frame_and_reports_collisions_without_moving_geometry(report):
    d=synthetic(report)
    by_group(d,"plan-envelope").update(front_growth_mm=25,rear_growth_mm=25,left_growth_mm=25,right_growth_mm=25,
        shift_back_mm=0,required_platform_gap_mm=0)
    row=build(ROOT,d)["condition_evaluations"][3]
    assert row["platform_overlap_sqm"]==.00225 and row["margin_mm"]==-5
    assert row["status"]=="reject-declared-local-arithmetic"
    by_group(d,"plan-envelope")["shift_back_mm"]=5
    row=build(ROOT,d)["condition_evaluations"][3]
    assert row["platform_overlap_sqm"]==0 and row["margin_mm"]==0
    assert not row["expanded_box_structure_verified"] and not row["wholly_in_reference_return_footprint"]
    assert not row["may_release_work"]


def test_large_rear_shift_cannot_leave_reference_stair_enclosure(report):
    d=synthetic(report)
    by_group(d,"plan-envelope").update(front_growth_mm=0,rear_growth_mm=0,left_growth_mm=0,right_growth_mm=0,
        shift_back_mm=6000,required_platform_gap_mm=0)
    row=build(ROOT,d)["condition_evaluations"][3]
    assert row["margin_mm"]>0 and not row["within_reference_stair_enclosure"]
    assert row["status"]=="reject-declared-local-arithmetic"


@pytest.mark.parametrize("defect",["parent","config","case","missing-group","duplicate-group","missing-field","extra-field","boolean","nan","negative-growth","zero-slope","no-source","no-revision","no-datum","no-plan-note","free-text-legal","reversed-body","non-string-group"])
def test_foreign_revisions_malformed_numbers_missing_references_and_silent_fields_rejected(report,defect):
    d=synthetic(report)
    v=by_group(d,"local-drop")
    if defect=="parent":
        d["parent_report_hash"]="0"*64
    elif defect=="config":
        d["config_hash"]="0"*64
    elif defect=="case":
        d["reference_case"]="G5"
    elif defect=="missing-group":
        d["groups"].pop()
    elif defect=="duplicate-group":
        d["groups"].append(copy.deepcopy(d["groups"][0]))
    elif defect=="missing-field":
        v.pop("additional_upper_reserve_mm")
    elif defect=="extra-field":
        v["approved"]=True
    elif defect=="boolean":
        v["extra_upper_fitting_mm"]=True
    elif defect=="nan":
        v["extra_upper_fitting_mm"]=float("nan")
    elif defect=="negative-growth":
        by_group(d,"plan-envelope")["front_growth_mm"]=-1
    elif defect=="zero-slope":
        by_group(d,"front-terminal")["slope_denominator"]=0
    elif defect=="no-source":
        v["extra_upper_fitting_mm"]=0
        d["groups"][0]["reference"]=""
    elif defect=="no-revision":
        v["extra_upper_fitting_mm"]=0
        d["basis"]["drawing_revision"]=""
    elif defect=="no-datum":
        v["highest_package_top_before_drop_z_mm"]=3500
        d["basis"]["datum_id"]=""
    elif defect=="no-plan-note":
        by_group(d,"plan-envelope")["front_growth_mm"]=0
        d["basis"]["coordinate_note"]=""
    elif defect=="free-text-legal":
        by_group(d,"front-terminal")["rights_record"]="yes"
    elif defect=="reversed-body":
        v["highest_package_top_before_drop_z_mm"]=3000
        v["lowest_package_bottom_before_drop_z_mm"]=3200
    else:
        d["groups"][0]["id"]=[]
    with pytest.raises(ContractError):
        validate_conditions(report["condition_template"],d)


def test_public_artifacts_and_all_references_are_current(report):
    files=exporter.render(report)
    assert len(files)==8
    assert all((ROOT/OUT/n).read_bytes()==v.encode() for n,v in files.items())
    assert report["report_hash"]==stable_hash({k:v for k,v in report.items() if k!="report_hash"})
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in report["source_hashes"].items())
    m=json.loads(files["artifact-manifest.json"])
    assert all(hashlib.sha256(files[n].encode()).hexdigest()==h for n,h in m["artifacts"].items())
    assert all((ROOT/OUT/ref).is_file() for ref in re.findall(r'(?:href|src)="([^"]+)"',files["index.html"]))
    rows=list(csv.DictReader(io.StringIO(files["builder-replies.csv"].lstrip("\ufeff"))))
    assert len(rows)==8
    assert all(row[k]=="" for row in rows for k in ["建商專業回覆","屋主選擇及日期","專業核對","施工圖發行"])
    assert report["protected_controls_unchanged"]==149 and not report["primary_abc_or_3d_changed"]


def test_private_cli_recalculation_keeps_source_and_existing_results_and_public_template(tmp_path,monkeypatch,report):
    private=tmp_path/"inputs/private"
    private.mkdir(parents=True)
    d=synthetic(report)
    by_group(d,"local-drop").update(local_values())
    source=private/"input.json"
    source.write_text(json.dumps(d),encoding="utf-8")
    source_before=source.read_bytes()
    expected=build(ROOT,d)
    monkeypatch.setattr(exporter,"ROOT",tmp_path)
    monkeypatch.setattr(exporter,"build",lambda root,document:expected)
    assert exporter.main(["--conditions","inputs/private/input.json","--output","inputs/private/result-001"])==0
    output=private/"result-001/review.json"
    saved=output.read_bytes()
    assert json.loads(saved)["condition_values_received"]==10
    assert exporter.main(["--conditions","inputs/private/input.json","--output","inputs/private/result-001"])==1
    assert output.read_bytes()==saved and source.read_bytes()==source_before
    assert not (tmp_path/OUT).exists()


def test_private_cli_rejects_public_output_without_evaluating_input(monkeypatch,tmp_path):
    monkeypatch.setattr(exporter,"ROOT",tmp_path)
    monkeypatch.setattr(exporter,"build",lambda *a:pytest.fail("Must not compute public input"))
    assert exporter.main(["--conditions","README.md","--output","structured/result"])==1


def test_original_interface_revision_and_controls_are_not_changed(report):
    hashes=report["config"]["pinned_sources"]
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==v for n,v in hashes.items())
    assert len(GROUPS)==4
    assert CONFIG=="inputs/b-front-drop-conditions.json"

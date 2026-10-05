from __future__ import annotations

import copy
import json

import pytest

from house_design.architect_handoff import PREDECESSOR_FILES, create_handoff_package
from house_design.brief import build_design_brief, design_brief_html, design_brief_markdown
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, write_json
from house_design.meeting_pack import build_meeting_pack, meeting_pack_html, meeting_pack_markdown
from house_design.planning import (
    TOPICS,
    build_risk_review,
    risk_html,
    risk_markdown,
    write_risk_review,
)
from house_design.planning_catalog import initial_register
from house_design.review import _report_hash_payload, build_review, write_review
from house_design.revision_integrity import revision_manifest_content_hash

PROOF = {
    "verified_by": "synthetic reviewer",
    "verified_at": "2026-10-02",
    "reference": "TEST ONLY / decision and acceptance record",
}


def bundle(tmp_path):
    p, r = read_json(ROOT / "inputs/project.json"), read_json(ROOT / "inputs/requirements.json")
    r["requirements"] = r["requirements"][:1]
    r["requirements"][0]["relationships"] = []
    g = initial_register(p, r)
    paths = {
        "project_path": tmp_path / "project.json",
        "requirements_path": tmp_path / "requirements.json",
        "register_path": tmp_path / "register.json",
        "rules_path": tmp_path / "rules.json",
        "physical_items_path": tmp_path / "physical.json",
    }
    for key, data in (
        ("project_path", p),
        ("requirements_path", r),
        ("register_path", g),
        ("rules_path", read_json(ROOT / "rules/predesign_readiness_rules.json")),
        ("physical_items_path", read_json(ROOT / "inputs/physical-items.json")),
    ):
        write_json(paths[key], data)
    return paths, p, r, g


def confirm(g, report, ids=None):
    contexts = {i["id"]: i["context_hash"] for i in report["items"]}
    for i in g["items"]:
        if ids is None or i["id"] in ids:
            i["status"] = "verified"
            i["evidence"] = [{**PROOF, "context_hash": contexts[i["id"]]}]


def test_current_register_all_topics_and_requirements_no_auto_decisions():
    before = sha256_file(ROOT / "inputs/requirements.json")
    report = build_risk_review()
    assert report["summary"]["tracked_requirements"] == report["summary"]["total_requirements"] == 66
    assert set(TOPICS) == {i["topic"] for i in report["items"]}
    assert report["summary"]["total_items"] == 105
    assert report["summary"]["due_completed"] == 0
    assert not report["readiness"]["eligible_for_decision_freeze"]
    assert sha256_file(ROOT / "inputs/requirements.json") == before


def test_missing_register_never_passes(tmp_path):
    paths, _, _, _ = bundle(tmp_path)
    paths["register_path"] = tmp_path / "missing.json"
    report = build_risk_review(**paths)
    assert {g["code"] for g in report["gaps"]} >= {"MISSING_REGISTER", "UNTRACKED_REQUIREMENT", "MISSING_TOPIC"}
    assert not report["readiness"]["eligible_for_decision_freeze"]


@pytest.mark.parametrize("case", ["duplicate", "cycle", "schema", "bad_array", "project"])
def test_bad_register_rejected(tmp_path, case):
    paths, _, _, g = bundle(tmp_path)
    if case == "duplicate":
        g["items"].append(copy.deepcopy(g["items"][0]))
    elif case == "cycle":
        g["items"][0]["dependencies"] = [g["items"][1]["id"]]
        g["items"][1]["dependencies"] = [g["items"][0]["id"]]
    elif case == "schema":
        g["schema"] = "other"
    elif case == "bad_array":
        g["items"][0]["check_ids"] = "check"
    else:
        g["project_id"] = "other"
    write_json(paths["register_path"], g)
    with pytest.raises(ContractError):
        build_risk_review(**paths)


def test_no_role_acceptance_and_failed_refs_are_visible(tmp_path):
    paths, _, _, g = bundle(tmp_path)
    i = g["items"][0]
    i["responsible_role"] = None
    i["evidence_required"] = ""
    i["requirement_ids"] = ["gone-req"]
    i["rule_ids"] = ["gone-rule"]
    i["dependencies"] = ["gone-decision"]
    write_json(paths["register_path"], g)
    report = build_risk_review(**paths)
    gaps = " ".join(x["message"] for x in report["gaps"])
    for text in ("缺責任角色", "缺驗收", "gone-req", "gone-rule", "gone-decision"):
        assert text in gaps


def test_coverage_removed_requirement_and_topic(tmp_path):
    paths, _, _, g = bundle(tmp_path)
    g["items"] = [i for i in g["items"] if i["topic"] != "parking" and not i["requirement_ids"]]
    write_json(paths["register_path"], g)
    report = build_risk_review(**paths)
    assert report["summary"]["tracked_requirements"] == 0
    assert any(x["code"] == "MISSING_TOPIC" and x["id"] == "parking" for x in report["gaps"])


def test_verified_without_current_evidence_unknown_not_complete(tmp_path):
    paths, _, _, g = bundle(tmp_path)
    i = g["items"][0]
    i["status"] = "verified"
    i["evidence"] = [PROOF]
    write_json(paths["register_path"], g)
    item = next(i for i in build_risk_review(**paths)["items"] if i["id"] == g["items"][0]["id"])
    assert item["status"] == "needs_review"


def test_phase_readiness_no_future_blockers_and_changed_question_invalidates(tmp_path):
    paths, _, _, g = bundle(tmp_path)
    report = build_risk_review(**paths)
    due = report["readiness"]["due_open_ids"]
    confirm(g, report, due)
    write_json(paths["register_path"], g)
    ready = build_risk_review(**paths)
    assert ready["readiness"]["eligible_for_decision_freeze"]
    assert ready["summary"]["due_completed"] == len(due)
    assert any(i["status"] == "unknown" for i in ready["items"] if not i["due"])
    g["items"][0]["question"] += " changed"
    write_json(paths["register_path"], g)
    assert not build_risk_review(**paths)["readiness"]["eligible_for_decision_freeze"]


def test_candidate_requirement_cannot_be_verified(tmp_path):
    paths, _, _, g = bundle(tmp_path)
    g["items"][-1]["dependencies"] = []
    write_json(paths["register_path"], g)
    report = build_risk_review(**paths)
    confirm(g, report, [g["items"][-1]["id"]])
    write_json(paths["register_path"], g)
    assert (
        next(i for i in build_risk_review(**paths)["items"] if i["id"].startswith("SPACE-"))["status"] == "needs_review"
    )


def test_dependency_prevents_completion_and_na_needs_reason(tmp_path):
    paths, _, _, g = bundle(tmp_path)
    g["items"][1]["dependencies"] = [g["items"][0]["id"]]
    write_json(paths["register_path"], g)
    report = build_risk_review(**paths)
    confirm(g, report, [g["items"][1]["id"]])
    write_json(paths["register_path"], g)
    item = next(i for i in build_risk_review(**paths)["items"] if i["id"] == g["items"][1]["id"])
    assert item["status"] == "needs_review" and item["pending_dependencies"]
    g["items"][1]["status"] = "not_applicable"
    write_json(paths["register_path"], g)
    assert any("不適用缺理由" in v for i in build_risk_review(**paths)["items"] for v in i["gaps"])


def test_physical_measurement_changes_invalidate_proof(tmp_path):
    paths, _, _, g = bundle(tmp_path)
    next(i for i in g["items"] if i["id"] == "PLAN-STORAGE-01")["requires_transport_measurement"] = False
    write_json(paths["register_path"], g)
    report = build_risk_review(**paths)
    oid = "PLAN-STORAGE-01"
    confirm(g, report, [oid])
    write_json(paths["register_path"], g)
    assert next(i for i in build_risk_review(**paths)["items"] if i["id"] == oid)["status"] == "verified"
    p = read_json(paths["physical_items_path"])
    p["items"][0]["measurements"].append({"width_mm": 2000, "depth_mm": 3000, "height_mm": 2500})
    write_json(paths["physical_items_path"], p)
    assert next(i for i in build_risk_review(**paths)["items"] if i["id"] == oid)["status"] == "needs_review"


def test_palanquin_claim_without_measured_transport_stays_unresolved(tmp_path):
    paths, _, _, g = bundle(tmp_path)
    report = build_risk_review(**paths)
    confirm(g, report, ["PLAN-STORAGE-01"])
    write_json(paths["register_path"], g)
    item = next(i for i in build_risk_review(**paths)["items"] if i["id"] == "PLAN-STORAGE-01")
    assert item["status"] == "needs_review"
    assert any("搬運外廓" in gap for gap in item["gaps"])
    physical = read_json(paths["physical_items_path"])
    physical["items"][0]["transport"].update(
        measurement_state="measured",
        evidence=PROOF,
        assembled_dimensions={"width_mm": 1600, "depth_mm": 2300, "height_mm": 2200},
    )
    write_json(paths["physical_items_path"], physical)
    # Measuring changes the context; old approval cannot become valid on its own.
    assert (
        next(i for i in build_risk_review(**paths)["items"] if i["id"] == "PLAN-STORAGE-01")["status"] == "needs_review"
    )
    confirm(g, build_risk_review(**paths), ["PLAN-STORAGE-01"])
    write_json(paths["register_path"], g)
    assert next(i for i in build_risk_review(**paths)["items"] if i["id"] == "PLAN-STORAGE-01")["status"] == "verified"


@pytest.mark.parametrize("date", ["待填", "not-a-date", ""])
def test_placeholder_proof_is_not_a_verified_decision(tmp_path, date):
    paths, _, _, g = bundle(tmp_path)
    report = build_risk_review(**paths)
    confirm(g, report, ["PLAN-HOUSEHOLD-01"])
    g["items"][0]["evidence"][0]["verified_at"] = date
    write_json(paths["register_path"], g)
    assert (
        next(i for i in build_risk_review(**paths)["items"] if i["id"] == "PLAN-HOUSEHOLD-01")["status"]
        == "needs_review"
    )


def test_removed_item_not_resolved_previous_tampering_rejected(tmp_path):
    paths, _, _, g = bundle(tmp_path)
    report = build_risk_review(**paths)
    prev = tmp_path / "previous.json"
    write_json(prev, report)
    gone = g["items"].pop(3)["id"]
    write_json(paths["register_path"], g)
    result = build_risk_review(**paths, previous_report_path=prev)
    assert {"id": gone, "state": "removed_needs_review"} in result["changes"]
    assert not result["readiness"]["eligible_for_decision_freeze"]
    report["summary"]["total_items"] = 1
    write_json(prev, report)
    with pytest.raises(ContractError, match="hash"):
        build_risk_review(**paths, previous_report_path=prev)


def test_public_outputs_ignore_private_unknown_fields_and_escape(tmp_path):
    paths, _, _, g = bundle(tmp_path)
    g["private_notes"] = "PRIVATE HEALTH AND FINANCES"
    g["items"][0]["private_health"] = "PRIVATE HEALTH AND FINANCES"
    g["items"][0]["title"] = "<script>alert('test')</script>"
    write_json(paths["register_path"], g)
    report = build_risk_review(**paths)
    outputs = json.dumps(report, ensure_ascii=False) + risk_html(report) + risk_markdown(report)
    assert "PRIVATE HEALTH AND FINANCES" not in outputs
    assert "&lt;script&gt;" in risk_html(report)
    assert "<script>alert" not in risk_html(report)
    files = write_risk_review(report, tmp_path / "out")
    assert all(p.is_file() for p in files.values())


def test_brief_and_packet_same_questions_stale_packet_disabled(tmp_path):
    paths, _, _, _ = bundle(tmp_path)
    report = build_risk_review(**paths)
    out = tmp_path / "out"
    write_risk_review(report, out)
    brief = build_design_brief(
        project_path=paths["project_path"],
        requirements_path=paths["requirements_path"],
        physical_items_path=paths["physical_items_path"],
        household_profile_path=tmp_path / "private.json",
        planning_register_path=paths["register_path"],
        planning_rules_path=paths["rules_path"],
    )
    assert "risk-review.html" in design_brief_html(brief)
    assert "risk-review.html" in design_brief_markdown(brief)
    packet_args = {
        "project_path": paths["project_path"],
        "requirements_path": paths["requirements_path"],
        "planning_register_path": paths["register_path"],
        "planning_rules_path": paths["rules_path"],
        "physical_items_path": paths["physical_items_path"],
        "predesign_root": out,
        "predesign_path": tmp_path / "missing-predesign.json",
        "handoff_root": tmp_path / "missing-handoff",
    }
    pack = build_meeting_pack(**packet_args)
    planning = next(s for s in pack["sections"] if s["id"] == "planning")
    assert planning["available"]
    assert planning["open_decisions"] == brief["planning"]["open_decisions"]
    assert "risk-review.html" in meeting_pack_html(pack) and "risk-review.html" in meeting_pack_markdown(pack)
    g = read_json(paths["register_path"])
    g["items"][0]["question"] += " new"
    write_json(paths["register_path"], g)
    stale = next(s for s in build_meeting_pack(**packet_args)["sections"] if s["id"] == "planning")
    assert not stale["available"]


def test_formal_review_links_planning_no_signoff_inherited(tmp_path):
    paths, _, _, _ = bundle(tmp_path)
    revision_root = tmp_path / "revisions"
    directory = revision_root / "TEST-RISK"
    model = {
        "schema": "house-normalized-model-v1",
        "revision_id": "TEST-RISK",
        "entities": {"spaces": [], "storeys": []},
    }
    model_path = directory / "model.json"
    write_json(model_path, model)
    manifest = {
        "schema": "house-drawing-revision-v1",
        "revision_id": "TEST-RISK",
        "status": "ready",
        "normalized_model": str(model_path),
        "normalized_model_sha256": sha256_file(model_path),
        "sources": [],
        "mapping": None,
        "issues": [],
    }
    manifest["content_hash"] = revision_manifest_content_hash(manifest)
    write_json(directory / "manifest.json", manifest)
    args = {
        "revision_id": "TEST-RISK",
        "project_path": paths["project_path"],
        "requirements_path": paths["requirements_path"],
        "revision_root": revision_root,
        "planning_register_path": paths["register_path"],
        "predesign_rule_pack_path": paths["rules_path"],
    }
    report = build_review(**args)
    assert not report["release"]["eligible"]
    assert report["signoff"]["valid"] is False
    other = copy.deepcopy(report)
    other["planning"]["generated_at"] = "different"
    assert stable_hash(_report_hash_payload(other)) == stable_hash(_report_hash_payload(report))
    out = write_review(report, output_root=tmp_path / "reviews")
    assert (out / "risk-review.html").exists()
    assert "risk-review.html" in (out / "report.md").read_text()


def test_check_pass_cannot_complete_outage_scenario_and_tamper_is_unknown(tmp_path):
    paths, _, _, g = bundle(tmp_path)
    g["items"][0]["check_ids"] = ["route"]
    write_json(paths["register_path"], g)
    # Even a fabricated pass cannot serve as geometric evidence without a sealed revision.
    drawing = {
        "schema": "house-review-report-v1",
        "project": {"project_id": g["project_id"]},
        "revision": {"revision_id": "missing", "content_hash": "not-sealed"},
        "coordination": {"findings": [{"check_id": "route", "status": "pass"}]},
        "model": {},
    }
    drawing["report_hash"] = stable_hash(_report_hash_payload(drawing))
    path = tmp_path / "drawing.json"
    write_json(path, drawing)
    report = build_risk_review(**paths, drawing_report_path=path, revision_root=tmp_path / "revisions")
    item = next(i for i in report["items"] if i["id"] == g["items"][0]["id"])
    assert item["check_results"] == [{"check_id": "route", "status": "unknown"}]
    assert item["status"] == "unknown"
    assert any(i["topic"] == "outage" and i["status"] == "unknown" for i in report["items"])
    drawing["coordination"]["findings"][0]["status"] = "fail"
    write_json(path, drawing)
    assert build_risk_review(**paths, drawing_report_path=path)["inputs"]["drawing_report"] is None


def test_trusted_formal_check_snapshot_still_requires_scenario_approval(tmp_path):
    paths, _, _, g = bundle(tmp_path)
    revision_root = tmp_path / "revisions"
    directory = revision_root / "SYNTHETIC-R1"
    model_path = directory / "model.json"
    model = {
        "schema": "house-normalized-model-v1",
        "revision_id": "SYNTHETIC-R1",
        "entities": {"spaces": [], "storeys": []},
    }
    write_json(model_path, model)
    manifest = {
        "schema": "house-drawing-revision-v1",
        "revision_id": "SYNTHETIC-R1",
        "status": "ready",
        "normalized_model": str(model_path),
        "normalized_model_sha256": sha256_file(model_path),
        "sources": [],
        "mapping": None,
        "issues": [],
    }
    manifest["content_hash"] = revision_manifest_content_hash(manifest)
    write_json(directory / "manifest.json", manifest)
    overlay_path = tmp_path / "overlay.json"
    write_json(
        overlay_path,
        {
            "schema": "house-coordination-overlay-v1",
            "revision_id": "SYNTHETIC-R1",
            "revision_hash": manifest["content_hash"],
            "objects": [],
            "coverage": [],
            "checks": [
                {
                    "id": "synthetic-metric",
                    "kind": "numeric",
                    "domain": "space_program",
                    "actual": 1,
                    "threshold": 0,
                    "unit": "TEST ONLY",
                    "operator": "min",
                    "evidence": PROOF,
                }
            ],
        },
    )
    review = build_review(
        revision_id="SYNTHETIC-R1",
        revision_root=revision_root,
        project_path=paths["project_path"],
        requirements_path=paths["requirements_path"],
        coordination_path=overlay_path,
    )
    review_path = tmp_path / "review.json"
    write_json(review_path, review)
    g["items"][0]["check_ids"] = ["synthetic-metric"]
    write_json(paths["register_path"], g)
    args = {**paths, "drawing_report_path": review_path, "revision_root": revision_root}
    result = build_risk_review(**args)
    item = next(i for i in result["items"] if i["id"] == "PLAN-HOUSEHOLD-01")
    assert item["check_results"] == [{"check_id": "synthetic-metric", "status": "pass"}]
    assert item["status"] == "unknown"  # metric pass does not certify the whole scenario
    confirm(g, result, ["PLAN-HOUSEHOLD-01"])
    write_json(paths["register_path"], g)
    assert next(i for i in build_risk_review(**args)["items"] if i["id"] == "PLAN-HOUSEHOLD-01")["status"] == "verified"
    # A source/model change without a new revision fails immutable evidence validation.
    model["changed_without_new_revision"] = True
    write_json(model_path, model)
    changed = next(i for i in build_risk_review(**args)["items"] if i["id"] == "PLAN-HOUSEHOLD-01")
    assert changed["status"] == "needs_review"
    assert changed["check_results"][0]["status"] == "unknown"


def test_handoff_seals_same_risk_report_and_rejects_missing_or_tampered_before_writes(tmp_path):
    paths, _, _, _ = bundle(tmp_path)
    predecessor = tmp_path / "legacy"
    predecessor.mkdir()
    for name in PREDECESSOR_FILES:
        (predecessor / name).write_text("<!doctype html><title>SYNTHETIC HISTORICAL REFERENCE</title>")
    brief = build_design_brief(
        project_path=paths["project_path"],
        requirements_path=paths["requirements_path"],
        physical_items_path=paths["physical_items_path"],
        household_profile_path=tmp_path / "no-private.json",
        planning_register_path=paths["register_path"],
        planning_rules_path=paths["rules_path"],
    )
    brief_path = tmp_path / "design-brief.json"
    write_json(brief_path, brief)
    args = {
        "project_path": paths["project_path"],
        "requirements_path": paths["requirements_path"],
        "brief_path": brief_path,
        "predecessor_root": predecessor,
        "output_root": tmp_path / "handoff",
    }
    with pytest.raises(ContractError, match="Missing JSON"):
        create_handoff_package(**args)
    assert not (tmp_path / "handoff/R001").exists()
    report = build_risk_review(**paths)
    write_risk_review(report, tmp_path)
    create_handoff_package(**args)
    package = tmp_path / "handoff/R001"
    assert "risk-review.html" in (package / "design-brief.html").read_text()
    assert (package / "risk-review.html").is_file()
    manifest = read_json(package / "handoff-manifest.json")
    for kind in ("json", "html", "markdown"):
        snapshot = manifest["snapshots"][f"risk_review_{kind}"]
        assert sha256_file(package / snapshot["file"]) == snapshot["sha256"]
    report["items"][0]["question"] = "TAMPERED"
    write_json(tmp_path / "risk-review.json", report)
    with pytest.raises(ContractError, match="disagree"):
        create_handoff_package(**args, revision_id="R002")
    assert not (tmp_path / "handoff/R002").exists()

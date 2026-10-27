"""Small synthetic records only: no scene/browser/pipeline or existing seals."""

from __future__ import annotations

import copy

import pytest

from house_design.cli import build_parser
from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, write_json
from house_design.coordination import coordination_review
from house_design.drawing_evidence import build_drawing_evidence, check_scope_matches, validate_drawing_evidence
from house_design.planning import build_risk_review
from house_design.review import _report_hash_payload, build_review, write_review
from house_design.revision_integrity import revision_manifest_content_hash

PROOF = {"verified_by": "TEST ONLY reviewer", "verified_at": "2026-10-16", "reference": "TEST ONLY scenario record"}
RID = "TEST-R1"
REQ = "B.floor-1.fixture"
CHECK = "B-fixture-check"


def seal_revision(root, revision_id=RID):
    model_path = root / revision_id / "model.json"
    model = {
        "schema": "house-normalized-model-v1", "revision_id": revision_id,
        "entities": {"spaces": [], "storeys": []},
    }
    write_json(model_path, model)
    manifest = {
        "schema": "house-drawing-revision-v1", "revision_id": revision_id,
        "label": "SYNTHETIC ONLY", "status": "ready", "sources": [], "mapping": None, "issues": [],
        "normalized_model": str(model_path), "normalized_model_sha256": sha256_file(model_path),
    }
    manifest["content_hash"] = revision_manifest_content_hash(manifest)
    write_json(root / revision_id / "manifest.json", manifest)
    return manifest, model


@pytest.fixture
def case(tmp_path):
    project = read_json(ROOT / "inputs/project.json")
    project.update(project_id="TEST ONLY isolated project", name="TEST ONLY project")
    requirements = {
        "schema": "house-requirements-v2",
        "requirements": [{
            "id": REQ, "title": "TEST ONLY B scenario", "category": "shrine",
            "applies_to": {"building_id": "B", "floor_id": "floor-1"},
            "status": "confirmed", "priority": "must", "constraints": {},
            "source": {"type": "owner_decision", "path": "TEST ONLY decision"},
        }],
    }
    register = {
        "schema": "house-planning-register-v1", "project_id": project["project_id"],
        "items": [{
            "id": "TEST-SCENARIO", "title": "TEST ONLY scenario", "topic": "storage",
            "scenario": "TEST ONLY operation", "question": "TEST ONLY question", "recommendation": "TEST ONLY proposal",
            "alternatives": ["TEST ONLY alternative and cost"], "building_ids": ["B"], "floor_id": "floor-1",
            "requirement_ids": [REQ], "rule_ids": [], "check_ids": [CHECK], "dependencies": [],
            "due_phase": "design", "status": "unknown", "basis": "professional_required", "urgency": "P1",
            "responsible_role": "TEST ONLY reviewer", "evidence_required": "TEST ONLY witnessed scenario",
            "evidence": [], "physical_item_id": "TEST-INVENTORY", "requires_transport_measurement": True,
        }],
    }
    physical = {"items": [{
        "id": "TEST-INVENTORY", "transport": {
            "measurement_state": "measured", "evidence": PROOF,
            "assembled_dimensions": {"width_mm": 1200, "depth_mm": 2200, "height_mm": 2100},
        },
    }]}
    paths = {key: tmp_path / name for key, name in (
        ("project_path", "project.json"), ("requirements_path", "requirements.json"),
        ("register_path", "register.json"), ("rules_path", "planning-rules.json"),
        ("physical_items_path", "physical-items.json"),
    )}
    for key, data in (
        ("project_path", project), ("requirements_path", requirements), ("register_path", register),
        ("rules_path", {"rules": []}), ("physical_items_path", physical),
    ):
        write_json(paths[key], data)
    formal_rules = tmp_path / "formal-rules.json"
    write_json(formal_rules, {"schema": "house-rule-pack-v2", "rules": []})
    root = tmp_path / "custom-revisions"
    manifest, model = seal_revision(root)
    overlay = {
        "schema": "house-coordination-overlay-v1", "revision_id": RID, "revision_hash": manifest["content_hash"],
        "objects": [], "coverage": [],
        "checks": [{
            "id": CHECK, "kind": "numeric", "domain": "space_program", "requirement_id": REQ,
            "operator": "min", "actual": 10, "threshold": 5, "unit": "TEST ONLY", "evidence": PROOF,
        }],
    }
    overlay_path = tmp_path / "overlay.json"
    write_json(overlay_path, overlay)
    snapshot = build_drawing_evidence(
        project=project, requirements=requirements, manifest=manifest, model=model,
        coordination=coordination_review(model, overlay, manifest["content_hash"], requirements),
    )
    formal = {
        "revision_id": RID, "revision_root": root, "project_path": paths["project_path"],
        "requirements_path": paths["requirements_path"], "rule_pack_path": formal_rules,
        "predesign_rule_pack_path": paths["rules_path"], "planning_register_path": paths["register_path"],
        "coordination_path": overlay_path, "private_budget_path": None,
    }
    return {
        "paths": paths, "formal": formal, "project": project, "requirements": requirements,
        "register": register, "physical": physical, "root": root, "manifest": manifest,
        "model": model, "overlay": overlay, "snapshot": snapshot,
    }


def risk(case, **kwargs):
    return build_risk_review(**case["paths"], revision_root=case["root"], **kwargs)


def approve(case, result):
    item = case["register"]["items"][0]
    item.update(status="verified", evidence=[{**PROOF, "context_hash": result["items"][0]["context_hash"]}])
    write_json(case["paths"]["register_path"], case["register"])


def reseal(snapshot):
    snapshot["evidence_hash"] = stable_hash({k: v for k, v in snapshot.items() if k != "evidence_hash"})


def test_formal_review_now_passes_exact_revision_overlay_and_sibling_inventory(case, tmp_path):
    result = build_review(**case["formal"])
    planning = result["planning"]
    assert planning["drawing_evidence"]["verified"]
    assert planning["inputs"]["physical_items"] == stable_hash(case["physical"])
    assert planning["items"][0]["check_results"] == [{"check_id": CHECK, "status": "pass"}]
    assert planning["items"][0]["status"] == "unknown"  # Metric never certifies the whole operation.
    assert not result["signoff"]["valid"] and not result["release"]["eligible"]
    approve(case, planning)
    approved = build_review(**case["formal"])
    assert approved["planning"]["items"][0]["status"] == "verified"
    assert approved["drawing_evidence"] == result["drawing_evidence"]  # Independent of planning.
    assert not approved["release"]["eligible"]
    again = build_review(**case["formal"])
    assert again["report_hash"] == approved["report_hash"]
    assert again["planning"]["report_hash"] == approved["planning"]["report_hash"]
    directory = write_review(approved, output_root=tmp_path / "output")
    stored = read_json(directory / "drawing-evidence.json")
    assert stored == result["drawing_evidence"]
    assert set(stored) == {
        "schema", "project_id", "project_hash", "requirements_hash", "revision", "model_hash", "coordination", "evidence_hash",
    }
    for filename in ("report.json", "drawing-evidence.json"):
        loaded = risk(case, drawing_report_path=directory / filename, expected_revision_id=RID)
        assert loaded["items"][0]["context_hash"] == approved["planning"]["items"][0]["context_hash"]
        assert loaded["items"][0]["status"] == "verified"
        assert loaded["report_hash"] == approved["planning"]["report_hash"]


def test_no_automatic_promotion_even_if_status_verified_without_named_scenario_proof(case):
    case["register"]["items"][0]["status"] = "verified"
    write_json(case["paths"]["register_path"], case["register"])
    result = risk(case, drawing_snapshot=case["snapshot"])
    item = result["items"][0]
    assert item["status"] == "needs_review"
    assert item["check_results"][0]["status"] == "pass"
    assert any("具名" in message for message in item["gaps"])


@pytest.mark.parametrize("mutation", [
    "project_id", "project_hash", "requirements_hash", "model_hash", "revision_id", "revision_hash",
    "findings", "overlay_hash", "check_scope", "missing_overlay", "extra_release", "bad_schema", "invalid_type",
])
def test_self_rehashed_but_stale_foreign_or_fabricated_snapshot_stays_unknown(case, mutation):
    snapshot = copy.deepcopy(case["snapshot"])
    if mutation in {"project_id", "project_hash", "requirements_hash", "model_hash"}:
        snapshot[mutation] = "foreign"
    elif mutation == "revision_id":
        snapshot["revision"]["revision_id"] = "not-a-present-revision"
    elif mutation == "revision_hash":
        snapshot["revision"]["content_hash"] = "foreign"
    elif mutation == "findings":
        snapshot["coordination"]["findings"][0]["measurements"]["actual"] = 999
    elif mutation == "overlay_hash":
        snapshot["coordination"]["overlay_hash"] = "foreign"
    elif mutation == "check_scope":
        snapshot["coordination"]["findings"][0]["applies_to"]["building_id"] = "A"
    elif mutation == "missing_overlay":
        snapshot["coordination"].pop("overlay")
    elif mutation == "extra_release":
        snapshot["release"] = {"eligible": True}
    elif mutation == "bad_schema":
        snapshot["schema"] = "other"
    else:
        snapshot["coordination"] = []
    reseal(snapshot)  # Self-hash consistency is deliberately NOT enough.
    result = risk(case, drawing_snapshot=snapshot)
    assert not result["drawing_evidence"]["verified"]
    assert result["inputs"]["drawing_evidence"] is None
    assert result["items"][0]["check_results"][0]["status"] == "unknown"


def test_missing_check_and_failed_check_remain_visible(case):
    case["register"]["items"][0]["check_ids"].append("never-existed")
    write_json(case["paths"]["register_path"], case["register"])
    result = risk(case, drawing_snapshot=case["snapshot"])
    assert result["items"][0]["check_results"][-1] == {"check_id": "never-existed", "status": "unknown"}
    case["overlay"]["checks"][0]["actual"] = 1
    write_json(case["formal"]["coordination_path"], case["overlay"])
    result = build_review(**case["formal"])
    assert result["planning"]["items"][0]["check_results"][0]["status"] == "fail"


def test_even_resealed_overlay_cannot_turn_a_real_failure_into_pass(case):
    snapshot = copy.deepcopy(case["snapshot"])
    snapshot["coordination"]["overlay"]["checks"][0]["actual"] = 1
    snapshot["coordination"]["overlay_hash"] = stable_hash(snapshot["coordination"]["overlay"])
    reseal(snapshot)
    assert not risk(case, drawing_snapshot=snapshot)["drawing_evidence"]["verified"]


def test_changed_project_or_requirement_requires_fresh_drawing_evidence(case):
    changed = copy.deepcopy(case["project"])
    changed["name"] += " new"
    write_json(case["paths"]["project_path"], changed)
    assert not risk(case, drawing_snapshot=case["snapshot"])["drawing_evidence"]["verified"]
    write_json(case["paths"]["project_path"], case["project"])
    case["requirements"]["requirements"][0]["status"] = "candidate"
    write_json(case["paths"]["requirements_path"], case["requirements"])
    assert not risk(case, drawing_snapshot=case["snapshot"])["drawing_evidence"]["verified"]
    current = build_review(**case["formal"])
    assert current["planning"]["items"][0]["check_results"][0]["status"] == "warning"


def test_old_revision_is_not_current_just_because_old_files_are_still_valid(case):
    old = case["snapshot"]
    assert risk(case, drawing_snapshot=old, expected_revision_id=RID)["drawing_evidence"]["verified"]
    seal_revision(case["root"], "TEST-R2")
    result = risk(case, drawing_snapshot=old, expected_revision_id="TEST-R2")
    assert result["items"][0]["check_results"][0]["status"] == "unknown"
    assert not result["drawing_evidence"]["verified"]
    # Explicitly selecting R1 without claiming it is R2 is still a valid comparison.
    assert risk(case, drawing_snapshot=old)["drawing_evidence"]["revision_id"] == RID


def test_model_change_without_new_revision_invalidates_previously_approved_scenario(case):
    first = risk(case, drawing_snapshot=case["snapshot"])
    approve(case, first)
    model_path = case["root"] / RID / "model.json"
    write_json(model_path, {**case["model"], "changed_without_new_revision": True})
    result = risk(case, drawing_snapshot=case["snapshot"])
    assert not result["drawing_evidence"]["verified"]
    assert result["items"][0]["status"] == "needs_review"
    assert result["items"][0]["check_results"][0]["status"] == "unknown"


@pytest.mark.parametrize("change", ["missing", "estimated", "dimensions"])
def test_formal_review_uses_selected_physical_inventory_and_invalidates_context(case, tmp_path, change):
    first = build_review(**case["formal"])
    approve(case, first["planning"])
    alternate = copy.deepcopy(case["physical"])
    if change == "missing":
        alternate["items"] = []
    elif change == "estimated":
        alternate["items"][0]["transport"]["measurement_state"] = "estimated"
    else:
        alternate["items"][0]["transport"]["assembled_dimensions"]["width_mm"] += 50
    selected = tmp_path / "selected-inventory.json"
    write_json(selected, alternate)
    result = build_review(**case["formal"], physical_items_path=selected)
    assert result["planning"]["inputs"]["physical_items"] == stable_hash(alternate)
    assert result["planning"]["items"][0]["status"] == "needs_review"
    assert result["drawing_evidence"] == first["drawing_evidence"]
    if change == "missing":
        assert "實物清冊引用失效" in result["planning"]["items"][0]["gaps"]


def test_missing_sibling_inventory_does_not_fall_back_to_canonical_project(case):
    # Only the test fixture is removed; the real physical inventory is untouched.
    case["paths"]["physical_items_path"].unlink()
    result = build_review(**case["formal"])
    assert result["planning"]["inputs"]["physical_items"] == stable_hash({"items": []})
    assert "實物清冊引用失效" in result["planning"]["items"][0]["gaps"]


def test_standalone_api_also_defaults_to_sibling_inventory(case):
    paths = {k: v for k, v in case["paths"].items() if k != "physical_items_path"}
    result = build_risk_review(**paths, revision_root=case["root"], drawing_snapshot=case["snapshot"])
    assert result["inputs"]["physical_items"] == stable_hash(case["physical"])


def test_overlay_update_invalidates_human_proof_even_if_numeric_result_still_passes(case):
    first = build_review(**case["formal"])
    approve(case, first["planning"])
    case["overlay"]["checks"][0]["actual"] += 1
    write_json(case["formal"]["coordination_path"], case["overlay"])
    changed = build_review(**case["formal"])
    assert changed["planning"]["items"][0]["check_results"][0]["status"] == "pass"
    assert changed["planning"]["items"][0]["status"] == "needs_review"
    assert changed["drawing_evidence"]["evidence_hash"] != first["drawing_evidence"]["evidence_hash"]
    assert changed["planning"]["items"][0]["context_hash"] != first["planning"]["items"][0]["context_hash"]


def test_lost_overlay_evidence_remains_unknown_after_formal_rebuild(case):
    first = build_review(**case["formal"])
    approve(case, first["planning"])
    case["overlay"]["checks"][0]["evidence"] = {}
    write_json(case["formal"]["coordination_path"], case["overlay"])
    changed = build_review(**case["formal"])
    assert changed["planning"]["items"][0]["check_results"][0]["status"] == "unknown"
    assert changed["planning"]["items"][0]["status"] == "needs_review"


def test_consistent_self_hash_with_changed_scope_still_cannot_override_requirements(case):
    item = case["register"]["items"][0]
    check = {"applies_to": {"requirement_id": REQ, "building_id": "C", "floor_id": "floor-1"}}
    assert not check_scope_matches(item, check, case["requirements"])


def test_drawing_validation_does_not_modify_snapshot(case):
    snapshot = case["snapshot"]
    before = copy.deepcopy(snapshot)
    assert validate_drawing_evidence(
        snapshot, project=case["project"], requirements=case["requirements"], revision_root=case["root"],
    )
    assert snapshot == before


@pytest.mark.parametrize("scope", ["other_building", "other_floor", "other_requirement"])
def test_check_pass_cannot_be_borrowed_for_an_unrelated_scenario(case, scope):
    item = case["register"]["items"][0]
    if scope == "other_building":
        item["building_ids"] = ["C"]
    elif scope == "other_floor":
        item["floor_id"] = "floor-2"
    else:
        item["requirement_ids"] = ["B.floor-1.other"]
    write_json(case["paths"]["register_path"], case["register"])
    result = risk(case, drawing_snapshot=case["snapshot"])
    assert result["drawing_evidence"]["verified"]
    assert result["items"][0]["check_results"][0]["status"] == "unknown"
    assert any("範圍" in gap for gap in result["items"][0]["gaps"])


def test_bare_unscoped_numeric_result_does_not_satisfy_single_building_scenario(case):
    case["overlay"]["checks"][0].pop("requirement_id")
    write_json(case["formal"]["coordination_path"], case["overlay"])
    result = build_review(**case["formal"])
    assert result["coordination"]["findings"][0]["status"] == "pass"
    assert result["planning"]["items"][0]["check_results"][0]["status"] == "unknown"


def test_snapshot_no_signoff_inheritance_and_final_report_hash_is_not_context(case, tmp_path):
    formal = build_review(**case["formal"])
    snapshot = formal["drawing_evidence"]
    baseline = risk(case, drawing_snapshot=snapshot)
    formal["signoff"] = {"valid": True, "decision": "approved"}
    formal["release"] = {"eligible": True}
    formal["report_hash"] = stable_hash(_report_hash_payload(formal))
    path = tmp_path / "unrelated-release.json"
    write_json(path, formal)
    result = risk(case, drawing_report_path=path)
    assert result["report_hash"] == baseline["report_hash"]
    assert result["items"][0]["status"] == "unknown"
    assert "signoff" not in result and "release" not in result
    assert result["inputs"]["drawing_report"] == snapshot["evidence_hash"] != formal["report_hash"]


def test_old_final_report_without_snapshot_is_readable_but_cannot_rebind_old_results(case, tmp_path):
    formal = build_review(**case["formal"])
    formal.pop("drawing_evidence")
    formal["report_hash"] = stable_hash(_report_hash_payload(formal))
    path = tmp_path / "legacy.json"
    write_json(path, formal)
    result = risk(case, drawing_report_path=path)
    assert not result["drawing_evidence"]["verified"]
    assert result["items"][0]["check_results"][0]["status"] == "unknown"


def test_report_and_snapshot_cannot_disagree_even_with_recomputed_envelope_hash(case, tmp_path):
    formal = build_review(**case["formal"])
    formal["coordination"]["findings"][0]["status"] = "fail"
    formal["report_hash"] = stable_hash(_report_hash_payload(formal))
    path = tmp_path / "inconsistent.json"
    write_json(path, formal)
    assert not risk(case, drawing_report_path=path)["drawing_evidence"]["verified"]


def test_explicit_root_cannot_silently_use_another_revision_store(case, tmp_path):
    paths = case["paths"]
    result = build_risk_review(**paths, drawing_snapshot=case["snapshot"], revision_root=tmp_path / "empty-root")
    assert not result["drawing_evidence"]["verified"]


def test_snapshot_and_path_are_mutually_exclusive(case, tmp_path):
    with pytest.raises(ContractError, match="Choose one"):
        risk(case, drawing_snapshot=case["snapshot"], drawing_report_path=tmp_path / "not-read.json")


def test_unhashed_tampered_snapshot_and_report_remain_unknown(case, tmp_path):
    snapshot = copy.deepcopy(case["snapshot"])
    snapshot["coordination"]["findings"][0]["status"] = "fail"
    assert not risk(case, drawing_snapshot=snapshot)["drawing_evidence"]["verified"]
    formal = build_review(**case["formal"])
    formal["coordination"]["findings"][0]["status"] = "fail"
    path = tmp_path / "tampered.json"
    write_json(path, formal)
    assert not risk(case, drawing_report_path=path)["drawing_evidence"]["verified"]


def test_changed_manifest_seal_is_rejected_even_though_model_is_unchanged(case):
    path = case["root"] / RID / "manifest.json"
    changed = read_json(path)
    changed["label"] = "changed without new seal"
    write_json(path, changed)
    assert not risk(case, drawing_snapshot=case["snapshot"])["drawing_evidence"]["verified"]


def test_malformed_snapshot_is_unknown_not_an_exception(case):
    for value in ({}, [], {"schema": "house-drawing-evidence-v1"}, "not-a-snapshot"):
        assert not validate_drawing_evidence(
            value, project=case["project"], requirements=case["requirements"], revision_root=case["root"],
        )


def test_cli_exposes_explicit_revision_and_inventory_without_launching_work():
    parser = build_parser()
    args = parser.parse_args([
        "predesign", "risk-review", "--drawing-evidence", "snapshot.json", "--revision", "TEST-R2",
        "--revision-root", "custom-revisions",
    ])
    assert args.drawing_report == "snapshot.json" and args.revision == "TEST-R2"
    assert args.revision_root == "custom-revisions"
    formal = parser.parse_args(["review", "run", "--revision", RID, "--physical-items", "selected-inventory.json"])
    assert formal.physical_items == "selected-inventory.json"
    assert parser.parse_args(["predesign", "risk-review", "--project", "other/project.json"]).physical_items is None

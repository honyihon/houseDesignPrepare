from __future__ import annotations

import copy

import pytest

from house_design.contracts import ROOT, read_json, sha256_file, stable_hash, write_json
from house_design.intake import validate_project
from house_design.review import _project_findings, build_review
from house_design.revision_integrity import revision_manifest_content_hash
from house_design.site_evidence import PING_TO_SQM, assess_parcel_area


def parcel(identifier="A"):
    return {
        "id": identifier,
        "land_number": f"TEST ONLY 區／段／小段／{identifier}-001",
        "parcel_area_sqm": 100.0,
        "parcel_area_ping": 100.0 / PING_TO_SQM,
        "parcel_area_evidence": {
            "status": "verified",
            "parcel_id": identifier,
            "land_number": f"TEST ONLY 區／段／小段／{identifier}-001",
            "value": 100.0,
            "unit": "m2",
            "source": {"reference": "TEST ONLY cadastral record", "reviewer": "測試查核人", "checked_at": "2026-10-16"},
        },
    }


def test_matching_checked_sqm_area_passes_without_changing_scalars():
    value = parcel()
    before = stable_hash(value)
    result = assess_parcel_area(value)
    assert result["status"] == "pass"
    assert result["issues"] == []
    assert result["source"]["reference"] == "TEST ONLY cadastral record"
    assert stable_hash(value) == before


@pytest.mark.parametrize("unit", ["m2", "m²"])
def test_ping_is_optional_and_can_be_derived_for_display(unit):
    value = parcel()
    value.pop("parcel_area_ping")
    value["parcel_area_evidence"]["unit"] = unit
    result = assess_parcel_area(value)
    assert result["status"] == "pass"
    assert result["derived_area_ping"] == pytest.approx(100 / PING_TO_SQM)


@pytest.mark.parametrize("sqm", [None, 0, -100, True, False, "100", float("nan"), float("inf")])
def test_missing_or_nonfinite_sqm_never_passes_even_with_filled_evidence(sqm):
    value = parcel()
    value["parcel_area_sqm"] = sqm
    assert assess_parcel_area(value)["status"] == "unknown"


@pytest.mark.parametrize("ping", [0, -10, True, "30.25", float("nan"), float("inf")])
def test_invalid_optional_ping_never_passes(ping):
    value = parcel()
    value["parcel_area_ping"] = ping
    assert assess_parcel_area(value)["status"] == "unknown"


def test_inconsistent_sqm_and_ping_is_an_explicit_data_failure_not_buildability():
    value = parcel()
    value["parcel_area_ping"] = 32
    result = assess_parcel_area(value)
    assert result["status"] == "fail"
    assert "AREA_UNIT_MISMATCH" in {i["code"] for i in result["issues"]}
    value["parcel_area_sqm"] = 32 * PING_TO_SQM
    # Correcting the scalar without re-checking the old 100 m² proof is not enough.
    assert assess_parcel_area(value)["status"] == "unknown"


def test_small_rounding_difference_is_not_a_survey_accuracy_claim():
    value = parcel()
    value["parcel_area_sqm"] += 0.005
    assert assess_parcel_area(value)["status"] == "pass"


@pytest.mark.parametrize("field,bad", [
    ("status", "assumed"), ("status", "unknown"), ("status", "pending"),
    ("parcel_id", "B"), ("land_number", "different land"), ("land_number", None),
    ("value", 105), ("value", True), ("value", float("nan")), ("unit", "ping"), ("unit", None),
])
def test_stale_or_misbound_evidence_never_passes(field, bad):
    value = parcel()
    value["parcel_area_evidence"][field] = bad
    assert assess_parcel_area(value)["status"] == "unknown"


@pytest.mark.parametrize("source", [
    None, {}, "document.pdf", {"reference": "record"},
    {"reference": "unknown", "reviewer": "查核人", "checked_at": "2026-10-16"},
    {"reference": "record", "reviewer": "Codex", "checked_at": "2026-10-16"},
    {"reference": "record", "reviewer": "查核人", "checked_at": "not-a-date"},
    {"reference": "record", "reviewer": "查核人", "checked_at": "2026-02-30"},
])
def test_incomplete_placeholder_or_invalid_source_is_unknown(source):
    value = parcel()
    value["parcel_area_evidence"]["source"] = source
    result = assess_parcel_area(value)
    assert result["status"] == "unknown"
    assert any(i["code"].startswith("AREA_SOURCE_") for i in result["issues"])


def test_land_number_fact_must_itself_be_verified():
    value = parcel()
    value["land_number"] = {"status": "unknown", "value": value["land_number"]}
    assert assess_parcel_area(value)["status"] == "unknown"
    value["land_number"]["status"] = "verified"
    assert assess_parcel_area(value)["status"] == "pass"


@pytest.mark.parametrize("schema", ["house-project-v2", "house-project-v3"])
def test_formal_consumer_keeps_legacy_numbers_readable_but_requires_evidence(schema):
    project = read_json(ROOT / "inputs/project.json")
    project["schema"] = schema
    parcels = [parcel(i) for i in "ABC"]
    for value in parcels:
        value.pop("parcel_area_evidence")
    if schema == "house-project-v2":
        project["parcel_relationship"] = "adjacent_separate_parcels"
        project["parcels"] = parcels
    else:
        project["site_search"]["selected_site"] = {"parcels": parcels}
    assert validate_project(project) == []  # Additive proof, not a schema migration.
    before = copy.deepcopy(project)
    results = [f for f in _project_findings(project) if f["rule_id"] == "SITE-PARCEL-AREA"]
    assert len(results) == 3 and {f["status"] for f in results} == {"unknown"}
    assert all("AREA_SOURCE_MISSING" in {i["code"] for i in f["evidence"][0]["assessment"]["issues"]} for f in results)
    parcels[0]["parcel_area_evidence"] = parcel()["parcel_area_evidence"]
    assert next(f for f in _project_findings(project) if f["rule_id"] == "SITE-PARCEL-AREA")["status"] == "pass"
    assert before["schema"] == project["schema"]
    assert all(p["parcel_area_sqm"] == 100 for p in parcels)


def test_current_32_ping_target_is_still_not_selected_parcel_evidence():
    project = read_json(ROOT / "inputs/project.json")
    before = stable_hash(project)
    assert project["site_search"]["selected_site"] is None
    assert not any(f["rule_id"] == "SITE-PARCEL-AREA" for f in _project_findings(project))
    assert stable_hash(project) == before


def test_formal_report_keeps_valid_area_separate_from_buildability_and_missing_sources(tmp_path):
    project = read_json(ROOT / "inputs/project.json")
    parcels = [parcel(i) for i in "ABC"]
    parcels[1]["parcel_area_evidence"]["source"] = None
    parcels[2]["parcel_area_ping"] = 32  # Deliberately inconsistent with 100 m².
    project["site_search"]["selected_site"] = {"parcels": parcels}
    project_path = tmp_path / "project.json"
    write_json(project_path, project)
    model_path = tmp_path / "revisions/TEST-AREA/model.json"
    write_json(model_path, {
        "schema": "house-normalized-model-v1", "revision_id": "TEST-AREA", "entities": {"spaces": [], "storeys": []},
    })
    manifest = {
        "schema": "house-drawing-revision-v1", "revision_id": "TEST-AREA", "status": "ready",
        "normalized_model": str(model_path), "normalized_model_sha256": sha256_file(model_path),
        "sources": [], "mapping": None, "issues": [],
    }
    manifest["content_hash"] = revision_manifest_content_hash(manifest)
    write_json(model_path.parent / "manifest.json", manifest)
    before = sha256_file(project_path)
    result = build_review(revision_id="TEST-AREA", project_path=project_path, revision_root=tmp_path / "revisions")
    areas = {f["applies_to"]["parcel_id"]: f["status"] for f in result["findings"] if f["rule_id"] == "SITE-PARCEL-AREA"}
    assert areas == {"A": "pass", "B": "unknown", "C": "fail"}
    assert not result["release"]["eligible"]
    assert all(f["status"] != "pass" for f in result["findings"] if f["rule_id"] == "SITE-BUILDABLE-FOOTPRINT")
    assert sha256_file(project_path) == before

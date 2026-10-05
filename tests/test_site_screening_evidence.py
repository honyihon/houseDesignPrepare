from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from house_design.contracts import ROOT, ContractError, read_json, write_json
from house_design.envelope import build_envelope_scenario
from house_design.intake import is_known
from house_design.sites import _evaluate, build_site_comparison, validate_site_criteria


def fact(value):
    return {
        "status": "verified",
        "value": value,
        "source": {"reference": "fixture document", "reviewer": "fixture reviewer", "checked_at": "2026-10-05"},
    }


def criterion(identifier):
    value = next(c for c in read_json(ROOT / "inputs/site-criteria.json")["criteria"] if c["id"] == identifier)
    value["status"] = "set"
    value["threshold"]["value"] = "yes"
    return value


def candidate():
    return read_json(ROOT / "inputs/site-candidate.template.json")


@pytest.mark.parametrize(
    "value", [None, "", "unknown", " UNKNOWN ", "pending", "needs_confirmation", "assumed", "estimated", "unverified"]
)
def test_uninvestigated_strings_never_eliminate_a_candidate(value):
    c = candidate()
    c["constructability"]["truck_access"] = value
    assert not is_known(value)
    assert _evaluate(criterion("SC-CONSTRUCTION-ACCESS"), c)["state"] == "unknown"


@pytest.mark.parametrize(
    "source",
    [
        None,
        "",
        {},
        "agent says so",
        {"reference": "document"},
        {"reference": "document", "reviewer": "someone", "checked_at": "not-a-date"},
    ],
)
def test_verified_road_without_traceable_checked_source_is_unknown(source):
    c = candidate()
    c["official_facts"]["road"] = {**fact(8), "source": source}
    line = criterion("SC-ROAD-WIDTH")
    line["threshold"]["value"] = 6
    assert _evaluate(line, c)["state"] == "unknown"


def test_evidenced_road_can_pass_or_fail_but_unknown_status_wins():
    c = candidate()
    line = criterion("SC-ROAD-WIDTH")
    line["threshold"]["value"] = 6
    for width, expected in [(8, "pass"), (4, "eliminated")]:
        c["official_facts"]["road"] = fact(width)
        assert _evaluate(line, c)["state"] == expected
    c["official_facts"]["road"]["status"] = "unknown"
    assert _evaluate(line, c)["state"] == "unknown"
    c["official_facts"]["road"] = fact(8)
    line["status"] = "unknown"
    assert _evaluate(line, c)["state"] == "unknown"


def test_adjacency_does_not_prove_all_three_core_functions():
    c = candidate()
    c["target_fit"]["three_adjacent_parcels"] = fact("yes")
    line = criterion("SC-CORE-FUNCTIONS")
    assert _evaluate(line, c)["state"] == "unknown"
    c["core_function_assessment"]["A"] = fact("yes")
    c["core_function_assessment"]["B"] = fact("yes")
    assert _evaluate(line, c)["state"] == "unknown"
    c["core_function_assessment"]["C"] = fact("yes")
    assert _evaluate(line, c)["state"] == "pass"
    c["core_function_assessment"]["C"] = fact("no")
    assert _evaluate(line, c)["state"] == "eliminated"


def test_utilities_require_all_four_systems_rights_and_boundaries():
    c = candidate()
    c["utilities"]["sewer_and_stormwater"] = fact("yes")
    line = criterion("SC-CROSS-PARCEL-UTILITY")
    assert _evaluate(line, c)["state"] == "unknown"
    for system in c["cross_parcel_utilities"].values():
        for key in system:
            system[key] = fact("yes")
    assert _evaluate(line, c)["state"] == "pass"
    assert len(_evaluate(line, c)["components"]) == 12
    c["cross_parcel_utilities"]["telecom"]["route_rights"] = fact("unknown")
    assert _evaluate(line, c)["state"] == "unknown"
    c["cross_parcel_utilities"]["water"]["responsibility_boundary"] = fact("no")
    assert _evaluate(line, c)["state"] == "eliminated"


def test_budget_not_proven_by_decision_or_missing_cost_components():
    c = candidate()
    c["decision"]["status"] = "selected"
    line = criterion("SC-TOTAL-COST")
    assert _evaluate(line, c)["state"] == "unknown"
    c["budget_assessment"]["affordability"] = fact("yes")
    assert _evaluate(line, c)["state"] == "unknown"
    for path in line["all_fields"]:
        c["budget_assessment"][path.split(".")[-1]] = fact("yes")
    assert _evaluate(line, c)["state"] == "pass"
    c["decision"]["status"] = "pending"
    assert _evaluate(line, c)["state"] == "pass"


def test_frontage_is_checked_per_parcel_not_compound_total():
    c = candidate()
    c["target_fit"]["frontage_mm"] = fact(18000)
    line = criterion("SC-FRONTAGE-MIN")
    line["threshold"]["value"] = 5500
    assert _evaluate(line, c)["state"] == "unknown"
    for parcel in c["parcels"]:
        parcel["frontage_mm"] = fact(6000)
    assert _evaluate(line, c)["state"] == "pass"
    c["parcels"][2]["frontage_mm"] = fact(5000)
    assert _evaluate(line, c)["state"] == "eliminated"
    c["parcels"][2]["building_id"] = "A"
    assert _evaluate(line, c)["state"] == "unknown"


def project_with_candidate(tmp_path: Path):
    p = read_json(ROOT / "inputs/project.json")
    c = candidate()
    p["site_search"]["candidate_sites"] = [c]
    path = tmp_path / "project.json"
    write_json(path, p)
    return p, c, path


def test_site_report_remains_unknown_and_retains_checked_sources(tmp_path):
    p, c, path = project_with_candidate(tmp_path)
    line = criterion("SC-CORE-FUNCTIONS")
    for building in ("A", "B", "C"):
        c["core_function_assessment"][building] = fact("yes")
    write_json(path, p)
    criteria = read_json(ROOT / "inputs/site-criteria.json")
    criteria["criteria"] = [line, criterion("SC-CONSTRUCTION-ACCESS")]
    criteria_path = tmp_path / "criteria.json"
    write_json(criteria_path, criteria)
    assert validate_site_criteria(criteria) == []
    report = build_site_comparison(project_path=path, criteria_path=criteria_path)
    row = report["candidates"][0]
    assert row["verdict"] == "unknown"
    assert row["cells"][0]["fact_sources"]["core_function_assessment.A"]["reference"] == "fixture document"


def test_candidate_total_never_becomes_single_parcel_or_target_fallback(tmp_path):
    p, c, path = project_with_candidate(tmp_path)
    c["target_fit"]["total_area_sqm"] = fact(317.36)
    c["official_facts"]["building_coverage_ratio"] = fact(0.6)
    write_json(path, p)
    report = build_envelope_scenario(project_path=path, candidate_id=c["candidate_id"])
    assert report["inputs"]["parcel_area_sqm"] is None
    assert report["area"]["legal_footprint_sqm"] is None
    report = build_envelope_scenario(project_path=path, candidate_id=c["candidate_id"], parcel_id="PARCEL-A")
    assert report["area"]["legal_footprint_sqm"] is None
    c["parcels"][0]["area_sqm"] = fact(105.79)
    c["parcels"][1]["area_sqm"] = fact(120)
    write_json(path, p)
    a = build_envelope_scenario(project_path=path, candidate_id=c["candidate_id"], parcel_id="PARCEL-A")
    b = build_envelope_scenario(project_path=path, candidate_id=c["candidate_id"], parcel_id="PARCEL-B")
    assert a["area"]["legal_footprint_sqm"] == 63.47
    assert b["area"]["legal_footprint_sqm"] == 72
    assert all(check["building"] == "A" for check in a["core_function_checks"])
    assert "ENV-PALANQUIN-PATH" not in {check["id"] for check in a["core_function_checks"]}
    with pytest.raises(ContractError):
        build_envelope_scenario(project_path=path, candidate_id=c["candidate_id"], parcel_id="missing")


def test_explicit_assumptions_are_still_available_without_claiming_site_facts():
    report = build_envelope_scenario(bcr=0.6, frontage_mm=6000, depth_mm=18000, parcel_area_sqm=100)
    assert report["area"]["legal_footprint_sqm"] == 60
    assert "parcel_area_sqm" in report["inputs"]["assumed_fields"]
    assert report["scenario"] == "hypothetical"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"parcel_area_sqm": -1},
        {"frontage_mm": float("nan")},
        {"depth_mm": float("inf")},
        {"bcr": 60},
        {"bcr": True},
        {"storeys": 0},
    ],
)
def test_invalid_geometry_never_produces_capacity(kwargs):
    with pytest.raises(ContractError):
        build_envelope_scenario(**kwargs)


def test_storage_measurement_never_confirms_assembled_transport_or_rehearsal(tmp_path):
    payload = read_json(ROOT / "inputs/physical-items.json")
    item = payload["items"][0]
    item["measurements"] = [
        {
            "sequence": 1,
            "dimensions": deepcopy(item["planning_dimensions"]),
            "measured_at": "2026-10-05",
            "measured_by": "fixture",
            "method": "fixture tape measurement",
        }
    ]
    path = tmp_path / "physical.json"
    write_json(path, payload)

    def check():
        report = build_envelope_scenario(physical_items_path=path, frontage_mm=6000)
        return next(c for c in report["core_function_checks"] if c["id"] == "ENV-PALANQUIN-PATH")

    result = check()
    assert result["storage_measured"]
    assert not result["transport_measured"]
    assert "抬桿與轉彎需求未確認" in result["reason"]
    item["transport"]["assembled_dimensions"] = deepcopy(item["planning_dimensions"])
    write_json(path, payload)
    assert not check()["transport_measured"]
    item["transport"]["assembled_measurement"] = fact("yes")
    write_json(path, payload)
    result = check()
    assert result["transport_measured"]
    assert not result["route_rehearsed"]
    assert "實際路徑搬運演練" in result["reason"]
    item["transport"]["route_rehearsal"] = fact("yes")
    write_json(path, payload)
    assert check()["route_rehearsed"]

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from house_design.contracts import ROOT, ContractError, read_json, sha256_file, write_json
from house_design.coordination import SCHEMA, compare_coordination, coordination_html, coordination_review
from house_design.drawings import compare_models, revision_manifest_content_hash
from house_design.review import build_review, write_review

PROOF = {"verified_by": "Synthetic tester", "verified_at": "2026-10-01", "reference": "TEST ONLY / A-01"}


def rectangle(oid, x, y, w, h, floor="floor-1", **extra):
    return {
        "id": oid,
        "building_id": "B",
        "floor_id": floor,
        "polygon_mm": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        "geometry_method": "professional_verified_polygon",
        "evidence": PROOF,
        **extra,
    }


def model():
    return {
        "schema": "house-normalized-model-v1",
        "revision_id": "TEST-R1",
        "coordinate_system": {
            "status": "verified",
            "axis": "x/y",
            "verified_by": "tester",
            "verified_at": "2026-10-01",
            "method": "synthetic registration",
            "reference_points": [[0, 0], [5000, 0]],
        },
        "entities": {
            "storeys": [
                {"id": "level-1", "building_id": "B", "floor_id": "floor-1", "elevation_mm": 0},
                {"id": "level-2", "building_id": "B", "floor_id": "floor-2", "elevation_mm": 3000},
            ],
            "spaces": [rectangle("room", 0, 0, 5000, 5000, boundary_measurement="finished_clear")],
            "equipment": [],
            "doors": [],
            "windows": [],
        },
    }


def overlay(kind="collision", **extra):
    objects = [rectangle("altar", 500, 500, 1000, 1000), rectangle("cabinet", 1400, 500, 1000, 1000)]
    check = {
        "id": "B-shrine",
        "kind": kind,
        "domain": "space_program",
        "priority": "must",
        "subject_id": "altar",
        "target_ids": ["cabinet"],
        "evidence": PROOF,
        **extra,
    }
    return {
        "schema": SCHEMA,
        "revision_id": "TEST-R1",
        "revision_hash": "test-hash",
        "registration": PROOF,
        "objects": objects,
        "checks": [check],
        "coverage": [
            {
                "building_id": "B",
                "floor_id": "floor-1",
                "domain": check["domain"],
                "complete": True,
                "object_ids": ["room", "altar", "cabinet"],
                "check_ids": [check["id"]],
                "evidence": PROOF,
            }
        ],
    }


def run(o, m=None, req=None):
    return coordination_review(m or model(), o, "test-hash", req or {"requirements": []})


def status(o, m=None, req=None):
    return run(o, m, req)["findings"][0]["status"]


def test_narrow_collision_not_bbox_tolerance():
    o = overlay()
    assert status(o) == "fail"  # overlap only 100 mm
    o["objects"][1] = rectangle("cabinet", 1500, 500, 1000, 1000)
    assert status(o) == "pass"  # touching is not positive-area collision


def test_concave_containment_and_rotated_polygon():
    m = model()
    m["entities"]["spaces"][0]["polygon_mm"] = [[0, 0], [5000, 0], [5000, 1000], [1000, 1000], [1000, 5000], [0, 5000]]
    o = overlay("containment", target_ids=["room"])
    o["objects"][0]["polygon_mm"] = [[700, 700], [1400, 1000], [1100, 1700], [400, 1400]]
    assert status(o, m) == "fail"


@pytest.mark.parametrize("missing", ["polygon", "evidence", "coordinates", "registration", "hull"])
def test_missing_geometry_proof_never_passes(missing):
    o, m = overlay(), model()
    if missing == "polygon":
        o["objects"][0].pop("polygon_mm")
    elif missing == "evidence":
        o["checks"][0].pop("evidence")
    elif missing == "coordinates":
        m["coordinate_system"]["status"] = "unknown"
    elif missing == "registration":
        o.pop("registration")
    else:
        o["objects"][0]["geometry_method"] = "ifc_convex_hull"
    assert status(o, m) == "unknown"


def route_overlay(kind="route", **extra):
    return overlay(
        kind,
        subject_id="room",
        target_ids=[],
        obstacle_ids=["altar", "cabinet"],
        path_mm=[[1000, 3000], [4000, 3000]],
        width_mm=900,
        **extra,
    )


def test_route_and_completeness():
    o = route_overlay()
    assert status(o) == "pass"
    o["checks"][0]["path_mm"] = [[1000, 1000], [4000, 1000]]
    assert status(o) == "fail"
    o["coverage"] = []
    assert status(o) == "unknown"


def test_omitted_obstacle_and_coverage_ids():
    o = route_overlay()
    o["objects"].append(rectangle("hidden-cabinet", 2500, 2500, 500, 500))
    assert status(o) == "unknown"
    o["coverage"][0]["object_ids"].append("hidden-cabinet")
    assert status(o) == "unknown"  # coverage declaration alone cannot omit an obstacle
    o["checks"][0]["obstacle_ids"].append("hidden-cabinet")
    assert status(o) == "fail"


def test_known_obstacle_without_geometry_cannot_be_ignored():
    o, m = route_overlay(), model()
    m["entities"]["equipment"] = [{"id": "undrawn-pump", "building_id": "B", "floor_id": "floor-1"}]
    o["coverage"][0]["object_ids"].append("undrawn-pump")
    assert status(o, m) == "unknown"
    o["checks"][0]["obstacle_ids"].append("undrawn-pump")
    assert status(o, m) == "unknown"


def test_turning_and_service_zone():
    o = route_overlay("turning_circle", center_mm=[3500, 3500], diameter_mm=1500)
    assert status(o) == "pass"
    o["checks"][0]["center_mm"] = [1000, 1000]
    assert status(o) == "fail"
    o = overlay("clearance", subject_id="room", target_ids=["altar"], obstacle_ids=["cabinet"])
    assert status(o) == "fail"


def test_carry_dimensions_not_storage_guess():
    o = route_overlay("carry_route", route_clear_height_mm=2400)
    assert status(o) == "unknown"
    o["checks"][0]["transport"] = {
        "measurement_state": "measured",
        "width_mm": 800,
        "depth_mm": 1200,
        "height_mm": 2000,
        "evidence": PROOF,
    }
    assert status(o) == "pass"
    o["checks"][0]["path_mm"] = [[1000, 3000], [3000, 3000], [3000, 4000]]
    assert status(o) == "professional_review"


def test_cross_floor_projection_small_overlap_and_missing_elevation():
    o, m = overlay("projection", domain="fengshui"), model()
    o["objects"][1] = rectangle("cabinet", 1490, 500, 1000, 1000, floor="floor-2")
    o["coverage"][0]["object_ids"] = ["room", "altar"]
    o["coverage"].append({**o["coverage"][0], "floor_id": "floor-2", "object_ids": ["cabinet"]})
    assert status(o, m) == "warning"
    m["entities"]["storeys"][1].pop("elevation_mm")
    assert status(o, m) == "unknown"


def test_sightline_requires_real_fixed_screen_and_direction():
    o = overlay(
        "sightline",
        domain="fengshui",
        subject_id="door",
        target_ids=["cabinet"],
        obstacle_ids=["altar"],
        ray_mm=[[600, 600], [2000, 1000]],
        direction_verified=True,
    )
    o["objects"].append(rectangle("door", 400, 400, 300, 300, category="door_opening"))
    o["coverage"][0]["object_ids"].append("door")
    assert status(o) == "unknown"
    o["objects"][0]["fixed_opaque_sightline_blocker"] = True
    assert status(o) == "pass"


def test_headroom_and_regulation_version():
    o = overlay("headroom", subject_id="room", target_ids=[], minimum_mm=2200)
    m = model()
    m["entities"]["spaces"][0]["finished_headroom_mm"] = 2100
    assert status(o, m) == "fail"
    o = overlay("numeric", domain="building_regulation", actual=800, threshold=900, unit="mm", operator="min")
    assert status(o) == "professional_review"
    o["checks"][0]["law"] = {
        "title": "SYNTHETIC LAW NOT A REAL RULE",
        "article": "test-1",
        "effective_from": "2026-10-01",
        "applicability": "synthetic fixture only",
        "evidence": PROOF,
    }
    assert status(o) == "fail"


def test_candidate_unknown_not_masked_as_warning():
    req = {"requirements": [{"id": "req", "status": "candidate", "priority": "must"}]}
    o = overlay(requirement_id="req")
    assert status(o, req=req) == "warning"
    o["objects"][0].pop("polygon_mm")
    assert status(o, req=req) == "unknown"


@pytest.mark.parametrize("mutation", ["hash", "revision", "duplicate", "floor", "bad_ids"])
def test_stale_or_malformed_rejected(mutation):
    o = overlay()
    if mutation == "hash":
        o["revision_hash"] = "stale"
    elif mutation == "revision":
        o["revision_id"] = "old"
    elif mutation == "duplicate":
        o["objects"].append(copy.deepcopy(o["objects"][0]))
    elif mutation == "floor":
        o["objects"][0]["floor_id"] = "nonexistent"
    else:
        o["checks"][0]["target_ids"] = [[]]
    with pytest.raises(ContractError):
        run(o)


def test_issue_transitions_and_removal_not_resolution():
    before = run(overlay())
    o = overlay()
    o["objects"][1] = rectangle("cabinet", 3000, 500, 1000, 1000)
    assert compare_coordination(before, run(o))[0]["state"] == "resolved"
    assert compare_coordination(run(o), before)[0]["state"] == "new"
    o["objects"][0].pop("polygon_mm")
    assert compare_coordination(before, run(o))[0]["state"] == "evidence_lost"
    assert compare_coordination(before, {"findings": []})[0]["state"] == "evidence_lost"
    assert compare_coordination(before, before)[0]["state"] == "persistent"


def test_structure_polygon_changes_tracked():
    a = {"entities": {"beams": [rectangle("beam", 0, 0, 100, 500)]}}
    b = copy.deepcopy(a)
    b["entities"]["beams"][0]["polygon_mm"][1][0] = 110
    assert compare_models(a, b)[0]["fields"][0]["field"] == "polygon_mm"


def test_printable_zones_escaping_and_projection():
    o = route_overlay("turning_circle", center_mm=[3000, 3000], diameter_mm=1500)
    o["checks"][0]["title"] = "<script>alert(1)</script>"
    html = coordination_html(run(o))
    assert '<circle class="turn"' in html
    assert '<polyline class="route"' in html
    assert "<script>" not in html and "&lt;script&gt;" in html


def sealed_fixture(root: Path):
    m = model()
    directory = root / m["revision_id"]
    p = directory / "model.json"
    write_json(p, m)
    manifest = {
        "schema": "house-drawing-revision-v1",
        "revision_id": m["revision_id"],
        "label": "SYNTHETIC / NOT CONSTRUCTION",
        "status": "ready",
        "normalized_model": str(p),
        "normalized_model_sha256": sha256_file(p),
        "sources": [],
        "mapping": None,
        "issues": [],
    }
    manifest["content_hash"] = revision_manifest_content_hash(manifest)
    write_json(directory / "manifest.json", manifest)
    return manifest


def test_formal_report_hash_overlay_and_artifacts(tmp_path):
    manifest = sealed_fixture(tmp_path / "revisions")
    project_path = tmp_path / "project.json"
    write_json(project_path, read_json(ROOT / "inputs/project.json"))
    o = overlay()
    o["revision_hash"] = manifest["content_hash"]
    overlay_path = tmp_path / "overlay.json"
    write_json(overlay_path, o)
    kwargs = {"revision_id": "TEST-R1", "revision_root": tmp_path / "revisions", "project_path": project_path}
    before = build_review(**kwargs)
    after = build_review(**kwargs, coordination_path=overlay_path)
    assert before["report_hash"] != after["report_hash"]
    assert any(f["finding_id"] == "COORD-B-shrine" and f["status"] == "fail" for f in after["findings"])
    assert after["release"]["eligible"] is False
    output = write_review(after, output_root=tmp_path / "output")
    assert (output / "coordination.html").exists()
    assert "coordination.html" in (output / "report.md").read_text()

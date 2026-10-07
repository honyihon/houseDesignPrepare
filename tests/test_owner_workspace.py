from __future__ import annotations

import copy
import shutil

import pytest

from house_design.contracts import ROOT, ContractError, read_json, sha256_file, stable_hash, write_json
from house_design.owner_consistency import build_consistency_review, write_consistency_review
from house_design.owner_workspace import (
    DRAFT_SCHEMA,
    SOURCE_FILES,
    apply_measurements,
    build_workspace,
    import_owner_records,
    load_records,
    owner_summary,
    records_html,
    write_workspace,
)
from house_design.revision_integrity import verify_revision_integrity


@pytest.fixture
def workspace_root(tmp_path):
    for file in SOURCE_FILES.values():
        target = tmp_path / file
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / file, target)
    return tmp_path


def draft(root, kind="answer", target="PLAN-HOUSEHOLD-01", data=None):
    w = build_workspace(root)
    return {
        "schema": DRAFT_SCHEMA,
        "project_id": w["project_id"],
        "source_hashes": w["source_hashes"],
        "record_hash": w["record_hash"],
        "rows": [{"id": "draft-test-1", "kind": kind, "target": target, "data": data or {"answer": "待家庭討論"}}],
    }


def test_workspace_counts_and_no_mutation(workspace_root):
    before = {p: (workspace_root / p).read_bytes() for p in SOURCE_FILES.values()}
    w = build_workspace(workspace_root)
    assert len(w["rooms"]) == 66
    assert len(w["questions"]) == 105
    assert sum(q["due"] for q in w["questions"]) == 8
    assert all(r["status"] == "candidate" for r in w["rooms"])
    assert all("未建立" in r["geometry_mapping"] for r in w["rooms"])
    assert before == {p: (workspace_root / p).read_bytes() for p in SOURCE_FILES.values()}


def test_preview_apply_and_replay(workspace_root):
    file = workspace_root / "draft.json"
    write_json(file, draft(workspace_root))
    assert import_owner_records(file, root=workspace_root)["count"] == 1
    assert not (workspace_root / "inputs/owner-records.json").exists()
    import_owner_records(file, root=workspace_root, apply=True)
    assert (
        len(
            load_records(build_workspace(workspace_root)["project_id"], workspace_root / "inputs/owner-records.json")[
                "entries"
            ]
        )
        == 1
    )
    with pytest.raises(ContractError, match="stale"):
        import_owner_records(file, root=workspace_root, apply=True)
    w = build_workspace(workspace_root)
    assert all(r["status"] == "candidate" for r in w["rooms"])


@pytest.mark.parametrize(
    "mutation",
    ["project", "source", "target", "duplicate", "unknown_field", "wrong_type", "absolute_path", "professional_stage"],
)
def test_bad_drafts_rejected_atomically(workspace_root, mutation):
    d = draft(workspace_root)
    if mutation == "project":
        d["project_id"] = "other"
    elif mutation == "source":
        d["source_hashes"]["physical"] = "stale"
    elif mutation == "target":
        d["rows"][0]["target"] = "missing"
    elif mutation == "duplicate":
        d["rows"].append(copy.deepcopy(d["rows"][0]))
    elif mutation == "unknown_field":
        d["rows"][0]["data"]["private_notes"] = "secret"
    elif mutation == "wrong_type":
        d["rows"][0]["data"]["answer"] = []
    elif mutation == "absolute_path":
        d["rows"][0]["data"]["reference"] = "/mnt/d/private/photo.png"
    else:
        d["rows"][0].update(kind="meeting", target="meeting-1", data={"stage": "verified"})
    file = workspace_root / "draft.json"
    write_json(file, d)
    with pytest.raises(ContractError):
        import_owner_records(file, root=workspace_root, apply=True)
    assert not (workspace_root / "inputs/owner-records.json").exists()


def test_empty_rows_do_not_write(workspace_root):
    d = draft(workspace_root)
    d["rows"][0]["data"] = {"answer": " "}
    file = workspace_root / "draft.json"
    write_json(file, d)
    assert import_owner_records(file, root=workspace_root, apply=True)["count"] == 0
    assert not (workspace_root / "inputs/owner-records.json").exists()


def test_correction_preserves_history_and_chain(workspace_root):
    file = workspace_root / "draft.json"
    write_json(file, draft(workspace_root))
    import_owner_records(file, root=workspace_root, apply=True)
    d = draft(workspace_root, data={"answer": "改用彈性客房"})
    d["rows"][0].update(id="draft-test-2", supersedes="draft-test-1")
    write_json(file, d)
    import_owner_records(file, root=workspace_root, apply=True)
    path = workspace_root / "inputs/owner-records.json"
    entries = read_json(path)["entries"]
    assert len(entries) == 2
    assert entries[0]["data"]["answer"] == "待家庭討論"
    assert entries[1]["previous_hash"] == entries[0]["entry_hash"]
    value = read_json(path)
    value["entries"][0]["data"]["answer"] = "tampered"
    write_json(path, value)
    with pytest.raises(ContractError, match="hash"):
        build_workspace(workspace_root)


MEASURE = {
    "width_mm": "1260",
    "depth_mm": "1740",
    "height_mm": "1830",
    "measured_by": "測試角色",
    "measured_at": "2026-10-02",
    "method": "捲尺最大外廓",
    "reference": "TEST ONLY / measure-1",
}


def test_measurement_batch_separate_from_answers(workspace_root):
    file = workspace_root / "measure.json"
    d = draft(workspace_root, "measurement", "B.palanquin.primary", MEASURE)
    write_json(file, d)
    path = workspace_root / SOURCE_FILES["physical"]
    before = path.read_bytes()
    assert apply_measurements(file, root=workspace_root)["count"] == 1
    assert path.read_bytes() == before
    apply_measurements(file, root=workspace_root, apply=True)
    item = read_json(path)["items"][0]
    assert item["measurements"][0]["dimensions"]["width_mm"] == 1260
    assert item["transport"]["assembled_dimensions"] is None
    with pytest.raises(ContractError):
        apply_measurements(file, root=workspace_root, apply=True)
    history = build_workspace(workspace_root)["historical_rooms"]
    furniture = next(i for r in history for i in r["furniture"] if i.get("physical_item_id"))
    assert furniture["width_mm"] == 1260 and furniture["dimension_source"] == "measured"


@pytest.mark.parametrize(
    "change",
    [
        {"height_mm": ""},
        {"width_mm": "nan"},
        {"width_mm": "-1"},
        {"measured_at": "明天"},
        {"method": ""},
        {"transport_width_mm": "1600"},
    ],
)
def test_bad_measurements_never_write(workspace_root, change):
    file = workspace_root / "measure.json"
    write_json(file, draft(workspace_root, "measurement", "B.palanquin.primary", {**MEASURE, **change}))
    path = workspace_root / SOURCE_FILES["physical"]
    before = path.read_bytes()
    with pytest.raises(ContractError):
        apply_measurements(file, root=workspace_root, apply=True)
    assert path.read_bytes() == before


def test_transport_requires_complete_separate_envelope(workspace_root):
    file = workspace_root / "measure.json"
    values = {**MEASURE, "transport_width_mm": "1700", "transport_depth_mm": "3000", "transport_height_mm": "2000"}
    write_json(file, draft(workspace_root, "measurement", "B.palanquin.primary", values))
    apply_measurements(file, root=workspace_root, apply=True)
    item = read_json(workspace_root / SOURCE_FILES["physical"])["items"][0]
    assert item["transport"]["measurement_state"] == "measured"
    assert item["transport"]["evidence"]["reference"] == MEASURE["reference"]
    assert item["measurements"][0]["dimensions"]["width_mm"] == 1260


def test_public_output_and_html_escaping(workspace_root):
    private = workspace_root / "inputs/private"
    private.mkdir()
    write_json(private / "budget.json", {"secret": "PRIVATE-SENTINEL"})
    paths = write_workspace(workspace_root)
    assert "PRIVATE-SENTINEL" not in (workspace_root / "structured/predesign/owner-workspace.html").read_text()
    assert paths["room_cards"].endswith(".md")
    value = records_html(
        {"entries": [{"kind": "answer", "target": "x", "data": {"answer": "</pre><script>alert(1)</script>"}}]}
    )
    assert "<script>" not in value


def test_consistency_does_not_hide_missing_geometry(workspace_root):
    report = build_consistency_review(workspace_root)
    assert any(f["status"] == "insufficient" for f in report["findings"])
    write_consistency_review(workspace_root)
    assert (workspace_root / "structured/predesign/consistency-review.html").is_file()


def test_r000_diagnosis_read_only():
    path = ROOT / "inputs/revisions/R000/manifest.json"
    recovery = path.parent / "source-recovery.json"
    archived = path.parent / "source/plan.json"
    before = {file: file.read_bytes() for file in (path, recovery, archived)}
    report = build_consistency_review()
    item = next(f for f in report["findings"] if f["title"] == "R000 原來源已偏離封存雜湊")
    detail = item["detail"]
    # HEAD tracks a live design, not necessarily the R000 historical source.
    # Committing a newer plan must not invalidate its independently sealed copy.
    historical = detail["historical_candidate"]
    assert historical is not None
    assert historical["matches_manifest"] == (historical["sha256"] == detail["expected"])
    assert detail["actual"] != detail["expected"]
    assert sha256_file(archived) == detail["expected"]
    assert verify_revision_integrity("R000")["valid"]
    assert {file: file.read_bytes() for file in before} == before


def test_owner_reply_in_risk_and_stale_packet(workspace_root):
    from house_design.planning import build_risk_review, risk_html

    file = workspace_root / "draft.json"
    write_json(file, draft(workspace_root))
    import_owner_records(file, root=workspace_root, apply=True)
    report = build_risk_review(
        project_path=workspace_root / SOURCE_FILES["project"],
        requirements_path=workspace_root / SOURCE_FILES["requirements"],
        register_path=workspace_root / SOURCE_FILES["register"],
        physical_items_path=workspace_root / SOURCE_FILES["physical"],
    )
    assert report["owner_records"]["entries"][0]["data"]["answer"] == "待家庭討論"
    assert "待家庭討論" in risk_html(report)
    assert report["summary"]["due_completed"] == 0
    assert stable_hash(owner_summary(report["project"]["project_id"], workspace_root / "inputs/owner-records.json"))


def test_changed_sources_flag_prior_answers_for_review(workspace_root):
    file = workspace_root / "draft.json"
    write_json(file, draft(workspace_root))
    import_owner_records(file, root=workspace_root, apply=True)
    assert build_workspace(workspace_root)["records"][0]["source_status"] == "current"
    path = workspace_root / SOURCE_FILES["requirements"]
    value = read_json(path)
    value["requirements"][0]["title"] += "（測試變更）"
    write_json(path, value)
    assert build_workspace(workspace_root)["records"][0]["source_status"] == "needs_review"
    assert "待複核" in records_html(
        owner_summary(build_workspace(workspace_root)["project_id"], workspace_root / "inputs/owner-records.json")
    )


def test_correction_cannot_retarget_old_record(workspace_root):
    file = workspace_root / "draft.json"
    write_json(file, draft(workspace_root))
    import_owner_records(file, root=workspace_root, apply=True)
    value = draft(workspace_root, target="PLAN-HOUSEHOLD-02")
    value["rows"][0].update(id="new-test-id", supersedes="draft-test-1")
    write_json(file, value)
    with pytest.raises(ContractError, match="Correction kind/target"):
        import_owner_records(file, root=workspace_root, apply=True)
    assert len(build_workspace(workspace_root)["records"]) == 1

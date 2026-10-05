from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from house_design.contracts import ROOT, sha256_file, stable_hash, write_json
from house_design.drawings import load_revision, revision_model3d_readiness
from house_design.revision_integrity import revision_manifest_content_hash, verify_revision_integrity


def seal_record(record: dict, directory: Path) -> None:
    record["content_hash"] = stable_hash({k: v for k, v in record.items() if k != "content_hash"})
    write_json(directory / "source-recovery.json", record)


@pytest.fixture
def recovered_revision(tmp_path):
    root = tmp_path / "revisions"
    directory = root / "RQA"
    directory.mkdir(parents=True)
    live = tmp_path / "live.json"
    live.write_bytes(b'{"version":"old"}\n')
    archive = directory / "source/plan.json"
    archive.parent.mkdir()
    archive.write_bytes(live.read_bytes())
    model = directory / "normalized_model.json"
    write_json(model, {"revision_id": "RQA"})
    manifest = {
        "revision_id": "RQA",
        "immutable": True,
        "status": "legacy_assumption",
        "sources": [{"kind": "legacy_parametric_json", "file": str(live), "sha256": sha256_file(live)}],
        "normalized_model": str(model),
        "normalized_model_sha256": sha256_file(model),
    }
    manifest["content_hash"] = revision_manifest_content_hash(manifest)
    write_json(directory / "manifest.json", manifest)
    record = {
        "schema": "house-revision-source-recovery-v1",
        "revision_id": "RQA",
        "original_manifest_sha256": sha256_file(directory / "manifest.json"),
        "recovered_at": "2026-10-05T00:00:00+00:00",
        "reason": "Historical bytes recovered from Git",
        "sources": [
            {
                "source_index": 0,
                "original_file": str(live),
                "sha256": sha256_file(live),
                "archived_file": "source/plan.json",
                "origin": {"type": "git_commit", "commit": "a" * 40, "path": str(live)},
            }
        ],
    }
    seal_record(record, directory)
    return root, directory, live, archive, manifest, record


def test_live_updates_or_removal_do_not_change_verified_history(recovered_revision):
    root, directory, live, archive, manifest, record = recovered_revision
    before = (directory / "manifest.json").read_bytes()
    live.write_bytes(b'{"version":"new"}\n')
    result = verify_revision_integrity("RQA", root)
    assert result["valid"]
    source = next(c for c in result["checks"] if c["name"] == "source[0]")
    assert source["details"]["verification_source"] == "audited_historical_copy"
    assert source["details"]["actual_sha256"] == manifest["sources"][0]["sha256"]
    assert source["details"]["live_reference_sha256"] != source["details"]["actual_sha256"]
    assert (directory / "manifest.json").read_bytes() == before
    assert load_revision("RQA", root)[0] == manifest
    live.unlink()
    assert verify_revision_integrity("RQA", root)["valid"]


def test_archive_tampering_cannot_fall_back_to_a_matching_live_file(recovered_revision):
    root, directory, live, archive, manifest, record = recovered_revision
    archive.write_bytes(b"tampered history")
    result = verify_revision_integrity("RQA", root)
    assert not result["valid"]
    assert "source_recovery" in {e["name"] for e in result["errors"]}


def test_missing_archive_blocks_even_if_live_source_matches(recovered_revision):
    root, directory, live, archive, manifest, record = recovered_revision
    archive.unlink()
    assert not verify_revision_integrity("RQA", root)["valid"]


@pytest.mark.parametrize(
    "change", ["revision", "manifest", "hash", "path", "absolute", "commit", "index", "duplicate", "reason", "seal"]
)
def test_invalid_recovery_cannot_waive_original_integrity(recovered_revision, change):
    root, directory, live, archive, manifest, original = recovered_revision
    record = deepcopy(original)
    live.write_bytes(b"current changed")
    source = record["sources"][0]
    if change == "revision":
        record["revision_id"] = "OTHER"
    elif change == "manifest":
        record["original_manifest_sha256"] = "0" * 64
    elif change == "hash":
        source["sha256"] = sha256_file(live)
    elif change == "path":
        source["archived_file"] = "../../live.json"
    elif change == "absolute":
        source["archived_file"] = str(archive)
    elif change == "commit":
        source["origin"]["commit"] = "HEAD"
    elif change == "index":
        source["source_index"] = True
    elif change == "duplicate":
        record["sources"].append(deepcopy(source))
    elif change == "reason":
        record["reason"] = ""
    seal_record(record, directory)
    if change == "seal":
        record["reason"] = "unsealed edit"
        write_json(directory / "source-recovery.json", record)
    result = verify_revision_integrity("RQA", root)
    assert not result["valid"]
    assert "source_recovery" in {e["name"] for e in result["errors"]}


def test_symlink_cannot_escape_revision_source_directory(recovered_revision):
    root, directory, live, archive, manifest, record = recovered_revision
    archive.unlink()
    archive.symlink_to(live)
    assert not verify_revision_integrity("RQA", root)["valid"]


def test_bad_record_json_fails_closed(recovered_revision):
    root, directory, live, archive, manifest, record = recovered_revision
    (directory / "source-recovery.json").write_text("not json")
    assert not verify_revision_integrity("RQA", root)["valid"]


def test_unrecovered_revision_still_verifies_original_source(recovered_revision):
    root, directory, live, archive, manifest, record = recovered_revision
    (directory / "source-recovery.json").unlink()
    assert verify_revision_integrity("RQA", root)["valid"]
    live.write_bytes(b"tampered")
    assert not verify_revision_integrity("RQA", root)["valid"]


def test_r000_recovered_without_changing_its_original_seals_or_authority():
    directory = ROOT / "inputs/revisions/R000"
    assert (
        sha256_file(directory / "manifest.json") == "26d12f305008389150b87b0d00194ccab332952bac27b0ab3b16b84298c327c6"
    )
    assert (
        sha256_file(directory / "normalized_model.json")
        == "266c010a0792bb9a72a9afd902f022f5e8f2ccf7074da04a32080be3ba6c793b"
    )
    assert (
        sha256_file(directory / "source/plan.json")
        == "44dca801266f1f76d403b010765fcc3377073e22532ce08344e1c4c651b014a8"
    )
    assert verify_revision_integrity("R000")["valid"]
    manifest, model = load_revision("R000")
    assert manifest["status"] == "legacy_assumption"
    assert any(i["code"] == "LEGACY_FOOTPRINT_ASSUMPTION" for i in model["import_issues"])
    readiness = revision_model3d_readiness("R000")
    assert readiness["eligible"] is False
    assert readiness["status"] == "blocked"


def test_model_tampering_is_not_waived_by_source_recovery(recovered_revision):
    root, directory, live, archive, manifest, record = recovered_revision
    write_json(directory / "normalized_model.json", {"revision_id": "RQA", "changed": True})
    result = verify_revision_integrity("RQA", root)
    assert not result["valid"]
    assert "normalized_model_sha256" in {e["name"] for e in result["errors"]}


def test_resealed_changed_manifest_cannot_reuse_old_recovery(recovered_revision):
    root, directory, live, archive, manifest, record = recovered_revision
    manifest["label"] = "new interpretation"
    manifest["content_hash"] = revision_manifest_content_hash(manifest)
    write_json(directory / "manifest.json", manifest)
    result = verify_revision_integrity("RQA", root)
    assert not result["valid"]
    assert "source_recovery" in {e["name"] for e in result["errors"]}

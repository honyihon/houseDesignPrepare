"""Small read-only index tests; no browser, scene or proposal generation."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from house_design import project_status
from house_design.project_status import (
    digest,
    inspect_project,
    public_path,
    read_public_json,
    render_status,
    source_checks_current,
)

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def indexed(tmp_path):
    source = tmp_path / "inputs/example.json"
    write_json(source, {"status": "unknown"})
    write_json(tmp_path / "structured/example/review.json", {
        "adopted": False, "source_hashes": {"inputs/example.json": hashlib.sha256(source.read_bytes()).hexdigest()}})
    for file in ("Docs/example.md", "structured/example.html", "structured/example-3d.html"):
        target = tmp_path / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("Not a rendered or approved fixture", encoding="utf-8")
    index = {"schema": "house-project-status-index-v1", "updated_at": "2026-10-27", "default_package": "example",
        "packages": [{"id": "example", "label": "Test only", "role": "discussion-basis", "document": "Docs/example.md",
            "entry": "structured/example.html", "viewer": "structured/example-3d.html",
            "report": "structured/example/review.json", "owner_reported_run": "synthetic-not-real",
            "owner_reported_status": "passed", "raw_result": None}], "work_items": []}
    write_json(tmp_path / project_status.INDEX, index)
    return tmp_path, index


def test_fresh_source_and_reported_pass_do_not_approve_qa_or_design(indexed):
    root, _ = indexed
    result = inspect_project(root)
    p = result["packages"][0]
    assert source_checks_current(result)
    assert p["source_state"] == "declared-source-hashes-match"
    assert p["owner_reported_status"] == "passed" and p["raw_result_state"] == "not-imported"
    assert p["rendered_qa_acceptance"] == "not-verified-by-this-index" and p["design_adopted"] is False
    assert p["professional_approval"] == "unknown"


def test_source_change_requires_rebuild_without_rewriting_expected_hash(indexed):
    root, _ = indexed
    report = (root / "structured/example/review.json").read_bytes()
    (root / "inputs/example.json").write_text("changed fixture", encoding="utf-8")
    result = inspect_project(root)
    p = result["packages"][0]
    assert not source_checks_current(result) and p["source_state"] == "source-changed-rebuild-required"
    assert [c["path"] for c in p["changed_sources"]] == ["inputs/example.json"]
    assert (root / "structured/example/review.json").read_bytes() == report


def test_raw_passed_result_is_present_but_never_accepted_automatically(indexed):
    root, index = indexed
    index["packages"][0]["raw_result"] = "Docs/qa-evidence/example.json"
    write_json(root / "Docs/qa-evidence/example.json", {"status": "passed", "sourceHashes": {}})
    write_json(root / project_status.INDEX, index)
    p = inspect_project(root)["packages"][0]
    assert p["raw_result_state"] == "present-unverified" and p["raw_result"]["sha256"]
    assert p["rendered_qa_acceptance"] == "not-verified-by-this-index"


def test_data_only_package_does_not_request_new_browser_evidence(indexed):
    root, index = indexed
    index["packages"][0].update(role="data-only-no-new-viewer", viewer=None,
        owner_reported_run=None, owner_reported_status=None)
    write_json(root / project_status.INDEX, index)
    p = inspect_project(root)["packages"][0]
    assert p["raw_result_state"] == "not-required-no-new-viewer"
    assert p["professional_approval"] == "unknown"


def test_markdown_keeps_all_table_rows_together_before_changed_source_list(indexed):
    root, index = indexed
    index["packages"].append({**index["packages"][0], "id": "second"})
    write_json(root / project_status.INDEX, index)
    (root / "inputs/example.json").write_text("changed", encoding="utf-8")
    lines = render_status(inspect_project(root)).splitlines()
    row_indices = [i for i, line in enumerate(lines) if line.startswith("|")]
    assert len(row_indices) == 4
    assert row_indices == list(range(row_indices[0], row_indices[-1] + 1))
    assert lines.index("## 來源差異／待補檔案") > row_indices[-1]


def test_missing_artifact_or_source_remains_incomplete(indexed):
    root, _ = indexed
    (root / "inputs/example.json").unlink()
    result = inspect_project(root)
    assert not source_checks_current(result)
    assert result["packages"][0]["source_state"] == "source-check-incomplete"


@pytest.mark.parametrize("name", ["", ".", "../secret.json", "/tmp/private.json", "inputs/private/example.json",
    ".git/config", "Docs/../../secret.json", "C:\\Users\\private.json"])
def test_private_hidden_absolute_and_traversal_paths_are_not_read(indexed, name):
    root, _ = indexed
    with pytest.raises(ValueError):
        public_path(root, name)


def test_symlink_to_private_or_outside_is_not_read(indexed, tmp_path):
    root, _ = indexed
    private = root / "inputs/private/example.json"
    write_json(private, {"sensitive": "test fixture only"})
    link = root / "Docs/private-link.json"
    try:
        link.symlink_to(private)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError):
        public_path(root, "Docs/private-link.json")
    link.unlink()
    link.symlink_to(tmp_path.parent / "outside.json")
    with pytest.raises(ValueError):
        public_path(root, "Docs/private-link.json")


def test_byte_limits_do_not_require_large_fixtures(indexed, monkeypatch):
    root, _ = indexed
    monkeypatch.setattr(project_status, "MAX_BYTES", 4)
    with pytest.raises(ValueError, match="20MB"):
        digest(root, "inputs/example.json", {})
    with pytest.raises(ValueError, match="20MB"):
        read_public_json(root, "inputs/example.json")


def test_duplicate_ids_and_unknown_default_are_rejected(indexed):
    root, index = indexed
    index["packages"].append(dict(index["packages"][0]))
    write_json(root / project_status.INDEX, index)
    with pytest.raises(ValueError, match="unique"):
        inspect_project(root)
    index["packages"].pop()
    index["default_package"] = "missing"
    write_json(root / project_status.INDEX, index)
    with pytest.raises(ValueError, match="Default"):
        inspect_project(root)


def test_index_is_read_only_and_does_not_spawn_browser(indexed):
    root, _ = indexed
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = inspect_project(root)
    assert not result["writes_performed"] and not result["browser_started"]
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_cli_check_exit_codes_and_json_are_source_only(indexed):
    root, _ = indexed
    cmd = [sys.executable, "-B", str(ROOT / "scripts/check_project_status.py"), "--root", str(root), "--check", "--json"]
    fresh = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=5)
    assert fresh.returncode == 0 and json.loads(fresh.stdout)["writes_performed"] is False
    (root / "inputs/example.json").write_text("changed", encoding="utf-8")
    stale = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=5)
    assert stale.returncode == 1
    assert json.loads(stale.stdout)["packages"][0]["source_state"] == "source-changed-rebuild-required"


def test_project_registry_has_separate_latest_c_scope_and_no_accepted_raw_results():
    index = read_public_json(ROOT, project_status.INDEX)
    assert index["default_package"] == "current-basis"
    by_id = {p["id"]: p for p in index["packages"]}
    assert by_id["c-care-layout"]["role"] == "care-comparison-not-merged-into-current-basis"
    assert by_id["c-care-products"]["viewer"] is None
    assert all(p["raw_result"] is None for p in index["packages"])
    assert index["authority"] == "navigation-and-work-index-only-not-design-requirement-or-approval"

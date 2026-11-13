"""Small file-only maintenance checks; no browser or model generation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_repository_health import inspect, local_only, markdown_links

ROOT = Path(__file__).resolve().parents[1]


def test_only_local_sources_are_excluded_without_reading_private_content(tmp_path):
    result = inspect(tmp_path, ["inputs/private/never-opened.json", ".claude/settings.local.json", ".env"])
    assert len(result["issues"]) == 3 and result["public_json_checked"] == 0
    assert all(v["kind"] == "local-only-file-in-public-index" for v in result["issues"])
    assert not local_only(".claude/settings.example.json")
    assert not local_only(".env.mcp.example")


def test_markdown_fences_external_links_fragments_and_escaped_paths():
    text = '[real](Docs/hello%20world.md?q=1#anchor)\n[online](https://example.com/x)\n[local](#section)\n~~~\n[fake](missing.md)\n~~~\n'
    assert list(markdown_links(text)) == [("Docs/hello%20world.md?q=1#anchor", "Docs/hello world.md")]


def test_missing_and_private_links_are_reported_without_modification(tmp_path):
    file = tmp_path/"README.md"
    text = "[missing](Docs/no.md)\n[private](inputs/private/no.json)\n[outside](../no.md)\n"
    file.write_text(text, encoding="utf-8")
    result = inspect(tmp_path, ["README.md"])
    assert {v["kind"] for v in result["issues"]} == {"missing-local-document-link", "document-links-private-data", "document-link-outside-project"}
    assert file.read_text() == text and not result["writes_performed"]
    assert not result["browser_started"]


def test_invalid_json_and_duplicates_are_not_auto_deleted(tmp_path):
    (tmp_path/"bad.json").write_text("not json", encoding="utf-8")
    for name in ["one.txt", "two.txt"]:
        (tmp_path/name).write_text("example"*200, encoding="utf-8")
    result = inspect(tmp_path, ["bad.json", "one.txt", "two.txt"])
    assert result["issues"][0]["kind"] == "invalid-public-text-or-json"
    assert len(result["duplicate_groups"]) == 1
    assert (tmp_path/"one.txt").is_file() and (tmp_path/"two.txt").is_file()


def test_byte_and_file_limits_are_bounded(tmp_path, monkeypatch):
    import scripts.check_repository_health as module
    monkeypatch.setattr(module, "MAX_FILE_BYTES", 4)
    (tmp_path/"large.json").write_text("not read", encoding="utf-8")
    result = inspect(tmp_path, ["large.json"])
    assert result["public_json_checked"] == 0 and result["informational"]
    monkeypatch.setattr(module, "MAX_FILES", 0)
    with pytest.raises(ValueError, match="bounded file count"):
        inspect(tmp_path, ["large.json"])


def test_symlink_to_outside_is_not_read(tmp_path):
    (tmp_path/"outside.json").symlink_to(tmp_path.parent/"not-in-project.json")
    result = inspect(tmp_path, ["outside.json"])
    assert result["issues"][0]["kind"] == "outside-project-path"


def test_new_navigation_and_manifest_json_are_well_formed():
    result = inspect(ROOT)
    assert result["issues"] == []
    assert result["public_json_checked"] >= 185
    assert result["markdown_checked"] >= 137
    assert len(result["duplicate_groups"]) >= 5
    index = json.loads((ROOT/"inputs/project-status.json").read_text(encoding="utf-8"))
    assert index["work_mode"] == "conditional-preplanning-real-data-integration-later"


def test_historical_cli_instructions_do_not_auto_expand_to_heavy_work():
    claude = (ROOT/"CLAUDE.md").read_text(encoding="utf-8")
    workflow = (ROOT/".claude/commands/workflow-house-all-in-one.md").read_text(encoding="utf-8")
    export = (ROOT/".claude/commands/export-final-design-html.md").read_text(encoding="utf-8")
    assert "Current operating mode (2026-11-06)" in claude and "AGENTS.md" in claude
    assert "related_report_hash" in workflow and "related_report_generated_at" in workflow
    assert "do not automatically" in workflow and "do not automatically start it" in export

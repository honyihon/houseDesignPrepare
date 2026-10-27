from __future__ import annotations

import json

import pytest

from house_design.contracts import ROOT, read_json, write_json
from house_design.meeting_pack import build_meeting_pack, meeting_pack_html, meeting_pack_markdown


@pytest.mark.parametrize("revision_fields,expected", [
    ({"revision_id": "TEST-R002"}, "TEST-R002"),
    ({"revision": "TEST-LEGACY"}, "TEST-LEGACY"),
    ({"revision_id": "TEST-R003", "revision": "TEST-OLD"}, "TEST-R003"),
    ({"revision_id": "", "revision": "TEST-LEGACY"}, "TEST-LEGACY"),
])
def test_handoff_revision_matches_json_html_and_markdown(tmp_path, revision_fields, expected):
    project_path = tmp_path / "project.json"
    write_json(project_path, read_json(ROOT / "inputs/project.json"))
    handoff_root = tmp_path / "handoff"
    write_json(handoff_root / "handoff-manifest.json", {**revision_fields, "label": "TEST ONLY"})
    pack = build_meeting_pack(project_path=project_path, predesign_path=tmp_path / "predesign.json",
                             criteria_path=tmp_path / "criteria.json", predesign_root=tmp_path / "reports",
                             handoff_root=handoff_root)
    handoff = next(s for s in json.loads(json.dumps(pack))["sections"] if s["id"] == "handoff")
    assert handoff["available"] and handoff["revision"] == expected
    assert f"版次 <code>{expected}</code>" in meeting_pack_html(pack)
    assert f"版次：`{expected}`" in meeting_pack_markdown(pack)


def test_missing_handoff_stays_unavailable_not_an_empty_or_invented_revision(tmp_path):
    project_path = tmp_path / "project.json"
    write_json(project_path, read_json(ROOT / "inputs/project.json"))
    pack = build_meeting_pack(project_path=project_path, predesign_path=tmp_path / "predesign.json",
                             criteria_path=tmp_path / "criteria.json", predesign_root=tmp_path / "reports",
                             handoff_root=tmp_path / "missing-handoff")
    handoff = next(s for s in pack["sections"] if s["id"] == "handoff")
    assert not handoff["available"]
    assert handoff["title"] in pack["missing_sections"]
    assert "版次 <code></code>" not in meeting_pack_html(pack)
    assert "版次：`None`" not in meeting_pack_markdown(pack)


def test_handoff_without_either_revision_field_explicitly_remains_unknown(tmp_path):
    from house_design.meeting_pack import _render_handoff, _section_handoff

    section = _section_handoff({"label": "TEST ONLY"}, tmp_path)
    assert section["revision"] is None
    assert "版次 <code>未提供</code>" in _render_handoff(section)

"""Archive regressions must detect tampering and never label source drift fresh."""
from __future__ import annotations

import json
from pathlib import Path

import historical_support as archive
import pytest


@pytest.fixture
def sealed(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "ROOT", tmp_path)
    monkeypatch.setattr(archive, "SEALS", tmp_path / "seals.json")
    source = tmp_path / "source.py"
    source.write_bytes(b"current source\n")
    artifact = tmp_path / "plan.svg"
    artifact.write_bytes(b"<svg/>\n")
    report = {"source_hashes": {"source.py": "0" * 64}, "adopted": False}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    record = {"report": "report.json", "report_sha256": archive.checksum(path),
              "artifacts": {"plan.svg": archive.checksum(artifact)},
              "observed_source_drift": {"source.py": {"recorded": "0" * 64, "current": archive.checksum(source)}}}
    archive.SEALS.write_text(json.dumps({"studies": {"example": record}}), encoding="utf-8")
    return tmp_path, report


def test_archived_source_drift_stays_explicit_and_no_file_is_written(sealed):
    root, expected = sealed
    before = {p: p.read_bytes() for p in root.iterdir()}
    assert archive.historical_study("example") == expected
    assert archive.source_drift(expected)["source.py"]["recorded"] == "0" * 64
    assert before == {p: p.read_bytes() for p in root.iterdir()}


@pytest.mark.parametrize("name,error", [("report.json", "Historical report changed"),
                                       ("plan.svg", "Historical artifact changed"),
                                       ("source.py", "Unreviewed historical source drift")])
def test_changed_archive_or_new_source_drift_fails_closed(sealed, name, error):
    root, _ = sealed
    path = root / name
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(AssertionError, match=error):
        archive.historical_study("example")


def test_viewer_loader_only_decodes_json_and_refuses_executable_code(tmp_path):
    path = tmp_path / "viewer.html"
    path.write_text('var DATA = {"value": 7};\n', encoding="utf-8")
    assert archive.saved_payload(path) == {"value": 7}
    path.write_text('var DATA = (()=>{throw Error("do not execute")})();\n', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        archive.saved_payload(path)


def test_svg_namespace_registry_is_reset_between_tests():
    from xml.etree import ElementTree as ET

    assert "http://www.w3.org/2000/svg" not in ET._namespace_map
    ET.register_namespace("", "http://www.w3.org/2000/svg")


def test_a_previous_svg_registration_does_not_leak_into_this_test():
    from xml.etree import ElementTree as ET

    assert "http://www.w3.org/2000/svg" not in ET._namespace_map


def test_checkout_rules_keep_frozen_crlf_html_and_live_javascript_bytes():
    import subprocess

    root = Path(__file__).resolve().parents[1]
    paths = ["structured/architect_handoffs/R001/legacy-reference/index.html", "assets/html_design_bridge.js",
             "scripts/check_storage_3d_playwright.cjs"]
    result = subprocess.run(["git", "check-attr", "text", "eol", "--", *paths], cwd=root,
                            capture_output=True, text=True, check=True, timeout=5)
    assert paths[0] + ": text: unset" in result.stdout
    for path in paths[1:]:
        assert path + ": eol: lf" in result.stdout

"""Explicit export adapter changes archive metadata, never content or source guards."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import sys
import zipfile
from pathlib import Path

import pytest

from house_design.contracts import ContractError, stable_hash
from house_design.reproducible_export import canonical_export_context, canonical_report, canonical_zip_metadata, main


def archive():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as writer:
        info = zipfile.ZipInfo("plan.txt", date_time=(2026, 11, 13, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        writer.writestr(info, b"same sealed content\n")
    return output.getvalue()


def test_native_windows_metadata_produces_exact_canonical_archive_and_restores_api(monkeypatch):
    original = zipfile.ZipInfo.__init__
    with canonical_zip_metadata():
        expected = archive()

    def windows_default(info, *args, **kwargs):
        original(info, *args, **kwargs)
        info.create_system = 0

    monkeypatch.setattr(zipfile.ZipInfo, "__init__", windows_default)
    native = archive()
    assert native != expected
    with canonical_zip_metadata():
        assert archive() == expected
    assert zipfile.ZipInfo.__init__ is windows_default
    with zipfile.ZipFile(io.BytesIO(native)) as old, zipfile.ZipFile(io.BytesIO(expected)) as new:
        assert old.read("plan.txt") == new.read("plan.txt") == b"same sealed content\n"


def test_context_restores_stdlib_even_when_source_guard_rejects_export():
    original = zipfile.ZipInfo.__init__
    with pytest.raises(ValueError, match="source changed"), canonical_zip_metadata():
        raise ValueError("source changed")
    assert zipfile.ZipInfo.__init__ is original


def test_launcher_preserves_arguments_exit_status_and_caller_argv(tmp_path):
    script = tmp_path / "test-export.py"
    script.write_text('import sys,zipfile\nassert sys.argv[1:] == ["--check"]\n'
                      'assert zipfile.ZipInfo("fixture").create_system == 3\nraise SystemExit(7)\n', encoding="utf-8")
    previous = sys.argv
    with pytest.raises(SystemExit) as error:
        main([str(script), "--check"])
    assert error.value.code == 7 and sys.argv is previous


def test_existing_discussion_archive_remains_exact_with_windows_style_defaults(monkeypatch):
    original = zipfile.ZipInfo.__init__

    def windows_default(info, *args, **kwargs):
        original(info, *args, **kwargs)
        info.create_system = 0

    monkeypatch.setattr(zipfile.ZipInfo, "__init__", windows_default)
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(SystemExit) as error:
        main([str(root / "scripts/export_design_discussion_basis.py"), "--check"])
    assert error.value.code == 0
    assert zipfile.ZipInfo.__init__ is windows_default


@pytest.fixture
def report_case(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"sealed source")
    report = {"source_hashes": {"source.txt": hashlib.sha256(source.read_bytes()).hexdigest()},
              "coordinates": [12522.854704013233, 3134.5569093655627], "adopted": False}
    report["report_hash"] = stable_hash(report)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return tmp_path, path, report


def test_native_roundoff_binds_to_verified_reference_without_overwriting_either_hash(report_case):
    root, path, reference = report_case
    actual = copy.deepcopy(reference)
    actual["coordinates"][0] = math.nextafter(actual["coordinates"][0], math.inf)
    actual["report_hash"] = stable_hash({k: v for k, v in actual.items() if k != "report_hash"})
    before = {p: p.read_bytes() for p in root.iterdir()}
    assert actual["report_hash"] != reference["report_hash"]
    assert canonical_report(root, path, actual) == reference
    assert actual["coordinates"] != reference["coordinates"]
    assert before == {p: p.read_bytes() for p in root.iterdir()}


@pytest.mark.parametrize("change", ["source", "geometry", "decision", "self-hash"])
def test_canonical_report_rejects_real_changes_before_export(report_case, change):
    root, path, actual = report_case
    if change == "source":
        (root / "source.txt").write_bytes(b"changed source")
    elif change == "geometry":
        actual["coordinates"][0] += .001
    elif change == "decision":
        actual["adopted"] = True
    if change != "self-hash":
        actual["report_hash"] = stable_hash({k: v for k, v in actual.items() if k != "report_hash"})
    else:
        actual["report_hash"] = "0" * 64
    with pytest.raises(ContractError):
        canonical_report(root, path, actual)


def test_export_context_restores_frozen_builder_and_module_search_path():
    from house_design import design_discussion_basis as discussion

    original = discussion.build_laundry_access
    original_path = sys.path[:]
    with pytest.raises(ValueError, match="stop"), canonical_export_context():
        assert discussion.build_laundry_access is not original
        raise ValueError("stop")
    assert discussion.build_laundry_access is original and sys.path == original_path

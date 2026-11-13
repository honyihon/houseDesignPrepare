"""Explicit export adapter changes archive metadata, never content or source guards."""
from __future__ import annotations

import io
import sys
import zipfile

import pytest

from house_design.reproducible_export import canonical_zip_metadata, main


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

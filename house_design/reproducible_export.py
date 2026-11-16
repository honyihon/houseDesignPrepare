"""Reproduce sealed discussion exports across native host differences.

The legacy exporters explicitly write Unix file permissions, but ZipInfo's
creator-system default follows the host OS. Native libm/GEOS can also produce
last-bit coordinate differences. Verify those against unchanged sealed inputs
without modifying the frozen exporters, drawings, or source hashes.
"""
from __future__ import annotations

import copy
import json
import math
import runpy
import sys
import zipfile
from contextlib import contextmanager
from pathlib import Path

from house_design.contracts import ContractError, sha256_file, stable_hash


def equivalent_geometry(reference, actual, path=""):
    """Permit only numeric roundoff; structures, source seals and decisions stay exact."""
    if isinstance(reference, dict):
        if not isinstance(actual, dict) or reference.keys() != actual.keys():
            raise ContractError("Canonical report keys changed: "+path)
        for key in reference:
            equivalent_geometry(reference[key], actual[key], path+"/"+key)
    elif isinstance(reference, (list, tuple)):
        if not isinstance(actual, (list, tuple)) or len(reference) != len(actual):
            raise ContractError("Canonical report sequence changed: "+path)
        for n, (a, b) in enumerate(zip(reference, actual, strict=True)):
            equivalent_geometry(a, b, path+"/"+str(n))
    elif isinstance(reference, float) and isinstance(actual, float):
        if not math.isfinite(reference) or not math.isfinite(actual) or abs(reference-actual) > 1e-9:
            raise ContractError("Canonical report numeric geometry changed: "+path)
    elif type(reference) is not type(actual) or reference != actual:
        raise ContractError("Canonical report fact or decision changed: "+path)


def canonical_report(root, report_path, actual):
    """Bind a native recomputation to unchanged sealed inputs and equivalent recorded math.

    Both self-hashes are verified independently. The caller still checks its pinned
    report file SHA; this function does not invent or overwrite any report hash.
    """
    root = Path(root).resolve()
    path = (root / report_path).resolve()
    if not path.is_relative_to(root):
        raise ContractError("Canonical report leaves project root")
    reference = json.loads(path.read_text(encoding="utf-8"))
    for report in (reference, actual):
        if report.get("report_hash") != stable_hash({k: v for k, v in report.items() if k != "report_hash"}):
            raise ContractError("Canonical report self-hash changed")
    if not reference.get("source_hashes"):
        raise ContractError("Canonical report source bindings missing")
    for name, expected in reference["source_hashes"].items():
        source = (root / name).resolve()
        if not source.is_relative_to(root) or not source.is_file() or sha256_file(source) != expected:
            raise ContractError("Canonical report source changed: "+name)
    equivalent_geometry({k: v for k, v in reference.items() if k != "report_hash"},
                        {k: v for k, v in actual.items() if k != "report_hash"})
    return copy.deepcopy(reference)


@contextmanager
def canonical_zip_metadata():
    """Single-threaded export-process context; restore the standard library on exit."""
    original = zipfile.ZipInfo.__init__

    def initialize(info, *args, **kwargs):
        original(info, *args, **kwargs)
        info.create_system = 3  # The archived file mode is 0o100644 << 16 (Unix).

    zipfile.ZipInfo.__init__ = initialize
    try:
        yield
    finally:
        zipfile.ZipInfo.__init__ = original


@contextmanager
def canonical_export_context(root=None):
    """Explicit compatibility boundary for the frozen discussion-package exporter."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    previous_path = sys.path[:]
    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from house_design import design_discussion_basis as discussion

    original = discussion.build_laundry_access

    def verified_laundry_access(project_root):
        actual = original(project_root)
        return canonical_report(project_root, "structured/coordination/abc-laundry-access-v1/review.json", actual)

    discussion.build_laundry_access = verified_laundry_access
    try:
        with canonical_zip_metadata():
            yield
    finally:
        discussion.build_laundry_access = original
        sys.path[:] = previous_path


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0].startswith("-"):
        raise SystemExit("Usage: python -m house_design.reproducible_export EXPORT_SCRIPT.py [arguments]")
    script = Path(args[0]).resolve()
    previous = sys.argv
    try:
        sys.argv = [str(script), *args[1:]]
        with canonical_export_context():
            runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.argv = previous


if __name__ == "__main__":
    main()

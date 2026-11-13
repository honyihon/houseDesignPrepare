"""Run frozen exporters with their original Unix ZIP metadata on any host.

The legacy exporters explicitly write Unix file permissions, but ZipInfo's
creator-system default follows the host OS. Keep that metadata consistent
without modifying the sealed exporters, drawings, or source hashes.
"""
from __future__ import annotations

import runpy
import sys
import zipfile
from contextlib import contextmanager
from pathlib import Path


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


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0].startswith("-"):
        raise SystemExit("Usage: python -m house_design.reproducible_export EXPORT_SCRIPT.py [arguments]")
    script = Path(args[0]).resolve()
    previous = sys.argv
    try:
        sys.argv = [str(script), *args[1:]]
        with canonical_zip_metadata():
            runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.argv = previous


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Read the project navigation/source index without writes or browser work."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from house_design.project_status import inspect_project, render_status, source_checks_current  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout; never writes a report")
    parser.add_argument("--check", action="store_true", help="Exit 1 when indexed source checks are incomplete or changed")
    parser.add_argument("--include-history", action="store_true", help="Also require archived source checks; differences still always printed")
    args = parser.parse_args()
    try:
        result = inspect_project(args.root)
    except (OSError, ValueError) as exc:
        print(f"Project index unavailable: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render_status(result), end="\n")
    return 1 if args.check and not source_checks_current(result, include_history=args.include_history) else 0


if __name__ == "__main__":
    raise SystemExit(main())

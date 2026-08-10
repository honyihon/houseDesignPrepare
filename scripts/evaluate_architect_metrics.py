#!/usr/bin/env python3
"""Evaluate concept-level architectural metrics from room_program.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.architect_metrics import evaluate_program, generate_metrics_report_md
from lib.standards import load_residential_defaults, repo_relative


PROGRAM_FILE = ROOT / "structured" / "room_program.json"
OUTPUT_DIR = ROOT / "structured" / "architect_metrics"
DEFAULT_OUTPUT_JSON = OUTPUT_DIR / "metrics.json"
DEFAULT_OUTPUT_MD = OUTPUT_DIR / "report.md"


def parse_buildings(raw: str) -> list[str]:
    buildings: list[str] = []
    for item in raw.split(","):
        token = item.strip().upper()
        if token and token not in buildings:
            buildings.append(token)
    return buildings or ["A", "B", "C", "STORAGE"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate concept-level architect metrics for A/B/C residential plans."
    )
    parser.add_argument("--program", type=Path, default=PROGRAM_FILE, help="room_program.json path")
    parser.add_argument("--buildings", type=str, default="A,B,C,STORAGE", help="Comma separated building IDs")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    program_path = args.program.resolve()
    if not program_path.exists():
        raise SystemExit(f"room_program not found: {program_path}")

    defaults = load_residential_defaults()
    program = json.loads(program_path.read_text(encoding="utf-8"))
    selected_buildings = parse_buildings(args.buildings)
    payload = evaluate_program(program, defaults, selected_buildings)
    payload["source_program_file"] = repo_relative(program_path)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(generate_metrics_report_md(payload), encoding="utf-8")

    print(f"Architect metrics JSON: {args.output_json.resolve()}")
    print(f"Architect metrics MD:   {args.output_md.resolve()}")
    print(f"Evaluated floors:       {payload['evaluated_floor_count']}")
    print(f"Skipped floors:         {payload['skipped_floor_count']}")
    print(f"Metrics:                {payload['metrics_count']}")


if __name__ == "__main__":
    main()

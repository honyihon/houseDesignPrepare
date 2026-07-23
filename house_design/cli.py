from __future__ import annotations

import argparse
import subprocess
import sys

from house_design.pipeline import build_steps, run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="house-design")
    subparsers = parser.add_subparsers(dest="command", required=True)
    pipeline = subparsers.add_parser("pipeline", help="Run the incremental layout pipeline")
    pipeline.add_argument("--mode", choices=("concept", "draft", "ifc"), default="draft")
    pipeline.add_argument("--selection", choices=("auto", "baseline", "best"), default="auto")
    pipeline.add_argument("--style", choices=("presentation", "technical", "debug"), default="presentation")
    pipeline.add_argument("--paper", choices=("a3", "a4"), default="a3")
    pipeline.add_argument("--output", default="structured/candidates/print_bundle.pdf")
    pipeline.add_argument("--python-exe", default=sys.executable)
    pipeline.add_argument("--force", action="store_true")
    step_names = [step.name for step in build_steps("baseline", "presentation", "a3", "output.pdf", "ifc")]
    pipeline.add_argument("--from-step", choices=step_names)
    pipeline.add_argument("--to-step", choices=step_names)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "pipeline":
        try:
            run_pipeline(
                mode=args.mode,
                selection=args.selection,
                style=args.style,
                paper=args.paper,
                output=args.output,
                force=args.force,
                from_step=args.from_step,
                to_step=args.to_step,
                python_exe=args.python_exe,
            )
        except (ValueError, subprocess.CalledProcessError) as exc:
            raise SystemExit(str(exc)) from exc

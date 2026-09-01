from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from house_design.contracts import ContractError, read_json, write_json
from house_design.dashboard import write_dashboard
from house_design.drawings import (
    compare_revisions,
    import_revision,
    list_revisions,
    revision_model3d_readiness,
    seed_legacy_parametric_revision,
    verify_revision_integrity,
)
from house_design.intake import decide_requirement, migrate_legacy_briefs, validate_intake
from house_design.meeting_report import write_meeting_pdf
from house_design.model3d import export_revision_model3d
from house_design.pipeline import build_steps, run_pipeline
from house_design.predesign import (
    build_predesign_report,
    validate_bundle,
    write_predesign_report,
)
from house_design.review import build_review, write_review


def _path(value: str | None) -> Path | None:
    return Path(value).expanduser() if value else None


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="house-design")
    subparsers = parser.add_subparsers(dest="command", required=True)
    pipeline = subparsers.add_parser("pipeline", help="Run the incremental layout pipeline")
    pipeline.add_argument(
        "--mode",
        choices=("concept", "draft", "release", "ifc"),
        default="draft",
        help="release is the professional-gated workflow; ifc is a deprecated compatibility alias",
    )
    pipeline.add_argument("--selection", choices=("auto", "baseline", "best"), default="auto")
    pipeline.add_argument("--style", choices=("presentation", "technical", "debug"), default="presentation")
    pipeline.add_argument("--paper", choices=("a3", "a4"), default="a3")
    pipeline.add_argument("--output", default="structured/candidates/print_bundle.pdf")
    pipeline.add_argument("--python-exe", default=sys.executable)
    pipeline.add_argument("--force", action="store_true")
    step_names = [step.name for step in build_steps("baseline", "presentation", "a3", "output.pdf", "ifc")]
    pipeline.add_argument("--from-step", choices=step_names)
    pipeline.add_argument("--to-step", choices=step_names)

    intake = subparsers.add_parser("intake", help="Manage parcel facts and owner requirement decisions")
    intake_sub = intake.add_subparsers(dest="intake_command", required=True)
    intake_validate = intake_sub.add_parser("validate", help="Validate project and requirement contracts")
    intake_validate.add_argument("--project", default="inputs/project.json")
    intake_validate.add_argument("--requirements", default="inputs/requirements.json")
    intake_migrate = intake_sub.add_parser(
        "migrate-briefs", help="Import legacy A/B/C briefs as unconfirmed candidate requirements"
    )
    intake_migrate.add_argument("--brief-dir", default="inputs/brief")
    intake_migrate.add_argument("--output", default="inputs/requirements.json")
    intake_decide = intake_sub.add_parser(
        "requirements-decide", help="Confirm or reject one requirement and append its decision log"
    )
    intake_decide.add_argument("--id", required=True)
    intake_decide.add_argument("--status", choices=("confirmed", "rejected"), required=True)
    intake_decide.add_argument("--priority", choices=("must", "should", "could"), required=True)
    intake_decide.add_argument("--reason", required=True)
    intake_decide.add_argument("--decided-by", required=True)
    intake_decide.add_argument("--decided-at")
    intake_decide.add_argument("--requirements", default="inputs/requirements.json")

    predesign = subparsers.add_parser("predesign", help="Validate phase gates before land purchase and construction")
    predesign_sub = predesign.add_subparsers(dest="predesign_command", required=True)
    for operation in ("validate", "report"):
        command = predesign_sub.add_parser(operation, help=f"{operation.title()} the predesign readiness register")
        command.add_argument("--project", default="inputs/project.json")
        command.add_argument("--predesign", default="inputs/predesign.json")
        command.add_argument("--rules", default="rules/predesign_readiness_rules.json")
        command.add_argument("--budget-private", default="inputs/private/budget.json")
        if operation == "report":
            command.add_argument("--output-root", default="structured/predesign")

    drawings = subparsers.add_parser("drawings", help="Import and compare immutable drawing revisions")
    drawings_sub = drawings.add_subparsers(dest="drawings_command", required=True)
    drawing_import = drawings_sub.add_parser("import", help="Import PDF plus IFC or DXF")
    drawing_import.add_argument("--revision", required=True)
    drawing_import.add_argument("--label", required=True)
    drawing_import.add_argument("--pdf")
    drawing_import.add_argument("--ifc")
    drawing_import.add_argument("--dxf")
    drawing_import.add_argument("--mapping")
    drawing_import.add_argument("--root", default="inputs/revisions")
    drawing_list = drawings_sub.add_parser("list", help="List immutable revisions")
    drawing_list.add_argument("--root", default="inputs/revisions")
    drawing_seed = drawings_sub.add_parser(
        "seed-legacy", help="Expose the historical parametric scenario as a non-authoritative R000 revision"
    )
    drawing_seed.add_argument("--revision", default="R000")
    drawing_seed.add_argument("--variant", default="f6000_g1")
    drawing_seed.add_argument("--plan", default="structured/parametric/plan.json")
    drawing_seed.add_argument("--root", default="inputs/revisions")
    drawing_compare = drawings_sub.add_parser("compare", help="Compare two normalized revisions")
    drawing_compare.add_argument("--from", dest="before_revision", required=True)
    drawing_compare.add_argument("--to", dest="after_revision", required=True)
    drawing_compare.add_argument("--root", default="inputs/revisions")
    drawing_compare.add_argument("--output")
    drawing_model3d = drawings_sub.add_parser(
        "model3d-readiness", help="Check whether a revision has authoritative geometry for current 3D"
    )
    drawing_model3d.add_argument("--revision", required=True)
    drawing_model3d.add_argument("--root", default="inputs/revisions")
    drawing_model3d.add_argument("--level", choices=("space_block", "walkthrough"), default="space_block")
    drawing_verify = drawings_sub.add_parser("verify", help="Verify immutable source, mapping and model hashes")
    drawing_verify.add_argument("--revision", required=True)
    drawing_verify.add_argument("--root", default="inputs/revisions")
    drawing_export = drawings_sub.add_parser(
        "export-model3d", help="Export a self-contained current-revision space-block viewer"
    )
    drawing_export.add_argument("--revision", required=True)
    drawing_export.add_argument("--root", default="inputs/revisions")
    drawing_export.add_argument("--output")
    drawing_export.add_argument("--output-root", default="structured/reviews")

    review = subparsers.add_parser("review", help="Run evidence-backed project and drawing review")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_run = review_sub.add_parser("run", help="Generate JSON, Markdown and offline dashboard")
    review_run.add_argument("--revision", required=True)
    review_run.add_argument("--previous")
    review_run.add_argument("--project", default="inputs/project.json")
    review_run.add_argument("--requirements", default="inputs/requirements.json")
    review_run.add_argument("--rules", default="rules/kaohsiung_review_rules.json")
    review_run.add_argument("--predesign", default="inputs/predesign.json")
    review_run.add_argument("--predesign-rules", default="rules/predesign_readiness_rules.json")
    review_run.add_argument("--budget-private", default="inputs/private/budget.json")
    review_run.add_argument("--revision-root", default="inputs/revisions")
    review_run.add_argument("--output-root", default="structured/reviews")
    review_run.add_argument("--signoff")
    review_run.add_argument("--skip-pdf", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "pipeline":
            mode = "release" if args.mode == "ifc" else args.mode
            if args.mode == "ifc":
                print("[deprecated] --mode ifc is now named --mode release; IFC is reserved for drawing files.")
            run_pipeline(
                mode=mode,
                selection=args.selection,
                style=args.style,
                paper=args.paper,
                output=args.output,
                force=args.force,
                from_step=args.from_step,
                to_step=args.to_step,
                python_exe=args.python_exe,
            )
        elif args.command == "intake" and args.intake_command == "validate":
            result = validate_intake(project_path=Path(args.project), requirements_path=Path(args.requirements))
            _print_json(result)
            if not result["valid"]:
                raise SystemExit(1)
        elif args.command == "intake" and args.intake_command == "migrate-briefs":
            result = migrate_legacy_briefs(brief_dir=Path(args.brief_dir), output=Path(args.output))
            _print_json(
                {
                    "output": str(Path(args.output)),
                    "requirements": len(result["requirements"]),
                    "status": "all imported items are candidate",
                }
            )
        elif args.command == "intake" and args.intake_command == "requirements-decide":
            result = decide_requirement(
                requirement_id=args.id,
                status=args.status,
                priority=args.priority,
                reason=args.reason,
                decided_by=args.decided_by,
                decided_at=args.decided_at,
                requirements_path=Path(args.requirements),
            )
            _print_json(result)
        elif args.command == "predesign" and args.predesign_command == "validate":
            private_path = Path(args.budget_private)
            result = validate_bundle(
                project=read_json(Path(args.project)),
                predesign=read_json(Path(args.predesign)),
                rules=read_json(Path(args.rules)),
                private_budget=read_json(private_path) if private_path.exists() else None,
            )
            _print_json(result)
            if not result["valid"]:
                raise SystemExit(1)
        elif args.command == "predesign" and args.predesign_command == "report":
            report = build_predesign_report(
                project_path=Path(args.project),
                predesign_path=Path(args.predesign),
                rule_pack_path=Path(args.rules),
                private_budget_path=Path(args.budget_private),
            )
            directory = write_predesign_report(report, Path(args.output_root))
            _print_json(
                {
                    "report": str(directory / "report.json"),
                    "markdown": str(directory / "report.md"),
                    "sources": str(directory / "sources.md"),
                    "current_phase": report["current_phase"],
                    "readiness_percent": report["readiness"]["percent"],
                    "eligible_for_next_phase": report["gate"]["eligible_for_next_phase"],
                    "active_blockers": report["gate"]["active_blockers"],
                }
            )
        elif args.command == "drawings" and args.drawings_command == "import":
            result = import_revision(
                revision_id=args.revision,
                label=args.label,
                pdf=_path(args.pdf),
                ifc=_path(args.ifc),
                dxf=_path(args.dxf),
                mapping_path=_path(args.mapping),
                root=Path(args.root),
            )
            _print_json(result)
        elif args.command == "drawings" and args.drawings_command == "list":
            _print_json({"revisions": list_revisions(Path(args.root))})
        elif args.command == "drawings" and args.drawings_command == "seed-legacy":
            result = seed_legacy_parametric_revision(
                plan_path=Path(args.plan),
                revision_id=args.revision,
                variant_id=args.variant,
                root=Path(args.root),
            )
            _print_json(result)
        elif args.command == "drawings" and args.drawings_command == "compare":
            result = compare_revisions(
                before_revision=args.before_revision,
                after_revision=args.after_revision,
                root=Path(args.root),
            )
            if args.output:
                write_json(Path(args.output), result)
            _print_json(result)
        elif args.command == "drawings" and args.drawings_command == "model3d-readiness":
            result = revision_model3d_readiness(args.revision, Path(args.root), args.level)
            _print_json(result)
            if not result["eligible"]:
                raise SystemExit(1)
        elif args.command == "drawings" and args.drawings_command == "verify":
            result = verify_revision_integrity(args.revision, Path(args.root))
            _print_json(result)
            if not result["valid"]:
                raise SystemExit(1)
        elif args.command == "drawings" and args.drawings_command == "export-model3d":
            result = export_revision_model3d(
                revision_id=args.revision,
                root=Path(args.root),
                output=Path(args.output) if args.output else None,
                output_root=Path(args.output_root),
            )
            _print_json(result)
        elif args.command == "review" and args.review_command == "run":
            report = build_review(
                revision_id=args.revision,
                project_path=Path(args.project),
                requirements_path=Path(args.requirements),
                rule_pack_path=Path(args.rules),
                predesign_path=Path(args.predesign),
                predesign_rule_pack_path=Path(args.predesign_rules),
                private_budget_path=Path(args.budget_private),
                revision_root=Path(args.revision_root),
                previous_revision=args.previous,
                signoff_path=_path(args.signoff),
            )
            directory = write_review(report, output_root=Path(args.output_root))
            dashboard = write_dashboard(report, directory)
            meeting_pdf = None if args.skip_pdf else write_meeting_pdf(report, directory / "meeting-report.pdf")
            _print_json(
                {
                    "report": str(directory / "report.json"),
                    "markdown": str(directory / "report.md"),
                    "dashboard": str(dashboard),
                    "meeting_pdf": str(meeting_pdf) if meeting_pdf else None,
                    "release_eligible": report["release"]["eligible"],
                    "model3d_status": report["model3d_readiness"]["status"],
                    "model3d_eligible": report["model3d_readiness"]["eligible"],
                    "status_counts": report["status_counts"],
                }
            )
    except (ContractError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc

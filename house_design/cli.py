from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from house_design.architect_handoff import (
    create_handoff_package,
    preflight_handoff_package,
    write_preflight_report,
)
from house_design.brief import build_design_brief, write_design_brief
from house_design.contracts import ContractError, read_json, write_json
from house_design.dashboard import write_dashboard
from house_design.drawings import (
    compare_revisions,
    import_revision,
    list_revisions,
    revision_model3d_readiness,
    seed_legacy_parametric_revision,
)
from house_design.envelope import build_envelope_scenario, write_envelope_scenario
from house_design.intake import (
    apply_requirement_decisions,
    decide_requirement,
    export_requirement_sheet,
    migrate_legacy_briefs,
    validate_intake,
)
from house_design.meeting_pack import build_meeting_pack, write_meeting_pack
from house_design.meeting_report import write_meeting_pdf
from house_design.model3d import export_revision_model3d
from house_design.owner_consistency import write_consistency_review
from house_design.owner_workspace import apply_measurements, import_owner_records, write_workspace
from house_design.physical_items import record_physical_item_measurement
from house_design.pipeline import build_steps, run_pipeline
from house_design.planning import build_risk_review, write_risk_review
from house_design.predesign import (
    build_predesign_report,
    validate_bundle,
    write_predesign_report,
)
from house_design.review import build_review, write_review
from house_design.revision_integrity import verify_revision_integrity
from house_design.sites import add_candidate_site, build_site_comparison, write_site_comparison


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
    for name in ("owner-records-import", "physical-measurements-import"):
        command = intake_sub.add_parser(name, help="Preview an offline draft; --apply explicitly writes the batch")
        command.add_argument("--file", required=True)
        command.add_argument("--root", default=".")
        command.add_argument("--apply", action="store_true")
    intake_validate = intake_sub.add_parser(
        "validate", help="Validate project, requirement and physical-item contracts"
    )
    intake_validate.add_argument("--project", default="inputs/project.json")
    intake_validate.add_argument("--requirements", default="inputs/requirements.json")
    intake_validate.add_argument("--physical-items", default="inputs/physical-items.json")
    intake_validate.add_argument("--site-criteria", default="inputs/site-criteria.json")
    intake_migrate = intake_sub.add_parser(
        "migrate-briefs", help="Import legacy A/B/C briefs as unconfirmed candidate requirements"
    )
    intake_migrate.add_argument("--brief-dir", default="inputs/brief")
    intake_migrate.add_argument("--output", default="inputs/requirements.json")
    intake_sheet = intake_sub.add_parser(
        "requirements-sheet", help="Export a fill-in decision sheet for one owner meeting"
    )
    intake_sheet.add_argument("--requirements", default="inputs/requirements.json")
    intake_sheet.add_argument("--output", default="structured/predesign/requirements-sheet.json")
    intake_decide = intake_sub.add_parser(
        "requirements-decide",
        help="Confirm or reject one requirement (--id) or a filled decision sheet (--batch) and append decision logs",
    )
    decide_target = intake_decide.add_mutually_exclusive_group(required=True)
    decide_target.add_argument("--id")
    decide_target.add_argument("--batch", help="Filled sheet from intake requirements-sheet; applied all-or-nothing")
    intake_decide.add_argument("--status", choices=("confirmed", "rejected"), help="required with --id")
    intake_decide.add_argument("--priority", choices=("must", "should", "could"), help="required with --id")
    intake_decide.add_argument("--reason", help="required with --id")
    intake_decide.add_argument("--decided-by", required=True)
    intake_decide.add_argument("--decided-at")
    intake_decide.add_argument("--requirements", default="inputs/requirements.json")
    intake_site_add = intake_sub.add_parser(
        "site-add", help="Register one candidate site from the template; every fact starts unknown"
    )
    intake_site_add.add_argument("--id", required=True)
    intake_site_add.add_argument("--label", required=True)
    intake_site_add.add_argument("--project", default="inputs/project.json")
    intake_site_add.add_argument("--template", default="inputs/site-candidate.template.json")
    intake_measure = intake_sub.add_parser(
        "physical-item-measure", help="Append one complete measured envelope to the physical-item register"
    )
    intake_measure.add_argument("--id", required=True)
    intake_measure.add_argument("--width-mm", required=True, type=float)
    intake_measure.add_argument("--depth-mm", required=True, type=float)
    intake_measure.add_argument("--height-mm", required=True, type=float)
    intake_measure.add_argument("--measured-by", required=True)
    intake_measure.add_argument("--method", required=True)
    intake_measure.add_argument("--measured-at")
    intake_measure.add_argument("--note", default="")
    intake_measure.add_argument("--physical-items", default="inputs/physical-items.json")

    predesign = subparsers.add_parser("predesign", help="Validate phase gates before land purchase and construction")
    predesign_sub = predesign.add_subparsers(dest="predesign_command", required=True)
    for name in ("owner-workspace", "consistency-review"):
        command = predesign_sub.add_parser(name, help="Generate public offline owner tools")
        command.add_argument("--root", default=".")
        command.add_argument("--output-root")
    risk = predesign_sub.add_parser("risk-review", help="Review public scenario decisions, missing coverage and phase deadlines")
    risk.add_argument("--project", default="inputs/project.json")
    risk.add_argument("--requirements", default="inputs/requirements.json")
    risk.add_argument("--register", default="inputs/planning-register.json")
    risk.add_argument("--rules", default="rules/predesign_readiness_rules.json")
    risk.add_argument("--physical-items", default="inputs/physical-items.json")
    risk.add_argument("--drawing-report", help="Selected formal review JSON; missing/untrusted checks remain unknown")
    risk.add_argument("--previous-report", help="Hash-verified earlier risk-review JSON to track removed/changed items")
    risk.add_argument("--revision-root", default="inputs/revisions")
    risk.add_argument("--output-root", default="structured/predesign")
    for operation in ("validate", "report"):
        command = predesign_sub.add_parser(operation, help=f"{operation.title()} the predesign readiness register")
        command.add_argument("--project", default="inputs/project.json")
        command.add_argument("--predesign", default="inputs/predesign.json")
        command.add_argument("--rules", default="rules/predesign_readiness_rules.json")
        command.add_argument("--budget-private", default="inputs/private/budget.json")
        if operation == "report":
            command.add_argument("--output-root", default="structured/predesign")
    predesign_brief = predesign_sub.add_parser(
        "brief", help="Write the consolidated design brief for architect and interior-designer meetings"
    )
    predesign_brief.add_argument("--project", default="inputs/project.json")
    predesign_brief.add_argument("--requirements", default="inputs/requirements.json")
    predesign_brief.add_argument("--physical-items", default="inputs/physical-items.json")
    predesign_brief.add_argument("--household-profile", default="inputs/private/household-profile.json")
    predesign_brief.add_argument("--design-request", default="inputs/design_request.md")
    predesign_brief.add_argument("--output-root", default="structured/predesign")
    predesign_brief.add_argument("--planning-register", help="Public scenario register (canonical project loads its default automatically)")
    meeting = predesign_sub.add_parser("meeting-pack", help="Compose the current architect site-search meeting packet")
    meeting.add_argument("--project", default="inputs/project.json")
    meeting.add_argument("--requirements", default="inputs/requirements.json")
    meeting.add_argument("--register", default="inputs/planning-register.json")
    meeting.add_argument("--source-root", default="structured/predesign")
    meeting.add_argument("--output-root", default="structured/predesign")

    predesign_compare = predesign_sub.add_parser(
        "site-compare", help="Score candidate sites against the elimination register; unknown never reads as a pass"
    )
    predesign_compare.add_argument("--project", default="inputs/project.json")
    predesign_compare.add_argument("--criteria", default="inputs/site-criteria.json")
    predesign_compare.add_argument("--output-root", default="structured/predesign")
    predesign_envelope = predesign_sub.add_parser(
        "envelope",
        help="Hypothetical buildable-envelope scenario for the architect meeting; not a regulatory finding",
    )
    predesign_envelope.add_argument("--candidate", help="Read ratios and dimensions from this candidate site")
    predesign_envelope.add_argument("--parcel", help="Single parcel_id within the candidate; never use the three-parcel total")
    predesign_envelope.add_argument("--assume-bcr", type=float, dest="assume_bcr", help="Building coverage ratio")
    predesign_envelope.add_argument("--assume-far", type=float, dest="assume_far", help="Floor area ratio")
    predesign_envelope.add_argument("--assume-frontage-mm", type=float, dest="assume_frontage_mm")
    predesign_envelope.add_argument("--assume-depth-mm", type=float, dest="assume_depth_mm")
    predesign_envelope.add_argument("--assume-setback-mm", type=float, dest="assume_setback_mm")
    predesign_envelope.add_argument("--assume-parcel-sqm", type=float, dest="assume_parcel_sqm")
    predesign_envelope.add_argument("--storeys", type=int, default=3, help="Habitable storeys; RF is a roof, not one")
    predesign_envelope.add_argument("--project", default="inputs/project.json")
    predesign_envelope.add_argument("--physical-items", default="inputs/physical-items.json")
    predesign_envelope.add_argument("--output-root", default="structured/predesign")

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
    drawing_handoff = drawings_sub.add_parser(
        "prepare-handoff", help="Create a future architect delivery contract without creating a revision"
    )
    drawing_handoff.add_argument("--revision", default="R001")
    drawing_handoff.add_argument("--label", default="初步設計")
    drawing_handoff.add_argument("--output-root", default="structured/architect_handoffs")
    drawing_handoff.add_argument("--predecessor-root", default="/mnt/d/Desktop/houseDesign")
    drawing_handoff.add_argument("--project", default="inputs/project.json")
    drawing_handoff.add_argument("--requirements", default="inputs/requirements.json")
    drawing_handoff.add_argument(
        "--brief", help="Design brief JSON from predesign brief; must match the project and requirement files"
    )
    drawing_preflight = drawings_sub.add_parser(
        "preflight", help="Preview-import an architect delivery package without creating a revision"
    )
    drawing_preflight.add_argument("--package", required=True)
    drawing_preflight.add_argument("--output")

    review = subparsers.add_parser("review", help="Run evidence-backed project and drawing review")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_template = review_sub.add_parser("template", help="Prepare an unverified revision-bound coordination overlay")
    review_template.add_argument("--revision", required=True)
    review_template.add_argument("--revision-root", default="inputs/revisions")
    review_template.add_argument("--output", required=True)
    review_run = review_sub.add_parser("run", help="Generate JSON, Markdown and offline dashboard")
    review_run.add_argument("--revision", required=True)
    review_run.add_argument("--previous")
    review_run.add_argument("--coordination", help="Revision-bound architectural/interior overlay JSON")
    review_run.add_argument("--previous-coordination", help="Previous revision overlay (requires --previous)")
    review_run.add_argument("--project", default="inputs/project.json")
    review_run.add_argument("--requirements", default="inputs/requirements.json")
    review_run.add_argument("--rules", default="rules/kaohsiung_review_rules.json")
    review_run.add_argument("--predesign", default="inputs/predesign.json")
    review_run.add_argument("--predesign-rules", default="rules/predesign_readiness_rules.json")
    review_run.add_argument("--budget-private", default="inputs/private/budget.json")
    review_run.add_argument("--revision-root", default="inputs/revisions")
    review_run.add_argument("--output-root", default="structured/reviews")
    review_run.add_argument("--signoff")
    review_run.add_argument("--planning-register", help="Public scenario register; does not confirm owner requirements")
    review_run.add_argument("--skip-pdf", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
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
            result = validate_intake(
                project_path=Path(args.project),
                requirements_path=Path(args.requirements),
                physical_items_path=Path(args.physical_items),
                site_criteria_path=Path(args.site_criteria),
            )
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
        elif args.command == "intake" and args.intake_command == "requirements-sheet":
            _print_json(
                export_requirement_sheet(requirements_path=Path(args.requirements), output=Path(args.output))
            )
        elif args.command == "intake" and args.intake_command == "requirements-decide":
            single_fields = {"--status": args.status, "--priority": args.priority, "--reason": args.reason}
            if args.batch:
                given = [flag for flag, value in single_fields.items() if value is not None]
                if given:
                    parser.error(f"{', '.join(given)} cannot be combined with --batch; fill them in the sheet")
                result = apply_requirement_decisions(
                    sheet_path=Path(args.batch),
                    decided_by=args.decided_by,
                    decided_at=args.decided_at,
                    requirements_path=Path(args.requirements),
                )
            else:
                missing = [flag for flag, value in single_fields.items() if value is None]
                if missing:
                    parser.error(f"--id requires {', '.join(missing)}")
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
        elif args.command == "intake" and args.intake_command == "site-add":
            result = add_candidate_site(
                candidate_id=args.id,
                label=args.label,
                project_path=Path(args.project),
                template_path=Path(args.template),
            )
            _print_json(result)
        elif args.command == "intake" and args.intake_command in {"owner-records-import", "physical-measurements-import"}:
            operation = import_owner_records if args.intake_command == "owner-records-import" else apply_measurements
            _print_json(operation(Path(args.file), root=Path(args.root).resolve(), apply=args.apply))
        elif args.command == "predesign" and args.predesign_command in {"owner-workspace", "consistency-review"}:
            operation = write_workspace if args.predesign_command == "owner-workspace" else write_consistency_review
            _print_json(operation(root=Path(args.root).resolve(), output_root=_path(args.output_root)))
        elif args.command == "intake" and args.intake_command == "physical-item-measure":
            result = record_physical_item_measurement(
                item_id=args.id,
                width_mm=args.width_mm,
                depth_mm=args.depth_mm,
                height_mm=args.height_mm,
                measured_by=args.measured_by,
                method=args.method,
                measured_at=args.measured_at,
                note=args.note,
                path=Path(args.physical_items),
            )
            _print_json(result)
        elif args.command == "predesign" and args.predesign_command == "meeting-pack":
            pack = build_meeting_pack(project_path=Path(args.project), requirements_path=Path(args.requirements),
                                      planning_register_path=Path(args.register), predesign_root=Path(args.source_root))
            paths = write_meeting_pack(pack, Path(args.output_root))
            _print_json({**{k: str(v) for k, v in paths.items()}, "missing_sections": pack["missing_sections"]})
        elif args.command == "predesign" and args.predesign_command == "risk-review":
            report = build_risk_review(
                project_path=Path(args.project), requirements_path=Path(args.requirements),
                register_path=Path(args.register), rules_path=Path(args.rules),
                drawing_report_path=_path(args.drawing_report), previous_report_path=_path(args.previous_report),
                revision_root=Path(args.revision_root),
                physical_items_path=Path(args.physical_items),
            )
            paths = write_risk_review(report, Path(args.output_root))
            _print_json({**{key: str(path) for key, path in paths.items()},
                         "summary": report["summary"], "readiness": report["readiness"]})
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
        elif args.command == "predesign" and args.predesign_command == "site-compare":
            report = build_site_comparison(
                project_path=Path(args.project),
                criteria_path=Path(args.criteria),
            )
            paths = write_site_comparison(report, Path(args.output_root))
            _print_json(
                {
                    "report": str(paths["json"]),
                    "markdown": str(paths["markdown"]),
                    "html": str(paths["html"]),
                    "compare_hash": report["compare_hash"],
                    "candidates": len(report["candidates"]),
                    "criteria": len(report["criteria"]),
                    "summary": report["summary"],
                    "next_actions": len(report["next_actions"]),
                    "warnings": report["warnings"],
                }
            )
        elif args.command == "predesign" and args.predesign_command == "envelope":
            report = build_envelope_scenario(
                project_path=Path(args.project),
                physical_items_path=Path(args.physical_items),
                candidate_id=args.candidate,
                parcel_id=args.parcel,
                bcr=args.assume_bcr,
                far=args.assume_far,
                frontage_mm=args.assume_frontage_mm,
                depth_mm=args.assume_depth_mm,
                setback_mm=args.assume_setback_mm,
                parcel_area_sqm=args.assume_parcel_sqm,
                storeys=args.storeys,
            )
            paths = write_envelope_scenario(report, Path(args.output_root))
            _print_json(
                {
                    "report": str(paths["json"]),
                    "markdown": str(paths["markdown"]),
                    "html": str(paths["html"]),
                    "scenario": report["scenario"],
                    "scenario_hash": report["scenario_hash"],
                    "overall_verdict": report["overall_verdict"],
                    "effective_footprint_sqm": report["area"]["effective_footprint_sqm"],
                    "open_questions": len(report["open_questions"]),
                    "warnings": report["warnings"],
                }
            )
        elif args.command == "predesign" and args.predesign_command == "brief":
            brief = build_design_brief(
                project_path=Path(args.project),
                requirements_path=Path(args.requirements),
                physical_items_path=Path(args.physical_items),
                household_profile_path=Path(args.household_profile),
                design_request_path=Path(args.design_request),
                planning_register_path=_path(args.planning_register),
            )
            paths = write_design_brief(brief, Path(args.output_root))
            summary = brief["decision_summary"]
            _print_json(
                {
                    "brief": str(paths["json"]),
                    "markdown": str(paths["markdown"]),
                    "html": str(paths["html"]),
                    "brief_hash": brief["brief_hash"],
                    "requirements": summary["requirements"],
                    "status_counts": summary["status_counts"],
                    "relationships": summary["relationships"],
                    "open_questions": sum(len(group["questions"]) for group in brief["open_questions"]),
                    "household_profile_provided": brief["household"]["provided"],
                    "warnings": brief["warnings"],
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
        elif args.command == "drawings" and args.drawings_command == "prepare-handoff":
            result = create_handoff_package(
                revision_id=args.revision,
                label=args.label,
                output_root=Path(args.output_root),
                predecessor_root=Path(args.predecessor_root),
                project_path=Path(args.project),
                requirements_path=Path(args.requirements),
                brief_path=_path(args.brief),
            )
            _print_json(result)
        elif args.command == "drawings" and args.drawings_command == "preflight":
            result = preflight_handoff_package(Path(args.package))
            if args.output:
                write_preflight_report(result, Path(args.output))
            _print_json(result)
            if not result["ready_for_space_block"]:
                raise SystemExit(1)
        elif args.command == "review" and args.review_command == "template":
            from house_design.coordination import coordination_template
            from house_design.drawings import load_revision

            manifest, model = load_revision(args.revision, Path(args.revision_root))
            destination = Path(args.output)
            if destination.exists():
                raise ContractError("Template destination already exists; existing designer inputs were preserved")
            write_json(destination, coordination_template(model, manifest["content_hash"]))
            _print_json({"coordination_template": str(destination), "revision": args.revision})
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
                coordination_path=_path(args.coordination),
                previous_coordination_path=_path(args.previous_coordination),
                planning_register_path=_path(args.planning_register),
            )
            directory = write_review(report, output_root=Path(args.output_root))
            dashboard = write_dashboard(report, directory)
            meeting_pdf = None if args.skip_pdf else write_meeting_pdf(report, directory / "meeting-report.pdf")
            _print_json(
                {
                    "report": str(directory / "report.json"),
                    "markdown": str(directory / "report.md"),
                    "dashboard": str(dashboard),
                    "coordination": str(directory / "coordination.html"),
                    "meeting_pdf": str(meeting_pdf) if meeting_pdf else None,
                    "release_eligible": report["release"]["eligible"],
                    "model3d_status": report["model3d_readiness"]["status"],
                    "model3d_eligible": report["model3d_readiness"]["eligible"],
                    "status_counts": report["status_counts"],
                }
            )
    except (ContractError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_run_full_pipeline_defines_validation_owner() -> None:
    script = (ROOT / "scripts" / "run_full_pipeline.ps1").read_text(encoding="utf-8")

    assert '[ValidateSet("inner", "outer", "none")]' in script
    assert '[string]$ValidationOwner = "inner"' in script
    assert '$ValidationOwner -eq "inner"' in script
    assert '@("scripts/validate_layout_bundle.py", "--strict")' in script
    assert '[ValidateSet("concept", "draft", "release", "ifc")]' in script
    assert 'if ($Mode -eq "release")' in script


def test_expert_workflow_passes_outer_validation_owner() -> None:
    script = (ROOT / "scripts" / "run_full_expert_workflow.ps1").read_text(encoding="utf-8")

    assert "-ValidationOwner outer" in script
    assert '$validationArgs += "--strict"' in script


def test_expert_workflow_passes_mode_to_html_consistency_check() -> None:
    script = (ROOT / "scripts" / "run_full_expert_workflow.ps1").read_text(encoding="utf-8")

    assert re.search(
        r'Invoke-PythonStep -Name "Step 3/8 HTML consistency check" -Arguments @\(\s*"scripts/check_html_consistency.py",\s*"--buildings", \$buildingsArg,\s*"--mode", \$Mode\s*\)',
        script,
        re.DOTALL,
    )


def test_manual_workflow_docs_include_mode_for_html_consistency() -> None:
    all_in_one = (ROOT / "scripts" / "WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md").read_text(encoding="utf-8")
    web_to_plan = (ROOT / "scripts" / "WEB_TO_PLAN_PROMPTS.zh-TW.md").read_text(encoding="utf-8")

    assert "python scripts/check_html_consistency.py --buildings <buildings> --mode <mode>" in all_in_one
    assert "python scripts/check_html_consistency.py --buildings <buildings> --mode <mode>" in web_to_plan
    assert "-ValidationOwner outer" in all_in_one
    assert "-ValidationOwner outer" in web_to_plan


def test_expert_gate_stage_does_not_update_task_board() -> None:
    script = (ROOT / "scripts" / "evaluate_expert_gates.py").read_text(encoding="utf-8")

    assert 'if args.stage in {"report", "full"}:' in script
    assert 'task_board_status = "skipped for stage gate"' in script
    assert 'print(f"Task board:  {task_board_status}")' in script


def test_expert_workflow_allows_gate_exit_10_before_explicit_exit() -> None:
    script = (ROOT / "scripts" / "run_full_expert_workflow.ps1").read_text(encoding="utf-8")

    assert 'AllowedExitCodes @(0, 10)' in script
    assert "exit 10" in script


def test_ifc_signoff_hash_is_enforced_at_report_stage() -> None:
    script = (ROOT / "scripts" / "run_full_expert_workflow.ps1").read_text(encoding="utf-8")

    assert "Assert-IfCSignoff" not in script
    assert "--enforce-signoff-hash" in script
    assert "AllowedExitCodes @(0, 2, 10)" in script
    assert "exit 2" in script


def test_expert_workflow_generates_domain_checklist_before_final_html() -> None:
    script = (ROOT / "scripts" / "run_full_expert_workflow.ps1").read_text(encoding="utf-8")

    assert 'Step 7/8 generate domain checklist' in script
    assert '"scripts/generate_domain_checklist.py"' in script
    assert 'Step 8/8 export final design HTML' in script


def test_docs_describe_signoff_hash_and_domain_checklist() -> None:
    usage = (ROOT / "Docs" / "claude-code-usage.md").read_text(encoding="utf-8")
    readme = (ROOT / "scripts" / "README.md").read_text(encoding="utf-8")

    assert "related_report_hash" in usage
    assert "domain_checklist.md" in usage
    assert "related_report_hash" in readme
    assert "domain_checklist.md" in readme


def test_prompts_do_not_describe_decision_only_ifc_signoff() -> None:
    all_in_one = (ROOT / "scripts" / "WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md").read_text(encoding="utf-8")
    web_to_plan = (ROOT / "scripts" / "WEB_TO_PLAN_PROMPTS.zh-TW.md").read_text(encoding="utf-8")

    assert "related_report_hash" in all_in_one
    assert "related_report_hash" in web_to_plan

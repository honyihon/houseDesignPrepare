from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_run_full_pipeline_defines_validation_owner() -> None:
    script = (ROOT / "scripts" / "run_full_pipeline.ps1").read_text(encoding="utf-8")

    assert '[ValidateSet("inner", "outer", "none")]' in script
    assert '[string]$ValidationOwner = "inner"' in script
    assert '$ValidationOwner -eq "inner"' in script


def test_expert_workflow_passes_outer_validation_owner() -> None:
    script = (ROOT / "scripts" / "run_full_expert_workflow.ps1").read_text(encoding="utf-8")

    assert "-ValidationOwner outer" in script


def test_expert_workflow_passes_mode_to_html_consistency_check() -> None:
    script = (ROOT / "scripts" / "run_full_expert_workflow.ps1").read_text(encoding="utf-8")

    assert re.search(
        r'Invoke-PythonStep -Name "Step 3/7 HTML consistency check" -Arguments @\(\s*"scripts/check_html_consistency.py",\s*"--buildings", \$buildingsArg,\s*"--mode", \$Mode\s*\)',
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

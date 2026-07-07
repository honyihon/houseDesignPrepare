## Task 4 Report: Workflow Stage And Validation Ownership Contracts

### What I implemented
- Updated `scripts/evaluate_expert_gates.py` so `--stage gate` still writes report outputs but does not update `task-board.md`.
- Added explicit `task_board_status` reporting, using `skipped for stage gate` for gate-only runs.
- Added `-ValidationOwner inner|outer|none` to `scripts/run_full_pipeline.ps1` with default `inner`.
- Kept IFC validation inside `run_full_pipeline.ps1` only when `-ValidationOwner inner`, and added explicit status messages for `outer` and `none`.
- Updated `scripts/run_full_expert_workflow.ps1` to pass `-ValidationOwner outer` into `run_full_pipeline.ps1`.
- Updated expert workflow gate/report steps to allow exit codes `@(0, 10)` and immediately preserve hard-gate exit `10`.
- Removed the now-unused JSON hard-gate polling helper from `scripts/run_full_expert_workflow.ps1`.
- Added `tests/test_workflow_contracts.py` covering validation ownership, gate-stage task-board behavior, and exit-10 handling contracts.

### What I tested and test results
- `python -m pytest tests/test_workflow_contracts.py -v`
  - Result: `4 passed`
- `powershell -NoProfile -ExecutionPolicy Bypass -Command '& { $null = [scriptblock]::Create((Get-Content -Raw ''scripts/run_full_pipeline.ps1'')); ''pipeline syntax ok'' }'`
  - Result: `pipeline syntax ok`
- `powershell -NoProfile -ExecutionPolicy Bypass -Command '& { $null = [scriptblock]::Create((Get-Content -Raw ''scripts/run_full_expert_workflow.ps1'')); ''expert workflow syntax ok'' }'`
  - Result: `expert workflow syntax ok`

### TDD evidence: RED command/output and GREEN command/output
#### RED
Command:
```powershell
python -m pytest tests/test_workflow_contracts.py -v
```

Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-8.4.2, pluggy-1.6.0 -- C:\Python314\python.exe
collecting ... collected 4 items

tests/test_workflow_contracts.py::test_run_full_pipeline_defines_validation_owner FAILED
tests/test_workflow_contracts.py::test_expert_workflow_passes_outer_validation_owner FAILED
tests/test_workflow_contracts.py::test_expert_gate_stage_does_not_update_task_board FAILED
tests/test_workflow_contracts.py::test_expert_workflow_allows_gate_exit_10_before_explicit_exit FAILED

============================== 4 failed in 0.15s ==============================
```

#### GREEN
Command:
```powershell
python -m pytest tests/test_workflow_contracts.py -v
```

Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-8.4.2, pluggy-1.6.0 -- C:\Python314\python.exe
collecting ... collected 4 items

tests/test_workflow_contracts.py::test_run_full_pipeline_defines_validation_owner PASSED
tests/test_workflow_contracts.py::test_expert_workflow_passes_outer_validation_owner PASSED
tests/test_workflow_contracts.py::test_expert_gate_stage_does_not_update_task_board PASSED
tests/test_workflow_contracts.py::test_expert_workflow_allows_gate_exit_10_before_explicit_exit PASSED

============================== 4 passed in 0.08s ==============================
```

### Files changed
- `scripts/evaluate_expert_gates.py`
- `scripts/run_full_pipeline.ps1`
- `scripts/run_full_expert_workflow.ps1`
- `tests/test_workflow_contracts.py`
- `.superpowers/sdd/task-4-report.md`

### Self-review findings
- Validation ownership is explicit now: direct pipeline runs still validate internally by default, while the documented expert workflow delegates ownership outward and validates exactly once in Step 5.
- Hard-gate failures preserve exit `10` at both the preflight gate and final report stage.
- Gate-only expert evaluation no longer mutates the task board, which matches the stage contract.
- I did not change the HTML consistency step, so exit `2` behavior remains owned by the existing script path.

### Any issues or concerns
- The focused contract tests and PowerShell syntax checks are green.
- I did not run the full end-to-end expert workflow in this task because the brief scoped verification to contract tests and syntax smoke checks.

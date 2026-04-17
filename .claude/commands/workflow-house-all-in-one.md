# /workflow-house-all-in-one

Run the full A/B/C residential workflow in one pass: requirement normalization, five-expert checks, HTML consistency, pipeline export, validation, and report generation.

## Usage

```bash
/workflow-house-all-in-one inputs/design_request.md --mode draft --buildings A,B,C --selection auto
```

## Behavior

1. Read the request markdown file.
2. Run `scripts/evaluate_expert_gates.py --stage normalize`.
3. Run expert hard gate (`--stage gate`).
4. Run HTML consistency checks.
5. Run `scripts/run_full_pipeline.ps1`.
6. Run `scripts/validate_layout_bundle.py`.
7. Run final expert report (`--stage report`) and update `task-board.md`.

## Command Mapping

Equivalent PowerShell call:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request <request_file> `
  -Mode <concept|draft|ifc> `
  -Buildings <A,B,C> `
  -Selection <auto|baseline|best>
```

## Notes

- Hard gate failures stop the workflow and require manual fixes.
- IFC mode requires `structured/expert_review/signoff.yaml` with `decision: approved`.
- Canonical input is non `_tmp` HTML only.

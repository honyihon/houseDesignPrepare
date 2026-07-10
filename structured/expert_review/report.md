# Expert Review Report

- Generated: `2026-07-10T06:12:34.875459+00:00`
- Mode: `ifc`
- Buildings: `A,B,C`
- Hard Gate: **PASS**

## Critical Failures

- None

## Warnings

- `INT-003` 需求文件應包含偏好描述（採光、收納、智能家居）。 | evidence: request missing section like '偏好' | fix: 在需求檔補上偏好與取捨說明。
- `ARCH-MET-001` Concept architect metrics found advisory or missing-data items. | evidence: generated_at=2026-07-10T02:28:49.052932+00:00; advisory=30; missing_data=8 | fix: Review structured/architect_metrics/report.md and update HTML geometry/openings or request professional calculation.

## Info Items

- `ARCH-MET-002` Architect metrics identified items requiring professional review. | evidence: generated_at=2026-07-10T02:28:49.052932+00:00; professional_required=18 | fix: Keep these items as architect/engineer confirmation tasks; do not treat concept metrics as signoff.

## Score Breakdown

- Weights: circulation=0.35, daylight=0.25, mep=0.2, fengshui=0.2
- Averages: circulation=58.98, daylight=59.14, mep=64.04, fengshui=74.96, composite=63.23
- Floors changed by expert weighting: 3

## Architect Metrics

- Evaluated floors: 12
- Status: ok=92, advisory=30, missing_data=8, professional_required=18
- Daylight avg: 1.26%; below target rooms: 25
- First issue: A:floor-1:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- Action groups:
  - owner_design_decision: 12 item(s)
  - architect_daylight_ventilation: 20 item(s)
  - accessibility_door_width: 6 item(s)
  - structural_rf_equipment: 13 item(s)

## Review Artifacts

- `normalized_request`: `structured/expert_review/request_normalized.json`
- `room_program`: `structured/room_program.json`
- `candidates`: `structured/candidates/layout_candidates.json`
- `architect_metrics`: `structured/architect_metrics/metrics.json`
- `architect_metrics_report`: `structured/architect_metrics/report.md`
- `html_consistency`: `structured/expert_review/html_consistency.json`
- `domain_checklist`: `structured/expert_review/domain_checklist.md`
- `viewer`: `structured/candidates/viewer.html`
- `pdf`: `structured/candidates/print_bundle.pdf`

## Citations

- `INT-003` ABC Design Revision Checklist 設計偏好與取捨紀錄 (https://github.com/honyihon/houseDesignPrepare/blob/main/Docs/ABC_design_revision_checklist.md)

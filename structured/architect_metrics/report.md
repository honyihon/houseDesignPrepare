# Architect Metrics Report

- Generated: `2026-07-10T02:28:49.052932+00:00`
- Schema: `architect-metrics-v1`
- Buildings: `A,B,C,STORAGE`
- Evaluated floors: **12**
- Skipped floors: **10**

## Status Summary

| Status | Count |
|---|---:|
| `ok` | 92 |
| `advisory` | 30 |
| `missing_data` | 8 |
| `professional_required` | 18 |

## Metric Types

| Metric | Count |
|---|---:|
| `daylight_factor` | 27 |
| `door_width` | 84 |
| `egress_distance_proxy` | 12 |
| `floor_area` | 12 |
| `structure_load_review` | 13 |

## Key Advisory Results

- Average concept daylight factor: `1.26%`
- Daylight-sensitive rooms below target: `25`
- Door width advisory count: `6`

## Top Issues

- A:floor-1:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- B:floor-1:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- C:floor-1:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- A:floor-1:entry:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- B:floor-1:shrine:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- C:floor-1:entrance:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-1:living:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- B:floor-2:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- C:floor-1:living:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-1:kitchen:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- B:floor-2:living2:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- C:floor-1:kitchen:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-1:flex1:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- B:floor-2:bar2:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- C:floor-1:elder:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-2:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- B:floor-2:master2:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- C:floor-1:elder-bath:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-2:master:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- B:floor-3:egress_distance_proxy - formal egress route and travel distance calculation remains professional work

## Notes

- Metrics are concept-level advisory screening only.
- Taiwan code, daylight, ventilation, egress, and structural compliance require professional calculation.
- Daylight factor adapts the Skills-Architects simplified daylight calculator method.

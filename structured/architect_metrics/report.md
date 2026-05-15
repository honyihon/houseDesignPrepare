# Architect Metrics Report

- Generated: `2026-05-15T08:34:21.152325+00:00`
- Schema: `architect-metrics-v1`
- Buildings: `A,B,C,STORAGE`
- Evaluated floors: **12**
- Skipped floors: **10**

## Status Summary

| Status | Count |
|---|---:|
| `ok` | 81 |
| `advisory` | 27 |
| `missing_data` | 31 |
| `professional_required` | 20 |

## Metric Types

| Metric | Count |
|---|---:|
| `daylight_factor` | 23 |
| `door_width` | 74 |
| `egress_distance_proxy` | 12 |
| `floor_area` | 12 |
| `structure_load_review` | 38 |

## Key Advisory Results

- Average concept daylight factor: `1.17%`
- Daylight-sensitive rooms below target: `22`
- Door width advisory count: `6`

## Top Issues

- A:floor-1::egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- A:floor-1:A:floor-1:entry:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-1:A:floor-1:living:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-1:A:floor-1:living:structure_load_review - formal structural review/signoff is required for load, anchoring, waterproofing, and maintenance path
- A:floor-1:A:floor-1:mdf:structure_load_review - formal structural review/signoff is required for load, anchoring, waterproofing, and maintenance path
- A:floor-1:A:floor-1:stair-door:structure_load_review - formal structural review/signoff is required for load, anchoring, waterproofing, and maintenance path
- A:floor-1:A:floor-1:bath1:structure_load_review - formal structural review/signoff is required for load, anchoring, waterproofing, and maintenance path
- A:floor-1:A:floor-1:kitchen:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-1:A:floor-1:flex1:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-1:A:floor-1:balcony1:structure_load_review - formal structural review/signoff is required for load, anchoring, waterproofing, and maintenance path
- A:floor-1:A:floor-1:water-inlet:structure_load_review - formal structural review/signoff is required for load, anchoring, waterproofing, and maintenance path
- A:floor-2::egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- A:floor-2:A:floor-2:master:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-2:A:floor-2:master-bath:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-2:A:floor-2:master-bath:structure_load_review - formal structural review/signoff is required for load, anchoring, waterproofing, and maintenance path
- A:floor-2:A:floor-2:study:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-2:A:floor-2:study:door_width - door width 800mm is below advisory minimum 900mm
- A:floor-2:A:floor-2:study:structure_load_review - formal structural review/signoff is required for load, anchoring, waterproofing, and maintenance path
- A:floor-2:A:floor-2:bedroom2:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- A:floor-3::egress_distance_proxy - egress proxy requires one entry marker or stair/landing cell

## Notes

- Metrics are concept-level advisory screening only.
- Taiwan code, daylight, ventilation, egress, and structural compliance require professional calculation.
- Daylight factor adapts the Skills-Architects simplified daylight calculator method.

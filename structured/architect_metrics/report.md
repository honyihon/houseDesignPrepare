# Architect Metrics Report

- Generated: `2026-10-05T07:15:22.627271+00:00`
- Schema: `architect-metrics-v1`
- Buildings: `A,B,C,STORAGE`
- Evaluated floors: **12**
- Skipped floors: **0**
- Non-floor sections: **10**

## Status Summary

| Status | Count |
|---|---:|
| `ok` | 97 |
| `advisory` | 33 |
| `missing_data` | 0 |
| `professional_required` | 25 |

## Metric Types

| Metric | Count |
|---|---:|
| `daylight_factor` | 26 |
| `door_width` | 92 |
| `egress_distance_proxy` | 12 |
| `floor_area` | 12 |
| `structure_load_review` | 13 |

## Key Advisory Results

- Average concept daylight factor: `1.7%`
- Daylight-sensitive rooms below target: `8`
- Door width advisory count: `3`

## Top Issues

- A:floor-1:floor_area - floor dimensions are auto-derived; replace with surveyed/CAD geometry
- B:floor-1:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- C:floor-1:floor_area - floor dimensions are auto-derived; replace with surveyed/CAD geometry
- A:floor-1:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- B:floor-1:entry:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- C:floor-1:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- A:floor-1:entry:daylight_factor - daylight estimate uses auto-derived geometry/openings
- B:floor-1:shrine:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- C:floor-1:entrance:daylight_factor - daylight estimate uses auto-derived geometry/openings
- A:floor-1:living:daylight_factor - daylight estimate uses auto-derived geometry/openings
- B:floor-2:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- C:floor-1:living:daylight_factor - daylight estimate uses auto-derived geometry/openings
- A:floor-1:dining:daylight_factor - daylight estimate uses auto-derived geometry/openings
- B:floor-2:stair2:door_width - door width 900mm is below advisory minimum 1000mm
- C:floor-1:dining:daylight_factor - daylight estimate uses auto-derived geometry/openings
- A:floor-1:kitchen:daylight_factor - daylight estimate uses auto-derived geometry/openings
- B:floor-2:living2:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required
- C:floor-1:kitchen:daylight_factor - daylight estimate uses auto-derived geometry/openings
- A:floor-1:flex1:daylight_factor - daylight estimate uses auto-derived geometry/openings
- B:floor-2:bar2:daylight_factor - concept daylight factor is below target; formal daylight/ventilation calculation still required

## Notes

- Metrics are concept-level advisory screening only.
- Taiwan code, daylight, ventilation, egress, and structural compliance require professional calculation.
- Daylight factor adapts the Skills-Architects simplified daylight calculator method.

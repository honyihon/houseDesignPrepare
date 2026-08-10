# Architect Metrics Report

- Generated: `2026-08-07T07:49:07.926817+00:00`
- Schema: `architect-metrics-v1`
- Buildings: `A,B,C,STORAGE`
- Evaluated floors: **12**
- Skipped floors: **0**
- Non-floor sections: **10**

## Status Summary

| Status | Count |
|---|---:|
| `ok` | 88 |
| `advisory` | 32 |
| `missing_data` | 0 |
| `professional_required` | 25 |

## Metric Types

| Metric | Count |
|---|---:|
| `daylight_factor` | 24 |
| `door_width` | 84 |
| `egress_distance_proxy` | 12 |
| `floor_area` | 12 |
| `structure_load_review` | 13 |

## Key Advisory Results

- Average concept daylight factor: `2.11%`
- Daylight-sensitive rooms below target: `0`
- Door width advisory count: `0`

## Top Issues

- A:floor-1:floor_area - floor dimensions are auto-derived; replace with surveyed/CAD geometry
- B:floor-1:floor_area - floor dimensions are auto-derived; replace with surveyed/CAD geometry
- C:floor-1:floor_area - floor dimensions are auto-derived; replace with surveyed/CAD geometry
- A:floor-1:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- B:floor-1:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- C:floor-1:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- A:floor-1:entry:daylight_factor - daylight estimate uses auto-derived geometry/openings
- B:floor-1:shrine:daylight_factor - daylight estimate uses auto-derived geometry/openings
- C:floor-1:entrance:daylight_factor - daylight estimate uses auto-derived geometry/openings
- A:floor-1:living:daylight_factor - daylight estimate uses auto-derived geometry/openings
- B:floor-2:floor_area - floor dimensions are auto-derived; replace with surveyed/CAD geometry
- C:floor-1:living:daylight_factor - daylight estimate uses auto-derived geometry/openings
- A:floor-1:dining:daylight_factor - daylight estimate uses auto-derived geometry/openings
- B:floor-2:egress_distance_proxy - formal egress route and travel distance calculation remains professional work
- C:floor-1:dining:daylight_factor - daylight estimate uses auto-derived geometry/openings
- A:floor-1:kitchen:daylight_factor - daylight estimate uses auto-derived geometry/openings
- B:floor-2:living2:daylight_factor - daylight estimate uses auto-derived geometry/openings
- C:floor-1:kitchen:daylight_factor - daylight estimate uses auto-derived geometry/openings
- A:floor-1:flex1:daylight_factor - daylight estimate uses auto-derived geometry/openings
- B:floor-2:bar2:daylight_factor - daylight estimate uses auto-derived geometry/openings

## Notes

- Metrics are concept-level advisory screening only.
- Taiwan code, daylight, ventilation, egress, and structural compliance require professional calculation.
- Daylight factor adapts the Skills-Architects simplified daylight calculator method.

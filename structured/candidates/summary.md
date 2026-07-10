# Layout Candidate Summary

- Generated at: `2026-07-10T02:28:49.434806+00:00`
- Evaluated floors: **12**

## Best Candidate by Floor

| Building | Floor | Best Strategy | Total | Circulation | Daylight | MEP |
|---|---|---:|---:|---:|---:|---:|
| A | floor-1 1F | mep | 64.86 | 59.5 | 61.93 | 72.73 |
| A | floor-2 2F | mep | 62.63 | 63.93 | 57.61 | 65.62 |
| A | floor-3 3F | mep | 61.78 | 60.83 | 66.91 | 58.33 |
| A | floor-4 RF | mep | 65.14 | 53.5 | 57.5 | 83.33 |
| B | floor-1 1F | circulation | 63.63 | 57.14 | 53.77 | 78.57 |
| B | floor-2 2F | circulation | 61.55 | 63.83 | 58.74 | 61.67 |
| B | floor-3 3F | circulation | 58.19 | 60.83 | 60.79 | 53.33 |
| B | floor-4 RF | daylight | 59.89 | 52.25 | 57.0 | 70.0 |
| C | floor-1 1F | mep | 64.36 | 63.64 | 60.74 | 68.18 |
| C | floor-2 2F | mep | 61.01 | 58.5 | 57.35 | 66.67 |
| C | floor-3 3F | circulation | 56.57 | 57.0 | 63.73 | 50.0 |
| C | floor-4 RF | circulation | 57.96 | 52.86 | 55.71 | 65.0 |

## Notes

- `baseline` uses original mapping (+ fuzzy fallback).
- `circulation/daylight/mep` are greedy strategy candidates based on weighted heuristics.
- Daylight score uses `structured/architect_metrics/metrics.json` when available, then falls back to the original outdoor-slot heuristic.
- Use this as a fast screening layer before manual architectural refinement.

# Layout Candidate Summary

- Generated at: `2026-07-23T07:14:03.971369+00:00`
- Evaluated floors: **12**

## Best Candidate by Floor

| Building | Floor | Best Strategy | Grade | Total | vs Baseline | Circulation | Daylight | MEP |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | floor-1 1F | baseline | weak | 61.31 | +0.00 | 58.95 | 50.74 | 72.73 |
| A | floor-2 2F | baseline | weak | 55.76 | +0.00 | 55.36 | 52.73 | 58.75 |
| A | floor-3 3F | baseline | weak | 54.08 | +0.00 | 56.17 | 52.53 | 53.33 |
| A | floor-4 RF | baseline | review | 67.8 | +0.00 | 56.5 | 57.5 | 87.92 |
| B | floor-1 1F | baseline | weak | 63.34 | +0.00 | 56.43 | 53.62 | 78.57 |
| B | floor-2 2F | baseline | weak | 62.92 | +0.00 | 62.67 | 58.83 | 66.67 |
| B | floor-3 3F | baseline | weak | 53.9 | +0.00 | 57.67 | 50.18 | 53.33 |
| B | floor-4 RF | baseline | weak | 58.57 | +0.00 | 53.0 | 57.0 | 65.5 |
| C | floor-1 1F | baseline | weak | 60.95 | +0.00 | 62.18 | 51.07 | 68.18 |
| C | floor-2 2F | baseline | weak | 57.25 | +0.00 | 56.33 | 57.06 | 58.33 |
| C | floor-3 3F | baseline | weak | 48.08 | +0.00 | 51.75 | 48.57 | 44.0 |
| C | floor-4 RF | baseline | weak | 57.84 | +0.00 | 52.5 | 55.71 | 65.0 |

## Low-score Review

| Floor | Weakest Dimension | Score |
|---|---|---:|
| A:floor-1 | daylight | 50.74 |
| A:floor-2 | daylight | 52.73 |
| A:floor-3 | daylight | 52.53 |
| B:floor-1 | daylight | 53.62 |
| B:floor-2 | daylight | 58.83 |
| B:floor-3 | daylight | 50.18 |
| B:floor-4 | circulation | 53.0 |
| C:floor-1 | daylight | 51.07 |
| C:floor-2 | circulation | 56.33 |
| C:floor-3 | mep | 44.0 |
| C:floor-4 | circulation | 52.5 |

## Notes

- `baseline` uses original mapping (+ fuzzy fallback).
- `circulation/daylight/mep` move only rooms without explicit source bindings; locked room-slot pairs are preserved.
- Daylight score uses `structured/architect_metrics/metrics.json` when available, then falls back to the original outdoor-slot heuristic.
- Use this as a fast screening layer before manual architectural refinement.

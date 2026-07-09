# House Workflow Quality Follow-up Design

## Goal

Reduce false-positive workflow findings, keep the expert gate consistent with HTML consistency policy, preserve presentation hatches in PDF output, and make Architect Metrics and rule citations produce traceable, actionable results.

## Scope

1. Ignore geometric overlaps whose width or height is no greater than a configurable 1 mm tolerance.
2. Keep the 1F main-entry rule as a warning while leaving upper-floor stair/landing absence as HTML consistency info only.
3. Replace SVG pattern fills with explicit solid fills and hatch paths that both browsers and `svglib` can render.
4. Trigger structural review from room/cell identity rather than arbitrary notes, remove duplicate metric labels, and balance top issues across buildings.
5. Replace placeholder rule URLs and improve accessible-space matching.

## Design Decisions

### Geometry Tolerance

`scripts/config/residential_defaults_tw.json` will define `spatial_metadata.geometry_overlap_tolerance_mm = 1.0`. `check_html_consistency.py` will calculate overlap width and height and report an overlap only when both exceed the tolerance. A real 2 mm overlap remains reportable.

### Entry Policy

The expert rule `BR-TW-002` will use `entry_ground_floor` and inspect only 1F/GF/Ground Floor plans. Upper-floor entry metadata remains useful but advisory; `check_html_consistency.py` already emits `ENTRY_COUNT_UPPER_FLOOR` as info.

### PDF-Compatible Hatches

Presentation SVGs will use the configured base room fill. Bath, service, and outdoor cells will receive explicit hatch `<path>` overlays bounded to each room rectangle. No `fill="url(#p2-...-hatch)"` values will reach `svglib`, so PDF export must complete without the current unsupported-color warnings while retaining visible hatch lines.

### Architect Metrics

Structural-review triggering will inspect the room and cell names plus an optional `structural_review` field. Notes remain evidence for deciding whether professional review language already exists, but note-only mentions such as “RF” or generic “設備” will not create a metric.

Summary labels will use `room_uid` directly when present. Top issues will be emitted round-robin by building so one building cannot consume the complete 20-item summary.

### Rule Citations and Accessibility

Regulatory accessibility links will point to the official National Land Management Agency regulation page. Project-specific interior and feng-shui heuristics will cite the repository design checklist instead of placeholder domains.

`accessible_door_min` will support a `keywords` array and inspect the full plan-cell text plus `data-accessible`. The configured aliases will include `無障礙` and `孝親`.

## Error Handling

- Unknown or missing overlap tolerance falls back to `1.0`.
- Non-presentation SVG styles remain unchanged.
- Empty structural-review identifiers do not create metrics.
- Existing single `keyword` rules remain backward compatible.

## Testing

- Unit tests cover 1 mm ignored and 2 mm reported overlap.
- Rule tests cover 1F entry failure, upper-floor exclusion, and accessible aliases.
- SVG/PDF tests verify no pattern URL remains, explicit hatch paths exist, and `svglib` emits no unsupported-color stderr.
- Architect Metrics tests cover note-only false positives, named equipment positives, non-duplicated labels, and cross-building issue balancing.
- Full pytest, concept workflow, draft workflow, bundle validation, and PDF stderr checks are required before completion.

## Non-Goals

- No canonical A/B/C room relocation or geometry redesign.
- No new PDF rendering dependency.
- No claim that advisory metrics prove regulatory compliance.
- No regeneration commit mixed with source-code commits.

## Acceptance Criteria

- Project HTML consistency has no 1 mm `CELL_OVERLAP` warnings.
- Expert report no longer warns about missing upper-floor main entries.
- Draft PDF export reports zero unsupported hatch-color warnings.
- Structure-review missing-data noise is materially reduced and top issue identifiers are not duplicated.
- No `example.com` remains in rule packs.
- All automated tests and workflow smoke checks pass.

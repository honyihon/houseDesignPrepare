# /export-final-design-html

Historical HTML workflow only. Current work is conditional preplanning, not final design adoption.
Follow AGENTS.md; missing inputs must be reported, never filled by automatically running the full pipeline.

Export canonical-first discussion HTML copies from the latest pipeline outputs without modifying canonical source HTML.

## Usage

```bash
/export-final-design-html --mode draft --buildings A,B,C --selection auto
```

## Behavior

1. Confirm these latest pipeline outputs exist:
   - `structured/room_program.json`
   - `structured/candidates/layout_candidates.json`
   - `structured/expert_review/report.json`
2. Resolve `--selection auto` the same way as the export workflow:
   - `concept` uses `best`
   - `draft` and `ifc` use `baseline`
3. Run `scripts/export_final_design_html.py`.
4. Report the generated output paths under `structured/final_design_html/`.

## Command Mapping

Equivalent PowerShell call:

```powershell
python scripts/export_final_design_html.py `
  --mode <concept|draft|ifc> `
  --selection <auto|baseline|best> `
  --buildings <A,B,C>
```

## Notes

- This command writes only to `structured/final_design_html/`.
- Canonical files such as `AbuildingView.html`, `BbuildingView.html`, and `CbuildingView.html` are not modified.
- If required outputs are missing, stop this export and report them; offer the historical workflow command for a separately authorized run, do not automatically start it.
- The final HTML keeps canonical visual room placement. The selected candidate is recorded as analysis metadata only, not applied as visible room moves.

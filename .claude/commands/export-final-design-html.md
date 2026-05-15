# /export-final-design-html

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
- If required pipeline outputs are missing, run `/workflow-house-all-in-one` first.
- The final HTML keeps canonical visual room placement. The selected candidate is recorded as analysis metadata only, not applied as visible room moves.

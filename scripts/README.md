# House Design Workflows

## Current parcel and drawing review

The confirmed 32 ping is **each parcel's land area**, not each floor's building
area. The current workflow keeps missing zoning, road, coverage, FAR and setback
facts as `unknown`; unknown is never rendered as a pass.

```bash
python3 -m house_design intake validate
python3 -m house_design drawings import --revision R001 --label "初步設計" \
  --pdf path/to/drawings.pdf --ifc path/to/model.ifc
python3 -m house_design review run --revision R001 --previous R000
```

Use `--dxf model.dxf --mapping mapping.json` when IFC is unavailable. DWG must
be exported to DXF. Outputs are written to `structured/reviews/<revision>/` as
JSON, Markdown, a printable PDF and a self-contained offline dashboard.

All rooms and equipment imported from the old briefs are `candidate` until the
owner explicitly changes them to `confirmed` or `rejected` in
`inputs/requirements.json`.

Large existing objects are recorded once in `inputs/physical-items.json`.
`intake validate` checks the register, and `intake physical-item-measure`
appends a complete measured width/depth/height set without discarding the
planning estimate or earlier measurements.

## Windows 原生 Playwright CLI 驗收

正式入口是 `scripts/check_windows_playwright.cjs`，不要再使用會消失的
`/tmp/house-windows-cli-check.cjs`。腳本預設檢查自身所在的專案，不硬編碼
WSL 發行版或 Desktop 舊目錄。需先備妥 Windows Node.js 20+、Edge（或 Chrome）
及專案 `node_modules`；不會自動安裝、要求系統管理員或更動安全設定。

在 **Windows PowerShell** 執行；下面的 `Ubuntu` 必須是實際存放最新專案的
WSL 發行版，可用 `wsl -l -q` 確認：

```powershell
$qa = '\\wsl.localhost\Ubuntu\root\workspace\houseDesignPrepare\scripts\check_windows_playwright.cjs'
Test-Path -LiteralPath $qa
node $qa --preflight
node $qa
```

若 `Test-Path` 為 `False`，先確認發行版及專案位置，不要直接執行 `node`。
如果腳本另存到 Windows，可指定 `--project '最新專案的完整路徑'`；只有三份
HTML 的舊 `D:\Desktop\houseDesign` 不會通過預檢。需要 Chrome 時加上
`--browser=chrome`。缺少專案依賴時另行在最新專案執行 `npm ci`；這只準備
Playwright 程式套件，不代表瀏覽器驗收通過。

`--preflight` 只檢查檔案，不啟動瀏覽器。完整驗收使用單一無頭瀏覽器／頁面，
依序檢查三棟十二層 HTML→3D 連結、共用尺寸與擺位、待調整家具清單、
固定比較框、停車取捨、雙折梯與冷氣配對／未核狀態、梯廳分區及牆面切換，
以及 1440×900／390×844 畫面的互動與標籤；不啟動 Python server、錄影或 trace。
另外檢查室內／外屬性、戶外家具類型及手機房間特寫／返回整層，不把標籤不重疊誤認為房內細節已清楚。
HTML 預設頁不一定是 1F；驗收會先點各層分頁並確認面板可見，再載入延遲
圖片，最後返回 1F 才點其 3D 連結，不強制顯示原本隱藏的樓層。
房間標籤以完整 `data-room`（棟別／樓層／房間）定位，並確認唯一且可見；
A、C 都有孝親房，不能只用共用文字找按鈕，也不以第一個匹配或強制點擊略過錯誤。
所有結果、CLI 紀錄及截圖都存入印出的 Windows `QA output folder`，不寫回
專案。驗收前後比對來源雜湊，來源中途變動、啟動失敗或缺結果都不判通過。
本版預檢應為 12 floors、105 rooms、129 items；會截取各樓層、A棟孝親房／一樓公衛、A／B二樓共用圖與四張衛浴／走道特寫，以及手機整層／房間特寫畫面。此前特寫自動剖視續版另加A二樓衛浴完整牆高、旋轉剖視、手機特寫，完整跑完預期27張。樓上另獨立檢查三間衛浴的完整設備、700mm操作帶、馬桶側邊本體間距、A走道櫃分時使用及兩組原尺寸衣櫃仍待排，不只比對兩張圖是否一樣。

本次C續版另加HTML基本圖／庭院比較、餐廳／客廳／廚房特寫、3D前院虛框及手機客廳／前院；完整預期44張、31份來源雜湊。獨立查面積、正常產品、照護暫留帶、TV同軸與未知前院，不只查兩張圖是否一樣，詳見[C一樓續版](../Docs/c-1f-space-use-v3.md)。

照片風格外觀v1保留上述27張，另加HTML立面、三棟各自正面／斜角、三棟合看及手機外觀，共36張。來源雜湊從25份增為30份，包含外觀JSON、原照片及三份立面SVG；預檢也核照片記錄的SHA-256。實際檢查HTML→全層外觀、正面／斜角、棟別／樓層切換、分享重載、手機返回室內，以及原剖視、展開、牆面、房間特寫與家具pending還原。外觀開口／装飾衝突保留待確認，17組室外機座標沿共用來源，不把美觀當成合規。
外觀v1的house-design-cli-lgBJsy已核對2603項／36張，是本次C重排前報告，不能替新版背書。本環境socket與Chromium受限制，C續版須Windows重跑及截圖目視。研究來源見[ABC外觀提案](../Docs/abc-facade-v1.md)；下列27／36張及126件為歷史流程，本次以44張／129件為準。
自動剖視驗收以設備本體五個取樣點檢查牆／門窗框／梯段遮擋，並實際旋轉、切完整牆高、返回整層與手機重載。剖視不得改HTML幾何、家具尺寸／位置或pending清單，也不得裁去冷氣／家具本體。取樣不等於像素可見或家具互不遮擋，仍須看截圖。
另獨立檢查 A 孝親房的床與衣櫃、150cm轉位、90cm滑門、一樓淋浴／馬桶／洗手台與公共夜間如廁路徑，不能只因兩張圖一起漏房仍一致就判通過。來源雜湊也包含需求表與CLI腳本自身。
2026-10-06 的照護回補版 `house-design-cli-WHIoXY` 已核對：Windows Edge 1799項檢查通過，
25個受驗收來源雜湊與當時版本一致，18張截圖已目視複查；手機選房、特寫、
重載還原與返回整層均完成。這是樓上重排前的歷史證據；本續版改過來源、viewer及CLI，須重新執行並目視複查，不能沿用舊passed。仍有兩組衣櫃與其他未解需求，不因CLI passed就視為全棟可施工。
`house-design-cli-kgqbHV` 是樓上續版的部分failed報告：430項已記錄檢查通過，A二樓走道特寫的使用限制檢查失敗。原因是3D房間資訊未輸出共同資料的家具備註，並非將尺寸或擺位驗成失敗；B／C與手機流程尚未跑到。已補房間／逐件限制及對應來源比對，仍保留原走道分時使用斷言。新版四張樓上特寫會先捲動至房間資訊，讓截圖包含限制說明；需重新跑完，不沿用部分報告當passed。
其後 `house-design-cli-EHN6RW` 的1877項自動檢查、25個當時來源雜湊及24張截圖已核對；走道限制正常顯示，但A二樓衛浴本體仍被鄰房高牆遮擋。此報告是最新自動剖視改動前的歷史證據，不代表27張截圖版已通過；須重新執行相同Windows命令。
自動剖視版 `house-design-cli-FGNn3E` 為1924項通過／1項失敗：末段手機A衛浴檢查誤將2F房間數寫為9，共用資料實際是10；先前整層房間ID／尺寸、兩組衣櫃pending及手機衛浴本體視線均通過。已改用共用房間ID集合比對，保留兩座特定衣櫃的1800 × 600 × 2200mm尺寸與隱藏狀態檢查，不改房屋圖。手機收合改為讀取狀態後設定，避免同頁hash切換把已收合面板反向展開，並等待畫布resize。這份failed仍是部分證據，修正後須重新執行相同命令；預期27張不變。
詳細證據與限制見 [ABC 合理性提案](../Docs/abc-layout-rationality-v2.md#未解與驗證)。
105 rooms／126 items 的 `house-design-cli-yh8nGv` 在手機選房前已完成1785項檢查，
但舊文字定位同時匹配A、C孝親房而中斷；屬部分證據，不是完整通過。
定位修正後已由上述新報告完成重跑，舊failed報告不能替代新報告。
106 rooms／126 items 的 `house-design-cli-hzNQgd` 是回補前報告，不適用目前 A 照護回補版。
106 rooms／128 items 報告對應截圖修正前版本，不能驗證目前已移除露台室內家具及修正造型的版本。
舊版 92 rooms／157 items 的通過報告不能驗證 ABC v2。
只關閉本次命名 session，不影響其他瀏覽器 session。

`passed` 只代表自動瀏覽器檢查通過，仍須看截圖；不是家具動線、建築容量、
法規或風水核定。回傳 `result.json`、錯誤紀錄或輸出目錄，才能繼續人工檢視。

## Historical HTML layout extraction

## Purpose

Convert the static building HTML pages into structured JSON files for downstream automation
(layout scoring, auto-plan generation, prompt input, etc.).

## Input Files

- `AbuildingView.html`
- `BbuildingView.html`
- `CbuildingView.html`
- `storage.html`

## Output Directory

- `structured/`
  - `AbuildingView.structured.json`
  - `BbuildingView.structured.json`
  - `CbuildingView.structured.json`
  - `storage.structured.json`
  - `index.json`

## Run

```bash
python scripts/extract_layout_data.py
python scripts/build_room_program.py
python scripts/evaluate_architect_metrics.py
python scripts/generate_layout_candidates.py
python scripts/render_candidate_viewer.py
python scripts/export_top1_svgs.py
python scripts/export_print_bundle_pdf.py
```

## One-Click Run (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1
```

## Incremental CLI

The package entrypoint hashes each step's command and inputs. Unchanged steps
with existing outputs are skipped automatically:

```bash
python -m house_design pipeline --mode concept
python -m house_design pipeline --mode draft --from-step candidates --to-step svg
python -m house_design pipeline --mode release --force
```

Options:

- `--force`: ignore the local cache and rerun the selected range.
- `--from-step` / `--to-step`: run only part of the pipeline.
- `--selection`, `--style`, `--paper`, `--output`: control generated artifacts.

The local cache is stored in `.house-design-cache.json` and is not committed.
Cache records include output hashes; SVG files listed by the manifest are
checked individually, and PDF fingerprints include SVG contents.
The PowerShell entrypoint remains available for compatibility and expert workflows.

Common options:

```powershell
# Export A4 bundle
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Paper a4 -Output structured/candidates/print_bundle_a4.pdf

# Fast concept iteration (no PDF, safe auto selection=baseline)
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Mode concept

# Draft bundle (default mode, auto selection=baseline)
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Mode draft

# Historical release gate (full export + validation; not IFC import or professional approval)
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Mode ifc

# Force specific candidate selection
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Selection best

# Use a specific Python executable
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -PythonExe py
```

## One-Click Expert Workflow (A/B/C + 5 Experts)

This is the all-in-one entrypoint for:
- requirement normalization
- expert hard gates (regulation/accessibility)
- HTML consistency checks
- pipeline export
- validation
- report + task-board update

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
  -Selection auto
```

Interface:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request <path/to/request.md> `
  -Mode <concept|draft|ifc> `
  -Buildings <A,B,C> `
  -Selection <auto|baseline|best> `
  -Paper <a3|a4> `
  -Output <output/pdf/path> `
  -PythonExe <python>
```

Key outputs:
- `structured/expert_review/report.json`
- `structured/expert_review/report.md`
- `structured/expert_review/request_normalized.json`
- `structured/expert_review/html_consistency.json`
- `structured/expert_review/domain_checklist.json`
- `structured/expert_review/domain_checklist.md`
- `structured/historical/html-workflow-task-board.md`（只記錄前身 HTML workflow）

## Dependency

```bash
python -m pip install --user beautifulsoup4
python -m pip install --user reportlab svglib
```

## Output for Step 2

After running `build_room_program.py`, you'll get:

- `structured/room_program.json`

This file unifies all buildings into one normalized schema:
- building/floor hierarchy
- room list with area parsing (`坪`, `m × m`)
- plan-cell mapping to rooms
- tables/checklists/section bullets converted into constraints

## Output for Architect Metrics

After running `evaluate_architect_metrics.py`, you'll get:

- `structured/architect_metrics/metrics.json`
- `structured/architect_metrics/report.md`

This advisory layer adds concept-level daylight, door width, floor area, egress proxy, and structure-review metadata. It does not replace Taiwan code, daylight, ventilation, egress, or structural professional calculations.

## Output for Step 3

After running `generate_layout_candidates.py`, you'll get:

- `structured/candidates/layout_candidates.json`
- `structured/candidates/summary.md`

Each evaluated floor includes:
- `baseline`, `circulation`, `daylight`, `mep` candidates
- per-candidate scores (`circulation`, `daylight`, `mep`, `utilization`, `total`)
- room-slot assignment details and unplaced/unassigned lists
- daylight fit from `structured/architect_metrics/metrics.json` when available, with fallback to the original outdoor-slot heuristic

## Output for Step 4

After running `render_candidate_viewer.py`, you'll get:

- `structured/candidates/viewer.html`

This page provides:
- floor selection
- candidate switching (ranked list)
- slot-to-room visual mapping
- score bars and rationale / unplaced room summaries

## Output for Step 5

After running `export_top1_svgs.py`, you'll get:

- `structured/candidates/svg/*.svg` (one Top1 SVG per evaluated floor)
- `structured/candidates/svg/manifest.json`
- `structured/candidates/svg/index.html`

This is suitable for sharing with designers/contractors as static deliverables.
SVG filenames are stable: `<building>_<floor>.svg`. The manifest records `candidate_selection`, `requested_selection`, `resolved_selection`, and each export's `selected_candidate_id` / `selected_strategy`, so candidate strategy changes should not churn filenames.
Round-2 annotations are included by default:
- window symbols (`WIN:`)
- dimension chains (`DIM:`)
- material legend (`LEGEND:`)
- elevation index (`ELEV:A-A`, `ELEV:B-B`)
- north arrow (`N↑`)

Default export mode uses `baseline` candidate mapping (closer to original floor plan intent).
To export heuristic best-score mapping instead:

```bash
python scripts/export_top1_svgs.py --selection best
```

## Output for Step 6

After running `export_print_bundle_pdf.py`, you'll get:

- `structured/candidates/print_bundle.pdf`

By default, this PDF is exported in A3 landscape and includes:
- cover page
- table of contents
- one floor layout per page (from `structured/candidates/svg/manifest.json`)

Optional arguments:
- `--paper a4` to output A4 landscape
- `--output <path>` to change destination file
- `--manifest <path>` to use a different SVG manifest

## Quality Gate

You can run validation manually:

```bash
python scripts/validate_layout_bundle.py
```

Checks include:
- `room_program.json` metadata / notes coverage
- exported SVG file existence
- required drawing markers (`ENT`, `DW:`, `WIN:`, `DIM:`, `LEGEND:`, `ELEV:`)

## Spatial Metadata Contract

Directional metadata is optional and backward-compatible:

- `.floor-plan`: `data-front-side`, `data-rear-side`, `data-site-orientation-note`
- `.plan-cell`: `data-zone`, `data-facing`, `data-outdoor-role`

`top/right/bottom/left` refer to the HTML visual grid, not geographic north. `data-north-deg` remains the geographic orientation input.

Extraction emits `house-design-structured-v3` when spatial metadata support is active. Downstream scripts accept both `house-design-structured-v2` and `house-design-structured-v3` during migration.

Room-program records expose `record_type=floor|section`. Metrics and candidate
generation report non-floor sections separately instead of treating overview
or specification content as skipped floors.

SVG validation parses XML and checks rendered `data-marker` groups for
entrances, doors, windows, and optional elevation indices. Marker strings in
`<metadata>` do not satisfy drawing validation.

## Shared Defaults Config

Default assumptions are centralized in:

- `scripts/config/residential_defaults_tw.json`

This file drives:
- wall / door / furniture defaults
- px-per-mm conversion
- drawing validation markers

## Improve Precision from Source HTML

You can make final SVG/PDF much closer to real drawings by adding geometry attributes in original HTML.

Supported attributes:
- floor: `.floor-plan`
  - `data-floor-width-mm`, `data-floor-depth-mm`, `data-north-deg`, `data-geometry-source`
- plan cell: `.plan-cell`
  - `data-x-mm`, `data-y-mm`, `data-w-mm`, `data-h-mm`
  - `data-door-mm`, `data-window-mm`
  - `data-entry="true"` for main entrance
  - `data-material` (optional material hint)
- room: `.room`
  - `data-x-mm`, `data-y-mm`, `data-w-mm`, `data-h-mm`
  - `data-target-cell="slot-<n>"` (optional binding hint)

Example:

```html
<div class="floor-plan" id="floor-1" data-floor-width-mm="11000" data-floor-depth-mm="7800" data-north-deg="0">
  <div class="plan-cell" data-x-mm="3600" data-y-mm="1200" data-w-mm="7400" data-h-mm="1300"
       data-door-mm="900" data-window-mm="1800">...</div>
</div>
```

When all cells on a floor provide `x/y/w/h` (mm), export enters `blueprint-precise-mm` mode.

## Prompt Templates

For daily HTML-design revisions that must convert to realistic plan drawings, use:

- `scripts/WEB_TO_PLAN_PROMPTS.zh-TW.md`
- `scripts/WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md`

This pack includes:
- single master prompt for end-to-end execution
- fixed failure response format
- fallback prompt when slash command is unavailable

## Troubleshooting

### 1) Rule citation issue (`citation_issues`)

Symptom:
- `report.json` shows `citation_issues`

Meaning:
- A `critical` rule is missing one or more of:
  - `source_doc`
  - `source_article`
  - `source_url`

Fix:
- Update the rule file under `scripts/rules/*.yaml`.
- Without full citations, that critical rule cannot become a hard gate.

### 2) IFC signoff missing

Symptom:
- `run_full_expert_workflow.ps1 -Mode ifc` exits `2` because signoff is missing or stale

Fix:
- Create `structured/expert_review/signoff.yaml` from `structured/expert_review/signoff.template.yaml`
- Set:
  - `decision: approved`
  - reviewer metadata
  - `related_report_hash` copied from the latest `structured/expert_review/report.json`
  - `related_report_generated_at` copied from the same report

Two-pass IFC flow:
1. Run `-Mode ifc` once to generate the latest report.
2. Review `structured/expert_review/report.md`.
3. Copy `report_hash` into `signoff.yaml` as `related_report_hash`.
4. Rerun `-Mode ifc`.

### 3) HTML mapping mismatch (`highlightRoom` / `room-id`)

Symptom:
- `html_consistency.json` contains `ROOM_TARGET_MISMATCH`

Fix:
- Ensure each `onclick="highlightRoom('xxx', this)"` matches `id="room-xxx"`.
- Keep DOM skeleton unchanged:
  - `.floor-plan > .plan-grid-visual > .plan-row > .plan-cell`

## Claude Code MCP (WSL)

Project-level MCP config is in:
- `.mcp.json`

Included MCP servers:
- `playwright` (browser navigation/scraping)
- `brave-search` (web search API)

### WSL setup

1. Prepare env vars:

```bash
cp .env.mcp.example .env.mcp
# edit .env.mcp and set BRAVE_API_KEY
source .env.mcp
```

2. Start Claude Code from this project root so it picks up `.mcp.json`.

3. Verify in Claude Code:
- MCP server list should include `playwright` and `brave-search`.
- Ask Claude to run a quick web lookup (for example a recent regulation update) and cite sources.

### Notes

- If `BRAVE_API_KEY` is missing, `brave-search` may fail to start; `playwright` can still be used for manual web browsing tasks.
- This repo keeps MCP settings at project scope (no global machine-level config required).

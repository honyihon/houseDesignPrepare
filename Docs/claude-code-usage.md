# Claude Code 指令使用教學

適用 repo：`D:\I29786\workspace\houseDesignPrepare`  
更新日期：2026-05-15

這份文件整理本專案的 Claude Code 設定、自訂 slash command、等效 PowerShell 指令，以及日常設計/出圖流程的建議用法。本專案主要用途是把 A/B/C 棟與儲藏空間的 HTML 平面配置轉成結構化 JSON，再產生建築計算輔助、候選配置、SVG 圖面、PDF bundle 與專家審查報告。

## 目前 Claude Code 設定

本 repo 目前有下列 Claude Code 相關檔案：

| 檔案 | 用途 |
|---|---|
| `CLAUDE.md` | Claude Code 進入 repo 後的常駐專案規則與 pipeline 說明 |
| `.claude/commands/workflow-house-all-in-one.md` | 自訂 slash command，對應 `/workflow-house-all-in-one` |
| `.claude/commands/export-final-design-html.md` | 自訂 slash command，對應 `/export-final-design-html` |
| `.claude/settings.local.json` | 本機啟用 MCP server 設定，目前啟用 `playwright`、`brave-search` |
| `.mcp.json` | project-level MCP server 定義，包含 `playwright` 與 `brave-search` |
| `.env.mcp.example` | Brave Search API key 的本機環境變數範本 |

目前真正可直接在 Claude Code 輸入的專案自訂 slash command 是：

```text
/workflow-house-all-in-one
/export-final-design-html
```

其餘指令是該 slash command 背後呼叫的 PowerShell 或 Python 腳本，也可以手動在終端機執行。

## 啟動方式

建議從專案根目錄啟動 Claude Code，讓它自動讀到 `CLAUDE.md`、`.claude/commands` 與 `.mcp.json`。

```powershell
cd D:\I29786\workspace\houseDesignPrepare
claude
```

進入 Claude Code 後可先檢查 MCP 狀態：

```text
/mcp
```

或在一般終端機執行：

```powershell
claude mcp list
```

## 第一次本機設定

本專案的 MCP 設定包含：

- `playwright`：瀏覽器操作與頁面檢查。
- `brave-search`：外部搜尋；需要 `BRAVE_API_KEY`。

在 WSL 或 bash 類環境可依範本建立環境變數檔：

```bash
cp .env.mcp.example .env.mcp
# 編輯 .env.mcp，填入 BRAVE_API_KEY
source .env.mcp
```

Windows PowerShell 若要啟用 Brave Search，可在啟動 Claude Code 前設定：

```powershell
$env:BRAVE_API_KEY = "your_brave_api_key_here"
cd D:\I29786\workspace\houseDesignPrepare
claude
```

如果沒有 `BRAVE_API_KEY`，`brave-search` 可能無法啟動；`playwright` 仍可用於瀏覽器驗證。

## 核心 Slash Command

### `/workflow-house-all-in-one`

用途：一次跑完整 A/B/C 住宅設計 workflow，包含需求標準化、專家 gate、HTML 一致性、出圖 pipeline、驗證、報告與 task board 更新。
流程成功時也會輸出一份不覆蓋原檔的 final design HTML 討論版。

Claude Code 內使用：

```text
/workflow-house-all-in-one inputs/design_request.md --mode draft --buildings A,B,C --selection auto --drawing-style presentation
```

等效 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

建議日常優先使用這個入口，因為它會把專家檢查、HTML 一致性與出圖驗證串在一起。

## Workflow Contracts

Exit codes:

| Exit code | Meaning |
|---:|---|
| `0` | Step completed successfully |
| `1` | Unexpected runtime error |
| `2` | Validation, consistency, or argument-level failure that is not an expert hard gate |
| `10` | Expert hard gate failed with eligible critical failure |

Validation ownership:

- Direct `scripts/run_full_pipeline.ps1` execution defaults to `-ValidationOwner inner`.
- `/workflow-house-all-in-one` passes `-ValidationOwner outer` and runs `validate_layout_bundle.py` exactly once after the pipeline.
- `-ValidationOwner none` is for targeted developer/debug commands only.

HTML consistency:

- Critical issues stop the workflow with exit code `2`.
- Warning-only and info-only reports exit `0`, but warning counts remain visible in `structured/expert_review/html_consistency.json`.
- Outdoor-like cells with `data-outdoor-role` do not require `data-window-mm` unless configured as opening-required roles.

### `/export-final-design-html`

用途：從最近一次 pipeline 產物產生 canonical-first final design HTML 討論版副本。畫面保留原 HTML 的格位、房名、`onclick` 與幾何，最後 selection 只作候選分析摘要與 AI 可讀 JSON metadata。

Claude Code 內使用：

```text
/export-final-design-html --mode draft --buildings A,B,C --selection auto
```

等效 PowerShell：

```powershell
python scripts/export_final_design_html.py `
  --mode draft `
  --selection auto `
  --buildings A,B,C
```

輸出位置：

```text
structured/final_design_html/index.html
structured/final_design_html/AbuildingView.final.html
structured/final_design_html/BbuildingView.final.html
structured/final_design_html/CbuildingView.final.html
structured/final_design_html/manifest.json
```

這個指令只讀取 canonical HTML 與 `structured/` 產物，不會修改 `AbuildingView.html`、`BbuildingView.html`、`CbuildingView.html`，也不會把候選配置 assignment 套成可視房間搬位。

## 參數說明

| 參數 | 可用值 | 說明 |
|---|---|---|
| `Request` / 第一個位置參數 | 例如 `inputs/design_request.md` | 設計需求 Markdown，建議每次改版前先更新 |
| `Mode` / `--mode` | `concept`、`draft`、`ifc` | 流程嚴謹度與輸出層級 |
| `Buildings` / `--buildings` | `A`、`B`、`C`，可逗號分隔 | 要檢查的棟別，預設通常用 `A,B,C` |
| `Selection` / `--selection` | `auto`、`baseline`、`best` | SVG/PDF 選用的候選配置 |
| `DrawingStyle` / `--drawing-style` | `presentation`、`technical`、`debug` | SVG/PDF 圖面風格，預設 `presentation` |
| `Paper` | `a3`、`a4` | PDF 紙張大小，預設 `a3` |
| `Output` | PDF 路徑 | 預設 `structured/candidates/print_bundle.pdf` |
| `PythonExe` | 例如 `python`、`py` | 指定 Python 可執行檔 |

`Selection auto` 的實際行為：

- `concept` 模式會自動使用 `best`，適合快速比較演算法評分最高的配置。
- `draft` 與 `ifc` 模式會自動使用 `baseline`，較貼近原始圖面意圖。

`DrawingStyle` 的實際用途：

- `presentation`：預設交付圖，低飽和分類底色、少標籤、適合討論與列印。
- `technical`：保留 DW/WIN/DIM/ELEV 等門窗、尺寸與立面索引標註。
- `debug`：保留 strategy、fit、notes、右側 legend 等演算法檢查資訊。

`presentation` 目前是 v2 版圖面樣式：白底圖紙、淡灰圖框、小型 title block、置中房名、淡 hatch 材質、低透明家具，以及底部極簡 legend。過長或過小的房名會改成 `R1`、`R2` 這類短碼，對照表寫在圖面底部與 `manifest.json` 的 `compact_label_count` / `compact_labels`。

外部工具評估結論：OpenPlans、OpenPlan3D、Konva 可列為後續 renderer spike；BuildFloorPlan、Archilogic MCP、Blender MCP 偏外部服務、概念生成、資料查詢或 3D/BIM，不建議作為目前本地 SVG/PDF 主線。

## Mode 使用建議

| 情境 | 建議 mode | 原因 |
|---|---|---|
| 快速檢查 HTML 或規則改動 | `concept` | 不輸出 PDF，速度較快 |
| 日常設計版交付 | `draft` | 會輸出 SVG 與 PDF bundle |
| 最終放行或類 IFC 檢查 | `ifc` | 會跑完整驗證，且需要 signoff |

常用範例：

```powershell
# 快速概念檢查，不產 PDF
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode concept `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation

# 日常草圖交付，產生預設 A3 PDF
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation

# 只檢查 A 棟
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A `
  -Selection auto `
  -DrawingStyle presentation

# 輸出 A4 PDF
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
  -DrawingStyle presentation `
  -Paper a4 `
  -Output structured/candidates/print_bundle_a4.pdf
```

`ifc` 模式需要先準備：

```text
structured/expert_review/signoff.yaml
```

可從範本複製：

```powershell
Copy-Item structured\expert_review\signoff.template.yaml structured\expert_review\signoff.yaml
```

至少需設定有效 decision：

```yaml
decision: approved
```

也可使用 `pass` 或 `approved_with_conditions`。

## 一鍵流程做了什麼

`/workflow-house-all-in-one` 對應的 `scripts/run_full_expert_workflow.ps1` 會依序執行：

1. `evaluate_expert_gates.py --stage normalize`  
   將 `inputs/design_request.md` 標準化成 `structured/expert_review/request_normalized.json`。

2. `evaluate_expert_gates.py --stage gate`  
   執行專家規則 preflight gate。若有具引用來源的 `critical` 失敗，流程會停止並回傳 exit code `10`。

3. `check_html_consistency.py`  
   檢查 A/B/C canonical HTML 的幾何欄位、入口數量、房間對應與尺寸範圍。

4. `run_full_pipeline.ps1`  
   執行 HTML 轉 JSON、建築計算輔助、候選配置、viewer、SVG、PDF 等主管線。

5. `validate_layout_bundle.py`  
   驗證 `room_program.json`、SVG manifest 與必要圖面標記。

6. `evaluate_expert_gates.py --stage report`  
   產出最終審查報告，並更新 `task-board.md` 的 last run 區塊。

7. `export_final_design_html.py`  
   產出 `structured/final_design_html/` 討論版 HTML 副本；畫面保留 canonical HTML，最後 selection 只進候選分析摘要與 metadata。

## 新增功能：建築計算輔助

本專案已加入 `Architect Metrics` 計算輔助層，將 `Skills-Architects` 的 calculator 思路接進本地 pipeline。它會從 `structured/room_program.json` 讀取 A/B/C 棟樓層、房間、格位幾何、門窗尺寸，產生概念級檢核結果。

這個功能會檢查：

- 採光概念值：使用簡化 daylight factor 估算，並產生窗地比、概念採光係數與 target 比較。
- 門寬：依入口、一般室內門、衛浴、設備/服務空間做 advisory 檢查。
- 樓層面積：由 `data-floor-width-mm`、`data-floor-depth-mm` 推算。
- 逃生距離 proxy：用入口、樓梯、走廊或玄關到各格位中心的直線距離做早期風險提示。
- RF/設備/運動區等結構載重文字完整性：只提醒需要結構技師確認，不做結構安全判定。

重要限制：

- 這些結果是 `advisory`，不是法規通過證明。
- 台灣法規 hard gate 仍以 `scripts/rules/*.yaml` 與專業確認為準。
- 採光、通風、逃生距離、樓梯、RF 載重、設備錨定仍需建築師、法規或結構技師正式計算。
- 報告中不應把 `Architect Metrics` 寫成「已通過法規」。

### 如何執行

一般使用者不需要單獨執行，因為 `run_full_pipeline.ps1` 已經會自動跑：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Mode concept -Selection best -DrawingStyle presentation
```

若只想更新建築計算輔助，可手動執行：

```powershell
python scripts/evaluate_architect_metrics.py
```

指定棟別：

```powershell
python scripts/evaluate_architect_metrics.py --buildings A,B,C
```

輸出檔：

| 檔案 | 說明 |
|---|---|
| `structured/architect_metrics/metrics.json` | 機器可讀的計算結果，schema 為 `architect-metrics-v1` |
| `structured/architect_metrics/report.md` | 人可讀摘要，列出 status 統計、採光概念結果、門寬提示與 top issues |

### Status 解讀

| Status | 意義 |
|---|---|
| `ok` | 概念資料足夠，且 advisory 檢查未發現明顯問題 |
| `advisory` | 有設計提醒，例如採光概念值低於 target、門寬低於建議值 |
| `missing_data` | 缺少幾何、門窗、入口、樓梯或其他必要 metadata |
| `professional_required` | 必須由建築師、法規、空調、水電或結構技師正式確認 |

目前 `report.md` 會呈現類似摘要：

```text
Evaluated floors: 12
Skipped floors: 10
Metric types: daylight_factor, door_width, egress_distance_proxy, floor_area, structure_load_review
```

`storage` 目前沒有 `plan_cells`，會被列為 skipped，這是預期行為。

### 對候選配置分數的影響

`generate_layout_candidates.py` 會優先讀取：

```text
structured/architect_metrics/metrics.json
```

如果某房間有 `daylight_factor` 結果，候選配置的 daylight score 會使用該概念採光分數；若沒有資料，才回到舊的 `outdoor` 格位 heuristic。

可在下列檔案確認是否有讀到新資料：

```text
structured/candidates/layout_candidates.json
```

檢查欄位：

```json
"architect_metrics_status": "loaded",
"architect_daylight_metric_count": 22
```

每個 candidate 的 `pair_details` 也會標示 daylight 來源：

```json
"dimension_fit_sources": {
  "daylight": "architect_metrics:daylight_factor"
}
```

### 對專家報告的影響

`evaluate_expert_gates.py` 會把 Architect Metrics 摘要放進：

```text
structured/expert_review/report.md
```

新增章節：

```text
## Architect Metrics
```

若有 `advisory` 或 `missing_data`，會加入 warning；若有 `professional_required`，會加入 info。這些都不會變成 hard gate failure。

## 重要輸出檔

| 檔案 | 說明 |
|---|---|
| `structured/expert_review/request_normalized.json` | 標準化後的需求 |
| `structured/expert_review/html_consistency.json` | HTML 一致性檢查結果 |
| `structured/expert_review/report.json` | 機器可讀專家審查報告 |
| `structured/expert_review/report.md` | 人可讀專家審查報告 |
| `structured/room_program.json` | 整合後的棟別/樓層/房間資料 |
| `structured/architect_metrics/metrics.json` | 建築計算輔助 JSON，供候選配置採光分數與專家報告引用 |
| `structured/architect_metrics/report.md` | 建築計算輔助摘要報告 |
| `structured/candidates/layout_candidates.json` | 各樓層候選配置與分數 |
| `structured/candidates/summary.md` | 候選配置摘要 |
| `structured/candidates/viewer.html` | 可切換樓層與候選配置的瀏覽器檢視 |
| `structured/candidates/svg/index.html` | SVG 圖面索引 |
| `structured/candidates/svg/manifest.json` | SVG 匯出摘要，包含 `candidate_selection`、`drawing_style`、`presentation_version` 與 `compact_label_count` |
| `structured/candidates/print_bundle.pdf` | PDF 圖面 bundle，`concept` 模式不產生 |
| `structured/final_design_html/*.final.html` | canonical-first HTML 討論版副本，不覆蓋 canonical HTML，也不搬動可視房間格位 |
| `structured/final_design_html/manifest.json` | final HTML 匯出摘要，包含 `sync_mode`、selection、report hash、候選 assignment 與 rejected visual moves 統計 |
| `task-board.md` | 自動更新 last run 摘要 |

## 手動 Pipeline 指令

若不需要專家 gate，只想跑一般出圖 pipeline：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1
```

常用選項：

```powershell
# 快速概念模式，不產 PDF
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Mode concept

# 草圖模式，預設會產 PDF
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Mode draft

# 完整驗證模式
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Mode ifc

# 強制選用最佳評分候選配置
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Selection best

# 改用 technical 或 debug 圖面風格
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -DrawingStyle technical
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -DrawingStyle debug

# 重建 presentation v2 SVG
python scripts/export_top1_svgs.py --selection best --style presentation

# 指定 Python launcher
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -PythonExe py
```

也可逐步執行：

```powershell
python scripts/extract_layout_data.py
python scripts/build_room_program.py
python scripts/evaluate_architect_metrics.py
python scripts/generate_layout_candidates.py
python scripts/render_candidate_viewer.py
python scripts/export_top1_svgs.py --selection baseline --style presentation
python scripts/export_print_bundle_pdf.py --paper a3 --output structured/candidates/print_bundle.pdf
python scripts/validate_layout_bundle.py
python scripts/export_final_design_html.py --mode draft --selection baseline --buildings A,B,C
```

注意：部分 Python 腳本沒有 `--help` 模式，直接執行就會重新產生 `structured/` 產物。

若只想用最近一次產物重建 final HTML 討論版：

```powershell
python scripts/export_final_design_html.py --mode concept --selection best --buildings A,B,C
```

## 常用檢查指令

只做 HTML 一致性檢查：

```powershell
python scripts/check_html_consistency.py --buildings A,B,C
```

只做專家 gate：

```powershell
python scripts/evaluate_expert_gates.py `
  --stage gate `
  --request inputs/design_request.md `
  --buildings A,B,C `
  --mode draft `
  --selection baseline
```

只做最終報告：

```powershell
python scripts/evaluate_expert_gates.py `
  --stage report `
  --request inputs/design_request.md `
  --buildings A,B,C `
  --mode draft `
  --selection baseline
```

只驗證出圖 bundle：

```powershell
python scripts/validate_layout_bundle.py
```

## HTML 修改規則

本專案的正式輸入是 canonical HTML：

- `AbuildingView.html`
- `BbuildingView.html`
- `CbuildingView.html`
- `storage.html`

不要把 `*_tmp.html` 當正式輸入；pipeline 也只讀非 `_tmp` 檔案。

`structured/final_design_html/*.final.html` 是 canonical-first 討論版副本，會保留原 HTML 的可視格位、房名、`onclick` 與幾何；候選 selection 只會寫進摘要與 JSON metadata，方便人看與 AI 讀。它不是下一次 pipeline 的正式輸入，也不會覆蓋 canonical HTML。

修改 HTML 時要保留 DOM 骨架：

```text
.floor-plan > .plan-grid-visual > .plan-row > .plan-cell
```

幾何資料以 mm 欄位為準：

```html
data-floor-width-mm
data-floor-depth-mm
data-x-mm
data-y-mm
data-w-mm
data-h-mm
data-door-mm
data-window-mm
data-entry="true"
```

同一樓層理想上只能有一個主入口：

```html
data-entry="true"
```

房間綁定要同步：

```html
onclick="highlightRoom('xxx', this)"
id="room-xxx"
```

修改 HTML 後至少跑一次：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode concept `
  -Buildings A,B,C `
  -Selection auto
```

## 失敗處理

### Hard gate fail

症狀：`run_full_expert_workflow.ps1` 顯示 hard gate failed，或 exit code 為 `10`。

處理：

1. 打開 `structured/expert_review/report.md`。
2. 查看 `Critical Failures`。
3. 依 `fix_hint` 修正 HTML、需求或 rules。
4. 重跑同一個 `/workflow-house-all-in-one` 或 PowerShell 命令。

### HTML consistency critical

症狀：`check_html_consistency.py` 回報 critical。

處理：

1. 打開 `structured/expert_review/html_consistency.json`。
2. 依 `code`、`file`、`floor_id`、`evidence` 定位問題。
3. 常見修正是補齊 `data-x-mm/y-mm/w-mm/h-mm`，或修正 `highlightRoom` 與 `room-xxx` 對應。

### IFC signoff missing

症狀：`-Mode ifc` 失敗並提示缺少 signoff。

處理：

```powershell
Copy-Item structured\expert_review\signoff.template.yaml structured\expert_review\signoff.yaml
```

再填入：

```yaml
decision: approved
reviewer_role: owner
reviewer_name: <name>
date: 2026-04-28
```

### MCP 無法啟動

先檢查：

```text
/mcp
```

再確認：

- 是否從 `D:\I29786\workspace\houseDesignPrepare` 啟動 Claude Code。
- Node / npx 是否可用。
- 使用 `brave-search` 時是否已設定 `BRAVE_API_KEY`。

## 建議工作流

日常設計調整：

```text
1. 更新 inputs/design_request.md
2. 請 Claude Code 修改 canonical HTML，不改 *_tmp.html
3. 執行 /workflow-house-all-in-one inputs/design_request.md --mode concept --buildings A,B,C --selection auto --drawing-style presentation
4. 修正 gate 或 consistency 問題
5. 打開 structured/final_design_html/index.html 討論最後配置重點
6. 執行 draft 產出 PDF
```

交付草圖：

```text
/workflow-house-all-in-one inputs/design_request.md --mode draft --buildings A,B,C --selection auto --drawing-style presentation
```

流程完成後可直接打開：

```text
structured/final_design_html/index.html
```

這裡的 `*.final.html` 會保留原設計視覺格位，並附上最後出圖 selection 的候選分析，適合拿來跟人討論或交給 AI 讀重點。

最終放行：

```text
1. 檢查 report.md 與 viewer.html
2. 建立 structured/expert_review/signoff.yaml
3. 執行 /workflow-house-all-in-one inputs/design_request.md --mode ifc --buildings A,B,C --selection auto --drawing-style presentation
```

## 備援 Prompt

如果 Claude Code 看不到 `/workflow-house-all-in-one`，可直接貼：

```text
請依照 scripts/WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md 執行 houseDesignPrepare 的一鍵全流程。

輸入：
- request_file: inputs/design_request.md
- mode: draft
- buildings: A,B,C
- selection: auto
- drawing_style: presentation

限制：
- 僅使用非 _tmp HTML。
- critical hard gate 失敗要停止。
- 回報 report.json、report.md、viewer.html、print_bundle.pdf 路徑。
```

也可以直接打開下列 prompt 文件使用：

- `scripts/WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md`
- `scripts/WEB_TO_PLAN_PROMPTS.zh-TW.md`

# Claude Code 指令使用教學

適用 repo：`D:\I29786\workspace\houseDesignPrepare`  
更新日期：2026-04-28

這份文件整理本專案的 Claude Code 設定、自訂 slash command、等效 PowerShell 指令，以及日常設計/出圖流程的建議用法。本專案主要用途是把 A/B/C 棟與儲藏空間的 HTML 平面配置轉成結構化 JSON，再產生候選配置、SVG 圖面、PDF bundle 與專家審查報告。

## 目前 Claude Code 設定

本 repo 目前有下列 Claude Code 相關檔案：

| 檔案 | 用途 |
|---|---|
| `CLAUDE.md` | Claude Code 進入 repo 後的常駐專案規則與 pipeline 說明 |
| `.claude/commands/workflow-house-all-in-one.md` | 自訂 slash command，對應 `/workflow-house-all-in-one` |
| `.claude/settings.local.json` | 本機啟用 MCP server 設定，目前啟用 `playwright`、`brave-search` |
| `.mcp.json` | project-level MCP server 定義，包含 `playwright` 與 `brave-search` |
| `.env.mcp.example` | Brave Search API key 的本機環境變數範本 |

目前真正可直接在 Claude Code 輸入的專案自訂 slash command 是：

```text
/workflow-house-all-in-one
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

Claude Code 內使用：

```text
/workflow-house-all-in-one inputs/design_request.md --mode draft --buildings A,B,C --selection auto
```

等效 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
  -Selection auto
```

建議日常優先使用這個入口，因為它會把專家檢查、HTML 一致性與出圖驗證串在一起。

## 參數說明

| 參數 | 可用值 | 說明 |
|---|---|---|
| `Request` / 第一個位置參數 | 例如 `inputs/design_request.md` | 設計需求 Markdown，建議每次改版前先更新 |
| `Mode` / `--mode` | `concept`、`draft`、`ifc` | 流程嚴謹度與輸出層級 |
| `Buildings` / `--buildings` | `A`、`B`、`C`，可逗號分隔 | 要檢查的棟別，預設通常用 `A,B,C` |
| `Selection` / `--selection` | `auto`、`baseline`、`best` | SVG/PDF 選用的候選配置 |
| `Paper` | `a3`、`a4` | PDF 紙張大小，預設 `a3` |
| `Output` | PDF 路徑 | 預設 `structured/candidates/print_bundle.pdf` |
| `PythonExe` | 例如 `python`、`py` | 指定 Python 可執行檔 |

`Selection auto` 的實際行為：

- `concept` 模式會自動使用 `best`，適合快速比較演算法評分最高的配置。
- `draft` 與 `ifc` 模式會自動使用 `baseline`，較貼近原始圖面意圖。

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
  -Selection auto

# 日常草圖交付，產生預設 A3 PDF
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
  -Selection auto

# 只檢查 A 棟
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A `
  -Selection auto

# 輸出 A4 PDF
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
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
   執行 HTML 轉 JSON、候選配置、viewer、SVG、PDF 等主管線。

5. `validate_layout_bundle.py`  
   驗證 `room_program.json`、SVG manifest 與必要圖面標記。

6. `evaluate_expert_gates.py --stage report`  
   產出最終審查報告，並更新 `task-board.md` 的 last run 區塊。

## 重要輸出檔

| 檔案 | 說明 |
|---|---|
| `structured/expert_review/request_normalized.json` | 標準化後的需求 |
| `structured/expert_review/html_consistency.json` | HTML 一致性檢查結果 |
| `structured/expert_review/report.json` | 機器可讀專家審查報告 |
| `structured/expert_review/report.md` | 人可讀專家審查報告 |
| `structured/room_program.json` | 整合後的棟別/樓層/房間資料 |
| `structured/candidates/layout_candidates.json` | 各樓層候選配置與分數 |
| `structured/candidates/summary.md` | 候選配置摘要 |
| `structured/candidates/viewer.html` | 可切換樓層與候選配置的瀏覽器檢視 |
| `structured/candidates/svg/index.html` | SVG 圖面索引 |
| `structured/candidates/print_bundle.pdf` | PDF 圖面 bundle，`concept` 模式不產生 |
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

# 指定 Python launcher
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -PythonExe py
```

也可逐步執行：

```powershell
python scripts/extract_layout_data.py
python scripts/build_room_program.py
python scripts/generate_layout_candidates.py
python scripts/render_candidate_viewer.py
python scripts/export_top1_svgs.py --selection baseline
python scripts/export_print_bundle_pdf.py --paper a3 --output structured/candidates/print_bundle.pdf
python scripts/validate_layout_bundle.py
```

注意：部分 Python 腳本沒有 `--help` 模式，直接執行就會重新產生 `structured/` 產物。

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
3. 執行 /workflow-house-all-in-one inputs/design_request.md --mode concept --buildings A,B,C --selection auto
4. 修正 gate 或 consistency 問題
5. 執行 draft 產出 PDF
```

交付草圖：

```text
/workflow-house-all-in-one inputs/design_request.md --mode draft --buildings A,B,C --selection auto
```

最終放行：

```text
1. 檢查 report.md 與 viewer.html
2. 建立 structured/expert_review/signoff.yaml
3. 執行 /workflow-house-all-in-one inputs/design_request.md --mode ifc --buildings A,B,C --selection auto
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

限制：
- 僅使用非 _tmp HTML。
- critical hard gate 失敗要停止。
- 回報 report.json、report.md、viewer.html、print_bundle.pdf 路徑。
```

也可以直接打開下列 prompt 文件使用：

- `scripts/WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md`
- `scripts/WEB_TO_PLAN_PROMPTS.zh-TW.md`

# Claude Code 使用指南

適用專案：`D:\I29786\workspace\houseDesignPrepare`
更新日期：2026-07-14

這個專案把 A、B、C 棟住宅 HTML 轉成結構化資料，再產生候選配置、SVG、PDF、建築指標與專家審查報告。

如果只想知道該執行哪個指令：

- 日常設計檢查：使用 `/workflow-house-all-in-one ... --mode concept`
- 要產生 PDF：改用 `--mode draft`
- 最終審查：改用 `--mode ifc`，並完成兩次執行與人工簽核
- 不需要專家報告，只想快速重建圖面：使用 `python -m house_design pipeline`

## 1. 第一次使用

### 安裝套件

在 PowerShell 執行：

```powershell
cd D:\I29786\workspace\houseDesignPrepare
python -m pip install -r requirements.txt -r requirements-dev.txt
```

### 啟動 Claude Code

一定要從專案根目錄啟動，Claude Code 才能讀到 `CLAUDE.md`、slash commands 與 MCP 設定：

```powershell
cd D:\I29786\workspace\houseDesignPrepare
claude
```

進入後可檢查 MCP：

```text
/mcp
```

Brave Search 需要 API key；沒有設定時不影響一般出圖流程：

```powershell
$env:BRAVE_API_KEY = "your_key"
claude
```

## 2. 最常用的一鍵流程

Claude Code 內執行：

```text
/workflow-house-all-in-one inputs/design_request.md --mode concept --buildings A,B,C --selection auto --drawing-style presentation
```

這個指令會依序完成：

1. 整理 `inputs/design_request.md` 的需求。
2. 執行法規、無障礙與專家規則 gate。
3. 檢查 HTML 幾何、房間綁定與入口資料。
4. 產生 JSON、建築指標、候選配置、viewer、SVG；draft/ifc 也產生 PDF。
5. 驗證輸出圖面。
6. 產生專家報告與 domain checklist。
7. 產生不覆蓋原檔的 final HTML 討論版。

等效 PowerShell 指令：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode concept `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

### Mode 怎麼選

| Mode | 用途 | PDF | 驗證程度 |
|---|---|---:|---|
| `concept` | 修改 HTML 後快速檢查 | 不產生 | 基本流程 |
| `draft` | 日常討論與草圖交付 | 產生 | 一般驗證 |
| `ifc` | 最終人工審查與放行 | 產生 | strict 驗證＋signoff hash |

通常先跑 concept，確認無誤後再跑 draft。

### Selection 怎麼選

| Selection | 行為 |
|---|---|
| `auto` | 所有模式選擇保留來源綁定的 `baseline`；試驗方案需明確指定 `best` |
| `baseline` | 保留最接近原始 HTML 的配置 |
| `best` | 使用演算法評分最高的候選方案 |

正式討論或交付建議使用 `auto` 或 `baseline`。`best` 是設計比較工具，不代表已通過法規或專業審查。

### Drawing style 怎麼選

| Style | 適合情境 |
|---|---|
| `presentation` | 一般討論、簡報與列印，畫面最乾淨 |
| `technical` | 需要門窗、尺寸、立面索引等技術標記 |
| `debug` | 檢查演算法、score、notes 與格位對應 |

## 3. 日常工作範例

### 快速檢查修改

```text
/workflow-house-all-in-one inputs/design_request.md --mode concept --buildings A,B,C --selection auto --drawing-style presentation
```

### 產生 A3 PDF

```text
/workflow-house-all-in-one inputs/design_request.md --mode draft --buildings A,B,C --selection auto --drawing-style presentation
```

### 只檢查 A 棟

```text
/workflow-house-all-in-one inputs/design_request.md --mode concept --buildings A --selection auto --drawing-style presentation
```

### 產生 A4 技術圖

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
  -Selection baseline `
  -DrawingStyle technical `
  -Paper a4 `
  -Output structured/candidates/print_bundle_a4.pdf
```

## 4. 快速增量 Pipeline

如果不需要專家 gate、task board 與 final HTML，只想重建圖面，可使用新的 package CLI：

```powershell
python -m house_design pipeline --mode concept
```

它會根據輸入與輸出 hash 跳過沒有變化的步驟。快取存在 `.house-design-cache.json`，不會提交到 Git。

常用指令：

```powershell
# 完整重跑，不使用快取
python -m house_design pipeline --mode draft --force

# 只重跑候選配置到 SVG
python -m house_design pipeline --mode draft --from-step candidates --to-step svg

# 產生 technical SVG/PDF
python -m house_design pipeline --mode draft --style technical
```

可用 step：

```text
extract → program → metrics → candidates → viewer → svg → pdf → validate
```

其中 `pdf` 不會出現在 concept；`validate` 只會出現在 ifc。

快取不只檢查 manifest 是否存在，也會檢查 manifest 列出的 SVG 與 output hash。若某張 SVG 遺失，SVG 與依賴它的 PDF 會自動重建。

## 5. 修改 HTML 時要遵守的規則

正式輸入只有：

- `AbuildingView.html`
- `BbuildingView.html`
- `CbuildingView.html`
- `storage.html`

不要把 `*_tmp.html` 或 `structured/final_design_html/*.final.html` 當成下一次 pipeline 的輸入。

必須保留 DOM 結構：

```text
.floor-plan > .plan-grid-visual > .plan-row > .plan-cell
```

房間格位與詳細資料必須成對：

```html
onclick="highlightRoom('living', this)"
id="room-living"
```

精確出圖使用 mm metadata：

```html
data-floor-width-mm="11000"
data-floor-depth-mm="7700"
data-x-mm="0"
data-y-mm="0"
data-w-mm="3600"
data-h-mm="2400"
data-door-mm="900"
data-window-mm="1800"
```

常用語意 metadata：

```html
data-entry="true"
data-room-role="elder"
data-accessible="true"
data-daylight-required="false"
data-structural-review="required"
```

注意：

- 同一樓層原則上只能有一個 `data-entry="true"`。
- 家庭劇院等不需要自然採光的空間可明確設定 `data-daylight-required="false"`。
- 屋頂水塔、熱泵、太陽能等設備應標記 `data-structural-review="required"`，但這只代表需要技師確認，不代表已通過結構審查。

## 6. 如何看執行結果

優先查看這些檔案：

| 想確認的內容 | 檔案 |
|---|---|
| 整體專家結論 | `structured/expert_review/report.md` |
| HTML 是否有錯 | `structured/expert_review/html_consistency.json` |
| 建築指標與待確認事項 | `structured/architect_metrics/report.md` |
| 候選分數與 baseline 差異 | `structured/candidates/summary.md` |
| 切換候選配置 | `structured/candidates/viewer.html` |
| SVG 圖面索引 | `structured/candidates/svg/index.html` |
| PDF | `structured/candidates/print_bundle.pdf` |
| 討論版 HTML | `structured/final_design_html/index.html` |
| 專業討論清單 | `structured/expert_review/domain_checklist.md` |

Architect Metrics 的 status：

| Status | 意義 |
|---|---|
| `ok` | 概念資料足夠，未發現明顯提醒 |
| `advisory` | 有設計提醒，例如採光偏低或門寬不足 |
| `missing_data` | 缺少必要的幾何或 metadata |
| `professional_required` | 必須由建築師、機電或結構技師確認 |

`professional_required` 不是程式錯誤，也不代表設計已通過；它表示這一項不能只靠本工具決定。

Room program 會把內容分成：

- `record_type=floor`：真正參與 metrics 與候選配置的樓層。
- `record_type=section`：overview、規格表或 storage 說明，不會誤算成 skipped floor。

候選 summary 的 grade：

| Grade | 分數 | 解讀 |
|---|---:|---|
| `good` | 80 以上 | heuristic 表現較完整，仍需人工審查 |
| `review` | 65–79.99 | 建議檢查弱項 |
| `weak` | 低於 65 | 應查看 Low-score Review 與 baseline 差異 |

這些是相對比較分數，不是法規分數。

## 7. IFC 最終簽核

IFC 必須跑兩次，因為第一次要先產生最新 report hash。

### 第一次執行

```text
/workflow-house-all-in-one inputs/design_request.md --mode ifc --buildings A,B,C --selection auto --drawing-style technical
```

第一次通常會因 signoff 尚未更新而以 exit code `2` 停止，這是預期流程。

### 人工檢查

1. 打開 `structured/expert_review/report.md`。
2. 確認 critical、warning、professional required 與 domain checklist。
3. 從 `structured/expert_review/report.json` 複製 `report_hash` 和 `generated_at`。

建立或更新：

```text
structured/expert_review/signoff.yaml
```

可以先複製範本：

```powershell
Copy-Item structured\expert_review\signoff.template.yaml structured\expert_review\signoff.yaml
```

填入：

```yaml
decision: approved
reviewer_kind: human
reviewer_role: owner
reviewer_name: <實際審查者>
reviewer_date: 2026-07-14
related_report_hash: <report.json 的 report_hash>
related_report_generated_at: <report.json 的 generated_at>
```

也可使用 `pass` 或 `approved_with_conditions`。

### 第二次執行

使用完全相同的 IFC 指令重跑。只有 signoff hash 對應最新 report，且 strict drawing validation 通過，流程才會成功。

Strict SVG validation 會解析實際 SVG XML，檢查入口、門、窗與所選 style 需要的尺寸、legend、elevation 圖元。只把 marker 字串放在 `<metadata>` 裡不會通過。

## 8. Exit code 怎麼看

| Exit code | 意義 | 下一步 |
|---:|---|---|
| `0` | 成功 | 查看報告與輸出 |
| `1` | 未預期程式錯誤 | 查看終端機 traceback |
| `2` | 參數、資料、validation 或 IFC signoff 問題 | 查看錯誤訊息與 report |
| `10` | 專家 hard gate 失敗 | 修正 critical failure 後重跑 |

## 9. 常見失敗處理

### Hard gate failed

打開：

```text
structured/expert_review/report.md
```

查看 `Critical Failures` 和 `fix_hint`。修正 HTML、需求或 rules 後重跑。不要為了讓 gate 通過而刪除法規引用欄位。

### HTML consistency critical

打開：

```text
structured/expert_review/html_consistency.json
```

常見原因：

- `highlightRoom('xxx')` 與 `id="room-xxx"` 不一致。
- 缺少 `data-x/y/w/h-mm`。
- 同一層有多個入口。
- 門窗尺寸超出合理範圍。

### Strict bundle validation failed

手動執行：

```powershell
python scripts/validate_layout_bundle.py --strict
```

它會指出哪張 SVG 缺少實際圖元或 manifest 指向的檔案不存在。重新產生 SVG：

```powershell
python -m house_design pipeline --mode draft --from-step svg --force
```

### IFC signoff missing or stale

表示 `signoff.yaml` 的 `related_report_hash` 不是最新 report hash。重新人工檢查最新報告並更新 hash，不要直接沿用舊簽核。

### MCP 無法啟動

確認：

- 是從專案根目錄啟動 Claude Code。
- Node/npm/npx 可以執行。
- Brave Search 已設定 `BRAVE_API_KEY`。
- 使用 `/mcp` 查看實際錯誤。

## 10. 測試與品質檢查

修改 Python 或 workflow 後執行：

```powershell
python -m pytest -q
python -m ruff check house_design scripts tests
python scripts/validate_layout_bundle.py --strict
```

若修改 HTML，至少再跑一次 concept：

```powershell
python -m house_design pipeline --mode concept --force
```

## 11. 其他可用指令

只重建 final HTML 討論版：

```text
/export-final-design-html --mode draft --buildings A,B,C --selection auto
```

只做 HTML consistency：

```powershell
python scripts/check_html_consistency.py --buildings A,B,C --mode draft
```

只更新 Architect Metrics：

```powershell
python scripts/evaluate_architect_metrics.py --buildings A,B,C
```

逐步手動執行：

```powershell
python scripts/extract_layout_data.py
python scripts/build_room_program.py
python scripts/evaluate_architect_metrics.py
python scripts/generate_layout_candidates.py
python scripts/render_candidate_viewer.py
python scripts/export_top1_svgs.py --selection baseline --style presentation
python scripts/export_print_bundle_pdf.py --paper a3 --output structured/candidates/print_bundle.pdf
python scripts/validate_layout_bundle.py --strict
```

## 12. Slash command 不可用時

把以下內容貼給 Claude Code：

```text
請依照 scripts/WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md 執行 houseDesignPrepare 全流程。

輸入：
- request_file: inputs/design_request.md
- mode: draft
- buildings: A,B,C
- selection: auto
- drawing_style: presentation

限制：
- 只使用 canonical、非 _tmp HTML。
- critical hard gate 失敗時停止。
- 回報 report.md、domain_checklist.md、viewer.html、final HTML 與 PDF 路徑。
```

相關文件：

- `CLAUDE.md`：專案固定規則與架構。
- `scripts/README.md`：各 pipeline 腳本詳細說明。
- `scripts/WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md`：slash command 的備援 prompt。
- `scripts/WEB_TO_PLAN_PROMPTS.zh-TW.md`：HTML 修改與出圖 prompt 範本。

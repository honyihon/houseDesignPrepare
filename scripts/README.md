# House Design Workflows

## 資源安全：重型驗收另開終端機執行

目前主案[A收納／乾區續修](../Docs/a-storage-dry-zone-v2.md)為12層／112區／128件，增加的是1件書櫃；下列舊案章節的127件為當時主案，比較案本身沒有採用新布局。先跑Windows主案CLI，不自動並行全套測試。

2026-10-15只修平面房名／冷氣符號與代碼的避讓，A二樓前陽台房名排入兩機之間。房間、家具與設備座標不變；比較圖依共用繪圖器更新，不採用。Windows CLI新增原生SVG實際字框檢查（含白邊）、兩台完整代碼及設備原位置／尺寸查核；`snbl6T`是修改前passed，不可沿用作新版目視或渲染通過。

屋主要求：卡住、逾時或耗資源的檢查不要在代理背景反覆重跑、影響正常修改。代理只做有20秒上限的檔案／語法／小範圍檢查；瀏覽器、全套測試、整套3D場景及大型轉图預設交屋主另外執行，且一次只跑一項。詳細規則見[AGENTS.md](../AGENTS.md)。

新版主案渲染先在另一個 **Windows PowerShell** 執行：

```powershell
node '\\wsl.localhost\Ubuntu\root\workspace\houseDesignPrepare\scripts\check_windows_playwright.cjs'
```

若要補完整程式驗收，再另開 **WSL 終端機** 逐項執行；逾時即列未完成，不自动重試：

```bash
cd /root/workspace/houseDesignPrepare
timeout 300s .venv/bin/pytest -q --tb=short
timeout 90s node --max-old-space-size=384 tests/js/model3d-facade-runtime.test.cjs
```

需要停下時使用該終端機的 `Ctrl+C`。不要與Windows瀏覽器驗收同時跑；exit 124是逾時，不是通過。無結果或被中止的執行也不算通過，渲染passed仍需目視。

## B 32地坪：後門搬轎預案／前門備案（未採用）

`python3 scripts/export_b32_entry_options.py` 只產出獨立的 `structured/candidates/b32-entry-options*`，不改ABC主案或既有七案。兩案、八層、64分區、60件為比較合計；主案仍12／112／127。後方通路、通行權與實物搬運未知；B不超32地坪，37.3坪舊圖不是本輪可採候選。詳見[比較契約](../Docs/b32-entry-options-v1.md)。

```bash
.venv/bin/pytest -q tests/test_b32_entry_options.py
node --test tests/js/b32-entry-playwright.test.cjs tests/js/b32-plan-viewer.test.cjs
node scripts/check_b32_entry_playwright.cjs --preflight
```

Windows PowerShell執行 `node '\\wsl.localhost\Ubuntu\root\workspace\houseDesignPrepare\scripts\check_b32_entry_playwright.cjs'`。沿用已安裝的Playwright CLI／Edge；結果在新TEMP，不安裝、不採用、不把舊七案passed套用新圖。前門備案的收納位置與通行暫留不同，不能只保留一個後門案並宣稱前門也已驗證可搬。

平面展示v2加入獨立放大、縮小、讀字／整層還原與原生捲動；配置仍v1、八張SVG不變。CLI會顯示 `B32 display revision: 2`，新增兩案×桌機／手機直橫六組閱讀操作及至少16張截圖。`o1kJdw`的v1 passed保留作歷史證據，不涵蓋新介面。

## ABC 前期整合比較／會談補充（未採用）

`python3 scripts/export_preparation_review.py` 只輸出新的 `structured/candidates/preparation-review*` 與 `structured/discussions/abc-preparation-meeting.*`，原 ABC 主案／需求／封存對話受雜湊保護。七案、28 層、281 區、284 件是比較間合計；主案仍 12 層／112 區／127 件。v2 更新 B 搬轎／神明堂連動、C 門前操作與客餐家具，不改固定32坪B缺口對照；範圍與未解需求見[動線修正版 v2](../Docs/abc-preparation-review-v2.md)，v1驗收不可當成v2渲染通過。

```bash
.venv/bin/python -m pytest tests/test_preparation_review.py -q
node --test tests/js/preparation-playwright.test.cjs
node scripts/check_preparation_playwright.cjs --preflight
```

新頁渲染須在 Windows PowerShell 執行 `node '\\wsl.localhost\Ubuntu\root\workspace\houseDesignPrepare\scripts\check_preparation_playwright.cjs'`；不只跑舊主案 QA。沿用已安裝的 Playwright CLI／Edge，不安裝、不採用、不修改來源；新 TEMP 目錄存結果與截圖，passed 仍需目視及專業查核。

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

## 每筆32地坪含騎樓容量比較（未採用）

情境來源為 `inputs/abc-arcade-capacity.json`，以`inputs/references/abc-before-a-arcade.json`固定舊骨架／32坪限制／加深對照，皆為歷史未採用方案。現A主案已改[32坪含騎樓](../Docs/a-32ping-arcade-layout-v1.md)，12 floors／112 rooms／127 items；B／C配置未改。修改情境或其來源後執行：

```bash
.venv/bin/python scripts/export_arcade_capacity.py
.venv/bin/pytest -q tests/test_arcade_capacity.py
node scripts/check_windows_playwright.cjs --preflight
```

入口：[容量比較](../structured/candidates/arcade-capacity.html)／[獨立3D](../structured/candidates/arcade-capacity-3d.html?scheme=arcade32#mode=tour&building=A&floor=floor-1&view=front)。36張平面SVG、manifest與3D同源；只重分配房間，不縮市售代表產品。1F暫估4m層高、同軸共同梯井、冷氣與立面同步，法規及專業狀態保持unknown。[結果與產圖契約](../Docs/abc-32ping-arcade-v1.md)列A／C衝突、B未解需求及每筆面積敏感度。

CLI保留主案及C公衛／採光流程，涵蓋三案 × ABC × 四層HTML／3D、返回同案／棟／層、無效連結與手機重載／重設／橫向。容量初版`0mTIes`已核對4598項／114份當時來源雜湊／71張分級目視截圖。後續手機取景續修加入360／390／430px按鈕尺寸及單行文字、實際overlay安全區、至少60%單一軸占比／16px家具本體投影／橫向整層40%寬度檢查；當時預期114份來源雜湊、72張截圖。本輪A騎樓主案改為115份來源雜湊，新增騎樓與A客餐廳手機直向／橫向特寫，舊版張數不適用。新版渲染與目視待Windows重跑，不能沿用0mTIes或sAmDnF；細節見[取景續修契約](../Docs/abc-32ping-arcade-v1.md#手機取景續修僅展示)及[A騎樓主案](../Docs/a-32ping-arcade-layout-v1.md)。

## Windows 原生 Playwright CLI 驗收

新增[B嚴格家規／C照護改善比較](../Docs/bc-constraints-review-v1.md)：執行 `.venv/bin/python scripts/export_bc_options.py` 產生五案、20張平面及單棟比較3D。ABC主案仍12 floors／112 rooms／127 items；B全層樓梯重排未採用，C客房待排衣櫃不算已容納。sXV7ej是新增比較前的驗收，新版需以原Windows命令重跑。

現行[風水小改與待決最佳方案](../Docs/fengshui-minimal-v1.md)增加A爐台／洗槽真正元件位置、B二／三樓神桌投影與C三樓側牆床檢查，另截四個桌面房間特寫。主案仍12 floors／112 rooms／127 items；B1及C1待決方案未採用。TBqvyB是改版前證據，新版必須重跑下方原命令，不宣稱風水／照護核可。

2026-10-12新增[B／C一樓動線續版](../Docs/bc-1f-flow-v1.md)：B神桌中軸180cm祭祀門、側門搬轎四段線與三個桌面特寫；C三區全寬開放、實牆電視與配管重算。主案仍12 floors／112 rooms／127 items；FYY4NW只適用改版前，請以原命令重跑，新截圖與專業條件不得沿用舊passed。

2026-10-12 [A MDF續修](../Docs/a-mdf-under-stair-v1.md)：新增共用平面候選虛框、敏感度剖面、3D可逆開關與手機驗收。備援補齊前後／左右維修，未新增第二台機櫃或認列原位釋放；預檢仍12／112／127。`house-design-cli-T1uj2e`的5133項／115份來源／75張截圖是此次續修前證據，新版須重跑，不覆寫舊報告。

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
2026-10-14修正SVG獨立房名層的驗收定位，以及純SVG失敗後CLI快照掩蓋原錯誤的問題；錯誤回報保留原網址／截圖，不重試、不降低判定。[894MkV未完成紀錄](../Docs/a-storage-dry-zone-v2.md#2026-10-14-windows未完成結果與驗收器修正)不能當作通過；新版請用上方Windows命令重驗，預檢12／112／128。房屋配置沒有因這次修驗收而更動。
本版預檢應為 **12 floors、112 rooms、128 items**；A主案騎樓、1200mm照護通道、4m名義一樓與共用前平台另做獨立檢查。會截取各樓層、A孝親房／一樓公衛、A／B二樓共用圖與衛浴／走道特寫，以及手機整層／特寫。樓上檢查三間衛浴700mm操作帶、馬桶側邊間距，以及屋主同意的A兩組更衣櫃分散／240cm淺櫃搬移；保留全部原尺寸與總收納量、公共1280mm暫留、私人更衣操作分時但未核。依當前同源pending清單判斷，不沿用舊版3件待排數字；下列27張及兩件待排等為歷史流程，不只比對兩張圖是否一樣。

提交1e38934的C續版另加HTML基本圖／庭院比較、餐廳／客廳／廚房特寫、3D前院虛框及手機客廳／前院；共44張、31份來源雜湊。獨立查面積、正常產品、照護暫留帶、TV同軸與未知前院，不只查兩張圖是否一樣，詳見[C一樓續版](../Docs/c-1f-space-use-v3.md)。

2026-10-07已核對 `house-design-cli-QEFdQU`：Windows Edge的2682項檢查通過，31份來源SHA-256與提交1e38934當時檔案一致，44張截圖已目視複查；12 floors／105 rooms／129 items，session已關閉。無pageerror或非預期錯誤，僅8次既有Three.js棄用warning。原始結果與截圖仍在Windows TEMP，詳細證據見[歷史驗收](../Docs/c-1f-space-use-v3.md#歷史-windows-驗收)。這份passed不適用本輪新增比較及共用viewer／HTML bridge／CLI改動。

2026-10-08新增[C一樓公衛／採光三案比較](../Docs/c-1f-bath-daylight-v1.md)：HTML實際選案、同方案SVG／3D、兩案公衛特寫、3D切換返回現況、手機重載／重設／收合及橫向特寫；最後返回ABC主案，確認未採用替代案。普通設備、孝親房床／衣櫃、前帶／樓梯、150cm暫留、門圖、候選窗、鞋櫃未容納與冷氣量另做獨立查核，不以兩張圖一起錯就判通過。主案預檢12／105／129；`house-design-cli-sAmDnF` 已核對**3275項自動檢查通過、64份來源雜湊與當時檔案吻合、56張截圖全部目視複查**，Windows Edge、1440 × 900／390 × 844／844 × 390。無pageerror或非預期錯誤，19次既有Three.js棄用warning，session已關閉。橫向公衛與含冷氣管路的C客廳特寫仍偏小，不能將passed當成全面可讀性驗收；詳細證據與待辦見[該輪Windows驗收](../Docs/c-1f-bath-daylight-v1.md#本輪-windows-驗收)。後續容量比較已改bridge／CLI，這份報告是歷史證據，須用上方原命令重新驗收，無需另裝Browser插件。

照片風格外觀v1保留上述27張，另加HTML立面、三棟各自正面／斜角、三棟合看及手機外觀，共36張。來源雜湊從25份增為30份，包含外觀JSON、原照片及三份立面SVG；預檢也核照片記錄的SHA-256。實際檢查HTML→全層外觀、正面／斜角、棟別／樓層切換、分享重載、手機返回室內，以及原剖視、展開、牆面、房間特寫與家具pending還原。外觀開口／装飾衝突保留待確認，17組室外機座標沿共用來源，不把美觀當成合規。
外觀v1的house-design-cli-lgBJsy已核對2603項／36張，是C重排前報告，不能替新版背書。本環境socket與Chromium受限制；QEFdQU是提交1e38934的Windows證據，sAmDnF只適用容量比較前來源，0mTIes只適用手機取景續修前來源，g2jEnZ只適用新A重排前來源，不代表Linux HTTP e2e也已執行。研究來源見[ABC外觀提案](../Docs/abc-facade-v1.md)；下列27／36／44／56／71張及126／129件為歷史流程，最新CLI主案127件，Windows與新截圖目視仍待重跑。
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

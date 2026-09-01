# House Design Prepare 使用指南

- 適用專案：`houseDesignPrepare`
- 更新日期：2026-08-31

本專案目前的核心用途，是在收到建築師圖面後，以不可變版次保存 PDF／IFC／DXF，並根據基地事實、屋主已確認需求、法源與圖面證據產生可追溯的檢核報告。

目前土地尚未確定。目標是在高雄尋找 A／B／C 三筆相鄰、未來分開檢核的土地，每筆約 32 坪。32 坪是「選地目標」，不是實際基地面積或每層可蓋面積。土地、地號、使用分區、道路、建蔽率、容積率與退縮未知時，系統必須顯示 `unknown`，不能推定為通過。

專案仍保留兩套歷史工具：

- HTML 分支：將早期 A／B／C 住宅 HTML 草圖轉成候選配置、SVG、PDF 與離線 3D 量體。
- 參數化分支：重現舊的「每層建築面積 32 坪」假設，產生容量報告與 walk-in 3D。

這兩套歷史輸出可用於存檔、討論與回歸測試，但不是現行設計基準，也不能證明可建築量體或法規合規。

## 1. 我現在應該執行哪個指令

| 目的 | 指令 | 主要輸出 |
|---|---|---|
| 檢查基地與需求資料格式 | `python -m house_design intake validate` | 終端機 JSON |
| 確認／淘汰一項屋主需求 | `python -m house_design intake requirements-decide ...` | 原子更新需求並追加 hash-chained decision log |
| 驗證前期階段閘門 | `python -m house_design predesign validate` | 終端機 JSON，不輸出私有金額 |
| 產生前期準備報告 | `python -m house_design predesign report` | `structured/predesign/` |
| 匯入建築師 PDF＋IFC | `python -m house_design drawings import ...` | `inputs/revisions/<revision>/` |
| 匯入 PDF＋DXF | `python -m house_design drawings import ... --dxf ... --mapping ...` | 不可變來源、mapping 與標準化模型 |
| 查看所有圖面版次 | `python -m house_design drawings list` | 終端機 JSON |
| 驗證不可變版次完整性 | `python -m house_design drawings verify --revision R001` | 來源、mapping、模型與 manifest seal 檢查 |
| 檢查現行版次是否具備 3D 輸入 | `python -m house_design drawings model3d-readiness --revision R001` | readiness JSON；阻擋時 exit code 1 |
| 產生現行空間量體模型 | `python -m house_design drawings export-model3d --revision R001` | `structured/reviews/R001/model3d.html` |
| 比較兩個圖面版次 | `python -m house_design drawings compare --from R001 --to R002` | 終端機 JSON，可另存檔 |
| 產生現行檢核報告 | `python -m house_design review run --revision R001` | JSON、Markdown、PDF、離線儀表板 |
| 比對前後版並檢核 | `python -m house_design review run --revision R002 --previous R001` | 報告內含 revision comparison |
| 對現行報告做真人簽核 | `python -m house_design review run --revision R001 --signoff ...` | 更新該版檢核輸出與簽核狀態 |
| 重建歷史 HTML 草圖輸出 | `python -m house_design pipeline --mode concept` | viewer、3D、SVG 等歷史輸出 |
| 重建歷史 PDF | `python -m house_design pipeline --mode draft` | 歷史 SVG 與 PDF |
| 嚴格驗證歷史圖包 | `python -m house_design pipeline --mode release` | 歷史圖包＋strict validation |

`pipeline --mode release` 只代表歷史出圖分支通過程式驗證，不代表現行圖面審查通過，更不代表建築師或主管機關核准。

## 2. 資料權威與目錄

| 資料 | 現行權威位置 | 說明 |
|---|---|---|
| 基地事實 | `inputs/project.json` | 地號、分區、道路、建蔽率、容積率、退縮及資料來源 |
| 前期階段狀態 | `inputs/predesign.json` | 家庭、財務、選地、設計、發包、施工與交屋閘門 |
| 精確預算 | `inputs/private/budget.json` | 已排除版控；只使用 `inputs/budget.private.template.json` 建立 |
| 屋主需求 | `inputs/requirements.json` | `candidate`／`confirmed`／`rejected`、優先度與 decision log |
| 建築師圖面版次 | `inputs/revisions/<revision>/` | 不可變 PDF／IFC／DXF、mapping、雜湊與 normalized model |
| 現行檢核結果 | `structured/reviews/<revision>/` | 報告、會議 PDF、比較結果與離線儀表板 |
| 前期準備結果 | `structured/predesign/` | 前期 report、目前行動與分層研究來源 |
| 高雄檢核規則 | `rules/kaohsiung_review_rules.json` | 法源、適用狀態、查證人與專業責任人 |
| 歷史 HTML 草圖 | `AbuildingView.html` 等 | 只在 HTML 歷史分支內是來源，不是現行專案圖面 |
| 歷史參數化情境 | `inputs/site.json`、`inputs/brief/` | 舊 32 坪 footprint 假設，只供重現與比較 |
| 歷史輸出 | `structured/candidates/`、`structured/parametric/` | 不得當成現行建築師圖面或合規結論 |

任何法規、結構、消防、機電與無障礙結論都必須保留法源、證據與負責專業人員。程式與 AI 不能取代依法執業者簽證。

## 3. 第一次安裝

所有命令都應從專案根目錄執行。

### Windows PowerShell

```powershell
cd D:\I29786\workspace\houseDesignPrepare
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,drawings]"
```

### WSL／Linux／macOS

```bash
cd /path/to/houseDesignPrepare
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,drawings]"
```

可依用途只安裝需要的依賴：

| 安裝方式 | 內容 |
|---|---|
| `python -m pip install -e .` | 核心 HTML、報告與 PDF 功能 |
| `python -m pip install -e ".[dev]"` | 另加 pytest、Ruff |
| `python -m pip install -e ".[drawings]"` | 另加 PyMuPDF、ezdxf、ifcopenshell |
| `python -m pip install -r requirements-import.txt` | drawing extras 的相容安裝方式 |

以下範例統一使用 `python -m house_design`。若 WSL／Linux／macOS 沒有 `python` 別名，請改用 `.venv/bin/python -m house_design`；Windows 也可使用 `.\.venv\Scripts\python.exe -m house_design`。安裝 editable package 後，還可將整段改寫成 `house-design`。

## 4. 現行工作流：基地、需求與圖面版次

### 4.0 土地未定時先跑前期閘門

```bash
python -m house_design predesign validate
python -m house_design predesign report
```

主要輸出：

- `structured/predesign/report.json`：機器可讀階段、阻擋、證據與負責角色。
- `structured/predesign/report.md`：現在要處理與後續階段預留。
- `structured/predesign/sources.md`：官方、專業、經驗與屋主政策的分層來源。

精確預算從範本複製到私有位置：

```bash
mkdir -p inputs/private
cp inputs/budget.private.template.json inputs/private/budget.json
```

`inputs/private/` 已由 `.gitignore` 排除。報告只會顯示私有預算表是否存在、有效及完成幾個欄位，不會帶出金額。

候選土地請從 `inputs/site-candidate.template.json` 建立。三筆相鄰、每筆約 32 坪目前只記在 `site_search.target_scenario`；只有選定並通過查核後，才能把正式 parcel 寫入 `site_search.selected_site`。

### 4.1 驗證基地與需求資料

```bash
python -m house_design intake validate
```

自訂輸入位置：

```bash
python -m house_design intake validate \
  --project path/to/project.json \
  --requirements path/to/requirements.json
```

輸出中的 `valid: true` 只表示 JSON 契約有效，不表示資料已完整，也不表示合規。請同時查看：

- `project_readiness.percent`：基地必要事實完成度。
- `project_issues`：基地資料契約錯誤。
- `requirement_issues`：需求資料契約錯誤。
- `requirements.candidate`／`confirmed`：待確認與已確認數量。

### 4.2 管理需求狀態

`inputs/requirements.json` 中每個項目的 `status`：

| Status | 意義 |
|---|---|
| `candidate` | 仍在討論；不會自動成為屋主硬需求 |
| `confirmed` | 屋主已確認；才會與圖面證據正式比對 |
| `rejected` | 已淘汰；應保留 decision log，不應直接刪除歷史 |

每項另有 `priority`：`must`、`should` 或 `could`。`must` 不符合時可形成阻擋；其他等級通常保留為警告或設計取捨，但生命安全、無障礙或專業規則仍以實際 finding 狀態為準。

逐項決策請用指令，不要直接刪除舊狀態或改寫 decision log：

```bash
python -m house_design intake requirements-decide \
  --id A.floor-1.elder \
  --status confirmed \
  --priority must \
  --reason "長輩需在一樓完成睡眠與沐浴" \
  --decided-by "屋主家庭會議" \
  --decided-at "2026-08-31"
```

每次執行會原子寫入目前狀態，並追加帶 `previous_entry_hash`／`entry_hash` 的紀錄；後續驗證會抓出被改寫或斷鏈的項目。家庭成員、照護與生活情境可從 `inputs/household-profile.template.json` 複製，但含個資的完成檔應放在 `inputs/private/`。

將舊 A／B／C brief 轉成候選需求：

```bash
python -m house_design intake migrate-briefs \
  --brief-dir inputs/brief \
  --output inputs/requirements.json
```

這是初始化／維護工具，會重寫 `--output`。既有需求已有人工作決策時，不要直接覆蓋；應先保留原檔並人工合併。匯入項目一律是 `candidate`，不會自動升級為 `confirmed`。

### 4.3 匯入不可變圖面版次

推薦同時取得 PDF 與 IFC：

```bash
python -m house_design drawings import \
  --revision R001 \
  --label "初步設計" \
  --pdf drawings/R001.pdf \
  --ifc drawings/R001.ifc
```

若只有 2D CAD，請設計方將 DWG 匯出為 DXF。DWG 不能直接匯入。

DXF 必須提供圖層語意 mapping，例如：

```json
{
  "schema": "house-drawing-mapping-v2",
  "dxf_unit_scale_to_mm": 1.0,
  "coordinate_system": {
    "status": "verified",
    "axis": {"x": "drawing-east", "y": "drawing-north", "z": "up"},
    "verified_by": "王建築師",
    "verified_at": "2026-08-31",
    "method": "PDF 與 DXF 共同控制點核對",
    "reference_points": [
      {"id": "GRID-A1", "source_mm": [0, 0], "project_mm": [0, 0]},
      {"id": "GRID-A2", "source_mm": [6000, 0], "project_mm": [6000, 0]}
    ]
  },
  "storeys": [
    {
      "building_id": "A", "floor_id": "floor-1", "elevation_mm": 0, "height_mm": 3200,
      "verified_by": "王建築師", "verified_at": "2026-08-31",
      "evidence": {"type": "drawing_level_note", "reference": "A-101 / EL±0"}
    }
  ],
  "layers": {
    "A-1F-ROOM-ELDER": {
      "kind": "space",
      "building_id": "A",
      "floor_id": "floor-1",
      "name": "孝親房",
      "requirement_id": "A.floor-1.elder"
    },
    "A-1F-DOOR-ELDER": {
      "kind": "door",
      "building_id": "A",
      "floor_id": "floor-1",
      "name": "孝親房門",
      "requirement_id": "A.floor-1.elder",
      "opening_width": {
        "value_mm": 900, "measurement": "finished_clear",
        "verified_by": "王建築師", "verified_at": "2026-08-31",
        "evidence": {"type": "door_schedule", "reference": "D01"}
      }
    }
  },
  "entities": {
    "8F": {"kind": "space", "name": "特定 handle 覆寫圖層設定", "requirement_id": "A.floor-1.elder"}
  }
}
```

```bash
python -m house_design drawings import \
  --revision R001 \
  --label "初步設計" \
  --pdf drawings/R001.pdf \
  --dxf drawings/R001.dxf \
  --mapping drawings/R001.mapping.json
```

匯入規則：

- 至少要提供 `--pdf`、`--ifc` 或 `--dxf` 其中一個。
- PDF 可單獨封存，但沒有 IFC／mapped DXF 時通常無法完成房間與門窗語意檢核。
- 原始圖、mapping 與 normalized model 都會記錄 SHA-256；manifest 另有涵蓋整份 metadata 的 content seal。
- `manifest.json` 一旦存在，同一 revision id 不能覆寫；收到新圖請使用 R002、R003 等新 id。
- DXF 未設定單位時，mapping 必須提供 `dxf_unit_scale_to_mm`。
- 閉合 DXF polyline 會保留 `polygon_mm` 並計算實際 polygon 面積，不再用 bbox 面積冒充凹形空間面積。
- DXF 門窗符號 bbox 只會成為 `overall_width_mm`；只有具人員、日期與門窗表證據的 `finished_clear` 才會寫入 `clear_width_mm`。
- `entities` 可用 DXF handle 覆寫 layer mapping；與 IFC 合併時必須明寫 `ifc_guid`，不做名稱猜測對帳。
- 未 mapping 的 DXF 圖層仍保留原始幾何，但不能證明房間或門窗需求。
- `drawings import`、`list`、`verify`、`seed-legacy`、`compare`、`model3d-readiness` 與 `export-model3d` 都可用 `--root` 指定非預設版次目錄。

IFC 建議：

- 棟名要有獨立 A／B／C token，例如 `A棟` 或 `Building A`。
- 樓層名使用 `1F`、`2F`、`3F`、`RF`；地下層可使用 `B1F`。
- 應提供 `IfcSpace`，否則房間層級檢核會維持未知。
- `IfcDoor.OverallWidth` 是名目寬度，不會自動當成完工後門淨寬。
- 沒有門窗表、可信 property 或 mapped DXF 開口證據時，門淨寬必須維持 `unknown`。

匯入後先驗證 seal；任何 source、mapping、normalized model 或 manifest 欄位被改動都會失敗，而且 compare、review、3D readiness 與 exporter 也會先做同一檢查：

```bash
python -m house_design drawings verify --revision R001
```

常見 manifest status：

| Status | 意義 |
|---|---|
| `ready` | 有可用的 machine-readable 圖面、標準化實體且無 blocking import issue |
| `needs_mapping` | 原始檔已保存，但語意對應不足 |
| `partial` | 已取得部分標準化實體，但仍有 blocking import issue |
| `legacy_assumption` | R000 等舊參數化情境，不得作為現行基準 |

### 4.4 列出版次

```bash
python -m house_design drawings list
```

自訂版次根目錄：

```bash
python -m house_design drawings list --root path/to/revisions
```

### 4.5 建立歷史 R000 示例

一般 repository 已有 R000，不需重建。新環境要將舊參數化情境封存為明確不可放行的版次時才使用：

```bash
python -m house_design drawings seed-legacy \
  --revision R000 \
  --variant f6000_g1 \
  --plan structured/parametric/plan.json
```

R000 會帶有 blocking 的 legacy assumption finding；它的用途是證明錯誤的 32 坪語意會被攔截，不是示範通過報告。

### 4.6 檢查現行 revision 的 3D 準備狀態

```bash
python -m house_design drawings model3d-readiness --revision R001
```

預設 `--level space_block` 只判斷「這一版是否足以建立可追溯的現行空間量體」，不會把
`structured/parametric/walkthrough.html` 或 `structured/candidates/model3d.html` 等歷史輸出當成現行版次。
阻擋時仍會先輸出完整 JSON，再以 exit code 1 結束，方便 CI 攔截。

必須同時符合：

1. manifest 是 `ready`，來源包含 IFC 或 DXF，且沒有 blocking import issue。
2. 每個空間都有有效 `bbox_mm`、`building_id`、`floor_id` 與可追溯的專業幾何來源。
3. 每個使用中的棟別／樓層都有數值 `elevation_mm`；1F 的 `0` 是有效標高。
4. IFC／DXF 的原點、軸向、單位與樓層基準已核對；`coordinate_system` 除了 `verified`，還有查核人、日期、方法與至少兩個控制點。

輸出的 `blockers` 會使用穩定代碼，例如 `SPACE_GEOMETRY_MISSING`、
`STOREY_ELEVATION_MISSING`、`COORDINATE_SYSTEM_UNVERIFIED`，每一項都有 `next_action`。
`space_block ready` 只表示輸入具備「空間量體」產圖條件，不表示圖面合規、結構安全或已獲專業放行。`--level walkthrough` 會另外要求精確 polygon、牆體、空間高度、門窗、樓梯及設備範圍；bbox 量體不會被稱為施工精度走入模型。

產生目前版次的離線空間量體：

```bash
python -m house_design drawings export-model3d --revision R001
```

預設輸出為 `structured/reviews/R001/model3d.html`。只有 readiness 通過且檔案確實存在時，同目錄 dashboard 才會顯示連結；頁面也會明確標示「空間量體模型」，不冒充施工精度 walkthrough。

自訂版次根目錄：

```bash
python -m house_design drawings model3d-readiness \
  --revision R001 --root path/to/revisions
```

### 4.7 比較兩個版次

```bash
python -m house_design drawings compare --from R001 --to R002
```

另存 JSON：

```bash
python -m house_design drawings compare \
  --from R001 \
  --to R002 \
  --output structured/reviews/R002/comparison.json
```

比較內容包含空間、門、窗與設備的新增、刪除，以及面積、尺寸、位置、樓層和門寬等欄位變更。

## 5. 現行工作流：產生檢核報告

### 5.1 執行單一版次檢核

```bash
python -m house_design review run --revision R001
```

同時比較前一版：

```bash
python -m house_design review run --revision R002 --previous R001
```

主要選項：

| 選項 | 預設 | 用途 |
|---|---|---|
| `--project` | `inputs/project.json` | 指定基地資料 |
| `--requirements` | `inputs/requirements.json` | 指定需求登錄 |
| `--rules` | `rules/kaohsiung_review_rules.json` | 指定規則包 |
| `--predesign` | `inputs/predesign.json` | 指定前期階段狀態 |
| `--predesign-rules` | `rules/predesign_readiness_rules.json` | 指定前期規則與分層來源 |
| `--budget-private` | `inputs/private/budget.json` | 讀取私有預算完整狀態；報告不輸出金額 |
| `--revision-root` | `inputs/revisions` | 指定不可變版次根目錄 |
| `--output-root` | `structured/reviews` | 指定報告根目錄 |
| `--previous` | 無 | 將前後版比較嵌入報告 |
| `--signoff` | 無 | 套用現行 JSON 真人簽核 |
| `--skip-pdf` | false | 不產生 meeting-report.pdf |

每次預設輸出到 `structured/reviews/<revision>/`：

| 檔案 | 用途 |
|---|---|
| `report.json` | 機器可讀 finding、證據、3D readiness、比較與 report hash |
| `report.md` | 可讀的逐項會議清單與 3D 阻擋原因 |
| `meeting-report.pdf` | 可列印會議報告，摘要包含 3D readiness；`--skip-pdf` 時不產生 |
| `index.html` | 完全離線的互動檢核儀表板，顯示現行 revision 3D 狀態與下一步 |

離線儀表板不依賴外部 CDN，可直接以瀏覽器開啟。

### 5.2 Finding 狀態

| Status | 意義 | 是否阻擋 `release_eligible` |
|---|---|---:|
| `pass` | 有足夠證據且此檢核通過 | 否 |
| `warning` | 設計提醒或非阻擋取捨 | 否 |
| `unknown` | 缺資料或證據，不能判斷 | 是 |
| `professional_review` | 必須由建築師／技師等專業人員確認 | 是 |
| `fail` | 已有證據顯示不符合契約或規則 | 是 |
| `not_applicable` | 經確認不適用 | 否 |

`release_eligible` 只有在以下條件全部成立時才可能為 true：

1. 沒有 `fail`。
2. 沒有 `unknown`。
3. 沒有 `professional_review`。
4. 現行 JSON signoff 有效。

命令以 exit code 0 完成，只表示報告成功產生；即使 `release_eligible: false`，命令仍可能成功。務必查看報告內容與輸出的 `release_eligible`。

## 6. 現行 JSON 人工簽核

現行簽核範本是 `inputs/signoff.template.json`，不是歷史 HTML 分支的 YAML signoff。

### 第一次執行：取得 report hash

```bash
python -m house_design review run --revision R001
```

人工檢查 `structured/reviews/R001/report.md`、`meeting-report.pdf` 與 `index.html`，再從 `report.json` 複製 `report_hash`。

### 建立簽核檔

PowerShell：

```powershell
Copy-Item inputs\signoff.template.json inputs\signoff.R001.json
```

Bash：

```bash
cp inputs/signoff.template.json inputs/signoff.R001.json
```

範例：

```json
{
  "schema": "house-review-signoff-v1",
  "revision_id": "R001",
  "decision": "approved_with_conditions",
  "reviewer_kind": "human",
  "reviewer_role": "architect",
  "reviewer_name": "實際審查者姓名",
  "reviewer_date": "2026-08-28",
  "related_report_hash": "從最新 report.json 複製",
  "conditions": []
}
```

允許的 decision 是 `approved`、`pass`、`approved_with_conditions`。

簽核無效的情況包括：

- `reviewer_kind` 不是 `human`。
- 審查者姓名空白或是 Claude、ChatGPT、Codex 等 AI 身分。
- 缺少 reviewer role 或日期。
- `revision_id` 與報告版次不同。
- `related_report_hash` 不是最新報告 hash。

### 第二次執行：套用簽核

```bash
python -m house_design review run \
  --revision R001 \
  --signoff inputs/signoff.R001.json
```

簽核只記錄該真人對該版報告的決定，不取代建照審查、結構計算、消防、機電、無障礙或其他依法簽證程序。即使 signoff 有效，只要仍有 fail、unknown 或 professional review，`release_eligible` 仍會是 false。

## 7. 歷史 HTML 與參數化 Pipeline

本章所有功能都屬歷史分支。它們適合重現早期草圖、測試 parser、比較候選方案與輸出討論圖，不會更新 `structured/reviews/<revision>/` 的現行檢核。

### 7.1 Mode

| Mode | 行為 | PDF | Validation |
|---|---|---:|---|
| `concept` | 快速重建歷史 viewer、3D 與 SVG | 不產生 | 無 strict gate |
| `draft` | 產生歷史討論／列印圖包 | 產生 | 一般產出檢查 |
| `release` | 完整歷史輸出與 strict bundle validation | 產生 | strict |
| `ifc` | `release` 的 deprecated 相容別名 | 產生 | strict |

IFC 現在應指建築圖面檔案格式。新指令請使用 `release`，不要再把 `ifc` 當成 mode 名稱。

### 7.2 常用指令

```bash
# 快速重建，不產生 PDF
python -m house_design pipeline --mode concept

# 歷史 A3 PDF
python -m house_design pipeline --mode draft

# 歷史 A4 technical PDF
python -m house_design pipeline \
  --mode draft \
  --style technical \
  --paper a4 \
  --output structured/candidates/print_bundle_a4.pdf

# 完整重跑，不使用快取
python -m house_design pipeline --mode release --force

# 只重跑候選配置到 SVG
python -m house_design pipeline \
  --mode draft \
  --from-step candidates \
  --to-step svg
```

Windows PowerShell 也保留一個非增量的歷史 wrapper。它會先跑 HTML consistency，再依序重建歷史輸出；需要完整逐步輸出或由 expert workflow 呼叫時可使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 `
  -Mode draft `
  -Paper a3 `
  -Selection baseline `
  -DrawingStyle presentation
```

`run_full_pipeline.ps1` 支援 `-Mode`、`-Paper`、`-Selection`、`-DrawingStyle`、`-Output` 與 `-PythonExe`。`-ValidationOwner` 是巢狀 workflow 用來避免重複驗證的內部協調選項；一般直接執行時保留預設 `inner`。日常重跑仍建議使用 package CLI，才能利用 step cache 與 `--from-step`／`--to-step`。

其他 pipeline 選項：

| 選項 | 用途 |
|---|---|
| `--selection auto|baseline|best` | 選擇候選策略 |
| `--style presentation|technical|debug` | 選擇 SVG／PDF 樣式 |
| `--paper a3|a4` | 選擇 PDF 紙張 |
| `--output <path>` | 指定 PDF 輸出位置 |
| `--from-step`／`--to-step` | 只執行一段步驟；所選 step 必須存在於該 mode |
| `--force` | 忽略 `.house-design-cache.json` |
| `--python-exe <path>` | 指定各 step 使用的 Python |

### 7.3 Selection

| Selection | 行為 |
|---|---|
| `auto` | 解析為來源保留的 `baseline` |
| `baseline` | 保留最接近原始 HTML 綁定的配置 |
| `best` | 使用 heuristic 總分最高的候選方案 |

`best` 只供比較，不代表法規、專業或屋主需求已通過。

### 7.4 Drawing style

| Style | 適合情境 |
|---|---|
| `presentation` | 一般討論、簡報與列印 |
| `technical` | 顯示較完整的門窗、尺寸、legend 與立面索引 |
| `debug` | 檢查候選分數、notes 與格位對應 |

### 7.5 Pipeline 步驟

```text
extract
  → program
  → metrics
  → candidates
  → viewer
  → model3d
  → parametric
  → walkthrough
  → svg
  → pdf        （concept 不執行）
  → validate   （只有 release 執行）
```

`parametric` 分支不讀 HTML；它只是在同一個 orchestrator 中依序執行。它讀取 `inputs/site.json` 與 `inputs/brief/`，仍是舊的 32 坪 footprint 情境。

`.house-design-cache.json` 會記錄命令、輸入與輸出 hash。未變更且輸出完整的 step 會跳過；SVG manifest 內的每張 SVG 與 PDF 依賴也會納入檢查。使用 `--force` 可忽略快取。

### 7.6 歷史輸出

| 內容 | 檔案 |
|---|---|
| 結構化 HTML | `structured/*buildingView.structured.json`、`structured/index.json` |
| 統一 room program | `structured/room_program.json` |
| 建築指標 | `structured/architect_metrics/metrics.json`、`report.md` |
| 候選方案 | `structured/candidates/layout_candidates.json`、`summary.md` |
| 候選切換 viewer | `structured/candidates/viewer.html` |
| HTML 量體 3D | `structured/candidates/model3d.html` |
| SVG 索引 | `structured/candidates/svg/index.html` |
| 列印 PDF | `structured/candidates/print_bundle.pdf` |
| 舊參數化容量 | `structured/parametric/plan.json`、`capacity.md` |
| 舊參數化 walk-in 3D | `structured/parametric/walkthrough.html` |

`model3d.html` 是與 A／B／C 原始 HTML 逐格對照的主要討論入口；原 HTML 會為每層與每個已綁定房間建立雙向連結。它支援
`#building=A&floor=floor-1&room=A:floor-1:living&view=plan` 深連結，且道路／前方固定為 HTML 平面上方 `y=0`。
`walkthrough.html` 則會依 6–10 m 開間重新排房，只能作為另一個歷史容量情境，不能拿來判斷原 HTML 房間是否在前段或後段。
兩個 3D viewer 都可離線開啟，但用途只是閱讀／比較，不能編輯後回寫模型。

## 8. 歷史 HTML 的幾何與資料可信度

在 HTML 歷史分支內，輸入是：

- `AbuildingView.html`
- `BbuildingView.html`
- `CbuildingView.html`
- `storage.html`

不要把 `*_tmp.html` 或 `structured/final_design_html/*.final.html` 當成 pipeline 輸入。

必須保留 DOM：

```text
.floor-plan > .plan-grid-visual > .plan-row > .plan-cell
```

房間格位與詳細資料必須成對：

```html
onclick="highlightRoom('living', this)"
id="room-living"
```

支援的幾何 metadata：

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

支援的語意 metadata：

```html
data-entry="true"
data-room-role="elder"
data-accessible="true"
data-daylight-required="false"
data-structural-review="required"
```

注意：HTML 裡有 mm 不代表它是實測值。每個 cell 應查看 `geometry_provenance`：

| Provenance | 意義 |
|---|---|
| `measured` | 已由量測或可信正式資料寫入 `inputs/dimensions.json` |
| `declared` | 由 HTML 顯示文字，例如「約 5.5m × 6.0m」或坪數推回 |
| `auto` | 從 CSS grid／class 自動推估，只能作為歷史草圖 |

`inputs/dimensions.json` 的 override 優先於 HTML `data-*-mm`。只有所有 cell 都不再是 `auto` 時，才可聲稱 `blueprint-precise-mm`；否則應標示 `mixed-provenance`。

檢視哪些值可由現有文字回填：

```bash
python scripts/seed_dimension_overrides.py --dry-run
```

建立 override 與待量測清單：

```bash
python scripts/seed_dimension_overrides.py
```

輸出：

- `inputs/dimensions.json`
- `structured/dimension_todo.md`

`--force` 會重新整理可推導項目並保留 measured entry，仍應先檢查現有人工量測資料。

`scripts/annotate_html_geometry.py` 會直接修改 canonical HTML、補上推估 metadata。只有確定要更新歷史來源時才執行：

```bash
python scripts/annotate_html_geometry.py
```

預設不處理 `*_tmp.html`；`--include-tmp` 會把暫存檔也納入，通常不建議。

## 9. 歷史一鍵專家流程與 Claude Code 指令

以下流程只服務 HTML 歷史分支，輸出到 `structured/expert_review/`，不要和現行的 `structured/reviews/<revision>/` 混用。

PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode concept `
  -Buildings A,B,C `
  -Selection auto `
  -DrawingStyle presentation
```

歷史 PDF：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
  -Selection baseline `
  -DrawingStyle presentation `
  -Paper a3
```

歷史 strict gate：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode release `
  -Buildings A,B,C `
  -Selection baseline `
  -DrawingStyle technical
```

此流程會執行舊 requirement normalization、expert gate、HTML consistency、pipeline、SVG validation、舊 expert report、domain checklist 與 final discussion HTML。

主要的 expert workflow 輸出：

- `structured/expert_review/request_normalized.json`：正規化後的歷史設計要求。
- `structured/expert_review/html_consistency.json`：HTML 幾何與房間綁定檢查。
- `structured/expert_review/report.json`、`report.md`：舊 expert gate 報告。
- `structured/expert_review/domain_checklist.json`、`domain_checklist.md`：屋主與各專業角色的待確認清單。
- `structured/final_design_html/index.html`：不覆蓋 canonical HTML 的討論版入口。
- `task-board.md`：歷史工作流更新的任務板。

歷史流程的人工簽核使用：

```text
structured/expert_review/signoff.yaml
```

這個 YAML 只綁定 `structured/expert_review/report.json`，不能用來簽核現行 revision review。`release` 第一次執行通常會要求更新 report hash；人工檢查後更新 YAML，再以相同指令執行第二次。

Claude Code 仍提供歷史 slash commands：

```text
/workflow-house-all-in-one inputs/design_request.md --mode concept --buildings A,B,C --selection auto --drawing-style presentation
/export-final-design-html --mode draft --buildings A,B,C --selection auto
```

`/workflow-house-all-in-one` 的舊介面仍可能顯示 `ifc`；直接呼叫 PowerShell 或 package CLI 時應改用 `release`。Slash command 不可用時，可把 `scripts/WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md` 貼給 Claude Code，但必須在 prompt 中標明這是歷史 HTML 分支。

## 10. 個別腳本功能索引

一般使用者優先使用 `python -m house_design ...` 或 PowerShell orchestrator。以下腳本適合除錯、局部重建或維護：

| 腳本 | 功能／輸出 |
|---|---|
| `scripts/annotate_html_geometry.py` | 直接替歷史 HTML 補推估幾何 metadata |
| `scripts/seed_dimension_overrides.py` | 從 HTML 尺寸文字建立 override 與待量測清單 |
| `scripts/extract_layout_data.py` | HTML → `structured/*.structured.json` |
| `scripts/build_room_program.py` | 建立 `structured/room_program.json` |
| `scripts/evaluate_architect_metrics.py` | 更新歷史概念級建築指標 |
| `scripts/generate_layout_candidates.py` | 建立 baseline／circulation／daylight／MEP 候選 |
| `scripts/render_candidate_viewer.py` | 建立候選切換 viewer |
| `scripts/export_model_3d.py` | 建立 HTML 草圖的離線 3D 量體 viewer |
| `scripts/generate_parametric_plan.py` | 建立舊 32 坪 footprint 變體與 capacity report |
| `scripts/export_walkthrough_3d.py` | 建立舊參數化 walk-in 3D |
| `scripts/export_top1_svgs.py` | 依 selection/style 匯出穩定檔名 SVG 與 manifest |
| `scripts/export_print_bundle_pdf.py` | 依 SVG manifest 匯出 A3／A4 PDF |
| `scripts/validate_layout_bundle.py` | 驗證 room program、manifest 與實際 SVG marker |
| `scripts/check_html_consistency.py` | 檢查歷史 HTML 幾何、房間綁定、入口與門窗資料 |
| `scripts/evaluate_expert_gates.py` | 舊 expert normalization／gate／report 實作 |
| `scripts/generate_domain_checklist.py` | 產生舊 owner／architect domain checklist |
| `scripts/export_final_design_html.py` | 產生不覆蓋 canonical HTML 的討論版快照 |

手動重建完整歷史輸出時的順序：

```bash
python scripts/check_html_consistency.py --mode draft
python scripts/extract_layout_data.py
python scripts/build_room_program.py
python scripts/evaluate_architect_metrics.py
python scripts/generate_layout_candidates.py
python scripts/render_candidate_viewer.py
python scripts/export_model_3d.py
python scripts/generate_parametric_plan.py
python scripts/export_walkthrough_3d.py
python scripts/export_top1_svgs.py --selection baseline --style presentation
python scripts/export_print_bundle_pdf.py --paper a3 --output structured/candidates/print_bundle.pdf
python scripts/validate_layout_bundle.py --strict
```

## 11. 常見失敗處理

### Intake valid，但 readiness 是 0%

這是可能且合理的狀態。`valid` 代表資料格式正確；readiness 代表地號、分區、道路、建蔽率、容積率等必要事實是否已取得。不要把 unknown 改成假數值只為提高完成度。

### Revision already exists

版次是不可變資料。不要刪除或覆蓋既有 R001；收到修正版請建立 R002，並用 `--previous R001` 產生比較。

### PDF／IFC／DXF dependency missing

```bash
python -m pip install -e ".[drawings]"
```

或：

```bash
python -m pip install -r requirements-import.txt
```

安裝完成後應以新的 revision id 重新匯入，避免把已建立的不可變 manifest 原地改寫。

### DXF status 是 needs_mapping

確認：

- 有傳入 `--mapping`。
- mapping 的 layer 名稱與 DXF 完全一致。
- 每個需要檢核的 layer 有 `kind`、`building_id`、`floor_id`。
- 需求空間有正確 `requirement_id`。
- DXF 未宣告單位時有 `dxf_unit_scale_to_mm`。

### Review 產生成功，但 release_eligible 是 false

這不是程式失敗。查看 `report.md` 或 dashboard 中的 `fail`、`unknown`、`professional_review`，依 `responsible_role` 與 `next_action` 補資料或交由專業人員確認。

### 現行 signoff 無效

確認 JSON 內的真人姓名、role、日期、revision id 與最新 `report_hash`。只要輸入、規則、圖面或 findings 改變，就應重新人工檢查並更新 hash。

### 歷史 HTML consistency critical

查看：

```text
structured/expert_review/html_consistency.json
```

常見原因：

- `highlightRoom('xxx')` 與 `id="room-xxx"` 不一致。
- 幾何 metadata 不完整或互相矛盾。
- 同一樓層有多個入口。
- 門窗尺寸超出合理範圍。

### 歷史 strict bundle validation failed

```bash
python scripts/validate_layout_bundle.py --strict
```

它會檢查 manifest 內 SVG 是否存在，以及入口、門、窗、尺寸、legend、elevation 等實際 SVG XML marker。只把文字放進 `<metadata>` 不會通過。

重新產生 SVG：

```bash
python -m house_design pipeline --mode draft --from-step svg --force
```

### 歷史 pipeline 沒有重跑預期步驟

先確認輸入是否真的改變；需要完整重建時使用：

```bash
python -m house_design pipeline --mode draft --force
```

## 12. Exit code

| Exit code | 適用流程 | 意義 |
|---:|---|---|
| `0` | 所有流程 | 命令成功執行；不等於設計合規 |
| `1` | package CLI／一般腳本 | 契約、參數、匯入、subprocess 或其他錯誤；`intake validate` 無效也回傳 1 |
| `2` | argparse／歷史 expert workflow | CLI 參數格式錯誤；或舊 YAML signoff 缺少、report hash 過期 |
| `10` | 歷史 expert workflow | 舊 expert hard gate 失敗 |

現行 `review run` 的 `release_eligible: false` 通常不會改變 exit code；請以報告欄位判讀。

## 13. 測試與品質檢查

修改 Python、CLI 或 workflow 後：

```bash
python -m pytest -q
python -m ruff check house_design scripts tests
```

修改 `structured/parametric/walkthrough.html`、`structured/candidates/model3d.html`
或其產生器後，另跑正式瀏覽器回歸：

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

Playwright 會自行在 `127.0.0.1:8770` 啟動暫存靜態站台，依序檢查桌機、
390×844 手機、棟層／房間／方案控制、HTML↔3D 對照、走入／輪椅模式、
deep link、共享 `model3d.html`、R000 現行 3D 阻擋狀態與 `file://` 離線開啟。失敗截圖與 trace 只會寫入
已忽略版控的 `test-results/playwright/`；CI 失敗時會保留七天供下載。

檢查前期閘門：

```bash
python -m house_design predesign validate
python -m house_design predesign report
```

檢查現行資料契約：

```bash
python -m house_design intake validate
```

只有在歷史 SVG 已產生時，才執行歷史 strict bundle validation：

```bash
python scripts/validate_layout_bundle.py --strict
```

修改歷史 HTML 後，至少重跑：

```bash
python -m house_design pipeline --mode concept --force
```

## 14. Claude Code 與 MCP

從專案根目錄啟動 Claude Code，才能讀取 `CLAUDE.md`、`.claude/commands/` 與 `.mcp.json`：

```powershell
cd D:\I29786\workspace\houseDesignPrepare
claude
```

進入後可用 `/mcp` 檢查 server。

Brave Search 需要 `BRAVE_API_KEY`；沒有設定不影響本機 intake、drawing import、review 或歷史出圖。PowerShell 範例：

```powershell
$env:BRAVE_API_KEY = "your_key"
claude
```

MCP 無法啟動時確認：

- 從專案根目錄啟動。
- Node、npm、npx 可執行。
- Brave Search 已取得 `BRAVE_API_KEY`。
- 使用 `/mcp` 查看實際錯誤。

## 15. 相關文件

- `README.md`：現行專案快速開始與資料權威摘要。
- `Docs/review-workflow.md`：現行圖面版次檢核的精簡操作流程。
- `Docs/predesign-owner-readiness.md`：選地、設計、發包、施工與交屋的不後悔指南。
- `structured/CURRENT_STATUS.md`：目前資料完成度與 R000 驗收狀態。
- `CLAUDE.md`：專案架構、限制與歷史分支細節。
- `scripts/README.md`：各歷史 pipeline 腳本詳細說明。
- `scripts/WORKFLOW_ALL_IN_ONE_PROMPT.zh-TW.md`：歷史 slash command 備援 prompt。
- `scripts/WEB_TO_PLAN_PROMPTS.zh-TW.md`：歷史 HTML 修改與出圖 prompt 範本。

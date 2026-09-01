# 圖面版次檢核工作流

## 1. 先完成前期閘門

土地尚未確定時，不要先把格局當成可建方案：

```bash
python3 -m house_design predesign validate
python3 -m house_design predesign report
```

查看 `structured/predesign/report.md`。家庭任務書、總預算上限、選地淘汰條件與候選土地初篩未完成時，不應進入格局定案。

精確預算請從 `inputs/budget.private.template.json` 複製到 `inputs/private/budget.json`；後者已被 Git 忽略。

## 2. 候選土地與基地事實

`inputs/project.json` 的三筆相鄰、每筆約 32 坪是選地目標。候選土地可從 `inputs/site-candidate.template.json` 建立；選定並通過書面查核後，才將正式三筆資料寫入 `site_search.selected_site.parcels`。

在正式 parcel 記錄填入地號、地籍面積、使用分區、道路、建蔽率、容積率與退縮，並保留來源。未取得的欄位維持 `null` 或 `status: unknown`。

```bash
python3 -m house_design intake validate
```

## 3. 確認需求

`inputs/requirements.json` 目前有 64 項由舊 brief 匯入的想法，全部是 `candidate`。逐項改成：

- `confirmed`：屋主已決定，才參與圖面硬檢核。
- `rejected`：明確淘汰並保留 decision log。
- `candidate`：仍在討論，不得產生硬失敗。

每項再設定 `must`、`should` 或 `could`。`must` 不符合會是失敗；`should`／`could` 會保留為警告或取捨。

用指令追加不可改寫的決策鏈，不要手動刪除歷史：

```bash
python3 -m house_design intake requirements-decide \
  --id A.floor-1.elder --status confirmed --priority must \
  --reason "一樓完整照護生活" --decided-by "屋主家庭會議"
```

## 4. 匯入不可變圖面版次

推薦 PDF＋IFC：

```bash
python3 -m house_design drawings import \
  --revision R001 --label "初步設計" \
  --pdf drawings/R001.pdf --ifc drawings/R001.ifc
```

DXF 需要 mapping JSON：

```json
{
  "schema": "house-drawing-mapping-v2",
  "dxf_unit_scale_to_mm": 1.0,
  "coordinate_system": {
    "status": "verified",
    "axis": {"x": "drawing-east", "y": "drawing-north", "z": "up"},
    "verified_by": "王建築師", "verified_at": "2026-08-31",
    "method": "共同控制點核對",
    "reference_points": [
      {"id": "P1", "source_mm": [0, 0], "project_mm": [0, 0]},
      {"id": "P2", "source_mm": [6000, 0], "project_mm": [6000, 0]}
    ]
  },
  "storeys": [{
    "building_id": "A", "floor_id": "floor-1", "elevation_mm": 0,
    "verified_by": "王建築師", "verified_at": "2026-08-31",
    "evidence": {"type": "drawing_level_note", "reference": "A-101 / EL±0"}
  }],
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
      "opening_width": {
        "value_mm": 900, "measurement": "finished_clear",
        "verified_by": "王建築師", "verified_at": "2026-08-31",
        "evidence": {"type": "door_schedule", "reference": "D01"}
      }
    }
  }
}
```

```bash
python3 -m house_design drawings import \
  --revision R001 --label "初步設計" \
  --pdf drawings/R001.pdf --dxf drawings/R001.dxf --mapping drawings/R001.mapping.json
```

版次一旦建立就不能覆寫；設計方更新圖面時使用 R002、R003 等新 id。PDF／IFC／DXF、mapping、normalized model 與 manifest seal 都會驗證。先執行 `python3 -m house_design drawings verify --revision R001`；compare、review 與 3D 也會自動先驗證。

IFC 的棟名必須有獨立的 A／B／C 標記（例如 `A棟` 或 `Building A`），樓層名建議使用 `1F`、`2F`、`3F`、`RF`。系統會保留 IFC `OverallWidth`，但它是名目寬度，不會直接當成完工後門淨寬；沒有門窗表、可信 property 或明確 DXF 開口證據時，門淨寬必須維持 `unknown`。

## 5. 檢核與比較

先確認這一版能否作為現行 3D 的輸入：

```bash
python3 -m house_design drawings model3d-readiness --revision R001 --level space_block
```

若回傳 `blocked`／exit code 1，依 `blockers[].next_action` 補齊權威空間幾何、棟層位置、樓層標高與座標證據，並以新 revision id 重新匯入。`--level walkthrough` 還要求精確空間 polygon、牆、門窗高度、樓梯與設備；歷史 walkthrough 不會被當成現行版次的替代品。

通過後產生清楚標示用途界線的現行空間量體：

```bash
python3 -m house_design drawings export-model3d --revision R001
```

```bash
python3 -m house_design review run --revision R001 --previous R000
```

輸出：

- `report.json`：機器可讀 finding、證據、責任人、狀態與 3D readiness。
- `report.md`：逐項會議清單與 3D 阻擋原因。
- `meeting-report.pdf`：可列印會議報告，摘要包含 3D readiness。
- `index.html`：完全離線的互動檢核儀表板，明示現行 revision 3D 是 blocked 或 ready。

結果狀態是 `pass`、`fail`、`warning`、`unknown`、`not_applicable`、`professional_review`。只要仍有 fail、unknown 或 professional_review，就不能宣稱整體合規。

review 會同時合併前期到期閘門；未到施工／交屋階段的未完成項目只保留為未來計畫，不會提早形成硬阻擋。

## 6. 人工簽核

複製 `inputs/signoff.template.json`，由真人專業人員填入姓名、角色、版次與最新 `report_hash`。AI 身分、不同版次或舊雜湊都會失效。

```bash
python3 -m house_design review run --revision R001 --signoff inputs/signoff.R001.json
```

簽核只代表該人員對該版報告的決定，不取代建照審查、結構計算、消防、機電或其他依法簽證程序。

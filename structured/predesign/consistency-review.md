# 三棟資料一致性查核

一致性不等於設計可行、法規合規或專業驗收；資料不足不可當成通過。

## 一致 · 實物與需求棟層對應
來源：inputs/physical-items.json
```json
"B.palanquin.primary"
```

## 資料不足 · 實物仍為規劃估值
來源：inputs/physical-items.json
```json
"B.palanquin.primary"
```

## 資料不足 · 組裝搬運外廓尚未實測
來源：inputs/physical-items.json
```json
"B.palanquin.primary"
```

## 資料不足 · 需求與歷史格位尚未有完整明確映射
來源：inputs/requirements.json / inputs/furniture-layout.json
```json
"不得依相似房名套用家具或幾何；歷史容量與需求卡分開顯示。"
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：AbuildingView.html
```json
{
  "building": "A",
  "floor": "floor-1",
  "message": "前院車庫 states 33.0 m² but its geometry is 13.2 m²",
  "evidence": "cell-1: text='約 5.5m × 6.0m（示意）'; 11000x1200mm; ratio=0.40",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：AbuildingView.html
```json
{
  "building": "A",
  "floor": "floor-1",
  "message": "客廳 states 16.5 m² but its geometry is 9.5 m²",
  "evidence": "cell-3: text='約 5 坪（示意）'; 7333x1300mm; ratio=0.58",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：AbuildingView.html
```json
{
  "building": "A",
  "floor": "floor-1",
  "message": "廚房 states 9.9 m² but its geometry is 7.8 m²",
  "evidence": "cell-8: text='約 3 坪（示意）'; 6000x1300mm; ratio=0.79",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：AbuildingView.html
```json
{
  "building": "A",
  "floor": "floor-1",
  "message": "多功能房/客房 states 13.2 m² but its geometry is 6.5 m²",
  "evidence": "cell-9: text='約 3.5–4 坪'; 5000x1300mm; ratio=0.49",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：AbuildingView.html
```json
{
  "building": "A",
  "floor": "floor-2",
  "message": "主臥室 states 19.8 m² but its geometry is 8.1 m²",
  "evidence": "cell-1: text='約 6 坪'; 7333x1100mm; ratio=0.41",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：AbuildingView.html
```json
{
  "building": "A",
  "floor": "floor-3",
  "message": "娛樂室/家庭劇院 states 26.4 m² but its geometry is 12.1 m²",
  "evidence": "cell-1: text='約 6–8 坪'; 11000x1100mm; ratio=0.46",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · CELL_OVERLAP
來源：AbuildingView.html
```json
{
  "building": "A",
  "floor": "floor-4",
  "message": "VF800 overlaps Haier 熱泵",
  "evidence": "cell-3 vs cell-4",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 資料不足 · HTML 靜態查核 · FOOTPRINT_INCONSISTENT
來源：AbuildingView.html
```json
{
  "building": "A",
  "floor": "<building>",
  "message": "Floor envelopes differ across 3 floors (width spread 0mm, depth spread 2500mm)",
  "evidence": "floor-1=11000x7700mm; floor-2=11000x5200mm; floor-3=11000x5200mm",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：CbuildingView.html
```json
{
  "building": "C",
  "floor": "floor-1",
  "message": "客廳 states 26.4 m² but its geometry is 9.3 m²",
  "evidence": "cell-3: text='約 8 坪'; 5500x1700mm; ratio=0.35",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：CbuildingView.html
```json
{
  "building": "C",
  "floor": "floor-1",
  "message": "孝親房 states 16.5 m² but its geometry is 10.2 m²",
  "evidence": "cell-8: text='約 5 坪｜長輩友善'; 7857x1300mm; ratio=0.62",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：CbuildingView.html
```json
{
  "building": "C",
  "floor": "floor-2",
  "message": "客廳（主角空間） states 28.1 m² but its geometry is 14.3 m²",
  "evidence": "cell-2: text='約 8.5 坪｜L型沙發＋電視牆＋茶几'; 11000x1300mm; ratio=0.51",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：CbuildingView.html
```json
{
  "building": "C",
  "floor": "floor-2",
  "message": "廁所（乾濕分離） states 9.3 m² but its geometry is 12.1 m²",
  "evidence": "cell-6: text='約 2.8 坪｜對齊 3F 管道'; 11000x1100mm; ratio=1.31",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 資料不足 · HTML 靜態查核 · FLOOR_COVERAGE_VOID
來源：CbuildingView.html
```json
{
  "building": "C",
  "floor": "floor-2",
  "message": "12.0 m² of the floor envelope is not covered by any cell",
  "evidence": "envelope=77.0 m² (11000x7000mm); void=16%",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：CbuildingView.html
```json
{
  "building": "C",
  "floor": "floor-3",
  "message": "主臥室（飯店級配置） states 38.0 m² but its geometry is 14.3 m²",
  "evidence": "cell-2: text='約 11.5 坪｜雙人床＋梳妝台＋衣櫃×4'; 11000x1300mm; ratio=0.38",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：CbuildingView.html
```json
{
  "building": "C",
  "floor": "floor-3",
  "message": "運動空間 states 14.9 m² but its geometry is 9.5 m²",
  "evidence": "cell-3: text='約 4.5 坪｜跑步機/瑜伽/重訓'; 7333x1300mm; ratio=0.64",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · AREA_TEXT_MISMATCH
來源：CbuildingView.html
```json
{
  "building": "C",
  "floor": "floor-3",
  "message": "廁所（乾濕分離） states 9.3 m² but its geometry is 12.1 m²",
  "evidence": "cell-5: text='約 2.8 坪｜夜間方便使用'; 11000x1100mm; ratio=1.31",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 資料不足 · HTML 靜態查核 · FLOOR_COVERAGE_VOID
來源：CbuildingView.html
```json
{
  "building": "C",
  "floor": "floor-3",
  "message": "8.2 m² of the floor envelope is not covered by any cell",
  "evidence": "envelope=53.9 m² (11000x4900mm); void=15%",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 矛盾 · HTML 靜態查核 · CELL_OVERLAP
來源：CbuildingView.html
```json
{
  "building": "C",
  "floor": "floor-4",
  "message": "加壓系統 overlaps 熱泵熱水器",
  "evidence": "cell-4 vs cell-5",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 資料不足 · HTML 靜態查核 · FOOTPRINT_INCONSISTENT
來源：CbuildingView.html
```json
{
  "building": "C",
  "floor": "<building>",
  "message": "Floor envelopes differ across 3 floors (width spread 0mm, depth spread 2100mm)",
  "evidence": "floor-1=11000x7000mm; floor-2=11000x7000mm; floor-3=11000x4900mm",
  "limitation": "示意格位警示，不等於實際設計或法規違規；退縮與留白需確認設計意圖。"
}
```

## 資料不足 · A 棟客餐廳提案與原 HTML 版本不同
來源：AbuildingView.html / inputs/requirements.json
```json
"原 HTML 客廳與餐廳分開；需求 A.floor-1.living 為合併客餐廳提案，仍待確認。保留兩版，不自動合併、移動或匹配家具。"
```

## 資料不足 · 原始 HTML 未提供完整家具映射
來源：AbuildingView.html
```json
"無可解析家具比例覆層；不代表內容通過"
```

## 一致 · HTML／來源家具尺寸
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:ceremonial-storage",
  "axes_checked": [
    "width_mm",
    "depth_mm",
    "height_mm"
  ]
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:ceremonial-storage",
  "field": "data-x-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:ceremonial-storage",
  "field": "data-y-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:ceremonial-storage",
  "field": "data-rotation-deg"
}
```

## 一致 · HTML／來源家具尺寸
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:ritual-cabinet",
  "axes_checked": [
    "width_mm",
    "depth_mm",
    "height_mm"
  ]
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:ritual-cabinet",
  "field": "data-x-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:ritual-cabinet",
  "field": "data-y-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:ritual-cabinet",
  "field": "data-rotation-deg"
}
```

## 一致 · HTML／來源家具尺寸
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:fireproof-cabinet",
  "axes_checked": [
    "width_mm",
    "depth_mm",
    "height_mm"
  ]
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:fireproof-cabinet",
  "field": "data-x-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:fireproof-cabinet",
  "field": "data-y-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:fireproof-cabinet",
  "field": "data-rotation-deg"
}
```

## 一致 · HTML／來源家具尺寸
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:prep-table",
  "axes_checked": [
    "width_mm",
    "depth_mm",
    "height_mm"
  ]
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:prep-table",
  "field": "data-x-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:prep-table",
  "field": "data-y-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:prep-table",
  "field": "data-rotation-deg"
}
```

## 一致 · HTML／來源家具尺寸
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:dehumidifier",
  "axes_checked": [
    "width_mm",
    "depth_mm",
    "height_mm"
  ]
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:dehumidifier",
  "field": "data-x-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:dehumidifier",
  "field": "data-y-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:storage:furniture:dehumidifier",
  "field": "data-rotation-deg"
}
```

## 一致 · HTML／來源家具尺寸
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:altar",
  "axes_checked": [
    "width_mm",
    "depth_mm",
    "height_mm"
  ]
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:altar",
  "field": "data-x-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:altar",
  "field": "data-y-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:altar",
  "field": "data-rotation-deg"
}
```

## 一致 · HTML／來源家具尺寸
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:offering-table",
  "axes_checked": [
    "width_mm",
    "depth_mm",
    "height_mm"
  ]
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:offering-table",
  "field": "data-x-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:offering-table",
  "field": "data-y-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:offering-table",
  "field": "data-rotation-deg"
}
```

## 一致 · HTML／來源家具尺寸
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:bench-left",
  "axes_checked": [
    "width_mm",
    "depth_mm",
    "height_mm"
  ]
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:bench-left",
  "field": "data-x-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:bench-left",
  "field": "data-y-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:bench-left",
  "field": "data-rotation-deg"
}
```

## 一致 · HTML／來源家具尺寸
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:bench-right",
  "axes_checked": [
    "width_mm",
    "depth_mm",
    "height_mm"
  ]
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:bench-right",
  "field": "data-x-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:bench-right",
  "field": "data-y-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:bench-right",
  "field": "data-rotation-deg"
}
```

## 一致 · HTML／來源家具尺寸
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:shoe-cabinet",
  "axes_checked": [
    "width_mm",
    "depth_mm",
    "height_mm"
  ]
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:shoe-cabinet",
  "field": "data-x-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:shoe-cabinet",
  "field": "data-y-ratio"
}
```

## 一致 · HTML／來源家具比例位置
來源：BbuildingView.html
```json
{
  "id": "B:floor-1:shrine:furniture:shoe-cabinet",
  "field": "data-rotation-deg"
}
```

## 資料不足 · 原始 HTML 未提供完整家具映射
來源：CbuildingView.html
```json
"無可解析家具比例覆層；不代表內容通過"
```

## 一致 · 歷史 3D 是否使用當前格位與家具來源
來源：structured/candidates/model3d.html
```json
"比較 ID、名稱、格位尺寸、來源狀態及家具配置；非合規檢查"
```

## 矛盾 · 不可變圖版完整性
來源：inputs/revisions/R000/manifest.json
```json
{
  "schema": "house-revision-integrity-v1",
  "revision_id": "R000",
  "checked_at": "2026-10-05T01:53:07.343634+00:00",
  "valid": false,
  "checks": [
    {
      "name": "manifest_revision_id",
      "valid": true,
      "message": "manifest revision_id matches the requested immutable directory"
    },
    {
      "name": "source[0]",
      "valid": false,
      "message": "source file is missing or its SHA-256 does not match",
      "details": {
        "file": "structured/parametric/plan.json",
        "expected_sha256": "44dca801266f1f76d403b010765fcc3377073e22532ce08344e1c4c651b014a8",
        "actual_sha256": "30b94dc0e660484155c96b0d1984f546c38a228cf42f8da6b1bc4fe867d1dfae"
      }
    },
    {
      "name": "normalized_model_sha256",
      "valid": true,
      "message": "normalized model digest matches",
      "details": {
        "file": "inputs/revisions/R000/normalized_model.json",
        "expected_sha256": "266c010a0792bb9a72a9afd902f022f5e8f2ccf7074da04a32080be3ba6c793b",
        "actual_sha256": "266c010a0792bb9a72a9afd902f022f5e8f2ccf7074da04a32080be3ba6c793b"
      }
    },
    {
      "name": "model_revision_id",
      "valid": true,
      "message": "normalized model revision_id matches"
    },
    {
      "name": "content_hash",
      "valid": true,
      "message": "manifest seal matches",
      "details": {
        "expected_sha256": "64fd89a3fbc2e4c974db94152ac6853f08c78ba5457155e07242d8fc221a9bb3",
        "actual_sha256": "64fd89a3fbc2e4c974db94152ac6853f08c78ba5457155e07242d8fc221a9bb3"
      }
    }
  ],
  "errors": [
    {
      "name": "source[0]",
      "valid": false,
      "message": "source file is missing or its SHA-256 does not match",
      "details": {
        "file": "structured/parametric/plan.json",
        "expected_sha256": "44dca801266f1f76d403b010765fcc3377073e22532ce08344e1c4c651b014a8",
        "actual_sha256": "30b94dc0e660484155c96b0d1984f546c38a228cf42f8da6b1bc4fe867d1dfae"
      }
    }
  ]
}
```

## 矛盾 · R000 原來源已偏離封存雜湊
來源：inputs/revisions/R000/manifest.json
```json
{
  "file": "structured/parametric/plan.json",
  "expected": "44dca801266f1f76d403b010765fcc3377073e22532ce08344e1c4c651b014a8",
  "actual": "30b94dc0e660484155c96b0d1984f546c38a228cf42f8da6b1bc4fe867d1dfae",
  "historical_candidate": {
    "reference": "git HEAD:structured/parametric/plan.json",
    "sha256": "44dca801266f1f76d403b010765fcc3377073e22532ce08344e1c4c651b014a8",
    "matches_manifest": true
  },
  "action": "保存現況；從可信歷史版本／備份比對原來源。若無法復原，保留異常，另經授權建立新版本；不得改 manifest。"
}
```

# 實物統計與量測輸入

`inputs/physical-items.json` 是家具、設備與特殊大型物件的集中尺寸來源。它保存兩種資料，但不混用：

- `planning_dimensions`：尚未量測時用於容量測試的規劃暫估值。
- `measurements`：實際量測紀錄；有資料後，最後一筆完整紀錄會成為 3D 使用尺寸。

每筆尺寸固定使用毫米，欄位為 `width_mm`、`depth_mm`、`height_mm`。三個方向必須一次填完整，系統不會把某一方向的實測值和其他方向的估值拼在一起。

## 目前登錄

| ID | 實物 | 規劃尺寸（寬 × 深 × 高） | 狀態 | 使用位置 |
|---|---|---:|---|---|
| `B.palanquin.primary` | 武轎（收納狀態） | 1200 × 1700 × 1800 mm | 一般尺寸暫估、待實測 | B 棟 1F 武轎儲藏室 |

這是規劃外廓，不是武轎製作規格。`transport.door_clear_target_mm` 暫列 1500 mm；抬桿裝妥後的搬運外廓、抬桿能否拆卸及轉角需求仍是未知，不可用收納外廓代替。

## 完成實測後輸入

以下指令會原子寫入一筆新紀錄，舊的量測紀錄會保留；3D 會使用最後一筆：

```bash
.venv/bin/python -m house_design intake physical-item-measure \
  --id B.palanquin.primary \
  --width-mm 1260 --depth-mm 1740 --height-mm 1830 \
  --measured-by "屋主" \
  --measured-at "2026-10-01" \
  --method "捲尺量最大外廓" \
  --note "包含固定裝飾，不含可拆抬桿"
```

輸入後驗證並重建歷史 3D 容量檢視：

```bash
.venv/bin/python -m house_design intake validate
.venv/bin/python scripts/export_model_3d.py
```

## 新增其他實物

在 `items` 陣列新增一筆，至少填寫：

- 穩定且唯一的 `id`。
- 名稱、分類、數量與預定棟層／需求 ID。
- 完整的規劃寬、深、高。
- 空的 `measurements` 陣列。
- 規劃值來源與限制說明。

適合列入的項目包括神桌、神轎、祖龕、大型家具、輪椅、照護床、機櫃、鋼琴、健身器材及屋頂大型設備。一般可隨意更換的小家具仍留在 `inputs/furniture-layout.json`，不必全部升格成實物紀錄。

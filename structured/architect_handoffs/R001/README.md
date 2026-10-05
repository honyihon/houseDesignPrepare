# R001 建築師圖面交付需求

> 目前土地尚未選定；本包是未來圖面交付契約，不是開始定案或施工授權。

## 必交檔案

- 同一版次的 PDF 圖冊。
- 優先提供 IFC；若只有 DWG，請另存 DXF。IFC 與 DXF 可同時提供，但跨格式合併只接受明確 IFC GlobalId。
- 填妥 `delivery.json` 與 `mapping.json`；所有檔案應放在本目錄內並使用相對路徑。
- 前身 A／B／C HTML 位於 `legacy-reference/`，只用來討論房間需求與名稱，不是基地、權威幾何或合規證據。

## 必須可追溯的模型資料

- 棟別只使用：A, B, C。
- 預期棟層：A floor-1、A floor-2、A floor-3、A floor-rf、B floor-1、B floor-2、B floor-3、B floor-rf、C floor-1、C floor-2、C floor-3、C floor-rf。
- 每個 IfcSpace 或 DXF 閉合空間需有棟別、樓層、名稱；能對應屋主需求時填 `requirement_id`。
- 座標需寫明單位、軸向、查核人、日期、方法及至少兩個共同基準點。
- 樓層需提供 `elevation_mm`、層高、查核人、日期及圖號證據；1F 也要明列 0 mm 基準。
- 走入式模型另需：精確空間 polygon、牆、樓梯、門窗位置與高度、固定設備位置或經查核的不適用聲明。
- 門窗幾何外框不可自動當成完工淨寬；淨寬必須標示量測型態並附門窗表／圖號證據。

## 交回前檢查

將檔案放入本包並更新 `delivery.json` 後，在專案根目錄執行：

```bash
.venv/bin/python -m house_design drawings preflight --package structured/architect_handoffs/R001
```

preflight 使用暫存目錄試匯入，不會建立或覆寫 `inputs/revisions/R001`。通過後才執行正式不可變匯入；若要修改圖面，使用新的 revision id，不得覆寫既有版次。

## 狀態解讀

- `ready_for_import`：檔案格式、mapping 與語意足以建立正常版次。
- `ready_for_space_block`：可產生有來源追溯的空間量體 3D。
- `ready_for_walkthrough`：牆、開口、樓梯、高度及設備範圍也完整；仍不等於法規或施工簽證。

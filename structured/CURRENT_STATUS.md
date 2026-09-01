# 現行專案狀態

土地尚未確定。現行條件是在高雄尋找三筆相鄰、每筆約 32 坪的土地；這是選地目標，不是已取得基地或可建量體。`structured/parametric/` 與 `structured/candidates/` 都是歷史假設／草圖輸出，不是可建量體或合規結論。

請從以下資料開始：

- `inputs/project.json`：基地事實與未知欄位。
- `inputs/predesign.json`：家庭、預算、選地到交屋的階段閘門。
- `inputs/requirements.json`：64 項待屋主逐條確認的既有想法。
- `inputs/revisions/`：不可變 PDF／IFC／DXF 圖面版次。
- `structured/reviews/<revision>/index.html`：現行離線檢核儀表板。
- `structured/predesign/report.md`：現在該做與後續預留事項。

目前 `R000` 只用來證明舊的「每層建築面積 32 坪」假設已被攔截，不得放行。

## 2026-08-31 不可變版次、現行 3D 與屋主流程

- `drawings verify` 會核對 revision id、每個 source、mapping、normalized model SHA-256、model revision id 與 manifest content seal；compare、review、3D readiness 與 exporter 會先執行同一完整性檢查。R000 已補 model hash 且目前驗證有效。
- DXF mapping 已升級為 `house-drawing-mapping-v2`：已驗證座標必須帶查核人、日期、方法與至少兩個控制點；樓層標高必須帶人員、日期與圖號證據。閉合 polyline 保留 polygon 並計算實際面積，門窗 bbox 只算名目／overall 寬度，不能自動冒充完工淨寬。
- IFC 空間可在 IfcOpenShell 幾何可用時擷取 display hull；IFC／DXF 合併只接受明確 `ifc_guid`，不以名稱猜測重複空間。端到端合成 R001 已證明：匯入 `ready`、seal 有效、凹形 polygon 10.0 m²、門淨寬證據 900 mm、review 與 exporter 全流程成功。
- 3D readiness 分成 `space_block` 與 `walkthrough`。前者只允許產生明確標示用途界線的「空間量體模型」；後者另要求精確 polygon、牆、門窗高度、樓梯與設備。dashboard 只有在量體 readiness 通過且 `model3d.html` 確實存在時才建立連結。
- `AbuildingView.html`、`BbuildingView.html`、`CbuildingView.html` 保留為原始房間配置的討論來源；`structured/candidates/model3d.html` 提供棟別、樓層、房間可分享定位與返回原 HTML 房間的雙向對照。`structured/parametric/walkthrough.html` 則明確維持為不同 6–10 m 尺度的歷史參數情境，兩者不可混作現行設計或施工依據。
- 歷史 walkthrough 行動版可收合控制面板，canvas 已有可存取名稱；dashboard 行動版改為兩列緊湊導覽、棟層樹預設收合，modal 支援 Escape、焦點限制與焦點回復。
- 新增 `intake requirements-decide` 的原子更新與 hash-chained decision log，以及 `inputs/household-profile.template.json`。64 項既有需求仍維持 `candidate`，尚未被擅自替屋主做決策。
- 前期規則由 35 增至 39 項，新增整體結構／耐震／強風／地工、避難與祭祀用火、1F 完整生活與垂直移動、健康材料／IAQ／濕黴蟲害／腐蝕四個設計期閘門；目前仍是 site_search，因此到期完成度維持 30%、5 個硬阻擋。
- CI 改用 Node 24 action v7、editable package install、跨平台矩陣 `fail-fast: false`、核心 Ruff 範圍與獨立真實 PDF＋DXF job；`svglib` 固定 1.5.1，避免 1.6 的 pycairo 原生編譯鏈。
- 自動驗證：159 pytest passed、Ruff passed、Playwright 17/17 passed、`pip check` passed、npm audit 0 vulnerabilities；桌面 1440×900、行動 390×844、現行量體互動與歷史 `file://` 均完成回歸。

R000 的判定仍是 `blocked`：99 個空間都有歷史 bbox，但 0 個屬權威可渲染幾何；12 個樓層中 0 個有標高，座標是 `local_assumed`，另有舊 footprint blocking issue。歷史 3D 只供回顧，不會冒充現行圖面。

## 2026-08-28 前期整合驗收

- 前期到期項目完成度 30%，5 個硬阻擋：家庭 20 年情境、預算上限、預算範圍／備用金、選地淘汰條件、土地選定。
- 整合後 R000：1 失敗、2 警告、12 未知、10 專業確認、3 通過；基地資料完成度 0%，`release_eligible: false`。
- 64 項舊想法全部維持 `candidate`，尚未被系統當成屋主硬需求。
- 實際格式的合成 PDF＋IFC＋DXF smoke import 為 `ready`；mapping 已複製進不可變版次並記錄 SHA-256，IFC 可解析 A 棟／1F 空間位置。
- 原 dashboard 曾完成桌面 1440 × 1024 與行動 390 × 844 驗收；本次新增前期階段卡片已由自動測試確認嵌入，仍建議下次有瀏覽器測試環境時補視覺回歸。
- 歷史 concept 已在隔離副本完整重跑；12 層 SVG、兩個 3D viewer 與候選 viewer 產生成功。84 個格位中 69 個（82.1%）仍是自動推估、35 個 declared overlap，舊參數化情境有 18 層容量超出，因此不得作為設計或可建結論。
- 自動驗證：129 tests passed、Ruff passed；現行 intake、predesign、R000 review 與隔離歷史 concept 均成功。
- 視覺比對與刻意差異見 `Docs/design/house-review-dashboard-fidelity.md`。

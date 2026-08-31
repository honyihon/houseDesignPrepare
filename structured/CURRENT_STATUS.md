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

## 2026-08-31 現行 revision 3D 閘門

- 新增 `drawings model3d-readiness`：版次被阻擋時仍輸出完整 JSON，並以 exit code 1 讓 CI／自動流程停止。
- R000 的判定是 `blocked`：99 個空間都有歷史 bbox，但 0 個屬權威可渲染幾何；12 個樓層中 0 個有標高，座標是 `local_assumed`，另有舊 footprint blocking issue。
- R000 report、Markdown、會議 PDF 與 dashboard 已重建；dashboard 不會把歷史 walkthrough 連結或冒充為現行 3D，並列出六項穩定 blocker code 與下一步。
- 1440 × 900 桌面與 390 × 844 手機已用 Playwright 截圖檢視；修正側欄跳轉會被 sticky header 遮住的問題後，標題、狀態、指標與阻擋原因均可讀。
- 自動驗證：142 pytest passed、Ruff passed、Playwright 10/10 passed、npm audit 0 vulnerabilities，既有歷史 3D 與 `file://` 離線流程未回歸。

## 2026-08-28 前期整合驗收

- 前期到期項目完成度 30%，5 個硬阻擋：家庭 20 年情境、預算上限、預算範圍／備用金、選地淘汰條件、土地選定。
- 整合後 R000：1 失敗、2 警告、12 未知、10 專業確認、3 通過；基地資料完成度 0%，`release_eligible: false`。
- 64 項舊想法全部維持 `candidate`，尚未被系統當成屋主硬需求。
- 實際格式的合成 PDF＋IFC＋DXF smoke import 為 `ready`；mapping 已複製進不可變版次並記錄 SHA-256，IFC 可解析 A 棟／1F 空間位置。
- 原 dashboard 曾完成桌面 1440 × 1024 與行動 390 × 844 驗收；本次新增前期階段卡片已由自動測試確認嵌入，仍建議下次有瀏覽器測試環境時補視覺回歸。
- 歷史 concept 已在隔離副本完整重跑；12 層 SVG、兩個 3D viewer 與候選 viewer 產生成功。84 個格位中 69 個（82.1%）仍是自動推估、35 個 declared overlap，舊參數化情境有 18 層容量超出，因此不得作為設計或可建結論。
- 自動驗證：129 tests passed、Ruff passed；現行 intake、predesign、R000 review 與隔離歷史 concept 均成功。
- 視覺比對與刻意差異見 `Docs/design/house-review-dashboard-fidelity.md`。

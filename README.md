# House Design Prepare

這個專案現在以「未來收到建築師圖面後，可以快速、可追溯地重跑檢核」為核心。

目前土地尚未確定。目標是在高雄尋找三筆相鄰土地，A／B／C 每筆約 32 坪；這只是選地目標，不是實際基地面積，更不是每層可蓋面積。土地、地號、使用分區、道路、建蔽率、容積率與退縮未確認之前，系統只會顯示未知，不會假裝合規。

## 快速開始

屋主離線填答、房間卡、會議／變更紀錄及實物量測：先執行 `predesign owner-workspace` 與 `predesign consistency-review`，開啟 `structured/predesign/owner-workspace.html`。草稿下載後預覽匯入，`--apply` 才寫入，詳見 [屋主工作台操作](Docs/owner-workspace.md)。

既有三棟預先設計 HTML 可繼續使用；手機圖文重疊已修正，版本差異與尺寸限制保留提示，詳見 [原 HTML 使用範圍](Docs/original-html-usability.md)。

地籍資料還沒取得時，可先用 [地籍資料前準備流程](Docs/pre-land-evidence-workflow.md) 備妥逐筆基地、逐棟機能、跨基地管線與預算證據欄位。候選地容量試算新增 `--parcel`，不再將三筆總面積套到單棟。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m house_design intake validate
.venv/bin/python -m house_design predesign validate
.venv/bin/python -m house_design predesign report
.venv/bin/python -m house_design predesign brief
.venv/bin/python -m house_design review run --revision R000
```

先閱讀 `structured/predesign/report.md` 與 `Docs/predesign-owner-readiness.md`。打開 `structured/reviews/R000/index.html` 可查看離線儀表板；R000 是舊「每層 32 坪」假設的封存示範，預期會被阻擋。

## 需求決策與設計任務書

`inputs/requirements.json` 的 66 項想法全部是 `candidate`，由屋主逐條決定後才會成為設計條件。開會時建議用決策表批次處理：

```bash
.venv/bin/python -m house_design intake requirements-sheet
# 會中填好 decision_status／decision_priority／reason 後：
.venv/bin/python -m house_design intake requirements-decide \
  --batch structured/predesign/requirements-sheet.json --decided-by "屋主家庭會議"
.venv/bin/python -m house_design predesign brief
```

`predesign brief` 產生 `structured/predesign/design-brief.json／.md／.html`，依「已確認／待屋主決定／已淘汰」分段，供建築師與設計師討論；家庭概況只輸出去識別化統計。交付包可用 `drawings prepare-handoff --brief structured/predesign/design-brief.json` 附上經雜湊驗證的任務書快照。

## 舊草圖的設計討論入口

- `AbuildingView.html`、`BbuildingView.html`、`CbuildingView.html`：原始房間格位與需求說明。
- `structured/candidates/model3d.html`：逐格讀取上述 HTML 座標的主要 3D 對照，可從 HTML 樓層／房間雙向定位；第一版另放入 70 個空間、157 件比例家具／設備，可切換顯示並檢查越界／碰撞。
- `structured/parametric/walkthrough.html`：會依 6–10 m 開間重新排房的另一個歷史容量情境；只有主版本 `f6000_g1` 的 B 棟固定對齊 `concept-safety-v1`，其餘仍不代表原 HTML 格局。

這三項都不是現行可建或施工設計。原設計 3D 的分享連結使用
`#building=A&floor=floor-1&room=A:floor-1:living&view=plan`；道路／前方固定對應 HTML 平面上方 `y=0`。
家具配置可在 `inputs/furniture-layout.json` 調整，使用與限制見 `Docs/furniture-layout-v1.md`。家具維持市售尺寸；洋紅警示代表目前歷史格位容納不了，不會自動縮小掩蓋問題。

大型或既有實物統一登錄在 `inputs/physical-items.json`，操作方式見 `Docs/physical-items.md`。目前 B 棟武轎先採收納外廓 1200 × 1700 × 1800 mm 的一般規劃值並標記待實測；家具 3D 會讀取這份清單，不在兩處重複維護尺寸。
B 棟 1F 的神明堂與武轎儲藏室已在 `BbuildingView.html` 畫出和 3D 同座標、同尺寸的第一版家具配置；儲藏室暫採 1500 mm 淨開口與直進直出動線，正式門位及轉向需求仍須待實測與建築師圖面確認。

## 建築師 R001 交付包

前身來源已更正為 `/mnt/d/Desktop/houseDesign` 的四份 HTML。`structured/architect_handoffs/R001/` 已保存其逐檔 SHA-256、需求快照、PDF＋IFC／DXF 交付清單與 mapping v2 範本；目前土地未選定，因此它只是未來交付契約。

建築師交回檔案後，先做不落版的暫存試匯入：

```bash
.venv/bin/python -m house_design drawings preflight \
  --package structured/architect_handoffs/R001 \
  --output structured/architect_handoffs/R001/preflight.json
```

只有 `ready_for_space_block: true` 且專案階段允許時才正式建立 R001。完整操作與判定邊界見 `Docs/architect-r001-handoff.md`。

收到建築師圖面後：

```bash
.venv/bin/python -m pip install -e ".[drawings]"
.venv/bin/python -m house_design drawings import \
  --revision R001 --label "初步設計" \
  --pdf path/to/drawings.pdf --ifc path/to/model.ifc
.venv/bin/python -m house_design drawings verify --revision R001
.venv/bin/python -m house_design drawings model3d-readiness --revision R001
.venv/bin/python -m house_design review run --revision R001 --previous R000
.venv/bin/python -m house_design drawings export-model3d --revision R001
```

建築／裝潢圖面到齊後，可用 `review template --revision R001 --output inputs/coordination-R001.json` 建立版次綁定的套繪輸入，再以 `review run --revision R001 --coordination inputs/coordination-R001.json` 檢查家具、門扇、動線、梁管線投影與淨空。詳見 [套繪填寫及限制](Docs/coordination-review.md)。已附三棟合成示範於 `structured/examples/coordination/`；重跑請使用 `python -m scripts.demo_coordination_review --output <新的示範目錄>`，不覆寫封存示範版次。示範不是實際住宅圖面或合規結論。

若只有 2D CAD，請建築師將 DWG 另存 DXF，並以 `--mapping` 提供圖層到棟別、樓層、空間／門窗／設備的對應。
匯入時原始圖與 mapping 會一併複製、雜湊並鎖定在該版次；IFC 的名目門寬不會自動冒充完工淨寬。
3D readiness 會要求權威空間幾何、棟層位置、樓層標高與已驗證的來源座標對齊；阻擋時不會把歷史 3D 冒充現行 revision。

## 資料權威順序

三棟防漏項：執行 `python -m house_design predesign risk-review`，開啟 `structured/predesign/risk-review.html`。十二組生活／未來／故障／施工情境會連到原有需求，顯示當期待決策、後續提醒及缺證據。接著 `predesign brief`、`predesign meeting-pack` 使用同一清單；不自動確認候選需求。填寫、雜湊複核與限制見 [決策驗收總表說明](Docs/planning-register.md)。

- `inputs/project.json`：基地事實與未知資料。
- `inputs/predesign.json`：家庭、財務、選地、設計、發包、施工與交屋階段閘門。
- `inputs/private/budget.json`：不進版控的精確預算；範本是 `inputs/budget.private.template.json`。
- `inputs/requirements.json`：屋主需求狀態與決策紀錄。
- `inputs/physical-items.json`：既有大型實物的規劃尺寸與逐次實測紀錄。
- `inputs/revisions/`：不可變 PDF／IFC／DXF 圖面版次。
- `structured/reviews/`：檢核報告、會議 PDF 與離線儀表板。
- `structured/predesign/`：前期準備報告與分層研究來源。
- `structured/parametric/`、`structured/candidates/`：歷史概念情境，不是現行基準。

任何法規、結構、消防、機電與無障礙結果都必須保留法源、證據與專業責任人；程式與 AI 不能代替依法執業者簽證。

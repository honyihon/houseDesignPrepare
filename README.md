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

- `AbuildingView.html`、`BbuildingView.html`、`CbuildingView.html`：先看 ABC v2 共用配置圖；舊房間格位、坪數、系統位置與需求卡折疊為歷史對照。
- `structured/candidates/model3d.html`：主要 3D 討論入口，預設 A 棟 1F；A 棟已回補孝親房與一樓淋浴，主案不計車位，前帶可合法興建仍待核。本版共 105 個空間、61 個家具空間、129 件家具／設備、17 組冷氣配對。選房後可用「房間特寫」放大並自動剖去遮擋牆／梯段上部；只改展示，不改房間或家具尺寸，可切完整牆高核對。原 HTML 的 92 個來源格位仍保留在原格位模式。
- [C 一樓空間利用續版](Docs/c-1f-space-use-v3.md)：獨立四人餐區、對向電視客廳、240cm廚具候選与孝親房衣櫃；門外全帶暢通主案／私有庭院待核虛框可切換，候選不計家具。A／B不改配置，ABC十二層共同核對產圖。
- 照片風格外觀 v1：[三棟完整外觀](structured/candidates/model3d.html#mode=tour&view=exterior&angle=oblique)，可看單棟正面／斜角、分享連結並還原室內設定。三份 HTML 新增同源立面、材料候選與 pending；保留孝親／祭祀動線，不新增車庫、承重柱或屋頂棚架。[外觀資料與建築師清單](Docs/abc-facade-v1.md)列官方法源及候選窗問題。地籍、採光、欄杆、機電和停車均未核准。
- `structured/parametric/walkthrough.html`：會依 6–10 m 開間重新排房的另一個歷史容量情境；只有主版本 `f6000_g1` 的 B 棟固定對齊 `concept-safety-v1`，其餘仍不代表原 HTML 格局。

這三項都不是現行可建或施工設計。全層導覽使用
`#mode=tour&building=A&floor=floor-1&view=front`；原座標單房分享連結使用
`#mode=interior&building=A&floor=floor-1&room=A:floor-1:living&view=plan`（舊連結仍有效）。道路／前方固定對應 HTML 平面上方 `y=0`。
全層導覽與HTML共用同一份 `inputs/concept-layout-review.json` 固定比較框（6 × 17.63m，非地籍或可建外框）；不再自動加深房屋。A已依屋主同意的回補方向恢復孝親房、一樓淋浴與公共夜間如廁路徑，主案不計車位；B採祭祀／搬轎優先、C採照護優先，也不計車位。原停車與其他未解需求另案保留，不視為已解或取捨定案。A前帶可合法興建、建蔽及騎樓未知，完整照護與無障礙仍需完成面、輔具演練及專業核對。
版本取捨、待調整家具與冷氣安裝核對項目見 [ABC 合理性提案](Docs/abc-layout-rationality-v2.md)。家具來源在 `inputs/furniture-layout.json`，操作見 [共用家具配置](Docs/furniture-layout-v1.md)。採常見市售代表尺寸，不是人口平均或實測；尺寸不縮放，放不下仍列原尺寸與原因。樓上淨空續版 `abc-rationality-v2-upstairs-clearance` 初排了 A 2F 洗手台／馬桶／走道櫃及 B 2F 套衛洗手台，待調整由6件降為2件（A更衣前室兩組180cm櫃）；一樓照護配置不變。兩處內部分界各移200mm，未擴大外框；A走道櫃取物時不能同時通行，仍需專業核對。無程式衝突不等於全棟可施工。外觀來源另在 `inputs/facade-concept.json`，不覆寫平面。修改後執行 `scripts/export_model_3d.py` 一起更新 viewer、共用資料、12份平面SVG與3份正立面SVG；交付 HTML 需附上 `assets/` 和 `structured/`。

大型或既有實物統一登錄在 `inputs/physical-items.json`，操作方式見 `Docs/physical-items.md`。目前 B 棟武轎先採收納外廓 1200 × 1700 × 1800 mm 的一般規劃值並標記待實測；家具 3D 會讀取這份清單，不在兩處重複維護尺寸。
B 神桌在前緣通行區後的私有前廳，入口偏軸，後側武轎室經 1600mm 直線預留帶與 1500mm 門進出；不在騎樓同時存轎與停車。樓上濕區、KTV、樓梯及屋頂設備避開神桌投影，仍待梁／管線與宗教顧問複核。三棟弱電放梯廳側邊壁龕、不另隔機房；同軸雙折梯只是初排，淨高／結構／消防待核。

Windows 原生 Playwright CLI 驗收入口為 `scripts/check_windows_playwright.cjs`，
不再依賴 `/tmp` 暫存腳本。操作與路徑預檢見 [Windows 驗收方式](scripts/README.md#windows-原生-playwright-cli-驗收)；
結果與截圖存入 Windows TEMP，預檢成功不代表畫面驗收通過。
2026-10-06 已核對樓上說明修正後的 Windows Edge 報告 `house-design-cli-EHN6RW`：1877項檢查通過、當時25個來源雜湊一致、24張截圖已目視複查；A 2F衛浴仍有鄰房高牆遮擋。最新特寫自動剖視續版針對此問題改善，CLI新增完整牆高、旋轉重算及手機衛浴驗收，完整跑完預期27張截圖，須在Windows重跑；不能沿用EHN6RW替新版畫面背書。兩組衣櫃及基地、停車、機電和專業核定仍待處理，詳見 [驗收證據與未解項目](Docs/abc-layout-rationality-v2.md#未解與驗證)。

外觀v1的house-design-cli-lgBJsy（2603項／36張、30份來源雜湊）是本次C一樓重排前證據。本次已改viewer／bridge／共用資料及CLI，預檢現在是12 floors／105 rooms／129 items，完整預期44張、31份來源雜湊。440項Python測試、7組JS、Ruff與檔案預檢通過；實際HTTP e2e因socket權限無法啟動，本次瀏覽器畫面仍須Windows重跑及截圖目視，不能沿用舊passed。

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
- `inputs/facade-concept.json`：照片風格外觀的材料、假設、逐棟差異、法源及待確認項目；不是基地事實或專業核定。
- `inputs/revisions/`：不可變 PDF／IFC／DXF 圖面版次。
- `structured/reviews/`：檢核報告、會議 PDF 與離線儀表板。
- `structured/predesign/`：前期準備報告與分層研究來源。
- `structured/parametric/`、`structured/candidates/`：歷史概念情境，不是現行基準。

任何法規、結構、消防、機電與無障礙結果都必須保留法源、證據與專業責任人；程式與 AI 不能代替依法執業者簽證。

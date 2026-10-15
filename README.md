# House Design Prepare

這個專案現在以「未來收到建築師圖面後，可以快速、可追溯地重跑檢核」為核心。

目前土地尚未確定。目標是在高雄尋找三筆相鄰土地，A／B／C 每筆約 32 坪；這只是選地目標，不是實際基地面積，更不是每層可蓋面積。土地、地號、使用分區、道路、建蔽率、容積率與退縮未確認之前，系統只會顯示未知，不會假裝合規。

## 快速開始

最新[A收納／乾區續修](Docs/a-storage-dry-zone-v2.md)：屋主同意分散收納，A2三組180cm衣櫃與原240cm淺櫃保留、走道不置櫃；A3回收走道旁0.96m²並配置閱讀桌／書櫃，比例偏大提醒仍保留。ABC HTML共用圖可讀字／放大／整層還原；主案12層／112區／128件。Windows新畫面待驗，舊passed不套用。

最新[ABC空間分配修正 v6](Docs/abc-space-efficiency-v1.md)：A樓上回收前段走道／過大梯前乾區給主臥、次臥及劇院，C樓上改橫向公共通道、運動區不穿主臥。樓梯本體、騎樓、照護與濕區位置保留；[主案3D](structured/candidates/model3d.html#mode=tour&building=A&floor=floor-2&view=plan)與HTML共用圖同步。B本輪以32坪後門預案優先、前門備案保留，舊B不自動採用。仍待新Windows驗收與專業檢核。

最新[B 32地坪後門搬轎預先設計／前門備案](structured/candidates/b32-entry-options.html)已獨立保存兩案、八層同源平面與[3D](structured/candidates/b32-entry-options-3d.html?scheme=b32-rear#mode=tour&building=B&floor=floor-1&view=rear)。B以32地坪為硬上限，不以37.3坪擴框解答；後門優先但後巷／通行權未核，沒有後巷時切換前門備案。主案不變、未採用／未核，[面積口徑、主臥餘量及未解需求](Docs/b32-entry-options-v1.md)不能省略。此新圖需用 `scripts/check_b32_entry_playwright.cjs` 驗收，舊七案的passed不適用。

平面閱讀展示v2預設讀字模式，提供放大／縮小、整層還原及圖框內捲動；兩案配置、八張SVG與ABC主案不改。請重跑同一B32 CLI驗收新版桌機／手機操作，v1的Windows passed不涵蓋此展示改動。

最新[ABC 前期整合比較](structured/candidates/preparation-review.html)提供 C 有窗公衛、樓高／梯井與 B 功能容量七案；[同源 3D](structured/candidates/preparation-review-3d.html)、[可列印設計師會談補充包](structured/discussions/abc-preparation-meeting.html)及 22 項使用情境已備妥。v2 修 B 搬轎／神明堂連動及 C 門前／客餐操作。均未採用、不改原 ABC 主案或每筆約 32 坪選地目標；擴框不是完整功能或法規通過。詳見[本輪假設、缺口與驗證方式](Docs/abc-preparation-review-v2.md)。

屋主離線填答、房間卡、會議／變更紀錄及實物量測：先執行 `predesign owner-workspace` 與 `predesign consistency-review`，開啟 `structured/predesign/owner-workspace.html`。草稿下載後預覽匯入，`--apply` 才寫入，詳見 [屋主工作台操作](Docs/owner-workspace.md)。

既有三棟預先設計 HTML 可繼續使用；手機圖文重疊已修正，版本差異與尺寸限制保留提示，詳見 [原 HTML 使用範圍](Docs/original-html-usability.md)。

本輪 B 棟依屋主家規新增神桌正前方中軸祭祀門，搬轎側門／通道獨立；C 棟客廳、餐桌與玄關改無隔牆開放空間。HTML／3D同步，未增加面積或核定搬運／風水，詳見 [B／C 一樓動線續版](Docs/bc-1f-flow-v1.md)。

現主案的[風水最小修改歷史](Docs/fengshui-minimal-v1.md)只避神桌本體，**B仍不符合本輪背牆禁梯廳與整廳上方禁睡要求**。最新[B嚴格家規／C照護改善比較](structured/candidates/bc-options.html)提供五案逐層平面與同源3D，不覆蓋ABC主案；B比較主臥整合走道成3.6×4.3m、床櫃留房內，C小改保留1F套衛／後窗、2F／3F浴廁後牆前移20cm。[取捨與採用門檻](Docs/bc-constraints-review-v1.md)仍明列B照護衛浴／武轎面積／KTV等缺口，以及C分時照護操作、備案客房衣櫃與戶外面積變更。未定案、不宣稱風水或法規核可。

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
- `structured/candidates/model3d.html`：主要 3D 討論入口，預設 A 棟 1F；A 主案已改為32坪含前3.9m騎樓，保留孝親房／一樓淋浴，不計車位。[A續版說明](Docs/a-32ping-arcade-layout-v1.md)列正常產品替代、公共照護動線、樓梯平台與緊繃面積。本版共112個空間、61個家具空間、127件家具／設備、17組冷氣配對。選房後可用「房間特寫」放大並自動剖去遮擋牆／梯段上部；只改展示，不改房間或家具尺寸，可切完整牆高核對。原HTML的92個來源格位仍保留在原格位模式。
- [C 一樓空間利用續版](Docs/c-1f-space-use-v3.md)：獨立四人餐區、對向電視客廳、240cm廚具候選与孝親房衣櫃；門外全帶暢通主案／私有庭院待核虛框可切換，候選不計家具。A／B不改配置，ABC十二層共同核對產圖。
- [C 一樓公衛／採光三案比較](structured/candidates/c1f-options.html)：保留現況，另比較前右公衛與前客廳＋中段公衛；平面／3D同源，保留孝親房、樓梯與前帶，不直接採用。新增濕區、借光與原鞋櫃未容納等代價見[方案說明](Docs/c-1f-bath-daylight-v1.md)。
- [ABC 每筆32地坪含騎樓歷史比較](structured/candidates/arcade-capacity.html#scheme=arcade32&building=A&floor=floor-1)：舊骨架／32坪限制／保留空間加深三案，36層SVG與[獨立3D](structured/candidates/arcade-capacity-3d.html?scheme=arcade32#mode=tour&building=A&floor=floor-1&view=front)同源。參考固定在`inputs/references/abc-before-a-arcade.json`；舊排法A、C容量衝突與B未解需求保留，不拿新A套舊映射湊通過，不覆寫現主案。逐筆面積、跨層樓梯／冷氣與法規界線見[比較說明](Docs/abc-32ping-arcade-v1.md)。
- 照片風格外觀 v1：[三棟完整外觀](structured/candidates/model3d.html#mode=tour&view=exterior&angle=oblique)，可看單棟正面／斜角、分享連結並還原室內設定。三份 HTML 新增同源立面、材料候選與 pending；保留孝親／祭祀動線，不新增車庫、承重柱或屋頂棚架。[外觀資料與建築師清單](Docs/abc-facade-v1.md)列官方法源及候選窗問題。地籍、採光、欄杆、機電和停車均未核准。
- `structured/parametric/walkthrough.html`：會依 6–10 m 開間重新排房的另一個歷史容量情境；只有主版本 `f6000_g1` 的 B 棟固定對齊 `concept-safety-v1`，其餘仍不代表原 HTML 格局。

上述圖面都不是現行可建或施工設計。全層導覽使用
`#mode=tour&building=A&floor=floor-1&view=front`；原座標單房分享連結使用
`#mode=interior&building=A&floor=floor-1&room=A:floor-1:living&view=plan`（舊連結仍有效）。道路／前方固定對應 HTML 平面上方 `y=0`。
全層導覽與HTML共用同一份 `inputs/concept-layout-review.json` 固定比較框（6 × 17.63m，非地籍或可建外框）；不再自動加深房屋。A已依屋主同意改成32坪含騎樓，前3.9m全部留通行，孝親房3.6 × 3.77m與工作陽台維持；保留一樓淋浴及不穿MDF／樓梯的公共如廁路徑。B採祭祀／搬轎優先、C採照護優先，三棟均不計車位。原停車與其他未解需求另案保留，不視為已解或取捨定案。騎樓適用、建蔽、容積及地籍未知；A客餐廳假設淨面積約18.003m²已貼需求下限，完整照護與無障礙仍需完成面、輔具演練及專業核對。
版本取捨、待調整家具與冷氣安裝核對項目見 [ABC 合理性提案](Docs/abc-layout-rationality-v2.md)與[A騎樓續版](Docs/a-32ping-arcade-layout-v1.md)。家具來源在 `inputs/furniture-layout.json`，操作見 [共用家具配置](Docs/furniture-layout-v1.md)。採常見市售代表尺寸，不是人口平均或實測；尺寸不縮放，放不下仍列原尺寸與原因。本版A名義1F層高4m、樓上3m，900mm雙折梯／260mm級深和共用前平台跨層同步；不是完成面淨寬或法規核可。A2F兩組180cm衣櫃及240cm走道櫃共3件待排；走道櫃會占1280mm公共通行暫留，本版不再畫成已安裝。B既有套衛與C健身区入口仍待定。無程式衝突不等於全棟可施工。外觀來源另在 `inputs/facade-concept.json`，不覆寫平面。修改後依序執行 `scripts/export_model_3d.py`、`scripts/export_c1f_options.py`、`scripts/export_arcade_capacity.py` 更新主案與比較；交付HTML需附上 `assets/` 和 `structured/`。

大型或既有實物統一登錄在 `inputs/physical-items.json`，操作方式見 `Docs/physical-items.md`。目前 B 棟武轎先採收納外廓 1200 × 1700 × 1800 mm 的一般規劃值並標記待實測；家具 3D 會讀取這份清單，不在兩處重複維護尺寸。
B 神桌在前緣通行區後的私有前廳，入口偏軸，後側武轎室經 1600mm 直線預留帶與 1500mm 門進出；不在騎樓同時存轎與停車。樓上濕區、KTV、樓梯及屋頂設備避開神桌投影，仍待梁／管線與宗教顧問複核。三棟弱電放梯廳側邊壁龕、不另隔機房；同軸雙折梯只是初排，淨高／結構／消防待核。

Windows 原生 Playwright CLI 驗收入口為 `scripts/check_windows_playwright.cjs`，
不再依賴 `/tmp` 暫存腳本。操作與路徑預檢見 [Windows 驗收方式](scripts/README.md#windows-原生-playwright-cli-驗收)；
結果與截圖存入 Windows TEMP，預檢成功不代表畫面驗收通過。
2026-10-12新增[A梯下MDF優先候選／側壁龕備援](Docs/a-mdf-under-stair-v1.md)，HTML／3D可切虛框比較，另附同源梯下敏感度剖面；保留600×600×1000mm原機櫃，90cm梯段尚不能完整容納120cm左右維修外廓。備援補齊兩側預留、後乾區與廚房門同步，孝親房／轉位不縮小。原位置家務櫃僅條件式範圍，不新增家具或計入已釋放面積。
預檢仍應為 **12 floors／112 rooms／127 items**；本MDF續修版Windows與新截圖目視待重跑。騎樓版`house-design-cli-T1uj2e`已核對5133項、115份當時來源、75張截圖存在並原尺寸目視13張；本輪來源已改，不能沿用passed。此前`house-design-cli-g2jEnZ`（12／105／129）及下列報告也只適用各自來源。
2026-10-07 Windows Edge 報告 `house-design-cli-QEFdQU` 是提交 `1e38934` 的歷史證據：2682項檢查通過、31份當時來源雜湊吻合、44張截圖已目視複查；12 floors／105 rooms／129 items，桌面1440 × 900、手機390 × 844，命名session已關閉。無pageerror或非預期錯誤，仍有8次既有Three.js棄用warning。[歷史驗收與限制](Docs/c-1f-space-use-v3.md#歷史-windows-驗收)記錄原始報告SHA-256；原始報告／截圖仍在Windows TEMP，非專業封存。

2026-10-08 Windows Edge報告 `house-design-cli-sAmDnF` 是容量比較前的歷史證據：**3275項自動檢查通過，64份來源雜湊與當時檔案一致，56張截圖已目視複查**；主案12／105／129，未採用公衛／採光替代案。19次既有Three.js棄用warning，無pageerror或非預期錯誤，session已關閉。**手機橫向公衛與含冷氣管路的C客廳特寫仍偏小，不等於全面視覺驗收通過。** 證據、取景待辦及報告SHA-256見[公衛／採光驗收](Docs/c-1f-bath-daylight-v1.md#本輪-windows-驗收)。當時452項Python／7組JS回歸通過；本輪新增32坪比較及HTML bridge／CLI改動，舊passed不驗新來源，需重新執行Windows驗收。QEFdQU、樓上 `house-design-cli-EHN6RW`（1877項／24張）與外觀v1的 `house-design-cli-lgBJsy`（2603項／36張）也只適用各自歷史版本；Linux HTTP e2e仍受socket限制，不以Windows流程當成全部HTTP e2e也已執行。

容量初版`house-design-cli-0mTIes`已核對4598項自動檢查、114份當時來源雜湊及71張分級目視截圖；發現手機3D連結換行、橫向整層／公衛與含管線客廳特寫偏小。其後展示續修做了双欄手機工具列、控制區留白、房間取景及橫向整層斜角，當時保留房間／產品。**目前A已另行重排騎樓主案**，不能再稱本輪只有展示改動；CLI另增A騎樓特寫，新版Windows／目視仍待重跑，不沿用0mTIes或g2jEnZ passed。歷史[取景續修契約](Docs/abc-32ping-arcade-v1.md#手機取景續修僅展示)與新A主案分開記錄。

每筆32坪含騎樓容量比較及C一樓公衛／採光比較仍未採用；選案與專業條件未定。後續還有緊湊骨架、A二樓待排衣櫃、B武轎裝抬桿搬運與ABC停車／前帶取捨，見[討論優先順序](Docs/abc-layout-rationality-v2.md#下一輪優先討論不改需求決定)。驗收通過不消除這些未解需求，也不代表基地、照護、法規、風水或施工已核准。

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
- `inputs/c1f-bath-daylight-options.json`：C一樓公衛／採光的未採用比較；不自動變更主案或需求狀態。
- `inputs/revisions/`：不可變 PDF／IFC／DXF 圖面版次。
- `structured/reviews/`：檢核報告、會議 PDF 與離線儀表板。
- `structured/predesign/`：前期準備報告與分層研究來源。
- `structured/parametric/`、`structured/candidates/`：歷史概念情境，不是現行基準。

任何法規、結構、消防、機電與無障礙結果都必須保留法源、證據與專業責任人；程式與 AI 不能代替依法執業者簽證。

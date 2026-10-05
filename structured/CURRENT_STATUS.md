# 現行專案狀態

土地尚未確定。現行條件是在高雄尋找三筆相鄰、每筆約 32 坪的土地；這是選地目標，不是已取得基地或可建量體。`structured/parametric/` 與 `structured/candidates/` 都是歷史假設／草圖輸出，不是可建量體或合規結論。

請從以下資料開始：

- `inputs/project.json`：基地事實與未知欄位。
- `inputs/predesign.json`：家庭、預算、選地到交屋的階段閘門。
- `inputs/requirements.json`：66 項待屋主逐條確認的既有想法（含 11 條空間關係）。
- `inputs/physical-items.json`：大型既有實物的暫估與實測尺寸清單。
- `inputs/revisions/`：不可變 PDF／IFC／DXF 圖面版次。
- `structured/reviews/<revision>/index.html`：現行離線檢核儀表板。
- `structured/predesign/report.md`：現在該做與後續預留事項。

## 2026-09-15 預先設計可用性評估與三項補強

針對「未來能否和建築師、設計師討論」的架構評估結論：治理、閘門、不可變版次與檢核已成熟；缺的是把需求整理成可討論文件、批次決策與結構化空間關係。本次完成三項第一優先補強：

- **設計任務書**：`predesign brief` 產生 `structured/predesign/design-brief.json／.md／.html`，依「已確認／待屋主決定／已淘汰」分段列出各棟需求、空間關係總表、大型實物與 3 × 12 題開會待問問題；家庭概況只輸出去識別化統計（人數、年齡級距、行動力類別），姓名、健康細節與自由文字不會出現，私有檔也不列雜湊。任務書帶 `brief_hash` 與來源檔案雜湊，變更後須重新產生。
- **批次決策表**：`intake requirements-sheet` 匯出會議用決策表，`intake requirements-decide --batch` 一次套用整批；全有或全無，並以 `requirement_hash`＋`decision_count` 拒絕過期表單（內容被改過或已有新決策都不會重播舊決定）。填 `confirmed` 的列會同時確認當下的空間關係。
- **空間關係檢核**：需求可帶 `relationships`（相鄰、直接可達、不得正對、上下壓疊、搬運路徑、獨立排氣等）。關係狀態由決策紀錄的 `relationship_hashes` 推導，不另設 status 欄位；確認後才新增的關係保持待確認。圖面回來後 `review run` 會對已確認關係發出 `REQ-RELATIONSHIP-*` 發現：幾何可判定者給 pass／fail／warning，跨樓層壓疊比對在座標系統未驗證前一律 unknown，非幾何關係交專業確認。
- 交付包可附任務書：`drawings prepare-handoff --brief structured/predesign/design-brief.json` 會先驗證 `brief_hash` 與來源雜湊，不符即拒絕且不建立目錄；通過後包內附 `design-brief.snapshot.json／.md／.html` 並登錄 manifest。
- 評估中另外兩項建議（選地淘汰條件與 `site-compare`、假設情境可建量體計算器）尚未實作，屬第二優先；後者若未來實作必須標示為假設情境，不得當成法規結論。
- 已知未收斂事項：需求 id 內嵌舊版樓層（任務書已標示為屋主建議、可調整）；家庭檔行動力欄位建議改用 `independent`／`walking_aid`／`wheelchair`／`unknown` 等 token，自由文字會落在「其他」類；工作區有前一輪參數化輸出（`structured/parametric/plan.json` 等）未提交，與 R000 封存雜湊不一致，導致 3 個歷史對照測試暫時失敗，須由屋主決定收斂方式。
- 自動驗收：212 pytest passed（另 3 個失敗為上述 R000 封存雜湊衝突，與本次變更無關），branch coverage 73.20%（門檻 68%），Ruff passed。

## 2026-09-09 B 棟武轎實物統計

- 新增集中式實物清單；`B.palanquin.primary` 先採收納外廓 1200 × 1700 × 1800 mm 的一般規劃值，明確維持 `pending measurement`，抬桿搬運外廓仍未知。
- B 棟歷史 3D 的武轎量體改讀實物清單，不再由家具 catalog 重複保存尺寸；實測後最後一筆完整寬／深／高會自動成為顯示尺寸。
- B 棟 1F 神明堂與武轎儲藏室已完成第一版用途配置，總家具／設備數更新為 69 個空間、154 件；`BbuildingView.html` 的比例框與 3D 使用相同 id、尺寸與相對位置，並由自動測試防止漂移。
- 儲藏室暫採 1500 mm 完成面淨開口與直進直出，不把 1800 mm 轉向圓硬塞入 1700 mm 深的歷史格位；若正式門位無法直線進出，須擴大房間／前室。
- 可用 `house-design intake physical-item-measure` 追加量測紀錄；`intake validate` 同時檢查實物清單，拒絕缺任一方向的部分實測。
- 自動驗收：177 pytest passed，branch coverage 70.13%（門檻 68%），Ruff passed，Playwright 18/18 passed；另完成 B 棟 1F 神明堂／武轎儲藏室 HTML 與 3D 俯視對位檢查。

## 2026-09-08 歷史 HTML 家具／設備初排

- `structured/candidates/model3d.html` 已加入第一版家具／設備比例量體：涵蓋 69 個 HTML 空間、147 件，並保留每房「HTML 明載／HTML＋房型推排／依房型推估」及對照文字。
- C 棟明確需求已優先落入，例如 2F L 型沙發＋茶几＋電視牆、240 cm 流理台＋75 × 70 cm 冰箱，以及 3F 180 × 200 cm 雙人床＋360 cm 四衣櫃牆；A／B 棟也依房間設備說明放入基礎家具、機櫃與屋頂設備。
- viewer 可切換家具顯示；選取單一房間時只顯示該房家具，洋紅外框會揭露越界或碰撞。「標示覆寫」下沒有家具互撞、仍有 19 件越界；多數是 HTML CSS 格位深度不足，例如 C 棟兩車＋機車車庫被抽成僅 1.2 m 深。預設「示意格子」則如實顯示 28 件越界及 A 棟多功能房的書桌／衣櫃碰撞。
- 可編輯來源為 `inputs/furniture-layout.json`，操作與限制見 `Docs/furniture-layout-v1.md`。這仍是歷史空間容量測試，不會升格為 R001 或現行室內設計。
- 自動驗收：169 pytest passed，branch coverage 69.45%（門檻 68%），Ruff passed，Playwright 17/17 passed；另完成 C 棟 1F 車庫、2F 客廳與 3F 主臥的桌面俯視視覺檢查。

目前 `R000` 只用來證明舊的「每層建築面積 32 坪」假設已被攔截，不得放行。

## 2026-09-02 R001 交付包與技術整理

- 前身來源已更正為 `/mnt/d/Desktop/houseDesign`；`structured/architect_handoffs/R001/legacy-reference/` 完整保存其入口與 A／B／C 四份 HTML，逐檔 SHA-256 與原檔相同。它們只供需求對照，不是權威圖面。
- 新增 `drawings prepare-handoff` 與 `drawings preflight`。交付包包含專案／64 項候選需求快照、A／B／C 共 12 個棟層的 mapping v2 範本及可列印說明；preflight 會在暫存目錄執行真正 importer，檢查包內路徑、格式、座標、標高、空間範圍、requirement id、space-block 與 walkthrough readiness，不會建立 R001。
- 現行 R001 範本的預期結果仍是 blocked：土地未選定，且尚無建築師 PDF＋IFC／DXF、交付人、座標與樓層證據。`inputs/revisions/R001/` 並不存在；不得把範本或前身 HTML 當成正式版次。
- 不可變版次 seal／驗證與 3D readiness 已從大型 drawing importer 拆為獨立模組；兩個歷史 3D exporter 的資料邏輯與 HTML／JS 模板也已分離，模板列入 pipeline fingerprint。
- Ruff 從只檢查 `F` 擴至 `E4`／`E7`／`E9`／`F`／`I`／`B`；CI 新增含 drawing extras 的 branch coverage 門檻 68%。前身 HTML 任務板移到 `structured/historical/`，不再和現行 revision 狀態混用。
- 自動驗收：165 pytest passed，branch coverage 69.45%（門檻 68%），Ruff passed，Playwright 17/17 passed，`pip check` passed，npm audit 0 vulnerabilities。R000 integrity 與 intake／predesign contracts 均有效；隔離 concept pipeline 完整成功，layout validation 為 0 errors／0 warnings，HTML consistency 為 0 critical／23 warnings／23 info。

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

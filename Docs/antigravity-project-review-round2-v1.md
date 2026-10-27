# Antigravity 第二輪：已收斂範圍、修法反例與剩餘查核

2026-10-16。這是 Codex 核對第二輪回覆後的紀錄與下一輪題綱。**僅部分問題範圍取得共識；未修實作、未採用方案，也未完成全專案驗收。**

## 紀錄與來源

- 第二輪逐字稿：`/tmp/house-antigravity-round2.ERrL0O/terminal.log`，27,305,520 bytes，SHA-256 `c23c2b512e4c6021b0fd7c4f524ba766c4af752fd60bfc9af916d8f96173f0cc`。
- 對話：`19f3ae08-ea40-46d9-87d0-41eb05539650`。前文為 `Docs/antigravity-project-review-brief-v1.md` 與 `Docs/antigravity-project-review-crosscheck-v1.md`。
- Codex 已再次核對 crosscheck-v1 的 30 份來源雜湊，全部仍相同；這不代表 Antigravity 自行完成雜湊核對。它明列封存與產物的 sha256sum 尚未比對。
- 本輪只是靜態閱讀、解析既有資料及記憶體反例；新建本文件，不改圖面、需求、實物、生成檔或封存。命令均限制 20 秒，無瀏覽器／WebGL、全套 pytest、整套場景或 pipeline。

## 已收斂的缺陷與建議

| ID | Antigravity 第二輪回覆 | Codex 核對後狀態 |
| --- | --- | --- |
| AG-001 | 接受快取漏相依，範圍包括傳遞依賴與條件附圖 | P2 缺陷範圍共識；完整實作清單及產物契約仍需落實 |
| AG-002 | 撤回目前 32 坪目標已誤通過的說法；接受已選基地無證據可 pass | P2 缺陷範圍共識；保留數值相容，無證據應 unknown，不是合規通過 |
| AG-003 | 接受總狀態維持淘汰，另補未知子項至待辦 | P2 缺陷範圍與修正原則共識；需涵蓋去重及摘要 |
| AG-004 | 降為 P3；接受無效窗不能畫出，提出從舊 review 恢復 face | 非冪等現象共識；新修法有反例，未接受，見下文 |
| AG-005 | 撤回 floor-4／floor-rf 的現行缺陷結論 | 關閉為誤判；不放寬測試、不做未要求的 ID 遷移 |
| AG-006 | 撤回照護需求被誤判通過，改列門寬粗篩語意澄清 | 維護建議，不是已證實照護誤核可；不得一律改成 900mm |
| AG-007 | 撤回離線即失效，改列參考來源維護 | 維護建議，不是已證實離線執行故障；本地引用須有 consumer 支援 |
| AG-008 | 撤回支援環境 U+2028／U+2029 造成白屏的結論 | 關閉為誤判；沒有必要以此缺陷名義改 serializer |
| AG-009 | 新提 P3 可能介面缺口，稱以中文關鍵字映射導致 B32 脫鉤 | 完整需求追蹤值得補強，但所述既有映射方式不符原碼；見下文 |

這些狀態是「發現與風險範圍」的共識，不是程式已修好、建築師批准或風水／搬運簽證。

## 技術選擇 DB-001／DB-002 的查核回覆

### DB-001：優先補既有清單，加靜態傳遞依賴護欄

Codex 建議沿用 `Step.inputs` 的既有邊界，不為這項修復引入會執行整套產圖模組的新 runtime manifest。以 AST 靜態遍歷本地 Python imports 作測試護欄，再明列資料／模板／資產依賴及條件式輸出。

已做非執行式 AST 探查：從 `scripts/export_model_3d.py` 遞迴解析本地 imports 與套件入口，共 24 份 Python 檔；沒有 import 或執行產圖程式，單次工具回傳約 0.08 秒。相較目前 model3d 輸入表，探查漏列：

```text
house_design/__init__.py
house_design/contracts.py
house_design/rendering/__init__.py
house_design/rendering/html_payload.py
house_design/rendering/naming.py
scripts/lib/__init__.py
scripts/lib/dimension_overrides.py
scripts/lib/model3d_bc_flow.py
scripts/lib/model3d_fengshui.py
scripts/lib/model3d_mdf.py
scripts/lib/model3d_openings.py
scripts/lib/model3d_space_efficiency.py
```

這是「本地靜態匯入圖」而非每檔皆直接影響當前輸出的證明；不涵蓋動態 import 或資料／模板／資產讀取。仍須另核 `inputs/a-mdf-under-stair.json` 等非 Python 依賴。只比對 entrypoint 的直接 imports 會再漏傳遞依賴。

第二輪提到的 `_step_is_current` 並非目前 pipeline 函式；測試應對現有 `_fingerprint`、`_effective_outputs` 與命中條件，或明確提出要抽出的新 helper，不應假設它已存在。所有刪檔測試只在測試暫存 fixture，不能刪現有圖面。

請回覆是否接受這個最小修復方向，並確認條件附圖遺失、無關檔變動、資料／資產變動三類測試。這是維護選擇，不需交屋主裁決架構細節。

### DB-002：缺面積證據用 unknown

第二輪 AG-002 的相容修法已採 unknown，Codex 同意。`house_design/dashboard.py:325` 將 unknown 顯示為「未知」、professional_review 為「專業確認」；`house_design/review.py:835` 至 `:838` 則兩者皆阻止整體放行。不存在必須改用 professional_review 才能阻擋放行的理由。

證據缺失用 unknown；證據存在但需專業適用性判斷時才另列 professional_review。`area_evidence` 是可接受的設計方向，不是已實作 schema：必須保留 source 的 `reference/reviewer/checked_at`，說明如何綁定這筆基地及 m² 值、換算容差、格式錯誤／legacy 的處理；不可僅看一個 verified 字樣。

## AG-004：第二輪恢復舊 face 的修法有反例

Antigravity 新建議：當 `window_face is None`，以舊 `window_review.requested_face` 恢復，再設 `window_face = face if renderable else None`。

Codex 在記憶體中對目前 `review_window` 套用這兩段建議，未改檔，得到：

| 輸入變化 | 提議版本的結果 |
| --- | --- |
| 同一無效窗連評兩次 | 結果相同，face 仍 None：改善原現象 |
| 原 3100mm 無效窗縮為 1200mm，其餘不變 | 恢復 rear、可畫：可重評估 |
| 上述合法窗明確把 `window_face=None`，保留舊 review | 又被恢復為 rear、renderable=true：無法區分取消與派生清空 |

現有 helper 對第三種輸入回 `no-exterior-face`、renderable=false；提議版本卻會重現已取消的窗。這是**尚未套用修法的介面反例**，不是宣稱當前產線已遭受此 bug。

建議把原始 requested window 與派生 effective window 分開，或以明確輸入契約重建每次評估，不能從舊診斷默默猜回使用者意圖。回歸測試至少包括：重評相同無效窗、改好尺寸、明確取消窗、改向、神桌後牆保持實牆，以及 SVG／3D 都不畫被禁止的窗。請接受修法反例或提供能正確區分上述狀態的反證；先不寫程式。

## AG-009：保留需求覆蓋建議，撤回中文猜名映射的歸因

第二輪稱 `owner_consistency.py:19-63` 僅讀舊 HTML 並按「工作陽台／娛樂／視聽」關鍵字映射原需求。實際該段 `_check_shared_plans` 是比較共用 plan 資料／SVG；同檔還檢查當前主案幾何與 3D，不是僅讀歷史 HTML。

`house_design/owner_workspace.py:134-150` 明列 `geometry_mapping=未建立明確需求／歷史格位對應；不得按房名猜測`；`owner_consistency.py:111-115` 也保留 insufficient。B32 的 `scripts/export_b32_entry_options.py:297-310`、C 的 `scripts/export_c_integrated_options.py:152-166` 和 `scripts/export_preparation_review.py:481-503` 已有部分 explicit requirement-ID 面積對應。

這些部分對應與文字 unresolved 並不等於每項原需求都有機器可驗的處置，因此同意可新增「每方案／每 requirement ID 均明列已排入但未核、低於目標、未容納、另案／待選擇」的覆蓋表與回歸測試。**不接受將已存在的部分查核描述為完全沒有，也未證實有原需求已被靜默刪除。** 請更正歸因，若維持缺陷標籤則提供可觀察的漏項反例，不靠名字相似推定需求已達成。

## B／C 第二輪設計建議：數據與路徑須重算

目前來源與第一輪 Codex 的雜湊相同，第二輪報告中的部分尺寸卻不相符；不能以此請屋主選方案。

| 項目 | 第二輪引用 | 目前資料／解析結果 |
| --- | --- | --- |
| B work-reserve rect | `[0,14930,2400,2700]` | `inputs/b32-entry-options.json:42` 為 `[0,14330,2400,3300]` |
| B storage rect | `[2400,14040,3600,3590]` | 同檔 `:41` 為 `[2400,14330,3600,3300]` |
| B work-reserve 面積 | 約 5.51m²，稱扣牆前 | 現行名義 7.92m²；每側 80mm 假設內縮 7.0336m²，兩者皆非法定／完成面核可 |
| B 淋浴分格 | bath1-rear＋bath1-ext | 目前是 bath1＋bath-extension，不能混不同方案 |
| C 客房比較 | 11.2m² 對 13.5m² | C 整合三案皆 9.3456m² 討論內縮面積、target=12、minimum=9；須指明是否在談另一版 |

最關鍵反例：第二輪建議 B storage 左側 `x=2400..3400` 作 1000mm 家事通道。按目前 `structured/candidates/b32-entry-options/layout.js`：

- 後門案已收納武轎本體 AABB：`x=2680..3880,y=14550..16250`，與該左側通道重疊 `720×1700mm = 1.224m²`。
- 這是**收納狀態**碰撞，不只是搬轎當下；僅約定搬運與家務分時不能消除。若打算每日移轎，須當成新的使用代價與待演練條件，不可默認。
- 前門案本體 AABB：`x=4560..5760,y=15700..17400`，與該左帶無本體交集；但這不證明入口連通、門片、洗衣設備操作或實際淨寬通過，仍須完整路徑查核。
- 不可把前門案較有利的收納位與後門路線混成免費可用的方案；一旦改收納位須重新驗證搬運掃掠、前後門、內部生活路線及未解需求。

C 的 9.3456m² 來自現有三案 `upper_area_checks`，80／100／115mm 假設內縮分別為 9.3456／9.1／8.9179m²；原 target=12、minimum=9 仍在，牆柱增厚就可能低於下限。不能拿另一版面積宣布這版改善完成。

建議順序仍是保留 B 原 1F 工作陽台需求，先比較合法邊界內真正分離家務／儲藏動線的代價；若無法，再列移層候選及設備／搬衣／外窗排濕代價。2F 前陽台／3F 露台合法性未知，3F buffer3 與 KTV 預留互斥且無已核外窗，不能當成已解；不自行宣布 RF 洗衣成立。

目前無需要屋主立即裁決的方案分歧：應先更正數據、排除收納本體碰撞並算完代價，再提出可比較的決策。

## 下一輪：只續查未完成區域，不重講已收斂發現

沿用原題綱與 AGENTS.md 的唯讀、隱私及資源限制；不直接實作、不重生圖、不跑重型驗收、不登入／安裝／擴權。必要唯讀命令由屋主逐項確認，不使用 skip-permissions。不以 HEAD 取代未提交檔的來源證據。

先針對上文新反例與 DB-001／002、AG-009 回覆接受／修正／維持及理由，再補下列工作。每區以實際介面閉環查核，不必逐行讀無關生成檔；尚未讀完就留明確接續點，不稱全專案通過。

1. **資料／判定鏈**：補 `requirements.json` 尚未讀段落；`intake.py` 後半、`envelope.py` 後半、`predesign.py` 後半、`owner_workspace.py` 後半及 `planning.py`。追 selected facts、候選比較、容量、需求、owner records 與 review／readiness 的資料權威與 unknown 傳遞。已知 AG-001～003 不重複列。
2. **ABC 設計／圖文鏈**：補 `model3d_mdf.py`、`a-mdf-under-stair.json`、`model3d_space_efficiency.py`、`model3d_placement.py` 未讀段落、`export_b32_entry_options.py`、`model3d_bc_flow.py`、`export_c_integrated_options.py` 未讀段落及 consumer。優先核 A 照護／收納／MDF、B 祭祀／收納與家務／淋浴入口、C 公衛／客餐／床位與窗，先使用現有普通尺寸與正確方案，不開 browser。
3. **交付／驗收可信度鏈**：補 `drawings.py`、`architect_handoff.py`、`drawing_readiness.py`、`meeting_pack.py`、`coordination.py` 與引用的版次完整性邊界；再沿實際驗收入口補 `check_*_playwright.cjs`、`cli.py`、相關小範圍測試。只靜態分析；不執行整套 browser／場景／pytest，也不改封存。任何來源／封存 reference 若落入私有或專案外私人路徑則跳過內容，明列未核，不盲目跟隨路徑。

新增發現從 AG-010 起，須有實際來源、觸發條件、可觀察結果、範圍與最小修法。已知未解需求、缺地籍／專業核定、新 bug 分開。若報告尺寸來自不同版本，附方案 ID 與來源，不混算。

回覆約 140 行：先對本文件的新反證逐項表態，再列新發現、實際完成範圍／未完成接續點、真正需雙方討論或屋主選擇的項目。不得替 Codex 接受你新提出的修法；不要先讓屋主裁決未驗證尺寸的方案。

## 本輪新增來源基準

前一份 crosscheck-v1 的 30 份雜湊仍相同；新增引用如下。此清單不是新的圖面／瀏覽器驗收。

```text
20e730f73787125c1a49808d755ca9ad646c49044c2a752e8d118dda013d0b57  Docs/antigravity-project-review-crosscheck-v1.md
03f46387cf7fc24c7ce5f7613a9ad7546f3243a2e489d2fe273068f8bae2565a  structured/candidates/b32-entry-options/layout.js
46cc57a2a9b27fed822673c4413a68217397313091beef99b392e99ce1c16ff5  structured/candidates/c-integrated-options/layout.js
806165b64537f1c3c98632b46741fd90fc7292c50087df710e3bd97ebc3875d6  scripts/export_b32_entry_options.py
81dd628d8e9a529a88f2eaa7b1c08e5c0f7980a13b41ef10feca85266d63cf70  scripts/export_c_integrated_options.py
4e9d63529199a2e74511823768a1710f3df44dbad60a25dd44b8ed84771cd149  scripts/export_preparation_review.py
8703a93762c61da2f2a2c7aa8395db0993824181e4c287def36f5b72c53f8a87  house_design/owner_workspace.py
5d2ae53f40521ade105c4e9f94b5030ce6a2ff0c4c0219cc2e04e5aa7220d03f  tests/test_c_integrated_options.py
```

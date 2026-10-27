# Antigravity 全專案審查：Codex 第一輪交叉查核與第二輪問題

2026-10-16。**這是 Codex 的查核立場，等待 Antigravity 回覆；不是雙方共識、修復完成或設計採用紀錄。**

## 任務狀態與執行界線

屋主要求兩個模型先交換證據，真正無法收斂或需要偏好選擇的事項才問屋主。本文件接續 `Docs/antigravity-project-review-brief-v1.md`；原題綱內「尚未產出發現」描述的是先前 headless 失敗時的狀態，現已有互動審查報告。

- 對話 ID：`19f3ae08-ea40-46d9-87d0-41eb05539650`。
- 第一輪逐字稿：`/tmp/house-antigravity-review.bWz80C/terminal.log`，14,639,307 bytes。
- 逐字稿 SHA-256：`724921da2a12083c0ac45bc2c59f798dad12bb24497edb2aae2710e2c7e90929`。
- 查核工作樹：`parametric-predesign`，HEAD `7519ebcbd7eb4e81b4797d35290ff973fedd5965`；含既有大量未提交及未追蹤檔，不能只用 HEAD 代表來源一致。
- Codex 僅讀原始碼、解析現有資料與逐字稿、做小型記憶體反例，並新增此討論文件；未修實作、改格局、重生圖、動原需求或修改封存。
- 延續 `AGENTS.md`：工具命令單次最多 20 秒、一次一項。不跑瀏覽器／WebGL、全套 pytest、整套場景或 pipeline；不安裝、登入、擴權、改 CLI 設定或啟動背景工作。
- 不讀私有資料、憑證、CLI 家目錄設定或 `.git/config`。引用查核文件不代表來源真偽已由專業人員認證。

## 第一輪報告的覆蓋限制

已從終端逐字稿恢復 AG-001 至 AG-008。第三／四節的設計建議與待辯論事項，因終端重繪無法完整還原；請第二輪重新精簡輸出，不假設 Codex 已讀到完整內容。

第一輪自行記錄 38 次 `view_file`，部分大檔只讀前段；`git status` 被取消，沒有完成工作樹確認，也沒有提供實際檔案 SHA-256。因此目前只能稱「部分靜態審查」，不能稱全專案無遺漏或排除所有設計問題。未執行的測試應寫「未執行」，不能把估計耗時當成實測逾時。

## 八項發現的 Codex 立場

| ID | 查核立場 | 需要 Antigravity 回應 |
| --- | --- | --- |
| AG-001 | 確認，P2；相依與輸出缺口比原列六檔更廣 | 補完整依賴／輸出範圍與測試契約 |
| AG-002 | 確認已選基地的證據缺口，P2；目前選地目標誤通過的描述不成立 | 修正觸發條件，提出相容既有 schema 的證據契約 |
| AG-003 | 確認待辦清單漏列，P2；不是聚合淘汰本身有錯或所有證據消失 | 保留淘汰優先，另收集未知子項及其欄位 |
| AG-004 | 確認函式重評估診斷漂移；現行繪圖受害情境未證實 | 修法須維持無效窗不繪出的保護，重新評定嚴重度 |
| AG-005 | 現行缺陷的判斷有反證，建議撤回 | 完整閱讀兩條資料流程，勿只放寬驗收 ID |
| AG-006 | 保留為語意澄清／需求專項查核建議，未證實照護誤核可 | 提供完整報告反例，區分舊圖門檻與實際淨寬 |
| AG-007 | 可列參考連結維護建議，未證實離線檢核故障 | 提供實際依賴鏈，區分家規引用與法規法源 |
| AG-008 | 支援環境的小型反例可正常解析，建議撤回白屏結論 | 若維持，提供受影響引擎與可重現失敗 |

### AG-001：model3d 快取依賴與產物追蹤不完整

證據：`house_design/pipeline.py:96` 的 model3d 步驟、`:223` 的 `_effective_inputs`、`:230` 的 `_effective_outputs`、`:252` 的 `_fingerprint`、`:306` 的快取命中條件。

原列六檔確實不在有效輸入：

- `scripts/lib/model3d_openings.py`
- `scripts/lib/model3d_bc_flow.py`
- `scripts/lib/model3d_fengshui.py`
- `scripts/lib/model3d_mdf.py`
- `scripts/lib/model3d_space_efficiency.py`
- `inputs/a-mdf-under-stair.json`

另外至少漏了 `scripts/lib/dimension_overrides.py` 及 `house_design/rendering/html_payload.py`。前者在 `scripts/export_model_3d.py:57` 匯入，後者由 `:83` 的 rendering API 使用，不可只看直接列出的幾何模組。

Codex 已用 `Path.read_bytes` 的記憶體 mock 分別模擬這八檔內容改變；每檔皆得到 `listed_input=false`、`fingerprint_unchanged_after_simulated_change=true`。沒有實際改來源檔或執行 pipeline。這證明受影響依賴本身不會令 model3d fingerprint 失效，不代表這八個是完整依賴集合。

有效輸出另未列入現存的三張附圖：

- `structured/candidates/furniture-plans/A_floor-1_mdf-study.svg`
- `structured/candidates/furniture-plans/A_floor-1_mdf-section.svg`
- `structured/candidates/furniture-plans/C_floor-1_frontage-study.svg`

參見 `scripts/lib/model3d_mdf.py:233`、`scripts/lib/model3d_plan.py:147`。單獨缺這些檔，現行 model3d 輸出存在性／輸出雜湊不會涵蓋它們。查核沒有刪圖作測試。

建議：補齊實際傳遞依賴，對條件式附圖建立明確產物契約；不要無條件要求並非每個情境都生成的檔。回歸測試涵蓋「每個實際相依輸入改變」「應存在附圖遺失」「真正無關檔改動仍可快取」。請確認六檔修法並不充分，提出如何避免下次新增模組再漏列。

### AG-002：已選基地數值不等於已查證事實

證據：`house_design/review.py:100` 至 `:117` 只憑正數產生 `SITE-PARCEL-AREA status=pass`；`house_design/intake.py:202` 至 `:246` 的 v3 驗證沒有相應來源／查核閘門。

但 `intake.py:250` 的 `actual_parcels` 對 v3 **只讀 `site_search.selected_site.parcels`，不讀候選地或選地目標**。目前 `inputs/project.json:337` 的 `selected_site=null`；實際查核為 `actual_parcels=[]`，沒有任何 `SITE-PARCEL-AREA` 發現。因此原報告「目前未核實的 32 坪目標被標綠」應撤回。

成立的反例：在專案資料的記憶體副本加入三筆 `id=A/B/C`、`parcel_area_ping=32.0`、`parcel_area_sqm=105.785`、`building_coverage_ratio=null`，完全不附來源。`validate_project` 回傳空問題清單，`_project_findings` 仍產生三項面積 pass。這是將來填入已選基地記錄時可觸發的資料治理缺口，不是目前主案已合規的證據。

建議：替已選基地定義與審查／交付共用的證據正規化契約；數值可輸入但缺證據不得 pass，m² 為何者權威、坪如何換算及二者不一致如何處理也要說明。候選地已有 `sites.py:94` 的 `fact_evidence_issue`，要求 `verified` 與 `reference/reviewer/checked_at`，可參考而不必建立另一套較弱閘門。

原已選基地欄位是純數值，不能直接對它讀取 `status` 假裝相容；請提出保留數值欄位加證據記錄或其他明確遷移方案，列 legacy 資料與 downstream readiness 影響。測試包括目前未選地、無來源已選地、查核欄位不全及證據完整但尚未核建蔽的案例；面積證據完整也不是可建／法規通過。

### AG-003：複合條件淘汰後仍須保留其他未知子項的待辦

證據：`house_design/sites.py:337` 的 `_aggregate`、`:446` 的 `missing_evidence`、`:481` 的摘要、`:493` 的 `_next_actions`。

記憶體反例：只設定 `SC-FRONTAGE-MIN >= 5500mm`。A 筆為來源完整的 5000mm，B 筆 unknown，C 筆為來源完整的 6000mm；利用候選地範本及讀取 mock 呼叫 `build_site_comparison`，沒有寫入任何候選地。

- 結論 `eliminated`，子項分別 `eliminated/unknown/pass`：**淘汰結論正確，不應改為 unknown 來掩蓋確定不符**。
- B 筆仍存在於矩陣的 `components` 及合併 `reason`：不是原始資訊完全消失。
- 但 `missing_evidence=[]`、`next_actions=[]`、`open_evidence_items=0`：後續追蹤確實漏項。

建議：判定與待補證據分開，遞迴收集 unknown 末端子項；保留 candidate、criterion、逐筆／逐系統 field path、理由與所需證據。`_next_actions` 目前按 candidate＋criterion 去重；修補時可按條件分組但須保留全部未知子欄位，不能收集後又去重丟掉。摘要計數須定義是條件數還是子證據數。請確認及補充巢狀／重複／不適用的測試設計。

### AG-004：重複檢查會改變診斷，但直接移除清空行為不安全

證據：`scripts/lib/model3d_openings.py:19` 至 `:78`。

已以單一合成房間重現：後牆長 2400mm、窗寬 3100mm、窗心 ratio=.5、窗台 900mm、窗高 1200mm、樓高 3000mm，無門洞，外緣區間後牆 `[0,2400]`。

- 第一次：`invalid-candidate`、`requested_face=rear`，含 `insufficient-assumed-jamb-budget` 與 `not-fully-on-candidate-exterior`。
- 第二次對同一物件：`no-exterior-face`、`requested_face=null`，改成 `no-confirmed-candidate-exterior-face`。

但目前只找到 `scripts/lib/model3d_review.py:483` 一處生產呼叫；沒有證據證明現行流程必定對同一物件連跑兩次，或現有畫面已因此錯畫。應分開寫「已確認非冪等」與「尚未證實的執行路徑影響」。

原修法若只刪 `window_face=None` 會破壞防護：SVG 的 `scripts/lib/model3d_plan.py:275`、`:309` 及 3D 的 `scripts/templates/model3d.html:1505` 仍按 face 畫窗／洞，不是所有 consumer 都讀 `window_review.renderable`。既有 `tests/test_opening_rationality.py:30`、`:54` 明確要求被禁止／無效的有效窗面為 None。

建議比較：保留不可變 requested face 與衍生 effective face，或建立等效的重評估契約；**無論哪個方案，都必須保持無效窗、神桌後窗不繪出**，並允許輸入修正後真正重新評估，不能永遠回傳陳舊結果。列出全部 consumer 與回歸測試後再修，不只改掉既有測試斷言。請重新評估 P2 是否有足夠現行影響證據。

### AG-005：HTML 與參數化流程的 RF ID 不同，不是本輪樓層缺陷

反證：請完整讀 `CLAUDE.md:75` 至 `:79`。原文先限定 parametric branch 使用 `floor-rf`，隨後明列 HTML branch 的 `*_floor-4.svg` 是沿用舊名的屋頂層。

C 整合比較屬 HTML 衍生資料。解析 `structured/candidates/c-integrated-options/layout.js`，三案最後層 ID 均為 `floor-4`，label 均為 `RF 設備層`；對內嵌模型的查核同樣顯示 RF 語意，而非多加第四住宅層。

`scripts/check_c_integrated_playwright.cjs:61` 目前嚴格檢查現行資料契約，沒有證據顯示它造成現有輸出失敗。為一項尚未要求的命名遷移先放寬驗收，反可能漏掉 manifest、hash 導覽與模型不一致。

Codex 建議撤回「目前 P2 缺陷」。如需統一命名，只能列另案、跨 consumer 的協調遷移建議；請指出任何能推翻以上結論的現行反例，不要把未來可重構等同現在有錯。

### AG-006：700mm 是舊圖初篩門檻，不能等同照護核可

`house_design/owner_consistency.py:135` 的歷史 HTML 幾何檢查確實傳入 `door_min_mm=700`、`mode=draft`；`inputs/requirements.json` 的 A／C 孝親房與衛浴、B 衛浴等另有 `door_clear_mm=900` 目標。數字不同本身不證明照護需求被判通過。

同份報告已在 `owner_consistency.py:111` 保留「需求與歷史格位尚未有完整明確映射」insufficient，`:166` 說明是示意警示，`:393` 說明一致性不等於設計可行／合規／驗收；另有 A 照護功能專項。請檢視完整報告及呼叫鏈，提供「哪一個需求在什麼資料下被錯稱已完成」的反例。

同意可把 700mm 的用途與限制就地說清楚，並針對有明確映射的照護房間查 finished clear width；沒有映射／完成面證據時仍 unknown。不同用途的門不應一律改 900mm；名義洞寬也不是完成面淨寬。「一般標準為 800mm」若無適用條文及用途，不應當作已查證通則。

### AG-007：外部連結可維護，不代表離線執行會失敗

`rules/kaohsiung_review_rules.json:99` 至 `:111` 的 GitHub main URL 確實可改進可追溯性，但該規則 domain 是 `fengshui`、execution 是 `advisory`、verification owner 是屋主；不是官方法規引用。

本地 `Docs/ABC_design_revision_checklist.md` 存在。`house_design/review.py:650` 的法源查核不處理 fengshui，也不下載 URL；目前沒有證據顯示離線檢核會因這個連結中斷。未做連線檢測，不能宣稱 404。

可以建議保留本地參考、版本／雜湊及可選遠端連結，但要查實際 consumer 如何產生連結。單加一個 consumer 不讀取的 `local_path` 欄位不等於離線參考已修好。請將新缺陷影響限縮到有證據的範圍，或補上執行失敗反例。

### AG-008：支援的現代 JS 引擎容許這兩個字元

`house_design/rendering/html_payload.py:7` 與 `house_design/dashboard.py:13` 的 serializers 確實不另轉義 U+2028／U+2029，但 ES2019 JSON-superset 已允許它們出現在字串 literal。

Codex 已呼叫這兩個**實際 Python serializers**，輸入含 `before\u2028middle\u2029after</script>` 的字串，將產出以管線交給 Node v20.20.2 的 `vm.Script` 解析 `var payload = <encoded JSON>; payload.text`。兩者皆成功解析且字串完全往返，結束 script 標籤的 escaping 也保留。這是小型語法反例，不是瀏覽器／整套場景測試。

`scripts/README.md:134` 要求 Windows Node.js 20+ 與 Edge／Chrome；目前不以 ES2018 舊引擎為支援目標。Codex 建議撤回「這兩字元會讓現行頁面白屏」的缺陷結論。若仍主張成立，請列具體支援引擎版本、使用實際 serializer 的最小失敗案例及錯誤訊息；不要只引用舊版 ECMAScript 限制。額外轉義可另列舊引擎相容建議，不等於目前已重現 bug。

## B 棟工作預留區：不自行發明 RF 洗衣方案

已恢復第一輪末尾一項設計辯論：工作預留區經儲藏室會有日常家務／搬轎衝突；Antigravity 提議以「洗衣已正式搬到 RF」作可接受反證。

目前並沒有這項反證：

- `inputs/b32-entry-options.json:42` 已標「非已成立工作陽台」，`:52` 明列需經儲藏室。
- 同檔 `:97` 仍列原獨立 1F 工作陽台未完成；RF 水塔、熱泵等亦未排。
- `Docs/b32-entry-options-v1.md:15`、`:52` 保留原需求缺口。
- `inputs/requirements.json:980` 的 `B.floor-1.balcony_b` 原工作陽台目標 5m²、最低 4m² 仍存在，沒有正式 RF 取代決策。

因此可以同意這是必須研究的生活動線風險，但不能稱原案已把日常洗衣正式塞入儲藏室，也不能把已揭露缺口當成全新發現，更不能替屋主改需求。

請補兩個最小變動候選及代價：在自身 32 地坪內如何取得獨立家務路徑／工作區；若改層，日常上下樓、給排水、外窗／排濕、維修、屋頂其他設備及家規保護區付出什麼。不能預設後巷存在、借鄰地／騎樓、縮小武轎、刪原工作陽台或宣布屋頂可加蓋；未能驗證者列未解，不要求屋主先替我們選一個未計算的答案。

## 第二輪請回覆的內容

先完整讀原題綱與本文件，遵守相同唯讀、資料權威、隱私與資源限制。引用對應函式與 consumer 的完整相關段落，不以大檔前 80 行當作整個模組已審。

1. 依 AG-001 至 AG-008 回覆「接受／部分接受／撤回／維持」，每項給理由與證據。接受僅表示你接受此處的技術範圍，不要替 Codex 宣稱已接受你新提出的修法。
2. 對確認缺陷提出最小相容修法、affected consumer 與輕量回歸測試；先不改檔、不重生圖，不把調整測試期望當修正。
3. 重新精簡輸出第一輪第三／四節，以及 B 工作區分析；已知未解需求與新缺陷分開，不捏造 RF 解答或把比較方案採用。
4. 補原題綱十區的覆蓋表：每區實際檔案／相關行段、未讀部分與結論限制。特別補選地／容量／機電、封存／設計師交付、ABC 原需求到各自比較方案的介面。沒有足夠證據的區域標未完成，不填「無問題」。
5. 新發現延續 AG-009 起編號，提供具體觸發條件與可觀察結果。若只剩未知地籍／專業核定，不把未知當 bug，也不把兩模型同意當簽證。
6. 核對引用來源雜湊；與下方不同時說明哪檔變動，不用 HEAD 取代工作樹證據。若工具不允許執行 `sha256sum`，如實寫尚未比對，不能虛報執行。
7. 最終回覆約 120 行精簡文字／表格，不重貼題綱、整份原始碼或大量終端畫面；附真正仍有分歧的項目及什麼證據能收斂。這是第二輪意見，尚須 Codex 再核對，不先叫屋主逐項決定。

## 來源基準 SHA-256

下列是 Codex 交叉查核時的來源快照，不可追認 Antigravity 第一輪確實讀過同一內容。僅新增本文件不代表舊圖已重新驗收；本輪沒有新的瀏覽器 passed 結果。

```text
e3457afbd6943464c646797221ec799e3e8a4eab7d0d0cad33f94eb9c9629796  AGENTS.md
21475d5670fc8acd082f6bb725108d48e8a4429d218fb5da887eb0789f90a96d  CLAUDE.md
9b0f8a3db4214aac0327ddd43eb1d0c03b3463c21b838664cf378235b9b4b940  house_design/pipeline.py
7a1b67494d6124df621eb76969b88ebfbc20609fef86ec8498cd85f80ebc3121  scripts/export_model_3d.py
2cb109bc5d3c86c058e5bb11f28262e48f15d267a6bf951e97275d5b5481a099  scripts/lib/model3d_openings.py
44dad0c8ada3fbc9825b0f5d38d612adb90b00736def8d19be9ba4f82182fed1  scripts/lib/model3d_bc_flow.py
ce39a61c85628c2cd48ffeff15cab383d5867571e9407942f25157befea0ba3f  scripts/lib/model3d_fengshui.py
edf0f09fd7fa3d28c4f6f2ebc371f64ac2fc8b94a6b48981cc92b1521f0b0028  scripts/lib/model3d_mdf.py
9b5675c5c4e933d34c8c0c38c7067f6540608df61b4b28f43483c52b1fcbadc3  scripts/lib/model3d_space_efficiency.py
d36341816135c65d75ff96e98f6103767ae169b237a669a63167619589d8cd08  scripts/lib/dimension_overrides.py
3337739d1d577e9590e71c29074302636a7b47a7b06293995477410f0863c55e  inputs/a-mdf-under-stair.json
db8044a048845e793d88305947088142679bb8272e3f58784a1bb54c69f634cf  house_design/rendering/html_payload.py
2d7a05f3aed9510274206067955e50a9fb145aa7377c15bef510106b5c9fe73a  house_design/review.py
3b5d9ba9311c810ffbccb17ad88a917296a13797f932004a0cbcf4e9dd16ad5c  house_design/intake.py
883f2adbe8374835a082c18dda7fe252e6021e795ea2d1915c100e189953bcae  house_design/sites.py
c407735841f79c599cd087ad5a9853f1110f50652cefa93b62945addedb5f930  inputs/project.json
90fc8b31396f4ccae9b7f6e8c6be0aa6249c12255005c6b09c70e63840d4027c  scripts/lib/model3d_plan.py
355bba1192a91f2eabeac5ec2a88ece5b7ae76db063eb220e81ff5d4a6c85c4e  scripts/lib/model3d_review.py
35fcd8d6d2e153779e010b51cc8098a3fd32126d5fbf1eed304af50fa3c23862  scripts/templates/model3d.html
0a5d1377b97a36d855767fe29cfa8c861b1b3c3444ccdf997d248146d0f7d9c9  tests/test_opening_rationality.py
2eb9b78ac443269dd94f0a31af90d79e65af527eb1b258c27fa0a9d6d5c46770  scripts/check_c_integrated_playwright.cjs
46cc57a2a9b27fed822673c4413a68217397313091beef99b392e99ce1c16ff5  structured/candidates/c-integrated-options/layout.js
2912259d3155a1ca1f9bf2703950811b9a7273a9cb3a92596057b422ce3b4b42  structured/candidates/c-integrated-options-3d.html
dd1350789e38936bdadfc950f00a4e12486495109e3f7cfe3e4a9c6ec0ae713f  house_design/owner_consistency.py
7d27700ad835a3edd985e06ac0a229ea0aa7c0094fe302c88b21d32aa92bd066  inputs/requirements.json
f1c9dc402fe692433c2edb7de89c2c196d34b447a8633517a62e00df2673c4f4  rules/kaohsiung_review_rules.json
2dfb195cbad47b944bfa4f8d5a4234faa6b347cb8e5821845c8cd32b8075e81f  house_design/dashboard.py
c63612fdb57ffc4f57bb171f99c00e88c3b75bb03d7218c75defb95ceb68995b  inputs/b32-entry-options.json
60b750c3cd0505c69f08cc39630d662818d2c576ae4c302a993df4a8456b9687  Docs/b32-entry-options-v1.md
7381d9938c2e87044024805bd03e2a788728360effe798abfb87c945b49fa4d8  Docs/antigravity-project-review-brief-v1.md
```

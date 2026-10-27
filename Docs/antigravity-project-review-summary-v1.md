# Antigravity／Codex 專案交叉審查：可執行清單

> 2026-10-27續作：AG-004已完成原始窗向／有效繪圖狀態的來源修復與輕量重評回歸；既有圖面未重產，不代表新SVG／3D畫面已驗收。影響及上游來源更新見[目前維護索引](project-status-v1.md)。下文保留10/16當時結案與待辦，其他P3不因本批而自動完成，也未重啟Antigravity CLI。

2026-10-16，核對至 Antigravity 第四輪及 AG-013 最後反證回覆。**狀態：五項已收斂 P2 均已分批修復並通過小範圍測試；AG-009全量需求對帳亦已完成。其他P3／增強仍待處理，不是全案無缺陷、方案採用或建築／法規／風水簽證。**

## 屋主先看這裡

已收斂五項 P2 程式／契約缺陷，現已在不改 ABC 格局、不補造地籍資料的前提下完成程式修復。另有門窗重評估的 P3，以及需求對帳、來源可攜性等增強。最後回覆中 Antigravity 已接受既有測試與實際函式反證，撤回 AG-013 現行缺陷結論，不列入修復、不擴張設定接受值。

目前沒有需要屋主裁決的未解模型技術分歧，不需再啟動泛查或重跑 Antigravity CLI。未來實作若發現新證據或涉及真正設計取捨，另案記錄與討論；不要把這次收斂當作整個專案毫無問題的保證。

原交叉審查階段沒有變更程式、原需求、家具／實物、HTML／SVG／3D、交付封存或既有雜湊。其後兩批修復僅改程式、測試與說明，沒有重新產圖或生成現有報告；未啟動新 browser／WebGL 或全套測試，沒有新的渲染驗收 passed。模型共識只用於收斂問題與修法邊界，不證明實際土地能建、照護能用或搬轎已通過。

## 第一批實作進度

AG-001（快取相依／條件附圖）、AG-003（未知子項證據漏列）、AG-010（會議包版次）已完成；83 項針對性測試及 Ruff 通過。既有圖面、選地報告與會議包未重新生成，不宣稱舊檔內容已更新。來源雜湊、測試命令及實作邊界見 [第一批修復紀錄](antigravity-review-fixes-batch1-v1.md)。

## 第二批實作進度

AG-002（已選基地面積證據）與 AG-011（非循環本版圖面證據快照）已完成。第二批新測試及既有回歸分兩組共196項、Ruff均通過；原有未知資料、專業待核及未採用方案維持原狀。舊版缺快照的報告不能自動綁定今日資料通過，須以相應來源重建。契約、相容性、實物清冊隔離、測試命令與雜湊見[第二批修復紀錄](antigravity-review-fixes-batch2-v1.md)。

## AG-009 增強進度：已完成全量對帳，不改圖或採用方案

66項原需求在ABC主案、B32兩案、C整合三案分開共170列，含RF；停車／C獨立公衛另追蹤。新增明確id映射、處置與來源綁定，聯集面積／80、100、115mm敏感度及共用不加總護欄。90項針對性測試及Ruff通過；沒有重產HTML／3D或改需求。見[可讀對帳表](../structured/reconciliation/requirement-ledger.md)與[實作／缺口紀錄](abc-requirement-ledger-v1.md)。

## 五項已確認且有範圍共識的 P2

| ID | 來源與問題 | 修復邊界／必要驗證 |
| --- | --- | --- |
| AG-001 | `house_design/pipeline.py:96`：model3d 相依與條件附圖追蹤不全，可能快取陳舊圖 | 明列實際資料／模板／資產依賴，加本地 Python 傳遞匯入的靜態護欄；依真正的 mdf_study、frontage_study_file 列產物。模擬來源變動、無關檔變動、應有附圖遺失；只在測試暫存區動 fixture，不刪現有圖。 |
| AG-002 | `house_design/review.py:100`：已選基地只要正數面積即可 pass，缺來源仍通過 | 保留現有數值相容，定義與地號／m² 綁定的查核來源；缺資料 unknown、m²／坪不一致明列、不假裝可建。現在 selected_site=null，沒有把目前32坪目標誤判成基地已通過。 |
| AG-003 | `house_design/sites.py:446`：複合條件被淘汰後，其餘未知子項漏入待補／待辦 | 保留確定不符時的淘汰結論；另遞迴收集未知末端，保留逐筆／逐系統欄位、去重與摘要契約。不能把淘汰改 unknown 來掩蓋已知不符。 |
| AG-010 | `house_design/meeting_pack.py:445`：讀 revision，但 handoff 寫 revision_id，會議包版次空白 | 優先讀 revision_id、相容舊 revision；測 JSON／HTML／Markdown 及缺交付包狀態。現有公開 R001 helper 與既有 pack.json 已重現，修生成器不等於授權重寫交付封存。 |
| AG-011 | `house_design/review.py:751`、`house_design/planning.py:195`：正式 review 沒將本版圖面證據／自訂 root／實物介面傳入 risk review | 用與當前專案、版次、模型、coordination 綁定的獨立可驗快照，避免 report→planning→report 的 hash 循環；維持防竄改與具名情境證據，不把裸 check pass 當批准。測自訂資料隔離、錯版／異專案／變更模型、缺人工證據及重跑 hash 穩定。 |

上表保留原審查的問題位置與修復邊界；五項現均已實作，實際新位置與驗證範圍以兩批紀錄為準。原定先 AG-001／003／010，再 AG-002／011 的順序已完成。

AG-011 在審查時提出的獨立快照，第二批已實作為 `house-drawing-evidence-v1`；包含 project／requirements、revision、model／manifest 雜湊與 coordination／overlay／findings，不含 planning／release／signoff。系統比對當前資料與 scope，並從指定封存重算套繪，不只檢查自身 hash；仍不認證真人證據真偽。現有 register 是105項、0個check_ids、0個verified；這是未來綁圖面check時會觸發的介面缺陷，不是現況105項皆因此失敗。

## 後續 P3 與增強，不能藉此任意重排格局

| ID | 分類與共同方向 |
| --- | --- |
| AG-004 | P3：分離唯一的開窗原始意圖與有效繪圖狀態。重評無效窗、修正尺寸、取消／改向、神桌後牆、SVG／3D 都需測；不從舊 review 猜回已取消的窗，不只刪清空行為而讓無效窗重新畫出。 |
| AG-009 | 已完成全量 requirement-ID 處置對帳表：A24／B22／C20共66項，包括RF。B32原面積列7／22、C整合原面積列11／20，現逐項補齊對帳；未進原面積表不等於刪需求，也不表示功能已通過。每項列未容納／未核／低於目標／併入共用組／另案等狀態；需求與格局未變更。 |
| AG-012 | P3 可攜性／公開資料衛生：公開 provenance 記來源別名、原檔名、相對交付檔與SHA-256；機器路徑用版控外映射。已撤回改歷史前身來源預設為ROOT／inputs的建議；不改現有R001／封存、不替換來源bytes。 |
| AG-006 | 把700mm說明為舊圖粗篩門檻，非照護完成面淨寬核可；不一律把所有門改900mm。 |
| AG-007 | 改善本地參考文件與版本可追溯性，必要時同步consumer；已撤回「現有GitHub來源連結使離線執行失敗」的說法。 |

AG-005（HTML屋頂 floor-4 與參數化 floor-rf）及 AG-008（現代JS中的 U+2028／U+2029 白屏）已撤回為目前缺陷，不作修復理由。

## 設計需求與真正後續決策

- **A**：本輪不搬動孝親房、樓梯、收納或MDF。原有照護轉位／倒地救援、梯下淨高、防火／散熱／防潮與空調維修，仍須產品、完成面與專業證據，程式修復不能解除待核。
- **B**：維持32地坪後門搬轎優先預案、前門獨立備案，均未採用，後巷權利未知。先保祭祀朝街中軸門、背牆禁梯／梯廳、整廳上方禁用範圍及搬運／淋浴原目標。左側1000mm家事通道會與後門案已收納武轎重疊1.224m²，該建議已不採；工作陽台仍未解，不能宣稱洗衣已搬RF。停車、KTV、設備及主臥牆柱餘量仍是原需求缺口。
- **C**：保留訪客不穿孝親房、公衛外窗／有效排濕、開放客餐、床體避上層濕區等方向，但整合比較尚未採用。二樓客房討論面積9.3456m²低於12m²目標；每側115mm內縮時8.9179m²，低於9m²下限。不可用另一版面積或縮家具宣稱原需求已達。

目前沒有需要屋主裁決的「兩模型未解格局分歧」。B工作區／C面積取捨須先做不碰撞且來源一致的幾何比較，才提出清楚的面積、日常使用、機電／防潮及成本代價；尚不要求屋主盲選。法規、結構、祭祀家規接受、後巷權利、實物搬運等仍分別需要相應專業／家人／現場證據。

## 第四輪新增 AG-013：已接受反證並撤回，不納入修復清單

Antigravity 稱 `scripts/check_html_consistency.py:117-133` 的 ifc promotion 結構不匹配，因為 `{"cell_overlap":["critical"]}` 不升等；建議另接受 critical 字樣。

Codex 反證：既有 `tests/test_html_consistency_metadata.py:253-286` 明確使用 `{"cell_overlap":["cell_overlap"]}`，`:307-341` 使用 `{"room_target_mismatch":["room_target_mismatch"]}`，都斷言升為critical。這是現有明確測試的設定契約，不是剛為了否認缺陷而改測試。

本輪已直接呼叫實際 `normalized_promotion_categories`／`promoted_level`，並用兩個合成HTML分別呼叫真正 `check_floor_geometry`，全在記憶體、沒有寫檔或跑整套檢查：

| mode／設定 | 實際結果 |
| --- | --- |
| ifc，category的陣列為空 | warning，與預設「不升等」相符 |
| ifc，category的陣列含該category | critical；真實CELL_OVERLAP與ROOM_TARGET_MISMATCH consumer皆重現 |
| draft，category的陣列含該category | warning，符合僅ifc升等 |
| ifc，陣列只含critical | warning；該token不是目前測試定義的選擇值，未找到承諾支援它的契約 |

此外 `scripts/evaluate_expert_gates.py:1112` 的選項是concept／draft／ifc，不支援報告所稱的 `--mode release`；該報告引用的`:156-157`是JSON規則讀取，並非這項promotion呼叫鏈。不要混用另一條pipeline的release模式。

Codex 不認定AG-013為已確認程式缺陷；Antigravity 在最後回覆明確接受上述反證，確認符合現有契約的輸入沒有失效反例，撤回缺陷結論。雙方同意不以未支援token不生效證明現有功能壞掉，也不擴張接受值。可另列設定語法說明或將來版本化schema整理的維護建議，但不需要屋主裁決，也不影響前述五項P2的優先處理。

## 審查覆蓋、限制與驗收分流

四輪已交換資料權威／選地容量、ABC概念與B32／C整合比較、產圖／快取、圖面交付／版本完整性、owner／planning及驗收入口的靜態證據。第四輪已更正不存在檔名，列出真實入口：

- `scripts/check_windows_playwright.cjs`
- `scripts/check_b32_entry_playwright.cjs`
- `scripts/check_c_integrated_playwright.cjs`
- `scripts/check_preparation_playwright.cjs`
- `scripts/check_html_consistency.py`

Codex核對相關實際consumer、結果驗證及finally區塊；沒有在本輪執行browser模式，不能把finally中的close嘗試稱為本輪實際回收成功。第四輪的「15個來源檔」不是已核的總數保證：main preflight會合併各比較／附圖來源並去重，應以每次真實結果的sourceHashes為準。

這是有範圍的交叉靜態審查，不是逐行／全環境無遺漏保證，不重複以100%宣告零缺陷。小型程式反例不代表法規、照護、風水或搬運演練。尚未執行本輪browser／整套pytest／場景runtime或專業查核；待實作來源改動後，需用新雜湊分批驗收，不能沿用舊passed。

後續實作沿用「一批修復＋20秒內小範圍測試＋影響清單」；重型browser與全套測試另給屋主精確命令，由另一終端執行，遇逾時／137／SIGKILL不反覆重跑。本文件的待辦清單不構成任意重排格局或重寫交付版次的授權。

## 最後單項反證回覆（已完成）

最後一輪只針對AG-013，沒有新缺陷編號，不改程式、不泛掃專案。Antigravity 的回覆重點：

1. 「接受反證並撤回 AG-013 現行程式缺陷結論」；現有測試與程式契約一致，ifc模式含category本身的設定可升等critical。
2. 更正evaluate_expert_gates的mode引用，承認只支援concept／draft／ifc，沒有所稱release模式。
3. 只保留設定語法文件／未來schema的維護選擇，不擴張現有接受值，不要求屋主裁決。

Codex 已核對並接受上述撤回，故這項分歧結案。終端逐字稿含前輪畫面的重繪殘留，仍可看到舊「AG-013已確認」段落；判定以本次提示後的明確撤回回覆為準，不把舊畫面當成新立場。

## 紀錄與來源快照

第四輪逐字稿：`/tmp/house-antigravity-round4.gdrpq7/terminal.log`，67,737,425 bytes，SHA-256 `104d782aaf566d1a57a90709d6e55f2ca467d636f5a38a4e08c4291fddffb77b`；對話`19f3ae08-ea40-46d9-87d0-41eb05539650`。

最後回覆逐字稿：`/tmp/house-antigravity-close.FgIWCK/terminal.log`，9,748,098 bytes，SHA-256 `3807fb2c289a3b009efd2a5992cbc252e8f7a68d8ebfc85d305b9ba7dc410f92`，沿用同一對話。本文件送出最後反證時的SHA-256為`bc72e09b8d9c37ddcd70934456695efe8670dd6ce37dca5e65cf35fc8cedbb1f`；收到回覆的審查結案階段僅更新本文狀態與回覆紀錄，當時沒有改動程式或圖面。其後屋主同意的第一批程式修復另見上節與修復紀錄。

前三份交叉查核文件與本文引用的56筆來源雜湊在審查結案前再次核對均相同。這些是修復前的歷史快照；第一批刻意修改的三個程式來源另記新雜湊，第一批驗證當時其餘53筆核對無非預期變動。第二批刻意修改 review／planning／cli 並新增證據 helper，另記於第二批修復紀錄，不覆寫歷史雜湊。補充第四輪引用如下；這不是新的渲染驗收來源清單：

```text
802e31167e325043b71ae683e5ac12dab81fb5bef2fa7684f0be40cb0d530871  scripts/check_windows_playwright.cjs
7afc58588d76e91241f3b803f65d347e80499aeefde9f62668dac80e094d3d36  scripts/check_b32_entry_playwright.cjs
2eb9b78ac443269dd94f0a31af90d79e65af527eb1b258c27fa0a9d6d5c46770  scripts/check_c_integrated_playwright.cjs
1bd5477f3ba7fd923c7a08c554884da4e0366f12dfaf6a2f4084ffd3637d9740  scripts/check_preparation_playwright.cjs
d57c09158b16613c95f004c9c31366ecb654e23aba0e437f37f48828e4ca6e91  scripts/check_html_consistency.py
202b762eaf93185f8011e1825a6dd7720c1ea87e4e41cff86da48873a52a0651  scripts/config/residential_defaults_tw.json
efae1116ecd7f3ccca820a7109a821eb00aebd87570f975dd32d1c0185609477  scripts/evaluate_expert_gates.py
e1c07b83d82e2231c2049f35a05435bc306d044665edbc0461cfd92e4369311e  tests/test_html_consistency_metadata.py
51e02f5100417244f12074546b9832881d34b70bac180e7f34617cbd16de58c2  Docs/antigravity-project-review-round3-v1.md
```

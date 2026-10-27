# Antigravity 第三輪：新增確認缺陷與收斂查核

2026-10-16。Codex 已核對第三輪意見；本文件是審查紀錄與接續題綱，**未實作修復、未採用格局、未重生圖面，也不是全專案驗收通過。**

## 紀錄與界線

- 逐字稿：`/tmp/house-antigravity-round3.dG3ERJ/terminal.log`，45,288,565 bytes。
- SHA-256：`3297293fb4280afc0259ed8f76421d0da160a3a6cfff4e30ad811cc02af04cef`。
- 對話：`19f3ae08-ea40-46d9-87d0-41eb05539650`。
- 前文：`Docs/antigravity-project-review-brief-v1.md`、`Docs/antigravity-project-review-crosscheck-v1.md`、`Docs/antigravity-project-review-round2-v1.md`。前兩輪文件列出的 38 筆來源雜湊再次核對，沒有變動。
- Codex 本輪僅靜態閱讀、解析既有公開檔與執行記憶體 mock 探查；未開參照來源的外部／私人內容，未改程式、原需求、實物或封存。自動命令皆限制 20 秒、一次一項；無 browser／WebGL、全套 pytest、整套場景或 pipeline。

## 已收斂的範圍

目前已有五項 P2 的缺陷範圍共識：AG-001 快取依賴／條件產物漏追蹤、AG-002 已選基地缺證據仍可面積 pass、AG-003 淘汰條件下未知子項漏入待辦，以及本輪確認的 AG-010／AG-011。這是問題範圍共識，不代表所有新提議修法都已被接受。

- DB-001：接受沿用顯式輸入清單＋靜態傳遞 import 測試護欄，不新增會啟動產圖程式的 runtime manifest。資料／資產仍須另核實際讀取鏈。
- DB-002：接受缺證據用 unknown；有證據仍需專業適用性判斷者另列 professional_review。二者均不放行。
- AG-004：第三輪接受「明確取消窗卻被舊 review 恢復」反例。Codex 同意分離原始請求與有效窗狀態的原則；選定唯一輸入意圖欄位，所有 SVG／3D consumer 都須按已審查的有效狀態繪出，不採模糊 fallback 或要求呼叫端猜兩個意圖欄位如何同步。現象為 P3，未證實目前單次產線已因此錯圖。
- AG-009：第三輪撤回舊 HTML 中文猜名映射的歸因，改列全量 requirement-ID 處置對帳表的增強建議；方向同意，數量仍須更正。
- B／C：第三輪接受先前尺寸與收納態碰撞更正。B 後門案左側 1000mm 通道與武轎重疊 1.224m²，不能用搬運分時消除；C 客房仍是 9.3456m² 討論值、12m² 原目標、9m² 原下限。沒有任何新方案在此被採用。
- AG-005／008 維持撤回；AG-006／007 維持語意／來源維護建議。不要重開已撤回缺陷或重列 AG-001～003。

### DB-001 的附圖條件不得憑空命名

第三輪使用 `frontage_Coordinate_study` 作條件名稱，這不是目前欄位。真實產圖契約在 `scripts/lib/model3d_plan.py:639-660`：

- MDF 附圖依 `plan_data(payload).layout_review.mdf_study` 與 A／floor-1 判斷，檔名取該 study；不能只憑 JSON 檔存在就要求附圖。
- 前緣附圖依各層的 `frontage_study_file` 判斷，見 `:148` 與 `:651`。
- 依賴清單只列實際讀取者；第三輪提到的 c1f brief、bridge 等是否為 model3d 本步依賴須追呼叫鏈，不因與展示相關就一律加入。

## AG-010：交付版次顯示空白，確認 P2

資料流：`house_design/architect_handoff.py:394` 產生 `revision_id`；`house_design/meeting_pack.py:445` 卻讀 `revision`，`:817-825` 再據此顯示。

Codex 以現有公開 `structured/architect_handoffs/R001/handoff-manifest.json` 直接呼叫 `_section_handoff` 與 `_render_handoff`，沒有建立／重建交付包：

```text
manifest_revision_id = R001
section_revision = null
rendered_empty_revision = true
```

既有 `structured/predesign/meeting-pack/architect/pack.json` 的 handoff section 亦為 null。Codex 接受先讀 `revision_id`、必要時相容舊 `revision` 的最小修法。測試應落在現有測試檔或明確新增檔，第二輪提到的 `tests/test_meeting_pack.py` 目前並不存在。需測 JSON／HTML／Markdown 的正確版次及舊格式回退；不是更改正式圖面版次或重寫封存。

## AG-011：正式 review 與圖面／實物證據介面斷開，確認 P2

`house_design/review.py:751-753` 先呼叫 `build_risk_review`，`:754` 才載入版次，`:757` 才計算 coordination；對 risk helper 只傳 project、requirements、register、rules，未傳自訂 revision_root、實物清冊或圖面報告。

`house_design/planning.py:195-217` 要求正式報告 schema、專案 ID、報告雜湊、不可變版次／模型相符，才接受其 check 結果。`:263-282` 缺可信 check 時已 verified 的項目會退回 needs_review。

Codex 做了兩種全記憶體探查，所有合成讀取與版次載入皆用 mock，不建立檔案：

| 探查 | 結果 |
| --- | --- |
| 同一合成項目、具本版 context proof，risk helper 收到雜湊／模型相符的合成 drawing report | status=verified、check=pass |
| 同一項目不傳 drawing report | status=needs_review、check=unknown、缺本版報告 gap |
| 真正 `build_review` 邊界 spy，在首次載入版次時停止 | 呼叫順序 risk-review → load-revision；risk kwargs 僅四項，不含上述三種證據介面 |

目前公開 register 有 105 項、0 項 check_ids、0 項 verified，因此**不可宣稱當前 105 項都已因這個原因失敗**。缺陷是未來綁圖面 check 的正式 review 路徑沒有可用證據通道；單獨 risk-review 命令仍能讀可信 drawing report，既有 `tests/test_planning.py:361-432` 就測此流程。

### 接線修法須避免放寬證據閘門與循環雜湊

Codex 接受補上路徑／證據介面的方向，**不接受直接把裸 coordination.findings 當成已驗證報告**，也不接受只把 risk helper 移到 coordination 後面就宣稱修好。

`review.py:694-701` 的報告雜湊涵蓋 planning（只排除它的 generated_at）；`planning.py:233` 的 context 又包含 drawing.report_hash。若把「當前、含 planning 的最終報告」回餵自己，會形成 hash 依賴循環／證據永遠失效。

可比較的最小安全方向：明確傳入一份已封存／已驗證、與當前 revision／model／coordination 相符的獨立圖面檢查快照，再讓 planning 與最終報告引用其穩定 hash；或設計等效的非循環 typed evidence snapshot。維持專案／版次／模型／check scope 與竄改驗證，不繼承另一份報告的 signoff 或 release。

請提出最小相容契約與測試，不直接改碼：至少含自訂 root／實物清冊不串到正式資料、當前圖面 pass 仍需具名情境證據、舊版／異專案／改模型／竄改快照仍降 unknown，以及重跑無變更時 hash 穩定。這是程式介面問題，不需屋主裁決該怎樣驗 hash。

## AG-012：本機路徑存在；收斂為 P3 可攜性／公開資料衛生改善

Codex 解析目前公開 handoff manifest，未讀被參照的外部來源：

```text
predecessor.source_root 是絕對路徑
4 / 4 個 predecessor.files[].source_path 是絕對路徑
現存 package_path 不是絕對路徑（新產包是否為絕對路徑取決於 output_root）
```

`architect_handoff.py:345`、`:406` 確實寫入 resolve 後的路徑；預設前身來源是屋主早先指定的 `/mnt/d/Desktop/houseDesign`。這有跨機器攜帶及環境路徑公開問題，但不等於已證明洩漏憑證或私人內容。

第三輪的 `owner_workspace.PRIVATE_PATTERNS` 常數不存在，實際是 `owner_workspace.py:240` 對匯入 owner draft 的 inline 正則。它不是現有全專案 manifest 政策；請更正引用及影響範圍。

**不接受把 predecessor_root 默默改成 ROOT 或 inputs 作為路徑修復**：這可能改變「歷史前身來源」的身份；inputs 也沒有必需的四份 HTML。不能為了隱去本機路徑就換掉來源或重寫既有 R001／封存來源記錄。

建議另設可攜公開 provenance（穩定來源別名、原檔名、相對 package file、SHA-256），需要本機定位時用不進版控的本地映射。保留已指定來源與 bytes 完整性；專案內路徑用相對路徑、外部來源不暴露機器目錄。未經另行授權不改現有交付包。請就此接受／修正，不把它擴大為已驗證資安漏洞。

## 覆蓋與算術更正：不能採用「100%」宣告

第三輪完成度清單列出以下不存在的目標：

| 報告名稱 | 本工作樹的真實入口／位置 |
| --- | --- |
| `scripts/check_model3d_playwright.cjs` | `scripts/check_windows_playwright.cjs` |
| `scripts/check_b32_entry_options_playwright.cjs` | `scripts/check_b32_entry_playwright.cjs` |
| `scripts/check_c_integrated_options_playwright.cjs` | `scripts/check_c_integrated_playwright.cjs` |
| `scripts/check_bc_options_playwright.cjs`／`scripts/check_c1f_options_playwright.cjs` | 沒有這兩個獨立腳本；先追現有入口是否覆蓋，不虛構已讀檔 |
| `house_design/rules/` | 不是現存目錄；有根目錄 `rules/` 與 `scripts/rules/` |

這不足以判定先前完全未讀其他檔，但使「驗收腳本已讀完」無法依該表驗證。請改列真實相對路徑、相關函式／行段及未核部分，不用 100% 或不存在的別名保證覆蓋。

另以目前 JSON／manifest 精確解析：

| 項目 | 第三輪 | 實際 |
| --- | --- | --- |
| 各棟原需求總數 | B16、C16 | A24、B22、C20，合計66，不能漏掉 RF 原需求 |
| B32 area_checks | 7／16，其餘9 | 7／22，其餘15不在面積列；不代表它們已被刪除或沒有其他功能檢查 |
| C integrated area_checks＋upper_area_checks | 11／16 | 11／20，其餘9不在面積列，同樣不等於靜默刪需求 |
| B storage 每側80mm討論內縮面積 | 10.7456m² | `(3600-160)*(3300-160)/1e6 = 10.8016m²` |

全量 requirement-ID 處置表必須從實際 JSON 列舉，RF／設備需求不能只因不是一般房間就漏掉；面積檢查僅一個維度，不可拿覆蓋表宣稱功能、法規或風水核可。

## 接續要求：鎖定收斂，不再泛泛重啟全專案

延續原題綱與 AGENTS.md 的唯讀／隱私／資源界線：不改碼、不改需求／圖面／封存、不 commit／push／安裝／登入／改設定、不開 browser／WebGL 或跑整套測試；每個工具命令最多20秒、逐項，不啟背景重跑。遇逾時／SIGKILL／137停止該次嘗試。僅讀專案公開範圍，不跟隨到 private／憑證／外部私人來源。

1. 對本文件逐項回覆：AG-010 是否接受確認；AG-011 如何用非循環、可驗證快照接線；AG-012 是否撤回換來源預設的修法；承認並修正不存在檔名／需求數／面積。AG-004 採唯一輸入意圖＋衍生有效狀態的共同原則，先不寫實作。
2. 補查**真正存在**的驗收入口：`scripts/check_windows_playwright.cjs`（2421行）、`check_b32_entry_playwright.cjs`（377行）、`check_c_integrated_playwright.cjs`（246行）、`check_preparation_playwright.cjs`（306行）、`check_html_consistency.py`（801行）。靜態追 preflight、browser runner、結果 JSON 判定、來源雜湊、資源清理與測試斷言；不啟動它們的 browser 模式。
3. 只在上述實際呼叫鏈需要時補 `house_design/rendering/`、`rules/`、`scripts/rules/` 及對應現存 tests。列已查的實際函式與不能驗的環節，不宣稱每一行／整專案零缺陷，不把未做的 browser／專業查核說成完成。
4. 新缺陷從 AG-013 起，必須有實際觸發條件、結果、目前範圍、來源及最小修法。若沒有新缺陷，輸出有範圍限制的收斂結論；不要再把已知未解需求編成新 bug，也不要求屋主處理我們尚未計算完的設計取捨。
5. 回覆約120行：先收斂表、再新發現／真實覆蓋與限制、最後真的仍有分歧的事項。不要重貼前幾輪整份報告，不代 Codex 接受新方案。技術範圍若已同意請明列，避免每輪重開相同討論。

## 新增來源 SHA-256

```text
d01ecab639b237de95343f3ff4696066c2841353c87d9e58d0dad59bf7536c92  house_design/meeting_pack.py
f51d1795d71d29d59de9de0d47c256855293f337e34fb7b1523b5bb3733f46f7  house_design/planning.py
2d7a05f3aed9510274206067955e50a9fb145aa7377c15bef510106b5c9fe73a  house_design/review.py
62dbac0496a7d3bd0318a7a01d36b819ad4b47e138cbd652c35fff0fe043d764  house_design/architect_handoff.py
8703a93762c61da2f2a2c7aa8395db0993824181e4c287def36f5b72c53f8a87  house_design/owner_workspace.py
fedb50c29b52448a6b172cc1ce3fc68be7b578e814ad9e7f77863f0b50a98d4f  house_design/cli.py
99c7169b67cec0e938a824761e739f5c3680a8f5b90ec46fe9b43baddc62d4e1  structured/architect_handoffs/R001/handoff-manifest.json
55eda028ac6c1e450586a4331b0bb4b8334773a2057553d3d2a62f32a1498d72  structured/predesign/meeting-pack/architect/pack.json
d52fb63793c98e5f4b8b93044eedba370b9c7a049f5e6820fbb7fb931829ca1f  tests/test_planning.py
```

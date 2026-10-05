# 三棟防漏項與決策驗收總表

這份表把「先想到」變成能追蹤的設計決策。已追蹤不等於已驗證，不取代法規簽證、風水專業判斷或施工授權。

## 先看與先決定

開啟 `structured/predesign/risk-review.html`。目前初稿有十二組情境，包含全棟逃生、防墜、健康材料與燃氣／電氣安全，再加上原有空間需求的逐項使用與驗收追蹤。數量及完成狀態每次由資料計算，不能把本文件的文字當成即時完成率。

目前先決定：家庭20年情境與需求分級、共餐及節慶人數、一樓完整生活、升降設備策略、祭祀用火、風水不可接受事項、三棟獨立程度、預算與分期。實物清點、車庫出入口和雨天搬運現在可先準備，涉及基地及實測的結論仍保持待確認。

對每項回答三件事：是否需要、哪些操作必須成立、何時用什麼證據確認。法規／安全與已確認全齡基準先守住；風水與配置衝突列替代及代價，不由系統自動取捨。

## 操作與交付

```sh
python -m house_design predesign risk-review
python -m house_design predesign brief
python -m house_design predesign meeting-pack
```

輸出 JSON、Markdown、HTML。在 HTML 可依分類、棟別、主題、最晚階段與狀態篩選；列印只印目前篩選的項目，會展開驗收細節。桌機及手機都可以離線開啟。

- `risk-review.html`：十二主題完整總表、當期問題、後續提醒、專業待確認及尚未檢查。
- `design-brief.html`：同一清單產生的當期問題，不另寫一份矛盾副本。
- `meeting-pack/architect/index.html`：選地諮詢開會包，保留現有選地問題並附當期防漏項；資料過期會要求重跑，不引用舊問題。
- 正式圖面 `review run` 的標準專案會附本表與連結，不把未到期施工／交屋項目全部變成選地阻擋。

要輸出到不同目錄，可加 `--output-root`。`meeting-pack --source-root` 必須指向已產生 brief／risk-review 等資料的目錄；它仍是選地諮詢包，不是後續發包授權。

## 維護唯一清單

編輯 `inputs/planning-register.json`，保留穩定 id。`planning_catalog.py` 僅保留初稿生成來源，報告不會重新生成或覆蓋已填清單。新增需求不會自動補上假的追蹤項目，會顯示「未追蹤需求」。

每項須有：title、topic、scenario、question、recommendation、alternatives、building_ids、requirement_ids、rule_ids、check_ids、dependencies、due_phase、responsible_role、evidence_required、status、basis、urgency、evidence。可填 floor_id、reason、physical_item_id。

- topic 是十二個固定主題；due_phase 沿用現有 owner_brief／finance／site_search／site_due_diligence／design／tender／construction／handover。
- basis 分 proposal、owner_preference、verified_fact、estimate、professional_required；不會因標成 verified_fact 就自動通過。
- urgency 的 P0／P1／P2 僅代表討論順序，不是屋主已確認的 must 或法定門檻。
- status 可存 unknown、in_progress、professional_review、verified、not_applicable；needs_review 是計算出的複核狀態。
- check_ids 綁正式套繪檢查的 check_id；沒設定只代表需人工驗收，不代表已有幾何通過證據。

缺責任、缺驗收方式、失效引用、遗漏主題與未追蹤需求都會顯示。重複 ID、依賴循環或格式錯誤會拒絕產表。依賴尚未完成，不能驗證後續項目。

## 如何確認，以及何時失效

先讀報告每項的 `context_hash`，完成真實決策與專業查核後再記錄：

```json
{
  "verified_by": "具名查核者及角色",
  "verified_at": "2026-10-02",
  "reference": "本版圖號、會議紀錄或驗收紀錄",
  "context_hash": "貼入該項本版雜湊"
}
```

填入該項 evidence，再改為 verified。不適用還須寫 reason，保留項目與具名證據，不用刪除代替解決。系統檢查證據綁定，無法認證簽名真偽或替代專業審查。

關聯需求未由屋主確認時不能 verified；需求確認仍走既有 `intake requirements-decide`，不要手改狀態跳過決策紀錄。本表不會自動確認或淘汰任何房間。

題目、建議、替代、驗收、責任、基地／專案、關聯需求／規則、前置決策或綁定實物變動，原證據會失效。重新產表後顯示 needs_review；不得僅複製新雜湊繞過複核。共有專案資料變更會保守要求重新確認相關項目。

收到正式圖面後：

```sh
python -m house_design predesign risk-review --drawing-report structured/reviews/R001/report.json
```

指定報告需符合雜湊、專案及不可變版次來源；不能拿合成範例通過結果證明實際設計。圖面更新後要指定新報告並複核。檢查即使 pass，整個停電／照護／搬運情境仍要有人工驗收證據。

武轎專項預設 `requires_transport_measurement: true`：實物清冊的 transport 除 assembled_dimensions（width_mm／depth_mm／height_mm）外，須有 measurement_state: measured 及具名日期來源 evidence。既有收納實測仍不等於裝上抬桿的搬運外廓；尺寸尚未補時不能標示已驗證。即使已測尺寸，轉彎、抬行與完整出入仍需實物演練。

比較修改前後，先保留前次報告到另一個輸出目錄，再使用 `--previous-report <前次risk-review.json>`。新增、內容改變及移除都會提示；移除項目不算解決。缺證據的項目只算已追蹤，不算完成。

## 隱私與判定邊界

本清單是公開設計資料，不能填姓名、健康自由文字、帳戶或精確金額。報表不讀取私有家庭訪談或預算；任務書沿用既有去識別化摘要。精確金額仍存 private，公開只寫「預算已／未確認」。不要把敏感文字貼進 title、scenario 或 evidence.reference。

需求追蹤率僅表示有對應項目，不表示生活、法規、安全或風水都符合。當期決策準備度不是既有前期閘門的完成率，兩者分開顯示，避免重複計分。法規適用、基地數字、承載、排水、消防、備援容量及驗收門檻都需負責專業依個案確認。

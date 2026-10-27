# Antigravity 審查修復：第一批

2026-10-16。AG-001／AG-003／AG-010 已完成程式修復與小範圍測試；AG-002／AG-011 尚未實作。本批不改 ABC 格局、需求、實測資料或交付封存，也沒有重新產生 HTML／SVG／3D、選地報告或會議包。

問題來源與雙方收斂範圍見 [交叉審查摘要](antigravity-project-review-summary-v1.md)。原審查文件的雜湊保留為當時快照，不改寫成修復後來源。

## 已完成的三項

| ID | 實作與相容性 | 驗證重點 |
| --- | --- | --- |
| AG-001 | 補齊 model3d 的本地 Python 傳遞相依、MDF／歷史配置資料及參數化圖面；將 parametric 排在 model3d 前，避免同輪讀到更新前的 plan.json。依真正生成的 layout.js 資料列入 MDF 平面／剖面及 frontage 附圖，不以來源檔存在代替實際生成。 | 靜態 AST 匯入護欄；來源變動與無關檔；條件附圖遺失／被改寫；損壞 manifest 強制重建，重建仍無效不得存快取。測試中的產圖呼叫均為替身，只動暫存 fixture。 |
| AG-003 | 從複合條件遞迴收集未知末端欄位，即使另一子項已導致淘汰也不漏列。保留原淘汰結論；待補與待辦依候選地／條件／欄位去重，HTML／Markdown 顯示欄位及原因，並相容沒有 field 的舊紀錄。 | A 地寬不符時仍追蹤 B／C；給水不符時仍列其他系統／權利／分界；遞迴去重、不適用分支、已知通過與舊資料顯示。 |
| AG-010 | 會議包優先讀 revision_id，缺少時相容 revision；皆缺則明示「未提供」。Markdown 同步列出交付契約版次、標籤及原警語；缺交付包仍是未取得，不補造版次。 | 真正 packet builder 的暫存資料，核對 JSON／HTML／Markdown；新舊欄位優先序、空值回退、缺包及既有 packet 回歸。 |

選地摘要的 `open_evidence_items` 現在計算「每候選地／條件／未知末端欄位」筆數，而非只算未知的父條件；另加 `open_evidence_items_basis` 說明計數口徑。這不代表已取得新證據，也不改變淘汰結果。

model3d 的 manifest 僅解析嚴格 JSON 資料賦值，不執行 JavaScript 或匯入產圖器。條件附圖限定為 furniture-plans 內的 SVG 檔名；拒絕絕對路徑、目錄跳脫及反斜線子路徑。

## 驗證紀錄

- 83 項針對性測試通過，耗時 0.46 秒；不是全套 pytest。
- 六個修改／新增的 Python 檔案通過 Ruff。
- 僅讀取目前 manifest：基本產物 17 件、有效產物共 20 件；MDF 平面、MDF 剖面與 C 一樓前緣附圖均存在。這不等同重新生成、內容正確或畫面目視驗收。
- 四份歷史審查文件共 56 筆來源雜湊，扣除本批刻意修改的三個來源檔，另 53 筆核對無非預期變動；原始審查雜湊不覆寫。

重驗小範圍測試（專案根目錄）：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest \
  -q -p no:cacheprovider \
  tests/test_incremental_pipeline.py \
  tests/test_site_missing_evidence.py \
  tests/test_site_screening_evidence.py \
  tests/test_meeting_pack_handoff.py \
  tests/test_planning.py::test_brief_and_packet_same_questions_stale_packet_disabled \
  --tb=short
```

```bash
timeout 20s .venv/bin/ruff check --no-cache \
  house_design/pipeline.py house_design/sites.py house_design/meeting_pack.py \
  tests/test_incremental_pipeline.py tests/test_site_missing_evidence.py \
  tests/test_meeting_pack_handoff.py
```

本批驗證對應的 SHA-256：

```text
a97b087113561b35d729ae7e63e4b023f2ea5791bf722ad3b1bb41ebc0bbb616  house_design/pipeline.py
161db1b16f8a5b990c4fdec116fe723de737287f4aa393bf060af1488f5bcb76  house_design/sites.py
35250dc39e884b934b42b80a555632482e4a7e160a8cb7b8eec4fa95b085aab4  house_design/meeting_pack.py
e1e80d34beda01016af37d68d1d4de05441fe862899d57b7341ea4dc66ce0e8f  tests/test_incremental_pipeline.py
d7b996e1126d8a52ace8c226ce11598be121e5eb3a64ffaec23a1a01c8da20e0  tests/test_site_missing_evidence.py
4e9cac08d76f84624c4759cb42dab891a89eaca655fb7f90e39319fdc7e3ff71  tests/test_meeting_pack_handoff.py
```

## 尚未完成與下一批

1. **AG-002：已選基地證據契約。** 保留舊數值相容，另綁定逐筆基地、面積／單位、來源與查核狀態；缺資料不能只憑正數面積通過。目前 selected_site 為 null，不把 32 地坪目標當成已取得基地證據。
2. **AG-011：跨版圖面證據串接。** 先定義與當前專案、版次、模型及 coordination 綁定的獨立快照，再接正式 risk review；不能將含 planning 的最終 report 反餵 planning 形成雜湊循環，也不能把程式 pass 當成人工／專業批准。
3. 原審查中的 P3 與需求對帳等增強仍未實作；不因第一批完成就宣稱全部問題結案。

本批未執行完整 pipeline、browser／WebGL、整套場景 runtime 或全套測試，沒有新的渲染驗收結果。既有生成報告仍是先前內容；修復將於日後重建時生效，不重寫既有 R001 或其他封存。程式測試不構成法規、結構、風水、照護或搬轎簽證。

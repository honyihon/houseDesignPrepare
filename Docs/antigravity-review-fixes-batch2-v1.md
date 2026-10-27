# Antigravity 審查修復：第二批

2026-10-16。AG-002／AG-011 已實作並通過小範圍測試；連同[第一批](antigravity-review-fixes-batch1-v1.md)，五項已收斂 P2 的程式修復完成。這不是 P3 全部完成、圖面採用、來源真偽或專業簽證。

## 本批變更

### AG-002：面積有數字不等於有證據

新增 `house_design/site_evidence.py`，正式 review 的 `SITE-PARCEL-AREA` 改讀證據評估：

- 保留 v2／v3 的面積數值格式；另加 `parcel_area_evidence`，綁定同一 parcel id、地號、m² 數值／單位及文件、查核人、日期。
- 只填數字、缺來源、未查核、欄位型別錯誤、舊地號／舊數值證據均為 unknown。明確的 m²／坪換算矛盾列 fail（資料矛盾，不是認定土地無法建造）。
- 拒絕布林、NaN、無限值及非正數。坪數可留空，僅為顯示換算，不回寫。0.01m² 僅為捨入容差，不是測量或法規容許誤差。
- 完整性 pass 只表示紀錄、換算及來源綁定完整；不認證文件真偽、不開啟私有參照、不判定可建量體。

填寫格式見[圖面工作流第 2a 節](review-workflow.md#2a-面積證據v2v3-都適用)。現有 `inputs/project.json` 不改，selected_site 仍為 null，32 地坪仍是目標。

### AG-011：正式 review 接上本版證據，但不自動批准

新增 `house_design/drawing_evidence.py`，採 `house-drawing-evidence-v1` 獨立快照：

1. 正式 review 驗證版次、檢核套繪，產生綁定 project／requirements、revision／manifest／model 及 coordination 的快照。
2. planning 驗證快照 hash，重新從指定 revision_root 驗封存與重算套繪，比對內容及情境棟層／需求範圍；不能只靠自行重算雜湊接受捏造結果。
3. 最終 review 與 planning 引用同一 evidence_hash，不把含 planning 的最終 report 反餵自身。快照不含執行時間、planning、release 或 signoff。

`write_review` 往後會另寫 `drawing-evidence.json`。正式 review 傳入相同 revision_root 與明確選取的實物清冊；不指定清冊時，以 project 同目錄為預設，缺檔仍缺資料，不誤讀主專案資料。獨立 risk-review 也使用此預設。

CLI 增加 `review run --physical-items`、`predesign risk-review --drawing-evidence`（drawing-report 別名）及 `--revision`。不指定 expected revision 時只是明確選取的比較快照，不推斷最新；正式 review 一律綁定指定版次。

相容性與失效行為：

- 仍接受最終 report.json 作輸入，但須含可驗獨立快照並與外層 model／revision／coordination 一致。舊報告缺完整來源綁定時保持可讀，指定檢查降 unknown；不把它重綁到今日資料而冒充本版證據。
- `inputs.drawing_report` 保留為穩定 evidence_hash 的別名，新鍵為 `inputs.drawing_evidence`；不能再將舊鍵解讀為最終 report_hash。原以舊報告 hash 綁定的人工證據須複核。
- 錯版、異專案／需求、來源／模型變動、套繪竄改或 scope 不符都不得沿用 pass；圖面更新後，即使數值仍 pass，也使舊人工情境證據失效。
- 單項 pass 不會自動將情境改為 verified；仍需本版具名、日期、來源與 context_hash 證據。武轎仍須搬運外廓實測，收納尺寸不代替搬運演練。

操作說明見[防漏項清單工作流](planning-register.md#如何確認以及何時失效)。

## 驗證（非全套／非渲染驗收）

兩組依序執行、各設 20 秒上限，共 **196 項通過**：

- 第二批新測試 85 項，加既有 planning／review／coordination 64 項，共149項，1.01秒。
- 第一批 incremental pipeline 護欄41項，加選地／前期／任務書6項，共47項，0.41秒。
- 七個本批 Python 檔案 Ruff 檢查通過。

所有新封存、修改／刪除、報告輸出皆限合成暫存 fixture。沒有對現有版次、實物或需求寫入，沒有啟動 browser／WebGL／完整場景／完整 pipeline／全套 pytest，也沒有重新產生現有圖面、選地報告或會議包。舊報告仍是舊內容，不沿用其 passed 宣稱本版已驗收。

重驗指令（專案根目錄、分組依序執行）：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest \
  -q -p no:cacheprovider tests/test_selected_site_area_evidence.py \
  tests/test_drawing_evidence_planning.py tests/test_planning.py \
  tests/test_review_system_v2.py tests/test_coordination.py --tb=short
```

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest \
  -q -p no:cacheprovider tests/test_incremental_pipeline.py \
  tests/test_predesign_intake_v2.py::test_current_project_models_32_ping_as_site_search_target_not_parcel_fact \
  tests/test_predesign_intake_v2.py::test_unknown_site_facts_are_not_counted_as_ready \
  tests/test_predesign_intake_v2.py::test_site_search_targets_cannot_be_promoted_without_real_selected_parcels \
  tests/test_predesign_readiness_v3.py::test_revision_review_includes_only_due_predesign_findings \
  tests/test_design_brief.py::test_brief_hash_is_stable_across_generated_at \
  tests/test_design_brief.py::test_brief_segments_requirements_by_status_and_building --tb=short
```

```bash
timeout 20s .venv/bin/ruff check --no-cache \
  house_design/review.py house_design/planning.py house_design/cli.py \
  house_design/site_evidence.py house_design/drawing_evidence.py \
  tests/test_selected_site_area_evidence.py tests/test_drawing_evidence_planning.py
```

本批驗證來源 SHA-256（歷史審查雜湊另保留，不覆寫）：

```text
1a955729fac484afaa700cb429483373749731533b1dc111302d3621111e4c6f  house_design/review.py
fbcac2570be7a0faaec82eaf1ea2db1a5bce230679f6b8443f4ab2c9d1abb586  house_design/planning.py
9c345993ee7038dc7a3cc843eeeaff0f3a79028f8a706b92cb4a730c5a3adbd4  house_design/cli.py
468506d07a420e759113ea14c26d1283396956c42e82636e5c725eef7ca422ad  house_design/site_evidence.py
749c335dfc27a924da0830746a0c5ecf52e2cba28465be34485b104fac460b6d  house_design/drawing_evidence.py
3837e0bf8e4f9cecb82520fb3cda93a0d964ef86160ab05361379d5bbf0e6f62  tests/test_selected_site_area_evidence.py
2b954473f56f5d346b4f3bbcac2a42933197f5aa532f6c02a2a6cba8c53faee4  tests/test_drawing_evidence_planning.py
```

## 後續仍待處理

P3 的開窗原始意圖／有效狀態（AG-004）、66項需求處置對帳（AG-009）、來源可攜性（AG-012）及 AG-006／007 說明增強尚未實作。本批不重排 ABC、不採用 B32／C 比較案、不改任何家規或專業待核。法規、結構、風水、後巷權利、照護及實物搬運仍需相應的真人／現場證據。

# R000 歷史來源封存修復

2026-10-05 經屋主同意修復。本次只恢復歷史可追溯性，不改 R000 原清單、模型、設計狀態或目前參數化工作檔。

## 原因及找回依據

原 `inputs/revisions/R000/manifest.json` 的 `sources[0].file` 指向持續更新的 `structured/parametric/plan.json`，不是獨立歷史副本。工作檔更新後，來源雜湊不符；原模型及清單封印仍相符，驗證器因此正確攔截。

從 Git 提交 `c62327bd42b3516aa43aa02aecdb18aa0691e696` 找回 `structured/parametric/plan.json` 的原始位元組。歷史檔 SHA-256 與原清單記載完全相同：

```text
44dca801266f1f76d403b010765fcc3377073e22532ce08344e1c4c651b014a8
```

找回檔保存於 `inputs/revisions/R000/source/plan.json`。原工作檔不回退，也不把現在的雜湊當成原版本。

## 追加紀錄與驗證

`inputs/revisions/R000/source-recovery.json` 記錄版次、原 manifest 位元組 SHA-256、時間、原因、來源索引、原路徑／雜湊、歷史副本位置、精確 Git 提交及紀錄自身封印。

驗證器對有修復紀錄的版次會：

1. 檢查紀錄封印及與原 manifest 的綁定，不能修改原 manifest 後沿用此紀錄。
2. 確認來源索引、原路徑及原 SHA-256 都與原清單一致。
3. 只接受版次 `source/` 內的相對路徑；越界、絕對路徑及逃逸符號連結拒絕。
4. 核對歷史副本的位元組必須符合原 SHA-256；沒有放寬雜湊條件。
5. 結果標示 `verification_source=audited_historical_copy`，並保留目前工作來源的雜湊，避免看起來像原路徑已復原。

有紀錄時歷史副本是該版次的驗證來源。即使工作檔剛好改回原內容，損壞的副本或修復紀錄也會阻擋，不會偷偷回退到工作檔繼續通過。沒有修復紀錄的版次仍依原清單核對。

紀錄封印提供內容一致性，不是數位簽章，也不保證查核人或文件真偽。Git origin 是此次找回的可追溯紀錄；日常驗證不需連線或依賴 Git，完整性以原雜湊相符為準。

## 不變的限制

- R000 仍為 `legacy_assumption`，每層 32 坪建築面積的歷史假設不是每筆土地 32 坪的可建證明。
- 現行 3D 就緒度仍是 `blocked`／`eligible=false`。
- 不能因來源完整性修復就宣稱法規、結構、風水、照護或搬運安全通過。
- 新的正式圖面須用新的版次匯入；目前匯入／legacy seed 已會複製來源至版次 `source/`，不得新增指向活躍工作檔的封存版次。

檢查：

```bash
.venv/bin/python -m house_design drawings verify --revision R000
.venv/bin/python -m pytest tests/test_revision_source_recovery.py tests/test_predesign_readiness_v3.py -q
```

若副本或紀錄損壞，先從上述精確 Git 提交及版控修復已知的原始內容，不改預期雜湊、不重寫 R000、不忽略失敗測試。

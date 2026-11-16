# CI 與封存資料重現

`quality` 同時檢查 Ubuntu／Windows、Python 3.10／3.12；完整 pytest、coverage、瀏覽器驗收由 GitHub Actions 執行。本機仍依 AGENTS.md 限制，只跑有 20 秒上限的小範圍檢查。

- Shapely 固定為封存幾何報告使用的 2.1.2；其版本也會影響報告雜湊。
- CI 使用 `PYTHONUTF8=1`，中文檔案及子程序輸出採 UTF-8。
- R001 的原始 CRLF HTML、LICENSE 複本及 CSV 保留位元組；一般原始碼採 LF。
- XML namespace registry 每項測試重設，避免別的匯出模組改變 SVG 前綴。

## 封存資料與原生數值

已封存的比較案，用封存 report、viewer literal JSON 與 artifact 雜湊檢查。`tests/fixtures/historical-study-seals.json` 明列基準提交及已知來源漂移；新增漂移會失敗。原有匯出器遇到過期來源，仍必須拒絕重建。

Windows／Unix 的 libm／GEOS 可在最後一個浮點位元產生差異。相關測試先重算原生結果，逐欄比較資料結構、來源、布林判定、核可狀態；只有浮點值允許絕對差 `1e-9`。這是數值重現容差，不能當成施工或照護餘量。兩份報告各自驗證真實 self-hash；封存圖面另以封存資料重繪並逐位元組比較。

## ZIP 的可重現入口

封存 ZIP 使用 Unix 建立系統欄位及檔案模式。Python 的 `ZipInfo` 預設建立系統會跟隨執行主機，因此 Windows 即使內容相同，也會產生不同 ZIP。需要重現封裝時，使用限定於該次程序的入口：

```bash
python -X utf8 -m house_design.reproducible_export scripts/export_design_discussion_basis.py --check
```

它固定 ZIP 建立系統為 `3`。討論包重核洗衣到達研究時，先獨立驗證原生結果與封存報告的 self-hash、所有來源檔位元組及整份內容；只有數值尾差在 `1e-9` 內才使用已驗封存值。原程式對報告檔的釘選 SHA 檢查仍照常執行。

離開時會還原 ZIP 標準函式、原 builder 及模組搜尋路徑。原生報告物件、來源、圖面與封存檔均不覆寫。pytest 使用相同公開 context，另模擬 Windows ZIP 欄位與數值尾差，並測試來源、尺寸、核可狀態或雜湊改變時必須拒絕。

一般設計研究與來源綁定匯出繼續使用既有 WSL 流程；Windows 可直接開啟已封存的離線包。這個入口僅重現現有且來源不變的討論資料，不能把新實測條件套回舊圖或自動採用設計。

需要查平台差異時，可另執行 `python tests/platform_diagnostics.py`；它只讀取來源、列出第一個差異，不會修改檔案或啟動瀏覽器。

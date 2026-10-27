# QA證據索引與來源更新順序

2026-10-27彙整。唯一機器索引為[project-status.json](../inputs/project-status.json)，唯讀盤點使用[check_project_status.py](../scripts/check_project_status.py)。不把本頁當新畫面驗收，也不回寫生成報告的`rendered_qa`、預期來源雜湊或封印。

## 屋主已回報的結果，不要求盲目重跑

| 包 | 已回報的run ID | 已知內容 | 本輪可給的證據狀態 |
| --- | --- | --- | --- |
| 原ABC | `house-design-cli-O9qsqw` | console為passed，12／112／128 | 歷史回報；本次未回收原始result／截圖，不作新來源passed |
| ABC整棟基準展示v2 | `house-current-design-cli-ne3nbQ` | console為passed，五案九態、36／340／341 | 同上，不因再次看到passed文字就自動接受 |
| B後右公衛／後左庫 | `house-b32-right-cli-Lnm9eK` | console為passed；既有文件記錄571檢查、202來源、20圖 | 保留原文件的當時核對紀錄，本次來源已改；不擴張到新上層或新程式 |
| C側盆／兩片門 | `house-c-bath-layout-cli-3UM6jA` | console為passed，兩案六態、24／234／300 | 歷史回報；本次未取得完整原始證據，不冒充已作本次目視 |
| C坐姿／選品準備 | 無新viewer | 純資料與有界座標研究 | 不要求新增畫面驗收，但產品／照護仍未核 |

本表run ID來自屋主貼回內容與既有文件，不虛構執行時間、來源清單、截圖存在或session回收。`raw_result=null`只是原始檔尚未納入本索引，不是否認屋主曾經跑成功。

## 回收資料時怎樣判斷

1. 先保留Windows原資料夾的`result.json`、`checks.log`（若有）及截圖，維持原bytes，記SHA-256。缺檔／無有效結構化結果就維持未完成，不只憑console的passed。
2. 用相應CLI的結果驗證契約逐項比run範圍、版本、來源雜湊、必需證據與錯誤；截圖另做目視。舊來源結果即使完整，只能成為該歷史來源證據，不能當本批新來源通過。
3. 原報告可能含本機使用者路徑；先保留在原TEMP或版控外位置，公開只加去識別化索引與原始SHA-256。不要直接`git add -A`把整包原報告／截圖推上去。若需遮蔽另存衍生副本，保留原檔hash及衍生關係，不將修改後bytes仍稱原件。
4. 本索引不自動讀私有路徑。只有確認可公開、未修改原bytes的副本，才可將`raw_result`填為允許的專案相對路徑；即使檔案存在，唯讀盤點仍只標`present-unverified`，不接受QA或專業核可。

## 本批來源影響與下一步

共享窗函式修復使舊報告宣告的`model3d_openings.py`、`model3d_review.py`雜湊不同。既有圖面未改，歷史結果保留；**不能只把報告hash換成今天的值，也不能略過父版來源檢查。**

修復前原始bytes已另存為[開窗函式參考](../inputs/references/source-history/20261027-before-model3d_openings.py.txt)與[提案評估函式參考](../inputs/references/source-history/20261027-before-model3d_review.py.txt)，兩者SHA-256均與既有整棟報告相符；[對照表](../inputs/references/source-history/20261027-opening-source-references.json)記錄取得方法。這是可追溯的歷史副本，不執行、不覆寫目前程式，也不將舊報告轉指這些副本來宣稱新來源通過。

重建的已知依賴層次如下，不代表現在自動執行或保證所有鎖定快照可直接換版：

1. 原ABC共用產圖與早期比較：`export_model_3d.py`；之後依既有順序處理`export_c1f_options.py`、`export_bc_options.py`、`export_arcade_capacity.py`、`export_preparation_review.py`。
2. `export_b32_entry_options.py`、`export_c_integrated_options.py`。
3. `export_interior_improvements.py` → `export_b32_rear_right.py` → `export_current_design_basis.py`。
4. C照護依次`export_c_care_entry.py` → `export_c_care_route.py` → `export_c_care_bath.py` → `export_c_care_bath_door.py` → `export_c_care_bath_layout.py` → `export_c_care_bath_readiness.py`。

完整上游產圖預設交屋主另終端，不能在代理背景重跑。先確認固定`base_plan_hash`、屋主接受的快照／取捨與實際幾何是否仍相同，再決定要更新哪些衍生包；若錨點不同，停止並列差異，不自動改expected hash、放寬測試或把變更當成已接受。原始圖面／封存不被這份順序授權覆寫。

這批**沒有執行上述重建**。因此現在直接跑末端preflight／資料`--check`可能會先因舊來源被攔截，這是護欄正常運作；先看唯讀盤點輸出的變更，不反覆重試。

## 上游更新後，才逐項安排畫面驗收

以下是準備好的指令，不是目前要求全部重跑；先按影響範圍選擇。每次只跑一個，不與全套測試／場景工作並行。

```powershell
node '\\wsl.localhost\Ubuntu\root\workspace\houseDesignPrepare\scripts\check_current_design_playwright.cjs'
node '\\wsl.localhost\Ubuntu\root\workspace\houseDesignPrepare\scripts\check_c_care_bath_layout_playwright.cjs'
```

B一樓或原ABC只有在其產物／來源也更新、需要新證據時才各自跑`check_b32_rear_right_playwright.cjs`或`check_windows_playwright.cjs`，不以別包passed取代。本輪純導覽、文字與候選清單不新增一套瀏覽器任務。

`check_project_status.py --check`的exit 1只表示來源／檔案檢查未齊，不等於畫面已失敗；exit 0也只表示該索引宣告來源相符，仍不驗報告封印或真正畫面。法規、宗教／風水、照護、搬運、產品與施工接受各自保留未知。

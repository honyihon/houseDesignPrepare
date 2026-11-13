# 全專案review與重整 v1

2026-11-06。以81996e1為整理前備份；本輪是專案維護及預先規劃的整理，不重新設計房間、不採用比較案、不覆寫原3D，不改任何法規、風水、外窗、面積、照護或搬轎要求。沒有自動commit／push。

## 範圍及結果

對Git公開工作檔作整體盤點：整理前1260檔，約129MB；檢查目錄、JSON語法、Markdown相對連結、重複內容、現行／歷史來源索引、全Python靜態規則與小範圍測試。不執行瀏覽器、WebGL、全套pytest或整套3D，沒有進行新的法規／產品市場／安全專項審查。

| 問題 | 處理 | 邊界 |
| --- | --- | --- |
| 首頁與機器索引停在2026-10-27，最新模式／圖面入口分散 | 首頁改短版導覽；機器索引加入條件規劃、高雄厝／C整合、新風及B深化 | 規劃入口不是整案採用或法規通過 |
| 三四份文件重複堆疊設計進度，容易將舊「最新」當現況 | 分工為首頁導覽、狀態、工具手冊及穩定套繪方法；四份舊導覽另存Docs/archive | 全部比較圖／JSON／manifest留原路徑，歷史連結維持 |
| 舊圖來源已改但全部混在目前狀態 | 索引明列7現行／6歷史；預設check只要求現行，include-history仍可完整檢查 | 歷史差異照列，不更新預期hash或假造passed |
| .claude/settings.local.json為個人本機權限卻納入Git | 加入忽略、從索引移除，保留本機原檔；提供不授權的空白範例 | 沒有修改或擴大實際權限，可從81996e1恢復 |
| 舊slash指令遇缺檔就要求整套重跑、IFC只提醒decision欄 | CLAUDE與兩份指令補現行模式／資源界線，缺檔不自動跑全流程；IFC補報告hash／時間綁定 | 未執行slash指令或更動任何專業簽認 |
| 12項Ruff靜態錯誤 | 修正延後匯入註記／排序、相鄰點zip明示strict=False、未使用迴圈變數 | 只修腳本表達；不生成或變更舊幾何產物 |
| 新包只有來源雜湊，索引未檢查其產物manifest | 有提供manifest的包同時核對產物位元組與報告識別 | 不當報告封印、畫面或專業簽認 |
| 缺一個便宜的日常整理檢查 | 新增check_repository_health.py：檔案／JSON／連結／本機檔誤入／重複提示 | 唯讀、有檔數／大小上限，不自動刪檔或產圖 |

## 哪些不刪

五組重複內容核對為模板與產物、或前後方案獨立局部圖，不作垃圾檔刪除。歷史設計、未採用方案、前後備案、對話來源、正式版次、QA紀錄及source-history均保留；它們的用途是比較、回歸與決策追溯，不是可直接相加的完整設計。

舊HTML解析流程、每層32坪參數案例及歷史CLI仍被測試／封存引用，因此保留並集中歷史入口，不進一步大搬動。未清除本機快取、私人檔、屋主瀏覽器或既有session。

**本輪唯一退出版控的檔案是.claude/settings.local.json；磁碟上的檔案仍在。** 四份舊導覽是歸檔而不是抹除內容，原版也可從81996e1恢復。

## 來源與驗收缺口仍在

- 全庫另讀46份宣告source_hashes的JSON：44份使用檔案路徑可直接比對，其中29份宣告來源相符、15份有差異；另外2份使用邏輯鍵（project／requirements等）須走專用解析器，不能誤報檔案遺失。這是宣告雜湊盤點，不是完整語意、報告封印或方案驗收。
- 歷史ABC整棟、B一樓、C局部／選品的共享開窗與檢查來源早已不同；C概念合圖快照綁定的舊導覽也早已改版，維持歷史／待核。
- 本次修了舊preparation匯出器的靜態寫法；引用它的前期會議、B家務／服務及需求對帳快照不能沿用來源相符聲明。它們已是歷史研究，本輪不重生圖或改其預期hash；如要復用，另開明確重建任務。
- 現行7包的來源／產物可分別查驗；「檔案相符」不等於房子可建、風水核可或真實運輸／照護可用。
- 家規、A套衛取捨、B浴廁原面積／外窗、外牆權利、梁板、產品及實物演練，依各專題保留未解。預先規劃有介面，不表示資料已到。

上述15份歷史差異主要是同一組共享開窗／檢查來源向下游傳遞，不能靠批次改hash或刪檔消除。完整清單見本輪靜態紀錄；預先規劃與當前看圖入口不因此自動改版。

## 維護方式

現在只改[inputs/project-status.json](../inputs/project-status.json)的入口／工作索引，不再把完整設計日誌複製進每份README。設計內容寫專題文件，歷史材料按日期標示；被source_hashes綁定的方法／圖面不拿來寫頻繁進度，以免無關更新使凍結快照失效。

安全小檢查在專案根目錄逐條執行，每條最多20秒：

~~~bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/check_repository_health.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/check_project_status.py --check
timeout 20s .venv/bin/ruff check house_design scripts tests
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_project_status.py tests/test_repository_health.py
~~~

本輪結果與實際來源雜湊另記於[靜態review紀錄](../inputs/references/project-reorganization-static-review-20261106.json)。後續瀏覽器／全套測試由屋主另開終端機，沒有執行就不報passed；整理不自動擴大為新一輪選品、法規、風水或工程定案。

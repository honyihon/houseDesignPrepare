# 專案目前入口、待辦與維護狀態

更新：2026-10-27。這是唯一的導覽／待辦入口，不是新的設計權威、採用紀錄或施工核可。原66項需求、105項規劃清單、圖面及R000／R001封存不改；屋主同意本批維護，不等於同意所有格局或產品。

## 現在從哪裡看

**先看ABC整棟討論基準，再單獨看C照護續版；兩者尚未合成同一套已採用配置。** B維持後巷優先與獨立前門備案，不借另一版的通路或面積。所有下列圖面仍是凍結討論快照。

| 用途 | 文件／平面 | 3D／資料 | 狀態與限制 |
| --- | --- | --- | --- |
| ABC整棟基準 | [取捨](current-design-basis-v1.md)／[HTML](../structured/candidates/current-design-basis.html) | [3D](../structured/candidates/current-design-basis-3d.html)／[112列對帳](../structured/candidates/current-design-basis/requirement-ledger.json) | 五案九態；A套衛待選、B前後門分案、C單台2F洗衣機。不是整套採用 |
| B一樓對照 | [限制](b32-rear-right-v1.md)／[HTML](../structured/candidates/b32-rear-right.html) | [3D](../structured/candidates/b32-rear-right-3d.html) | 兩版三態；僅一樓深化，不代替整棟基準或實物搬運驗證 |
| C最新照護排法 | [側盆／門組取捨](c-care-bath-layout-v1.md)／[HTML](../structured/candidates/c-care-bath-layout.html) | [3D](../structured/candidates/c-care-bath-layout-3d.html) | 兩案六態，側盆250mm偏側及右扶手旁18.5mm餘量仍待核；未併回ABC基準 |
| C坐姿與商品準備 | [決策說明](c-care-bath-readiness-v1.md)／[研究摘要](../structured/candidates/c-care-bath-readiness/summary.md) | [16欄詢問表](../structured/candidates/c-care-bath-readiness/supplier-checklist.csv) | 純資料研究，沒有新3D；四類產品身份與16項實際尺寸仍未知 |
| 一般衛浴選品 | [三組候選及價格口徑](abc-standard-bath-shortlist-v3.md) | [照護產品另案](c-care-bath-market-products-v1.md) | 候選不等於已選定，不因本表移管或換家具 |
| 原ABC與早期比較 | [A原頁](../AbuildingView.html)／[B原頁](../BbuildingView.html)／[C原頁](../CbuildingView.html) | [原ABC 3D](../structured/candidates/model3d.html) | 歷史對照，12層／112區／128件；舊B有已知家規與需求缺口，不是推薦直接採用版 |

## 本批已處理

- **WIN-001／AG-004開窗重評估**：原始方向存在cell的`window_request.face`，`tour_features.window_face`只供SVG／3D繪圖。重建／改向／取消以`set_window_request()`明確更新；尺寸仍以`window_mm`為原始來源。不從舊`window_review.requested_face`猜回窗戶。
- 尺寸、門洞、外牆接觸或樓高修正後可重新評估；未修正的衝突重評仍不畫窗。神桌後背牆、取消與零寬情境不會因重評而重新出窗。
- 新增[機器可讀入口／待辦索引](../inputs/project-status.json)與唯讀檢查程式。它不是第二份需求表，不修改candidate、verified、產品或方案採用狀態。
- 整理[QA證據索引](qa-evidence-index-v1.md)與[下一批A照護／C商品資料表](a-care-and-c-products-next-v1.md)，不要求現在全部重跑或盲選。

## 重要：共用來源已改，凍結圖沒有重產

本批刻意修正`model3d_openings.py`及`model3d_review.py`。引用它們舊雜湊的報告應被判為 **source-changed-rebuild-required**；既有檔案仍可閱讀，但不是以新來源重算的圖，也不能拿舊passed證明新程式／新圖已驗證。

**沒有更新既有報告的預期雜湊，沒有重產HTML／SVG／3D，也沒有重寫封存。** 不放寬各包既有preflight。只重跑最末端CLI會先被過期上游攔截；此時應停止，不能用更新digest或重複開瀏覽器湊通過。上游重建及證據處理見[QA索引](qa-evidence-index-v1.md)。

修復前兩份程式另存於[歷史來源對照表](../inputs/references/source-history/20261027-opening-source-references.json)，已逐份核對與既有整棟報告宣告的SHA-256相符；只供追溯，不更換報告來源路徑，也不代表來源恢復或畫面驗收。

唯讀盤點指令，每次20秒內，逐項執行：

```bash
cd /root/workspace/houseDesignPrepare
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/check_project_status.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/check_project_status.py --check --json
```

第二行來源未更新時預期exit 1，並逐檔列出舊／新SHA-256；exit 2代表索引本身讀取／格式有問題。這兩行不寫任何檔案，不執行封印驗證、生成器、preflight、browser或場景，也不接受任何QA。來源相符仍只代表宣告的檔案雜湊相符。

## 接下來的優先順序

| 工作ID | 下一件事 | 完成前仍保留的限制 |
| --- | --- | --- |
| QA-001 | 回收原結果作歷史證據；確認新來源的上游重建範圍，再安排受影響圖面的驗收 | 屋主console回報與原始result、來源相符、截圖目視分開。不能只把report的not-run改passed |
| A-CARE-001 | 先核A1門組與整段照護動線，再議A2套衛 | 名義900mm不等完成淨900mm；115mm是假設預算，不是實測；不能縮床或孝親房來硬配 |
| C-PRODUCT-001 | 補門、盆、折椅、扶手完整商品圖，再做安全足尺確認 | 16個值保持未知；不以市場摘要／小模型值填成實測或取得照護信用 |
| A-SUITE-001 | 用面積、收納、外窗及工程代價讓屋主選擇 | 新套衛比較使主臥約12.13m²、低於16m²目標，且兩件收納移書房，尚未同意 |
| B-CARRY-001 | 取得裝桿外廓、巷道／門外條件與權利，續排IDF、乾衣及屋頂設備 | 保留前門備案；1200×1700×1800mm是收納規劃值，不是完整搬運演練 |
| MEP-SITE-001 | 逐筆地籍／可建外框、停車、立管、排濕及屋頂檢修整合 | 每筆約32坪是目標，不等每層可蓋；有後巷不等可開後窗 |
| BACKUP-001 | 屋主另行明確確認commit／push範圍後，先檢查內容、個資及暫存證據再分批保存 | 本批沒有commit／push，不自動add全部工作區；新增檔與舊改動皆保留 |

實際要補的尺寸、文件與決策已拆在[下一批準備表](a-care-and-c-products-next-v1.md)。已答覆的局部偏好可以逐項附來源整理，但不能把66項原需求整批確認或把105項規劃清單自動verified。

## 維護界限

這輪僅來源修復、測試與導覽／候選／QA索引，沒有重排ABC、採用任何產品、調整管距、縮小照護或搬運目標、刪除停車或KTV需求。原R000／R001與正式產品回覆保留原bytes。瀏覽器、全套測試、完整3D生成／runtime仍交屋主另終端執行；逾時、137或SIGKILL不自動重試。

2026-10-27本批輕量檢查：開窗與索引40項、產圖依賴41項測試通過，相關Python檔Ruff通過；抽定23份需求／產品／圖面／封存檔與修改前SHA-256全部相同。這些是程式與檔案檢查，沒有新畫面passed或方案採用。

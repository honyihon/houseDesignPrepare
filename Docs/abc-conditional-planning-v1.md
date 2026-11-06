# ABC條件式預先規劃 v1

2026-11-06，依屋主最新方向：目前只做預先規劃，等實際條件到齊後再統一套用。**現在不用提供實測資料，也不為資料未到而定死工程尺寸或選機。**

先將這套機制落在[ABC新風／室外口／檢修](abc-fresh-air-detail-v1.md)，共用的資料分層與採用流程可供後續其他工程接用；不是已完成全專案參數化或完整BIM自動設計。

入口：[條件表、備案與重算結果](../structured/coordination/abc-fresh-air-planning-v1/index.html)。沒有實際輸入的預設輸出，一律是**待資料，不是通過，也不是設計已失敗**。

## 三層資料，不混在一起

| 層次 | 內容 | 後續如何使用 |
|---|---|---|
| 固定需求／已確認前提 | 各棟獨立、B香火獨排、C隔間可關及單台2F洗衣機、原家規／外窗／面積／照護、B搬轎前後兩版、三樓既定用途一期通風 | 資料輸入不會自動改寫；需求要變需屋主另行決定 |
| 研究假設 | 現有8機位、24乾區標籤、10組外口、Ø125＋25保溫、檢修預算與剖面試算 | 保留原版作比較，不冒充已量測或已選產品 |
| 實際條件 | 梁底、目標天花、可用管帶、產品含接口包絡、抽拉、完成淨孔、工作點、外牆條件及前後入口前提 | 依固定欄位輸入，可分批重算；數值／來源／日期一起保存 |

原ABC、目前3D及149份控制保持不變。工具只輸出獨立的「條件套入結果＋影響清單＋還缺什麼」，不讀取任意JSON路徑套patch，不自動改原房間／門窗／家具，不將假設升格為實測。

## 條件進來之後會自動做什麼

- 每處候選機位：含管口／消音的安裝包絡、四管橫排／雙層尺寸、板下至完成天花餘量、側抽長度、整機拆換淨口、最低／最高風量及同一目標風量下的靜壓比較。
- 每組前後外口：分別檢查OA／EA候選座標處的實牆高位區間能否放入實際外罩／孔高，以及提供的前／後外牆開孔條件。
- B兩層外口：後側條件不成立而前側已提供可行條件時，建議優先檢視前備案；前側未確認就維持待核，不假定一定可用。兩側都不成立就列需重排，不擅借共壁。
- B有無後巷：只影響搬轎備案的比較提示；不拿它推定後牆合法開孔，也不因後口不可用就取消後門。搬轎入口不自動採用。
- 每一輸入都有影響對照表，填入一欄就可知道哪幾項比較會重算；缺的欄位保留待資料，不當0或false。

「數值相容」僅表示所填條件下的算術比較吻合；輸入的source不是工具自行核實的專業簽證。真正三維路由、門窗完整框料、法規、風向污染、照護、家規及現場性能仍保留人工關卡，不會因一堆數值相容而變成整案approved。

## 資料填法

提供可編輯的JSON／CSV空表，兩種格式選一種作同一份輸入，不同時偷偷合併兩份衝突資料。可分批填值，其餘留空。每個欄位有固定ID與單位；向量順序見欄位說明，例如`[寬,深,高]`，不是公分。

JSON數值填在`value`；來源填`source`，量測／圖說日期填`date`（YYYY-MM-DD）。未知用`null`，不是0；布林值使用`true`／`false`。產品尺寸／曲線欄另填`model_ref`，需與該區`model`的型號／版次完全一致，避免換機型後沿用舊尺寸；非產品欄留`null`。CSV的向量用JSON格式，例如`[1600,1000,450]`；儲存UTF-8。

來源可以是圖號／頁碼／量測紀錄，不能只寫「應該可以」。非空值缺來源／日期、混機型版次、單位錯誤、重複ID、未知欄位、NaN、尺寸負數或過期基準會拒收，避免默默套錯版。風機曲線風量與目標風量不同時不借用靜壓數據；最小風量大於最大風量則明列資料矛盾。外牆開孔條件按樓層／側向各候選組分開，不將二樓條件套到三樓。

本工具依名義候選座標比較，不自動推算基地縮放或房間重排。資料若意味梁、牆、窗、管路必須換位，會列出需要修改的分支；等實際資料批次完成後，才進入正式合圖。

## 之後有資料才執行的指令

目前已輸出空白模板及規劃狀態，不需要先執行以下初始化。真的開始收資料時，在專案根目錄建立私人工作檔（目錄已被Git忽略）；既有檔不會被覆寫：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_abc_fresh_air_planning.py --init-input inputs/private/abc-fresh-air-conditions.json
```

若偏好CSV，初始化路徑改成`.csv`。填完部分資料即可只讀重算，預設只列摘要、不寫產物：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_abc_fresh_air_planning.py --inputs inputs/private/abc-fresh-air-conditions.json
```

需要保存可看圖表的本次結果時，另外指定**新的私人輸出目錄**，不覆寫已保存的結果：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_abc_fresh_air_planning.py --inputs inputs/private/abc-fresh-air-conditions.json --out inputs/private/abc-fresh-air-conditions-run01
```

基準或參數欄位結構改版時，舊輸入不會被自動搬到新圖；先保留舊檔、初始化新表，逐欄核對才轉入。未核定前不覆寫原JSON／HTML／3D，不背景啟動瀏覽器或整套場景驗收。

## 本批檔案與小檢查

`inputs/abc-fresh-air-planning.json`保存工作邊界；`house_design/abc_fresh_air_planning.py`定義固定欄位及比較；`scripts/export_abc_fresh_air_planning.py`提供模板與重算。輸出包含模板、條件字典／影響表、待核清單、JSON與manifest，來源雜湊需相符。

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_abc_fresh_air_planning.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_abc_fresh_air_planning.py
```

初期目標是「條件收到就能定位影響、重算比較、保留備案」，不是「填完表就自動取得施工核可」。

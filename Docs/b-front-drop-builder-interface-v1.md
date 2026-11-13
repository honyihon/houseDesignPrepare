# B前排水：建商回覆順序與條件回套

2026-11-11。[會議與欄位入口](../structured/coordination/b-front-drop-conditions-v1/index.html)。接[Claude第二輪](b-front-drop-claude-crosscheck-v2.md)，不新增格局或請屋主現在補實測。先把建商會需要回答的問題、依據及資料接口備齊，等同版條件回來再套用；原ABC／3D、家規、兩種搬轎版與149控制保留。

## 跟建商怎麼談

先問BFD-01合法前終端與完整前出路線，再問BFD-02騎樓上游及BFD-03梯底／落差；BFD-04成品包絡、BFD-05水力通氣及BFD-06清掃／防火同步核。BFD-07前後搬轎與施工分別演練，BFD-08最後收同範圍費用、工期及保固。每題已列建議窗口與鎖定工序，不代替各方議定日期、責任或合約。

如果只有「可以」兩字，仍請附同版圖號、標高基準、完整包絡及依據。沒有合法前終端時，不靠地下穿祭祀或換成G5消除共同缺口。只有完整具體方案仍衝突時，才回屋主討論代價；現在不固定落差或選產品。

## 已備28欄，允許分批回來

四組分開：局部落差10欄、上游間隔5欄、前終端7欄及平面外框6欄。公開[空白JSON](../structured/coordination/b-front-drop-conditions-v1/actual-data-template.json)全部null，[欄位說明](../structured/coordination/b-front-drop-conditions-v1/field-guide.csv)標明單位與口徑。非空資料需來源與共同圖面版次；有標高就需共同datum_id，平面值需coordinate_note說明對原研究框的關係。工具只檢查宣告資料格式，不能證明對方實際使用同一版；收資料後仍要人工對圖。

上方安裝、額外穩定餘量M、上凸、下凸與操作空間各自明填，不能空白當0，也不能將已納入實體包絡的尺寸再扣一次。局部50、1:50及5190下界不填入實際欄位。

本接口的落差算式不直接套前輪3461.6預算：前輪已含下方50，若把它當實體管底再扣操作空間會重複。本次先請專業提供**未扣操作空間的整盒實體底標高**，再扣下凸、操作、地坪與完成淨高要求。上方同樣從整盒最高實體包絡起算。缺一界就留未知，不替你選區間中點或500／600。

前終端只算宣告單一等坡段的起點／接點管內底、完整水平長與設計坡度；不從上方管頂猜地下管內底。不同坡段、井及跌水需另立完整接法，不能把全程折成一條直線。權利／接管documented只代表有文件待人工核查，沒有自動合法認證；not-available會提示暫停鎖定前濕區。

平面只比較原G4D[1280,4990,400,400]及既有平台／保護投影；不自動移井或判整盒真實構造。若實際基地框、梯核、井位或路線不同，須另立新研究版次，不能只把新座標塞到這份欄位套用。上游只核宣告的一點，不是整段已核。

## 日後收到資料再執行

把JSON另存`inputs/private/b-front-drop-conditions-001.json`，保留未知null及全部欄位，不改原研究hash；完成資料回來後由同版接口檢查。不讀取舊私人回覆、不寄出、不自動改正式需求或3D。

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_conditions.py \
  --conditions inputs/private/b-front-drop-conditions-001.json \
  --output inputs/private/b-front-drop-result-001
```

結果目錄必須全新，下一次用002；不覆寫先前輸入、結果或019交付快照。輸入及私人報告可能含現場資料，只留inputs/private，公開包不匯入。數值相容只標記局部算式相容，專業審查、屋主選擇與施工圖發行仍全部未知／未發行。即使四組全相容，也未驗水力、消防、宗教、完整搬運或法律權利，不能放行。

八題及欄位已接SEQ-04、BC-CMP-01與B-WET-001，不新增正式需求或比較案；新私人交付快照使用020，後續021。建商可先離線填CSV或看JSON，沒有要求先安裝工具或現在把28欄全部填完。

公開模板的小檢查：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_conditions.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_conditions.py --check
```

原第二輪來源／圖與私人001～003紀錄不改。沒有新外部AI、瀏覽器、WebGL或主場景工作；程式測試不是專業核可。

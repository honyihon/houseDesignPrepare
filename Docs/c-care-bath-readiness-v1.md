# C 套衛：坐姿可及與選品交付 v1

2026-10-22。依屋主「下一步」先釐清250mm偏側、能否只後移盆／門、18.5mm板試點餘量及完整商品交付條件。本輪不改任何HTML、SVG、3D、房間、家具、設備或需求，不新增畫面驗收任務；只新增座標研究、廠商填答來源與決策文件。

- [完整結論、比較表與足尺驗證計畫](../structured/candidates/c-care-bath-readiness/summary.md)
- [16項廠商尺寸填答CSV（Windows Excel用UTF-8 BOM）](../structured/candidates/c-care-bath-readiness/supplier-checklist.csv)
- [座標／限制／來源雜湊](../structured/candidates/c-care-bath-readiness/review.json)／[商品查核交付JSON](../structured/candidates/c-care-bath-readiness/product-checklist.json)
- [保留側盆版HTML](../structured/candidates/c-care-bath-layout.html)／[同源3D](../structured/candidates/c-care-bath-layout-3d.html)
- [廠商回覆來源檔，不會被生成器覆寫](../inputs/c-care-bath-products.json)

## 建議方向

先保留側盆版250mm偏側與現有門位，不再單純往後搬盆／門。下一份真正有用的資料是洗手台完整安裝剖面、門組整件包絡及安全足尺坐姿紀錄，不是再假定幾個人體或產品尺寸。

固定目前x=4665mm、盆前50mm及900mm討論矩形，偏側217.5mm才恰好不碰掀起扶手；偏側250mm保留32.5mm方向餘量。若比較額外30mm討論餘量，所需偏側247.5mm。這不是所有姿勢的最小偏側，更不證明250mm坐姿能自然操作龍頭。30mm非建築法規、施工公差或照護安全標準。

只把盆與門同量往後移、想維持同一盆前距離並置中時：

- 目前900mm靜止矩形要避開前方扶手，後移至少217.5mm。
- 兩片門含既有20mm止擋，最多只剩200mm後移預算。
- 兩條連續不等式沒有共同非負區間，差17.5mm；後移150mm仍撞前方配件，後移200mm亦仍碰撞且停門餘量歸零。
- 這只排除這一種局部策略，不證明整間浴室不可能；未重建門洞或驗全程動線，不會把這些試算作已完成配置。

板試點方面，原中心x=4850mm時，至門組56mm、至右扶手18.5mm；若僅試點左移20mm，兩側為36mm與38.5mm。純數學等分點x=4831.25mm時兩側各37.25mm；不是施工精度或真人救援結論。三個試點各重算全開／半開／全關路線，半開與關門仍被當下門片阻擋，沒有沿用全開結果。這些只是數值候選，原HTML／3D仍畫原試點，不能宣稱原圖18.5mm已改善。

## 選品交付的四類問題

1. 兩片後收疊門：實際全開至少保留原900mm目標；完整室內外凸、從洞口後緣到全開尾端／止擋／檢修的距離，以及全行程向洞口前端的外凸，都要有原廠圖。現討論130mm整組厚、710mm洞後延伸、30mm前凸不是實際商品。不得把名義1200mm或假設970mm當完成淨寬。
2. 洗手台：原600×450mm及850mm頂高只是模型，不是選定產品或照護合適高度。需含支架、龍頭操作點、膝部實際高寬深、給排水與隔熱的剖面；170mm可見薄盆不給檯下通行信用。若選不同尺寸，必須回套模型，不能只憑更小尺寸宣稱通過。
3. 折椅：需整件折起含鉸座／背板距完成面的最前外凸，以及放下完整外廓、全角度掃掠、承重與錨定。現模型折起向前57.5mm，不是45mm座板厚。
4. 右側扶手：需含底座、握持離牆及整件最內凸。現模型向內67.5mm不是35mm管徑；不能為套進試點而削減必要握持間隙，應取得商品圖再比試點或整合布局。

CSV的「廠商實際尺寸」與廠商／型號／文件欄全空，旁欄清楚分開模型值及方向預算。CSV供詢問與回傳，不會自動匯入。機器可讀回覆放在`inputs/c-care-bath-products.json`；四類共16尺寸，沒有商品或真人資料時保持null／unknown，不預設品牌、不自動採購。

文件紀錄需含專案相對路徑`document`、正確`sha256`、文件版本`revision`、`checked_by`及ISO日期`checked_at`。只接受`inputs/references/`、`assets/references/`或`Docs/`內的文件，不讀外部或私人設定路徑。單檔超過20MB不自動雜湊，列為待人工查核，不提高資源上限。

有填尺寸卻缺身份、文件、版本、查核人、日期，或檔案雜湊不符時，該數字不會取得尺寸信用。即使文件紀錄完整且單項尺寸在預算內，狀態也只是`inside-this-scalar-budget-not-approved`，必須完整回套模型與專業審核，不是整個產品、臨床使用或施工通過。文件可讀／雜湊一致只證明檔案一致，不自動證明文件內容或廠商數值真實。

## 足尺驗證前先保留未知

先記錄實際椅型、含輪／腳踏板外廓、坐姿高度與使用者／照護需求，再依摘要的安全足尺計畫，由本人在適當陪同及職能治療／照護評估下確認自然操作、膝腳配管與協助位置。未取得資料前，不引用平均人體就判定可及，不做冒險抬抱／轉位或倒地救援試驗。

盆前與馬桶側移仍須分時，完整轉位仍借淋浴濕地；原公共直達照服偏好仍有缺口。床、衣櫃、窗、830mm戶外通風帶、前公衛、IDF、樓梯、上層與2F唯一既有洗衣機完全保留。風水、門組外解鎖／救援、結構、消防、排水防水與施工仍未知。

## 驗證與資源限制

生成器先查側盆父版全部來源雜湊、HTML／3D資料一致性及模型補回後的自雜湊，再鎖定完整側盆平面雜湊`59aa1ccee2455b9d3ab0f7c0360d2f3ec2bea992576a91457884c7b71ab57640`。若來源或座標改變，拒絕沿用這份研究；不是重新生成父版來消除不一致。

36項小範圍Python測試與Ruff通過。包括連續後移界限、全開與關門反例、16個空值、缺來源數字不能當已知、文件版本／日期／雜湊、私人路徑拒收、尺寸邊界與只寫四個新輸出檔。測試中的假廠商文件只在臨時目錄驗證拒收邏輯，從未寫入正式選品來源，也不構成真實商品資料。

只做檔案與座標運算，不啟動瀏覽器、WebGL、3D場景runtime或背景工作；本次不需屋主再跑Windows驗收。父版既有QA仍僅對應原來源，不能擴張成這些數值候選或照護核可。

WSL每個命令最多20秒、依序執行：

```bash
cd /root/workspace/houseDesignPrepare
timeout 20s .venv/bin/python -m ruff check house_design/c_care_bath_readiness.py scripts/export_c_care_bath_readiness.py tests/test_c_care_bath_readiness.py
timeout 20s .venv/bin/python scripts/export_c_care_bath_readiness.py
timeout 20s .venv/bin/python -m pytest -q tests/test_c_care_bath_readiness.py
timeout 20s .venv/bin/python scripts/export_c_care_bath_readiness.py --check
```

逾時或資源錯誤就停止該嘗試，不自動重跑、安裝、提高權限或清掉其他程序。本輪未commit／push，也未修改任何既有配置、驗收程式或父版來源。

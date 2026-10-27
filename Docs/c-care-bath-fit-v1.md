# C 套衛：完成面、公差與選品檢核 v1

2026-10-21啟動、2026-10-22完成。依屋主「下一步」，核對上一輪完成展示驗收的套衛，不直接採用配置、不新增另一套3D、不縮設備、不改原需求。

- [檢核頁：七組壓力情境與12項選品交付](../structured/candidates/c-care-bath-fit.html)
- [同一原配置3D](../structured/candidates/c-care-bath-3d.html?scheme=c-bath-refined&use=transfer#mode=tour&building=C&floor=floor-1&room=C%3Afloor-1%3Aelder-bath&focus=room&view=plan)
- [原始座標、來源雜湊與計算](../structured/candidates/c-care-bath-fit/review.json)
- [未選產品交付清單](../structured/candidates/c-care-bath-fit/product-checklist.json)

## 結論：先解門組，再決定洗手台／折椅與隔間

名義2400×3000mm、假設扣每面115mm後2170×2770mm，並未自動通過施工。上一版只列10／15／8.5mm三個緊餘量，本輪還找出兩個**零餘量**：

| 固定座標中的位置 | 原餘量 | 需要處理的內容 |
| --- | ---: | --- |
| 入口900mm試線到洗手台 | 10mm | 盆緣、前牆完成面及定位誤差。 |
| 洗手台前最後到位點 | 0mm | 矩形恰貼盆緣；可以重排試線，但不能假稱檯下可鑽入。 |
| 馬桶側移預留到洗手台右緣 | 15mm | 左完成面、盆寬與支架／外凸物。 |
| 600×1800剛性示意板轉向到收起折椅 | 8.5mm | 含鉸座的折起厚度；不是擔架或真人救援證明。 |
| 開啟1260mm門片尾端到假設後完成面 | 0mm | 未另外留止擋／檢修，不能當作已選好的可施工門組。 |

拉門名義1200mm扣雙側115mm後是970mm討論淨寬，超過原900mm目標70mm；置中900mm矩形到每側門框僅35mm。這些仍不是實際商品完成淨寬。

建議順序：

1. 先拿門組的全開淨寬、停放長度／厚度、把手、軌道、止擋與外解鎖／門外拆卸圖。若單片仍不能成立，優先研究「兩片連動、共同向後收疊」的真實產品；**不是普通兩扇向兩側對開**，也不能先宣稱已放得下。增加的疊片厚度可能侵入轉位空間，須回套完整動線。
2. 洗手台原600×450mm尺寸保留，先確認含盆緣、龍頭、熱管與壁掛支架的外廓。兩個方向都吃緊，不能只把入口向後挪一點就宣稱解決；它還牽動門洞及門片停放。
3. 折椅要提供「含鉸座的折起包絡」，扶手要提供「含底座、握持與全角度掃掠」的安裝圖。現有模型的座板與管身不是完整市售商品。
4. 商品及完成面資料回齊後，才微調門位／隔間。先保原外框、後窗、830mm戶外帶、原床及上層；若必須借臥室，須獨立列出照護／窗／床位代價，不在這張檢核表偷改。

## 七組情境的意義

原座標零增量、完成面／門框額外5mm、額外10mm、商品局部額外10mm、相對定位不利5mm、門後止擋額外20mm，以及一組不利組合。

這些是**假設的方向性餘量預算**，不是選品尺寸、法定容差、發生機率或已核施工標準。115mm已在原圖扣除；本輪只算額外侵入，不再重複扣115mm。每個剩餘值都列公式係數及參數，不執行求解器或自動重排。

- 負數：原固定試線／預留沒有承受該增量，不代表整間浴室永遠無解。
- 零：恰好貼齊，沒有額外餘量；接觸可否接受仍須商品及照護評估。
- 正數：只是此方向預算尚餘，不是全配置通過。

例如完成面／門框額外10mm，入口餘量降為0mm、剛性板轉向餘量為−1.5mm，門片後停放為−10mm；不能沿用原座標的「無衝突」當成實際完工也可用。

檢核頁另列「若不利組合後想多留30mm」的額外名義淨距。30mm只供討論，未寫入原需求或宣稱符合照護標準；數字不是牆體移動量，不可直接加總成房間擴大量。

## 缺資料也能先完成的部分

建立12項交付清單：馬桶、洗手台、開放淋浴、套衛拉門，以及原8項工程配件。品牌型號、實際尺寸圖、安裝圖、查核人／日期與文件雜湊皆保持未知，不會因填入一般尺寸而變成verified。

另須取得完整牆體與完成面剖面、產品安裝條件、防水／坡度／排水設計、扶手與折椅補強及照護側別評估。外窗及排風需求、公共直達照服偏好、濕區分時操作與原關門／折椅放下／扶手放下反例全部保留。

## 驗證與資源分流

父版屋主提供的 `house-c-care-bath-cli-L0vesu` 為展示v2的passed；上一輪已核561項、327份來源、15筆手機證據及12張截圖。結果SHA256為 `a9a0aa8db0d7e496ed25ef6da71c3b10280517333e91aedcdcfe37e4023fc393`。這不等於新檢核頁畫面已驗收，更不是施工或照護核可。

本輪只讀父版report／viewer，重建其模型載荷雜湊並核對來源，從共同座標算餘量。不重新產生父版、ABC、原HTML／3D或SVG，保留既有畫面證據的對應關係。

輕量命令各自最多20秒，依序執行；逾時即停，不自動重試：

```bash
cd /root/workspace/houseDesignPrepare
timeout 20s .venv/bin/python -m ruff check house_design/c_care_bath_fit.py scripts/export_c_care_bath_fit.py tests/test_c_care_bath_fit.py
timeout 20s .venv/bin/python scripts/export_c_care_bath_fit.py
timeout 20s .venv/bin/python scripts/export_c_care_bath_fit.py --check
timeout 20s .venv/bin/python -m pytest -q tests/test_c_care_bath_fit.py
timeout 20s node scripts/check_c_care_bath_playwright.cjs --preflight
```

修正新匯出腳本直接執行時未找到本機套件的問題；路徑以腳本所在專案為準，不依賴呼叫者目錄、不安裝套件，並以隔離模式／其他工作目錄作回歸測試。`--check`只讀來源及計算，不寫入檔案或開瀏覽器。

27項小範圍測試涵蓋數學、零餘量、增量單調性、資料不足／偽造通過拒絕、來源一致、直接命令可用及靜態HTML數字／連結／產物一致。Ruff及父版preflight亦通過；這些不是新頁面瀏覽器驗收。前端測試技能用於警語、同源連結及可橫向捲動表格；Browser插件未提供，依屋主要求未啟動瀏覽器或WebGL。

如需看新表，Windows自行開啟即可，這輪不必重跑整套3D：

```powershell
Start-Process '\\wsl.localhost\Ubuntu\root\workspace\houseDesignPrepare\structured\candidates\c-care-bath-fit.html'
```

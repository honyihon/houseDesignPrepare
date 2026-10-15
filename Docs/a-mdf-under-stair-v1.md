# A 棟 MDF：梯下優先候選／側壁龕備援

2026-10-12。依屋主同意優先研究梯下，保留原18U落地機櫃；**尚未正式搬入，不認列原位置已釋放**。B／C配置、本棟騎樓、孝親房與樓上樓梯軸線保留。

## 先看這裡

- [A 棟 HTML](../AbuildingView.html)：1F共用家具圖下方展開「MDF：梯下優先候選／側壁龕備援」，可勾選候選虛框。
- [3D 梯下比較](../structured/candidates/model3d.html#mode=tour&building=A&floor=floor-1&room=A:floor-1:stair-door&view=front&focus=room&mdf=study)：青色機櫃候選；橘色維修與原位再利用虛框。關閉比較即可回到備援，不新增第二台機櫃。
- [同源比較平面](../structured/candidates/furniture-plans/A_floor-1_mdf-study.svg)／[梯下敏感度剖面](../structured/candidates/furniture-plans/A_floor-1_mdf-section.svg)：不是結構剖面，不因線條畫得下就代表可施工。

## 為什麼沒有直接搬入

原HTML與需求均希望利用梯下，前版側壁龕只是避免把未知淨高、散熱與消防當成已通過。本輪把梯下優先候選具體化，也補上前版沒有完整檢查的左右維修預留。

| 項目 | 本輪比較值 | 狀態 |
| --- | --- | --- |
| 原18U落地機櫃 | 寬600 × 深600 × 高1000mm | 一般代表尺寸，非實物／廠商確認；不縮小、不改壁掛 |
| 原維修要求 | 前800／後600／左右各300mm | 保留，完整平面外廓1200 × 2000mm |
| 上折回程梯 | 名義梯寬900mm | 不代表完成面、扶手或消防核可 |
| 梯下候選本體 | x1330–1930、y6900–7500mm | 位於上折回程梯較高段，非低段梯下 |
| 完整維修範圍 | x1030–2230、y6100–8100mm | **比梯段寬300mm，並跨出梯間70mm**；兩側淨高與地面維修通路未證明 |
| 新增家具／釋放面積 | 0件／未知 | 不增加庫存、不把備援面積計成已增加的可用空間 |

候選只沿同源級高／級深計算縱向敏感度：機櫃區最低踏步頂約3.00m；完整前後維修長度覆蓋的上折梯最低踏步頂約2.50m。另假設扣200／300mm時，本體區約2.80／2.70m，縱向維修區約2.30／2.20m。**扣除量不是結構設計，這些值不涵蓋左右300mm的完整站立範圍，也不證明梁下、排風或避難合格。** 2m站立、頂部20cm只是討論預留，不是引用法規或原廠值。

沒有切斜板、增開通往抬高梯段的側門、擴大梯井、減少客餐廳／孝親房或借用騎樓。未核開口、換機路線及結構分隔不能靠3D自動剖視假裝已存在。

## 備援與原位再利用

備援原1.10 × 2.18m不能完整留左右各300mm，本輪調成**1.36 × 2.18m，2.9648m²**；機櫃中心x680、y11110mm。相較前版2.398m²，先多保留0.5668m²修正備援，不宣稱省下這塊。

後段公共乾區改2.16 × 2.06m，150cm轉位仍在原絕對位置x1940–3440、y10080–11580mm；廚房門中心由x1750微調到x1900mm，避開新分界。孝親房3.60 × 3.77m、床／衣櫃、120cm照護通道、公衛及工作陽台不縮小，夜間如廁不穿MDF或梯段。

若梯下之後成立，再撤銷備援，沿原側牆研究40cm深、160cm長、120cm高的乾式家務櫃，前方暫留60cm操作帶；其餘併公共乾區。這是**另一個時間狀態的候選，不是與現機櫃一起安裝**，不列為已擺家具、已達成收納或新增房間。上層三件待排櫃也沒有因一樓畫出虛框就被取消。

## 建築師與弱電技師要核對

1. 結構剖面：實際梁、梯斜板、完成面、兩側維修地面與樓梯淨高；禁止為機櫃切梁／斜板。名義90cm是否能作最終樓梯仍待核。
2. 消防／避難：梯間能否設設備、所需分隔與耐燃、UPS電池及消防配置；維修不得占連續通行，不能用門片或剖視替代核准。
3. 設備：實物18U外廓、可拆後板／側板、線纜彎曲、完整換機與UPS搬運。不能自動把原前後維修要求改成前修型；若需變更須另選原廠支援的產品並確認。
4. 散熱／濕氣：盤點路由、交換、PoE、NAS／NVR、UPS負載與發熱，計算通風，溫控、吸排風、噪音及凝結水；不能為降噪封死櫃。除濕設備的電源與排水不得導入機櫃。
5. 水與電：浴廁／廚房管線不得從機櫃上方漏水風險區穿過；專用迴路、UPS、SPD、接地、跨棟光纖與線路權利另核。

這些欄位都保留`unknown`、`evidence: null`。資料到齊後需更新方案版本與專業證據，不是把目前的未知欄位改成passed就直接採用。

## 資料與驗證

來源在`inputs/a-mdf-under-stair.json`、`inputs/concept-layout-review.json`、`inputs/furniture-layout.json`；剖面與候選外廓從實際共用梯段／機櫃資料推算，由`model3d_mdf.py`輸出，沒有另一套手填圖面。

```bash
.venv/bin/python scripts/export_model_3d.py
.venv/bin/python scripts/export_c1f_options.py
.venv/bin/python scripts/export_arcade_capacity.py
node scripts/check_windows_playwright.cjs --preflight
```

主案仍12 floors／112 rooms／127 items，另有3件樓上收納待排。MDF虛框不計入家具統計，原有C公衛與舊骨架容量比較也不採用此候選。

本轮最終本地驗證：514項Python回歸（含21項MDF資料測試）、7個JS測試檔、Ruff、115舊來源加4份MDF來源共119份預檢、五個viewer內嵌script語法及文件連結檢查通過。Three.js場景數學測試以1080×900、390×790及844×336驗MDF開關、分享重載、外觀返回、跨層關閉、機櫃本體／維修外廓、八個非安裝比較框與不變的127件家具，不是瀏覽器像素證據。HTTP e2e另增兩項MDF案例，62項可列出，但未執行成功。

| 渲染驗收項目 | 本輪狀態 |
| --- | --- |
| Browser插件 | 未提供，沿用已安裝Playwright |
| 實際頁面識別／非空白／錯誤遮罩 | 尚未取得新版瀏覽器證據 |
| 實際console／截圖／互動 | 尚未取得新版瀏覽器證據 |
| Playwright直接開本地file URL | Chromium載入頁面前因`sandbox_host_linux.cc:41 / Operation not permitted (1)`結束；無新版截圖 |
| 靜態SVG剖面 | 已用本地中文字型替換做局部圖面檢視；不是瀏覽器或結構驗收 |

### MDF版 Windows 部分驗收與控制面板修正

屋主回傳`house-design-cli-tLJ0Td`，已直接核對原始`result.json`：Windows Edge、主案12／112／127，2334項已記錄檢查通過，119份來源SHA-256與修正前當時檔案一致，命名session已關閉；**整體結果仍為failed**。中斷前已走完ABC桌機逐層比對與A手機MDF特寫，但後續C手機、外觀與比較案流程尚未完成。36張截圖含`failure.png`，本次原尺寸查看4張：失敗畫面、MDF桌機／手機特寫及HTML剖面；不是36張全部目視驗收。訊息只有4次既有Three.js棄用warning，不能據此宣稱後段console也已通過。

失敗不是C棟房間被刪除：同一viewer只改hash時，A手機MDF特寫的收合控制狀態會保留。腳本直接點`C:floor-1:garage`的側欄按鈕，按鈕存在卻因收合而不可見，15秒後逾時。已改成先確認C棟1F與MDF比較關閉，再明確展開控制並等canvas完成尺寸調整，才點前緣通行區；不使用強制點擊、不延長逾時，也不改ABC房屋／家具配置。

回歸測試涵蓋「初始收合／已展開、延遲resize、移除展開步驟即失敗」，手機HTTP e2e也補同頁hash切C的情境。新版仍需屋主重跑同一Windows命令，不能把此次部分通過當成全流程passed。原始報告SHA-256：`5df0a6ec2357c227e14e6719174c556f5c5403f231539f377f1893019e9df653`；結果／截圖仍在Windows TEMP，未正式封存。

修正後152項Windows CLI單元／契約測試、檔案預檢、Ruff及空白檢查通過；62項HTTP e2e可列出，但實際執行手機MDF轉C案例時，WSL本地伺服器在socket建立即因`PermissionError: [Errno 1] Operation not permitted`結束，沒有新的瀏覽器互動證據。119份受驗收來源只有`scripts/check_windows_playwright.cjs`與此次報告不同；HTML、3D、SVG、房間與家具資料均未改動。

`house-design-cli-T1uj2e` 的5133項／115份來源／75張截圖，是本MDF改動前的Windows證據，不能替新版背書。新版需重跑HTML開關、剖面載入、3D開關／重載／返回及手機收合，並目視新截圖；自動通過仍不是專業或施工驗收。

```powershell
node '\\wsl.localhost\Ubuntu\root\workspace\houseDesignPrepare\scripts\check_windows_playwright.cjs'
```

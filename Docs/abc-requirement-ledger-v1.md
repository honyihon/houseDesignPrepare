# ABC 全量需求對帳 v1

2026-10-20補充：本頁及`structured/reconciliation/`保留舊六案歷史對帳。最新B後右公衛／上層改善、C已接受廚房／單機家務及A套衛取捨，請改看[目前討論基準](current-design-basis-v1.md)與其[112列同源需求對帳](../structured/candidates/current-design-basis/requirement-ledger.json)。兩者都是未採用的分案對帳，不把新舊面積或驗收結果混用。

2026-10-16，AG-009。已將目前 66 項原面積需求逐項對應到 ABC 主案、B32 後門／前門兩案及 C 整合三案；**對帳完成不代表需求已確認、方案採用或功能符合**。不改格局、家具、原需求、尺寸與既有交付封存。

## 先看哪裡

- [完整可讀對帳表](../structured/reconciliation/requirement-ledger.md)：逐需求的處置、討論面積、原下限／目標與未解內容。
- [機器可讀數據](../structured/reconciliation/requirement-ledger.json)：房間 id／幾何、來源雜湊、敏感度、共用對象及來源新鮮度。
- [人工映射與處置來源](../inputs/requirement-dispositions.json)：明確綁定需求 id，不靠房名相似猜測。不是新的需求決定檔；權威仍是 `inputs/requirements.json`。

A24／B22／C20，共66項，六案分開共170列（66＋22＋22＋20＋20＋20），含RF。ABC停車與C一樓獨立公衛另列補充，沒有把不在66項面積清單的既有需求丟掉。B32原部分面積表各7列、C整合原部分面積表各11列，現均完整逐需求列出；未在舊面積表出現不等於刪需求。

## 目前最需要處理的缺口

| 範圍 | 對帳結果 | 建議下一步（尚非採用） |
| --- | --- | --- |
| A2 主臥衛浴 | 圖上雖有 `master-bath` 名稱，但其需求綁定是公用衛浴 `A.floor-2.bath2`，原獨立主臥套衛未容納。分散衣櫃也不是另一間獨立更衣室。 | 保留套衛原目標，另比較公共衛浴是否仍可保留的濕區小改；不直接把同一間公衛改名充數。 |
| A1 面積餘量 | 80mm內縮假設下玄關3.6400m²／下限3.6，客餐18.0026m²／下限18；內縮100mm即分別3.4888／17.6613，低於原下限。 | 等完成面／柱位後重核照護通路、家具與入口，不以增加櫃體占走道或縮家具解決。 |
| ABC舊B主案 | 1F衛浴3.3456m²／下限4.5且無淋浴，2F主臥與3FKTV各10.4228m²／下限14；仍有背梯及整廳上方客房家規衝突。 | 依屋主先前方向以B32後門預案繼續改善、保留獨立前門備案；舊B只作比較，不混用較大的房間或設備。 |
| B32未容納功能 | IDF、獨立1F工作陽台、3F工作陽台、RF水塔／VF800及熱泵未容納；茶水／KTV另案研究。原一車位亦未容納。 | 先研究後段家務／機電的獨立進出、排水／散熱及維修，不再用已與武轎重疊的左側1000mm通道。不假裝洗衣已移RF，也不假設A／C可接KTV。 |
| B32祭祀與主臥餘量 | 神明堂整體聯集30.2104m²，但扣本案側緣暫留後，後門案21.4384、前門案19.0992m²；主臥80mm時20.0312m²，增加內縮即低於20m²原目標。 | 整廳面積不是專用祭拜人數容量，兩門案分別作尖峰活動與搬運分時演練；牆柱及設備不能靠薄牆假設保證。扣通道值也不是直接的法規面積判定。 |
| C1廚房／工作陽台 | 舊主案廚房5.4656m²低於6m²下限；整合案廚房改善，但兩版後側僅1.5008m²，低於原工作陽台4m²下限。 | 保留原一樓家務目標，先做真實工作流程／設備操作與獨立出入比較，不能以2F洗衣或RF平台頂替未決需求。 |
| C2客房／起居 | 整合三案客房80mm時9.3456m²低於12m²目標，115mm時8.9179m²低於9m²下限；改前客房也偏離原後段偏好。3.6m案起居18.2560m²低於22m²目標。 | 優先保候選外窗與照護，但原目標不刪，先比較客房／起居實際牆柱餘量，再提出取捨讓屋主決定。 |
| C公衛／運動 | 主案缺訪客不穿孝親房的獨立公衛；整合案已有前高窗公衛提案，但排濕／救援未核。運動比較只避器材與討論外廓投影，不保證結構傳音或原廠安全距離。 | 公衛繼續核獨立排氣補氣、防水與救援；外窗不保證不發黴。運動另需產品手冊／梁板／隔振證據，不用面積夠代替使用核定。 |

目前沒有因這份對帳而自動採用新案、淘汰原需求或要求屋主立即盲選。下一段可按A套衛、B32家務機電、C一樓工作能力分別做不碰撞幾何比較；涉及實際用途／面積犧牲時，再附數字與代價討論。

後續已有獨立[B32家務／機電研究](b32-service-study-v1.md)：六個分區比較、七張SVG，原B32與本對帳快照未變更；不得將研究中的設備／面積當原案已容納。緊湊通道案的儲藏約9.64m²低於原10.5m²目標，需要屋主確認是否沿此方向細排；IDF一樓與屋頂隔振仍未解。

## 計算與防漏規則

- 明確逐id映射，將「有對應配置」「部分配置」「併入共用組」「未容納」「另案研究」「缺映射」分開，全部保留功能／專業接受未知。
- `floor-rf` 明確對應概念圖 `floor-4`，不以編號不同誤稱缺屋頂。
- 開放客餐、L形衛浴、水塔／加壓等多格取正交幾何聯集，內部開放格線不重複內縮、重疊不重複加面積。80／100／115mm皆為討論假設，不是實測牆厚、完成面／法定淨面積。
- 併入主臥的衣櫃、梯廳壁龕、共用玄關不給整塊區域獨立面積信用，列出共用對象；所有需求列都禁止跨列面積加總。
- 不借另一案／棟／樓層的房間，並核對既有部分面積表的房間及數值。失效id、錯層／錯棟、原映射與snapshot的requirement_id衝突，不能保留已算的數字當有效面積。
- 新需求沒映射仍列為待補；已移除需求的舊映射列為孤兒；原需求內容雜湊改變則整批映射要求複核，不自動確認需求或繞過decision log。
- 僅讀 strict JSON data assignment，不執行layout.js或匯入產圖器。比較案內嵌source_hashes逐筆對照當前公開檔案；不開私人／專案外來源或指向它們的symlink。

本次B32／C比較案內嵌來源雜湊與當前檔相符；ABC主案只有共用配置快照、沒有同樣完整的內嵌生成依賴，所以標記 `snapshot-only-not-regenerated`，不冒稱已重算整個生成器。來源相符不等於瀏覽器畫面或專業驗收通過。

## 重跑方式與測試證據

輕量檔案對帳，不啟動browser／WebGL／完整runtime／pipeline：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m house_design predesign requirement-ledger
```

只寫 `structured/reconciliation/requirement-ledger.json`／`.md`。可用 `--root <專案目錄>` 及 `--output-root <報告目錄>` 明確指定；不改既有HTML、SVG、3D或交付包。表中有連到各案的3D，但本輪沒有啟動畫面驗收，不套用舊passed。

本輪 **90項針對性測試通過（1.72秒）**：新增48項對帳測試、41項既有incremental pipeline護欄、1項第二批CLI相容測試；三個Python檔案Ruff通過。不是全套pytest。

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest \
  -q -p no:cacheprovider tests/test_requirement_reconciliation.py \
  tests/test_drawing_evidence_planning.py::test_cli_exposes_explicit_revision_and_inventory_without_launching_work \
  tests/test_incremental_pipeline.py --tb=short

timeout 20s .venv/bin/ruff check --no-cache \
  house_design/requirement_reconciliation.py house_design/cli.py tests/test_requirement_reconciliation.py
```

測試覆蓋66項／RF完整性、舊B與B32隔離、C不同樓高差異、共同格位不加總、新增／刪除需求、面積表不一致、壞檔／來源過期、私人／外部／symlink阻擋及只輸出新報告。讀取與報告輸出前後12個既有資料／圖面檔及R000／R001兩個manifest雜湊均相同。

本輪來源SHA-256（CLI的第二批舊雜湊保留為當時紀錄，不回寫）：

```text
4a9e029ca52851cf27f9e82a1961e50a8d86524ee071c45c16447bfe624bd718  house_design/cli.py
3f6a407ca21e7eeb8a691e01030a6d3ffe3127fc373dc34c01ea4869a55e9fdf  house_design/requirement_reconciliation.py
e36e04e1ef91babaee6337be4b7cf37134ba8fac8d9b9750aa1d17c16fd90ac4  inputs/requirement-dispositions.json
65729e4028b1e1352c42de5ce1cbaf1d525d335a900ba15de398126277c67920  tests/test_requirement_reconciliation.py
```

生成報告的內容hash為 `e7f21828a8ab883deeacc3e26679271694ce2ab9477043c429e7cf4d761105f1`。這是同源資料對帳，不是建築／結構／風水／照護／搬運簽證。AG-004開窗意圖、AG-012來源可攜性及其他說明增強仍另列待辦。

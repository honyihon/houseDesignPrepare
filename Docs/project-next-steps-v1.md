# ABC下一階段：決策與條件總表

2026-11-06。屋主要求「還能做什麼／繼續」後，先把分散的三棟議題整理為一張可追蹤總表，不再新增未採用格局。**現在只做預先規劃，等實際資料再統一套用；沒有要求現在補實測，也沒有新增強迫選擇題。**

[開啟總表](../structured/planning/project-next-steps/index.html)／[Markdown閱讀版](../structured/planning/project-next-steps/project-next-steps.md)／[討論CSV](../structured/planning/project-next-steps/work-items.csv)。

唯一輸入是既有`inputs/project-status.json`的work_items，沿原ID增補followup。共14議題；原11個維護／設計題保留，另將原先混在大項目的B兩衛面積／外窗、C整棟與照護續版、C客房／景觀冷媒單列，不是新增三項屋主需求。生成器只讀`inputs/requirements.json`與`inputs/planning-register.json`對應ID／原狀態，不確認、淘汰或寫入正式清單。

## 最值得先保留的方向

| 棟別／主題 | 目前建議 | 要等什麼，屆時才討論 |
| --- | --- | --- |
| A一樓照護 | 兩門1200名義洞口小改獨立留比較；不直接採用 | 真實門組、完成牆／梁與救援，才評公衛轉乾區0.87024㎡代價 |
| A二樓套衛 | 暫保公衛、主臥及收納，不直接採用約12.13㎡主臥的小套衛案 | 同版完整面積／排水後，才決定套衛與臥室／收納順位 |
| B祭祀及搬轎 | 神桌朝街／乾保護室不放寬；後門預設與前門備案分開留 | 實物含桿／人員搬運、後巷權利及完成門組，不把窄通道算通過 |
| B上層浴廁 | 保留原面積與外窗偏好；現位獨排與後窗重排都留代價 | 實際牆柱管井容量不足時，再請屋主選完整替代；未接受無窗／縮面積 |
| C照護 | 可關前室／樓梯保留，新增完整1F接側盆／兩片門／入口的獨立靜態比較，主3D不改 | 用真實商品與完成面重核連續照護／救援；濕地分時、偏側到盆與緊餘量仍保留 |
| C冷氣／景觀 | 客房單機服務優先比較；保留景觀、洗曬與唯一2F洗衣機 | 負荷／實機／管長／樹冠土重到齊，才定台數與路線 |
| 全棟基地／機電 | 梁板、合法外口、排水終端及屋頂維修先備資料接口 | 真實32地坪含騎樓／界址／可建量未到，不自動壓縮格局或視為合法車位 |

上表只整理既有研究建議，不宣稱新的商品、市場價格、法規或家規核可。老專題文件內的較早B說法不得蓋過新家規與第三輪研究；各列來源只支援該項研究，不代表整份文件變成當前主案。

## 表格怎樣避免變成第二份矛盾清單

- 每列沿用work_item ID，列現在可先做、資料來後再做、必要時的取捨、依賴議題及來源。
- 正式需求與情境只引用ID／原狀態；沒有把candidate或unknown改成confirmed／verified。屋主新答覆仍以專題證據為據，日後正式狀態改動另走原決策流程。
- 對應範圍只是本階段優先議題；未列入總表的原需求／情境ID完整留在review.json，沒有刪除、降級或宣稱已解決，不輸出虛假的完成率。
- 原圖、B前後兩版及149控制不改；新輸出只有HTML／Markdown／CSV／JSON與manifest，沒有新場景。
- 新風184欄仍是唯一已完成的數值條件接口；本總表是跨專業交接地圖，不宣稱所有建築、照護或風水條件都能一鍵自動套圖。

## 日後更新與安全檢查

只維護`inputs/project-status.json`的followup，重產這個小表即可。若正式需求／情境ID被刪改、依賴循環、跨棟錯引、來源遺失或受保護圖面變更，工具拒絕默默套用。

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_project_next_steps.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_project_next_steps.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_project_next_steps.py
```

不背景啟動瀏覽器／WebGL、全套pytest、完整3D生成或外部AI。獨立新表未取得瀏覽器目視與任何專業核可；目前無實際工程值，不沿用歷史passed。

本輪小範圍測試與來源綁定見[靜態檢查紀錄](../inputs/references/project-next-steps-static-review-20261106.json)。前輪重整紀錄只適用當時來源，這輪新增工作索引與總表另存證據，不修改舊紀錄的預期hash。

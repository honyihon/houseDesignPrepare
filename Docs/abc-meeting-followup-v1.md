# ABC會後：回覆、費用與變更怎麼追

2026-11-11。[紀錄接口](../structured/planning/abc-meeting-followup/index.html)接既有[六段聯席議程](abc-coordination-meeting-v1.md)，不新增問題清單。本輪尚未開會、未收到實際回覆，只準備空白紀錄與明確指定私人資料後的整理方式。

2026-11-13洗衣方向更新：當前空白模板改用`inputs/abc-meeting-followup-laundry-v1.json`第2版，明列原config來源／hash、最新屋主答覆與同一22題的新文字；原`inputs/abc-meeting-followup.json`保持原樣。仍沿六列／同一問題ID，沒有導入或改寫舊私人回覆。舊紀錄的config_hash不會被新模板默認接受；原紀錄須先留存，再人工按圖號與受影響問題核對後另建新版，不能改hash硬套或把原passed轉給新版。本輪交付044，001～043快照均保留。

## 每一段分開記五種狀態

六列固定沿COORD-01～06及原BC問題。資料回覆分尚未收到、部分收到、收到待核及回報衝突；即使回覆說可以，也須記來源、收到日與圖面版次，不能直接叫相容、採用或可施工。

費用／工期、屋主選擇、專業文件與圖面發行各自記錄。回報有費用文件不等於已接受價格；屋主選擇不能代替專業核對；有專業文件或發行紀錄也只記回報存在，仍需人工核內容、權責與有效範圍。實際專業核可及工具施工放行始終未知／否，不由表格自動核定。

有待補項就記哪些資料；已議定才填窗口與期限。空白期限不當逾期，不自動寄信／催辦，也不因一段缺件封鎖整個專案。收到資料、取捨與費用可在會前或會後分批整理；meeting_date只在確有會議紀錄時填，不從收到回覆推定開過會。

## 議程後沿原五步走

先核同版與完整範圍，再分可續算、待資料及有矛盾；需要時回套完整方案及成本；屋主選擇與專業核對分開，最後由有權責方按正式程序發行。六段聯席行動CSV加上這些紀錄欄，不把原builder-replies、a-interface、change-log或drawing-register換成新正式流程。

有費用、工期或保固影響，仍引用原同範圍估價／變更紀錄；B兩搬轎版與G4D／前濕區重排／G5互斥方向不能相加。A的建商／設計師交接、C照護／商品與各法規、家規及搬運證據分開，不因某段文件齊就將其他項目關閉。

## 日後使用明確的一份私人紀錄

將[空白JSON](../structured/planning/abc-meeting-followup/record-template.json)另存`inputs/private/abc-followup-records-001.json`，沿原六列填；未知維持null／空白，不改來源hash、棟別或問題ID。非空的回覆需來源、日期與同版標示；已記錄的屋主選擇、專業文件和圖面發行各有獨立範圍／來源及日期欄。不自動驗證文件是否真的核可，存在性和內容仍要人工核。

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_abc_meeting_followup.py \
  --records inputs/private/abc-followup-records-001.json \
  --output inputs/private/abc-followup-summary-001
```

輸出目錄必須全新，下一次用002；不搜尋、合併或覆寫舊私人回覆，不將結果自動放回公開包。私人資料可能有姓名、價格或現場文件，均留inputs/private。已收到、已選擇或有發行紀錄不會改原正式66項candidate、105項unknown、149控制或主3D。

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_abc_meeting_followup.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_abc_meeting_followup.py --check
```

交付包只帶空白模板，既有聯席頁增會後段落及同一六列CSV的紀錄欄；沒有新格局、產品或採用。新快照023，022及更早保留，下次024。不啟動外部AI、瀏覽器、WebGL或全套測試；靜態檢查不當專業核可。

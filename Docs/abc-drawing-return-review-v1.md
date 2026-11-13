# ABC建商回圖與變更核對

2026-11-11。供日後收到建商／建築師圖面時使用；目前沒有接收或匯入新的正式圖面。先開[回圖核對入口](../structured/planning/design-discussion-basis/source-index.html#drawing-return)，沿原有[圖面目錄](../structured/planning/design-discussion-basis/drawing-register.csv)及[變更表](../structured/planning/design-discussion-basis/change-log.csv)記錄，不另建一套需求、表格或匯入工具。

## 一次回圖怎麼處理

1. 原始交付檔另存新的私人目錄，保留提供方、日期、檔名、格式、SHA-256、棟層與方案狀態。請對方列清本次更新哪些圖、未改部分沿用哪一版；缺圖、混版與權責未明先記待補。
2. 以同版平面、剖面、門窗表、結構、機電與報價核對。只有PDF也能先閱讀及提問；需要數值檢核時，再補可追溯的模型、尺寸與專業依據，不從圖片猜門淨寬或管道高程。
3. 沿下表八項檢查原新版差異。每個改動回填原change-log，連回既有BC問題、需求ID、受影響樓層、工程節點及估價依據；「圖沒畫」與「模型差異沒列出」均不代表不受影響。
4. 將缺資料、確有衝突、可比較的替代分開。圖面、費用工期、屋主選擇、專業核對及正式發行各自記錄；收到文件只代表有這份文件，不等於內容或簽認權責已核。
5. 資料齊備後，在獨立比較中回套、核完整代價，再由屋主決定仍需取捨的項目。正式版次及舊版停用按有權責方程序處理，不能用這份閱讀包直接發行施工圖。

會後狀態沿[六段行動與回覆追蹤](../structured/planning/design-discussion-basis/abc-coordination.html#after-meeting)記，不重抄另一份紀錄；日期、窗口、價格及選擇目前全留白。

## 八項核對重點

| 步驟 | 要核什麼 | 須一併回看 |
| --- | --- | --- |
| RETURN-01 收件與版次 | 原新版圖號、來源雜湊、完整棟層及所據會議／問題 | 建築、結構、門窗、機電、產品表及報價是否同版；BC-04／05 |
| RETURN-02 基地與結構 | 地籍、騎樓退縮、可用面積、後巷／外窗權利、座標標高及梁板梯洞 | 約32地坪不等於每層可建32坪；改梯須核上下層、門片、淨高及管線；BC-01／13／16 |
| RETURN-03 A設計師介面 | 主臥、公衛、套衛與等量收納，門組、降板防水、新風弱電及梯下MDF | A裝潢另談，預埋共同核；未採用的小主臥與無窗案不能混入，供料、折抵及保固逐列議定；BC-03／06／22 |
| RETURN-04 B祭祀與搬轎 | 朝街正前門、神桌背牆及上下乾保護，後門預設／無後巷前門備案 | 前搬轎走祭祀正門；完整含桿、人員、門態與路線重核，既有三項家規答覆不延伸成地下穿保護的許可；BC-07／08 |
| RETURN-05 B濕區及屋頂 | 原面積與外窗、乾檢修、合法排水終端、上游及G4D完整包絡 | 落差上下限不能預選500／600；Q3到達、聲學新風、RF24㎡與R1防水仍獨立，局部可行不解全棟缺口；BC-09／13／14 |
| RETURN-06 C日常與照護 | 合併客餐拉椅通行、獨立公衛、可關前室、床側及浴室門盆扶手 | 訪客不穿孝親房、床體避上層濕區、唯一2F洗衣機；濕地轉位、盆偏250及18.5mm餘量仍待產品／真人核對；BC-10／11／17 |
| RETURN-07 三棟機電維修 | 全熱優先／至少過濾機械新風、關門睡房、獨立排氣補氣、外口及冷凝排水 | 機型、壓損、噪音、結露、電力與拆換空間同版；3F人數未知不當0，8機位不等於8台；BC-12～15／21 |
| RETURN-08 變更與發行 | 變更前後依據、需求、工序、A設計師介面與客變估價 | 未知費用不填0，互斥方案不相加；屋主選擇、專業核對與正式發行分開；BC-05／19／20 |

八項是閱讀順序，不是八項新需求或自動驗收。詳細條件與原工程節點已接在包內入口，實際變更仍按原ID逐項追查。

## 原表格新增哪些欄

- drawing-register.csv：格式、原始檔SHA-256、所據會議／問題、座標標高、完整樓層、缺件混版、僅收件狀態及須同步重核圖面；沿用原提供方、日期、圖號版次等欄。
- change-log.csv：原新檔SHA-256、變更範圍與依據、原需求ID、同版模型／差異報告、A設計師介面、估價／客變單及未解工項；沿用原費用、工期、選擇、核對及發行欄。

公開包只產空白模板；已填副本留在inputs/private/，不自動搜尋、合併或回寫。這輪交付另建design-discussion-024，001～023保留；下次另用025，不覆寫舊回覆。表單需搬版時先保留原檔，再按ID及圖號人工對帳。

## 正式圖面沿既有工具

[R001交付契約與preflight](architect-r001-handoff.md)及[不可變版次流程](review-workflow.md)已有收件、試匯入、正式匯入、來源驗證及比較。優先同版PDF＋IFC；只有DWG時由設計方另存DXF並補語意mapping。模型需要可追溯實體ID、單位、共同座標基準與樓層標高，不能靠房名猜測跨版實體。

雜湊一致只表示與指定檔案快照相同，不證內容正確或專業核可。模型比較只能列出已表示、可對應欄位的新增／移除／修改；不同ID或mapping須人工對帳，風水、完整照護、聲學、權利與費用影響仍需對應依據。

R000是歷史非權威參考，不是目前概念SVG／3D的正式匯入底圖。現有structured/architect_handoffs/R001/也是交付範本；下列R001／R002只是未來操作示例，並不表示已收到或已核定這兩版。正式來源或mapping更新後使用下一個不可變版次，不能改寫前版。

日後實際資料到齊，才在另一個WSL終端機執行。先依原交付契約準備新的私人交付目錄inputs/private/architect-return-001，並確認下列結果目錄尚未使用：

```bash
timeout 20s mkdir -- inputs/private/architect-review-001
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m house_design drawings preflight --package inputs/private/architect-return-001 --output inputs/private/architect-review-001/preflight.json
```

第一條若失敗便停止，另選新目錄；不覆寫原結果。preflight以暫存模型檢查交付完整度，不建立正式R001，也不代表適合定案或施工。未達本次readiness時保留報告逐項補件；逾時或被終止便列未完成，不背景重跑。

正式匯入須另依原流程與階段執行。已有兩個來源可驗證的正式版次、且以下輸出檔尚未存在時，才使用：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m house_design drawings verify --revision R001 --root inputs/revisions
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m house_design drawings verify --revision R002 --root inputs/revisions
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m house_design drawings compare --from R001 --to R002 --root inputs/revisions --output inputs/private/architect-review-001/R001-R002-diff.json
```

逐條核結果，任一失敗即停止相依步驟。這輪未執行上述圖面命令，未改正式需求、家規、原ABC／3D或前後門備案。

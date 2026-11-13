# B前排水：回覆後的研究與估價分流

2026-11-11。[分流與估價入口](../structured/planning/b-front-drop-reply-routes/index.html)。接既有[BFD八題／28欄接口](b-front-drop-builder-interface-v1.md)，原接口、020快照與研究來源凍結保留。本輪只把回覆後的動作與估價範圍列清，不新增格局或要求現在補實測。

## 先分清是待資料還是宣告數字衝突

空白模板只觸發BFR-07資料未齊；不是七種失敗，也不是要求現在把28欄填完。局部缺資料時繼續獨立準備，未知保null，不推定接受縮面積、無窗、少平台或放寬家規。

前終端／權利文件宣告not-available時走BFR-01；單段落差數字不足另走BFR-02。兩者不能混成「所有方案無解」，也不能以G4D、G5或前濕區重排名稱不同就解除共同終端前提。documented及落差相容仍只代表有文件／宣告算式，沒有合法授權。

上游不足走BFR-03，室內落差不能回頭改善騎樓。梯下d上下限無交集走BFR-04，先核實體頂底、管件與重複扣帳，G4D局部家族優先；前濕區重排居次，G5全梯鏡像最後。外框侵平台、保護或超原梯核走BFR-05，微後移也要重核新後緣梯底，不能只修平面或吞掉幾毫米。

四組全數字相容才觸發BFR-06，仍須完整水力通氣、清掃抽換、權利、防火與兩版搬轎，且RF24／Q3聲學／R1防水仍另核。任何觸發只標「研究下一步」，不選d、移井、採用或發行施工圖。多個衝突會同時列出，不隱藏其餘問題；後續研究均註明前終端的當前待核狀態。

## 六種估價範圍，不直接合計

BFC-01共通資料與同版核對只計一次。BFC-02 G4D局部、BFC-03前濕區重排、BFC-04全梯鏡像是互斥設計方向，只比較完整版本的差額，不能當三套同時施作相加；後兩者尚無完成替代圖，先列研究費與範圍，施工價待圖。

BFC-05合法終端與路線替代要說清和共通工作的重疊及原契約是否已含。BFC-06成品、足尺／搬運及工程交接把首裝、檢修、汰換與保固分列。研究設計費、施工價、數量、幣別、工期、折抵及屋主選擇目前全留白，不虛構估價或自動總額。

原主臥／兩衛外窗、茶水、KTV／客房／工作天井及RF目標不改；神桌朝街、正前開門、背牆與祭祀／乾背保護、武轎庫避濕及前後搬轎兩版保留。只有具體同版完整替代與代價可比較時，才請屋主取捨，不因本輪繼續而放寬。

## 日後明確指定私人算式結果才回算分流

本輪未讀取或搜尋任何實際私人回覆。公開包只引用空白基準；日後先按28欄接口產新私人算式結果，再指定該review.json。工具核報告封印、來源版本，從原條件重新計算並逐項相符後才產分流；只改status、缺欄或塞入不同版次會拒絕，不靠關鍵字猜「可以」。

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_reply_routes.py \
  --result inputs/private/b-front-drop-result-001/review.json \
  --output inputs/private/b-front-drop-routing-001
```

結果目錄必須全新，下一次用002，不覆寫舊算式、條件、回覆或公共模板。私人結果仍留inputs/private，不會自動匯入離線交付或改正式需求；費用需人工按同版完整範圍議定。

公開基準小檢查：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_reply_routes.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_reply_routes.py --check
```

沿原SEQ-04／BC-CMP-01／B-WET-001，包內增兩份CSV接原B前排水頁，不增比較案或圖面。新交付快照021，後續022；020及更早各保當時來源。沒有新外部AI、瀏覽器、WebGL或主3D生成，程式測試不等於專業核可。

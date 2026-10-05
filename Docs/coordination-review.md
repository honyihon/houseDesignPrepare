# 建築／裝潢套繪檢核第一版

用途：收到建築師的正式版次後，將家具、櫃體、門扇開啟區、梁柱、管線、操作區及搬運路徑放在共同座標下，輸出可追溯的問題與可列印圖。這不是建照審查、施工圖簽證或風水保證。

## 先看什麼

- `house_design/coordination.py`：幾何檢核、證據條件、問題追蹤及套繪圖。
- `scripts/demo_coordination_review.py`：三棟合成範例，不能視為目前住宅方案。
- `structured/examples/coordination/reviews/DEMO-R2/coordination.html`：執行範例腳本後可開啟的可列印套繪。
- 正式資料仍以 `inputs/revisions/<版次>/manifest.json` 與封存的 normalized model 為準。既有概念 HTML／3D 不會自動轉成權威圖面。

## 正式流程

先依既有圖面匯入流程建立不可變版次（PDF 加 IFC／DXF 及語意 mapping）。再產生給裝潢設計師的空白套繪模板：

```sh
python -m house_design review template --revision R001 --output inputs/coordination-R001.json
python -m house_design review run --revision R001 --coordination inputs/coordination-R001.json --skip-pdf
python -m house_design review run --revision R002 --previous R001 --coordination inputs/coordination-R002.json --previous-coordination inputs/coordination-R001.json --skip-pdf
```

模板不覆蓋現有檔案。`revision_id` 和 `revision_hash` 必須與正式 manifest 一致；更新圖面後應重新產生模板、重新對位，不可只改雜湊繼續使用舊配置。報告含完整套繪快照與雜湊，任何內容改變都需重新簽認。舊簽認不會繼承。

安裝幾何套件：`pip install -e '.[drawings]'`（需 Shapely 2）。沒有套繪或證據時回報未知；不能以「沒有問題被找到」解讀為全案合規。

## 填寫契約

所有長度為 mm，`polygon_mm` 為共同座標中的閉合區域頂點（至少三點，不必重複起點）。模型和套繪的物件 id 不可重複；棟層必須在正式模型存在。

```json
{
  "id": "B-F1-altar",
  "building_id": "B",
  "floor_id": "floor-1",
  "category": "altar",
  "polygon_mm": [[500,500],[1700,500],[1700,1300],[500,1300]],
  "geometry_method": "professional_verified_polygon",
  "evidence": {"verified_by": "填查核人", "verified_at": "填日期", "reference": "填本版圖號與明細"}
}
```

這些座標只是填寫格式範例，不能用於實際設計。精確多邊形接受 `closed_dxf_polyline`、`professional_verified_polygon`、`surveyed_polygon`；bbox、IFC convex hull 和概念尺寸不能證明淨空。共同座標需有查核人、日期、方法、軸向和至少兩個控制點。套繪頂層 `registration` 另填對位證據。

`checks` 每項填穩定 `id`、`kind`、`domain`、`priority`、`subject_id`、`target_ids`、`obstacle_ids`、`evidence`，可加 `requirement_id`、`responsible_role`、`next_action`、`title`。

| kind | 設計師要提供的內容 |
|---|---|
| containment | 家具／門扇區為 subject；完成面房間為唯一 target，標註 `boundary_measurement: finished_clear` |
| collision | 家具、門扇區、梁柱／神桌背牆管線保護區等指定 polygon 比較；門弧應提供完整開啟掃掠區，不是單一開門姿勢 |
| clearance | 完成面房間為 subject，操作／抽換淨空 polygon 為唯一 target，所有障礙列入 obstacle_ids |
| turning_circle | 完成面房間、`center_mm`、`diameter_mm`，檢查指定圓而非搜尋所有可行圓心 |
| route | 完成面通行聯合區、`path_mm`、`width_mm` 與全部障礙；門口／門檻／高差另由專業審查 |
| carry_route | 另填 `transport` 的 width/depth/height_mm、measurement_state: measured、evidence，及 route_clear_height_mm；深度沿直線路徑方向，端點延伸半深度；非直線交由專業演練 |
| projection | 神桌／神明堂保護區與同棟上層廁所、廚房、濕區、管線、梁等；需所有樓層標高及完整聲明。神桌當層梁與背牆管線另做 collision／headroom，不能以跨層通過代替 |
| sightline | 門洞 subject、床／神桌／廁所目標、ray_mm、direction_verified: true；屏風需證明 fixed_opaque_sightline_blocker: true（包含固定性、高度及不透光性） |
| headroom | subject.finished_headroom_mm 及 minimum_mm；證據須引用完成面至最低梁／天花點，不能用樓高 |
| numeric | actual、threshold、unit、operator: min/max，證據引用計算書；此版比對已提供數值，不自動計算建蔽／容積或判斷法規適用 |

負向證明（沒有障礙／沒有沖射）須提供 `coverage`：building_id、floor_id、domain、complete: true、check_ids、object_ids、evidence。object_ids 要列出該層所有具幾何的物件；比較清單不可漏掉已知家具／梁柱／管線等。非障礙需逐物件以 `obstruction: false` 加查核證據說明（例如上方且不影響此檢查的構件）；不可為求通過批次忽略。跨層投影需同棟所有樓層聲明。沒有畫出的物件仍仰賴設計師完整性聲明，系統不能偵測圖面外現場物件。

法規 domain 的任何檢查須另外填 law：title、article、effective_from、applicability、evidence。請建築師查核條文版本、基地與建物用途適用性；不得將屋主 900mm／1500mm 等偏好自行稱為法定門檻。一般屋主標準放 accessibility／space_program 等 domain。風水只檢查指定的可觀察衝突，坐向、龍虎邊、擇日等保留專業確認。

candidate 需求的可計算結果只供討論；缺證據仍是 unknown，不能藉 candidate 降成一般警告。風水未確認 must 需求不變成強制違規。武轎現有暫估尺寸繼續供收納排版，搬運審核等實測後再確認。

## 三棟優先討論清單

- A：設備與全齡生活；一樓完整生活、家具／輪椅操作、設備維修、弱電機櫃與屋頂設備介面。
- B：神桌背牆與上方濕區／梁管線、神明堂視線與動線、香火排煙／防火／祭品清理、武轎收納與搬出轉彎、儲藏防潮和門口尺寸。
- C：長輩自住完整生活圈；床側轉位、夜間如廁、衛浴救援、照護與升降策略，同時檢查設備拆換及家具碰撞。
- 全棟：結構與機電、逃生、採光通風、消防、無障礙、排水防水、噪音、插座、預算和施工介面。未設檢查、不可量化項目與法定專業事項仍要列入會議逐項簽認。

第一版不做自動路徑搜尋、三維旋轉掃掠、現場量測、法規條文更新或風水方位推定。檢查指定配置與已提供資料，不代表對所有可能情境做完審查。

生活、故障、跨棟與施工驗收的完整追蹤見 [防漏項與決策總表](planning-register.md)。幾何通過不能代替整個生活情境完成。

## 產物與問題追蹤

`report.json` 保存證據與套繪，`report.md` 是會議清單，`index.html` 顯示問題及版次差異，`coordination.html` 顯示每層精確圖形、跨層投影、路徑和迴轉區，附實際值、門檻／來源、負責人與下一步。

沿用 check id 可以追蹤 new（新增／回歸）、resolved（通過或不適用）、persistent（持續）、evidence_lost（失去證據）。刪除檢查不會當作解決；需求判斷按本次需求清單重新評估，不代表重現過去屋主決策。所有結果需建築師／設計師專業確認。

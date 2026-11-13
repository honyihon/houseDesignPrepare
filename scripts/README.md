# House Design Workflows

現在採「條件式預先規劃，實際資料到齊再統一套用」。目前圖與資料入口見[專案狀態](../Docs/project-status-v1.md)，本頁只放操作與資源界線，不再複製設計進度。

最新[洗衣預埋前溝通單](../Docs/abc-laundry-roughin-v1.md)用`export_abc_laundry_roughin.py`產八項接口與三處用途單頁圖，綁定046輪用報告與30來源、現行建商計畫；不改原研究或已驗ZIP。先匯出本研究，再依序更新project-next-steps、builder-communication、design-discussion-basis；一圖接原systems設備頁，88SVG／129檔。20欄實際資料全null，沿原BC／A-IF與inspection-log，不新增必填表或代定點位／規格。交付047、下次048，001～046不覆寫；沒有自動瀏覽器或WebGL重跑。

## 日常只讀檢查

在專案根目錄逐條執行，每次最多20秒：

~~~bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/check_repository_health.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/check_project_status.py --check
timeout 20s .venv/bin/ruff check house_design scripts tests
~~~

來源索引列出現行與歷史包，預設 --check 只要求現行來源相符；--include-history 仍能完整追查歷史差異，不重寫舊hash。即使檔案相符，也不代表畫面、產品或施工通過。

新風條件模板及獨立重算：

~~~bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_abc_fresh_air_planning.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_abc_fresh_air_planning.py
~~~

資料初始化／分批填寫／新私人目錄輸出，見[條件式工作說明](../Docs/abc-conditional-planning-v1.md)。不要將研究假設填成實測；--inputs 預設唯讀，--out 只建立新的 inputs/private 子目錄，不覆寫原ABC或3D。

三棟跨專業優先議題從同一work_items衍生：[決策與條件總表](../structured/planning/project-next-steps/index.html)。只寫獨立HTML／Markdown／CSV／JSON，不寫正式需求或原圖：

~~~bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_project_next_steps.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_project_next_steps.py
~~~

## 建商會議與A裝潢介面

上層儲藏新需求見[逐層新圖](../structured/coordination/upper-floor-storage-v1/index.html)／[安排及限制](../Docs/abc-upper-floor-storage-v1.md)。先執行`timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_upper_floor_storage.py`，再順序更新三個討論工具；10張新圖涵蓋ABC 2F／3F／RF九層及B RF兩版本。交付副本以plan_readability從原title／內外機欄補可見圖例，不更動源圖幾何。新櫃尚未併主3D，無瀏覽器工作；新快照028、後續029，001～027保留。

[同源儲藏立體檢視](../structured/coordination/upper-floor-storage-viewer-v1/index.html)／[建立與修正](../Docs/abc-upper-floor-storage-3d-v1.md)／[第3版回傳驗收](../Docs/abc-upper-floor-storage-3d-qa-v1.md)沿上述凍結平面資料，只為新櫃呈現指定高度，周邊保多邊形／占地投影，不改原主3D。lkfOCT的204項自動檢查通過、30項來源與20張特寫已核；本輪不改驗收來源或重產3D，只補後到紀錄與討論索引。未來若改檢視來源，執行`timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_upper_floor_storage_viewer.py`後依序更新三個討論工具；`timeout 20s node scripts/check_storage_3d_playwright.cjs --preflight`只查檔案，新版瀏覽器仍由屋主另開Windows終端機。快照033沿同一份已驗收3D ZIP，後續034，001～032保留。

[併入前同版核對](../Docs/abc-upper-floor-storage-merge-v1.md)用`timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/check_upper_floor_storage_merge.py`從實際內嵌模型核十版本／30組狀態，只比資料、不啟動場景；加`--write-report`只更新其JSON。A／C六層備未套用座標，B四案需先整層同步；相同XY放得下不能代替房界／梯核版本一致。該次快照034沿同一份已驗收3D ZIP，原001～033保留。

[A／C完整場景加櫃比較](../structured/coordination/ac-storage-preview-v1/index.html)／[顯示驗收結果](../Docs/ac-upper-floor-storage-qa-v1.md)維持6BIQez受測原檔：188檢查／24案例通過、36張截圖目視完成，25來源相符。六件櫃以外的房界、家具與C樓梯／空調保持，B不混入；手機整層較密等限制仍明列。只核檔案可用`timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_ac_storage_preview.py --check`及`timeout 20s node scripts/check_ac_storage_preview_playwright.cjs --preflight`，不跑場景。若日後改來源／畫面，舊passed不沿用，另由屋主Windows終端機重驗。交付038沿兩份已驗收ZIP並核相同來源／產物摘要，下次039，001～037保留。

[B上層同版底圖與收納](../structured/coordination/b-upper-storage-sync-v1/index.html)／[安排與限制](../Docs/b-upper-storage-sync-v1.md)將P4二樓、Q3三樓與RF D1／D2原配置／收納接成八張平面及一張梯井接口；原家具、兩個RF桌位、後門／前門各三態來源保留。這是靜態底圖與未來3D輸入，不是新3D，原RF24㎡、排水與專業缺口保留。先更新本底圖，再依序更新三個討論工具；本輪快照039附第三份獨立ZIP，下次040，001～038保留。

    timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_upper_storage_sync.py
    timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_upper_storage_sync.py --check

[B同版上層／收納3D比較](../structured/coordination/b-upper-storage-3d-v1/index.html)／[第2版驗收](../Docs/b-upper-storage-3d-qa-v1.md)已核kVD0sW的127檢查／16案例、96來源及32張桌機手機截圖；二樓梯完整名稱可讀，顯示修正結案。原幾何、14張平面及已驗ZIP保持；產製時待驗狀態由另存的同源回傳補上，不改舊證據。交付042沿第四份ZIP另綁驗收，下次043，001～041保留；本輪沒有背景啟動場景或重跑。

續作[逐層收納看圖](../structured/planning/design-discussion-basis/life-walkthrough.html#storage-review)，在既有生活頁列十案例的來源尺寸、取物與用途代價；建議沿inputs/design-discussion-basis.json的storage_owner_review，幾何仍取inputs/upper-floor-storage.json，不寫回原來源。回饋沿ABC-DAILY-CHAIN原列，28情境／18CSV及四份獨立ZIP保持；首頁B改讀同源顯示摘要。依序更新三個討論工具及小範圍檢查，交付043、下次044，001～042不覆寫。未啟動新瀏覽器、場景或採用。

    timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_upper_storage_viewer.py
    timeout 20s node scripts/check_b_upper_storage_3d_playwright.cjs --preflight

建商六階段議程／七份空白回覆表與A裝潢介面見[溝通包](../structured/planning/builder-communication/index.html)。更新總表後再重產本包；實際回覆用新的私人副本，已有目錄拒絕覆寫：

~~~bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_builder_communication.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_builder_communication.py --init-records inputs/private/builder-meetings-001
~~~

[完整用法](../Docs/builder-communication-v1.md)。這是靜態文件工具，不回填採用、不啟動瀏覽器；CSV空白不代表零元或通過。

逐層版本、A設計師任務書、B／C比較與離線附件已接成[獨立討論包](../structured/planning/design-discussion-basis/index.html)。只複製現有SVG作閱讀副本，不重建3D；[操作方式](../Docs/design-discussion-basis-v1.md)：

~~~bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_design_discussion_basis.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_design_discussion_basis.py --create-share inputs/private/design-discussion-001
~~~

--create-share只建立全新私人目錄與ZIP，不讀舊會議回覆、不寄出。公開空白模板重產時，先更新next-steps，再builder-communication，再本包；原私人紀錄不覆寫。

B上層前公衛／後套衛兩案為獨立小型幾何研究，保原3D、後門／前門各三態；面積達標不等於前室內、排水、淨高與隔音已核。見[研究入口](../structured/coordination/b-upper-replan-v1/index.html)及[說明](../Docs/b-upper-replan-v1.md)：

~~~bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_upper_replan.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q --tb=short -p no:cacheprovider tests/test_b_upper_replan.py
~~~

P3只深化前段管井、乾側檢修與可關門態，另核支管＋偏移全長，原P1／P2不重產。見[P3入口](../structured/coordination/b-front-service-detail-v1/index.html)及[限制](../Docs/b-front-service-detail-v1.md)：

~~~bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_service_detail.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q --tb=short -p no:cacheprovider tests/test_b_front_service_detail.py
~~~

若有修改，先重產P3，再依序next-steps、builder-communication及design-discussion-basis；完整排水仍未解騎樓／梯核，不將靜態通過當工程核可。

C完整1F照護整合為[獨立靜態比較](../structured/coordination/c-ground-coordination-v1/index.html)，不重產舊照護或原3D；[調整與限制](../Docs/c-ground-coordination-v1.md)：

~~~bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_c_ground_coordination.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q --tb=short -p no:cacheprovider tests/test_c_ground_coordination.py
~~~

若修改C比較，先重產這個小包，再更新next-steps、builder-communication及design-discussion-basis。四組門81態不等於實際照護／門組核可，舊來源差異仍保留。

B三樓娛樂與隔音空間見[Q1／Q2獨立比較](../structured/coordination/b-third-entertainment-v1/index.html)／[前量體、天井與RF代價](../Docs/b-third-entertainment-v1.md)。0／50／100等額外內縮僅面積敏感度，不是聲學規格；原KTV20及工作陽台目標不改：

~~~bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_third_entertainment.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q --tb=short -p no:cacheprovider tests/test_b_third_entertainment.py
~~~

若修改B三樓研究，先重產此包，再依序更新next-steps、builder-communication與design-discussion-basis。沒有自動改原3D或採用屋頂機位／開洞。

B工作天井／RF留板帶續案見[R0／R1／R2比較](../structured/coordination/b-working-court-v1/index.html)／[限制與取捨](../Docs/b-working-court-v1.md)。凍結上一輪Q2來源，只產靜態SVG與CSV；R1少開洞不代表解除2F更衣區上方防水代價，R2乾家務不抵原戶外目標：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_working_court.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_working_court.py --check
```

修改本續案時，先產此包，再依序產project-next-steps、builder-communication及design-discussion-basis；不要改寫凍結的三樓比較或舊驗收紀錄。

B屋頂全設備／曬衣及新風介面另見[S1／S2同圖比較](../structured/coordination/b-roof-equipment-v1/index.html)／[資料回套方式](../Docs/b-roof-equipment-v1.md)。前後熱泵預留不當選機；24㎡平台及日常RF前門尚未核可：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_roof_equipment.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_roof_equipment.py --check
```

有實際包絡時，模板另存私人JSON，再用`--conditions inputs/private/b-roof-conditions.json --output inputs/private/b-roof-recalculation-001`寫全新私人目錄；不覆寫公開預設、已填回覆或舊快照。不自動移設備、旋轉或採用。只改本題時先產本包，再順序更新三個討論／交付工具，不改凍結R1及舊圖。

B屋頂日常使用另見[D1／D2桌架與前門](../structured/coordination/b-roof-daily-use-v1/index.html)／[容量及到達取捨](../Docs/b-roof-daily-use-v1.md)。RF前門同洞改左鉸鏈避原全開轉角，700／800／900分別核算，不改24㎡或家規：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_roof_daily_use.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_roof_daily_use.py --check
```

先產此靜態續案，再順序更新project-next-steps、builder-communication及design-discussion-basis；不重產凍結S1／S2、RF或原3D，不覆寫既有私人討論快照。固定前帶不足24㎡已列必要界，不以重跑或微移設備宣稱解除。

B三樓Q3見[L形KTV／上層梯](../structured/coordination/b-ktv-stair-options-v1/index.html)／[條件與失敗案例](../Docs/b-ktv-stair-options-v1.md)。只作獨立平面、兩門九態及局部踏步／平台算式；不執行整套場景或採用新梯：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_ktv_stair_options.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_ktv_stair_options.py --check
```

改本題先產Q3，再依序更新三個討論／交付工具。原Q2、RF R／S／D及所有控制凍結，不重建；新梯到達後移時不得沿用舊屋頂門路結果。100mm等數值只是空間預算，不能當隔音規格。

Q3改梯RF同版接法見[到達／前室／設備](../structured/coordination/b-q3-roof-coordination-v1/index.html)／[條件與代價](../Docs/b-q3-roof-coordination-v1.md)。只重算指定地面、九門態各兩案、日常與必要巡檢；不跑實際樓梯或採用新樓板：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_q3_roof_coordination.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_q3_roof_coordination.py --check
```

修改此題先產本包，再順序更新project-next-steps、builder-communication及design-discussion-basis；不改凍結Q3／D／S來源或私人回覆。新完整平台、前室、門檻及屋突條件須專業回覆，900日常預算不套到770側門或搬整機。

Q3／RF工程接口見[剖面、整機汰換與九項回覆](../structured/coordination/b-q3-engineering-gates-v1/index.html)／[高度與回套邊界](../Docs/b-q3-engineering-gates-v1.md)。只算同版向下投影、四個層厚預算、單洞口持握餘量及24㎡必要界，不改格局或把巡檢當整機搬運：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_q3_engineering_gates.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_q3_engineering_gates.py --check
```

日後把actual-data-template.json另存私人JSON，使用`--conditions inputs/private/b-q3-transport-conditions-001.json --output inputs/private/b-q3-transport-result-001`建立全新結果；空白保null，不自動拆機、旋轉、改門或外吊。寬度相容永遠不核准整段搬運。只更新本題時先產本包，再順序更新三個討論／交付工具；原Q3 RF接法、Q3／D／S來源及已填私人資料凍結保留。

[B條件回覆與退回路線](../Docs/b-review-route-v1.md)直接併在原decision-sequence.html的B段，另有b-review-replies.csv九列，沒有新場景或比較案。export_design_discussion_basis.py會核對固定工程報告SHA-256、報告封印及其來源，區分已知RF24㎡不足與其他待證據；口頭可以不會解除容量缺口。只更新決策文字時順序重產三個討論／交付工具，不重產凍結工程圖；私人副本用全新編號。

[P4前段器具與短支管](../structured/coordination/b-front-drainage-layout-v1/index.html)／[代價及未解項](../Docs/b-front-drainage-layout-v1.md)只改獨立2F前段，保原房界、管井、乾檢修與器具尺寸；九門態、五試線及完整四線重算，最有利4.4mm不當工程餘量：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drainage_layout.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drainage_layout.py --check
```

先產本包，再順序更新三個討論／交付工具；不改凍結P3／Q3來源、兩種搬轎版或原3D。器具真實排口／管徑坡度／高程及1F梯核落水仍待資料，actual-outlets.csv先留白，公開目錄不存實際私人回覆。

[一樓落水平台／踏步](../structured/coordination/b-front-drop-stair-v1/index.html)／[四反例及Claude指令](../Docs/b-front-drop-stair-v1.md)核P4原G0及G1～3，不把不碰家具當可用空井，不作全域無解結論：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_stair.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_stair.py --check
```

先產本包，再更新三個討論／交付工具，不改凍結P4／Q3／兩個1F版本。原四反例包是首輪前凍結紀錄；首輪回應及目前待核狀態見下項，不重產舊圖改寫歷史。

[Claude首輪交叉核對／G4D室內落差](../structured/coordination/b-front-drop-claude-v1/index.html)／[算式與第二輪稿](../Docs/b-front-drop-claude-crosscheck-v1.md)：驗原prompt／stdout／response來源，原G4／G5高程不容列明假設梯底；G4D先在室內高位落500，完整水平長不縮，只部分假設容納。400井外包、騎樓及合法前終端仍待核，Q3前KTV已乾不假造污水減量，沒有全共識或採用：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_claude.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_claude.py --check
```

先產本包，再順序更新project-next-steps、builder-communication及design-discussion-basis。原G0～3／P4／Q3及149控制不動；不重產主3D。第二輪依[自足討論稿](../Docs/claude-b-front-drop-followup-v2.md)在另一個WSL終端執行，不自動啟動長討論：

```bash
python3 scripts/review_b_fengshui_with_claude.py --brief Docs/claude-b-front-drop-followup-v2.md --timeout 900 --output inputs/private/b-front-drop-claude-002
```

上列為首輪當時的指令。後來002模型拒絕、003以Opus指定名稱完成，使用[第二版明確指定模型的執行器](review_b_fengshui_with_claude_v2.py)；[過程紀錄](../Docs/b-front-drop-claude-cli-recovery-v1.md)保留，不重跑或覆寫既有私人回覆。

[第二輪G4D落差範圍與完整包絡](../structured/coordination/b-front-drop-claude-v2/index.html)／[核對與排序](../Docs/b-front-drop-claude-crosscheck-v2.md)已核003回應；有效落差d須同核上下限，不固定500或選600，前後側外擴與上凸分開，上游／通氣／合法終端仍未知：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_claude_round2.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_claude_round2.py --check
```

原首輪包、prompt、149控制及001／002／003紀錄凍結保留。先產新包，再順序更新三個討論／交付工具；新私人交付用019後續020。本輪只有算式與研究排序部分一致，沒有完整設計共識或採用，沒有新外部AI請求。

[G4D建商回覆與資料接口](../structured/coordination/b-front-drop-conditions-v1/index.html)／[同版口徑與回算](../Docs/b-front-drop-builder-interface-v1.md)把BFD八題接原SEQ-04／BC-CMP-01，28欄全null，分批收到來源、版次及共同標高後只算局部，不改圖或放行：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_conditions.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_conditions.py --check
```

日後另存私人條件檔，再用`--conditions inputs/private/b-front-drop-conditions-001.json --output inputs/private/b-front-drop-result-001`產新結果，非空目錄拒絕覆寫。公開討論包只帶空白模板；原第二輪包凍結、019以前快照保留，新接口交付用020後續021，不自動合併任何私人數值。現在不需執行重型驗收或再呼叫AI。

[B前排水回覆與估價分流](../structured/planning/b-front-drop-reply-routes/index.html)／[七條路線與六種估價口徑](../Docs/b-front-drop-response-routes-v1.md)接原八題，不新增格局或比較案。公開基準只觸發缺資料；終端是共同前提，局部相容仍不放行，互斥替代案不相加：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_reply_routes.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_front_drop_reply_routes.py --check
```

日後明確指定`--result inputs/private/b-front-drop-result-001/review.json --output inputs/private/b-front-drop-routing-001`才核原條件及來源、產新私人分流；不自動搜尋或匯入回覆。先產本包，再依序更新三個討論／交付工具；原28欄接口、020以前快照凍結保留，新交付021後續022。不新增AI或瀏覽器工作。

[ABC格局與預埋聯席議程](../structured/planning/design-discussion-basis/abc-coordination.html)／[使用範圍](../Docs/abc-coordination-meeting-v1.md)由inputs/abc-coordination-agenda.json接原BC／SEQ、樓層、比較與圖面。六段共90分鐘只供建議議程，實際日期、窗口與回覆留白；A風格／材質仍另談，不發訊息或安排會議。

只改議程文字時重產三個討論／交付工具；會核時間連續、跨棟引用及既有ID，圖面／3D與凍結研究不重產。新增聯席行動CSV帶在同一離線包，交付快照022，後續023，不覆寫原回覆。

[會後回覆紀錄](../structured/planning/abc-meeting-followup/index.html)／[口徑及私人摘要](../Docs/abc-meeting-followup-v1.md)沿六段COORD與原BC問題，分開記資料、費用工期、屋主選擇、專業文件及圖面發行；回報有文件不是內容或權責已核，不自動結案／放行：

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_abc_meeting_followup.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_abc_meeting_followup.py --check
```

日後用`--records inputs/private/abc-followup-records-001.json --output inputs/private/abc-followup-summary-001`明確指定一份資料、產全新私人結果；不自動搜尋合併，也不匯入公開包。先產本空白包，再順序更新三個討論／交付工具；聯席頁沿原六列CSV增追蹤欄，交付023後續024，舊022與原資料保留。

[回圖核對入口](../structured/planning/design-discussion-basis/source-index.html#drawing-return)／[正式版次銜接與日後指令](../Docs/abc-drawing-return-review-v1.md)沿原drawing-register.csv及change-log.csv增收件／雜湊／影響／估價欄，沒有新增表單或匯入器。只補指引時依序更新project-next-steps、builder-communication、design-discussion-basis；新交付024、後續025，001～023及舊回覆不覆寫。PDF可先閱讀，數值檢核待同版模型與mapping；未收到真圖前不執行preflight／import／compare或建立R001。

[同範圍核價](../structured/planning/design-discussion-basis/decision-sequence.html#quote-review)／[欄位及計價口徑](../Docs/abc-quote-review-v1.md)沿原12組與same-scope-quotes.csv加比較組／列ID、基準及互斥／重複／共用歸屬八欄，沒有新表單、報價匯入器或自動總價。Q分類不是不重疊的工程清單；真實價單留私人副本，不採購或聯絡廠商。依序更新三個討論／交付工具；新交付025，後續026，001～024與已填原檔保留。

[隱蔽工程分批檢查與A交接](../structured/planning/design-discussion-basis/decision-sequence.html#inspection-handoff)／[依據及留證方式](../Docs/abc-inspection-handoff-v1.md)沿SEQ-11／12及原inspection-log.csv增八個空白欄，不新增表格或現場驗收器。九組含B聲學隱蔽節點、完工調試及A進場前後；實際方法、要求值、通知及結果待採用設計／產品／規範與各方約定，不自動放行、簽認或歸責。依序更新三個討論／交付工具；新交付026，後續027，001～025及原紀錄保留。

討論包[首頁快速看圖](../structured/planning/design-discussion-basis/index.html#quick-review)直接沿原聯席retain／request、A任務及B／C比較顯示三棟摘要，沒有新增摘要JSON、表格或決策；[閱讀順序](../structured/planning/design-discussion-basis/index.html#reading-order)依討論進度導向原頁，全部樓層與表格保留於原生details中。只重整靜態文件，未作瀏覽器畫面驗收；依序更新三個討論／交付工具。新交付027，後續028，001～026及已填紀錄保留。

## 資源安全：重型驗收另開終端機執行

遵守[AGENTS.md](../AGENTS.md)：不讓背景驗收影響正常修改。下列項目不由代理自動啟動：

- 瀏覽器／WebGL與完整3D場景runtime。
- 全套pytest、整套圖面生成、大量或高解析轉圖。
- 外部AI長討論／輪詢、套件安裝或提高權限。

遇到逾時、exit 137或SIGKILL，停止本次嘗試，不自動重試。只處理能確定屬於本次的session，不使用全域pkill。舊session不明就列未知。

## Windows 原生 Playwright CLI 驗收

以下由屋主在另一個PowerShell視窗執行；目前主要看圖包是高雄厝／C整合比較：

~~~powershell
node '\\wsl.localhost\Ubuntu\root\workspace\houseDesignPrepare\scripts\check_kaohsiung_options_playwright.cjs'
~~~

只要檔案預檢，可在WSL根目錄執行，不開瀏覽器：

~~~bash
timeout 20s node scripts/check_kaohsiung_options_playwright.cjs --preflight
~~~

舊方案專用CLI仍保留，不互借passed：
check_windows_playwright.cjs（原ABC歷史）、check_current_design_playwright.cjs（2026-10-20比較）、check_b32_rear_right_playwright.cjs（舊B一樓）、check_c_care_bath_layout_playwright.cjs（舊C局部）。
完整方式及先前Windows故障排查見[舊操作手冊](../Docs/archive/scripts-readme-before-reorganization-20261106.md#windows-原生-playwright-cli-驗收)。

瀏覽器passed仍須對來源雜湊與截圖做核對；不是法規、結構、風水、照護、搬運或施工核可。

## 正式圖面與歷史工具分流

[正式圖面／資料權威](../Docs/review-workflow.md)、[R001交付包](../Docs/architect-r001-handoff.md)與[需求／情境總表](../Docs/planning-register.md)另有版次管理，不以概念產圖替代建築師圖面。
HTML的Step 1～8及「每層32坪」參數分支為歷史／回歸用途，不能當目前基地可建面積。舊指令、依賴、解析格式、MCP與故障排除均保留於[歸檔手冊](../Docs/archive/scripts-readme-before-reorganization-20261106.md)。

歷史IFC release gate仍要求 related_report_hash／related_report_generated_at 及有效簽認；domain_checklist.md 是檢核產物，不是專業核可。不要只填 decision: approved 繞過雜湊。

## 本機設定

.claude/settings.local.json 已退出版控，現有本機檔保留；.claude/settings.example.json 只是空白範例，不自動開啟權限或MCP。私人資料、憑證與實際條件放 inputs/private/ 或適當環境設定，不提交Git。

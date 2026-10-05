# 建築師開會包

- 專案：高雄三棟住宅前期規劃（階段 `site_search`）
- 對象：建築師（選地可行性諮詢）
- 產生時間：2026-10-05T01:55:03.807970+00:00
- 開會包雜湊：`55f2b818b42055a757d4abf757f7d07a103a03e48c22396cdeee311f91abf7ec`

> ⚠ 本資料夾全部是屋主端的前期整理，不是法規檢討、不是設計圖、也不是可行性意見。所有分區、建蔽率、容積率、退縮、建築線、結構與消防結論，都必須由高雄市執業建築師依個案正式認定並簽證。
> ⚠ 土地尚未選定。三筆相鄰、每筆約 32 坪是選地目標，不是已取得的基地，更不是每層可建面積。
> ⚠ 未知永遠不是通過：本包內任何標示「未知／資料不足」的項目，都不得被當成已通過或已合規。

## 內容

1. 我們是誰、要蓋什麼
2. 選地淘汰條件
3. 候選地比較與缺件
4. 假設量體試算（假設情境）
5. 設計任務書摘要
6. 目前的硬阻擋與責任分工
7. 圖面交付契約預告
8. 本次會議要拿到的答案
9. 防漏項與當期決策

## 本次會議要拿到的答案

1. 以三筆各約 32 坪相鄰地、每棟 3 層＋RF 為前提，最小可接受的面寬與深度是多少？
   - 為什麼要問：這兩個數字直接填回 SC-FRONTAGE-MIN 與 SC-DEPTH-MIN，沒有它們，候選地比較表無法做出任何篩選。
   - 答案寫回：`inputs/site-criteria.json · SC-FRONTAGE-MIN / SC-DEPTH-MIN`
2. 三筆地要各自申照還是合併申請？對建蔽率、法定空地、防火間隔與棟距分別有什麼影響？
   - 為什麼要問：影響三棟的量體、棟距與設備策略；也決定跨基地管線是否可行。
   - 答案寫回：`inputs/site-criteria.json · SC-THREE-PERMITS / SC-CROSS-PARCEL-UTILITY`
3. 室內車庫（單車位淨 3000 × 6100 mm）在這種面寬下是否成立？不成立時的替代方案是什麼？
   - 為什麼要問：車位在室內是屋主的硬需求；此淨尺寸由休旅車加壁掛充電樁推導，不是抓的。
   - 答案寫回：`inputs/site-criteria.json · SC-FRONTAGE-MIN；envelope 情境的 ENV-GARAGE-1BAY`
4. B 棟神明廳與武轎搬運路徑（目前規劃目標淨寬 1500 mm），在結構與法規上有哪些早期限制？
   - 為什麼要問：神明廳位置與武轎進出會鎖住樓梯、開口與結構，愈晚改代價愈高。
   - 答案寫回：`envelope 情境的 ENV-SHRINE-STACK / ENV-PALANQUIN-PATH`
5. 全齡無障礙基準下，1F 完整生活圈（出入、衛浴、睡眠、用餐）的最小合理面積是多少？
   - 為什麼要問：全齡無障礙是不可妥協的家庭基準，但專案目前沒有可引用的最小面積依據，只能標 unknown。
   - 答案寫回：`envelope 情境的 ENV-GROUND-FLOOR-LIFE / ENV-ELDER-SUITE`
6. 你需要我在簽約買地前準備哪些文件，才能給出書面可行性意見？費用與時程大概是多少？
   - 為什麼要問：這場會議的目的就是把「憑印象買地」換成「有書面意見再出價」。
   - 答案寫回：`inputs/predesign.json · PD-SITE-SELECTED 的 evidence pointer`

## 當期防漏項待決策

[完整情境／驗收總表](../../risk-review.html)

- PLAN-ACCESSIBILITY-03：預留電梯、樓梯升降或只維持一樓生活？（屋主／建築師／相關專業）
- PLAN-HOUSEHOLD-01：哪些空間與使用需求不能刪？（屋主／建築師／相關專業）
- PLAN-HOUSEHOLD-02：日常與尖峰人數各是多少？（屋主／建築師／相關專業）
- PLAN-HOUSEHOLD-03：A與C各要保留哪些一樓完整生活能力？（屋主／建築師／相關專業）
- PLAN-RITUAL-01：香燭及金紙在哪裡用、頻率多少？（屋主／建築師／相關專業）
- PLAN-RITUAL-03：哪些風水禁忌是不可接受，哪些可調整？（屋主／建築師／相關專業）
- PLAN-SHARED-01：水電網路和車道各自獨立到什麼程度？（屋主／建築師／相關專業）
- PLAN-DELIVERY-01：總預算範圍備用金與分期順序如何確認？（屋主／建築師／相關專業）

## 資料來源與雜湊

| 檔案 | 用途 | 產生方式 | SHA-256 |
|---|---|---|---|
| `inputs/project.json` | 基地事實與候選土地 | `屋主維護` | `c407735841f79c599cd087ad5a9853f1110f50652cefa93b62945addedb5f930` |
| `inputs/predesign.json` | 階段閘門與三棟定位 | `屋主維護` | `739cc4a6a0dabe2c86f6c6a689832bfcdef0e38caaeed45c5f2a0f623008fb0b` |
| `inputs/site-criteria.json` | 選地淘汰條件 | `屋主與建築師共同填寫` | `89f8b97d416604d9b1cea55b1ab6fa65a743397da7bdc11ee5fee92c7c1af878` |
| `structured/predesign/site-compare.json` | 候選地比較 | `predesign site-compare` | `2d85c10e634a7e0db90b86e8f628867aeeb3e3ac9a4dd30c483f1fba9bcfe167` |
| `structured/predesign/envelope.json` | 假設量體試算 | `predesign envelope` | `a19ae26e93d5bc237eb7943900451fdba6f8bdbef5b4fe87de5098611ac6d6ed` |
| `structured/predesign/design-brief.json` | 設計任務書 | `predesign brief` | `d72ff0cd79aa8701dc5eb7e81d8fdaa4fb0593f908343a236fe1f197279892b0` |
| `structured/predesign/report.json` | 前期準備完成度 | `predesign report` | `4ce3477c57c012265a816a85e14ac9daf78b3428075fc60eb62eb887d86fc6ca` |
| `structured/architect_handoffs/R001/handoff-manifest.json` | 交付契約 | `drawings prepare-handoff` | `99c7169b67cec0e938a824761e739f5c3680a8f5b90ec46fe9b43baddc62d4e1` |
| `structured/predesign/risk-review.json` | 防漏項與當期決策 | `predesign risk-review` | `84c5b8be524fc5a166a4557e2a98dc011d0eac749d38d0944444852d0f4bdc6f` |

## 屋主回覆與未解事項（非驗收）

草稿與屋主回覆不是需求確認、法規簽證或專業驗收。禁止填姓名、健康細節、精確預算及電腦絕對路徑。

尚無已匯入紀錄。

# 地籍資料取得前：先完成準備，不代填基地事實

這份流程適用三棟 A／B／C 的選地討論。資料結構、未知攔截、逐筆試算與回歸測試已先做好；地籍、可建性、管線權利與專業評估仍須取得實際文件。不構成法規、結構、風水或搬運安全簽證。

## 資料放哪裡

| 內容 | 來源檔 | 現在可先做 |
|---|---|---|
| 每塊候選地的 A／B／C 三筆基地 | `inputs/project.json` → `site_search.candidate_sites[].parcels[]` | 分開 parcel_id、building_id、地號、面積、面寬、深度；未知數值留 null，不將三筆合計除以三假裝已測得 |
| 新候選地空白範本 | `inputs/site-candidate.template.json` | `intake site-add` 複製新範本；已登錄候選地補缺的欄位但保留舊填答 |
| 選地門檻 | `inputs/site-criteria.json` | 可先與家人整理底線；門檻數字尚未議定就維持 unknown，不自動採建議值 |
| 三棟核心功能 | 候選地 `core_function_assessment.A/B/C` | 整理 A 一樓生活照護、B 祭祀／搬運／上下疊圖、C 孝親衛浴；由建築師附配置評估，土地相鄰不算證明 |
| 跨基地系統 | 候選地 `cross_parcel_utilities` | 給水、電力、污雨排水、弱電分別記錄 connectivity、route_rights、responsibility_boundary；共十二項須分開查核 |
| 可負擔性 | 候選地 `budget_assessment` | 預算上限、土地、基礎、管線、搬運粗估及 affordability 分開；公開只留 yes/no，金額留 `inputs/private` |
| 武轎 | `inputs/physical-items.json` | 收納實測用 measurements；搬運另填 transport.assembled_dimensions、assembled_measurement 及 route_rehearsal |

跨基地管線至少備妥：各自計量與表位、管路路線及權利、維修進出、停水停電影響、費用分攤、設備及管路所有權。若改採各棟獨立供應，應由專業提出新策略並重新檢討門檻，不隨意把所有欄位填 yes。

污水及雨水仍須在證據文件內分開確認去向，不以其中一者已可接代表另一者成立。

## 事實與證據格式

每個比較欄位使用同一種資料格：

```json
{
  "status": "unknown",
  "value": null,
  "source": null
}
```

取得文件後，source 改成下面的結構，填實際文件參照、查核人及日期。只有事實查核完成才把 status 改為 verified；暫估使用 assumed，尚待詢問用 pending。

```json
{
  "reference": "文件路徑或官方文件編號，含適用地號與頁碼",
  "reviewer": "實際查核人／專業角色",
  "checked_at": "YYYY-MM-DD"
}
```

程式檢查來源欄位完整與日期格式，不驗證文件真偽，也不能替建築師作專業認定。空來源、只有 verified 標籤、舊版純字串事實或未查核值都維持未知；有完整來源且確定不符合門檻才會淘汰。舊版 `unknown`／`pending` 字串仍能讀取，不會被當成不符合。

核心功能、跨基地管線與預算的複合門檻，每個子欄位都須符合並有來源，不能以單一總括回答代替。逐筆面寬、深度則檢查 A／B／C 各筆；確定有一筆不符即可列不符合，其餘缺資料仍逐項保留。

## 地籍資料到來前可以如何試想

以下是刻意指定的假設，不寫回候選地、不變成已確認的要求；輸出另放 `/tmp`，不覆蓋正式討論入口。可調整面寬、建蔽率、退縮比較敏感度，但不以樂觀情境當購地理由。

```bash
.venv/bin/python -m house_design predesign envelope \
  --assume-parcel-sqm 100 --assume-bcr 0.6 \
  --assume-frontage-mm 6000 --assume-depth-mm 18000 \
  --assume-setback-mm 0 --output-root /tmp/house-envelope-assumption
```

收到逐筆地籍資料並附來源後，可逐棟試算：

```bash
.venv/bin/python -m house_design predesign envelope \
  --candidate SITE-001 --parcel PARCEL-A --output-root /tmp/house-envelope-A
```

B／C 改用 PARCEL-B／PARCEL-C 與不同輸出目錄。未指定單筆、只有三筆總面積、或逐筆證據不足時，基地幾何保持未知；不回填每筆 32 坪目標、不默認三筆等大。有 `--assume-*` 覆寫的欄位會另標假設，不能說是文件查得。

三棟原 HTML 與 `structured/candidates/model3d.html` 仍是格位／家具初排，這次沒有改房間、縮小家具或將草圖定案。實際面積、門位、柱位、完成面及風水方位確定後再疊圖檢討。

## 收納量測與搬運驗證分開

1. `measurements` 只證明收納外廓，保留既有追加量測流程。
2. `transport.assembled_dimensions` 必須包含抬桿及突出物的完整寬、深、高；`assembled_measurement` 使用上述資料格，value=yes 並附實測來源。
3. `transport.route_rehearsal` 另記整段路徑實際演練結果與來源，不能由尺寸量測推定已演練。
4. 規劃門寬 1500 mm 仍是初期目標。量體寬度比較不涵蓋門片、門五金、轉角、坡度、淨高及搬運人員站位；即使已實測也保留這項限制。

## 補資料後的順序

先查來源與地號適用範圍 → 比較選地條件 → A／B／C 各自做容量試算 → 交建築師做法規／機能配置 → 屋主確認需求 → 室內設計師核對家具及機電界面。不能倒過來拿家具草圖證明土地可建。

```bash
.venv/bin/python -m house_design predesign site-compare
.venv/bin/python -m house_design predesign envelope
.venv/bin/python -m house_design predesign report
.venv/bin/python -m house_design predesign risk-review
.venv/bin/python -m house_design predesign brief
.venv/bin/python -m house_design predesign owner-workspace
.venv/bin/python -m house_design predesign consistency-review
.venv/bin/python -m house_design predesign meeting-pack
```

`envelope` 沒指定候選地時只是選地目標的假設情境，並非候選地評估。屋主工作頁來源變更後，舊草稿匯入會被攔截；重新開啟新工作頁，不繞過來源雜湊檢查。R000 歷史來源已用原雜湊相符的獨立副本及追加紀錄修復，見 [封存修復紀錄](r000-source-recovery.md)；仍不可當成現行設計。

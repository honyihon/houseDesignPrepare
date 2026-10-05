# 候選土地淘汰比較表

- 專案：高雄三棟住宅前期規劃（階段 `site_search`）
- 產生時間：2026-10-05T01:55:03.602114+00:00
- 比較表雜湊：`53fca7e539d9abe7a180b802dad435b6354290823c9d1ba82a40157f226584e4`

> ⚠ 尚未設定任何淘汰門檻：本表只能列出缺什麼資料，無法做出任何篩選結論。
> ⚠ 未知永遠不是通過：任一硬淘汰條件缺資料時，該候選地的結論只能是「資料不足」，不得當成可行、合規或已通過初篩。
> ⚠ 本表是屋主與建築師共同約定的篩選條件，不是法規檢討；分區、建蔽率、容積率、退縮與建築線必須由高雄市執業建築師依個案正式認定。

## 一、結論摘要

- 候選土地 1 筆：淘汰 0、資料不足 1、可續評估 0
- 淘汰條件 12 條，其中 12 條門檻尚未設定
- 待補證據 12 項

## 二、淘汰條件

| id | 條件 | 類型 | 門檻 | 依據 | 需要的證據 | 負責角色 |
|---|---|---|---|---|---|---|
| `SC-PARCEL-ADJACENCY` | 三筆地界相鄰與各棟基地對應 | 必問 | **未設定** | 相鄰只證明基地關係，不證明三棟核心功能、獨立申照或跨基地管線成立。 | 三筆地籍圖、地號與界址查核；須有來源、查核人與日期 | 建築師／地政士／測量人員 |
| `SC-FRONTAGE-MIN` | 每棟最小有效面寬 | 硬淘汰 | **未設定** | 面寬決定室內車庫是否成立（單車位淨寬由 garage_min_bay_mm 推導），也決定樓梯與走道之後還剩多少可用進深。 | 地籍圖或實測面寬 | 屋主／建築師 |
| `SC-DEPTH-MIN` | 每棟最小有效深度 | 硬淘汰 | **未設定** | 車庫淨深加上前後退縮，是 1F 能否同時容納車庫與完整生活圈的下限。 | 地籍圖或實測深度 | 屋主／建築師 |
| `SC-ROAD-WIDTH` | 臨路寬度與退縮條件 | 硬淘汰 | **未設定** | 臨路寬度同時影響建築線、退縮、消防搶救與車輛進出；過窄的既成道路可能無法申照。 | 都發局建築線指定或地籍圖說 | 建築師 |
| `SC-CONSTRUCTION-ACCESS` | 施工車輛與吊裝進出 | 硬淘汰 | **未設定** | 預拌混凝土車、吊車與板模車進不來，會直接變成小搬運與人工加價，甚至改變結構工法。 | 現勘照片與路寬、轉彎半徑、限高紀錄 | 屋主／營造廠 |
| `SC-THREE-PERMITS` | 三棟能否各自申照與計量 | 必問 | **未設定** | 各自申照與合併申請，對建蔽率、法定空地、防火間隔、棟距與水電表位的影響完全不同。 | 建築師書面意見 | 建築師／地政士 |
| `SC-CROSS-PARCEL-UTILITY` | 跨基地管線是否可行 | 必問 | **未設定** | 專案已列出跨棟給排水、電力與弱電路徑為待確認事項；若不允許跨基地埋管，三棟的設備策略要重做。 | 給水、電力、污雨排水、弱電各自的可接性、管路權利與責任分界書面查核；每個欄位皆須有來源、查核人與日期 | 建築師／水電／公用事業單位 |
| `SC-CORE-FUNCTIONS` | A／B／C 核心功能能否同時容納 | 硬淘汰 | **未設定** | A 全齡 1F 生活圈、B 神明廳與武轎搬運、C 孝親房與無障礙衛浴是三棟定位的底線；放不下就該換地，不是壓縮需求。 | 建築師逐棟核心機能配置評估與圖面證據；predesign envelope 只能當提問素材，不能當已確認證據 | 屋主／建築師 |
| `SC-FLOOD` | 淹水潛勢與基地標高排水 | 硬淘汰 | **未設定** | 室內車庫加上高雄降雨，淹水潛勢與相對標高是不可逆的選地條件。 | 水利署防災資訊服務網查詢結果與雨後現勘 | 屋主／建築師 |
| `SC-LIQUEFACTION` | 土壤液化潛勢 | 必問 | **未設定** | 液化潛勢影響地質調查範圍、基礎工法與造價，須在出價前知道。 | 土壤液化潛勢查詢系統結果；必要時由技師判斷是否需鑽探 | 建築師／結構技師 |
| `SC-NEIGHBOUR-ENV` | 噪音、異味、鄰房開口與西曬 | 偏好 | **未設定** | 白天、夜間與雨後各看一次才看得出來；長輩房與神明廳對這幾項特別敏感。 | 三個時段的現勘紀錄 | 屋主 |
| `SC-TOTAL-COST` | 土地加基礎、管線與搬運後仍在預算內 | 硬淘汰 | **未設定** | 土地單價便宜但基礎、擋土、管線與小搬運昂貴的基地，總價可能反而超出上限。 | 私有預算表上限與建築師／營造廠粗估 | 屋主／建築師 |

## 三、候選地比較

| 條件 | 測試候選地 |
|---|---|
| 三筆地界相鄰與各棟基地對應（必問） | 未知（門檻尚未設定） |
| 每棟最小有效面寬（硬淘汰） | 未知（parcels.PARCEL-A.frontage_mm：門檻尚未設定；parcels.PARCEL-B.frontage_mm：門檻尚未設定；parcels.PARCEL-C.frontage_mm：門檻尚未設定） |
| 每棟最小有效深度（硬淘汰） | 未知（parcels.PARCEL-A.depth_mm：門檻尚未設定；parcels.PARCEL-B.depth_mm：門檻尚未設定；parcels.PARCEL-C.depth_mm：門檻尚未設定） |
| 臨路寬度與退縮條件（硬淘汰） | 未知（門檻尚未設定） |
| 施工車輛與吊裝進出（硬淘汰） | 未知（門檻尚未設定） |
| 三棟能否各自申照與計量（必問） | 未知（門檻尚未設定） |
| 跨基地管線是否可行（必問） | 未知（cross_parcel_utilities.water.connectivity：門檻尚未設定；cross_parcel_utilities.water.route_rights：門檻尚未設定；cross_parcel_utilities.water.responsibility_boundary：門檻尚未設定；cross_parcel_utilities.electricity.connectivity：門檻尚未設定；cross_parcel_utilities.electricity.route_rights：門檻尚未設定；cross_parcel_utilities.electricity.responsibility_boundary：門檻尚未設定；cross_parcel_utilities.sewer_and_stormwater.connectivity：門檻尚未設定；cross_parcel_utilities.sewer_and_stormwater.route_rights：門檻尚未設定；cross_parcel_utilities.sewer_and_stormwater.responsibility_boundary：門檻尚未設定；cross_parcel_utilities.telecom.connectivity：門檻尚未設定；cross_parcel_utilities.telecom.route_rights：門檻尚未設定；cross_parcel_utilities.telecom.responsibility_boundary：門檻尚未設定） |
| A／B／C 核心功能能否同時容納（硬淘汰） | 未知（core_function_assessment.A：門檻尚未設定；core_function_assessment.B：門檻尚未設定；core_function_assessment.C：門檻尚未設定） |
| 淹水潛勢與基地標高排水（硬淘汰） | 未知（門檻尚未設定） |
| 土壤液化潛勢（必問） | 未知（門檻尚未設定） |
| 噪音、異味、鄰房開口與西曬（偏好） | 未知（門檻尚未設定） |
| 土地加基礎、管線與搬運後仍在預算內（硬淘汰） | 未知（budget_assessment.affordability：門檻尚未設定；budget_assessment.budget_limit_reviewed：門檻尚未設定；budget_assessment.land_estimate_reviewed：門檻尚未設定；budget_assessment.foundation_estimate_reviewed：門檻尚未設定；budget_assessment.utility_estimate_reviewed：門檻尚未設定；budget_assessment.handling_estimate_reviewed：門檻尚未設定） |
| **結論** | **資料不足，不得視為通過** |

### 測試候選地（`SITE-001`）

- 結論：**資料不足，不得視為通過**
- 三筆地界相鄰與各棟基地對應：門檻尚未設定
- 每棟最小有效面寬：parcels.PARCEL-A.frontage_mm：門檻尚未設定；parcels.PARCEL-B.frontage_mm：門檻尚未設定；parcels.PARCEL-C.frontage_mm：門檻尚未設定
- 每棟最小有效深度：parcels.PARCEL-A.depth_mm：門檻尚未設定；parcels.PARCEL-B.depth_mm：門檻尚未設定；parcels.PARCEL-C.depth_mm：門檻尚未設定
- 臨路寬度與退縮條件：門檻尚未設定
- 施工車輛與吊裝進出：門檻尚未設定
- 三棟能否各自申照與計量：門檻尚未設定
- 跨基地管線是否可行：cross_parcel_utilities.water.connectivity：門檻尚未設定；cross_parcel_utilities.water.route_rights：門檻尚未設定；cross_parcel_utilities.water.responsibility_boundary：門檻尚未設定；cross_parcel_utilities.electricity.connectivity：門檻尚未設定；cross_parcel_utilities.electricity.route_rights：門檻尚未設定；cross_parcel_utilities.electricity.responsibility_boundary：門檻尚未設定；cross_parcel_utilities.sewer_and_stormwater.connectivity：門檻尚未設定；cross_parcel_utilities.sewer_and_stormwater.route_rights：門檻尚未設定；cross_parcel_utilities.sewer_and_stormwater.responsibility_boundary：門檻尚未設定；cross_parcel_utilities.telecom.connectivity：門檻尚未設定；cross_parcel_utilities.telecom.route_rights：門檻尚未設定；cross_parcel_utilities.telecom.responsibility_boundary：門檻尚未設定
- A／B／C 核心功能能否同時容納：core_function_assessment.A：門檻尚未設定；core_function_assessment.B：門檻尚未設定；core_function_assessment.C：門檻尚未設定
- 淹水潛勢與基地標高排水：門檻尚未設定
- 土壤液化潛勢：門檻尚未設定
- 土地加基礎、管線與搬運後仍在預算內：budget_assessment.affordability：門檻尚未設定；budget_assessment.budget_limit_reviewed：門檻尚未設定；budget_assessment.land_estimate_reviewed：門檻尚未設定；budget_assessment.foundation_estimate_reviewed：門檻尚未設定；budget_assessment.utility_estimate_reviewed：門檻尚未設定；budget_assessment.handling_estimate_reviewed：門檻尚未設定

待補證據：

- 三筆地界相鄰與各棟基地對應：三筆地籍圖、地號與界址查核；須有來源、查核人與日期（建築師／地政士／測量人員）
- 每棟最小有效面寬：地籍圖或實測面寬（屋主／建築師）
- 每棟最小有效深度：地籍圖或實測深度（屋主／建築師）
- 臨路寬度與退縮條件：都發局建築線指定或地籍圖說（建築師）
- 施工車輛與吊裝進出：現勘照片與路寬、轉彎半徑、限高紀錄（屋主／營造廠）
- 三棟能否各自申照與計量：建築師書面意見（建築師／地政士）
- 跨基地管線是否可行：給水、電力、污雨排水、弱電各自的可接性、管路權利與責任分界書面查核；每個欄位皆須有來源、查核人與日期（建築師／水電／公用事業單位）
- A／B／C 核心功能能否同時容納：建築師逐棟核心機能配置評估與圖面證據；predesign envelope 只能當提問素材，不能當已確認證據（屋主／建築師）
- 淹水潛勢與基地標高排水：水利署防災資訊服務網查詢結果與雨後現勘（屋主／建築師）
- 土壤液化潛勢：土壤液化潛勢查詢系統結果；必要時由技師判斷是否需鑽探（建築師／結構技師）
- 噪音、異味、鄰房開口與西曬：三個時段的現勘紀錄（屋主）
- 土地加基礎、管線與搬運後仍在預算內：私有預算表上限與建築師／營造廠粗估（屋主／建築師）

## 四、下一步

| 類型 | 對象 | 要做的事 | 負責角色 |
|---|---|---|---|
| 設定門檻 | `SC-PARCEL-ADJACENCY` | 與建築師談定「三筆地界相鄰與各棟基地對應」的門檻值，填回 inputs/site-criteria.json | 建築師／地政士／測量人員 |
| 設定門檻 | `SC-FRONTAGE-MIN` | 與建築師談定「每棟最小有效面寬」的門檻值，填回 inputs/site-criteria.json | 屋主／建築師 |
| 設定門檻 | `SC-DEPTH-MIN` | 與建築師談定「每棟最小有效深度」的門檻值，填回 inputs/site-criteria.json | 屋主／建築師 |
| 設定門檻 | `SC-ROAD-WIDTH` | 與建築師談定「臨路寬度與退縮條件」的門檻值，填回 inputs/site-criteria.json | 建築師 |
| 設定門檻 | `SC-CONSTRUCTION-ACCESS` | 與建築師談定「施工車輛與吊裝進出」的門檻值，填回 inputs/site-criteria.json | 屋主／營造廠 |
| 設定門檻 | `SC-THREE-PERMITS` | 與建築師談定「三棟能否各自申照與計量」的門檻值，填回 inputs/site-criteria.json | 建築師／地政士 |
| 設定門檻 | `SC-CROSS-PARCEL-UTILITY` | 與建築師談定「跨基地管線是否可行」的門檻值，填回 inputs/site-criteria.json | 建築師／水電／公用事業單位 |
| 設定門檻 | `SC-CORE-FUNCTIONS` | 與建築師談定「A／B／C 核心功能能否同時容納」的門檻值，填回 inputs/site-criteria.json | 屋主／建築師 |
| 設定門檻 | `SC-FLOOD` | 與建築師談定「淹水潛勢與基地標高排水」的門檻值，填回 inputs/site-criteria.json | 屋主／建築師 |
| 設定門檻 | `SC-LIQUEFACTION` | 與建築師談定「土壤液化潛勢」的門檻值，填回 inputs/site-criteria.json | 建築師／結構技師 |
| 設定門檻 | `SC-NEIGHBOUR-ENV` | 與建築師談定「噪音、異味、鄰房開口與西曬」的門檻值，填回 inputs/site-criteria.json | 屋主 |
| 設定門檻 | `SC-TOTAL-COST` | 與建築師談定「土地加基礎、管線與搬運後仍在預算內」的門檻值，填回 inputs/site-criteria.json | 屋主／建築師 |
| 補證據 | `SITE-001 / SC-PARCEL-ADJACENCY` | 取得三筆地籍圖、地號與界址查核；須有來源、查核人與日期，補上「三筆地界相鄰與各棟基地對應」 | 建築師／地政士／測量人員 |
| 補證據 | `SITE-001 / SC-FRONTAGE-MIN` | 取得地籍圖或實測面寬，補上「每棟最小有效面寬」 | 屋主／建築師 |
| 補證據 | `SITE-001 / SC-DEPTH-MIN` | 取得地籍圖或實測深度，補上「每棟最小有效深度」 | 屋主／建築師 |
| 補證據 | `SITE-001 / SC-ROAD-WIDTH` | 取得都發局建築線指定或地籍圖說，補上「臨路寬度與退縮條件」 | 建築師 |
| 補證據 | `SITE-001 / SC-CONSTRUCTION-ACCESS` | 取得現勘照片與路寬、轉彎半徑、限高紀錄，補上「施工車輛與吊裝進出」 | 屋主／營造廠 |
| 補證據 | `SITE-001 / SC-THREE-PERMITS` | 取得建築師書面意見，補上「三棟能否各自申照與計量」 | 建築師／地政士 |
| 補證據 | `SITE-001 / SC-CROSS-PARCEL-UTILITY` | 取得給水、電力、污雨排水、弱電各自的可接性、管路權利與責任分界書面查核；每個欄位皆須有來源、查核人與日期，補上「跨基地管線是否可行」 | 建築師／水電／公用事業單位 |
| 補證據 | `SITE-001 / SC-CORE-FUNCTIONS` | 取得建築師逐棟核心機能配置評估與圖面證據；predesign envelope 只能當提問素材，不能當已確認證據，補上「A／B／C 核心功能能否同時容納」 | 屋主／建築師 |
| 補證據 | `SITE-001 / SC-FLOOD` | 取得水利署防災資訊服務網查詢結果與雨後現勘，補上「淹水潛勢與基地標高排水」 | 屋主／建築師 |
| 補證據 | `SITE-001 / SC-LIQUEFACTION` | 取得土壤液化潛勢查詢系統結果；必要時由技師判斷是否需鑽探，補上「土壤液化潛勢」 | 建築師／結構技師 |
| 補證據 | `SITE-001 / SC-NEIGHBOUR-ENV` | 取得三個時段的現勘紀錄，補上「噪音、異味、鄰房開口與西曬」 | 屋主 |
| 補證據 | `SITE-001 / SC-TOTAL-COST` | 取得私有預算表上限與建築師／營造廠粗估，補上「土地加基礎、管線與搬運後仍在預算內」 | 屋主／建築師 |

## 五、資料來源

| 檔案 | 用途 | SHA-256 |
|---|---|---|
| `inputs/project.json` | 候選土地與專案階段 | `c407735841f79c599cd087ad5a9853f1110f50652cefa93b62945addedb5f930` |
| `inputs/site-criteria.json` | 選地淘汰條件 | `89f8b97d416604d9b1cea55b1ab6fa65a743397da7bdc11ee5fee92c7c1af878` |

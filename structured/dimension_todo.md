# 待補實測尺寸清單

- Generated: `2026-08-06T04:07:03.593245+00:00`
- 已有尺寸依據: **15** / 84 格
- 仍為 auto-grid 推導（純猜測）: **69** 格
- 其中「標示面積與繪製位置衝突」: **1** 格（下方標 ⚠️）

> auto 欄位是 `scripts/annotate_html_geometry.py` 由 CSS class 推出的猜測值
> （列深度查表 1100/1200/1300/1700mm、樓層寬固定 11000mm），不是實測值。
> 量到真值後填入 `inputs/dimensions.json` 並把 `_provenance` 改成 `measured`。

⚠️ 標記的格子在 HTML 上已寫有坪數或尺寸，但那個面積放不進它被畫到的位置。
這代表**文字標示與平面配置其中一個是錯的**，不能靠推算解決，請優先實測這幾格。

## A / floor-1 1F

| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |
|---|---|---:|---:|---|---|---|---|
| `entry` | 玄關 | 3667.0 | 1300.0 | unknown |  |  |  |
| `mdf` | A-MDF 主機櫃 | 6000.0 | 1100.0 | unknown |  |  |  |
| `stair-door` | 🚪✨ 梯間隔斷門 | 5000.0 | 1100.0 | unknown |  |  |  |
| `dining` | 餐廳 | 5500.0 | 1100.0 | unknown |  |  |  |
| `bath1` | 1F 公用衛浴 | 5500.0 | 1100.0 | accessible-bath |  |  |  |
| `balcony1` | 後工作陽台 | 5500.0 | 1700.0 | unknown |  |  |  |
| `water-inlet` | 給水進線區 | 5500.0 | 1700.0 | unknown |  |  |  |

## A / floor-2 2F

| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |
|---|---|---:|---:|---|---|---|---|
| `master-bath` | 主臥衛浴 | 3667.0 | 1100.0 | unknown |  |  |  |
| `walkin` | 更衣/收納 | 5500.0 | 1300.0 | unknown |  |  |  |
| `hall2` | 🚶 走廊 | 5500.0 | 1300.0 | unknown |  |  |  |
| `study` | 書房/工作室 | 5500.0 | 800.0 | unknown |  |  |  |
| `bedroom2` | 次臥 | 5500.0 | 800.0 | unknown |  |  |  |
| `bath2` | 2F 公用衛浴 | 6000.0 | 2000.0 | unknown |  |  |  |
| `balcony2` | 高雄厝陽台 | 5000.0 | 2000.0 | unknown |  |  |  |

## A / floor-3 3F

| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |
|---|---|---:|---:|---|---|---|---|
| `guest` | 客房 | 6600.0 | 1100.0 | unknown |  |  |  |
| `bath3` | 3F 衛浴 | 4400.0 | 1100.0 | unknown |  |  |  |
| `multi` | 多功能室 | 5500.0 | 3000.0 | unknown |  |  |  |
| `stair3` | 梯間（通 RF） | 5500.0 | 2000.0 | unknown |  |  |  |
| `terrace3` | 3F 多功能小陽台 | 5500.0 | 1000.0 | unknown |  |  |  |

## A / floor-4 RF

| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |
|---|---|---:|---:|---|---|---|---|
| `riser` | 弱電立管終點/維修孔 | 11000.0 | 1100.0 | unknown |  |  |  |
| `water-tank` | 水塔 | 3667.0 | 1100.0 | unknown |  |  |  |
| `vf800` | VF800 | 3667.0 | 1100.0 | unknown |  |  |  |
| `haier` | Haier 熱泵 | 3667.0 | 1100.0 | unknown |  |  |  |
| `solar` | 太陽能設備區 | 5500.0 | 1700.0 | unknown |  |  |  |
| `laundry-rf` | RF 曬衣／設備維修平台 | 5500.0 | 1700.0 | unknown |  |  |  |

## B / floor-1 1F

| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |
|---|---|---:|---:|---|---|---|---|
| `garage` | 前院車庫 | 11000.0 | 1200.0 | unknown |  |  | ⚠️ declared 5.5m × 6.0m 超出樓層深 5300mm（y=0） |
| `shrine` | 神明廳 + 玄關 | 11000.0 | 1300.0 | shrine |  |  |  |
| `stair1` | 樓梯間 | 3667.0 | 1100.0 | unknown |  |  |  |
| `idf-cabinet` | IDF-B 機櫃 | 3667.0 | 1100.0 | unknown |  |  |  |
| `bath1` | 無障礙衛浴 | 3667.0 | 1100.0 | unknown |  |  |  |
| `storage` | 武轎儲藏室 | 5500.0 | 1700.0 | unknown |  |  |  |
| `balcony1` | 後工作陽台 | 5500.0 | 1700.0 | unknown |  |  |  |

## B / floor-2 2F

| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |
|---|---|---:|---:|---|---|---|---|
| `living2` | 家庭大客廳 | 11000.0 | 1300.0 | unknown |  |  |  |
| `stair2` | 樓梯間 | 3667.0 | 1100.0 | unknown |  |  |  |
| `bar2` | 茶水吧 | 3667.0 | 1100.0 | unknown |  |  |  |
| `bath2` | 客用衛浴 | 3667.0 | 1100.0 | unknown |  |  |  |
| `master2` | 主臥套房 | 11000.0 | 1000.0 | unknown |  |  |  |
| `balcony2` | 2F 高雄厝景觀陽臺（位置待道路側確認） | 5000.0 | 2000.0 | unknown |  |  |  |

## B / floor-3 3F

| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |
|---|---|---:|---:|---|---|---|---|
| `terrace3` | 3F 前側彈性室內區 | 11000.0 | 1200.0 | unknown |  |  |  |
| `stair3` | 樓梯間 | 5500.0 | 1300.0 | unknown |  |  |  |
| `ktv3` | 多功能娛樂室 | 5500.0 | 1300.0 | unknown |  |  |  |
| `bath3` | 3F 衛浴 | 6600.0 | 2800.0 | unknown |  |  |  |
| `guest3` | 後客房 | 4400.0 | 1800.0 | unknown |  |  |  |
| `ladder3` | 3F 後側工作小陽台＋爬梯（通RF） | 4400.0 | 1000.0 | unknown |  |  |  |

## B / floor-4 RF

| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |
|---|---|---:|---:|---|---|---|---|
| `stairRF` | 樓梯出口 | 11000.0 | 1300.0 | unknown |  |  |  |
| `tank-rf` | B 棟水塔 | 5500.0 | 1100.0 | unknown |  |  |  |
| `pump-rf` | VF800 恆壓 | 5500.0 | 1100.0 | unknown |  |  |  |
| `hotwater-rf` | Haier 熱泵熱水器 | 11000.0 | 1300.0 | unknown |  |  |  |
| `platform-rf` | 活動平台 / 曬衣棚架 | 11000.0 | 1700.0 | unknown |  |  |  |

## C / floor-1 1F

| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |
|---|---|---:|---:|---|---|---|---|
| `garage` | 前院車庫 | 11000.0 | 1200.0 | unknown |  |  |  |
| `entrance` | 玄關 | 2750.0 | 1700.0 | unknown |  |  |  |
| `sideyard` | 側院 | 2750.0 | 1700.0 | unknown |  |  |  |
| `dining` | 餐廳 | 3771.0 | 1100.0 | unknown |  |  |  |
| `kitchen` | 廚房 | 4086.0 | 1100.0 | unknown |  |  |  |
| `stair1f` | 樓梯 + IDF | 3143.0 | 1100.0 | unknown |  |  |  |
| `sliding-door` | 拉門阻隔 | 3143.0 | 1300.0 | unknown |  |  |  |
| `elder-bath` | 孝親衛浴 | 5500.0 | 1700.0 | accessible-bath |  |  |  |
| `service` | 後工作陽台 | 5500.0 | 1700.0 | unknown |  |  |  |

## C / floor-2 2F

| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |
|---|---|---:|---:|---|---|---|---|
| `balcony2f` | 2F 高雄厝景觀陽臺 | 5000.0 | 2000.0 | unknown |  |  |  |
| `stair2f` | 樓梯 | 3667.0 | 1300.0 | unknown |  |  |  |

## C / floor-3 3F

| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |
|---|---|---:|---:|---|---|---|---|
| `terrace3f` | 3F 主臥通風小陽台 | 5000.0 | 1000.0 | unknown |  |  |  |
| `stair3f` | 樓梯 | 3667.0 | 1300.0 | unknown |  |  |  |

## C / floor-4 RF

| 覆寫 key | 名稱 | auto 寬 (mm) | auto 深 (mm) | 用途 | 實測寬 | 實測深 | 備註 |
|---|---|---:|---:|---|---|---|---|
| `stair-rf` | 樓梯出口（⬇️3F） | 5500.0 | 1300.0 | unknown |  |  |  |
| `riser-rf` | 弱電預留人孔 | 5500.0 | 1300.0 | unknown |  |  |  |
| `water-tank` | 不鏽鋼水塔 | 3667.0 | 1100.0 | unknown |  |  |  |
| `pump` | 加壓系統 | 3667.0 | 1100.0 | unknown |  |  |  |
| `heatpump` | 熱泵熱水器 | 3667.0 | 1100.0 | unknown |  |  |  |
| `platform` | 活動平台 / 曬衣棚架 | 6600.0 | 1700.0 | unknown |  |  |  |
| `laundry-rf` | 曬衣區 | 4400.0 | 1700.0 | unknown |  |  |  |

# 三棟房間需求卡

草稿與屋主回覆不是需求確認、法規簽證或專業驗收。禁止填姓名、健康細節、精確預算及電腦絕對路徑。

## A.floor-1.entry · 玄關（含車庫進屋緩衝）

```json
{
  "id": "A.floor-1.entry",
  "title": "玄關（含車庫進屋緩衝）",
  "location": {
    "building_id": "A",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "6m 開間下前帶只有 2.43m 寬，玄關拿到的是車庫旁整條剩餘空間：鞋櫃＋輪椅停放位＋從車庫進屋的緩衝。Q10：鞋櫃做完之後還要留得下 150cm 迴轉圈，所以不要做滿牆大鞋櫃。",
  "constraints": {
    "target_sqm": 8.0,
    "min_sqm": 3.6,
    "band": "front",
    "light": "preferred",
    "private": false,
    "wheelchair_turn": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/0/rooms/0"
  },
  "relationships": [
    {
      "type": "no_through_view",
      "target": "A.floor-1.balcony",
      "rationale": "A 棟大門不可一眼直通後陽台（穿堂）；若用屏風遮擋，不得擋到輪椅動線。",
      "source": {
        "type": "design_request",
        "path": "inputs/design_request.md",
        "pointer": "A-Q11"
      }
    }
  ],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-1.living · 客餐廳（開放式）

```json
{
  "id": "A.floor-1.living",
  "title": "客餐廳（開放式）",
  "location": {
    "building_id": "A",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "原客廳 20 + 餐廳 11 合併。5.6m 寬的房子分兩間會變成兩條細長條，合併後在後帶是 5.6 × 3.2m 的完整方形。放在後帶而非車庫旁 —— 車庫旁只有 2.43m 寬。Q7：餐桌不正對公衛門（公衛已移到前帶最遠端）。Q9：玄關→客餐廳→孝親房不可有高低差。",
  "constraints": {
    "target_sqm": 18.0,
    "min_sqm": 18.0,
    "band": "rear",
    "light": "required",
    "private": false,
    "wheelchair_turn": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/0/rooms/1"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-1.kitchen · 廚房

```json
{
  "id": "A.floor-1.kitchen",
  "title": "廚房",
  "location": {
    "building_id": "A",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "主廚房。Q8：要能直通後陽台，不穿越孝親房。",
  "constraints": {
    "target_sqm": 6.5,
    "min_sqm": 6.0,
    "band": "rear",
    "light": "preferred",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/0/rooms/2"
  },
  "relationships": [
    {
      "type": "direct_access",
      "target": "A.floor-1.balcony",
      "must_not_pass_through": [
        "A.floor-1.elder"
      ],
      "rationale": "廚房／餐廳到後工作陽台是關鍵家務動線：要直接開門連通，不得穿越孝親房。",
      "source": {
        "type": "design_request",
        "path": "inputs/design_request.md",
        "pointer": "A-Q8"
      }
    }
  ],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-1.elder · 孝親房（原多功能房）

```json
{
  "id": "A.floor-1.elder",
  "title": "孝親房（原多功能房）",
  "location": {
    "building_id": "A",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "Q1：多功能房正式改孝親房。Q2：要放得下床＋衣櫃＋150cm 迴轉圈。",
  "constraints": {
    "target_sqm": 11.0,
    "min_sqm": 10.0,
    "band": "rear",
    "light": "required",
    "private": true,
    "door_clear_mm": 900,
    "wheelchair_turn": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/0/rooms/3"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-1.bath1 · 1F 無障礙公衛

```json
{
  "id": "A.floor-1.bath1",
  "title": "1F 無障礙公衛",
  "location": {
    "building_id": "A",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "移到前帶（車庫旁）：2.43m 淨寬放得下 150×180 迴轉圈，而且離餐桌最遠，順帶滿足 Q7 不正對餐廳。Q3 門淨寬 90cm；Q4 橫拉或外開，不要內開。比照 C 棟孝親衛浴。",
  "constraints": {
    "target_sqm": 6.5,
    "min_sqm": 4.5,
    "band": "front",
    "light": "none",
    "private": true,
    "door_clear_mm": 900,
    "door_swing": "sliding",
    "wheelchair_turn": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/0/rooms/4"
  },
  "relationships": [
    {
      "type": "not_facing",
      "target": "A.floor-1.living",
      "rationale": "公衛門不要正對餐廳；原文建議側向口袋門或側開門，並用餐邊櫃遮視線。",
      "source": {
        "type": "design_request",
        "path": "inputs/design_request.md",
        "pointer": "A-Q7"
      }
    }
  ],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-1.mdf · 樓梯下 MDF 主機櫃

```json
{
  "id": "A.floor-1.mdf",
  "title": "樓梯下 MDF 主機櫃",
  "location": {
    "building_id": "A",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "三棟中樞弱電核心，19吋機櫃落地。要散熱與除濕，不能做成密閉櫃。",
  "constraints": {
    "target_sqm": 1.5,
    "min_sqm": 1.2,
    "band": "core",
    "light": "none",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/0/rooms/5"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-1.balcony · 後工作陽台（含給水進線）

```json
{
  "id": "A.floor-1.balcony",
  "title": "後工作陽台（含給水進線）",
  "location": {
    "building_id": "A",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "原獨立的『給水進線區』1.0 m² 併入 —— 6m 開間下它被切成 467 mm 寬的細縫，而且只能從孝親房進出。總開關／減壓閥／過濾本來就是掛在後陽台牆上的壁掛設備，不需要獨立房間。洗衣、清潔、設備維修。深度要 ≥1.8 m（洗衣機 0.65 ＋ 通行 0.9 ＋ 設備牆）。Q11：大門不可直通後陽台（穿堂煞）。",
  "constraints": {
    "target_sqm": 5.0,
    "min_sqm": 4.0,
    "band": "rear",
    "light": "required",
    "private": false,
    "counts_in_footprint": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/0/rooms/6"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-2.master · 主臥室

```json
{
  "id": "A.floor-2.master",
  "title": "主臥室",
  "location": {
    "building_id": "A",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 16.0,
    "min_sqm": 12.0,
    "band": "front",
    "light": "required",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/1/rooms/0"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-2.master_bath · 主臥衛浴

```json
{
  "id": "A.floor-2.master_bath",
  "title": "主臥衛浴",
  "location": {
    "building_id": "A",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 5.0,
    "min_sqm": 3.6,
    "band": "auto",
    "light": "none",
    "private": true,
    "access_from": [
      "master"
    ]
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/1/rooms/1"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-2.closet · 更衣／收納

```json
{
  "id": "A.floor-2.closet",
  "title": "更衣／收納",
  "location": {
    "building_id": "A",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 4.0,
    "min_sqm": 2.5,
    "band": "auto",
    "light": "none",
    "private": true,
    "access_from": [
      "master"
    ]
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/1/rooms/2"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-2.study · 書房／工作室

```json
{
  "id": "A.floor-2.study",
  "title": "書房／工作室",
  "location": {
    "building_id": "A",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 9.0,
    "min_sqm": 7.0,
    "band": "auto",
    "light": "required",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/1/rooms/3"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-2.bed2 · 次臥

```json
{
  "id": "A.floor-2.bed2",
  "title": "次臥",
  "location": {
    "building_id": "A",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 11.0,
    "min_sqm": 9.0,
    "band": "rear",
    "light": "required",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/1/rooms/4"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-2.bath2 · 2F 公用衛浴

```json
{
  "id": "A.floor-2.bath2",
  "title": "2F 公用衛浴",
  "location": {
    "building_id": "A",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 4.5,
    "min_sqm": 3.2,
    "band": "auto",
    "light": "none",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/1/rooms/5"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-2.balcony2 · 高雄厝陽台（植栽區）

```json
{
  "id": "A.floor-2.balcony2",
  "title": "高雄厝陽台（植栽區）",
  "location": {
    "building_id": "A",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 5.0,
    "min_sqm": 3.0,
    "band": "rear",
    "light": "required",
    "private": false,
    "counts_in_footprint": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/1/rooms/6"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-3.media · 娛樂室／家庭劇院

```json
{
  "id": "A.floor-3.media",
  "title": "娛樂室／家庭劇院",
  "location": {
    "building_id": "A",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "design_request 第五節：長輩房與無障礙定案前，不建議先花大錢做高級影音室。",
  "constraints": {
    "target_sqm": 20.0,
    "min_sqm": 14.0,
    "band": "front",
    "light": "preferred",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/2/rooms/0"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-3.guest · 客房

```json
{
  "id": "A.floor-3.guest",
  "title": "客房",
  "location": {
    "building_id": "A",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 12.0,
    "min_sqm": 9.0,
    "band": "rear",
    "light": "required",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/2/rooms/1"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-3.bath3 · 3F 衛浴

```json
{
  "id": "A.floor-3.bath3",
  "title": "3F 衛浴",
  "location": {
    "building_id": "A",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "加水錘吸收器。",
  "constraints": {
    "target_sqm": 4.5,
    "min_sqm": 3.2,
    "band": "auto",
    "light": "none",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/2/rooms/2"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-3.multi · 多功能室

```json
{
  "id": "A.floor-3.multi",
  "title": "多功能室",
  "location": {
    "building_id": "A",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 10.0,
    "min_sqm": 7.0,
    "band": "auto",
    "light": "preferred",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/2/rooms/3"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-3.balcony3 · 3F 多功能小陽台

```json
{
  "id": "A.floor-3.balcony3",
  "title": "3F 多功能小陽台",
  "location": {
    "building_id": "A",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 4.0,
    "min_sqm": 2.5,
    "band": "rear",
    "light": "required",
    "private": false,
    "counts_in_footprint": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/2/rooms/4"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-rf.rf_stair · 梯間屋突

```json
{
  "id": "A.floor-rf.rf_stair",
  "title": "梯間屋突",
  "location": {
    "building_id": "A",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 6.0,
    "min_sqm": 4.5,
    "band": "core",
    "light": "none",
    "private": false,
    "penthouse": true,
    "penthouse_class": "enclosed"
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/3/rooms/0"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-rf.rf_tank · 水塔／VF800 加壓區

```json
{
  "id": "A.floor-rf.rf_tank",
  "title": "水塔／VF800 加壓區",
  "location": {
    "building_id": "A",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "WT-L-1000B #304 水塔＋變頻恆壓泵含旁通。載重與防颱錨定要有結構圖說（Q12）。",
  "constraints": {
    "target_sqm": 3.0,
    "min_sqm": 2.4,
    "band": "rear",
    "light": "none",
    "private": false,
    "penthouse": true,
    "penthouse_class": "tank"
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/3/rooms/1"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-rf.rf_hp · 熱泵熱水器區

```json
{
  "id": "A.floor-rf.rf_hp",
  "title": "熱泵熱水器區",
  "location": {
    "building_id": "A",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "Haier 太陽能熱泵。排風不可回吸。",
  "constraints": {
    "target_sqm": 2.5,
    "min_sqm": 2.0,
    "band": "rear",
    "light": "none",
    "private": false,
    "penthouse": true,
    "penthouse_class": "open_mep"
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/3/rooms/2"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-rf.rf_solar · 太陽能設備區

```json
{
  "id": "A.floor-rf.rf_solar",
  "title": "太陽能設備區",
  "location": {
    "building_id": "A",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 12.0,
    "min_sqm": 6.0,
    "band": "front",
    "light": "required",
    "private": false,
    "counts_in_footprint": false,
    "penthouse": false,
    "penthouse_class": "energy"
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/3/rooms/3"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## A.floor-rf.rf_deck · 曬衣／設備維修平台

```json
{
  "id": "A.floor-rf.rf_deck",
  "title": "曬衣／設備維修平台",
  "location": {
    "building_id": "A",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "design_request 第五節：RF 不建議當主要曬衣區，對照護家庭不實際。",
  "constraints": {
    "target_sqm": 16.0,
    "min_sqm": 8.0,
    "band": "auto",
    "light": "required",
    "private": false,
    "counts_in_footprint": false,
    "penthouse": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/A.json",
    "pointer": "/floors/3/rooms/4"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-1.entry_b · 玄關

```json
{
  "id": "B.floor-1.entry_b",
  "title": "玄關",
  "location": {
    "building_id": "B",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "前帶獨立玄關，先轉入走道後再到後帶神明廳；大門不直沖神桌，亦不得形成大門到後側開口的直線穿堂。",
  "constraints": {
    "target_sqm": 4.0,
    "min_sqm": 3.0,
    "band": "front",
    "light": "preferred",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/0/rooms/0"
  },
  "relationships": [
    {
      "type": "no_through_view",
      "target": "B.floor-1.balcony_b",
      "rationale": "大門到後陽台不可一眼看穿（穿堂）；原文建議半透屏風或格柵拉門，且不得擋祭祀動線。",
      "source": {
        "type": "design_request",
        "path": "inputs/design_request.md",
        "pointer": "B-Q7"
      }
    }
  ],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-1.shrine · 神明廳（核心）

```json
{
  "id": "B.floor-1.shrine",
  "title": "神明廳（核心）",
  "location": {
    "building_id": "B",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "面積 30.0 不動，但 6m 開間下必須放在走道之後的後帶 —— 車庫旁只有 2.6m 概念分格，完成面還會更窄，放不下 22 m² 的下限。改放後帶可得 5.6m 淨骨架全寬，神桌背牆是完整一面 RC 實牆。神桌背牆要 RC 實牆、上方避樑、排風獨立不與浴廁共管、補氣口不可直吹神桌。2F 衛浴與排水管不得壓到神桌 —— 這是 B 棟風水最大紅線。採光改由側面外牆取得（三棟四面皆外牆，棟距 6m）。",
  "constraints": {
    "target_sqm": 30.0,
    "min_sqm": 22.0,
    "band": "rear",
    "light": "required",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/0/rooms/1"
  },
  "relationships": [
    {
      "type": "not_stacked_under",
      "target": "B.floor-2.bath_g",
      "rationale": "神明廳上方不要有 2F 客用衛浴；至少馬桶、淋浴區與排水管不得壓在神桌正上方（風水紅線，也有漏水與濕氣風險）。",
      "source": {
        "type": "design_request",
        "path": "inputs/design_request.md",
        "pointer": "B-Q4"
      }
    },
    {
      "type": "not_stacked_under",
      "target": "B.floor-2.master_bath",
      "rationale": "神明廳上方不要有 2F 主臥衛浴；至少馬桶、淋浴區與排水管不得壓在神桌正上方。",
      "source": {
        "type": "design_request",
        "path": "inputs/design_request.md",
        "pointer": "B-Q4"
      }
    },
    {
      "type": "separate_ventilation",
      "target": "exterior",
      "rationale": "神明廳排風要 4 吋獨立直排戶外，不與浴室、廚房、ERV 共管；補氣口不可直吹神桌。",
      "source": {
        "type": "design_request",
        "path": "inputs/design_request.md",
        "pointer": "B-Q5"
      }
    }
  ],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-1.palanquin · 武轎儲藏室

```json
{
  "id": "B.floor-1.palanquin",
  "title": "武轎儲藏室",
  "location": {
    "building_id": "B",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "移到車庫旁的前帶：第一版概念淨寬 2.6m，緊鄰玄關與車庫。採 1500mm 完成面淨開口與連續直線搬運帶，武轎長向正對門洞，不在室內轉向。武轎收納外廓暫採 1200 × 1700 × 1800mm；本體、抬桿組裝外廓與操作餘量仍待實測，不能拿暫估值直接下單或施工。",
  "constraints": {
    "target_sqm": 10.5,
    "min_sqm": 9.0,
    "band": "front",
    "light": "none",
    "private": false,
    "door_clear_mm": 1500
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/0/rooms/2"
  },
  "relationships": [
    {
      "type": "transport_path",
      "target": "entry",
      "object_id": "B.palanquin.primary",
      "clear_width_mm": 1500,
      "rationale": "以武轎實際尺寸檢查從大門到武轎儲藏室的搬運路徑（原文為「大門 → 神明廳 → 儲藏室」）；整座進出時門淨寬目標 ≥150cm，轉向建議 180cm 圓徑，避免 90 度死角。",
      "source": {
        "type": "design_request",
        "path": "inputs/design_request.md",
        "pointer": "B-Q9"
      }
    }
  ],
  "physical_items": [
    {
      "id": "B.palanquin.primary",
      "label": "武轎（收納狀態）",
      "category": "ceremonial_equipment",
      "quantity": 1,
      "location": {
        "building_id": "B",
        "floor_id": "floor-1",
        "requirement_id": "B.floor-1.palanquin"
      },
      "planning_dimensions": {
        "width_mm": 1200,
        "depth_mm": 1700,
        "height_mm": 1800
      },
      "measurements": [],
      "transport": {
        "carrying_poles_removable": null,
        "assembled_dimensions": null,
        "assembled_measurement": {
          "status": "unknown",
          "value": null,
          "source": null
        },
        "route_rehearsal": {
          "status": "unknown",
          "value": null,
          "source": null
        },
        "door_clear_target_mm": 1500,
        "note": "1500 mm 是第一版規劃目標，不是由本體寬度自動推得的施工定案；抬桿與轉彎仍待實測。"
      },
      "source": {
        "type": "owner_authorized_typical_assumption",
        "note": "2026-09-09 屋主同意先採一般武轎規劃量體；1200 × 1700 mm 取自既有 storage.html 神轎預留區，1800 mm 高為前期保守暫估。"
      }
    }
  ],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-1.bath_acc · 1F 無障礙衛浴

```json
{
  "id": "B.floor-1.bath_acc",
  "title": "1F 無障礙衛浴",
  "location": {
    "building_id": "B",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "置於 y=9500..12700 中段濕式核心，完成面門淨寬概念目標 900mm，須補輪椅迴轉圖。排水立管集中服務側，不能進入 y>=12700 的神桌與神明廳後帶投影。",
  "constraints": {
    "target_sqm": 7.0,
    "min_sqm": 4.5,
    "band": "core",
    "light": "none",
    "private": true,
    "door_clear_mm": 900,
    "door_swing": "sliding",
    "wheelchair_turn": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/0/rooms/3"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-1.idf_b · IDF-B 機櫃

```json
{
  "id": "B.floor-1.idf_b",
  "title": "IDF-B 機櫃",
  "location": {
    "building_id": "B",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "接 A 棟 MDF。散熱與除濕同 A 棟原則。",
  "constraints": {
    "target_sqm": 1.5,
    "min_sqm": 1.0,
    "band": "core",
    "light": "none",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/0/rooms/4"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-1.balcony_b · 後工作陽台（水路進線點）

```json
{
  "id": "B.floor-1.balcony_b",
  "title": "後工作陽台（水路進線點）",
  "location": {
    "building_id": "B",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "置於中段服務核心並貼側外牆；玄關到神明廳以轉折走道處理。防火／隔煙門維持法定功能，裝飾拉門或屏風只能另設，不能取代。",
  "constraints": {
    "target_sqm": 5.0,
    "min_sqm": 4.0,
    "band": "core",
    "light": "required",
    "private": false,
    "counts_in_footprint": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/0/rooms/5"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-2.living_b · 家庭大客廳

```json
{
  "id": "B.floor-2.living_b",
  "title": "家庭大客廳",
  "location": {
    "building_id": "B",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 28.0,
    "min_sqm": 20.0,
    "band": "front",
    "light": "required",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/1/rooms/0"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-2.tea · 茶水吧／梯廳

```json
{
  "id": "B.floor-2.tea",
  "title": "茶水吧／梯廳",
  "location": {
    "building_id": "B",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 5.0,
    "min_sqm": 3.0,
    "band": "core",
    "light": "preferred",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/1/rooms/1"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-2.bath_g · 客用衛浴

```json
{
  "id": "B.floor-2.bath_g",
  "title": "客用衛浴",
  "location": {
    "building_id": "B",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "與主衛集中在 y<12700 的中段濕式核心，不得落在 1F 神桌或神明廳後帶正上方。",
  "constraints": {
    "target_sqm": 5.0,
    "min_sqm": 3.6,
    "band": "core",
    "light": "none",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/1/rooms/2"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-2.master_bath · 主臥衛浴

```json
{
  "id": "B.floor-2.master_bath",
  "title": "主臥衛浴",
  "location": {
    "building_id": "B",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "獨立畫成中段濕區，從主臥乾區進入；任何排水、地漏或管道間不得跨入 y>=12700 的神桌上方保護帶。",
  "constraints": {
    "target_sqm": 6.0,
    "min_sqm": 4.5,
    "band": "core",
    "light": "none",
    "private": true,
    "access_from": [
      "master_b"
    ]
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/1/rooms/3"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-2.master_b · 主臥乾區

```json
{
  "id": "B.floor-2.master_b",
  "title": "主臥乾區",
  "location": {
    "building_id": "B",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "後帶只配置床、衣櫃與梳妝等乾式機能；主衛另置中段服務核心，禁止在神桌投影上方設地漏、排水或浴廁。",
  "constraints": {
    "target_sqm": 20.0,
    "min_sqm": 14.0,
    "band": "rear",
    "light": "required",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/1/rooms/4"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-2.balcony_b2 · 2F 高雄厝景觀陽臺

```json
{
  "id": "B.floor-2.balcony_b2",
  "title": "2F 高雄厝景觀陽臺",
  "location": {
    "building_id": "B",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "概念版置於中段側外牆；最終面向與法規條件仍待道路側及基地坐向確認。",
  "constraints": {
    "target_sqm": 7.0,
    "min_sqm": 4.0,
    "band": "core",
    "light": "required",
    "private": false,
    "counts_in_footprint": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/1/rooms/5"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-3.flex_b · 前側彈性室內區

```json
{
  "id": "B.floor-3.flex_b",
  "title": "前側彈性室內區",
  "location": {
    "building_id": "B",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 14.0,
    "min_sqm": 10.0,
    "band": "front",
    "light": "required",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/2/rooms/0"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-3.ktv · 多功能娛樂室（KTV／劇院）

```json
{
  "id": "B.floor-3.ktv",
  "title": "多功能娛樂室（KTV／劇院）",
  "location": {
    "building_id": "B",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "固定於前帶，與後客房及 1F 神明廳投影分離；隔音門、浮式地坪與管線穿孔封堵需由聲學／建築專業確認。",
  "constraints": {
    "target_sqm": 20.0,
    "min_sqm": 14.0,
    "band": "front",
    "light": "preferred",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/2/rooms/1"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-3.bath_b3 · 3F 衛浴

```json
{
  "id": "B.floor-3.bath_b3",
  "title": "3F 衛浴",
  "location": {
    "building_id": "B",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "集中 y=9500..12700 服務核心並和下層濕區疊合，不跨入後帶神桌投影。",
  "constraints": {
    "target_sqm": 5.0,
    "min_sqm": 3.2,
    "band": "core",
    "light": "none",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/2/rooms/2"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-3.guest_b · 後客房

```json
{
  "id": "B.floor-3.guest_b",
  "title": "後客房",
  "location": {
    "building_id": "B",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "後帶為安靜乾式客房；KTV 留在前帶，中間以走道、樓梯與設備緩衝帶隔開。",
  "constraints": {
    "target_sqm": 12.0,
    "min_sqm": 9.0,
    "band": "rear",
    "light": "required",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/2/rooms/3"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-3.balcony_b3 · 工作小陽台

```json
{
  "id": "B.floor-3.balcony_b3",
  "title": "工作小陽台",
  "location": {
    "building_id": "B",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "只作工作陽台與立管檢修，不再承擔 RF 主要通行；3F 至 RF 改由符合正式設計的樓梯延續到屋突。",
  "constraints": {
    "target_sqm": 4.0,
    "min_sqm": 2.5,
    "band": "core",
    "light": "required",
    "private": false,
    "counts_in_footprint": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/2/rooms/4"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-rf.rf_stair · 梯間屋突

```json
{
  "id": "B.floor-rf.rf_stair",
  "title": "梯間屋突",
  "location": {
    "building_id": "B",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "3F 正式樓梯延續到 RF，不能以爬梯作日常或主要設備維修動線；樓梯尺寸、防火區劃與屋突面積待建築師確認。",
  "constraints": {
    "target_sqm": 6.0,
    "min_sqm": 4.5,
    "band": "core",
    "light": "none",
    "private": false,
    "penthouse": true,
    "penthouse_class": "enclosed"
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/3/rooms/0"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-rf.rf_tank · B 棟水塔／VF800

```json
{
  "id": "B.floor-rf.rf_tank",
  "title": "B 棟水塔／VF800",
  "location": {
    "building_id": "B",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "水塔與 VF800 集中 y=7715..10885 中段設備核心，不得進入 y>=12700 神桌上方保護帶；載重與防颱錨定須有結構正式圖說。",
  "constraints": {
    "target_sqm": 3.0,
    "min_sqm": 2.4,
    "band": "core",
    "light": "none",
    "private": false,
    "penthouse": true,
    "penthouse_class": "tank"
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/3/rooms/1"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-rf.rf_hp · 熱泵熱水器區

```json
{
  "id": "B.floor-rf.rf_hp",
  "title": "熱泵熱水器區",
  "location": {
    "building_id": "B",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "集中 y=10885..12700 中段設備核心；冷凝水接獨立間接排水／地排，不可回接生活飲用水塔。",
  "constraints": {
    "target_sqm": 2.5,
    "min_sqm": 2.0,
    "band": "core",
    "light": "none",
    "private": false,
    "penthouse": true,
    "penthouse_class": "open_mep"
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/3/rooms/2"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-rf.rf_deck · 活動平台／曬衣棚架

```json
{
  "id": "B.floor-rf.rf_deck",
  "title": "活動平台／曬衣棚架",
  "location": {
    "building_id": "B",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "日常活動集中前帶；設備維修動線與活動區分流。",
  "constraints": {
    "target_sqm": 24.0,
    "min_sqm": 10.0,
    "band": "front",
    "light": "required",
    "private": false,
    "counts_in_footprint": false,
    "penthouse": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/3/rooms/3"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## B.floor-rf.rf_shrine_buffer · 神桌上方無設備保護區

```json
{
  "id": "B.floor-rf.rf_shrine_buffer",
  "title": "神桌上方無設備保護區",
  "location": {
    "building_id": "B",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "固定 y=12700..17630。禁止水塔、泵浦、熱泵、冷氣室外機、太陽能逆變器、排水立管與其他重設備；採低活動、非日常使用，只保留必要巡檢。",
  "constraints": {
    "target_sqm": 29.5,
    "min_sqm": 20.0,
    "band": "rear",
    "light": "required",
    "private": false,
    "counts_in_footprint": false,
    "penthouse": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/B.json",
    "pointer": "/floors/3/rooms/4"
  },
  "relationships": [
    {
      "type": "stacked_over",
      "target": "B.floor-1.shrine",
      "rationale": "屋頂神桌上方保護區要落在神明廳正上方；區內不放水塔、泵浦、熱泵、冷氣室外機、逆變器與排水立管等重設備。",
      "source": {
        "type": "legacy_brief",
        "path": "inputs/brief/B.json",
        "pointer": "/floors/3/rooms/4"
      }
    }
  ],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-1.entry · 玄關（含車庫進屋緩衝）

```json
{
  "id": "C.floor-1.entry",
  "title": "玄關（含車庫進屋緩衝）",
  "location": {
    "building_id": "C",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "前帶 2.43m 寬，玄關與孝親衛浴分掉這一條。鞋櫃做完仍要留得下 150cm 迴轉圈。",
  "constraints": {
    "target_sqm": 6.5,
    "min_sqm": 3.0,
    "band": "front",
    "light": "preferred",
    "private": false,
    "wheelchair_turn": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/0/rooms/0"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-1.living · 客餐廳（開放式）

```json
{
  "id": "C.floor-1.living",
  "title": "客餐廳（開放式）",
  "location": {
    "building_id": "C",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "原客廳 20 + 餐廳 11 合併。放後帶取得 5.6m 全寬（車庫旁的前帶只有 2.43m，會變成保齡球道）。",
  "constraints": {
    "target_sqm": 18.0,
    "min_sqm": 18.0,
    "band": "rear",
    "light": "required",
    "private": false,
    "wheelchair_turn": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/0/rooms/1"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-1.kitchen · 廚房

```json
{
  "id": "C.floor-1.kitchen",
  "title": "廚房",
  "location": {
    "building_id": "C",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "要能直通後陽台，不穿越孝親房。",
  "constraints": {
    "target_sqm": 6.5,
    "min_sqm": 6.0,
    "band": "rear",
    "light": "preferred",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/0/rooms/2"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-1.elder · 孝親房／長輩房

```json
{
  "id": "C.floor-1.elder",
  "title": "孝親房／長輩房",
  "location": {
    "building_id": "C",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "門寬 ≥90cm。到浴室零高差 —— 6m 開間下浴室在走道正對面，房門與浴室門要對齊，夜間路徑是 1.2m 直線不轉折。這是 A 棟要抄的樣板。",
  "constraints": {
    "target_sqm": 11.5,
    "min_sqm": 10.0,
    "band": "rear",
    "light": "required",
    "private": true,
    "door_clear_mm": 900,
    "wheelchair_turn": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/0/rooms/3"
  },
  "relationships": [
    {
      "type": "direct_access",
      "target": "C.floor-1.elder_bath",
      "rationale": "孝親房到孝親衛浴要夜間最短、最亮、無門檻；舊概念把衛浴放在走道對面且兩門正對，照服員可從走道直接進出。",
      "source": {
        "type": "design_request",
        "path": "inputs/design_request.md",
        "pointer": "C 棟 三、3. 連續無障礙動線"
      }
    }
  ],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-1.elder_bath · 孝親衛浴

```json
{
  "id": "C.floor-1.elder_bath",
  "title": "孝親衛浴",
  "location": {
    "building_id": "C",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "6m 開間下無法維持套房內衛浴（後帶全部取 min 仍超出 2.1 m²），改放走道對面的前帶。門要與孝親房門正對。好處是照服員可從走道直接進出，不必穿越長輩臥室。150×180cm 迴轉。牆面預埋補強、緊急按鈕連動聲光＋手機推播。",
  "constraints": {
    "target_sqm": 8.0,
    "min_sqm": 4.5,
    "band": "front",
    "light": "none",
    "private": true,
    "door_clear_mm": 900,
    "door_swing": "sliding",
    "wheelchair_turn": true,
    "access_from": [
      "corridor"
    ]
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/0/rooms/4"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-1.idf_c · IDF-C 弱電機櫃

```json
{
  "id": "C.floor-1.idf_c",
  "title": "IDF-C 弱電機櫃",
  "location": {
    "building_id": "C",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "與 1F 樓梯間同區。",
  "constraints": {
    "target_sqm": 1.5,
    "min_sqm": 1.0,
    "band": "core",
    "light": "none",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/0/rooms/5"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-1.balcony · 後工作陽台

```json
{
  "id": "C.floor-1.balcony",
  "title": "後工作陽台",
  "location": {
    "building_id": "C",
    "floor_id": "floor-1"
  },
  "status": "candidate",
  "rationale": "4.0 會被切成 2900×1554（淨深不足 1500），提到 4.8 換取深度。洗衣機 0.65 ＋ 通行 0.9 是實際下限。",
  "constraints": {
    "target_sqm": 4.8,
    "min_sqm": 4.0,
    "band": "rear",
    "light": "required",
    "private": false,
    "counts_in_footprint": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/0/rooms/6"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-2.living2 · 客廳（2F 主角空間）

```json
{
  "id": "C.floor-2.living2",
  "title": "客廳（2F 主角空間）",
  "location": {
    "building_id": "C",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 22.0,
    "min_sqm": 16.0,
    "band": "front",
    "light": "required",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/1/rooms/0"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-2.guest2 · 客房／多功能房

```json
{
  "id": "C.floor-2.guest2",
  "title": "客房／多功能房",
  "location": {
    "building_id": "C",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 12.0,
    "min_sqm": 9.0,
    "band": "rear",
    "light": "required",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/1/rooms/1"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-2.kitchenette · 小型廚房

```json
{
  "id": "C.floor-2.kitchenette",
  "title": "小型廚房",
  "location": {
    "building_id": "C",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 6.0,
    "min_sqm": 4.0,
    "band": "rear",
    "light": "preferred",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/1/rooms/2"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-2.bath_c2 · 廁所（乾濕分離）

```json
{
  "id": "C.floor-2.bath_c2",
  "title": "廁所（乾濕分離）",
  "location": {
    "building_id": "C",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 5.0,
    "min_sqm": 3.6,
    "band": "auto",
    "light": "none",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/1/rooms/3"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-2.balcony_c2 · 2F 高雄厝景觀陽臺

```json
{
  "id": "C.floor-2.balcony_c2",
  "title": "2F 高雄厝景觀陽臺",
  "location": {
    "building_id": "C",
    "floor_id": "floor-2"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 7.0,
    "min_sqm": 4.0,
    "band": "rear",
    "light": "required",
    "private": false,
    "counts_in_footprint": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/1/rooms/4"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-3.master_c · 主臥室（飯店級配置）

```json
{
  "id": "C.floor-3.master_c",
  "title": "主臥室（飯店級配置）",
  "location": {
    "building_id": "C",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 20.0,
    "min_sqm": 14.0,
    "band": "front",
    "light": "required",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/2/rooms/0"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-3.gym · 運動空間

```json
{
  "id": "C.floor-3.gym",
  "title": "運動空間",
  "location": {
    "building_id": "C",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 14.0,
    "min_sqm": 9.0,
    "band": "auto",
    "light": "preferred",
    "private": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/2/rooms/1"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-3.bath_c3 · 廁所（乾濕分離）

```json
{
  "id": "C.floor-3.bath_c3",
  "title": "廁所（乾濕分離）",
  "location": {
    "building_id": "C",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 5.0,
    "min_sqm": 3.6,
    "band": "auto",
    "light": "none",
    "private": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/2/rooms/2"
  },
  "relationships": [
    {
      "type": "stacked_over",
      "target": "C.floor-2.bath_c2",
      "rationale": "2F／3F 衛浴上下對齊，讓管線合理、降低堵塞；是否列為設計凍結待屋主與建築師確認。",
      "source": {
        "type": "design_request",
        "path": "inputs/design_request.md",
        "pointer": "C-Q10"
      }
    }
  ],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-3.balcony_c3 · 3F 主臥通風小陽台

```json
{
  "id": "C.floor-3.balcony_c3",
  "title": "3F 主臥通風小陽台",
  "location": {
    "building_id": "C",
    "floor_id": "floor-3"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 4.0,
    "min_sqm": 2.5,
    "band": "rear",
    "light": "required",
    "private": false,
    "counts_in_footprint": true
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/2/rooms/3"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-rf.rf_stair · 梯間屋突

```json
{
  "id": "C.floor-rf.rf_stair",
  "title": "梯間屋突",
  "location": {
    "building_id": "C",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 6.0,
    "min_sqm": 4.5,
    "band": "core",
    "light": "none",
    "private": false,
    "penthouse": true,
    "penthouse_class": "enclosed"
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/3/rooms/0"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-rf.rf_tank · 不鏽鋼水塔／加壓 VF800

```json
{
  "id": "C.floor-rf.rf_tank",
  "title": "不鏽鋼水塔／加壓 VF800",
  "location": {
    "building_id": "C",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 3.0,
    "min_sqm": 2.4,
    "band": "rear",
    "light": "none",
    "private": false,
    "penthouse": true,
    "penthouse_class": "tank"
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/3/rooms/1"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-rf.rf_hp · 熱泵熱水器（Haier）

```json
{
  "id": "C.floor-rf.rf_hp",
  "title": "熱泵熱水器（Haier）",
  "location": {
    "building_id": "C",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 2.5,
    "min_sqm": 2.0,
    "band": "rear",
    "light": "none",
    "private": false,
    "penthouse": true,
    "penthouse_class": "open_mep"
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/3/rooms/2"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

## C.floor-rf.rf_dry · 曬衣區／活動平台

```json
{
  "id": "C.floor-rf.rf_dry",
  "title": "曬衣區／活動平台",
  "location": {
    "building_id": "C",
    "floor_id": "floor-rf"
  },
  "status": "candidate",
  "rationale": "由舊版面積 brief 匯入，尚未經屋主逐項確認。",
  "constraints": {
    "target_sqm": 24.0,
    "min_sqm": 10.0,
    "band": "auto",
    "light": "required",
    "private": false,
    "counts_in_footprint": false,
    "penthouse": false
  },
  "source": {
    "type": "legacy_brief",
    "path": "inputs/brief/C.json",
    "pointer": "/floors/3/rooms/3"
  },
  "relationships": [],
  "physical_items": [],
  "checks": [
    "此候選空間是否保留、必要性與驗收動作為何？"
  ],
  "geometry_mapping": "未建立明確需求／歷史格位對應；不得按房名猜測"
}
```

### 待填

- acceptance：________________
- cleaning：________________
- equipment：________________
- people：________________
- reference：________________
- storage：________________

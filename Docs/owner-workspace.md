# 屋主工作台：填答、量測、開會與資料查核

開啟 `structured/predesign/owner-workspace.html`，不需服務或上網。先填當期問題，再下載草稿保存；瀏覽器暫存不是備份。手機與電腦以草稿檔交換，載入前先備份目前草稿。

## 五個工作項目

- 屋主填答：當期／全部問題、棟別與樓層篩選。答案只是回覆，不自動確認或驗收。
- 房間需求卡：需求、面積假設、關係、實物及操作／收納／設備／清潔／驗收待填。歷史 HTML 家具另列，未建立明確映射不按名稱配對。
- 會議與變更：提案、屋主結論、待專業確認分開，附責任角色、期限與文件。成本、時程未知留白，不填零。
- 實物量測：收納與搬運外廓分開，各自完整寬／深／高，單位毫米；操作空間、重量、可拆部件及照片引用。新物件只建立提案。
- 已匯入紀錄：修正時新增紀錄引用舊 ID，不覆寫歷史。

頁面不讀私有家庭或預算檔。公開文字禁止填姓名、健康細節、精確預算或電腦絕對路徑。文件／照片填相對引用，不上傳附件；系統無法識別所有敏感自由文字，匯出前須自行檢查。

## 匯入答案與會議紀錄

下載檔留在專案外，先預覽：

```sh
.venv/bin/python -m house_design intake owner-records-import --file /path/to/house-owner-draft.json
# 確認預覽後才寫入：
.venv/bin/python -m house_design intake owner-records-import --file /path/to/house-owner-draft.json --apply
```

`--apply` 才追加寫入 `inputs/owner-records.json`，不改需求確認或專業驗收。正式需求確認仍用 `intake requirements-decide`；情境完成仍走防漏項證據流程。

草稿綁定公開來源與紀錄版本。來源變更、未知 ID、重複匯入、過期及格式錯誤拒絕整批。過期請保留舊草稿，重產工作台後對照答案重新審閱，不改雜湊繞過檢查。

## 正式量測另行套用

一般草稿匯入只保存量測回覆，不改實物尺寸。使用「只下載量測草稿」，確認量測者、日期、方法與引用，再執行：

```sh
.venv/bin/python -m house_design intake physical-measurements-import --file /path/to/house-measurements-draft.json
.venv/bin/python -m house_design intake physical-measurements-import --file /path/to/house-measurements-draft.json --apply
.venv/bin/python -m house_design intake validate
.venv/bin/python scripts/export_model_3d.py
.venv/bin/python -m house_design predesign consistency-review
```

只填本體時不推算搬運尺寸。裝妥抬桿的完整尺寸才存入 `transport`；舊量測與搬運版本保留。轉彎、實物演練與正式開口仍另驗收。一般估值不能當實測。

量測使來源版本改變，草稿不能重放。3D 重建後若 HTML 比例覆層過期，查核報告會指出差異；依來源更新覆層後重驗，不縮小家具或修改正式圖面掩蓋。

## 每次更新後

```sh
.venv/bin/python -m house_design predesign owner-workspace
.venv/bin/python -m house_design predesign consistency-review
.venv/bin/python -m house_design predesign risk-review
.venv/bin/python -m house_design predesign brief
.venv/bin/python -m house_design predesign meeting-pack
```

產生工作台、房間卡與量測 Markdown、JSON，及一致性 JSON／Markdown／HTML。列印只印目前頁面與篩選並展開來源細節。缺資料不算完成。

一致性分一致、矛盾、資料不足、版本過期；只比較可解析的同用途資料，不證明合規或生活好用。R000 顯示封存／現況雜湊及 Git HEAD 的候選歷史來源；不恢復工作檔、不改封存、不自動建立新圖版。

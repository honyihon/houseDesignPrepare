# R001 建築師交付包與 preflight

本專案以前身 `/mnt/d/Desktop/houseDesign` 的 `index.html`、A／B／C 三份 HTML 作為歷史房間需求參考。這四份 HTML 不是基地事實、建築師圖面或合規證據；收到正式圖面後，必須以新的不可變 revision 匯入。

目前已產生 `structured/architect_handoffs/R001/`。因土地尚未選定，這個目錄是未來交付契約與範本，不是請建築師開始定案或施工的授權。

## 1. 產生新的交付範本

```bash
.venv/bin/python -m house_design predesign brief   # 先產生 structured/predesign/design-brief.json
.venv/bin/python -m house_design drawings prepare-handoff \
  --revision R001 \
  --label "初步設計" \
  --brief structured/predesign/design-brief.json \
  --predecessor-root /mnt/d/Desktop/houseDesign
```

`--brief` 會先驗證任務書的 `brief_hash` 與其記錄的 project／requirements 雜湊；任務書被手改過、或和本包要快照的專案／需求檔案不一致時，命令會直接拒絕，不建立任何目錄。通過後包內會附上 `design-brief.snapshot.json`（原始 JSON）、`design-brief.md` 與 `design-brief.html`（由驗證過的 JSON 重新渲染），並在 manifest 的 `snapshots` 記錄雜湊。

為避免蓋掉建築師已填寫的檔案，目標目錄非空時命令會停止。需要另一版時使用 R002、R003，或先人工確認並選擇新的輸出目錄。

輸出包含：

- `README.md`、`architect-request.html`：可交付與列印的圖面需求。
- `delivery.json`：交付人、日期、檔案路徑與逐項聲明。
- `mapping.json`：座標、樓層標高、DXF layer／entity、IFC GlobalId 與設備範圍範本。
- `legacy-reference/`：完全複製的前身四份 HTML，manifest 會記錄 SHA-256。
- `project.snapshot.json`、`owner-requirements.snapshot.json`：當次公開專案與需求快照，不含私有預算或健康資料。
- `design-brief.snapshot.json`、`design-brief.md`、`design-brief.html`：經雜湊驗證的設計任務書快照（使用 `--brief` 時）。
- 任務書含防漏項清單時，會一併封存同雜湊的 `risk-review.json`、Markdown 與 HTML，保留離線連結。先執行 `predesign risk-review` 再執行 `predesign brief`；兩份資料不一致或缺清單時，交付包建立前就會停止。
- `handoff-manifest.json`：預期 A／B／C、12 個棟層與需求 id 範圍。

## 2. 建築師交回檔案

建議將同一版次的檔案放在 `incoming/`，並在 `delivery.json` 使用包內相對路徑：

```json
{
  "files": {
    "pdf": "incoming/R001.pdf",
    "ifc": "incoming/R001.ifc",
    "dxf": null,
    "mapping": "mapping.json"
  }
}
```

優先組合是 PDF＋IFC；只有 DWG 時另存 DXF 並填語意 mapping。IFC 和 DXF 可同時提供，但同一實體跨格式合併只接受明確 `ifc_guid`，不以名稱猜測。

## 3. 交回前 preflight

```bash
.venv/bin/python -m house_design drawings preflight \
  --package structured/architect_handoffs/R001 \
  --output structured/architect_handoffs/R001/preflight.json
```

preflight 會檢查：

- 所有來源都在交付包內，拒絕 `../` 或絕對路徑逸出。
- PDF 及 IFC／DXF 的檔頭與可解析性。
- 交付人、日期、棟別範圍與查核聲明。
- mapping v2、座標軸、查核證據與至少兩個共同基準點。
- A／B／C 12 個預期棟層的標高、層高與圖號證據。
- 每個預期棟層是否有可追溯空間，及 `requirement_id` 是否存在於需求快照。
- `space_block` 與更嚴格 `walkthrough` readiness。

它只在作業系統暫存目錄呼叫真正的 importer，結束後刪除 preview，不會建立或改動 `inputs/revisions/R001`。未達 `ready_for_space_block` 時 exit code 是 1，但仍先輸出完整 JSON，方便逐項補件。

## 4. 正式匯入

只有來源確定為同一版、preflight 符合本次目的，且專案階段允許時才建立不可變版次：

```bash
.venv/bin/python -m house_design drawings import \
  --revision R001 --label "初步設計" \
  --pdf structured/architect_handoffs/R001/incoming/R001.pdf \
  --ifc structured/architect_handoffs/R001/incoming/R001.ifc \
  --mapping structured/architect_handoffs/R001/mapping.json
```

接著依序執行 `drawings verify`、`drawings model3d-readiness`、`review run`。同一 revision id 永遠不能覆寫；設計方更新任何來源或 mapping，都建立下一版。

## 判定邊界

- `ready_for_import` 只表示來源與 mapping 足以正常匯入。
- `ready_for_space_block` 才能產生可追溯的現行空間量體。
- `ready_for_walkthrough` 另要求精確空間 polygon、牆、門窗高度、樓梯與設備範圍。
- `project_ready_for_design` 受土地與前期階段控制，和技術檔案 readiness 分開。
- 任何 ready 都不代替建築師、技師、地政士、主管機關或其他依法執業者的審查與簽證。

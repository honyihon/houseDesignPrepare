# House Design Prepare

這個專案現在以「未來收到建築師圖面後，可以快速、可追溯地重跑檢核」為核心。

目前土地尚未確定。目標是在高雄尋找三筆相鄰土地，A／B／C 每筆約 32 坪；這只是選地目標，不是實際基地面積，更不是每層可蓋面積。土地、地號、使用分區、道路、建蔽率、容積率與退縮未確認之前，系統只會顯示未知，不會假裝合規。

## 快速開始

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m house_design intake validate
.venv/bin/python -m house_design predesign validate
.venv/bin/python -m house_design predesign report
.venv/bin/python -m house_design review run --revision R000
```

先閱讀 `structured/predesign/report.md` 與 `Docs/predesign-owner-readiness.md`。打開 `structured/reviews/R000/index.html` 可查看離線儀表板；R000 是舊「每層 32 坪」假設的封存示範，預期會被阻擋。

收到建築師圖面後：

```bash
.venv/bin/python -m pip install -e ".[drawings]"
.venv/bin/python -m house_design drawings import \
  --revision R001 --label "初步設計" \
  --pdf path/to/drawings.pdf --ifc path/to/model.ifc
.venv/bin/python -m house_design review run --revision R001 --previous R000
```

若只有 2D CAD，請建築師將 DWG 另存 DXF，並以 `--mapping` 提供圖層到棟別、樓層、空間／門窗／設備的對應。
匯入時原始圖與 mapping 會一併複製、雜湊並鎖定在該版次；IFC 的名目門寬不會自動冒充完工淨寬。

## 資料權威順序

- `inputs/project.json`：基地事實與未知資料。
- `inputs/predesign.json`：家庭、財務、選地、設計、發包、施工與交屋階段閘門。
- `inputs/private/budget.json`：不進版控的精確預算；範本是 `inputs/budget.private.template.json`。
- `inputs/requirements.json`：屋主需求狀態與決策紀錄。
- `inputs/revisions/`：不可變 PDF／IFC／DXF 圖面版次。
- `structured/reviews/`：檢核報告、會議 PDF 與離線儀表板。
- `structured/predesign/`：前期準備報告與分層研究來源。
- `structured/parametric/`、`structured/candidates/`：歷史概念情境，不是現行基準。

任何法規、結構、消防、機電與無障礙結果都必須保留法源、證據與專業責任人；程式與 AI 不能代替依法執業者簽證。

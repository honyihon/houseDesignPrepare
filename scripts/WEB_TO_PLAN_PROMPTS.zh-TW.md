# 網頁改版 -> 真實平面圖（單一主流程版）

這份文件改為「一次貼上即可跑完整流程」：需求標準化、5 專家檢核、HTML 一致性、管線出圖、驗證與報告。

---

## 0) 先用一鍵腳本（首選）

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_full_expert_workflow.ps1 `
  -Request inputs/design_request.md `
  -Mode draft `
  -Buildings A,B,C `
  -Selection auto
```

---

## 1) Claude 主 Prompt（單次貼上）

```text
你要在 houseDesignPrepare 專案執行「A/B/C + 5 專家」全流程，並遵守以下規則：

固定角色：
1) 台灣建築法規專家（建築技術規則 / 無障礙規範）
2) 傳統風水顧問（八宅 / 玄空 / 形巒）
3) 前端工程師（React/TypeScript/Three.js/Responsive）
4) 室內設計顧問（動線/採光/通風/收納/智慧家居）
5) 專案管理專家（任務拆解/驗證點/可追蹤文件）

輸入：
- request_file: <例如 inputs/design_request.md>
- mode: <concept|draft|ifc>
- buildings: <A,B,C>
- selection: <auto|baseline|best>

流程順序（不可跳步）：
1. 需求標準化
   - python scripts/evaluate_expert_gates.py --stage normalize --request <request_file> --buildings <buildings> --mode <mode> --selection <selection>
2. 專家規則檢核（法規/無障礙硬阻擋）
   - python scripts/evaluate_expert_gates.py --stage gate --request <request_file> --buildings <buildings> --mode <mode> --selection <selection>
3. HTML 一致性檢查
   - python scripts/check_html_consistency.py --buildings <buildings> --mode <mode>
4. 主管線輸出
   - powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Mode <mode> -Selection <selection> -ValidationOwner outer
5. 品質驗證
   - python scripts/validate_layout_bundle.py
6. 匯總報告 + task-board 更新
   - python scripts/evaluate_expert_gates.py --stage report --request <request_file> --buildings <buildings> --mode <mode> --selection <selection>

硬性限制：
- 僅允許使用非 `_tmp` HTML 作為正式輸入。
- 法規/無障礙 `critical` 且有條文引用時，必須停止流程。
- `ifc` 模式必須檢查 `structured/expert_review/signoff.yaml` 且 `decision: approved`。

回報格式（固定）：
1) Hard gate: PASS/FAIL
2) Critical/Warning/Info 計數
3) 5 專家結論（每位 2-3 行）
4) score_breakdown：circulation/daylight/mep/fengshui/composite
5) pipeline_best 與 expert_best 差異樓層數
6) 輸出路徑：report.json / report.md / viewer.html / print_bundle.pdf
```

---

## 2) 失敗處理格式（固定）

若流程中斷，請強制用以下模板回報：

```text
[FAIL_STAGE]
- stage: <normalize|gate|html_consistency|pipeline|validate|report>
- reason: <一句話>
- hard_gate: <pass|fail>

[TOP_ISSUES]
1) <code> <file/floor> <evidence>
2) ...

[MIN_FIX]
1) ...
2) ...

[RETRY_COMMAND]
<可直接重跑的一行命令>
```

---

## 3) 快速實務建議

1. 每次改版前先更新 `inputs/design_request.md`。
2. `draft` 模式先跑通，再用 `ifc` 做最終放行。
3. 若只改單層，仍需跑完整 gate + consistency，再決定是否省略 PDF。

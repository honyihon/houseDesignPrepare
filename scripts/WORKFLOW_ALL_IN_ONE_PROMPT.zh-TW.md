# 一鍵全流程主 Prompt（備援）

當 `/workflow-house-all-in-one` 指令不可用時，直接貼這段給 Claude Code。

```text
你現在要執行 houseDesignPrepare 的「一鍵全流程」。

輸入：
- request_file: <請代入，例如 inputs/design_request.md>
- mode: <concept|draft|ifc>
- buildings: <A,B,C>
- selection: <auto|baseline|best>

請按以下固定順序執行，且每一步都要回報結果摘要：

1) 需求標準化
   - python scripts/evaluate_expert_gates.py --stage normalize --request <request_file> --buildings <buildings> --mode <mode> --selection <selection>

2) 專家硬性 Gate（法規/無障礙）
   - python scripts/evaluate_expert_gates.py --stage gate --request <request_file> --buildings <buildings> --mode <mode> --selection <selection>
   - 若 exit code=10 或 hard_gate=fail：停止，列出 critical_failures 與修正建議。

3) HTML 一致性檢查
   - python scripts/check_html_consistency.py --buildings <buildings>
   - 若有 critical：停止，列出檔案、樓層、證據與最小修正建議。

4) 主管線輸出
   - powershell -ExecutionPolicy Bypass -File scripts/run_full_pipeline.ps1 -Mode <mode> -Selection <selection>

5) Bundle 驗證
   - python scripts/validate_layout_bundle.py

6) 最終匯總報告 + task board 更新
   - python scripts/evaluate_expert_gates.py --stage report --request <request_file> --buildings <buildings> --mode <mode> --selection <selection>

回報格式：
- Hard gate：PASS/FAIL
- Critical / Warning / Info 數量
- score_breakdown（circulation/daylight/mep/fengshui/composite）
- expert_recommendations 中與 pipeline_best 不同的樓層數
- 產物路徑：report.json、report.md、viewer.html、print_bundle.pdf（若 mode 非 concept）

限制：
- 僅使用非 `_tmp` HTML 作為正式輸入。
- 不可省略法規條文引用欄位（source_doc/source_article/source_url）來觸發 critical gate。
- IFC 模式需檢查 structured/expert_review/signoff.yaml 且 decision=approved。
```

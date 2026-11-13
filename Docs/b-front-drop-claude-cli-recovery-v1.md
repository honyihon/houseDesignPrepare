# B落管第二輪：模型對接失敗與Opus 5.5重跑方式

2026-11-10。屋主執行的002在3.226秒結束，exit 1；stdout雖然subtype是success，is_error仍是true，API明確回報HTTP 400：`claude-fable-5-2`模型名稱不受支援。沒有response.md，沒有可交叉核對的第二輪設計回覆。失敗紀錄原樣留在私人目錄，不匯入成研究結論。

屋主接著指定 **Opus 5.5**。本次使用完整名稱`claude-opus-5-5`；已確認目前本機Claude CLI內含此名稱，但尚未驗證目前API實際可用。模型列表唯讀查詢未取得可用清單，不根據上一輪用量標籤推定實際作答模型，也不自動換機型或重試。

## 用新的獨立執行器

原[第一版腳本](../scripts/review_b_fengshui_with_claude.py)已由研究報告鎖定來源雜湊，維持原樣。[第二版](../scripts/review_b_fengshui_with_claude_v2.py)新增必填`--model`、不發出請求的`--dry-run`及安全的錯誤分類。會把指定名稱交給Claude的`--model`，不改全域設定、不加fallback；工具、MCP與hooks仍停用。每次只啟動一個CLI，逾時只停止本次程序群，不自動重跑。

依[AGENTS.md](../AGENTS.md)的資源分流，長任務請由屋主另開WSL終端執行：

```bash
cd /root/workspace/houseDesignPrepare
python3 scripts/review_b_fengshui_with_claude_v2.py \
  --brief Docs/claude-b-front-drop-followup-v2.md \
  --model claude-opus-5-5 \
  --timeout 900 \
  --output inputs/private/b-front-drop-claude-003
```

001第一輪與002失敗紀錄不覆寫；003若已非空，改用004。純檢查參數可在同一指令末尾加`--dry-run`，不建立輸出目錄、不呼叫模型；它也不代表服務已接受這個型號。若服務仍拒絕此完整名稱，保留錯誤，另從服務端模型清單核對實際ID，不自動猜其他拼法。

新執行器的result.json使用v2 schema，另列requested_model、failure_category及CLI明示的model（缺少仍為null）；不以modelUsage補猜。成功時仍只標記response-awaiting-codex-crosscheck，沒有共識或專業核可。原始stdout可能含用量／會話資料，留在私人目錄，不整份貼回或加入版控。

## 目前設計狀態

[G4／G4D／G5比較](../structured/coordination/b-front-drop-claude-v1/index.html)及[首輪交叉核對](b-front-drop-claude-crosscheck-v1.md)仍是目前研究。018交付快照記錄的是第二輪回應前的狀態；後來的002是失敗嘗試，沒有新增設計意見，不回寫舊快照或改造封印。原ABC／3D、兩種搬轎方案與149控制不改，G4D維持條件候選，不能當已採用或完成工程設計。

小範圍驗證（不呼叫外部AI）：

```bash
timeout 20s .venv/bin/ruff check scripts/review_b_fengshui_with_claude_v2.py tests/test_claude_discussion_runner_v2.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q --tb=short -p no:cacheprovider tests/test_claude_discussion_runner_v2.py tests/test_b_front_drop_claude.py
```

失敗來源、指定模型、檢查範圍與雜湊見[本輪診斷紀錄](../inputs/references/b-front-drop-claude-round2-attempt-20261110.json)。

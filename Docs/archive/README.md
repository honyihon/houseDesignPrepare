# 歷史資料與歸檔規則

現在請從[專案目前狀態](../project-status-v1.md)進入。歷史文件保留決策、面積取捨及來源，文中的「最新／passed」僅適用當時版本，不能當目前驗收。

| 歸檔 | 原位置／用途 |
| --- | --- |
| [重整前首頁](readme-before-reorganization-20261106.md) | README.md，完整舊設計入口、正式流程及歷史時間線 |
| [重整前工具手冊](scripts-readme-before-reorganization-20261106.md) | scripts/README.md，舊命令、解析格式與故障排查 |
| [重整前進度紀錄](project-status-before-reorganization-20261106.md) | Docs/project-status-v1.md，2026-11-06以前的逐輪紀錄 |
| [重整前套繪進度](coordination-review-before-reorganization-20261106.md) | Docs/coordination-review.md，舊方案進度與方法 |

原版內容亦可從Git提交81996e1恢復。此處只搬導覽的歷史內容；原JSON／HTML／SVG、比較版本、來源快照、manifest、正式圖面封存及測試樣本均留在原路徑，避免破壞引用與來源雜湊。

相同內容未必冗餘：模板與輸出檔各有角色；前後方案可有相同局部圖但不同出入路線。刪檔前先查文字引用、source_hashes、manifest、測試與生成器輸出清單，不以「很舊／重複」為理由直接刪除。

本機.claude/settings.local.json已退出版控，但現有本機檔沒有刪除；需要比對可從81996e1查看。不要將權限或私人條件重新加入Git。

# 共用洗衣到達：前側瓶頸與條件式後口

2026-11-13。承接[一樓共用洗衣預規劃](abc-ground-laundry-v1.md)，保三棟一樓共用一組、C2原機暫不用保空間、A2以上另留機位。這輪優先研究A後側能否合法平層直接進原洗衣陽台，前門協助取送備案保留；未選A為正式主位置，未改原室內分區或洗曬預留。

[開比較圖](../structured/coordination/abc-laundry-access-v1/index.html)／[前側反例](../structured/coordination/abc-laundry-access-v1/front-entry-screen.svg)／[條件式後口](../structured/coordination/abc-laundry-access-v1/rear-entry-conditional.svg)／[門片三態](../structured/coordination/abc-laundry-access-v1/rear-door-states.svg)。同三張亦附進原討論包[生活頁](../structured/planning/design-discussion-basis/life-walkthrough.html#laundry-access)，不另立屋主流程，回饋沿ABC-DAILY-CHAIN與原建商動線題。

A一樓公共乾區與廚房共邊只有1040mm；每側115mm完成預算下，樂觀剩810mm。把乾區0.364㎡三角區改標廚房，可得到約1254mm斜邊，卻不增加兩區合併可走地面。先忽略廚具、門片，只對完成邊界作900mm圓形本體中心可行域檢查，兩試點仍位於不同連通區。因此不能以斜門較長宣稱已改善照護通行。這只否決該固定房界算法，其他前側重排仍可研究；不自行縮孝親房、放棄照護通道或把未核梯下MDF當成已釋出。

後口候選在A陽台後界留1200mm名義洞，總框230mm預算後970mm，實際淨寬未知。1260×95mm上吊平移門概念向左收，2520×95mm完整移動包絡只占原名義陽台牆帶。全開時900mm試線在基地內不碰列明本體；半開與關閉會阻擋。試線有0.63㎡在基地外，故只裁切核基地內，未核門外轉向與三棟全程到達。上吊與地面無凸軌只是目標，產品、門檻、操作力、防盜、消防、風雨、遮雨及排水均待實際資料。

移動包絡到乾衣備位僅20mm、到降下衣物外廓70mm，屬模型間距，不能當產品安全距離；實際五金、接管或衣物變大就要重排。進出試線與洗／乾操作帶重疊，須先進入停妥、離開行程後再關門取放，不能一面移門一面通行。全開局部不碰不等於長輩或輪椅已能獨立操作。

先請建商核A合法後口、共同後巷權利、ABC相對位置、有效寬度、轉向、高差、遮雨與防滑。B有後巷不等於A／C都接得上。若後路不成立，家人／照服平層分戶小籃取送保留；前門仍未核全程通行。若屋主要求每位長輩自行使用且前側整體重排也無法成立，須重新比較共享位置，不能強迫走窄廚房。

上一批原小晾架容量、降下占1500mm轉位、雨天乾衣與獨排補氣、原設備完成面／完整維修、鄰孝親房噪音振動及加深灣2.232㎡廚房代價均保持。沒有縮房、減收納、改樓梯、占騎樓，B祭祀／搬轎後門預設與前門備案不改。廚房是否一定可關門的偏好尚未答覆，仍保原門，不代填選擇。

來源綁定上一批review檔案SHA-256、內容report_hash與15項來源；另核149項原配置保護、66項candidate及105項unknown。原3D、已驗四份獨立ZIP及001～044討論快照均不覆寫。19欄新實際條件保持null，空白不是0、不讀私人回覆、不自動採用。這是靜態向量與局部幾何，沒有瀏覽器、實物、法規、照護、風水或施工驗收。

```bash
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_abc_laundry_access.py
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_abc_laundry_access.py --check
timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_abc_laundry_access.py
```

先匯出本小型研究，再依序更新project-next-steps、builder-communication、design-discussion-basis。討論包接原生活頁與A1補充圖，預計交付045、下次046；同名私人快照存在就停止，不重寫。

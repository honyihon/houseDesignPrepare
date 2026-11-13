# B同版上層與收納3D比較

2026-11-12。[開B上層3D](../structured/coordination/b-upper-storage-3d-v1/index.html)／[同版平面目錄](../structured/coordination/b-upper-storage-3d-v1/plans.html)。沿已核對P4二樓、Q3三樓與RF D1／D2的完整多邊形，四版本各可切原配置／加櫃，以及收納特寫、整層、樓梯接口與俯視。

第1版TQX7gQ的96項來源相符、121檢查及16案例通過，32張截圖目視完成；發現二樓梯房間標籤沿P4寫「未改本體」，會混淆Q3上層改梯。顯示第2版只修正畫面名稱為「二樓L形到達／一樓原梯接Q3上層改梯」及標籤避讓優先，保原來源名稱供追溯，尺寸、樓板、踏步與家具不動。新畫面待另驗，不沿用第1版passed。

樓梯沿來源標高：2F +4m，3F +7m，RF +10m。二樓採L形到達，保留一樓來梯右側投影；三樓與RF沿Q3改梯踏步及平台。只畫列明到達／前室／門檻，樓板明確挖除梯井／天井，不能以整個梯核實心地面遮住下層。

只有新增櫃與尺寸相符的舊模型器具沿用概念高度／安裝標高，這不是選品或實測。未列高度的設備、桌架與機櫃仍畫平面投影；房界1100mm線框只是辨識空間的顯示標示，不代表真實牆高／厚度。沒有補造梁板、扶手或淨高核可。

二樓／三樓各450×1200×1800mm雜物櫃保原位置，RF兩版各將自己的1200×450折衣桌改900mm高下櫃工作檯，不把舊桌再畫一次。原家具與衣櫃容量保留，不侵入神桌乾背保護。原RF24㎡缺口、P4完整排水與騎樓淨高、KTV聲學／新風、法規／結構及實際門組仍待資料。

一樓後門搬轎預案與無後巷前門備案各保日常／祭祀／搬運平面，可由側欄開原同版圖。這份3D只呈現上層，不把兩個一樓混畫成新配置。原ABC主3D、A／C與已驗收獨立儲藏檢視均不修改，不沿用其passed。

本次只序列化資料、3D程式及向量副本；沒有執行完整模型生成器、瀏覽器或WebGL。小範圍檔案／語法檢查不能當新畫面已通過。實際網格三角形、櫃體本體與像素、各級踏步尺寸／標高、品名、切換及手機畫面由下列屋主驗收核對；結果仍需目視。

WSL只查檔案：

    timeout 20s env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/export_b_upper_storage_viewer.py --check
    timeout 20s node scripts/check_b_upper_storage_3d_playwright.cjs --preflight

屋主另開Windows PowerShell：

    node '\\wsl.localhost\Ubuntu\root\workspace\houseDesignPrepare\scripts\check_b_upper_storage_3d_playwright.cjs'

沿既有Edge／Playwright，不安裝或重試。開頭應顯示B upper storage display revision: 2。桌機1440×1000、手機390×844核16個樓層／狀態案例，預期32張特寫／整層／樓梯截圖；二樓另外核實際場景DOM標籤分清一樓原梯與Q3上層改梯，樓梯接口視角須有畫面內可讀的完整標籤。worker單次120秒，失敗保留當時資料，無完成結果為incomplete；沒有產品、宗教、照護、結構、消防或施工核可。

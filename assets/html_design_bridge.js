(function () {
    "use strict";

    var body = document.body;
    var buildingId = String(body.getAttribute("data-building-id") || "").toUpperCase();
    if (!/^[ABC]$/.test(buildingId)) return;

    var viewerPath = "structured/candidates/model3d.html";
    var walkthroughPath = "structured/parametric/walkthrough.html";

    function floorIdOf(element) {
        var floor = element && element.closest ? element.closest(".floor-plan") : null;
        if (!floor || !/^floor-(?:[1-4])$/.test(floor.id || "")) return "";
        return floor.id;
    }

    function viewerUrl(floorId, roomId) {
        var url = new URL(viewerPath, document.baseURI);
        var params = new URLSearchParams();
        params.set("building", buildingId);
        if (floorId) params.set("floor", floorId);
        if (roomId) params.set("room", buildingId + ":" + floorId + ":" + roomId);
        params.set("view", "plan");
        url.hash = params.toString();
        return url.href;
    }

    function link(className, text, href) {
        var anchor = document.createElement("a");
        anchor.className = className;
        anchor.textContent = text;
        anchor.href = href;
        return anchor;
    }

    function installOverview() {
        var header = document.querySelector(".container > .header");
        if (!header) return;

        var panel = document.createElement("aside");
        panel.className = "design-bridge";
        panel.setAttribute("aria-label", "原設計 HTML 與 3D 對照");

        var copy = document.createElement("div");
        copy.innerHTML =
            "<strong>原設計討論草圖 · " + buildingId + " 棟</strong>" +
            "<p>道路／前方在平面上方（y=0）。房間位置可與原設計 3D 逐格對照；尺寸多由 CSS 格位推估，非建築師圖或實測值。</p>";

        var actions = document.createElement("div");
        actions.className = "design-bridge-actions";
        actions.appendChild(link("design-bridge-link", "開啟原設計 3D", viewerUrl("", "")));
        actions.appendChild(link(
            "design-bridge-link secondary",
            "查看不同的參數化情境",
            new URL(walkthroughPath, document.baseURI).href
        ));

        panel.appendChild(copy);
        panel.appendChild(actions);
        header.insertAdjacentElement("afterend", panel);
    }

    function installFloorLinks() {
        document.querySelectorAll(".floor-plan[data-front-side]").forEach(function (floor) {
            if (!/^floor-[1-4]$/.test(floor.id || "")) return;
            var header = floor.querySelector(":scope > .floor-header");
            if (!header || header.querySelector(".design-bridge-floor-link")) return;
            header.appendChild(link("design-bridge-floor-link", "在 3D 查看本層", viewerUrl(floor.id, "")));
        });
    }

    function roomIdsFromPlan() {
        var ids = {};
        document.querySelectorAll(".plan-cell[onclick]").forEach(function (cell) {
            var match = String(cell.getAttribute("onclick") || "").match(/highlightRoom\(\s*['\"]([^'\"]+)['\"]/);
            if (!match) return;
            var floorId = floorIdOf(cell);
            if (floorId) ids[match[1]] = floorId;
        });
        return ids;
    }

    function installRoomLinks() {
        var roomFloors = roomIdsFromPlan();
        Object.keys(roomFloors).forEach(function (roomId) {
            var room = document.getElementById("room-" + roomId);
            if (!room || room.querySelector(".design-bridge-room-link")) return;
            room.appendChild(link(
                "design-bridge-room-link",
                "在原設計 3D 查看這個空間",
                viewerUrl(roomFloors[roomId], roomId)
            ));
        });
    }

    function reviewNote(parent, title, text) {
        if (!parent) return;
        var note = document.createElement("aside");
        note.className = "design-review-note";
        var heading = document.createElement("strong");
        heading.textContent = title;
        var copy = document.createElement("p");
        copy.textContent = text;
        note.appendChild(heading);
        note.appendChild(copy);
        parent.appendChild(note);
        return note;
    }

    function installReviewNotes() {
        var panel = document.querySelector(".design-bridge");
        if (!panel || panel.querySelector(".design-review-note")) return;
        var notes = {
            A: "版本差異：本 HTML 客廳與餐廳分開，需求表 A.floor-1.living 已提出後帶合併客餐廳。兩者不能視為同一版；合併配置仍待屋主確認與建築師推導。本圖可討論用途與設備，不能直接驗證房間面積或照護淨空。",
            B: "神明堂與武轎室可用來討論日常／祭拜／收納流程；150cm 開口與搬運帶、180cm 轉向空間是暫定目標，不是已驗證的武轎搬運條件。抬桿組裝外廓、實際門位、轉角、搬運人員及雨天進出仍待確認。",
            C: "孝親生活圈可用來討論照護流程，但坪數文字與示意格位尺寸尚有落差；例如兩車＋機車不能以車庫格位證明成立。衛浴需演練倒地擋門、床側轉位與照護者協助，不因標示輪椅尺寸就視為通過。"
        };
        var note = reviewNote(panel, "使用範圍與待確認事項", notes[buildingId]);
        var limitation = document.createElement("p");
        limitation.textContent = "HTML／3D 格位多為推估；坪數、設備容量、淨寬、防水與消防文字為討論條件，適用性與驗收依據須由負責專業確認。跨層外框差異或留白可能是退縮／露台等意圖，不自動判錯，也不視為已驗證。";
        note.appendChild(limitation);
        note.appendChild(link("design-bridge-link secondary", "查看資料一致性查核", new URL("structured/predesign/consistency-review.html", document.baseURI).href));
        if (buildingId === "A") {
            ["living", "dining"].forEach(function (id) {
                reviewNote(document.getElementById("room-" + id), "版本不同：不要直接套用合併客餐廳需求",
                    "此處保留原 HTML 的分開配置。需求表的後帶合併客餐廳是另一份待確認提案；位置、面積及家具不能一對一套用。討論時須先選定版本，再核對廚房至用餐區、如廁、睡眠與出入的完整一樓生活流程。此次不自動合併或搬動房間。");
            });
        }
        if (buildingId === "B") {
            reviewNote(document.getElementById("room-storage"), "搬運情境尚未驗證",
                "請沿門外 → 搬運前室 → 儲藏位置逐段確認：組裝外廓、門扇完全開啟、轉彎與搬運人員、地面高差、雨天遮蔽及臨時物品。收納尺寸不等於搬運尺寸；未有實測與正式門位前，不把 150cm／180cm 規劃目標當成通過。");
            reviewNote(document.getElementById("room-shrine"), "祭拜情境：圖面只能先討論流程",
                "分別討論日常與節慶的供桌／座位、人流、供品準備、清洗、垃圾及訪客如廁。排風補氣、用火與隔煙、防火區劃及跨層神桌保護須由相關專業確認；圖面或設備數字不能代替功能測試。");
        }
        if (buildingId === "C") {
            reviewNote(document.getElementById("room-elder"), "照護情境：待家具與完成面尺寸驗證",
                "演練床側轉位 → 夜間如廁 → 淋浴 → 回床，以及照護者協助、輔具停放、跌倒求救與救援。需核對床、扶手、門扇及設備放入後的完成面淨空；不只檢查是否畫得下輪椅圓。");
        }
    }

    function restoreRoomAnchor() {
        var match = String(location.hash || "").match(/^#room-(.+)$/);
        if (!match) return;
        var roomId = decodeURIComponent(match[1]);
        var room = document.getElementById("room-" + roomId);
        if (!room) return;
        var floorId = floorIdOf(room);
        if (floorId && typeof window.showFloor === "function") {
            window.showFloor(floorId.replace("floor-", ""));
        }
        if (typeof window.highlightRoom === "function") {
            window.highlightRoom(roomId, null);
        }
    }

    installOverview();
    installFloorLinks();
    installRoomLinks();
    installReviewNotes();
    restoreRoomAnchor();
}());

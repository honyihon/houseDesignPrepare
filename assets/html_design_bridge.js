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
    restoreRoomAnchor();
}());

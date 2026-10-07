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
        params.set("mode", "tour");
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

    function exteriorUrl() {
        var url = new URL(viewerPath, document.baseURI);
        url.hash = new URLSearchParams({mode: "tour", building: buildingId, view: "exterior", angle: "front"}).toString();
        return url.href;
    }

    function installFacadeProposal() {
        var facade = window.HOUSE_CONCEPT_LAYOUT && window.HOUSE_CONCEPT_LAYOUT.facade;
        var record = facade && facade.buildings && facade.buildings.find(function(b){return b.id===buildingId;});
        var host = document.querySelector(".design-bridge");
        if (!host || !record || document.querySelector(".shared-facade-proposal")) return;
        var panel = document.createElement("section");
        panel.className = "shared-facade-proposal";
        panel.id = "facade-proposal";
        panel.setAttribute("data-facade-id", facade.id);
        panel.setAttribute("data-facade-status", facade.status);
        panel.setAttribute("data-geometry-source", facade.geometry_source);
        var title=document.createElement("h2");title.textContent=buildingId+" 棟 · 照片風格外觀 v1";panel.appendChild(title);
        var copy=document.createElement("p");copy.textContent=record.summary+" "+record.entry;panel.appendChild(copy);
        var notice=document.createElement("p");notice.className="design-review-note";
        notice.textContent=record.parking+" 原候選開口不等於有效採光；衝突格柵／窗位不假裝已裝。深色框只是飾面概念，不是已核梁柱；屋頂不加整片棚架。";panel.appendChild(notice);
        var svgUrl=new URL("structured/candidates/furniture-plans/"+record.elevation_file,document.baseURI).href;
        var open=link("shared-facade-open", "", svgUrl);open.target="_blank";open.rel="noopener";
        var img=document.createElement("img");img.src=svgUrl;
        img.alt=buildingId+" 棟正立面提案，與3D外觀共用元件；非核准立面或施工圖";open.appendChild(img);panel.appendChild(open);
        var actions=document.createElement("div");actions.className="design-bridge-actions";
        actions.appendChild(link("design-bridge-link facade-exterior-link", "在 3D 查看完整外觀", exteriorUrl()));
        actions.appendChild(link("design-bridge-link secondary", "放大正立面", svgUrl));
        actions.appendChild(link("design-bridge-link secondary", "外觀資料與建築師清單", new URL("Docs/abc-facade-v1.md",document.baseURI).href));panel.appendChild(actions);
        var swatches=document.createElement("ul");swatches.className="facade-materials";
        Object.keys(facade.palette).forEach(function(key){
            var material=facade.palette[key], li=document.createElement("li"), swatch=document.createElement("i");
            swatch.style.backgroundColor=material.color;swatch.setAttribute("aria-hidden","true");li.appendChild(swatch);
            var text=document.createElement("span");text.textContent=material.label+" — "+material.note;li.appendChild(text);swatches.appendChild(li);
        });panel.appendChild(swatches);
        var dimensions=document.createElement("p");dimensions.textContent=facade.assumption_note;
        dimensions.setAttribute("data-facade-dimensions","assumed-not-specified");panel.appendChild(dimensions);
        var pending=document.createElement("details"),summary=document.createElement("summary");
        summary.textContent=record.pending.length+" 項開口／裝飾／維修待確認";pending.appendChild(summary);
        record.pending.forEach(function(item){var p=document.createElement("p");p.setAttribute("data-facade-pending-id",item.id);
            p.textContent=item.note+(item.issues?"（"+item.issues.join("、")+"）":"");pending.appendChild(p);});panel.appendChild(pending);
        var checklist=document.createElement("details"), checklistTitle=document.createElement("summary");
        checklistTitle.textContent="地籍出來前先保留的專業檢核";checklist.appendChild(checklistTitle);
        facade.pending_checks.forEach(function(item){var p=document.createElement("p");p.setAttribute("data-facade-check-id",item.id);
            p.textContent=item.note;checklist.appendChild(p);});panel.appendChild(checklist);
        var reference=document.createElement("details"), referenceTitle=document.createElement("summary");
        referenceTitle.textContent="屋主參考照片（只作風格）";reference.appendChild(referenceTitle);
        var photo=document.createElement("img");photo.src=new URL(facade.reference.file,document.baseURI).href;
        photo.alt=facade.reference.evidence;photo.loading="lazy";reference.appendChild(photo);panel.appendChild(reference);
        host.insertAdjacentElement("afterend",panel);
    }

    function installOverview() {
        var header = document.querySelector(".container > .header");
        if (!header) return;

        var panel = document.createElement("aside");
        panel.className = "design-bridge";
        panel.setAttribute("aria-label", "原設計 HTML 與 3D 對照");

        var copy = document.createElement("div");
        copy.innerHTML =
            "<strong>有界合理性提案 · " + buildingId + " 棟 · ABC v2</strong>" +
            "<p>道路／前方在上（y=0）。下方共用圖與 3D 同版；不再靠放大房屋或縮小家具消除衝突。6 × 17.63m 只是比較框，非地籍或可建面積。舊格子及需求卡保留作版本對照，不代表本版已容納。</p>";

        var actions = document.createElement("div");
        actions.className = "design-bridge-actions";
        actions.appendChild(link("design-bridge-link", "開啟本版 3D 提案", viewerUrl("floor-1", "")));
        if (buildingId === "A") actions.appendChild(link("design-bridge-link secondary", "在 3D 查看補回的孝親房", viewerUrl("floor-1", "flex1")));
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

    var placementIssues = {overflow: "量體越界", "furniture-overlap": "家具重疊", "operation-space": "操作空間不足",
        "door-approach": "入口暫留帶受阻", stairs: "梯段定位受阻", "unsupported-wall": "櫃背落在開口",
        window: "遮擋窗位", "transport-band": "武轎搬運帶受阻", "transport-width": "武轎寬度大於暫定搬運帶", "reference-pending": "對應沙發／床位尚待調整", circulation: "公共通行預留帶受阻", "care-route": "照護路徑受阻", "care-turn": "照護轉位預留受阻", "hvac-service": "室外機散熱／檢修預留受阻"};

    function installSharedPlans() {
        var data = window.HOUSE_CONCEPT_LAYOUT;
        var building = data && data.buildings && data.buildings.find(function (b) { return b.id === buildingId; });
        if (!building) {
            reviewNote(document.querySelector(".design-bridge"), "共用配置圖尚未產出",
                "請重新執行 scripts/export_model_3d.py，再一起交付 HTML、assets 與 structured/candidates。不得以舊格子索引代替 3D 的家具座標。");
            return;
        }
        building.floors.forEach(function (floor) {
            var host = document.getElementById(floor.id);
            var grid = host && host.querySelector(".plan-grid-visual");
            if (!grid || host.querySelector(".shared-furniture-plan")) return;
            var panel = document.createElement("section");
            panel.className = "shared-furniture-plan";
            panel.setAttribute("data-floor-id", floor.id);
            panel.setAttribute("aria-label", floor.label + " HTML 與 3D 共用家具配置");
            var heading = document.createElement("h3");
            heading.textContent = "HTML／3D 共用家具配置圖";
            panel.appendChild(heading);
            var note = document.createElement("p");
            note.textContent = "常見市售尺寸暫估，固定家具靠牆，虛線為操作／入口／設備暫留帶。固定比較框 " +
                (floor.width_mm/1000).toFixed(2) + " × " + (floor.depth_mm/1000).toFixed(2) +
                "m，不因家具變大而加深。未解家具保留原尺寸列待調整；車位、門窗、法規、實際管路與照護淨空未核定。";
            panel.appendChild(note);
            if (floor.id === "floor-1" && building.layout_review) {
                var decision = document.createElement("p");
                decision.className = "design-review-note";
                decision.setAttribute("data-parking-status", building.layout_review.parking.status);
                decision.textContent = building.layout_review.summary + " 停車：" + building.layout_review.parking.note;
                panel.appendChild(decision);
                var care = (data.layout_review.checks || []).find(function (check) { return check.id === "A-1F-care-functions"; });
                if (buildingId === "A" && care) {
                    var careNote = document.createElement("p");
                    careNote.className = "design-review-note";
                    careNote.setAttribute("data-care-function-check", care.status);
                    careNote.textContent = "A 棟孝親房已補回：正常床＋衣櫃、150cm轉位、一樓淋浴／馬桶／洗手台。主案不計車位，停車替代另列。夜間如廁：孝親房 → 公共乾區 → 一樓公衛；廚房直接通往工作陽台，不穿越臥室。" + care.note;
                    panel.appendChild(careNote);
                }
            }
            (floor.deferred_rooms || []).forEach(function (room) {
                var deferred = document.createElement("p");
                deferred.setAttribute("data-deferred-room-id", room.id);
                deferred.textContent = "未解／合併：" + room.name + " — " + room.note;
                panel.appendChild(deferred);
            });
            var svgUrl = new URL("structured/candidates/furniture-plans/" + floor.plan_file, document.baseURI).href;
            var open = link("shared-plan-open", "", svgUrl);
            open.target = "_blank";
            open.rel = "noopener";
            open.title = "開啟等比例圖，放大查看（編號對照下方清單）";
            var img = document.createElement("img");
            img.src = svgUrl;
            img.alt = buildingId + " 棟 " + floor.label + " 等比例家具、入口與樓梯定位圖；與 3D 全層導覽相同";
            img.loading = "lazy";
            open.appendChild(img);
            panel.appendChild(open);
            var actions = document.createElement("div");
            actions.className = "design-bridge-actions";
            actions.appendChild(link("design-bridge-link secondary", "放大配置圖", svgUrl));
            actions.appendChild(link("design-bridge-link", "在 3D 核對這一層", viewerUrl(floor.id, "")));
            panel.appendChild(actions);
            if (floor.frontage_study_file) {
                var frontage = floor.rooms.find(function(room){return !!room.features.frontage_study;});
                var study = frontage.features.frontage_study;
                var comparison = document.createElement("details");
                comparison.className = "frontage-study-review";
                comparison.setAttribute("data-frontage-study-status", study.status);
                var comparisonTitle = document.createElement("summary");
                comparisonTitle.textContent = "門外23.4m²：全帶暢通主案／私有庭院待核比較";
                comparison.appendChild(comparisonTitle);
                var limitation = document.createElement("p");
                limitation.textContent = study.note;
                comparison.appendChild(limitation);
                var toggleLabel = document.createElement("label");
                toggleLabel.className = "frontage-study-toggle";
                var toggle = document.createElement("input");
                toggle.type = "checkbox";
                toggle.setAttribute("data-frontage-study-toggle", frontage.id);
                toggleLabel.appendChild(toggle);
                toggleLabel.appendChild(document.createTextNode("比較私有前院虛框（未施作；不是已確認可用空間）"));
                comparison.appendChild(toggleLabel);
                var studyUrl = new URL("structured/candidates/furniture-plans/" + floor.frontage_study_file, document.baseURI).href;
                toggle.addEventListener("change", function(){
                    img.src = open.href = toggle.checked ? studyUrl : svgUrl;
                    actions.querySelector("a").href = open.href;
                    panel.setAttribute("data-frontage-study-visible", String(toggle.checked));
                });
                panel.setAttribute("data-frontage-study-visible", "false");
                study.zones.forEach(function(zone){
                    var candidate = document.createElement("p");
                    candidate.setAttribute("data-frontage-study-zone", zone.id);
                    candidate.textContent = zone.name + " " + zone.geometry.w_mm + "×" + zone.geometry.h_mm + "mm — " + zone.note;
                    comparison.appendChild(candidate);
                });
                var conditions = document.createElement("ul");
                study.conditions.forEach(function(condition){var li=document.createElement("li");li.textContent=condition;conditions.appendChild(li);});
                comparison.appendChild(conditions);
                comparison.appendChild(link("design-bridge-room-link", "在 3D 查看前緣，再勾選私有前院比較", viewerUrl(floor.id, frontage.key)));
                panel.appendChild(comparison);
            }
            var number = 0;
            floor.rooms.forEach(function (room) {
                var details = document.createElement("details");
                details.id = "proposal-room-" + room.key;
                details.setAttribute("data-model-room-id", room.id);
                if (room.requirement_id) details.setAttribute("data-requirement-id", room.requirement_id);
                var summary = document.createElement("summary");
                var pending = room.furniture.filter(function (i) { return i.placement.issues.length; });
                summary.textContent = room.name + " · " + room.furniture.length + " 件" + (pending.length ? "／" + pending.length + " 件待調整" : "") +
                    (room.features.space_group ? " · 同一梯廳分區" : "") + (room.features.access_pending ? " · 入口待配置" : "");
                details.appendChild(summary);
                if (room.features.frontage_study) {
                    var frontageNote = document.createElement("p");
                    frontageNote.textContent = room.features.frontage_study.note;
                    details.appendChild(frontageNote);
                }
                if (room.requirement_id) {
                    var requirement = document.createElement("p");
                    requirement.textContent = "需求對應：" + room.requirement_id + "。本提案外框 " +
                        (room.geometry.w_mm / 1000).toFixed(2) + " × " + (room.geometry.h_mm / 1000).toFixed(2) +
                        "m；非實測或完成面淨尺寸，原需求狀態不變。";
                    details.appendChild(requirement);
                }
                var slidingDoors = room.features.doors.filter(function (door) { return door.operation === "sliding"; });
                if (slidingDoors.length) {
                    var doorway = document.createElement("p");
                    doorway.textContent = "滑門提案：門寬暫估" + slidingDoors.map(function (door) { return door.width_mm; }).join("／") +
                        "mm，避免內開門占操作／轉位區；門框後淨寬、軌道、防水及緊急救援待核。";
                    details.appendChild(doorway);
                }
                if (pending.length) details.open = true;
                if (room.placement_note) {
                    var roomNote = document.createElement("p");
                    roomNote.textContent = room.placement_note;
                    details.appendChild(roomNote);
                }
                var ul = document.createElement("ul");
                room.furniture.forEach(function (item) {
                    number += 1;
                    var li = document.createElement("li");
                    li.setAttribute("data-furniture-id", item.id);
                    li.setAttribute("data-placement-status", item.placement.status);
                    if (item.physical_item_id) {
                        li.setAttribute("data-physical-item-id", item.physical_item_id);
                        li.setAttribute("data-measurement-state", item.physical_measurement_state);
                    }
                    li.textContent = number + ". " + item.label + " " + item.width_mm + " × " + item.depth_mm + " × " + item.height_mm + "mm" +
                        (item.placement.wall_anchor ? " · 靠牆" : " · 活動配置") +
                        (item.mount_height_mm ? " · 暫估底高 " + item.mount_height_mm + "mm" : "") +
                        (item.placement.issues.length ? " · 待調整（" + item.placement.issues.map(function(k){return placementIssues[k] || k;}).join("、") + "，未展示）" : " · 未實測") +
                        (item.note ? " · " + item.note : "");
                    ul.appendChild(li);
                });
                details.appendChild(ul);
                details.appendChild(link("design-bridge-room-link", "在 3D 核對家具", viewerUrl(floor.id, room.key)));
                panel.appendChild(details);
            });
            var hvac = data.layout_review && data.layout_review.hvac_routes || [];
            var routes = hvac.filter(function (r) { return r.indoor_room.startsWith(buildingId + ":" + floor.id + ":"); });
            if (routes.length) {
                var aircon = document.createElement("details");
                aircon.className = "hvac-route-review";
                var airconTitle = document.createElement("summary");
                airconTitle.textContent = "冷氣配對／高位配管提案（機型未選，不代表可安裝）";
                aircon.appendChild(airconTitle);
                routes.forEach(function (route) {
                    var p = document.createElement("p");
                    p.setAttribute("data-hvac-route-id", route.id);
                    p.textContent = route.id + "：" + route.indoor_room + " → " + route.outdoor_room +
                        "；折線路徑暫估 " + (route.estimated_routed_length_mm/1000).toFixed(2) + "m，高低差 " +
                        (route.elevation_difference_mm/1000).toFixed(2) + "m。原廠最短／最長配管、高低差、追加冷媒、散熱與排水皆待核。";
                    aircon.appendChild(p);
                });
                panel.appendChild(aircon);
            }
            grid.insertAdjacentElement("beforebegin", panel);
            var caption = document.createElement("p");
            caption.className = "legacy-plan-caption";
            caption.textContent = "以下是已被本版提案取代的歷史索引／需求卡；位置、車數與坪數不得直接套用。現在的配置以上方共用圖為準，未解需求沒有刪除。";
            grid.insertAdjacentElement("beforebegin", caption);
            var visual = grid.closest(".visual-plan");
            if (visual) visual.classList.add("with-shared-plan");
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

    function archiveLegacyPlans() {
        var current = window.HOUSE_CONCEPT_LAYOUT && window.HOUSE_CONCEPT_LAYOUT.buildings.find(function(b){return b.id===buildingId;});
        document.querySelectorAll(".floor-plan[id]").forEach(function (floor) {
            var content = floor.querySelector(":scope > .floor-content");
            var shared = floor.querySelector(".shared-furniture-plan");
            if (!content || !current || floor.querySelector(".legacy-layout")) return;
            var archive = document.createElement("details");
            archive.className = "legacy-layout";
            var summary = document.createElement("summary");
            summary.textContent = shared ? "展開歷史索引／原需求卡（非 ABC v2 的現在位置或容量）" : "展開歷史系統／需求筆記（未施工，設備位置及驗收數字未核定）";
            archive.appendChild(summary);
            if(shared) content.insertAdjacentElement("beforebegin", shared);
            content.insertAdjacentElement("beforebegin", archive);
            archive.appendChild(content);
            var oldHeader = floor.querySelector(":scope > .floor-header");
            if(oldHeader){
                var newHeader=document.createElement("div");newHeader.className="floor-header proposal-floor-header";
                var title=document.createElement("h2");title.className="floor-title";
                var record=current.floors.find(function(f){return f.id===floor.id;});
                title.textContent=record?buildingId+" 棟 "+record.label+" · ABC v2 有界提案":"歷史系統與需求參考（非現場使用指南）";
                newHeader.appendChild(title);
                var floorLink=oldHeader.querySelector(".design-bridge-floor-link");
                if(floorLink)newHeader.appendChild(floorLink);
                oldHeader.insertAdjacentElement("beforebegin",newHeader);
                archive.appendChild(oldHeader);
            }
            floor.querySelectorAll(":scope > .orientation-info, :scope > .direction-grid").forEach(function(node){archive.appendChild(node);});
            if(!shared)reviewNote(newHeader,"現在配置請看 1F／2F／3F／RF 共用圖",current.layout_review.summary+" 原位置、車數與坪數是歷史版本，未經確認不能當現況。" );
        });
    }

    function archiveTopMetadata() {
        var oldHeader=document.querySelector(".container > .header");
        var bridge=document.querySelector(".design-bridge");
        if(!oldHeader || !bridge || document.querySelector(".legacy-metadata"))return;
        var archive=document.createElement("details");archive.className="legacy-layout legacy-metadata";
        var summary=document.createElement("summary");summary.textContent="歷史版本標題／統計（舊坪數、設備位置及收納容量，不是本版承諾）";
        archive.appendChild(summary);
        var header=document.createElement("div");header.className="header proposal-header";
        var title=document.createElement("h1");title.textContent=buildingId+" 棟 · ABC v2 合理性提案";header.appendChild(title);
        var note=document.createElement("p");note.textContent="與 3D 共用有界初排；基地、完成面、法規及屋主取捨未核定。";header.appendChild(note);
        oldHeader.insertAdjacentElement("beforebegin",header);
        bridge.insertAdjacentElement("afterend",archive);
        archive.appendChild(oldHeader);
        var stats=document.querySelector(".container > .stats-bar");
        if(stats)archive.appendChild(stats);
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
        var current = window.HOUSE_CONCEPT_LAYOUT && window.HOUSE_CONCEPT_LAYOUT.buildings.find(function (b) { return b.id === buildingId; });
        if (current && current.layout_review) {
            reviewNote(panel, "本版優先順序（待屋主及建築師確認）", current.layout_review.summary);
            current.layout_review.assumptions.concat(current.layout_review.deferred.map(function(d){return d.note;})).forEach(function(text){
                reviewNote(panel, "假設／未解需求", text);
            });
            return;
        }
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
        var proposal = String(location.hash || "").match(/^#proposal-room-(.+)$/);
        if (proposal) {
            var target = document.getElementById("proposal-room-" + decodeURIComponent(proposal[1]));
            if (target) {
                var proposalFloor = floorIdOf(target);
                if (proposalFloor && typeof window.showFloor === "function") window.showFloor(proposalFloor.replace("floor-", ""));
                target.open = true;
                target.scrollIntoView({block: "start"});
            }
            return;
        }
        var match = String(location.hash || "").match(/^#room-(.+)$/);
        if (!match) return;
        var roomId = decodeURIComponent(match[1]);
        var room = document.getElementById("room-" + roomId);
        if (!room) return;
        var archive = room.closest(".legacy-layout");
        if (archive) archive.open = true;
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
    installSharedPlans();
    archiveLegacyPlans();
    archiveTopMetadata();
    installFacadeProposal();
    installRoomLinks();
    installReviewNotes();
    restoreRoomAnchor();
}());

  // Local B32 presentation policy only. Never rewrite DATA, geometry, access
  // flags, furniture visibility or professional/transport review outcomes.
  function b32EntryDescription(cell, features) {
    var valid=function(opening){return opening && Number.isFinite(opening.width_mm) && opening.width_mm>0 &&
      Number.isFinite(opening.ratio) && ["front","rear","left","right"].indexOf(opening.face)>=0;};
    if((features.doors || []).some(valid))return "已排門位，通行未核";
    if((features.open_connections || []).some(valid))return "已排開口，通行未核";
    return cell.is_outdoor ? "戶外範圍／使用權利未核" : "入口資料不足，仍待配置";
  }
  function b32RoomText(cell, features) {
    return cell.name+(features.access_pending ? " · "+b32EntryDescription(cell,features) : "");
  }
  function b32ShortRoomText(cell) {
    var names={garage:"騎樓／前通行帶",stair1:"樓梯（待核）",shrine:"神明堂",storage:"武轎庫",
      "rear-bath":"後右公衛","laundry-base":"家務區"};
    return names[cell.key] || cell.name.split(/[（｜]/)[0].slice(0,12);
  }
  function b32LabelPolicy(entry, context) {
    if(context.mode==="all")return true;
    if(context.focused || entry.kind!=="room")return false;
    var cell=entry.mesh.userData.cell;
    if(context.selected===cell.id)return true;
    if(entry.mesh.userData.floor.id==="floor-1") {
      var keys=context.width<=860 ? ["stair1","shrine","storage","rear-bath"] :
        ["garage","stair1","shrine","storage","rear-bath","laundry-base"];
      return keys.indexOf(cell.key)>=0;
    }
    return ["stair","bedroom","bath"].indexOf(cell.kind)>=0;
  }
  function b32DisplayContext() {
    return {mode:document.getElementById("b32-label-mode").value,
      focused:roomCameraFocused && presentation==="tour",selected:viewState.room,width:stage.clientWidth};
  }
  function b32LabelLimit(context) { return context.mode==="all" ? Infinity : context.width<=860 ? 4 : 6; }
  function b32SyncRoomReadout() {
    var mesh=viewState.room && meshById[viewState.room],status=document.getElementById("b32-room-entry-status");
    status.hidden=!mesh;
    status.textContent=mesh ? "入口："+b32EntryDescription(mesh.userData.cell,featuresOf(mesh.userData.cell))+
      "。門組、完成面淨寬、門檻、家規、照護救援與消防仍待核；有門位不等於核准通行。" : "";
  }
  function b32DisplayEvidence() {
    return {revision:2,mode:document.getElementById("b32-label-mode").value,
      focused:roomCameraFocused && presentation==="tour",
      entry:document.getElementById("b32-room-entry-status").textContent,
      limitation:"display-only; openings and all access/transport/approval flags unchanged"};
  }
  var b32LabelMode=document.getElementById("b32-label-mode");
  b32LabelMode.value=new URL(location.href).searchParams.get("labels")==="all"?"all":"compact";
  function b32SyncDensityControl() {
    document.body.dataset.b32LabelMode=b32LabelMode.value;
    document.getElementById("furniture-names").disabled=facadeIsActive() || b32LabelMode.value!=="all";
  }
  b32SyncDensityControl();
  b32LabelMode.addEventListener("change",function(){
    b32SyncDensityControl();
    var next=new URL(location.href);next.searchParams.set("labels",b32LabelMode.value);history.replaceState(null,"",next.href);
  });
  document.getElementById("b32-room-details").addEventListener("click",function(){
    var toggle=document.getElementById("mobile-panel-toggle");
    if(document.getElementById("app").classList.contains("panel-collapsed"))toggle.click();
    b32SyncRoomReadout();
    window.requestAnimationFrame(function(){
      var target=document.getElementById("b32-room-details-panel"),panel=document.getElementById("panel");
      var top=target.getBoundingClientRect().top-panel.getBoundingClientRect().top+panel.scrollTop;
      panel.scrollTop=Math.max(0,top-58);
      document.getElementById("b32-details-back").focus({preventScroll:true});
    });
  });
  document.getElementById("b32-details-back").addEventListener("click",function(){
    var toggle=document.getElementById("mobile-panel-toggle");
    if(window.matchMedia("(max-width:860px)").matches && !document.getElementById("app").classList.contains("panel-collapsed"))toggle.click();
    document.getElementById("b32-room-details").focus({preventScroll:true});
  });

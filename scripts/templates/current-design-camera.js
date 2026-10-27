  // Current discussion viewer only. Fit real room/product bounds; never change
  // model coordinates, furniture dimensions, scene visibility or adoption flags.
  function basisBodyPixelBudget(item) {
    if (["bed","sofa","clothes-rack","treadmill","altar"].indexOf(item.shape)>=0) {
      return {short:40,long:96};
    }
    if (item.catalog_id==="washer" || item.catalog_id==="utility-sink-planning") {
      return {short:32,long:48};
    }
    if (["toilet","vanity","shower"].indexOf(item.shape)>=0) { return {short:32,long:64}; }
    return {short:16,long:28};
  }
  function basisChooseRoomFrame(box,area,width,height,fov,bodies,baseline) {
    if (!bodies.length || !area.usable) { return {frame:baseline,score:null,baselineScore:null}; }
    function score(frame) {
      return Math.min.apply(null,bodies.map(function(body){
        var r=frameBodyRect(body.box,frame,width,height),w=r.right-r.left,h=r.bottom-r.top;
        return Math.min(Math.min(w,h)/body.budget.short,Math.max(w,h)/body.budget.long);
      }));
    }
    var best=baseline,original=score(baseline),bestScore=original;
    [0,.2,-.2,.6,-.6,1.2,-1.2].forEach(function(theta){
      [.25,.45,.65,.85,1].forEach(function(phi){
        var candidate=cameraFrameForBox(box,area,width,height,theta,phi,fov),value=score(candidate);
        if (value>bestScore+.001) { best=candidate;bestScore=value; }
      });
    });
    return {frame:best,score:bestScore,baselineScore:original};
  }
  function basisMobileCloseup() {
    return !!(DATA.source && DATA.source.current_design_basis) && presentation==="tour" &&
      roomCameraFocused && !!viewState.room && stage.clientWidth<=860 && !facadeIsActive();
  }
  var basisLastDraw=null,basisResizePending=false,basisResizeObserver=null;
  function basisRenderFrame() {
    var width=stage.clientWidth,height=stage.clientHeight,area=cameraViewportRect();
    var clipped=basisMobileCloseup() && area.usable;
    // Three's scissor uses logical pixels and a bottom-left origin. Clear the
    // entire canvas before rendering inside the measured text-free rectangle,
    // otherwise old whole-floor pixels survive when switching to a closeup.
    renderer.setScissorTest(false);
    if (clipped) {
      var left=Math.ceil(area.left),right=Math.floor(area.right),top=Math.ceil(area.top),bottom=Math.floor(area.bottom);
      renderer.clear();
      renderer.setScissor(left,height-bottom,right-left,bottom-top);
      renderer.setScissorTest(true);
    }
    try { renderer.render(scene,camera); }
    finally { renderer.setScissorTest(false); }
    var size=renderer.getSize(new THREE.Vector2());
    basisLastDraw={clipped:clipped,area:clipped?{left:left,right:right,top:top,bottom:bottom}:null,
      stage:{width:width,height:height},renderSize:{width:size.x,height:size.y},clearedOutside:clipped};
  }
  function basisCameraEvidence() {
    return {revision:2,policy:"current-design-readable-v2",lastDraw:basisLastDraw,
      scissorTestRestored:renderer.getScissorTest()===false};
  }
  function basisScheduleResize() {
    if (basisResizePending) { return; }
    basisResizePending=true;
    window.requestAnimationFrame(function(){basisResizePending=false;resize();});
  }
  function basisObserveViewport() {
    if (typeof ResizeObserver!=="function") { return; }
    // The panel changes the stage without a window resize. Text can also wrap
    // after room selection, font loading or opening the equipment list.
    basisResizeObserver=new ResizeObserver(basisScheduleResize);
    [stage,"stage-title","room-view-actions","study-stage-note","orientation","compass"].forEach(function(value){
      var element=typeof value==="string"?document.getElementById(value):value;
      if (element) { basisResizeObserver.observe(element); }
    });
  }

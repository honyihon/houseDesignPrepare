  // Bath page only. A thin wall-hung basin and an open shower floor must be
  // framed from their real meshes, never from the empty nominal product box.
  function bathChooseRoomFrame(box,area,width,height,fov,bodies,baseline) {
    var original=basisChooseRoomFrame(box,area,width,height,fov,bodies,baseline);
    if (!bodies.length || !area.usable) { return original; }
    function score(frame) {
      return Math.min.apply(null,bodies.map(function(body){
        var r=frameBodyRect(body.box,frame,width,height),w=r.right-r.left,h=r.bottom-r.top;
        return Math.min(Math.min(w,h)/body.budget.short,Math.max(w,h)/body.budget.long);
      }));
    }
    var best=original.frame,bestScore=original.score;
    // A small, deterministic camera-only search on focus/resize, not a render
    // loop, scene rebuild or retry. Retain full room bounds and all furniture.
    [0,.2,-.2,.6,-.6,1.2,-1.2,1.6,-1.6,2.2,-2.2,Math.PI].forEach(function(theta){
      [.1,.25,.45,.65,.85,1,1.2,1.35,1.4,1.45].forEach(function(phi){
        var candidate=cameraFrameForBox(box,area,width,height,theta,phi,fov),value=score(candidate);
        if (value>bestScore+.001) { best=candidate;bestScore=value; }
      });
    });
    return {frame:best,score:bestScore,baselineScore:original.baselineScore};
  }
  function bathSyncRoomTitle(mesh,name) {
    var title=document.getElementById("stage-title");
    title.title=name;
    // Keep the full room name in its tooltip, sidebar and equipment list. The
    // mobile drawing needs space below the real, measured controls, not text
    // squeezed over a small basin. No room/product dimensions are changed.
    if (!mesh || mesh.userData.cell.key!=="elder-bath" || stage.clientWidth>860 || presentation!=="tour") { return; }
    title.textContent="C 棟 · 1F · 孝親套衛比較";
    var small=document.createElement("small");
    small.textContent="本房3件原尺寸設備 · 未採用／專業未核";
    title.appendChild(small);
  }

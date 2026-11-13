  // Runs only inside the new A/C comparison copy; original viewer is untouched.
  var acStorageCases=study.storage_cases.filter(function(c){return c.option===studyChoice.id;});
  var acStorageFocusPending=false,acStorageLastDrawStamp=null;
  function acStorageCase(){
    return acStorageCases && acStorageCases.find(function(c){return c.floor===viewState.floor;});
  }
  function acStorageViewStamp(){
    var a=cameraViewportRect();
    return JSON.stringify({stage:[stage.clientWidth,stage.clientHeight],area:[a.left,a.right,a.top,a.bottom],
      position:camera.position.toArray(),rotation:camera.quaternion.toArray(),projection:Array.from(camera.projectionMatrix.elements),
      scope:[viewState.building,viewState.floor,viewState.room,roomCameraFocused],
      names:document.getElementById("furniture-names").checked,labels:document.getElementById("b32-label-mode").value});
  }
  function acStorageFrameReady(){
    var stamp=acStorageViewStamp(),matches=acStorageLastDrawStamp===stamp;
    var sizeMatches=!!basisLastDraw&&basisLastDraw.renderSize.width===stage.clientWidth&&basisLastDraw.renderSize.height===stage.clientHeight;
    return {ready:!acStorageFocusPending&&!basisResizePending&&matches&&sizeMatches,resizePending:basisResizePending,
      drawMatchesCurrent:matches,renderSizeMatches:sizeMatches,lastDraw:basisLastDraw,stamp:stamp,lastDrawStamp:acStorageLastDrawStamp};
  }
  function acStorageReadout(){
    if(!acStorageCases)return;
    var c=acStorageCase(),selected=useChoice.id==="storage",text=c
      ?c.case+"｜"+c.label+"｜"+c.rect_mm[2]+"×"+c.rect_mm[3]+"×"+c.height_mm+"mm"
      :studyChoice.building+(viewState.floor?"棟1F｜沿原配置，本輪不加櫃":"棟全棟概覽｜選樓層看各層收納");
    var readout=document.getElementById("ac-storage-readout");if(readout)readout.textContent=text;
    var floorSelect=document.getElementById("ac-storage-floor");if(floorSelect)floorSelect.value=viewState.floor||"";
    var focus=document.getElementById("ac-storage-focus");if(focus){focus.disabled=!c;focus.textContent=selected?"看新增櫃體":"看預計加櫃位置";}
    document.getElementById("study-stage-note").textContent=(selected?"加櫃比較":"原配置對照")+" · 未採用｜"+text;
    document.getElementById("study-plan-link").href=viewState.floor?studyChoice.id+"_"+useChoice.id+"_"+viewState.floor+".svg":"plans.html";
  }
  function acStorageCollapsePanel(){
    if(innerWidth>860)return;
    document.getElementById("app").classList.add("panel-collapsed");
    var button=document.getElementById("mobile-panel-toggle");button.setAttribute("aria-expanded","false");button.textContent="展開控制";
  }
  function acStorageSourceBox(c){
    var host=meshById[c.host_room_id],base=host.userData.floor.base_mm,r=c.rect_mm;
    host.parent.updateWorldMatrix(true,false);
    return new THREE.Box3(new THREE.Vector3(r[0]*MM,base*MM,-(r[1]+r[3])*MM),
      new THREE.Vector3((r[0]+r[2])*MM,(base+c.height_mm)*MM,-r[1]*MM)).applyMatrix4(host.parent.matrixWorld);
  }
  function acStorageFrameCabinet(c){
    if(acStorageCase()!==c)return;
    scene.updateMatrixWorld(true);
    var entry=furnitureById[c.proposed_item_id],box=entry?new THREE.Box3().setFromObject(entry.group):acStorageSourceBox(c);
    box.expandByScalar(.4);frameLighting(box);
    var area=cameraViewportRect(),frame=cameraFrameForBox(box,area,stage.clientWidth,stage.clientHeight,
      c.rect_mm[2]<c.rect_mm[3]?-0.65:0.65,.95,camera.fov);
    spherical.theta=frame.theta;spherical.phi=frame.phi;spherical.radius=frame.radius;target.copy(frame.target);
    cameraFitState={area:area,theta:frame.theta,phi:frame.phi,radius:frame.radius,closeupPolicy:"ac-storage-body-v1"};
    updateCamera();positionFurnitureLabels();
  }
  function acStorageResize(){
    acStorageFocusPending=true;
    try{
      resize();
      var c=acStorageCase();
      if(c&&roomCameraFocused&&viewState.room===c.host_room_id&&new URL(location.href).searchParams.get("cabinet")==="1"){
        // Resize and cabinet fitting share one callback: never draw the generic
        // whole-room fit while waiting for another animation frame.
        acStorageFrameCabinet(c);
      }
    }finally{
      acStorageFocusPending=false;
    }
  }
  function acStorageFocus(){
    var c=acStorageCase();if(!c)return;
    acStorageFocusPending=true;
    setScope(studyChoice.building,c.floor,c.host_room_id,true,false);
    roomCameraFocused=true;viewState.view="front";selectedFurniture=useChoice.id==="storage"?c.proposed_item_id:"";
    acStorageCollapsePanel();
    requestAnimationFrame(function(){
      resize();applyViewPreset("front",false);acStorageFrameCabinet(c);writeHash();
      var url=new URL(location.href);url.searchParams.set("cabinet","1");history.replaceState(null,"",url.href);
      furnitureEntries.forEach(styleFurniture);renderFurnitureList();positionFurnitureLabels();acStorageReadout();
      acStorageFocusPending=false;
    });
  }
  function acStorageFloorView(){
    var floor=viewState.floor||"floor-2";
    acStorageFocusPending=true;
    roomCameraFocused=false;acStorageCollapsePanel();setScope(studyChoice.building,floor,"",true,true);
    var url=new URL(location.href);url.searchParams.delete("cabinet");history.replaceState(null,"",url.href);
    requestAnimationFrame(function(){
      try{resize();applyViewPreset("front",false);acStorageReadout();}
      finally{acStorageFocusPending=false;}
    });
  }
  function acStoragePixels(projected){
    var gl=renderer.getContext(),sx=canvas.width/stage.clientWidth,sy=canvas.height/stage.clientHeight;
    var x=Math.max(0,Math.floor(projected.left*sx)),top=Math.max(0,Math.floor(projected.top*sy));
    var right=Math.min(canvas.width,Math.ceil(projected.right*sx)),bottom=Math.min(canvas.height,Math.ceil(projected.bottom*sy));
    var w=right-x,h=bottom-top;if(w<=0||h<=0)return {sampled:0,orange:0,ratio:0};
    var bytes=new Uint8Array(w*h*4);gl.readPixels(x,canvas.height-bottom,w,h,gl.RGBA,gl.UNSIGNED_BYTE,bytes);
    var stride=Math.max(1,Math.ceil(Math.max(w,h)/200)),sampled=0,orange=0;
    for(var row=0;row<h;row+=stride)for(var col=0;col<w;col+=stride){
      var i=(row*w+col)*4,r=bytes[i],g=bytes[i+1],b=bytes[i+2];sampled++;
      if(bytes[i+3]>0&&r>110&&g>55&&r>g*1.12&&g>b*1.35&&r-b>65)orange++;
    }
    return {method:"webgl-readPixels-cabinet-aabb",sampled:sampled,orange:orange,ratio:sampled?orange/sampled:0};
  }
  function acStorageEvidence(pixels){
    var names=document.getElementById("furniture-names");
    var c=acStorageCase(),entry=c&&furnitureById[c.proposed_item_id],result={
      schema:"house-ac-storage-runtime-v1",reportHash:study.report_hash,displayRevision:study.display_revision,option:studyChoice.id,use:useChoice.id,
      floor:viewState.floor,caseId:c?c.case:null,present:!!entry,focusPending:acStorageFocusPending,frame:acStorageFrameReady(),
      newItems:furnitureEntries.filter(function(e){return !!e.item.storage_case;}).map(function(e){return e.item.id;}),
      fullNames:acStorageCases.map(function(i){return i.label;}),webglLost:rendererContextLost,
      sourceNote:c?c.note:null,labelMode:document.getElementById("b32-label-mode").value,
      furnitureNames:{checked:names.checked,disabled:names.disabled,
        visibleLabels:Array.from(document.querySelectorAll("#furniture-labels [data-furniture-label]")).filter(function(el){
          return !el.hidden&&getComputedStyle(el).display!=="none";
        }).map(function(el){return {id:el.getAttribute("data-furniture-label"),text:el.textContent};})}};
    if(!entry)return result;
    entry.group.updateWorldMatrix(true,true);
    var inverse=new THREE.Matrix4().copy(entry.group.parent.matrixWorld).invert(),local=new THREE.Box3();
    entry.parts.forEach(function(part){
      part.mesh.geometry.computeBoundingBox();
      var transform=new THREE.Matrix4().multiplyMatrices(inverse,part.mesh.matrixWorld);
      local.union(part.mesh.geometry.boundingBox.clone().applyMatrix4(transform));
    });
    var box=new THREE.Box3().setFromObject(entry.group),points=boxCorners(box).map(function(p){return p.project(camera);});
    var left=Math.min.apply(null,points.map(function(p){return(p.x+1)*stage.clientWidth/2;}));
    var right=Math.max.apply(null,points.map(function(p){return(p.x+1)*stage.clientWidth/2;}));
    var top=Math.min.apply(null,points.map(function(p){return(1-p.y)*stage.clientHeight/2;}));
    var bottom=Math.max.apply(null,points.map(function(p){return(1-p.y)*stage.clientHeight/2;}));
    result.actualRectMm=[local.min.x/MM,-local.max.z/MM,(local.max.x-local.min.x)/MM,(local.max.z-local.min.z)/MM];
    result.actualBottomMm=local.min.y/MM;result.actualTopMm=local.max.y/MM;
    result.actualHeightMm=(local.max.y-local.min.y)/MM;result.visible=entry.group.visible&&entry.group.parent.visible;
    result.overflow=entry.overflow;result.collision=entry.collision;
    result.projected={left:left,right:right,top:top,bottom:bottom,width:right-left,height:bottom-top,
      inFront:points.every(function(p){return p.z>=-1&&p.z<=1;})};
    result.safeArea=cameraViewportRect();result.stage={width:stage.clientWidth,height:stage.clientHeight};
    result.pixels=pixels?acStoragePixels(result.projected):null;
    return result;
  }
  window.__AC_STORAGE_QA__=acStorageEvidence;
  function acStorageInit(){
    FURNITURE_BASIS_LABEL["owner-storage-proposal"]="屋主收納提案";
    document.getElementById("furniture-names").setAttribute("aria-describedby","ac-name-help");
    var selector=document.getElementById("ac-storage-floor");
    var overview=document.createElement("option");overview.value="";overview.textContent="全棟概覽（選樓層看收納）";selector.appendChild(overview);
    DATA.buildings[0].floors.forEach(function(f){
      var c=acStorageCases.find(function(v){return v.floor===f.id;}),option=document.createElement("option");
      option.value=f.id;option.textContent=c?c.case+"｜"+c.label:"1F｜原配置，本輪不改";selector.appendChild(option);
    });
    selector.addEventListener("change",function(){
      setScope(studyChoice.building,selector.value,"",true,true);acStorageReadout();
      var url=new URL(location.href);url.searchParams.delete("cabinet");history.replaceState(null,"",url.href);
    });
    document.getElementById("ac-storage-focus").addEventListener("click",acStorageFocus);
    document.getElementById("ac-storage-floor-view").addEventListener("click",acStorageFloorView);
    acStorageReadout();
    if(new URL(location.href).searchParams.get("cabinet")==="1")acStorageFocus();
  }
  requestAnimationFrame(acStorageInit);

  // Shared photo-inspired facade, isolated from room and furniture geometry.
  // Inlined by export_model_3d.py for offline file:// use; no extra runtime.
  var facadeGroups = [], facadeMaterials = {}, exteriorAngle = "front", indoorSnapshot = null;
  var facadeControlIds = ["architecture", "full-walls", "navigation", "room-cutaway", "cut", "explode", "ghost"];
  function facadeIsActive() { return viewState.view === "exterior"; }
  function facadeMaterial(name) {
    if (!facadeMaterials[name]) {
      var entry = DATA.facade.palette[name], glass = name === "glass";
      var settings = {color:entry.color,roughness:name==="metal"?.5:.85,metalness:name==="metal"?.4:0,
        transparent:glass,opacity:glass?.3:1,depthWrite:!glass,side:THREE.DoubleSide};
      // Small deterministic tile/joint texture. This is an illustrative matte
      // finish, not the reference photo pasted onto invented structural walls.
      if (name === "light" || name === "dark") {
        var tile = document.createElement("canvas"); tile.width=tile.height=128;
        var ctx=tile.getContext("2d");ctx.fillStyle=entry.color;ctx.fillRect(0,0,128,128);
        ctx.strokeStyle=name==="light"?"#c6c5bd":"#43494d";ctx.lineWidth=.6;
        for(var n=0;n<4;n++){ctx.beginPath();ctx.moveTo(n*37,0);ctx.lineTo(n*37+18,52);ctx.lineTo(n*37+9,128);ctx.stroke();}
        var texture=new THREE.CanvasTexture(tile);texture.wrapS=texture.wrapT=THREE.RepeatWrapping;
        texture.repeat.set(3,1);settings.map=texture;
      }
      facadeMaterials[name]=new THREE.MeshStandardMaterial(settings);
    }
    return facadeMaterials[name];
  }
  function facadeBox(group, box, material) {
    var mesh=new THREE.Mesh(boxGeom,material);
    mesh.scale.set(box.w_mm*MM,box.h_mm*MM,box.d_mm*MM);
    mesh.position.set((box.x_mm+box.w_mm/2)*MM,(box.z_mm+box.h_mm/2)*MM,wz(box.y_mm+box.d_mm/2));
    mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);return mesh;
  }
  function initFacadeLayer() {
    if (!DATA.facade || DATA.facade.schema !== "house-facade-layer-v1") { return; }
    DATA.facade.buildings.forEach(function(record){
      var entry=floorGroups.find(function(e){return e.building.id===record.id;});if(!entry){return;}
      var group=new THREE.Group();entry.group.parent.add(group);group.visible=false;
      var parts=[], equipment=[];
      record.components.filter(function(c){return c.rendered;}).forEach(function(c){
        var mesh=facadeBox(group,c.box_mm,facadeMaterial(c.material));
        mesh.userData.facade=c;parts.push(mesh);
      });
      // Outdoor units stay at the exact original paired-proposal coordinates.
      // No decorative screen or pipe run is invented to conceal them.
      entry.building.floors.forEach(function(floor){floor.cells.forEach(function(cell){
        if(cell.tour_active===false){return;}
        (cell.tour_features.hvac_units || []).filter(function(u){return u.type==="outdoor";}).forEach(function(u){
          var alongX=u.face==="front"||u.face==="rear", w=alongX?u.width_mm:u.depth_mm,d=alongX?u.depth_mm:u.width_mm;
          var mesh=facadeBox(group,{x_mm:u.x_mm-w/2,y_mm:u.y_mm-d/2,z_mm:floor.base_mm+u.mount_height_mm,
            w_mm:w,d_mm:d,h_mm:u.height_mm},new THREE.MeshStandardMaterial({color:0xb5c4c8,roughness:.9}));
          var fan=new THREE.Mesh(cylinderGeom,new THREE.MeshStandardMaterial({color:0x50626a,roughness:.9}));
          fan.scale.set(.5,.015,.5);fan.rotation.x=Math.PI/2;
          fan.position.copy(mesh.position);fan.position.z+=u.face==="front"?(d*MM/2+.01):-(d*MM/2+.01);
          group.add(fan);equipment.push({id:u.id,room:cell.id,floor:floor.id,position_mm:[u.x_mm,u.y_mm,floor.base_mm+u.mount_height_mm],mesh:mesh});
        });
      });});
      facadeGroups.push({building:record.id,group:group,parts:parts,equipment:equipment,record:record});
    });
  }
  function syncFacadeControls() {
    var active=facadeIsActive();
    stage.classList.toggle("exterior",active);
    document.getElementById("view-exterior").hidden=active;
    ["exterior-front","exterior-oblique","exterior-return"].forEach(function(id){document.getElementById(id).hidden=!active;});
    document.getElementById("exterior-front").classList.toggle("on",active&&exteriorAngle==="front");
    document.getElementById("exterior-oblique").classList.toggle("on",active&&exteriorAngle==="oblique");
    ["exterior-front","exterior-oblique"].forEach(function(id){document.getElementById(id).setAttribute("aria-pressed",
      active&&((id==="exterior-front")===(exteriorAngle==="front"))?"true":"false");});
    var actions=document.getElementById("facade-actions");
    actions.style.top=active?(document.getElementById("stage-title").offsetTop+document.getElementById("stage-title").offsetHeight+8)+"px":"12px";
    ["furniture","furniture-names","show-conflicts","architecture","full-walls","navigation","room-cutaway","cut","explode","ghost","view-plan"].forEach(function(id){
      var control=document.getElementById(id);
      control.disabled=active || (id==="room-cutaway" && presentation!=="tour") ||
        (["architecture","full-walls","navigation"].indexOf(id)>=0 && presentation==="diagnostic");
    });
    document.querySelectorAll("#floor-visibility input, #floor-visibility button, #color-mode button").forEach(function(c){c.disabled=active;});
    var panel=document.getElementById("facade-review");panel.hidden=!active;
    if(active){
      panel.textContent="外觀 v1：同一份 tour_mm 門窗／陽台；裝飾不是梁柱，材質、欄杆、採光與防水未核定。";
      var records=facadeGroups.filter(function(e){return e.group.visible;}).map(function(e){return e.record;});
      records.forEach(function(r){
        var p=document.createElement("p");p.textContent=r.id+" 棟："+r.summary+" "+r.parking;panel.appendChild(p);
        var details=document.createElement("details"),summary=document.createElement("summary");
        summary.textContent=r.pending.length+" 項開口／格柵／維修待確認（未裝完成）";details.appendChild(summary);
        r.pending.forEach(function(item){var note=document.createElement("p");note.setAttribute("data-facade-pending-id",item.id);
          note.textContent=item.id+"："+item.note+(item.issues?" ["+item.issues.join(", ")+"]":"");details.appendChild(note);});
        panel.appendChild(details);
      });
      var source=document.createElement("a");source.href="../../Docs/abc-facade-v1.md";source.textContent="外觀材料／法規來源與建築師確認清單";
      source.className="inline";panel.appendChild(source);
    }
  }
  function updateFacadeLayer() {
    var active=facadeIsActive();
    facadeGroups.forEach(function(entry){entry.group.visible=active&&(!viewState.building||entry.building===viewState.building);});
    if(active){
      pickables.forEach(function(mesh){mesh.userData.shell.visible=false;mesh.userData.edges.visible=false;});
      ghostMeshes.forEach(function(m){m.visible=false;});
      document.getElementById("stage-title").innerHTML=escapeHtml((viewState.building?viewState.building+" 棟":"三棟")+" · 完整外觀 v1")+
        "<small>照片風格提案 · 門窗／陽台沿共用平面 · 車位／法規／結構未核</small>";
      document.getElementById("layout-review-note").textContent="外觀展示不計停車、不改房間／家具；候選窗衝突及前後設備遮屏仍待確認。";
    }
    syncFacadeControls();
  }
  function captureIndoorState() {
    var controls={};facadeControlIds.forEach(function(id){var c=document.getElementById(id);controls[id]={checked:c.checked,value:c.value};});
    return {state:Object.assign({},viewState),presentation:presentation,geomSource:geomSource,roomFocus:roomCameraFocused,
      selectedFurniture:selectedFurniture,controls:controls,floors:floorGroups.map(function(e){return e.group.visible;})};
  }
  function restoreIndoorControls() {
    if(!indoorSnapshot){return null;}
    var snapshot=indoorSnapshot;indoorSnapshot=null;
    facadeControlIds.forEach(function(id){var c=document.getElementById(id), saved=snapshot.controls[id];
      if(typeof saved.checked==="boolean"){c.checked=saved.checked;}c.value=saved.value;});
    return snapshot;
  }
  function enterExterior(buildingId, angle, write) {
    if(!DATA.facade || !facadeGroups.length){return;}
    if(!facadeIsActive()){indoorSnapshot=captureIndoorState();}
    exteriorAngle=angle==="oblique"?"oblique":"front";
    presentation="tour";roomCameraFocused=false;selectedFurniture="";
    viewState.view="exterior";
    viewState.building=buildingRecord(buildingId)?buildingId:"";viewState.floor="";viewState.room="";
    document.getElementById("cut").value="1000";document.getElementById("explode").value="0";
    document.getElementById("architecture").checked=true;document.getElementById("full-walls").checked=true;
    document.getElementById("navigation").checked=false;document.getElementById("room-cutaway").checked=false;
    document.getElementById("ghost").checked=false;
    floorGroups.forEach(function(e){var visible=!viewState.building||e.building.id===viewState.building;
      e.group.visible=visible;if(e.checkbox){e.checkbox.checked=visible;}});
    syncPresentation();applyCut();syncGeometryButtons();applyLayout();renderScopeControls();showInfo(null);
    applyViewPreset("exterior",false);if(write!==false){writeHash();}
  }
  function leaveExterior(write, buildingId, floorId) {
    if(!facadeIsActive()){return;}
    var currentBuilding=viewState.building, snapshot=restoreIndoorControls();
    presentation=snapshot?snapshot.presentation:"tour";geomSource=snapshot?snapshot.geomSource:"auto";
    viewState.view=snapshot?snapshot.state.view:"front";
    var next=snapshot?snapshot.state:{building:currentBuilding||"A",floor:"floor-1",room:""};
    if(floorId){presentation="tour";next={building:buildingId||currentBuilding||"A",floor:floorId,room:""};}
    syncPresentation();setScope(next.building,next.floor,next.room,false,false);
    if(snapshot && !floorId){
      // setScope chooses a default source for a newly selected legacy room;
      // explicit return must restore the user's saved source, not that default.
      geomSource=snapshot.geomSource;
      roomCameraFocused=snapshot.roomFocus;selectedFurniture=snapshot.selectedFurniture;
      floorGroups.forEach(function(e,n){e.group.visible=snapshot.floors[n];if(e.checkbox){e.checkbox.checked=e.group.visible;}});
      applyLayout();showInfo(viewState.room?meshById[viewState.room]:null);
    }
    applyCut();syncGeometryButtons();syncRoomViewActions();applyViewPreset(viewState.view,false);
    if(write!==false){writeHash();}
  }
  function facadeViewBox() {
    var box=new THREE.Box3();facadeGroups.filter(function(e){return e.group.visible;}).forEach(function(e){box.expandByObject(e.group);});
    pickables.filter(function(m){return m.visible&&m.parent.visible;}).forEach(function(m){box.expandByObject(m);});
    return box;
  }
  function fitExteriorCamera() {
    var box=facadeViewBox();if(box.isEmpty()){return;}
    var centre=box.getCenter(new THREE.Vector3());target.copy(centre);frameLighting(box);
    spherical.theta=exteriorAngle==="oblique"?.5:0;
    spherical.phi=exteriorAngle==="oblique"?1.25:Math.PI/2-.021;
    var direction=new THREE.Vector3(Math.sin(spherical.phi)*Math.sin(spherical.theta),Math.cos(spherical.phi),Math.sin(spherical.phi)*Math.cos(spherical.theta));
    var right=new THREE.Vector3().crossVectors(new THREE.Vector3(0,1,0),direction).normalize();
    var up=new THREE.Vector3().crossVectors(direction,right).normalize();
    var tanV=Math.tan(camera.fov*Math.PI/360), aspect=(stage.clientWidth||1)/(stage.clientHeight||1);
    var topPixels=document.getElementById("facade-actions").offsetTop+document.getElementById("facade-actions").offsetHeight+16;
    var topLimit=Math.max(.2,1-2*topPixels/(stage.clientHeight||1));
    var bottomLimit=Math.max(.3,1-2*(document.getElementById("orientation").offsetHeight+26)/(stage.clientHeight||1));
    var radius=3;
    boxCorners(box).forEach(function(corner){var offset=corner.sub(centre), depth=offset.dot(direction),vertical=offset.dot(up);
      radius=Math.max(radius,depth+Math.abs(offset.dot(right))/(tanV*aspect*.85),depth+Math.abs(vertical)/(tanV*(vertical>0?topLimit:bottomLimit)));});
    spherical.radius=radius;updateCamera();
  }
  function applyExteriorView(write) {
    viewState.view="exterior";root.scale.x=1;root.position.x=-modelCentreX;root.updateMatrixWorld(true);
    updateFacadeLayer();fitExteriorCamera();
    document.getElementById("view-front").classList.toggle("on",exteriorAngle==="front");document.getElementById("view-plan").classList.remove("on");
    document.getElementById("compass").innerHTML="<span><b>外觀</b><br />"+(exteriorAngle==="front"?"正立面":"斜角")+"</span>";
    if(write!==false){writeHash();}
  }
  function facadeDebug() {
    var visible=facadeGroups.filter(function(e){return e.group.visible;}), box=facadeViewBox();
    return {active:facadeIsActive(),id:DATA.facade&&DATA.facade.id,source:DATA.facade&&DATA.facade.source,
      status:DATA.facade&&DATA.facade.status,compliance:"unknown",angle:exteriorAngle,
      buildings:visible.map(function(e){return e.building;}),
      componentIds:visible.flatMap(function(e){return e.parts.map(function(p){return p.userData.facade.id;});}),
      openings:visible.flatMap(function(e){return e.record.openings;}),pending:visible.flatMap(function(e){return e.record.pending;}),
      allFloors:floorGroups.filter(function(e){return e.group.visible;}).map(function(e){return e.building.id+":"+e.floor.id;}),
      equipment:visible.flatMap(function(e){return e.equipment.map(function(u){return {id:u.id,room:u.room,floor:u.floor,position_mm:u.position_mm};});}),
      screenBounds:!facadeIsActive()||box.isEmpty()?[]:boxCorners(box).map(function(p){return p.project(camera).toArray();}),
      controls:facadeControlIds.reduce(function(all,id){var c=document.getElementById(id);all[id]={value:c.value,checked:c.checked,disabled:c.disabled};return all;},{}),
      snapshotAvailable:!!indoorSnapshot};
  }

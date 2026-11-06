  // Selected C layout only. Products, finished clearances and structure remain unapproved.
  var csMergeData=DATA.c_stair_merge || null;
  var csGateQuery=new URLSearchParams(location.search);
  var csGateState={front:csGateQuery.get("gate")==="closed"?"closed":"open",
    side:csGateQuery.get("sidegate")==="closed"?"closed":"open"};
  var csVoidFloorMaterial=null;
  function csInitControls(){
    if(!csMergeData)return;
    document.body.dataset.cStairIntegration="1";
    document.body.dataset.cStairDisplayRevision="2";
    var box=document.createElement("fieldset");box.id="c-stair-controls";
    box.style.cssText="margin:12px 0;padding:10px;border:1px solid #8fb5ab";
    var legend=document.createElement("legend");legend.textContent="C棟前置門配置已確認";box.appendChild(legend);
    [["front","c-stair-front-door","一、二樓前置門"],["side","c-stair-side-door","二樓側門（原900名義洞口）"]].forEach(function(spec){
      var label=document.createElement("label");label.htmlFor=spec[1];label.textContent=spec[2];
      var select=document.createElement("select");select.id=spec[1];select.style.cssText="width:100%;min-height:44px";
      [["open","開門示意"],["closed","關門示意"]].forEach(function(value){
        var option=document.createElement("option");option.value=value[0];option.textContent=value[1];select.appendChild(option);
      });
      select.value=csGateState[spec[0]];label.appendChild(select);box.appendChild(label);
      select.addEventListener("change",function(){
        csGateState[spec[0]]=select.value;
        var url=new URL(location.href);url.searchParams.set(spec[0]==="front"?"gate":"sidegate",select.value);
        history.replaceState(null,"",url.href);
        applyLayout();applyViewPreset(viewState.view,false);csUpdateReadout();
      });
    });
    var note=document.createElement("p");note.id="c-stair-door-state";note.setAttribute("role","status");
    note.style.cssText="font-size:12px;line-height:1.7";box.appendChild(note);
    document.getElementById("bc-study-controls").appendChild(box);csUpdateReadout();
  }
  function csUpdateReadout(){
    var note=document.getElementById("c-stair-door-state");if(!note)return;
    note.textContent="前門"+(csGateState.front==="open"?"開":"關")+"／側門"+(csGateState.side==="open"?"開":"關")+
      "；1200／900是名義洞口，實際淨寬、門型及消防未核。側門開啟仍有旁通。";
  }
  function csPrepareFloor(mesh){
    var active=presentation==="tour" && (featuresOf(mesh.userData.cell)||{}).c_stair_full_floor_omitted;
    mesh.userData.csFloorOmitted=!!active;
    if(active){
      if(!csVoidFloorMaterial)csVoidFloorMaterial=new THREE.MeshBasicMaterial({transparent:true,opacity:0,depthWrite:false,side:THREE.DoubleSide});
      mesh.material=csVoidFloorMaterial;
    }
  }
  function csBox(mesh,group,id,rect,top,height,role,colour,opacity){
    var part=architectureBox(group,(rect[0]+rect[2]/2)*MM,(top-height/2)*MM,wz(rect[1]+rect[3]/2),
      rect[2]*MM,height*MM,rect[3]*MM,colour,opacity);
    if(!part)return;
    part.userData.cameraFit=true;
    part.userData.csMerge={id:id,role:role,room:mesh.userData.cell.id,floor:mesh.userData.floor.id,
      rect_mm:rect,top_z_mm:top,height_mm:height};
    trackArchitecturePart(part,mesh,role==="tread"||role==="platform"?"stairs":role==="floor"?"floor":"door");
    return part;
  }
  function csBuildParts(mesh,group,features){
    if(presentation!=="tour"||!features.c_stair_surfaces)return;
    var base=mesh.userData.floor.base_mm,height=mesh.userData.floor.height_mm;
    features.c_stair_surfaces.forEach(function(s){
      csBox(mesh,group,s.id,s.rect_mm,s.top_z_mm,features.c_stair_surface_depth_mm,
        s.kind==="tread"?"tread":s.kind==="corridor-floor"?"floor":"platform",
        s.kind==="tread"?0xa7b8bd:s.kind==="corridor-floor"?0xc8d2cb:0x9fc8b2,1);
    });
    var arrival=features.c_stair_context_arrival;
    if(arrival && viewState.floor===mesh.userData.floor.id){
      csBox(mesh,group,arrival.id,arrival.rect_mm,arrival.top_z_mm,features.c_stair_surface_depth_mm,
        "platform",0x9fc8b2,1);
    }
    var gate=features.c_front_gate;
    if(gate){
      var wallHeight=document.getElementById("full-walls").checked?height:1050;
      var wall=gate.wall_budgets_mm[0],lo=gate.opening_x_mm[0],hi=gate.opening_x_mm[1];
      csBox(mesh,group,"front-fixed-left",[wall[0],wall[1],lo-wall[0],wall[3]],base+wallHeight,wallHeight,"partition",0xe3e6dc,1);
      csBox(mesh,group,"front-fixed-right",[hi,wall[1],wall[0]+wall[2]-hi,wall[3]],base+wallHeight,wallHeight,"partition",0xe3e6dc,1);
      if(wallHeight>2100)csBox(mesh,group,"front-overdoor",[lo,wall[1],hi-lo,wall[3]],base+wallHeight,wallHeight-2100,"partition",0xe3e6dc,1);
      csBox(mesh,group,"front-return",gate.wall_budgets_mm[1],base+wallHeight,wallHeight,"partition",0xe3e6dc,1);
      csBox(mesh,group,"front-frame-left",[lo,wall[1],45,wall[3]],base+2100,2100,"frame",0x527f75,1);
      csBox(mesh,group,"front-frame-right",[hi-45,wall[1],45,wall[3]],base+2100,2100,"frame",0x527f75,1);
      csBox(mesh,group,"front-frame-top",[lo,wall[1],hi-lo,wall[3]],base+2100,45,"frame",0x527f75,1);
      var rect=csGateState.front==="open"?gate.parking_rect_mm:gate.closed_leaf_rect_mm;
      csBox(mesh,group,"front-leaf",rect,base+2070,2070,"front-leaf",0xbda77f,1);
      csBox(mesh,group,"front-handle",[rect[0]+75,rect[1]+rect[3],45,25],base+1100,150,"handle",0x536878,1);
      if(viewState.room===mesh.userData.cell.id)addNavigationLabel(mesh,"前置門"+(csGateState.front==="open"?"開":"關")+"（產品／淨寬未核）",
        new THREE.Vector3((lo+hi)/2*MM,(base+250)*MM,wz(wall[1])),"entry");
    }
    var side=features.c_side_gate;
    if(side){
      csBox(mesh,group,"side-leaf",csGateState.side==="open"?side.open_rect_mm:side.closed_rect_mm,
        base+side.height_mm,side.height_mm,"side-leaf",0x9b9d85,1);
    }
  }
  function csEvidence(){
    if(!csMergeData)return {revision:1,active:false,parts:[],floorOmissions:[]};
    var parts=[],omissions=[];
    scene.traverse(function(p){
      var data=p.userData && p.userData.csMerge;
      if(data){
        var visible=true;for(var q=p;q;q=q.parent)if(!q.visible)visible=false;
        parts.push({id:data.id,role:data.role,room:data.room,floor:data.floor,visible:visible,
          actualRectMm:[(p.position.x-p.scale.x/2)/MM,(-p.position.z-p.scale.z/2)/MM,p.scale.x/MM,p.scale.z/MM],
          actualTopMm:(p.position.y+p.scale.y/2)/MM,actualHeightMm:p.scale.y/MM,
          opacity:p.material.opacity});
      }
    });
    pickables.forEach(function(mesh){
      if(!(mesh.userData.cell.tour_features||{}).c_stair_full_floor_omitted)return;
      omissions.push({room:mesh.userData.cell.id,floor:mesh.userData.floor.id,omitted:mesh.userData.csFloorOmitted===true,
        actualOpacity:mesh.material.opacity,actualDepthWrite:mesh.material.depthWrite});
    });
    return {revision:1,displayRevision:2,active:true,option:studyChoice.id,frontState:csGateState.front,sideState:csGateState.side,
      ownerConfirmedLayout:true,professionalApproval:"unknown",frontClearWidthMm:null,sideClearWidthMm:null,
      floorBases:DATA.buildings[0].floors.map(function(f){return {id:f.id,base_mm:f.base_mm,height_mm:f.height_mm};}),
      parts:parts,floorOmissions:omissions};
  }
  csInitControls();

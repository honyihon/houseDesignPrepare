  // Coordination envelopes are neither physical shafts nor approved pipe sizes.
  var caData=DATA.c_ac01_routing || null;
  function caInitControls(){
    if(!caData)return;
    document.body.dataset.cAc01RouteRevision="1";
    var section=document.createElement("fieldset");section.id="c-ac01-controls";
    section.style.cssText="margin:12px 0;padding:10px;border:1px solid #b8935d";
    var legend=document.createElement("legend");legend.textContent="C客餐冷氣：立管候選";section.appendChild(legend);
    var note=document.createElement("p");note.textContent="室內機改至乾式前室右壁；管線先在室內升高，再走二樓高位。立管協調帶占二樓0.04㎡，非已核管井。";
    note.style.cssText="font-size:12px;line-height:1.7";section.appendChild(note);
    [["c-ac01-indoor-link","看一樓室內機／管線","floor-1",caData.new_indoor_room],
      ["c-ac01-riser-link","看二樓立管協調帶","floor-2","C:floor-2:living2f"]].forEach(function(spec){
      var link=document.createElement("a"),url=new URL(location.href);
      url.hash="mode=tour&building=C&floor="+spec[2]+"&room="+encodeURIComponent(spec[3])+"&focus=room&view=plan";
      link.id=spec[0];link.href=url.href;link.textContent=spec[1];link.style.cssText="display:block;margin:8px 0;color:#b7e4df";section.appendChild(link);
    });
    var detail=document.createElement("a");detail.id="c-ac01-section-link";
    detail.href="kaohsiung-house-options/c-ac01-route-study.svg";detail.textContent="看新舊管線／穿板候選剖面";
    detail.style.cssText="display:block;color:#b7e4df";section.appendChild(detail);
    document.getElementById("bc-study-controls").appendChild(section);
  }
  function caBuildParts(mesh,group,features){
    var zone=features.c_ac01_riser_envelope;
    if(!caData||presentation!=="tour"||!zone)return;
    var r=zone.rect_mm,h=zone.top_z_mm-zone.bottom_z_mm;
    var part=architectureBox(group,(r[0]+r[2]/2)*MM,(zone.top_z_mm-h/2)*MM,wz(r[1]+r[3]/2),r[2]*MM,h*MM,r[3]*MM,0xb67834,.25);
    if(part){part.userData.cameraFit=false;part.userData.caEnvelope={room:mesh.userData.cell.id,floor:mesh.userData.floor.id};}
  }
  function caEvidence(){
    if(!caData)return {revision:1,active:false,envelopes:[]};
    var envelopes=[];
    scene.traverse(function(part){
      var tag=part.userData&&part.userData.caEnvelope;if(!tag)return;
      var visible=true;for(var parent=part;parent;parent=parent.parent)if(!parent.visible)visible=false;
      envelopes.push({room:tag.room,floor:tag.floor,visible:visible,
        rect_mm:[(part.position.x-part.scale.x/2)/MM,(-part.position.z-part.scale.z/2)/MM,part.scale.x/MM,part.scale.z/MM],
        bottom_z_mm:(part.position.y-part.scale.y/2)/MM,top_z_mm:(part.position.y+part.scale.y/2)/MM});
    });
    return {revision:1,active:true,professionalApproval:"unknown",envelopes:envelopes};
  }
  caInitControls();

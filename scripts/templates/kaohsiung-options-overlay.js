  // Prospective soil finish / shrubs only. No fabricated slab excavation,
  // retaining wall, foundation or compliant plant/soil specification.
  function khBuildZones(mesh, group, base, features) {
    var zone=features.kaohsiung_zones;
    if(!zone || presentation!=="tour")return;
    function tag(part,id,rect){
      part.userData.cameraFit=id!=="garden";
      part.userData.khZone={id:id,room:mesh.userData.cell.id,rect_mm:rect};
    }
    function outline(rect,id){
      var x=rect[0],y=rect[1],w=rect[2],h=rect[3];
      var p=[[x,y],[x+w,y],[x+w,y+h],[x,y+h],[x,y]].map(function(v){return new THREE.Vector3(v[0]*MM,base+.055,wz(v[1]));});
      var line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(p),new THREE.LineDashedMaterial({color:0x2563eb,dashSize:.12,gapSize:.07,clippingPlanes:[clipPlane]}));
      line.computeLineDistances();tag(line,id,rect);group.add(line);
    }
    outline(zone.garden_mm,"garden");
    zone.soil_rects_mm.forEach(function(r,n){
      var soil=architectureBox(group,(r[0]+r[2]/2)*MM,base+.012,wz(r[1]+r[3]/2),r[2]*MM,.012,r[3]*MM,0x719c73,.88);
      tag(soil,"soil-"+n,r);
    });
    zone.woody_points_mm.forEach(function(p,n){
      var trunk=architectureBox(group,p[0]*MM,base+.36,wz(p[1]),.055,.68,.055,0x826344,1);
      tag(trunk,"trunk-"+n,[p[0]-27.5,p[1]-27.5,55,55]);
      var shrub=architectureBox(group,p[0]*MM,base+.93,wz(p[1]),.32,.6,.32,0x30693e,.85);
      tag(shrub,"woody-"+n,[p[0]-160,p[1]-160,320,320]);
    });
  }
  function khEvidence(){
    var parts=[];
    scene.traverse(function(p){
      if(!p.userData.khZone)return;
      var visible=true;for(var q=p;q;q=q.parent){if(!q.visible)visible=false;}
      var geometry=p.geometry && p.geometry.parameters || {};
      var linePoints=null;
      if(p.isLine && p.geometry.attributes.position){
        var attr=p.geometry.attributes.position;linePoints=[];
        for(var i=0;i<attr.count;i++)linePoints.push([attr.getX(i)/MM,-attr.getZ(i)/MM]);
      }
      parts.push({id:p.userData.khZone.id,room:p.userData.khZone.room,rect_mm:p.userData.khZone.rect_mm,visible:visible,
        actualGeometry:{widthMm:geometry.width==null?null:geometry.width*p.scale.x/MM,heightMm:geometry.height==null?null:geometry.height*p.scale.y/MM,
          depthMm:geometry.depth==null?null:geometry.depth*p.scale.z/MM},actualCenterMm:[p.position.x/MM,-p.position.z/MM],actualLinePointsMm:linePoints});
    });
    return {revision:1,option:document.body.dataset.studyOption,use:document.body.dataset.studyUse,
      parts:parts,adopted:false,legalAndStructuralApproval:"unknown",soilDepthMm:null};
  }
  function khEquipmentRows(cell,features){
    features=features || {};
    var rows=[],zone=features.kaohsiung_zones;
    function area(rect){return rect[2]*rect[3]/1000000;}
    function amount(value){return String(Math.round(value*1000)/1000);}
    if(!(cell.furniture || []).length){
      rows.push({id:"empty-furniture",text:"本區未列獨立家具；景觀與空調依現有資料另列，未列項目仍待確認。"});
    }
    if(zone){
      rows.push({id:"garden",text:"景觀比較區 "+amount(area(zone.garden_mm))+"㎡（名義範圍，未核定）"});
      rows.push({id:"soil",text:"覆土候選投影 "+amount(zone.soil_rects_mm.reduce(function(total,rect){return total+area(rect);},0))+"㎡；實際土深、荷重、防水及法定綠化面積未核。"});
      rows.push({id:"woody",text:"木本植栽示意 "+zone.woody_points_mm.length+"株；至少一株120cm，樹種與土深未定。"});
    }
    (features.hvac_units || []).forEach(function(unit){
      rows.push({id:"hvac-"+unit.type+"-"+unit.id,text:unit.id+"｜"+(unit.type==="outdoor"?"室外機":"室內機")+" "+unit.width_mm+"×"+unit.depth_mm+"×"+unit.height_mm+" mm（代表尺寸；機型、管線與維修未核）"});
    });
    if(!rows.length)rows.push({id:"empty-equipment",text:"本房尚未列景觀或空調資料；不代表相關設計已完成。"});
    return rows;
  }
  function khAppendEquipmentReadout(list,cell,features){
    var section=document.createElement("div");section.id="kh-room-equipment";
    section.setAttribute("data-room",cell.id);section.setAttribute("role","list");
    section.setAttribute("aria-label","本房景觀與空調資料，未核定");
    var heading=document.createElement("p");heading.textContent="景觀與空調資料（未核）";
    heading.style.fontWeight="600";section.appendChild(heading);
    khEquipmentRows(cell,features).forEach(function(row){
      var entry=document.createElement("p");entry.setAttribute("role","listitem");
      entry.setAttribute("data-kh-equipment-id",row.id);entry.textContent=row.text;
      entry.style.cssText="margin:8px 0;line-height:1.6;overflow-wrap:anywhere";
      section.appendChild(entry);
    });
    list.appendChild(section);
  }

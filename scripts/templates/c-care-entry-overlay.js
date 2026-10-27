    // Generic full-height door LEAF BUDGETS, not selected/certified products.
    // Their actual meshes are exported to QA, never counted as extra furniture.
    (features.care_entry_leaves||[]).forEach(function(spec){
      var r=spec.rect_mm,h=spec.height_mm*MM;
      var leaf=new THREE.Mesh(new THREE.BoxGeometry(r[2]*MM,h,r[3]*MM),
        new THREE.MeshBasicMaterial({color:spec.state==="closed"?0xa84324:0xb67715,transparent:true,opacity:.35,depthWrite:false,clippingPlanes:[clipPlane]}));
      leaf.position.set((r[0]+r[2]/2)*MM,base+h/2,wz(r[1]+r[3]/2));
      leaf.userData.careEntryLeaf=spec;leaf.userData.cameraFit=false;group.add(leaf);
    });
    if(features.care_entry_turn_circle_mm){
      var circle=features.care_entry_turn_circle_mm,points=[];
      for(var index=0;index<49;index++){
        var angle=index/48*Math.PI*2;
        points.push(new THREE.Vector3((circle[0]+Math.cos(angle)*circle[2])*MM,base+.055,wz(circle[1]+Math.sin(angle)*circle[2])));
      }
      var turn=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineDashedMaterial({color:0x6d28d9,dashSize:.08,gapSize:.06,clippingPlanes:[clipPlane]}));
      turn.userData.cameraFit=false;turn.computeLineDistances();group.add(turn);
    }

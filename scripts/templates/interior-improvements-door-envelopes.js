    // Interior comparison only: dashed FLOOR budgets, not a selected door or
    // validated moving leaf. Original ABC and older comparison viewers are not
    // regenerated. The same reservations are serialized into SVG and 3D data.
    if (viewState.room === cell.id) {
      (features.reserved_mm || []).filter(function(zone){return zone.kind.indexOf("b-right-")===0 || zone.kind.indexOf("b-window-")===0 || zone.kind.indexOf("b-daily-")===0;}).forEach(function(zone){
        var b=zone.aabb, points=[
          [b.minX,b.minY],[b.maxX,b.minY],[b.maxX,b.maxY],[b.minX,b.maxY],[b.minX,b.minY]
        ].map(function(p){return new THREE.Vector3(p[0]*MM,base+.04,wz(p[1]));});
        var envelope=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),
          new THREE.LineDashedMaterial({color:0xb45309,dashSize:.06,gapSize:.035,clippingPlanes:[clipPlane]}));
        envelope.userData.interiorDoorEnvelope=zone.kind;
        envelope.computeLineDistances();group.add(envelope);
        var label=zone.kind==="b-right-slider-park"?"拉門向前停放預留（非產品）":
          zone.kind==="b-window-slider-park"?"拉門向右停放預留（非產品）":
          zone.kind.indexOf("slider-closed")>=0?"拉門關閉範圍（不可通行）":
          zone.kind.indexOf("dry-door")>=0?"乾櫃內開門範圍（取物分時）":
          zone.kind==="b-window-toilet-side-transfer"?"便器側移預留（非照護核可）":
          zone.kind==="b-window-toilet-front"?"便器前方操作（非核定）":
          zone.kind==="b-daily-drying-loading"?"晾衣取放預留（非照護通道）":
          zone.kind==="b-daily-dehumidifier-service"?"除濕機100mm假設維修量（非原廠）":
          zone.kind.indexOf("b-daily-existing-")===0?"原洗衣／洗槽操作保留":"洗手操作預留（非核定）";
        addNavigationLabel(mesh,label,new THREE.Vector3((b.minX+b.maxX)*MM/2,base+.12,wz((b.minY+b.maxY)/2)),"entry");
      });
    }

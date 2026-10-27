    // Real-sized door hardware budget meshes, not selected products or furniture.
    (features.care_door_parts||[]).forEach(function(spec){
      var r=spec.rect_mm;
      var part=new THREE.Mesh(new THREE.BoxGeometry(r[2]*MM,spec.height_mm*MM,r[3]*MM),
        new THREE.MeshBasicMaterial({color:spec.id==="bath-door-pull"?0x334155:0xa84324,transparent:true,opacity:.65,clippingPlanes:[clipPlane]}));
      part.position.set((r[0]+r[2]/2)*MM,base+(spec.bottom_mm+spec.height_mm/2)*MM,wz(r[1]+r[3]/2));
      part.userData.careDoor=spec;part.userData.cameraFit=false;group.add(part);
    });

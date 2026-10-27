    // Source-bound explanatory outlines, not extra furniture or approved routes.
    (features.care_route_overlays||[]).forEach(function(spec){
      var points=spec.points_mm.map(function(p){return new THREE.Vector3(p[0]*MM,base+.075,wz(p[1]));});
      var line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineDashedMaterial({
        color:spec.kind==="sweep"?0xb45309:spec.blocked?0xb43b25:0x137d9c,dashSize:.1,gapSize:.06,clippingPlanes:[clipPlane]}));
      line.userData.cameraFit=false;line.userData.careRoute=spec;line.computeLineDistances();group.add(line);
    });

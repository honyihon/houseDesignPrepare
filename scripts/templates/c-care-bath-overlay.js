    (features.care_bath_components||[]).forEach(function(spec){
      var part=new THREE.Group(),material=new THREE.MeshBasicMaterial({color:spec.id.indexOf("alarm")===0?0xc43c2b:spec.id==="fold-seat"?0x9d7955:0x64748b,clippingPlanes:[clipPlane]});
      part.userData.careBath=spec;part.userData.cameraFit=false;
      if(spec.kind==="box"){
        var r=spec.rect_mm,h=spec.height_mm*MM;
        var box=new THREE.Mesh(new THREE.BoxGeometry(r[2]*MM,h,r[3]*MM),material);
        box.position.set((r[0]+r[2]/2)*MM,base+(spec.bottom_mm+spec.height_mm/2)*MM,wz(r[1]+r[3]/2));part.add(box);
      }else{
        var points=spec.points_mm.map(function(p){return new THREE.Vector3(p[0]*MM,base+p[2]*MM,wz(p[1]));}),radius=spec.diameter_mm*MM/2;
        points.forEach(function(point){var end=new THREE.Mesh(new THREE.SphereGeometry(radius,12,8),material);end.position.copy(point);part.add(end);});
        for(var n=1;n<points.length;n++){
          var direction=new THREE.Vector3().subVectors(points[n],points[n-1]),length=direction.length();
          var pipe=new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,length,12),material);
          pipe.position.copy(points[n]).add(points[n-1]).multiplyScalar(.5);pipe.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),direction.normalize());part.add(pipe);
        }
      }
      group.add(part);
    });
    if(features.care_bath_circle_mm){
      var c=features.care_bath_circle_mm,points=[];
      for(var n=0;n<=48;n++){var a=n/48*Math.PI*2;points.push(new THREE.Vector3((c[0]+Math.cos(a)*c[2])*MM,base+.08,wz(c[1]+Math.sin(a)*c[2])));}
      var circle=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineDashedMaterial({color:features.care_bath_state==="shower"?0xb43b25:0x6d28d9,dashSize:.08,gapSize:.06,clippingPlanes:[clipPlane]}));
      circle.userData.cameraFit=false;circle.computeLineDistances();group.add(circle);
    }
    if(features.care_bath_vent_route_mm){
      var points=features.care_bath_vent_route_mm.map(function(p){return new THREE.Vector3(p[0]*MM,base+p[2]*MM,wz(p[1]));});
      var vent=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineDashedMaterial({color:0xb45309,dashSize:.1,gapSize:.06,clippingPlanes:[clipPlane]}));
      vent.userData.cameraFit=false;vent.computeLineDistances();group.add(vent);
    }

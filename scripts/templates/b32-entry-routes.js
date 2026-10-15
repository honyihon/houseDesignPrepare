    // B32-only body translation annotation. No imaginary rear alley geometry.
    (features.b32_transport_segments || []).forEach(function(segment) {
      var b=segment.body_sweep_mm;
      var points=segment.centerline_mm.map(function(p){return new THREE.Vector3(p[0]*MM,base+.05,wz(p[1]));});
      var line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineDashedMaterial({color:0x287b89,dashSize:.16,gapSize:.10,clippingPlanes:[clipPlane]}));
      line.computeLineDistances();line.userData.cameraFit=false;group.add(line);
      var corners=[[b.minX,b.minY],[b.maxX,b.minY],[b.maxX,b.maxY],[b.minX,b.maxY],[b.minX,b.minY]].map(function(p){return new THREE.Vector3(p[0]*MM,base+.035,wz(p[1]));});
      var band=new THREE.Line(new THREE.BufferGeometry().setFromPoints(corners),new THREE.LineDashedMaterial({color:0x287b89,dashSize:.16,gapSize:.10,clippingPlanes:[clipPlane]}));
      band.computeLineDistances();band.userData.cameraFit=false;group.add(band);
      var a=segment.centerline_mm[0],z=segment.centerline_mm[1],dx=z[0]-a[0],dy=z[1]-a[1],length=Math.sqrt(dx*dx+dy*dy);
      if(length>0){
        var nx=dx/length,ny=dy/length,mx=(a[0]+z[0])/2,my=(a[1]+z[1])/2;
        var arrow=[[mx-ny*120-nx*170,my+nx*120-ny*170],[mx,my],[mx+ny*120-nx*170,my-nx*120-ny*170]].map(function(p){return new THREE.Vector3(p[0]*MM,base+.06,wz(p[1]));});
        var tip=new THREE.Line(new THREE.BufferGeometry().setFromPoints(arrow),new THREE.LineBasicMaterial({color:0x287b89,clippingPlanes:[clipPlane]}));
        tip.userData.cameraFit=false;group.add(tip);
      }
      transportRouteParts.push({mesh:mesh,part:line,segment:segment,status:"storage-body-sweep-only-not-transport-approval"});
      if(viewState.room===cell.id)addNavigationLabel(mesh,segment.label,new THREE.Vector3((a[0]+z[0])*MM/2,base+.18,wz((a[1]+z[1])/2)),"study");
    });

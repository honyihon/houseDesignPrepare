(function(global){'use strict';
  function rectsOverlap(a,b,gap=0){
    return a.left<b.left+b.width+gap&&a.left+a.width+gap>b.left&&a.top<b.top+b.height+gap&&a.top+a.height+gap>b.top;
  }
  // CSS supplies measured, uncompressed label sizes. Place names, never move models.
  function placeLabels(candidates,viewport,obstacles=[]) {
    const margin=8,gap=6,placed=[];
    for(const c of [...candidates].sort((a,b)=>a.priority-b.priority)){
      if(![c.x,c.y,c.width,c.height].every(Number.isFinite)||c.width<=0||c.height<=0||
         c.width>viewport.width-2*margin||c.height>viewport.height-2*margin)continue;
      const choices=[];
      for(const step of [0,18,42,72,110,160]){
        for(const [dx,dy] of [[0,-1],[0,1],[-1,0],[1,0],[-1,-1],[1,-1],[-1,1],[1,1]]){
          const x=c.x+(dx<0?-c.width-gap-step:dx>0?gap+step:-c.width/2);
          const y=c.y+(dy<0?-c.height-gap-step:dy>0?gap+step:-c.height/2);
          const rect={left:Math.max(margin,Math.min(viewport.width-margin-c.width,x)),
            top:Math.max(margin,Math.min(viewport.height-margin-c.height,y)),width:c.width,height:c.height};
          const nearX=Math.max(rect.left,Math.min(rect.left+rect.width,c.x)),nearY=Math.max(rect.top,Math.min(rect.top+rect.height,c.y));
          choices.push({rect,score:(nearX-c.x)**2+(nearY-c.y)**2});
        }
      }
      choices.sort((a,b)=>a.score-b.score);
      const best=choices.find(({rect})=>!obstacles.some(o=>rectsOverlap(rect,o,gap))&&!placed.some(p=>rectsOverlap(rect,p.rect,gap)));
      if(best)placed.push({id:c.id,rect:best.rect});
    }
    return placed;
  }

global.B_UPPER_LABELS={rectsOverlap:rectsOverlap,placeLabels:placeLabels};})(globalThis);

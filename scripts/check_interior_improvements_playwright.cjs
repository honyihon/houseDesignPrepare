// Native Windows only for rendered QA. --preflight performs file checks only.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {spawnSync}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {isDeepStrictEqual:same}=require('node:util');
const legacy=require('./check_windows_playwright.cjs');
const MARKER='house-interior-improvements-qa';
const INDEX='structured/candidates/interior-improvements.html',VIEWER='structured/candidates/interior-improvements-3d.html';
const MANIFEST='structured/candidates/interior-improvements/review.json';
const IDS=['b-rear-service','b-front-service','c-care-laundry','a-upper-wet-core','b-rear-right-access','b-front-right-access','b-rear-window','b-front-window','b-rear-dry-service','b-front-dry-service'];
const OWNER_CHOICES={'c-washer':'one-washer-retain-2f-no-1f-addition','a-bath-move':'exterior-window-priority-retain-rear-bath','c-kitchen':'front-fridge-450mm-public-area-tradeoff-for-integration'};
const PENDING=['b-left-access','b-table-benches','b-storage','c-base'];
function preflight(project){
  const primary=legacy.preflight(project),study=JSON.parse(fs.readFileSync(path.join(project,MANIFEST),'utf8'));
  if(study.schema!=='house-interior-improvements-review-v1'||study.revision!==7||study.status!=='comparison-only-not-adopted'||
    !same(study.options.map(o=>o.id),IDS)||!same(study.frame_mm,[6000,17630])||study.default_option!=='b-rear-dry-service'||
    study.owner_decisions.length!==7||new Set(study.owner_decisions.map(d=>d.id)).size!==7||study.owner_decisions.some(d=>
      OWNER_CHOICES[d.id] ? d.status!=='confirmed-preference'||d.choice!==OWNER_CHOICES[d.id]||!d.source : !PENDING.includes(d.id)||d.status!=='pending')||
    Object.values(study.professional_status).some(v=>v!=='unknown')||study.rendered_qa!=='not-run')throw Error('Invalid interior improvement scope or approval');
  const accepted=study.owner_decisions.find(d=>d.id==='c-kitchen').accepted_scope;
  if(!accepted||accepted.front_partition_shift_mm!==450||accepted.nominal_public_loss_sqm!==1.08||accepted.whole_c_layout_adopted!==false||
    accepted.professional_approval!=='unknown'||!/^[a-f0-9]{64}$/.test(accepted.layout_sha256)||!/^[a-f0-9]{64}$/.test(accepted.basis_report_hash))throw Error('C kitchen acceptance must remain scoped, not whole-layout or professional approval');
  const files=[INDEX,VIEWER,MANIFEST,'scripts/check_interior_improvements_playwright.cjs','scripts/export_interior_improvements.py'];
  const hashes={...study.source_hashes,'scripts/export_interior_improvements.py':study.generator_sha256};
  for(const [rel,sha] of Object.entries(hashes)){
    if(!/^(inputs|scripts|structured|assets|house_design)\/[\w./-]+$/.test(rel)||rel.split('/').some(p=>p==='..'||p.toLowerCase().includes('private'))||!/^[a-f0-9]{64}$/.test(sha))throw Error('Unsafe source/hash');
    if(crypto.createHash('sha256').update(fs.readFileSync(path.join(project,rel))).digest('hex')!==sha)throw Error('Stale interior source: '+rel);files.push(rel);
  }
  const raw=fs.readFileSync(path.join(project,VIEWER),'utf8').match(/^\s*var DATA = (.+);\s*$/m);
  const payload=raw&&JSON.parse(raw[1]).bc_options;
  if(!payload||!same(payload.options.map(o=>o.id),IDS))throw Error('Missing/incorrect 3D options');
  const counts={options:0,floors:0,rooms:0,items:0};
  for(const o of study.options){
    const m=payload.options.find(p=>p.id===o.id).model;
    if(m.buildings.length!==1||m.buildings[0].id!==o.building||m.bc_option.revision!==7||!same(m.bc_option.geometry_review,o.review)||
      !same(m.bc_option.owner_decisions,study.owner_decisions.filter(d=>d.building===o.building))||o.status!==study.status)throw Error('Mixed model or stale review');
    if(o.id.endsWith('-right-access')){
      const rooms=o.plans.floors[0].rooms,bath=rooms.find(r=>r.key==='bath-extension'),dry=rooms.find(r=>r.key==='altar-backing');
      const door=bath.features.doors.find(d=>d.neighbor==='B:floor-1:corridor1'),dryDoor=dry.features.doors.find(d=>d.neighbor==='B:floor-1:dry-access');
      const last=o.review.bath_route_sensitivity.at(-1),area=o.review.area_rows.find(r=>r.zone==='bathroom');
      if(rooms.some(r=>['bath1','bath-shoulder'].includes(r.key))||!same(bath.geometry,{x_mm:1140,y_mm:12970,w_mm:3180,h_mm:1960})||
        door?.face!=='right'||door.width_mm!==1130||door.operation!=='sliding'||dryDoor?.face!=='left'||dryDoor.width_mm!==1060||
        dry.features.doors.some(d=>d.neighbor==='B:floor-1:corridor1')||o.review.bath_access!=='right-carry-passage'||
        area.original_target_sqm!==7||area.sensitivity.at(-1).area_sqm!==5.1035||last.passage_width_mm!==1355||last.door_clear_assumption_mm!==900||
        last.dry_door_clear_assumption_mm!==830||o.review.front_continuous_1500mm_shortfall_mm!==145||o.review.operation_vs_fixed_body.length||
        !o.review.operation_vs_shared_wet_floor.length||o.review.bath_route_sensitivity.some(r=>
          ['bath_entry_route','basin_approach_route','toilet_side_route','dry_cabinet_700mm_body_route'].some(k=>r[k].coordinate_failures.length)||
          r.turn_circle_coordinate_failures.length||r.fixture_body_coordinate_failures.length||r.dry_door_swing_coordinate_failures.length)||
        o.review.carry_body_115mm.coordinate_failures.length||o.review.bath_window!=='none-mechanical-exhaust-makeup-air-and-waterproofing-unknown')throw Error('B right-access tradeoffs or paired door/clearance study differ');
    }
    if(o.id.endsWith('-window')||o.id.endsWith('-dry-service')){
      const rooms=o.plans.floors[0].rooms,bath=rooms.find(r=>r.key==='rear-bath'),dry=rooms.find(r=>r.key==='altar-backing');
      const door=bath.features.doors.find(d=>d.neighbor==='B:floor-1:dry-route'),dryDoor=dry.features.doors.find(d=>d.neighbor==='B:floor-1:corridor1');
      const areas=Object.fromEntries(o.review.area_rows.map(r=>[r.zone,r])),last=o.review.bath_route_sensitivity.at(-1);
      const toilet=bath.furniture.find(i=>i.catalog_id==='toilet');
      if(!same(bath.geometry,{x_mm:0,y_mm:14500,w_mm:2700,h_mm:3130})||door?.face!=='front'||door.width_mm!==1130||door.operation!=='sliding'||
        dryDoor?.face!=='right'||dryDoor.width_mm!==1060||!bath.features.window_review?.renderable||bath.features.window_face!=='rear'||
        bath.features.window_mm!==900||bath.features.window_sill_mm!==1500||bath.features.window_height_mm!==600||
        Math.abs(bath.features.window_ratio*2700-1950)>.001||toilet.placement.rotation_deg!==90||
        !same(toilet.placement.aabb,{minX:1885,maxX:2585,minY:14825,maxY:15275})||
        areas.bathroom.original_target_sqm!==7||areas.storage.original_target_sqm!==10.5||areas.laundry.original_target_sqm!==5||
        areas.bathroom.sensitivity.at(-1).area_sqm!==7.163||areas.storage.sensitivity.at(-1).area_sqm!==11.1215||areas.laundry.sensitivity.at(-1).area_sqm!==5.005||
        o.review.laundry_public_route_counted_as_area!==false||!o.review.independent_outdoor_work_balcony.startsWith('unmet')||
        o.review.carry_entry_mode!==(o.id.startsWith('b-rear-')?'rear':'front')||o.review.carry_body_115mm.coordinate_failures.length||
        o.review.front_gate_clear_115mm!==1430||o.review.front_continuous_1500mm_shortfall_mm!==70||
        last.passage_width_mm!==1130||last.door_clear_assumption_mm!==900||last.local_open_route_leaf_gap_mm!==365||
        !o.review.dry_turn_and_transfer_do_not_borrow_shower||o.review.operation_vs_fixed_body.length||o.review.operation_vs_shared_wet_floor.length||
        o.review.bath_route_sensitivity.some(r=>['bath_entry_route','local_bath_open_route','basin_approach_route','toilet_side_route','shower_approach_route','dry_cabinet_700mm_body_route'].some(k=>r[k].coordinate_failures.length)||
          !r.arrival_during_ritual.coordinate_failures.length||!r.closed_door_route.coordinate_failures.length||r.turn_circle_coordinate_failures.length||
          r.bath_operation_coordinate_failures.length||r.laundry_operation_coordinate_failures.length||r.dry_door_swing_coordinate_failures.length)||
        !o.review.arrival_ritual_conflict.startsWith('must-time-separate-pending-family'))throw Error('B rear-window geometry, original targets or conditional limitations differ');
      if(rooms.filter(r=>['laundry-front','laundry-base'].includes(r.key)).some(r=>r.outdoor||r.features.window_review?.renderable))throw Error('Interior laundry may not be presented as an exterior-window balcony');
    }
    if(o.id.endsWith('-dry-service')){
      const control=study.options.find(p=>p.id===(o.id.startsWith('b-rear-')?'b-rear-window':'b-front-window'));
      const daily=o.review.daily_use_review,room=o.plans.floors[0].rooms.find(r=>r.key==='laundry-base');
      const rack=room.furniture.find(i=>i.catalog_id==='generic-indoor-drying-envelope-1200'),dehum=room.furniture.find(i=>i.catalog_id==='dehumidifier');
      if(!daily||!rack||!dehum||!same([rack.width_mm,rack.depth_mm,rack.height_mm],[1200,600,1600])||
        !same(rack.placement.aabb,{minX:3005,maxX:4205,minY:13785,maxY:14385})||
        !same(dehum.placement.aabb,{minX:2500,maxX:2850,minY:13985,maxY:14285})||
        rack.physical_item_id!==null||dehum.physical_item_id!==null||!same(o.review.area_rows,control.review.area_rows)||
        !same(daily.equipment.dehumidifier_service_mm,[2400,13885,550,500])||
        daily.sensitivity.some(r=>r.equipment_and_operation_failures.length||r.local_loading_700mm_body_route.coordinate_failures.length||
          !r.ceremony_bath_access_failures.length||!r.ceremony_bath_access_status.startsWith('blocked'))||
        !same(daily.cross_corridor.remaining_laundry_area_sensitivity.map(r=>r.area_sqm),[2.0832,1.868,1.7108])||
        daily.cross_corridor.original_minimum_sqm!==4||daily.cross_corridor.original_target_sqm!==5||
        daily.cross_corridor.nominal_area_taken_sqm!==3.3448||!daily.cross_corridor.position.startsWith('reject')||
        Object.values(daily.mechanical_requirements).some(v=>!v.startsWith('unknown'))||
        daily.next_recommendation.status!=='owner-direction-required-not-drawn-or-adopted'||
        !daily.next_recommendation.simple_swap_front_carry_status.startsWith('not-accommodated')||
        !daily.original_work_balcony.startsWith('unmet'))throw Error('B drying study lost dimensions, operating limits or unresolved ritual access');
      for(const f of o.plans.floors){const old=control.plans.floors.find(p=>p.id===f.id);
        for(const r of f.rooms){const before=old.rooms.find(p=>p.id===r.id);
          if(!same(r.geometry,before.geometry)||!same(r.features.doors,before.features.doors)||!same(r.features.open_connections,before.features.open_connections)||
            before.furniture.some(i=>!r.furniture.some(p=>same(p,i)))||r.furniture.length-before.furniture.length!==(f.id==='floor-1'&&r.key==='laundry-base'?2:0))throw Error('B daily study may only add two tentative items, no hidden geometry/product edits');}}
    }
    if(o.building==='C'){
      const washers=o.plans.floors.flatMap(f=>f.rooms.flatMap(r=>r.furniture.filter(i=>i.catalog_id==='washer').map(i=>({floor:f.id,item:i}))));
      if(washers.length!==1||washers[0].floor!=='floor-2'||o.review.washer_count!==1||o.review.washer_floor!=='floor-2')throw Error('C must keep exactly one washer on floor-2');
      const kitchen=o.plans.floors[0].rooms.find(r=>r.key==='kitchen'),fridge=kitchen.furniture.find(i=>i.catalog_id==='fridge-75');
      if(!same(kitchen.geometry,{x_mm:0,y_mm:8580,w_mm:2400,h_mm:3520})||fridge.placement.rotation_deg!==180||
        !same(fridge.placement.aabb,{minX:1435,maxX:2185,minY:8795,maxY:9495})||o.review.public_area_tradeoff.nominal_public_loss_sqm!==1.08||
        o.review.public_area_tradeoff.status!=='owner-confirmed-for-integration-professional-unknown'||o.review.furniture_body_sensitivity.some(i=>i.inset_mm===null)||
        o.review.operation_vs_fixed_body.length||o.review.kitchen_route_sensitivity.some(r=>
          r.counter_operation_depth_mm!==900||r.operation_failures.length||r.fixed_body_failures.length||r.kitchen_entry_route.coordinate_failures.length||
          r.fridge_body_replacement_route.coordinate_failures.length||!r.fridge_clearance_discussion_assumptions_met))throw Error('C front fridge, full working bands or scoped owner acceptance differ');
    }
    if(o.building==='A'){
      const bath=o.plans.floors.find(f=>f.id==='floor-3').rooms.find(r=>r.key==='bath3');
      if(!bath.features.window_review?.renderable||bath.features.window_face!=='rear'||bath.features.window_mm!==600||
        bath.features.window_sill_mm!==2100||bath.features.window_height_mm!==500||o.review.windowless_relocation!=='withdrawn-owner-prefers-exterior-window')throw Error('A must retain the rear high-window bathroom, not the withdrawn windowless relocation');
    }
    counts.options++;
    for(const f of o.plans.floors){
      const mf=m.buildings[0].floors.find(p=>p.id===f.id),active=mf.cells.filter(c=>c.tour_active);
      if(active.length!==f.rooms.length||f.width_mm!==6000||f.depth_mm!==17630)throw Error('Missing floor rooms or expanded frame');
      for(const r of f.rooms){
        const c=active.find(c=>c.id===r.id);
        if(!c||!same(c.tour_mm,r.geometry)||!same(c.tour_features,r.features)||c.furniture.length!==r.furniture.length||
          r.furniture.some(i=>!same(i.placement,c.furniture_placements.tour_mm[i.id])))throw Error('HTML/3D parity differs');
      }
      const rel='structured/candidates/interior-improvements/'+f.plan_file,svg=fs.readFileSync(path.join(project,rel),'utf8');
      if(!svg.includes('data-improvement-option="'+o.id+'"')||f.rooms.some(r=>r.furniture.some(i=>!svg.includes('data-furniture-id="'+i.id+'"'))))throw Error('SVG incomplete');
      files.push(rel);counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
    }
  }
  return {study,cli:primary.cli,counts,mainCounts:primary.counts,sourceFiles:[...new Set([...primary.sourceFiles,...files])]};
}
async function checkPages(page,base,output,study,expected){
  const checks=[],screenshots=[],messages=[],counts={options:0,floors:0,rooms:0,items:0};
  const assert=(v,name)=>{checks.push({name,passed:Boolean(v)});if(!v)throw Error(name);};
  const capture=async name=>{const file=output+'/'+name;await page.screenshot({path:file,fullPage:false});screenshots.push(file);};
  const ready=async id=>page.waitForFunction(id=>document.body.dataset.studyOption===id&&window.__htmlModel3dDebug?.().cameraFraming.ready,id);
  page.setDefaultTimeout(15000);page.setDefaultNavigationTimeout(30000);
  page.on('pageerror',e=>messages.push({level:'pageerror',text:e.message}));
  page.on('console',m=>{if(['error','warning'].includes(m.type()))messages.push({level:m.type(),text:m.text()});});
  try{
    await page.setViewportSize({width:1440,height:900});await page.goto(base+'structured/candidates/interior-improvements.html');
    assert((await page.title()).includes('ABC室內改善')&&await page.locator('section[data-option]').count()===10,'Index identity/nonblank/ten options');
    const navLabels=await page.locator('nav[aria-label="改善比較導航"] a[href^="#"]').allTextContents();
    assert(navLabels.length===10&&new Set(navLabels).size===10,'All ten navigation labels distinguish controls and use studies');
    assert(await page.locator('[data-decision]').count()===7&&await page.locator('[data-decision-status="confirmed-preference"]').count()===3&&
      await page.locator('[data-decision-status="pending"]').count()===4,'Three confirmed preferences and four pending decisions in HTML');
    assert(await page.locator('[data-decision="c-kitchen"]').getAttribute('data-decision-status')==='confirmed-preference'&&
      (await page.locator('[data-decision="c-kitchen"]').innerText()).includes('已確認')&&
      (await page.locator('[data-decision="c-kitchen"]').innerText()).includes('1.08m²'),'C kitchen owner acceptance and area cost visible without construction approval');
    assert((await page.locator('[data-decision="c-washer"]').innerText()).includes('撤下1F新增機')&&
      (await page.locator('[data-decision="a-bath-move"]').innerText()).includes('撤回3F無窗移位'),'Confirmed A window and C single-washer choices visible');
    assert((await page.locator('.warning').first().innerText()).includes('不是原主案'),'Visible comparison warning');
    await capture('interior-index-desktop.png');
    const first=page.locator('[data-plan-viewer]').first();
    await first.locator('[data-plan-controls]').waitFor({state:'visible'});
    const before=await first.getAttribute('data-plan-width');await first.locator('[data-plan-action="in"]').click();
    assert(Number(await first.getAttribute('data-plan-width'))>Number(before),'Plan zoom changes rendered width');
    await first.locator('[data-plan-action="overview"]').click();assert(await first.getAttribute('data-plan-mode')==='overview','Plan overview action');
    for(const o of study.options){
      await page.goto(base+'structured/candidates/interior-improvements-3d.html?scheme='+o.id+'#mode=tour&building='+o.building+'&floor=floor-1&view=plan');
      await ready(o.id);
      assert((await page.title()).includes(o.label)&&await page.locator('#study-stage-note').isVisible(),'Isolated option identity and visible warning '+o.id);
      assert((await page.locator('#study-plan-link').getAttribute('href'))==='interior-improvements.html#'+o.id&&!(await page.locator('#tour-actions').isVisible()),'Correct return/no main shortcuts '+o.id);
      for(const f of o.plans.floors){
        await page.locator('#scope-floors [data-floor="'+f.id+'"]').click();
        await page.waitForFunction(fid=>window.__htmlModel3dDebug().state.floor===fid,f.id);
        const d=await page.evaluate(()=>window.__htmlModel3dDebug());
        assert(d.presentation==='tour'&&d.bcOption?.id===o.id&&d.bcOption.revision===7&&d.state.building===o.building&&d.visibleRooms.length===f.rooms.length,'Complete isolated floor '+o.id+' '+f.id);
        for(const r of f.rooms){
          const rr=d.tour.rooms.find(t=>t.id===r.id);
          assert(rr&&JSON.stringify(rr.geometry)===JSON.stringify(r.geometry)&&JSON.stringify(rr.features)===JSON.stringify(r.features),'Actual room geometry/features '+o.id+' '+r.id);
          if(r.features.window_review?.renderable)assert(rr.windowParts>0,'Actual candidate window geometry '+o.id+' '+r.id);
          for(const i of r.furniture){const a=d.furniture.shapes.find(s=>s.id===i.id);
            assert(a?.visible&&a.parts>0&&!a.overflow&&!a.collision&&a.width===i.width_mm&&a.depth===i.depth_mm&&a.height===i.height_mm&&
              Math.abs(a.center[0]-i.placement.center_x_mm)<.05&&Math.abs(a.center[1]-i.placement.center_y_mm)<.05,'Actual full-size furniture '+o.id+' '+i.id);}
          for(const i of r.furniture){const a=d.furniture.shapes.find(s=>s.id===i.id);
            assert(Math.abs(a.rotation-i.placement.rotation_deg)<.05,'Actual furniture rotation '+o.id+' '+i.id);}
        }
        if(o.building==='C'){
          if(f.id==='floor-1'){
            const fridge=d.furniture.shapes.find(s=>s.id==='C:floor-1:kitchen:furniture:fridge');
            const counter=d.furniture.shapes.find(s=>s.id==='C:floor-1:kitchen:furniture:counter');
            assert(Math.abs(fridge.rotation-180)<.05&&Math.abs(fridge.center[0]-1810)<.05&&Math.abs(fridge.center[1]-9145)<.05&&
              counter.placement.operation_mm.maxX-counter.placement.operation_mm.minX===900,'C actual front fridge orientation and retained 900mm counter operation band');
            assert((await page.locator('#study-stage-note').innerText()).includes('客餐取捨已確認')&&
              (await page.locator('#study-stage-note').innerText()).includes('未採用'),'C confirmed tradeoff and whole-layout limitation visible on 3D stage');
          }
          const washerIds=o.plans.floors.flatMap(p=>p.rooms.flatMap(r=>r.furniture.filter(i=>i.catalog_id==='washer').map(i=>i.id)));
          const visibleWashers=d.furniture.shapes.filter(s=>s.visible&&washerIds.includes(s.id));
          assert(visibleWashers.length===(f.id==='floor-2'?1:0)&&!d.furniture.shapes.some(s=>s.id==='C:floor-1:kitchen:furniture:care-washer'),'C only original second-floor washer, no first-floor addition '+f.id);
          if(f.id==='floor-2')await capture('c-single-washer-second-floor-desktop.png');
        }
        if(o.building==='A'&&f.id==='floor-3'){
          const bath=d.tour.rooms.find(r=>r.id==='A:floor-3:bath3');
          assert(bath.features.window_face==='rear'&&bath.features.window_mm===600&&bath.windowParts>0,'A retained bathroom has actual rear candidate window');
        }
        if(o.id.endsWith('-right-access')&&f.id==='floor-1'){
          const bath=d.tour.rooms.find(r=>r.id==='B:floor-1:bath-extension'),dry=d.tour.rooms.find(r=>r.id==='B:floor-1:altar-backing');
          assert(!d.tour.rooms.some(r=>r.id==='B:floor-1:bath1')&&bath.features.doors.some(p=>p.face==='right'&&p.operation==='sliding')&&
            dry.features.doors.some(p=>p.face==='left'&&p.neighbor==='B:floor-1:dry-access')&&!dry.features.doors.some(p=>p.neighbor==='B:floor-1:corridor1'),
            'B actual right bathroom and separate left dry entrance '+o.id);
          const cabinet=d.furniture.shapes.find(s=>s.id==='B:floor-1:altar-backing:furniture:cabinet');
          assert(Math.abs(cabinet.rotation-90)<.05&&Math.abs(cabinet.center[0]-3980)<.05&&Math.abs(cabinet.center[1]-12085)<.05,
            'B actual full-size dry cabinet moves to right wall '+o.id);
          assert(bath.features.reserved_mm.filter(z=>z.kind.startsWith('b-right-slider-')).length===2&&
            (await page.locator('#study-stage-note').innerText()).includes('未採用'),'B door budgets and unadopted status retained '+o.id);
        }
        if((o.id.endsWith('-window')||o.id.endsWith('-dry-service'))&&f.id==='floor-1'){
          const bath=d.tour.rooms.find(r=>r.id==='B:floor-1:rear-bath'),dry=d.tour.rooms.find(r=>r.id==='B:floor-1:altar-backing');
          assert(bath.windowParts>0&&bath.features.window_face==='rear'&&bath.features.window_mm===900&&
            bath.features.window_sill_mm===1500&&bath.features.window_height_mm===600&&
            bath.features.doors.some(p=>p.face==='front'&&p.operation==='sliding')&&
            dry.features.doors.some(p=>p.face==='right'&&p.neighbor==='B:floor-1:corridor1'),
            'B actual direct rear bathroom window and independent dry-cabinet door '+o.id);
          const toilet=d.furniture.shapes.find(s=>s.id==='B:floor-1:rear-bath:furniture:toilet');
          const basin=d.furniture.shapes.find(s=>s.id==='B:floor-1:rear-bath:furniture:basin');
          const washer=d.furniture.shapes.find(s=>s.id==='B:floor-1:laundry-front:furniture:washer');
          assert(Math.abs(toilet.rotation-90)<.05&&Math.abs(toilet.center[0]-2235)<.05&&Math.abs(toilet.center[1]-15050)<.05&&
            Math.abs(basin.center[1]-17290)<.05&&Math.abs(washer.center[0]-1800)<.05&&Math.abs(washer.center[1]-11810)<.05,
            'B actual wall-backed toilet, rear basin and forward washer '+o.id);
          assert(bath.features.reserved_mm.some(z=>z.kind==='b-window-toilet-side-transfer')&&
            bath.features.reserved_mm.filter(z=>z.kind.startsWith('b-window-slider-')).length===2,
            'B actual separate transfer and slider reservation data '+o.id);
        }
        if(o.id.endsWith('-dry-service')&&f.id==='floor-1'){
          const rack=d.furniture.shapes.find(s=>s.id==='B:floor-1:laundry-base:furniture:small-drying-rack');
          const dehum=d.furniture.shapes.find(s=>s.id==='B:floor-1:laundry-base:furniture:dehumidifier');
          assert(rack?.parts>6&&rack.width===1200&&rack.depth===600&&rack.height===1600&&
            Math.abs(rack.center[0]-3605)<.05&&Math.abs(rack.center[1]-14085)<.05&&
            dehum?.width===350&&dehum.depth===300&&dehum.height===600&&Math.abs(dehum.center[0]-2675)<.05,
            'B actual small open drying rack and dehumidifier without resized catalog rack '+o.id);
          const room=d.tour.rooms.find(r=>r.id==='B:floor-1:laundry-base');
          assert(room.features.reserved_mm.filter(z=>z.kind.startsWith('b-daily-')).length===4,
            'B original laundry bands and new drying-service budgets retained '+o.id);
        }
        if(f.id===(o.building==='A'?'floor-3':'floor-1'))await capture(o.id+'-changed-floor-desktop.png');
        counts.floors++;counts.rooms+=f.rooms.length;counts.items+=f.rooms.reduce((n,r)=>n+r.furniture.length,0);
      }
      counts.options++;
    }
    for(const o of study.options){
      const floor=o.building==='A'?'floor-3':'floor-1',key=o.building==='A'?'bath3':o.id.endsWith('-dry-service')?'laundry-base':o.id.endsWith('-window')?'rear-bath':o.id.endsWith('-right-access')?'bath-extension':o.building==='B'?'bath1':'kitchen';
      await page.setViewportSize({width:390,height:844});
      await page.goto(base+'structured/candidates/interior-improvements-3d.html?scheme='+o.id+'#mode=tour&building='+o.building+'&floor='+floor+'&room='+encodeURIComponent(o.building+':'+floor+':'+key)+'&focus=room&view=front');
      await ready(o.id);const toggle=page.locator('#mobile-panel-toggle');
      if(await toggle.isVisible()&&await toggle.getAttribute('aria-expanded')==='true')await toggle.click();
      await page.waitForFunction(()=>window.__htmlModel3dDebug().panelCollapsed);
      const d=await page.evaluate(()=>window.__htmlModel3dDebug());
      assert(d.roomCloseup&&d.state.room===o.building+':'+floor+':'+key&&d.visibleRooms.length===o.plans.floors.find(f=>f.id===floor).rooms.length,'Mobile closeup retains complete floor '+o.id);
      assert(await page.locator('#study-stage-note').isVisible(),'Mobile comparison warning '+o.id);
      if(o.id.endsWith('-right-access')){
        await toggle.click();
        const info=page.locator('#info');await info.waitFor({state:'visible'});
        const text=await info.innerText();
        assert(text.includes('5.1035')&&text.includes('1355')&&text.includes('無外窗'),'B mobile area, route and window tradeoffs available in open details '+o.id);
        await info.scrollIntoViewIfNeeded();await capture(o.id+'-mobile-tradeoffs.png');
        await toggle.click();await page.waitForFunction(()=>window.__htmlModel3dDebug().panelCollapsed);
      }
      if(o.id.endsWith('-window')){
        await toggle.click();const info=page.locator('#info');await info.waitFor({state:'visible'});
        const text=await info.innerText();
        assert(text.includes('7.1630')&&text.includes('5.0050')&&text.includes('0.005m²')&&
          text.includes('祭祀區')&&text.includes('分時')&&text.includes('權利')&&text.includes('不保證防黴'),
          'B mobile rear-window budget, ritual conflict and ventilation limits remain readable '+o.id);
        await info.scrollIntoViewIfNeeded();await capture(o.id+'-mobile-tradeoffs.png');
        await toggle.click();await page.waitForFunction(()=>window.__htmlModel3dDebug().panelCollapsed);
        const r=await page.evaluate(()=>window.__htmlModel3dDebug().tour.rooms.find(r=>r.id==='B:floor-1:rear-bath'));
        assert(r.windowParts>0,'B mobile bathroom closeup retains real candidate window '+o.id);
      }
      if(o.id.endsWith('-dry-service')){
        const ids=['B:floor-1:laundry-base:furniture:small-drying-rack','B:floor-1:laundry-base:furniture:dehumidifier'];
        assert(ids.every(id=>{const s=d.furniture.shapes.find(s=>s.id===id);return s?.visible&&s.parts>0&&!s.overflow&&!s.collision;}),
          'B mobile full-size drying equipment visible in laundry closeup '+o.id);
        await page.waitForFunction(()=>{const f=window.__htmlModel3dDebug().cameraFraming;return f.safeArea?.usable&&f.autoFit?.area&&
          ['left','right','top','bottom'].every(k=>Math.abs(f.autoFit.area[k]-f.safeArea[k])<1);});
        const frame=await page.evaluate(()=>window.__htmlModel3dDebug().cameraFraming);
        assert(ids.every(id=>{const item=frame.selectedItems.find(i=>i.id===id),points=item?.corners;
          if(!points||points.length!==8||points.some(p=>!p.every(Number.isFinite)||Math.abs(p[2])>1))return false;
          const xs=points.map(p=>(p[0]+1)*frame.width/2),ys=points.map(p=>(1-p[1])*frame.height/2);
          return Math.max(...xs)-Math.min(...xs)>=16&&Math.max(...ys)-Math.min(...ys)>=16&&
            Math.min(...xs)>=frame.safeArea.left-1&&Math.max(...xs)<=frame.safeArea.right+1&&
            Math.min(...ys)>=frame.safeArea.top-1&&Math.max(...ys)<=frame.safeArea.bottom+1;}),
          'B mobile new equipment has 16px projected bodies inside safe area, not label-only evidence '+o.id);
        await toggle.click();const info=page.locator('#info');await info.waitFor({state:'visible'});const text=await info.innerText();
        assert(text.includes('1.7108')&&text.includes('4m²下限')&&text.includes('祭祀占用時')&&text.includes('35×30×60cm')&&
          text.includes('不是把原240cm架縮小')&&text.includes('除濕不等於換氣')&&text.includes('未新增門或隔間'),
          'B mobile ceremony failure and unapproved drying ventilation remain explicit '+o.id);
        await info.scrollIntoViewIfNeeded();await capture(o.id+'-mobile-tradeoffs.png');
        await toggle.click();await page.waitForFunction(()=>window.__htmlModel3dDebug().panelCollapsed);
      }
      await capture(o.id+'-mobile-focus.png');await page.locator('#room-overview').click();
      assert(!(await page.evaluate(()=>window.__htmlModel3dDebug().roomCloseup)),'Mobile return to whole floor '+o.id);
    }
    await page.goto(base+'structured/candidates/interior-improvements.html');await capture('interior-index-mobile.png');
    assert(JSON.stringify(counts)===JSON.stringify(expected),'All ten options and forty floors inspected');
    const unexpected=messages.filter(m=>!(m.level==='warning'&&(m.text.includes('GPU stall due to ReadPixels')||m.text.includes('Scripts "build/three.js" and "build/three.min.js" are deprecated'))));
    assert(!unexpected.length,'No relevant console/runtime errors');
    return {marker:'house-interior-improvements-qa',revision:7,status:'passed',counts,checks,screenshots,messages};
  }catch(e){await capture('failure.png').catch(()=>{});await page.goto('about:blank').catch(()=>{});
    return {marker:'house-interior-improvements-qa',revision:7,status:'failed',error:String(e),counts,checks,screenshots,messages};}
}
function makeBrowserScript(base,output,study,counts){return `async page => (${checkPages.toString()})(page,${JSON.stringify(base)},${JSON.stringify(output)},${JSON.stringify(study)},${JSON.stringify(counts)})`;}
function findReport(v){if(v&&typeof v==='object'){if(v.marker===MARKER)return v;for(const x of Object.values(v)){const r=findReport(x);if(r)return r;}}else if(typeof v==='string'){try{return findReport(JSON.parse(v));}catch{}}return null;}
function validateReport(r,counts){
  if(!r||r.marker!==MARKER||!['passed','failed'].includes(r.status))throw Error('No completed structured QA result');
  if(r.status==='passed'&&(r.revision!==7||!same(r.counts,counts)||!r.checks?.length||r.checks.some(c=>c.passed!==true)||!Array.isArray(r.screenshots)||r.screenshots.length<29))throw Error('Incomplete passing evidence');
  return r;
}
function runQa(options,prepared,output,execute=spawnSync){
  const session='house-interior-'+crypto.randomBytes(5).toString('hex'),config=path.join(output,'cli.config.json'),script=path.join(output,'check-pages.js');
  const base=pathToFileURL(options.project+path.sep).href,sourceHashes=legacy.hashSources(options.project,prepared.sourceFiles);
  fs.writeFileSync(config,JSON.stringify({browser:{browserName:'chromium',launchOptions:{channel:options.browser,headless:true},contextOptions:{viewport:{width:1440,height:900},deviceScaleFactor:1}},allowUnrestrictedFileAccess:true,outputDir:output}));
  fs.writeFileSync(script,makeBrowserScript(base,output,prepared.study,prepared.counts));
  const invoke=(name,args,required=true)=>{const r=execute(process.execPath,[prepared.cli,'cli','-s='+session,'--json',...args],{cwd:output,encoding:'utf8',timeout:240000,maxBuffer:8*1024*1024,env:{...process.env,PWTEST_DAEMON_SESSION_DIR:path.join(output,'daemon'),NO_UPDATE_NOTIFIER:'1'}});
    fs.writeFileSync(path.join(output,name+'.log'),(r.stdout||'')+'\n'+(r.stderr||'')+(r.error?'\n'+String(r.error):''));if(required&&(r.error||r.status!==0))throw Error(name+' failed; see '+name+'.log');return r;};
  let report={marker:MARKER,status:'incomplete'};
  try{
    invoke('open',['open',base+INDEX,'--config='+config]);const response=JSON.parse(invoke('checks',['run-code','--filename='+script]).stdout);
    if(response?.isError)throw Error('Playwright CLI error; see checks.log.');report=validateReport(findReport(response),prepared.counts);
    if(!same(sourceHashes,legacy.hashSources(options.project,prepared.sourceFiles))){report.status='incomplete';report.error='Sources changed during QA; rerun unchanged version.';}
  }catch(e){report.status='incomplete';report.error=String(e);}
  finally{Object.assign(report,{project:options.project,sourceHashes,browser:options.browser,session});try{const c=invoke('close',['close'],false);report.sessionClosed=!c.error&&c.status===0&&['closed','not-open'].includes(JSON.parse(c.stdout).status);}catch{report.sessionClosed=false;}fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(report,null,2));}
  return report;
}
function main(){
  const o=legacy.parseArguments(process.argv.slice(2));
  if(o.help){console.log('Windows: node scripts/check_interior_improvements_playwright.cjs [--preflight] [--project <folder>]. No installs or adoption.');return;}
  if(!o.preflight&&process.platform!=='win32')throw Error('Use native Windows Node for browser QA; WSL --preflight is file-only.');
  const p=preflight(o.project);console.log('Project: '+o.project);console.log('Primary ABC unchanged: '+JSON.stringify(p.mainCounts));console.log('Interior improvement preflight passed: '+JSON.stringify(p.counts));
  console.log('Interior revision: 7; B small-rack/dehumidifier studies added, original eight plans retained. Ceremony bathroom access remains blocked; ventilation and work balcony unknown. No adoption or professional approval.');
  if(o.preflight){console.log('Files only. Browser/rendered/professional QA not performed.');return;}
  const output=fs.mkdtempSync(path.join(os.tmpdir(),'house-interior-cli-'));console.log('QA output folder: '+output);
  const r=runQa(o,p,output);console.log('Automated interior browser checks: '+r.status);console.log('Result: '+path.join(output,'result.json'));
  if(r.error)console.error(r.error);if(!r.sessionClosed)console.warn('Only this session was targeted; cleanup unconfirmed.');
  console.log('Screenshots need visual review; no adoption, care, religious, transport or construction approval.');if(r.status!=='passed')process.exitCode=1;
}
if(require.main===module){try{main();}catch(e){console.error(String(e));process.exitCode=1;}}
module.exports={preflight,checkPages,makeBrowserScript,findReport,validateReport,runQa};

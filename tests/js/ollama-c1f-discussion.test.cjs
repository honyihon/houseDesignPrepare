'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { MODEL, MARKER, SOURCES, argumentsOf, prepare, continueMessages, discuss } = require('../../scripts/review_c1f_with_ollama.cjs');
const root = path.resolve(__dirname, '../..');

// Contract doubles only. These fixtures are NOT real Kimi opinions or evidence
// that Ollama, cloud credentials, geometry or a two-model discussion succeeded.
const response = body => ({ ok: true, status: 200, json: async () => body });
const answer = () => response({ model: MODEL, done: true, message: { role: 'assistant', content: 'fixture, not a model response' } });

test('only local daemon origins and complete explicit followup arguments are accepted', () => {
  assert.equal(MODEL, 'kimi-k3:cloud');
  assert.equal(argumentsOf([]).host, 'http://127.0.0.1:11434');
  assert.equal(argumentsOf(['--preflight']).preflight, true);
  assert.equal(argumentsOf(['--host','http://localhost:11434']).host, 'http://localhost:11434');
  assert.equal(argumentsOf(['--resume','result.json','--followup','reply.md']).followup, 'reply.md');
  for (const args of [['--model','a-different-model'], ['--host'], ['--resume','result.json'],
    ['--followup','reply.md'], ['--host','https://ollama.com'], ['--host','http://user:password@localhost:11434'],
    ['--host','http://localhost:11434/api'], ['--host','http://localhost:11434/?key=private']]) {
    assert.throws(() => argumentsOf(args));
  }
});

test('prompt contains owner decisions and actual C evidence without sharing whole A/B plans', () => {
  const data = prepare(root);
  assert.equal(Object.keys(data.sourceHashes).length, SOURCES.length);
  for (const [file,hash] of Object.entries(data.sourceHashes)) {
    assert.equal(hash, crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex'));
  }
  const evidence = JSON.parse(data.messages[1].content.split('C 專案同源證據 JSON：\n')[1]);
  assert.equal(evidence.main_c_plans.id, 'C');
  assert.equal(evidence.side_bed_candidate.plans.id, 'C');
  assert.equal(evidence.side_bed_candidate.id, 'c-side-bed');
  assert.deepEqual(evidence.independent_public_bath_candidates.map(o=>o.id), ['bath-front','front-living']);
  assert.ok(evidence.legacy_c1f_requirements.every(r=>r.id.startsWith('C.floor-1.')));
  assert.ok(!JSON.stringify(evidence).includes('B:floor-'));
  assert.ok(!JSON.stringify(evidence).includes('A:floor-'));
  assert.ok(data.messages[1].content.includes('尚未接受'));
  assert.ok(data.messages[1].content.includes('27.2m²') && data.messages[1].content.includes('22.4m²'));
  assert.ok(data.messages[1].content.includes('保留原 20m²'));
  assert.ok(!data.messages[1].content.includes('## 執行與狀態'),'local execution instructions are not shared with the model');
  assert.ok(!data.messages[1].content.includes('\\wsl.localhost'),'do not share machine-specific command paths');
  assert.ok(data.requestCharacters < 100000,'avoid the old 295k-character duplicated evidence');
  const read = file => JSON.parse(fs.readFileSync(path.join(root,file),'utf8').replace(/^window\.\w+\s*=\s*/,'').replace(/;\s*$/,''));
  const original = read('structured/candidates/bc-options/layout.js').options.find(o=>o.id==='c-side-bed').plans;
  const compactFloor = evidence.side_bed_candidate.plans.floors[0];
  assert.deepEqual(compactFloor.rooms.map(r=>r.id), original.floors[0].rooms.map(r=>r.id),'retain the complete real first-floor inventory');
  for (const room of compactFloor.rooms) {
    const real = original.floors[0].rooms.find(r=>r.id===room.id);
    assert.deepEqual(room.geometry,real.geometry);
    for (const key of ['doors','open_connections','reserved_mm','fixed_reserved_mm','stair_geometry','hvac_units']) {
      assert.deepEqual(room.features[key],real.features[key],room.id+' '+key);
    }
    assert.deepEqual(room.furniture.map(i=>i.id),real.furniture.map(i=>i.id));
    for (const item of room.furniture) {
      const actual=real.furniture.find(i=>i.id===item.id);
      assert.deepEqual(item.placement,actual.placement,'no simplification of product/operation geometry');
      assert.deepEqual([item.width_mm,item.depth_mm,item.height_mm],[actual.width_mm,actual.depth_mm,actual.height_mm]);
      assert.equal(item.shared_operation_mode,actual.shared_operation_mode);
    }
  }
  for (const floor of evidence.side_bed_candidate.plans.floors.slice(1)) {
    const real=original.floors.find(f=>f.id===floor.id);
    for (const room of real.rooms.filter(r=>r.kind==='bath'||r.kind==='kitchen')) {
      assert.deepEqual(floor.rooms.find(r=>r.id===room.id).geometry,room.geometry,'all upper wet projections remain exact');
    }
  }
  const main=read('structured/candidates/furniture-plans/layout.js').buildings.find(b=>b.id==='C');
  for (const room of evidence.main_c_plans.floors[0].rooms) {
    assert.deepEqual(room.geometry,main.floors[0].rooms.find(r=>r.id===room.id).geometry);
  }
  assert.deepEqual(evidence.main_c_plans.floors[0].rooms.find(r=>r.key==='elder').furniture.map(i=>i.placement),
    main.floors[0].rooms.find(r=>r.key==='elder').furniture.map(i=>i.placement));
  const originalPublic=read('structured/candidates/c1f-options/layout.js').options;
  for (const option of evidence.independent_public_bath_candidates) {
    const real=originalPublic.find(o=>o.id===option.id);
    assert.deepEqual(option.floor.rooms.map(r=>r.key).sort(),['dining','entrance','living','public-bath']);
    assert.ok(option.omitted_rooms.includes('not automatically merged'));
    assert.ok(option.upper_geometry_reference.includes('not the side-bed'));
    for (const room of option.floor.rooms) {
      const actual=real.floor.rooms.find(r=>r.id===room.id);
      assert.deepEqual(room.geometry,actual.geometry);
      assert.deepEqual(room.features.doors,actual.features.doors);
      assert.deepEqual(room.furniture.map(i=>i.placement),actual.furniture.map(i=>i.placement));
    }
  }
});

test('cloud request uses one direct nonstreaming chat, not a local-tags gate, and no credentials or pulls', async () => {
  const calls = [];
  const out = await discuss('http://127.0.0.1:11434', [{role:'user',content:'fixture'}], async (url,options)=> {
    calls.push({url,options});return answer();
  });
  assert.deepEqual(calls.map(c=>c.url), ['http://127.0.0.1:11434/api/chat']);
  assert.equal(calls[0].options.method, 'POST');
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.model, MODEL);assert.equal(body.stream, false);
  assert.ok(!('Authorization' in calls[0].options.headers));
  assert.equal(out.message.content, 'fixture, not a model response');
});

test('empty local model inventory does not reject an available cloud model', async () => {
  let calls = 0;
  const reply = await discuss('http://localhost:11434', [], async url=> {
    calls++;
    if (url.endsWith('/api/tags')) return response({models:[]});
    assert.ok(url.endsWith('/api/chat'));return answer();
  });
  assert.equal(reply.model,MODEL);
  assert.equal(calls,1);
});

test('blocked network and cloud HTTP errors remain failures, not completed model discussions', async () => {
  await assert.rejects(discuss('http://localhost:11434', [], async ()=> { throw new Error('socket: operation not permitted'); }), /operation not permitted/);
  await assert.rejects(discuss('http://localhost:11434', [], async ()=> ({ok:false,status:401,text:async()=> 'unauthorized'})), /Ollama HTTP 401/);
  let calls=0;
  await assert.rejects(discuss('http://localhost:11434', [], async ()=> {
    calls++;return {ok:false,status:404,text:async()=> 'requested cloud model unavailable'};
  }), /Ollama HTTP 404.*cloud model unavailable/);
  assert.equal(calls,1,'do not replace a failed cloud model or pull a local model');
});

test('empty, partial, wrong-provider and failed model replies cannot become research evidence', async () => {
  for (const reply of [
    { model:MODEL,done:false,message:{role:'assistant',content:'partial'} },
    { model:MODEL,done:true,message:{role:'assistant',content:'  '} },
    { model:MODEL,done:true,message:{role:'assistant',content:[]} },
    { model:'a-different-model',done:true,message:{role:'assistant',content:'fixture'} },
    { error:'model unavailable' },
  ]) {
    await assert.rejects(discuss('http://localhost:11434', [], async ()=> response(reply)),
      /Incomplete\/empty response|model unavailable/);
  }
});

test('real prior dialogue and explicit followup are preserved; stale, failed or tampered resumes are rejected', () => {
  const prepared = prepare(root),previous = {marker:MARKER,model:MODEL,status:'external-response-received-awaiting-codex-review',
    sourceHashes:prepared.sourceHashes,messages:[...prepared.messages,{role:'assistant',content:'fixture, not a model response'}]};
  const continued = continueMessages(prepared,previous,'Codex fixture followup');
  assert.equal(continued.at(-2).role,'assistant');
  assert.equal(continued.at(-1).content,'Codex fixture followup');
  for (const mutate of [p=>{p.status='failed';},p=>{p.model='other-model';},p=>{p.sourceHashes={};},
    p=>{p.messages[0].content='changed initial scope';},p=>{p.messages.pop();},p=>{p.messages.at(-1).content='';}]) {
    const bad=structuredClone(previous);mutate(bad);assert.throws(()=>continueMessages(prepared,bad,'followup'),/Invalid, stale/);
  }
  assert.throws(()=>continueMessages(prepared,previous,' '),/Invalid, stale/);
});

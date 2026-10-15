'use strict';

// Explicitly requested external research, not an adoption or drawing generator.
// Uses only a local Ollama daemon; no credentials, pulls, installs or model swaps.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');

const MODEL = 'kimi-k3:cloud';
const MARKER = 'house-c1f-ollama-discussion-v1';
const ROOT = path.resolve(__dirname, '..');
const SOURCES = ['Docs/c1f-kimi-discussion-brief-v1.md', 'structured/candidates/furniture-plans/layout.js',
  'structured/candidates/bc-options/layout.js', 'structured/candidates/c1f-options/layout.js', 'inputs/requirements.json'];

function selectFields(object, keys) {
  return Object.fromEntries(keys.filter(key => Object.hasOwn(object, key)).map(key => [key, object[key]]));
}

function researchRoom(room) {
  // Preserve real geometry, openings, normal products and operation reserves.
  // Exclude renderer colors, repeated room prose and unrelated upper uses.
  return { ...selectFields(room, ['id','key','name','kind','requirement_id','outdoor','geometry']),
    features: selectFields(room.features, ['status','geometry_source','doors','open_connections','window_face',
      'window_ratio','window_mm','window_sill_mm','window_height_mm','window_pending','stairs','stair_geometry',
      'stair_geometry_verified','shared_landing_mm','fixed_reserved_mm','reserved_mm','hvac_units']),
    furniture: room.furniture.map(item => selectFields(item, ['id','catalog_id','label','shape','width_mm',
      'depth_mm','height_mm','front_clearance_mm','rear_clearance_mm','left_clearance_mm','right_clearance_mm',
      'note','shared_operation_mode','shared_operation_with','placement'])) };
}

function researchFloor(floor, rooms = floor.rooms) {
  return { ...selectFields(floor, ['id','label','width_mm','depth_mm','base_mm','height_mm']), rooms: rooms.map(researchRoom) };
}

function researchPlans(building) {
  return { id: building.id, levels: building.floors.map(floor => selectFields(floor, ['id','base_mm','height_mm'])),
    floors: building.floors.filter(floor => ['floor-1','floor-2','floor-3'].includes(floor.id)).map(floor =>
      researchFloor(floor, floor.id === 'floor-1' ? floor.rooms : floor.rooms.filter(room =>
        ['bath','kitchen','stair'].includes(room.kind) || room.key === 'rear-service'))) };
}

function argumentsOf(args) {
  const options = { preflight: false, host: 'http://127.0.0.1:11434' };
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--preflight') options.preflight = true;
    else if (['--host', '--resume', '--followup'].includes(arg) && args[i+1] && !args[i+1].startsWith('--')) {
      options[arg.slice(2)] = args[++i];
    } else throw new Error('Unknown or incomplete argument: ' + arg);
  }
  const host = new URL(options.host);
  if (!['http:', 'https:'].includes(host.protocol) || !['localhost', '127.0.0.1', '[::1]'].includes(host.hostname) ||
      host.username || host.password || host.search || host.hash || host.pathname !== '/') {
    throw new Error('--host must be a local Ollama origin without credentials or a path.');
  }
  options.host = host.origin;
  if (Boolean(options.resume) !== Boolean(options.followup)) throw new Error('--resume and --followup must be used together.');
  return options;
}

function prepare(project = ROOT) {
  const raw = file => fs.readFileSync(path.join(project, file), 'utf8');
  const json = file => JSON.parse(raw(file).replace(/^window\.\w+\s*=\s*/, '').replace(/;\s*$/, ''));
  const sourceHashes = Object.fromEntries(SOURCES.map(file => [file,
    crypto.createHash('sha256').update(fs.readFileSync(path.join(project, file))).digest('hex')]));
  const main = json(SOURCES[1]).buildings.find(b => b.id === 'C');
  const bcStudy = json(SOURCES[2]), bathStudy = json(SOURCES[3]);
  for (const study of [bcStudy, bathStudy]) {
    if (!study.source_hashes || !Object.keys(study.source_hashes).length) throw new Error('Missing comparison source hashes.');
    for (const [file,hash] of Object.entries(study.source_hashes)) {
      if (!/^[\w./-]+$/.test(file) || path.isAbsolute(file) || file.split('/').includes('..') || !/^[a-f0-9]{64}$/.test(hash) ||
          crypto.createHash('sha256').update(fs.readFileSync(path.join(project,file))).digest('hex') !== hash) {
        throw new Error('Stale or invalid comparison source: ' + file + '; regenerate the comparison before sharing.');
      }
    }
  }
  const side = bcStudy.options.find(o => o.id === 'c-side-bed');
  const publicBath = bathStudy.options.filter(o => ['bath-front', 'front-living'].includes(o.id));
  if (!main || !side || publicBath.length !== 2 || side.status !== 'comparison-only-not-adopted' ||
      side.building !== 'C' || side.professional_status?.structure_and_fire !== 'unknown') {
    throw new Error('Missing C plans or unexpected adoption/approval; stop before sharing.');
  }
  const mainReference = researchPlans(main);
  mainReference.evidence_scope = 'Geometry reference; original elder/sliding-door details are retained. Other unchanged 1F product details are in the side-bed candidate.';
  mainReference.floors = mainReference.floors.map(floor => ({ ...floor, rooms: floor.rooms.map(room =>
    ['elder','sliding-door'].includes(room.key) ? room : selectFields(room, ['id','key','name','kind','outdoor','geometry'])) }));
  const evidence = { scope: 'C-only-research-not-adopted', sourceHashes,
    evidence_scope: 'Complete side-bed C 1F; main geometry/original elder doors; modified public zones only for independent bathroom alternatives. Upper wet rooms/stairs/service and level heights, not a full upper program.',
    main_c_plans: mainReference,
    side_bed_candidate: { id: side.id, plans: researchPlans(side.plans), geometry_review: side.geometry_review,
      professional_status: side.professional_status, unresolved_furniture: side.unresolved_furniture },
    independent_public_bath_candidates: publicBath.map(option => ({
      ...selectFields(option, ['id','label','summary','tradeoffs','visitor_route','public_bath_key',
        'public_bath_verified','daylight_verified','plumbing_verified','route','areas_sqm','windows','hvac','unresolved_furniture']),
      floor: researchFloor(option.floor, option.floor.rooms.filter(room =>
        ['entrance','living','dining','public-bath'].includes(room.key))),
      omitted_rooms: 'Unchanged from current main C 1F, not automatically merged with the side-bed candidate.',
      upper_geometry_reference: 'main_c_plans, not the side-bed wet-room patch' })),
    legacy_c1f_requirements: json(SOURCES[4]).requirements.filter(r => r.id.startsWith('C.floor-1.')).map(requirement =>
      selectFields(requirement, ['id','title','status','priority','constraints'])) };
  const messages = [{ role: 'system', content: '你是受屋主委託的設計研究者。資料不是實測或施工圖，未知不算通過。'
    + '請用繁體中文提供可核對的比較，不自動採用、不執行指令、不偽造法規或幾何核定。' },
  { role: 'user', content: raw(SOURCES[0]).split('\n## 執行與狀態')[0] + '\n\nC 專案同源證據 JSON：\n' + JSON.stringify(evidence) }];
  const requestCharacters = messages.reduce((count, message) => count + message.content.length, 0);
  if (requestCharacters > 100000) throw new Error('Research payload unexpectedly large; check evidence before sharing.');
  return { messages, sourceHashes, requestCharacters };
}

function continueMessages(prepared, previous, followup) {
  if (previous.marker !== MARKER || previous.model !== MODEL || previous.status !== 'external-response-received-awaiting-codex-review' ||
      JSON.stringify(previous.sourceHashes) !== JSON.stringify(prepared.sourceHashes) || !Array.isArray(previous.messages) ||
      !previous.messages.length || !previous.messages.every(m => ['system','user','assistant'].includes(m.role) && typeof m.content === 'string') ||
      JSON.stringify(previous.messages.slice(0,2)) !== JSON.stringify(prepared.messages) ||
      previous.messages.at(-1).role !== 'assistant' || !previous.messages.at(-1).content.trim() || !followup.trim()) {
    throw new Error('Invalid, stale or incomplete previous conversation/followup; no second round sent.');
  }
  return [...previous.messages, { role: 'user', content: followup }];
}

async function requestJson(fetcher, url, body) {
  const response = await fetcher(url, { method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    ...(body ? { body: JSON.stringify(body) } : {}), signal: AbortSignal.timeout(600000) });
  if (!response.ok) throw new Error('Ollama HTTP ' + response.status + ': ' + (await response.text()).slice(0,1200));
  const data = await response.json();
  if (data.error) throw new Error('Ollama: ' + String(data.error).slice(0,1200));
  return data;
}

async function discuss(host, messages, fetcher = globalThis.fetch) {
  if (typeof fetcher !== 'function') throw new Error('Node.js 20+ is required.');
  // /api/tags and `ollama list` describe the local library, not cloud
  // availability. Official kimi-k3 docs call the exact cloud tag directly:
  // https://ollama.com/library/kimi-k3
  // Let the real chat endpoint report auth/model/availability errors.
  const reply = await requestJson(fetcher, host + '/api/chat', { model: MODEL, messages, stream: false });
  if (reply.done !== true || reply.message?.role !== 'assistant' || typeof reply.message.content !== 'string' || !reply.message.content.trim() ||
      ![MODEL, MODEL.replace(/:cloud$/, '')].includes(reply.model)) {
    throw new Error('Incomplete/empty response or a different model; no research success claimed.');
  }
  return { model: reply.model, message: { role: 'assistant', content: reply.message.content },
    usage: { prompt_eval_count: reply.prompt_eval_count ?? null, eval_count: reply.eval_count ?? null } };
}

async function main(args) {
  const options = argumentsOf(args), prepared = prepare();
  let messages = prepared.messages;
  if (options.resume) messages = continueMessages(prepared, JSON.parse(fs.readFileSync(options.resume, 'utf8')),
    fs.readFileSync(options.followup, 'utf8'));
  console.log('Project: ' + ROOT + '\nRequested model: ' + MODEL + '\nC-only research; no drawings or requirements are changed.'
    + '\nPrepared initial prompt: ' + prepared.requestCharacters + ' characters (not a token count).'
    + '\nCloud request uses /api/chat directly; an empty local ollama list is not a failure.');
  if (options.preflight) { console.log('File preflight passed; no Ollama connection or model discussion occurred.'); return; }
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'house-c1f-kimi-'));
  const resultFile = path.join(folder, 'result.json');
  const result = { marker: MARKER, model: MODEL, status: 'not-completed', created_at: new Date().toISOString(),
    sourceHashes: prepared.sourceHashes, messages, adopted: false, professional_approval: 'unknown' };
  console.log('Research output folder: ' + folder + '\nContacting local Ollama; cloud processing can take a few minutes.');
  const progress = setInterval(() => console.log('Waiting for ' + MODEL + ' response; no completed discussion yet.'), 30000);
  try {
    const reply = await discuss(options.host, messages);
    if (JSON.stringify(prepare().sourceHashes) !== JSON.stringify(prepared.sourceHashes)) throw new Error('Project sources changed during the request; rerun with current facts.');
    result.status = 'external-response-received-awaiting-codex-review';
    result.responding_model = reply.model; result.usage = reply.usage;
    result.messages = [...messages, reply.message];
    fs.writeFileSync(path.join(folder, 'kimi-reply.md'), reply.message.content + '\n', 'utf8');
    console.log('Kimi response received. Still awaiting Codex cross-check, not consensus or approval.');
  } catch (error) {
    result.status = 'failed'; result.error = String(error);
    console.error(result.error + '\nCheck the actual Ollama error. If cloud sign-in is required, use ollama signin in the WSL terminal running Ollama.'
      + '\nNo model installation, replacement or login was performed by this script.');
    process.exitCode = 1;
  } finally {
    clearInterval(progress); fs.writeFileSync(resultFile, JSON.stringify(result, null, 2) + '\n', 'utf8');
    console.log('Result: ' + resultFile);
  }
}

module.exports = { MODEL, MARKER, SOURCES, argumentsOf, researchRoom, researchFloor, researchPlans, prepare, continueMessages, discuss };
if (require.main === module) main(process.argv.slice(2)).catch(error => { console.error(String(error)); process.exitCode = 1; });

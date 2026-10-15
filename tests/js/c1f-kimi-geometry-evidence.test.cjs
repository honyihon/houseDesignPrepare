'use strict';

// Historical research evidence and explicitly limited coordinate probes.
// These tests do not render a plan, contact a model, adopt a layout or certify
// human movement, accessibility, religious rules, construction or legality.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '../..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const json = name => JSON.parse(read(name));
const first = json('inputs/references/c1f-kimi-round1-20261013.json');
const second = json('inputs/references/c1f-kimi-round2-20261013.json');
const audit = json('inputs/references/c1f-kimi-round2-audit-20261013.json');
const probe = audit.preferred_corrected_probe;
const marker = 'C 專案同源證據 JSON：\n';
const initial = second.messages[1].content;
assert.ok(initial.includes(marker));
const evidence = JSON.parse(initial.slice(initial.indexOf(marker) + marker.length));
const archivedItems = evidence.side_bed_candidate.plans.floors[0].rooms.flatMap(r => r.furniture);
const dimensions = pair => pair.slice().sort((a, b) => a - b);
const overlap = (a, b) => Math.max(0, Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0])) *
  Math.max(0, Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]));
const distance = (c, b) => Math.hypot(c[0] - Math.max(b[0], Math.min(c[0], b[0] + b[2])),
  c[1] - Math.max(b[1], Math.min(c[1], b[1] + b[3])));
const inset = (w, d) => (w - 160) * (d - 160) / 1e6;
const area = polygon => Math.abs(polygon.reduce((sum, [x, y], i) => {
  const [nx, ny] = polygon[(i + 1) % polygon.length];
  return sum + x * ny - nx * y;
}, 0)) / 2;
const expand = (b, n) => [b[0] - n, b[1] - n, b[2] + 2 * n, b[3] + 2 * n];

test('round two preserves the real first conversation and immutable reply evidence', () => {
  assert.equal(second.model, 'kimi-k3:cloud');
  assert.ok(['kimi-k3', second.model].includes(second.responding_model));
  assert.equal(second.status, 'external-response-received-awaiting-codex-review');
  assert.equal(second.messages.length, 5);
  assert.deepEqual(second.messages.slice(0, 3), first.messages);
  assert.equal(second.messages[3].content, read('Docs/c1f-kimi-followup-v2.md'));
  assert.equal(read('inputs/references/c1f-kimi-round2-20261013.md'), second.messages[4].content + '\n');
  const digest = crypto.createHash('sha256').update(read(audit.provenance.round2_result)).digest('hex');
  assert.equal(digest, audit.provenance.result_sha256);
  assert.deepEqual(audit.provenance.source_hashes, second.sourceHashes);
  assert.deepEqual(first.sourceHashes, second.sourceHashes);
  // Historical hashes are not required to equal future adopted drawings.
});

test('known model furniture shrinkage is detected; the probe restores archived products', () => {
  assert.ok(second.messages[4].content.includes('沙發 x1500..2400、y8000..8900'));
  assert.ok(second.messages[4].content.includes('茶几 x500..1100、y7950..8850'));
  for (const item of audit.verified_findings.undersized_kimi_furniture) {
    const source = archivedItems.find(i => i.catalog_id === item.catalog_id);
    assert.deepEqual(dimensions(item.required_dimensions_mm), dimensions([source.width_mm, source.depth_mm]));
    assert.notDeepEqual(dimensions(item.body.slice(2)), dimensions(item.required_dimensions_mm));
  }
  for (const item of probe.furniture) {
    const source = archivedItems.find(i => i.catalog_id === item.catalog_id);
    assert.ok(source);
    assert.deepEqual(dimensions(item.body.slice(2)), dimensions([source.width_mm, source.depth_mm]));
  }
});

test('door hits a fixed shoe cabinet and the original front-WC turn circle enters the WC', () => {
  const collision = audit.verified_findings.kimi_door_hits_cabinet;
  const [x, y] = collision.witness;
  const [bx, by, bw, bh] = collision.body;
  assert.ok(x > bx && x < bx + bw && y > by && y < by + bh);
  for (const {hinge} of collision.witnesses) {
    assert.ok(y > hinge[1]);
    assert.ok(Math.hypot(x - hinge[0], y - hinge[1]) < 1000);
  }
  assert.equal(collision.operation_bounding_overlap_sqm, 0.3);
  const turn = audit.verified_findings.kimi_front_wc_circle_intersection;
  assert.ok(distance(turn.circle, turn.wc) < turn.radius_mm);
  const [w, d] = audit.verified_findings.kimi_bare_entry_rectangle_can_fit_1500_circle.clear_dimensions_mm;
  assert.ok(w >= 1500 && d >= 1500); // empty rectangle only, not furnished entry approval
  assert.equal(audit.verified_findings.kimi_wc_entry_sink_bottleneck.remaining_straight_entry_span_mm, 320);
});

test('corrected fixed bodies and limited turn probes have the stated planar separation', () => {
  for (let i = 0; i < probe.furniture.length; i++) {
    for (let j = i + 1; j < probe.furniture.length; j++) {
      assert.equal(overlap(probe.furniture[i].body, probe.furniture[j].body), 0);
    }
  }
  const livingCells = [[0, 7100, 4000, 1930], [4000, 7500, 2000, 2000], [2400, 9030, 1600, 470]];
  for (const item of probe.furniture.filter(i => i.zone === 'living')) {
    assert.equal(livingCells.reduce((sum, cell) => sum + overlap(item.body, cell), 0), item.body[2] * item.body[3]);
  }
  for (const circle of Object.values(probe.turning_circles)) {
    for (const item of probe.furniture) {
      assert.ok(distance(circle, item.body) >= circle[2]);
      if (item.operation) assert.ok(distance(circle, item.operation) >= circle[2]);
    }
  }
  const backup = audit.backup_equal_basis;
  assert.ok(distance(probe.turning_circles.entrance_cross_dining, expand(probe.zones.public_wc, 80)) > 750);
  assert.ok(distance(backup.cross_zone_turn_circle, expand(backup.zones.public_wc, 80)) > 750);
  // The corrected door no longer touches the fixed cabinet, but its operation
  // still shares floor with door movement. This is not simultaneous clearance.
  assert.ok(probe.main_door.x_interval[1] < probe.furniture.find(i => i.catalog_id === 'shoe-cabinet').body[0]);
  assert.match(probe.shared_operation.main_door_sweep_with_shoe_operation, /sequential-only-unverified/);
  assert.equal(probe.shared_operation.kitchen_counter_fridge_operation_overlap_sqm, 0.42);
});

test('area comparison repairs the kitchen and entry on the same discussion basis', () => {
  const livingMM2 = area(probe.zones.living_polygon);
  assert.equal(livingMM2, 12472000);
  assert.equal((livingMM2 + 12800000) / 1e6, probe.living_dining_nominal_sqm);
  assert.equal(livingMM2 + 12800000 + 7200000 + 1128000, 33600000);
  assert.equal(inset(2400, 3070), 6.5184);
  assert.equal(audit.backup_equal_basis.living_dining_nominal_sqm, probe.living_dining_nominal_sqm);
  assert.equal(inset(2000, 1800), 3.0176);
  assert.ok(inset(2000, 1400) < 3);
  for (const fixture of probe.public_wc_fixtures) {
    assert.deepEqual(dimensions(fixture.body.slice(2)), dimensions(fixture.product_dimensions_mm));
  }
  assert.equal(overlap(probe.public_wc_fixtures[0].operation, probe.public_wc_fixtures[1].operation), 0);
});

test('HVAC/stair findings are conditional calculations, not adopted geometry or permits', () => {
  assert.equal(audit.verified_findings.existing_hvac_intrudes_new_wc.overlap_y_mm, 155);
  assert.ok(overlap(audit.verified_findings.existing_hvac_intrudes_new_wc.body, probe.zones.public_wc) > 0);
  assert.equal(overlap(probe.hvac.body, probe.zones.public_wc), 0);
  for (const s of audit.verified_findings.stair_same_parallel_u_geometry) {
    assert.equal(s.run_mm, (s.assumed_risers / 2 - 1) * 270);
    assert.equal(s.extra_parallel_flight_depth_vs_18_mm, s.run_mm - 2160);
  }
  assert.equal(audit.adopted, false);
  assert.equal(audit.professional_approval, 'unknown');
  assert.equal(audit.rendered_qa_performed, false);
  assert.equal(probe.route_centerlines_only.verified_clear_route_width_mm, null);
  assert.equal(probe.hvac.manufacturer_and_new_route_status, 'unknown');
});

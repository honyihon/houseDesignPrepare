const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {resolvePython} = require('../e2e/python.cjs');

for (const platform of ['linux', 'win32']) {
  test(`Python selection honors explicit interpreter on ${platform}`, () => {
    assert.equal(resolvePython({platform, env: {PYTHON: '/custom path/python'}, exists: () => false}), '/custom path/python');
  });
  test(`fresh CI checkout uses PATH Python on ${platform}`, () => {
    assert.equal(resolvePython({platform, env: {}, exists: () => false}), platform === 'win32' ? 'python' : 'python3');
  });
  test(`existing project environment is retained on ${platform}`, () => {
    const root = path.resolve('/fixture repo');
    const expected = path.join(root, '.venv', platform === 'win32' ? 'Scripts' : 'bin', platform === 'win32' ? 'python.exe' : 'python');
    assert.equal(resolvePython({root, platform, env: {}, exists: candidate => candidate === expected}), expected);
  });
}

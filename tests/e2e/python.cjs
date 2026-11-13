const fs = require('node:fs');
const path = require('node:path');

function resolvePython({env = process.env, platform = process.platform,
  root = path.resolve(__dirname, '../..'), exists = fs.existsSync} = {}) {
  if (env.PYTHON) return env.PYTHON;
  const local = path.join(root, '.venv', platform === 'win32' ? 'Scripts' : 'bin',
    platform === 'win32' ? 'python.exe' : 'python');
  return exists(local) ? local : platform === 'win32' ? 'python' : 'python3';
}

module.exports = {resolvePython};

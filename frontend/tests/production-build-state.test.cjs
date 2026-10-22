const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

test('production build reuse rejects changed, added, deleted inputs and incomplete output', () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'campus-build-state-'));
  try {
    const root = path.join(temporary, 'frontend');
    const script = path.join(root, 'scripts', 'production-build-state.cjs');
    fs.mkdirSync(path.dirname(script), { recursive: true });
    fs.copyFileSync(path.join(__dirname, '../scripts/production-build-state.cjs'), script);
    fs.mkdirSync(path.join(root, 'src'));
    const source = path.join(root, 'src', 'page.tsx');
    fs.writeFileSync(source, 'original');
    for (const file of ['BUILD_ID', 'routes-manifest.json', 'prerender-manifest.json', 'server/pages-manifest.json']) {
      const target = path.join(root, '.next', file);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, '{}');
    }
    const invoke = flag => spawnSync(process.execPath, [script, flag], {
      env: { ...process.env, NEXT_BUILD_DIR: '.next' }, encoding: 'utf8',
    }).status;
    assert.equal(invoke('--check'), 1); // Build lacks a recorded input fingerprint.
    assert.equal(invoke('--record'), 0);
    assert.equal(invoke('--check'), 0);
    fs.writeFileSync(source, 'changed');
    assert.equal(invoke('--check'), 1);
    assert.equal(invoke('--record'), 0);
    const added = path.join(root, 'src', 'new.tsx');
    fs.writeFileSync(added, 'new');
    assert.equal(invoke('--check'), 1);
    assert.equal(invoke('--record'), 0);
    fs.unlinkSync(added);
    assert.equal(invoke('--check'), 1);
    assert.equal(invoke('--record'), 0);
    fs.unlinkSync(path.join(root, '.next', 'routes-manifest.json'));
    assert.equal(invoke('--check'), 1);
    assert.equal(invoke('--record'), 1);
  } finally {
    // Only remove the exact directory allocated by mkdtemp for this test.
    assert.ok(path.resolve(temporary).startsWith(path.resolve(os.tmpdir()) + path.sep));
    fs.rmSync(temporary, { recursive: true, force: true });
  }
});

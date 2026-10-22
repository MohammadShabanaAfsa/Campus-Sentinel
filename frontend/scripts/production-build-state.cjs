// A successful build records its inputs; additions/deletions also invalidate it.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const build = path.resolve(root, process.env.NEXT_BUILD_DIR || '.next');
const hash = crypto.createHash('sha256');
function include(relative) {
  const target = path.resolve(root, relative);
  hash.update(relative + '\0');
  if (!fs.existsSync(target)) { hash.update('missing\0'); return; }
  if (fs.statSync(target).isDirectory()) {
    for (const entry of fs.readdirSync(target).sort()) include(path.join(relative, entry));
  } else { hash.update(fs.readFileSync(target)); }
}
for (const input of ['src', 'public', 'scripts/production-build-state.cjs', 'scripts/next-typescript-config.cjs',
  'package.json', 'package-lock.json', 'next.config.js', 'tsconfig.json',
  'tailwind.config.ts', 'tailwind.config.js', 'postcss.config.js',
  '.eslintrc.json', '.env', '.env.local', '.env.production', '.env.production.local', '../.env']) include(input);
for (const key of ['DOCKER_BUILD', 'NEXT_PUBLIC_API_URL', 'NEXT_PUBLIC_WS_URL',
  'NEXT_PUBLIC_CAMPUS_LAT', 'NEXT_PUBLIC_CAMPUS_LNG', 'NEXT_PUBLIC_CAMPUS_ZOOM']) {
  hash.update(key + '=' + (process.env[key] || '') + '\0');
}
const fingerprint = hash.digest('hex');
const marker = path.join(build, '.campus-source-hash');
const complete = ['BUILD_ID', 'routes-manifest.json', 'prerender-manifest.json',
  'server/pages-manifest.json'].every(file => fs.existsSync(path.join(build, file)));
if (process.argv.includes('--record')) {
  if (!complete) { console.error('Production build is incomplete.'); process.exit(1); }
  fs.writeFileSync(marker, fingerprint + '\n');
} else {
  process.exit(complete && fs.existsSync(marker) && fs.readFileSync(marker, 'utf8').trim() === fingerprint ? 0 : 1);
}

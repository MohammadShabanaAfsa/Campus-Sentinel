// Alternate Next outputs must never add their generated types to shared tsconfig.
const fs = require('node:fs');
const path = require('node:path');

function nextTypeScriptConfig(root, distDir) {
  if (!/^\.next(?:-[a-zA-Z0-9_-]+)?$/.test(distDir)) {
    throw new Error('NEXT_BUILD_DIR must be .next or a .next-<name> directory inside frontend');
  }
  if (distDir === '.next') return { tsconfigPath: 'tsconfig.json' };
  const name = `${distDir}.tsconfig.json`;
  const config = {
    extends: './tsconfig.json',
    compilerOptions: { tsBuildInfoFile: `./${distDir}/cache/typescript.tsbuildinfo` },
    include: ['next-env.d.ts', 'src/**/*.ts', 'src/**/*.tsx', `${distDir}/types/**/*.ts`],
    // Override shared .next-* exclusion so THIS output's generated types are checked.
    exclude: ['node_modules'],
  };
  const target = path.join(root, name);
  const text = JSON.stringify(config, null, 2) + '\n';
  if (!fs.existsSync(target) || fs.readFileSync(target, 'utf8') !== text) {
    fs.writeFileSync(target, text);
  }
  return { tsconfigPath: name };
}

module.exports = { nextTypeScriptConfig };

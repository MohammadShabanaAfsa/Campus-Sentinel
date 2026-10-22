const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const ts = require('typescript');
const { nextTypeScriptConfig } = require('../scripts/next-typescript-config.cjs');
test('temporary Next types stay isolated from production roots', async () => {
 const root = fs.mkdtempSync(path.join(os.tmpdir(), 'campus-types-'));
 try {
  const base = fs.readFileSync(path.join(__dirname, '../tsconfig.json'), 'utf8');
  fs.writeFileSync(path.join(root, 'tsconfig.json'), base);
  for (const file of ['src/page.tsx', '.next/types/current.ts', '.next-activity-verification/types/app/agents/page.ts']) {
   fs.mkdirSync(path.dirname(path.join(root,file)), {recursive:true}); fs.writeFileSync(path.join(root,file),'export {};');
  }
  const files = name => ts.parseJsonConfigFileContent(ts.readConfigFile(path.join(root,name),ts.sys.readFile).config, ts.sys, root).fileNames.map(f=>path.relative(root,f).replaceAll('\\','/')).sort();
  assert.deepEqual(files('tsconfig.json'), ['.next/types/current.ts','src/page.tsx']);
  const config = nextTypeScriptConfig(root,'.next-activity-verification');
  assert.deepEqual(files(config.tsconfigPath), ['.next-activity-verification/types/app/agents/page.ts','src/page.tsx']);
  await require('next/dist/lib/typescript/writeConfigurationDefaults').writeConfigurationDefaults(ts,path.join(root,config.tsconfigPath),false,true,'.next-activity-verification',false);
  assert.equal(fs.readFileSync(path.join(root,'tsconfig.json'),'utf8'),base);
  fs.unlinkSync(path.join(root,'.next-activity-verification/types/app/agents/page.ts'));
  assert.deepEqual(files('tsconfig.json'), ['.next/types/current.ts','src/page.tsx']);
 } finally { assert.ok(root.startsWith(os.tmpdir()+path.sep)); fs.rmSync(root,{recursive:true,force:true}); }
});
test('output paths cannot escape frontend',()=>{
 for(const value of ['../other','C:\\outside','/tmp/build','.next/../../outside']) assert.throws(()=>nextTypeScriptConfig(__dirname,value),/NEXT_BUILD_DIR/);
});

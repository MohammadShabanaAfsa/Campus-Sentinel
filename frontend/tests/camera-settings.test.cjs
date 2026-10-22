const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function harness() {
  const state = []; let index = 0, saved = 0;
  const calls = [];
  const api = { post: async (url, data) => { calls.push({url, data}); return {data:{message:'No frames received'}}; } };
  const camera = {id:'classroom-id', name:'Classroom', rtsp_url:'http://old:8080/video', location_name:'Classroom', latitude:17.3547, longitude:78.5936, zone_type:'classroom'};
  const source = fs.readFileSync(require.resolve('../src/components/cameras/EditCameraModal.tsx'), 'utf8');
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS, jsx:ts.JsxEmit.ReactJSX}}).outputText, {
    exports, require: name => name === 'react' ? {useState: initial => {
      const slot = index++; if (!(slot in state)) state[slot] = initial;
      return [state[slot], value => state[slot] = value];
    }} : name === '@/lib/api' ? {default:api, camerasApi:{update:async (id,payload) => calls.push({id,payload})}} : require(name),
  });
  const render = () => { index = 0; return exports.EditCameraModal({camera,onClose:()=>{},onSaved:()=>saved++}); };
  const nodes = (tree, predicate) => {
    if (Array.isArray(tree)) return tree.flatMap(child => nodes(child, predicate));
    if (!tree || typeof tree !== 'object') return [];
    const children = [].concat(tree.props?.children || []);
    return [...(predicate(tree) ? [tree] : []), ...children.flatMap(child => nodes(child,predicate))];
  };
  return {render,nodes,calls,api,saved:()=>saved};
}
const settle = async () => { for(let i=0;i<20;i++) await Promise.resolve(); };

test('editing source PATCHes the existing ID and preserves untouched coordinates', async () => {
  const h = harness(); let tree = h.render();
  const input = h.nodes(tree, node => node.type === 'input')[1];
  input.props.onChange({target:{value:'http://new:8080/video'}});
  tree = h.render();
  h.nodes(tree,node=>node.type==='form')[0].props.onSubmit({preventDefault(){}});
  await settle();
  assert.equal(h.calls[0].id, 'classroom-id');
  assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0].payload)), {rtsp_url:'http://new:8080/video'});
  assert.equal(h.saved(),1);
});

test('connection test reports camera failure and restart targets only the saved camera', async () => {
  const h = harness(); let tree = h.render();
  h.nodes(tree,node=>node.type==='button' && node.props.children==='Test Connection')[0].props.onClick();
  await settle(); tree = h.render();
  assert.equal(h.nodes(tree,node=>node.props?.role==='status')[0].props.children,'No frames received');
  assert.equal(h.calls[0].url,'/api/v1/cameras/test-source');
  h.nodes(tree,node=>node.type==='button' && node.props.children==='Restart Camera')[0].props.onClick();
  await settle();
  assert.equal(h.calls[1].url,'/api/v1/streams/classroom-id/restart');
});

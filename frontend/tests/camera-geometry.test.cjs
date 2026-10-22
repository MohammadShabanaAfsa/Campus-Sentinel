const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const ts=require('typescript');
const settle=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
async function harness(initialMode='zone',scenario='ok'){
 const hooks=[];let index=0;const pending=[];const listeners=new Map();const zones=[];let line=null;const calls=[];let token=scenario==='missing-session'?null:'current-token';
 const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>Object.is(v,b[i]));
 const api={get:async url=>{if(scenario==='401')throw {response:{status:401}};if(url.endsWith('/snapshot')){if(scenario==='unavailable')throw {response:{status:404}};return{data:{frame_b64:'jpeg-data'}};}return{data:url.endsWith('/zones')?zones.map(z=>({...z})):line};},
  post:async(url,data)=>{calls.push({method:'POST',url,data});zones.push({id:'zone-id',...data});},
  put:async(url,data)=>{calls.push({method:'PUT',url,data});if(url.endsWith('/counting-line'))line=data;else Object.assign(zones[0],data);},
  delete:async url=>{calls.push({method:'DELETE',url});if(url.endsWith('/counting-line'))line=null;else zones.splice(0);}};
 const exports={};const source=fs.readFileSync(require.resolve('../src/components/cameras/ZoneDrawerModal.tsx'),'utf8');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,{
  exports,window:{addEventListener:(key,fn)=>{if(!listeners.has(key))listeners.set(key,new Set());listeners.get(key).add(fn);},removeEventListener:(key,fn)=>listeners.get(key)?.delete(fn)},
  require:name=>name==='react'?{
   useState:initial=>{const slot=index++;if(!(slot in hooks))hooks[slot]={value:initial};return[hooks[slot].value,value=>hooks[slot].value=typeof value==='function'?value(hooks[slot].value):value];},
   useCallback:(fn,deps)=>{const slot=index++;if(!same(hooks[slot]?.deps,deps))hooks[slot]={value:fn,deps};return hooks[slot].value;},
   useEffect:(fn,deps)=>{const slot=index++;if(!same(hooks[slot]?.deps,deps)){const old=hooks[slot];hooks[slot]={deps};pending.push(()=>{old?.cleanup?.();hooks[slot].cleanup=fn();});}},
  }:name==='@/lib/api'?{default:api}:name==='@/lib/session'?{getAccessToken:()=>token,SESSION_EXPIRED_EVENT:'expired'}:require(name),
 });
 const render=()=>{index=0;const tree=exports.ZoneDrawerModal({camera:{id:'camera-id',name:'Entrance'},onClose:()=>{},initialMode});while(pending.length)pending.shift()();return tree;};
 function nodes(tree,predicate){if(Array.isArray(tree))return tree.flatMap(t=>nodes(t,predicate));if(!tree||typeof tree!=='object')return[];return[...(predicate(tree)?[tree]:[]),...nodes(tree.props?.children,predicate)];}
 const find=(type)=>nodes(render(),n=>n.type===type);
 const button=name=>nodes(render(),n=>n.type==='button'&&n.props.children===name)[0];
 const points=()=>nodes(render(),n=>n.props?.['data-testid']==='draft-point');
 const draft=kind=>nodes(render(),n=>n.props?.['data-testid']===kind)[0];
 const image=()=>find('img')[0];
 const loadImage=()=>image().props.onLoad({currentTarget:{naturalWidth:640,naturalHeight:480}});
 const click=(x,y)=>find('svg')[0]?.props.onClick({clientX:x,clientY:y,currentTarget:{getBoundingClientRect:()=>({left:100,top:50,width:320,height:240})}});
 const expire=()=>{token=null;for(const fn of listeners.get('expired')||[])fn();};
 render();await settle();render();
 return{render,nodes,find,button,click,calls,zones,line:()=>line,image,loadImage,points,draft,expire};
}

test('frame loads as an image with matching transparent positioned SVG',async()=>{
 const h=await harness();assert.ok(h.image().props.src.startsWith('data:image/jpeg;base64,'));assert.equal(h.find('svg').length,0);
 assert.equal(h.button('Draw Restricted Zone').props.disabled,true);h.loadImage();const svg=h.find('svg')[0];
 assert.equal(svg.props.viewBox,'0 0 640 480');assert.match(svg.props.className,/absolute inset-0.*w-full h-full/);
 assert.equal(h.button('Draw Restricted Zone').props.disabled,false);
});
test('point marker and line appear immediately, third point closes visible polygon; Save/Edit/Clear work',async()=>{
 const h=await harness();h.loadImage();h.button('Draw Restricted Zone').props.onClick();
 h.click(132,74);assert.equal(h.points().length,1);assert.equal(h.points()[0].props.cx,64);
 h.click(388,74);assert.equal(h.points().length,2);assert.equal(h.draft('draft-line').props.points,'64,48 576,48');
 h.click(388,266);assert.equal(h.points().length,3);assert.equal(h.draft('draft-polygon').props.points,'64,48 576,48 576,432');
 await h.button('Save').props.onClick();assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0].data.zone_points)),[{x:.1,y:.1},{x:.9,y:.1},{x:.9,y:.9}]);
 h.button('Edit').props.onClick();await h.button('Save').props.onClick();assert.equal(h.calls[1].method,'PUT');
 await h.button('Clear').props.onClick();assert.equal(h.zones.length,0);
});
test('vehicle two-click line is visible immediately and saves normalized points; Clear works',async()=>{
 const h=await harness('line');h.loadImage();h.button('Draw Counting Line').props.onClick();h.click(132,170);h.click(388,170);
 assert.equal(h.points().length,2);assert.equal(h.draft('draft-line').props.points,'64,240 576,240');h.click(200,200);assert.equal(h.points().length,2);
 await h.button('Save').props.onClick();assert.deepEqual(JSON.parse(JSON.stringify(h.line().points)),[{x:.1,y:.5},{x:.9,y:.5}]);
 h.button('Edit').props.onClick();await h.button('Save').props.onClick();await h.button('Clear').props.onClick();assert.equal(h.line(),null);
});
for(const scenario of ['missing-session','401'])test(`${scenario} shows sign-in guidance instead of blank drawing area`,async()=>{
 const h=await harness('zone',scenario);assert.equal(h.image(),undefined);assert.equal(h.find('svg').length,0);
 assert.ok(h.nodes(h.render(),n=>n.type==='p'&&n.props.children==='Please sign in again').length);
 assert.equal(h.button('Draw Restricted Zone').props.disabled,true);assert.equal(h.calls.length,0);
});
test('session expiry while editing hides frame/overlay and prevents Save',async()=>{
 const h=await harness();h.loadImage();h.button('Draw Restricted Zone').props.onClick();h.click(132,74);h.expire();
 assert.equal(h.find('svg').length,0);assert.equal(h.image(),undefined);assert.equal(h.button('Draw Restricted Zone').props.disabled,true);
});
test('unavailable snapshot or failed image decode blocks drawing with explicit message',async()=>{
 const h=await harness('zone','unavailable');assert.equal(h.image(),undefined);assert.ok(h.nodes(h.render(),n=>n.type==='p'&&n.props.children==='Camera frame unavailable').length);
 assert.equal(h.button('Draw Restricted Zone').props.disabled,true);
 const decoded=await harness();decoded.image().props.onError();assert.equal(decoded.find('svg').length,0);assert.equal(decoded.button('Draw Restricted Zone').props.disabled,true);
});
test('Cancel discards unsaved geometry without sending a write',async()=>{
 const h=await harness();h.loadImage();h.button('Draw Restricted Zone').props.onClick();h.click(132,74);h.button('Cancel').props.onClick();assert.equal(h.points().length,0);assert.equal(h.calls.length,0);
});
test('loaded frame and mode selection immediately accept drawing clicks',async()=>{
 const h=await harness();h.loadImage();h.click(132,74);assert.equal(h.points().length,1);
 h.button('Vehicle Count').props.onClick();h.click(132,170);h.click(388,170);
 assert.equal(h.points().length,2);assert.equal(h.draft('draft-line').props.points,'64,240 576,240');
});

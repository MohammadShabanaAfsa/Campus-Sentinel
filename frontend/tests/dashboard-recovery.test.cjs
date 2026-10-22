const assert = require("node:assert/strict");
const { test, beforeEach } = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("typescript");
const src = path.resolve(__dirname, "../src");
const resolve = Module._resolveFilename;
Module._resolveFilename = function(request, ...args) {
  return resolve.call(this, request.startsWith("@/") ? path.join(src, request.slice(2)) : request, ...args);
};
for (const extension of [".ts", ".tsx"]) {
  require.extensions[extension] = (module, file) => module._compile(ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2021, esModuleInterop: true }, fileName: file,
  }).outputText, file);
}
const session = require("../src/lib/session.ts");
const { default: api } = require("../src/lib/api.ts");
const { useAppStore: store } = require("../src/store/useAppStore.ts");
const { startRealtimeEvents } = require("../src/hooks/useRealtimeEvents.ts");
test('bootstrap and WebSocket copies of the same alert remain one dashboard row', () => {
  store.setState({alerts:[]});
  const alert={id:'same-alert',title:'PHONE USE',status:'active',severity:'low',created_at:new Date().toISOString()};
  store.getState().addAlert(alert);store.getState().addAlert({...alert,title:'PHONE USE confirmed'});
  assert.equal(store.getState().alerts.length,1);
  assert.equal(store.getState().alerts[0].title,'PHONE USE confirmed');
});
const { startCameraStream } = require("../src/lib/cameraStream.ts");
const token = (seconds = 3600, id = "user") => `header.${Buffer.from(JSON.stringify({ type:"access", sub:id, exp:Date.now()/1000+seconds })).toString("base64url")}.signature`;
let cookie, calls, timers, intervals, sockets, nextTimer;
const payload = { overall_score:90, risk_level:"safe", crowd_score:100, loitering_score:100, access_score:90, anomaly_score:100, anomaly_count:0, active_alerts:1, updated_at:new Date().toISOString() };

beforeEach(() => {
  const storage = new Map();
  global.localStorage = { getItem:key=>storage.get(key)||null, setItem:(key,value)=>storage.set(key,value), removeItem:key=>storage.delete(key) };
  global.window = new EventTarget();
  cookie = "";
  global.document = { get cookie() { return cookie; }, set cookie(value) { cookie = value.includes("Max-Age=0") ? "" : value; } };
  calls = [];
  api.defaults.adapter = async config => {
    calls.push(config);
    return { status:200, data:config.url === "/health" ? {status:"healthy"} : payload, headers:{}, config };
  };
  session.saveSession(token());
  store.setState({ cameras:[], camerasLoaded:false, cameraError:false, csi:null, csiError:false, isConnected:false, backendConnected:null, authenticationRequired:false });
  timers = new Map(); intervals = new Map(); sockets=[]; nextTimer=0;
  global.setTimeout = (fn,delay) => { const id=++nextTimer; timers.set(id,{fn,delay}); return id; };
  global.clearTimeout = id => timers.delete(id);
  global.setInterval = (fn,delay) => { const id=++nextTimer; intervals.set(id,{fn,delay}); return id; };
  global.clearInterval = id => intervals.delete(id);
  global.WebSocket = class {
    static OPEN=1; static CLOSING=2;
    readyState=0;
    constructor(url) { this.url=url; sockets.push(this); }
    open() { this.readyState=1; this.onopen?.(); }
    close() { this.readyState=3; this.onclose?.({code:1000}); }
    drop(code=1006) { this.readyState=3; this.onclose?.({code}); }
    send() {}
  };
});
const settle = async () => { for(let i=0;i<12;i++) await Promise.resolve(); };
const runRetry = () => { const [id,item] = timers.entries().next().value; timers.delete(id); assert.equal(item.delay,3000); item.fn(); };

test("expired access tokens clear storage and route cookie together", () => {
  session.saveSession(token(-60));
  assert.equal(session.getAccessToken(),null);
  assert.equal(localStorage.getItem("access_token"),null);
  assert.equal(cookie,"");
});

test("parallel 401 responses expire one session without navigating or erasing cameras", async () => {
  const cameras=[{id:"camera", name:"Classroom", status:"online"}];
  store.getState().setCameras(cameras);
  let expired=0;
  window.addEventListener(session.SESSION_EXPIRED_EVENT,()=>expired++);
  api.defaults.adapter=async config=>Promise.reject({config,response:{status:401}});
  await Promise.allSettled([api.get("/api/v1/cameras/"),api.get("/api/v1/csi/campus")]);
  assert.equal(expired,1);
  assert.equal(cookie,"");
  assert.equal(store.getState().cameras,cameras);
  assert.equal(window.location,undefined);
});

test("late 401 from an older token preserves a newer login", async () => {
  const old=localStorage.getItem("access_token");
  session.saveSession(token(3600,"new-user"));
  api.defaults.adapter=async config=>Promise.reject({config:{...config,headers:{Authorization:`Bearer ${old}`}},response:{status:401}});
  await assert.rejects(api.get("/api/v1/csi/campus"));
  assert.ok(cookie.includes(localStorage.getItem("access_token")));
  assert.notEqual(localStorage.getItem("access_token"),old);
});

test("bad login credentials and temporary server failures do not clear a valid session", async () => {
  const current=localStorage.getItem("access_token");
  api.defaults.adapter=async config=>Promise.reject({config,response:{status:config.url.includes("login")?401:503}});
  await assert.rejects(api.post("/api/v1/auth/login",{}));
  await assert.rejects(api.get("/api/v1/csi/campus"));
  assert.equal(localStorage.getItem("access_token"),current);
});

test("middleware sends an expired cookie to stable login and clears it", () => {
  const { NextRequest } = require("next/server");
  const { middleware } = require("../src/middleware.ts");
  const request = url => new NextRequest(`http://localhost:3000${url}`, {headers:{cookie:`cs_token=${token(-60)}`}});
  const dashboard=middleware(request("/dashboard"));
  assert.equal(dashboard.status,307);
  assert.match(dashboard.headers.get("location"),/\/login/);
  assert.match(dashboard.headers.get("set-cookie"),/cs_token=;/);
  const login=middleware(request("/login"));
  assert.equal(login.status,200);
  assert.equal(login.headers.get("location"),null);
});

test("CSI failure is independent of API health, realtime connection, and retained cameras", async () => {
  const cameras=[{id:"camera", status:"online"}];
  store.getState().setCameras(cameras);
  store.getState().updateCSI(payload);
  api.defaults.adapter=async config => config.url === "/health" ? {config,status:200,data:{status:"healthy"}} : Promise.reject(new Error("CSI unavailable"));
  const cleanup=startRealtimeEvents();
  sockets[0].open();
  await settle();
  assert.equal(store.getState().isConnected,true);
  assert.equal(store.getState().backendConnected,true);
  assert.equal(store.getState().csiError,true);
  assert.equal(store.getState().cameras,cameras);
  assert.equal(store.getState().csi.overall_score,90);
  cleanup();
});

test("a classroom capture error keeps the dashboard live and Entrance online", () => {
  store.setState({backendConnected:true, isConnected:true});
  store.getState().setCameras([
    {id:"entrance",status:"online"},
    {id:"classroom",status:"error",last_error:"Camera source unreachable: connection timed out"},
  ]);
  assert.equal(store.getState().backendConnected,true);
  assert.equal(store.getState().isConnected,true);
  assert.equal(store.getState().cameras[0].status,"online");
  assert.equal(store.getState().cameraError,false);
});

test("events disconnect schedules one delayed retry, retains cameras, and cleans up on unmount", async () => {
  const cameras=[{id:"camera",status:"online"}];
  store.getState().setCameras(cameras);
  const cleanup=startRealtimeEvents();
  sockets[0].open(); sockets[0].drop();
  assert.equal(timers.size,1);
  assert.equal(store.getState().cameras,cameras);
  runRetry(); sockets[1].open();
  assert.equal(sockets.filter(ws=>ws.readyState<2).length,1);
  cleanup();
  assert.equal(timers.size,0); assert.equal(intervals.size,0);
  await settle();
});

test("Strict Mode cleanup ignores late callbacks from the first socket", async () => {
  const firstCleanup=startRealtimeEvents();
  const staleOpen=sockets[0].onopen;
  firstCleanup();
  const secondCleanup=startRealtimeEvents();
  staleOpen();
  assert.equal(store.getState().isConnected,false);
  sockets[1].open();
  assert.equal(sockets.filter(ws=>ws.readyState<2).length,1);
  secondCleanup();
  await settle();
});

test("camera sockets retry at 3 seconds and manual replacement cannot leave competing sockets", () => {
  const callbacks={onConnected:()=>{},onMessage:()=>{}};
  const stop=startCameraStream("camera",callbacks);
  sockets[0].open(); sockets[0].drop();
  runRetry();
  assert.equal(sockets.filter(ws=>ws.readyState<2).length,1);
  stop();
  const stopReplacement=startCameraStream("camera",callbacks);
  assert.equal(timers.size,0);
  assert.equal(sockets.filter(ws=>ws.readyState<2).length,1);
  stopReplacement();
});

test("camera retries stop after five failed attempts and session expiry stops all sockets", async () => {
  let error="";
  const stopCamera=startCameraStream("camera",{onConnected:()=>{},onMessage:()=>{},onError:value=>error=value});
  for(let i=0;i<5;i++) { sockets.at(-1).drop(); runRetry(); }
  sockets.at(-1).drop();
  assert.equal(timers.size,0);
  assert.match(error,/multiple attempts/);
  const stopEvents=startRealtimeEvents();
  session.clearSession();
  assert.equal(sockets.filter(ws=>ws.readyState<2).length,0);
  assert.equal(store.getState().authenticationRequired,true);
  stopCamera(); stopEvents(); await settle();
});

test('alert deletion removes only its dashboard fixture row', () => {
  const { handleRealtimeMessage } = require('../src/hooks/useRealtimeEvents.ts');
  store.setState({alerts:[]});
  for (const id of ['keep','fixture']) handleRealtimeMessage({type:'new_alert',alert:{id,title:id,status:'active',severity:'low',created_at:new Date().toISOString()}});
  handleRealtimeMessage({type:'alert_deleted',alert_id:'fixture'});
  assert.deepEqual(store.getState().alerts.map(a=>a.id),['keep']);
});

test('all alert types reach the real dashboard store and render', () => {
  const { handleRealtimeMessage } = require('../src/hooks/useRealtimeEvents.ts');
  const captured = path.resolve(__dirname,'../../logs/stabilization-dashboard-events.json');
  const labels=['SLEEPING','TALKING','PHONE USE','EATING','RUNNING','SUDDEN ACCELERATION','LOITERING','RESTRICTED AREA PROHIBITED','FALL DETECTED','CROWD DENSITY','CROWD SURGE','SUSPECTED FIGHT','ABANDONED BAG','AFTER-HOURS PRESENCE','EMERGENCY EXIT BLOCKED'];
  const messages=fs.existsSync(captured) ? JSON.parse(fs.readFileSync(captured,'utf8')) : labels.map((title,index)=>({type:'new_alert',alert:{id:`fixture-${index}`,title,status:'active',severity:'low',created_at:new Date().toISOString(),threat_score:.2}}));
  store.setState({alerts:[]});
  for (const msg of messages) {handleRealtimeMessage(msg);handleRealtimeMessage(msg);}
  assert.equal(store.getState().alerts.length,messages.length);
  const exports={};
  const source=fs.readFileSync(path.join(src,'components/alerts/AlertPanel.tsx'),'utf8');
  require('node:vm').runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText,{
    exports,require:name=>name==='react'?{useEffect:()=>{}}:name==='@/store/useAppStore'?{useAppStore:selector=>selector(store.getState())}:require(name),
  });
  const html=require('react-dom/server').renderToStaticMarkup(exports.AlertPanel());
  for(const label of labels) assert.ok(html.includes(label),`Missing renderable ${label}`);
  for(const msg of messages) handleRealtimeMessage({type:'alert_deleted',alert_id:msg.alert.id});
  assert.equal(store.getState().alerts.length,0);
});

test('reconnect and Redis resync recover missed alerts without duplicate rows', async () => {
 store.setState({alerts:[]});
 const missed={id:'missed',title:'FALL DETECTED',status:'active',severity:'high',created_at:new Date().toISOString()};
 api.defaults.adapter=async config=>({status:200,config,headers:{},data:config.url==='/api/v1/alerts/'?[missed]:config.url==='/health'?{status:'healthy'}:payload});
 const cleanup=startRealtimeEvents();sockets[0].open();await settle();
 assert.equal(store.getState().alerts.filter(a=>a.id==='missed').length,1);
 sockets[0].onmessage({data:JSON.stringify({type:'realtime_resync'})});await settle();
 assert.equal(store.getState().alerts.filter(a=>a.id==='missed').length,1);
 cleanup();
});

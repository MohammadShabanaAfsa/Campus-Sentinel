const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("typescript");
const src = path.resolve(__dirname, "../src");
// Chart layout needs browser dimensions; test the real badge/gauge text and store.
const load = Module._load;
Module._load = function (request, ...args) {
  if (request === "recharts") {
    const React = require("react");
    const passthrough = ({ children }) => React.createElement("div", null, children);
    return { RadialBarChart: passthrough, ResponsiveContainer: passthrough, RadialBar: () => null, PolarAngleAxis: () => null };
  }
  return load.call(this, request, ...args);
};
const resolve = Module._resolveFilename;
Module._resolveFilename = function (request, ...args) {
  return resolve.call(this, request.startsWith("@/") ? path.join(src, request.slice(2)) : request, ...args);
};
for (const extension of [".ts", ".tsx"]) {
  require.extensions[extension] = (module, file) => {
    const code = ts.transpileModule(fs.readFileSync(file, "utf8"), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2021, esModuleInterop: true },
      fileName: file,
    }).outputText;
    module._compile(code, file);
  };
}
const React = require("react");
// Read the current snapshot during server-rendered tests, matching browser hooks.
const useSyncExternalStore = React.useSyncExternalStore;
React.useSyncExternalStore = (subscribe, getSnapshot) => useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
const { renderToStaticMarkup } = require("react-dom/server");
const { useAppStore: store } = require("../src/store/useAppStore.ts");
const { Header } = require("../src/components/dashboard/Header.tsx");
const { CSIGauge } = require("../src/components/dashboard/CSIGauge.tsx");
const { parseCSI } = require("../src/lib/csi.ts");
const { handleRealtimeMessage } = require("../src/hooks/useRealtimeEvents.ts");
const payload = (score, level, seconds = 0) => ({
  overall_score: score, risk_level: level, crowd_score: 100, loitering_score: 100,
  access_score: score, anomaly_score: 100, anomaly_count: 0, active_alerts: 1,
  updated_at: new Date(Date.UTC(2026, 9, 2, 8, 0, seconds)).toISOString(),
});
const render = (component) => renderToStaticMarkup(React.createElement(component));

test("initial dashboard has a loading state without a fake safety score", () => {
  store.setState({ csi: null, csiError: false });
  assert.match(render(Header), /Loading/);
  assert.match(render(CSIGauge), /Loading safety index/);
});

test("badge and gauge consume the same backend score and level", () => {
  store.getState().updateCSI(parseCSI(payload(83, "low_risk")));
  assert.match(render(Header), /83.*LOW RISK/);
  assert.match(render(CSIGauge), />83</);
  assert.match(render(CSIGauge), /Low Risk/);
});

test("realtime update changes both displays including component safety values", () => {
  handleRealtimeMessage({ type: "csi_update", ...payload(65, "moderate", 1) });
  assert.equal(store.getState().csi.overall_score, 65);
  assert.equal(store.getState().csi.access_score, 65);
  assert.match(render(Header), /65.*MODERATE/);
  assert.match(render(CSIGauge), />65</);
  assert.match(render(CSIGauge), /Recent anomalies: 0/);
  assert.equal(store.getState().csi.anomaly_score, 100);
});

test("late polling responses cannot overwrite newer realtime updates", () => {
  store.getState().updateCSI(parseCSI(payload(83, "low_risk")));
  assert.equal(store.getState().csi.overall_score, 65);
});

test("temporary failure keeps the last valid score and identifies it as stale", () => {
  store.getState().setCSIError(true);
  assert.match(render(Header), /65.*stale/);
  assert.match(render(CSIGauge), /showing last valid score/);
});

test("zero is a valid backend score; invalid payloads never become fake scores", () => {
  handleRealtimeMessage({ type: "csi_update", ...payload(0, "critical", 2) });
  assert.equal(store.getState().csi.overall_score, 0);
  assert.throws(() => handleRealtimeMessage({ type:"csi_update", overall:70 }));
  assert.equal(store.getState().csi.overall_score, 0);
});

test("both Leaflet views use the shared campus and preserve camera markers", () => {
  const { CAMPUS_CENTER, CAMPUS_ZOOM, CAMPUS_NAME } = require("../src/lib/campus.ts");
  assert.deepEqual(CAMPUS_CENTER, [17.3545464, 78.5934475]);
  assert.equal(CAMPUS_ZOOM, 18);
  assert.equal(CAMPUS_NAME, "Sreyas Institute of Engineering and Technology");
  for (const file of ["CampusMap.tsx", "CampusMapEnhanced.tsx"]) {
    const source = fs.readFileSync(path.join(src, "components/map", file), "utf8");
    assert.match(source, /center: CAMPUS_CENTER/);
    assert.match(source, /zoom: CAMPUS_ZOOM/);
    assert.match(source, /addCampusMarker\(L, map\)/);
    assert.match(source, /cameraPosition\(cam\)/);
    assert.match(source, /L.marker\(position/);
    assert.doesNotMatch(source, /circleMarker|#2563eb|geolocation/);
    assert.doesNotMatch(source, /fitBounds|setView|flyTo|17\.385/);
  }
});

test("campus building and entrance camera share the exact geographic anchor", () => {
  const { addCampusMarker } = require("../src/lib/campusMarker.ts");
  const { CAMPUS_CENTER, CAMPUS_NAME, cameraPosition } = require("../src/lib/campus.ts");
  let coordinates, options, popup, tooltip;
  const marker = { addTo:()=>marker, bindPopup:value=>{ popup=value; return marker; }, bindTooltip:value=>{ tooltip=value; return marker; } };
  const L = { divIcon:config=>config, marker:(position,config)=>{ coordinates=position; options=config; return marker; } };
  addCampusMarker(L, {});
  const entrance = { id:"entrance", name:"General Entrance", latitude:17.3545464, longitude:78.5934475 };
  assert.deepEqual(coordinates, cameraPosition(entrance));
  assert.equal(coordinates,CAMPUS_CENTER);
  assert.equal(popup,CAMPUS_NAME);
  assert.equal(tooltip,CAMPUS_NAME);
  assert.match(options.icon.html,/data-campus-marker/);
  assert.match(options.icon.html,/#f59e0b/);
  assert.deepEqual(options.icon.iconAnchor,[14,40]);
});

test("missing or invalid camera coordinates are hidden with one warning and never moved to a fallback", () => {
  const { cameraPosition } = require("../src/lib/campus.ts");
  const warn = console.warn;
  const warnings=[];
  console.warn=message=>warnings.push(message);
  try {
    const missing = { id:"missing", name:"Missing", latitude:null, longitude:null };
    assert.equal(cameraPosition(missing),null);
    assert.equal(cameraPosition(missing),null);
    assert.equal(warnings.length,1);
    assert.equal(cameraPosition({id:"invalid", name:"Invalid", latitude:91,longitude:NaN}),null);
    assert.deepEqual(cameraPosition({id:"zero",name:"Zero",latitude:0,longitude:0}),[0,0]);
  } finally { console.warn=warn; }
});

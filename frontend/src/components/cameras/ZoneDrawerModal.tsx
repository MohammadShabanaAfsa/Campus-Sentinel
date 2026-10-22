"use client";
import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import {getAccessToken, SESSION_EXPIRED_EVENT} from "@/lib/session";
import type { CameraItem } from "./CamerasManagementView";

type Point = { x: number; y: number };
type Zone = { id: string; name: string; zone_points: Point[]; alert_level: string; is_active: boolean };
type Line = { points: Point[]; enabled: boolean };
interface Props { camera: CameraItem; onClose: () => void; initialMode?: "zone" | "line"; }
export function ZoneDrawerModal({ camera, onClose, initialMode = "zone" }: Props) {
  const [frameSrc, setFrameSrc] = useState<string | null>(null);
  const [frameSize, setFrameSize] = useState({width:640,height:360});
  const [frameState, setFrameState] = useState<"loading" | "ready" | "unavailable">("loading");
  const [sessionExpired, setSessionExpired] = useState(false);
  const [frameRetry, setFrameRetry] = useState(0);
  const [zones, setZones] = useState<Zone[]>([]);
  const [line, setLine] = useState<Line | null>(null);
  const [mode, setMode] = useState(initialMode);
  const [points, setPoints] = useState<Point[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [name, setName] = useState("Restricted Area");
  const [severity, setSeverity] = useState("high");
  const [enabled, setEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const base = `/api/v1/cameras/${camera.id}`;
  const load = useCallback(async () => {
    const [z, l] = await Promise.all([api.get(`${base}/zones`), api.get(`${base}/counting-line`)]);
    setZones(z.data.map((zone: Zone) => ({ ...zone, zone_points: zone.zone_points.map(p =>
      p.x > 1 || p.y > 1 ? { x: p.x / 640, y: p.y / 360 } : p) })));
    setLine(l.data);
  }, [base]);
  const expire = useCallback(() => {
    setSessionExpired(true); setFrameSrc(null); setFrameState("unavailable");
    setDrawing(false); setPoints([]); setError("Please sign in again");
  }, []);
  const requestError = useCallback((failure: unknown, message: string) => {
    const value = failure as {response?: {status?:number}; message?:string};
    if (value.response?.status === 401 || value.message === "Sign in required" || !getAccessToken()) expire();
    else setError(message);
  }, [expire]);
  useEffect(() => {
    window.addEventListener(SESSION_EXPIRED_EVENT, expire);
    if (!getAccessToken()) expire();
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expire);
  }, [expire]);
  useEffect(() => {
    if (!getAccessToken()) { expire(); return; }
    load().catch(failure => requestError(failure, "Could not load camera geometry."));
  }, [load, expire, requestError]);
  useEffect(() => {
    let active = true;
    setFrameSrc(null); setFrameState("loading"); setDrawing(false); setPoints([]);
    if (!getAccessToken()) { expire(); return; }
    api.get(`/api/v1/streams/${camera.id}/snapshot`).then(res => {
      if (!active) return;
      if (!getAccessToken()) { expire(); return; }
      if (typeof res.data.frame_b64 !== "string" || !res.data.frame_b64.trim()) {
        setFrameState("unavailable"); return;
      }
      setFrameSrc(`data:image/jpeg;base64,${res.data.frame_b64}`);
    }).catch(failure => {
      if (!active) return;
      setFrameState("unavailable");
      const value = failure as {response?: {status?:number}; message?:string};
      if (value.response?.status === 401 || value.message === "Sign in required" || !getAccessToken()) expire();
    });
    return () => { active = false; };
  }, [camera.id, frameRetry, expire]);
  const canDraw = frameState === "ready" && !sessionExpired;
  const start = () => { if (!canDraw) return; setPoints([]); setEditing(null); setEnabled(true); setDrawing(true); setError(""); };
  const save = async () => {
    if (!canDraw || !getAccessToken()) { if (!getAccessToken()) expire(); return; }
    setBusy(true); setError("");
    try {
      if (mode === "line") await api.put(`${base}/counting-line`, { points, enabled });
      else {
        const data = { name, zone_points: points, alert_level: severity, is_active: enabled };
        if (editing) await api.put(`${base}/zones/${editing}`, data);
        else await api.post(`${base}/zones`, data);
      }
      setDrawing(false); setPoints([]); setEditing(null); await load(); setNotice("Saved. Camera analysis updates within five seconds.");
    } catch (failure) { requestError(failure, "Save failed. Use a valid polygon or two distinct line points."); }
    finally { setBusy(false); }
  };
  const clear = async (id?: string) => {
    setBusy(true); setError("");
    try { await api.delete(id ? `${base}/zones/${id}` : `${base}/counting-line`); await load(); setPoints([]); setDrawing(false); }
    catch (failure) { requestError(failure, "Clear failed; the saved geometry is unchanged."); }
    finally { setBusy(false); }
  };
  const button = "rounded bg-slate-700 px-3 py-2 text-xs text-white disabled:opacity-40";
  return <div className="fixed inset-0 z-[1200] flex items-center justify-center bg-black/80 p-4">
    <div className="w-full max-w-4xl max-h-[90vh] overflow-auto rounded-xl bg-slate-900 p-4 text-white">
      <div className="flex justify-between mb-3"><h2>{camera.name} - Camera geometry</h2><button onClick={onClose} aria-label="Close geometry editor">Close</button></div>
      <div className="flex gap-2 mb-3">
        <button className={button} onClick={() => { setMode("zone"); setDrawing(canDraw); setPoints([]); setEditing(null); }}>Restricted Zone</button>
        <button className={button} onClick={() => { setMode("line"); setDrawing(canDraw); setPoints([]); setEditing(null); }}>Vehicle Count</button>
      </div>
      {sessionExpired ? <div role="alert" className="rounded border border-amber-500 p-6 text-center">
        <p>Please sign in again</p><a href="/login" className="text-blue-300 underline">Sign in</a>
      </div> : <>
        {frameState === "unavailable" && <div role="alert" className="rounded border border-red-500 p-6 text-center">
          <p>Camera frame unavailable</p><button className={button} onClick={() => setFrameRetry(v => v + 1)}>Retry Frame</button>
        </div>}
        {frameState === "loading" && <p role="status">Loading camera frame...</p>}
        {frameSrc && frameState !== "unavailable" && <div className="relative w-full overflow-hidden" style={{aspectRatio:`${frameSize.width} / ${frameSize.height}`}}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={frameSrc} alt={`Geometry frame: ${camera.name}`} className="block w-full h-full" onLoad={e => {
            const img=e.currentTarget;
            if (!img.naturalWidth || !img.naturalHeight) { setFrameState("unavailable"); return; }
            if (!getAccessToken()) { expire(); return; }
            setFrameSize({width:img.naturalWidth,height:img.naturalHeight}); setFrameState("ready"); setDrawing(true);
          }} onError={() => { setFrameSrc(null); setFrameState("unavailable"); setDrawing(false); }} />
          {canDraw && <svg aria-label="Camera geometry drawing layer" viewBox={`0 0 ${frameSize.width} ${frameSize.height}`}
            preserveAspectRatio="none" className={`absolute inset-0 z-10 w-full h-full ${drawing ? "cursor-crosshair pointer-events-auto" : "pointer-events-none"}`}
            onClick={e => {
              if (!canDraw || !drawing || (mode === "line" && points.length >= 2)) return;
              if (!getAccessToken()) { expire(); return; }
              const rect=e.currentTarget.getBoundingClientRect();
              if (rect.width <= 0 || rect.height <= 0) return;
              setPoints(prev => [...prev, {x:Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width)),
                                          y:Math.max(0,Math.min(1,(e.clientY-rect.top)/rect.height))}]);
            }}>
            {zones.filter(z => z.is_active && z.id !== editing).map(z => <polygon key={z.id}
              points={z.zone_points.map(p => `${p.x*frameSize.width},${p.y*frameSize.height}`).join(" ")}
              fill="rgba(239,68,68,0.12)" stroke="#ef4444" strokeWidth={2} vectorEffect="non-scaling-stroke" />)}
            {line?.enabled && !(mode === "line" && drawing) && <polyline data-testid="saved-counting-line"
              points={line.points.map(p => `${p.x*frameSize.width},${p.y*frameSize.height}`).join(" ")}
              fill="none" stroke="#22c55e" strokeWidth={3} vectorEffect="non-scaling-stroke" />}
            {mode === "zone" && points.length >= 3 ? <polygon data-testid="draft-polygon"
              points={points.map(p => `${p.x*frameSize.width},${p.y*frameSize.height}`).join(" ")}
              fill="rgba(56,189,248,0.2)" stroke="#38bdf8" strokeWidth={2} vectorEffect="non-scaling-stroke" />
              : <polyline data-testid="draft-line" points={points.map(p => `${p.x*frameSize.width},${p.y*frameSize.height}`).join(" ")}
                  fill="none" stroke="#38bdf8" strokeWidth={3} vectorEffect="non-scaling-stroke" />}
            {points.map((p,i) => <circle key={i} data-testid="draft-point" cx={p.x*frameSize.width} cy={p.y*frameSize.height}
              r={Math.max(4,frameSize.width*.008)} fill="#38bdf8" stroke="white" strokeWidth={2} vectorEffect="non-scaling-stroke" />)}
          </svg>}
        </div>}
      </>}
      <p className="text-xs text-slate-400 my-2">{mode === "zone" ? "Click at least three points around the restricted area." : "Click start and end. IN crosses to the right-hand side of the directed start to end line. Counts reset on line change or camera restart."}</p>
      {mode === "zone" && <div className="flex gap-2 mb-2"><input aria-label="Zone name" value={name} onChange={e => setName(e.target.value)} className="bg-slate-800 p-2" /><select aria-label="Zone severity" value={severity} onChange={e => setSeverity(e.target.value)} className="bg-slate-800 p-2">{["low", "medium", "high", "critical"].map(s => <option key={s}>{s}</option>)}</select></div>}
      <label className="text-xs mr-3"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /> Enabled</label>
      <div className="flex gap-2 my-2">
        <button className={button} disabled={!canDraw || busy} onClick={start}>{mode === "zone" ? "Draw Restricted Zone" : "Draw Counting Line"}</button>
        {drawing && <><button className={button} onClick={() => setPoints([])}>Redraw</button><button className={button} disabled={!canDraw || busy || (mode === "zone" ? points.length < 3 : points.length !== 2)} onClick={save}>Save</button><button className={button} onClick={() => { setDrawing(false); setPoints([]); }}>Cancel</button></>}
        {mode === "line" && line && <><button className={button} disabled={!canDraw || busy} onClick={() => { if (!canDraw) return; setPoints(line.points); setEnabled(line.enabled); setDrawing(true); }}>Edit</button><button className={button} disabled={sessionExpired || busy} onClick={() => clear()}>Clear</button></>}
      </div>
      {mode === "zone" && zones.map(z => <div key={z.id} className="flex items-center gap-3 my-2 text-sm"><span>{z.name} ({z.alert_level}, {z.is_active ? "enabled" : "disabled"})</span><button className={button} disabled={!canDraw || busy} onClick={() => { if (!canDraw) return; setEditing(z.id); setPoints(z.zone_points); setName(z.name); setSeverity(z.alert_level); setEnabled(z.is_active); setDrawing(true); }}>Edit</button><button className={button} disabled={sessionExpired || busy} onClick={() => clear(z.id)}>Clear</button></div>)}
      {notice && <p className="text-xs text-slate-400">{notice}</p>}{error && !sessionExpired && <p role="alert" className="text-sm text-red-400">{error}</p>}
    </div>
  </div>;
}

"use client";
import {useEffect,useRef,useState} from "react";
import api from "@/lib/api";
import type {CameraItem} from "./CamerasManagementView";
type Point={x:number;y:number};
type Exit={id:string;name:string;points:Point[];enabled:boolean};
type HoursZone=Exit & {start:string;end:string};
type Configuration={schedule:{enabled:boolean;start:string;end:string;timezone:string;zones:HoursZone[]};exit_zones:Exit[]};
const defaults:Configuration={schedule:{enabled:false,start:"06:00",end:"21:00",timezone:"Asia/Kolkata",zones:[]},exit_zones:[]};
export function CampusRulesModal({camera,onClose}:{camera:CameraItem;onClose:()=>void}) {
 const [config,setConfig]=useState<Configuration>(defaults);
 const [loaded,setLoaded]=useState(false);const [error,setError]=useState("");const [busy,setBusy]=useState(false);
 const [draft,setDraft]=useState<Point[]>([]);const [mode,setMode]=useState<"exit"|"hours"|null>(null);
 const [editing,setEditing]=useState<string|null>(null);const [name,setName]=useState("Emergency Exit");
 const [enabled,setEnabled]=useState(true);const [start,setStart]=useState("06:00");const [end,setEnd]=useState("21:00");
 const canvas=useRef<HTMLCanvasElement>(null);const image=useRef<HTMLImageElement|null>(null);
 const [size,setSize]=useState({width:640,height:360});const url=`/api/v1/cameras/${camera.id}/campus-events`;
 useEffect(()=>{let active=true;api.get(url).then(r=>{if(active){setConfig(r.data);setLoaded(true);}}).catch(()=>setError("Unable to load camera rules."));
  api.get(`/api/v1/streams/${camera.id}/snapshot`).then(r=>{const img=new Image();img.onload=()=>{if(active){image.current=img;setSize({width:640,height:Math.round(640*img.naturalHeight/img.naturalWidth)});}};img.src=`data:image/jpeg;base64,${r.data.frame_b64}`;}).catch(()=>{});
  return()=>{active=false;};},[url,camera.id]);
 useEffect(()=>{const node=canvas.current;const ctx=node?.getContext("2d");if(!node||!ctx)return;
  ctx.clearRect(0,0,node.width,node.height);if(image.current)ctx.drawImage(image.current,0,0,node.width,node.height);
  const draw=(points:Point[],color:string)=>{if(!points.length)return;ctx.beginPath();ctx.moveTo(points[0].x*node.width,points[0].y*node.height);points.slice(1).forEach(p=>ctx.lineTo(p.x*node.width,p.y*node.height));if(points.length>=3)ctx.closePath();ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke();points.forEach(p=>{ctx.beginPath();ctx.arc(p.x*node.width,p.y*node.height,4,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();});};
  config.exit_zones.filter(z=>z.enabled&&z.id!==editing).forEach(z=>draw(z.points,"#f97316"));config.schedule.zones.filter(z=>z.enabled&&z.id!==editing).forEach(z=>draw(z.points,"#a78bfa"));draw(draft,"#38bdf8");
 },[config,draft,size,editing]);
 const save=async(next:Configuration)=>{setBusy(true);setError("");try{const r=await api.put(url,next);setConfig(r.data);setDraft([]);setMode(null);setEditing(null);}catch{setError("Save failed. Check polygon, hours and IANA timezone.");}finally{setBusy(false);}};
 const begin=(kind:"exit"|"hours")=>{setMode(kind);setDraft([]);setEditing(null);setName(kind==="exit"?"Emergency Exit":"Scheduled Area");setEnabled(true);};
 const savePolygon=()=>{const zone={id:editing||crypto.randomUUID(),name,points:draft,enabled};
  if(mode==="exit")return save({...config,exit_zones:[...config.exit_zones.filter(z=>z.id!==editing),zone]});
  return save({...config,schedule:{...config.schedule,zones:[...config.schedule.zones.filter(z=>z.id!==editing),{...zone,start,end}]}});};
 const button="rounded bg-slate-700 px-3 py-2 text-xs disabled:opacity-40";
 return <div className="fixed inset-0 z-[1300] flex items-center justify-center bg-black/80 p-4"><div className="max-h-[90vh] overflow-auto w-full max-w-4xl rounded-xl bg-slate-900 p-4 text-white">
  <div className="flex justify-between"><h2>{camera.name} ? Campus rules</h2><button onClick={onClose}>Close</button></div>
  <div className="flex flex-wrap gap-3 my-3 items-center">
   <label><input type="checkbox" checked={config.schedule.enabled} onChange={e=>setConfig({...config,schedule:{...config.schedule,enabled:e.target.checked}})}/> After-hours monitoring</label>
   <label>Permitted from <input aria-label="Permitted start" type="time" value={config.schedule.start} onChange={e=>setConfig({...config,schedule:{...config.schedule,start:e.target.value}})} className="bg-slate-800"/></label>
   <label>to <input aria-label="Permitted end" type="time" value={config.schedule.end} onChange={e=>setConfig({...config,schedule:{...config.schedule,end:e.target.value}})} className="bg-slate-800"/></label>
   <input aria-label="Timezone" value={config.schedule.timezone} onChange={e=>setConfig({...config,schedule:{...config.schedule,timezone:e.target.value}})} className="bg-slate-800 p-1"/>
   <button className={button} disabled={!loaded||busy} onClick={()=>save(config)}>Save Hours</button>
  </div>
  <canvas ref={canvas} width={size.width} height={size.height} className="w-full bg-slate-950 cursor-crosshair" onClick={e=>{if(!mode)return;const r=e.currentTarget.getBoundingClientRect();setDraft(p=>[...p,{x:Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))}]);}}/>
  <div className="flex gap-2 my-3"><button className={button} disabled={!loaded||busy} onClick={()=>begin("exit")}>Draw Exit Zone</button><button className={button} disabled={!loaded||busy} onClick={()=>begin("hours")}>Draw Schedule Zone</button></div>
  {mode&&<div className="flex flex-wrap gap-2 items-center"><input aria-label="Area name" value={name} onChange={e=>setName(e.target.value)} className="bg-slate-800 p-2"/><label><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/> Enabled</label>
   {mode==="hours"&&<><input aria-label="Zone start" type="time" value={start} onChange={e=>setStart(e.target.value)} className="bg-slate-800"/><input aria-label="Zone end" type="time" value={end} onChange={e=>setEnd(e.target.value)} className="bg-slate-800"/></>}
   <button className={button} disabled={busy||draft.length<3} onClick={savePolygon}>Save</button><button className={button} onClick={()=>setDraft([])}>Redraw</button><button className={button} onClick={()=>{setMode(null);setDraft([]);setEditing(null);}}>Cancel</button></div>}
  <p className="text-xs text-slate-400 my-3">Polygons use normalized coordinates. Zone hours override camera hours inside that zone. Overnight windows are supported. Updates apply within five seconds.</p>
  {[...config.exit_zones.map(z=>({...z,kind:"exit" as const})),...config.schedule.zones.map(z=>({...z,kind:"hours" as const}))].map(z=><div key={z.id} className="flex gap-3 items-center my-2"><span>{z.name} ({z.kind})</span><button className={button} disabled={busy} onClick={()=>{setMode(z.kind);setEditing(z.id);setName(z.name);setEnabled(z.enabled);setDraft(z.points);if("start" in z){setStart(z.start);setEnd(z.end);}}}>Edit</button><button className={button} disabled={busy} onClick={()=>save(z.kind==="exit"?{...config,exit_zones:config.exit_zones.filter(v=>v.id!==z.id)}:{...config,schedule:{...config.schedule,zones:config.schedule.zones.filter(v=>v.id!==z.id)}})}>Clear</button></div>)}
  {error&&<p role="alert" className="text-red-400">{error}</p>}
 </div></div>;
}

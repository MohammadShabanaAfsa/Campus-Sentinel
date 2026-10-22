"use client";

import { useState } from "react";
import api, { camerasApi } from "@/lib/api";
import type { CameraItem } from "./CamerasManagementView";

function message(error: any): string {
  const detail = error?.response?.data?.detail;
  return typeof detail === "string" ? detail : "Camera request failed. Check the source and try again.";
}

export function EditCameraModal({ camera, onClose, onSaved }: {
  camera: CameraItem; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState({ name: camera.name, rtsp_url: camera.rtsp_url,
    location_name: camera.location_name, zone_type: camera.zone_type,
    latitude: camera.latitude == null ? "" : String(camera.latitude),
    longitude: camera.longitude == null ? "" : String(camera.longitude) });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(camera.last_error || "");
  const act = async (action: "save" | "test" | "restart") => {
    setBusy(true); setNotice("");
    try {
      if (action === "test") {
        const { data } = await api.post("/api/v1/cameras/test-source", { rtsp_url: form.rtsp_url.trim() });
        setNotice(data.message);
      } else if (action === "restart") {
        if (form.rtsp_url.trim() !== camera.rtsp_url) {
          setNotice("Save the source change before restarting."); return;
        }
        await api.post(`/api/v1/streams/${camera.id}/restart`);
        setNotice("Camera restart requested.");
      } else {
        const payload: Record<string, unknown> = {};
        for (const key of ["name", "rtsp_url", "location_name", "zone_type"] as const) {
          if (form[key].trim() !== camera[key]) payload[key] = form[key].trim();
        }
        for (const key of ["latitude", "longitude"] as const) {
          const value = form[key].trim() === "" ? null : Number(form[key]);
          const limit = key === "latitude" ? 90 : 180;
          if (value !== null && (!Number.isFinite(value) || Math.abs(value) > limit)) {
            setNotice(`Invalid ${key}.`); return;
          }
          if (value !== (camera[key] ?? null)) payload[key] = value;
        }
        await camerasApi.update(camera.id, payload);
        onSaved();
      }
    } catch (error) { setNotice(message(error)); }
    finally { setBusy(false); }
  };
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
    <div role="dialog" aria-modal="true" aria-label="Camera settings" className="w-full max-w-lg rounded-xl border border-gray-700 bg-[#1a1f2e] p-5 text-white">
      <h2 className="text-lg font-semibold mb-4">Camera settings: {camera.name}</h2>
      <form onSubmit={(event) => { event.preventDefault(); void act("save"); }}>
        {(["name", "rtsp_url", "location_name", "latitude", "longitude", "zone_type"] as const).map((key) =>
          <label key={key} className="block mb-3 text-sm">
            {{ name: "Name", rtsp_url: "Video source", location_name: "Location", latitude: "Latitude", longitude: "Longitude", zone_type: "Zone type" }[key]}
            <input disabled={busy} required={["name", "rtsp_url", "location_name", "zone_type"].includes(key)} value={form[key]}
              onChange={(event) => { setForm({ ...form, [key]: event.target.value }); setNotice(""); }}
              className="mt-1 block w-full rounded border border-gray-600 bg-[#0d1117] p-2" />
          </label>)}
        <p className="text-xs text-gray-400 mb-3">Android IP Webcam: http://&lt;PHONE_IP&gt;:8080/video. Use the address shown by the phone on the same network.</p>
        {notice && <p role="status" className="text-sm text-amber-300 mb-3">{notice}</p>}
        <div className="flex flex-wrap gap-2">
          <button disabled={busy} className="rounded bg-blue-600 px-3 py-2">Save</button>
          <button disabled={busy} type="button" onClick={() => void act("test")} className="rounded bg-gray-700 px-3 py-2">Test Connection</button>
          <button disabled={busy} type="button" onClick={() => void act("restart")} className="rounded bg-gray-700 px-3 py-2">Restart Camera</button>
          <button disabled={busy} type="button" onClick={onClose} className="rounded px-3 py-2">Close</button>
        </div>
      </form>
    </div>
  </div>;
}

"use client";

import { useState } from "react";
import { X, Camera, Loader2 } from "lucide-react";
import { camerasApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CAMPUS_CENTER } from "@/lib/campus";

const ZONE_TYPES = ["entrance", "corridor", "lab", "parking", "cafeteria", "library", "admin", "restricted", "general"];

interface Props {
  onClose: () => void;
  onAdded: () => void;
}

export function AddCameraModal({ onClose, onAdded }: Props) {
  const [form, setForm] = useState({
    name: "",
    location_name: "",
    rtsp_url: "",
    zone_type: "general",
    latitude: "",
    longitude: "",
    resolution: "1920x1080",
    fps: "25",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await camerasApi.create({
        ...form,
        latitude: form.latitude ? parseFloat(form.latitude) : undefined,
        longitude: form.longitude ? parseFloat(form.longitude) : undefined,
        fps: parseInt(form.fps),
      });
      onAdded();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || "Failed to add camera");
    } finally {
      setLoading(false);
    }
  };

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-[#1a1f2e] border border-[#2a3042] rounded-xl w-full max-w-lg mx-4 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#2a3042]">
          <div className="flex items-center gap-2">
            <Camera className="w-4 h-4 text-blue-400" />
            <h3 className="text-sm font-semibold text-white">Add Camera</h3>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Camera Name *" value={form.name} onChange={set("name")} placeholder="Main Entrance" required />
            <Field label="Location *" value={form.location_name} onChange={set("location_name")} placeholder="Building A" required />
          </div>

          <Field
            label="RTSP URL *"
            value={form.rtsp_url}
            onChange={set("rtsp_url")}
            placeholder="rtsp://admin:pass@192.168.1.100:554/stream1"
            required
            mono
          />

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Zone Type</label>
              <select
                value={form.zone_type}
                onChange={set("zone_type")}
                className="w-full bg-[#0d1117] border border-[#2a3042] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              >
                {ZONE_TYPES.map((z) => (
                  <option key={z} value={z}>{z.charAt(0).toUpperCase() + z.slice(1)}</option>
                ))}
              </select>
            </div>
            <Field label="Latitude" value={form.latitude} onChange={set("latitude")} placeholder={String(CAMPUS_CENTER[0])} />
            <Field label="Longitude" value={form.longitude} onChange={set("longitude")} placeholder={String(CAMPUS_CENTER[1])} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Resolution</label>
              <select
                value={form.resolution}
                onChange={set("resolution")}
                className="w-full bg-[#0d1117] border border-[#2a3042] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              >
                {["640x480", "1280x720", "1920x1080", "2560x1440", "3840x2160"].map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
            <Field label="FPS" value={form.fps} onChange={set("fps")} placeholder="25" type="number" />
          </div>

          {/* RTSP hint */}
          <div className="text-xs text-gray-500 bg-[#0d1117] rounded-lg p-2.5 border border-[#2a3042]">
            <p className="font-medium text-gray-400 mb-1">Supported stream sources:</p>
            <p>Hikvision: <span className="text-blue-400">rtsp://user:pass@IP:554/Streaming/Channels/101</span></p>
            <p>Generic RTSP: <span className="text-blue-400">rtsp://user:pass@IP:554/stream</span></p>
            <p>Video file: <span className="text-blue-400">file:///path/to/video.mp4</span> (loops automatically)</p>
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-900/20 border border-red-700 rounded px-3 py-2">{error}</p>
          )}

          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className="flex-1 px-4 py-2 bg-[#0d1117] border border-[#2a3042] rounded-lg text-sm text-gray-400 hover:text-white">
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg text-sm text-white flex items-center justify-center gap-2"
            >
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Add Camera
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({
  label, value, onChange, placeholder, required, mono, type = "text",
}: {
  label: string; value: string; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string; required?: boolean; mono?: boolean; type?: string;
}) {
  return (
    <div>
      <label className="block text-xs text-gray-400 mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        className={cn(
          "w-full bg-[#0d1117] border border-[#2a3042] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500",
          mono && "font-mono text-xs"
        )}
      />
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { Header } from "@/components/dashboard/Header";
import { Settings, Save, RotateCcw, Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface SystemSettings {
  loitering_threshold_secs: number;
  crowd_density_threshold: number;
  running_speed_threshold: number;
  alert_cooldown_secs: number;
  yolo_confidence_threshold: number;
  frame_skip: number;
  max_cameras: number;
  csi_update_interval_secs: number;
  abd_contamination_rate: number;
}

type SaveState = "idle" | "saving" | "saved" | "error";

const FIELD_META: Record<keyof SystemSettings, { label: string; unit: string; min: number; max: number; step: number; hint: string }> = {
  loitering_threshold_secs:  { label: "Loitering Threshold",      unit: "sec",  min: 30,   max: 3600, step: 30,   hint: "How long a person must stay before triggering a loitering alert" },
  crowd_density_threshold:   { label: "Crowd Density Threshold",  unit: "ppl",  min: 1,    max: 200,  step: 1,    hint: "Person count above which a crowd density alert is triggered" },
  running_speed_threshold:   { label: "Running Speed Threshold",  unit: "m/s",  min: 0.5,  max: 20,   step: 0.1,  hint: "Movement speed above which 'running' is detected" },
  alert_cooldown_secs:       { label: "Alert Cooldown",           unit: "sec",  min: 10,   max: 600,  step: 10,   hint: "Minimum seconds between the same alert type per camera" },
  yolo_confidence_threshold: { label: "YOLO Confidence",          unit: "",     min: 0.1,  max: 0.99, step: 0.05, hint: "Detection confidence threshold (lower = more detections, more noise)" },
  frame_skip:                { label: "Frame Skip",               unit: "frames", min: 1,  max: 10,   step: 1,    hint: "Process 1 frame per N (higher = lower CPU, lower accuracy)" },
  max_cameras:               { label: "Max Cameras",              unit: "",     min: 1,    max: 64,   step: 1,    hint: "Maximum concurrent camera streams" },
  csi_update_interval_secs:  { label: "CSI Update Interval",      unit: "sec",  min: 10,   max: 600,  step: 10,   hint: "How often Campus Safety Index is recalculated" },
  abd_contamination_rate:    { label: "ABD Contamination Rate",   unit: "",     min: 0.01, max: 0.2,  step: 0.01, hint: "IsolationForest contamination parameter (expected anomaly fraction)" },
};

const SECTIONS = {
  "Detection": ["yolo_confidence_threshold", "frame_skip", "max_cameras"],
  "Behavioral Analytics": ["loitering_threshold_secs", "crowd_density_threshold", "running_speed_threshold", "abd_contamination_rate"],
  "Alerts & Safety": ["alert_cooldown_secs", "csi_update_interval_secs"],
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [original, setOriginal] = useState<SystemSettings | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/settings/", {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
      });
      const data = await res.json();
      setSettings(data);
      setOriginal(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!settings) return;
    setSaveState("saving");
    try {
      const res = await fetch("/api/v1/settings/", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify(settings),
      });
      if (res.ok) {
        setOriginal(settings);
        setSaveState("saved");
        setTimeout(() => setSaveState("idle"), 3000);
      } else {
        setSaveState("error");
      }
    } catch {
      setSaveState("error");
    }
  };

  const reset = async () => {
    const res = await fetch("/api/v1/settings/reset", {
      method: "POST",
      headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
    });
    if (res.ok) { await load(); }
  };

  const hasChanges = JSON.stringify(settings) !== JSON.stringify(original);

  const updateField = (key: keyof SystemSettings, value: number) => {
    setSettings(prev => prev ? { ...prev, [key]: value } : null);
  };

  return (
    <div className="flex h-screen bg-[#0a0e1a] text-white overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-4 space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Settings className="w-5 h-5 text-blue-400" />
              <h2 className="text-lg font-semibold">System Settings</h2>
            </div>
            <div className="flex gap-2">
              <button onClick={reset}
                className="flex items-center gap-2 px-3 py-1.5 border border-[#2a3042] text-gray-400 hover:text-white text-xs rounded-lg transition-colors">
                <RotateCcw className="w-3 h-3" /> Reset Defaults
              </button>
              <button onClick={save} disabled={!hasChanges || saveState === "saving"}
                className={cn(
                  "flex items-center gap-2 px-4 py-1.5 text-xs rounded-lg font-medium transition-colors",
                  saveState === "saved" ? "bg-green-600 text-white" :
                  saveState === "error" ? "bg-red-600 text-white" :
                  hasChanges ? "bg-blue-600 hover:bg-blue-700 text-white" :
                  "bg-[#1a1f2e] border border-[#2a3042] text-gray-500 cursor-default"
                )}>
                {saveState === "saved" ? <Check className="w-3 h-3" /> : <Save className="w-3 h-3" />}
                {saveState === "saving" ? "Saving..." : saveState === "saved" ? "Saved!" : saveState === "error" ? "Error" : "Save Changes"}
              </button>
            </div>
          </div>

          {loading || !settings ? (
            <div className="flex items-center justify-center h-40">
              <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="space-y-4">
              {Object.entries(SECTIONS).map(([section, fields]) => (
                <div key={section} className="bg-[#1a1f2e] border border-[#2a3042] rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-white mb-4">{section}</h3>
                  <div className="space-y-5">
                    {fields.map(fieldKey => {
                      const key = fieldKey as keyof SystemSettings;
                      const meta = FIELD_META[key];
                      const value = settings[key];
                      const isChanged = original && original[key] !== value;

                      return (
                        <div key={key}>
                          <div className="flex items-center justify-between mb-1.5">
                            <div className="flex items-center gap-2">
                              <span className="text-sm text-white">{meta.label}</span>
                              {isChanged && <span className="text-xs text-blue-400 bg-blue-900/20 px-1.5 rounded">changed</span>}
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-mono text-blue-400 w-16 text-right">{value}{meta.unit}</span>
                            </div>
                          </div>
                          <input
                            type="range"
                            min={meta.min}
                            max={meta.max}
                            step={meta.step}
                            value={value}
                            onChange={e => updateField(key, Number(e.target.value))}
                            className="w-full h-1.5 bg-[#2a3042] rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-blue-500"
                          />
                          <div className="flex justify-between mt-0.5">
                            <span className="text-xs text-gray-600">{meta.min}{meta.unit}</span>
                            <span className="text-xs text-gray-500 text-center max-w-xs">{meta.hint}</span>
                            <span className="text-xs text-gray-600">{meta.max}{meta.unit}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}

              {/* System info */}
              <div className="bg-[#1a1f2e] border border-[#2a3042] rounded-xl p-5">
                <h3 className="text-sm font-semibold text-white mb-3">System Information</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[
                    { label: "Version", value: "1.0.0" },
                    { label: "Environment", value: process.env.NODE_ENV ?? "production" },
                    { label: "AI Engine", value: "YOLOv8n" },
                    { label: "Tracking", value: "ByteTrack" },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-[#0d1117] rounded-lg p-3">
                      <p className="text-xs text-gray-500">{label}</p>
                      <p className="text-sm text-white mt-1 font-mono">{value}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

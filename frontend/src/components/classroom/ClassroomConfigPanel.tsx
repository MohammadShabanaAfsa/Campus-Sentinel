"use client";

import { useEffect, useState } from "react";
import { Settings, Save, Check } from "lucide-react";
import { classroomApi } from "@/lib/api";

interface Config {
  expected_students: number;
  sleeping_secs_threshold: number;
  talking_secs_threshold: number;
}

export function ClassroomConfigPanel({ cameraId }: { cameraId: string }) {
  const [config, setConfig] = useState<Config | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    classroomApi.getConfig(cameraId).then((res) => {
      if (!cancelled) setConfig(res.data);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [cameraId]);

  if (!config) {
    return (
      <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] p-4 text-xs text-gray-500">
        Loading configuration...
      </div>
    );
  }

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await classroomApi.updateConfig(cameraId, config);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] p-4">
      <div className="flex items-center gap-2 mb-3">
        <Settings className="w-4 h-4 text-blue-400" />
        <h3 className="text-sm font-medium text-white">Classroom Settings</h3>
      </div>

      <div className="space-y-3">
        <label className="block">
          <span className="text-xs text-gray-400">Expected Students</span>
          <input
            type="number"
            min={1}
            value={config.expected_students}
            onChange={(e) => setConfig({ ...config, expected_students: Number(e.target.value) })}
            className="w-full mt-1 bg-[#0d1117] border border-[#2a3042] rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
          />
        </label>

        <label className="block">
          <span className="text-xs text-gray-400">Sleeping Threshold (seconds)</span>
          <input
            type="number"
            min={1}
            value={config.sleeping_secs_threshold}
            onChange={(e) => setConfig({ ...config, sleeping_secs_threshold: Number(e.target.value) })}
            className="w-full mt-1 bg-[#0d1117] border border-[#2a3042] rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
          />
        </label>

        <label className="block">
          <span className="text-xs text-gray-400">Talking Threshold (seconds)</span>
          <input
            type="number"
            min={1}
            value={config.talking_secs_threshold}
            onChange={(e) => setConfig({ ...config, talking_secs_threshold: Number(e.target.value) })}
            className="w-full mt-1 bg-[#0d1117] border border-[#2a3042] rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
          />
        </label>

        <button
          onClick={handleSave}
          disabled={saving}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm py-1.5 rounded-lg transition-colors"
        >
          {saved ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
          {saved ? "Saved" : saving ? "Saving..." : "Save"}
        </button>
      </div>
    </div>
  );
}

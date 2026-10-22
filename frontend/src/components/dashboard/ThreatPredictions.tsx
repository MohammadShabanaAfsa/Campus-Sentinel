"use client";

import { useEffect } from "react";
import { Brain, AlertTriangle } from "lucide-react";
import { useAppStore } from "@/store/useAppStore";
import { predictionsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const LEVEL_STYLES: Record<string, string> = {
  critical: "text-purple-400 bg-purple-900/20 border-purple-700",
  high:     "text-red-400 bg-red-900/20 border-red-700",
  medium:   "text-amber-400 bg-amber-900/20 border-amber-700",
  low:      "text-green-400 bg-green-900/20 border-green-700",
};

const THREAT_ICONS: Record<string, string> = {
  potential_fight:     "⚔️",
  crowd_surge:         "👥",
  security_breach:     "🔓",
  restricted_access:   "🚫",
};

export function ThreatPredictions() {
  const predictions = useAppStore((s) => s.predictions);
  const setPredictions = useAppStore((s) => s.setPredictions);

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await predictionsApi.list({ hours: 1 });
        setPredictions(res.data.slice(0, 8));
      } catch (_) {}
    };
    fetch();
    const t = setInterval(fetch, 30000);
    return () => clearInterval(t);
  }, [setPredictions]);

  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] flex flex-col">
      <div className="flex items-center gap-2 p-4 border-b border-[#2a3042]">
        <Brain className="w-4 h-4 text-blue-400" />
        <h3 className="text-sm font-medium text-white">AI Threat Predictions</h3>
      </div>

      <div className="flex-1 p-3 space-y-2 overflow-y-auto">
        {predictions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-24 text-gray-500">
            <Brain className="w-8 h-8 mb-2" />
            <p className="text-xs">No active threat predictions</p>
          </div>
        ) : (
          predictions.map((pred, i) => (
            <div
              key={i}
              className={cn("rounded-lg border p-3", LEVEL_STYLES[pred.threat_level])}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-base">{THREAT_ICONS[pred.threat_type] || "⚠️"}</span>
                  <span className="text-xs font-medium capitalize">
                    {pred.threat_type.replace(/_/g, " ")}
                  </span>
                </div>
                <span className="text-xs font-bold">{Math.round(pred.probability * 100)}%</span>
              </div>

              <div className="w-full bg-[#0d1117] rounded-full h-1.5 mb-2">
                <div
                  className="h-1.5 rounded-full"
                  style={{
                    width: `${pred.probability * 100}%`,
                    backgroundColor: pred.threat_level === "critical" ? "#7c3aed"
                      : pred.threat_level === "high" ? "#ef4444"
                      : pred.threat_level === "medium" ? "#f59e0b" : "#22c55e",
                  }}
                />
              </div>

              {pred.recommended_action && (
                <p className="text-xs opacity-75 leading-snug">{pred.recommended_action}</p>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

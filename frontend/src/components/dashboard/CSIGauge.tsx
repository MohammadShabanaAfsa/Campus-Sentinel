"use client";

import { RadialBarChart, RadialBar, ResponsiveContainer, PolarAngleAxis } from "recharts";
import { useAppStore } from "@/store/useAppStore";
import { cn } from "@/lib/utils";

const RISK_CONFIG = {
  safe:      { color: "#22c55e", label: "Safe",      bg: "bg-green-900/20 border-green-700" },
  low_risk: { color: "#84cc16", label: "Low Risk", bg: "bg-lime-900/20 border-lime-700" },
  moderate:  { color: "#f59e0b", label: "Moderate",  bg: "bg-amber-900/20 border-amber-700" },
  high_risk: { color: "#ef4444", label: "High Risk", bg: "bg-red-900/20 border-red-700" },
  critical:  { color: "#7c3aed", label: "Critical",  bg: "bg-purple-900/20 border-purple-700" },
};

export function CSIGauge() {
  // Atomic selectors: this component only re-renders when `csi` itself
  // changes, not on every unrelated alert/classroom/prediction update
  // elsewhere in the store (bare useAppStore() subscribes to the whole
  // state and re-renders on every single mutation anywhere).
  const csi = useAppStore((s) => s.csi);
  const csiError = useAppStore((s) => s.csiError);
  if (!csi) {
    return <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] p-4 h-full">
      <h3 className="text-sm font-medium text-gray-400">Campus Safety Index</h3>
      <p role="status" className="text-sm text-gray-500 mt-4">{csiError ? "Safety index unavailable" : "Loading safety index\u2026"}</p>
    </div>;
  }
  const config = RISK_CONFIG[csi.risk_level];

  const chartData = [{ value: csi.overall_score, fill: config.color }];

  return (
    <div className={cn("bg-[#1a1f2e] rounded-xl border p-4 h-full", config.bg)}>
      <h3 className="text-sm font-medium text-gray-400 mb-2">Campus Safety Index</h3>

      <div className="relative h-36">
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart
            cx="50%" cy="70%"
            innerRadius="60%" outerRadius="90%"
            startAngle={180} endAngle={0}
            data={chartData}
          >
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
          <RadialBar background={{ fill: "#2a3042" }} dataKey="value" cornerRadius={4} />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center mt-8">
          <span className="text-3xl font-bold" style={{ color: config.color }}>
            {Math.round(csi.overall_score)}
          </span>
          <span className="text-xs text-gray-400">/ 100</span>
        </div>
      </div>

      <div className="text-center mb-3">
        <span className="text-sm font-semibold" style={{ color: config.color }}>
          {config.label}
        </span>
      </div>

      {csiError && <p role="status" className="text-xs text-amber-400 mb-2">Updates unavailable; showing last valid score</p>}
      <p className="text-xs text-gray-500 mb-2">Recent anomalies: {csi.anomaly_count} / Active events: {csi.active_alerts}</p>
      <div className="space-y-1.5" title="Category safety scores: 100 means no matching recent events. Overall CSI includes all event types.">
        {[
          { label: "Crowd", value: csi.crowd_score },
          { label: "Loitering", value: csi.loitering_score },
          { label: "Access", value: csi.access_score },
          { label: "Anomaly", value: csi.anomaly_score },
        ].map(({ label, value }) => (
          <div key={label} className="flex items-center gap-2">
            <span className="text-xs text-gray-500 w-16">{label}</span>
            <div className="flex-1 bg-[#2a3042] rounded-full h-1.5">
              <div
                className="h-1.5 rounded-full transition-all duration-500"
                style={{ width: `${value}%`, backgroundColor: config.color }}
              />
            </div>
            <span className="text-xs text-gray-400 w-8 text-right">{Math.round(value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

"use client";

import { RadialBarChart, RadialBar, ResponsiveContainer } from "recharts";
import { cn } from "@/lib/utils";
import type { ClassroomMetric } from "@/store/useAppStore";

const LEVEL_CONFIG: Record<string, { color: string; label: string; bg: string }> = {
  excellent: { color: "#22c55e", label: "Excellent", bg: "bg-green-900/20 border-green-700" },
  good:      { color: "#3b82f6", label: "Good",      bg: "bg-blue-900/20 border-blue-700" },
  fair:      { color: "#f59e0b", label: "Fair",       bg: "bg-amber-900/20 border-amber-700" },
  poor:      { color: "#ef4444", label: "Poor",       bg: "bg-red-900/20 border-red-700" },
};

function levelFor(score: number): string {
  if (score >= 80) return "excellent";
  if (score >= 60) return "good";
  if (score >= 40) return "fair";
  return "poor";
}

export function AttentionIndexGauge({ metric }: { metric?: ClassroomMetric }) {
  const score = metric?.attention_index ?? 0;
  const level = levelFor(score);
  const config = LEVEL_CONFIG[level];
  const chartData = [{ value: score, fill: config.color }];

  return (
    <div className={cn("bg-[#1a1f2e] rounded-xl border p-4 h-full", config.bg)}>
      <h3 className="text-sm font-medium text-gray-400 mb-2">Class Attention Index</h3>

      <div className="relative h-32">
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart
            cx="50%" cy="70%"
            innerRadius="60%" outerRadius="90%"
            startAngle={180} endAngle={0}
            data={chartData}
          >
            <RadialBar {...({
              minAngle: 15,
              background: { fill: "#2a3042" },
              clockWise: true,
              dataKey: "value",
              cornerRadius: 4,
            } as any)} />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center mt-6">
          <span className="text-3xl font-bold" style={{ color: config.color }}>
            {Math.round(score)}
          </span>
          <span className="text-xs text-gray-400">/ 100</span>
        </div>
      </div>

      <div className="text-center mb-3">
        <span className="text-sm font-semibold" style={{ color: config.color }}>
          {config.label}
        </span>
      </div>

      {metric ? (
        <div className="grid grid-cols-2 gap-2 text-center">
          <div className="bg-[#0d1117] rounded-lg py-1.5">
            <p className="text-sm font-semibold text-white">{metric.present_count}/{metric.expected_count}</p>
            <p className="text-xs text-gray-500">Present</p>
          </div>
          <div className="bg-[#0d1117] rounded-lg py-1.5">
            <p className="text-sm font-semibold text-white">{Math.round(metric.faculty_engagement_score)}</p>
            <p className="text-xs text-gray-500">Faculty Engagement</p>
          </div>
        </div>
      ) : (
        <p className="text-xs text-gray-600 text-center">No data yet</p>
      )}
    </div>
  );
}

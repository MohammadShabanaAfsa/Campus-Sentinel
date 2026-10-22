"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

interface FeatureContributions {
  [key: string]: number;
}

interface Explanation {
  method?: string;
  feature_contributions?: FeatureContributions;
  base_value?: number;
  predicted_value?: number;
  summary?: string;
}

interface ExplanationPanelProps {
  explanation: Explanation;
  threatScore: number;
}

const FEATURE_LABELS: Record<string, string> = {
  duration:            "Stay Duration",
  location_risk:       "Location Risk",
  crowd_density:       "Crowd Density",
  time_of_day:         "Time of Day",
  historical_pattern:  "Historical Pattern",
  movement_speed:      "Movement Speed",
  direction_changes:   "Direction Changes",
  zone_proximity:      "Zone Proximity",
  person_count:        "Person Count",
  abnormal_behavior:   "Abnormal Behavior",
};

function scoreColor(score: number): string {
  if (score >= 0.7) return "#ef4444";
  if (score >= 0.4) return "#f59e0b";
  return "#22c55e";
}

export function ExplanationPanel({ explanation, threatScore }: ExplanationPanelProps) {
  if (!explanation) return null;

  const contributions = explanation.feature_contributions ?? {};
  const chartData = Object.entries(contributions)
    .map(([key, value]) => ({
      feature: FEATURE_LABELS[key] ?? key.replace(/_/g, " "),
      value: Number(value.toFixed(3)),
      absValue: Math.abs(value),
    }))
    .sort((a, b) => b.absValue - a.absValue)
    .slice(0, 8);

  const maxVal = Math.max(...chartData.map((d) => d.absValue), 0.001);

  return (
    <div className="mt-3 bg-[#0d1117] border border-[#2a3042] rounded-xl p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-blue-500" />
          <span className="text-xs font-semibold text-blue-400 uppercase tracking-wide">
            AI Explanation ({explanation.method ?? "SHAP"})
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Threat Score</span>
          <span
            className="text-sm font-bold px-2 py-0.5 rounded"
            style={{ color: scoreColor(threatScore), backgroundColor: `${scoreColor(threatScore)}20` }}
          >
            {(threatScore * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* AI Summary */}
      {explanation.summary && (
        <p className="text-xs text-gray-300 italic bg-blue-900/10 border border-blue-900/30 rounded-lg px-3 py-2">
          &quot;{explanation.summary}&quot;
        </p>
      )}

      {/* Feature contribution bar chart */}
      {chartData.length > 0 && (
        <div>
          <p className="text-xs text-gray-500 mb-2">Feature Contributions</p>
          <ResponsiveContainer width="100%" height={chartData.length * 28 + 20}>
            <BarChart
              layout="vertical"
              data={chartData}
              margin={{ top: 0, right: 8, bottom: 0, left: 100 }}
            >
              <XAxis
                type="number"
                domain={[0, maxVal]}
                tick={{ fontSize: 9, fill: "#6b7280" }}
                tickFormatter={(v) => v.toFixed(2)}
              />
              <YAxis
                type="category"
                dataKey="feature"
                tick={{ fontSize: 10, fill: "#94a3b8" }}
                width={96}
              />
              <Tooltip
                contentStyle={{
                  background: "#1a1f2e",
                  border: "1px solid #2a3042",
                  fontSize: 11,
                  borderRadius: 6,
                }}
                formatter={(v: number) => [v.toFixed(3), "Contribution"]}
              />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {chartData.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={entry.value > 0.15 ? "#ef4444" : entry.value > 0.08 ? "#f59e0b" : "#3b82f6"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Base value footer */}
      {explanation.base_value !== undefined && (
        <div className="flex items-center gap-4 text-xs text-gray-600 border-t border-[#2a3042] pt-2">
          <span>Base value: <span className="text-gray-400">{explanation.base_value.toFixed(3)}</span></span>
          {explanation.predicted_value !== undefined && (
            <span>Predicted: <span className="text-gray-400">{explanation.predicted_value.toFixed(3)}</span></span>
          )}
        </div>
      )}
    </div>
  );
}

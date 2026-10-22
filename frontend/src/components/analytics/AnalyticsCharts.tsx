"use client";

import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line } from "recharts";
import { BarChart2 } from "lucide-react";
import { analyticsApi } from "@/lib/api";

export function AnalyticsCharts() {
  const [behaviorData, setBehaviorData] = useState<{ behavior_type: string; count: number }[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});

  useEffect(() => {
    const fetch = async () => {
      try {
        const [sumRes, behavRes] = await Promise.all([
          analyticsApi.summary(24),
          analyticsApi.behaviorDistribution(24),
        ]);
        setSummary(sumRes.data);
        setBehaviorData(behavRes.data.slice(0, 6));
      } catch (_) {}
    };
    fetch();
    const t = setInterval(fetch, 60000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] flex flex-col">
      <div className="flex items-center gap-2 p-4 border-b border-[#2a3042]">
        <BarChart2 className="w-4 h-4 text-blue-400" />
        <h3 className="text-sm font-medium text-white">24h Analytics</h3>
      </div>

      <div className="p-3 grid grid-cols-2 gap-2 border-b border-[#2a3042]">
        {[
          { label: "Detections", value: summary.total_detections || 0 },
          { label: "Persons", value: summary.person_detections || 0 },
          { label: "Alerts", value: summary.total_alerts || 0 },
          { label: "Anomalies", value: summary.behavior_anomalies || 0 },
        ].map(({ label, value }) => (
          <div key={label} className="bg-[#0d1117] rounded-lg p-2 text-center">
            <p className="text-lg font-bold text-white">{value.toLocaleString()}</p>
            <p className="text-xs text-gray-500">{label}</p>
          </div>
        ))}
      </div>

      <div className="flex-1 p-3">
        <p className="text-xs text-gray-500 mb-2">Behavior Distribution</p>
        {behaviorData.length > 0 ? (
          <ResponsiveContainer width="100%" height={150}>
            <BarChart data={behaviorData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <XAxis
                dataKey="behavior_type"
                tick={{ fontSize: 9, fill: "#6b7280" }}
                tickFormatter={(v) => v.split("_")[0]}
              />
              <YAxis tick={{ fontSize: 9, fill: "#6b7280" }} />
              <Tooltip
                contentStyle={{ background: "#1a1f2e", border: "1px solid #2a3042", fontSize: 11 }}
                labelStyle={{ color: "#fff" }}
              />
              <Bar dataKey="count" fill="#3b82f6" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-32 flex items-center justify-center text-gray-600 text-xs">
            No data yet
          </div>
        )}
      </div>
    </div>
  );
}

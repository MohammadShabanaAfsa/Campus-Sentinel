"use client";

import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { TrendingUp } from "lucide-react";
import { classroomApi } from "@/lib/api";
import type { ClassroomMetric } from "@/store/useAppStore";

interface Props {
  cameraId: string;
  hours?: number;
}

export function ClassroomTrendChart({ cameraId, hours = 4 }: Props) {
  const [data, setData] = useState<ClassroomMetric[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await classroomApi.metricHistory(cameraId, hours);
        if (!cancelled) setData(res.data);
      } catch (_) {
        // no-op
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const interval = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [cameraId, hours]);

  const chartData = data.map((m) => ({
    time: new Date(m.recorded_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    "Attention Index": m.attention_index,
    "Present": m.present_count,
    "Faculty Engagement": m.faculty_engagement_score,
  }));

  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] flex flex-col">
      <div className="flex items-center gap-2 p-4 border-b border-[#2a3042]">
        <TrendingUp className="w-4 h-4 text-blue-400" />
        <h3 className="text-sm font-medium text-white">Attention Trend ({hours}h)</h3>
      </div>

      <div className="p-3">
        {loading ? (
          <div className="h-52 flex items-center justify-center text-gray-600 text-xs">Loading...</div>
        ) : chartData.length === 0 ? (
          <div className="h-52 flex items-center justify-center text-gray-600 text-xs">No data yet</div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <XAxis dataKey="time" tick={{ fontSize: 9, fill: "#6b7280" }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: "#6b7280" }} />
              <Tooltip
                contentStyle={{ background: "#1a1f2e", border: "1px solid #2a3042", fontSize: 11 }}
                labelStyle={{ color: "#fff" }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="Attention Index" stroke="#3b82f6" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="Faculty Engagement" stroke="#22c55e" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="Present" stroke="#f59e0b" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

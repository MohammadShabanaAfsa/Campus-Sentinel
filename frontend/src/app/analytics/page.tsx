"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { Header } from "@/components/dashboard/Header";
import { BarChart2, TrendingUp, Users, AlertTriangle } from "lucide-react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from "recharts";
import { analyticsApi, csiApi } from "@/lib/api";
import { useRealtimeEvents } from "@/hooks/useRealtimeEvents";

const BEHAVIOR_COLORS = ["#3b82f6","#ef4444","#f59e0b","#22c55e","#a855f7","#ec4899","#14b8a6"];

export default function AnalyticsPage() {
  useRealtimeEvents();
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [hourlyData, setHourlyData] = useState<Record<string, unknown>[]>([]);
  const [behaviorData, setBehaviorData] = useState<{ behavior_type: string; count: number }[]>([]);
  const [csiHistory, setCsiHistory] = useState<Record<string, unknown>[]>([]);
  const [hours, setHours] = useState(24);

  useEffect(() => {
    const fetch = async () => {
      const [sumRes, hourRes, behavRes, csiRes] = await Promise.all([
        analyticsApi.summary(hours),
        analyticsApi.detectionsByHour(hours),
        analyticsApi.behaviorDistribution(hours),
        csiApi.history({ hours }),
      ]);
      setSummary(sumRes.data);
      // Group hourly data by hour
      const byHour: Record<string, Record<string, unknown>> = {};
      (hourRes.data as { hour: string; object_class: string; count: number }[]).forEach((row) => {
        const h = new Date(row.hour).getHours();
        const key = `${h}:00`;
        if (!byHour[key]) byHour[key] = { hour: key };
        byHour[key][row.object_class] = row.count;
      });
      setHourlyData(Object.values(byHour).sort((a, b) => ((a.hour as string) < (b.hour as string) ? -1 : 1)));
      setBehaviorData(behavRes.data);
      setCsiHistory(csiRes.data.map((s: { time: string; score: number; risk_level: string }) => ({
        time: new Date(s.time).getHours() + ":00",
        score: Math.round(s.score),
        risk: s.risk_level,
      })));
    };
    fetch();
    const t = setInterval(fetch, 60000);
    return () => clearInterval(t);
  }, [hours]);

  return (
    <div className="flex h-screen bg-[#0a0e1a] text-white overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-4 space-y-4">
          {/* Controls */}
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Analytics</h2>
            <div className="flex gap-2">
              {[6, 24, 48, 168].map((h) => (
                <button key={h} onClick={() => setHours(h)}
                  className={`px-3 py-1.5 rounded-lg text-xs border transition-colors ${
                    hours === h ? "bg-blue-600 border-blue-500 text-white" : "bg-[#1a1f2e] border-[#2a3042] text-gray-400"
                  }`}>
                  {h >= 168 ? "7d" : h >= 48 ? "2d" : `${h}h`}
                </button>
              ))}
            </div>
          </div>

          {/* KPI cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Total Detections", value: summary.total_detections || 0, icon: TrendingUp, color: "text-blue-400" },
              { label: "Person Detections", value: summary.person_detections || 0, icon: Users, color: "text-green-400" },
              { label: "Total Alerts", value: summary.total_alerts || 0, icon: AlertTriangle, color: "text-red-400" },
              { label: "Behavior Anomalies", value: summary.behavior_anomalies || 0, icon: BarChart2, color: "text-purple-400" },
            ].map(({ label, value, icon: Icon, color }) => (
              <div key={label} className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Icon className={`w-4 h-4 ${color}`} />
                  <span className="text-xs text-gray-400">{label}</span>
                </div>
                <p className={`text-2xl font-bold ${color}`}>{value.toLocaleString()}</p>
              </div>
            ))}
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {/* CSI over time */}
            <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] p-4">
              <h3 className="text-sm font-medium mb-3">Campus Safety Index — {hours}h</h3>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={csiHistory}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2a3042" />
                  <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#6b7280" }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#6b7280" }} />
                  <Tooltip contentStyle={{ background: "#1a1f2e", border: "1px solid #2a3042", fontSize: 11 }} />
                  <Line type="monotone" dataKey="score" stroke="#3b82f6" dot={false} strokeWidth={2} name="CSI Score" />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Detections by hour */}
            <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] p-4">
              <h3 className="text-sm font-medium mb-3">Detections by Hour</h3>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={hourlyData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2a3042" />
                  <XAxis dataKey="hour" tick={{ fontSize: 10, fill: "#6b7280" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#6b7280" }} />
                  <Tooltip contentStyle={{ background: "#1a1f2e", border: "1px solid #2a3042", fontSize: 11 }} />
                  <Bar dataKey="person" fill="#22c55e" name="Person" stackId="a" radius={[0,0,0,0]} />
                  <Bar dataKey="car" fill="#3b82f6" name="Car" stackId="a" />
                  <Bar dataKey="bicycle" fill="#a855f7" name="Bicycle" stackId="a" />
                  <Legend wrapperStyle={{ fontSize: 10 }} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Behavior distribution */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] p-4">
              <h3 className="text-sm font-medium mb-3">Behavior Distribution</h3>
              {behaviorData.length === 0 ? (
                <div className="flex items-center justify-center h-40 text-gray-600 text-sm">No behavior data yet</div>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={behaviorData} dataKey="count" nameKey="behavior_type" cx="50%" cy="50%" outerRadius={80} label={({ behavior_type, percent }) => `${behavior_type.split("_")[0]} ${(percent * 100).toFixed(0)}%`}>
                      {behaviorData.map((_, i) => (
                        <Cell key={i} fill={BEHAVIOR_COLORS[i % BEHAVIOR_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ background: "#1a1f2e", border: "1px solid #2a3042", fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] p-4">
              <h3 className="text-sm font-medium mb-3">Behavior Count Breakdown</h3>
              <div className="space-y-2">
                {behaviorData.slice(0, 8).map((b, i) => {
                  const total = behaviorData.reduce((s, x) => s + x.count, 0);
                  return (
                    <div key={b.behavior_type} className="flex items-center gap-2">
                      <span className="w-32 text-xs text-gray-400 capitalize truncate">
                        {b.behavior_type.replace(/_/g, " ")}
                      </span>
                      <div className="flex-1 bg-[#2a3042] rounded-full h-2">
                        <div className="h-2 rounded-full" style={{
                          width: `${(b.count / total) * 100}%`,
                          backgroundColor: BEHAVIOR_COLORS[i % BEHAVIOR_COLORS.length],
                        }} />
                      </div>
                      <span className="text-xs text-gray-400 w-8 text-right">{b.count}</span>
                    </div>
                  );
                })}
                {behaviorData.length === 0 && (
                  <p className="text-gray-600 text-sm text-center mt-8">No data yet</p>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { Header } from "@/components/dashboard/Header";
import { CheckCircle, Clock, AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { alertsApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";
import { useRealtimeEvents } from "@/hooks/useRealtimeEvents";
import { ExplanationPanel } from "@/components/alerts/ExplanationPanel";

const SEV_COLORS: Record<string, string> = {
  critical: "border-l-4 border-purple-600 bg-purple-900/10",
  high:     "border-l-4 border-red-600 bg-red-900/10",
  medium:   "border-l-4 border-amber-500 bg-amber-900/10",
  low:      "border-l-4 border-green-600 bg-green-900/10",
};
const SEV_BADGE: Record<string, string> = {
  critical: "bg-purple-600/20 text-purple-300 border-purple-700",
  high:     "bg-red-600/20 text-red-300 border-red-700",
  medium:   "bg-amber-600/20 text-amber-300 border-amber-700",
  low:      "bg-green-600/20 text-green-300 border-green-700",
};

type Alert = Record<string, unknown>;

function AlertRow({
  alert,
  onAck,
  onResolve,
}: {
  alert: Alert;
  onAck: (id: string) => void;
  onResolve: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const explanation = alert.explanation as Record<string, unknown> | undefined;
  const hasExplanation = Boolean(explanation && Object.keys(explanation).length > 0);

  return (
    <div className={cn("px-4 py-3", SEV_COLORS[alert.severity as string])}>
      <div className="flex items-start gap-3">
        {/* Expand toggle */}
        <button
          onClick={() => hasExplanation && setExpanded((v) => !v)}
          className={cn("mt-0.5 flex-shrink-0 transition-colors", hasExplanation ? "text-gray-400 hover:text-white" : "text-gray-700 cursor-default")}
        >
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>

        <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0 text-gray-400" />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={cn("text-xs px-1.5 py-0.5 rounded border", SEV_BADGE[alert.severity as string])}>
              {(alert.severity as string).toUpperCase()}
            </span>
            <span className="text-xs text-gray-500 capitalize">
              {alert.alert_type === "restricted_zone" ? "restricted area" : (alert.alert_type as string).replace(/_/g, " ")}
            </span>
            <span className="text-xs text-gray-600 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatDistanceToNow(new Date(alert.created_at as string), { addSuffix: true })}
            </span>
            {alert.threat_score !== undefined && (
              <span className="text-xs text-gray-600">
                Threat: <span className="text-gray-400">{((alert.threat_score as number) * 100).toFixed(0)}%</span>
              </span>
            )}
          </div>
          <p className="text-sm text-white font-medium">{alert.title as string}</p>
          {Boolean(alert.description) && (
            <p className="text-xs text-gray-400 mt-0.5">{alert.description as string}</p>
          )}
          {hasExplanation && !expanded && Boolean((explanation as Record<string, unknown>).summary) && (
            <p className="text-xs text-blue-400 mt-1 italic truncate">
              AI: {(explanation as Record<string, string>).summary}
            </p>
          )}

          {/* Expandable explanation */}
          {expanded && hasExplanation && (
            <ExplanationPanel
              explanation={explanation as Parameters<typeof ExplanationPanel>[0]["explanation"]}
              threatScore={(alert.threat_score as number) ?? 0}
            />
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2 flex-shrink-0 ml-2">
          {alert.status === "active" && (
            <>
              <button
                onClick={() => onAck(alert.id as string)}
                className="text-xs px-2 py-1 bg-amber-900/30 text-amber-300 border border-amber-700 rounded hover:bg-amber-900/50 transition-colors"
              >
                Ack
              </button>
              <button
                onClick={() => onResolve(alert.id as string)}
                className="text-xs px-2 py-1 bg-green-900/30 text-green-300 border border-green-700 rounded hover:bg-green-900/50 transition-colors"
              >
                Resolve
              </button>
            </>
          )}
          {alert.status !== "active" && (
            <span className="text-xs px-2 py-1 bg-[#2a3042] text-gray-400 rounded capitalize">
              {alert.status as string}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AlertsPage() {
  useRealtimeEvents();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [filter, setFilter] = useState("active");
  const [severity, setSeverity] = useState("all");
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<Record<string, number>>({});

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const params: Record<string, unknown> = { limit: 100 };
        if (filter !== "all") params.status = filter;
        if (severity !== "all") params.severity = severity;
        const [alertRes, statRes] = await Promise.all([
          alertsApi.list(params),
          alertsApi.stats(),
        ]);
        setAlerts(alertRes.data);
        setStats(statRes.data);
      } finally {
        setLoading(false);
      }
    };
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [filter, severity]);

  const handleAck = async (id: string) => {
    await alertsApi.acknowledge(id);
    setAlerts((prev) => prev.map((a) => a.id === id ? { ...a, status: "acknowledged" } : a));
  };
  const handleResolve = async (id: string) => {
    await alertsApi.resolve(id);
    setAlerts((prev) => prev.map((a) => a.id === id ? { ...a, status: "resolved" } : a));
  };

  return (
    <div className="flex h-screen bg-[#0a0e1a] text-white overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-4 space-y-4">
          {/* KPI stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Active",   value: stats.active   ?? 0, color: "text-red-400" },
              { label: "Critical", value: stats.critical  ?? 0, color: "text-purple-400" },
              { label: "Last 24h", value: stats.last_24h  ?? 0, color: "text-amber-400" },
              { label: "Total",    value: stats.total     ?? 0, color: "text-gray-300" },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] p-4 text-center">
                <p className={cn("text-2xl font-bold", color)}>{value}</p>
                <p className="text-xs text-gray-500 mt-1">{label}</p>
              </div>
            ))}
          </div>

          {/* Filter bar */}
          <div className="flex flex-wrap gap-2 items-center">
            <div className="flex gap-1">
              {["active", "acknowledged", "resolved", "all"].map((f) => (
                <button key={f} onClick={() => setFilter(f)}
                  className={cn("px-3 py-1.5 rounded-lg text-xs capitalize border transition-colors",
                    filter === f
                      ? "bg-blue-600 border-blue-500 text-white"
                      : "bg-[#1a1f2e] border-[#2a3042] text-gray-400 hover:text-white"
                  )}>
                  {f}
                </button>
              ))}
            </div>
            <div className="ml-auto flex gap-1">
              {["all", "critical", "high", "medium", "low"].map((s) => (
                <button key={s} onClick={() => setSeverity(s)}
                  className={cn("px-3 py-1.5 rounded-lg text-xs capitalize border transition-colors",
                    severity === s
                      ? "bg-blue-600/30 border-blue-500 text-blue-300"
                      : "bg-[#1a1f2e] border-[#2a3042] text-gray-400 hover:text-white"
                  )}>
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Hint */}
          <p className="text-xs text-gray-600">
            Click <ChevronRight className="inline w-3 h-3" /> on any alert to see AI explanation (SHAP feature contributions).
          </p>

          {/* Alert list */}
          <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] overflow-hidden">
            {loading ? (
              <div className="flex items-center justify-center h-40">
                <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : alerts.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-gray-500">
                <CheckCircle className="w-10 h-10 mb-2 text-green-500" />
                <p className="text-sm">No alerts match the current filter</p>
              </div>
            ) : (
              <div className="divide-y divide-[#2a3042]">
                {alerts.map((alert) => (
                  <AlertRow
                    key={alert.id as string}
                    alert={alert}
                    onAck={handleAck}
                    onResolve={handleResolve}
                  />
                ))}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

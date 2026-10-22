"use client";

import { useEffect } from "react";
import { Bell, CheckCircle, XCircle, Clock } from "lucide-react";
import { useAppStore } from "@/store/useAppStore";
import { alertsApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { formatDistanceToNow } from "date-fns";

const SEVERITY_STYLES: Record<string, string> = {
  critical: "border-l-4 border-purple-600 bg-purple-900/10",
  high:     "border-l-4 border-red-600 bg-red-900/10",
  medium:   "border-l-4 border-amber-600 bg-amber-900/10",
  low:      "border-l-4 border-green-600 bg-green-900/10",
};

const SEVERITY_BADGE: Record<string, string> = {
  critical: "bg-purple-600/20 text-purple-400 border border-purple-700",
  high:     "bg-red-600/20 text-red-400 border border-red-700",
  medium:   "bg-amber-600/20 text-amber-400 border border-amber-700",
  low:      "bg-green-600/20 text-green-400 border border-green-700",
};

export function AlertPanel() {
  const alerts = useAppStore((s) => s.alerts);
  const addAlert = useAppStore((s) => s.addAlert);
  const acknowledgeAlert = useAppStore((s) => s.acknowledgeAlert);

  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const res = await alertsApi.list({ status: "active", limit: 50 });
        res.data.forEach((a: Parameters<typeof addAlert>[0]) => addAlert(a));
      } catch (_) {}
    };
    fetchAlerts();
  }, [addAlert]);

  const activeAlerts = alerts.filter((a) => a.status === "active").slice(0, 20);

  const handleAck = async (id: string) => {
    try {
      await alertsApi.acknowledge(id);
      acknowledgeAlert(id);
    } catch (_) {}
  };

  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] h-full flex flex-col">
      <div className="flex items-center justify-between p-4 border-b border-[#2a3042]">
        <div className="flex items-center gap-2">
          <Bell className="w-4 h-4 text-red-400" />
          <h3 className="text-sm font-medium text-white">Active Alerts</h3>
          {activeAlerts.length > 0 && (
            <span className="bg-red-600 text-white text-xs px-1.5 py-0.5 rounded-full">
              {activeAlerts.length}
            </span>
          )}
        </div>
        <span className="text-xs text-gray-500">Real-time</span>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {activeAlerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-gray-500">
            <CheckCircle className="w-8 h-8 mb-2 text-green-500" />
            <p className="text-sm">No active alerts</p>
          </div>
        ) : (
          activeAlerts.map((alert) => (
            <div
              key={alert.id}
              className={cn("rounded-lg p-3 flex items-start gap-3", SEVERITY_STYLES[alert.severity])}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={cn("text-xs px-1.5 py-0.5 rounded font-medium", SEVERITY_BADGE[alert.severity])}>
                    {alert.severity.toUpperCase()}
                  </span>
                  <span className="text-xs text-gray-500 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
                  </span>
                </div>
                <p className="text-sm text-white font-medium truncate">{alert.title}</p>
                {alert.threat_score > 0 && (
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-gray-500">Threat:</span>
                    <div className="flex-1 bg-[#2a3042] rounded-full h-1">
                      <div
                        className="h-1 rounded-full bg-red-500"
                        style={{ width: `${Math.round(alert.threat_score * 100)}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-400">{Math.round(alert.threat_score * 100)}%</span>
                  </div>
                )}
              </div>
              <button
                onClick={() => handleAck(alert.id)}
                className="text-gray-500 hover:text-green-400 flex-shrink-0 mt-0.5"
                title="Acknowledge"
              >
                <CheckCircle className="w-4 h-4" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { Clock, AlertCircle } from "lucide-react";
import { analyticsApi } from "@/lib/api";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";

const BEHAVIOR_COLORS: Record<string, string> = {
  loitering:         "bg-amber-500",
  crowd_surge:       "bg-red-500",
  restricted_access: "bg-purple-500",
  running:           "bg-blue-500",
  crowd_formation:   "bg-orange-500",
  abandoned_object:  "bg-yellow-500",
};

export function IncidentTimeline() {
  const alerts = useAppStore((s) => s.alerts);
  const recentAlerts = alerts.slice(0, 10);

  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] flex flex-col">
      <div className="flex items-center gap-2 p-4 border-b border-[#2a3042]">
        <Clock className="w-4 h-4 text-blue-400" />
        <h3 className="text-sm font-medium text-white">Incident Timeline</h3>
      </div>

      <div className="flex-1 p-3 overflow-y-auto">
        {recentAlerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-24 text-gray-500">
            <Clock className="w-8 h-8 mb-2" />
            <p className="text-xs">No recent incidents</p>
          </div>
        ) : (
          <div className="relative">
            <div className="absolute left-4 top-0 bottom-0 w-px bg-[#2a3042]" />
            <div className="space-y-3">
              {recentAlerts.map((alert, i) => (
                <div key={alert.id} className="flex gap-3 pl-2">
                  <div className={cn(
                    "w-3 h-3 rounded-full flex-shrink-0 mt-1 z-10",
                    BEHAVIOR_COLORS[alert.alert_type] || "bg-gray-500"
                  )} />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-white truncate">{alert.title}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-gray-500">
                        {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
                      </span>
                      <span className={cn(
                        "text-xs px-1 rounded",
                        alert.severity === "critical" ? "text-purple-400" :
                        alert.severity === "high" ? "text-red-400" :
                        alert.severity === "medium" ? "text-amber-400" : "text-green-400"
                      )}>
                        {alert.severity}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

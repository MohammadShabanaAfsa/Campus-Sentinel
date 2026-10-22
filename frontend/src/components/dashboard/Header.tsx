"use client";

import { Bell, User, RefreshCw } from "lucide-react";
import { useAppStore } from "@/store/useAppStore";
import { useShallow } from "zustand/react/shallow";
import { cn } from "@/lib/utils";
import { format } from "date-fns/format";
import { useEffect, useState } from "react";
import Link from "next/link";

export function Header() {
  const { alerts, csi, isConnected } = useAppStore(
    useShallow((s) => ({ alerts: s.alerts, csi: s.csi, isConnected: s.isConnected }))
  );
  const [time, setTime] = useState<Date | null>(null);
  const csiError = useAppStore((s) => s.csiError);
  const backendConnected = useAppStore((s) => s.backendConnected);
  const authenticationRequired = useAppStore((s) => s.authenticationRequired);
  const criticalAlerts = alerts.filter((a) => a.severity === "critical" && a.status === "active").length;

  useEffect(() => {
    setTime(new Date());
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  const riskColors: Record<string, string> = {
    safe: "text-green-400 bg-green-900/30 border-green-700",
    low_risk: "text-lime-400 bg-lime-900/30 border-lime-700",
    moderate: "text-amber-400 bg-amber-900/30 border-amber-700",
    high_risk: "text-red-400 bg-red-900/30 border-red-700",
    critical: "text-purple-400 bg-purple-900/30 border-purple-700 animate-pulse",
  };

  return (
    <header className="h-14 bg-[#0d1117] border-b border-[#2a3042] flex items-center justify-between px-4">
      <div className="flex items-center gap-4">
        {authenticationRequired && <Link href="/login" className="text-sm text-amber-400">Session expired. Sign in</Link>}
        <h1 className="text-sm font-semibold text-white">Smart Surveillance Dashboard</h1>
        <div className={cn("text-xs px-2 py-1 rounded border font-medium", csi ? riskColors[csi.risk_level] : "text-gray-400 border-gray-700")}>
          CSI: {csi ? `${Math.round(csi.overall_score)} \u2014 ${csi.risk_level.replaceAll("_", " ").toUpperCase()}${csiError ? " (stale)" : ""}` : csiError ? "Unavailable" : "Loading\u2026"}
        </div>
      </div>

      <div className="flex items-center gap-4">
        {time && (
          <span className="text-xs text-gray-400 hidden md:block font-mono">
            {format(time, "yyyy-MM-dd HH:mm:ss")} UTC
          </span>
        )}

        {criticalAlerts > 0 && (
          <div className="flex items-center gap-1 bg-red-900/40 border border-red-700 rounded px-2 py-1 animate-pulse">
            <Bell className="w-3 h-3 text-red-400" />
            <span className="text-xs text-red-400 font-medium">{criticalAlerts} Critical</span>
          </div>
        )}

        <div className={cn("flex items-center gap-1", isConnected || backendConnected ? "text-green-400" : "text-red-400")}>
          <RefreshCw className={cn("w-3 h-3", isConnected && "animate-spin")} />
          <span className="text-xs">{authenticationRequired ? "Sign in required" : isConnected ? "Live" : backendConnected ? "API connected" : backendConnected === null ? "Connecting" : "Offline"}</span>
        </div>

        <button className="w-8 h-8 bg-[#1a1f2e] rounded-full flex items-center justify-center hover:bg-[#2a3042]">
          <User className="w-4 h-4 text-gray-400" />
        </button>
      </div>
    </header>
  );
}

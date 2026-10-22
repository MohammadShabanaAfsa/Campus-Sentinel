"use client";

import { Shield, Camera, Bell, Map, BarChart2, Settings, Activity, Cpu, FileWarning, LogOut, School } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { useShallow } from "zustand/react/shallow";
import { clearSession } from "@/lib/session";

const NAV_ITEMS = [
  { href: "/dashboard",  label: "Dashboard",   icon: Activity },
  { href: "/cameras",    label: "Cameras",     icon: Camera },
  { href: "/classroom",  label: "Classrooms",  icon: School },
  { href: "/alerts",     label: "Alerts",      icon: Bell },
  { href: "/incidents",  label: "Incidents",   icon: FileWarning },
  { href: "/map",        label: "Campus Map",  icon: Map },
  { href: "/analytics",  label: "Analytics",   icon: BarChart2 },
  { href: "/agents",     label: "AI Agents",   icon: Cpu },
  { href: "/settings",   label: "Settings",    icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { alerts, isConnected } = useAppStore(
    useShallow((s) => ({ alerts: s.alerts, isConnected: s.isConnected }))
  );

  const handleLogout = () => {
    clearSession();
    router.push("/login");
  };
  const activeAlerts = alerts.filter((a) => a.status === "active").length;

  return (
    <aside className="w-16 lg:w-60 bg-[#0d1117] border-r border-[#2a3042] flex flex-col h-full">
      {/* Logo */}
      <div className="p-4 flex items-center gap-3 border-b border-[#2a3042]">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center flex-shrink-0">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div className="hidden lg:block">
          <p className="text-sm font-bold text-white leading-none">Campus</p>
          <p className="text-xs text-blue-400">Sentinel</p>
        </div>
      </div>

      {/* Connection status */}
      <div className="px-3 py-2 hidden lg:flex items-center gap-2">
        <span className={cn("w-2 h-2 rounded-full", isConnected ? "bg-green-500 animate-pulse" : "bg-red-500")} />
        <span className="text-xs text-gray-400">{isConnected ? "Live" : "Disconnected"}</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-2 space-y-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors relative",
                isActive
                  ? "bg-blue-600/20 text-blue-400 border border-blue-600/30"
                  : "text-gray-400 hover:bg-white/5 hover:text-white"
              )}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              <span className="hidden lg:block">{label}</span>
              {label === "Alerts" && activeAlerts > 0 && (
                <span className="hidden lg:flex ml-auto bg-red-600 text-white text-xs rounded-full w-5 h-5 items-center justify-center">
                  {activeAlerts > 9 ? "9+" : activeAlerts}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Logout */}
      <div className="p-2 border-t border-[#2a3042]">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-red-900/20 hover:text-red-400 transition-colors"
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          <span className="hidden lg:block">Logout</span>
        </button>
        <p className="text-xs text-gray-600 mt-1 hidden lg:block px-1">v1.0.0 Production</p>
      </div>
    </aside>
  );
}

"use client";

import { Suspense } from "react";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { Header } from "@/components/dashboard/Header";
import { CSIGauge } from "@/components/dashboard/CSIGauge";
import { AlertPanel } from "@/components/alerts/AlertPanel";
import { CameraGrid } from "@/components/cameras/CameraGrid";
import { ThreatPredictions } from "@/components/dashboard/ThreatPredictions";
import { IncidentTimeline } from "@/components/dashboard/IncidentTimeline";
import { AnalyticsCharts } from "@/components/analytics/AnalyticsCharts";
import { CampusMap } from "@/components/map/CampusMap";
import { useRealtimeEvents } from "@/hooks/useRealtimeEvents";
import { LoadingSpinner } from "@/components/ui/loading-spinner";

export default function DashboardPage() {
  useRealtimeEvents(); // Connect WebSocket globally

  return (
    <div className="flex h-screen bg-[#0a0e1a] text-white overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-4 space-y-4">
          {/* Top Row: CSI + Alert Stats */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            <div className="lg:col-span-1">
              <Suspense fallback={<LoadingSpinner />}>
                <CSIGauge />
              </Suspense>
            </div>
            <div className="lg:col-span-3">
              <Suspense fallback={<LoadingSpinner />}>
                <AlertPanel />
              </Suspense>
            </div>
          </div>

          {/* Middle Row: Live Cameras + Map */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <div className="xl:col-span-2">
              <Suspense fallback={<LoadingSpinner />}>
                <CameraGrid />
              </Suspense>
            </div>
            <div className="xl:col-span-1">
              <Suspense fallback={<LoadingSpinner />}>
                <CampusMap />
              </Suspense>
            </div>
          </div>

          {/* Bottom Row: Threats + Timeline + Analytics */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <Suspense fallback={<LoadingSpinner />}>
              <ThreatPredictions />
            </Suspense>
            <Suspense fallback={<LoadingSpinner />}>
              <IncidentTimeline />
            </Suspense>
            <Suspense fallback={<LoadingSpinner />}>
              <AnalyticsCharts />
            </Suspense>
          </div>
        </main>
      </div>
    </div>
  );
}

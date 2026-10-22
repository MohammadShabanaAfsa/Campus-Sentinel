"use client";

import dynamic from "next/dynamic";
import { useEffect } from "react";
import { camerasApi } from "@/lib/api";
import { useAppStore } from "@/store/useAppStore";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { Header } from "@/components/dashboard/Header";
import { useRealtimeEvents } from "@/hooks/useRealtimeEvents";
import { LoadingSpinner } from "@/components/ui/loading-spinner";

const CampusMapEnhanced = dynamic(
  () => import("@/components/map/CampusMapEnhanced").then(m => ({ default: m.CampusMapEnhanced })),
  { ssr: false, loading: () => <LoadingSpinner /> }
);

export default function MapPage() {
  useRealtimeEvents();
  // A direct /map visit has not mounted the dashboard's CameraGrid loader.
  const setCameras = useAppStore((state) => state.setCameras);
  useEffect(() => {
    let mounted = true;
    let fetching = false;
    const loadCameras = async () => {
      if (fetching) return;
      fetching = true;
      try {
        const response = await camerasApi.list();
        if (!Array.isArray(response.data)) throw new Error("Invalid camera response");
        if (mounted) setCameras(response.data);
      } catch {
        if (mounted) console.warn("[Map] Camera update unavailable; retaining existing markers");
      } finally { fetching = false; }
    };
    void loadCameras();
    const timer = setInterval(loadCameras, 10000);
    return () => { mounted = false; clearInterval(timer); };
  }, [setCameras]);
  return (
    <div className="flex h-screen bg-[#0a0e1a] text-white overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-hidden p-4">
          <CampusMapEnhanced />
        </main>
      </div>
    </div>
  );
}

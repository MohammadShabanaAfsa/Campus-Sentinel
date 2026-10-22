"use client";

import { Suspense } from "react";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { Header } from "@/components/dashboard/Header";
import { CamerasManagementView } from "@/components/cameras/CamerasManagementView";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { useRealtimeEvents } from "@/hooks/useRealtimeEvents";

export default function CamerasPage() {
  useRealtimeEvents();
  return (
    <div className="flex h-screen bg-[#0a0e1a] text-white overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-4">
          <Suspense fallback={<LoadingSpinner />}>
            <CamerasManagementView />
          </Suspense>
        </main>
      </div>
    </div>
  );
}

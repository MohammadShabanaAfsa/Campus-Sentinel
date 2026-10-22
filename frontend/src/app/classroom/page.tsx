"use client";

import { useState } from "react";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { Header } from "@/components/dashboard/Header";
import { useRealtimeEvents } from "@/hooks/useRealtimeEvents";
import { useAppStore } from "@/store/useAppStore";
import { ClassroomOverviewGrid } from "@/components/classroom/ClassroomOverviewGrid";
import { AttentionIndexGauge } from "@/components/classroom/AttentionIndexGauge";
import { ClassroomTrendChart } from "@/components/classroom/ClassroomTrendChart";
import { ClassroomConfigPanel } from "@/components/classroom/ClassroomConfigPanel";

export default function ClassroomPage() {
  useRealtimeEvents();
  const [selectedCameraId, setSelectedCameraId] = useState<string | null>(null);
  const classroomMetrics = useAppStore((s) => s.classroomMetrics);

  return (
    <div className="flex h-screen bg-[#0a0e1a] text-white overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Classroom Monitoring</h2>
              <p className="text-xs text-gray-500 mt-0.5">
                Attendance, engagement, and attention tracking across all classrooms — click a room for details.
              </p>
            </div>
          </div>

          <ClassroomOverviewGrid selectedCameraId={selectedCameraId} onSelect={setSelectedCameraId} />

          {selectedCameraId && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <AttentionIndexGauge metric={classroomMetrics[selectedCameraId]} />
              <div className="lg:col-span-2">
                <ClassroomTrendChart cameraId={selectedCameraId} />
              </div>
              <div className="lg:col-span-3 lg:max-w-sm">
                <ClassroomConfigPanel cameraId={selectedCameraId} />
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

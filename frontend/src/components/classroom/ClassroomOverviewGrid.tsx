"use client";

import { useEffect, useState } from "react";
import { School, Wifi, WifiOff, Moon, MessageCircle, UserX, GraduationCap } from "lucide-react";
import { classroomApi } from "@/lib/api";
import { useAppStore } from "@/store/useAppStore";
import { cn } from "@/lib/utils";

interface ClassroomOverviewItem {
  camera_id: string;
  camera_name: string;
  location_name: string;
  status: string;
  latest_metric: {
    present_count: number;
    expected_count: number;
    missing_count: number;
    sleeping_count: number;
    talking_count: number;
    faculty_present: boolean;
    faculty_engagement_score: number;
    attention_index: number;
  } | null;
}

const LEVEL_COLOR: Record<string, string> = {
  excellent: "text-green-400 bg-green-900/20 border-green-700",
  good: "text-blue-400 bg-blue-900/20 border-blue-700",
  fair: "text-amber-400 bg-amber-900/20 border-amber-700",
  poor: "text-red-400 bg-red-900/20 border-red-700",
};

function levelFor(score: number): string {
  if (score >= 80) return "excellent";
  if (score >= 60) return "good";
  if (score >= 40) return "fair";
  return "poor";
}

interface GridProps {
  selectedCameraId?: string | null;
  onSelect?: (cameraId: string) => void;
}

export function ClassroomOverviewGrid({ selectedCameraId, onSelect }: GridProps) {
  const [classrooms, setClassrooms] = useState<ClassroomOverviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const realtimeMetrics = useAppStore((s) => s.classroomMetrics);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await classroomApi.list();
        setClassrooms(res.data);
      } catch (_) {
        // no-op — keep last known list
      } finally {
        setLoading(false);
      }
    };
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] p-8 text-center text-gray-500">
        Loading classrooms...
      </div>
    );
  }

  if (classrooms.length === 0) {
    return (
      <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] p-8 flex flex-col items-center justify-center text-gray-500">
        <School className="w-10 h-10 mb-2" />
        <p className="text-sm">No classrooms configured</p>
        <p className="text-xs mt-1">Set a camera&apos;s zone type to &quot;classroom&quot; in Settings to enable monitoring.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {classrooms.map((room) => {
        // Prefer the realtime WebSocket snapshot when available — it's fresher
        // than the 15s REST poll.
        const live = realtimeMetrics[room.camera_id];
        const metric = live ?? room.latest_metric;
        const attentionIndex = metric?.attention_index ?? 0;
        const level = levelFor(attentionIndex);

        return (
          <div
            key={room.camera_id}
            onClick={() => onSelect?.(room.camera_id)}
            className={cn(
              "bg-[#1a1f2e] rounded-xl border p-4 transition-colors",
              onSelect && "cursor-pointer hover:border-blue-600/50",
              selectedCameraId === room.camera_id ? "border-blue-600" : "border-[#2a3042]"
            )}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-white truncate">{room.camera_name}</p>
                <p className="text-xs text-gray-500 truncate">{room.location_name}</p>
              </div>
              <div className={cn("flex items-center gap-1 flex-shrink-0", room.status === "online" ? "text-green-400" : "text-gray-500")}>
                {room.status === "online" ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
              </div>
            </div>

            <div className={cn("rounded-lg border px-3 py-2 mb-3 flex items-center justify-between", LEVEL_COLOR[level])}>
              <span className="text-xs font-medium">Attention Index</span>
              <span className="text-lg font-bold">{Math.round(attentionIndex)}</span>
            </div>

            {metric ? (
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="flex items-center gap-1.5 text-gray-400">
                  <UserX className="w-3.5 h-3.5 text-gray-500" />
                  <span>
                    {metric.present_count}/{metric.expected_count} present
                    {metric.missing_count > 0 && <span className="text-red-400"> ({metric.missing_count} missing)</span>}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-gray-400">
                  <GraduationCap className="w-3.5 h-3.5 text-gray-500" />
                  <span>{metric.faculty_present ? `Faculty ${Math.round(metric.faculty_engagement_score)}%` : "No faculty detected"}</span>
                </div>
                <div className="flex items-center gap-1.5 text-gray-400">
                  <Moon className="w-3.5 h-3.5 text-gray-500" />
                  <span>{metric.sleeping_count} sleeping</span>
                </div>
                <div className="flex items-center gap-1.5 text-gray-400">
                  <MessageCircle className="w-3.5 h-3.5 text-gray-500" />
                  <span>{metric.talking_count} talking</span>
                </div>
              </div>
            ) : (
              <p className="text-xs text-gray-600 text-center py-2">No data yet</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

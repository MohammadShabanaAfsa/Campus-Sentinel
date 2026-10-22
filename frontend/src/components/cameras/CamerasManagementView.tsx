"use client";

import { useEffect, useState, useCallback } from "react";
import { Camera, Plus, RefreshCw, Play, Square, RotateCcw, Settings, Trash2 } from "lucide-react";
import { camerasApi } from "@/lib/api";
import api from "@/lib/api";
import { cn } from "@/lib/utils";
import { AddCameraModal } from "@/components/cameras/AddCameraModal";
import { LiveCameraModal } from "@/components/cameras/LiveCameraModal";
import { EditCameraModal } from "./EditCameraModal";
import { ZoneDrawerModal } from "@/components/cameras/ZoneDrawerModal";

export interface CameraItem {
  id: string;
  name: string;
  location_name: string;
  rtsp_url: string;
  last_error?: string | null;
  status: "online" | "offline" | "error" | "maintenance";
  zone_type: string;
  latitude?: number;
  longitude?: number;
  is_active: boolean;
  is_recording: boolean;
  resolution: string;
  fps: number;
}

const STATUS_BADGE = {
  online:      "bg-green-900/40 text-green-400 border-green-700",
  offline:     "bg-gray-800 text-gray-400 border-gray-600",
  error:       "bg-red-900/40 text-red-400 border-red-700",
  maintenance: "bg-amber-900/40 text-amber-400 border-amber-700",
};

const ZONE_COLORS: Record<string, string> = {
  entrance:   "text-blue-400",
  corridor:   "text-cyan-400",
  lab:        "text-purple-400",
  parking:    "text-gray-400",
  cafeteria:  "text-orange-400",
  library:    "text-green-400",
  admin:      "text-yellow-400",
  restricted: "text-red-400",
  general:    "text-gray-400",
};

export function CamerasManagementView() {
  const [cameras, setCameras] = useState<CameraItem[]>([]);
  const [streamStatus, setStreamStatus] = useState<Record<string, Record<string, unknown>>>({});
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedCamera, setSelectedCamera] = useState<CameraItem | null>(null);
  const [showLiveModal, setShowLiveModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showZoneModal, setShowZoneModal] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [camRes, statusRes] = await Promise.all([
        camerasApi.list(),
        api.get("/api/v1/streams/status").catch(() => ({ data: {} })),
      ]);
      setCameras(camRes.data);
      setStreamStatus(statusRes.data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const t = setInterval(fetchData, 10000);
    return () => clearInterval(t);
  }, [fetchData]);

  const handleStreamAction = async (camId: string, action: "start" | "stop" | "restart") => {
    await api.post(`/api/v1/streams/${camId}/${action}`);
    setTimeout(fetchData, 1500);
  };

  const handleCameraAdded = () => {
    setShowAddModal(false);
    fetchData();
  };

  const handleDeleteCamera = async (cam: CameraItem) => {
    if (!confirm(`Delete camera "${cam.name}"? This cannot be undone.`)) return;
    try {
      await camerasApi.delete(cam.id);
      fetchData();
    } catch (_) {}
  };

  const onlineCameras = cameras.filter((c) => c.status === "online").length;

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Camera Management</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            {onlineCameras}/{cameras.length} cameras online
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchData}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1a1f2e] border border-[#2a3042] rounded-lg text-sm text-gray-400 hover:text-white"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm text-white"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Camera
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: "Total Cameras", value: cameras.length, color: "text-white" },
          { label: "Online",  value: cameras.filter((c) => c.status === "online").length,  color: "text-green-400" },
          { label: "Offline", value: cameras.filter((c) => c.status === "offline").length, color: "text-gray-400" },
          { label: "Error",   value: cameras.filter((c) => c.status === "error").length,   color: "text-red-400" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-[#1a1f2e] rounded-lg border border-[#2a3042] p-3 text-center">
            <p className={cn("text-2xl font-bold", color)}>{value}</p>
            <p className="text-xs text-gray-500 mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      {/* Camera cards */}
      {loading ? (
        <div className="flex items-center justify-center h-40">
          <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : cameras.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 text-gray-500 border border-dashed border-[#2a3042] rounded-xl">
          <Camera className="w-12 h-12 mb-3" />
          <p className="text-sm font-medium">No cameras configured</p>
          <p className="text-xs mt-1 mb-4">Add your first RTSP camera to get started</p>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
          >
            Add Camera
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {cameras.map((cam) => {
            const st = streamStatus[cam.id] || {};
            return (
              <CameraCard
                key={cam.id}
                camera={cam}
                streamInfo={st}
                onView={() => { setSelectedCamera(cam); setShowLiveModal(true); }}
                onEdit={() => { setSelectedCamera(cam); setShowEditModal(true); }}
                onZone={() => { setSelectedCamera(cam); setShowZoneModal(true); }}
                onStreamAction={handleStreamAction}
                onDelete={() => handleDeleteCamera(cam)}
              />
            );
          })}
        </div>
      )}

      {/* Modals */}
      {showEditModal && selectedCamera && <EditCameraModal camera={selectedCamera} onClose={() => setShowEditModal(false)} onSaved={() => { setShowEditModal(false); fetchData(); }} />}
      {showAddModal && (
        <AddCameraModal onClose={() => setShowAddModal(false)} onAdded={handleCameraAdded} />
      )}
      {showLiveModal && selectedCamera && (
        <LiveCameraModal camera={selectedCamera} onClose={() => setShowLiveModal(false)} />
      )}
      {showZoneModal && selectedCamera && (
        <ZoneDrawerModal camera={selectedCamera} onClose={() => { setShowZoneModal(false); fetchData(); }} />
      )}
    </div>
  );
}

function CameraCard({
  camera, streamInfo, onView, onEdit, onZone, onStreamAction, onDelete,
}: {
  camera: CameraItem;
  streamInfo: Record<string, unknown>;
  onView: () => void;
  onEdit: () => void;
  onZone: () => void;
  onStreamAction: (id: string, action: "start" | "stop" | "restart") => void;
  onDelete: () => void;
}) {
  const isOnline = camera.status === "online";
  const framesProcessed = (streamInfo.frames_processed as number) || 0;
  const uptime = (streamInfo.uptime_secs as number) || 0;

  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] overflow-hidden hover:border-blue-600/40 transition-colors">
      {/* Preview thumbnail */}
      <div
        className="relative aspect-video bg-[#0d1117] cursor-pointer group"
        onClick={onView}
      >
        {isOnline ? (
          <div className="w-full h-full flex flex-col items-center justify-center gap-2">
            <div className="w-8 h-8 border-2 border-blue-500/40 border-t-blue-500 rounded-full animate-spin" />
            <p className="text-xs text-gray-500">Click to view live feed</p>
          </div>
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <div className="text-center">
              <Camera className="w-10 h-10 mx-auto mb-2 text-gray-700" />
              <p className="text-xs text-gray-600 capitalize">{camera.status}</p>
            </div>
          </div>
        )}

        {/* Overlay badges */}
        <div className="absolute top-2 left-2 flex gap-1">
          {isOnline && (
            <span className="bg-red-600 text-white text-xs px-1.5 py-0.5 rounded font-medium">LIVE</span>
          )}
          <span className={cn(
            "text-xs px-1.5 py-0.5 rounded border capitalize",
            STATUS_BADGE[camera.status]
          )}>
            {camera.status}
          </span>
        </div>

        <div className="absolute top-2 right-2">
          <span className={cn("text-xs font-medium capitalize", ZONE_COLORS[camera.zone_type] || "text-gray-400")}>
            {camera.zone_type}
          </span>
        </div>

        {/* Stream actions overlay */}
        <div className="absolute bottom-2 right-2 hidden group-hover:flex gap-1">
          {!isOnline ? (
            <button
              onClick={(e) => { e.stopPropagation(); onStreamAction(camera.id, "start"); }}
              className="p-1.5 bg-green-600/80 hover:bg-green-600 rounded text-white"
              title="Start stream"
            >
              <Play className="w-3 h-3" />
            </button>
          ) : (
            <>
              <button
                onClick={(e) => { e.stopPropagation(); onStreamAction(camera.id, "restart"); }}
                className="p-1.5 bg-amber-600/80 hover:bg-amber-600 rounded text-white"
                title="Restart stream"
              >
                <RotateCcw className="w-3 h-3" />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onStreamAction(camera.id, "stop"); }}
                className="p-1.5 bg-red-600/80 hover:bg-red-600 rounded text-white"
                title="Stop stream"
              >
                <Square className="w-3 h-3" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Info */}
      <div className="p-3">
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white truncate">{camera.name}</p>
            <p className="text-xs text-gray-500 truncate">{camera.location_name}</p>
          </div>
          <div className="flex items-center gap-1 flex-shrink-0">
            <button
              onClick={onEdit}
              className="p-1.5 text-gray-500 hover:text-blue-400 hover:bg-blue-900/20 rounded"
              title="Edit camera settings"
            >
              <Settings className="w-3.5 h-3.5" />
            </button>
            <button onClick={onZone} className="p-1.5 text-gray-400" title="Configure zones">Zones</button>
            <button
              onClick={onDelete}
              className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-900/20 rounded"
              title="Delete camera"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {camera.status === "error" && camera.last_error && <p className="text-xs text-red-400 mb-2">{camera.last_error}</p>}
        {/* Stats */}
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-[#0d1117] rounded p-1.5">
            <p className="text-xs font-medium text-white">{framesProcessed.toLocaleString()}</p>
            <p className="text-xs text-gray-600">Frames</p>
          </div>
          <div className="bg-[#0d1117] rounded p-1.5">
            <p className="text-xs font-medium text-white">
              {uptime >= 3600
                ? `${Math.floor(uptime / 3600)}h`
                : uptime >= 60
                ? `${Math.floor(uptime / 60)}m`
                : `${Math.floor(uptime)}s`}
            </p>
            <p className="text-xs text-gray-600">Uptime</p>
          </div>
          <div className="bg-[#0d1117] rounded p-1.5">
            <p className="text-xs font-medium text-white">{camera.resolution}</p>
            <p className="text-xs text-gray-600">Res</p>
          </div>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, Wifi, WifiOff, Maximize2 } from "lucide-react";
import { useAppStore } from "@/store/useAppStore";
import { camerasApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import { LiveCameraModal } from "@/components/cameras/LiveCameraModal";
import type { CameraItem } from "@/components/cameras/CamerasManagementView";
import { startCameraStream } from "@/lib/cameraStream";
import { diagnostic } from "@/lib/diagnostics";
import { getAccessToken } from "@/lib/session";

const STATUS_STYLES: Record<string, string> = {
  online:      "text-green-400",
  offline:     "text-gray-500",
  error:       "text-red-400",
  maintenance: "text-amber-400",
};

function CameraFeed({
  camera,
  paused,
  onClick,
}: {
  camera: { id: string; name: string; location_name: string; status: string; zone_type: string; last_error?: string | null };
  paused: boolean;
  onClick: () => void;
}) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (camera.status !== "online" || paused) {
      setConnected(false);
      return;
    }

    return startCameraStream(camera.id, {
      onConnected: setConnected,
      onMessage: (msg) => {
        if (msg.type === "frame" && imgRef.current) {
          imgRef.current.src = `data:image/jpeg;base64,${msg.data}`;
        }
      },
    });
  }, [camera.id, camera.status, paused]);

  return (
    <div
      className="bg-[#0d1117] rounded-xl border border-[#2a3042] overflow-hidden group cursor-pointer"
      onClick={onClick}
    >
      <div className="relative aspect-video bg-black">
        {camera.status === "online" ? (
          // Live frames update this ref directly; Next image optimization adds latency/caching.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            ref={imgRef}
            className="w-full h-full object-cover"
            alt={camera.name}
            onError={(e) => { (e.target as HTMLImageElement).removeAttribute("src"); }}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <div className="text-center text-gray-600">
              <Camera className="w-10 h-10 mx-auto mb-2" />
              <p className="text-xs">{camera.status.toUpperCase()}</p>
              {camera.last_error && <p className="text-xs text-red-400 px-3 mt-2">{camera.last_error}</p>}
            </div>
          </div>
        )}

        {/* Fullscreen hint */}
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
          <Maximize2 className="w-8 h-8 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>

        {/* Overlay */}
        <div className="absolute top-2 left-2 flex items-center gap-1">
          <div className={cn("w-2 h-2 rounded-full", camera.status === "online" ? "bg-green-500 animate-pulse" : "bg-gray-500")} />
          <span className="text-xs text-white bg-black/60 px-1.5 py-0.5 rounded">{camera.name}</span>
        </div>

        {/* Live badge */}
        {connected && (
          <div className="absolute top-2 right-2 bg-red-600 text-white text-xs px-1.5 py-0.5 rounded font-medium">
            LIVE
          </div>
        )}

        {/* Zone type */}
        <div className="absolute bottom-2 left-2">
          <span className="text-xs bg-blue-900/70 text-blue-300 px-1.5 py-0.5 rounded capitalize">
            {camera.zone_type}
          </span>
        </div>
      </div>

      <div className="px-3 py-2 flex items-center justify-between">
        <div>
          <p className="text-xs font-medium text-white">{camera.name}</p>
          <p className="text-xs text-gray-500">{camera.location_name}</p>
        </div>
        <div className={cn("flex items-center gap-1", STATUS_STYLES[camera.status])}>
          {camera.status === "online" ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
          <span className="text-xs capitalize">{camera.status}</span>
        </div>
      </div>
    </div>
  );
}

export function CameraGrid() {
  const cameras = useAppStore((s) => s.cameras);
  const setCameras = useAppStore((s) => s.setCameras);
  const camerasLoaded = useAppStore((s) => s.camerasLoaded);
  const cameraError = useAppStore((s) => s.cameraError);
  const [activeCamera, setActiveCamera] = useState<CameraItem | null>(null);

  useEffect(() => {
    let mounted = true;
    let fetching = false;
    const fetchCameras = async () => {
      if (fetching) return;
      if (!getAccessToken()) { if (mounted) useAppStore.getState().setCameraError(true); return; }
      fetching = true;
      try {
        const res = await camerasApi.list();
        if (!Array.isArray(res.data)) throw new Error("Invalid camera response");
        if (mounted) setCameras(res.data);
        diagnostic("Cameras", `Loaded ${res.data.length} cameras`);
      } catch (error) {
        if (mounted) useAppStore.getState().setCameraError(true);
        diagnostic("Cameras", `List request failed: ${error instanceof Error ? error.message : "request failed"}`);
      } finally { fetching = false; }
    };
    fetchCameras();
    const interval = setInterval(fetchCameras, 10000);
    return () => { mounted = false; clearInterval(interval); };
  }, [setCameras]);

  const openModal = (cam: typeof cameras[0]) => {
    setActiveCamera({
      ...cam,
      rtsp_url: "",
      is_active: cam.status === "online",
      is_recording: cam.is_recording,
      resolution: "HD",
      fps: 0,
    } as CameraItem);
  };

  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Camera className="w-4 h-4 text-blue-400" />
          <h3 className="text-sm font-medium text-white">Live Cameras</h3>
          <span className="text-xs text-gray-500">
            {camerasLoaded ? `${cameras.filter((c) => c.status === "online").length}/${cameras.length} online` : "Loading cameras"}
          </span>
        </div>
      </div>

      {cameraError && <p role="status" className="text-xs text-amber-400 mb-2">Camera updates unavailable; retaining last loaded cameras</p>}
      {cameras.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-40 text-gray-500">
          <Camera className="w-10 h-10 mb-2" />
          <p className="text-sm">{!camerasLoaded ? cameraError ? "Cameras unavailable" : "Loading cameras" : "No cameras configured"}</p>
          {camerasLoaded && <p className="text-xs mt-1">Add cameras via Settings</p>}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {cameras.slice(0, 4).map((cam) => (
            <CameraFeed key={cam.id} camera={cam} paused={activeCamera?.id === cam.id} onClick={() => openModal(cam)} />
          ))}
        </div>
      )}

      {activeCamera && (
        <LiveCameraModal camera={activeCamera} onClose={() => setActiveCamera(null)} />
      )}
    </div>
  );
}

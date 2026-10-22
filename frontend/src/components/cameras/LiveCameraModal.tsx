"use client";

import { useEffect, useRef, useState } from "react";
import { X, Users, AlertCircle, Wifi, RefreshCw } from "lucide-react";
import type { CameraItem } from "./CamerasManagementView";

import { startCameraStream } from "@/lib/cameraStream";
import { ZoneDrawerModal } from './ZoneDrawerModal';
import { CampusRulesModal } from './CampusRulesModal';

interface TrackInfo {
  track_id: number;
  class_name: string;
  duration_secs: number;
  confidence: number;
}

interface Props {
  camera: CameraItem;
  onClose: () => void;
}

export function LiveCameraModal({ camera, onClose }: Props) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [retryVersion, setRetryVersion] = useState(0);
  const [geometryMode, setGeometryMode] = useState<'zone' | 'line' | null>(null);
  const [campusRules,setCampusRules]=useState(false);

  const [connected, setConnected] = useState(false);
  const [fps, setFps] = useState(0);
  const [personCount, setPersonCount] = useState(0);
  const [tracks, setTracks] = useState<TrackInfo[]>([]);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);

  const frameCounter = useRef(0);
  const lastFpsCheck = useRef(Date.now());

  useEffect(() => {
    if (camera.status !== "online") { setError("Camera is offline"); return; }

    setError("");
    setRetrying(false);

    return startCameraStream(camera.id, {
      onConnected: (value) => {
        setConnected(value);
        if (value) { setError(""); setRetrying(false); }
      },
      onRetry: (attempt) => {
        setRetrying(true);
        setError(`Connection lost — retrying in 3s (${attempt}/5)`);
      },
      onError: (message) => {
        setError(message);
        setRetrying(false);
      },
      onMessage: (msg) => {
        if (msg.type === "frame" && imgRef.current) {
          imgRef.current.src = `data:image/jpeg;base64,${msg.data}`;
          frameCounter.current++;

          const now = Date.now();
          const elapsed = (now - lastFpsCheck.current) / 1000;
          if (elapsed >= 1) {
            setFps(Math.round(frameCounter.current / elapsed));
            frameCounter.current = 0;
            lastFpsCheck.current = now;
          }
        }
        if (msg.tracks) {
          setPersonCount(Number(msg.person_count) || 0);
          setTracks((msg.tracks as TrackInfo[]).filter((t) => t.class_name === "person").slice(0, 10));
        }
      },
    });
  }, [camera.id, camera.status, retryVersion]);

  const manualRetry = () => setRetryVersion((value) => value + 1);

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      {geometryMode && <ZoneDrawerModal camera={camera} initialMode={geometryMode} onClose={() => setGeometryMode(null)} />}
      {campusRules && <CampusRulesModal camera={camera} onClose={()=>setCampusRules(false)} />}
      <div className="bg-[#1a1f2e] border border-[#2a3042] rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-3 border-b border-[#2a3042]">
          <div className="flex items-center gap-3">
            <div className={`w-2 h-2 rounded-full ${connected ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
            <span className="text-sm font-semibold text-white">{camera.name}</span>
            <span className="text-xs text-gray-500">{camera.location_name}</span>
            {connected && (
              <span className="text-xs bg-red-600 text-white px-1.5 py-0.5 rounded font-medium">LIVE</span>
            )}
          </div>
          <div className="flex items-center gap-4">
            <button className="text-xs text-blue-300" onClick={()=>setCampusRules(true)}>Campus Rules / Exit Zones</button>
            <button className="text-xs text-blue-300" onClick={() => setGeometryMode('zone')}>Draw Restricted Zone</button>
            <button className="text-xs text-blue-300" onClick={() => setGeometryMode('line')}>Draw Counting Line</button>
            <div className="flex items-center gap-3 text-xs text-gray-400">
              <span className="flex items-center gap-1"><Users className="w-3 h-3" /> {personCount}</span>
              <span className="flex items-center gap-1"><Wifi className="w-3 h-3" /> {fps} FPS</span>
            </div>
            <button onClick={onClose} className="text-gray-500 hover:text-white">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Feed + sidebar */}
        <div className="flex flex-1 overflow-hidden">
          {/* Video */}
          <div className="flex-1 bg-black relative">
            {error ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-500 gap-3">
                {retrying
                  ? <RefreshCw className="w-10 h-10 text-yellow-500 animate-spin" />
                  : <AlertCircle className="w-10 h-10 text-red-500" />}
                <p className="text-sm text-center px-4">{error}</p>
                {!retrying && (
                  <button
                    onClick={manualRetry}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded-lg"
                  >
                    <RefreshCw className="w-3 h-3" /> Retry
                  </button>
                )}
              </div>
            ) : (
              // Live WebSocket JPEGs update this ref; keep the direct image path uncached.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                ref={imgRef}
                className="w-full h-full object-contain"
                alt={`Live feed: ${camera.name}`}
              />
            )}
            {/* Corner info */}
            <div className="absolute bottom-3 left-3 text-xs text-white/70">
              {camera.resolution} · {camera.fps} FPS source
            </div>
          </div>

          {/* Track sidebar */}
          <div className="w-56 bg-[#0d1117] border-l border-[#2a3042] p-3 overflow-y-auto flex-shrink-0">
            <p className="text-xs font-medium text-gray-400 mb-2 flex items-center gap-1">
              <Users className="w-3 h-3" /> Tracked ({tracks.length})
            </p>
            {tracks.length === 0 ? (
              <p className="text-xs text-gray-600 text-center mt-8">No persons tracked</p>
            ) : (
              <div className="space-y-2">
                {tracks.map((t) => (
                  <div key={t.track_id} className="bg-[#1a1f2e] rounded-lg p-2 border border-[#2a3042]">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-white">#{t.track_id}</span>
                      <span className="text-xs text-gray-500">{t.confidence.toFixed(2)}</span>
                    </div>
                    <div className="text-xs text-gray-500">
                      {t.duration_secs >= 60
                        ? `${Math.floor(t.duration_secs / 60)}m ${Math.floor(t.duration_secs % 60)}s`
                        : `${Math.floor(t.duration_secs)}s`}
                    </div>
                    {t.duration_secs > 180 && (
                      <span className="text-xs text-amber-400 mt-1 block">⚠ Long stay</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

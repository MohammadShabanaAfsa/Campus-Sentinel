"use client";

import { useEffect, useRef, useState } from "react";
import { CAMPUS_CENTER, CAMPUS_ZOOM, cameraPosition } from "@/lib/campus";
import { addCampusMarker } from "@/lib/campusMarker";
import { useAppStore } from "@/store/useAppStore";
import { Layers, MapPin, Thermometer, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

type Layer = "cameras" | "heatmap" | "incidents";

export function CampusMapEnhanced() {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<unknown>(null);
  const heatLayerRef = useRef<unknown>(null);
  const markersRef = useRef<unknown[]>([]);
  const incidentMarkersRef = useRef<unknown[]>([]);
  const cameras = useAppStore((s) => s.cameras);
  const [activeLayers, setActiveLayers] = useState<Set<Layer>>(new Set<Layer>(["cameras", "heatmap"]));  const [heatHours, setHeatHours] = useState(6);
  const [loading, setLoading] = useState(false);

  const toggleLayer = (layer: Layer) => {
    setActiveLayers(prev => {
      const next = new Set(prev);
      next.has(layer) ? next.delete(layer) : next.add(layer);
      return next;
    });
  };

  // Init Leaflet map
  useEffect(() => {
    if (typeof window === "undefined" || mapInstanceRef.current) return;
    const L = require("leaflet");
    require("leaflet/dist/leaflet.css");

    // Guard against StrictMode double-invoke
    if ((mapRef.current as HTMLElement & { _leaflet_id?: number })?._leaflet_id) return;

    const map = L.map(mapRef.current!, {
      center: CAMPUS_CENTER,
      zoom: CAMPUS_ZOOM,
      zoomControl: true,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(map);

    addCampusMarker(L, map);
    mapInstanceRef.current = map;
    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Camera markers
  useEffect(() => {
    if (!mapInstanceRef.current) return;
    const L = require("leaflet");
    const map = mapInstanceRef.current as import("leaflet").Map;

    // Remove old markers
    markersRef.current.forEach((m: unknown) => (m as import("leaflet").Marker).remove());
    markersRef.current = [];

    if (!activeLayers.has("cameras")) return;

    cameras.forEach(cam => {
      const position = cameraPosition(cam);
      if (!position) return;
      const statusColor = cam.status === "online" ? "#22c55e" : "#6b7280";
      const icon = L.divIcon({
        html: `<div style="width:28px;height:28px;border-radius:50%;background:${statusColor};border:3px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center;">
          <svg width="12" height="12" fill="white" viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"/></svg>
        </div>`,
        className: "",
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      });

      const marker = L.marker(position, { icon, title: cam.name })
        .bindPopup(`
          <div style="font-family:sans-serif;min-width:180px;">
            <strong style="color:#1e40af;">${cam.name}</strong><br/>
            <span style="color:#6b7280;font-size:12px;">${cam.location_name ?? ""}</span><br/>
            <div style="margin-top:6px;display:flex;align-items:center;gap:6px;">
              <span style="background:${statusColor};color:white;padding:2px 8px;border-radius:12px;font-size:11px;">${cam.status}</span>
              <span style="font-size:11px;color:#6b7280;">${cam.zone_type ?? "general"}</span>
            </div>
          </div>
        `)
        .addTo(map);

      markersRef.current.push(marker);
    });
  }, [cameras, activeLayers]);

  // Heatmap layer
  useEffect(() => {
    if (!mapInstanceRef.current) return;
    const map = mapInstanceRef.current as import("leaflet").Map;

    if (heatLayerRef.current) {
      (heatLayerRef.current as { remove: () => void }).remove();
      heatLayerRef.current = null;
    }

    if (!activeLayers.has("heatmap")) return;

    const loadHeat = async () => {
      setLoading(true);
      try {
        const token = localStorage.getItem("access_token");
        const res = await fetch(`/api/v1/heatmap/detections?hours=${heatHours}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await res.json();
        if (!data.points?.length) return;

        // Dynamically load leaflet.heat
        const L = require("leaflet");
        if (!(L as Record<string, unknown>).heatLayer) {
          await import("leaflet.heat" as string);
        }

        const heat = (L as Record<string, (...args: unknown[]) => unknown>).heatLayer(data.points, {
          radius: 25,
          blur: 15,
          maxZoom: 17,
          max: 1.0,
          gradient: { 0.0: "#22c55e", 0.3: "#f59e0b", 0.6: "#ef4444", 1.0: "#7c3aed" },
        }) as { addTo: (map: unknown) => unknown };
        heat.addTo(map);
        heatLayerRef.current = heat;
      } catch (e) {
        console.warn("Heatmap load failed:", e);
      } finally {
        setLoading(false);
      }
    };

    loadHeat();
  }, [activeLayers, heatHours]);

  // Incident markers
  useEffect(() => {
    if (!mapInstanceRef.current) return;
    const L = require("leaflet");
    const map = mapInstanceRef.current as import("leaflet").Map;

    incidentMarkersRef.current.forEach((m: unknown) => (m as import("leaflet").Marker).remove());
    incidentMarkersRef.current = [];

    if (!activeLayers.has("incidents")) return;

    const loadIncidents = async () => {
      try {
        const token = localStorage.getItem("access_token");
        const res = await fetch("/api/v1/incidents/?status=open", {
          headers: { Authorization: `Bearer ${token}` },
        });
        const incidents = await res.json();
        if (!Array.isArray(incidents)) return;

        incidents.forEach((inc: Record<string, unknown>) => {
          if (!inc.latitude || !inc.longitude) return;
          const icon = L.divIcon({
            html: `<div style="width:24px;height:24px;background:#ef4444;border:2px solid white;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:12px;">⚠</div>`,
            className: "",
            iconSize: [24, 24],
            iconAnchor: [12, 12],
          });
          const m = L.marker([inc.latitude, inc.longitude], { icon })
            .bindPopup(`<strong>${inc.title}</strong><br/>${inc.incident_type}`)
            .addTo(map);
          incidentMarkersRef.current.push(m);
        });
      } catch {
        // silently ignore
      }
    };
    loadIncidents();
  }, [activeLayers]);

  return (
    <div className="relative h-full rounded-xl overflow-hidden border border-[#2a3042]">
      {/* Map container */}
      <div ref={mapRef} className="w-full h-full" />

      {/* Layer controls */}
      <div className="absolute top-3 right-3 z-[1000] bg-[#1a1f2e]/95 backdrop-blur border border-[#2a3042] rounded-xl p-3 space-y-2 shadow-xl">
        <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
          <Layers className="w-3 h-3" /> <span>Layers</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-amber-400 px-2">
          <span className="w-2 h-2 rounded-sm bg-amber-500" /> Campus
        </div>
        {([
          { id: "cameras" as Layer, label: "Cameras", icon: MapPin, color: "text-green-400" },
          { id: "heatmap" as Layer, label: "Heatmap", icon: Thermometer, color: "text-red-400" },
          { id: "incidents" as Layer, label: "Incidents", icon: AlertTriangle, color: "text-amber-400" },
        ]).map(({ id, label, icon: Icon, color }) => (
          <button
            key={id}
            onClick={() => toggleLayer(id)}
            className={cn(
              "flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs w-full transition-colors",
              activeLayers.has(id) ? `bg-white/10 ${color}` : "text-gray-500 hover:text-gray-300"
            )}
          >
            <div className={cn("w-2 h-2 rounded-full", activeLayers.has(id) ? "bg-current" : "bg-gray-600")} />
            <Icon className="w-3 h-3" />
            {label}
          </button>
        ))}

        {activeLayers.has("heatmap") && (
          <div className="pt-2 border-t border-[#2a3042]">
            <p className="text-xs text-gray-500 mb-1">Heat window</p>
            <select
              value={heatHours}
              onChange={e => setHeatHours(Number(e.target.value))}
              className="w-full bg-[#0d1117] border border-[#2a3042] rounded text-xs text-gray-300 px-2 py-1"
            >
              {[1, 6, 12, 24, 48].map(h => <option key={h} value={h}>{h}h</option>)}
            </select>
          </div>
        )}
      </div>

      {/* Loading indicator */}
      {loading && (
        <div className="absolute bottom-3 right-3 z-[1000] bg-[#1a1f2e]/90 border border-[#2a3042] rounded-lg px-3 py-1.5 text-xs text-gray-400 flex items-center gap-2">
          <div className="w-3 h-3 border border-blue-400 border-t-transparent rounded-full animate-spin" />
          Loading heatmap...
        </div>
      )}

      {/* Legend */}
      {activeLayers.has("heatmap") && (
        <div className="absolute bottom-3 left-3 z-[1000] bg-[#1a1f2e]/90 border border-[#2a3042] rounded-xl p-3 text-xs">
          <p className="text-gray-400 mb-2">Detection Density</p>
          <div className="flex items-center gap-1">
            <div className="w-20 h-2 rounded-full" style={{ background: "linear-gradient(to right, #22c55e, #f59e0b, #ef4444, #7c3aed)" }} />
          </div>
          <div className="flex justify-between mt-1 text-gray-600">
            <span>Low</span><span>High</span>
          </div>
        </div>
      )}
    </div>
  );
}


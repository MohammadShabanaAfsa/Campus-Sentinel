"use client";

import { useEffect, useRef, useState } from "react";
import { Map as MapIcon } from "lucide-react";
import { CAMPUS_CENTER, CAMPUS_ZOOM, cameraPosition } from "@/lib/campus";
import { addCampusMarker } from "@/lib/campusMarker";
import { useAppStore } from "@/store/useAppStore";
import "leaflet/dist/leaflet.css";
export function CampusMap() {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<unknown>(null);
  const [mapReady, setMapReady] = useState(false);
  const markersLayer = useRef<unknown>(null);
  // Atomic selector: only re-render (and only re-run the marker effect) when
  // the cameras array reference actually changes — bare useAppStore() would
  // re-render this on every alert/CSI/classroom update too, and `alerts`
  // isn't even used in this component.
  const cameras = useAppStore((s) => s.cameras);

  useEffect(() => {
    if (typeof window === "undefined") return;

    let destroyed = false;

    const initMap = async () => {
      const L = (await import("leaflet")).default;

      if (!mapRef.current || destroyed) return;

      // Guard against StrictMode double-invoke: container already has a map
      if ((mapRef.current as HTMLElement & { _leaflet_id?: number })._leaflet_id) return;

      const map = L.map(mapRef.current, {
        center: CAMPUS_CENTER,
        zoom: CAMPUS_ZOOM,
        zoomControl: false,
      });

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap contributors",
      }).addTo(map);

      addCampusMarker(L, map);

      if (!destroyed) {
        mapInstance.current = map;
        setMapReady(true);
      } else {
        map.remove();
      }
    };

    initMap();

    return () => {
      destroyed = true;
      if (mapInstance.current) {
        (mapInstance.current as { remove: () => void }).remove();
        mapInstance.current = null;
        markersLayer.current = null;
      }
    };
  }, []);

  // Add camera markers when cameras load. `cameras` gets a brand-new array
  // reference every ~10s poll cycle in CameraGrid even when the underlying
  // data hasn't changed, which re-runs this effect — so it must replace the
  // marker set each time, not append to it. The previous version called
  // L.marker(...).addTo(map) without ever clearing prior markers, silently
  // stacking a full duplicate set of markers on every poll forever.
  useEffect(() => {
    if (!mapInstance.current || typeof window === "undefined") return;
    const addMarkers = async () => {
      const L = (await import("leaflet")).default;
      if (!mapInstance.current) return;
      const map = mapInstance.current as ReturnType<typeof L.map>;

      if (!markersLayer.current) {
        markersLayer.current = L.layerGroup().addTo(map);
      }
      const layer = markersLayer.current as ReturnType<typeof L.layerGroup>;
      layer.clearLayers();

      cameras.forEach((cam) => {
        const position = cameraPosition(cam);
        if (!position) return;
        const color = cam.status === "online" ? "#22c55e" : "#6b7280";
        const icon = L.divIcon({
          html: `<div style="background:${color};width:12px;height:12px;border-radius:50%;border:2px solid white;box-shadow:0 0 6px ${color}"></div>`,
          className: "",
          iconSize: [12, 12],
        });
        L.marker(position, { icon, title: cam.name })
          .addTo(layer)
          .bindPopup(`<b>${cam.name}</b><br/>${cam.location_name}<br/>Status: ${cam.status}`);
      });
    };
    addMarkers();
  }, [cameras, mapReady]);

  return (
    <div className="bg-[#1a1f2e] rounded-xl border border-[#2a3042] overflow-hidden flex flex-col h-full">
      <div className="flex items-center gap-2 p-3 border-b border-[#2a3042]">
        <MapIcon className="w-4 h-4 text-blue-400" />
        <h3 className="text-sm font-medium text-white">Campus Map</h3>
        <div className="ml-auto flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 bg-amber-500 rounded-sm" /> Campus
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 bg-green-500 rounded-full" /> Online
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 bg-gray-500 rounded-full" /> Offline
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 bg-red-500 rounded-full" /> Alert
          </span>
        </div>
      </div>
      <div ref={mapRef} className="flex-1 min-h-[280px]" />
    </div>
  );
}

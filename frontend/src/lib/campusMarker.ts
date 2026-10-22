import { CAMPUS_CENTER, CAMPUS_NAME } from "@/lib/campus";

export function addCampusMarker(L: typeof import("leaflet"), map: import("leaflet").Map) {
  const icon = L.divIcon({
    // The stem ends at the geographic anchor; the building sits above it so
    // the green entrance-camera marker at the same point stays visible.
    html: `<div data-campus-marker="true" style="width:28px;height:40px;">
      <div style="width:28px;height:28px;border-radius:6px;background:#f59e0b;border:2px solid white;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 5px #0006;">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#111827" stroke-width="2" aria-hidden="true"><path d="M3 10l9-7 9 7M5 10v11h14V10M9 21v-6h6v6M9 10h.01M15 10h.01"/></svg>
      </div><div style="width:2px;height:12px;background:#f59e0b;margin:auto;"></div>
    </div>`,
    className: "campus-marker",
    iconSize: [28, 40],
    iconAnchor: [14, 40],
    popupAnchor: [0, -40],
  });
  return L.marker(CAMPUS_CENTER, { icon, title: CAMPUS_NAME, zIndexOffset: 500 })
    .addTo(map).bindPopup(CAMPUS_NAME).bindTooltip(CAMPUS_NAME, { direction: "top" });
}

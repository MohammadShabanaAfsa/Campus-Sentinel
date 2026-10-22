# Campus marker alignment

The blue dot was a separate Leaflet campus circle marker. It was not browser geolocation or a camera feed. It used `CAMPUS_CENTER`, whose public environment variables and default values came from an earlier map-embed viewport. That point differed from the database-backed green General Entrance camera marker by roughly one kilometre.

The green marker comes from `Camera.latitude`/`Camera.longitude` in PostgreSQL, returned by `GET /api/v1/cameras/` and stored in the frontend camera state. Its exact existing coordinates are **17.3545464, 78.5934475**. The user identified this marker as correct, so those values were copied into the canonical campus configuration without guessing or changing camera records. Classroom retains its separate existing position **17.3547, 78.5936**.

The canonical campus reference is `frontend/src/lib/campus.ts`, reading `NEXT_PUBLIC_CAMPUS_LAT`, `NEXT_PUBLIC_CAMPUS_LNG`, and `NEXT_PUBLIC_CAMPUS_ZOOM`. Root `.env`, `.env.example`, and `backend/.env` now agree on **17.3545464 / 78.5934475 / 18**. All other environment values remain unchanged. Native Next builds read the root public variables; existing Docker build arguments pass the same public variables. Both map initial centers and the campus marker use this shared reference. Individual camera positions still come from their records.

The unexplained blue dot was replaced with an amber building icon, with a Campus legend, tooltip, and popup **Sreyas Institute of Engineering and Technology**. Its stem ends at the same geographic point as the green entrance marker; the building is drawn above that point so the camera remains visible. Green indicates online cameras, gray indicates offline/error cameras, and red incident markers remain intact. Camera markers with missing or invalid coordinates are hidden with one warning per camera, rather than placed at a fallback location.

No frontend browser geolocation or `setView`/`flyTo`/`fitBounds` override was found. None is enabled. A direct visit to `/map` now also loads the existing camera API independently and refreshes its records, since that route does not mount the dashboard camera loader. Temporary request failures retain existing markers.

Stale generic Hyderabad coordinate examples were found in the Add Camera form and deployment example. The form now displays placeholders from the shared campus reference without silently filling missing coordinates, and the deployment example uses the confirmed entrance point. The earlier map report was updated. Historical descriptions of the original generic center remain only as documentation of the previous issue; no old map coordinate pair remains in frontend runtime code.

Validation passed:

- `npm test`: **19 tests passed**.
- `npm run lint`: passed with existing unrelated warnings.
- `npm run type-check`: passed.
- `npm run build`: passed, including final lint/type validation.
- `backend/.venv/Scripts/python.exe scripts/verify_campus_map.py`: passed against the rebuilt production frontend in Edge.

The browser check verified both `/dashboard` and `/map`: loaded OpenStreetMap tiles, zoom 18, campus/entrance anchors exactly aligned at the map center, correct campus popup, both camera markers, no blue dot, no geolocation calls, and no center/marker movement across a real camera refresh cycle. Camera layer toggles preserved the separate campus marker; the incident layer still enabled normally. Before/after database reads confirmed that camera records and coordinates were unchanged. Screenshots are saved under `logs/campus-map-{dashboard,map}-verified.png`.

Files changed:

- `.env`, `.env.example`, `backend/.env` (campus coordinates only).
- `frontend/src/lib/campus.ts`, new `frontend/src/lib/campusMarker.ts`.
- `frontend/src/components/map/CampusMap.tsx`, `CampusMapEnhanced.tsx`.
- `frontend/src/app/map/page.tsx`.
- `frontend/src/components/cameras/AddCameraModal.tsx`.
- `frontend/tests/csi.test.cjs`.
- New `scripts/verify_campus_map.py`.
- `docs/DEPLOYMENT.md`, `docs/CAMPUS_MAP_AND_CSI.md`, this report.

General Entrance is online. Classroom was already in error and the configured phone URL refused connections before any map changes. Its camera marker, coordinates, source URL, capture/reconnect implementation, and cards were preserved. The phone server must be reachable for that feed to become live again; the map correction does not change the camera source or restart the backend.

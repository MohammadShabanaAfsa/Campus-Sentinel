# Campus location and dynamic safety index

Both map components use Leaflet. They previously opened at the hardcoded central Hyderabad coordinates `17.385, 78.4867`, zoom 16. Both now read the shared campus configuration and add a permanent campus marker named **Sreyas Institute of Engineering and Technology**. No camera, incident, or heatmap layer changes the initial view.

The campus center is now `17.3545464, 78.5934475`, zoom 18, copied exactly from the existing General Entrance camera record, which the user confirmed is the correct green marker. The earlier map-embed viewport coordinates differed from that camera location and have been replaced. The environment keys are `NEXT_PUBLIC_CAMPUS_LAT`, `NEXT_PUBLIC_CAMPUS_LNG`, and `NEXT_PUBLIC_CAMPUS_ZOOM`. Next loads these public keys from the project `.env` for native builds; Docker supplies them as build arguments. Public environment changes require rebuilding Next. The separate campus marker is a labeled amber building icon at the same geographic point as the entrance camera; both camera records keep their original coordinates.

The old dashboard read the first historical per-camera row from `/api/v1/csi/latest`. The database contained a **69.5 / moderate** row dated August 6, 2026, which rendered as 70, with zero anomaly and historical component scores. The old periodic calculation read Redis behavior metrics and included a placeholder historical value. Alert and incident mutations did not recalculate it. The events endpoint also used a different connection manager from the Redis broadcaster.

`backend/app/services/safety_index.py` is now the canonical calculation for the live campus API, scheduled snapshots, and mutation broadcasts. It reads database alerts and incidents from the preceding 24 hours. Each record is counted once; manually created incidents and alerts are separate records because the schema has no link identifying duplicates.

```
penalty = severity_penalty * max(0, 1 - age_hours / 24) * status_factor
CSI = clamp(round(100 - sum(penalties)), 0, 100)
```

Severity penalties are low 2, medium 5, high 10, and critical 20. Resolved/closed/dismissed records have status factor 0.25; other statuses, including acknowledged, have factor 1. Unknown legacy severities are logged and conservatively use medium. No recent events produces 100. Future timestamps are capped at zero age.

| Score | Level |
|---|---|
| 90–100 | SAFE |
| 75–89 | LOW RISK |
| 60–74 | MODERATE |
| 40–59 | HIGH RISK |
| 0–39 | CRITICAL |

Crowd, loitering, access, and anomaly are category safety scores using the same event penalties. A category with no matching events scores 100. `anomaly_count` is a separate count of matching recent records. Other incident types still affect overall CSI even when these four category scores are 100.

The authenticated live endpoint is **GET `/api/v1/csi/campus`**. Creation, updates, resolution, and deletion publish a complete `csi_update` snapshot on Redis **`csi_updates`**, delivered by the existing **`/api/v1/ws/events`** WebSocket and shared connection manager. Automated alert creation and periodic snapshots use the same service. The frontend's existing realtime hook also fetches every five seconds for time decay, reconnects, missed broadcasts, and temporary Redis failures. The header and gauge consume the same Zustand object, accept zero scores, reject malformed/stale snapshots, and retain the last valid value on failure. Before the first successful response they show loading or unavailable. History and per-camera API routes remain available.

Changed files:

- Configuration/startup: `.env`, `.env.example`, `backend/.env`, `.gitignore`, `run`, `docker-compose.yml`, `frontend/Dockerfile`, `frontend/next.config.js`, `frontend/package.json`, `frontend/.eslintrc.json`, `backend/requirements-dev.txt`.
- Backend: `app/services/safety_index.py`, `app/services/tasks/analytics_tasks.py`, `app/services/tasks/alert_tasks.py`, `app/services/websocket_manager.py`, `app/api/v1/endpoints/{csi,alerts,incidents,websocket}.py`, `app/schemas/alert.py`, `tests/unit/test_csi.py` (paths relative to `backend`).
- Frontend: `src/lib/{campus,csi,api}.ts`, `src/store/useAppStore.ts`, `src/hooks/useRealtimeEvents.ts`, `src/components/dashboard/{Header,CSIGauge}.tsx`, `src/components/map/{CampusMap,CampusMapEnhanced}.tsx`, `tests/csi.test.cjs`.
- Lint compatibility: escaped existing JSX text in `frontend/src/components/alerts/ExplanationPanel.tsx` and `frontend/src/components/classroom/ClassroomOverviewGrid.tsx`.
- Supporting artifacts: `scripts/verify_campus_safety.py`, this report, and the CSI reference in `ai-engine/classroom/attention_index.py`'s docstring.
- Camera recovery from the earlier camera fix: `ai-engine/vision/stream_manager.py`, `backend/app/api/v1/endpoints/cameras.py`, and `backend/tests/unit/test_stream_recovery.py`.

Validation commands:

```
cd backend
.venv/Scripts/python.exe -m pytest tests/unit/test_csi.py tests/unit/test_stream_recovery.py -q
cd ../frontend
npm test
npm run lint
npm run type-check
npm run build
cd ..
backend/.venv/Scripts/python.exe scripts/verify_campus_safety.py
```

The smoke check uses existing database events and an existing active local account. It inserts no test incidents or alerts, verifies authenticated API/Redis/WebSocket delivery, checks the production dashboard and frontend API proxy, and checks active cameras for fresh frames. The Android IP Webcam source remains `http://172.28.170.74:8080/video`, and General Entrance retains its local webcam source.

Validation results on October 2, 2026:

- Backend: 40 tests passed across CSI and stream recovery.
- Frontend: 7 tests passed; lint and TypeScript checks passed. Existing hook/image lint warnings and Pydantic warnings remain.
- Production build completed through the project's launcher; the frontend is serving on port 3000. The generated dashboard/camera bundles contain the Sreyas coordinates, and authenticated dashboard/proxy requests return HTTP 200.
- Live smoke check passed: canonical CSI API, full Redis-to-WebSocket snapshot, and fresh frames from both Classroom and General Entrance.
- The current score is 0 / CRITICAL from actual recent database events. It may remain zero while total decayed penalties exceed 100; resolving or removing sufficient events raises it according to the formula.
- The restored Celery worker is receiving and processing the existing camera analysis queue.
- `bash -n run` passed.

There are no remaining blockers for these map, CSI, and camera fixes. Existing email logs show mock delivery and an invalid `SMTP_FROM` address (`alerts@localhost`); real email delivery requires valid SMTP configuration. This is separate from dashboard alerts and CSI updates. Android IP Webcam must remain running at its configured address for the live phone feed.

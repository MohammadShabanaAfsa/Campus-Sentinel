# Startup cleanup and Classroom source update

Verified on 2026-10-12 using native Windows Python, Git Bash `./run`, Docker
Compose, and the existing production Next.js server.

## Warning fixes

| Warning | Cause | Fix |
| --- | --- | --- |
| incidents effect missing `load` | Function recreated on render; effect depended only on its captured status | Memoize load with useCallback([status]); effect depends on load |
| AlertPanel missing `addAlert` | Effect omitted captured Zustand action | Include stable addAlert action dependency; no additional subscription |
| ThreatPredictions missing `setPredictions` | Polling effect omitted captured Zustand action | Include stable action; keep existing interval cleanup |
| ZoneDrawerModal missing `drawAll` | Redraw function captured polygon state and was called from snapshot request callback | Memoize drawing with zones/currentPoints; drawing effect depends on callback and background-loaded state; snapshot request remains dependent only on camera.id |
| camera `<img>` warnings | Next lint favors optimized static images | Keep ref-updated live JPEG images; two element-local rule exceptions explain why optimization/caching is inappropriate |
| Compose version obsolete | Modern Compose ignores top-level version | Remove only version field |
| Pydantic class-based configuration deprecation | Settings still used legacy Config class | Use equivalent SettingsConfigDict with unchanged env_file/case_sensitive/extra options |
| Prediction model_version namespace warning | Pydantic's broad model_ prefix conflicts with legitimate existing response field | Protect actual model_validate/model_dump names while preserving model_version and response serialization |

No global ESLint or warning suppression was added. MediaPipe/TFLite feedback
messages, protobuf GetPrototype deprecation and Celery's future startup-retry
deprecation remain visible. Resolving those entails library/model/configuration
changes outside the requested warning fixes; they were not hidden or upgraded.

## Classroom record

- Existing ID: `6cf7815f-009b-48e6-bf71-a7548a5e75b0`.
- Old PostgreSQL `rtsp_url`: `http://172.28.170.74:8080/video`.
- New PostgreSQL `rtsp_url`: `http://192.168.1.10:8080/video`.
- Initial native requests test: HTTP 200, multipart MJPEG, 8192 bytes received.
- Initial native OpenCV test: opened=true, frame_received=true, 1920x1080 frame.
- Updated only rtsp_url on the existing record. Camera ID/configuration/history
  and related records were preserved; two cameras total, one named Classroom.
- `POST /api/v1/streams/{id}/restart` returned HTTP 200, status=restarting.
  Classroom was producing live detector/MediaPipe/QR processing logs afterward.
- Root `.env`, `backend/.env`, `.env.example` seed values were updated too.

After the requested full `./run` startup verification, the phone ceased responding.
A separate fresh native request failed with ConnectTimeout: connection to
192.168.1.10 timed out (connect timeout=3). The backend reports the same source
unreachable timeout and remains reconnecting. The successful initial checks do
not imply the phone stayed online. Its correctly saved new URL was retained.

## Production build reuse

The former run check tested BUILD_ID and whether selected input timestamps were
newer. Its message meant no usable/current build was found, not an application
error. It could miss deleted sources or changes in inputs outside that list.

A successful `npm run build` now records a SHA-256 fingerprint of source/public
files, package lock, relevant configuration/env files and build-time public env
values. `./run` checks required production manifests and that fingerprint. Changed,
added or deleted inputs invalidate the build. Legacy builds without a marker are
rebuilt once. Messages now distinguish missing/stale rebuilding and safe reuse.
The server remains `next start`, never next dev.

Verified build directory: `frontend/.next-startup-cleanup` via NEXT_BUILD_DIR.
`./run` reused that valid build and logs show `next start`, Ready in 930ms. The
default .next remains supported; it will rebuild if its fingerprint is absent or
stale. Next automatically included this build directory's generated TypeScript
types in tsconfig.json.

## Final checks

- `docker compose config --quiet`: valid, no obsolete version warning.
- `npm run lint`: no ESLint warnings or errors.
- `npm run type-check`: passed.
- `npm run build`: compiled, checked types/lint, generated all 14 pages, completed.
- `npm test`: 23 passed, including build invalidation/reuse coverage.
- Relevant backend suite: 77 passed, no warnings after Pydantic cleanup.
- Git Bash syntax check and actual `./run`: passed; Redis/PostgreSQL healthy,
  Celery ready, backend healthy, frontend responding in production mode.
- General Entrance: running, 2.08 processed FPS, fresh frame, valid 640x480
  WebSocket JPEG and two person tracks in the sample; no source change.
- Classroom: saved new URL, reconnecting after subsequent phone timeout.
- QR/activity regression suites pass; live tracks/JPEG publication works. No QR
  identity was decoded in the final sample and no positive activity was invented.

## Changed files

- `frontend/src/app/incidents/page.tsx`
- `frontend/src/components/alerts/AlertPanel.tsx`
- `frontend/src/components/cameras/ZoneDrawerModal.tsx`
- `frontend/src/components/dashboard/ThreatPredictions.tsx`
- `frontend/src/components/cameras/CameraGrid.tsx`
- `frontend/src/components/cameras/LiveCameraModal.tsx`
- `frontend/package.json`
- `frontend/scripts/production-build-state.cjs`
- `frontend/tests/production-build-state.test.cjs`
- `frontend/tsconfig.json` (Next-generated type include)
- `docker-compose.yml`
- `run`
- `.env`, `backend/.env`, `.env.example`
- `backend/app/core/config.py`
- `backend/app/schemas/prediction.py`
- `docs/STARTUP_WARNING_CLEANUP.md`

Runtime verification reports/logs were regenerated. No camera detector, tracker,
QR persistence, activity thresholds, CSI rule, map, database schema or alert rule
was changed by this cleanup.

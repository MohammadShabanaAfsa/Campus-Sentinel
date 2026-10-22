# Classroom camera source fix

## Current address update — 2026-10-03

The existing Classroom row now uses `http://172.28.170.74:8080/video` in both `rtsp_url` and `stream_url`; its previous source was `http://192.0.0.5:8080/video`. Camera ID remains `6cf7815f-009b-48e6-bf71-a7548a5e75b0`. The targeted database update preserved name, location, coordinates (`17.3547, 78.5936`), zone type, configuration and related records. Only Classroom was restarted through `POST /api/v1/streams/{id}/restart`.

The first bounded native probe reported a connection timeout. The phone became reachable afterward: direct native OpenCV open/read/release testing returned `opened=true` and `frame_received=true`. Runtime verification then showed Classroom `online/running`, fresh processed frames, no last error, and General Entrance still `online/running` with continuous uptime. Authenticated Cameras page returned HTTP 200; camera API counts were **Total 2, Online 2, Error 0**. The edit dialog reads the saved URL from that API.

Files updated for this address change: `.env`, `backend/.env`, `.env.example`, `CAMPUS_SENTINEL_PROJECT_DOCUMENTATION.md`, `docs/CAMPUS_MAP_AND_CSI.md`, `docs/DASHBOARD_REGRESSION.md`, and this report. Earlier runtime observations below are historical. No detection, tracking, MediaPipe, behavioral, alert, CSI, authentication, map or infrastructure code was changed. Runtime verification details are recorded in `logs/classroom-ip-update-verification.json`.

## Earlier implementation verification

Verified on 2026-10-03 against the native FastAPI/Next.js runtime with Docker PostgreSQL and Redis.

1. **Source before the fix:** `http://192.0.0.5:8080/video`.
2. **Storage:** PostgreSQL `cameras.rtsp_url`, Classroom ID `6cf7815f-009b-48e6-bf71-a7548a5e75b0`. Capture reads this row at startup and reconnect.
3. **Why environment edits did not fix it:** `IP_CAMERA_URL` seeds Classroom only when the cameras table is empty. Existing rows are preserved and take precedence. The hardcoded default has been removed; `.env.example` now uses a blank optional seed with a format hint.
4. **Files changed:**
   - `backend/app/api/v1/endpoints/cameras.py`: authenticated source test, probe-before-save, targeted restart after commit, synchronized `stream_url`.
   - `backend/app/services/camera_probe.py`: five-second subprocess deadline around the shared capture implementation; hung probes are killed and waited for.
   - `backend/app/schemas/camera.py`: source validation, test request and error response fields.
   - `backend/app/models/camera.py`: expose the existing JSON configuration's `last_error`; no schema migration.
   - `backend/app/core/config.py`, `backend/app/main.py`, `.env.example`: optional first-time seed; existing database values remain authoritative.
   - `ai-engine/vision/camera_manager.py`: HTTP headers check, bounded FFmpeg open/read, first-frame check, concise errors and source log redaction.
   - `ai-engine/vision/stream_manager.py`: serialize restart/start, release capture in `finally`, configured reconnect delay, persist/expose camera errors.
   - `frontend/src/components/cameras/EditCameraModal.tsx`: editable name/source/location/coordinates/zone, Save, Test Connection, Restart Camera.
   - `frontend/src/components/cameras/CamerasManagementView.tsx`: gear opens editing; separate Zones button retains zone drawing; cards show error reason.
   - `frontend/src/components/cameras/CameraGrid.tsx`, `frontend/src/store/useAppStore.ts`: dashboard cards show the persisted camera error without changing backend connection state.
   - `backend/tests/unit/test_camera_settings.py`, `frontend/tests/camera-settings.test.cjs`, `frontend/tests/dashboard-recovery.test.cjs`: update/restart/error/isolation checks.
   - `scripts/verify_camera_settings.py`: native frame, transactional database and runtime verification.
   - `frontend/tsconfig.json`: Next.js generated include for the separate verification build directory.
5. **Update API:** `PATCH /api/v1/cameras/{camera_id}` with `{ "rtsp_url": "http://<PHONE_IP>:8080/video" }`. A changed network source must yield a frame before committing. A failed probe returns HTTP 422 and preserves the saved source. Successful source updates commit the same row and enqueue only its stream restart.
6. **Test/restart APIs:** `POST /api/v1/cameras/test-source` with `rtsp_url`; `POST /api/v1/streams/{camera_id}/restart`. The test returns `reachable`, `opened`, `frame_read`, and `message`. Local webcam probes are rejected to avoid reopening the active Entrance device.
7. **UI:** Cameras → Classroom gear → edit Video source → Test Connection → Save. Restart Camera targets the saved source; unsaved source changes must be saved first. Untouched coordinates and other fields are omitted from the PATCH.
8. **Database verification:** the actual update endpoint changed `rtsp_url` and `stream_url` inside a PostgreSQL transaction, preserved identity/coordinates/location/zone and other configuration keys, and queued exactly one targeted restart. The outer transaction was rolled back so a temporary local test video was never adopted by the live stream. Final saved Classroom remains `http://192.0.0.5:8080/video`, latitude `17.3547`, longitude `78.5936`. No rows were deleted or recreated; existing history and classroom configuration remain attached to the same ID.
9. **Exact current runtime error:** `Camera source unreachable: connection timed out`. Authenticated native test returned `reachable=false`, `opened=false`, `frame_read=false` in **3.89 seconds**. Live Classroom is `reconnecting`, its database status is `error`, and it retries after the configured **5 seconds**. It has no local-webcam fallback.
10. **General Entrance:** source remains `0`, ID `1a32cb23-0820-4385-9ab5-de8e472e2c04`, coordinates remain `17.3545464, 78.5934475`, and status is `online`. Its frame counter and uptime continued across the Classroom-only restart; native verification observed 58 processed frames, zero errors, and a recent frame. Backend health and authenticated production Cameras page returned HTTP 200. Backend and frontend were restarted once to load the new code; future camera-source edits require only that camera's restart. Docker and Celery were left running.
11. **Checks:**
    - Camera settings + existing stream recovery: **8 passed**.
    - Entire backend suite: **75 passed, 8 failed**. Failures concern older tests using a camera-less StreamManager, loitering timing, outdated CSI level/contribution expectations, and a missing `pytest` import in tracker tests. These unrelated implementations were left unchanged.
    - Frontend tests: **22 passed**.
    - Frontend TypeScript check: **passed**.
    - Production build: **passed**, with existing lint warnings. Verified build is served from `.next-camera-verification`.
    - Native reachable HTTP source: HTTP connection plus OpenCV frame read **passed**.
    - Actual PostgreSQL update/preservation and Classroom-only restart/Entrance isolation: **passed**.

The current phone address is unreachable. Enter the address currently shown by Android IP Webcam on a network reachable from the laptop; the implemented dialog now verifies and applies that address safely.

Re-run native verification from the repository root:

```powershell
backend/.venv/Scripts/python.exe scripts/verify_camera_settings.py --runtime
```

This verification rolls back its test database source and performs one restart of the existing Classroom stream. It does not restart Entrance.

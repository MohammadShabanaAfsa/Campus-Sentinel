# Dashboard regression repair

The reload loop was an authentication redirect cycle. Protected API requests returned **401**. The Axios interceptor removed `localStorage.access_token` and navigated the entire browser to `/login`, but left the `cs_token` cookie. Middleware treated any cookie as authenticated and redirected `/login` back to `/dashboard`. The remounted dashboard sent more unauthorized requests and repeated the cycle. The CSI polling exposed this existing session mismatch more frequently; no CSI calculation or map effect reloaded the browser. An isolated Edge session reproduced four navigations in eight seconds with an expired token. The original rejected token was already removed by the interceptor, so its expiry versus an invalid signature cannot be determined from the remaining logs.

Disconnected/Offline came from the events socket failing authentication or having no access token after the interceptor removed it. The two database cameras and managed capture workers were still present. The camera fetch failed with 401, its exception was silently swallowed, and the fresh Zustand store contained `[]`. The UI rendered that initial unknown state as **0/0 / No cameras configured**. This was not an empty successful camera response, a changed camera API schema, or deletion of camera records.

Credential expiry/rejection now clears both storage and cookie once and marks the session as requiring sign-in. It does not reload or navigate the dashboard. Middleware checks access-token structure/type/expiry before redirecting the login page; the backend still verifies signatures and authorization. Login saves both credentials through the same session helper. Late 401 responses from older sessions cannot invalidate a newer login. Failed login attempts and temporary 5xx/network errors do not log out a valid user.

API health, events WebSocket connectivity, camera-list availability, and CSI availability have separate states. A missing initial camera response displays loading/unavailable. A temporary request failure retains the previous camera list and count. The existing events socket retries after three seconds, cleans up timers and callbacks on unmount, and ignores stale callbacks. Camera preview and modal sockets use the existing backend frame route with one socket per feed, three-second retries, five consecutive failed attempts, and safe manual replacement. None of these requests opens a new OpenCV capture.

The PostgreSQL camera registry, startup seeding, managed stream workers, YOLO detection/annotation, agents, canonical CSI formula, and Sreyas map configuration remain. Per-frame YOLO diagnostic logging was removed. Development-only frontend diagnostics report transitions and request failures without logging tokens or frames.

Actual routes and configuration:

- API base: `http://localhost:8000`; health: `GET /health`.
- Cameras: `GET /api/v1/cameras/`, returning the existing array of database camera records.
- CSI: `GET /api/v1/csi/campus`.
- Events: `ws://localhost:8000/api/v1/ws/events?token=<access-token>`.
- Camera frames: `ws://localhost:8000/api/v1/ws/camera/<camera-id>/stream?token=<access-token>`.
- Phone source: `http://172.28.170.74:8080/video`. The native backend settings and resolved Compose backend environment both contain this exact value; General Entrance retains its existing webcam source.
- Public API/WebSocket/map variables are loaded from the root `.env` for native builds and supplied at Docker build time. The real `.env` values were not modified during this repair.
- Development CORS permits the frontend origin. Real Edge requests from `http://localhost:3000` passed. FastAPI is running on `0.0.0.0:8000`.

Only PostgreSQL and Redis are currently running in Docker; backend, worker, and frontend run natively. `docker compose ps` confirmed healthy infrastructure. Compose backend/frontend logs contain no running application containers, so native application logs were inspected instead. `docker compose config --format json` confirmed the backend phone URL and frontend public build URLs. An actual `docker compose exec backend printenv IP_CAMERA_URL` is unavailable while that service is not running; the resolved configuration and native backend were verified without starting a competing backend container.

Validation:

```
cd frontend
npm test
npm run lint
npm run type-check
npm run build
cd ../backend
.venv/Scripts/python.exe -m pytest tests/unit/test_csi.py tests/unit/test_stream_recovery.py -q
cd ..
backend/.venv/Scripts/python.exe scripts/verify_dashboard_browser.py --expect-regression
backend/.venv/Scripts/python.exe scripts/verify_dashboard_browser.py
backend/.venv/Scripts/python.exe scripts/verify_campus_safety.py
docker compose ps
docker compose config --format json
```

The regression reproduction ran before replacing the old production build. The repaired build passed lint/type validation and production compilation. **17 frontend tests and 41 backend tests passed.** An isolated HTTP test used actual incident routes and the canonical service to verify **100 -> 90** after high-severity incident creation and **90 -> 98** after resolution, including published snapshots. It did not change the live database. The existing scoring tests cover decay, bounds, components, and no recent events.

Real Edge verification passed: Live/Connected, 2/2 online, decoded frames for General Entrance and Classroom, and loaded CSI. Temporary CSI and camera-list 503 responses retained state and did not navigate. Forcing the events socket closed reconnected after three seconds while retaining cameras, with exactly one events socket and two camera feed sockets. Credentials rejected by the backend clear both session locations and reach a stable login page without a reload cycle. Expired cookies are also cleared by middleware. The live smoke check passed authenticated camera/CSI/proxy requests and full Redis-to-WebSocket delivery, with fresh camera heartbeats/frames. The Celery worker is processing camera analysis tasks.

The current live CSI is **0 / CRITICAL** because actual recent penalties exceed 100. No data was removed to produce a demonstration score of 100. With no recent records, the service returns 100. The Sreyas map remains at the configured campus center and zoom 18.

The final map check loaded **6/6 tiles** and found the campus and camera marker layers. Visual inspection also confirmed YOLO boxes and track IDs on the live entrance feed. The verified camera/map screenshot is saved locally at `logs/dashboard-regression-verified.png`.

Changed files in this repair:

- `frontend/src/lib/{api,session,cameraStream,diagnostics}.ts`
- `frontend/src/middleware.ts`
- `frontend/src/app/login/page.tsx`
- `frontend/src/store/useAppStore.ts`
- `frontend/src/hooks/useRealtimeEvents.ts`
- `frontend/src/components/dashboard/{Header,Sidebar}.tsx`
- `frontend/src/components/cameras/{CameraGrid,LiveCameraModal}.tsx`
- `frontend/next.config.js`, `frontend/Dockerfile`, `docker-compose.yml`
- `frontend/tests/dashboard-recovery.test.cjs`
- `ai-engine/vision/stream_manager.py` (also visible through the backend junction)
- `backend/tests/unit/test_csi.py`, `backend/requirements-dev.txt`
- `scripts/verify_dashboard_browser.py`, `scripts/verify_campus_safety.py`
- This report.

No Git history is available because this workspace has no `.git` repository. Findings were established from source, native logs, HTTP/WebSocket checks, and the browser reproduction. Existing lint/Pydantic warnings and mock SMTP configuration remain unrelated to this repair. A previously rejected/expired browser session requires signing in again; it is not reused or bypassed.

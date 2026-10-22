# Live behavior overlays

Implemented and verified on 2026-10-03.

1. **Files changed**
   - `ai-engine/vision/behavior_overlay.py`: display-only cache, supported labels, sorting and exact-track routing.
   - `ai-engine/vision/frame_annotator.py`: behavior strips above person boxes and separate camera banners; labels remain within frame boundaries.
   - `ai-engine/vision/stream_manager.py`: merge current analyzer state before drawing/encoding; enrich existing Redis track payloads.
   - `agents/behavior_agent/agent.py`: include active detector snapshots, capture timestamp and tracker-session ID in the existing behavior-state key.
   - `ai-engine/behavioral/movement.py`, `loitering.py`, `zone_checker.py`, `crowd.py`: expose current detections separately from alert cooldowns, using existing conditions and thresholds.
   - `ai-engine/classroom/classroom_monitor.py`, `attendance.py`: expose confirmed sleeping/talking and sustained camera conditions; clear per-person state for a fresh tracker.
   - `backend/tests/unit/test_behavior_overlays.py`: 23 regression tests.
   - `scripts/verify_behavior_overlays.py`: native stream/metadata/WebSocket verification and isolated rendering-cost measurement.
   - This report. No frontend code, camera sources, coordinates, database schema, CSI, incident logic, authentication, WebSocket architecture or alert dispatch code was changed.
2. **Where boxes are drawn:** OpenCV `FrameAnnotator` draws onto the backend JPEG. The existing camera WebSocket delivers that JPEG; frontend rendering is unchanged and does not draw a second set of boxes.
3. **Track association:** analyzers provide the same `track_id` as ByteTracker. Movement labels use the analyzer's detected movement subtype. Classroom labels use only confirmed `is_sleeping` / `is_talking`, not candidates. The capture thread joins snapshots to track IDs without matching box positions. Existing `camera:{id}:behavior_state` carries agent snapshots; existing `camera:{id}:tracks` adds a backward-compatible `behaviors` array to each track and a `camera_behaviors` array to the frame metadata. Tracker-session IDs reject results from older capture threads; ordinary reconnects retain the tracker session.
4. **Person labels:** RUNNING, SUDDEN ACCELERATION, ZIGZAG MOVEMENT, LOITERING, RESTRICTED ZONE, SLEEPING and TALKING. Normal persons keep their existing ID/class/confidence label. No normal/safe/student identity is invented.
5. **Camera banners only:** CROWD DENSITY, CROWD SURGE, CROWD FORMATION, LOW CLASS ATTENTION, MISSING STUDENTS and LOW FACULTY ENGAGEMENT, when their existing analyzers confirm the condition. These are never assigned to every person's box.
6. **Lifetime:** four seconds from the analyzed frame's timestamp. A newer active snapshot refreshes the label; an ended condition, vanished track or expired timestamp clears it. Re-reading the same Redis snapshot cannot extend its expiry. Delayed results older than four seconds and older tracker sessions are ignored.
7. **Multiple labels:** up to three per person and three camera banners. Order is critical → high → medium → low, then most recent detection. Labels prefer two lines above the box, falling back inside its top when necessary.
8. **Alerts:** drawing/cache code creates no alerts and does not call alert tasks. Existing thresholds, alert payloads, priority of movement alerts, and once-per-track/episode or camera cooldown gates remain intact. Active display state can persist while an existing alert is on cooldown. Per-track state starts fresh with a fresh tracker so reused numeric IDs cannot inherit another person's state; crowd cooldown remains camera-scoped. State exchange is serialized as existing Redis JSON snapshots; each display cache belongs only to its capture thread. No database lookup is added per box or frame. Redis display-state reads are limited to at most four per second per camera.
9. **Verification:**
   - **23 overlay tests passed**, covering all seven person labels, severity/recency ordering, expiry/end/disappearance/session filtering, camera-only crowd banners, real movement rules, loitering/restricted-zone cooldowns, confirmed sleeping/talking thresholds, sustained missing-student detection, unchanged alert dispatch count, frame bounds, and a controlled Classroom capture → annotation → JPEG → Redis metadata pipeline.
   - **Full backend suite: 97 passed, 9 failed.** Eight failures are the previously observed legacy expectations (camera-less StreamManager calls, inconsistent loitering fixture positions, old CSI level/contribution expectations, and a missing tracker-test import). The ninth is an existing CSI loader test whose fixed `2026-10-02 08:00 UTC` fixture aged beyond the real 24-hour window during this run. It also fails independently without importing the overlay tests. CSI code and tests were left unchanged.
   - **Frontend TypeScript check passed; 22 frontend tests passed.** The frontend implementation and its existing production build did not require changes.
   - Native Entrance track metadata and authenticated camera WebSocket JPEG decoding passed.
   - Final Entrance sample: **3.68 processed FPS**, versus **3.76** before rollout (about 2% difference in a short live sample). An earlier post-rollout sample was 3.78 FPS. These are observational samples, not a controlled detection benchmark.
   - Isolated six-person 1280×720 drawing benchmark: normal median **4.249 ms**, behavior median **4.700 ms**, additional median **0.451 ms**; cache attachment **0.035 ms**. Benchmark fixtures were never injected into live cameras, Redis, or alerts.
   - A full-disk error interrupted a later independent test rerun. About 150 MB of regenerable `.next-camera-verification/cache` was cleared; the frontend's served build files were retained, and the rerun completed.
10. **Camera status:** General Entrance is running with fresh JPEGs and no camera error. Classroom was already reconnecting in the pre-rollout baseline and still reports `Camera source unreachable: connection timed out` at its unchanged `http://172.28.170.74:8080/video` source. Its live JPEG cannot currently be verified because the phone is unreachable. The controlled Classroom pipeline test passes; the live stream will use the new overlay code when its configured source becomes reachable. No fake live behavior was inserted to demonstrate labels.

Native measurements are stored in `logs/behavior-overlay-baseline.json` and `logs/behavior-overlay-verification.json`. Updated backend logs are `logs/backend-overlays-final.out.log` and `logs/backend-overlays-final.err.log`; frontend, Celery, PostgreSQL and Redis were left running during backend code loading.

Run the native verification from the repository root:

```powershell
backend/.venv/Scripts/python.exe scripts/verify_behavior_overlays.py
```

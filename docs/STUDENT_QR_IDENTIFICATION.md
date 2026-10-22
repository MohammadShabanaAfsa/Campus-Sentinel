# Live student QR identification

Implemented and verified on 2026-10-12.

1. **Files changed:**
   - `ai-engine/identity/__init__.py` and `qr_identity.py`: cached student mapping, OpenCV QR decoding, conservative association, temporary identities.
   - `ai-engine/tracking/tracker.py`: expose the existing `time_since_update` value so stale boxes cannot acquire or retain identities. Tracking rules and IDs are unchanged.
   - `ai-engine/vision/stream_manager.py`: initialize QR state per camera capture session, scan raw frames, attach identity to existing tracks before annotation and existing Redis publication. QR failures fall back to UNKNOWN without disabling behavior analysis.
   - `ai-engine/vision/frame_annotator.py`: identity → confirmed activities → existing track/class/confidence label. Known identities must have a matching track ID and `method=qr`; otherwise display UNKNOWN.
   - `backend/app/core/config.py` and `.env.example`: configurable scan, timeout and association settings.
   - `backend/requirements.txt`: add `openpyxl==3.1.5` for workbook reading. OpenCV was already installed.
   - `backend/tests/unit/test_qr_identity.py`: 16 QR-specific tests.
   - `backend/tests/unit/test_behavior_overlays.py`: extend controlled Classroom integration test to verify QR identity and sleeping metadata on the same track through JPEG/Redis output.
   - `scripts/verify_behavior_overlays.py`: verify exact-track QR identity metadata in live streams.
   - This report. No student database tables were created, and no source workbook, QR files, photos, camera source, coordinates, alert rules, CSI, authentication, frontend or WebSocket protocol code was changed.
2. **QR library:** existing OpenCV `QRCodeDetector`, multi-code decoding plus single-code fallback. The fallback is needed because the multi-code path can miss otherwise readable single cards.
3. **Mapping:** read only `rollno` and `name` from the active sheet of `student_face_list.xlsx` once per backend process. The immutable mapping is shared safely between camera threads, with initialization protected by a lock. The current workbook contains **16 students**. `face_file` is ignored and student photos are never opened. Missing headers, empty metadata and duplicate rolls disable QR mapping rather than guessing names; video and activities continue.
4. **Scan frequency:** at most once per **1 second** per camera, and only when there is a currently observed person. The decoder is created once per capture connection; the workbook is not read per frame, and no database lookup is used for QR identification.
5. **Association:** use the QR's center and existing YOLO/ByteTracker person boxes. A uniquely containing, currently observed box wins. Multiple containing boxes are ambiguous and rejected. Otherwise use point-to-box distance, with a maximum of **0.08 × frame diagonal**. Reject the nearest match if its distance differs from the second-nearest by at most **0.03 × frame diagonal**. Codes must match an enrolled roll number exactly. Unknown/empty/unreadable codes cannot assign identity. Conflicting rolls on one track, or one roll simultaneously presented by multiple tracks, are rejected.
6. **Identity lifetime:** **30 seconds**, refreshed when the same valid QR is seen again. Clear when the tracker no longer returns that person, `time_since_update > 0`, the timeout expires, or the capture restarts/reconnects. Each camera has separate mutable identity state, owned exclusively by its capture thread. Numeric track IDs cannot inherit identity from an older capture session.
7. **Overlay:** backend OpenCV draws the label into the JPEG; the existing WebSocket and frontend display it unchanged. Known example:

   ```text
   ROLLNO | NAME
   CONFIRMED ACTIVITY
   #12 person 0.91
   ```

   Unknown tracks display UNKNOWN and can still display confirmed activities. Text prefers space above the box; otherwise it uses the box's top interior, with frame-coordinate clamping.
8. **Behaviors preserved:** SLEEPING, TALKING, RUNNING, SUDDEN ACCELERATION, ZIGZAG MOVEMENT, LOITERING and RESTRICTED ZONE. Up to three person behaviors, ordered by severity then recency, retain the existing four-second display cache. PHONE USE and EATING are not supported or fabricated. Crowd density/surge/formation and sustained classroom conditions remain separate camera banners. No QR or rendering code creates attendance records or alerts.
9. **Configuration:** defaults are already active; optionally set these in `backend/.env` (and root `.env` for consistent startup configuration):

   ```dotenv
   QR_IDENTIFICATION_ENABLED=true
   STUDENT_QR_WORKBOOK=student_face_list.xlsx
   QR_SCAN_INTERVAL_SECS=1.0
   QR_IDENTITY_TIMEOUT_SECS=30.0
   QR_ASSOC_MAX_DISTANCE_FRACTION=0.08
   QR_ASSOC_AMBIGUITY_MARGIN_FRACTION=0.03
   ```

   Restart the backend to reload an edited workbook or configuration. Remove a workbook row and restart to stop accepting that roll number. QR identification remains independent of the existing PostgreSQL camera records.
10. **Tests and performance:**
    - **47 focused tests passed**, covering QR matching, all previous overlays, camera updates and stream recovery. The QR tests include a real OpenCV decode, lookup caching, invalid/unknown values, stale/expired/disappeared tracks, ambiguity, conflicting codes, decoder failure, single-card fallback and known/unknown activity rendering.
    - All **16 generated PNGs** decoded and resolved to the expected roll/name using the actual scanner with controlled person boxes. No test identities or activities were injected into the live cameras or Redis.
    - Controlled 640×480 QR identity scanning took a median **55.39 ms**. It runs at most once per second, with cached identity used between scans. Card-only scan median was **33.57 ms**, p95 **48.46 ms**. These are local controlled measurements, not a guarantee for large/blurred frames.
    - The full backend run before the additional single-card fallback regression test had **112 passed, 9 pre-existing failures**: old camera-less StreamManager expectations, inconsistent loitering test coordinates, outdated CSI scoring expectations, a CSI fixture older than the real 24-hour window, and a missing tracker-test import. The final focused suite, including the fallback test, passed.
    - Native Entrance verification sampled **3.48 processed FPS**, one tracked person, a recent frame and valid 480×640 JPEG delivery over the authenticated camera WebSocket. That person correctly remained unassigned/UNKNOWN; no physical enrolled QR presentation was observed during the sample. Existing historical baseline values in the verifier are not a controlled comparison for this run.
11. **Camera status and limitations:** General Entrance is running, with its saved local-webcam source `0` unchanged. Classroom retains `http://172.28.170.74:8080/video` and currently reports **Camera source unreachable: connection timed out**. Its controlled QR + sleeping capture-to-JPEG/Redis integration test passes, but live phone-camera verification needs a reachable source. The native application services were initially stopped; they were started for verification, and the final backend implementation is loaded. Docker services remained healthy. A QR identifies the presented code, not the holder's authenticity; copied codes can be presented. Association is deliberately conservative and may leave a person UNKNOWN when boxes overlap or the card is unreadable.

Show one student's generated QR clearly inside their detected person box, away from other people. The name and roll number should appear after the next scan. If no confirmed behavior exists, only identity and the existing track label appear.

QR fixture/performance verification is recorded in `logs/student-qr-verification.json`. Native camera verification is in `logs/behavior-overlay-verification.json`; current backend logs are `logs/backend-student-qr-final.out.log` and `logs/backend-student-qr-final.err.log`.

# QR decoding and association fix

Verified on 2026-10-12.

- **Raw code:** `student_qr/23VE1A6607.png` decodes to `23VE1A6607` with both OpenCV multi-code and single-code APIs. All 16 student identities load from the workbook; the backend prints `Loaded 16 QR student identities.` once per process.
- **Actual webcam result:** General Entrance decoded **23VE1A6630**, confirmed it was in the mapping, and assigned **Shabana** to **track 1**. The captured scan was frame 63; identity was attached on renderer frame 66. This is a live result, not the controlled track-24 fixture.
- **Successful decoding path:** single-code fallback on the **upscaled full frame**. Original-frame QR corners were approximately `(370.2,342.8), (426.5,328.0), (442.5,385.3), (383.0,399.5)`; center `(405.6,363.9)`. The detected pattern edges were about 60 pixels long, excluding the white border.
- **Presentation issue observed:** the inspected webcam frame initially showed the back of the phone, with no QR visible. Live scans therefore reported empty text and no assignment. After the QR was presented to the camera, a valid roll was decoded and assigned. Keep the complete square and white border facing the webcam, preferably at least about 100 pixels across in the preview for more reliable decoding.
- **Scan timing:** temporary configuration is `QR_SCAN_INTERVAL_SECS=0.25`. Only one QR job runs at a time; observed median submission spacing in the recorded sample was **0.936 seconds**, limited by decoding work and processed-frame cadence. The permanent code default remains **1.0 second**.
- **Association rule:** prefer a uniquely containing current person box; otherwise choose the nearest box if distance from QR center to box is within `max(QR_ASSOCIATION_MARGIN_PX, QR_ASSOC_MAX_DISTANCE_FRACTION × frame diagonal)`. The explicit margin is **40 pixels**; the retained fraction is **0.08** (64 pixels for 640×480). Overlapping boxes and near-tied candidates within the existing **0.03 × diagonal** ambiguity margin are rejected. Results stay attached to the original scan frame's track ID and cannot be rematched to another person's newer box. Disappeared/stale tracks reject delayed results.
- **Reliability changes:** try full frame, enlarged full frame, padded sufficiently large person ROIs and enlarged ROIs; use nearest-neighbor enlargement with preserved aspect ratio and map all corners back to original coordinates. Person ROIs below 64×96 pixels are skipped. Trim decoded whitespace without changing case. Preserve unreadable corners and use single-code fallback when multi decoding is empty or incomplete.
- **Stall protection:** a live OpenCV decode of an unreadable pattern stalled the capture path. QR decoding now runs in one QR-only process with bounded queues and a **2-second watchdog**. It does not open a camera, create a tracker, or query the database. Capture-thread updates are nonblocking. Already decoded matches are returned progressively so another ROI's subsequent stall cannot discard them. Worker errors/timeouts leave video and behavioral processing running; workers are cleaned up on capture stop/reconnect. This changes only QR processing, not the camera/tracking architecture.
- **Debugging:** `QR_DEBUG_LOGGING=true` records capture frame/time, variant/API, found state, normalized text, original-frame corners/center, membership, candidates, selection and rejection/assignment reason. `QR_DEBUG_OVERLAY=true` draws temporary QR polygons and the decoded roll, or UNREADABLE for undecoded patterns. No identity is assigned from corners alone. Native finder false positives are possible; an unreadable debug polygon is not evidence of a valid QR.
- **Size diagnostic:** clean fixtures decoded at 290, 160, 120, 100, 80, 64 and **48 pixels** square; 40 and 32 pixels failed. This is a clean resized-image test, not a universal webcam threshold. Blur, glare, focus, perspective, display refresh and compression can demand larger codes. Run `backend/.venv/Scripts/python.exe scripts/diagnose_student_qr.py`; results are in `logs/student-qr-size-diagnostic.json`.
- **Tests: 54 passed.** Focused QR, overlay, camera-setting and recovery tests include real QR decoding, whitespace normalization, incomplete-multi fallback, ROI coordinate transforms, margins/ambiguity, optional debug drawing, nonblocking process decoding, timeout cleanup, stale-result rejection and progressive result handling. No test QR identities or fake activities were injected into the live cameras.
- **System verification:** General Entrance resumed fresh JPEG/WebSocket delivery after decoder isolation. A sample with three tracks ran at 2.18 processed FPS, with frame age 0.1 seconds. Classroom remains at its unchanged unreachable phone URL; no source was changed. QR identities still expire after 30 seconds or sooner when a track disappears/stales, so UNKNOWN after the QR is removed and the timeout expires is expected.

## Files changed

`ai-engine/identity/qr_identity.py`, `ai-engine/vision/stream_manager.py` (QR wiring and cleanup only), `backend/app/core/config.py`, `.env`, `backend/.env`, `.env.example`, `backend/tests/unit/test_qr_identity.py`, `backend/tests/unit/test_behavior_overlays.py` (QR test wiring only), `scripts/diagnose_student_qr.py`, and this report.

YOLO, tracker, behavior detectors, alerts, CSI, camera source records, student photos and the source workbook were left unchanged.

## Current debug settings

```dotenv
QR_SCAN_INTERVAL_SECS=0.25
QR_ASSOCIATION_MARGIN_PX=40
QR_DEBUG_LOGGING=true
QR_DEBUG_OVERLAY=true
QR_SCAN_TIMEOUT_SECS=2.0
```

These debug settings remain enabled temporarily for further camera testing. After debugging, set the interval to `1.0` and both debug flags to `false` in root and backend environment files, then restart the backend to reload settings. This avoids keeping the expensive debug scan rate and verbose logs permanently enabled.

Live success evidence is saved in `logs/qr-live-debug-verification.json` and `logs/backend-qr-debug-final.err.log`. Current backend logs are `logs/backend-qr-live.out.log` and `logs/backend-qr-live.err.log`.

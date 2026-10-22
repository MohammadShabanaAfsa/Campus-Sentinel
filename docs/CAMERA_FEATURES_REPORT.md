# Restricted area, fall detection and vehicle counting

Implemented and loaded on 13 October 2026. Existing activity thresholds, QR,
CSI, crowd/loitering routing and alert dispatch architecture are unchanged.

## Restricted area

Open a camera's live view and select **Draw Restricted Zone**, or use **Zones**
on the camera card. Click at least three points and Save. Existing polygons have
Edit/Clear controls; Redraw clears the draft points while preserving the edited
zone ID. Name, severity and enabled state are editable. Save errors are visible.

Coordinates are normalized against the displayed snapshot rectangle, which
keeps the original frame aspect ratio. Legacy saved 640×360 pixel polygons are
converted for editing. New API writes require normalized, finite coordinates
and a nonzero polygon area. Existing `restricted_zones` rows store the polygon,
camera ID, name, severity and enabled state; no new table is required.

Detection uses the person's bbox bottom-center, normalized by actual frame
dimensions. No configured polygon means no event. Zones refresh within five
seconds without camera restart or per-frame database queries. Entry emits one
detector alert and a person-level RESTRICTED AREA label; leaving rearms entry.
Zone ID/name are included in overlay event metadata for the existing alert path.

Native authenticated API create/edit/clear checks passed for General Entrance
and Classroom using temporary **disabled** zones. Those rows were removed;
existing user zones and camera configurations were preserved.

## Fall detection

`FallDetector` consumes a separate `fall_pose` metadata export from the already
sampled MediaPipe Pose result. No additional model or per-frame Pose invocation
is introduced, and existing face/wrist signals remain unchanged.

Evidence combines torso shoulder-to-hip angle, wide bbox, low hip position,
recent upright history and rapid downward/vertical-to-horizontal change.
Visible downward supporting legs reject crouch/bending candidates. A qualifying
transition must remain horizontal for four seconds before emitting the HIGH
person-level FALL DETECTED event. Sustained upright recovery clears confirmation.
Only confirmed events reach the existing clean overlay and alert router.

Configuration:

```dotenv
FALL_ANGLE_THRESHOLD=60
FALL_PERSISTENCE_SECS=4
FALL_RECOVERY_SECS=2
```

States are per camera/track: NORMAL → FALL CANDIDATE → FALL CONFIRMED.
Uncertain/missing Pose cannot start confirmation. Track loss expires state after
three seconds. Existing alert transition/cooldown rules suppress duplicates.

Tests cover upright, sitting, bending, supported crouch/shoe-tying geometry,
slow lying transitions, brief horizontal posture, sudden sustained posture,
recovery, track expiry and one alert per confirmed episode.

## Vehicle counting

Select **Draw Counting Line** in the live view, click start/end and Save. Edit,
Redraw, Clear and enabled controls are available. The line is stored normalized
in the existing camera config JSONB under `vehicle_counting_line`.

Existing YOLO/tracker output supports car, motorcycle, bicycle, bus and truck;
bus/truck classes were added to the existing detector's class allowlist.
Counting requires a current vehicle track to cross the finite saved segment.
A small normalized deadband rejects near-line jitter. IN crosses onto the
right-hand side of the directed start → end line in image coordinates; reversing
endpoints reverses direction. Each track counts at most once per direction per
stream session. Stale tracks and people are excluded.

Counts appear as a compact bottom-of-frame IN/OUT/TOTAL strip and in the existing
Redis track payload. No line means no counting/display, including Classroom.
Crossings create no alerts. Config refresh is cached for five seconds. Counts
reset when the counting line changes or the camera stream restarts. Optional
hourly/daily historical count storage was not added.

Native authenticated line save/read/clear checks passed on both cameras with a
temporary disabled line. The test left both cameras unconfigured for counting.
Tests cover all five vehicle classes, IN/OUT, no crossing, finite segment bounds,
deduplication, stale tracks, resolution independence, deadband and reset.

## Verification and limits

- **184 selected backend regression tests passed**, including existing person
  activities, QR identity, eating, crowd, loitering, routing and clean overlays.
- **26 frontend tests passed**, including draw/save/edit/clear workflows and
  normalized pointer coordinates.
- TypeScript checks and the production build passed. The new production UI is
  served from `.next-camera-features`; `/cameras` returns HTTP 200.
- General Entrance is online, with fresh frames and one person track.
- Classroom currently reports `Camera source unreachable: connection timed out`
  at its unchanged saved phone source. Its configuration/API paths passed, but
  live detections cannot be verified until frames return.
- No physical fall, real vehicle crossing or user-drawn restricted-area entry
  was observed during this implementation. No synthetic live alerts were inserted.

Fall detection is a conservative heuristic that still needs live validation for
camera angle, visibility and tracking continuity. It can miss occluded falls,
falls with no prior upright observation or folded-leg geometry; rapid intentional
lying can resemble a fall. Tests cannot establish real-world detection accuracy.
Zone re-entry rearms the detector, but the preserved 60-second alert cooldown
may suppress a rapid repeat dashboard alert. Vehicle totals are session-local.

Runtime evidence:

- `logs/camera-features-api-verification.json`
- `logs/qr-identity-camera-features-final.json`

Repeat API verification with
`backend/.venv/Scripts/python.exe scripts/verify_camera_features.py`.

## Files changed

- `ai-engine/behavioral/fall.py`
- `ai-engine/behavioral/zone_checker.py`
- `ai-engine/classroom/face_pose_analyzer.py`
- `ai-engine/vision/vehicle_counter.py`
- `ai-engine/vision/stream_manager.py`
- `ai-engine/vision/detector.py`
- `ai-engine/vision/frame_annotator.py`
- `ai-engine/vision/behavior_overlay.py`
- `backend/app/schemas/camera.py`
- `backend/app/api/v1/endpoints/cameras.py`
- `backend/app/core/config.py`
- `backend/tests/unit/test_camera_features.py`
- `backend/tests/unit/test_behavior_overlays.py`
- `frontend/src/components/cameras/ZoneDrawerModal.tsx`
- `frontend/src/components/cameras/LiveCameraModal.tsx`
- `frontend/tests/camera-geometry.test.cjs`
- `frontend/tsconfig.json` (Next.js verification build types)
- `.env.example`
- `scripts/verify_camera_features.py`
- `docs/CAMERA_FEATURES_REPORT.md`

Disposable frontend launcher: `logs/restart-frontend-camera-features.sh`.

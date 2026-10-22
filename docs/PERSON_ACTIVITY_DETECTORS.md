# Phone use and eating prototype

These two LOW-severity person activities consume actual YOLO detections and
MediaPipe landmarks on the existing tracker IDs. They feed the existing overlay
cache and Redis track payload. They create no automatic alerts or database tables.
QR identification, sleeping/talking rules, CSI, and camera sources are unchanged.

## Phone use

The existing YOLO COCO model supports class 67, `cell phone`; this class was added
to the retained detection filter. Phone objects are excluded from tracker input
so they cannot consume or interfere with existing person track IDs.

A detection must have confidence >= 0.5. Its center must be within the person's
horizontal box plus the configured pixel margin, and above 75% of person height.
It must be within 0.45 visible shoulder widths of a visible wrist. That wrist must
be above its corresponding visible elbow by at least 0.05 shoulder widths.
Missing pose evidence, distant objects and resting desk phones do not qualify.

The closest qualifying person receives the object only when there is no competing
person or the normalized distance advantage exceeds 0.15 shoulder widths. Ties
are rejected. Confirmation requires both two seconds of persistent association
and at least three samples. Gaps longer than 1.5 seconds reset/clear the state.

## Eating

Eating uses the existing FaceMesh mouth center and visible Pose wrists/shoulders.
It does not use mouth movement or the talking detector's MAR value.

A wrist must first be observed away from the mouth (>= 0.70 shoulder widths),
approach within 0.35 shoulder widths, then withdraw to the away region. A complete
cycle takes 0.25–3 seconds in the near region. Counted cycles must be at least one
second apart. Three completed cycles within 20 seconds confirm eating; the last
cycle must be within six seconds. Missing landmarks interrupt a cycle. Initial
hand-near-mouth observations and stationary chin resting do not count.

These are conservative motion heuristics, not proof of ingestion. Repeated mouth
touching can resemble eating; occlusion, small people, low-confidence landmarks,
and sampling can miss real actions. Phone presentation, including a QR displayed
on a held phone, can meet the phone-use rule. Distinguishing such purposes needs
additional evidence and real-video validation.

## Configuration defaults

| Setting | Default |
| --- | --- |
| ACTIVITY_ANALYSIS_INTERVAL_SECS | 0.75 |
| ACTIVITY_DEBUG | false |
| PHONE_USE_MIN_DURATION_SECS | 2.0 |
| PHONE_USE_MIN_HITS | 3 |
| PHONE_USE_CLEAR_TIMEOUT_SECS | 1.5 |
| PHONE_PERSON_ASSOCIATION_MARGIN | 20.0 pixels |
| PHONE_HAND_DISTANCE_THRESHOLD | 0.45 shoulder widths |
| EATING_MIN_EVENTS | 3 |
| EATING_WINDOW_SECS | 20.0 |
| EATING_CLEAR_TIMEOUT_SECS | 6.0 |
| EATING_MOUTH_DISTANCE_THRESHOLD | 0.35 shoulder widths |
| EATING_MIN_NEAR_SECS | 0.25 |
| EATING_MAX_NEAR_SECS | 3.0 |
| EATING_MIN_EVENT_INTERVAL_SECS | 1.0 |

Sampling runs on processed frames, so 0.75 seconds is a target minimum interval,
not a guaranteed frequency. Classroom monitoring frames can also sample, sharing
the same results to avoid duplicate MediaPipe work. YOLO remains shared; the
existing per-camera MediaPipe instance is reused. No per-frame database queries
were added. State is in capture-thread memory and removed when the track is absent.

Confirmed events retain the existing `track_id`. The existing overlay cache
combines them with other behaviors and QR identity, limits person labels to two
by severity/recency, and keeps camera-level events in banners. No ZIGZAG, NORMAL,
or SAFE labels were added. Debug diagnostics are disabled by default.

## Files changed for this task

- `ai-engine/vision/detector.py`: retain COCO phone detections.
- `ai-engine/classroom/face_pose_analyzer.py`: export mouth and visible pose points.
- `ai-engine/behavioral/person_activity.py`: per-track temporal activity rules.
- `ai-engine/vision/stream_manager.py`: sampling, same-ID overlay integration.
- `ai-engine/classroom/classroom_monitor.py`: optionally reuse sampled landmarks.
- `backend/app/core/config.py`: configurable defaults.
- `.env.example`: document defaults; existing `.env` files are unchanged.
- `backend/tests/unit/test_person_activity.py`: 18 detector/rule tests.
- `backend/tests/unit/test_behavior_overlays.py`: isolate activity sampling in the
  existing controlled pipeline fixture.
- `docs/PERSON_ACTIVITY_DETECTORS.md`: this report.

## Validation on 2026-10-12

Focused suite: **71 passed**, covering activity rules, overlays, QR identity,
retired zigzag suppression and stream recovery. The activity tests cover class
retention, persistence, margin association, desk/distant/ambiguous phone rejection,
clear timeouts, repeated eating cycles, talking-only and stationary-hand negatives,
missing landmarks, independent tracks, concurrent activities and debug-off behavior.

Full backend suite before the final three focused tests: **139 passed, 9 failed**.
The outstanding failures concern legacy camera-less StreamManager expectations,
loitering fixture coordinates, dated/legacy CSI expectations, and a tracker test
missing its pytest import. This task does not repair those unrelated modules.
The frontend production build passed, including type checking and page generation.

Native live check: General Entrance running, 2.48 FPS, fresh frame age 0.3 seconds,
valid 640x480 WebSocket JPEG and one person track. Classroom's existing phone URL
`http://172.28.170.74:8080/video` timed out; no live Classroom verification was
possible. No identity was decoded in this runtime sample. QR code/settings were
unchanged and QR regression tests passed. No claim of live phone/eating accuracy
is made from controlled fixtures; real action trials remain necessary.

The updated native backend was restarted to load the code. Celery, frontend,
PostgreSQL and Redis were left running. Runtime logs are in
`logs/backend-activities.out.log` and `logs/backend-activities.err.log`.

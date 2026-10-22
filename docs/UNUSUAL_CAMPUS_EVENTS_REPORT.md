# Unusual campus events — 13 October 2026

Implemented independent `CampusEvents` analyzers on both camera streams. They
consume existing active tracks and shared MediaPipe Pose samples, produce only
confirmed camera-level events, and use the existing alert task → PostgreSQL →
Redis → WebSocket → dashboard path. Working activity thresholds, QR, CSI,
restricted-area rules, fall detection, vehicle counts and camera-role exclusions
remain unchanged. No new model instances or per-frame database reads were added.

## Rules and thresholds

| Feature | Confirmation | Clear/reset |
|---|---|---|
| SUSPECTED FIGHT | Nearby pair within normalized radius 0.15; both people have rapid wrist motion ≥0.70 person heights/sec; relative body motion ≥0.10 normalized frame units/sec; at least three rapid samples and three approach/separation direction reversals within five seconds; sustained qualifying evidence for four seconds | Three seconds of sustained calm/separation; expired tracks/capture gaps clear state |
| ABANDONED BAG | Previously associated backpack/handbag/suitcase; no nearby person; stationary within normalized radius 0.02 for 45 seconds | Nearby person, significant bag movement or track expiry |
| AFTER-HOURS PRESENCE | Current people outside configured permitted hours for two seconds | No qualifying people or return to permitted hours |
| EMERGENCY EXIT BLOCKED | Same active person/object remains inside its saved exit polygon for ten seconds | Object leaves, expires or polygon changes |

Bag ownership requires an unambiguous nearest person bbox within normalized
radius 0.18. Bags with no observed owner are not called abandoned. Bag proximity
uses bbox distance so a bag on the ground near the owner's feet can associate.
Other nearby people suppress abandonment too. A five-second bag threshold is
available only when `ACTIVITY_DEBUG=true`; production remains 45 seconds and
`ACTIVITY_DEBUG=false` remains set. Existing object classes/tracker are reused.

Fight states are NORMAL → FIGHT_CANDIDATE → FIGHT_CONFIRMED. Confirmation
requires combined temporal signals, not proximity alone or a gesture. Pose wrist
metadata is exported separately from the already executed Pose inference, so
existing phone/eating wrist and face signals are preserved. Missing usable wrist
observations cannot start a fight confirmation. The banner includes involved
track IDs, e.g. `SUSPECTED FIGHT - TRACKS #2 / #5`. Alert titles use an em dash.

Exit polygons use normalized coordinates. Person foot points and object centers
are tested against each polygon. Stale tracks are excluded from every feature.
Multiple simultaneous confirmations of one kind form one camera-level episode,
with all involved track/zone/bag IDs retained in metadata. Existing transition
deduplication suppresses per-frame alerts. All four event severities are HIGH.

## Configuration UI and storage

Open the camera live view and select **Campus Rules / Exit Zones**.

- Set permitted start/end hours, IANA timezone and enable after-hours monitoring,
  then **Save Hours**. Defaults are 06:00–21:00, Asia/Kolkata, **disabled** until
  explicitly enabled. Overnight ranges are supported; equal endpoints permit
  the full day.
- **Draw Schedule Zone** adds a polygon with its own permitted hours. Enabled
  zone hours override camera hours inside that zone; overlapping rules all
  must permit the time. Zones inherit the camera timezone.
- **Draw Exit Zone** adds a named emergency exit polygon. Save/Edit/Redraw/Clear
  and enabled controls are provided. No exit polygon means no exit monitoring.

Per-camera settings reside in existing `cameras.config` JSONB under
`campus_events`, using authenticated GET/PUT
`/api/v1/cameras/{camera_id}/campus-events`. No tables or migrations were needed.
Configuration refresh is cached for five seconds. Model validation rejects
invalid timezones, HH:MM values and non-normalized/degenerate polygons. No debug
table or candidate values appear in the normal camera feed.

New settings and production values are documented in `.env.example`:
`FIGHT_PERSISTENCE_SECS=4`, `FIGHT_CLEAR_SECS=3`,
`FIGHT_PROXIMITY_RADIUS=0.15`, `FIGHT_RELATIVE_SPEED=0.10`,
`FIGHT_ARM_SPEED=0.70`, `ABANDONED_BAG_SECS=45`,
`ABANDONED_BAG_TEST_SECS=5`, `BAG_OWNER_RADIUS=0.18`,
`BAG_STATIONARY_RADIUS=0.02`, `AFTER_HOURS_CONFIRM_SECS=2`,
`EXIT_BLOCKAGE_SECS=10`.

## Verification

- **210 selected backend regression tests passed**, including 26 unusual-event
  tests plus existing person activities, fall/vehicle/zone tests, QR, crowd,
  loitering and camera routing/overlay tests.
- **28 frontend tests passed**, including normalized exit draw/save/edit/clear
  and camera/polygon schedule saves. TypeScript and production build passed.
- Tests reject conversation, hugging, handshake, walking together and brief
  movement inputs; confirm sustained combined fight evidence; and verify calm
  recovery and one alert. Bag, schedule/overnight/zone override, exit timing,
  stale-track, configuration preservation and duplicate cases are covered.
- For all four new types, isolated tests execute the actual existing alert task
  with mocked persistence/Redis, checking HIGH severity, metadata persistence,
  `alerts_channel` publication and cooldown suppression. The frontend already
  accepts generic `new_alert` messages. No test detections or fake alerts were
  inserted into the live database or broadcast as real events.
- Native authenticated configuration save/read/edit/clear checks passed on both
  cameras using temporary **disabled** rules, then restored their original
  settings. Existing camera configuration keys were preserved.
- General Entrance is **online**, with active tracked people and fresh frames.
  Classroom reports **`Camera source unreachable: connection timed out`** at its
  unchanged saved phone source. Its configuration/API tests passed, but live
  unusual-event analysis cannot be verified until frames return.
- Backend health and `/cameras` return HTTP 200. Backend/frontend were reloaded;
  Redis, PostgreSQL and Celery were preserved. UI build: `.next-campus-events`.

Evidence: `logs/campus-events-native-verification.json`,
`logs/qr-identity-campus-events.json`,
`logs/campus-events-live-observation.json`. Repeat the reversible native API
check with `backend/.venv/Scripts/python.exe scripts/verify_campus_events.py`.

## Remaining limitations

No live fight, bag abandonment or exit blockage was staged or confirmed during
this work. These are conservative heuristic prototypes, not validated estimates
of intent or violence. Fast playful interactions can resemble fight evidence;
occluded wrists or slow sampling can miss it. Bag ownership is inferred from
proximity, not verified ownership; tracker ID changes can lose association.
Exit center/foot-point tests can miss partial overlap. Schedule monitoring
requires an enabled rule and a correct system clock/timezone. Episodes reset
after camera restart or capture discontinuities; uncertain time gaps cannot
confirm a continuous condition. Existing 60-second alert cooldown and brief
transition grace remain in effect and may suppress rapid repeat dashboard
alerts even when the analyzer rearms. Live accuracy needs representative saved
footage or actual observations; test results alone do not establish it.

## Files changed

- `ai-engine/behavioral/campus_events.py`
- `ai-engine/classroom/face_pose_analyzer.py`
- `ai-engine/vision/stream_manager.py`
- `ai-engine/vision/behavior_overlay.py`
- `ai-engine/vision/frame_annotator.py`
- `ai-engine/vision/confirmed_alerts.py`
- `backend/app/core/config.py`
- `backend/app/schemas/camera.py`
- `backend/app/api/v1/endpoints/cameras.py`
- `backend/tests/unit/test_campus_events.py`
- `frontend/src/components/cameras/CampusRulesModal.tsx`
- `frontend/src/components/cameras/LiveCameraModal.tsx`
- `frontend/tests/campus-rules.test.cjs`
- `frontend/tsconfig.json` (new production build type directory)
- `.env.example`
- `scripts/verify_campus_events.py`
- `docs/UNUSUAL_CAMPUS_EVENTS_REPORT.md`

Disposable UI launcher: `logs/restart-frontend-campus-events.sh`.

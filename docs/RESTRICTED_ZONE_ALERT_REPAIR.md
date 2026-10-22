# Restricted-area alert path — 13 October 2026

## Findings

Saved polygons are active, normalized and scoped to the correct General Entrance
camera ID. The source is 640×480. The detector uses bbox bottom-center:
`foot_x=(x1+x2)/2`, `foot_y=y2`, then divides by the actual source width/height.
No display/source coordinate mismatch was found.

The observed no-alert condition was a real OUTSIDE result, not a failed polygon
load: person bbox bottoms were near normalized Y=0.999. The polygon used during
the live recording ended at Y=0.95238. A torso overlapping a polygon does not
establish that its required foot point is inside it. The user updated the saved
polygon during investigation; the analyzer loaded that updated polygon without
the agent changing its coordinates.

A separate alert-path defect was found: the transition router keyed restricted
events only by behavior/track ID, and the worker used a shared 60-second cooldown
for that track. Brief exit/re-entry, another zone or reused track IDs after a
stream restart could therefore suppress a valid entry episode.

## Restricted-only changes

Each zone/track OUTSIDE→INSIDE transition receives a unique episode ID, retained
while inside and cleared after an observed exit. The overlay state, behavior
snapshot, alert metadata, transition router and worker carry this ID. Distinct
zone episodes no longer collapse in the confirmed-event cache. One person still
has one clean RESTRICTED AREA label even when multiple zone events are present.

The worker atomically deduplicates restricted-zone deliveries using camera ID,
zone ID, track ID and episode ID, retaining the reservation for 24 hours. New
entries use new keys, so old cooldowns cannot suppress their first valid alert.
Duplicate deliveries of the same episode remain suppressed. Other alert types
retain their original cooldown and transition behavior.

Wrong-camera polygons and invalid/stale tracks are rejected. Zone refresh
preserves unchanged zones' episode state, so editing another polygon does not
recreate alerts unnecessarily. Existing severity configuration is preserved;
the saved General Entrance zone is HIGH. No polygon or unrelated detector was
modified.

`RESTRICTED_ZONE_DEBUG=true` enables log-only diagnostics for one active person
per analyzer sample: camera/track ID, source size, raw/normalized foot point,
polygon, inside flag, transition, episode ID and emit/suppression reason.
Diagnostics were enabled temporarily for this recording and are now disabled.
`ACTIVITY_DEBUG=false` remains set and no debug overlay is drawn.

## Live observation

The user selected **Use current live footage only**. A 45-second observer read
real detector logs, Redis track/overlay snapshots, Redis alert publication and
the authenticated events WebSocket; then checked PostgreSQL for matching alerts.
No tracks, polygons, detections or live alerts were injected.

| Observation | Result |
|---|---|
| Diagnostic samples | 46 |
| Source dimensions | 640×480 |
| Normalized foot Y range | 0.998811–0.999792 |
| Polygon maximum Y | 0.952381 |
| Inside samples / entry transitions | 0 / 0 |
| RESTRICTED AREA overlay frames | 0 |
| PostgreSQL restricted alerts | 0 |
| Redis restricted messages | 0 |
| WebSocket restricted alerts | 0 |
| New dashboard restricted alert | None expected; no live entry occurred |

Example Track #2: foot `(366.40,479.62)`, normalized
`(0.572493,0.999202)`, transition OUTSIDE, reason `foot_outside_polygon`.
Thus the negative live result is correct; positive live entry/overlay/delivery
remains unverified with this footage. A positive check requires the bbox foot
point to actually enter the drawn area, with feet visible. The repair does not
switch to torso-center detection or enlarge the user's polygon to force it.

Evidence: `logs/restricted-zone-live/report.json` and captured JPEGs in that
directory. Repeat the observer with
`backend/.venv/Scripts/python.exe scripts/capture_restricted_zone_live.py --seconds 45`
while restricted-only logging is enabled.

## Tests and service state

**217 selected backend tests passed**, including seven new restricted-path tests:
outside, entry, staying inside, exit/re-entry within transition grace, old
cooldown rejection prevention, duplicate episode suppression, wrong camera,
stale tracks, source-resolution scaling and separate zone episodes. Actual
alert-task tests with mocked DB/Redis verify persisted HIGH alerts and published
messages for both entry episodes, not synthetic live database rows.

**35 frontend tests passed**, including dashboard alert bootstrap/WebSocket
deduplication. Frontend alert handling was unchanged; the actual user dashboard
was not manually operated and no positive live WebSocket alert was available
to visually verify a new row.

The alert worker was warm-restarted with zero active jobs to load its targeted
deduplication change. Backend was reloaded for diagnostics and then restored to
normal logging. General Entrance remains running; other detector rules,
frontend code, PostgreSQL schema, Redis architecture and CSI were unchanged.

## Files changed

- `ai-engine/behavioral/zone_checker.py`
- `ai-engine/vision/behavior_overlay.py`
- `ai-engine/vision/confirmed_alerts.py`
- `backend/app/services/tasks/alert_tasks.py`
- `backend/app/core/config.py`
- `backend/tests/unit/test_restricted_zone_alert_path.py`
- `backend/tests/unit/test_behavior_overlays.py`
- `scripts/capture_restricted_zone_live.py`
- `docs/RESTRICTED_ZONE_ALERT_REPAIR.md`

Disposable launchers: `logs/restart-backend-zone-debug.sh`,
`logs/restart-worker-zone-fix.sh`.

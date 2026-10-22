# Live activity diagnostics

Enabled `ACTIVITY_DEBUG=true` in backend/.env. Both camera loops are instrumented.
Thresholds, QR, alerts, CSI, classroom metrics and inference cadence are unchanged.
Disable the temporary panel/logging by setting the flag false and restarting the
backend. Only the native backend was restarted to load the instrumentation.

Each active current person track emits one structured `ACTIVITY_SAMPLE` record
per activity sample. Numeric absent measurements are null, never guessed zero.
Face-state entries report last rule-update time and updated_this_sample alongside
current landmark measurements. Classroom sleeping/talking remain every 30 raw
frames; diagnostics do not add extra rule updates or consume alerts. Faculty
tracks excluded by ClassroomMonitor may have no sleep/talk state; the reason is
reported explicitly. Phone/eating observations include association evidence,
normalized distances, cycle phases, timestamps and actual confirmation state.

Latest detailed captured General Entrance sample: track 1, raw frame 531,
sample_time 1791816448.6365426, MediaPipe executed=true.

| Activity | General Entrance live state | Classroom live state | Why not confirming |
| --- | --- | --- | --- |
| SLEEPING | Face available; EAR=0.3748434533; head_down=false; candidate start=null; duration=0/15 seconds; confirmed=false | No samples: native stream connection timed out | eyes_not_closed_and_no_qualifying_head_down |
| TALKING | Mouth available; MAR=0.0367061247; samples=30; MAR std=0.0099855215; candidate duration=0/8 seconds; confirmed=false | No samples: native stream connection timed out | mar_std_below_threshold (existing cutoff 0.035) |
| PHONE USE | Cell phone detected=false; confidence=null; wrists available=false; distance=null; associated IDs=[]; hits=0; duration=0; confirmed=false | No samples: native stream connection timed out | no_cell_phone_detected |
| EATING | Mouth available; shoulder scale=0; left/right distances=null; both states UNAVAILABLE; cycles=0/3 within 20 seconds; confirmed=false | No samples: native stream connection timed out | missing_mouth_wrist_or_shoulder_landmarks |

Classroom was configured and retried throughout the checks but the native backend
could not connect to http://192.168.1.10:8080/video. No Classroom numeric values
were fabricated. The user was asked for the phone's currently displayed URL and
server state. Diagnostics will run automatically when its source reconnects.

State persistence was verified live: track 1 reached 52 consecutive activity
samples and accumulated 30 retained mouth samples. It was not recreated each
frame. Seven interruptions occurred earlier in the final capture, with explicit
ACTIVITY_STATE_RESET reason `track_missing_or_not_current`. The existing cleanup
removes person activity state when a track is absent from current detections;
this applies even if that tracker ID subsequently reappears. No cleanup policy
was changed. A separate real frame showed Persons:0 during a head-down moment,
confirming that losing the person detection prevents a box/activity on that frame.

The debug panel was visually verified in a real General Entrance JPEG. It shows
SLEEP EAR/duration, TALK std/sample count, PHONE hits/duration and EAT cycles for
one selected track. No new confirmed behavior label was injected for this check.

Artifacts:

- `logs/backend-activity-diagnostics-final.err.log`: current live structured logs.
- `logs/activity-live-diagnostics-final.json`: captured exact values and ranges.
- `logs/activity-debug-general.jpg`: real frame with the temporary panel.
- `logs/backend-activity-diagnostics.err.log`: initial capture retained separately.
- `scripts/collect_activity_diagnostics.py`: extracts only activity records, avoiding
  unrelated log entries such as WebSocket authentication URLs.

Run the collector with:

```powershell
backend/.venv/Scripts/python.exe scripts/collect_activity_diagnostics.py
```

Files changed: ai-engine/classroom/student_state.py (read-only diagnostic records),
ai-engine/classroom/classroom_monitor.py (remove superseded duplicate debug line),
ai-engine/behavioral/person_activity.py, ai-engine/vision/stream_manager.py,
backend/.env, backend/tests/unit/test_person_activity.py,
backend/tests/unit/test_behavior_overlays.py, scripts/collect_activity_diagnostics.py,
and this report. No frontend rebuild is required for a server-rendered JPEG panel.

Regression coverage includes General Entrance and Classroom state snapshots,
diagnostics not advancing rules/consuming alerts, one-track overlay/debug-off
gating, QR identity, existing behavior overlays, retired zigzag and stream recovery.
Final focused result: **80 passed**.

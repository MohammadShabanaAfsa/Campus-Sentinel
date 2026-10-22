# Classroom activity routing — 13 October 2026

The existing database `camera.zone_type` controls routing. StreamManager reads
the role when opening its camera loop and includes it in each internal tracks
message. BehaviorAgent skips and removes crowd/loitering analyzers for the
`classroom` role; other roles retain their previous analysis path. The legacy
Celery behavioral-analysis entry point also checks camera role before creating
either disabled analyzer. No duplicate activity pipeline was added.

Classroom retains sleeping, talking, phone use, eating, running, sudden
acceleration and restricted-area detection. Its classroom monitor retains
Missing Students, Low Class Attention, Faculty Engagement and CAI.

Execution path:

- `ai-engine/vision/stream_manager.py`: YOLO, existing tracking, shared person
  activity sampling/analysis, behavior snapshots, clean renderer, alert router.
- `ai-engine/classroom/classroom_monitor.py`: creates and shares its sleeping
  and talking state with the person activity analyzer; runs classroom metrics.
- `ai-engine/classroom/student_state.py`: sleeping and talking detector state.
- `ai-engine/behavioral/person_activity.py`: invokes the shared sleeping/talking
  rules and confirms phone use/eating with the existing track ID.
- `agents/behavior_agent/agent.py`: always invokes `_run_movement` and
  `_run_zones`; creates neither loitering nor crowd analyzer for Classroom.
- `ai-engine/behavioral/movement.py`: running and sudden acceleration.
- `ai-engine/behavioral/zone_checker.py`: restricted-area rules.

StreamManager additionally filters disabled Classroom results before rendering
and alert routing, protecting against stale Redis snapshots. This covers all
outputs of the skipped crowd analyzer, including crowd formation. General
Entrance does not use this suppression filter. Existing thresholds, identity,
activity rules and alert deduplication remain unchanged. No black debug panel
is drawn and `ACTIVITY_DEBUG=false` remains set.

137 selected regression tests passed. These include person-activity and eating
rules, general crowd/loitering confirmation, surge regression tests, explicit
assertions that Classroom never calls the disabled analyzers, movement/zone
execution, legacy task gating, and Classroom camera-loop tests that inject old
crowd/loitering snapshots and verify no labels or alerts escape the filter.

Native backend was reloaded. General Entrance is online and its fresh Redis
state reports `zone_type=general`, `crowd_loitering_enabled=true`.
Classroom currently has no frames and reports
`Camera source unreachable: connection timed out`. Live Classroom activities
could not be demonstrated; its routing and detector paths are verified by
inspection and controlled pipeline tests. No phone URL was changed.

Files changed:

- `agents/behavior_agent/agent.py`
- `ai-engine/vision/stream_manager.py`
- `backend/app/services/tasks/ai_tasks.py`
- `backend/tests/unit/test_loitering_crowd.py`
- `backend/tests/unit/test_behavior_overlays.py`
- `docs/CLASSROOM_ACTIVITY_ROUTING.md`

Runtime evidence: `logs/qr-identity-classroom-policy.json`.

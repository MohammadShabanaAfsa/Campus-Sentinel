# Campus Sentinel final software stabilization ? 2026-10-21

Software regression checks pass. General Entrance is online. Classroom remains unreachable at its existing configured URL and is retrying; no replacement URL or fallback camera was introduced.

## Verification results

| Check | Result | Method |
|---|---|---|
| Backend unit tests | 344 passed | UNIT TEST, synthetic landmarks/tracks/clocks |
| Backend integration tests | 7 passed | Synthetic stream/tracker/annotator integration |
| Full backend suite | 351 passed, 0 failed | `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` with DEBUG=false |
| Frontend tests | 40 passed, 0 failed | `npm --prefix frontend test` |
| Production frontend build | Passed compilation, lint, type checks, all 14 static pages | `npm run build`, NEXT_BUILD_DIR=.next-stabilization-final |
| Actual alert delivery | 15 types, 17 stored/published/received alerts | SYNTHETIC events through real Celery broker + isolated worker, PostgreSQL, Redis, WebSocket |
| Actual browser dashboard | All 15 labels rendered in served production dashboard | Headless Edge with real authentication and WebSocket |
| Fixture cleanup | Passed; no test cameras/alerts retained | Database deletion, dashboard deletion messages, test result/queue/outbox cleanup |
| Vehicle SQL persistence/outbox recovery | Passed against actual PostgreSQL and Redis | Isolated inactive fixture cameras |
| Native services | Backend healthy, frontend HTTP 200, Redis PONG, Celery PONG | LIVE health only |

All alert types validated: SLEEPING, TALKING, PHONE USE, EATING, RUNNING, SUDDEN ACCELERATION, LOITERING, RESTRICTED AREA PROHIBITED, FALL DETECTED, CROWD DENSITY, CROWD SURGE, SUSPECTED FIGHT, ABANDONED BAG, AFTER-HOURS PRESENCE, EMERGENCY EXIT BLOCKED.

The delivery run used two temporary inactive fixture cameras, a unique Celery validation queue and temporary worker. Outbound notifications were disabled only in that worker. Repeated delivery of the same episode was blocked; a new episode within the old cooldown window and an independent camera were accepted. The normal worker remained running. No physical actions were requested or simulated detections inserted into real camera histories.

## Root causes and fixes

1. Vehicle totals lived only in capture-session memory. Daily PostgreSQL totals now restore after reconnect, restart, and backend restart. A unique crossing ledger makes retries idempotent. A Redis outbox recovers crossings after a controlled database outage/restart. Writes occur on crossing changes; reads occur on initialization/date rollover, not every frame. Daily boundaries use Asia/Kolkata. First observation after restart establishes a fresh crossing baseline rather than fabricating a crossing.
2. Global type/track cooldown could suppress a legitimate new episode. Confirmed events now carry unique episode IDs. Deduplication is camera/type/subject/episode scoped; same active episodes remain quiet, while clear/reconfirm creates a new ID. Fight pairs, bags, and exit zones retain independent scopes. Existing restricted-zone episode IDs and overlap logic are preserved. Legacy non-episode producers retain bounded cooldown protection.
3. Fight-pair/exit events could collapse into a single camera-type entry before alert routing. Confirmed snapshots preserve their independent scopes. Fight overlays can combine participant IDs into a camera-level banner.
4. A Redis subscription failure could permanently stop realtime delivery. The listener now closes failed subscriptions and resubscribes with bounded backoff. On resubscription it requests frontend resynchronization. Frontend reconnect/resync retrieves active alerts from PostgreSQL-backed APIs and merges by ID.
5. Temporary validation alerts could remain in client memory after database cleanup. A deletion event removes the matching row without clearing unrelated alerts. Both store/rendering tests and actual browser receipt cover cleanup.
6. Classroom capture restart retained attendance/low-attention/engagement timers. Restart now clears only that camera's transient classroom analytics state; configuration and other cameras remain intact.
7. Loitering could retain elapsed time across an excessive observation gap without an explicit empty sample. A gap beyond three seconds now resets the candidate. Tests simulate continuous samples for duration checks rather than assuming unobserved minutes count as presence.
8. Predicted stale tracks could retain person overlays. Stale track boxes/labels are excluded from production annotation while detector state can retain its configured grace.
9. Two simultaneous camera startups could each construct the same YOLO singleton. Initialization is now locked. Eight concurrent callers are tested to receive one model instance; final native startup logged exactly one YOLO model load.
10. Default explanation contribution weights summed to 0.8 for a threat score of 0.5. Default relative contributions now normalize to one; explicit contributions remain untouched.
11. Five baseline test failures used obsolete risk bands/restricted-label wording or a wall-clock-dependent fixed October 2 fixture. Tests now use canonical existing risk bands, the existing PROHIBITED label, and a mocked clock. CSI production calculation and restricted overlap behavior were not changed.
12. Celery now explicitly enables broker startup retry, resolving its startup retry deprecation warning.

Classroom already had bounded native network open/read timeouts, same-source retry, restart joins and a per-camera start lock. Added recovery tests confirm timeout followed by successful connection uses the same camera ID/source and no Entrance substitution. Its remaining connectivity failure is environmental rather than replaced with a fabricated working feed.

## Camera-by-camera checklist

[x] means verified by unit test/simulation/integration plus inspected routing. It does not mean the physical behavior was demonstrated live. [N/A] indicates intentional role/configuration exclusions. Classroom has no current live frame.

| Feature | General Entrance | Classroom |
|---|---|---|
| SLEEPING | [x] UNIT/SIM + routing | [x] UNIT/SIM + routing |
| TALKING | [x] UNIT/SIM + routing | [x] UNIT/SIM + routing |
| PHONE USE | [x] UNIT/SIM + routing | [x] UNIT/SIM + routing |
| EATING | [x] UNIT/SIM + routing | [x] UNIT/SIM + routing |
| RUNNING | [x] UNIT/SIM + routing | [x] UNIT/SIM + routing |
| SUDDEN ACCELERATION | [x] UNIT/SIM + routing | [x] UNIT/SIM + routing |
| RESTRICTED AREA PROHIBITED | [x] UNIT/SIM + routing | [x] UNIT/SIM + routing |
| FALL DETECTED | [x] UNIT/SIM + routing | [x] UNIT/SIM + routing |
| SUSPECTED FIGHT | [x] UNIT/SIM + routing | [x] UNIT/SIM + routing |
| ABANDONED BAG | [x] UNIT/SIM + routing | [x] UNIT/SIM + routing |
| QR identity persistence | [x] UNIT/SIM + routing | [x] UNIT/SIM + routing |
| LOITERING | [x] UNIT/SIM + routing | [N/A] intentionally disabled |
| CROWD DENSITY | [x] UNIT/SIM + routing | [N/A] intentionally disabled |
| CROWD SURGE | [x] UNIT/SIM + routing | [N/A] intentionally disabled |
| MISSING STUDENTS | [N/A] classroom only | [x] UNIT/SIM + routing |
| LOW CLASS ATTENTION | [N/A] classroom only | [x] UNIT/SIM + routing |
| FACULTY ENGAGEMENT | [N/A] classroom only | [x] UNIT/SIM + routing |
| CAI | [N/A] classroom only | [x] UNIT/SIM + routing |
| AFTER-HOURS PRESENCE | Rule [x] UNIT/SIM; currently [N/A] schedule disabled | Rule [x] UNIT/SIM; currently [N/A] schedule disabled |
| EMERGENCY EXIT BLOCKED | Rule [x] UNIT/SIM; currently [N/A] no exit polygon saved | Rule [x] UNIT/SIM; currently [N/A] no exit polygon saved |
| VEHICLE IN / OUT / TOTAL | Rule [x] UNIT/SIM; currently [N/A] no counting line saved | Rule [x] UNIT/SIM; currently [N/A] no counting line saved |
| Vehicle daily persistence | [x] UNIT/SIM/integration | [x] UNIT/SIM/integration |
| Alert episode isolation | [x] UNIT/SIM/integration | [x] UNIT/SIM/integration |
| Redis / WebSocket / dashboard delivery | [x] UNIT/SIM/integration | [x] UNIT/SIM/integration |
| Reconnect handling | [x] UNIT/SIM/integration | [x] UNIT/SIM/integration |
| LIVE frame delivery | [x] 640 x 480 JPEG, running | [ ] network timeout, retrying |

Routing uses camera ID and zone_type. Person activities, movement, fall, fight, bag and QR remain supported on both roles. General Entrance does not instantiate classroom analytics. Classroom still excludes crowd and loitering. Schedules and exit polygons remain opt-in; neither camera currently has these configured, and neither has a counting line. Software geometry tests cover normalized restricted polygons, vehicle lines and emergency exits: Draw/Save/Edit/Clear, authentication expiry and unavailable-frame handling.

## Database changes

Additive, idempotent migration: `backend/migrations/001_vehicle_daily_counts.sql`.

- `vehicle_daily_counts`: camera_id, count_date, in_count, out_count, total_count, updated_at; composite camera/date primary key and nonnegative/total constraints.
- `vehicle_crossings`: unique event_id, camera_id, count_date, direction; makes retried crossing persistence idempotent.
- Both tables have camera foreign keys with cascade cleanup. Existing records and schemas are otherwise preserved.
- Applied to the current PostgreSQL database and included in fresh-install init SQL. Backend startup also applies the additive migration for existing installations. Standalone command: `backend/.venv/Scripts/python.exe scripts/migrate_vehicle_counts.py`.

## Final native observation and performance

- General Entrance: running; decoded 640 x 480 JPEG delivery; **3.246 processed FPS** measured from StreamManager.frames_processed over 12.015 seconds. FRAME_SKIP=3. This is processed FPS, not source frame-number progression.
- Classroom: reconnecting; `Camera source unreachable: connection timed out`; FPS unavailable. The configured URL was preserved.
- Final sampled frame contained zero active detections/tracks. Model loading and the processing path are active; synthetic tests verify positive track/behavior paths. No positive physical behavior is claimed from an empty sampled scene.
- PostgreSQL/Redis/Celery/backend/frontend healthy. No fixture cameras remain.
- No inference passes were added. YOLO initialization reuse improved; MediaPipe instances, per-camera analyzers, Redis clients/config caches and pooled vehicle storage are reused. CPU utilization and busy-scene sustained throughput were not profiled.
- ACTIVITY_DEBUG=false. Person labels remain above the matching box, maximum two; group banners remain separate. No black diagnostic panel or diagnostic polygons are drawn.
- Production thresholds preserved: fight 4 s; fall 4 s; bag 45 s; loitering 300 s, radius 0.05, track-loss grace 3 s. No ZIGZAG reintroduced. QR recognition and activity confirmation thresholds were not changed.

## Failure classification and limitations

- Baseline six failing backend tests: **fixed** (five stale/flaky test expectations and one default-weight defect).
- Final failed tests: **none**; no skipped failing tests were hidden.
- Classroom camera timeout: **environment-dependent**, unresolved connectivity. Automatic same-source recovery is verified by mocks. A reachable phone/network source is needed for live frame delivery; no physical behavior demonstration is requested.
- Real-world activity sensitivity/false-positive rates, staged fight/fall/bag/vehicle crossing quality, crowded-scene throughput and long-duration physical loitering remain **NOT LIVE VERIFIED**. All requested behavior rules have deterministic software verification.
- No counting line/schedule/exit zone is currently configured. Those camera features cannot produce corresponding real scene output until configured; their software rules and persistence/geometry paths pass tests.
- Events/vehicles hidden while a camera is offline cannot be reconstructed without footage. Total persistence prevents losing already observed committed/queued crossings; it cannot count unobserved vehicles. Redis outbox recovery assumes Redis retains its data; simultaneous loss of both database and Redis data is outside this check.
- Realtime pub/sub is transient. Reconnect/resubscribe resynchronization recovers active database alerts; it does not reconstruct every intermediate resolved event while disconnected.

## Files changed

- `ai-engine/vision/detector.py`
- `ai-engine/vision/stream_manager.py`
- `ai-engine/vision/vehicle_counter.py`
- `ai-engine/vision/confirmed_alerts.py`
- `ai-engine/vision/behavior_overlay.py`
- `ai-engine/vision/frame_annotator.py`
- `ai-engine/behavioral/campus_events.py`
- `ai-engine/behavioral/loitering.py`
- `ai-engine/classroom/attendance.py`
- `ai-engine/classroom/classroom_monitor.py`
- `backend/app/main.py`
- `backend/app/core/celery_app.py`
- `backend/app/services/vehicle_counts.py`
- `backend/app/services/tasks/alert_tasks.py`
- `backend/migrations/001_vehicle_daily_counts.sql`
- `infrastructure/postgres/init.sql`
- `frontend/src/hooks/useRealtimeEvents.ts`
- `frontend/tests/dashboard-recovery.test.cjs`
- `backend/tests/unit/test_alert_episodes.py`
- `backend/tests/unit/test_vehicle_persistence.py`
- `backend/tests/unit/test_stabilization_recovery.py`
- `backend/tests/unit/test_classroom_metrics_regression.py`
- `backend/tests/unit/test_stream_recovery.py`
- `backend/tests/unit/test_loitering_crowd.py`
- `backend/tests/unit/test_csi.py`
- `backend/tests/unit/test_phase3.py`
- `backend/tests/unit/test_retired_zigzag.py`
- `scripts/migrate_vehicle_counts.py`
- `scripts/verify_stabilization_delivery.py`
- `scripts/verify_stabilization_health.py`
- `docs/FINAL_STABILIZATION_REPORT.md`

## Evidence and repeatable diagnostics

- `logs/stabilization-backend-tests.txt`
- `logs/stabilization-frontend-tests.txt`
- `logs/stabilization-delivery-report.json`
- `logs/stabilization-dashboard-events.json` ? received synthetic payloads, also consumed by frontend tests
- `logs/stabilization-health.json`
- `scripts/verify_stabilization_delivery.py` ? actual isolated Celery/DB/Redis/WebSocket/browser test with fixture cleanup
- `scripts/verify_stabilization_health.py` ? read-only camera/service/routing/processed-FPS observation

Production frontend is serving `.next-stabilization-final` on port 3000. Shared frontend build-isolation configuration was not modified. The existing root launcher retains its default-build freshness check and will rebuild its default output when needed. Existing camera URLs, restricted polygon coordinates, activity thresholds, CSI formula, map and QR data were preserved.

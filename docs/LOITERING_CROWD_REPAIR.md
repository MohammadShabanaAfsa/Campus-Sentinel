# Loitering and crowd repair — 13 October 2026

Implemented and loaded through the existing `./run` launcher with `ACTIVITY_DEBUG=false`. Both General Entrance and Classroom are online. PostgreSQL/Redis were reused; camera records, sources and schemas were not changed.

| Rule | Production settings | Confirmation and reset | Display / alert |
|---|---|---|---|
| LOITERING | 300 seconds; normalized movement radius 0.05 | Existing track ID, pixel center divided by actual frame width/height. Movement bounds cover the entire episode. Significant movement, missing/stale track, invalid position or backward timestamp restarts/clears the episode. | Person-level LOITERING label; one MEDIUM confirmation event. Remains MEDIUM during long episodes. |
| CROWD DENSITY | 20 valid active people | Count unique current track IDs; exclude stale, missing-ID and invalid-confidence entries. One alert on entry; three seconds below threshold rearm the episode. | Top camera banner such as `CROWD DENSITY - 24 PERSONS`; camera-level alert, never a person label. Existing medium/high density severities retained. |
| CROWD SURGE | >50% growth within 30 seconds; current count >5 | Five-second stable baseline, at least three supporting samples and three seconds of sustained growth. Three seconds of nonqualifying counts clear the episode. Reconnect/session change, backward timestamps and capture gaps >5 seconds reset history. | Top camera banner with current count; one HIGH alert per confirmed episode. |

`LOITERING_DEBUG_THRESHOLD_SECS=10` is used only when `ACTIVITY_DEBUG=true`. Production mode continues to use `LOITERING_THRESHOLD_SECS=300`. Tests use simulated timestamps rather than shortening the running application's thresholds or injecting live detections.

The configurable surge settings are `CROWD_SURGE_WINDOW_SECS`, `CROWD_SURGE_GROWTH_THRESHOLD`, `CROWD_SURGE_BASELINE_SECS`, `CROWD_SURGE_CONFIRM_SECS`, `CROWD_SURGE_MIN_SAMPLES`, `CROWD_EPISODE_CLEAR_SECS` and `CROWD_MAX_SAMPLE_GAP_SECS`. They are documented in `.env.example`.

The shared `BehaviorAgent` invokes both analyzers for every camera. Capture timestamps (`observed_at`) are passed to these rules instead of inferring elapsed time from a frame count. Crowd analyzers now reset with each camera stream session, alongside existing per-track analyzers. Missing Students, CAI, attention and other classroom metrics retain their existing classroom-only routing.

Confirmed overlay snapshots continue through the existing confirmation router, Celery alert task, PostgreSQL, Redis, WebSocket and dashboard store. The detector's edge state prevents repeated producer alerts, while active snapshots keep the label/banner visible. Existing Redis cooldown and dashboard alert-ID deduplication remain in place; rapid new episodes can still be suppressed by that existing cooldown.

Live checks:

| Camera | Result |
|---|---|
| General Entrance | Running; fresh 640×480 WebSocket JPEG and behavior state. Startup check approximately 0.99 processed FPS. Shared rules enabled; classroom metrics disabled. Checked behavior snapshot counted 0 active people and had no crowd events. Raw tracker payloads may also contain stale tracks. |
| Classroom | Running; fresh 1920×1080 WebSocket JPEG and behavior state. Startup check approximately 0.69 processed FPS. Shared rules and classroom metrics enabled. Checked behavior snapshot counted 1 active person and had no crowd events. |

These startup FPS readings are observations, not a controlled performance comparison. No real crowd was staged and no continuous 300-second stationary-person confirmation was performed in this turn. Positive confirmation, rearming, duplicate prevention and rendering were verified with isolated deterministic tests, not fabricated production alerts.

Validation: **25 new loitering/crowd tests passed; 73 focused behavior/overlay tests passed. Full backend unit and integration run: 216 passed, 5 failed.** The five failures are the previously observed CSI tests: fixed expired event dates, three legacy score-to-level boundary expectations, and explanation contributions expecting 1.0 versus existing 0.8. CSI code was left unchanged. Existing sleeping/talking, phone/eating, QR, tracker, clean overlay and stream integration regressions passed.

Files changed in this loitering/crowd task:

- `ai-engine/behavioral/loitering.py`
- `ai-engine/behavioral/crowd.py`
- `agents/behavior_agent/agent.py`
- `ai-engine/vision/frame_annotator.py` — HUD person count excludes stale tracks; existing clean labels and camera banner layout retained.
- `backend/app/core/config.py`
- `.env.example`
- `backend/tests/unit/test_loitering_crowd.py`
- `backend/tests/unit/test_behavioral.py`
- `backend/tests/unit/test_complete_pipeline.py`
- `docs/LOITERING_CROWD_REPAIR.md`

Runtime evidence: `logs/loitering-crowd-live-verification.json`, `logs/behavior-overlay-verification.json` and `logs/loitering-crowd-startup.out.log`. The app remains running at http://localhost:3000.

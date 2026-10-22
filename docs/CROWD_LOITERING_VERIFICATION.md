# Crowd and loitering verification — 13 October 2026

Crowd density now uses five active, unique, non-stale person tracks per camera.
Four people do not confirm density; five or six do. Density remains a single
camera-level banner, with a count-bearing dashboard alert on episode entry.
Existing crowd surge and formation detection logic is unchanged.

Loitering uses normalized person center coordinates, actual capture timestamps,
the persistent track ID, a 300-second duration and a 0.05 movement bound.
Previously one missing or stale track sample deleted the timer immediately.
It now preserves state through a three-second disappearance grace. Longer loss
resets state, including when the next observation directly returns after grace.
Movement outside the bound resets the timer and clears confirmation. Confirmed
loitering is a MEDIUM person-level event. Existing alert transition and cooldown
mechanisms suppress per-frame duplicates.

73 crowd/loitering, complete-pipeline and overlay tests passed. Tests include
both camera paths, 4/5/6 density boundaries, stale and duplicate exclusion,
stationary confirmation at 300 seconds, movement reset, short/long track loss,
single alerts, camera banner versus person-label separation, and unchanged surge
regressions. Test timestamps verify duration without waiting five wall-clock
minutes or lowering the production threshold.

Native backend was reloaded. General Entrance is online with one active person,
so no density confirmation is expected. No live 300-second stationary test was
performed. Classroom currently reports `Camera source unreachable: connection
timed out` for its existing phone source; its live verification is unavailable.
Both cameras use the same updated analyzers. No camera source was changed.
`ACTIVITY_DEBUG=false` remains set.

Files changed:

- `ai-engine/behavioral/loitering.py`
- `ai-engine/vision/confirmed_alerts.py` (density alert title includes count)
- `backend/app/core/config.py`
- `.env`
- `backend/.env`
- `.env.example`
- `backend/tests/unit/test_loitering_crowd.py`
- `docs/CROWD_LOITERING_VERIFICATION.md`

Runtime evidence: `logs/qr-identity-crowd-loitering.json`.

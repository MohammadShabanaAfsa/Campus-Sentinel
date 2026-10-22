# Restricted-zone hit test — 13 October 2026

Stored normalized polygons and the existing episode/deduplication fix remain
unchanged. Only restricted-zone reference geometry and its display label changed.

Settings:

```dotenv
RESTRICTED_ZONE_FOOT_TOLERANCE=0.05
RESTRICTED_ZONE_REFERENCE_POINT=FOOT_POINT
```

Tolerance is validated between 0 and 0.10. Modes are FOOT_POINT or
LOWER_BODY_POINT. FOOT_POINT is bbox bottom-center. LOWER_BODY_POINT is bbox
center X and `y1+0.90*(y2-y1)`. Both normalize using actual source dimensions.
Hit testing first checks the exact reference point, then a short vertical segment
upward by the configured tolerance. There is no horizontal tolerance or polygon
enlargement. Other uses of point-in-polygon, including emergency-exit monitoring,
keep their original exact behavior.

General Entrance uses a camera-specific override in existing `cameras.config`:
`restricted_zone_reference_point=LOWER_BODY_POINT`. Its tolerance is 0.05.
Other cameras retain the configured default FOOT_POINT mode. Camera ID, source,
stored polygons and other camera config fields were preserved.

Confirmed person labels now read **RESTRICTED AREA PROHIBITED**. On every
processed frame, only this cached label is rechecked against the current box and
removed immediately when its reference point exits the tolerant area; it does
not wait for the cached behavior snapshot to expire. Normal behavior analysis
continues to manage the existing entry episodes and HIGH alert path unchanged.

## Verification

221 selected backend tests passed. Added cases cover exact inside, just below
within tolerance, farther below tolerance, no sideways tolerance, unchanged
polygon data, lower-body reference and no repeated alert within an episode.
Existing entry/re-entry, duplicate delivery, source scaling, wrong camera and
other activity regression tests continue to pass.

Two current-footage checks were performed on General Entrance without moving or
enlarging the polygon or injecting detections. Initial tolerant FOOT_POINT test
had one usable sample and no hit. At that X, the local polygon boundary was more
than 0.05 above the foot, even though the polygon's maximum Y was close enough
at another X. General Entrance was then configured to LOWER_BODY_POINT as the
user's requested alternative and tested for another 45 seconds.

| Final live check | Result |
|---|---|
| Reference | LOWER_BODY_POINT |
| Vertical tolerance | 0.05 |
| Diagnostic samples | 44 |
| Inside samples | 0 |
| Overlay frames | 0 |
| Alerts saved in PostgreSQL | 0 |
| Redis/WebSocket restricted alerts | 0 / 0 |
| New dashboard restricted alert | No; no entry confirmed |

Example sample: foot `(0.573163,0.998533)`; lower-body reference
`(0.573163,0.911824)`. The polygon's maximum X is 0.341356, so this sample is
outside horizontally regardless of vertical tolerance. The current footage
therefore cannot positively verify an entry/overlay/dashboard alert. The new
geometry behavior is confirmed in tests; a positive live check still needs an
actual reference point within the zone's horizontal extent.

Diagnostics were turned off after recording; `ACTIVITY_DEBUG=false` remains set.
The backend is left running with the requested General Entrance settings.
Evidence: `logs/restricted-zone-live/report.json`.

Files changed:

- `ai-engine/behavioral/zone_checker.py`
- `ai-engine/vision/behavior_overlay.py` (requested display wording)
- `ai-engine/vision/stream_manager.py` (restricted-label exit recheck only)
- `backend/app/core/config.py`
- `.env`, `backend/.env`, `.env.example`
- `backend/tests/unit/test_restricted_zone_alert_path.py`
- `backend/tests/unit/test_behavior_overlays.py`
- `docs/RESTRICTED_ZONE_HIT_TEST.md`

Database change: General Entrance's reference override in existing camera config;
no schema change and no alteration to polygon coordinates or alert deduplication.

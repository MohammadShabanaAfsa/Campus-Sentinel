# Restricted-zone bbox overlap — 13 October 2026

Restricted-zone violation now uses the person's entire bounding rectangle,
normalized using source frame width/height, and the saved normalized polygon.
Four-plane Sutherland–Hodgman clipping computes the intersection polygon; the
shoelace formula computes its area. Intersection area divided by bbox area must
reach `RESTRICTED_ZONE_MIN_OVERLAP_RATIO=0.05`. The same area test handles bbox
corners, crossing polygon edges, containment and simple concave polygons.
Tiny touches do not bypass the area threshold. No rasterization, image/model
inference or additional geometry package is required.

Saved polygon vertices, zone UI, camera sources, role routing, other activity
rules and existing entry-episode/deduplication code are unchanged. Legacy foot
reference/tolerance settings and the old camera-specific lower-body reference
are retained for compatibility but no longer control restricted violations.
The exact point-in-polygon function used by emergency-exit/schedule features
was not changed. Overlap ratios are source-resolution independent.

The clean person label remains **RESTRICTED AREA PROHIBITED**, with the existing
HIGH warning style. It is revalidated against the current bbox on every processed
frame and removed when overlap falls below threshold. Sustained overlap retains
the existing episode ID and produces no repeated alert. Exit and later re-entry
use the already implemented new episode ID. Severity configuration is preserved;
the active General Entrance zone is HIGH.

## Tests

**233 selected backend regression tests passed**, including 12 new overlap tests:
whole bbox outside; side, upper-body and lower-body overlap; corner and edge
intersections; tiny below-threshold overlap; 5% boundary; concave/disconnected
intersection and polygon winding; containment and scaling; degenerate bbox;
entry/stay/exit/re-entry on General Entrance and Classroom roles. Existing
restricted episode/cooldown, QR, activity, fall, vehicle, crowd, loitering and
unusual-event regressions passed.

## Live General Entrance result

A read-only observer was started before the backend reload so it could record
the first genuine entry, reconnect the authenticated WebSocket and monitor
Redis publication. It injected no detections or database alerts.

| Observation | Result |
|---|---|
| Threshold | 5% of bbox area |
| Inside samples | 25 |
| Observed overlap range | 15.8084–24.0328% |
| Overlay frames | 24 |
| PostgreSQL alerts during recording | 1, HIGH |
| Redis alert messages | 1 |
| Authenticated WebSocket alerts | 1 |
| Dashboard alert API | HTTP 200 for the same alert ID |
| Dashboard handler/store replay | Captured live event produces one HIGH row; repeated delivery stays one row |

The saved JPEG `logs/restricted-zone-overlap-live/frame-083.jpg` was inspected:
it displays UNKNOWN, RESTRICTED AREA PROHIBITED with the existing TALKING label,
and `#1 PERSON 0.91` above the associated box. The retained zone episode reports
`already_inside_no_duplicate` on subsequent samples.

Recorded alert ID: `b1e0bf3c-e09c-4041-9e3e-586bcdf68b4a`.
The actual user browser dashboard was not manually operated; dashboard delivery
was verified via its authenticated API and the actual frontend message handler
and store with the captured live WebSocket payload.

Classroom uses the same new restricted-overlap path but is currently offline at
its saved phone source, so live Classroom confirmation remains unavailable.
Diagnostic logging was disabled after testing and `ACTIVITY_DEBUG=false` remains
set. Normal backend reload resets track sessions as before; a still-overlapping
person on a new stream session can create that session's new entry episode.

This uses bbox area, which can include background around the body. Occlusion or
tracker box errors can affect the ratio. No body-segmentation claim is made.

Evidence:

- `logs/restricted-zone-overlap-live/report.json`
- `logs/restricted-zone-overlap-live/dashboard-api.json`
- `logs/restricted-zone-overlap-live/dashboard-store-verification.json`

Files changed:

- `ai-engine/behavioral/zone_checker.py`
- `ai-engine/vision/stream_manager.py` (same overlap test for label exit)
- `backend/app/core/config.py`
- `.env`, `backend/.env`, `.env.example`
- `backend/tests/unit/test_restricted_zone_overlap.py`
- `scripts/capture_restricted_zone_overlap_live.py`
- `docs/RESTRICTED_ZONE_BBOX_OVERLAP.md`

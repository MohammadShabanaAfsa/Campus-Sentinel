# Opt-in QR identity workflow

A student deliberately presents their roll-number QR. A successful decode is
looked up in the cached `student_face_list.xlsx` enrollment mapping, then assigned
to the existing person `track_id`. This is a QR presentation identity, not proof
of the person's biometric identity. No live face matching or embedding model runs.

The mapping includes `name` and the optional relative `face_file` profile reference.
Profile filenames containing absolute paths or parent traversal are omitted.
Photos are never opened by the camera QR decoder. The optional photo side panel
has not been added; metadata is available in the existing authenticated track
payload for a future profile display. Excel is loaded once per backend process.

## Lifetime and association

Identity has no elapsed-time or QR-visibility expiry. It survives while the same
track is current, including repeated QR-free frames. `QR_TRACK_GRACE_SECS=3.0`
allows brief detection loss; absence beyond that grace clears identity. The old
`QR_IDENTITY_TIMEOUT_SECS` setting is retained only for configuration compatibility.

Each camera owns a separate QR state instance. Camera restart/reconnect creates
a fresh instance. `QRIdentityTracker.reset(track_id)` clears one track, and
`reset()` clears all tracks. Reset cancels outstanding decoder results. A new
valid QR assigned to the same track replaces its previous identity; a repeated
presentation of the same QR preserves its original `identified_at`.

Assignment requires one unambiguous containing person box or an unambiguous
nearest box within the configured margin. Stale tracks, overlapping holders,
nearby ambiguous holders, conflicting codes and transfers from an existing
grace-protected owner are rejected. Async results retain their original track
ID and cannot be reassigned to another person's newer bounding box.

State contains `track_id`, `roll_no`, `name`, `face_file`, `identified_at`,
`last_seen`, and QR method/verification metadata. Existing Redis track snapshots
and WebSocket messages carry this state. No database migration is required.

## Overlay and alerts

The existing clean renderer draws identity, at most two confirmed activities,
then track/confidence directly above the associated box, with a top-inside
fallback. No activity debug table is drawn; `ACTIVITY_DEBUG=false` remains set.

Known person alerts use `PHONE USE — ROLLNO NAME`; unknown person alerts use
`PHONE USE — Person #TRACK_ID`. Known identity is also copied into existing
PostgreSQL alert metadata as `student_identity`, so historical alerts retain the
identity at confirmation. Existing transition deduplication and Redis cooldown
remain unchanged. Camera-wide alerts do not receive student identity.

## Verification on 13 October 2026

All 159 selected regression tests passed. Tests cover correct association, long persistence without QR, disappearance
grace, explicit reset, new camera session, valid replacement, protected ownership,
ambiguity rejection, real OpenCV decoding, clean two-activity overlay, alert
identity and duplicate suppression. Both general and classroom camera-loop
paths are exercised by pipeline tests. Activity, eating, crowd and loitering
regressions are included; their detector logic was not changed.

Native backend was reloaded and returned HTTP 200. The workbook loaded 16
identities and 16 profile references. General Entrance remained online with one
current person; no live QR was presented, so live identity remained UNKNOWN.
Classroom was offline before and after reload, with exact stream error:
`Camera source unreachable: connection timed out`. Live Classroom identification
could not be verified.

Short native frame-rate samples measured General Entrance at 1.3 processed FPS
before and 1.1–1.2 after reload. These brief samples include normal variation and
startup effects, and do not establish a causal slowdown. The change adds no
per-frame database/Excel/photo reads or face model inference; existing QR scan
cadence and worker isolation are preserved.

Runtime evidence: `logs/qr-identity-before.json`, `logs/qr-identity-after.json`,
and `logs/qr-identity-final.json`. Repeat the read-only check with:

```powershell
backend/.venv/Scripts/python.exe scripts/verify_qr_identity_runtime.py --label check
```

Files changed for this workflow:

- `ai-engine/identity/qr_identity.py`
- `ai-engine/vision/stream_manager.py`
- `ai-engine/vision/confirmed_alerts.py`
- `backend/app/core/config.py`
- `.env.example`
- `backend/tests/unit/test_qr_identity.py`
- `backend/tests/unit/test_complete_pipeline.py`
- `scripts/verify_qr_identity_runtime.py`
- `docs/QR_IDENTITY_WORKFLOW.md`

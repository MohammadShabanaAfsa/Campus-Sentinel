# Evidence-based activity input repair

Used the supplied track 1/frame 531 diagnostics as the baseline. Analyzer/model
instances already persisted; the repair targets lost inputs and premature state
cleanup. No sleeping duration, talking duration, eating cycle/window/visibility
threshold, phone-use timing, QR logic, alert dispatcher/cooldown or CSI rule was
changed.

## Sleeping and track loss

Before repair, PersonActivityAnalyzer deleted state whenever a track was absent
or time_since_update > 0, even though ByteTracker retained the same ID. The live
baseline showed zero detected people during head movement and repeated resets.

ACTIVITY_TRACK_GRACE_SECS=3 now preserves per-person memory across short losses.
Missing tracks contribute no new detection/activity events. State is deleted
after grace expires; it is never transferred to a different ID. The existing
tracker and QR cache are unchanged.

Sleeping additionally uses SLEEPING_LANDMARK_GRACE_SECS=3. An established candidate
pauses on missing EAR/head evidence, retains its start/state, and excludes the
unobserved interval from its duration. It cannot newly confirm during an unknown
sample. Visible open eyes immediately reset the candidate; longer missing periods
reset it too. The full 15-second default requirement remains. Classroom reset
explicitly clears old tracker state, while ordinary cleanup permits short gaps.

Tests cover pause/resume without counting missing time, longer-gap expiry, open-eye
reset, short track loss, cleanup and unchanged alert consumption. No live positive
sleeping trial was claimed; these temporal guarantees were verified with controlled
timestamps.

## Talking calibration

The user supplied labeled 20-second quiet and continuous-speaking periods. Quiet
capture had 24 valid MAR samples; speaking had 17. Analysis used track 4 in both
periods, excluding secondary track 10 and splitting history at sample-counter
restarts. It did not combine different identities/track runs or use mouth history
from before the labeled period.

| Phase | Track-4 samples | Continuous runs | Valid rule windows | Population MAR std range |
| --- | --- | --- | --- | --- |
| Quiet | 17 | 13, 4 | 6 | 0.003379–0.004107 |
| Speaking | 15 | 5, 1, 9 | 2 | 0.045732–0.048237 |

Variance is computed over 8..30 samples, matching the rule's population standard
deviation and warm-up. The **existing 0.035 threshold already separates the clean
windows**. It was retained; the eight-second confirmation duration remains.
TALKING_MAR_STD_THRESHOLD is now configurable. GENERAL_TALKING_MAR_STD_THRESHOLD
optionally overrides it for general cameras only; the active override is 0.035.
Classroom's value remains 0.035.

An initial pooled comparison suggested 0.014777. That comparison was corrected
to exclude track-loss boundaries, and that value is not active. Only two valid
speaking windows remain, so these short captures do not justify fitting a new
camera-wide threshold or claim reliable discrimination from yawning/eating.
The speaking capture instead supplies direct evidence that resets interrupted
mouth-history warm-up and sustained-duration confirmation.

Artifacts: logs/talking-calibration-quiet.json, talking-calibration-speaking.json,
talking-calibration-result.json and talking-calibration-distributions.json.

## Phone detection

COCO class 67 was retained already, but YOLO inference used conf=0.5 before the
post-filter. A phone scoring below that cutoff could never reach association.

YOLO_PHONE_CONFIDENCE_THRESHOLD=0.25 now controls phone candidates independently.
Full-frame inference uses the lower floor and post-filters class 67 at 0.25;
persons and every other retained class still use 0.5. Full-frame class options are
explicitly restored on every call because Ultralytics retains phone-only ROI
prediction options across calls.

At activity samples where no full-frame phone is found, an optional phone-only
inference uses enlarged, padded person ROIs for tracks with usable wrists and
two shoulders, preserves aspect ratio, maps results
back to full-frame coordinates and deduplicates overlapping ROI objects. It reuses
the existing model with a shared inference lock. At most two person ROIs are
processed, controlled by PHONE_ROI_MAX_PERSONS and PHONE_ROI_INFERENCE_ENABLED.
No new tracker is created. Phone detections remain excluded from person tracking.

Native replay of the user's real saved frame logs/phone-live-19.jpg detected
class 67 at **0.408076** and a person at 0.936874. The old 0.5 cutoff would discard
that phone. ROI replay returned no phone on that frame; no benefit is claimed for
that particular image. Exact results: logs/phone-saved-frame-inference.json.

The repaired live pipeline logged **19 phone-present samples** in the verification
capture, including full-frame phone confidence **0.604690** at frame 12, track 1.
There was no qualifying wrist association: no_near_raised_wrist, hit_count=0,
confirmed=false. Phone timing was not shortened to compensate for missing wrists.

## Pose/eating inputs

The old pose input was the complete YOLO person box, not a separate upper-body
crop, but it had no context/padding. ACTIVITY_POSE_CROP_PADDING=0.20 now expands
each side and clips to the frame. Mouth/wrist/shoulder geometry uses analysis_bbox
to map landmarks correctly; original person boxes and track IDs remain unchanged.
No landmarks from separate people are combined. Padding can include surrounding
people, so crowded-scene pose assignment still requires further validation.

Diagnostics now record original/padded boxes, clipping, pose availability and each
wrist/elbow/shoulder's visibility plus whether its coordinates are in the crop.
The original 0.6 landmark visibility requirement remains.

Example real repaired sample: padded box [6,28,600,480] versus original person box
[91.05,103.97,515.65,479.61]. Pose detected=true. Shoulder visibility was 0.998903
and 0.998947, with shoulder scale 236.70 pixels. Wrist visibility was 0.120639 and
0.235461, and both wrists were outside the crop. The padded crop already touches
the bottom of the 640x480 frame: padding cannot recover hands outside the video.
EATING remains unconfirmed with cycles=0/3; EATING_MIN_EVENTS was not reduced.
The phone/eating rules require the camera to show the relevant hands/arms.

## Verification and limits

- **85 focused tests passed**: grace, class-specific confidence, ROI/full-frame
  filter restoration, padded-coordinate mapping, existing activities, QR,
  overlays, retired zigzag and stream recovery.
- General Entrance delivered fresh 640x480 WebSocket JPEGs after repair. The live
  initial ROI sample measured 1.19 processed FPS. After limiting ROI work to
  usable hand/shoulder inputs, the final live sample measured **1.68 FPS**, with a
  0.3-second fresh-frame age. ROI inference adds CPU work; these rates are lower
  than an earlier 2.48 FPS diagnostic sample and is not a controlled performance
  benchmark. The optional bounded ROI path can be disabled if its cost is unsuitable.
- Classroom's existing source http://192.168.1.10:8080/video was unavailable during
  this verification (failed to open/reconnecting; final check: No frames received). Its controlled pipeline tests
  passed; no current live Classroom positive activity trial is claimed.
- Positive live phone detection is verified. Phone-use association, eating and
  sleeping confirmation remain contingent on actual visible temporal evidence.
- Final native backend log: logs/backend-input-repair-ready.err.log. Earlier live phone
  evidence is preserved in logs/backend-activity-repair-final.err.log and
  logs/activity-repair-final-live.json. Activity debug remains enabled.

Changed files: backend/app/core/config.py, backend/.env, .env.example,
ai-engine/classroom/student_state.py, ai-engine/classroom/classroom_monitor.py,
ai-engine/classroom/face_pose_analyzer.py, ai-engine/behavioral/person_activity.py,
ai-engine/vision/detector.py, ai-engine/vision/stream_manager.py,
backend/tests/unit/test_person_activity.py, backend/tests/unit/test_behavior_overlays.py,
and this report. Backend was restarted to load the repair; frontend, Celery,
Redis/PostgreSQL, camera sources and QR settings were not changed.

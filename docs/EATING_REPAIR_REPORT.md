# Eating-only repair — 13 October 2026

The eating state-machine and input-filter fixes are implemented and tested. Production settings remain **NEAR ≤0.70, AWAY ≥0.85, three completed cycles within 20 seconds**. The backend was reloaded in clean mode with `ACTIVITY_DEBUG=false` and `EATING_DEBUG=false`.

You selected **“Use saved frames for now.”** Both saved camera sequences were replayed with real MediaPipe inference and their recorded track IDs, stream sessions and timestamps. Neither sequence contains three fully observable completed cycles. They counted **0 cycles**, emitted **0 EATING confirmations**, and calculated **0 local alert transitions**. No live or database alerts were injected. A fresh live three-cycle confirmation remains unverified.

## Why it was failing and what changed

1. **Near-contact timing included withdrawal.** The old check measured from the first NEAR observation until AWAY. A one-second contact followed by a slow sideways withdrawal could exceed the existing three-second contact limit and be rejected. Near dwell now closes at the observed LEAVING phase; subsequent travel to AWAY does not extend that dwell. The existing minimum/maximum contact durations are retained.
2. **Selection could favor a more visible stationary hand.** Left and right hand states now advance independently. Actual normalized-distance motion selects the moving hand, with continuity during its contact. Visibility remains an acceptance requirement and a fallback ranking criterion. Selection never gates processing of the other usable hand.
3. **One slow missing sample could exceed the grace budget.** Eating's 1.5-second base grace now adapts to sampling cadence, bounded at three seconds. Unknown time is excluded from the contact timer starting at the last valid observation. Completed cycle history survives a short landmark interruption. A prolonged interruption clears the incomplete hand phase.
4. **Eating's wrist cutoff was not consistently applied.** Eating was configured for visibility 0.50, but the base shared pose output filtered wrists at 0.60. The pose analyzer now exports additional raw wrist candidates from its existing inference. Only eating reads those candidates using its existing 0.50 cutoff. The filtered wrist map consumed by PHONE USE remains unchanged, and no extra model inference is added.
5. **The archived clips lack the required visible returns.** General Entrance starts at NEAR without an observed initial AWAY, later records an AWAY, then NEAR followed by unavailable/out-of-crop wrists. Classroom records AWAY → NEAR without a subsequent visible AWAY. Preserving a candidate cannot supply an unobserved return.

## State and safeguards

Each hand has independent `AWAY → APPROACHING → NEAR_MOUTH → LEAVING → AWAY` state. Distances are full-frame wrist-to-mouth distances divided by visible shoulder width. The 0.70–0.85 band preserves the contact/withdrawal episode and does not count a cycle. Repeated NEAR observations do not create repeated cycles. A cycle requires an observed initial AWAY, qualifying contact and an observed return to AWAY.

One usable wrist suffices. An unavailable wrist does not complete a cycle. Out-of-crop wrist evidence invalidates an interrupted withdrawal; returning after that loss cannot manufacture a cycle. Short missing input can resume an already observed LEAVING phase when a valid AWAY is subsequently seen, or resume NEAR with unknown time excluded.

`EATING_TEST_MIN_CYCLES=1` remains diagnostic-only. The replay reports whether that test count was reached; it never changes the production three-cycle rule or produces a one-cycle production label.

`EATING_DEBUG=true` enables eating-only logs containing selected hand, wrist visibility, normalized distance, phase and completed cycles, with camera/track IDs for context. It does not enable the black panel or log phone, EAR/MAR or other detector diagnostics. Final mode leaves this flag false.

## Measured saved-frame results

Duplicate frame IDs were skipped. These are fresh inferences on archived camera JPEGs, not a new live capture.

| Measurement | General Entrance | Classroom |
|---|---:|---:|
| Current-person samples replayed | 19 | 17 |
| Mouth reference available | 18/19 | 15/17 |
| Both shoulders available | 19/19 | 17/17 |
| Accepted left wrist | 0/19 | 0/17 |
| Accepted right wrist | 11/19 | 4/17 |
| Accepted wrist Pose visibility | 0.747–0.974 | 0.752–0.950 |
| Normalized wrist-mouth distance | 0.453–0.948 | 0.570–1.005 |
| Selected hand when usable | Right | Right |
| Observed phases | NEAR / AWAY / unavailable | AWAY / NEAR / unavailable |
| Completed cycles | 0 | 0 |
| EATING confirmations | 0 | 0 |

The complete five-phase sequence, slow withdrawal, one full cycle and three-cycle confirmation were verified in deterministic tests. The archived sequences did not capture the complete three-cycle motion with usable input at every required boundary.

## Tests and alert behavior

**17 new eating tests passed**, alongside 45 existing person-activity tests. The final complete backend unit/integration run reported **233 passed, 5 failed**. The five failures are the pre-existing CSI tests: fixed expired event dates, three legacy score-level expectations, and explanation contributions expecting 1.0 instead of existing 0.8. CSI implementation was left unchanged.

Tests cover one cycle, incomplete contact, short/long landmark loss, out-of-frame rejection, hysteresis, slow LEAVING, independent hands, a lower-visibility moving hand, stationary near-mouth contact, preserved completed history, the 20-second window, the one-cycle diagnostic setting, and unchanged phone wrist inputs/model call count. Three completed cycles produce the existing LOW `eating` event; repeated confirmed snapshots produce only one alert transition through the unchanged confirmation router. Existing overlay tests pass and retain the clean EATING label above the corresponding box.

No fresh live LOW eating alert or visible production EATING label was demonstrated in this turn. A reliable new recording must begin with a visible sideways AWAY position and keep the wrist visible through each return, repeating three times.

## Files changed

- `ai-engine/behavioral/person_activity.py` — eating geometry, hand phases, timing, grace, selection and eating-only logs.
- `ai-engine/classroom/face_pose_analyzer.py` — data-only raw wrist candidate export; existing filtered outputs and model calls preserved.
- `backend/app/core/config.py` — eating-only diagnostic flag and bounded maximum landmark grace.
- `.env.example` — documents those eating settings.
- `backend/tests/unit/test_eating_state_machine.py` — 17 focused tests.
- `backend/tests/unit/test_person_activity.py` — correct missing-time expectation.
- `scripts/replay_eating_frames.py` — eating-only saved-frame replay; no PostgreSQL/Redis writes or live alert dispatch.
- `docs/EATING_REPAIR_REPORT.md` — this report.

Evidence: `logs/phone-eating-repair/eating-only-replay-entrance.json` and `eating-only-replay-classroom.json`. Replay command: `backend/.venv/Scripts/python.exe scripts/replay_eating_frames.py --camera entrance` (or `--camera classroom`).

PHONE USE, sleeping/talking rules, movement, loitering/crowd, QR, CSI, camera routing and alert architecture were not changed in this task. Frontend, Celery, PostgreSQL and Redis were retained during backend reloads.

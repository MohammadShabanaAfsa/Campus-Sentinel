"""
Per-student state detectors — Sleeping and Talking — driven by MediaPipe
Face Mesh signals (eye-aspect-ratio, mouth-aspect-ratio) sustained over time.
Mirrors the LoiterState pattern in ai_engine.behavioral.loitering: one state
machine per track_id, alerting once when a sustained condition is first met.
"""
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from loguru import logger

EAR_CLOSED_THRESHOLD = 0.20      # below this, eyes are considered closed
MAR_TALKING_STD_THRESHOLD = 0.035  # mouth-shape variability indicating speech
MAR_HISTORY_WINDOW = 30           # samples kept per track for variance calc


@dataclass
class _SleepState:
    track_id: int
    closed_since: Optional[float] = None
    alerted: bool = False
    last_valid_at: Optional[float] = None
    paused_at: Optional[float] = None
    excluded_secs: float = 0.0

    def duration_closed(self, now: float) -> float:
        endpoint = self.paused_at if self.paused_at is not None else now
        return max(0.0, endpoint-self.closed_since-self.excluded_secs) if self.closed_since is not None else 0.0


@dataclass
class _TalkState:
    track_id: int
    mar_history: List[float] = field(default_factory=list)
    talking_since: Optional[float] = None
    alerted: bool = False
    last_valid_at: Optional[float] = None
    paused_at: Optional[float] = None
    excluded_secs: float = 0.0


class SleepingDetector:
    """Flags a student as sleeping once eyes-closed / head-down persists
    beyond the configured threshold."""

    _instances: Dict[str, "SleepingDetector"] = {}

    def __init__(self, camera_id: str, threshold_secs: float = 15.0, landmark_grace_secs: float = 3.0):
        self.camera_id = camera_id
        self.threshold_secs = threshold_secs
        self._states: Dict[int, _SleepState] = {}
        self.diagnostics = {}
        self.landmark_grace_secs = landmark_grace_secs
        self.ear_threshold = EAR_CLOSED_THRESHOLD
        self._missing_since = {}

    @classmethod
    def get_instance(cls, camera_id: str, threshold_secs: float = 15.0) -> "SleepingDetector":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id, threshold_secs=threshold_secs)
        return cls._instances[camera_id]

    def update(self, track_id: int, face_signals: Dict) -> Dict:
        """
        Feed one frame's face signals for a track. Returns
        {is_sleeping_candidate, is_sleeping, duration_secs} for this instant.
        """
        now = time.time()
        if track_id not in self._states:
            self._states[track_id] = _SleepState(track_id=track_id)
        state = self._states[track_id]

        eyes_closed = face_signals.get("ear") is not None and face_signals["ear"] < self.ear_threshold
        head_down = bool(face_signals.get("head_down"))
        # Either sustained eyes-closed (drowsy) or a bowed head with no visible
        # face (asleep on the desk) counts as a "closed" instant.
        candidate = eyes_closed or (head_down and not face_signals.get("face_detected"))
        unknown = face_signals.get('ear') is None and not candidate
        reset_reason = None

        if unknown and state.closed_since is not None:
            if state.paused_at is None:
                state.paused_at = state.last_valid_at if state.last_valid_at is not None else now
            if now-state.paused_at <= self.landmark_grace_secs:
                reset_reason = 'landmarks_missing_grace_paused'
            else:
                state.closed_since = None
                state.paused_at = None
                state.excluded_secs = 0.0
                state.alerted = False
                reset_reason = 'landmark_grace_expired'

        if candidate:
            if state.paused_at is not None:
                if now-state.paused_at > self.landmark_grace_secs:
                    state.closed_since = None
                    state.excluded_secs = 0.0
                else:
                    state.excluded_secs += now-state.paused_at
                state.paused_at = None
            if state.closed_since is None:
                state.closed_since = now
            state.last_valid_at = now
        elif not unknown:
            state.closed_since = None
            state.paused_at = None
            state.excluded_secs = 0.0
            state.alerted = False

        duration = state.duration_closed(now)
        is_sleeping = candidate and duration >= self.threshold_secs
        result = {"is_sleeping_candidate": candidate, "is_sleeping": is_sleeping, "duration_secs": duration}
        self.diagnostics[track_id] = {**result, "sample_time": now, "face_landmarks_available": bool(face_signals.get("face_detected")),
            "ear": face_signals.get("ear"), "head_down": face_signals.get("head_down"), "candidate_start_time": state.closed_since,
            "reset_reason": reset_reason or (None if candidate else ("face_landmarks_missing_and_no_head_down" if not face_signals.get("face_detected") else "eyes_not_closed_and_no_qualifying_head_down")),
            "paused": state.paused_at is not None, "excluded_gap_secs": state.excluded_secs}
        return result

    def consume_alert(self, track_id: int) -> bool:
        """Returns True exactly once per continuous sleeping episode (edge-triggered)."""
        state = self._states.get(track_id)
        if state is None or state.alerted:
            return False
        state.alerted = True
        return True

    def cleanup(self, active_track_ids: set, force=False):
        for tid in list(self._states.keys()):
            if tid not in active_track_ids:
                missing = self._missing_since.setdefault(tid,time.time())
                if not force and time.time()-missing<=self.landmark_grace_secs:
                    continue
                del self._states[tid]
                self.diagnostics.pop(tid, None)
                self._missing_since.pop(tid,None)
            else:
                self._missing_since.pop(tid,None)


class TalkingDetector:
    """Flags a student as talking once mouth-shape variability (speech-like
    movement) is sustained beyond the configured threshold."""

    _instances: Dict[str, "TalkingDetector"] = {}

    def __init__(self, camera_id: str, threshold_secs: float = 8.0, mar_std_threshold: float = MAR_TALKING_STD_THRESHOLD):
        self.camera_id = camera_id
        self.threshold_secs = threshold_secs
        self._states: Dict[int, _TalkState] = {}
        self.diagnostics = {}
        self.mar_std_threshold = mar_std_threshold

    @classmethod
    def get_instance(cls, camera_id: str, threshold_secs: float = 8.0) -> "TalkingDetector":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id, threshold_secs=threshold_secs)
        return cls._instances[camera_id]

    def update(self, track_id: int, face_signals: Dict) -> Dict:
        now = time.time()
        if track_id not in self._states:
            self._states[track_id] = _TalkState(track_id=track_id)
        state = self._states[track_id]

        mar = face_signals.get("mar")
        if mar is None:
            if state.paused_at is None:state.paused_at=state.last_valid_at if state.last_valid_at is not None else now
            if now-state.paused_at>3:
                state.mar_history.clear();state.talking_since=None;state.alerted=False;state.excluded_secs=0
            self.diagnostics[track_id]={'is_talking_candidate':False,'is_talking':False,'duration_secs':0,
                'sample_time':now,'mouth_samples':len(state.mar_history),'mar':None,'mar_variability':self._stdev(state.mar_history),
                'reset_reason':'mouth_missing_grace_paused','mouth_landmarks_available':False,'missing_mouth_sample':True}
            return {'is_talking_candidate':False,'is_talking':False,'duration_secs':0,'mar_variability':self._stdev(state.mar_history)}
        if state.paused_at is not None:
            if now-state.paused_at>3:state.mar_history.clear();state.talking_since=None;state.excluded_secs=0;state.alerted=False
            else:state.excluded_secs+=now-state.paused_at
            state.paused_at=None
        state.last_valid_at=now
        if mar is not None:
            state.mar_history.append(mar)
            if len(state.mar_history) > MAR_HISTORY_WINDOW:
                state.mar_history = state.mar_history[-MAR_HISTORY_WINDOW:]

        mar_std = self._stdev(state.mar_history) if len(state.mar_history) >= 8 else 0.0
        is_talking_now = mar_std >= self.mar_std_threshold

        if is_talking_now:
            if state.talking_since is None:
                state.talking_since = now
        else:
            state.talking_since = None
            state.excluded_secs=0
            state.alerted = False

        duration = max(0,now-state.talking_since-state.excluded_secs) if state.talking_since is not None else 0.0
        is_talking = duration >= self.threshold_secs
        result = {"is_talking_candidate": is_talking_now, "is_talking": is_talking,
                  "duration_secs": duration, "mar_variability": mar_std}
        self.diagnostics[track_id] = {**result, "sample_time": now, "mouth_landmarks_available": mar is not None,
            "mar": mar, "mouth_samples": len(state.mar_history), "candidate_start_time": state.talking_since,
            "reset_reason": None if is_talking_now else ("insufficient_mouth_samples" if len(state.mar_history)<8 else "mar_std_below_threshold"),
            "missing_mouth_sample": mar is None}
        return result

    def consume_alert(self, track_id: int) -> bool:
        state = self._states.get(track_id)
        if state is None or state.alerted:
            return False
        state.alerted = True
        return True

    def cleanup(self, active_track_ids: set):
        for tid in list(self._states.keys()):
            if tid not in active_track_ids:
                del self._states[tid]
                self.diagnostics.pop(tid, None)

    @staticmethod
    def _stdev(values: List[float]) -> float:
        n = len(values)
        if n < 2:
            return 0.0
        mean = sum(values) / n
        return (sum((v - mean) ** 2 for v in values) / n) ** 0.5

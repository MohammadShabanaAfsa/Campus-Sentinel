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

    def duration_closed(self, now: float) -> float:
        return (now - self.closed_since) if self.closed_since else 0.0


@dataclass
class _TalkState:
    track_id: int
    mar_history: List[float] = field(default_factory=list)
    talking_since: Optional[float] = None
    alerted: bool = False


class SleepingDetector:
    """Flags a student as sleeping once eyes-closed / head-down persists
    beyond the configured threshold."""

    _instances: Dict[str, "SleepingDetector"] = {}

    def __init__(self, camera_id: str, threshold_secs: float = 15.0):
        self.camera_id = camera_id
        self.threshold_secs = threshold_secs
        self._states: Dict[int, _SleepState] = {}

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

        eyes_closed = face_signals.get("ear") is not None and face_signals["ear"] < EAR_CLOSED_THRESHOLD
        head_down = bool(face_signals.get("head_down"))
        # Either sustained eyes-closed (drowsy) or a bowed head with no visible
        # face (asleep on the desk) counts as a "closed" instant.
        candidate = eyes_closed or (head_down and not face_signals.get("face_detected"))

        if candidate:
            if state.closed_since is None:
                state.closed_since = now
        else:
            state.closed_since = None
            state.alerted = False

        duration = state.duration_closed(now)
        is_sleeping = duration >= self.threshold_secs
        return {"is_sleeping_candidate": candidate, "is_sleeping": is_sleeping, "duration_secs": duration}

    def consume_alert(self, track_id: int) -> bool:
        """Returns True exactly once per continuous sleeping episode (edge-triggered)."""
        state = self._states.get(track_id)
        if state is None or state.alerted:
            return False
        state.alerted = True
        return True

    def cleanup(self, active_track_ids: set):
        for tid in list(self._states.keys()):
            if tid not in active_track_ids:
                del self._states[tid]


class TalkingDetector:
    """Flags a student as talking once mouth-shape variability (speech-like
    movement) is sustained beyond the configured threshold."""

    _instances: Dict[str, "TalkingDetector"] = {}

    def __init__(self, camera_id: str, threshold_secs: float = 8.0):
        self.camera_id = camera_id
        self.threshold_secs = threshold_secs
        self._states: Dict[int, _TalkState] = {}

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
        if mar is not None:
            state.mar_history.append(mar)
            if len(state.mar_history) > MAR_HISTORY_WINDOW:
                state.mar_history = state.mar_history[-MAR_HISTORY_WINDOW:]

        mar_std = self._stdev(state.mar_history) if len(state.mar_history) >= 8 else 0.0
        is_talking_now = mar_std >= MAR_TALKING_STD_THRESHOLD

        if is_talking_now:
            if state.talking_since is None:
                state.talking_since = now
        else:
            state.talking_since = None
            state.alerted = False

        duration = (now - state.talking_since) if state.talking_since else 0.0
        is_talking = duration >= self.threshold_secs
        return {"is_talking_candidate": is_talking_now, "is_talking": is_talking,
                "duration_secs": duration, "mar_variability": mar_std}

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

    @staticmethod
    def _stdev(values: List[float]) -> float:
        n = len(values)
        if n < 2:
            return 0.0
        mean = sum(values) / n
        return (sum((v - mean) ** 2 for v in values) / n) ** 0.5

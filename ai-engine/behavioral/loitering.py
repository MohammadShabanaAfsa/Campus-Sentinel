"""
Loitering Detection — flags individuals who remain in a small area
beyond a configurable time threshold.
"""
import time
import math
from typing import List, Dict, Any
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class LoiterState:
    track_id: int
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    positions: list = field(default_factory=list)
    alerted: bool = False

    @property
    def duration(self) -> float:
        return self.last_seen - self.first_seen

    @property
    def movement_radius(self) -> float:
        if len(self.positions) < 2:
            return 0.0
        xs = [p[0] for p in self.positions]
        ys = [p[1] for p in self.positions]
        return math.sqrt((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2)


class LoiteringDetector:
    _instances: Dict[str, "LoiteringDetector"] = {}

    def __init__(self, camera_id: str, threshold_secs: int = 300, movement_threshold: float = 0.05):
        self.camera_id = camera_id
        self.threshold_secs = threshold_secs
        self.movement_threshold = movement_threshold  # Normalized screen fraction
        self._states: Dict[int, LoiterState] = {}

    @classmethod
    def get_instance(cls, camera_id: str) -> "LoiteringDetector":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id)
        return cls._instances[camera_id]

    def analyze(self, tracks: List[Dict]) -> List[Dict]:
        """
        Analyze current tracks for loitering.
        Returns list of alert dicts to dispatch.
        """
        alerts = []
        now = time.time()
        active_ids = {t["track_id"] for t in tracks if t.get("class_name") == "person"}

        # Clean up dead tracks
        for tid in list(self._states.keys()):
            if tid not in active_ids:
                del self._states[tid]

        for track in tracks:
            if track.get("class_name") != "person":
                continue
            tid = track["track_id"]

            if tid not in self._states:
                self._states[tid] = LoiterState(track_id=tid)
            state = self._states[tid]

            state.last_seen = now
            pos = (track.get("cx", 0), track.get("cy", 0))
            state.positions.append(pos)
            if len(state.positions) > 200:
                state.positions = state.positions[-200:]

            # Check loitering conditions
            if (state.duration >= self.threshold_secs and
                    state.movement_radius <= self.movement_threshold and
                    not state.alerted):

                risk_score = min(1.0, state.duration / (self.threshold_secs * 2))
                severity = "high" if risk_score > 0.7 else "medium"
                state.alerted = True

                alerts.append({
                    "alert_type": "loitering",
                    "severity": severity,
                    "title": f"Loitering Detected — Person #{tid}",
                    "description": (
                        f"Person #{tid} has been stationary for "
                        f"{int(state.duration // 60)} min {int(state.duration % 60)} sec "
                        f"within a small area (radius {state.movement_radius:.3f})."
                    ),
                    "threat_score": risk_score,
                    "feature_contributions": {
                        "duration": state.duration / (self.threshold_secs * 2) * 0.6,
                        "movement_radius": (self.movement_threshold - state.movement_radius) * 0.3,
                        "location": 0.1,
                    },
                    "metadata": {
                        "track_id": tid,
                        "duration_secs": state.duration,
                        "movement_radius": state.movement_radius,
                        "position": pos,
                    },
                })
                logger.warning(f"Loitering alert: Person #{tid} on camera {self.camera_id}")

        return alerts

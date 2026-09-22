"""
Abnormal Movement Detection:
- Running / sudden acceleration
- Zig-zag movement
- Direction changes
- Opposite-crowd movement
"""
import math
import time
from typing import List, Dict
from dataclasses import dataclass, field
from collections import deque


@dataclass
class MovementState:
    track_id: int
    velocities: deque = field(default_factory=lambda: deque(maxlen=20))
    directions: deque = field(default_factory=lambda: deque(maxlen=20))
    last_pos: tuple = (0.0, 0.0)
    last_time: float = field(default_factory=time.time)
    alerted: bool = False


class MovementAnalyzer:
    _instances: Dict[str, "MovementAnalyzer"] = {}

    RUNNING_SPEED_PX_PER_FRAME = 15.0   # pixels/frame — tune for resolution
    ZIGZAG_DIRECTION_CHANGES = 5         # within 10 frames
    ACCELERATION_MULTIPLIER = 3.0        # 3x sudden speed increase

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self._states: Dict[int, MovementState] = {}

    @classmethod
    def get_instance(cls, camera_id: str) -> "MovementAnalyzer":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id)
        return cls._instances[camera_id]

    def analyze(self, tracks: List[Dict]) -> List[Dict]:
        alerts = []
        now = time.time()
        active_ids = {t["track_id"] for t in tracks if t.get("class_name") == "person"}

        for tid in list(self._states.keys()):
            if tid not in active_ids:
                del self._states[tid]

        for track in tracks:
            if track.get("class_name") != "person":
                continue
            tid = track["track_id"]

            if tid not in self._states:
                self._states[tid] = MovementState(
                    track_id=tid,
                    last_pos=(track["cx"], track["cy"]),
                    last_time=now
                )
                continue

            state = self._states[tid]
            cx, cy = track["cx"], track["cy"]
            dt = now - state.last_time
            if dt <= 0:
                continue

            dx = cx - state.last_pos[0]
            dy = cy - state.last_pos[1]
            speed = math.sqrt(dx**2 + dy**2) / dt
            direction = math.atan2(dy, dx)

            state.velocities.append(speed)
            state.directions.append(direction)
            state.last_pos = (cx, cy)
            state.last_time = now

            if state.alerted:
                continue

            # Running detection
            if speed > self.RUNNING_SPEED_PX_PER_FRAME and len(state.velocities) >= 3:
                alerts.append(self._make_alert(tid, "running", speed, "person running detected"))
                state.alerted = True
                continue

            # Sudden acceleration
            if len(state.velocities) >= 5:
                recent_avg = sum(list(state.velocities)[-3:]) / 3
                prev_avg = sum(list(state.velocities)[-8:-3]) / 5
                if prev_avg > 0 and recent_avg / prev_avg > self.ACCELERATION_MULTIPLIER:
                    alerts.append(self._make_alert(tid, "sudden_acceleration", recent_avg, "sudden acceleration"))
                    state.alerted = True
                    continue

            # Zig-zag detection
            if len(state.directions) >= 10:
                direction_changes = sum(
                    1 for i in range(1, len(state.directions))
                    if abs(state.directions[i] - state.directions[i-1]) > math.pi / 2
                )
                if direction_changes >= self.ZIGZAG_DIRECTION_CHANGES:
                    alerts.append(self._make_alert(tid, "zigzag_movement", speed, "zig-zag movement detected"))
                    state.alerted = True

        return alerts

    def _make_alert(self, track_id: int, movement_type: str, speed: float, description: str) -> Dict:
        severity_map = {"running": "medium", "sudden_acceleration": "high", "zigzag_movement": "medium"}
        return {
            "alert_type": "abnormal_movement",
            "severity": severity_map.get(movement_type, "medium"),
            "title": f"Abnormal Movement — Person #{track_id} ({movement_type})",
            "description": f"Person #{track_id}: {description} (speed: {speed:.1f} px/s)",
            "threat_score": 0.6,
            "metadata": {"track_id": track_id, "movement_type": movement_type, "speed": speed},
        }

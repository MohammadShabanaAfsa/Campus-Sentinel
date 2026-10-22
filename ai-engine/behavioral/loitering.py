"""
Loitering Detection — flags individuals who remain in a small area
beyond a configurable time threshold.
"""
from ai_engine.vision.behavior_overlay import event

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
    bounds: tuple | None = None
    missing_since: float | None = None

    @property
    def duration(self) -> float:
        return self.last_seen - self.first_seen

    @property
    def movement_radius(self) -> float:
        if self.bounds is not None:
            xmin,ymin,xmax,ymax=self.bounds
            return math.hypot(xmax-xmin,ymax-ymin)
        if len(self.positions) < 2:
            return 0.0
        xs = [p[0] for p in self.positions]
        ys = [p[1] for p in self.positions]
        return math.sqrt((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2)


class LoiteringDetector:
    _instances: Dict[str, "LoiteringDetector"] = {}

    def __init__(self, camera_id: str, threshold_secs=None, movement_threshold=None):
        from app.core.config import settings
        self.camera_id = camera_id
        self.threshold_secs = threshold_secs if threshold_secs is not None else (
            settings.LOITERING_DEBUG_THRESHOLD_SECS if settings.ACTIVITY_DEBUG else settings.LOITERING_THRESHOLD_SECS)
        self.movement_threshold = movement_threshold if movement_threshold is not None else settings.LOITERING_MOVEMENT_RADIUS
        self.track_grace_secs = settings.LOITERING_TRACK_GRACE_SECS
        if self.threshold_secs<=0 or self.movement_threshold<=0:raise ValueError('Loitering thresholds must be positive')
        self._states: Dict[int, LoiterState] = {}
        self.overlay_events=[]

    @classmethod
    def get_instance(cls, camera_id: str) -> "LoiteringDetector":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id)
        return cls._instances[camera_id]

    def analyze(self, tracks: List[Dict], frame_width=640, frame_height=480, now=None) -> List[Dict]:
        """
        Analyze current tracks for loitering.
        Returns list of alert dicts to dispatch.
        """
        alerts = []
        self.overlay_events = []
        now = time.time() if now is None else now
        if not math.isfinite(now):return []
        valid={}
        for track in tracks:
            if track.get('class_name')!='person' or track.get('time_since_update',0)>0 or track.get('track_id') is None:continue
            if frame_width<=0 or frame_height<=0:continue
            bbox=track.get('bbox')
            cx=track.get('cx',(bbox[0]+bbox[2])/2 if bbox else None)
            cy=track.get('cy',(bbox[1]+bbox[3])/2 if bbox else None)
            if cx is None or cy is None or not all(math.isfinite(v) for v in (cx,cy)):continue
            if not (0<=cx<=frame_width and 0<=cy<=frame_height):continue
            valid[track['track_id']]=(cx/frame_width,cy/frame_height)
        active_ids=set(valid)

        # Clean up dead tracks
        for tid in list(self._states.keys()):
            if tid not in active_ids and self._states[tid].missing_since is None:
                self._states[tid].missing_since = self._states[tid].last_seen
            if tid not in active_ids and (now < self._states[tid].last_seen or
                                          now-self._states[tid].last_seen > self.track_grace_secs):
                del self._states[tid]

        for tid,pos in valid.items():
            if tid not in self._states:
                self._states[tid] = LoiterState(track_id=tid,first_seen=now,last_seen=now)
            state = self._states[tid]
            if now<state.last_seen or now-state.last_seen>self.track_grace_secs:
                state=self._states[tid]=LoiterState(track_id=tid,first_seen=now,last_seen=now)
            state.missing_since = None
            state.last_seen = now
            if state.bounds is None:
                points=state.positions+[pos]
                state.bounds=(min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points))
            else:
                a,b,c,d=state.bounds;state.bounds=(min(a,pos[0]),min(b,pos[1]),max(c,pos[0]),max(d,pos[1]))
            state.positions.append(pos)
            if len(state.positions) > 200:
                state.positions = state.positions[-200:]
            if state.movement_radius>self.movement_threshold:
                state.first_seen=now;state.positions=[pos];state.bounds=(*pos,*pos);state.alerted=False

            # Check loitering conditions
            active = (state.duration >= self.threshold_secs and
                      state.movement_radius <= self.movement_threshold)
            if active:
                risk_score = min(1.0, state.duration / (self.threshold_secs * 2))
                self.overlay_events.append(event("loitering", "medium", tid,duration_secs=state.duration,movement_radius=state.movement_radius))
            else:
                state.alerted=False
            if active and not state.alerted:

                risk_score = min(1.0, state.duration / (self.threshold_secs * 2))
                severity = "medium"
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

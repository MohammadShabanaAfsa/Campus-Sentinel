"""
Crowd Density Monitoring and Unusual Formation Detection.
"""
import math
import time
from typing import List, Dict
from collections import deque
from loguru import logger


class CrowdAnalyzer:
    _instances: Dict[str, "CrowdAnalyzer"] = {}

    def __init__(self, camera_id: str, density_threshold: int = 20, surge_window_secs: float = 30.0):
        self.camera_id = camera_id
        self.density_threshold = density_threshold
        self.surge_window_secs = surge_window_secs
        self._count_history: deque = deque(maxlen=100)
        self._last_alert_time: float = 0
        self._alert_cooldown: float = 60.0

    @classmethod
    def get_instance(cls, camera_id: str) -> "CrowdAnalyzer":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id)
        return cls._instances[camera_id]

    def analyze(self, tracks: List[Dict]) -> List[Dict]:
        alerts = []
        now = time.time()

        person_tracks = [t for t in tracks if t.get("class_name") == "person"]
        person_count = len(person_tracks)

        self._count_history.append((now, person_count))

        # High density alert
        if (person_count >= self.density_threshold and
                now - self._last_alert_time > self._alert_cooldown):
            density_ratio = person_count / self.density_threshold
            risk_score = min(1.0, density_ratio * 0.7)
            self._last_alert_time = now
            alerts.append({
                "alert_type": "crowd_density",
                "severity": "high" if density_ratio > 1.5 else "medium",
                "title": f"High Crowd Density — {person_count} persons detected",
                "description": f"Crowd count of {person_count} exceeds threshold of {self.density_threshold}.",
                "threat_score": risk_score,
                "metadata": {"person_count": person_count, "threshold": self.density_threshold},
            })

        # Crowd surge detection (rapid growth)
        surge_alert = self._detect_surge(now, person_count)
        if surge_alert:
            alerts.append(surge_alert)

        # Unusual crowd formation (clustering)
        formation_alert = self._detect_formation(person_tracks, now)
        if formation_alert:
            alerts.append(formation_alert)

        return alerts

    def _detect_surge(self, now: float, current_count: int) -> Dict | None:
        """Detect if crowd is growing rapidly in a short window."""
        window_start = now - self.surge_window_secs
        window_data = [(t, c) for t, c in self._count_history if t >= window_start]
        if len(window_data) < 3:
            return None

        initial_count = window_data[0][1]
        if initial_count == 0:
            return None

        growth_rate = (current_count - initial_count) / initial_count
        if growth_rate > 0.5 and current_count > 5:  # 50% growth
            return {
                "alert_type": "crowd_surge",
                "severity": "high",
                "title": f"Rapid Crowd Surge — {growth_rate*100:.0f}% growth in {self.surge_window_secs:.0f}s",
                "description": f"Crowd grew from {initial_count} to {current_count} persons.",
                "threat_score": min(1.0, growth_rate * 0.8),
                "metadata": {"initial_count": initial_count, "current_count": current_count, "growth_rate": growth_rate},
            }
        return None

    def _detect_formation(self, person_tracks: List[Dict], now: float) -> Dict | None:
        """Detect if persons are clustering tightly (potential fight/incident)."""
        if len(person_tracks) < 4:
            return None

        positions = [(t["cx"], t["cy"]) for t in person_tracks]
        centroid_x = sum(p[0] for p in positions) / len(positions)
        centroid_y = sum(p[1] for p in positions) / len(positions)
        avg_dist = sum(math.dist(p, (centroid_x, centroid_y)) for p in positions) / len(positions)

        # Normalized — tight clustering if avg dist < 5% of frame
        if avg_dist < 0.05 * 1920 and len(person_tracks) >= 4:  # Using px estimate
            return {
                "alert_type": "crowd_formation",
                "severity": "high",
                "title": f"Unusual Crowd Formation — {len(person_tracks)} persons clustered",
                "description": f"Tight clustering of {len(person_tracks)} persons detected (avg dist {avg_dist:.1f}px).",
                "threat_score": 0.75,
                "metadata": {"person_count": len(person_tracks), "avg_distance_px": avg_dist},
            }
        return None

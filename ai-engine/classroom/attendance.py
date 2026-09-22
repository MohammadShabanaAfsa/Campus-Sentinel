"""
Attendance Monitoring + Missing Student Detection.
Counts active person tracks in a classroom camera against the configured
expected roster size. Sustained shortfall (not a momentary occlusion) is
raised as a "missing_students" alert.
"""
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from loguru import logger

SUSTAINED_SHORTFALL_SECS = 20.0  # avoid alerting on a single frame's occlusion/misdetection


@dataclass
class _AttendanceState:
    shortfall_since: Optional[float] = None
    last_missing_count: int = 0
    alerted_for: int = 0  # missing_count we last alerted for, to re-alert if it worsens


class AttendanceAnalyzer:
    _instances: Dict[str, "AttendanceAnalyzer"] = {}

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self._state = _AttendanceState()

    @classmethod
    def get_instance(cls, camera_id: str) -> "AttendanceAnalyzer":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id)
        return cls._instances[camera_id]

    def analyze(self, tracks: List[Dict], expected_students: int) -> Dict:
        """
        Returns {present_count, expected_count, missing_count, alerts}.
        `present_count` excludes the person identified as faculty by the
        caller — pass only student tracks in for a precise count, or all
        person tracks for a simple headcount if faculty isn't separated.
        """
        present_count = sum(1 for t in tracks if t.get("class_name") == "person")
        missing_count = max(0, expected_students - present_count)

        alerts = []
        now = time.time()
        state = self._state

        if missing_count > 0:
            if state.shortfall_since is None:
                state.shortfall_since = now
            duration = now - state.shortfall_since
            if duration >= SUSTAINED_SHORTFALL_SECS and missing_count != state.alerted_for:
                state.alerted_for = missing_count
                severity = "high" if missing_count >= max(3, expected_students * 0.3) else "medium"
                alerts.append({
                    "alert_type": "missing_students",
                    "severity": severity,
                    "title": f"Missing Students — {missing_count} unaccounted for",
                    "description": (
                        f"Only {present_count}/{expected_students} students detected "
                        f"for over {int(duration)}s."
                    ),
                    "threat_score": min(1.0, missing_count / max(1, expected_students)),
                    "metadata": {
                        "present_count": present_count,
                        "expected_count": expected_students,
                        "missing_count": missing_count,
                        "shortfall_duration_secs": duration,
                    },
                })
                logger.warning(
                    f"Missing students alert: camera={self.camera_id} "
                    f"present={present_count} expected={expected_students}"
                )
        else:
            state.shortfall_since = None
            state.alerted_for = 0

        return {
            "present_count": present_count,
            "expected_count": expected_students,
            "missing_count": missing_count,
            "alerts": alerts,
        }

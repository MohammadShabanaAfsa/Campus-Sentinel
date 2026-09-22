"""
ClassroomMonitor — top-level orchestrator for the Classroom Monitoring module.
Ties together attendance, faculty engagement, sleeping/talking detection, and
the Class Attention Index for a single classroom camera, using the tracks
already produced by YOLO + ByteTrack and MediaPipe Face Mesh/Pose for the
per-student signals.

One instance per camera (`get_instance`), invoked by StreamManager at a
throttled cadence — MediaPipe inference per person crop is too expensive to
run on every frame.
"""
import time
from typing import Dict, List, Optional
import numpy as np
from loguru import logger

from ai_engine.classroom.face_pose_analyzer import FacePoseAnalyzer
from ai_engine.classroom.attendance import AttendanceAnalyzer
from ai_engine.classroom.engagement import FacultyEngagementAnalyzer
from ai_engine.classroom.student_state import SleepingDetector, TalkingDetector
from ai_engine.classroom.attention_index import compute_attention_index

SUSTAINED_LOW_ENGAGEMENT_SECS = 30.0
LOW_ENGAGEMENT_THRESHOLD = 30.0
SUSTAINED_LOW_ATTENTION_SECS = 30.0
LOW_ATTENTION_THRESHOLD = 40.0


class ClassroomMonitor:
    _instances: Dict[str, "ClassroomMonitor"] = {}

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self._config = self._load_config()
        self._face_pose = FacePoseAnalyzer.get_instance(camera_id)
        self._attendance = AttendanceAnalyzer.get_instance(camera_id)
        self._engagement = FacultyEngagementAnalyzer.get_instance(camera_id)
        self._sleeping = SleepingDetector.get_instance(camera_id, self._config["sleeping_secs_threshold"])
        self._talking = TalkingDetector.get_instance(camera_id, self._config["talking_secs_threshold"])
        self._last_faculty_signals: Optional[Dict] = None
        self._low_engagement_since: Optional[float] = None
        self._low_attention_since: Optional[float] = None

    @classmethod
    def get_instance(cls, camera_id: str) -> "ClassroomMonitor":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id)
        return cls._instances[camera_id]

    def refresh_config(self):
        self._config = self._load_config()
        # SleepingDetector/TalkingDetector are per-camera singletons whose
        # threshold was fixed at first construction — push the new values in
        # directly so an edited config takes effect without a stream restart.
        self._sleeping.threshold_secs = self._config["sleeping_secs_threshold"]
        self._talking.threshold_secs = self._config["talking_secs_threshold"]

    def analyze(self, tracks: List[Dict], frame: np.ndarray) -> Dict:
        """
        Run the full classroom pipeline for one frame.
        Returns {metrics: dict-shaped-for-ClassroomMetric, alerts: [alert_data...]}.
        """
        h, w = frame.shape[:2]
        person_tracks = [t for t in tracks if t.get("class_name") == "person"]
        active_ids = {t["track_id"] for t in person_tracks}
        self._sleeping.cleanup(active_ids)
        self._talking.cleanup(active_ids)
        self._engagement.cleanup(active_ids)

        alerts: List[Dict] = []

        # ─── Attendance / Missing Students ──────────────────────────────────
        attendance = self._attendance.analyze(person_tracks, self._config["expected_students"])
        alerts.extend(attendance["alerts"])

        # ─── Faculty Engagement ──────────────────────────────────────────────
        engagement = self._engagement.analyze(
            person_tracks, self._config["teaching_zone"], self._last_faculty_signals, w, h,
        )
        faculty_id = engagement["faculty_track_id"]

        # ─── Per-student Face/Pose analysis (skip the faculty track) ───────
        sleeping_count = 0
        talking_count = 0
        for t in person_tracks:
            tid = t["track_id"]
            crop = self._crop_track(frame, t["bbox"], w, h)
            signals = self._face_pose.analyze_crop(crop)

            if tid == faculty_id:
                # Cache this frame's pose signal for next call's engagement scoring.
                self._last_faculty_signals = signals
                continue

            sleep_state = self._sleeping.update(tid, signals)
            if sleep_state["is_sleeping"]:
                sleeping_count += 1
                if self._sleeping.consume_alert(tid):
                    alerts.append(self._sleeping_alert(tid, sleep_state))

            talk_state = self._talking.update(tid, signals)
            if talk_state["is_talking"]:
                talking_count += 1
                if self._talking.consume_alert(tid):
                    alerts.append(self._talking_alert(tid, talk_state))

        # ─── Class Attention Index ───────────────────────────────────────────
        cai = compute_attention_index(
            present_count=attendance["present_count"],
            expected_count=attendance["expected_count"],
            sleeping_count=sleeping_count,
            talking_count=talking_count,
            faculty_engagement_score=engagement["engagement_score"],
            faculty_present=engagement["faculty_present"],
        )

        alerts.extend(self._sustained_engagement_alert(engagement))
        alerts.extend(self._sustained_attention_alert(cai))

        metrics = {
            "camera_id": self.camera_id,
            "present_count": attendance["present_count"],
            "expected_count": attendance["expected_count"],
            "missing_count": attendance["missing_count"],
            "sleeping_count": sleeping_count,
            "talking_count": talking_count,
            "attentive_count": cai["attentive_count"],
            "faculty_present": engagement["faculty_present"],
            "faculty_engagement_score": engagement["engagement_score"],
            "attention_index": cai["attention_index"],
            "details": {
                "attention_level": cai["level"],
                "attention_factors": cai["factors"],
                "faculty_track_id": faculty_id,
                "engagement_details": engagement.get("details", {}),
            },
        }

        return {"metrics": metrics, "alerts": alerts}

    # ─── Internals ───────────────────────────────────────────────────────────

    def _crop_track(self, frame: np.ndarray, bbox: List[float], w: int, h: int) -> Optional[np.ndarray]:
        x1, y1, x2, y2 = bbox
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(w, int(x2)), min(h, int(y2))
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def _sleeping_alert(self, track_id: int, state: Dict) -> Dict:
        logger.warning(f"[CLASSROOM] Sleeping student detected: camera={self.camera_id} track={track_id}")
        return {
            "alert_type": "sleeping_student",
            "severity": "low",
            "title": f"Sleeping Student Detected — #{track_id}",
            "description": f"Student #{track_id} has shown no eye/head activity for {int(state['duration_secs'])}s.",
            "threat_score": min(1.0, state["duration_secs"] / 60.0),
            "metadata": {"track_id": track_id, "duration_secs": state["duration_secs"]},
        }

    def _talking_alert(self, track_id: int, state: Dict) -> Dict:
        logger.warning(f"[CLASSROOM] Talking student detected: camera={self.camera_id} track={track_id}")
        return {
            "alert_type": "talking_student",
            "severity": "low",
            "title": f"Talking Student Detected — #{track_id}",
            "description": f"Student #{track_id} has shown sustained mouth activity for {int(state['duration_secs'])}s.",
            "threat_score": min(1.0, state["duration_secs"] / 30.0),
            "metadata": {"track_id": track_id, "duration_secs": state["duration_secs"], "mar_variability": state["mar_variability"]},
        }

    def _sustained_engagement_alert(self, engagement: Dict) -> List[Dict]:
        now = time.time()
        if engagement["faculty_present"] and engagement["engagement_score"] < LOW_ENGAGEMENT_THRESHOLD:
            if self._low_engagement_since is None:
                self._low_engagement_since = now
            elif now - self._low_engagement_since >= SUSTAINED_LOW_ENGAGEMENT_SECS:
                self._low_engagement_since = now  # reset so we don't spam every call
                return [{
                    "alert_type": "low_faculty_engagement",
                    "severity": "medium",
                    "title": "Low Faculty Engagement Detected",
                    "description": f"Faculty engagement score is {engagement['engagement_score']}/100.",
                    "threat_score": 1.0 - (engagement["engagement_score"] / 100.0),
                    "metadata": engagement.get("details", {}),
                }]
        else:
            self._low_engagement_since = None
        return []

    def _sustained_attention_alert(self, cai: Dict) -> List[Dict]:
        now = time.time()
        if cai["attention_index"] < LOW_ATTENTION_THRESHOLD:
            if self._low_attention_since is None:
                self._low_attention_since = now
            elif now - self._low_attention_since >= SUSTAINED_LOW_ATTENTION_SECS:
                self._low_attention_since = now
                return [{
                    "alert_type": "low_class_attention",
                    "severity": "medium",
                    "title": "Low Class Attention Index",
                    "description": f"Class Attention Index dropped to {cai['attention_index']}/100 ({cai['level']}).",
                    "threat_score": 1.0 - (cai["attention_index"] / 100.0),
                    "metadata": cai.get("factors", {}),
                }]
        else:
            self._low_attention_since = None
        return []

    def _load_config(self) -> Dict:
        defaults = {
            "expected_students": 30,
            "teaching_zone": None,
            "sleeping_secs_threshold": 15.0,
            "talking_secs_threshold": 8.0,
        }
        try:
            from sqlalchemy import create_engine, select
            from sqlalchemy.orm import Session
            from app.core.config import settings
            from app.models.classroom import ClassroomConfig
            import uuid

            engine = create_engine(settings.SYNC_DATABASE_URL)
            with Session(engine) as session:
                cfg = session.execute(
                    select(ClassroomConfig).where(ClassroomConfig.camera_id == uuid.UUID(self.camera_id))
                ).scalar_one_or_none()
                if cfg:
                    return {
                        "expected_students": cfg.expected_students,
                        "teaching_zone": cfg.teaching_zone,
                        "sleeping_secs_threshold": cfg.sleeping_secs_threshold,
                        "talking_secs_threshold": cfg.talking_secs_threshold,
                    }
        except Exception as e:
            logger.warning(f"ClassroomMonitor[{self.camera_id}]: could not load config, using defaults: {e}")
        return defaults

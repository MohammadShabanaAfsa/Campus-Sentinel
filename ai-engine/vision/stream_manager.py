"""
StreamManager — one instance per camera (get_instance(camera_id)), consistent
with every other per-camera singleton in this codebase (YOLODetector,
ByteTracker, ThreatPredictor, ...). Each instance owns exactly one daemon
thread running its camera's capture -> detect -> track -> analyze loop,
backed by CameraManager (each camera opens its own configured source; no
cross-camera fallback unless explicitly enabled for that camera).

Module-level start_all_active_cameras()/stop_all_camera_streams() are the
orchestration entry points used by app.main at startup/shutdown and by the
cameras API when a new camera is created.
"""
import threading
import time
import json
from typing import Dict, List, Optional
from enum import Enum
from loguru import logger

_redis = None
_health_thread: Optional[threading.Thread] = None
_health_thread_lock = threading.Lock()
HEALTH_CHECK_INTERVAL = 30
STALL_THRESHOLD_SECS = 60


class StreamState(Enum):
    STOPPED   = "stopped"
    STARTING  = "starting"
    RUNNING   = "running"
    RECONNECTING = "reconnecting"
    ERROR     = "error"


class StreamManager:
    """One instance per camera. Provides start / stop / restart / status."""

    RECONNECT_DELAY_SECS = 10

    _instances: Dict[str, "StreamManager"] = {}
    _instances_lock = threading.Lock()

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.thread: Optional[threading.Thread] = None
        self.state = StreamState.STOPPED
        self.error_count = 0
        self.started_at = 0.0
        self.last_frame_at = 0.0
        self.frames_processed = 0
        self._stop_event = threading.Event()
        self._start_lock = threading.Lock()

    @classmethod
    def get_instance(cls, camera_id: str) -> "StreamManager":
        with cls._instances_lock:
            if camera_id not in cls._instances:
                cls._instances[camera_id] = cls(camera_id)
            return cls._instances[camera_id]

    @classmethod
    def all_instances(cls) -> List["StreamManager"]:
        with cls._instances_lock:
            return list(cls._instances.values())

    def is_alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    # ─── Public API ──────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start this camera's stream in a daemon thread."""
        with self._start_lock:
            if self.is_alive():
                logger.debug(f"Camera {self.camera_id} already running")
                return False

            self._stop_event = threading.Event()
            self.state = StreamState.STARTING
            self.started_at = time.time()
            self.thread = threading.Thread(
                target=self._camera_loop,
                daemon=True,
                name=f"cam-{self.camera_id[:8]}",
            )
            self.thread.start()
            logger.info(f"Started stream for camera {self.camera_id}")
            return True

    def stop(self):
        self._stop_event.set()
        self.state = StreamState.STOPPED
        logger.info(f"Stopped stream for camera {self.camera_id}")

    def restart(self):
        self.stop()
        time.sleep(2)
        self.start()

    def get_status(self) -> Dict:
        return {
            "state": self.state.value,
            "is_alive": self.is_alive(),
            "frames_processed": self.frames_processed,
            "error_count": self.error_count,
            "uptime_secs": round(time.time() - self.started_at, 1) if self.started_at else 0,
            "last_frame_age_secs": round(time.time() - self.last_frame_at, 1) if self.last_frame_at else None,
        }

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _camera_loop(self):
        """Main loop for this camera: open stream -> process frames -> reconnect on failure."""
        import cv2
        import base64
        from ai_engine.vision.detector import YOLODetector
        from ai_engine.tracking.tracker import ByteTracker
        from ai_engine.vision.frame_annotator import FrameAnnotator
        from ai_engine.vision.camera_manager import CameraManager

        camera_id = self.camera_id
        stop_event = self._stop_event

        rtsp_url = _get_rtsp_url(camera_id)
        if rtsp_url is None:
            logger.error(f"Camera {camera_id} not found in DB")
            self.state = StreamState.ERROR
            return

        detector  = YOLODetector.get_instance()
        tracker   = ByteTracker(camera_id=camera_id)
        annotator = FrameAnnotator()
        redis     = _get_redis()

        from app.core.config import settings
        frame_skip = settings.FRAME_SKIP
        cam_mgr = CameraManager(camera_id=camera_id, primary_source=rtsp_url, enable_fallback=False)
        is_classroom = _get_camera_zone_type(camera_id) == "classroom"
        if is_classroom:
            from ai_engine.classroom.classroom_monitor import ClassroomMonitor
            classroom_monitor = ClassroomMonitor.get_instance(camera_id)
            logger.info(f"Classroom Monitoring enabled for camera {camera_id}")

        while not stop_event.is_set():
            self.state = StreamState.STARTING

            if not cam_mgr.open():
                logger.warning(f"Cannot open stream {camera_id} (source={rtsp_url})")
                self.state = StreamState.RECONNECTING
                self.error_count += 1
                _update_camera_status(camera_id, "error")
                self._wait_or_stop(stop_event, self.RECONNECT_DELAY_SECS)
                continue

            logger.info(
                f"Stream opened: camera {camera_id} "
                f"(source={cam_mgr.active_source}, fallback={cam_mgr.using_fallback})"
            )
            _update_camera_status(camera_id, "online")
            self.state = StreamState.RUNNING
            self.error_count = 0
            frame_n = 0

            while not stop_event.is_set():
                ret, frame = cam_mgr.read()
                if not ret:
                    logger.warning(f"Frame loss on camera {camera_id}")
                    break

                frame_n += 1
                if frame_n % frame_skip != 0:
                    continue

                try:
                    detections = detector.detect(frame)
                    tracks = tracker.update(detections, frame)
                    logger.debug(
                        f"[YOLO] camera={camera_id} frame={frame_n} "
                        f"detections={len(detections)} tracks={len(tracks)}"
                    )
                    annotated = annotator.draw(frame.copy(), tracks)

                    # Encode to JPEG → base64
                    _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 72])
                    frame_b64 = base64.b64encode(buf).decode("utf-8")

                    payload = json.dumps({
                        "type": "frame",
                        "camera_id": camera_id,
                        "frame_number": frame_n,
                        "tracks": tracks,
                        "detection_count": len(detections),
                        "person_count": sum(1 for t in tracks if t.get("class_name") == "person"),
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    })

                    # Write to Redis
                    redis.set(f"camera:{camera_id}:latest_frame", frame_b64, ex=10)
                    redis.set(f"camera:{camera_id}:tracks", payload, ex=10)
                    redis.set(f"camera:{camera_id}:heartbeat", time.time(), ex=60)
                    redis.publish("camera_events", payload)

                    # Persist detections + tracks every 10 frames
                    if frame_n % 10 == 0:
                        _persist_detections(camera_id, detections, tracks, frame_n)

                    # Trigger behavioral analysis in Celery (skip if worker not running)
                    if frame_n % 30 == 0:
                        frame_h, frame_w = frame.shape[:2]
                        try:
                            from app.services.tasks.ai_tasks import analyze_behavior
                            analyze_behavior.delay(camera_id, json.dumps(tracks), frame_n, frame_w, frame_h)
                        except Exception:
                            pass

                        # Feed the same tracks to the agent-bus pipeline:
                        # BehaviorAgent -> ABD scoring -> PredictionAgent -> DecisionAgent -> ResponseAgent
                        try:
                            from agents.orchestrator.agent_bus import AgentBus
                            AgentBus.get_instance().publish("tracks", {
                                "camera_id": camera_id,
                                "frame_number": frame_n,
                                "tracks": tracks,
                                "frame_width": frame_w,
                                "frame_height": frame_h,
                                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            })
                        except Exception as e:
                            logger.warning(f"AgentBus publish failed for camera {camera_id}: {e}")

                        # Classroom Monitoring: attendance, sleeping/talking detection,
                        # faculty engagement, and Class Attention Index.
                        if is_classroom:
                            try:
                                result = classroom_monitor.analyze(tracks, frame)
                                _persist_classroom_metric(camera_id, result["metrics"])
                                _publish_classroom_metric(camera_id, result["metrics"])
                                for alert_data in result["alerts"]:
                                    from app.services.tasks.alert_tasks import create_and_dispatch_alert
                                    create_and_dispatch_alert.delay(camera_id, alert_data)
                            except Exception as e:
                                logger.error(f"Classroom monitoring error on camera {camera_id}: {e}")

                    self.last_frame_at = time.time()
                    self.frames_processed += 1

                except Exception as e:
                    logger.error(f"Frame processing error on camera {camera_id}: {e}")

            cam_mgr.release()
            if not stop_event.is_set():
                self.state = StreamState.RECONNECTING
                logger.info(f"Reconnecting camera {camera_id} in {self.RECONNECT_DELAY_SECS}s...")
                self._wait_or_stop(stop_event, self.RECONNECT_DELAY_SECS)

        cam_mgr.release()
        self.state = StreamState.STOPPED
        _update_camera_status(camera_id, "offline")
        logger.info(f"Stream stopped: camera {camera_id}")

    def _wait_or_stop(self, stop_event: threading.Event, secs: float):
        stop_event.wait(timeout=secs)


# ─── Module-level orchestration ───────────────────────────────────────────────

def start_all_active_cameras():
    """Load all active cameras from DB and start one StreamManager per camera."""
    cameras = _load_active_cameras()
    logger.info(f"Starting {len(cameras)} camera streams (one StreamManager each)")
    for cam in cameras:
        StreamManager.get_instance(str(cam["id"])).start()
    _start_health_monitor()


def stop_all_camera_streams():
    for sm in StreamManager.all_instances():
        sm.stop()
    logger.info("All camera streams stopped")


def get_all_statuses() -> Dict[str, Dict]:
    return {sm.camera_id: sm.get_status() for sm in StreamManager.all_instances()}


def _start_health_monitor():
    """Single shared health-check thread covering every camera's StreamManager."""
    global _health_thread
    with _health_thread_lock:
        if _health_thread is not None and _health_thread.is_alive():
            return

        def _monitor():
            while True:
                time.sleep(HEALTH_CHECK_INTERVAL)
                _health_check()

        _health_thread = threading.Thread(target=_monitor, daemon=True, name="stream-health")
        _health_thread.start()


def _health_check():
    """Restart stalled camera streams."""
    for sm in StreamManager.all_instances():
        if sm.state == StreamState.RUNNING:
            age = time.time() - sm.last_frame_at if sm.last_frame_at else 0
            if age > STALL_THRESHOLD_SECS:
                logger.warning(f"Camera {sm.camera_id} stalled ({age:.0f}s) — restarting")
                sm.restart()


def _get_redis():
    global _redis
    if _redis is None:
        import redis as r
        from app.core.config import settings
        _redis = r.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _get_rtsp_url(camera_id: str) -> Optional[str]:
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from app.models.camera import Camera
        import uuid

        engine = create_engine(settings.SYNC_DATABASE_URL)
        with Session(engine) as session:
            cam = session.get(Camera, uuid.UUID(camera_id))
            return cam.rtsp_url if cam else None
    except Exception as e:
        logger.error(f"Could not get RTSP URL for {camera_id}: {e}")
        return None


def _get_camera_zone_type(camera_id: str) -> Optional[str]:
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from app.models.camera import Camera
        import uuid

        engine = create_engine(settings.SYNC_DATABASE_URL)
        with Session(engine) as session:
            cam = session.get(Camera, uuid.UUID(camera_id))
            return cam.zone_type if cam else None
    except Exception as e:
        logger.error(f"Could not get zone_type for {camera_id}: {e}")
        return None


def _persist_classroom_metric(camera_id: str, metrics: dict):
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from app.models.classroom import ClassroomMetric
        import uuid

        engine = create_engine(settings.SYNC_DATABASE_URL)
        with Session(engine) as session:
            m = ClassroomMetric(
                camera_id=uuid.UUID(camera_id),
                present_count=metrics["present_count"],
                expected_count=metrics["expected_count"],
                missing_count=metrics["missing_count"],
                sleeping_count=metrics["sleeping_count"],
                talking_count=metrics["talking_count"],
                attentive_count=metrics["attentive_count"],
                faculty_present=metrics["faculty_present"],
                faculty_engagement_score=metrics["faculty_engagement_score"],
                attention_index=metrics["attention_index"],
                details=metrics.get("details", {}),
            )
            session.add(m)
            session.commit()
        logger.debug(
            f"[CLASSROOM] camera={camera_id} present={metrics['present_count']}/{metrics['expected_count']} "
            f"sleeping={metrics['sleeping_count']} talking={metrics['talking_count']} "
            f"attention_index={metrics['attention_index']}"
        )
    except Exception as e:
        logger.error(f"Classroom metric persist error for {camera_id}: {e}")


def _publish_classroom_metric(camera_id: str, metrics: dict):
    try:
        redis = _get_redis()
        payload = json.dumps({
            "type": "classroom_update",
            "camera_id": camera_id,
            "metrics": metrics,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        redis.set(f"classroom:{camera_id}:latest_metric", payload, ex=120)
        redis.publish("classroom_updates", payload)
    except Exception as e:
        logger.warning(f"Classroom metric publish error for {camera_id}: {e}")


def _update_camera_status(camera_id: str, status: str):
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from app.models.camera import Camera
        from datetime import datetime
        import uuid

        engine = create_engine(settings.SYNC_DATABASE_URL)
        with Session(engine) as session:
            cam = session.get(Camera, uuid.UUID(camera_id))
            if cam:
                cam.status = status
                cam.last_heartbeat = datetime.utcnow()
                session.commit()
    except Exception as e:
        logger.warning(f"Could not update camera status {camera_id}: {e}")


def _persist_detections(camera_id: str, detections: list, tracks: list, frame_n: int):
    """Batch write detections + track positions to DB."""
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from app.models.detection import Detection
        import uuid
        from datetime import datetime

        engine = create_engine(settings.SYNC_DATABASE_URL)
        cam_uuid = uuid.UUID(camera_id)
        now = datetime.utcnow()

        with Session(engine) as session:
            for det in detections:
                x1, y1, x2, y2 = det["bbox"]
                d = Detection(
                    camera_id=cam_uuid,
                    detected_at=now,
                    object_class=det["class_name"],
                    confidence=det["confidence"],
                    bbox_x=x1, bbox_y=y1,
                    bbox_w=x2 - x1, bbox_h=y2 - y1,
                    frame_number=frame_n,
                )
                session.add(d)
            session.commit()
    except Exception as e:
        logger.warning(f"Detection persist error: {e}")


def _load_active_cameras() -> list:
    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from app.models.camera import Camera

        engine = create_engine(settings.SYNC_DATABASE_URL)
        with Session(engine) as session:
            cams = session.execute(
                select(Camera).where(Camera.is_active == True)
            ).scalars().all()
            return [{"id": c.id, "rtsp_url": c.rtsp_url} for c in cams]
    except Exception as e:
        logger.error(f"Could not load cameras: {e}")
        return []

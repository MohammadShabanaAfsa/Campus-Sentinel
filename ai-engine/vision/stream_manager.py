"""
StreamManager â€” one instance per camera (get_instance(camera_id)), consistent
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
        self._start_lock = threading.RLock()
        self.last_error: Optional[str] = None

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

    # â”€â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
        with self._start_lock:
            self.stop()
            thread = self.thread
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=35)
            if self.is_alive():
                self.last_error = "Previous capture is still stopping; retry shortly"
                logger.warning(f"Camera {self.camera_id}: {self.last_error}")
                return False
            return self.start()

    def get_status(self) -> Dict:
        return {
            "state": self.state.value,
            "is_alive": self.is_alive(),
            "frames_processed": self.frames_processed,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "uptime_secs": round(time.time() - self.started_at, 1) if self.started_at else 0,
            "last_frame_age_secs": round(time.time() - self.last_frame_at, 1) if self.last_frame_at else None,
        }

    # â”€â”€â”€ Internal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _camera_loop(self):
        """One capture/track/analyze/render loop per camera, with isolated reconnect state."""
        import cv2,base64,uuid
        from pathlib import Path
        from app.core.config import settings
        from ai_engine.vision.detector import YOLODetector
        from ai_engine.tracking.tracker import ByteTracker
        from ai_engine.vision.camera_manager import CameraManager,safe_source
        from ai_engine.vision.frame_annotator import FrameAnnotator
        from ai_engine.vision.behavior_overlay import BehaviorOverlayCache
        from ai_engine.vision.confirmed_alerts import ConfirmedAlertTransitions
        from ai_engine.behavioral.person_activity import PersonActivityAnalyzer
        from ai_engine.behavioral.fall import FallDetector
        from ai_engine.behavioral.campus_events import CampusEvents
        from ai_engine.vision.vehicle_counter import VehicleCounter
        camera_id=self.camera_id;stop_event=self._stop_event
        source=_get_rtsp_url(camera_id)
        if source is None:
            self.state=StreamState.ERROR;self.last_error="Camera not found";return
        detector=YOLODetector.get_instance();annotator=FrameAnnotator();redis=_get_redis()
        zone_type=_get_camera_zone_type(camera_id);camera_name=_get_camera_name(camera_id)
        is_classroom=zone_type=="classroom"
        general_enabled=zone_type=="general" and settings.ENABLE_ACTIVITY_ANALYSIS_ON_GENERAL
        classroom_monitor=None
        if is_classroom:
            from ai_engine.classroom.classroom_monitor import ClassroomMonitor
            classroom_monitor=ClassroomMonitor.get_instance(camera_id)
        logger.info(f'Activity routing: camera_id={camera_id} camera_name={camera_name!r} zone_type={zone_type} general_enabled={general_enabled} classroom_metrics={is_classroom}')
        mapping=None
        if settings.QR_IDENTIFICATION_ENABLED:
            try:
                from ai_engine.identity.qr_identity import load_student_mapping
                workbook=Path(settings.STUDENT_QR_WORKBOOK)
                if not workbook.is_absolute():workbook=Path(__file__).resolve().parents[2]/workbook
                mapping=load_student_mapping(workbook)
            except Exception as error:logger.warning(f'QR mapping unavailable: {type(error).__name__}')
        cam=CameraManager(camera_id=camera_id,primary_source=source,enable_fallback=False)
        delay=max(.1,settings.CAMERA_RECONNECT_DELAY_SECS);qr=None
        try:
            while not stop_event.is_set():
                self.state=StreamState.STARTING
                latest=_get_rtsp_url(camera_id)
                if latest is not None:cam.primary_source=latest
                if not cam.open():
                    self.last_error=cam.last_error or 'Failed to open video stream'
                    self.error_count+=1;self.state=StreamState.RECONNECTING
                    _update_camera_status(camera_id,'error',self.last_error)
                    self._wait_or_stop(stop_event,delay);continue
                logger.info(f'Stream opened: camera {camera_id} source={safe_source(cam.active_source)}')
                self.last_error=None;self.error_count=0;self.state=StreamState.RUNNING
                _update_camera_status(camera_id,'online')
                tracker=ByteTracker(camera_id=camera_id);session=uuid.uuid4().hex
                from app.services.vehicle_counts import get_vehicle_count_store
                fall=FallDetector(settings);vehicles=VehicleCounter(camera_id,get_vehicle_count_store());next_vehicle_config=0.
                campus=CampusEvents(settings);next_campus_config=0.
                if is_classroom:classroom_monitor.reset_track_state()
                cache=BehaviorOverlayCache(session);transitions=ConfirmedAlertTransitions()
                activity=PersonActivityAnalyzer(camera_id,settings,general_face_activities=general_enabled,camera_name=camera_name,zone_type=zone_type)
                if is_classroom:
                    activity._sleeping=classroom_monitor._sleeping;activity._talking=classroom_monitor._talking
                qr=None
                if mapping is not None:
                    try:
                        from ai_engine.identity.qr_identity import QRIdentityTracker
                        qr=QRIdentityTracker(mapping,track_grace_secs=settings.QR_TRACK_GRACE_SECS,scan_interval=settings.QR_SCAN_INTERVAL_SECS,
                            max_distance_fraction=settings.QR_ASSOC_MAX_DISTANCE_FRACTION,ambiguity_margin_fraction=settings.QR_ASSOC_AMBIGUITY_MARGIN_FRACTION,
                            association_margin_px=settings.QR_ASSOCIATION_MARGIN_PX,debug_logging=settings.QR_DEBUG_LOGGING,
                            debug_overlay=False,isolate_decoder=True,scan_timeout=settings.QR_SCAN_TIMEOUT_SECS)
                    except Exception as error:logger.warning(f'QR worker unavailable: {type(error).__name__}')
                next_activity=next_behavior=next_poll=0.;frame_n=0
                while not stop_event.is_set():
                    ret,frame=cam.read()
                    if not ret:
                        self.last_error=cam.last_error or 'No frames received'
                        _update_camera_status(camera_id,'error',self.last_error);break
                    frame_n+=1
                    if frame_n%max(1,settings.FRAME_SKIP):continue
                    try:
                        detections=detector.detect(frame)
                        tracks=tracker.update([d for d in detections if d.get('class_name')!='cell phone'],frame)
                        signals=None;class_frame=is_classroom and frame_n%30==0
                        if time.monotonic()>=next_activity or class_frame:
                            next_activity=time.monotonic()+max(.1,settings.ACTIVITY_ANALYSIS_INTERVAL_SECS)
                            try:
                                signals=activity.sample(frame,tracks)
                                detections=detector.activity_phone_candidates(frame,tracks,detections,settings)
                                for raw in signals.values():raw['phone_roi_attempted']=bool(detector.last_phone_roi_used)
                                events=activity.analyze(tracks,detections,signals,frame.shape)
                                cache.update('fall',{'stream_session':session,'observed_at':time.time(),'frame_number':frame_n,
                                    'overlay_events':fall.analyze(tracks,signals,frame.shape)})
                                cache.update('activity',{'stream_session':session,'observed_at':time.time(),'frame_number':frame_n,'overlay_events':events})
                            except Exception as error:
                                signals=None;logger.warning(f'Activity analysis unavailable: {type(error).__name__}: {error}')
                        if signals is not None:
                            try:
                                if time.monotonic()>=next_campus_config:
                                    next_campus_config=time.monotonic()+5
                                    campus.configure(_get_campus_config(camera_id))
                                cache.update('campus',{'stream_session':session,'observed_at':time.time(),'frame_number':frame_n,
                                    'overlay_events':campus.analyze(tracks,signals,frame.shape)})
                            except Exception as error:logger.warning(f'Campus event analysis unavailable: {type(error).__name__}: {error}')
                        if time.monotonic()>=next_behavior or class_frame:
                            next_behavior=time.monotonic()+settings.BEHAVIOR_ANALYSIS_INTERVAL_SECS
                            try:
                                from agents.orchestrator.agent_bus import AgentBus
                                AgentBus.get_instance().publish('tracks',{'camera_id':camera_id,'zone_type':zone_type,'tracks':tracks,'stream_session':session,
                                    'observed_at':time.time(),'frame_number':frame_n,'frame_width':frame.shape[1],'frame_height':frame.shape[0],
                                    'timestamp':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
                            except Exception as error:logger.warning(f'AgentBus unavailable: {type(error).__name__}')
                        if class_frame:
                            try:
                                result=classroom_monitor.analyze(tracks,frame,person_signals=signals,shared_person_states=True)
                                cache.update('classroom',{'stream_session':session,'observed_at':time.time(),'frame_number':frame_n,'overlay_events':result.get('overlay_events',[])})
                                _persist_classroom_metric(camera_id,result['metrics']);_publish_classroom_metric(camera_id,result['metrics'])
                            except Exception as error:logger.error(f'Classroom monitoring error: {error}')
                        if signals is not None and settings.ACTIVITY_DEBUG:activity.debug_sample(tracks,signals,frame.shape,frame_n,classroom_monitor)
                        if time.monotonic()>=next_poll:
                            next_poll=time.monotonic()+.25
                            try:
                                state=redis.get(f'camera:{camera_id}:behavior_state')
                                if state:cache.update('behavior',json.loads(state))
                            except Exception:pass
                        tracks,banners=cache.attach(tracks)
                        # Remove only restricted labels as soon as the current box exits;
                        # other detector state and entry-episode routing remain untouched.
                        from ai_engine.behavioral.zone_checker import ZoneChecker
                        for tracked in tracks:
                            tracked['behaviors']=[e for e in tracked.get('behaviors',[]) if
                                e.get('type')!='restricted_zone' or not e.get('zone_points') or
                                ZoneChecker.overlap_ratio(tracked['bbox'],frame.shape[1],frame.shape[0],e['zone_points'])+1e-9>=e.get('min_overlap_ratio',.05)]
                        disabled = {'loitering','crowd_density','crowd_surge','crowd_formation'} if is_classroom else set()
                        if disabled:
                            tracks=[{**t,'behaviors':[b for b in t.get('behaviors',[]) if b['type'] not in disabled]} for t in tracks]
                            banners=[b for b in banners if b['type'] not in disabled]
                        if qr is not None:
                            try:tracks=qr.update(frame,tracks,frame_number=frame_n)
                            except Exception as error:
                                logger.warning(f'QR cache unavailable: {type(error).__name__}');qr.close();qr=None
                        if qr is None:tracks=[{**t,'identity':None} for t in tracks]
                        for alert in transitions.update([e for e in cache.confirmed_events(tracks) if e['type'] not in disabled],tracks):
                            alert['metadata']['stream_session']=session
                            try:
                                from app.services.tasks.alert_tasks import create_and_dispatch_alert
                                create_and_dispatch_alert.delay(camera_id,alert)
                            except Exception as error:
                                transitions.delivery_failed(alert);logger.warning(f'Alert enqueue unavailable: {type(error).__name__}; video continues')
                        # Diagnostic panels/polygons are never drawn into production JPEGs.
                        if time.monotonic()>=next_vehicle_config:
                            next_vehicle_config=time.monotonic()+5
                            try:vehicles.configure(_get_vehicle_line(camera_id))
                            except Exception as error:logger.debug(f'Counting line refresh unavailable: {type(error).__name__}')
                        vehicle_counts=vehicles.update(tracks,frame.shape)
                        annotated=annotator.draw(frame.copy(),tracks,{'camera_behaviors':banners,'vehicle_counts':vehicle_counts})
                        _,buffer=cv2.imencode('.jpg',annotated,[cv2.IMWRITE_JPEG_QUALITY,72])
                        payload=json.dumps({'type':'frame','camera_id':camera_id,'frame_number':frame_n,'tracks':tracks,'camera_behaviors':banners,
                            'stream_session':session,'vehicle_counts':vehicle_counts,'detection_count':len(detections),'person_count':sum(t.get('class_name')=='person' for t in tracks),
                            'timestamp':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
                        redis.set(f'camera:{camera_id}:latest_frame',base64.b64encode(buffer).decode('utf-8'),ex=10)
                        redis.set(f'camera:{camera_id}:tracks',payload,ex=10);redis.set(f'camera:{camera_id}:heartbeat',time.time(),ex=60)
                        redis.publish('camera_events',payload)
                        if frame_n%10==0:_persist_detections(camera_id,detections,tracks,frame_n)
                        self.last_frame_at=time.time();self.frames_processed+=1
                    except Exception as error:logger.error(f'Frame processing error on {camera_id}: {error}')
                if qr is not None:qr.close();qr=None
                cam.release()
                if not stop_event.is_set():
                    self.state=StreamState.RECONNECTING;self._wait_or_stop(stop_event,delay)
        finally:
            if qr is not None:qr.close()
            cam.release();self.state=StreamState.STOPPED
            logger.info(f'Stream stopped: camera {camera_id}')

    def _wait_or_stop(self, stop_event: threading.Event, secs: float):
        stop_event.wait(timeout=secs)


# â”€â”€â”€ Module-level orchestration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
                logger.warning(f"Camera {sm.camera_id} stalled ({age:.0f}s) â€” restarting")
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


def _get_campus_config(camera_id: str):
    from sqlalchemy import text
    if not hasattr(_get_vehicle_line,'engine'):
        from sqlalchemy import create_engine
        from app.core.config import settings
        _get_vehicle_line.engine=create_engine(settings.SYNC_DATABASE_URL,pool_pre_ping=True)
    with _get_vehicle_line.engine.connect() as connection:
        config=connection.execute(text('SELECT config FROM cameras WHERE id=:id'),{'id':camera_id}).scalar() or {}
        return config.get('campus_events',{})


def _get_vehicle_line(camera_id: str):
    try:
        from sqlalchemy import create_engine,text
        from app.core.config import settings
        if not hasattr(_get_vehicle_line,'engine'):
            _get_vehicle_line.engine=create_engine(settings.SYNC_DATABASE_URL,pool_pre_ping=True)
        with _get_vehicle_line.engine.connect() as connection:
            config=connection.execute(text('SELECT config FROM cameras WHERE id=:id'),{'id':camera_id}).scalar() or {}
            return config.get('vehicle_counting_line')
    except Exception:
        raise


def _get_camera_name(camera_id: str) -> str:
    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings
        with create_engine(settings.SYNC_DATABASE_URL).connect() as connection:
            return connection.execute(text("SELECT name FROM cameras WHERE id = :id"), {"id": camera_id}).scalar() or camera_id
    except Exception:
        return camera_id


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


def _update_camera_status(camera_id: str, status: str, last_error: Optional[str] = None):
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
                cam.config = {**(cam.config or {}), "last_error": last_error}
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

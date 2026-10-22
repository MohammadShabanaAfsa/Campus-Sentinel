"""
Celery tasks for AI pipeline: behavioral analysis trigger.

Frame capture, YOLO detection, and tracking all run inline inside
ai_engine.vision.stream_manager.StreamManager._camera_loop (one daemon
thread per camera in the API process) — not as Celery tasks. This file only
holds the legacy behavioral-analyzer task for compatibility. The current
StreamManager publishes track snapshots to the persistent BehaviorAgent.
"""
import json
from celery import shared_task
from loguru import logger


@shared_task(name="app.services.tasks.ai_tasks.analyze_behavior")
def analyze_behavior(camera_id: str, tracks_json: str, frame_number: int, frame_width: int = 1920, frame_height: int = 1080):
    """Run behavioral analytics on tracked persons."""
    try:
        from ai_engine.behavioral.loitering import LoiteringDetector
        from ai_engine.behavioral.crowd import CrowdAnalyzer
        from ai_engine.behavioral.movement import MovementAnalyzer
        from ai_engine.behavioral.zone_checker import ZoneChecker

        tracks = json.loads(tracks_json)

        from ai_engine.vision.stream_manager import _get_camera_zone_type
        classroom = _get_camera_zone_type(camera_id) == 'classroom'
        movement_analyzer = MovementAnalyzer.get_instance(camera_id)
        zone_checker = ZoneChecker.get_instance(camera_id)

        alerts_generated = []
        if not classroom:
            alerts_generated.extend(LoiteringDetector.get_instance(camera_id).analyze(tracks,frame_width,frame_height))
            alerts_generated.extend(CrowdAnalyzer.get_instance(camera_id).analyze(tracks,frame_width))
        alerts_generated.extend(movement_analyzer.analyze(tracks,frame_width,frame_height))
        alerts_generated.extend(zone_checker.analyze(tracks, frame_width, frame_height))

        for alert_data in alerts_generated:
            from app.services.tasks.alert_tasks import create_and_dispatch_alert
            create_and_dispatch_alert.delay(camera_id, alert_data)

    except Exception as e:
        logger.error(f"Behavioral analysis error: {e}")

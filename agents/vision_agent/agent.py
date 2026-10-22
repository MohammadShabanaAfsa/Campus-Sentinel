"""
Vision Agent — responsible for:
1. Subscribing to raw frame events
2. Running YOLOv8 detection
3. Running ByteTrack tracking
4. Publishing tracks to the agent bus
"""
import json
import base64
import numpy as np
from loguru import logger
from agents.orchestrator.agent_bus import AgentBus


class VisionAgent:
    NAME = "VisionAgent"

    def __init__(self):
        self.bus = AgentBus.get_instance()
        self._detector = None
        self._trackers = {}

    def _get_detector(self):
        if self._detector is None:
            from ai_engine.vision.detector import YOLODetector
            from app.core.config import settings
            self._detector = YOLODetector.get_instance(
                model_path=settings.YOLO_MODEL_PATH,
                device=settings.YOLO_DEVICE
            )
        return self._detector

    def _get_tracker(self, camera_id: str):
        if camera_id not in self._trackers:
            from ai_engine.tracking.tracker import ByteTracker
            self._trackers[camera_id] = ByteTracker(camera_id=camera_id)
        return self._trackers[camera_id]

    def start(self):
        """Register message handlers and start listening."""
        self.bus.subscribe("raw_frames", self._on_raw_frame)
        logger.info(f"{self.NAME} started")

    def _on_raw_frame(self, message: dict):
        """Process an incoming raw frame message."""
        try:
            camera_id = message["camera_id"]
            frame_b64 = message["frame_b64"]
            frame_number = message.get("frame_number", 0)

            import cv2
            frame_bytes = base64.b64decode(frame_b64)
            frame_arr = np.frombuffer(frame_bytes, dtype=np.uint8)
            frame = cv2.imdecode(frame_arr, cv2.IMREAD_COLOR)

            detector = self._get_detector()
            tracker = self._get_tracker(camera_id)

            detections = detector.detect(frame)
            tracks = tracker.update(detections, frame)

            # Publish tracks to behavior agent
            self.bus.publish("tracks", {
                "camera_id": camera_id,
                "frame_number": frame_number,
                "tracks": tracks,
                "timestamp": message.get("timestamp"),
            })

            logger.debug(f"{self.NAME}: Processed frame {frame_number} for camera {camera_id} — {len(tracks)} tracks")

        except Exception as e:
            logger.error(f"{self.NAME} error: {e}")

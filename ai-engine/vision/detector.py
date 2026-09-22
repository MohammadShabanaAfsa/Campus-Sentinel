"""YOLOv8-based object detector with singleton pattern for model reuse."""
import numpy as np
from typing import List, Dict, Any
from loguru import logger


class YOLODetector:
    _instances: Dict[str, "YOLODetector"] = {}
    _model = None

    TARGET_CLASSES = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle",
                      24: "backpack", 26: "handbag", 28: "suitcase", 63: "laptop"}

    def __init__(self, model_path: str = "yolov8n.pt", device: str = "cpu", conf_threshold: float = 0.5):
        self.model_path = model_path
        self.device = device
        self.conf_threshold = conf_threshold
        self._load_model()

    def _load_model(self):
        try:
            from ultralytics import YOLO
            self._model = YOLO(self.model_path)
            self._model.to(self.device)
            logger.info(f"YOLOv8 model loaded: {self.model_path} on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            self._model = None

    @classmethod
    def get_instance(cls, model_path: str = "yolov8n.pt", device: str = "cpu") -> "YOLODetector":
        key = f"{model_path}_{device}"
        if key not in cls._instances:
            cls._instances[key] = cls(model_path=model_path, device=device)
        return cls._instances[key]

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Run detection on a frame.
        Returns list of dicts: {class_id, class_name, confidence, bbox: [x1,y1,x2,y2]}
        """
        if self._model is None:
            return []

        try:
            results = self._model(frame, conf=self.conf_threshold, verbose=False)
            detections = []

            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                for box in boxes:
                    class_id = int(box.cls[0])
                    if class_id not in self.TARGET_CLASSES:
                        continue
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    detections.append({
                        "class_id": class_id,
                        "class_name": self.TARGET_CLASSES[class_id],
                        "confidence": float(box.conf[0]),
                        "bbox": [x1, y1, x2, y2],
                        "cx": (x1 + x2) / 2,
                        "cy": (y1 + y2) / 2,
                        "width": x2 - x1,
                        "height": y2 - y1,
                    })

            return detections

        except Exception as e:
            logger.error(f"Detection error: {e}")
            return []

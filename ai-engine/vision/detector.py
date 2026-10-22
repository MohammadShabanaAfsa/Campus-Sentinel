"""YOLOv8-based object detector with singleton pattern for model reuse."""
import numpy as np
import threading
from typing import List, Dict, Any
from loguru import logger


class YOLODetector:
    _instances: Dict[str, "YOLODetector"] = {}
    _model = None
    _inference_lock = threading.Lock()
    _instance_lock = threading.Lock()

    TARGET_CLASSES = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck",
                      24: "backpack", 26: "handbag", 28: "suitcase", 63: "laptop", 67: "cell phone"}

    def __init__(self, model_path: str = "yolov8n.pt", device: str = "cpu", conf_threshold: float = 0.5):
        self.model_path = model_path
        self.device = device
        self.conf_threshold = conf_threshold
        from app.core.config import settings
        self.phone_conf_threshold = settings.YOLO_PHONE_CONFIDENCE_THRESHOLD
        self.phone_roi_max_input_size=settings.PHONE_ROI_MAX_INPUT_SIZE
        self.debug_logging=settings.ACTIVITY_DEBUG
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
        # Both capture threads start together; initialization must be atomic too.
        with cls._instance_lock:
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
            with self._inference_lock:
                # Ultralytics retains prediction options: restore all classes after a phone-only ROI call.
                results = self._model(frame, conf=min(self.conf_threshold,self.phone_conf_threshold), classes=list(self.TARGET_CLASSES), imgsz=640, verbose=False)
            detections = []

            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                for box in boxes:
                    class_id = int(box.cls[0])
                    if getattr(self,'debug_logging',False):logger.debug(f'YOLO_RAW class_id={class_id} class_name={result.names.get(class_id,class_id) if hasattr(result,"names") else class_id} confidence={float(box.conf[0]):.6f} bbox={box.xyxy[0].tolist()}')
                    if class_id not in self.TARGET_CLASSES:
                        continue
                    threshold = self.phone_conf_threshold if class_id==67 else self.conf_threshold
                    if float(box.conf[0])<threshold:
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
                        "source": "full_frame",
                    })

            return detections

        except Exception as e:
            logger.error(f"Detection error: {e}")
            return []

    def detect_phone_rois(self, frame, tracks, max_persons=2):
        """Reuse the loaded model on enlarged person crops; return frame coordinates."""
        if self._model is None:return []
        import cv2
        h,w=frame.shape[:2]
        phones=[]
        persons=[t for t in tracks if t.get('class_name')=='person' and t.get('time_since_update',0)==0
                 and t['bbox'][2]-t['bbox'][0]>=80 and t['bbox'][3]-t['bbox'][1]>=120]
        persons.sort(key=lambda t:t.get('confidence',0),reverse=True)
        for track in persons[:max_persons]:
            x1,y1,x2,y2=track['bbox'];dx,dy=.2*(x2-x1),.2*(y2-y1)
            x1,y1=max(0,int(x1-dx)),max(0,int(y1-dy));x2,y2=min(w,int(x2+dx)),min(h,int(y2+dy))
            crop=frame[y1:y2,x1:x2]
            if crop.size==0:continue
            maximum=max(640,min(1280,int(getattr(self,'phone_roi_max_input_size',960))))
            maximum=maximum//32*32
            scale=min(2.0,max(1.5,640/max(crop.shape[:2])),maximum/max(crop.shape[:2]))
            enlarged=cv2.resize(crop,None,fx=scale,fy=scale,
                interpolation=cv2.INTER_CUBIC if scale>1 else cv2.INTER_AREA) if scale!=1 else crop
            with self._inference_lock:
                # Keep enlargement at the network input; default imgsz=640 would undo it.
                input_size=min(maximum,max(640,int(np.ceil(max(enlarged.shape[:2])/32)*32)))
                results=self._model(enlarged,conf=self.phone_conf_threshold,classes=[67],imgsz=input_size,verbose=False)
            sx,sy=enlarged.shape[1]/crop.shape[1],enlarged.shape[0]/crop.shape[0]
            for result in results:
                if result.boxes is None:continue
                for box in result.boxes:
                    if int(box.cls[0])!=67 or float(box.conf[0])<self.phone_conf_threshold:continue
                    a,b,c,d=box.xyxy[0].tolist()
                    phones.append({'class_id':67,'class_name':'cell phone','confidence':float(box.conf[0]),
                        'bbox':[x1+a/sx,y1+b/sy,x1+c/sx,y1+d/sy],'source':'person_roi'})
        # Overlapping crops must not multiply phone evidence.
        def iou(a,b):
            overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
            area=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-overlap
            return overlap/area if area>0 else 0
        unique=[]
        for phone in sorted(phones,key=lambda d:d['confidence'],reverse=True):
            if not any(iou(phone['bbox'],other['bbox'])>.5 for other in unique):unique.append(phone)
        return unique

    def activity_phone_candidates(self, frame, tracks, detections, settings):
        """Called only at activity cadence; landmarks must not gate object recovery."""
        self.last_phone_roi_used=False
        if not settings.PHONE_ROI_INFERENCE_ENABLED or any(
                d.get('class_name')=='cell phone' and d.get('confidence',0)>=self.phone_conf_threshold
                for d in detections):
            return detections
        eligible=[t for t in tracks if t.get('class_name')=='person' and t.get('time_since_update',0)==0
                  and t['bbox'][2]-t['bbox'][0]>=80 and t['bbox'][3]-t['bbox'][1]>=120]
        if not eligible:return detections
        self.last_phone_roi_used=True
        return [*detections,*self.detect_phone_rois(frame,eligible,settings.PHONE_ROI_MAX_PERSONS)]

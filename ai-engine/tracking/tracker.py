"""
ByteTrack multi-object tracker implementation.
Tracks persons across video frames using Hungarian algorithm + Kalman filter.
"""
import numpy as np
from typing import List, Dict, Any
from dataclasses import dataclass, field
from collections import defaultdict
import time


@dataclass
class Track:
    track_id: int
    class_name: str
    bbox: List[float]
    confidence: float
    cx: float
    cy: float
    age: int = 0
    hits: int = 1
    time_since_update: int = 0
    position_history: List[tuple] = field(default_factory=list)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    @property
    def duration_secs(self) -> float:
        return self.last_seen - self.first_seen

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "class_name": self.class_name,
            "bbox": self.bbox,
            "confidence": self.confidence,
            "cx": self.cx,
            "cy": self.cy,
            "age": self.age,
            "duration_secs": round(self.duration_secs, 2),
            "position_history": self.position_history[-10:],  # Last 10 positions
        }


class ByteTracker:
    """Simplified ByteTrack implementation using IoU-based assignment."""

    _instances: Dict[str, "ByteTracker"] = {}

    def __init__(self, camera_id: str, max_age: int = 30, min_hits: int = 3, iou_threshold: float = 0.3):
        self.camera_id = camera_id
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.tracks: List[Track] = []
        self._next_id = 1

    @classmethod
    def get_instance(cls, camera_id: str) -> "ByteTracker":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id)
        return cls._instances[camera_id]

    def update(self, detections: List[Dict], frame: np.ndarray) -> List[Dict]:
        """
        Update tracker with new detections.
        Returns list of active track dicts.
        """
        now = time.time()
        h, w = frame.shape[:2]

        # Predict existing tracks
        for track in self.tracks:
            track.time_since_update += 1
            track.age += 1

        if not detections:
            self.tracks = [t for t in self.tracks if t.time_since_update <= self.max_age]
            return self._get_active_tracks()

        # Build cost matrix (IoU)
        det_bboxes = np.array([[d["bbox"][0], d["bbox"][1], d["bbox"][2], d["bbox"][3]] for d in detections])
        track_bboxes = np.array([t.bbox for t in self.tracks]) if self.tracks else np.array([]).reshape(0, 4)

        if len(self.tracks) > 0:
            iou_matrix = self._compute_iou_matrix(track_bboxes, det_bboxes)
            matched_tracks, matched_dets, unmatched_tracks, unmatched_dets = self._assign(iou_matrix)
        else:
            matched_tracks, matched_dets = [], []
            unmatched_tracks = list(range(len(self.tracks)))
            unmatched_dets = list(range(len(detections)))

        # Update matched tracks
        for t_idx, d_idx in zip(matched_tracks, matched_dets):
            det = detections[d_idx]
            track = self.tracks[t_idx]
            track.bbox = det["bbox"]
            track.confidence = det["confidence"]
            track.cx = det["cx"]
            track.cy = det["cy"]
            track.time_since_update = 0
            track.hits += 1
            track.last_seen = now
            track.position_history.append((round(det["cx"] / w, 3), round(det["cy"] / h, 3)))
            if len(track.position_history) > 100:
                track.position_history = track.position_history[-100:]

        # Create new tracks for unmatched detections
        for d_idx in unmatched_dets:
            det = detections[d_idx]
            new_track = Track(
                track_id=self._next_id,
                class_name=det["class_name"],
                bbox=det["bbox"],
                confidence=det["confidence"],
                cx=det["cx"],
                cy=det["cy"],
                position_history=[(round(det["cx"] / w, 3), round(det["cy"] / h, 3))],
            )
            self.tracks.append(new_track)
            self._next_id += 1

        # Remove dead tracks
        self.tracks = [t for t in self.tracks if t.time_since_update <= self.max_age]

        return self._get_active_tracks()

    def _get_active_tracks(self) -> List[Dict]:
        return [t.to_dict() for t in self.tracks if t.hits >= self.min_hits]

    def _compute_iou_matrix(self, boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
        iou = np.zeros((len(boxes_a), len(boxes_b)))
        for i, a in enumerate(boxes_a):
            for j, b in enumerate(boxes_b):
                iou[i, j] = self._iou(a, b)
        return iou

    def _iou(self, a: np.ndarray, b: np.ndarray) -> float:
        x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
        x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def _assign(self, iou_matrix: np.ndarray):
        """Greedy IoU-based assignment."""
        matched_tracks, matched_dets = [], []
        unmatched_tracks = list(range(iou_matrix.shape[0]))
        unmatched_dets = list(range(iou_matrix.shape[1]))

        if iou_matrix.size == 0:
            return matched_tracks, matched_dets, unmatched_tracks, unmatched_dets

        # Sort pairs by IoU descending
        pairs = sorted([(iou_matrix[i, j], i, j)
                        for i in range(iou_matrix.shape[0])
                        for j in range(iou_matrix.shape[1])],
                       reverse=True)

        used_t, used_d = set(), set()
        for iou_val, t, d in pairs:
            if iou_val < self.iou_threshold:
                break
            if t in used_t or d in used_d:
                continue
            matched_tracks.append(t)
            matched_dets.append(d)
            used_t.add(t)
            used_d.add(d)

        unmatched_tracks = [i for i in range(iou_matrix.shape[0]) if i not in used_t]
        unmatched_dets = [j for j in range(iou_matrix.shape[1]) if j not in used_d]

        return matched_tracks, matched_dets, unmatched_tracks, unmatched_dets

"""
FrameAnnotator — draws detection boxes, track IDs, labels,
crowd count overlay, and timestamp onto raw frames.
"""
import cv2
import numpy as np
import time
from typing import List, Dict

CLASS_COLORS = {
    "person":    (0,   220,  80),
    "car":       (255, 140,   0),
    "bicycle":   (255,   0, 200),
    "motorcycle":(200, 100, 255),
    "backpack":  (  0, 180, 255),
    "handbag":   (  0, 180, 255),
    "suitcase":  (  0, 180, 255),
}
DEFAULT_COLOR = (0, 200, 255)

RISK_COLORS = {
    "safe":      (0,   220,  80),
    "moderate":  (255, 165,   0),
    "high_risk": (255,  50,  50),
    "critical":  (180,   0, 255),
}


class FrameAnnotator:
    def draw(self, frame: np.ndarray, tracks: List[Dict], overlay_info: Dict | None = None) -> np.ndarray:
        h, w = frame.shape[:2]
        person_count = sum(1 for t in tracks if t.get("class_name") == "person")

        for track in tracks:
            self._draw_track(frame, track, w, h)

        self._draw_hud(frame, person_count, w, h, overlay_info)
        return frame

    def _draw_track(self, frame: np.ndarray, track: Dict, w: int, h: int):
        x1, y1, x2, y2 = [int(v) for v in track["bbox"]]
        cls = track.get("class_name", "unknown")
        tid = track.get("track_id", 0)
        conf = track.get("confidence", 0)
        color = CLASS_COLORS.get(cls, DEFAULT_COLOR)

        # Bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        # Label background
        label = f"#{tid} {cls} {conf:.2f}"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(frame, (x1, y1 - lh - 6), (x1 + lw + 4, y1), color, -1)
        cv2.putText(frame, label, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

        # Movement trail (last 5 positions)
        positions = track.get("position_history", [])
        if len(positions) >= 2:
            pts = [(int(p[0] * w), int(p[1] * h)) for p in positions[-6:]]
            for i in range(1, len(pts)):
                alpha = i / len(pts)
                c = tuple(int(v * alpha) for v in color)
                cv2.line(frame, pts[i - 1], pts[i], c, 1)

    def _draw_hud(self, frame: np.ndarray, person_count: int, w: int, h: int, info: Dict | None):
        # Semi-transparent top bar
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 34), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

        # Timestamp
        ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        cv2.putText(frame, ts, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

        # Person count
        count_str = f"Persons: {person_count}"
        cv2.putText(frame, count_str, (w - 140, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 80), 1)

        # LIVE indicator (blinking red dot)
        blink = int(time.time() * 2) % 2 == 0
        if blink:
            cv2.circle(frame, (w - 160, 17), 5, (0, 0, 220), -1)
            cv2.putText(frame, "LIVE", (w - 152, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 220), 1)

        # CSI / risk overlay (bottom left)
        if info and "risk_level" in info:
            risk = info["risk_level"]
            score = info.get("csi_score", "—")
            rc = RISK_COLORS.get(risk, (200, 200, 200))
            bottom_bar = frame.copy()
            cv2.rectangle(bottom_bar, (0, h - 28), (200, h), (0, 0, 0), -1)
            cv2.addWeighted(bottom_bar, 0.5, frame, 0.5, 0, frame)
            cv2.putText(frame, f"CSI {score} | {risk.upper()}", (6, h - 9),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, rc, 1)

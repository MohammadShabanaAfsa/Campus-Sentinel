"""
FrameAnnotator — draws detection boxes, track IDs, labels,
crowd count overlay, and timestamp onto raw frames.
"""
import cv2
import numpy as np
import time
from typing import List, Dict
from ai_engine.vision.behavior_overlay import PERSON_LABELS, CAMERA_LABELS, SEVERITY_ORDER

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
        person_count = sum(1 for t in tracks if t.get("class_name") == "person" and t.get('time_since_update',0)==0)

        self._draw_hud(frame, person_count, w, h, overlay_info)
        banners = [b for b in (overlay_info or {}).get('camera_behaviors', []) if b.get('type') in CAMERA_LABELS][:3]
        label_top_margin = 38 + 22 * len(banners) if banners else 36
        for track in tracks:
            if track.get('time_since_update',0)>0:continue
            self._draw_track(frame, track, w, h, label_top_margin)
        self._draw_camera_alerts(frame, (overlay_info or {}).get("camera_behaviors", []), w, h)
        counts=(overlay_info or {}).get('vehicle_counts')
        if counts is not None:
            self._text_strip(frame,f"VEHICLES IN: {counts['in']}  OUT: {counts['out']}  TOTAL: {counts['total']}",
                             8,max(0,h-26),w,h,(45,45,45),.48)
        return frame

    def _draw_track(self, frame: np.ndarray, track: Dict, w: int, h: int, top_margin=36):
        x1, y1, x2, y2 = [int(v) for v in track["bbox"]]
        x1, x2 = max(0, min(w - 1, x1)), max(0, min(w - 1, x2))
        y1, y2 = max(0, min(h - 1, y1)), max(0, min(h - 1, y2))
        cls = track.get("class_name", "unknown")
        tid = track.get("track_id", 0)
        conf = track.get("confidence", 0)
        color = CLASS_COLORS.get(cls, DEFAULT_COLOR)

        # Bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        # Behavior belongs to this exact track, never inferred from position.
        behaviors = sorted((b for b in track.get("behaviors", [])
                            if cls == "person" and b.get("type") in PERSON_LABELS
                            and b.get("track_id") == tid),
                           key=lambda b: (SEVERITY_ORDER.get(b.get("severity"), 4), -b.get("detected_at", 0)))[:2]
        label = f"#{tid} {cls.upper()} {conf:.2f}"
        lines = []
        if cls == "person":
            identity = track.get("identity") or {}
            known = (identity.get("verified") is True and identity.get("method") == "qr"
                     and identity.get("track_id") == tid and identity.get("roll_no") and identity.get("name"))
            identity_text = f"{identity['roll_no']} | {identity['name']}".upper() if known else "UNKNOWN"
            lines.append((identity_text, (45, 45, 45), 0.52))
        if behaviors:
            severity = behaviors[0].get('severity', 'low')
            backgrounds = {'low':(0,105,150),'medium':(10,65,185),'high':(30,40,180),'critical':(100,25,130)}
            lines.append((" | ".join(PERSON_LABELS[b["type"]] for b in behaviors), backgrounds.get(severity,backgrounds['low']), 0.52))
        lines.append((label, color, 0.45))
        block_height = 22 * len(lines)
        # Reserve the HUD; use the box's top interior if there is no space above.
        top = y1 - block_height if y1 - block_height >= top_margin else max(top_margin, y1)
        top = min(max(0, top), max(0, h - block_height))
        for index, (text, background, scale) in enumerate(lines):
            self._text_strip(frame, text, x1, top + index * 22, w, h, background, scale)

    @staticmethod
    def _text_strip(frame, text, x, y, w, h, background, scale):
        # Fit labels to the frame rather than painting off-screen.
        available = max(1, w - 8)
        width = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0]
        scale = max(0.25, min(scale, scale * available / max(1, width)))
        while text and cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0] > available:
            text = text[:-1]
        (width, height), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
        x = max(0, min(x, w - width - 4))
        y = max(0, min(y, h - height - baseline - 6))
        cv2.rectangle(frame, (x, y), (min(w - 1, x + width + 4), min(h - 1, y + height + baseline + 6)), background, -1)
        cv2.putText(frame, text, (x + 2, min(h - 1, y + height + 3)), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 1, cv2.LINE_AA)

    def _draw_camera_alerts(self, frame, behaviors, w, h):
        for index, behavior in enumerate(behaviors[:3]):
            label = CAMERA_LABELS.get(behavior.get("type"))
            if label is None:
                continue
            count = behavior.get("person_count")
            if behavior.get('type')=='suspected_fight':
                label+=' - TRACKS '+ ' / '.join(f'#{tid}' for tid in behavior.get('track_ids',[]))
            if count is not None:
                label += f" - {count} PERSONS"
            self._text_strip(frame, "ALERT: " + label, 8, 38 + index * 22, w, h, (30, 60, 160), 0.5)

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
            cv2.circle(frame, (w - 210, 17), 5, (0, 0, 220), -1)
            cv2.putText(frame, "LIVE", (w - 202, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 220), 1)

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

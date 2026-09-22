"""
Faculty Engagement Analysis.
Identifies the faculty member among tracked persons (whoever spends the most
time in the configured teaching zone, or — with no zone configured — the
longest-observed track nearest the front of the room) and scores their
engagement from time-in-zone, movement activity, and facing-the-class ratio
(from MediaPipe Pose shoulder geometry).
"""
import time
from collections import defaultdict
from typing import Dict, List, Optional
from loguru import logger


class FacultyEngagementAnalyzer:
    _instances: Dict[str, "FacultyEngagementAnalyzer"] = {}

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self._zone_time: Dict[int, float] = defaultdict(float)
        self._positions: Dict[int, List[tuple]] = defaultdict(list)
        self._facing_samples: Dict[int, List[float]] = defaultdict(list)
        self._last_update = time.time()

    @classmethod
    def get_instance(cls, camera_id: str) -> "FacultyEngagementAnalyzer":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id)
        return cls._instances[camera_id]

    def analyze(
        self,
        tracks: List[Dict],
        teaching_zone: Optional[List[dict]],
        faculty_pose_signals: Optional[Dict],
        frame_w: int,
        frame_h: int,
    ) -> Dict:
        """
        `faculty_pose_signals`: the FacePoseAnalyzer output for the track this
        analyzer identified as faculty on the PREVIOUS call (the caller runs
        pose analysis only for that one track, to avoid paying MediaPipe's
        cost for every student every frame).
        """
        now = time.time()
        dt = max(0.0, now - self._last_update)
        self._last_update = now

        person_tracks = [t for t in tracks if t.get("class_name") == "person"]
        if not person_tracks:
            return {"faculty_present": False, "faculty_track_id": None, "engagement_score": 0.0, "details": {}}

        for t in person_tracks:
            tid = t["track_id"]
            cx, cy = t.get("cx", 0), t.get("cy", 0)
            if teaching_zone and frame_w and frame_h:
                if self._in_zone(cx / frame_w, cy / frame_h, teaching_zone):
                    self._zone_time[tid] += dt
            self._positions[tid].append((cx, cy))
            if len(self._positions[tid]) > 60:
                self._positions[tid] = self._positions[tid][-60:]

        faculty_id = self._identify_faculty(person_tracks, bool(teaching_zone))
        if faculty_id is None:
            return {"faculty_present": False, "faculty_track_id": None, "engagement_score": 0.0, "details": {}}

        faculty_track = next((t for t in person_tracks if t["track_id"] == faculty_id), None)
        duration = max(1.0, faculty_track.get("duration_secs", 1) if faculty_track else 1)

        zone_ratio = min(1.0, self._zone_time.get(faculty_id, 0) / duration) if teaching_zone else 0.6
        movement_ratio = self._movement_activity(self._positions.get(faculty_id, []))

        facing = (faculty_pose_signals or {}).get("facing_camera")
        self._facing_samples[faculty_id].append(1.0 if facing else (0.0 if facing is not None else 0.5))
        if len(self._facing_samples[faculty_id]) > 30:
            self._facing_samples[faculty_id] = self._facing_samples[faculty_id][-30:]
        facing_ratio = sum(self._facing_samples[faculty_id]) / len(self._facing_samples[faculty_id])

        engagement_score = round(100 * (0.45 * zone_ratio + 0.30 * movement_ratio + 0.25 * facing_ratio), 1)

        return {
            "faculty_present": True,
            "faculty_track_id": faculty_id,
            "engagement_score": engagement_score,
            "details": {
                "zone_ratio": round(zone_ratio, 3),
                "movement_ratio": round(movement_ratio, 3),
                "facing_ratio": round(facing_ratio, 3),
            },
        }

    def cleanup(self, active_track_ids: set):
        for store in (self._zone_time, self._positions, self._facing_samples):
            for tid in list(store.keys()):
                if tid not in active_track_ids:
                    del store[tid]

    # ─── Internals ───────────────────────────────────────────────────────────

    def _identify_faculty(self, person_tracks: List[Dict], has_zone: bool) -> Optional[int]:
        if has_zone:
            in_zone_tracks = {tid: t for tid in self._zone_time for t in person_tracks
                               if t["track_id"] == tid and self._zone_time[tid] > 0}
            if in_zone_tracks:
                return max(in_zone_tracks, key=lambda tid: self._zone_time[tid])
            return None
        # No teaching zone configured: fall back to the longest-observed track
        # nearest the top of the frame (front of room, closest to the board).
        candidates = [t for t in person_tracks if t.get("duration_secs", 0) > 5]
        if not candidates:
            return None
        return min(candidates, key=lambda t: t.get("cy", 1e9))["track_id"]

    def _movement_activity(self, positions: List[tuple]) -> float:
        if len(positions) < 5:
            return 0.5
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        spread = (max(xs) - min(xs)) + (max(ys) - min(ys))
        return min(1.0, spread / 400.0)

    def _in_zone(self, x: float, y: float, polygon: List[dict]) -> bool:
        """Ray-casting point-in-polygon test; x/y and polygon points are
        normalized 0-1 frame fractions."""
        n = len(polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]["x"], polygon[i]["y"]
            xj, yj = polygon[j]["x"], polygon[j]["y"]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

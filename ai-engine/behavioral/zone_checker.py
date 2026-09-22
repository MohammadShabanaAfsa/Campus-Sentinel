"""
Restricted Zone Violation Detector.
Checks if tracked persons enter admin-defined polygon zones.
"""
from typing import List, Dict
from loguru import logger


class ZoneChecker:
    _instances: Dict[str, "ZoneChecker"] = {}

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self._zones: List[Dict] = []
        self._alerted_tracks: Dict[str, set] = {}  # zone_id → set of track_ids
        self._load_zones()

    @classmethod
    def get_instance(cls, camera_id: str) -> "ZoneChecker":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id)
        return cls._instances[camera_id]

    def _load_zones(self):
        """Load restricted zones for this camera from DB."""
        try:
            from sqlalchemy import create_engine, select
            from sqlalchemy.orm import Session
            from app.core.config import settings
            from app.models.camera import RestrictedZone
            import uuid

            engine = create_engine(settings.SYNC_DATABASE_URL)
            with Session(engine) as session:
                zones = session.execute(
                    select(RestrictedZone).where(
                        RestrictedZone.camera_id == uuid.UUID(self.camera_id),
                        RestrictedZone.is_active == True
                    )
                ).scalars().all()
                self._zones = [
                    {"id": str(z.id), "name": z.name, "points": z.zone_points, "alert_level": z.alert_level}
                    for z in zones
                ]
        except Exception as e:
            logger.warning(f"Could not load zones for camera {self.camera_id}: {e}")

    def analyze(self, tracks: List[Dict], frame_w: int = 1920, frame_h: int = 1080) -> List[Dict]:
        """
        `frame_w`/`frame_h` are required to test a track against a zone: zone
        polygons are stored normalized (0-1 fractions, see RestrictedZone),
        but track cx/cy from the detector are absolute pixel coordinates —
        without normalizing by the actual frame size first, the polygon test
        silently compares incompatible coordinate spaces and zone violations
        never fire correctly.
        """
        alerts = []

        for track in tracks:
            if track.get("class_name") != "person":
                continue
            tid = track["track_id"]
            cx = track.get("cx", 0)
            cy = track.get("cy", 0)
            nx = cx / frame_w if frame_w else 0
            ny = cy / frame_h if frame_h else 0

            for zone in self._zones:
                zone_id = zone["id"]
                if zone_id not in self._alerted_tracks:
                    self._alerted_tracks[zone_id] = set()

                if self._point_in_polygon(nx, ny, zone["points"]):
                    if tid not in self._alerted_tracks[zone_id]:
                        self._alerted_tracks[zone_id].add(tid)
                        alerts.append({
                            "alert_type": "restricted_zone",
                            "severity": zone["alert_level"],
                            "title": f"Restricted Zone Violation — {zone['name']}",
                            "description": f"Person #{tid} entered restricted zone '{zone['name']}'.",
                            "threat_score": 0.85,
                            "metadata": {
                                "track_id": tid,
                                "zone_id": zone_id,
                                "zone_name": zone["name"],
                                "position": (cx, cy),
                            },
                        })
                else:
                    self._alerted_tracks[zone_id].discard(tid)

        return alerts

    def _point_in_polygon(self, x: float, y: float, polygon: List[Dict]) -> bool:
        """Ray casting algorithm for point-in-polygon test."""
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

    def refresh_zones(self):
        """Re-load zones from DB (call after admin updates zones)."""
        self._load_zones()
        self._alerted_tracks.clear()

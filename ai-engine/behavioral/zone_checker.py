"""
Restricted Zone Violation Detector.
Checks if tracked persons enter admin-defined polygon zones.
"""
from ai_engine.vision.behavior_overlay import event

from typing import List, Dict
import time
import json
import uuid
import math
from loguru import logger


class ZoneChecker:
    _instances: Dict[str, "ZoneChecker"] = {}

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self._zones: List[Dict] = []
        self._alerted_tracks: Dict[str, set] = {}  # zone_id → set of track_ids
        self._episodes = {}
        self._load_zones()
        self._next_refresh = time.monotonic()+5

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
            from app.models.camera import RestrictedZone, Camera
            import uuid

            if not hasattr(self,'_engine'):self._engine=create_engine(settings.SYNC_DATABASE_URL,pool_pre_ping=True)
            engine = self._engine
            with Session(engine) as session:
                camera=session.get(Camera,uuid.UUID(self.camera_id))
                self._reference_mode=(camera.config or {}).get('restricted_zone_reference_point') if camera else None
                zones = session.execute(
                    select(RestrictedZone).where(
                        RestrictedZone.camera_id == uuid.UUID(self.camera_id),
                        RestrictedZone.is_active == True
                    )
                ).scalars().all()
                zones = [
                    {"id": str(z.id), "camera_id":str(z.camera_id), "name": z.name, "points": self._normalize_points(z.zone_points), "alert_level": z.alert_level}
                    for z in zones
                ]
                changed={z['id'] for z in self._zones if z not in zones}
                for zone_id in changed:self._alerted_tracks.pop(zone_id,None)
                self._episodes={key:value for key,value in self._episodes.items() if key[0] not in changed}
                self._zones=zones
        except Exception as e:
            logger.warning(f"Could not load zones for camera {self.camera_id}: {e}")

    @staticmethod
    def _normalize_points(points):
        # Legacy ZoneDrawer submits its fixed 640x360 canvas coordinates.
        if any(p['x']>1 or p['y']>1 for p in points):
            return [{'x':p['x']/640,'y':p['y']/360} for p in points]
        return points

    @staticmethod
    def reference_point(bbox,frame_w,frame_h,mode='FOOT_POINT'):
        x1,y1,x2,y2=bbox
        y=y1+.90*(y2-y1) if mode=='LOWER_BODY_POINT' else y2
        return ((x1+x2)*.5/frame_w,y/frame_h)

    @staticmethod
    def overlap_ratio(bbox,frame_w,frame_h,polygon):
        """Exact polygon/rectangle area via four-plane clipping and shoelace area.

        Supports simple concave polygons, containment and crossing edges without
        rasterization, model inference, or modifying stored coordinates.
        """
        if frame_w<=0 or frame_h<=0 or len(bbox)!=4 or not all(math.isfinite(v) for v in bbox):return 0.
        x1,y1,x2,y2=bbox
        if x2<=x1 or y2<=y1:return 0.
        left,right=x1/frame_w,x2/frame_w;top,bottom=y1/frame_h,y2/frame_h
        points=[(p['x'],p['y']) for p in polygon]
        if len(points)<3 or not all(math.isfinite(v) for p in points for v in p):return 0.
        for axis,bound,keep_greater in ((0,left,True),(0,right,False),(1,top,True),(1,bottom,False)):
            if not points:return 0.
            output=[];previous=points[-1]
            previous_inside=previous[axis]>=bound if keep_greater else previous[axis]<=bound
            for current in points:
                inside=current[axis]>=bound if keep_greater else current[axis]<=bound
                if inside!=previous_inside:
                    fraction=(bound-previous[axis])/(current[axis]-previous[axis])
                    output.append(tuple(previous[k]+fraction*(current[k]-previous[k]) for k in (0,1)))
                if inside:output.append(current)
                previous=current;previous_inside=inside
            points=output
        if len(points)<3:return 0.
        area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))*.5
        return min(1.,area/((right-left)*(bottom-top)))

    @staticmethod
    def hit_test(x,y,polygon,tolerance=0.05):
        """Exact point, then vertical-only upward segment; polygon stays intact."""
        if ZoneChecker._point_in_polygon(None,x,y,polygon):return True
        tolerance=max(0,min(.10,tolerance))
        if tolerance==0:return False
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            if not min(a['x'],b['x'])<=x<=max(a['x'],b['x']):continue
            if a['x']==b['x']:
                edge_y=min(max(y,min(a['y'],b['y'])),max(a['y'],b['y']))
            else:edge_y=a['y']+(x-a['x'])*(b['y']-a['y'])/(b['x']-a['x'])
            if 0<=y-edge_y<=tolerance+1e-9:return True
        return False

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
        self.overlay_events = []
        from app.core.config import settings
        debug=getattr(settings,'RESTRICTED_ZONE_DEBUG',False)
        threshold=settings.RESTRICTED_ZONE_MIN_OVERLAP_RATIO
        debug_track=next((t['track_id'] for t in tracks if t.get('class_name')=='person' and t.get('time_since_update',0)==0),None)
        if time.monotonic()>=getattr(self,'_next_refresh',float('inf')):
            self._next_refresh=time.monotonic()+5
            self._load_zones()

        for track in tracks:
            if track.get("class_name") != "person" or track.get('time_since_update',0)>0:
                continue
            tid = track["track_id"]
            bbox=track.get('bbox')
            if not bbox or len(bbox)!=4 or frame_w<=0 or frame_h<=0 or not all(math.isfinite(v) for v in bbox):continue
            cx = (bbox[0]+bbox[2])*.5
            cy = bbox[3]
            nx = cx / frame_w
            ny = cy / frame_h

            for zone in self._zones:
                zone_id = zone["id"]
                if zone_id not in self._alerted_tracks:
                    self._alerted_tracks[zone_id] = set()

                if zone.get('camera_id',self.camera_id)!=self.camera_id:continue
                overlap=self.overlap_ratio(bbox,frame_w,frame_h,zone['points'])
                inside=overlap+1e-9>=threshold
                was_inside=tid in self._alerted_tracks[zone_id]
                key=(zone_id,tid)
                if not hasattr(self,'_episodes'):self._episodes={}
                if inside:
                    self._episodes.setdefault(key,uuid.uuid4().hex)
                    self.overlay_events.append(event("restricted_zone", zone["alert_level"], tid,
                                                     zone_id=zone_id,zone_name=zone['name'],episode_id=self._episodes[key],
                                                     zone_points=zone['points'],min_overlap_ratio=threshold,overlap_ratio=overlap))
                    if tid not in self._alerted_tracks[zone_id]:
                        self._alerted_tracks[zone_id].add(tid)
                        alerts.append({
                            "alert_type": "restricted_zone",
                            "severity": zone["alert_level"],
                            "title": f"Restricted Area Violation — {zone['name']}",
                            "description": f"Person #{tid} entered restricted area '{zone['name']}'.",
                            "threat_score": 0.85,
                            "metadata": {
                                "track_id": tid,
                                "zone_id": zone_id,
                                "zone_name": zone["name"],
                                "episode_id": self._episodes[key],
                                "position": (cx, cy),
                                "overlap_ratio":overlap,
                            },
                        })
                else:
                    self._alerted_tracks[zone_id].discard(tid)
                    self._episodes.pop(key,None)
                if debug and tid==debug_track:
                    logger.info('RESTRICTED_ZONE_SAMPLE '+json.dumps({'camera_id':self.camera_id,'track_id':tid,
                        'source_size':[frame_w,frame_h],'foot_point':[cx,cy],'normalized_foot':[nx,ny],
                        'hit_test':'BBOX_OVERLAP','bbox':bbox,'overlap_ratio':overlap,'min_overlap_ratio':threshold,
                        'zone_id':zone_id,'polygon':zone['points'],'inside':inside,
                        'transition':'OUTSIDE_TO_INSIDE' if inside and not was_inside else 'INSIDE_TO_OUTSIDE' if was_inside and not inside else 'INSIDE' if inside else 'OUTSIDE',
                        'episode_id':self._episodes.get(key),'alert_emitted':inside and not was_inside,
                        'reason':'new_entry_episode' if inside and not was_inside else 'already_inside_no_duplicate' if inside else 'overlap_below_threshold'}))

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

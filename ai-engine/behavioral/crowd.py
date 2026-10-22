"""Camera-level crowd episodes with timestamped, stabilized surge evidence."""
import math
import statistics
import time
from collections import deque
from typing import List, Dict
from ai_engine.vision.behavior_overlay import event


class CrowdAnalyzer:
    _instances = {}

    def __init__(self, camera_id, density_threshold=None, surge_window_secs=None):
        from app.core.config import settings
        self.camera_id = camera_id
        self.density_threshold = settings.CROWD_DENSITY_THRESHOLD if density_threshold is None else density_threshold
        self.surge_window_secs = settings.CROWD_SURGE_WINDOW_SECS if surge_window_secs is None else surge_window_secs
        self.growth_threshold = settings.CROWD_SURGE_GROWTH_THRESHOLD
        self.baseline_secs = settings.CROWD_SURGE_BASELINE_SECS
        self.confirm_secs = settings.CROWD_SURGE_CONFIRM_SECS
        self.min_samples = settings.CROWD_SURGE_MIN_SAMPLES
        self.clear_secs = settings.CROWD_EPISODE_CLEAR_SECS
        self.max_gap_secs = settings.CROWD_MAX_SAMPLE_GAP_SECS
        if self.density_threshold<=0 or self.surge_window_secs<=0:raise ValueError('Crowd thresholds must be positive')
        self.reset()

    def reset(self):
        self._count_history = deque()
        self._last_sample = None
        self._baseline = None
        self._density_active = False
        self._density_clear_since = None
        self._surge_active = False
        self._surge_since = None
        self._surge_hits = 0
        self._surge_clear_since = None
        self.overlay_events = []

    @classmethod
    def get_instance(cls, camera_id):
        if camera_id not in cls._instances:cls._instances[camera_id]=cls(camera_id)
        return cls._instances[camera_id]

    @staticmethod
    def active_people(tracks):
        # Count real current tracks once; predictions and malformed entries are excluded.
        result=[];seen=set()
        for track in tracks:
            if track.get('class_name')!='person' or track.get('time_since_update',0)>0:continue
            confidence=track.get('confidence',1)
            if confidence is None or not math.isfinite(confidence) or confidence<=0:continue
            tid=track.get('track_id')
            if tid is None or tid in seen:continue
            seen.add(tid)
            result.append(track)
        return result

    def analyze(self, tracks, frame_width=640, now=None):
        now=time.time() if now is None else now
        if not math.isfinite(now):return []
        if self._last_sample is not None and (now<self._last_sample or now-self._last_sample>self.max_gap_secs):
            self.reset()  # A capture discontinuity is not crowd growth.
        repeated=self._last_sample==now
        self._last_sample=now;self.overlay_events=[];alerts=[]
        people=self.active_people(tracks);count=len(people)
        if not repeated:self._count_history.append((now,count))
        while self._count_history and now-self._count_history[0][0]>self.surge_window_secs:self._count_history.popleft()

        if count>=self.density_threshold:
            self._density_clear_since=None
            severity='high' if count/self.density_threshold>1.5 else 'medium'
            self.overlay_events.append(event('crowd_density',severity,person_count=count))
            if not self._density_active:
                self._density_active=True
                alerts.append({'alert_type':'crowd_density','severity':severity,
                    'title':f'CROWD DENSITY - {count} PERSONS',
                    'description':f'Current count {count} reaches threshold {self.density_threshold}.',
                    'threat_score':min(1,count/self.density_threshold*.7),
                    'metadata':{'track_id':None,'person_count':count,'threshold':self.density_threshold}})
        elif self._density_active:
            if self._density_clear_since is None:self._density_clear_since=now
            if now-self._density_clear_since>=self.clear_secs:self._density_active=False

        surge=self._detect_surge(now,count,repeated)
        if surge:
            self.overlay_events.append(event('crowd_surge','high',person_count=count,
                initial_count=surge['metadata']['initial_count'],growth_rate=surge['metadata']['growth_rate']))
            if not self._surge_active:
                self._surge_active=True;alerts.append(surge)
        formation=self._detect_formation(people,now,frame_width)
        if formation:
            alerts.append(formation)
            self.overlay_events.append(event('crowd_formation',formation['severity'],person_count=count))
        return alerts

    def _stable_baseline(self, now):
        history=list(self._count_history)
        earlier=[i for i,(stamp,count) in enumerate(history) if stamp<=now-self.baseline_secs]
        if not earlier:return None
        samples=history[earlier[-1]:]
        if len(samples)<self.min_samples or max(c for _,c in samples)-min(c for _,c in samples)>1:return None
        return samples[0][0],statistics.median(c for _,c in samples)

    def _detect_surge(self, now, current_count, repeated=False):
        if self._baseline is not None and now-self._baseline[0]>self.surge_window_secs:self._baseline=None
        if self._baseline is None:self._baseline=self._stable_baseline(now)
        initial=self._baseline[1] if self._baseline else None
        growth=(current_count-initial)/max(1,initial) if initial is not None else 0
        qualifying=initial is not None and current_count>5 and growth>self.growth_threshold
        if not qualifying:
            self._surge_since=None;self._surge_hits=0
            if self._surge_active:
                if self._surge_clear_since is None:self._surge_clear_since=now
                if now-self._surge_clear_since>=self.clear_secs:self._surge_active=False
            return None
        self._surge_clear_since=None
        if self._surge_since is None:self._surge_since=now
        if not repeated:self._surge_hits+=1
        if not self._surge_active and (now-self._surge_since<self.confirm_secs or self._surge_hits<self.min_samples):return None
        return {'alert_type':'crowd_surge','severity':'high',
            'title':f'CROWD SURGE - {growth*100:.0f}% growth',
            'description':f'Count grew from {initial:g} to {current_count} within {self.surge_window_secs:g} seconds.',
            'threat_score':min(1,growth*.8),
            'metadata':{'track_id':None,'person_count':current_count,'initial_count':initial,
                'current_count':current_count,'growth_rate':growth,'window_secs':self.surge_window_secs}}

    def _detect_formation(self, person_tracks: List[Dict], now: float,frame_width=640) -> Dict | None:
        """Detect if persons are clustering tightly (potential fight/incident)."""
        if len(person_tracks) < 4:
            return None

        positions = [(t["cx"], t["cy"]) for t in person_tracks]
        centroid_x = sum(p[0] for p in positions) / len(positions)
        centroid_y = sum(p[1] for p in positions) / len(positions)
        avg_dist = sum(math.dist(p, (centroid_x, centroid_y)) for p in positions) / len(positions)

        # Normalized — tight clustering if avg dist < 5% of frame
        if avg_dist < 0.05 * frame_width and len(person_tracks) >= 4:
            return {
                "alert_type": "crowd_formation",
                "severity": "high",
                "title": f"Unusual Crowd Formation — {len(person_tracks)} persons clustered",
                "description": f"Tight clustering of {len(person_tracks)} persons detected (avg dist {avg_dist:.1f}px).",
                "threat_score": 0.75,
                "metadata": {"person_count": len(person_tracks), "avg_distance_px": avg_dist},
            }
        return None

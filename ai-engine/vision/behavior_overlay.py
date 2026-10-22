"""Display-only behavior state, owned by one camera's capture thread.

Consumes analyzer snapshots, never runs detection or dispatches alerts.
"""
import time

PERSON_LABELS = {
    "fall_detected": "FALL DETECTED",
    "running": "RUNNING", "sudden_acceleration": "SUDDEN ACCELERATION",
    "loitering": "LOITERING", "phone_use": "PHONE USE", "eating": "EATING",
    "restricted_zone": "RESTRICTED AREA PROHIBITED", "sleeping": "SLEEPING", "talking": "TALKING",
}
CAMERA_LABELS = {
    'suspected_fight':'SUSPECTED FIGHT', 'abandoned_bag':'ABANDONED BAG',
    'after_hours_presence':'AFTER-HOURS PRESENCE', 'emergency_exit_blocked':'EMERGENCY EXIT BLOCKED',
    "crowd_density": "CROWD DENSITY", "crowd_surge": "CROWD SURGE",
    "crowd_formation": "CROWD FORMATION", "low_class_attention": "LOW CLASS ATTENTION",
    "missing_students": "MISSING STUDENTS", "low_faculty_engagement": "LOW FACULTY ENGAGEMENT",
}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def event(behavior_type, severity, track_id=None, **metadata):
    return {"type": behavior_type, "severity": severity, "track_id": track_id, **metadata}


class BehaviorOverlayCache:
    TIMEOUT_SECS = 4.0
    MAX_LABELS = 2

    def __init__(self, session):
        self.session = session
        self._sources = {}
        self._versions = {}

    def update(self, source, snapshot, now=None):
        now = time.time() if now is None else now
        if snapshot.get("stream_session") != self.session:
            return
        observed = snapshot.get("observed_at")
        if not isinstance(observed, (int, float)) or observed > now + 1:
            return
        version = (observed, snapshot.get("frame_number", 0))
        if version <= self._versions.get(source, (-1, -1)):
            return  # Re-reading Redis must not refresh an old detection's expiry.
        self._versions[source] = version
        entries = []
        if now - observed < self.TIMEOUT_SECS:
            for item in snapshot.get("overlay_events", []):
                kind = item.get("type")
                if kind not in PERSON_LABELS and kind not in CAMERA_LABELS:
                    continue
                tid = item.get("track_id")
                if kind in PERSON_LABELS and tid is None:
                    continue  # Never guess a person from a box or title.
                entries.append({**item, "track_id": tid if kind in PERSON_LABELS else None,
                                "detected_at": observed, "expires_at": observed + self.TIMEOUT_SECS})
        self._sources[source] = entries  # Empty snapshot ends that source's conditions.

    def attach(self, tracks, now=None):
        now = time.time() if now is None else now
        active = {t["track_id"] for t in tracks if t.get("class_name") == "person" and t.get('time_since_update',0)==0}
        by_track = {}
        banners = {}
        for source, entries in self._sources.items():
            live = [item for item in entries if item["expires_at"] > now and
                    (item["track_id"] is None or item["track_id"] in active)]
            self._sources[source] = live
            for item in live:
                target = banners if item["track_id"] is None else by_track.setdefault(item["track_id"], {})
                previous = target.get(item["type"])
                if previous is not None and item['type']=='suspected_fight':
                    item={**item,'track_ids':sorted(set(previous.get('track_ids',[]))|set(item.get('track_ids',[])))}
                if previous is None or self._order(item) < self._order(previous):
                    target[item["type"]] = item
        enriched = []
        for track in tracks:
            behaviors = sorted(by_track.get(track["track_id"], {}).values(), key=self._order)[:self.MAX_LABELS]
            enriched.append({**track, "behaviors": [self._public(item) for item in behaviors]})
        return enriched, [self._public(item) for item in sorted(banners.values(), key=self._order)[:3]]

    @staticmethod
    def _order(item):
        return (SEVERITY_ORDER.get(item.get("severity"), 4), -item["detected_at"], item["type"])

    def confirmed_events(self,tracks,now=None):
        now=time.time() if now is None else now
        active={t['track_id'] for t in tracks if t.get('class_name')=='person' and t.get('time_since_update',0)==0}
        events={}
        for entries in self._sources.values():
            for e in entries:
                if e['expires_at']>now and (e['track_id'] is None or e['track_id'] in active):
                    key=(e['type'],e['track_id'])
                    if e.get('zone_id'):key=(*key,e['zone_id'])
                    if e['type']=='suspected_fight':key=(*key,tuple(sorted(e.get('track_ids',[]))))
                    if e['type']=='restricted_zone' and e.get('episode_id'):key=(*key,e.get('zone_id'),e['episode_id'])
                    events[key]=self._public(e)
        return list(events.values())

    @staticmethod
    def _public(item):
        return {key: value for key, value in item.items() if key != "expires_at"}

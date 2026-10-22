"""Edge-triggered alerts from the same confirmed snapshots used by overlays."""
from ai_engine.vision.behavior_overlay import PERSON_LABELS,CAMERA_LABELS
import time
import uuid

class ConfirmedAlertTransitions:
    @staticmethod
    def event_key(e):
        key=(e['type'],e.get('track_id'))
        if e['type']=='restricted_zone' and e.get('zone_id') and e.get('episode_id'):
            return (*key,e['zone_id'],e['episode_id'])
        for field in ('bag_track_id','zone_id'):
            if field in e:return (*key,field,e[field])
        if e['type']=='suspected_fight':return (*key,'pair',tuple(sorted(e.get('track_ids',[]))))
        return key
    def __init__(self,clear_grace_secs=3.0):
        self.active=set();self.last_seen={};self.clear_grace_secs=clear_grace_secs;self.retry_after={};self.episodes={}

    @staticmethod
    def expand(events):
        for e in events:
            if e['type']=='abandoned_bag' and e.get('bag_track_ids'):
                for i,bag in enumerate(e['bag_track_ids']):
                    owners=e.get('owner_track_ids',[])
                    yield {**e,'bag_track_id':bag,'bag_track_ids':[bag],
                           'owner_track_ids':owners[i:i+1]}
            else:yield e
    def update(self,events,tracks,now=None):
        now=time.monotonic() if now is None else now
        self.active={key for key in self.active if key in self.last_seen and now-self.last_seen[key]<=self.clear_grace_secs}
        identities={t['track_id']:t.get('identity') for t in tracks if t.get('class_name')=='person'}
        current={self.event_key(e):e for e in self.expand(events) if e['type'] in PERSON_LABELS or e['type'] in CAMERA_LABELS}
        self.episodes={key:value for key,value in self.episodes.items() if key in self.active or key in self.retry_after}
        alerts=[]
        for key,e in current.items():
            if key in self.active or now<self.retry_after.get(key,0):continue
            self.retry_after.pop(key,None)
            kind,tid=key[:2];label=(PERSON_LABELS|CAMERA_LABELS)[kind];identity=identities.get(tid) or {}
            who=f'Person #{tid}' if tid is not None else 'Camera'
            known = (identity.get('verified') is True and identity.get('method') == 'qr'
                     and identity.get('track_id') == tid and identity.get('roll_no') and identity.get('name'))
            if known:who=f'{identity["roll_no"]} {identity["name"]}'
            movement=kind in ('running','sudden_acceleration')
            alert_type='abnormal_movement' if movement else {'sleeping':'sleeping_student','talking':'talking_student'}.get(kind,kind)
            metadata={**{k:v for k,v in e.items() if k not in ('type','severity')},'track_id':tid,'behavior_type':kind}
            metadata['episode_id']=e.get('episode_id') or self.episodes.setdefault(key,uuid.uuid4().hex)
            if known:
                metadata['student_identity'] = {field: identity.get(field) for field in
                                               ('roll_no', 'name', 'method', 'identified_at')}
            if movement:metadata['movement_type']=kind
            title = f'{label} — {e["person_count"]} PERSONS' if kind == 'crowd_density' and 'person_count' in e else f'{label} — {who}'
            if kind=='suspected_fight':title=label+' — TRACKS '+' / '.join(f'#{track}' for track in e.get('track_ids',[]))
            alerts.append({'alert_type':alert_type,'severity':e.get('severity','low'),'title':title,
                'description':f'Confirmed {label.lower()} on {who}.','threat_score':.2 if e.get('severity')=='low' else .6,'metadata':metadata})
        for key in current:self.last_seen[key]=now
        self.active|={key for key in current if key not in self.retry_after}
        self.last_seen={key:seen for key,seen in self.last_seen.items() if key in self.active}
        return alerts
    def delivery_failed(self,alert):
        data=alert['metadata'];key=self.event_key({**data,'type':data['behavior_type']})
        self.active.discard(key);self.last_seen.pop(key,None);self.retry_after[key]=time.monotonic()+2

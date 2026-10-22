"""Timestamped movement rules with smoothing and jitter/jump rejection."""
import math,time,statistics
from dataclasses import dataclass,field
from collections import deque
from ai_engine.vision.behavior_overlay import event

@dataclass
class MovementState:
    track_id:int
    velocities:deque=field(default_factory=lambda:deque(maxlen=20))
    directions:deque=field(default_factory=lambda:deque(maxlen=20))
    last_pos:tuple=(0.,0.)
    last_time:float=field(default_factory=time.time)
    alerted:bool=False
    last_bbox:object=None
    smooth_pos:object=None
    high_hits:int=0
    high_since:object=None
    high_origin:object=None
    active:set=field(default_factory=set)

class MovementAnalyzer:
    _instances={}
    def __init__(self,camera_id):
        from app.core.config import settings
        self.camera_id=camera_id;self.settings=settings;self._states={};self.overlay_events=[]
    @classmethod
    def get_instance(cls,camera_id):
        if camera_id not in cls._instances:cls._instances[camera_id]=cls(camera_id)
        return cls._instances[camera_id]
    def analyze(self,tracks,frame_width=640,frame_height=480):
        now=time.time();alerts=[];self.overlay_events=[];s=self.settings
        active={t['track_id'] for t in tracks if t.get('class_name')=='person'}
        for tid in list(self._states):
            if tid not in active and now-self._states[tid].last_time>s.ACTIVITY_TRACK_GRACE_SECS:del self._states[tid]
        for t in tracks:
            if t.get('class_name')!='person' or t.get('time_since_update',0)>0:continue
            tid=t['track_id'];scale=640/max(1,frame_width)
            a,b,c,d=t.get('bbox',[t.get('cx',0)-30,t.get('cy',0)-50,t.get('cx',0)+30,t.get('cy',0)+50]);pos=((a+c)/2*scale,d*scale)
            state=self._states.get(tid)
            if state is None:
                self._states[tid]=MovementState(tid,last_pos=pos,last_time=now,last_bbox=[a,b,c,d],smooth_pos=pos);continue
            dt=now-state.last_time;distance=math.dist(pos,state.last_pos)
            previous=state.last_bbox
            area=max(1,(c-a)*(d-b));old_area=max(1,(previous[2]-previous[0])*(previous[3]-previous[1])) if previous else area
            invalid=dt<.05 or dt>5 or not .65<=area/old_area<=1.55 or distance>max(120,.8*math.hypot(c-a,d-b)*scale)
            state.last_time=now;state.last_pos=pos;state.last_bbox=[a,b,c,d]
            if invalid:
                state.velocities.clear();state.smooth_pos=pos;state.high_hits=0;state.high_since=None;state.active.clear();continue
            old=state.smooth_pos or pos;state.smooth_pos=tuple(.35*p+.65*q for p,q in zip(pos,old))
            speed=math.dist(old,state.smooth_pos)/dt
            state.velocities.append(speed)
            smoothed=statistics.median(list(state.velocities)[-3:])
            high=smoothed>=s.RUNNING_SPEED_THRESHOLD_PX_SEC and len(state.velocities)>=5
            if high:
                if state.high_since is None:state.high_since=now;state.high_origin=old
                state.high_hits+=1
            else:state.high_hits=0;state.high_since=None
            kinds=set()
            if high and state.high_hits>=s.RUNNING_MIN_CONSECUTIVE_SAMPLES and now-state.high_since>=s.RUNNING_MIN_DURATION_SECS and math.dist(state.high_origin,state.smooth_pos)>=s.RUNNING_MIN_DISPLACEMENT_PX:kinds.add('running')
            if len(state.velocities)>=8 and state.high_hits>=3:
                speeds=list(state.velocities);baseline=statistics.median(speeds[-8:-3]);recent=statistics.median(speeds[-3:])
                if baseline>=s.ACCELERATION_MIN_BASE_SPEED_PX_SEC and recent-baseline>=s.ACCELERATION_MIN_DELTA_PX_SEC and recent/baseline>=s.ACCELERATION_RATIO:kinds.add('sudden_acceleration')
            for kind in sorted(kinds):
                self.overlay_events.append(event(kind,'medium',tid,speed=smoothed))
                if kind not in state.active:alerts.append(self._make_alert(tid,kind,smoothed,kind.replace('_',' ')))
            state.active=kinds
        return alerts
    def _make_alert(self,track_id,movement_type,speed,description):
        return {'alert_type':'abnormal_movement','severity':'medium','title':f'{movement_type.replace("_"," ").upper()} — Person #{track_id}',
            'description':f'{description}; smoothed speed {speed:.1f} px/s at 640px reference width','threat_score':.6,
            'metadata':{'track_id':track_id,'movement_type':movement_type,'speed':speed}}

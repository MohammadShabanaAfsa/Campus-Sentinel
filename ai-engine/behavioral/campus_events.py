"""Independent unusual-event state; uses existing tracks and Pose samples."""
import math
import time
from collections import deque
from datetime import datetime
from zoneinfo import ZoneInfo
from ai_engine.vision.behavior_overlay import event
from ai_engine.behavioral.zone_checker import ZoneChecker

BAGS={'backpack','handbag','suitcase'}

class CampusEvents:
    def __init__(self,settings):
        self.settings=settings;self.config={};self.previous={};self.pairs={};self.bags={};self.exits={}
        self.after_since=None;self.last_time=None

    def configure(self,config):
        config=config or {}
        if config.get('exit_zones')!=self.config.get('exit_zones'):self.exits.clear()
        if config.get('schedule')!=self.config.get('schedule'):self.after_since=None
        self.config=config

    @staticmethod
    def inside(point,polygon):return ZoneChecker._point_in_polygon(None,*point,polygon)

    def analyze(self,tracks,signals,shape,now=None,wall_time=None):
        now=time.monotonic() if now is None else now
        if self.last_time is not None and (now<self.last_time or now-self.last_time>5):
            self.previous.clear();self.pairs.clear();self.bags.clear();self.exits.clear();self.after_since=None
        self.last_time=now;h,w=shape[:2];current={};events=[]
        for t in tracks:
            if t.get('time_since_update',0)>0:continue
            x1,y1,x2,y2=t['bbox']
            if not all(math.isfinite(v) for v in (x1,y1,x2,y2)) or x2<=x1 or y2<=y1:continue
            current[t['track_id']]={**t,'center':((x1+x2)*.5/w,(y1+y2)*.5/h),'foot':((x1+x2)*.5/w,y2/h)}
        people={tid:t for tid,t in current.items() if t['class_name']=='person'}
        events.extend(self._fight(people,signals,shape,now))
        events.extend(self._bags(current,people,shape,now))
        events.extend(self._after_hours(people,now,wall_time))
        events.extend(self._exit_blockage(current,now))
        self.previous={tid:{'center':t['center'],'time':now,'wrists':self._wrists(t,signals.get(tid,{}),shape)} for tid,t in people.items()}
        return events

    @staticmethod
    def _wrists(track,raw,shape):
        h,w=shape[:2];a,b,c,d=raw.get('analysis_bbox',track['bbox'])
        return {side:((a+p[0]*(c-a))/w,(b+p[1]*(d-b))/h) for side,p in raw.get('fight_wrists',{}).items()}

    def _fight(self,people,signals,shape,now):
        events=[];ids=sorted(people);seen=set()
        for i,left in enumerate(ids):
            for right in ids[i+1:]:
                key=(left,right);seen.add(key);p,q=people[left],people[right]
                distance=math.dist(p['center'],q['center'])
                state=self.pairs.setdefault(key,{'phase':'NORMAL','samples':deque(),'last_distance':distance,'direction':0,'last_seen':now})
                state['last_seen']=now
                close=distance<=self.settings.FIGHT_PROXIMITY_RADIUS
                oldp,oldq=self.previous.get(left),self.previous.get(right)
                rapid=False
                if close and oldp and oldq:
                    dt=now-oldp['time']
                    if dt>0:
                        relative=math.hypot(*[(p['center'][k]-oldp['center'][k]-q['center'][k]+oldq['center'][k])/dt for k in (0,1)])
                        arm_speeds=[]
                        for tid,track,old in ((left,p,oldp),(right,q,oldq)):
                            wrists=self._wrists(track,signals.get(tid,{}),shape)
                            scale=max(.05,(track['bbox'][3]-track['bbox'][1])/shape[0])
                            arm_speeds.append(max((math.dist(point,old['wrists'][side])/dt/scale for side,point in wrists.items() if side in old['wrists']),default=0))
                        rapid=relative>=self.settings.FIGHT_RELATIVE_SPEED and all(speed>=self.settings.FIGHT_ARM_SPEED for speed in arm_speeds)
                delta=distance-state['last_distance'];direction=1 if delta>.01 else -1 if delta<-.01 else 0
                reversal=bool(direction and state['direction'] and direction!=state['direction'])
                if direction:state['direction']=direction
                state['last_distance']=distance
                state['samples'].append((now,rapid,reversal))
                while state['samples'] and now-state['samples'][0][0]>5:state['samples'].popleft()
                evidence=close and rapid and sum(s[1] for s in state['samples'])>=3 and sum(s[2] for s in state['samples'])>=3
                if evidence:
                    state.pop('calm_since',None);state.setdefault('candidate_since',now)
                    if state['phase']!='FIGHT_CONFIRMED':state['phase']='FIGHT_CANDIDATE'
                    if now-state['candidate_since']>=self.settings.FIGHT_PERSISTENCE_SECS:state['phase']='FIGHT_CONFIRMED'
                else:
                    state.pop('candidate_since',None)
                    if state['phase']=='FIGHT_CONFIRMED':
                        state.setdefault('calm_since',now)
                        if now-state['calm_since']>=self.settings.FIGHT_CLEAR_SECS:state['phase']='NORMAL';state['samples'].clear()
                    else:state['phase']='NORMAL'
                if state['phase']=='FIGHT_CONFIRMED':events.append(event('suspected_fight','high',track_ids=list(key)))
        for key,state in list(self.pairs.items()):
            if key not in seen and now-state['last_seen']>self.settings.FIGHT_CLEAR_SECS:del self.pairs[key]
        return events  # Preserve independent pair episodes for alert routing.

    def _bags(self,current,people,shape,now):
        events=[];active=set()
        duration=(self.settings.ABANDONED_BAG_TEST_SECS if self.settings.ACTIVITY_DEBUG else self.settings.ABANDONED_BAG_SECS)
        for tid,bag in current.items():
            if bag['class_name'] not in BAGS:continue
            active.add(tid);p=bag['center']
            state=self.bags.setdefault(tid,{'anchor':p,'last_seen':now,'owner':None})
            # Reappearing IDs do not prove the bag stayed stationary while unseen.
            if now-state['last_seen']>3:
                state=self.bags[tid]={'anchor':p,'last_seen':now,'owner':None}
            state['last_seen']=now
            h,w=shape[:2]
            def person_distance(person):
                a,b,c,d=person['bbox'];a,c=a/w,c/w;b,d=b/h,d/h
                return math.hypot(max(a-p[0],0,p[0]-c),max(b-p[1],0,p[1]-d))
            nearby=sorted((person_distance(t),owner) for owner,t in people.items())
            near=nearby and nearby[0][0]<=self.settings.BAG_OWNER_RADIUS
            if near:
                if len(nearby)==1 or nearby[1][0]-nearby[0][0]>.03:state['owner']=nearby[0][1]
                else:state['owner']=None  # Require a fresh unambiguous association.
                state.pop('unattended_since',None);state['anchor']=p
            elif math.dist(p,state['anchor'])>self.settings.BAG_STATIONARY_RADIUS:
                state['anchor']=p;state.pop('unattended_since',None)
            elif state['owner'] is not None:
                state.setdefault('unattended_since',now)
                if now-state['unattended_since']>=duration:events.append(event('abandoned_bag','high',bag_track_id=tid,owner_track_id=state['owner']))
        self.bags={tid:s for tid,s in self.bags.items() if tid in active or now-s['last_seen']<=3}
        return [event('abandoned_bag','high',bag_track_ids=[e['bag_track_id'] for e in events],
                      owner_track_ids=[e['owner_track_id'] for e in events])] if events else []

    def _after_hours(self,people,now,wall_time):
        schedule=self.config.get('schedule') or {}
        if not schedule.get('enabled',False):self.after_since=None;return []
        local=(datetime.now(ZoneInfo(schedule['timezone'])) if wall_time is None else wall_time.astimezone(ZoneInfo(schedule['timezone'])))
        minute=local.hour*60+local.minute
        def mins(value):h,m=map(int,value.split(':'));return h*60+m
        def permitted(rule):
            start,end=mins(rule['start']),mins(rule['end'])
            return start<=minute<end if start<end else minute>=start or minute<end
        scopes=[z for z in schedule.get('zones',[]) if z.get('enabled',True)]
        offending=[]
        for tid,person in people.items():
            rules=[scope for scope in scopes if self.inside(person['foot'],scope['points'])]
            if any(not permitted(rule) for rule in (rules or [schedule])):offending.append(tid)
        if not offending:self.after_since=None;return []
        if self.after_since is None:self.after_since=now
        return [event('after_hours_presence','high',track_ids=offending)] if now-self.after_since>=self.settings.AFTER_HOURS_CONFIRM_SECS else []

    def _exit_blockage(self,current,now):
        events=[];active=set()
        for zone in self.config.get('exit_zones',[]):
            if not zone.get('enabled',True):continue
            blockers=[]
            for tid,track in current.items():
                point=track['foot'] if track['class_name']=='person' else track['center']
                key=(zone['id'],tid)
                if self.inside(point,zone['points']):
                    active.add(key);self.exits.setdefault(key,now)
                    if now-self.exits[key]>=self.settings.EXIT_BLOCKAGE_SECS:blockers.append(tid)
            if blockers:events.append(event('emergency_exit_blocked','high',zone_id=zone['id'],zone_name=zone['name'],track_ids=blockers))
        self.exits={key:stamp for key,stamp in self.exits.items() if key in active}
        return events  # Independently confirmed exit zones need separate episodes.

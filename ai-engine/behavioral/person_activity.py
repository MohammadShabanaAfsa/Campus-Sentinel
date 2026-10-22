"""Conservative phone-hand association and repeated hand-to-mouth rules.

Consumes real detections/landmarks on existing IDs; creates no alert tasks.
Coordinates supplied to analyze() are full-frame pixels, distances normalized
by visible shoulder width. Instances and their state belong to a capture thread.
"""
import math
import time
import json
from collections import deque
from dataclasses import dataclass, field
from loguru import logger
from ai_engine.vision.behavior_overlay import event


@dataclass
class PhoneState:
    since: float
    last_seen: float
    hits: int = 1
    confirmed: bool = False


@dataclass
class EatingState:
    events: deque = field(default_factory=deque)
    hands: dict = field(default_factory=dict)
    last_observed: float = 0
    selected_wrist: str = None


class PersonActivityAnalyzer:
    def __init__(self, camera_id, settings, general_face_activities=False, camera_name='', zone_type=''):
        self.camera_id=camera_id
        self.settings=settings
        self.phones={}
        self.eating={}
        self.last_signals={}
        self._face_pose=None
        self.camera_name = camera_name
        self.zone_type = zone_type
        self.mediapipe_executed = set()
        self.debug_snapshots = {}
        self.sample_counts = {}
        self.phone_observations = {}
        self.reset_reasons = {}
        self.last_track_seen = {}
        self._sleeping = self._talking = None
        if general_face_activities:
            from ai_engine.classroom.student_state import SleepingDetector, TalkingDetector
            # Independent per-stream state; reuse rules without classroom orchestration.
            self._sleeping = SleepingDetector(camera_id, landmark_grace_secs=getattr(settings,'SLEEPING_LANDMARK_GRACE_SECS',3.0))
            self._sleeping.ear_threshold=getattr(settings,'GENERAL_SLEEP_EAR_THRESHOLD',None) or getattr(settings,'SLEEP_EAR_THRESHOLD',.20)
            self._talking = TalkingDetector(camera_id, mar_std_threshold=getattr(settings,'GENERAL_TALKING_MAR_STD_THRESHOLD',None) or getattr(settings,'TALKING_MAR_STD_THRESHOLD',.035))

    def sample(self, frame, tracks):
        if self._face_pose is None:
            from ai_engine.classroom.face_pose_analyzer import FacePoseAnalyzer
            self._face_pose=FacePoseAnalyzer.get_instance(self.camera_id)
        signals={}
        self.mediapipe_executed.clear()
        h,w=frame.shape[:2]
        for track in tracks:
            if track.get('class_name')!='person' or track.get('time_since_update',0)>0:
                continue
            x1,y1,x2,y2=track['bbox']
            padding=getattr(self.settings,'ACTIVITY_POSE_CROP_PADDING',.20)
            dx,dy=(x2-x1)*padding,(y2-y1)*padding
            x1,y1,x2,y2=x1-dx,y1-dy,x2+dx,y2+dy
            x1,y1=max(0,int(x1)),max(0,int(y1))
            x2,y2=min(w,int(x2)),min(h,int(y2))
            if x2-x1<20 or y2-y1<20:
                continue
            signals[track['track_id']]=self._face_pose.analyze_crop(frame[y1:y2,x1:x2])
            signals[track['track_id']]['analysis_bbox']=[x1,y1,x2,y2]
            signals[track['track_id']]['original_person_bbox']=track['bbox']
            signals[track['track_id']]['crop_touches_frame_edge']=x1==0 or y1==0 or x2==w or y2==h
            raw=signals[track['track_id']]
            # Keep the face/pose inputs that drive sleeping and talking unchanged.
            # Recover only limb signals from a wider crop when no usable wrist exists.
            if not raw.get('wrists') and hasattr(type(self._face_pose),'analyze_activity_limbs'):
                a,b,c,d=track['bbox'];padding=getattr(self.settings,'EATING_LIMB_CROP_PADDING',.35)
                limb_box=[max(0,int(a-(c-a)*padding)),max(0,int(b-(d-b)*padding)),
                          min(w,int(c+(c-a)*padding)),min(h,int(d+(d-b)*padding))]
                la,lb,lc,ld=limb_box
                if limb_box!=[x1,y1,x2,y2] and lc-la>=20 and ld-lb>=20:
                    try:
                        limbs=self._face_pose.analyze_activity_limbs(frame[lb:ld,la:lc],
                            getattr(self.settings,'EATING_WRIST_VISIBILITY_THRESHOLD',.50))
                        raw['limb_recovery_visibility']=limbs['landmark_visibility']
                        if limbs['wrists']:
                            for key in ('wrists','elbows','shoulders','wrist_sources'):raw[key]=limbs[key]
                            raw['landmark_visibility']=limbs['landmark_visibility']
                            raw['limb_analysis_bbox']=limb_box
                    except Exception as error:
                        logger.debug(f'Activity limb recovery unavailable: {type(error).__name__}')
            for side,source in list(raw.get('wrist_sources',{}).items()):
                if source!='hands':continue
                a0,b0,c0,d0=raw.get('limb_analysis_bbox',[x1,y1,x2,y2])
                p=raw['wrists'][side];px,py=a0+p[0]*(c0-a0),b0+p[1]*(d0-b0)
                a,b,c,d=track['bbox']
                ambiguous=any(t['track_id']!=track['track_id'] and t.get('class_name')=='person' and t['bbox'][0]<=px<=t['bbox'][2] and t['bbox'][1]<=py<=t['bbox'][3] for t in tracks)
                if ambiguous or not (a-20<=px<=c+20 and b-20<=py<=d+20):
                    raw['wrists'].pop(side,None);raw['wrist_sources'].pop(side,None)
            if self._face_pose._face_mesh is not None or self._face_pose._pose is not None:
                self.mediapipe_executed.add(track['track_id'])
        self.last_signals=signals
        return signals

    @staticmethod
    def _geometry(track, raw, frame_shape):
        h,w=frame_shape[:2]
        x1,y1,x2,y2=raw.get('analysis_bbox',track['bbox'])
        x1,y1=max(0,int(x1)),max(0,int(y1));x2,y2=min(w,int(x2)),min(h,int(y2))
        def point(value,bbox=None):
            if value is None or len(value)!=2 or not all(math.isfinite(v) and 0<=v<=1 for v in value):return None
            a,b,c,d=bbox or [x1,y1,x2,y2]
            return (a+value[0]*(c-a),b+value[1]*(d-b))
        limb_bbox=raw.get('limb_analysis_bbox',[x1,y1,x2,y2])
        geometry={key:{side:point(value,limb_bbox) for side,value in raw.get(key,{}).items() if point(value,limb_bbox) is not None}
                  for key in ('wrists','elbows','shoulders')}
        geometry['mouth']=point(raw.get('mouth_center')) if raw.get('face_detected') else None
        shoulders=geometry['shoulders']
        geometry['scale']=math.dist(shoulders['left'],shoulders['right']) if len(shoulders)==2 else 0
        return geometry

    @staticmethod
    def _wrist_quality(raw,side):
        source=raw.get('wrist_sources',{}).get(side,'pose')
        key=f'{side}_hand_wrist' if source=='hands' else f'{side}_wrists'
        return raw.get('landmark_visibility',{}).get(key,{}).get('visibility',1.0)

    def _eating_geometry(self,track,raw,frame_shape):
        """Eating-only wrist acceptance; the phone geometry remains unchanged."""
        geometry=self._geometry(track,raw,frame_shape)
        geometry['wrist_quality']={side:self._wrist_quality(raw,side) for side in geometry['wrists']}
        geometry['wrist_sources']=dict(raw.get('wrist_sources',{}))
        h,w=frame_shape[:2]
        a,b,c,d=raw.get('analysis_bbox',track['bbox'])
        a,b,c,d=max(0,int(a)),max(0,int(b)),min(w,int(c)),min(h,int(d))
        cutoff=getattr(self.settings,'EATING_WRIST_VISIBILITY_THRESHOLD',.50)
        for side,candidate in raw.get('eating_wrist_candidates',{}).items():
            if side in geometry['wrists'] or candidate['visibility']<cutoff:continue
            x,y=candidate['point']
            if not all(math.isfinite(v) and 0<=v<=1 for v in (x,y)):continue
            geometry['wrists'][side]=(a+x*(c-a),b+y*(d-b))
            geometry['wrist_quality'][side]=candidate['visibility']
            geometry['wrist_sources'][side]='pose_eating_candidate'
        return geometry

    @staticmethod
    def _step_eating_hand(hand, distance, now, settings):
        """Observe one hand; near dwell ends at LEAVING, not at the later AWAY."""
        near=settings.EATING_MOUTH_DISTANCE_THRESHOLD
        away=getattr(settings,'EATING_AWAY_DISTANCE_THRESHOLD',2*near)
        previous=hand.get('phase')
        completed=False
        if distance>=away:
            since=hand.get('near_since')
            dwell=hand.get('near_duration')
            if dwell is None and since is not None:dwell=now-since
            completed=bool(hand.get('away') and dwell is not None and
                settings.EATING_MIN_NEAR_SECS<=dwell<=settings.EATING_MAX_NEAR_SECS)
            hand.update(away=True,near_since=None,near_duration=None,phase='AWAY')
        elif distance<=near:
            if hand.get('away'):
                if hand.get('near_since') is None:hand['near_since']=now
                elif previous=='LEAVING' and hand.get('near_duration') is not None:
                    hand['near_since']=now-hand['near_duration']
                hand['near_duration']=None
            hand['phase']='NEAR_MOUTH'
        elif hand.get('near_since') is not None:
            if previous!='LEAVING':hand['near_duration']=now-hand['near_since']
            hand['phase']='LEAVING'
        else:
            hand['phase']='APPROACHING'
        hand['last_distance']=distance
        hand['last_valid_at']=now
        return completed

    def analyze(self, tracks, detections, signals, frame_shape, now=None):
        now=time.monotonic() if now is None else now
        s=self.settings
        persons={t['track_id']:t for t in tracks if t.get('class_name')=='person' and t.get('time_since_update',0)==0}
        for tid in persons:self.last_track_seen[tid]=now
        grace=getattr(s,'ACTIVITY_TRACK_GRACE_SECS',3.0)
        retained={tid for tid,seen in self.last_track_seen.items() if now-seen<=grace} | set(persons)
        for tid in list(self.last_track_seen):
            if tid not in retained:del self.last_track_seen[tid]
        geometry={tid:self._geometry(t,signals.get(tid,{}),frame_shape) for tid,t in persons.items()}
        if s.ACTIVITY_DEBUG:
            removed = set(self.eating)-retained
            for tid in removed:
                logger.info('ACTIVITY_STATE_RESET '+json.dumps({'camera_id':self.camera_id,'camera_name':self.camera_name,
                    'track_id':tid,'reason':'track_grace_expired','sample_time':time.time()}))
        for states in (self.phones,self.eating,self.reset_reasons):
            for tid in list(states):
                if tid not in retained:del states[tid]
        if self._sleeping is not None:
            for tid in retained-set(persons):
                self._sleeping.update(tid,{})
                self._talking.update(tid,{})
            # Retain missing tracks within grace, but exclude them from output.
            self._sleeping.cleanup(retained,force=True)
            self._talking.cleanup(retained)
        matched=set()
        self.phone_observations = {tid: [] for tid in persons}
        for phone in detections:
            if phone.get('class_name')!='cell phone' or phone.get('confidence',0)<getattr(s,'YOLO_PHONE_CONFIDENCE_THRESHOLD',.25):continue
            px1,py1,px2,py2=phone['bbox'];cx,cy=(px1+px2)/2,(py1+py2)/2
            def wrist_edge_distance(p):
                return math.hypot(max(px1-p[0],0,p[0]-px2),max(py1-p[1],0,p[1]-py2))
            candidates=[]
            for tid,track in persons.items():
                x1,y1,x2,y2=track['bbox'];g=geometry[tid];scale=g['scale']
                margin=s.PHONE_PERSON_ASSOCIATION_MARGIN
                observation = {'confidence': phone.get('confidence'), 'associated_track_id': None,
                    'source':phone.get('source','full_frame'),'bbox':phone['bbox'],
                    'phone_to_wrist_distance': min((math.dist(p,(cx,cy))/scale for p in g['wrists'].values()), default=None) if scale>=10 else None,
                    'reason': None}
                self.phone_observations[tid].append(observation)
                if scale<10:
                    observation['reason']='shoulder_scale_missing';continue
                shoulder_y=sum(p[1] for p in g['shoulders'].values())/2
                if not (x1-margin<=cx<=x2+margin and y1-margin<=cy<=max(y1+.75*(y2-y1),shoulder_y+.65*scale)):
                    observation['reason']='outside_upper_person_region';continue
                distances=[]
                observation['phone_to_wrist_edge_distance']=min((wrist_edge_distance(p)/scale for p in g['wrists'].values()),default=None)
                for side,wrist in g['wrists'].items():
                    elbow=g['elbows'].get(side)
                    # Raised hand plus phone proximity: a desk phone alone is insufficient.
                    hand_detected=signals.get(tid,{}).get('wrist_sources',{}).get(side)=='hands'
                    chest_hand_contact=(cy<=shoulder_y+.65*scale and wrist[1]<=shoulder_y+.9*scale
                                        and wrist_edge_distance(wrist)<=s.PHONE_HAND_DISTANCE_THRESHOLD*scale)
                    raised_without_elbow=elbow is None and wrist[1]<=shoulder_y+.4*scale
                    if hand_detected or chest_hand_contact or raised_without_elbow or elbow is not None and wrist[1]<elbow[1]-.05*scale:
                        distance=wrist_edge_distance(wrist)/scale
                        if distance<=s.PHONE_HAND_DISTANCE_THRESHOLD:distances.append(distance)
                if distances:candidates.append((min(distances),tid))
                else:
                    # Missing wrist may still have an observed elbow/upper-body handling relationship.
                    shoulder_y=sum(p[1] for p in g['shoulders'].values())/2
                    arm_dist=min((math.dist(p,(cx,cy))/scale for p in g['elbows'].values()),default=math.inf)
                    upright=py2-py1>1.1*(px2-px1)
                    if phone.get('confidence',0)>=.5 and upright and abs(cy-shoulder_y)<=.6*scale and arm_dist<=.75:
                        candidates.append((arm_dist,tid));observation['reason']='upper_body_elbow_evidence'
                    else:observation['reason']='no_near_raised_wrist_or_arm_evidence'
            candidates.sort()
            if candidates and (len(candidates)==1 or candidates[1][0]-candidates[0][0]>.15):
                matched.add(candidates[0][1])
                for observations in self.phone_observations.values():
                    observations[-1]['associated_track_id']=candidates[0][1]
                self.phone_observations[candidates[0][1]][-1]['reason']='associated'
            elif candidates:
                for _,tid in candidates:self.phone_observations[tid][-1]['reason']='ambiguous_person_association'
        output=[]
        for tid in persons:
            self.reset_reasons[tid] = {}
            sleep_state = talk_state = {}
            if self._sleeping is not None:
                raw = signals.get(tid, {})
                sleep_state = self._sleeping.update(tid, raw)
                talk_state = self._talking.update(tid, raw)
                if sleep_state['is_sleeping']:
                    output.append(event('sleeping', 'low', tid))
                if talk_state['is_talking']:
                    output.append(event('talking', 'low', tid))
            state=self.phones.get(tid)
            if tid in matched:
                if state is None or now-state.last_seen>s.PHONE_USE_CLEAR_TIMEOUT_SECS:
                    state=self.phones[tid]=PhoneState(now,now)
                else:state.last_seen=now;state.hits+=1
                state.confirmed=(now-state.since>=s.PHONE_USE_MIN_DURATION_SECS and state.hits>=s.PHONE_USE_MIN_HITS)
            elif state is not None and now-state.last_seen>s.PHONE_USE_CLEAR_TIMEOUT_SECS:
                self.reset_reasons[tid]['phone_use'] = 'phone_missing_beyond_clear_timeout'
                del self.phones[tid];state=None
            if state is not None and state.confirmed:output.append(event('phone_use','low',tid))
            eat=self.eating.setdefault(tid,EatingState())
            while eat.events and now-eat.events[0]>s.EATING_WINDOW_SECS:eat.events.popleft()
            g=self._eating_geometry(persons[tid],signals.get(tid,{}),frame_shape)
            valid=g['mouth'] is not None and g['scale']>=10
            threshold=s.EATING_MOUTH_DISTANCE_THRESHOLD
            away_threshold=getattr(s,'EATING_AWAY_DISTANCE_THRESHOLD',2*threshold)
            landmark_grace=min(getattr(s,'EATING_MAX_LANDMARK_GRACE_SECS',3.0),
                max(getattr(s,'EATING_LANDMARK_GRACE_SECS',1.5),2*max(0,now-eat.last_observed)))
            if now-eat.last_observed>max(s.EATING_MAX_NEAR_SECS,3*s.ACTIVITY_ANALYSIS_INTERVAL_SECS):
                if eat.hands:self.reset_reasons[tid]['eating']='sample_gap_interrupted_cycle'
                eat.hands.clear()
            visible=[side for side in ('left','right') if side in g['wrists'] and
                     g['wrist_quality'][side]>=getattr(s,'EATING_WRIST_VISIBILITY_THRESHOLD',.50)]
            current=eat.selected_wrist
            if current not in visible or eat.hands.get(current,{}).get('phase') in (None,'AWAY'):
                eat.selected_wrist=max(visible,key=lambda side:g['wrist_quality'][side],default=None)
            for side in ('left','right'):
                wrist=g['wrists'].get(side)
                if not valid or side not in visible:
                    if not valid or not visible:self.reset_reasons[tid]['eating'] = 'missing_mouth_wrist_or_shoulder_landmarks'
                    hand=eat.hands.get(side)
                    if hand is not None:
                        hand.setdefault('missing_since',now)
                        hand.setdefault('missing_grace',landmark_grace)
                        hand.setdefault('paused_at',hand.get('last_valid_at',now))
                        wrist_meta=signals.get(tid,{}).get('landmark_visibility',{}).get(f'{side}_wrists',{})
                        if wrist is None and wrist_meta.get('in_crop') is False:hand['left_frame']=True
                        if now-hand['missing_since']>hand['missing_grace']:eat.hands.pop(side,None)
                    continue
                distance=math.dist(wrist,g['mouth'])/g['scale']
                hand=eat.hands.setdefault(side,{'away':False,'near_since':None,'near_duration':None})
                old_distance=hand.get('last_distance',distance)
                hand['motion']=abs(distance-old_distance)
                if 'missing_since' in hand:
                    # Pause the phase; do not count an unobserved withdrawal as a cycle.
                    gap=now-hand['missing_since']
                    budget=hand.pop('missing_grace',landmark_grace)
                    paused_at=hand.pop('paused_at',hand['missing_since'])
                    left_frame=hand.pop('left_frame',False)
                    if gap>budget or left_frame or (distance>=away_threshold and hand.get('phase')!='LEAVING'):
                        hand.update(near_since=None,near_duration=None,away=False)
                    elif hand['near_since'] is not None and hand.get('phase')!='LEAVING':hand['near_since']+=now-paused_at
                    hand.pop('missing_since',None)
                if self._step_eating_hand(hand,distance,now,s):
                    if not eat.events or now-eat.events[-1]>=s.EATING_MIN_EVENT_INTERVAL_SECS:eat.events.append(now)
            # A highly visible resting hand must not hide the other hand's real cycle.
            def moving_hand_rank(side):
                hand=eat.hands.get(side,{})
                phase=hand.get('phase')
                dwell=hand.get('near_duration')
                if dwell is None and hand.get('near_since') is not None:dwell=now-hand['near_since']
                in_cycle=bool(hand.get('away') and phase!='AWAY' and (dwell is None or dwell<=s.EATING_MAX_NEAR_SECS))
                near_cycle=in_cycle and phase in ('NEAR_MOUTH','LEAVING')
                motion=hand.get('motion',0)
                # Motion chooses the active hand; keep it selected during its hold.
                return (motion>.03,motion if motion>.03 else 0,side==eat.selected_wrist and near_cycle,
                        near_cycle,in_cycle,g['wrist_quality'][side])
            eat.selected_wrist=max(visible,key=moving_hand_rank,default=None)
            eat.last_observed=now
            confirmed=(len(eat.events)>=s.EATING_MIN_EVENTS and now-eat.events[-1]<=s.EATING_CLEAR_TIMEOUT_SECS)
            if confirmed:output.append(event('eating','low',tid))
            if getattr(s,'EATING_DEBUG',False):
                selected=eat.selected_wrist
                logger.info('EATING_SAMPLE '+json.dumps({'camera_id':self.camera_id,'track_id':tid,
                    'left_wrist_visibility':g['wrist_quality'].get('left'),
                    'right_wrist_visibility':g['wrist_quality'].get('right'),
                    'selected_hand':selected,'wrist_visibility':g['wrist_quality'][selected] if selected else None,
                    'normalized_distance':math.dist(g['wrists'][selected],g['mouth'])/g['scale'] if valid and selected else None,
                    'current_phase':eat.hands.get(selected,{}).get('phase','UNAVAILABLE') if valid and selected else 'UNAVAILABLE',
                    'completed_cycles':len(eat.events)}))
            if getattr(s,'PHONE_EATING_DEBUG',False):
                observations=self.phone_observations.get(tid,[])
                logger.info('PHONE_EATING_SAMPLE '+json.dumps({'camera_id':self.camera_id,'camera_name':self.camera_name,
                    'track_id':tid,'sample_time':time.time(),
                    'phone':{'observations':observations,'hits':state.hits if state else 0,
                        'roi_attempted':bool(signals.get(tid,{}).get('phone_roi_attempted')),
                        'duration':now-state.since if state else 0,'confirmed':bool(state and state.confirmed)},
                    'eating':{'selected_wrist':eat.selected_wrist,'visibility':signals.get(tid,{}).get('landmark_visibility',{}),
                        'limb_analysis_bbox':signals.get(tid,{}).get('limb_analysis_bbox'),
                        'recovery_visibility':signals.get(tid,{}).get('limb_recovery_visibility',{}),
                        'distance':math.dist(g['wrists'][eat.selected_wrist],g['mouth'])/g['scale'] if valid and eat.selected_wrist else None,
                        'wrist_distances':{side:math.dist(p,g['mouth'])/g['scale'] for side,p in g['wrists'].items()} if valid else {},
                        'phases':eat.hands,'cycles':len(eat.events),'confirmed':confirmed,
                        'test_cycle_met':len(eat.events)>=getattr(s,'EATING_TEST_MIN_CYCLES',1),
                        'reset_reason':self.reset_reasons[tid].get('eating')}}))
        return output

    def debug_sample(self, tracks, signals, frame_shape, frame_number, classroom_monitor=None):
        """Read actual state after processing; never update rules or consume alerts."""
        if not self.settings.ACTIVITY_DEBUG:
            self.debug_snapshots.clear()
            return
        sampled_at = time.time()
        mono = time.monotonic()
        active = {t['track_id'] for t in tracks if t.get('class_name')=='person' and t.get('time_since_update',0)==0}
        for tid in list(self.sample_counts):
            if tid not in active and tid not in self.last_track_seen:
                self.sample_counts.pop(tid, None)
                self.debug_snapshots.pop(tid, None)
        sleeping = self._sleeping if self._sleeping is not None else getattr(classroom_monitor, '_sleeping', None)
        talking = self._talking if self._talking is not None else getattr(classroom_monitor, '_talking', None)
        for track in tracks:
            tid = track['track_id']
            if tid not in active:continue
            raw = signals.get(tid, {})
            g = self._geometry(track, raw, frame_shape)
            self.sample_counts[tid] = self.sample_counts.get(tid, 0)+1
            def face_snapshot(detector, kind):
                value = dict(getattr(detector, 'diagnostics', {}).get(tid, {}))
                previous = self.debug_snapshots.get(tid, {}).get(kind, {})
                value['updated_this_sample'] = value.get('sample_time') is not None and value.get('sample_time') != previous.get('sample_time')
                value['sample_age_secs'] = sampled_at-value['sample_time'] if value.get('sample_time') else None
                if not value.get('sample_time'):value['reset_reason']='not_processed_by_face_rule_yet_or_faculty_excluded'
                return value
            sleep = face_snapshot(sleeping, 'sleeping')
            talk = face_snapshot(talking, 'talking')
            phone = self.phones.get(tid)
            eat = self.eating.get(tid, EatingState())
            distances = {side: math.dist(wrist,g['mouth'])/g['scale'] if g['mouth'] is not None and g['scale']>=10 else None
                         for side,wrist in g['wrists'].items()}
            near = self.settings.EATING_MOUTH_DISTANCE_THRESHOLD
            away = getattr(self.settings,'EATING_AWAY_DISTANCE_THRESHOLD',2*near)
            eating_confirmed = len(eat.events)>=self.settings.EATING_MIN_EVENTS and mono-eat.events[-1]<=self.settings.EATING_CLEAR_TIMEOUT_SECS
            observations = self.phone_observations.get(tid, [])
            snapshot = {'camera_name':self.camera_name,'camera_id':self.camera_id,'zone_type':self.zone_type,
                'track_id':tid,'frame_number':frame_number,'sample_time':sampled_at,
                'pose_inputs':{'analysis_bbox':raw.get('analysis_bbox'),'original_person_bbox':raw.get('original_person_bbox'),
                    'crop_touches_frame_edge':raw.get('crop_touches_frame_edge'),'pose_detected':raw.get('pose_detected'),
                    'landmark_visibility':raw.get('landmark_visibility',{})},
                'same_track_sample_count':self.sample_counts[tid], 'mediapipe_executed':tid in self.mediapipe_executed,
                'sleeping':{**sleep,'threshold_secs':getattr(sleeping,'threshold_secs',None),
                    'current_face_landmarks_available':bool(raw.get('face_detected')),'current_ear':raw.get('ear'),'current_head_down':raw.get('head_down')},
                'talking':{**talk,'threshold_secs':getattr(talking,'threshold_secs',None),'current_mar':raw.get('mar'),
                    'current_mouth_landmarks_available':raw.get('mar') is not None},
                'phone_use':{'cell_phone_detected':bool(observations),'observations':observations,
                    'phone_confidence':max((o['confidence'] for o in observations),default=None),
                    'phone_to_wrist_distance':min((o['phone_to_wrist_distance'] for o in observations if o['phone_to_wrist_distance'] is not None),default=None),
                    'associated_track_ids':sorted({o['associated_track_id'] for o in observations if o['associated_track_id'] is not None}),
                    'distance_units':'shoulder_widths',
                    'wrist_landmarks_available':bool(g['wrists']),'hit_count':phone.hits if phone else 0,
                    'duration_secs':mono-phone.since if phone else 0,'confirmed':bool(phone and phone.confirmed),
                    'reset_reason':self.reset_reasons.get(tid,{}).get('phone_use') or (None if phone else ('no_cell_phone_detected' if not observations else 'no_valid_persistent_association'))},
                'eating':{'mouth_point_available':g['mouth'] is not None,'left_wrist_distance':distances.get('left'),
                    'shoulder_width_px':g['scale'],
                    'right_wrist_distance':distances.get('right'),'distance_units':'shoulder_widths',
                    'hand_states':{side:('UNAVAILABLE' if distances.get(side) is None else 'NEAR' if distances[side]<=near else 'AWAY' if distances[side]>=away else 'BETWEEN') for side in ('left','right')},
                    'cycle_phase':eat.hands,'completed_cycles':len(eat.events),'required_cycles':self.settings.EATING_MIN_EVENTS,
                    'window_secs':self.settings.EATING_WINDOW_SECS,'event_ages_secs':[mono-t for t in eat.events],
                    'confirmed':eating_confirmed,'reset_reason':self.reset_reasons.get(tid,{}).get('eating') or ('missing_mouth_wrist_or_shoulder_landmarks' if g['mouth'] is None or not distances or g['scale']<10 else 'insufficient_completed_cycles' if len(eat.events)<self.settings.EATING_MIN_EVENTS else 'last_cycle_expired' if not eating_confirmed else None)}}
            snapshot['eating']['debug_test_cycle_met']=len(eat.events)>=getattr(self.settings,'EATING_TEST_MIN_CYCLES',1)
            self.debug_snapshots[tid] = snapshot
            logger.info('ACTIVITY_SAMPLE '+json.dumps(snapshot))

    def draw_debug(self, frame, tracks):
        if not self.settings.ACTIVITY_DEBUG:return frame
        import cv2
        candidates = [t for t in tracks if t.get('class_name')=='person' and t['track_id'] in self.debug_snapshots]
        if not candidates:return frame
        track = min(candidates, key=lambda t:t['track_id'])
        d = self.debug_snapshots[track['track_id']]
        sleep,talk,phone,eat = (d[k] for k in ('sleeping','talking','phone_use','eating'))
        def number(value, digits=2):return f'{value:.{digits}f}' if isinstance(value,(float,int)) else 'NA'
        lines = [f'DEBUG #{track["track_id"]}',
            f'SLEEP EAR={number(sleep.get("ear"))} dur={number(sleep.get("duration_secs"),1)}/{number(sleep.get("threshold_secs"),0)}',
            f'TALK std={number(talk.get("mar_variability"),3)} samples={talk.get("mouth_samples",0)}',
            f'PHONE hits={phone["hit_count"]} dur={number(phone["duration_secs"],1)}',
            f'EAT cycles={eat["completed_cycles"]}/{eat["required_cycles"]}']
        h,w=frame.shape[:2]
        x=max(0,min(w-300,int(track['bbox'][0])))
        y=max(40,min(h-105,int(track['bbox'][3])+5))
        cv2.rectangle(frame,(x,y),(min(w-1,x+300),min(h-1,y+100)),(15,15,15),-1)
        for i,line in enumerate(lines):cv2.putText(frame,line,(x+3,min(h-2,y+17+i*19)),cv2.FONT_HERSHEY_SIMPLEX,.43,(0,255,255),1)
        return frame
